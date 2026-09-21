"""Verification-only production evidence boundary (ADR-092).

This module authenticates receipt bytes that a host has configured it to trust. It never
creates keys, signs anything, discovers a key from a document, or invents a permit: a
missing trust policy, receipt store, current-state authority or per-attempt host lease is
a typed blocker. Receipt labels (``EvidenceKind``) are descriptions, never authority.

Evidence is a closed, purpose-specific Ed25519 document with its own domain prefix. The
signature is checked through a *separate* ``Ed25519SignatureVerifier`` instance that holds
only the evidence pins. Every resolution also asks an injected ``CurrentEvidenceAuthority``
for fresh state; nothing here caches or returns a transferable permission. A resolution is
an audit observation of one invocation, not a capability.

Limits: these are in-process checks by trusted host code. A caller that controls the
interpreter, the raw store or the raw service is not stopped by them; real effect
authority stays with external host leases. Attestations bind exact claims and candidate
but cannot prove the claim is true; the configured issuer's remit is an external
obligation.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, NoReturn, Protocol

from .brain_kernel.promotion_auth import (
    Ed25519SignatureVerifier,
    PrincipalBinding,
    PromotionAuthenticationError,
    SignatureVerifier,
)
from .runtime_contracts import canonical_digest as lease_canonical_digest
from .whole_os_qualification import (
    Disposition,
    EvidenceKind,
    EvidenceRef,
    ExternalObligation,
    QualificationLedger,
)

EVIDENCE_KIND = "hive-production-evidence"
EVIDENCE_SCHEMA_VERSION = 1
EVIDENCE_ALGORITHM = "ed25519"
# Domain prefix prepended to the canonical signature-free payload. The signature is never
# part of its own preimage.
EVIDENCE_DOMAIN_PREFIX = b"hive-mind-os/production-evidence/v1\n"

MODE_LEGACY = "legacy-unspecified"
MODE_TRUSTED_LOCAL = "trusted-local"
MODE_PRODUCTION = "production-evidence-v1"

_MAX_INT = 2**53
_MAX_TEXT = 4096
_MAX_ID = 512
_MAX_LIST = 256
_MAX_DEPTH = 6
_MAX_NODES = 512


class EvidenceBlocker(StrEnum):
    TRUST_STORE_MISSING = "trust-store-missing"
    RECEIPT_STORE_MISSING = "receipt-store-missing"
    CURRENT_AUTHORITY_MISSING = "current-authority-missing"
    LEASE_MAPPING_MISSING = "host-lease-mapping-missing"
    POLICY_INVALID = "policy-invalid"
    USE_INVALID = "use-invalid"
    URI_NOT_ALLOWED = "receipt-uri-not-allowed"
    STORE_UNAVAILABLE = "receipt-store-unavailable"
    RECEIPT_OVERSIZE = "receipt-oversize"
    DIGEST_MISMATCH = "digest-mismatch"
    RECEIPT_MALFORMED = "receipt-malformed"
    CRYPTO_UNAVAILABLE = "crypto-unavailable"
    SIGNATURE_INVALID = "signature-invalid"
    ISSUER_UNKNOWN = "issuer-unknown"
    ISSUER_REMIT = "issuer-remit"
    CONTEXT_MISMATCH = "context-mismatch"
    TIME_WINDOW = "time-window"
    EVIDENCE_STALE = "evidence-stale"
    STATUS_UNAVAILABLE = "status-unavailable"
    STATUS_MISMATCH = "status-mismatch"
    STATUS_STALE = "status-stale"
    EVIDENCE_REVOKED = "evidence-revoked"
    STATUS_NOT_ACTIVE = "status-not-active"
    SEPARATION = "principal-separation"
    DUPLICATE_EVIDENCE = "duplicate-evidence"
    INCOMPLETE = "incomplete-evidence"
    MANIFEST_MALFORMED = "manifest-malformed"
    AUDIT_UNAVAILABLE = "audit-unavailable"
    MODE_MISMATCH = "evidence-mode-mismatch"
    CLOCK_INVALID = "clock-invalid"


_CAPABILITY_BLOCKERS = frozenset(
    {
        EvidenceBlocker.TRUST_STORE_MISSING,
        EvidenceBlocker.RECEIPT_STORE_MISSING,
        EvidenceBlocker.CURRENT_AUTHORITY_MISSING,
        EvidenceBlocker.LEASE_MAPPING_MISSING,
        EvidenceBlocker.POLICY_INVALID,
        EvidenceBlocker.CRYPTO_UNAVAILABLE,
        EvidenceBlocker.STORE_UNAVAILABLE,
        EvidenceBlocker.STATUS_UNAVAILABLE,
        EvidenceBlocker.AUDIT_UNAVAILABLE,
        EvidenceBlocker.CLOCK_INVALID,
    }
)
_AUTHORITY_BLOCKERS = frozenset(
    {
        EvidenceBlocker.ISSUER_UNKNOWN,
        EvidenceBlocker.ISSUER_REMIT,
        EvidenceBlocker.SIGNATURE_INVALID,
        EvidenceBlocker.EVIDENCE_REVOKED,
        EvidenceBlocker.STATUS_NOT_ACTIVE,
        EvidenceBlocker.STATUS_MISMATCH,
        EvidenceBlocker.SEPARATION,
        EvidenceBlocker.MODE_MISMATCH,
    }
)


class ProductionEvidenceError(RuntimeError):
    """A typed fail-closed blocker. Its text never contains receipt bytes or keys."""

    def __init__(self, blocker: EvidenceBlocker, detail: str) -> None:
        super().__init__(f"{blocker.value}: {detail}")
        self.blocker = blocker
        self.detail = detail


def _fail(blocker: EvidenceBlocker, detail: str) -> NoReturn:
    raise ProductionEvidenceError(blocker, detail)


def blocker_disposition(blocker: EvidenceBlocker) -> Disposition:
    if blocker in _CAPABILITY_BLOCKERS:
        return Disposition.BLOCKED_CAPABILITY
    if blocker in _AUTHORITY_BLOCKERS:
        return Disposition.BLOCKED_AUTHORITY
    return Disposition.BLOCKED_SOURCE


def obligation_for(
    error: ProductionEvidenceError, blocks_claims: tuple[str, ...]
) -> ExternalObligation:
    """Express a resolution failure as a typed obligation; never as a permit."""
    detail = " ".join(error.detail.split())[:300] or "no detail"
    return ExternalObligation(
        f"production-evidence-{error.blocker.value}",
        blocker_disposition(error.blocker),
        f"{error.blocker.value}: {detail}",
        blocks_claims,
    )


# --- primitive validation -------------------------------------------------------------


def _ident(value: object, label: str, blocker: EvidenceBlocker) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > _MAX_ID
        or not value.isascii()
        or any(character.isspace() or not character.isprintable() for character in value)
    ):
        _fail(blocker, f"{label} must be an exact ASCII identifier")
    return value


def _sha(value: object, label: str, blocker: EvidenceBlocker) -> str:
    if (
        type(value) is not str
        or len(value) != 71
        or not value.startswith("sha256:")
        or set(value[7:]) - set("0123456789abcdef")
    ):
        _fail(blocker, f"{label} must be a lowercase SHA-256 digest")
    return value


def _int(value: object, label: str, blocker: EvidenceBlocker) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_INT:
        _fail(blocker, f"{label} must be a bounded nonnegative integer")
    return value


def _now(value: object) -> int:
    return _int(value, "verification time", EvidenceBlocker.CLOCK_INVALID)


def _canonical_bytes(value: object) -> bytes:
    """This module's own encoding: sorted, compact, ASCII-escaped, no NaN."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=True
    ).encode("ascii")


