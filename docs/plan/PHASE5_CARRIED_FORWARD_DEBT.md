# Phase 5 role deepening — carried-forward debt

- **Established:** 2026-07-31
- **Authority:** explicit maintainer direction to preserve unresolved findings, merge bounded Phase 5
  candidates, and carry unresolved work into the next phase.
- **Posture:** accepted integration debt; not a green-build, release-readiness, production-readiness,
  independent-verification, or superiority claim.
- **Applies from:** Phase 5D Curator integration into `agent/phase5a-orchestrator-shadow`.
- **Current next owning phase:** Phase 5H Role-Deepening Consolidation Court unless a later explicit
  plan decision assigns an item elsewhere.

## Carry-forward rules

1. Preserve all failed-run receipts and adverse findings.
2. Do not weaken, skip, delete, or relabel a gate to obtain a passing result.
3. Later phases must distinguish focused role success from full-suite and static/type status.
4. These items do not block an explicitly maintainer-authorized normal merge, but they remain part
   of future integration, release, and compliance decisions.
5. No later report may describe the combined integration head as fully green until all applicable
   exit conditions are satisfied with exact-head receipts.
6. Later evidence may resolve or reopen an earlier item; every transition must preserve both the
   prior adverse evidence and the later receipt.

## Phase 5D carried-forward items

| ID | Finding and evidence | Current impact | Required resolution / exit condition | Effective status |
|---|---|---|---|---|
| P5D-DEBT-01 | Constitutional CI run `30660783595` reported unsorted imports in `src/hive_mind_os/foundation/curator_playbook.py`, unused local `builtin_instruction`, and unsorted imports in `tests/test_phase5d_curator_playbook.py`. Cleanup run `30661841213` demonstrated deterministic Ruff repairs but stopped before commit because Pyright failed. Phase 5E, 5F, and 5G exact-head runs reproduced the same Ruff findings. | Full repository static validation is not green. | Commit the deterministic Ruff repairs; run `ruff check src tests scripts` on the exact resulting head and retain a successful hosted receipt. | open |
| P5D-DEBT-02 | Cleanup run `30661841213` passed all 41 focused Phase 5D tests and Ruff after repair, then Pyright 1.1.411 reported two `Mapping`/`dict` errors in `curator_playbook.py`. Later global Pyright jobs were skipped because Ruff failed first. | Global type validation remains unresolved. | Correct the mutable-container typing without weakening exact-container validation or defensive-copy semantics; run Pyright 1.1.411 and focused/full tests successfully on the exact successor head. | open |
| P5D-DEBT-03 | Run `30660783595` failed `test_seeded_process_kill_sweep_reclaims_without_duplicate_effects` on Python 3.11. Runs `30674773848`, `30677041971`, and `30677227480` later passed all Python matrices, but Phase 5G initial run `30679862330` failed the same worker test on Python 3.12 with the queue not fully reaching `done`. | The worker sweep is intermittently nondeterministic across exact hosted runs; prior passing receipts remain valid but do not prove closure. | Reproduce and correct the deterministic timing/state defect without weakening the test. Exit requires a root-cause record plus repeated exact-head Python 3.11, 3.12, and 3.14 passes. | reopened |
| P5D-DEBT-04 | The integration tree retains `.github/workflows/phase5d-materialize.yml`, `.github/workflows/phase5d-publication-remand.yml`, and `.github/workflows/phase5d-final-cleanup.yml`. Their predicates are Phase-5D-specific, but they remain write-capable integration surface. | Temporary publication machinery remains in the combined tree. | Remove all three workflows in a normal successor commit after preserving their run receipts; verify no permanent behavior is lost and run governance/static tests. | open |
| P5D-DEBT-05 | Later exact-head runs passed broad test, build, SBOM, CodeQL, secret, and dependency gates but continued to fail inherited Ruff, skip global Pyright, or expose the reopened worker failure. | The integration head has broad evidence but is not fully green. | Obtain an exact-head Constitutional CI run where every required job, including Ruff, global Pyright, and all Python matrices, completes successfully after applicable root causes are resolved. | open |

## Phase 5E carried-forward items

PR #55 delivered a bounded, inert Integrator intake rather than the complete Integrator deep playbook.

