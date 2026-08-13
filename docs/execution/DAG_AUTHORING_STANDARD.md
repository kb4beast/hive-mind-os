# DAG Authoring Standard

Normative requirements for any dependency DAG that Hive Mind OS builds and executes for
any repository.

**Enforcement status — read this before citing the standard as a gate.** `autopilot
dag-lint` (`.autopilot/bin/dag_standard.py`, wired at `.autopilot/bin/autopilot.py:796`
`add_dag_standard_arguments(commands)` and dispatched at `:869-872`) mechanically checks
*part* of this document. The rest is author-verified. §8 states, per requirement, which is
which; do not assume a MUST here is machine-enforced.

**Not yet bound to `BUILD_DAG`.** Making the DAG-build flow
(`_uninstalled_contract`, `src/hive_mind_os/autopilot_workflow.py:964`) require
conformance to this standard by digest is *specified* in
`docs/execution/runbooks/PRODUCT-GENERIC-DAG.md` §3.4 and is **not implemented**. The
shipped `task_prompt` (`autopilot_workflow.py:1009-1022`) does not name this document.
Until that lands, conformance is an authoring discipline plus `dag-lint`, not a product
gate.

This document is repository-neutral and language-neutral: every rule is stated so it holds
without knowing the repository's ecosystem. Bracketed `[Example]` notes cite incidents from
the Hive Mind OS repository's own DAG only to illustrate a failure mode, never as
requirements about that repository.

---

## 1. Why: a BFS level is not an executable wave

A breadth-first traversal produces *levels*. A level is not a thing you can run. Keep
three concepts distinct.

**Dependency level** — graph depth: the nodes whose dependencies all sit at strictly lower
depth. A property of the graph alone. It says nothing about whether those nodes may write
concurrently, collide on files, or fit a session budget.

**Dispatch round** — the nodes actually released to workers at one time. A round is
*compiled* from a level by removing conflicts (file-lock overlap, semantic-lock
intersection), isolating serial nodes, and capping at session capacity. One level yields
one or more rounds. Never fewer.

**Integration transaction** — the merge of one round's completed node branches into the
shared target branch, in a declared order, by a single integrator, followed by exactly one
repository-wide validation. A round advances the target only through this transaction.

A DAG that encodes only levels is underspecified for execution.

---

## 2. Node contract requirements

Every node MUST carry these fields, concretely populated. Empty, absent, or placeholder
values are contract-incomplete and block release.

**`write_scope`** — concrete paths or narrow directory globs the node may create or
modify. No bare recursive glob, no whole top-level directory glob. If a node cannot name
what it writes, it is not decomposed enough. *(AUTHOR-VERIFIED — `dag-lint` checks only
that `write_scope` is present and non-empty; it does not check that it is narrow.)*
`file_locks` must cover the write scope; overlap is computed by `scopes_overlap`
(`.autopilot/bin/controller.py:368`) via `_nodes_conflict`
(`.autopilot/bin/release_barrier.py:244`).

**`read_scope`** — concrete paths the node needs to read. Globs are not banned. The
agreed rule is *concrete paths plus metadata-only indexing, with budgeted and recorded
cold expansion* — not an absolute prohibition on globs:

1. Name the concrete files and directories the work is known to need.
2. For discovery, use *metadata-only indexing*: a path listing, symbol/table-of-contents
   index, or grep result set — not full file bodies.
3. If the node proves mid-execution that its read scope was incomplete, it may perform a
   **budgeted cold expansion**: a bounded additional read (declare the budget, e.g. N
   files or N tokens) that is **recorded** as evidence naming the paths added and why.
   Unrecorded expansion is a contract violation; recorded expansion is normal and feeds
   back into the next DAG revision.

