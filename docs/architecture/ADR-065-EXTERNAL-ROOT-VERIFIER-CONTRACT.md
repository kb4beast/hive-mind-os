# ADR-065: External-root verifier integration contract

## Status

Implemented local integration contract; external custody, deployment, and independent review
remain blocked. This ADR is deliberately not a root-authority promotion.

## Context

`AuthorityRegistry.mint_root` records a process-local ceremony. Its issuer string and digest
make the record inspectable but do not authenticate the party that asserted it. The authority
successor DAG therefore requires a verifier operated outside the agent process, with owner
custody, revocation, rotation, and deployment evidence.

The system needs a replaceable boundary now so an owner-operated verifier can be integrated
without rewriting the kernel. The court's advocate favoured an explicit attestation/verifier
protocol; the cross-examiner rejected treating an injected Python double, self-generated key,
or digest as external authority. The resulting contract records verifier evidence but reserves
the question of whether a real operator and custody system exist for `ROOT-3000`.

## Decision

- `ExternalRootAttestation` seals the envelope digest, owner issuer/reference, issuance time,
  and expiry. It contains no private key and is explicitly not a signature.
- `ExternalRootVerifier` is an injected protocol with an identity and a method that returns a
  sealed `ExternalRootVerification` tied to that exact attestation and a receipt reference.
- `AuthorityRegistry.admit_external_root` fails closed unless the attestation binds the exact
  root envelope, the configured verifier returns an accepted matching verification, and the
  verification time falls within the attestation validity window.
- The registry preserves that attestation/verification evidence separately from ordinary
  `RootProvenance`; `require_external_root` refuses an ordinary local mint, a revoked root,
  missing evidence, or an expired attestation.
- The protocol is not automatically wired into GitHub delivery. That production transition
  requires the owner-controlled verifier deployment, external witness, and the later Judge.

## Threats and retained limits

| Threat | Local control | Still open |
| --- | --- | --- |
| Self-issued local root called external | `require_external_root` rejects `mint_root` records | A process attacker can still alter local code or inject a fixture verifier |
| Wrong envelope/issuer/reference | Attestation and verification bind exact sealed claims | Real verifier must authenticate the owner and validate its own policy |
| Expired/revoked authority used later | Validity-window and live-registry checks fail closed | Real revocation propagation and clock source require deployment evidence |
| Provider lock-in | Narrow replaceable protocol | No real provider, key custody system, or transport is selected here |
| Evidence claimed as a signature | ADR and types distinguish digests from signatures | Owner/operator must provide a cryptographic trust and custody record |

## Acceptance evidence

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_brain_kernel_authority -v
```

The suite covers local-root rejection, accepted evidence binding, mismatched attestation refusal
before a verifier call, rejected/misattributed verifier output, expiration, and revocation. Test
doubles are protocol fixtures only and are not accepted as operator evidence.

## Rollback

Revert the integration-contract commit as an atomic local candidate while retaining all test and
decision evidence. Do not replace it with a local key or HMAC workaround. Existing ordinary
local roots remain explicitly local either way.
