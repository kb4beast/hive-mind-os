# ADR-046: Opt-in Durable, One-shot Model-role Execution

- **Status:** Adapted bounded trusted-local implementation after independent Curator and Judge review
- **Date:** 2026-08-03
- **Prior decisions:** ADR-040, ADR-041, ADR-042, ADR-044
- **Scope:** one explicit model-backed role invocation through a durable local turn
  store; it does not enable model delivery jobs, generic model resumption, provider
  authentication, or hard isolation.

## Context

ADR-044 deliberately provided only a reusable model-turn state primitive.  The legacy
`ModelBackend.execute` loop can retry a call after a transport failure, resolves a
mutable prompt champion at execution time, and consumes an in-memory budget after a
provider call.  `RepositoryMission` and `resume_mission` likewise lack durable work-item
and completed-role artifacts for model backends.  Wiring that path directly would let a
restart make a changed request or repeat an outcome-unknown provider call.

The available internal evidence is the reviewed ADR-044 state contract and an
independent Architect/Cross-Examiner inspection of the current backend, mission, and
mission-store seams.  No provider idempotency, provider outcome-query contract,
provider-signed receipt, external lease authority, or hostile-process boundary is
available in this worktree.  Those sources must not be invented.

## Court record

- **Claim — advocate:** an opt-in executor can make a model role recoverable by sealing
  a stable work item, prompt, request, role contract, selected acceptance specification,
  provider configuration, local policy/lease references, redaction policy, and resource
  reservation before one provider invocation. **Disposition: adapt.**
- **Claim — cross-examiner:** wrapping the existing model retry loop, or turning on
  existing repository-mission resume for model jobs, is safe. **Disposition: reject.**
  It would regenerate work-item IDs, reread mutable prompt selection, omit completed
  model-role context, and allow duplicate provider requests.
- **Claim — expert boundary:** a local SQLite transaction and SHA-256 locators prove
  only local record consistency. **Disposition: adapt as a local recovery control; do
  not promote it to provider authentication, external atomicity, or source authority.**
- **Independent Architect/Cross-Examiner:** recommends a separate `durable-model-v1`
  lane with an append-only role slot, a permanent pre-dispatch reservation, a single
  `complete_once` call, terminal observed failures, and quarantine for uncertainty.
  Its provisional disposition is `adapt` at that bounded interface.
- **Independent Curator:** `adapt` after 62 focused checks plus four subtests, including
  exact typed acceptance/budget lookalikes, configured-secret and configured-endpoint
  exclusion, one-shot dispatch, reservation, reopen, and quarantine probes.  The
  Curator required the typed-input and receipt-projection corrections before its final
  disposition.
- **Independent Judge:** `adapt` after 12 durable-executor tests; 31 model
  state/backend/provider tests plus four subtests; same-slot/two-store race probes; and
  a concurrent-recovery probe.  One race made exactly one provider call and rehydrated
  a completed result; forced recovery during an in-flight call made one call and
  terminally quarantined the turn.  That intentional availability cost is accepted for
  this bounded fail-closed lane.
- **Dissent / blocking evidence:** no externally authenticated model result,
  idempotency/reconciliation API, externally enforceable lease/budget, model-role
  mission journal, capability-effect receipt rehydration, or credential/hostile-code
  isolation exists.  The Curator/Judge `adapt` verdict applies only to this local,
  opt-in executor and does not promote those absent capabilities.

## Decision

1. Add `DurableModelRoleExecutor` as a separate opt-in API.  It leaves
   `ModelBackend.execute`, the CLI model modes, `RepositoryMission`, and
   `resume_mission` unchanged.  The initial lane accepts one typed executable
   acceptance specification per durable model mission; it refuses to compress a
   multi-spec mission into a misleading single spec binding.
2. `DurableModelExecutionContext` requires a stable mission ID/state reference, an
   immutable local `ModelTurnBudget`, typed acceptance specification, policy and lease
   references, redaction-policy digest/secrets, and content-addressed prompt digests.
   A durable call reads the exact pinned prompt artifact or the generation-zero prompt;
   it never asks the registry for the current champion and never writes/promotes one.
3. The model-turn store creates an append-only role slot keyed by
   `(mission, state reference, role, work item)`.  A changed prompt, request/context,
   provider configuration/path/parameters, selected specification, role contract,
   policy/lease reference, redaction policy, or work-item binding yields a different
   plan and is rejected by that slot before network access.
4. Durable admission atomically records the exact plan, its slot, sealed mission budget,
   and one non-releasable reservation.  The reservation is one episode, one provider
   call, and a worst-case bounded compute estimate.  It is retained for successful,
   invalid, failed, and ambiguous turns; it is not silently released after a crash.
   This is local accounting, not an external authorization or billing record.
