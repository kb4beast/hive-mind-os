"""Canonical, inert compiler for subject-neutral portable DAG plans.

The compiler authenticates bytes and produces deterministic dispatch rounds.  It
does not launch workers, import a repository controller, or grant authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from typing import Any, Mapping

from .portable_plan import PortableNode, PortablePlanBundle
from .runtime_contracts import (
    ContractViolation,
    canonical_digest,
    raw_sha256,
    require_digest,
)

STANDARD_VERSION = 2
STANDARD_SOURCE_PATH = "docs/execution/DAG_AUTHORING_STANDARD_V2.md"
COMPILER_PACKAGE_ID = "hive-mind-portable-compiler-v1"
COMPILER_PACKAGE_DESCRIPTOR: Mapping[str, Any] = {
    "algorithm": "canonical-kahn-level-first-fit-v1",
    "canonical_json": "utf8-sorted-compact-v1",
    "conflicts": "resource-capacity-v1",
    "package_id": COMPILER_PACKAGE_ID,
    "plan_schema_version": 1,
    "standard_version": STANDARD_VERSION,
}
COMPILER_PACKAGE_DIGEST = canonical_digest(COMPILER_PACKAGE_DESCRIPTOR)

REQUIRED_ROLES = frozenset(
    {
        "orchestrator",
        "explorer",
        "architect",
        "builder",
        "curator",
        "integrator",
        "steward",
        "optimizer",
    }
)
REQUIRED_LIFECYCLE_STAGES = frozenset(
    {"discover", "design", "build", "validate", "grow", "maintain", "integrate"}
)


@dataclass(frozen=True, slots=True)
class GraphMetrics:
    node_count: int
    raw_edge_count: int
    dependency_level_count: int
    transitive_direct_edge_count: int

    def to_document(self) -> dict[str, int]:
        return {
            "node_count": self.node_count,
            "raw_edge_count": self.raw_edge_count,
            "dependency_level_count": self.dependency_level_count,
            "transitive_direct_edge_count": self.transitive_direct_edge_count,
        }


@dataclass(frozen=True, slots=True)
class DispatchRound:
    round_index: int
    dependency_level: int
    node_ids: tuple[str, ...]
    resource_usage: tuple[tuple[str, int], ...]

    def to_document(self) -> dict[str, Any]:
        return {
            "round_index": self.round_index,
            "dependency_level": self.dependency_level,
            "node_ids": list(self.node_ids),
            "resource_usage": {key: value for key, value in self.resource_usage},
        }


@dataclass(frozen=True, slots=True)
class CompilationReceipt:
    plan_digest: str
    request_id: str
    subject_id: str
    standard_digest: str
    compiler_package_id: str
    compiler_package_digest: str
    maximum_workers: int
    metrics: GraphMetrics
    rounds: tuple[DispatchRound, ...]
    lint_errors: tuple[str, ...] = ()
    lint_warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.lint_errors or self.lint_warnings:
            raise ContractViolation("a compilation receipt cannot contain lint findings")

    def to_document(self) -> dict[str, Any]:
        return {
            "plan_digest": self.plan_digest,
            "request_id": self.request_id,
            "subject_id": self.subject_id,
            "standard_digest": self.standard_digest,
            "compiler_package_id": self.compiler_package_id,
            "compiler_package_digest": self.compiler_package_digest,
            "maximum_workers": self.maximum_workers,
            "metrics": self.metrics.to_document(),
            "rounds": [item.to_document() for item in self.rounds],
            "lint_errors": [],
            "lint_warnings": [],
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())


def git_blob_id(raw: bytes) -> str:
    """Return Git's SHA-1 object id for exact blob bytes."""

    if type(raw) is not bytes:
        raise ContractViolation("Git blob input must be immutable bytes")
    header = f"blob {len(raw)}\0".encode("ascii")
    return sha1(header + raw).hexdigest()


