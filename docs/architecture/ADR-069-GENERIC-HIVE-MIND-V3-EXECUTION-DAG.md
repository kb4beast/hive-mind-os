# ADR-069: Sealed external Generic Hive Mind V3 execution DAG

- Status: proposed `adapt`; distinct Curator and Judge disposition pending
- Date: 2026-08-23
- Scope: repeated persisted-subject Autopilot invocation and its bounded product-completion DAG
- Immutable plan authoring base: commit `42b4aeef17f816430a7d8a435102635afea8761a`, tree `b896e16755a1d6864989757732fdc5ca9d2b5eed`
- Immutable historical Payload A: commit `4e2b81b932e5145f24c4b52ceeee664bff91df2e`, tree `8c42aeaf4ed480dd3ccc353356b7fa9f3ed49157`
- Immutable Git-boundary correction parent: commit `f06e52c43a1e2d1d53523378c0d6f5564fb984bf`, tree `8730203c89835c4d1d9dac4be9b2086dacd2d869`
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

Payload A is preserved append-only at `4e2b81b932e5145f24c4b52ceeee664bff91df2e`.
Its inert plan and independent committed verifier passed, but two focused tests
incorrectly ran the precommit-only authoring mode against the committed payload
HEAD. The exact commit therefore ran 12 of 14 focused tests, while the same bytes
overlaid on the intended base passed 14 of 14. This ADR adapts the lineage with a
versioned correction child; it does not erase or relabel that failed observation.

That first correction is preserved at
`f06e52c43a1e2d1d53523378c0d6f5564fb984bf` as the sole direct child of Payload A.
Its verifier inherited `os.environ` and invoked `git` through `PATH`. An inherited
`GIT_WORK_TREE` could therefore redirect every Git query to a different clean
checkout while the verifier read payload bytes from the candidate checkout. The
successor records the observed status as
`QUALIFICATION_REMANDED_GIT_ENVIRONMENT_FAIL_OPEN` and proposes `ADAPT_REMAND`
because the claimed Git/worktree boundary could fail open; a distinct court must
disposition that proposal. Neither the commit nor the report is deleted or
retrospectively rewritten. The external report bytes remain predecessor evidence,
referenced by raw SHA-256
`731beb68c2fed2c1a3d8666530c1f193b2e21144428448816216b4f9b0bba810`.

This ADR proposes a second, append-only correction as exactly one non-merge direct
child of `f06e52c`. Its final commit, tree, manifest digest, payload aggregate, and
qualification report do not yet exist and are intentionally not asserted here.

## Decision

Propose `adapt` for a second append-only Git-boundary correction while retaining
the separately sealed, external `manual-parent-v1` V3 overlay with 20 nodes, 28 raw
edges, 17 levels, six intentionally redundant direct edges, and exact typed
durability. All nodes are serial in this authored topology, yielding exactly 20
one-node rounds. The plan contains no runnable command. A distinct Curator and Judge
must disposition the successor's exact committed bytes; this authoring decision is
not that disposition.

The successor changes exactly ADR-069, this V3 README, `manifest.json`,
`verify_plan.py`, and the focused test. It preserves the other six members of the
ordered 11-path payload inventory byte-for-byte from `f06e52c`. The immutable plan
authoring base remains `42b4aeef`; the Git correction parent and direct Git parent
are `f06e52c`. These two roles must not be collapsed.

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
                   combined_envelope_b, authoring_base_parent,
                   correction_parent } -> { commit, tree }
