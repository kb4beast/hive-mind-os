# Phase 3 public/private memory separation court

- Case: `P3-MEMORY-SEPARATION-002`
- Scope: Phase 3 item 2 only
- Exact base: `7f7013c99d86bbd34f966b902bb873cf5c10d740`
- Branch: `codex/phase3-public-private-memory-separation`
- Parent delivery: draft PR #32, based on exact PR #31 head
  `94e67cde15fa8a75d92561384241f0419c9f589b`
- Governing records: ADR-019, ADR-020, ADR-021, ADR-022,
  `P1-OPEN-MEMORY`, `P1-OBSIDIAN-OPEN-BRAIN`, and
  `P3-BRAIN-PACK-001`

## Participants and independence

| Function | Identity | Independence |
| --- | --- | --- |
| Clerk, Orchestrator, Advocate, Builder | `Codex-root` | coordinates and presents; cannot curate, steward, or judge itself |
| Explorer and source-intake specialist | `/root/item2_explorer` | no implementation edits or verdict |
| Architect and Cross-Examiner | `/root/item2_architect` | no implementation edits or verdict |
| Privacy/security Expert Witness | `/root/item2_privacy_expert` | no implementation edits or promotion verdict |
| Pre-commit Curator | `/root/item2_final_curator` | independently remanded the first candidate; no edits |
| Pre-commit Steward | `/root/item2_final_steward` | independently remanded the first candidate; no edits |
| Final Curator | deferred | exact-head reconstruction deferred to the final-system check |
| Final Steward | deferred | exact-head reliability review deferred to the final-system check |
| Judge | reserved | distinct exact-candidate disposition; no edits |

The Integrator and Optimizer lifecycle evidence must be recorded before judgment.
Generated evidence, successful tests, and the Builder's opinion cannot fill any
independent role.

## Original requirement and atomic claims

The admitted user requirement is Phase 3 item 2: **Separate safe public memory from
private/sensitive runtime records.**

The court separates that requirement into the following atomic claims:

| Claim | Advocate case | Burden before adoption |
| --- | --- | --- |
| `SEP-001` | A strict separated profile keeps the canonical Foundation database outside the repository/vault. | Reject repository overlap, linked roots, wrong scope, and unregistered identity before public mutation. |
| `SEP-002` | Independently released safe-public memory is materialized into a separately owned, single-scope public release store. | Prove the public store contains only a versioned public envelope and minimal public release provenance, never mixed runtime tables or fields. |
| `SEP-003` | The separated projector reads only the public release store; projection and release journals/receipts remain private and external. | Reproduce projection with the Foundation database absent or unreadable and with no `.hive-mind-projection-state` creation in strict mode. |
| `SEP-004` | Physical placement cannot replace the existing independent, subject-digest-bound safe-public release decision. | Preserve storage/payload sensitivity checks, independent decider attribution, release subject binding, quarantine exclusion, and authority intersection. |
| `SEP-005` | One tenant/repository scope receives a deterministic opaque protected layout. | Bind the layout to exact tenant and repository identity without raw identifiers in directory names and reject cross-scope store substitution. |
| `SEP-006` | Separation is additive and opt-in. | Preserve the accepted item-1 command/API behavior, Generation Zero, the Phase 2 store schema, all 17 Phase 2 schemas, and all seven item-1 projection schemas. |
| `SEP-007` | Existing stores require an explicit, quiescent, verified migration decision rather than an implicit move or copy. | Supply inspection and rollback guidance; do not claim atomic live migration, backup, encryption, or deletion. |
| `SEP-008` | A protected root is a placement and disclosure boundary, not a complete security product. | Preserve dissent about host permissions, backups, malware, low-entropy digests, external authentication, retention, and crypto-erasure. |

## Scope finding

Item 1 already proved logical safe-public filtering and deterministic publication
from one physically mixed Foundation database. Its accepted default also keeps
private projection recovery state in an ignored directory inside the repository and
permits the caller to place the private Foundation database elsewhere in the
repository outside `hive-mind/`. An ignore rule is not a privacy control. Item 2
must therefore add both a distinct low-privilege public persistence boundary and a
stricter protected-state placement profile rather than relabel item-1 filtering as
completed separation.

The eligible minimal implementation is:

1. an explicit private Foundation source outside the repository/vault;
2. a separately self-identifying, single-tenant/repository, append-only safe-public
   release store;
3. a one-way, idempotent, crash-recoverable release transformation with a strict
   public-envelope allowlist and separate authentic
   `foundation.public-memory.release` authority;
4. an explicit external protected-state root for private release and projection
   journals, staged bytes, completion receipts, and conflict receipts;
5. a separated projector that consumes only the public release store and reproduces
   the item-1 public tree for the same admitted fixture without opening the
   Foundation database; and
6. typed, inspectable receipts and tests proving the boundary.

HOME and domain notes, richer prose, Bases, Canvas, Obsidian refresh/support,
federation, self-host recursion, Inbox/import, plugins, watchers, Sync, retrieval,
outbox acknowledgement, protected content bodies, encryption, key management,
automated migration, cleanup, and deletion remain outside this court.

## Source admission and provenance

No new external semantic source, code, dependency, template, or license is admitted
by the preliminary design. The court relies on repository-owned contracts and the
already admitted Phase 1 source record.

