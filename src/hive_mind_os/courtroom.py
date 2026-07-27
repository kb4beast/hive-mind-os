from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import Iterable, Mapping


class SourceStatus(StrEnum):
    VERIFIED = "verified"
    PARTIAL = "partial"
    PENDING_INGESTION = "pending_ingestion"


class EvidenceStance(StrEnum):
    SUPPORTS = "supports"
    OPPOSES = "opposes"
    CONTEXT = "context"


class EvidenceStrength(IntEnum):
    ASSERTION = 1
    DOCUMENTED = 2
    REPRODUCED = 3
    EMPIRICAL = 4


class BurdenOfProof(IntEnum):
    CAPTURE = 0
    DESIGN = 1
    IMPLEMENT = 2
    PROMOTE = 3
    SUPERIORITY = 4


class Disposition(StrEnum):
    ADOPT = "adopt"
    ADAPT = "adapt"
    DEFER = "defer"
    REJECT = "reject"
    QUARANTINE = "quarantine"


class ImplementationState(StrEnum):
    INVENTORIED = "inventoried"
    PLANNED = "planned"
    IMPLEMENTED = "implemented"
    VALIDATED = "validated"


class CapabilityMaturity(StrEnum):
    SPECIFIED = "specified"
    STRUCTURALLY_PROTOTYPED = "structurally_prototyped"
    EXECUTED_IN_ISOLATION = "executed_in_isolation"
    INDEPENDENTLY_VERIFIED_E2E = "independently_verified_e2e"
    PRODUCTION_PROVEN = "production_proven"


class IssueSeverity(StrEnum):
    WARNING = "warning"
    BLOCKING = "blocking"


@dataclass(frozen=True, slots=True)
class SourceRecord:
    id: str
    title: str
    uri: str
    kind: str
    status: SourceStatus
    version_ref: str | None = None
    license_spdx: str | None = None
    content_digest: str | None = None
    provenance_complete: bool = True
    requires_complete_ingestion: bool = True
    object_type: str | None = None
    retrieved_at: str | None = None
    snapshot_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.title.strip() or not self.uri.strip():
            raise ValueError("source id, title, and URI are required")
        if self.status is SourceStatus.VERIFIED and not (self.version_ref or self.content_digest):
            raise ValueError("verified sources require a version reference or content digest")


@dataclass(frozen=True, slots=True)
class IdeaClaim:
    id: str
    case_id: str
    proposition: str
    source_ids: tuple[str, ...]
    category: str
    burden: BurdenOfProof
    architecture_refs: tuple[str, ...] = ()
    acceptance_tests: tuple[str, ...] = ()
    outcome_metrics: tuple[str, ...] = ()
    code_refs: tuple[str, ...] = ()
    test_refs: tuple[str, ...] = ()
    benchmark_refs: tuple[str, ...] = ()
    comparator_source_ids: tuple[str, ...] = ()
    implementation_state: ImplementationState = ImplementationState.INVENTORIED
    capability_maturity: CapabilityMaturity = CapabilityMaturity.SPECIFIED

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.case_id.strip() or not self.proposition.strip():
            raise ValueError("claim id, case id, and proposition are required")
        if not self.source_ids:
            raise ValueError("every claim must identify at least one source")


@dataclass(frozen=True, slots=True)
class Exhibit:
    id: str
    claim_id: str
    source_id: str
    stance: EvidenceStance
    strength: EvidenceStrength
    locator: str
    content_digest: str
    independent: bool = True

    def __post_init__(self) -> None:
        if any(not item.strip() for item in (self.id, self.claim_id, self.source_id, self.locator, self.content_digest)):
            raise ValueError("exhibits require identity, source, locator, and digest")

    @property
    def weight(self) -> float:
        independence = 1.0 if self.independent else 0.65
        return float(self.strength) * independence


@dataclass(frozen=True, slots=True)
class ExpertTestimony:
    id: str
    claim_id: str
    discipline: str
    stance: EvidenceStance
    summary: str
    actor_id: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if any(not item.strip() for item in (self.id, self.claim_id, self.discipline, self.summary, self.actor_id)):
            raise ValueError("testimony requires complete identity and summary")
        if not self.evidence_refs:
            raise ValueError("expert testimony must cite evidence")


