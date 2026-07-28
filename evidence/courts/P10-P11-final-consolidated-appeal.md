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

The first repair audit, `evidence/audits/P10-P11-repair-post.json`, passed 353 tests with
no failures at `96268c76d4eb9dad09ca12cdd0bb9c241c242709`. Its ignored-file inventory
then exposed that a broad repository `artifacts/` rule excluded the enforcement
receipts' nested artifact bytes. The audit is retained as adverse packaging evidence.
The appeal adds a narrow exception only for the committed experiment evidence tree,
tracks those digest-bound bytes, and requires a fresh audit of the corrected candidate.

## Post-merge byte-integrity appeal

The second consolidated review of merged commit
`6fb396a81f88456ce0566ec2d70b4476ae0ba721` supported the P11 repair and
`B-OPS-02`'s local resolution but blocked P10 again. The Curator, Judge, and Orchestrator
all reproduced that Git text normalization changed committed evidence bytes after the
runtime validator had approved them. The exact Git-object discrepancies are retained in
`evidence/experiments/adverse-artifact-integrity.json`; the old experiment and both prior
repair audits remain adverse evidence.

The byte-integrity appeal:

1. applies `-text -diff` to `evidence/experiments/_artifacts/**`;
2. validates every committed experiment reference and each nested enforcement artifact
   against `git show HEAD:<path>`;
3. requires every known mismatch or unresolvable legacy label to match the explicit
   adverse manifest exactly; and
4. adds fresh experiment `EXP-98c64c11-bd9c-47a5-a376-d39fad641332`, whose direct and
   nested references must have zero Git-object mismatches.

An initial regeneration attempt (`EXP-f0346c51-f094-4617-91fc-d41b80ce4ec3`) failed
closed before a verdict when its Windows path budget was exhausted. Its partial artifacts
and failure record are retained. The successful appeal uses a shorter evidence layout;
it does not weaken receipt validation or any maturity boundary.
