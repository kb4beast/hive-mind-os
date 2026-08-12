# MIGRATION-460 — Route public CLI and scheduler ingress to the canonical mission runtime

## 1. Contract summary

**Objective.** Route public CLI (`hive-mind enqueue` / `serve` / `status`) and
scheduler ingress to the canonical mission runtime behind compatibility
switches. New missions default to canonical; legacy stays as explicit,
reversible rollback modes.

**Acceptance criteria (compressed).**

| # | Criterion |
|---|---|
| AC1 | New missions default to canonical runtime. |
| AC2 | Legacy routes remain explicit rollback modes during qualification. |
| AC3 | No request is executed by two authoritative stores. |
| AC4 | Status and receipts identify the actual runtime. |

**Scope.**

| Kind | Paths |
|---|---|
| write (exact, complete) | `src/hive_mind_os/cli.py`, `src/hive_mind_os/workers.py`, `src/hive_mind_os/repository_compatibility.py`, `tests/test_hive_cortex_cli_migration.py` (new), `docs/execution/CLI_MIGRATION.md` (new) |
| read (exact, sealed) | `src/hive_mind_os/cli.py`, `src/hive_mind_os/workers.py`, `src/hive_mind_os/repository_compatibility.py` — this is the contract's complete `read_scope`. Do NOT open any other file: every collaborator fact this node needs (scheduler, projection, mission_store, brain_kernel store/events/canonical, cortex compatibility, mission_runtime, the two guard tests) is carried as a verified inline signature in the Section 2 map. |
| forbidden (never create/modify) | any `__init__.py`, any `conftest.py`, `pyproject.toml`, `.autopilot/**`, `.github/CODEOWNERS`, `.github/governance/**`, `evidence/courts/**`, `docs/architecture/HARDENED_VISION_CONTRACT.md`, `src/hive_mind_os/projection.py`, `src/hive_mind_os/scheduler.py`, `src/hive_mind_os/mission_store.py`, everything under `src/hive_mind_os/brain_kernel/` and `src/hive_mind_os/cortex/`, all sibling nodes' files, all other tests |

**Semantic locks:** `public-cli-routing`, `canonical-runtime`.
**Round:** R4, ALONE (`parallel_safe: false`, merge surface high) — no siblings.
Branch `autopilot/migration-460`; never touch the release branch; never
rebase/squash/amend the node branch; stop at a draft PR + node receipt.

## 2. Existing-code map (real signatures — do not re-derive)

