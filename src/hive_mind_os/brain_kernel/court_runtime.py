"""Immutable local court coordination for evidence-bound kernel decisions.

This module deliberately schedules no model work and performs no effects.  It
turns already-retained role results and consultation records into a narrow,
auditable courtroom record.  A caller must arrange any model-backed work and
persist the returned records through the kernel event spine.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from .consultation import CheatingDisposition, ConsultationResult
from .contracts import RoleResult


class CourtProtocolError(ValueError):
    """A courtroom input would weaken identity, evidence, or retention rules."""


class CourtSeat(StrEnum):
    ADVOCATE = "advocate"
    CROSS_EXAMINER = "cross_examiner"
    EXPERT_WITNESS = "expert_witness"
    JUDGE = "judge"
    APPEALS_JUDGE = "appeals_judge"


class CourtDisposition(StrEnum):
    ADOPT = "adopt"
    ADAPT = "adapt"
    DEFER = "defer"
    REJECT = "reject"
    QUARANTINE = "quarantine"


class CourtClaimKind(StrEnum):
    ORDINARY = "ordinary"
    CHEATING = "cheating"
    SUPERIORITY = "superiority"


_APPROVING = frozenset({CourtDisposition.ADOPT, CourtDisposition.ADAPT})
_ADVERSE = frozenset({CourtDisposition.REJECT, CourtDisposition.QUARANTINE})


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CourtProtocolError(f"{label} is required")
    return value


def _references(values: Iterable[str], label: str) -> tuple[str, ...]:
    result = tuple(values)
    if not result or any(not isinstance(value, str) or not value.strip() for value in result):
        raise CourtProtocolError(f"{label} require at least one retained reference")
    return tuple(dict.fromkeys(result))


@dataclass(frozen=True, slots=True)
class CourtParticipant:
    """One temporary court seat with an explicit, non-human identity disclosure."""

    seat: CourtSeat
    identity: str
    task: str
    identity_kind: str = "procedural_role"

    def __post_init__(self) -> None:
        object.__setattr__(self, "seat", CourtSeat(self.seat))
        _text(self.identity, "participant identity")
        _text(self.task, "participant task")
        if self.identity_kind not in {"model_role", "procedural_role"}:
            raise CourtProtocolError("court participants cannot claim independent human status")


@dataclass(frozen=True, slots=True)
class CourtBrief:
    """A seat's immutable statement and the evidence it examined."""

    participant: CourtParticipant
    conclusion: str
    evidence_refs: tuple[str, ...]
    role_result_refs: tuple[str, ...] = ()
    consultation_refs: tuple[str, ...] = ()
    dissent: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.participant, CourtParticipant):
            raise CourtProtocolError("brief requires a court participant")
        _text(self.conclusion, "brief conclusion")
        object.__setattr__(self, "evidence_refs", _references(self.evidence_refs, "brief evidence"))
        object.__setattr__(self, "role_result_refs", tuple(dict.fromkeys(self.role_result_refs)))
        object.__setattr__(self, "consultation_refs", tuple(dict.fromkeys(self.consultation_refs)))
        if self.dissent is not None:
            _text(self.dissent, "dissent")


@dataclass(frozen=True, slots=True)
class CourtCase:
    """The bounded case before the temporary court."""

    case_id: str
    claim_kind: CourtClaimKind
    subject: str
    affected_identities: tuple[str, ...]
    role_results: tuple[RoleResult, ...] = ()
    consultations: tuple[ConsultationResult, ...] = ()

    def __post_init__(self) -> None:
        _text(self.case_id, "case id")
        object.__setattr__(self, "claim_kind", CourtClaimKind(self.claim_kind))
        _text(self.subject, "case subject")
        identities = tuple(self.affected_identities)
        if any(not isinstance(identity, str) or not identity.strip() for identity in identities):
            raise CourtProtocolError("affected identities must be non-empty strings")
        object.__setattr__(self, "affected_identities", tuple(dict.fromkeys(identities)))
        if any(not isinstance(result, RoleResult) for result in self.role_results):
            raise CourtProtocolError("role_results must contain RoleResult values")
        if any(not isinstance(result, ConsultationResult) for result in self.consultations):
            raise CourtProtocolError("consultations must contain ConsultationResult values")

    @property
    def source_identities(self) -> tuple[str, ...]:
        """Every identity whose affected output must not judge this case."""

        return tuple(
            dict.fromkeys(
                (*self.affected_identities, *(result.executor_id for result in self.role_results))
            )
        )

    @property
    def evidence_refs(self) -> tuple[str, ...]:
        """References retained by the upstream result and consultation contracts."""

        refs = [
            *(result.result_digest for result in self.role_results),
            *(ref for result in self.consultations for ref in result.evidence_refs),
        ]
        return tuple(dict.fromkeys(refs))


@dataclass(frozen=True, slots=True)
class CourtVerdict:
    case_id: str
    disposition: CourtDisposition
    decided_by: str
    reasons: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    dissent: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.case_id, "verdict case id")
        object.__setattr__(self, "disposition", CourtDisposition(self.disposition))
        _text(self.decided_by, "judge identity")
        object.__setattr__(self, "reasons", _references(self.reasons, "verdict reasons"))
        object.__setattr__(self, "evidence_refs", _references(self.evidence_refs, "verdict evidence"))
        if any(not isinstance(item, str) or not item.strip() for item in self.dissent):
            raise CourtProtocolError("dissent must contain non-empty strings")
        object.__setattr__(self, "dissent", tuple(dict.fromkeys(self.dissent)))


