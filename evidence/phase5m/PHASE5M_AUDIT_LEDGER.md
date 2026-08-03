# Phase 5M audit ledger

This is an append-only procedural ledger. Distinct labels below are separate acting identities but
not authenticated external participants.

## Entry 1 — source intake

- **Clerk:** Phase5M-Inventory-Clerk
- **Subject base:** `8ca34497051a9b50927f3615df49506f79d0046e`
- **Sources preserved:** `docs/plan/PHASE5_CARRIED_FORWARD_DEBT.md`,
  `docs/plan/PHASE5J_CARRIED_FORWARD_DEBT.md`, and
  `evidence/phase5l/phase5_debt_reconciliation.json`
- **Atomic claim:** six active debt items require chained Phase 5E–5J inventories, installed-wheel
  verification, package verification, permanent CI, and exact-head receipts.
- **Provenance:** repository-local MIT-licensed records at the exact subject base; no external source
  or copied implementation was used.

## Entry 2 — adversarial design review

- **Advocate:** Phase5M-Inventory-Advocate
- **Cross-Examiner:** Phase5M-Inventory-CrossExaminer
- **Expert witness:** Phase5M-Packaging-Witness
- **Findings:** separate per-phase scripts would duplicate boundary logic and make later drift easy;
  one generic chain must still retain phase-specific official validators, ordered output fields, and
  semantic boundary assertions. Import success alone is insufficient because it can accidentally
  resolve to the editable source tree.
- **Mitigations:** exact predecessor verification, per-link digests, phase-specific assertions,
  explicit installed-root import checks, isolated wheel reproduction, and retained JSON evidence.

## Entry 3 — procedural judgment

- **Judge:** Phase5M-Inventory-Judge
- **Disposition:** `adapt`
- **Reason:** implement the six requested inventory exits as one reusable Phase 5E–5K chain so the
  newest package-private component is not left outside permanent verification. Reject any inference
  that local inventory or CI evidence establishes authenticated independence or release authority.
- **Appeal:** permitted through a later append-only court record.

## Entry 4 — local builder receipt

- **Builder:** Phase5M-Inventory-Builder
- **Curator:** Phase5M-Inventory-Curator
- **Result:** 80 focused tests passed; Ruff passed; Pyright 1.1.411 reported zero findings; an
  isolated wheel imported and validated all seven Phase 5E–5K implementations and contracts.
- **Wheel digest:**
  `sha256:19b27f7688f7e523a099e93b3c55ac1fb2157a0b4145e4691619cce2bae6b75e`
- **Inventory tail:**
  `sha256:4efbbe2e70e2d000fedde4dbf425df8ed5e7a6986778c8d52f0d3faf254d5ef8`
- **Limit:** the six debts remain active pending exact committed-head hosted receipts.

## Entry 5 — failed hosted reconstruction and successor

- **Failed receipts:** push run `30773938617` and pull-request run `30773951801` on
  `5dc751af7c879768ce0ee59c4b8768470bd9fe29`
- **Observed failure:** Python 3.11 and 3.14 each rejected the committed Phase 5A, Phase 5B, and
  Phase 5C inventories as different from deterministic current-tree rebuilds.
- **Root cause:** those historical generators deliberately include `.github/workflows/ci.yml` in
  their implementation digests. Adding the Phase 5E–5K permanent verifier changed that protected
  input, so the old artifacts became stale as designed.
- **Successor action:** regenerate Phase 5A, update and regenerate the A→B predecessor digest,
  repeat through Phase 5D, then regenerate Phase 5E–5K from the new verified Phase 5D tail.
- **New chain digests:** Phase 5A
  `sha256:6c8b884901bccab1988fd5fc9ffabecb231127c2af72aa4d897067e1e05e439c`;
  Phase 5D `sha256:dc85f9729df4152f8a156f5ce779777711bda32b9b315d48f3a4e36a785052ad`;
  Phase 5K `sha256:4efbbe2e70e2d000fedde4dbf425df8ed5e7a6986778c8d52f0d3faf254d5ef8`.
- **Disposition:** retain both failed runs; require fresh exact-successor push and pull-request runs.

## Entry 6 — exact-successor closure receipts

- **Subject:** `da90b4430f8cb99113b58657db7539600e753395`
- **Push run:** `30774229678`, fully successful
- **Pull-request run:** `30774230905`, fully successful
- **Verified gates:** Python 3.11/3.12/3.14, Ruff, Pyright 1.1.411, CodeQL, secret scan,
  dependency/license review where applicable, wheel build, installed Phase 5A–D verification,
  installed Phase 5E–K verification, SPDX SBOM, artifact upload, and push attestation.
- **Judge:** Phase5M-Closure-Judge
- **Disposition:** adopt closure of `P5E-DEBT-02`, `P5F-DEBT-02`, `P5G-DEBT-02`,
  `P5H-DEBT-02`, `P5H-DEBT-05`, `P5I-DEBT-02`, and `P5J-DEBT-02`; retain all other
  active debt and every external gate.
- **Successor reconciliation:**
  `sha256:abc6a0ebcb0b676d13529ccf71330cf683a75464d1b017cef6fc7c75a6ecb701`
