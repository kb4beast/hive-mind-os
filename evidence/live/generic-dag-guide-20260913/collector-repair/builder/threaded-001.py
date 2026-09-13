from __future__ import annotations

import importlib
import faulthandler
import gc
import os
import pathlib
import sys
import unittest
import threading

EXPECTED_EXECUTABLE = pathlib.Path("C:\\Users\\beesp\\AppData\\Local\\Programs\\Python\\Python312\\python.exe").resolve()
REPOSITORY_ROOT = pathlib.Path("C:\\h\\node-completeness-audit\\windows-collector-repair\\frozen-v4").resolve()
SOURCE_ROOT = (REPOSITORY_ROOT / "src").resolve()
RESULT_MARKER = "HIVE_V4_UNITTEST_RESULT_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
EXPECTED_CHILD_PYTHONPATH = str(SOURCE_ROOT) + os.pathsep + str(REPOSITORY_ROOT)
if pathlib.Path(sys.executable).resolve() != EXPECTED_EXECUTABLE:
    raise SystemExit("focused validation used an unexpected Python executable")
if os.environ.get("PYTHONPATH") != EXPECTED_CHILD_PYTHONPATH:
    raise SystemExit("focused validation did not bind the child Python source path")
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(SOURCE_ROOT))
package = importlib.import_module("hive_mind_os")
expected_package = (SOURCE_ROOT / "hive_mind_os" / "__init__.py").resolve()
if pathlib.Path(package.__file__).resolve() != expected_package:
    raise SystemExit("focused validation imported hive_mind_os from another checkout")
print(f"BOUND_PYTHON={pathlib.Path(sys.executable).resolve()}", flush=True)
print(f"BOUND_PACKAGE={pathlib.Path(package.__file__).resolve()}", flush=True)
diagnostic_stop = threading.Event()
def dump_diagnostics():
    while not diagnostic_stop.wait(0.001):
        print("FOCUSED_VALIDATION_DIAGNOSTIC (not a process deadline)", file=sys.stderr, flush=True)
        faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
diagnostic_thread = threading.Thread(target=dump_diagnostics, daemon=True)
diagnostic_thread.start()
try:
    program = unittest.main(module=None, exit=False)
finally:
    diagnostic_stop.set()
    diagnostic_thread.join()
gc.collect()
successful = program.result.wasSuccessful()
print(
    f"{RESULT_MARKER} tests_run={program.result.testsRun} "
    f"failures={len(program.result.failures)} "
    f"errors={len(program.result.errors)} "
    f"skipped={len(program.result.skipped)} "
    f"expected_failures={len(program.result.expectedFailures)} "
    f"unexpected_successes={len(program.result.unexpectedSuccesses)} "
    f"successful={str(successful).lower()}",
    flush=True,
)
if not successful:
    raise SystemExit(1)