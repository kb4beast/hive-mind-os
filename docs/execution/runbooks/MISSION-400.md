# MISSION-400 — Canonical end-to-end mission runner (mission_runtime + mission_adapter)

Read this runbook plus your rendered prompt only. Do not re-read
`.autopilot/plan.json`, `.autopilot/README.md`, or policy files. The wave
protocol is `docs/execution/runbooks/README.md`; you are the R1 worker, not
the integrator. This node runs ALONE in Round R1 (level 6) — no siblings —
and every remaining node depends on it.

## 1. Contract summary

**Objective.** Wire ONE canonical end-to-end mission runner through all eight
roles, consultation, durable effects, exact verification, and acceptance — by
COMPOSING the existing role/effect/verification machinery, never reimplementing it.

**Acceptance criteria (compressed).**
1. A single objective executes all applicable roles with real typed outputs
   and receipts.
2. Role-first consultation resolves role-resolvable ambiguity before human
   escalation.
3. Effects, verification, remand, integration, operations, and optimization
   are event-derived.
4. Routine reversible repository work completes without discretionary human
   answers.
5. No role or model self-approves, fabricates authority, or bypasses
   exact-candidate verification.

**Scope table.**

| Kind | Paths |
|---|---|
| write_scope (ONLY these 4) | `src/hive_mind_os/brain_kernel/mission_runtime.py`, `src/hive_mind_os/cortex/repository/mission_adapter.py`, `tests/test_hive_cortex_mission_runtime.py`, `docs/execution/CANONICAL_MISSION_RUNTIME.md` |
| read_scope | `src/hive_mind_os/brain_kernel/**`, `src/hive_mind_os/cortex/**`, `src/hive_mind_os/model_backend.py` (all read-only) |
| forbidden_scope | `.github/CODEOWNERS`, `.github/governance/**`, `evidence/courts/**`, `docs/architecture/HARDENED_VISION_CONTRACT.md` |

Additionally forbidden (hard rules): any `__init__.py` — note
`src/hive_mind_os/cortex/repository/__init__.py` ALREADY EXISTS, so
`mission_adapter.py` is a new module inside an existing package and NO
`__init__` edit is needed or allowed — any `conftest.py`, `pyproject.toml`,
`.autopilot/**`, and every file outside the four write-scope paths. New
modules are imported by full module path (`hive_mind_os.brain_kernel.
mission_runtime`, `hive_mind_os.cortex.repository.mission_adapter`); no
package re-exports.

**Semantic locks:** `canonical-mission-runtime` (this node defines it);
`event-schema` — the reducer in `projection.py` is CLOSED (`reduce_event`
raises on unknown types); append ONLY the nine existing event types
(`mission.created`, `mission.transition`, `work.created`, `work.transition`,
`evaluation.plan.sealed`, `evaluation.result`, `evaluation.bundle.recorded`,
`closeout.obligations.declared`, `role.result`) and do NOT edit
`projection.py`; `authority-model` — no new grants; only
`AuthorityRegistry`/capability tokens authorize effects.

**Branch:** `autopilot/mission-400`, PR target `main` (draft PR only; never
merge, never touch the release branch, never rebase/squash/amend the node
branch, never run repo-wide test discovery — the authenticated validation broker
exclusively owns that gate). Stopping condition: draft integration PR with the
eight-role local mission suite green; do NOT route public CLI traffic.

## 2. Existing-code map (real symbols; NEVER invent others; paths relative to `src/hive_mind_os/`)

