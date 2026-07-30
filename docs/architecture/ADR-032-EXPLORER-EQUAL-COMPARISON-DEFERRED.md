# ADR-032: Explorer equal-evidence comparison is deferred

- Status: accepted `defer` by P4E-001; roadmap item 6 remains incomplete
- Date: 2026-07-30
- Base: `11e4a7b16b00e11caf59c231b5b718f14ed65195`
- Extends: ADR-028, ADR-029, ADR-030, and ADR-031

## Decision

Do not execute or claim the Phase 4 item-6 comparison between Explorer v2 and
Generation Zero from the current repository state. Do not add another readiness
compiler: Phase 4C already fails closed with `forced-not-run` and `not-run`.

Explorer v2 has no runtime renderer or provider binding. Its definition is inert,
authority-free, and has no effective capabilities or tools. The Phase 4C suite is
development-visible, explicitly not a holdout or comparison, contains no executable
case bodies or oracles, rejects candidate observations, and accepts only caller-
supplied Generation Zero observation receipts. The Phase 4A injected engine, P10
prompt experiment runner, and P13 repository-delivery benchmark execute different
subjects and cannot be relabeled as this comparison.

## Reopening gate

A later appeal must first provide:

1. separately judged test-only runtime adapters for both exact subject definitions;
2. identical sealed evidence packets, repository/memory cutoffs, and tool/network
   policy;
3. evaluator-custodied executable holdouts and access receipts;
4. identical enforced model/provider/version/parameter/retry, token, cost, time,
   tool, network, and environment envelopes;
5. counterbalanced paired repeated trials with raw failures and losing cases;
6. provider-usage reconciliation, explicit unknown-accounting failure, and complete
   request/response and environment receipts;
7. a preregistered primary estimand, minimum meaningful effect, safety floors,
   confidence/alpha and precision or power target, multiplicity and sequential-stop
   rules, and intention-to-treat handling of missing or failed trials;
8. paired analysis with task/repository as the independent unit—repeated executions
   of one task are not independent samples;
9. authenticated evaluator custody, blinded lane labels until scoring seals,
   deterministic scoring, safety disqualifiers, effect sizes, and uncertainty; and
10. encrypted or redacted content-addressed raw request/response artifacts, access
    policy, provider request IDs, resolved model versions, timestamps, and complete
    retry/rate-limit/timeout receipts;
11. fresh isolated workspaces and conversations for every trial, with identical
    secrets/tool/network policy and no cross-lane cache or state leakage;
12. immutable run/pair/trial/attempt identities, idempotency keys, and crash-safe
    checkpoints that adopt verified completed effects without duplicate calls;
13. quarantine of incomplete pairs with partial artifacts retained and excluded only
    according to the preregistered intention-to-treat rule; and
14. a fresh independent court.

The preregistered treatment difference must be the exact agent composition. Any
evidence, cutoff, subject, provider, tool, environment, or budget mismatch invalidates
the pair. Identical enforced ceilings are required; differing actual consumption
within those ceilings is an outcome to retain, not a reason to discard the pair.
Overspend, unknown accounting, or envelope mismatch invalidates. Missing and failed
trials remain in the preregistered analysis.

## Scope and rollback

This ADR changes no product code, schema, runtime, API, CLI, provider, benchmark,
projector, view, resource, champion, or activation state. A later appeal may
supersede or close the blocker only with the required receipts and a new verdict.
This ADR, its court evidence, and the original `defer` remain append-only history;
rollback cannot delete them or convert the blocked comparison into a valid result.

## Not admitted

Roadmap item 6 is not complete. No Explorer v2 behavior, comparison, effectiveness,
customer value, learning, promotion, activation, or superiority claim is admitted.
Even a later valid result is scoped only to its pinned subjects, sampled
task/repository population, evidence, provider/model/configuration, resource policy,
environment, and time. A head-to-head test estimates the total composition effect;
component causality requires separately preregistered ablations.

## Judgment

Fresh Judge `/root/phase4e_judge` issued `defer` at exact evidence head
`c4cad6fa8de52475c01fd8a86fc5ca680ebe05e5`. The bounded readiness
adjudication is complete; the comparison is not. `B-OPS-09` remains open. Phase 5
may proceed only without relying on any comparison, behavior, value, learning,
promotion, or activation claim.
