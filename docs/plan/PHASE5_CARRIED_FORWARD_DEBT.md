# Phase 5 role deepening — carried-forward debt

- **Established:** 2026-07-31
- **Authority:** explicit maintainer direction to preserve these unresolved findings, merge the
  bounded Phase 5D candidate, and carry the work into the next phase.
- **Posture:** accepted integration debt; not a green-build, release-readiness, production-readiness,
  independent-verification, or superiority claim.
- **Applies from:** Phase 5D Curator integration into `agent/phase5a-orchestrator-shadow`.
- **Next owning phase:** Phase 5E Integrator deep playbook unless a later explicit plan decision
  assigns an item elsewhere.

## Carry-forward rules

1. Preserve all failed-run receipts and adverse findings.
2. Do not weaken, skip, delete, or relabel a gate to obtain a passing result.
3. Later phases must distinguish focused Phase 5D success from full-suite and static/type failure.
4. These items do not block the maintainer-authorized normal merge of PR #54, but they remain open
   and must be included in future integration, release, and compliance decisions.
5. No later report may describe Phase 5D or the combined Phase 5A–5D integration head as fully green
   until all applicable exit conditions below are satisfied with exact-head receipts.

## Open carried-forward items

| ID | Finding and evidence | Current impact | Required resolution / exit condition | Status |
|---|---|---|---|---|
| P5D-DEBT-01 | Constitutional CI run `30660783595` on head `86ad72581365793c556c7ebd648c41ad77d77b4e` reported Ruff findings: unsorted imports in `src/hive_mind_os/foundation/curator_playbook.py`, unused local `builtin_instruction`, and unsorted imports in `tests/test_phase5d_curator_playbook.py`. Cleanup run `30661841213` demonstrated that Ruff can repair all three findings, but the workflow stopped before committing because Pyright failed. | The merged source tree still contains the original Ruff findings unless a later commit removes them. Full static validation is not green. | Commit the deterministic Ruff repairs on a successor branch; run `ruff check src tests scripts` on the exact resulting head and retain a successful hosted receipt. | open |
| P5D-DEBT-02 | Cleanup run `30661841213` passed all 41 focused Phase 5D tests and Ruff after repair, then Pyright 1.1.411 reported two errors in `curator_playbook.py`: assignment through `Mapping[str, Any]` near line 337 and return of `Mapping[str, Any]` where `dict[str, Any]` is declared near line 342. Because the gate failed, no cleanup product commit was published. | The Phase 5D candidate remains type-check failing and the attempted source repairs are not present in the branch head. | Correct the mutable-container typing without weakening exact-container validation or defensive-copy semantics; run Pyright 1.1.411 and focused/full tests successfully on the exact successor head. | open |
| P5D-DEBT-03 | Full Python 3.11 suite in Constitutional CI run `30660783595` failed `tests/test_workers.py::WorkerTests::test_seeded_process_kill_sweep_reclaims_without_duplicate_effects`; the same full suite passed on Python 3.12 and 3.14 in that run. The failure has not been independently reproduced or proven flaky. | Cross-version deterministic-suite status is unresolved. It must not be silently classified as an infrastructure-only failure. | Reproduce under pinned Python 3.11 or establish a bounded deterministic fix. Exit requires successful exact-head Python 3.11, 3.12, and 3.14 hosted runs without weakening the worker test. | open |
| P5D-DEBT-04 | The Phase 5D branch retains temporary write-capable workflows `.github/workflows/phase5d-materialize.yml`, `.github/workflows/phase5d-publication-remand.yml`, and `.github/workflows/phase5d-final-cleanup.yml`. The final-cleanup workflow attempted self-removal but failed before commit publication. Their branch predicates are Phase-5D-specific, but their presence is still integration surface. | The combined integration tree contains temporary publication machinery and additional `contents: write` workflow definitions. | Remove all three workflows in a normal successor commit after preserving their run receipts. Verify no required permanent CI behavior is lost and run repository governance/static tests. | open |
| P5D-DEBT-05 | Constitutional CI run `30661841169` on head `292e8b97ccc5b53fd0f0d9730badabdf4e1c784d` completed with failure. Cleanup run `30661841213` also completed with failure. | PR #54 is being merged by explicit maintainer exception, not because required gates passed. | A later exact combined integration head must pass the full Constitutional CI matrix and installed-wheel evidence jobs. Until then, release and production gates remain blocked. | open |

## Evidence that remains valid

The following bounded evidence is preserved despite the carried-forward failures:

- PR #54 remains an inert, package-private Curator candidate with authority `none`, activation
  `inert`, zero effective capabilities, and zero tools.
- Cleanup run `30661841213` executed all 41 focused Phase 5D tests successfully before Pyright
  stopped publication.
- Earlier Phase 5D installed-wheel, build, secret-scan, dependency/license, and CodeQL jobs produced
  successful receipts where their individual jobs completed successfully.
- One assistant performed separate procedural role passes; authenticated independent Curator or
  Judge execution is not claimed.

## Handoff to Phase 5E

Phase 5E begins from the normal merge commit of PR #54. The Integrator deep playbook must:

1. inventory these five debt items as inherited unresolved integration inputs;
2. preserve their source run IDs and exact commit bindings;
3. prevent any compatibility or release recommendation from treating them as resolved;
4. define a reversible path for removing temporary workflows and closing the static/type failures;
5. keep Phase 5E itself inert, package-private, authority-free, and outside supported API/CLI/runtime
   selection surfaces; and
6. carry any still-open items into the next phase and release court without erasure.
