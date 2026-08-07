# ADR-049: Verifiable Hive Kernel local authority gateway

## Status

Proposed Phase 5 candidate. It supplies no provider, network, Git, credential, or
external-effect capability.

## Decision

`AuthorityRegistry` validates registered constraint envelopes before issuing a
capability token. Missing, revoked, expired, broadening, action-denied, or out-of-scope
path requests fail closed. `EffectGateway` accepts only an intent bound exactly to that
token, dispatches only a locally registered callback, and returns the existing receipt
for a duplicate idempotency key. Unregistered adapters fail closed.

The gateway is intentionally callback-only: it does not register filesystem, process,
network, provider, Git, GitHub, memory, or promotion adapters in this phase. Protected
push, merge, and deploy actions are denied by the tested envelope fixture.

## Rollback

Remove the additive authority/gateway modules. No legacy path, old receipt, or external
system has been changed. Courtroom disposition remains open.