**Severity — stated to match the linter, not to overstate it.** A *universal* read scope —
a bare recursive glob (`**`, `**/*`) or a whole top-level directory glob (`src/**`,
`lib/**`, `pkg/**`, `app/**`: any single top-level directory, whatever the ecosystem calls
it) — invites a worker to ingest the whole tree it covers. `dag-lint` emits it as a
**WARNING** (check `universal-read-scope`), not an error. Per §8, a warning does not block,
but it MUST carry a recorded justification naming the node, the check, and why the
universal scope is correct here — normally "this is a declared discovery node with read
budget N". An unrecorded universal read scope is treated as an error at the next gate.
Deeper globs (`src/pkg/sub/**`) are not flagged and are not banned.

**`forbidden_scope`** — explicit: other nodes' write scopes, sealed plan and control-plane
files, protected branches, and any shared scaffold this node does not own (§3). "Not in my
write scope" is not the same as "forbidden"; state the prohibition.

**`required_tests`** — non-empty, and every entry a literal runnable command in this
repository (`pytest tests/foo/test_bar.py`, `npm test -- --run src/bar`,
`go test ./pkg/bar/...`). Not "unit tests pass". Not a suite name that no command
produces. Focused: the node's own tests, not the repository suite (§6).

**`stopping_condition`** — an observable predicate that tells the worker it is done and
must stop. Not "the feature works" — "`required_tests` green, receipt written, claim
settled, no files touched outside `write_scope`".

**`rollback`** — how to undo this node's effect without unwinding neighbors. For a pure
code node, "revert the node branch" suffices only if the node branch is never rebased or
squashed (§6). For nodes with external or stateful effects, name the compensating action.

**`parallel_safe`** — set honestly. False if the node touches shared configuration, a
migration, a lockfile, a registry, or anything whose concurrent modification is
unresolvable by merge. A dishonest `true` is far more expensive than a conservative
`false`: it produces a merge the integrator cannot settle.

**`semantic_locks`** — name shared **interfaces**, not just files. Two nodes editing
different files that both change the same public function signature, event schema, config
key namespace, CLI surface, or database table conflict semantically even though their
file locks are disjoint. `_nodes_conflict` intersects these sets literally, so the lock
names must be a shared controlled vocabulary across the DAG (`iface:control-plane-api`,
`schema:receipt-v1`), not free text.

---

## 3. Scaffold ownership

**PRIMARY RULE (normative, language-neutral).** If two or more nodes eligible in the same
round would create the *first* files in a directory that no node owns, that is an
**error**. The directory needs exactly one named owner before either node runs. This rule
is stated over the graph — "two creators, one unowned directory" — and therefore holds in
every ecosystem without knowing which marker file that ecosystem requires. Marker-file
tables (below) are an *enhancement* that makes the finding more precise and its fix more
concrete; they are never the source of the requirement, and a language absent from the
table does not exempt a plan.

**Corollary — implied scaffolds.** Any file that two or more nodes might both need to
*create* MUST have exactly
one named owner node, or be explicitly forbidden to all of them and created by a prior
node. Static file-lock overlap cannot find these: the colliding file is in *neither*
node's declared write scope, because each author scoped the files they consciously intend
to write and forgot the scaffolding those new files imply.

[Example] Two same-level nodes in this repository's DAG declared disjoint write scopes but
both needed `tests/hive_cortex/__init__.py` to make their new test packages importable.
The file was in neither scope. Both would have created it; whichever merged second
conflicted or silently clobbered.

**Derivation procedure** — for each node, for each *new* file in its `write_scope`:

1. Walk from the new file up to the repository root. Every intermediate directory that
   requires a marker file to be a valid package/module/target in this ecosystem yields an
   implied scaffold path (`__init__.py`, `mod.rs`, `index.ts`, `package.json`,
   `BUILD`/`CMakeLists.txt`, `conftest.py`). This list is illustrative, not exhaustive: an
   ecosystem missing from it is still governed by the primary rule above.
2. Add the ecosystem's shared mutable manifests that a new file may force: dependency
   manifests and lockfiles, test/build configuration, generated barrels and re-export
   indexes, service/plugin registries, fixture roots, migration sequence files, i18n
   catalogs, CI job matrices.
3. Union these implied paths across all nodes. Any path implied by two or more nodes, or
   implied by one node and already owned by another, is a **contested scaffold**.
