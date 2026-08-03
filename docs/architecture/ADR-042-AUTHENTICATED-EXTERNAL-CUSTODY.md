# ADR-042: Authenticated External Custody for Configurations and Receipts

- **Status:** Adapted for a bounded local integration after independent Curator and Judge review; not a production-authentication promotion
- **Date:** 2026-08-03
- **Originating requirement:** P1 correctness hardening, authenticated external receipt/configuration custody
- **Prior decisions:** ADR-003, ADR-007, ADR-011, ADR-014, ADR-040, ADR-041
- **Capability maturity:** externally verifiable envelope and strict opt-in enforcement; no configured production issuer or external retention

## Context

ADR-040 and ADR-041 deliberately distinguish canonical SHA-256 integrity from external
authentication. A privileged local actor can replace a configuration or receipt together
with every local digest and label. The existing trusted-root check proves only that a
particular local path contains the locally expected bytes.

The required next step is intentionally narrow. It must make a configuration or a
local tool receipt admissible only when an independently configured external signing
identity attests to its exact semantic bindings. It must not manufacture an issuer,
private key, role credential, provider-execution claim, external retention service, or
new repository/governance authority.

## Court record

- **Atomic claim:** A signed, public-key-verifiable custody envelope can bind an exact
  mission configuration or tool receipt to an external signer identity and trusted key
  history, while an unsigned local SHA-256 digest cannot.
- **Advocate:** Builder/Orchestrator implementation. A small detached envelope leaves
  `tool-receipt` v1 as the local observation and makes external custody explicit,
  versioned, independently re-verifiable, and replaceable.
- **Cross-examiner:** Independent Architect/Cross-Examiner reviewed the existing local
  receipt, sandbox, GitHub, and durable-store paths. It required asymmetric verification,
  a separately controlled root, semantic rebinding rather than a bare digest signature,
  append-only nonce admission, strict authenticated mode, keyset overlap/revocation, and
  explicit limits. Its disposition is `adapt` for this bounded tranche.
- **Expert testimony:** `cryptography==47.0.0` supplies the optional Ed25519 public-key
  verifier. Source: `https://pypi.org/project/cryptography/47.0.0/`, retrieved
  2026-08-03; source distribution SHA-256
  `9f8e55fe4e63613a5e1cc5819030f27b97742d720203a087802ce4ce9ceb52bb`;
  license `Apache-2.0 OR BSD-3-Clause`; upstream source
  `https://github.com/pyca/cryptography/tree/47.0.0`. It is a pinned optional
  `custody` extra, not a base dependency. The kernel uses no cryptographic private key.
- **Curator disposition:** `adapt`. Independent public-material reproduction covered the
  contracts, replay persistence, freshness/expiry, revocation monotonicity, safe
  append-only migration, strict reopened missions, and hostile stored-keyset mutation.
  It found no remaining bounded-tranche implementation blocker. It retains the explicit
  production, external-retention, local-time, and provider-execution dissent below.
- **Judge disposition:** `adapt`. Independent reproduction confirmed strict new and
  existing mission enforcement, receipt custody, durable attestation-ID/nonce replay
  admission, rotation/revocation, migration, and rejection of a direct hostile SQLite
  keyset rewrite. This ADR does not close B-GOV-02 or B-GOV-03 and cannot be used to
  claim an authenticated production provider.
- **Dissent:** An external service that signs a host-submitted receipt proves that it
  received/custodied that assertion. It does not by itself prove that the sandbox or
  provider executed the action. Provider credential mediation and authenticated role
  possession remain separate P15 obligations.

## Decision

1. Add `custody-keyset` and `custody-attestation` version-1 contracts. The old closed
   `tool-receipt` v1 remains the local observation; it is not extended with ambiguous
   optional authentication fields.
2. Use Ed25519 detached signatures over canonical JSON and a fixed domain/version prefix.
   Each signed attestation includes authority, signer identity and key ID, keyset sequence,
   algorithm, audience, issue/expiry timestamps, nonce, unique attestation ID, exact
   subject, and signature. An envelope binds either:
   - a configuration digest plus mission/state identity, repository, pin, risk, and
     normalized acceptance-specification-set digest; or
   - exact receipt bytes (by receipt-file digest), mission/state/action/actor/provider,
     policy decision, lease, local verifier, and action digest.
3. A pinned `TrustAnchor` verifies externally signed keysets. Keysets are strictly
   sequential and identify public signer keys, identities, validity windows, and active
   or revoked state. Current active keys may overlap for rotation; a later keyset rejects
   a retired/revoked key. Every persisted keyset and contiguous history is authenticated
   again against the pinned root before a stored public key can verify an attestation.
   Missing, stale, gapped, malformed, unsigned, rewritten, or cross-authority keysets
   fail closed.
