# Builder receipt: RAW-GITHUB-2070 and ROOT-INTERFACE-3010

## Candidate binding

- Candidate commit: `603494028ddf4ac002b0b8c7fb02fd9e8c44847a`
- Candidate tree: `572fd857cefdd217d97dae8c8db7b3565a54213b`
- Branch: `codex/authority-hardening-successor`
- Builder disposition: implementation complete; no local adoption or promotion claim.

## Implemented controls

1. The public raw GitHub write methods `push_branch`, `open_draft_pr`, and
   `deliver` reject with `GitHubRawWriteQuarantined` before credentials, Git,
   HTTP, or delivery-file parsing.
2. The production `WorkspacePushExecutor` no longer delegates to that raw
   client. It requires a live `github-push` effect invocation, a sealed
   `DeliveryGrant`, exact action and branch scope, an explicit credential, and
   the matching `https://github.com/<owner>/<repository>.git` production remote.
3. `EffectGateway` and `DurableEffectOutbox` install and clear the narrowly
   scoped execution marker only around an already capability-validated adapter
   invocation. This preserves durable recovery while rejecting a direct
   workspace-push call.
4. The kernel now records an injected external-root attestation and verifier
   result separately from local root provenance. It rejects local mints,
   mismatches, rejected or misattributed output, expiry, and revocation when an
   external root is required.

## Validation on the exact candidate

| Check | Result |
| --- | --- |
| `PYTHONPATH=src python -m unittest tests.test_brain_kernel_authority tests.test_delivery_grants tests.test_hive_cortex_effects tests.test_hive_cortex_delivery tests.test_github_adapter -v` | PASS — 134 focused tests |
| `PYTHONPATH=src python -m unittest discover -s tests -v` | PASS — 1,108 tests; 7 platform-limited skips; 987.660 seconds |
| `python .autopilot/bin/autopilot.py --repo-root . dag-lint --plan docs/plan/authority-hardening-successor-2026-08-22/plan.json --strict --json` | PASS — 0 errors, 0 warnings |
| `git diff --check` and clean candidate worktree check | PASS |

The complete suite emitted existing legacy resource/deprecation warnings, but
reported no test failures or errors. The skips are Windows environment limits
for creating symbolic links, not skipped successor assertions.

## Required independent next steps

- `RAW-CURATOR-2970` must independently reproduce the raw-write, no-I/O,
  grant/remote binding, effect-context, host-allowlist, and recovery claims.
- `ROOT-CURATOR-3020` must independently reproduce the local no-claim and
  verifier-evidence behavior, explicitly distinguishing test doubles from
  external custody.
- `RAW-JUDGE-3920` and `ROOT-JUDGE-3930` remain separate dispositions.
- `ROOT-3000` remains blocked until an owner-controlled external verifier and
  independent security witness provide real custody, rotation, revocation,
  deployment, and rollback evidence. No local process key, fixture verifier,
  issuer string, or hash satisfies that obligation.

## Rollback

Revert candidate `6034940` as one unit if independent review finds a reachable
raw side-effect path or a verifier-evidence binding error. Preserve this receipt,
the ADRs, tests, and dissent; do not re-enable raw GitHub writes as a fallback.
