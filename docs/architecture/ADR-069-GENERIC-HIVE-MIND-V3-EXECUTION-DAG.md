# ADR-069: Sealed external Generic Hive Mind V3 execution DAG

- Status: proposed `adapt`; distinct Curator and Judge disposition pending
- Date: 2026-08-23
- Scope: repeated persisted-subject Autopilot invocation and its bounded product-completion DAG
- Immutable authoring-base parent: commit `42b4aeef17f816430a7d8a435102635afea8761a`, tree `b896e16755a1d6864989757732fdc5ca9d2b5eed`
- Immutable Clerk intake: `docs/execution/dags/generic-hive-mind-product-v3/source-intake.json`, 58,463 bytes, SHA-256 `dd884c72e2e587b4111dc9b6343296a52b3e87cc909ed2fa5d13141176a2782c`

## Context

The desired user interaction is a repeatable command such as
`hive-mind autopilot run "foobar"`. When the exact subject already has a
persisted request and the current branch is its persisted target, a repeat must
not fail merely because normal target creation would reject the existing branch.
It also must not trust a mutable in-repository plan, execute repository Python in
the portable command, or weaken the external controller boundary.

The earlier plan is retained as provenance only. Reusing or rewriting
`.autopilot/plan.json` would permit ambiguous generation identity and unsafe
fallback. A checked-in signature or digest alone would also be insufficient:
the active Windows session can read the old authority key, the stored capability
is expired and stale, and the observed host worktree contained ignored bytecode.
The legacy continuation launcher returned a quiescent success but withheld
release publication after reconciliation and GitHub snapshot drift; it is not V3
authority or dispatch.

## Decision

Adopt a separately sealed, external `manual-parent-v1` V3 overlay with 20 nodes,
28 raw edges, 17 levels, six intentionally redundant direct edges, and exact
typed durability. All nodes are serial in this authored topology, yielding
exactly 20 one-node rounds. The plan contains no runnable command.

The same-request fast path is allowed only before new-target protection and only
for an exact persisted subject, request, repository, objective, launch, target,
HEAD, tree, compiler, standard, generation, and resume identity. It consumes a
complete externally authenticated plan bundle. It does not infer authority from
repository contents, request repetition, branch existence, or mission scope.

### Checked-in generation manifest

`manifest.json` is inert and uses the following sealed shape:

```text
schema_version, kind, plan_id
authorship { architect, judge=UNASSIGNED, court_status, execution_authority=NONE }
request_binding { request_id, objective_digest, repository_id, task_key,
                  launch_digest, target_branch }
snapshot_lineage { request_observation, qualified_prerequisite,
                   combined_envelope_b, authoring_base_parent } -> { commit, tree }
source_bindings.repository[] -> { path, bytes, sha256, git_blob }
source_bindings.overlay[] -> { path, bytes, sha256 }
committed_payload_contract {
  mode=exact-single-overlay-commit-v1,
  authoring_base_parent,
  expected_changed_paths[11], payload_bindings[10],
  manifest_authentication=caller-supplied-raw-sha256,
  court_envelope_b_bindings
}
plan_binding { expected_plan_digest, expected_raw_bytes_digest, external_path,
               historical_autopilot_plan_policy, historical_v1_expected_plan_digest }
topology { node_count, raw_edge_count, level_count, round_count,
           redundant_direct_edge_count }
execution_contract { mode=manual-parent-v1,
                     executable_dispatch_command_available=false,
                     every_round_command=null,
                     legacy_fallback=PROHIBITED }
execution_authorized=false
```

The manifest binds the six V1 source blobs and expected V1 digest, V1 and V2
standards, the frozen V2 compiler, Clerk intake, qualification evidence, snapshot
lineage, the immutable authoring-base parent, the exact 11-path committed
payload, the external plan bytes, and the independent verifier. The manifest
cannot authenticate itself: its raw digest must be supplied by the caller from
the independent court/Envelope B. That court also binds the committed payload
HEAD and tree. The expected V3 plan digest lives outside `plan.json`.

### Host-external activation bundle

The checked-in manifest never becomes an activation bundle. A host-external
bundle must be signed by a principal distinct from the worker, or be enforced by
an outside-repository sandbox/token that denies worker access to the signing key
and control plane. It contains, under one authenticated envelope:

```text
complete_plan_bytes
manifest_digest, expected_plan_digest
reviewer_identity, reviewer_evidence_digest
actor_identity, issuer_identity
request_id, repository_id, objective_digest, target_branch
authoring_base_parent_commit, authoring_base_parent_tree
committed_payload_head, committed_payload_tree
caller_authenticated_manifest_digest
compiler_digest, standard_digest
one_run_nonce, lease_deadline
```

It additionally binds the exact interpreter and a pristine, read-only,
cache-free Git extraction at commit
`ca43709591313c1c166a2e655b8982ccff16daf3`. The complete 16-path manifest in
`node-contracts.json` includes each byte count, raw SHA-256, and Git blob. Its
bundle digest is
`sha256:76b89c6e83c9dc2c7ae4d41bbba0b2f6b1fdd8861e0a7c7aeda01602d1c89255`.
Predecessor and new trust receipts plus a one-run compare-and-swap ledger are
required. These are blockers, not facts asserted satisfied by this ADR.

### Verification order

The verifier fails closed in this order:

1. Require a caller-supplied canonical SHA-256 and compare it to raw
   `manifest.json` bytes before parsing; then apply duplicate-key,
   non-finite-number, size, and depth rejection.
2. Validate fixed request, repository, objective, target, snapshot, expected-plan,
   topology, execution, exact payload, and distinct-review boundaries.
