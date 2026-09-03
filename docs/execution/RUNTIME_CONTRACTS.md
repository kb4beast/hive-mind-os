# Subject-Neutral Runtime Contracts

`RUNTIME-CONTRACTS-150` owns the shared data and interface boundary used by
later runtime nodes. Implementations live elsewhere. These contracts are
immutable, closed, versioned, canonicalized with UTF-8 JSON, and intentionally
unable to perform effects.

The published schemas are `portable-plan.schema.json` and
`runtime-contracts.schema.json`.

## Portable plans

`PortablePlanBundle` binds one request and objective to a typed subject. A
repository subject carries repository, commit, tree, and target-branch identity.
A non-repository subject carries typed locator and version digests. In both
cases, `subject_id` is the canonical digest of the typed binding, preventing a
repository or cross-subject substitution.

Every bundle includes:

- a `StandardBinding` with version, source path, raw SHA-256, byte count, Git
  blob, package ID, and package digest;
- typed resources, capabilities, adapters, authorities, budgets, evidence,
  recovery, integration, and token policy;
- nodes with dependency, acceptance, rollback, role, lifecycle-stage, resource,
  capability, adapter, authority, budget, and evidence bindings.

Constructors reject cycles, duplicate identities, dangling references, unsafe
subject unions, unsupported versions, and unknown fields at the byte boundary.
Capabilities only describe requirements. They never enlarge an authority
envelope.

Subject and resource snapshots accept only canonical UTC RFC 3339 observation
timestamps. Their inert constructors do not consult an ambient clock; a caller
that has an explicit admission clock must reject future observations at that
boundary. Resource `mutable` and snapshot `binary` flags are exact booleans, so
integer or falsey substitutes cannot bypass versioning or alter canonical
identity.
Capability, provenance, and evidence collections are exact immutable tuples at
the Python boundary; mutable lists cannot be retained inside frozen identities.
Capability effects use the closed V1 vocabulary `none`, `local-reversible`, and
`external-reversible`. Unknown and near-miss values are invalid, and every
external class requires an authority envelope whose `external_effects` flag is
exactly true.

## Strict JSON boundary

`strict_json_object` accepts immutable bytes only and rejects duplicate keys,
non-finite numbers, a UTF-8 BOM, invalid UTF-8, non-object roots, excessive
bytes, and excessive nesting. Canonical encoding sorts object keys, uses no
insignificant whitespace, forbids non-finite values, and hashes the complete
bytes with SHA-256.

## Durability and ownership

`NodeRuntimeContract` uses the typed roles `none`, `provider`, and `consumer`.
`validate_runtime_contracts` takes the independently sealed expected assignment
map; it does not infer a weaker assignment. It verifies every dependency,
provider ancestry, exact node inventory, exact write-path count, unique path
ownership, and the exact shared-surface owner map. For the V3 contract this is
20 nodes, 85 writable paths, and seven shared surfaces.

## Decision memory

A `DecisionMemoryDraft` retains the question, snapshot, alternatives, evidence,
counterevidence, constraints, authority, budget, scoring model, scores,
uncertainty, owner, decision time, freshness, corrections, supersession, and
appeal state. A successful `DecisionMemoryEntry` adds the winner, every loser,
and a digest of the complete entry.

`select_decision` never guesses. It returns a typed `SelectionBlocker` for:

- missing or unreferenced evidence, scores, or constraint results;
- missing, expired, or ambiguous authority;
- a stale subject snapshot;
- an unresolved highest-score tie; or
- an unsafe highest-scoring alternative.

It does not select a lower-scoring alternative to conceal an unsafe winner.

## Waves and hosts

`WaveManifest` provides immutable, digest-chained states including
`CHECKPOINTED`, `CANDIDATE_SEALED`, `VERIFYING`, `INTEGRATION_READY`,
`RECOVERABLE`, `REPLAN_REQUIRED`, and terminal states. Candidate identity binds
commit, tree, and subject. The transition table is closed; a skipped or backward
transition fails.

`HostAdapter` is a protocol with four explicit methods:

1. `observe` performs a read-only subject observation.
2. `prepare` receives the sealed one-run capability and its exact signed proof,
   authenticates those externally supplied bindings, and returns a bounded
   `HostLease`.
3. `execute` accepts exact input bytes and an existing lease.
4. `cancel` terminates that lease without replacing its authority.

Host identity, executable and adapter digests, trust evidence, activation and
proof digests, manifest/repository/request/target identity, candidate
parent/commit/tree/content identity, execution-client digest, activation
issuance, protected-merge denial, nonce, lease deadline, required capabilities,
allowed nodes, input, output, all activation principals, signed proof bytes, and
receipt evidence are explicit. The host identity's adapter digest is the
canonical digest of the plan's complete adapter inventory (ID, interface,
version, and configuration digest), not a caller-supplied availability claim.
Observations are admission-bound rather than
cache-trusted; resume uses a fresh observation and checks the complete original
identity, trust, cleanliness, and capabilities. Every receipt is bounded by the
exclusive interval `lease.issued_at <= observed_at < min(lease.expires_at,
runtime deadline)`. A fresh adapter return must additionally be no later than
the current clock; authenticated historical and independently verified adopted
evidence does not repeat that wall-clock check, so clock rollback cannot erase
an already durable in-interval fact. Cached create results undergo that
same fresh validation, cancellation cannot cross the adapter boundary after
lease expiry, and checkpoints accept only successful message receipts retained
by the append-only host journal (including externally authenticated adoption)
and matched to the full lease document, node, and input digest.
Every message, cancellation, and checkpoint also authenticates its exact lease
against the successful create/adoption record and the activation claim binding
the proof, nonce, subject, create identity, and observed host.

