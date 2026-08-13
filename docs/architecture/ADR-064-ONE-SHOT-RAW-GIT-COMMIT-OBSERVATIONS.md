# ADR-064: One-shot raw Git commit observations

- Status: proposed challenger architecture; implementation and promotion remain blocked
- Disposition: `ADAPT`
- Program: `git-commit-observation-v1`
- Court: `CASE-GIT-COMMIT-OBSERVATION-OPENING`
- Scope: controller-private immutable commit observations for diagnostics and explicit pure receipt validation

## Context

The knowledge-projection `BASELINE-000` node remains blocked because the unchanged doctor
command does not complete its frozen test vector before its internal 180-second timeout.
The retained Git-observation baseline diagnostic recorded one Python 3.14 trial at
186.231892 seconds; doctor failed and the trial did not reproduce the complete vector.
This is adverse end-to-end evidence, not proof that Git subprocess overhead caused the
timeout.

The prior fixture challenger was independently rejected. Its focused correctness results do
not authorize its reuse, amendment, or promotion. The rejection court authorized a separate
appeal only for a new, invocation-scoped immutable Git-read challenger. The opening court
then adapted that proposal into this sealed DAG and no broader cache proposal.

Inspection of the current controllers exposes two hazards that this design must not inherit:

1. `snapshot_cache` can ambiently replace `_git`, object-existence, ancestry, tree, and
   parent helpers with results retained across calls inside its body. A ref move, fetch,
   replace-ref change, object-store change, or other mutable transition can make such a
   generic or negative result stale.
2. `_StatusCommitGraph` derives records from delimiter-formatted `git log` text. Commit
   messages are arbitrary bytes and can contain those delimiters, so a message can forge,
   split, or overwrite a record. That representation is not an evidence boundary.

These are threat inputs, not a claim that the proposed replacement will meet the doctor
gate. The challenger must independently establish correctness, safety, and performance.

## Decision

Introduce one private, narrowly named reader in `.autopilot/bin/controller.py` that creates
an invocation-local `GitCommitObservation`. The reader accepts a finite sequence of full
commit object IDs, validates and deduplicates them while preserving first-request order,
then reads the exact commit objects through one replacement-disabled binary
`git cat-file --batch` process.

The observation is an immutable, non-serializable context-managed value. It contains only
bound repository identity and verified commit facts. Its only authorized consumers are:

- exercised controller diagnostics that need tree or direct-parent facts for an explicit
  finite commit set; and
- `durable_controller.ControlPlane.validate_receipt`, through an explicit invocation-local
  parameter or local variable, for pure receipt validation.

It is not a cache API, authority object, repository snapshot, ancestry graph, or general Git
facade. No method that mutates local or remote state accepts it. Exiting its context, whether
normally or by exception, invalidates it and releases its facts. A later operation creates a
new observation from new repository checks.

## Repository and request binding

Before starting the batch, the reader resolves and binds all of the following from the exact
repository argument:

- the canonical repository worktree root;
- the canonical absolute Git directory;
- the canonical common Git directory, kept distinct from the per-worktree Git directory;
- the repository object format; and
- the permitted primary object store under that common directory.

Ordinary worktrees and linked worktrees may share a common directory, but their repository
roots and Git directories remain distinct identities. An observation's
`assert_repository(...)` check must resolve the supplied repository again and fail closed if
any bound identity or object format differs. Identity strings alone never grant authority.

Each requested ID must be lowercase hexadecimal and exactly the full width declared by the
repository object format: 40 characters for SHA-1 or 64 for SHA-256. Symbolic names, refs,
abbreviations, uppercase forms, whitespace, invalid hex, mixed-format IDs, and unsupported
object formats are rejected before Git is invoked. Deduplication preserves the first
occurrence's order. The result records the finite deduplicated tuple and cannot later add a
commit or resolve a ref.

## Rejected repository states

The first challenger supports only a complete local primary object store. It fails closed
before reading commit bodies if any of these mechanisms is configured or present:

- shallow repository metadata;
- grafts;
- promisor remotes or partial-clone configuration;
- replace refs or replacement configuration;
- alternate object databases, including environment, configuration, or
  `objects/info/alternates` sources; or
