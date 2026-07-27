# Evidence Ledger and Memory Simulation

## Ledger principle

The real implementation uses an append-only event and lesson store. Classic GPT must emulate this by appending ledger entries in the conversation and never rewriting prior events.

## Event schema

```json
{
  "sequence": 1,
  "run_id": "RUN-...",
  "event_type": "objective.started",
  "actor": "orchestrator",
  "payload": {},
  "created_at": "ISO-8601 or conversation-relative timestamp",
  "receipt_status": "SIMULATED|USER_PROVIDED|TOOL_VERIFIED"
}
```

## Recommended event types

- `objective.started`
- `work.started`
- `work.completed`
- `work.blocked`
- `work.failed`
- `source.registered`
- `claim.extracted`
- `court.verdict`
- `policy.allowed_simulation`
- `policy.denied`
- `artifact.proposed`
- `artifact.received`
- `test.not_run`
- `test.receipt`
- `curator.verdict`
- `experiment.verdict`
- `lesson.recorded`
- `objective.completed`

## Evidence record

```yaml
evidence_id:
kind:
summary:
source:
provenance:
strength:
independent:
receipt_status:
payload:
created_at:
```

## Memory partitions

- **Working memory:** active objective context.
- **Episodic memory:** what occurred in a run.
- **Semantic memory:** validated facts with provenance and freshness.
- **Procedural memory:** versioned skills and workflows.
- **Project memory:** architecture, decisions, constraints, glossary.
- **User/organization memory:** explicitly supplied preferences and policies.
- **Negative memory:** rejected hypotheses, regressions, unsafe strategies, counterexamples.

Each memory item needs:
- scope;
- source;
- confidence;
- owner;
- created time;
- freshness/TTL;
- correction history;
- deletion/forgetting policy.

Unsupported memory never becomes a constitutional rule.

## Portable checkpoint

```yaml
checkpoint_version: 1
run_id:
objective:
risk_tier:
autonomy_level:
status:
current_role:
completed_roles:
completed_stages:
evidence_index:
court_verdicts:
policy_decisions:
artifacts:
blockers:
lessons:
next_transition:
```

## New-chat behavior

The GPT cannot assume prior chat state. A user must paste the checkpoint. The resumed GPT appends new entries and preserves all prior evidence IDs and verdicts.

## Ledger integrity caveat

Conversation text is not cryptographically append-only. The GPT must describe it as a **simulated ledger**, not equivalent to the SQLite/hash-chained production target.
