# Curator receipt: CONTINUATION-CURATOR-3070 (repaired candidate)

## Identity and exact binding

- Curator identity: independent of the Builder.
- Source candidate: `1aa731f58b2d97eae65782b2d79685cefd2ae333`
- Source tree: `7762abb323b8e108036a5ba20cfac1353d115041`
- Builder receipt commit: `fb773cf3688e8db5e8cf087961c4e3821b28dcd6`
- Builder receipt: `evidence/audits/authority-hardening-successor/builder/CONTINUATION-3060-REPAIR-1aa731f.md`.
- The Builder-receipt commit changes only that receipt; launcher, controller,
  tests, ADR, and successor plan are identical to the source candidate. Audit
  began with a clean worktree.

## Curator disposition

**ADOPT — scoped local repair for `CONTINUATION-3060`, pending the distinct
`CONTINUATION-JUDGE-3960` disposition and the node's outstanding exact-head full
repository CI evidence.**

The prior Curator dissent is reproduced as repaired:

1. The launcher accepts only `-Apply`; it derives its root from its own
   `$PSScriptRoot`, verifies the Git top-level, has no `RepoRoot` or `Actor`
   parameter, and uses the constant `autopilot:preauthorized-continuation`
   provenance label.
2. It refuses a staged or unstaged modified `.autopilot/bin/autopilot.py` and
   reports the committed controller blob it invokes. The independently observed
   blob was `2a6e3b29b327f2824faff6b45018868f57a411f6`.
3. `run_orchestration` now returns structured `release_publication` evidence.
   A real stale `-Apply` invocation returned `WITHHELD`, `published: false`, a
   typed `CONTINUATION WITHHELD` result, and exit code `3`; no dispatcher release
   or workspace change occurred.

This adoption is solely a local continuation-interface result. It makes no
external-root, raw-delivery, protected-merge, deployment, credential, spending,
policy-mutation, `ROOT-3000`, or `PROMOTION-3990` claim.

## Independent reproduction

| Command or probe | Result |
| --- | --- |
| `git diff --no-ext-diff --check 1aa731f^ 1aa731f` | PASS — no whitespace error. |
| `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest tests.test_preauthorized_continuation tests.test_brain_kernel_authority tests.test_autopilot_workflow -v` | PASS — 42 tests, 1 Windows symlink-capability skip. This includes runtime rejection of `-RepoRoot` and `-Actor`. |
| `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest discover -s .autopilot/tests -p test_orchestration.py -v` | PASS — 26 tests, 1 Windows symlink-capability skip. This includes both `PUBLISHED` and `WITHHELD` publication-contract cases. |
| `python -m ruff check tests/test_preauthorized_continuation.py .autopilot/bin/autopilot.py .autopilot/tests/test_orchestration.py` | PASS. |
| PowerShell AST parse of `scripts/Invoke-PreauthorizedContinuation.ps1` | PASS — zero parser errors. |
| Strict successor DAG lint | PASS — 0 errors, 0 warnings; one existing serial-in-level informational finding. |
| No-apply live probe | Exit `0`; JSON recorded `release_publication.requested: false`, `published: false`, `outcome: WITHHELD`, followed by `CONTINUATION INSPECTED`. |
| Stale `-Apply` live adverse probe | Exit `3`; JSON recorded `requested: true`, `published: false`, `outcome: WITHHELD`, then `CONTINUATION WITHHELD`. It reported stale target/reconciliation/snapshot evidence and made no worktree change. |
| Direct `-RepoRoot .` and `-Actor forged:actor` probes | Each rejected by PowerShell parameter binding with exit `1`, before launcher execution. |

Live probes inherited `PYTHONDONTWRITEBYTECODE=1`. `git status --porcelain`
before and after the no-apply, stale-apply, and foreign-parameter probes was
identical. The stale controller remains withheld rather than reused or published.

## Static authority audit

1. `scripts/Invoke-PreauthorizedContinuation.ps1:1-3` exposes only the
   `Apply` switch. Lines 17-28 resolve the launcher's repository and require that
   it is the Git top-level; lines 35-45 require a clean, committed controller.
2. Lines 49-64 create the fixed actor/request/argument array and invoke Python
   without shell interpolation. Review and focused static tests found no
   credentials, raw GitHub write, protected-ref, merge, deploy, execution-policy,
   spending, policy-mutation, or root-minting path.
3. `.autopilot/bin/autopilot.py:981-1001` publishes only after the existing
   `should_publish_release` gate and reports an explicit publication result.
   `scripts/Invoke-PreauthorizedContinuation.ps1:74-82` rejects a requested but
   un-published release with exit `3`.
4. `plan.json` now gives `CONTINUATION-3060` a Curator and a separate Judge path.
   It is deliberately outside `PROMOTION-3990`'s dependencies. ADR-066 retains
   the `ROOT-3000` external custody/verifier boundary.

## Retained dissent and evidence boundary

- A committed controller blob is local repository-integrity evidence, not an
  externally authenticated controller release or a root signature. The launcher
  also resolves `python` from the local execution environment. Those ordinary
  local-host trust assumptions are not converted into an external-authority claim.
- The live control plane was stale and no eligible wave existed, so an actual
  `PUBLISHED` release was not exercised against this repository. The positive
  publication path is covered by the focused orchestration suite; any production
  dispatch remains subject to its pre-existing reconciliation, eligibility, lease,
  scope, and safe-action gates.
- The Builder node requires `python -m unittest discover -s tests -v`; this
  Curator independently ran its scoped required suites and probes, not that full
  repository gate. An exact-head CI/full-suite receipt remains necessary before
  final Builder/Judge closure.

## Rollback and non-promotion

Revert the repair commits `383b01f` and `1aa731f` together with ADR-066, the
launcher, its tests, the orchestration publication contract, and the plan node if
this scope boundary regresses. Preserve the prior adverse Curator/Judge receipts,
this receipt, and the Builder repair receipt. `ROOT-3000` remains
`BLOCKED_EXTERNAL_AUTHORITY`; `PROMOTION-3990` remains blocked and untouched.
