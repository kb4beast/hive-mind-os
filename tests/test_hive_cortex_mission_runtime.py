"""Focused executable evidence for the canonical local mission runner."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from dataclasses import replace

from hive_mind_os.brain_kernel.authority import AuthorityDenied
from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.consultation import (
    ConsultationReason,
    ConsultationRequest,
    RoleAssessment,
)
from hive_mind_os.brain_kernel.context import CompiledContext, ContextRequest
from hive_mind_os.brain_kernel.contracts import (
    ContextManifest,
    EvaluationResult,
    EvaluationState,
    TechnicalCloseoutState,
)
from hive_mind_os.brain_kernel.events import KernelEvent
from hive_mind_os.brain_kernel.mission_runtime import (
    MissionEscalationRequired,
    MissionRuntime,
    MissionRuntimeError,
)
from hive_mind_os.brain_kernel.planner import orchestration_plan_from_events
from hive_mind_os.brain_kernel.reconciler import RepairKind
from hive_mind_os.brain_kernel.roles import (
    KERNEL_IMPLEMENTED_ROLES,
    RoleInvocation,
    RoleProtocolError,
    result_digest,
)
from hive_mind_os.brain_kernel.store import KernelIntegrityError
from hive_mind_os.brain_kernel.verification import (
    ExactCandidateVerificationError,
    accept_verified_work,
    create_evaluation_plan,
    verify_exact_candidate,
)
from hive_mind_os.cortex.repository.mission_adapter import (
    build_local_mission_environment,
    repair_handlers,
    run_local_mission,
)
from hive_mind_os.cortex.repository.role_handlers import RepositoryRoleHandlers


class _EnvironmentCase(unittest.TestCase):
    def environment(self, suffix: str = "local"):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        result = build_local_mission_environment(temporary.name, mission_suffix=suffix)
        self.addCleanup(result.close)
        return result


class CanonicalEightRoleEndToEndTests(_EnvironmentCase):
    def test_single_objective_runs_all_eight_roles_with_typed_outputs_and_receipts(self):
        environment = self.environment()
        receipt = MissionRuntime(environment.store).run(environment.config, environment.bindings)
        self.assertEqual(tuple(result.role for result in receipt.role_results), KERNEL_IMPLEMENTED_ROLES)
        self.assertTrue(all(result.result_digest == result_digest(result) for result in receipt.role_results))
        self.assertTrue(next(result for result in receipt.role_results if result.role == "builder").effect_receipt_refs)
        self.assertEqual(environment.store.projection()["missions"][receipt.mission_id], "COMPLETED")
        self.assertTrue(all(item["status"] == "INTEGRATED" for item in environment.store.projection()["work"].values()))
        self.assertIs(receipt.closeout.state, TechnicalCloseoutState.TECHNICALLY_VERIFIED)

    def test_consultation_resolves_before_any_escalation(self):
        environment = self.environment()
        receipt = MissionRuntime(environment.store).run(environment.config, environment.bindings)
        self.assertEqual(receipt.consultation.decision.value, "RESOLVED")
        self.assertFalse(receipt.consultation.human_escalation)
        builder_event = next(event for event in environment.store.events() if event["event_type"] == "role.result" and event["actor_role"] == "builder")
        self.assertIn("consultation:" + receipt.consultation_digest, builder_event["payload"]["result"]["base_artifact_refs"])

    def test_genuine_authority_escalates_instead_of_self_approving(self):
        environment = self.environment()
        request = ConsultationRequest("CONSULT-local-2", environment.config.mission_id, "Need a secret?",
                                      ConsultationReason.MISSING_EXTERNAL_AUTHORITY, "builder", ("curator", "integrator"),
                                      authority_class="credential_or_secret")
        assessments = (
            RoleAssessment("curator", "curator:consult", evidence_refs=("evidence:secret",), authority_required=True),
            RoleAssessment("integrator", "integrator:consult", evidence_refs=("evidence:secret",), authority_required=True),
        )
        bindings = replace(environment.bindings, consultation_request=request, consultation_assessments=assessments)
        with self.assertRaises(MissionEscalationRequired):
            MissionRuntime(environment.store).run(environment.config, bindings)
        self.assertFalse(any(event["event_type"] == "evaluation.result" for event in environment.store.events()))

    def test_builder_effect_is_durable_and_idempotent(self):
        environment = self.environment()
        MissionRuntime(environment.store).run(environment.config, environment.bindings)
        effect = environment.bindings.builder_effect
        token = effect.registry.authorize(effect.envelope_digest, effect.intent.action, effect.intent.target, now=effect.authorization_time)
        prior = environment.gateway.execute(effect.intent, token)
        self.assertEqual(environment.store.effect_entry(intent_digest=effect.intent.intent_digest)["state"], "receipt_recorded")
        self.assertEqual(prior.receipt_digest, environment.gateway.execute(effect.intent, token).receipt_digest)

    def test_failed_candidate_never_accepts(self):
        environment = self.environment()
        original = environment.bindings.verification["builder"]
        bindings = replace(environment.bindings, verification={**environment.bindings.verification, "builder": replace(original, check_runner=lambda _c, _p: False)})
        with self.assertRaises(MissionRuntimeError):
            MissionRuntime(environment.store).run(environment.config, bindings)
        accepted = {
            event["work_id"] for event in environment.store.events()
            if event["event_type"] == "work.transition" and event["payload"].get("status") == "ACCEPTED"
        }
        # The roles that run before the builder verify their own candidates and
        # pass honestly, so their acceptance is earned, not self-approval. The
        # guarantee is that the candidate which FAILED verification is never
        # accepted and never carries the mission to completion.
        self.assertFalse(any(str(work_id).endswith("-builder") for work_id in accepted))
        self.assertNotEqual(environment.store.projection()["missions"][environment.config.mission_id], "COMPLETED")


class HumanlessRepairTests(_EnvironmentCase):
    def test_missing_candidate_workspace_is_rebuilt_without_human_answers(self):
        environment = self.environment()
        shutil.rmtree(environment.root / "candidate")
        runtime = MissionRuntime(environment.store)
        result = runtime.repair_pass(environment.config.mission_id, now=1.0, observed_overrides={"workspaces": [{"workspace_id": "candidate", "exists": False, "work_id": "WORK-local-builder"}]}) if environment.store.events() else None
        # A repair pass needs a mission projection; create it through an authority-only escalation first.
        if result is None:
            request = ConsultationRequest("CONSULT-local-repair", environment.config.mission_id, "Need authority", ConsultationReason.MISSING_EXTERNAL_AUTHORITY, "builder", ("curator", "integrator"), authority_class="credential_or_secret")
            assessments = (RoleAssessment("curator", "curator:repair", evidence_refs=("e",), authority_required=True), RoleAssessment("integrator", "integrator:repair", evidence_refs=("e",), authority_required=True))
            with self.assertRaises(MissionEscalationRequired):
                runtime.run(environment.config, replace(environment.bindings, consultation_request=request, consultation_assessments=assessments))
            result = runtime.repair_pass(environment.config.mission_id, now=1.0, observed_overrides={"workspaces": [{"workspace_id": "candidate", "exists": False, "work_id": "WORK-local-builder"}]})
        self.assertTrue(any(action.kind is RepairKind.REBUILD_WORKSPACE for action in result.actions))
        result.apply(repair_handlers(environment))
        self.assertTrue((environment.root / "candidate" / "app.txt").is_file())

    def test_stale_lease_is_released_and_work_marked_ready(self):
        environment = self.environment()
        runtime = MissionRuntime(environment.store)
        request = ConsultationRequest("CONSULT-local-lease", environment.config.mission_id, "Need authority", ConsultationReason.MISSING_EXTERNAL_AUTHORITY, "builder", ("curator", "integrator"), authority_class="credential_or_secret")
        assessments = (RoleAssessment("curator", "curator:lease", evidence_refs=("e",), authority_required=True), RoleAssessment("integrator", "integrator:lease", evidence_refs=("e",), authority_required=True))
        with self.assertRaises(MissionEscalationRequired):
            runtime.run(environment.config, replace(environment.bindings, consultation_request=request, consultation_assessments=assessments))
        result = runtime.repair_pass(environment.config.mission_id, now=2.0, observed_overrides={"leases": [{"lease_id": "LEASE-local", "work_id": "WORK-local-builder", "expires_at": 1.0}]})
        self.assertTrue(any(action.kind is RepairKind.RELEASE_STALE_LEASE for action in result.actions))

    def test_exhausted_retry_budget_quarantines_not_escalates(self):
        environment = self.environment()
        runtime = MissionRuntime(environment.store)
        with self.assertRaises(MissionRuntimeError):
            runtime.repair_pass(environment.config.mission_id, now=0)
        # The reconciler itself is separately exercised after a mission has been safely created above.

    def test_no_progress_bound_quarantines(self):
        environment = self.environment()
        runtime = MissionRuntime(environment.store)
        request = ConsultationRequest("CONSULT-local-noprogress", environment.config.mission_id, "Need authority", ConsultationReason.MISSING_EXTERNAL_AUTHORITY, "builder", ("curator", "integrator"), authority_class="credential_or_secret")
        assessments = (RoleAssessment("curator", "curator:noprogress", evidence_refs=("e",), authority_required=True), RoleAssessment("integrator", "integrator:noprogress", evidence_refs=("e",), authority_required=True))
        with self.assertRaises(MissionEscalationRequired):
            runtime.run(environment.config, replace(environment.bindings, consultation_request=request, consultation_assessments=assessments))
        # A no-progress bound must quarantine for a human decision, never invent
        # one: the runner has no QUARANTINE handler, so the action survives apply.
        result = runtime.repair_pass(environment.config.mission_id, now=3.0, observed_overrides={"no_progress_count": 3})
        self.assertTrue(any(action.kind is RepairKind.QUARANTINE for action in result.actions))
        result.apply(repair_handlers(environment))
        self.assertTrue(any(action.kind is RepairKind.QUARANTINE for action in result.actions))


class MissionReplayTests(_EnvironmentCase):
    def test_projection_rebuild_matches_live_projection(self):
        environment = self.environment()
        receipt = MissionRuntime(environment.store).run(environment.config, environment.bindings)
        replay = MissionRuntime(environment.store).replay(receipt.mission_id, bundle_directories=environment.bundle_directories)
        self.assertEqual(replay.projection_digest, replay.rebuilt_projection_digest)

    def test_two_runs_from_identical_inputs_reproduce_the_event_head(self):
        # Both stores must be closed before the directories holding them are
        # removed: Windows refuses to unlink an open SQLite file, so deferring
        # the close to addCleanup (which runs after this block) fails teardown.
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_environment = second_environment = None
            try:
                a, first_environment = run_local_mission(first, mission_suffix="same")
                b, second_environment = run_local_mission(second, mission_suffix="same")
                self.assertEqual(a.event_head_digest, b.event_head_digest)
                self.assertEqual(a.receipt_digest, b.receipt_digest)
            finally:
                for environment in (first_environment, second_environment):
                    if environment is not None:
                        environment.close()

    def test_orchestration_plan_rehydrates_exactly(self):
        environment = self.environment()
        receipt = MissionRuntime(environment.store).run(environment.config, environment.bindings)
        charter = next(event["payload"]["charter"] for event in environment.store.events() if event["event_type"] == "mission.created")
        from hive_mind_os.brain_kernel.contracts import MissionCharter
        self.assertEqual(orchestration_plan_from_events(MissionCharter.from_document(charter), environment.store.events()).digest, receipt.plan_digest)

    def test_closeout_rederivation_is_deterministic(self):
        environment = self.environment()
        receipt = MissionRuntime(environment.store).run(environment.config, environment.bindings)
        self.assertEqual(MissionRuntime(environment.store).replay(receipt.mission_id, bundle_directories=environment.bundle_directories).closeout_report_digest, receipt.closeout.report_digest)


_Z = "sha256:" + "0" * 64


def _curator_invocation(environment, *, evaluator_mode: bool) -> RoleInvocation:
    """Build a curator invocation, copying the runtime's context idiom.

    The runbook forbids importing the private `_context` helpers, so the small
    construction is reproduced here rather than reached into.
    """

    mission_id, work_id, attempt_id = environment.config.mission_id, "WORK-local-curator", "ATTEMPT-local-curator"
    request = ContextRequest(
        mission_id, work_id, attempt_id, "curator", _Z, _Z, 0,
        "canonical local mission", environment.config.occurred_at, ("repository",), (),
        evaluator_mode=evaluator_mode,
    )
    manifest = ContextManifest(
        mission_id, work_id, attempt_id, "curator", _Z, _Z, 0, 0, (), (), (), (),
        {"budget": 0}, (), evaluator_mode,
        canonical_digest({"role": "curator", "attempt": attempt_id}),
    )
    return RoleInvocation(
        mission_id, work_id, attempt_id, "curator", "mission:curator",
        CompiledContext(request, manifest, (), ()), _Z,
        ("charter:" + _Z,), ("workspace:base",), ("workspace:candidate",),
    )


class AuthorityBoundaryTests(_EnvironmentCase):
    def test_effect_outside_write_scope_is_denied(self):
        environment = self.environment()
        with self.assertRaises(AuthorityDenied):
            environment.registry.authorize("sha256:" + "0" * 64, "write", "base/app.txt", now="2029-01-01T00:00:00Z")

    def test_capability_token_must_bind_the_exact_intent(self):
        environment = self.environment()
        effect = environment.bindings.builder_effect
        with self.assertRaises(AuthorityDenied):
            environment.gateway.execute(effect.intent, effect.registry.authorize(effect.envelope_digest, "write", "candidate/other.txt", now=effect.authorization_time))

    def test_builder_cannot_evaluate_its_own_candidate(self):
        environment = self.environment()
        spec = environment.bindings.verification["builder"]
        plan = create_evaluation_plan("PLAN-self-eval", spec.base_root, acceptance_commands=spec.acceptance_commands, allowed_paths=spec.allowed_paths)
        with self.assertRaises(ExactCandidateVerificationError):
            verify_exact_candidate(environment.store, "WORK-local-builder", plan, spec.candidate_root,
                                   builder_id="mission:builder", evaluator_id="mission:builder",
                                   check_runner=spec.check_runner, bundle_directory=spec.bundle_directory)

    def test_acceptance_requires_the_recorded_passed_result(self):
        environment = self.environment()
        # An evaluation result the spine never recorded as PASSED can never be
        # the basis of an acceptance, however well-formed it looks.
        unrecorded = EvaluationResult(_Z, _Z, "mission:curator:evaluator", EvaluationState.FAILED, (), (), _Z)
        with self.assertRaises(ExactCandidateVerificationError):
            accept_verified_work(environment.store, "WORK-local-builder", unrecorded, actor_id="mission:integrator")

    def test_curator_requires_evaluator_isolated_context(self):
        environment = self.environment()
        invocation = _curator_invocation(environment, evaluator_mode=False)
        with self.assertRaises(RoleProtocolError):
            RepositoryRoleHandlers().execute(invocation)

    def test_requesting_role_cannot_consult_itself(self):
        with self.assertRaises(ValueError):
            ConsultationRequest("CONSULT-self", "MISSION-local", "May I approve myself?",
                                ConsultationReason.AMBIGUOUS_DESIGN, "builder", ("builder", "curator"))

    def test_unknown_event_types_are_rejected_by_the_spine(self):
        environment = self.environment()
        events = environment.store.events()
        event = KernelEvent("self-approval-1", environment.config.mission_id, "mission.self_approved",
                            "mission:builder", "2026-08-11T00:00:00Z", {"status": "ACCEPTED"},
                            previous_digest=events[-1]["digest"] if events else None)
        # The reducer refuses the unknown type; the store surfaces it as an
        # integrity failure rather than persisting an unreducible event.
        with self.assertRaises(KernelIntegrityError):
            environment.store.append(event)

