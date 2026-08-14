from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fixture_support import copy_autopilot_fixture

BIN = Path(__file__).resolve().parents[1] / "bin"
# round_driver imports its siblings by name, exactly as the CLI does.
sys.path.insert(0, str(BIN))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, BIN / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


controller = _load("driver_controller", "controller.py")
attended = _load("driver_attended_host", "attended_host.py")
driver = _load("driver_module", "round_driver.py")

NODE = "MISSION-400"
BRANCH = "autopilot/mission-400"


def git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", "-C", str(root)) + arguments,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class RoundDriverTests(unittest.TestCase):
    """Integration order, gate discipline, and triage authority, as tested code."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.root = base / "work"
        self.origin = base / "origin.git"
        self.root.mkdir()
        copy_autopilot_fixture(Path(__file__).resolve().parents[1], self.root / ".autopilot")
        control_path = self.root / ".autopilot" / "control-plane.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control["verify_git_objects"] = False
        control_path.write_text(json.dumps(control, indent=2) + "\n", encoding="utf-8")
        self.target = control["target"]["branch"]
        subprocess.run(
            ("git", "init", "--bare", f"--initial-branch={self.target}", str(self.origin)),
            check=True,
            capture_output=True,
        )
        git(self.root, "init", f"--initial-branch={self.target}")
        git(self.root, "config", "user.name", "Fixture")
        git(self.root, "config", "user.email", "fixture@hive-mind.invalid")
        (self.root / "shared.txt").write_text("base\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", "fixture base")
        git(self.root, "remote", "add", "origin", str(self.origin))
        git(self.root, "push", "-u", "origin", self.target)
        self.base = git(self.root, "rev-parse", "HEAD")
        self.plane = controller.ControlPlane(self.root)
        self.report = driver.RoundReport()
        self.round = driver.Round(
            round_id="R-TEST",
            level=6,
            nodes=(NODE,),
            parallel_safe=False,
            reason="fixture round",
            command="dispatch",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def publish_node_branch(self, *, sealed: bool, content: str = "node work\n") -> str:
        """Build a node branch, optionally sealed by a receipt-authored head."""

        git(self.root, "checkout", "-q", "-b", "tmp-node", self.base)
        (self.root / "node.txt").write_text(content, encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", "node candidate")
        head = git(self.root, "rev-parse", "HEAD")
        if sealed:
            tree = git(self.root, "rev-parse", "HEAD^{tree}")
            head = subprocess.run(
                (
                    "git", "-C", str(self.root), "commit-tree", tree, "-p", head,
                    "-m", "receipt",
                ),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "GIT_AUTHOR_NAME": "Receipt",
                    "GIT_AUTHOR_EMAIL": attended.RECEIPT_IDENTITY,
                    "GIT_COMMITTER_NAME": "Receipt",
                    "GIT_COMMITTER_EMAIL": attended.RECEIPT_IDENTITY,
                },
            ).stdout.strip()
        git(self.root, "push", "--force", "origin", f"{head}:refs/heads/{BRANCH}")
        git(self.root, "checkout", "-q", self.target)
        return head

    def test_sealed_branch_integrates_and_is_idempotent(self) -> None:
        head = self.publish_node_branch(sealed=True)
        whole = driver.integrate_round(self.plane, self.round, self.report, push=False)
        self.assertTrue(whole)
        self.assertEqual(self.report.steps[-1].outcome, "INTEGRATED")
        self.assertEqual(
            git(self.root, "merge-base", "--is-ancestor", head, "HEAD"), ""
        )
        again = driver.RoundReport()
        self.assertTrue(driver.integrate_round(self.plane, self.round, again, push=False))
        self.assertEqual(again.steps[-1].outcome, "ALREADY")

    def test_unsealed_branch_is_pending_not_integrated(self) -> None:
        self.publish_node_branch(sealed=False)
        whole = driver.integrate_round(self.plane, self.round, self.report, push=False)
        self.assertFalse(whole)
        self.assertEqual(self.report.steps[-1].outcome, "PENDING")

    def test_conflict_aborts_and_reports_a_scope_violation(self) -> None:
        git(self.root, "checkout", "-q", "-b", "tmp-node", self.base)
        (self.root / "shared.txt").write_text("node side\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", "node candidate")
        tree = git(self.root, "rev-parse", "HEAD^{tree}")
        head = subprocess.run(
            ("git", "-C", str(self.root), "commit-tree", tree, "-p", "HEAD", "-m", "receipt"),
            check=True, capture_output=True, text=True,
            env={
                **os.environ,
                "GIT_AUTHOR_NAME": "Receipt",
                "GIT_AUTHOR_EMAIL": attended.RECEIPT_IDENTITY,
                "GIT_COMMITTER_NAME": "Receipt",
                "GIT_COMMITTER_EMAIL": attended.RECEIPT_IDENTITY,
            },
        ).stdout.strip()
        git(self.root, "push", "--force", "origin", f"{head}:refs/heads/{BRANCH}")
        git(self.root, "checkout", "-q", self.target)
        (self.root / "shared.txt").write_text("target side\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", "target advance")
        whole = driver.integrate_round(self.plane, self.round, self.report, push=False)
        self.assertFalse(whole)
        self.assertEqual(self.report.steps[-1].outcome, "CONFLICT")
        self.assertIn("scope violation", self.report.steps[-1].detail)
        self.assertEqual(git(self.root, "status", "--porcelain"), "")

    def test_integration_refuses_to_run_off_the_target_branch(self) -> None:
        git(self.root, "checkout", "-q", "-b", "somewhere-else")
        with self.assertRaises(driver.RoundDriverError):
            driver.integrate_round(self.plane, self.round, self.report, push=False)

    def test_validation_releases_its_lease_even_when_tests_fail(self) -> None:
        def failing() -> tuple[bool, str]:
            return False, "FAILED (failures=1)"

        driver.validate_round(
            self.plane, self.round, self.report, owner="test:owner", runner=failing
        )
        self.assertEqual(self.report.steps[-1].outcome, "FAILED")
        self.assertIsNone(self.plane.status().get("active_validation_lease"))

    def test_validation_releases_its_lease_when_the_runner_raises(self) -> None:
        def exploding() -> tuple[bool, str]:
            raise RuntimeError("runner died")

        with self.assertRaises(RuntimeError):
            driver.validate_round(
                self.plane, self.round, self.report, owner="test:owner", runner=exploding
            )
        self.assertIsNone(self.plane.status().get("active_validation_lease"))

    def test_completion_reads_node_rows_not_the_plan_wide_boolean(self) -> None:
        status = {
            "complete": False,
            "nodes": [
                {"node_id": "BOOT-000", "state": "COMPLETE"},
                {"node_id": NODE, "state": "RECONCILIATION_REQUIRED"},
            ],
        }
        self.assertEqual(driver.completed_nodes(status), {"BOOT-000"})

    def test_partial_round_resume_does_not_reselect_completed_members(self) -> None:
        compiled = driver.Round(
            round_id="R-PARTIAL",
            level=2,
            nodes=("A", "B", "C"),
            parallel_safe=True,
            reason="capacity round",
            command="dispatch",
        )
        status = {
            "nodes": [
                {"node_id": "A", "state": "COMPLETE"},
                {"node_id": "B", "state": "READY"},
                {"node_id": "C", "state": "READY"},
            ]
        }
        with patch.object(driver, "compile_rounds", return_value=(compiled,)):
            selected = driver.select_round(self.plane, status, max_sessions=3)
        assert selected is not None
        self.assertEqual(selected.nodes, ("B", "C"))
        self.assertIn("resuming only unaccepted", selected.reason)

    def test_plan_quiescence_requires_no_residual_runtime_authority(self) -> None:
        status = {"nodes": [], "active_validation_lease": None}
        with patch.object(driver, "select_round", return_value=None):
            with patch.object(self.plane, "status", return_value=status):
                with patch.object(self.plane, "active_claims", return_value={}):
                    result = driver.drive_round(
                        self.plane,
                        actor="test:driver",
                        push=False,
                        heal=False,
                    )
        self.assertEqual(result["disposition"], "PLAN_QUIESCENT")

    def test_completed_plan_with_a_live_claim_is_waiting_not_quiescent(self) -> None:
        status = {"nodes": [], "active_validation_lease": None}
        with patch.object(driver, "select_round", return_value=None):
            with patch.object(self.plane, "status", return_value=status):
                with patch.object(
                    self.plane,
                    "active_claims",
                    return_value={"A": {"node_id": "A"}},
                ):
                    result = driver.drive_round(
                        self.plane,
                        actor="test:driver",
                        push=False,
                        heal=False,
                    )
        self.assertEqual(result["disposition"], "WAITING")

    def test_driver_refuses_to_select_before_reconciliation(self) -> None:
        class UnreconciledPlane:
            """The one call drive_round makes before it decides anything."""

            def status(self) -> dict[str, object]:
                return {"reconciliation_required": True, "nodes": []}

        result = driver.drive_round(
            UnreconciledPlane(), actor="test:driver", push=False, heal=False
        )
        self.assertTrue(result["blocked"])
        self.assertEqual(result["steps"][0]["outcome"], "RECONCILE_REQUIRED")
        self.assertIn("--reconcile", result["steps"][0]["detail"])
        self.assertIsNone(result["round_id"])
        self.assertEqual(result["disposition"], "RECONCILE_REQUIRED")

    def test_driver_attempts_reconciliation_before_conceding(self) -> None:
        missing = Path(self.temporary.name) / "empty"

        class UnreconciledPlane:
            """No snapshot script exists, so the heal attempt must fail cleanly."""

            ap_root = missing / ".autopilot"
            repo_root = missing

            def status(self) -> dict[str, object]:
                return {"reconciliation_required": True, "nodes": []}

        result = driver.drive_round(UnreconciledPlane(), actor="test:driver", push=False)
        self.assertTrue(result["blocked"])
        self.assertEqual(result["steps"][0]["phase"], "heal")
        self.assertEqual(result["steps"][0]["outcome"], "FAILED")
        self.assertEqual(result["steps"][1]["outcome"], "RECONCILE_REQUIRED")
        self.assertEqual(result["disposition"], "RECONCILE_REQUIRED")

    def test_validation_runs_against_this_checkouts_sources(self) -> None:
        """An editable install elsewhere must not win the gate's imports."""

        source = self.root / "src" / "probe_pkg"
        source.mkdir(parents=True)
        (source / "__init__.py").write_text("ORIGIN = 'this-checkout'\n", encoding="utf-8")
        tests = self.root / "tests"
        tests.mkdir(exist_ok=True)
        (tests / "test_probe.py").write_text(
            "import unittest, probe_pkg\n"
            "class T(unittest.TestCase):\n"
            "    def test_origin(self):\n"
            "        self.assertEqual(probe_pkg.ORIGIN, 'this-checkout')\n",
            encoding="utf-8",
        )
        passed, summary = driver.default_validation_runner(self.root)()
        self.assertTrue(passed, summary)

    def test_validation_does_not_inherit_git_environment_variables(self) -> None:
        """An exported GIT_* must not make the gate fail for environmental reasons."""

        tests = self.root / "tests"
        tests.mkdir(exist_ok=True)
        (tests / "test_probe_env.py").write_text(
            "import os, unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_no_inherited_git_vars(self):\n"
            "        self.assertEqual([k for k in os.environ if k.upper().startswith('GIT_')], [])\n",
            encoding="utf-8",
        )
        previous = os.environ.get("GIT_EDITOR")
        os.environ["GIT_EDITOR"] = "true"
        try:
            passed, summary = driver.default_validation_runner(self.root)()
        finally:
            if previous is None:
                os.environ.pop("GIT_EDITOR", None)
            else:
                os.environ["GIT_EDITOR"] = previous
        self.assertTrue(passed, summary)

    def test_blocker_classification_follows_required_authority(self) -> None:
        self.assertEqual(
            driver.classify_blocker("remote branch already exists; reconcile it"), "CLASS_B"
        )
        self.assertEqual(
            driver.classify_blocker("node requires owner credential for delivery"), "CLASS_C"
        )
        self.assertEqual(
            driver.classify_blocker("runbook demands a digest equality the store cannot produce"),
            "CLASS_A",
        )

    def test_triage_reports_without_repairing_a_sealed_blocker(self) -> None:
        blockers = Path(self.plane.blockers_dir)
        blockers.mkdir(parents=True, exist_ok=True)
        (blockers / f"{NODE}.jsonl").write_text(
            json.dumps({"error": "requires production authority"}) + "\n", encoding="utf-8"
        )
        driver.triage_round(self.plane, (NODE,), self.report)
        self.assertEqual(self.report.steps[-1].outcome, "CLASS_C")
        self.assertTrue(self.report.blocked)


if __name__ == "__main__":
    unittest.main()