3. In default committed mode require the current HEAD to be one non-merge child
   of the immutable authoring-base parent, require `git diff --name-only` to equal
   the exact 11-path allowlist, bind the committed payload HEAD/tree, and reject
   dirty, staged, or unapproved untracked/ignored state. The only declared
   exception is `.hive-mind/autopilot-request.json`.
4. Resolve safe non-symlink paths and verify every manifest-declared repository
   and overlay byte count and raw SHA-256. Independently verify Git objects at the
   frozen authoring commit.
5. Only after all source bytes pass, parse inert contracts, traceability,
   ownership/effects, and Clerk intake. Never import or execute the materializer
   or target repository Python.
6. Verify all 89 inherited mappings; V3 corners;
   exact host manifest; topology, typed durability, redundant-edge rationales,
   ownership, effects, and evidence boundaries.
7. Independently reconstruct every expanded node and its Standard-V2 seal, then
   reconstruct and compare the entire plan and plan seal.
8. Prove manual-parent/no-command/no-fallback/no-authority/A5 boundaries and
   byte-compare `.autopilot/plan.json` before and after verification.

This order rejects materializer substitution before authored code can execute.
An explicit `--authoring-check` exists only for deterministic precommit
development at the immutable base parent; it reports non-qualification and is
forbidden as execution or release evidence. Default verification refuses that
precommit state and refuses a missing caller manifest digest.

### Returned execution contract and resume identity

The compiled result is `manual-parent-v1`, `executable=false`, with exactly 20
rounds, one node per round, and `command=null` in every round. A trusted parent
may invoke durable task APIs directly only after external activation succeeds.

The resume ID is the digest of a `manual-parent-resume-v1` object binding plan and
generation IDs, request, objective, repository, task key, launch, target branch,
immutable authoring-base parent commit and tree. Runtime resume also requires
the committed payload HEAD/tree, caller-authenticated manifest digest, the
manifest's expected-plan digest, one-run nonce and deadline, frozen-host bundle
digest, interpreter digest, parent principal, and round-ledger digest. Repeat
resume is idempotent only for the exact identity. A generation collision or
concurrent loser is rejected.

### Ownership and evidence lineages

The overlay assigns every one of 85 writable candidate paths to exactly one node
and forbids it for every other node. Seven sensitive surfaces have named sole
writers: adapter registry, DAG executor, host runtime/integration transaction,
task reuse, and token ledger, with shared schemas/interfaces owned only by
RUNTIME-CONTRACTS.

All implementation, documentation, and tests finish before
QUALIFICATION-PREP-625. That node freezes candidate Envelope A. CANDIDATE-CI-627
runs only the exact frozen doctor plus repository CI. GENERIC-QUALIFICATION-630
is evidence-only. HANDOFF-700 may create only an authorized draft pull request
and may not merge. Receipts after freeze are written to a separate external
Envelope B evidence worktree/branch whose lineage references, but never mutates
or reidentifies, the candidate.

PowerShell preparation is inert and bounded. It may prepare inspectable scripts,
but it may not impersonate a human, expand authority, obtain credentials, spend,
accept legal terms, mutate production, bypass a protected branch, or substitute
for missing evidence.

## Threat model and required tests

The overlay rejects request/objective/repository/target/HEAD/tree/compiler/
standard staleness; source or path swap; duplicate keys; NaN/infinity; oversized
or deeply nested JSON; detached signature or digest substitution; node or plan
resealing; topology, durability, ownership, or effect corruption; missing V1
mapping; source-quarantine mutation; generation collision; expired/replayed
lease; repeat-resume mismatch; and concurrent activation losers. Invalid V3 has
no legacy fallback. Tests also prove deterministic materialization, source
verification before any authored code, self-review rejection, exact frozen-host
and evidence lineage, and no `.autopilot` mutation.

The focused harness constructs a temporary Git checkout, commits exactly the 11
payload paths as one child of the immutable base, and requires default committed
verification to pass. Missing caller binding, extra commit, wrong parent, path
addition, dirty tracked state, staged state, and other untracked or ignored state
must fail.

## Migration and rollback

Migration is additive:

1. Preserve V1 and `.autopilot/plan.json` byte-for-byte as historical evidence.
2. Land the exact 11-path inert V3 payload as one child of the immutable
   authoring-base parent without wiring it into the public runtime; have the
   independent court bind its commit, tree, and manifest digest.
3. Obtain independent court disposition and a fresh external trust deployment.
4. Implement the same-request discovery and activation path behind a reversible
   feature gate.
5. Qualify a frozen candidate using the external Envelope B evidence lineage.
6. Enable the easy command only for exact authenticated V3 matches.

Rollback disables the V3 feature gate and retires outstanding V3 leases and
nonces. It preserves append-only receipts and the sealed overlay for diagnosis.
Rollback must not execute V1 as a fallback; the user receives a typed blocker and
can inspect or reissue a fresh V3 generation through the external trust path.

## Consequences and nonclaims

The design makes the eventual common command small while keeping generation,
review, activation, execution, evidence, and handoff identities explicit. It
adds host-external custody and evidence-worktree operational work, and it refuses
to turn an existing branch or repeated prompt into authority.

SRC-024 remains `QUARANTINE` with content unread. SRC-025 remains unresolved.
The Clerk intake's nested-status contradiction is preserved only as a supplemental
correction/nonclaim in `traceability.json`; the intake is not mutated. The final
vision claim remains below the full Hardened Vision Contract until that conflict
is resolved. A5 is not ready. No full-autonomy, production, release, or
superiority claim is made.
