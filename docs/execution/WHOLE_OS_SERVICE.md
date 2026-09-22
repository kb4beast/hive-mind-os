# Whole-OS service composition

The pipeline defaults to `full-autonomy-or-superiority`. A bounded operational run
must opt into `-ClaimScope bounded-operational-production-pilot` and retain exact
candidate, authority, target/runtime, 72-hour, restart, and rollback evidence.

The implementation composes repository bindings, a versioned outcome graph, the
durable scheduler, independent qualification, lesson routing, delivery, and
benchmark adapters. `hive_mind_os.whole_os_service.WholeOSService` is the public
durable scheduling root. A configured installation supplies
`hive_mind_os.whole_os_composition.WholeOSCompositionHost` to explicitly compose
discovery, bounded building, qualification, idempotent delivery, PR feedback,
and scoped learning inside each package. The CLI resolves those capabilities only
from the sealed, process-local host-factory registry populated by trusted launcher
code; target configuration cannot name imports, commands, credentials, or secrets.

## Operator CLI

Use a closed JSON document matching `src/hive_mind_os/schemas/whole-os-service-config.schema.json`.
It embeds only the admitted binding descriptor and sealed graph; commands,
imports, callbacks, and credential values are rejected or unsupported.

```text
hive-mind whole-os inspect --config path/to/service.json --json
hive-mind whole-os status --config path/to/service.json --json
hive-mind whole-os start --config path/to/service.json --json
hive-mind whole-os run-once --config path/to/service.json --json
hive-mind whole-os resume --config path/to/service.json --json
hive-mind whole-os status --config path/to/service.json --execution-mode cohort --cohort-size 8 --json
```

`inspect` and `status` are read-only and do not initialize the queue or resolve an
executable host. `run-once` runs one dependency-ready cohort (one package in strict
mode). `start` and `resume` boundedly run cohorts until the campaign is terminal or
cannot make immediate progress. A trusted launcher registers an independently
validated `WholeOSHostFactoryRegistration` before invoking the CLI. If no factory
matches the descriptor's provider version, configuration digest, and authority
reference, execution returns `blocked_capability` without initializing the service.

The standalone stock `hive-mind` shell starts with an empty process-local registry;
therefore its executable commands block unless trusted launcher code registered a
factory in that same process. A deployment console script should call
`run_registered_whole_os(argv, registration=..., factory=...)`. This is intentional:
the stock shell cannot infer adapters or credentials from a repository or service
JSON document. `inspect` and `status` remain directly usable from the stock shell.

For the repository-owned Codex deployment host, use the sequential executable
pipeline. It launches one stage at a time and durably resumes incomplete stages:

```powershell
powershell -NoProfile -File scripts/whole-os/Invoke-WholeOSPipeline.ps1 -Background
```

For the smaller two-target pilot, select the bounded scope explicitly:

```powershell
powershell -NoProfile -File scripts/whole-os/Invoke-WholeOSPipeline.ps1 `
  -ClaimScope bounded-operational-production-pilot -Background
```

That route runs host bootstrap, N32, and N33. The default full scope also runs N30
and N31. Existing state without a scope is treated as full scope, and a state-root
scope mismatch stops before reuse.

Individual stages can also be invoked directly from `scripts/whole-os/`. Their
structured receipts default to `%LOCALAPPDATA%\HiveMindOS\whole-os-pipeline`, outside
the target repository and its application artifacts.

The trusted local Codex composition is a separate launcher. It admits the exact
clean `codex/` checkout, resolves and hashes the native Codex executable, writes the
inert service JSON and all runtime evidence outside the repository, obtains a fresh
read-only Curator session, registers the host factory in-process, and starts
`WholeOSService`:

```powershell
powershell -NoProfile -File scripts/whole-os/Invoke-WholeOSCodexService.ps1 `
  -Repository (Resolve-Path .) `
  -StateRoot "$env:LOCALAPPDATA\HiveMindOS\whole-os-codex-host"
```

The bootstrap profile grants trusted-local planning/build only. Its startup mission
is deliberately read-only and must retain distinct real Codex Curator and Builder
session IDs before the startup receipt can report `complete`. The service config has
no import, command, callback, credential, secret, or token field; Codex authentication
stays in its normal user-owned session store. The launcher does not grant GitHub
delivery, hostile-code isolation, deployment, spending, merge, or external signing.
Successful append-only receipts are stored below
`<StateRoot>\startup-receipts\`; `startup-current.json` is only the replaceable
operator pointer to the latest attempt.

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

Executable CLI routes now construct `WholeOSService` from the admitted host factory;
there is no unconfigured or synthetic execution fallback. Cohort mode calls the
service's durable `run_cohort()`/`run_to_completion()` paths. Strict mode preserves
the package-at-a-time compatibility path. This keeps existing automation compatible
while allowing a host to replace repeated role-by-role exchanges with a single
kickoff, parallel implementation wave, one convergence pass, and one final
verification checkpoint.

The host supplies `ConfiguredMissionBindingsProvider` and `WholeOSHost`; Hive never
loads credential values from graph payloads. `WholeOSService` enqueues only
dependency-ready packages, uses scheduler leases, binds every payload to the tenant,
repository, descriptor, and graph digest, and reconciles completed jobs before
enqueuing successors. Unknown packages and cross-package results fail closed.

External applications receive source/artifact outputs only. They must not import
Hive, its scheduler, state path, or evidence store at runtime.

## Current evidence state

The generic scheduling and configured-host composition are implemented. A fresh
trusted local host process completed for exact clean baseline `ed96ffde`, but that
receipt does not prove hostile-code isolation, external delivery, a later candidate,
Roblox Studio/device execution, or a measured tournament. Production candidate and
adapter attestations, external delivery grants, target/runtime receipts, and the
72-hour window remain typed bounded-pilot inputs. See
`docs/execution/WHOLE_OS_COMPOSITION_HOST.md` for the configured host boundary and
its explicit incomplete-capability behavior.
