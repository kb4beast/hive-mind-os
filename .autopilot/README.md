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
append-only reconciliation records. A branch name, PR title, plan document, or edited
status file never proves completion.

`BOOT-000` is the one historical bootstrap that predates durable receipt publication.
Its exact PR, actual branch, candidate commit/tree, squash-integrated commit/tree, test
evidence, changed paths, and authority are sealed in
`.autopilot/bootstrap-completion.json` and cross-bound by
`.autopilot/control-plane.json`. The controller verifies candidate/integrated tree
equality and target ancestry; it does not fabricate the planned bootstrap branch.

## Commands

```bash
python .autopilot/bin/autopilot.py --repo-root . doctor
python .autopilot/bin/autopilot.py --repo-root . status
python .autopilot/bin/autopilot.py --repo-root . ready
python .autopilot/bin/autopilot.py --repo-root . render-prompt NODE_ID
python .autopilot/bin/autopilot.py --repo-root . claim NODE_ID \
  --owner PROVIDER:SESSION --publish-remote
python .autopilot/bin/autopilot.py --repo-root . heartbeat NODE_ID \
  --owner PROVIDER:SESSION
python .autopilot/bin/autopilot.py --repo-root . complete NODE_ID \
  --owner PROVIDER:SESSION --receipt PATH
```

`--publish-remote` creates a unique empty claim commit on the node's fixed remote branch.
Git ref creation is the cross-session mutex: a competing worker loses the push race and
must stop. Local claim files add lease/heartbeat state but are not treated as the only
cross-session lock.

## Dispatcher protocol

A dispatcher session does not implement product work. It:

1. reads this file and `plan.json`;
2. fetches current `main` and records its exact SHA;
3. inspects open/merged/closed PRs, CI, remote node branches, and stale claims;
4. writes a current `.autopilot/state/github-state.json` snapshot through
   `install-github-snapshot`;
5. runs `status`;
6. reconciles target advancement before issuing worker prompts;
7. returns only dependency-ready, conflict-free nodes with copy-ready prompts.

Target reconciliation remains intentionally live and session-local: a fresh dispatcher
must inspect whatever `main` is now before releasing work. Completion evidence is the
opposite: once integrated and validated, it must survive deletion of local
`.autopilot/state/` and a completely fresh checkout.

## ChatGPT Classic-first execution workflow

`.autopilot/workflow-policy.json` is a mandatory plan-wide policy for every node and every dispatcher/repair/reconciliation/integration/promotion/replan session. ChatGPT Classic is the normal node owner and must exhaust its available reasoning, connectors/tools, bounded repair paths, and role-first consultation before Codex is considered. Codex is a last-resort executor for only the smallest concrete subtask requiring a capability unavailable in Classic; ownership returns to Classic afterward. Difficulty or convenience alone is never a Codex reason.

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

## State and durable receipts

Runtime state under `.autopilot/state/` is generated and ignored by Git. Runtime state
may contain a working copy of a receipt, but it is never the durable completion source.

For every non-bootstrap node, `complete` deterministically derives a durable receipt
path from that node's existing `evidence/**` write scope and writes:

`<node evidence directory>/autopilot-completion-receipt.json`

This does **not** expand node authority. The receipt stays inside the node's sealed write
scope. It must contain the exact base/final commit **and tree** identities, plan and
contract binding, changed paths, passing required tests, evidence, role identities,
authority, consultations, acceptance decision, and rollback reference.

Worker publication order is mandatory:

1. Finish and commit the node implementation/evidence. Record that commit and tree as
   `final_commit` and `final_tree` in the receipt.
2. Run `autopilot complete ...`. The command validates the receipt, writes runtime state,
   writes the durable receipt, and prints the durable repository-relative path.
3. Commit the durable receipt as a follow-up evidence commit on the same node branch.
4. Push and open/update the draft PR.
5. **Merge the node PR with an ancestry-preserving merge commit. Do not squash or rebase
   node PRs.** The validated `final_commit` must remain an ancestor of `main` after
   integration. The historical PR #120 squash is handled only by its sealed bootstrap
   attestation and is not precedent for future nodes.
6. After merge, rerun the dispatcher. It validates the durable receipt against current
   target history before releasing any dependent node.

If a durable or local receipt exists but is stale, tampered, wrong-plan, wrong-branch,
wrong-tree, non-integrated, or outside write scope, the node fails closed as
`REPAIR_REQUIRED`; a valid duplicate copy is not used to hide a conflicting local one.

## Permanent dispatcher prompt

Use the exact prompt in `USER_GUIDE/02_ONE_PROMPT_FOREVER.md` after the bootstrap PR is
merged. The human should never need to remember the prior dispatcher response.