source_bindings.repository[] -> { path, bytes, sha256, git_blob }
source_bindings.overlay[] -> { path, bytes, sha256 }
committed_payload_contract {
  mode=exact-append-only-git-boundary-correction-v3,
  authoring_base_parent=plan-authoring-base,
  correction_parent=f06e52c,
  predecessor_payload=f06e52c { commit, tree, parent_commit, parent_tree,
                        manifest_raw_sha256, full_payload_aggregate,
                        qualification_report_sha256, observed_status,
                        author_proposed_disposition },
  historical_payload_a { commit, tree, parent_commit, parent_tree,
                         manifest_raw_sha256, full_payload_aggregate,
                         observed_status, author_proposed_disposition },
  expected_changed_paths[5], payload_inventory[11], payload_bindings[10],
  activation_anti_downgrade,
  git_execution_boundary {
    caller_absolute_native_executable_and_raw_sha256,
    reject_all_inherited_case_insensitive_GIT_prefix,
    minimal_child_environment, no_path_lookup,
    explicit_git_dir_and_work_tree, disabled_system_and_global_config,
    raw_HEAD_index_worktree_blob_equality,
    per_invocation_executable_revalidation,
    strong_read_only_runtime=REQUIRED_NOT_SATISFIED
  },
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
lineage, the immutable plan authoring base, historical Payload A, and the preserved
`f06e52c` correction parent. It also binds the exact five-path successor allowlist,
ten embedded non-manifest payload bindings, the ordered 11-path inventory, the
external plan bytes, and the independent verifier. The manifest cannot authenticate
itself: its raw digest must be supplied by the caller from the independent
court/Envelope B. Ten embedded bindings plus that externally authenticated manifest
make the complete 11-path binding.

The executable digest also cannot be selected by the checked-in manifest or derived
from the candidate's `PATH`. The caller supplies an absolute, already-canonical path
to a direct native Git executable and a lowercase `sha256:<64-hex>` digest of that
file. An independent court must bind that path and digest together with the v3
contract, correction parent, committed HEAD/tree, successor aggregate, predecessor
identity, remand/supersession verdict, predecessor qualification-report digest,
historical Payload A disposition, court verdict, and external minimum-version and
revocation-policy digest. The expected V3 plan digest lives outside `plan.json`.

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
correction_parent_commit, correction_parent_tree, committed_contract_mode
committed_payload_head, committed_payload_tree
caller_authenticated_manifest_digest, corrected_full_payload_aggregate_digest
caller_authenticated_git_executable_path_and_raw_sha256
predecessor_payload_identity, predecessor_supersession_verdict, court_verdict
predecessor_qualification_report_digest
external_minimum_version_and_revocation_policy_digest
compiler_digest, standard_digest
one_run_nonce, lease_deadline
```

It additionally binds the exact interpreter and a pristine, read-only,
cache-free host extraction at commit
`ca43709591313c1c166a2e655b8982ccff16daf3`. The complete 16-path manifest in
`node-contracts.json` includes each byte count, raw SHA-256, and Git blob. Its
bundle digest is
`sha256:76b89c6e83c9dc2c7ae4d41bbba0b2f6b1fdd8861e0a7c7aeda01602d1c89255`.
That 16-path host bundle does not bind the Git executable's DLLs/shared objects,
runtime loader, `libexec` helpers, trust store, or operating-system dependencies.
Execution therefore additionally requires an externally frozen, read-only Git
runtime bundle and platform controls that prevent replacement during use.
Predecessor and new trust receipts plus a one-run compare-and-swap ledger are
required. A signed external minimum-version and revocation policy must reject both
the `f06e52c` and Payload A manifests and every v1 fallback. These are blockers, not
facts asserted satisfied by this ADR.

### Verification order

The verifier fails closed in this order:

1. Before any Git invocation, enumerate the inherited environment and reject every
   variable whose name begins with `GIT_` under case-insensitive comparison. Do not
   log its value. Require `--git-executable` to be an absolute, already-canonical,
   regular, non-link native executable and compare its open-file raw SHA-256 with
   the caller-supplied `--expected-git-executable-sha256`.
2. Resolve the repository's real `.git`/linked-worktree metadata, common object
   directory, index, and worktree explicitly. Reject object alternates. Invoke only
   the absolute executable, with an argument list, `shell=False`, and the same
   absolute subprocess executable; never search the caller's `PATH`. Give the child
   a new minimal environment: deterministic locale, a `PATH` containing only the
   bound executable directory, controlled `GIT_*` safety settings, and only the
   operating-system variables needed to start a native process. Disable system and
   global Git config, replacement objects, lazy fetch, optional locks, prompts,
   the global attributes file, hooks, fsmonitor, untracked cache, external diff,
   and implicit repository discovery. Repository `.gitattributes` may still be
   parsed by Git, but cannot affect the verifier's direct raw-byte blob proof. Pass
   explicit `--git-dir` and `--work-tree` to every call.
3. Require a caller-supplied canonical SHA-256 and compare it to raw
   `manifest.json` bytes before parsing; then apply duplicate-key,
   non-finite-number, size, and depth rejection. Validate fixed request, repository,
   objective, target, snapshot, expected-plan, topology, execution, exact payload,
   authorship `execution_authority=NONE`, and distinct-review boundaries.
4. Independently verify the plan base, Payload A, and `f06e52c` commit objects,
   trees, and sole-parent lineage. In default committed mode require current HEAD
   to be one non-merge direct child of `f06e52c`, require the raw name-only tree diff
   to equal the exact five-path successor allowlist, bind the complete 11-path
   payload inventory and committed HEAD/tree, require regular-file modes, and prove
   that all six inherited blobs equal `f06e52c` while all five correction blobs
   differ.
5. Treat porcelain status as diagnostic only, not as the trust root. Parse the raw
   `HEAD` tree and stage-zero index inventories and require exact mode/blob/path
   equality. Read every tracked worktree file directly and compute its Git blob ID
   in the verifier, require every index visibility flag to be normal, and reject the
   union of untracked and ignored paths except
   `.hive-mind/autopilot-request.json`. Repeat the complete cleanliness proof before
   returning committed qualification. Qualification therefore requires a checkout
   with raw bytes equal to Git blobs; platform line-ending normalization such as
   `core.autocrlf` is not accepted as equivalent evidence.
6. Resolve safe non-link paths and verify every manifest-declared repository and
   overlay byte count and raw SHA-256. Independently verify Git objects at the frozen
   authoring commit. Only after all source bytes pass, parse inert contracts,
   traceability, ownership/effects, and Clerk intake. Never import or execute the
   materializer or target repository Python.
7. Verify all 89 inherited mappings, V3 corners, exact host manifest, topology,
   typed durability, redundant-edge rationales, ownership, effects, and evidence
   boundaries. Independently reconstruct every expanded node and its Standard-V2
   seal, then reconstruct and compare the entire plan and plan seal.
8. Prove manual-parent/no-command/no-fallback/no-authority/A5 boundaries,
   byte-compare `.autopilot/plan.json` before and after verification, and recheck the
   executable path/open-handle identity and full digest before and after every Git
   invocation and once more before success.

This order rejects materializer substitution before authored code can execute and
closes the reproduced ambient `GIT_WORK_TREE` redirection. The required CLI boundary
is:

```text
verify_plan.py --repo-root <repository> --overlay-dir <overlay>
  --expected-manifest-digest sha256:<64-hex>
  --git-executable <absolute-canonical-native-file>
  --expected-git-executable-sha256 sha256:<64-hex>
  [--authoring-check]
```

The executable path and its expected digest are independent caller inputs; the
verifier does not discover either through `PATH`. An explicit `--authoring-check`
exists only for deterministic successor development at the immutable `f06e52c`
correction parent. It reports `committed_payload_qualification=false` and is
forbidden as execution, activation, release, or merge evidence. Default committed
verification refuses that precommit state, a missing caller manifest digest, or a
missing caller Git binding.

### Returned execution contract and resume identity

The compiled result is `manual-parent-v1`, `executable=false`, with exactly 20
rounds, one node per round, and `command=null` in every round. A trusted parent
may invoke durable task APIs directly only after external activation succeeds.
Committed mode may report `committed_payload_qualification=true`; it always
reports `execution_qualification=false` and `execution.authorized=false`.

The resume ID is the digest of a `manual-parent-resume-v1` object binding plan and
generation IDs, request, objective, repository, task key, launch, target branch,
immutable authoring-base parent commit and tree. Runtime resume also requires
the committed payload HEAD/tree, caller-authenticated manifest digest, the
manifest's expected-plan digest, the caller-authenticated Git executable path and
raw digest, the frozen Git-runtime bundle identity, one-run nonce and deadline,
frozen-host bundle digest, interpreter digest, parent principal, and round-ledger
digest. Repeat resume is idempotent only for the exact identity. A generation
collision or concurrent loser is rejected.

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

The checked-in successor does not authorize even that bounded handoff. DAG
execution, activation, release, deployment, pull-request creation, protected-branch
change, and merge all remain deferred until their independent prerequisites and
authority are satisfied.

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
no predecessor or legacy fallback. The Git boundary additionally rejects ambient
repository redirection, executable substitution, `PATH` interception, configuration
and attribute injection, object alternates, replacement objects, hidden index state,
and a worktree other than the explicitly bound checkout.

The focused harness must construct an immutable temporary checkout at `f06e52c`,
overlay the current manifest-bound payload bytes, commit exactly the five correction
paths as one non-merge direct child, and require default committed verification to
pass. Authoring mode must use the same `f06e52c` fixture without committing those
five paths and must return non-qualification. The required adversarial matrix covers:

- inherited `GIT_WORK_TREE`, `GIT_DIR`, `GIT_INDEX_FILE`, object-directory,
  alternates, config-count/key/value, and mixed-case `gIt_*` variables;
- a hostile caller `PATH`, relative/non-canonical/link/wrapper executable paths,
  missing or malformed digests, wrong executable bytes, and executable identity or
  digest changes before, during, and after subprocess use;
- hostile system, global, XDG, and repository-local config, including worktree,
  fsmonitor, hooks, attributes, ignores, external diff, and object-alternate
  redirection, without executing an injected helper;
- exact `HEAD`/index/worktree divergence, non-stage-zero index entries, mode or
  blob changes, skip-worktree/assume-unchanged state, ignored-only contamination,
  dirty/staged files, and unapproved untracked files;
- Windows launch with only OS-derived `SystemRoot`/`WINDIR`, POSIX launch with no
  inherited user environment, bounded output/timeout behavior, and no shell or
  subprocess executable search; and
- missing caller bindings, extra commit, wrong parent, path addition, predecessor
  manifest or contract downgrade, remanded-report substitution, self-review, exact
  frozen-host/evidence lineage, and no `.autopilot` mutation.

Portable pre/post path, open-handle identity, and digest checks detect many
executable swaps but do not prove that the kernel executed bytes from the retained
handle. Tests must preserve this distinction rather than relabel detection as
strong executable immutability.

## Migration and rollback

Migration is additive:

1. Preserve V1 and `.autopilot/plan.json` byte-for-byte as historical evidence.
2. Preserve Payload A and its exact-commit 12/14 focused result as an observed
   failing predecessor with author-proposed `adapt`; do not rewrite or discard it.
3. Preserve `f06e52c`, its v2 manifest and aggregate, and its qualification-report
   bytes. Record the reproduced ambient-Git fail-open and remand the report's
   qualification conclusion; do not rewrite the commit or report and do not permit
   either predecessor to activate.
4. Land the successor's exact five changed paths as one non-merge direct child of
   `f06e52c`, without wiring it into the public runtime. Have a distinct court bind
   its then-known commit, tree, manifest digest, full 11-path payload aggregate,
   Git executable path/digest, predecessor report digest, and remand/supersession
   disposition. Do not predeclare those successor identities.
5. Obtain independent court disposition, deploy a frozen read-only Git runtime and
   fresh external trust policy, and revoke the predecessor manifest versions.
6. Implement the same-request discovery and activation path behind a reversible
   feature gate.
7. Qualify a frozen candidate using the external Envelope B evidence lineage.
8. Enable the easy command only for exact authenticated V3 matches.

Rollback disables the V3 feature gate and retires outstanding V3 leases and
nonces. It preserves append-only receipts and the sealed overlay for diagnosis.
Rollback must not reactivate `f06e52c` or Payload A or execute V1 as a fallback;
the user receives a typed blocker and can inspect or reissue a fresh V3 generation
through the external trust path.

## Consequences and nonclaims

The design makes the eventual common command small while keeping generation,
review, activation, execution, evidence, and handoff identities explicit. It
adds host-external custody and evidence-worktree operational work, and it refuses
to turn an existing branch or repeated prompt into authority.

The portable verifier's executable checks are a qualification boundary, not a
complete runtime attestation. On POSIX, a retained read handle plus path rechecks
does not make pathname execution equivalent to execute-by-file-descriptor. On
Windows, a retained ordinary file handle plus identity rechecks does not by itself
prove deny-write/deny-delete sharing, reparse-point safety, ACL custody, or immutable
volume semantics. On both platforms, a raw digest of the main Git executable omits
the dynamic loader, DLLs/shared objects, locale/runtime data, `libexec` helpers, and
other child programs. A read-only externally attested runtime bundle and appropriate
platform launch primitive remain execution prerequisites. Until those are supplied,
`committed_payload_qualification=true` can describe only the inert payload check;
execution, activation, release, deployment, and merge remain deferred.

SRC-024 remains `QUARANTINE` with content unread. SRC-025 remains unresolved.
The Clerk intake's nested-status contradiction is preserved only as a supplemental
correction/nonclaim in `traceability.json`; the intake is not mutated. The final
vision claim remains below the full Hardened Vision Contract until that conflict
is resolved. A5 is not ready. No full-autonomy, production, release, or
superiority claim is made.