| ID | Finding and evidence | Current impact | Required resolution / exit condition | Status |
|---|---|---|---|---|
| P5E-DEBT-01 | Phase 5E implements only integration scope, compatibility plan, inherited-debt register, and blocked Steward handoff. Full contract inventory, dependency graph, data lineage, adapter replacement analysis, migration ordering, rollback mapping, and integration-receipt outputs are absent. | Integrator cannot support a release or compatibility conclusion. | Implement the missing outputs as separately versioned, digest-bound contracts with adversarial tests and exact scope reconstruction. | open |
| P5E-DEBT-02 | No Phase 5E inventory generator, chained inventory artifact, installed-wheel verifier, or permanent CI installation step was added. | Packaged Phase 5E availability and inventory integrity are unverified. | Add Phase 5E inventory and installed-wheel verification, chain it from prior inventories, update permanent CI, and retain exact-head artifacts. | open |
| P5E-DEBT-03 | No Phase 5E courtroom docket, dissent record, migration/rollback document, ADR, source register, or procedural-role review artifact was completed. | Governance, dissent, and rollback evidence are incomplete. | Add the missing append-only evidence and architecture records without claiming authenticated independence. | open |
| P5E-DEBT-04 | Focused run `30674699706` passed 9 Phase 5E tests, Ruff, and Pyright on Phase 5E files, while later full runs remained non-green because of inherited debt. | Phase 5E has bounded focused evidence but no fully green integrated receipt. | Preserve focused evidence and later obtain fully successful exact-head integrated CI. | open |
| P5E-DEBT-05 | Phase 5E remains package-private, inert, authority-free, and has no authenticated independent Integrator or Steward execution. Compatibility checks remain `not-run`; release remains `defer`. | No release approval, production readiness, external execution, or independent verification may be inferred. | Require authenticated external evidence and applicable release-court gates before changing these claims. | open |

## Phase 5F carried-forward items

PR #56 delivered a bounded, inert Steward intake rather than the complete Steward deep playbook.

| ID | Finding and evidence | Current impact | Required resolution / exit condition | Status |
|---|---|---|---|---|
| P5F-DEBT-01 | Phase 5F implements only a degraded health snapshot, non-executed maintenance plan, reversible recovery plan, and blocked Optimizer handoff. Complete reliability, observability, dependency-health, runbook, interruption-recovery, evidence-integrity, and operational-maintenance outputs are absent. | Steward cannot support a health, recovery, maintenance, readiness, or Optimizer-eligibility conclusion. | Implement missing outputs as separately versioned, digest-bound contracts with exact evidence requirements, fail-closed unknown states, reversible steps, and adversarial tests. | open |
| P5F-DEBT-02 | No Phase 5F inventory generator, chained inventory artifact, installed-wheel verifier, permanent CI installation step, or package-resource verification was added. | Packaged Phase 5F availability and inventory integrity are unverified. | Add Phase 5F inventory and installed-wheel verification, chain it through Phase 5E, update CI, and retain exact-head artifacts. | open |
| P5F-DEBT-03 | No Phase 5F courtroom docket, dissent record, ADR, source register, operational runbook, recovery exercise, migration/rollback evidence, or procedural-role review artifact was completed. | Governance, operational recovery, and rollback evidence are incomplete. | Add the missing append-only evidence and operations records without claiming authenticated independence or executed recovery. | open |
| P5F-DEBT-04 | Run `30677227480` passed all Python matrices and build/security jobs but failed inherited Ruff and skipped global Pyright. | Phase 5F has cross-version compatibility evidence but no dedicated successful Pyright or fully green integrated receipt. | Preserve the passing evidence and later obtain successful focused/global Pyright plus fully successful exact-head CI. | open |
| P5F-DEBT-05 | Phase 5F remains package-private, inert, authority-free, reports health `degraded`, leaves maintenance/recovery `not-run`, and blocks Optimizer eligibility. | No executed maintenance, recovery success, healthy status, release approval, learning eligibility, or independent verification may be inferred. | Require authenticated external evidence, executed reversible recovery/maintenance receipts, resolved applicable debt, and release-court approval before changing these claims. | open |

## Phase 5G carried-forward items

PR #57 delivers a bounded, inert Optimizer intake rather than an executed optimization program.
The maintainer explicitly authorized normal merge with the following work carried into Phase 5H.

