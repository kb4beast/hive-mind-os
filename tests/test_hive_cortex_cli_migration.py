"""MIGRATION-460: public CLI and scheduler ingress routing to the canonical runtime.

Every test uses only the durable local surfaces (`Scheduler`, `MissionStore`,
`KernelStore`) so the routing claims are proved against real state, never against
a mock of the code under test.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hive_mind_os import cli, workers
from hive_mind_os.acceptance import AcceptanceSpecification
from hive_mind_os.brain_kernel.store import KernelStore
from hive_mind_os.mission_store import MissionStore
from hive_mind_os.repository_compatibility import (
    CANONICAL_ENQUEUE_ROUTE,
    CANONICAL_JOB_KIND,
    CANONICAL_ROLLBACK_REF,
    COMPATIBILITY_MODES,
    LEGACY_ENQUEUE_ROUTE,
    LEGACY_JOB_KIND,
    RuntimeRouteError,
    default_kernel_state_dir,
    record_canonical_enqueue,
    resolve_runtime_route,
    runtime_identity,
)
from hive_mind_os.scheduler import Scheduler
from hive_mind_os.workers import (
    Worker,
    execute_canonical_mission_job,
    route_job_executor,
)
from tests.fixtures.fixture_repo import build_fixture_repo


class _MigrationCliCase(unittest.TestCase):
    """Shared local state: one fixture repository plus one scheduler root."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fixture = build_fixture_repo(self.root / "source")
        self.state_dir = self.root / "state"
        self.kernel_state_dir = default_kernel_state_dir(self.state_dir)

    def specification(self, identifier: str = "alpha") -> Path:
        path = self.root / f"{identifier}.json"
        specification = AcceptanceSpecification(
            identifier,
            "increment(1) returns 2",
            (
                sys.executable,
                "-B",
                "-c",
                "from tiny_pkg.maths import increment; assert increment(1) == 2",
            ),
            declared_paths=("tiny_pkg/maths.py",),
        )
        path.write_text(json.dumps(specification.to_dict()), encoding="utf-8")
        return path

    def enqueue_arguments(
        self,
        *,
        mode: str | None = None,
        objective: str = "Fix the failing test",
        specification: Path | None = None,
        max_attempts: int | None = None,
    ) -> Namespace:
        argv = [
            "--repository",
            str(self.fixture.root),
            "--objective",
            objective,
            "--acceptance-spec",
            str(specification or self.specification()),
            "--state-dir",
            str(self.state_dir),
            "--pin",
            self.fixture.commit_two,
        ]
        if mode is not None:
            argv += ["--compatibility-mode", mode]
        if max_attempts is not None:
            argv += ["--max-attempts", str(max_attempts)]
        return cli.build_enqueue_parser().parse_args(argv)

    def enqueue(self, **kwargs: object) -> dict[str, object]:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(cli._run_enqueue(self.enqueue_arguments(**kwargs)), 0)  # type: ignore[arg-type]
        return json.loads(output.getvalue())

    def jobs(self) -> tuple:
        scheduler = Scheduler(self.state_dir)
        try:
            return scheduler.jobs()
        finally:
            scheduler.close()

    def kernel_events(self) -> list[dict[str, object]]:
        database = KernelStore.database_path(self.kernel_state_dir)
        if not database.is_file():
            return []
        store = KernelStore(database, read_only=True)
        try:
            return store.events()
        finally:
            store.close()

    def status_model(self) -> dict[str, object]:
        output = io.StringIO()
        arguments = Namespace(
            state_dir=str(self.state_dir), html=None, json_output=True
        )
        with redirect_stdout(output):
            self.assertEqual(cli._run_status(arguments), 0)
        return json.loads(output.getvalue())

    def assert_legacy_store_untouched(self, mission_id: str) -> None:
        store = MissionStore(self.state_dir)
        try:
            self.assertFalse(store.has_mission(mission_id))
        finally:
            store.close()
        self.assertFalse((self.state_dir / "d" / mission_id).exists())


