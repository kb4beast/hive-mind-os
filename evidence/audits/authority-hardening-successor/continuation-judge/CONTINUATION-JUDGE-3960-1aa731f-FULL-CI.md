# CONTINUATION-JUDGE-3960 — exact-candidate scoped local adoption

## Candidate and evidence binding

- Implementation candidate: `1aa731f58b2d97eae65782b2d79685cefd2ae333`
- Implementation tree: `7762abb323b8e108036a5ba20cfac1353d115041`
- Builder-receipt head: `fb773cf3688e8db5e8cf087961c4e3821b28dcd6`
- Current plan-document head: `f5402b9b170ddab5373b7823da6cc1e589342150`
- Judge identity: `local_judge_disposition`, distinct from Builder and Curator.

The diff from the implementation candidate through the plan-document head contains
only the Builder receipt and successor-plan documentation; no launcher, Autopilot
controller, test, ADR, or `AGENTS.md` implementation path changed. Thus the full gate
below directly exercises the exact repaired executable source.

## Disposition

**ADOPT — CONTINUATION-3060 as a scoped local durable-continuity control.** This
supersedes the prior `1aa731f` Judge **DEFER**, whose only remaining condition was
exact-candidate full-CI evidence. It does not adopt unlimited consent, external
authority, or a production release.

## Evidence admitted

1. The prior Judge reproduction recorded **42 passed / 1 platform skip** for the
   continuation, authority, and workflow suite, plus **26 passed / 1 platform skip**
   for the Autopilot orchestration suite; PowerShell AST parsing and the no-apply
   `WAIT` probe passed.
2. Independent Curator receipt
   `continuation-curator/CONTINUATION-CURATOR-3070-1aa731f.md` adopted the scoped
   repair. It independently reproduced foreign parameter rejection, committed
   controller binding, no direct privileged path, and stale `-Apply` exit `3` with
   `CONTINUATION WITHHELD`, `published: false`, and no release/worktree mutation.
3. Exact-source full CI was run with inherited `GIT_*` variables scrubbed and:

   ```powershell
   $env:PYTHONDONTWRITEBYTECODE='1'
   $env:PYTHONPATH='src'
   python -m unittest discover -s tests -v
   ```

   Result: **1,115 passed, 7 Windows symlink-capability skips, 0 failures/errors**.
   Scrubbing inherited Git configuration preserves the repository's clean execution
   model; it does not relax a test or policy.
4. The previous dissent is resolved in source and tests: the launcher exposes only
   `-Apply`, derives its own Git top-level, fixes the actor label, requires a clean
   committed controller blob, and rejects requested-but-unpublished release output.
   The machine-readable successor DAG now includes the implementation, Curator, and
   Judge nodes with explicit scope, dependencies, stopping condition, and rollback.

## Scope and retained dissent

- This adoption means only that an explicit owner directive for the existing
  routine/reversible workflow may persist across sessions through this local launcher.
  It **rejects any interpretation as unlimited consent**. New material scope still
  requires its own authority.
- A stale controller continues to withhold rather than publish. The positive live
  publication path was not exercised against this stale repository; it remains subject
  to the existing reconciliation, eligibility, lease, scope, and safe-action gates.
- The committed-controller blob and local `python` resolution are local-host integrity
  assumptions, not external authentication, key custody, or a root signature.
- **ROOT-3000 remains `BLOCKED_EXTERNAL_AUTHORITY`.** No external verifier, owner
  custody, rotation/revocation, deployment, rollback ceremony, or independent witness
  is supplied by this control.
- **PROMOTION-3990 remains blocked and untouched.** This receipt authorizes neither
  real remote delivery nor a full-authority claim.

## Rollback

If this scoped behavior regresses, revert `383b01f` and `1aa731f` together with the
Builder receipt, continuation DAG nodes, and associated ADR/test updates. Preserve the
original adverse Builder/Curator/Judge receipts, the repaired Curator receipt, and this
verdict. Do not restore the historic fixed-branch recovery helper as a fallback.