| Path | Symbol | Real signature | Role in this node |
|---|---|---|---|
| `brain_kernel/canonical.py` | `canonical_digest` | `canonical_digest(value: Any) -> str` | `sha256:<64hex>` over canonical JSON; receipt/consultation digests |
| `brain_kernel/store.py` | `KernelStore` | `KernelStore(path: str \| Path = ":memory:", *, read_only: bool = False)`; `append(event, *, expected_sequence=None, recorded_at="1970-01-01T00:00:00Z", idempotency_key=None) -> int`; `events() -> list[dict]`; `projection() -> dict`; `rebuild_projections() -> dict`; `effect_entry(*, intent_digest) -> dict \| None`; `close()` | durable spine + projections; every `append` must chain `previous_digest=events[-1]["digest"]` |
| `brain_kernel/events.py` | `KernelEvent` | frozen dataclass `(event_id, mission_id, event_type, actor_id, occurred_at, payload, work_id=None, attempt_id=None, actor_role=None, event_version=1, previous_digest=None)` | every appended fact |
| `brain_kernel/contracts.py` | `MissionCharter` | frozen dataclass, positional: `schema_version(=1), mission_id, created_at, objective, acceptance_specs, repository_root, base_commit(40hex), target_branch, policy_fingerprint, role_registry_fingerprint, model_route_fingerprint, budget: Budget, external_grants, protected_branches, human_gates, status: MissionState` | charter payload for `mission.created` |
| `brain_kernel/contracts.py` | `WorkItem`, `WorkState`, `MissionState`, `Budget`, `ConstraintEnvelope`, `EffectIntent`, `RoleResult`, `ContextManifest`, `EvaluationResult`, `TechnicalCloseoutReport`, `TechnicalCloseoutState` | see file; `Budget(max_wall_seconds, max_model_calls, max_input_tokens, max_output_tokens, max_cost_microunits, max_tool_calls, max_work_items, max_depth)` | typed contracts; ids must match `MISSION-…`/`WORK-…`/`ATTEMPT-…` regexes |
| `brain_kernel/planner.py` | `OrchestratorPlanner.plan`; `WorkSchedule`; `persist_plan`; `orchestration_plan_from_events` | `plan(self, charter, work_items: Iterable[WorkItem], schedules: Iterable[WorkSchedule]) -> OrchestrationPlan`; `WorkSchedule(work_id, budget: Budget, risk_lane, stop_conditions(≥1), consultation_roles(≥2, excluding the item role), human_gates ⊆ charter.human_gates)`; `persist_plan(store, plan) -> tuple[int, ...]` (mission must be CREATED/PLANNING/READY/PAUSED); `orchestration_plan_from_events(charter, events) -> OrchestrationPlan` | plan build, one schedule per item, durable `work.created` events, replay rehydration |
| `brain_kernel/objectives.py` | `ObjectiveGraph` | validates: charter `acceptance_specs` ⊆ union of item `acceptance_specs`; overlapping write scopes require a dependency; depth = parent depth + 1 when `parent_work_id` set | plan graph invariants |
| `brain_kernel/roles.py` | `KERNEL_IMPLEMENTED_ROLES` | `("orchestrator","explorer","architect","builder","curator","integrator","steward","optimizer")` | canonical lifecycle order |
| `brain_kernel/roles.py` | `RoleInvocation`; `append_role_result`; `result_digest` | `RoleInvocation(mission_id, work_id, attempt_id, role, executor_id, context: CompiledContext, authority_envelope_digest, evidence_refs(≥1), base_artifact_refs, candidate_artifact_refs)` (manifest ids/role/authority must bind); `append_role_result(store, result: RoleResult, *, occurred_at: str) -> int` (work must be RUNNING); `result_digest(result: RoleResult) -> str` | role input, durable `role.result`, digest rebind after adding effect receipts |
| `brain_kernel/role_runtime.py` | `RoleRuntime` | provider-backed async runtime (read-only reference) | do NOT call it in tests; the runner takes a `RoleExecutor` protocol so it can bind later |
| `cortex/repository/role_handlers.py` | `RepositoryRoleHandlers` | `roles() -> tuple[str,...]`; `execute(invocation: RoleInvocation) -> RoleResult` | the deterministic local executor the adapter binds; curator requires `evaluator_mode` + `generator_evaluator_separated` |
| `brain_kernel/context.py` | `ContextRequest`, `CompiledContext` | `ContextRequest(mission_id, work_id, attempt_id, role, charter_digest, authority_digest, token_budget, query, now, data_scopes, hot_items, repository_key=None, evaluator_mode=False, …)`; `CompiledContext(request, manifest, warm, cold, bindings=())` | deterministic fixture context (copy the construction pattern from `cortex/repository/local_execution.py:_context`) |
| `brain_kernel/consultation.py` | `ConsultationRequest`, `RoleAssessment`, `ConsultationLoop`, `ConsultationResult`, `ConsultationDecision`, `ConsultationReason` | `ConsultationLoop().append(request, assessments) -> tuple[ConsultationLoop, ConsultationResult]`; requesting role cannot be in `applicable_roles`; `human_escalation` True only for `TRUE_AUTHORITY_REQUIRED` | role-first consultation |
| `brain_kernel/authority.py` | `AuthorityRegistry`, `CapabilityToken`, `AuthorityDenied` | `register(envelope, parent=None)`; `authorize(digest, action, target, *, now) -> CapabilityToken` | the ONLY path to effect authorization |
| `brain_kernel/effects.py` | `EffectGateway` | `EffectGateway(store: KernelStore \| None = None)`; `register_adapter(name, adapter, *, version="1")`; `execute(intent, token) -> EffectResult(intent_digest, receipt_digest, status)` | with `store` set, routes through `DurableEffectOutbox` (durable, idempotent, ambiguity fails closed) |
| `brain_kernel/effect_outbox.py` | `EffectReconciliationRequired` | `class EffectReconciliationRequired(RuntimeError)` | surfaced, never swallowed |
| `cortex/repository/local_execution.py` | `LocalWorkspaceAdapter` | `LocalWorkspaceAdapter(root)`; `register_payload(content: bytes) -> str`; `materialize(source, target) -> Path`; `apply(intent: EffectIntent) -> None` (requires `action=="write"`, `target_adapter=="isolated-write"`) | the root-confined write adapter the mission adapter registers |
| `cortex/repository/builder_adapter.py` | `IsolatedBuilderAdapter` | `adapter_name = "isolated-builder"`; `register_action(action) -> str`; `apply(intent) -> Mapping` | read-only reference; NOT required for this node (the fixture uses `LocalWorkspaceAdapter`) |
| `brain_kernel/verification.py` | `create_evaluation_plan`; `seal_evaluation_plan` | `(plan_id, base_root, *, acceptance_commands, allowed_paths) -> EvaluationPlan`; `(store, work_id, plan, *, base_root, actor_id) -> int` | plan sealed from base BEFORE candidate access; appends `evaluation.plan.sealed` (reducer: work RUNNING, actor_role architect, one plan per work) |
| `brain_kernel/verification.py` | `verify_exact_candidate` | `(store, work_id, plan, candidate_root, *, builder_id, evaluator_id, check_runner: Callable[[str, Path], bool], bundle_directory) -> VerificationOutcome(result, bundle_path, changed_paths)` | appends `evaluation.result` (reducer: work AWAITING_VERIFICATION, actor curator, `builder_id != evaluator_id`) |
| `brain_kernel/verification.py` | `accept_verified_work`; `ExactCandidateVerificationError` | `(store, work_id, result, *, actor_id) -> int`; `class …(RuntimeError)` | ACCEPTED only via the exact recorded PASSED result; boundary tests |
| `brain_kernel/closeout.py` | `declare_closeout_obligations`; `record_evaluation_bundle`; `integrate_verified_work` | `(store, mission_id, *, required_roles=KERNEL_IMPLEMENTED_ROLES, historical_evidence=(), actor_id=…) -> int`; `(store, work_id, result, bundle_directory, *, bundle_ref, actor_id=…) -> int` (work must still be AWAITING_VERIFICATION); `(store, work_id, result, *, actor_id=…) -> int` | obligations event; bundle binding; ACCEPTED → INTEGRATED |
| `brain_kernel/closeout.py` | `derive_technical_closeout` | `(store, mission_id, *, bundle_directories: Mapping[str, str \| Path] \| None = None) -> TechnicalCloseoutReport` | event-derived acceptance; require `TECHNICALLY_VERIFIED` |
| `brain_kernel/reconciler.py` | `DesiredStateReconciler`, `ObservedState`, `ReconciliationPolicy`, `ReconciliationResult`, `RepairAction`, `RepairKind` | `DesiredStateReconciler(policy=None).reconcile(observed: ObservedState \| Mapping, *, now: float) -> ReconciliationResult`; `ReconciliationResult.apply(handlers: Mapping[str \| RepairKind, Callable[[RepairAction], Any]]) -> tuple[str, ...]` | humanless repair (remand/retry/rebuild/quarantine, all bounded) |
| `brain_kernel/local_assurance.py`; `brain_kernel/court_runtime.py` | `build_local_assurance_report`, `verify_local_assurance_artifact`; `CourtHistory`, `record_case` | see files | read-only references; do NOT call or wire — cite in the doc only |