5. The executor invokes only `provider.complete_once` after the durable
   `dispatch_started` transition.  It never calls `complete`, its corrective retry
   loop, or a replacement request.  An observed malformed response or observed response
   decoding failure becomes a terminal failed model turn.  A timeout, cancellation,
   transport uncertainty, process interruption, or failure to durably adopt an outcome
   quarantines the turn and prohibits another provider call.
6. A successful response must parse and pass the existing role-result validator before
   it is transformed into the bounded caller-redacted `ModelRoleResult` and atomically
   adopted with the successful turn result.  On restart, the executor validates the
   same sealed inputs and returns that exact sanitized result without a provider call.
   A terminal turn without a sanitized successful result is not reinterpreted as a
   role success.  The configured provider endpoint is treated as a durable-output
   exclusion alongside caller-configured secret values, and prior context carrying that
   endpoint is rejected before it can reach the legacy ledger context manifest.

## Threat model and non-claims

| Threat | Control | Residual / non-claim |
|---|---|---|
| Restart changes prompt, provider configuration, request context, or role input | Pinned prompt/read, canonical request/config/selection digests, immutable role slot | Changes before the first durable admission are still caller input; no external configuration authority exists |
| Crash or timeout after a request may have reached the provider | `dispatch_started`, recovery quarantine, and no retry/replacement | Cannot determine whether the provider executed the request without an external outcome witness |
| Caller makes a second same-role plan | Slot is uniquely bound to the original plan digest | Explicit supersession authority is not implemented |
| Provider invocation exhausts a budget after a crash | Atomic permanent local reservation before dispatch | Not an externally enforceable lease, cost receipt, or billing reconciliation |
| A raw prompt, response, effective configured-provider endpoint, key, or configured secret reaches durable role state | Closed prior state contracts, digest-only plan/result fields, pinned result selection/redaction, configured-endpoint exclusion, and bounded ledger receipt | Unknown secrets, unrelated caller-supplied URLs, an incomplete redaction policy, or host/ledger compromise remain risks |
| Successful state is forged locally | Append-only triggers and binding checks | A hostile host can alter local storage and deny service; SHA-256 is not authentication |
| Model result resumes repository side effects incorrectly | This lane does not integrate `RepositoryMission` or its P06 capability checkpoints | A future model-mission journal must bind sanitized role results to ordered receipt refs before promotion |

## Migration and rollback

- This is additive.  A caller begins a fresh `durable-model-v1` mission with a
  filesystem-backed store and sealed inputs.  Legacy model-call ledger entries, legacy
  retrying model runs, and scripted P06 missions are never backfilled or relabeled as
  durable.
- Reopening an admitted mission revalidates its plan, role slot, budget, and reservation.
  `planned` may make its one call; `dispatch_started` becomes terminal ambiguous;
  completed successful role state is rehydrated; all other terminal states fail closed.
- Rollback disables new executor starts and blocks any active durable model-role
  mission.  It preserves the append-only store and must never route an existing durable
  slot through legacy retrying `ModelBackend.execute`.

## Acceptance and required validation

- A valid result survives store reopen with no second provider call and an exact
  sanitized rehydrated `AgentResult`.
- A transport failure after dispatch, cancellation, or restart from
  `dispatch_started` produces a terminal quarantine and zero later calls.
- `max_retries > 0`, invalid JSON, and observed provider-response errors still produce
  at most one call and never invoke the legacy corrective path.
- Mutating provider configuration, pinned prompt, request context, role contract,
  acceptance specification, policy/lease/redaction binding, slot, budget, reservation,
  or store event fails before a new dispatch or blocks the mission.
- Reservations are atomic, cannot exceed mission/per-episode bounds, remain held after
  failure/ambiguity, and reject a later call when exhausted.
- Secret sentinels in selected model output are redacted before durable role adoption;
  prior context containing a configured unredacted secret is rejected before network
  access; raw prompt/response/API-key values and the effective configured provider
  endpoint URL are absent from state and ledger evidence.  Unrelated caller URLs remain
  a redaction-policy residual.
- Independent Curator reproduced the focused tests and inspected the unchanged legacy
  retrying path.  An independent Judge challenged crash ordering, concurrent dispatch,
  state tampering, budget accounting, migration/rollback, and every
  non-authentication/non-isolation claim.  Both dispositions are `adapt` only for the
  stated local lane.

## Deferred obligations

Model-backed `RepositoryMission` lifecycle resumption, durable capability-effect receipt
rehydration, a closed multi-specification-set binding, provider request idempotency and
outcome lookup, provider/result authentication, external leases/budgets, immutable
external retention, source authorship, credential isolation, hostile-code containment,
and governance/branch-protection changes remain separate obligations.
