# Whole-OS acceptance status

Final disposition: `DEFER` -- the implementation candidate is usable for local and
configured-host qualification, but N30–N33 cannot close without their external
evidence and observation windows.

## Integrated candidate

- PR #185 was merged to `main` at
  `428af931342820d8f7350bf0f7664115b6257302`.
- Its immutable Linux test matrices, static/type checks, CodeQL, secret scan,
  Autopilot control-room check, SBOM, and build provenance passed. Windows matrices
  were still executing when this successor qualification packet was prepared.
- N28/N29 integration, recovery, adversarial, benchmark-contract, pilot-runtime, and
  qualification checks passed locally with `PYTHONPATH` bound to the exact admitted
  checkout.
- The N27 successor adds a fail-closed Studio/runtime/device receipt adapter, closed
  evidence schema, and negative tests. A signed Studio installation was discovered,
  but no game or admitted runtime session was executed.

## Open dispositions

- N30: `DEFER`. The frozen protocol is `OPEN_EXTERNAL_EVIDENCE_BLOCKED`; no matched
  lane ran and no challenger was promoted. See
  `docs/benchmarks/whole-os-results-20260914-428af93.md`.
- N31: `BLOCKED_AUTHORITY` and `BLOCKED_EVIDENCE`. No sealed Whole-OS host binding,
  self-delivery grant, supervisor rollback pointer, or measured candidate exists.
- N32: `BLOCKED_SOURCE`, `BLOCKED_CAPABILITY`, `BLOCKED_AUTHORITY`, and
  `BLOCKED_EVIDENCE`. No admitted ordinary target or rights-cleared Roblox subject,
  runtime/test universe, device matrix, target grants, or N30 candidate exists.
- N33: `DEFER`. Its 72-hour self/external outcome windows and final requirement-to-
  receipt closeout cannot start while N31 and N32 are blocked.

Complete source ingestion and comparator reuse rights, production host/adapters,
signed evaluator custody, scoped pilot delivery authority, real comparator receipts,
and Roblox Studio/game/device evidence remain open. `CloseoutManifest` still requires
dispositions for N00–N33 and evidence mappings for R01–R18. This is therefore a
candidate-bound status receipt, not a production, superiority, or full-autonomy
release verdict.