class CliRoutingTests(_MigrationCliCase):
    def test_parser_defaults_compatibility_mode_to_canonical(self) -> None:
        parser = cli.build_enqueue_parser()
        minimal = parser.parse_args(
            ["--repository", str(self.fixture.root), "--objective", "o"]
        )
        self.assertEqual("canonical", minimal.compatibility_mode)
        self.assertEqual(("canonical", "kernel-v1", "legacy"), COMPATIBILITY_MODES)
        for mode in COMPATIBILITY_MODES:
            parsed = parser.parse_args(
                [
                    "--repository",
                    str(self.fixture.root),
                    "--objective",
                    "o",
                    "--compatibility-mode",
                    mode,
                ]
            )
            self.assertEqual(mode, parsed.compatibility_mode)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(
                [
                    "--repository",
                    str(self.fixture.root),
                    "--objective",
                    "o",
                    "--compatibility-mode",
                    "shadow",
                ]
            )

    def test_new_enqueue_defaults_to_canonical_runtime(self) -> None:
        output = self.enqueue()

        self.assertEqual("canonical", output["runtime"])
        jobs = self.jobs()
        self.assertEqual([CANONICAL_JOB_KIND], [job.kind for job in jobs])
        self.assertEqual("canonical", jobs[0].payload["runtime"])
        self.assertEqual(output["mission_id"], jobs[0].mission_id)
        events = self.kernel_events()
        self.assertEqual(1, len(events))
        self.assertEqual("mission.created", events[0]["event_type"])
        self.assertEqual(
            f"MISSION-canonical-{str(output['mission_id'])[2:]}",
            events[0]["mission_id"],
        )
        payload = events[0]["payload"]
        self.assertEqual(CANONICAL_ENQUEUE_ROUTE, payload["migration_route"])
        self.assertEqual("canonical", payload["runtime"])
        self.assertEqual(output["mission_id"], payload["legacy_mission_id"])
        self.assertEqual(output["job_id"], payload["scheduler_job_id"])
        self.assertEqual(CANONICAL_ROLLBACK_REF, payload["rollback_ref"])

    def test_worker_routes_canonical_kind_to_canonical_executor(self) -> None:
        output = self.enqueue()
        calls: list[tuple[str, str]] = []

        def recorder(job, state_dir) -> str:
            calls.append((job.kind, str(job.payload["mission_id"])))
            return str(job.payload["mission_id"])

        queue = Scheduler(self.state_dir)
        try:
            worker = Worker(
                queue,
                "t",
                executor=lambda job, state_dir: execute_canonical_mission_job(
                    job, state_dir, invoker=recorder
                ),
            )
            self.assertTrue(worker.run_once())
            self.assertEqual([(CANONICAL_JOB_KIND, output["mission_id"])], calls)
            job = queue.jobs()[0]
            self.assertEqual("done", job.state)
            self.assertEqual(output["mission_id"], job.mission_id)
        finally:
            queue.close()

    def test_status_identifies_actual_runtime(self) -> None:
        canonical = self.enqueue(objective="Canonical objective")
        legacy = self.enqueue(objective="Legacy objective", mode="legacy")
        self.assertNotEqual(canonical["mission_id"], legacy["mission_id"])

        model = self.status_model()
        routes = model["runtime_routes"]
        self.assertEqual("canonical", routes[canonical["mission_id"]])
        self.assertEqual("legacy", routes[legacy["mission_id"]])
        self.assertEqual(2, len(routes))

        html_path = self.root / "status.html"
        arguments = Namespace(
            state_dir=str(self.state_dir), html=str(html_path), json_output=False
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cli._run_status(arguments), 0)
        self.assertTrue(html_path.is_file())
        self.assertIn("Mission control", html_path.read_text(encoding="utf-8"))

    def test_status_reports_unknown_runtime_for_a_foreign_job_kind(self) -> None:
        scheduler = Scheduler(self.state_dir)
        try:
            scheduler.enqueue(
                "test", {"mission_id": "M-foreign"}, mission_id="M-foreign"
            )
        finally:
            scheduler.close()

        self.assertEqual("unknown", runtime_identity("test"))
        model = self.status_model()
        self.assertEqual("unknown", model["runtime_routes"]["M-foreign"])


