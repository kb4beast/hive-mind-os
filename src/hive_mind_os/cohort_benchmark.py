"""Deterministic strict-versus-cohort scheduling measurements.

The estimator models the scheduler contract from declared package durations. It
does not claim real-world superiority; measured production receipts can replace
the duration inputs without changing the comparison shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .brain_kernel.canonical import canonical_digest
from .outcome_graph import OutcomeGraphSpec, OutcomeWorkPackage, compile_outcome_graph


class CohortBenchmarkError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TopologyEstimate:
    topology: str
    elapsed_ms: int
    worker_busy_ms: int
    maximum_workers: int
    peak_parallelism: int
    coordination_checkpoints: int
    dispatch_batches: tuple[tuple[str, ...], ...]

    @property
    def utilization(self) -> float:
        capacity = self.elapsed_ms * self.maximum_workers
        return 0.0 if capacity == 0 else self.worker_busy_ms / capacity

    def to_document(self) -> dict[str, object]:
        return {
            "topology": self.topology,
            "elapsed_ms": self.elapsed_ms,
            "worker_busy_ms": self.worker_busy_ms,
            "maximum_workers": self.maximum_workers,
            "peak_parallelism": self.peak_parallelism,
            "coordination_checkpoints": self.coordination_checkpoints,
            "dispatch_batches": [list(batch) for batch in self.dispatch_batches],
            "utilization": self.utilization,
        }


@dataclass(frozen=True, slots=True)
class CohortEfficiencyReceipt:
    graph_digest: str
    duration_digest: str
    strict: TopologyEstimate
    cohort: TopologyEstimate

    @property
    def elapsed_ms_saved(self) -> int:
        return self.strict.elapsed_ms - self.cohort.elapsed_ms

    @property
    def modeled_speedup(self) -> float:
        if self.cohort.elapsed_ms == 0:
            return 1.0
        return self.strict.elapsed_ms / self.cohort.elapsed_ms

    def to_document(self) -> dict[str, object]:
        return {
            "graph_digest": self.graph_digest,
            "duration_digest": self.duration_digest,
            "strict": self.strict.to_document(),
            "cohort": self.cohort.to_document(),
            "elapsed_ms_saved": self.elapsed_ms_saved,
            "modeled_speedup": self.modeled_speedup,
            "claim_scope": "deterministic-scheduler-model-only",
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())


def _validate_durations(
    graph: OutcomeGraphSpec, durations_ms: Mapping[str, int]
) -> dict[str, int]:
    package_ids = {package.package_id for package in graph.packages}
    if set(durations_ms) != package_ids:
        raise CohortBenchmarkError("durations must bind every package exactly once")
    normalized = dict(durations_ms)
    if any(type(value) is not int or value < 0 for value in normalized.values()):
        raise CohortBenchmarkError("package durations must be nonnegative integers")
    return normalized


def _conflicts(
    package: OutcomeWorkPackage,
    active_packages: tuple[OutcomeWorkPackage, ...],
) -> bool:
    paths = set(package.allowed_paths)
    locks = set(package.semantic_locks)
    return any(
        paths.intersection(active.allowed_paths)
        or locks.intersection(active.semantic_locks)
        for active in active_packages
    )


def compare_execution_topologies(
    graph: OutcomeGraphSpec,
    durations_ms: Mapping[str, int],
    *,
    maximum_workers: int | None = None,
) -> CohortEfficiencyReceipt:
    """Compare strict serialization with the dynamic cohort scheduler."""

    graph = compile_outcome_graph(graph)
    durations = _validate_durations(graph, durations_ms)
    requested_workers = (
        graph.maximum_concurrent if maximum_workers is None else maximum_workers
    )
    if type(requested_workers) is not int or requested_workers < 1:
        raise CohortBenchmarkError("maximum_workers must be a positive integer")
    workers = min(requested_workers, graph.maximum_concurrent)
    by_id = {package.package_id: package for package in graph.packages}
    strict_batches = tuple((package.package_id,) for package in graph.packages)
    strict = TopologyEstimate(
        "strict",
        sum(durations.values()),
        sum(durations.values()),
        1,
        1 if graph.packages else 0,
        len(graph.packages) + (1 if graph.packages else 0),
        strict_batches,
    )

    now = 0
    done: set[str] = set()
    pending = set(by_id)
    active: dict[str, int] = {}
    batches: list[tuple[str, ...]] = []
    peak = 0
    while pending or active:
        active_packages = tuple(by_id[package_id] for package_id in active)
        capacity = workers - len(active)
        launched: list[str] = []
        for package_id in sorted(pending):
            if capacity == 0:
                break
            package = by_id[package_id]
            if not set(package.dependencies) <= done:
                continue
            if _conflicts(package, active_packages):
                continue
            active[package_id] = now + durations[package_id]
            active_packages = (*active_packages, package)
            launched.append(package_id)
            capacity -= 1
        for package_id in launched:
            pending.remove(package_id)
        if launched:
            batches.append(tuple(launched))
            peak = max(peak, len(active))
        if not active:
            raise CohortBenchmarkError("scheduler model cannot make progress")
        next_completion = min(active.values())
        now = next_completion
        completed = {
            package_id
            for package_id, completed_at in active.items()
            if completed_at == next_completion
        }
        for package_id in completed:
            active.pop(package_id)
        done.update(completed)

    cohort = TopologyEstimate(
        "cohort",
        now,
        sum(durations.values()),
        workers,
        peak,
        2 if graph.packages else 0,
        tuple(batches),
    )
    return CohortEfficiencyReceipt(
        graph.digest,
        canonical_digest(dict(sorted(durations.items()))),
        strict,
        cohort,
    )


__all__ = [
    "CohortBenchmarkError",
    "CohortEfficiencyReceipt",
    "TopologyEstimate",
    "compare_execution_topologies",
]
