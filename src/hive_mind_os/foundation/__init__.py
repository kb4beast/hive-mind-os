"""Opt-in Phase 2 memory and telemetry foundation.

This package is intentionally absent from the frozen top-level facades.  Importing it
does not activate a runtime, migrate a Generation Zero store, or enable an exporter.
"""

from .authority import AuthorityDecision, decide_foundation_write
from .contracts import PHASE2_SCHEMA_NAMES, load_foundation_schema, validate_foundation
from .generation import (
    GENERATOR_VERSION,
    compile_generation_zero_candidates,
    verify_generated_candidates,
)
from .observability import (
    MetricPoint,
    OTelEnvelope,
    TraceRecord,
    project_metric,
    project_otel_envelope,
    project_trace,
)
from .opportunities import OpportunityLedger, OpportunityResult
from .store import FoundationStore, IdempotencyConflict, ScopeError
from .usage import (
    ProviderUsageAdapter,
    ReceiptedModelProvider,
    ReconciliationResult,
    UsageRecorder,
    reconcile_invoice,
)

__all__ = [
    "GENERATOR_VERSION",
    "PHASE2_SCHEMA_NAMES",
    "FoundationStore",
    "AuthorityDecision",
    "IdempotencyConflict",
    "MetricPoint",
    "OTelEnvelope",
    "OpportunityLedger",
    "OpportunityResult",
    "ProviderUsageAdapter",
    "ReceiptedModelProvider",
    "ReconciliationResult",
    "ScopeError",
    "TraceRecord",
    "UsageRecorder",
    "compile_generation_zero_candidates",
    "decide_foundation_write",
    "load_foundation_schema",
    "project_metric",
    "project_otel_envelope",
    "project_trace",
    "reconcile_invoice",
    "validate_foundation",
    "verify_generated_candidates",
]