Hard reducer facts you must design around (`brain_kernel/projection.py`, read
only): work lifecycle `PROPOSED→READY→LEASED→RUNNING→AWAITING_VERIFICATION→
ACCEPTED→INTEGRATED`; mission lifecycle `CREATED→PLANNING→READY→RUNNING→
VERIFYING→INTEGRATING→COMPLETED`; `role.result` and `evaluation.plan.sealed`
require the work item RUNNING; `evaluation.result` and
`evaluation.bundle.recorded` require AWAITING_VERIFICATION; ACCEPTED requires
the recorded `passed_evaluation_digest`. There is NO consultation event type —
retain consultation by digest inside role-result evidence refs (below).

## 3. Design

### 3.1 `src/hive_mind_os/brain_kernel/mission_runtime.py` (new)

Imports: stdlib + `.authority`, `.canonical`, `.consultation`, `.contracts`,
`.context`, `.closeout`, `.effects`, `.events`, `.planner`, `.reconciler`,
`.roles`, `.store`, `.verification`. It must NOT import anything from
`hive_mind_os.cortex` (dependency direction: cortex → kernel only), must not
call a provider, and must not touch the filesystem except through the injected
verification specs/gateway.

```python
class MissionRuntimeError(RuntimeError):
    """The canonical mission lifecycle cannot proceed fail-open."""

class MissionEscalationRequired(MissionRuntimeError):
    """A genuine human authority class is required; carries .consultation."""
    def __init__(self, consultation: ConsultationResult) -> None: ...

class RoleExecutor(Protocol):
    def execute(self, invocation: RoleInvocation) -> RoleResult: ...

@dataclass(frozen=True, slots=True)
class MissionConfig:
    mission_id: str; objective: str
    acceptance_spec: str            # single charter acceptance id
    repository_root: str
    base_commit: str                # 40-hex; fixture uses "0"*40
    target_branch: str              # must not be protected
    occurred_at: str                # RFC 3339; injected constant => replayable
    charter_budget: Budget
    schedule_budget: Budget         # per-item; 8*consumptive <= charter (planner gate)
    executor_prefix: str = "mission"

@dataclass(frozen=True, slots=True)
class BuilderEffectBinding:
    registry: AuthorityRegistry
    gateway: EffectGateway          # built with the SAME KernelStore => durable outbox
    envelope_digest: str            # key registered in the registry
    intent: EffectIntent            # bound to the builder work/attempt ids
    authorization_time: str         # RFC 3339, before envelope expiry

@dataclass(frozen=True, slots=True)
class WorkVerificationSpec:
    base_root: str; candidate_root: str
    acceptance_commands: tuple[str, ...]
    allowed_paths: tuple[str, ...]  # becomes plan.allowed_test_paths
    check_runner: Callable[[str, Path], bool]
    bundle_directory: str           # must not exist yet; one per work item
    bundle_ref: str                 # RELATIVE, e.g. "bundle:WORK-…-builder"

@dataclass(frozen=True, slots=True)
class MissionBindings:
    role_executor: RoleExecutor
    builder_effect: BuilderEffectBinding
    verification: Mapping[str, WorkVerificationSpec]  # exactly the 8 role keys
    consultation_request: ConsultationRequest         # requesting_role="builder"
    consultation_assessments: tuple[RoleAssessment, ...]

@dataclass(frozen=True, slots=True)
class MissionRunReceipt:
    mission_id: str; charter_digest: str; plan_digest: str
    consultation: ConsultationResult
    consultation_digest: str                # canonical_digest(result.to_document())
    role_results: tuple[RoleResult, ...]    # eight, lifecycle order
    effect_receipt_digests: tuple[str, ...] # >=1 (builder write)
    evaluation_result_digests: Mapping[str, str]  # work_id -> result_digest
    bundle_refs: tuple[str, ...]            # relative refs only => replayable
    closeout: TechnicalCloseoutReport
    event_head_digest: str; projection_digest: str
    def to_document(self) -> dict[str, object]: ...
    @property
    def receipt_digest(self) -> str: ...    # canonical_digest(to_document())

@dataclass(frozen=True, slots=True)
class MissionReplayEvidence:
    event_head_digest: str; projection_digest: str
    rebuilt_projection_digest: str; closeout_report_digest: str

class MissionRuntime:
    def __init__(self, store: KernelStore) -> None: ...
    def run(self, config: MissionConfig, bindings: MissionBindings) -> MissionRunReceipt: ...
    def repair_pass(self, mission_id: str, *, now: float,
                    observed_overrides: Mapping[str, Any] | None = None,
                    policy: ReconciliationPolicy | None = None) -> ReconciliationResult: ...
    def replay(self, mission_id: str, *,
               bundle_directories: Mapping[str, str | Path]) -> MissionReplayEvidence: ...
```

