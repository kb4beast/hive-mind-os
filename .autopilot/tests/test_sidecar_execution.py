from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

from sidecar_execution import (  # noqa: E402
    SidecarPolicyError,
    active_sidecars,
    make_descendant_spec,
    plan_sidecars,
    record_sidecar_state,
    sidecar_events,
    sidecar_spec_digest,
    validate_sidecar_policy,
)


class SidecarExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / ".autopilot").mkdir()
        source = Path(__file__).resolve().parents[1]
        shutil.copy2(source / "sidecar-bindings.lock", self.root / ".autopilot" / "sidecar-bindings.lock")
        self.policy = json.loads((source / "orchestration-policy.json").read_text(encoding="utf-8"))["sidecars"]
        self.task = {
            "launch_instruction_id": "sha256:" + "1" * 64,
            "node_id": "NODE-1",
            "authority_mode": "EXECUTION_AUTHORIZED",
        }
        self.node = {
            "risk": "high",
            "read_scope": ["a", "b", "c"],
            "evidence_requirements": ["one", "two", "three"],
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_planning_is_deterministic_token_positive_and_bounded(self) -> None:
        first = plan_sidecars([self.task], {"NODE-1": self.node}, self.policy)
        second = plan_sidecars([dict(reversed(list(self.task.items())))], {"NODE-1": dict(reversed(list(self.node.items())))}, self.policy)
        self.assertEqual(first, second)
        self.assertLessEqual(len(first), self.policy["max_sidecars_per_primary"])
        self.assertTrue(all(item["estimated_net_savings_tokens"] >= self.policy["min_net_savings_tokens"] for item in first))
        self.assertTrue(all(sidecar_spec_digest(item) == item["sidecar_id"] for item in first))

    def test_insufficient_net_savings_admits_nothing(self) -> None:
        policy = dict(self.policy)
        policy["min_net_savings_tokens"] = 100_000
        self.assertEqual(plan_sidecars([self.task], {"NODE-1": self.node}, policy), ())

    def test_descendant_is_root_authenticated_and_depth_bounded(self) -> None:
        parent = plan_sidecars([self.task], {"NODE-1": self.node}, self.policy)[0]
        child = make_descendant_spec(parent, {"purpose": "independent_review", "prompt": "Review exact evidence", "evidence_refs": ["receipt:1"]}, self.policy)
        self.assertEqual(child["depth"], 2)
        self.assertEqual(child["parent_sidecar_id"], parent["sidecar_id"])
        self.assertEqual(sidecar_spec_digest(child), child["sidecar_id"])
        with self.assertRaisesRegex(SidecarPolicyError, "depth"):
            make_descendant_spec(child, {"purpose": "independent_review", "prompt": "too deep", "evidence_refs": ["receipt:1"]}, self.policy)

    def test_descendant_without_evidence_is_denied(self) -> None:
        parent = plan_sidecars([self.task], {"NODE-1": self.node}, self.policy)[0]
        with self.assertRaisesRegex(SidecarPolicyError, "evidence"):
            make_descendant_spec(parent, {"purpose": "independent_review", "prompt": "review", "evidence_refs": []}, self.policy)

    def test_ledger_is_hash_chained_and_terminal_is_monotonic(self) -> None:
        sidecar_id = "sha256:" + "2" * 64
        record_sidecar_state(self.root, sidecar_id, "PREPARED", parent_launch_instruction_id=self.task["launch_instruction_id"])
        self.assertEqual(len(active_sidecars(self.root)), 1)
        terminal = record_sidecar_state(self.root, sidecar_id, "FAILED", reason="bounded")
        self.assertEqual(record_sidecar_state(self.root, sidecar_id, "FAILED", reason="bounded"), terminal)
        self.assertEqual(active_sidecars(self.root), ())
        self.assertEqual(len(sidecar_events(self.root)), 2)
        with self.assertRaisesRegex(SidecarPolicyError, "cannot regress"):
            record_sidecar_state(self.root, sidecar_id, "ACTIVE")

    def test_policy_rejects_unbounded_or_authority_inheriting_sidecars(self) -> None:
        for field, value in (("max_depth", 3), ("primary_authority_inheritance", True), ("require_parent_ack", False)):
            with self.subTest(field=field):
                policy = dict(self.policy)
                policy[field] = value
                self.assertTrue(validate_sidecar_policy(policy))


if __name__ == "__main__":
    unittest.main()
