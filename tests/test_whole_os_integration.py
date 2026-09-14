import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Event, Lock, Thread
from time import sleep

from hive_mind_os.cortex.repository.mission_bindings import (
    ConfiguredMissionBindingsProvider,
    MissionBindingDescriptor,
)
from hive_mind_os.outcome_graph import OutcomeWorkPackage, compile_outcome_graph
from hive_mind_os.scheduler import Scheduler
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
        class RetryHost(FakeHost):
            def __init__(self):
                self.calls = 0

            def execute_package(self, package, bindings, payload):
                self.calls += 1
                sleep(0.05)
                if self.calls == 1:
                    return PackageExecutionResult(
                        package.package_id, PackageStatus.FAILED, None, (), "transient"
                    )
                return super().execute_package(package, bindings, payload)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            host = RetryHost()
            config, provider, _ = self._components(
                root,
                (OutcomeWorkPackage("A", ("R1",), allowed_paths=("a",)),),
                host=host,
            )
            scheduler = Scheduler(root / "queue", lease_seconds=0.03, backoff_seconds=0)
            service = WholeOSService(config, provider, host, scheduler=scheduler)
            result = service.run_to_completion()
            self.assertEqual(result.status, "complete")
            self.assertEqual(host.calls, 2)
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


if __name__ == "__main__":
    unittest.main()
