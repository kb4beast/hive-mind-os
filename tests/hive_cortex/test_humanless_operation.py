"""HUMANLESS-430 — humanless operation qualification.

Five situation classes (ambiguity, missing tests, design tradeoffs, CI repair,
recoverable failure) are resolved end to end by already-merged deterministic
kernel surfaces.  No test in this module may ask a human a question, and the
only escalation path exercised here is the genuine-authority one.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.consultation import (
    AUTHORITY_CLASSES,
    ConsultationDecision,
    ConsultationLoop,
    ConsultationReason,
    ConsultationRequest,
    ConsultationResult,
    RoleAssessment,
    evaluate_consultation,
)
from hive_mind_os.brain_kernel.reconciler import (
    DesiredStateReconciler,
    ReconciliationPolicy,
    RepairKind,
)
from hive_mind_os.brain_kernel.workers import KernelWorker, ScopeLockStore
from hive_mind_os.scheduler import ManualClock, Scheduler

from .acceptance_harness import (
    GENUINE_HUMAN_AUTHORITY,
    SPECIALIST_ROLES,
    AcceptanceRun,
    Approval,
    Consultation,
    EffectReceipt,
    load_fixture_inventory,
    validate_run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "hive_cortex"
EVIDENCE_PACKET = REPO_ROOT / "evidence" / "autonomy" / "humanless" / "humanless-qualification.json"
MISSION_ID = "MISSION-humanless-430"

PACKET_REF = "evidence/autonomy/humanless/humanless-qualification.json"
NOW = 100.0


# --------------------------------------------------------------------------
# Construction helpers (private to this module; no underscore imports)
# --------------------------------------------------------------------------


def _request(
    request_id: str,
    reason: ConsultationReason,
    *,
    question: str,
    requesting_role: str = "builder",
    applicable_roles: tuple[str, ...] = ("orchestrator", "curator"),
    evidence_refs: tuple[str, ...] = (),
    authority_class: str | None = None,
    round: int = 1,
) -> ConsultationRequest:
    return ConsultationRequest(
        request_id=request_id,
        mission_id=MISSION_ID,
        question=question,
        reason_code=reason,
        requesting_role=requesting_role,
        applicable_roles=applicable_roles,
        round=round,
        evidence_refs=evidence_refs,
        authority_class=authority_class,
    )


def _assessment(
    role: str,
    *,
    answer: str | None = None,
    proposed: ConsultationDecision = ConsultationDecision.RESOLVED,
    evidence_refs: tuple[str, ...] = (),
    dissent: str | None = None,
    authority_required: bool = False,
) -> RoleAssessment:
    return RoleAssessment(
        role=role,
        identity=f"model:{role}-humanless",
        answer=answer,
        evidence_refs=evidence_refs,
        proposed_decision=proposed,
        dissent=dissent,
        authority_required=authority_required,
        identity_kind="model_role",
    )


def _scenario(
    scenario_id: str,
    *,
    mechanism: str,
    reason: str = "",
    decision: str = "",
    repairs: tuple[str, ...] = (),
    human_escalation: bool = False,
    answered: bool = False,
    dissent_recorded: bool = False,
) -> dict[str, object]:
    """One closed-key scenario row; defaults keep the packet canonical."""

    return {
        "scenario_id": scenario_id,
        "reason": reason,
        "mechanism": mechanism,
        "decision": decision,
        "repairs": list(repairs),
        "human_escalation": bool(human_escalation),
        "answered": bool(answered),
        "dissent_recorded": bool(dissent_recorded),
    }


def _no_test_fixture():
    """The ACCEPT-240 fixture that declares a project with no tests."""

    for fixture in load_fixture_inventory(FIXTURE_ROOT):
        if fixture.scenario == "no-test":
            return fixture
    raise AssertionError("no-test fixture is missing from the inventory")


# --------------------------------------------------------------------------
# Situation-class mechanisms
# --------------------------------------------------------------------------


def _ambiguity_round() -> tuple[ConsultationLoop, ConsultationResult]:
    request = _request(
        "REQ-ambiguity",
        ConsultationReason.AMBIGUOUS_DESIGN,
        question="Which retained surface owns the humanless qualification packet?",
        evidence_refs=(PACKET_REF,),
    )
    assessments = (
        _assessment(
            "orchestrator",
            answer="The retained qualification packet owns it; no human input is needed.",
            evidence_refs=(PACKET_REF,),
        ),
        _assessment("curator", evidence_refs=(PACKET_REF,)),
    )
    return ConsultationLoop().append(request, assessments)


def _missing_tests_round() -> ConsultationResult:
    fixture = _no_test_fixture()
    ref = f"tests/fixtures/hive_cortex/{fixture.fixture_id}"
    request = _request(
        "REQ-missing-tests",
        ConsultationReason.MISSING_EVIDENCE,
        question=f"The {fixture.fixture_id} fixture declares no tests; what happens next?",
    )
    assessments = (
        _assessment(
            "orchestrator",
            proposed=ConsultationDecision.REMAND,
            evidence_refs=(ref,),
        ),
        _assessment(
            "curator",
            proposed=ConsultationDecision.REMAND,
            evidence_refs=(ref,),
        ),
    )
    return evaluate_consultation(request, assessments)


def _design_tradeoff_round() -> ConsultationResult:
    request = _request(
        "REQ-design-tradeoff",
        ConsultationReason.AMBIGUOUS_DESIGN,
        question="Should the qualification packet expose one wide record or two narrow ones?",
        evidence_refs=(PACKET_REF,),
    )
    assessments = (
        _assessment(
            "orchestrator",
            proposed=ConsultationDecision.REPLAN,
            dissent="prefer smaller interface",
            evidence_refs=(PACKET_REF,),
        ),
        _assessment(
            "curator",
            answer="Keep one record and replan the surface split in a later node.",
            evidence_refs=(PACKET_REF,),
        ),
    )
    return evaluate_consultation(request, assessments)


def _ci_repair_document() -> dict[str, object]:
    return {
        "mission_id": MISSION_ID,
        "mission_status": "EXECUTING",
        "work": [{"work_id": "WORK-ci", "status": "RUNNING", "attempts": 1}],
        "provider_failures": [
            {
                "failure_id": "ci-1",
                "work_id": "WORK-ci",
                "retryable": True,
                "attempts": 1,
            }
        ],
    }


def _interruption_document() -> dict[str, object]:
    return {
        "mission_id": MISSION_ID,
        "mission_status": "EXECUTING",
        "work": [
            {
                "work_id": "WORK-resume",
                "status": "AWAITING_VERIFICATION",
                "attempts": 0,
            }
        ],
        "leases": [
            {
                "lease_id": "LEASE-resume",
                "work_id": "WORK-resume",
                "state": "ACTIVE",
                "expires_at": 10.0,
            }
        ],
        "workspaces": [
            {
                "workspace_id": "WS-resume",
                "work_id": "WORK-resume",
                "exists": False,
            }
        ],
        "verifications": [{"work_id": "WORK-resume", "status": "INTERRUPTED"}],
    }


def qualification_scenarios() -> tuple[dict[str, object], ...]:
    """Re-run the five situation classes and report them as plain rows."""

    _, ambiguity = _ambiguity_round()
    missing_tests = _missing_tests_round()
    tradeoff = _design_tradeoff_round()
    reconciler = DesiredStateReconciler()
    ci_repair = reconciler.reconcile(_ci_repair_document(), now=NOW)
    interruption = reconciler.reconcile(_interruption_document(), now=NOW)

    rows = (
        _scenario(
            "ambiguity",
            mechanism="evaluate_consultation",
            reason=ambiguity.reason_code.value,
            decision=ambiguity.decision.value,
            human_escalation=ambiguity.human_escalation,
            answered=bool(ambiguity.answer),
            dissent_recorded=bool(ambiguity.dissent),
        ),
        _scenario(
            "missing-tests",
            mechanism="evaluate_consultation",
            reason=missing_tests.reason_code.value,
            decision=missing_tests.decision.value,
            human_escalation=missing_tests.human_escalation,
            answered=bool(missing_tests.answer),
            dissent_recorded=bool(missing_tests.dissent),
        ),
        _scenario(
            "design-tradeoff",
            mechanism="evaluate_consultation",
            reason=tradeoff.reason_code.value,
            decision=tradeoff.decision.value,
            human_escalation=tradeoff.human_escalation,
            answered=bool(tradeoff.answer),
            dissent_recorded=bool(tradeoff.dissent),
        ),
        _scenario(
            "ci-repair",
            mechanism="DesiredStateReconciler.reconcile",
            repairs=tuple(action.action_id for action in ci_repair.actions),
            human_escalation=False,
        ),
        _scenario(
            "recoverable-interruption",
            mechanism="DesiredStateReconciler.reconcile",
            repairs=tuple(action.action_id for action in interruption.actions),
            human_escalation=False,
        ),
    )
    return tuple(sorted(rows, key=lambda row: str(row["scenario_id"])))


def build_qualification_packet() -> dict[str, object]:
    return {
        "packet_id": "humanless-qualification-v1",
        "node_id": "HUMANLESS-430",
        "semantic_lock": "humanless-qualification",
        "genuine_authority_classes": sorted(AUTHORITY_CLASSES),
        "harness_authority_classes": sorted(GENUINE_HUMAN_AUTHORITY),
        "scenarios": list(qualification_scenarios()),
        "scenario_digest": canonical_digest(list(qualification_scenarios())),
    }


def _valid_run() -> AcceptanceRun:
    effects = tuple(
        EffectReceipt(role, f"effect-{index}") for index, role in enumerate(SPECIALIST_ROLES)
    )
    return AcceptanceRun(
        roles=SPECIALIST_ROLES,
        consultations=(Consultation("curator", ("steward", "optimizer")),),
        approvals=(Approval("builder", "curator", "candidate-1"),),
        sealed_candidate="candidate-1",
        observed_commits=("base-1", "candidate-1"),
        sealed_commits=("base-1", "candidate-1"),
        future_commits=("future-1",),
        authority_class=None,
        human_escalated=False,
        expected_effects=effects,
        receipt_candidate="candidate-1",
        receipt_roles=SPECIALIST_ROLES,
        receipt_effects=effects,
    )


def _escalation_result(authority_class: str) -> ConsultationResult:
    request = _request(
        "REQ-authority",
        ConsultationReason.MISSING_EXTERNAL_AUTHORITY,
        question=f"Does the mission hold {authority_class} authority?",
        evidence_refs=(PACKET_REF,),
        authority_class=authority_class,
    )
    assessments = (
        _assessment("orchestrator", authority_required=True, evidence_refs=(PACKET_REF,)),
        _assessment("curator", authority_required=True, evidence_refs=(PACKET_REF,)),
    )
    return evaluate_consultation(request, assessments)


# --------------------------------------------------------------------------
# required_tests: humanless-operation-suite
# --------------------------------------------------------------------------


class HumanlessOperationSuiteTests(unittest.TestCase):
    def test_ambiguity_resolved_by_role_consultation(self) -> None:
        loop, result = _ambiguity_round()
        self.assertIs(result.decision, ConsultationDecision.RESOLVED)
        self.assertTrue(result.answer)
        self.assertIs(result.human_escalation, False)
        self.assertTrue(result.identity_records)
        for record in result.identity_records:
            self.assertEqual(record["identity_kind"], "model_role")
        self.assertIs(result.role_first_exhausted, True)
        self.assertEqual(len(loop.history), 1)

    def test_missing_tests_become_repair_work(self) -> None:
        fixture = _no_test_fixture()
        self.assertIs(fixture.tests_present, False)
        result = _missing_tests_round()
        self.assertIs(result.decision, ConsultationDecision.REMAND)
        self.assertIn(f"tests/fixtures/hive_cortex/{fixture.fixture_id}", result.evidence_refs)
        self.assertIs(result.human_escalation, False)

    def test_design_tradeoff_replans_with_recorded_dissent(self) -> None:
        result = _design_tradeoff_round()
        self.assertIs(result.decision, ConsultationDecision.REPLAN)
        self.assertTrue(result.dissent)
        self.assertTrue(any("diverged" in item for item in result.dissent))
        self.assertIs(result.human_escalation, False)

    def test_ci_failure_creates_bounded_retry_repair(self) -> None:
        result = DesiredStateReconciler().reconcile(_ci_repair_document(), now=NOW)
        self.assertEqual(len(result.actions), 1)
        action = result.actions[0]
        self.assertIs(action.kind, RepairKind.RETRY)
        self.assertEqual(action.target_id, "WORK-ci")
        self.assertEqual(action.attempt, 1)
        self.assertEqual(action.max_attempts, 3)
        self.assertIs(result.quarantined, False)

        applied: list[str] = []
        self.assertEqual(
            result.apply({RepairKind.RETRY: lambda item: applied.append(item.action_id)}),
            ("retry:WORK-ci",),
        )
        self.assertEqual(applied, ["retry:WORK-ci"])
        self.assertEqual(result.apply({}), ())

    def test_recoverable_interruption_resumes_without_restating_context(self) -> None:
        reconciler = DesiredStateReconciler()
        first = reconciler.reconcile(_interruption_document(), now=NOW)
        second = reconciler.reconcile(_interruption_document(), now=NOW)
        self.assertEqual(first.desired.desired_digest, second.desired.desired_digest)
        self.assertEqual(first.actions, second.actions)
        self.assertEqual(
            {action.kind for action in first.actions},
            {RepairKind.RELEASE_STALE_LEASE, RepairKind.REBUILD_WORKSPACE, RepairKind.REMAND},
        )
        self.assertIs(first.quarantined, False)
        self.assertTrue(first.desired.work)
        for record in first.desired.work:
            self.assertEqual(record["desired_status"], "READY")

    def test_worker_retries_recoverable_execution_failure(self) -> None:
        calls: list[str] = []

        def executor(job) -> None:
            calls.append(job.id)
            if len(calls) == 1:
                raise RuntimeError("transient")

        with tempfile.TemporaryDirectory() as root:
            clock = ManualClock()
            scheduler = Scheduler(root, clock=clock, backoff_seconds=0)
            locks = ScopeLockStore(root)
            try:
                worker = KernelWorker(scheduler, locks, "worker-humanless", executor)
                job = worker.enqueue(MISSION_ID, "WORK-retry", ())
                self.assertIs(worker.run_once(), True)
                failed = scheduler.get(job.id)
                self.assertEqual(failed.state, "ready")
                self.assertIsNotNone(failed.last_error)
                self.assertTrue(str(failed.last_error).startswith("RuntimeError"))
                clock.advance(1)
                self.assertIs(worker.run_once(), True)
                self.assertEqual(scheduler.get(job.id).state, "done")
                self.assertEqual(len(calls), 2)
            finally:
                scheduler.close()
                locks.close()

    def test_end_to_end_run_passes_acceptance_harness(self) -> None:
        self.assertEqual(validate_run(_valid_run()), ())


# --------------------------------------------------------------------------
# required_tests: genuine-authority-classification-suite
# --------------------------------------------------------------------------


class GenuineAuthorityClassificationSuiteTests(unittest.TestCase):
    def test_every_genuine_authority_class_escalates(self) -> None:
        self.assertEqual(len(AUTHORITY_CLASSES), 8)
        for authority_class in sorted(AUTHORITY_CLASSES):
            with self.subTest(authority_class=authority_class):
                result = _escalation_result(authority_class)
                self.assertIs(result.decision, ConsultationDecision.TRUE_AUTHORITY_REQUIRED)
                self.assertIs(result.human_escalation, True)
                self.assertEqual(result.authority_class, authority_class)
                self.assertIsNone(result.answer)

    def test_unknown_authority_class_is_rejected_at_construction(self) -> None:
        with self.assertRaises(ValueError):
            _request(
                "REQ-unknown-authority",
                ConsultationReason.MISSING_EXTERNAL_AUTHORITY,
                question="May the mission take a convenience shortcut?",
                evidence_refs=(PACKET_REF,),
                authority_class="convenience",
            )

    def test_authority_claim_without_evidence_blocks_instead_of_escalating(self) -> None:
        request = _request(
            "REQ-authority-no-evidence",
            ConsultationReason.MISSING_EXTERNAL_AUTHORITY,
            question="Does the mission hold production access?",
            authority_class="production_access",
        )
        result = evaluate_consultation(
            request,
            (
                _assessment("orchestrator", authority_required=True),
                _assessment("curator", authority_required=True),
            ),
        )
        self.assertIs(result.decision, ConsultationDecision.BLOCKED_EVIDENCE)
        self.assertIs(result.human_escalation, False)
        self.assertIsNone(result.authority_class)

    def test_result_contract_rejects_convenience_escalation(self) -> None:
        result = _escalation_result("protected_branch_merge")
        with self.assertRaises(ValueError):
            replace(result, decision=ConsultationDecision.RESOLVED)
        with self.assertRaises(ValueError):
            replace(result, authority_class=None)

    def test_harness_accepts_only_genuine_authority_packets(self) -> None:
        self.assertEqual(len(GENUINE_HUMAN_AUTHORITY), 8)
        for authority_class in sorted(GENUINE_HUMAN_AUTHORITY):
            with self.subTest(authority_class=authority_class):
                run = replace(
                    _valid_run(),
                    human_escalated=True,
                    authority_class=authority_class,
                )
                self.assertEqual(validate_run(run), ())
        defect = replace(_valid_run(), human_escalated=True, authority_class=None)
        self.assertIn("human-escalation-software-defect", validate_run(defect))


# --------------------------------------------------------------------------
# required_tests: software-defect-not-human-suite
# --------------------------------------------------------------------------


class SoftwareDefectNotHumanSuiteTests(unittest.TestCase):
    def test_repair_vocabulary_has_no_human_channel(self) -> None:
        self.assertEqual(
            {item.value for item in RepairKind},
            {
                "release-stale-lease",
                "retry",
                "remand",
                "rebuild-workspace",
                "rollback",
                "quarantine",
            },
        )
        for item in RepairKind:
            for banned in ("human", "question", "escalat", "ask"):
                self.assertNotIn(banned, item.value.lower())
                self.assertNotIn(banned, item.name.lower())

    def test_defect_within_budget_retries_not_escalates(self) -> None:
        document = {
            "mission_id": MISSION_ID,
            "mission_status": "EXECUTING",
            "provider_failures": [
                {
                    "failure_id": "defect-0",
                    "work_id": "WORK-defect",
                    "retryable": True,
                    "attempts": 0,
                }
            ],
        }
        result = DesiredStateReconciler().reconcile(document, now=NOW)
        self.assertEqual(len(result.actions), 1)
        self.assertIs(result.actions[0].kind, RepairKind.RETRY)
        self.assertEqual(result.actions[0].target_id, "WORK-defect")
        self.assertIs(result.quarantined, False)

    def test_exhausted_defect_quarantines_in_system(self) -> None:
        document = {
            "mission_id": MISSION_ID,
            "mission_status": "EXECUTING",
            "provider_failures": [
                {
                    "failure_id": "defect-3",
                    "work_id": "WORK-defect",
                    "retryable": True,
                    "attempts": 3,
                }
            ],
        }
        result = DesiredStateReconciler(ReconciliationPolicy(max_retries=3)).reconcile(
            document, now=NOW
        )
        self.assertEqual(len(result.actions), 1)
        action = result.actions[0]
        self.assertIs(action.kind, RepairKind.QUARANTINE)
        self.assertEqual(action.target_id, "WORK-defect")
        self.assertIs(result.quarantined, True)
        self.assertEqual(result.desired.mission_status, "QUARANTINED")

        document_out = action.to_document()
        self.assertEqual(
            set(document_out),
            {
                "action_id",
                "kind",
                "target_id",
                "reason",
                "attempt",
                "max_attempts",
                "authority_scope",
            },
        )
        for key, value in document_out.items():
            self.assertNotIn("human", key.lower())
            if isinstance(value, str):
                self.assertNotIn("human", value.lower())
                self.assertNotIn("escalat", value.lower())

    def test_no_progress_quarantines_within_bound(self) -> None:
        document = {
            "mission_id": MISSION_ID,
            "mission_status": "EXECUTING",
            "no_progress_count": 3,
        }
        result = DesiredStateReconciler().reconcile(document, now=NOW)
        self.assertEqual(len(result.actions), 1)
        action = result.actions[0]
        self.assertIs(action.kind, RepairKind.QUARANTINE)
        self.assertEqual(action.target_id, MISSION_ID)
        self.assertEqual(action.attempt, 3)
        self.assertEqual(action.max_attempts, 3)
        self.assertIs(result.quarantined, True)

    def test_defect_consultation_cannot_manufacture_authority(self) -> None:
        request = _request(
            "REQ-defect-authority",
            ConsultationReason.AMBIGUOUS_DESIGN,
            question="The build crashed; may the mission claim owner authority to skip it?",
        )
        result = evaluate_consultation(
            request,
            (
                _assessment("orchestrator", authority_required=True),
                _assessment("curator"),
            ),
        )
        self.assertIs(result.decision, ConsultationDecision.BLOCKED_EVIDENCE)
        self.assertIsNot(result.decision, ConsultationDecision.TRUE_AUTHORITY_REQUIRED)
        self.assertIs(result.human_escalation, False)
        self.assertIsNone(result.authority_class)

    def test_retained_evidence_packet_matches_recomputation(self) -> None:
        packet = json.loads(EVIDENCE_PACKET.read_text(encoding="utf-8"))
        self.assertEqual(packet, build_qualification_packet())
        self.assertEqual(packet["scenario_digest"], canonical_digest(packet["scenarios"]))
        self.assertEqual(len(packet["scenarios"]), 5)
        for scenario in packet["scenarios"]:
            with self.subTest(scenario_id=scenario["scenario_id"]):
                self.assertIs(scenario["human_escalation"], False)


if __name__ == "__main__":
    if "--write-evidence" in sys.argv:
        EVIDENCE_PACKET.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_PACKET.write_text(
            json.dumps(build_qualification_packet(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    else:
        unittest.main()
