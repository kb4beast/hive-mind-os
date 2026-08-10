# Parallel Execution

The initial dependency waves are:

| Level | Mode | Nodes | Minimum route tiers |
|---:|---|---|---|
| 0 | serial/gated | BOOT-000 | T2 |
| 1 | parallel | RECON-010, BASE-020 | T2 |
| 2 | serial/gated | ARCH-100 | T4 |
| 3 | serial/gated | CONTRACT-110 | T4 |
| 4 | parallel | ROLE-200, CONSULT-210, EFFECT-220, CONTEXT-230, ACCEPT-240, RECONCILE-250, MIGRATE-260 | T3, T4 |
| 5 | parallel | ORCH-300, EXPLORER-310, ARCHITECT-320, BUILDER-330, CURATOR-340, INTEGRATOR-350, STEWARD-360, OPTIMIZER-370, COURT-380 | T2, T3, T4 |
| 6 | serial/gated | MISSION-400 | T4 |
| 7 | parallel | DURABLE-410, DELIVERY-420, HUMANLESS-430, CHEAT-440, LEARN-500 | T3, T4 |
| 8 | serial/gated | SELFHEAL-450, MIGRATION-460, CHALLENGER-510, POISON-540 | T3, T4 |
| 9 | serial/gated | EVAL-520 | T4 |
| 10 | serial/gated | PROMOTE-530, BENCH-600 | T3, T4 |
| 11 | serial/gated | QUALIFY-610 | T4 |
| 12 | serial/gated | LEGACY-620 | T4 |
| 13 | serial/gated | A3-700 | T4 |
| 14 | serial/gated | A4-800 | T4 |
| 15 | serial/gated | A5-900 | T4 |

## Rules

- Start only nodes emitted by `autopilot ready` after live GitHub reconciliation.
- Every worker must win its remote claim before product work.
- Do not run two nodes with overlapping file or semantic locks.
- A worker stops after opening its draft PR and publishing its receipt; it does not merge.
- Downstream nodes start only after dependencies are merged into target and their receipts validate.
- Integration and promotion nodes remain serial even when all inputs are ready.
- When main advances outside the plan, stop new claims and run reconciliation.
- On CI failure, start a repair session for the same node/branch rather than a downstream node.

The longest dependency chain contains 16 nodes:

`BOOT-000 -> RECON-010 -> ARCH-100 -> CONTRACT-110 -> ROLE-200 -> ORCH-300 -> MISSION-400 -> LEARN-500 -> CHALLENGER-510 -> EVAL-520 -> PROMOTE-530 -> QUALIFY-610 -> LEGACY-620 -> A3-700 -> A4-800 -> A5-900`
