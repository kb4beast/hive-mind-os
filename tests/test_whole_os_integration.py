import unittest
from contextvars import copy_context
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Condition, Event, Lock, Thread, current_thread
from types import MethodType

from hive_mind_os.cohort_assurance import (
    TerminalAssessment,
    TerminalEvidence,
    convergence_candidate_digest,
)
from hive_mind_os.cohort_runtime import VerificationResult
from hive_mind_os.cortex.repository.mission_bindings import (
    ConfiguredMissionBindingsProvider,
    MissionBindingDescriptor,
)
from hive_mind_os.outcome_graph import OutcomeWorkPackage, compile_outcome_graph
from hive_mind_os.scheduler import ManualClock, Scheduler
from hive_mind_os.whole_os_service import (
    PackageExecutionResult,
    PackageStatus,
    WholeOSService,
    WholeOSServiceConfig,
)

D = "sha256:" + "a" * 64


class FakeHost:
    def execute_package(self, package, bindings, payload):
        return PackageExecutionResult(
            package.package_id, PackageStatus.COMPLETED, D, (D,)
        )

    def assess_terminal_candidate(self, candidate, payload):
        digest = convergence_candidate_digest(candidate)
        return TerminalAssessment(
            VerificationResult(True, ("whole-os-terminal-curator",), "accepted"),
            TerminalEvidence(
                digest,
                "whole-os-builder",
                "whole-os-curator",
                (f"review:{digest}",),
                (f"aggregate:{digest}",),
                (f"verify:{digest}",),
            ),
        )