**`run()` control flow (exact order; each numbered step is a store append or
composition call — nothing else). `Z = "sha256:" + "0"*64` throughout:**
1. Validate: `bindings.verification` keys == set of `KERNEL_IMPLEMENTED_ROLES`;
   `consultation_request.requesting_role == "builder"` with `applicable_roles`
   drawn from `("curator","integrator","steward","optimizer")`.
2. `charter = MissionCharter(1, mission_id, occurred_at, objective,
   (acceptance_spec,), repository_root, base_commit, target_branch, Z, Z, Z,
   charter_budget, (), ("main",), (), MissionState.CREATED)`. Append
   `mission.created` (payload `{"charter": charter.to_document()}`, actor
   `f"{prefix}:orchestrator"`, actor_role `"orchestrator"`), then
   `mission.transition` → `PLANNING`.
3. Eight `WorkItem`s: `work_id=f"WORK-{mission_id.removeprefix('MISSION-')}-{role}"`,
   `parent_work_id=None`, `depth=0`, `risk_tier="R1"`, `dependencies=`
   previous work_id (lifecycle chain), `acceptance_specs=(acceptance_spec,)`
   and `write_scope=("candidate/app.txt",)` on the builder item only (others
   `()`), `status=WorkState.PROPOSED`, `authority_envelope_digest=Z`,
   `idempotency_key=canonical_digest({"work_id": work_id})`,
   `context_request={"role": role}`, `max_attempts=2`. Eight `WorkSchedule`s:
   `risk_lane="R1"`, `stop_conditions=("mission-runtime-bounded",)`,
   `consultation_roles=` two of `("curator","integrator","steward","optimizer")`
   excluding the item role, `human_gates=()`, `budget=schedule_budget`.
   `persist_plan(self.store, OrchestratorPlanner().plan(charter, items, schedules))`.
4. `declare_closeout_obligations(self.store, mission_id, actor_id=f"{prefix}:orchestrator")`.
5. `mission.transition` → `READY`, then → `RUNNING`.
6. Consultation (criterion 2): `loop, result = ConsultationLoop().append(
   bindings.consultation_request, bindings.consultation_assessments)`.
   If `result.human_escalation` or `result.decision is not
   ConsultationDecision.RESOLVED`: raise `MissionEscalationRequired(result)` —
   the runner NEVER answers a genuine authority class itself.
   `consultation_ref = "consultation:" + canonical_digest(result.to_document())`.
7. Per role in `KERNEL_IMPLEMENTED_ROLES` order, `spec = verification[role]`:

