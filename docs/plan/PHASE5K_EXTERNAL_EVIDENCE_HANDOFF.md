# Phase 5K external adoption evidence handoff

## Purpose

This handoff defines how a real external review result may be submitted for verification. It is not a
trust anchor, identity, signature, review result, adoption decision, or P14 authorization.

## Frozen repository context

- Repository: `kb4beast/hive-mind-os`
- Integration branch: `agent/phase5a-orchestrator-shadow`
- Phase 5J merge commit: `6c2e76b0e07c038724c39bebf4ab2ad8394e72a7`
- Phase 5J source head: `06b81ee7ae38da9c2050e92b16dfcb1fbc65a97d`
- Phase 5K branch: `agent/phase5k-external-adoption-evidence-intake`
- `main`, `release/version_1.1`, and PR #49 must not be modified

At submission time, record the exact Phase 5K PR head and tree. Any head movement invalidates the
submission binding and requires a new evidence package.

## Required external evidence

Supply one independently issued evidence object for each role:

1. Curator
2. Judge
3. Orchestrator

Every object must bind:

- participant identifier;
- role identifier;
- external issuer identifier;
- public key or verifiable key identifier;
- signature and signed-payload digest;
- repository and tenant;
- Phase 5J merge commit;
- packet head and tree;
- decision or recommendation;
- exact scope and evidence-index digests;
- issued and expiry timestamps;
- replay nonce;
- external append-only retention reference;
- revocation reference;
- conflict-of-interest disclosure; and
- authority reference.

The Judge decision must be exactly one of `adopt`, `adapt`, `reject`, `defer`, or `abstain`.

## Trust-anchor requirements

Trust anchors must originate outside agent control. They must identify the issuer, allowed roles,
verification method, key status, validity window, revocation mechanism, and external retention
boundary. A repository-local label, self-signed fixture, local digest, GitHub username alone, or
procedural role name is insufficient.

## Required rejection behavior

Reject evidence that is:

- self-issued or from an unknown issuer;
- unsigned or invalidly signed;
- replayed;
- expired or revoked;
- bound to another repository, tenant, commit, head, tree, packet, role, or scope;
- affected by an unresolved participant conflict;
- missing external append-only retention;
- incomplete; or
- based on an unsupported decision.

## Secret handling

Do not commit credentials, private keys, signing secrets, access tokens, private evidence bodies, or
retention-account secrets. Submit only public verification material and content-addressed references
needed for independent verification.

## Current status

Until external evidence and trust anchors are actually supplied and verified:

- evidence register: empty;
- verified roles: none;
- selected decision: none;
- signed decision present: false;
- ADR-015 adopted: false;
- P14 eligible: false;
- P20 eligible: false;
- release ready: false;
- production ready: false;
- deployment authorized: false;
- promotion eligible: false;
- superiority established: false;
- authority: none; and
- activation: inert.

## Submission checkpoint

The next executor must stop rather than invent any missing identity, signature, trust anchor,
retention reference, authority, timestamp, nonce, revocation record, conflict disclosure, or decision.
