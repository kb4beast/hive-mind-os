"""Local deterministic repository implementations of the kernel role protocol.

This adapter deliberately emits only typed requests and evidence-bound results. It
does not register an effect adapter or call a provider; later Phase 7 work must bind
any local effect to the authority gateway and sealed verification.
"""

from __future__ import annotations

from dataclasses import asdict

from ...brain_kernel.canonical import canonical_digest
from ...brain_kernel.context import CompiledContext, ContextRequest
from ...brain_kernel.contracts import ContextManifest, RoleResult
from ...brain_kernel.events import KernelEvent
from ...brain_kernel.roles import (
    KERNEL_IMPLEMENTED_ROLES,
    RoleCapabilities,
    RoleHandler,
    RoleInvocation,
    RoleProtocolError,
    append_role_result,
    next_role,
    result_digest,
    role_capabilities,
    role_prompt,
)
from ...brain_kernel.store import KernelStore
from ...models import Role
from ...prompt_registry import PromptRegistry


class _RepositoryRoleHandler:
    """Common local result construction for the fixed repository-role registry."""

    def __init__(self, role: str) -> None:
        self.role = role
        self.capabilities: RoleCapabilities = role_capabilities(role)

    def execute(self, invocation: RoleInvocation) -> RoleResult:
        if invocation.role != self.role:
            raise RoleProtocolError("handler and invocation roles differ")
        if self.role == "curator" and not (
            invocation.context.request.evaluator_mode
            and invocation.context.manifest.generator_evaluator_separated
        ):
            raise RoleProtocolError("curator requires a fresh evaluator-isolated context")
        output_ref = canonical_digest(
            {
                "role": self.role,
                "context_manifest": invocation.context.manifest.manifest_digest,
                "evidence": invocation.evidence_refs,
                "required_outputs": self.capabilities.required_outputs,
            }
        )
        provisional = RoleResult(
            mission_id=invocation.mission_id,
            work_id=invocation.work_id,
            attempt_id=invocation.attempt_id,
            role=self.role,
            executor_id=invocation.executor_id,
            context_manifest_digest=invocation.context.manifest.manifest_digest,
            authority_envelope_digest=invocation.authority_envelope_digest,
            base_artifact_refs=tuple((*invocation.evidence_refs, *invocation.base_artifact_refs)),
            candidate_artifact_refs=invocation.candidate_artifact_refs,
            output_artifact_refs=(output_ref,),
            claims=self.capabilities.required_outputs,
            effect_receipt_refs=(),
            unresolved_risks=("local-only handler; effect execution is not enabled",),
            requested_next_role=next_role(self.role),
            self_assessment="deterministic local contract result; not a verification verdict",
            result_digest="sha256:" + "0" * 64,
        )
        return RoleResult(**{**asdict(provisional), "result_digest": result_digest(provisional)})


class RepositoryRoleHandlers:
    """Closed registry of executable, local-only repository role handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, RoleHandler] = {
            role: _RepositoryRoleHandler(role) for role in KERNEL_IMPLEMENTED_ROLES
        }

    def roles(self) -> tuple[str, ...]:
        return tuple(self._handlers)

    def handler_for(self, role: str) -> RoleHandler:
        try:
            return self._handlers[role]
        except KeyError as error:
            raise RoleProtocolError("role has no executable kernel handler") from error

    def execute(self, invocation: RoleInvocation) -> RoleResult:
        return self.handler_for(invocation.role).execute(invocation)


def register_kernel_prompts(registry: PromptRegistry) -> dict[str, str]:
    """Register local version-zero role prompts without promoting a champion."""

    return {
        role: registry.register(
            Role(role),
            role_prompt(role),
            parent_digest=None,
            created_by="kernel:phase7",
        )
        for role in KERNEL_IMPLEMENTED_ROLES
    }


_FIXTURE_MISSION_ID = "MISSION-phase7-fixture"
_FIXTURE_DIGEST = "sha256:" + "0" * 64
_FIXTURE_TIME = "1970-01-01T00:00:00Z"


def _fixture_context(role: str, work_id: str, attempt_id: str) -> CompiledContext:
    evaluator = role == "curator"
    request = ContextRequest(
        mission_id=_FIXTURE_MISSION_ID,
        work_id=work_id,
        attempt_id=attempt_id,
        role=role,
        charter_digest=_FIXTURE_DIGEST,
        authority_digest=_FIXTURE_DIGEST,
        token_budget=0,
        query="phase 7 local fixture",
        now=_FIXTURE_TIME,
        data_scopes=("repository",),
        hot_items=(),
        evaluator_mode=evaluator,
    )
    manifest = ContextManifest(
        request.mission_id,
        request.work_id,
        request.attempt_id,
        request.role,
        request.charter_digest,
        request.authority_digest,
        request.token_budget,
        0,
        (),
        (),
        (),
        (),
        {"budget": 0},
        (),
        evaluator,
        canonical_digest({"role": role, "attempt": attempt_id}),
    )
    return CompiledContext(request, manifest, (), ())


def _append_fixture_event(store: KernelStore, event: KernelEvent) -> int:
    events = store.events()
    return store.append(
        KernelEvent(
            event.event_id,
            event.mission_id,
            event.event_type,
            event.actor_id,
            event.occurred_at,
            event.payload,
            work_id=event.work_id,
            attempt_id=event.attempt_id,
            actor_role=event.actor_role,
            event_version=event.event_version,
            previous_digest=events[-1]["digest"] if events else None,
        )
    )


def run_fixture_role_mission(store: KernelStore) -> tuple[RoleResult, ...]:
    """Run the eight local role handlers in an empty fixture store.

    The fixture deliberately leaves all work running. A role result is not an
    effect, verification verdict, or acceptance decision.
    """

    if store.events():
        raise RoleProtocolError("fixture role mission requires an empty event store")
    _append_fixture_event(
        store,
        KernelEvent(
            "phase7:mission",
            _FIXTURE_MISSION_ID,
            "mission.created",
            "phase7:fixture",
            _FIXTURE_TIME,
            {},
        ),
    )
    handlers = RepositoryRoleHandlers()
    results: list[RoleResult] = []
    for role in KERNEL_IMPLEMENTED_ROLES:
        work_id = f"WORK-phase7-{role}"
        attempt_id = f"ATTEMPT-phase7-{role}"
        _append_fixture_event(
            store,
            KernelEvent(
                f"phase7:{role}:work",
                _FIXTURE_MISSION_ID,
                "work.created",
                "phase7:fixture",
                _FIXTURE_TIME,
                {},
                work_id=work_id,
            ),
        )
        for status in ("READY", "LEASED", "RUNNING"):
            _append_fixture_event(
                store,
                KernelEvent(
                    f"phase7:{role}:{status}",
                    _FIXTURE_MISSION_ID,
                    "work.transition",
                    "phase7:fixture",
                    _FIXTURE_TIME,
                    {"status": status},
                    work_id=work_id,
                    actor_role=role,
                ),
            )
        result = handlers.execute(
            RoleInvocation(
                mission_id=_FIXTURE_MISSION_ID,
                work_id=work_id,
                attempt_id=attempt_id,
                role=role,
                executor_id=f"phase7:fixture:{role}",
                context=_fixture_context(role, work_id, attempt_id),
                authority_envelope_digest=_FIXTURE_DIGEST,
                evidence_refs=("fixture:evidence",),
                base_artifact_refs=("fixture:base",),
                candidate_artifact_refs=("fixture:candidate",),
            )
        )
        append_role_result(store, result, occurred_at=_FIXTURE_TIME)
        results.append(result)
    return tuple(results)
