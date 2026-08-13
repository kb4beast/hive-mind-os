from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AUTOPILOT_TESTS = REPO_ROOT / ".autopilot" / "tests"
BLOCKER_EVIDENCE_COMMIT = "6bc343f079be6f2d5fd6953d92099a8d5de872b1"

# These values come from unittest discovery over the immutable baseline tree, not
# from the inconsistent arithmetic in ADR-063.  unittest's "Ran N tests" count
# includes skipped tests, so the retained receipt means 380 passed + 1 skipped.
BASELINE_DISCOVERED_TESTS = 381
BASELINE_IDS_SHA256 = (
    "7c0cf4ae7a2efca60af613b1702c97133a28b043bad09b231fe3a6c97d23eef4"
)
BASELINE_TEST_AST_SHA256 = (
    "617e2578c3db04d8a5b5a1a872b252ee457328ac0bd2763ef85129ffde9e6661"
)
CONDITIONAL_SKIP_TEST_ID = (
    "test_orchestration.IntentOrchestrationTests."
    "test_binding_state_symlink_escape_is_rejected"
)


def _run(*arguments: str) -> str:
    completed = subprocess.run(
        arguments,
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def _discovered_ids() -> list[str]:
    # Discovery occurs in a child because the controller tests intentionally use
    # top-level sibling imports whose module names would pollute this test process.
    program = r"""
import json
import sys
import unittest
from pathlib import Path

test_root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(test_root))
suite = unittest.defaultTestLoader.discover(
    str(test_root), pattern="test_*.py", top_level_dir=str(test_root)
)

def flatten(item):
    for child in item:
        if isinstance(child, unittest.TestSuite):
            yield from flatten(child)
        else:
            yield child

print(json.dumps([case.id() for case in flatten(suite)]))
"""
    output = _run(sys.executable, "-c", program, str(AUTOPILOT_TESTS))
    return json.loads(output)


def _frozen_ast_digest() -> str:
    """Hash all test behavior while allowing only the authorized lifecycle seam."""

    records: list[list[str]] = []
    for path in sorted(AUTOPILOT_TESTS.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if path.name == "test_healing.py":
            # DP-FIXTURE-030 may change imports and HealingFixture lifecycle only.
            tree.body = [
                node
                for node in tree.body
                if not isinstance(node, (ast.Import, ast.ImportFrom))
            ]
            for node in tree.body:
                if isinstance(node, ast.ClassDef) and node.name == "HealingFixture":
                    node.body = [
                        member
                        for member in node.body
                        if not (
                            isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
                            and member.name in {"setUp", "tearDown"}
                        )
                    ]
        records.append(
            [
                path.name,
                ast.dump(tree, annotate_fields=True, include_attributes=False),
            ]
        )
    body = json.dumps(
        records, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


class DoctorPerformanceBehaviorContractTests(unittest.TestCase):
    def test_discovery_ids_and_order_match_the_real_baseline(self) -> None:
        identifiers = _discovered_ids()
        self.assertEqual(len(identifiers), BASELINE_DISCOVERED_TESTS)
        digest = hashlib.sha256(("\n".join(identifiers) + "\n").encode()).hexdigest()
        self.assertEqual(digest, BASELINE_IDS_SHA256)

    def test_assertions_subtests_constants_decorators_and_methods_are_frozen(self) -> None:
        self.assertEqual(_frozen_ast_digest(), BASELINE_TEST_AST_SHA256)

    def test_the_one_conditional_skip_remains_in_the_frozen_method(self) -> None:
        identifiers = _discovered_ids()
        self.assertIn(CONDITIONAL_SKIP_TEST_ID, identifiers)
        tree = ast.parse(
            (AUTOPILOT_TESTS / "test_orchestration.py").read_text(encoding="utf-8")
        )
        methods = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "test_binding_state_symlink_escape_is_rejected"
        ]
        self.assertEqual(len(methods), 1)
        calls = [
            node
            for node in ast.walk(methods[0])
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "skipTest"
        ]
        self.assertEqual(len(calls), 1)

    def test_doctor_command_and_timeout_are_unchanged(self) -> None:
        source = (REPO_ROOT / ".autopilot" / "bin" / "controller.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        doctors = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "doctor"
        ]
        self.assertEqual(len(doctors), 1)
        calls = [
            node
            for node in ast.walk(doctors[0])
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run"
        ]
        controller_test_calls = [
            call
            for call in calls
            if any(
                isinstance(value, ast.Constant) and value.value == "unittest"
                for value in ast.walk(call)
            )
        ]
        self.assertEqual(len(controller_test_calls), 1)
        call = controller_test_calls[0]
        keyword_values = {item.arg: item.value for item in call.keywords}
        self.assertEqual(ast.literal_eval(keyword_values["timeout"]), 180)
        command_constants = [
            value.value
            for value in ast.walk(call.args[0])
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
        ]
        self.assertIsInstance(call.args[0], (ast.Tuple, ast.List))
        command_items = call.args[0].elts
        self.assertEqual(len(command_items), 7)
        self.assertIsInstance(command_items[0], ast.Attribute)
        self.assertEqual(command_items[0].attr, "executable")
        self.assertEqual(
            [ast.literal_eval(item) for item in command_items[1:5]],
            ["-m", "unittest", "discover", "-s"],
        )
        self.assertIsInstance(command_items[5], ast.Call)
        self.assertEqual(ast.literal_eval(command_items[6]), "-v")
        self.assertEqual(command_constants.count("tests"), 1)

    def test_sealed_vector_claim_matches_retained_unittest_evidence(self) -> None:
        """Fail closed while the sealed contract contradicts its own receipt."""

        evidence = json.loads(
            _run(
                "git",
                "show",
                f"{BLOCKER_EVIDENCE_COMMIT}:evidence/knowledge-projection/baseline.json",
            )
        )
        receipt = next(
            item
            for item in evidence["required_test_receipts"]
            if item["command"] == "python -m unittest discover -s .autopilot/tests -v"
        )
        match = re.search(r"Ran (\d+) tests", receipt["receipt"])
        self.assertIsNotNone(match)
        retained_total = int(match.group(1))
        self.assertEqual(retained_total, BASELINE_DISCOVERED_TESTS)
        self.assertIn("skipped=1", receipt["receipt"])

        specification = (
            REPO_ROOT / "docs" / "execution" / "dags" / "doctor-performance-v1" / "specs.py"
        ).read_text(encoding="utf-8")
        claimed = re.search(r"discover exactly (\d+) executions", specification)
        self.assertIsNotNone(claimed)
        # This assertion intentionally remains red until an independently governed
        # correction reconciles the sealed prose with the retained 381-test receipt.
        self.assertEqual(
            int(claimed.group(1)),
            retained_total,
            "sealed execution count disagrees with unittest and the retained "
            "381-total receipt, which includes one conditional skip",
        )


if __name__ == "__main__":
    unittest.main()
