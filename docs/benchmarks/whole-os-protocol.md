# Whole-OS measurement protocol (N02)

Status: frozen measurement design; **no execution and no superiority claim**. This
protocol is an inert contract for N30. Comparator source bytes, licenses, archive
receipts, runtime availability and provider authority remain open obligations.

`whole-os-match-protocol.json` is the closed scheduling artifact. It requires the
same immutable source/binary, prompt, model, command/profile, tool, context,
check-policy and learning-policy digest for every recipe. Different labels with the
same complete digest are one entrant. Candidate bytes do not exist at N02: an
independent evaluator must seal MB/MC originals immediately before their stage,
each hybrid before its stage, and exactly two distinct unchanged variants before the
untouched `promotion_holdout` final.

## Records and denominators

Each `AttemptMetric` binds subject family, task, variant and four relevant digests;
eligibility/result; active, queue and wall time; usage and cost with their bases;
checks, defects, recovery and disclosure events. Unknown quantities are `null` with
an `unknown` basis, never zero. Failed, ineligible, unknown and inconclusive rows
remain in the evidence set. Report the eligible attempted success denominator next
to total rows and every excluded capability reason; an ineligible lane is not a
failed matched-builder comparison.

The strata are small bug, feature, absent tests, multi-file, cross-language,
self-runtime, ambiguous backlog, provider failure, restart, tenant isolation, draft
export, endpoint learning and Roblox runtime. Component builders use identical
admitted adapters/limits. Whole-system lanes record unsupported capabilities and
infrastructure cost explicitly.

## Frozen statistics and decision gates

Development screening is 12 distinct task families per eligible variant and one
declared seed. Final qualification is at least 30 distinct repository/task-family
pairs with three predeclared seeded repetitions where stochasticity applies.
Repetitions are averaged within a family before paired bootstrap, so three runs of
one repository are never three independent repositories.

Use deterministic paired-family bootstrap: 10,000 resamples, fixed published seed,
and 95% percentile intervals for paired success difference, cost ratio/difference,
and elapsed-time ratio/difference. Success noninferiority requires lower success
interval bound strictly greater than -0.05 and every safety/quality hard gate. A
success win needs a positive success interval with no required regression. After
both satisfy noninferiority, efficiency can decide only where cost-ratio upper bound
is below 1.0 and time-ratio upper bound is at most 1.10 (symmetrically for the
opponent). Otherwise record DRAW/INCONCLUSIVE. Wide intervals create a new versioned
experiment; they never authorize sampling until significance.

Track retransmitted context, redundant checks, model calls, avoided work and
provider billed-cache distinctions. Host estimates remain estimates.

## Bracket and custody

Tracks are separate: MB0–MB3 builder-component, MC0–MC1 whole-campaign, MH1–MH4
measured hybrids. Analytical A/H labels are never measurement IDs. N30 owns a
benchmark-only adapter; it cannot grant credentials, relax a gate or change a
recipe. A round sorts by losses then stable ID, rotates left by round minus one,
uses a bye only for an odd field (fewest prior byes, then ID), and skips a pair after
two inconclusive meetings. A bye is neutral; the third resolved loss eliminates;
safety quarantine is separate. Stop at one survivor, no schedulable pairs, 24
rounds, or a bounded lease ending. No automatic lease renewal or task expansion.

One frozen variant/task/seed execution is reused for permitted bookkeeping; entering
another matchup never triggers another model run. Hybrids use disjoint harder
development data. The selected original/hybrid pair must share an operating regime,
be distinct, and receive no recipe change after final data opens. If no such pair
exists, report no comparative championship.

Sources informing the design are EX01, EX03, EX06 and EX07 as preserved in the
tournament source record. Their raw bodies/licenses have not been archived here;
this protocol neither reuses nor executes their code. See also the N00 open
obligations `EO-EXT-SOURCE-ARCHIVES` and `EO-COMPARATOR-RIGHTS`.
