"""Typed, subject-neutral portable plan data.

Portable plans are inert proposals.  They describe needs and policy bindings but
cannot authenticate a host or authorize an effect.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping

from .runtime_contracts import (
    AdapterRequirement,
    AuthorityEnvelope,
    BudgetPolicy,
    CapabilityRequirement,
    ContractViolation,
    EvidenceReference,
    IntegrationPolicy,
    RecoveryPolicy,
    ResourceRequirement,
    TokenPolicy,
    _closed,
    canonical_digest,
    canonical_json_bytes,
    portable_path,
    require_digest,
    require_identifier,
    require_time,
    requires_external_authority,
    strict_json_object,
)

_GIT_OBJECT = re.compile(r"[0-9a-f]{40}\Z")


class SubjectKind(StrEnum):
    REPOSITORY = "repository"
    NON_REPOSITORY = "non_repository"


@dataclass(frozen=True, slots=True)
class StandardBinding:
    version: int
    source_path: str
    raw_sha256: str
    byte_count: int
    git_blob: str
    package_id: str
    package_digest: str

    def __post_init__(self) -> None:
        if type(self.version) is not int or self.version < 1:
            raise ContractViolation("standard version must be a positive integer")
        if portable_path(self.source_path) != self.source_path:
            raise ContractViolation(
                "standard source_path must use normalized POSIX spelling"
            )
        require_digest(self.raw_sha256, "standard raw_sha256")
        if type(self.byte_count) is not int or self.byte_count < 1:
            raise ContractViolation("standard byte_count must be positive")
        if _GIT_OBJECT.fullmatch(self.git_blob) is None:
            raise ContractViolation("standard git_blob must be lowercase 40-hex")
        require_identifier(self.package_id, "standard package_id")
        require_digest(self.package_digest, "standard package_digest")

    def to_document(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "source_path": self.source_path,
            "raw_sha256": self.raw_sha256,
            "byte_count": self.byte_count,
            "git_blob": self.git_blob,
            "package_id": self.package_id,
            "package_digest": self.package_digest,
        }


@dataclass(frozen=True, slots=True)
class RepositorySubject:
    repository_id: str
    commit: str
    tree: str
    target_branch: str

    def __post_init__(self) -> None:
        require_digest(self.repository_id, "repository_id")
        if (
            _GIT_OBJECT.fullmatch(self.commit) is None
            or _GIT_OBJECT.fullmatch(self.tree) is None
        ):
            raise ContractViolation(
                "repository subject requires lowercase 40-hex commit and tree"
            )
        if type(self.target_branch) is not str or not self.target_branch:
            raise ContractViolation("repository target_branch is required")

    def to_document(self) -> dict[str, str]:
        return {
            "repository_id": self.repository_id,
            "commit": self.commit,
            "tree": self.tree,
            "target_branch": self.target_branch,
        }


@dataclass(frozen=True, slots=True)
class NonRepositorySubject:
    subject_type: str
    locator_digest: str
    version_digest: str

    def __post_init__(self) -> None:
        require_identifier(self.subject_type, "subject_type")
        require_digest(self.locator_digest, "locator_digest")
        require_digest(self.version_digest, "version_digest")

    def to_document(self) -> dict[str, str]:
        return {
            "subject_type": self.subject_type,
            "locator_digest": self.locator_digest,
            "version_digest": self.version_digest,
        }


@dataclass(frozen=True, slots=True)
class SubjectBinding:
    kind: SubjectKind
    subject_id: str
    repository: RepositorySubject | None
    non_repository: NonRepositorySubject | None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SubjectKind):
            raise ContractViolation("subject kind must be typed")
        require_digest(self.subject_id, "subject_id")
        if self.kind is SubjectKind.REPOSITORY:
            if self.repository is None or self.non_repository is not None:
                raise ContractViolation(
                    "repository subject must have only repository binding"
                )
            payload: RepositorySubject | NonRepositorySubject = self.repository
        else:
            if self.non_repository is None or self.repository is not None:
                raise ContractViolation(
                    "non-repository subject must have only non_repository binding"
                )
            payload = self.non_repository
        expected = canonical_digest(
            {"kind": self.kind.value, "binding": payload.to_document()}
        )
        if self.subject_id != expected:
            raise ContractViolation(
                "subject_id does not authenticate the typed subject binding"
            )

    @classmethod
    def for_repository(cls, repository: RepositorySubject) -> "SubjectBinding":
        subject_id = canonical_digest(
            {"kind": SubjectKind.REPOSITORY.value, "binding": repository.to_document()}
        )
        return cls(SubjectKind.REPOSITORY, subject_id, repository, None)

    @classmethod
    def for_non_repository(cls, subject: NonRepositorySubject) -> "SubjectBinding":
        subject_id = canonical_digest(
            {"kind": SubjectKind.NON_REPOSITORY.value, "binding": subject.to_document()}
        )
        return cls(SubjectKind.NON_REPOSITORY, subject_id, None, subject)

    def to_document(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "subject_id": self.subject_id,
            "repository": None
            if self.repository is None
            else self.repository.to_document(),
            "non_repository": None
            if self.non_repository is None
            else self.non_repository.to_document(),
        }


@dataclass(frozen=True, slots=True)
class BudgetAllocation:
    budget_id: str
    policy: BudgetPolicy

    def __post_init__(self) -> None:
        require_identifier(self.budget_id, "budget_id")
        if not isinstance(self.policy, BudgetPolicy):
            raise ContractViolation("budget allocation requires a typed policy")

    def to_document(self) -> dict[str, Any]:
        return {"budget_id": self.budget_id, "policy": self.policy.to_document()}


@dataclass(frozen=True, slots=True)
class PortableNode:
    node_id: str
    objective: str
    dependencies: tuple[str, ...]
    resource_ids: tuple[str, ...]
    capability_ids: tuple[str, ...]
    adapter_ids: tuple[str, ...]
    authority_id: str
    budget_id: str
    evidence_ids: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    rollback: str
    roles: tuple[str, ...]
    lifecycle_stages: tuple[str, ...]

    def __post_init__(self) -> None:
        require_identifier(self.node_id, "node_id")
        if type(self.objective) is not str or not self.objective:
            raise ContractViolation("portable node objective is required")
        for name in (
            "dependencies",
            "resource_ids",
            "capability_ids",
            "adapter_ids",
            "evidence_ids",
            "acceptance_criteria",
            "roles",
            "lifecycle_stages",
        ):
            values = getattr(self, name)
            if type(values) is not tuple or any(
                type(value) is not str or not value for value in values
            ):
                raise ContractViolation(f"{name} must contain strings")
            if len(set(values)) != len(values):
                raise ContractViolation(f"{name} contains duplicates")
        if self.node_id in self.dependencies:
            raise ContractViolation("portable node cannot depend on itself")
        require_identifier(self.authority_id, "node authority_id")
        require_identifier(self.budget_id, "node budget_id")
        if not self.acceptance_criteria:
            raise ContractViolation("portable node acceptance_criteria are required")
        if type(self.rollback) is not str or not self.rollback:
            raise ContractViolation("portable node rollback is required")
        if not self.roles or not self.lifecycle_stages:
            raise ContractViolation(
                "portable node roles and lifecycle_stages are required"
            )

    def to_document(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "objective": self.objective,
            "dependencies": list(self.dependencies),
            "resource_ids": list(self.resource_ids),
            "capability_ids": list(self.capability_ids),
            "adapter_ids": list(self.adapter_ids),
            "authority_id": self.authority_id,
            "budget_id": self.budget_id,
            "evidence_ids": list(self.evidence_ids),
            "acceptance_criteria": list(self.acceptance_criteria),
            "rollback": self.rollback,
            "roles": list(self.roles),
            "lifecycle_stages": list(self.lifecycle_stages),
        }


@dataclass(frozen=True, slots=True)
class PortablePlanBundle:
    schema_version: int
    plan_id: str
    request_id: str
    objective_digest: str
    subject: SubjectBinding
    standard: StandardBinding
    resources: tuple[ResourceRequirement, ...]
    capabilities: tuple[CapabilityRequirement, ...]
    adapters: tuple[AdapterRequirement, ...]
    authority: tuple[AuthorityEnvelope, ...]
    budgets: tuple[BudgetAllocation, ...]
    recovery: RecoveryPolicy
    integration: IntegrationPolicy
    token_policy: TokenPolicy
    evidence: tuple[EvidenceReference, ...]
    nodes: tuple[PortableNode, ...]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ContractViolation("unsupported portable-plan schema version")
        require_identifier(self.plan_id, "plan_id")
        require_digest(self.request_id, "request_id")
        require_digest(self.objective_digest, "objective_digest")
        if not isinstance(self.subject, SubjectBinding):
            raise ContractViolation("portable plan requires a typed subject")
        if not isinstance(self.standard, StandardBinding):
            raise ContractViolation("portable plan requires a typed standard binding")
        inventories: tuple[tuple[str, tuple[Any, ...], str], ...] = (
            ("resource_id", self.resources, "resources"),
            ("capability_id", self.capabilities, "capabilities"),
            ("adapter_id", self.adapters, "adapters"),
            ("authority_id", self.authority, "authority"),
            ("budget_id", self.budgets, "budgets"),
            ("evidence_id", self.evidence, "evidence"),
            ("node_id", self.nodes, "nodes"),
        )
        ids: dict[str, set[str]] = {}
        for attribute, values, label in inventories:
            observed = [getattr(value, attribute) for value in values]
            if len(set(observed)) != len(observed):
                raise ContractViolation(f"portable plan {label} contain duplicate ids")
            ids[label] = set(observed)
        if not self.nodes:
            raise ContractViolation("portable plan requires at least one node")
        for capability in self.capabilities:
            if (
                capability.adapter_id not in ids["adapters"]
                or capability.authority_id not in ids["authority"]
            ):
                raise ContractViolation(
                    "capability refers to an unknown adapter or authority"
                )
        by_node = {node.node_id: node for node in self.nodes}
        for node in self.nodes:
            checks = (
                (node.resource_ids, ids["resources"], "resource"),
                (node.capability_ids, ids["capabilities"], "capability"),
                (node.adapter_ids, ids["adapters"], "adapter"),
                (node.evidence_ids, ids["evidence"], "evidence"),
            )
            for references, inventory, label in checks:
                if not set(references) <= inventory:
                    raise ContractViolation(
                        f"node {node.node_id} refers to an unknown {label}"
                    )
            if (
                node.authority_id not in ids["authority"]
                or node.budget_id not in ids["budgets"]
            ):
                raise ContractViolation(
                    f"node {node.node_id} refers to unknown authority or budget"
                )
            if not set(node.dependencies) <= set(by_node):
                raise ContractViolation(
                    f"node {node.node_id} has an unknown dependency"
                )
        self._validate_acyclic(by_node)

    @staticmethod
    def _validate_acyclic(by_node: Mapping[str, PortableNode]) -> None:
        permanent: set[str] = set()
        temporary: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in permanent:
                return
            if node_id in temporary:
                raise ContractViolation(
                    "portable plan dependency graph contains a cycle"
                )
            temporary.add(node_id)
            for dependency in by_node[node_id].dependencies:
                visit(dependency)
            temporary.remove(node_id)
            permanent.add(node_id)

        for node_id in by_node:
            visit(node_id)

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "request_id": self.request_id,
            "objective_digest": self.objective_digest,
            "subject": self.subject.to_document(),
            "standard": self.standard.to_document(),
            "resources": [item.to_document() for item in self.resources],
            "capabilities": [item.to_document() for item in self.capabilities],
            "adapters": [item.to_document() for item in self.adapters],
            "authority": [item.to_document() for item in self.authority],
            "budgets": [item.to_document() for item in self.budgets],
            "recovery": self.recovery.to_document(),
            "integration": self.integration.to_document(),
            "token_policy": self.token_policy.to_document(),
            "evidence": [item.to_document() for item in self.evidence],
            "nodes": [item.to_document() for item in self.nodes],
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_document())

    def digest(self) -> str:
        return canonical_digest(self.to_document())

    @classmethod
    def from_bytes(cls, raw: bytes) -> "PortablePlanBundle":
        return cls.from_document(strict_json_object(raw))

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "PortablePlanBundle":
        fields = {
            "schema_version",
            "plan_id",
            "request_id",
            "objective_digest",
            "subject",
            "standard",
            "resources",
            "capabilities",
            "adapters",
            "authority",
            "budgets",
            "recovery",
            "integration",
            "token_policy",
            "evidence",
            "nodes",
        }
        _closed(document, fields, "portable plan")
        for name in (
            "resources",
            "capabilities",
            "adapters",
            "authority",
            "budgets",
            "evidence",
            "nodes",
        ):
            if not isinstance(document[name], list) or any(
                not isinstance(item, Mapping) for item in document[name]
            ):
                raise ContractViolation(f"portable plan {name} must be an object list")
        subject = _subject_from_document(document["subject"])
        standard = _standard_from_document(document["standard"])
        return cls(
            schema_version=document["schema_version"],
            plan_id=document["plan_id"],
            request_id=document["request_id"],
            objective_digest=document["objective_digest"],
            subject=subject,
            standard=standard,
            resources=tuple(
                _resource_from_document(item) for item in document["resources"]
            ),
            capabilities=tuple(
                _capability_from_document(item) for item in document["capabilities"]
            ),
            adapters=tuple(
                _adapter_from_document(item) for item in document["adapters"]
            ),
            authority=tuple(
                _authority_from_document(item) for item in document["authority"]
            ),
            budgets=tuple(
                _budget_allocation_from_document(item) for item in document["budgets"]
            ),
            recovery=_recovery_from_document(document["recovery"]),
            integration=_integration_from_document(document["integration"]),
            token_policy=_token_from_document(document["token_policy"]),
            evidence=tuple(
                _evidence_from_document(item) for item in document["evidence"]
            ),
            nodes=tuple(_node_from_document(item) for item in document["nodes"]),
        )


def _string_list(document: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = document[key]
    if not isinstance(value, list) or any(type(item) is not str for item in value):
        raise ContractViolation(f"{key} must be a string list")
    return tuple(value)


def _standard_from_document(value: Any) -> StandardBinding:
    if not isinstance(value, Mapping):
        raise ContractViolation("standard binding must be an object")
    fields = {
        "version",
        "source_path",
        "raw_sha256",
        "byte_count",
        "git_blob",
        "package_id",
        "package_digest",
    }
    _closed(value, fields, "standard binding")
    return StandardBinding(**value)


def _subject_from_document(value: Any) -> SubjectBinding:
    fields = {"kind", "subject_id", "repository", "non_repository"}
    if not isinstance(value, Mapping):
        raise ContractViolation("subject must be an object")
    _closed(value, fields, "subject")
    try:
        kind = SubjectKind(value["kind"])
    except (TypeError, ValueError) as error:
        raise ContractViolation("unsupported subject kind") from error
    repository = None
    non_repository = None
    if value["repository"] is not None:
        item = value["repository"]
        if not isinstance(item, Mapping):
            raise ContractViolation("repository binding must be an object")
        _closed(
            item,
            {"repository_id", "commit", "tree", "target_branch"},
            "repository binding",
        )
        repository = RepositorySubject(**item)
    if value["non_repository"] is not None:
        item = value["non_repository"]
        if not isinstance(item, Mapping):
            raise ContractViolation("non_repository binding must be an object")
        _closed(
            item,
            {"subject_type", "locator_digest", "version_digest"},
            "non_repository binding",
        )
        non_repository = NonRepositorySubject(**item)
    return SubjectBinding(kind, value["subject_id"], repository, non_repository)


def _resource_from_document(value: Mapping[str, Any]) -> ResourceRequirement:
    _closed(
        value, {"resource_id", "kind", "quantity", "unit", "constraints"}, "resource"
    )
    return ResourceRequirement(
        value["resource_id"],
        value["kind"],
        value["quantity"],
        value["unit"],
        _string_list(value, "constraints"),
    )


def _capability_from_document(value: Mapping[str, Any]) -> CapabilityRequirement:
    fields = {
        "capability_id",
        "operation",
        "effect_class",
        "authority_id",
        "adapter_id",
    }
    _closed(value, fields, "capability")
    return CapabilityRequirement(**value)


def _adapter_from_document(value: Mapping[str, Any]) -> AdapterRequirement:
    fields = {"adapter_id", "interface", "version", "configuration_digest"}
    _closed(value, fields, "adapter")
    return AdapterRequirement(**value)


def _authority_from_document(value: Mapping[str, Any]) -> AuthorityEnvelope:
    fields = {
        "authority_id",
        "principal_id",
        "grant_digest",
        "allowed_actions",
        "denied_actions",
        "expires_at",
        "external_effects",
    }
    _closed(value, fields, "authority")
    return AuthorityEnvelope(
        value["authority_id"],
        value["principal_id"],
        value["grant_digest"],
        _string_list(value, "allowed_actions"),
        _string_list(value, "denied_actions"),
        value["expires_at"],
        value["external_effects"],
    )


def _budget_from_document(value: Mapping[str, Any]) -> BudgetPolicy:
    fields = {
        "wall_seconds",
        "model_calls",
        "input_tokens",
        "output_tokens",
        "cost_microunits",
        "tool_calls",
        "concurrent_workers",
    }
    _closed(value, fields, "budget policy")
    return BudgetPolicy(**value)


def _budget_allocation_from_document(value: Mapping[str, Any]) -> BudgetAllocation:
    _closed(value, {"budget_id", "policy"}, "budget allocation")
    if not isinstance(value["policy"], Mapping):
        raise ContractViolation("budget policy must be an object")
    return BudgetAllocation(value["budget_id"], _budget_from_document(value["policy"]))


def _recovery_from_document(value: Any) -> RecoveryPolicy:
    if not isinstance(value, Mapping):
        raise ContractViolation("recovery policy must be an object")
    fields = {
        "maximum_attempts",
        "checkpoint_required",
        "rollback_required",
        "stop_conditions",
    }
    _closed(value, fields, "recovery policy")
    return RecoveryPolicy(
        value["maximum_attempts"],
        value["checkpoint_required"],
        value["rollback_required"],
        _string_list(value, "stop_conditions"),
    )


def _integration_from_document(value: Any) -> IntegrationPolicy:
    if not isinstance(value, Mapping):
        raise ContractViolation("integration policy must be an object")
    fields = {
        "strategy",
        "target",
        "expected_base",
        "compare_and_swap",
        "protected_target",
    }
    _closed(value, fields, "integration policy")
    return IntegrationPolicy(**value)


def _token_from_document(value: Any) -> TokenPolicy:
    if not isinstance(value, Mapping):
        raise ContractViolation("token policy must be an object")
    fields = {
        "context_tokens",
        "response_tokens",
        "reserve_tokens",
        "accounting",
        "overflow",
    }
    _closed(value, fields, "token policy")
    return TokenPolicy(**value)


def _evidence_from_document(value: Mapping[str, Any]) -> EvidenceReference:
    fields = {"evidence_id", "digest", "source", "claim_ids", "observed_at"}
    _closed(value, fields, "evidence reference")
    return EvidenceReference(
        value["evidence_id"],
        value["digest"],
        value["source"],
        _string_list(value, "claim_ids"),
        value["observed_at"],
    )


def _node_from_document(value: Mapping[str, Any]) -> PortableNode:
    fields = {
        "node_id",
        "objective",
        "dependencies",
        "resource_ids",
        "capability_ids",
        "adapter_ids",
        "authority_id",
        "budget_id",
        "evidence_ids",
        "acceptance_criteria",
        "rollback",
        "roles",
        "lifecycle_stages",
    }
    _closed(value, fields, "portable node")
    return PortableNode(
        value["node_id"],
        value["objective"],
        _string_list(value, "dependencies"),
        _string_list(value, "resource_ids"),
        _string_list(value, "capability_ids"),
        _string_list(value, "adapter_ids"),
        value["authority_id"],
        value["budget_id"],
        _string_list(value, "evidence_ids"),
        _string_list(value, "acceptance_criteria"),
        value["rollback"],
        _string_list(value, "roles"),
        _string_list(value, "lifecycle_stages"),
    )


def validate_activation_plan_binding(
    plan: PortablePlanBundle,
    *,
    request_sha256: str,
    repository_id: str,
    candidate_parent_commit: str,
    candidate_parent_tree: str,
    target_branch: str,
) -> None:
    """Cross-bind a portable plan to the repository-scoped V2 activation.

    The current activation contract carries repository parent and target
    claims, but no typed non-repository subject identity.  It therefore cannot
    authorize a non-repository plan; such execution requires a future
    activation version with an explicit subject binding.
    """

    if not isinstance(plan, PortablePlanBundle):
        raise ContractViolation("activation binding requires a typed plan")
    require_digest(request_sha256, "activation request_sha256")
    require_digest(repository_id, "activation repository_id")
    if plan.request_id != request_sha256:
        raise ContractViolation("plan request differs from the activation")
    if plan.subject.kind is not SubjectKind.REPOSITORY:
        raise ContractViolation(
            "repository-scoped activation cannot authorize a non-repository plan"
        )
    repository = plan.subject.repository
    assert repository is not None
    if repository.repository_id != repository_id:
        raise ContractViolation("plan repository differs from the activation")
    if repository.commit != candidate_parent_commit:
        raise ContractViolation("plan base commit differs from the activation")
    if repository.tree != candidate_parent_tree:
        raise ContractViolation("plan base tree differs from the activation")
    if repository.target_branch != target_branch:
        raise ContractViolation("plan target branch differs from the activation")


def validate_runtime_plan_admission(
    plan: PortablePlanBundle,
    *,
    execution_deadline: datetime,
) -> tuple[bool, tuple[str, ...]]:
    """Validate the authority and static budget needed at an effect boundary.

    The returned flag records whether any admitted capability is external; the
    tuple is the exact operation vocabulary the host must possess.  Generation
    metadata is deliberately absent because it is provenance, not authority.
    """

    if not isinstance(plan, PortablePlanBundle):
        raise ContractViolation("runtime admission requires a typed plan")
    if (
        not isinstance(execution_deadline, datetime)
        or execution_deadline.tzinfo is None
        or execution_deadline.utcoffset() is None
    ):
        raise ContractViolation("runtime execution deadline must be timezone-aware")
    authorities = {item.authority_id: item for item in plan.authority}
    capabilities = {item.capability_id: item for item in plan.capabilities}
    budgets = {item.budget_id: item.policy for item in plan.budgets}
    external_effects_required = False
    required_capabilities: set[str] = set()
    for node in plan.nodes:
        try:
            authority = authorities[node.authority_id]
            budget = budgets[node.budget_id]
        except KeyError as error:
            raise ContractViolation(
                f"{node.node_id} refers to an unavailable authority or budget"
            ) from error
        if require_time(authority.expires_at, "authority expiry") < execution_deadline:
            raise ContractViolation(
                f"{node.node_id} authority expires before the execution deadline"
            )
        if budget.wall_seconds < 1 or budget.tool_calls < len(node.capability_ids):
            raise ContractViolation(
                f"{node.node_id} has insufficient static wall/tool budget"
            )
        for capability_id in node.capability_ids:
            try:
                capability = capabilities[capability_id]
            except KeyError as error:
                raise ContractViolation(
                    f"{node.node_id} refers to an unavailable capability"
                ) from error
            if (
                capability.authority_id != node.authority_id
                or capability.adapter_id not in node.adapter_ids
                or capability.operation not in authority.allowed_actions
                or capability.operation in authority.denied_actions
            ):
                raise ContractViolation(
                    f"{node.node_id} capability is not explicitly granted"
                )
            if capability.operation in {"merge", "protected-merge"}:
                raise ContractViolation("protected merge is never delegated")
            if requires_external_authority(capability.effect_class):
                external_effects_required = True
                if not authority.external_effects:
                    raise ContractViolation(
                        f"{node.node_id} external effect lacks external-effect authority"
                    )
            required_capabilities.add(capability.operation)
    return external_effects_required, tuple(sorted(required_capabilities))


__all__ = [
    "BudgetAllocation",
    "NonRepositorySubject",
    "PortableNode",
    "PortablePlanBundle",
    "RepositorySubject",
    "StandardBinding",
    "SubjectBinding",
    "SubjectKind",
    "validate_activation_plan_binding",
    "validate_runtime_plan_admission",
]
