# Output Schemas and Simulation Protocol

## Mission Control

```yaml
run_id:
status:
objective:
risk_tier:
autonomy_level:
current_role:
completed_roles:
completed_stages:
evidence_count:
open_court_cases:
blockers:
budget_status:
next_transition:
```

## Typed objective

```yaml
objective_id:
goal:
repository_or_context:
acceptance_criteria:
constraints:
risk_tier:
autonomy_level:
available_tools:
evidence_inventory:
created_at:
```

## Work item

```yaml
work_item_id:
objective_id:
role:
instruction:
dependencies:
status:
required_outputs:
```

## Role result

```yaml
role:
work_item_id:
status:
summary:
evidence:
proposed_actions:
lessons:
limitations:
```

## Evidence

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
```

## Court case

```yaml
case_id:
claim_id:
proposition:
source_ids:
burden:
advocate_brief:
cross_examiner_brief:
expert_findings:
supporting_exhibits:
opposing_exhibits:
unresolved_objections:
prohibited_findings:
verdict:
obligations:
architecture_mapping:
acceptance_tests:
outcome_metrics:
```

## Policy decision

```yaml
action:
actor_role:
risk:
required_level:
available_level:
decision:
reason:
required_external_grant:
required_receipts:
```

## Recursive experiment

```yaml
experiment_id:
contract:
champion_id:
candidate:
proposer_id:
builder_id:
evaluator_id:
observations:
artifacts:
policy_violations:
metric_gaming_signals:
holdout_accessed:
verdict:
reasons:
next_non_improvement_count:
```

## Compliance verdict

```yaml
verdict: COMPLIANT | BLOCKED | FAILED
full_lifecycle_claimed:
simulation_only:
completed_roles:
completed_stages:
missing_evidence:
policy_violations:
unresolved_sources:
rollback_status:
independent_verification_status:
reasons:
next_eligible_action:
```

## Full-response skeleton

```markdown
# MISSION CONTROL
...

# ROLE PASSES
## Orchestrator
...
## Explorer
...
## Architect
...
## Builder
...
## Curator
...
## Integrator
...
## Steward
...
## Optimizer
...

# COURT DOCKET
...

# POLICY DECISIONS
...

# COMPLIANCE VERDICT
...

# LEDGER DELTA
```jsonl
...
```

# RUN CHECKPOINT
```yaml
...
```
```

## Compact mode

For small tasks, use:

```markdown
**Mode:** Partial Hive OS simulation
**Applicable roles:** ...
**Decision:** ...
**Evidence:** ...
**Risks/blockers:** ...
**Next transition:** ...
```

Do not claim full lifecycle completion in compact mode.
