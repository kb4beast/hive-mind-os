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

## Renewed Curator and Steward review

Curator `/root/item5_curator` returned `PASS` on exact repair
`52f4ce8484dedd6f2b6457af331251a2e5e0f3e1`. Historical policy identity,
ADR indexing, a separate-store pending-run probe, privacy, authority, compatibility,
packaging, and nonactivation boundaries all passed.

Steward `/root/item4_explorer/steward` retained one `REMAND`. Top-level hostile
context and mapping bounds, indexed replay, same-store convergence, cross-store
pending/replay, and interruption recovery passed, but the list-valued finding fields
still trusted hostile `list` subclass iteration for evidence IDs, acceptance criteria,
and metrics.

## Nested finding-bound repair candidate

Exact implementation commit `40bc5d6a08cbf9eb32ea4cce766da4a547e40249`
consumes all three nested list fields only through a shared explicit
maximum-plus-one limiter before membership, uniqueness, or content checks. Hostile
list subclasses are rejected after 65 values and cannot reach ledger writes.

Builder receipts are `19 passed, 9 subtests` focused; `194 passed, 1 skipped,
66 subtests` combined; all fourteen governance tests; Ruff and Pyright pass. The
inventory document digest is
`sha256:bd83372d50468a5aaf8b8272497f8d3b6ea328ed273a5e83b09c3c59973f8e66`
and its file digest is
`sha256:3b003c8fa48d4ff8ea667431a983998d2a1d482a33807a611280fa24630eb5d3`.
Only renewed Steward review is required for this remand.

## Final Steward verdict

Independent Steward `/root/item4_explorer/steward` returned `PASS` on exact
implementation commit `40bc5d6a08cbf9eb32ea4cce766da4a547e40249`.
For each nested field, the reviewer observed exactly 65 consumed values, a controlled
`ExplorerShadowError`, one failed terminal receipt, and zero encounter or opportunity
writes. Focused, combined, Ruff, and Pyright receipts reproduced with no new critical
boundedness or reliability defect.

Because the final repair changes finding validation after the earlier Cross-Examiner
and Curator exact-commit verdicts, both identities must confirm the final
implementation before judgment.

## Final Cross-Examiner and Curator verdicts

Cross-Examiner `/root/phase4_architect` and Curator `/root/item5_curator`
independently returned `PASS` on exact implementation
`40bc5d6a08cbf9eb32ea4cce766da4a547e40249`.

Cross-Examination reproduced policy drift, indexed replay, all hostile-container
bounds, same-store one-engine convergence, separate-store pending then replay,
changed-input conflicts, duplicate finding rejection, and preselection failure
receipts. Curator independently confirmed the nested-list bounds, failed terminal
receipts, zero admissions, privacy, unchanged schema/authority/public surfaces, exact
inventories, and inert nonactivation boundaries.

The final technical receipts are `19 passed, 9 subtests` focused; `194 passed,
1 skipped, 66 subtests` combined; all fourteen governance tests; Ruff and Pyright
pass; the 133-resource installed-wheel contract remains unchanged. Explorer,
Architect, Builder, Cross-Examiner, Curator, and Steward burdens are satisfied for
this bounded candidate. Distinct Judge disposition remains required.

## First Judge disposition

Distinct Judge `/root/item5_judge` issued `defer` on implementation
`40bc5d6a08cbf9eb32ea4cce766da4a547e40249` and evidence head `d754da1`.
Technical evidence passed, but lifecycle evidence did not:

- the Architect also served as implementation Cross-Examiner;
- no separately identified Integrator or Optimizer verdict existed; and
- the Orchestrator scope, budget, dependencies, stopping conditions, and court
  schedule were not explicitly receipted.

A stacked draft PR is prohibited until those identities report and a distinct Judge
renews judgment. No activation, public release, live-provider readiness, usefulness,
customer value, semantic quality, performance, or superiority claim is admitted.

## Orchestrator receipt

Orchestrator `/root` records the following bounded Phase 4A decision:

- **Outcome:** prove only an inert, package-private Explorer shadow substrate over
  existing authorized storage; no behavioral-value or activation claim.
- **Scope and authority:** additive skills, deterministic context selection,
  one injected engine call, typed findings, and existing opportunity admission.
  No live provider, tool, Git, web, public projection, champion, or runtime selector.
- **Budgets:** at most 256 context records, 1,000,000 canonical context bytes,
  64 findings, 64 values per nested finding list, and one engine call. Review work
  is limited to exact-delta attacks after each remand.
- **Dependencies:** judged Phase 3 head `2cbfe1d`, existing FoundationStore,
  OpportunityLedger, canonical/schema validators, and the unchanged 133-resource
  installed-wheel contract.
- **Recovery and rollback:** pending sealed runs fail closed for explicit recovery;
  same-store calls serialize; separate-store calls observe pending or replay;
  callers can remove the opt-in substrate without changing active Generation Zero.
- **Stopping conditions:** stop and remand on any unbounded input, ambiguous run
  identity, missing receipt, second engine call, partial admission, authority leak,
  public/activation drift, compatibility failure, or missing independent role.
- **Court schedule:** preserve each remand; obtain distinct Cross-Examiner,
  Integrator, and Optimizer receipts on the exact implementation; then renew Judge
  review. Only an `adapt`/`adopt` verdict may permit a stacked draft PR, which must
  remain open, draft, unmerged, and inactive.

