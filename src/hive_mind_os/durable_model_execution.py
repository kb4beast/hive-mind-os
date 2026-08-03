"""Opt-in, one-shot execution of a model-backed role with durable recovery.

This adapter deliberately does *not* replace :class:`ModelBackend`'s legacy retrying
path.  A caller must supply a sealed role context, a filesystem-backed
``ModelTurnStore``, and one typed acceptance specification.  The adapter persists a
plan plus a permanent local budget reservation before exactly one ``complete_once``
call.  Any uncertain outcome is quarantined instead of retried.

The local plan, digests, SQLite transaction, and provider response digest are evidence
of local process state only.  They are not provider authentication, a provider
idempotency key, an outcome-reconciliation API, an externally valid lease, or credential
isolation.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from types import MappingProxyType
from typing import Mapping, Sequence
from urllib.parse import urlsplit

from .acceptance import AcceptanceSpecification
from .model_backend import ModelBackend, ModelTurnError
from .model_provider import (
    ModelProviderError,
    ModelRequest,
    ModelResponse,
    ModelResponseError,
    redact,
)
from .model_turn_state import (
    ModelProviderIdentity,
    ModelRoleResult,
    ModelTurnAmbiguity,
    ModelTurnBudget,
    ModelTurnBudgetReservation,
    ModelTurnOutcome,
    ModelTurnPhase,
    ModelTurnPlan,
    ModelTurnResult,
    ModelTurnStateError,
    ModelTurnStore,
)
from .models import AgentResult, Objective, Role, WorkItem
from .roles import RoleContract
from .runtime import HiveKernel


class DurableModelExecutionError(RuntimeError):
    """The durable one-shot role cannot safely yield a result."""


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _digest_document(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise DurableModelExecutionError("durable model binding is not canonical JSON") from error
    return _digest_bytes(encoded)


def _contains_any_text(value: object, needles: Sequence[str]) -> bool:
    if isinstance(value, str):
        return any(needle in value for needle in needles)
    if isinstance(value, Mapping):
        return any(
            _contains_any_text(key, needles) or _contains_any_text(item, needles)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_any_text(item, needles) for item in value)
    return False


@dataclass(frozen=True, slots=True)
class DurableModelExecutionContext:
    """Explicit, non-secret bindings required for one durable role lane.

    ``prompt_artifact_digests`` pins content-addressed prompt artifacts by role.  The
    caller must give the same mapping after a restart; a mutable champion pointer is
    never consulted by this adapter.  The initial profile accepts exactly one typed
    acceptance specification because the reviewed v1 model-turn contract has one
    specification binding.  Multi-spec repository missions remain a separate contract
    design obligation.
    """

    mission_id: str
    state_ref: str
    acceptance_specification: AcceptanceSpecification
    policy_decision_ref: str
    lease_id: str
    redaction_policy_digest: str
    budget: ModelTurnBudget
    prompt_artifact_digests: Mapping[Role | str, str]
    redaction_secrets: Sequence[str] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.acceptance_specification, AcceptanceSpecification):
            raise ValueError(
                "durable model execution requires an exact typed acceptance specification"
            )
        try:
            specification = AcceptanceSpecification.from_dict(
                self.acceptance_specification.to_dict()
            )
        except (AttributeError, ValueError) as error:
            raise ValueError(
                "durable model execution acceptance specification is not executable"
            ) from error
        object.__setattr__(self, "acceptance_specification", specification)
        if not isinstance(self.budget, ModelTurnBudget):
            raise ValueError("durable model execution requires an exact typed model-turn budget")
        budget = ModelTurnBudget(
            self.budget.mission_id,
            self.budget.max_episodes,
            self.budget.max_tool_calls,
            self.budget.max_compute_units,
            self.budget.max_tool_calls_per_episode,
            self.budget.max_compute_units_per_episode,
        )
        object.__setattr__(self, "budget", budget)
        if self.budget.mission_id != self.mission_id:
            raise ValueError("durable model budget must bind the execution mission")
        normalized: dict[str, str] = {}
        for role, digest in self.prompt_artifact_digests.items():
            try:
                role_name = Role(role).value
            except ValueError as error:
                raise ValueError("durable model prompt mapping has an unknown role") from error
            if not isinstance(digest, str) or not digest.startswith("sha256:"):
                raise ValueError("durable model prompt mapping requires SHA-256 digests")
            normalized[role_name] = digest
        if not normalized:
            raise ValueError("durable model prompt mapping is required")
        object.__setattr__(self, "prompt_artifact_digests", MappingProxyType(normalized))
        object.__setattr__(
            self,
            "redaction_secrets",
            tuple(value for value in self.redaction_secrets if isinstance(value, str) and value),
        )

    def prompt_digest_for(self, role: Role) -> str:
        try:
            return self.prompt_artifact_digests[role.value]
        except KeyError as error:
            raise DurableModelExecutionError(
                f"durable model execution has no sealed prompt for {role.value}"
            ) from error


class DurableModelRoleExecutor:
    """Run or safely rehydrate one logical role through a ``ModelTurnStore``.

    The adapter is intentionally scoped to a caller that already owns stable mission,
    work-item, objective, policy, and lease bindings.  It does not enable legacy CLI or
    ``RepositoryMission`` resumption, which currently lack the required role journal and
    checkpoint/receipt rehydration protocol.
    """

    def __init__(
        self,
        backend: ModelBackend,
        store: ModelTurnStore,
        context: DurableModelExecutionContext,
    ) -> None:
        self.backend = backend
        self.store = store
        self.context = context

    async def execute(
        self,
        contract: RoleContract,
        work_item: WorkItem,
        objective: Objective,
        prior_results: tuple[AgentResult, ...] = (),
    ) -> AgentResult:
        if objective.id != self.context.mission_id:
            raise DurableModelExecutionError("objective ID does not bind the durable model mission")
        self._reject_configured_secrets_in_context(prior_results)
        provider = self.backend.role_providers.get(contract.role, self.backend.provider)
        self._reject_provider_endpoint_in_context(provider, prior_results)
        self._reject_configured_secrets_in_ledger_projection(
            provider,
            contract,
            work_item,
            objective,
        )
        prompt_digest = self.context.prompt_digest_for(contract.role)
        system, user, truncated, observed_prompt_digest = self.backend._prompt(  # noqa: SLF001 - deliberate sealed adapter seam
            contract,
            work_item,
            objective,
            prior_results,
            pinned_prompt_digest=prompt_digest,
        )
        if observed_prompt_digest != prompt_digest:
            raise DurableModelExecutionError("sealed durable prompt did not reproduce exactly")
        request = ModelRequest(system, user)
        request_body = provider.build_request_body(request)
        plan = self._plan(
            contract,
            work_item,
            provider,
            prompt_digest,
            request_body,
        )
        reservation = ModelTurnBudgetReservation.create(
            plan,
            compute_units=(
                max(1, len(request_body) // 4) + provider.config.max_output_tokens
            )
            / 1000.0,
        )
        try:
            record = self.store.register_durable_plan(
                plan,
                budget=self.context.budget,
                reservation=reservation,
            )
            record = self.store.durable_record(
                plan,
                budget=self.context.budget,
                reservation=reservation,
            )
        except ModelTurnStateError as error:
            raise DurableModelExecutionError(f"durable model admission failed: {error}") from error

        if record.phase is ModelTurnPhase.DISPATCH_STARTED:
            self.store.recover(plan.logical_turn_id)
            raise DurableModelExecutionError(
                "durable model turn was interrupted after dispatch and is quarantined"
            )
        if record.phase is ModelTurnPhase.AMBIGUOUS:
            raise DurableModelExecutionError("durable model turn is quarantined as ambiguous")
        if record.phase is ModelTurnPhase.COMPLETED:
            if record.role_result is None:
                raise DurableModelExecutionError(
                    "durable model turn completed without an admissible resumable role result"
                )
            result = record.role_result.to_agent_result()
            HiveKernel._validate_result(contract.role, result)
            return result
        if record.phase is not ModelTurnPhase.PLANNED:
            raise DurableModelExecutionError("durable model turn has an unknown phase")

        try:
            self.store.start_dispatch(plan.logical_turn_id)
        except ModelTurnStateError as error:
            raise DurableModelExecutionError(
                "durable model dispatch was rejected before provider invocation"
            ) from error

        context_manifest = self.backend._context_manifest(  # noqa: SLF001 - same sealed adapter seam
            prior_results,
            role=contract.role,
            provider=provider,
        )
        try:
            response = await asyncio.to_thread(provider.complete_once, request)
        except ModelResponseError as error:
            response = ModelResponse("", error.raw_body, None, None)
            self.backend._record_call(  # noqa: SLF001 - preserves legacy redacted receipt shape
                objective, contract, work_item, request_body, response, 0, 0.0,
                "provider_failure", truncated, provider, context_manifest, prompt_digest,
                error=redact(str(error), self._redaction_values(provider)),
            )
            self._adopt_observed_failure(plan, response, ModelTurnOutcome.PROVIDER_RESPONSE_FAILURE)
            raise DurableModelExecutionError("provider returned an observed unusable response") from None
        except ModelProviderError as error:
            self.backend._record_call(  # noqa: SLF001 - no provider body is available
                objective, contract, work_item, request_body, None, 0, 0.0,
                "provider_failure", truncated, provider, context_manifest, prompt_digest,
                error=redact(str(error), self._redaction_values(provider)),
            )
            self._quarantine(plan)
            raise DurableModelExecutionError(
                "provider outcome is uncertain after durable dispatch and is quarantined"
            ) from None
        except BaseException:
            self._quarantine(plan)
            raise

        try:
            if self._observed_compute(response) > reservation.compute_units:
                self.backend._record_call(  # noqa: SLF001 - preserves bounded evidence
                    objective, contract, work_item, request_body, response, 0, 0.0,
                    "provider_failure", truncated, provider, context_manifest, prompt_digest,
                    error="provider-reported usage exceeds the sealed durable reservation",
                )
                self._adopt_observed_failure(
                    plan, response, ModelTurnOutcome.PROVIDER_RESPONSE_FAILURE
                )
                raise DurableModelExecutionError(
                    "provider-reported usage exceeds the sealed durable reservation"
                )
            turn = self.backend._parse_turn(response.content, contract)  # noqa: SLF001 - shared contract parser
            result = self.backend._to_result(turn, contract, work_item)  # noqa: SLF001 - shared result mapping
            HiveKernel._validate_result(contract.role, result)
            role_result = ModelRoleResult.from_agent_result(
                plan.logical_turn_id,
                result,
                redaction_policy_digest=self.context.redaction_policy_digest,
                redaction_secrets=self._redaction_values(provider),
            )
            turn_result = ModelTurnResult.from_dict(
                {
                    "schema_version": 1,
                    "logical_turn_id": plan.logical_turn_id,
                    "outcome": ModelTurnOutcome.SUCCEEDED.value,
                    "response_digest": _digest_bytes(response.raw_body),
                    "structured_result_digest": role_result.digest,
                    "prompt_tokens": response.prompt_tokens,
                    "completion_tokens": response.completion_tokens,
                    "transport_retry_index": response.transport_retry_index,
                }
            )
            self.store.adopt_role_result(turn_result, role_result)
            self.backend._record_call(  # noqa: SLF001 - preserves bounded evidence
                objective, contract, work_item, request_body, response, 0, 0.0,
                "succeeded", truncated, provider, context_manifest, prompt_digest,
            )
            return role_result.to_agent_result()
        except ModelTurnError as error:
            self.backend._record_call(  # noqa: SLF001 - preserves bounded evidence
                objective, contract, work_item, request_body, response, 0, 0.0,
                "invalid_output", truncated, provider, context_manifest, prompt_digest,
                error=redact(str(error), self._redaction_values(provider)),
            )
            self._adopt_observed_failure(plan, response, ModelTurnOutcome.INVALID_OUTPUT)
            raise DurableModelExecutionError("provider returned an observed invalid role result") from None
        except ModelTurnStateError as error:
            self._quarantine(plan)
            raise DurableModelExecutionError(
                "durable model state could not adopt the observed provider outcome"
            ) from error
        except DurableModelExecutionError:
            self._quarantine(plan)
            raise
        except BaseException:
            self._quarantine(plan)
            raise

    def _plan(
        self,
        contract: RoleContract,
        work_item: WorkItem,
        provider: object,
        prompt_digest: str,
        request_body: bytes,
    ) -> ModelTurnPlan:
        config = getattr(provider, "config", None)
        kind = getattr(provider, "kind", None)
        if config is None or kind is None:
            raise DurableModelExecutionError("durable model provider lacks a sealed configuration")
        host = urlsplit(config.base_url).hostname
        if host is None:
            raise DurableModelExecutionError("durable model provider has no hostname")
        identity = ModelProviderIdentity.from_dict(
            {"kind": str(kind), "base_url_host": host.casefold(), "model_id": config.model}
        )
        provider_configuration = {
            "kind": str(kind),
            "base_url": config.base_url,
            "model": config.model,
            "api_key_env": config.api_key_env,
            "timeout_s": config.timeout_s,
            "max_output_tokens": config.max_output_tokens,
            "temperature": config.temperature,
            "max_retries": config.max_retries,
        }
        selection = {
            "role": contract.role.value,
            "provider": identity.to_dict(),
            "provider_configuration_digest": _digest_document(provider_configuration),
            "prompt_artifact_digest": prompt_digest,
        }
        try:
            return ModelTurnPlan.create(
                mission_id=self.context.mission_id,
                state_ref=self.context.state_ref,
                role=contract.role.value,
                work_item_id=work_item.id,
                provider=identity,
                prompt_digest=prompt_digest,
                request_digest=_digest_bytes(request_body),
                acceptance_specification_id=self.context.acceptance_specification.identifier,
                acceptance_specification_digest=self.context.acceptance_specification.digest,
                role_contract_digest=_digest_document(asdict(contract)),
                configuration_digest=_digest_document(provider_configuration),
                selection_digest=_digest_document(selection),
                policy_decision_ref=self.context.policy_decision_ref,
                lease_id=self.context.lease_id,
                redaction_policy_digest=self.context.redaction_policy_digest,
            )
        except ModelTurnStateError as error:
            raise DurableModelExecutionError(f"durable model plan is invalid: {error}") from error

    @staticmethod
    def _observed_compute(response: ModelResponse) -> float:
        if response.prompt_tokens is None or response.completion_tokens is None:
            return 0.0
        return (response.prompt_tokens + response.completion_tokens) / 1000.0

    def _adopt_observed_failure(
        self,
        plan: ModelTurnPlan,
        response: ModelResponse,
        outcome: ModelTurnOutcome,
    ) -> None:
        result = ModelTurnResult.from_dict(
            {
                "schema_version": 1,
                "logical_turn_id": plan.logical_turn_id,
                "outcome": outcome.value,
                "response_digest": _digest_bytes(response.raw_body),
                "structured_result_digest": None,
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "transport_retry_index": response.transport_retry_index,
            }
        )
        try:
            self.store.adopt_result(result)
        except ModelTurnStateError:
            self._quarantine(plan)
            raise

    def _quarantine(self, plan: ModelTurnPlan) -> None:
        try:
            self.store.mark_ambiguous(
                plan.logical_turn_id,
                ModelTurnAmbiguity.PROVIDER_OUTCOME_UNKNOWN,
            )
        except ModelTurnStateError:
            # A terminal observed result may have committed just before an exception; it
            # remains terminal.  A caller will revalidate that durable record on restart.
            pass

    def _reject_configured_secrets_in_context(
        self,
        prior_results: tuple[AgentResult, ...],
    ) -> None:
        """Do not put a configured secret into the legacy ledger context manifest.

        Durable results rehydrated by this lane have already passed selected-result
        redaction.  A caller can still provide arbitrary non-durable prior context, so
        this boundary rejects a known configured secret rather than trusting the legacy
        backend's summary-only ledger projection to redact it.  Unknown secrets remain
        an explicit redaction-policy residual.
        """

        if not self.context.redaction_secrets:
            return

        if any(
            _contains_any_text(
                {
                    "summary": result.summary,
                    "evidence": [
                        {
                            "kind": item.kind,
                            "summary": item.summary,
                            "source": item.source,
                            "payload": item.payload,
                        }
                        for item in result.evidence
                    ],
                    "proposed_actions": result.proposed_actions,
                    "lessons": result.lessons,
                },
                self.context.redaction_secrets,
            )
            for result in prior_results
        ):
            raise DurableModelExecutionError(
                "durable model prior context contains an unredacted configured secret"
            )

    def _reject_provider_endpoint_in_context(
        self,
        provider: object,
        prior_results: tuple[AgentResult, ...],
    ) -> None:
        config = getattr(provider, "config", None)
        endpoint = getattr(config, "base_url", None)
        if not isinstance(endpoint, str) or not endpoint:
            raise DurableModelExecutionError("durable model provider lacks a sealed endpoint")
        if any(
            _contains_any_text(
                {
                    "summary": result.summary,
                    "evidence": [
                        {
                            "kind": item.kind,
                            "summary": item.summary,
                            "source": item.source,
                            "payload": item.payload,
                        }
                        for item in result.evidence
                    ],
                    "proposed_actions": result.proposed_actions,
                    "lessons": result.lessons,
                },
                (endpoint,),
            )
            for result in prior_results
        ):
            raise DurableModelExecutionError(
                "durable model prior context contains the configured provider endpoint"
            )

    def _reject_configured_secrets_in_ledger_projection(
        self,
        provider: object,
        contract: RoleContract,
        work_item: WorkItem,
        objective: Objective,
    ) -> None:
        """Fail closed if known secret text would enter a durable ``model.call`` receipt."""

        if not self.context.redaction_secrets:
            return
        config = getattr(provider, "config", None)
        base_url = getattr(config, "base_url", "")
        host = urlsplit(base_url).hostname if isinstance(base_url, str) else None
        values = (
            self.context.mission_id,
            self.context.state_ref,
            self.context.acceptance_specification.identifier,
            self.context.policy_decision_ref,
            self.context.lease_id,
            self.context.redaction_policy_digest,
            objective.id,
            work_item.id,
            contract.role.value,
            str(getattr(provider, "kind", "")),
            host or "",
            str(getattr(config, "model", "")),
            str(getattr(config, "api_key_env", "")),
        )
        if any(
            secret in value
            for secret in self.context.redaction_secrets
            for value in values
        ):
            raise DurableModelExecutionError(
                "durable model ledger projection contains a configured secret"
            )

    def _redaction_values(self, provider: object) -> tuple[str, ...]:
        config = getattr(provider, "config", None)
        endpoint = getattr(config, "base_url", "")
        return (
            *self.context.redaction_secrets,
            endpoint if isinstance(endpoint, str) and endpoint else "",
        )