@dataclass(frozen=True, slots=True)
class CaseParticipants:
    advocate_id: str
    cross_examiner_id: str
    judge_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        identities = (self.advocate_id, self.cross_examiner_id, *self.judge_ids)
        if any(not identity.strip() for identity in identities):
            raise ValueError("court participants require identities")
        if not self.judge_ids:
            raise ValueError("at least one independent judge is required")
        if len(set(identities)) != len(identities):
            raise ValueError("advocate, cross-examiner, and judges must be independent identities")


@dataclass(frozen=True, slots=True)
class CourtCase:
    claim: IdeaClaim
    participants: CaseParticipants
    exhibits: tuple[Exhibit, ...]
    testimony: tuple[ExpertTestimony, ...]
    unresolved_objections: tuple[str, ...] = ()
    prohibited_findings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if any(exhibit.claim_id != self.claim.id for exhibit in self.exhibits):
            raise ValueError("all exhibits must belong to the case claim")
        if any(item.claim_id != self.claim.id for item in self.testimony):
            raise ValueError("all testimony must belong to the case claim")


@dataclass(frozen=True, slots=True)
class CourtVerdict:
    claim_id: str
    disposition: Disposition
    score: float
    reasons: tuple[str, ...]
    obligations: tuple[str, ...]
    decided_by: tuple[str, ...]


class Courtroom:
    """Adversarial, evidence-bearing decision engine for source ideas and changes."""

    _thresholds: Mapping[BurdenOfProof, float] = {
        BurdenOfProof.CAPTURE: -1.0,
        BurdenOfProof.DESIGN: 0.10,
        BurdenOfProof.IMPLEMENT: 0.25,
        BurdenOfProof.PROMOTE: 0.40,
        BurdenOfProof.SUPERIORITY: 0.55,
    }

    def __init__(self, sources: Iterable[SourceRecord]) -> None:
        self.sources = {source.id: source for source in sources}
        if not self.sources:
            raise ValueError("courtroom requires a source registry")

    def hear(self, case: CourtCase) -> CourtVerdict:
        reasons: list[str] = []
        obligations: list[str] = list(case.unresolved_objections)

        unknown_sources = set(case.claim.source_ids) - set(self.sources)
        if unknown_sources:
            raise KeyError("unknown source(s): " + ", ".join(sorted(unknown_sources)))

        if case.prohibited_findings:
            return CourtVerdict(
                claim_id=case.claim.id,
                disposition=Disposition.QUARANTINE,
                score=-1.0,
                reasons=tuple(case.prohibited_findings),
                obligations=("remove the prohibited behavior and reopen as a new appeal",),
                decided_by=case.participants.judge_ids,
            )

        source_records = [self.sources[source_id] for source_id in case.claim.source_ids]
        incomplete_sources = [
            source.id
            for source in source_records
            if not source.provenance_complete
            or (source.requires_complete_ingestion and source.status is not SourceStatus.VERIFIED)
        ]
        if incomplete_sources and case.claim.burden > BurdenOfProof.CAPTURE:
            reasons.append("source ingestion or provenance is incomplete: " + ", ".join(sorted(incomplete_sources)))

        supporting = [item for item in case.exhibits if item.stance is EvidenceStance.SUPPORTS]
        opposing = [item for item in case.exhibits if item.stance is EvidenceStance.OPPOSES]
        supporting_testimony = [item for item in case.testimony if item.stance is EvidenceStance.SUPPORTS]
        opposing_testimony = [item for item in case.testimony if item.stance is EvidenceStance.OPPOSES]

        if not supporting:
            reasons.append("no supporting exhibit")
        if case.claim.burden >= BurdenOfProof.DESIGN and not (opposing or opposing_testimony):
            reasons.append("no adversarial cross-examination evidence")

        if case.claim.burden >= BurdenOfProof.IMPLEMENT:
            if not case.claim.architecture_refs:
                reasons.append("implementation has no architecture mapping")
            if not case.claim.acceptance_tests:
                reasons.append("implementation has no acceptance tests")
        if case.claim.burden >= BurdenOfProof.PROMOTE:
            if not case.claim.code_refs or not case.claim.test_refs:
                reasons.append("promotion lacks code and test receipts")
            if not case.claim.outcome_metrics:
                reasons.append("promotion lacks outcome metrics")
        if case.claim.burden is BurdenOfProof.SUPERIORITY:
            if len(set(case.claim.comparator_source_ids)) < 2:
                reasons.append("superiority claim lacks at least two independent comparators")
            if not case.claim.benchmark_refs:
                reasons.append("superiority claim lacks reproducible benchmark evidence")

        support_weight = sum(item.weight for item in supporting) + 0.75 * len(supporting_testimony)
        oppose_weight = sum(item.weight for item in opposing) + 0.75 * len(opposing_testimony)
        total = support_weight + oppose_weight
        score = 0.0 if total == 0 else round((support_weight - oppose_weight) / total, 6)

        if reasons:
            return CourtVerdict(
                claim_id=case.claim.id,
                disposition=Disposition.DEFER,
                score=score,
                reasons=tuple(reasons),
                obligations=tuple(dict.fromkeys((*obligations, *reasons))),
                decided_by=case.participants.judge_ids,
            )

        threshold = self._thresholds[case.claim.burden]
        if score < threshold:
            return CourtVerdict(
                claim_id=case.claim.id,
                disposition=Disposition.REJECT,
                score=score,
                reasons=(f"evidence score {score:.3f} did not meet burden threshold {threshold:.3f}",),
                obligations=("reopen only with materially new evidence",),
                decided_by=case.participants.judge_ids,
            )

        disposition = Disposition.ADAPT if obligations else Disposition.ADOPT
        return CourtVerdict(
            claim_id=case.claim.id,
            disposition=disposition,
            score=score,
            reasons=("burden of proof satisfied",),
            obligations=tuple(dict.fromkeys(obligations)),
            decided_by=case.participants.judge_ids,
        )


