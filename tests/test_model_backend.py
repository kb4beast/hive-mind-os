from __future__ import annotations

import asyncio
import io
import json
import os
import unittest
import urllib.error
from dataclasses import dataclass
from hashlib import sha256
from unittest.mock import patch

from hive_mind_os.autonomy import AutonomyBudget, BudgetExceeded
from hive_mind_os.cli import build_parser
from hive_mind_os.ledger import EvidenceLedger
from hive_mind_os.model_backend import ModelBackend, ModelTurnError
from hive_mind_os.model_provider import (
    ModelRequest,
    ModelResponse,
    ModelResponseError,
    OpenAICompatibleProvider,
    ProviderConfig,
    ProviderKind,
)
from hive_mind_os.models import (
    AgentResult,
    Evidence,
    Objective,
    Role,
    WorkItem,
    WorkStatus,
)
from hive_mind_os.roles import ROLE_CONTRACTS
from hive_mind_os.runtime import HiveKernel


def valid_turn(role: Role) -> str:
    return json.dumps({
        "summary": f"{role.value} complete",
        "outputs": {name: f"evidence for {name}" for name in ROLE_CONTRACTS[role].required_outputs},
        "proposed_actions": [], "lessons": ["structured output validated"], "success": True,
    }, sort_keys=True)


