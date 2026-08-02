# Phase 5 role deepening — carried-forward debt

- **Established:** 2026-07-31
- **Authority:** explicit maintainer direction to preserve unresolved findings, merge bounded Phase 5
  candidates, and carry unresolved work into the next phase.
- **Posture:** accepted integration debt; not a green-build, release-readiness, production-readiness,
  independent-verification, or superiority claim.
- **Applies from:** Phase 5D Curator integration into `agent/phase5a-orchestrator-shadow`.
- **Current next owning phase:** Phase 5J Independent Adoption Review Packet unless a later explicit
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
7. Procedural role labels, local digests, merged PRs, and broad passing jobs cannot satisfy an
   authenticated-independence or external-adoption gate.

## Phase 5D carried-forward items

| ID | Finding and evidence | Current impact | Required resolution / exit condition | Effective status |
|---|---|---|---|---|
| P5D-DEBT-01 | Constitutional CI run `30660783595` reported unsorted imports in `src/hive_mind_os/foundation/curator_playbook.py`, unused local `builtin_instruction`, and unsorted imports in `tests/test_phase5d_curator_playbook.py`. Cleanup run `30661841213` demonstrated deterministic Ruff repairs but stopped before commit because Pyright failed. Phase 5E through Phase 5I exact-head runs reproduced the same Ruff findings. | Full repository static validation is not green. | Commit the deterministic Ruff repairs; run `ruff check src tests scripts` on the exact resulting head and retain a successful hosted receipt. | open |
| P5D-DEBT-02 | Cleanup run `30661841213` passed all 41 focused Phase 5D tests and Ruff after repair, then Pyright 1.1.411 reported two `Mapping`/`dict` errors in `curator_playbook.py`. Later global Pyright jobs were skipped because Ruff failed first. | Global type validation remains unresolved. | Correct the mutable-container typing without weakening exact-container validation or defensive-copy semantics; run Pyright 1.1.411 and focused/full tests successfully on the exact successor head. | open |
| P5D-DEBT-03 | Run `30660783595` failed `test_seeded_process_kill_sweep_reclaims_without_duplicate_effects` on Python 3.11. Later runs passed all matrices, but Phase 5G run `30679862330` failed it on Python 3.12 and Phase 5I run `30681039055` failed it again on Python 3.11, each with the queue not fully reaching `done`. Passing runs `30680063488` and `30680444662` did not explain the recurrence. | The worker sweep is intermittently nondeterministic across exact hosted runs; passing receipts remain valid but do not prove closure. | Reproduce and correct the deterministic timing/state defect without weakening the test. Exit requires a root-cause record plus repeated exact-head Python 3.11, 3.12, and 3.14 passes. | reopened |
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

PR #57 delivered a bounded, inert Optimizer intake rather than an executed optimization program.

| ID | Finding and evidence | Current impact | Required resolution / exit condition | Status |
|---|---|---|---|---|
| P5G-DEBT-01 | Phase 5G implements only a degraded baseline snapshot, proposed challenger plan, non-executed evaluation plan, and blocked promotion-court handoff. Real metrics, outcome datasets, resource budgets, comparator results, regression results, experiment receipts, improvement proposals, and rollback exercises are absent. | Optimizer cannot support improvement, learning, superiority, promotion, or release conclusions. | Implement separately versioned, digest-bound outcome, experiment, resource, regression, rollback, and proposal contracts with held-out and adversarial tests. | open |
| P5G-DEBT-02 | No Phase 5G inventory generator, chained inventory artifact, installed-wheel verifier, package-resource verification, or permanent CI installation step was added. Existing permanent verification stops at Phase 5D. | Packaged Phase 5G availability and current-tree inventory integrity are unverified. | Add chained Phase 5E–5G inventories and installed-wheel verification, update permanent CI, and retain successful exact-head artifacts. | open |
| P5G-DEBT-03 | No Phase 5G courtroom docket, dissent record, ADR, source register, protected-holdout custody receipt, comparator manifest, losing-result archive, independent evaluator record, or promotion-court disposition was completed. | Governance and independent promotion evidence are absent. | Add append-only evidence and court records while keeping holdout contents sealed and avoiding authenticated-independence claims without external proof. | open |
| P5G-DEBT-04 | Initial run `30679862330` exposed a Phase 5G test-contract error and the reopened worker failure. The digest-boundary test was corrected in commit `99d20dac8b2b0891020a473c206676860ac61a14`. Corrected run `30680063488` passed all three Python matrices plus build, SBOM, CodeQL, secret, and dependency jobs, but inherited Ruff failed and global Pyright was skipped. | The Phase 5G source correction has cross-version evidence, but no fully green exact-head receipt exists. | Preserve both runs; require successful global Pyright, all Python matrices, and a fully successful exact-head Constitutional CI run after inherited gates are repaired. | open |
| P5G-DEBT-05 | Phase 5G remains package-private, inert, authority-free, leaves holdout `sealed-not-accessed`, evaluations `not-run`, superiority `prohibited`, and promotion court blocked. No authenticated independent Optimizer, evaluator, Judge, or court execution exists. | No learning, improvement, superiority, promotion, release, production readiness, or independent verification may be inferred. | Require authenticated independent evaluation, protected-holdout custody, preserved losing results, statistical/regression evidence, and applicable court approval before changing these claims. | open |

