"""LEARN-500 — scoped, evidence-bound lesson generation.

Every signal in this module transcribes a fact that is already recorded in this
repository: either a healing outcome record committed under
``.autopilot/lessons`` in commit ``a5e4ce23a4710d991f9ef3b83b64a797d8321bee``
(its ``record_id`` is reused verbatim as the evidence digest), or a remediation
commit whose SHA, author time, and subject come from ``git log``.  No lesson in
these tests is hand-authored: statements are computed from the recorded signals
by :func:`derived_statement`, and every other lesson field is asserted against
the recorded evidence it must be derived from.
"""

from __future__ import annotations

import inspect
import tempfile
import unittest
from dataclasses import dataclass, fields, replace
from pathlib import Path

import hive_mind_os.brain_kernel.learning_runtime as learning_runtime
from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.contracts import MemoryRecord, MemoryState
from hive_mind_os.brain_kernel.learning_runtime import (
    Counterexample,
    DissentRecord,
    LearningDenied,
    LearningSignal,
    Lesson,
    LessonApplicability,
    LessonGenerator,
    LessonProvenance,
    OutcomeClass,
    SignalKind,
    lesson_memory_record,
    record_dissent,
    retain_counterexample,
)
from hive_mind_os.brain_kernel.memory import ConsolidationPolicy, MemoryArtifactStore

NOW = "2026-08-12T15:00:00Z"
EXPIRY_AT_DEFAULT_TTL = "2026-11-10T15:00:00Z"
EVALUATOR = "curator:learn-500-evaluator"

WEDGED = "node-wedged"
HEALER_LEARNING = "healer-learning-not-durable"
WAVE_EXECUTOR = "wave-executor-incomplete"

FORBIDDEN_SURFACE = frozenset(
    {"apply", "enforce", "promote", "mutate", "update_policy", "update_prompt", "set_champion"}
)


@dataclass(frozen=True, slots=True)
class RecordedFact:
    """A fact already recorded in repository history, not a fabricated fixture."""

    key: str
    source: str
    evidence_ref: str
    episode_record_id: str
    kind: SignalKind
    outcome: OutcomeClass
    error_class: str
    context_key: str
    observed_at: str


def _commit_evidence(sha: str) -> str:
    """Derive a stable evidence digest from a real 40-hex commit identity."""

    return canonical_digest({"commit": sha})


