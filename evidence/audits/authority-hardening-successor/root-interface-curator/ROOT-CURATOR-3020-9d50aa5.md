# ROOT-CURATOR-3020 — independent Curator receipt

## Exact candidate

- Role: Curator, independent of the Builder receipt for this candidate.
- Candidate commit: `9d50aa58ab7e657062ff9085b9ae00bc2251a1e9`.
- Candidate tree: `a66450206b93b8ee9ff7f5e60e81798ece87c965`.
- Branch: `codex/authority-hardening-successor`.
- Audit start state: tracked worktree clean. This receipt is the only audit write.
- Change range reviewed: `3196edf..9d50aa5`, including
  `src/hive_mind_os/brain_kernel/authority.py`, its authority tests, ADR-065, the
  successor DAG, and the Builder receipt. `git diff --check` was clean; successor
  `dag-lint --strict` returned zero errors and warnings.

## Independent reproduction

| Command | Result |
| --- | --- |
| `PYTHONPATH=src python -m unittest tests.test_brain_kernel_authority tests.test_delivery_grants tests.test_hive_cortex_effects tests.test_hive_cortex_delivery tests.test_github_adapter -q` | PASS — 134 tests, 0 failures/errors, 19.096 seconds. |
| `PYTHONPATH=src python -m unittest -v tests.test_brain_kernel_authority.ExternalRootIntegrationTests` | PASS — 5 tests: local-root refusal; exact accepted binding; mismatch before verifier invocation; rejected/misattributed/invalid-time verifier output; expiry and revocation refusal. |

## Findings

1. `ExternalRootAttestation` and `ExternalRootVerification` seal their exact claims
   and validate RFC 3339 validity fields (`src/hive_mind_os/brain_kernel/authority.py:93-225`).
   The code and ADR-065 correctly state that these digests are not signatures.
2. `AuthorityRegistry.admit_external_root` refuses a non-root, unsealed or
   mismatched attestation before calling the verifier; then it requires a configured
   verifier, matching accepted sealed output, and a verification time inside the
   attestation window (`authority.py:296-367`). The mismatch-before-call and
   rejected/misattributed/time-invalid tests passed.
3. `require_external_root` distinguishes ordinary local `mint_root` provenance from
   separately recorded verifier evidence and fails closed for missing, expired, or
   revoked evidence (`authority.py:379-395` and following). The local-mint,
   expiration, and revocation tests passed.

## Court disposition

**ADOPT — local ROOT-INTERFACE-3010 integration contract only, subject to the
separate `ROOT-JUDGE-3930` disposition.** The contract is internally coherent and
the stated negative cases reproduce at the exact candidate.

## Dissent and explicit non-external-root conclusion

**No external verifier, owner custody, signing authority, deployment, rotation,
revocation propagation, or independent operator witness was observed.** The tested
verifier is the in-process `_FixtureExternalRootVerifier` in
`tests/test_brain_kernel_authority.py`; it is a protocol double, not external evidence.
`receipt_ref` is a bound non-empty reference, not a Curator-verified external receipt.
A process attacker can supply a fixture verifier or alter local code. Therefore this
receipt does not satisfy, advance, or promote `ROOT-3000`.

## Rollback

If later integration evidence conflicts with the bound fields or validity rules,
revert the local contract as a candidate while preserving this receipt and the
external-root blocker. Do not substitute a process-local key, HMAC, issuer string,
or digest for the missing owner-operated verifier.

## Evidence boundary

I did not independently repeat the successor DAG's full `unittest discover` command.
The prior Builder receipt reports a full run at the implementation commit and current
remote CI success was supplied only as supplemental context. This focused Curator
receipt establishes the exact-head local contract behavior, but it is not a substitute
for the exact-head full-suite/CI receipt required before the later Judge disposition.
