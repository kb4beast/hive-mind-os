"""N06 fail-closed admission rules for reuse and validation receipts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from .runtime_contracts import canonical_digest, require_digest
from .test_result_cache import CachedTestResult, TestOutcome


class CheckPurpose(StrEnum):
    DEVELOPER = "developer"
    INDEPENDENT_CANDIDATE = "independent_candidate"
    INTEGRATION = "integration"
    PUBLICATION_OBSERVATION = "publication_observation"


@dataclass(frozen=True, slots=True)
class ValidationScope:
    tenant_digest: str
    trust_domain_digest: str
    adapter_digest: str
    policy_digest: str
    external_state_digest: str | None
    purpose: CheckPurpose

    def __post_init__(self):
        for x in (
            self.tenant_digest,
            self.trust_domain_digest,
            self.adapter_digest,
            self.policy_digest,
        ):
            require_digest(x, "validation scope")
        if self.external_state_digest is not None:
            require_digest(self.external_state_digest, "external_state_digest")

    @property
    def digest(self):
        return canonical_digest(
            {
                "schema_version": 2,
                "tenant_digest": self.tenant_digest,
                "trust_domain_digest": self.trust_domain_digest,
                "adapter_digest": self.adapter_digest,
                "policy_digest": self.policy_digest,
                "external_state_digest": self.external_state_digest,
                "purpose": self.purpose.value,
            }
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "tenant_digest": self.tenant_digest,
            "trust_domain_digest": self.trust_domain_digest,
            "adapter_digest": self.adapter_digest,
            "policy_digest": self.policy_digest,
            "external_state_digest": self.external_state_digest,
            "purpose": self.purpose.value,
            "scope_digest": self.digest,
        }

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> "ValidationScope":
        fields = {
            "schema_version",
            "tenant_digest",
            "trust_domain_digest",
            "adapter_digest",
            "policy_digest",
            "external_state_digest",
            "purpose",
            "scope_digest",
        }
        if set(value) != fields or value.get("schema_version") != 2:
            raise ValueError("validation scope has unknown shape")
        try:
            result = cls(
                value["tenant_digest"],
                value["trust_domain_digest"],
                value["adapter_digest"],
                value["policy_digest"],
                value["external_state_digest"],
                CheckPurpose(value["purpose"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("validation scope is invalid") from error
        if value["scope_digest"] != result.digest:
            raise ValueError("validation scope digest mismatch")
        return result


@dataclass(frozen=True, slots=True)
class InvalidationReport:
    reusable: bool
    reason: str
    required_check: str


def admit_cached_result(
    result: CachedTestResult | None,
    *,
    stored_scope: ValidationScope,
    requested_scope: ValidationScope,
    live_check: bool = False,
) -> InvalidationReport:
    if not isinstance(stored_scope, ValidationScope) or not isinstance(
        requested_scope, ValidationScope
    ):
        return InvalidationReport(
            False, "validation scope is not authenticated", "run-required-check"
        )
    if result is None:
        return InvalidationReport(
            False, "no matching passing receipt", "run-required-check"
        )
    if result.outcome is not TestOutcome.PASSED:
        return InvalidationReport(
            False, "non-passing receipts are evidence only", "run-required-check"
        )
    if stored_scope.digest != requested_scope.digest:
        return InvalidationReport(
            False,
            "scope, purpose, tenant, adapter, policy, or freshness changed",
            "run-required-check",
        )
    if live_check and (
        requested_scope.external_state_digest is None
        or stored_scope.external_state_digest is None
    ):
        return InvalidationReport(
            False, "live-state freshness is unknown", "run-required-check"
        )
    return InvalidationReport(
        True, "exact candidate and validation scope match", "none"
    )
