from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "bin"


def _load():
    spec = importlib.util.spec_from_file_location(
        "host_scheduler_test_module", BIN / "host_scheduler.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


scheduler = _load()
DIGEST = "sha256:" + "a" * 64


class HostSchedulerTests(unittest.TestCase):
    def demand(
        self,
        execution: str,
        slots: int,
        *,
        epoch: int,
        weight: int = 1,
        repository: str | None = None,
    ):
        suffix = execution.rsplit("-", 1)[-1]
        return scheduler.make_demand(
            host_id="host-1",
            repository_transport_digest=repository or DIGEST,
            execution_namespace="namespace-" + suffix,
            execution_id="sha256:" + suffix * 64,
            plan_fingerprint=DIGEST,
            capacity_generation=DIGEST,
            requested_slots=slots,
            weight=weight,
            enqueued_epoch=epoch,
        )

    def test_wide_frontier_uses_all_four_slots_without_requiring_thirteen(self) -> None:
        wide = self.demand("execution-b", 13, epoch=1)
        result = scheduler.weighted_round_robin(
            [wide], available_slots=4, cursor_execution_id=None
        )
        self.assertEqual(result["grants"][0]["slots"], 4)
        self.assertEqual(result["ungranted"][0]["remaining_slots"], 9)

    def test_small_execution_cannot_starve_behind_wide_execution(self) -> None:
        wide = self.demand("execution-b", 13, epoch=1)
        small = self.demand("execution-c", 1, epoch=2)
        result = scheduler.weighted_round_robin(
            [wide, small],
            available_slots=4,
            cursor_execution_id=wide["execution_id"],
        )
        grants = {item["execution_id"]: item["slots"] for item in result["grants"]}
        self.assertEqual(grants[small["execution_id"]], 1)
        self.assertEqual(grants[wide["execution_id"]], 3)
        self.assertEqual(result["cursor_execution_id"], wide["execution_id"])

    def test_weighted_policy_is_deterministic_and_work_conserving(self) -> None:
        first = self.demand("execution-b", 8, epoch=1, weight=2)
        second = self.demand("execution-c", 8, epoch=1, weight=1)
        forward = scheduler.weighted_round_robin(
            [first, second], available_slots=7, cursor_execution_id=None
        )
        reverse = scheduler.weighted_round_robin(
            [second, first], available_slots=7, cursor_execution_id=None
        )
        self.assertEqual(forward, reverse)
        self.assertEqual(sum(item["slots"] for item in forward["grants"]), 7)
        grants = {item["execution_id"]: item["slots"] for item in forward["grants"]}
        self.assertGreater(grants[first["execution_id"]], grants[second["execution_id"]])

    def test_forged_or_duplicate_demand_is_rejected(self) -> None:
        demand = self.demand("execution-b", 1, epoch=1)
        forged = dict(demand)
        forged["requested_slots"] = 2
        with self.assertRaisesRegex(scheduler.HostSchedulerError, "digest"):
            scheduler.weighted_round_robin(
                [forged], available_slots=1, cursor_execution_id=None
            )
        with self.assertRaisesRegex(scheduler.HostSchedulerError, "duplicated"):
            scheduler.weighted_round_robin(
                [demand, demand], available_slots=1, cursor_execution_id=None
            )


if __name__ == "__main__":
    unittest.main()