def _digest_of(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def evidence_preimage(payload: Mapping[str, object]) -> bytes:
    """The exact bytes an issuer must sign: domain prefix + signature-free payload."""
    if "signature" in payload:
        _fail(EvidenceBlocker.RECEIPT_MALFORMED, "the signature is not part of its preimage")
    return EVIDENCE_DOMAIN_PREFIX + _canonical_bytes(dict(payload))


def _claim_value(kind: str, value: object, blocker: EvidenceBlocker) -> object:
    if kind == "id":
        return _ident(value, "claim", blocker)
    if kind == "id_or_empty":
        return "" if value == "" and type(value) is str else _ident(value, "claim", blocker)
    if kind == "text":
        if type(value) is not str or len(value) > _MAX_TEXT or "\x00" in value:
            _fail(blocker, "claim text is invalid or too long")
        return value
    if kind == "digest":
        return _sha(value, "claim", blocker)
    if kind == "int":
        return _int(value, "claim", blocker)
    if kind in {"ids", "texts"}:
        if not isinstance(value, (list, tuple)) or len(value) > _MAX_LIST:
            _fail(blocker, "claim list is invalid or too long")
        item_kind = "id" if kind == "ids" else "text"
        return [_claim_value(item_kind, item, blocker) for item in value]
    _fail(blocker, "unknown claim type")


# --- purpose schema table -------------------------------------------------------------


class EvidencePurpose(StrEnum):
    PILOT_HOST = "pilot-host"
    PILOT_SUPERVISOR = "pilot-supervisor"
    PILOT_DELIVERY_AUTHORITY = "pilot-delivery-authority"
    PILOT_BENCHMARK = "pilot-benchmark"
    PILOT_TARGET = "pilot-target"
    PILOT_RUNTIME_CAPABILITY = "pilot-runtime-capability"
    ATTEMPT_DELIVERY = "attempt-delivery"
    ATTEMPT_RUNTIME = "attempt-runtime"
    PILOT_RESTART = "pilot-restart"
    PILOT_ROLLBACK_CONTROL = "pilot-rollback-control"
    PILOT_OBSERVATION = "pilot-observation"
    CLOSEOUT_REQUIREMENT = "closeout-requirement"
    CLOSEOUT_NODE = "closeout-node"
    CLOSEOUT_ROLE = "closeout-role"
    CLOSEOUT_STAGE = "closeout-stage"
    CLOSEOUT_STARTUP = "closeout-startup"
    CLOSEOUT_ROLLBACK = "closeout-rollback"
    CLOSEOUT_JUDGMENT = "closeout-judgment"


class UseMode(StrEnum):
    # GATE: permits execution; needs fresh, current, explicitly-aged evidence.
    GATE = "gate"
    # RECORD: a historical fact; signature and current status are verified, natural
    # freshness is not required.
    RECORD = "record"


class WindowRule(StrEnum):
    PRE_PILOT = "pre-pilot"  # observed_at <= window_end (the pilot start)
    ATTEMPT = "attempt"  # window_start <= observed_at <= window_end (plan end)
    PILOT = "pilot"  # plan start <= observed_at <= plan end
    THROUGH_PILOT_END = "through-pilot-end"  # observed_at <= window_end
    CLOSEOUT = "closeout"  # only observed <= issued <= now
    POST_SEAL = "post-seal"  # sealed_at <= observed_at <= issued_at <= now


class IssuerRole(StrEnum):
    BUILDER = "builder"
    ATTESTOR = "attestor"
    EVALUATOR = "evaluator"
    JUDGE = "judge"


@dataclass(frozen=True, slots=True)
class PurposeSchema:
    purpose: EvidencePurpose
    mode: UseMode
    window: WindowRule
    claims: tuple[tuple[str, str], ...]
    binds_authority: bool
    roles: frozenset[IssuerRole]

    @property
    def claim_names(self) -> frozenset[str]:
        return frozenset(name for name, _ in self.claims)


_WINDOW_BOUNDS: Mapping[WindowRule, tuple[bool, bool]] = MappingProxyType(
    {
        WindowRule.PRE_PILOT: (False, True),
        WindowRule.ATTEMPT: (True, True),
        WindowRule.PILOT: (True, True),
        WindowRule.THROUGH_PILOT_END: (False, True),
        WindowRule.CLOSEOUT: (False, False),
        WindowRule.POST_SEAL: (True, False),
    }
)

_ATTESTOR = frozenset({IssuerRole.ATTESTOR})
_EVALUATOR = frozenset({IssuerRole.EVALUATOR})
_JUDGE = frozenset({IssuerRole.JUDGE})
_MODE_CLAIM = (("pilot_mode", "id"),)
_ATTEMPT_CLAIMS = (
    ("family_id", "id"),
    ("started_at", "int"),
    ("ended_at", "int"),
)
_ASSESSMENT_CLAIMS = (("disposition", "id"), ("obligation_ids", "ids"))
_OPERATION_CLAIMS = (("argv", "texts"), ("exit_code", "int"))


def _schema(
    purpose: EvidencePurpose,
    mode: UseMode,
    window: WindowRule,
    claims: tuple[tuple[str, str], ...],
    roles: frozenset[IssuerRole],
    *,
    authority: bool,
) -> tuple[EvidencePurpose, PurposeSchema]:
    return purpose, PurposeSchema(purpose, mode, window, claims, authority, roles)


PURPOSE_SCHEMAS: Mapping[EvidencePurpose, PurposeSchema] = MappingProxyType(
    dict(
        (
            _schema(EvidencePurpose.PILOT_HOST, UseMode.GATE, WindowRule.PRE_PILOT, _MODE_CLAIM, _ATTESTOR, authority=True),
            _schema(EvidencePurpose.PILOT_SUPERVISOR, UseMode.GATE, WindowRule.PRE_PILOT, _MODE_CLAIM, _ATTESTOR, authority=True),
            _schema(EvidencePurpose.PILOT_DELIVERY_AUTHORITY, UseMode.GATE, WindowRule.PRE_PILOT, _MODE_CLAIM, _ATTESTOR, authority=True),
            _schema(EvidencePurpose.PILOT_BENCHMARK, UseMode.GATE, WindowRule.PRE_PILOT, (), _ATTESTOR, authority=True),
            _schema(EvidencePurpose.PILOT_TARGET, UseMode.GATE, WindowRule.PRE_PILOT, _MODE_CLAIM, _ATTESTOR, authority=True),
            _schema(EvidencePurpose.PILOT_RUNTIME_CAPABILITY, UseMode.GATE, WindowRule.PRE_PILOT, _MODE_CLAIM, _ATTESTOR, authority=True),
            _schema(
                EvidencePurpose.ATTEMPT_DELIVERY, UseMode.RECORD, WindowRule.ATTEMPT,
                (*_ATTEMPT_CLAIMS, ("resource_units", "int"), ("domain", "id_or_empty")),
                _EVALUATOR, authority=True,
            ),
            _schema(
                EvidencePurpose.ATTEMPT_RUNTIME, UseMode.RECORD, WindowRule.ATTEMPT,
                (*_ATTEMPT_CLAIMS, ("check_class", "id")),
                _EVALUATOR, authority=True,
            ),
            _schema(EvidencePurpose.PILOT_RESTART, UseMode.RECORD, WindowRule.PILOT, _MODE_CLAIM, _ATTESTOR, authority=True),
            _schema(EvidencePurpose.PILOT_ROLLBACK_CONTROL, UseMode.RECORD, WindowRule.THROUGH_PILOT_END, _MODE_CLAIM, _ATTESTOR, authority=True),
            _schema(EvidencePurpose.PILOT_OBSERVATION, UseMode.RECORD, WindowRule.PILOT, (("observed_through", "int"),), _ATTESTOR, authority=True),
            _schema(EvidencePurpose.CLOSEOUT_REQUIREMENT, UseMode.RECORD, WindowRule.CLOSEOUT, _ASSESSMENT_CLAIMS, _ATTESTOR, authority=False),
            _schema(EvidencePurpose.CLOSEOUT_NODE, UseMode.RECORD, WindowRule.CLOSEOUT, _ASSESSMENT_CLAIMS, _ATTESTOR, authority=False),
            _schema(EvidencePurpose.CLOSEOUT_ROLE, UseMode.RECORD, WindowRule.CLOSEOUT, (("role_id", "id"),), _ATTESTOR, authority=False),
            _schema(EvidencePurpose.CLOSEOUT_STAGE, UseMode.RECORD, WindowRule.CLOSEOUT, (("stage_id", "id"),), _ATTESTOR, authority=False),
            _schema(EvidencePurpose.CLOSEOUT_STARTUP, UseMode.RECORD, WindowRule.CLOSEOUT, _OPERATION_CLAIMS, _ATTESTOR, authority=False),
            _schema(EvidencePurpose.CLOSEOUT_ROLLBACK, UseMode.RECORD, WindowRule.CLOSEOUT, _OPERATION_CLAIMS, _ATTESTOR, authority=False),
            _schema(
                EvidencePurpose.CLOSEOUT_JUDGMENT, UseMode.RECORD, WindowRule.POST_SEAL,
                (
                    ("manifest_digest", "digest"),
                    ("release_id", "id"),
                    ("previous_release_digest", "digest"),
                    ("sealed_at", "int"),
                    ("final_disposition", "id"),
                    ("independent_judge_id", "id"),
                ),
                _JUDGE, authority=False,
            ),
        )
    )
)
GATE_PURPOSES = frozenset(
    purpose for purpose, schema in PURPOSE_SCHEMAS.items() if schema.mode is UseMode.GATE
)
assert set(PURPOSE_SCHEMAS) == set(EvidencePurpose)


def _normalize_claims(
    schema: PurposeSchema, claims: object, blocker: EvidenceBlocker
) -> dict[str, object]:
    if not isinstance(claims, Mapping) or set(claims) != set(schema.claim_names):
        _fail(blocker, "claims do not match the closed purpose schema")
    return {name: _claim_value(kind, claims[name], blocker) for name, kind in schema.claims}


# --- the exact use ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvidenceUse:
    """What the host expects a receipt to say. Expected values come from the host's
    frozen plan/manifest, never from the receipt under test."""

    purpose: EvidencePurpose
    subject_id: str
    operation_id: str
    candidate_digest: str
    authority_digest: str | None
    claims: Mapping[str, object]
    window_start: int | None = None
    window_end: int | None = None
    lease_digest: str | None = None

    def __post_init__(self) -> None:
        blocker = EvidenceBlocker.USE_INVALID
        if type(self.purpose) is not EvidencePurpose:
            _fail(blocker, "purpose is not in the closed schema table")
        schema = PURPOSE_SCHEMAS[self.purpose]
        _ident(self.subject_id, "subject", blocker)
        _ident(self.operation_id, "operation", blocker)
        _sha(self.candidate_digest, "candidate digest", blocker)
        if schema.binds_authority:
            _sha(self.authority_digest, "authority digest", blocker)
        elif self.authority_digest is not None:
            _fail(blocker, "this purpose does not bind an authority digest")
        needs_start, needs_end = _WINDOW_BOUNDS[schema.window]
        for name, value, needed in (
            ("window_start", self.window_start, needs_start),
            ("window_end", self.window_end, needs_end),
        ):
            if needed:
                _int(value, name, blocker)
            elif value is not None:
                _fail(blocker, f"{name} is not used by this purpose's window rule")
        if (
            self.window_start is not None
            and self.window_end is not None
            and self.window_start > self.window_end
        ):
            _fail(blocker, "evidence window is empty")
        if self.lease_digest is not None:
            if schema.mode is not UseMode.GATE:
                _fail(blocker, "only gate uses may carry a host lease digest")
            _sha(self.lease_digest, "lease digest", blocker)
        object.__setattr__(
            self,
            "claims",
            MappingProxyType(_normalize_claims(schema, self.claims, blocker)),
        )

    @property
    def schema(self) -> PurposeSchema:
        return PURPOSE_SCHEMAS[self.purpose]

    def document(self) -> dict[str, object]:
        return {
            "purpose": self.purpose.value,
            "subject_id": self.subject_id,
            "operation_id": self.operation_id,
            "candidate_digest": self.candidate_digest,
            "authority_digest": self.authority_digest,
            "claims": dict(self.claims),
            "window_start": self.window_start,
            "window_end": self.window_end,
            "lease_digest": self.lease_digest,
        }

    def digest(self) -> str:
        return _digest_of(self.document())


# --- trusted configuration --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TrustedIssuer:
    """A host-pinned public key and its configured remit. No private key lives here."""

    principal_id: str
    administration_id: str
    key_id: str
    public_key: bytes
    role: IssuerRole
    remit: frozenset[EvidencePurpose]

    def __post_init__(self) -> None:
        blocker = EvidenceBlocker.POLICY_INVALID
        for name in ("principal_id", "administration_id", "key_id"):
            _ident(getattr(self, name), name, blocker)
        if type(self.public_key) is not bytes or len(self.public_key) != 32:
            _fail(blocker, "an evidence public key must be 32 raw bytes")
        if type(self.role) is not IssuerRole:
            _fail(blocker, "issuer role is not in the closed set")
        remit = frozenset(self.remit)
        if any(type(item) is not EvidencePurpose for item in remit):
            _fail(blocker, "issuer remit must name known purposes")
        if any(self.role not in PURPOSE_SCHEMAS[item].roles for item in remit):
            _fail(blocker, "issuer remit exceeds what its role may attest")
        object.__setattr__(self, "remit", remit)

    @property
    def public_key_digest(self) -> str:
        return "sha256:" + hashlib.sha256(self.public_key).hexdigest()

    def document(self) -> dict[str, object]:
        return {
            "principal_id": self.principal_id,
            "administration_id": self.administration_id,
            "key_id": self.key_id,
            "public_key_digest": self.public_key_digest,
            "role": self.role.value,
            "remit": sorted(item.value for item in self.remit),
        }


@dataclass(frozen=True, slots=True)
class EvidenceTrustPolicy:
    """Immutable host trust: pins, remit, ages and allowlists.

    ``promotion_public_key_digests`` must list every configured promotion pin so that
    evidence keys are provably distinct from them. There is no default age: each GATE
    purpose needs an explicit maximum, and RECORD purposes have none.
    """

    generation: str
    issuers: tuple[TrustedIssuer, ...]
    uri_prefixes: tuple[str, ...]
    gate_maximum_age_seconds: Mapping[EvidencePurpose, int]
    status_maximum_age_seconds: int
    promotion_public_key_digests: frozenset[str]
    maximum_receipt_bytes: int = 65536
    store_deadline_seconds: int = 10

    def __post_init__(self) -> None:
        blocker = EvidenceBlocker.POLICY_INVALID
        _ident(self.generation, "policy generation", blocker)
        issuers = tuple(self.issuers)
        if not issuers or any(type(item) is not TrustedIssuer for item in issuers):
            _fail(blocker, "trusted issuers are required")
        for label, values in (
            ("principal", [item.principal_id for item in issuers]),
            ("key", [item.key_id for item in issuers]),
            ("public key", [item.public_key_digest for item in issuers]),
        ):
            if len(set(values)) != len(values):
                _fail(blocker, f"issuer {label} identifiers must be unique")
        promotion = frozenset(self.promotion_public_key_digests)
        for digest in promotion:
            _sha(digest, "promotion pin", blocker)
        if any(item.public_key_digest in promotion for item in issuers):
            _fail(blocker, "an evidence key equals a configured promotion pin")
        # Configured (not proven) separation between builder, evaluator and judge.
        groups = {
            role: {item.administration_id for item in issuers if item.role is role}
            for role in (IssuerRole.BUILDER, IssuerRole.EVALUATOR, IssuerRole.JUDGE)
        }
        roles = tuple(groups)
        for index, left in enumerate(roles):
            for right in roles[index + 1 :]:
                if groups[left] & groups[right]:
                    _fail(blocker, "builder, evaluator and judge share an administration")
        prefixes = tuple(self.uri_prefixes)
        if not prefixes or any(
            type(item) is not str
            or ":" not in item
            or not item.isascii()
            or any(character.isspace() for character in item)
            for item in prefixes
        ):
            _fail(blocker, "receipt URI allowlist prefixes are required")
        ages = dict(self.gate_maximum_age_seconds)
        if set(ages) != set(GATE_PURPOSES) or any(
            type(value) is not int or not 1 <= value <= _MAX_INT for value in ages.values()
        ):
            _fail(blocker, "every gate purpose needs an explicit positive maximum age")
        for name in ("status_maximum_age_seconds", "maximum_receipt_bytes", "store_deadline_seconds"):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= 16 * 1024 * 1024:
                _fail(blocker, f"{name} must be a bounded positive integer")
        object.__setattr__(self, "issuers", issuers)
        object.__setattr__(self, "uri_prefixes", prefixes)
        object.__setattr__(self, "promotion_public_key_digests", promotion)
        object.__setattr__(self, "gate_maximum_age_seconds", MappingProxyType(ages))

    def document(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "kind": "hive-production-evidence-policy",
            "generation": self.generation,
            "issuers": [
                item.document() for item in sorted(self.issuers, key=lambda i: i.principal_id)
            ],
            "uri_prefixes": sorted(self.uri_prefixes),
            "gate_maximum_age_seconds": {
                purpose.value: age for purpose, age in self.gate_maximum_age_seconds.items()
            },
            "status_maximum_age_seconds": self.status_maximum_age_seconds,
            "promotion_public_key_digests": sorted(self.promotion_public_key_digests),
            "maximum_receipt_bytes": self.maximum_receipt_bytes,
            "store_deadline_seconds": self.store_deadline_seconds,
        }

    @property
    def policy_digest(self) -> str:
        return _digest_of(self.document())

    def issuer(self, principal_id: str) -> TrustedIssuer | None:
        return next((i for i in self.issuers if i.principal_id == principal_id), None)

    def issuer_with_role(self, principal_id: str, role: IssuerRole) -> TrustedIssuer:
        found = self.issuer(principal_id)
        if found is None:
            _fail(EvidenceBlocker.ISSUER_UNKNOWN, f"{role.value} is not a configured principal")
        if found.role is not role:
            _fail(EvidenceBlocker.SEPARATION, f"principal is not configured as a {role.value}")
        return found

    def require_separation(self, builder_id: str, judge_id: str) -> tuple[TrustedIssuer, TrustedIssuer]:
        """Names alone are insufficient: both must be bound principals that differ in
        principal, administration and key. Real-world independence stays external."""
        builder = self.issuer_with_role(builder_id, IssuerRole.BUILDER)
        judge = self.issuer_with_role(judge_id, IssuerRole.JUDGE)
        if (
            builder.principal_id == judge.principal_id
            or builder.administration_id == judge.administration_id
            or builder.public_key_digest == judge.public_key_digest
        ):
            _fail(EvidenceBlocker.SEPARATION, "builder and judge are not separated")
        return builder, judge


# --- injected ports ---------------------------------------------------------------------


class StatusState(StrEnum):
    ACTIVE = "active"
    RETIRED = "retired"
    ROTATED = "rotated"
    REVOKED = "revoked"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CurrentEvidenceStatus:
    """Fresh external state for exactly one use/issuer/key/receipt. Only ACTIVE passes in
    this first slice; RETIRED/ROTATED/UNKNOWN block until an archival policy exists."""

    use_digest: str
    issuer_id: str
    key_id: str
    receipt_digest: str
    policy_generation: str
    observed_at: int
    issuer_state: StatusState
    key_state: StatusState
    receipt_state: StatusState
    lease_digest: str | None = None


class ReceiptStore(Protocol):
    def read(self, uri: str, max_bytes: int, deadline_seconds: int) -> bytes:
        """Return the stored object's bytes, reading at most ``max_bytes + 1``.

        Only allowlisted schemes/namespaces, no redirects, bytes only. Raise on any
        unavailability. The resolver rejects anything longer than ``max_bytes``."""
        ...


class CurrentEvidenceAuthority(Protocol):
    def resolve(
        self,
        use: EvidenceUse,
        issuer_id: str,
        key_id: str,
        receipt_digest: str,
        now: int,
    ) -> CurrentEvidenceStatus:
        """Fresh state for this exact tuple; required on every invocation."""
        ...


class HostLeaseDocument(Protocol):
    def to_document(self) -> Mapping[str, Any]: ...


class HostLeasePort(Protocol):
    def current_lease(
        self, *, candidate_digest: str, subject_id: str, attempt_id: str
    ) -> HostLeaseDocument | None:
        """The actual host lease for this attempt, or None when no mapping exists. How
        a pilot candidate maps to lease ``candidate_*`` fields is the host's binding."""
        ...


class DeterministicReceiptStore:
    """Conformance adapter: exact-key lookup in an in-memory table under one namespace.

    It demonstrates the ``ReceiptStore`` contract for tests and rehearsals. It is not a
    custody backend and makes no claim about durability or access control."""

    _SCHEMES = frozenset({"receipt"})

    def __init__(self, namespace: str, objects: Mapping[str, bytes]) -> None:
        scheme = namespace.partition(":")[0]
        if scheme not in self._SCHEMES or not namespace.endswith("/"):
            raise ValueError("conformance namespace must be a receipt: scheme prefix")
        self.namespace = namespace
        self._objects = dict(objects)
        self.reads: list[str] = []

    def put(self, uri: str, data: bytes) -> None:
        if not uri.startswith(self.namespace) or type(data) is not bytes:
            raise ValueError("conformance objects must be bytes inside the namespace")
        self._objects[uri] = data

    def read(self, uri: str, max_bytes: int, deadline_seconds: int) -> bytes:
        self.reads.append(uri)
        if not uri.startswith(self.namespace):
            raise LookupError("uri is outside the allowlisted namespace")
        try:
            return self._objects[uri][: max_bytes + 1]
        except KeyError as error:
            raise LookupError("receipt does not exist") from error


# --- strict parsing ---------------------------------------------------------------------


def _reject_pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate object key")
        result[key] = value
    return result


def _reject_constant(name: str) -> NoReturn:
    raise ValueError(f"non-finite constant {name} is not allowed")


def _reject_float(text: str) -> NoReturn:
    raise ValueError("floating point numbers are not part of the evidence schema")


def _within_depth(text: str) -> bool:
    depth = 0
    in_string = escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > _MAX_DEPTH:
                return False
        elif character in "]}":
            depth -= 1
    return True


def _within_records(value: object) -> bool:
    stack = [value]
    count = 0
    while stack:
        current = stack.pop()
        count += 1
        if count > _MAX_NODES:
            return False
        if isinstance(current, dict):
            stack.extend(current.keys())
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return True


def _parse_document(raw: bytes) -> dict[str, object]:
    malformed = EvidenceBlocker.RECEIPT_MALFORMED
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ProductionEvidenceError(malformed, "receipt is not UTF-8") from error
    if not _within_depth(text):
        _fail(malformed, "receipt nesting exceeds the bound")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_pairs,
            parse_constant=_reject_constant,
            parse_float=_reject_float,
        )
    except (ValueError, RecursionError) as error:
        raise ProductionEvidenceError(malformed, f"strict JSON parse failed: {error}") from error
    if not isinstance(value, dict) or not _within_records(value):
        _fail(malformed, "receipt must be one bounded JSON object")
    return value


