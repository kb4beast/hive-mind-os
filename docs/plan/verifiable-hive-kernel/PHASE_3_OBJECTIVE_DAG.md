# Verifiable Hive Kernel: Phase 3 objective DAG

Phase 3 adds a bounded local-only planning surface over the Phase 2 event spine.
`ObjectiveGraph` validates typed work items before persistence. The deterministic fixture
planner supports `bugfix`, `feature`, `refactor`, `docs`, and `integration`; identical
charter inputs produce identical plan and graph digests.

`hive-mind kernel plan MISSION_ID --charter CHARTER.json --fixture docs --state-dir
STATE_DIR` appends a fixture plan to an existing local kernel mission. `kernel graph`
with the same charter/state arguments reads the durable graph and ready work. Both
commands remain local; graph opens the database read-only.

The implementation deliberately defers any model planner, authority issuer, scheduler,
or effect execution. Replan records supersession events instead of deleting a prior
graph. Rollback removes the additive planner modules and CLI commands; Phase 2 events
and all legacy mission paths remain unchanged.

Full local-gate receipt is recorded with the Phase 3 commit. Independent courtroom
disposition remains an open obligation.
