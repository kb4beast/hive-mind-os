# Self-healing runtime

`src/hive_mind_os/brain_kernel/self_healing.py` composes the desired-state
reconciler; it never forks, subclasses, or re-implements it. Fault
classification stays in `DesiredStateReconciler.reconcile`, and applying a
repair is always an explicit, authority-checked handler call. See
[DESIRED_STATE_RECONCILIATION.md](DESIRED_STATE_RECONCILIATION.md) for the base
planner semantics assumed below.

## Fault matrix

| Failure class | Observed signal | `RepairKind` | Bound / budget | Terminal outcome |
|---|---|---|---|---|
| Dead worker holding a claim | `leases[].expires_at <= now`, state `ACTIVE`/`LEASED` | `RELEASE_STALE_LEASE` | one action per lease id | work returns to `READY` |
| Retryable provider failure | `provider_failures[].retryable`, `attempts < max_retries` | `RETRY` | `ReconciliationPolicy.max_retries` (3) | `QUARANTINE` once spent; a non-retryable failure quarantines immediately |
| Missing workspace | `workspaces[].exists` false, `rebuild_attempts < max_retries` | `REBUILD_WORKSPACE` | `max_retries` | `QUARANTINE` on exhaustion |
| Interrupted verification | work `AWAITING_VERIFICATION` + verification `INTERRUPTED`/`MISSING`/`ABORTED` | `REMAND` | `max_retries` | `QUARANTINE` on exhaustion |
| Undecided intent on live work | `intents[]` bound to non-terminal work | `REMAND` | `max_retries` | bounded role re-decision; an orphaned intent quarantines instead |
| Diverged integration | `rollback_required` or `INTEGRATING` + failed/partial integration | `ROLLBACK` | authority-gated, see below | `escalated-authority` when out of scope |
| Repeated semantic stall | `no_progress_count >= no_progress_limit` | `QUARANTINE` | `no_progress_limit` (3) | mission quarantined |
| Repair storm | more proposals than `max_repairs_per_pass` | `QUARANTINE` | `max_repairs_per_pass` (8) | pass truncated and quarantined |

Actions apply in the reconciler's deterministic order (priority, then
`action_id`), so an identical observation yields an identical
`HealingReceipt.digest`.

## Failover identity guarantee

`ProviderFailoverChain.complete` computes `request_identity(request)` **once**,
before the first attempt, and hands the same immutable `ModelRequest` to every
provider, so `FailoverReceipt.request_digest` is identical whether one provider
or five were tried — failover changes the transport, never the contract.
`FailoverReceipt.response_digest` covers only `response.content`.

Only `ModelTransportError` and `MissingModelCredential` trigger failover; each
records a `FailoverAttempt` holding the provider index, the non-secret
`credential_reference`, an outcome, and redacted detail. `raw_body`, API keys,
and environment values never enter an attempt, receipt, or event.
`ModelResponseError` is semantic, propagates unchanged, and lands on the
no-progress ledger instead of silently switching providers. Full transport
exhaustion raises `FailoverExhaustedError` carrying every attempt.

## Authority rule for rollback

Before dispatch, `SelfHealingRuntime.heal` checks
`set(action.authority_scope) <= set(granted_authority)`. The guard applies to
every kind, and `ROLLBACK` is the case that matters: a rollback runs
automatically only inside authority the caller already holds. Otherwise the
handler is never invoked, the outcome is `escalated-authority`, and the
`action_id` lands in `HealingReceipt.escalations` for a human or role decision.

## No-progress loop

`ProgressLedger.advance` is a pure comparator. A pass that proposes actions
adopts the desired digest as the new signature and resets the count; a pass that
proposes nothing keeps the previous signature, so identical stalls accumulate.
The caller persists `ProgressUpdate.no_progress_count` into the next observed
document, where the reconciler's existing bound (not duplicated here) emits
`QUARANTINE`.

## Wiring handlers

Build a `RepairHandlerRegistry`, `register` one handler per `RepairKind`
(re-registering raises `ValueError`), pass it to `SelfHealingRuntime`, and call
`heal(observed, now=..., granted_authority=(...))`. An unregistered kind is a
safe no-op recorded as `skipped-no-handler`, mirroring
`ReconciliationResult.apply`; the proposal is retained, never invented. A
handler exception is wrapped in `SelfHealingError` and stops the pass — a failed
repair is never stepped over.

## Durable pass event — open obligation

`SelfHealingRuntime` optionally appends one `self_healing.pass` `KernelEvent`
(`occurred_at` pinned to the epoch, `idempotency_key` = receipt digest) so a
crashed-and-replayed pass is a read-only retry. That append currently fails
closed: `projection.reduce_event` rejects unknown event types and
`KernelStore.append_batch` rebuilds projections in the same transaction, so the
store raises `KernelIntegrityError` and writes nothing. Teaching the reducer
this type is a change to `projection.py`, outside this node's write scope, so it
is recorded as an open obligation rather than worked around. Until it lands,
construct `SelfHealingRuntime` without a `store`.