def _decode_signature(value: object) -> bytes:
    if type(value) is not str or len(value) != 88:
        _fail(EvidenceBlocker.RECEIPT_MALFORMED, "signature must be canonical base64")
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ProductionEvidenceError(
            EvidenceBlocker.RECEIPT_MALFORMED, "signature is not base64"
        ) from error
    if len(raw) != 64 or base64.b64encode(raw).decode("ascii") != value:
        _fail(EvidenceBlocker.RECEIPT_MALFORMED, "signature must be a canonical Ed25519 value")
    return raw


# --- resolver ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvidenceResolution:
    """An audit observation of one invocation. Not a token: nothing accepts it in place
    of resolving again."""

    purpose: EvidencePurpose
    use_digest: str
    receipt_digest: str
    issuer_id: str
    administration_id: str
    key_id: str
    public_key_digest: str
    observed_at: int
    issued_at: int
    verified_at: int
    policy_generation: str
    policy_digest: str

    def document(self) -> dict[str, object]:
        return {
            "purpose": self.purpose.value,
            "use_digest": self.use_digest,
            "receipt_digest": self.receipt_digest,
            "issuer_id": self.issuer_id,
            "administration_id": self.administration_id,
            "key_id": self.key_id,
            "public_key_digest": self.public_key_digest,
            "observed_at": self.observed_at,
            "issued_at": self.issued_at,
            "verified_at": self.verified_at,
            "policy_generation": self.policy_generation,
            "policy_digest": self.policy_digest,
        }

    def digest(self) -> str:
        return _digest_of(self.document())


