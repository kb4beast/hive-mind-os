from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from hive_mind_os import cli
from hive_mind_os.verify import verify_repository


class StandaloneVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repository = self.root / "agent-change"
        self.repository.mkdir()
        self._git("init")
        self._git("config", "user.email", "agent@example.invalid")
        self._git("config", "user.name", "Agent")
        (self.repository / "app.py").write_text(
            "def value() -> int:\n    return 1\n",
            encoding="utf-8",
        )
        (self.repository / "check_value.py").write_text(
            "from app import value\nassert value() == 2\n",
            encoding="utf-8",
        )
        self._git("add", "app.py", "check_value.py")
        self._git("commit", "-m", "base")
        (self.repository / "app.py").write_text(
            "def value() -> int:\n    return 2\n",
            encoding="utf-8",
        )
        self._git("add", "app.py")
        self._git("commit", "-m", "agent change")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _git(self, *arguments: str) -> None:
        completed = subprocess.run(
            ("git", "-C", str(self.repository), *arguments),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_seals_before_reading_and_emits_a_receipt_bundle(self) -> None:
        specification = self.root / "acceptance.json"
        specification.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "id": "value-is-two",
                    "criterion": "value returns two",
                    "command": {
                        "argv": [
                            sys.executable,
                            "check_value.py",
                        ],
                        "expected": "succeeded",
                    },
                    "declared_paths": ["app.py"],
                }
            ),
            encoding="utf-8",
        )
        bundle = self.root / "bundle"
        report = verify_repository(self.repository, specification, bundle)

        self.assertEqual(report.verdict, "adopt")
        self.assertLess(report.seal_sequence, report.repository_read_sequence)
        self.assertTrue(report.report_path.is_file())
        document = json.loads(report.report_path.read_text(encoding="utf-8"))
        self.assertEqual(document["changed_paths"], ["app.py"])
        self.assertTrue(document["checks"][0]["matched"])
        self.assertTrue((bundle / "receipts").is_dir())

    def test_cli_returns_success_for_an_adopted_verdict(self) -> None:
        specification = self.root / "acceptance.json"
        specification.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "id": "value-is-two",
                    "criterion": "value returns two",
                    "command": {
                        "argv": [sys.executable, "check_value.py"],
                        "expected": "succeeded",
                    },
                    "declared_paths": ["app.py"],
                }
            ),
            encoding="utf-8",
        )
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli._run_verify(
                cli.build_verify_parser().parse_args(
                    [
                        "--repository",
                        str(self.repository),
                        "--spec",
                        str(specification),
                        "--output",
                        str(self.root / "cli-bundle"),
                    ]
                )
            )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "adopt")


if __name__ == "__main__":
    unittest.main()
