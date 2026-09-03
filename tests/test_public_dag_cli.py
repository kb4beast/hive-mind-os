from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from tests.test_dag_standard_product import STANDARD, compiler_plan

ROOT = Path(__file__).resolve().parents[1]


class PublicDagCliTests(unittest.TestCase):
    def run_cli(
        self, arguments: list[str], *, cwd: Path
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "src")
        return subprocess.run(
            [sys.executable, "-B", "-m", "hive_mind_os.dag_cli", *arguments],
            cwd=cwd,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def fixture(self, root: Path) -> tuple[Path, Path, str]:
        plan = compiler_plan()
        plan_path = root / "plan.json"
        standard_path = root / "standard.md"
        plan_path.write_bytes(plan.canonical_bytes())
        standard_path.write_bytes(STANDARD)
        return plan_path, standard_path, plan.digest()

    def test_validate_rounds_and_graph_work_from_another_current_directory(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = root / "inputs"
            elsewhere = root / "elsewhere"
            inputs.mkdir()
            elsewhere.mkdir()
            plan, standard, digest = self.fixture(inputs)
            common = [
                "--plan",
                str(plan.resolve()),
                "--standard",
                str(standard.resolve()),
                "--expected-plan-digest",
                digest,
            ]
            for command in ("validate", "rounds", "graph"):
                completed = self.run_cli([command, *common], cwd=elsewhere)
                self.assertEqual(0, completed.returncode, completed.stderr)
                self.assertTrue(json.loads(completed.stdout))

    def test_missing_status_and_unconfigured_execute_are_inert_typed_results(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan, standard, digest = self.fixture(root)
            absent = root / "absent-state"
            status = self.run_cli(
                [
                    "status",
                    "--state-directory",
                    str(absent.resolve()),
                    "--plan",
                    str(plan.resolve()),
                    "--expected-plan-digest",
                    digest,
                ],
                cwd=root,
            )
            self.assertEqual(0, status.returncode, status.stderr)
            status_document = json.loads(status.stdout)
            self.assertFalse(status_document["state_present"])
            self.assertEqual(digest, status_document["binding"]["plan_digest"])
            self.assertFalse(absent.exists())

            substituted = self.run_cli(
                [
                    "status",
                    "--state-directory",
                    str(absent.resolve()),
                    "--plan",
                    str(plan.resolve()),
                    "--expected-plan-digest",
                    "sha256:" + "0" * 64,
                ],
                cwd=root,
            )
            self.assertEqual(2, substituted.returncode)
            self.assertIn("does not match expected bytes", substituted.stderr)

            blocked = self.run_cli(
                [
                    "execute",
                    "--plan",
                    str(plan.resolve()),
                    "--standard",
                    str(standard.resolve()),
                    "--expected-plan-digest",
                    digest,
                    "--activation",
                    str((root / "forged.json").resolve()),
                    "--state-directory",
                    str(absent.resolve()),
                ],
                cwd=root,
            )
            self.assertEqual(2, blocked.returncode)
            self.assertIn("EXTERNAL_RUNTIME_REQUIRED", blocked.stderr)
            self.assertFalse(absent.exists())

    def test_build_and_powershell_preparation_are_inert_until_explicit_use(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan, standard, digest = self.fixture(root)
            output = root / "sealed.json"
            client = root / "hive-mind.exe"
            client.write_bytes(b"pinned public CLI fixture")
            client_digest = "sha256:" + sha256(client.read_bytes()).hexdigest()
            built = self.run_cli(
                [
                    "build",
                    "--plan",
                    str(plan.resolve()),
                    "--standard",
                    str(standard.resolve()),
                    "--expected-plan-digest",
                    digest,
                    "--output",
                    str(output.resolve()),
                ],
                cwd=root,
            )
            self.assertEqual(0, built.returncode, built.stderr)
            self.assertTrue(output.is_file())
            prepared = self.run_cli(
                [
                    "prepare-powershell",
                    "--plan",
                    str(plan.resolve()),
                    "--standard",
                    str(standard.resolve()),
                    "--subject",
                    "fixture",
                    "--expected-plan-digest",
                    digest,
                    "--state-directory",
                    str((root / "state").resolve()),
                    "--execution-client",
                    str(client.resolve()),
                    "--expected-execution-client-digest",
                    client_digest,
                ],
                cwd=root,
            )
            self.assertEqual(0, prepared.returncode, prepared.stderr)
            document = json.loads(prepared.stdout)
            self.assertFalse(document["execution_authorized"])
            self.assertNotIn("dag execute", document["text"])
            self.assertFalse((root / "state").exists())

    def test_relative_paths_are_not_silently_promoted_to_explicit_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan, standard, digest = self.fixture(root)
            relative_plan = plan.relative_to(root)
            relative_standard = standard.relative_to(root)
            completed = self.run_cli(
                [
                    "validate",
                    "--plan",
                    str(relative_plan),
                    "--standard",
                    str(relative_standard),
                    "--expected-plan-digest",
                    digest,
                ],
                cwd=root,
            )
            self.assertEqual(2, completed.returncode)
            self.assertIn("explicit absolute path", completed.stderr)


if __name__ == "__main__":
    unittest.main()
