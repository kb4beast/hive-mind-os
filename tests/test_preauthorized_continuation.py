from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "Invoke-PreauthorizedContinuation.ps1"
AGENTS = ROOT / "AGENTS.md"
ADR = ROOT / "docs" / "architecture" / "ADR-066-PREAUTHORIZED-CONTINUATION-LAUNCHER.md"


class PreauthorizedContinuationLauncherTests(unittest.TestCase):
    """ADR-066: continuation must resume a narrow live control-plane path."""

    def setUp(self) -> None:
        self.script = SCRIPT.read_text(encoding="utf-8")

    def test_launcher_uses_a_fixed_control_plane_request_and_argument_array(self) -> None:
        self.assertIn("$arguments = @(\n", self.script)
        self.assertIn('"orchestrate",', self.script)
        self.assertIn('"--request", $request,', self.script)
        self.assertIn(
            "Continue the existing authorized routine and reversible Hive Mind work.",
            self.script,
        )
        self.assertIn('$arguments += "--apply"', self.script)
        self.assertIn("& $python @arguments", self.script)
        self.assertNotIn("param(\n    [string]$Request", self.script)
        self.assertNotIn("Invoke-Expression", self.script)
        self.assertNotIn("cmd.exe", self.script)

    def test_launcher_reobserves_the_current_repository_before_execution(self) -> None:
        self.assertIn("Resolve-Path -LiteralPath $RepoRoot", self.script)
        self.assertIn('Join-Path $root ".autopilot\\bin\\autopilot.py"', self.script)
        self.assertIn("git -C $root rev-parse --is-inside-work-tree", self.script)
        self.assertNotIn("ARCH-100", self.script)
        self.assertNotIn("release/hive-mind-os-singleton", self.script)

    def test_launcher_cannot_smuggle_credentials_or_privileged_shortcuts(self) -> None:
        for forbidden in (
            "GITHUB_TOKEN",
            "GH_TOKEN",
            "github_pat_",
            "Set-ItemProperty",
            "ExecutionPolicy",
            "Set-ExecutionPolicy",
            "git push",
            '"merge"',
            '"deploy"',
            '"push"',
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.script)

    def test_agent_instruction_is_durable_and_preserves_external_authority_limits(self) -> None:
        instructions = AGENTS.read_text(encoding="utf-8")
        adr = ADR.read_text(encoding="utf-8")
        self.assertIn("## Durable operator continuation", instructions)
        self.assertIn("Invoke-PreauthorizedContinuation.ps1 -Apply", instructions)
        self.assertIn("A new material scope", instructions)
        self.assertIn("ROOT-3000", adr)
        self.assertIn("not durable unlimited consent", adr)


if __name__ == "__main__":
    unittest.main()
