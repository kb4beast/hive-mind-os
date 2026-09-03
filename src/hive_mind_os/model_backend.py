"""Structured model backend and append-only ``model.call`` receipt payload.

Each event records provider kind, base URL host, model, role/work item, bounded parameter
summary, request/response SHA-256 digests, reported token counts, retry indices, duration,
context truncation, and outcome. Prompt/response bodies and credential values are excluded.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any, Callable, Mapping
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
from .prompt_registry import PromptRegistry, generation_zero_prompt, prompt_digest
from .roles import RoleContract
from .token_ledger import measure_call


class ModelTurnError(RuntimeError):
    """Raised after bounded retries cannot produce a valid structured turn."""


@dataclass(frozen=True, slots=True)
class RepositoryContext:
    """Bounded repository facts supplied only to a repository Builder turn."""

    failing_test_stdout: str
    failing_test_stderr: str
    named_files: tuple[tuple[str, str], ...]
    file_tree: tuple[str, ...]
    current_diff: str | None

    def to_prompt(self) -> dict[str, object]:
        return {
            "failing_test": {
                "stdout": self.failing_test_stdout,
                "stderr": self.failing_test_stderr,
            },
            "named_files": [
                {"path": path, "content": content}
                for path, content in self.named_files
            ],
            "file_tree": list(self.file_tree),
            "current_diff": self.current_diff,
        }


@dataclass(frozen=True, slots=True)
class ContextEnvelope:
    """Caller-compiled, token-bound context that the backend renders verbatim."""

    manifest_digest: str
    token_budget: int
    estimated_tokens: int
    full_bodies: tuple[tuple[str, str], ...]
    digests: tuple[tuple[str, str], ...]
    omitted_roles: tuple[str, ...]
    cold_references: tuple[str, ...]
    generator_evaluator_separated: bool

    def __post_init__(self) -> None:
        if re.fullmatch(r"sha256:[0-9a-f]{64}", self.manifest_digest) is None:
            raise ValueError("context envelope manifest digest is invalid")
        if type(self.token_budget) is not int or self.token_budget < 0:
            raise ValueError("context envelope token budget must be non-negative")
        if type(self.estimated_tokens) is not int or self.estimated_tokens < 0:
            raise ValueError("context envelope estimate must be non-negative")
        if type(self.generator_evaluator_separated) is not bool:
            raise ValueError("context envelope separation flag must be boolean")
        for values, label in (
            (self.full_bodies, "full bodies"),
            (self.digests, "digests"),
        ):
            if type(values) is not tuple or any(
                type(item) is not tuple
                or len(item) != 2
                or any(type(part) is not str or not part for part in item)
                for item in values
            ):
                raise ValueError(f"context envelope {label} are invalid")
        for values, label in (
            (self.omitted_roles, "omitted roles"),
            (self.cold_references, "cold references"),
        ):
            if type(values) is not tuple or any(
                type(item) is not str or not item for item in values
            ):
                raise ValueError(f"context envelope {label} are invalid")
            if len(set(values)) != len(values):
                raise ValueError(f"context envelope {label} contain duplicates")
        full_roles = [role for role, _ in self.full_bodies]
        digest_roles = [role for role, _ in self.digests]
        all_roles = [*full_roles, *digest_roles, *self.omitted_roles]
        if len(all_roles) != len(set(all_roles)):
            raise ValueError("context envelope assigns a role to multiple tiers")
        for _role, value in self.digests:
            if re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
                raise ValueError("context envelope result digest is invalid")

    def to_prompt(self) -> dict[str, object]:
        return {
            "manifest_digest": self.manifest_digest,
            "token_budget": self.token_budget,
            "estimated_tokens": self.estimated_tokens,
            "full_bodies": [
                {"role": role, "body": body} for role, body in self.full_bodies
            ],
            "digests": [
                {"role": role, "result_digest": value} for role, value in self.digests
            ],
            "omitted_roles": list(self.omitted_roles),
            "cold_references": list(self.cold_references),
            "generator_evaluator_separated": self.generator_evaluator_separated,
        }

    def to_receipt(self) -> dict[str, object]:
        return {
            "manifest_digest": self.manifest_digest,
            "token_budget": self.token_budget,
            "estimated_tokens": self.estimated_tokens,
            "full_body_digests": [
                {"role": role, "sha256": _digest(body.encode("utf-8"))}
                for role, body in self.full_bodies
            ],
            "result_digests": [
                {"role": role, "result_digest": value} for role, value in self.digests
            ],
            "omitted_roles": list(self.omitted_roles),
            "cold_reference_count": len(self.cold_references),
            "generator_evaluator_separated": self.generator_evaluator_separated,
        }


class BuilderActionProtocolError(ModelTurnError):
    """A structurally valid Builder turn has invalid executable actions."""


def _digest(content: bytes) -> str:
    return f"sha256:{sha256(content).hexdigest()}"


def _render_context(
    prior_roles: list[dict[str, object]], omitted_roles: list[str]
) -> str:
    return json.dumps(
        {"prior_roles": prior_roles, "omitted_roles": omitted_roles},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


class ModelBackend:
    def __init__(
        self,
        provider: ModelProvider,
        *,
        ledger: EvidenceLedger | None = None,
        budget: AutonomyBudget | None = None,
        context_limit_chars: int = 8000,
        role_providers: Mapping[Role, ModelProvider] | None = None,
        prompt_registry: PromptRegistry | None = None,
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
        self.prompt_registry = prompt_registry

    async def execute(
        self,
        contract: RoleContract,
        work_item: WorkItem,
        objective: Objective,
        context: tuple[AgentResult, ...],
        *,
        repository_context: RepositoryContext | None = None,
        result_validator: Callable[[AgentResult], None] | None = None,
        context_envelope: ContextEnvelope | None = None,
    ) -> AgentResult:
        system, user, truncated, prompt_artifact_digest = self._prompt(
            contract, work_item, objective, context, repository_context, context_envelope
        )
        corrective: str | None = None
        last_error = "model did not return a valid turn"
        provider = self.role_providers.get(contract.role, self.provider)
        context_manifest = self._context_manifest(
            context,
            role=contract.role,
            provider=provider,
            context_envelope=context_envelope,
        )
        allowance = self.budget.issue_allowance()
        used_calls = 0
        used_compute = 0.0
        retry_index = 0
        ordinary_failures = 0
        builder_correction_used = False
        try:
            while True:
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
                    result = self._to_result(turn, contract, work_item)
                    if result_validator is not None:
                        try:
                            result_validator(result)
                        except ValueError as error:
                            raise BuilderActionProtocolError(str(error)) from None
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
                        prompt_artifact_digest,
                    )
                    return result
                except BuilderActionProtocolError as error:
                    last_error = str(error)
                    self._record_call(
                        objective, contract, work_item, body, response, retry_index,
                        time.monotonic() - started, "invalid_output", truncated,
                        provider, context_manifest,
                        prompt_artifact_digest,
                        error=last_error,
                    )
                    if builder_correction_used:
                        raise ModelTurnError(
                            "Builder action protocol remained invalid after one correction: "
                            + last_error
                        ) from None
                    builder_correction_used = True
                    invalid_output = response.content[:4_000] if response else ""
                    corrective = (
                        "Your previous Builder response had invalid proposed actions. "
                        "Return a corrected complete JSON turn. Invalid output:\n"
                        f"{invalid_output}\nValidation error: {last_error}"
                    )
                except ModelTurnError as error:
                    last_error = str(error)
                    self._record_call(
                        objective, contract, work_item, body, response, retry_index,
                        time.monotonic() - started, "invalid_output", truncated,
                        provider, context_manifest,
                        prompt_artifact_digest,
                        error=last_error,
                    )
                    corrective = (
                        "Your previous response was invalid. Return only JSON matching the "
                        f"required contract. Validation error: {last_error}"
                    )
                    ordinary_failures += 1
                    if builder_correction_used or ordinary_failures > provider.config.max_retries:
                        raise ModelTurnError(
                            f"model output remained invalid after {retry_index + 1} attempts: "
                            + last_error
                        ) from None
                except ModelProviderError as error:
                    if isinstance(error, ModelResponseError):
                        response = ModelResponse("", error.raw_body, None, None)
                    last_error = redact(str(error))
                    self._record_call(
                        objective, contract, work_item, body, response, retry_index,
                        time.monotonic() - started, "provider_failure", truncated,
                        provider, context_manifest,
                        prompt_artifact_digest,
                        error=last_error,
                    )
                    if builder_correction_used or retry_index >= provider.config.max_retries:
                        raise
                retry_index += 1
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
        repository_context: RepositoryContext | None,
        context_envelope: ContextEnvelope | None = None,
    ) -> tuple[str, str, bool, str]:
        system = generation_zero_prompt(contract)
        artifact_digest = prompt_digest(system)
        if self.prompt_registry is not None:
            try:
                system, artifact_digest = self.prompt_registry.champion_prompt(
                    contract.role
                )
            except KeyError:
                artifact_digest = self.prompt_registry.register(
                    contract.role,
                    system,
                    parent_digest=None,
                    created_by="model-backend:generation-0",
                    experiment_id="generation-0",
                )
                self.prompt_registry.promote(
                    contract.role,
                    artifact_digest,
                    promoted_by="model-backend:generation-0",
                    experiment_id="generation-0",
                    expected_current=None,
                )
        if context_envelope is None:
            prior_roles = [
                {
                    "role": item.role.value,
                    "summary": item.summary,
                    "evidence": [asdict(evidence) for evidence in item.evidence],
                }
                for item in context
            ]
            omitted_roles: list[str] = []
            rendered = _render_context(prior_roles, omitted_roles)
            while prior_roles and len(rendered) > self.context_limit_chars:
                omitted_roles.append(str(prior_roles.pop(0)["role"]))
                rendered = _render_context(prior_roles, omitted_roles)
            truncated = bool(omitted_roles)
        else:
            if context_envelope.estimated_tokens > context_envelope.token_budget:
                raise ValueError("context envelope exceeds its declared token budget")
            rendered = json.dumps(
                context_envelope.to_prompt(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            truncated = bool(context_envelope.omitted_roles)
        user = json.dumps(
            {
                "objective": objective.goal,
                "acceptance_criteria": list(objective.acceptance_criteria),
                "constraints": list(objective.constraints),
                "base_workspace": objective.repository,
                "work_item": work_item.instruction,
                "prior_context_json": rendered,
                "context_truncated": truncated,
                "repository_context": (
                    None if repository_context is None else repository_context.to_prompt()
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return system, user, truncated, artifact_digest

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
        prompt_artifact_digest: str,
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
                "credential_reference": getattr(
                    provider, "credential_reference", "test-double"
                ),
                "api_key_env": provider.config.api_key_env or None,
            },
            "request_digest": _digest(request_body),
            "prompt_artifact_digest": prompt_artifact_digest,
            "response_digest": _digest(response.raw_body) if response else None,
            "prompt_tokens": response.prompt_tokens if response else None,
            "completion_tokens": response.completion_tokens if response else None,
            "token_accounting": measure_call(
                request_bytes=len(request_body),
                prompt_tokens=response.prompt_tokens if response else None,
                completion_tokens=response.completion_tokens if response else None,
                max_output_tokens=provider.config.max_output_tokens,
            ).to_document(),
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
        context_envelope: ContextEnvelope | None = None,
    ) -> dict[str, object]:
        manifest: dict[str, object] = {
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
        if context_envelope is not None:
            manifest["context_envelope"] = context_envelope.to_receipt()
            manifest["manifest_digest"] = context_envelope.manifest_digest
        return manifest
