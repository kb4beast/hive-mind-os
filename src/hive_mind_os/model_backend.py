"""Structured model backend and append-only ``model.call`` receipt payload.

Each event records provider kind, base URL host, model, role/work item, bounded parameter
summary, request/response SHA-256 digests, reported token counts, retry indices, duration,
context truncation, and outcome. Prompt/response bodies and credential values are excluded.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict
from hashlib import sha256
from typing import Any, Mapping
from urllib.parse import urlsplit

from .autonomy import AutonomyBudget, BudgetExceeded
from .contracts import validate_contract
from .ledger import EvidenceLedger
from .model_provider import (
    ModelProvider,
    ModelProviderError,
    ModelRequest,
    ModelResponse,
    ModelResponseError,
    redact,
)
from .models import AgentResult, Evidence, Objective, Role, WorkItem
from .roles import RoleContract


class ModelTurnError(RuntimeError):
    """Raised after bounded retries cannot produce a valid structured turn."""


def _digest(content: bytes) -> str:
    return f"sha256:{sha256(content).hexdigest()}"


class ModelBackend:
    def __init__(
        self,
        provider: ModelProvider,
        *,
        ledger: EvidenceLedger | None = None,
        budget: AutonomyBudget | None = None,
        context_limit_chars: int = 8000,
        role_providers: Mapping[Role, ModelProvider] | None = None,
    ) -> None:
        if context_limit_chars < 1:
            raise ValueError("context limit must be positive")
        self.provider = provider
        self.role_providers = dict(role_providers or {})
        self.ledger = ledger or EvidenceLedger()
        self.budget = budget or AutonomyBudget(
            max_episodes=10_000,
            max_tool_calls=10_000,
            max_compute_units=10_000.0,
        )
        self.context_limit_chars = context_limit_chars

    async def execute(
        self,
        contract: RoleContract,
        work_item: WorkItem,
        objective: Objective,
        context: tuple[AgentResult, ...],
    ) -> AgentResult:
        system, user, truncated = self._prompt(
            contract, work_item, objective, context
        )
        corrective: str | None = None
        last_error = "model did not return a valid turn"
        provider = self.role_providers.get(contract.role, self.provider)
        context_manifest = self._context_manifest(
            context,
            role=contract.role,
            provider=provider,
        )
        allowance = self.budget.issue_allowance()
        used_calls = 0
        used_compute = 0.0
        try:
            for retry_index in range(provider.config.max_retries + 1):
                request = ModelRequest(system, user, corrective)
                body = provider.build_request_body(request)
                response: ModelResponse | None = None
                started = time.monotonic()
                estimated_tokens = max(1, len(body) // 4)
                request_compute = (
                    estimated_tokens + provider.config.max_output_tokens
                ) / 1000.0
                if (
                    used_calls + 1 > allowance.tool_calls
                    or used_compute + request_compute > allowance.compute_units
                ):
                    raise BudgetExceeded("role-turn allowance exhausted before model request")
                used_calls += 1
                used_compute += request_compute
                try:
                    response = await asyncio.to_thread(
                        provider.complete_once, request
                    )
                    turn = self._parse_turn(response.content, contract)
                    self._record_call(
                        objective,
                        contract,
                        work_item,
                        body,
                        response,
                        retry_index,
                        time.monotonic() - started,
                        "succeeded",
                        truncated,
                        provider,
                        context_manifest,
                    )
                    return self._to_result(turn, contract, work_item)
                except ModelTurnError as error:
                    last_error = str(error)
                    self._record_call(
                        objective, contract, work_item, body, response, retry_index,
                        time.monotonic() - started, "invalid_output", truncated,
                        provider, context_manifest,
                        error=last_error,
                    )
                    corrective = (
                        "Your previous response was invalid. Return only JSON matching the "
                        f"required contract. Validation error: {last_error}"
                    )
                except ModelProviderError as error:
                    if isinstance(error, ModelResponseError):
                        response = ModelResponse("", error.raw_body, None, None)
                    last_error = redact(str(error))
                    self._record_call(
                        objective, contract, work_item, body, response, retry_index,
                        time.monotonic() - started, "provider_failure", truncated,
                        provider, context_manifest,
                        error=last_error,
                    )
                    if retry_index >= provider.config.max_retries:
                        raise
            raise ModelTurnError(
                f"model output remained invalid after "
                f"{provider.config.max_retries + 1} attempts: {last_error}"
            )
        finally:
            if used_calls:
                self.budget.consume(
                    allowance, tool_calls=used_calls, compute_units=used_compute
                )

    def _prompt(
        self,
        contract: RoleContract,
        work_item: WorkItem,
        objective: Objective,
        context: tuple[AgentResult, ...],
    ) -> tuple[str, str, bool]:
        system = (
            "You are the Hive Mind OS specialist for role "
            f"{contract.role.value}. Mission: {contract.mission}\n"
            "Return only a JSON object with summary, outputs, proposed_actions, lessons, "
            "and success. outputs must contain exactly these keys: "
            + ", ".join(contract.required_outputs)
            + ". Quality gates: "
            + "; ".join(contract.quality_gates)
        )
        rendered = json.dumps(
            [
                {
                    "role": item.role.value,
                    "summary": item.summary,
                    "evidence": [asdict(evidence) for evidence in item.evidence],
                }
                for item in context
            ],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        truncated = len(rendered) > self.context_limit_chars
        if truncated:
            rendered = rendered[: self.context_limit_chars]
        user = json.dumps(
            {
                "objective": objective.goal,
                "acceptance_criteria": list(objective.acceptance_criteria),
                "constraints": list(objective.constraints),
                "base_workspace": objective.repository,
                "work_item": work_item.instruction,
                "prior_context_json": rendered,
                "context_truncated": truncated,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return system, user, truncated

    @staticmethod
    def _parse_turn(content: str, contract: RoleContract) -> dict[str, Any]:
        try:
            turn = json.loads(content)
        except json.JSONDecodeError as error:
            raise ModelTurnError(f"invalid JSON: {error.msg}") from None
        validation = validate_contract("model-turn", turn)
        if not validation.valid:
            raise ModelTurnError("; ".join(validation.issues))
        if not isinstance(turn, dict) or not isinstance(turn.get("outputs"), dict):
            raise ModelTurnError("turn outputs must be an object")
        expected = set(contract.required_outputs)
        observed = set(turn["outputs"])
        if observed != expected:
            raise ModelTurnError(
                f"outputs must match required names; missing={sorted(expected - observed)} "
                f"unexpected={sorted(observed - expected)}"
            )
        return turn

    @staticmethod
    def _to_result(
        turn: dict[str, Any],
        contract: RoleContract,
        work_item: WorkItem,
    ) -> AgentResult:
        outputs = turn["outputs"]
        return AgentResult(
            role=contract.role,
            work_item_id=work_item.id,
            summary=turn["summary"],
            evidence=tuple(
                Evidence(
                    kind="contract-output",
                    summary=name,
                    source=f"model:{contract.role.value}",
                    payload={"content": outputs[name]},
                )
                for name in contract.required_outputs
            ),
            proposed_actions=tuple(turn["proposed_actions"]),
            lessons=tuple(turn["lessons"]),
            success=turn["success"],
        )

    def _record_call(
        self,
        objective: Objective,
        contract: RoleContract,
        work_item: WorkItem,
        request_body: bytes,
        response: ModelResponse | None,
        retry_index: int,
        duration_s: float,
        outcome: str,
        context_truncated: bool,
        provider: ModelProvider,
        context_manifest: Mapping[str, object],
        *,
        error: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "provider_kind": provider.kind.value,
            "base_url_host": urlsplit(provider.config.base_url).hostname,
            "model_id": provider.config.model,
            "provider_configuration": (
                "shared"
                if provider.config == self.provider.config
                else "role-override"
            ),
            "role": contract.role.value,
            "work_item_id": work_item.id,
            "request": {
                "temperature": provider.config.temperature,
                "max_output_tokens": provider.config.max_output_tokens,
                "api_key_env": provider.config.api_key_env,
            },
            "request_digest": _digest(request_body),
            "response_digest": _digest(response.raw_body) if response else None,
            "prompt_tokens": response.prompt_tokens if response else None,
            "completion_tokens": response.completion_tokens if response else None,
            "retry_index": retry_index,
            "transport_retry_index": (
                response.transport_retry_index if response else None
            ),
            "duration_ms": round(duration_s * 1000, 3),
            "context_truncated": context_truncated,
            "context_manifest": dict(context_manifest),
            "outcome": outcome,
            "error": error,
        }
        self.ledger.append_event(
            objective.id, "model.call", contract.role.value, payload
        )

    def identity_for_role(self, role: Role) -> dict[str, str]:
        """Expose the effective role provider for mission context receipts."""

        provider = self.role_providers.get(role, self.provider)
        return {
            "provider_kind": provider.kind.value,
            "model_id": provider.config.model,
            "configuration": (
                "shared"
                if provider.config == self.provider.config
                else "role-override"
            ),
        }

    def _context_manifest(
        self,
        context: tuple[AgentResult, ...],
        *,
        role: Role,
        provider: ModelProvider,
    ) -> dict[str, object]:
        return {
            "role": role.value,
            "prior_roles": [item.role.value for item in context],
            "summaries": [item.summary for item in context],
            "receipt_digests": [
                digest
                for item in context
                for evidence in item.evidence
                for digest in evidence.payload.get("receipt_digests", [])
                if isinstance(digest, str)
            ],
            "provider_kind": provider.kind.value,
            "model_id": provider.config.model,
            "provider_configuration": (
                "shared"
                if provider.config == self.provider.config
                else "role-override"
            ),
        }
