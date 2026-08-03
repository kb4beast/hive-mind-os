# Phase 5O audit ledger

## Entry 1 — source and claims

- Clerk: P5O-Governance-Clerk
- Subject base: `60b76a3ea858f20d1cd126cc223573adb2857c5e`
- Sources: Phase 5E/F/G contracts, tests, inventories, audit ledgers, carried-debt records, hardened
  vision, ADR-014, ADR-015, benchmark and source-docket rules.
- License/provenance: repository-local MIT records; no external code, dataset, comparator, or factual
  result was introduced.
- Atomic claims: the named governance records were absent; record existence can be supplied locally;
  execution, recovery, evaluation, independence, and promotion cannot be supplied locally.

## Entry 2 — debate and judgment

- Advocates: P5O-E/F/G-Advocate
- Cross-Examiners: P5O-E/F/G-CrossExaminer
- Witnesses: P5O-Contract/Ops/Eval-Witness
- Judges: P5O-E/F/G-Judge
- Verdicts: `adapt` E and F governance; `defer` G promotion while adopting fail-closed custody
  records. Reject every inference of executed compatibility, recovery, evaluation, or release.

## Entry 3 — local builder/curator receipt

- Record:
  `sha256:13499ff4a27a3e4f20a78c6e9695bb7ed83354ca4da7d3cd25b0e3699c2a83a6`
- Six deterministic/adversarial tests passed.
- Ruff passed; Pyright 1.1.411 reported zero findings.
- Every required document path is present and SHA-256 sealed.
- Limit: `P5E/F/G-DEBT-03` remain active pending exact-head hosted receipts.

## Entry 4 — failed inventory reconstruction and successor

- Failed push run: `30775991954`
- Failed pull-request run: `30776007077`
- Subject: `26c21db8df2c0b0b8574f874111f02794fa81322`
- Observation: Python 3.11/3.12/3.14 rejected current-tree Phase 5A–D inventory reconstruction.
- Root cause: Phase 5A–D intentionally seal `docs/architecture/ADR_INDEX.md`; adding ADR-037–039
  changed that protected input. Phase 5N's D-root check exposed all four stale links.
- Successor: regenerate Phase 5A, update each hard-coded predecessor digest through Phase 5D, then
  regenerate the Phase 5E–K chain. Preserve both failed runs; require fresh exact-head workflows.
