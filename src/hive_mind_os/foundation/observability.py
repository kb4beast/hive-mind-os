from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

ALLOWED_METRIC_LABELS = frozenset(
    {
        "outcome",
        "provider_kind",
        "record_type",
        "reconciliation_status",
        "schema_version",
        "sensitivity",
    }
)
PROHIBITED_METRIC_LABELS = frozenset(
    {
        "attempt_id",
        "correlation_id",
        "digest",
        "error",
        "idea_id",
        "mission_id",
        "model_id",
        "path",
        "repository_id",
        "request_id",
        "span_id",
        "tenant_id",
        "trace_id",
        "url",
        "user_id",
    }
)
METRIC_LABEL_VALUES = {
    "outcome": frozenset(
        {
            "abandoned",
            "cancelled",
            "failed",
            "interrupted",
            "invalid-output",
            "provider-failure",
            "succeeded",
            "unknown",
        }
    ),
    "provider_kind": frozenset({"anthropic", "openai_compatible", "unknown"}),
    "record_type": frozenset(
        {
            "attribution-record",
            "decision-record",
            "idea-encounter",
            "memory-record",
            "opportunity-record",
            "outcome-record",
            "usage-event",
            "usage-reconciliation",
        }
    ),
    "reconciliation_status": frozenset(
        {"complete", "conflicting", "missing", "partial", "unavailable", "unknown"}
    ),
    "schema_version": frozenset({"1", "2"}),
    "sensitivity": frozenset({"internal", "private", "safe-public"}),
}
ALLOWED_METRIC_NAMES = frozenset(
    {
        "hive.foundation.outbox.pending",
        "hive.foundation.records",
        "hive.foundation.reconciliation",
        "hive.foundation.usage.attempts",
    }
)
_METRIC_NAME = re.compile(r"hive\.foundation\.[a-z0-9_.]{1,48}\Z")
_MAX_METRIC_VALUE = 10**15
_MAX_TRACE_ATTRIBUTES = 32
_MAX_TRACE_IDENTIFIER = 256
_MAX_TRACE_NAME = 128
_MAX_TRACE_KEY = 64
_MAX_TRACE_VALUE = 256
_PROHIBITED_TRACE_FRAGMENTS = frozenset(
    {
        "api_key",
        "authorization",
        "body",
        "content",
        "credential",
        "error_message",
        "header",
        "password",
        "prompt",
        "raw",
        "request",
        "response",
        "secret",
        "token",
    }
)
_RESERVED_TRACE_ATTRIBUTES = frozenset(
    {"gen_ai.operation.name", "gen_ai.provider.name", "hive.outcome"}
)


@dataclass(frozen=True, slots=True)
class MetricPoint:
    name: str
    value: int
    labels: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class TraceRecord:
    name: str
    trace_id: str
    span_id: str
    attributes: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        _validate_trace_record(self)


@dataclass(frozen=True, slots=True)
class OTelEnvelope:
    """Dependency-free local envelope using admitted OpenTelemetry vocabulary."""

    event_name: str
    trace_id: str
    span_id: str
    attributes: tuple[tuple[str, str], ...]
    export_enabled: bool = False


def _validate_trace_record(trace: TraceRecord) -> None:
    if (
        not isinstance(trace.name, str)
        or not trace.name
        or len(trace.name) > _MAX_TRACE_NAME
        or not isinstance(trace.trace_id, str)
        or not trace.trace_id
        or len(trace.trace_id) > _MAX_TRACE_IDENTIFIER
        or not isinstance(trace.span_id, str)
        or not trace.span_id
        or len(trace.span_id) > _MAX_TRACE_IDENTIFIER
        or not isinstance(trace.attributes, tuple)
        or len(trace.attributes) > _MAX_TRACE_ATTRIBUTES
    ):
        raise ValueError("trace identity or attribute count is unbounded")
    seen: set[str] = set()
    for item in trace.attributes:
        if (
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or not isinstance(item[1], str)
        ):
            raise ValueError("trace attributes must be string pairs")
        key, value = item
        normalized_key = key.casefold().replace("-", "_")
        if (
            not key
            or len(key) > _MAX_TRACE_KEY
            or len(value) > _MAX_TRACE_VALUE
            or key in seen
            or key in _RESERVED_TRACE_ATTRIBUTES
            or any(
                fragment in normalized_key
                for fragment in _PROHIBITED_TRACE_FRAGMENTS
            )
        ):
            raise ValueError(f"trace attribute {key} is unsupported or unbounded")
        seen.add(key)


def project_metric(
    name: str,
    value: int,
    labels: Mapping[str, str],
) -> MetricPoint:
    if _METRIC_NAME.fullmatch(name) is None or name not in ALLOWED_METRIC_NAMES:
        raise ValueError("metric name is outside the bounded foundation namespace")
    unknown = set(labels) - ALLOWED_METRIC_LABELS
    if unknown:
        raise ValueError(f"unbounded metric labels are prohibited: {sorted(unknown)}")
    if set(labels) & PROHIBITED_METRIC_LABELS:
        raise ValueError("high-cardinality metric labels are prohibited")
    if type(value) is not int or not 0 <= value <= _MAX_METRIC_VALUE:
        raise ValueError("metric value must be a bounded nonnegative integer")
    for key, label in labels.items():
        if label not in METRIC_LABEL_VALUES[key]:
            raise ValueError(f"metric label {key} is outside its fixed vocabulary")
    return MetricPoint(name, value, tuple(sorted(labels.items())))


def project_trace(
    name: str,
    *,
    trace_id: str,
    span_id: str,
    attributes: Mapping[str, Any],
) -> TraceRecord:
    if (
        not name
        or len(name) > _MAX_TRACE_NAME
        or not trace_id
        or len(trace_id) > _MAX_TRACE_IDENTIFIER
        or not span_id
        or len(span_id) > _MAX_TRACE_IDENTIFIER
        or len(attributes) > _MAX_TRACE_ATTRIBUTES
    ):
        raise ValueError("trace identity or attribute count is unbounded")
    if set(attributes) & _RESERVED_TRACE_ATTRIBUTES or any(
        fragment in key.casefold().replace("-", "_")
        for key in attributes
        for fragment in _PROHIBITED_TRACE_FRAGMENTS
    ):
        raise ValueError("trace attributes cannot contain body or free-text fields")
    normalized: list[tuple[str, str]] = []
    for key, value in sorted(attributes.items()):
        if (
            not key
            or len(key) > _MAX_TRACE_KEY
            or not isinstance(value, (str, int, bool))
            or len(str(value)) > _MAX_TRACE_VALUE
        ):
            raise ValueError(f"trace attribute {key} is unsupported or unbounded")
        normalized.append((key, str(value)))
    return TraceRecord(name, trace_id, span_id, tuple(normalized))


def project_otel_envelope(
    trace: TraceRecord,
    *,
    provider_kind: str,
    outcome: str,
) -> OTelEnvelope:
    _validate_trace_record(trace)
    if (
        provider_kind not in METRIC_LABEL_VALUES["provider_kind"]
        or outcome not in METRIC_LABEL_VALUES["outcome"]
    ):
        raise ValueError("OpenTelemetry provider/outcome is outside fixed vocabulary")
    attributes = {
        **dict(trace.attributes),
        "gen_ai.operation.name": trace.name,
        "gen_ai.provider.name": provider_kind,
        "hive.outcome": outcome,
    }
    return OTelEnvelope(
        event_name="gen_ai.client.operation",
        trace_id=trace.trace_id,
        span_id=trace.span_id,
        attributes=tuple(sorted(attributes.items())),
        export_enabled=False,
    )
