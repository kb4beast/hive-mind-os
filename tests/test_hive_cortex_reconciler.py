from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hive_mind_os.brain_kernel.reconciler import (
    DesiredStateReconciler,
    ReconciliationPolicy,
    RepairKind,
)
from hive_mind_os.brain_kernel.workers import KernelWorker, ScopeLockStore
from hive_mind_os.scheduler import ManualClock, Scheduler


class HiveCortexReconcilerTests(unittest.TestCase):
    def test_reconciler_transition_tests(self) -> None:
        observed = {
            "mission_id": "MISSION-reconcile",
            "mission_status": "RUNNING",
            "work": {
                "WORK-b": {"status": "RUNNING", "authority_scope": ["src/b.py"]},
                "WORK-a": {"status": "RUNNING", "authority_scope": ["src/a.py"]},
            },
            "leases": [
                {"lease_id": "LEASE-a", "work_id": "WORK-a", "expires_at": 10},
            ],
            "intents": [
                {"intent_id": "INTENT-a", "work_id": "WORK-a"},
            ],
        }
        first = DesiredStateReconciler().reconcile(observed, now=10)
        second = DesiredStateReconciler().reconcile(
            {"intents": list(reversed(observed["intents"])), **{k: v for k, v in observed.items() if k != "intents"}},
            now=10,
        )
        self.assertEqual(first.observed.digest, second.observed.digest)
        self.assertEqual(first.desired.desired_digest, second.desired.desired_digest)
        self.assertEqual(
            [action.kind for action in first.actions],
            [RepairKind.RELEASE_STALE_LEASE, RepairKind.REMAND],
        )
        self.assertEqual(first.actions[0].authority_scope, ("src/a.py",))

    def test_stale_lease_tests(self) -> None:
        result = DesiredStateReconciler().reconcile(
            {
                "mission_id": "MISSION-lease",
                "mission_status": "RUNNING",
                "work": {"WORK-lease": {"status": "LEASED"}},
                "leases": [
                    {"lease_id": "LEASE-stale", "work_id": "WORK-lease", "expires_at": 4}
                ],
            },
            now=5,
        )
        self.assertEqual(result.actions[0].kind, RepairKind.RELEASE_STALE_LEASE)
        self.assertEqual(result.desired.work[0]["desired_status"], "READY")

    def test_crash_recovery_tests(self) -> None:
        result = DesiredStateReconciler(
            ReconciliationPolicy(max_retries=2)
        ).reconcile(
            {
                "mission_id": "MISSION-crash",
                "mission_status": "RUNNING",
                "authority_scope": ["src/allowed.py"],
                "work": {
                    "WORK-crash": {
                        "status": "AWAITING_VERIFICATION",
                        "attempts": 1,
                    }
                },
                "workspaces": [
                    {"workspace_id": "WS-crash", "work_id": "WORK-crash", "exists": False}
                ],
                "provider_failures": [
                    {"failure_id": "FAIL-crash", "work_id": "WORK-crash", "attempts": 1}
                ],
                "verifications": [
                    {
                        "verification_id": "VERIFY-crash",
                        "work_id": "WORK-crash",
                        "status": "INTERRUPTED",
                        "attempts": 1,
                    }
                ],
            },
            now=1,
        )
        self.assertEqual(
            {action.kind for action in result.actions},
            {RepairKind.REBUILD_WORKSPACE, RepairKind.RETRY, RepairKind.REMAND},
        )
        self.assertFalse(result.quarantined)
        self.assertEqual(
            {scope for action in result.actions for scope in action.authority_scope},
            {"src/allowed.py"},
        )

    def test_no_progress_quarantine_tests(self) -> None:
        policy = ReconciliationPolicy(no_progress_limit=2, max_repairs_per_pass=2)
        result = DesiredStateReconciler(policy).reconcile(
            {
                "mission_id": "MISSION-stall",
                "mission_status": "RUNNING",
                "no_progress_count": 2,
                "progress_signature": "same-observation",
                "intents": [
                    {"intent_id": "INTENT-orphan", "work_id": "WORK-missing"}
                ],
            },
            now=1,
        )
        self.assertTrue(result.quarantined)
        self.assertEqual(result.desired.mission_status, "QUARANTINED")
        self.assertTrue(any(action.kind is RepairKind.QUARANTINE for action in result.actions))
        self.assertEqual(result.actions[-1].authority_scope, ())

    def test_worker_adapter_does_not_apply_repairs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            clock = ManualClock(10)
            scheduler = Scheduler(root, clock=clock)
            locks = ScopeLockStore(root)
            try:
                worker = KernelWorker(scheduler, locks, "worker", lambda _: None)
                result = worker.reconcile(
                    {
                        "mission_id": "MISSION-adapter",
                        "mission_status": "RUNNING",
                        "no_progress_count": 3,
                    }
                )
                self.assertTrue(result.quarantined)
                self.assertEqual(scheduler.jobs(), ())
            finally:
                locks.close()
                scheduler.close()


if __name__ == "__main__":
    unittest.main()