| Path | Symbol | Signature (verbatim) | Role |
|---|---|---|---|
| `src/hive_mind_os/repository_compatibility.py` | `LEGACY_ENQUEUE_ROUTE` | `LEGACY_ENQUEUE_ROUTE = "legacy-enqueue-v1"` | existing legacy ingress route id |
| `src/hive_mind_os/repository_compatibility.py` | `default_kernel_state_dir` | `def default_kernel_state_dir(legacy_state_dir: str | Path) -> Path` | derives sibling `.hive-mind-kernel-state` root |
| `src/hive_mind_os/repository_compatibility.py` | `record_legacy_enqueue` | `def record_legacy_enqueue(job: Job, *, kernel_state_dir: str | Path | None = None, legacy_state_dir: str | Path) -> str` | idempotent kernel `mission.created` record for a legacy job; template for the canonical variant |
| `src/hive_mind_os/scheduler.py` | `Job` | frozen dataclass: `id, kind, payload, payload_digest, state, attempts, max_attempts, not_before, lease_owner, lease_token, lease_expiry, mission_id, last_error` | one durable queue entry |
| `src/hive_mind_os/scheduler.py` | `Scheduler.enqueue` | `def enqueue(self, kind: str, payload: Mapping[str, Any], *, max_attempts: int = 3, not_before: float | None = None, mission_id: str | None = None) -> Job` | single durable queue; dedupes on payload digest |
| `src/hive_mind_os/scheduler.py` | `Scheduler.jobs` | `def jobs(self) -> tuple[Job, ...]` | read all jobs (used by status and tests) |
| `src/hive_mind_os/workers.py` | `JobExecutor` | `JobExecutor = Callable[[Job, Path], str]` | executor contract; returns mission id |
| `src/hive_mind_os/workers.py` | `execute_mission_job` | `def execute_mission_job(job: Job, state_dir: Path) -> str` | LEGACY executor; raises `ValueError` unless `job.kind == "repository-mission"`; runs `RepositoryMission` via `MissionStore` |
| `src/hive_mind_os/workers.py` | `Worker.__init__` | `def __init__(self, scheduler: Scheduler, owner: str, *, executor: JobExecutor = execute_mission_job, heartbeat_interval: float | None = None) -> None` | lease-owning worker; default executor changes in this node |
| `src/hive_mind_os/workers.py` | `serve` | `def serve(state_dir: str | Path, *, worker_count: int, once: bool, stop_event: threading.Event | None = None, executor: JobExecutor = execute_mission_job) -> int` | CLI serve loop; default executor changes in this node |
| `src/hive_mind_os/cli.py` | `build_enqueue_parser` | `def build_enqueue_parser() -> argparse.ArgumentParser` | owns `--compatibility-mode` (today: `choices=("kernel-v1", "legacy"), default="kernel-v1"`) |
| `src/hive_mind_os/cli.py` | `_run_enqueue` | `def _run_enqueue(args: argparse.Namespace) -> int` | computes `mission_id = f"M-{sha256(encoded).hexdigest()[:32]}"`, enqueues kind `"repository-mission"`, calls `record_legacy_enqueue` when mode is `kernel-v1` |
| `src/hive_mind_os/cli.py` | `_run_serve` | `def _run_serve(args: argparse.Namespace) -> int` | wraps `serve(args.state_dir, worker_count=args.workers, once=args.once)` |
| `src/hive_mind_os/cli.py` | `_run_status` | `def _run_status(args: argparse.Namespace) -> int` | `model = build_projection(args.state_dir)`; prints `projection_json(model)` or writes HTML |
| `src/hive_mind_os/projection.py` | `build_projection` | `def build_projection(state_dir: str | Path, *, schema_version: int = DEFAULT_PROJECTION_SCHEMA_VERSION) -> dict[str, Any]` | read-only status model; `projection_html` reads only `model["missions"]`, so extra top-level keys are safe |
| `src/hive_mind_os/projection.py` | `projection_json` | `def projection_json(model: dict[str, Any]) -> str` | JSON dump used by `_run_status` |
| `src/hive_mind_os/mission_store.py` | `MissionStore.has_mission` | `def has_mission(self, mission_id: str) -> bool` | legacy mission truth; must stay EMPTY for canonical requests (AC3 probe) |
| `src/hive_mind_os/brain_kernel/store.py` | `KernelStore.database_path` | `def database_path(state_dir: str | Path) -> Path` (staticmethod) | portable kernel db path |
| `src/hive_mind_os/brain_kernel/store.py` | `KernelStore.append` | `def append(self, event: KernelEvent, *, expected_sequence: int | None = None, recorded_at: str = "1970-01-01T00:00:00Z", idempotency_key: str | None = None) -> int` | idempotent durable append |
| `src/hive_mind_os/brain_kernel/store.py` | `KernelStore.events` | `def events(self) -> list[dict[str, Any]]` | read chain (for `previous_digest` and tests) |
| `src/hive_mind_os/brain_kernel/events.py` | `KernelEvent` | frozen dataclass: `event_id, mission_id, event_type, actor_id, occurred_at, payload, work_id=None, attempt_id=None, actor_role=None, event_version=1, previous_digest=None` | kernel fact shape |
| `src/hive_mind_os/brain_kernel/canonical.py` | `canonical_digest` | `def canonical_digest(value: Any) -> str` | `sha256:`-prefixed digest for idempotency keys |
| `src/hive_mind_os/cortex/compatibility/models.py` | `AdapterMode` | `class AdapterMode(StrEnum): LEGACY = "legacy"; SHADOW = "shadow"; CANONICAL = "canonical"` | naming source for runtime identities |
| `src/hive_mind_os/cortex/compatibility/models.py` | `CompatibilityError` | `class CompatibilityError(RuntimeError)` | precedent for typed route errors |
| `src/hive_mind_os/cortex/compatibility/routing.py` | `RollbackRouter` | `class RollbackRouter(Generic[_T])` with `route(mode)`, `rollback()`, `invoke(...)` | design precedent: exactly one owner invoked per operation, rollback ref retained |
| `src/hive_mind_os/brain_kernel/mission_runtime.py` | `MissionRuntime` | per the MISSION-400 runbook §3.1 (lands in R1, verbatim): `class MissionRuntime:` with `def __init__(self, store: KernelStore) -> None` and `def run(self, config: MissionConfig, bindings: MissionBindings) -> MissionRunReceipt` | the canonical end-to-end mission runner this node binds to — do NOT read the file (outside `read_scope`); if the landed module lacks exactly this entry point, escalate (Section 6), never re-derive |
| `tests/test_cli_enqueue.py` | `test_legacy_rollback_mode_reuses_the_existing_job_without_kernel_writes` | asserts `assertEqual(migrated, rolled_back)` on the FULL parsed stdout dict of a `kernel-v1` enqueue vs a `legacy` enqueue of the same work | out-of-scope guard: every enqueue stdout key must be mode-invariant across `kernel-v1` and `legacy` (see 3.3) |
| `tests/test_workers.py` | (guard facts) | `"repository-mission"` jobs run through `Worker(queue, ...)` with the DEFAULT executor and must complete; jobs of other kinds (`"test"`) always inject a custom `executor=` | out-of-scope guard: the default-executor flip must keep legacy kind end-to-end green |

