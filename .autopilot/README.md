# Hive Mind OS Implementation Autopilot

This directory is the deterministic **implementation control plane** for building the
Verifiable Hive Cortex architecture. It is not the Hive Mind OS product runtime.

## Canonical objective

Build one self-operating Hive Mind OS runtime that:

- uses all eight specialist roles as meaningful, provider-backed participants;
- solves routine reversible repository work end to end without avoidable human answers;
- consults applicable roles before any human escalation;
- treats suspected cheating as a typed, evidence-bound court question;
- keeps deterministic control, authority, effects, verification, and promotion outside
  probabilistic model discretion;
- learns only through immutable challengers and independent evaluation;
- recovers after interruption without a human restating context.

## Source of truth

The controller reconstructs execution state from target-branch ancestry, **durable
validated completion evidence**, PR/CI snapshots, remote branches, bounded claims, and
append-only reconciliation records. A branch name, PR title, plan document, edited
status file, static DAG level, or dependency-ready classification never proves completion
or authorizes execution.

`BOOT-000` is the one historical bootstrap that predates durable receipt commits. Its
exact PR, actual branch, candidate commit/tree, squash-integrated commit/tree, tests,
changed paths, authority, and one-time historical installation scope are sealed in
`.autopilot/bootstrap-completion.json` and `.autopilot/control-plane.json`. The
controller verifies the integrated history and exact tree/diff; it does not fabricate
the planned bootstrap branch or treat the PR title as a receipt.

Merged PR #120 also assigned one exact dispatcher-release-barrier amendment to
`RECON-010`. The generated RECON plan entry retained a narrower write scope, so that
contradiction is represented separately in `.autopilot/authority-amendments.json` and
validated fail-closed. The sealed plan fingerprint and historical BOOT-000 attestation
are not rewritten. The amendment expands effective RECON authority only to the exact
listed control-plane/documentation/test paths.

## Commands

All execution commands must use one authenticated coordinate set. Populate these once
from the exact initialized execution; never rely on the parser's `default` namespace or
borrow another worktree's roots:

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
STATE_DIR="<absolute repository coordination root>"
HOST_RUNTIME_DIR="<absolute canonical per-user host runtime>"
EXECUTION_NAMESPACE="<exact execution namespace>"
HOST_ID="<canonical authenticated host id>"
PYTHON="<absolute interpreter from the sealed execution identity>"
AUTOPILOT=("$PYTHON" "$REPO_ROOT/.autopilot/bin/autopilot.py" --repo-root "$REPO_ROOT" \
  --state-dir "$STATE_DIR" --host-runtime-dir "$HOST_RUNTIME_DIR" \
  --execution-namespace "$EXECUTION_NAMESPACE")
SNAPSHOT=("$PYTHON" "$REPO_ROOT/.autopilot/bin/github_snapshot.py" --repo-root "$REPO_ROOT" \
  --state-dir "$STATE_DIR" --host-runtime-dir "$HOST_RUNTIME_DIR" \
  --execution-namespace "$EXECUTION_NAMESPACE")

"${AUTOPILOT[@]}" doctor
"${AUTOPILOT[@]}" status
"${AUTOPILOT[@]}" ready
"${AUTOPILOT[@]}" dispatch --host-id "$HOST_ID" \
  --actor DISPATCHER_ID [--node NODE_ID ...]
"${SNAPSHOT[@]}" --reconcile --actor SNAPSHOT_ACTOR
"${AUTOPILOT[@]}" run-round \
  --actor INTEGRATOR_ID --release-id RELEASE_ID
"${AUTOPILOT[@]}" snapshot-observation-begin --actor SNAPSHOT_ACTOR
"${AUTOPILOT[@]}" install-github-snapshot SNAPSHOT_FILE --observation-id OBSERVATION_ID
"${AUTOPILOT[@]}" render-prompt --host-id "$HOST_ID" NODE_ID
"${AUTOPILOT[@]}" infer-intent "USER MESSAGE"
"${AUTOPILOT[@]}" orchestrate --host-id "$HOST_ID" \
  --request "USER MESSAGE" [--apply] --json
