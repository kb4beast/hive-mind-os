# Phase 4A Explorer shadow substrate court

## Claims and testimony

Explorer/Clerk/Advocate `/root/phase4_explorer` mapped the exact base and found that
Phase 2 already implements transactional encounter preservation, exact duplicate
convergence, semantic candidate staging, authority intersection, memory receipt
fields, and usage attribution fields. It does not implement rich Explorer behavior,
progressive selection, canonical reusable discovery skills, or a shadow runner.

Architect/Cross-Examiner `/root/phase4_architect` recommended `adapt`: build inert
skills plus deterministic context selection and a one-shot injected engine. Skill
prose alone is too weak; a live vertical slice is unsafe before protected retrieval,
hard budget enforcement, and loop controls exist.

## Builder burden

The candidate must satisfy
`docs/architecture/PHASE4_EXPLORER_SHADOW_CONTRACT.md`, preserve all prior contracts,
and make no activation or behavioral-superiority claim. Independent
Cross-Examination, Curator, Steward, and Judge dispositions remain pending.

## Builder candidate

The first runnable candidate adds no public API, CLI, runtime selector, provider, or
tool adapter. `foundation.explorer_shadow` compiles three inert skills, selects only
whole same-scope pre-cutoff records with mandatory critical coverage, receipts every
selection and omission, excludes quarantined and same-run inputs, invokes one injected
engine, validates a closed finding shape and selected evidence membership, derives
the collision key, and uses the existing authorized `OpportunityLedger`.

Focused unittest, Ruff, Pyright, and diff checks pass. This is Builder evidence;
independent exact-byte review remains required.

## First-candidate cross-examination

Architect acting as independent implementation Cross-Examiner returned `REMAND` on
exact commit `9b34f6a8b80ab2ffac43956ff8aea55daae380f2`. Focused tests, Ruff, and Pyright pass,
but the candidate does not yet satisfy the court:

- skills are mutable runtime constants rather than strict packaged resources;
- string cutoffs, shallow typing, content-only byte counting, and unbounded input/
  output materialization are unsafe;
- later-run generated material is not excluded and selection is not durably appended;
- authority scope is checked after the engine call;
- findings are written before the full batch validates; and
- replay calls the engine again and changes `new` into `duplicate`.

Repair must deep-freeze validated packaged skills, use sealed sequence cutoffs and
canonical whole-record bounds, extend self-host exclusions, append run/selection/
failure receipts, preflight authority, validate a bounded batch before one atomic
write, and make run replay deterministic. No publication or judgment is permitted.

## Remand repair candidate

The repair replaces mutable skill dictionaries with an immutable packaged Python
resource validated against `skill-definition-v2`; adds two strict Phase 4 schemas;
uses integer sequence cutoffs and canonical whole-record byte accounting; bounds and
validates every request, record, finding, list, and hostile iterable; excludes
same-run, generated, projection, Explorer-shadow, and nonzero self-host inputs; and
preflights authentic actor/scope authority before selecting or invoking the engine.

Selection and all terminal success/failure states are append-only Foundation records.
The full finding batch validates before writes. Savepoint-safe nested transactions
make all encounters, opportunities, relations, and the terminal success receipt one
atomic unit. Operational rollback receives a terminal failure receipt. Exact run
replay returns the stored result without invoking the engine again.

Phase 3 item 1 is now explicitly treated as a historical point-in-time receipt: its
judged store digest remains pinned while the new Phase 4 inventory binds the current
store and the compatibility bridge. No Phase 3 evidence file or installed-resource
count changes.

Builder receipts are `11 passed` focused, `186 passed, 1 skipped, 63 subtests passed`
for the combined Phase 2–4 matrix, all eight governance tests, Ruff, Pyright, exact
inventory, diff checks, and an isolated installed wheel with the unchanged
133-resource contract. Phase 4 inventory is
`sha256:f9c6cc97137dc5b4188c77c65766af6bee1ffde409e231bbb2b2b351e94423b5`.
Renewed exact-byte Cross-Examination is required.

## Second cross-examination

The same independent Cross-Examiner returned `REMAND` on exact commit
`6afd1d6102ed529d3011dada65401a9d387d4247`. The first remand was repaired, but
three adversarial cases remained:

- replay identity did not bind the newly supplied context inventory, current skill
  bundle digest, and engine identity;
