"""Evidence-bound, non-promoting learning primitives for the Optimizer role.

This module is intentionally local and effect-free.  It turns already retained
outcomes into scoped lessons and immutable challenger proposals, then returns a
recommendation for an independent court.  It cannot replace a champion, run an
evaluation, or promote anything.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import cast

from .canonical import canonical_digest


def _is_exact_nonblank_string(value: object) -> bool:
    return type(value) is str and bool(value.strip())


class OptimizerError(ValueError):
    """An optimizer input violates the local, non-promoting contract."""


class PromotionRecommendation(StrEnum):
    """A court-facing recommendation that deliberately has no effect."""

    DEFER = "defer"
    REQUEST_INDEPENDENT_REVIEW = "request-independent-review"


@dataclass(frozen=True, slots=True)
class OutcomeAttribution:
    """The minimum retained facts from which a reusable lesson can be derived."""

    evidence_refs: tuple[str, ...]
    context_ref: str
    outcome_ref: str
    error_class: str
    applicability: tuple[str, ...]
    confidence: float
    expires_at: str
    provenance_ref: str

    def __post_init__(self) -> None:
        _validate_outcome_attribution(self)


@dataclass(frozen=True, slots=True)
class ScopedLesson:
    """An immutable, provenance-bound lesson candidate."""

    attribution: OutcomeAttribution
    lesson_digest: str

    def __post_init__(self) -> None:
        _validate_scoped_lesson(self)


@dataclass(frozen=True, slots=True)
class ChallengerProposal:
    """An immutable alternative; it contains no mutable champion reference."""

    challenger_id: str
    parent_champion_id: str
    change_ref: str
    author_id: str
    lesson: ScopedLesson
    proposal_digest: str

    def __post_init__(self) -> None:
        _validate_challenger_proposal(self)

    @property
    def lesson_digest(self) -> str:
        return self.lesson.lesson_digest


def _require_trimmed_string(value: object, label: str) -> str:
    if type(value) is not str:
        raise OptimizerError(f"{label} must be an exact trimmed string")
    text = cast(str, value)
    if not text.strip() or text != text.strip():
        raise OptimizerError(f"{label} must be an exact trimmed string")
    return text


def _validate_outcome_attribution(value: object) -> OutcomeAttribution:
    if type(value) is not OutcomeAttribution:
        raise OptimizerError("lesson attribution type is invalid")
    if type(value.evidence_refs) is not tuple or type(value.applicability) is not tuple:
        raise OptimizerError("lesson sequence bindings must be immutable tuples")
    if not value.evidence_refs:
        raise OptimizerError("lesson attribution requires retained evidence")
    for item in value.evidence_refs:
        _require_trimmed_string(item, "lesson evidence reference")
    if len(set(value.evidence_refs)) != len(value.evidence_refs):
        raise OptimizerError("lesson evidence references must be unique")
    for item, label in (
        (value.context_ref, "lesson context reference"),
        (value.outcome_ref, "lesson outcome reference"),
        (value.error_class, "lesson error class"),
        (value.provenance_ref, "lesson provenance reference"),
        (value.expires_at, "lesson expiry"),
    ):
        _require_trimmed_string(item, label)
    if not value.applicability:
        raise OptimizerError("lesson applicability is required")
    for item in value.applicability:
        _require_trimmed_string(item, "lesson applicability")
    if len(set(value.applicability)) != len(value.applicability):
        raise OptimizerError("lesson applicability must be unique")
    if type(value.confidence) is not float or not 0.0 <= value.confidence <= 1.0:
        raise OptimizerError("lesson confidence must be a float in [0, 1]")
    try:
        expires = datetime.fromisoformat(value.expires_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise OptimizerError("lesson expiry must be RFC 3339") from error
    if expires.tzinfo is None or expires.astimezone(timezone.utc) <= datetime.now(timezone.utc):
        raise OptimizerError("lesson expiry must be in the future")
    return value


def _validate_scoped_lesson(value: object) -> ScopedLesson:
    if type(value) is not ScopedLesson:
        raise OptimizerError("scoped lesson type is invalid")
    attribution = _validate_outcome_attribution(value.attribution)
    _require_trimmed_string(value.lesson_digest, "lesson digest")
    if value.lesson_digest != canonical_digest(asdict(attribution)):
        raise OptimizerError("lesson digest does not match its attribution")
    return value


def _proposal_material(value: ChallengerProposal) -> dict[str, str]:
    return {
        "challenger_id": value.challenger_id,
        "parent_champion_id": value.parent_champion_id,
        "change_ref": value.change_ref,
        "author_id": value.author_id,
        "lesson_digest": value.lesson.lesson_digest,
    }


def _validate_challenger_proposal(value: object) -> ChallengerProposal:
    if type(value) is not ChallengerProposal:
        raise OptimizerError("challenger proposal type is invalid")
    _validate_scoped_lesson(value.lesson)
    for item, label in (
        (value.challenger_id, "challenger identity"),
        (value.parent_champion_id, "champion identity"),
        (value.change_ref, "challenger change reference"),
        (value.author_id, "author identity"),
        (value.proposal_digest, "proposal digest"),
    ):
        _require_trimmed_string(item, label)
    if value.challenger_id == value.parent_champion_id:
        raise OptimizerError("challenger must differ from its champion")
    if value.proposal_digest != canonical_digest(_proposal_material(value)):
        raise OptimizerError("proposal digest does not match its bindings")
    return value


@dataclass(frozen=True, slots=True)
class CourtRecommendation:
    """A non-executable independent-review request."""

    proposal_digest: str
    evaluator_id: str
    recommendation: PromotionRecommendation
    reason: str


class Optimizer:
    """Create lessons and proposals without any champion-changing capability."""

    def attribute_outcome(self, attribution: OutcomeAttribution) -> ScopedLesson:
        _validate_outcome_attribution(attribution)
        return ScopedLesson(
            attribution=attribution,
            lesson_digest=canonical_digest(asdict(attribution)),
        )

    def propose_challenger(
        self,
        lesson: ScopedLesson,
        *,
        challenger_id: str,
        champion_id: str,
        change_ref: str,
        author_id: str,
    ) -> ChallengerProposal:
        _validate_scoped_lesson(lesson)
        for value, label in (
            (challenger_id, "challenger identity"),
            (champion_id, "champion identity"),
            (change_ref, "challenger change reference"),
            (author_id, "author identity"),
        ):
            _require_trimmed_string(value, label)
        if challenger_id == champion_id:
            raise OptimizerError("challenger must differ from its champion")
        values = {
            "challenger_id": challenger_id,
            "parent_champion_id": champion_id,
            "change_ref": change_ref,
            "author_id": author_id,
            "lesson_digest": lesson.lesson_digest,
        }
        return ChallengerProposal(
            challenger_id=challenger_id,
            parent_champion_id=champion_id,
            change_ref=change_ref,
            author_id=author_id,
            lesson=lesson,
            proposal_digest=canonical_digest(values),
        )

    def recommend_independent_review(
        self,
        proposal: ChallengerProposal,
        *,
        evaluator_id: str,
        evidence_complete: bool,
    ) -> CourtRecommendation:
        _validate_challenger_proposal(proposal)
        _require_trimmed_string(evaluator_id, "evaluator identity")
        if evaluator_id == proposal.author_id:
            raise OptimizerError("optimizer candidate author cannot evaluate or promote it")
        if type(evidence_complete) is not bool:
            raise OptimizerError("evidence completeness must be a boolean")
        if not evidence_complete:
            return CourtRecommendation(
                proposal.proposal_digest,
                evaluator_id,
                PromotionRecommendation.DEFER,
                "retained evidence is incomplete",
            )
        return CourtRecommendation(
            proposal.proposal_digest,
            evaluator_id,
            PromotionRecommendation.REQUEST_INDEPENDENT_REVIEW,
            "independent court must evaluate before any promotion",
        )
