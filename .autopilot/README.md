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

The controller reconstructs execution state from target-branch ancestry, validated
receipts, PR/CI snapshots, remote branches, bounded claims, and append-only
reconciliation records. A branch name, PR title, plan document, or edited status file
never proves completion.

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

## State and receipts

Runtime state under `.autopilot/state/` is generated and ignored by Git. Completion
receipts are accepted only when they bind the plan fingerprint, node contract, base and
final commits, changed paths, passing tests, evidence, role identities, authority,
consultations, acceptance decision, and rollback.

## Permanent dispatcher prompt

Use the exact prompt in `USER_GUIDE/02_ONE_PROMPT_FOREVER.md` after the bootstrap PR is
merged. The human should never need to remember the prior dispatcher response.
