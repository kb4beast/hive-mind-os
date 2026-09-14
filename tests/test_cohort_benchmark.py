from __future__ import annotations

import unittest

from hive_mind_os.cohort_benchmark import (
    CohortBenchmarkError,
    compare_execution_topologies,
)
from hive_mind_os.outcome_graph import OutcomeGraphSpec, OutcomeWorkPackage


def package(
    package_id: str, *dependencies: str, lock: str | None = None
) -> OutcomeWorkPackage:
    return OutcomeWorkPackage(
        package_id,
        (f"outcome-{package_id}",),
        dependencies=dependencies,
        semantic_locks=() if lock is None else (lock,),
    )


class CohortBenchmarkTests(unittest.TestCase):
    def test_independent_work_models_one_parallel_batch(self) -> None:
        graph = OutcomeGraphSpec(
            tuple(package(name) for name in "abcd"),
            "sha256:" + "1" * 64,
            maximum_concurrent=4,
        )
        receipt = compare_execution_topologies(graph, {name: 100 for name in "abcd"})

        self.assertEqual(receipt.strict.elapsed_ms, 400)
        self.assertEqual(receipt.cohort.elapsed_ms, 100)
        self.assertEqual(receipt.cohort.peak_parallelism, 4)
        self.assertEqual(receipt.strict.coordination_checkpoints, 5)
        self.assertEqual(receipt.cohort.coordination_checkpoints, 2)
        self.assertEqual(receipt.modeled_speedup, 4.0)
        self.assertEqual(
            receipt.to_document()["claim_scope"],
            "deterministic-scheduler-model-only",
        )

    def test_dynamic_refill_does_not_wait_for_slow_peer(self) -> None:
        graph = OutcomeGraphSpec(
            (package("fast"), package("slow"), package("next", "fast")),
            "sha256:" + "2" * 64,
            maximum_concurrent=2,
        )
        receipt = compare_execution_topologies(
            graph, {"fast": 100, "slow": 300, "next": 100}
        )

        self.assertEqual(receipt.strict.elapsed_ms, 500)
        self.assertEqual(receipt.cohort.elapsed_ms, 300)
        self.assertEqual(receipt.cohort.dispatch_batches, (("fast", "slow"), ("next",)))

    def test_semantic_lock_serializes_conflicting_ready_work(self) -> None:
        graph = OutcomeGraphSpec(
            (package("a", lock="shared"), package("b", lock="shared")),
            "sha256:" + "3" * 64,
            maximum_concurrent=2,
        )
        receipt = compare_execution_topologies(graph, {"a": 50, "b": 50})

        self.assertEqual(receipt.cohort.elapsed_ms, 100)
        self.assertEqual(receipt.cohort.peak_parallelism, 1)

    def test_duration_manifest_must_be_exact_and_nonnegative(self) -> None:
        graph = OutcomeGraphSpec(
            (package("a"), package("b")),
            "sha256:" + "4" * 64,
            maximum_concurrent=2,
        )
        with self.assertRaisesRegex(CohortBenchmarkError, "exactly once"):
            compare_execution_topologies(graph, {"a": 1})
        with self.assertRaisesRegex(CohortBenchmarkError, "nonnegative"):
            compare_execution_topologies(graph, {"a": 1, "b": -1})


if __name__ == "__main__":
    unittest.main()
