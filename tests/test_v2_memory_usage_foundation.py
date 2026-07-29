from __future__ import annotations

import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import Mapping, cast

import hive_mind_os_v2
from hive_mind_os_v2 import (
    AttemptKind,
    CostObservation,
    DeliveryConflictError,
    DuplicateRecordError,
    FoundationStore,
    MemoryDisposition,
    MemoryRecord,
    MemoryRelation,
    NativeUsageField,
    NormalizedUsageDimension,
    ReconciliationStatus,
    RepositoryConflictError,
    RepositoryIdentity,
    ScopeViolationError,
    StoreVersionError,
    UsageAxis,
    UsageEvent,
    UsageOutcome,
    UsagePurpose,
    contract_digest,
)

TIMESTAMP = "2026-07-28T00:00:00+00:00"


def repository(
    repository_id: str = "repo:hive-mind-os",
    canonical_uri: str = "https://github.com/kb4beast/hive-mind-os",
) -> RepositoryIdentity:
    return RepositoryIdentity(
        tenant_id="tenant:test",
        repository_id=repository_id,
        canonical_uri=canonical_uri,
        default_branch="main",
        created_at=TIMESTAMP,
    )


def memory_record(
    record_id: str,
    *,
    disposition: MemoryDisposition = MemoryDisposition.ACTIVE,
    supersedes_record_id: str | None = None,
    tombstone_reason: str | None = None,
) -> MemoryRecord:
    return MemoryRecord(
        tenant_id="tenant:test",
        repository_id="repo:hive-mind-os",
        record_type="idea",
        actor_id="explorer:test",
        source_uri="urn:test:source",
        source_digest=contract_digest({"source": "fixture"}),
        payload={"title": record_id, "confidence": 0.7},
        relations=(MemoryRelation("supports", "memory:external"),),
        disposition=disposition,
        supersedes_record_id=supersedes_record_id,
        tombstone_reason=tombstone_reason,
        confidence=0.7,
        record_id=record_id,
        occurred_at=TIMESTAMP,
        observed_at=TIMESTAMP,
    )


def usage_event(
    event_id: str = "usage:event-1",
    attempt_id: str = "attempt:1",
) -> UsageEvent:
    return UsageEvent(
        tenant_id="tenant:test",
        repository_id="repo:hive-mind-os",
        mission_id="mission:1",
        run_id="run:1",
        step_id="step:1",
        role="builder",
        work_item_id="work:1",
        actor_id="builder:test",
        purpose=UsagePurpose.ACTING,
        attempt_id=attempt_id,
        attempt_kind=AttemptKind.MODEL,
        outcome=UsageOutcome.SUCCEEDED,
        trace_id="trace:1",
        span_id="span:1",
        provider="openai-compatible",
        model="fixture-model",
        model_version="2026-07-28",
        provider_request_id="request:1",
        budget_lease_id="lease:1",
        latency_ms=125,
        prompt_digest=contract_digest({"prompt": "redacted"}),
        response_digest=contract_digest({"response": "redacted"}),
        native_usage=(
            NativeUsageField("usage.prompt_tokens", 11, "token"),
            NativeUsageField("usage.completion_tokens", 7, "token"),
            NativeUsageField("usage.cached_tokens", None, "token", "not reported"),
        ),
        normalized_usage=(
            NormalizedUsageDimension(
                UsageAxis.INPUT_TOKENS,
                11,
                "token",
                "openai-compatible/v1:usage.prompt_tokens",
            ),
            NormalizedUsageDimension(
                UsageAxis.OUTPUT_TOKENS,
                7,
                "token",
                "openai-compatible/v1:usage.completion_tokens",
            ),
        ),
        normalization_version="usage-normalization:v1",
        cost=CostObservation(
            "0.0018",
            "USD",
            "fixture-price-card",
            price_card_version="fixture:2026-07-28",
            estimated=True,
        ),
        reconciliation_status=ReconciliationStatus.UNAVAILABLE,
        event_id=event_id,
        occurred_at=TIMESTAMP,
        observed_at=TIMESTAMP,
    )


