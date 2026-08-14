from __future__ import annotations

import builtins
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from collections.abc import Mapping, Sequence
from pathlib import Path
from unittest import mock

BIN = Path(__file__).resolve().parents[1] / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

from doctor_checkpoint import (  # noqa: E402
    CheckpointError,
    DoctorValidationSession,
    build_binding,
    discover_test_ids,
    partition_test_ids,
    resume_validation,
)


def _git(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repository), *args),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _outcomes(
    test_ids: Sequence[str],
    *,
    failed: Sequence[str] = (),
    diagnostic: str = "",
) -> dict[str, object]:
    failures = set(failed)
    return {
        "outcomes": [
            {
                "test_id": test_id,
                "status": "FAILED" if test_id in failures else "PASSED",
                "diagnostic": diagnostic,
            }
            for test_id in test_ids
        ]
    }


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], float]] = []

    def __call__(
        self,
        test_ids: Sequence[str],
        timeout_seconds: float,
    ) -> Mapping[str, object]:
        shard = tuple(test_ids)
        self.calls.append((shard, timeout_seconds))
        return _outcomes(shard)


class DoctorCheckpointContractTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repo"
        self.tests_root = self.root / ".autopilot" / "tests"
        self.bin_root = self.root / ".autopilot" / "bin"
        self.store = self.root / ".autopilot" / "state" / "doctor-checkpoints"
        self.tests_root.mkdir(parents=True)
        self.bin_root.mkdir(parents=True)
        (self.root / ".autopilot" / "plan.json").write_text(
            json.dumps(
                {
                    "plan_id": "synthetic-doctor-checkpoint-v1",
                    "nodes": [{"id": "ONLY-000", "dependencies": []}],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        (self.bin_root / "helper.py").write_text(
            "VALUE = 'one'\n",
            encoding="utf-8",
        )
        (self.tests_root / "test_alpha.py").write_text(
            """import unittest


class AlphaTests(unittest.TestCase):
    def test_first(self):
        pass

    def test_second(self):
        pass


class OtherTests(unittest.TestCase):
    def test_third(self):
        pass
""",
            encoding="utf-8",
        )
        (self.tests_root / "test_beta.py").write_text(
            """import unittest


class BetaTests(unittest.TestCase):
    def test_fourth(self):
        pass
""",
            encoding="utf-8",
        )
        _git(self.root, "init", "-q")
        _git(self.root, "config", "user.name", "Checkpoint Contract")
        _git(self.root, "config", "user.email", "checkpoint@example.invalid")
        _git(
            self.root,
            "remote",
            "add",
            "origin",
            "https://example.invalid/acme/synthetic.git",
        )
        _git(self.root, "add", ".autopilot")
        _git(self.root, "commit", "-qm", "synthetic checkpoint fixture")
        self.head = _git(self.root, "rev-parse", "HEAD")
        self.expected_ids = (
            "test_alpha.AlphaTests.test_first",
            "test_alpha.AlphaTests.test_second",
            "test_alpha.OtherTests.test_third",
            "test_beta.BetaTests.test_fourth",
        )
        self.expected_shards = (
            self.expected_ids[:2],
            self.expected_ids[2:3],
            self.expected_ids[3:],
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def binding(
        self,
        *,
        environment: Mapping[str, str] | None = None,
        interpreter: Sequence[str] | None = None,
    ) -> Mapping[str, object]:
        return build_binding(
            self.root,
            environment=environment or {"DOCTOR_MODE": "strict"},
            interpreter=interpreter,
        )

    def validate(
        self,
        runner: object,
        *,
        store: Path | None = None,
        binding: Mapping[str, object] | None = None,
        test_ids: Sequence[str] | None = None,
        timeout_seconds: float = 2.0,
    ) -> DoctorValidationSession:
        return resume_validation(
            self.root,
            store or self.store,
            binding=binding or self.binding(),
            test_ids=test_ids or self.expected_ids,
            runner=runner,
            timeout_seconds=timeout_seconds,
        )

    def assert_content_addressed(self, session: DoctorValidationSession) -> None:
        self.assertRegex(session.session_id, r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            session.session_dir.name,
            session.session_id.removeprefix("sha256:"),
        )
        self.assertTrue(session.session_dir.is_relative_to(self.store.resolve()))

    def test_discovery_freezes_the_exact_ordered_vector_and_class_shards(self) -> None:
        discovered = discover_test_ids(self.root)
        self.assertIsInstance(discovered, tuple)
        self.assertEqual(discovered, self.expected_ids)
        self.assertEqual(partition_test_ids(discovered), self.expected_shards)
        flattened = tuple(test_id for shard in self.expected_shards for test_id in shard)
        self.assertEqual(flattened, discovered)

    def test_partition_rejects_duplicate_malformed_and_noncanonical_order(self) -> None:
        invalid_vectors = (
            (self.expected_ids[0], self.expected_ids[0]),
            ("not-a-unittest-id",),
            tuple(reversed(self.expected_ids)),
            (
                self.expected_ids[0],
                self.expected_ids[2],
                self.expected_ids[1],
                self.expected_ids[3],
            ),
        )
        for vector in invalid_vectors:
            with self.subTest(vector=vector), self.assertRaises(CheckpointError):
                partition_test_ids(vector)

    def test_binding_covers_repo_manifest_plan_interpreter_and_hashed_environment(
        self,
    ) -> None:
        secret = "private-binding-value-must-not-persist"
        binding = self.binding(
            environment={"DOCTOR_MODE": "strict", "API_TOKEN": secret},
            interpreter=(sys.executable, "-I"),
        )
        rendered = json.dumps(binding, sort_keys=True)
        self.assertNotIn(secret, rendered)
        self.assertEqual(binding["schema_version"], 1)
        self.assertEqual(binding["repository"]["root"], self.root.resolve().as_posix())
        self.assertEqual(binding["repository"]["head"], self.head)
        self.assertEqual(
            binding["repository"]["origin"],
            "https://example.invalid/acme/synthetic.git",
        )
        self.assertEqual(binding["interpreter"]["argv"], [sys.executable, "-I"])
        self.assertIn("version", binding["interpreter"])
        self.assertEqual(
            set(binding["environment"]),
            {"API_TOKEN", "DOCTOR_MODE"},
        )
        for digest in binding["environment"].values():
            self.assertRegex(digest, r"^sha256:[0-9a-f]{64}$")
        for name in ("digest",):
            self.assertRegex(binding[name], r"^sha256:[0-9a-f]{64}$")
        for section in ("autopilot_manifest", "plan"):
            self.assertRegex(binding[section]["digest"], r"^sha256:[0-9a-f]{64}$")

    def test_every_binding_input_changes_the_content_addressed_session(self) -> None:
        runner = RecordingRunner()
        baseline_binding = self.binding()
        baseline = self.validate(runner, binding=baseline_binding)
        session_ids = {baseline.session_id}

        plan = self.root / ".autopilot" / "plan.json"
        original_plan = plan.read_text(encoding="utf-8")
        plan.write_text(original_plan.replace("ONLY-000", "ONLY-001"), encoding="utf-8")
        plan_binding = self.binding()
        session_ids.add(self.validate(RecordingRunner(), binding=plan_binding).session_id)
        plan.write_text(original_plan, encoding="utf-8")

        helper = self.bin_root / "helper.py"
        helper.write_text("VALUE = 'two'\n", encoding="utf-8")
        manifest_binding = self.binding()
        session_ids.add(
            self.validate(RecordingRunner(), binding=manifest_binding).session_id
        )
        helper.write_text("VALUE = 'one'\n", encoding="utf-8")

        environment_binding = self.binding(environment={"DOCTOR_MODE": "other"})
        session_ids.add(
            self.validate(RecordingRunner(), binding=environment_binding).session_id
        )

        interpreter_binding = self.binding(interpreter=(sys.executable, "-I"))
        session_ids.add(
            self.validate(RecordingRunner(), binding=interpreter_binding).session_id
        )

        self.assertEqual(len(session_ids), 5)
        # Durable receipts are runtime state, not an input to the byte manifest.
        self.assertEqual(self.binding(), baseline_binding)

    def test_timeout_returns_pending_and_resume_runs_only_missing_shards(self) -> None:
        calls: list[tuple[str, ...]] = []

        def timeout_after_one(
            test_ids: Sequence[str],
            timeout_seconds: float,
        ) -> Mapping[str, object]:
            del timeout_seconds
            shard = tuple(test_ids)
            calls.append(shard)
            if len(calls) == 2:
                raise subprocess.TimeoutExpired(("synthetic",), 0.01)
            return _outcomes(shard)

        pending = self.validate(timeout_after_one, timeout_seconds=0.01)
        self.assertIsInstance(pending, DoctorValidationSession)
        self.assertEqual(pending.state, "PENDING")
        self.assertEqual(pending.completed_test_ids, self.expected_shards[0])
        self.assertEqual(
            pending.missing_test_ids,
            self.expected_shards[1] + self.expected_shards[2],
        )
        self.assert_content_addressed(pending)
        self.assertEqual(len(pending.receipt_paths), 1)
        self.assertFalse(any(p.name.endswith(".tmp") for p in pending.session_dir.rglob("*")))

        resumed_runner = RecordingRunner()
        resumed = self.validate(resumed_runner, timeout_seconds=0.01)
        self.assertEqual(resumed.session_id, pending.session_id)
        self.assertEqual(resumed.session_dir, pending.session_dir)
        self.assertEqual(resumed.state, "PASSED")
        self.assertEqual(
            [call[0] for call in resumed_runner.calls],
            list(self.expected_shards[1:]),
        )
        self.assertEqual(resumed.completed_test_ids, self.expected_ids)
        self.assertEqual(resumed.missing_test_ids, ())
        self.assertEqual(
            tuple(outcome["test_id"] for outcome in resumed.outcomes),
            self.expected_ids,
        )
        self.assertEqual(len(resumed.receipt_paths), len(self.expected_shards))

        no_rerun = RecordingRunner()
        terminal = self.validate(no_rerun)
        self.assertEqual(terminal.state, "PASSED")
        self.assertEqual(no_rerun.calls, [])

    def test_failed_shard_finalizes_and_reopens_the_same_adverse_ledger(self) -> None:
        shard = self.expected_shards[0]

        def failing_runner(
            test_ids: Sequence[str],
            timeout_seconds: float,
        ) -> Mapping[str, object]:
            del timeout_seconds
            return _outcomes(test_ids, failed=(test_ids[0],), diagnostic="assertion")

        failed = self.validate(failing_runner, test_ids=shard)
        self.assertEqual(failed.state, "FAILED")
        self.assertEqual(failed.completed_test_ids, shard)
        self.assertEqual(failed.missing_test_ids, ())
        self.assertEqual(len(failed.receipt_paths), 1)

        forbidden = RecordingRunner()
        reopened = self.validate(forbidden, test_ids=shard)
        self.assertEqual(forbidden.calls, [])
        self.assertEqual(reopened.session_id, failed.session_id)
        self.assertEqual(reopened.session_dir, failed.session_dir)
        self.assertEqual(reopened.state, "FAILED")
        self.assertEqual(reopened.outcomes, failed.outcomes)

    def test_composite_is_an_exact_ordered_bijection_of_the_frozen_vector(self) -> None:
        complete = self.validate(RecordingRunner())
        observed = tuple(outcome["test_id"] for outcome in complete.outcomes)
        self.assertEqual(complete.state, "PASSED")
        self.assertEqual(observed, self.expected_ids)
        self.assertEqual(len(observed), len(set(observed)))
        for path in complete.receipt_paths:
            self.assertTrue(path.is_file())
            json.loads(path.read_text(encoding="utf-8"))
        self.assertFalse(any(p.name.endswith(".tmp") for p in complete.session_dir.rglob("*")))

    def test_runner_receipt_rejects_missing_duplicate_foreign_order_and_status(self) -> None:
        shard = self.expected_shards[0]
        cases = {
            "missing": _outcomes(shard[:1]),
            "duplicate": _outcomes((shard[0], shard[0])),
            "foreign": _outcomes((shard[0], "foreign.Case.test_intruder")),
            "order": _outcomes(tuple(reversed(shard))),
            "status": {
                "outcomes": [
                    {"test_id": test_id, "status": "UNKNOWN", "diagnostic": ""}
                    for test_id in shard
                ]
            },
        }
        for label, result in cases.items():
            case_store = self.store / label

            def invalid_runner(
                test_ids: Sequence[str],
                timeout_seconds: float,
                result: Mapping[str, object] = result,
            ) -> Mapping[str, object]:
                del test_ids, timeout_seconds
                return result

            with self.subTest(label=label), self.assertRaises(CheckpointError):
                self.validate(invalid_runner, store=case_store, test_ids=shard)

    def test_tampered_receipt_fails_closed_before_any_rerun(self) -> None:
        complete = self.validate(RecordingRunner(), test_ids=self.expected_shards[0])
        receipt = complete.receipt_paths[0]
        document = json.loads(receipt.read_text(encoding="utf-8"))
        document["outcomes"][0]["status"] = "FAILED"
        receipt.write_text(json.dumps(document), encoding="utf-8")
        forbidden = RecordingRunner()
        with self.assertRaises(CheckpointError):
            self.validate(forbidden, test_ids=self.expected_shards[0])
        self.assertEqual(forbidden.calls, [])

    def test_malformed_receipt_fails_closed_before_any_rerun(self) -> None:
        complete = self.validate(RecordingRunner(), test_ids=self.expected_shards[0])
        complete.receipt_paths[0].write_text("{not-json", encoding="utf-8")
        forbidden = RecordingRunner()
        with self.assertRaises(CheckpointError):
            self.validate(forbidden, test_ids=self.expected_shards[0])
        self.assertEqual(forbidden.calls, [])

    def test_foreign_session_receipt_fails_closed(self) -> None:
        shard = self.expected_shards[0]
        first = self.validate(RecordingRunner(), test_ids=shard)
        foreign_binding = self.binding(environment={"DOCTOR_MODE": "foreign"})
        second = self.validate(
            RecordingRunner(),
            binding=foreign_binding,
            test_ids=shard,
        )
        first.receipt_paths[0].write_bytes(second.receipt_paths[0].read_bytes())
        with self.assertRaises(CheckpointError):
            self.validate(RecordingRunner(), test_ids=shard)

    def test_symlinked_receipt_fails_closed_when_supported(self) -> None:
        shard = self.expected_shards[0]
        complete = self.validate(RecordingRunner(), test_ids=shard)
        receipt = complete.receipt_paths[0]
        outside = Path(self.temporary.name) / "outside-receipt.json"
        outside.write_bytes(receipt.read_bytes())
        receipt.unlink()
        try:
            os.symlink(outside, receipt)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")
        with self.assertRaises(CheckpointError):
            self.validate(RecordingRunner(), test_ids=shard)

    def test_repo_discovery_and_store_traversal_fail_closed(self) -> None:
        outside_store = Path(self.temporary.name) / "outside-store"
        with self.assertRaises(CheckpointError):
            self.validate(RecordingRunner(), store=outside_store)
        with self.assertRaises(CheckpointError):
            discover_test_ids(self.root, start_dir="../outside")
        with self.assertRaises(CheckpointError):
            discover_test_ids(self.root, start_dir=".autopilot/../.git")

    def test_store_symlink_fails_closed_when_supported(self) -> None:
        outside = Path(self.temporary.name) / "outside-store"
        outside.mkdir()
        self.store.parent.mkdir(parents=True)
        try:
            os.symlink(outside, self.store, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"directory symlink creation unavailable: {error}")
        with self.assertRaises(CheckpointError):
            self.validate(RecordingRunner())

    def test_same_session_lock_is_fail_fast_and_prevents_double_execution(self) -> None:
        shard = self.expected_shards[0]
        entered = threading.Event()
        release = threading.Event()
        first_result: list[DoctorValidationSession] = []
        first_error: list[BaseException] = []

        def blocking_runner(
            test_ids: Sequence[str],
            timeout_seconds: float,
        ) -> Mapping[str, object]:
            del timeout_seconds
            entered.set()
            if not release.wait(timeout=5):
                raise AssertionError("test failed to release the synthetic runner")
            return _outcomes(test_ids)

        def first_call() -> None:
            try:
                first_result.append(self.validate(blocking_runner, test_ids=shard))
            except BaseException as error:  # pragma: no cover - asserted below
                first_error.append(error)

        worker = threading.Thread(target=first_call, daemon=True)
        worker.start()
        self.assertTrue(entered.wait(timeout=5), "first validation never entered runner")
        competing = RecordingRunner()
        try:
            with self.assertRaisesRegex(CheckpointError, r"(?i)lock|busy|active"):
                self.validate(competing, test_ids=shard)
        finally:
            release.set()
            worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(first_error, [])
        self.assertEqual(len(first_result), 1)
        self.assertEqual(first_result[0].state, "PASSED")
        self.assertEqual(competing.calls, [])

    def test_secret_values_from_environment_diagnostics_and_timeout_never_persist(
        self,
    ) -> None:
        secret = "github_pat_private_doctor_checkpoint_value"
        binding = self.binding(environment={"API_TOKEN": secret})
        calls = 0

        def sensitive_runner(
            test_ids: Sequence[str],
            timeout_seconds: float,
        ) -> Mapping[str, object]:
            nonlocal calls
            del timeout_seconds
            calls += 1
            if calls == 1:
                return _outcomes(test_ids, diagnostic=f"runner said token={secret}")
            raise subprocess.TimeoutExpired(
                ("synthetic",),
                0.01,
                stderr=f"transport exposed {secret}",
            )

        pending = self.validate(sensitive_runner, binding=binding, timeout_seconds=0.01)
        self.assertEqual(pending.state, "PENDING")
        persisted = b"\n".join(
            path.read_bytes() for path in self.store.rglob("*") if path.is_file()
        )
        self.assertNotIn(secret.encode("utf-8"), persisted)
        self.assertIn(b"[REDACTED]", persisted)

    def test_module_load_and_runtime_do_not_depend_on_ambient_hive_mind_os(
        self,
    ) -> None:
        module_path = BIN / "doctor_checkpoint.py"
        module_name = "isolated_doctor_checkpoint_contract"
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        isolated = importlib.util.module_from_spec(spec)
        original_import = builtins.__import__

        def guarded_import(
            name: str,
            globals: Mapping[str, object] | None = None,
            locals: Mapping[str, object] | None = None,
            fromlist: Sequence[str] = (),
            level: int = 0,
        ) -> object:
            if name == "hive_mind_os" or name.startswith("hive_mind_os."):
                raise AssertionError(f"ambient package import attempted: {name}")
            return original_import(name, globals, locals, fromlist, level)

        sys.modules[module_name] = isolated
        try:
            with mock.patch("builtins.__import__", side_effect=guarded_import):
                spec.loader.exec_module(isolated)
                binding = isolated.build_binding(
                    self.root,
                    environment={"DOCTOR_MODE": "isolated"},
                )
                self.assertRegex(binding["digest"], r"^sha256:[0-9a-f]{64}$")
        finally:
            sys.modules.pop(module_name, None)


if __name__ == "__main__":
    unittest.main()
