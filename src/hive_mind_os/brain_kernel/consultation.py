"""Role-first consultation and anti-cheating adjudication.

This module is deliberately deterministic.  Role outputs are evidence-bound
proposals; they never grant credentials, consent, legal approval, production
access, or any other authority.  A consultation record is the append-only
boundary consumed by later mission and courtroom runtimes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable, Mapping

from ..contracts import ContractValidation, ROLE_NAMES
from .canonical import canonical_document

MAX_CONSULTATION_ROUNDS = 3
MIN_CONSULTED_ROLES = 2

AUTHORITY_CLASSES = frozenset(
    {
        "credential_or_secret",
        "legal_or_regulatory",
        "financial_spend",
        "production_access",
        "protected_branch_merge",
        "owner_value_choice",
        "personal_consent",
        "external_contractual_commitment",
    }
)


class ConsultationReason(StrEnum):
    AMBIGUOUS_DESIGN = "AMBIGUOUS_DESIGN"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    MISSING_EXTERNAL_AUTHORITY = "MISSING_EXTERNAL_AUTHORITY"
    UNSAFE_EFFECT = "UNSAFE_EFFECT"
    INDEPENDENCE_CONCERN = "INDEPENDENCE_CONCERN"
    SUSPECTED_CHEATING = "SUSPECTED_CHEATING"
    NO_PROGRESS = "NO_PROGRESS"


class ConsultationDecision(StrEnum):
    RESOLVED = "RESOLVED"
    REMAND = "REMAND"
    REPLAN = "REPLAN"
    BLOCKED_EVIDENCE = "BLOCKED_EVIDENCE"
    TRUE_AUTHORITY_REQUIRED = "TRUE_AUTHORITY_REQUIRED"
    QUARANTINE = "QUARANTINE"


class CheatingDisposition(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CONFIRMED = "CONFIRMED"
    DISPROVED = "DISPROVED"
    UNRESOLVED = "UNRESOLVED"


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value


def _role(value: str, label: str = "role") -> str:
    value = _text(value, label)
    if value not in ROLE_NAMES:
        raise ValueError(f"{label} is not a registered role")
    return value


def _strings(values: Iterable[str], label: str) -> tuple[str, ...]:
    result = tuple(values)
    if any(not isinstance(value, str) or not value.strip() for value in result):
        raise ValueError(f"{label} must contain non-empty strings")
    return result


@dataclass(frozen=True, slots=True)
class ConsultationRequest:
    """A typed question that must be routed to roles before escalation."""

    request_id: str
    mission_id: str
    question: str
    reason_code: ConsultationReason
    requesting_role: str
    applicable_roles: tuple[str, ...]
    round: int = 1
    suspected_cheating: bool = False
    evidence_refs: tuple[str, ...] = ()
    authority_class: str | None = None

    def __post_init__(self) -> None:
        _text(self.request_id, "request_id")
        _text(self.mission_id, "mission_id")
        _text(self.question, "question")
        object.__setattr__(self, "reason_code", ConsultationReason(self.reason_code))
        object.__setattr__(self, "requesting_role", _role(self.requesting_role, "requesting_role"))
        roles = tuple(_role(role, "applicable role") for role in self.applicable_roles)
        if len(set(roles)) != len(roles):
            raise ValueError("applicable_roles must be unique")
        if len(roles) < MIN_CONSULTED_ROLES:
            raise ValueError("at least two applicable roles are required")
        if self.requesting_role in roles:
            raise ValueError("requesting role cannot approve its own consultation")
        object.__setattr__(self, "applicable_roles", roles)
        if type(self.round) is not int or not 1 <= self.round <= MAX_CONSULTATION_ROUNDS:
            raise ValueError(f"round must be between 1 and {MAX_CONSULTATION_ROUNDS}")
        if type(self.suspected_cheating) is not bool:
            raise ValueError("suspected_cheating must be boolean")
        object.__setattr__(self, "evidence_refs", _strings(self.evidence_refs, "evidence_refs"))
        if self.authority_class is not None:
            _text(self.authority_class, "authority_class")
            if self.authority_class not in AUTHORITY_CLASSES:
                raise ValueError("authority_class is not a genuine human authority class")


@dataclass(frozen=True, slots=True)
class RoleAssessment:
    """A role's bounded, evidence-bound consultation testimony."""

    role: str
    identity: str
    answer: str | None = None
    evidence_refs: tuple[str, ...] = ()
    proposed_decision: ConsultationDecision = ConsultationDecision.RESOLVED
    dissent: str | None = None
    cheating_disposition: CheatingDisposition = CheatingDisposition.NOT_APPLICABLE
    authority_required: bool = False
    identity_kind: str = "model_role"

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", _role(self.role))
        _text(self.identity, "identity")
        if self.identity_kind not in {"model_role", "procedural_role"}:
            raise ValueError("role identities cannot claim to be independent humans")
        if self.answer is not None:
            _text(self.answer, "answer")
        object.__setattr__(self, "evidence_refs", _strings(self.evidence_refs, "evidence_refs"))
        object.__setattr__(self, "proposed_decision", ConsultationDecision(self.proposed_decision))
        object.__setattr__(self, "cheating_disposition", CheatingDisposition(self.cheating_disposition))
        if type(self.authority_required) is not bool:
            raise ValueError("authority_required must be boolean")
        if self.dissent is not None:
            _text(self.dissent, "dissent")


