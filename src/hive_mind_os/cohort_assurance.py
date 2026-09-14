"""End-loaded evidence and bounded repair for cohort execution."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from .brain_kernel.canonical import canonical_digest
from .cohort_journal import CohortJournalEventKind, CohortJournalStore
from .cohort_policy import CohortExecutionPolicy, EffectClass
from .cohort_runtime import (
    CohortKickoff,
    CohortRunResult,
    CohortRunStatus,
    CohortRuntime,
    CohortRuntimeError,
    ConvergenceResult,
    PackageExecutor,
    PackageRunResult,
    PackageRunState,
    VerificationResult,
)
from .outcome_graph import OutcomeGraphSpec, OutcomeWorkPackage, compile_outcome_graph


class CohortAssuranceError(CohortRuntimeError):
    """A terminal assurance or repair contract was malformed."""


_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def convergence_candidate_digest(convergence: ConvergenceResult) -> str:
    """Return the canonical digest every terminal receipt must bind."""

    if not isinstance(convergence, ConvergenceResult):
        raise CohortAssuranceError("candidate convergence must be typed")
    return canonical_digest(_plain(convergence.output))


@dataclass(frozen=True, slots=True)
class TerminalEvidence:
    """Typed receipts required before a cohort candidate can succeed."""

    candidate_digest: str
    producer_identity: str
    reviewer_identity: str
    review_refs: tuple[str, ...]
    aggregate_refs: tuple[str, ...]
    verification_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _SHA256.fullmatch(self.candidate_digest):
            raise CohortAssuranceError(
                "candidate digest must be a lowercase SHA-256 ref"
            )
        if not self.producer_identity.strip() or not self.reviewer_identity.strip():
            raise CohortAssuranceError(
                "producer and terminal reviewer identities are required"
            )
        if self.producer_identity == self.reviewer_identity:
            raise CohortAssuranceError(
                "terminal reviewer must be independent from the candidate producer"
            )
        for name, refs in (
            ("review", self.review_refs),
            ("aggregate", self.aggregate_refs),
            ("verification", self.verification_refs),
        ):
            if not refs or any(not ref.strip() for ref in refs):
                raise CohortAssuranceError(f"{name} evidence references are required")
            if len(set(refs)) != len(refs):
                raise CohortAssuranceError(f"{name} evidence references must be unique")
            if any(self.candidate_digest not in ref for ref in refs):
                raise CohortAssuranceError(
                    f"{name} evidence references must bind the candidate digest"
                )

    def to_document(self) -> dict[str, object]:
        return {
            "candidate_digest": self.candidate_digest,
            "producer_identity": self.producer_identity,
            "reviewer_identity": self.reviewer_identity,
            "review_refs": list(self.review_refs),
            "aggregate_refs": list(self.aggregate_refs),
            "verification_refs": list(self.verification_refs),
        }

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> "TerminalEvidence":
        required = {
            "candidate_digest",
            "producer_identity",
            "reviewer_identity",
            "review_refs",
            "aggregate_refs",
            "verification_refs",
        }
        if set(document) != required:
            raise CohortAssuranceError("terminal evidence document has unknown fields")
        refs: list[tuple[str, ...]] = []
        for name in ("review_refs", "aggregate_refs", "verification_refs"):
            value = document[name]
            if not isinstance(value, (list, tuple)) or any(
                type(item) is not str for item in value
            ):
                raise CohortAssuranceError("terminal evidence references are invalid")
            refs.append(tuple(value))
        candidate_digest = document["candidate_digest"]
        producer_identity = document["producer_identity"]
        reviewer_identity = document["reviewer_identity"]
        if not (
            isinstance(candidate_digest, str)
            and isinstance(producer_identity, str)
            and isinstance(reviewer_identity, str)
        ):
            raise CohortAssuranceError("terminal evidence identities are invalid")
        return cls(
            candidate_digest,
            producer_identity,
            reviewer_identity,
            refs[0],
            refs[1],
            refs[2],
        )


@dataclass(frozen=True, slots=True)
class TerminalAssessment:
    """One evidence-bearing decision at a convergence boundary."""

    verification: VerificationResult
    evidence: TerminalEvidence

    def __post_init__(self) -> None:
        if not isinstance(self.verification, VerificationResult):
            raise CohortAssuranceError("terminal verification must be typed")
        if not isinstance(self.evidence, TerminalEvidence):
            raise CohortAssuranceError("terminal evidence must be typed")


@dataclass(frozen=True, slots=True)
class RepairDirective:
    """A single shared instruction for one parallel repair wave."""

    package_ids: tuple[str, ...]
    instruction: str

    def __post_init__(self) -> None:
        if not self.package_ids or len(set(self.package_ids)) != len(self.package_ids):
            raise CohortAssuranceError("repair package ids must be nonempty and unique")
        if not self.instruction.strip():
            raise CohortAssuranceError("consolidated repair instruction is required")


@dataclass(frozen=True, slots=True)
class AssuredCohortResult:
    """Final cohort state after zero or one consolidated repair wave."""

    initial: CohortRunResult
    status: CohortRunStatus
    package_results: tuple[PackageRunResult, ...]
    convergence: ConvergenceResult
    verification: VerificationResult
    evidence: TerminalEvidence | None
    repair_directive: RepairDirective | None

    @property
    def repair_attempted(self) -> bool:
        return self.repair_directive is not None


TerminalAssessor = Callable[
    [CohortKickoff, tuple[PackageRunResult, ...], ConvergenceResult],
    TerminalAssessment,
]
RepairPlanner = Callable[[CohortRunResult], RepairDirective | None]
RepairExecutor = Callable[
    [
        OutcomeWorkPackage,
        CohortKickoff,
        Mapping[str, PackageRunResult],
        RepairDirective,
    ],
    PackageRunResult,
]


def _status(
    results: tuple[PackageRunResult, ...],
    convergence: ConvergenceResult,
    verification: VerificationResult,
) -> CohortRunStatus:
    if (
        any(result.state is PackageRunState.FAILED for result in results)
        or not convergence.accepted
        or not verification.passed
    ):
        return CohortRunStatus.FAILED
    if any(
        result.state
        in {PackageRunState.BLOCKED_DEPENDENCY, PackageRunState.BLOCKED_POLICY}
        for result in results
    ):
        return CohortRunStatus.BLOCKED
    return CohortRunStatus.SUCCEEDED


class CohortAssuranceRuntime:
    """Run a cohort with end-loaded evidence and at most one repair wave."""

    def __init__(
        self,
        policy: CohortExecutionPolicy,
        journal: CohortJournalStore | None = None,
    ) -> None:
        self.policy = policy
        self.journal = journal
        self.runtime = CohortRuntime(policy, journal)

    def execute(
        self,
        *,
        graph: OutcomeGraphSpec,
        run_id: str,
        kickoff_context: Mapping[str, object],
        execute_package: PackageExecutor,
        converge: Callable[
            [CohortKickoff, tuple[PackageRunResult, ...]], ConvergenceResult
        ],
        assess: TerminalAssessor,
        plan_repair: RepairPlanner,
        execute_repair: RepairExecutor,
        effect_classes: Mapping[str, EffectClass] | None = None,
    ) -> AssuredCohortResult:
        """Execute without interleaved review, then repair the cohort once if needed."""

        graph = compile_outcome_graph(graph)
        assessments: list[TerminalAssessment] = []

        def verify(
            kickoff: CohortKickoff,
            results: tuple[PackageRunResult, ...],
            convergence: ConvergenceResult,
        ) -> VerificationResult:
            assessment = assess(kickoff, results, convergence)
            if not isinstance(assessment, TerminalAssessment):
                raise CohortAssuranceError(
                    "terminal assessor returned an untyped result"
                )
            if assessment.evidence.candidate_digest != convergence_candidate_digest(
                convergence
            ):
                raise CohortAssuranceError(
                    "terminal evidence does not bind the converged candidate"
                )
            assessments.append(assessment)
            if self.journal is not None:
                self.journal.append(
                    run_id,
                    CohortJournalEventKind.TERMINAL_EVIDENCE,
                    assessment.evidence.to_document(),
                )
            return assessment.verification

        initial = self.runtime.execute(
            graph=graph,
            run_id=run_id,
            kickoff_context=kickoff_context,
            execute_package=execute_package,
            converge=converge,
            verify=verify,
            effect_classes=effect_classes,
            finalize=False,
        )
        initial_evidence = (
            assessments[-1].evidence if assessments else self._retained_evidence(run_id)
        )
        retained_repair = self._retained_repair(run_id)
        retained_completed = self._retained_completed(run_id)
        if initial.status is CohortRunStatus.SUCCEEDED and initial_evidence is None:
            initial = self._replace_verification(
                initial,
                VerificationResult(False, (), "terminal evidence is missing"),
            )
        if (
            initial.status is CohortRunStatus.SUCCEEDED
            or retained_repair is not None
            or retained_completed
        ):
            self.runtime.record_completion(initial)
            return AssuredCohortResult(
                initial,
                initial.status,
                initial.package_results,
                initial.convergence,
                initial.verification,
                initial_evidence,
                retained_repair,
            )

        directive = plan_repair(initial)
        if directive is None:
            self.runtime.record_completion(initial)
            return AssuredCohortResult(
                initial,
                initial.status,
                initial.package_results,
                initial.convergence,
                initial.verification,
                initial_evidence,
                None,
            )
        self._validate_repair(graph, directive, effect_classes or {})
        if self.journal is not None:
            self.journal.append(
                run_id,
                CohortJournalEventKind.REPAIR_ATTEMPT,
                {
                    "package_ids": list(directive.package_ids),
                    "instruction": directive.instruction,
                },
            )
        by_id = {package.package_id: package for package in graph.packages}
        current = {result.package_id: result for result in initial.package_results}

        def repair(package_id: str) -> PackageRunResult:
            package = by_id[package_id]
            dependencies = {
                dependency: current[dependency] for dependency in package.dependencies
            }
            try:
                result = execute_repair(
                    package, initial.kickoff, dependencies, directive
                )
                if not isinstance(result, PackageRunResult):
                    raise CohortAssuranceError(
                        "repair executor returned an untyped result"
                    )
                if result.package_id != package_id:
                    raise CohortAssuranceError("repair returned a cross-package result")
                return result
            except Exception as error:
                return PackageRunResult(
                    package_id,
                    PackageRunState.FAILED,
                    {},
                    message=f"{type(error).__name__}: {error}",
                )

        # The directive is one shared plan; its non-conflicting targets execute together.
        with ThreadPoolExecutor(
            max_workers=min(
                len(directive.package_ids), self.policy.max_parallel_packages
            ),
            thread_name_prefix=f"repair-{run_id}",
        ) as pool:
            repaired = tuple(pool.map(repair, directive.package_ids))
        current.update((result.package_id, result) for result in repaired)
        final_results = tuple(current[package.package_id] for package in graph.packages)
        if self.journal is not None:
            self.journal.append(
                run_id,
                CohortJournalEventKind.REPAIR_RESULT,
                {
                    "package_results": [
                        self._package_document(result) for result in repaired
                    ]
                },
            )

        try:
            final_convergence = converge(initial.kickoff, final_results)
            if not isinstance(final_convergence, ConvergenceResult):
                raise CohortAssuranceError("converger returned an untyped result")
        except Exception as error:
            final_convergence = ConvergenceResult(
                False, {}, f"{type(error).__name__}: {error}"
            )
        if self.journal is not None:
            self.journal.append(
                run_id,
                CohortJournalEventKind.CONVERGENCE,
                self._convergence_document(final_convergence),
            )
        try:
            final_assessment = assess(initial.kickoff, final_results, final_convergence)
            if not isinstance(final_assessment, TerminalAssessment):
                raise CohortAssuranceError(
                    "terminal assessor returned an untyped result"
                )
            if final_assessment.evidence.candidate_digest != (
                convergence_candidate_digest(final_convergence)
            ):
                raise CohortAssuranceError(
                    "terminal evidence does not bind the converged candidate"
                )
            final_verification = final_assessment.verification
            final_evidence = final_assessment.evidence
            if self.journal is not None:
                self.journal.append(
                    run_id,
                    CohortJournalEventKind.TERMINAL_EVIDENCE,
                    final_evidence.to_document(),
                )
        except Exception as error:
            final_verification = VerificationResult(
                False, (), f"{type(error).__name__}: {error}"
            )
            final_evidence = None
        if self.journal is not None:
            self.journal.append(
                run_id,
                CohortJournalEventKind.VERIFICATION,
                self._verification_document(final_verification),
            )
        final_status = _status(final_results, final_convergence, final_verification)
        final_run = CohortRunResult(
            run_id,
            final_status,
            initial.kickoff,
            final_results,
            final_convergence,
            final_verification,
            initial.dispatch_batches,
            initial.max_parallelism,
        )
        self.runtime.record_completion(final_run)
        return AssuredCohortResult(
            initial,
            final_status,
            final_results,
            final_convergence,
            final_verification,
            final_evidence,
            directive,
        )

    def _events(self, run_id: str):
        return () if self.journal is None else self.journal.events(run_id)

    def _retained_evidence(self, run_id: str) -> TerminalEvidence | None:
        for event in reversed(self._events(run_id)):
            if event.kind is CohortJournalEventKind.TERMINAL_EVIDENCE:
                return TerminalEvidence.from_document(event.payload)
        return None

    def _retained_repair(self, run_id: str) -> RepairDirective | None:
        for event in self._events(run_id):
            if event.kind is CohortJournalEventKind.REPAIR_ATTEMPT:
                package_ids = event.payload.get("package_ids")
                instruction = event.payload.get("instruction")
                if not isinstance(package_ids, tuple) or type(instruction) is not str:
                    raise CohortAssuranceError("retained repair directive is invalid")
                return RepairDirective(package_ids, instruction)
        return None

    def _retained_completed(self, run_id: str) -> bool:
        return any(
            event.kind is CohortJournalEventKind.RUN_COMPLETED
            for event in self._events(run_id)
        )

    @staticmethod
    def _replace_verification(
        result: CohortRunResult, verification: VerificationResult
    ) -> CohortRunResult:
        return CohortRunResult(
            result.run_id,
            _status(result.package_results, result.convergence, verification),
            result.kickoff,
            result.package_results,
            result.convergence,
            verification,
            result.dispatch_batches,
            result.max_parallelism,
        )

    @staticmethod
    def _package_document(result: PackageRunResult) -> dict[str, object]:
        return {
            "package_id": result.package_id,
            "state": result.state.value,
            "output": _plain(result.output),
            "evidence_refs": list(result.evidence_refs),
            "message": result.message,
        }

    @staticmethod
    def _convergence_document(result: ConvergenceResult) -> dict[str, object]:
        return {
            "accepted": result.accepted,
            "output": _plain(result.output),
            "message": result.message,
        }

    @staticmethod
    def _verification_document(result: VerificationResult) -> dict[str, object]:
        return {
            "passed": result.passed,
            "checks": list(result.checks),
            "message": result.message,
        }

    @staticmethod
    def _validate_repair(
        graph: OutcomeGraphSpec,
        directive: RepairDirective,
        effect_classes: Mapping[str, EffectClass],
    ) -> None:
        if not isinstance(directive, RepairDirective):
            raise CohortAssuranceError("repair planner returned an untyped directive")
        known = {package.package_id for package in graph.packages}
        unknown = set(directive.package_ids) - known
        if unknown:
            raise CohortAssuranceError(
                f"repair names unknown packages: {sorted(unknown)}"
            )
        blocked = [
            package_id
            for package_id in directive.package_ids
            if effect_classes.get(package_id, EffectClass.ROUTINE_REVERSIBLE)
            in CohortExecutionPolicy.HARD_GATE_EFFECTS
        ]
        if blocked:
            raise CohortAssuranceError(
                f"repair cannot bypass hard-gated packages: {sorted(blocked)}"
            )
        selected = [
            package
            for package in graph.packages
            if package.package_id in directive.package_ids
        ]
        if any(
            set(package.dependencies).intersection(directive.package_ids)
            for package in selected
        ):
            raise CohortAssuranceError(
                "one repair wave cannot contain dependency-related targets"
            )
        for index, package in enumerate(selected):
            for peer in selected[index + 1 :]:
                if set(package.allowed_paths).intersection(peer.allowed_paths) or set(
                    package.semantic_locks
                ).intersection(peer.semantic_locks):
                    raise CohortAssuranceError(
                        "one repair wave requires conflict-free package targets"
                    )


__all__ = [
    "AssuredCohortResult",
    "CohortAssuranceError",
    "CohortAssuranceRuntime",
    "RepairDirective",
    "TerminalAssessment",
    "TerminalEvidence",
    "convergence_candidate_digest",
]
