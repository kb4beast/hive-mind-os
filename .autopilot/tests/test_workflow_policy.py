from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class WorkflowPolicyTests(unittest.TestCase):
    def test_policy_is_chatgpt_first_and_codex_last_resort(self) -> None:
        policy = json.loads((ROOT / "workflow-policy.json").read_text(encoding="utf-8"))
        self.assertEqual(policy["preferred_surface"], "chatgpt_classic")
        self.assertEqual(policy["codex_mode"], "last_resort_bounded_subtask_only")
        self.assertEqual(policy["response_contract"]["required_sections"], ["WHAT I DID", "NEXT STEPS", "BLOCKS"])

    def test_control_plane_and_model_routing_reference_policy(self) -> None:
        control = json.loads((ROOT / "control-plane.json").read_text(encoding="utf-8"))
        routing = json.loads((ROOT / "model-routing.json").read_text(encoding="utf-8"))
        self.assertEqual(control["workflow_policy_file"], ".autopilot/workflow-policy.json")
        self.assertEqual(routing["execution_surface_policy"]["preferred"], "chatgpt_classic")

    def test_every_execution_template_embeds_policy(self) -> None:
        for name in ("worker.md", "integration.md", "promotion.md", "reconciliation.md", "repair.md", "replan.md"):
            text = (ROOT / "templates" / name).read_text(encoding="utf-8")
            self.assertIn("ChatGPT Classic owns this node", text)
            self.assertIn("WHAT I DID", text)
            self.assertIn("BLOCKS", text)

    def test_human_escalation_is_novice_safe(self) -> None:
        text = (ROOT / "templates" / "human-escalation.md").read_text(encoding="utf-8")
        self.assertIn("never assume the user knows", text)
        self.assertIn("click-by-click", text)


if __name__ == "__main__":
    unittest.main()