@dataclass(frozen=True, slots=True)
class ConsultationResult:
    """The schema-compatible retained result of one consultation round."""

    request_id: str
    mission_id: str
    question: str
    reason_code: ConsultationReason
    requesting_role: str
    consulted_roles: tuple[str, ...]
    round: int
    suspected_cheating: bool
    evidence_refs: tuple[str, ...]
    decision: ConsultationDecision
    answer: str | None
    dissent: tuple[str, ...]
    human_escalation: bool
    authority_class: str | None
    role_first_exhausted: bool
    cheating_disposition: CheatingDisposition
    identity_records: tuple[Mapping[str, str], ...]

    def __post_init__(self) -> None:
        _text(self.request_id, "request_id")
        _text(self.mission_id, "mission_id")
        _text(self.question, "question")
        object.__setattr__(self, "reason_code", ConsultationReason(self.reason_code))
        object.__setattr__(self, "requesting_role", _role(self.requesting_role, "requesting_role"))
        roles = tuple(_role(role, "consulted role") for role in self.consulted_roles)
        if len(set(roles)) < MIN_CONSULTED_ROLES:
            raise ValueError("at least two distinct roles must be consulted")
        object.__setattr__(self, "consulted_roles", roles)
        if type(self.round) is not int or not 1 <= self.round <= MAX_CONSULTATION_ROUNDS:
            raise ValueError("round is outside the bounded consultation range")
        if type(self.suspected_cheating) is not bool:
            raise ValueError("suspected_cheating must be boolean")
        object.__setattr__(self, "evidence_refs", _strings(self.evidence_refs, "evidence_refs"))
        object.__setattr__(self, "decision", ConsultationDecision(self.decision))
        if self.answer is not None:
            _text(self.answer, "answer")
        object.__setattr__(self, "dissent", _strings(self.dissent, "dissent"))
        if type(self.human_escalation) is not bool:
            raise ValueError("human_escalation must be boolean")
        if self.authority_class is not None:
            if self.authority_class not in AUTHORITY_CLASSES:
                raise ValueError("authority_class is not a genuine human authority class")
        if self.human_escalation != (self.decision is ConsultationDecision.TRUE_AUTHORITY_REQUIRED):
            raise ValueError("human escalation is reserved for genuine authority need")
        if type(self.role_first_exhausted) is not bool or not self.role_first_exhausted:
            raise ValueError("role-first consultation must be exhausted before a result")
        object.__setattr__(self, "cheating_disposition", CheatingDisposition(self.cheating_disposition))
        records = tuple(dict(record) for record in self.identity_records)
        if len(records) < MIN_CONSULTED_ROLES:
            raise ValueError("identity records are required for every consulted role")
        for record in records:
            if set(record) != {"identity", "identity_kind", "role"}:
                raise ValueError("identity records have an invalid shape")
            _text(record["identity"], "identity")
            _role(record["role"], "identity role")
            if record["identity_kind"] not in {"model_role", "procedural_role"}:
                raise ValueError("identity records cannot claim independent human status")
        object.__setattr__(self, "identity_records", records)
        if self.decision is ConsultationDecision.QUARANTINE and not (
            self.suspected_cheating
            or self.reason_code
            in {
                ConsultationReason.SUSPECTED_CHEATING,
                ConsultationReason.NO_PROGRESS,
                ConsultationReason.UNSAFE_EFFECT,
            }
        ):
            raise ValueError("quarantine requires a typed safety or progress concern")
        if self.cheating_disposition is CheatingDisposition.CONFIRMED and self.decision is not ConsultationDecision.QUARANTINE:
            raise ValueError("confirmed cheating must quarantine")
        if self.cheating_disposition is CheatingDisposition.UNRESOLVED and self.decision is not ConsultationDecision.QUARANTINE:
            raise ValueError("unresolved cheating cannot become ordinary success")
        if self.decision is ConsultationDecision.TRUE_AUTHORITY_REQUIRED:
            if self.authority_class is None or self.authority_class not in AUTHORITY_CLASSES:
                raise ValueError("genuine authority class is required for escalation")
            if not self.evidence_refs:
                raise ValueError("authority escalation requires retained evidence")
        elif self.authority_class is not None:
            raise ValueError("authority class is only valid for genuine authority escalation")

    def to_document(self) -> dict[str, Any]:
        return canonical_document(self)

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "ConsultationResult":
        validation = validate_consultation_document(document)
        if not validation.valid:
            raise ValueError("invalid consultation: " + "; ".join(validation.issues))
        values = dict(document)
        values["reason_code"] = ConsultationReason(values["reason_code"])
        values["decision"] = ConsultationDecision(values["decision"])
        values["cheating_disposition"] = CheatingDisposition(values["cheating_disposition"])
        for field in ("consulted_roles", "evidence_refs", "dissent"):
            values[field] = tuple(values[field])
        values["identity_records"] = tuple(dict(item) for item in values["identity_records"])
        return cls(**values)


