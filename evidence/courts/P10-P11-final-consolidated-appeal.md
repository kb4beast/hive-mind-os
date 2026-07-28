# P10/P11 Final Consolidated Review Appeal

- Reviewed commit: `939287358679902a175d49abeea684a79b7d76ae`
- Review date: 2026-07-28
- Boundary: merged P01–P13 candidate, with focused reproduction of P10 and P11

## Independent adverse findings

The Curator (`/root/p08_p09_curator`) issued `BLOCK`.

- P10's fixture surface inferred evidence completeness from prompt substrings and emitted
  nine synthetic `fixture:*` references that resolved to no artifact or receipt.
- P11 accepted completion and failure after lease expiry when no competing worker had
  reclaimed the job.

The Judge (`/root/p08_p09_judge`) issued `adapt — BLOCK`.

- The Judge independently reproduced P11 completion at time 6 from a lease that expired
  at time 5 and identified the analogous failure mutation.
- P10's bounded scripted controls were otherwise supported, subject to the Curator's
  independently reproduced evidence-resolution counterexample.

The Orchestrator (`/root/p13_final3_orchestrator`) issued `BLOCK` on court closure.

- The merged tree and CI were healthy.
- `B-OPS-02` remained marked open even though P11 was marked done.
- ADR-013 and ADR-014 still reserved their dispositions for this review.

## Appeal scope

The appeal is intentionally limited to:

1. real P05 fixture-mission execution and digest-bound prompt, report, and receipt
   validation before P10 promotion;
2. atomic unexpired-lease predicates plus no-reclaim regressions for P11 completion and
   failure; and
3. additive ADR/blocker closure within the tested scripted/local single-machine boundary.

The original experiment, audits, commit, and reviewer dissent remain preserved. This
appeal does not close `B-OPS-03`, source or licensing obligations, authenticated identity,
external retention, hostile isolation, production readiness, release readiness, or any
superiority burden.
