"""Immutable, digest-sealed grants for controlled GitHub delivery.

A grant is the only thing that authorizes a remote action.  It is frozen and
tamper-evident: every field except the digest is folded into ``grant_digest``
and re-checked on construction, so a mutated copy cannot be reconstructed.
The set of grantable actions is a closed vocabulary that structurally excludes
merge, so no grant can ever carry merge authority.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from hive_mind_os.brain_kernel.canonical import canonical_digest

_SIMPLE_NAME = re.compile(r"[A-Za-z0-9_.-]+\Z")

# Mirrors hive_mind_os.autonomous_os.PROTECTED_BRANCHES (autonomous_os.py:32).
# It is duplicated on purpose: branch denial must not depend on importing the
# heavy legacy brain module, and the constant belongs with the denial logic.
PROTECTED_BRANCHES: frozenset[str] = frozenset({"main", "master", "staging"})

# "merge" is deliberately absent and is not a spelling this package accepts.
VALID_DELIVERY_ACTIONS: frozenset[str] = frozenset(
    {"push", "open_draft_pr", "post_comment"}
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


@dataclass(frozen=True, slots=True)
class DeliveryGrant:
    """One immutable authorization for controlled delivery to one repository."""

    grant_id: str
    owner: str
    repository: str
    base_branch: str
    branch_prefix: str
    allowed_actions: tuple[str, ...]
    issued_at: str
    grant_digest: str

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
        _require_text(self.issued_at, "issued_at")
        _require_text(self.grant_digest, "grant_digest")
        expected = canonical_digest(
            _grant_payload(
                grant_id=self.grant_id,
                owner=self.owner,
                repository=self.repository,
                base_branch=self.base_branch,
                branch_prefix=self.branch_prefix,
                allowed_actions=actions,
                issued_at=self.issued_at,
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
    ) -> "DeliveryGrant":
        """Seal one grant; invalid or ungrantable input fails closed."""

        _require_text(grant_id, "grant_id")
        _require_simple_name(owner, "owner")
        _require_simple_name(repository, "repository")
        _require_simple_name(base_branch, "base_branch")
        actions = _require_actions(allowed_actions)
        digest = canonical_digest(
            _grant_payload(
                grant_id=grant_id,
                owner=owner,
                repository=repository,
                base_branch=base_branch,
                branch_prefix=branch_prefix,
                allowed_actions=actions,
                issued_at=issued_at,
            )
        )
        return cls(
            grant_id,
            owner,
            repository,
            base_branch,
            branch_prefix,
            actions,
            issued_at,
            digest,
        )

    def require(self, action: str) -> None:
        """Deny any action this grant does not explicitly carry."""

        if action not in self.allowed_actions:
            raise DeliveryGrantError(
                f"delivery grant {self.grant_id} does not allow action {action!r}"
            )

    def require_push_branch(self, branch: str) -> None:
        """Deny every ref except a branch under the granted run-branch prefix."""

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
