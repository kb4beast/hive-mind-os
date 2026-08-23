# Builder receipt: CONTINUATION-3060

## Candidate binding

- Candidate commit: `5de1d5706f01ce219f6d5e55198e2e4f8a23ceff`
- Candidate tree: `930952d65a1a0edc2596a879ac39adddf6cdf7a8`
- Branch: `codex/authority-hardening-successor`
- Builder disposition: local durable-continuation mechanism implemented; no root,
  promotion, or external-authority claim.

## Implemented controls

1. `Invoke-PreauthorizedContinuation.ps1` resolves the current repository and
   current Autopilot CLI before it constructs a fixed `orchestrate` request.
2. `-Apply` is opt-in, uses a PowerShell argument array rather than shell
   interpolation, and reaches only the pre-existing capability-gated dispatcher.
   Without `-Apply`, it is a live inspection.
3. The launcher has no caller-controlled command/request input, credential or
   registry access, execution-policy override, raw GitHub write, protected-ref,
   merge, deployment, policy, spending, or external-root path.
4. `AGENTS.md` makes a prior explicit owner continuation directive durable for
   its existing routine/reversible scope, while preserving separate authority for
   every new material scope.
5. ADR-066 records the migration away from the stale fixed-node recovery helper,
   rollback, and the retained `ROOT-3000` obligation.

## Validation on the exact candidate

| Check | Result |
| --- | --- |
| `python -m ruff check tests/test_preauthorized_continuation.py` | PASS |
| `PYTHONPATH=src python -m unittest tests.test_preauthorized_continuation tests.test_brain_kernel_authority tests.test_autopilot_workflow -v` | PASS — 39 tests; 1 Windows symlink-capability skip |
| PowerShell AST parse of `scripts/Invoke-PreauthorizedContinuation.ps1` | PASS — zero parser errors |
| `powershell -NoProfile -File scripts/Invoke-PreauthorizedContinuation.ps1` | PASS — live inspection returned the legacy controller's stale-release/quiescent typed state and requested no dispatcher release |
| `git diff --check` before sealing candidate | PASS |

The live inspection intentionally did not run `-Apply`: the current legacy
controller had no current eligible release. Its refusal is the expected fail-closed
result, not a reason to reuse the historic branch or bypass release controls.

## Required independent next steps

- A Curator must verify that the launcher cannot widen a durable owner directive
  into root, credential, or protected external authority.
- A separate Judge must decide whether the local continuation mechanism is adopted
  without treating it as a disposition of `ROOT-3000`.
- `ROOT-3000` remains blocked pending owner-controlled external verifier custody,
  rotation, revocation, deployment, rollback, and independent witness evidence.

## Rollback

Revert candidate `5de1d57` and this receipt together if the launcher can replay a
stale branch/node or reach a side-effect path outside the dispatcher. Preserve the
ADR, tests, and review dissent; do not restore the historic fixed-branch helper as a
fallback.
