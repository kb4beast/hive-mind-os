# Whole-OS service composition

The implementation composes repository bindings, a versioned outcome graph, the
durable scheduler, a host-owned package executor, independent qualification, lesson
routing, delivery, and benchmark adapters. The public composition root is
`hive_mind_os.whole_os_service.WholeOSService`.

The host supplies `ConfiguredMissionBindingsProvider` and `WholeOSHost`; Hive never
loads credential values from graph payloads. `WholeOSService` enqueues only
dependency-ready packages, uses scheduler leases, binds every payload to the tenant,
repository, descriptor, and graph digest, and reconciles completed jobs before
enqueuing successors. Unknown packages and cross-package results fail closed.

External applications receive source/artifact outputs only. They must not import
Hive, its scheduler, state path, or evidence store at runtime.

## Current evidence state

The software composition is implemented. Real host configuration, production
adapter attestations, external delivery grants, and fresh-process integration
receipts are not present in this repository and remain typed qualification inputs.