Naming/interop note: `AdapterMode` values are reused as *strings* only
(`"legacy"` / `"canonical"`); `repository_compatibility.py` must NOT import
from `cortex.compatibility` (it deliberately stays an outer-layer module that
imports only `brain_kernel` and `scheduler` — keep it that way).

Scope note: the sealed contract's `read_scope` (`.autopilot/plan.json`,
MIGRATION-460) is exactly `cli.py`, `workers.py`,
`repository_compatibility.py`. Every other row in this map is a verified
inline signature recorded at runbook-authoring time precisely so the worker
never opens an out-of-scope file (per the README worker read budget: rendered
prompt + `AGENTS.md` + this runbook + read-scope files only). If any inline
signature is contradicted by the landed code, escalate per Section 6 — do not
read out-of-scope files to re-derive it.

## 3. Design

### 3.1 `src/hive_mind_os/repository_compatibility.py` — additive route layer

Keep every existing symbol byte-compatible. Add:

```python
CANONICAL_ENQUEUE_ROUTE = "canonical-enqueue-v1"
CANONICAL_JOB_KIND = "canonical-mission"
LEGACY_JOB_KIND = "repository-mission"
RUNTIME_CANONICAL = "canonical"
RUNTIME_LEGACY = "legacy"
COMPATIBILITY_MODES = ("canonical", "kernel-v1", "legacy")


class RuntimeRouteError(RuntimeError):
    """A public ingress request cannot be routed without weakening a gate."""


@dataclass(frozen=True, slots=True)
class RuntimeRoute:
    mode: str                     # selected --compatibility-mode value
    runtime: str                  # RUNTIME_CANONICAL | RUNTIME_LEGACY
    job_kind: str                 # scheduler kind carrying the request
    records_kernel_ingress: bool  # append a kernel mission.created record?
    rollback_ref: str             # explicit route back


def resolve_runtime_route(compatibility_mode: str) -> RuntimeRoute
def runtime_identity(job_kind: str) -> str
def record_canonical_enqueue(job: Job, *, kernel_state_dir: str | Path | None = None,
                             legacy_state_dir: str | Path) -> str
```

`resolve_runtime_route` mapping (anything else raises `RuntimeRouteError`):

| mode | runtime | job_kind | kernel ingress | rollback_ref |
|---|---|---|---|---|
| `canonical` (default) | `canonical` | `canonical-mission` | yes | `rollback:cli-compatibility-mode-kernel-v1` |
| `kernel-v1` | `legacy` | `repository-mission` | yes (existing `record_legacy_enqueue`) | `rollback:legacy-enqueue-v1` |
| `legacy` | `legacy` | `repository-mission` | no | `rollback:legacy-only` |

