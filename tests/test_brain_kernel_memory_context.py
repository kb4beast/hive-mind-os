from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hive_mind_os.brain_kernel.context import (
    ContextCompiler,
    ContextRequest,
    HotContextItem,
)
from hive_mind_os.brain_kernel.contracts import MemoryRecord, MemoryState
from hive_mind_os.brain_kernel.memory import (
    MemoryAccess,
    MemoryArtifactStore,
    MemoryCatalog,
    MemoryDenied,
    RetrievalRequest,
)

DIGEST = "sha256:" + "0" * 64
TIME = "2026-08-07T12:00:00Z"
LATER = "2026-08-08T12:00:00Z"


class KernelMemoryContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.artifacts = MemoryArtifactStore(Path(self.temporary.name))
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
        valid_to: str | None = None,
        supersedes: tuple[str, ...] = (),
    ) -> MemoryRecord:
        artifact = self.artifacts.put(body)
        return MemoryRecord(
            record_id,
            memory_class,
            scope,
            subject_keys,
            artifact.digest,
            ("SRC-one",),
            "verified",
            "internal",
            TIME,
            valid_to,
            TIME,
            TIME,
            MemoryState.ACTIVE,
            supersedes,
            (),
            None,
            (),
            "retain",
            DIGEST,
        )

    @staticmethod
    def access(*, roles: tuple[str, ...] = ("builder",), evaluator_visible: bool = True) -> MemoryAccess:
        return MemoryAccess(roles, ("internal",), evaluator_visible)

    def request(self, *, role: str = "builder", query: str = "") -> RetrievalRequest:
        return RetrievalRequest(
            "MISSION-one", "WORK-one", role, query, LATER, ("internal",)
        )

    def test_artifacts_are_immutable_and_reject_secrets_or_raw_transcripts(self) -> None:
        artifact = self.artifacts.put("immutable evidence")
        self.assertEqual("immutable evidence", self.artifacts.get(artifact.digest))
        with self.assertRaises(MemoryDenied):
            self.artifacts.put("sk_abcdefghijklmnopqrstuvwxyz")
        with self.assertRaises(MemoryDenied):
            self.artifacts.put("a model said this", content_kind="model_transcript")
        path = self.artifacts._path(artifact.digest)
        path.write_text("rewritten", encoding="utf-8")
        with self.assertRaises(MemoryDenied):
            self.artifacts.get(artifact.digest)

    def test_lifecycle_supersession_conflict_retraction_and_expiry_preserve_records(self) -> None:
        first = self.record("MEMORY-one", "old validated fact")
        successor = self.record(
            "MEMORY-two", "new validated fact", supersedes=("MEMORY-one",)
        )
        self.catalog.register(first, self.access())
        events = self.catalog.supersede(successor, self.access(), now=LATER, reason="corrected")
        self.assertEqual(("MEMORY-one",), tuple(event.record_id for event in events))
        self.assertEqual(("MEMORY-two",), tuple(item.record.record_id for item in self.catalog.active_records(self.request())))
        conflict = self.catalog.record_conflict(("MEMORY-two", "MEMORY-one"), reason="dissent", recorded_at=LATER)
        self.assertIn(conflict.conflict_id, self.catalog.conflicts_for(("MEMORY-two",)))
        event = self.catalog.transition(
            "MEMORY-two", MemoryState.RETRACTED, event_id="retract-two", occurred_at=LATER, reason="evidence withdrawn"
        )
        self.assertEqual(MemoryState.RETRACTED, event.state)
        expiring = self.record("MEMORY-three", "short lived", valid_to=TIME)
        self.catalog.register(expiring, self.access())
        self.assertEqual(("MEMORY-three",), tuple(event.record_id for event in self.catalog.expire(now=LATER)))
        self.assertEqual(3, len(self.catalog.lifecycle_events()))
        self.assertEqual("old validated fact", self.artifacts.get(first.content_ref))

    def test_snapshot_rebuild_reproduces_the_active_memory_projection(self) -> None:
        first = self.record("MEMORY-one", "old fact")
        successor = self.record("MEMORY-two", "corrected fact", supersedes=("MEMORY-one",))
        self.catalog.register(first, self.access())
        self.catalog.supersede(successor, self.access(), now=LATER, reason="correction")
        self.catalog.record_conflict(("MEMORY-one", "MEMORY-two"), reason="review", recorded_at=LATER)
        snapshot = self.catalog.snapshot()
        rebuilt = MemoryCatalog.rebuild(self.artifacts, snapshot)
        self.assertEqual(snapshot.digest(), rebuilt.snapshot().digest())
        self.assertEqual(
            self.catalog.active_records(self.request()),
            rebuilt.active_records(self.request()),
        )

    def test_ranking_is_deterministic_and_unauthorized_records_are_omitted(self) -> None:
        builder = self.record("MEMORY-builder", "alpha alpha")
        curator = self.record("MEMORY-curator", "alpha secret assessment")
        self.catalog.register(builder, self.access())
        self.catalog.register(curator, self.access(roles=("curator",)))
        first = self.catalog.rank(self.request(query="alpha"))
        second = self.catalog.rank(self.request(query="alpha"))
        self.assertEqual(first, second)
        self.assertEqual(("MEMORY-builder",), tuple(item.entry.record.record_id for item in first))
        self.assertEqual(
            ("MEMORY-curator",),
            tuple(item.entry.record.record_id for item in self.catalog.rank(self.request(role="curator", query="alpha"))),
        )

    def test_context_is_bounded_valid_and_cold_retrieval_creates_a_new_manifest(self) -> None:
        alpha = self.record("MEMORY-alpha", "alpha alpha alpha")
        beta = self.record("MEMORY-beta", "beta")
        self.catalog.register(alpha, self.access())
        self.catalog.register(beta, self.access())
        compiler = ContextCompiler(self.catalog)
        request = ContextRequest(
            "MISSION-one", "WORK-one", "ATTEMPT-one", "builder", DIGEST, DIGEST,
            6, "beta", LATER, ("internal",), (HotContextItem("WORK-one", 1),),
        )
        compiled = compiler.compile(request)
        self.assertLessEqual(compiled.estimated_tokens, request.token_budget)
        self.assertEqual(("MEMORY-beta",), compiled.manifest.warm_items)
        self.assertEqual(("MEMORY-alpha",), compiled.manifest.cold_references)
        self.assertEqual(compiled.manifest.manifest_digest, compiler.manifests.get(compiled.manifest.manifest_digest).manifest_digest)
        self.assertIsInstance(json.loads(json.dumps(compiled.manifest.to_document())), dict)
        updated = compiler.retrieve_cold(compiled, "MEMORY-alpha")
        self.assertNotEqual(compiled.manifest.manifest_digest, updated.manifest.manifest_digest)
        self.assertIn("MEMORY-alpha", updated.manifest.warm_items)
        self.assertEqual(2, len(compiler.manifests.manifests()))

    def test_evaluator_mode_excludes_builder_scratchpad_without_dropping_valid_evidence(self) -> None:
        evidence = self.record("MEMORY-evidence", "accepted test evidence")
        scratchpad = self.record("MEMORY-scratch", "builder internal rationale", memory_class="scratchpad")
        self.catalog.register(evidence, self.access(roles=("curator",)))
        self.catalog.register(scratchpad, self.access(roles=("curator",), evaluator_visible=False))
        request = ContextRequest(
            "MISSION-one", "WORK-one", "ATTEMPT-curator", "curator", DIGEST, DIGEST,
            40, "evidence", LATER, ("internal",), (), evaluator_mode=True,
        )
        compiled = ContextCompiler(self.catalog).compile(request)
        self.assertEqual(("MEMORY-evidence",), compiled.manifest.warm_items)
        self.assertIn("evaluator_isolation", compiled.manifest.excluded_categories)
        self.assertTrue(compiled.manifest.generator_evaluator_separated)

    def test_hot_context_never_slices_required_items_to_fit(self) -> None:
        request = ContextRequest(
            "MISSION-one", "WORK-one", "ATTEMPT-one", "builder", DIGEST, DIGEST,
            1, "", LATER, ("internal",), (HotContextItem("charter", 2),),
        )
        with self.assertRaisesRegex(ValueError, "hard token budget"):
            ContextCompiler(self.catalog).compile(request)