| 7. | Exact call | Gate satisfied |
|---|---|---|
| a | three `work.transition` appends PROPOSED→READY→LEASED→RUNNING, actor `f"{prefix}:orchestrator"`, actor_role `"orchestrator"` | reducer `_WORK_NEXT` chain |
| b | `plan_k = create_evaluation_plan(f"PLAN-{work_id}", spec.base_root, acceptance_commands=spec.acceptance_commands, allowed_paths=spec.allowed_paths)`; `seal_evaluation_plan(self.store, work_id, plan_k, base_root=spec.base_root, actor_id=f"{prefix}:architect")` | seal requires work RUNNING + architect actor; one plan per work |
| c | builder only: `token = registry.authorize(envelope_digest, intent.action, intent.target, now=authorization_time)`; `effect = gateway.execute(intent, token)` | durable outbox receipt; token binds exact intent target |
| d | build deterministic `CompiledContext` via private `_context` helper copied from `local_execution._context` (`evaluator_mode` and `generator_evaluator_separated` True only for curator; `authority_digest=Z`; `manifest_digest=canonical_digest({"role": role, "attempt": attempt_id})`); `invocation = RoleInvocation(mission_id, work_id, f"ATTEMPT-…-{role}", role, f"{prefix}:{role}", context, Z, evidence_refs=(consultation_ref,)` for builder else `("charter:"+charter.digest(),)`, `base_artifact_refs=("workspace:base",), candidate_artifact_refs=("workspace:candidate",))`; `result = bindings.role_executor.execute(invocation)`; builder only: rebind `effect_receipt_refs=(effect.receipt_digest,)` via `RoleResult(**{**asdict(result), "effect_receipt_refs": …, "result_digest": Z})` then recompute with `roles.result_digest` (the `local_execution._with_receipt` idiom — copy, never import); `append_role_result(self.store, result, occurred_at=config.occurred_at)` | `role.result` requires work RUNNING; executor/actor/attempt bindings enforced by reducer |
| e | `work.transition` → `AWAITING_VERIFICATION` | prerequisite for f/g |
| f | `outcome = verify_exact_candidate(self.store, work_id, plan_k, spec.candidate_root, builder_id=result.executor_id, evaluator_id=f"{prefix}:curator:evaluator", check_runner=spec.check_runner, bundle_directory=spec.bundle_directory)`; if `outcome.result.state is not EvaluationState.PASSED` raise `MissionRuntimeError` | exact-candidate verification; distinct builder/evaluator; fail closed |
| g | `record_evaluation_bundle(self.store, work_id, outcome.result, spec.bundle_directory, bundle_ref=spec.bundle_ref, actor_id=f"{prefix}:curator:evaluator")` | bundle binds while still AWAITING_VERIFICATION |
| h | `accept_verified_work(self.store, work_id, outcome.result, actor_id=f"{prefix}:integrator")` → ACCEPTED, then `integrate_verified_work(self.store, work_id, outcome.result, actor_id=f"{prefix}:integrator")` → INTEGRATED | ACCEPTED requires recorded `passed_evaluation_digest` |
8. `mission.transition` RUNNING→`VERIFYING`→`INTEGRATING`→`COMPLETED`.
9. `closeout = derive_technical_closeout(self.store, mission_id,
   bundle_directories={spec.bundle_ref: spec.bundle_directory for each role})`;
   if `closeout.state is not TechnicalCloseoutState.TECHNICALLY_VERIFIED`,
   raise `MissionRuntimeError` listing `closeout.missing_obligations`.
10. Return `MissionRunReceipt` (head digest = `store.events()[-1]["digest"]`,
    projection digest = `canonical_digest(store.projection())`).

Internal helper `_append(event_type, payload, *, event_id, actor_id,
actor_role=None, work_id=None, attempt_id=None, idempotency_key=None)` reads
`store.events()` and chains `previous_digest` (the
`role_handlers._append_fixture_event` pattern). All `occurred_at` values are
`config.occurred_at` — replay determinism depends on injected time.

**`repair_pass()`** builds an `ObservedState` document from
`store.projection()` (`mission_id`, `mission_status`, work records with
`work_id/mission_id/status/attempts`), merges `observed_overrides`
(leases/workspaces/provider_failures/no_progress from adapter probes) on top,
and returns `DesiredStateReconciler(policy).reconcile(document, now=now)`. It
executes nothing; callers apply handlers via `ReconciliationResult.apply`.

**`replay()`** captures `before = canonical_digest(store.projection())`, calls
`store.rebuild_projections()` to discard the derived views and re-materialize
them from sequence one, then compares `after = canonical_digest(store.projection())`
against `before` (mismatch → `MissionRuntimeError`), re-derives
`derive_technical_closeout(...)` and returns the four digests as
`MissionReplayEvidence`, with `rebuilt_projection_digest = after`.

Do **not** digest the value `rebuild_projections()` returns. It returns the full
reduced state, whose work entries accumulate `evaluation_plan_digest` and
`passed_evaluation_digest` (`projection.py` `reduce_event`), while `projection()`
rehydrates only `mission_id`/`status` from the `work_projection` table
(`store.py:650`). After any mission that seals an evaluation plan and records a
passed evaluation — which this node's own `run()` flow requires before ACCEPTED —
those two digests differ by construction, and nothing inside this node's write
scope can reconcile them. Reading the digest off `projection()` on both sides is
both satisfiable and the stronger claim: it proves the materialized read model
survives a full replay byte-identically. `append()` already ends in a full
rebuild (`store.py:320`), so `before` is itself a replay product and the equality
is a genuine determinism check, not a tautology.

### 3.2 `src/hive_mind_os/cortex/repository/mission_adapter.py` (new)

Imports: stdlib, `...brain_kernel.*` (authority, canonical, consultation,
contracts, effects, mission_runtime, reconciler, store), and
`.local_execution` (`LocalWorkspaceAdapter`), `.role_handlers`
(`RepositoryRoleHandlers`). Constants: `_Z = "sha256:" + "0"*64`,
`_SHA = "0"*40`, `_TIME = "2026-08-11T00:00:00Z"`,
`_AUTH_TIME = "2029-01-01T00:00:00Z"`, envelope expiry `"2030-01-01T00:00:00Z"`.

