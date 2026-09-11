# ADR: Exact held-out primary selection

Status: accepted for reversible delivery; merge and promotion prohibited.

## Context and decision

The evaluator previously selected the greatest held-out name after sorting.
Repeated baseline 0.5 and candidate outcomes 0.75 and 0.25 can therefore change
KEEP to DISCARD when only their names are exchanged, under default guardrails.
This is a source-derived example; this document is not a reproduction receipt.
Use an optional exact primary name in EvaluationContract. An undesignated
singleton remains eligible. Undesignated multiple held-out surfaces quarantine.
A supplied name must match exactly one held-out surface, even for singleton
input. Names in other kinds cannot satisfy selection. Missing held-out input
without designation retains missing-surface RETEST; empty input remains an error.
Selection failures join quarantine before completeness, guardrails, or scoring.
All existing configured guardrails and strict threshold comparisons remain.

## Architecture and migration

Selection belongs solely to the evaluation contract, runtime, and record.
The contract document includes exact-held-out-v1 and the optional name, including
null, in the fingerprint preimage. Retain canonical bytes plus newline at
contracts/<fingerprint hex>.json before the evaluation receipt. Existing bytes
must match exactly. Both writes flush and fsync; failures return no record.
Schema 2 keeps the absent-designation zero/singleton layout for every verdict.
Schema 3 covers all explicit designations and undesignated multiple surfaces.
Requested identity, resolved identity, and actual scoring are separate facts.
Constructor positions and singleton scoring remain compatible. Fingerprints,
evaluation IDs, record digests, dataclass shape, and file counts change.
Historical bytes are never rewritten. Interpret old receipts using original
provenance; schema alone does not identify policy. New policy resolution requires
the retained preimage and verification against the receipt fingerprint.

## Threats, validation, and rollback

Content binding does not authenticate pre-observation commitment or measurements.
Contract persistence adds availability cost and may leave orphan or partial files.
No transactional crash recovery, promotion admission, or superiority is claimed.
Run focused evaluation tests, baseline reproduction, and independent verification.
Rollback supersedes the isolated candidate and retains receipts and policy provenance.

## Delivery evidence and scope ruling

The independent appeals identity returned `adapt`: the bounded functional change is
eligible for a delivery pull request, but neither merge nor challenger promotion is
authorized. Authenticated premeasurement chronology remains a separate
LEARNING-040-002 obligation; it is not evidence for or against the narrower claim
that an explicit contract designation prevents held-out selection from changing
when surface names are exchanged.

The legacy name-swap reproduction source is bound as
`sha256:e91ebe0a5bc7e6f2bf966ac21dbda0e24cc30858b548bb58f78e3aa5307622f8`.
Its independently executed receipt is bound as
`sha256:4d7b5f1112278efcbc2a26f63032e777762f063654165e7333b04ebbe502ce22`;
the external delivery evidence retains the exact source bytes, raw output, host
receipt, and authenticated tournament-event digest. Isolated executable cases
cover duplicate designation, a name found only in another surface kind, and a
renamed/unmatched designation. Each asserts the selection-specific quarantine
reason, absence of scoring, and absence of unrelated evidence diagnostics.

Outstanding obligations remain explicit: contract chronology is not authenticated;
builder, verifier, judge, and promoter principals are not yet cryptographically
authenticated; replay resistance and promotion admission are not implemented; and
no superiority or promotion claim is made.