- an object-store layout or object format outside the explicitly supported set.

Setting `GIT_NO_REPLACE_OBJECTS=1` for the batch is mandatory but not sufficient: a
repository containing replace refs is still rejected. Likewise, a currently reachable
object does not make a promisor or alternate store acceptable. Supporting any rejected
state requires a separate architecture decision and adversarial evidence; this ADR does not
silently fall back to optimistic behavior or network fetching.

## One-shot binary protocol

The reader starts exactly one `git cat-file --batch` child in the bound repository. It uses
binary standard input and output, sets replacements disabled, sends only the validated full
IDs as ASCII lines in their preserved order, closes the input through the bounded
communication operation, and captures stdout and stderr without text decoding.

For every requested ID, the parser requires exactly this response in the same position:

```text
<requested-full-oid> commit <decimal-size>\n
<exactly decimal-size body bytes>\n
```

The header ID must exactly equal the requested ID, the type must be exactly `commit`, and the
size must be canonical non-negative ASCII decimal suitable for a bounded read. The parser
consumes exactly that many body bytes and exactly one protocol newline. It accepts no
missing-object line, abbreviation, duplicate response, extra response, reordering, unknown
type, malformed header, non-decimal size, truncated header or body, missing terminator, or
trailing output. Any non-zero process result or unexpected stderr is fatal.

For each response the parser independently computes:

```text
HASH("commit " + ASCII(decimal body length) + NUL + exact body bytes)
```

using the repository's declared object format. The recomputed full ID must equal both the
request and response header. The body is parsed as bytes, not delimiter-separated text.
Before the first blank line it must contain exactly one leading `tree <full-oid>` header,
followed immediately by zero or more `parent <full-oid>` headers. A later or duplicate tree
or parent header, a parent before tree, or an object-format-width mismatch is fatal. Commit
message bytes after the header/body separator are opaque and cannot create records.

No partial mapping is returned. A failure in any requested object discards the entire
observation.

## Immutable value and lifecycle

`GitCommitObservation` is a frozen, finite data class whose public facts are tuples and
read-only mappings. Its exposed facts are limited to:

- bound repository root, Git directory, common directory, object format, and permitted
  object store;
- the ordered tuple of requested full commit IDs; and
- the verified tree and direct-parent tuple for each of those IDs.

It contains no refs, origin, target, reconcile state, authority, claims, releases, leases,
snapshots, receipts, intents, CAS tokens, force-with-lease values, verdicts, mutable indexes,
worktree content, negative lookups, or conclusions about ancestry. Pickle and equivalent
serialization are rejected. It is never written to disk, a receipt, process-global state,
controller instance state, a shared daemon, or another invocation.

Nested and concurrent calls create distinct observations and distinct child processes. The
batch child is fully communicated with and reaped; no live child is exposed to consumers.
On timeout, cancellation, parser failure, consumer exception, or normal exit, cleanup kills
the child if needed, waits for it, clears temporary buffers and lookup references, and
invalidates the observation. Tree and parent access after context exit raises
`GitCommitObservationError` rather than returning retained facts.

The invalidation mechanism may use a private lifecycle guard separate from the frozen fact
payload, but must not make the verified facts mutable or serializable.

## Controller integration boundary

The first implementation is intentionally additive and private. It does not ambiently
replace `_git`, `git_object_exists`, `is_ancestor`, `_commit_tree`, `_commit_parents`, or any
other controller method. Callers enumerate the exact full IDs, enter the context, and pass
the observation explicitly to a pure reader. Missing coverage or repository mismatch is an
error, not a fallback to cached or guessed data.

For the exercised diagnostic and receipt-validation paths, the unsafe generic Git-result
cache and delimiter graph are bypassed or removed:

- `_StatusCommitGraph` and delimiter-formatted `git log` output cannot supply commit facts;
- `snapshot_cache` cannot wrap the observation factory or substitute generic `_git`, object
  existence, ancestry, tree, or parent answers used by those paths;
- object non-existence is never retained across a later fetch or object-store transition;
- refs and `HEAD` are resolved freshly outside the observation; and
- ancestry and diff questions remain direct, fresh Git operations and are not batched by
  this challenger.

