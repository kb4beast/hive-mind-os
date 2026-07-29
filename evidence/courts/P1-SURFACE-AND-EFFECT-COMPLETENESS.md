# P1 Surface and Effect Characterization Court

- Case ID: `P1-SURFACE-AND-EFFECT-COMPLETENESS`
- Status: candidate awaiting independent Curator and Judge disposition
- Originating requirement:
  `evidence/courts/P1-CHARACTERIZATION-JUDGE.md`
- Baseline production commit:
  `b032a9f32f48889e0889fae8d6dd04eb03f46b63`
- Verified repair head:
  `0948f7ec385238f5825ce7c39dd25de2e9a1035d`

## Participants

| Function | Identity |
| --- | --- |
| Orchestrator and Builder | `/root` |
| Architect and Advocate | `/root/phase1_architecture` |
| Integrator, Steward, Optimizer, and Cross-Examiner | `/root/phase1_runtime` |
| Curator and Expert Witness | pending `/root/phase1_curator` |
| Judge | pending `/root/phase1_judge` |

No Builder finding is an independent verification or judgment.

## Atomic claims

### P1-SE-001 — supported signatures must be frozen

The 131 root-facade bindings, 33 package-system-facade bindings, and 13 CLI
parser contracts are supported generation-zero surfaces whose signatures must
not silently drift.

Requested disposition: `adapt`. Freeze exact supported facades and CLI
contracts while marking 304 additional module definitions as de-facto
observable, not newly promised API.

### P1-SE-002 — event paths must be completeness-enforced

Generation zero has 48 direct ledger sinks, 53 event-producing source sites,
and 47 literal production event types. A source change that adds or changes a
matched path must fail the fixture until its evidence is deliberately updated.

Requested disposition: `adapt`. The registry closes the earlier prose-only
inventory, but event-schema sufficiency and behavioral coverage remain
deferred.

### P1-SE-003 — persistence writers must be machine registered

The published bounded rules find 224 SQLite, filesystem, lesson, process, Git,
network, and remote-effect sites with exact source receipts and zero
unclassified matched candidates.

Requested disposition: `adapt`. Accept the bounded static registry as
generation-zero characterization, not as proof of semantic completeness.

### P1-SE-004 — discovered runtime defects block architecture promotion

Run/model correlation, scheduler history, mutation/event atomicity,
read-only projection behavior, PIT restart recovery, event validation,
privacy, migration, concurrency, and Windows behavior remain incomplete.

Requested disposition: `defer` Phase 2 implementation and all architecture
promotion until those obligations receive separate design and executable
acceptance evidence.

## Advocate case

The artifact improves the fixture from aggregate names and prose to exact,
regenerable contracts. It deduplicates facade definitions while retaining
every binding, canonicalizes signatures without memory-address defaults,
records de-facto surfaces without overpromising them, resolves the ingestion
event wrapper, and makes matched unknowns fail closed. It changes no
production code and can be rolled back by removing the evidence, script, and
test additions.

## Cross-examination and dissent

Static matching cannot prove that an arbitrary Python program has no other
writer. Receiver aliases, generated/reflected calls, native code, arbitrary
sandbox commands, and adapter semantics can evade source-name rules.
Untyped `.write` receipts can also conservatively include nonpersistent
buffers. Zero unclassified candidates therefore means zero unknowns within
the declared rules only.

The registry exposes rather than repairs generation-zero defects:

- model calls can use a different stream identity from kernel lifecycle
  events;
- scheduler and mission mutations lack a transactional event/outbox;
- direct successful sandbox, Git, and GitHub effects lack one-to-one events;
- two test event types have no production producer;
- projections can write during nominal reads; and
- crash, privacy, migration, and concurrency properties remain unproven.

## Curator remand 1 — interpreter-dependent evidence

The Curator remanded candidate
`83e9e2ca16c34d118e86ec85acd44afeadbd6107`. Python 3.14 reproduced the
artifact, while Python 3.12 produced different public-API, CLI, and observable
AST digests. Runtime-effect receipts were identical, but the supported CI
matrix would have failed.

The causes were version-sensitive `argparse` help formatting, `ast.dump`/
`ast.unparse` forms, the runtime representation of a union type alias, and a
public default containing `sys.executable`.

The repair:

- removes formatted help text while retaining semantic CLI actions;
- derives observable signatures and constant expressions from exact source
  segments;
- canonicalizes union aliases independently of `typing.Union` versus
  `types.UnionType`; and
- records interpreter-path defaults as the semantic value `sys.executable`.

The Python 3.12 and 3.14 generators must now produce structurally identical
artifacts and the same inventory digest. The supported GitHub Python 3.11 job
remains an exact-head publication gate.

## Acceptance evidence

The candidate must provide:

1. an artifact reproduced byte-for-byte from the exact source tree;
2. supported facade, package facade, and CLI contracts;
3. de-facto module inventory without a support claim;
4. 48 direct sinks, 53 producers, and 47 literal event types;
5. a bounded writer/effect registry with no unclassified matched candidates;
6. fixture version 2 linked to the artifact digest;
7. focused tests, Ruff, and Pyright passing;
8. no `src/hive_mind_os` production change; and
9. independent exact-head Curator and Judge receipts before publication.

## Rollback and appeal

Rollback removes the surface artifact, generator, fixture-v2 additions, and
this characterization record, returning to the already published Phase 1
fixture. No production state or API is modified.

An appeal is ripe only after an independent Judge disposition. A different
Appeals Judge must hear it.