def _result_issues(document: Mapping[str, Any]) -> list[str]:
    required = {
        "request_id", "mission_id", "question", "reason_code", "requesting_role",
        "consulted_roles", "round", "suspected_cheating", "evidence_refs", "decision",
        "answer", "dissent", "human_escalation", "authority_class", "role_first_exhausted",
        "cheating_disposition", "identity_records",
    }
    issues: list[str] = []
    if set(document) != required:
        missing = sorted(required - set(document))
        unknown = sorted(set(document) - required)
        if missing:
            issues.append("missing properties: " + ", ".join(missing))
        if unknown:
            issues.append("unknown properties: " + ", ".join(unknown))
    enum_checks = {
        "reason_code": {item.value for item in ConsultationReason},
        "requesting_role": set(ROLE_NAMES),
        "decision": {item.value for item in ConsultationDecision},
        "cheating_disposition": {item.value for item in CheatingDisposition},
    }
    for field, values in enum_checks.items():
        if document.get(field) not in values:
            issues.append(f"{field} has an invalid value")
    if not isinstance(document.get("consulted_roles"), list) or len(set(document.get("consulted_roles", ()))) < 2:
        issues.append("consulted_roles must contain at least two unique roles")
    if type(document.get("round")) is not int or not 1 <= document.get("round", 0) <= MAX_CONSULTATION_ROUNDS:
        issues.append("round is outside the bounded consultation range")
    for field in ("suspected_cheating", "human_escalation", "role_first_exhausted"):
        if type(document.get(field)) is not bool:
            issues.append(f"{field} must be boolean")
    if document.get("role_first_exhausted") is not True:
        issues.append("role_first_exhausted must be true")
    if not isinstance(document.get("identity_records"), list):
        issues.append("identity_records must be a list")
    return issues