The existing generic cache/graph may not be renamed, copied, or moved behind the new type.
The Builder must produce no new generic, ref, `HEAD`, negative, ancestry, cross-instance,
persistent, or shared cache.

## Durable pure consumption

`durable_controller.ControlPlane.validate_receipt` may accept a keyword-only
`commit_observation` parameter. The caller, not the control-plane instance, owns its context.
Validation first verifies repository identity and exact commit coverage, then may read only
verified tree and direct-parent facts from it. The parameter is invocation-local and is not
assigned to `self`, captured by a closure that outlives the call, installed as an ambient
helper, returned, serialized, or added to a durable receipt.

Receipt schema checks, plan fingerprints, paths, roles, authority declarations, and all
other mutable or policy-bearing facts remain independent of the observation. Ancestry and
integration checks remain fresh because this challenger does not prove ancestry. A caller
without a valid explicit observation uses the existing fresh validation path; it must not
reuse a prior success or negative result.

## Effect boundary

An observation and any result derived from it are diagnostic or pure-validation evidence
only. Before deciding or attempting any claim, completion, retirement, repair, fetch, push,
`update-ref`, CAS, compensation, release, reconcile action, remote-claim publication, receipt
publication, or other side effect, the caller must:

1. leave and invalidate the observation context;
2. freshly and uncached read the repository identity, origin, target, reconcile state, refs,
   required objects, authority, releases, leases, claims, snapshots, receipts, intents, and
   current CAS/force-with-lease values relevant to that effect;
3. retain the existing local CAS or remote `--force-with-lease` guard; and
4. freshly verify the resulting state after the effect.

No observation parameter is added to `claim`, `complete`, `release`, `reconcile`,
`publish_remote_claim`, or any effect method. `sealed_recovery.py` and
`release_barrier.py` are forbidden consumers because their recovery and release decisions
must remain based on fresh state. Capability to observe commit bodies grants no network,
credential, policy, mutation, or publication authority.

## Threat model and mandatory response

| Threat | Required response |
|---|---|
| Delimiters in a commit message forge or overwrite graph records | Parse length-framed raw commit bodies; treat message bytes as opaque |
| Ref, `HEAD`, or target changes while facts are retained | Observe only full content-addressed IDs; keep refs out; invalidate before effects |
| A missing object arrives after fetch | Fail the whole call and retain no negative result; a later call starts fresh |
| Replace refs change object meaning | Reject repositories containing replacements and set replacements disabled |
| Shallow, graft, promisor, or alternate storage hides provenance | Reject the repository state before starting the batch |
| A linked worktree is confused with its main worktree | Bind root, absolute Git directory, and common directory separately |
| SHA-1 and SHA-256 objects are confused | Bind declared format, enforce full width, and recompute the declared hash |
| Malformed, reordered, partial, wrong-type, or extra batch output is accepted | Exact count/order/framing/hash validation; discard the entire observation |
| A timeout or cancellation leaks a Git child | Kill if live, wait/reap, clear buffers, invalidate, and propagate failure |
| A pure validation result becomes effect authority | End context, perform fresh mutable/authority reads, preserve CAS, verify after effect |
| The observation becomes a semantic cache through instance retention | Explicit local parameter only; frozen, non-serializable, non-retained, invalid after exit |
| The optimization expands to diff or ancestry | Keep both out of scope; require a new court and ADR |

All ambiguous cases fail closed. No parser recovery, partial acceptance, cached verdict, or
network repair is authorized.

## Migration and activation

Migration follows the sealed DAG and is reversible by node:

1. `GCO-TEST-020` defines the independent red adversarial contract without changing the
   frozen `.autopilot/tests` tree.
2. This ADR fixes the architecture before implementation.
3. `GCO-BUILD-040` may add only the private observation and controller diagnostic use in
   `.autopilot/bin/controller.py`.
4. `GCO-INTEGRATE-050` may add only explicit pure consumption in
   `.autopilot/bin/durable_controller.py`.
5. `GCO-SAFETY-060` independently verifies scope, repository-state rejection, parser
   framing, lifecycle cleanup, cache/graph bypass, and effect freshness.
