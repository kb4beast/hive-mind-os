# Phase 1 Court: Usage Telemetry and Fair Learning

- Case ID: `P1-USAGE-TELEMETRY-FAIR-LEARNING`
- Status: hearing open; independent testimony and verdict pending
- Original request SHA-256:
  `dbd73add9f47aa98a30d19f1538179e5e961c1452a70b9ce54b7403b4e387a46`

## Frozen parent claims

- `TEL-001`: Retain granular provider-native usage and cost, then derive
  provider-normalized views without double counting.
- `TEL-002`: Attribute use to mission, role, idea, court stance, and
  champion/challenger/neutral purpose.
- `TEL-003`: Measure agent effectiveness and marginal verified value.
- `TEL-004`: Detect loops, retry storms, context churn, and stalled progress.
- `TEL-005`: Enforce hierarchical budget circuit breakers and evidence-bound,
  scoped, appealable quarantine.
- `TEL-006`: Compare champions and challengers under sealed fair conditions
  where either can fail and inconclusive evidence cannot promote.

## Generation-zero evidence

The runtime inventory proves that OpenAI-compatible and Anthropic usage are
collapsed into two optional fields; cached/reasoning/modality/billable/cost and
invoice semantics are absent. `ModelBackend`, `AutonomyBudget`, and
`ExperimentRunner` use different accounting/estimation paths and do not
reconcile. Host profiles are unverified and provide no telemetry adapter.

The characterization fixture freezes these limitations rather than treating
missing values as zero.

## Advocate case

Pinned OpenTelemetry conventions, mutable provider documentation, and
generation-zero code all demonstrate that native meanings differ. Immutable
native attempt receipts plus explicitly versioned per-axis normalization avoid
false universal counters. A local outbox permits later metrics/traces without
making any exporter authoritative.

## Cross-examination and dissent

OpenTelemetry GenAI conventions are `Development`. Provider pages are mutable.
Fine-grained events increase privacy, cardinality, cost, and gaming risk.
Relative efficiency can reward low-quality or under-instrumented agents.
Prices/invoices may be unavailable, and unknown must not become zero. Evaluation
papers do not prove this system’s fairness.

## Architecture, metrics, and rollback

Candidate decision: ADR-020. Required metrics include model-attempt capture,
explicit unknown-accounting share, per-axis reconciliation error, budget-versus-
usage delta, secret leakage, loop detector precision/recall/time-to-break,
absolute customer value/trust, and equal sealed resources.

Migration dual-emits old `model.call` and additive native usage events.
Rollback disables new consumers/exporters but retains attempts, mapping
versions, reconciliation gaps, failures, and dissent.

## Open obligations

`P1-SRC-B02` through `P1-SRC-B04`, provider fixture coverage, price/version and
invoice policy, privacy/security expert testimony, held-out evaluation design,
 loop benchmark, and a distinct Judge receipt remain blocking.

The independent Curator `/root/phase1_curator` accepted the accuracy of the
repaired generation-zero telemetry characterization. Provider-source
admission, ADR-020 adoption, Phase 2 implementation, and the distinct Judge
receipt remain blocked.
