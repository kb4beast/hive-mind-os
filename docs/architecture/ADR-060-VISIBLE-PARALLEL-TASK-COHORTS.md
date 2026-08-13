# ADR-060: Visible parallel task cohorts with explicit authority

## Status

Adapted implementation candidate on the singleton release branch. Independent Curator
and security review are required before promotion.

## Context

The orchestration contract emitted released tasks only when no active or recovery task
already existed. One recovery task could therefore suppress every other released node,
and eligible unreleased work had no visible place to investigate or prepare. The
closure-first scheduling preference had accidentally become task-creation exclusivity.
Operators saw one task even when several independent workstreams could safely proceed.

## Court record and dispositions

- Advocate: adopt complete cohort creation before the first wait so independent work is
  visible, durable, and managed by the host executor.
- Cross-Examiner: reject any design that treats task creation as claim authority or lets
  an unreleased task mutate repository or remote state.
- Expert: distinguish read-only preparation from the durable write-authorized lifecycle
  in task identity; retain identity across ordinary create, resume, repair, and receipt
  transitions.
- Judge: **adapt** complete visible cohorts with explicit authority modes, deterministic
  titles, fail-closed claims, and terminal polling of every created task.

## Decision

1. Build one visible cohort containing active/recovery tasks, every node in the current
   conflict-free dispatcher release, and read-only preparation tasks for other eligible
   nodes.
2. Create the entire cohort before the first wait. An existing task never suppresses a
   newly released or preparation task.
3. Put node ID, action, authority mode, and instruction digest in every durable title.
4. `PREPARATION_ONLY` may inspect, diagnose, and produce a handoff but cannot claim,
   write, commit, push, or publish completion. Release authority remains independently
   enforced by the dispatcher and claim command.
5. Treat closure-first as result-collection priority. Poll every created task to a
   terminal host result, answer recoverable questions in the same task, and do not end
   the parent merely because one task finished.
6. Keep one write-authorized instruction identity across create, resume, repair, and
   receipt work. Use a distinct authority class for preparation so it cannot be silently
   reused as an execution grant.

## Threats, migration, and rollback

Preparation tasks increase visible task count and could waste attention; deterministic
eligibility, task identity, and bounded read-only scope limit that cost. A malicious or
confused preparation task could attempt mutation, so prompts, policy validation, and the
existing claim/release barriers all deny authority independently. Existing active task
bindings retain their write-authorized identity. Rollback removes preparation effects
and restores released-only task creation while retaining append-only binding evidence.

## Acceptance evidence

Tests must reproduce a mixed state containing active recovery, a released node, and an
eligible unreleased node; assert that all are emitted together; assert explicit and
unambiguous authority; prove preparation cannot be confused with write authorization;
prove create-to-resume binding identity remains stable; and verify the checked-in policy
cannot disable cohort creation, polling, or closure-priority semantics.