def load_bound_plan(
    plan_bytes: bytes,
    *,
    expected_plan_digest: str,
    standard_bytes: bytes,
    expected_request_id: str | None = None,
    expected_subject_id: str | None = None,
) -> PortablePlanBundle:
    """Parse one canonical plan and authenticate every compiler binding."""

    require_digest(expected_plan_digest, "expected plan digest")
    plan = PortablePlanBundle.from_bytes(plan_bytes)
    if plan_bytes != plan.canonical_bytes():
        raise ContractViolation("portable plan bytes are not in canonical form")
    if plan.digest() != expected_plan_digest:
        raise ContractViolation("portable plan digest does not match caller expectation")
    if expected_request_id is not None:
        require_digest(expected_request_id, "expected request_id")
        if plan.request_id != expected_request_id:
            raise ContractViolation("portable plan request binding is stale or substituted")
    if expected_subject_id is not None:
        require_digest(expected_subject_id, "expected subject_id")
        if plan.subject.subject_id != expected_subject_id:
            raise ContractViolation("portable plan subject binding is stale or substituted")
    if type(standard_bytes) is not bytes:
        raise ContractViolation("standard input must be immutable bytes")
    standard = plan.standard
    if standard.version != STANDARD_VERSION or standard.source_path != STANDARD_SOURCE_PATH:
        raise ContractViolation("portable plan uses an unsupported authoring standard")
    if standard.raw_sha256 != raw_sha256(standard_bytes):
        raise ContractViolation("authoring-standard raw digest mismatch")
    if standard.byte_count != len(standard_bytes):
        raise ContractViolation("authoring-standard byte count mismatch")
    if standard.git_blob != git_blob_id(standard_bytes):
        raise ContractViolation("authoring-standard Git blob mismatch")
    if (
        standard.package_id != COMPILER_PACKAGE_ID
        or standard.package_digest != COMPILER_PACKAGE_DIGEST
    ):
        raise ContractViolation("canonical compiler package identity mismatch")
    _validate_governance_coverage(plan)
    return plan


def _validate_governance_coverage(plan: PortablePlanBundle) -> None:
    roles: set[str] = set()
    stages: set[str] = set()
    for node in plan.nodes:
        unknown_roles = set(node.roles) - REQUIRED_ROLES
        if unknown_roles:
            raise ContractViolation(
                f"node {node.node_id} has unsupported role(s): {', '.join(sorted(unknown_roles))}"
            )
        unknown_stages = set(node.lifecycle_stages) - REQUIRED_LIFECYCLE_STAGES
        if unknown_stages:
            raise ContractViolation(
                f"node {node.node_id} has unsupported lifecycle stage(s): "
                + ", ".join(sorted(unknown_stages))
            )
        if not node.evidence_ids:
            raise ContractViolation(f"node {node.node_id} has no evidence binding")
        roles.update(node.roles)
        stages.update(node.lifecycle_stages)
    missing_roles = REQUIRED_ROLES - roles
    if missing_roles:
        raise ContractViolation(
            "portable plan omits required specialist role(s): "
            + ", ".join(sorted(missing_roles))
        )
    missing_stages = REQUIRED_LIFECYCLE_STAGES - stages
    if missing_stages:
        raise ContractViolation(
            "portable plan omits required lifecycle stage(s): "
            + ", ".join(sorted(missing_stages))
        )


def graph_metrics(plan: PortablePlanBundle) -> GraphMetrics:
    by_id = {node.node_id: node for node in plan.nodes}
    levels = _dependency_levels(by_id)
    transitive = 0
    for node in plan.nodes:
        for dependency in node.dependencies:
            if any(
                dependency in _ancestors(other, by_id)
                for other in node.dependencies
                if other != dependency
            ):
                transitive += 1
    return GraphMetrics(
        node_count=len(plan.nodes),
        raw_edge_count=sum(len(node.dependencies) for node in plan.nodes),
        dependency_level_count=max(levels.values(), default=-1) + 1,
        transitive_direct_edge_count=transitive,
    )


def _ancestors(node_id: str, by_id: Mapping[str, PortableNode]) -> frozenset[str]:
    result: set[str] = set()
    stack = list(by_id[node_id].dependencies)
    while stack:
        current = stack.pop()
        if current not in result:
            result.add(current)
            stack.extend(by_id[current].dependencies)
    return frozenset(result)


