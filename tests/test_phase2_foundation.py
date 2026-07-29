from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import hive_mind_os
from hive_mind_os.foundation.authority import AuthorityDecision, decide_foundation_write
from hive_mind_os.foundation.canonical import digest
from hive_mind_os.foundation.contracts import (
    PHASE2_SCHEMA_NAMES,
    validate_foundation,
    validate_foundation_catalog,
)
from hive_mind_os.foundation.generation import (
    _load_canonical_definitions,
    compile_generation_zero_candidates,
    verify_generated_candidates,
)
from hive_mind_os.foundation.observability import (
    TraceRecord,
    project_metric,
    project_otel_envelope,
    project_trace,
)
from hive_mind_os.foundation.opportunities import OpportunityLedger
from hive_mind_os.foundation.store import (
    FoundationStore,
    IdempotencyConflict,
    ScopeError,
)
from hive_mind_os.foundation.usage import (
    ProviderUsageAdapter,
    ReceiptedModelProvider,
    UsageAttribution,
    UsageRecorder,
    reconcile_invoice,
    reconcile_usage_axes,
)
from hive_mind_os.ledger import EvidenceLedger
from hive_mind_os.model_provider import (
    ModelRequest,
    ModelResponse,
    ModelTransportError,
    ProviderConfig,
    ProviderKind,
)
from hive_mind_os.models import Role
from hive_mind_os.policy import Action, PolicyDecision
from scripts.phase2_foundation_inventory import build_phase2_inventory

FIXTURES = Path(__file__).parent / "fixtures" / "phase2"
REPOSITORY_IDENTITY = {
    "record_type": "repository-identity",
    "schema_version": 1,
    "tenant_id": "tenant:test",
    "repository_id": "repository:test",
    "project_lineage_id": "lineage:test",
    "instance_id": "instance:test",
    "remote_evidence_digest": digest("remote-evidence"),
    "controller_build_digest": digest("controller"),
    "self_host_depth": 0,
    "parent_run_id": None,
    "subject_commit": None,
    "target_cutoff": None,
}


def allowed_authority(
    action: str,
    *,
    role: Role = Role.BUILDER,
    public_release_allowed: bool = False,
    tenant_id: str = "tenant:test",
    repository_id: str = "repository:test",
    actor_id: str | None = None,
    public_release_subject_digest: str | None = None,
) -> AuthorityDecision:
    authority_actor = actor_id or (
        "foundation-usage-recorder-v1"
        if action == "foundation.telemetry.write"
        else role.value
    )
    decision = decide_foundation_write(
        role=role,
        action=action,
        policy_decision=PolicyDecision(True, "fixture"),
        lease_actions={action},
        adapter_actions={action},
        mission_risk_allowed=True,
        budget_available=True,
        recorder_identity=(
            "foundation-usage-recorder-v1"
            if action == "foundation.telemetry.write"
            else None
        ),
        tenant_id=tenant_id,
        repository_id=repository_id,
        actor_id=authority_actor,
        decision_id=f"decision:{action}:{authority_actor}",
        lease_id=f"lease:{action}:{authority_actor}",
        public_release_decision_id=(
            "release:curator-approved" if public_release_allowed else None
        ),
        public_release_decided_by=(
            "curator" if public_release_allowed else None
        ),
        public_release_subject_digest=(
            public_release_subject_digest if public_release_allowed else None
        ),
    )
    if not decision.allowed:
        raise AssertionError(decision)
    return decision


class FoundationContractAndGenerationTests(unittest.TestCase):
    def test_catalog_is_separate_strict_and_complete(self) -> None:
        self.assertEqual(len(PHASE2_SCHEMA_NAMES), 17)
        self.assertTrue(validate_foundation_catalog().valid)
        self.assertEqual(len(hive_mind_os.__all__), 131)

    def test_generated_candidates_are_deterministic_inert_and_drift_checked(self) -> None:
        first = compile_generation_zero_candidates()
        second = compile_generation_zero_candidates()
        self.assertEqual(first, second)
        self.assertEqual(len(first), 9)
        self.assertEqual(verify_generated_candidates(first), ())
        canonical_root = (
            Path(__file__).parents[1]
            / "src"
            / "hive_mind_os"
            / "foundation"
            / "canonical"
            / "agents"
        )
        self.assertEqual(len(tuple(canonical_root.glob("*.json"))), 8)
        projected_architect = json.loads(first["agents/architect.json"])
        canonical_architect = json.loads(
            (canonical_root / "architect.json").read_bytes()
        )
        self.assertEqual(
            projected_architect.pop("generator_version"),
            "phase2-foundation-generator-v1",
        )
        self.assertEqual(projected_architect, canonical_architect)
        architect = json.loads(first["agents/architect.json"])
        self.assertTrue(validate_foundation("agent-definition-v2", architect).valid)
        manifest = json.loads(first["manifest.json"])
        self.assertTrue(validate_foundation("prompt-composition-v2", manifest).valid)
        mutated = dict(first)
        mutated["agents/architect.json"] += b" "
        self.assertEqual(
            verify_generated_candidates(mutated),
            ("generated artifact drift: agents/architect.json",),
        )
        with tempfile.TemporaryDirectory() as temporary:
            package_root = Path(temporary) / "foundation"
            temporary_agents = package_root / "canonical" / "agents"
            temporary_agents.mkdir(parents=True)
            for source in canonical_root.glob("*.json"):
                (temporary_agents / source.name).write_bytes(source.read_bytes())
            stale = json.loads(
                (temporary_agents / "explorer.json").read_text(encoding="utf-8")
            )
            stale["mission"] = "mutated without refreshing the content digest"
            (temporary_agents / "explorer.json").write_text(
                json.dumps(stale), encoding="utf-8"
            )
            with patch(
                "hive_mind_os.foundation.generation.files",
                return_value=package_root,
            ), self.assertRaisesRegex(ValueError, "content digest mismatch"):
                _load_canonical_definitions()

    def test_contracts_fail_closed_on_unknown_fields(self) -> None:
        candidate = json.loads(
            compile_generation_zero_candidates()["agents/explorer.json"]
        )
        candidate["self_granted_authority"] = True
        result = validate_foundation("agent-definition-v2", candidate)
        self.assertFalse(result.valid)
        self.assertIn("unknown properties", result.issues[0])
        for field in (
            "memory_contract",
            "usage_contract",
            "portability",
            "governance",
        ):
            malformed = json.loads(
                compile_generation_zero_candidates()["agents/explorer.json"]
            )
            malformed[field] = {}
            self.assertFalse(
                validate_foundation("agent-definition-v2", malformed).valid,
                field,
            )
        attribution = {
            "record_type": "attribution-record",
            "schema_version": 1,
            "record_id": "attribution:test",
            "subject_record_id": "usage:test",
            "outcome": "avoidable-waste",
            "purpose_allocations_ppm": {"build": 500_000},
            "resource_allocations_ppm": {"tokens": 1_000_000},
            "reviewed_by": None,
        }
        result = validate_foundation(
            "outcome-attribution-record-v1", attribution
        )
        self.assertFalse(result.valid)
        self.assertTrue(
            any("1000000 ppm" in issue for issue in result.issues)
        )
        self.assertTrue(
            any("independent review" in issue for issue in result.issues)
        )

    def test_additive_inventory_preserves_frozen_facades_and_legacy_resources(self) -> None:
        inventory = build_phase2_inventory(Path(__file__).parents[1])
        frozen = inventory["generation_zero"]
        self.assertEqual(
            (frozen["root_api_count"], frozen["package_api_count"], frozen["cli_parser_count"]),
            (131, 33, 13),
        )
        self.assertEqual(
            (
                frozen["legacy_schema_count"],
                frozen["legacy_package_resource_count"],
                frozen["legacy_total_resource_count"],
            ),
            (20, 48, 68),
        )
        self.assertTrue(inventory["foundation_contracts"]["catalog_valid"])
        self.assertEqual(inventory["foundation_contracts"]["count"], 17)
        self.assertEqual(inventory["generated_candidates"]["count"], 9)
        self.assertEqual(inventory["canonical_agent_sources"]["count"], 8)

    def test_authority_is_an_intersection_and_telemetry_is_recorder_only(self) -> None:
        allowed = decide_foundation_write(
            role=Role.BUILDER,
            action="foundation.memory.write",
            policy_decision=PolicyDecision(True, "fixture"),
            lease_actions={"foundation.memory.write"},
            adapter_actions={"foundation.memory.write"},
            mission_risk_allowed=True,
            budget_available=True,
            tenant_id="tenant:test",
            repository_id="repository:test",
            actor_id="builder",
            decision_id="decision:fixture",
            lease_id="lease:fixture",
        )
        self.assertTrue(allowed.allowed)
        self.assertIs(allowed.mapped_action, Action.WRITE_WORKSPACE)
        missing_lease = decide_foundation_write(
            role=Role.BUILDER,
            action="foundation.memory.write",
            policy_decision=PolicyDecision(True, "fixture"),
            lease_actions=None,
            adapter_actions={"foundation.memory.write"},
            mission_risk_allowed=True,
            budget_available=True,
        )
        self.assertFalse(missing_lease.allowed)
        untrusted_telemetry = decide_foundation_write(
            role=Role.BUILDER,
            action="foundation.telemetry.write",
            policy_decision=PolicyDecision(True, "fixture"),
            lease_actions={"foundation.telemetry.write"},
            adapter_actions={"foundation.telemetry.write"},
            mission_risk_allowed=True,
            budget_available=True,
            recorder_identity="agent-self",
        )
        self.assertFalse(untrusted_telemetry.allowed)


class FoundationStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "foundation.sqlite3"
        self.store = FoundationStore(self.path)
        self.store.register_repository(
            REPOSITORY_IDENTITY,
            authority=allowed_authority("foundation.repository.register"),
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def _append(
        self,
        key: str = "memory:one",
        payload: dict | None = None,
        *,
        authority: AuthorityDecision | None = None,
        sensitivity: str = "private",
        destination: str = "local",
        actor_id: str = "builder",
        repository_id: str = "repository:test",
        observed_at: str | None = None,
        approve_public_release: bool = False,
    ) -> dict:
        content_digest = digest("safe-reference")
        document = {
            "record_type": "memory-record",
            "schema_version": 1,
            "memory_id": key,
            "memory_kind": "semantic",
            "repository_id": repository_id,
            "tenant_id": "tenant:test",
            "mission_id": None,
            "run_id": None,
            "step_id": None,
            "actor_id": "builder",
            "payload_digest": content_digest,
            "previous_record_id": None,
            "supersedes_record_id": None,
            "observed_at": "2026-07-28T00:00:00+00:00",
            "recorded_at": "2026-07-28T00:00:00+00:00",
            "causation_id": None,
            "correlation_id": None,
            "source_refs": [],
            "claim_refs": [],
            "evidence_refs": ["fixture:evidence"],
            "court_refs": [],
            "code_receipt_refs": [],
            "generation_refs": [],
            "status": "active",
            "confidence_ppm": None,
            "freshness_expires_at": None,
            "contradiction_refs": [],
            "relation_refs": [],
            "owner_id": "builder",
            "sensitivity": "private",
            "access_purpose": "test",
            "retention": "governed",
            "deletion_policy": "tombstone",
            "quarantine_state": "none",
            "appeal_state": "available",
            "content_digest": content_digest,
            "protected_content_ref": None,
            "retrieval_receipt": None,
        }
        if payload:
            document.update(payload)
        selected_authority = authority or allowed_authority(
                "foundation.memory.write",
                repository_id=repository_id,
                actor_id=actor_id,
                public_release_allowed=approve_public_release,
                public_release_subject_digest=(
                    digest(document) if approve_public_release else None
                ),
            )
        return self.store.append_record(
            authority=selected_authority,
            foundation_action="foundation.memory.write",
            tenant_id="tenant:test",
            repository_id=repository_id,
            record_type="memory-record",
            schema_name="memory-record-v1",
            stream_id="memory:stream",
            payload=document,
            actor_id=actor_id,
            idempotency_key=key,
            sensitivity=sensitivity,
            destination=destination,
            observed_at=observed_at,
        )

    def test_wal_record_and_outbox_are_atomic_append_only_and_recoverable(self) -> None:
        record = self._append()
        self.assertEqual(self.store.journal_mode().casefold(), "wal")
        pending = self.store.pending_outbox(
            tenant_id="tenant:test", repository_id="repository:test"
        )
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["source_record_id"], record["record_id"])
        for statement in (
            "UPDATE records SET status='changed'",
            "DELETE FROM records",
            "UPDATE outbox_messages SET destination='network'",
        ):
            with self.assertRaises(sqlite3.DatabaseError):
                with self.store._connection:
                    self.store._connection.execute(statement)
        self.store.close()
        self.store = FoundationStore(self.path)
        self.assertEqual(
            len(
                self.store.pending_outbox(
                    tenant_id="tenant:test", repository_id="repository:test"
                )
            ),
            1,
        )

    def test_idempotency_scope_and_privacy_fail_closed(self) -> None:
        original = self._append()
        replay = self._append()
        self.assertEqual(replay["record_id"], original["record_id"])
        with self.assertRaises(IdempotencyConflict):
            self._append(
                payload={
                    "content_digest": digest("different"),
                    "payload_digest": digest("different"),
                }
            )
        with self.assertRaises(ScopeError):
            self.store.records(tenant_id="", repository_id="repository:test")
        with self.assertRaises(ValueError):
            self._append("memory:secret", {"prompt": "do not persist"})

    def test_writes_enforce_action_scope_public_release_and_full_command(self) -> None:
        denied = decide_foundation_write(
            role=Role.BUILDER,
            action="foundation.memory.write",
            policy_decision=PolicyDecision(False, "denied"),
            lease_actions={"foundation.memory.write"},
            adapter_actions={"foundation.memory.write"},
            mission_risk_allowed=True,
            budget_available=True,
        )
        with self.assertRaises(PermissionError):
            self._append("memory:denied", authority=denied)
        with self.assertRaises(PermissionError):
            self._append(
                "memory:public-denied",
                {"sensitivity": "safe-public"},
                sensitivity="safe-public",
            )
        public = self._append(
            "memory:public",
            {"sensitivity": "safe-public"},
            sensitivity="safe-public",
            approve_public_release=True,
        )
        self.assertEqual(public["sensitivity"], "safe-public")
        self.assertEqual(public["public_release_decision_id"], "release:curator-approved")
        self.assertEqual(public["public_release_decided_by"], "curator")
        self.assertEqual(
            public["public_release_subject_digest"], public["semantic_digest"]
        )
        original = self._append("memory:full-command")
        self.assertEqual(
            self._append("memory:full-command")["record_id"],
            original["record_id"],
        )
        for command in (
            {"destination": "different"},
            {"actor_id": "different"},
        ):
            with self.assertRaises(IdempotencyConflict):
                self._append("memory:full-command", **command)
        explicit = self._append(
            "memory:observed-command",
            observed_at="2000-01-01T00:00:00+00:00",
        )
        self.assertEqual(
            explicit["command_observed_at"], "2000-01-01T00:00:00+00:00"
        )
        with self.assertRaises(IdempotencyConflict):
            self._append(
                "memory:observed-command",
                observed_at="2099-01-01T00:00:00+00:00",
            )
        with self.assertRaises(ScopeError):
            self._append(
                "memory:wrong-scope",
                {"repository_id": "repository:other"},
            )
        with self.assertRaises(PermissionError):
            self.store.append_record(
                authority=allowed_authority("foundation.memory.write"),
                foundation_action="foundation.memory.write",
                tenant_id="tenant:test",
                repository_id="repository:test",
                record_type="usage-event",
                schema_name="usage-event-v1",
                stream_id="usage:forbidden",
                payload={},
                actor_id="builder",
                idempotency_key="usage:forbidden",
            )

    def test_schema_validation_and_store_admission_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            self.store.append_record(
                authority=allowed_authority("foundation.memory.write"),
                foundation_action="foundation.memory.write",
                tenant_id="tenant:test",
                repository_id="repository:test",
                record_type="memory-record",
                schema_name="memory-record-v1",
                stream_id="memory:invalid",
                payload={"record_type": "memory-record", "schema_version": 1},
                actor_id="builder",
                idempotency_key="memory:invalid",
            )
        with self.assertRaises(ValueError):
            self._append(
                "memory:type-mismatch",
                {"record_type": "opportunity-record"},
            )
        with tempfile.TemporaryDirectory() as temporary:
            legacy_path = Path(temporary) / "evidence-ledger.sqlite3"
            legacy = EvidenceLedger(legacy_path)
            legacy.close()
            before = sqlite3.connect(legacy_path)
            try:
                before_objects = before.execute(
                    "SELECT type,name,sql FROM sqlite_master ORDER BY type,name"
                ).fetchall()
                before_version = before.execute("PRAGMA user_version").fetchone()[0]
            finally:
                before.close()
            with self.assertRaisesRegex(RuntimeError, "non-empty unversioned"):
                FoundationStore(legacy_path)
            after = sqlite3.connect(legacy_path)
            try:
                self.assertEqual(
                    after.execute(
                        "SELECT type,name,sql FROM sqlite_master ORDER BY type,name"
                    ).fetchall(),
                    before_objects,
                )
                self.assertEqual(
                    after.execute("PRAGMA user_version").fetchone()[0],
                    before_version,
                )
            finally:
                after.close()

    def test_all_canonical_memory_kinds_and_retrieval_receipts_validate(self) -> None:
        kinds = (
            "working",
            "episodic",
            "semantic",
            "procedural",
            "prospective",
            "decision",
            "opportunity",
            "counterfactual",
            "social",
            "evaluation",
            "resource",
            "governance",
            "not-applicable",
        )
        for kind in kinds:
            with self.subTest(kind=kind):
                record = self._append(
                    f"memory:kind:{kind}",
                    {
                        "memory_kind": kind,
                        "retrieval_receipt": (
                            {
                                "selected_memory_ids": ["memory:selected"],
                                "omitted_memory_ids": ["memory:omitted"],
                                "ordering": ["memory:selected"],
                                "purpose": "mission-context",
                                "policy_result": "allowed",
                                "critical_context_coverage": "complete",
                            }
                            if kind == "working"
                            else None
                        ),
                    },
                )
                self.assertEqual(record["payload"]["memory_kind"], kind)

    def test_same_version_shape_and_cross_scope_self_relation_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            malformed_path = Path(temporary) / "malformed.sqlite3"
            connection = sqlite3.connect(malformed_path)
            connection.executescript(
                "CREATE TABLE unrelated(value TEXT); PRAGMA user_version=1;"
            )
            before = connection.execute(
                "SELECT type,name,sql FROM sqlite_master ORDER BY type,name"
            ).fetchall()
            connection.close()
            with self.assertRaises(RuntimeError):
                FoundationStore(malformed_path)
            verifier = sqlite3.connect(malformed_path)
            try:
                self.assertEqual(
                    verifier.execute(
                        "SELECT type,name,sql FROM sqlite_master ORDER BY type,name"
                    ).fetchall(),
                    before,
                )
            finally:
                verifier.close()

        other_identity = {
            **REPOSITORY_IDENTITY,
            "repository_id": "repository:other",
            "instance_id": "instance:other",
        }
        self.store.register_repository(
            other_identity,
            authority=allowed_authority(
                "foundation.repository.register",
                repository_id="repository:other",
            ),
        )
        other = self._append(
            "memory:other",
            repository_id="repository:other",
        )
        with self.assertRaises(ScopeError):
            self.store.add_relation(
                authority=allowed_authority("foundation.memory.write"),
                foundation_action="foundation.memory.write",
                tenant_id="tenant:test",
                repository_id="repository:test",
                source_record_id=other["record_id"],
                target_record_id=other["record_id"],
                relation="self",
                evidence={"receipt": digest("cross-scope")},
                actor_id="builder",
            )

    def test_interrupted_initialization_rolls_back_and_reopens(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "interrupted.sqlite3"

            def interrupt() -> str:
                raise RuntimeError("fixture initialization interruption")

            with self.assertRaisesRegex(RuntimeError, "interruption"):
                FoundationStore(path, clock=interrupt)
            connection = sqlite3.connect(path)
            try:
                tables = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
                self.assertEqual(tables, [])
                self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 0)
            finally:
                connection.close()
            reopened = FoundationStore(path)
            reopened.close()

    def test_outbox_reads_and_delivery_authority_are_repository_scoped(self) -> None:
        other_identity = {
            **REPOSITORY_IDENTITY,
            "repository_id": "repository:other",
            "instance_id": "instance:other-outbox",
        }
        self.store.register_repository(
            other_identity,
            authority=allowed_authority(
                "foundation.repository.register",
                repository_id="repository:other",
            ),
        )
        local = self._append("memory:local-scope")
        other = self._append(
            "memory:other-scope", repository_id="repository:other"
        )
        local_pending = self.store.pending_outbox(
            tenant_id="tenant:test", repository_id="repository:test"
        )
        other_pending = self.store.pending_outbox(
            tenant_id="tenant:test", repository_id="repository:other"
        )
        self.assertIn(local["record_id"], {item["source_record_id"] for item in local_pending})
        self.assertNotIn(other["record_id"], {item["source_record_id"] for item in local_pending})
        self.assertIn(other["record_id"], {item["source_record_id"] for item in other_pending})
        with self.assertRaises(PermissionError):
            self.store.record_delivery_attempt(
                other_pending[0]["message_id"],
                "local",
                "succeeded",
                authority=allowed_authority("foundation.outbox.deliver"),
                tenant_id="tenant:test",
                repository_id="repository:other",
                actor_id="builder",
            )

    def test_delivery_replay_uses_append_only_attempt_and_ack_receipts(self) -> None:
        self._append()
        message = self.store.pending_outbox(
            tenant_id="tenant:test", repository_id="repository:test"
        )[0]
        self.store.record_delivery_attempt(
            message["message_id"],
            "local",
            "failed",
            authority=allowed_authority("foundation.outbox.deliver"),
            tenant_id="tenant:test",
            repository_id="repository:test",
            actor_id="builder",
            error_class="SinkUnavailable",
        )
        self.assertEqual(
            len(
                self.store.pending_outbox(
                    tenant_id="tenant:test", repository_id="repository:test"
                )
            ),
            1,
        )
        with self.assertRaises(ScopeError):
            self.store.record_delivery_attempt(
                message["message_id"],
                "wrong-destination",
                "succeeded",
                authority=allowed_authority("foundation.outbox.deliver"),
                tenant_id="tenant:test",
                repository_id="repository:test",
                actor_id="builder",
            )
        with self.assertRaises(ValueError):
            self.store.acknowledge(
                message["message_id"],
                "local",
                "",
                authority=allowed_authority("foundation.outbox.deliver"),
                tenant_id="tenant:test",
                repository_id="repository:test",
                actor_id="builder",
            )
        with self.assertRaises(RuntimeError):
            self.store.acknowledge(
                message["message_id"],
                "local",
                "sink:receipt",
                authority=allowed_authority("foundation.outbox.deliver"),
                tenant_id="tenant:test",
                repository_id="repository:test",
                actor_id="builder",
            )
        self.store.record_delivery_attempt(
            message["message_id"],
            "local",
            "succeeded",
            authority=allowed_authority("foundation.outbox.deliver"),
            tenant_id="tenant:test",
            repository_id="repository:test",
            actor_id="builder",
        )
        self.store.acknowledge(
            message["message_id"],
            "local",
            "sink:receipt",
            authority=allowed_authority("foundation.outbox.deliver"),
            tenant_id="tenant:test",
            repository_id="repository:test",
            actor_id="builder",
        )
        self.store.acknowledge(
            message["message_id"],
            "local",
            "sink:receipt",
            authority=allowed_authority("foundation.outbox.deliver"),
            tenant_id="tenant:test",
            repository_id="repository:test",
            actor_id="builder",
        )
        self.assertEqual(
            self.store.pending_outbox(
                tenant_id="tenant:test", repository_id="repository:test"
            ),
            [],
        )
        with self.assertRaises(IdempotencyConflict):
            self.store.acknowledge(
                message["message_id"],
                "local",
                "sink:conflicting-receipt",
                authority=allowed_authority("foundation.outbox.deliver"),
                tenant_id="tenant:test",
                repository_id="repository:test",
                actor_id="builder",
            )
        self.assertEqual(
            self.store.verify_integrity(
                tenant_id="tenant:test", repository_id="repository:test"
            ),
            (),
        )

    def test_integrity_detects_schema_and_content_tampering(self) -> None:
        record = self._append("memory:integrity")
        self.store._connection.execute("DROP TRIGGER records_no_update")
        with self.store._connection:
            self.store._connection.execute(
                "UPDATE records SET actor_id='tampered' WHERE record_id=?",
                (record["record_id"],),
            )
        issues = self.store.verify_integrity(
            tenant_id="tenant:test", repository_id="repository:test"
        )
        self.assertTrue(any("store schema integrity failed" in issue for issue in issues))
        self.assertTrue(any("command digest mismatch" in issue for issue in issues))


