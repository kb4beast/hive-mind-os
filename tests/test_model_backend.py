from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import pytest

from hive_mind_os.autonomy import AutonomyBudget, BudgetExceeded
from hive_mind_os.cli import build_parser
from hive_mind_os.ledger import EvidenceLedger
from hive_mind_os.model_backend import ModelBackend, ModelTurnError
from hive_mind_os.model_provider import (
    ModelRequest,
    ModelResponse,
    ProviderConfig,
    ProviderKind,
)
from hive_mind_os.models import Objective, Role, WorkItem, WorkStatus
from hive_mind_os.roles import ROLE_CONTRACTS
from hive_mind_os.runtime import HiveKernel


def valid_turn(role: Role) -> str:
    return json.dumps(
        {
            "summary": f"{role.value} complete",
            "outputs": {
                name: f"evidence for {name}"
                for name in ROLE_CONTRACTS[role].required_outputs
            },
            "proposed_actions": [],
            "lessons": ["structured output validated"],
            "success": True,
        },
        sort_keys=True,
    )


@dataclass
class FakeProvider:
    responses: list[str]

    def __post_init__(self) -> None:
        self.config = ProviderConfig(
            ProviderKind.OPENAI_COMPATIBLE,
            "https://models.example/v1",
            "fake-model",
            "FAKE_KEY_ENV",
            max_retries=2,
        )
        self.kind = ProviderKind.OPENAI_COMPATIBLE
        self.calls: list[ModelRequest] = []

    def build_request_body(self, request: ModelRequest) -> bytes:
        return json.dumps(
            {
                "system": request.system,
                "user": request.user,
                "corrective": request.corrective_message,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        content = self.responses.pop(0)
        raw = json.dumps({"content": content}, sort_keys=True).encode()
        return ModelResponse(content, raw, 10, 5)

    def complete_once(self, request: ModelRequest) -> ModelResponse:
        return self.complete(request)


def execute_once(
    backend: ModelBackend, role: Role = Role.ARCHITECT
):
    objective = Objective("Produce a verified change")
    work_item = WorkItem(objective.id, role, "Do bounded work")
    return asyncio.run(
        backend.execute(ROLE_CONTRACTS[role], work_item, objective, ())
    )


def test_valid_turn_passes_kernel_result_validation() -> None:
    backend = ModelBackend(FakeProvider([valid_turn(Role.ARCHITECT)]))
    result = execute_once(backend)
    HiveKernel._validate_result(Role.ARCHITECT, result)


def test_malformed_json_retries_then_succeeds() -> None:
    ledger = EvidenceLedger()
    provider = FakeProvider(["{", valid_turn(Role.ARCHITECT)])
    result = execute_once(ModelBackend(provider, ledger=ledger))
    assert result.success
    events = [event for event in ledger.events() if event["event_type"] == "model.call"]
    assert [event["payload"]["retry_index"] for event in events] == [0, 1]
    assert events[0]["payload"]["outcome"] == "invalid_output"


def test_persistently_malformed_output_fails_without_result() -> None:
    ledger = EvidenceLedger()
    provider = FakeProvider(["{", "{", "{"])
    with pytest.raises(ModelTurnError):
        execute_once(ModelBackend(provider, ledger=ledger))
    events = [event for event in ledger.events() if event["event_type"] == "model.call"]
    assert len(events) == 3
    assert all(event["payload"]["outcome"] == "invalid_output" for event in events)


def test_budget_exhaustion_prevents_provider_call() -> None:
    provider = FakeProvider([valid_turn(Role.ARCHITECT)])
    budget = AutonomyBudget(1, 0, 100.0)
    with pytest.raises(BudgetExceeded):
        execute_once(ModelBackend(provider, budget=budget))
    assert provider.calls == []


def test_receipt_is_complete_and_contains_no_api_key() -> None:
    ledger = EvidenceLedger()
    provider = FakeProvider([valid_turn(Role.ARCHITECT)])
    execute_once(ModelBackend(provider, ledger=ledger))
    payload = ledger.events()[0]["payload"]
    assert payload["request_digest"].startswith("sha256:")
    assert payload["response_digest"].startswith("sha256:")
    assert payload["model_id"] == "fake-model"
    assert payload["role"] == "architect"
    assert payload["retry_index"] == 0
    assert (payload["prompt_tokens"], payload["completion_tokens"]) == (10, 5)
    assert "sentinel-key" not in json.dumps(payload)


def test_context_truncation_request_digest_is_deterministic() -> None:
    provider_one = FakeProvider([valid_turn(Role.ARCHITECT)])
    provider_two = FakeProvider([valid_turn(Role.ARCHITECT)])
    objective = Objective("same", id="objective-fixed", created_at="2026-07-27T00:00:00Z")
    work_item = WorkItem(
        objective.id,
        Role.ARCHITECT,
        "same instruction",
        id="work-fixed",
        created_at="2026-07-27T00:00:00Z",
    )
    ledgers = [EvidenceLedger(), EvidenceLedger()]
    for provider, ledger in zip((provider_one, provider_two), ledgers, strict=True):
        backend = ModelBackend(provider, ledger=ledger, context_limit_chars=4)
        asyncio.run(
            backend.execute(
                ROLE_CONTRACTS[Role.ARCHITECT], work_item, objective, ()
            )
        )
    assert (
        ledgers[0].events()[0]["payload"]["request_digest"]
        == ledgers[1].events()[0]["payload"]["request_digest"]
    )


def test_offline_model_backend_completes_all_eight_roles() -> None:
    provider = FakeProvider([valid_turn(role) for role in HiveKernel().lifecycle])
    report = asyncio.run(
        HiveKernel(backend=ModelBackend(provider)).run_objective(
            Objective("Run the full structured lifecycle")
        )
    )
    assert report.status is WorkStatus.SUCCEEDED
    assert len(report.results) == 8


def test_cli_backend_flag_preserves_deterministic_default() -> None:
    parser = build_parser()
    assert parser.parse_args(["offline"]).backend == "deterministic"
    assert parser.parse_args(["offline", "--backend", "model"]).backend == "model"
