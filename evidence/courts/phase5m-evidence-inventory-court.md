# Phase 5M evidence-inventory court

## Case

Whether the repository should adapt the six Phase 5E–5J inventory debt exit conditions into a
single deterministic Phase 5E–5K evidence chain and installed-wheel verification gate.

## Preserved claims

| Claim | Advocate case | Cross-examination | Expert testimony | Disposition |
|---|---|---|---|---|
| Current permanent wheel verification ends at Phase 5D. | The CI workflow contains dedicated Phase 5A–5D steps and no later step. | A successful wheel build alone does not prove later private modules import or validate. | The packaging witness reproduced the gap at base `8ca3449`. | `adopt` |
| Six debt items share one inventory/package/CI exit. | One chain removes duplicated mechanics and verifies all current later components. | Generic logic could hide phase semantics. | Official per-phase validators, exact output orders, and 55 phase-specific boundary assertions retain semantics. | `adapt` |
| Installed imports must be isolated from source. | Relative-to-installed-root checks provide objective evidence. | `PYTHONPATH` can still be misconfigured. | The verifier inspects every imported module file and fails unless it is beneath the supplied root. | `adopt` |
| Passing this court proves release readiness. | None; the implementation explicitly denies it. | External authority, B-OPS-08, ADR-015, and P14/P20 gates remain absent. | Local and hosted CI cannot authenticate external participants or authorize deployment. | `reject` |

## Participants

- Clerk: Phase5M-Inventory-Clerk
- Advocate: Phase5M-Inventory-Advocate
- Cross-Examiner: Phase5M-Inventory-CrossExaminer
- Expert Witness: Phase5M-Packaging-Witness
- Judge: Phase5M-Inventory-Judge

These are distinct procedural identities used by one assistant. No authenticated independence is
claimed.

## Verdict

`adapt`. Implement the reusable chain, isolated installed-wheel verifier, permanent artifact and
attestation step, deterministic tests, rollback record, and exact-head validation. Debt closure is
deferred until the exact implementation head passes hosted push and pull-request workflows.
