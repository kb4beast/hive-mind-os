# ROOT-JUDGE-3930 — exact-head local disposition

## Candidate and role boundary

- Candidate commit: `9d50aa58ab7e657062ff9085b9ae00bc2251a1e9`
- Candidate tree: `a66450206b93b8ee9ff7f5e60e81798ece87c965`
- Change range reviewed: `3196edf00cdbb8e52388b8a98afabc8bfb833cad..9d50aa58ab7e657062ff9085b9ae00bc2251a1e9`
- Judge identity: `local_judge_disposition`, separate from Builder, Curator, Architect, and Steward.

## Disposition

**ADOPT — ROOT-INTERFACE-3010's scoped local verifier-integration contract.** The
contract is adopted only as a fail-closed, replaceable interface. It is not an
adoption of an external root, owner authentication, signing authority, or deployment.

## Evidence reviewed and independently reproduced

- Reviewed ADR-065, the successor DAG, the Builder receipt, and independent
  `ROOT-CURATOR-3020-9d50aa5` receipt. The Curator recorded 134 focused tests and
  five exact-head root-interface adversarial tests passing, while expressly finding
  no external verifier or custody evidence.
- `git diff --check` over the stated range was clean. The strict successor DAG lint
  returned zero errors and zero warnings.
- Independently ran the exact-head root-interface suite together with the raw
  controls needed to ensure the two successor verdicts remain bounded:

  ```powershell
  $env:PYTHONPATH='src'
  python -m unittest tests.test_brain_kernel_authority.ExternalRootIntegrationTests tests.test_github_adapter.GitHubAdapterTests.test_raw_write_entry_points_are_quarantined_before_any_io tests.test_github_adapter.WorkspacePushExecutorTests.test_direct_executor_call_is_refused_before_git_runs tests.test_github_adapter.WorkspacePushExecutorTests.test_unapproved_production_push_host_is_refused_before_git_runs tests.test_github_adapter.WorkspacePushExecutorTests.test_production_push_host_is_declared_to_the_effect_gateway -v
  ```

  Result: **9 passed, 0 failures/errors**.
- Independently verified Constitutional CI run
  [`32603059081`](https://github.com/kb4beast/hive-mind-os/actions/runs/32603059081)
  is `success` for this exact SHA, including static/type, security, dependency, and
  multi-version/unit-test jobs.

## Adopted local finding

The `ExternalRootAttestation` and `ExternalRootVerification` records seal their
declared fields but do not call those seals signatures. `AuthorityRegistry` rejects
ordinary local mint provenance as external evidence, requires an injected verifier
to return accepted, exact-bound, validity-window-conforming evidence, and refuses
missing, expired, rejected, misattributed, or revoked evidence via
`require_external_root`.

## Dissent, boundary, and rollback

- The verified object in tests is an in-process fixture. `receipt_ref` is merely a
  bound reference; it is not a judicially verified external receipt.
- No external verifier, owner-controlled key custody, signing implementation,
  deployment target, rotation/revocation propagation, clock authority, or independent
  operator witness was supplied or observed. Process code can still inject a fixture
  verifier or alter this local contract.
- **ROOT-3000 remains outside and blocked.** This receipt does not satisfy or advance
  its owner-operated custody/deployment obligation.
- **PROMOTION-3990 remains outside and blocked.** Neither this interface nor the
  matching raw-write verdict authorizes real remote delivery or a full-authority claim.
- Roll back by reverting the root-interface candidate series through
  `603494028ddf4ac002b0b8c7fb02fd9e8c44847a` (and its follow-up exact-head fix as
  applicable), while retaining this receipt, ADR-065, the Curator receipt, and all
  negative findings. Never substitute a process-local key, HMAC, issuer string, or
  digest for the missing owner-operated verifier.