`runtime_identity(job_kind)` returns `RUNTIME_CANONICAL` for
`canonical-mission`, `RUNTIME_LEGACY` for `repository-mission`, and the
literal string `"unknown"` otherwise (status is a projection and must not
crash; executors fail closed separately).

`record_canonical_enqueue` mirrors `record_legacy_enqueue` line-for-line with:
kernel mission id `f"MISSION-canonical-{job.mission_id[2:]}"` (same `M-`
validation), `event_id = f"migration:{CANONICAL_ENQUEUE_ROUTE}:{legacy_mission_id}"`,
`event_type="mission.created"`, `actor_id="migration-460-cli-ingress"`,
`actor_role="integrator"`, `occurred_at="1970-01-01T00:00:00Z"`, payload
`{"migration_route": CANONICAL_ENQUEUE_ROUTE, "runtime": RUNTIME_CANONICAL,
"legacy_mission_id", "scheduler_job_id", "scheduler_payload_digest",
"repository_pin": job.payload.get("pin"), "rollback_ref":
"rollback:cli-compatibility-mode-kernel-v1"}`, `previous_digest` from
`store.events()[-1]["digest"]` when non-empty, and idempotency key
`canonical_digest({"route": CANONICAL_ENQUEUE_ROUTE, "legacy_mission_id": ...,
"scheduler_payload_digest": job.payload_digest})`. Idempotent: re-running the
same enqueue is a read-only retry.

### 3.2 `src/hive_mind_os/workers.py` — kind-based dispatch, fail-closed

Add after `execute_mission_job` (import `CANONICAL_JOB_KIND`,
`LEGACY_JOB_KIND`, `RuntimeRouteError`, `default_kernel_state_dir` from
`.repository_compatibility`; this direction has no import cycle —
`repository_compatibility` never imports `workers`):

```python
CanonicalMissionInvoker = Callable[[Job, Path], str]


def _default_canonical_invoker(job: Job, state_dir: Path) -> str:
    """Bind lazily to hive_mind_os.brain_kernel.mission_runtime (MISSION-400)."""


def execute_canonical_mission_job(
    job: Job, state_dir: Path, *, invoker: CanonicalMissionInvoker | None = None,
) -> str:
    if job.kind != CANONICAL_JOB_KIND:
        raise ValueError(f"unsupported job kind: {job.kind}")
    ...


def route_job_executor(job: Job, state_dir: Path) -> str:
    if job.kind == CANONICAL_JOB_KIND:
        return execute_canonical_mission_job(job, state_dir)
    if job.kind == LEGACY_JOB_KIND:
        return execute_mission_job(job, state_dir)
    raise ValueError(f"unsupported job kind: {job.kind}")
```

`_default_canonical_invoker` binds to the MISSION-400 entry point exactly as
quoted in the Section 2 map (`MissionRuntime(store).run(config, bindings) ->
MissionRunReceipt`). Do NOT read `brain_kernel/mission_runtime.py` or
`docs/execution/CANONICAL_MISSION_RUNTIME.md` — both are outside this node's
`read_scope`; the quoted signature is the binding contract, and a mismatch is
an escalation (Section 6), not a research task. Call that entry point with
the job payload fields
(`mission_id`, `repository`, `objective`, `acceptance_criteria`,
`acceptance_specifications`, `pin`) and a kernel state root of
`default_kernel_state_dir(state_dir)`; return the mission id string. Import
`mission_runtime` INSIDE the function body (lazy) so legacy-only deployments
never import it. If the import or the expected entry point is missing, raise
`RuntimeRouteError` — NEVER fall back to legacy (fail closed; the scheduler's
existing retry/dead-letter path in `Worker.run_once` handles the failure).
`execute_canonical_mission_job` uses `invoker or _default_canonical_invoker`
so tests inject a recording invoker without the full runtime.