@dataclass(frozen=True, slots=True)
class CourtRecord:
    """One append-only record; rejected and dissenting records remain first-class."""

    case: CourtCase
    briefs: tuple[CourtBrief, ...]
    verdict: CourtVerdict
    appeal_of: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.case, CourtCase) or not isinstance(self.verdict, CourtVerdict):
            raise CourtProtocolError("record requires a case and verdict")
        if self.verdict.case_id != self.case.case_id:
            raise CourtProtocolError("verdict is not bound to the court case")
        if not self.briefs or any(not isinstance(brief, CourtBrief) for brief in self.briefs):
            raise CourtProtocolError("record requires court briefs")
        _validate_panel(self.case, self.briefs, self.verdict)
        if self.appeal_of is not None:
            _text(self.appeal_of, "appeal parent case id")


def _validate_panel(case: CourtCase, briefs: tuple[CourtBrief, ...], verdict: CourtVerdict) -> None:
    participants = tuple(brief.participant for brief in briefs)
    seats = {participant.seat for participant in participants}
    required = {CourtSeat.ADVOCATE, CourtSeat.CROSS_EXAMINER, CourtSeat.EXPERT_WITNESS, CourtSeat.JUDGE}
    if not required.issubset(seats):
        raise CourtProtocolError("court requires advocate, cross-examiner, expert witness, and judge briefs")
    if len(seats) != len(participants):
        raise CourtProtocolError("each court seat may submit only one brief")
    if len({participant.identity for participant in participants}) != len(participants):
        raise CourtProtocolError("each court brief requires a distinct identity")
    by_seat = {participant.seat: participant for participant in participants}
    if by_seat[CourtSeat.ADVOCATE].task == by_seat[CourtSeat.CROSS_EXAMINER].task:
        raise CourtProtocolError("advocate and cross-examiner require distinct tasks")
    deciding_participant = by_seat.get(CourtSeat.APPEALS_JUDGE, by_seat[CourtSeat.JUDGE])
    if deciding_participant.identity != verdict.decided_by:
        raise CourtProtocolError("verdict must be issued by the assigned deciding participant")
    if deciding_participant.identity in case.source_identities:
        raise CourtProtocolError("judge cannot adjudicate an affected generator, builder, or evaluator")
    evidence = set(case.evidence_refs)
    evidence.update(ref for brief in briefs for ref in brief.evidence_refs)
    if verdict.disposition in _APPROVING and case.claim_kind in {CourtClaimKind.CHEATING, CourtClaimKind.SUPERIORITY}:
        if not evidence:
            raise CourtProtocolError("cheating and superiority claims cannot be approved without evidence")
        if not any(brief.participant.seat is CourtSeat.CROSS_EXAMINER for brief in briefs):
            raise CourtProtocolError("approval requires adversarial cross-examination")
    unresolved_cheating = any(
        consultation.cheating_disposition is CheatingDisposition.UNRESOLVED
        for consultation in case.consultations
    )
    if unresolved_cheating and verdict.disposition in _APPROVING:
        raise CourtProtocolError("unresolved cheating cannot receive an approving verdict")


@dataclass(frozen=True, slots=True)
class CourtHistory:
    """Persistent-style append-only case history for one local runtime instance."""

    records: tuple[CourtRecord, ...] = ()

    def append(self, record: CourtRecord) -> "CourtHistory":
        if not isinstance(record, CourtRecord):
            raise TypeError("record must be a CourtRecord")
        if any(existing.case.case_id == record.case.case_id for existing in self.records):
            raise CourtProtocolError("court case ids are append-only and cannot be replaced")
        if record.appeal_of is not None:
            parent = next((item for item in self.records if item.case.case_id == record.appeal_of), None)
            if parent is None:
                raise CourtProtocolError("appeal must retain an existing parent record")
            if parent.verdict.disposition not in _ADVERSE:
                raise CourtProtocolError("appeals are only available after rejected or quarantined verdicts")
            appeals = [brief.participant for brief in record.briefs if brief.participant.seat is CourtSeat.APPEALS_JUDGE]
            if len(appeals) != 1 or record.verdict.decided_by != appeals[0].identity:
                raise CourtProtocolError("appeal verdict requires its assigned appeals judge")
            parent_identities = {brief.participant.identity for brief in parent.briefs}
            if appeals[0].identity in parent_identities:
                raise CourtProtocolError("appeals judge must be distinct from the original court")
            prior_evidence = {
                *parent.case.evidence_refs,
                *parent.verdict.evidence_refs,
                *(ref for brief in parent.briefs for ref in brief.evidence_refs),
            }
            new_evidence = {
                *record.case.evidence_refs,
                *record.verdict.evidence_refs,
                *(ref for brief in record.briefs for ref in brief.evidence_refs),
            } - prior_evidence
            if not new_evidence:
                raise CourtProtocolError("appeal requires materially new retained evidence")
        return CourtHistory((*self.records, record))

    @property
    def dissent(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                item
                for record in self.records
                for item in (*record.verdict.dissent, *(brief.dissent for brief in record.briefs if brief.dissent))
            )
        )


def record_case(
    history: CourtHistory,
    case: CourtCase,
    briefs: Iterable[CourtBrief],
    verdict: CourtVerdict,
    *,
    appeal_of: str | None = None,
) -> CourtHistory:
    """Validate and append a court record without mutating prior dissent or verdicts."""

    return history.append(CourtRecord(case, tuple(briefs), verdict, appeal_of))
