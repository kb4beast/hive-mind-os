from __future__ import annotations

import json
import time
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any, Callable, Mapping
from uuid import uuid4

from hive_mind_os.model_provider import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelResponseError,
    ModelTransportError,
)

from .authority import AuthorityDecision
from .canonical import stable_id
from .contracts import validate_foundation
from .store import FoundationStore, IdempotencyConflict

NORMALIZATION_VERSION = "usage-axes-v1"
TERMINAL_OUTCOMES = frozenset(
    {"abandoned", "cancelled", "interrupted", "invalid-output", "provider-failure", "succeeded"}
)


def _nonnegative_int(value: Any) -> int | None:
    return value if type(value) is int and 0 <= value <= 10**15 else None


class ProviderUsageAdapter:
    """Versioned parsing of repository-owned provider-shaped fixtures.

    This parser establishes software behavior only.  It does not claim current live
    provider billing semantics.
    """

    @staticmethod
    def parse(provider_kind: str, raw_body: bytes) -> dict[str, Any]:
        if len(raw_body) > 1_000_000:
            return ProviderUsageAdapter._unknown_observation(
                "response-size-limit", raw_body
            )
        try:
            body = json.loads(raw_body)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return ProviderUsageAdapter._unknown_observation("invalid-json", raw_body)
        if not isinstance(body, dict):
            return ProviderUsageAdapter._unknown_observation("non-object", raw_body)
        usage = body.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        native, unmapped_count = ProviderUsageAdapter._numeric_usage(
            provider_kind, usage
        )
        if provider_kind == "openai_compatible":
            input_tokens = _nonnegative_int(usage.get("prompt_tokens"))
            output_tokens = _nonnegative_int(usage.get("completion_tokens"))
            prompt_details = usage.get("prompt_tokens_details")
            completion_details = usage.get("completion_tokens_details")
            cached = (
                _nonnegative_int(prompt_details.get("cached_tokens"))
                if isinstance(prompt_details, dict)
                else None
            )
            reasoning = (
                _nonnegative_int(completion_details.get("reasoning_tokens"))
                if isinstance(completion_details, dict)
                else None
            )
            axes = ProviderUsageAdapter._axes(
                input_tokens,
                output_tokens,
                reported_total=_nonnegative_int(usage.get("total_tokens")),
                cache_read=cached,
                cache_write=None,
                reasoning=reasoning,
            )
        elif provider_kind == "anthropic":
            input_tokens = _nonnegative_int(usage.get("input_tokens"))
            output_tokens = _nonnegative_int(usage.get("output_tokens"))
            axes = ProviderUsageAdapter._axes(
                input_tokens,
                output_tokens,
                reported_total=None,
                cache_read=_nonnegative_int(usage.get("cache_read_input_tokens")),
                cache_write=_nonnegative_int(usage.get("cache_creation_input_tokens")),
                reasoning=None,
            )
        else:
            input_tokens = None
            output_tokens = None
            axes = ProviderUsageAdapter._unknown_axes()
        axis_statuses = {
            str(axis.get("status"))
            for axis in axes.values()
            if isinstance(axis, Mapping)
        }
        accounting_status = (
            "conflicting"
            if "conflicting" in axis_statuses
            else "reported"
            if input_tokens is not None and output_tokens is not None
            else "unknown"
        )
        provider_request_id = ProviderUsageAdapter._bounded_identifier(body.get("id"))
        served_model_id = ProviderUsageAdapter._bounded_identifier(body.get("model"))
        identity_failure = (
            "provider-identity-size-limit"
            if (
                isinstance(body.get("id"), str) and provider_request_id is None
            )
            or (
                isinstance(body.get("model"), str) and served_model_id is None
            )
            else None
        )
        return {
            "adapter_version": NORMALIZATION_VERSION,
            "accounting_status": accounting_status,
            "native": native,
            "native_provenance": ProviderUsageAdapter._provenance(
                raw_body, "response-body"
            ),
            "normalized_axes": axes,
            "provider_request_id": provider_request_id,
            "served_model_id": served_model_id,
            "unmapped_path_count": unmapped_count,
            "observation_failure": identity_failure,
        }

    @staticmethod
    def _bounded_identifier(value: Any) -> str | None:
        return value if isinstance(value, str) and 0 < len(value) <= 256 else None

    @staticmethod
    def _numeric_usage(
        provider_kind: str,
        value: Mapping[str, Any],
    ) -> tuple[dict[str, int | None], int]:
        native: dict[str, int | None] = {}
        allowed = {
            "openai_compatible": {
                "completion_tokens",
                "completion_tokens_details.reasoning_tokens",
                "prompt_tokens",
                "prompt_tokens_details.cached_tokens",
                "total_tokens",
            },
            "anthropic": {
                "cache_creation_input_tokens",
                "cache_read_input_tokens",
                "input_tokens",
                "output_tokens",
            },
        }.get(provider_kind, set())

        def lookup(path: str) -> tuple[bool, Any]:
            item: Any = value
            for part in path.split("."):
                if not isinstance(item, Mapping) or part not in item:
                    return False, None
                item = item[part]
            return True, item

        leaf_count = 0

        def count_leaves(item: Any, depth: int = 0) -> None:
            nonlocal leaf_count
            if leaf_count > 128:
                return
            if isinstance(item, Mapping) and depth <= 3:
                for child in item.values():
                    count_leaves(child, depth + 1)
            else:
                leaf_count += 1

        count_leaves(value)
        if leaf_count > 128:
            return {}, leaf_count
        mapped_count = 0
        for path in sorted(allowed):
            present, item = lookup(path)
            if not present:
                continue
            if item is None:
                native[path] = None
                mapped_count += 1
            elif type(item) is int and 0 <= item <= 10**15:
                native[path] = item
                mapped_count += 1
        return native, max(0, leaf_count - mapped_count)

    @staticmethod
    def _unknown_observation(
        reason: str,
        raw_body: bytes | None = None,
    ) -> dict[str, Any]:
        return {
            "adapter_version": NORMALIZATION_VERSION,
            "accounting_status": "unknown",
            "native": {},
            "native_provenance": ProviderUsageAdapter._provenance(
                raw_body, "response-body" if raw_body is not None else "no-response"
            ),
            "normalized_axes": ProviderUsageAdapter._unknown_axes(),
            "provider_request_id": None,
            "served_model_id": None,
            "unmapped_path_count": 0,
            "observation_failure": reason,
        }

    @staticmethod
    def _provenance(raw_body: bytes | None, source: str) -> dict[str, Any]:
        return {
            "source": source,
            "unit": "tokens",
            "semantics_status": (
                "fixture-adapter-unverified"
                if source == "response-body"
                else "unknown"
            ),
            "raw_body_digest": (
                f"sha256:{sha256(raw_body).hexdigest()}"
                if raw_body is not None
                else None
            ),
        }

    @staticmethod
    def _axes(
        input_tokens: int | None,
        output_tokens: int | None,
        *,
        reported_total: int | None,
        cache_read: int | None,
        cache_write: int | None,
        reasoning: int | None,
    ) -> dict[str, Any]:
        cache_status = "unknown"
        uncached: int | None = None
        if input_tokens is not None and (cache_read is not None or cache_write is not None):
            known_subsets = (cache_read or 0) + (cache_write or 0)
            if known_subsets <= input_tokens:
                uncached = input_tokens - known_subsets
                cache_status = "complete"
            else:
                cache_status = "conflicting"
        output_status = (
            "partial"
            if output_tokens is not None and reasoning is not None and reasoning <= output_tokens
            else "unknown" if reasoning is None else "conflicting"
        )
        direction_status = (
            "complete"
            if input_tokens is not None and output_tokens is not None
            else "unknown"
        )
        if (
            input_tokens is not None
            and output_tokens is not None
            and reported_total is not None
            and input_tokens + output_tokens != reported_total
        ):
            direction_status = "conflicting"
        return {
            "direction": {
                "input": input_tokens,
                "output": output_tokens,
                "reported_total": reported_total,
                "status": direction_status,
            },
            "cache_input": {
                "total": input_tokens,
                "read": cache_read,
                "write": cache_write,
                "uncached": uncached,
                "status": cache_status,
            },
            "modality": {"status": "unknown"},
            "output_kind": {
                "total": output_tokens,
                "reasoning_subset": reasoning,
                "status": output_status,
            },
            "billable": {"status": "unknown"},
        }

    @staticmethod
    def _unknown_axes() -> dict[str, Any]:
        return ProviderUsageAdapter._axes(
            None,
            None,
            reported_total=None,
            cache_read=None,
            cache_write=None,
            reasoning=None,
        )


