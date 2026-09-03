"""Fail-closed, externally authenticated one-run DAG activation.

The repository may describe and validate an activation, but it never owns the
signing keys or the durable replay ledger. Callers verify two independent
attestations, verify the issuer signature, and atomically consume the nonce in
that order before handing the returned capability to a runner. Internal seals
reject public-constructor and mutation bypasses, but are process-local integrity
guards, not cryptographic isolation from hostile code in the same interpreter.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import secrets
from base64 import b64encode
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol, cast


class ActivationBundleError(ValueError):
    """An activation artifact fails a mandatory binding or ordering check."""


_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_GIT_ID = re.compile(r"[0-9a-f]{40}\Z")
_BRANCH = re.compile(r"codex/[A-Za-z0-9._/-]{1,160}\Z")
_MAX_BUNDLE_BYTES = 262_144
_MAX_EVIDENCE_BYTES = 1_048_576
_MAX_DEPTH = 20
_MAX_LEASE = timedelta(minutes=15)
_CAPABILITY_KEY = secrets.token_bytes(32)
CAPABILITY_SECURITY_BOUNDARY = "trusted-process-integrity-only"

_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "plan_id",
        "status",
        "predecessor",
        "candidate_base",
        "request_text",
        "request_sha256",
        "repository_id",
        "source_intake",
        "target_branch",
        "plan",
        "activation_policy",
        "execution_authorized",
    }
)
_SOURCE_INTAKE_FIELDS = frozenset(
    {
        "path",
        "sha256",
        "archive_path",
        "archive_sha256",
        "source_count",
        "unavailable_source_count",
    }
)
_PREDECESSOR_FIELDS = frozenset(
    {
        "plan_id",
        "commit",
        "tree",
        "qualification_receipt_path",
        "qualification_receipt_sha256",
    }
)
_CANDIDATE_BASE_FIELDS = frozenset({"commit", "tree"})
_PLAN_FIELDS = frozenset({"path", "sha256", "mode", "node_count"})
_POLICY_FIELDS = frozenset(
    {
        "maximum_lease_seconds",
        "nonce_uniqueness",
        "signature_order",
        "required_principals",
        "protected_merge_authorized",
    }
)
_PRINCIPAL_FIELDS = frozenset({"principal_id", "authority_domain", "key_id"})
_BUNDLE_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "plan_id",
        "request_sha256",
        "repository_id",
        "target_branch",
        "predecessor_commit",
        "predecessor_tree",
        "candidate_parent_commit",
        "candidate_parent_tree",
        "candidate_branch",
        "candidate_commit",
        "candidate_tree",
        "candidate_content_sha256",
        "plan_sha256",
        "manifest_sha256",
        "frozen_host_evidence_sha256",
        "review_evidence_sha256",
        "builder",
        "independent_reviewer",
        "actor",
        "issuer",
        "host_attester",
        "nonce",
        "issued_at",
        "expires_at",
        "signature",
    }
)
_REVIEW_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "candidate_commit",
        "candidate_tree",
        "candidate_content_sha256",
        "plan_sha256",
        "manifest_sha256",
        "reviewer",
        "verdict",
        "test_evidence_sha256",
        "reviewed_at",
        "signature",
    }
)
_HOST_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "candidate_commit",
        "candidate_tree",
        "candidate_parent_commit",
        "candidate_parent_tree",
        "candidate_content_sha256",
        "plan_sha256",
        "manifest_sha256",
        "attester",
        "host_bundle_sha256",
        "interpreter_sha256",
        "git_executable_sha256",
        "execution_client_sha256",
        "worktree_clean",
        "bytecode_free",
        "read_only_custody",
        "observed_at",
        "expires_at",
        "signature",
    }
)
_RESERVATION_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "nonce",
        "activation_digest",
        "candidate_commit",
        "candidate_tree",
        "candidate_content_sha256",
        "plan_sha256",
        "issued_at",
        "expires_at",
        "consumed_at",
        "ledger",
        "signature",
    }
)


@dataclass(frozen=True, slots=True)
class Principal:
    principal_id: str
    authority_domain: str
    key_id: str

    def as_dict(self) -> dict[str, str]:
        return {
            "principal_id": self.principal_id,
            "authority_domain": self.authority_domain,
            "key_id": self.key_id,
        }


class ActivationPayload:
    """Parser-issued, immutable activation bytes not yet trusted by verifiers.

    The constructor is deliberately unavailable.  Otherwise a caller could pair
    genuine signed bytes with substituted scalar claims and skip the strict
    bundle parser.
    """

    __slots__ = (
        "_seal",
        "nonce",
        "activation_digest",
        "candidate_commit",
        "candidate_tree",
        "candidate_content_sha256",
        "candidate_parent_commit",
        "candidate_parent_tree",
        "plan_sha256",
        "manifest_sha256",
        "repository_id",
        "request_sha256",
        "target_branch",
        "execution_client_sha256",
        "issued_at",
        "protected_merge_authorized",
        "expires_at",
        "builder",
        "reviewer",
        "actor",
        "issuer",
        "host_attester",
        "issuer_signature",
        "issuer_signed_bytes",
        "review_signature",
        "review_signed_bytes",
        "host_signature",
        "host_signed_bytes",
    )

    def __new__(cls, *_args: object, **_kwargs: object) -> ActivationPayload:
        raise ActivationBundleError(
            "activation payloads can only be issued by strict bundle preparation"
        )

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("activation payloads are immutable")

    def __reduce__(self) -> object:
        raise TypeError("activation payloads are process-local and cannot be pickled")

    def __repr__(self) -> str:
        return "<ActivationPayload sealed>"

    def proof_document(self) -> dict[str, object]:
        """Return the exact public proof carried to the host boundary."""

        _require_payload(self)
        return _payload_proof_document(self)


class _SealedActivationStage:
    __slots__ = ("_payload", "_reservation_receipt", "_seal")
    _stage_name = "activation-stage"

    def __new__(cls, *_args: object, **_kwargs: object) -> _SealedActivationStage:
        raise ActivationBundleError(
            f"{cls.__name__} can only be issued by the ordered verification pipeline"
        )

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("activation verification stages are immutable")

    def __reduce__(self) -> object:
        raise TypeError("activation verification stages cannot be pickled")

    @property
    def payload(self) -> ActivationPayload:
        return _require_stage(self, type(self), self._stage_name)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} sealed>"


class AttestedActivation(_SealedActivationStage):
    """Activation whose review and frozen-host attestations passed."""

    __slots__ = ()
    _stage_name = "attested"


class VerifiedActivation(_SealedActivationStage):
    """Activation whose attestations and issuer signature passed."""

    __slots__ = ()
    _stage_name = "verified"


class AuthorizedOneRun(_SealedActivationStage):
    """Opaque single-use capability issued only after host-ledger CAS."""

    __slots__ = ()
    _stage_name = "authorized-one-run"

    @property
    def activation_digest(self) -> str:
        return self.payload.activation_digest

    @property
    def nonce(self) -> str:
        return self.payload.nonce

    @property
    def candidate_commit(self) -> str:
        return self.payload.candidate_commit

    @property
    def candidate_tree(self) -> str:
        return self.payload.candidate_tree

    @property
    def candidate_content_sha256(self) -> str:
        return self.payload.candidate_content_sha256

    @property
    def candidate_parent_commit(self) -> str:
        return self.payload.candidate_parent_commit

    @property
    def candidate_parent_tree(self) -> str:
        return self.payload.candidate_parent_tree

    @property
    def plan_sha256(self) -> str:
        return self.payload.plan_sha256

    @property
    def manifest_sha256(self) -> str:
        return self.payload.manifest_sha256

    @property
    def repository_id(self) -> str:
        return self.payload.repository_id

    @property
    def request_sha256(self) -> str:
        return self.payload.request_sha256

    @property
    def target_branch(self) -> str:
        return self.payload.target_branch

    @property
    def execution_client_sha256(self) -> str:
        return self.payload.execution_client_sha256

    @property
    def issued_at(self) -> datetime:
        return self.payload.issued_at

    @property
    def protected_merge_authorized(self) -> bool:
        return self.payload.protected_merge_authorized

    @property
    def expires_at(self) -> datetime:
        return self.payload.expires_at

    @property
    def proof_digest(self) -> str:
        return _raw_sha256(_canonical_bytes(self.proof_document()))

    @property
    def reservation_receipt(self) -> bytes:
        validate_authorized_one_run(self)
        return self._reservation_receipt

    def proof_document(self) -> dict[str, object]:
        validate_authorized_one_run(self)
        return _authorization_proof_document(
            self.payload, self._reservation_receipt
        )


class NonceLedger(Protocol):
    """Host-owned storage with ``nonce`` as the unique compare-and-swap key."""

    def consume_once(
        self,
        *,
        nonce: str,
        activation_digest: str,
        candidate_commit: str,
        candidate_tree: str,
        candidate_content_sha256: str,
        plan_sha256: str,
        issued_at: datetime,
        expires_at: datetime,
    ) -> bytes | None: ...


SignatureVerifier = Callable[[Principal, bytes, str], bool]


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ActivationBundleError(
            "artifact is not canonical-JSON compatible"
        ) from error


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ActivationBundleError("activation expiry must include a timezone")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _payload_proof_document(payload: ActivationPayload) -> dict[str, object]:
    """Serialize security-relevant claims without consulting their seal."""

    return {
        "schema_version": 1,
        "kind": "hive-mind-signed-activation-proof-v1",
        "nonce": payload.nonce,
        "activation_digest": payload.activation_digest,
        "candidate_commit": payload.candidate_commit,
        "candidate_tree": payload.candidate_tree,
        "candidate_content_sha256": payload.candidate_content_sha256,
        "candidate_parent_commit": payload.candidate_parent_commit,
        "candidate_parent_tree": payload.candidate_parent_tree,
        "plan_sha256": payload.plan_sha256,
        "manifest_sha256": payload.manifest_sha256,
        "repository_id": payload.repository_id,
        "request_sha256": payload.request_sha256,
        "target_branch": payload.target_branch,
        "execution_client_sha256": payload.execution_client_sha256,
        "issued_at": _utc_text(payload.issued_at),
        "protected_merge_authorized": payload.protected_merge_authorized,
        "expires_at": _utc_text(payload.expires_at),
        "principals": {
            "builder": payload.builder.as_dict(),
            "independent_reviewer": payload.reviewer.as_dict(),
            "actor": payload.actor.as_dict(),
            "issuer": payload.issuer.as_dict(),
            "host_attester": payload.host_attester.as_dict(),
        },
        "signed_proof": {
            "independent_review": {
                "signed_bytes_base64": b64encode(payload.review_signed_bytes).decode(
                    "ascii"
                ),
                "signature": payload.review_signature,
            },
            "frozen_host": {
                "signed_bytes_base64": b64encode(payload.host_signed_bytes).decode(
                    "ascii"
                ),
                "signature": payload.host_signature,
            },
            "issuer": {
                "signed_bytes_base64": b64encode(payload.issuer_signed_bytes).decode(
                    "ascii"
                ),
                "signature": payload.issuer_signature,
            },
        },
    }


def _authorization_proof_document(
    payload: ActivationPayload, reservation_receipt: bytes
) -> dict[str, object]:
    document = _payload_proof_document(payload)
    document["kind"] = "hive-mind-authorized-one-run-proof-v1"
    document["nonce_reservation_receipt_base64"] = b64encode(
        reservation_receipt
    ).decode("ascii")
    return document


def _capability_seal(
    stage: str,
    payload: ActivationPayload,
    reservation_receipt: bytes | None = None,
) -> str:
    material = _canonical_bytes(
        {
            "stage": stage,
            "proof": _payload_proof_document(payload),
            "reservation_receipt_sha256": (
                None
                if reservation_receipt is None
                else _raw_sha256(reservation_receipt)
            ),
        }
    )
    return hmac.new(_CAPABILITY_KEY, material, hashlib.sha256).hexdigest()


def _issue_payload(**claims: object) -> ActivationPayload:
    payload = object.__new__(ActivationPayload)
    for name in ActivationPayload.__slots__:
        if name != "_seal":
            object.__setattr__(payload, name, claims[name])
    object.__setattr__(payload, "_seal", _capability_seal("prepared", payload))
    return payload


def _require_payload(value: object) -> ActivationPayload:
    if type(value) is not ActivationPayload:
        raise ActivationBundleError(
            "an activation must come from strict bundle preparation"
        )
    try:
        seal = value._seal
        expected = _capability_seal("prepared", value)
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise ActivationBundleError("activation payload seal is missing") from error
    if type(seal) is not str or not hmac.compare_digest(seal, expected):
        raise ActivationBundleError("activation payload seal is invalid")
    return value


def _issue_stage(
    stage_type: type[_SealedActivationStage],
    stage_name: str,
    payload: ActivationPayload,
    *,
    reservation_receipt: bytes | None = None,
) -> _SealedActivationStage:
    _require_payload(payload)
    if stage_type is AuthorizedOneRun:
        if type(reservation_receipt) is not bytes:
            raise ActivationBundleError(
                "authorized one-run capability requires a nonce reservation receipt"
            )
    elif reservation_receipt is not None:
        raise ActivationBundleError(
            "nonce reservation receipt is only valid after issuer verification"
        )
    stage = object.__new__(stage_type)
    object.__setattr__(stage, "_payload", payload)
    object.__setattr__(stage, "_reservation_receipt", reservation_receipt)
    object.__setattr__(
        stage,
        "_seal",
        _capability_seal(stage_name, payload, reservation_receipt),
    )
    return stage


def _require_stage(
    value: object,
    expected_type: type[_SealedActivationStage],
    stage_name: str,
) -> ActivationPayload:
    if type(value) is not expected_type:
        raise ActivationBundleError(
            f"{expected_type.__name__} must be issued by its required prior stages"
        )
    try:
        payload = value._payload
        reservation_receipt = value._reservation_receipt
        seal = value._seal
        _require_payload(payload)
        if expected_type is AuthorizedOneRun:
            if type(reservation_receipt) is not bytes:
                raise ActivationBundleError(
                    "authorized capability lacks a nonce reservation receipt"
                )
        elif reservation_receipt is not None:
            raise ActivationBundleError(
                "pre-authorization stage carries a nonce reservation receipt"
            )
        expected = _capability_seal(stage_name, payload, reservation_receipt)
    except (AttributeError, TypeError, ValueError) as error:
        raise ActivationBundleError(
            f"{expected_type.__name__} capability seal is missing"
        ) from error
    if type(seal) is not str or not hmac.compare_digest(seal, expected):
        raise ActivationBundleError(
            f"{expected_type.__name__} capability seal is invalid"
        )
    return payload


def validate_authorized_one_run(value: object) -> AuthorizedOneRun:
    """Fail closed unless ``value`` is the exact nonce-CAS-issued capability."""

    _require_stage(value, AuthorizedOneRun, AuthorizedOneRun._stage_name)
    return cast(AuthorizedOneRun, value)


def _no_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ActivationBundleError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise ActivationBundleError(f"non-finite JSON number is forbidden: {value}")


def _depth(value: object, current: int = 1) -> int:
    if isinstance(value, Mapping):
        return max([current, *(_depth(item, current + 1) for item in value.values())])
    if isinstance(value, list):
        return max([current, *(_depth(item, current + 1) for item in value)])
    if isinstance(value, float) and not math.isfinite(value):
        raise ActivationBundleError("non-finite numbers are forbidden")
    return current


def parse_json_object(
    raw: bytes, *, label: str, maximum_bytes: int
) -> Mapping[str, object]:
    """Parse one strict UTF-8 JSON object with bounded size and nesting."""

    if type(maximum_bytes) is not int or maximum_bytes < 1:
        raise ActivationBundleError("JSON byte limit must be a positive integer")
    if not isinstance(raw, bytes) or not raw:
        raise ActivationBundleError(f"{label} bytes are required")
    if len(raw) > maximum_bytes:
        raise ActivationBundleError(f"{label} exceeds its byte limit")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ActivationBundleError(f"{label} is not strict UTF-8") from error
    if text.startswith("\ufeff"):
        raise ActivationBundleError(f"{label} must not contain a UTF-8 BOM")
    try:
        value = json.loads(
            text, object_pairs_hook=_no_duplicate_pairs, parse_constant=_reject_constant
        )
    except ActivationBundleError:
        raise
    except (json.JSONDecodeError, RecursionError) as error:
        raise ActivationBundleError(f"{label} is invalid JSON") from error
    if not isinstance(value, Mapping):
        raise ActivationBundleError(f"{label} must be a JSON object")
    if _depth(value) > _MAX_DEPTH:
        raise ActivationBundleError(f"{label} exceeds the nesting-depth limit")
    return value


def _exact_fields(
    value: Mapping[str, object], expected: frozenset[str], label: str
) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise ActivationBundleError(
            f"{label} fields are invalid; missing={sorted(expected - actual)}, "
            f"unknown={sorted(actual - expected)}"
        )


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ActivationBundleError(f"{label} must be sha256:<64 lowercase hex>")
    return value


def _require_nonzero_sha256(value: object, label: str) -> str:
    digest = _require_sha256(value, label)
    if digest == "sha256:" + "0" * 64:
        raise ActivationBundleError(f"{label} must not be a placeholder digest")
    return digest


def _require_git_id(value: object, label: str) -> str:
    if not isinstance(value, str) or not _GIT_ID.fullmatch(value):
        raise ActivationBundleError(f"{label} must be a 40-character lowercase Git ID")
    return value


def _require_text(value: object, label: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ActivationBundleError(f"{label} must be non-empty bounded text")
    return value


def _parse_time(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ActivationBundleError(f"{label} must be a UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise ActivationBundleError(f"{label} is invalid") from error
    if parsed.utcoffset() != timedelta(0):
        raise ActivationBundleError(f"{label} must be UTC")
    return parsed.astimezone(UTC)


def _principal(value: object, label: str) -> Principal:
    if not isinstance(value, Mapping):
        raise ActivationBundleError(f"{label} must be a principal object")
    _exact_fields(value, _PRINCIPAL_FIELDS, label)
    fields: dict[str, str] = {}
    for field in ("principal_id", "authority_domain", "key_id"):
        text = _require_text(value.get(field), f"{label} {field}")
        if text != text.strip():
            raise ActivationBundleError(
                f"{label} {field} must use canonical unpadded text"
            )
        fields[field] = text
    return Principal(
        principal_id=fields["principal_id"],
        authority_domain=fields["authority_domain"],
        key_id=fields["key_id"],
    )


def _raw_sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _signed_material(document: Mapping[str, object]) -> tuple[bytes, str]:
    signature = _require_text(document.get("signature"), "signature", maximum=16_384)
    material = dict(document)
    material.pop("signature")
    return _canonical_bytes(material), signature


def request_sha256(request_text: str) -> str:
    if not isinstance(request_text, str) or not request_text:
        raise ActivationBundleError("request text is required")
    return _raw_sha256(request_text.encode("utf-8"))


def validate_draft_manifest(manifest: Mapping[str, object]) -> None:
    """Validate the inert V4 description; it can never grant execution."""

    _exact_fields(manifest, _MANIFEST_FIELDS, "manifest")
    if type(manifest.get("schema_version")) is not int or manifest.get(
        "schema_version"
    ) != 2:
        raise ActivationBundleError("unsupported manifest version")
    if manifest.get("kind") != "hive-mind-generic-product-v4-manifest-v2":
        raise ActivationBundleError("wrong manifest kind")
    if manifest.get("plan_id") != "generic-hive-mind-product-v4":
        raise ActivationBundleError("wrong plan")
    if manifest.get("status") != "CANDIDATE_NOT_AUTHORIZED":
        raise ActivationBundleError("manifest status must remain inert")
    if manifest.get("target_branch") != "main":
        raise ActivationBundleError("wrong target branch")
    if manifest.get("execution_authorized") is not False:
        raise ActivationBundleError("manifest must not authorize execution")

    request_text = manifest.get("request_text")
    if not isinstance(request_text, str) or manifest.get(
        "request_sha256"
    ) != request_sha256(request_text):
        raise ActivationBundleError("request digest does not match request text")
    _require_sha256(manifest.get("repository_id"), "repository_id")

    source_intake = manifest.get("source_intake")
    if not isinstance(source_intake, Mapping):
        raise ActivationBundleError("source intake binding is missing")
    _exact_fields(source_intake, _SOURCE_INTAKE_FIELDS, "source intake binding")
    if (
        source_intake.get("path")
        != "evidence/audits/v4-successor-recovery/SOURCE-INTAKE.json"
        or source_intake.get("archive_path")
        != "evidence/sources/v4-successor-recovery/SOURCE-ARCHIVE.json"
    ):
        raise ActivationBundleError("source intake paths are not canonical")
    _require_sha256(source_intake.get("sha256"), "source intake sha256")
    _require_sha256(
        source_intake.get("archive_sha256"), "source archive sha256"
    )
    if (
        type(source_intake.get("source_count")) is not int
        or type(source_intake.get("unavailable_source_count")) is not int
    ):
        raise ActivationBundleError("source intake counts must be integers")
    if source_intake.get("source_count") != 13:
        raise ActivationBundleError("source intake must bind exactly 13 sources")
    if source_intake.get("unavailable_source_count") != 0:
        raise ActivationBundleError("source intake contains unavailable sources")

    predecessor = manifest.get("predecessor")
    if not isinstance(predecessor, Mapping):
        raise ActivationBundleError("predecessor is missing")
    _exact_fields(predecessor, _PREDECESSOR_FIELDS, "predecessor")
    if predecessor.get("plan_id") != "generic-hive-mind-product-v3":
        raise ActivationBundleError("wrong predecessor")
    _require_git_id(predecessor.get("commit"), "predecessor commit")
    _require_git_id(predecessor.get("tree"), "predecessor tree")
    if (
        predecessor.get("qualification_receipt_path")
        != "evidence/audits/generic-v3-baseline-recovery/V3-R4-QUALIFICATION.json"
    ):
        raise ActivationBundleError("predecessor receipt path is not canonical")
    _require_nonzero_sha256(
        predecessor.get("qualification_receipt_sha256"), "predecessor receipt"
    )

    candidate_base = manifest.get("candidate_base")
    if not isinstance(candidate_base, Mapping):
        raise ActivationBundleError("candidate base is missing")
    _exact_fields(candidate_base, _CANDIDATE_BASE_FIELDS, "candidate base")
    _require_git_id(candidate_base.get("commit"), "candidate base commit")
    _require_git_id(candidate_base.get("tree"), "candidate base tree")

    plan = manifest.get("plan")
    if not isinstance(plan, Mapping):
        raise ActivationBundleError("plan binding is missing")
    _exact_fields(plan, _PLAN_FIELDS, "plan binding")
    if plan.get("path") != "docs/execution/dags/generic-hive-mind-product-v4/plan.json":
        raise ActivationBundleError("plan path is not canonical")
    _require_sha256(plan.get("sha256"), "plan sha256")
    if plan.get("mode") != "host-activated-generic-dag-v1":
        raise ActivationBundleError("plan execution mode is unsupported")
    if (
        type(plan.get("node_count")) is not int
        or not 1 <= int(plan["node_count"]) <= 1_000
    ):
        raise ActivationBundleError("plan node count is invalid")

    policy = manifest.get("activation_policy")
    if not isinstance(policy, Mapping):
        raise ActivationBundleError("activation policy is missing")
    _exact_fields(policy, _POLICY_FIELDS, "activation policy")
    if (
        type(policy.get("maximum_lease_seconds")) is not int
        or policy.get("maximum_lease_seconds") != 900
    ):
        raise ActivationBundleError("activation lease policy is invalid")
    if policy.get("nonce_uniqueness") != "nonce-primary-key-global-single-use":
        raise ActivationBundleError("nonce policy is invalid")
    if policy.get("signature_order") != [
        "independent_review",
        "frozen_host",
        "issuer",
        "nonce_cas",
    ]:
        raise ActivationBundleError("signature order is invalid")
    if policy.get("required_principals") != [
        "builder",
        "independent_reviewer",
        "actor",
        "issuer",
        "host_attester",
    ]:
        raise ActivationBundleError("required principals are invalid")
    if policy.get("protected_merge_authorized") is not False:
        raise ActivationBundleError("activation cannot authorize a protected merge")


def _validate_predecessor_receipt(
    receipt: Mapping[str, object], predecessor: Mapping[str, object]
) -> None:
    """Require the canonical R4 receipt to carry its bounded ADAPT semantics."""

    if (
        type(receipt.get("schema_version")) is not int
        or receipt.get("schema_version") != 1
        or receipt.get("kind") != "hive-mind-v3-qualification-receipt-v1"
        or receipt.get("receipt_id") != "V3-R4-QUALIFICATION-2026-09-03"
        or receipt.get("case_id")
        != "CASE-GENERIC-V3-BASELINE-RECOVERY-2026-09-02"
    ):
        raise ActivationBundleError("predecessor qualification receipt is not canonical R4")
    if receipt.get("candidate_commit") != predecessor.get("commit"):
        raise ActivationBundleError("predecessor receipt commit does not match the manifest")
    if receipt.get("candidate_tree") != predecessor.get("tree"):
        raise ActivationBundleError("predecessor receipt tree does not match the manifest")
    if (
        receipt.get("status") != "QUALIFIED_INERT_PREDECESSOR"
        or receipt.get("disposition") != "ADAPT"
    ):
        raise ActivationBundleError("predecessor receipt is not an adapted inert predecessor")
    for field in (
        "execution_authorized",
        "activation_authorized",
        "release_ready",
        "deployment_ready",
        "production_ready",
        "protected_merge_authorized",
        "a5_ready",
        "superiority_claimed",
        "external_attestation",
    ):
        if receipt.get(field) is not False:
            raise ActivationBundleError(f"predecessor receipt must deny {field}")
    if receipt.get("signature") is not None:
        raise ActivationBundleError("predecessor receipt must not claim a signature")
    court = receipt.get("court")
    if not isinstance(court, Mapping) or court.get("verdict") != "ADAPT":
        raise ActivationBundleError("predecessor receipt lacks the ADAPT judgment")
    identities = tuple(court.get(field) for field in ("builder", "curator", "judge"))
    if any(not isinstance(value, str) or not value for value in identities) or len(
        {str(value).casefold() for value in identities}
    ) != len(identities):
        raise ActivationBundleError("predecessor court identities are not distinct")
    dissent = receipt.get("material_dissent")
    if not isinstance(dissent, list) or "V4-SBOM-P2-001" not in {
        item.get("finding_id") for item in dissent if isinstance(item, Mapping)
    }:
        raise ActivationBundleError("predecessor receipt omits the carried SBOM dissent")


def _validate_review(
    review: Mapping[str, object], bundle: Mapping[str, object], now: datetime
) -> tuple[Principal, bytes, str]:
    _exact_fields(review, _REVIEW_FIELDS, "review evidence")
    if (
        type(review.get("schema_version")) is not int
        or review.get("schema_version") != 1
        or review.get("kind") != "hive-mind-independent-review-v1"
    ):
        raise ActivationBundleError("review evidence kind or version is invalid")
    for field in (
        "candidate_commit",
        "candidate_tree",
        "candidate_content_sha256",
        "plan_sha256",
        "manifest_sha256",
    ):
        if review.get(field) != bundle.get(field):
            raise ActivationBundleError(
                f"review evidence {field} does not match the bundle"
            )
    if review.get("verdict") != "ADOPT":
        raise ActivationBundleError("independent review did not adopt the candidate")
    _require_sha256(review.get("test_evidence_sha256"), "review test evidence")
    reviewed_at = _parse_time(review.get("reviewed_at"), "reviewed_at")
    if reviewed_at > now:
        raise ActivationBundleError("review evidence is from the future")
    reviewer = _principal(review.get("reviewer"), "reviewer")
    if reviewer != _principal(bundle.get("independent_reviewer"), "bundle reviewer"):
        raise ActivationBundleError("reviewer identity does not match the bundle")
    signed, signature = _signed_material(review)
    return reviewer, signed, signature


def _validate_frozen_host(
    evidence: Mapping[str, object],
    bundle: Mapping[str, object],
    expires_at: datetime,
    now: datetime,
) -> tuple[Principal, bytes, str]:
    _exact_fields(evidence, _HOST_FIELDS, "frozen-host evidence")
    if (
        type(evidence.get("schema_version")) is not int
        or evidence.get("schema_version") != 1
        or evidence.get("kind") != "hive-mind-frozen-host-attestation-v1"
    ):
        raise ActivationBundleError("frozen-host evidence kind or version is invalid")
    for field in (
        "candidate_commit",
        "candidate_tree",
        "candidate_parent_commit",
        "candidate_parent_tree",
        "candidate_content_sha256",
        "plan_sha256",
        "manifest_sha256",
    ):
        if evidence.get(field) != bundle.get(field):
            raise ActivationBundleError(
                f"frozen-host evidence {field} does not match the bundle"
            )
    for field in (
        "host_bundle_sha256",
        "interpreter_sha256",
        "git_executable_sha256",
        "execution_client_sha256",
    ):
        _require_sha256(evidence.get(field), field)
    for field in ("worktree_clean", "bytecode_free", "read_only_custody"):
        if evidence.get(field) is not True:
            raise ActivationBundleError(f"frozen-host evidence requires {field}=true")
    observed_at = _parse_time(evidence.get("observed_at"), "host observed_at")
    host_expires = _parse_time(evidence.get("expires_at"), "host expires_at")
    if observed_at > now or host_expires < expires_at or host_expires <= observed_at:
        raise ActivationBundleError(
            "frozen-host evidence is stale for the activation lease"
        )
    attester = _principal(evidence.get("attester"), "host attester")
    if attester != _principal(bundle.get("host_attester"), "bundle host attester"):
        raise ActivationBundleError("host-attester identity does not match the bundle")
    signed, signature = _signed_material(evidence)
    return attester, signed, signature


def prepare_activation_bundle(
    *,
    bundle_bytes: bytes,
    manifest_bytes: bytes,
    plan_bytes: bytes,
    predecessor_receipt_bytes: bytes,
    review_evidence_bytes: bytes,
    frozen_host_evidence_bytes: bytes,
    now: datetime,
) -> ActivationPayload:
    """Bind all raw artifacts and times without trusting an external signature."""

    if now.tzinfo is None or now.utcoffset() is None:
        raise ActivationBundleError("current time must include a timezone")
    current_time = now.astimezone(UTC)
    bundle = parse_json_object(
        bundle_bytes, label="activation bundle", maximum_bytes=_MAX_BUNDLE_BYTES
    )
    manifest = parse_json_object(
        manifest_bytes, label="manifest", maximum_bytes=_MAX_EVIDENCE_BYTES
    )
    predecessor_receipt = parse_json_object(
        predecessor_receipt_bytes,
        label="predecessor qualification receipt",
        maximum_bytes=_MAX_EVIDENCE_BYTES,
    )
    review = parse_json_object(
        review_evidence_bytes,
        label="review evidence",
        maximum_bytes=_MAX_EVIDENCE_BYTES,
    )
    frozen = parse_json_object(
        frozen_host_evidence_bytes,
        label="frozen-host evidence",
        maximum_bytes=_MAX_EVIDENCE_BYTES,
    )
    if not plan_bytes or len(plan_bytes) > 16 * _MAX_EVIDENCE_BYTES:
        raise ActivationBundleError("plan bytes are missing or oversized")
    validate_draft_manifest(manifest)
    _exact_fields(bundle, _BUNDLE_FIELDS, "activation bundle")
    if (
        type(bundle.get("schema_version")) is not int
        or bundle.get("schema_version") != 2
        or bundle.get("kind") != "hive-mind-one-run-activation-bundle-v2"
    ):
        raise ActivationBundleError("activation bundle kind or version is invalid")
    for field in ("plan_id", "request_sha256", "repository_id", "target_branch"):
        if bundle.get(field) != manifest.get(field):
            raise ActivationBundleError(f"bundle {field} does not match the manifest")

    predecessor = manifest["predecessor"]
    candidate_base = manifest["candidate_base"]
    plan_binding = manifest["plan"]
    assert (
        isinstance(predecessor, Mapping)
        and isinstance(candidate_base, Mapping)
        and isinstance(plan_binding, Mapping)
    )
    _validate_predecessor_receipt(predecessor_receipt, predecessor)
    expected = {
        "predecessor_commit": predecessor["commit"],
        "predecessor_tree": predecessor["tree"],
        "candidate_parent_commit": candidate_base["commit"],
        "candidate_parent_tree": candidate_base["tree"],
        "plan_sha256": plan_binding["sha256"],
        "manifest_sha256": _raw_sha256(manifest_bytes),
    }
    for field, value in expected.items():
        if bundle.get(field) != value:
            raise ActivationBundleError(
                f"bundle {field} does not match its bound artifact"
            )
    if bundle.get("plan_sha256") != _raw_sha256(plan_bytes):
        raise ActivationBundleError("plan bytes do not match the activation bundle")
    if predecessor.get("qualification_receipt_sha256") != _raw_sha256(
        predecessor_receipt_bytes
    ):
        raise ActivationBundleError(
            "predecessor qualification receipt bytes do not match the manifest"
        )

    for field in (
        "request_sha256",
        "repository_id",
        "candidate_content_sha256",
        "plan_sha256",
        "manifest_sha256",
        "frozen_host_evidence_sha256",
        "review_evidence_sha256",
        "nonce",
    ):
        _require_sha256(bundle.get(field), field)
    for field in (
        "predecessor_commit",
        "predecessor_tree",
        "candidate_parent_commit",
        "candidate_parent_tree",
        "candidate_commit",
        "candidate_tree",
    ):
        _require_git_id(bundle.get(field), field)
    if bundle.get("candidate_commit") == bundle.get("candidate_parent_commit"):
        raise ActivationBundleError("candidate must not equal its parent")
    branch = bundle.get("candidate_branch")
    if (
        not isinstance(branch, str)
        or not _BRANCH.fullmatch(branch)
        or ".." in branch
        or "//" in branch
    ):
        raise ActivationBundleError("candidate branch must be a bounded codex/ branch")
    if bundle.get("review_evidence_sha256") != _raw_sha256(review_evidence_bytes):
        raise ActivationBundleError("review evidence bytes do not match the bundle")
    if bundle.get("frozen_host_evidence_sha256") != _raw_sha256(
        frozen_host_evidence_bytes
    ):
        raise ActivationBundleError(
            "frozen-host evidence bytes do not match the bundle"
        )

    issued_at = _parse_time(bundle.get("issued_at"), "issued_at")
    expires_at = _parse_time(bundle.get("expires_at"), "expires_at")
    if (
        expires_at <= issued_at
        or expires_at - issued_at > _MAX_LEASE
        or issued_at > current_time
        or expires_at <= current_time
    ):
        raise ActivationBundleError("bundle is not currently valid")

    principals = {
        name: _principal(bundle.get(name), name)
        for name in (
            "builder",
            "independent_reviewer",
            "actor",
            "issuer",
            "host_attester",
        )
    }
    if len({item.principal_id.casefold() for item in principals.values()}) != len(
        principals
    ):
        raise ActivationBundleError("activation principals must be distinct")
    if len({item.key_id.casefold() for item in principals.values()}) != len(principals):
        raise ActivationBundleError("activation principal keys must be distinct")

    reviewer, review_signed, review_signature = _validate_review(
        review, bundle, current_time
    )
    attester, host_signed, host_signature = _validate_frozen_host(
        frozen, bundle, expires_at, current_time
    )
    issuer_signed, issuer_signature = _signed_material(bundle)
    activation_digest = _raw_sha256(issuer_signed)
    return _issue_payload(
        nonce=str(bundle["nonce"]),
        activation_digest=activation_digest,
        candidate_commit=str(bundle["candidate_commit"]),
        candidate_tree=str(bundle["candidate_tree"]),
        candidate_content_sha256=str(bundle["candidate_content_sha256"]),
        candidate_parent_commit=str(bundle["candidate_parent_commit"]),
        candidate_parent_tree=str(bundle["candidate_parent_tree"]),
        plan_sha256=str(bundle["plan_sha256"]),
        manifest_sha256=str(bundle["manifest_sha256"]),
        repository_id=str(bundle["repository_id"]),
        request_sha256=str(bundle["request_sha256"]),
        target_branch=str(bundle["target_branch"]),
        execution_client_sha256=str(frozen["execution_client_sha256"]),
        issued_at=issued_at,
        protected_merge_authorized=False,
        expires_at=expires_at,
        builder=principals["builder"],
        reviewer=reviewer,
        actor=principals["actor"],
        issuer=principals["issuer"],
        issuer_signature=issuer_signature,
        issuer_signed_bytes=issuer_signed,
        review_signature=review_signature,
        review_signed_bytes=review_signed,
        host_attester=attester,
        host_signature=host_signature,
        host_signed_bytes=host_signed,
    )


def verify_external_attestations(
    payload: ActivationPayload,
    *,
    review_verifier: SignatureVerifier,
    frozen_host_verifier: SignatureVerifier,
) -> AttestedActivation:
    """Verify both independently signed prerequisites before the issuer."""

    _require_payload(payload)
    if not review_verifier(
        payload.reviewer, payload.review_signed_bytes, payload.review_signature
    ):
        raise ActivationBundleError("independent-review signature verification failed")
    if not frozen_host_verifier(
        payload.host_attester, payload.host_signed_bytes, payload.host_signature
    ):
        raise ActivationBundleError("frozen-host signature verification failed")
    return _issue_stage(
        AttestedActivation, AttestedActivation._stage_name, payload
    )  # type: ignore[return-value]


def verify_external_signature(
    activation: AttestedActivation, verifier: SignatureVerifier
) -> VerifiedActivation:
    """Verify the external issuer only after both prerequisite attestations."""

    try:
        payload = _require_stage(
            activation, AttestedActivation, AttestedActivation._stage_name
        )
    except ActivationBundleError as error:
        raise ActivationBundleError(
            "external attestations must be verified before the issuer"
        ) from error
    if not verifier(
        payload.issuer, payload.issuer_signed_bytes, payload.issuer_signature
    ):
        raise ActivationBundleError("external issuer signature verification failed")
    return _issue_stage(
        VerifiedActivation, VerifiedActivation._stage_name, payload
    )  # type: ignore[return-value]


def _validated_reservation_receipt(
    receipt_bytes: bytes,
    payload: ActivationPayload,
    verifier: SignatureVerifier,
) -> bytes:
    receipt = parse_json_object(
        receipt_bytes,
        label="nonce reservation receipt",
        maximum_bytes=65_536,
    )
    _exact_fields(receipt, _RESERVATION_FIELDS, "nonce reservation receipt")
    if (
        type(receipt.get("schema_version")) is not int
        or receipt.get("schema_version") != 1
        or receipt.get("kind")
        != "hive-mind-nonce-reservation-receipt-v1"
    ):
        raise ActivationBundleError(
            "nonce reservation receipt kind or version is invalid"
        )
    if receipt_bytes != _canonical_bytes(receipt):
        raise ActivationBundleError("nonce reservation receipt must be canonical JSON")
    expected = {
        "nonce": payload.nonce,
        "activation_digest": payload.activation_digest,
        "candidate_commit": payload.candidate_commit,
        "candidate_tree": payload.candidate_tree,
        "candidate_content_sha256": payload.candidate_content_sha256,
        "plan_sha256": payload.plan_sha256,
        "issued_at": _utc_text(payload.issued_at),
        "expires_at": _utc_text(payload.expires_at),
    }
    for field, value in expected.items():
        if receipt.get(field) != value:
            raise ActivationBundleError(
                f"nonce reservation receipt {field} does not match the activation"
            )
    consumed_at = _parse_time(receipt.get("consumed_at"), "nonce consumed_at")
    if consumed_at < payload.issued_at or consumed_at >= payload.expires_at:
        raise ActivationBundleError(
            "nonce reservation must occur within the activation validity interval"
        )
    ledger = _principal(receipt.get("ledger"), "nonce ledger")
    activation_principals = (
        payload.builder,
        payload.reviewer,
        payload.actor,
        payload.issuer,
        payload.host_attester,
    )
    if ledger.principal_id.casefold() in {
        item.principal_id.casefold() for item in activation_principals
    }:
        raise ActivationBundleError(
            "nonce ledger principal must be independent from activation principals"
        )
    if ledger.key_id.casefold() in {
        item.key_id.casefold() for item in activation_principals
    }:
        raise ActivationBundleError(
            "nonce ledger key must be independent from activation principal keys"
        )
    signed_bytes, signature = _signed_material(receipt)
    if not verifier(ledger, signed_bytes, signature):
        raise ActivationBundleError(
            "nonce reservation receipt signature verification failed"
        )
    return receipt_bytes


def restore_one_run(
    activation: VerifiedActivation,
    receipt_bytes: bytes,
    *,
    receipt_verifier: SignatureVerifier,
) -> AuthorizedOneRun:
    """Restore a run after restart from an externally authenticated CAS receipt.

    The caller must freshly prepare and verify the activation in this process.
    The already-consumed nonce is not consumed again.
    """

    try:
        payload = _require_stage(
            activation, VerifiedActivation, VerifiedActivation._stage_name
        )
    except ActivationBundleError as error:
        raise ActivationBundleError(
            "issuer signature must be verified before nonce reservation"
        ) from error
    receipt = _validated_reservation_receipt(
        receipt_bytes, payload, receipt_verifier
    )
    return _issue_stage(
        AuthorizedOneRun,
        AuthorizedOneRun._stage_name,
        payload,
        reservation_receipt=receipt,
    )  # type: ignore[return-value]


def reserve_one_run(
    activation: VerifiedActivation,
    ledger: NonceLedger,
    *,
    receipt_verifier: SignatureVerifier,
) -> AuthorizedOneRun:
    """Consume the nonce by CAS and authenticate the durable host receipt."""

    try:
        payload = _require_stage(
            activation, VerifiedActivation, VerifiedActivation._stage_name
        )
    except ActivationBundleError as error:
        raise ActivationBundleError(
            "issuer signature must be verified before nonce reservation"
        ) from error
    receipt = ledger.consume_once(
        nonce=payload.nonce,
        activation_digest=payload.activation_digest,
        candidate_commit=payload.candidate_commit,
        candidate_tree=payload.candidate_tree,
        candidate_content_sha256=payload.candidate_content_sha256,
        plan_sha256=payload.plan_sha256,
        issued_at=payload.issued_at,
        expires_at=payload.expires_at,
    )
    if receipt is None:
        raise ActivationBundleError("activation nonce was already used")
    return restore_one_run(
        activation, receipt, receipt_verifier=receipt_verifier
    )
