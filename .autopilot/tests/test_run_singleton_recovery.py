from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "run-singleton-recovery.ps1"


class SingletonRecoveryScriptTests(unittest.TestCase):
    def test_quarantine_fails_before_repository_or_control_plane_access(self) -> None:
        shell = shutil.which("powershell") or shutil.which("pwsh")
        self.assertIsNotNone(shell, "PowerShell is required to exercise the recovery guard")
        assert shell is not None

        with tempfile.TemporaryDirectory() as temporary:
            nonexistent_root = Path(temporary) / "must-not-be-created"
            completed = subprocess.run(
                (
                    shell,
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(SCRIPT),
                    "-RepoRoot",
                    str(nonexistent_root),
                    "-Node",
                    "TEST-RECOVERY",
                ),
                capture_output=True,
                text=True,
                check=False,
            )
            root_was_touched = nonexistent_root.exists()

        output = completed.stdout + completed.stderr
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Singleton recovery is quarantined", output)
        # PowerShell formats a thrown string to the terminal width.  Assert the
        # semantic guard after normalizing ANSI decoration and wrapped lines,
        # rather than coupling the safety contract to host-specific rendering.
        plain_output = re.sub(r"\x1b\[[0-9;]*m", "", output)
        self.assertIn(
            "No release, claim, Git, or repository action was attempted",
            re.sub(r"\s+", " ", plain_output),
        )
        self.assertFalse(root_was_touched)

    def test_quarantined_script_has_no_dispatch_or_claim_transport(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("autopilot.py", source)
        self.assertNotIn("github_snapshot.py", source)
        self.assertNotIn("Invoke-Checked", source)


if __name__ == "__main__":
    unittest.main()
