from __future__ import annotations

import importlib
import faulthandler
import gc
import os
import pathlib
import sys
import unittest

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
faulthandler.dump_traceback_later(0.01, repeat=True)
try:
    program = unittest.main(module=None, exit=False)
finally:
    faulthandler.cancel_dump_traceback_later()
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