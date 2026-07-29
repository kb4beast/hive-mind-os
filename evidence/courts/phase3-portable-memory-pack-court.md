# Phase 3 portable memory pack court

- Case: `P3-BRAIN-PACK-001`
- Scope: Phase 3 item 1 only
- Exact base: `94e67cde15fa8a75d92561384241f0419c9f589b`
- Branch: `codex/phase3-open-brain-obsidian-projection`
- Governing records: ADR-019, ADR-021, ADR-022

## Participants

| Function | Identity | Independence |
| --- | --- | --- |
| Clerk, Orchestrator, Advocate | `Codex-root` | coordinates and presents |
| Architect, Cross-Examiner, Steward | `Planck` | no implementation edits |
| Builder | `Codex-root` | cannot curate or judge itself |
| Curator, privacy/security Expert | `Kuhn` | independent reconstruction; no edits |
| Judge | `Ohm` | reserved for exact committed candidate |

## Scope finding

The eligible deliverable is one opt-in, read-only, single-tenant/repository snapshot
projector producing generic deterministic Markdown plus a manifest for CLI/editor use.
Phase 3 items 2–8 remain outside this court: public/private storage migration, HOME
and domain notes, Bases/Canvas, actual Obsidian refresh, federation/tenant isolation
suite, self-host recursion, and optional Inbox.

Generation Zero remains selected. The 131 root APIs, 33 package APIs, 13 existing
`hive-mind` parsers, 304 frozen definitions, prompts, legacy stores, 20 legacy schemas,
48 hive-core resources, and 68-resource receipt must remain exact.

## Admitted claims and dispositions

| Claim | Phase 1 disposition | Item 1 disposition | Limit |
| --- | --- | --- | --- |
| `OB-004` OS works without Obsidian | adopt-design | adopt | module CLI and ordinary files only |
| `OB-005` no account/paid service/plugin/proprietary DB | adopt-design | adopt | no Obsidian support claim |
| `OB-009` deterministic canonical-memory projections | adopt-design | adopt | safe-public metadata-only memory notes |
| `OB-010` generated files grant no authority or canonical mutation | adopt-design | adopt | authentic authority required only for filesystem publish |
| `OB-011` generated/human namespaces are separate | adopt-design | adapt | `hive-mind/generated` managed; human files outside it |
| `OB-012` staging, validation, expected digest, atomic replace | adopt-design | adopt | per-file replace; manifest is commit marker |
| `OB-013` human conflicts preserved | adopt-design | adopt | human bytes remain; desired bytes and digest receipt are private |
| `OB-014` safe-public default denial and redaction | adopt-design | adopt | explicit memory allowlist; omission counts stay private |
| `OB-015` no export re-ingestion | adopt-design | adapt | item 1 has no intake/read-from-pack path; future intake must enforce exclusion |
| `OB-016` optional Inbox | defer | defer | separate court only if required |
| `OB-017` Bases/Canvas | adapt-design | defer | Phase 3 item 4 |
| `OB-018` plugin/watcher/Sync writer unjustified | reject | reject | no such dependency or writer |

## Source admission

No new semantic source, library, template, or dependency is admitted.

`P1SRC-OBSIDIAN-HELP` remains `adapt` at pinned commit
`29e89022c6aeb0a9e9971b6f0c98733dbc2eb716` only for ordinary local Markdown/editor
interoperability. Documentation reuse terms remain unresolved, so no help text or
template is copied. `P1SRC-JSON-CANVAS` is admitted but irrelevant to item 1.
Obsidian CLI/URI, plugins, Sync, and refresh conformance are not claimed.

The implementation uses only repository-owned contracts and Python/SQLite/filesystem
behavior exercised directly by tests. No external production dependency is added.

## Advocate case and cross-examination

| Proposal | Advocate | Cross-examination | Verdict |
| --- | --- | --- | --- |
| Add `brain` to frozen `hive-mind` parser | convenient discoverability | changes a frozen 13-contract surface | reject |
| Separate `python -m hive_mind_os.foundation.brain` command | additive and reversible | must stay inert and typed | adopt |
| Use `FoundationStore(path)` to read | reuses code | may initialize/configure writable state and lacks one snapshot | reject |
| Read-only consistent snapshot API | validates existing canonical state | live WAL needs normal SQLite read locking | adapt |
| Dump all safe-public payload/storage fields | explicit release seems sufficient | protected refs, future fields, rendering attacks, and excess disclosure remain | reject |
| Metadata-only `memory-record-v1` allowlist | closes item 1 without inventing content | less useful until item 3 | adopt |
| Public omission counts/SQLite sequence cursor | operationally informative | leaks private activity and churns on private writes | reject |
| Eligible-set digest cursor; private omission counts | deterministic and privacy-preserving | cursor is not event replay | adopt |
| Acknowledge Phase 2 `local` outbox messages | connects the transactional outbox | historical messages were not routed to this projection | defer |
| Separate private projection transaction/conflict receipts | honest and replayable | not a Phase 2 delivery receipt | adopt |
| Whole-plan conflict on one edited path | avoids mixed cursor | delays unrelated notes | adopt for item 1 |
| Automatically delete stale managed files | keeps tree minimal | append-only deletion/migration and human collisions are not adjudicated | reject |
| Manifest-last per-file atomic replace | portable stdlib implementation | not an atomic whole-directory CAS | adapt |

## Threat and privacy examination

The court requires and tests:

- missing/wrong/corrupted database and repository scope;
- private/internal/quarantined exclusion and release-subject binding;
- path traversal, Windows-invalid canonical IDs, links/reparse targets, protected
  store overlap, and unmanaged generated files;
- YAML/frontmatter, Markdown/embed/HTML, control, bidi, size, and list attacks;
- deterministic repeat and clean-root rebuild;
- missing, changed, renamed, or manually edited managed paths;
- process locking, interruption, partial replacement, manifest-last commit, and
  restart;
- immutable/check mode without canonical logical writes;
- no canonical record or outbox mutation/acknowledgement; and
- exact Generation Zero and Phase 2 compatibility.

## Preserved dissent

Filesystem digest preflight is not a cryptographic CAS against a malicious writer.
SQLite live-WAL reads may use existing sidecar coordination. Private projection state
is append-only by protocol and exact-content comparison, not by database trigger.
Per-file atomic replacement can expose a partial tree to a reader that ignores the
manifest. Public release can still disclose correlation through approved identifiers
and digests. The current memory contract supplies metadata, not useful prose.

These limits block broader support, completeness, usefulness, or superiority claims.
They do not block the narrow opt-in item 1 candidate if exact recovery and
compatibility evidence passes.

## Preliminary disposition

Architecture: `adopt with narrow adaptations`.

Implementation: `pending exact committed candidate, full verification, independent
Curator/Steward reconstruction, and Judge verdict`.

No PR is merged and no runtime is activated by this preliminary disposition.
