# ADR-025: Bounded Obsidian Bases and JSON Canvas views

- Status: adapted for bounded stacked draft delivery; activation and final-system
  promotion remain pending
- Date: 2026-07-29
- Exact base: `7e26a56eab5fe79f075cccc57a6ff0a01fb9ef9a`
- Case: `P3-OBSIDIAN-VIEWS-004`
- Constitutional impact: no; additive opt-in projection only

## Context

Phase 3 item 3 emits receipt-owned safe-public cognitive notes with flat properties.
Item 4 asks for Obsidian Bases and JSON Canvas views for ideas, War Room, agent
scorecards, token/value accounting, loops, and quarantine.

The verified item-3 source supports released metadata navigation. It does not contain
agent definitions or performance scores, provider usage, token/cost/value accounting,
loop signals, or quarantine records. Quarantined memory is deliberately excluded
from the public projection. Empty dashboards or numeric zero would therefore be
false.

Adding `.base` or `.canvas` files to `hive-mind/generated-cognitive` would invalidate
item 3's exact manifest and ownership receipt. Item 3 must remain byte-for-byte
unchanged.

## Decision

Add a separate opt-in module and managed namespace:

```text
hive-mind/generated-cognitive-views/
  bases/
    ideas.base
    released-war-room.base
    agent-records.base
    telemetry-metadata.base
  canvases/
    war-room.canvas
  manifest.json
```

The projector reads only an exact, receipt-owned item-3 manifest/tree and its
external protected state. It accepts no Foundation database or public SQLite path.
It holds the existing item-3 lock while compiling and publishing item 4; lock order
is always item 3 then item 4. It never repairs item 3.

The four Bases are strict, generator-owned YAML using only global filters, property
display names, and one core table view. Filters are fixed constants plus the
validated repository identity digest. They include folder, note schema,
generator/mapping version, `sensitivity=safe-public`, `is_generated=true`, and
`is_authoritative=false`. There are no formulas, summaries, plugins, dynamic time,
file timestamps, backlinks, `this`, HTML, URLs, or untrusted expressions.

The constant-size Canvas contains fixed disclosure text and file nodes pointing to
the four Bases. It uses only the JSON Canvas 1.0 text/file-node subset, fixed integer
geometry, no URLs, no HTML, and no edges. Full domain-separated SHA-256 node IDs
depend on repository identity and semantic node role, not cursor, status, timestamps,
text, geometry, or content digests.

The Canvas explicitly says:

- the War Room is released, static, safe-public, generated, nonauthoritative, and
  not live;
- agent score and health are unavailable;
- token/value accounting is unavailable and no zero is implied;
- loop state is unavailable;
- quarantine inventory is unavailable because the source admits only
  nonquarantined public memory.

No loop or quarantine Base is emitted because an empty result could be misread as
zero or all-clear.

Eight strict item-4 schemas are separately catalogued: Base, Canvas, manifest,
transaction, receipt, conflict, result, and failure. No frozen facade or root CLI
parser changes.

## Source disposition

`PHASE3_ITEM4_SOURCE_REGISTER.md` pins the official Obsidian help repository and JSON
Canvas 1.0 specification. Bases documentation is used for abstract factual syntax
only; its reuse license is unresolved and no example/template is copied. JSON Canvas
1.0 is MIT licensed.

The claim is limited to deterministic generation of the pinned documented Base
subset and the strict JSON Canvas 1.0 subset. Obsidian runtime compatibility,
rendering, and refresh are not claimed.

## Publication and recovery

Item 4 has a separate external protected-state root, lock, complete desired-byte
staging, strict journal, expected-prior plan, receipt chain, typed conflicts,
transaction-qualified sibling files, atomic destination no-overwrite, and
manifest-last publication.

The journal is written inside a preparation directory before desired-byte staging.
Only a complete preparation with an exact staged-file plan is atomically sealed as a
recoverable transaction. An incomplete preparation is never silently deleted: it is
moved to a bounded content-addressed `abandoned` directory with a canonical receipt
binding its original transaction ID and every preserved file digest. The shortened
evidence name keeps nested paths inside the supported Windows path budget. Only the
known journal and hashed staging-file layout may be abandoned, and a readable
preserved journal must agree with the receipt's transaction identity.

Completion receipts, conflict evidence, and abandonment receipts are first written
and fsynced to a content-digest temporary name, then installed by a platform atomic
no-replace rename. A complete interrupted temporary is installed on restart; an
incomplete temporary whose bytes do not match its name is explicitly unsealed and
discarded before the authoritative operation is retried. Check mode reports pending
temporary evidence without changing it.

A sealed older item-4 transaction is recovered under its recorded historic item-3
manifest/receipt evidence before the current verified item-3 source is projected
separately. Recovery requires fresh authentic write authority for the same tenant
and repository, while the journal preserves the original actor, lease, and decision
as historical evidence. Missing or altered source receipts fail closed. Check mode
is read-only and performs no recovery.

The item-3 source must have no pending transaction, unmanaged path, drift, link,
hardlink, junction, or reserved sibling. Source changes during check or publication
that are observed before the manifest commit fail closed. The item-3 lock excludes
cooperative writers; an uncooperative mutation after the final pre-manifest
revalidation remains the inherited filesystem limitation. Item 4 cannot expand
authority or adopt unreceipted state.

All protected receipt/conflict records are structurally and semantically validated.
After recovery every receipt must be reachable from the installed manifest head;
schema-valid forged side branches fail closed. Reserved siblings are preflighted
before replay and removed only after their exact journal digest and hardlink identity
are proven. Recovery specifically admits and completes the verified two-link
next-file/destination crash window. Source-receipt validation caches already proven
history within one bounded validation pass while rechecking every direct receipt
head, avoiding repeated full-chain traversal.

Directory seals and prior-file preservation use native atomic no-replace rename on
Windows, Linux (`renameat2`), and macOS (`renamex_np`); unsupported platforms fail
closed. On Windows the protected-state root is limited to 110 characters so the
deepest preparation path remains below the classic 260-character boundary.

The same documented malicious uncooperative-writer filesystem limitation as item 3
remains dissent.

## Bounds

- exactly four Bases, one Canvas, and one manifest;
- each Base at most 64 KiB;
- Canvas at most 256 KiB, at most 16 nodes, and zero edges;
- manifest at most 1 MiB;
- complete tree at most 2 MiB;
- protected path enumeration at most 200,100, pending transactions at most 64,
  conflicts reported at most 200 with explicit overflow summary, and every
  protected document at most 2 MiB.

## Migration

Require a clean exact item-3 source, select a disjoint item-4 protected-state root,
run read-only `check`, run opt-in `project`, repeat both, reconstruct in a clean root,
and prove item-1/item-3 bytes unchanged.

## Rollback

Stop invoking item 4. Preserve generated views, manifests, journals, receipts,
conflicts, source pins, court evidence, and dissent. Deletion, adoption, cleanup,
opening the repository as a vault, or launching Obsidian requires separate authority.

## Deferred

Genuine agent scorecards/health, token/value accounting, loops, quarantine inventory,
Obsidian runtime support, automatic refresh, watchers, Sync, federation, self-host
recursion, Inbox/import, plugins, retrieval, encryption, cleanup/deletion,
usefulness, production readiness, and superiority remain deferred.
