# Builder repair receipt: CONTINUATION-3060

## Candidate binding

- Candidate commit: `1aa731f58b2d97eae65782b2d79685cefd2ae333`
- Candidate tree: `7762abb323b8e108036a5ba20cfac1353d115041`
- Branch: `codex/authority-hardening-successor`
- Prior adverse reviews retained: `CONTINUATION-CURATOR-3060-5de1d57` (**ADAPT**)
  and `CONTINUATION-JUDGE-3960-5de1d57` (**DEFER**).
- Builder disposition: repair complete pending exact-head full CI, independent
  Curator, and independent Judge. No promotion or external-authority claim.

## Repairs to the deferred candidate

1. The launcher now derives its only repository from its own `$PSScriptRoot`,
   normalizes and verifies the Git top-level, and accepts neither `RepoRoot` nor
   `Actor` input. The dispatcher actor is the fixed non-authorizing audit label
   `autopilot:preauthorized-continuation`.
2. It refuses a staged or modified `.autopilot/bin/autopilot.py` and records the
   committed controller blob it invokes. The original direction therefore cannot
   be replayed against an arbitrary local control plane.
3. The Autopilot orchestration contract records `release_publication` with
   explicit `requested`, `published`, and `PUBLISHED`/`WITHHELD` fields. The
   launcher exits `3` with `CONTINUATION WITHHELD` when `-Apply` did not publish
   a dispatcher release, rather than reporting a false success.
4. The successor DAG now includes `CONTINUATION-3060`, an independent Curator
   node, and an independent Judge node. Their states remain pending until this
   repaired candidate is independently examined.

## Validation on the exact candidate

| Check | Result |
| --- | --- |
| `python -m ruff check tests/test_preauthorized_continuation.py .autopilot/bin/autopilot.py .autopilot/tests/test_orchestration.py` | PASS |
| PowerShell AST parse | PASS — zero parser errors |
| `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest tests.test_preauthorized_continuation tests.test_brain_kernel_authority tests.test_autopilot_workflow -v` | PASS — 42 tests; 1 Windows symlink-capability skip |
| `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s .autopilot/tests -p test_orchestration.py -v` | PASS — 26 tests; 1 Windows symlink-capability skip |
| strict successor DAG lint | PASS — 0 errors, 0 warnings |
| `Invoke-PreauthorizedContinuation.ps1` | PASS — inspection-only live contract; no release requested |
| `Invoke-PreauthorizedContinuation.ps1 -Apply` | PASS adverse probe — exits `3`, emits `CONTINUATION WITHHELD`, reports stale target/reconciliation/snapshot evidence, and publishes no dispatcher release |

The live dispatcher is still an obsolete singleton release. The adverse `-Apply`
probe is expected to refuse; no historic branch, node, credential, or fallback path
was reused.

## Required independent next steps

- Run the full repository CI gate on this exact candidate.
- `CONTINUATION-CURATOR-3070` must independently reproduce the parameter denial,
  committed-controller binding, and stale `-Apply` non-success behavior.
- `CONTINUATION-JUDGE-3960` must issue a new exact-candidate disposition only
  after the Curator result and full CI evidence are available.
- `ROOT-3000` and `PROMOTION-3990` remain blocked and are not dependencies this
  local continuation repair may satisfy.

## Rollback

Revert `383b01f` and `1aa731f` with this repair receipt if an arbitrary repository,
uncommitted controller, caller-selected actor, or false publication result becomes
reachable. Preserve the prior Builder receipt, the adverse Curator/Judge receipts,
and this repair record; never restore the fixed-branch recovery helper.