_COMMON_FIELDS = frozenset(
    {
        "kind",
        "schema_version",
        "algorithm",
        "purpose",
        "issuer_id",
        "key_id",
        "subject_id",
        "operation_id",
        "candidate_digest",
        "observed_at",
        "issued_at",
        "claims",
        "signature",
    }
)


class PinnedEvidenceResolver:
    """Resolve one reference against one exact use. Any missing dependency is a typed
    blocker; there is no permissive default and no cross-call cache."""

    def __init__(
        self,
        policy: EvidenceTrustPolicy | None,
        store: ReceiptStore | None,
        authority: CurrentEvidenceAuthority | None,
        *,
        signature_verifier: SignatureVerifier | None = None,
    ) -> None:
        self._policy = policy
        self._store = store
        self._authority = authority
        self._bindings: dict[str, PrincipalBinding] = {}
        self._verifier: SignatureVerifier | None = None
        if policy is not None:
            try:
                for issuer in policy.issuers:
                    self._bindings[issuer.principal_id] = PrincipalBinding(
                        issuer.principal_id,
                        "receipt",
                        issuer.administration_id,
                        issuer.key_id,
                        issuer.public_key_digest,
                    )
                # A separate instance holding only evidence pins.
                self._verifier = signature_verifier or Ed25519SignatureVerifier(
                    {issuer.key_id: issuer.public_key for issuer in policy.issuers}
                )
            except PromotionAuthenticationError as error:
                raise ProductionEvidenceError(
                    EvidenceBlocker.POLICY_INVALID, "evidence pins were rejected by the adapter"
                ) from error

    @property
    def policy(self) -> EvidenceTrustPolicy | None:
        return self._policy

    def _ready(self) -> tuple[EvidenceTrustPolicy, ReceiptStore, CurrentEvidenceAuthority]:
        if self._policy is None:
            _fail(EvidenceBlocker.TRUST_STORE_MISSING, "no evidence trust policy is configured")
        if self._store is None:
            _fail(EvidenceBlocker.RECEIPT_STORE_MISSING, "no receipt store is configured")
        if self._authority is None:
            _fail(
                EvidenceBlocker.CURRENT_AUTHORITY_MISSING,
                "no current-evidence authority is configured",
            )
        return self._policy, self._store, self._authority

    def require(self, ref: EvidenceRef, use: EvidenceUse, now: int) -> EvidenceResolution:
        policy, store, authority = self._ready()
        _now(now)
        if type(ref) is not EvidenceRef or ref.kind is EvidenceKind.SYNTHETIC:
            _fail(EvidenceBlocker.USE_INVALID, "a non-synthetic evidence reference is required")
        if type(use) is not EvidenceUse:
            _fail(EvidenceBlocker.USE_INVALID, "an exact evidence use is required")
        schema = use.schema
        if ref.subject_id != use.subject_id:
            _fail(EvidenceBlocker.CONTEXT_MISMATCH, "reference subject is not the expected subject")
        if not any(ref.uri.startswith(prefix) for prefix in policy.uri_prefixes):
            _fail(EvidenceBlocker.URI_NOT_ALLOWED, "receipt URI is outside the allowlist")

        raw = self._fetch(store, policy, ref.uri)
        receipt_digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        if receipt_digest != ref.digest:
            _fail(EvidenceBlocker.DIGEST_MISMATCH, "retrieved bytes do not match the reference")
        document = _parse_document(raw)
        receipt = self._shape(document, use)
        issuer = self._issuer(policy, receipt, schema)
        observed_at: int = receipt["observed_at"]
        issued_at: int = receipt["issued_at"]
        self._times(policy, use, ref, observed_at, issued_at, _now(now))

        payload = {key: value for key, value in document.items() if key != "signature"}
        self._verify(policy, issuer, payload, _decode_signature(document["signature"]))
        status = self._status(authority, policy, use, issuer, receipt_digest, issued_at, now)
        return EvidenceResolution(
            use.purpose,
            use.digest(),
            receipt_digest,
            issuer.principal_id,
            issuer.administration_id,
            issuer.key_id,
            issuer.public_key_digest,
            observed_at,
            issued_at,
            now,
            status.policy_generation,
            policy.policy_digest,
        )

    def require_all(
        self, entries: Iterable[tuple[EvidenceRef, EvidenceUse]], now: int
    ) -> tuple[EvidenceResolution, ...]:
        """Resolve every entry afresh. The same bytes cannot be counted twice and one
        issuer cannot be counted as several witnesses for one use; distinct authorized
        witnesses for one use remain legal."""
        self._ready()
        receipts: set[str] = set()
        witnesses: set[tuple[str, str]] = set()
        resolved: list[EvidenceResolution] = []
        for ref, use in entries:
            resolution = self.require(ref, use, now)
            witness = (resolution.use_digest, resolution.issuer_id)
            if resolution.receipt_digest in receipts or witness in witnesses:
                _fail(EvidenceBlocker.DUPLICATE_EVIDENCE, "evidence would be counted twice")
            receipts.add(resolution.receipt_digest)
            witnesses.add(witness)
            resolved.append(resolution)
        return tuple(resolved)

    @staticmethod
    def _fetch(store: ReceiptStore, policy: EvidenceTrustPolicy, uri: str) -> bytes:
        try:
            raw = store.read(uri, policy.maximum_receipt_bytes, policy.store_deadline_seconds)
        except ProductionEvidenceError:
            raise
        except Exception as error:
            raise ProductionEvidenceError(
                EvidenceBlocker.STORE_UNAVAILABLE, "receipt could not be retrieved"
            ) from error
        if type(raw) is not bytes:
            _fail(EvidenceBlocker.STORE_UNAVAILABLE, "receipt store returned non-bytes")
        if len(raw) > policy.maximum_receipt_bytes:
            _fail(EvidenceBlocker.RECEIPT_OVERSIZE, "receipt exceeds the byte bound")
        return raw

    @staticmethod
    def _shape(document: dict[str, object], use: EvidenceUse) -> dict[str, Any]:
        malformed = EvidenceBlocker.RECEIPT_MALFORMED
        schema = use.schema
        purpose = document.get("purpose")
        try:
            declared = EvidencePurpose(purpose) if type(purpose) is str else None
        except ValueError:
            declared = None
        if declared is None:
            _fail(malformed, "receipt purpose is not in the closed schema table")
        if declared is not use.purpose:
            _fail(EvidenceBlocker.CONTEXT_MISMATCH, "receipt was issued for another purpose")
        fields = set(_COMMON_FIELDS)
        if schema.binds_authority:
            fields.add("authority_digest")
        if set(document) != fields:
            _fail(malformed, "receipt fields do not match the closed schema")
        if document["kind"] != EVIDENCE_KIND or document["algorithm"] != EVIDENCE_ALGORITHM:
            _fail(malformed, "unsupported evidence kind or algorithm")
        version = document["schema_version"]
        if type(version) is not int or version != EVIDENCE_SCHEMA_VERSION:
            _fail(malformed, "unsupported evidence schema version")
        for name in ("issuer_id", "key_id", "subject_id", "operation_id"):
            _ident(document[name], name, malformed)
        _sha(document["candidate_digest"], "candidate digest", malformed)
        if schema.binds_authority:
            _sha(document["authority_digest"], "authority digest", malformed)
        _int(document["observed_at"], "observed_at", malformed)
        _int(document["issued_at"], "issued_at", malformed)
        claims = _normalize_claims(schema, document["claims"], malformed)
        expected: dict[str, object] = {
            "subject_id": use.subject_id,
            "operation_id": use.operation_id,
            "candidate_digest": use.candidate_digest,
        }
        if schema.binds_authority:
            expected["authority_digest"] = use.authority_digest
        for name, value in expected.items():
            if document[name] != value:
                _fail(EvidenceBlocker.CONTEXT_MISMATCH, f"receipt {name} is not the expected value")
        if claims != dict(use.claims):
            _fail(EvidenceBlocker.CONTEXT_MISMATCH, "receipt claims are not the expected claims")
        return dict(document)

    @staticmethod
    def _issuer(
        policy: EvidenceTrustPolicy, receipt: Mapping[str, Any], schema: PurposeSchema
    ) -> TrustedIssuer:
        issuer = policy.issuer(receipt["issuer_id"])
        if issuer is None or receipt["key_id"] != issuer.key_id:
            _fail(EvidenceBlocker.ISSUER_UNKNOWN, "issuer or key is not a configured pin")
        if schema.purpose not in issuer.remit or issuer.role not in schema.roles:
            _fail(EvidenceBlocker.ISSUER_REMIT, "issuer is not configured for this purpose")
        return issuer

    @staticmethod
    def _times(
        policy: EvidenceTrustPolicy,
        use: EvidenceUse,
        ref: EvidenceRef,
        observed_at: int,
        issued_at: int,
        now: int,
    ) -> None:
        window = EvidenceBlocker.TIME_WINDOW
        if ref.observed_at != observed_at:
            _fail(EvidenceBlocker.CONTEXT_MISMATCH, "reference and receipt observation differ")
        # observed_at <= receipt signing <= verification time
        if observed_at > issued_at or issued_at > now:
            _fail(window, "observation, signing and verification times are out of order")
        rule, start, end = use.schema.window, use.window_start, use.window_end
        if rule in {WindowRule.ATTEMPT, WindowRule.PILOT}:
            inside = start is not None and end is not None and start <= observed_at <= end
        elif rule in {WindowRule.PRE_PILOT, WindowRule.THROUGH_PILOT_END}:
            inside = end is not None and observed_at <= end
        elif rule is WindowRule.POST_SEAL:
            inside = start is not None and start <= observed_at and start <= now
        else:
            inside = True
        if not inside:
            _fail(window, "observation is outside the window this purpose allows")
        if use.schema.mode is UseMode.GATE:
            limit = policy.gate_maximum_age_seconds[use.purpose]
            if now - issued_at > limit:
                _fail(EvidenceBlocker.EVIDENCE_STALE, "gate evidence exceeds its maximum age")

    def _verify(
        self,
        policy: EvidenceTrustPolicy,
        issuer: TrustedIssuer,
        payload: Mapping[str, object],
        signature: bytes,
    ) -> None:
        verifier = self._verifier
        binding = self._bindings.get(issuer.principal_id)
        if verifier is None or binding is None:
            _fail(EvidenceBlocker.TRUST_STORE_MISSING, "no signature verifier is configured")
        try:
            accepted = verifier.verify(binding, evidence_preimage(payload), signature)
        except ProductionEvidenceError:
            raise
        except Exception as error:
            raise ProductionEvidenceError(
                EvidenceBlocker.CRYPTO_UNAVAILABLE, "the signature provider failed"
            ) from error
        if accepted is not True:
            _fail(EvidenceBlocker.SIGNATURE_INVALID, "signature does not match the pinned key")

    @staticmethod
    def _status(
        authority: CurrentEvidenceAuthority,
        policy: EvidenceTrustPolicy,
        use: EvidenceUse,
        issuer: TrustedIssuer,
        receipt_digest: str,
        issued_at: int,
        now: int,
    ) -> CurrentEvidenceStatus:
        use_digest = use.digest()
        try:
            status = authority.resolve(use, issuer.principal_id, issuer.key_id, receipt_digest, now)
        except ProductionEvidenceError:
            raise
        except Exception as error:
            raise ProductionEvidenceError(
                EvidenceBlocker.STATUS_UNAVAILABLE, "current status could not be obtained"
            ) from error
        if type(status) is not CurrentEvidenceStatus:
            _fail(EvidenceBlocker.STATUS_UNAVAILABLE, "current status has the wrong type")
        mismatch = EvidenceBlocker.STATUS_MISMATCH
        if (
            status.use_digest != use_digest
            or status.issuer_id != issuer.principal_id
            or status.key_id != issuer.key_id
            or status.receipt_digest != receipt_digest
            or status.policy_generation != policy.generation
            or status.lease_digest != use.lease_digest
        ):
            _fail(mismatch, "current status is not bound to this exact use")
        if type(status.observed_at) is not int or status.observed_at > now:
            _fail(mismatch, "current status was observed in the future")
        if status.observed_at < issued_at or now - status.observed_at > policy.status_maximum_age_seconds:
            _fail(EvidenceBlocker.STATUS_STALE, "current status is stale")
        states = (status.issuer_state, status.key_state, status.receipt_state)
        if StatusState.REVOKED in states:
            _fail(EvidenceBlocker.EVIDENCE_REVOKED, "issuer, key or receipt is revoked")
        if any(state is not StatusState.ACTIVE for state in states):
            _fail(
                EvidenceBlocker.STATUS_NOT_ACTIVE,
                "only ACTIVE issuer, key and receipt are accepted until an archival policy exists",
            )
        return status


