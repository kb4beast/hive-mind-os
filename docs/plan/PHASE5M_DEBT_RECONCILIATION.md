# Phase 5M — additive debt reconciliation

- **Predecessor:** Phase 5L reconciliation
  `sha256:981832a1a900b98883c4eea3e052c666df5c084a6719038d6657a7c8b0357dcc`
- **Validated subject:** `da90b4430f8cb99113b58657db7539600e753395`
- **Exact-subject runs:** `30774229678`, `30774230905`
- **Disposition:** 17 resolved, 18 active
- **Reconciliation digest:**
  `sha256:abc6a0ebcb0b676d13529ccf71330cf683a75464d1b017cef6fc7c75a6ecb701`
- **Authority:** none

Phase 5M preserves the Phase 5L 10/25 point-in-time record and adds a successor reconciliation at
`evidence/phase5m/phase5_debt_reconciliation.json`. Seven exact exit conditions are satisfied:

- `P5E-DEBT-02`, `P5F-DEBT-02`, `P5G-DEBT-02`, `P5H-DEBT-02`, `P5I-DEBT-02`, and
  `P5J-DEBT-02` now have chained deterministic inventories, isolated installed-wheel reproduction,
  a permanent CI gate, retained artifacts, and fully successful exact-head workflows; and
- `P5H-DEBT-05` now has its requested exact-final-head chained inventory/wheel, Ruff, global
  Pyright, all-Python, build, and security receipt.

The failed predecessor runs `30773938617` and `30773951801` remain preserved in the Phase 5M audit
ledger. They are evidence that workflow-sealed older inventories failed closed before the complete
A–K chain was regenerated.

Eighteen debts remain active. Eleven require external evidence or authority. Seven are repository-
internal output, governance, or reconstruction tranches. `B-OPS-08` remains active. ADR-015 remains
proposed, so P14/P20 eligibility, authenticated independence, release and production readiness,
deployment, promotion, and superiority remain false.
