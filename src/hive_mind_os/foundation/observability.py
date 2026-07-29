from __future__ import annotations

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


@dataclass(frozen=True, slots=True)
class OTelEnvelope:
    """Dependency-free local envelope using admitted OpenTelemetry vocabulary."""

    event_name: str
    trace_id: str
    span_id: str
    attributes: tuple[tuple[str, str], ...]
    export_enabled: bool = False


def project_metric(
    name: str,
    value: int,
    labels: Mapping[str, str],
) -> MetricPoint:
    unknown = set(labels) - ALLOWED_METRIC_LABELS
    if unknown:
        raise ValueError(f"unbounded metric labels are prohibited: {sorted(unknown)}")
    if set(labels) & PROHIBITED_METRIC_LABELS:
        raise ValueError("high-cardinality metric labels are prohibited")
    if type(value) is not int or value < 0:
        raise ValueError("metric value must be a nonnegative integer")
    for key, label in labels.items():
        if not label or len(label) > 64:
            raise ValueError(f"metric label {key} is empty or unbounded")
    return MetricPoint(name, value, tuple(sorted(labels.items())))


def project_trace(
    name: str,
    *,
    trace_id: str,
    span_id: str,
    attributes: Mapping[str, Any],
) -> TraceRecord:
    prohibited = {"content", "error_message", "prompt", "response", "raw_body"}
    if set(attributes) & prohibited:
        raise ValueError("trace attributes cannot contain body or free-text fields")
    normalized: list[tuple[str, str]] = []
    for key, value in sorted(attributes.items()):
        if not isinstance(value, (str, int, bool)) or len(str(value)) > 256:
            raise ValueError(f"trace attribute {key} is unsupported or unbounded")
        normalized.append((key, str(value)))
    return TraceRecord(name, trace_id, span_id, tuple(normalized))


def project_otel_envelope(
    trace: TraceRecord,
    *,
    provider_kind: str,
    outcome: str,
) -> OTelEnvelope:
    attributes = {
        "gen_ai.operation.name": trace.name,
        "gen_ai.provider.name": provider_kind,
        "hive.outcome": outcome,
        **dict(trace.attributes),
    }
    return OTelEnvelope(
        event_name="gen_ai.client.operation",
        trace_id=trace.trace_id,
        span_id=trace.span_id,
        attributes=tuple(sorted(attributes.items())),
        export_enabled=False,
    )
