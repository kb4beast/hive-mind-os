"""Private, content-addressed lesson draft lifecycle (N20)."""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum

from .brain_kernel.canonical import canonical_digest, canonical_document
from .durable_contracts import ContractStore


class DraftError(ValueError):
    pass


class ProcessingState(StrEnum):
    CAPTURED_PRIVATE = "CAPTURED_PRIVATE"
    CANDIDATE_PRIVATE = "CANDIDATE_PRIVATE"
    SANITIZED_DRAFT = "SANITIZED_DRAFT"
    REVIEWED_DRAFT = "REVIEWED_DRAFT"
    COMMITTED_DRAFT = "COMMITTED_DRAFT"
    DRAFT_PR_OPEN = "DRAFT_PR_OPEN"
    BLOCKED_EXPORT_DESTINATION = "BLOCKED_EXPORT_DESTINATION"
    BLOCKED_EXPORT_AUTHORITY = "BLOCKED_EXPORT_AUTHORITY"
    QUARANTINED_EXPORT = "QUARANTINED_EXPORT"
    EXPORT_FAILED_RETRYABLE = "EXPORT_FAILED_RETRYABLE"


@dataclass(frozen=True, slots=True)
class LessonDraft:
    draft_id: str
    document_status: str
    processing_state: ProcessingState
    origin_subject_token: str
    origin_mission_token: str
    statement: str
    applicability: tuple[str, ...]
    outcome_class: str
    evidence_tokens: tuple[str, ...]
    private_custody_token: str
    confidence_basis: str
    counterexamples: tuple[str, ...]
    disposition_refs: tuple[str, ...]
    generator_id: str
    reviewer_id: str | None
    sanitization_receipt_digest: str | None
    export_policy_digest: str
    withheld_reason_code: str | None
    created_at: str

    def __post_init__(self):
        if not isinstance(self.processing_state, ProcessingState):
            object.__setattr__(
                self, "processing_state", ProcessingState(self.processing_state)
            )
        if self.document_status != "DRAFT":
            raise DraftError("document_status must be DRAFT")
        if (
            len(self.statement) > 2000
            or len(self.applicability) > 20
            or len(self.counterexamples) > 20
        ):
            raise DraftError("draft bounds exceeded")
        req = (
            self.draft_id,
            self.origin_subject_token,
            self.origin_mission_token,
            self.outcome_class,
            self.private_custody_token,
            self.confidence_basis,
            self.export_policy_digest,
            self.generator_id,
            self.created_at,
        )
        if any(type(v) is not str or not v.strip() for v in req):
            raise DraftError("required draft field missing")
        if any(
            type(v) is not str or not v.strip()
            for seq in (
                self.applicability,
                self.evidence_tokens,
                self.counterexamples,
                self.disposition_refs,
            )
            for v in seq
        ):
            raise DraftError("draft tokens must be non-empty")
        reviewed_states = {
            ProcessingState.REVIEWED_DRAFT,
            ProcessingState.COMMITTED_DRAFT,
            ProcessingState.DRAFT_PR_OPEN,
        }
        if self.processing_state in reviewed_states:
            if not self.reviewer_id or not self.sanitization_receipt_digest:
                raise DraftError("review evidence required")
            if self.reviewer_id == self.generator_id:
                raise DraftError("draft generator cannot review its own projection")

    @property
    def digest(self):
        return canonical_digest(self)

    def to_dict(self):
        return canonical_document(self)

    @classmethod
    def from_dict(cls, value):
        fields = {
            "draft_id",
            "document_status",
            "processing_state",
            "origin_subject_token",
            "origin_mission_token",
            "statement",
            "applicability",
            "outcome_class",
            "evidence_tokens",
            "private_custody_token",
            "confidence_basis",
            "counterexamples",
            "disposition_refs",
            "generator_id",
            "reviewer_id",
            "sanitization_receipt_digest",
            "export_policy_digest",
            "withheld_reason_code",
            "created_at",
        }
        if set(value) != fields:
            raise DraftError("closed draft schema")
        return cls(
            **{
                **value,
                "processing_state": ProcessingState(value["processing_state"]),
                "applicability": tuple(value["applicability"]),
                "evidence_tokens": tuple(value["evidence_tokens"]),
                "counterexamples": tuple(value["counterexamples"]),
                "disposition_refs": tuple(value["disposition_refs"]),
            }
        )

    def transition(self, state, **changes):
        if not isinstance(state, ProcessingState):
            raise DraftError("invalid processing state")
        allowed = {
            ProcessingState.CAPTURED_PRIVATE: {
                ProcessingState.CANDIDATE_PRIVATE,
                ProcessingState.QUARANTINED_EXPORT,
            },
            ProcessingState.CANDIDATE_PRIVATE: {
                ProcessingState.SANITIZED_DRAFT,
                ProcessingState.QUARANTINED_EXPORT,
            },
            ProcessingState.SANITIZED_DRAFT: {
                ProcessingState.REVIEWED_DRAFT,
                ProcessingState.QUARANTINED_EXPORT,
            },
            ProcessingState.REVIEWED_DRAFT: {
                ProcessingState.COMMITTED_DRAFT,
                ProcessingState.BLOCKED_EXPORT_DESTINATION,
                ProcessingState.BLOCKED_EXPORT_AUTHORITY,
                ProcessingState.QUARANTINED_EXPORT,
            },
            ProcessingState.COMMITTED_DRAFT: {
                ProcessingState.DRAFT_PR_OPEN,
                ProcessingState.BLOCKED_EXPORT_DESTINATION,
                ProcessingState.BLOCKED_EXPORT_AUTHORITY,
                ProcessingState.EXPORT_FAILED_RETRYABLE,
                ProcessingState.QUARANTINED_EXPORT,
            },
            ProcessingState.DRAFT_PR_OPEN: {
                ProcessingState.EXPORT_FAILED_RETRYABLE,
                ProcessingState.QUARANTINED_EXPORT,
            },
            ProcessingState.EXPORT_FAILED_RETRYABLE: {
                ProcessingState.DRAFT_PR_OPEN,
                ProcessingState.BLOCKED_EXPORT_AUTHORITY,
                ProcessingState.BLOCKED_EXPORT_DESTINATION,
                ProcessingState.QUARANTINED_EXPORT,
            },
            ProcessingState.BLOCKED_EXPORT_AUTHORITY: {
                ProcessingState.DRAFT_PR_OPEN,
                ProcessingState.QUARANTINED_EXPORT,
            },
            ProcessingState.BLOCKED_EXPORT_DESTINATION: {
                ProcessingState.DRAFT_PR_OPEN,
                ProcessingState.QUARANTINED_EXPORT,
            },
            ProcessingState.QUARANTINED_EXPORT: set(),
        }
        if state not in allowed[self.processing_state]:
            raise DraftError(
                f"invalid draft transition: {self.processing_state.value} -> {state.value}"
            )
        if state is ProcessingState.SANITIZED_DRAFT and not changes.get(
            "sanitization_receipt_digest", self.sanitization_receipt_digest
        ):
            raise DraftError("sanitization receipt required")
        if state is ProcessingState.REVIEWED_DRAFT and (
            not changes.get("reviewer_id", self.reviewer_id)
            or not changes.get(
                "sanitization_receipt_digest", self.sanitization_receipt_digest
            )
        ):
            raise DraftError("review evidence required")
        reviewer = changes.get("reviewer_id", self.reviewer_id)
        if state is ProcessingState.REVIEWED_DRAFT and reviewer == self.generator_id:
            raise DraftError("draft generator cannot review its own projection")
        return replace(self, processing_state=state, **changes)


def create_draft(**kwargs):
    kwargs.setdefault("document_status", "DRAFT")
    kwargs.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    kwargs.setdefault("reviewer_id", None)
    kwargs.setdefault("sanitization_receipt_digest", None)
    return LessonDraft(**kwargs)


class LessonDraftStore:
    def __init__(self, path):
        self._store = ContractStore(path, LessonDraft.from_dict)

    def put(self, draft):
        return self._store.put(draft.digest, draft)

    def get(self, digest):
        return self._store.get(digest)

    def reviewed_for_export(self, digest):
        draft = self.get(digest)
        if draft is None or draft.processing_state not in {
            ProcessingState.REVIEWED_DRAFT,
            ProcessingState.COMMITTED_DRAFT,
            ProcessingState.DRAFT_PR_OPEN,
        }:
            raise DraftError("draft is not exportable")
        return draft