# --- composition -------------------------------------------------------------------------

_LEDGER_LOCKS: dict[str, threading.Lock] = {}
_LEDGER_LOCKS_GUARD = threading.Lock()


def _ledger_lock(ledger: QualificationLedger) -> threading.Lock:
    key = os.path.abspath(ledger.path)
    with _LEDGER_LOCKS_GUARD:
        return _LEDGER_LOCKS.setdefault(key, threading.Lock())


@dataclass(frozen=True, slots=True)
class ProductionEvidenceContext:
    """Fixed at host construction. Never selected by a request or read from a document.

    ``ledger`` receives local audit entries only; they are not externally signed
    evidence. The in-process lock serializes this module's appends to one ledger path and
    does not make the ledger safe against other processes."""

    resolver: PinnedEvidenceResolver
    clock: Callable[[], int]
    ledger: QualificationLedger
    lease_port: HostLeasePort | None = None

    def __post_init__(self) -> None:
        if (
            type(self.resolver) is not PinnedEvidenceResolver
            or not callable(self.clock)
            or type(self.ledger) is not QualificationLedger
        ):
            _fail(EvidenceBlocker.POLICY_INVALID, "production context needs a resolver, clock and ledger")

    def now(self) -> int:
        try:
            value = self.clock()
        except Exception as error:
            raise ProductionEvidenceError(
                EvidenceBlocker.CLOCK_INVALID, "the trusted clock failed"
            ) from error
        return _now(value)

    def context_digest(self) -> str:
        policy = self.resolver.policy
        return _digest_of(
            {
                "mode": MODE_PRODUCTION,
                "policy_digest": None if policy is None else policy.policy_digest,
                "lease_port": self.lease_port is not None,
            }
        )

    def lease_digest(self, *, candidate_digest: str, subject_id: str, attempt_id: str) -> str:
        """Digest of the actual host lease for this attempt, over the lease's own
        document with ``runtime_contracts.canonical_digest``. Missing mapping blocks."""
        port = self.lease_port
        if port is None:
            _fail(EvidenceBlocker.LEASE_MAPPING_MISSING, "no host lease mapping is configured")
        try:
            lease = port.current_lease(
                candidate_digest=candidate_digest, subject_id=subject_id, attempt_id=attempt_id
            )
            if lease is None:
                raise LookupError("no lease is mapped to this candidate and attempt")
            return lease_canonical_digest(lease.to_document())
        except Exception as error:
            raise ProductionEvidenceError(
                EvidenceBlocker.LEASE_MAPPING_MISSING,
                "no current host lease is mapped to this candidate and attempt",
            ) from error

    def verify(
        self,
        scope: str,
        entries: Sequence[tuple[EvidenceRef, EvidenceUse]],
        *,
        now: int | None = None,
        after: Callable[[tuple[EvidenceResolution, ...]], None] | None = None,
    ) -> tuple[EvidenceResolution, ...]:
        """Resolve every entry afresh, then run ``after``, then append a local audit
        record. Failure or an unwritable audit record yields no positive result."""
        rows = tuple(entries)
        uses = tuple(use.digest() for _, use in rows)
        try:
            moment = self.now() if now is None else _now(now)
            resolutions = self.resolver.require_all(rows, moment)
            if after is not None:
                after(resolutions)
        except ProductionEvidenceError as error:
            self._audit(scope, uses, (), error)
            raise
        self._audit(scope, uses, resolutions, None)
        return resolutions

    def record_failure(self, scope: str, error: ProductionEvidenceError) -> None:
        """Audit a failure detected before any resolution began."""
        self._audit(scope, (), (), error)

    def _audit(
        self,
        scope: str,
        uses: tuple[str, ...],
        resolutions: tuple[EvidenceResolution, ...],
        failure: ProductionEvidenceError | None,
    ) -> None:
        payload = {
            "schema_version": 1,
            "scope": scope,
            "outcome": "success" if failure is None else "failure",
            "blocker": None if failure is None else failure.blocker.value,
            "context_digest": self.context_digest(),
            "use_digests": list(uses),
            "resolution_digests": [item.digest() for item in resolutions],
            "note": "local audit record; not externally signed evidence",
        }
        try:
            with _ledger_lock(self.ledger):
                self.ledger.append(
                    "production-evidence-success" if failure is None else "production-evidence-failure",
                    payload,
                )
        except Exception as error:
            raise ProductionEvidenceError(
                EvidenceBlocker.AUDIT_UNAVAILABLE,
                "the local audit record could not be written"
                + ("" if failure is None else f" while recording {failure.blocker.value}"),
            ) from error
