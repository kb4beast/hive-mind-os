# Canonical Runtime Migration Map

This map turns ADR-055 into a reversible sequence.  The singleton release
branch is the only execution target; `main` is reserved for final integration.

| Legacy surface | Canonical destination | Compatibility boundary | Exit evidence |
| --- | --- | --- | --- |
| `HiveKernel` lifecycle | `brain_kernel` mission events and role protocols | CLI facade translates requests and projects legacy reports | replay and report parity |
| `RepositoryMission` | repository effect adapter plus Curator verifier | adapter owns bounded workspace/process/Git effects | candidate/effect/receipt parity |
| `MissionLoop` | canonical role/action protocol | typed Builder action translator | action and retry parity |
| `AutonomousBrain` | host/effect and outcome-learning adapters | run charter and feedback projection | point-in-time learning parity |
| scheduler and workers | canonical leases and delivery workers | queue adapter | lease recovery and idempotency tests |
| legacy compatibility commands | derived projections only | no direct authority writes | no-dual-write audit |

## Ordered gates

1. **Contracts:** define event, authority, context, effect, verification,
   learning, and delivery schemas.
2. **Adapters:** wrap one legacy surface at a time; adapters may request only
   the canonical effect gateway.
3. **Replay:** feed identical sealed fixtures to old and new projections and
   compare normalized outcomes, evidence, and failure states.
4. **Shadow:** derive canonical projections without changing external effects;
   compare held-out runs and retain dissent.
5. **Cutover:** route one mission class to canonical authority after Curator
   approval and rollback rehearsal.
6. **Retirement:** remove legacy ownership only after all dependents migrate,
   receipts are retained, and a rollback reference is sealed.

## Invariants

- Exactly one authority-bearing write exists for each mission event.
- Compatibility output is derived, never independently committed as mission
  truth.
- Effect requests carry scope, lease, idempotency key, target, actor, and
  rollback metadata.
- Replay is deterministic for a sealed event stream.
- Shadow mode has no external effect authority.
- Any parity, provenance, security, or rollback failure stops the gate and
  preserves the last accepted boundary.

## Current disposition

The repository evidence supports the architecture decision and identifies the
existing split-brain surfaces.  This map is a planning artifact, not proof that
the migration is complete.  Each later implementation node must attach exact
candidate/tree identities, tests, independent verification, and a reversible
completion receipt.
