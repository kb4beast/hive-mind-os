# P15 — Authenticated Identities and Provider Receipts

> **Withdrawn as an executable phase by P5.2 (2026-08-03).** Do not schedule this
> work. Its required external authority is retained in
> [Human Authority Gates](../architecture/HUMAN_AUTHORITY_GATES.md).

Status: withdrawn | Historical dependency: P14

## 1. Objective

Close `B-GOV-02` and `B-GOV-03` by requiring non-self-issued, revocable identities for
material roles and cryptographically bound, completely mediated provider execution receipts.

## 2. Required reading

1. `docs/plan/01_POST_P13_OVERVIEW.md`
2. `docs/plan/P08_CURATOR_INDEPENDENCE.md`
3. `docs/architecture/ADR-012-BLIND-FIRST-CURATOR-INDEPENDENCE.md`
4. `docs/plan/P14_REAL_PROVIDER_CAPABILITY_APPEAL.md`
5. `docs/plan/BLOCKERS.md` (`B-GOV-02`, `B-GOV-03`)

## 3. Prerequisites and authority

- Branch: `phase/P15-authenticated-identity-receipts`.
- P14 has a permitted real-provider mission.
- A human selects an external issuer/trust root and controls credential issuance,
  revocation, and rotation outside agent authority.
- Test credentials are isolated from production credentials; no private key is committed.

## 4. Scope and design constraints

- Add replaceable identity-verifier and receipt-authenticator interfaces.
- Bind issuer, subject, role, mission, action, provider, request/response digests, policy,
  allowance/lease, timestamps, nonce, and verifier to signed envelopes.
- Require distinct authenticated Builder and Curator subjects at applicable burdens.
- Mediate every provider call through one enforceable boundary; direct/bypass calls fail.
- Verify trust chain, algorithm policy, audience, expiry, revocation, replay, and role binding.
- Keep structural P08 independence; cryptography supplements rather than replaces it.
- Signing never grants capability, money, deployment, or policy authority.

## 5. Deliverables

- ADR for the chosen replaceable identity and receipt envelope.
- Identity, signing, verification, revocation, replay, and mediation adapters.
- Schemas and migration/versioning rules for signed evidence.
- Offline test issuer and deterministic cryptographic fixtures; optional runtime dependency
  must be isolated behind an extra and justified by ADR.
- P15 audit, threat model, key-rotation/recovery runbook, and court record.

## 6. Required tests

Reject unsigned, self-issued, unknown-issuer, wrong-role, expired, not-yet-valid, revoked,
replayed, altered, wrong-audience, wrong-mission, wrong-policy, wrong-lease, and bypassed
evidence. Prove keys and secrets never appear in receipts or errors. Prove rotation accepts
valid overlap and rejects retired keys. Prove provider failure still produces an authenticated
failure receipt.

## 7. Exit criteria

- Full deterministic gates pass.
- Independent verification reproduces the chain without access to signing secrets.
- Builder cannot verify itself as Curator; agents cannot issue or extend their own identity.
- Every provider action is mediated and authenticated; bypass attempts fail closed.
- Revocation, rotation, replay, tamper, outage, and recovery tests pass.
- Separate Curator, Judge, and Orchestrator dispositions permit the exact candidate.

## 8. Evidence, rollback, and forbidden shortcuts

Retain public trust material, signed test receipts, revocation/rotation events, threat tests,
adverse attempts, audit, and dissent. Rollback disables authenticated operation fail-closed;
it must not silently accept unsigned legacy evidence.

Do not treat role strings, shared API keys, TLS, repository accounts, or locally generated
self-signed keys as authenticated independence.
