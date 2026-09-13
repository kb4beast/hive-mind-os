# Generic user-guide implementation

Builder identity: `/root/generic_guide_builder`. Scope delegated by `/root`:
three documentation files in isolated `C:\h\node-guide1`, branch
`codex/generic-dag-guide`, base `b19b2a177e2d10ebf49b565dcdd1ad9878bbaeac`,
tree `6fb9b59c4c697ae9b9bc296676783f8ce662f3c0`.

This implements the separately deferred generic-guide alternative from
`C:\h\node-completeness-audit\next-delivery\RECOMMENDATION.md`. That independent
review identified missing guide entry paths and the stale bootstrap entry point.
The owner waived preimplementation tournament gates. This report is builder
evidence, not independent verification, a court verdict, or node acceptance.

## Changes and claims

| Claim | Implementation/source evidence |
|---|---|
| Installed interface can inspect exact portable plans and write inert canonical output. | New guide with installed help, absolute paths, provenance-derived digest and identity expectations, validate/rounds/graph/build templates. `cli.py`, `dag_cli.py`, `dag_standard.py`, `subject_execution.py`, `pyproject.toml`. Twelve inert CLI commands independently executable through `validate_guide.py`; exact transcripts retained. |
| Default external execution refusal and operator-local execution are distinct. | Profile table and explicitly effectful local template. `dag_cli.py`, `local_dag_runtime.py`, `compiled_tournament.py`, `local_run_authority.py`, `local_codex_worker.py`. No local run dispatched by this work. |
| Progress/resume formats must not be conflated. | External `dag status` reads SQLite; local `status.json` and brain index are derived views with durable signed source evidence. `subject_execution.py:status`, `local_dag_runtime.py:_publish`, `_events`, and `execute`. Missing SQLite status is not presented as absence of local progress. |
| Existing bootstrap history remains accessible. | New guide index links every existing guide; start page adds current-entry links and historical context. Validation compares entire previous start-page body to the new content, preserving it verbatim after newline normalization. |
| Documentation does not grant or claim release/node authority. | Current-run completeness must bind its own accepted receipts; local identities are under one account, local status does not imply independent administration, promotion remains false. No generated live plan or signing credentials supplied. |

## Architecture, threat, compatibility, migration, rollback

The change is a documentation entry-point repair; no architecture, runtime,
schema, policy, authority, evidence parser, or execution wiring changes. The
guide links existing runtime and authoring contracts. It explains the existing
host-custody boundaries, stale/substituted input rejection, uncertain interrupted
effects, and risks of confusing local authentication with independent principals.

Compatibility: all historical guide paths and the old start-page body remain.
The build template uses only behavior present at the pinned base, independently
of the separate expected-identity forwarding repair. No receipt migration is
needed. No live state migration or activation is performed. Rollback is a revert
of these three documentation changes; repository/candidate/state remain outside
this documentation delivery.

## Validation and limitations

- `VALIDATION.json`: 21 exact base Git blobs with Git object IDs, raw SHA-256,
  byte counts; 15 local links resolve; original start-page body retained; 12 CLI
  commands pass in an external fixture folder. Checks cover help, inspections,
  canonical build, no-overwrite refusal, absent-state status, default external
  execution refusal and mismatched identity rejection.
- `POWERSHELL-SYNTAX.json`: all five fenced PowerShell examples parse; execution
  templates were not executed.
- `git diff --check` passes.
- All source material is from this MIT-licensed repository, versioned at the
  base above; `LICENSE` bytes are included in the source manifest. No external
  source ingestion or copied third-party code.
- Local execution/resume behavior is source-grounded, supported by cited
  existing tests, not a new live run or a claim those test suites passed here.
  Full gate, exact-head independent review, Git commit/push, and PR qualification
  belong to the root delivery process and have not been performed by this builder.
- No claim that AC-PUBLIC-GUIDE/AC-HANDOFF-GUIDE, their enclosing nodes, or all
  nodes are accepted complete is made. Applicable current-generation acceptance
  evidence and external authority remain separate obligations.

The initial inspection attempted absent `USER_GUIDE/README.md` (the intended gap)
and an incorrect guessed `local_runtime_cli.py` path. The latter was corrected
to actual `local_dag_runtime.py`; no missing-source content was invented. No
implementation attempt or validation failure has been hidden.
