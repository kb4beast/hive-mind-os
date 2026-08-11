# ADR-055: Portable intent-driven Autopilot orchestration

## Status

Adapted implementation candidate. Local Builder tests pass; independent Curator and
promotion judgment remain required before this change can be merged into a protected
branch.

## Context

The installed Autopilot reconstructs repository truth, computes dependency-ready work,
publishes conflict-free releases, claims nodes, and validates durable receipts. Its
operator workflow still depends on a long prompt and asks a human to open and coordinate
worker chats. A recent L2 run demonstrated the practical failure: nested review agents
ran concurrently, but primary work was not represented by durable user-visible tasks;
review work consumed capacity; the parent returned with children active; and no closure
invariant forced one node through receipt and PR before widening the investigation graph.

The user supplied the live GenericPrompt as source evidence. It is pinned to repository
commit `760d5e2468484924cbdd077a78584f570a67bd2c`, Git blob
`0fce4315bdaaaf0e1cf4ed5b57dfd15efacd4717`, 30,114 bytes, and SHA-256
`f810b17311cebae09413abcfbb1c2155a4934d8ebefa483aadb512e36eed2c5b`.
The source repository declares no license. Its wording and code are therefore not copied;
only independently expressed abstract patterns are considered. The older specialized
GenericPrompt already archived in this repository is a distinct source and is not treated
as a revision or derivative without custody evidence.

Official OpenAI model guidance independently supports explicit tool routing, concurrency,
retry, stopping limits, autonomy boundaries, and state-aware intent interpretation. It
does not establish Hive Mind's repository policy and is used only as expert testimony for
the host-adapter design.

## Court record

- Clerk/Explorer: `source-lineage-019ff107-ea0d-7d52-8a5c-ad22df21c3fb`
- Advocate/Architect: `controller-extension-019ff107-e756-70e2-a000-feb6726d0f52`
- Cross-Examiner/Test Expert: `orchestration-tests-019ff107-e8dd-7252-8043-855698b7160e`
- Builder: the current implementation branch
- Judge: deferred to an independent Curator; the Builder does not approve itself

The candidate dispositions are:

1. **Adopt** repository-resident machine-readable DAG/node contracts, evidence-derived
   state, conflict-aware waves, atomic claims, receipts, and first-class recovery.
2. **Adapt** one permanent dispatcher into a stable command and versioned policy rather
   than a frozen long prompt.
3. **Adapt** broad parallelism into deterministic priority-ordered maximal safe waves
   with `parallel_safe`, locks, capacity, and closure pressure. This does not claim a
   globally maximum-cardinality wave.
4. **Adopt** durable primary tasks with host identity bindings; nested agents are bounded
   sidecars and cannot substitute for primary node delivery.
5. **Adopt** state-aware intent classification for build/start/continue/check/finish,
   while negation, advice, quoted text, and protected effects fail closed.
6. **Reject** unlimited review expansion, task completion as repository completion,
   protected-branch authority inferred from terse language, and human escalation for a
   repairable software/controller defect.
7. **Quarantine** source copying or redistribution until the GenericPrompt license and
   authorship rights are resolved.

## Decision

Add an outer orchestration layer without moving repository truth into a model or chat UI.

1. `.autopilot/orchestration-policy.json` defines host-neutral durable-task transport,
   Codex adapter names, startup order, closure-first scheduling, polling, recovery, and
   quiescence.
2. `autopilot orchestrate --request TEXT [--apply]` classifies ordinary user language and
   emits a digest-bound orchestration contract. `--apply` may publish only the existing
   safe dispatcher release; it grants no merge, deployment, secret, or protected-ref
   authority.
3. Codex primary nodes map to `create_thread`, `wait_threads`, and
   `send_message_to_thread`. Each launch has a deterministic instruction/idempotency ID in
   its title so a restarted parent can find and resume it. Append-only
   `PREPARED -> CREATED -> BOUND -> TERMINAL_OBSERVED -> RELEASED` host records make the recovery boundary
   inspectable. Nested multi-agent workers are
   allowed only for bounded research, independent review, or non-blocking validation.
4. Existing active, receipt-pending, PR, CI-failed, or repair-required work is emitted
   before new ready nodes. At least one closure target must finish before optional audits
   widen the graph. The parent may not issue a final response while required primary tasks
   remain active.
5. Automatic dispatch now enforces `parallel_safe`; a serial node cannot share a release,
   even when its locks are disjoint. Wave order is deterministic by critical-path value,
   downstream unlock value, then node ID.
6. `CHECK` uses a non-mutating observation path. Explicit negation or advice language
   cannot publish a release.
7. The installed `hive-mind autopilot` CLI can initialize another Git repository with a
   portable, source-pinned DAG-build request, emit the one reusable prompt, and inspect an
   installed control plane. The generated target defaults to an unprotected release
   branch and fails closed instead of replacing an existing request.

The host adapter performs external task operations and returns task/thread identifiers.
A task's final message never marks a node complete; repository ancestry and validated
durable receipts remain authoritative.

## Threats and counterclaims

- Natural-language intent can over-authorize work. Explicit negation and read-only/advice
  requests override action terms; protected effects always require separate authority.
- Durable task creation can crash between external creation and local binding. A
  `PREPARED` record is written first; launch IDs are deterministic and embedded in
  titles/prompts so hosts search and bind an existing task before retrying creation.
- More concurrency can increase conflict and review churn. Serial nodes are isolated,
  locks remain mandatory, and closure obligations block wave widening.
- `status` historically reaped stale claims. A separate observation method prevents a
  check request from changing state; recovery ticks may reap through existing bounded
  mechanisms.
- A settled graph may contain quarantine or escalation rather than success. The contract
  reports quiescence separately from task activity and does not convert adverse terminal
  evidence into success.
- Host adapters may not expose durable tasks. Such a host must return an explicit
  capability blocker; it may not silently replace primary tasks with nested agents.

## Migration and rollback

Existing dispatcher, claim, receipt, and plan formats remain valid. Hosts may continue to
use the detailed dispatcher protocol while adopting the orchestration contract. Other
repositories begin with `hive-mind autopilot init`, review the generated request, and then
build their repository-specific DAG.

Rollback removes the additive portable CLI/module/policy and the `orchestrate`,
`infer-intent`, and `simple-prompt` commands, then restores the former wave selector. It
does not delete task history, claims, receipts, source records, or adverse evidence.

## Acceptance evidence

Focused tests must prove intent/negation handling, non-mutating checks, closure-first
resume, durable-task output, task idempotency identity, serial-node isolation,
conflict-free priority, portable initialization, source pinning, overwrite refusal, and
repository-neutral output. The complete repository CI gate remains required before a
passing delivery claim.
