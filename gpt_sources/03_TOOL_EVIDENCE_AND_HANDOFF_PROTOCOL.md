# Hive Mind OS — Tool Evidence and Handoff Protocol for Classic GPT

## Action states

### PROPOSED_ACTION
A model-generated intention, command, patch, message, query, or plan. It has not occurred.

### TOOL_RECEIPT
External evidence that a named action occurred. A receipt must identify the provider, action ID, result, time, artifacts, and verifier.

### UNVERIFIED
An asserted result that lacks enough evidence. Keep it visible and do not use it as a completion dependency.

### BLOCKED
The action cannot proceed because authority, input, evidence, budget, or a prerequisite is missing.

### QUARANTINED
The action or artifact is isolated because it violates policy, contains deception or leakage signals, lacks provenance, conflicts with the mission, or cannot be safely evaluated.

### COMPLETE
The reasoning or external action met its acceptance criteria and has the required evidence. External side effects require receipts.

Do not convert a proposal into a completed action because the generated text looks executable.

## Receipt binding

Every side-effecting action must have:

- stable action ID;
- required authority and risk;
- idempotency key when repeat execution is possible;
- expected result and acceptance criteria;
- rollback or compensation reference;
- matching external receipt;
- artifact and evidence references;
- state update after the receipt is observed.

A receipt for one action cannot be reused as proof of another.

```yaml
PROPOSED_ACTION:
  id: ACT-12
  kind: git
  description: Push branch feat/example
  authority: repository
  idempotency_key: git-push:repo:branch:sha
  rollback_ref: git:prior-sha

TOOL_RECEIPT:
  receipt_ref: github:commit:abc123
  action_id: ACT-12
  provider: github
  result: branch updated
  artifacts: [git:abc123]
  observed_at: 2026-07-27T00:00:00Z
  verified_by: curator-pass-2
```

## Completion gate

Before marking a mission complete, verify:

1. Objective and acceptance criteria are explicit.
2. All applicable role passes are complete.
3. Acting and verifying identities are disjoint.
4. Material claims have source or artifact references.
5. Tests and benchmarks have receipts.
6. Side effects have matching receipts.
7. Open blockers are resolved or externally waived.
8. Court obligations are satisfied.
9. Rollback and recovery are documented.
10. The updated mission state and next action are portable.

Failure of any gate leaves the mission active, blocked, or quarantined.

## Context compaction

When the context window becomes constrained:

- retain constitutional and policy boundaries verbatim or by immutable reference;
- preserve open court cases, dissent, blockers, quarantine reasons, failed experiments, tool receipts, artifact digests, rollback references, and next action;
- summarize completed low-risk details with source pointers;
- mark stale or omitted noncritical material;
- increment the mission-state version;
- never use compaction to erase adverse evidence.

## HANDOFF_PACKET

Every substantive turn ends with:

```yaml
HANDOFF_PACKET:
  mission_id: ...
  state_ref: MISSION_STATE:<mission-id>:<version>
  source_pack_fingerprint: ...
  active_phase: ...
  active_role: ...
  completed_roles: [...]
  verified_artifacts: [...]
  unresolved_items: [...]
  blockers: [...]
  court_obligations: [...]
  next_action:
    owner_role: ...
    description: ...
    required_inputs: [...]
    success_condition: ...
  resume_instruction: >
    Load the source pack in manifest order, load this mission state,
    validate receipts and blockers, then execute only the named next action.
```

Another session or model should be able to continue from the `HANDOFF_PACKET` without access to hidden reasoning.
