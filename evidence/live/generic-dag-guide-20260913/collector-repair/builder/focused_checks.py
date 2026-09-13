"""Retain diagnostic and timeout refusal checks without rerunning the full suite."""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(r"C:\h\node-guide1")
OUT = Path(__file__).resolve().parent
names = [
    "test_generated_bootstrap_diagnostics_preserve_module_completion",
    "test_generated_bootstrap_rejects_diagnostic_thread_failure",
    "test_collector_records_bounded_focused_validation_timeout",
    "test_collector_attributes_a_module_process_timeout_with_partial_streams",
    "test_terminal_result_rejects_skips_and_every_adverse_outcome",
    "test_bounded_runner_timeout_kills_descendants_but_not_unrelated_process",
]
command = ["py", "-3.12", "-B", "-m", "unittest", *("tests.test_collect_v4_activation_evidence.CollectV4ActivationEvidenceTests." + name for name in names), "-v"]
environment = os.environ.copy()
environment["PYTHONPATH"] = str(ROOT / "src")
started = time.monotonic()
with (OUT / "focused.stdout.txt").open("wb") as stdout, (OUT / "focused.stderr.txt").open("wb") as stderr:
    result = subprocess.run(command, cwd=ROOT, env=environment, stdout=stdout, stderr=stderr, timeout=420)
file = "tests/test_collect_v4_activation_evidence.py"
old = subprocess.check_output(["git", "-C", str(ROOT), "show", "3bfd4edd504a1c1dc6b4448941dc38f4fdfcdbba:" + file])
def assertions(raw):
    return [ast.dump(node, include_attributes=False) for node in ast.walk(ast.parse(raw)) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr.startswith("assert")]
remaining = assertions((ROOT / file).read_bytes())
prior = assertions(old)
for assertion in prior:
    remaining.remove(assertion)
files = ["scripts/Collect-V4ActivationEvidence.ps1", "scripts/V4EvidenceProcess.ps1", file]
source = [{"path": name, "sha256": hashlib.sha256((ROOT / name).read_bytes()).hexdigest()} for name in files]
report = {"status": "passed" if result.returncode == 0 else "failed", "argv": command,
    "exit_code": result.returncode, "duration_seconds": time.monotonic() - started,
    "prior_assertions_preserved": len(prior), "new_assertions": len(remaining), "source_working_bytes": source,
    "stdout_sha256": hashlib.sha256((OUT / "focused.stdout.txt").read_bytes()).hexdigest(),
    "stderr_sha256": hashlib.sha256((OUT / "focused.stderr.txt").read_bytes()).hexdigest()}
(OUT / "FOCUSED-VALIDATION.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report))
raise SystemExit(result.returncode)
