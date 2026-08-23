# CONTINUATION-JUDGE-3960 — repaired exact-candidate disposition

## Candidate and role boundary

- Candidate commit: `1aa731f58b2d97eae65782b2d79685cefd2ae333`
- Candidate tree: `7762abb323b8e108036a5ba20cfac1353d115041`
- Repair range reviewed: `5de1d5706f01ce219f6d5e55198e2e4f8a23ceff..1aa731f58b2d97eae65782b2d79685cefd2ae333`
- Builder receipt reviewed: `builder/CONTINUATION-3060-REPAIR-1aa731f.md`, sealed in
  follow-up receipt commit `fb773cf3688e8db5e8cf087961c4e3821b28dcd6`.
- Judge identity: `local_judge_disposition`, separate from the Builder and Curator.

## Disposition

**DEFER — repaired local control is credible, but not yet independently qualified for
local adoption.** The earlier repository-scope and false-success dissent is resolved
in the reviewed source and focused reproduction. The successor DAG now records the
implementation, Curator, and Judge nodes. This disposition remains deferred solely
because the required exact-candidate Curator receipt and full repository CI evidence
were not available when sealed.

## Resolved prior dissent

1. The launcher now accepts only `-Apply`; it derives the repository from its own
   `$PSScriptRoot`, requires that path to be the Git top-level, fixes the audit actor
   label, and rejects a modified or staged `.autopilot/bin/autopilot.py`. It records
   the committed controller blob before invocation. The prior caller-selected
   `RepoRoot` and `Actor` paths are absent.
2. `run_orchestration` now reports `release_publication` with `requested`,
   `published`, and `PUBLISHED`/`WITHHELD` fields. The launcher emits
   `CONTINUATION WITHHELD` and exits `3` if an `-Apply` request did not publish a
   release; it no longer describes withholding as applied success.
3. `CONTINUATION-3060`, `CONTINUATION-CURATOR-3070`, and
   `CONTINUATION-JUDGE-3960` now appear in the machine-readable successor DAG with
   explicit dependencies, scope, stopping conditions, and rollback.

## Independent evidence

- `git diff --check` over the repair range was clean; PowerShell AST parsing returned
  zero errors.
- Independently ran:

  ```powershell
  $env:PYTHONDONTWRITEBYTECODE='1'
  $env:PYTHONPATH='src'
  python -m unittest tests.test_preauthorized_continuation tests.test_brain_kernel_authority tests.test_autopilot_workflow -v
  python -m unittest discover -s .autopilot/tests -p test_orchestration.py -v
  ```

  Results: **42 passed, 1 platform-limited symlink skip**; then **26 passed, 1
  platform-limited symlink skip**; zero failures/errors.
- The focused launcher tests execute the unsupported `-RepoRoot` and `-Actor`
  parameter probes and verify denial before execution. Orchestration tests reproduce
  both `WITHHELD` without dispatch and `PUBLISHED` only after a dispatch call.
- The Judge ran the launcher without `-Apply`; its structured live result remained a
  stale-release `WAIT` with no eligible nodes or release. The Judge did not execute
  `-Apply`, because a judicial review is not authority to publish a live release.
- No workflow run was associated with the exact candidate when checked, and no new
  `CONTINUATION-CURATOR-3070` receipt was present. The Builder's focused results are
  retained evidence, not substitutes for those gates.

## Required evidence before a new Judge disposition

- An independent Curator must reproduce the repository/actor denial, committed
  controller binding, no-direct-privileged-path result, and stale `-Apply` exit-3
  withholding behavior on this exact candidate.
- Record an exact-candidate full repository CI result for
  `PYTHONPATH=src python -m unittest discover -s tests -v` (or an equivalent
  immutable CI receipt that directly binds this SHA).

## Authority boundary and rollback

This repair supports only scoped local continuity for an already authorized
routine/reversible workflow. It rejects unlimited consent, cannot authenticate an
owner, and grants no new material scope. **ROOT-3000 remains blocked** on an
owner-operated external verifier, custody, rotation/revocation, deployment, rollback,
and independent witness. **PROMOTION-3990 remains blocked**; neither this receipt nor
the continuation launcher authorizes real remote delivery or a full-authority claim.

If later evidence fails, revert `383b01f` and `1aa731f` along with the repair Builder
receipt; retain the original Builder, Curator, and Judge adverse receipts and both
defer dispositions. Do not restore the historic fixed-branch helper.

## Append-only Curator addendum

Independent Curator receipt
`continuation-curator/CONTINUATION-CURATOR-3070-1aa731f.md` became available after
this Judge receipt was initially sealed. It adopts the repaired control at scoped local
level and independently reproduced all previously missing adverse probes: foreign
`RepoRoot` and `Actor` parameters fail PowerShell binding before launcher execution;
the committed controller blob is observed; and stale `-Apply` returns exit `3` with
`CONTINUATION WITHHELD`, `published: false`, and no worktree/release change. The Curator
retains the same full-CI boundary: it did not run the full repository gate, and no
exact-candidate workflow run is available. This corroborates the repaired behavior but
does not change the Judge's **DEFER** pending immutable exact-candidate full-CI evidence.