Change ONLY the two executor defaults: `Worker.__init__(...,
executor: JobExecutor = route_job_executor, ...)` and `serve(...,
executor: JobExecutor = route_job_executor)`. Everything else in `Worker`,
`serve`, and `execute_mission_job` stays byte-identical — `tests/test_workers.py`
enqueues `"repository-mission"` jobs against the default executor and must
keep passing unmodified. Define `route_job_executor` before `Worker` so the
default binds.

### 3.3 `src/hive_mind_os/cli.py` — switch, ingress record, status identity

- `build_enqueue_parser`: `--compatibility-mode` becomes
  `choices=("canonical", "kernel-v1", "legacy"), default="canonical"` with help
  text naming canonical as the default runtime and `kernel-v1`/`legacy` as
  explicit rollback modes during qualification.
- `_run_enqueue`: after computing `mission_id`, call
  `route = resolve_runtime_route(getattr(args, "compatibility_mode", "canonical"))`
  (wrap `RuntimeRouteError` in `SystemExit`). Enqueue with
  `scheduler.enqueue(route.job_kind, {"mission_id": mission_id,
  "runtime": route.runtime, **semantic_payload}, max_attempts=args.max_attempts,
  mission_id=mission_id)`. Then: `route.mode == "canonical"` →
  `record_canonical_enqueue(job, legacy_state_dir=args.state_dir,
  kernel_state_dir=getattr(args, "kernel_state_dir", None))`;
  `route.mode == "kernel-v1"` → existing `record_legacy_enqueue(...)` call
  unchanged; `legacy` → no kernel write. Extend the printed JSON with exactly
  ONE new key: `"runtime": route.runtime` (keep existing keys untouched —
  `tests/test_cli_enqueue.py` parses this JSON and is out of scope). Do NOT
  print `compatibility_mode` or `rollback_ref`: the guard test
  `test_legacy_rollback_mode_reuses_the_existing_job_without_kernel_writes`
  asserts `assertEqual(migrated, rolled_back)` on the FULL parsed dict of a
  `kernel-v1` enqueue vs a `legacy` enqueue of the same work, so every stdout
  key must be mode-invariant across those two modes. `runtime` qualifies
  (both resolve to `"legacy"`); `compatibility_mode` (`"kernel-v1"` vs
  `"legacy"`) and `rollback_ref` (`"rollback:legacy-enqueue-v1"` vs
  `"rollback:legacy-only"`) do not. Mode and rollback identity live instead in
  the kernel ingress event payload (`record_canonical_enqueue`, Section 3.1)
  and are pinned by this node's own tests via
  `resolve_runtime_route(...).rollback_ref`.
- `_run_status`: after `model = build_projection(args.state_dir)`, open
  `Scheduler(args.state_dir)` (close in `finally`) and attach
  `model["runtime_routes"] = {job.mission_id or job.id:
  runtime_identity(job.kind) for job in scheduler.jobs()}` before printing.
  `projection_html` renders only `model["missions"]`, so the HTML path is
  unaffected by the extra top-level key; the JSON path now identifies the
  actual runtime per mission (AC4).
- `_run_serve`: unchanged (dispatch is by job kind inside `workers.py`).
- Imports: extend the existing `from .repository_compatibility import ...`
  line; add `Scheduler` usage is already imported.

### 3.4 Authority model (AC3, state in `docs/execution/CLI_MIGRATION.md`)

