# Phase 1 Court: Open Memory

- Case ID: `P1-OPEN-MEMORY`
- Status: characterization adapted for draft publication; architecture deferred
- Original request SHA-256:
  `dbd73add9f47aa98a30d19f1538179e5e961c1452a70b9ce54b7403b4e387a46`

## Participants

Explorer/Clerk/Advocate is `/root/phase1_sources`;
Architect/Cross-Examiner is `/root/phase1_architecture`;
Integrator/Steward/Optimizer is `/root/phase1_runtime`; Builder is `/root`.
Independent Curator and security/privacy Expert is `/root/phase1_curator`.
The distinct Judge is `/root/phase1_judge`.

## Frozen parent claims

- `MEM-001`: Preserve exact and semantic idea duplicates, refinements,
  contradictions, and relationships without silent merging.
- `MEM-002`: Provide open per-repository and federated long-term memory.
- `MEM-003`: Cover and replay complete work history.
- `MEM-004`: Measure memory utility, contamination, staleness, privacy, and
  retrieval quality.
- `MEM-005`: Isolate multiple repositories and prevent unsafe recursion when
  Hive Mind OS operates on itself.

Child claims cover repository identity, record IDs/types/versions, provenance,
confidence, sensitivity, retention, access, supersession/tombstones,
transactional outbox, deterministic retrieval manifests, human corrections,
federation, and deletion/audit reconciliation.

## Generation-zero evidence

`docs/architecture/PHASE1_RUNTIME_PATH_INVENTORY.md` shows fragmented ledger,
mission, scheduler, prompt, experiment, source, and receipt planes. The SQLite
ledger is append-only but does not implement the richer event schema’s digest
chain, stream version, causation, or correlation. Lessons have no read API.
There is no repository identity, safe-public memory pack, federated memory, or
complete replay contract.

## Advocate case

An additive open record and local outbox can unify lineage without replacing
the generation-zero stores. Deterministic projections and retrieval indexes can
remain rebuildable, provider-neutral views over authoritative records.

## Cross-examination and dissent

A universal memory store is a high-impact privacy and integrity target.
Semantic deduplication can leak or falsely merge ideas. Federation can cross
tenant boundaries. Append-only history conflicts with erasure unless sensitive
payload handling and minimal tombstones are designed explicitly. PROV-O and
JSON-LD may add complexity without measured value.

## Acceptance, metrics, and rollback

Candidate architecture is ADR-019. Acceptance includes old/new reconciliation,
event-chain verification, crash recovery without duplicate effects,
retrieval provenance/precision/recall, contamination and staleness rates,
cross-tenant escape rate zero, deletion/privacy receipts, and self-host
recursion tests. Rollback stops v2 writes/projections while retaining all v2
records and the generation-zero stores.

## Open obligations

Source admission, privacy/legal expert testimony, deletion model,
repository/tenant identity, semantic-dedup benchmark, complete event taxonomy,
and architecture-merits judgment remain blocking.

The independent Curator accepted the repaired characterization boundary after
two remands strengthened database, append-only, and telemetry fixtures. That
acceptance does not adopt ADR-019 or activate a memory migration.
The independent Judge adapted this characterization for stacked draft
publication and deferred ADR-019 and Phase 2 authorization.

## Phase 1 merits continuation

The prior deferral remains historical evidence for the earlier candidate.
`PHASE1_CANONICAL_CONTRACTS.md` now fixes repository/tenant identity,
record-envelope, retrieval-manifest, deletion/tombstone, privacy, federation,
outbox, projection, self-host recursion, evaluation, migration, and rollback
requirements. `P1-SOURCE-ADMISSION.md` explicitly decides every memory-related
source without relying on unavailable content.

ADR-019 is now an adopted architecture candidate pending the new independent
Curator and Judge record in `P1-MERITS-COMPLETION.md`. No memory writer,
migration, federation, or projector is implemented in Phase 1.