@dataclass
class FakeProvider:
    responses: list[str]

    def __post_init__(self) -> None:
        self.config = ProviderConfig(
            ProviderKind.OPENAI_COMPATIBLE, "https://models.example/v1",
            "fake-model", "FAKE_KEY_ENV", max_retries=2,
        )
        self.kind = ProviderKind.OPENAI_COMPATIBLE
        self.calls: list[ModelRequest] = []

    def build_request_body(self, request: ModelRequest) -> bytes:
        return json.dumps({
            "system": request.system, "user": request.user,
            "corrective": request.corrective_message,
        }, sort_keys=True, separators=(",", ":")).encode()

    def complete_once(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        content = self.responses.pop(0)
        raw = json.dumps({"content": content}, sort_keys=True).encode()
        return ModelResponse(content, raw, 10, 5)

    def complete(self, request: ModelRequest) -> ModelResponse:
        return self.complete_once(request)


class BackendTransport:
    def __init__(self, response: bytes | BaseException) -> None:
        self.response = response
        self.calls = 0

    def post(self, url, headers, body, timeout_s):
        self.calls += 1
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


def execute_once(backend: ModelBackend, role: Role = Role.ARCHITECT, context=()):
    objective = Objective("Produce a verified change")
    work_item = WorkItem(objective.id, role, "Do bounded work")
    return asyncio.run(backend.execute(ROLE_CONTRACTS[role], work_item, objective, context))


class ModelBackendTests(unittest.TestCase):
    def test_valid_turn_passes_kernel_result_validation(self) -> None:
        result = execute_once(ModelBackend(FakeProvider([valid_turn(Role.ARCHITECT)])))
        HiveKernel._validate_result(Role.ARCHITECT, result)

    def test_malformed_json_retries_with_one_role_turn_allowance(self) -> None:
        ledger = EvidenceLedger()
        provider = FakeProvider(["{", valid_turn(Role.ARCHITECT)])
        budget = AutonomyBudget(1, 2, 100.0)
        result = execute_once(ModelBackend(provider, ledger=ledger, budget=budget))
        self.assertTrue(result.success)
        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(budget.episodes_used, 1)
        events = [e for e in ledger.events() if e["event_type"] == "model.call"]
        self.assertEqual([e["payload"]["retry_index"] for e in events], [0, 1])

    def test_persistently_malformed_output_fails_without_result(self) -> None:
        ledger = EvidenceLedger()
        with self.assertRaises(ModelTurnError):
            execute_once(ModelBackend(FakeProvider(["{", "{", "{"]), ledger=ledger))
        events = ledger.events()
        self.assertEqual(len(events), 3)
        self.assertTrue(
            all(event["payload"]["outcome"] == "invalid_output" for event in events)
        )

    def test_budget_exhaustion_prevents_provider_call(self) -> None:
        provider = FakeProvider([valid_turn(Role.ARCHITECT)])
        with self.assertRaises(BudgetExceeded):
            execute_once(ModelBackend(provider, budget=AutonomyBudget(1, 0, 100.0)))
        self.assertEqual(provider.calls, [])

    def test_integrated_receipt_contains_no_api_key(self) -> None:
        secret = "sentinel-integrated-receipt-key"
        raw = json.dumps({
            "choices": [{"message": {"content": valid_turn(Role.ARCHITECT)}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }).encode()
        transport = BackendTransport(raw)
        config = ProviderConfig(
            ProviderKind.OPENAI_COMPATIBLE, "https://models.example/v1",
            "real-shape-model", "TEST_MODEL_KEY", max_retries=0,
        )
        ledger = EvidenceLedger()
        with patch.dict(os.environ, {"TEST_MODEL_KEY": secret}):
            execute_once(ModelBackend(OpenAICompatibleProvider(config, transport), ledger=ledger))
        payload = ledger.events()[0]["payload"]
        encoded = json.dumps(payload, sort_keys=True)
        self.assertNotIn(secret, encoded)
        self.assertEqual(transport.calls, 1)
        self.assertTrue(payload["request_digest"].startswith("sha256:"))
        self.assertTrue(payload["response_digest"].startswith("sha256:"))
        self.assertEqual(payload["model_id"], "real-shape-model")
        self.assertEqual(payload["role"], "architect")
        self.assertEqual(payload["retry_index"], 0)
        self.assertEqual(
            (payload["prompt_tokens"], payload["completion_tokens"]),
            (10, 5),
        )

    def test_failed_provider_response_body_is_digested(self) -> None:
        raw = b"{not-json"
        transport = BackendTransport(raw)
        config = ProviderConfig(
            ProviderKind.OPENAI_COMPATIBLE, "https://models.example/v1",
            "model", "TEST_MODEL_KEY", max_retries=0,
        )
        ledger = EvidenceLedger()
        with patch.dict(os.environ, {"TEST_MODEL_KEY": "secret"}):
            with self.assertRaises(ModelResponseError):
                execute_once(ModelBackend(OpenAICompatibleProvider(config, transport), ledger=ledger))
        payload = ledger.events()[0]["payload"]
        self.assertEqual(payload["outcome"], "provider_failure")
        self.assertIsNotNone(payload["response_digest"])

    def test_http_error_response_body_is_digested(self) -> None:
        raw = b'{"error":"bad request"}'
        error = urllib.error.HTTPError(
            "https://models.example/v1/chat/completions",
            400,
            "bad request",
            {},
            io.BytesIO(raw),
        )
        transport = BackendTransport(error)
        config = ProviderConfig(
            ProviderKind.OPENAI_COMPATIBLE,
            "https://models.example/v1",
            "model",
            "TEST_MODEL_KEY",
            max_retries=0,
        )
        ledger = EvidenceLedger()
        with patch.dict(os.environ, {"TEST_MODEL_KEY": "secret"}):
            with self.assertRaises(ModelResponseError):
                execute_once(
                    ModelBackend(
                        OpenAICompatibleProvider(config, transport),
                        ledger=ledger,
                    )
                )
        payload = ledger.events()[0]["payload"]
        self.assertEqual(payload["outcome"], "provider_failure")
        self.assertEqual(
            payload["response_digest"],
            f"sha256:{sha256(raw).hexdigest()}",
        )

    def test_context_truncation_is_actual_and_deterministic(self) -> None:
        prior = AgentResult(
            Role.EXPLORER, "prior", "x" * 100,
            (Evidence("contract-output", "problem statement", "test", {"large": "y" * 100}),),
        )
        ledgers = [EvidenceLedger(), EvidenceLedger()]
        for ledger in ledgers:
            execute_once(
                ModelBackend(FakeProvider([valid_turn(Role.ARCHITECT)]), ledger=ledger, context_limit_chars=4),
                context=(prior,),
            )
            self.assertTrue(ledger.events()[0]["payload"]["context_truncated"])
        self.assertEqual(
            ledgers[0].events()[0]["payload"]["request_digest"],
            ledgers[1].events()[0]["payload"]["request_digest"],
        )

    def test_corrective_body_is_included_in_pre_call_budget(self) -> None:
        provider = FakeProvider(["{", valid_turn(Role.ARCHITECT)])
        budget = AutonomyBudget(1, 2, 2.6, max_compute_units_per_episode=2.6)
        with self.assertRaises(BudgetExceeded):
            execute_once(ModelBackend(provider, budget=budget))
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(budget.episodes_used, 1)

    def test_offline_backend_completes_all_roles(self) -> None:
        provider = FakeProvider([valid_turn(role) for role in HiveKernel().lifecycle])
        report = asyncio.run(HiveKernel(backend=ModelBackend(provider)).run_objective(Objective("full")))
        self.assertIs(report.status, WorkStatus.SUCCEEDED)
        self.assertEqual(len(report.results), 8)

    def test_cli_flag_preserves_deterministic_default(self) -> None:
        parser = build_parser()
        self.assertEqual(parser.parse_args(["offline"]).backend, "deterministic")
        self.assertEqual(parser.parse_args(["offline", "--backend", "model"]).backend, "model")


if __name__ == "__main__":
    unittest.main()
