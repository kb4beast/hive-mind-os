"""Adversarial fixtures proving governed memory and learning resist poisoning.

Every fixture below constructs a real poisoning attempt against a real kernel
surface (``hive_mind_os.brain_kernel.memory`` and
``hive_mind_os.brain_kernel.learning_runtime``) and asserts the surface refuses
or contains it.  Rejection assertions are paired with a positive control so a
fixture cannot pass by breaking the surface outright.  No fixture runs git, a
subprocess, or the network; all filesystem work happens in a temporary
directory.
"""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from hive_mind_os.brain_kernel.contracts import MemoryRecord, MemoryState
from hive_mind_os.brain_kernel.learning_runtime import (
    GENERATOR_IDENTITY,
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
from hive_mind_os.brain_kernel.memory import (
    ConsolidationPolicy,
    MemoryAccess,
    MemoryArtifactStore,
    MemoryCatalog,
    MemoryCatalogStore,
    MemoryDenied,
    RetrievalRequest,
)

DIGEST = "sha256:" + "0" * 64
OTHER_DIGEST = "sha256:" + "1" * 64
TIME = "2026-08-07T12:00:00Z"  # baseline instant
SOON = "2026-08-08T12:00:00Z"  # +1 day
LATER = "2026-08-09T12:00:00Z"  # +2 days
BEYOND = "2026-08-10T12:00:00Z"  # +3 days


class _PoisoningFixture(unittest.TestCase):
    """Local replica of the kernel memory fixture; sibling modules are never imported."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.artifacts = MemoryArtifactStore(self.root)
        self.catalog = MemoryCatalog(self.artifacts)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def record(
        self,
        record_id: str,
        body: str,
        *,
        memory_class: str = "fact",
        scope: str = "mission",
        subject_keys: tuple[str, ...] = ("MISSION-one",),
        source_refs: tuple[str, ...] = ("SRC-one",),
        valid_from: str = TIME,
        valid_to: str | None = None,
        available_at: str = TIME,
        supersedes: tuple[str, ...] = (),
        outcome_refs: tuple[str, ...] = (),
        evaluator_id: str | None = None,
        sensitivity: str = "internal",
    ) -> MemoryRecord:
        artifact = self.artifacts.put(body)
        return MemoryRecord(
            record_id,
            memory_class,
            scope,
            subject_keys,
            artifact.digest,
            source_refs,
            "verified",
            sensitivity,
            valid_from,
            valid_to,
            TIME,
            available_at,
            MemoryState.ACTIVE,
            supersedes,
            (),
            evaluator_id,
            outcome_refs,
            "retain",
            DIGEST,
        )

    @staticmethod
    def access(roles: tuple[str, ...] = ("builder",)) -> MemoryAccess:
        return MemoryAccess(roles, ("internal",), True)

    def request(
        self,
        *,
        mission_id: str = "MISSION-one",
        work_id: str = "WORK-one",
        role: str = "builder",
        query: str = "",
        now: str = SOON,
    ) -> RetrievalRequest:
        return RetrievalRequest(mission_id, work_id, role, query, now, ("internal",))

    def active_ids(self, request: RetrievalRequest | None = None) -> tuple[str, ...]:
        chosen = self.request() if request is None else request
        return tuple(
            entry.record.record_id for entry in self.catalog.active_records(chosen)
        )

    def ranked_ids(self, request: RetrievalRequest) -> tuple[str, ...]:
        return tuple(item.entry.record.record_id for item in self.catalog.rank(request))


class MemoryPoisoningSuite(_PoisoningFixture):
    """required_tests: memory-poisoning-suite."""

    def test_secret_and_transcript_bodies_are_rejected(self) -> None:
        # Positive control: ordinary evidence enters the store and reads back.
        artifact = self.artifacts.put("ordinary retained evidence")
        self.assertEqual("ordinary retained evidence", self.artifacts.get(artifact.digest))
        # Poison: smuggle a credential into durable memory as evidence.
        with self.assertRaisesRegex(MemoryDenied, "secret-like data"):
            self.artifacts.put("api_key = AKIAIOSFODNN7EXAMPLE")
        with self.assertRaisesRegex(MemoryDenied, "secret-like data"):
            self.artifacts.put("ghp_abcdefghijklmnopqrstuvwxyz0123456789")
        # Poison: launder an unverified model transcript into durable memory.
        with self.assertRaisesRegex(MemoryDenied, "raw transcripts"):
            self.artifacts.put("the model asserted the fix is safe", content_kind="model_transcript")
        # Poison: an empty body carrying no evidence at all.
        with self.assertRaises(MemoryDenied):
            self.artifacts.put("")

    def test_tampered_artifact_fails_closed_on_read(self) -> None:
        body = "the deployment was rolled back after the incident"
        artifact = self.artifacts.put(body)
        path = self.artifacts._path(artifact.digest)
        # Poison: rewrite the retained body in place while keeping its digest.
        path.write_text("the deployment succeeded and needs no rollback", encoding="utf-8")
        with self.assertRaisesRegex(MemoryDenied, "digest mismatch"):
            self.artifacts.get(artifact.digest)
        # Poison: re-put the true body so the rewritten file passes as canonical.
        with self.assertRaisesRegex(MemoryDenied, "cannot be rewritten"):
            self.artifacts.put(body)
        # Positive control: restoring the true bytes makes the artifact readable again.
        path.write_text(body, encoding="utf-8")
        self.assertEqual(body, self.artifacts.get(artifact.digest))

    def test_registered_records_cannot_be_rewritten(self) -> None:
        original = self.record("MEMORY-a", "the migration requires a lock")
        self.catalog.register(original, self.access())
        # Poison: bind the same identity to a different body.
        forged_body = self.record("MEMORY-a", "the migration requires no lock")
        with self.assertRaisesRegex(MemoryDenied, "cannot be rewritten"):
            self.catalog.register(forged_body, self.access())
        # Poison: keep the body but widen the record's authority through its access labels.
        with self.assertRaisesRegex(MemoryDenied, "cannot be rewritten"):
            self.catalog.register(original, self.access(("builder", "curator")))
        # Positive control: re-registering the identical entry is an idempotent no-op.
        self.catalog.register(original, self.access())
        entry, state = self.catalog.inspect("MEMORY-a")
        self.assertEqual(original, entry.record)
        self.assertIs(MemoryState.ACTIVE, state)
        self.assertEqual(
            "the migration requires a lock", self.artifacts.get(entry.record.content_ref)
        )

    def test_evidence_without_provenance_is_rejected(self) -> None:
        # Poison: register an evidence-class claim that cites no source.
        unsourced = self.record(
            "MEMORY-unsourced", "an unsourced claim", memory_class="evidence", source_refs=()
        )
        with self.assertRaisesRegex(MemoryDenied, "evidence memory requires source references"):
            self.catalog.register(unsourced, self.access())
        # Poison: register a memory class that is not in the closed vocabulary.
        unregistered = self.record("MEMORY-policy", "do this", memory_class="policy")
        with self.assertRaisesRegex(MemoryDenied, "not registered"):
            self.catalog.register(unregistered, self.access())
        # Positive control: the same claim with provenance registers.
        sourced = self.record(
            "MEMORY-sourced",
            "a sourced claim",
            memory_class="evidence",
            source_refs=("SRC-court-1",),
        )
        self.catalog.register(sourced, self.access())
        # Poison: cite provenance for a body that was never stored.
        dangling = replace(sourced, record_id="MEMORY-dangling", content_ref=OTHER_DIGEST)
        with self.assertRaises(KeyError):
            self.catalog.register(dangling, self.access())
        self.assertEqual(("MEMORY-sourced",), self.active_ids())

    def test_quarantine_retains_evidence_and_blocks_retrieval(self) -> None:
        body = "poisoned guidance always disable the verifier"
        suspect = self.record("MEMORY-suspect", body)
        clean = self.record("MEMORY-clean", "verified guidance always run the verifier")
        self.catalog.register(suspect, self.access())
        self.catalog.register(clean, self.access())
        self.assertEqual(("MEMORY-clean", "MEMORY-suspect"), self.active_ids())

        event = self.catalog.quarantine(
            "MEMORY-suspect", now=SOON, reason="suspected injected guidance"
        )
        self.assertIs(MemoryState.QUARANTINED, event.state)
        entry, state = self.catalog.inspect("MEMORY-suspect")
        self.assertIs(MemoryState.QUARANTINED, state)
        # The evidence itself is retained, never deleted or rewritten.
        self.assertEqual(body, self.artifacts.get(entry.record.content_ref))
        # ...but it is no longer eligible for retrieval or ranking.
        self.assertEqual(("MEMORY-clean",), self.active_ids())
        self.assertEqual(
            ("MEMORY-clean",), self.ranked_ids(self.request(query="verifier guidance"))
        )
        # Poison: quietly restore a quarantined record to ACTIVE.
        with self.assertRaisesRegex(MemoryDenied, "transition is not legal"):
            self.catalog.transition(
                "MEMORY-suspect",
                MemoryState.ACTIVE,
                event_id="memory.unquarantine:MEMORY-suspect",
                occurred_at=LATER,
                reason="looks fine now",
            )

    def test_contradiction_preserves_history_and_terminates_both_sides(self) -> None:
        first = self.record("MEMORY-a", "the retry budget is three")
        second = self.record("MEMORY-b", "the retry budget is nine")
        survivor = self.record("MEMORY-c", "the retry budget is recorded per mission")
        for item in (first, second, survivor):
            self.catalog.register(item, self.access())

        conflict, events = self.catalog.contradict(
            ("MEMORY-a", "MEMORY-b"), now=SOON, reason="incompatible retry budgets"
        )
        self.assertEqual(("MEMORY-a", "MEMORY-b"), conflict.record_ids)
        self.assertEqual(2, len(events))
        for record_id in ("MEMORY-a", "MEMORY-b"):
            entry, state = self.catalog.inspect(record_id)
            self.assertIs(MemoryState.CONTRADICTED, state)
            # Neither side was overwritten: both bodies are still retained.
            self.assertTrue(self.artifacts.get(entry.record.content_ref))
        self.assertEqual(
            (conflict.conflict_id,), self.catalog.conflicts_for(("MEMORY-a", "MEMORY-b"))
        )
        # Positive control: only the uncontradicted record survives retrieval.
        self.assertEqual(("MEMORY-c",), self.active_ids())
        self.assertEqual(("MEMORY-c",), self.ranked_ids(self.request(query="retry budget")))

    def test_single_record_contradiction_is_rejected(self) -> None:
        self.catalog.register(self.record("MEMORY-a", "the retry budget is three"), self.access())
        self.catalog.register(self.record("MEMORY-b", "the retry budget is nine"), self.access())
        # Poison: retire an inconvenient record by "contradicting" it against nothing.
        with self.assertRaisesRegex(ValueError, "at least two distinct records"):
            self.catalog.contradict(("MEMORY-a",), now=SOON, reason="I disagree")
        # Poison: pad a single record into a quorum by repeating it.
        with self.assertRaisesRegex(ValueError, "at least two distinct records"):
            self.catalog.contradict(("MEMORY-a", "MEMORY-a"), now=SOON, reason="I disagree twice")
        self.assertIs(MemoryState.ACTIVE, self.catalog.inspect("MEMORY-a")[1])
        # Positive control: two genuinely distinct records do contradict.
        self.catalog.contradict(("MEMORY-a", "MEMORY-b"), now=SOON, reason="incompatible budgets")
        self.assertIs(MemoryState.CONTRADICTED, self.catalog.inspect("MEMORY-a")[1])

    def test_unresolved_conflict_reduces_rank_confidence(self) -> None:
        body = "pin the transitive dependency set"
        for record_id in ("MEMORY-a", "MEMORY-b", "MEMORY-c"):
            self.catalog.register(self.record(record_id, body), self.access())
        baseline = {item.entry.record.record_id: item for item in self.catalog.rank(
            self.request(query=body)
        )}
        self.assertEqual(3, len(baseline))
        self.assertEqual(
            {0.0}, {item.terms.unresolved_conflict_penalty for item in baseline.values()}
        )

        # Poison: assert a contradiction to knock a rival record out of retrieval.
        # The kernel keeps every record ACTIVE and reduces confidence instead.
        self.catalog.record_conflict(
            ("MEMORY-a", "MEMORY-b"), reason="unresolved dissent", recorded_at=SOON
        )
        for record_id in ("MEMORY-a", "MEMORY-b"):
            self.assertIs(MemoryState.ACTIVE, self.catalog.inspect(record_id)[1])
        ranked = self.catalog.rank(self.request(query=body))
        scores = {item.entry.record.record_id: item for item in ranked}
        self.assertEqual(3, len(scores), "conflicted history must not be dropped")
        self.assertEqual(1.0, scores["MEMORY-a"].terms.unresolved_conflict_penalty)
        self.assertEqual(1.0, scores["MEMORY-b"].terms.unresolved_conflict_penalty)
        self.assertEqual(0.0, scores["MEMORY-c"].terms.unresolved_conflict_penalty)
        for record_id in ("MEMORY-a", "MEMORY-b"):
            self.assertAlmostEqual(
                0.18,
                scores["MEMORY-c"].score - scores[record_id].score,
                places=12,
            )
            self.assertLess(scores[record_id].score, baseline[record_id].score)
        self.assertEqual(
            ("MEMORY-c", "MEMORY-a", "MEMORY-b"),
            tuple(item.entry.record.record_id for item in ranked),
        )

    def test_snapshot_tamper_fails_closed(self) -> None:
        self.catalog.register(self.record("MEMORY-a", "retained adverse finding"), self.access())
        self.catalog.quarantine("MEMORY-a", now=SOON, reason="quarantine-reason-zulu")
        store = MemoryCatalogStore(self.root)
        digest = store.persist(self.catalog)
        # Positive control: the untouched snapshot restores to the same projection.
        self.assertEqual(self.catalog.snapshot().digest(), store.restore(digest).snapshot().digest())

        path = store._path(digest)
        original = path.read_text(encoding="utf-8")
        self.assertIn("quarantine-reason-zulu", original)
        # Poison: rewrite retained lifecycle history inside a still-parseable snapshot.
        path.write_text(original.replace("quarantine-reason-zulu", "quarantine-reason-zulv"), encoding="utf-8")
        with self.assertRaisesRegex(MemoryDenied, "snapshot digest mismatch"):
            store.restore(digest)
        # Positive control: restoring the true bytes restores the snapshot again.
        path.write_text(original, encoding="utf-8")
        self.assertEqual(self.catalog.snapshot().digest(), store.restore(digest).snapshot().digest())


class StaleEvidenceSuite(_PoisoningFixture):
    """required_tests: stale-evidence-suite."""

    def test_expiry_is_deterministic_and_terminal(self) -> None:
        self.catalog.register(
            self.record("MEMORY-short", "short lived guidance", valid_to=SOON), self.access()
        )
        self.catalog.register(self.record("MEMORY-durable", "durable guidance"), self.access())
        self.assertEqual(("MEMORY-durable", "MEMORY-short"), self.active_ids())

        events = self.catalog.expire(now=LATER)
        self.assertEqual(("MEMORY-short",), tuple(event.record_id for event in events))
        self.assertEqual((MemoryState.EXPIRED,), tuple(event.state for event in events))
        self.assertIs(MemoryState.EXPIRED, self.catalog.inspect("MEMORY-short")[1])
        # Poison: run expiry again to mint a second, differently-dated history for the record.
        self.assertEqual((), self.catalog.expire(now=LATER))
        self.assertEqual((), self.catalog.expire(now=BEYOND))
        self.assertEqual(1, len(self.catalog.lifecycle_events()))
        # Poison: revive expired guidance by transitioning it back to ACTIVE.
        with self.assertRaisesRegex(MemoryDenied, "transition is not legal"):
            self.catalog.transition(
                "MEMORY-short",
                MemoryState.ACTIVE,
                event_id="memory.revive:MEMORY-short",
                occurred_at=BEYOND,
                reason="still useful",
            )
        self.assertEqual(("MEMORY-durable",), self.active_ids(self.request(now=LATER)))

    def test_expired_and_embargoed_records_are_not_retrievable(self) -> None:
        self.catalog.register(self.record("MEMORY-control", "current guidance"), self.access())
        self.catalog.register(
            self.record("MEMORY-past", "elapsed guidance", valid_to=SOON), self.access()
        )
        self.catalog.register(
            self.record("MEMORY-embargoed", "embargoed guidance", available_at=LATER), self.access()
        )
        self.catalog.register(
            self.record("MEMORY-notyet", "not yet valid guidance", valid_from=LATER), self.access()
        )
        # Poison: cite guidance that is embargoed or not yet valid at the query instant.
        # `MEMORY-past` is the positive control here: its window is still open at SOON.
        self.assertEqual(
            ("MEMORY-control", "MEMORY-past"), self.active_ids(self.request(now=SOON))
        )
        # Poison: cite guidance whose validity window already closed. `_eligible` refuses
        # it on `valid_to` alone, before any `expire` fact has been appended.
        self.assertEqual((), self.catalog.lifecycle_events())
        # Positive control at the same instant: the embargoed and not-yet-valid records
        # become eligible once their boundaries pass, so the SOON exclusion above is the
        # availability gate and not an unrelated filter.
        self.assertEqual(
            ("MEMORY-control", "MEMORY-embargoed", "MEMORY-notyet"),
            self.active_ids(self.request(now=LATER)),
        )
        self.assertEqual((), self.catalog.lifecycle_events())

    def test_stale_evidence_ranks_below_fresh_evidence(self) -> None:
        body = "roll forward through the migration"
        self.catalog.register(self.record("MEMORY-fresh", body, valid_to=LATER), self.access())
        self.catalog.register(
            self.record("MEMORY-stale", body, valid_to="2026-08-08T13:00:00Z"), self.access()
        )
        ranked = self.catalog.rank(self.request(query=body))
        scores = {item.entry.record.record_id: item for item in ranked}
        self.assertEqual(2, len(scores))
        # Both are eligible at SOON, so this is a confidence ordering, not a filter.
        self.assertLess(
            scores["MEMORY-stale"].terms.freshness_score,
            scores["MEMORY-fresh"].terms.freshness_score,
        )
        self.assertLess(scores["MEMORY-stale"].score, scores["MEMORY-fresh"].score)
        self.assertEqual(
            ("MEMORY-fresh", "MEMORY-stale"),
            tuple(item.entry.record.record_id for item in ranked),
        )

    def test_scope_prevents_cross_mission_reuse(self) -> None:
        # Every record grants both roles, so each exclusion below is the scope filter
        # rather than the access-role filter.
        both = self.access(("builder", "curator"))
        self.catalog.register(self.record("MEMORY-mission", "mission local finding"), both)
        self.catalog.register(
            self.record(
                "MEMORY-work",
                "work local finding",
                scope="work_item",
                subject_keys=("WORK-one",),
            ),
            both,
        )
        self.catalog.register(
            self.record(
                "MEMORY-role", "role local finding", scope="role", subject_keys=("builder",)
            ),
            both,
        )
        # Positive control: each record is retrievable inside its own scope.
        self.assertEqual(
            ("MEMORY-mission", "MEMORY-role", "MEMORY-work"),
            self.active_ids(self.request()),
        )
        # Poison: reuse a mission-scoped finding as a general rule on another mission.
        self.assertEqual(
            ("MEMORY-role", "MEMORY-work"),
            self.active_ids(self.request(mission_id="MISSION-two")),
        )
        # Poison: reuse a work-item finding on an unrelated work item.
        self.assertEqual(
            ("MEMORY-mission", "MEMORY-role"),
            self.active_ids(self.request(work_id="WORK-two")),
        )
        # Poison: reuse a role-scoped finding from a different role that holds access.
        self.assertEqual(
            ("MEMORY-mission",),
            self.active_ids(self.request(role="curator", work_id="WORK-two")),
        )


class OvergeneralizationSuite(_PoisoningFixture):
    """required_tests: overgeneralization-suite."""

    def episode(self, record_id: str, body: str, **overrides: object) -> MemoryRecord:
        values: dict[str, object] = {
            "memory_class": "episode",
            "outcome_refs": ("OUT-1",),
        }
        values.update(overrides)
        return self.record(record_id, body, **values)  # type: ignore[arg-type]

    def lesson(self, supersedes: tuple[str, ...], **overrides: object) -> MemoryRecord:
        values: dict[str, object] = {
            "memory_class": "lesson",
            "supersedes": supersedes,
            "evaluator_id": "EVAL-court-1",
            "outcome_refs": ("OUT-1",),
            "valid_to": LATER,
        }
        values.update(overrides)
        return self.record("MEMORY-lesson", "always pin deps", **values)  # type: ignore[arg-type]

    def _register_two_episodes(self) -> tuple[str, ...]:
        support = ("MEMORY-e1", "MEMORY-e2")
        self.catalog.register(self.episode("MEMORY-e1", "first episode"), self.access())
        self.catalog.register(self.episode("MEMORY-e2", "second episode"), self.access())
        return support

    def _keys(self, support: tuple[str, ...]) -> dict[str, str]:
        return {record_id: f"ctx-{index}" for index, record_id in enumerate(support)}

    def test_unproven_lesson_is_rejected(self) -> None:
        support = self._register_two_episodes()
        keys = self._keys(support)
        # Poison: promote a lesson that no independent evaluator ever approved.
        with self.assertRaisesRegex(MemoryDenied, "complete independent approval"):
            self.catalog.consolidate(
                self.lesson(support, evaluator_id=None),
                self.access(),
                supporting_record_ids=support,
                independence_keys=keys,
                now=SOON,
                reason="promotion",
            )
        # Poison: promote a lesson bound to no measured outcome.
        with self.assertRaisesRegex(MemoryDenied, "complete independent approval"):
            self.catalog.consolidate(
                self.lesson(support, outcome_refs=()),
                self.access(),
                supporting_record_ids=support,
                independence_keys=keys,
                now=SOON,
                reason="promotion",
            )
        # Poison: cite two episodes while the lesson itself only supersedes one, so the
        # promoted claim is broader than the evidence it retires.
        with self.assertRaisesRegex(MemoryDenied, "complete independent approval"):
            self.catalog.consolidate(
                self.lesson(("MEMORY-e1",)),
                self.access(),
                supporting_record_ids=support,
                independence_keys=keys,
                now=SOON,
                reason="promotion",
            )
        # Poison: relabel a bare opinion as the promoted lesson.
        with self.assertRaisesRegex(MemoryDenied, "complete independent approval"):
            self.catalog.consolidate(
                self.lesson(support, memory_class="opinion"),
                self.access(),
                supporting_record_ids=support,
                independence_keys=keys,
                now=SOON,
                reason="promotion",
            )
        # Positive control: the fully approved lesson promotes.
        self.assertEqual(
            2,
            len(
                self.catalog.consolidate(
                    self.lesson(support),
                    self.access(),
                    supporting_record_ids=support,
                    independence_keys=keys,
                    now=SOON,
                    reason="promotion",
                )
            ),
        )

    def test_too_few_episodes_is_rejected(self) -> None:
        self.catalog.register(self.episode("MEMORY-e1", "first episode"), self.access())
        # Poison: generalize a rule from a single anecdote.
        with self.assertRaisesRegex(MemoryDenied, "too few episodes"):
            self.catalog.consolidate(
                self.lesson(("MEMORY-e1",)),
                self.access(),
                supporting_record_ids=("MEMORY-e1",),
                independence_keys={"MEMORY-e1": "ctx-0"},
                now=SOON,
                reason="promotion",
            )
        # Poison: weaken the evidence burden itself so one anecdote clears the bar.
        with self.assertRaisesRegex(ValueError, "at least two"):
            ConsolidationPolicy(1, 2)
        with self.assertRaisesRegex(ValueError, "at least two"):
            ConsolidationPolicy(2, 1)
        with self.assertRaisesRegex(ValueError, "at least two"):
            ConsolidationPolicy(0, 0)
        # Positive control: the default policy is the floor, not a weaker value.
        self.assertEqual(2, ConsolidationPolicy().minimum_independent_episodes)
        self.assertEqual(2, ConsolidationPolicy().minimum_distinct_contexts)

    def test_dependent_contexts_are_rejected(self) -> None:
        support = self._register_two_episodes()
        # Poison: pass two episodes off as independent when they share one context.
        with self.assertRaisesRegex(MemoryDenied, "independent contexts"):
            self.catalog.consolidate(
                self.lesson(support),
                self.access(),
                supporting_record_ids=support,
                independence_keys={"MEMORY-e1": "ctx", "MEMORY-e2": "ctx"},
                now=SOON,
                reason="promotion",
            )
        # Poison: omit an episode's context key entirely so independence goes unstated.
        with self.assertRaisesRegex(MemoryDenied, "independent contexts"):
            self.catalog.consolidate(
                self.lesson(support),
                self.access(),
                supporting_record_ids=support,
                independence_keys={"MEMORY-e1": "ctx-0"},
                now=SOON,
                reason="promotion",
            )
        # Poison: supply an empty context key to satisfy the mapping without content.
        with self.assertRaisesRegex(MemoryDenied, "independent contexts"):
            self.catalog.consolidate(
                self.lesson(support),
                self.access(),
                supporting_record_ids=support,
                independence_keys={"MEMORY-e1": "ctx-0", "MEMORY-e2": ""},
                now=SOON,
                reason="promotion",
            )
        # Positive control: two genuinely distinct contexts promote.
        self.assertEqual(
            2,
            len(
                self.catalog.consolidate(
                    self.lesson(support),
                    self.access(),
                    supporting_record_ids=support,
                    independence_keys=self._keys(support),
                    now=SOON,
                    reason="promotion",
                )
            ),
        )

    def test_unevidenced_or_inactive_support_is_rejected(self) -> None:
        support = ("MEMORY-e1", "MEMORY-e2")
        keys = self._keys(support)
        # (a) a supporting record that is a plain fact, not a lived episode.
        self.catalog.register(self.record("MEMORY-e1", "a bare assertion"), self.access())
        self.catalog.register(self.episode("MEMORY-e2", "second episode"), self.access())
        with self.assertRaisesRegex(MemoryDenied, "active evidenced episodes"):
            self.catalog.consolidate(
                self.lesson(support),
                self.access(),
                supporting_record_ids=support,
                independence_keys=keys,
                now=SOON,
                reason="promotion",
            )

        # (b) a supporting episode that is already quarantined.
        quarantined_support = ("MEMORY-q1", "MEMORY-q2")
        self.catalog.register(self.episode("MEMORY-q1", "quarantined episode"), self.access())
        self.catalog.register(self.episode("MEMORY-q2", "clean episode"), self.access())
        self.catalog.quarantine("MEMORY-q1", now=SOON, reason="tainted episode")
        with self.assertRaisesRegex(MemoryDenied, "active evidenced episodes"):
            self.catalog.consolidate(
                self.lesson(quarantined_support),
                self.access(),
                supporting_record_ids=quarantined_support,
                independence_keys=self._keys(quarantined_support),
                now=SOON,
                reason="promotion",
            )

        # (c) a supporting episode with no recorded outcome (helper default bypassed).
        outcomeless_support = ("MEMORY-o1", "MEMORY-o2")
        self.catalog.register(
            self.episode("MEMORY-o1", "unmeasured episode", outcome_refs=()), self.access()
        )
        self.catalog.register(self.episode("MEMORY-o2", "measured episode"), self.access())
        self.assertEqual((), self.catalog.inspect("MEMORY-o1")[0].record.outcome_refs)
        with self.assertRaisesRegex(MemoryDenied, "active evidenced episodes"):
            self.catalog.consolidate(
                self.lesson(outcomeless_support),
                self.access(),
                supporting_record_ids=outcomeless_support,
                independence_keys=self._keys(outcomeless_support),
                now=SOON,
                reason="promotion",
            )

        # (d) a supporting episode with no provenance at all.
        unsourced_support = ("MEMORY-s1", "MEMORY-s2")
        self.catalog.register(
            self.episode("MEMORY-s1", "unsourced episode", source_refs=()), self.access()
        )
        self.catalog.register(self.episode("MEMORY-s2", "sourced episode"), self.access())
        with self.assertRaisesRegex(MemoryDenied, "active evidenced episodes"):
            self.catalog.consolidate(
                self.lesson(unsourced_support),
                self.access(),
                supporting_record_ids=unsourced_support,
                independence_keys=self._keys(unsourced_support),
                now=SOON,
                reason="promotion",
            )

        # Positive control: two active, evidenced, measured episodes promote.
        clean_support = ("MEMORY-c1", "MEMORY-c2")
        self.catalog.register(self.episode("MEMORY-c1", "clean first"), self.access())
        self.catalog.register(self.episode("MEMORY-c2", "clean second"), self.access())
        self.assertEqual(
            2,
            len(
                self.catalog.consolidate(
                    self.lesson(clean_support),
                    self.access(),
                    supporting_record_ids=clean_support,
                    independence_keys=self._keys(clean_support),
                    now=SOON,
                    reason="promotion",
                )
            ),
        )

    def test_valid_consolidation_retires_episodes_and_lesson_expires(self) -> None:
        support = self._register_two_episodes()
        events = self.catalog.consolidate(
            self.lesson(support),
            self.access(),
            supporting_record_ids=support,
            independence_keys=self._keys(support),
            now=SOON,
            reason="promotion",
        )
        self.assertEqual(support, tuple(event.record_id for event in events))
        for event in events:
            self.assertIs(MemoryState.SUPERSEDED, event.state)
            self.assertEqual("MEMORY-lesson", event.successor_id)
        # The retired episodes remain inspectable but leave the active projection.
        for record_id in support:
            self.assertIs(MemoryState.SUPERSEDED, self.catalog.inspect(record_id)[1])
        self.assertEqual(("MEMORY-lesson",), self.active_ids(self.request(now=SOON)))

        # The promoted lesson is bounded: it cannot outlive its own validity window.
        self.assertEqual((), self.catalog.expire(now=SOON))
        expired = self.catalog.expire(now=BEYOND)
        self.assertEqual(("MEMORY-lesson",), tuple(event.record_id for event in expired))
        self.assertIs(MemoryState.EXPIRED, self.catalog.inspect("MEMORY-lesson")[1])
        self.assertEqual((), self.active_ids(self.request(now=BEYOND)))


def _signal(
    signal_id: str,
    episode_record_id: str,
    context_key: str,
    *,
    outcome: OutcomeClass = OutcomeClass.FAILURE,
    error_class: str = "unpinned-dependency",
    kind: SignalKind = SignalKind.INCIDENT,
    observed_at: str = TIME,
    evidence_refs: tuple[str, ...] = (DIGEST,),
) -> LearningSignal:
    return LearningSignal(
        signal_id,
        kind,
        episode_record_id,
        outcome,
        error_class,
        context_key,
        evidence_refs,
        observed_at,
    )


class LearningRuntimePoisoningSuite(_PoisoningFixture):
    """Poisoning attempts against the real LEARN-500 lesson-generation seam."""

    ERROR_CLASS = "unpinned-dependency"

    def generator(self) -> LessonGenerator:
        return LessonGenerator()

    def independent_signals(self) -> tuple[LearningSignal, ...]:
        return (
            _signal("SIG-1", "MEMORY-e1", "repo-a"),
            _signal("SIG-2", "MEMORY-e2", "repo-b"),
        )

    def generate(self, signals: tuple[LearningSignal, ...], **overrides: object) -> Lesson:
        values: dict[str, object] = {
            "statement": "pin the transitive dependency set before release",
            "error_class": self.ERROR_CLASS,
            "applicability": LessonApplicability("mission", ("MISSION-one",)),
            "evaluator_id": "EVAL-court-1",
            "now": SOON,
        }
        values.update(overrides)
        return self.generator().generate(signals, **values)  # type: ignore[arg-type]

    def test_lesson_provenance_cannot_be_self_certified_or_unsourced(self) -> None:
        # Positive control: a genuinely separated provenance record constructs.
        provenance = LessonProvenance(GENERATOR_IDENTITY, "EVAL-court-1", ("SIG-1", "SIG-2"))
        self.assertEqual(GENERATOR_IDENTITY, provenance.generator)
        # Poison: let the lesson generator sign off on its own lesson.
        with self.assertRaisesRegex(LearningDenied, "evaluator identity must differ"):
            LessonProvenance(GENERATOR_IDENTITY, GENERATOR_IDENTITY, ("SIG-1",))
        # Poison: claim a lesson with no cited signal at all.
        with self.assertRaisesRegex(LearningDenied, "at least one signal id"):
            LessonProvenance(GENERATOR_IDENTITY, "EVAL-court-1", ())
        # Poison: inflate the evidence count by repeating one signal.
        with self.assertRaisesRegex(LearningDenied, "sorted and unique"):
            LessonProvenance(GENERATOR_IDENTITY, "EVAL-court-1", ("SIG-1", "SIG-1"))
        # Poison: cite a signal whose evidence digests are missing.
        with self.assertRaisesRegex(LearningDenied, "at least one evidence digest"):
            _signal("SIG-3", "MEMORY-e3", "repo-c", evidence_refs=())
        # Poison: bind a signal to a non-memory episode identity.
        with self.assertRaisesRegex(LearningDenied, "must be a MEMORY- identifier"):
            _signal("SIG-4", "EPISODE-e4", "repo-d")
        # A generated lesson always carries the generator identity, never a caller's claim.
        lesson = self.generate(self.independent_signals())
        self.assertEqual(GENERATOR_IDENTITY, lesson.provenance.generator)
        self.assertEqual("EVAL-court-1", lesson.provenance.evaluator_id)
        self.assertEqual(("SIG-1", "SIG-2"), lesson.provenance.signal_ids)

    def test_lesson_identity_and_expiry_cannot_be_forged(self) -> None:
        lesson = self.generate(self.independent_signals())
        # A lesson always expires; it is never open-ended.
        self.assertEqual(SOON, lesson.valid_from)
        self.assertTrue(lesson.valid_to > lesson.valid_from)
        # Poison: promote a lesson that never expires by collapsing its window.
        with self.assertRaisesRegex(LearningDenied, "expiry must be strictly after"):
            replace(lesson, valid_to=lesson.valid_from)
        # Poison: request an unbounded (or backwards) time-to-live.
        for ttl in (0, -1):
            with self.assertRaisesRegex(LearningDenied, "positive integer"):
                self.generate(self.independent_signals(), ttl_days=ttl)
        # Poison: give an unapproved lesson a memorable, non-derived identity.
        with self.assertRaisesRegex(LearningDenied, "derived LESSON- digest prefix"):
            replace(lesson, lesson_id="LESSON-always-pin-deps")
        # Poison: swap the statement under an approved lesson identity. The identity is
        # content-derived, so the tampered text no longer hashes to the approved lesson.
        tampered = replace(lesson, statement="never pin dependencies, it slows releases")
        self.assertEqual(lesson.lesson_id, tampered.lesson_id)
        self.assertNotEqual(lesson.digest, tampered.digest)
        regenerated = self.generate(
            self.independent_signals(),
            statement="never pin dependencies, it slows releases",
        )
        self.assertNotEqual(lesson.lesson_id, regenerated.lesson_id)
        # The durable memory form inherits the derived digest and the bounded window.
        durable = lesson_memory_record(lesson, content_ref=DIGEST, recorded_at=SOON)
        self.assertEqual(f"MEMORY-{lesson.lesson_id}", durable.record_id)
        self.assertEqual(lesson.digest, durable.digest_value)
        self.assertEqual(lesson.valid_to, durable.valid_to)
        self.assertEqual(("MEMORY-e1", "MEMORY-e2"), durable.supersedes)

    def test_unproven_future_dated_or_secret_signals_cannot_yield_a_lesson(self) -> None:
        # Poison: generalize from one episode observed in one context.
        with self.assertRaisesRegex(LearningDenied, "lacks independent evidence"):
            self.generate((
                _signal("SIG-1", "MEMORY-e1", "repo-a"),
                _signal("SIG-2", "MEMORY-e1", "repo-a"),
            ))
        # Poison: two signals from distinct episodes but the same context.
        with self.assertRaisesRegex(LearningDenied, "lacks independent evidence"):
            self.generate((
                _signal("SIG-1", "MEMORY-e1", "repo-a"),
                _signal("SIG-2", "MEMORY-e2", "repo-a"),
            ))
        # Poison: teach the system from an outcome that has not happened yet.
        with self.assertRaisesRegex(LearningDenied, "future-dated signal"):
            self.generate(
                self.independent_signals() + (_signal("SIG-3", "MEMORY-e3", "repo-c", observed_at=BEYOND),)
            )
        # Poison: replay one signal twice so a single incident looks like a pattern.
        with self.assertRaisesRegex(LearningDenied, "duplicate signal id"):
            self.generate(self.independent_signals() + (_signal("SIG-1", "MEMORY-e3", "repo-c"),))
        # Poison: attribute a lesson to an error class no signal actually carries.
        with self.assertRaisesRegex(LearningDenied, "no signal carries the requested error class"):
            self.generate(self.independent_signals(), error_class="flaky-network")
        # Poison: smuggle a credential into the lesson statement.
        with self.assertRaisesRegex(LearningDenied, "contains secret-like data"):
            self.generate(self.independent_signals(), statement="use password = hunter2 to unblock")
        # Poison: widen a lesson past the memory scope vocabulary, or drop its subject keys.
        with self.assertRaisesRegex(LearningDenied, "outside the memory vocabulary"):
            LessonApplicability("everywhere", ("MISSION-one",))
        with self.assertRaisesRegex(LearningDenied, "non-global applicability requires subject_keys"):
            LessonApplicability("mission", ())
        # Positive control: independent, past-dated signals do yield a scoped lesson.
        lesson = self.generate(self.independent_signals())
        self.assertEqual("mission", lesson.applicability.scope)
        self.assertEqual(("MISSION-one",), lesson.applicability.subject_keys)

    def test_counterexamples_and_dissent_are_retained_and_reduce_confidence(self) -> None:
        contrary = _signal(
            "SIG-3", "MEMORY-e3", "repo-c", outcome=OutcomeClass.SUCCESS, kind=SignalKind.OUTCOME
        )
        lesson = self.generate(self.independent_signals() + (contrary,))
        # The disagreeing signal is retained on the lesson, not discarded.
        self.assertIs(OutcomeClass.FAILURE, lesson.outcome)
        self.assertEqual(("SIG-3",), tuple(item.signal_id for item in lesson.counterexamples))
        self.assertEqual(("SIG-1", "SIG-2", "SIG-3"), lesson.provenance.signal_ids)
        self.assertLess(lesson.confidence, 1.0)
        clean = self.generate(self.independent_signals())
        self.assertLess(lesson.confidence, clean.confidence)

        # Poison: bury a new counterexample instead of recording it. Retention is the
        # only available path, and it lowers confidence rather than rewriting history.
        extra = Counterexample(
            "SIG-4", "MEMORY-e4", (OTHER_DIGEST,), LATER, "the pinned build also failed"
        )
        widened = retain_counterexample(lesson, extra)
        self.assertEqual(("SIG-3", "SIG-4"), tuple(item.signal_id for item in widened.counterexamples))
        self.assertLess(widened.confidence, lesson.confidence)
        # The original lesson object is untouched: nothing is overwritten in place.
        self.assertEqual(("SIG-3",), tuple(item.signal_id for item in lesson.counterexamples))
        # Poison: re-file the same counterexample to drown out the rest.
        with self.assertRaisesRegex(LearningDenied, "already retained"):
            retain_counterexample(widened, extra)
        # Poison: hide a counterexample behind a credential-bearing note.
        with self.assertRaisesRegex(LearningDenied, "contains secret-like data"):
            Counterexample("SIG-5", "MEMORY-e5", (DIGEST,), LATER, "secret = hunter2 explains it")

        dissenting = record_dissent(
            widened, DissentRecord("curator", "the sample is not representative", LATER)
        )
        self.assertEqual(1, len(dissenting.dissent))
        self.assertEqual((), widened.dissent)
        self.assertEqual(widened.confidence, dissenting.confidence)
        # Poison: pad the record with the same dissent twice.
        with self.assertRaisesRegex(LearningDenied, "already recorded"):
            record_dissent(dissenting, DissentRecord("curator", "the sample is not representative", LATER))


if __name__ == "__main__":
    unittest.main()