def validate_consultation_document(document: Any) -> ContractValidation:
    """Validate the fail-closed consultation v1 document without side effects."""

    if not isinstance(document, Mapping):
        return ContractValidation(False, ("consultation must be an object",))
    issues = _result_issues(document)
    if issues:
        return ContractValidation(False, tuple(dict.fromkeys(issues)))
    try:
        ConsultationResult.from_document.__func__  # keep type checkers aware of the class
        # Validation below is intentionally delegated to the same immutable constructor.
        values = dict(document)
        values["reason_code"] = ConsultationReason(values["reason_code"])
        values["decision"] = ConsultationDecision(values["decision"])
        values["cheating_disposition"] = CheatingDisposition(values["cheating_disposition"])
        values["consulted_roles"] = tuple(values["consulted_roles"])
        values["evidence_refs"] = tuple(values["evidence_refs"])
        values["dissent"] = tuple(values["dissent"])
        values["identity_records"] = tuple(dict(item) for item in values["identity_records"])
        ConsultationResult(**values)
    except (TypeError, ValueError, KeyError) as error:
        issues.append(str(error))
    return ContractValidation(not issues, tuple(dict.fromkeys(issues)))


def _dissent_for(assessments: tuple[RoleAssessment, ...]) -> tuple[str, ...]:
    dissent = [item.dissent for item in assessments if item.dissent]
    decisions = {item.proposed_decision for item in assessments}
    if len(decisions) > 1:
        dissent.append(
            "Role recommendations diverged: "
            + ", ".join(sorted(item.value for item in decisions))
        )
    return tuple(dict.fromkeys(item for item in dissent if item))