Host creation accepts exact signed canonical plan bytes and derives its subject,
node inventory, authority digest, and required capabilities rather than trusting
caller-supplied scalar scope. It also requires the exact bound standard bytes,
re-runs canonical compiler/governance qualification, and applies the same
authority-expiry, allowed/denied action, effect-class, adapter-membership, and
static wall/tool budget admission used by `DagExecutor` before host observation.
The repository-scoped V2 activation must match the plan's request, repository,
base commit/tree, and target branch; it cannot authorize a non-repository plan.
The generation ID is provenance only and grants no authority. Public journal
calls cannot append host outcomes or create activation
claims; those writes require the trusted runtime path. The corresponding
execution journal permits inert initialization for read-only status fixtures,
but only the executor path can record host-backed progress or terminal state.
Create is uniquely claimed per activation, message per exact lease and node,
checkpoint per exact lease/node/input, and cancellation per exact lease. Caller
idempotency aliases are durably mapped to that canonical semantic claim: exact
sequential or concurrent aliases converge, while a second input, checkpoint, or
cancellation reason is denied before an adapter effect. Adoption aliases are
bound through the same append-only mapping and cannot be rebound; an exact
adoption retry must also carry the originally authenticated evidence digest,
which is retained as a typed append-only adoption claim. A legacy or
tampered store with conflicting successes fails verification instead of using a
first match. Only the atomic intent owner crosses the adapter boundary.
Convergence applies to separate journal handles sharing the same SQLite store,
not only threads using one Python object. A handle that observes an exact
in-flight canonical intent polls durable state for the caller's bounded settle
timeout without inferring owner death from process-local memory. A truly
orphaned intent reaches that timeout and returns `HostRecoveryRequired`; it is
never taken over or re-executed.
The cancellation claim retains the exact reason as typed durable data. Once
every leased node has an authenticated successful message and canonical
checkpoint, completion acquires a lease-level terminal claim in the same host
journal transaction that checks cancellation. Completion prevents a later
cancel before the adapter call; an earlier committed cancel supplies its exact
reason to the executor, while an ambiguous cancel claim blocks completion until
adoption. Thus neither a crash nor a caller-key alias can overwrite
cancellation with completion.

The sole checkpoint digest is derived from the complete canonical lease digest
and complete successful receipt. `HostRuntime` computes it independently and
rejects a caller-supplied substitute before a checkpoint intent, preventing a
wrong first writer from poisoning recovery. Checkpoint creation is journal-only
and may close an already durable message after expiry without invoking the
adapter.

`HostRuntime` additionally requires the host capability
`host-enforced-deadline-v1`. Live message, cancellation, and resume reject clock
rollback before lease issuance, use exclusive upper bounds, and recompute the
effective lease/runtime deadline immediately before the adapter call. Its
prepare path likewise rechecks the activation issuance lower bound and all
exclusive upper bounds immediately before reservation; the adapter must enforce
that same complete activation interval atomically. Its
in-process wait detects timeout but does not
contain the adapter thread, so effect containment after a deadline is explicitly
owned by the external adapter, which must atomically enforce both lease bounds.
The append-only host journal binds one activation
proof/nonce to one create identity and observed host. A separate journal store
does not share that exclusion: global replay prevention remains an obligation of
the external nonce/run ledger and adapter idempotency.
The process-local journal writer guards do not defend against hostile code in
the same interpreter, and hash chains do not defend against an attacker with
write access capable of replacing the journal store and recomputing it. Durable
resume therefore assumes trusted, exclusive storage custody.
Compound journal verification reads its event, alias, semantic, adoption,
activation, cancellation, completion, and preparation tables through one
SQLite read transaction. A valid commit from another connection therefore
cannot be combined with older event rows and misreported as corruption. Pure
compound reads retain that snapshot through result selection; write paths close
their verification snapshot before acquiring `BEGIN IMMEDIATE`, avoiding a
read-to-write transaction upgrade. This is consistency within one journal
database, not a global transaction across independent stores.
Expired leases cannot authorize new effects. A separate reconciliation-only
resume performs a fresh read-only host observation so a historical receipt
observed within its original lease can still be adopted and checkpointed after
expiry; it never retries that effect or permits message/cancel/create. It can
also restore a committed create missing only the executor's `host.lease-ready`
event, create the deterministic journal-only checkpoint for a committed message,
record a dedicated recovered-node event while a sibling remains blocked, close
a run whose node proofs were complete before `run.completed`, and record an
already committed cancellation. Missing or conflicting host proof remains
blocked.
There is no default ambient-host implementation.

## Maturity boundary

These contracts do not resolve the active-gate versus reference-only vision
conflict. A5 remains not-ready, and these interfaces do not support claims of
full autonomy, hardened-vision compliance, production readiness, release
readiness, deployment readiness, protected-merge readiness, or superiority.

The focused checks are:

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
python -B -m unittest tests.test_portable_plan tests.test_runtime_contracts -v
```
