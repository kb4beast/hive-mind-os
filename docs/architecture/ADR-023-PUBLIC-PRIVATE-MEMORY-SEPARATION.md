# ADR-023: Public/private memory release-store separation

- Status: adopted as the Phase 3 item 2 architecture candidate; implementation
  judgment and activation remain pending
- Date: 2026-07-29
- Exact base: `7f7013c99d86bbd34f966b902bb873cf5c10d740`
- Governing records: ADR-019 through ADR-022 and
  `P3-MEMORY-SEPARATION-002`
- Constitutional impact: yes; additive contract and authority action only

## Context

Phase 2 stores private, internal, and independently released safe-public records in
one private append-only Foundation database. Phase 3 item 1 reads that database
through a verified safe-public filter and publishes a deterministic metadata-only
pack. That prevents disclosed private rows from entering the pack, but the projector
still needs read access to the mixed database. Item 1 also places its recovery state
in an ignored directory inside the repository by default. Ignore rules are not
privacy controls.

Path-only relocation of the Foundation database would reduce accidental Git
disclosure but would not create a low-privilege public read boundary. Modifying the
Foundation v1 schema would invalidate Phase 2's frozen schema digest and rollback.

## Decision

Add an opt-in, single-tenant/repository `PublicMemoryReleaseStore`. It is a separate
self-identifying SQLite file with its own schema version and schema-object digest. It
contains only:

- immutable store/scope/origin-policy metadata;
- append-only `hive-public-memory-envelope/v1` documents;
- deterministic release IDs and public-envelope digests; and
- the source release decision reference and independently attributable decider already
  admitted for publication.

It contains no private/internal/quarantined or unsupported records, protected content
references, retrieval receipts, runtime sequence/version gaps, authority or lease
credentials, idempotency keys, private omission counts, runtime relation tables,
opportunity keys, usage/telemetry, outbox, delivery attempts, acknowledgements,
paths, prompts, responses, tool bodies, or private error text.

Materialization is a one-way transformation:

```text
private Foundation store
  -> verified consistent safe-public snapshot
  -> strict public envelope
  -> append-only public release store
  -> separated item-1 projector
  -> existing deterministic public pack
```

The Foundation database remains canonical and byte/schema unchanged. The release
store is nonauthoritative release persistence. Generated Markdown remains a
nonauthoritative projection.

The new `foundation.public-memory.release` action requires the same authentic
role/policy/lease/adapter/risk/budget intersection as other material Foundation
writes. It cannot classify a record or manufacture public approval. Each source must
already have safe-public storage and payload sensitivity, an independent release
decision bound to the complete source payload digest, and no quarantine.

The item-2 transform additionally requires `protected_content_ref` and
`retrieval_receipt` to be null. The public-envelope digest is computed only over the
released fields. The release-policy digest binds the exact public-field allowlist,
required-null fields, policy version, and envelope version. A separately protected
private receipt binds source record IDs/digests, source cursor/counts, redaction
policy, public envelopes, destination logical digest, authority/lease, and scope.
A bounded self-contained private journal lets restart finish earlier pending batches
before considering a newer Foundation snapshot.

The separated projector accepts only the public-store ownership marker. Its private
locks, journals, staged bytes, completion receipts, and conflicts use an explicit
protected state root disjoint from the repository. It can reproduce the item-1 public
tree while the private Foundation database is unavailable.

The accepted item-1 `project` and `check` entrypoints remain for compatibility but
are characterized as direct mixed-store projection, not item-2 separation. The
dedicated module adds `release`, `project-separated`, and `check-separated`; the 13
frozen `hive-mind` parsers do not change.

## Source, license, and dependency disposition

No new external source, dependency, template, or copied code is admitted. The design
uses repository-owned contracts and directly tested Python/SQLite/filesystem
behavior. `P1SRC-OBSIDIAN-HELP` remains factual-reference-only with unresolved
documentation-reuse terms. Obsidian, Canvas, plugins, Sync, watchers, and external
security products are irrelevant to item 2.

Claims about encryption, secure deletion, crypto-erasure, operating-system access
control, backup destruction, or malicious-writer resistance require separately
pinned authoritative sources and tests; they are not made here.

## Threats and dissent

- A safe-public release is an irreversible disclosure to recipients, Git history,
  clones, caches, and artifacts. Tombstones cannot restore secrecy.
- Public IDs, timestamps, decision references, and unkeyed source digests may still
  allow correlation or membership inference. Independent release remains mandatory.
- SQLite append-only triggers and schema digests provide integrity/admission evidence,
  not encryption or resistance to an attacker who can rewrite code and files.
- Process-local authority seals are not durable external identity authentication.
- The public and private commits are not one distributed transaction. A protected
  self-contained journal plus deterministic idempotency repairs the tested crash
  windows, including a changed source snapshot; it does not claim exactly-once
  distributed delivery.
- An external protected root is placement hardening, not proof of ACLs, encryption,
  safe backups, retention, or crypto-erasure.
- One public store represents one tenant/repository scope. Broader physical tenant
  isolation and federation remain item 6.

## Migration

This item does not mutate, relabel, acknowledge, move, raw-copy, or delete a
Foundation database or outbox row. It reads one verified transaction, creates or
opens an empty/same-scope public release store, appends deterministic released
envelopes, and checks that separated projection matches the direct item-1 public tree
for the same eligible fixture.

Existing item-1 packs are not silently adopted as release stores. Existing
Foundation files may be used only in place, quiescent and outside the repository;
any later automated mover requires its own WAL/backup/sidecar migration court.

## Rollback

Stop invoking `release`, `project-separated`, and `check-separated`. The unchanged
item-1 direct path remains available. Preserve the Foundation database, public
release store, generated pack, private journals/receipts/conflicts, dissent, and
audit evidence. Do not delete or rewrite any of them.

## Acceptance

Acceptance requires:

- exact frozen `131/33/13/304` Generation Zero compatibility;
- all 17 Phase 2 and seven item-1 schemas unchanged, with three separately catalogued
  item-2 schemas additive;
- private/internal/quarantined/unsupported and protected-field exclusion;
- strict public-store shape, scope, canonical JSON, append-only, digest, authority,
  idempotency, corruption, and wrong-store tests;
- private source and protected state disjoint from the repository;
- restart after public commit, hardlink/link/path, scope-substitution, and conflict
  tests;
- projection with the Foundation store absent and exact item-1 public-tree parity;
- complete Python 3.11/3.12/3.14, Ruff, Pyright, CodeQL, secret, dependency/license,
  wheel/resource, SBOM, and provenance receipts; and
- independent Curator, Steward, and distinct Judge reconstruction.