4. `CustodyProvenanceStore` append-only records verified keysets and accepted envelopes.
   `(authority, key, nonce)` is durable and unique. Exact-byte revalidation for the same
   binding is idempotent; a different envelope reusing a nonce fails, including after a
   restart. This is local durable provenance, not a claim of externally immutable
   retention.
5. `ExternalCustodyAdapter` is the only kernel-facing attestation interface. It takes an
   injected `CustodyAttestor` and a public verifier. It does not generate, load, log, or
   receive a production private key. A human-selected external issuer/service is required
   before use outside deterministic tests.
6. `MissionStore` schema version 3 adds a configuration-custody column. In
   `require_authenticated_custody=True` mode, mission registration and later reads reject
   missing or invalid signed configuration. `RepositoryMission` refuses to materialize a
   strict durable mission without an external custody adapter, attests every local receipt,
   and re-verifies receipt custody before its evidence is accepted or published.
7. Default legacy operation is explicitly **unattested local**. It remains available only
   for the prior local/reversible contract and must not be described as authenticated.
   The current CLI has no configured external issuer/trust root, so it remains in that
   local mode rather than silently simulating external custody.

## Threat model and controls

| Threat | Control | Residual / boundary |
|---|---|---|
| Local state and SHA-256 digests are recomputed after tampering | Externally identified Ed25519 signer attests exact semantic subject and raw receipt digest | A compromised issuer can attest false claims |
| Attestation is moved to another mission/action/policy/lease | Exact complete subject comparison before signature admission | A signed predicate may still be semantically insufficient |
| Signature is changed, self-issued, unknown, or algorithm-downgraded | Fixed Ed25519 algorithm/audience, anchor/keyset verification, external signer must differ from receipt actor | Role credential proof is not implemented |
| Key compromise, rotation, or revocation | Root-signed sequential keysets; overlap active keys; revocation rejects new attestations | Real revocation freshness depends on an externally supplied keyset |
| Host rewrites the local keyset cache to substitute an attacker public key | Re-authenticate each persisted keyset and contiguous sequence history with the pinned root before use | Host can erase or roll back local records; external retention/fresh supply remains P16 work |
| A previously valid envelope is replayed | Durable unique `(authority, key, nonce)` record; same bytes only are idempotent | Local provenance DB remains host-writable absent P16 |
| Expired or future assertion is admitted | RFC 3339 issue/expiry and key-validity-window checks | Time source is local until a trusted time authority is added |
| Failed execution loses evidence | Failed local receipt can be attested like success; result is bound in the receipt subject | Current scripted path needs its own issuer to attest failures |
| Host asks an external service to sign forged receipt bytes | ADR records custody-of-assertion, not authenticated provider execution | Complete provider mediation is separate P15 work |
| External branch controls are changed as part of hardening | No branch-protection/governance changes in this tranche | Existing governance posture is unchanged |

## Migration and rollback

- Mission stores migrate from versions 1/2 to version 3 additively. Existing
  configurations retain their original canonical digest but have no custody envelope and
  are `legacy-unattested` by implication.
- Strict authenticated mode cannot register, open, or resume an unsigned legacy mission.
  Operators must obtain a new external configuration attestation and enqueue a new mission;
  no local auto-upgrade exists.
- The retained configuration envelope, keysets, nonce records, raw receipts, failed
  attempts, and old local state are never deleted by migration or rollback.
- Existing custody-provenance stores add authority-scoped `attestation_id` admission by
  a transactional backfill that temporarily replaces and then restores the append-only
  update trigger. A malformed legacy envelope or conflicting ID fails migration closed.
- If the adapter must be disabled, strict mode fails closed before configuration use or
  delivery publication. Reverting code must not turn a strict mission into an accepted
  local one. A non-strict legacy run remains labeled local and is not rollback evidence
  for authenticated custody.

## Verification

- `tests/test_custody.py`: public-key configuration/receipt binding; altered bytes,
  self-issuance, expiry, stale keyset, revocation/reactivation, conflicting nonce or
  attestation ID, restart replay, malformed legacy migration, hostile local keyset
  rewrite, and unsigned strict restart all reject. Rotation overlap succeeds; strict
  mission-store configuration custody, successful delivery, and preserved failed-run
  evidence custody every local receipt.
- `tests/test_contracts.py`: the new contracts are strict Draft 2020-12 catalog entries.
- Existing focused mission-store and repository-delivery tests reproduce local durability
  and delivery behavior without downgrading the legacy label.
- Static type checking, Ruff, compilation, and diff checks remain required before
  promotion. An independent Curator/Judge must repeat the candidate tests with no signing
  secret and record their separate disposition.

## Deferred, distinct tranches

This decision does not authenticate source/repository custody or remote locks; resume
model-backed role turns; hard-isolate hostile code and credentials; mediate provider calls;
provide external immutable retention; or alter branch protection/governance. Those stay
separate to keep authority, threat model, migration, rollback, and evidence burdens clear.
