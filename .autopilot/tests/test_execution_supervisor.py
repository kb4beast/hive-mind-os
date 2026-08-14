from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
import tempfile
import threading
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

BIN = Path(__file__).resolve().parents[1] / "bin"


def _load():
    spec = importlib.util.spec_from_file_location(
        "execution_supervisor_test_module", BIN / "execution_supervisor.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


supervisor = _load()

EXECUTION_ID = "sha256:" + "a" * 64
NAMESPACE = "fixed-point-test"
PLAN_ID = "sha256:" + "b" * 64
RELEASE_ID = "sha256:" + "c" * 64
OBSERVATION_ID = "sha256:" + "d" * 64
TERMINAL_OBSERVATION_ID = "sha256:" + "f" * 64


class DeterministicClock:
    def __init__(self) -> None:
        self._value = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
        self._lock = threading.Lock()

    def __call__(self) -> datetime:
        with self._lock:
            value = self._value
            self._value += timedelta(microseconds=1)
            return value


class SimulatedCrash(BaseException):
    pass


class ExecutionSupervisorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.clock = DeterministicClock()
        self._serial = 0

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def execution_dir(self) -> Path:
        self._serial += 1
        directory = self.base / f"execution-{self._serial}"
        (directory / "locks").mkdir(parents=True)
        return directory.resolve()

    def authenticate(
        self,
        directory: Path,
        execution_id: str,
        namespace: str,
        plan_fingerprint: str,
    ) -> Path:
        self.assertEqual(execution_id, EXECUTION_ID)
        self.assertEqual(namespace, NAMESPACE)
        self.assertEqual(plan_fingerprint, PLAN_ID)
        self.assertTrue(directory.is_absolute())
        return directory

    def supervise(self, directory: Path, step, **overrides):
        arguments = {
            "execution_dir": directory,
            "execution_id": EXECUTION_ID,
            "execution_namespace": NAMESPACE,
            "authenticate": self.authenticate,
            "plan_fingerprint": PLAN_ID,
            "initial_frontier_id": "ROUND-1",
            "host_capability": supervisor.HostCapability.AUTHENTICATED_LIFECYCLE,
            "step": step,
            "verify_fixed_point": self.verify_fixed_point,
            "clock": self.clock,
        }
        arguments.update(overrides)
        return supervisor.run_to_fixed_point(**arguments)

    @staticmethod
    def digest(value: str) -> str:
        return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()

    @classmethod
    def wait_condition(cls, label: str = "unchanged"):
        return supervisor.WaitCondition(
            observation_fingerprint=cls.digest("observation:" + label),
            resume_token=cls.digest("resume:" + label),
        )

    @classmethod
    def waiting(cls, detail: str, label: str = "unchanged"):
        return supervisor.StepResult(
            supervisor.StepDisposition.WAITING,
            detail,
            wait_condition=cls.wait_condition(label),
        )

    @staticmethod
    def quiescent_evidence(request, **changes):
        values = {
            "execution_id": request.execution_id,
            "execution_namespace": request.execution_namespace,
            "plan_fingerprint": request.plan_fingerprint,
            "initial_frontier_id": request.initial_frontier_id,
            "current_frontier_id": request.current_frontier_id,
            "terminal_observation_id": request.terminal_observation_id,
            "release_authority_id": RELEASE_ID,
            "controller_observation_id": OBSERVATION_ID,
            "dag_complete": True,
            "active_claims": 0,
            "active_launches": 0,
            "active_sidecars": 0,
            "active_validation_leases": 0,
            "active_publication_transactions": 0,
            "active_global_reservations": 0,
            "host_lifecycle_authenticated": True,
            "active_host_threads": 0,
            "active_host_turns": 0,
            "unobserved_host_lifecycle_items": 0,
        }
        values.update(changes)
        return supervisor.FixedPointEvidence.create(**values)

    def verify_fixed_point(self, request):
        return self.quiescent_evidence(request)

    @staticmethod
    def journal_events(directory: Path):
        return [
            json.loads(line)
            for line in (directory / supervisor.JOURNAL_NAME)
            .read_text(encoding="utf-8")
            .splitlines()
        ]

    def test_durable_round_survives_crash_and_restart_skips_completed_frontier(
        self,
    ) -> None:
        directory = self.execution_dir()
        calls: list[str] = []
        crashed = False

        def step(context):
            calls.append(context.frontier_id)
            if context.frontier_id == "ROUND-1":
                return supervisor.StepResult(
                    supervisor.StepDisposition.ROUND_COMPLETE,
                    "first round is durably complete",
                    next_frontier_id="ROUND-2",
                )
            return self.waiting("second round is waiting", "round-2")

        def crash_after_completed(event):
            nonlocal crashed
            if event["state"] == "ROUND_COMPLETE" and not crashed:
                crashed = True
                raise SimulatedCrash("power loss after durable append")

        with self.assertRaises(SimulatedCrash):
            self.supervise(directory, step, after_append=crash_after_completed)
        self.assertEqual(calls, ["ROUND-1"])

        calls.clear()
        result = self.supervise(directory, step)
        self.assertEqual(result.disposition, supervisor.StepDisposition.WAITING)
        self.assertEqual(result.epoch, 2)
        self.assertEqual(result.frontier_id, "ROUND-2")
        self.assertEqual(result.completed_frontiers, ("ROUND-1",))
        self.assertEqual(calls, ["ROUND-2"])
        acquisitions = [
            event
            for event in self.journal_events(directory)
            if event["state"] == "LEASE_ACQUIRED"
        ]
        self.assertEqual([event["payload"]["epoch"] for event in acquisitions], [1, 2])
        self.assertFalse(acquisitions[1]["payload"]["previous_transaction_closed"])

    def test_crash_with_unknown_step_outcome_requires_recovery_without_replay(
        self,
    ) -> None:
        directory = self.execution_dir()
        calls = 0

        def crash(_context):
            nonlocal calls
            calls += 1
            raise SimulatedCrash("unknown callback boundary")

        with self.assertRaises(SimulatedCrash):
            self.supervise(directory, crash)
        result = self.supervise(
            directory,
            lambda _context: self.fail("an unresolved step must not be replayed"),
        )
        self.assertEqual(calls, 1)
        self.assertEqual(
            result.disposition, supervisor.StepDisposition.RECOVERY_REQUIRED
        )
        self.assertFalse(result.successful)
        self.assertIsNotNone(result.unknown_attempt_id)
        before = self.journal_events(directory)
        repeated = self.supervise(
            directory,
            lambda _context: self.fail("a durable recovery obligation must not poll"),
        )
        self.assertEqual(repeated.journal_event_id, result.journal_event_id)
        self.assertEqual(self.journal_events(directory), before)
        self.assertEqual(sum(event["state"] == "STEP_STARTED" for event in before), 1)

        with self.assertRaises(supervisor.SupervisorRecoveryError):
            supervisor.reconcile_unknown_attempt(
                execution_dir=directory,
                execution_id=EXECUTION_ID,
                execution_namespace=NAMESPACE,
                authenticate=self.authenticate,
                plan_fingerprint=PLAN_ID,
                initial_frontier_id="ROUND-1",
                attempt_id="sha256:" + "0" * 64,
                observation_id=OBSERVATION_ID,
                result=supervisor.StepResult(
                    supervisor.StepDisposition.ROUND_COMPLETE,
                    "observed completion",
                    next_frontier_id="ROUND-2",
                ),
                verify_fixed_point=self.verify_fixed_point,
                clock=self.clock,
            )
        reconciled = supervisor.reconcile_unknown_attempt(
            execution_dir=directory,
            execution_id=EXECUTION_ID,
            execution_namespace=NAMESPACE,
            authenticate=self.authenticate,
            plan_fingerprint=PLAN_ID,
            initial_frontier_id="ROUND-1",
            attempt_id=result.unknown_attempt_id,
            observation_id=OBSERVATION_ID,
            result=supervisor.StepResult(
                supervisor.StepDisposition.ROUND_COMPLETE,
                "authenticated observation proves the round completed",
                next_frontier_id="ROUND-2",
            ),
            verify_fixed_point=self.verify_fixed_point,
            clock=self.clock,
        )
        self.assertEqual(
            reconciled.disposition, supervisor.StepDisposition.ROUND_COMPLETE
        )
        resumed = self.supervise(
            directory,
            lambda context: self.waiting(
                f"resumed at {context.frontier_id}", "reconciled-round-2"
            ),
        )
        self.assertEqual(resumed.frontier_id, "ROUND-2")

    def test_observer_unknown_attempt_cannot_be_upgraded_to_round_completion(
        self,
    ) -> None:
        directory = self.execution_dir()

        def crash(_context):
            raise SimulatedCrash("unknown observer boundary")

        with self.assertRaises(SimulatedCrash):
            self.supervise(
                directory,
                lambda _context: self.fail(
                    "observer must not call admission-capable step"
                ),
                observe_terminal=crash,
                host_capability=supervisor.HostCapability.AUTHENTICATED_OBSERVER,
            )
        pending = self.supervise(
            directory,
            lambda _context: self.fail("unknown observer must not call step"),
            observe_terminal=lambda _context: self.fail(
                "unknown observer must not be replayed"
            ),
            host_capability=supervisor.HostCapability.AUTHENTICATED_OBSERVER,
        )
        assert pending.unknown_attempt_id is not None

        with self.assertRaises(supervisor.SupervisorRecoveryError):
            supervisor.reconcile_unknown_attempt(
                execution_dir=directory,
                execution_id=EXECUTION_ID,
                execution_namespace=NAMESPACE,
                authenticate=self.authenticate,
                plan_fingerprint=PLAN_ID,
                initial_frontier_id="ROUND-1",
                attempt_id=pending.unknown_attempt_id,
                observation_id=OBSERVATION_ID,
                result=supervisor.StepResult(
                    supervisor.StepDisposition.ROUND_COMPLETE,
                    "an observer cannot prove admission completed",
                    next_frontier_id="ROUND-2",
                ),
                verify_fixed_point=self.verify_fixed_point,
                clock=self.clock,
            )

        reconciled = supervisor.reconcile_unknown_attempt(
            execution_dir=directory,
            execution_id=EXECUTION_ID,
            execution_namespace=NAMESPACE,
            authenticate=self.authenticate,
            plan_fingerprint=PLAN_ID,
            initial_frontier_id="ROUND-1",
            attempt_id=pending.unknown_attempt_id,
            observation_id=OBSERVATION_ID,
            result=supervisor.StepResult(
                supervisor.StepDisposition.WAITING_FOR_HOST,
                "observer still sees nonterminal host lifecycle",
                wait_condition=self.wait_condition("observer-reconciliation"),
            ),
            verify_fixed_point=self.verify_fixed_point,
            clock=self.clock,
        )
        self.assertEqual(
            reconciled.disposition, supervisor.StepDisposition.WAITING_FOR_HOST
        )

    def test_concurrent_supervisors_have_exactly_one_winner(self) -> None:
        directory = self.execution_dir()
        entered = threading.Event()
        release = threading.Event()
        callback_calls = 0
        results: list[object] = []
        failures: list[BaseException] = []

        def step(_context):
            nonlocal callback_calls
            callback_calls += 1
            entered.set()
            self.assertTrue(release.wait(5))
            return self.waiting("leased callback completed", "concurrent")

        def invoke():
            try:
                results.append(self.supervise(directory, step))
            except BaseException as error:
                failures.append(error)

        first = threading.Thread(target=invoke)
        second = threading.Thread(target=invoke)
        first.start()
        self.assertTrue(entered.wait(5))
        second.start()
        second.join(5)
        release.set()
        first.join(5)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(callback_calls, 1)
        self.assertEqual(len(results), 1)
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], supervisor.SupervisorLeaseHeld)
        acquisitions = [
            event
            for event in self.journal_events(directory)
            if event["state"] == "LEASE_ACQUIRED"
        ]
        self.assertEqual(len(acquisitions), 1)
        self.assertEqual(acquisitions[0]["payload"]["epoch"], 1)

    def test_unknown_disposition_and_invalid_evidence_fail_closed(self) -> None:
        cases = (
            ("bare string", lambda _context: "WAITING"),
            (
                "untyped enum value",
                lambda _context: supervisor.StepResult(
                    "WAITING",  # type: ignore[arg-type]
                    "a string is not a typed disposition",
                ),
            ),
            (
                "missing evidence",
                lambda _context: supervisor.StepResult(
                    supervisor.StepDisposition.PLAN_QUIESCENT,
                    "unsupported success",
                ),
            ),
            (
                "waiting without wake evidence",
                lambda _context: supervisor.StepResult(
                    supervisor.StepDisposition.WAITING,
                    "unbounded poll request",
                ),
            ),
        )
        for label, step in cases:
            with self.subTest(label=label):
                result = self.supervise(self.execution_dir(), step)
                self.assertEqual(
                    result.disposition, supervisor.StepDisposition.RECOVERY_REQUIRED
                )
                self.assertFalse(result.successful)

    def test_false_quiescence_never_succeeds(self) -> None:
        cases = (
            {"dag_complete": False},
            {"active_claims": 1},
            {"active_launches": 1},
            {"active_sidecars": 1},
            {"active_validation_leases": 1},
            {"active_publication_transactions": 1},
            {"active_global_reservations": 1},
            {"host_lifecycle_authenticated": False},
            {"active_host_threads": 1},
            {"active_host_turns": 1},
            {"unobserved_host_lifecycle_items": 1},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                result = self.supervise(
                    self.execution_dir(),
                    lambda _context: supervisor.StepResult(
                        supervisor.StepDisposition.PLAN_QUIESCENT,
                        "controller claims a fixed point",
                        terminal_observation_id=TERMINAL_OBSERVATION_ID,
                    ),
                    verify_fixed_point=lambda request, item=changes: (
                        self.quiescent_evidence(request, **item)
                    ),
                )
                self.assertEqual(
                    result.disposition, supervisor.StepDisposition.RECOVERY_REQUIRED
                )
                self.assertFalse(result.successful)

    def test_only_complete_zero_activity_evidence_is_success(self) -> None:
        directory = self.execution_dir()
        verifier_requests = []

        def verify(request):
            verifier_requests.append(request)
            return self.quiescent_evidence(request)

        result = self.supervise(
            directory,
            lambda _context: supervisor.StepResult(
                supervisor.StepDisposition.PLAN_QUIESCENT,
                "controller observed the complete fixed point",
                terminal_observation_id=TERMINAL_OBSERVATION_ID,
            ),
            verify_fixed_point=verify,
        )
        self.assertEqual(result.disposition, supervisor.StepDisposition.PLAN_QUIESCENT)
        self.assertTrue(result.successful)
        self.assertEqual(len(verifier_requests), 1)
        self.assertEqual(
            result.fixed_point_evidence.terminal_observation_id,
            TERMINAL_OBSERVATION_ID,
        )
        self.assertEqual(result.fixed_point_evidence.execution_id, EXECUTION_ID)
        repeated = self.supervise(
            directory,
            lambda _context: self.fail("durable fixed point must not replay the step"),
            verify_fixed_point=verify,
        )
        self.assertTrue(repeated.successful)
        self.assertEqual(repeated.epoch, 1)
        self.assertEqual(repeated.journal_event_id, result.journal_event_id)
        self.assertEqual(len(verifier_requests), 2)

        with self.assertRaises(supervisor.SupervisorRecoveryError):
            self.supervise(
                directory,
                lambda _context: self.fail("stale success must not replay the step"),
                verify_fixed_point=lambda request: self.quiescent_evidence(
                    request,
                    controller_observation_id=self.digest("authority-advanced"),
                ),
            )

    def test_step_cannot_fabricate_all_zero_fixed_point_evidence(self) -> None:
        verifier_calls = 0

        def verifier(_request):
            nonlocal verifier_calls
            verifier_calls += 1
            self.fail("forged host evidence must be rejected before verifier")

        forged = supervisor.FixedPointEvidence.create(
            execution_id=EXECUTION_ID,
            execution_namespace=NAMESPACE,
            plan_fingerprint=PLAN_ID,
            initial_frontier_id="ROUND-1",
            current_frontier_id="ROUND-1",
            terminal_observation_id=TERMINAL_OBSERVATION_ID,
            release_authority_id=RELEASE_ID,
            controller_observation_id=OBSERVATION_ID,
            dag_complete=True,
            active_claims=0,
            active_launches=0,
            active_sidecars=0,
            active_validation_leases=0,
            active_publication_transactions=0,
            active_global_reservations=0,
            host_lifecycle_authenticated=True,
            active_host_threads=0,
            active_host_turns=0,
            unobserved_host_lifecycle_items=0,
        )
        result = self.supervise(
            self.execution_dir(),
            lambda _context: supervisor.StepResult(
                supervisor.StepDisposition.PLAN_QUIESCENT,
                "host fabricated zeros",
                fixed_point_evidence=forged,
                terminal_observation_id=TERMINAL_OBSERVATION_ID,
            ),
            verify_fixed_point=verifier,
        )
        self.assertEqual(
            result.disposition, supervisor.StepDisposition.RECOVERY_REQUIRED
        )
        self.assertEqual(verifier_calls, 0)

        def shared(_value):
            return self.waiting("shared authority is invalid")

        with self.assertRaises(supervisor.SupervisorContractError):
            self.supervise(self.execution_dir(), shared, verify_fixed_point=shared)

    def test_verifier_evidence_must_bind_exact_execution_and_frontier(self) -> None:
        def wrong_execution(request):
            return self.quiescent_evidence(request, execution_id="sha256:" + "9" * 64)

        result = self.supervise(
            self.execution_dir(),
            lambda _context: supervisor.StepResult(
                supervisor.StepDisposition.PLAN_QUIESCENT,
                "terminal lifecycle observed",
                terminal_observation_id=TERMINAL_OBSERVATION_ID,
            ),
            verify_fixed_point=wrong_execution,
        )
        self.assertEqual(
            result.disposition, supervisor.StepDisposition.RECOVERY_REQUIRED
        )
        self.assertFalse(result.successful)

    def test_completed_round_advances_once_and_wait_does_not_busy_loop(self) -> None:
        directory = self.execution_dir()
        calls: list[str] = []

        def step(context):
            calls.append(context.frontier_id)
            if context.frontier_id == "ROUND-1":
                return supervisor.StepResult(
                    supervisor.StepDisposition.ROUND_COMPLETE,
                    "round one complete",
                    next_frontier_id="ROUND-2",
                )
            return self.waiting("no immediate progress", "round-2")

        first = self.supervise(directory, step)
        self.assertEqual(first.disposition, supervisor.StepDisposition.WAITING)
        self.assertEqual(calls, ["ROUND-1", "ROUND-2"])

        calls.clear()
        before = self.journal_events(directory)
        second = self.supervise(directory, step)
        self.assertEqual(second.disposition, supervisor.StepDisposition.WAITING)
        self.assertEqual(calls, [])
        self.assertEqual(second.journal_event_id, first.journal_event_id)
        self.assertEqual(self.journal_events(directory), before)
        assert first.wait_condition is not None
        stored_observation = first.wait_condition.observation_fingerprint
        stored_token = first.wait_condition.resume_token
        assert stored_observation is not None and stored_token is not None
        with self.assertRaisesRegex(
            supervisor.SupervisorContractError, "resume token does not match"
        ):
            self.supervise(
                directory,
                step,
                observation_fingerprint=self.digest("forged observation"),
                resume_token=self.digest("wrong token"),
                verify_wait_observation=lambda _request: self.fail(
                    "wrong token must fail before observation"
                ),
            )
        self.assertEqual(self.journal_events(directory), before)
        with self.assertRaisesRegex(
            supervisor.SupervisorContractError, "not authenticated current state"
        ):
            self.supervise(
                directory,
                step,
                observation_fingerprint=self.digest("forged observation"),
                resume_token=stored_token,
                verify_wait_observation=lambda _request: stored_observation,
            )
        self.assertEqual(self.journal_events(directory), before)
        unchanged = self.supervise(
            directory,
            step,
            observation_fingerprint=stored_observation,
            resume_token=stored_token,
            verify_wait_observation=lambda _request: stored_observation,
        )
        self.assertEqual(unchanged.journal_event_id, first.journal_event_id)
        self.assertEqual(calls, [])
        self.assertEqual(self.journal_events(directory), before)
        changed_observation = self.digest("changed observation")
        changed = self.supervise(
            directory,
            step,
            observation_fingerprint=changed_observation,
            resume_token=stored_token,
            verify_wait_observation=lambda _request: changed_observation,
        )
        self.assertEqual(changed.disposition, supervisor.StepDisposition.WAITING)
        self.assertEqual(calls, ["ROUND-2"])

    def test_partial_journal_cannot_be_replayed_under_another_plan(self) -> None:
        directory = self.execution_dir()
        self.supervise(
            directory,
            lambda _context: self.waiting("plan-a durable wait"),
        )
        journal = directory / supervisor.JOURNAL_NAME
        before = journal.read_bytes()
        other_plan = self.digest("plan-b")
        steps = 0

        def permissive_authenticator(
            supplied: Path,
            execution_id: str,
            namespace: str,
            plan_fingerprint: str,
        ) -> Path:
            self.assertEqual(execution_id, EXECUTION_ID)
            self.assertEqual(namespace, NAMESPACE)
            self.assertEqual(plan_fingerprint, other_plan)
            return supplied

        def step(_context):
            nonlocal steps
            steps += 1
            return self.waiting("must not run", "plan-b")

        with self.assertRaisesRegex(
            supervisor.SupervisorJournalError,
            "identity or hash chain is invalid",
        ):
            supervisor.run_to_fixed_point(
                execution_dir=directory,
                execution_id=EXECUTION_ID,
                execution_namespace=NAMESPACE,
                authenticate=permissive_authenticator,
                plan_fingerprint=other_plan,
                initial_frontier_id="ROUND-1",
                host_capability=supervisor.HostCapability.AUTHENTICATED_LIFECYCLE,
                step=step,
                verify_fixed_point=self.verify_fixed_point,
                clock=self.clock,
            )
        self.assertEqual(steps, 0)
        self.assertEqual(journal.read_bytes(), before)
        first_event = json.loads(before.splitlines()[0])
        self.assertEqual(first_event["plan_fingerprint"], PLAN_ID)

    def test_attended_and_no_launch_capabilities_wait_without_calling_step(
        self,
    ) -> None:
        for capability in (
            supervisor.HostCapability.ATTENDED_CARD_ONLY,
            supervisor.HostCapability.NO_LAUNCH,
        ):
            with self.subTest(capability=capability.value):
                directory = self.execution_dir()
                result = self.supervise(
                    directory,
                    lambda _context: self.fail(
                        "card-only/no-launch capability must not call autonomous step"
                    ),
                    host_capability=capability,
                )
                self.assertEqual(
                    result.disposition, supervisor.StepDisposition.WAITING_FOR_HOST
                )
                self.assertFalse(result.successful)
                self.assertIn(
                    "session card is preparation, not a launch", result.detail
                )
                before = self.journal_events(directory)
                repeated = self.supervise(
                    directory,
                    lambda _context: self.fail("unchanged attended wait must not poll"),
                    host_capability=capability,
                )
                self.assertEqual(repeated.journal_event_id, result.journal_event_id)
                self.assertEqual(self.journal_events(directory), before)

    def test_host_capability_change_resumes_a_durable_host_wait(self) -> None:
        directory = self.execution_dir()
        first = self.supervise(
            directory,
            lambda _context: self.fail("no-launch capability must not step"),
            host_capability=supervisor.HostCapability.NO_LAUNCH,
        )
        before = self.journal_events(directory)
        calls = 0

        def step(_context):
            nonlocal calls
            calls += 1
            return supervisor.StepResult(
                supervisor.StepDisposition.BLOCKED,
                "new lifecycle authority observed the pending frontier",
            )

        changed = self.supervise(
            directory,
            step,
            host_capability=supervisor.HostCapability.AUTHENTICATED_LIFECYCLE,
        )
        self.assertEqual(changed.disposition, supervisor.StepDisposition.BLOCKED)
        self.assertEqual(calls, 1)
        self.assertGreater(len(self.journal_events(directory)), len(before))
        self.assertNotEqual(changed.journal_event_id, first.journal_event_id)

    def test_authenticated_observer_can_verify_terminal_truth_without_launch(
        self,
    ) -> None:
        calls: list[str] = []

        result = self.supervise(
            self.execution_dir(),
            lambda _context: self.fail("observer must not call admission-capable step"),
            observe_terminal=lambda context: (
                calls.append(context.frontier_id)
                or supervisor.ObserverResult(
                    supervisor.StepDisposition.PLAN_QUIESCENT,
                    "observer authenticated terminal controller and host truth",
                    terminal_observation_id=TERMINAL_OBSERVATION_ID,
                )
            ),
            host_capability=supervisor.HostCapability.AUTHENTICATED_OBSERVER,
        )

        self.assertTrue(result.successful)
        self.assertEqual(calls, ["ROUND-1"])

    def test_authenticated_observer_cannot_advance_a_round(self) -> None:
        result = self.supervise(
            self.execution_dir(),
            lambda _context: self.fail("observer must not call admission-capable step"),
            observe_terminal=lambda _context: supervisor.ObserverResult(
                supervisor.StepDisposition.ROUND_COMPLETE,
                "attempted observer admission",
            ),
            host_capability=supervisor.HostCapability.AUTHENTICATED_OBSERVER,
        )

        self.assertEqual(
            result.disposition, supervisor.StepDisposition.RECOVERY_REQUIRED
        )
        self.assertEqual(result.completed_frontiers, ())

    def test_authenticated_observer_wait_is_idempotent(self) -> None:
        directory = self.execution_dir()
        calls = 0

        def observe(_context):
            nonlocal calls
            calls += 1
            return supervisor.ObserverResult(
                supervisor.StepDisposition.WAITING_FOR_HOST,
                "host lifecycle is not terminal",
                wait_condition=self.wait_condition("observer"),
            )

        first = self.supervise(
            directory,
            lambda _context: self.fail("observer must not call admission-capable step"),
            observe_terminal=observe,
            host_capability=supervisor.HostCapability.AUTHENTICATED_OBSERVER,
        )
        before = self.journal_events(directory)
        repeated = self.supervise(
            directory,
            lambda _context: self.fail("observer must not call admission-capable step"),
            observe_terminal=observe,
            host_capability=supervisor.HostCapability.AUTHENTICATED_OBSERVER,
        )

        self.assertEqual(repeated.journal_event_id, first.journal_event_id)
        self.assertEqual(self.journal_events(directory), before)
        self.assertEqual(calls, 1)

    def test_wake_at_wait_replays_until_due_then_steps_once(self) -> None:
        directory = self.execution_dir()
        current = [datetime(2026, 8, 14, 12, 0, tzinfo=UTC)]
        calls = 0

        def clock():
            return current[0]

        def wait(_context):
            nonlocal calls
            calls += 1
            return supervisor.StepResult(
                supervisor.StepDisposition.WAITING,
                "wake only at the durable deadline",
                wait_condition=supervisor.WaitCondition(
                    wake_at=datetime(2026, 8, 14, 13, 0, tzinfo=UTC)
                ),
            )

        first = self.supervise(directory, wait, clock=clock)
        before = self.journal_events(directory)
        repeated = self.supervise(directory, wait, clock=clock)
        self.assertEqual(repeated.journal_event_id, first.journal_event_id)
        self.assertEqual(calls, 1)
        self.assertEqual(self.journal_events(directory), before)

        current[0] = datetime(2026, 8, 14, 13, 0, tzinfo=UTC)
        due = self.supervise(
            directory,
            lambda _context: supervisor.StepResult(
                supervisor.StepDisposition.BLOCKED, "deadline observation is adverse"
            ),
            clock=clock,
        )
        self.assertEqual(due.disposition, supervisor.StepDisposition.BLOCKED)

    def test_blocked_and_recovery_dispositions_stop_after_one_step(self) -> None:
        for disposition in (
            supervisor.StepDisposition.BLOCKED,
            supervisor.StepDisposition.RECOVERY_REQUIRED,
        ):
            with self.subTest(disposition=disposition.value):
                calls = 0

                def step(_context):
                    nonlocal calls
                    calls += 1
                    return supervisor.StepResult(disposition, "adverse state")

                result = self.supervise(self.execution_dir(), step)
                self.assertEqual(result.disposition, disposition)
                self.assertEqual(calls, 1)
                self.assertFalse(result.successful)

    def test_torn_tail_is_preserved_before_explicit_recovery(self) -> None:
        directory = self.execution_dir()
        self.supervise(directory, lambda _context: self.waiting("initial durable wait"))
        journal = directory / supervisor.JOURNAL_NAME
        torn_bytes = b'{"schema_version":1,"kind":"partial-event"'
        with journal.open("ab") as stream:
            stream.write(torn_bytes)
        with self.assertRaises(supervisor.TornJournalTail):
            self.supervise(
                directory,
                lambda _context: self.fail("a torn journal must stop before stepping"),
            )

        receipt = supervisor.recover_torn_tail(
            execution_dir=directory,
            execution_id=EXECUTION_ID,
            execution_namespace=NAMESPACE,
            authenticate=self.authenticate,
            plan_fingerprint=PLAN_ID,
            initial_frontier_id="ROUND-1",
            actor="test:curator",
            reason="simulated partial append",
            clock=self.clock,
        )
        preserved = json.loads(receipt.evidence_path.read_text(encoding="utf-8"))
        self.assertEqual(preserved["plan_fingerprint"], PLAN_ID)
        self.assertEqual(base64.b64decode(preserved["tail_base64"]), torn_bytes)
        self.assertEqual(preserved["tail_digest"], receipt.tail_digest)
        self.assertEqual(preserved["tail_bytes"], len(torn_bytes))
        self.assertTrue(journal.read_bytes().endswith(b"\n"))
        self.assertNotIn(torn_bytes, journal.read_bytes())

        calls = 0

        def resumed(_context):
            nonlocal calls
            calls += 1
            return self.waiting("safe after explicit repair", "post-repair")

        result = self.supervise(directory, resumed)
        self.assertEqual(result.epoch, 3)
        self.assertEqual(result.disposition, supervisor.StepDisposition.WAITING)
        self.assertEqual(calls, 1)

        preserved["reason"] = "tampered recovery explanation"
        receipt.evidence_path.write_text(
            json.dumps(preserved, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(supervisor.SupervisorJournalError):
            self.supervise(
                directory,
                lambda _context: self.fail(
                    "tampered recovery evidence must stop before stepping"
                ),
            )

    def test_new_lock_journal_and_receipt_fsync_file_before_parent_entry(self) -> None:
        directory = self.execution_dir()
        calls: list[tuple[str, Path | None]] = []

        def file_sync(_descriptor):
            calls.append(("file", None))

        def directory_sync(path):
            calls.append(("directory", Path(path)))

        with (
            mock.patch.object(supervisor.os, "fsync", side_effect=file_sync),
            mock.patch.object(
                supervisor, "_fsync_directory", side_effect=directory_sync
            ),
        ):
            with supervisor._SupervisorLease(directory):
                pass
        self.assertEqual(
            calls,
            [("file", None), ("directory", directory / "locks")],
        )

        calls.clear()
        journal = directory / "durability-journal.jsonl"
        with (
            mock.patch.object(supervisor.os, "fsync", side_effect=file_sync),
            mock.patch.object(
                supervisor, "_fsync_directory", side_effect=directory_sync
            ),
        ):
            supervisor._append_bytes(journal, b"{}\n")
        self.assertEqual(calls, [("file", None), ("directory", directory)])

        calls.clear()
        receipt = directory / "durability-receipt.json"
        with (
            mock.patch.object(supervisor.os, "fsync", side_effect=file_sync),
            mock.patch.object(
                supervisor, "_fsync_directory", side_effect=directory_sync
            ),
        ):
            supervisor._exclusive_canonical_write(receipt, {"receipt": "exact"})
        self.assertEqual(calls, [("file", None), ("directory", directory)])

    def test_replace_fsyncs_parent_after_replace_and_after_failed_temp_cleanup(
        self,
    ) -> None:
        directory = self.execution_dir()
        journal = directory / "replace.jsonl"
        journal.write_bytes(b"old\n")
        real_replace = supervisor.os.replace
        calls: list[str] = []

        def file_sync(_descriptor):
            calls.append("file")

        def replace(source, destination):
            calls.append("replace")
            real_replace(source, destination)

        with (
            mock.patch.object(supervisor.os, "fsync", side_effect=file_sync),
            mock.patch.object(supervisor.os, "replace", side_effect=replace),
            mock.patch.object(
                supervisor,
                "_fsync_directory",
                side_effect=lambda _path: calls.append("directory"),
            ),
        ):
            supervisor._replace_with_prefix(journal, b"new\n")
        self.assertEqual(calls, ["file", "replace", "directory"])
        self.assertEqual(journal.read_bytes(), b"new\n")

        calls.clear()

        def failed_replace(_source, _destination):
            calls.append("replace")
            raise OSError("simulated rename failure")

        with (
            mock.patch.object(supervisor.os, "fsync", side_effect=file_sync),
            mock.patch.object(supervisor.os, "replace", side_effect=failed_replace),
            mock.patch.object(
                supervisor,
                "_fsync_directory",
                side_effect=lambda _path: calls.append("directory"),
            ),
        ):
            with self.assertRaises(supervisor.SupervisorRecoveryError):
                supervisor._replace_with_prefix(journal, b"not-installed\n")
        self.assertEqual(calls, ["file", "replace", "directory"])
        self.assertFalse(tuple(directory.glob(".execution-supervisor-recovery-*")))

    def test_journal_rejects_duplicate_nonfinite_noncanonical_and_extra_fields(
        self,
    ) -> None:
        mutators = {
            "duplicate": lambda raw: raw.replace(b"{", b'{"schema_version":1,', 1),
            "nonfinite": lambda raw: raw.replace(b'"epoch":1', b'"epoch":NaN', 1),
            "noncanonical": self._noncanonical_first_line,
            "extra field": self._extra_first_line,
        }
        for label, mutate in mutators.items():
            with self.subTest(label=label):
                directory = self.execution_dir()
                self.supervise(directory, lambda _context: self.waiting("seed journal"))
                journal = directory / supervisor.JOURNAL_NAME
                journal.write_bytes(mutate(journal.read_bytes()))
                with self.assertRaises(supervisor.SupervisorJournalError):
                    self.supervise(
                        directory,
                        lambda _context: self.fail("invalid journal must fail closed"),
                    )

    @staticmethod
    def _noncanonical_first_line(raw: bytes) -> bytes:
        first, separator, rest = raw.partition(b"\n")
        value = json.loads(first)
        return json.dumps(value, sort_keys=True).encode("utf-8") + separator + rest

    @staticmethod
    def _extra_first_line(raw: bytes) -> bytes:
        first, separator, rest = raw.partition(b"\n")
        value = json.loads(first)
        value["unexpected"] = True
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        return encoded + separator + rest


if __name__ == "__main__":
    unittest.main()
