from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path

from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.closeout import (
    declare_closeout_obligations,
    integrate_verified_work,
    record_evaluation_bundle,
)
from hive_mind_os.brain_kernel.contracts import (
    HistoricalEvidenceReference,
    RoleResult,
)
from hive_mind_os.brain_kernel.events import KernelEvent
from hive_mind_os.brain_kernel.projection import state_digest
from hive_mind_os.brain_kernel.roles import append_role_result, result_digest
from hive_mind_os.brain_kernel.store import KernelStore
from hive_mind_os.brain_kernel.verification import (
    accept_verified_work,
    create_evaluation_plan,
    seal_evaluation_plan,
    verify_exact_candidate,
)
from hive_mind_os.cli import (
    _run_kernel_closeout,
    _run_kernel_status,
    build_kernel_parser,
)

TIME = "2026-08-08T12:00:00Z"
DIGEST = "sha256:" + "0" * 64
ROOT = Path(__file__).resolve().parents[1]


def _tree_manifest(root: Path) -> tuple[tuple[str, str], ...]:
    return tuple(
        (
            path.relative_to(root).as_posix(),
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LocalCompatibilityFirewallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.receipts = self.root / "legacy-receipts"
        (self.receipts / "nested").mkdir(parents=True)
        (self.receipts / "receipt.json").write_bytes(b'{"legacy":true}\r\n')
        (self.receipts / "nested" / "report.txt").write_bytes(b"legacy report\n")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _append(
        self,
        store: KernelStore,
        event_id: str,
        mission_id: str,
        event_type: str,
        *,
        work_id: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        events = store.events()
        store.append(
            KernelEvent(
                event_id,
                mission_id,
                event_type,
                "fixture",
                TIME,
                payload or {},
                work_id=work_id,
                previous_digest=events[-1]["digest"] if events else None,
            )
        )

    def _running_work(self, store: KernelStore, mission_id: str, work_id: str) -> None:
        self._append(store, f"{mission_id}:created", mission_id, "mission.created")
        self._append(
            store, f"{work_id}:created", mission_id, "work.created", work_id=work_id
        )
        for status in ("READY", "LEASED", "RUNNING"):
            self._append(
                store,
                f"{work_id}:{status}",
                mission_id,
                "work.transition",
                work_id=work_id,
                payload={"status": status},
            )

    def _role_result(self, mission_id: str, work_id: str) -> RoleResult:
        provisional = RoleResult(
            mission_id,
            work_id,
            "ATTEMPT-compatibility",
            "builder",
            "executor:builder",
            DIGEST,
            DIGEST,
            (),
            (),
            ("artifact:builder",),
            ("claim:builder",),
            (),
            (),
            None,
            "local fixture output",
            DIGEST,
        )
        return replace(provisional, result_digest=result_digest(provisional))

    def _stage_store(self, phase: int) -> tuple[KernelStore, Path, str]:
        state_dir = self.root / f"phase-{phase}" / "state"
        state_dir.mkdir(parents=True)
        store = KernelStore(KernelStore.database_path(state_dir))
        mission_id = f"MISSION-phase-{phase}"
        work_id = f"WORK-phase-{phase}"
        self._append(store, f"{mission_id}:created", mission_id, "mission.created")
        if phase >= 3:
            self._append(
                store, f"{work_id}:created", mission_id, "work.created", work_id=work_id
            )
        if phase >= 4:
            for status in ("READY", "LEASED", "RUNNING"):
                self._append(
                    store,
                    f"{work_id}:{status}",
                    mission_id,
                    "work.transition",
                    work_id=work_id,
                    payload={"status": status},
                )
        if phase >= 7:
            append_role_result(
                store, self._role_result(mission_id, work_id), occurred_at=TIME
            )
        if phase >= 8:
            base = self.root / f"phase-{phase}" / "base"
            candidate = self.root / f"phase-{phase}" / "candidate"
            base.mkdir()
            (base / "app.txt").write_text("before\n", encoding="utf-8")
            shutil.copytree(base, candidate)
            (candidate / "app.txt").write_text("after\n", encoding="utf-8")
            plan = create_evaluation_plan(
                f"EVAL-phase-{phase}",
                base,
                acceptance_commands=("content-is-after",),
                allowed_paths=("app.txt",),
            )
            seal_evaluation_plan(
                store, work_id, plan, base_root=base, actor_id="architect"
            )
            self._append(
                store,
                f"{work_id}:awaiting",
                mission_id,
                "work.transition",
                work_id=work_id,
                payload={"status": "AWAITING_VERIFICATION"},
            )
            verify_exact_candidate(
                store,
                work_id,
                plan,
                candidate,
                builder_id="builder:one",
                evaluator_id="curator:two",
                check_runner=lambda _command, root: (root / "app.txt").read_text(
                    encoding="utf-8"
                )
                == "after\n",
                bundle_directory=self.root / f"phase-{phase}" / "bundle",
            )
        store.close()
        return KernelStore.database_path(state_dir), state_dir, mission_id

    def _complete_closeout(
        self, label: str, *, integrate: bool = True
    ) -> tuple[Path, Path, str, str]:
        state_dir = self.root / label / "state"
        state_dir.mkdir(parents=True)
        store = KernelStore(KernelStore.database_path(state_dir))
        mission_id = "MISSION-complete"
        work_id = "WORK-complete"
        self._running_work(store, mission_id, work_id)
        reference = HistoricalEvidenceReference(
            "receipt:legacy",
            canonical_digest(
                {"bytes": (self.receipts / "receipt.json").read_bytes().hex()}
            ),
            "legacy-fixture",
            "retain unchanged",
        )
        declare_closeout_obligations(
            store, mission_id, historical_evidence=(reference,)
        )
        for role, executor in (
            ("orchestrator", "executor:orchestrator"),
            ("explorer", "executor:explorer"),
            ("architect", "executor:architect"),
            ("builder", "executor:builder"),
            ("curator", "executor:curator"),
            ("integrator", "executor:integrator"),
            ("steward", "executor:steward"),
            ("optimizer", "executor:optimizer"),
        ):
            provisional = RoleResult(
                mission_id,
                work_id,
                "ATTEMPT-complete",
                role,
                executor,
                DIGEST,
                DIGEST,
                (),
                (),
                (f"artifact:{role}",),
                (f"claim:{role}",),
                (),
                (),
                None,
                "local fixture output",
                DIGEST,
            )
            append_role_result(
                store,
                replace(provisional, result_digest=result_digest(provisional)),
                occurred_at=TIME,
            )
        base = self.root / label / "base"
        candidate = self.root / label / "candidate"
        base.mkdir(parents=True)
        (base / "app.txt").write_text("before\n", encoding="utf-8")
        shutil.copytree(base, candidate)
        (candidate / "app.txt").write_text("after\n", encoding="utf-8")
        plan = create_evaluation_plan(
            "EVAL-complete",
            base,
            acceptance_commands=("content-is-after",),
            allowed_paths=("app.txt",),
        )
        seal_evaluation_plan(store, work_id, plan, base_root=base, actor_id="architect")
        self._append(
            store,
            f"{work_id}:awaiting",
            mission_id,
            "work.transition",
            work_id=work_id,
            payload={"status": "AWAITING_VERIFICATION"},
        )
        outcome = verify_exact_candidate(
            store,
            work_id,
            plan,
            candidate,
            builder_id="builder:one",
            evaluator_id="curator:two",
            check_runner=lambda _command, root: (root / "app.txt").read_text(
                encoding="utf-8"
            )
            == "after\n",
            bundle_directory=self.root / label / "bundle",
        )
        record_evaluation_bundle(
            store, work_id, outcome.result, outcome.bundle_path, bundle_ref="fixture"
        )
        accept_verified_work(store, work_id, outcome.result, actor_id="integrator")
        if integrate:
            integrate_verified_work(store, work_id, outcome.result)
        store.close()
        return KernelStore.database_path(state_dir), state_dir, mission_id, "fixture"

    def _assert_closeout_read_only(
        self,
        state_dir: Path,
        mission_id: str,
        bundle_ref: list[str],
        expected_status: int,
        expected_text: str | None = None,
    ) -> None:
        receipt_manifest = _tree_manifest(self.receipts)
        database = KernelStore.database_path(state_dir)
        database_digest = _file_digest(database) if database.exists() else None
        events_before: list[dict[str, object]] = []
        projection_before: str | None = None
        if database.exists():
            reader = KernelStore(database, read_only=True)
            events_before = reader.events()
            projection_before = state_digest(reader.projection())
            reader.close()
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(
                expected_status,
                _run_kernel_closeout(
                    argparse.Namespace(
                        mission_id=mission_id,
                        state_dir=str(state_dir),
                        bundle_ref=bundle_ref,
                        json_output=True,
                    )
                ),
            )
        if expected_text is not None:
            self.assertIn(expected_text, stdout.getvalue())
        self.assertEqual(receipt_manifest, _tree_manifest(self.receipts))
        self.assertEqual(
            database_digest, _file_digest(database) if database.exists() else None
        )
        if database.exists():
            reader = KernelStore(database, read_only=True)
            self.assertEqual(events_before, reader.events())
            self.assertEqual(projection_before, state_digest(reader.projection()))
            reader.close()

    def test_closeout_replays_phase_one_through_eight_fixtures_without_mutation(
        self,
    ) -> None:
        for phase in range(1, 9):
            with self.subTest(phase=phase):
                database, state_dir, mission_id = self._stage_store(phase)
                self.assertTrue(database.is_file())
                self._assert_closeout_read_only(state_dir, mission_id, [], 0)

    def test_closeout_preserves_historical_receipt_bytes_for_all_local_outcomes(
        self,
    ) -> None:
        database, state_dir, mission_id, reference = self._complete_closeout("complete")
        bundle = database.parent.parent / "bundle"
        self._assert_closeout_read_only(
            state_dir,
            mission_id,
            [f"{reference}={bundle}"],
            0,
            "TECHNICALLY_VERIFIED",
        )

        blocked = bundle / "verification.json"
        blocked.write_text("{}", encoding="utf-8")
        self._assert_closeout_read_only(
            state_dir,
            mission_id,
            [f"{reference}={bundle}"],
            0,
            "BLOCKED",
        )

        partial_database, partial_state, partial_mission, partial_reference = (
            self._complete_closeout("partial", integrate=False)
        )
        self._assert_closeout_read_only(
            partial_state,
            partial_mission,
            [f"{partial_reference}={partial_database.parent.parent / 'bundle'}"],
            0,
            "PARTIAL",
        )
        self._assert_closeout_read_only(state_dir, mission_id, ["malformed"], 1)
        missing_state = self.root / "missing" / "state"
        self._assert_closeout_read_only(missing_state, "MISSION-missing", [], 1)
        self.assertFalse(missing_state.exists())

    def test_closeout_import_is_lazy_and_legacy_status_route_is_read_only(self) -> None:
        source = (ROOT / "src" / "hive_mind_os" / "cli.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        module_imports = [
            node.module for node in tree.body if isinstance(node, ast.ImportFrom)
        ]
        self.assertNotIn("brain_kernel.closeout", module_imports)
        closeout = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_run_kernel_closeout"
        )
        self.assertIn(
            "brain_kernel.closeout",
            [
                node.module
                for node in ast.walk(closeout)
                if isinstance(node, ast.ImportFrom)
            ],
        )
        probe = subprocess.run(
            (
                sys.executable,
                "-c",
                "import sys; import hive_mind_os.cli; "
                "raise SystemExit(int('hive_mind_os.brain_kernel.closeout' in sys.modules))",
            ),
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, probe.returncode, probe.stderr)
        forbidden = {
            "model_provider",
            "model_backend",
            "prompt_registry",
            "experiment_runner",
            "ledger",
            "git_adapter",
            "github_adapter",
            "socket",
        }
        closeout_source = (
            ROOT / "src" / "hive_mind_os" / "brain_kernel" / "closeout.py"
        ).read_text(encoding="utf-8")
        closeout_imports = {
            node.module.rsplit(".", 1)[-1]
            for node in ast.walk(ast.parse(closeout_source))
            if isinstance(node, ast.ImportFrom) and node.module
        }
        self.assertFalse(forbidden & closeout_imports)
        database, state_dir, mission_id = self._stage_store(1)
        database_digest = _file_digest(database)
        parsed = build_kernel_parser().parse_args(
            ["status", mission_id, "--state-dir", str(state_dir), "--json"]
        )
        self.assertEqual("status", parsed.kernel_command)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(0, _run_kernel_status(parsed))
        self.assertEqual(mission_id, json.loads(stdout.getvalue())["mission_id"])
        self.assertEqual(database_digest, _file_digest(database))


if __name__ == "__main__":
    unittest.main()
