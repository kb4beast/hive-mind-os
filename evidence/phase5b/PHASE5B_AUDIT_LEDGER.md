# Phase 5B audit ledger

This ledger is append-only. Earlier findings remain visible after repair.

## P5B-AUDIT-001 — scope frozen

Only an inert, package-private Architect deep playbook is in scope. Other Phase 5
roles, live selection, implementation, activation, and `B-OPS-09` are excluded.

## P5B-AUDIT-002 — canonical lineage pinned

The Phase 2 Architect source, generated projection, Generation Zero prompt, built-in
agent, skill, and instruction are all read through digest-checked package resources.

## P5B-AUDIT-003 — option-local claim remand

Initial review found that a claim mapping could point at a valid design ID owned by a
different option. Repair requires every mapping to be a subset of the mapped option's
complete local design-ID set.

## P5B-AUDIT-004 — per-option verification remand

Initial review found that aggregate coverage could allow one option to borrow another
option's verification. Repair requires exact acceptance, invariant, threat, migration,
and rollback coverage independently for every option.

## P5B-AUDIT-005 — trust-boundary remand

Interfaces and trust boundaries must connect distinct components owned by the same
option. Boundary data classes must be declared by local components, and the exact union
of boundary threat IDs must equal the option's threat set.

## P5B-AUDIT-006 — semantic reseal remand

Schema-valid nested outputs could not be trusted solely because their digests were
recomputed. Canonical envelope validation now reconstructs the complete design from the
request snapshot and compares exact bytes. The focused suite mutates and reseals at
least 442 individual output leaves; each altered design is rejected.

## P5B-AUDIT-007 — blocked high-score remand

A caller-supplied high score cannot make an option viable. Rankings order viability
before score and carry explicit violations, unknowns, residual-risk blockers, and
objective-state blockers.

## P5B-AUDIT-008 — reserve-accounting remand

Reserve percentages alone were insufficient. Every known axis now contains exact
rollback reserve, verification reserve, and nine positive design-section quantities
whose sum equals the ceiling. Insufficient indivisible units fail closed.

## P5B-AUDIT-009 — adopted-claim evidence remand

The caller-controlled `material` flag cannot bypass evidence or acceptance. Every
`adopt` or `adapt` claim requires non-empty admitted evidence, non-empty admitted
acceptance criteria, and exact option-local mappings.

## P5B-AUDIT-010 — focused verification

The current focused suite contains 50 test methods, including strict schemas,
determinism, authority, malformed inputs, option locality, complete verification,
trust containment, migration/rollback, resources, mutation, and resealing. The final
inventory, wheel, complete hosted matrix, and exact-head receipts remain pending.

## P5B-AUDIT-011 — local isolated wheel

The local wheel imported the Architect modules from the isolated installation, retained
133 governed JSON resources and 22 components, validated thirteen contracts and ten
outputs, reconciled all four resource axes, and preserved zero effective capabilities,
zero tools, no authority, and inert activation. The local build used setuptools 82.0.1;
hosted setuptools 83.0.0 and exact-head security/provenance gates remain required.

## P5B-AUDIT-012 — current-tree inventory-chain reconciliation

The complete suite correctly detected that Phase 5B's CI and ADR-index additions changed
two files governed by the Phase 5A current-tree inventory. The Phase 5A inventory was
regenerated without changing Phase 5A code, contracts, or historical commits. Its prior
digest `sha256:0628a5236d5e06cceb3055fc65320a339c48cd229f56bfd39ef1ebce0c03d516`
remains recorded here; the reconciled input digest is
`sha256:ff76b245267d244354d99bf136a35088e7169b1e9da9f6afa7afa73ffdc0fa55`.
