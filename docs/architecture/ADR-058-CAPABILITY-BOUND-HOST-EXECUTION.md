# ADR-058: Capability-bound durable-task execution and singleton target authority

## Status

Adapted implementation candidate on the singleton release branch. Independent
Curator and security review are required before promotion.

## Context

ADR-057 defined host-neutral orchestration contracts, but review found that a JSON
contract alone did not execute its parallel wave, historical node `pr_target` values
could contradict the singleton release target, free-form terminal labels could be
forged, and a failed launch could regenerate the same unusable identity. Review also
found that clean tracked target Python establishes provenance, not execution trust.

## Court record and dispositions

- Advocate: adopt an executable host loop so parallelism, polling, recovery, and
  quiescence are product behavior rather than prompt convention.
- Cross-Examiner: reject target-controlled Python execution without an externally
  stored independent bundle pin; reject host events not bound to the creation
  capability; reject any task target other than the live singleton target.
- Expert: adapt deterministic launch identity into one durable node-delivery lifecycle
  with attempt-specific failed-retry lineage and host-side idempotency.
- Judge: **adapt** ADR-057 with the controls below; all unrelated duplicate receipts,
  protected targets, secret-like prompts, and unsafe fixes remain fail-closed.

## Decision

1. `.autopilot/bin/host_execution.py` executes a validated v1 orchestration contract
   through an injected adapter. It creates the complete parallel-safe wave before the
   first wait, capability-binds events and acknowledgements, resolves recoverable
   attention in the same task, polls to terminal state, and emits a typed blocker after
   bounded no-progress cycles.
2. The control-plane singleton branch is the only executable PR target. Historical
   plan targets remain fingerprinted provenance and are overlaid at runtime; generated
   tasks cannot inherit `main`.
3. A failed or cancelled host launch receives a new attempt-specific instruction ID
   carrying the prior released event as `retry_of`. Successful release remains an
   idempotency tombstone.
4. Quiescence requires no active host binding, claim, or global validation lease.
5. The portable wrapper executes an installed controller only after a distinct Curator
   pins the exact clean bundle outside the target repository. Missing or stale trust
   creates a durable independent-review task, not target-code execution.
6. Git subprocesses receive a narrow runtime/transport environment; proxy values are
   validated, Git config injection is rejected, and remote mutation accepts only the
   canonical configured remote name.
7. Generic in-authority software blockers spawn a bounded Steward repair task and can
   append an exact resolution plus retry action. The reusable recovery sequence and
   regression tests are checked in; repository-specific runtime details remain local.

## Threats, migration, and rollback

Host adapters can lie unless their capability is protected by the host boundary; the
executor therefore validates exact host/task/cursor/capability tuples but does not claim
cryptographic identity beyond that boundary. Existing plan fingerprints and receipts
remain unchanged. Rollback removes the host executor and policy fields, restores the
previous orchestration target derivation and trust behavior, and retains all append-only
runtime evidence.

## Acceptance evidence

Tests must prove create-before-wait parallelism, attention recovery, forged-event
rejection, active-resource quiescence denial, singleton target derivation, advisory
intent safety, external trust invalidation, attempt-specific retry lineage, narrow Git
environment behavior, exact duplicate-receipt repair, and generic blocker resolution.
