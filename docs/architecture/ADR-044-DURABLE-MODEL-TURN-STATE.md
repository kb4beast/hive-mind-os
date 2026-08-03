# ADR-044: Durable, Fail-Closed Model-Turn Role State

- **Status:** Adapted bounded local implementation after independent Curator and Judge review
- **Date:** 2026-08-03
- **Prior decisions:** ADR-011, ADR-040, ADR-041, ADR-042, ADR-043
- **Scope:** reusable model-turn planning, result adoption, recovery, and provenance.
  The original implementation made no live-path change; ADR-046 subsequently adopts it
  only through a separate opt-in, one-shot model-role executor.  Legacy `ModelBackend`,
  `RepositoryMission`, provider transport, credentials, and authority remain unchanged.

## Context

The current model backend emits append-only in-process call evidence, but its role turn
is not a durable recovery unit.  Retrying after a crash or network timeout can issue the
same semantic request twice while the provider outcome is unknown.  Existing SHA-256
digests bind local bytes but do **not** authenticate a provider, a model, its response,
or a host that can alter local storage.

The external provider-identity/result-authentication source, provider idempotency
contract, and a trusted external result witness are unavailable in this worktree.  They
must not be invented.  This ADR therefore limits the implementation to a durable,
replaceable local state adapter that refuses to replay an ambiguous turn.

## Court record

- **Advocate (Builder):** make one provider invocation a deterministic logical turn,
  seal it before dispatch, retain bounded non-secret result provenance, and let a later
  process resume from durable state rather than hidden reasoning.
- **Cross-examiner (architecture review):** fail closed after any unobserved provider
  outcome; avoid storing prompts, responses, credentials, arbitrary provider errors, or
  mutable current-state rows; do not imply that response digests authenticate a
  provider.
- **Expert testimony:** local append-only state can make the local recovery decision
  inspectable, but cannot prove that a remote provider did or did not perform an
  invocation.  An interrupted or timeout-exposed invocation therefore remains
  ambiguous without external reconciliation.
- **Curator disposition:** `adapt` after independent reproduction of 35 focused checks
  across state, contract, and model-backend suites, sealed-input mutation probes,
  successful digest-only/tampered-state failure closure, and configured-secret
  admission/reopen checks. The verdict applies only to the reusable local primitive.
- **Judge disposition:** `adapt` after independently reproducing 24 direct state/contract
  tests, transition/tamper/redaction probes, and confirming no live model/mission wiring.
  A two-store dispatch race produced one durable dispatch start and one fail-closed
  conflict; the adapter normalizes that conflict and retains a regression.
- **Dissent / blocking evidence:** neither model/provider authenticity nor provider
  idempotency is established.  The adapter must not be used as a production promotion,
  delivery authorization, or a substitute for hard credential/process isolation.

## Decision

1. `model-turn-plan`, `model-turn-result`, and `model-role-result` are strict typed
   contracts. A plan binds one mission/state, registered role, work item, bounded
   provider selector, prompt/request digests, sealed acceptance-specification, role
   contract/configuration/selection, policy/lease, and redaction-policy bindings. A
   response observation carries a response digest, outcome, optional parsed-result
   digest, bounded token counts, and retry index. A successful role may additionally
   retain a bounded canonical, caller-redacted result needed to rehydrate downstream
   role context. Unknown fields, raw prompt/response, API key, endpoint URL, and
   free-form provider errors are rejected.
2. The `MTURN-<sha256>` logical ID is deterministically derived from the complete
   canonical plan.  It is a stable local idempotency/replay key, not authentication.
   A changed plan cannot reuse it.
3. `ModelTurnStore` requires a filesystem-backed SQLite database by default. Plans
   and state events are append-only with database update/delete triggers. Stored event
   sequences reconstruct `planned`, `dispatch_started`, `completed`, or `ambiguous`;
   there is no mutable "current outcome" row to silently rewrite. A completed response
   may be atomically bound to a matching selected role-result artifact, which rehydrates
   an exact `AgentResult` shape for later local context; digest-only failed/invalid
   results deliberately do not pretend to be resumable role state.