4. Resolve each contested scaffold by one of: assign it to exactly one node's
   `write_scope` and add it to every other implicated node's `forbidden_scope`; or hoist
   it into a prior scaffold node that all contenders depend on. Record the choice in the
   node contract, not only in prose.

**Already-established surfaces are not contested.** A scaffold that already exists in the
working tree, or that sits inside a directory that already exists, needs no creator: a
missing `conftest.py` beside working tests means none is required, not that two nodes are
racing to add one. Only *first* files in a *new* directory are judged. A plan linted
without a repository (a freshly authored DAG, before any clone) treats every implied
scaffold as absent, which is the correct conservative default.

**Severity.** A contested scaffold implied by two or more same-level nodes with no single
owner is a `dag-lint` **error** (check `scaffold-collision`) and blocks. Two weaker cases
are **warnings**: a scaffold implied by only one node but outside that node's declared
write scope, and a shared repository-root manifest implied by two nodes introducing the
same new top-level source root. Both still require a recorded justification per §8.
A glob that merely *covers* a scaffold path is permission, not ownership: only a literal
path in a node's `write_scope` (or an implier whose own scope already covers it) makes that
node accountable.

**A file is not required to have an extension.** Requiring a dot in the last path segment
is a language assumption, not a fact about repositories: `Dockerfile`, `Makefile`, Bazel
`BUILD`/`WORKSPACE`, `Earthfile`, `Gemfile` and extensionless shell entry points are
ordinary files, and two nodes creating the first of them in a new directory contest it
exactly as much as two `.go` files would. The primary rule counts every literal
multi-segment `write_scope` entry as a file in its parent directory. A *top-level* entry
(`src`, `Makefile`) has no parent below the repository root and is skipped, so a literal
scope that is really a directory can never invent a surface.

**The marker table must name nothing rather than name the wrong thing.** A marker is only
emitted where that ecosystem genuinely puts one: `mod.rs` declares a module *inside* a
crate's source root, so `src/engine/mod.rs` is real while `crates/engine/mod.rs` is not
(that crate root wants `Cargo.toml` and `src/lib.rs`, which the table cannot locate); and a
Jest `__tests__` directory is a folder of files with no barrel, unlike a Python test
package or a .NET test project. Where the table cannot state the artifact truthfully it
emits none and the surface is reported by the primary directory rule instead — a less
precise finding, never a quieter one. Both still block.

---

## 4. Ordering rules beyond raw dependencies

Data dependencies are necessary, not sufficient. An author MUST additionally apply these
orderings, adding explicit edges where the raw graph does not already imply them.

**Durability before crash/resume proofs.** A node whose acceptance criteria assert
recovery from crash, restart, resume, interruption, or replay MUST depend transitively on
the node establishing the durable state those criteria rely on. *Failure mode:* acceptance
is unprovable — the worker can only simulate recovery against volatile state, and will
either fabricate evidence or block. [Example] a node asserting "mission resumes after
interruption without restating context" sat at the same dependency level as the node
building durable mission state.

**Durability before external-effect delivery.** A node performing effects outside the
repository — push, PR, comment, deploy, notification, webhook, payment — MUST depend on
the durability node. *Failure mode:* a crash mid-delivery leaves an un-replayable external
effect with no record of whether it happened; retry duplicates it, with no idempotency key
to consult.