class NoDualAuthorityTests(_MigrationCliCase):
    def test_canonical_request_never_reaches_legacy_mission_store(self) -> None:
        output = self.enqueue()
        mission_id = str(output["mission_id"])

        queue = Scheduler(self.state_dir)
        try:
            worker = Worker(
                queue,
                "canonical",
                executor=lambda job, state_dir: execute_canonical_mission_job(
                    job, state_dir, invoker=lambda item, root: mission_id
                ),
            )
            self.assertTrue(worker.run_once())
            self.assertEqual("done", queue.jobs()[0].state)
        finally:
            queue.close()

        self.assert_legacy_store_untouched(mission_id)

    def test_legacy_request_never_invokes_canonical_runtime(self) -> None:
        output = self.enqueue(mode="legacy")
        mission_id = str(output["mission_id"])
        job = self.jobs()[0]
        self.assertEqual(LEGACY_JOB_KIND, job.kind)

        with patch(
            "hive_mind_os.workers.execute_canonical_mission_job",
            side_effect=AssertionError("canonical runtime must not run a legacy job"),
        ) as canonical:
            self.assertEqual(mission_id, route_job_executor(job, self.state_dir))
        self.assertEqual(0, canonical.call_count)

        store = MissionStore(self.state_dir)
        try:
            self.assertTrue(store.has_mission(mission_id))
        finally:
            store.close()

    def test_duplicate_enqueue_is_deduplicated_single_job(self) -> None:
        first = self.enqueue()
        second = self.enqueue()

        self.assertEqual(first, second)
        jobs = self.jobs()
        self.assertEqual(1, len(jobs))
        self.assertEqual(first["job_id"], jobs[0].id)
        self.assertEqual(1, len(self.kernel_events()))

    def test_unknown_job_kind_fails_closed(self) -> None:
        scheduler = Scheduler(self.state_dir)
        try:
            job = scheduler.enqueue(
                "test", {"mission_id": "M-foreign"}, mission_id="M-foreign"
            )
        finally:
            scheduler.close()

        # The router itself must refuse: an unknown kind may not be handed to
        # either execution authority and rejected only by that authority's own guard.
        with patch(
            "hive_mind_os.workers.execute_mission_job",
            side_effect=AssertionError("legacy runtime must not see an unknown kind"),
        ) as legacy, patch(
            "hive_mind_os.workers.execute_canonical_mission_job",
            side_effect=AssertionError("canonical runtime must not see an unknown kind"),
        ) as canonical:
            with self.assertRaisesRegex(ValueError, "unsupported job kind: test"):
                route_job_executor(job, self.state_dir)
        self.assertEqual(0, legacy.call_count)
        self.assertEqual(0, canonical.call_count)
        self.assert_legacy_store_untouched("M-foreign")

    def test_missing_canonical_runtime_fails_closed_not_fallback(self) -> None:
        output = self.enqueue(max_attempts=1)
        mission_id = str(output["mission_id"])

        def unavailable(job, state_dir) -> str:
            raise RuntimeRouteError("canonical mission runtime is unavailable")

        queue = Scheduler(self.state_dir)
        try:
            worker = Worker(
                queue,
                "canonical",
                executor=lambda job, state_dir: execute_canonical_mission_job(
                    job, state_dir, invoker=unavailable
                ),
            )
            self.assertTrue(worker.run_once())
            job = queue.jobs()[0]
            self.assertEqual("dead-letter", job.state)
            self.assertIn("RuntimeRouteError", job.last_error or "")
        finally:
            queue.close()

        self.assert_legacy_store_untouched(mission_id)

    def test_default_canonical_invoker_fails_closed_without_a_bindings_provider(
        self,
    ) -> None:
        output = self.enqueue()
        previous = workers.set_canonical_mission_bindings_provider(None)
        self.addCleanup(workers.set_canonical_mission_bindings_provider, previous)

        with self.assertRaisesRegex(RuntimeRouteError, "bindings provider"):
            execute_canonical_mission_job(self.jobs()[0], self.state_dir)

        self.assert_legacy_store_untouched(str(output["mission_id"]))

    def test_default_canonical_invoker_runs_the_kernel_mission_runtime(self) -> None:
        output = self.enqueue()
        mission_id = str(output["mission_id"])
        observed: dict[str, object] = {}

        class RecordingRuntime:
            def __init__(self, store) -> None:
                observed["store"] = store

            def run(self, config, bindings):
                observed["run"] = (config, bindings)
                return SimpleNamespace(mission_id="MISSION-canonical-recorded")

        def provider(payload, kernel_root):
            observed["payload"] = payload
            observed["kernel_root"] = kernel_root
            return ("config-sentinel", "bindings-sentinel")

        previous = workers.set_canonical_mission_bindings_provider(provider)
        self.addCleanup(workers.set_canonical_mission_bindings_provider, previous)
        with patch(
            "hive_mind_os.brain_kernel.mission_runtime.MissionRuntime", RecordingRuntime
        ):
            returned = execute_canonical_mission_job(self.jobs()[0], self.state_dir)

        self.assertEqual(mission_id, returned)
        self.assertEqual(("config-sentinel", "bindings-sentinel"), observed["run"])
        self.assertEqual(mission_id, dict(observed["payload"])["mission_id"])
        self.assertEqual(self.kernel_state_dir, observed["kernel_root"])
        self.assert_legacy_store_untouched(mission_id)


