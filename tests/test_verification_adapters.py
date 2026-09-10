from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hive_mind_os.verification_adapters import (
    LocalProcessSandbox,
    SandboxRequirements,
    VerificationBudget,
    VerificationError,
    VerificationRegistry,
    verify_repository,
)


class VerificationAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "FOO BAR"
        self.repo.mkdir()

    def trusted(self, *, wall_seconds: float = 30) -> dict:
        return {
            "sandbox": LocalProcessSandbox(),
            "requirements": SandboxRequirements(network_policy="inherit", hostile_code_isolation=False),
            "budget": VerificationBudget(wall_seconds=wall_seconds),
        }

    def test_trusted_local_process_does_not_claim_memory_isolation(self) -> None:
        capabilities = LocalProcessSandbox().capabilities
        self.assertFalse(capabilities.hostile_code_isolation)
        self.assertFalse(capabilities.cpu_memory_limits)

    def test_python_unittest_receipt_is_sealed_and_content_addressed(self) -> None:
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "test_ok.py").write_text(
            "import unittest\nclass T(unittest.TestCase):\n    def test_ok(self): self.assertTrue(True)\n",
            encoding="utf-8",
        )
        evidence = self.root / "python-evidence"
        receipt = verify_repository(self.repo, evidence_directory=evidence, **self.trusted())
        self.assertEqual(
            "PASSED", receipt["status"],
            Path(receipt["stderr"]["path"]).read_text(encoding="utf-8", errors="replace"),
        )
        self.assertEqual("python-unittest", receipt["adapter_id"])
        self.assertTrue(receipt["sealed_command_digest"].startswith("sha256:"))
        self.assertIn("Python", receipt["tool_version"]["text"])
        self.assertEqual(receipt, json.loads((evidence / "receipt.json").read_bytes()))

    def test_python_adapter_does_not_inherit_secrets(self) -> None:
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "test_environment.py").write_text(
            "import os, unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_secret_absent(self): self.assertNotIn('HIVE_ACCEPTANCE_SECRET', os.environ)\n",
            encoding="utf-8",
        )
        with mock.patch.dict(os.environ, {"HIVE_ACCEPTANCE_SECRET": "must-not-leak"}):
            receipt = verify_repository(
                self.repo, evidence_directory=self.root / "secret-evidence", **self.trusted()
            )
        self.assertEqual("PASSED", receipt["status"])
        self.assertNotIn("HIVE_ACCEPTANCE_SECRET", receipt["environment"])

    @unittest.skipUnless(os.name == "nt", "Windows operator identity behavior")
    def test_python_adapter_retains_receipted_windows_username(self) -> None:
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "test_operator.py").write_text(
            "import getpass, unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_operator(self): self.assertEqual('hive-verifier', getpass.getuser())\n",
            encoding="utf-8",
        )
        with mock.patch.dict(os.environ, {"USERNAME": "hive-verifier"}):
            receipt = verify_repository(
                self.repo,
                evidence_directory=self.root / "operator-evidence",
                **self.trusted(),
            )
        self.assertEqual(
            "PASSED",
            receipt["status"],
            Path(receipt["stderr"]["path"]).read_text(
                encoding="utf-8", errors="replace"
            ),
        )
        self.assertIn("USERNAME", receipt["environment"])

    def test_python_adapter_provides_verification_scoped_temporary_storage(self) -> None:
        (self.repo / "tests").mkdir()
        (self.repo / ".hive-verification" / "tmp").mkdir(parents=True)
        (self.repo / "tests" / "test_temporary_storage.py").write_text(
            "import os, pathlib, tempfile, unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_temp_is_scoped(self):\n"
            "        root = pathlib.Path.cwd().resolve()\n"
            "        temp = pathlib.Path(tempfile.gettempdir()).resolve()\n"
            "        self.assertEqual(root.parent / 'tmp', temp, (temp, root, dict(os.environ)))\n",
            encoding="utf-8",
        )
        receipt = verify_repository(
            self.repo,
            evidence_directory=self.root / "temporary-storage-evidence",
            **self.trusted(),
        )
        self.assertEqual(
            "PASSED",
            receipt["status"],
            Path(receipt["stderr"]["path"]).read_text(
                encoding="utf-8", errors="replace"
            ),
        )
        self.assertTrue({"TEMP", "TMP", "TMPDIR"}.issubset(receipt["environment"]))

    def test_default_hostile_sandbox_requirement_fails_closed_before_writes(self) -> None:
        evidence = self.root / "blocked-evidence"
        receipt = verify_repository(self.repo, evidence_directory=evidence)
        self.assertEqual("BLOCKED", receipt["status"])
        self.assertIn("sandbox", receipt["reason"])
        self.assertEqual(receipt, json.loads((evidence / "receipt.json").read_bytes()))

    def test_no_compatible_adapter_is_an_obligation_not_a_pass(self) -> None:
        evidence = self.root / "missing-evidence"
        receipt = verify_repository(self.repo, evidence_directory=evidence, **self.trusted())
        self.assertEqual("VERIFICATION_OBLIGATION", receipt["status"])
        self.assertEqual(receipt, json.loads((evidence / "receipt.json").read_bytes()))

    def test_failed_test_is_durable_and_never_reported_as_passed(self) -> None:
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "test_fail.py").write_text(
            "import unittest\nclass T(unittest.TestCase):\n    def test_fail(self): self.fail('expected')\n",
            encoding="utf-8",
        )
        evidence = self.root / "failed-evidence"
        receipt = verify_repository(self.repo, evidence_directory=evidence, **self.trusted())
        self.assertEqual("FAILED", receipt["status"])
        self.assertNotEqual(0, receipt["exit_code"])
        self.assertEqual(receipt, json.loads((evidence / "receipt.json").read_bytes()))

    @unittest.skipUnless(shutil.which("node"), "Node is unavailable")
    def test_node_typescript_adapter_runs_node_test_protocol(self) -> None:
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "basic.test.js").write_text(
            "const test=require('node:test'); const assert=require('node:assert'); test('ok',()=>assert.equal(1,1));\n",
            encoding="utf-8",
        )
        receipt = verify_repository(self.repo, evidence_directory=self.root / "node-evidence", **self.trusted())
        self.assertEqual("PASSED", receipt["status"])
        self.assertEqual("node-typescript", receipt["adapter_id"])
        self.assertEqual("test-execution", receipt["verification_kind"])
        self.assertTrue(receipt["tests_executed"])

    @unittest.skipUnless(shutil.which("go"), "Go is unavailable")
    def test_go_adapter_runs_compiled_language_target(self) -> None:
        (self.repo / "go.mod").write_text("module example.invalid/fixture\n\ngo 1.22\n", encoding="utf-8")
        (self.repo / "answer.go").write_text("package fixture\nfunc Answer() int { return 42 }\n", encoding="utf-8")
        (self.repo / "answer_test.go").write_text(
            "package fixture\nimport \"testing\"\nfunc TestAnswer(t *testing.T){if Answer()!=42{t.Fail()}}\n",
            encoding="utf-8",
        )
        receipt = verify_repository(
            self.repo,
            evidence_directory=self.root / "go-evidence",
            # The adapter intentionally starts with isolated empty Go caches.
            # Use its production default wall budget so this test measures the
            # sealed cold-cache execution rather than runner contention.
            **self.trusted(wall_seconds=300),
        )
        self.assertEqual(
            "PASSED",
            receipt["status"],
            json.dumps(
                {
                    "exit_code": receipt["exit_code"],
                    "timed_out": receipt["timed_out"],
                    "disk_delta_bytes": receipt["disk_delta_bytes"],
                    "stderr": Path(receipt["stderr"]["path"]).read_text(
                        encoding="utf-8", errors="replace"
                    ),
                },
                sort_keys=True,
            ),
        )
        self.assertEqual("go-test", receipt["adapter_id"])
        self.assertTrue(
            {"GOCACHE", "GOMODCACHE", "GOPATH", "GOTMPDIR"}.issubset(
                receipt["environment"]
            )
        )

    @unittest.skipUnless(shutil.which("rustc"), "Rust compiler is unavailable")
    def test_rust_adapter_runs_compiled_language_target_without_network(self) -> None:
        (self.repo / "src").mkdir()
        (self.repo / "Cargo.toml").write_text(
            '[package]\nname = "fixture"\nversion = "0.1.0"\nedition = "2021"\n',
            encoding="utf-8",
        )
        (self.repo / "Cargo.lock").write_text(
            'version = 4\n\n[[package]]\nname = "fixture"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )
        (self.repo / "src" / "lib.rs").write_text(
            "pub fn answer() -> i32 { 42 }\n#[cfg(test)] mod tests { #[test] fn answer_is_42(){ assert_eq!(super::answer(),42); } }\n",
            encoding="utf-8",
        )
        command = VerificationRegistry().seal(self.repo, adapter_id="rustc-check")
        self.assertIsNotNone(command)
        assert command is not None
        self.assertEqual("rustc", Path(command.argv[0]).stem)
        receipt = verify_repository(self.repo, evidence_directory=self.root / "rust-evidence", **self.trusted())
        self.assertEqual(
            "PASSED", receipt["status"],
            Path(receipt["stderr"]["path"]).read_text(encoding="utf-8", errors="replace"),
        )
        self.assertEqual("rustc-check", receipt["adapter_id"])
        self.assertEqual("compile-check", receipt["verification_kind"])
        self.assertFalse(receipt["tests_executed"])
        self.assertFalse((self.repo / "target").exists())

    def test_symlink_test_path_is_rejected(self) -> None:
        outside = self.root / "outside.py"
        outside.write_text("raise SystemExit(1)\n", encoding="utf-8")
        (self.repo / "tests").mkdir()
        link = self.repo / "tests" / "test_escape.py"
        try:
            link.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")
        with self.assertRaisesRegex(VerificationError, "alias|symlink"):
            VerificationRegistry().seal(self.repo)


if __name__ == "__main__":
    unittest.main()
