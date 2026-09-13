"""A/B candidate: identical module, Python-thread-owned diagnostic snapshots."""
import json
import os
from pathlib import Path
import subprocess

OUT = Path(__file__).resolve().parent
python = subprocess.check_output(["py", "-3.12", "-c", "import sys;print(sys.executable)"]).decode().strip()
root = OUT / "frozen-v4"
environment = os.environ.copy()
environment["PYTHONPATH"] = str(root / "src") + os.pathsep + str(root)
bootstrap = (OUT / "bootstrap.py").read_text().replace("import unittest", "import unittest\nimport threading")
replacement = '''diagnostic_stop = threading.Event()
def dump_diagnostics():
    while not diagnostic_stop.wait(INTERVAL):
        print("FOCUSED_VALIDATION_DIAGNOSTIC (not a process deadline)", file=sys.stderr, flush=True)
        faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
diagnostic_thread = threading.Thread(target=dump_diagnostics, daemon=True)
diagnostic_thread.start()'''
bootstrap = bootstrap.replace("faulthandler.dump_traceback_later(15, repeat=True)", replacement)
bootstrap = bootstrap.replace("faulthandler.cancel_dump_traceback_later()", "diagnostic_stop.set()\n    diagnostic_thread.join()")
results = []
for label, interval in (("threaded-01", "0.01"), ("threaded-001", "0.001")):
    path = OUT / f"{label}.py"
    path.write_text(bootstrap.replace("INTERVAL", interval), encoding="utf-8")
    result = subprocess.run([python, "-I", "-B", "-X", "utf8", "-W", "error::ResourceWarning", str(path), "-v", "tests.test_dag_executor"], cwd=root, env=environment, capture_output=True, timeout=300)
    (OUT / f"{label}.stdout.txt").write_bytes(result.stdout)
    (OUT / f"{label}.stderr.txt").write_bytes(result.stderr)
    results.append({"label": label, "diagnostic_interval_seconds": interval, "exit_code": result.returncode, "stderr_bytes": len(result.stderr), "diagnostic_occurrences": result.stderr.count(b"FOCUSED_VALIDATION_DIAGNOSTIC"), "terminal_marker_present": b"HIVE_V4_UNITTEST_RESULT_" in result.stdout})
(OUT / "THREADED-DIAGNOSTIC-RESULT.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
print(json.dumps(results))