4. A caller persists `dispatch_started` immediately before invoking a provider.  Only
   a response-observed, contract-valid result may transition the turn to `completed`.
   A timeout, interruption, response-loss, duplicate/disputed outcome, or any other
   uncertainty must call `mark_ambiguous` (or is marked by `recover`).  An ambiguous
   logical turn cannot dispatch again or adopt a result.  A new, separately planned
   logical turn requires explicit higher-layer authority.
5. This remains deliberately separate from the existing raw `ModelBackend` retry loop.
   ADR-046 provides a bounded opt-in caller that uses one `complete_once` call and local
   quarantine; it does not add provider idempotency/result reconciliation, repository
   role acceptance state, external leases, or credential/hostile-code isolation.

## Threat model and residuals

| Threat | Control | Residual / non-claim |
|---|---|---|
| Crash after sending a provider request | `dispatch_started` then recovery quarantine | Does not determine whether the provider executed the request |
| Network timeout / response loss | Explicit `ambiguous` terminal state prevents replay | The caller must honestly classify uncertainty; no provider witness exists |
| Same logical id bound to another prompt/request | Deterministic id re-derivation and exact-plan idempotency checks | SHA-256 is local integrity only |
| Stored state rewritten or deleted by an ordinary API path | Append-only tables, triggers, contiguous event reconstruction | A hostile host with SQLite access can deny service or alter all local records; this is not authentication |
| Prompt, response, credential, or verbose error leaked into state | Closed contracts retain identifiers/digests/counts plus only the selected, bounded role result after caller-supplied secret redaction | Unknown secrets or a dishonest/incomplete redaction policy remain a host/caller risk |
| A completed turn silently repeats | Exactly one dispatch transition and one terminal transition | Higher-layer replacement/new-turn authority remains unresolved |
| Provider or model impersonation | No local digest is promoted to provider identity | External authentication, provider receipts, key custody, and TLS/root trust are separate obligations |

## Migration and rollback

- This adapter is additive and has no backfill.  Existing model-call ledger entries
  remain historical local evidence, not durable logical-turn state.  A caller adopts by
  creating a filesystem-backed store, registering a typed plan, and persisting the
  dispatch transition before its own provider call.
- Recovery is objective: `planned` may be dispatched; `dispatch_started` becomes
  `ambiguous`; `completed` and `ambiguous` are terminal.  No historical plan can be
  silently recast as a successful result.
- Rollback removes only a future caller integration.  It never deletes the append-only
  database, and it restores weaker non-resumable behavior; it cannot preserve a claim
  of durable fail-closed recovery.

## Acceptance and validation

- `tests/test_model_turn_state.py` covers deterministic plan binding, durable reopen and
  selected-result rehydration, append-only/idempotent registration, response/result and
  plan-binding rejection, timeout ambiguity quarantine, interruption recovery, strict
  contracts, memory-store rejection, local digest/kind tamper detection, and configured
  secret redaction without raw prompt/response persistence.
- `tests/test_contracts.py` validates catalog inclusion and strict schemas.
- The original independent Curator and Judge verified that no live model path was
  silently changed.  ADR-046 requires separate Curator and Judge evidence for its
  opt-in execution adapter; it cannot retroactively widen this primitive's verdict.

## Deferred obligations

Provider authentication, externally witnessed outcomes, provider idempotency keys and
reconciliation APIs, Model-backed `RepositoryMission` adoption, multi-specification
binding, external lease/budget authority, actual acceptance execution, hard hostile-code
and credential isolation, external immutable retention, protection against incomplete
caller redaction, and production recovery operations remain separate evidence
obligations. ADR-046's local single-call reservation does not resolve those gaps. This
ADR does not alter source custody, external branch protection, or governance.