"${AUTOPILOT[@]}" simple-prompt
"${AUTOPILOT[@]}" runtime-authority-migrate --mode dry-run --actor ACTOR
"${AUTOPILOT[@]}" runtime-authority-migrate --mode apply --actor ACTOR
"${AUTOPILOT[@]}" runtime-authority-migrate --mode verify --actor ACTOR
"${AUTOPILOT[@]}" runtime-authority-migrate --mode rollback-before-ready \
  --actor ACTOR --reason "abort and preserve pre-READY migration evidence"
"${AUTOPILOT[@]}" host-runtime-upgrade --actor ACTOR \
  --reason "install frozen host-kernel writer" \
  --expected-host-kernel-generation CURRENT_HOST_KERNEL_GENERATION
"${AUTOPILOT[@]}" host-runtime-recover-torn-tail \
  --ledger-kind repository-registry --actor ACTOR \
  --reason "recover an authenticated power-loss tail"
"${AUTOPILOT[@]}" execution-kernel-upgrade \
  --execution-id EXECUTION_ID \
  --expected-identity-record-id CURRENT_EXECUTION_IDENTITY_RECORD_ID \
  --actor ACTOR --reason "install frozen execution kernel"
"${AUTOPILOT[@]}" prepare-launch INSTRUCTION_ID --host HOST --host-id "$HOST_ID" \
  --repository REPOSITORY \
  --node-id NODE_ID --lifecycle LIFECYCLE --branch BRANCH \
  --resource-key RESOURCE_KEY --target-sha TARGET_SHA \
  --plan-fingerprint PLAN_FINGERPRINT --target-branch TARGET_BRANCH \
  --authority-class WRITE_AUTHORIZED
"${AUTOPILOT[@]}" bind-launch INSTRUCTION_ID \
  --host HOST --task-id TASK_ID --host-id "$HOST_ID" [--cursor CURSOR] \
  --capability CAPABILITY --resource-key RESOURCE_KEY --authority-epoch EPOCH
"${AUTOPILOT[@]}" check-launch-authority INSTRUCTION_ID \
  --resource-key RESOURCE_KEY --authority-epoch EPOCH
"${AUTOPILOT[@]}" fence-launch INSTRUCTION_ID \
  --actor ACTOR --reason "explicit audited revocation"
"${AUTOPILOT[@]}" claim NODE_ID --owner PROVIDER:SESSION --launch-instruction-id INSTRUCTION_ID \
  --resource-key RESOURCE_KEY --authority-epoch EPOCH --publish-remote
"${AUTOPILOT[@]}" heartbeat NODE_ID --owner PROVIDER:SESSION --claim-id CLAIM_ID \
  --launch-instruction-id INSTRUCTION_ID --resource-key RESOURCE_KEY \
  --authority-epoch EPOCH
"${AUTOPILOT[@]}" complete NODE_ID --owner PROVIDER:SESSION --claim-id CLAIM_ID \
  --launch-instruction-id INSTRUCTION_ID --resource-key RESOURCE_KEY \
  --authority-epoch EPOCH --receipt PATH
