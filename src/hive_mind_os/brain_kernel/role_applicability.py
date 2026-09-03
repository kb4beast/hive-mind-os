"""Deterministic role applicability and dependency-context routing.

Applicability is evidence about how a canonical lifecycle role is discharged;
it is never permission to remove that role from the lifecycle.  This module is
pure and deliberately has no provider, filesystem, or effect dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping, Sequence

from .canonical import canonical_digest
from .roles import KERNEL_IMPLEMENTED_ROLES, RoleProtocolError


class ApplicabilityDenied(RoleProtocolError):
    """A disposition would weaken lifecycle accountability."""


class RoleDisposition(StrEnum):
    MODEL_EXECUTE = "model_execute"
    DETERMINISTIC_CHECK = "deterministic_check"
    NOT_APPLICABLE = "not_applicable"
    DEFERRED = "deferred"
    BLOCKED = "blocked"


class TaskArchetype(StrEnum):
    DOC_ONLY = "doc_only"
    TEST_ONLY = "test_only"
    SINGLE_MODULE_CHANGE = "single_module_change"
    MULTI_MODULE_CHANGE = "multi_module_change"
    EXTERNAL_EFFECT = "external_effect"
    INVESTIGATION = "investigation"


_DOC_SUFFIXES = (".md", ".mdx", ".rst", ".txt", ".adoc")


def _nonempty_unique(values: tuple[str, ...], label: str) -> None:
    if not values or any(not isinstance(value, str) or not value.strip() for value in values):
        raise ApplicabilityDenied(f"{label} requires non-empty string values")
    if len(set(values)) != len(values):
        raise ApplicabilityDenied(f"{label} must not contain duplicates")


@dataclass(frozen=True, slots=True)
class ArchetypeSignals:
    """Observable facts used to select a task archetype, with evidence."""

    write_scope: tuple[str, ...]
    performs_external_effect: bool
    asserts_recovery: bool
    acceptance_count: int
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _nonempty_unique(self.evidence_refs, "archetype evidence_refs")
        if not isinstance(self.performs_external_effect, bool) or not isinstance(
            self.asserts_recovery, bool
        ):
            raise ApplicabilityDenied("archetype effect and recovery signals must be boolean")
        if self.write_scope != tuple(sorted(set(self.write_scope))):
            raise ApplicabilityDenied("write_scope must be sorted and unique")
        if any(not isinstance(path, str) or not path.strip() for path in self.write_scope):
            raise ApplicabilityDenied("write_scope paths must be non-empty strings")
        if not isinstance(self.acceptance_count, int) or isinstance(self.acceptance_count, bool):
            raise ApplicabilityDenied("acceptance_count must be an integer")
        if self.acceptance_count < 1:
            raise ApplicabilityDenied("at least one acceptance criterion is required")

    @property
    def archetype(self) -> TaskArchetype:
        if self.performs_external_effect:
            return TaskArchetype.EXTERNAL_EFFECT
        if not self.write_scope:
            return TaskArchetype.INVESTIGATION
        lowered = tuple(path.replace("\\", "/").casefold() for path in self.write_scope)
        if all(path.endswith(_DOC_SUFFIXES) for path in lowered):
            return TaskArchetype.DOC_ONLY
        if all(
            path.startswith("tests/")
            or "/tests/" in f"/{path}"
            or path.startswith(".autopilot/tests/")
            or path.rsplit("/", 1)[-1].startswith("test_")
            for path in lowered
        ):
            return TaskArchetype.TEST_ONLY
        if len(self.write_scope) == 1:
            return TaskArchetype.SINGLE_MODULE_CHANGE
        return TaskArchetype.MULTI_MODULE_CHANGE


@dataclass(frozen=True, slots=True)
class RoleDispositionRecord:
    role: str
    disposition: RoleDisposition
    rationale: str
    evidence_refs: tuple[str, ...]
    trigger: str | None = None
    blocking_reason: str | None = None

    def __post_init__(self) -> None:
        if self.role not in KERNEL_IMPLEMENTED_ROLES:
            raise ApplicabilityDenied("disposition role is not canonical")
        if not isinstance(self.disposition, RoleDisposition):
            try:
                object.__setattr__(self, "disposition", RoleDisposition(self.disposition))
            except (TypeError, ValueError) as error:
                raise ApplicabilityDenied("role disposition is unknown") from error
        if not isinstance(self.rationale, str) or not self.rationale.strip():
            raise ApplicabilityDenied("role disposition requires a rationale")
        _nonempty_unique(self.evidence_refs, "role disposition evidence_refs")
        if self.disposition is RoleDisposition.DEFERRED:
            if not isinstance(self.trigger, str) or not self.trigger.strip():
                raise ApplicabilityDenied("a deferred role requires a named trigger")
        elif self.trigger is not None:
            raise ApplicabilityDenied("only a deferred role may carry a trigger")
        if self.disposition is RoleDisposition.BLOCKED:
            if not isinstance(self.blocking_reason, str) or not self.blocking_reason.strip():
                raise ApplicabilityDenied("a blocked role requires a blocking reason")
        elif self.blocking_reason is not None:
            raise ApplicabilityDenied("only a blocked role may carry a blocking reason")

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "role": self.role,
                "disposition": self.disposition.value,
                "rationale": self.rationale,
                "evidence_refs": self.evidence_refs,
                "trigger": self.trigger,
                "blocking_reason": self.blocking_reason,
            }
        )


@dataclass(frozen=True, slots=True)
class ApplicabilityPolicy:
    """Closed, immutable archetype-to-role disposition table."""

    table: Mapping[str, Mapping[str, RoleDisposition]]

    def __post_init__(self) -> None:
        expected_archetypes = {item.value for item in TaskArchetype}
        if set(self.table) != expected_archetypes:
            raise ApplicabilityDenied("policy must cover every task archetype exactly once")
        normalized: dict[str, Mapping[str, RoleDisposition]] = {}
        for archetype in sorted(expected_archetypes):
            row = self.table[archetype]
            if set(row) != set(KERNEL_IMPLEMENTED_ROLES):
                raise ApplicabilityDenied(
                    f"policy row {archetype!r} must cover every canonical role"
                )
            converted: dict[str, RoleDisposition] = {}
            for role in KERNEL_IMPLEMENTED_ROLES:
                try:
                    converted[role] = RoleDisposition(row[role])
                except (TypeError, ValueError) as error:
                    raise ApplicabilityDenied(
                        f"policy row {archetype!r} has an unknown disposition"
                    ) from error
            if converted["curator"] is RoleDisposition.NOT_APPLICABLE:
                raise ApplicabilityDenied("curator may never be not applicable")
            normalized[archetype] = MappingProxyType(converted)
        object.__setattr__(self, "table", MappingProxyType(normalized))

    @property
    def policy_digest(self) -> str:
        return canonical_digest(
            {
                archetype: {
                    role: row[role].value for role in KERNEL_IMPLEMENTED_ROLES
                }
                for archetype, row in sorted(self.table.items())
            }
        )


def _row(*values: RoleDisposition) -> dict[str, RoleDisposition]:
    if len(values) != len(KERNEL_IMPLEMENTED_ROLES):
        raise ApplicabilityDenied("internal applicability row has the wrong role count")
    return dict(zip(KERNEL_IMPLEMENTED_ROLES, values, strict=True))


_D = RoleDisposition.DETERMINISTIC_CHECK
_M = RoleDisposition.MODEL_EXECUTE
_N = RoleDisposition.NOT_APPLICABLE

DEFAULT_APPLICABILITY_POLICY = ApplicabilityPolicy(
    {
        TaskArchetype.DOC_ONLY.value: _row(_D, _D, _N, _M, _M, _D, _D, _D),
        TaskArchetype.TEST_ONLY.value: _row(_D, _D, _D, _M, _M, _D, _D, _D),
        TaskArchetype.SINGLE_MODULE_CHANGE.value: _row(
            _D, _M, _D, _M, _M, _D, _D, _D
        ),
        TaskArchetype.MULTI_MODULE_CHANGE.value: _row(*((_M,) * 8)),
        TaskArchetype.EXTERNAL_EFFECT.value: _row(*((_M,) * 8)),
        TaskArchetype.INVESTIGATION.value: _row(_D, _M, _N, _N, _M, _D, _D, _D),
    }
)


def resolve_dispositions(
    signals: ArchetypeSignals,
    *,
    policy: ApplicabilityPolicy = DEFAULT_APPLICABILITY_POLICY,
) -> tuple[RoleDispositionRecord, ...]:
    """Resolve all eight roles in lifecycle order without silently skipping one."""

    archetype = signals.archetype
    row = policy.table[archetype.value]
    records = tuple(
        RoleDispositionRecord(
            role=role,
            disposition=row[role],
            rationale=(
                f"policy {policy.policy_digest} resolves {archetype.value}/{role} "
                f"as {row[role].value}"
            ),
            evidence_refs=signals.evidence_refs,
        )
        for role in KERNEL_IMPLEMENTED_ROLES
    )
    if tuple(record.role for record in records) != KERNEL_IMPLEMENTED_ROLES:
        raise ApplicabilityDenied("applicability did not preserve lifecycle order")
    if records[KERNEL_IMPLEMENTED_ROLES.index("curator")].disposition is RoleDisposition.NOT_APPLICABLE:
        raise ApplicabilityDenied("curator may never be not applicable")
    if signals.performs_external_effect:
        for role in ("integrator", "steward"):
            if records[KERNEL_IMPLEMENTED_ROLES.index(role)].disposition is RoleDisposition.NOT_APPLICABLE:
                raise ApplicabilityDenied(
                    f"external effects require accountable {role} disposition"
                )
    if signals.asserts_recovery:
        steward = records[KERNEL_IMPLEMENTED_ROLES.index("steward")]
        if steward.disposition is RoleDisposition.NOT_APPLICABLE:
            raise ApplicabilityDenied("recovery claims require steward accountability")
    return records


ROLE_DEPENDENCIES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "orchestrator": (),
        "explorer": ("orchestrator",),
        "architect": ("explorer",),
        "builder": ("architect",),
        "curator": ("builder",),
        "integrator": ("curator",),
        "steward": ("integrator",),
        "optimizer": ("steward",),
    }
)


class ContextTier(StrEnum):
    FULL = "full"
    DIGEST = "digest"
    OMITTED = "omitted"


def _validate_role_dependencies() -> None:
    roles = set(KERNEL_IMPLEMENTED_ROLES)
    if set(ROLE_DEPENDENCIES) != roles:
        raise ApplicabilityDenied("role dependency graph must cover canonical roles")
    if any(dependency not in roles for values in ROLE_DEPENDENCIES.values() for dependency in values):
        raise ApplicabilityDenied("role dependency graph refers to an unknown role")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(role: str) -> None:
        if role in visiting:
            raise ApplicabilityDenied("role dependency graph must be acyclic")
        if role in visited:
            return
        visiting.add(role)
        for dependency in ROLE_DEPENDENCIES[role]:
            visit(dependency)
        visiting.remove(role)
        visited.add(role)

    for role in KERNEL_IMPLEMENTED_ROLES:
        visit(role)


_validate_role_dependencies()


def _transitive_dependencies(role: str) -> set[str]:
    found: set[str] = set()
    pending = list(ROLE_DEPENDENCIES[role])
    while pending:
        dependency = pending.pop()
        if dependency in found:
            continue
        found.add(dependency)
        pending.extend(ROLE_DEPENDENCIES[dependency])
    return found


def route_prior_results(
    role: str, prior_roles: Sequence[str]
) -> Mapping[str, ContextTier]:
    """Classify every supplied prior role exactly once for a consumer role."""

    if role not in ROLE_DEPENDENCIES:
        raise ApplicabilityDenied("context consumer role is not canonical")
    supplied = tuple(prior_roles)
    if len(set(supplied)) != len(supplied):
        raise ApplicabilityDenied("prior role context must not contain duplicates")
    if any(item not in ROLE_DEPENDENCIES for item in supplied):
        raise ApplicabilityDenied("prior role context contains an unknown role")
    direct = set(ROLE_DEPENDENCIES[role])
    transitive = _transitive_dependencies(role) - direct
    return MappingProxyType(
        {
            item: (
                ContextTier.FULL
                if item in direct
                else ContextTier.DIGEST
                if item in transitive
                else ContextTier.OMITTED
            )
            for item in supplied
        }
    )
