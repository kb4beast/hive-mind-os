# ADR-071: Portable DAG runtime and external one-run activation

Status: proposed `adapt`; candidate implementation and independent court pending

Date: 2026-09-02

## Context

The Generic Hive Mind Product V3 overlay defines a complete 20-node, eight-role product
program, but its frozen Standard-V2 execution mode is intentionally
`manual-parent-v1`: it contains no runnable command and the installed controller accepts
only `.autopilot/plan.json`. Pull request 154 later squash-merged the V3 tree and severed
the historical commits used by its regression suite. ADR-070 repairs that evidence
boundary without pretending that V3 became executable.

A local V4 draft introduced an inert manifest and an external-signature concept. It did
not contain a plan, accepted placeholder artifact identities, compared principals only by
labels, and let a nonce ledger key replay protection by `(nonce, payload)`. Those gaps make
the draft useful source evidence but not an activation candidate.

## Decision

Implement a subject-neutral portable runtime as a versioned product surface rather than
modifying the frozen `.autopilot` compiler. The runtime uses closed, strict JSON contracts
for subject identity, resources, adapters, capabilities, authority, budgets, recovery,
integration, evidence, and nodes. A canonical packaged compiler validates the exact plan,
builds deterministic conflict-free rounds, and leaves all host effects behind injected
adapters and explicit authority envelopes. Repository and non-repository subjects use the
same interfaces.

Complete the previously planned product modules for plan lineage and generation, runtime
contracts, adapters and indexing, durable waves and integration, task and test reuse,
context and token accounting, the generic executor, public CLI, recovery, fixtures, and
qualification. Preserve eight lifecycle dispositions even when deterministic checks avoid
model calls. Read-only commands accept explicit absolute inputs and do not create state.

Replace the V4 activation draft with an ordered external gate:

1. Strictly parse and hash the exact manifest, plan, R4 qualification receipt,
   independent-review record, and frozen-host record. The predecessor receipt must
   bind the manifest commit/tree, its distinct `ADAPT` court, every denied readiness
   flag, and the carried SBOM dissent.
2. Bind request, repository, predecessor, candidate parent, candidate commit/tree/content,
   plan, manifest, evidence, five structured principals, lease, and nonce.
3. Verify the independent reviewer and frozen-host signatures through host-injected
   verifiers.
4. Verify the distinct external issuer signature over the complete bundle.
5. Atomically consume a globally unique nonce, keyed by nonce alone, in host-owned storage,
   and return a signed reservation receipt that a fresh process can verify without relying
   on process-local object identity. Restoration revalidates every bundle and reservation
   binding and never consumes the nonce a second time.
6. Return a typed one-run capability whose candidate, client, host, and proof bindings are
   propagated into every downstream lease and effect. The repository never mints a
   signature or nonce and a checked-in manifest remains `execution_authorized: false`.

The activation never authorizes a protected merge. Delivery of a review branch or draft
pull request is separately bounded; merging `main`, obtaining credentials, accepting
terms, spending, deployment, and production mutation remain external authority gates.

### C77 amendment: semantic SPDX evidence is load-bearing

The attested `3743ad1` build artifact proved that provenance authentication and shallow
JSON shape checks are not semantic SPDX conformance: its `creationInfo.created` carried
nanoseconds and its package omitted mandatory `copyrightText`. The original artifact,
attestation, and independent validator transcript remain preserved as C77 adverse
evidence. This amendment adopts two narrowly bounded corrections:

1. The V4 source intake/archive contract binds 13 sources, including the exact SPDX 2.2.2
   clauses and the exact Apache-2.0 `spdx-tools` 0.8.5 release. The activation validator
   therefore rejects any manifest that names a stale source count.
2. The build-evidence job accepts only `SPDX-2.2` generated JSON, validates a real UTC
   calendar timestamp, removes fractional seconds only, and adds `copyrightText:
   NOASSERTION` only when that required field is missing. It rejects every other version,
   malformed timestamp, empty package set, non-object package, or empty/non-string
   existing copyright field. It then runs the hash-locked Linux CPython 3.12
   `spdx-tools==0.8.5` validator before upload or attestation.

This is a deterministic adapter for two observed Syft v0.42.2 gaps, not a general SPDX
converter or a claim that `NOASSERTION` establishes copyright facts. It preserves all
other fields, refuses unknown version semantics, and must be re-courted if the generator,
SPDX major/minor version, validator, or normalization surface changes.

### C78 amendment: preserve both merge-result and direct-candidate checks