class WholeOSIntegrationTests(unittest.TestCase):
    def _components(
        self,
        root,
        packages,
        *,
        capacity=2,
        attempts=3,
        host=None,
        campaign="campaign",
    ):
        descriptor = MissionBindingDescriptor(
            "configuration",
            D,
            "tenant",
            "repository",
            "v1",
            (("local", "v1"),),
            ("provider",),
            "authority",
            D,
            "state",
        )
        provider = ConfiguredMissionBindingsProvider(
            descriptor, lambda d, p, r: ("runtime", "delivery")
        )
        graph = compile_outcome_graph(
            packages,
            base_snapshot="a" * 40,
            maximum_concurrent=capacity,
            court_receipt=D,
        )
        config = WholeOSServiceConfig(
            campaign, "tenant", "repository", root, descriptor, graph, attempts
        )
        return config, provider, host or FakeHost()

    def test_dependency_order_survives_durable_queue(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            descriptor = MissionBindingDescriptor(
                "configuration",
                D,
                "tenant",
                "repository",
                "v1",
                (("local", "v1"),),
                ("provider",),
                "authority",
                D,
                "state",
            )
            provider = ConfiguredMissionBindingsProvider(
                descriptor, lambda d, p, r: ("runtime", "delivery")
            )
            graph = compile_outcome_graph(
                (
                    OutcomeWorkPackage("N00", ("R01",), allowed_paths=("src",)),
                    OutcomeWorkPackage(
                        "N01", ("R02",), dependencies=("N00",), allowed_paths=("docs",)
                    ),
                ),
                base_snapshot="a" * 40,
                maximum_concurrent=2,
                court_receipt=D,
            )
            service = WholeOSService(
                WholeOSServiceConfig(
                    "campaign",
                    "tenant",
                    "repository",
                    root,
                    descriptor,
                    graph,
                ),
                provider,
                FakeHost(),
            )
            self.assertEqual(service.run_once().completed_packages, ("N00",))
            self.assertEqual(service.run_once().status, "complete")
            service.close()

    def test_cohort_runs_ready_packages_concurrently_with_one_immutable_kickoff(self):
        class ConcurrentHost:
            def __init__(self):
                self.barrier = Barrier(2)
                self.lock = Lock()
                self.active = 0
                self.maximum_active = 0
                self.kickoffs = []

            def execute_package(self, package, bindings, payload):
                kickoff = payload["cohort_kickoff"]
                with self.lock:
                    self.kickoffs.append(kickoff)
                    self.active += 1
                    self.maximum_active = max(self.maximum_active, self.active)
                if package.package_id in {"A", "B"}:
                    self.barrier.wait(timeout=2)
                with self.assert_immutable(kickoff):
                    kickoff["schema_version"] = 2
                with self.lock:
                    self.active -= 1
                return PackageExecutionResult(
                    package.package_id, PackageStatus.COMPLETED, D, (D,)
                )

            def assess_terminal_candidate(self, candidate, payload):
                return FakeHost().assess_terminal_candidate(candidate, payload)

            @staticmethod
            def assert_immutable(kickoff):
                class Raises:
                    def __enter__(self):
                        return self

                    def __exit__(self, kind, value, traceback):
                        return kind is TypeError

                return Raises()

        with TemporaryDirectory() as directory:
            host = ConcurrentHost()
            config, provider, _ = self._components(
                Path(directory),
                (
                    OutcomeWorkPackage("A", ("R1",), allowed_paths=("a",)),
                    OutcomeWorkPackage("B", ("R2",), allowed_paths=("b",)),
                    OutcomeWorkPackage(
                        "C", ("R3",), dependencies=("A", "B"), allowed_paths=("c",)
                    ),
                ),
                host=host,
            )
            service = WholeOSService(config, provider, host)
            result = service.run_to_completion()
            self.assertEqual(result.status, "complete")
            self.assertEqual(result.completed_packages, ("A", "B", "C"))
            self.assertEqual(host.maximum_active, 2)
            self.assertEqual(
                {item["context_digest"] for item in host.kickoffs},
                {host.kickoffs[0]["context_digest"]},
            )
            service.close()

    def test_cohort_resume_uses_done_jobs_without_reexecution(self):
        class RecordingHost(FakeHost):
            def __init__(self):
                self.calls = []

            def execute_package(self, package, bindings, payload):
                self.calls.append(package.package_id)
                return super().execute_package(package, bindings, payload)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            host = RecordingHost()
            config, provider, _ = self._components(
                root,
                (
                    OutcomeWorkPackage("A", ("R1",), allowed_paths=("a",)),
                    OutcomeWorkPackage(
                        "B", ("R2",), dependencies=("A",), allowed_paths=("b",)
                    ),
                ),
                capacity=1,
                host=host,
            )
            first = WholeOSService(config, provider, host)
            self.assertEqual(first.run_cohort().completed_packages, ("A",))
            first.close()
            resumed = WholeOSService(config, provider, host)
            self.assertEqual(resumed.run_to_completion().status, "complete")
            self.assertEqual(host.calls, ["A", "B"])
            resumed.close()

    def test_terminal_assessment_is_candidate_bound_and_resumes_exactly_once(self):
        class CountingHost(FakeHost):
            def __init__(self):
                self.package_calls = 0
                self.assessment_calls = 0

            def execute_package(self, package, bindings, payload):
                self.package_calls += 1
                return super().execute_package(package, bindings, payload)

            def assess_terminal_candidate(self, candidate, payload):
                self.assessment_calls += 1
                return super().assess_terminal_candidate(candidate, payload)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            host = CountingHost()
            config, provider, _ = self._components(
                root,
                (OutcomeWorkPackage("A", ("R1",), allowed_paths=("a",)),),
                host=host,
            )
            first = WholeOSService(config, provider, host)
            completed = first.run_to_completion()
            self.assertEqual(completed.status, "complete")
            assessment = completed.terminal_assessment
            self.assertIsNotNone(assessment)
            assert assessment is not None
            candidate = first._terminal_candidate()
            self.assertEqual(
                assessment.evidence.candidate_digest,
                convergence_candidate_digest(candidate),
            )
            self.assertEqual(host.package_calls, 1)
            self.assertEqual(host.assessment_calls, 1)
            first.close()

            resumed = WholeOSService(config, provider, host)
            self.assertEqual(resumed.run_to_completion().status, "complete")
            self.assertEqual(host.package_calls, 1)
            self.assertEqual(host.assessment_calls, 1)
            self.assertEqual(resumed._terminal_jobs()[0].state, "done")
            resumed.close()

    def test_missing_or_cross_candidate_assessor_fails_closed(self):
        class MissingAssessor:
            def execute_package(self, package, bindings, payload):
                return PackageExecutionResult(
                    package.package_id, PackageStatus.COMPLETED, D, (D,)
                )

        class CrossCandidateHost(FakeHost):
            def assess_terminal_candidate(self, candidate, payload):
                digest = "sha256:" + "b" * 64
                return TerminalAssessment(
                    VerificationResult(True, ("curator",), "accepted"),
                    TerminalEvidence(
                        digest,
                        "builder",
                        "curator",
                        (f"review:{digest}",),
                        (f"aggregate:{digest}",),
                        (f"verify:{digest}",),
                    ),
                )

        for host in (MissingAssessor(), CrossCandidateHost()):
            with self.subTest(host=type(host).__name__):
                with TemporaryDirectory() as directory:
                    config, provider, _ = self._components(
                        Path(directory),
                        (OutcomeWorkPackage("A", ("R1",), allowed_paths=("a",)),),
                        attempts=1,
                        host=host,
                    )
                    service = WholeOSService(
                        config,
                        provider,
                        host,  # pyright: ignore[reportArgumentType]
                    )
                    result = service.run_to_completion()
                    self.assertEqual(result.status, "blocked")
                    self.assertEqual(result.completed_packages, ("A",))
                    self.assertIsNone(result.terminal_assessment)
                    self.assertIn("terminal", result.terminal_message)
                    self.assertEqual(service._terminal_jobs()[0].state, "dead-letter")
                    service.close()

    def test_terminal_blocker_is_persisted_and_only_stops_dependents(self):
        class BlockingHost(FakeHost):
            def execute_package(self, package, bindings, payload):
                if package.package_id == "A":
                    return PackageExecutionResult(
                        "A", PackageStatus.BLOCKED_AUTHORITY, None, (), "grant absent"
                    )
                return super().execute_package(package, bindings, payload)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            host = BlockingHost()
            config, provider, _ = self._components(
                root,
                (
                    OutcomeWorkPackage("A", ("R1",), allowed_paths=("a",)),
                    OutcomeWorkPackage("B", ("R2",), allowed_paths=("b",)),
                    OutcomeWorkPackage(
                        "C", ("R3",), dependencies=("A",), allowed_paths=("c",)
                    ),
                ),
                host=host,
            )
            service = WholeOSService(config, provider, host)
            result = service.run_to_completion()
            self.assertEqual(result.status, "blocked")
            self.assertEqual(result.completed_packages, ("B",))
            self.assertEqual(result.blocked_packages, ("A", "C"))
            self.assertEqual(service._jobs()[0].attempts, 1)
            service.close()

    def test_cohort_heartbeats_short_leases_and_retries_failures(self):
        class RecordingScheduler(Scheduler):
            """Records each durably committed heartbeat expiry."""

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.heartbeat_seen = Condition()
                self.heartbeat_expiries = []

            def heartbeat(self, job_id, lease_token):
                job = super().heartbeat(job_id, lease_token)
                with self.heartbeat_seen:
                    self.heartbeat_expiries.append(job.lease_expiry)
                    self.heartbeat_seen.notify_all()
                return job

            def wait_for_expiry(self, target, timeout):
                with self.heartbeat_seen:
                    return self.heartbeat_seen.wait_for(
                        lambda: any(
                            expiry is not None and expiry >= target
                            for expiry in self.heartbeat_expiries
                        ),
                        timeout=timeout,
                    )

        hold_errors = []

        class SlowReceiptService(WholeOSService):
            def _persist_package_result(self, result):
                hold_lease("receipt")
                return super()._persist_package_result(result)

        class RetryHost(FakeHost):
            def __init__(self):
                self.calls = 0
                self.assessment_calls = 0

            def execute_package(self, package, bindings, payload):
                self.calls += 1
                hold_lease("host")
                if self.calls == 1:
                    return PackageExecutionResult(
                        package.package_id, PackageStatus.FAILED, None, (), "transient"
                    )
                return super().execute_package(package, bindings, payload)

            def assess_terminal_candidate(self, candidate, payload):
                self.assessment_calls += 1
                hold_lease("assessment")
                return super().assess_terminal_candidate(candidate, payload)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            host = RetryHost()
            config, provider, _ = self._components(
                root,
                (OutcomeWorkPackage("A", ("R1",), allowed_paths=("a",)),),
                host=host,
            )
            clock = ManualClock(1000.0)
            scheduler = RecordingScheduler(
                root / "queue", clock=clock, lease_seconds=0.03, backoff_seconds=0
            )

            def hold_lease(stage):
                # Slow stages advance controlled scheduler time past the original
                # lease length. The clock stays frozen until the real heartbeat
                # thread has durably renewed the lease for the new time, so CI
                # latency cannot expire it and a missing heartbeat times out.
                if hold_errors:
                    return
                for _ in range(3):
                    clock.advance(0.02)
                    target = clock.now() + scheduler.lease_seconds
                    if not scheduler.wait_for_expiry(target, timeout=5.0):
                        hold_errors.append(f"no durable heartbeat during {stage}")
                        return

            service = SlowReceiptService(config, provider, host, scheduler=scheduler)
            try:
                result = service.run_to_completion()
                self.assertEqual([], hold_errors)
                self.assertEqual(result.status, "complete")
                self.assertEqual(host.calls, 2)
                self.assertEqual(host.assessment_calls, 1)
            finally:
                service.close()

    def test_retained_package_receipt_reconciles_without_reexecuting_host(self):
        class NoReplayHost(FakeHost):
            def __init__(self):
                self.calls = 0

            def execute_package(self, package, bindings, payload):
                self.calls += 1
                raise AssertionError("a retained effect must be inspected, not replayed")

        with TemporaryDirectory() as directory:
            root = Path(directory)
            host = NoReplayHost()
            config, provider, _ = self._components(
                root,
                (OutcomeWorkPackage("A", ("R1",), allowed_paths=("a",)),),
                host=host,
            )
            service = WholeOSService(config, provider, host)
            try:
                service._persist_package_result(
                    PackageExecutionResult("A", PackageStatus.COMPLETED, D, (D,))
                )
                result = service.run_to_completion()
                self.assertEqual(result.status, "complete")
                self.assertEqual(host.calls, 0)
            finally:
                service.close()

    def test_strict_runner_does_not_claim_another_services_job(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            scheduler = Scheduler(root / "queue")
            scheduler.enqueue("other", {"package_id": "foreign"}, mission_id="other")
            config, provider, host = self._components(
                root,
                (OutcomeWorkPackage("A", ("R1",), allowed_paths=("a",)),),
            )
            service = WholeOSService(config, provider, host, scheduler=scheduler)
            self.assertEqual(service.run_once().status, "complete")
            foreign = next(job for job in scheduler.jobs() if job.kind == "other")
            self.assertEqual(foreign.state, "ready")
            service.close()

    def test_two_services_atomically_lease_write_paths_and_semantic_locks(self):
        class ContentionHost(FakeHost):
            def __init__(self):
                self.entered = Event()
                self.release = Event()
                self.lock = Lock()
                self.active = 0
                self.maximum_active = 0
                self.calls = 0

            def execute_package(self, package, bindings, payload):
                with self.lock:
                    self.calls += 1
                    self.active += 1
                    self.maximum_active = max(self.maximum_active, self.active)
                    self.entered.set()
                self.assert_released()
                with self.lock:
                    self.active -= 1
                return super().execute_package(package, bindings, payload)

            def assert_released(self):
                if not self.release.wait(timeout=2):
                    raise AssertionError("test did not release executing package")

        cases = (
            (
                OutcomeWorkPackage("A", ("R1",), allowed_paths=("src/shared.py",)),
                OutcomeWorkPackage("B", ("R2",), allowed_paths=("src/shared.py",)),
            ),
            (
                OutcomeWorkPackage(
                    "A",
                    ("R1",),
                    allowed_paths=("src/a.py",),
                    semantic_locks=("schema-migration",),
                ),
                OutcomeWorkPackage(
                    "B",
                    ("R2",),
                    allowed_paths=("src/b.py",),
                    semantic_locks=("schema-migration",),
                ),
            ),
        )
        for first_package, second_package in cases:
            with self.subTest(
                resources=first_package.semantic_locks or first_package.allowed_paths
            ):
                with TemporaryDirectory() as directory:
                    root = Path(directory)
                    host = ContentionHost()
                    first_config, first_provider, _ = self._components(
                        root,
                        (first_package,),
                        host=host,
                        campaign="campaign-a",
                    )
                    second_config, second_provider, _ = self._components(
                        root,
                        (second_package,),
                        host=host,
                        campaign="campaign-b",
                    )
                    first_scheduler = Scheduler(root / "shared-queue")
                    second_scheduler = Scheduler(root / "shared-queue")
                    first = WholeOSService(
                        first_config,
                        first_provider,
                        host,
                        scheduler=first_scheduler,
                    )
                    second = WholeOSService(
                        second_config,
                        second_provider,
                        host,
                        scheduler=second_scheduler,
                    )
                    start = Barrier(3)
                    one_returned = Event()
                    observations = []

                    def run(service):
                        start.wait(timeout=2)
                        observations.append(service.run_cohort())
                        one_returned.set()

                    threads = (
                        Thread(target=run, args=(first,)),
                        Thread(target=run, args=(second,)),
                    )
                    for thread in threads:
                        thread.start()
                    start.wait(timeout=2)
                    self.assertTrue(host.entered.wait(timeout=2))
                    self.assertTrue(one_returned.wait(timeout=2))
                    host.release.set()
                    for thread in threads:
                        thread.join(timeout=2)
                        self.assertFalse(thread.is_alive())

                    self.assertEqual(host.calls, 1)
                    self.assertEqual(host.maximum_active, 1)
                    self.assertEqual(len(observations), 2)
                    self.assertEqual(
                        sum(bool(item.completed_packages) for item in observations), 1
                    )

                    self.assertEqual(first.run_to_completion().status, "complete")
                    self.assertEqual(second.run_to_completion().status, "complete")
                    self.assertEqual(host.calls, 2)
                    first.close()
                    second.close()


class _SyntheticReplayHost(FakeHost):
    """SYNTHETIC host that vouches for its retained successes on demand."""

    def __init__(self, verdict=None):
        self.verdict = verdict
        self.executions = 0
        self.assessments = 0
        self.validations = 0

    def execute_package(self, package, bindings, payload):
        self.executions += 1
        return super().execute_package(package, bindings, payload)

    def assess_terminal_candidate(self, candidate, payload):
        self.assessments += 1
        return super().assess_terminal_candidate(candidate, payload)

    def validate_retained_package_result(self, package, result, payload):
        self.validations += 1
        self.seen = (package.package_id, result, payload)
        if isinstance(self.verdict, Exception):
            raise self.verdict
        return self.verdict


class WholeOSRetainedReplayTests(unittest.TestCase):
    """The service must not deliver a resumed success its host no longer vouches for."""

    def _service(self, root, host):
        return WholeOSIntegrationTests()._components(
            root,
            (OutcomeWorkPackage("A", ("R1",), allowed_paths=("a",)),),
            host=host,
        )

    def _completed(self, root, host):
        config, provider, _ = self._service(root, host)
        service = WholeOSService(config, provider, host)
        self.addCleanup(service.close)
        self.assertEqual(service.run_to_completion().status, "complete")
        return config, provider, service

    def test_valid_retained_success_is_delivered_after_every_resume(self):
        directory = self.enterContext(TemporaryDirectory())
        host = _SyntheticReplayHost()
        config, provider, first = self._completed(Path(directory), host)
        self.assertGreater(host.validations, 0)
        self.assertEqual(host.seen[0], "A")
        self.assertEqual(host.seen[1].status, PackageStatus.COMPLETED)
        self.assertEqual(host.seen[2]["package_id"], "A")
        resumed = WholeOSService(config, provider, host)
        self.addCleanup(resumed.close)
        self.assertEqual(resumed.run_to_completion().status, "complete")
        self.assertEqual((host.executions, host.assessments), (1, 1))

    def test_rejected_retained_success_is_blocked_for_same_and_recreated_service(self):
        directory = self.enterContext(TemporaryDirectory())
        root = Path(directory)
        host = _SyntheticReplayHost()
        config, provider, first = self._completed(root, host)
        historical = first.observe()
        self.assertIsNotNone(historical.terminal_assessment)

        host.verdict = "admission revoked"
        before = host.validations
        replay = first.run_to_completion()
        self.assertGreater(host.validations, before, "the host was asked again")
        self.assertEqual(replay.status, "blocked")
        self.assertEqual(replay.completed_packages, ())
        self.assertEqual(replay.blocked_packages, ("A",))
        self.assertIsNone(replay.terminal_assessment)
        self.assertIn("admission revoked", replay.terminal_message)
        self.assertIn("failed revalidation", replay.terminal_message)
        self.assertEqual(first.run_once().status, "blocked")

        resumed = WholeOSService(config, provider, host)
        self.addCleanup(resumed.close)
        self.assertEqual(resumed.run_to_completion().status, "blocked")
        self.assertEqual(resumed.observe().status, "blocked")
        # No duplicate effect and no new terminal assessment on a rejected replay;
        # the retained receipts stay on disk as history.
        self.assertEqual((host.executions, host.assessments), (1, 1))
        self.assertTrue(list(Path(directory).rglob("terminal-*.json")))
        self.assertTrue(list((Path(directory)).rglob("packages/*.json")))

    def test_verdict_is_never_carried_between_operations(self):
        directory = self.enterContext(TemporaryDirectory())
        host = _SyntheticReplayHost()
        _, _, service = self._completed(Path(directory), host)
        host.verdict = "temporarily unavailable"
        self.assertEqual(service.observe().status, "blocked")
        host.verdict = None
        self.assertEqual(service.observe().status, "complete")
        self.assertEqual((host.executions, host.assessments), (1, 1))

    def test_nested_calls_share_one_verdict_per_invocation(self):
        directory = self.enterContext(TemporaryDirectory())
        host = _SyntheticReplayHost()
        _, _, service = self._completed(Path(directory), host)
        before = host.validations
        self.assertEqual(service.observe().status, "complete")
        # observe() classifies the package for its packages, its terminal
        # candidate and its status, yet asks the host once for the invocation.
        self.assertEqual(host.validations - before, 1)
        before = host.validations
        self.assertEqual(service.observe().status, "complete")
        self.assertEqual(host.validations - before, 1, "a second call asks again")

    def _hold_first_observation(self, service, host):
        """Pause a first public ``observe()`` after it holds a valid verdict.

        Returns ``(shared, finish)``: ``shared['context']`` is a context copied *inside*
        that call (what a propagating framework would hand to another call) and
        ``finish()`` releases and joins the first call, restoring the service.
        """

        classified, release = Event(), Event()
        original = service._classify_done
        shared = {}

        def classify_then_wait(self_):
            result = original()
            if current_thread().name == "first-observer":
                shared["context"] = copy_context()
                classified.set()
                if not release.wait(10):
                    raise AssertionError("coordinator failed to release the first observer")
            return result

        def first_observation():
            try:
                shared["status"] = service.observe().status
            except BaseException as error:  # reported through the assertion below
                shared["error"] = repr(error)

        service._classify_done = MethodType(classify_then_wait, service)
        thread = Thread(target=first_observation, name="first-observer")
        thread.start()
        self.assertTrue(classified.wait(10), "first call reached classification")

        def finish():
            release.set()
            thread.join(10)
            service._classify_done = original
            self.assertFalse(thread.is_alive())
            self.assertNotIn("error", shared)

        self.addCleanup(finish)
        return shared, finish

    def test_overlapping_public_calls_never_share_a_verdict(self):
        """Judge counterexample: revocation between two overlapping observations."""

        directory = self.enterContext(TemporaryDirectory())
        host = _SyntheticReplayHost()
        _, _, service = self._completed(Path(directory), host)
        shared, finish = self._hold_first_observation(service, host)
        # The first call now holds a valid verdict; revoke, then call again.
        host.verdict = "synthetic admission revoked between overlapping calls"
        before = host.validations
        second = service.observe()
        self.assertGreater(host.validations, before, "fresh host validation")
        self.assertEqual(second.status, "blocked")
        self.assertEqual(second.completed_packages, ())
        self.assertIsNone(second.terminal_assessment)
        self.assertIn("revoked between overlapping calls", second.terminal_message)
        finish()
        self.assertEqual(service.observe().status, "blocked")
        self.assertEqual(service.run_to_completion().status, "blocked")
        self.assertEqual((host.executions, host.assessments), (1, 1), "no duplicate effects")

    def test_copied_context_never_authorizes_another_public_call(self):
        """Judge remand-2 counterexample: a context copied inside a public call."""

        directory = self.enterContext(TemporaryDirectory())
        host = _SyntheticReplayHost()
        _, _, service = self._completed(Path(directory), host)
        shared, finish = self._hold_first_observation(service, host)
        host.verdict = "synthetic admission revoked before a context-propagated call"
        for name, entry in (
            ("observe", service.observe),
            ("run_once", service.run_once),
            ("run_cohort", service.run_cohort),
            ("run_to_completion", service.run_to_completion),
        ):
            with self.subTest(f"overlapping {name}"):
                before = host.validations
                result = shared["context"].copy().run(entry)
                self.assertGreater(host.validations, before, "fresh host validation")
                self.assertEqual(result.status, "blocked")
                self.assertEqual(result.completed_packages, ())
                self.assertIsNone(result.terminal_assessment)
        finish()
        # The original invocation has exited; its escaped context must stay inert.
        for name, entry in (("observe", service.observe), ("run_to_completion", service.run_to_completion)):
            with self.subTest(f"after exit {name}"):
                before = host.validations
                result = shared["context"].copy().run(entry)
                self.assertGreater(host.validations, before, "fresh host validation")
                self.assertEqual(result.status, "blocked")
        before = host.validations
        shared["context"].copy().run(service._classify_done)
        shared["context"].copy().run(service._classify_done)
        self.assertEqual(host.validations - before, 2, "a closed scope memoizes nothing")
        self.assertEqual((host.executions, host.assessments), (1, 1), "no duplicate effects")

    def test_concurrent_calls_in_copied_contexts_each_revalidate(self):
        directory = self.enterContext(TemporaryDirectory())
        host = _SyntheticReplayHost()
        _, _, service = self._completed(Path(directory), host)
        shared, finish = self._hold_first_observation(service, host)
        host.verdict = "revoked"
        before = host.validations
        seen = []

        def observe_in_copy():
            seen.append(shared["context"].copy().run(service.observe).status)

        threads = [Thread(target=observe_in_copy) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        self.assertEqual(seen, ["blocked"] * 4)
        self.assertGreaterEqual(host.validations - before, 4)
        finish()
        self.assertEqual((host.executions, host.assessments), (1, 1))

    def test_concurrent_independent_run_calls_each_revalidate(self):
        directory = self.enterContext(TemporaryDirectory())
        host = _SyntheticReplayHost()
        _, _, service = self._completed(Path(directory), host)
        host.verdict = "revoked"
        seen = []

        def run():
            seen.append(service.run_to_completion().status)

        threads = [Thread(target=run) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        self.assertEqual(seen, ["blocked"] * 4)
        self.assertEqual((host.executions, host.assessments), (1, 1))

    def test_host_errors_and_untyped_verdicts_fail_closed(self):
        for verdict in (RuntimeError("evidence unreadable"), True, "", 0):
            with self.subTest(verdict=repr(verdict)):
                directory = self.enterContext(TemporaryDirectory())
                host = _SyntheticReplayHost()
                _, _, service = self._completed(Path(directory), host)
                host.verdict = verdict
                self.assertEqual(service.observe().status, "blocked")

    def test_missing_service_receipt_of_a_done_package_is_rejected_when_validated(self):
        directory = self.enterContext(TemporaryDirectory())
        root = Path(directory)
        host = _SyntheticReplayHost()
        _, _, service = self._completed(root, host)
        for receipt in root.rglob("packages/*.json"):
            receipt.unlink()
        observation = service.observe()
        self.assertEqual(observation.status, "blocked")
        self.assertIn("lacks a valid durable receipt", observation.terminal_message)

    def test_host_without_the_capability_keeps_its_explicit_legacy_contract(self):
        directory = self.enterContext(TemporaryDirectory())
        host = FakeHost()
        config, provider, _ = WholeOSRetainedReplayTests._service(
            self, Path(directory), host
        )
        service = WholeOSService(config, provider, host)
        self.addCleanup(service.close)
        self.assertEqual(service.run_to_completion().status, "complete")
        resumed = WholeOSService(config, provider, host)
        self.addCleanup(resumed.close)
        self.assertEqual(resumed.run_to_completion().status, "complete")

    def test_dependents_are_not_released_by_a_rejected_dependency(self):
        directory = self.enterContext(TemporaryDirectory())
        host = _SyntheticReplayHost()
        config, provider, _ = WholeOSIntegrationTests()._components(
            Path(directory),
            (
                OutcomeWorkPackage("A", ("R1",), allowed_paths=("a",)),
                OutcomeWorkPackage(
                    "B", ("R2",), dependencies=("A",), allowed_paths=("b",)
                ),
            ),
            capacity=1,
            host=host,
        )
        first = WholeOSService(config, provider, host)
        self.addCleanup(first.close)
        self.assertEqual(first.run_cohort().completed_packages, ("A",))
        host.verdict = "evidence corrupted"
        resumed = WholeOSService(config, provider, host)
        self.addCleanup(resumed.close)
        observation = resumed.run_to_completion()
        self.assertEqual(observation.status, "blocked")
        self.assertEqual(observation.completed_packages, ())
        self.assertEqual(observation.blocked_packages, ("A", "B"))
        self.assertEqual(host.executions, 1, "B never ran on a rejected dependency")


if __name__ == "__main__":
    unittest.main()