RECORDED_FACTS: tuple[RecordedFact, ...] = (
    # .autopilot/lessons/claim-defunct-expired-reap.jsonl (commit a5e4ce2):
    # verdict CLAIM_DEFUNCT, action reap, outcome UNBLOCKED for node MISSION-400.
    RecordedFact(
        "lesson.claim-defunct",
        "lesson-record",
        "sha256:b3f9cc530f081fff237ef6c5fddf456888dbdbea063210ff7b3c0e8251f25413",
        "MEMORY-MISSION-400.claim-defunct",
        SignalKind.OUTCOME,
        OutcomeClass.SUCCESS,
        WEDGED,
        "node:MISSION-400",
        "2026-08-12T11:15:00Z",
    ),
    # .autopilot/lessons/retry-quarantined-blockers-resolved-lift-quarantine.jsonl
    # (commit a5e4ce2): verdict RETRY_QUARANTINED, outcome UNBLOCKED.
    RecordedFact(
        "lesson.retry-quarantined",
        "lesson-record",
        "sha256:b381cc7036f19c2279347a748b72ac84e6039c3be9cb212a755279c2ef406a00",
        "MEMORY-MISSION-400.retry-quarantined",
        SignalKind.OUTCOME,
        OutcomeClass.SUCCESS,
        WEDGED,
        "node:MISSION-400",
        "2026-08-12T11:31:00Z",
    ),
    # 9117520 fix(autopilot): let a later session retire a dead worker's remote claim
    RecordedFact(
        "commit.retire-dead-claim",
        "commit",
        _commit_evidence("911752039f4111e1dc8284c1935ba58e20f03339"),
        "MEMORY-COMMIT.911752039f41",
        SignalKind.REPAIR,
        OutcomeClass.SUCCESS,
        WEDGED,
        "path:src/hive_mind_os",
        "2026-08-12T04:47:17-05:00",
    ),
    # aa62a9d fix(runbooks): make the MISSION-400 replay contract satisfiable
    RecordedFact(
        "commit.replay-contract-unsatisfiable",
        "commit",
        _commit_evidence("aa62a9df5df40f49ba0745709b0605fb72debfc4"),
        "MEMORY-COMMIT.aa62a9df5df4",
        SignalKind.REMAND,
        OutcomeClass.FAILURE,
        WEDGED,
        "path:docs/execution/runbooks",
        "2026-08-12T04:31:45-05:00",
    ),
    # 2eecea5 fix(runbooks): make MISSION-400's failed-candidate claim satisfiable
    RecordedFact(
        "commit.failed-candidate-unsatisfiable",
        "commit",
        _commit_evidence("2eecea5e34c988de5afd488a7e34c7c24f2ee5ba"),
        "MEMORY-COMMIT.2eecea5e34c9",
        SignalKind.REMAND,
        OutcomeClass.FAILURE,
        WEDGED,
        "path:docs/execution/runbooks",
        "2026-08-12T09:33:59-05:00",
    ),
    # 9c9d547 feat(autopilot): heal wedges from evidence instead of polling
    RecordedFact(
        "commit.heal-from-evidence",
        "commit",
        _commit_evidence("9c9d5472faa8efe2b335f1e9b90c94a893b10621"),
        "MEMORY-COMMIT.9c9d5472faa8",
        SignalKind.REPAIR,
        OutcomeClass.SUCCESS,
        HEALER_LEARNING,
        "path:src/hive_mind_os",
        "2026-08-12T07:39:49-05:00",
    ),
    # 6ded14f feat(autopilot): make the healer's learning durable, honest, committed
    RecordedFact(
        "commit.healer-learning-durable",
        "commit",
        _commit_evidence("6ded14f9c228d8bad1ca290ec72b874ebf25c578"),
        "MEMORY-COMMIT.6ded14f9c228",
        SignalKind.HUMAN_CORRECTION,
        OutcomeClass.PARTIAL,
        HEALER_LEARNING,
        "path:autopilot-state",
        "2026-08-12T09:05:53-05:00",
    ),
    # 5de7bbf feat(autopilot): implement the host adapter the wave executor never had
    RecordedFact(
        "commit.missing-host-adapter",
        "commit",
        _commit_evidence("5de7bbf22b66670aebbbbf16f443cffc79d5cfed"),
        "MEMORY-COMMIT.5de7bbf22b66",
        SignalKind.INCIDENT,
        OutcomeClass.FAILURE,
        WAVE_EXECUTOR,
        "path:src/hive_mind_os",
        "2026-08-12T05:04:28-05:00",
    ),
    # 7ec26c5 fix(autopilot): make the round gate test the checkout it is integrating
    RecordedFact(
        "commit.round-gate-wrong-tree",
        "commit",
        _commit_evidence("7ec26c540e211dfe06007259df90c2091c04034d"),
        "MEMORY-COMMIT.7ec26c540e21",
        SignalKind.REMAND,
        OutcomeClass.FAILURE,
        WAVE_EXECUTOR,
        "path:src/hive_mind_os",
        "2026-08-12T09:47:12-05:00",
    ),
)

FACTS_BY_KEY = {fact.key: fact for fact in RECORDED_FACTS}


def signal_from(fact: RecordedFact) -> LearningSignal:
    return LearningSignal(
        f"SIGNAL-{fact.key}",
        fact.kind,
        fact.episode_record_id,
        fact.outcome,
        fact.error_class,
        fact.context_key,
        (fact.evidence_ref,),
        fact.observed_at,
    )


def signals_for(error_class: str) -> tuple[LearningSignal, ...]:
    return tuple(
        signal_from(fact) for fact in RECORDED_FACTS if fact.error_class == error_class
    )


def signals_named(*keys: str) -> tuple[LearningSignal, ...]:
    return tuple(signal_from(FACTS_BY_KEY[key]) for key in keys)


