# Court record: Phase 3 item 5 Obsidian vault refresh

- Case: `P3-OBSIDIAN-REFRESH-001`
- Disposition: `adapt`
- Subject implementation: `ee09e4cb9a4bc5fd0711e738249039507a194e43`
- Review candidate: `8b0b0a029b8ef52b1ef75a64961234466f860dc2`
- Runtime: Obsidian Desktop `1.12.7`, Windows `10.0.26200`

## Claims

| Claim | Evidence | Disposition |
|---|---|---|
| Core Obsidian reflects item-1 external replacement in an already-open pane. | Fourth run, count `6 -> 7`, `4.315128s`. | adopt |
| Core Obsidian reflects item-3 external replacement in an already-open pane. | Fourth run, total `7 -> 8`, `4.185468s`. | adopt |
| Core Bases recomputes after a new generated idea note appears. | Fourth run, `1 -> 2` rows, `8.940211s`. | adopt |
| The generated Canvas parses and renders embedded Bases. | Fourth-run Canvas screenshot and preserved target bytes. | adopt |
| Generated item-4 bytes remain owned after runtime observation. | Fourth run unloads Canvas, waits at least 300 seconds, preserves both observed targets plus the complete item-4 namespace, and requires final item-4 `unchanged`. | adapt: minimal stable serialization |
| The behavior generalizes to other hosts, versions, profiles, Git remotes, or Sync. | No evidence. | defer |

## Advocate

The Explorer and Architect supported a real-projector, disposable-vault black-box
test. The candidate protocol binds visible outcomes to projector timestamps and
hashes and uses no plugin or watcher.

## Cross-examination

The first run disproved the initial integrity claim when Obsidian canonicalized Base
YAML. The second run's immediate check was also insufficient: Obsidian rewrote the
Canvas about four minutes later. The third run passed for its own subject but became
non-promotable when production YAML hardening advanced. All remain append-only
evidence. The fourth run covers the sealed production subject.

Remaining weaknesses:

- the Obsidian process and user profile predated the run;
- no official refresh latency guarantee exists;
- screenshots prove only the recorded host and fixture; and
- `.obsidian` and vault registration are local side effects, not product state.

## Independent roles and judgment

| Lifecycle duty | Identity | Receipt |
|---|---|---|
| Orchestrator | `P3I5-Orchestrator` | Scoped the exact-host claim, budgets, stop conditions, reversible stack, and court schedule. |
| Explorer / Advocate | `P3I5-Explorer` | Pinned official help, release, installed-runtime, signature, license, and counterclaim evidence. |
| Architect | `P3I5-Architect` | Designed the exact-commit disposable-clone protocol, deadlines, stability gate, and rollback. |
| Builder | `P3I5-Builder` | Implemented the minimal serializers, fixture, validator, tests, and evidence package. |
| Cross-Examiner / Integrator | `Einstein` (`/root/item5_cross_examiner`) | Passed exact candidate `8b0b0a0`; reproduced 115 integration tests with 34 subtests, Ruff, Pyright, inventory, surviving-vault, compatibility, and provenance checks. |
| Curator / Expert Witness | `Locke` (`/root/item5_curator`) | Passed exact candidate `8b0b0a0`; reproduced all 147 tests with 57 subtests, focused tests, hashes, runtime-subject ancestry, and claim boundaries. |
| Steward | `/root/item4_explorer/steward` | Passed exact candidate `8b0b0a0`; reproduced focused and item 2–5 matrices, recovery-boundary tests, deterministic inventory, rollback, and operational limits. |
| Optimizer | `/root/item5_optimizer` | Passed exact candidate `8b0b0a0`; independently reconciled all three latencies, the `321.151072s` interval, comparator classification, and absence of a superiority claim. |
| Judge | `/root/item5_judge` | Independently reproduced 147 tests with 57 subtests, Ruff, and Pyright on `b53175f`, then issued the final narrow `adapt`. |

Discover, design, build, validate, integrate, maintain, grow/outcome measurement,
and orchestration are covered. All technical and evidentiary reviewers returned
`PASS`.

The original item-5 byte-freeze instruction conflicts with runtime-discovered Base
and Canvas canonicalization. The Judge considered that conflict explicitly and
limited the remedy to the two serialization changes described below.

## Final judgment

Judge `/root/item5_judge` issued `adapt` on review-record candidate
`b53175ffbd5d85e73ffc2ce6773560a999545170`. The original byte freeze is changed
only enough to admit the runtime-required Base scalar quoting and Canvas
serialization repairs. This is not authority for a semantic, namespace, filter,
schema, protocol, capability, or authority redesign.

The admitted result is limited to Obsidian Desktop `1.12.7` on the recorded Windows
build and fixture. Other hosts, versions, profiles, clean-profile isolation, Git
remotes, Sync, multi-device behavior, production activation, merge, usefulness,
value, latency guarantees, generalization, and superiority remain deferred or
rejected. Failed and superseded runs, dissent, rollback, and the exact sealed
production bytes remain controlling evidence.

A stacked draft PR may be published but must remain open, unmerged, and inactive.
Any relevant byte, schema, interface, capability, protocol, or evidence change
requires renewed independent review and judgment.
