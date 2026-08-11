from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class WorkflowPolicyTests(unittest.TestCase):
    def test_policy_uses_host_neutral_durable_primary_tasks(self) -> None:
        policy = json.loads((ROOT / "workflow-policy.json").read_text(encoding="utf-8"))
        self.assertEqual(policy["preferred_surface"], "capability_matched_durable_task")
        self.assertEqual(policy["host_policy"]["codex"]["create_primary"], "create_thread")
        self.assertIn("may not replace", policy["host_policy"]["nested_agents"])
        self.assertIn(
            "does not suppress task creation",
            policy["dispatcher_release_barrier"]["parallel_rule"],
        )
        self.assertIn(
            "PREPARATION_ONLY",
            policy["dispatcher_release_barrier"]["preparation_rule"],
        )
        self.assertTrue(policy["global_validation"]["single_authoritative_run"])
        self.assertTrue(
            policy["global_validation"]["lease_required_for_repository_wide_gate"]
        )
        self.assertEqual(policy["response_contract"]["required_sections"], ["WHAT I DID", "NEXT STEPS", "BLOCKS"])

    def test_control_plane_and_model_routing_reference_policy(self) -> None:
        control = json.loads((ROOT / "control-plane.json").read_text(encoding="utf-8"))
        routing = json.loads((ROOT / "model-routing.json").read_text(encoding="utf-8"))
        self.assertEqual(control["workflow_policy_file"], ".autopilot/workflow-policy.json")
        self.assertEqual(
            routing["execution_surface_policy"]["preferred"],
            "capability_matched_durable_task",
        )

    def test_every_execution_template_embeds_policy(self) -> None:
        for name in ("worker.md", "integration.md", "promotion.md", "reconciliation.md", "repair.md", "replan.md"):
            text = (ROOT / "templates" / name).read_text(encoding="utf-8")
            self.assertIn("durable primary task owns this node", text)
            self.assertIn("WHAT I DID", text)
            self.assertIn("BLOCKS", text)
            self.assertIn("validation-lease-acquire", text)
            self.assertIn("non-verdict evidence", text)
            self.assertIn("complete visible task cohort", text)
            self.assertIn("PREPARATION_ONLY", text)

    def test_human_escalation_is_novice_safe(self) -> None:
        text = (ROOT / "templates" / "human-escalation.md").read_text(encoding="utf-8")
        self.assertIn("never assume the user knows", text)
        self.assertIn("click-by-click", text)

    def test_orchestration_module_survives_a_clean_checkout(self) -> None:
        repository = ROOT.parent
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", ".autopilot/bin/orchestration.py"],
            cwd=repository,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        policy = json.loads((ROOT / "orchestration-policy.json").read_text(encoding="utf-8"))
        self.assertEqual(
            policy["task_transport"]["binding_sequence"],
            ["PREPARED", "CREATED", "BOUND", "TERMINAL_OBSERVED", "RELEASED"],
        )
        validation = policy["wave"]["repository_wide_validation"]
        self.assertTrue(validation["lease_required"])
        self.assertFalse(validation["retry_while_another_owner_holds_lease"])
        cohort = policy["parallel_task_cohort"]
        self.assertTrue(cohort["create_released_tasks_even_when_recovery_tasks_exist"])
        self.assertTrue(cohort["create_eligible_preparation_tasks"])
        self.assertTrue(cohort["create_entire_cohort_before_first_wait"])
        self.assertTrue(cohort["poll_every_created_task_to_terminal"])


if __name__ == "__main__":
    unittest.main()