class ContractTests(unittest.TestCase):
    def test_candidate_is_explicitly_quarantined_and_inactive(self) -> None:
        self.assertEqual(hive_mind_os_v2.CANDIDATE_STATUS, "quarantined")
        self.assertFalse(hive_mind_os_v2.RUNTIME_ACTIVATED)

    def test_repository_identity_digest_excludes_observation_time(self) -> None:
        first = repository()
        second = RepositoryIdentity(
            tenant_id=first.tenant_id,
            repository_id=first.repository_id,
            canonical_uri=first.canonical_uri,
            default_branch=first.default_branch,
            created_at="2026-07-29T00:00:00+00:00",
        )
        self.assertEqual(first.identity_digest, second.identity_digest)
        self.assertNotEqual(first.to_contract(), second.to_contract())

    def test_tombstone_requires_target_and_reason(self) -> None:
        with self.assertRaisesRegex(ValueError, "tombstones require"):
            memory_record(
                "memory:tombstone",
                disposition=MemoryDisposition.TOMBSTONE,
            )

    def test_contract_rejects_non_finite_json(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-finite"):
            MemoryRecord(
                tenant_id="tenant:test",
                repository_id="repo:hive-mind-os",
                record_type="idea",
                actor_id="explorer:test",
                source_uri="urn:test:source",
                payload={"invalid": float("nan")},
                record_id="memory:non-finite",
                occurred_at=TIMESTAMP,
                observed_at=TIMESTAMP,
            )

    def test_usage_keeps_native_and_normalized_axes_separate(self) -> None:
        contract = usage_event().to_contract()
        native = cast(list[dict[str, object]], contract["native_usage"])
        normalized = cast(list[dict[str, object]], contract["normalized_usage"])
        self.assertIsNone(native[2]["value"])
        self.assertEqual(
            [item["axis"] for item in normalized],
            ["input-tokens", "output-tokens"],
        )
        self.assertNotIn("total_tokens", contract)
        self.assertNotIn("prompt", contract)
        self.assertNotIn("response", contract)

    def test_duplicate_normalized_axis_is_rejected(self) -> None:
        first = NormalizedUsageDimension(
            UsageAxis.INPUT_TOKENS,
            1,
            "token",
            "fixture:a",
        )
        second = NormalizedUsageDimension(
            UsageAxis.INPUT_TOKENS,
            2,
            "token",
            "fixture:b",
        )
        with self.assertRaisesRegex(ValueError, "axes must be unique"):
            UsageEvent(
                tenant_id="tenant:test",
                repository_id="repo:hive-mind-os",
                mission_id="mission:1",
                run_id="run:1",
                step_id="step:1",
                role="builder",
                work_item_id="work:1",
                actor_id="builder:test",
                purpose=UsagePurpose.ACTING,
                attempt_id="attempt:duplicate-axis",
                attempt_kind=AttemptKind.MODEL,
                outcome=UsageOutcome.SUCCEEDED,
                trace_id="trace:duplicate-axis",
                span_id="span:duplicate-axis",
                provider="fixture",
                model="fixture",
                normalized_usage=(first, second),
                normalization_version="fixture:v1",
                event_id="usage:duplicate-axis",
                occurred_at=TIMESTAMP,
                observed_at=TIMESTAMP,
            )


class _FailingMemoryOutboxStore(FoundationStore):
    def _append_outbox(
        self,
        aggregate_kind: str,
        aggregate_id: str,
        event_type: str,
        payload: Mapping[str, object],
    ) -> int:
        if event_type == "memory.recorded.v2":
            raise RuntimeError("injected post-insert outbox failure")
        return super()._append_outbox(
            aggregate_kind,
            aggregate_id,
            event_type,
            payload,
        )


class FoundationStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "foundation.sqlite3"
        self.store = FoundationStore(self.path)
        self.store.register_repository(repository())

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def test_file_store_uses_wal_and_exact_store_markers(self) -> None:
        report = self.store.verify_integrity()
        self.assertTrue(report.valid, report.errors)
        self.assertEqual(report.journal_mode, "wal")
        self.assertEqual(
            self.store._connection.execute("PRAGMA application_id").fetchone()[0],
            hive_mind_os_v2.STORE_APPLICATION_ID,
        )
        self.assertEqual(
            self.store._connection.execute("PRAGMA user_version").fetchone()[0],
            hive_mind_os_v2.STORE_SCHEMA_VERSION,
        )

    def test_memory_and_outbox_commit_atomically_with_hash_chain(self) -> None:
        self.store.append_memory(memory_record("memory:one"))
        self.store.append_memory(
            memory_record(
                "memory:two",
                disposition=MemoryDisposition.SUPERSESSION,
                supersedes_record_id="memory:one",
            )
        )
        records = self.store.memory_records("tenant:test", "repo:hive-mind-os")
        self.assertEqual(len(records), 2)
        self.assertIsNone(records[0]["previous_record_digest"])
        self.assertEqual(
            records[1]["previous_record_digest"],
            records[0]["record_digest"],
        )
        pending = self.store.pending_outbox("projector:test")
        self.assertEqual(
            [message.event_type for message in pending],
            [
                "repository.registered.v2",
                "memory.recorded.v2",
                "memory.recorded.v2",
            ],
        )
        report = self.store.verify_integrity()
        self.assertTrue(report.valid, report.errors)
        self.assertEqual(report.memory_records_checked, 2)
        self.assertEqual(report.outbox_messages_checked, 3)

    def test_duplicate_memory_rolls_back_without_orphan_outbox(self) -> None:
        record = memory_record("memory:one")
        self.store.append_memory(record)
        before = len(self.store.pending_outbox("projector:test"))
        with self.assertRaises(DuplicateRecordError):
            self.store.append_memory(record)
        after = len(self.store.pending_outbox("projector:test"))
        self.assertEqual(after, before)
        self.assertEqual(
            len(self.store.memory_records("tenant:test", "repo:hive-mind-os")),
            1,
        )

    def test_post_insert_outbox_failure_rolls_back_record_and_relation(self) -> None:
        self.store.close()
        self.store = _FailingMemoryOutboxStore(self.path)
        before = len(self.store.pending_outbox("projector:test"))
        with self.assertRaisesRegex(RuntimeError, "injected"):
            self.store.append_memory(memory_record("memory:rollback"))
        self.assertEqual(
            len(self.store.memory_records("tenant:test", "repo:hive-mind-os")),
            0,
        )
        self.assertEqual(len(self.store.pending_outbox("projector:test")), before)
        relation_count = self.store._connection.execute(
            "SELECT COUNT(*) FROM memory_relations"
        ).fetchone()[0]
        self.assertEqual(relation_count, 0)
        self.assertTrue(self.store.verify_integrity().valid)

    def test_repository_identity_is_idempotent_but_not_mutable(self) -> None:
        sequence = self.store.register_repository(repository())
        self.assertEqual(sequence, 1)
        with self.assertRaises(RepositoryConflictError):
            self.store.register_repository(
                repository(canonical_uri="https://example.invalid/different")
            )

    def test_supersession_cannot_cross_repository_scope(self) -> None:
        self.store.append_memory(memory_record("memory:one"))
        self.store.register_repository(repository("repo:other", "urn:repo:other"))
        cross_scope = MemoryRecord(
            tenant_id="tenant:test",
            repository_id="repo:other",
            record_type="idea",
            actor_id="explorer:test",
            source_uri="urn:test:source",
            payload={"title": "invalid"},
            disposition=MemoryDisposition.SUPERSESSION,
            supersedes_record_id="memory:one",
            record_id="memory:cross-scope",
            occurred_at=TIMESTAMP,
            observed_at=TIMESTAMP,
        )
        with self.assertRaisesRegex(ScopeViolationError, "cannot cross"):
            self.store.append_memory(cross_scope)

    def test_usage_attempt_is_durable_and_unknown_is_not_zero(self) -> None:
        self.store.append_usage(usage_event())
        events = self.store.usage_events("tenant:test", "repo:hive-mind-os")
        self.assertEqual(len(events), 1)
        native = events[0]["event"]["native_usage"]
        self.assertIsNone(native[2]["value"])
        self.assertEqual(events[0]["event"]["retry_index"], 0)
        with self.assertRaises(DuplicateRecordError):
            self.store.append_usage(
                usage_event(event_id="usage:event-2", attempt_id="attempt:1")
            )
        self.assertEqual(
            len(self.store.usage_events("tenant:test", "repo:hive-mind-os")),
            1,
        )
        self.assertTrue(self.store.verify_integrity().valid)

    def test_outbox_delivery_is_idempotent_and_append_only(self) -> None:
        message = self.store.pending_outbox("projector:test")[0]
        receipt = contract_digest({"delivered": message.message_id})
        sequence = self.store.record_delivery(
            message.message_id,
            "projector:test",
            receipt,
        )
        self.assertEqual(
            self.store.record_delivery(
                message.message_id,
                "projector:test",
                receipt,
            ),
            sequence,
        )
        self.assertEqual(len(self.store.pending_outbox("projector:test")), 0)
        with self.assertRaises(DeliveryConflictError):
            self.store.record_delivery(
                message.message_id,
                "projector:test",
                contract_digest({"different": True}),
            )
        with self.assertRaisesRegex(ValueError, "lowercase sha256"):
            self.store.record_delivery(
                message.message_id,
                "other:consumer",
                "sha256:" + ("g" * 64),
            )
        with self.assertRaisesRegex(sqlite3.DatabaseError, "append-only"):
            self.store._connection.execute(
                "UPDATE outbox_deliveries SET consumer_id = 'mutated'"
            )
        report = self.store.verify_integrity()
        self.assertTrue(report.valid, report.errors)
        self.assertEqual(report.outbox_deliveries_checked, 1)

    def test_reopen_recovers_records_and_pending_delivery(self) -> None:
        self.store.append_memory(memory_record("memory:one"))
        self.store.append_usage(usage_event())
        self.store.close()
        self.store = FoundationStore(self.path)
        self.assertEqual(
            len(self.store.memory_records("tenant:test", "repo:hive-mind-os")),
            1,
        )
        self.assertEqual(
            len(self.store.usage_events("tenant:test", "repo:hive-mind-os")),
            1,
        )
        self.assertEqual(len(self.store.pending_outbox("replay:test")), 3)
        report = self.store.verify_integrity()
        self.assertTrue(report.valid, report.errors)
        self.assertEqual(report.repositories_checked, 1)

    def test_store_rejects_unregistered_scope(self) -> None:
        record = MemoryRecord(
            tenant_id="tenant:test",
            repository_id="repo:missing",
            record_type="idea",
            actor_id="explorer:test",
            source_uri="urn:test:source",
            payload={"title": "missing"},
            record_id="memory:missing",
            occurred_at=TIMESTAMP,
            observed_at=TIMESTAMP,
        )
        with self.assertRaises(ScopeViolationError):
            self.store.append_memory(record)

    def test_database_tables_reject_update_and_delete(self) -> None:
        self.store.append_memory(memory_record("memory:one"))
        self.store.append_usage(usage_event())
        for table in (
            "repositories",
            "memory_records",
            "memory_relations",
            "usage_events",
            "outbox_messages",
        ):
            with self.subTest(table=table):
                with self.assertRaises(sqlite3.DatabaseError):
                    self.store._connection.execute(f"DELETE FROM {table}")

    def test_two_connections_serialize_digest_chain(self) -> None:
        second = FoundationStore(self.path)
        barrier = Barrier(2)

        def append(store: FoundationStore, record_id: str) -> int:
            barrier.wait(timeout=5)
            return store.append_memory(memory_record(record_id))

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = (
                    executor.submit(append, self.store, "memory:concurrent-a"),
                    executor.submit(append, second, "memory:concurrent-b"),
                )
                for future in futures:
                    self.assertGreater(future.result(timeout=10), 0)
            records = self.store.memory_records("tenant:test", "repo:hive-mind-os")
            self.assertEqual(len(records), 2)
            self.assertEqual(
                records[1]["previous_record_digest"],
                records[0]["record_digest"],
            )
            report = self.store.verify_integrity()
            self.assertTrue(report.valid, report.errors)
        finally:
            second.close()

    def test_integrity_detects_relation_index_drift(self) -> None:
        self.store.append_memory(memory_record("memory:one"))
        self.store._connection.execute(
            """
            INSERT INTO memory_relations(record_id,relation_type,target_record_id)
            VALUES('memory:one','contradicts','memory:other')
            """
        )
        report = self.store.verify_integrity()
        self.assertFalse(report.valid)
        self.assertIn("memory:1:relation-index", report.errors)

    def test_integrity_detects_outbox_tamper_and_missing_guard(self) -> None:
        self.store._connection.execute("DROP TRIGGER outbox_messages_no_update")
        self.store._connection.execute(
            "UPDATE outbox_messages SET event_type = 'forged.event' WHERE sequence = 1"
        )
        report = self.store.verify_integrity()
        self.assertFalse(report.valid)
        self.assertIn("database:missing-trigger-outbox_messages_no_update", report.errors)
        self.assertIn("outbox:1:event-type", report.errors)

    def test_store_rejects_unmarked_non_empty_database(self) -> None:
        self.store.close()
        self.path.unlink()
        unrelated = sqlite3.connect(self.path)
        unrelated.execute("CREATE TABLE unrelated(value TEXT NOT NULL)")
        unrelated.commit()
        unrelated.close()
        with self.assertRaisesRegex(StoreVersionError, "unmarked non-empty"):
            FoundationStore(self.path)
        self.store = FoundationStore(":memory:")

    def test_store_rejects_incompatible_database_marker_before_schema_use(self) -> None:
        self.store.close()
        incompatible = sqlite3.connect(self.path)
        incompatible.execute("PRAGMA application_id=12345")
        incompatible.commit()
        incompatible.close()
        with self.assertRaises(StoreVersionError):
            FoundationStore(self.path)
        self.store = FoundationStore(":memory:")


if __name__ == "__main__":
    unittest.main()
