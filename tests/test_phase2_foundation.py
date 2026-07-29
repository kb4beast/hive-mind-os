from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

import hive_mind_os
from hive_mind_os.foundation.authority import decide_foundation_write
from hive_mind_os.foundation.canonical import digest
from hive_mind_os.foundation.contracts import (
    PHASE2_SCHEMA_NAMES,
    validate_foundation,
    validate_foundation_catalog,
)
from hive_mind_os.foundation.generation import (
    compile_generation_zero_candidates,
    verify_generated_candidates,
)
from hive_mind_os.foundation.observability import (
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
    UsageRecorder,
    reconcile_invoice,
)
from hive_mind_os.model_provider import (
    ModelRequest,
    ModelResponse,
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

    def test_contracts_fail_closed_on_unknown_fields(self) -> None:
        candidate = json.loads(
            compile_generation_zero_candidates()["agents/explorer.json"]
        )
        candidate["self_granted_authority"] = True
        result = validate_foundation("agent-definition-v2", candidate)
        self.assertFalse(result.valid)
        self.assertIn("unknown properties", result.issues[0])
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

    def test_authority_is_an_intersection_and_telemetry_is_recorder_only(self) -> None:
        allowed = decide_foundation_write(
            role=Role.BUILDER,
            action="foundation.memory.write",
            policy_decision=PolicyDecision(True, "fixture"),
            lease_actions={"foundation.memory.write"},
            adapter_actions={"foundation.memory.write"},
            mission_risk_allowed=True,
            budget_available=True,
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
        self.store.register_repository(REPOSITORY_IDENTITY)

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def _append(self, key: str = "memory:one", payload: dict | None = None) -> dict:
        return self.store.append_record(
            tenant_id="tenant:test",
            repository_id="repository:test",
            record_type="memory",
            schema_name="memory-record-v1",
            stream_id="memory:stream",
            payload=payload or {"content_digest": digest("safe-reference")},
            actor_id="builder",
            idempotency_key=key,
        )

    def test_wal_record_and_outbox_are_atomic_append_only_and_recoverable(self) -> None:
        record = self._append()
        self.assertEqual(self.store.journal_mode().casefold(), "wal")
        pending = self.store.pending_outbox()
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
        self.assertEqual(len(self.store.pending_outbox()), 1)

    def test_idempotency_scope_and_privacy_fail_closed(self) -> None:
        original = self._append()
        replay = self._append()
        self.assertEqual(replay["record_id"], original["record_id"])
        with self.assertRaises(IdempotencyConflict):
            self._append(payload={"content_digest": digest("different")})
        with self.assertRaises(ScopeError):
            self.store.records(tenant_id="", repository_id="repository:test")
        with self.assertRaises(ValueError):
            self._append("memory:secret", {"prompt": "do not persist"})

    def test_delivery_replay_uses_append_only_attempt_and_ack_receipts(self) -> None:
        self._append()
        message = self.store.pending_outbox()[0]
        self.store.record_delivery_attempt(
            message["message_id"], "local", "failed", error_class="SinkUnavailable"
        )
        self.assertEqual(len(self.store.pending_outbox()), 1)
        self.store.acknowledge(message["message_id"], "local", "sink:receipt")
        self.store.acknowledge(message["message_id"], "local", "sink:receipt")
        self.assertEqual(self.store.pending_outbox(), [])
        with self.assertRaises(IdempotencyConflict):
            self.store.acknowledge(
                message["message_id"], "local", "sink:conflicting-receipt"
            )
        self.assertEqual(
            self.store.verify_integrity(
                tenant_id="tenant:test", repository_id="repository:test"
            ),
            (),
        )


class OpportunityLedgerTests(unittest.TestCase):
    def test_exact_concurrent_duplicates_preserve_encounters_and_converge(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "foundation.sqlite3"
            initializer = FoundationStore(path)
            initializer.register_repository(REPOSITORY_IDENTITY)
            initializer.close()
            barrier = threading.Barrier(2)
            results = []
            failures = []

            def register(encounter_id: str) -> None:
                store = FoundationStore(path)
                try:
                    barrier.wait()
                    result = OpportunityLedger(store).register(
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
                            record_type="opportunity",
                        )
                    ),
                    1,
                )
            finally:
                verifier.close()

    def test_semantic_candidate_never_auto_merges(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = FoundationStore(Path(temporary) / "foundation.sqlite3")
            store.register_repository(REPOSITORY_IDENTITY)
            ledger = OpportunityLedger(store)
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
        self.assertIn("private_note", malformed["unmapped_paths"])
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
            store.register_repository(REPOSITORY_IDENTITY)
            recorder = UsageRecorder(
                store, tenant_id="tenant:test", repository_id="repository:test"
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
            )
            store.close()
            reopened = FoundationStore(path)
            recovered = UsageRecorder(
                reopened, tenant_id="tenant:test", repository_id="repository:test"
            ).recover_interrupted()
            self.assertEqual(recovered, (interrupted,))
            records = reopened.records(
                tenant_id="tenant:test",
                repository_id="repository:test",
                record_type="usage-attempt",
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
            reopened.close()

    def test_terminal_without_durable_start_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = FoundationStore(Path(temporary) / "foundation.sqlite3")
            store.register_repository(REPOSITORY_IDENTITY)
            recorder = UsageRecorder(
                store, tenant_id="tenant:test", repository_id="repository:test"
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
            store.register_repository(REPOSITORY_IDENTITY)
            recorder = UsageRecorder(
                store, tenant_id="tenant:test", repository_id="repository:test"
            )
            provider = ReceiptedModelProvider(
                FixtureProvider(),
                recorder,
                purpose="fixture",
                actor_id="builder",
                trace_id="trace:provider",
            )
            response = provider.complete_once(ModelRequest("system", "user"))
            self.assertEqual(response.prompt_tokens, 100)
            records = store.records(
                tenant_id="tenant:test",
                repository_id="repository:test",
                record_type="usage-attempt",
            )
            self.assertEqual(
                [record["payload"]["event_kind"] for record in records],
                ["attempt-started", "attempt-terminal"],
            )
            self.assertEqual(records[-1]["payload"]["accounting_status"], "reported")
            store.close()

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
            {"record_type": "usage-attempt", "outcome": "succeeded"},
        )
        self.assertEqual(point.value, 1)
        with self.assertRaises(ValueError):
            project_metric(
                "hive.foundation.records", 1, {"repository_id": "repository:test"}
            )
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


if __name__ == "__main__":
    unittest.main()
