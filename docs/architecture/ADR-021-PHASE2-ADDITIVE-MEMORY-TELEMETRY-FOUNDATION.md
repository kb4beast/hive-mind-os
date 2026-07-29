# ADR-021: Additive memory and telemetry foundation

- Status: adopted for Phase 2 implementation; activation remains prohibited
- Date: 2026-07-28
- Governing records: ADR-018, ADR-019, ADR-020, and the Phase 2 delivery court

## Context

Phase 1 adopted canonical agent, memory, Obsidian-projection, and usage contracts while
freezing Generation Zero. Phase 2 must implement the underlying memory and telemetry
foundation without changing the selected runtime, its two legacy SQLite stores, its
prompts, package selection, CLI, or supported public facades.

The principal conflict is atomicity. Adding memory, opportunity, accounting, and
outbox data to separate databases would make a single governed write impossible.
Adding tables to `EvidenceLedger` would mutate the captured Generation Zero store.

## Decision

Adopt one private, opt-in `FoundationStore` with SQLite WAL, `synchronous=FULL`,
foreign keys, bounded busy timeout, and immediate write transactions. It is a new
authority for Phase 2 records only. Generation Zero remains selected and unchanged.

The store contains immutable repository identities, append-only record streams,
relations, exact/structured opportunity keys, outbox messages, delivery attempts, and
acknowledgements. A record and its local outbox message commit in one transaction.
Delivery state is represented by append-only receipts rather than mutation.

Phase 2 schemas and generated candidates live under
`hive_mind_os.foundation`, outside the frozen legacy schema catalog and top-level
facades. The wheel verifies the original 20 schemas plus the separately counted
foundation resources. Eight versioned canonical agent sources compile to eight inert
generated definitions plus a manifest. The compiler binds their prompt-layer digests
to the frozen Generation Zero prompts; generated definitions remain authority-free.

Every material foundation write is bounded by:

`role ceiling ∩ policy decision ∩ lease ∩ adapter enforcement ∩ mission risk ∩ budget`.

Missing input denies. A generated file, memory, usage event, outcome, or apparent
success cannot grant authority. Usage collection requires the fixed trusted-recorder
identity. Store entry points enforce the decision and action/type boundary. A
safe-public record additionally requires an explicit independent public-release
decision bound to tenant, repository, actor, lease, subject digest, and an
independently attributable decider. Those references are stored with the record.

Idea handling is encounter-first. Exact and structured matches are transactional.
Semantic matches are candidates only and cannot merge. Relationships and appeals are
append-only.

Usage keeps logical-request, physical-attempt, provider-request, and receipt identity
separate. Provider-shaped fixture fields are preserved as bounded numeric native
paths. Normalization is versioned and keeps direction, cache, modality, output kind,
and billing axes separate. Caller-supplied mission, run, step, role, work item,
court/experiment, prompt-layer, context, and memory-selection attribution is bounded
and survives start, terminal, and restart-recovery receipts. Missing is unknown,
never zero. Decisions, outcomes, attribution, corrections, and invoices are
late-bound append-only records.

Observability is local-only. Metrics use a fixed low-cardinality label vocabulary.
Correlated trace and OpenTelemetry-shaped envelopes may carry governed identifiers,
but bodies and free-text errors are prohibited. Export is disabled by default.

The database is self-identifying. Initialization refuses every non-empty unversioned
database, including Generation Zero stores, and validates an immutable schema-object
digest before reopening a same-version database. First initialization publishes
tables, triggers, ownership marker, schema digest, and user version in one rollbackable
transaction.

## Consequences

- The foundation can be enabled in a shadow caller by wrapping a model provider with
  `ReceiptedModelProvider`; no default constructor, selector, or CLI changes.
- A started attempt is durable before I/O and a terminal usage record is durable
  before the wrapper returns or re-raises. Restart converts a nonterminal attempt to
  interrupted/unknown without inventing usage and preserves the durable caller
  attribution.
- Atomicity is claimed only inside the foundation database. No exactly-once external
  side effect or cross-database transaction is claimed.
- Provider fixtures prove parser behavior, not live provider billing conformance.
  Provider observations and numeric values are bounded. Trace identities, attribute
  counts, names, keys, and values are validated both when constructed and when
  projected to the local OpenTelemetry envelope. Axis conflicts propagate to
  top-level accounting state, including fixed-vocabulary billable status.
- Obsidian, role activation, active leases/loop control/quarantine, host adapters, and
  champion promotion remain in later phases.

## Threats and mitigations

- A unified local store is a compromise target: it stores no prompt/response/tool
  body by default, requires tenant/repository scope, and uses append-only triggers.
- Digests can expose low-entropy content: foundation APIs reject raw body fields and
  treat all new records as private unless policy explicitly says otherwise.
- Dual records can disagree: the outbox and invoice reconciliation retain gaps and
  residuals rather than manufacturing equality.
- Concurrent dedup can erase dissent: every encounter survives, semantic targets are
  typed, classification requires the staged relation, and matching never auto-merges.
- Generated churn can hide edits: deterministic byte generation binds source and
  output digests, and `--check` rejects hand edits.
- Advisory authority can be bypassed by direct store calls: every material write
  requires a matching allowed decision; type/action and safe-public release are
  enforced at the storage boundary.

## Rollback

Stop constructing foundation stores and provider wrappers. Generation Zero continues
unchanged. Retain the foundation database, pending outbox, dissent, gaps, and receipts
for appeal; never delete or rewrite them as rollback.
