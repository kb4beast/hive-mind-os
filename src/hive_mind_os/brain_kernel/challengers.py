"""Generate immutable challengers from accepted lessons without touching live champions."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ..models import Role, utc_now
from ..prompt_registry import PromptRegistry, prompt_digest
from ..recursive_improvement import (
    ExperimentCandidate,
    MetricDirection,
    MetricSpec,
    RecursiveImprovementContract,
)
from .canonical import canonical_digest

__all__ = [
    "FORBIDDEN_SELF_MODIFICATION_CLASSES",
    "UNRECOGNIZED_TAG_REASON",
    "FORBIDDEN_CLASS_REASON",
    "AcceptedLesson",
    "ChallengerGenerationError",
    "ChallengerGenerator",
    "ChallengerRejection",
    "ChallengerSpec",
    "ChallengerSurface",
    "ChampionMutationError",
    "ForbiddenChallengerClass",
    "GenerationResult",
    "classify_forbidden",
    "lesson_from_document",
]


class ChallengerGenerationError(ValueError):
    """A lesson or challenger specification is malformed."""


class ChampionMutationError(RuntimeError):
    """A challenger attempted to alias or move a live champion."""


class ForbiddenChallengerClass(RuntimeError):
    """A lesson would seed a forbidden self-modification challenger."""

    def __init__(self, lesson_id: str, forbidden_class: str) -> None:
        super().__init__(
            f"lesson {lesson_id} maps to forbidden class {forbidden_class}"
        )
        self.lesson_id = lesson_id
        self.forbidden_class = forbidden_class


def _contract_forbidden_behaviors() -> tuple[str, ...]:
    """Read the canonical list off a constructed contract, never a hand copy.

    ``RecursiveImprovementContract`` is a ``slots=True`` dataclass, so the
    class attribute is a slot descriptor rather than the default tuple; the
    only honest way to reach the default is to instantiate the contract.
    """

    probe = RecursiveImprovementContract(
        primary=MetricSpec("task_success_rate", MetricDirection.MAXIMIZE),
        guardrails=(),
    )
    return probe.forbidden_behaviors


FORBIDDEN_SELF_MODIFICATION_CLASSES: frozenset[str] = frozenset(
    _contract_forbidden_behaviors()
)

FORBIDDEN_CLASS_REASON = "forbidden self-modification class"
UNRECOGNIZED_TAG_REASON = "unrecognized applicability tag"


class ChallengerSurface(StrEnum):
    PROMPT = "prompt"
    PLANNER = "planner"
    POLICY_RULE = "policy-rule"
    RETRIEVAL = "retrieval"
    TOOL_SELECTION = "tool-selection"


_SURFACE_TAG_PREFIXES: Mapping[str, ChallengerSurface] = {
    "prompt": ChallengerSurface.PROMPT,
    "planner": ChallengerSurface.PLANNER,
    "policy-rule": ChallengerSurface.POLICY_RULE,
    "retrieval": ChallengerSurface.RETRIEVAL,
    "tool-selection": ChallengerSurface.TOOL_SELECTION,
}

# Applicability tag prefixes that are not challenger surfaces at all: they name
# the governance machinery itself, so a lesson pointing at them would seed a
# self-modification challenger. Values are members of the canonical contract
# list above (checked at import).
_FORBIDDEN_TAG_PREFIXES: Mapping[str, str] = {
    "champion": "live_champion_mutation",
    "goal": "goal_mutation",
    "objective": "goal_mutation",
    "policy": "policy_mutation",
    "weights": "self_weight_modification",
    "model": "self_weight_modification",
    "holdout": "holdout_access",
    "evaluator": "self_evaluation",
    "judge": "self_evaluation",
    "metric": "metric_gaming",
    "evidence": "evidence_concealment",
    "ledger": "evidence_concealment",
    "budget": "unbounded_resource_acquisition",
    "resource": "unbounded_resource_acquisition",
}

# PROMPT challengers are per-role; the registry performs the authoritative
# coercion, this only keeps a nonsense target from being treated as parented.
_ROLE_VALUES: frozenset[str] = frozenset(role.value for role in Role)

if not set(_FORBIDDEN_TAG_PREFIXES.values()) <= FORBIDDEN_SELF_MODIFICATION_CLASSES:
    raise RuntimeError(
        "challenger tag classification drifted from the recursive-improvement contract"
    )


def _require_text(value: Any, message: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ChallengerGenerationError(message)
    return value


def _require_text_tuple(value: Any, message: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ChallengerGenerationError(message)
    items = tuple(value)
    if not items or any(
        not isinstance(item, str) or not item.strip() for item in items
    ):
        raise ChallengerGenerationError(message)
    return items


@dataclass(frozen=True, slots=True)
class AcceptedLesson:
    lesson_id: str
    source_episode_id: str
    outcome: str
    error_class: str
    applicability: tuple[str, ...]
    confidence: float
    provenance: tuple[str, ...]
    expires_at: str
    status: str = "accepted"

    def __post_init__(self) -> None:
        _require_text(self.lesson_id, "lesson_id is required")
        _require_text(self.source_episode_id, "source_episode_id is required")
        _require_text(self.outcome, "outcome is required")
        _require_text(self.error_class, "error_class is required")
        _require_text(self.expires_at, "expires_at is required")
        _require_text(self.status, "status is required")
        _require_text_tuple(
            self.applicability, "applicability must be a nonempty tuple of tags"
        )
        _require_text_tuple(
            self.provenance, "provenance must be a nonempty tuple of evidence refs"
        )
        if not isinstance(self.confidence, (int, float)) or isinstance(
            self.confidence, bool
        ):
            raise ChallengerGenerationError("confidence must be numeric")
        if not 0.0 < float(self.confidence) <= 1.0:
            raise ChallengerGenerationError(
                "confidence must fall in the interval (0.0, 1.0]"
            )
        if self.status != "accepted":
            raise ChallengerGenerationError(
                "only accepted lessons may seed challengers"
            )


def lesson_from_document(document: Mapping[str, Any]) -> AcceptedLesson:
    """Adapt a LEARN-500 lesson record; this is the ONLY LEARN-500 coupling point."""

    if not isinstance(document, Mapping):
        raise ChallengerGenerationError("lesson document must be a mapping")

    def pick(*keys: str) -> Any:
        for key in keys:
            if key in document:
                return document[key]
        return None

    confidence = pick("confidence")
    try:
        confidence_value = float(confidence)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ChallengerGenerationError("confidence must be numeric") from None

    applicability = pick("applicability")
    provenance = pick("provenance", "evidence_refs")
    return AcceptedLesson(
        lesson_id=_require_text(pick("lesson_id", "id"), "lesson_id is required"),
        source_episode_id=_require_text(
            pick("source_episode_id", "episode_id"), "source_episode_id is required"
        ),
        outcome=_require_text(pick("outcome"), "outcome is required"),
        error_class=_require_text(pick("error_class"), "error_class is required"),
        applicability=_require_text_tuple(
            applicability, "applicability must be a nonempty tuple of tags"
        ),
        confidence=confidence_value,
        provenance=_require_text_tuple(
            provenance, "provenance must be a nonempty tuple of evidence refs"
        ),
        expires_at=_require_text(
            pick("expires_at", "expiry"), "expires_at is required"
        ),
        status=_require_text(
            document.get("status", "accepted"), "status is required"
        ),
    )


@dataclass(frozen=True, slots=True)
class ChallengerSpec:
    challenger_id: str
    surface: ChallengerSurface
    champion_ref: str
    target: str
    hypothesis: str
    changed_scope: tuple[str, ...]
    rollback_ref: str
    lesson_id: str
    provenance: tuple[str, ...]
    created_by: str
    created_at: str
    content: str
    content_digest: str

    def __post_init__(self) -> None:
        required = {
            "challenger_id": self.challenger_id,
            "champion_ref": self.champion_ref,
            "target": self.target,
            "hypothesis": self.hypothesis,
            "rollback_ref": self.rollback_ref,
            "lesson_id": self.lesson_id,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "content": self.content,
        }
        for name, value in required.items():
            _require_text(value, f"challenger {name} is required")
        _require_text_tuple(
            self.changed_scope, "challenger changed_scope must be nonempty"
        )
        _require_text_tuple(
            self.provenance, "challenger provenance must be nonempty"
        )
        if not isinstance(self.surface, ChallengerSurface):
            raise ChallengerGenerationError("challenger surface is required")
        if (
            self.challenger_id == self.champion_ref
            or self.content_digest == self.champion_ref
        ):
            raise ChampionMutationError(
                "challenger may not alias the live champion"
            )
        if self.content_digest != prompt_digest(self.content):
            raise ChallengerGenerationError(
                "challenger content digest does not address its content"
            )

    def to_experiment_candidate(self) -> ExperimentCandidate:
        return ExperimentCandidate(
            id=self.content_digest,
            parent_champion_id=self.champion_ref,
            hypothesis=self.hypothesis,
            changed_paths=self.changed_scope,
            rollback_ref=self.rollback_ref,
        )


@dataclass(frozen=True, slots=True)
class ChallengerRejection:
    lesson_id: str
    reason: str
    forbidden_class: str | None = None


@dataclass(frozen=True, slots=True)
class GenerationResult:
    challengers: tuple[ChallengerSpec, ...]
    rejections: tuple[ChallengerRejection, ...]


def classify_forbidden(lesson: AcceptedLesson) -> str | None:
    """Return the forbidden self-modification class this lesson would seed."""

    for tag in lesson.applicability:
        prefix = tag.partition(":")[0]
        if prefix in _SURFACE_TAG_PREFIXES:
            continue
        forbidden = _FORBIDDEN_TAG_PREFIXES.get(prefix)
        if forbidden is not None:
            return forbidden
    if lesson.error_class in FORBIDDEN_SELF_MODIFICATION_CLASSES:
        return lesson.error_class
    return None


class ChallengerGenerator:
    """Turn accepted lessons into immutable, champion-parented challengers."""

    def __init__(
        self,
        *,
        generated_by: str,
        registry: PromptRegistry | None = None,
        now: Callable[[], str] = utc_now,
    ) -> None:
        if not isinstance(generated_by, str) or not generated_by.strip():
            raise ChallengerGenerationError("generated_by identity is required")
        self.generated_by = generated_by
        self.registry = registry
        self._now = now

    def generate(
        self,
        lessons: Sequence[AcceptedLesson | Mapping[str, Any]],
        *,
        champions: Mapping[str, str],
    ) -> GenerationResult:
        specs: dict[str, ChallengerSpec] = {}
        rejections: list[ChallengerRejection] = []

        for entry in lessons:
            if isinstance(entry, AcceptedLesson):
                lesson = entry
            else:
                try:
                    lesson = lesson_from_document(entry)
                except ChallengerGenerationError as error:
                    rejections.append(
                        ChallengerRejection(_document_id(entry), str(error))
                    )
                    continue

            forbidden = classify_forbidden(lesson)
            if forbidden is not None:
                rejections.append(
                    ChallengerRejection(
                        lesson.lesson_id, FORBIDDEN_CLASS_REASON, forbidden
                    )
                )
                continue

            for tag in lesson.applicability:
                prefix, separator, target = tag.partition(":")
                surface = _SURFACE_TAG_PREFIXES.get(prefix)
                if surface is None or not separator or not target.strip():
                    rejections.append(
                        ChallengerRejection(lesson.lesson_id, UNRECOGNIZED_TAG_REASON)
                    )
                    continue

                resolved = self._resolve_champion(surface, target, champions)
                if resolved is None:
                    rejections.append(
                        ChallengerRejection(
                            lesson.lesson_id,
                            f"no live champion for {surface.value}:{target}",
                        )
                    )
                    continue
                champion_ref, champion_content = resolved

                content = self._build_content(
                    lesson, surface, target, champion_ref, champion_content
                )
                content_digest = prompt_digest(content)
                challenger_id = "chal:" + canonical_digest(
                    (surface, target, champion_ref, lesson.lesson_id, content_digest)
                )[len("sha256:") :]
                if challenger_id in specs:
                    continue

                spec = ChallengerSpec(
                    challenger_id=challenger_id,
                    surface=surface,
                    champion_ref=champion_ref,
                    target=target,
                    hypothesis=(
                        f"applying lesson {lesson.lesson_id} to "
                        f"{surface.value}:{target} reduces {lesson.error_class}"
                    ),
                    changed_scope=(f"{surface.value}:{target}",),
                    rollback_ref=champion_ref,
                    lesson_id=lesson.lesson_id,
                    provenance=lesson.provenance + (f"lesson:{lesson.lesson_id}",),
                    created_by=self.generated_by,
                    created_at=self._now(),
                    content=content,
                    content_digest=content_digest,
                )
                specs[challenger_id] = spec

                if self.registry is not None and surface is ChallengerSurface.PROMPT:
                    # Content-addressed artifact + lineage record only. This
                    # stores bytes; it never moves a champion pointer.
                    self.registry.register(
                        target,
                        content,
                        parent_digest=champion_ref,
                        created_by=self.generated_by,
                        experiment_id=f"challenger:{lesson.lesson_id}",
                    )

        return GenerationResult(tuple(specs.values()), tuple(rejections))

    def _resolve_champion(
        self,
        surface: ChallengerSurface,
        target: str,
        champions: Mapping[str, str],
    ) -> tuple[str, str | None] | None:
        """Return ``(champion_ref, champion_content)`` or ``None`` when parentless."""

        if surface is ChallengerSurface.PROMPT and target not in _ROLE_VALUES:
            return None
        if surface is ChallengerSurface.PROMPT and self.registry is not None:
            try:
                content, digest = self.registry.champion_prompt(target)
            except (KeyError, ValueError, RuntimeError):
                return None
            return digest, content

        champion_ref = champions.get(f"{surface.value}:{target}")
        if not isinstance(champion_ref, str) or not champion_ref.strip():
            return None
        if surface is ChallengerSurface.PROMPT:
            # Without a registry the champion prompt text is unreadable; the
            # challenger is still parented on the champion ref and its base is
            # a deterministic reference stub rather than invented prompt text.
            return champion_ref, f"champion-prompt {champion_ref}"
        return champion_ref, None

    @staticmethod
    def _build_content(
        lesson: AcceptedLesson,
        surface: ChallengerSurface,
        target: str,
        champion_ref: str,
        champion_content: str | None,
    ) -> str:
        if surface is ChallengerSurface.PROMPT:
            if champion_content is None:
                raise ChallengerGenerationError(
                    "prompt challengers require resolvable champion content"
                )
            return champion_content + (
                f"\n\nLesson {lesson.lesson_id}: avoid {lesson.error_class}; "
                f"evidence: {lesson.provenance[0]}"
            )
        return json.dumps(
            {
                "surface": surface.value,
                "target": target,
                "champion_ref": champion_ref,
                "lesson_id": lesson.lesson_id,
                "error_class": lesson.error_class,
                "directive": f"counteract {lesson.error_class}",
            },
            sort_keys=True,
            separators=(",", ":"),
        )


def _document_id(document: Any) -> str:
    if isinstance(document, Mapping):
        for key in ("lesson_id", "id"):
            value = document.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return "<unknown>"