## Distinct Cross-Examiner remand

New identity `/root/phase4_distinct_cross`, with no prior Explorer, Advocate,
Architect, Builder, Curator, Steward, or Judge role in this case, returned `REMAND`
on implementation `40bc5d6a08cbf9eb32ea4cce766da4a547e40249`.

The injected engine received the same frozen dataclass instances later used for
terminal and evidence receipts. Reflective `object.__setattr__` mutation could
therefore make a successful terminal request digest disagree with its sealed
selection and derive encounter evidence from post-selection content while store
integrity still passed. Separately, exported skill mapping proxies retained a private
mutable dictionary alias, allowing schema-valid packaged skill drift.

## Sealed-input and immutable-skill repair candidate

Exact implementation commit `f91d227bbe8ddcdb5d8833aafcf695f6ccd302f8`
copies the request at the trust boundary, snapshots each validated context record,
and passes further independent request/context copies to injected engine code.
Admission and terminal receipts therefore reuse internal pre-engine snapshots even
when the engine reflectively mutates its copies.

Packaged skills now have no retained mutable backing alias, use immutable nested
values, and must compile to the pinned bundle digest
`sha256:f0c149f6ae3a738cc0324ecb3311e0a3ff93cdfd4923be3709e3c9e5e5b05985`.
Schema-valid drift fails compilation. Direct attacks cover reflective request/context
mutation, matching sealed request digests, pre-engine evidence digests, absent mutable
backing, mapping immutability, and pinned-digest failure.

Builder receipts are `20 passed, 9 subtests` focused; `195 passed, 1 skipped,
66 subtests` combined; all fourteen governance tests; Ruff and Pyright pass. The
inventory document digest is
`sha256:6b5656608a5a53c104d4e9139f0ac485eebec6eab6db3d3350a4581b62816b36`
and its file digest is
`sha256:ba453267f1dee2097430d0054156d7c93306e6d910b500d377de62aacc10945e`.
Distinct Cross-Examiner renewal remains required; Integrator and Optimizer roles are
still open.

## Lifecycle closure verdicts

Distinct Cross-Examiner `/root/phase4_distinct_cross` returned `PASS` on exact
implementation `f91d227bbe8ddcdb5d8833aafcf695f6ccd302f8`. Reflective engine
mutation left caller and sealed snapshots unchanged, selection and terminal request
digests matched, admitted evidence retained its pre-engine digest, integrity passed,
the mutable skill alias was absent, direct mutation failed, and schema-valid drift
was rejected by the pinned bundle digest.

Independent Integrator `/root/phase4_explorer/integrator` returned `PASS` for the
bounded integration. Phase 2–4 contracts, FoundationStore, OpportunityLedger,
inventories, governance, package-private boundaries, root/foundation exports, CLI,
runtime, projections, packaging, and rollback remained compatible and inactive.
No public projection or private-data boundary changed.

Independent Optimizer `/root/phase4_explorer/optimizer` returned `PASS` only for the
inert substrate. The numeric byte/count/call envelopes and honest deferred claims are
adequate for this slice. Finding metrics and stopping strings remain hypotheses;
caller classification can bias selection; no token/cost/time budget, semantic quality,
baseline, holdout, causal attribution, learning, challenger/champion, regression,
safety-budget, or multi-comparator superiority evidence exists. Therefore no value,
learning, activation, promotion, or superiority claim is admitted.

The Orchestrator, Explorer, Architect, Builder, distinct Cross-Examiner, Curator,
Integrator, Steward, and Optimizer duties are now explicitly receipted. Because the
final sealed-input repair postdates the Curator's exact-commit verdict, final Curator
confirmation and renewed distinct judgment remain required.

## Final Curator confirmation

Curator `/root/item5_curator` returned `PASS` on exact implementation
`f91d227bbe8ddcdb5d8833aafcf695f6ccd302f8`. Reflective mutation of engine
snapshots and externally retained originals could not alter sealed request,
selection, evidence, terminal, privacy, or integrity receipts. Skill drift failed
against the pinned digest before an engine call, emitted one failed terminal, and
wrote zero admissions. All 20 focused tests, the 195-test combined matrix,
governance, Ruff, Pyright, both inventories, and the exact installed wheel passed.

The independently rebuilt exact wheel preserved all 133 resources, imported the
Phase 4 modules, and compiled the inert authority-none bundle to its pinned digest.
All mandatory lifecycle roles and final implementation receipts are now present.
Renewed distinct Judge disposition is required before any draft publication.

## Final Judge disposition

Distinct Judge `/root/item5_judge` issued `adapt` on exact implementation
`f91d227bbe8ddcdb5d8833aafcf695f6ccd302f8` with evidence head
`aebb84c87723cb4c684dfab086f0ed79382eafd1`. The prior `defer`, every remand,
dissent, repair, and losing assumption remains preserved. All required specialist
and court identities now have explicit receipts.

The verdict admits only the bounded, inert, package-private Explorer shadow
substrate. It permits a stacked PR based on
`codex/phase3-federation-recursion-guards` only while open, draft, unmerged, and
inactive. It does not admit activation, public release, live provider/tool readiness,
semantic quality, usefulness, customer value, learning, promotion, or superiority.
Caller classification, byte-versus-token budgeting, pending-run recovery, semantic
evaluation, live integration, and champion/challenger evidence remain deferred.
