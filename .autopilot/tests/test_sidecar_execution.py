from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

BIN = Path(__file__).resolve().parents[1] / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import sidecar_execution as sidecar_module  # noqa: E402
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
        self.authority = {
            "parent_launch_instruction_id": self.task["launch_instruction_id"],
            "parent_sidecar_id": None,
            "parent_resource_key": "sha256:" + "8" * 64,
            "parent_authority_epoch": 1,
            "parent_authority_class": "PREPARATION_ONLY",
            "parent_dispatcher_release_id": None,
            "parent_dispatcher_admission_epoch": None,
            "host_reservation_id": "sha256:" + "9" * 64,
            "capacity_host_id": "fixture:host",
            "capacity_generation": "sha256:" + "a" * 64,
            "capacity_epoch": 1,
            "reservation_expires_at": "2030-01-01T01:00:00Z",
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
        record_sidecar_state(self.root, sidecar_id, "PREPARED", **self.authority)
        self.assertEqual(len(active_sidecars(self.root)), 1)
        terminal = record_sidecar_state(self.root, sidecar_id, "FAILED", reason="bounded")
        self.assertEqual(record_sidecar_state(self.root, sidecar_id, "FAILED", reason="bounded"), terminal)
        self.assertEqual(active_sidecars(self.root), ())
        self.assertEqual(len(sidecar_events(self.root)), 2)
        with self.assertRaisesRegex(SidecarPolicyError, "cannot regress"):
            record_sidecar_state(self.root, sidecar_id, "ACTIVE")

    def test_competing_terminal_writes_are_serialized_under_one_lock(self) -> None:
        sidecar_id = "sha256:" + "3" * 64
        record_sidecar_state(
            self.root,
            sidecar_id,
            "PREPARED",
            **self.authority,
        )
        barrier = threading.Barrier(2)

        def settle(state: str) -> str:
            barrier.wait()
            try:
                record_sidecar_state(self.root, sidecar_id, state, reason=state)
                return "accepted"
            except SidecarPolicyError:
                return "rejected"

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(settle, ("SUCCEEDED", "FAILED")))
        self.assertEqual(sorted(outcomes), ["accepted", "rejected"])
        events = sidecar_events(self.root)
        self.assertEqual(len(events), 2)
        self.assertIn(events[-1]["state"], {"SUCCEEDED", "FAILED"})
        self.assertEqual(active_sidecars(self.root), ())

    def test_capacity_denial_is_a_first_class_terminal_admission_receipt(self) -> None:
        sidecar_id = "sha256:" + "7" * 64
        authority = dict(self.authority)
        authority.pop("host_reservation_id")
        denied = record_sidecar_state(
            self.root,
            sidecar_id,
            "SKIPPED_CAPACITY",
            **authority,
            spec_digest="sha256:" + "6" * 64,
            token_budget_reserved=100,
            admission_code="ADMISSION_DENIED",
            reason="authenticated host capacity is exhausted",
        )
        self.assertEqual(denied["state"], "SKIPPED_CAPACITY")
        self.assertNotIn("host_reservation_id", denied)
        self.assertEqual(active_sidecars(self.root), ())
        self.assertEqual(sidecar_events(self.root), (denied,))

    def test_first_sidecar_read_waits_for_first_append_barrier(self) -> None:
        sidecar_id = "sha256:" + "4" * 64
        append_entered = threading.Event()
        allow_append = threading.Event()
        original = sidecar_module._append_unlocked

        def delayed_append(*args, **kwargs):
            append_entered.set()
            self.assertTrue(allow_append.wait(2))
            return original(*args, **kwargs)

        with patch.object(sidecar_module, "_append_unlocked", side_effect=delayed_append):
            with ThreadPoolExecutor(max_workers=2) as executor:
                writer = executor.submit(
                    record_sidecar_state,
                    self.root,
                    sidecar_id,
                    "PREPARED",
                    **self.authority,
                )
                self.assertTrue(append_entered.wait(2))
                reader = executor.submit(sidecar_events, self.root)
                self.assertFalse(reader.done())
                allow_append.set()
                written = writer.result(timeout=3)
                observed = reader.result(timeout=3)
        self.assertEqual([event["event_id"] for event in observed], [written["event_id"]])

    def test_empty_sidecar_read_is_non_mutating(self) -> None:
        state = self.root / ".autopilot" / "state"
        self.assertEqual(sidecar_events(self.root), ())
        self.assertFalse(state.exists())

    def test_policy_rejects_unbounded_or_authority_inheriting_sidecars(self) -> None:
        for field, value in (("max_depth", 3), ("primary_authority_inheritance", True), ("require_parent_ack", False)):
            with self.subTest(field=field):
                policy = dict(self.policy)
                policy[field] = value
                self.assertTrue(validate_sidecar_policy(policy))


if __name__ == "__main__":
    unittest.main()