def _dependency_levels(by_id: Mapping[str, PortableNode]) -> dict[str, int]:
    levels: dict[str, int] = {}

    def level(node_id: str) -> int:
        if node_id not in levels:
            dependencies = by_id[node_id].dependencies
            levels[node_id] = 0 if not dependencies else 1 + max(level(item) for item in dependencies)
        return levels[node_id]

    for node_id in sorted(by_id):
        level(node_id)
    return levels


def _worker_limit(plan: PortablePlanBundle, requested: int | None) -> int:
    budgets = {item.budget_id: item.policy for item in plan.budgets}
    declared = [budgets[node.budget_id].concurrent_workers for node in plan.nodes]
    if not declared or min(declared) < 1:
        raise ContractViolation("every scheduled node requires a positive worker allowance")
    limit = min(declared)
    if requested is not None:
        if type(requested) is not int or requested < 1:
            raise ContractViolation("maximum_workers must be a positive integer")
        limit = min(limit, requested)
    return limit


def _compile_rounds(
    plan: PortablePlanBundle,
    *,
    maximum_workers: int,
) -> tuple[DispatchRound, ...]:
    by_id = {node.node_id: node for node in plan.nodes}
    levels = _dependency_levels(by_id)
    capacities = {resource.resource_id: resource.quantity for resource in plan.resources}
    result: list[DispatchRound] = []
    for dependency_level in range(max(levels.values(), default=-1) + 1):
        members = sorted(node_id for node_id, value in levels.items() if value == dependency_level)
        batches: list[list[str]] = []
        usages: list[dict[str, int]] = []
        for node_id in members:
            node = by_id[node_id]
            if any(capacities[resource_id] < 1 for resource_id in node.resource_ids):
                raise ContractViolation(f"node {node_id} requires an unavailable resource")
            placed = False
            for batch, usage in zip(batches, usages, strict=True):
                if len(batch) >= maximum_workers:
                    continue
                if any(usage.get(resource_id, 0) + 1 > capacities[resource_id] for resource_id in node.resource_ids):
                    continue
                batch.append(node_id)
                for resource_id in node.resource_ids:
                    usage[resource_id] = usage.get(resource_id, 0) + 1
                placed = True
                break
            if not placed:
                batches.append([node_id])
                usages.append({resource_id: 1 for resource_id in node.resource_ids})
        for batch, usage in zip(batches, usages, strict=True):
            result.append(
                DispatchRound(
                    round_index=len(result),
                    dependency_level=dependency_level,
                    node_ids=tuple(batch),
                    resource_usage=tuple(sorted(usage.items())),
                )
            )
    return tuple(result)


def compile_plan(
    plan_bytes: bytes,
    *,
    expected_plan_digest: str,
    standard_bytes: bytes,
    expected_request_id: str | None = None,
    expected_subject_id: str | None = None,
    maximum_workers: int | None = None,
) -> CompilationReceipt:
    """Authenticate and compile one plan without performing any host effect."""

    plan = load_bound_plan(
        plan_bytes,
        expected_plan_digest=expected_plan_digest,
        standard_bytes=standard_bytes,
        expected_request_id=expected_request_id,
        expected_subject_id=expected_subject_id,
    )
    worker_limit = _worker_limit(plan, maximum_workers)
    rounds = _compile_rounds(plan, maximum_workers=worker_limit)
    return CompilationReceipt(
        plan_digest=plan.digest(),
        request_id=plan.request_id,
        subject_id=plan.subject.subject_id,
        standard_digest=plan.standard.raw_sha256,
        compiler_package_id=COMPILER_PACKAGE_ID,
        compiler_package_digest=COMPILER_PACKAGE_DIGEST,
        maximum_workers=worker_limit,
        metrics=graph_metrics(plan),
        rounds=rounds,
    )


__all__ = [
    "COMPILER_PACKAGE_DESCRIPTOR",
    "COMPILER_PACKAGE_DIGEST",
    "COMPILER_PACKAGE_ID",
    "CompilationReceipt",
    "DispatchRound",
    "GraphMetrics",
    "REQUIRED_LIFECYCLE_STAGES",
    "REQUIRED_ROLES",
    "STANDARD_SOURCE_PATH",
    "STANDARD_VERSION",
    "compile_plan",
    "git_blob_id",
    "graph_metrics",
    "load_bound_plan",
]