## Phase 5H carried-forward items

PR #58 delivered a bounded, deterministic, non-release consolidation court rather than an authenticated
adoption or release court.

| ID | Finding and evidence | Current impact | Required resolution / exit condition | Status |
|---|---|---|---|---|
| P5H-DEBT-01 | Phase 5H binds an exact eight-role request and emits role inventory, evidence coverage, conflicts, and `defer-non-release`, but it does not independently reconstruct every role candidate’s Git ancestry, tree, inventory, contract digest, and evidence chain from authoritative repository data. | The local court cannot prove a complete, current, independently reconstructed role-deepening inventory. | Produce a machine-readable ancestry and contract/evidence index keyed to exact commits, trees, file digests, PR merges, and retained receipts; verify it independently against Git and package contents. | open |
| P5H-DEBT-02 | No Phase 5H inventory generator, chained Phase 5E–5H inventory artifact, installed-wheel verifier, package-resource verification, or permanent CI step was added. Permanent installed-wheel verification still stops at Phase 5D. | Packaged Integrator through consolidation-court availability and inventory integrity remain unverified. | Add chained Phase 5E–5H inventories and installed-wheel verifiers, update permanent CI, and retain successful exact-head artifacts. | open |
| P5H-DEBT-03 | Phase 5H was executed procedurally by one assistant. No externally retained court record or authenticated distinct Curator, Judge, Appeals Judge, or Orchestrator decision exists. | The court cannot satisfy ADR-015 adoption, authenticated independence, P20, or release-governance burdens. | Obtain non-self-issued, revocable identities and externally retained signed court evidence from distinct authorized participants; verify forgery, replay, expiry, and bypass fail closed. | open |
| P5H-DEBT-04 | ADR-015 and `01_POST_P13_OVERVIEW.md` remain proposed. P14 cannot begin under their own executor protocol until the complete program receives an independent permitting disposition. P18, P19, operational evidence, external retention, and applicable blocker exits are also absent. | P14–P20 remain unavailable; Phase 5H can only issue `defer-non-release`. | Complete an independent adoption docket for ADR-015 and the full P14–P20 plan. A permitting disposition may unlock only P14; it does not clear any capability, production, source, or superiority blocker. | open |
| P5H-DEBT-05 | Run `30680444662` on source head `045bc758213d9410642d6c9909b408dff0ffafc5` passed all three Python matrices, build/SBOM, CodeQL, secret, and dependency jobs. It failed only inherited Phase 5D Ruff and skipped global Pyright. Closeout documentation commits were added after the tested source head. | Phase 5H has broad source compatibility evidence but no fully green or exact-final-head receipt. | Preserve `docs/plan/PHASE5H_TERMINAL_RECEIPT.md`; later obtain exact-final-head tests, chained inventory/installed-wheel verification, Ruff, global Pyright, and fully successful Constitutional CI. | open |

## Phase 5I carried-forward items

PR #59 delivers a bounded local adoption-preparation docket rather than an authenticated independent
adoption review. The maintainer explicitly authorized normal merge with the following work carried
into Phase 5J.

