import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hive_mind_os.pilot_orchestration import (
    PilotExecutionBlocker,
    PilotExecutionError,
    WholeOSPilotRunner,
)
from hive_mind_os.pilot_runtime import (
    PilotController,
    PilotPlan,
    PilotPrerequisites,
    PilotStore,
)
from hive_mind_os.whole_os_qualification import (
    EvidenceKind,
    EvidenceRef,
    PilotAttempt,
    canonical_digest,
)
from hive_mind_os.whole_os_service import ServiceObservation

DIGEST = "sha256:" + "a" * 64


def receipt(subject: str, label: str) -> EvidenceRef:
    return EvidenceRef(
        f"receipt:{label}",
        canonical_digest(label),
        EvidenceKind.EXTERNAL_RECEIPT,
        subject,
        0,
    )


def prerequisites() -> PilotPrerequisites:
    return PilotPrerequisites(
        receipt(DIGEST, "host"),
        receipt("pilot", "supervisor"),
        receipt("pilot", "authority"),
        receipt(DIGEST, "benchmark"),
        production_candidate=receipt(DIGEST, "production"),
    )


class FakeService:
    def __init__(self, controller: PilotController, *, fail: bool = False) -> None:
        self.controller = controller
        self.fail = fail
        self.run_calls = 0
        self.observe_calls = 0

    def observation(self) -> ServiceObservation:
        return ServiceObservation("campaign", "running", (), ("package",), ())

    def run_once(self) -> ServiceObservation:
        self.run_calls += 1
        if not self.controller.store.load().active_attempts:
            raise AssertionError("host ran before the pilot intent was durable")
        if self.fail:
            raise TimeoutError("uncertain host boundary")
        return self.observation()

    def observe(self) -> ServiceObservation:
        self.observe_calls += 1
        return self.observation()


class AcceptedEvaluator:
    def __call__(self, **values) -> PilotAttempt:
        subject = values["subject_id"]
        return PilotAttempt(
            values["attempt_id"],
            subject,
            values["family_id"],
            values["candidate_digest"],
            "accepted",
            receipt(subject, f"delivery-{values['attempt_id']}"),
            values["started_at"],
            values["ended_at"],
            values["resource_units"],
            values["domain"],
        )


class PilotOrchestrationTests(unittest.TestCase):
    def plan(self, prerequisites_value: PilotPrerequisites) -> PilotPlan:
        return PilotPlan(
            "pilot",
            "self",
            DIGEST,
            ("self",),
            0,
            259200,
            1,
            10,
            3,
            receipt("pilot", "authority").digest,
            prerequisites_value,
        )

    def test_prerequisite_blockers_prevent_host_execution(self):
        with TemporaryDirectory() as root:
            controller = PilotController(
                PilotStore(Path(root)), self.plan(PilotPrerequisites())
            )
            service = FakeService(controller)
            runner = WholeOSPilotRunner(
                controller, service, AcceptedEvaluator(), clock=lambda: 1
            )
            with self.assertRaises(PilotExecutionError) as raised:
                runner.run_once(
                    attempt_id="attempt",
                    subject_id="self",
                    family_id="feature",
                )
            self.assertEqual(
                raised.exception.blocker,
                PilotExecutionBlocker.PREREQUISITES_UNRESOLVED,
            )
            self.assertEqual(service.run_calls, 0)

    def test_service_attempt_is_driven_inside_durable_lease(self):
        with TemporaryDirectory() as root:
            controller = PilotController(
                PilotStore(Path(root)), self.plan(prerequisites())
            )
            service = FakeService(controller)
            times = iter((1, 2))
            result = WholeOSPilotRunner(
                controller, service, AcceptedEvaluator(), clock=lambda: next(times)
            ).run_once(
                attempt_id="attempt",
                subject_id="self",
                family_id="feature",
            )
            self.assertEqual(service.run_calls, 1)
            self.assertEqual(result.attempt.status, "accepted")
            self.assertFalse(result.state.active_attempts)

    def test_uncertain_effect_is_observed_after_restart_and_never_repeated(self):
        with TemporaryDirectory() as root:
            plan = self.plan(prerequisites())
            controller = PilotController(PilotStore(Path(root)), plan)
            service = FakeService(controller, fail=True)
            runner = WholeOSPilotRunner(
                controller, service, AcceptedEvaluator(), clock=lambda: 1
            )
            with self.assertRaises(PilotExecutionError) as raised:
                runner.run_once(
                    attempt_id="attempt",
                    subject_id="self",
                    family_id="failure",
                )
            self.assertEqual(
                raised.exception.blocker,
                PilotExecutionBlocker.RECONCILIATION_REQUIRED,
            )
            resumed_controller = PilotController(PilotStore(Path(root)), plan)
            resumed_service = FakeService(resumed_controller)
            resumed = WholeOSPilotRunner(
                resumed_controller,
                resumed_service,
                AcceptedEvaluator(),
                clock=lambda: 2,
            )
            with self.assertRaises(PilotExecutionError):
                resumed.run_once(
                    attempt_id="attempt",
                    subject_id="self",
                    family_id="failure",
                )
            result = resumed.reconcile_from_observation("attempt")
            self.assertEqual(resumed_service.run_calls, 0)
            self.assertEqual(resumed_service.observe_calls, 1)
            self.assertEqual(result.attempt.status, "accepted")


if __name__ == "__main__":
    unittest.main()
