# Whole-OS service composition

The implementation composes repository bindings, a versioned outcome graph, the
durable scheduler, a host-owned package executor, independent qualification, lesson
routing, delivery, and benchmark adapters. The public composition root is
`hive_mind_os.whole_os_service.WholeOSService`.

## Operator CLI

Use a closed JSON document matching `src/hive_mind_os/schemas/whole-os-service-config.schema.json`.
It embeds only the admitted binding descriptor and sealed graph; commands,
imports, callbacks, and credential values are rejected or unsupported.

```text
hive-mind whole-os inspect --config path/to/service.json --json
hive-mind whole-os status --config path/to/service.json --json
hive-mind whole-os run-once --config path/to/service.json --json
hive-mind whole-os resume --config path/to/service.json --json
```

`inspect` is read-only. `status` projects durable queue state. `run-once` and
`resume` execute one bounded step. The stock CLI has no host executor and
reports `BLOCKED_CAPABILITY`; a configured host must construct `WholeOSService`
with its own `WholeOSHost` and credential broker.

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