def evaluate_consultation(
    request: ConsultationRequest,
    assessments: Iterable[RoleAssessment],
) -> ConsultationResult:
    """Adjudicate one bounded round after at least two applicable roles testify."""

    if not isinstance(request, ConsultationRequest):
        raise TypeError("request must be a ConsultationRequest")
    received = tuple(assessments)
    if len(received) < MIN_CONSULTED_ROLES:
        raise ValueError("human escalation is forbidden before two roles evaluate the question")
    if any(not isinstance(item, RoleAssessment) for item in received):
        raise TypeError("assessments must be RoleAssessment instances")
    roles = tuple(item.role for item in received)
    if len(set(roles)) != len(roles):
        raise ValueError("each applicable role may testify only once per round")
    if not set(roles).issubset(set(request.applicable_roles)):
        raise ValueError("assessment came from a role outside the applicable route")
    if len(set(roles)) < MIN_CONSULTED_ROLES:
        raise ValueError("at least two distinct applicable roles must evaluate the question")

    evidence = tuple(dict.fromkeys((*request.evidence_refs, *(ref for item in received for ref in item.evidence_refs))))
    dissent = _dissent_for(received)
    cheating = CheatingDisposition.NOT_APPLICABLE
    decision = ConsultationDecision.RESOLVED
    answer: str | None = next((item.answer for item in received if item.answer), None)

    cheating_votes = {item.cheating_disposition for item in received if item.cheating_disposition is not CheatingDisposition.NOT_APPLICABLE}
    if request.suspected_cheating or request.reason_code is ConsultationReason.SUSPECTED_CHEATING:
        if CheatingDisposition.CONFIRMED in cheating_votes:
            cheating = CheatingDisposition.CONFIRMED
            decision = ConsultationDecision.QUARANTINE
            answer = None
        elif CheatingDisposition.UNRESOLVED in cheating_votes or not cheating_votes:
            cheating = CheatingDisposition.UNRESOLVED
            decision = ConsultationDecision.QUARANTINE
            answer = None
        elif cheating_votes == {CheatingDisposition.DISPROVED} and evidence:
            cheating = CheatingDisposition.DISPROVED
        else:
            cheating = CheatingDisposition.UNRESOLVED
            decision = ConsultationDecision.QUARANTINE
            answer = None
    elif any(item.authority_required for item in received) or request.authority_class is not None or request.reason_code is ConsultationReason.MISSING_EXTERNAL_AUTHORITY:
        if request.authority_class not in AUTHORITY_CLASSES or not evidence:
            decision = ConsultationDecision.BLOCKED_EVIDENCE
            answer = None
        else:
            decision = ConsultationDecision.TRUE_AUTHORITY_REQUIRED
            answer = None
    elif request.reason_code is ConsultationReason.NO_PROGRESS and request.round >= MAX_CONSULTATION_ROUNDS:
        decision = ConsultationDecision.QUARANTINE
        answer = None
    elif request.reason_code is ConsultationReason.MISSING_EVIDENCE and not evidence:
        decision = ConsultationDecision.BLOCKED_EVIDENCE
        answer = None
    elif any(item.proposed_decision is ConsultationDecision.REPLAN for item in received):
        decision = ConsultationDecision.REPLAN
    elif any(item.proposed_decision is ConsultationDecision.REMAND for item in received):
        decision = ConsultationDecision.REMAND

    if decision is ConsultationDecision.QUARANTINE and not (request.suspected_cheating or request.reason_code in {ConsultationReason.SUSPECTED_CHEATING, ConsultationReason.NO_PROGRESS}):
        raise ValueError("quarantine requires a typed safety concern")
    if cheating is CheatingDisposition.NOT_APPLICABLE and request.suspected_cheating:
        raise AssertionError("suspected cheating must receive an adjudication")
    identities = tuple(
        {"identity": item.identity, "identity_kind": item.identity_kind, "role": item.role}
        for item in received
    )
    return ConsultationResult(
        request_id=request.request_id,
        mission_id=request.mission_id,
        question=request.question,
        reason_code=request.reason_code,
        requesting_role=request.requesting_role,
        consulted_roles=roles,
        round=request.round,
        suspected_cheating=request.suspected_cheating,
        evidence_refs=evidence,
        decision=decision,
        answer=answer,
        dissent=dissent,
        human_escalation=decision is ConsultationDecision.TRUE_AUTHORITY_REQUIRED,
        authority_class=request.authority_class if decision is ConsultationDecision.TRUE_AUTHORITY_REQUIRED else None,
        role_first_exhausted=True,
        cheating_disposition=cheating,
        identity_records=identities,
    )


@dataclass(frozen=True, slots=True)
class ConsultationLoop:
    """Immutable bounded history; each round returns a new loop."""

    history: tuple[ConsultationResult, ...] = ()
    max_rounds: int = MAX_CONSULTATION_ROUNDS

    def __post_init__(self) -> None:
        if type(self.max_rounds) is not int or not 1 <= self.max_rounds <= MAX_CONSULTATION_ROUNDS:
            raise ValueError(f"max_rounds must be between 1 and {MAX_CONSULTATION_ROUNDS}")
        if len(self.history) > self.max_rounds:
            raise ValueError("consultation history exceeds the bounded loop")

    def append(self, request: ConsultationRequest, assessments: Iterable[RoleAssessment]) -> tuple["ConsultationLoop", ConsultationResult]:
        if len(self.history) >= self.max_rounds:
            raise ValueError("consultation loop is exhausted; preserve history and stop")
        if request.round != len(self.history) + 1:
            raise ValueError("consultation rounds must be contiguous and append-only")
        result = evaluate_consultation(request, assessments)
        return ConsultationLoop((*self.history, result), self.max_rounds), result

    @property
    def exhausted(self) -> bool:
        return len(self.history) >= self.max_rounds


# Explicit aliases make the protocol discoverable to callers that use the
# common request/result terminology.
Consultation = ConsultationResult
RoleFirstConsultation = ConsultationLoop
