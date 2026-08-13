# Architecture Decision: Private Knowledge First, Safe Learning Second

- Decision ID: `ADR-KP-2026-08-13`
- Status: **accepted for implementation planning; not implemented**
- Court disposition: **adapt**
- Baseline: `main` at `a93df2632f259f4b63f7a4f27eb0b163b5a47204`
- Deciders: `codex:knowledge-judge` after separate Scout, Advocate,
  Cross-Examiner, and Expert Witness briefs
- Product owner for the plan: Orchestrator

This record authorizes an additive implementation program. It does not change the
normative architecture, activate a runtime, publish data, or claim product readiness.
Any eventual architecture-contract change still requires its normal governed ADR,
tests, Curator reproduction, and exact-candidate court.

## Context

The requested product must remember everything material Hive Mind considered, show
why work moved forward or returned to an earlier stage, connect every specialist and
court role to evidence, preserve champions and challengers so ideas are not needlessly
repeated, and work as a tool for repositories other than this one. It must also prevent
secrets, customer/private data, proprietary expression, identifying repository details,
and incompatible-license material from becoming shared learning.

Current `main` supplies useful event, memory, court, lesson, challenger, evaluation,
promotion, rollback, and operational-projection primitives. It does **not** implement
the requested stable idea-pass model, complete knowledge authority, Obsidian-compatible
private projector, shared release gateway, sanitized registry, or their end-to-end
integration. A divergent Phase 3 branch contains useful patterns but is not current-main
product evidence and is not merge-ready.

## Decision

Implement the product in five ordered boundaries:

1. **Prerequisite authority and intake safety.** Reconcile every current store and
   source obligation; close capability expansion through the actual effect boundary;
   make lessons content-bound, provenance-resolved, time-valid, inert on import, and
   unable to inject shared prose into a challenger or prompt; quarantine existing
   cross-repository Autopilot lesson details without rewriting history.
2. **Protected canonical knowledge.** Add one explicit append-only knowledge authority
   with repository-neutral identities, typed records and edges, point-in-time replay,
   protected/erasable bodies, retained deletion receipts, and stable `Idea` plus
   immutable ordered `IdeaPass` records.
3. **One-shot private projection.** Deterministically project permitted summaries and
   every permitted relationship into an external per-repository Markdown/YAML/JSON
   vault. Obsidian may render the vault after current official compatibility evidence is
   admitted, but it is optional, disposable, and never authoritative.
4. **Offline safe-learning release.** Compose a new structural allowlist from private
   evidence; pass it through separate authority, provenance, sensitivity, proprietary,
   personal-data, secret, license, topology/linkage, poisoning, independence, retention,
   and revocation gates; retain the denied or approved decision. Before the exact
   release court, use only synthetic, license-clean inputs.
5. **Local inert reuse.** Admit only approved content-addressed abstractions into a
   local sanitized registry. Explorer and Optimizer may cite them as read-only prior
   art. A shared record never executes, grants authority, mutates a champion, enters a
   prompt as free text, or automatically creates/promotes a challenger.

The program's first release checkpoint is the private canonical store plus one-shot
private projector and trace. The local shared registry is a later safety laboratory,
not a prerequisite for that private MVP.

## Authority and storage model

| Plane | Authority | Permitted content | Explicit exclusions |
| --- | --- | --- | --- |
| Canonical metadata | Protected append-only knowledge store | Opaque IDs, types, edges, actor/role, timestamps, evidence digests, decisions, classifications, receipts | Generated filenames, mutable titles, Obsidian state |
| Protected payload | Separate access-controlled body storage | Policy-permitted private summaries and source references | Raw credentials; content whose ownership, legal status, or retention is unknown |
| Private projection | Least-authority one-shot projector | Permitted summaries, links, roles, courts, passes, work, outcomes, lessons, challengers, conflicts, tombstones | Raw secrets, hidden reasoning, raw transcripts, unbounded tool/log bodies |
| Local shared registry | Separate offline release authority | Newly composed abstract mechanism, applicability, constraints, evaluated status, uncertainty, counterexamples, expiry, revocation, non-reversible digests | Repository/source/patch/prompt bodies, private identifiers, paths/remotes/branches, customer or proprietary expression |

No role, court participant, watcher, plugin, or human edit writes directly to generated
notes as canonical state. A generated note cannot grant authority or become evidence
merely by existing.

## Record and transition model

Record types do not mutate into other types. Each transition appends a record and a
typed relation:

```text
Source -> AtomicClaim -> IdeaEncounter -> Idea -> IdeaPass
IdeaPass --adopt/adapt--> WorkItem -> Candidate -> VerifiedDeliverable
VerifiedDeliverable -> Delivery -> Outcome -> LearningSignal -> Lesson
Lesson -> Challenger -> Evaluation -> Promotion | Rejection | Rollback
Outcome | Incident | Appeal | Remand -> ReentryEvent -> later IdeaPass
SharedLearningCandidate -> ReleaseDecision -> SharedLearning | Quarantine
```

An idea may traverse the conceptual lifecycle repeatedly. The implementation DAG and
durable chronology remain acyclic: every return creates a later immutable pass, remand,
appeal, reversal, re-entry, or successor-work record. The semantic backward edge cites
the earlier requested stage; it never rewrites or schedules an earlier node again.

Every backward transition must retain:

- source gate and requested destination stage;
- exact reason and cited evidence;
- actor, specialist role, and court seat where applicable;
- prior pass/work/candidate and later pass/work that fulfills the request;
- authority, timestamp, point-in-time subject commit, and disposition; and
- dissent, counterexamples, losing alternatives, and appeal conditions.

