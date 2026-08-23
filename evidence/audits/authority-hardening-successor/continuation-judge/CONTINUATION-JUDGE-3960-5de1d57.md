# CONTINUATION-JUDGE-3960 — exact-candidate local disposition

## Candidate and role boundary

- Candidate commit: `5de1d5706f01ce219f6d5e55198e2e4f8a23ceff`
- Candidate tree: `930952d65a1a0edc2596a879ac39adddf6cdf7a8`
- Change range reviewed: `9d50aa58ab7e657062ff9085b9ae00bc2251a1e9..5de1d5706f01ce219f6d5e55198e2e4f8a23ceff`
- Judge identity: `local_judge_disposition`, separate from the Builder.
- Curator receipt: not available when this disposition was sealed; this is not a
  substitute for the required independent Curator review.

## Disposition

**DEFER — do not adopt CONTINUATION-3060 as the canonical preauthorized
continuation launcher yet.** Its fixed request, array invocation, typed live-state
re-observation, and no-apply behavior are locally credible; however, the launcher
does not bind execution to the already authorized repository/scope.

## Evidence reviewed and independently reproduced

- Reviewed ADR-066, the durable-continuation instruction in `AGENTS.md`, and Builder
  receipt `CONTINUATION-3060-5de1d57`. `git diff --check` over the candidate range
  was clean.
- Independently ran:

  ```powershell
  $env:PYTHONPATH='src'
  python -m unittest tests.test_preauthorized_continuation tests.test_brain_kernel_authority tests.test_autopilot_workflow -v
  ```

  Result: **39 passed, 1 platform-limited symlink skip, 0 failures/errors**.
- PowerShell AST parsing of the launcher returned zero parser errors.
- Independently invoked the launcher **without** `-Apply`. It classified the fixed
  request as `CONTINUE`, reported a stale/invalid dispatcher release, returned
  `WAIT` with no eligible nodes or tasks, and made no dispatcher release request.
  `-Apply` was deliberately not exercised because this judicial review does not
  authorize a state-changing release.

## Dissent requiring repair before adoption

1. The public `-RepoRoot` parameter accepts an arbitrary existing Git repository.
   The launcher resolves that selected path and executes its
   `.autopilot/bin/autopilot.py` with `orchestrate --apply` when requested. Checking
   only for a Git root and a local CLI does not bind this execution to the repository
   and routine/reversible scope that the original owner directive covered. This is a
   material scope-expansion path, even though it is not shell interpolation.
2. `-Actor` is syntactically constrained but caller supplied; the dispatcher accepts
   a non-empty actor string as attribution. It must not be interpreted as an
   authenticated identity or independent authority.
3. `CONTINUATION-3060` is absent from the candidate successor `plan.json`, so its
   lifecycle, ownership, independent Curator prerequisite, stopping condition, and
   rollback are not yet represented in the machine-readable DAG.
4. No independent Curator receipt or exact-candidate full CI receipt was available
   to this Judge. The Builder-focused evidence is useful but not a replacement for
   those gates.

## Required route to a later local adoption

- Bind the canonical invocation to the launcher repository resolved from
  `$PSScriptRoot` (or accept another root only when a separately sealed,
  scope-bound authority record verifies it); add an adverse test that an arbitrary
  Git repository cannot be selected under the prior directive.
- Treat the actor as a non-authorizing audit label unless a separate authenticated
  identity contract is implemented and reviewed.
- Add `CONTINUATION-3060` and its independent Curator/Judge nodes to the successor
  DAG, then obtain a Curator receipt and exact-candidate CI before a new Judge review.

## Authority boundary and rollback

This decision rejects any interpretation of durable continuation as unlimited consent.
A prior owner directive may cover only the already authorized routine/reversible scope;
new material scope still requires its own authority. **ROOT-3000 remains blocked** on
owner-operated external verifier/custody/rotation/revocation/deployment/witness evidence.
**PROMOTION-3990 remains blocked** and this receipt authorizes neither real remote
delivery nor any full-authority claim.

If the candidate is rolled back, revert `5de1d5706f01ce219f6d5e55198e2e4f8a23ceff`
and its Builder receipt together, retain ADR-066 and this dissent as evidence, and do
not restore the historic fixed-branch helper as a fallback.

## Append-only Curator addendum

After this receipt was initially sealed, independent Curator receipt
`continuation-curator/CONTINUATION-CURATOR-3060-5de1d57.md` became available. Its
**ADAPT** disposition independently confirms the unbound `RepoRoot`/`Actor` finding
and adds a second material adverse result: against the stale live control plane,
`-Apply` withheld dispatch and changed no worktree state but exited zero and printed
`CONTINUATION APPLIED`. That success message is misleading for a typed withheld
continuation and must be repaired with an adverse runtime test. The Curator also
confirms no independent full repository CI run for the exact candidate. These findings
reinforce, rather than alter, this Judge's **DEFER** disposition.
