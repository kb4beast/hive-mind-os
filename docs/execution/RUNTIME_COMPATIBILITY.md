# Runtime compatibility boundary

Status: `ADAPT` for MIGRATE-260. The legacy paths remain the authority until
independent parity evidence and a rollback rehearsal qualify a canonical route.

## Scope and ownership

The additive package `hive_mind_os.cortex.compatibility` registers typed adapters
for the four in-scope legacy surfaces:

| Legacy entry point | Adapter | Canonical destination | Current authority |
| --- | --- | --- | --- |
| `RepositoryMission` | `RepositoryMissionAdapter` | repository effect adapter plus Curator verifier | legacy |
| `MissionLoop` | `MissionLoopAdapter` | canonical role/action protocol | legacy |
| `AutonomousBrain` | `AutonomousBrainAdapter` | host/effect and outcome-learning adapters | legacy |
| scheduler `Worker` / `execute_mission_job` | `LegacyWorkerAdapter` | canonical leases and delivery workers | legacy |

Each adapter produces a typed `CompatibilityRequest` and a read-only
`CompatibilityObservation`. The observation retains separate behavior and evidence
fields plus canonical digests. The registry also retains an explicit typed retirement
blocker for every path; no old path is declared retired by this change.

## Parity and no-dual-write rule

`ParityProbe` compares two already-produced, effect-free or shadow observations. It
does not call both runtimes and it rejects observations marked as effectful outside
shadow mode. `RollbackRouter` invokes exactly one owner per operation. The legacy
route is selected at construction, and canonical routing is unavailable until a
matched behavior-and-evidence parity verdict is explicitly supplied.

This makes shadow/replay safe: canonical projections can be derived from sealed
events and receipts without a second authoritative write, while adverse evidence
remains visible as a parity difference.

## Rollback and retirement gate

The router always retains a `rollback_ref` and can return to the legacy owner before
or after qualification. Qualification is not retirement. Retirement requires the
entry point's blocker evidence, accepted parity, independent Curator verification,
and a successful rollback rehearsal to be recorded by a later migration node.

Rollback for this node is to revert the additive compatibility package, tests, and
this document; the pre-existing legacy modules, scheduler state, TLS/certificate
controls, provenance, and authority gates remain unchanged.

## Receipt test names

The focused executable receipt tests are:

- `compatibility-adapter-tests` — `test_compatibility_adapter_tests`
- `no-dual-write-tests` — `test_no_dual_write_tests`
- `rollback-routing-tests` — `test_rollback_routing_tests`
