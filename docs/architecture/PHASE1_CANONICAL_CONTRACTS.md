# Phase 1 Canonical Redesign Contracts

- Status: adopted architecture; production implementation is not active
- Governing decisions: ADR-018, ADR-019, and ADR-020
- Generation Zero champion: unchanged
- Phase 1 source court:
  `evidence/courts/P1-SOURCE-ADMISSION.md`
- Atomic claim register:
  `evidence/courts/P1-ATOMIC-CLAIM-REGISTER.md`

This document closes the Phase 1 architecture obligation by defining the
canonical contracts that Phase 2 and later challengers must implement. These
are design contracts, not new runtime schemas. A field named here does not
exist in production until an additive schema, migration, implementation,
conformance fixture, rollback receipt, independent Curator, and Judge approve
it.

## Generation Zero boundary

The existing Python facade remains the active champion. The generated
characterization inventory freezes:

- 131 `hive_mind_os.__all__` bindings;
- 33 `hive_mind_os.package_system.__all__` bindings;
- 13 semantic CLI parser contracts;
- 304 de-facto module definitions, without promoting them to supported API;
- 48 ledger sinks, 53 event-producing sites, 47 literal event types, and 224
  bounded effect sites; and
- the existing role, prompt, package, schema, SQLite, provider-parser, and
  `model.call` receipts.

Phase 1 changes no file under `src/hive_mind_os`, no schema resource, no
package resource, no prompt, no database shape, and no runtime selector.

## `hive-agent-definition/v2`

One versioned agent definition is the canonical design authority for an agent
challenger. It must contain:

| Field family | Required content |
| --- | --- |
| Identity | definition ID, schema version, role ID, version, content digest, status, supersedes/rollback references |
| Constitutional duty | mission, non-delegable duties, forbidden actions, lifecycle stages, failure and stop conditions |
| Typed behavior | input and output contract references, quality gates, acceptance and behavioral evaluation references |
| Composition | ordered prompt-layer references, independently versioned skill references, typed tool references, workflow references |
| Boundaries | requested capabilities, constitutional ceiling reference, policy-action mapping version, lease requirements, risk ceiling |
| Memory | allowed record classes, read/write purposes, sensitivity, retention, retrieval and contamination rules |
| Usage | supported usage-event version, budget dimensions, unknown-accounting and reconciliation behavior |
| Portability | projection target, host evidence version, unsupported/degraded capabilities, conformance status |
| Governance | sources, court cases, dissent, owner, activation prerequisites, rollback and quarantine rules |

The eight constitutional role identifiers and the Generation Zero lifecycle
order remain frozen. A ninth role is a constitutional change, not an extension.
Role enum iteration is not lifecycle order.

Prompts are deterministic projections of ordered content-addressed layers.
Skills are reusable typed procedures and never identities or grants. Tool
descriptions bind to enforced adapters but do not implement authority. Host
artifacts are projections and must report unsupported semantics.

## `hive-memory/v1`

The canonical open memory authority is an append-only, local-first,
provider-neutral record envelope:

| Field family | Required content |
| --- | --- |
| Identity and scope | record ID, schema version, record type, repository instance, tenant, mission/run/step, actor identity |
| Integrity and time | payload digest, previous/superseded record, observed and recorded timestamps, causation/correlation |
| Provenance | source, claim, evidence, court, code/receipt and generation references |
| Knowledge quality | status, confidence, freshness/expiry, contradiction, duplicate/refinement relation, owner |
| Governance | sensitivity, access purpose, retention, deletion/tombstone policy, quarantine and appeal state |
| Content | typed safe content reference or bounded summary; never private hidden chain-of-thought |

The record types must cover working, episodic, semantic, procedural,
prospective, decision, opportunity, counterfactual, social, evaluation,
resource, and governance memory. Every material mission object has a record or
an explicit not-applicable disposition. Every retrieval records selected and
omitted IDs, ordering, purpose, policy result, and critical-context coverage.

The authoritative writer is a local transactional outbox/WAL that can
reconcile with Generation Zero stores. Search indexes, embeddings, metrics,
traces, Markdown, HTML, Canvas, Bases, and caches are rebuildable projections.

## `hive-obsidian-projection/v1`

Obsidian is an optional human workbench over the open memory authority.
Projection records require:

- stable memory-derived note IDs and relative paths;
- source record ID, source digest, projector version, projection time, status,
  sensitivity decision, and expected prior digest;
- safe-public allowlisting and redaction receipts;
- deterministic Markdown/YAML bytes using portable field types;
- staging, validation, atomic replacement, interruption recovery, and conflict
  preservation;
- generated and human namespaces that cannot silently overwrite each other;
  and
- a no-Obsidian CLI/editor path using ordinary files.

