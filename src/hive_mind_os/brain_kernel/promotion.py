"""Court-gated atomic champion promotion and rollback authority.

This module schedules no model work and invents no registry API.  It turns an
independent, already-validated court record into the single kernel authority
that may move a champion pointer, and it records an append-only receipt for
every outcome -- including the outcomes that deliberately move nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterable, Mapping

if TYPE_CHECKING:
    from .evaluation_runtime import ChallengerDescriptor, EvaluationRecordReference, PromptEvaluationSubject

from ..models import Role, utc_now
from ..prompt_registry import PromptRegistry, PromotionCommittedEvidencePending
from ..recursive_improvement import ExperimentVerdict
from .canonical import canonical_digest
from .court_runtime import CourtClaimKind, CourtDisposition, CourtHistory
from .promotion_auth import PromotionAuthorization

__all__ = [
    "PromotionAuthority",
    "PromotionAuthorityError",
    "PromotionCandidate",
    "PromotionDecision",
    "PromotionDecisionLog",
]

_HEX_DIGITS = frozenset("0123456789abcdef")


class PromotionAuthorityError(ValueError):
    """A promotion input would weaken authority separation or pointer safety."""


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PromotionAuthorityError(f"{label} is required")
    return value


def _refs(values: Iterable[str], label: str) -> tuple[str, ...]:
    result = tuple(values)
    if not result or any(
        not isinstance(value, str) or not value.strip() for value in result
    ):
        raise PromotionAuthorityError(f"{label} require at least one retained reference")
    if len(set(result)) != len(result):
        raise PromotionAuthorityError(f"{label} must be unique")
    return result


def _artifact_digest(value: str, label: str) -> str:
    _text(value, label)
    prefix, separator, hex_digits = value.partition(":")
    if (
        prefix != "sha256"
        or separator != ":"
        or len(hex_digits) != 64
        or any(character not in _HEX_DIGITS for character in hex_digits)
    ):
        raise PromotionAuthorityError(
            f"{label} must be a canonical sha256:<64 lowercase hex> digest"
        )
    return value


# The five-verdict vocabulary is owned by ``recursive_improvement``; this module
# only classifies it.  Terminal verdicts close a candidate for good, rollback
# verdicts are the only adverse verdicts that may demote a live champion.
_TERMINAL_VERDICTS = frozenset(
    {
        ExperimentVerdict.KEEP,
        ExperimentVerdict.DISCARD,
        ExperimentVerdict.QUARANTINE,
        ExperimentVerdict.STOP,
    }
)
_ROLLBACK_VERDICTS = frozenset(
    {ExperimentVerdict.DISCARD, ExperimentVerdict.QUARANTINE}
)
_COMPATIBLE_DISPOSITIONS: Mapping[ExperimentVerdict, frozenset[CourtDisposition]] = {
    ExperimentVerdict.KEEP: frozenset(
        {CourtDisposition.ADOPT, CourtDisposition.ADAPT}
    ),
    ExperimentVerdict.RETEST: frozenset({CourtDisposition.DEFER}),
    ExperimentVerdict.DISCARD: frozenset({CourtDisposition.REJECT}),
    ExperimentVerdict.QUARANTINE: frozenset({CourtDisposition.QUARANTINE}),
    ExperimentVerdict.STOP: frozenset(
        {CourtDisposition.DEFER, CourtDisposition.REJECT}
    ),
}


@dataclass(frozen=True, slots=True)
class PromotionCandidate:
    """One challenger bound to the champion it intends to replace."""

    candidate_id: str
    role: str
    experiment_id: str
    artifact_digest: str
    parent_champion_digest: str | None
    proposer_id: str
    builder_id: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.candidate_id, "candidate id")
        try:
            role_value = Role(self.role).value
        except ValueError as error:
            raise PromotionAuthorityError("candidate role is not a kernel role") from error
        object.__setattr__(self, "role", role_value)
        _text(self.experiment_id, "experiment id")
        object.__setattr__(
            self,
            "artifact_digest",
            _artifact_digest(self.artifact_digest, "candidate artifact digest"),
        )
        if self.parent_champion_digest is not None:
            object.__setattr__(
                self,
                "parent_champion_digest",
                _artifact_digest(
                    self.parent_champion_digest, "parent champion digest"
                ),
            )
        _text(self.proposer_id, "proposer id")
        _text(self.builder_id, "builder id")
        if self.artifact_digest == self.parent_champion_digest:
            raise PromotionAuthorityError(
                "a challenger cannot mutate the live champion in place"
            )
        if self.proposer_id == self.builder_id:
            raise PromotionAuthorityError(
                "proposer and builder identities must be distinct"
            )
        object.__setattr__(
            self, "evidence_refs", _refs(self.evidence_refs, "candidate evidence refs")
        )


    def evaluation_subject(self, descriptor: ChallengerDescriptor, *, contract_fingerprint: str) -> PromptEvaluationSubject:
        """Bind prompt bytes explicitly, without redefining the proposal digest."""
        from .evaluation_runtime import PromptEvaluationSubject

        return PromptEvaluationSubject(
            descriptor=descriptor, candidate_id=self.candidate_id, role=self.role,
            experiment_id=self.experiment_id, artifact_digest=self.artifact_digest,
            parent_champion_digest=self.parent_champion_digest, proposer_id=self.proposer_id,
            builder_id=self.builder_id, evidence_refs=self.evidence_refs,
            contract_fingerprint=contract_fingerprint,
        )


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    """A judge's verdict on one candidate, bound to one independent court case."""

    decision_id: str
    court_case_id: str
    candidate: PromotionCandidate
    verdict: ExperimentVerdict
    judge_id: str
    evaluator_id: str
    reasons: tuple[str, ...]
    contract_fingerprint: str
    decided_at: str = ""
    evaluation_subject: PromptEvaluationSubject | None = field(default=None, kw_only=True)
    evaluation_record: EvaluationRecordReference | None = field(default=None, kw_only=True)
    promoter_id: str | None = field(default=None, kw_only=True)
    authorization: PromotionAuthorization | Mapping[str, Any] | None = field(default=None, kw_only=True)

    def __post_init__(self) -> None:
        if self.authorization is not None and not isinstance(self.authorization, PromotionAuthorization):
            object.__setattr__(self, "authorization", PromotionAuthorization.from_document(self.authorization))
        _text(self.decision_id, "decision id")
        _text(self.court_case_id, "court case id")
        if not isinstance(self.candidate, PromotionCandidate):
            raise PromotionAuthorityError("decision requires a promotion candidate")
        try:
            object.__setattr__(self, "verdict", ExperimentVerdict(self.verdict))
        except ValueError as error:
            raise PromotionAuthorityError(
                "decision verdict is not an experiment verdict"
            ) from error
        _text(self.judge_id, "judge id")
        _text(self.evaluator_id, "evaluator id")
        object.__setattr__(self, "reasons", _refs(self.reasons, "decision reasons"))
        _text(self.contract_fingerprint, "contract fingerprint")
        if not isinstance(self.decided_at, str):
            raise PromotionAuthorityError("decision timestamp must be a string")
        if not self.decided_at.strip():
            object.__setattr__(self, "decided_at", utc_now())
        identities = (
            self.candidate.proposer_id,
            self.candidate.builder_id,
            self.evaluator_id,
            self.judge_id,
        )
        if self.promoter_id is not None:
            _text(self.promoter_id, "promoter id")
            if self.promoter_id in identities:
                raise PromotionAuthorityError("promoter must be independent of proposer, builder, evaluator, and judge")
        if len(set(identities)) != 4:
            raise PromotionAuthorityError(
                "promotion requires four distinct proposer, builder, evaluator, "
                "and judge identities"
            )

    @property
    def binding_digest(self) -> str:
        """The candidate binding this decision may never be re-pointed at."""

        return canonical_digest(self.candidate)


