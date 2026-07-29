# ADR-020: Provider-Native Usage, Privacy, and Fair Learning

- Status: adopted as the Phase 1 architecture contract; additive implementation begins in Phase 2
- Date: 2026-07-28
- Constitutional impact: yes

## Context

Generation zero retains only two optional model token fields, locally estimated
compute/token costs, selected durations, and disconnected budget counters.
Provider semantics, retries, host telemetry, prices, invoices, memory use, and
court purpose are not completely attributable or reconcilable.

## Decision

Phase 2 will add an append-only usage event that retains provider-native
dimensions and separately derives versioned normalized dimensions. Every
model/tool attempt must bind to repository, mission, run, step, role, work
item, acting/court purpose, provider/model/version, budget lease, prompt/context
digests, outcome, retry, and trace identifiers.

The local transactional outbox is authoritative for emission. Metrics and
traces are projections. No outbound telemetry service is required.

The normative Phase 1 envelope is `hive-usage-event/v1` in
`docs/architecture/PHASE1_CANONICAL_CONTRACTS.md`. Adoption does not change
`ModelResponse`, `model.call`, provider parsing, budget behavior, or any
Generation Zero API. It does not enable an exporter, learning policy,
quarantine action, or champion switch.

## Normalization and reconciliation invariants

- Native observations are immutable; normalization never overwrites them.
- Input/output, cached/uncached, reasoning, billable, and modality dimensions
  are separate axes and are not blindly summed.
- Unknown is not zero.
- Estimates, provider reports, host reports, prices, and invoices retain
  separate provenance and uncertainty.
- Cost includes currency and price-card version.
- Every retry/attempt has its own receipt and one terminal relationship.
- Reconciliation reports gaps rather than manufacturing equality.

## Privacy and security

Default events exclude prompt/response bodies and secrets. Digests,
high-cardinality IDs, summaries, and error text still require classification,
redaction, retention, tenant isolation, access audit, and deletion policy.
Metric labels use bounded vocabularies. Exporters are replaceable, disabled by
default, and cannot expand collection authority.

Threats include cardinality denial of service, secret leakage, forged provider
usage, double counting, missing failed attempts, price drift, telemetry
tampering, evaluator gaming, and champion/challenger resource asymmetry.

## Fair-learning evaluation

Before comparison, seal task inputs, future commits, memory packets, identities,
provider/model policy, tools, budgets, stop rules, metric version, and access
logs. Apply absolute customer-value, correctness, trust, privacy, leakage,
authority, and rollback gates to both champion and challenger. Then compare
outcomes with uncertainty under equal resource policy. Either side may fail;
inconclusive evidence defers promotion.

Measure marginal verified value per token, cost, time, and tool call alongside
quality and trust. Activity, novelty, token minimization, and agent survival are
not objectives.

## Migration and rollback

Dual-emit generation-zero `model.call` plus additive usage events. Reconcile
counts and provider fixtures before consumers move. Rollback disables the new
consumer/exporter and retains native events, normalization version, gaps, and
failed receipts. Never rewrite old usage to fit a new mapping or price.

## Acceptance

- provider fixtures cover native fields, missing fields, retries, failures, and
  unknown semantics;
- per-axis reconciliation and deliberate double-count tests pass;
- crash recovery produces no lost or duplicated terminal attempts;
- privacy/redaction/cardinality tests pass;
- champion and challenger receive equivalent sealed resources;
- invoices reconcile where available and remain explicitly unavailable where
  not; and
- independent Curator and Judge receipts precede any learning or budget-policy
  activation.