def derived_statement(error_class: str, signals: tuple[LearningSignal, ...]) -> str:
    """Compose the lesson text strictly from what the recorded signals contain."""

    episodes = sorted({signal.episode_record_id for signal in signals})
    contexts = sorted({signal.context_key for signal in signals})
    kinds = sorted({signal.kind.value for signal in signals})
    return (
        f"error class {error_class} is attested by {len(episodes)} recorded episodes"
        f" across {len(contexts)} contexts via {'/'.join(kinds)} records"
    )


def wedge_lesson(
    generator: LessonGenerator | None = None,
    *,
    signals: tuple[LearningSignal, ...] | None = None,
    statement: str | None = None,
    **overrides: object,
) -> Lesson:
    engine = generator if generator is not None else LessonGenerator()
    used = signals if signals is not None else signals_for(WEDGED)
    arguments: dict[str, object] = {
        "statement": statement if statement is not None else derived_statement(WEDGED, used),
        "error_class": WEDGED,
        "applicability": LessonApplicability("mission", ("MISSION-400",)),
        "evaluator_id": EVALUATOR,
        "now": NOW,
        "roles": ("optimizer", "curator"),
    }
    arguments.update(overrides)
    return engine.generate(used, **arguments)  # type: ignore[arg-type]


class LessonGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.generator = LessonGenerator()
        self.signals = signals_for(WEDGED)

    def test_lesson_binds_episode_outcome_error_class_applicability_confidence_provenance_expiry(
        self,
    ) -> None:
        lesson = wedge_lesson(self.generator)

        for field in fields(Lesson):
            if field.name in {"counterexamples", "dissent"}:
                continue
            self.assertTrue(
                getattr(lesson, field.name) or getattr(lesson, field.name) == 0.0,
                f"{field.name} must be populated",
            )

        supporting = tuple(
            signal for signal in self.signals if signal.outcome is OutcomeClass.SUCCESS
        )
        contrary = tuple(
            signal for signal in self.signals if signal.outcome is not OutcomeClass.SUCCESS
        )
        self.assertEqual(len(supporting), 3)
        self.assertEqual(len(contrary), 2)

        # Every bound field is a function of the recorded signals.
        self.assertRegex(lesson.lesson_id, r"\ALESSON-[0-9a-f]{20}\Z")
        self.assertEqual(lesson.statement, derived_statement(WEDGED, self.signals))
        self.assertEqual(lesson.error_class, WEDGED)
        self.assertIs(lesson.outcome, OutcomeClass.SUCCESS)
        self.assertEqual(
            lesson.episode_record_ids,
            tuple(sorted({signal.episode_record_id for signal in supporting})),
        )
        self.assertEqual(lesson.applicability, LessonApplicability("mission", ("MISSION-400",)))
        self.assertEqual(lesson.confidence, round(3 / 6, 6))
        self.assertEqual(
            lesson.provenance,
            LessonProvenance(
                "learning_runtime",
                EVALUATOR,
                tuple(sorted(signal.signal_id for signal in self.signals)),
                ("optimizer", "curator"),
            ),
        )
        self.assertEqual(lesson.valid_from, NOW)
        self.assertIsNotNone(lesson.valid_to)
        self.assertEqual(lesson.valid_to, EXPIRY_AT_DEFAULT_TTL)
        self.assertGreater(lesson.valid_to, lesson.valid_from)
        self.assertRegex(lesson.digest, r"\Asha256:[0-9a-f]{64}\Z")

    def test_generation_requires_independent_episodes_and_contexts(self) -> None:
        single_episode = signals_named("lesson.claim-defunct")
        with self.assertRaises(LearningDenied) as one_episode:
            wedge_lesson(self.generator, signals=single_episode)
        self.assertIn("independent evidence", str(one_episode.exception))

        # Both wave-executor facts are recorded against src/hive_mind_os.
        single_context = signals_for(WAVE_EXECUTOR)
        self.assertEqual(len({signal.episode_record_id for signal in single_context}), 2)
        self.assertEqual(len({signal.context_key for signal in single_context}), 1)
        with self.assertRaises(LearningDenied) as one_context:
            wedge_lesson(
                self.generator,
                signals=single_context,
                statement=derived_statement(WAVE_EXECUTOR, single_context),
                error_class=WAVE_EXECUTOR,
            )
        self.assertIn("independent evidence", str(one_context.exception))

    def test_lesson_id_and_digest_are_deterministic(self) -> None:
        first = wedge_lesson(self.generator)
        second = wedge_lesson(LessonGenerator(policy=ConsolidationPolicy(), default_ttl_days=90))
        self.assertEqual(first.lesson_id, second.lesson_id)
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(first, second)

    def test_lesson_id_is_bound_to_evidence_digests(self) -> None:
        baseline = wedge_lesson(self.generator)
        altered = tuple(
            replace(signal, evidence_refs=("sha256:" + "a" * 64,))
            if signal.signal_id == "SIGNAL-lesson.claim-defunct"
            else signal
            for signal in self.signals
        )
        rebound = wedge_lesson(self.generator, signals=altered, statement=baseline.statement)
        self.assertEqual(rebound.episode_record_ids, baseline.episode_record_ids)
        self.assertEqual(rebound.provenance.signal_ids, baseline.provenance.signal_ids)
        self.assertNotEqual(rebound.lesson_id, baseline.lesson_id)
        self.assertNotEqual(rebound.digest, baseline.digest)

    def test_lesson_has_no_policy_prompt_or_champion_mutation_surface(self) -> None:
        lesson = wedge_lesson(self.generator)
        for holder in (Lesson, LessonGenerator, lesson, self.generator):
            for name in FORBIDDEN_SURFACE:
                self.assertFalse(
                    hasattr(holder, name), f"{holder!r} exposes a mutation surface {name}"
                )
        source = inspect.getsource(learning_runtime)
        for token in ("PolicyEngine", "prompt_registry", "LearningPromotionGate"):
            self.assertNotIn(token, source)

    def test_secretlike_statement_rejected(self) -> None:
        with self.assertRaises(LearningDenied):
            wedge_lesson(
                self.generator,
                statement="rotate the runner: api_key: sk_live_9f3cfb3a2b1c4d5e",
            )

    def test_nonpositive_ttl_days_rejected(self) -> None:
        for window in (0, -1):
            with self.assertRaises(LearningDenied):
                wedge_lesson(self.generator, ttl_days=window)

    def test_applicability_scope_outside_memory_vocabulary_rejected(self) -> None:
        with self.assertRaises(LearningDenied):
            LessonApplicability("policy", ("MISSION-400",))
        with self.assertRaises(LearningDenied):
            LessonApplicability("mission", ())


class OutcomeAttributionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.generator = LessonGenerator()

    def test_attribute_groups_signals_by_error_class(self) -> None:
        every = tuple(signal_from(fact) for fact in RECORDED_FACTS)
        buckets = self.generator.attribute(every, now=NOW)
        self.assertEqual(set(buckets), {WEDGED, HEALER_LEARNING, WAVE_EXECUTOR})
        self.assertEqual(len(buckets[WEDGED]), 5)
        self.assertEqual(len(buckets[HEALER_LEARNING]), 2)
        self.assertEqual(len(buckets[WAVE_EXECUTOR]), 2)
        for error_class, bucket in buckets.items():
            self.assertTrue(all(signal.error_class == error_class for signal in bucket))
            self.assertEqual(
                bucket,
                tuple(sorted(bucket, key=lambda item: (item.observed_at, item.signal_id))),
            )

    def test_future_dated_signal_rejected(self) -> None:
        late = signal_from(FACTS_BY_KEY["lesson.retry-quarantined"])
        with self.assertRaises(LearningDenied) as denied:
            self.generator.attribute((late,), now="2026-08-12T11:14:59Z")
        self.assertIn("future-dated", str(denied.exception))
        self.assertEqual(len(self.generator.attribute((late,), now="2026-08-12T11:31:00Z")), 1)

    def test_duplicate_signal_ids_rejected(self) -> None:
        repeated = signals_named("commit.retire-dead-claim", "commit.retire-dead-claim")
        with self.assertRaises(LearningDenied) as denied:
            self.generator.attribute(repeated, now=NOW)
        self.assertIn("duplicate signal id", str(denied.exception))

    def test_tied_outcomes_rejected(self) -> None:
        tied = signals_for(HEALER_LEARNING)
        outcomes = {signal.outcome for signal in tied}
        self.assertEqual(len(outcomes), len(tied))  # one success, one partial
        with self.assertRaises(LearningDenied) as denied:
            self.generator.generate(
                tied,
                statement=derived_statement(HEALER_LEARNING, tied),
                error_class=HEALER_LEARNING,
                applicability=LessonApplicability("repository", ("hive-mind-os",)),
                evaluator_id=EVALUATOR,
                now=NOW,
            )
        self.assertIn("tied outcomes", str(denied.exception))

    def test_contrary_outcome_signals_become_counterexamples_at_birth(self) -> None:
        lesson = wedge_lesson(self.generator)
        contrary = tuple(
            signal
            for signal in sorted(
                signals_for(WEDGED), key=lambda item: (item.observed_at, item.signal_id)
            )
            if signal.outcome is not OutcomeClass.SUCCESS
        )
        self.assertEqual(len(lesson.counterexamples), 2)
        self.assertEqual(
            tuple(item.signal_id for item in lesson.counterexamples),
            tuple(signal.signal_id for signal in contrary),
        )
        for retained, signal in zip(lesson.counterexamples, contrary):
            self.assertEqual(retained.episode_record_id, signal.episode_record_id)
            self.assertEqual(retained.evidence_refs, signal.evidence_refs)
            self.assertEqual(retained.observed_at, signal.observed_at)
            self.assertIn(signal.outcome.value, retained.note)
            self.assertNotIn(retained.episode_record_id, lesson.episode_record_ids)

    def test_signal_requires_evidence_refs_and_valid_episode_id(self) -> None:
        fact = FACTS_BY_KEY["commit.retire-dead-claim"]
        with self.assertRaises(LearningDenied):
            LearningSignal(
                "SIGNAL-x", fact.kind, fact.episode_record_id, fact.outcome,
                fact.error_class, fact.context_key, (), fact.observed_at,
            )
        with self.assertRaises(LearningDenied):
            LearningSignal(
                "SIGNAL-x", fact.kind, "EPISODE-911752", fact.outcome,
                fact.error_class, fact.context_key, (fact.evidence_ref,), fact.observed_at,
            )
        with self.assertRaises(LearningDenied):
            LearningSignal(
                "SIGNAL-x", fact.kind, fact.episode_record_id, fact.outcome,
                fact.error_class, fact.context_key, ("911752039f41",), fact.observed_at,
            )
        with self.assertRaises(LearningDenied):
            LearningSignal(
                "SIGNAL-x", fact.kind, fact.episode_record_id, fact.outcome,
                fact.error_class, fact.context_key, (fact.evidence_ref,), "2026-08-12T04:47:17",
            )

    def test_empty_signal_batch_rejected(self) -> None:
        with self.assertRaises(LearningDenied):
            self.generator.attribute((), now=NOW)
        with self.assertRaises(LearningDenied):
            wedge_lesson(self.generator, signals=())


class CounterexampleRetentionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.artifacts = MemoryArtifactStore(Path(self.temporary.name))
        self.generator = LessonGenerator()
        self.lesson = wedge_lesson(self.generator)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def counterexample_from(key: str, note: str) -> Counterexample:
        fact = FACTS_BY_KEY[key]
        return Counterexample(
            f"SIGNAL-{key}",
            fact.episode_record_id,
            (fact.evidence_ref,),
            fact.observed_at,
            note,
        )

    def test_retain_counterexample_appends_and_lowers_confidence(self) -> None:
        addition = self.counterexample_from(
            "commit.missing-host-adapter",
            "recorded incident with outcome failure contrary to success",
        )
        updated = retain_counterexample(self.lesson, addition)

        self.assertIsNot(updated, self.lesson)
        self.assertEqual(len(self.lesson.counterexamples), 2)
        self.assertEqual(self.lesson.confidence, 0.5)
        self.assertEqual(len(updated.counterexamples), 3)
        self.assertLess(updated.confidence, self.lesson.confidence)
        self.assertEqual(updated.confidence, round(0.5 * 3 / (3 + 3 + 1), 6))
        self.assertEqual(updated.counterexamples[-1], addition)
        self.assertEqual(updated.lesson_id, self.lesson.lesson_id)

    def test_counterexamples_never_removed(self) -> None:
        first = self.counterexample_from("commit.missing-host-adapter", "contrary incident")
        second = self.counterexample_from("commit.round-gate-wrong-tree", "contrary remand")
        updated = retain_counterexample(retain_counterexample(self.lesson, first), second)
        self.assertEqual(
            tuple(item.signal_id for item in updated.counterexamples),
            tuple(item.signal_id for item in self.lesson.counterexamples)
            + (first.signal_id, second.signal_id),
        )
        self.assertEqual(len(updated.counterexamples), 4)
        self.assertEqual(len(self.lesson.counterexamples), 2)

    def test_duplicate_counterexample_rejected(self) -> None:
        addition = self.counterexample_from("commit.missing-host-adapter", "contrary incident")
        updated = retain_counterexample(self.lesson, addition)
        with self.assertRaises(LearningDenied):
            retain_counterexample(updated, addition)
        born = self.lesson.counterexamples[0]
        with self.assertRaises(LearningDenied):
            retain_counterexample(self.lesson, born)

    def test_record_dissent_appends_and_preserves_lesson_fields(self) -> None:
        dissent = DissentRecord(
            "curator",
            "the src/hive_mind_os repair may not generalise to runbook contracts",
            NOW,
        )
        updated = record_dissent(self.lesson, dissent)
        self.assertEqual(self.lesson.dissent, ())
        self.assertEqual(updated.dissent, (dissent,))
        for field in fields(Lesson):
            if field.name == "dissent":
                continue
            self.assertEqual(getattr(updated, field.name), getattr(self.lesson, field.name))
        self.assertEqual(updated.digest != self.lesson.digest, True)
        with self.assertRaises(LearningDenied):
            record_dissent(updated, dissent)

    def test_lesson_memory_record_maps_to_valid_memory_record(self) -> None:
        artifact = self.artifacts.put(self.lesson.statement, content_kind="lesson")
        record = lesson_memory_record(
            self.lesson, content_ref=artifact.digest, recorded_at=NOW
        )
        self.assertIsInstance(record, MemoryRecord)
        self.assertEqual(record.record_id, f"MEMORY-{self.lesson.lesson_id}")
        self.assertEqual(record.memory_class, "lesson")
        self.assertEqual(record.scope, "mission")
        self.assertEqual(record.subject_keys, ("MISSION-400",))
        self.assertEqual(record.content_ref, artifact.digest)
        self.assertEqual(record.source_refs, self.lesson.episode_record_ids)
        self.assertEqual(record.supersedes, self.lesson.episode_record_ids)
        self.assertEqual(record.superseded_by, ())
        self.assertIs(record.state, MemoryState.ACTIVE)
        self.assertEqual(record.evaluator_id, EVALUATOR)
        self.assertEqual(record.outcome_refs, (self.lesson.digest,))
        self.assertEqual(record.digest_value, self.lesson.digest)
        self.assertIsNotNone(record.valid_to)
        self.assertEqual(record.valid_to, EXPIRY_AT_DEFAULT_TTL)
        self.assertEqual(record.to_document()["digest"], self.lesson.digest)
        # Reconstruct to prove MemoryRecord.__post_init__ accepts the mapping.
        MemoryRecord(*[getattr(record, field.name) for field in fields(MemoryRecord)])

    def test_confidence_stays_bounded_after_many_counterexamples(self) -> None:
        fact = FACTS_BY_KEY["commit.round-gate-wrong-tree"]
        lesson = self.lesson
        previous = lesson.confidence
        for index in range(25):
            lesson = retain_counterexample(
                lesson,
                Counterexample(
                    f"SIGNAL-{fact.key}.{index}",
                    fact.episode_record_id,
                    (fact.evidence_ref,),
                    fact.observed_at,
                    f"repeat contrary observation {index}",
                ),
            )
            self.assertLessEqual(lesson.confidence, previous)
            self.assertGreaterEqual(lesson.confidence, 0.0)
            self.assertLessEqual(lesson.confidence, 1.0)
            previous = lesson.confidence
        self.assertEqual(len(lesson.counterexamples), 27)


if __name__ == "__main__":
    unittest.main()