`P1SRC-OBSIDIAN-HELP` remains `adapt` only for the narrow fact that a vault uses
ordinary local files. Its unresolved documentation-reuse terms still prohibit
copying help text or templates. `P1SRC-JSON-CANVAS`, Obsidian CLI/URI, plugins, Sync,
and refresh behavior are irrelevant to item 2.

If implementation later depends on an external security, filesystem, encryption, or
privacy claim, that source must be separately pinned with URI, version/digest,
retrieval time, license, atomic claims, counterclaims, and measured application
evidence before the claim is used.

## Alternatives under cross-examination

| Alternative | Advocate | Cross-examination | Preliminary disposition |
| --- | --- | --- | --- |
| Treat item-1 filtering as complete item 2 | avoids code churn | ignored recovery state and an in-repository private database remain possible | reject |
| Add a single-scope public SQLite release store | supplies a low-privilege physical read boundary and append-only release history | must remain nonauthoritative, avoid copied runtime fields, and preserve divergence/revocation dissent | adapt pending evidence |
| Add a protected-content body vault | enables private prose | Phase 2 deliberately rejects bodies; encryption, access audit, deletion, and key lifecycle are not adjudicated | defer |
| Require all callers to change immediately | creates one mode | breaks the adopted item-1 interface and exceeds additive migration authority | reject |
| Add only an opt-in strict external protected layout | closes accidental Git placement gaps | still mixes public and private rows behind one filesystem read boundary | reject as sole design; retain as a required deployment control |

## Authority, privacy, and threat obligations

The implementation must fail closed for:

- protected root inside the repository, repository inside the protected root, or
  source database anywhere inside the repository;
- symbolic links, junctions, reparse points, hard-linked protected files, path
  traversal, broad/root targets, or scope substitution;
- store identity or registered tenant/repository mismatch;
- missing or forged public-release evidence, payload/storage sensitivity mismatch,
  quarantined records, schema drift, chain/integrity failure, or authority mismatch;
- public bytes containing protected-state paths, private record identifiers, private
  omission counts, recovery receipts, WAL/SHM data, or protected references; and
- interruption or conflict recovery that writes private evidence back into the
  repository.

The public envelope digest must be computed only over released fields. Item 2 rejects
non-null `protected_content_ref` or `retrieval_receipt` from the separated release
path; those fields require a later protected-content and retrieval court. A private
release receipt must bind the source record and digest, exact redaction/allowlist
policy, public envelope and digest, scope, destination, actor, independent release
decision/decider, authority/lease, and idempotency. The public store retains only the
minimum provenance needed to validate and project its released envelope.

The external protected root does not itself prove filesystem access control,
encryption at rest, secure backup, malicious-local-writer resistance, authenticated
human identity, legal deletion, crypto-erasure, or absence of low-entropy
correlation. Those claims remain explicit dissent or later evidence obligations.

## Migration and rollback obligations

The strict profile is additive. Existing item-1 callers continue unchanged but are
explicitly characterized as direct mixed-store projection, not item-2 separation.
New strict callers materialize a public release store, then project from it while the
private Foundation source and protected receipts remain disjoint from the repository.

No live database, WAL, SHM, lock, journal, or receipt may be silently moved or
copied. Adoption of an existing Foundation database requires caller-controlled
quiescence, backup, exact file-set and digest verification, identity/integrity
revalidation, and a separately recorded migration receipt. Item 2 may document this
obligation without adding an automated mover.

Rollback stops using the strict profile and returns to the still-supported item-1
mode. Preserve the canonical store, public pack, protected projection evidence,
conflicts, tests, audit records, and dissent. Rollback never deletes or rewrites
canonical, public, private-evidence, or human-authored bytes.

## Preliminary disposition

Explorer/Clerk `/root/item2_explorer` found that item 1 is a disclosure filter over
one private database and recommended a separate nonauthoritative public persistence
artifact. Architect/Cross-Examiner `/root/item2_architect` rejected path-only
separation and selected a per-scope append-only release store. Privacy/security
Expert `/root/item2_privacy_expert` independently concurred that external placement
is necessary but insufficient and required a public-only envelope, split receipts,
correlation controls, and honest deletion limits.

Architecture: `adapt` to the narrow release-store design above.

Implementation: `pending`.

No runtime is activated, no PR is merged, and `main` is not modified by opening this
court.

## Implementation candidate before delivery judgment

The Builder implemented the adopted narrow shape through:

- `public_memory.py` for the separate store, release authority boundary, strict
  envelope, private journal/receipt, and read-only public snapshot;
- the existing brain projector with an external protected-state option and a
  public-store-only separated entrypoint;
- three additive item-2 schemas and a separate deterministic inventory; and
- focused privacy, scope, hardlink, idempotency, crash/restart, append-only,
  tamper, compatibility, and private-source-absence regressions.

The direct item-1 path remains available and is not relabeled as separated. The
implementation does not mutate Foundation, acknowledge its outbox, add public
content, or begin any later item.

The independent pre-commit Curator and Steward both returned `REMAND` for a generic
append bypass, changed-snapshot receipt recovery gap, newer-store admission,
unbounded existing-store reads, and public/protected-root overlap. The Builder
repaired every finding with narrow regressions: verified-only internal append,
self-contained bounded recovery journals, exact-version admission, pre-enumeration
bounds, and bidirectional persistence-root separation.

Implementation disposition is `adapt` as a reversible draft candidate. Exact-head
multi-version/supply-chain verification, fresh final Curator and Steward
reconstruction, and a distinct Judge promotion verdict are explicitly deferred to
the later final-system check; no adoption or superiority claim is made now.
