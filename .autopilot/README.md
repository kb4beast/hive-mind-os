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

```bash
python .autopilot/bin/autopilot.py --repo-root . doctor
python .autopilot/bin/autopilot.py --repo-root . status
python .autopilot/bin/autopilot.py --repo-root . ready
python .autopilot/bin/autopilot.py --repo-root . dispatch \
  --actor DISPATCHER_ID [--node NODE_ID ...]
python .autopilot/bin/autopilot.py --repo-root . render-prompt NODE_ID
python .autopilot/bin/autopilot.py --repo-root . infer-intent "USER MESSAGE"
python .autopilot/bin/autopilot.py --repo-root . orchestrate \
  --request "USER MESSAGE" [--apply] --json
python .autopilot/bin/autopilot.py --repo-root . simple-prompt
python .autopilot/bin/autopilot.py --repo-root . prepare-launch INSTRUCTION_ID --host HOST
python .autopilot/bin/autopilot.py --repo-root . bind-launch INSTRUCTION_ID \
  --host HOST --task-id TASK_ID [--host-id HOST_ID] [--cursor CURSOR]
python .autopilot/bin/autopilot.py --repo-root . record-launch-terminal INSTRUCTION_ID \
  --terminal-state SUCCEEDED --host-event-ref HOST_TERMINAL_EVENT \
  --observed-by ORCHESTRATOR_ID
python .autopilot/bin/autopilot.py --repo-root . release-launch INSTRUCTION_ID \
  --terminal-event TERMINAL_OBSERVATION_EVENT_ID \
  --reason "terminal host result recorded"
python .autopilot/bin/autopilot.py --repo-root . claim NODE_ID \
  --owner PROVIDER:SESSION --publish-remote
python .autopilot/bin/autopilot.py --repo-root . heartbeat NODE_ID \
  --owner PROVIDER:SESSION
python .autopilot/bin/autopilot.py --repo-root . complete NODE_ID \
  --owner PROVIDER:SESSION --receipt PATH
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
records `PREPARED -> CREATED -> BOUND -> TERMINAL_OBSERVED -> RELEASED` events and
consumes existing bindings;
emitting JSON alone is not task creation.

`status` distinguishes static **eligibility** from current execution **release**.
`ready` returns only nodes whose latest valid dispatcher release assigns `START NOW`.
A worker claim fails closed if there is no current explicit release for that exact node.

`--publish-remote` creates a unique empty claim commit on the node's fixed remote branch.
That claim retains the exact node branch, target SHA, owner, lease, and plan fingerprint.
Git ref creation is the cross-session mutex: a competing worker loses the push race and
must stop. Local claim files add lease/heartbeat state but are not the cross-session or
durable completion source.

## Dispatcher protocol

A dispatcher session does not implement product work. Until it completes the steps below,
all not-yet-released workers are `WAIT`.

1. Read this file, `workflow-policy.json`, `control-plane.json`,
   `authority-amendments.json`, and `plan.json`.
2. Fetch the configured singleton release target branch and record its exact commit and tree.
3. Inspect open/merged/closed PRs, CI, remote node branches, claims, durable receipts, and
   plan-impacting changes.
4. Install a current `.autopilot/state/github-state.json` snapshot through
   `install-github-snapshot`.
5. Run `doctor`, `status`, and `ready` as applicable.
6. Reconcile current target state before release. Any graph/scope inconsistency must use
   append-only reconciliation/replan authority; never silently broaden a node.
7. Compute the smallest dependency-eligible, conflict-free candidate wave. Eligibility
   alone still means `WAIT`.
8. Run `dispatch --actor ... [--node ...]`. This is the explicit release boundary.
9. Require every candidate node to have exactly one verdict: `START NOW`, `WAIT`, or
   `STOP`.
10. A released multi-node wave must say `START TOGETHER NOW`. The dispatcher must also
    emit a plain action sentence such as `Open these 2 sessions now: RECON-010, BASE-020`
    or `Do not open any worker sessions yet`.
11. Render/copy worker prompts only for current `START NOW` nodes.

Static DAG/level membership never authorizes a worker. A target-branch advance or merge,
new conflicting claim, GitHub snapshot change, or new reconciliation event makes prior
release instructions stale. Run the dispatcher again rather than reusing an old prompt.
The claim command independently revalidates the release before creating a claim.

Target reconciliation remains intentionally live and session-local: a fresh dispatcher
must inspect the configured singleton release target branch before releasing work. Completion evidence is the
opposite: once integrated and validated, it survives deletion of local
`.autopilot/state/` and a completely fresh checkout.

## Host-neutral durable primary-task workflow

`.autopilot/workflow-policy.json` is mandatory for every node and every
dispatcher/repair/reconciliation/integration/promotion/replan task. The approved durable
primary task owns its released node through the stopping condition. Host selection is
capability-matched and never expands authority. Nested agents are bounded sidecars for
research, review, or non-blocking validation; they cannot replace primary delivery.

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

Runtime state under `.autopilot/state/` is generated and ignored by Git. It may contain a
working receipt copy, dispatcher reconciliation state, GitHub snapshots, and dispatcher
release records, but it is never the durable completion source.

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

Worker publication order is mandatory:

1. Receive a current explicit dispatcher `START NOW` for the exact node.
2. Claim the fixed node branch remotely and work only on that branch.
3. Finish and commit the node implementation/evidence. Record that exact commit and tree
   as `final_commit` and `final_tree` in the receipt.
4. Run `autopilot complete ...`. It validates the candidate and claim provenance, appends
   the zero-path durable receipt commit, advances the local node branch to that commit,
   writes only a working copy/index under `.autopilot/state/`, and prints the receipt
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
