# Phase 1 Memory, Usage, Model, Event, and Host Path Inventory

- Status: generation-zero characterization complete; canonical Phase 1 target
  envelopes adopted without production activation
- Scope: repository state at
  `b032a9f32f48889e0889fae8d6dd04eb03f46b63`
- Truth boundary: an existing field or file path is not proof of completeness,
  privacy, replay, provider reconciliation, or host support.

## Durable and in-memory state

| Path | Writer | Stored data | Durability and replay | Known gap |
| --- | --- | --- | --- | --- |
| `EvidenceLedger` SQLite `events` | Runtime, mission, model backend, sandbox, curator, prompt and experiment paths | Run ID, event type, actor, canonical JSON payload, timestamp | WAL-backed, ordered sequence, update/delete triggers | No payload digest chain, repository identity, sensitivity, retention, tenant, schema discriminator, or transactional outbox. |
| `EvidenceLedger` SQLite `lessons` | Runtime and mission | Run, role, lesson, source event, timestamp | Append-only triggers and event foreign key | Free text; no provenance beyond one optional event, confidence, expiry, access policy, duplicate identity, or retrieval measurement. |
| `MissionStore` SQLite and mission directories | Repository mission and worker recovery | Mission record, checkpoints, intents, receipts, workspace/reconciliation state | Durable checkpoint and resume path | Separate store from the evidence ledger; no unified memory-record contract or cross-store transaction. |
| Prompt registry filesystem plus prompt ledger | Prompt bootstrap, experiments, independent promotion path | Content-addressed prompt files, lineage/events, champion pointer, quarantine | Atomic pointer replace and interprocess lock | Not a general memory system; active instructions still exist outside it. |
| Receipt and evidence JSON files | Sandbox, audit, ingestion, Git/GitHub and mission paths | Content-addressed or referenced execution/source receipts | Repository-visible evidence in several namespaces | No one catalog covers every receipt, sensitivity, retention, or deletion policy. |
| Scheduler SQLite | Worker queue | Jobs, leases, retries, dead letters | Durable lease/retry state | Operational state is not automatically joined to mission/evidence memory. |
| Source docket Python plus source exhibits | Source ingestion and audit | Sources, atomic claims, decisions, obligations, raw artifacts | Reproducible repository state | Docket remains not release-ready; Phase 1 sources are not silently admitted. |
| Projection functions | Read-only renderers | General and War Room JSON/HTML views | Rebuilt from ledger events | No open brain pack, Obsidian Markdown projection, conflict detection, tombstones, or governed annotation intake. |
| Process memory | Runtime context tuples and backend objects | Prior role summaries/evidence and active provider configuration | Lost unless separately represented in events/checkpoints | No complete call/step context replay or retrieval manifest for every execution path. |

There is no generation-zero federated memory, repository identity registry,
Obsidian brain projector, semantic index with governed provenance, or
cross-repository isolation policy.

The formal `event.schema.json` is a competing inert model: it requires stable
event/stream IDs, stream version, causation/correlation, payload and
previous-event digests, but `EvidenceLedger.append_event` validates none of
those fields. Phase 2 must adjudicate the conflict rather than silently
declaring either representation canonical. The lessons table also has no
generation-zero read API.

## Model-call and usage paths

| Producer | Current semantics | Persisted fields | Missing or ambiguous dimensions |
| --- | --- | --- | --- |
| `OpenAICompatibleProvider` | Maps provider `usage.prompt_tokens` and `usage.completion_tokens` | Two optional nonnegative counts on `ModelResponse` | Cached input, reasoning, billable/nonbillable, audio/image, request ID, model revision, service tier, currency and cost are discarded. |
| `AnthropicProvider` | Maps `usage.input_tokens` to prompt and `usage.output_tokens` to completion | Same two optional normalized fields | Cache creation/read, server-tool use, request ID, model revision, billing dimensions and cost are discarded. |
| `ModelBackend` | Appends `model.call` for success, invalid output, or provider failure | Provider kind, base host, model, role/work item, selected parameters, request/response digests, the two token counts, retry indexes, duration, context manifest/truncation, outcome/error | No attempt ID, provider response ID, price/version, invoice reconciliation, orthogonal token axes, privacy classification, purpose/court identity, mission hierarchy beyond run ID, or host telemetry link. Transport retries inside a provider are not individually emitted by `execute`, which calls `complete_once`. |
| `AutonomyBudget` | Issues local allowances and consumes estimated compute after a turn | In-memory counters exposed to some evaluation paths | Estimate is request bytes/4 plus maximum output; it is not provider usage, a reservation service, or durable hierarchical lease. |
| `ExperimentRunner` | Uses approximate UTF-8 prompt bytes/4 as `token_cost` | Experiment observations/events | Not reconciled to `model.call`, provider usage, invoice, role purpose, or retries. |
| Sandbox/tool receipts | Records duration, bounded output metadata and outcomes | Tool receipt and some ledger events | No common usage-event envelope joining tools and models; process resource metrics are incomplete. |
| Host profiles | Declare possible host capabilities | Static unverified JSON | No host telemetry ingestion, session correlation, conformance run, cancellation receipt, or provider-normalized usage adapter. |

