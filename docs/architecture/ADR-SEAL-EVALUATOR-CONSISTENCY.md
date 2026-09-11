# ADR: Seal evaluator consistency in evaluation receipts

Status: Proposed implementation; independent verification pending.

## Context and decision

An otherwise eligible evaluation can use a prediction sealed under a different
evaluator label. The existing receipt omits the seal label, losing attribution.
Require exact equality between the recorded seal evaluator and runtime evaluator.
Add mismatch to the existing quarantine reasons before numerical scoring; retain
both labels and supplied surfaces. An absent seal retains ordinary quarantine.
Quarantine leaves primary_effect, required_effect and noise_floor null.

The runtime owns this check and reuses its existing retention path. Public call
signatures, EvaluationRecord fields, measurement thresholds and guardrails stay
unchanged. No workspace, plan, service or dependency is introduced.

## Threat and compatibility

This prevents inconsistent evaluator attribution, not impersonation. Labels are
not authenticated principals. Candidate-to-measurement binding, evaluator version
attestation, authenticated reveal, replay resistance and complete promotion
binding remain unresolved. An intentional evaluator handoff now quarantines;
there is no demonstrated tracked handoff caller or authorized handoff interface.
Unknown external consumers remain a compatibility limitation. This decision
grants no promotion authority and adds no promotion behavior.

## Migration and retention

New documents use schema_version 2 and add holdout.evaluator_id, null if unsealed.
Both labels contribute to canonical receipt identities, including matching cases.
The configuration fingerprint remains unchanged; schema 2 is not implementation
attestation. Preserve schema-1 bytes, paths and digests without inferring missing
labels or claiming they satisfy the new check. Repeated revised inputs remain
deterministic. Persistence errors propagate; partial-write recovery is not added.

## Acceptance and rollback

SealEvaluatorBindingTests in tests/test_hive_cortex_evaluation.py covers mismatch,
precedence, attribution, unsealed input, immutable repetition, legacy coexistence
and persistence failure. Existing verdict and guardrail tests must also pass in
independent focused verification. No execution result is asserted by this ADR.
Supersede or revert only the isolated candidate; retain old and new receipts.
