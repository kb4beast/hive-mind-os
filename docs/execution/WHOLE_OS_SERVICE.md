# Whole-OS service composition

The implementation composes repository bindings, a versioned outcome graph, the
durable scheduler, independent qualification, lesson routing, delivery, and
benchmark adapters. `hive_mind_os.whole_os_service.WholeOSService` is the public
durable scheduling root. A configured installation supplies
`hive_mind_os.whole_os_composition.WholeOSCompositionHost` to explicitly compose
discovery, bounded building, qualification, idempotent delivery, PR feedback,
and scoped learning inside each package. The stock CLI remains inert because it
does not own those host capabilities.

## Operator CLI

Use a closed JSON document matching `src/hive_mind_os/schemas/whole-os-service-config.schema.json`.
It embeds only the admitted binding descriptor and sealed graph; commands,
imports, callbacks, and credential values are rejected or unsupported.

```text
hive-mind whole-os inspect --config path/to/service.json --json
hive-mind whole-os status --config path/to/service.json --json
hive-mind whole-os run-once --config path/to/service.json --json
hive-mind whole-os resume --config path/to/service.json --json
hive-mind whole-os status --config path/to/service.json --execution-mode cohort --cohort-size 8 --json
```

`inspect` is read-only. `status` projects durable queue state. `run-once` and
`resume` execute one bounded step. The stock CLI has no host executor and
reports `BLOCKED_CAPABILITY`; a configured host must construct `WholeOSService`
with its own `WholeOSHost` and credential broker.

Configured hosts use `run_cohort()` for one capacity-bounded wave or
`run_to_completion()` for bounded dependency-aware fanout until the graph is
terminal or no work is immediately claimable. `run_to_completion()` never sleeps
through retry backoff or steals an active lease; it returns the durable observation
so an operator or supervisor can resume later. Its optional `maximum_cohorts` limit
provides a smaller explicit work budget.

`cohort` is the default execution mode. `strict` is an explicit compatibility
mode that preserves the existing package-at-a-time behavior. In cohort mode, all
dependency-ready packages receive one shared kickoff context, execute concurrently
up to `--max-parallel-packages` (also spelled `--cohort-size`), then converge at one
cohort checkpoint. The effective limit never exceeds the sealed graph's
`maximum_concurrent`. CLI inspection and status JSON always report the selected
mode, effective parallelism, and checkpoint topology so an operator can verify the
selection without starting work.

The service kickoff is deterministic and digest-bound to the campaign, tenant,
repository, admitted binding descriptor, graph, and base snapshot. Host callbacks
receive it through an immutable payload. Scheduler leases are scoped to the service's
job kind and campaign, heartbeated while a host callback runs, and transitioned only
after the typed result returns. Successful jobs remain done across process restarts;
typed authority and capability blockers dead-letter immediately; transient failures
retain the configured retry policy. A blocked branch does not prevent independent
ready branches from completing.

The CLI's stock host boundary remains intentionally inert in either mode. Run and
resume still route through `CohortRuntime` and report typed blockers rather than
claiming unavailable effects. Embedded hosts construct `CohortRuntime` with a
`CohortExecutionPolicy`; strict
hosts may continue using `WholeOSService` unchanged. This keeps existing automation
compatible while allowing a host to replace repeated role-by-role exchanges with a
single kickoff, parallel implementation wave, one convergence pass, and one final
verification checkpoint.

The host supplies `ConfiguredMissionBindingsProvider` and `WholeOSHost`; Hive never
loads credential values from graph payloads. `WholeOSService` enqueues only
dependency-ready packages, uses scheduler leases, binds every payload to the tenant,
repository, descriptor, and graph digest, and reconciles completed jobs before
enqueuing successors. Unknown packages and cross-package results fail closed.

External applications receive source/artifact outputs only. They must not import
Hive, its scheduler, state path, or evidence store at runtime.

## Current evidence state

The generic scheduling and configured-host composition are implemented. Synthetic
tests prove the typed protocol and target-runtime independence; they do not prove
live PR publication, hostile-code isolation, Roblox Studio/device execution, or a
measured tournament. Real host configuration, production adapter attestations,
external delivery grants, and fresh-process receipts remain typed qualification
inputs. See `docs/execution/WHOLE_OS_COMPOSITION_HOST.md` for the configured host
boundary and its explicit incomplete-capability behavior.