@dataclass(frozen=True, slots=True)
class DocketDecision:
    claim_id: str
    disposition: Disposition
    rationale: str
    advocate_case: str
    cross_examination: str
    expert_findings: tuple[str, ...]

    def __post_init__(self) -> None:
        required = (self.claim_id, self.rationale, self.advocate_case, self.cross_examination)
        if any(not item.strip() for item in required):
            raise ValueError("docket decisions require a full adversarial record")
        if not self.expert_findings:
            raise ValueError("at least one expert finding is required")


@dataclass(frozen=True, slots=True)
class DocketIssue:
    severity: IssueSeverity
    message: str
    source_id: str | None = None
    claim_id: str | None = None


@dataclass(frozen=True, slots=True)
class DocketAudit:
    issues: tuple[DocketIssue, ...]

    @property
    def inventory_complete(self) -> bool:
        inventory_failures = {
            "source has no captured claim",
            "claim has no courtroom decision",
            "claim references an unknown source",
            "decision references an unknown claim",
        }
        return not any(issue.message in inventory_failures for issue in self.issues)

    @property
    def release_ready(self) -> bool:
        return not any(issue.severity is IssueSeverity.BLOCKING for issue in self.issues)

    @property
    def machine_blocked_claim_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    issue.claim_id
                    for issue in self.issues
                    if issue.claim_id
                    and issue.message
                    == "dependent claim is machine-blocked by incomplete source evidence"
                }
            )
        )


