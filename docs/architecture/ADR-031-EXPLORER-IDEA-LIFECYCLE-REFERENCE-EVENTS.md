# ADR-031: Explorer idea lifecycle reference events

- Status: accepted with adapted inert scope by P4D-001
- Date: 2026-07-30
- Base: `59df5f5f2d0af45f403f74dac9781d2664f227cd`
- Extends: ADR-021, ADR-024, ADR-025, ADR-028, ADR-029, and ADR-030

## Decision

Add a package-private bridge that compiles one append-only `memory-record-v1`
reference event for each recorded Explorer idea stage: encounter, relationship,
court, experiment, or outcome.

The bridge reuses the existing Foundation store, memory contract, public-release
boundary, cognitive notes, Ideas Base, and Obsidian path. It adds no table, schema
resource, projector, public API, CLI, runtime binding, or write-back path.

Each event has a stable scoped identity, exact predecessor, common lifecycle
correlation, actor and owner, timestamp, and one digest-bearing stage reference.
A relationship reference is content-addressed over tenant, repository, source,
target, relationship, and evidence digest; SQLite row number and duplicate row count
are never semantic identity.

## Authority and privacy

Compilation grants no authority. Persistence separately requires
`foundation.memory.write`; `foundation.opportunity.write` is insufficient.
Events are private by default. Safe-public compilation still requires an independent
release decision bound to the exact resulting memory payload, followed by the
existing release and projection workflow.

Generated Markdown and Obsidian remain nonauthoritative. No private Foundation
relation graph is directly projected.

The bridge validates complete ancestry before each successor append. This is
intentionally fail-closed but has linear work per append and quadratic cumulative
cost. The package-private bridge remains inert. Runtime activation requires a later
court to adopt either a leased ancestry-work budget with observable fail-closed
exhaustion or an authenticated checkpoint/index that does not skip provenance.

## Admitted meaning

An event proves only that Hive Mind retained a scoped, content-addressed reference.
External court, experiment, and outcome locators remain `pinned-unverified`; they
do not prove artifact availability, semantic truth, customer value, lifecycle
completion, comparison, promotion, activation, or superiority. Missing future stages
remain `unknown`. An explicit early terminal disposition makes them not applicable
without fabricating later records.

## Rollback

Disable or remove the package-private bridge and its focused tests. Existing
append-only memory evidence remains governed by the original Foundation contracts
and needs no migration. Exact Phase 4C base `59df5f5` remains operational.

## Deferred

Artifact resolution and authentication, lifecycle completeness queries, private
graph visualization, v2 Obsidian view migration, automatic backfill, candidate
runtime integration, comparison, customer outcomes, learning, promotion, activation,
and superiority require later courts. Runtime integration also requires a governed
ancestry-work/depth budget or independently judged authenticated checkpoint/index
design.

## Judgment

Independent Judge `/root/phase4d_judge` issued `adapt` for exact implementation
`93c43f51488ba13177759a83191ede9f5d50210d`. The admitted scope is only the
inert, package-private reference-event bridge described above. Runtime binding,
backfill, champion use, promotion, activation, and superiority remain denied.
