"""Capture the actual bounded-process result for the frozen V4 DAG module."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(r"C:\h\node-guide1")
OUT = Path(__file__).resolve().parent
FROZEN = OUT / "frozen-v4"
PIN = "1038b5a7d2eb49904c59957ad3e989af8bb2fcc5"
FROZEN.mkdir(exist_ok=False)
archive = subprocess.check_output(["git", "-C", str(ROOT), "archive", "--format=tar", PIN])
with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
    tar.extractall(FROZEN, filter="data")
python = subprocess.check_output(["py", "-3.12", "-c", "import sys;print(sys.executable)"]).decode().strip()
collector = (ROOT / "scripts/Collect-V4ActivationEvidence.ps1").read_text()
bootstrap = collector.split('$testBootstrap = @"\n', 1)[1].split('\n"@', 1)[0]
bootstrap = bootstrap.replace("$pythonExecutableLiteral", json.dumps(python)).replace("$repositoryRootLiteral", json.dumps(str(FROZEN))).replace("$testResultMarkerLiteral", json.dumps("HIVE_V4_UNITTEST_RESULT_" + "a" * 32))
(OUT / "bootstrap.py").write_text(bootstrap, encoding="utf-8")
script = '''$ErrorActionPreference = 'Stop'
. $env:HIVE_PROBE_RUNNER
$result = Invoke-BoundedPythonValidation -PythonExecutable $env:HIVE_PROBE_PYTHON -BootstrapPath $env:HIVE_PROBE_BOOTSTRAP -Modules @('tests.test_dag_executor') -WorkingDirectory $env:HIVE_PROBE_ROOT -TaskkillExecutable $env:HIVE_PROBE_TASKKILL -TimeoutMilliseconds 300000
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $env:HIVE_PROBE_RESULT
'''
(OUT / "invoke.ps1").write_text(script, encoding="utf-8")
env = os.environ.copy()
env.update({"HIVE_PROBE_RUNNER": str(ROOT / "scripts/V4EvidenceProcess.ps1"), "HIVE_PROBE_PYTHON": python,
    "HIVE_PROBE_BOOTSTRAP": str(OUT / "bootstrap.py"), "HIVE_PROBE_ROOT": str(FROZEN),
    "HIVE_PROBE_TASKKILL": str(Path(os.environ["SystemRoot"]) / "System32/taskkill.exe"),
    "HIVE_PROBE_RESULT": str(OUT / "MODULE-RESULT.json")})
result = subprocess.run(["powershell", "-NoProfile", "-File", str(OUT / "invoke.ps1")], cwd=OUT, env=env, capture_output=True, timeout=340)
(OUT / "runner.stdout.txt").write_bytes(result.stdout)
(OUT / "runner.stderr.txt").write_bytes(result.stderr)
manifest = {"source_commit": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).decode().strip(),
    "frozen_commit": PIN, "archive_sha256": hashlib.sha256(archive).hexdigest(), "runner_exit_code": result.returncode,
    "bootstrap_sha256": hashlib.sha256((OUT / "bootstrap.py").read_bytes()).hexdigest()}
(OUT / "REPRODUCTION.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(json.dumps(manifest))
if (OUT / "MODULE-RESULT.json").exists():
    record = json.loads((OUT / "MODULE-RESULT.json").read_text(encoding="utf-8-sig"))
    (OUT / "module.stdout.txt").write_text(record.pop("stdout"), encoding="utf-8")
    (OUT / "module.stderr.txt").write_text(record.pop("stderr"), encoding="utf-8")
    print(json.dumps(record))