class SourceDocketAuditor:
    """Proves that no source or idea silently disappears from the system."""

    def audit(
        self,
        sources: Iterable[SourceRecord],
        claims: Iterable[IdeaClaim],
        decisions: Iterable[DocketDecision],
    ) -> DocketAudit:
        source_map = {source.id: source for source in sources}
        claim_map = {claim.id: claim for claim in claims}
        decision_map = {decision.claim_id: decision for decision in decisions}
        issues: list[DocketIssue] = []

        claims_by_source: dict[str, list[IdeaClaim]] = {source_id: [] for source_id in source_map}
        for claim in claim_map.values():
            for source_id in claim.source_ids:
                if source_id not in source_map:
                    issues.append(
                        DocketIssue(IssueSeverity.BLOCKING, "claim references an unknown source", source_id, claim.id)
                    )
                    continue
                claims_by_source[source_id].append(claim)

            if claim.id not in decision_map:
                issues.append(DocketIssue(IssueSeverity.BLOCKING, "claim has no courtroom decision", claim_id=claim.id))
                continue

            decision = decision_map[claim.id]
            if decision.disposition in {Disposition.ADOPT, Disposition.ADAPT}:
                if not claim.architecture_refs:
                    issues.append(
                        DocketIssue(IssueSeverity.BLOCKING, "adopted claim lacks architecture mapping", claim_id=claim.id)
                    )
                if not claim.acceptance_tests:
                    issues.append(
                        DocketIssue(IssueSeverity.BLOCKING, "adopted claim lacks acceptance tests", claim_id=claim.id)
                    )

            if claim.implementation_state in {ImplementationState.IMPLEMENTED, ImplementationState.VALIDATED}:
                if not claim.code_refs or not claim.test_refs:
                    issues.append(
                        DocketIssue(IssueSeverity.BLOCKING, "implemented claim lacks code/test receipts", claim_id=claim.id)
                    )

            if claim.burden is BurdenOfProof.SUPERIORITY and decision.disposition in {
                Disposition.ADOPT,
                Disposition.ADAPT,
            }:
                if len(set(claim.comparator_source_ids)) < 2 or not claim.benchmark_refs:
                    issues.append(
                        DocketIssue(
                            IssueSeverity.BLOCKING,
                            "superiority verdict lacks comparator and benchmark receipts",
                            claim_id=claim.id,
                        )
                    )

        for source_id, source in source_map.items():
            if not claims_by_source[source_id]:
                issues.append(
                    DocketIssue(IssueSeverity.BLOCKING, "source has no captured claim", source_id=source_id)
                )
            if not source.provenance_complete:
                issues.append(
                    DocketIssue(IssueSeverity.BLOCKING, "source provenance is incomplete", source_id=source_id)
                )
            if source.requires_complete_ingestion and source.status is not SourceStatus.VERIFIED:
                issues.append(
                    DocketIssue(
                        IssueSeverity.BLOCKING,
                        "source requires complete ingestion before derived ideas may be promoted",
                        source_id=source_id,
                    )
                )
            if source.kind == "repository":
                if source.object_type != "commit":
                    issues.append(
                        DocketIssue(
                            IssueSeverity.BLOCKING,
                            "repository source lacks an exact commit object pin",
                            source_id=source_id,
                        )
                    )
                if (
                    not source.version_ref
                    or len(source.version_ref) != 40
                    or any(character not in "0123456789abcdef" for character in source.version_ref)
                ):
                    issues.append(
                        DocketIssue(
                            IssueSeverity.BLOCKING,
                            "repository source pin is mutable or ambiguous",
                            source_id=source_id,
                        )
                    )
            if source.content_digest is not None and (
                not source.content_digest.startswith("sha256:")
                or len(source.content_digest) != 71
                or any(
                    character not in "0123456789abcdef"
                    for character in source.content_digest.removeprefix("sha256:")
                )
            ):
                issues.append(
                    DocketIssue(
                        IssueSeverity.BLOCKING,
                        "source content digest is not a raw-byte SHA-256 receipt",
                        source_id=source_id,
                    )
                )
            if source.license_spdx is None:
                issues.append(
                    DocketIssue(
                        IssueSeverity.BLOCKING,
                        "source license or reuse grant is unresolved",
                        source_id=source_id,
                    )
                )

        incomplete_source_ids = {
            issue.source_id
            for issue in issues
            if issue.source_id
            and issue.message
            in {
                "source provenance is incomplete",
                "source requires complete ingestion before derived ideas may be promoted",
                "repository source lacks an exact commit object pin",
                "repository source pin is mutable or ambiguous",
                "source content digest is not a raw-byte SHA-256 receipt",
            }
        }
        for claim in claim_map.values():
            blocking_sources = sorted(set(claim.source_ids) & incomplete_source_ids)
            if blocking_sources:
                issues.append(
                    DocketIssue(
                        IssueSeverity.BLOCKING,
                        "dependent claim is machine-blocked by incomplete source evidence",
                        source_id=",".join(blocking_sources),
                        claim_id=claim.id,
                    )
                )

        for decision_id in set(decision_map) - set(claim_map):
            issues.append(
                DocketIssue(IssueSeverity.BLOCKING, "decision references an unknown claim", claim_id=decision_id)
            )

        return DocketAudit(tuple(issues))