One durable queue (`Scheduler`) carries every request exactly once, keyed by
payload digest. Execution authority is selected by job kind: `repository-
mission` → legacy `MissionStore`/`RepositoryMission` only; `canonical-mission`
→ `brain_kernel` mission runtime only. A canonical request never creates a
`MissionStore` mission; a legacy request never invokes the canonical runtime.
The kernel `mission.created` ingress records (both routes' `record_*_enqueue`)
are migration *records*, not a second execution authority — this matches the
"no-dual-write audit" row and Cutover gate of
`docs/execution/CANONICAL_RUNTIME_MIGRATION_MAP.md`.

### 3.5 `docs/execution/CLI_MIGRATION.md` (new)

Sections: (1) routing table from 3.1 verbatim; (2) default-canonical statement
with the exact flag (`hive-mind enqueue ... --compatibility-mode canonical` is
the default); (3) rollback procedure — re-enqueue with `--compatibility-mode
kernel-v1` (legacy execution + kernel record) or `legacy` (legacy only), no
data migration required because the queue and stores are unchanged; (4) the
single-authority invariant of 3.4; (5) how status/receipts identify the
runtime (`runtime_routes` in `hive-mind status`, `runtime` in enqueue output
and kernel ingress payload); (6) pointer to `CANONICAL_RUNTIME_MIGRATION_MAP.md`.

## 4. Implementation order (small commits on `autopilot/migration-460`)

1. `repository_compatibility.py`: constants, `RuntimeRouteError`,
   `RuntimeRoute`, `resolve_runtime_route`, `runtime_identity`,
   `record_canonical_enqueue`.
2. `workers.py`: add `CanonicalMissionInvoker`, `_default_canonical_invoker`
   (bound to the Section 2 quoted `MissionRuntime.run` signature — do not read
   `mission_runtime.py`; escalate on mismatch), `execute_canonical_mission_job`,
   `route_job_executor`; flip the two executor defaults.
3. `cli.py`: parser choices/default, `_run_enqueue` routing + output keys,
   `_run_status` runtime annotation.
4. `tests/test_hive_cortex_cli_migration.py` (all classes below).
5. `docs/execution/CLI_MIGRATION.md`.
6. Run focused tests (Section 5), fix, commit, push branch, open draft PR,
   record the node receipt. STOP — no merge, no downstream nodes.

## 5. Test plan

New file `tests/test_hive_cortex_cli_migration.py`, stdlib `unittest` only,
using the same pattern as `tests/test_cli_enqueue.py` — the pattern is fully
stated here so the file need not be opened: TemporaryDirectory + `addCleanup`,
`tests.fixtures.fixture_repo.build_fixture_repo`, `argparse.Namespace` into
`cli._run_enqueue`, `redirect_stdout` + `json.loads` on output.

| required_tests name | Test class | Methods |
|---|---|---|
| `cli-routing-tests` | `CliRoutingTests` | `test_parser_defaults_compatibility_mode_to_canonical` (parse minimal argv via `cli.build_enqueue_parser()`); `test_new_enqueue_defaults_to_canonical_runtime` (default Namespace → output `runtime == "canonical"`, sole job kind `canonical-mission`, kernel store has the `canonical-enqueue-v1` `mission.created` event); `test_worker_routes_canonical_kind_to_canonical_executor` (enqueue canonical, `Worker(queue, "t", executor=lambda job, sd: workers.execute_canonical_mission_job(job, sd, invoker=recorder)).run_once()` → recorder called once, job `done`); `test_status_identifies_actual_runtime` (one canonical + one legacy enqueue → `_run_status` JSON `runtime_routes` maps each mission to its runtime; `--html` path still writes) |
| `no-dual-authority-tests` | `NoDualAuthorityTests` | `test_canonical_request_never_reaches_legacy_mission_store` (canonical enqueue + stub-invoker execution → `MissionStore(state_dir).has_mission(mission_id)` is `False`, no `state/d/<mission>` directory); `test_legacy_request_never_invokes_canonical_runtime` (`unittest.mock.patch` `hive_mind_os.workers.execute_canonical_mission_job` with a fail-if-called sentinel, run a `repository-mission` job through `route_job_executor`); `test_duplicate_enqueue_is_deduplicated_single_job` (same canonical enqueue twice → one scheduler job, kernel append idempotent); `test_unknown_job_kind_fails_closed` (`route_job_executor` raises `ValueError`); `test_missing_canonical_runtime_fails_closed_not_fallback` (invoker raising `RuntimeRouteError` → job retries/dead-letters via `Worker.run_once`, `MissionStore` stays empty) |
| `legacy-rollback-tests` | `LegacyRollbackTests` | `test_kernel_v1_mode_retains_legacy_execution_and_kernel_record` (mode `kernel-v1` → job kind `repository-mission`, output `runtime == "legacy"`, `legacy-enqueue-v1` kernel event, and `resolve_runtime_route("kernel-v1").rollback_ref == "rollback:legacy-enqueue-v1"` — rollback identity is NOT in stdout, per 3.3); `test_legacy_mode_writes_no_kernel_record` (mode `legacy` → no kernel database file); `test_unknown_mode_is_rejected` (`resolve_runtime_route("shadow")` and `"canary"` raise `RuntimeRouteError`); `test_legacy_job_still_executes_end_to_end` (fixture repo + `Worker(queue, "w").run_once()` with the NEW default executor completes the legacy mission, guarding the default-flip regression) |

Exact focused commands (repo root; if `hive_mind_os` resolves outside this
worktree, prefix `PYTHONPATH=src `):

```bash
python -m unittest tests.test_hive_cortex_cli_migration -v
python -m unittest tests.test_cli_enqueue -v      # out-of-scope guard: must stay green unmodified
python -m unittest tests.test_workers -v          # out-of-scope guard: default-executor flip must not break it
```

Do NOT run `python -m unittest discover` or any repo-wide pass — the R4
integrator runs the single leased repo-wide validation.

Edge cases the tests must pin: `M-` prefix validation in
`record_canonical_enqueue` (invalid mission id raises `ValueError`); kernel
event chain `previous_digest` correct when the canonical record is appended
after an existing event; `runtime_identity` returning `"unknown"` for a
foreign kind without crashing `_run_status`.

## 6. Acceptance self-check → receipt evidence

| Criterion | Demonstrated by | Receipt evidence |
|---|---|---|
| AC1 new missions default canonical | parser default + `test_new_enqueue_defaults_to_canonical_runtime` | focused test transcript; `git diff` hunk of `build_enqueue_parser` |
| AC2 legacy = explicit rollback modes | `LegacyRollbackTests` (both modes still work, unknown modes rejected); `CLI_MIGRATION.md` rollback procedure | test transcript; doc path |
| AC3 no dual authoritative stores | `NoDualAuthorityTests` (mission store untouched by canonical, canonical runtime untouched by legacy, dedup, fail-closed) | test transcript; Section 3.4 invariant quoted in receipt |
| AC4 status/receipts identify runtime | `runtime` in enqueue JSON + kernel ingress payload; `runtime_routes` in status; `test_status_identifies_actual_runtime` | test transcript; sample status JSON |
| Evidence requirements | base + final commit SHAs, changed-path list (must equal write_scope subset), command receipts, roles, rollback ref `rollback:cli-compatibility-mode-kernel-v1` | node completion receipt |

Escalate (per contract) instead of improvising if: `mission_runtime.py` did
not land or exposes no usable public run entry (contradicted assumption);
required changes exceed write scope; three semantic attempts fail.

## 7. Out-of-scope traps — do NOT

- Do not modify `projection.py`, `scheduler.py`, `mission_store.py`,
  `mission.py`, anything under `brain_kernel/` or `cortex/` — annotate status
  in `_run_status` (cli.py) only.
- Do not touch `tests/test_cli_enqueue.py` or `tests/test_workers.py`; they
  are compatibility guards. If one breaks, fix your change, not the test.
- Do not create or edit any `__init__.py`, `conftest.py`, `pyproject.toml`,
  `.autopilot/**`, `.github/CODEOWNERS`, `.github/governance/**`,
  `evidence/courts/**`, or `docs/architecture/HARDENED_VISION_CONTRACT.md`.
- Do not import `cortex.compatibility` from `repository_compatibility.py`, and
  do not import `mission_runtime` at module top level in `workers.py` (lazy
  import inside `_default_canonical_invoker` only). New symbols are reached by
  full module path; no package re-export edits anywhere.
- Do not add a legacy fallback inside the canonical executor, a second queue,
  a `MissionStore` write for canonical missions, or a kernel execution write
  for legacy missions.
- Do not remove or rename `record_legacy_enqueue`, `LEGACY_ENQUEUE_ROUTE`,
  `execute_mission_job`, or any existing CLI flag/output key.
- Do not run repo-wide test discovery; do not merge the PR; do not touch the
  release branch; never rebase/squash/amend `autopilot/migration-460`.
