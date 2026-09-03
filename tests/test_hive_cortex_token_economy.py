from __future__ import annotations

import asyncio
import json
import unittest

from hive_mind_os.ledger import EvidenceLedger
from hive_mind_os.model_backend import ContextEnvelope, ModelBackend
from hive_mind_os.model_provider import ModelResponse, ProviderConfig, ProviderKind
from hive_mind_os.models import AgentResult, Evidence, Objective, Role, WorkItem
from hive_mind_os.roles import ROLE_CONTRACTS
from hive_mind_os.token_ledger import (
    PurposeCalibration,
    TokenAccountingError,
    TokenLedger,
    TokenMeasurement,
    TokenRecord,
    TokenSource,
    calibrate,
    calibration_document,
    measure_call,
)

DIGEST = "sha256:" + "c" * 64


class _Provider:
    kind = ProviderKind.OPENAI_COMPATIBLE

    def __init__(self) -> None:
        self.config = ProviderConfig(
            self.kind,
            "https://provider.example/v1",
            "test-model",
            "TEST_API_KEY",
            max_retries=0,
        )

    @property
    def credential_reference(self) -> str:
        return "test-double"

    def build_request_body(self, request) -> bytes:
        return json.dumps(
            {"system": request.system, "user": request.user},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    def complete_once(self, request) -> ModelResponse:
        role = Role.EXPLORER
        turn = {
            "summary": "measured result",
            "outputs": {
                name: f"output:{name}" for name in ROLE_CONTRACTS[role].required_outputs
            },
            "proposed_actions": [],
            "lessons": [],
            "success": True,
        }
        content = json.dumps(turn)
        return ModelResponse(content, content.encode(), 41, 7)


def _backend_inputs():
    objective = Objective("bounded investigation")
    work = WorkItem(objective.id, Role.EXPLORER, "inspect evidence")
    return ROLE_CONTRACTS[Role.EXPLORER], work, objective


def _record(index: int, *, sample_count_ready: bool = True) -> TokenRecord:
    return TokenRecord(
        run_id="run-one",
        role="explorer",
        work_item_id=f"work-{index}",
        outcome="succeeded",
        retry_index=0,
        measurement=TokenMeasurement(
            10 + index,
            5,
            TokenSource.MEASURED,
            TokenSource.MEASURED,
            None,
        ),
        context_manifest_digest=DIGEST,
        omitted_role_count=1,
        purpose="bounded_read_only_research",
        avoided_input_tokens=100 if sample_count_ready else None,
        coordination_tokens=2,
    )


class TokenLedgerTests(unittest.TestCase):
    def test_provider_counts_are_recorded_as_measured(self) -> None:
        measurement = measure_call(
            request_bytes=400,
            prompt_tokens=91,
            completion_tokens=17,
            max_output_tokens=100,
            cache_read_tokens=12,
        )
        self.assertIs(TokenSource.MEASURED, measurement.input_source)
        self.assertIs(TokenSource.MEASURED, measurement.output_source)
        self.assertIs(TokenSource.MEASURED, measurement.cache_source)
        self.assertEqual((91, 17, 12), (measurement.input_tokens, measurement.output_tokens, measurement.cache_read_tokens))

    def test_missing_counts_use_named_estimator_only_where_derivable(self) -> None:
        measurement = measure_call(
            request_bytes=400,
            prompt_tokens=None,
            completion_tokens=None,
            max_output_tokens=100,
        )
        self.assertEqual(100, measurement.input_tokens)
        self.assertIs(TokenSource.ESTIMATED, measurement.input_source)
        self.assertEqual("bytes-div-4", measurement.estimator)
        self.assertIsNone(measurement.output_tokens)
        self.assertIs(TokenSource.UNAVAILABLE, measurement.output_source)

    def test_unavailable_counts_are_never_reported_as_zero(self) -> None:
        measurement = measure_call(
            request_bytes=None,
            prompt_tokens=None,
            completion_tokens=None,
            max_output_tokens=100,
        )
        self.assertIsNone(measurement.input_tokens)
        self.assertIsNone(measurement.output_tokens)
        self.assertIs(TokenSource.UNAVAILABLE, measurement.input_source)
        self.assertIs(TokenSource.UNAVAILABLE, measurement.output_source)

    def test_estimated_source_requires_an_estimator_name(self) -> None:
        with self.assertRaises(TokenAccountingError):
            TokenMeasurement(
                10,
                None,
                TokenSource.ESTIMATED,
                TokenSource.UNAVAILABLE,
                None,
            )

    def test_single_token_ledger_appends_complete_hash_chained_record(self) -> None:
        evidence = EvidenceLedger()
        self.addCleanup(evidence.close)
        ledger = TokenLedger(evidence)
        record = _record(1)
        sequence = ledger.record(record)
        event = evidence.events()[0]
        self.assertEqual(1, sequence)
        self.assertEqual("token.accounting", event["event_type"])
        self.assertEqual(record.record_digest, event["payload"]["record_digest"])
        self.assertEqual(1, event["payload"]["call_count"])
        self.assertEqual(0, event["payload"]["fallback_count"])
        with self.assertRaises(TokenAccountingError):
            ledger.record(record)

    def test_model_call_event_carries_additive_token_accounting(self) -> None:
        evidence = EvidenceLedger()
        self.addCleanup(evidence.close)
        backend = ModelBackend(_Provider(), ledger=evidence)
        contract, work, objective = _backend_inputs()
        asyncio.run(backend.execute(contract, work, objective, ()))
        payload = evidence.events()[0]["payload"]
        self.assertEqual((41, 7), (payload["prompt_tokens"], payload["completion_tokens"]))
        self.assertEqual("measured", payload["token_accounting"]["input_source"])
        self.assertEqual("measured", payload["token_accounting"]["output_source"])

    def test_calibration_is_deterministic_and_refuses_to_extrapolate(self) -> None:
        sparse = calibrate(tuple(_record(index) for index in range(4)))
        self.assertEqual("insufficient", sparse[0].confidence)
        self.assertEqual(0, sparse[0].observed_net_savings_tokens)
        enough = tuple(_record(index) for index in range(5))
        first = calibrate(enough)
        second = calibrate(enough)
        self.assertEqual(first, second)
        self.assertEqual("provisional", first[0].confidence)
        self.assertGreater(first[0].observed_net_savings_tokens, 0)

    def test_calibration_document_is_canonical_json(self) -> None:
        calibrations = (
            PurposeCalibration("review", 5, 10, 5, 20, "provisional"),
            PurposeCalibration("build", 10, 20, 10, 30, "calibrated"),
        )
        first = json.dumps(calibration_document(calibrations), sort_keys=True, separators=(",", ":"))
        second = json.dumps(calibration_document(tuple(reversed(calibrations))), sort_keys=True, separators=(",", ":"))
        self.assertEqual(first, second)


class ContextEnvelopeTests(unittest.TestCase):
    def test_envelope_over_budget_fails_closed(self) -> None:
        backend = ModelBackend(_Provider())
        self.addCleanup(backend.ledger.close)
        contract, work, objective = _backend_inputs()
        envelope = ContextEnvelope(DIGEST, 9, 10, (), (), (), (), False)
        with self.assertRaisesRegex(ValueError, "exceeds its declared token budget"):
            backend._prompt(contract, work, objective, (), None, envelope)

    def test_envelope_is_not_character_truncated_and_receipt_excludes_body(self) -> None:
        secret_body = "bounded-body-" + "x" * 2_000
        backend = ModelBackend(_Provider(), context_limit_chars=8)
        self.addCleanup(backend.ledger.close)
        contract, work, objective = _backend_inputs()
        envelope = ContextEnvelope(
            DIGEST,
            100,
            50,
            (("orchestrator", secret_body),),
            (),
            (),
            ("memory:cold",),
            False,
        )
        _, user, truncated, _ = backend._prompt(
            contract, work, objective, (), None, envelope
        )
        self.assertFalse(truncated)
        self.assertIn(secret_body, user)
        self.assertNotIn(secret_body, json.dumps(envelope.to_receipt(), sort_keys=True))

    def test_legacy_backend_path_retains_whole_record_truncation(self) -> None:
        backend = ModelBackend(_Provider(), context_limit_chars=64)
        self.addCleanup(backend.ledger.close)
        contract, work, objective = _backend_inputs()
        prior = AgentResult(
            role=Role.ORCHESTRATOR,
            work_item_id="work-prior",
            summary="x" * 1_000,
            evidence=(Evidence("fact", "prior", "test", {"value": "x" * 100}),),
        )
        _, user, truncated, _ = backend._prompt(
            contract, work, objective, (prior,), None
        )
        self.assertTrue(truncated)
        rendered = json.loads(json.loads(user)["prior_context_json"])
        self.assertEqual(["orchestrator"], rendered["omitted_roles"])


if __name__ == "__main__":
    unittest.main()
