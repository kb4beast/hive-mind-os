# ADR-045: Verifiable Hive Kernel Canonical Contracts

## Status

Proposed. This record adds only immutable in-process types, schemas, and pure
validation. It grants no effect, provider, Git, network, secret, persistence, or
policy authority. Independent courtroom disposition remains required before any
promotion claim.

## Context

Phase 1 of the preserved Verifiable Hive Kernel handoff requires one strict contract
surface that later event, authority, memory, effect, and evaluation phases can share.
Existing repository contracts remain authoritative for existing behavior. The kernel
surface is additive and must remain independent of repository-cortex implementation.

## Decision

Add frozen dataclass contracts and strict JSON schemas under `brain_kernel` for the
mission charter, work item, constraint envelope, context manifest, memory record,
effect intent/receipt, evaluation plan, candidate, and future event spine. Canonical
JSON is UTF-8, sorted-key, compact, and rejects NaN. Every schema fails closed at its
root; an extension field is not silently accepted.

The authority comparison helper is pure: it only determines whether a child envelope
is no broader than a parent. It neither grants authority nor executes an effect.
Portable paths normalize Windows and POSIX separators to relative POSIX spelling and
reject absolute and traversal paths.

## Consequences and rollback

No state is persisted and no legacy command changes. Later phases must bind these
types to append-only events before they can mediate effects. Rollback removes the
additive contracts, schemas, tests, and this record; it has no data migration.

## Evidence obligations

The fixture inventory and executable conformance suite cover every new schema. The
Advocate, Cross-Examiner, Expert Witness, Curator, and independent Judge obligations
remain open; this ADR does not represent an adopted courtroom disposition.
