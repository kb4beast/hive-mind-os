from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / ".autopilot" / "bin" / "hermetic_ci.py"
PLAN = "sha256:" + "a" * 64


class HermeticCiTests(unittest.TestCase):
    def _git(self, root: Path, *arguments: str) -> str:
        return subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()

    def test_frozen_clone_ignores_foreign_editable_import_and_seals_vector(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "candidate"
            package = root / "src" / "hive_mind_os"
            tests = root / "tests"
            scripts = root / ".autopilot" / "bin"
            package.mkdir(parents=True)
            tests.mkdir(parents=True)
            scripts.mkdir(parents=True)
            (package / "__init__.py").write_text(
                'SOURCE = "frozen-candidate"\n', encoding="utf-8"
            )
            (tests / "test_sample.py").write_text(
                "import unittest\n"
                "import hive_mind_os\n\n"
                "class Sample(unittest.TestCase):\n"
                "    def test_candidate_import(self):\n"
                "        self.assertEqual(hive_mind_os.SOURCE, 'frozen-candidate')\n",
                encoding="utf-8",
            )
            (scripts / "hermetic_ci.py").write_bytes(RUNNER.read_bytes())
            self._git(root, "init")
            self._git(root, "config", "user.name", "Hermetic Test")
            self._git(root, "config", "user.email", "hermetic@example.invalid")
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "fixture")
            receipt = Path(temporary) / "receipt.json"
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(Path(temporary) / "foreign-editable")
            completed = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(RUNNER),
                    "--repo-root",
                    str(root),
                    "--suite",
                    "tests",
                    "--plan-fingerprint",
                    PLAN,
                    "--execution-namespace",
                    "fixture-execution",
                    "--receipt",
                    str(receipt),
                    "--timeout-seconds",
                    "60",
                    "--discovery-timeout-seconds",
                    "30",
                    "--verbosity",
                    "0",
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=environment,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            value = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(value["run"]["classification"], "PASS")
            self.assertEqual(value["test_vector"]["test_ids"], ["test_sample.Sample.test_candidate_import"])
            self.assertEqual(value["run"]["outcome"]["tests_run"], 1)
            self.assertTrue(value["discovery"]["isolated"])
            self.assertTrue(value["discovery"]["no_user_site"])
            imported = Path(value["discovery"]["imported_hive_mind_os_path"])
            self.assertIn("hive-mind-hermetic-", str(imported))
            self.assertEqual(imported.parts[-3:], ("src", "hive_mind_os", "__init__.py"))
            self.assertNotIn("foreign-editable", str(imported))

    def test_dirty_candidate_is_rejected_before_clone_or_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "candidate"
            root.mkdir()
            self._git(root, "init")
            self._git(root, "config", "user.name", "Hermetic Test")
            self._git(root, "config", "user.email", "hermetic@example.invalid")
            (root / "tracked.txt").write_text("one\n", encoding="utf-8")
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "fixture")
            (root / "tracked.txt").write_text("two\n", encoding="utf-8")
            receipt = Path(temporary) / "receipt.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(RUNNER),
                    "--repo-root",
                    str(root),
                    "--plan-fingerprint",
                    PLAN,
                    "--execution-namespace",
                    "fixture-execution",
                    "--receipt",
                    str(receipt),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("clean frozen candidate", completed.stderr)
            self.assertFalse(receipt.exists())


if __name__ == "__main__":
    unittest.main()
