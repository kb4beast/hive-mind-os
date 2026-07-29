# Portable checkpoint — Phase 2 additive foundation

- Branch: `codex/phase2-additive-memory-telemetry-foundation`
- Stack base: PR #29 exact head `3298078c41ce69103eb2bdce61960a69dc6aab93`
- Accepted Phase 2 candidate:
  `69ae532566ba0f780b7fb24832dee70484aa738d`; independently accepted by Curator
  `Kuhn`, Steward `Planck`, and Judge `Ohm`; not activated or merged
- Governing ADR: ADR-021
- Court: `evidence/courts/phase2-additive-foundation-court.md`
- Inventory: `evidence/phase2/phase2_foundation_inventory.json`
- Exact verification: push run `30430857403`, PR run `30430863499`, artifact
  `8715442587`, provenance attestation `37680789`

Implemented:

- 17 strict additive contracts, 8 canonical agent sources, and 9 deterministic inert
  agent/manifest artifacts;
- private scoped SQLite/WAL foundation store with record chains and transactional
  outbox;
- encounter-first concurrent exact/structured opportunity deduplication;
- semantic-candidate classification without automatic merge;
- provider-shaped native usage observations and orthogonal normalized axes;
- started/terminal attempt receipts, restart interruption recovery, and an opt-in
  provider wrapper;
- append-only delivery attempts/acks, bounded metrics, correlated local traces,
  disabled-export OpenTelemetry envelope, and invoice gap reconciliation;
- enforced authority/action/public-release boundaries and privacy/body rejection;
- self-identifying store admission, full-command idempotency, canonical integrity,
  destination-bound delivery, bounded provider observations, and retry-preserving
  physical-attempt receipts.
- complete canonical memory-kind/retrieval coverage, scoped outbox access, atomic
  initialization, subject-bound release provenance, typed semantic staging,
  opportunity-key integrity, strict agent subcontracts, enforced canonical
  self-digests/generator versions, bounded traces, and explicit per-axis
  reconciliation without cross-axis totals.
- bounded caller-supplied usage attribution preserved through terminal and recovery
  receipts; bounded normalized integers; fixed billable-status reconciliation;
  direct/OTel trace boundary validation; and cross-repository opportunity-key
  integrity.
- process-local issuer-sealed authority decisions verified at every store boundary;
  direct fabrication and post-issuance mutation fail closed.
- fail-closed installed-wheel SPDX generation and package identity verification;
  immutable upload and provenance name both wheel and SBOM.

Unchanged:

- Generation Zero runtime selection and stores;
- 131 root APIs, 33 package APIs, 13 CLI contracts;
- legacy schemas/resources and Phase 1 historical inventory;
- Obsidian/Phase 3 and later behavior.

Phase 2 is fully complete as an inert additive foundation. After sealing this
evidence-only descendant and rechecking its exact head, the next eligible objective
is Phase 3 item 1: implement a portable per-repository memory pack and deterministic
projection with a CLI/editor-only path. Start it on a new stacked branch from the
final PR #31 head. Do not activate Phase 2, merge either PR, or add Obsidian-dependent
behavior to this checkpoint.
