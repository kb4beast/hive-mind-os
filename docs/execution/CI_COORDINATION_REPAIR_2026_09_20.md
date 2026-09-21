# CI coordination repair — 2026-09-20

## Scope and source

The owner requested coordinated completion of the remaining production tasks,
with Codex as delegator and Claude assigned bounded work. This receipt covers
only two concurrency tests. It does not close a production or live-pilot gate.

Source: Constitutional CI run `35016845048`, PR #191 at
`7de0e21ac498ff369eb41d3316cc9df58a0d2830`. Windows Python 3.14 reported
`test_cross_handle_create_alias_waits_for_durable_owner` failing at the initial
`owner_in_prepare` wait, and
`test_cohort_heartbeats_short_leases_and_retries_failures` returning `blocked`.
The tests are the same on the inspected main baseline
`20a7ea2f57dc1671731165915f63e4886dbf3125`.

## Claims and dispositions

| Claim | Advocate and counterargument | Disposition and evidence |
| --- | --- | --- |
| The create-alias test must coordinate an overlapping owner and alias without treating a three-second CI scheduling delay as a functional failure. | Claude Sonnet 5 diagnosis proposed larger test-only budgets. Root obtained the exact traceback, correcting the initial hypothesis that the alias wait failed. The Curator checked that larger budgets do not alter production timeouts or the single-preparation assertions. | Adopt: finite orchestration bounds, surfaced worker exceptions and unconditional owner release preserve the intended test. |
| Heartbeat liveness can be tested with controlled scheduler time and real durable renewals. | Root proposed the existing ManualClock with renewal acknowledgements. Claude implemented the test. The cross-examiner checked that historic renewals cannot satisfy a later clock target. A disabled-heartbeat negative control must still fail. | Adopt: each slow stage spans 60 ms of controlled time against a 30 ms lease and waits for actual persisted renewal after each advance. |
| This repair proves production readiness or a measured production latency bound. | No such claim is supported by a test-harness change. | Defer: all production qualification and live-pilot obligations remain open. |

## Separate participants

- Orchestration/design and execution receipts: Codex `/root`.
- Diagnostic witness: Claude Sonnet 5, medium effort, session
  `d9e507f8-2b9d-4357-bb97-b8bd12642391`.
- Builder: distinct Claude Sonnet 5, medium effort, session
  `c62eddd9-0fa3-42fb-8d1e-0d96a44746fc`.
- Curator/cross-examiner: `/root/readiness_cross_examiner`; no blocking issue.
- Separate Judge: `/root/readiness_judge`; `adopt`, conditional on the mandatory
  full CI gate for the final integrated candidate. The Judge independently ran
  both tests and reproduced the heartbeat-disabled failure.

These are procedural agent identities on a shared operator host. They are not
authenticated independent human review or independently administered custody.

## Validation and retained dissent

Root ran the host-runtime, Whole-OS integration and scheduler suites: 76 tests
passed. Ten repetitions of each repaired test passed (20 executions). Removing
the periodic heartbeat loop produced one expected assertion failure, zero errors,
and `no durable heartbeat during host`. The Judge separately reproduced 2/2
positive tests and the same negative control. `git diff --check` passed.

Raw logs, prompts, model-reported usage and the negative-control script are
retained at `local-custody:production-closeout-20260920`. The mandatory full
repository gate and remote CI remain pending at this receipt's creation; focused
checks do not substitute for them. Later receipts must bind their actual candidate.

The original diagnostic hypothesis about the failing alias wait was incorrect;
the retained traceback identified the earlier owner-start wait. No production
runtime defect or population flake rate is established by this evidence.

## Acceptance, compatibility and rollback

Production runtime, scheduler fencing, lease expiry checks, single-effect
assertions, and existing expired-lease rejection tests are unchanged. Acceptance
requires positive tests, the detecting negative control, and the full integrated
CI gate. Revert this repair commit to restore the prior test harness; retain this
receipt and all failed observations. No deployment, host grant, or live scheduler
configuration changes are part of this repair.