6. `GCO-SMOKE-070` runs exactly one fresh doctor trial on each pinned runtime. Either a
   failure or a runtime at or above 180 seconds stops the expensive matrix.
7. Only after both smokes pass may `GCO-QUALIFY-080` run the full independent matrix and
   correctness gates.
8. Only a distinct `GCO-JUDGE-090` `ADOPT` verdict with zero unresolved material findings
   can authorize the narrow candidate or a later knowledge `BASELINE-000` retry.

There is no persistent schema migration and no compatibility promise for the private API.
Activation does not alter `.autopilot/plan.json`, the doctor command or timeout, test
discovery, the frozen vector, sealed predecessor DAGs, production `src`, release barriers,
or recovery policy.

## Verification and outcome metrics

Architecture conformance is necessary but not promotion evidence. The candidate must pass:

- all adversarial tests in `tests.test_doctor_git_fact_batching`, including delimiter
  injection, repository mutation, rejected Git configurations, object formats, worktrees,
  exact protocol framing, cleanup, concurrency, explicit durable use, and effect boundaries;
- the unchanged full `.autopilot` discovery command with exactly 381 executions: 380 passes,
  zero failures, zero errors, and the same one conditional skip;
- the complete test-ID digest
  `sha256:7c0cf4ae7a2efca60af613b1702c97133a28b043bad09b231fe3a6c97d23eef4`;
- full repository CI, `python -m unittest discover -s tests -v`;
- independent scope, seal, safety, lifecycle, and rollback checks; and
- the sealed two-runtime performance policy: one passing smoke below 180 seconds on each
  runtime, then at least six fresh cold-first alternating exact-doctor trials per runtime,
  every trial passing below 180 seconds and nearest-rank p95 at most 135 seconds.

Process count, raw batch microbenchmarks, focused-test speed, a single successful trial, or a
change relative to one baseline sample cannot establish causality or superiority. The
baseline diagnostic is a retained comparator only. Promotion requires the full matrix and a
court verdict; a performance pass still cannot automatically authorize publication,
superiority language, or `BASELINE-000` retry.

## Rejected alternatives

- Retaining or expanding `snapshot_cache`: rejected because invocation locality does not
  make mutable, negative, authority, or effect-adjacent facts immutable.
- Repairing `_StatusCommitGraph` delimiters: rejected for this challenger; raw
  length-framed commit objects are the evidence source.
- Generic `_git` memoization or ref/`HEAD` caching: rejected because command text is not a
  sufficient freshness or repository identity key.
- Persistent object caches or a shared Git daemon: rejected because they cross invocation
  and object-store boundaries.
- Batching diffs or ancestry: rejected because their semantics and completeness burden are
  not covered by this court.
- Fetch-on-miss or promisor support: rejected because it introduces network effects and
  turns a pure observation into mutation authority.
- Automatic promotion after timing improvement: rejected by the courtroom burden.

## Rollback

Each GCO node remains one retained unsquashed commit. Revert only the failing node's commit,
in reverse dependency order when necessary; do not rebase, squash, amend, or rewrite a
sibling. Rolling back integration removes explicit durable consumption before rolling back
the private controller implementation. Because there is no persistent schema or cache,
rollback requires no data migration.

Retain the opening court, baseline diagnostic, safety receipts, benchmark receipts, dissent,
and final verdict append-only, marking later evidence superseded where appropriate. Never
delete the rejected fixture evidence or relabel a failed GCO result. A rollback does not
authorize the old generic cache/graph for effect-adjacent facts and does not unblock
knowledge `BASELINE-000`.

## Consequences and unresolved burdens

The design provides a narrow, byte-verifiable source of immutable tree and direct-parent
facts while preserving fresh authority and effect decisions. It deliberately rejects Git
configurations that could change object interpretation and accepts the cost of repeated
fresh observations rather than weakening provenance.

Implementation is not present at this ADR node, so the independent contract remains red
only for the missing private API. No safety qualification, runtime smoke, two-runtime
qualification, full behavior-vector reproduction, full-suite result, promotion verdict,
superiority claim, or `BASELINE-000` retry authority exists yet. The retained diagnostic
also does not prove that this design can reduce end-to-end runtime enough to satisfy the
135-second p95 burden.