| ID | Finding and evidence | Current impact | Required resolution / exit condition | Status |
|---|---|---|---|---|
| P5I-DEBT-01 | Phase 5I emits a proposed document manifest, required-but-unauthenticated adoption roles, missing external-input register, and `awaiting-independent-adoption`. It does not produce an authenticated Curator recommendation, Judge disposition, or Orchestrator confirmation. | ADR-015 and the P14–P20 program remain proposed; P14 remains blocked. | Obtain distinct non-self-issued reviewer identities and externally verifiable signed dispositions bound to the exact packet and scope. | open |
| P5I-DEBT-02 | No Phase 5I inventory generator, chained Phase 5E–5I inventory artifact, installed-wheel verifier, package-resource verification, or permanent CI step was added. Permanent installed-wheel verification still stops at Phase 5D. | Packaged adoption-docket availability and current-tree inventory integrity are unverified. | Add chained Phase 5E–5I inventories and installed-wheel verification, update permanent CI, and retain successful exact-head artifacts. | open |
| P5I-DEBT-03 | Provider authority, identity/signing, external retention, deployment/rollback, source/license, and comparator-access inputs remain missing. No secret, credential, signature, external account, grant, or evidence body was accepted. | The adoption packet cannot satisfy external authority, custody, or operational prerequisites. | Supply each input through an authorized external boundary with custody, expiry, revocation, replay, and bypass evidence; do not commit secrets. | open |
| P5I-DEBT-04 | Run `30681039055` on source head `eb1fb6a48e1ae3f080582888dcd40274fa0eb699` passed Python 3.12 and 3.14, build/SBOM, CodeQL, secret, and dependency jobs. All eleven Phase 5I tests passed, but Python 3.11 reproduced reopened `P5D-DEBT-03`; inherited Ruff failed and global Pyright was skipped. | Phase 5I has bounded contract evidence but no cross-version or fully green integrated receipt. | Preserve `docs/plan/PHASE5I_TERMINAL_RECEIPT.md`; resolve the worker and static/type root causes, then obtain exact-head all-matrix and fully successful CI. | open |
| P5I-DEBT-05 | Phase 5I remains package-private, inert, authority-free, and its closeout documentation follows the tested source head. It cannot itself accept or manufacture an independent permitting decision. | No exact-final-head, authenticated-adoption, P14-eligibility, release, production, deployment, promotion, or superiority claim may be inferred. | Complete an external independent review of the frozen packet; record its authenticated result without broadening the permitted scope, then rerun exact-final-head verification. | open |

## Evidence that remains valid

- Phase 4 Explorer and Phase 5A–5I candidates remain bounded and do not gain authority merely from
  integration or naming.
- Cleanup run `30661841213` executed 41 focused Phase 5D tests successfully before Pyright stopped
  publication.
- Phase 5E focused run `30674699706` passed its focused tests, Ruff, and Pyright.
- Later Phase 5E through Phase 5I runs passed broad Python, build, SBOM, CodeQL, secret, and dependency
  gates where reported.
- Phase 5G corrected the request-digest test contract in commit
  `99d20dac8b2b0891020a473c206676860ac61a14`.
- Phase 5H run `30680444662` passed the full deterministic suite on Python 3.11, 3.12, and 3.14 and
  introduced no Phase 5H Ruff finding.
- Phase 5I run `30681039055` passed all eleven Phase 5I tests, Python 3.12 and 3.14 full suites, and
  build/security gates; its Python 3.11 failure was the reopened worker test.
- One assistant performed separate procedural role passes; authenticated independent Curator,
  Integrator, Steward, Optimizer, court, Judge, or Orchestrator execution is not claimed.

## Handoff to Phase 5J

Phase 5J begins from the normal merge commit of PR #59. It is an **Independent Adoption Review
Packet**, not an independent review result, P14 implementation, or P20 Release Readiness.

Phase 5J must:

1. freeze the exact Phase 5I merge commit, tree, ADR-015 bytes, P14–P20 overview bytes, debt-plan bytes,
   and all applicable evidence references;
2. produce a reviewer-facing Curator packet, Judge decision template, and Orchestrator confirmation
   template without pre-filling a permitting outcome;
3. define signature, identity, expiry, revocation, replay, external-retention, conflict-of-interest,
   and scope-binding requirements for each external participant;
4. include every open or reopened Phase 5D–5I debt item and every missing external-input class;
5. preserve dissent, rejection, abstention, narrowing, and `defer` as first-class outcomes;
6. issue only `awaiting-external-review` until authenticated external evidence is supplied;
7. keep ADR adoption, P14/P20 eligibility, release, production, deployment, promotion, superiority,
   authority, and activation false; and
8. end with a human/external handoff rather than fabricating the independent review inside this
   procedural session.