Provider token meanings are not interchangeable. The two generation-zero
fields are compatibility aliases only; Phase 2 must retain the native value
and its source path before deriving normalized dimensions.

## Event coverage gaps

The prose paths below are now complemented by the exact generated registry in
`evidence/phase1/generation_zero_surface_inventory.json`: 48 direct ledger
sinks, 53 producing sites, and 47 literal production event types. The
registry is bounded by its declared static sink rules and does not convert
these gaps into implemented capabilities.

The ledger receives important mission, work, result, model, prompt, experiment,
policy, sandbox, and verification events. Coverage is nevertheless incomplete:

- there is no required event envelope shared by every writer;
- events have no previous-event digest or payload digest in the SQLite table,
  despite a richer standalone event schema existing elsewhere;
- store commits and ledger appends are not one atomic transaction;
- scheduler leases/retries overwrite current job rows and have no append-only
  retry/lease history, preventing exact retry-storm reconstruction;
- provider attempts, host sessions, retrieval reads, memory writes, projection
  writes, privacy decisions, budget reservations, and invoice imports are not
  comprehensively represented;
- retry storms, repeated-context churn, stalled progress, and loop fingerprints
  are not first-class events; and
- timestamps are writer-generated and there is no ingestion/observation time
  distinction.

The registry also demonstrates that `HiveKernel.run_objective` can use a
different stream identity from `ModelBackend._record_call`, that
`war_room.event` and `experiment.decision` lack production emitters, and that
projection reads can create stores on a previously absent root.

## Privacy and threat obligations

1. Request and response bodies are excluded from `model.call`, but context
   manifests retain summaries. Summary text can still contain sensitive data.
   Other ledger events persist objectives, absolute repository/output paths,
   evidence payloads, actions, and lessons, so the wider ledger is not
   content-minimal.
2. `api_key_env` stores the credential variable name, not the secret, but error
   redaction depends on known secret values and adapter behavior.
3. Raw provider error bodies may be retained in exceptions and response
   digests; there is no uniform data classification or retention policy.
4. Obsidian projection would make records easy to browse and accidentally
   publish. Safe public, private, secret, and deletion/tombstone boundaries are
   required before projection.
5. High-cardinality identifiers belong in traces or governed records, not
   metric labels. Metrics must use bounded vocabularies.
6. A generated note must never be re-ingested as a new authoritative record.

## Required Phase 2 observability envelope

The additive usage event must retain:

- stable repository, mission, run, step, role, court-purpose, work-item,
  attempt, provider request, and trace/span identifiers;
- native provider/model/version/host semantics and raw usage dimensions;
- orthogonal normalized token dimensions with explicit derivation version;
- request, response, prompt-layer, context-manifest, and memory-selection
  digests without secret bodies by default;
- budget reservation, actual consumption, outcome, retry, latency, tool,
  quarantine, and rollback linkage;
- cost amount, currency, price-card version, invoice reference, and
  reconciliation status when available;
- sensitivity, retention, tenant/repository scope, consent/policy decision, and
  redaction receipts; and
- a transactional local outbox so crashes cannot create an unrecorded effect.

Normalized totals must be derivable, never accepted as an unconstrained second
source of truth. Reconciliation is per axis; cached, reasoning, billable, and
total dimensions must not be summed as though they were disjoint.

## Fair-learning boundary

Champion and challenger comparisons require the same sealed task, evidence
access, memory packet, budget policy, provider/model policy, tool surface, stop
conditions, and measurement version. Either side may fail absolute gates.
Relative improvement cannot excuse a privacy, trust, leakage, authority,
rollback, or minimum-customer-value failure. An inconclusive result cannot
promote.

## Canonical target mapping

Generation Zero paths remain unchanged. ADR-019 maps durable memory and
projection work to `hive-memory/v1` and
`hive-obsidian-projection/v1`. ADR-020 maps attempt, usage, cost, budget,
loop, and evaluation work to `hive-usage-event/v1`. The full field and
authority contracts are in `PHASE1_CANONICAL_CONTRACTS.md`.

The missing transactional outbox, repository identity, privacy policy,
provider conformance, replay, deletion, federation, concurrency, and recovery
behaviors are Phase 2/3 implementation gates rather than unresolved Phase 1
architecture choices.
