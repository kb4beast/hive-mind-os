from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "scripts" / "whole-os" / "Invoke-WholeOSPipeline.ps1"
RUNNER = ROOT / "scripts" / "whole-os" / "Invoke-WholeOSAgentStage.ps1"
SCHEMA = ROOT / "scripts" / "whole-os" / "stage-result.schema.json"
STAGES = (
    "Invoke-WholeOSHostBootstrap.ps1",
    "Invoke-WholeOSN30Tournament.ps1",
    "Invoke-WholeOSN31SelfPilot.ps1",
    "Invoke-WholeOSN32ExternalPilot.ps1",
    "Invoke-WholeOSN33Closeout.ps1",
)


class WholeOSPowerShellPipelineTests(unittest.TestCase):
    def test_pipeline_has_exact_sequential_stage_order(self) -> None:
        text = PIPELINE.read_text(encoding="utf-8")
        positions = [text.index(name) for name in STAGES]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('status -eq "complete"', text)
        self.assertIn("Start-Sleep -Seconds $delay", text)

    def test_runner_uses_closed_results_and_no_unsafe_bypass(self) -> None:
        text = RUNNER.read_text(encoding="utf-8")
        self.assertIn('"--output-schema", $schema', text)
        self.assertIn('"--ask-for-approval", "never"', text)
        self.assertIn('"--sandbox", "danger-full-access"', text)
        self.assertLess(text.index('"--ask-for-approval"'), text.index('"exec",'))
        for forbidden in (
            "dangerously-bypass-approvals-and-sandbox",
            "dangerously-bypass-hook-trust",
            "Invoke-Expression",
            "Set-ExecutionPolicy",
            "--ignore-rules",
        ):
            self.assertNotIn(forbidden, text)

    def test_master_background_process_is_hidden_and_deduplicated(self) -> None:
        text = PIPELINE.read_text(encoding="utf-8")
        self.assertIn("-WindowStyle Hidden", text)
        self.assertIn('"pipeline-process.json"', text)
        self.assertIn("Get-Process -Id", text)

    def test_result_schema_is_closed_and_covers_every_stage(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            set(schema["properties"]["stage"]["enum"]),
            {
                "host-bootstrap",
                "n30-tournament",
                "n31-self-pilot",
                "n32-external-pilot",
                "n33-closeout",
            },
        )
        self.assertEqual(
            set(schema["properties"]["status"]["enum"]),
            {"complete", "in_progress", "blocked", "failed"},
        )

    def test_stage_prompts_forbid_fabricated_external_receipts(self) -> None:
        prompt_root = PIPELINE.parent / "prompts"
        prompts = tuple(prompt_root.glob("*.md"))
        self.assertEqual(len(prompts), 5)
        combined = "\n".join(path.read_text(encoding="utf-8") for path in prompts)
        self.assertIn("Never relabel unit fixtures as real comparator", combined)
        self.assertIn("Do not merge a protected branch", combined)
        self.assertIn("not proof", combined)
        self.assertIn("actual hours", combined)

    @unittest.skipUnless(
        shutil.which("powershell") or shutil.which("pwsh"),
        "PowerShell is required for script parse verification",
    )
    def test_every_powershell_script_parses(self) -> None:
        shell = shutil.which("powershell") or shutil.which("pwsh")
        scripts = (PIPELINE, RUNNER, *(PIPELINE.parent / item for item in STAGES))
        command = (
            "$errors=$null; [void][System.Management.Automation.Language.Parser]::"
            "ParseFile($env:HIVE_PS_PARSE_TARGET,[ref]$null,[ref]$errors); if($errors.Count){"
            "$errors | ForEach-Object { Write-Error $_ }; exit 1 }"
        )
        for script in scripts:
            with self.subTest(script=script.name):
                environment = dict(os.environ)
                environment["HIVE_PS_PARSE_TARGET"] = str(script)
                result = subprocess.run(
                    [shell, "-NoProfile", "-Command", command],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                    env=environment,
                )
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
