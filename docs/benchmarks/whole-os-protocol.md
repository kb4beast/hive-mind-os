# Whole-OS measurement protocol (N02)

Status: **software contract only; external evidence blocked; no execution or
superiority claim**.

The checked-in `whole-os-match-protocol.json` is an OPEN inspection record. It
names every expected MB/MC/MH lane and every missing external obligation without
inventing recipe bytes, manifest digests, signatures, custody, or a lease. Changing
its status strings does not create authority. `load_match_protocol_for_inspection`
returns only inert metadata. `load_match_protocol` can validate a future complete
document, but even a valid `MatchProtocol` cannot schedule, apply, seal, aggregate,
or decide a match without a host-registry handle.

## Trust and admission boundary

`campaign_metrics` does not authenticate external authority. It contains no key,
token, verifier callback, admission constructor, default registry, or production
registry implementation. A separately configured host owns `AdmissionRegistry`.
Only that host can:

- authenticate evaluator, custodian, builders, affected champion and lease issuer;
- resolve a registry-instance-bound opaque admission handle;
- attest immutable recipes and disjoint task/family/block manifests;
- issue one opaque receipt per exact pair or bye;
- atomically consume receipts in an append-only replay ledger;
- append seals with compare-and-swap history; and
- record and resolve qualification aggregates.

Tests inject an in-memory fake registry defined only in the test module. Its handles
work only in that fake instance. It demonstrates the protocol handshake, not real
external verification or N30 readiness.

Every executable call resolves the handle again. The resolved admission identity is
the canonical digest of the complete protocol digest, complete `StageEvidence`, and
complete `LeaseRecord`. Stage evidence binds recipe, task, family and block manifest
digests; task/family/repetition/seed membership; all thirteen strata; manifest
signature reference; evaluator/custodian/builders/affected champion identities;
stage and opening times; and, for final, both exact finalist bindings. The lease
binds protocol, stage, budget, issuer, issue/expiry/revocation times and permitted
operations. The library rejects an untrusted issuer, wrong scope, future, expired,
revoked, or operation-ineligible lease on every use. Schedule/apply convert a valid
expiry or revocation observation into the explicit `lease_exhausted` terminal;
sealing and qualification fail closed.

## Frozen protocol and recipes

A future closed document must provide exactly MB0–MB3, MC0–MC1 and MH1–MH4 with
concrete provenance and the eight immutable behavior digests: source/binary,
prompt, model, command/profile, tool, context, check policy and learning policy.
Duplicate complete behavior is one entrant and therefore rejects as two labels.
Every recipe binds its track and operating regime. The canonical protocol digest
also binds seeds, retry rule, sample sizes, every public manifest digest/signature
reference, custody receipt, terminal rules and closure receipt. OPEN/DEFERRED
recipes never construct a closed protocol.

Builder-component and whole-campaign tracks remain separate. Original evaluation
uses only `development-screening`; hybrid evaluation uses only
`harder-hybrid-development`; final uses the actual admitted
`promotion_holdout` manifest digest. Finalists must be one whole-campaign original
and one hybrid with different recipes in the same operating regime.

## Attempt records and descriptive statistics

`AttemptMetric` binds family, task, variant, candidate/config/model/environment,
eligibility/result, active/queue/wall time, usage/cost bases and units, provider
availability, billed-cache distinctions, checks, defects, recovery, disclosure,
context retransmission, redundant checks, model calls and avoided work. Unknown
usage/cost is null with an unknown basis, never zero. Known cost requires a currency.
Non-finite, negative and boolean numeric values reject. Summaries retain every
eligibility/result cell, including eligible-but-not-attempted rows.

`paired_family_bootstrap` is deliberately descriptive. It averages repetitions
within family and computes the deterministic 10,000-resample, 95% interval, but its
`DescriptiveInterval` cannot enter `decide_match`.

Qualification uses `stage_paired_bootstrap`. It revalidates admission and requires
exact equality with the authenticated task/family/repetition manifest: 12 distinct
families × one declared repetition for original/hybrid, or 30 distinct families ×
three declared repetitions for final. Every row carries a distinct execution
receipt digest; the registry verifies it against durable consumed evidence and
returns an opaque `AggregateReceipt`. `decide_match` accepts only three co-bound
registry aggregate receipts for success difference, cost ratio and time ratio.

Success noninferiority requires each directional lower bound to be strictly greater
than -0.05 and both hard gates. A strictly positive/negative success interval wins
for left/right. After both candidates are noninferior, efficiency may decide when a
candidate's cost upper bound is below 1.0 and time upper bound at most 1.10, or its
time upper bound is below 1.0 and cost upper bound at most 1.10, with reciprocal
right-side tests. Otherwise the result is DRAW or INCONCLUSIVE. One or both safety
failures produce `QUARANTINE_LEFT`, `QUARANTINE_RIGHT`, or `QUARANTINE_BOTH`.

## Bracket, receipts and replay

Each round sorts eligible entrants by loss count and stable ID, rotates left by
round minus one, and selects the odd-field bye by fewest prior byes then ID. It
finds the maximum deterministic set of same-track, same-regime pairs that have met
inconclusively fewer than two times. Unmatched entrants receive no receipt and no
implicit win. If no pair exists, the explicit partial terminal is
`no_schedulable_pairs`; zero entrants have the same terminal and one has
`one_survivor`.

The registry issues exactly one opaque `IssuedReceipt` for every scheduled pair and
bye. Each canonical plan binds admission/protocol/stage, round/index/orientation,
track/regime, actual block ID/digest, task/family/repetition/seed,
evaluator/custodian, and issuance time. `apply` requires exact set equality: zero,
partial, duplicate, substituted or extra results reject. A bye requires `BYE`.
`QUARANTINE_BOTH` removes both entrants. Resolved losses increment only the loser;
the third loss eliminates. DRAW/INCONCLUSIVE increments stage-local meeting count.
The host registry atomically consumes exact opaque handles in its append-only ledger,
so changing public fields or restoring an earlier `BracketState` cannot bypass replay.

## Seals and final custody

Seals bind protocol and stage-evidence digests, sequence, variant/candidate/recipe,
evaluator/custodian, stage, actual block/task/family manifests, regime, epoch time
and signature reference. The registry exposes authenticated append-only history;
the module requires contiguous order and strictly increasing times, exact admitted
principals and manifests, correct stage/variant class, and an immutable recipe.

Final admission references the exact original and hybrid qualification seal digests.
Both prior seals must precede final-stage admission. The registry must then contain
exactly two final pair seals, unchanged and sealed after final admission but before
the recorded holdout-open time. Final scheduling rechecks this history and uses the
actual external holdout digest. A cross-track, cross-regime, late, changed,
unqualified or builder/custodian-substituted pair rejects.

## Honest stopping point and external obligations

The software supports deterministic fixture validation only. It does not execute or
download a comparator, reveal a holdout, spend a lease, or authorize promotion.
N30 still owes pinned source/archive bytes and execution rights for EX01/EX03/EX06/
EX07 and datasets; concrete recipe manifests and candidate bytes; externally
custodied disjoint task/family/block manifests; authenticated independent evaluator
and custodian receipts; actual provider/runtime availability; and an authenticated,
bounded, non-renewing N30 lease. Missing evidence remains DEFERRED and cannot be
replaced with fixture handles or well-shaped local JSON.
