"""Typed, local-only executable-role contracts for the Verifiable Hive Kernel.

The handlers in this module deliberately turn bounded context plus retained
evidence into typed role results.  They do not invoke a model, access a network,
write a repository, promote a candidate, or reach the legacy mission runtime.
Those effects remain behind later, separately verified kernel integrations.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Protocol

from ..agents import RoleCapabilities, agent_type_for, canonical_roles
from .canonical import canonical_digest
from .context import CompiledContext
from .contracts import RoleResult
from .events import KernelEvent

if TYPE_CHECKING:
    from .store import KernelStore

KERNEL_IMPLEMENTED_ROLES: tuple[str, ...] = tuple(
    role.value for role in canonical_roles()
)


class RoleProtocolError(ValueError):
    """A role invocation violates the local kernel role boundary."""


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
            raise RoleProtocolError(
                "role invocation is not bound to its context manifest"
            )

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


def role_capabilities(role: str) -> RoleCapabilities:
    """Return the closed capability envelope owned by one direct agent."""

    try:
        return agent_type_for(role).capabilities
    except ValueError as error:
        raise RoleProtocolError("role has no executable kernel handler") from error


def role_allows_action(role: str, action: str) -> bool:
    """Return the closed capability decision for one role/action pair."""

    if not isinstance(action, str) or not action.strip():
        raise RoleProtocolError("role action is required")
    return role_capabilities(role).allows(action)


def next_role(role: str) -> str | None:
    """Return the direct agent's handoff recommendation without scheduling work."""

    try:
        successor = agent_type_for(role).next_role
    except ValueError as error:
        raise RoleProtocolError("role has no executable kernel handler") from error
    return None if successor is None else successor.value


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
