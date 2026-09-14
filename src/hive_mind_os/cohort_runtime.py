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
from .cohort_journal import (
    CohortJournalEvent,
    CohortJournalEventKind,
    CohortJournalStore,
)
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


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def _canonical_output(value: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        document = json.loads(canonical_bytes(dict(value)))
    except (TypeError, ValueError) as error:
        raise CohortRuntimeError("cohort output must be canonical JSON") from error
    if type(document) is not dict:
        raise CohortRuntimeError("cohort output must be a JSON object")
    return document


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

    def __init__(
        self,
        policy: CohortExecutionPolicy,
        journal: CohortJournalStore | None = None,
    ) -> None:
        if not isinstance(policy, CohortExecutionPolicy):
            raise CohortRuntimeError("cohort runtime requires a typed execution policy")
        if policy.mode is not CohortExecutionMode.COHORT:
            raise CohortRuntimeError(
                "strict execution remains owned by the existing strict runtime"
            )
        self.policy = policy
        self.journal = journal

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
        resume: bool = True,
        finalize: bool = True,
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
        kickoff_record = {
            "graph_digest": kickoff.graph_digest,
            "policy_digest": kickoff.policy_digest,
            "context_digest": kickoff.context_digest,
            "context": _thaw(kickoff.context),
            "effect_classes": {
                package_id: effect.value
                for package_id, effect in sorted(classifications.items())
            },
        }
        retained: tuple[CohortJournalEvent, ...] = ()
        retained_convergence: ConvergenceResult | None = None
        retained_verification: VerificationResult | None = None
        retained_completion: CohortRunStatus | None = None
        if self.journal is not None:
            retained = self.journal.events(run_id)
            if retained and not resume:
                raise CohortRuntimeError(
                    "cohort journal already exists and resume was disabled"
                )
            if retained:
                if retained[
                    0
                ].kind is not CohortJournalEventKind.KICKOFF or canonical_bytes(
                    _thaw(retained[0].payload)
                ) != canonical_bytes(kickoff_record):
                    raise CohortRuntimeError(
                        "retained cohort kickoff does not match this execution"
                    )
                (
                    results,
                    batches,
                    max_parallelism,
                    retained_convergence,
                    retained_verification,
                    retained_completion,
                ) = self._replay(retained, by_id)
                pending.difference_update(results)
            else:
                self.journal.append(
                    run_id, CohortJournalEventKind.KICKOFF, kickoff_record
                )
        for package_id in sorted(pending):
            effect = classifications.get(package_id, EffectClass.ROUTINE_REVERSIBLE)
            decision = self.policy.checkpoint(effect, CohortPhase.IMPLEMENTATION)
            if decision.disposition is CheckpointDisposition.BLOCKED:
                result = PackageRunResult(
                    package_id,
                    PackageRunState.BLOCKED_POLICY,
                    {},
                    message=decision.reason,
                )
                result = self._record_package_result(run_id, result, "policy")
                results[package_id] = result
        pending.difference_update(results)

        if retained_completion is not None:
            assert retained_convergence is not None
            assert retained_verification is not None
            ordered = tuple(results[package.package_id] for package in graph.packages)
            status = self._status(ordered, retained_convergence, retained_verification)
            if status is not retained_completion:
                raise CohortRuntimeError(
                    "retained cohort completion contradicts replayed results"
                )
            return CohortRunResult(
                run_id,
                status,
                kickoff,
                ordered,
                retained_convergence,
                retained_verification,
                tuple(batches),
                max_parallelism,
            )

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
                    result = PackageRunResult(
                        package_id,
                        PackageRunState.BLOCKED_DEPENDENCY,
                        {},
                        message=f"dependency {dependency} did not succeed",
                    )
                    result = self._record_package_result(run_id, result, "dependency")
                    results[package_id] = result
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
                    if self.journal is not None:
                        self.journal.append(
                            run_id,
                            CohortJournalEventKind.DISPATCH,
                            {
                                "batch_index": len(batches),
                                "package_ids": launched,
                                "active_count": len(active),
                            },
                        )

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
                    result = self._record_package_result(run_id, result, "executor")
                    results[package_id] = result

        ordered = tuple(results[package.package_id] for package in graph.packages)
        if retained_convergence is None:
            try:
                convergence = converge(kickoff, ordered)
                if not isinstance(convergence, ConvergenceResult):
                    raise CohortRuntimeError("converger returned an untyped result")
            except Exception as error:
                convergence = ConvergenceResult(
                    False, {}, f"{type(error).__name__}: {error}"
                )
            if self.journal is not None:
                convergence = ConvergenceResult(
                    convergence.accepted,
                    _canonical_output(convergence.output),
                    convergence.message,
                )
                self.journal.append(
                    run_id,
                    CohortJournalEventKind.CONVERGENCE,
                    self._convergence_document(convergence),
                )
        else:
            convergence = retained_convergence
        if retained_verification is None:
            try:
                verification = verify(kickoff, ordered, convergence)
                if not isinstance(verification, VerificationResult):
                    raise CohortRuntimeError(
                        "terminal verifier returned an untyped result"
                    )
            except Exception as error:
                verification = VerificationResult(
                    False, (), f"{type(error).__name__}: {error}"
                )
            if self.journal is not None:
                self.journal.append(
                    run_id,
                    CohortJournalEventKind.VERIFICATION,
                    self._verification_document(verification),
                )
        else:
            verification = retained_verification

        status = self._status(ordered, convergence, verification)
        completed = CohortRunResult(
            run_id,
            status,
            kickoff,
            ordered,
            convergence,
            verification,
            tuple(batches),
            max_parallelism,
        )
        if finalize:
            self.record_completion(completed)
        return completed

    def record_completion(self, result: CohortRunResult) -> None:
        """Seal a journal lifecycle after a composing assurance layer finishes."""

        if not isinstance(result, CohortRunResult):
            raise CohortRuntimeError("cohort completion result must be typed")
        if self.journal is None:
            return
        retained = self.journal.events(result.run_id)
        if retained and retained[-1].kind is CohortJournalEventKind.RUN_COMPLETED:
            return
        self.journal.append(
            result.run_id,
            CohortJournalEventKind.RUN_COMPLETED,
            {
                "status": result.status.value,
                "package_count": len(result.package_results),
                "dispatch_batch_count": len(result.dispatch_batches),
                "max_parallelism": result.max_parallelism,
            },
        )

    def _record_package_result(
        self, run_id: str, result: PackageRunResult, source: str
    ) -> PackageRunResult:
        if self.journal is None:
            return result
        normalized = PackageRunResult(
            result.package_id,
            result.state,
            _canonical_output(result.output),
            result.evidence_refs,
            result.message,
        )
        self.journal.append(
            run_id,
            CohortJournalEventKind.PACKAGE_RESULT,
            {
                "package_id": normalized.package_id,
                "state": normalized.state.value,
                "output": normalized.output,
                "evidence_refs": list(normalized.evidence_refs),
                "message": normalized.message,
                "source": source,
            },
        )
        return normalized

    @staticmethod
    def _convergence_document(result: ConvergenceResult) -> dict[str, Any]:
        return {
            "accepted": result.accepted,
            "output": _thaw(result.output),
            "message": result.message,
        }

    @staticmethod
    def _verification_document(result: VerificationResult) -> dict[str, Any]:
        return {
            "passed": result.passed,
            "checks": list(result.checks),
            "message": result.message,
        }

    @staticmethod
    def _status(
        ordered: tuple[PackageRunResult, ...],
        convergence: ConvergenceResult,
        verification: VerificationResult,
    ) -> CohortRunStatus:
        direct_failure = any(item.state is PackageRunState.FAILED for item in ordered)
        dependency_block = any(
            item.state
            in {PackageRunState.BLOCKED_DEPENDENCY, PackageRunState.BLOCKED_POLICY}
            for item in ordered
        )
        if direct_failure or not convergence.accepted or not verification.passed:
            return CohortRunStatus.FAILED
        if dependency_block:
            return CohortRunStatus.BLOCKED
        return CohortRunStatus.SUCCEEDED

    @classmethod
    def _replay(
        cls,
        retained: tuple[CohortJournalEvent, ...],
        by_id: Mapping[str, OutcomeWorkPackage],
    ) -> tuple[
        dict[str, PackageRunResult],
        list[tuple[str, ...]],
        int,
        ConvergenceResult | None,
        VerificationResult | None,
        CohortRunStatus | None,
    ]:
        results: dict[str, PackageRunResult] = {}
        batches: list[tuple[str, ...]] = []
        dispatched: set[str] = set()
        max_parallelism = 0
        convergence: ConvergenceResult | None = None
        verification: VerificationResult | None = None
        completion: CohortRunStatus | None = None
        for event in retained[1:]:
            payload = event.payload
            if event.kind is CohortJournalEventKind.DISPATCH:
                package_ids = payload.get("package_ids")
                active_count = payload.get("active_count")
                if (
                    not isinstance(package_ids, tuple)
                    or not package_ids
                    or any(
                        type(item) is not str or item not in by_id
                        for item in package_ids
                    )
                    or type(active_count) is not int
                    or active_count < 1
                ):
                    raise CohortRuntimeError("retained cohort dispatch is invalid")
                batches.append(package_ids)
                dispatched.update(package_ids)
                max_parallelism = max(max_parallelism, active_count)
            elif event.kind is CohortJournalEventKind.PACKAGE_RESULT:
                result = cls._package_result_from_document(payload)
                if result.package_id not in by_id:
                    raise CohortRuntimeError("retained result names an unknown package")
                if result.package_id in results:
                    raise CohortRuntimeError("retained package result is duplicated")
                source = payload.get("source")
                if source == "executor" and result.package_id not in dispatched:
                    raise CohortRuntimeError(
                        "retained package result has no dispatch evidence"
                    )
                if source not in {"executor", "policy", "dependency"}:
                    raise CohortRuntimeError(
                        "retained package result source is invalid"
                    )
                if (
                    source == "policy"
                    and result.state is not PackageRunState.BLOCKED_POLICY
                ) or (
                    source == "dependency"
                    and result.state is not PackageRunState.BLOCKED_DEPENDENCY
                ):
                    raise CohortRuntimeError(
                        "retained package result source contradicts its state"
                    )
                results[result.package_id] = result
            elif event.kind is CohortJournalEventKind.CONVERGENCE:
                if set(results) != set(by_id):
                    raise CohortRuntimeError(
                        "retained convergence precedes package completion"
                    )
                convergence = cls._convergence_from_document(payload)
            elif event.kind is CohortJournalEventKind.VERIFICATION:
                if convergence is None:
                    raise CohortRuntimeError(
                        "retained verification precedes convergence"
                    )
                verification = cls._verification_from_document(payload)
            elif event.kind is CohortJournalEventKind.RUN_COMPLETED:
                if verification is None:
                    raise CohortRuntimeError(
                        "retained completion precedes verification"
                    )
                try:
                    completion = CohortRunStatus(payload["status"])
                except (KeyError, ValueError) as error:
                    raise CohortRuntimeError(
                        "retained completion status is invalid"
                    ) from error
            elif event.kind is CohortJournalEventKind.REPAIR_ATTEMPT:
                convergence = None
                verification = None
            elif event.kind is CohortJournalEventKind.REPAIR_RESULT:
                documents = payload.get("package_results")
                if not isinstance(documents, tuple) or not documents:
                    raise CohortRuntimeError("retained repair result is invalid")
                for document in documents:
                    if not isinstance(document, Mapping):
                        raise CohortRuntimeError("retained repair result is invalid")
                    result = cls._package_result_from_document(document)
                    if result.package_id not in by_id:
                        raise CohortRuntimeError(
                            "retained repair result names an unknown package"
                        )
                    results[result.package_id] = result
                convergence = None
                verification = None
            elif event.kind is CohortJournalEventKind.TERMINAL_EVIDENCE:
                continue
        if completion is not None and set(results) != set(by_id):
            raise CohortRuntimeError("retained completed cohort is missing results")
        return (
            results,
            batches,
            max_parallelism,
            convergence,
            verification,
            completion,
        )

    @staticmethod
    def _package_result_from_document(
        document: Mapping[str, Any],
    ) -> PackageRunResult:
        try:
            package_id = document["package_id"]
            state = PackageRunState(document["state"])
            output = document["output"]
            evidence_refs = document["evidence_refs"]
            message = document["message"]
        except (KeyError, ValueError, TypeError) as error:
            raise CohortRuntimeError("retained package result is invalid") from error
        if (
            type(package_id) is not str
            or not isinstance(output, Mapping)
            or not isinstance(evidence_refs, tuple)
            or any(type(item) is not str for item in evidence_refs)
            or type(message) is not str
        ):
            raise CohortRuntimeError("retained package result is invalid")
        return PackageRunResult(
            package_id, state, _thaw(output), evidence_refs, message
        )

    @staticmethod
    def _convergence_from_document(
        document: Mapping[str, Any],
    ) -> ConvergenceResult:
        accepted = document.get("accepted")
        output = document.get("output")
        message = document.get("message")
        if (
            type(accepted) is not bool
            or not isinstance(output, Mapping)
            or type(message) is not str
        ):
            raise CohortRuntimeError("retained convergence is invalid")
        return ConvergenceResult(accepted, _thaw(output), message)

    @staticmethod
    def _verification_from_document(
        document: Mapping[str, Any],
    ) -> VerificationResult:
        passed = document.get("passed")
        checks = document.get("checks")
        message = document.get("message")
        if (
            type(passed) is not bool
            or not isinstance(checks, tuple)
            or any(type(item) is not str for item in checks)
            or type(message) is not str
        ):
            raise CohortRuntimeError("retained verification is invalid")
        return VerificationResult(passed, checks, message)


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