GitHub's default `pull_request` checkout is a synthetic merge commit with two parents.
That is correct input for ordinary Linux merge-result tests, but cannot be passed to the
PowerShell qualification collector, whose evidence contract proves one direct-child
candidate and must not infer a parent. The Windows test lane therefore checks out the
immutable event head (`github.event.pull_request.head.sha`, falling back to `github.sha`
for push); it retains full history. Linux unit tests keep GitHub's default merge-result
checkout. This split is a CI-input binding only: it does not relax the collector or turn a
merge commit into a candidate.

## Invariants and threats

- Duplicate JSON keys, non-finite numbers, excessive size/depth, unknown fields, stale
  leases, artifact substitutions, candidate/parent collapse, identity/key collisions,
  non-adopting review, dirty or writable frozen-host claims, bad signatures, and nonce
  replay fail before execution.
- Graph level is not authority. Workers are admitted only by exact dependencies, resource
  conflicts, adapter availability, live authority, budgets, and an authenticated run.
- Capability effect class is a closed versioned vocabulary. Every external class requires
  explicit external-effect authority at both executor and public host admission; unknown
  classes fail closed.
- Candidate, test, transaction, and effect identities are content-addressed. Recovery
  adopts an exact prior outcome or stops on ambiguity instead of intentionally retrying
  an externally observable effect; global duplicate-effect exclusion still depends on
  the trusted shared nonce/run journal and adapter-side idempotency.
- Durable host state binds the complete observed host identity, trust-evidence digest,
  canonical plan adapter inventory, compiler receipt, required-capability set, lease,
  candidate, execution client, and activation proof.
  Recovery performs a fresh host observation for each resume attempt and rejects any
  identity, trust, capability, receipt-time, or content drift.
- A Python thread timeout detects an ambiguous result; it does not terminate an arbitrary
  external effect. Activation therefore requires a trusted host adapter that independently
  enforces `lease.issued_at <= now < lease.expires_at` and the signed runtime deadline
  atomically. Prepare also atomically enforces the activation issuance lower bound and
  the minimum of activation, lease, and runtime upper bounds. Results observed at or
  after either exclusive deadline are rejected and reconciled rather than represented
  as contained or successful. Fresh returns must not be future-dated, while exact
  authenticated historical or adopted in-interval evidence survives wall-clock rollback.
- Host operations are uniquely claimed by semantic identity rather than caller alias:
  activation for create, lease and node for message, the exact successful host result for
  checkpoint, and lease for cancellation. Alias rebinding and a second input for one
  lease/node fail closed. Separate handles on the same SQLite store poll an in-flight
  canonical intent for a bounded settle interval instead of treating absent process-local
  ownership as a crash; an orphaned intent times out to recovery and is never retried.
  Checkpoint identity is derived from the complete lease and receipt.
- Lease completion and cancellation are atomically ordered in the host journal. The
  cancellation claim retains its exact reason; a pending claim blocks completion, a
  committed cancellation wins terminal recovery, and a completion seal prevents later
  cancellation before the adapter boundary.
- Multi-table journal verification and its pure result selection use one SQLite read
  snapshot. Writers release that verification snapshot before `BEGIN IMMEDIATE`, so a
  concurrent valid commit cannot create a mixed-state false-corruption result or require
  a read-to-write transaction upgrade. This does not claim atomicity across separate
  journal databases.
- After expiry, a read-only observer may close only executor-local gaps backed by exact
  durable host proof: lease-ready, deterministic checkpoint, recovered node success,
  run completion, or committed cancellation. It cannot prepare, execute, or cancel.
- This candidate checks positive wall/tool admission capacity and uses the compiler's
  declared concurrency limit. Host receipts do not yet carry complete wall, tool, model,
  token, and cost counters, so runtime all-dimension budget reconciliation is explicitly
  not claimed and remains a blocking follow-up for any enforced-budget readiness claim.
- Content-addressing does not grant integration authority. Prepare and commit require a
  separately verified authorization bound to the exact candidate, base, transaction,
  adapter, lease, and integration operation.
- Repository code cannot establish that an external principal is honest, that a host is
  physically read-only, or that a host ledger is truly atomic. Those properties remain
  independently attested and operationally enforced; injected verifiers do not turn local
  strings into trust.
- A signature over a substitute but internally self-consistent candidate is valid only if
  every independent binding names that same candidate. Review and host attestations are
  therefore separately signed and included by raw digest in the issuer bundle.
- A green step name is not artifact evidence. The build job must explicitly produce a
  non-empty SPDX JSON document with at least one discovered package, upload the exact
  wheel and SBOM paths, and submit those same paths for provenance attestation. Missing
  files or an empty package inventory stop the job.