class LegacyRollbackTests(_MigrationCliCase):
    def test_kernel_v1_mode_retains_legacy_execution_and_kernel_record(self) -> None:
        output = self.enqueue(mode="kernel-v1")

        self.assertEqual("legacy", output["runtime"])
        self.assertNotIn("compatibility_mode", output)
        self.assertNotIn("rollback_ref", output)
        jobs = self.jobs()
        self.assertEqual([LEGACY_JOB_KIND], [job.kind for job in jobs])
        events = self.kernel_events()
        self.assertEqual(1, len(events))
        self.assertEqual(
            LEGACY_ENQUEUE_ROUTE, events[0]["payload"]["migration_route"]
        )
        self.assertEqual(
            f"rollback:{LEGACY_ENQUEUE_ROUTE}",
            resolve_runtime_route("kernel-v1").rollback_ref,
        )
        self.assertEqual(
            CANONICAL_ROLLBACK_REF, resolve_runtime_route("canonical").rollback_ref
        )

    def test_legacy_mode_writes_no_kernel_record(self) -> None:
        output = self.enqueue(mode="legacy")

        self.assertEqual("legacy", output["runtime"])
        self.assertEqual([LEGACY_JOB_KIND], [job.kind for job in self.jobs()])
        self.assertFalse(KernelStore.database_path(self.kernel_state_dir).exists())
        self.assertEqual([], self.kernel_events())
        self.assertFalse(resolve_runtime_route("legacy").records_kernel_ingress)

    def test_unknown_mode_is_rejected(self) -> None:
        for mode in ("shadow", "canary"):
            with self.assertRaisesRegex(RuntimeRouteError, mode):
                resolve_runtime_route(mode)

    def test_legacy_job_still_executes_end_to_end(self) -> None:
        output = self.enqueue(mode="legacy")
        mission_id = str(output["mission_id"])

        queue = Scheduler(self.state_dir)
        try:
            self.assertTrue(Worker(queue, "w").run_once())
            job = queue.jobs()[0]
            self.assertEqual("done", job.state)
            self.assertEqual(mission_id, job.mission_id)
        finally:
            queue.close()

        self.assertTrue((self.state_dir / "d" / mission_id).is_dir())
        store = MissionStore(self.state_dir)
        try:
            self.assertTrue(store.has_mission(mission_id))
            self.assertEqual("succeeded", store.mission(mission_id)["status"])
        finally:
            store.close()


class CanonicalIngressRecordTests(_MigrationCliCase):
    def test_canonical_record_rejects_a_job_without_a_legacy_mission_id(self) -> None:
        scheduler = Scheduler(self.state_dir)
        try:
            job = scheduler.enqueue(CANONICAL_JOB_KIND, {"mission_id": "unprefixed"})
        finally:
            scheduler.close()

        self.assertIsNone(job.mission_id)
        with self.assertRaisesRegex(ValueError, "valid mission id"):
            record_canonical_enqueue(job, legacy_state_dir=self.state_dir)
        self.assertEqual([], self.kernel_events())

    def test_canonical_record_chains_previous_digest(self) -> None:
        legacy = self.enqueue(objective="Legacy first", mode="kernel-v1")
        canonical = self.enqueue(objective="Canonical second")

        events = self.kernel_events()
        self.assertEqual(2, len(events))
        self.assertEqual(LEGACY_ENQUEUE_ROUTE, events[0]["payload"]["migration_route"])
        self.assertEqual(
            CANONICAL_ENQUEUE_ROUTE, events[1]["payload"]["migration_route"]
        )
        self.assertIsNone(events[0]["previous_digest"])
        self.assertEqual(events[0]["digest"], events[1]["previous_digest"])
        self.assertEqual(
            f"MISSION-legacy-{str(legacy['mission_id'])[2:]}", events[0]["mission_id"]
        )
        self.assertEqual(
            f"MISSION-canonical-{str(canonical['mission_id'])[2:]}",
            events[1]["mission_id"],
        )


if __name__ == "__main__":
    unittest.main()
