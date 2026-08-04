from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
TESTS = ROOT / "tests"


class CIContractTests(unittest.TestCase):
    def _workflow_test_command(self) -> str:
        lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
        step_name = "- name: Run deterministic test suite"
        for index, line in enumerate(lines):
            if line.strip() != step_name:
                continue
            for candidate in lines[index + 1 :]:
                stripped = candidate.strip()
                if stripped.startswith("- name:"):
                    break
                if stripped.startswith("run:"):
                    return stripped.partition(":")[2].strip()
        self.fail("workflow test-suite command is missing")

    def test_documented_gate_matches_workflow(self) -> None:
        command = self._workflow_test_command()
        for document in ("README.md", "AGENTS.md", "docs/plan/00_OVERVIEW.md"):
            with self.subTest(document=document):
                self.assertIn(command, (ROOT / document).read_text(encoding="utf-8"))

    def test_readme_starts_with_status_and_a_runnable_entry_point(self) -> None:
        opening = "\n".join(
            (ROOT / "README.md").read_text(encoding="utf-8").splitlines()[:40]
        ).lower()
        self.assertIn("## status: early. here is exactly what works.", opening)
        self.assertIn("hive-mind deliver --help", opening)
        for forbidden in ("docket", "atomic claim", "burden", "stage 0", "courtroom"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, opening)

    def test_no_test_module_imports_third_party(self) -> None:
        local_roots = {"hive_mind_os", "tests"}
        local_roots.update(
            path.stem if path.is_file() else path.name
            for path in TESTS.iterdir()
            if not path.name.startswith("__")
        )
        allowed_roots = set(sys.stdlib_module_names) | local_roots
        for path in sorted(TESTS.glob("*.py")):
            module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imported_roots = {
                alias.name.partition(".")[0]
                for node in ast.walk(module)
                if isinstance(node, ast.Import)
                for alias in node.names
            }
            imported_roots.update(
                node.module.partition(".")[0]
                for node in ast.walk(module)
                if isinstance(node, ast.ImportFrom) and node.module
            )
            with self.subTest(path=path.name):
                self.assertTrue(
                    imported_roots <= allowed_roots,
                    f"third-party test imports: {sorted(imported_roots - allowed_roots)}",
                )

    def test_workflow_installs_no_extras(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            "python -m pip install --disable-pip-version-check --no-deps -e .",
            workflow,
        )

    def test_workflow_exercises_windows_with_python_3_12(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        windows_job = workflow.partition("  unit-tests-windows:\n")[2].partition(
            "\n  quality:\n"
        )[0]
        self.assertTrue(windows_job, "Windows unit-test job is missing")
        self.assertIn("runs-on: windows-latest", windows_job)
        self.assertIn('python-version: ["3.12"]', windows_job)
        self.assertIn(self._workflow_test_command(), windows_job)
