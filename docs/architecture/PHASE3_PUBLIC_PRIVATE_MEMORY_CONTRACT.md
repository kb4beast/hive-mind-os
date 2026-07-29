# Phase 3 item 2 public/private memory contract

## Scope and authorities

The private Foundation database remains the canonical Phase 2 runtime authority. A
`PublicMemoryReleaseStore` is a separately owned, nonauthoritative persistence tier
for already released safe-public memory envelopes. The generated memory pack remains
a deterministic view over that public tier.

| Operation | Required authority | Canonical mutation |
| --- | --- | --- |
| Read private release candidates | existing Foundation file access plus exact scope | none |
| Materialize public envelopes | authentic `foundation.public-memory.release` intersection | append public release store and protected receipt only |
| Project released envelopes | authentic `foundation.projection.write` intersection | public pack and protected projection receipt only |
| Check released projection | none beyond explicit local file access | none |

Sensitivity labels, release-store contents, generated files, successful results, and
apparent value never grant authority.

## Public envelope admission

A release candidate must satisfy all of:

1. exact tenant and repository scope and registered identity;
2. a valid, integrity-checked Foundation v1 snapshot;
3. `record_type=memory-record` and `schema_name=memory-record-v1`;
4. safe-public storage and payload sensitivity;
5. an independent release decision and decider;
6. release subject digest equal to the canonical complete payload digest;
7. active/superseded/tombstoned, nonquarantined state; and
8. null protected-content and retrieval-receipt fields.

Future or extra fields fail closed. The three item-2 schemas are separate from the 17
Phase 2 and seven item-1 catalogs.

## Physical stores

The private Foundation store must be an existing single-link regular file outside
the resolved repository. The protected release and separated-projection roots must
be regular, non-root paths disjoint from the repository. A public release store must
not be the same file, a hardlink, or share the private/protected persistence root.

Each public store is immutably bound to one tenant ID, repository ID, repository
identity digest, origin Foundation schema version/digest, and release-policy
version/digest. Its only tables are `public_memory_metadata` and `released_memory`,
both protected by no-update/no-delete triggers.

## Idempotency and recovery

Release IDs bind scope, source record/digest, release policy, and public-envelope
digest. Repeating exact content returns unchanged; different content for one source
record conflicts. Only the verified materialization path can invoke the internal
append boundary; generic caller-supplied envelopes have no public append API. One
SQLite immediate transaction appends a batch.

Before that transaction, a bounded, deterministic, self-contained private journal is
durably published. It binds the verified public envelopes, source records/digests,
counts, release policy, authority, and expected destination digest. Restart finishes
all older pending journals before a newer source snapshot. Private counts,
authority/lease references, paths, and omission evidence never enter the public
store or generated pack.

Separated projection uses the item-1 staging, manifest-last publication, ownership,
conflict, and restart protocol with an external protected state root. The public
release store is the only memory source opened by this path; the private Foundation
store is not opened.

## Compatibility and deferred scope

The direct item-1 API/CLI remains supported and its public bytes remain characterized.
Generation Zero selectors, facades, prompts, stores, roles, packages, and 13 parser
contracts remain untouched.

Item 2 adds no HOME/domain notes, richer prose, Bases, Canvas, refresh/support claim,
federation, self-host recursion, Inbox/import, plugin, watcher, Sync, retrieval,
protected-content vault, encryption/KMS, deletion/crypto-erasure, public cleanup,
outbox routing/acknowledgement, activation, usefulness, or superiority claim.
