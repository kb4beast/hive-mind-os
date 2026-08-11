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
from typing import Mapping

from .canonical import canonical_digest


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
        if not self.evidence_refs or any(not value.strip() for value in self.evidence_refs):
            raise OptimizerError("lesson attribution requires retained evidence")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise OptimizerError("lesson evidence references must be unique")
        for value in (
            self.context_ref,
            self.outcome_ref,
            self.error_class,
            self.provenance_ref,
        ):
            if not value.strip():
                raise OptimizerError("lesson attribution bindings must be nonempty")
        if not self.applicability or any(not value.strip() for value in self.applicability):
            raise OptimizerError("lesson applicability is required")
        if len(set(self.applicability)) != len(self.applicability):
            raise OptimizerError("lesson applicability must be unique")
        if not isinstance(self.confidence, float) or not 0.0 <= self.confidence <= 1.0:
            raise OptimizerError("lesson confidence must be a float in [0, 1]")
        try:
            expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise OptimizerError("lesson expiry must be RFC 3339") from error
        if expires.tzinfo is None or expires.astimezone(timezone.utc) <= datetime.now(timezone.utc):
            raise OptimizerError("lesson expiry must be in the future")


@dataclass(frozen=True, slots=True)
class ScopedLesson:
    """An immutable, provenance-bound lesson candidate."""

    attribution: OutcomeAttribution
    lesson_digest: str

    def __post_init__(self) -> None:
        expected = canonical_digest(asdict(self.attribution))
        if self.lesson_digest != expected:
            raise OptimizerError("lesson digest does not match its attribution")


@dataclass(frozen=True, slots=True)
class ChallengerProposal:
    """An immutable alternative; it contains no mutable champion reference."""

    challenger_id: str
    parent_champion_id: str
    change_ref: str
    author_id: str
    lesson_digest: str
    proposal_digest: str

    def __post_init__(self) -> None:
        for value in (
            self.challenger_id,
            self.parent_champion_id,
            self.change_ref,
            self.author_id,
            self.lesson_digest,
            self.proposal_digest,
        ):
            if not value.strip():
                raise OptimizerError("challenger proposal bindings must be nonempty")
        if self.challenger_id == self.parent_champion_id:
            raise OptimizerError("challenger must differ from its champion")


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
        if not challenger_id.strip() or not champion_id.strip() or not change_ref.strip() or not author_id.strip():
            raise OptimizerError("challenger proposal bindings must be nonempty")
        if author_id != author_id.strip():
            raise OptimizerError("author identity must not contain surrounding whitespace")
        if challenger_id == champion_id:
            raise OptimizerError("challenger must differ from its champion")
        values: Mapping[str, str] = {
            "challenger_id": challenger_id,
            "parent_champion_id": champion_id,
            "change_ref": change_ref,
            "author_id": author_id,
            "lesson_digest": lesson.lesson_digest,
        }
        return ChallengerProposal(
            **values,
            proposal_digest=canonical_digest(values),
        )

    def recommend_independent_review(
        self,
        proposal: ChallengerProposal,
        *,
        evaluator_id: str,
        evidence_complete: bool,
    ) -> CourtRecommendation:
        if not evaluator_id.strip():
            raise OptimizerError("evaluator identity is required")
        if evaluator_id != evaluator_id.strip():
            raise OptimizerError("evaluator identity must not contain surrounding whitespace")
        if evaluator_id == proposal.author_id:
            raise OptimizerError("optimizer candidate author cannot evaluate or promote it")
        if not isinstance(evidence_complete, bool):
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
