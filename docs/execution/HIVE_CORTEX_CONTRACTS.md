# Hive Cortex Canonical Contracts

Status: version 1, accepted for the singleton release branch

The `brain_kernel` package is the authority-bearing contract boundary described
by ADR-055. Contracts are immutable frozen dataclasses, serialized through the
canonical JSON representation, and validated against the local Draft 2020-12
schema catalog before they are persisted or exchanged.

## Contract families

- Mission and work: `MissionCharter`, `WorkItem`, `ExecutionLease`.
- Authority and context: `ConstraintEnvelope`, `ContextManifest`.
- Role and effect protocol: `RoleResult`, `EffectIntent`, `EffectReceipt`.
- Evidence and learning: `MemoryRecord`, `EvaluationPlan`, `EvaluationResult`,
  `Candidate`, `HistoricalEvidenceReference`.
- Closeout: `TechnicalCloseoutReport`.

Every digest-bearing contract binds its canonical fields. Effect intents include
the actor, role, authority digest, target, parameters digest, idempotency key,
policy decision, and rollback description. Effect receipts bind the intent and
observed/postcondition digests; they never grant authority. Role output is a
proposal and cannot execute an effect or verify itself.

## Compatibility rules

1. Schema version `1` is exact: unknown fields, missing required fields, invalid
   enums, unsafe paths, malformed identifiers, and invalid digests are rejected.
2. Additive evolution requires a new schema version and an explicit migration
   fixture. Existing version-1 documents remain readable without reinterpretation.
3. A contract change must update the typed dataclass, schema, round-trip fixture,
   compatibility test, and rollback evidence together.
4. Canonical bytes and digests are field-order independent and reject non-finite
   values. No secret, credential, or transport setting belongs in a contract.
5. Independent verification and policy gates remain separate identities; a role
   result cannot approve itself or directly cause an effect.

The executable compatibility firewall is `tests/test_hive_cortex_contracts.py`,
supplementing the per-contract tests in `tests/test_brain_kernel_contracts.py`.
