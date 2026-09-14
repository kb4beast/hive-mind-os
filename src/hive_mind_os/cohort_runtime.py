"""High-throughput dependency-aware cohort execution.

This is the default high-throughput execution model. Existing executors retain
their strict node-by-node contracts as an explicit compatibility mode.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from .brain_kernel.canonical import canonical_bytes, canonical_digest
from .cohort_policy import (
    CheckpointDisposition,
    CohortExecutionMode,
    CohortExecutionPolicy,
    CohortPhase,
    EffectClass,
)
from .outcome_graph import OutcomeGraphSpec, OutcomeWorkPackage, compile_outcome_graph


class CohortRuntimeError(ValueError):
    """A cohort request or callback violated the runtime contract."""


class PackageRunState(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED_DEPENDENCY = "blocked_dependency"
    BLOCKED_POLICY = "blocked_policy"


class CohortRunStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class CohortKickoff:
    """One immutable context object shared by every package in the cohort."""

    run_id: str
    graph_digest: str
    policy_digest: str
    context_digest: str
    context: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class PackageRunResult:
    package_id: str
    state: PackageRunState
    output: Mapping[str, Any]
    evidence_refs: tuple[str, ...] = ()
    message: str = ""

    def __post_init__(self) -> None:
        if not self.package_id or type(self.state) is not PackageRunState:
            raise CohortRuntimeError("package result identity and state must be typed")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise CohortRuntimeError("package evidence references must be unique")


@dataclass(frozen=True, slots=True)
class ConvergenceResult:
    accepted: bool
    output: Mapping[str, Any]
    message: str = ""

    def __post_init__(self) -> None:
        if type(self.accepted) is not bool:
            raise CohortRuntimeError("convergence acceptance must be boolean")


@dataclass(frozen=True, slots=True)
class VerificationResult:
    passed: bool
    checks: tuple[str, ...] = ()
    message: str = ""

    def __post_init__(self) -> None:
        if type(self.passed) is not bool:
            raise CohortRuntimeError("verification result must be boolean")
        if len(set(self.checks)) != len(self.checks):
            raise CohortRuntimeError("terminal verification checks must be unique")


@dataclass(frozen=True, slots=True)
class CohortRunResult:
    run_id: str
    status: CohortRunStatus
    kickoff: CohortKickoff
    package_results: tuple[PackageRunResult, ...]
    convergence: ConvergenceResult
    verification: VerificationResult
    dispatch_batches: tuple[tuple[str, ...], ...]
    max_parallelism: int

    def package(self, package_id: str) -> PackageRunResult:
        for result in self.package_results:
            if result.package_id == package_id:
                return result
        raise CohortRuntimeError(f"cohort has no package {package_id}")


PackageExecutor = Callable[
    [OutcomeWorkPackage, CohortKickoff, Mapping[str, PackageRunResult]],
    PackageRunResult,
]
Converger = Callable[[CohortKickoff, tuple[PackageRunResult, ...]], ConvergenceResult]
TerminalVerifier = Callable[
    [CohortKickoff, tuple[PackageRunResult, ...], ConvergenceResult],
    VerificationResult,
]


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _kickoff(
    graph: OutcomeGraphSpec,
    policy: CohortExecutionPolicy,
    run_id: str,
    context: Mapping[str, Any],
) -> CohortKickoff:
    if type(run_id) is not str or not run_id.strip():
        raise CohortRuntimeError("cohort run id must be nonempty")
    if not isinstance(context, Mapping):
        raise CohortRuntimeError("cohort kickoff context must be a mapping")
    try:
        # Round-trip once to detach the shared context from mutable caller state.
        document = json.loads(canonical_bytes(dict(context)))
    except (TypeError, ValueError) as error:
        raise CohortRuntimeError(
            "cohort kickoff context must be canonical JSON"
        ) from error
    frozen = _freeze(document)
    assert isinstance(frozen, Mapping)
    return CohortKickoff(
        run_id, graph.digest, policy.digest, canonical_digest(document), frozen
    )


class CohortRuntime:
    """Run implementation packages at maximum safe dependency concurrency.

    Package callbacks are execution only: the runtime does not interleave
    advocate/reviewer/judge exchanges.  All package results converge once, then
    the consolidated candidate is verified once at the terminal boundary.
    """

    def __init__(self, policy: CohortExecutionPolicy) -> None:
        if not isinstance(policy, CohortExecutionPolicy):
            raise CohortRuntimeError("cohort runtime requires a typed execution policy")
        if policy.mode is not CohortExecutionMode.COHORT:
            raise CohortRuntimeError(
                "strict execution remains owned by the existing strict runtime"
            )
        self.policy = policy

    def execute(
        self,
        *,
        graph: OutcomeGraphSpec,
        run_id: str,
        kickoff_context: Mapping[str, Any],
        execute_package: PackageExecutor,
        converge: Converger,
        verify: TerminalVerifier,
        effect_classes: Mapping[str, EffectClass] | None = None,
    ) -> CohortRunResult:
        graph = compile_outcome_graph(graph)
        kickoff = _kickoff(graph, self.policy, run_id, kickoff_context)
        by_id = {package.package_id: package for package in graph.packages}
        pending = set(by_id)
        results: dict[str, PackageRunResult] = {}
        batches: list[tuple[str, ...]] = []
        max_parallelism = 0
        classifications = dict(effect_classes or {})
        if set(classifications) - set(by_id):
            raise CohortRuntimeError("effect classification names an unknown package")
        for package_id in sorted(pending):
            effect = classifications.get(package_id, EffectClass.ROUTINE_REVERSIBLE)
            decision = self.policy.checkpoint(effect, CohortPhase.IMPLEMENTATION)
            if decision.disposition is CheckpointDisposition.BLOCKED:
                results[package_id] = PackageRunResult(
                    package_id,
                    PackageRunState.BLOCKED_POLICY,
                    {},
                    message=decision.reason,
                )
        pending.difference_update(results)

        maximum_workers = min(
            graph.maximum_concurrent, self.policy.max_parallel_packages
        )

        with ThreadPoolExecutor(
            max_workers=maximum_workers,
            thread_name_prefix=f"cohort-{run_id}",
        ) as pool:
            active: dict[Future[PackageRunResult], str] = {}
            active_paths: set[str] = set()
            active_locks: set[str] = set()

            while pending or active:
                blocked = sorted(
                    package_id
                    for package_id in pending
                    if any(
                        dependency in results
                        and results[dependency].state is not PackageRunState.SUCCEEDED
                        for dependency in by_id[package_id].dependencies
                    )
                )
                for package_id in blocked:
                    dependency = next(
                        dependency
                        for dependency in by_id[package_id].dependencies
                        if dependency in results
                        and results[dependency].state is not PackageRunState.SUCCEEDED
                    )
                    results[package_id] = PackageRunResult(
                        package_id,
                        PackageRunState.BLOCKED_DEPENDENCY,
                        {},
                        message=f"dependency {dependency} did not succeed",
                    )
                    pending.remove(package_id)

                capacity = maximum_workers - len(active)
                ready = [
                    by_id[package_id]
                    for package_id in sorted(pending)
                    if all(
                        dependency in results
                        and results[dependency].state is PackageRunState.SUCCEEDED
                        for dependency in by_id[package_id].dependencies
                    )
                ]
                launched: list[str] = []
                for package in ready:
                    if capacity == 0:
                        break
                    if active_paths.intersection(
                        package.allowed_paths
                    ) or active_locks.intersection(package.semantic_locks):
                        continue
                    dependency_results = MappingProxyType(
                        {
                            dependency: results[dependency]
                            for dependency in package.dependencies
                        }
                    )
                    future = pool.submit(
                        execute_package, package, kickoff, dependency_results
                    )
                    active[future] = package.package_id
                    active_paths.update(package.allowed_paths)
                    active_locks.update(package.semantic_locks)
                    pending.remove(package.package_id)
                    launched.append(package.package_id)
                    capacity -= 1
                if launched:
                    batches.append(tuple(launched))
                    max_parallelism = max(max_parallelism, len(active))

                if not active:
                    if pending:
                        raise CohortRuntimeError(
                            "cohort cannot make dependency or resource progress"
                        )
                    break

                completed, _ = wait(tuple(active), return_when=FIRST_COMPLETED)
                for future in completed:
                    package_id = active.pop(future)
                    package = by_id[package_id]
                    active_paths.difference_update(package.allowed_paths)
                    active_locks.difference_update(package.semantic_locks)
                    try:
                        result = future.result()
                        if not isinstance(result, PackageRunResult):
                            raise CohortRuntimeError(
                                "package executor returned an untyped result"
                            )
                        if result.package_id != package_id:
                            raise CohortRuntimeError(
                                "package executor returned a cross-package result"
                            )
                    except Exception as error:
                        result = PackageRunResult(
                            package_id,
                            PackageRunState.FAILED,
                            {},
                            message=f"{type(error).__name__}: {error}",
                        )
                    results[package_id] = result

        ordered = tuple(results[package.package_id] for package in graph.packages)
        try:
            convergence = converge(kickoff, ordered)
            if not isinstance(convergence, ConvergenceResult):
                raise CohortRuntimeError("converger returned an untyped result")
        except Exception as error:
            convergence = ConvergenceResult(
                False, {}, f"{type(error).__name__}: {error}"
            )
        try:
            verification = verify(kickoff, ordered, convergence)
            if not isinstance(verification, VerificationResult):
                raise CohortRuntimeError("terminal verifier returned an untyped result")
        except Exception as error:
            verification = VerificationResult(
                False, (), f"{type(error).__name__}: {error}"
            )

        direct_failure = any(item.state is PackageRunState.FAILED for item in ordered)
        dependency_block = any(
            item.state
            in {PackageRunState.BLOCKED_DEPENDENCY, PackageRunState.BLOCKED_POLICY}
            for item in ordered
        )
        if direct_failure or not convergence.accepted or not verification.passed:
            status = CohortRunStatus.FAILED
        elif dependency_block:
            status = CohortRunStatus.BLOCKED
        else:
            status = CohortRunStatus.SUCCEEDED
        return CohortRunResult(
            run_id,
            status,
            kickoff,
            ordered,
            convergence,
            verification,
            tuple(batches),
            max_parallelism,
        )


__all__ = [
    "CohortKickoff",
    "CohortRunResult",
    "CohortRunStatus",
    "CohortRuntime",
    "CohortRuntimeError",
    "ConvergenceResult",
    "PackageRunResult",
    "PackageRunState",
    "VerificationResult",
]
