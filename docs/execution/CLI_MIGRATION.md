# CLI migration — public ingress routing to the canonical mission runtime

MIGRATION-460 routes public CLI and scheduler ingress (`hive-mind enqueue`,
`serve`, `status`) to the canonical mission runtime behind a compatibility
switch. New missions default to canonical; the legacy routes remain explicit,
reversible rollback modes for the duration of qualification.

## 1. Routing table

`--compatibility-mode` resolves through
`hive_mind_os.repository_compatibility.resolve_runtime_route`. Any other value
raises `RuntimeRouteError` and the command exits without enqueuing anything.

| mode | runtime | scheduler job kind | kernel ingress record | rollback_ref |
|---|---|---|---|---|
| `canonical` (default) | `canonical` | `canonical-mission` | yes (`canonical-enqueue-v1`) | `rollback:cli-compatibility-mode-kernel-v1` |
| `kernel-v1` | `legacy` | `repository-mission` | yes (`legacy-enqueue-v1`) | `rollback:legacy-enqueue-v1` |
| `legacy` | `legacy` | `repository-mission` | no | `rollback:legacy-only` |

## 2. Default is canonical

```bash
hive-mind enqueue --repository <path> --objective <objective> \
    --acceptance-spec <spec.json> --state-dir <state>
```

is identical to passing `--compatibility-mode canonical`. The enqueue output
carries `"runtime": "canonical"`, the queued job kind is `canonical-mission`,
and a `mission.created` ingress record is appended to the kernel store under
mission id `MISSION-canonical-<legacy-suffix>`.

## 3. Rollback procedure

No data migration is required: the durable queue, the legacy `MissionStore`, and
the kernel store are all unchanged by this node. To roll a request back, re-run
the same `hive-mind enqueue` command with an explicit mode:

- `--compatibility-mode kernel-v1` — legacy execution plus the pre-existing
  `legacy-enqueue-v1` kernel ingress record.
- `--compatibility-mode legacy` — legacy execution only, no kernel write.

Both rollback modes produce a `repository-mission` job that the unchanged
`execute_mission_job` executor runs, so an in-flight canonical qualification can
be abandoned at any time by re-enqueuing. Enqueue is deduplicated on the payload
digest, so repeating a command is a read-only retry rather than a second
request. Because the job kind is part of that digest, a canonical request and
its rollback are separate queue entries and never contend for one lease.

Rollback identity is deliberately absent from enqueue stdout: the guard test
`tests/test_cli_enqueue.py::test_legacy_rollback_mode_reuses_the_existing_job_without_kernel_writes`
requires every stdout key to be mode-invariant across `kernel-v1` and `legacy`.
Mode and rollback identity live in the kernel ingress payload
(`migration_route`, `runtime`, `rollback_ref`) and in
`resolve_runtime_route(mode).rollback_ref`.

## 4. Single-authority invariant

One durable queue (`Scheduler`) carries every request exactly once, keyed by
payload digest. Execution authority is then selected by job kind, in
`hive_mind_os.workers.route_job_executor`:

- `repository-mission` → legacy `MissionStore` / `RepositoryMission` only.
- `canonical-mission` → the `brain_kernel` mission runtime only.

A canonical request never creates a `MissionStore` mission; a legacy request
never invokes the canonical runtime. An unknown kind is refused by the router
itself and is handed to neither authority. The canonical executor has no legacy
fallback: a missing or unusable runtime raises `RuntimeRouteError` and the
scheduler's existing retry/dead-letter path in `Worker.run_once` owns the
failure. The kernel `mission.created` ingress records written by
`record_legacy_enqueue` and `record_canonical_enqueue` are migration *records*,
not a second execution authority — this matches the no-dual-write audit row and
the Cutover gate of `CANONICAL_RUNTIME_MIGRATION_MAP.md`.

### Canonical binding seam

`MissionRuntime.run` takes a `MissionConfig` **and** a `MissionBindings` (role
executor, builder effect authority, per-role verification specs, and a
role-first consultation). None of those can be derived from a scheduler payload,
so `workers._default_canonical_invoker` resolves them through a deployment-
registered provider:

```python
from hive_mind_os import workers

previous = workers.set_canonical_mission_bindings_provider(build_bindings)
```

The provider receives `(payload, kernel_state_root)` and returns
`(MissionConfig, MissionBindings)`. Until one is registered the canonical route
fails closed with `RuntimeRouteError`; it never silently degrades to legacy
execution. `execute_canonical_mission_job(..., invoker=...)` remains available
for callers that own the full invocation.

## 5. How status and receipts identify the runtime

- `hive-mind enqueue` output includes `"runtime": "canonical" | "legacy"`.
- The kernel ingress payload includes `migration_route`, `runtime`, and (on the
  canonical route) `rollback_ref`.
- `hive-mind status` adds a top-level `runtime_routes` object mapping each
  mission id (or job id, when a job carries none) to the runtime that owns it,
  derived from the queued job kind via `runtime_identity`. An unrecognised kind
  renders `"unknown"` rather than failing: status is a read-only projection and
  must not crash. The HTML status page renders only `model["missions"]` and is
  unaffected by the added key.

## 6. See also

`docs/execution/CANONICAL_RUNTIME_MIGRATION_MAP.md` — the overall canonical
runtime migration map, including the no-dual-write audit and Cutover gate this
node satisfies.
