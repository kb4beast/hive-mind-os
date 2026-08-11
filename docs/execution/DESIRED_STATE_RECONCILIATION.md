# Desired-state reconciliation

RECONCILE-250 adds a deterministic recovery planner at
`hive_mind_os.brain_kernel.reconciler`. It is an additive projection: the event
spine, scheduler, effect adapters, and authority envelopes remain authoritative.
The planner never edits an event, executes a provider, rebuilds a workspace, or
acquires a lease by itself.

## Input and projection

`DesiredStateReconciler.reconcile(observed, now=...)` accepts either an
`ObservedState` or a mapping with these fields:

| Field | Meaning |
| --- | --- |
| `mission_id`, `mission_status` | Current mission identity and observed status |
| `work` | Mapping or records keyed by `work_id`; records may include `status`, `attempts`, `workspace_id`, `authority_scope`, and rollback fields |
| `leases` | Lease records with `lease_id`, `work_id`, and `expires_at`/`lease_expiry` |
| `intents` | Durable intent records bound to a `work_id` |
| `workspaces` | Workspace records with `workspace_id`, `work_id`, and `exists`/`present` |
| `provider_failures` | Failure records with `failure_id`, `work_id`, `retryable`, and `attempts` |
| `verifications` | Verification records; `INTERRUPTED`, `MISSING`, and `ABORTED` are recoverable states |
| `no_progress_count`, `progress_signature` | Loop detector inputs |
| `authority_scope` | Existing scope inherited by repairs; reconciliation never adds paths |

Records are copied and sorted by stable identifiers before projection. The
result contains `observed_digest`, `desired_digest`, sorted `RepairAction`
records, and a quarantined flag. Equal observations produce equal digests even
when adapters provide records in different orders.

## Bounded repairs

- Expired active leases produce `release-stale-lease`, then make nonterminal work
  desired `READY`.
- Intents without a matching mission work item are quarantined. Intents bound to
  known active work are remanded for a fresh decision.
- Missing workspaces are rebuilt only within `max_retries`; exhaustion is
  quarantined.
- Retryable provider failures produce `retry` within the same attempt budget;
  terminal or exhausted failures are quarantined.
- Interrupted verification is remanded without re-running the effect. Exhausted
  verification attempts are quarantined.
- Partial or failed integration produces `rollback`, preserving the last accepted
  state as the rollback target.
- Repeated no-progress and an over-large repair pass quarantine rather than loop.

`ReconciliationResult.apply()` invokes only handlers explicitly supplied by the
caller, in deterministic action order. A missing handler is a safe no-op. This
keeps side effects, certificate/provenance checks, leases, and protected
authority at their existing boundaries.