@dataclass(frozen=True, slots=True)
class PromotionDecisionLog:
    """Append-only decision history; every append returns a new log."""

    decisions: tuple[PromotionDecision, ...] = ()

    def __post_init__(self) -> None:
        recorded = tuple(self.decisions)
        if any(not isinstance(item, PromotionDecision) for item in recorded):
            raise PromotionAuthorityError(
                "decision log retains PromotionDecision values only"
            )
        object.__setattr__(self, "decisions", recorded)

    def for_candidate(self, candidate_id: str) -> tuple[PromotionDecision, ...]:
        return tuple(
            decision
            for decision in self.decisions
            if decision.candidate.candidate_id == candidate_id
        )

    def append(
        self, decision: PromotionDecision, *, court_history: CourtHistory
    ) -> "PromotionDecisionLog":
        if not isinstance(decision, PromotionDecision):
            raise PromotionAuthorityError("append requires a PromotionDecision")
        if not isinstance(court_history, CourtHistory):
            raise PromotionAuthorityError("append requires a CourtHistory")

        # 1. Append-only: ids are never reused and a court case decides once.
        if any(
            existing.decision_id == decision.decision_id
            for existing in self.decisions
        ):
            raise PromotionAuthorityError(
                "promotion decision ids are append-only and cannot be replaced"
            )
        if any(
            existing.court_case_id == decision.court_case_id
            for existing in self.decisions
        ):
            raise PromotionAuthorityError(
                "one promotion decision per court case is allowed"
            )

        # 2. The court decided independently, before this log ever saw it.
        record = next(
            (
                item
                for item in court_history.records
                if item.case.case_id == decision.court_case_id
            ),
            None,
        )
        if record is None:
            raise PromotionAuthorityError(
                "promotion requires an independent court record for its case id"
            )

        # 3. Candidate binding: the court judged this exact artifact.
        if record.case.subject != decision.candidate.artifact_digest:
            raise PromotionAuthorityError(
                "court record is not bound to the candidate artifact digest"
            )

        # 4. Identity binding: the court's judge decided, and the interested
        #    lanes were declared affected so ``_validate_panel`` already refused
        #    to seat any of them as the judge.
        if record.verdict.decided_by != decision.judge_id:
            raise PromotionAuthorityError(
                "promotion judge must be the court verdict's deciding identity"
            )
        interested = {
            decision.candidate.proposer_id,
            decision.candidate.builder_id,
            decision.evaluator_id,
        }
        if not interested.issubset(set(record.case.affected_identities)):
            raise PromotionAuthorityError(
                "proposer, builder, and evaluator must be declared affected "
                "identities of the court case"
            )

        # 5. Verdict and disposition must agree.
        compatible = _COMPATIBLE_DISPOSITIONS.get(decision.verdict)
        if compatible is None:
            raise PromotionAuthorityError("promotion verdict has no court mapping")
        if record.verdict.disposition not in compatible:
            raise PromotionAuthorityError(
                "court disposition does not authorize this promotion verdict"
            )

        # 6. Champion-beating claims carry the superiority burden.
        if (
            decision.verdict is ExperimentVerdict.KEEP
            and record.case.claim_kind is not CourtClaimKind.SUPERIORITY
        ):
            raise PromotionAuthorityError(
                "a KEEP verdict requires a superiority claim before the court"
            )

        # 7. Terminal verdicts close a candidate; only RETEST may be followed.
        if any(
            prior.verdict in _TERMINAL_VERDICTS
            for prior in self.for_candidate(decision.candidate.candidate_id)
        ):
            raise PromotionAuthorityError(
                "a terminal verdict for this candidate is append-only"
            )

        return PromotionDecisionLog((*self.decisions, decision))


