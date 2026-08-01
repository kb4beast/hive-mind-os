# Phase 5 role deepening — carried-forward debt

- **Established:** 2026-07-31
- **Authority:** explicit maintainer direction to preserve these unresolved findings, merge bounded
  Phase 5 candidates, and carry unresolved work into the next phase.
- **Posture:** accepted integration debt; not a green-build, release-readiness, production-readiness,
  independent-verification, or superiority claim.
- **Applies from:** Phase 5D Curator integration into `agent/phase5a-orchestrator-shadow`.
- **Current next owning phase:** Phase 5F Steward deep playbook unless a later explicit plan decision
  assigns an item elsewhere.

## Carry-forward rules

1. Preserve all failed-run receipts and adverse findings.
2. Do not weaken, skip, delete, or relabel a gate to obtain a passing result.
3. Later phases must distinguish focused role success from full-suite and static/type status.
4. These items do not block an explicitly maintainer-authorized normal merge, but they remain part
   of future integration, release, and compliance decisions.
5. No later report may describe the combined integration head as fully green until all applicable
   exit conditions are satisfied with exact-head receipts.
6. Later exact-head evidence may resolve an earlier item; the resolving receipt must be recorded
   without erasing the original adverse evidence.

## Phase 5D carried-forward items

| ID | Finding and evidence | Current impact | Required resolution / exit condition | Effective status |
|---|---|---|---|---|
| P5D-DEBT-01 | Constitutional CI run `30660783595` reported unsorted imports in `src/hive_mind_os/foundation/curator_playbook.py`, unused local `builtin_instruction`, and unsorted imports in `tests/test_phase5d_curator_playbook.py`. Cleanup run `30661841213` demonstrated that Ruff can repair all three findings, but the workflow stopped before committing because Pyright failed. Exact-head Phase 5E run `30674773848` reproduced the same three Ruff findings. | Full repository static validation is not green. | Commit the deterministic Ruff repairs on a successor branch; run `ruff check src tests scripts` on the exact resulting head and retain a successful hosted receipt. | open |
| P5D-DEBT-02 | Cleanup run `30661841213` passed all 41 focused Phase 5D tests and Ruff after repair, then Pyright 1.1.411 reported two errors in `curator_playbook.py`: assignment through `Mapping[str, Any]` near line 337 and return of `Mapping[str, Any]` where `dict[str, Any]` is declared near line 342. Exact-head run `30674773848` could not re-run global Pyright because Ruff failed first. | Global type validation remains unresolved. | Correct the mutable-container typing without weakening exact-container validation or defensive-copy semantics; run Pyright 1.1.411 and focused/full tests successfully on the exact successor head. | open |
| P5D-DEBT-03 | Constitutional CI run `30660783595` failed `tests/test_workers.py::WorkerTests::test_seeded_process_kill_sweep_reclaims_without_duplicate_effects` on Python 3.11. Exact-head run `30674773848` on `6e817115bc214d61ebd251e43a014cbbe4f20d96` subsequently passed the full deterministic suite on Python 3.11, 3.12, and 3.14 without weakening the test. | The earlier cross-version uncertainty is closed by later exact-head evidence; the original failure remains preserved as adverse history. | Preserve run `30674773848` as the resolution receipt. Reopen only if a later deterministic reproduction fails on an unchanged relevant code path. | resolved |
| P5D-DEBT-04 | The integration base retains temporary write-capable workflows `.github/workflows/phase5d-materialize.yml`, `.github/workflows/phase5d-publication-remand.yml`, and `.github/workflows/phase5d-final-cleanup.yml`. Their branch predicates are Phase-5D-specific, but their presence is still integration surface. | The combined integration tree contains temporary publication machinery and additional `contents: write` workflow definitions. | Remove all three workflows in a normal successor commit after preserving their run receipts. Verify no required permanent CI behavior is lost and run repository governance/static tests. | open |
| P5D-DEBT-05 | Phase 5D Constitutional CI and cleanup runs failed. Exact-head Phase 5E run `30674773848` passed all full test matrices, build, installed-wheel checks through Phase 5D, SBOM, CodeQL, secret scan, and dependency review, but still failed the inherited Ruff findings and skipped global Pyright. | The integration head has broad executable evidence but is not fully green. | Obtain one later exact-head Constitutional CI run where every required job, including Ruff and global Pyright, completes successfully. | open |