- duplicate finding IDs inside one batch could create contradictory encounter
  relations; and
- invalid engine identity or skill compilation failures before selection had no
  durable terminal receipt.

The Cross-Examiner required conflict without an engine call for changed replay
inputs, global finding-ID uniqueness before admission, and a failed terminal receipt
for every authorized preselection failure.

## Second remand repair candidate

Exact implementation commit `fd27593d76acf83f56b4ed68c75226bbcb4e44cd`
recomputes and compares current context, skill, and engine identity before accepting
a stored success; rejects changed replay inputs without invoking the engine; checks
finding-ID uniqueness before the admission transaction; and durably receipts invalid
engine identity and skill compilation failures with explicit unavailable sentinels.

The repair also returns defensive schema copies and enforces semantic consistency
between terminal status, selection fields, outcomes, and error code. Builder receipts
are `14 passed, 6 subtests` focused; `189 passed, 1 skipped, 63 subtests` combined;
all fourteen governance tests; Ruff and Pyright pass; isolated-wheel verification
preserves all 133 resources and validates installed Phase 4 imports. The inventory
document digest is
`sha256:b4791e6f4ebe0cca2b3833efd7350c8df227c0a4d768d1a4aeab235f51269d7c`
and its file digest is
`sha256:652006c2a626b90f0bf4e218f63087ed8c88a27456d471127e3e249ac19efc09`.
Renewed exact-commit Cross-Examination remains required.

## Renewed cross-examination verdict

Independent Cross-Examiner `/root/phase4_architect` returned `PASS` on exact
implementation commit `fd27593d76acf83f56b4ed68c75226bbcb4e44cd`.
The reviewer reproduced all 14 focused tests, Ruff, Pyright, both the Phase 4
inventory and historical Phase 3 inventory, and confirmed there is no implementation
difference in the later evidence-only commit.

The verdict specifically confirms zero-call replay conflicts for changed context or
engine identity, failed terminal receipts with zero admission writes for duplicate
finding IDs, durable preselection failure receipts, atomic admission, authority
preflight, bounded hostile iteration, and recursion exclusions. No new critical
fail-open defect was found. Curator, Steward, and distinct Judge review remain
pending; publication remains prohibited.

## Curator and Steward remands

Independent Curator `/root/item5_curator` returned `REMAND` on implementation
`fd27593d76acf83f56b4ed68c75226bbcb4e44cd`. The durable context-selection
payload omitted `policy_version`, so replay reconstructed historical receipts using
the current runtime policy constant. The Curator also found the ADR index still
named ADR-028 as the next available identifier.

Independent Steward `/root/item4_explorer/steward` separately returned `REMAND`.
Hostile `Sequence` and `Mapping` implementations could make selection and finding
validation iterate beyond declared limits; replay queries materialized complete
record histories; and two concurrent identical run invocations on one store could
both call their engines before colliding at receipt admission.

Both reviewers reproduced the prior green receipts. These remands supersede the
earlier Cross-Examiner pass for promotion purposes and remain part of the permanent
record.

## Curator and Steward repair candidate

Exact implementation commit `52f4ce8484dedd6f2b6457af331251a2e5e0f3e1`
persists and reconstructs `policy_version`, tests policy drift, and corrects the ADR
index. Context sequences and finding mappings are now consumed only to explicit
maximum-plus-one limits without trusting reported length. Replay uses unique
idempotency-key lookups with `LIMIT 1`, not whole-history scans.

One store serializes the complete shadow invocation, so a concurrent identical call
waits and replays the first result without invoking its engine. The selection check
and durable claim also execute in one immediate transaction, so a separate store
connection observes either a terminal replay or a sealed pending run rather than
calling a second engine.

Builder receipts are `18 passed, 6 subtests` focused; `193 passed, 1 skipped,
63 subtests` combined; all fourteen governance tests; Ruff and Pyright pass; and an
isolated wheel preserves all 133 resources and installed Phase 4 imports. The
inventory document digest is
`sha256:973fbd14dd87472a760f197377cae4ac204f871ce0c15eb369deb0916248bf48`
and its file digest is
`sha256:b16d565f1517cc9765a198a7023f90c598d02327551be355fbc7b59e5749d4de`.
Renewed Curator and Steward review of the exact repair is required.