Generated views never mutate canonical state and are excluded from source,
idea, novelty, and telemetry ingestion. Human/Obsidian input is an untrusted
Inbox proposal only and requires a separate validated, idempotent, dry-runnable
import court before implementation.

The repository root may be opened directly as a vault. `.obsidian/` is
local-only and ignored in Phase 1. No plugin, importer, account, paid Sync
service, watcher, or executable host is required or supported. Remote Git
updates remain explicit Git operations; only local file refresh is automatic.

## `hive-usage-event/v1`

Every model or governed tool attempt must eventually emit one immutable native
attempt event or an explicit unknown-accounting failure:

| Field family | Required content |
| --- | --- |
| Correlation | repository, tenant, mission, run, step, role, work item, idea, case, experiment, trace/span, attempt and provider request IDs |
| Identity | acting identity, court purpose/stance, evaluation arm, provider, model, model revision, host and adapter version |
| Inputs | request, prompt-layer, context and memory-selection digests; selected/omitted counts; no bodies by default |
| Native usage | provider field names/values/units and provenance, with missing distinct from zero |
| Normalized usage | versioned orthogonal axes for input/output, cached/uncached, reasoning, modality and billable status |
| Resources | tool, elapsed time, compute/memory/energy when available, budget reservation/consumption, retry and loop linkage |
| Cost | amount, currency, price-card version, estimate/report/invoice provenance and uncertainty |
| Result | outcome, terminal relationship, error class/redaction, progress fingerprint, value/effectiveness linkage |
| Governance | sensitivity, retention, consent/policy, quarantine, exporter and deletion/reconciliation status |

Inclusive and exclusive dimensions are never blindly summed. Native,
normalized, estimated, host-reported, provider-reported, price-card, and
invoice observations remain separate. Unknown is never zero. Metrics use
bounded labels; high-cardinality identifiers stay in governed records/traces.
Export is disabled by default and cannot expand collection authority.

## Effective authority

The effective permission for any side effect is:

```text
constitutional role ceiling
INTERSECT versioned policy action
INTERSECT explicit lease or required external grant
INTERSECT selected adapter enforcement
INTERSECT mission risk and resource budgets
```

Any missing identity, mapping, lease, adapter enforcement, source license,
evidence, rollback, or independence requirement denies the action. Capability
requests, manifests, prompts, skills, memory, Obsidian notes, telemetry,
metrics, evaluation wins, and past success never expand authority.

The acting Builder cannot verify, judge, promote, or merge its own work. An
Explorer cannot modify production. Curator and Judge identities must be
separate from the affected acting, architecture, and advocacy identities.

## Threat, privacy, and isolation contract

Phase 2 and Phase 3 implementations must test:

- canonical-source compromise and generated-diff concealment;
- capability-to-grant confusion and host semantic loss;
- prompt/memory/Obsidian injection and generated-view re-ingestion;
- secret, private-repository, tenant, and cross-repository disclosure;
- concurrent writers, stale projections, partial replacement, replay, and
  crash recovery;
- false duplicate merge, contradiction erasure, retrieval contamination, and
  deletion/tombstone reconciliation;
- forged or missing provider usage, retries, price drift, double counting,
  cardinality denial of service, exporter leakage, and evaluator gaming; and
- recursive self-host projection, telemetry, idea, and delegation loops.

Private payloads must be stored outside the safe-to-publish memory pack under
repository/tenant isolation. Default events and projections exclude prompt and
response bodies, secrets, hidden reasoning, and private repository content.

## Migration and rollback

1. Keep every Generation Zero facade, fixture, prompt, store, and selector.
2. Add v2 records and schemas without runtime activation.
3. Dual-write only through a local transactional outbox and reconcile each old
   store/event against the new record.
4. Generate deterministic candidate projections and fail on drift.
5. Run privacy, recovery, compatibility, behavioral, and equal-budget shadow
   evaluations.
6. Promote one independently controlled pointer at a time.

Rollback moves the independently controlled pointer to the last verified
Generation Zero or prior champion, disables new writers/consumers/projectors,
and preserves new records, dissent, failures, conflicts, fixtures, and
receipts. Rollback never rewrites history or deletes human-authored notes.
The complete Phase 1 rollback plan is
`docs/architecture/PHASE1_ROLLBACK_PLAN.md`.

## Observability and evaluation

Required Phase 2/3 measures include outbox lag, replay/reconciliation gaps,
projection age/conflicts, privacy/redaction failures, cross-tenant escapes,
retrieval precision/recall and contamination, explicit unknown-accounting
share, per-axis usage error, loop detection precision/recall, time-to-break,
absolute customer value/trust, and rollback recovery time.

Champion/challenger comparisons seal tasks, commits, memory packets,
identities, provider/model policy, tools, budgets, stop rules, metric version,
and access logs. Both arms face the same absolute value, correctness, safety,
privacy, authority, and rollback gates. Either may fail; inconclusive evidence
promotes neither.
