# Version 1.1 integration hardening court

- Case: `VERSION-1.1-INTEGRATION-HARDENING`
- Base release head: `07b19ba809b1be24d50f64de5a8704a760414db0`
- Historical omitted candidate: PR #30 at `39e07c9e3c3ce439911481be2d38d901d05d4824`
- Burden: reversible draft integration evidence only
- Independence: procedural single-model role simulation; not authenticated independent actors

## Atomic issues

1. Preserve the exact pre-hardening release head.
2. Preserve and adjudicate PR #30 without adding a second active foundation.
3. Replace the missing off-repository Phase 5A handoff with a conservative,
   source-bound reconstruction and mark the stale handoff superseded.
4. Align the selected setuptools 83.0.0 pin with its governance test.
5. Repair ADR/release/version terminology and machine-readable scope records.
6. Produce an exact-head audit, wheel/resource, SBOM, provenance, security, dependency,
   type, lint, and Python-version evidence set.
7. Run all Hive Mind role purposes and retain dissent without calling one model
   independent.
8. Publish only an open draft PR; do not merge or modify original refs.

## Advocate

The accepted stacked tree contains substantial working code and evidence, but a
release integration is trustworthy only when omitted history, stale handoffs,
configuration drift, and exact-head evidence are made explicit. A tree-neutral merge
can preserve PR #30 without selecting its obsolete package, and one machine-readable
audit can continuously verify the integrated contract.

## Cross-examination

- Adding PR #30 files would create competing authorities and ambiguous migrations.
- A prose-only claim that PR #30 was superseded could still lose exact bytes.
- The previous package pin mismatch proves that ancestry alone does not prove an
  integrated tree is coherent.
- Procedural role labels are not authenticated independence.
- Green CI does not satisfy P20 or authorize activation, value, learning, promotion,
  superiority, or a merge into `main`.

## Expert findings

The selected design uses exact Git ancestry for historical preservation, a qualified
ADR collision, an atomic claim disposition map, a canonical release manifest, a
strict repository audit, dynamic package-version extraction for the SBOM, and hosted
artifact/provenance binding. The stale Phase 3 handoff remains visible but is marked
non-executable. The reconstructed Phase 5A objective cites only controlling records
and states that the unavailable original wording was not recovered.

## Integrated inventory reconciliation

The first affected-chain run reproduced four exact-inventory failures. The cause was
not a runtime regression: PR #7 changed `pyproject.toml` after Phase 3/4 inventory
receipts were sealed, and this hardening also qualified the ADR-021 registry collision.
The current inventory chain was regenerated in dependency order from Phase 3 item 3
through Phase 4D. Historical digests remain point-in-time evidence in prior commits and
are mapped to the new current-tree digests in
`evidence/releases/version_1.1/inventory-reconciliation.json`. The affected 152-test
regression set passes with two platform-specific skips.

## Simulated specialist dispositions

The machine-readable role record covers Orchestrator, Explorer, Architect, Builder,
Cross-Examiner, Curator, Integrator, Steward, Optimizer, and Judge purposes. All
recommend `adapt` for the bounded hardening candidate. The record explicitly denies
that these are separately authenticated actors.

## Judge disposition

**ADAPT** for an open draft PR and exact-head evidence only, subject to:

- the pre-hardening archive ref remaining intact;
- PR #30 exact head becoming an ancestor through a verified zero-tree-delta merge;
- all tests and hosted checks passing on the final exact head;
- the original PRs and source branches remaining untouched; and
- the PR remaining draft and unmerged.

No merge, runtime activation, release readiness, production scope, customer value,
learning, promotion, or superiority claim is authorized. `B-OPS-09` and P20 remain
open. A later release decision requires authenticated independent reconstruction and
the literal P20 burden.

## Rollback

Close or abandon only the hardening draft branch/PR while retaining all commits,
archive refs, source PRs, and court evidence. Never delete PR #30 history or rewrite
an original branch to simulate a clean result.