```

`orchestrate` is the normal host entrypoint. It reads live controller truth, infers
build/start/continue/check/finish intent, resumes unfinished node work before widening
the wave, and emits digest-bound durable-task instructions. `--apply` may publish the
existing safe dispatcher release for start/continue/finish intent; it never grants merge,
deployment, credential, spending, or protected-ref authority. `CHECK` uses non-mutating
observation.

The mandatory host-neutral behavior is versioned in
`.autopilot/orchestration-policy.json`. Codex maps primary work to `create_thread`,
`wait_threads`, and `send_message_to_thread`. Nested subagents cannot replace primary
node tasks. External task operations are performed by the active host adapter. The CLI
records `PREPARED -> CREATED -> BOUND -> HOST_EVENT_OBSERVED -> RELEASED` events and
consumes existing bindings;
emitting JSON alone is not task creation.

Hosted commands must use the exact absolute shared state directory and
instruction/resource/epoch envelope injected by the dispatcher. The uppercase values in
the command synopsis are placeholders only; a worker may not derive or substitute its
own authority values.

`status` distinguishes static **eligibility** from current execution **release**.
`ready` returns only nodes whose latest valid dispatcher release assigns `START NOW`.
A worker claim fails closed if there is no current explicit release for that exact node.
`dispatch` returns the exact `release_id` for a repository-shared admission generation.
The public `run-round` command must present that ID. Under the shared dispatcher lock it
revalidates the release and preflights the exact receipt head for every released node
before triage or Git effects. A partial wave returns `PENDING` without healing,
reconciliation, merge, push, or validation. Run the canonical host-aware `heal` command
and `"${SNAPSHOT[@]}" --reconcile --actor SNAPSHOT_ACTOR` as separate fenced operations,
obtain a fresh dispatch, and retry with the new `release_id`. A whole wave is integrated
and validated as one
fenced transaction; validation cannot be skipped on the public path.

Publication validation is accepted only from the independently authenticated validation
broker; a worker or integrator cannot substitute a direct test process or caller-produced
receipt. On the current Windows host, independently attested network isolation is not
available, so the broker fails closed before running candidate tests and publication
remains blocked. `run-round` does not weaken or bypass that boundary.

`--publish-remote` creates a unique empty claim commit on the node's fixed remote branch.
That claim retains the exact node branch, target SHA, owner, lease, and plan fingerprint.
Git ref creation is the cross-session mutex: a competing worker loses the push race and
must stop. Local claim files add lease/heartbeat state but are not the cross-session or
durable completion source.

## Dispatcher protocol

A dispatcher session does not implement product work. Until it completes the steps below,
all not-yet-released workers are `WAIT`.

For level-by-level execution of the current DAG, follow
`docs/execution/runbooks/README.md`: it fixes the dispatch rounds, the explicit
`--node` waves, the serial integration order, and bounded-wait supervision.
`"${SNAPSHOT[@]}" --reconcile --actor <id>` performs
steps 2, 4, and 6 below deterministically in one command. Before its first `git fetch` or
`gh` read, the helper reserves a monotonic repository-shared observation ID. Installation
must present that exact reservation, so a slower observation that began before a newer
one is fenced instead of overwriting newer scheduling evidence.

1. Read this file, `workflow-policy.json`, `control-plane.json`,
   `authority-amendments.json`, and `plan.json`.
2. Fetch the configured singleton release target branch and record its exact commit and tree.
3. Inspect open/merged/closed PRs, CI, remote node branches, claims, durable receipts, and
   plan-impacting changes.
4. Install a current snapshot in the authenticated execution directory through
   `install-github-snapshot --observation-id ...` using the exact reservation created
   before the external reads.
5. Run `doctor`, `status`, and `ready` as applicable.
6. Reconcile current target state before release. Any graph/scope inconsistency must use
   append-only reconciliation/replan authority; never silently broaden a node.
7. Compute the smallest dependency-eligible, conflict-free candidate wave. Eligibility
   alone still means `WAIT`; admission is the minimum of the authenticated provider
   ceiling, repository policy, and demonstrably remaining per-user host capacity across
   every repository's primary, sidecar, and validation reservations. A
   `parallel_safe: false` node must be released alone.
8. Run `"${AUTOPILOT[@]}" dispatch --host-id "$HOST_ID" --actor ...
   [--node ...]`. This is the explicit release boundary.
9. Require every candidate node to have exactly one verdict: `START NOW`, `WAIT`, or
   `STOP`.
10. A released multi-node wave must say `START TOGETHER NOW`. The dispatcher must also
    emit a plain action sentence such as `Open these 2 sessions now: RECON-010, BASE-020`
    or `Do not open any worker sessions yet`.
11. Render/copy worker prompts only for current `START NOW` nodes.

Static DAG/level membership never authorizes a worker. Every standard linked worktree
consults the same locked release and monotonic admission generation. A target-branch
advance, plan change, or authorized snapshot/reconciliation mutation invalidates the
generation; active claims prevent replacement or invalidation until they settle. Run the
dispatcher again rather than reusing an old prompt. Claim admission and every hosted
claim transition independently revalidate the exact current release before changing
authority.

Capacity admission is a durable host-kernel schedule, not an all-siblings barrier.
Each execution records an exact DEMAND over candidate reservation IDs; deterministic
weighted round-robin emits expiring, single-use GRANT capabilities. A thirteen-node
ready barrier on four authenticated slots therefore advances as `4, 4, 4, 1` as
permits return, while its downstream barrier remains closed until all thirteen settle.
A continuously queued small execution receives a slot ahead of the next wide-execution
turn, regardless of repository. Unavailable capacity returns the resumable typed state
`WAITING_FOR_CAPACITY`; it is not an authority or integrity failure. Expired unused
grants restore the exact unconsumed candidates, while consumed grants can never be
replayed for another reservation.

Target reconciliation evidence remains intentionally live and execution-scoped: a fresh
dispatcher must inspect the configured singleton release target branch before releasing
work, and the resulting exact digest must match the repository-arbiter target watermark.
Completion evidence is the opposite: once integrated and validated, it survives deletion
of runtime authority and a completely fresh checkout.

## Host-neutral durable primary-task workflow

`.autopilot/workflow-policy.json` is mandatory for every node and every
dispatcher/repair/reconciliation/integration/promotion/replan task. The approved durable
primary task owns its released node through the stopping condition. Host selection is
capability-matched and never expands authority. Nested agents are bounded sidecars for
research, review, or non-blocking validation; they cannot replace primary delivery.

Sidecars are admitted only when deterministic token accounting predicts a positive net
saving above policy margin. The root creates them with read-only authority, reserves a
shared descendant budget, and records every preparation, binding, progress event, and
terminal result in the hash-chained `state/sidecar-bindings.jsonl` registry. A sidecar
may request a depth-two descendant, but only the root may authenticate and spawn it;
deeper, duplicate, unevidenced, or over-budget requests are denied before side effects.
Primary tasks, sidecars, and validation consume one canonical per-OS-user host budget
across every registered repository. The current App Server policy is conservatively one
slot unless a stronger expiring provider capability is independently sealed; compiler
support never fabricates a larger ceiling. Initial and descendant sidecar admission fail
closed when no slot remains. Parent tasks receive idempotent spawn and terminal notices.
Early parent termination cancels and settles its whole sidecar subtree first. Poll,
replay, timeout, malformed-result, and cancellation paths fail closed and active
sidecars prevent a quiescent verdict.

The attended-card adapter has no authenticated lifecycle and the current Codex App Server
protocol has no crash-exact thread creation key. They therefore advertise card-only and
observer-only authority respectively; unfinished autonomous work returns
`WAITING_FOR_HOST` instead of claiming it was launched. Optional preparation tasks and
sidecars are omitted when they cannot be settled. Mandatory work is never silently
truncated; a cohort that cannot fit authenticated capacity fails closed before a host
effect.

When a capability is unavailable, return an exact typed blocker to the parent. The parent
repairs the workflow or selects an approved capable host and resumes the same node. A
repairable host/tool gap is not a reason to make the user execute commands manually.

If human action is genuinely required, never assume the user knows the UI, command, or terminology. Give exact novice-safe steps, expected results, what to return, and safety/rollback guidance. Every session response ends with `WHAT I DID`, `NEXT STEPS`, and `BLOCKS`.

## Role-first consultation rule

A worker may not ask the owner a question merely because the task is ambiguous, hard,
blocked by a software defect, or missing evidence another role can collect. It must
first create a typed consultation and route it to at least two applicable roles.

Human escalation is valid only for a genuine authority class:

- credential or secret;
- legal or regulatory signoff;
- financial spend;
- production access;
- protected-branch merge;
- owner value choice;
- personal consent;
- external contractual commitment.

Roles may not fabricate any of those. Same-model role identities are procedural
separation, not independent humans.

## Cheating definition

The system must raise a cheating concern when it detects or proposes any of the
following:

- weakening, replacing, hiding, or reading sealed acceptance material improperly;
- evaluator or holdout leakage;
- target/future commit access before a prediction or plan is sealed;
- self-grading or self-promotion presented as independent;
- fabricated, stale, mismatched, or selectively omitted evidence;
- authority expansion, credential use, protected-branch mutation, merge, deployment,
  spending, or policy mutation outside a sealed grant;
- metric gaming, benchmark overfitting, friendly-reviewer selection, or consultation
  theater;
- concealment of dissent, adverse tests, failed attempts, or rollback gaps.

A role council may disprove the concern only with retained evidence. Confirmed cheating
quarantines the work. Unresolved cheating cannot be converted into ordinary success.

## State and durable receipt commits

Runtime state under the authenticated execution directory is generated and ignored by
Git. The default repository-local locator may still resolve beneath `.autopilot/state/`,
but callers must use the canonical `--state-dir`, `--host-runtime-dir`, and
`--execution-namespace` coordinates rather than assuming that path. Runtime authority may
contain a working receipt copy, dispatcher reconciliation state, GitHub snapshots, and
dispatcher release records, but it is never the durable completion source.

For every non-bootstrap node, `complete` validates the receipt and creates an **empty
receipt commit** on the already-claimed node branch. The receipt commit:

- has the exact `final_commit` as its only parent;
- has the exact `final_tree`, so it changes **zero repository paths** and therefore does
  not expand the node's effective file write authority;
- contains the canonical machine-readable completion receipt in its commit message;
- is accepted only when the receipt's declared `changed_paths` exactly match the actual
  `base_commit..final_commit` Git diff and every path is allowed by the node contract plus
  any validated exact-path authority amendment;
- is cross-checked against the retained remote-claim commit, including node ID, plan
  fingerprint, target/base SHA, and claimed branch.

The receipt still contains exact base/final commit **and tree** identities, plan and
contract binding, changed paths, passing required tests, evidence, role identities,
authority, consultations, acceptance decision, and rollback reference.

### Sealed receipt-branch retirement

The controller has one non-generic recovery for the court-quarantined `EXPLORER-310`
receipt branch. Its sealed record, independent court disposition, source SHA, archive ref,
and configured `origin` repository are fixed in repository artifacts. The command has no
remote, branch, SHA, or replacement-node option. It creates and verifies a zero-path
quarantine commit before atomically deleting the active receipt branch under an exact lease.
The single literal `origin` fetch URL must also be the actual push destination: push URLs,
Git URL rewrites, and injected Git configuration fail closed.
It writes append-only runtime evidence only after remote verification. A fresh snapshot,
reconciliation, and dispatcher release are mandatory before a replacement claim.
The sealed incident target remains provenance; the independent Appeals `ADAPT` record
requires the current reconciled singleton target to contain the integrated capability.

### Sealed L2 recovery bootstrap

ADR-057 adds three separately sealed, release-only recovery primitives. `OPTIMIZER-370`
and `ORCH-300` may receive an exact repair dispatch and CAS-published ancestry-preserving
repair claim only when their committed authorities, current authenticated snapshot,
reconciliation, full doctor evidence, dispatcher release, literal origin, branch head,
PR mapping, and node scope all match. Their replacement receipts must bind the exact grant,
old receipt, complete repair-claim payload, captured execution release, and deterministic
merge. Only the exact historical/replacement pair resolves; every other duplicate remains
fail closed.

The literal-origin singleton release ref is fetched and compared immediately before and
after each recovery CAS. Repair claim and receipt intents are written before publication,
so an exact interrupted or expired lease can be verified and resumed or rolled back after
restart. Ambiguous or failed compensation remains `ADVERSE` with its intent and audit
evidence intact. The global validation lease is a repository-shared, locked mutex with an
exact nonce-backed `lease_id`; release and expiry repair must present that generation, so
a stale owner cannot delete its successor. Claims use the same repository authority and
return an exact `claim_id` required by every later claim transition. Replacement
receipts are rejected unless their complete schema, identities, evidence references, and
model-runtime record have the sealed types and nonblank values. Consultation and identity
rows have exact nested schemas and unique roles; authority digests use canonical lowercase
SHA-256 syntax.
The sealed envelope also fixes node-defined test/role ordering and forbids identity reuse
or requester self-consultation. Its end-to-end regression uses a wholly disposable bare
remote through real claim and receipt CAS, restart recovery, integration, and durable
`COMPLETE` reconstruction.

`retire-builder-330-branch --actor IDENTITY` has no caller-selected remote/ref/SHA inputs.
It may archive and retire only the sealed stale Builder head under an atomic source-head and
archive-absence lease. A fresh snapshot must then show the canonical branch absent and the
dedicated archive ref at the exact candidate before reconciliation, full doctor, status,
dispatch, and ordinary canonical reclaim. It does not reuse the Explorer retirement grant.

Controller test fixtures are built from the Git-tracked `.autopilot` manifest with an empty
runtime state directory. Tests must never import ignored `.autopilot/state/**`, generated
modules, bytecode caches, or live origin refs. Production generated-state and literal-origin
verification semantics are unchanged.

Linked worktrees and registered independent clones converge on one repository arbiter;
each authenticated execution namespace then converges on its own execution directory.
Repository target watermarks, claims, publication fences, and cross-execution conflicts
live under the arbiter. Receipts, blockers, snapshots, task/sidecar bindings, attended
cards, and execution validation state live under the execution namespace. Existing
legacy registries require the explicit `runtime-authority-migrate` reconciliation court,
which archives exact bytes, partitions compatible evidence, quarantines ambiguity, and
fails closed on unproved authority. The runtime-ready marker is published only after
bootstrap and attended migration both complete. See ADR-063.

The repository arbiter is paired with one canonical per-user host admission kernel, so
aggregate session and validation reservations are host-wide and multi-repository. This
does not claim OS-level CPU, memory, disk, network, CI, or process cancellation control;
an authority fence cannot forcibly cancel an external chat. Those stronger capabilities
require a separately governed execution provider.

Ordinary writers reject a different host or execution kernel before mutation.  The two
upgrade commands above are the only transition apertures: they require an exact
predecessor CAS, an append-only generation record, and a host/repository/execution
zero-activity cut.  They are crash-idempotent and reject downgrade or retired-writer
replay; changing checkout bytes alone never grants writer authority.
If a host JSONL append is torn by power loss, `host-runtime-recover-torn-tail`
retains the exact tail bytes in immutable evidence before truncating to a fully
validated prefix.  Complete-but-invalid records and ambiguous interior corruption
remain fail-closed; capacity history additionally requires `--host-id`.

Worker publication order is mandatory:

1. Receive a current explicit dispatcher `START NOW` for the exact node.
2. Claim the fixed node branch remotely and work only on that branch.
3. Finish and commit the node implementation/evidence. Record that exact commit and tree
   as `final_commit` and `final_tree` in the receipt.
4. Run `autopilot complete ...`. It validates the candidate and claim provenance, appends
   the zero-path durable receipt commit, advances the local node branch to that commit,
   writes only a working copy/index under the authenticated execution directory, and prints the receipt
   commit SHA.
5. Push the node branch and open/update its draft PR. The receipt commit itself is the
   durable repository evidence; no extra file path is required.
6. **Integrate node PRs with an ancestry-preserving merge commit. Do not squash or
   rebase.** The claim, exact candidate, and receipt commits must remain ancestors of
   the singleton release branch. The historical PR #120 squash is handled only by its sealed bootstrap
   attestation and is not precedent for future nodes.
7. After merge, rerun the dispatcher. The merge advances the singleton release branch, so every earlier worker
   release is stale by definition. A fresh controller reconstructs completion and only a
   new dispatch release may start further work.

If a local receipt is stale or tampered it cannot be hidden behind a valid durable
commit. If multiple durable receipt commits exist for one node, or a retained receipt is
wrong-plan, wrong-branch, wrong-tree, non-integrated, out-of-scope, missing claim
provenance, or otherwise inconsistent, the node fails closed as `REPAIR_REQUIRED`.

## Permanent dispatcher prompt

Use the short prompt in `USER_GUIDE/02_ONE_PROMPT_FOREVER.md`. Its behavior is defined by
the versioned policy and controller rather than repeated prompt prose. The human should
never need to remember the prior response, and prior releases must never be carried into
a new dispatcher session.
