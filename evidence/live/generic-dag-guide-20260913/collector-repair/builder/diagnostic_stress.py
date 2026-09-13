"""External-only acceleration of diagnostic sampling; production limits untouched."""
import json
import os
from pathlib import Path
import subprocess

OUT = Path(__file__).resolve().parent
python = subprocess.check_output(["py", "-3.12", "-c", "import sys;print(sys.executable)"]).decode().strip()
root = OUT / "frozen-v4"
environment = os.environ.copy()
environment["PYTHONPATH"] = str(root / "src") + os.pathsep + str(root)
bootstrap = (OUT / "bootstrap.py").read_text()
results = []
for label, interval in (("accelerated-01", "0.01"), ("accelerated-001", "0.001")):
    path = OUT / f"{label}.py"
    path.write_text(bootstrap.replace("dump_traceback_later(15,", f"dump_traceback_later({interval},"), encoding="utf-8")
    result = subprocess.run([python, "-I", "-B", "-X", "utf8", "-W", "error::ResourceWarning", str(path), "-v", "tests.test_dag_executor"], cwd=root, env=environment, capture_output=True, timeout=300)
    (OUT / f"{label}.stdout.txt").write_bytes(result.stdout)
    (OUT / f"{label}.stderr.txt").write_bytes(result.stderr)
    results.append({"label": label, "diagnostic_interval_seconds": interval, "exit_code": result.returncode, "stderr_bytes": len(result.stderr), "diagnostic_occurrences": result.stderr.count(b"Timeout ("), "terminal_marker_present": b"HIVE_V4_UNITTEST_RESULT_" in result.stdout})
(OUT / "DIAGNOSTIC-STRESS.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
print(json.dumps(results))
