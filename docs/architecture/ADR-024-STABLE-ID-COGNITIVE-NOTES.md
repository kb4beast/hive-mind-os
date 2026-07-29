# ADR-024: Stable-ID cognitive note projection

- Status: adapted for bounded draft delivery; activation and final-system promotion
  remain pending
- Date: 2026-07-29
- Exact base: `40a508b6b1bfb4a8624cf1ef8169384d32a39d44`
- Governing records: ADR-019 through ADR-023 and
  `P3-COGNITIVE-NOTES-003`
- Constitutional impact: no; additive projection contracts and opt-in command only

## Context

Phase 3 items 1 and 2 produce a deterministic generic safe-public memory pack from
either the mixed Foundation database or a physically separate public release store.
The accepted generic projection preserves provenance but does not provide the HOME,
idea, evidence, court, run, agent, and telemetry navigation requested by item 3.

The current public envelope contains released `memory-record-v1` metadata. It does
not contain a public prose body, court verdict, agent definition, provider usage
event, token/cost axes, prompt, response, trace body, or protected content. A
cognitive layer may organize the released metadata; it may not invent or dereference
facts that are absent.

Changing `hive-mind/generated`, its item-1 manifest, or any of the seven frozen
projection schemas would invalidate accepted bytes and ownership receipts. Adding
unknown files inside that namespace would correctly be treated as a conflict.

## Decision

Add an opt-in, public-store-only cognitive projector with a separately managed
namespace:

```text
hive-mind/
  generated/                 # unchanged item-1 output
  generated-cognitive/
    HOME.md
    ideas/
    evidence/
    courts/
    runs/
    agents/
    telemetry/
    manifest.json
```

The projector accepts only a verified, same-scope item-2 public release store. Its
durable locks, journals, desired-byte staging, ownership receipts, and conflicts
live in an explicit protected state root outside the repository. It never opens the
private Foundation database.

Publication uses transaction-ID-qualified `.cognitive-prior-*` and
`.cognitive-next-*` sibling files for the shortest per-file atomic install window.
They are reserved recovery artifacts, never desired-tree or manifest entries. The
same-directory location is required for atomic rename and no-overwrite hardlink
installation across supported filesystems. They are admitted only by an exact
external journal, exact expected/desired digests, and safe non-link paths; restart
finishes or conflicts without adopting them. Check mode and ordinary successful
publication leave none.

On Windows, the final no-overwrite window holds no-delete handles on the namespace,
destination parent, and prepared file so a concurrent junction/source move fails
before the link. Parent identity and managed ancestry are revalidated after linking.
Other platforms retain atomic no-overwrite semantics but cannot promise containment
against an uncooperative process deliberately renaming reserved recovery artifacts;
that stronger malicious-writer filesystem transaction remains outside this slice.

Each admitted released memory record produces exactly one note through this exhaustive
mapping:

| `memory_kind` | Note kind |
| --- | --- |
| `opportunity` | `idea` |
| `semantic`, `procedural`, `not-applicable` | `evidence` |
| `decision`, `counterfactual`, `governance` | `court` |
| `working`, `episodic`, `prospective` | `run` |
| `social` | `agent` |
| `evaluation`, `resource` | `telemetry` |

Unknown kinds fail closed. One-note-per-record avoids cross-record inference,
aggregation ambiguity, and multiplicative reference fan-out. HOME is a deterministic
repository index containing fixed explanatory text and bounded counts by note kind.

Record note identity is derived from the immutable released source record ID; HOME
identity is derived from the repository identity digest. Full hexadecimal digests
form filenames. Mutable titles, timestamps, status, content digests, input order,
and paths never form identity.

Eight strict item-3 schemas are separately catalogued: HOME, note, manifest,
transaction, receipt, conflict, result, and failure. They do not change the 17 Phase 2, seven
item-1, or three item-2 schemas and do not enter the frozen top-level facades or 13
root CLI parsers.

Properties are flat, bounded, deterministic, and limited to already released fields.
Untrusted values are JSON-quoted YAML scalars or indented JSON. Generated headings,
paths, and Markdown structure use projector-owned constants only. Notes are marked
generated and nonauthoritative.

Telemetry notes are metadata views of released `evaluation` or `resource` memory
records. They are not canonical usage accounting and do not report tokens, cost,
provider usage, invoices, or traces. Unknown or unavailable accounting must never be
rendered as zero.

## Source, license, and dependency disposition

No new external source, dependency, template, or copied code is admitted. The design
applies repository-owned requirements and the already admitted item-1/item-2
projection and public-envelope contracts. No Obsidian documentation, runtime,
account, plugin, Sync, watcher, URI, CLI, Base, or Canvas is required.

## Invariants and threats

- A public release store is the only source; private or wrong-scope stores fail
  before repository or protected-state mutation.
- Every source field rendered is already present in the verified public envelope.
- Stable IDs and paths are domain separated from mutable display state.
- NFC, control, bidirectional, length, list, file-count, note, manifest, and pack
  bounds fail closed before publication.
- Manifest-last publication is the commit marker. A valid ownership receipt is
  required before replacing prior generated bytes.
- Manual edits, unmanaged files, missing files, link/reparse/hardlink substitution,
  path overlap, and late races preserve observed bytes and emit typed conflict
  evidence.
- Interruption recovery accepts only an exact bounded journal and exact staged bytes.
- Reserved sibling names from any other transaction are typed conflicts detected
  before replay mutates a file.
- A sealed older transaction finishes before the current public snapshot is
  projected. Both manifest receipts remain explicit; stale work is never silently
  relabelled as current.
- The public release store is rejected above the 512 MiB total-file read bound
  before SQLite decode or output.
- Public IDs and unkeyed digests remain correlatable; hashing is not anonymization.
- Generated notes grant no authority and are never an intake path.

## Migration

Keep item-1 and item-2 commands and bytes unchanged. Materialize or reuse a verified
same-scope public release store, run cognitive `check` without writes, then run the
opt-in cognitive `project` command with a dedicated external protected-state root.
Verify a clean-root reconstruction and unchanged item-1 tree before enabling any
caller. No existing generated namespace is adopted, moved, or rewritten.

## Rollback

Stop invoking the cognitive module commands. Preserve the public release store,
`generated-cognitive` tree, manifests, journals, receipts, conflicts, tests, court
records, and dissent. Do not delete or rewrite canonical, generated, protected, or
human-authored data.

## Acceptance

Acceptance requires focused tests for deterministic HOME and all six domain kinds,
stable identity, safe rendering, strict catalogs, public-store-only operation,
item-1 byte parity, separation, scope, bounds, conflicts, interruption recovery, and
read-only checks. Frozen `131/33/13/304` surfaces and 17/7/3 prior schema catalogs
must remain exact. Full multi-version, security/supply-chain, wheel/resource,
independent reconstruction, and distinct judgment remain final-system obligations.

Rich prose, reference aggregation, raw usage/cost dashboards, backlinks, Bases,
Canvas, Obsidian refresh/support, federation, self-host recursion, Inbox/import,
plugins, watchers, Sync, retrieval, encryption/KMS, cleanup/deletion, activation,
usefulness, production readiness, and superiority remain deferred.
