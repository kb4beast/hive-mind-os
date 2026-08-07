# Verifiable Hive Kernel Phase 1 Fixture Inventory

This inventory is generated from the contract-conformance fixture set in
`tests/test_brain_kernel_contracts.py`. Each entry is structurally validated by the
existing schema engine during that test; no receipt or historical evidence artifact is
changed.

| Schema | Fixture source |
| --- | --- |
| `brain-kernel-charter` | `MissionCharter` |
| `brain-kernel-work-item` | `WorkItem` |
| `brain-kernel-authority` | `ConstraintEnvelope` |
| `brain-kernel-context-manifest` | `ContextManifest` |
| `brain-kernel-effect-intent` | `EffectIntent` |
| `brain-kernel-effect-receipt` | `EffectReceipt` |
| `brain-kernel-memory-record` | `MemoryRecord` |
| `brain-kernel-evaluation` | `EvaluationPlan` |
| `brain-kernel-candidate` | `Candidate` |
| `brain-kernel-event` | explicit canonical event fixture |

The inventory is intentionally limited to Phase 1 schemas. `ExecutionLease`,
`RoleResult`, and `EvaluationResult` are frozen canonical contracts from the handoff
but are not assigned an independent Phase 1 schema filename; their event bindings are
reserved for the later event-store phase.