```python
class MissionAdapterError(RuntimeError): ...

class LocalMissionEnvironment:
    """Owns root, store, workspace adapter, registry, gateway, config, bindings."""
    root: Path; store: KernelStore; workspace: LocalWorkspaceAdapter
    registry: AuthorityRegistry; gateway: EffectGateway
    config: MissionConfig; bindings: MissionBindings
    bundle_directories: dict[str, Path]     # bundle_ref -> absolute dir
    def close(self) -> None: ...            # store.close()

def build_local_mission_environment(
    root: str | Path, *, mission_suffix: str = "local",
    store: KernelStore | None = None) -> LocalMissionEnvironment: ...

def run_local_mission(root: str | Path, *,
    mission_suffix: str = "local") -> tuple[MissionRunReceipt, LocalMissionEnvironment]: ...

def rebuild_candidate_workspace(environment: LocalMissionEnvironment) -> Path: ...

def repair_handlers(environment: LocalMissionEnvironment
    ) -> dict[RepairKind, Callable[[RepairAction], None]]: ...
```

`build_local_mission_environment` does exactly:

| # | Construction (exact values) |
|---|---|
| 1 | `root/base` mkdir, write `app.txt` = `"before\n"`; `workspace = LocalWorkspaceAdapter(root)`; `workspace.materialize(root/"base", "candidate")` |
| 2 | `store = store or KernelStore(root / "kernel.sqlite3")` |
| 3 | Builder envelope — copy the `local_execution._builder_envelope` field pattern (do NOT import the private name): `ConstraintEnvelope("AUTH-mission-<suffix>", mission_id, builder_work_id, None, "builder", "R1", ("write",), ("network","push","merge","deploy"), ("candidate",), ("candidate",), (), (), (), (), Budget(1,0,0,0,0,1,1,1), "2030-01-01T00:00:00Z", _Z, _Z)`; `registry.register(envelope)` (registry keys by `digest_value == _Z`, same as the existing fixture) |
| 4 | `gateway = EffectGateway(store)`; `gateway.register_adapter("isolated-write", workspace.apply)`; `parameters_digest = workspace.register_payload(b"after\n")`; `EffectIntent(mission_id, builder_work_id, builder_attempt_id, "mission:builder", "builder", "write", "R1", "isolated-write", "candidate/app.txt", parameters_digest, canonical_digest({"mission": mission_id, "effect": "builder-write"}), _Z, (), "discard isolated candidate", "local-mission-policy", canonical_digest({"intent": mission_id}))` |
| 5 | Verification specs: every role gets `base_root=candidate_root=str(root/"candidate")`, `acceptance_commands=("local-check",)`, `allowed_paths=("app.txt",)`, `check_runner` returning True — EXCEPT builder: `base_root=str(root/"base")`, `check_runner` = read `root/"candidate"/"app.txt" == "after\n"`. All: `bundle_directory=str(root/"bundles"/work_id)`, `bundle_ref=f"bundle:{work_id}"`. Ordering fact: builder seals against pristine `base` and verifies the mutated `candidate`; roles before/after builder seal AND verify the same `candidate` state (no diff), so every diff set is exact |
| 6 | Consultation fixture: `ConsultationRequest("CONSULT-<suffix>-1", mission_id, "Which exact candidate content satisfies the acceptance check?", ConsultationReason.AMBIGUOUS_DESIGN, "builder", ("curator","integrator"))`; two `RoleAssessment`s (roles curator/integrator, identities `mission:curator:consult` / `mission:integrator:consult`, `answer="write after\\n to candidate/app.txt"`, `evidence_refs=("fixture:consultation-evidence",)`, `proposed_decision=ConsultationDecision.RESOLVED`) |
| 7 | `bindings.role_executor = RepositoryRoleHandlers()`; `config = MissionConfig(mission_id=f"MISSION-{mission_suffix}", …, base_commit=_SHA, target_branch="candidate/local-mission", occurred_at=_TIME, charter_budget=Budget(400,16,800,800,800,40,12,4), schedule_budget=Budget(50,2,100,100,100,5,1,1), repository_root="local-fixture")` |

`repair_handlers` returns exactly three bounded handlers:
`RepairKind.REBUILD_WORKSPACE` → delete-if-exists then
`rebuild_candidate_workspace` (re-`materialize` from `base`);
`RepairKind.RELEASE_STALE_LEASE` → record the release in an environment-local
list (leases are runner-local; there is no lease event type);
`RepairKind.RETRY` → no-op record (the durable outbox already makes the
builder effect an idempotent retry). NO handler for `QUARANTINE`/`ROLLBACK` —
missing handlers are a safe no-op per `ReconciliationResult.apply`, and
quarantine must never be silently "handled".

**What "a failed candidate never accepts" can mean.** `run()` walks
`KERNEL_IMPLEMENTED_ROLES` in order, and `orchestrator`, `explorer`, and
`architect` complete before `builder`. Each verifies its *own* candidate
through `verify_exact_candidate` and passes honestly, so each is ACCEPTED
before the builder's check ever runs. Asserting that the store holds **zero**
ACCEPTED transitions therefore forbids acceptances that were genuinely earned,
and no implementation inside this node's write scope can satisfy it while only
the builder's `check_runner` returns False.

