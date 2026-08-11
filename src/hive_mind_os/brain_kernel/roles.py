"""Typed, local-only executable-role contracts for the Verifiable Hive Kernel.

The handlers in this module deliberately turn bounded context plus retained
evidence into typed role results.  They do not invoke a model, access a network,
write a repository, promote a candidate, or reach the legacy mission runtime.
Those effects remain behind later, separately verified kernel integrations.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Protocol

from .canonical import canonical_digest
from .context import CompiledContext
from .contracts import RoleResult
from .events import KernelEvent

if TYPE_CHECKING:
    from .store import KernelStore

KERNEL_IMPLEMENTED_ROLES: tuple[str, ...] = (
    "orchestrator",
    "explorer",
    "architect",
    "builder",
    "curator",
    "integrator",
    "steward",
    "optimizer",
)


class RoleProtocolError(ValueError):
    """A role invocation violates the local kernel role boundary."""


@dataclass(frozen=True, slots=True)
class RoleCapabilities:
    """Closed capability envelope advertised by one executable role handler."""

    allowed_actions: tuple[str, ...]
    forbidden_actions: tuple[str, ...]
    required_outputs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.required_outputs:
            raise RoleProtocolError("role handlers require declared outputs")
        if set(self.allowed_actions) & set(self.forbidden_actions):
            raise RoleProtocolError("role action sets overlap")

    def allows(self, action: str) -> bool:
        """Return whether the role may request an action through an adapter.

        This is intentionally only a request check.  It does not authorize or
        execute an effect; authority and effect adapters remain separate kernel
        boundaries.
        """

        return action in self.allowed_actions and action not in self.forbidden_actions


@dataclass(frozen=True, slots=True)
class RoleInvocation:
    """All local, already-bounded input presented to one role execution."""

    mission_id: str
    work_id: str
    attempt_id: str
    role: str
    executor_id: str
    context: CompiledContext
    authority_envelope_digest: str
    evidence_refs: tuple[str, ...]
    base_artifact_refs: tuple[str, ...]
    candidate_artifact_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.role not in KERNEL_IMPLEMENTED_ROLES:
            raise RoleProtocolError("role has no executable kernel handler")
        if not self.executor_id.strip():
            raise RoleProtocolError("executor identity is required")
        if not self.evidence_refs:
            raise RoleProtocolError("role execution requires retained evidence")
        request = self.context.request
        manifest = self.context.manifest
        if (
            request.mission_id != self.mission_id
            or request.work_id != self.work_id
            or request.attempt_id != self.attempt_id
            or request.role != self.role
            or manifest.mission_id != self.mission_id
            or manifest.work_id != self.work_id
            or manifest.attempt_id != self.attempt_id
            or manifest.role != self.role
            or manifest.authority_digest != self.authority_envelope_digest
        ):
            raise RoleProtocolError("role invocation is not bound to its context manifest")

    def to_kwargs(self) -> dict[str, object]:
        """Return constructor values for deterministic test and adapter rebinding."""

        return {
            "mission_id": self.mission_id,
            "work_id": self.work_id,
            "attempt_id": self.attempt_id,
            "role": self.role,
            "executor_id": self.executor_id,
            "context": self.context,
            "authority_envelope_digest": self.authority_envelope_digest,
            "evidence_refs": self.evidence_refs,
            "base_artifact_refs": self.base_artifact_refs,
            "candidate_artifact_refs": self.candidate_artifact_refs,
        }


class RoleHandler(Protocol):
    """A deterministic, provider-free executable role implementation."""

    role: str
    capabilities: RoleCapabilities

    def execute(self, invocation: RoleInvocation) -> RoleResult:
        """Produce an evidence-bound result without directly causing an effect."""

        ...


def result_digest(result: RoleResult) -> str:
    """Hash every semantic RoleResult field except its self-referential digest."""

    values = asdict(result)
    values.pop("result_digest")
    return canonical_digest(values)


def append_role_result(
    store: KernelStore,
    result: RoleResult,
    *,
    occurred_at: str,
) -> int:
    """Append one validated result to the local event spine, idempotently.

    This records no effect and does not transition the work item. Verification and
    acceptance remain separate later-phase responsibilities.
    """

    if result.result_digest != result_digest(result):
        raise RoleProtocolError("role result digest does not bind its content")
    events = store.events()
    return store.append(
        KernelEvent(
            event_id=f"role-result:{result.result_digest}",
            mission_id=result.mission_id,
            event_type="role.result",
            actor_id=result.executor_id,
            occurred_at=occurred_at,
            payload={"result": asdict(result)},
            work_id=result.work_id,
            attempt_id=result.attempt_id,
            actor_role=result.role,
            previous_digest=events[-1]["digest"] if events else None,
        ),
        idempotency_key=result.result_digest,
    )


_CAPABILITIES: dict[str, RoleCapabilities] = {
    "orchestrator": RoleCapabilities(
        ("query_state", "plan", "request_human_gate"),
        ("write", "accept", "verify", "merge", "policy_change"),
        ("objective_dag", "risk_register", "budget_allocation", "stop_conditions"),
    ),
    "explorer": RoleCapabilities(
        ("read", "analyze", "request_source_search"),
        ("write", "accept", "candidate_mutation"),
        ("evidence_map", "candidate", "uncertainty"),
    ),
    "architect": RoleCapabilities(
        ("read", "propose_design_artifact"),
        ("implementation_approval", "weaken_constraints"),
        ("architecture", "interfaces", "threat_model", "rollback_plan"),
    ),
    "builder": RoleCapabilities(
        ("request_isolated_write", "request_command", "request_branch_commit"),
        ("accept", "protected_branch", "merge", "deploy", "modify_sealed_acceptance"),
        ("candidate", "tests", "change_summary", "effect_intents"),
    ),
    "curator": RoleCapabilities(
        ("read_fresh_workspace", "request_test", "inspect_diff"),
        ("candidate_write", "accept", "reuse_builder_scratchpad"),
        ("check_results", "defect_findings", "verdict", "evidence_bundle"),
    ),
    "integrator": RoleCapabilities(
        ("read", "request_contract_test", "request_builder_work"),
        ("write", "merge", "conceal_breaking_change"),
        ("compatibility_report", "data_lineage", "integration_result"),
    ),
    "steward": RoleCapabilities(
        ("read_runtime_state", "request_recovery_test", "propose_maintenance_work"),
        ("trade_recoverability_for_speed",),
        ("recovery_proof", "operational_readiness", "maintenance_findings"),
    ),
    "optimizer": RoleCapabilities(
        ("query_ledger", "request_held_out_experiment", "register_candidate"),
        ("promote", "change_champion", "change_dataset", "policy_change"),
        ("comparison", "measurement_caveats", "promotion_recommendation"),
    ),
}

_NEXT_ROLE = {
    "orchestrator": "explorer",
    "explorer": "architect",
    "architect": "builder",
    "builder": "curator",
    "curator": "integrator",
    # The integrator must request a Builder work item for a code repair; it cannot patch.
    "integrator": "builder",
    "steward": "optimizer",
    "optimizer": None,
}


def role_capabilities(role: str) -> RoleCapabilities:
    """Return the closed kernel contract for one registered role."""

    try:
        return _CAPABILITIES[role]
    except KeyError as error:
        raise RoleProtocolError("role has no executable kernel handler") from error


def role_allows_action(role: str, action: str) -> bool:
    """Return the closed capability decision for one role/action pair."""

    if not isinstance(action, str) or not action.strip():
        raise RoleProtocolError("role action is required")
    return role_capabilities(role).allows(action)


def next_role(role: str) -> str | None:
    """Return a fixed handoff recommendation without scheduling any work."""

    try:
        return _NEXT_ROLE[role]
    except KeyError as error:
        raise RoleProtocolError("role has no executable kernel handler") from error


def role_prompt(role: str) -> str:
    """Render the version-zero local prompt artifact for one kernel role."""

    capabilities = role_capabilities(role)
    return "\n".join(
        (
            f"Hive Mind OS local kernel role: {role}",
            "RoleRuntime may provide bounded cognition; this role has no direct-effect capability.",
            "Allowed requests: " + ", ".join(capabilities.allowed_actions),
            "Forbidden actions: " + ", ".join(capabilities.forbidden_actions),
            "Required outputs: " + ", ".join(capabilities.required_outputs),
        )
    )
