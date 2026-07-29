# Phase 3 stable-ID cognitive notes court

- Case: `P3-COGNITIVE-NOTES-003`
- Scope: Phase 3 item 3 only
- Exact base: `40a508b6b1bfb4a8624cf1ef8169384d32a39d44`
- Branch: `codex/phase3-stable-id-cognitive-notes`
- Parent delivery: draft PR #33 on
  `codex/phase3-public-private-memory-separation`
- Governing records: ADR-019 through ADR-024,
  `P3-BRAIN-PACK-001`, and `P3-MEMORY-SEPARATION-002`

## Participants and independence

| Function | Identity | Independence |
| --- | --- | --- |
| Clerk, Orchestrator, Advocate | `Codex-root` | coordinates and presents; cannot curate, steward, or judge |
| Explorer | `/root/explorer` | read-only repository discovery; no edits or verdict |
| Architect | `/root/architect` | read-only architecture and threat analysis; no edits or verdict |
| Integrator and Optimizer Expert Witness | `/root/integrator_optimizer` | read-only contract/metric testimony; no edits or verdict |
| Builder | `/root/builder` | isolated code, schemas, and tests; cannot verify or judge |
| Cross-Examiner | `/root/cross_examiner` | read-only adversarial review; no edits or verdict |
| Curator | `/root/curator` | independent reproduction after repair; no edits or verdict |
| Steward | `/root/steward` | independent reliability/recovery review; no edits or verdict |
| Judge | `/root/judge` | distinct final item-3 disposition; no edits |

Generated evidence, successful tests, and the Advocate's or Builder's opinion cannot
fill an independent role.

## Original requirement and atomic claims

The admitted requirement is Phase 3 item 3: **Add HOME, idea, evidence, court, run,
agent, and telemetry notes using stable IDs and properties.**

| Claim | Advocate case | Burden before adoption |
| --- | --- | --- |
| `COG-001` | A separate cognitive namespace preserves the accepted item-1 pack and ownership protocol. | Prove item-1 bytes/catalog remain exact and the two namespaces do not conflict. |
| `COG-002` | A public-store-only projector maintains item-2 least privilege. | Project with the private Foundation store absent; reject wrong store/scope/overlap before writes. |
| `COG-003` | One exhaustive memory-kind mapping creates the six requested domain note classes without inference. | Map every admitted kind exactly once, fail on unknown kinds, and reconcile HOME counts. |
| `COG-004` | Domain-separated stable IDs survive mutable metadata and input order. | Derive identity from immutable source/scope only; prove mutable fields change bytes but not ID/path. |
| `COG-005` | Strict atomic properties make metadata navigable without inventing content. | Trace every rendered value to a released field or fixed constant; reject unknown properties and hostile rendering. |
| `COG-006` | A telemetry note can honestly index released resource/evaluation metadata. | State that raw usage accounting is unavailable; never emit token, cost, provider, invoice, or trace claims. |
| `COG-007` | A separate manifest-last protocol is reversible and recoverable. | Bound compilation and reads; preserve edits; test typed drift/conflict, interruption, restart, and external state. |
| `COG-008` | The slice is additive and opt-in. | Preserve `131/33/13/304`, 17/7/3 prior catalogs, root CLI, dependencies, and explicit later-item deferrals. |

## Source admission and provenance

No new external source or dependency is admitted. The court uses the repository-owned
founding handoff, hardened contract, ADR-019 through ADR-023, strict item-2 public
envelope, and accepted projection security patterns. The original candidate
directory layout expressly required later adjudication; ADR-024 records the adapted
separate namespace.

No unavailable source content is invented. Obsidian documentation remains outside
the implementation claim and is unnecessary to ordinary Markdown/YAML operation.

## Advocate case

Metadata-only notes materially improve browseability while retaining the append-only
store as truth. A one-record/one-note model is deterministic, bounded, reversible,
and avoids aggregating separate release decisions. A dedicated namespace and
catalog prevent item 3 from weakening earlier contracts. Stable opaque identities
make note updates independent of mutable headings and paths.

## Independent testimony

Explorer `/root/explorer` found that current public envelopes support only metadata
notes; rich prose, verdicts, scorecards, and raw telemetry would be fabricated. The
Explorer required stable path-independent identity, additive schemas, public-store
separation, installed-resource evidence, total-file bounds, and preserved dissent.

Architect `/root/architect` selected a distinct `generated-cognitive` namespace,
public-store-only module commands, one note per released record, an exhaustive
memory-kind mapping, eight separate contracts, external protected state, and
manifest-last recovery. The Architect explicitly deferred raw telemetry and rich
content.

Integrator/Optimizer `/root/integrator_optimizer` confirmed the frozen 17/7/3
catalog boundary and `131/33/13/304` surfaces. The witness warned that usage is
private and unknown is not zero, prohibited stable IDs in metric labels, required
bounded fan-out, and rejected usefulness or superiority claims without evaluation.

