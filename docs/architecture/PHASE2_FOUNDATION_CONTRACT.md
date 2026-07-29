# Phase 2 foundation contract

## Selected and candidate paths

Generation Zero remains the selected champion. Its 131 root exports, 33 package
exports, 13 CLI parser contracts, role order, prompts, `ModelResponse`, `model.call`,
legacy stores, 20 legacy schemas, 48 hive-core resources, and 68-resource receipt
remain available.

`hive_mind_os.foundation` is an internal candidate package. Importing it has no side
effect. It is not re-exported by either frozen facade and no CLI selects it.

## Canonical authorities

| Concept | Canonical Phase 2 authority | Projection |
| --- | --- | --- |
| Agent candidate | strict foundation schema plus deterministic generated JSON | inert agent JSON |
| Memory and provenance | append-only foundation record stream | local outbox, later Phase 3 open brain |
| Opportunity | encounter, opportunity key, and append-only relation | query result only |
| Usage/accounting | started and terminal usage records with native observation | metrics, trace, invoice reconciliation |
| Delivery | immutable outbox message and delivery receipts | destination-specific consumer |
| Authority | existing policy decision plus Phase 2 intersection | allow/deny receipt; never generated authority |

## Repository identity

Callers register explicit opaque tenant, project-lineage, repository-instance, and
controller identities. Remote/path evidence is represented by digests. Mutable
paths, branches, titles, and remote URLs are not canonical identity. Every query
requires tenant and repository, including pending-outbox reads and delivery receipts.

## Record and transaction invariants

Each record has a stable content-bound ID, schema/type, scoped stream and monotonic
version, prior digest, semantic digest, actor, observed/recorded times, correlation,
causation, sensitivity, retention, status, and idempotency key. Replaying the same key
and full semantic command returns the original; changing payload, actor, destination,
scope, schema/type, stream, status, sensitivity, retention, correlation, or causation
fails closed. Explicit observed time and authority/lease/release provenance are part
of that command.

Each record and outbox message share a single transaction. Domain and outbox tables
reject update and delete. Delivery attempts and acknowledgements append. WAL reopen
preserves pending work. Delivery receipts are bound to the immutable destination, and
an acknowledgement requires a prior successful attempt and a nonempty sink receipt.

The store will create tables only in an empty, unversioned database. A versioned
foundation database must carry the expected ownership marker, exact columns, and
schema-object digest. It never adopts or migrates a Generation Zero database.
Interrupted first initialization rolls back to a reusable empty database.

## Opportunity invariants

An `IdeaEncounter` is written before classification. Normalized problem and proposal
digests are distinct. Exact and structured uniqueness is scoped to tenant/repository
and enforced inside an immediate transaction. A duplicate adds a relation and keeps
both encounters. Semantic candidates require explicit later classification as
duplicate, reinforcement, refinement, variant, contradiction, complement, appeal, or
not-duplicate. Candidate endpoints must be typed opportunity records; direct or
unstaged classification fails closed. Integrity verification binds opportunity keys
to the scoped typed record and its normalization/exact/structured digests.

## Usage invariants

The opt-in provider wrapper writes `attempt-started` before calling the provider and
one terminal record before returning or re-raising. A restart closes abandoned starts
as interrupted with unknown accounting. No raw prompt, response, header, credential,
tool body, hidden reasoning, or raw error is persisted.

Provider-native numeric paths are preserved independently of normalized axes.
Malformed, missing, or out-of-range fields are unknown; all accepted numeric values
are bounded at `10**15`. Cache and reasoning values are subsets; there is no
cross-axis total. Invoice reconciliation reports matched, missing, duplicate,
residual, conflicting, partial, or unavailable observations.
Per-axis reconciliation compares only like dimensions from separately identified
estimate, provider, host, and invoice observations. It never emits a cross-axis
aggregate. Billable status uses only `billable`, `non-billable`, `unavailable`, or
`unknown`, and conflicting sources remain conflicting.

The optional recorder accepts bounded caller attribution for mission, run, step,
role, work item, idea, court case, experiment, span, prompt layers, context, memory
selection, model revision, host, and access audit. The same attribution is copied
from the durable start into normal terminal and restart-recovery receipts; omitted
attribution remains explicit null rather than being inferred. Recorder admission
revalidates the object even if a caller bypassed its constructor, and the strict
schema independently enforces identifier lengths, digest syntax, and count maxima.

## Privacy and observability

Sensitivity defaults to private. Safe-public requires an independent policy decision.
Every store write requires a process-local tamper-evident `AuthorityDecision` issued
by the authority intersection function. The store verifies the decision seal before
examining allowed/action/scope fields, so direct construction, dataclass replacement,
or post-construction mutation fails closed. The seal authenticates only this
in-process decision boundary; durable decision/lease/public-release references remain
the provenance record and no external identity or authorization protocol is claimed.
Metrics accept only schema version, record type, provider kind, outcome,
reconciliation status, and sensitivity labels. IDs stay in governed records or trace
attributes. OpenTelemetry-shaped local envelopes are dependency-free and outbound
export remains disabled. Metric names and values are bounded. Trace attributes reject
body, request, response, credential, authorization, password, and reserved
provider/outcome keys; trace names, IDs, attribute count, keys, and values are bounded.
The exported immutable trace record enforces the same checks at construction, and
the OpenTelemetry projection revalidates them so callers cannot bypass privacy or
bounds by skipping the convenience projector.

## Phase boundary

Phase 2 does not add an Obsidian projection, activate v2 agents, change role behavior,
enforce loop/quarantine/leases, claim live provider semantics, add host projections,
or promote a challenger.
