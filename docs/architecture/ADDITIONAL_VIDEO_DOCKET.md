# Additional Autonomous-Engineering Video Docket

## Status

This document records the four additional user-supplied videos added to the founding source docket on 2026-07-27. It is subordinate to the immutable source records and courtroom decisions in:

- `src/hive_mind_os/additional_video_docket.py`
- `src/hive_mind_os/source_docket.py`
- `src/hive_mind_os/vision.py`

A partial transcript, search summary, title page, or demonstration is evidence for investigation, not proof that every described feature works as claimed. No video-derived idea may be promoted solely because it appears persuasive in a demonstration.

## Chain of custody

| Source | Docket ID | Intake status | Court treatment |
|---|---|---:|---|
| `https://www.youtube.com/watch?v=eaNA2oOXoUg` | `SRC-016` | Partial | Adapt the defensible long-running coding and observability patterns; keep full ingestion blocking |
| `https://www.youtube.com/watch?v=IbFaY3xFpZM` | `SRC-017` | Pending ingestion | Preserve only; defer all content claims until transcript or artifacts are verified |
| `https://www.youtube.com/watch?v=eA9Zf2-qYYM` | `SRC-018` | Partial | Adapt goal-to-result loops, context, memory, skills, schedules, and governed tool integration |
| `https://www.youtube.com/watch?v=kIWMLL0S8X8` | `SRC-019` | Partial | Adapt separation of persistent orchestration from coding execution and secure channel-driven control |

All four URLs are included in the fingerprinted `HardenedVisionContract`. Removing or changing one changes the constitutional fingerprint.

## Case group A — long-running autonomous coding

### Advocate

Long-running coding systems are stronger when they turn a specification into a visible task graph, assign bounded work to parallel subagents, validate intermediate outputs, and continue until objective completion criteria are met. A live board can reduce coordination friction by exposing plans, active work, validation, stalls, costs, and security findings.

### Cross-examination

A demonstration can conceal manual prompting, cherry-picked runs, uncontrolled context growth, correlated subagent errors, weak security boundaries, or a false completion signal. Parallelism can multiply duplicated work and cost. A status board can merely repeat agent assertions rather than project verified runtime state.

### Verdict

**Adapt**, through `CLM-058` and `CLM-059`.

### Required controls

- Specifications become typed objectives, acceptance criteria, risks, dependencies, budgets, and stop conditions.
- Subagents receive finite leases, scoped tools, deduplication keys, and shared artifact contracts.
- Builder output is not accepted as validation evidence.
- Curator verification runs in a separate identity and clean workspace.
- Mission-control state is derived from ledger events and receipts, not conversational claims.
- Security findings become traceable work items without granting the discovering agent write or merge authority.
- Stalled, disputed, unknown, and quarantined states remain explicit.

## Case group B — goal-to-result agents, context, memory, skills, and tools

### Advocate

Useful agents operate as iterative goal-to-result systems rather than one-turn responders. Durable project instructions, cross-session memory, reusable skills, schedules, and external tools can compound capability and reduce repeated prompting.

### Cross-examination

Persistent context can become stale or poisoned. Memory can silently change behavior. Generated skills can preserve mistakes. Schedules can repeat unsafe actions. Broad tool access can bypass the intended authority boundary. An observe-think-act loop can also continue indefinitely without objective stopping rules.

### Verdict

**Adapt**, through `CLM-061` through `CLM-064`.

### Required controls

- Every loop has explicit success, retry, escalation, budget, quarantine, and stop conditions.
- Instructions, context, and memory are versioned, scoped, provenance-bearing, correction-aware, freshness-bound, and inspectable.
- The constitution and policy engine outrank learned or user/project memory.
- Skills are governed executable SOPs with tests, versioning, ownership, rollback, and champion/challenger promotion.
- Schedules are durable triggers, not authority grants.
- MCP-style adapters inherit caller identity, authorization, budgets, idempotency, provenance, and rollback obligations.
- Connectors cannot expose raw secrets or expand permissions.

## Case group C — persistent orchestration plus replaceable coding engines

### Advocate

A durable control hub can manage goals, schedules, channels, memory, and recovery while dispatching repository work to replaceable coding engines, models, and sandboxes. This separates long-lived coordination from short-lived execution and allows model or tool substitution.

### Cross-examination

A remote-control or messaging layer can become an ambient superuser. A coding engine may receive broader credentials than the initiating channel. Persistent orchestrators can accumulate stale state, repeat side effects, or conceal failures behind friendly status messages.

### Verdict

**Adapt**, through `CLM-065` and `CLM-066`.

### Required controls

- Control-plane state and execution-plane state use versioned contracts.
- Every dispatched action has a typed objective, scoped identity, finite budget, idempotency key, checkpoint, and evidence receipt.
- Messaging channels may request or inspect work but cannot directly invoke privileged side effects.
- Coding engines remain replaceable and execute only in sandbox tiers.
- Secrets are brokered through handles and policy, never copied into channel or model context.
- Recovery resumes from the last verified checkpoint and does not replay completed side effects.

## Unresolved source — `IbFaY3xFpZM`

The source is intentionally preserved as `SRC-017`, but its content is not asserted. `CLM-060` is a **defer** verdict with a blocking obligation:

1. capture a complete transcript or equivalent primary artifacts;
2. record retrieval time and content digest;
3. extract atomic, time-coded claims;
4. preserve supporting and opposing evidence;
5. run advocate, cross-examiner, and independent expert review;
6. map any adopted idea to architecture, tests, metrics, rollback, and ownership.

Until those steps are complete, the source may not be used to justify implementation or superiority claims.

## Acceptance obligations

The source-docket tests prove:

- all four sources remain inventoried;
- all nine claims have courtroom decisions;
- adopted or adapted claims map to architecture and acceptance tests;
- the unidentified video remains deferred rather than hallucinated;
- partial and pending video ingestion remains release-blocking;
- the immutable vision contract contains every supplied URL.

These tests prove capture and governance. They do not prove the video systems' marketing claims or Hive Mind OS implementation completeness.
