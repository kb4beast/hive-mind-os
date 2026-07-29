# Phase 3 item 1 projection contract

## Scope

This contract implements only the portable per-repository memory pack and
deterministic CLI/editor projection required by Phase 3 item 1. Generation Zero and
the inert Phase 2 foundation remain selected exactly as before.

Excluded until later Phase 3 items are HOME and domain-specific notes, Bases, Canvas,
War Room, automatic-refresh support, public/private store migration, federation,
self-host recursion, Inbox/import, watcher, retrieval, and any Obsidian runtime
dependency.

## Authorities

| Concern | Authority | Projection |
| --- | --- | --- |
| Memory truth | append-only Phase 2 Foundation database | generated Markdown |
| Repository scope | immutable registered repository identity | identity digest in manifest |
| Public release | independent release decision bound to payload digest | sensitivity decision digest |
| Pack ownership | exact manifest plus matching private completion receipt | managed path/digest set |
| Write permission | authentic `foundation.projection.write` intersection | private transaction receipt |
| Human input | none in item 1 | files outside generated namespace are untouched |

Generated files, manifests, successful projection, and apparent mission value never
grant authority or mutate canonical memory.

## Snapshot admission

The database path must already exist as a regular non-link file. The output root is
fixed at `<resolved-repository>/hive-mind` and cannot contain the database.

One normally coordinated read-only SQLite transaction validates store ownership and
integrity, reads the exact
repository identity, counts local omissions, and exposes to the compiler only records
meeting:

1. exact tenant and repository scope;
2. storage sensitivity `safe-public`;
3. `record_type=memory-record`;
4. `schema_name=memory-record-v1`;
5. payload sensitivity `safe-public`;
6. nonempty independently attributable release decision and decider;
7. release subject digest equal to the stored semantic digest; and
8. no quarantined status or quarantine state.

The compiler never receives private/internal payloads and never dereferences
protected references. Empty eligible input produces a valid empty pack.

## Deterministic artifacts

Public artifacts depend only on the registered identity, verified eligible records,
canonical source times/digests, and fixed schema/projector versions. They contain no
wall-clock attempt time, absolute path, authority lease, private omission count, or
SQLite sequence.

Every note is a metadata-only `hive-obsidian-projection/v1` document. The source
record ID remains canonical identity; the filename and `note_id` use the full SHA-256
of that ID only as a portable projection key.

The manifest is `hive-brain-pack/v1`. Its `memory-set:<sha256>` cursor is derived from
the sorted eligible record IDs and semantic digests. The manifest is the final commit
marker and owns exactly the listed generated files.

## Rendering and bounds

- UTF-8 without BOM, LF, and one final newline;
- stable field and file ordering;
- JSON-quoted YAML scalars;
- untrusted metadata only in quoted frontmatter or an indented JSON code block;
- no generated Markdown links, embeds, HTML, scripts, commands, or Wikilinks;
- NFC input, no control or bidirectional override characters;
- at most 100,000 records, 256 list items, 4,096 characters per string,
  1 MiB per note, 256 MiB per pack, and 16 MiB per manifest;
- portable relative paths only, full hashed filenames, and no symlink, junction,
  reparse, hard-linked state file, absolute, traversal, or linked managed target.

The allowlisted memory fields exclude `protected_content_ref` and
`retrieval_receipt`. Later fields fail closed until this contract is versioned.

## Publication states

| Status | Meaning | Exit |
| --- | --- | --- |
| `projected` | desired tree verified and manifest committed | 0 |
| `unchanged` | current tree exactly matches the desired tree | 0 |
| `drift` | read-only `check` found a difference | 1 |
| `conflict` | managed/unowned bytes differ; conflicting bytes were not overwritten | 1 |
| `failed` | scope, integrity, schema, authority, path, bound, I/O, or recovery failure | 2 |

`project` stages every desired byte on the same filesystem, records expected prior
digests and authority references, validates staging, rechecks the exact namespace and
non-link roots under the process lock before `os.replace`, replaces notes, and
publishes the manifest last. A prior manifest authorizes mutation only when a private
completion receipt binds its exact digest. After interruption, exact desired files
are recognized, stale completed transaction state is removed, and the remaining
transaction resumes; any third digest conflicts.

On conflict, observed public bytes are never copied into protected state or
overwritten. The desired generated tree and a digest-only conflict receipt are
preserved under ignored protected projection state. An uncooperative writer racing
between atomic replacements can leave already-published exact desired note bytes
under the prior manifest; restart treats those bytes as resumable state. No source
record or Phase 2 outbox message is changed or acknowledged.

## Verification and rollback

`check` performs the same snapshot, compilation, schema, path, and digest verification
without creating the pack or projection state. Full rebuild and repeat projection of
one snapshot must have identical public trees.

Rollback is to stop the opt-in command. Item 1 exposes no automated cleanup command.
Canonical data, public files, conflicts, receipts, audit records, and dissent remain
available for review and later migration.