## Cross-examination obligations

The independent Cross-Examiner must actively probe wrong-store admission, low-entropy
correlation, taxonomy confusion, YAML/Markdown/control/bidi injection, path/link/
hardlink substitution, count and byte exhaustion, unmanaged files, missing or
edited notes, forged manifests/receipts, crash windows, late races, protected-state
overlap, private field leakage, raw-usage inference, generated-note re-ingestion,
schema/package drift, and rollback gaps.

## Preliminary disposition

`adapt — implementation candidate permitted`

The taxonomy is adopted as item-3 intent. Exact storage is adapted to a separately
managed cognitive namespace, one note per already released record, metadata-only
telemetry, and eight additive strict contracts. Promotion, activation, usefulness,
production readiness, and superiority remain unjudged. Final disposition requires
Builder receipts, independent Cross-Examination, Curator and Steward reconstruction,
Integrator compatibility evidence, Optimizer outcome obligations, and a distinct
Judge.

## Cross-examination and remediation record

Cross-Examiner `/root/cross_examiner` remanded junction recovery, typed conflict
evidence, total source-byte bounds, changed-snapshot semantics, result-count
strictness, HOME validation, and adversarial coverage. Each issue received an
executable regression and bounded repair. A sealed older snapshot is completed under
its own cursor and receipt before current projection; this is preserved as an
explicit design choice rather than described as one atomic cross-store transaction.

Steward `/root/steward` subsequently remanded tampered staged manifests, abandoned
and completed transaction debris, late replacement races, incomplete receipt-plan
validation, Python-recursive history walking, and an undocumented same-directory
atomic-install window. The current candidate validates complete manifest and receipt
plans, exact prior chains, and non-no-op operations; walks history iteratively under
an explicit bound; atomically refuses late overwrite; and governs the reserved
transaction siblings in ADR-024, contract, migration, rollback, and dissent.

Renewed Cross-Examination remanded a final Windows junction/source-move window, an
unrelated reserved sibling discovered only after replay mutation, and missing schema
validation for an existing conflict document. The repair adds Windows no-delete
leases over the root, destination parent, and prepared file, preflight sibling
admission, post-link ancestry/identity verification, and existing-conflict contract
validation. Cross-Examiner reruns observed typed conflicts without an external
generated file, completion receipt, or pre-conflict manifest mutation, and confirmed
schema-invalid conflict evidence fails closed. The renewed PASS is bound to
`cognitive.py` digest
`sha256:63e1aed35c9c403fafb488c29e098cb9178f09d9110c6098853431c19fab0b41`.

The Advocate concedes that file-at-a-time publication is not a filesystem
transaction and that a machine failure can temporarily expose reserved dotfiles
until exact-journal recovery. This limitation does not authorize adoption of
unjournaled state or deletion of human bytes.

## Verification receipts pending final judgment

The exact pre-judgment candidate passed `101` focused tests plus `23` subtests across
Phase 2 and Phase 3 items 1–3, Pyright with zero errors/warnings, Ruff, exact
inventory characterization, and whitespace validation. Steward independently
returned PASS after reproducing the repaired receipt tampering cases and running all
66 then-current item-1/item-2/item-3 tests. Curator's final current-byte rerun,
bound to the same implementation digest, returned PASS with all 69 item-1/item-2/
item-3 tests and exact inventory equality. A distinct Judge disposition remains
required before the preliminary disposition changes.

Final development inventory digest:
`sha256:2340004a3ed91df96e87826ca220c81ad6ca16aaae93f181119a225c4cdc4057`.

## Final judgment

Judge `/root/judge` issues:

`adapt`

Phase 3 item 3 is accepted for a stacked draft PR as an opt-in,
public-store-only, metadata-only cognitive projection. The judgment is bound to:

- implementation digest
  `sha256:63e1aed35c9c403fafb488c29e098cb9178f09d9110c6098853431c19fab0b41`;
- inventory digest
  `sha256:2340004a3ed91df96e87826ca220c81ad6ca16aaae93f181119a225c4cdc4057`;
- Judge reproduction of `101 passed, 23 subtests passed`;
- final current-byte Curator PASS with 69 Phase 3 tests and exact inventory;
- renewed Cross-Examiner PASS on the three final remands; and
- Steward, Ruff, Pyright, inventory, and whitespace PASS receipts.

No activation, usefulness, production-readiness, or superiority claim is adopted.
No public prose, canonical verdict, agent health, or usage/cost inference is
adopted. File-at-a-time publication and the documented malicious uncooperative-
writer limitation remain dissent. All explicitly deferred later Phase 3 and
final-system verification obligations remain open.
