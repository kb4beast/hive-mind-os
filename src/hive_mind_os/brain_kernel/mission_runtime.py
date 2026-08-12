"""Canonical, event-derived local mission lifecycle runner.

This module composes the kernel's existing planner, authority, effect, and
verification boundaries.  It deliberately has no cortex or provider dependency.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from .authority import AuthorityRegistry
from .canonical import canonical_digest
from .closeout import (
    declare_closeout_obligations,
    derive_technical_closeout,
    integrate_verified_work,
    record_evaluation_bundle,
)
from .consultation import (
    ConsultationDecision,
    ConsultationLoop,
    ConsultationRequest,
    ConsultationResult,
    RoleAssessment,
)
from .context import CompiledContext, ContextRequest
from .contracts import (
    Budget,
    ContextManifest,
    EffectIntent,
    EvaluationState,
    MissionCharter,
    MissionState,
    RoleResult,
    TechnicalCloseoutReport,
    TechnicalCloseoutState,
    WorkItem,
    WorkState,
)
from .effects import EffectGateway
from .events import KernelEvent
from .planner import OrchestratorPlanner, WorkSchedule, persist_plan
from .reconciler import (
    DesiredStateReconciler,
    ReconciliationPolicy,
    ReconciliationResult,
)
from .roles import KERNEL_IMPLEMENTED_ROLES, RoleInvocation, append_role_result, result_digest
from .store import KernelStore
from .verification import (
    create_evaluation_plan,
    accept_verified_work,
    seal_evaluation_plan,
    verify_exact_candidate,
)

_Z = "sha256:" + "0" * 64
_CONSULTING_ROLES = ("curator", "integrator", "steward", "optimizer")


class MissionRuntimeError(RuntimeError):
    """The canonical mission lifecycle cannot safely proceed."""


class MissionEscalationRequired(MissionRuntimeError):
    """A role-first consultation proved genuine human authority is required."""

    def __init__(self, consultation: ConsultationResult) -> None:
        super().__init__("mission requires genuine human authority")
        self.consultation = consultation


class RoleExecutor(Protocol):
    def execute(self, invocation: RoleInvocation) -> RoleResult: ...


@dataclass(frozen=True, slots=True)
class MissionConfig:
    mission_id: str
    objective: str
    acceptance_spec: str
    repository_root: str
    base_commit: str
    target_branch: str
    occurred_at: str
    charter_budget: Budget
    schedule_budget: Budget
    executor_prefix: str = "mission"


@dataclass(frozen=True, slots=True)
class BuilderEffectBinding:
    registry: AuthorityRegistry
    gateway: EffectGateway
    envelope_digest: str
    intent: EffectIntent
    authorization_time: str


@dataclass(frozen=True, slots=True)
class WorkVerificationSpec:
    base_root: str
    candidate_root: str
    acceptance_commands: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    check_runner: Callable[[str, Path], bool]
    bundle_directory: str
    bundle_ref: str


@dataclass(frozen=True, slots=True)
class MissionBindings:
    role_executor: RoleExecutor
    builder_effect: BuilderEffectBinding
    verification: Mapping[str, WorkVerificationSpec]
    consultation_request: ConsultationRequest
    consultation_assessments: tuple[RoleAssessment, ...]


@dataclass(frozen=True, slots=True)
class MissionRunReceipt:
    mission_id: str
    charter_digest: str
    plan_digest: str
    consultation: ConsultationResult
    consultation_digest: str
    role_results: tuple[RoleResult, ...]
    effect_receipt_digests: tuple[str, ...]
    evaluation_result_digests: Mapping[str, str]
    bundle_refs: tuple[str, ...]
    closeout: TechnicalCloseoutReport
    event_head_digest: str
    projection_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "mission_id": self.mission_id,
            "charter_digest": self.charter_digest,
            "plan_digest": self.plan_digest,
            "consultation": self.consultation.to_document(),
            "consultation_digest": self.consultation_digest,
            "role_results": [asdict(item) for item in self.role_results],
            "effect_receipt_digests": list(self.effect_receipt_digests),
            "evaluation_result_digests": dict(sorted(self.evaluation_result_digests.items())),
            "bundle_refs": list(self.bundle_refs),
            "closeout": self.closeout.to_document(),
            "event_head_digest": self.event_head_digest,
            "projection_digest": self.projection_digest,
        }

    @property
    def receipt_digest(self) -> str:
        return canonical_digest(self.to_document())


@dataclass(frozen=True, slots=True)
class MissionReplayEvidence:
    event_head_digest: str
    projection_digest: str
    rebuilt_projection_digest: str
    closeout_report_digest: str


class MissionRuntime:
    def __init__(self, store: KernelStore) -> None:
        self.store = store

    def _append(
        self, config: MissionConfig, event_type: str, payload: Mapping[str, Any], *,
        event_id: str, actor_id: str, actor_role: str | None = None,
        work_id: str | None = None, attempt_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> int:
        events = self.store.events()
        return self.store.append(
            KernelEvent(event_id, config.mission_id, event_type, actor_id,
                        config.occurred_at, dict(payload), work_id=work_id,
                        attempt_id=attempt_id, actor_role=actor_role,
                        previous_digest=events[-1]["digest"] if events else None),
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def _work_id(config: MissionConfig, role: str) -> str:
        return f"WORK-{config.mission_id.removeprefix('MISSION-')}-{role}"

    @staticmethod
    def _attempt_id(config: MissionConfig, role: str) -> str:
        return f"ATTEMPT-{config.mission_id.removeprefix('MISSION-')}-{role}"

    @staticmethod
    def _context(config: MissionConfig, charter_digest: str, role: str, work_id: str,
                 attempt_id: str) -> CompiledContext:
        evaluator = role == "curator"
        request = ContextRequest(
            config.mission_id, work_id, attempt_id, role, charter_digest, _Z, 0,
            "canonical local mission", config.occurred_at, ("repository",), (),
            evaluator_mode=evaluator,
        )
        manifest = ContextManifest(
            config.mission_id, work_id, attempt_id, role, charter_digest, _Z,
            0, 0, (), (), (), (), {"budget": 0}, (), evaluator,
            canonical_digest({"role": role, "attempt": attempt_id}),
        )
        return CompiledContext(request, manifest, (), ())

    def _validate_bindings(self, bindings: MissionBindings) -> None:
        if set(bindings.verification) != set(KERNEL_IMPLEMENTED_ROLES):
            raise MissionRuntimeError("verification bindings must cover exactly every role")
        request = bindings.consultation_request
        if request.requesting_role != "builder" or not set(request.applicable_roles).issubset(_CONSULTING_ROLES):
            raise MissionRuntimeError("consultation must be builder-requested and role-first")

    def run(self, config: MissionConfig, bindings: MissionBindings) -> MissionRunReceipt:
        self._validate_bindings(bindings)
        charter = MissionCharter(
            1, config.mission_id, config.occurred_at, config.objective,
            (config.acceptance_spec,), config.repository_root, config.base_commit,
            config.target_branch, _Z, _Z, _Z, config.charter_budget, (), ("main",), (),
            MissionState.CREATED,
        )
        self._append(config, "mission.created", {"charter": charter.to_document()},
                     event_id=f"mission-created:{config.mission_id}",
                     actor_id=f"{config.executor_prefix}:orchestrator", actor_role="orchestrator")
        self._append(config, "mission.transition", {"status": MissionState.PLANNING.value},
                     event_id=f"mission-planning:{config.mission_id}",
                     actor_id=f"{config.executor_prefix}:orchestrator", actor_role="orchestrator")

        items: list[WorkItem] = []
        schedules: list[WorkSchedule] = []
        previous: str | None = None
        for role in KERNEL_IMPLEMENTED_ROLES:
            work_id = self._work_id(config, role)
            item = WorkItem(
                work_id, config.mission_id, None, 0, f"{role} lifecycle work",
                config.objective, role, "R1", () if previous is None else (previous,),
                (), (), (config.acceptance_spec,), ("candidate/app.txt",) if role == "builder" else (),
                (), {"role": role}, 2, WorkState.PROPOSED, _Z,
                canonical_digest({"work_id": work_id}),
            )
            consultation_roles = tuple(candidate for candidate in _CONSULTING_ROLES if candidate != role)[:2]
            schedules.append(WorkSchedule(work_id, config.schedule_budget, "R1",
                                          ("mission-runtime-bounded",), consultation_roles, ()))
            items.append(item)
            previous = work_id
        plan = OrchestratorPlanner().plan(charter, items, schedules)
        persist_plan(self.store, plan)
        declare_closeout_obligations(self.store, config.mission_id,
                                     actor_id=f"{config.executor_prefix}:orchestrator")
        for status in (MissionState.READY, MissionState.RUNNING):
            self._append(config, "mission.transition", {"status": status.value},
                         event_id=f"mission-{status.value.lower()}:{config.mission_id}",
                         actor_id=f"{config.executor_prefix}:orchestrator", actor_role="orchestrator")

        _, consultation = ConsultationLoop().append(
            bindings.consultation_request, bindings.consultation_assessments
        )
        if consultation.human_escalation or consultation.decision is not ConsultationDecision.RESOLVED:
            raise MissionEscalationRequired(consultation)
        consultation_digest = canonical_digest(consultation.to_document())
        consultation_ref = "consultation:" + consultation_digest
        results: list[RoleResult] = []
        effects: list[str] = []
        evaluations: dict[str, str] = {}
        bundle_refs: list[str] = []
        for role in KERNEL_IMPLEMENTED_ROLES:
            work_id = self._work_id(config, role)
            attempt_id = self._attempt_id(config, role)
            spec = bindings.verification[role]
            for status in (WorkState.READY, WorkState.LEASED, WorkState.RUNNING):
                self._append(config, "work.transition", {"status": status.value},
                             event_id=f"work-{status.value.lower()}:{work_id}",
                             actor_id=f"{config.executor_prefix}:orchestrator", actor_role="orchestrator",
                             work_id=work_id, attempt_id=attempt_id)
            evaluation_plan = create_evaluation_plan(
                f"PLAN-{work_id}", spec.base_root,
                acceptance_commands=spec.acceptance_commands, allowed_paths=spec.allowed_paths,
            )
            seal_evaluation_plan(self.store, work_id, evaluation_plan, base_root=spec.base_root,
                                 actor_id=f"{config.executor_prefix}:architect")
            receipt_digest: str | None = None
            if role == "builder":
                effect = bindings.builder_effect.gateway.execute(
                    bindings.builder_effect.intent,
                    bindings.builder_effect.registry.authorize(
                        bindings.builder_effect.envelope_digest,
                        bindings.builder_effect.intent.action,
                        bindings.builder_effect.intent.target,
                        now=bindings.builder_effect.authorization_time,
                    ),
                )
                receipt_digest = effect.receipt_digest
                effects.append(receipt_digest)
            invocation = RoleInvocation(
                config.mission_id, work_id, attempt_id, role,
                f"{config.executor_prefix}:{role}",
                self._context(config, charter.digest(), role, work_id, attempt_id), _Z,
                (consultation_ref,) if role == "builder" else ("charter:" + charter.digest(),),
                ("workspace:base",), ("workspace:candidate",),
            )
            result = bindings.role_executor.execute(invocation)
            if receipt_digest is not None:
                provisional = RoleResult(**{**asdict(result), "effect_receipt_refs": (receipt_digest,), "result_digest": _Z})
                result = RoleResult(**{**asdict(provisional), "result_digest": result_digest(provisional)})
            append_role_result(self.store, result, occurred_at=config.occurred_at)
            results.append(result)
            self._append(config, "work.transition", {"status": WorkState.AWAITING_VERIFICATION.value},
                         event_id=f"work-awaiting-verification:{work_id}",
                         actor_id=f"{config.executor_prefix}:orchestrator", actor_role="orchestrator",
                         work_id=work_id, attempt_id=attempt_id)
            outcome = verify_exact_candidate(
                self.store, work_id, evaluation_plan, spec.candidate_root,
                builder_id=result.executor_id, evaluator_id=f"{config.executor_prefix}:curator:evaluator",
                check_runner=spec.check_runner, bundle_directory=spec.bundle_directory,
            )
            if outcome.result.state is not EvaluationState.PASSED:
                raise MissionRuntimeError(f"exact candidate verification failed for {work_id}")
            record_evaluation_bundle(self.store, work_id, outcome.result, spec.bundle_directory,
                                     bundle_ref=spec.bundle_ref,
                                     actor_id=f"{config.executor_prefix}:curator:evaluator")
            accept_verified_work(self.store, work_id, outcome.result,
                                 actor_id=f"{config.executor_prefix}:integrator")
            integrate_verified_work(self.store, work_id, outcome.result,
                                    actor_id=f"{config.executor_prefix}:integrator")
            evaluations[work_id] = outcome.result.result_digest
            bundle_refs.append(spec.bundle_ref)
        for status in (MissionState.VERIFYING, MissionState.INTEGRATING, MissionState.COMPLETED):
            self._append(config, "mission.transition", {"status": status.value},
                         event_id=f"mission-{status.value.lower()}:{config.mission_id}",
                         actor_id=f"{config.executor_prefix}:orchestrator", actor_role="orchestrator")
        directories = {spec.bundle_ref: spec.bundle_directory for spec in bindings.verification.values()}
        closeout = derive_technical_closeout(self.store, config.mission_id, bundle_directories=directories)
        if closeout.state is not TechnicalCloseoutState.TECHNICALLY_VERIFIED:
            raise MissionRuntimeError("technical closeout is incomplete: " + ", ".join(closeout.missing_obligations))
        events = self.store.events()
        return MissionRunReceipt(
            config.mission_id, charter.digest(), plan.digest, consultation, consultation_digest,
            tuple(results), tuple(effects), evaluations, tuple(bundle_refs), closeout,
            events[-1]["digest"], canonical_digest(self.store.projection()),
        )

    def repair_pass(self, mission_id: str, *, now: float,
                    observed_overrides: Mapping[str, Any] | None = None,
                    policy: ReconciliationPolicy | None = None) -> ReconciliationResult:
        projection = self.store.projection()
        if mission_id not in projection["missions"]:
            raise MissionRuntimeError("mission is unknown")
        document: dict[str, Any] = {
            "mission_id": mission_id,
            "mission_status": projection["missions"][mission_id],
            "work": [
                {"work_id": work_id, "mission_id": data["mission_id"], "status": data["status"], "attempts": 0}
                for work_id, data in projection["work"].items() if data["mission_id"] == mission_id
            ],
            "leases": (), "intents": (), "workspaces": (), "provider_failures": (),
            "verifications": (), "no_progress_count": 0, "authority_scope": ("candidate",),
        }
        document.update(dict(observed_overrides or {}))
        return DesiredStateReconciler(policy).reconcile(document, now=now)

    def replay(self, mission_id: str, *, bundle_directories: Mapping[str, str | Path]) -> MissionReplayEvidence:
        events = self.store.events()
        if not any(event["mission_id"] == mission_id for event in events):
            raise MissionRuntimeError("mission is unknown")
        # Both digests are read from projection(); the value rebuild_projections()
        # returns is the full reduced state, whose work entries accumulate
        # evaluation digests that the materialized read model never rehydrates.
        # Comparing those two would be unsatisfiable after any accepted mission.
        projection_digest = canonical_digest(self.store.projection())
        self.store.rebuild_projections()
        rebuilt_digest = canonical_digest(self.store.projection())
        if projection_digest != rebuilt_digest:
            raise MissionRuntimeError("rebuilt projection differs from live projection")
        closeout = derive_technical_closeout(self.store, mission_id, bundle_directories=bundle_directories)
        return MissionReplayEvidence(events[-1]["digest"], projection_digest, rebuilt_digest, closeout.report_digest)


__all__ = [
    "BuilderEffectBinding", "MissionBindings", "MissionConfig", "MissionEscalationRequired",
    "MissionReplayEvidence", "MissionRunReceipt", "MissionRuntime", "MissionRuntimeError",
    "RoleExecutor", "WorkVerificationSpec",
]
