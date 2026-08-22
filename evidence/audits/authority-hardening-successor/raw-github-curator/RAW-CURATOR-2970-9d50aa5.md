# RAW-CURATOR-2970 — independent Curator receipt

## Exact candidate

- Role: Curator, independent of the Builder receipt for this candidate.
- Candidate commit: `9d50aa58ab7e657062ff9085b9ae00bc2251a1e9`.
- Candidate tree: `a66450206b93b8ee9ff7f5e60e81798ece87c965`.
- Branch: `codex/authority-hardening-successor`.
- Audit start state: tracked worktree clean. This receipt is the only audit write.
- Change range reviewed: `3196edf..9d50aa5`; source, tests, successor DAG, ADR-063,
  ADR-064, ADR-065, and the prior Builder receipt were inspected. `git diff --check`
  was clean. The successor `dag-lint --strict` returned zero errors and warnings.

## Independent reproduction

| Command | Result |
| --- | --- |
| `PYTHONPATH=src python -m unittest tests.test_brain_kernel_authority tests.test_delivery_grants tests.test_hive_cortex_effects tests.test_hive_cortex_delivery tests.test_github_adapter -q` | PASS — 134 tests, 0 failures/errors, 19.096 seconds. |
| `PYTHONPATH=src python -m unittest -v tests.test_github_adapter.GitHubAdapterTests.test_raw_write_entry_points_are_quarantined_before_any_io tests.test_github_adapter.WorkspacePushExecutorTests.test_direct_executor_call_is_refused_before_git_runs tests.test_github_adapter.WorkspacePushExecutorTests.test_unapproved_production_push_host_is_refused_before_git_runs tests.test_github_adapter.WorkspacePushExecutorTests.test_production_push_host_is_declared_to_the_effect_gateway` | PASS — 4 raw-delivery adversarial controls. |

The focused run emitted an existing SQLite `ResourceWarning`, but no test failure or
error. I did not treat the Builder's reported remote CI result as a substitute for
these local reproductions.

## Findings

1. `GitHubClient.push_branch`, `open_draft_pr`, and `deliver` call the quarantine
   guard before credential lookup, Git, HTTP, or delivery-file parsing
   (`src/hive_mind_os/github_adapter.py:350-357,608-616,696-705,1268-1280`). The
   raw-write no-I/O adversarial test passed.
2. `WorkspacePushExecutor.push` checks immutable grant action and branch scope,
   requires the active `github-push` effect invocation, binds a production remote to
   the grant's exact GitHub repository, and only then reads the credential
   (`src/hive_mind_os/cortex/github/push_executor.py:60-108`). The direct-executor
   and wrong-host tests passed before Git ran.
3. The active invocation is installed only around an already capability-validated
   adapter call and is reset in `finally` (`src/hive_mind_os/brain_kernel/effects.py:49-80`).
   The focused suite also passed the registry-less gateway/outbox and controlled
   recovery regressions.
4. The controlled delivery host declaration includes the Git push host when a
   production HTTPS executor is configured; the dedicated host-declaration test
   passed.

## Court disposition

**ADOPT — local RAW-GITHUB-2070 migration control, subject to the separate
`RAW-JUDGE-3920` disposition.** The reproduced evidence supports the narrow claim:
the repository's raw public write entry points are quarantined, and the production
workspace executor refuses direct and grant/remote/context-invalid calls.

## Dissent and limits

- This is not a cryptographic boundary. Code running in the same process can alter
  code or deliberately reach private implementation details such as the context marker.
- `allow_local_test_remote=True` exists solely for socket-free tests; it is not a
  production remote authorization mechanism.
- Read-only `GitHubClient` observations remain available. No evidence here claims
  that an arbitrary external caller with independently obtained credentials is governed
  by an external root.
- `ROOT-3000`, external custody, deployment, and promotion were neither tested nor
  claimed. They remain blocked.

## Rollback

Retain this receipt and revert the migration candidate as a unit if a raw write path
is later shown reachable. Do not restore raw client writes as a compatibility fallback.

## Evidence boundary

I did not independently repeat the successor DAG's full `unittest discover` command.
The prior Builder receipt reports a full run at the implementation commit and current
remote CI success was supplied only as supplemental context. This focused Curator
receipt therefore supports the recorded local control disposition, but it is not a
substitute for the exact-head full-suite/CI receipt required before the later Judge
disposition.
