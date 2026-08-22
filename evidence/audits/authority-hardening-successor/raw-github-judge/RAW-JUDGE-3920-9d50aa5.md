# RAW-JUDGE-3920 — exact-head local disposition

## Candidate and role boundary

- Candidate commit: `9d50aa58ab7e657062ff9085b9ae00bc2251a1e9`
- Candidate tree: `a66450206b93b8ee9ff7f5e60e81798ece87c965`
- Change range reviewed: `3196edf00cdbb8e52388b8a98afabc8bfb833cad..9d50aa58ab7e657062ff9085b9ae00bc2251a1e9`
- Judge identity: `local_judge_disposition`, separate from Builder, Curator, Architect, and Steward.

## Disposition

**ADOPT — RAW-GITHUB-2070's scoped local write-quarantine and effect-bound
workspace-push control.** This is an adoption of local refusal and routing behavior,
not an external-authority, credential-custody, or production-promotion verdict.

## Evidence reviewed and independently reproduced

- Reviewed ADR-064, the successor DAG, the Builder receipt, and independent
  `RAW-CURATOR-2970-9d50aa5` receipt. The Curator recorded 134 focused tests passing
  and four raw-delivery adversarial controls passing on this exact head.
- `git diff --check` over the stated range was clean. The strict successor DAG lint
  returned zero errors and zero warnings.
- Independently ran the four raw adverse controls on this exact head:

  ```powershell
  $env:PYTHONPATH='src'
  python -m unittest tests.test_github_adapter.GitHubAdapterTests.test_raw_write_entry_points_are_quarantined_before_any_io tests.test_github_adapter.WorkspacePushExecutorTests.test_direct_executor_call_is_refused_before_git_runs tests.test_github_adapter.WorkspacePushExecutorTests.test_unapproved_production_push_host_is_refused_before_git_runs tests.test_github_adapter.WorkspacePushExecutorTests.test_production_push_host_is_declared_to_the_effect_gateway -v
  ```

  Result: **4 passed, 0 failures/errors**.
- Independently verified Constitutional CI run
  [`32603059081`](https://github.com/kb4beast/hive-mind-os/actions/runs/32603059081)
  is `success` for this exact SHA. Its static/type, dependency/license, CodeQL,
  secret-scan, build/SBOM, and Python 3.11/3.12/3.14 plus Windows unit-test jobs
  all completed successfully.

## Adopted local finding

`GitHubClient.push_branch`, `open_draft_pr`, and `deliver` deny before credentials,
Git, HTTP, or delivery-file parsing. `WorkspacePushExecutor` refuses a direct call,
requires the active `github-push` effect invocation, rechecks immutable grant action
and branch scope, and refuses a production remote that does not exactly bind to the
granted GitHub repository. The controlled-delivery declaration includes the Git push
host in its gateway allowlist.

## Dissent, boundary, and rollback

- The context marker is an in-process control, not a cryptographic boundary. A party
  able to alter process code or reach private implementation is outside its claim.
- `allow_local_test_remote=True` remains a socket-free test fixture, not remote
  authorization. Read-only GitHub observations remain available.
- **ROOT-3000 remains outside and blocked.** Nothing here supplies an owner-operated
  verifier, key custody, rotation/revocation policy, deployment evidence, or an
  independent external witness.
- **PROMOTION-3990 remains outside and blocked.** This receipt cannot authorize real
  remote delivery or any full-authority claim.
- Roll back by reverting the raw-migration candidate series through
  `603494028ddf4ac002b0b8c7fb02fd9e8c44847a` (and its follow-up exact-head fix as
  applicable), while retaining this receipt, ADR-064, the Curator receipt, and all
  negative probes. Do not restore raw write methods as a compatibility fallback.