@dataclass(frozen=True, slots=True)
class UsageAttribution:
    """Bounded caller-supplied lineage for an opt-in physical model attempt."""

    mission_id: str | None = None
    run_id: str | None = None
    step_id: str | None = None
    role: str | None = None
    work_item_id: str | None = None
    idea_id: str | None = None
    case_id: str | None = None
    experiment_id: str | None = None
    span_id: str | None = None
    prompt_layer_digest: str | None = None
    context_digest: str | None = None
    memory_selection_digest: str | None = None
    selected_count: int | None = None
    omitted_count: int | None = None
    model_revision: str | None = None
    host_id: str | None = None
    access_audit_ref: str | None = None

    def __post_init__(self) -> None:
        _validate_usage_attribution(self)


def _validate_usage_attribution(attribution: UsageAttribution) -> None:
    identifiers = (
        attribution.mission_id,
        attribution.run_id,
        attribution.step_id,
        attribution.role,
        attribution.work_item_id,
        attribution.idea_id,
        attribution.case_id,
        attribution.experiment_id,
        attribution.span_id,
        attribution.model_revision,
        attribution.host_id,
        attribution.access_audit_ref,
    )
    if any(
        value is not None
        and (
            not isinstance(value, str)
            or not value
            or len(value) > 256
        )
        for value in identifiers
    ):
        raise ValueError("usage attribution identifiers must be bounded")
    for value in (
        attribution.prompt_layer_digest,
        attribution.context_digest,
        attribution.memory_selection_digest,
    ):
        if value is not None and (
            not isinstance(value, str)
            or len(value) != 71
            or not value.startswith("sha256:")
            or any(character not in "0123456789abcdef" for character in value[7:])
        ):
            raise ValueError("usage attribution digests must be sha256 digests")
    if any(
        value is not None
        and (type(value) is not int or not 0 <= value <= 10**9)
        for value in (attribution.selected_count, attribution.omitted_count)
    ):
        raise ValueError("usage attribution counts must be bounded integers")