The satisfiable invariant, which is also the sharper one, is that the
candidate that FAILED verification is never accepted and never carries the
mission to completion: the builder's work item has no ACCEPTED transition, and
the mission projection never reads `COMPLETED`. That preserves the sealed
acceptance criterion ("No role or model self-approves, fabricates authority, or
bypasses exact-candidate verification") exactly — it pins the failing candidate
by name instead of making a global claim that real, honest work violates.

Verified 2026-08-12: with only the builder's runner failing, the accepted work
items are `WORK-<suffix>-{orchestrator,explorer,architect}`, the builder's is
absent, and the mission projection stays `RUNNING`.

### 3.3 `docs/execution/CANONICAL_MISSION_RUNTIME.md` (new)

One page: the ten-step lifecycle as a table (step → event types → reducer
gate); the closed event-schema statement; the escalation contract
(`MissionEscalationRequired` is the ONLY human hand-off, consultation first);
the authority statement (effects only via `AuthorityRegistry` token +
`EffectGateway(store)` outbox); replay guarantees (injected time, relative
refs, deterministic digests); what the runner NEVER does (no provider calls
in the local suite, no push/merge/deploy, no new event types, no
self-approval; `RoleRuntime` binds later via the `RoleExecutor` protocol).

## 4. Implementation order (small commits on `autopilot/mission-400`)

1. `mission_runtime.py`: errors, `RoleExecutor`, all section-3.1 dataclasses.
2. `MissionRuntime._append` + steps 1–5 of `run()` (charter, plan, closeout
   obligations, mission transitions).
3. Steps 6–10 of `run()` (consultation gate, per-role loop, closeout, receipt).
4. `repair_pass()` and `replay()`.
5. `mission_adapter.py`: environment builder, `run_local_mission`,
   `rebuild_candidate_workspace`, `repair_handlers`.
6. `tests/test_hive_cortex_mission_runtime.py` (section 5); focused command green.
7. `docs/execution/CANONICAL_MISSION_RUNTIME.md`.
8. Push branch, open draft PR to `main`, run `autopilot complete` per your
   rendered prompt, push the durable receipt commit. STOP.

## 5. Test plan — `tests/test_hive_cortex_mission_runtime.py`

Conventions (match `tests/test_hive_cortex_orchestrator.py`):
`unittest.TestCase`; constants `DIGEST = "sha256:" + "0"*64`, `SHA = "0"*40`,
`TIME = "2026-08-11T00:00:00Z"`; `tempfile.TemporaryDirectory` +
`addCleanup(environment.close)`; import by full module path
(`hive_mind_os.brain_kernel.mission_runtime`,
`hive_mind_os.cortex.repository.mission_adapter`).

Focused command (the ONLY test command this node runs):

```
PYTHONPATH=src python -m unittest tests.test_hive_cortex_mission_runtime -v
```

| required_tests name | Test class | Methods (minimum) |
|---|---|---|
| `canonical-eight-role-e2e-tests` | `CanonicalEightRoleEndToEndTests` | `test_single_objective_runs_all_eight_roles_with_typed_outputs_and_receipts` (roles of `receipt.role_results` == `KERNEL_IMPLEMENTED_ROLES`; every `result_digest` re-verifies via `roles.result_digest`; builder result has a non-empty `effect_receipt_refs`; projection shows mission COMPLETED and all eight work items INTEGRATED; `receipt.closeout.state is TechnicalCloseoutState.TECHNICALLY_VERIFIED`); `test_consultation_resolves_before_any_escalation` (`receipt.consultation.decision is RESOLVED`, `human_escalation is False`, and the builder `role.result` event payload's evidence includes `receipt.consultation_digest` ref); `test_genuine_authority_escalates_instead_of_self_approving` (bindings with `ConsultationReason.MISSING_EXTERNAL_AUTHORITY`, `authority_class="credential_or_secret"`, assessments with `authority_required=True` and evidence → `MissionEscalationRequired`; afterwards the store contains ZERO `evaluation.result` and ZERO ACCEPTED transitions); `test_builder_effect_is_durable_and_idempotent` (`store.effect_entry(intent_digest=…)["state"] == "receipt_recorded"`; re-`execute` of the same intent+token returns the identical `receipt_digest`); `test_failed_candidate_never_accepts` (check_runner returning False → `MissionRuntimeError`; the **builder's** work item never reaches ACCEPTED and the mission never reaches COMPLETED — see §3.3) |
| `humanless-repair-tests` | `HumanlessRepairTests` | `test_missing_candidate_workspace_is_rebuilt_without_human_answers` (delete `root/candidate` before `run`; `repair_pass` with `observed_overrides={"workspaces": [{"workspace_id": "candidate", "exists": False, "work_id": builder_work_id}]}` proposes `REBUILD_WORKSPACE`; `result.apply(repair_handlers(env))` re-materializes; mission then completes; assert NO `WAITING_HUMAN` status anywhere in `store.events()` and `result.quarantined is False`); `test_stale_lease_is_released_and_work_marked_ready` (override with an expired lease → `RELEASE_STALE_LEASE` action and `desired_status == "READY"` for that work record); `test_exhausted_retry_budget_quarantines_not_escalates` (provider failure override with `attempts >= max_retries` → a `QUARANTINE` action, `quarantined is True`, and `apply` with the adapter handlers executes nothing for it); `test_no_progress_bound_quarantines` (`no_progress_count=3` → quarantine of the mission id) |
| `mission-replay-tests` | `MissionReplayTests` | `test_projection_rebuild_matches_live_projection` (`replay()` returns equal `projection_digest`/`rebuilt_projection_digest`, both read from `projection()` on either side of `rebuild_projections()` — never from that call's return value; see §3.1); `test_two_runs_from_identical_inputs_reproduce_the_event_head` (two fresh roots, same `mission_suffix` → identical `event_head_digest`, identical `closeout.report_digest`, identical `receipt.receipt_digest`); `test_orchestration_plan_rehydrates_exactly` (`orchestration_plan_from_events(charter, store.events()).digest == receipt.plan_digest`); `test_closeout_rederivation_is_deterministic` (call `derive_technical_closeout` twice with the environment's `bundle_directories`; equal `report_digest`) |
| `authority-boundary-tests` | `AuthorityBoundaryTests` | `test_effect_outside_write_scope_is_denied` (`registry.authorize(_Z, "write", "base/app.txt", now=…)` → `AuthorityDenied`); `test_capability_token_must_bind_the_exact_intent` (authorize a DIFFERENT allowed target, present it with the builder intent → `AuthorityDenied` from `validate_capability_token` inside `gateway.execute`); `test_builder_cannot_evaluate_its_own_candidate` (`verify_exact_candidate` with `builder_id == evaluator_id` → `ExactCandidateVerificationError`); `test_acceptance_requires_the_recorded_passed_result` (`accept_verified_work` with a FAILED or unrecorded `EvaluationResult` → `ExactCandidateVerificationError`); `test_curator_requires_evaluator_isolated_context` (curator `RoleInvocation` with `evaluator_mode=False` → `RoleProtocolError` from `RepositoryRoleHandlers.execute`); `test_requesting_role_cannot_consult_itself` (`ConsultationRequest(..., requesting_role="builder", applicable_roles=("builder","curator"))` → `ValueError`); `test_unknown_event_types_are_rejected_by_the_spine` (`store.append` of a `KernelEvent` with `event_type="mission.self_approved"` raises — the reducer schema is closed) |

Edge cases folded into the above: `MissionBindings.verification` missing a
role → `MissionRuntimeError` before any append; bundle directory reuse →
`ExactCandidateVerificationError`; candidate mutated after snapshot → FAILED.
Do NOT run `python -m unittest discover`, pytest, or any other test module.

## 6. Acceptance self-check → receipt evidence

| Criterion | Demonstrated by | Receipt evidence |
|---|---|---|
| All eight roles, typed outputs and receipts | `run()` step 7 over `KERNEL_IMPLEMENTED_ROLES`; `MissionRunReceipt.role_results` + builder effect receipt | `test_single_objective_runs_all_eight_roles_…` pass line |
| Role-first consultation before human escalation | step 6 gate; `MissionEscalationRequired` is the only human hand-off | `test_consultation_resolves_…` and `test_genuine_authority_escalates_…` pass lines |
| Effects/verification/remand/integration/operations/optimization event-derived | every state change is a spine event of an existing type; closeout and replay recompute from events only; remand proposals derive from projection via `repair_pass` | `MissionReplayTests` pass lines; `derive_technical_closeout` state in receipt |
| Routine reversible work without discretionary human answers | `HumanlessRepairTests` complete the mission with zero `WAITING_HUMAN` states and zero human gates | `humanless-repair` pass lines |
| No self-approval / fabricated authority / verification bypass | `AuthorityBoundaryTests` (distinct evaluator, token binding, closed event schema, recorded-passed-result gate) | `authority-boundary` pass lines |
| Evidence requirements | base + final commit SHAs, changed-path inventory == the four write-scope paths, exact focused-test transcript, role/authority identities from the receipt, consultation record digest, rollback ref = revert of the node commit | attach to node completion receipt via `autopilot complete` |

## 7. Out-of-scope traps (do NOT do these)

- Do NOT edit ANY existing file — `projection.py` (closed event schema),
  `verification.py`, `closeout.py`, `planner.py`, `reconciler.py`, `roles.py`,
  `role_handlers.py`, `local_execution.py`, `builder_adapter.py`, and
  `cortex/repository/__init__.py` are read-only. If an existing gate
  contradicts this design, `autopilot fail` with a blocker; never "fix" it.
- Do NOT invent new kernel event types, authority classes, work/mission
  states, or a parallel receipt store — compose the nine event types and the
  existing outbox only.
- Do NOT import private underscore names (`_builder_envelope`, `_context`,
  `_with_receipt`, `_append_fixture_event`, `_IDS`) — copy the small idioms
  into your own private helpers.
- Do NOT call `ModelBackend`, `RoleRuntime.execute`, or any provider in the
  local suite; the `RoleExecutor` protocol is the later binding point. Do NOT
  wire the CLI, `local_assurance`, `court_runtime`, `workers.KernelWorker`, or
  the legacy mission runtime — cite them in the doc, leave them untouched.
- Do NOT let the runner auto-handle `QUARANTINE`/`ROLLBACK` repair actions,
  auto-answer `TRUE_AUTHORITY_REQUIRED`, or accept a FAILED/ABSTAINED
  evaluation — all three must fail closed.
- Do NOT put absolute paths, wall-clock times, or platform path separators
  into any event payload or receipt document (replay tests catch this; use
  `normalize_portable_path` semantics and injected times).
- Do NOT touch `.autopilot/**`, the release branch, forbidden_scope files, any
  `__init__.py`/`conftest.py`/`pyproject.toml`; do NOT rebase/squash/amend the
  node branch, run repo-wide discovery, or merge the draft PR. Stop at the
  draft PR + durable receipt commit.