## Phase 5E carried-forward items

PR #55 delivers a bounded, inert Integrator intake rather than the complete Integrator deep playbook.
The maintainer explicitly authorized normal merge with the following work carried into Phase 5F.

| ID | Finding and evidence | Current impact | Required resolution / exit condition | Status |
|---|---|---|---|---|
| P5E-DEBT-01 | Phase 5E implements only the initial integration scope, compatibility plan, inherited-debt register, and blocked Steward handoff. Full contract inventory, dependency graph, data lineage, adapter replacement analysis, migration ordering, rollback mapping, and integration-receipt outputs are not implemented. | The Integrator role is incomplete and cannot support a release or compatibility conclusion. | Implement the missing outputs as separately versioned, digest-bound contracts with adversarial tests and exact scope reconstruction. | open |
| P5E-DEBT-02 | No Phase 5E inventory generator, chained inventory artifact, installed-wheel verifier, or permanent CI installation step was added. Existing installed-wheel verification stops at Phase 5D. | Packaged Phase 5E availability and current-tree inventory integrity are unverified. | Add Phase 5E inventory and installed-wheel verification, chain it from prior phase inventories, update permanent CI, and retain successful exact-head artifact receipts. | open |
| P5E-DEBT-03 | No Phase 5E courtroom docket, dissent record, migration/rollback document, ADR, source register, or procedural-role review artifact was completed. | Governance, dissent, and rollback evidence for a complete Phase 5E candidate are absent. | Add the missing append-only evidence and architecture records without claiming authenticated independence. | open |
| P5E-DEBT-04 | Focused hosted run `30674699706` passed 9 Phase 5E tests, Ruff 0.16.0, and Pyright 1.1.411 on the new Phase 5E files. Exact-head full run `30674773848` passed all Python matrices and build/security jobs but failed inherited Ruff before global Pyright. | The new Phase 5E files have bounded focused evidence, but the merged integration head is not fully green. | Preserve the focused receipt and later obtain a fully successful exact-head Constitutional CI run after inherited static/type debt is resolved. | open |
| P5E-DEBT-05 | The Phase 5E candidate remains package-private, inert, authority-free, and has no authenticated independent Integrator or Steward execution. Compatibility checks remain `not-run`; release recommendation remains `defer`. | No release approval, production readiness, external execution, or independent verification may be inferred. | Require external authenticated evidence and applicable release-court gates before changing these claims. | open |

## Evidence that remains valid

- PR #54 remains an inert, package-private Curator candidate with authority `none`, activation
  `inert`, zero effective capabilities, and zero tools.
- Cleanup run `30661841213` executed all 41 focused Phase 5D tests successfully before Pyright
  stopped publication.
- Phase 5E focused run `30674699706` passed 9 tests, Ruff, and Pyright for the new Phase 5E files.
- Exact-head run `30674773848` passed full tests on Python 3.11, 3.12, and 3.14, build,
  installed-wheel checks through Phase 5D, SBOM, CodeQL, secret scan, and dependency review.
- One assistant performed separate procedural role passes; authenticated independent Curator,
  Integrator, Steward, or Judge execution is not claimed.

## Handoff to Phase 5F

Phase 5F begins from the normal merge commit of PR #55. The Steward deep playbook must:

1. ingest every still-open Phase 5D and Phase 5E debt item with exact run and commit bindings;
2. preserve the resolved status and evidence for `P5D-DEBT-03` without erasing its original failure;
3. define reliability, observability, recovery, maintainability, runbook, and evidence-integrity checks;
4. prevent health, readiness, or recovery recommendations from treating open debt as resolved;
5. preserve reversible cleanup paths for temporary workflows and incomplete static/type gates;
6. remain inert, package-private, authority-free, and outside supported API/CLI/runtime selection;
7. carry any still-open items into Phase 5G Optimizer and the release court without erasure; and
8. avoid any production-readiness, release-readiness, authenticated-independence, or superiority claim.
