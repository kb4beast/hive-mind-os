# Whole-OS acceptance status

Claim scopes are explicit: bounded operational production requires exact candidate,
host, authority, target/runtime, 72-hour observation, restart, and rollback evidence;
full autonomy or superiority additionally requires N30/N31. Roblox is optional.

Campaign disposition: `DEFER` -- the repository implementation is integrated on
`main` and the remaining local execution gaps are repaired by the current successor
candidate. External qualification and elapsed observation remain open. This is not a
production, superiority, or full-autonomy verdict.

This status was reconciled on `2026-09-21` for ADR-091. The trusted local host now
has an exact-baseline startup receipt, and the N32 target scope no longer carries a
hidden Roblox or N30 dependency. The missing bounded-production evidence and the
`DEFER` disposition remain.

## Integrated candidate

- PR #203 was merged to `main` at
  `ed96ffde57304d6b1ab7923e4d219640ac96b44f`, tree
  `34f0332108193851117e159b200c30bacfdbe1e8`. All 12 hosted checks passed, including
  Linux Python 3.11/3.12/3.14 and Windows Python 3.12/3.14.
- A trusted-host bootstrap for that exact clean baseline completed with distinct
  Curator and Builder sessions and 16 passing focused tests. The current successor
  makes claim scope explicit, removes the generic pilot's hidden Roblox requirement,
  and keeps N30/N31 only on the full-autonomy or superiority path.
- The configured composition now joins discovery, bounded building, independent
  qualification, idempotent PR delivery/reconciliation, head-bound feedback, and
  scoped learning. Synthetic two-subject fixtures prove protocol behavior and target
  runtime independence only; they do not prove a live forge or hostile-code backend.
- N27 now requires role-bound external verifier identities, broker/environment leases,
  fresh engine/device observations, and independently attested metric, persistence,
  security, asset, and cleanup payloads. Contract fixtures can yield only
  `RUNTIME_VALIDATED`, never `PRODUCTION_CANDIDATE`.

## Open qualification dispositions

- N03: `ADAPT` for the exact `ed96ffde` trusted local baseline. Its non-synthetic
  startup receipt binds the clean head/tree and distinct Curator/Builder sessions.
  It grants no hard isolation, external delivery, or successor-candidate credit.
- N18/N23/N29: `BLOCKED_CAPABILITY` and `BLOCKED_EVIDENCE` for strong real-backend
  claims. Deterministic negative controls exist; attested hard-isolation, egress,
  secret-probe, evaluator-custody, and exact-candidate real-service execution do not.
- N27: `DEFER` for optional Roblox qualification under ADR-090. The adapter is
  implemented, but there is no admitted game, brokered runtime/test universe,
  multi-client/device harness, or external verifier set. No Roblox support is claimed.
- N30: `BLOCKED_SOURCE` and `BLOCKED_AUTHORITY` for execution. The runner is now
  closed over `AdmittedBenchmarkRunner`, revalidates the live admission immediately
  before each effect, persists intent first, and reconciles uncertain writes without
  duplicate execution. The protocol remains `OPEN_EXTERNAL_EVIDENCE_BLOCKED`; no
  matched real lane ran and no challenger was promoted.
- N31: `BLOCKED_AUTHORITY` and `BLOCKED_EVIDENCE` for the full scope. The durable
  controller enforces leases, concurrency, daily budgets, distinct accepted families,
  restart, and rollback evidence. No sealed real host, self-delivery grant, supervisor
  rollback pointer, or measured candidate receipt exists.
- N32: `BLOCKED_SOURCE`, `BLOCKED_CAPABILITY`, `BLOCKED_AUTHORITY`, and
  `BLOCKED_EVIDENCE`. Coupon Hive and Reese's Rainbow Web are selected as two real
  external candidates, but the exact independently qualified successor candidate,
  successor-bound host receipt, host-issued target profiles, scoped grants, and
  attested runtime receipts are not yet sealed. N30 is additionally required only
  for `full-autonomy-or-superiority`.
- N33: `DEFER`. The closeout schema requires evidence-bearing R01-R18 and N00-N33
  assessments, all roles/stages, attested successful startup/rollback receipts, and a
  judge distinct from the builder. Bounded closeout requires positive N28/N29/N32/N33
  evidence; full closeout requires positive N30/N31/N32/N33 evidence.

For the bounded path, exact successor qualification, host/adapters, scoped pilot
delivery authority, target/runtime receipts, and the two-target observation window
remain open. Comparator intake, rights, evaluator custody, and N30 remain open for
the full scope. Optional Roblox Studio/game/device evidence remains deferred and
outside this release scope. This is therefore a candidate-bound status receipt, not
a production, superiority, or full-autonomy release verdict. A host-owned launcher
must register the exact admitted executable factory before `hive-mind whole-os
start`; configuration cannot name imports, commands, credentials, callbacks, or
secret values.

The color-coded dependency view and deterministic resume boundary are recorded in
`docs/execution/WHOLE_OS_STATUS_DAG.md`.