class PromotionAuthority:
    """The only surface allowed to move a champion pointer."""

    def __init__(self, registry: PromptRegistry) -> None:
        if not isinstance(registry, PromptRegistry):
            raise PromotionAuthorityError("promotion authority requires a PromptRegistry")
        self.registry = registry
        self._log = PromotionDecisionLog()
        self._applied: frozenset[str] = frozenset()
        self._receipts: tuple[dict[str, Any], ...] = ()

    @property
    def log(self) -> PromotionDecisionLog:
        return self._log

    @property
    def receipts(self) -> tuple[dict[str, Any], ...]:
        return self._receipts

    def submit(
        self, decision: PromotionDecision, *, court_history: CourtHistory
    ) -> PromotionDecision:
        """Record a court-backed decision.  This never moves a pointer."""

        try:
            self._log = self._log.append(decision, court_history=court_history)
        except PromotionAuthorityError as error:
            self._record_receipt(decision, action="submit", status="rejected", prior_digest=None,
                                 reasons=(str(error),), pointer_after=None)
            raise
        return decision

    def _actionable(self, decision_id: str) -> PromotionDecision:
        _text(decision_id, "decision id")
        decision = next(
            (item for item in self._log.decisions if item.decision_id == decision_id),
            None,
        )
        if decision is None or decision_id in self._applied:
            raise PromotionAuthorityError(
                "only a logged, unapplied decision can act on the champion pointer"
            )
        return decision

    def apply(self, decision_id: str) -> dict[str, Any]:
        return self._run_with_refusal_receipt(decision_id, "apply")

    def _run_with_refusal_receipt(self, decision_id: str, operation: str) -> dict[str, Any]:
        prior_count = len(self._receipts)
        try:
            return self._apply(decision_id) if operation == "apply" else self._rollback(decision_id)
        except PromotionAuthorityError as error:
            if len(self._receipts) == prior_count:
                decision = next((item for item in self._log.decisions if item.decision_id == decision_id), None)
                if decision is not None:
                    self._record_receipt(decision, action=operation, status="rejected", prior_digest=None,
                                         reasons=(str(error),), pointer_after=None)
                else:
                    receipt: dict[str, Any] = {
                        "schema_version": 1, "kind": "promotion.receipt", "decision_id": decision_id,
                        "status": "rejected", "action": operation, "candidate_binding": None,
                        "code": "decision-unavailable", "reasons": [str(error)], "recorded_at": utc_now(),
                    }
                    if self.registry.principal_verifier is not None:
                        receipt["authentication"] = self.registry.principal_verifier.sign_rejection(receipt)
                    self.registry.ledger.append_event("promotion:unbound", "promotion.receipt", "promotion-authority", receipt)
                    self._receipts = (*self._receipts, receipt)
            raise

    def _apply(self, decision_id: str) -> dict[str, Any]:
        """Carry out a logged decision.  Only KEEP may move the pointer."""

        decision = self._actionable(decision_id)
        candidate = decision.candidate
        current = self.registry.champion_digest(candidate.role)
        if candidate.artifact_digest == current:
            raise PromotionAuthorityError(
                "decisions against the active champion must go through rollback()"
            )

        if decision.verdict is not ExperimentVerdict.KEEP:
            if decision.verdict is ExperimentVerdict.QUARANTINE:
                self.registry.quarantine(
                    candidate.role,
                    candidate.artifact_digest,
                    actor=decision.judge_id,
                    experiment_id=candidate.experiment_id,
                    reasons=decision.reasons,
                )
                action = "quarantine-candidate"
            else:
                action = "retain-champion"
            self._applied |= {decision_id}
            return self._record_receipt(
                decision,
                action=action,
                status="applied",
                prior_digest=current,
                reasons=decision.reasons,
                pointer_after=self.registry.champion_digest(candidate.role),
            )

        payload = self.decision_payload(decision)
        sequence = self.registry.ledger.append_event(
            candidate.experiment_id, "experiment.decision", decision.judge_id, payload,
        )
        try:
            prior = self.registry.promote(
                candidate.role, candidate.artifact_digest,
                promoted_by=decision.promoter_id or decision.judge_id,
                experiment_id=candidate.experiment_id,
                expected_current=candidate.parent_champion_digest,
                decision_event_sequence=sequence,
            )
        except PromotionCommittedEvidencePending as error:
            self._applied |= {decision_id}
            return self._record_receipt(
                decision, action="promote", status="committed-evidence-pending",
                prior_digest=error.prior_digest, reasons=(str(error),),
                pointer_after=error.pointer_after,
            )
        except (RuntimeError, OSError, ValueError) as error:
            self._record_receipt(
                decision, action="promote",
                status="commit-state-unknown" if getattr(error, "code", "") == "commit-state-unknown" else "failed",
                prior_digest=current, reasons=(str(error),),
                pointer_after=None if getattr(error, "code", "") == "commit-state-unknown" else current,
            )
            raise PromotionAuthorityError("atomic promotion was refused: " + str(error)) from error
        self._applied |= {decision_id}
        return self._record_receipt(
            decision, action="promote", status="applied", prior_digest=prior,
            reasons=decision.reasons, pointer_after=candidate.artifact_digest,
        )

    @staticmethod
    def decision_payload(decision: PromotionDecision, *, include_authorization: bool = True) -> dict[str, Any]:
        """The exact signed judgment/promotion preimage; authorization is excluded when signing."""
        candidate = decision.candidate
        payload: dict[str, Any] = {
            "verdict": decision.verdict.value,
            "role": candidate.role,
            "candidate_digest": candidate.artifact_digest,
            "current_digest": candidate.parent_champion_digest,
            "registration_experiment_id": candidate.experiment_id,
            "registration_role": candidate.role,
            "registration_author": candidate.proposer_id,
            "registration_parent_digest": candidate.parent_champion_digest,
            "proposer_id": candidate.proposer_id,
            "builder_id": candidate.builder_id,
            "evaluator_id": decision.evaluator_id,
            "judge_id": decision.judge_id,
            "retained_artifact_refs": list(candidate.evidence_refs),
            "contract_fingerprint": decision.contract_fingerprint,
            "decision_id": decision.decision_id,
            "court_case_id": decision.court_case_id,
            "reasons": list(decision.reasons),
            "decided_at": decision.decided_at,
            "decision_binding_digest": decision.binding_digest,
        }
        payload.update({
            "candidate_id": candidate.candidate_id,
            "promoter_id": decision.promoter_id,
            "evaluation_subject": decision.evaluation_subject.document() if decision.evaluation_subject else None,
            "evaluation_subject_digest": decision.evaluation_subject.subject_digest if decision.evaluation_subject else None,
            "evaluation_record": decision.evaluation_record.document() if decision.evaluation_record else None,
        })
        if include_authorization:
            payload["authorization"] = (
                decision.authorization.document() if isinstance(decision.authorization, PromotionAuthorization) else None
            )
        return payload

    @staticmethod
    def authorization_digest(decision: PromotionDecision) -> str:
        return canonical_digest(PromotionAuthority.decision_payload(decision, include_authorization=False))

    def rollback(self, decision_id: str) -> dict[str, Any]:
        return self._run_with_refusal_receipt(decision_id, "rollback")

    def _rollback(self, decision_id: str) -> dict[str, Any]:
        """Restore the retained prior champion under an adverse verdict."""

        decision = self._actionable(decision_id)
        candidate = decision.candidate
        if decision.verdict not in _ROLLBACK_VERDICTS:
            raise PromotionAuthorityError(
                "only a discard or quarantine verdict authorizes a rollback"
            )
        restored = candidate.parent_champion_digest
        if restored is None:
            raise PromotionAuthorityError(
                "rollback requires a retained prior champion digest"
            )
        current = self.registry.champion_digest(candidate.role)
        if current != candidate.artifact_digest:
            raise PromotionAuthorityError(
                "rollback requires the candidate to be the active champion"
            )
        try:
            prior = self.registry.rollback_champion(
                candidate.role,
                restored,
                actor=decision.judge_id,
                reason="; ".join(decision.reasons),
            )
        except RuntimeError as error:
            self._record_receipt(
                decision,
                action="rollback",
                status="failed",
                prior_digest=current,
                restored_digest=restored,
                reasons=(str(error),),
                pointer_after=self.registry.champion_digest(candidate.role),
            )
            raise PromotionAuthorityError(
                "atomic rollback was refused: " + str(error)
            ) from error

        # Quarantine strictly AFTER the pointer is restored: the champion must
        # never be simultaneously active and quarantined.
        if decision.verdict is ExperimentVerdict.QUARANTINE:
            self.registry.quarantine(
                candidate.role,
                candidate.artifact_digest,
                actor=decision.judge_id,
                experiment_id=candidate.experiment_id,
                reasons=decision.reasons,
            )
        self._applied |= {decision_id}
        return self._record_receipt(
            decision,
            action="rollback",
            status="applied",
            prior_digest=prior,
            restored_digest=restored,
            reasons=decision.reasons,
            pointer_after=self.registry.champion_digest(candidate.role),
        )

    def _record_receipt(
        self,
        decision: PromotionDecision,
        *,
        action: str,
        status: str,
        prior_digest: str | None,
        restored_digest: str | None = None,
        reasons: Iterable[str] = (),
        pointer_after: str | None = None,
    ) -> dict[str, Any]:
        candidate = decision.candidate
        receipt: dict[str, Any] = {
            "schema_version": 1,
            "kind": "promotion.receipt",
            "decision_id": decision.decision_id,
            "court_case_id": decision.court_case_id,
            "verdict": decision.verdict.value,
            "role": candidate.role,
            "candidate_digest": candidate.artifact_digest,
            "candidate_id": candidate.candidate_id,
            "parent_champion_digest": candidate.parent_champion_digest,
            "binding_digest": decision.binding_digest,
            "action": action,
            "status": status,
            "prior_digest": prior_digest,
            "restored_digest": restored_digest,
            "pointer_after": pointer_after,
            "reasons": list(reasons),
            "recorded_at": utc_now(),
        }
        if decision.evaluation_subject is not None or decision.evaluation_record is not None:
            receipt.update({
                "evaluation_subject": decision.evaluation_subject.document() if decision.evaluation_subject else None,
                "evaluation_subject_digest": decision.evaluation_subject.subject_digest if decision.evaluation_subject else None,
                "evaluation_record": decision.evaluation_record.document() if decision.evaluation_record else None,
                "promoter_id": decision.promoter_id,
                "decision_payload": self.decision_payload(decision),
            })
        receipt["receipt_digest"] = canonical_digest(receipt)
        if self.registry.principal_verifier is not None and status in {"failed", "rejected", "commit-state-unknown"}:
            receipt["authentication"] = self.registry.principal_verifier.sign_rejection(receipt)
        self.registry.ledger.append_event(
            candidate.experiment_id,
            "promotion.receipt",
            decision.judge_id,
            receipt,
        )
        self._receipts = (*self._receipts, receipt)
        return receipt