class UsageRecorder:
    """Durable opt-in attempt recorder; Generation Zero remains unchanged."""

    def __init__(
        self,
        store: FoundationStore,
        *,
        tenant_id: str,
        repository_id: str,
        authority: AuthorityDecision,
        recorder_id: str = "foundation-usage-recorder-v1",
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.store = store
        self.tenant_id = tenant_id
        self.repository_id = repository_id
        if recorder_id != "foundation-usage-recorder-v1":
            raise ValueError("usage recorder identity is fixed and cannot self-declare")
        store._require_authority(
            authority,
            "foundation.telemetry.write",
            tenant_id=tenant_id,
            repository_id=repository_id,
            actor_id=recorder_id,
        )
        self.recorder_id = recorder_id
        self.authority = authority
        self._id_factory = id_factory or (lambda: str(uuid4()))

    def start_attempt(
        self,
        *,
        logical_request_id: str,
        retry_index: int,
        provider_kind: str,
        requested_model_id: str,
        purpose: str,
        actor_id: str,
        request_digest: str,
        budget_lease_id: str | None,
        trace_id: str,
        attribution: UsageAttribution | None = None,
    ) -> str:
        attempt_attribution = attribution or UsageAttribution()
        _validate_usage_attribution(attempt_attribution)
        attempt_id = f"attempt:{self._id_factory()}"
        payload = {
            "record_type": "usage-event",
            "schema_version": 1,
            "event_kind": "attempt-started",
            "attempt_id": attempt_id,
            "logical_request_id": logical_request_id,
            "retry_index": retry_index,
            "provider_kind": provider_kind,
            "requested_model_id": requested_model_id,
            "purpose": purpose,
            "actor_id": actor_id,
            "request_digest": request_digest,
            "budget_lease_id": budget_lease_id,
            "trace_id": trace_id,
            "accounting_status": "pending",
            "adapter_version": NORMALIZATION_VERSION,
            "native": {},
            "native_provenance": ProviderUsageAdapter._provenance(
                None, "no-response"
            ),
            "normalized_axes": ProviderUsageAdapter._unknown_axes(),
            "provider_request_id": None,
            "served_model_id": None,
            "unmapped_path_count": 0,
            "observation_failure": "pending",
        }
        payload.update(
            self._canonical_families(
                attempt_id=attempt_id,
                logical_request_id=logical_request_id,
                retry_index=retry_index,
                provider_kind=provider_kind,
                requested_model_id=requested_model_id,
                served_model_id=None,
                provider_request_id=None,
                purpose=purpose,
                actor_id=actor_id,
                request_digest=request_digest,
                budget_lease_id=budget_lease_id,
                trace_id=trace_id,
                duration_ms=None,
                outcome=None,
                error_class=None,
                attribution=attempt_attribution,
            )
        )
        validation = validate_foundation("usage-event-v1", payload)
        if not validation.valid:
            raise ValueError("invalid usage start: " + "; ".join(validation.issues))
        self.store.append_record(
            authority=self.authority,
            foundation_action="foundation.telemetry.write",
            tenant_id=self.tenant_id,
            repository_id=self.repository_id,
            record_type="usage-event",
            schema_name="usage-event-v1",
            stream_id=f"usage:{attempt_id}",
            payload=payload,
            actor_id=self.recorder_id,
            idempotency_key=f"usage-start:{attempt_id}",
            correlation_id=logical_request_id,
            sensitivity="private",
            status="started",
        )
        return attempt_id

    def finish_attempt(
        self,
        *,
        attempt_id: str,
        logical_request_id: str,
        provider_kind: str,
        outcome: str,
        duration_ms: int | float,
        response: ModelResponse | None,
        error_class: str | None = None,
    ) -> dict[str, Any]:
        if outcome not in TERMINAL_OUTCOMES:
            raise ValueError("unsupported terminal outcome")
        if error_class is not None and (
            len(error_class) > 80 or not error_class.replace("_", "").isalnum()
        ):
            raise ValueError("error_class must be a bounded symbolic value")
        starts = [
            record["payload"]
            for record in self.store.records(
                tenant_id=self.tenant_id,
                repository_id=self.repository_id,
                record_type="usage-event",
            )
            if record["payload"].get("event_kind") == "attempt-started"
            and record["payload"].get("attempt_id") == attempt_id
        ]
        if len(starts) != 1:
            raise ValueError("terminal usage requires exactly one durable start")
        started = starts[0]
        if (
            started.get("logical_request_id") != logical_request_id
            or started.get("provider_kind") != provider_kind
        ):
            raise IdempotencyConflict("terminal usage differs from its durable start")
        observation = (
            ProviderUsageAdapter.parse(provider_kind, response.raw_body)
            if response is not None
            else {
                "adapter_version": NORMALIZATION_VERSION,
                "accounting_status": "unknown",
                "native": {},
                "native_provenance": ProviderUsageAdapter._provenance(
                    None, "no-response"
                ),
                "normalized_axes": ProviderUsageAdapter._unknown_axes(),
                "provider_request_id": None,
                "served_model_id": None,
                "unmapped_path_count": 0,
                "observation_failure": "no-response",
            }
        )
        response_digest = (
            f"sha256:{sha256(response.raw_body).hexdigest()}"
            if response is not None
            else None
        )
        payload = {
            "record_type": "usage-event",
            "schema_version": 1,
            "event_kind": "attempt-terminal",
            "attempt_id": attempt_id,
            "logical_request_id": logical_request_id,
            "provider_kind": provider_kind,
            "outcome": outcome,
            "duration_ms": duration_ms,
            "response_digest": response_digest,
            "error_class": error_class,
            **observation,
        }
        payload.update(
            self._canonical_families(
                attempt_id=attempt_id,
                logical_request_id=logical_request_id,
                retry_index=int(started["retry_index"]),
                provider_kind=provider_kind,
                requested_model_id=str(started["requested_model_id"]),
                served_model_id=observation["served_model_id"],
                provider_request_id=observation["provider_request_id"],
                purpose=str(started["purpose"]),
                actor_id=str(started["actor_id"]),
                request_digest=str(started["request_digest"]),
                budget_lease_id=started["budget_lease_id"],
                trace_id=str(started["trace_id"]),
                duration_ms=duration_ms,
                outcome=outcome,
                error_class=error_class,
                attribution=self._attribution_from_started(started),
            )
        )
        validation = validate_foundation("usage-event-v1", payload)
        if not validation.valid:
            raise ValueError("invalid usage terminal: " + "; ".join(validation.issues))
        return self.store.append_record(
            authority=self.authority,
            foundation_action="foundation.telemetry.write",
            tenant_id=self.tenant_id,
            repository_id=self.repository_id,
            record_type="usage-event",
            schema_name="usage-event-v1",
            stream_id=f"usage:{attempt_id}",
            payload=payload,
            actor_id=self.recorder_id,
            idempotency_key=f"usage-terminal:{attempt_id}",
            correlation_id=logical_request_id,
            causation_id=attempt_id,
            sensitivity="private",
            status="terminal",
        )

    def recover_interrupted(self) -> tuple[str, ...]:
        records = self.store.records(
            tenant_id=self.tenant_id,
            repository_id=self.repository_id,
            record_type="usage-event",
        )
        started: dict[str, dict[str, Any]] = {}
        terminal: set[str] = set()
        for record in records:
            payload = record["payload"]
            attempt_id = payload.get("attempt_id")
            if not isinstance(attempt_id, str):
                continue
            if payload.get("event_kind") == "attempt-started":
                started[attempt_id] = payload
            elif payload.get("event_kind") == "attempt-terminal":
                terminal.add(attempt_id)
        recovered: list[str] = []
        for attempt_id in sorted(set(started) - terminal):
            payload = started[attempt_id]
            try:
                self.finish_attempt(
                    attempt_id=attempt_id,
                    logical_request_id=str(payload["logical_request_id"]),
                    provider_kind=str(payload["provider_kind"]),
                    outcome="interrupted",
                    duration_ms=0,
                    response=None,
                    error_class="InterruptedBeforeTerminalReceipt",
                )
            except IdempotencyConflict:
                continue
            recovered.append(attempt_id)
        return tuple(recovered)

    def _canonical_families(
        self,
        *,
        attempt_id: str,
        logical_request_id: str,
        retry_index: int,
        provider_kind: str,
        requested_model_id: str,
        served_model_id: Any,
        provider_request_id: Any,
        purpose: str,
        actor_id: str,
        request_digest: str,
        budget_lease_id: Any,
        trace_id: str,
        duration_ms: int | float | None,
        outcome: str | None,
        error_class: str | None,
        attribution: UsageAttribution,
    ) -> dict[str, Any]:
        return {
            "correlation": {
                "repository_id": self.repository_id,
                "tenant_id": self.tenant_id,
                "mission_id": attribution.mission_id,
                "run_id": attribution.run_id,
                "step_id": attribution.step_id,
                "role": attribution.role,
                "work_item_id": attribution.work_item_id,
                "idea_id": attribution.idea_id,
                "case_id": attribution.case_id,
                "experiment_id": attribution.experiment_id,
                "trace_id": trace_id,
                "span_id": attribution.span_id,
                "logical_request_id": logical_request_id,
                "attempt_id": attempt_id,
                "provider_request_id": provider_request_id,
            },
            "identity": {
                "acting_identity": actor_id,
                "court_purpose": purpose,
                "court_stance": "none",
                "evaluation_arm": "none",
                "provider_kind": provider_kind,
                "requested_model_id": requested_model_id,
                "served_model_id": served_model_id,
                "model_revision": attribution.model_revision,
                "host_id": attribution.host_id,
                "adapter_version": NORMALIZATION_VERSION,
            },
            "inputs": {
                "request_digest": request_digest,
                "prompt_layer_digest": attribution.prompt_layer_digest,
                "context_digest": attribution.context_digest,
                "memory_selection_digest": attribution.memory_selection_digest,
                "selected_count": attribution.selected_count,
                "omitted_count": attribution.omitted_count,
                "bodies_persisted": False,
            },
            "resources": {
                "elapsed_ms": duration_ms,
                "compute_ms": None,
                "peak_memory_bytes": None,
                "energy_joules": None,
                "budget_lease_id": budget_lease_id,
                "reservation": None,
                "consumption": None,
                "retry_index": retry_index,
                "loop_signal_id": None,
                "tool_id": None,
            },
            "cost": {
                "amount": None,
                "currency": None,
                "price_card_version": None,
                "provenance": "unknown",
                "uncertainty": "unknown",
            },
            "result": {
                "outcome": outcome,
                "terminal_relationship": (
                    "terminal" if outcome is not None else "pending"
                ),
                "error_class": error_class,
                "redaction": "bodies-excluded",
                "progress_fingerprint": None,
                "value_link": None,
            },
            "governance": {
                "sensitivity": "private",
                "retention": "governed",
                "consent_policy": "foundation-local-v1",
                "quarantine_state": "none",
                "exporter": "disabled",
                "deletion_status": "retained",
                "reconciliation_status": "pending",
                "access_purpose": purpose,
                "access_audit_ref": attribution.access_audit_ref,
            },
        }

    @staticmethod
    def _attribution_from_started(started: Mapping[str, Any]) -> UsageAttribution:
        correlation = started["correlation"]
        identity = started["identity"]
        inputs = started["inputs"]
        governance = started["governance"]
        if not all(
            isinstance(value, Mapping)
            for value in (correlation, identity, inputs, governance)
        ):
            raise ValueError("durable usage attribution is invalid")
        return UsageAttribution(
            mission_id=correlation.get("mission_id"),
            run_id=correlation.get("run_id"),
            step_id=correlation.get("step_id"),
            role=correlation.get("role"),
            work_item_id=correlation.get("work_item_id"),
            idea_id=correlation.get("idea_id"),
            case_id=correlation.get("case_id"),
            experiment_id=correlation.get("experiment_id"),
            span_id=correlation.get("span_id"),
            prompt_layer_digest=inputs.get("prompt_layer_digest"),
            context_digest=inputs.get("context_digest"),
            memory_selection_digest=inputs.get("memory_selection_digest"),
            selected_count=inputs.get("selected_count"),
            omitted_count=inputs.get("omitted_count"),
            model_revision=identity.get("model_revision"),
            host_id=identity.get("host_id"),
            access_audit_ref=governance.get("access_audit_ref"),
        )


class ReceiptedModelProvider:
    """Opt-in provider adapter that durably receipts each physical attempt.

    It preserves the wrapped provider protocol and is never selected by default.
    """

    def __init__(
        self,
        provider: ModelProvider,
        recorder: UsageRecorder,
        *,
        purpose: str,
        actor_id: str,
        trace_id: str,
        budget_lease_id: str | None = None,
        attribution: UsageAttribution | None = None,
    ) -> None:
        self.provider = provider
        self.recorder = recorder
        self.purpose = purpose
        self.actor_id = actor_id
        self.trace_id = trace_id
        self.budget_lease_id = budget_lease_id
        self.attribution = attribution or UsageAttribution()
        self.config = provider.config
        self.kind = provider.kind

    def build_request_body(self, request: ModelRequest) -> bytes:
        return self.provider.build_request_body(request)

    def complete_once(self, request: ModelRequest) -> ModelResponse:
        return self._complete_once(request, retry_index=0)

    def _complete_once(
        self,
        request: ModelRequest,
        *,
        retry_index: int,
    ) -> ModelResponse:
        body = self.provider.build_request_body(request)
        request_digest = f"sha256:{sha256(body).hexdigest()}"
        logical_request_id = stable_id(
            "logical-request",
            {
                "repository_id": self.recorder.repository_id,
                "request_digest": request_digest,
                "purpose": self.purpose,
            },
        )
        attempt_id = self.recorder.start_attempt(
            logical_request_id=logical_request_id,
            retry_index=retry_index,
            provider_kind=self.kind.value,
            requested_model_id=self.config.model,
            purpose=self.purpose,
            actor_id=self.actor_id,
            request_digest=request_digest,
            budget_lease_id=self.budget_lease_id,
            trace_id=self.trace_id,
            attribution=self.attribution,
        )
        started = time.perf_counter()
        try:
            response = self.provider.complete_once(request)
        except BaseException as error:
            failed_response = (
                ModelResponse("", error.raw_body, None, None)
                if isinstance(error, ModelResponseError)
                else None
            )
            self.recorder.finish_attempt(
                attempt_id=attempt_id,
                logical_request_id=logical_request_id,
                provider_kind=self.kind.value,
                outcome="provider-failure",
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                response=failed_response,
                error_class=type(error).__name__,
            )
            raise
        self.recorder.finish_attempt(
            attempt_id=attempt_id,
            logical_request_id=logical_request_id,
            provider_kind=self.kind.value,
            outcome="succeeded",
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            response=response,
        )
        return response

    def complete(self, request: ModelRequest) -> ModelResponse:
        last_error: ModelTransportError | None = None
        for retry_index in range(self.config.max_retries + 1):
            try:
                return replace(
                    self._complete_once(request, retry_index=retry_index),
                    transport_retry_index=retry_index,
                )
            except ModelTransportError as error:
                last_error = error
        raise ModelTransportError(
            f"model transport failed after {self.config.max_retries + 1} "
            f"attempts: {last_error}"
        ) from None


@dataclass(frozen=True, slots=True)
class AxisReconciliationResult:
    axes: tuple[dict[str, Any], ...]
    double_count_guard: str = "orthogonal-axes-never-summed"


def reconcile_usage_axes(
    observations: list[Mapping[str, Any]],
) -> AxisReconciliationResult:
    """Compare like-for-like dimensions without creating a cross-axis total."""

    allowed_sources = {
        "estimate",
        "host-report",
        "invoice",
        "provider-report",
    }
    allowed_dimensions = {
        "direction": {"input", "output", "reported_total"},
        "cache_input": {"read", "total", "uncached", "write"},
        "modality": {"audio", "image", "text", "unknown"},
        "output_kind": {"reasoning_subset", "total"},
        "billable": {"status"},
    }
    grouped: dict[tuple[str, str], dict[str, int | str | None]] = {}
    for observation in observations:
        if set(observation) != {"source", "axis", "dimension", "value"}:
            raise ValueError("axis observations require exact source/axis/dimension/value")
        source = observation["source"]
        axis = observation["axis"]
        dimension = observation["dimension"]
        value = observation["value"]
        if source not in allowed_sources:
            raise ValueError("unknown reconciliation source")
        if (
            not isinstance(axis, str)
            or not isinstance(dimension, str)
            or dimension not in allowed_dimensions.get(axis, set())
        ):
            raise ValueError("unknown reconciliation axis or dimension")
        if axis == "billable":
            if value not in {None, "billable", "non-billable", "unavailable", "unknown"}:
                raise ValueError("billable status is outside the fixed vocabulary")
        elif value is not None and (
            type(value) is not int or not 0 <= value <= 10**15
        ):
            raise ValueError("axis value must be unknown or a bounded integer")
        key = (axis, dimension)
        sources = grouped.setdefault(key, {})
        if source in sources:
            raise ValueError("duplicate source observation for an axis dimension")
        sources[str(source)] = value
    axes: list[dict[str, Any]] = []
    for (axis, dimension), sources in sorted(grouped.items()):
        known = {value for value in sources.values() if value is not None}
        status = (
            "unknown"
            if not known
            else "complete"
            if len(known) == 1 and all(value is not None for value in sources.values())
            else "conflicting"
            if len(known) > 1
            else "partial"
        )
        axes.append(
            {
                "axis": axis,
                "dimension": dimension,
                "observations": dict(sorted(sources.items())),
                "status": status,
            }
        )
    return AxisReconciliationResult(tuple(axes))


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    status: str
    matched_attempt_ids: tuple[str, ...]
    missing_attempt_ids: tuple[str, ...]
    duplicate_attempt_ids: tuple[str, ...]
    residuals: tuple[dict[str, Any], ...]
    unavailable: bool


def reconcile_invoice(
    usage_records: list[Mapping[str, Any]],
    invoice_lines: list[Mapping[str, Any]] | None,
) -> ReconciliationResult:
    attempts = {
        str(record["attempt_id"]): record
        for record in usage_records
        if record.get("event_kind") == "attempt-terminal"
    }
    if invoice_lines is None:
        return ReconciliationResult(
            "unavailable", (), tuple(sorted(attempts)), (), (), True
        )
    seen: set[str] = set()
    duplicates: set[str] = set()
    matched: set[str] = set()
    residuals: list[dict[str, Any]] = []
    for line in invoice_lines:
        attempt_id = str(line.get("attempt_id", ""))
        if attempt_id in seen:
            duplicates.add(attempt_id)
            continue
        seen.add(attempt_id)
        usage = attempts.get(attempt_id)
        if usage is None:
            residuals.append({"attempt_id": attempt_id, "reason": "invoice-only"})
            continue
        try:
            amount = Decimal(str(line["amount"]))
            if not amount.is_finite() or amount < 0:
                raise InvalidOperation
        except (KeyError, InvalidOperation):
            residuals.append({"attempt_id": attempt_id, "reason": "invalid-amount"})
            continue
        if not isinstance(line.get("currency"), str) or not line["currency"]:
            residuals.append({"attempt_id": attempt_id, "reason": "missing-currency"})
            continue
        matched.add(attempt_id)
    missing = set(attempts) - matched
    status = (
        "conflicting"
        if duplicates
        else "complete"
        if not missing and not residuals
        else "partial"
    )
    return ReconciliationResult(
        status,
        tuple(sorted(matched)),
        tuple(sorted(missing)),
        tuple(sorted(duplicates)),
        tuple(residuals),
        False,
    )
