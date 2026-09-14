# Whole-OS acceptance status

Campaign disposition: `DEFER` -- the repository implementation is integrated on
`main` and the remaining local execution gaps are repaired by the current successor
candidate. External qualification and elapsed observation remain open. This is not a
production, superiority, or full-autonomy verdict.

## Integrated candidate

- PR #186 was merged to `main` at
  `4a0120a3a564723358f29adb60e34ab34bec5964`. Its Linux and Windows Python matrices,
  static/type checks, CodeQL, secret scan, Autopilot check, SBOM, and build provenance
  all passed on the exact PR candidate.
- The current successor candidate removes four post-merge local gaps: it routes the
  `whole-os start`/`resume` CLI through a sealed host-owned factory, executes N30 only
  through the admitted protocol with durable intent/reconciliation, enforces N31/N32
  concurrency and time/resource/subject/domain evidence, and prevents N33 from
  sealing empty or self-judged evidence.
- The configured composition now joins discovery, bounded building, independent
  qualification, idempotent PR delivery/reconciliation, head-bound feedback, and
  scoped learning. Synthetic two-subject fixtures prove protocol behavior and target
  runtime independence only; they do not prove a live forge or hostile-code backend.
- N27 now requires role-bound external verifier identities, broker/environment leases,
  fresh engine/device observations, and independently attested metric, persistence,
  security, asset, and cleanup payloads. Contract fixtures can yield only
  `RUNTIME_VALIDATED`, never `PRODUCTION_CANDIDATE`.

## Open qualification dispositions

- N03: `BLOCKED_EVIDENCE` for production use. The replaceable host/profile contracts
  exist, but no current production host attestation or sealed configured-host binding
  was supplied.
- N18/N23/N29: `BLOCKED_CAPABILITY` and `BLOCKED_EVIDENCE` for strong real-backend
  claims. Deterministic negative controls exist; attested hard-isolation, egress,
  secret-probe, evaluator-custody, and exact-candidate real-service execution do not.
- N27: `BLOCKED_SOURCE`, `BLOCKED_CAPABILITY`, and `BLOCKED_AUTHORITY` for real Roblox
  qualification. The adapter is implemented, but there is no admitted game, brokered
  runtime/test universe, multi-client/device harness, or external verifier set.
- N30: `BLOCKED_SOURCE` and `BLOCKED_AUTHORITY` for execution. The runner is now
  closed over `AdmittedBenchmarkRunner`, revalidates the live admission immediately
  before each effect, persists intent first, and reconciles uncertain writes without
  duplicate execution. The protocol remains `OPEN_EXTERNAL_EVIDENCE_BLOCKED`; no
  matched real lane ran and no challenger was promoted.
- N31: `BLOCKED_AUTHORITY` and `BLOCKED_EVIDENCE`. The durable controller now enforces
  leases, concurrency, daily budgets, distinct accepted families, restart and rollback
  evidence. No sealed real host, self-delivery grant, supervisor rollback pointer, or
  measured candidate receipt exists.
- N32: `BLOCKED_SOURCE`, `BLOCKED_CAPABILITY`, `BLOCKED_AUTHORITY`, and
  `BLOCKED_EVIDENCE`. No admitted ordinary target or rights-cleared Roblox subject,
  runtime/test universe, device matrix, target grants, or N30 candidate exists.
- N33: `DEFER`. The closeout schema now requires evidence-bearing R01-R18 and N00-N33
  assessments, all roles/stages, attested successful startup/rollback receipts, and a
  judge distinct from the builder. A positive verdict is structurally impossible
  while N30/N31/N32 are incomplete.

Complete source ingestion and comparator reuse rights, production host/adapters,
signed evaluator custody, scoped pilot delivery authority, real comparator receipts,
and Roblox Studio/game/device evidence remain open. This is therefore a
candidate-bound status receipt, not a production, superiority, or full-autonomy
release verdict. A host-owned launcher must register the exact admitted executable
factory before `hive-mind whole-os start`; configuration cannot name imports, commands,
credentials, callbacks, or secret values.

The color-coded dependency view and deterministic resume boundary are recorded in
`docs/execution/WHOLE_OS_STATUS_DAG.md`.
