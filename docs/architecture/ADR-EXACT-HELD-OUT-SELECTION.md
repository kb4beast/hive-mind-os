# ADR: Exact held-out primary selection

Status: proposed implementation; execution and independent verification pending.

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
