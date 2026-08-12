"""Scoped, evidence-bound lesson generation from governed learning signals.

Lessons produced here are advisory data records.  Nothing in this module writes
policy, rewrites an instruction template, or selects a champion variant: those
paths stay with the existing kernel gates and are deliberately not importable
from here.  A lesson is a pure function of the recorded signals it cites, so an
unevidenced claim cannot acquire an identity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from .canonical import canonical_digest
from .contracts import MemoryRecord, MemoryState
from .memory import ConsolidationPolicy

# Copied literals (private names in the source modules are never imported).
_MEMORY_ID = re.compile(r"MEMORY-[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_LESSON_ID = re.compile(r"LESSON-[0-9a-f]{20}\Z")
_SECRET = re.compile(
    r"(?i)(?:\b(?:api[_-]?key|password|secret|access[_-]?token)\s*[:=]\s*\S+|\b(?:sk|ghp|github_pat)_[a-z0-9_-]{8,})"
)
_SCOPES = frozenset({"global", "repository", "mission", "role", "work_item"})

GENERATOR_IDENTITY = "learning_runtime"


class LearningDenied(ValueError):
    """A lesson operation violates the evidence-bound learning contract."""


class SignalKind(StrEnum):
    OUTCOME = "outcome"
    INCIDENT = "incident"
    REMAND = "remand"
    REPAIR = "repair"
    HUMAN_CORRECTION = "human_correction"


class OutcomeClass(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LearningDenied(f"{label} is required")
    return value


def _free_text(value: object, label: str) -> str:
    text = _text(value, label)
    if _SECRET.search(text) is not None:
        raise LearningDenied(f"{label} contains secret-like data")
    return text


def _memory_id(value: object, label: str) -> str:
    text = _text(value, label)
    if _MEMORY_ID.fullmatch(text) is None:
        raise LearningDenied(f"{label} must be a MEMORY- identifier")
    return text


def _evidence(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not value:
        raise LearningDenied(f"{label} requires at least one evidence digest")
    for item in value:
        if not isinstance(item, str) or _DIGEST.fullmatch(item) is None:
            raise LearningDenied(f"{label} must be lowercase sha256:<64 hex>")
    return value


def _instant(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise LearningDenied(f"{label} must be an RFC 3339 time")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise LearningDenied(f"{label} must be an RFC 3339 time") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LearningDenied(f"{label} must include an offset")
    return parsed.astimezone(timezone.utc)


def _render(value: datetime) -> str:
    utc = value.astimezone(timezone.utc).replace(tzinfo=None)
    spec = "microseconds" if utc.microsecond else "seconds"
    return f"{utc.isoformat(timespec=spec)}Z"


def _member(value: object, kind: type[StrEnum], label: str) -> Any:
    try:
        return kind(value)
    except ValueError as error:
        raise LearningDenied(f"{label} is not a recognised {kind.__name__}") from error


@dataclass(frozen=True, slots=True)
class LearningSignal:
    """One recorded outcome, incident, remand, repair, or human correction.

    Signals carry digests, never free-text excerpts of model or tool output.
    """

    signal_id: str
    kind: SignalKind
    episode_record_id: str
    outcome: OutcomeClass
    error_class: str
    context_key: str
    evidence_refs: tuple[str, ...]
    observed_at: str

    def __post_init__(self) -> None:
        _text(self.signal_id, "signal_id")
        _text(self.error_class, "error_class")
        _text(self.context_key, "context_key")
        object.__setattr__(self, "kind", _member(self.kind, SignalKind, "kind"))
        object.__setattr__(self, "outcome", _member(self.outcome, OutcomeClass, "outcome"))
        _memory_id(self.episode_record_id, "episode_record_id")
        _evidence(self.evidence_refs, "evidence_refs")
        _instant(self.observed_at, "observed_at")


@dataclass(frozen=True, slots=True)
class LessonApplicability:
    scope: str
    subject_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.scope not in _SCOPES:
            raise LearningDenied("applicability scope is outside the memory vocabulary")
        if not isinstance(self.subject_keys, tuple):
            raise LearningDenied("subject_keys must be a tuple")
        for key in self.subject_keys:
            _text(key, "subject key")
        if len(set(self.subject_keys)) != len(self.subject_keys):
            raise LearningDenied("subject_keys must be unique")
        if self.scope != "global" and not self.subject_keys:
            raise LearningDenied("non-global applicability requires subject_keys")


@dataclass(frozen=True, slots=True)
class LessonProvenance:
    generator: str
    evaluator_id: str
    signal_ids: tuple[str, ...]
    roles: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.generator, "generator")
        _text(self.evaluator_id, "evaluator_id")
        if self.generator == self.evaluator_id:
            raise LearningDenied("evaluator identity must differ from the generator")
        if not isinstance(self.signal_ids, tuple) or not self.signal_ids:
            raise LearningDenied("provenance requires at least one signal id")
        if tuple(sorted(set(self.signal_ids))) != self.signal_ids:
            raise LearningDenied("signal_ids must be sorted and unique")
        if not isinstance(self.roles, tuple) or len(set(self.roles)) != len(self.roles):
            raise LearningDenied("provenance roles must be a tuple of unique names")


@dataclass(frozen=True, slots=True)
class Counterexample:
    signal_id: str
    episode_record_id: str
    evidence_refs: tuple[str, ...]
    observed_at: str
    note: str

    def __post_init__(self) -> None:
        _text(self.signal_id, "signal_id")
        _memory_id(self.episode_record_id, "episode_record_id")
        _evidence(self.evidence_refs, "evidence_refs")
        _instant(self.observed_at, "observed_at")
        _free_text(self.note, "counterexample note")


@dataclass(frozen=True, slots=True)
class DissentRecord:
    role: str
    position: str
    recorded_at: str

    def __post_init__(self) -> None:
        _text(self.role, "dissent role")
        _free_text(self.position, "dissent position")
        _instant(self.recorded_at, "recorded_at")


@dataclass(frozen=True, slots=True)
class Lesson:
    """An advisory, expiring claim bound to the episodes that produced it."""

    lesson_id: str
    statement: str
    error_class: str
    outcome: OutcomeClass
    episode_record_ids: tuple[str, ...]
    applicability: LessonApplicability
    confidence: float
    provenance: LessonProvenance
    valid_from: str
    valid_to: str
    counterexamples: tuple[Counterexample, ...] = ()
    dissent: tuple[DissentRecord, ...] = ()

    def __post_init__(self) -> None:
        _text(self.lesson_id, "lesson_id")
        if _LESSON_ID.fullmatch(self.lesson_id) is None:
            raise LearningDenied("lesson_id must be a derived LESSON- digest prefix")
        _free_text(self.statement, "lesson statement")
        _text(self.error_class, "error_class")
        object.__setattr__(self, "outcome", _member(self.outcome, OutcomeClass, "outcome"))
        if not isinstance(self.episode_record_ids, tuple) or not self.episode_record_ids:
            raise LearningDenied("a lesson requires at least one source episode")
        for record_id in self.episode_record_ids:
            _memory_id(record_id, "episode_record_id")
        if tuple(sorted(set(self.episode_record_ids))) != self.episode_record_ids:
            raise LearningDenied("episode_record_ids must be sorted and unique")
        if not isinstance(self.applicability, LessonApplicability):
            raise LearningDenied("applicability must be a LessonApplicability")
        if not isinstance(self.provenance, LessonProvenance):
            raise LearningDenied("provenance must be a LessonProvenance")
        if type(self.confidence) is not float or not 0.0 <= self.confidence <= 1.0:
            raise LearningDenied("confidence must be a float within [0.0, 1.0]")
        started = _instant(self.valid_from, "valid_from")
        expires = _instant(self.valid_to, "valid_to")
        if expires <= started:
            raise LearningDenied("lesson expiry must be strictly after valid_from")
        if not isinstance(self.counterexamples, tuple) or not isinstance(self.dissent, tuple):
            raise LearningDenied("retained records must be tuples")
        signal_ids = [item.signal_id for item in self.counterexamples]
        if len(set(signal_ids)) != len(signal_ids):
            raise LearningDenied("counterexamples must have unique signal ids")
        positions = [(item.role, item.position) for item in self.dissent]
        if len(set(positions)) != len(positions):
            raise LearningDenied("dissent positions must be unique per role")

    @property
    def digest(self) -> str:
        return canonical_digest(self)


class LessonGenerator:
    """Derives lessons from recorded signals; it decides nothing else."""

    def __init__(
        self,
        *,
        policy: ConsolidationPolicy = ConsolidationPolicy(),
        default_ttl_days: int = 90,
    ) -> None:
        if not isinstance(policy, ConsolidationPolicy):
            raise LearningDenied("evidence policy must be a ConsolidationPolicy")
        if type(default_ttl_days) is not int or default_ttl_days <= 0:
            raise LearningDenied("default_ttl_days must be a positive integer")
        self.policy = policy
        self.default_ttl_days = default_ttl_days

    def attribute(
        self, signals: Iterable[LearningSignal], *, now: str
    ) -> Mapping[str, tuple[LearningSignal, ...]]:
        """Group validated signals by error class under a point-in-time guard."""

        horizon = _instant(now, "now")
        collected = tuple(signals)
        if not collected:
            raise LearningDenied("attribution requires at least one signal")
        seen: set[str] = set()
        buckets: dict[str, list[LearningSignal]] = {}
        for signal in collected:
            if not isinstance(signal, LearningSignal):
                raise LearningDenied("attribution accepts LearningSignal records only")
            if signal.signal_id in seen:
                raise LearningDenied("duplicate signal id in attribution batch")
            seen.add(signal.signal_id)
            if _instant(signal.observed_at, "observed_at") > horizon:
                raise LearningDenied("future-dated signal cannot inform a lesson")
            buckets.setdefault(signal.error_class, []).append(signal)
        ordered = {
            error_class: tuple(
                sorted(items, key=lambda item: (item.observed_at, item.signal_id))
            )
            for error_class, items in sorted(buckets.items())
        }
        return MappingProxyType(ordered)

    def generate(
        self,
        signals: Iterable[LearningSignal],
        *,
        statement: str,
        error_class: str,
        applicability: LessonApplicability,
        evaluator_id: str,
        now: str,
        roles: tuple[str, ...] = (),
        ttl_days: int | None = None,
    ) -> Lesson:
        """Build one Lesson from the signals matching ``error_class``."""

        _free_text(statement, "lesson statement")
        _text(error_class, "error_class")
        _text(evaluator_id, "evaluator_id")
        if not isinstance(applicability, LessonApplicability):
            raise LearningDenied("applicability must be a LessonApplicability")
        window = self.default_ttl_days if ttl_days is None else ttl_days
        if type(window) is not int or window <= 0:
            raise LearningDenied("ttl_days must be a positive integer")

        buckets = self.attribute(signals, now=now)
        bucket = buckets.get(error_class)
        if not bucket:
            raise LearningDenied("no signal carries the requested error class")
        self._require_independence(bucket, "lesson lacks independent evidence")

        dominant = self._dominant_outcome(bucket)
        supporting = tuple(item for item in bucket if item.outcome is dominant)
        contrary = tuple(item for item in bucket if item.outcome is not dominant)
        self._require_independence(supporting, "lesson lacks independent evidence")

        confidence = round(len(supporting) / (len(supporting) + len(contrary) + 1), 6)
        episode_record_ids = tuple(sorted({item.episode_record_id for item in supporting}))
        signal_ids = tuple(sorted(item.signal_id for item in bucket))
        evidence_refs = tuple(
            sorted({digest for item in bucket for digest in item.evidence_refs})
        )
        counterexamples = tuple(
            Counterexample(
                item.signal_id,
                item.episode_record_id,
                item.evidence_refs,
                item.observed_at,
                f"recorded {item.kind.value} with outcome {item.outcome.value}"
                f" contrary to {dominant.value}",
            )
            for item in sorted(contrary, key=lambda item: (item.observed_at, item.signal_id))
        )

        valid_from = now
        valid_to = _render(_instant(now, "now") + timedelta(days=window))
        provenance = LessonProvenance(GENERATOR_IDENTITY, evaluator_id, signal_ids, roles)
        core = {
            "applicability": {
                "scope": applicability.scope,
                "subject_keys": list(applicability.subject_keys),
            },
            "confidence": confidence,
            "episode_record_ids": list(episode_record_ids),
            "error_class": error_class,
            "evaluator_id": evaluator_id,
            "evidence_refs": list(evidence_refs),
            "generator": GENERATOR_IDENTITY,
            "outcome": dominant.value,
            "signal_ids": list(signal_ids),
            "statement": statement,
            "valid_from": valid_from,
            "valid_to": valid_to,
        }
        lesson_id = "LESSON-" + canonical_digest(core).removeprefix("sha256:")[:20]
        return Lesson(
            lesson_id,
            statement,
            error_class,
            dominant,
            episode_record_ids,
            applicability,
            confidence,
            provenance,
            valid_from,
            valid_to,
            counterexamples,
        )

    def _require_independence(
        self, signals: tuple[LearningSignal, ...], reason: str
    ) -> None:
        episodes = {item.episode_record_id for item in signals}
        contexts = {item.context_key for item in signals}
        if (
            len(episodes) < self.policy.minimum_independent_episodes
            or len(contexts) < self.policy.minimum_distinct_contexts
        ):
            raise LearningDenied(reason)

    @staticmethod
    def _dominant_outcome(signals: tuple[LearningSignal, ...]) -> OutcomeClass:
        tally: dict[OutcomeClass, int] = {}
        for item in signals:
            tally[item.outcome] = tally.get(item.outcome, 0) + 1
        highest = max(tally.values())
        leaders = [outcome for outcome, count in tally.items() if count == highest]
        if len(leaders) != 1:
            raise LearningDenied("tied outcomes cannot yield a dominant lesson")
        return leaders[0]


def retain_counterexample(lesson: Lesson, counterexample: Counterexample) -> Lesson:
    """Append a counterexample and lower confidence; nothing is ever removed."""

    if not isinstance(lesson, Lesson) or not isinstance(counterexample, Counterexample):
        raise LearningDenied("counterexample retention requires a lesson record")
    if any(item.signal_id == counterexample.signal_id for item in lesson.counterexamples):
        raise LearningDenied("counterexample signal is already retained")
    retained = lesson.counterexamples + (counterexample,)
    supporting = len(lesson.episode_record_ids)
    confidence = round(
        lesson.confidence * supporting / (supporting + len(retained) + 1), 6
    )
    return replace(lesson, counterexamples=retained, confidence=confidence)


def record_dissent(lesson: Lesson, dissent: DissentRecord) -> Lesson:
    """Append a dissenting position without altering any other lesson field."""

    if not isinstance(lesson, Lesson) or not isinstance(dissent, DissentRecord):
        raise LearningDenied("dissent retention requires a lesson record")
    if any(
        item.role == dissent.role and item.position == dissent.position
        for item in lesson.dissent
    ):
        raise LearningDenied("dissent position is already recorded")
    return replace(lesson, dissent=lesson.dissent + (dissent,))


def lesson_memory_record(
    lesson: Lesson,
    *,
    content_ref: str,
    recorded_at: str,
    retention_policy: str = "governed-lesson",
) -> MemoryRecord:
    """Construct the durable form of a lesson without registering it anywhere."""

    if not isinstance(lesson, Lesson):
        raise LearningDenied("memory binding requires a lesson record")
    _text(content_ref, "content_ref")
    _instant(recorded_at, "recorded_at")
    _text(retention_policy, "retention_policy")
    return MemoryRecord(
        record_id=f"MEMORY-{lesson.lesson_id}",
        memory_class="lesson",
        scope=lesson.applicability.scope,
        subject_keys=lesson.applicability.subject_keys,
        content_ref=content_ref,
        source_refs=lesson.episode_record_ids,
        authority_level="internal",
        sensitivity="internal",
        valid_from=lesson.valid_from,
        valid_to=lesson.valid_to,
        recorded_at=recorded_at,
        available_at=recorded_at,
        state=MemoryState.ACTIVE,
        supersedes=lesson.episode_record_ids,
        superseded_by=(),
        evaluator_id=lesson.provenance.evaluator_id,
        outcome_refs=(lesson.digest,),
        retention_policy=retention_policy,
        digest_value=lesson.digest,
    )