class OpportunityLedgerTests(unittest.TestCase):
    def test_exact_concurrent_duplicates_preserve_encounters_and_converge(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "foundation.sqlite3"
            initializer = FoundationStore(path)
            initializer.register_repository(
                REPOSITORY_IDENTITY,
                authority=allowed_authority("foundation.repository.register"),
            )
            initializer.close()
            barrier = threading.Barrier(2)
            results = []
            failures = []

            def register(encounter_id: str) -> None:
                store = FoundationStore(path)
                try:
                    barrier.wait()
                    result = OpportunityLedger(
                        store,
                        authority=allowed_authority(
                            "foundation.opportunity.write", role=Role.EXPLORER
                        ),
                    ).register(
                        tenant_id="tenant:test",
                        repository_id="repository:test",
                        encounter_id=encounter_id,
                        problem="  Duplicate   failures ",
                        proposal="Use one canonical key",
                        structured_key={"component": "ledger", "kind": "duplicate"},
                        actor_id="explorer",
                        evidence_digests=[digest(encounter_id)],
                    )
                    results.append(result)
                except BaseException as error:
                    failures.append(error)
                finally:
                    store.close()

            threads = [
                threading.Thread(target=register, args=(f"encounter:{index}",))
                for index in range(2)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(failures, [])
            self.assertEqual(len(results), 2)
            opportunity_ids = {
                result.opportunity_record_id
                for result in results
                if result.opportunity_record_id is not None
            }
            self.assertEqual(len(opportunity_ids), 1)
            verifier = FoundationStore(path)
            try:
                self.assertEqual(
                    len(
                        verifier.records(
                            tenant_id="tenant:test",
                            repository_id="repository:test",
                            record_type="idea-encounter",
                        )
                    ),
                    2,
                )
                self.assertEqual(
                    len(
                        verifier.records(
                            tenant_id="tenant:test",
                            repository_id="repository:test",
                            record_type="opportunity-record",
                        )
                    ),
                    1,
                )
            finally:
                verifier.close()

    def test_semantic_candidate_never_auto_merges(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = FoundationStore(Path(temporary) / "foundation.sqlite3")
            store.register_repository(
                REPOSITORY_IDENTITY,
                authority=allowed_authority("foundation.repository.register"),
            )
            ledger = OpportunityLedger(
                store,
                authority=allowed_authority(
                    "foundation.opportunity.write", role=Role.EXPLORER
                ),
            )
            first = ledger.register(
                tenant_id="tenant:test",
                repository_id="repository:test",
                encounter_id="encounter:first",
                problem="one",
                proposal="one",
                structured_key={"key": "one"},
                actor_id="explorer",
                evidence_digests=[digest("one")],
            )
            candidate = ledger.register(
                tenant_id="tenant:test",
                repository_id="repository:test",
                encounter_id="encounter:second",
                problem="similar but distinct",
                proposal="different",
                structured_key={"key": "two"},
                actor_id="explorer",
                evidence_digests=[digest("two")],
                semantic_candidate_ids=[str(first.opportunity_record_id)],
                semantic_evidence={
                    "algorithm_id": "fixture-neighbor-search",
                    "algorithm_version": "1",
                    "index_digest": digest("fixture-index"),
                    "threshold_ppm": 800_000,
                    "neighbor_scores_ppm": {
                        str(first.opportunity_record_id): 900_000
                    },
                },
            )
            self.assertEqual(candidate.classification, "semantic-candidate")
            self.assertIsNone(candidate.opportunity_record_id)
            ledger.classify_semantic_candidate(
                tenant_id="tenant:test",
                repository_id="repository:test",
                encounter_record_id=candidate.encounter_record_id,
                opportunity_record_id=str(first.opportunity_record_id),
                relationship="not-duplicate",
                evidence={"review_digest": digest("independent")},
                actor_id="explorer",
            )
            store.close()

    def test_semantic_candidates_require_typed_targets_and_prior_staging(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = FoundationStore(Path(temporary) / "foundation.sqlite3")
            store.register_repository(
                REPOSITORY_IDENTITY,
                authority=allowed_authority("foundation.repository.register"),
            )
            memory_store_test = FoundationStoreTests("_append")
            memory_store_test.store = store
            memory = memory_store_test._append("memory:not-an-opportunity")
            ledger = OpportunityLedger(
                store,
                authority=allowed_authority(
                    "foundation.opportunity.write", role=Role.EXPLORER
                ),
            )
            semantic_evidence = {
                "algorithm_id": "fixture-neighbor-search",
                "algorithm_version": "1",
                "index_digest": digest("fixture-index"),
                "threshold_ppm": 800_000,
                "neighbor_scores_ppm": {memory["record_id"]: 900_000},
            }
            with self.assertRaises(ScopeError):
                ledger.register(
                    tenant_id="tenant:test",
                    repository_id="repository:test",
                    encounter_id="encounter:wrong-type",
                    problem="wrong type",
                    proposal="must fail",
                    structured_key={"key": "wrong-type"},
                    actor_id="explorer",
                    evidence_digests=[digest("wrong-type")],
                    semantic_candidate_ids=[memory["record_id"]],
                    semantic_evidence=semantic_evidence,
                )
            with self.assertRaisesRegex(ValueError, "staged typed candidate"):
                ledger.classify_semantic_candidate(
                    tenant_id="tenant:test",
                    repository_id="repository:test",
                    encounter_record_id=memory["record_id"],
                    opportunity_record_id=memory["record_id"],
                    relationship="duplicate",
                    evidence={"review_digest": digest("unstaged")},
                    actor_id="explorer",
                )
            store.close()

    def test_integrity_binds_opportunity_keys_to_typed_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = FoundationStore(Path(temporary) / "foundation.sqlite3")
            store.register_repository(
                REPOSITORY_IDENTITY,
                authority=allowed_authority("foundation.repository.register"),
            )
            ledger = OpportunityLedger(
                store,
                authority=allowed_authority(
                    "foundation.opportunity.write", role=Role.EXPLORER
                ),
            )
            ledger.register(
                tenant_id="tenant:test",
                repository_id="repository:test",
                encounter_id="encounter:integrity",
                problem="integrity",
                proposal="bind keys",
                structured_key={"key": "integrity"},
                actor_id="explorer",
                evidence_digests=[digest("integrity")],
            )
            store._connection.execute("DROP TRIGGER opportunity_keys_no_update")
            store._connection.execute(
                "UPDATE opportunity_keys SET exact_digest=?",
                (digest("tampered-key"),),
            )
            issues = store.verify_integrity(
                tenant_id="tenant:test", repository_id="repository:test"
            )
            self.assertTrue(
                any("opportunity key" in issue and "target mismatch" in issue for issue in issues)
            )
            store.close()

    def test_integrity_rejects_cross_repository_opportunity_key_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = FoundationStore(Path(temporary) / "foundation.sqlite3")
            store.register_repository(
                REPOSITORY_IDENTITY,
                authority=allowed_authority("foundation.repository.register"),
            )
            other_identity = {
                **REPOSITORY_IDENTITY,
                "repository_id": "repository:other",
                "instance_id": "instance:other",
            }
            store.register_repository(
                other_identity,
                authority=allowed_authority(
                    "foundation.repository.register",
                    repository_id="repository:other",
                ),
            )
            first = OpportunityLedger(
                store,
                authority=allowed_authority(
                    "foundation.opportunity.write", role=Role.EXPLORER
                ),
            ).register(
                tenant_id="tenant:test",
                repository_id="repository:test",
                encounter_id="encounter:first-scope",
                problem="first scope",
                proposal="keep first scope",
                structured_key={"key": "first"},
                actor_id="explorer",
                evidence_digests=[digest("first-scope")],
            )
            second = OpportunityLedger(
                store,
                authority=allowed_authority(
                    "foundation.opportunity.write",
                    role=Role.EXPLORER,
                    repository_id="repository:other",
                ),
            ).register(
                tenant_id="tenant:test",
                repository_id="repository:other",
                encounter_id="encounter:second-scope",
                problem="second scope",
                proposal="keep second scope",
                structured_key={"key": "second"},
                actor_id="explorer",
                evidence_digests=[digest("second-scope")],
            )
            self.assertNotEqual(
                first.opportunity_record_id, second.opportunity_record_id
            )
            store._connection.execute("DROP TRIGGER opportunity_keys_no_update")
            store._connection.execute(
                "UPDATE opportunity_keys SET opportunity_record_id=? "
                "WHERE repository_id=?",
                (second.opportunity_record_id, "repository:test"),
            )
            store._connection.execute(
                "CREATE TRIGGER opportunity_keys_no_update "
                "BEFORE UPDATE ON opportunity_keys BEGIN SELECT "
                "RAISE(ABORT, 'opportunity_keys is append-only'); END"
            )
            issues = store.verify_integrity(
                tenant_id="tenant:test", repository_id="repository:test"
            )
            self.assertTrue(
                any("opportunity key" in issue and "target mismatch" in issue for issue in issues)
            )
            store.close()


class UsageAndObservabilityTests(unittest.TestCase):
    def _fixture(self, name: str) -> bytes:
        return (FIXTURES / name).read_bytes()

    def test_provider_fixtures_preserve_native_and_orthogonal_axes(self) -> None:
        openai = ProviderUsageAdapter.parse(
            "openai_compatible", self._fixture("openai_usage.json")
        )
        self.assertEqual(openai["native"]["prompt_tokens"], 100)
        self.assertEqual(openai["normalized_axes"]["direction"]["input"], 100)
        self.assertEqual(openai["normalized_axes"]["cache_input"]["read"], 25)
        self.assertEqual(openai["normalized_axes"]["cache_input"]["uncached"], 75)
        self.assertEqual(
            openai["normalized_axes"]["output_kind"]["reasoning_subset"], 10
        )
        anthropic = ProviderUsageAdapter.parse(
            "anthropic", self._fixture("anthropic_usage.json")
        )
        self.assertEqual(anthropic["normalized_axes"]["cache_input"]["uncached"], 90)
        missing = ProviderUsageAdapter.parse(
            "openai_compatible", self._fixture("missing_usage.json")
        )
        self.assertEqual(missing["accounting_status"], "unknown")
        malformed = ProviderUsageAdapter.parse(
            "openai_compatible", self._fixture("malformed_usage.json")
        )
        self.assertEqual(malformed["native"], {})
        self.assertEqual(malformed["unmapped_path_count"], 3)
        conflicting = ProviderUsageAdapter.parse(
            "openai_compatible",
            b'{"usage":{"prompt_tokens":2,"completion_tokens":3,"total_tokens":99}}',
        )
        self.assertEqual(
            conflicting["normalized_axes"]["direction"]["status"], "conflicting"
        )

    def test_attempt_terminal_is_durable_and_restart_recovers_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "foundation.sqlite3"
            store = FoundationStore(path)
            store.register_repository(
                REPOSITORY_IDENTITY,
                authority=allowed_authority("foundation.repository.register"),
            )
            recorder = UsageRecorder(
                store,
                tenant_id="tenant:test",
                repository_id="repository:test",
                authority=allowed_authority("foundation.telemetry.write"),
            )
            completed = recorder.start_attempt(
                logical_request_id="request:one",
                retry_index=0,
                provider_kind="openai_compatible",
                requested_model_id="requested",
                purpose="build",
                actor_id="builder",
                request_digest=digest("request"),
                budget_lease_id=None,
                trace_id="trace:one",
            )
            recorder.finish_attempt(
                attempt_id=completed,
                logical_request_id="request:one",
                provider_kind="openai_compatible",
                outcome="succeeded",
                duration_ms=12,
                response=ModelResponse(
                    "{}",
                    self._fixture("openai_usage.json"),
                    100,
                    40,
                ),
            )
            interrupted = recorder.start_attempt(
                logical_request_id="request:two",
                retry_index=0,
                provider_kind="anthropic",
                requested_model_id="requested",
                purpose="validate",
                actor_id="curator",
                request_digest=digest("request-two"),
                budget_lease_id=None,
                trace_id="trace:two",
                attribution=UsageAttribution(
                    mission_id="mission:recover",
                    run_id="run:recover",
                    step_id="step:recover",
                    role="curator",
                    work_item_id="work:recover",
                    prompt_layer_digest=digest("recover-prompt"),
                    context_digest=digest("recover-context"),
                    memory_selection_digest=digest("recover-memory"),
                    selected_count=5,
                    omitted_count=1,
                ),
            )
            store.close()
            reopened = FoundationStore(path)
            recovered = UsageRecorder(
                reopened,
                tenant_id="tenant:test",
                repository_id="repository:test",
                authority=allowed_authority("foundation.telemetry.write"),
            ).recover_interrupted()
            self.assertEqual(recovered, (interrupted,))
            records = reopened.records(
                tenant_id="tenant:test",
                repository_id="repository:test",
                record_type="usage-event",
            )
            terminals = [
                record["payload"]
                for record in records
                if record["payload"]["event_kind"] == "attempt-terminal"
            ]
            self.assertEqual(len(terminals), 2)
            self.assertEqual(
                {terminal["accounting_status"] for terminal in terminals},
                {"reported", "unknown"},
            )
            recovered_terminal = next(
                terminal
                for terminal in terminals
                if terminal["attempt_id"] == interrupted
            )
            self.assertEqual(
                recovered_terminal["correlation"]["mission_id"], "mission:recover"
            )
            self.assertEqual(
                recovered_terminal["inputs"]["memory_selection_digest"],
                digest("recover-memory"),
            )
            self.assertEqual(recovered_terminal["inputs"]["selected_count"], 5)
            reopened.close()

    def test_terminal_without_durable_start_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = FoundationStore(Path(temporary) / "foundation.sqlite3")
            store.register_repository(
                REPOSITORY_IDENTITY,
                authority=allowed_authority("foundation.repository.register"),
            )
            recorder = UsageRecorder(
                store,
                tenant_id="tenant:test",
                repository_id="repository:test",
                authority=allowed_authority("foundation.telemetry.write"),
            )
            with self.assertRaisesRegex(ValueError, "durable start"):
                recorder.finish_attempt(
                    attempt_id="attempt:missing",
                    logical_request_id="request:missing",
                    provider_kind="anthropic",
                    outcome="provider-failure",
                    duration_ms=0,
                    response=None,
                )
            store.close()

    def test_opt_in_provider_receipts_are_durable_before_return(self) -> None:
        class FixtureProvider:
            kind = ProviderKind.OPENAI_COMPATIBLE
            config = ProviderConfig(
                ProviderKind.OPENAI_COMPATIBLE,
                "https://example.invalid/v1",
                "fixture-model",
                "UNUSED_KEY",
            )

            def build_request_body(self, request: ModelRequest) -> bytes:
                return json.dumps(
                    {"system": request.system, "user": request.user},
                    sort_keys=True,
                ).encode()

            def complete_once(self, request: ModelRequest) -> ModelResponse:
                return ModelResponse(
                    "{}",
                    (FIXTURES / "openai_usage.json").read_bytes(),
                    100,
                    40,
                )

            def complete(self, request: ModelRequest) -> ModelResponse:
                return self.complete_once(request)

        with tempfile.TemporaryDirectory() as temporary:
            store = FoundationStore(Path(temporary) / "foundation.sqlite3")
            store.register_repository(
                REPOSITORY_IDENTITY,
                authority=allowed_authority("foundation.repository.register"),
            )
            recorder = UsageRecorder(
                store,
                tenant_id="tenant:test",
                repository_id="repository:test",
                authority=allowed_authority("foundation.telemetry.write"),
            )
            provider = ReceiptedModelProvider(
                FixtureProvider(),
                recorder,
                purpose="fixture",
                actor_id="builder",
                trace_id="trace:provider",
                attribution=UsageAttribution(
                    mission_id="mission:one",
                    run_id="run:one",
                    step_id="step:one",
                    role="builder",
                    work_item_id="work:one",
                    prompt_layer_digest=digest("prompt-layers"),
                    context_digest=digest("context"),
                    memory_selection_digest=digest("memory-selection"),
                    selected_count=3,
                    omitted_count=2,
                    access_audit_ref="access:one",
                ),
            )
            response = provider.complete_once(ModelRequest("system", "user"))
            self.assertEqual(response.prompt_tokens, 100)
            records = store.records(
                tenant_id="tenant:test",
                repository_id="repository:test",
                record_type="usage-event",
            )
            self.assertEqual(
                [record["payload"]["event_kind"] for record in records],
                ["attempt-started", "attempt-terminal"],
            )
            self.assertEqual(records[-1]["payload"]["accounting_status"], "reported")
            unbounded_contract = json.loads(json.dumps(records[-1]["payload"]))
            unbounded_contract["normalized_axes"]["direction"]["input"] = 10**15 + 1
            self.assertFalse(
                validate_foundation("usage-event-v1", unbounded_contract).valid
            )
            forged_contract = json.loads(json.dumps(records[-1]["payload"]))
            forged_contract["correlation"]["mission_id"] = "x" * 100_000
            forged_contract["inputs"]["prompt_layer_digest"] = "not-a-digest"
            forged_contract["inputs"]["selected_count"] = 10**30
            self.assertFalse(
                validate_foundation("usage-event-v1", forged_contract).valid
            )
            for record in records:
                self.assertEqual(
                    record["payload"]["correlation"]["mission_id"], "mission:one"
                )
                self.assertEqual(
                    record["payload"]["correlation"]["work_item_id"], "work:one"
                )
                self.assertEqual(
                    record["payload"]["inputs"]["memory_selection_digest"],
                    digest("memory-selection"),
                )
                self.assertEqual(record["payload"]["inputs"]["selected_count"], 3)
                self.assertEqual(
                    record["payload"]["governance"]["access_audit_ref"],
                    "access:one",
                )
            forged_attribution = UsageAttribution(mission_id="mission:valid")
            object.__setattr__(
                forged_attribution,
                "mission_id",
                "x" * 100_000,
            )
            object.__setattr__(
                forged_attribution,
                "prompt_layer_digest",
                "not-a-digest",
            )
            object.__setattr__(
                forged_attribution,
                "selected_count",
                10**30,
            )
            with self.assertRaises(ValueError):
                recorder.start_attempt(
                    logical_request_id="request:forged-attribution",
                    retry_index=0,
                    provider_kind="openai_compatible",
                    requested_model_id="requested",
                    purpose="fixture",
                    actor_id="builder",
                    request_digest=digest("forged-attribution"),
                    budget_lease_id=None,
                    trace_id="trace:forged-attribution",
                    attribution=forged_attribution,
                )
            store.close()

    def test_physical_attempt_ids_are_unique_and_retry_semantics_are_preserved(
        self,
    ) -> None:
        class RetryProvider:
            kind = ProviderKind.OPENAI_COMPATIBLE
            config = ProviderConfig(
                ProviderKind.OPENAI_COMPATIBLE,
                "https://example.invalid/v1",
                "fixture-model",
                "UNUSED_KEY",
                max_retries=1,
            )

            def __init__(self, *, fail_once: bool) -> None:
                self.fail_once = fail_once
                self.calls = 0

            def build_request_body(self, request: ModelRequest) -> bytes:
                return json.dumps(
                    {"system": request.system, "user": request.user},
                    sort_keys=True,
                ).encode()

            def complete_once(self, request: ModelRequest) -> ModelResponse:
                self.calls += 1
                if self.fail_once and self.calls == 1:
                    raise ModelTransportError("fixture transport failure")
                return ModelResponse(
                    "{}",
                    (FIXTURES / "openai_usage.json").read_bytes(),
                    100,
                    40,
                )

            def complete(self, request: ModelRequest) -> ModelResponse:
                return self.complete_once(request)

        with tempfile.TemporaryDirectory() as temporary:
            store = FoundationStore(Path(temporary) / "foundation.sqlite3")
            store.register_repository(
                REPOSITORY_IDENTITY,
                authority=allowed_authority("foundation.repository.register"),
            )
            recorder = UsageRecorder(
                store,
                tenant_id="tenant:test",
                repository_id="repository:test",
                authority=allowed_authority("foundation.telemetry.write"),
            )
            request = ModelRequest("system", "user")
            for _ in range(2):
                ReceiptedModelProvider(
                    RetryProvider(fail_once=False),
                    recorder,
                    purpose="unique-attempt",
                    actor_id="builder",
                    trace_id="trace:unique",
                ).complete_once(request)
            records = store.records(
                tenant_id="tenant:test",
                repository_id="repository:test",
                record_type="usage-event",
            )
            start_ids = [
                record["payload"]["attempt_id"]
                for record in records
                if record["payload"]["event_kind"] == "attempt-started"
            ]
            self.assertEqual(len(start_ids), 2)
            self.assertEqual(len(set(start_ids)), 2)

            retry_provider = RetryProvider(fail_once=True)
            response = ReceiptedModelProvider(
                retry_provider,
                recorder,
                purpose="retry-attempt",
                actor_id="builder",
                trace_id="trace:retry",
            ).complete(request)
            self.assertEqual(response.transport_retry_index, 1)
            self.assertEqual(retry_provider.calls, 2)
            retry_records = [
                record["payload"]
                for record in store.records(
                    tenant_id="tenant:test",
                    repository_id="repository:test",
                    record_type="usage-event",
                )
                if record["payload"]["identity"]["court_purpose"] == "retry-attempt"
            ]
            self.assertEqual(
                [
                    item["resources"]["retry_index"]
                    for item in retry_records
                    if item["event_kind"] == "attempt-started"
                ],
                [0, 1],
            )
            self.assertEqual(
                [
                    item["outcome"]
                    for item in retry_records
                    if item["event_kind"] == "attempt-terminal"
                ],
                ["provider-failure", "succeeded"],
            )
            store.close()

    def test_provider_native_observation_is_bounded_and_path_allowlisted(self) -> None:
        usage = {f"secret_{index}": index for index in range(5_000)}
        usage["api_key"] = 123
        observation = ProviderUsageAdapter.parse(
            "openai_compatible",
            json.dumps({"usage": usage}).encode(),
        )
        self.assertEqual(observation["native"], {})
        self.assertGreater(observation["unmapped_path_count"], 128)
        self.assertNotIn("api_key", json.dumps(observation))
        oversized_integer = ProviderUsageAdapter.parse(
            "openai_compatible",
            (
                b'{"usage":{"prompt_tokens":'
                + (b"9" * 5_000)
                + b',"completion_tokens":1}}'
            ),
        )
        self.assertEqual(oversized_integer["accounting_status"], "unknown")
        self.assertEqual(oversized_integer["observation_failure"], "invalid-json")
        bounded_parser_integer = ProviderUsageAdapter.parse(
            "openai_compatible",
            (
                b'{"usage":{"prompt_tokens":'
                + (b"9" * 4_000)
                + b',"completion_tokens":1}}'
            ),
        )
        self.assertEqual(bounded_parser_integer["accounting_status"], "unknown")
        self.assertIsNone(
            bounded_parser_integer["normalized_axes"]["direction"]["input"]
        )
        self.assertNotIn("prompt_tokens", bounded_parser_integer["native"])
        oversized_id = ProviderUsageAdapter.parse(
            "openai_compatible",
            json.dumps(
                {
                    "id": "x" * 900_000,
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                }
            ).encode(),
        )
        self.assertIsNone(oversized_id["provider_request_id"])
        self.assertEqual(
            oversized_id["observation_failure"],
            "provider-identity-size-limit",
        )

    def test_axis_conflicts_propagate_and_cross_axes_are_never_summed(self) -> None:
        direction = ProviderUsageAdapter.parse(
            "openai_compatible",
            b'{"usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":99}}',
        )
        cache = ProviderUsageAdapter.parse(
            "anthropic",
            b'{"usage":{"input_tokens":10,"output_tokens":5,'
            b'"cache_read_input_tokens":11}}',
        )
        reasoning = ProviderUsageAdapter.parse(
            "openai_compatible",
            b'{"usage":{"prompt_tokens":10,"completion_tokens":5,'
            b'"completion_tokens_details":{"reasoning_tokens":6}}}',
        )
        for observation in (direction, cache, reasoning):
            self.assertEqual(observation["accounting_status"], "conflicting")
        reconciled = reconcile_usage_axes(
            [
                {
                    "source": "provider-report",
                    "axis": "direction",
                    "dimension": "input",
                    "value": 100,
                },
                {
                    "source": "host-report",
                    "axis": "direction",
                    "dimension": "input",
                    "value": 100,
                },
                {
                    "source": "provider-report",
                    "axis": "cache_input",
                    "dimension": "read",
                    "value": 25,
                },
                {
                    "source": "provider-report",
                    "axis": "output_kind",
                    "dimension": "reasoning_subset",
                    "value": 10,
                },
                {
                    "source": "provider-report",
                    "axis": "billable",
                    "dimension": "status",
                    "value": "billable",
                },
                {
                    "source": "invoice",
                    "axis": "billable",
                    "dimension": "status",
                    "value": "billable",
                },
            ]
        )
        self.assertEqual(
            reconciled.double_count_guard, "orthogonal-axes-never-summed"
        )
        self.assertEqual(len(reconciled.axes), 4)
        self.assertEqual(
            next(axis for axis in reconciled.axes if axis["axis"] == "billable")[
                "status"
            ],
            "complete",
        )
        self.assertFalse(
            any("aggregate" in key for axis in reconciled.axes for key in axis)
        )
        for billable_status in (
            "billable",
            "non-billable",
            "unavailable",
            "unknown",
        ):
            with self.subTest(billable_status=billable_status):
                billable = reconcile_usage_axes(
                    [
                        {
                            "source": "provider-report",
                            "axis": "billable",
                            "dimension": "status",
                            "value": billable_status,
                        }
                    ]
                )
                self.assertEqual(billable.axes[0]["status"], "complete")
        conflicting_billable = reconcile_usage_axes(
            [
                {
                    "source": "provider-report",
                    "axis": "billable",
                    "dimension": "status",
                    "value": "billable",
                },
                {
                    "source": "invoice",
                    "axis": "billable",
                    "dimension": "status",
                    "value": "non-billable",
                },
            ]
        )
        self.assertEqual(conflicting_billable.axes[0]["status"], "conflicting")
        with self.assertRaises(ValueError):
            reconcile_usage_axes(
                [
                    {
                        "source": "provider-report",
                        "axis": "billable",
                        "dimension": "status",
                        "value": "invented",
                    }
                ]
            )

    def test_invoice_reconciliation_never_manufactures_equality(self) -> None:
        usage = [
            {"event_kind": "attempt-terminal", "attempt_id": "attempt:one"},
            {"event_kind": "attempt-terminal", "attempt_id": "attempt:two"},
        ]
        unavailable = reconcile_invoice(usage, None)
        self.assertTrue(unavailable.unavailable)
        self.assertEqual(unavailable.missing_attempt_ids, ("attempt:one", "attempt:two"))
        partial = reconcile_invoice(
            usage,
            [
                {"attempt_id": "attempt:one", "amount": "0.10", "currency": "USD"},
                {"attempt_id": "attempt:one", "amount": "0.10", "currency": "USD"},
                {"attempt_id": "invoice-only", "amount": "0.20", "currency": "USD"},
            ],
        )
        self.assertEqual(partial.status, "conflicting")
        self.assertEqual(partial.duplicate_attempt_ids, ("attempt:one",))
        self.assertEqual(partial.missing_attempt_ids, ("attempt:two",))

    def test_metrics_are_bounded_and_traces_carry_correlation_without_bodies(self) -> None:
        point = project_metric(
            "hive.foundation.records",
            1,
            {"record_type": "usage-event", "outcome": "succeeded"},
        )
        self.assertEqual(point.value, 1)
        with self.assertRaises(ValueError):
            project_metric(
                "hive.foundation.records", 1, {"repository_id": "repository:test"}
            )
        with self.assertRaises(ValueError):
            project_metric("hive.foundation.arbitrary", 1, {})
        with self.assertRaises(ValueError):
            project_metric("hive.foundation.records", 10**15 + 1, {})
        trace = project_trace(
            "model.attempt",
            trace_id="trace:one",
            span_id="span:one",
            attributes={"attempt_id": "attempt:one", "outcome": "succeeded"},
        )
        self.assertEqual(trace.trace_id, "trace:one")
        otel = project_otel_envelope(
            trace, provider_kind="openai_compatible", outcome="succeeded"
        )
        self.assertFalse(otel.export_enabled)
        self.assertEqual(otel.event_name, "gen_ai.client.operation")
        with self.assertRaises(ValueError):
            project_trace(
                "model.attempt",
                trace_id="trace:one",
                span_id="span:one",
                attributes={"prompt": "private"},
            )
        for field in (
            "request_body",
            "api_key",
            "authorization",
            "password",
            "gen_ai.provider.name",
            "hive.outcome",
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                project_trace(
                    "model.attempt",
                    trace_id="trace:one",
                    span_id="span:one",
                    attributes={field: "untrusted"},
                )
        with self.assertRaises(ValueError):
            project_trace(
                "x" * 100_000,
                trace_id="trace:one",
                span_id="span:one",
                attributes={},
            )
        with self.assertRaises(ValueError):
            project_trace(
                "model.attempt",
                trace_id="trace:one",
                span_id="span:one",
                attributes={f"field_{index}": index for index in range(10_000)},
            )
        with self.assertRaises(ValueError):
            project_otel_envelope(
                trace, provider_kind="x" * 1_000, outcome="succeeded"
            )
        with self.assertRaises(ValueError):
            TraceRecord(
                "x" * 100_000,
                "trace" * 1_000,
                "span" * 1_000,
                (("request_body", "SECRET"),),
            )
        forged = TraceRecord("model.attempt", "trace:one", "span:one", ())
        object.__setattr__(
            forged,
            "attributes",
            (("request_body", "SECRET"),),
        )
        with self.assertRaises(ValueError):
            project_otel_envelope(
                forged,
                provider_kind="openai_compatible",
                outcome="succeeded",
            )


if __name__ == "__main__":
    unittest.main()
