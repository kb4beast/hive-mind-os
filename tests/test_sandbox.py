from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import patch

from hive_mind_os.autonomy import EpisodeAllowance
from hive_mind_os.contracts import (
    tool_intent_digest,
    validate_contract,
)
from hive_mind_os.ledger import EvidenceLedger
from hive_mind_os.models import Role
from hive_mind_os.receipts import (
    FileReceiptValidator,
    ReceiptReference,
    sha256_digest,
)
from hive_mind_os.sandbox import (
    ConfinementViolation,
    SandboxDenied,
    SandboxRunner,
    SandboxSpec,
    SandboxTimeout,
)


class SandboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.root = self.base / "workspace"
        self.trusted = self.base / "evidence"
        self.root.mkdir()
        self.python_name = Path(sys.executable).name

    def spec(self, **overrides: Any) -> SandboxSpec:
        values: dict[str, Any] = {
            "root": self.root,
            "argv_allowlist": (self.python_name,),
            "timeout_s": 5.0,
            "max_output_bytes": 4096,
        }
        values.update(overrides)
        return SandboxSpec(**values)

    def runner(
        self,
        *,
        spec: SandboxSpec | None = None,
        allowance: EpisodeAllowance | None = None,
        role: Role = Role.BUILDER,
        trusted: Path | None = None,
        ledger: EvidenceLedger | None = None,
    ) -> SandboxRunner:
        return SandboxRunner(
            spec or self.spec(),
            trusted or self.trusted,
            allowance or EpisodeAllowance(20, 100.0),
            role=role,
            ledger=ledger,
        )

    def intent(
        self,
        argv: list[str],
        *,
        path_args: list[int] | None = None,
        action_id: str = "ACT-sandbox-1",
    ) -> dict[str, Any]:
        document: dict[str, Any] = {
            "schema_version": 1,
            "action_id": action_id,
            "mission_id": "mission-sandbox",
            "state_ref": "MISSION_STATE:mission-sandbox:1",
            "actor_id": "builder-pass-1",
            "kind": "command",
            "description": "execute a bounded sandbox command",
            "action_digest": f"sha256:{'0' * 64}",
            "policy_decision_ref": "POLICY-sandbox-1",
            "lease_id": "LEASE-sandbox-1",
            "idempotency_key": action_id,
            "rollback_ref": None,
            "command": {
                "argv": argv,
                "path_args": path_args or [],
            },
            "status": "proposed",
        }
        document["action_digest"] = tool_intent_digest(document)
        return document

    def stdout(self, receipt: dict[str, Any], trusted: Path | None = None) -> bytes:
        root = trusted or self.trusted
        artifact = receipt["artifacts"][0]
        return (root / artifact["path"]).read_bytes()

    def test_happy_path_receipt_round_trips_through_validator(self) -> None:
        runner = self.runner()
        intent = self.intent([sys.executable, "-c", "print('hi')"])
        receipt = runner.run(intent)
        self.assertTrue(validate_contract("tool-receipt", receipt).valid)
        self.assertEqual(self.stdout(receipt).splitlines(), [b"hi"])
        self.assertIsNotNone(runner.last_reference)
        assert runner.last_reference is not None
        validation = FileReceiptValidator(self.trusted).validate(
            runner.last_reference,
            mission_id=intent["mission_id"],
            state_ref=intent["state_ref"],
            actor_id=intent["actor_id"],
            action_id=intent["action_id"],
            action_kind=intent["kind"],
            action_digest=intent["action_digest"],
        )
        self.assertTrue(validation.valid, validation.issues)
        self.assertTrue(validation.succeeded)

    def test_intent_digest_binds_every_declared_field(self) -> None:
        runner = self.runner()
        intent = self.intent([sys.executable, "-c", "print('bound')"])
        intent["description"] = "mutated after digest"
        with self.assertRaisesRegex(SandboxDenied, "digest"):
            runner.run(intent)
        self.assertEqual(runner.spawn_count, 0)

        missing_command = dict(intent)
        missing_command["action_digest"] = f"sha256:{'0' * 64}"
        missing_command.pop("command")
        missing_command["action_digest"] = tool_intent_digest(missing_command)
        self.assertFalse(validate_contract("tool-intent", missing_command).valid)

    def test_non_allowlisted_executable_is_denied_before_spawn(self) -> None:
        runner = self.runner()
        intent = self.intent(["definitely-not-a-hive-executable", "--version"])
        with self.assertRaisesRegex(SandboxDenied, "allowlisted"):
            runner.run(intent)
        self.assertEqual(runner.spawn_count, 0)
        self.assertFalse((self.trusted / "receipts").exists())

    def test_parent_path_escape_is_rejected(self) -> None:
        runner = self.runner()
        intent = self.intent(
            [sys.executable, "-c", "print('no spawn')", "../outside.txt"],
            path_args=[3],
        )
        with self.assertRaises(ConfinementViolation):
            runner.run(intent)
        self.assertEqual(runner.spawn_count, 0)

    @unittest.skipIf(os.name == "nt", "POSIX-only symlink confinement case")
    def test_symlink_escape_is_rejected(self) -> None:
        outside = self.base / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        (self.root / "link.txt").symlink_to(outside)
        runner = self.runner()
        intent = self.intent(
            [sys.executable, "-c", "print('no spawn')", "link.txt"],
            path_args=[3],
        )
        with self.assertRaises(ConfinementViolation):
            runner.run(intent)
        self.assertEqual(runner.spawn_count, 0)

    def test_environment_is_scrubbed_unless_allowlisted(self) -> None:
        name = "HIVE_MIND_SANDBOX_SENTINEL"
        code = f"import os;print(os.environ.get({name!r}, 'absent'))"
        with patch.dict(os.environ, {name: "present"}):
            absent_runner = self.runner(trusted=self.base / "absent-evidence")
            absent = absent_runner.run(
                self.intent([sys.executable, "-c", code], action_id="ACT-env-absent")
            )
            allowed_runner = self.runner(
                spec=self.spec(env_allowlist=(name,)),
                trusted=self.base / "allowed-evidence",
            )
            allowed = allowed_runner.run(
                self.intent([sys.executable, "-c", code], action_id="ACT-env-allowed")
            )
        self.assertEqual(
            self.stdout(absent, self.base / "absent-evidence").splitlines(),
            [b"absent"],
        )
        self.assertEqual(
            self.stdout(allowed, self.base / "allowed-evidence").splitlines(),
            [b"present"],
        )

    def test_timeout_kills_process_tree_and_leaves_failed_receipt(self) -> None:
        marker = self.root / "survived.txt"
        child = (
            "import pathlib,time;"
            "time.sleep(0.8);"
            "pathlib.Path('survived.txt').write_text('not killed')"
        )
        parent = (
            "import subprocess,sys,time;"
            f"subprocess.Popen([sys.executable,'-c',{child!r}]);"
            "time.sleep(5)"
        )
        runner = self.runner(spec=self.spec(timeout_s=0.2))
        started = time.monotonic()
        with self.assertRaises(SandboxTimeout) as captured:
            runner.run(self.intent([sys.executable, "-c", parent]))
        self.assertLess(time.monotonic() - started, 2.0)
        receipt = captured.exception.receipt
        self.assertEqual(receipt["execution"]["outcome"], "timeout")
        self.assertEqual(receipt["result"], "failed")
        self.assertIsNotNone(runner.last_reference)
        time.sleep(1.0)
        self.assertFalse(marker.exists())

    def test_timeout_covers_early_parent_exit_and_background_child(self) -> None:
        marker = self.root / "background-survived.txt"
        child = (
            "import pathlib,time;"
            "time.sleep(0.8);"
            "pathlib.Path('background-survived.txt').write_text('not killed')"
        )
        parent = (
            "import subprocess,sys;"
            f"subprocess.Popen([sys.executable,'-c',{child!r}],"
            "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)"
        )
        runner = self.runner(spec=self.spec(timeout_s=0.2))
        started = time.monotonic()
        with self.assertRaises(SandboxTimeout) as captured:
            runner.run(self.intent([sys.executable, "-c", parent]))
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(captured.exception.receipt["execution"]["outcome"], "timeout")
        time.sleep(1.0)
        self.assertFalse(marker.exists())

    def test_output_cap_is_explicit_and_digest_bound(self) -> None:
        runner = self.runner(spec=self.spec(max_output_bytes=100))
        receipt = runner.run(
            self.intent(
                [sys.executable, "-c", "import sys;sys.stdout.buffer.write(b'x'*4096)"]
            )
        )
        stdout = self.stdout(receipt)
        stream = receipt["execution"]["stdout"]
        self.assertEqual(stdout, b"x" * 100)
        self.assertEqual(stream["bytes"], 100)
        self.assertTrue(stream["truncated"])
        self.assertEqual(stream["digest"], sha256_digest(stdout))

    def test_policy_denial_occurs_before_spawn(self) -> None:
        runner = self.runner(role=Role.EXPLORER)
        with self.assertRaisesRegex(SandboxDenied, "read-only"):
            runner.run(self.intent([sys.executable, "-c", "print('denied')"]))
        self.assertEqual(runner.spawn_count, 0)

    def test_exhausted_allowance_occurs_before_spawn(self) -> None:
        runner = self.runner(allowance=EpisodeAllowance(0, 0.0))
        with self.assertRaisesRegex(SandboxDenied, "allowance exhausted"):
            runner.run(self.intent([sys.executable, "-c", "print('denied')"]))
        self.assertEqual(runner.spawn_count, 0)

    def test_concurrent_calls_cannot_overbook_one_call_allowance(self) -> None:
        barrier = threading.Barrier(2)

        class SynchronizedRunner(SandboxRunner):
            def _validate_intent(self, intent: dict[str, Any]) -> None:
                super()._validate_intent(intent)
                barrier.wait(timeout=2)

        runner = SynchronizedRunner(
            self.spec(),
            self.trusted,
            EpisodeAllowance(1, 1.0),
        )
        intents = [
            self.intent(
                [sys.executable, "-c", "print('one')"],
                action_id=f"ACT-concurrent-{index}",
            )
            for index in range(2)
        ]

        def invoke(intent: dict[str, Any]) -> str:
            try:
                runner.run(intent)
            except SandboxDenied:
                return "denied"
            return "succeeded"

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(invoke, intents))
        self.assertEqual(sorted(outcomes), ["denied", "succeeded"])
        self.assertEqual(runner.tool_calls_used, 1)
        self.assertEqual(runner.spawn_count, 1)

    def test_all_pre_spawn_denials_append_ledger_evidence(self) -> None:
        cases: list[tuple[str, dict[str, Any], type[SandboxDenied]]] = []
        invalid_digest = self.intent([sys.executable, "-c", "print('no')"])
        invalid_digest["description"] = "mutated"
        cases.append(("digest", invalid_digest, SandboxDenied))
        escape = self.intent(
            [sys.executable, "-c", "print('no')", "../outside.txt"],
            path_args=[3],
        )
        cases.append(("escape", escape, ConfinementViolation))
        embedded_nul = self.intent([sys.executable, "-c", "print('no')\x00"])
        cases.append(("nul", embedded_nul, SandboxDenied))

        for label, intent, error_type in cases:
            with self.subTest(case=label):
                ledger = EvidenceLedger()
                runner = self.runner(
                    trusted=self.base / f"{label}-evidence",
                    ledger=ledger,
                )
                with self.assertRaises(error_type):
                    runner.run(intent)
                denials = [
                    event
                    for event in ledger.events()
                    if event["event_type"] == "sandbox.denied"
                ]
                self.assertEqual(len(denials), 1)
                self.assertEqual(runner.spawn_count, 0)

    def test_subprocess_creation_error_is_a_receipted_denial(self) -> None:
        class FailingRunner(SandboxRunner):
            def _spawn(self, argv: list[str]) -> subprocess.Popen[bytes]:
                raise subprocess.SubprocessError("simulated child setup failure")

        ledger = EvidenceLedger()
        runner = FailingRunner(
            self.spec(),
            self.trusted,
            EpisodeAllowance(1, 1.0),
            ledger=ledger,
        )
        with self.assertRaisesRegex(SandboxDenied, "SubprocessError"):
            runner.run(self.intent([sys.executable, "-c", "print('no')"]))
        self.assertEqual(runner.spawn_count, 0)
        self.assertEqual(
            [event["event_type"] for event in ledger.events()],
            ["sandbox.denied"],
        )

    def test_non_object_intent_is_a_receipted_schema_denial(self) -> None:
        ledger = EvidenceLedger()
        runner = self.runner(ledger=ledger)
        with self.assertRaises(SandboxDenied):
            runner.run([])  # type: ignore[arg-type]
        self.assertEqual(runner.spawn_count, 0)
        events = ledger.events()
        self.assertEqual([event["event_type"] for event in events], ["sandbox.denied"])
        self.assertEqual(events[0]["payload"]["action_id"], None)

    def test_interrupted_publish_leaves_no_receipt_claim(self) -> None:
        class InterruptedRunner(SandboxRunner):
            def _atomic_write(self, relative: str, content: bytes) -> None:
                if relative.startswith("receipts/"):
                    raise OSError("simulated receipt publish interruption")
                super()._atomic_write(relative, content)

        runner = InterruptedRunner(
            self.spec(),
            self.trusted,
            EpisodeAllowance(20, 100.0),
        )
        with self.assertRaisesRegex(OSError, "simulated"):
            runner.run(self.intent([sys.executable, "-c", "print('orphan')"]))
        self.assertIsNone(runner.last_reference)
        receipts = self.trusted / "receipts"
        self.assertFalse(receipts.exists() and any(receipts.iterdir()))
        absent = ReceiptReference(
            f"receipts/{'0' * 64}.json",
            f"sha256:{'0' * 64}",
        )
        validation = FileReceiptValidator(self.trusted).validate(
            absent,
            mission_id="mission-sandbox",
            state_ref="MISSION_STATE:mission-sandbox:1",
            actor_id="builder-pass-1",
            action_id="ACT-sandbox-1",
            action_kind="command",
            action_digest=f"sha256:{'0' * 64}",
        )
        self.assertFalse(validation.valid)

    def test_repeat_execution_differs_only_in_volatile_receipt_fields(self) -> None:
        runner = self.runner()
        intent = self.intent([sys.executable, "-c", "print('stable')"])
        first = runner.run(intent)
        second = runner.run(intent)
        self.assertEqual(tool_intent_digest(intent), intent["action_digest"])

        def normalize(receipt: dict[str, Any]) -> dict[str, Any]:
            normalized = deepcopy(receipt)
            normalized["receipt_id"] = "<receipt-id>"
            normalized["execution_id"] = "<execution-id>"
            normalized["observed_at"] = "<timestamp>"
            normalized["execution"]["duration_ms"] = 0
            for artifact in normalized["artifacts"]:
                artifact["created_at"] = "<timestamp>"
            return normalized

        self.assertEqual(normalize(first), normalize(second))

    def test_golden_intent_and_receipt_conform_to_extended_contracts(self) -> None:
        fixture_root = Path(__file__).parent / "fixtures" / "sandbox"
        intent = json.loads((fixture_root / "intent.json").read_text(encoding="utf-8"))
        receipt = json.loads(
            (fixture_root / "receipt.json").read_text(encoding="utf-8")
        )
        self.assertEqual(intent["action_digest"], tool_intent_digest(intent))
        self.assertTrue(validate_contract("tool-intent", intent).valid)
        self.assertTrue(validate_contract("tool-receipt", receipt).valid)

    def test_trusted_receipt_store_cannot_be_inside_workspace(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside"):
            self.runner(trusted=self.root / "untrusted-receipts")


if __name__ == "__main__":
    unittest.main()