- An authenticated SBOM is not necessarily a conformant SBOM. Before upload or
  attestation, the build job invokes the C77-bounded normalizer and an exact-hash
  `spdx-tools==0.8.5` Linux CPython 3.12 environment. A standard-version mismatch,
  malformed timestamp, missing package inventory, malformed copyright field, resolver
  hash mismatch, or validator finding stops the job. The tool lock is platform-specific
  by design; an unsupported runner architecture fails closed rather than silently using
  a different dependency artifact.
- Evidence collection accepts only a fully qualified output outside the repository,
  rejects reparse-point ancestry visible during preflight, and proves that the candidate
  object has exactly one parent. Its Windows CI lane must receive the immutable direct
  event head, while Linux merge-result tests retain GitHub's default PR merge checkout.
  Generated PowerShell binds an absolute,
  caller-authenticated client executable and rehashes it immediately before every
  invocation. Neither path performs handle-relative execution or holds a directory/file
  handle across validation and use, so immutable host custody and ACLs remain required to
  exclude a concurrent substitution race.
- Unavailable local commits and mutable provider observations are preserved as exact,
  digest-bound archive bytes. A source is not represented as preserved merely because a
  URI or expected digest was recorded.

## Migration

Land the squash-proof V3 baseline correction and the portable runtime together on an
ordinary `codex/` review branch based on canonical `main`. Preserve the abandoned local
V4 commits as provenance; do not cherry-pick their weak schema unchanged. Publish an exact
V3 correction candidate as a separate immutable ref for review, then bind V4 to that
commit/tree and its qualification receipt. Existing `.autopilot` state remains untouched
and quiescent.

Keep predecessor regression coverage point-in-time by reconstructing R4 from a
raw-digest integrity-checked, prerequisite-bound delta bundle. Verify the prerequisite, sole advertised
ref, commit, and tree before extracting exact payload bytes into the disposable test
repository. Do not populate an R4 fixture from shared V4 worktree files or a mutable remote
ref.

After independent review and full supported-host CI, publish one draft pull request. A
trusted host may then create fresh signed review/frozen-host records and an issuer bundle
for a maximum 15-minute lease, consume the nonce, and run exactly the bound candidate.
No expired or partially populated template is executable.

## Rollback

Revert the portable-runtime candidate commit and close its unmerged pull request. Preserve
all source intake, losing designs, court records, benchmark lanes, failed signatures,
consumed nonces, and adverse CI. Never reuse a consumed nonce or rewrite a V3/V4 manifest
to make a later candidate appear identical. Existing Autopilot state and protected
branches are outside this rollback and must not be reset.

## Acceptance

- Focused tests cover every module and public command, plus cross-language and
  non-repository fixtures, deterministic recovery, conflict and drift failures, replay,
  duplicate effects, exact integration authorization, static budget admission and
  concurrency limits, fresh resume observations, late-result rejection, and a controlled
  token comparator. Complete runtime budget metering remains unclaimed as described above.
- The predecessor regression harness authenticates and exercises the exact qualified R4
  object and fails when its bundle prerequisite is absent or any bound identity changes.
- Full repository CI passes on Linux Python 3.11/3.12/3.14 and Windows 3.12/3.14.
- Linux PR tests exercise GitHub's merge result; Windows collector tests exercise the
  immutable direct candidate, and static CI contract tests reject a topology collapse.
- The collector rejects relative, in-repository, observed reparse-point, and
  non-sole-parent evidence targets; the PowerShell preparation path rejects client-byte
  substitution visible at its pre-invocation checks. Concurrent replacement resistance
  remains a frozen-host custody obligation.
- Pull-request CI executes dependency/license review and the downloaded build artifact
  and verified attestation both contain the generated SBOM; the R4 false-green SBOM
  observation remains retained as adverse evidence.
- C77 regression coverage proves missing-only `NOASSERTION`, strict whole-second UTC
  normalization, idempotent output, unsupported/malformed-input denial, source/archive
  digest binding, and the exact-hash validator lock. A fresh remote artifact and
  attestation must be independently checked by the Curator and Judge; the retained C77
  artifact can never be reclassified as semantically valid.
- A separately identified Curator reproduces exact artifacts and a distinct Judge issues
  a courtroom disposition after the final candidate is frozen.
- The final handoff names exact commits, trees, artifact digests, CI receipts, the unmerged
  pull request, and any remaining external signature/nonce/merge gates without claiming
  A5, production readiness, release readiness, or superiority.
