"""Immutable, digest-sealed grants for controlled GitHub delivery.

A grant is the only thing that authorizes a remote action.  It is frozen and
tamper-evident: every field except the digest is folded into ``grant_digest``
and re-checked on construction, so a mutated copy cannot be reconstructed.
The set of grantable actions is a closed vocabulary that structurally excludes
merge, so no grant can ever carry merge authority.

Tamper-evidence alone does not say who issued a grant, and a sealed grant that
never goes stale outlives the work it was cut for.  Two properties close that:
issuance is recorded in a :class:`DeliveryGrantLedger` and a grant the ledger
never admitted authorizes nothing, and every grant carries a finite
``expires_at`` that is refused at use.  Once the owner anchors the ledger to a
``RootProvenance`` admitted by the kernel authority registry, an issuance that
cannot present that same record is refused, so a self-issued grant is
distinguishable from an owner-issued one.  The digest is unkeyed: this is
attribution by record, not a signature, and it cannot stop a caller that is
already inside the process from performing the ceremony itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from hive_mind_os.brain_kernel.authority import RootProvenance
from hive_mind_os.brain_kernel.canonical import canonical_digest

_SIMPLE_NAME = re.compile(r"[A-Za-z0-9_.-]+\Z")

# The issuer and authority recorded for a grant nobody anchored to an owner
# authority.  It is a reserved spelling: it names the absence of an owner, and
# an anchored ledger refuses it.
SELF_ISSUED = "self-issued"

DEFAULT_GRANT_LIFETIME = timedelta(hours=24)
MAX_GRANT_LIFETIME = timedelta(days=7)

# Mirrors hive_mind_os.autonomous_os.PROTECTED_BRANCHES (autonomous_os.py:32).
# It is duplicated on purpose: branch denial must not depend on importing the
# heavy legacy brain module, and the constant belongs with the denial logic.
PROTECTED_BRANCHES: frozenset[str] = frozenset({"main", "master", "staging"})

# "merge" is deliberately absent and is not a spelling this package accepts.
# Every action here is additive and self-scoped: "close_own_pr" and
# "delete_own_branch" exist so a pilot can retract exactly what it created, and
# neither is implied by any other action -- a grant must name it to hold it.
VALID_DELIVERY_ACTIONS: frozenset[str] = frozenset(
    {"push", "open_draft_pr", "post_comment", "close_own_pr", "delete_own_branch"}
)


class DeliveryGrantError(PermissionError):
    """A remote delivery action is not covered by an immutable grant."""


def _grant_payload(
    *,
    grant_id: str,
    owner: str,
    repository: str,
    base_branch: str,
    branch_prefix: str,
    allowed_actions: Iterable[str],
    issued_at: str,
    expires_at: str,
    issuer: str,
    authority_ref: str,
) -> dict[str, Any]:
    """Return the exact document sealed by ``grant_digest``."""

    return {
        "grant_id": grant_id,
        "owner": owner,
        "repository": repository,
        "base_branch": base_branch,
        "branch_prefix": branch_prefix,
        "allowed_actions": list(allowed_actions),
        "issued_at": issued_at,
        "expires_at": expires_at,
        "issuer": issuer,
        "authority_ref": authority_ref,
    }


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DeliveryGrantError(f"delivery grant {label} is required")
    return value


def _require_simple_name(value: Any, label: str) -> str:
    _require_text(value, label)
    if _SIMPLE_NAME.fullmatch(value) is None:
        raise DeliveryGrantError(f"delivery grant {label} must be a simple name")
    return value


def _require_actions(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)) or not value:
        raise DeliveryGrantError("delivery grant requires at least one allowed action")
    actions = tuple(value)
    if any(not isinstance(action, str) for action in actions):
        raise DeliveryGrantError("delivery grant actions must be strings")
    if len(set(actions)) != len(actions):
        raise DeliveryGrantError("delivery grant actions must be unique")
    unknown = sorted(set(actions) - VALID_DELIVERY_ACTIONS)
    if unknown:
        raise DeliveryGrantError(
            "delivery grant action is not grantable: " + ", ".join(unknown)
        )
    return actions


def _moment(value: Any, label: str) -> datetime:
    _require_text(value, label)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise DeliveryGrantError(
            f"delivery grant {label} must be an RFC 3339 time"
        ) from error
    if parsed.tzinfo is None:
        raise DeliveryGrantError(f"delivery grant {label} must carry a UTC offset")
    return parsed


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sealed_provenance(provenance: Any) -> RootProvenance:
    """Refuse any owner authority record that does not seal its own fields.

    The payload mirrors the one ``AuthorityRegistry.mint_root`` seals
    (authority.py:79-86) on purpose: this package validates a record it is
    handed without depending on the registry that minted it.
    """

    if not isinstance(provenance, RootProvenance):
        raise DeliveryGrantError(
            "owner authority requires a recorded root provenance"
        )
    expected = canonical_digest(
        {
            "envelope": provenance.envelope_digest,
            "issuer": provenance.issuer,
            "authority_ref": provenance.authority_ref,
            "recorded_at": provenance.recorded_at,
        }
    )
    if provenance.record_digest != expected:
        raise DeliveryGrantError(
            "owner authority record digest does not seal its fields"
        )
    return provenance


@dataclass(frozen=True, slots=True)
class GrantIssuance:
    """The recorded act that admitted one delivery grant into a ledger."""

    grant_digest: str
    issuer: str
    authority_ref: str
    recorded_at: str
    anchor_digest: str
    record_digest: str


class DeliveryGrantLedger:
    """Owner-anchored issuance ledger; an unanchored ledger authorizes nothing."""

    def __init__(self) -> None:
        self._issuances: dict[str, GrantIssuance] = {}
        self._anchor: RootProvenance | None = None

    @property
    def anchor_digest(self) -> str:
        return "" if self._anchor is None else self._anchor.record_digest

    def anchor(self, provenance: RootProvenance) -> RootProvenance:
        """Admit the one owner authority every later issuance must present."""

        sealed = _sealed_provenance(provenance)
        if self._anchor is not None and self._anchor.record_digest != sealed.record_digest:
            raise DeliveryGrantError(
                "owner authority anchor is recorded and cannot be replaced"
            )
        self._anchor = sealed
        return sealed

    def record(
        self,
        grant: DeliveryGrant,
        *,
        provenance: RootProvenance | None,
        recorded_at: str,
    ) -> GrantIssuance:
        """Admit one grant, refusing an issuance the anchored owner did not back."""

        anchor = self.anchor_digest
        if not anchor:
            raise DeliveryGrantError(
                "delivery grant ledger requires a recorded owner authority anchor"
            )
        if provenance is None:
            raise DeliveryGrantError(
                "delivery grant issuance requires the recorded owner authority"
            )
        sealed_provenance = _sealed_provenance(provenance)
        issuer = SELF_ISSUED if provenance is None else provenance.issuer
        authority_ref = SELF_ISSUED if provenance is None else provenance.authority_ref
        if grant.issuer != issuer or grant.authority_ref != authority_ref:
            raise DeliveryGrantError(
                "delivery grant does not name the authority it was issued under"
            )
        anchored = sealed_provenance.record_digest
        if anchored != anchor:
            raise DeliveryGrantError(
                "delivery grant issuance is not anchored to the recorded owner authority"
            )
        _require_text(recorded_at, "recorded_at")
        lifetime = _moment(grant.expires_at, "expires_at") - _moment(
            grant.issued_at, "issued_at"
        )
        if lifetime > MAX_GRANT_LIFETIME:
            raise DeliveryGrantError(
                "delivery grant lifetime exceeds the maximum grantable window"
            )
        record = GrantIssuance(
            grant.grant_digest,
            issuer,
            authority_ref,
            recorded_at,
            anchored,
            canonical_digest(
                {
                    "grant": grant.grant_digest,
                    "issuer": issuer,
                    "authority_ref": authority_ref,
                    "recorded_at": recorded_at,
                    "anchor": anchored,
                }
            ),
        )
        self._issuances[grant.grant_digest] = record
        return record

    def issuance(self, grant_digest: str) -> GrantIssuance | None:
        return self._issuances.get(grant_digest)

    def require_issued(self, grant: DeliveryGrant) -> GrantIssuance:
        """Refuse a grant unless a current owner anchor admitted it."""

        anchor = self.anchor_digest
        if not anchor:
            raise DeliveryGrantError(
                "delivery grant ledger requires a recorded owner authority anchor"
            )
        record = self._issuances.get(grant.grant_digest)
        if record is None:
            raise DeliveryGrantError(
                f"delivery grant {grant.grant_id} has no recorded issuance"
            )
        if record.anchor_digest != anchor:
            raise DeliveryGrantError(
                f"delivery grant {grant.grant_id} was not issued "
                "under the recorded owner authority"
            )
        return record


LEDGER = DeliveryGrantLedger()


@dataclass(frozen=True, slots=True)
class DeliveryGrant:
    """One immutable, attributable, finite authorization for one repository.

    ``grant_digest`` keeps its position ahead of the fields it seals because
    existing callers construct a grant positionally; the digest covers every
    field regardless of declaration order.
    """

    grant_id: str
    owner: str
    repository: str
    base_branch: str
    branch_prefix: str
    allowed_actions: tuple[str, ...]
    issued_at: str
    grant_digest: str
    expires_at: str = ""
    issuer: str = ""
    authority_ref: str = ""

    def __post_init__(self) -> None:
        _require_text(self.grant_id, "grant_id")
        _require_simple_name(self.owner, "owner")
        _require_simple_name(self.repository, "repository")
        _require_simple_name(self.base_branch, "base_branch")
        prefix = _require_text(self.branch_prefix, "branch_prefix")
        if not prefix.endswith("/") or prefix.startswith("/") or prefix == "/":
            raise DeliveryGrantError(
                "delivery grant branch_prefix must be a relative prefix ending in '/'"
            )
        actions = _require_actions(self.allowed_actions)
        _require_text(self.grant_digest, "grant_digest")
        _require_text(self.issuer, "issuer")
        _require_text(self.authority_ref, "authority_ref")
        if _moment(self.expires_at, "expires_at") <= _moment(
            self.issued_at, "issued_at"
        ):
            raise DeliveryGrantError("delivery grant expires_at must follow issued_at")
        expected = canonical_digest(
            _grant_payload(
                grant_id=self.grant_id,
                owner=self.owner,
                repository=self.repository,
                base_branch=self.base_branch,
                branch_prefix=self.branch_prefix,
                allowed_actions=actions,
                issued_at=self.issued_at,
                expires_at=self.expires_at,
                issuer=self.issuer,
                authority_ref=self.authority_ref,
            )
        )
        if self.grant_digest != expected:
            raise DeliveryGrantError("delivery grant digest does not seal its fields")

    @classmethod
    def issue(
        cls,
        *,
        grant_id: str,
        owner: str,
        repository: str,
        base_branch: str,
        branch_prefix: str,
        allowed_actions: tuple[str, ...],
        issued_at: str,
        expires_at: str | None = None,
        provenance: RootProvenance | None = None,
        recorded_at: str | None = None,
    ) -> "DeliveryGrant":
        """Seal one grant and record its issuance; unrecorded input fails closed.

        ``provenance`` is the owner authority the issuance is made under. The
        ledger must already be anchored to that record; a bare process ledger
        and self-issued grants are denied before they can authorize delivery.
        """

        _require_text(grant_id, "grant_id")
        _require_simple_name(owner, "owner")
        _require_simple_name(repository, "repository")
        _require_simple_name(base_branch, "base_branch")
        actions = _require_actions(allowed_actions)
        issued = _moment(issued_at, "issued_at")
        if provenance is not None:
            _sealed_provenance(provenance)
        issuer = SELF_ISSUED if provenance is None else provenance.issuer
        authority_ref = SELF_ISSUED if provenance is None else provenance.authority_ref
        expiry = (
            _stamp(issued + DEFAULT_GRANT_LIFETIME) if expires_at is None else expires_at
        )
        digest = canonical_digest(
            _grant_payload(
                grant_id=grant_id,
                owner=owner,
                repository=repository,
                base_branch=base_branch,
                branch_prefix=branch_prefix,
                allowed_actions=actions,
                issued_at=issued_at,
                expires_at=expiry,
                issuer=issuer,
                authority_ref=authority_ref,
            )
        )
        grant = cls(
            grant_id,
            owner,
            repository,
            base_branch,
            branch_prefix,
            actions,
            issued_at,
            digest,
            expiry,
            issuer,
            authority_ref,
        )
        LEDGER.record(
            grant,
            provenance=provenance,
            recorded_at=issued_at if recorded_at is None else recorded_at,
        )
        return grant

    def _require_usable(self, now: str | None) -> None:
        """Deny a grant the ledger never admitted, and one whose lifetime ran out."""

        LEDGER.require_issued(self)
        moment = datetime.now(timezone.utc) if now is None else _moment(now, "now")
        if moment >= _moment(self.expires_at, "expires_at"):
            raise DeliveryGrantError(
                f"delivery grant {self.grant_id} expired at {self.expires_at}"
            )

    def require(
        self,
        action: str,
        *,
        now: str | None = None,
    ) -> None:
        """Deny any action this grant does not explicitly carry."""

        self._require_usable(now)
        if action not in self.allowed_actions:
            raise DeliveryGrantError(
                f"delivery grant {self.grant_id} does not allow action {action!r}"
            )

    def require_push_branch(
        self,
        branch: str,
        *,
        now: str | None = None,
    ) -> None:
        """Deny every ref except a branch under the granted run-branch prefix."""

        self._require_usable(now)
        if not isinstance(branch, str) or not branch.strip():
            raise DeliveryGrantError("push branch is required")
        if branch in PROTECTED_BRANCHES:
            raise DeliveryGrantError(f"push to protected branch {branch!r} is denied")
        if branch == self.base_branch:
            raise DeliveryGrantError(
                f"push to grant base branch {branch!r} is denied"
            )
        if not branch.startswith(self.branch_prefix):
            raise DeliveryGrantError(
                f"push branch {branch!r} is outside the granted prefix "
                f"{self.branch_prefix!r}"
            )

    def require_own_run_branch(
        self,
        branch: Any,
        operation: str,
        *,
        now: str | None = None,
    ) -> None:
        """Deny every ref this grant could not itself have created.

        The retraction operations (``close_own_pr``, ``delete_own_branch``) are
        allowed to touch exactly the branches ``require_push_branch`` would have
        allowed them to create, and nothing else.  ``operation`` only names the
        caller in the refusal so an audit trail records what was refused; it
        never relaxes a check.
        """

        self._require_usable(now)
        if not isinstance(branch, str) or not branch.strip():
            raise DeliveryGrantError(f"{operation} requires a branch name")
        if branch in PROTECTED_BRANCHES:
            raise DeliveryGrantError(
                f"{operation} on protected branch {branch!r} is denied"
            )
        if branch == self.base_branch:
            raise DeliveryGrantError(
                f"{operation} on grant base branch {branch!r} is denied"
            )
        if not branch.startswith(self.branch_prefix):
            raise DeliveryGrantError(
                f"{operation} on branch {branch!r} is outside the granted prefix "
                f"{self.branch_prefix!r}"
            )
