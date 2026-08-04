from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_RUNNER = REPOSITORY_ROOT / "examples" / "verify-an-agent-change" / "run_example.py"


class VerificationExampleTests(unittest.TestCase):
    def test_runner_creates_an_adopted_sealed_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "example-out"
            completed = subprocess.run(
                (sys.executable, str(EXAMPLE_RUNNER), "--output", str(output)),
                cwd=REPOSITORY_ROOT,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                text=True,
                timeout=30,
            )

            self.assertEqual(
                completed.returncode,
                0,
                f"example stderr:\n{completed.stderr}\nexample stdout:\n{completed.stdout}",
            )
            verification = json.loads(
                (output / "receipt-bundle" / "verification.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(verification["verdict"], "adopt")
        self.assertEqual(verification["changed_paths"], ["discounts.py"])
        self.assertLess(
            verification["seal_sequence"], verification["repository_read_sequence"]
        )


if __name__ == "__main__":
    unittest.main()
