# ADR-037: Integrator governance boundary

- Status: adapted bounded record
- Phase: 5E

The package-private Integrator intake remains inert and authority-free. Integration scope,
compatibility planning, debt preservation, and Steward handoff are structural records, not executed
compatibility or release approval. Any later full Integrator outputs must remain separately
versioned, request/digest bound, replaceable across adapters, and fail closed on unknown contract,
license, migration, rollback, or external-authority evidence.

Migration is additive: introduce new output schemas beside the intake, reproduce old envelopes, and
activate nothing. Rollback removes the additive schemas and records while preserving historical
dissent and debt. Authenticated independence, execution, release, and production remain prohibited.