## Role model

All eight specialist roles remain distinct in the graph:

- Orchestrator owns outcome, decomposition, budgets, dependencies, scheduling,
  stopping, re-entry reasons, and handoff.
- Explorer owns source admission, idea encounters, collisions, prior-art lookup, and
  evidence-backed problem selection.
- Architect owns identity, contracts, invariants, threats, migration, rollback, and
  authority boundaries.
- Builder owns isolated implementation and focused executable tests.
- Curator independently reproduces correctness, provenance, privacy, IP, licensing,
  disclosure, and release evidence.
- Integrator owns versioned boundaries among stores, projections, repositories,
  tenants, registry, CLI, and delivery.
- Steward owns durability, replay, drift, conflicts, backup, restore, retention,
  takedown, tombstones, and operational health.
- Optimizer owns lesson admission, outcome evaluation, champion/challenger linkage,
  controlled experiments, and promotion evidence.

Temporary Clerk, Advocate, Cross-Examiner, Expert Witness, Judge, and Appeals Judge
identities are recorded separately. A role node or declared wiring is not proof of
behavior: every episode carries an evidence-maturity label such as declaration,
fixture, model turn, repository read, real effect, independently reproduced, or
externally authenticated.

## Required gates

The following conditions fail closed:

- missing or ambiguous authority, identity, source, version, digest, license,
  provenance, classification, retention, evidence, rollback, or tenant scope;
- authority-token mismatch, collision, expansion, expiry, revocation, stale policy,
  or cross-mission/work substitution at use time;
- unresolved canonical ownership or a cross-boundary reference;
- unknown protected-body ownership, customer status, legal status, or deletion policy;
- stale projection cursor, source drift, human edit, partial publication, unexpected
  file, or non-reproducible rebuild;
- unknown or extra shared-record field; private/proprietary/secret/PII/license/taint,
  identity-linkage, topology, timing/count, poisoning, or reversibility risk;
- release author, Curator, Judge, or affected champion identities that are not
  procedurally separate; and
- any attempted activation, execution, authority grant, prompt concatenation, remote
  publication, or automatic promotion from shared learning.

## Alternatives and dispositions

| Alternative | Disposition | Reason |
| --- | --- | --- |
| Markdown, repository, or Obsidian is authority | Reject | Cannot meet immutable typed authority and replay invariants |
| Direct projector over current mixed stores | Reject | Would merge contradictions and sensitivity boundaries without one owner |
| Private-only projector first | Adopt | Smallest credible useful product and first release checkpoint |
| Staged private plus offline release plus local registry | Adapt | Selected full local program after blocking safety amendments |
| Automatic remote/public publication | Quarantine | External identity, retention, transport, revocation, and nondisclosure obligations remain open |
| Wholesale Phase 3 merge | Reject | Divergent prototype and incomplete current contracts |
| Watcher, Inbox, plugin, Sync, external embeddings, SaaS | Defer | Not required for the local outcome; evidence and authority are absent |

## Consequences

Positive consequences:

- Obsidian becomes a rich view without becoming a new source of truth.
- Repeated ideas, failed candidates, dissent, and workflow returns remain explainable.
- Private and shared learning use separate stores, identities, authorities, schemas,
  and courts.
- The design works offline and without an Obsidian installation.
- Existing main and prototype primitives can be adapted selectively with retained
  provenance.

Costs and constraints:

- The program adds 31 independently reviewable nodes and 18 integration rounds.
- A complete private graph still excludes material that policy forbids materializing.
- Retention/takedown and official Obsidian-source admission are blocking contract work,
  not documentation polish.
- Shared prior art may not reduce repeated ideation; duplicate escape, false merge,
  poisoning, and customer outcomes must be measured before an efficacy claim.
- Procedural agent separation does not replace authenticated legal, privacy, licensing,
  security, or independent-human authority where policy requires it.

## Implementation, evidence, and rollback

The executable contracts are in
`docs/execution/dags/knowledge-projection-v1/specs.py`. The generated plan is additive
and materializes under `.autopilot/state/`; `.autopilot/plan.json` remains byte-sealed
and unchanged.

Each node has one write scope, focused tests, objective acceptance evidence, consulted
roles, semantic locks, stopping condition, and rollback. The exact candidate must pass:

- deterministic generation and manifest verification;
- strict DAG lint and semantic round compilation;
- all focused node receipts and one full suite per integration round;
- point-in-time, corruption, concurrency, privacy/IP/license, poisoning, retention,
  takedown, projection-interruption, cross-tenant, recursion, migration, and rollback
  qualification; and
- a distinct release Judge after Curator reproduction.

Rollback disables the affected version or adapter and rebuilds derived views. It never
deletes canonical ancestry, dissent, losing ideas, adverse evidence, appeals, conflicts,
release denials, revocations, tombstones, or deletion receipts. Sensitive bodies may be
removed only through the authorized takedown contract; the retained receipt must not
contain the removed body.

## Current status

- Tournament and plan bundle: complete only when the final manifest verifier passes.
- New implementation nodes complete: **0 of 31 (0%)**.
- New implementation nodes in progress: **0**.
- New implementation nodes not started: **31**.
- Remote/public publication: **quarantined**.
- Watcher, bidirectional Inbox, plugin surfaces, external embeddings, and SaaS:
  **deferred**.

The existing current-main foundations remain credited inputs, not completed nodes in
this new acceptance program.
