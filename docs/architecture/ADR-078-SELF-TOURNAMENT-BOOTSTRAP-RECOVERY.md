# ADR-078: Self-tournament bootstrap recovery

Date: 2026-09-09
Status: adapted for local implementation; final self-tournament evidence pending

## Sources and atomic claims

- `origin/main@fa4ec7bc709a447c317f729d44cf046d5e2d6cda`, retrieved 2026-09-09, repository license applies. This is the merged generic tournament runtime from PR #171.
- The owner-directed self-tournament plan `sha256:568eee920336593ad8e03dafed9629b841b01f1ecda2153dec126d53ed67822c`, stored outside the repository under `self-tournament-live-2026-09-09/prepared`, is private operational provenance. It requires a real model-backed run against the merged repository and forbids substituting deterministic fixtures.
- Failed run state retained outside the repository under `self-tournament-live-2026-09-09/state` recorded a Windows path-copy failure before `RUNTIME-030` could execute.
- Failed run state retained at `C:\h\s1` recorded 12 fresh model sessions and a 10/13-node terminal result. Its sealed runtime audit executed 38 focused tests; 22 errored because the scrubbed Windows environment omitted the identity variable required by `getpass.getuser()`. The selection court deferred its revised proposal because no post-revision examiner existed. The no-change builder then preserved the pinned candidate, but `VERIFY-070` blocked because the runtime supplied no positive no-change receipt.
- Failed run state retained outside the repository under `self-tournament-live-2026-09-09/state-r3` recorded 11 fresh model sessions and an 8/13-node terminal result. Extended-path materialization succeeded, but target tests that themselves create nested Git repositories exceeded Git for Windows' internal `$GIT_DIR` limit under the deep evidence prefix. The new post-revision examiner completed and the judge selected a bounded experiment, but their combined measured input exceeded the sealed 180,000-token court allocation, so the runtime correctly refused to record court completion.

These receipts are evidence of bootstrap defects. They do not authorize promotion, merge, push, deployment, credential use, or weaker acceptance criteria.

## Court

Advocate (Architect identity): the runtime should be able to run its own supported operator-local profile through terminal judgment. Windows path aliases, a scrubbed but usable non-secret operator identity, post-revision challenge, and no-change verification are necessary parts of that contract.

Cross-examiner (Curator identity): extended paths must not leak into receipts or command arguments; retaining an ambient username must not reopen general environment inheritance; a re-examiner must remain distinct from the judge; and no-change verification must never be represented as tests passing or as proof of implementation value.

Expert witness (Steward identity): Win32 extended path syntax is limited to the host copy operation. The username name and value can be explicitly included in the content-digested receipt while all other ambient variables remain scrubbed. The existing fresh-session checks can validate a separate re-examiner. A clean candidate pinned to the exact base commit is objectively verifiable without executing irrelevant tests.

Judge (Integrator identity), distinct from the identities above: **adapt**.

## Decision

1. Deep verification copies use Win32 extended paths only during the host filesystem copy. Recorded paths and child-process arguments remain ordinary resolved paths.
2. On Windows, the sealed verification environment retains `USERNAME` when present. It remains an explicit, receipted non-secret identity field; arbitrary ambient variables and secrets remain excluded.
3. Before `COURT-050` judges a revised proposal, the runtime dispatches a fresh post-revision cross-examiner. Its actor, role, transcript, report, and session are retained beside the judge, and the existing no-session-reuse gate applies.
4. When the selection court authorizes no experiment, independent verification records the exact expected and observed commit, observed tree, and clean working-tree result. It reports zero tests and a no-change status; it must not claim test success or implementation value.
5. A failed or changed no-change candidate remains fail-closed. A selected experiment still requires actual sealed focused tests.
6. The court's two independent model sessions share the existing sealed budget. Court source packets are capped below the general evidence-packet maximum, and the judge receives digest-linked adjudicative fields rather than a duplicate of the examiner's full retained dossier.
7. Operator-local Windows runs use a short external private-state root when target tests create nested Git repositories. Deep brain and plan paths remain supported; Git's internal nested-repository limit is retained as an explicit platform limitation rather than represented as hostile-code isolation.

## Acceptance and rollback

Acceptance is executable in `tests/test_verification_adapters.py` and `tests/test_local_dag_runtime.py`, followed by `python -m unittest discover -s tests -v` with `PYTHONPATH=src`. Final operational acceptance additionally requires a fresh real model-backed self-tournament pinned to the repaired commit, complete external brain publication, candidate verification, and reversible delivery evidence.

Rollback is one branch revert. Both failed run histories remain immutable external evidence. Reverting this change does not alter the champion, protected references, or external systems, but restores the demonstrated inability to complete the supported Windows self-run.