| ID | Finding and evidence | Current impact | Required resolution / exit condition | Status |
|---|---|---|---|---|
| P5G-DEBT-01 | Phase 5G implements only a degraded baseline snapshot, proposed challenger plan, non-executed evaluation plan, and blocked promotion-court handoff. Real metrics, outcome datasets, resource budgets, comparator results, regression results, experiment receipts, improvement proposals, and rollback exercises are absent. | Optimizer cannot support improvement, learning, superiority, promotion, or release conclusions. | Implement separately versioned, digest-bound outcome, experiment, resource, regression, rollback, and proposal contracts with held-out and adversarial tests. | open |
| P5G-DEBT-02 | No Phase 5G inventory generator, chained inventory artifact, installed-wheel verifier, package-resource verification, or permanent CI installation step was added. Existing permanent verification stops at Phase 5D. | Packaged Phase 5G availability and current-tree inventory integrity are unverified. | Add chained Phase 5E–5G inventories and installed-wheel verification, update permanent CI, and retain successful exact-head artifacts. | open |
| P5G-DEBT-03 | No Phase 5G courtroom docket, dissent record, ADR, source register, protected-holdout custody receipt, comparator manifest, losing-result archive, independent evaluator record, or promotion-court disposition was completed. | Governance and independent promotion evidence are absent. | Add append-only evidence and court records while keeping holdout contents sealed and avoiding authenticated-independence claims without external proof. | open |
| P5G-DEBT-04 | Initial run `30679862330` exposed a Phase 5G test-contract error and the reopened worker failure. The digest-boundary test was corrected in commit `99d20dac8b2b0891020a473c206676860ac61a14`; corrected run `30680063488` passed build, SBOM, CodeQL, secret, and dependency jobs but remained nonterminal at closeout for Python matrices and still failed inherited Ruff before global Pyright. | The fix is committed, but no terminal fully green exact-head receipt exists. | Preserve both runs; require terminal passing focused Phase 5G tests, global Pyright, all Python matrices, and a fully successful exact-head Constitutional CI run. | open |
| P5G-DEBT-05 | Phase 5G remains package-private, inert, authority-free, leaves holdout `sealed-not-accessed`, evaluations `not-run`, superiority `prohibited`, and promotion court blocked. No authenticated independent Optimizer, evaluator, Judge, or court execution exists. | No learning, improvement, superiority, promotion, release, production readiness, or independent verification may be inferred. | Require authenticated independent evaluation, protected-holdout custody, preserved losing results, statistical/regression evidence, and applicable court approval before changing these claims. | open |

## Evidence that remains valid

- Phase 4 Explorer and Phase 5A–5G candidates remain bounded and do not gain authority merely from
  integration or naming.
- Cleanup run `30661841213` executed 41 focused Phase 5D tests successfully before Pyright stopped
  publication.
- Phase 5E focused run `30674699706` passed its focused tests, Ruff, and Pyright.
- Later Phase 5E and Phase 5F runs passed broad Python, build, SBOM, CodeQL, secret, and dependency
  gates where reported.
- Phase 5G corrected the request-digest test contract in commit `99d20dac8b2b0891020a473c206676860ac61a14`.
- One assistant performed separate procedural role passes; authenticated independent Curator,
  Integrator, Steward, Optimizer, court, or Judge execution is not claimed.

## Handoff to Phase 5H

Phase 5H begins from the normal merge commit of PR #57. It is a **Role-Deepening Consolidation
Court**, not P20 Release Readiness. P20 remains unavailable because its P18/P19, external-retention,
authenticated-judge, operational, and blocker prerequisites are not satisfied.

Phase 5H must:

1. reconstruct the exact Phase 4 Explorer and Phase 5A–5G candidate inventory and ancestry;
2. ingest every open or reopened Phase 5D–5G item with exact run and commit bindings;
3. preserve all resolved, reopened, adverse, dissenting, losing, and inconclusive evidence;
4. produce a role-coverage matrix, contract/evidence index, conflict register, rollback map, and
   machine-readable non-release disposition;
5. reject any claim that merged PRs, broad passing jobs, or procedural role labels establish release
   readiness, production readiness, authenticated independence, or superiority;
6. remain inert, package-private, authority-free, and outside supported API/CLI/runtime selection;
7. route unresolved obligations to P14–P20 adoption or another explicit successor without pretending
   those phases are complete; and
8. avoid promotion, release, deployment, production, or comparative-claim authority.