Only the first two of the four orderings below are machine-checked, and only as
**warnings**: `dag-lint`'s `durability-ordering` check matches recovery vocabulary
(crash/restart/resume/interrupt/replay/recover) and external-effect phrases
(push/pull request/comment/deploy/publish) in a node's `objective` and
`acceptance_criteria`, ignoring a phrase that a negation precedes ("no hidden deploy
authority") or that a passive denial trails ("direct push is forbidden"). It then reports
the node if any durability provider sits at the **same or a later dependency level** and is
not already an ancestor. A provider at a strictly *earlier* level is silently accepted: the
level ordering already guarantees it is integrated first, so no edge is needed. A plan that
asserts these semantics with *no* durability provider anywhere is reported too.

Because it is a heuristic over English prose, this check is capped at warning severity and
can never block a plan on its own. It is not merely advisory, however: each finding is
converted into a scheduling constraint that splits the round (§5 step 2), so an unaddressed
warning changes the compiled schedule rather than being ignored. The two orderings that
follow are **AUTHOR-VERIFIED** — no check exists.

**Safety and poisoning gates before activating learned behavior.** *(AUTHOR-VERIFIED — not
machine-checked.)* A node that lets the
system act on learned, inferred, accumulated, or externally supplied signal MUST depend on
the node implementing that signal's validation, provenance, and rejection path. *Failure
mode:* activation ships first, the system is briefly and verifiably exploitable, and the
gate node must then prove a negative retroactively.

**Benchmark before authoritative promotion.** *(AUTHOR-VERIFIED — not machine-checked.)*
A node making some component canonical,
default, or authoritative MUST depend on the node producing the comparative measurement
that justifies it. *Failure mode:* promotion is a claim with no evidence; the benchmark
later contradicts it, and the DAG has no rollback for a promotion already merged.

Each of these is an *edge you add*, and the reason for the edge belongs in the node's
`rationale` so a later author does not "optimize" it away.

---

## 5. Round compilation

Levels split into rounds by this procedure. It MUST be deterministic and re-runnable.

1. Take the level's eligible nodes (dependencies satisfied, not stopped).
2. **Semantic ordering (durability barriers).** Apply the §4 orderings that the raw graph
   does not yet encode as edges. Where a level contains both a durability provider and a
   node whose claims depend on it, the provider is a **release barrier**: it is dispatched
   and integrated *alone*, and every other member of that level is deferred behind it, so
   the rest of the level is proven against durable state that actually exists. A provider
   in a *later* level defers only the node that named it. This step runs **before** packing
   — it splits one level into several release groups, and steps 3–6 then apply within each
   group independently.
3. **Serial isolation.** Every node with `parallel_safe: false` becomes its own round,
   alone. It may share a round with nothing.
4. **Conflict-free packing.** Among the remaining parallel-safe nodes, pack greedily into
   rounds such that no two nodes in a round conflict under `_nodes_conflict` — file-lock
   overlap or semantic-lock intersection — **and** do not declare overlapping `write_scope`
   (a stricter condition the dispatcher does not model; see §8 check 7), **and** are not
   reported as contending for an unowned shared scaffold (§3, check `scaffold-collision`
   at `error` severity). Dispatching a reported contending pair together *is* the
   collision, so the compiler defers one member; the surface then already exists when the
   other runs. Naming exactly one owner — the fix §3 prescribes — removes the finding and
   lets the pair share a round again. Warnings never split a round: they describe a
   contract defect for the author to fix, not a schedule hazard.
5. **Capacity cap.** Truncate each round to the executor's concurrent session capacity.
   Remaining nodes form the next round.
6. **Emit parallel rounds before serial rounds within a release group**, so a
   high-importance serial node cannot cap the group's first wave at one session; within a
   round, declare the integration merge order.

Steps 2–6 are exactly what `autopilot dag-rounds` implements, so the compiled schedule and
this procedure agree by construction. **Step 2 is not optional and not cosmetic.**
`dag-rounds --no-semantic-ordering` disables it and falls back to pure lock/capacity
scheduling; use that flag only to *see* the unordered schedule, never to execute one.

> [Example] In this repository's own DAG, level 7 holds five mutually conflict-free,
> parallel-safe nodes. Steps 3–5 alone compile them into a single five-session round.
> Step 2 recognizes that two of them assert resume and external-delivery semantics that
> the level's durability provider establishes, and splits the level into a one-session
> barrier round followed by a four-session round. Both schedules are lock-legal; only the
> second is provable.

**The dispatcher MUST be given an explicit node list.** *(AUTHOR-VERIFIED — nothing checks
that the operator actually passed one; `dag-rounds` only prints the correct command.)*
`dispatch` (`.autopilot/bin/release_barrier.py:299`) accepts `requested_nodes` and
validates them against eligibility, `parallel_safe`, and conflicts. Its fallback greedy
selection — used only when no list is supplied — sorts by critical-path importance
(`ordered = sorted(eligible, key=…)`, `:352-359`) and can pick a serial node first, after
which `if any(not bool(self.node(chosen).get("parallel_safe")) for chosen in wave): continue`
(`:366-370`) rejects every subsequent candidate and the wave is capped at one session. That is a correct implementation of "greedy over a level" and a
wrong execution plan. Compile the round, then pass it.

---

## 6. Execution invariants

The DAG MUST be executable under these invariants; author node contracts assuming them.

1. **Workers never mutate the shared target branch.** Each node works on its own node
   branch. Only the integrator touches the target.
2. **A single integrator merges, in the round's declared order.** Concurrent integration
   is not an optimization; it is the loss of a serialization point.
3. **Never rebase or squash a node branch.** Rollback (§2) and receipt-to-commit binding
   depend on the node branch's commits surviving into the target's ancestry.
4. **Claims are settled explicitly and never allowed to lapse once a branch is mutated.**
   A worker that has written anything must release, fail, or escalate its claim by an
   explicit action. Expiry-by-timeout on a mutated branch leaves work whose ownership and
   completeness are both unknown.
5. **One repository-wide validation per round, run by the integrator.** Per-node
   repository-wide validation serializes N parallel workers on a single lease all running
   the same expensive suite. Workers run their own `required_tests` only; the round's full
   suite runs once, after integration.
6. **The sealed plan and control-plane state are read-only to workers.** Node contracts
   must list them in `forbidden_scope`.

---

## 7. Token economy requirements for authoring

**The rendered prompt IS the node contract.** Author node contracts so that the rendered
worker prompt is sufficient to do the work. Workers MUST NOT be instructed to read the
whole plan file to discover their own contract — plan files run to tens of thousands of
tokens, and the controller enforces every gate deterministically regardless of what the
worker read. [Example] re-reading this repository's plan file cost roughly 18.5K tokens
per worker for information the prompt already carried.

**Per-node runbooks carry implementation detail.** Keep the node contract to scope,
tests, stopping condition, and locks. Put procedure, commands, and gotchas in a per-node
runbook the prompt links; the worker reads one file, not the corpus.

**Focused tests only.** Workers run `required_tests`; the repository suite runs once per
round at integration (§6.5).

**No duplicate discovery.** If several nodes need the same survey of the codebase, make it
one upstream node whose output is a written index, and give the downstream nodes that
index in `required_inputs`. Paying for the same exploration N times is the single largest
avoidable cost in a wide DAG.

---

## 8. Author checklist — and exactly what is enforced

This checklist is **partly mechanized**. Do not treat it as a machine gate. Run
`python .autopilot/bin/autopilot.py --repo-root . dag-lint --json`, then work the
AUTHOR-VERIFIED rows by hand; a warning is not a pass and an absent check is not a pass.

`dag-lint` emits ten checks. Their real names and severities, verified against
`.autopilot/bin/dag_standard.py` by enumerating every `check=` literal in that file
(`graph-validity`, `scope-syntax`, `parallel-safe-declaration`, `contract-completeness`,
`universal-read-scope`, `write-scope-overlap`, `scaffold-collision`,
`durability-ordering`, `serial-in-level`, `capacity-split`). **Five of them can emit
`error` and therefore block**: `graph-validity`, `scope-syntax`, `contract-completeness`,
`write-scope-overlap`, and the `≥2 impliers` form of `scaffold-collision`. Three emit
`warning` (`universal-read-scope`, `parallel-safe-declaration`, `durability-ordering`) and
two emit `info` (`serial-in-level`, `capacity-split`):

| Checklist item | `dag-lint` check | Severity | What the code actually verifies |
|---|---|---|---|
| 1. Graph validity | `graph-validity` | error | unique ids, every dependency resolves, no self-dependency, no cycle, levels computable |
| 2. Scaffold collision | `scaffold-collision` | error / warning | implied scaffolds derived from created paths; ≥2 same-level impliers with no single owner = error; single implier outside its own scope, or a shared root manifest, = warning |
| 3. Universal read scope | `universal-read-scope` | **warning** | `read_scope` entries that are a bare recursive glob or a whole top-level directory glob |
| 4. Durability ordering | `durability-ordering` | **warning** | recovery / external-effect vocabulary in `objective` + `acceptance_criteria` without a durability provider among ancestors |
| 5. Serial-in-level | `serial-in-level` | **info** | a level mixing serial and parallel-safe nodes; reports the compiled rounds |
| 5b. Capacity split | `capacity-split` | **info** | a level wider than the session cap; reports the compiled rounds |
| 6. Contract completeness | `contract-completeness` | error | presence and non-emptiness of `required_tests`, `stopping_condition`, `rollback`, `forbidden_scope`, `write_scope` — **presence only** |
| 7. Write-scope overlap | `write-scope-overlap` | error | two nodes that are both `parallel_safe` **and sit at the same dependency level** declare `write_scope` entries resolving to a common path. Computed from `write_scope` alone, deliberately independent of `file_locks`: the write scope is what the worker is told it may write. Nodes at different levels are not compared (the dependency edge already orders them) |
| 8. Scope syntax | `scope-syntax` | error | a `write_scope` or `file_locks` entry the dispatcher's own lock parser cannot anchor — bare `**`, `**/*.py`, `*.md`, an absolute path, or `..` traversal. Such a pattern has no static prefix, so conflict detection cannot prove disjointness against anything; it blocks rather than silently forcing every node into its own round. Note this is what actually rejects `write_scope: ["**"]` — *not* `contract-completeness` |
| 9. `parallel_safe` declared | `parallel-safe-declaration` | **warning** | a node carrying no `parallel_safe` key at all. Omission is read as `false`, so the node is silently released alone and costs a dispatch round. Emitted once per undeclared node, or as a single plan-wide finding when no node in the plan declares it |

**AUTHOR-VERIFIED — no check exists for any of these.** Each is normative; none is
machine-enforced. State in the sealing receipt that you verified them by hand.

- **Narrow `write_scope`** (§2). Presence is checked; narrowness is not. A node may declare
  `write_scope: ["src/**"]` — an entire top-level source tree — and draw **zero findings of
  any severity**. (A bare `write_scope: ["**"]` is a different case: it is rejected, but by
  `scope-syntax`, because it cannot be anchored — not because anything judged it too wide.)
- **`read_scope` presence** (§2). `read_scope` is not in the completeness field list. A node
  with *no* `read_scope` at all raises nothing; only a universal one warns.
- **`required_tests` are runnable commands** (§2). Only non-emptiness is checked. `"unit
  tests pass"` passes the linter and is still a contract violation.
- **`stopping_condition` and `rollback` are meaningful** (§2). Only non-emptiness is checked.
- **Honest `parallel_safe`, `semantic_locks` naming shared interfaces, `file_locks` covering
  `write_scope`** (§2). Not checked at all.
- **Safety and poisoning gates before activating learned behavior** (§4).
- **Benchmark before authoritative promotion** (§4).
- **The dispatcher is invoked with an explicit node list** (§5). `dag-rounds` *prints* the
  correct command; nothing verifies the operator ran it.
- **Every execution invariant in §6** and **every token-economy requirement in §7**.

**Lint severity semantics.** Lint **errors** block DAG sealing and dispatch (`dag-lint`
exits 1). Lint **warnings** do not block by default, but each one MUST carry a recorded
justification naming the node, the check, and why the deviation is correct for this
repository; an unjustified warning is treated as an error at the next gate. `dag-lint
--strict` makes warnings exit non-zero, which is the right setting for a sealing gate once
the justifications are recorded. **Info** findings are compilation facts, not deviations,
and need no justification.
