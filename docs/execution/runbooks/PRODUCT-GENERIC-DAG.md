# PRODUCT-GENERIC-DAG — Standard-conforming DAG generation (A) and runtime token economy (B)

Read this runbook plus your rendered prompt only. Do not re-read
`.autopilot/plan.json` (it is SEALED and fingerprint-bound — read-only, never
edited), `.autopilot/README.md`, or policy files. The wave protocol is
`docs/execution/runbooks/README.md`.

**Why this runbook exists.** Hive Mind OS is a generic product: anyone clones it
and points `hive-mind autopilot init` at their own repository
(`docs/execution/PORTABLE_AUTOPILOT.md`). Its GenericPrompt/BUILD_DAG flow
builds a dependency DAG for an *arbitrary* repository and then executes it. A
long debugging session on this repository's own DAG surfaced six defects that
are **not** specific to this repository — any generated DAG would have them.
They were fixed here *operationally* in `docs/execution/runbooks/README.md`
(round splitting, explicit `--node` waves, per-round validation, prompt-as-
contract, R2A/R2B durability ordering). Operational fixes do not travel to
someone else's clone. This runbook specifies the **product-code** changes that
make the generic behavior real, in two packages:

| Package | Makes generic | Target files |
|---|---|---|
| **A** | *Generated* DAGs conform to a published standard and are linted before the build task may report success | `src/hive_mind_os/autopilot_workflow.py`, `tests/test_autopilot_workflow.py`, `docs/execution/DAG_AUTHORING_STANDARD.md` (authored by another agent — read-only here) |
| **B** | *Executing* a DAG costs a bounded, measured number of tokens per mission on any repository | `src/hive_mind_os/brain_kernel/role_runtime.py`, `src/hive_mind_os/model_backend.py`, two new modules, their tests, one doc |

The six generic lessons, and where each is answered:

| # | Lesson (repo-independent) | Answered by |
|---|---|---|
| 1 | **Scaffold collision.** Two same-level nodes declared disjoint `write_scope`s but both had to create the same package scaffold file (`tests/hive_cortex/__init__.py`) that was in NEITHER scope. Static file-lock overlap (`.autopilot/bin/release_barrier.py:244` `_nodes_conflict`) cannot see a file no node declared. | Standard §scaffold-ownership + `dag-lint` rule, required by the Package A prompt |
| 2 | **Universal read scopes.** `read_scope` of `**` or `src/**` invites a worker to read the entire repository. Globs are not banned — some repos need a discovery pass — but cold expansion must be budgeted and RECORDED. | Standard §read-scope + `dag-lint` rule (Package A); runtime enforcement by budgeted cold retrieval (Package B, §4.3) |
| 3 | **Durability ordering.** A node whose acceptance asserts crash/restart/resume/interruption/replay recovery, or that performs external effects (push/PR/comment/deploy), cannot be honestly proven before a durability node exists. Here `HUMANLESS-430` ("mission resumes after interruption without restating context") and `DELIVERY-420` sat at the SAME BFS level as `DURABLE-410`. | Standard §durability-ordering + `dag-lint` rule (Package A) |
| 4 | **Serial nodes inside parallel levels.** A BFS dependency level is NOT an executable wave. Greedy selection (`release_barrier.py:350-372`, the `else:` branch opening `wave = []` / `ordered = sorted(` at `:351-352`) appends the highest-priority node first and then *skips every other node* if that first node is `parallel_safe: false` — `if not bool(self.node(node_id).get("parallel_safe")): continue` at `:364-365` and the `if any(not bool(self.node(chosen).get("parallel_safe")) for chosen in wave): continue` guard at `:366-370`, capping the wave at one session. | Standard §round-compilation + `dag-lint` rule (Package A) |
| 5 | **Per-round validation.** Repository-wide validation must run once per round (integrator), not once per node, or N parallel workers serialize on one validation lease. | Standard §validation-ownership (Package A) |
| 6 | **Prompt-as-contract.** The rendered worker prompt must BE the node contract; workers must not re-read the plan file (~18.5K tokens measured here) because the controller enforces every gate deterministically anyway. | Standard §prompt-as-contract (Package A) + measured token ledger (Package B, §4.5) |

Package A makes the *generator* produce DAGs bound to the standard and gated on
`dag-lint`. Be precise about the strength of that claim: `dag-lint` mechanically
catches the subset of defects 1-6 that is mechanizable (see the standard's §8
enforcement table), and the rest remain author-verified requirements the prompt
imposes. Package B makes *executing* any such DAG affordable. Neither is
repo-specific.

**Implementation status.** Package A is a specification in this runbook. It is
**not implemented**: `src/hive_mind_os/autopilot_workflow.py` carries no standard
pin and the shipped DAG-build prompt (`:1009-1022`, quoted verbatim in §2.1) does
not name the standard. Package B is likewise unimplemented and, per §1.3, not
currently dispatchable. Do not cite either as an existing capability.

---

## 1. Contract summary

### 1.1 Package A — BUILD_DAG emits standard-conforming DAGs

**Objective.** The bootstrap contract emitted for an uninstalled repository must
(a) bind the DAG-build task to `docs/execution/DAG_AUTHORING_STANDARD.md` by
**digest**, so a built DAG is provably bound to the standard version it was
authored against, and (b) forbid the DAG-build task from reporting success until
`autopilot dag-lint` returns zero errors against the DAG it built.

**Acceptance criteria.**

| # | Criterion |
|---|---|
| A1 | `initialize_repository` pins the authoring standard by path + sha256 + byte length + standard version, materializes it inside the target repository under `.hive-mind/`, and fails closed if the packaged standard is missing or its bytes do not match the pin. |
| A2 | The bootstrap contract returned by `_uninstalled_contract` carries that pin as a top-level `dag_authoring_standard` object, and the contract id covers it. |
| A3 | The DAG-build task prompt names the standard's local path and digest, requires conformance, and requires `dag-lint` zero-error exit *before* success may be reported. |
| A4 | A persisted request that predates the standard fails closed with a remediation message; it is never silently treated as standard-bound. |
| A5 | `tests/test_autopilot_workflow.py` is updated to the new contract shape and pins the standard digest freshness; no test weakens or bypasses a digest check. |

**Scope table.**

| Kind | Paths |
|---|---|
| write_scope | `src/hive_mind_os/autopilot_workflow.py`, `tests/test_autopilot_workflow.py`, `docs/execution/PORTABLE_AUTOPILOT.md` (one new subsection only) |
| read_scope | `src/hive_mind_os/autopilot_workflow.py`, `tests/test_autopilot_workflow.py`, `docs/execution/DAG_AUTHORING_STANDARD.md` (read-only — another agent owns it) |
| forbidden | `.autopilot/**` (SEALED — `plan.json` read-only, controller bundle owned elsewhere), any `__init__.py`, any `conftest.py`, `pyproject.toml`, `.github/CODEOWNERS`, `.github/governance/**`, `evidence/courts/**`, `docs/architecture/HARDENED_VISION_CONTRACT.md`, `docs/execution/DAG_AUTHORING_STANDARD.md` (read-only) |

**Shared-file warning (lesson 1, live).** `docs/execution/PORTABLE_AUTOPILOT.md`
is a *shared* doc that other work also edits — at the time this runbook was
written it already showed uncommitted modifications from a concurrent agent.
Package A appends exactly one new subsection (§3.6) and must not reflow,
reorder, or rewrite anything else in that file. If a node contract does not name
`PORTABLE_AUTOPILOT.md` in its `write_scope`, drop §3.6 from the package and
record the documentation gap in the receipt rather than writing outside scope —
that is precisely the unowned-shared-file failure this runbook exists to
generalize away.

**Cross-agent dependency.** `docs/execution/DAG_AUTHORING_STANDARD.md` exists at
exactly that path and is owned by another agent, who may still revise it. Package
A depends only on its **path and bytes**, never on its prose — so re-read and
re-pin its sha256 and byte length as the last step before the PR (§5 step 6). Do
not edit it, do not create a second copy, and do not inline a summary of it into
`autopilot_workflow.py`.

**`autopilot dag-lint` is a *generated-controller* command.** In a target
repository the DAG-build task creates `.autopilot/bin/autopilot.py`. The prompt
therefore requires the **generated** controller to implement `dag-lint` per the
standard and to exit zero. This repository's own `.autopilot/bin/` has *already*
gained `dag-lint` and `dag-rounds` through a separate, non-product deliverable
owned by another agent (`.autopilot/bin/dag_standard.py`); Package A must neither
read nor depend on it. New subcommands are wired exactly as in
`.autopilot/bin/autopilot.py:660` `def parser() -> argparse.ArgumentParser` →
`commands.add_parser(...)` → dispatch in `main()` (`:866`) — that is the pattern
the standard describes, not something Package A implements.

Line citations in this runbook drift whenever the controller bundle changes; each
one below quotes its anchor symbol or source line so it can be re-found with
`grep` rather than trusted blindly. Re-verify before relying on a number.

### 1.2 Package B — runtime token economy

**Objective.** Stop paying eight full model calls with quadratic prior-result
accumulation and character-truncated context for every mission on every
repository. Preserve full eight-role lifecycle accountability.

**The measured problem (all three facts verified in this checkout):**

1. `src/hive_mind_os/brain_kernel/role_runtime.py:168` runs all eight roles
   serially and hands **every** prior result to every later role:
   ```python
   results.append(await self.execute(invocation, prior_results=tuple(results)))
   ```
   Role *k* receives *k* prior results, so a mission delivers
   `0+1+2+…+7 = 28` accumulated prior-result payloads.
2. Those payloads are rendered into the prompt at
   `src/hive_mind_os/model_backend.py:266-279` and then truncated by an
   **8,000-character** budget, **oldest-first**, with no dependency awareness:
   ```python
   while prior_roles and len(rendered) > self.context_limit_chars:
       omitted_roles.append(str(prior_roles.pop(0)["role"]))
       rendered = _render_context(prior_roles, omitted_roles)
   ```
   `self.context_limit_chars` is the constructor default `context_limit_chars:
   int = 8000` (`model_backend.py:89`, validated at `:93`, stored at `:103`).
   Dropping oldest-first discards the orchestrator/explorer framing a builder
   actually depends on while retaining unrelated recent chatter.
3. Sidecar admission is calibrated by hardcoded constants rather than measured
   history (`.autopilot/bin/sidecar_execution.py:285-289`, verbatim — anchor line `if task.get("authority_mode") == "PREPARATION_ONLY" or scope_count >= 3:`):
   ```python
   if task.get("authority_mode") == "PREPARATION_ONLY" or scope_count >= 3:
       candidates.append(_candidate(parent_id, node_id, "bounded_read_only_research", f"Read-only sidecar for {node_id}. …", 4_800 + 250 * min(scope_count, 8), policy))
   if risk in {"moderate", "high", "critical"} or evidence_count >= 3:
       saved = {"moderate": 5_200, "high": 6_600, "critical": 7_800}.get(risk, 5_400) + 150 * min(evidence_count, 8)
   ```

**Acceptance criteria.**

| # | Criterion |
|---|---|
| B1 | Every role of `KERNEL_IMPLEMENTED_ROLES` resolves to exactly one disposition — `MODEL_EXECUTE`, `DETERMINISTIC_CHECK`, `NOT_APPLICABLE`, `DEFERRED`, `BLOCKED` — by task archetype, and every mission still produces eight evidence-bound, digest-verifiable `RoleResult`s in lifecycle order. A small task costs fewer than eight model calls without losing a single lifecycle account. |
| B2 | Context is dependency-routed: direct dependency roles get the full body, transitive get a digest/reference, unrelated are omitted and *named* as omitted; full evidence stays reachable by explicit, recorded cold retrieval. |
| B3 | The existing `ContextCompiler` (`src/hive_mind_os/brain_kernel/context.py:436`) is the only context system. No second budgeting/tiering/manifest mechanism is created. The change is connecting it to the model backend and role runtime. |
| B4 | Every model call records input+output tokens with an explicit measurement source (`MEASURED` / `ESTIMATED` / `UNAVAILABLE`) into the append-only ledger, and a deterministic calibration artifact is derivable from that history. |
| B5 | The 8,000-character oldest-first truncation is no longer the governing mechanism when a compiled envelope is supplied; it remains only as the unchanged legacy fallback for callers that supply none. |

**Scope table.**

| Kind | Paths |
|---|---|
| write_scope | `src/hive_mind_os/brain_kernel/role_applicability.py` (new), `src/hive_mind_os/token_ledger.py` (new), `src/hive_mind_os/brain_kernel/role_runtime.py`, `src/hive_mind_os/model_backend.py`, `tests/test_hive_cortex_role_applicability.py` (new), `tests/test_hive_cortex_token_economy.py` (new), `docs/execution/TOKEN_ECONOMY.md` (new) |
| read_scope | `src/hive_mind_os/brain_kernel/context.py`, `src/hive_mind_os/brain_kernel/roles.py`, `src/hive_mind_os/brain_kernel/contracts.py`, `src/hive_mind_os/ledger.py`, `src/hive_mind_os/model_provider.py` (all read-only) |
| forbidden | `.autopilot/**`, `src/hive_mind_os/brain_kernel/context.py` (read-only — do NOT edit; B3 forbids forking it), `src/hive_mind_os/brain_kernel/projection.py`, any `__init__.py`, any `conftest.py`, `pyproject.toml`, `tests/test_hive_cortex_role_runtime.py`, `tests/test_model_backend.py`, `tests/test_hive_cortex_context.py` (compatibility guards — must pass unmodified) |

### 1.3 Ownership and authority — state plainly

**Package A** has no authority problem worth solving: no node in
`.autopilot/plan.json` declares `src/hive_mind_os/autopilot_workflow.py` in any
`write_scope`, so Package A is planner-authored product work that must land
through a plan that actually owns the file (see the escalation below), or as an
explicitly authorized out-of-DAG change by the repository owner. It does not
attach to an existing node.

**Package B should be owned by `MIGRATION-460`, semantically** — and cannot be
authorized there today. Both halves of that sentence matter:

*Why MIGRATION-460 is the right semantic owner.* It is the node where public
CLI/scheduler ingress routes to the canonical runtime
(`docs/execution/runbooks/MIGRATION-460.md` §3.2: `route_job_executor` →
`execute_canonical_mission_job` → the canonical mission runtime). It is the
first point at which real user traffic starts paying the per-mission token bill
that Package B bounds. It is `parallel_safe: false` with
`merge_conflict_surface: "high"` and runs ALONE in round R4
(`docs/execution/runbooks/README.md` round table), so a runtime-wide change
there collides with no sibling. Its `semantic_locks` are `public-cli-routing`
and `canonical-runtime` — the second is exactly the lock a role-runtime/backend
change needs to hold.

*Why it cannot be authorized there today — verified, not assumed.* An authority
amendment can only **widen** an existing node's `write_scope` / `file_locks` /
`required_tests` / `acceptance_criteria` (`.autopilot/bin/release_barrier.py:192-213`, `def node(self, node_id)`, whose four
`_merge_unique` calls at `:197-212` are the only widening it performs) and can never create a node or add a
dependency edge. But the amendment mechanism is narrower still:

- `release_barrier.py:85-86` — `if node_id != "RECON-010": issues.append("authority amendment may only target RECON-010")`.
- `release_barrier.py:169-173` — the document must contain **exactly one**
  amendment, the sealed RECON-010 one.
- `release_barrier.py:153-157` — verbatim:
  ```python
  if any(
      scope.startswith("src/") or scope.startswith("tests/")
      for scope in additional_write
  ):
      issues.append("authority amendment may not enter product runtime/test paths")
  ```

So an amendment can never add `src/**` or `tests/**` paths to any node,
including MIGRATION-460. Independently: `src/hive_mind_os/brain_kernel/role_runtime.py`
is inside `ROLE-200`'s `write_scope` and `ROLE-200` is `COMPLETE`
(`autopilot status` verdict `STOP`), and `src/hive_mind_os/model_backend.py` is
in **no** node's `write_scope` anywhere in the sealed plan.

*Therefore.* Package B is **not dispatchable under the current sealed plan**.
Do not attempt an amendment; it will fail `validate_configuration` and block
every dispatch. The honest paths, in order of preference:

1. **Plan-version lineage (the real fix).** Once the controller supports plan
   generations with receipt re-binding, emit plan v2 containing a node whose
   `write_scope` is exactly Package B's write list, with dependency on
   `MIGRATION-460`. This is the same constraint that forced the R2A/R2B
   durability split to be round order rather than dependency edges
   (`docs/execution/runbooks/README.md`, "Why level 7 splits"). Package A is
   what makes plan v2 trustworthy: the regenerated DAG would be lint-clean by
   construction.
2. **Owner-authorized out-of-DAG change.** The repository owner explicitly
   authorizes Package B as product work outside the DAG, executed from this
   runbook, with its own PR and receipts. This is a genuine human authority
   decision (a plan-scope decision), not something a worker may self-grant.
3. **Do nothing yet.** Package B stays a specification until (1) or (2). That is
   an acceptable outcome; shipping it by widening an authority gate is not.

A worker handed this runbook and a node contract that does not list Package B's
write paths must run `autopilot fail` with a blocker naming this section — never
"just edit the file".

---

## 2. Existing-code map (real symbols and signatures; never invent others)

### 2.1 Package A

| Path:line | Symbol | Real signature / value | Role in this work |
|---|---|---|---|
| `src/hive_mind_os/autopilot_workflow.py:19-30` | `GENERIC_PROMPT_SOURCE` | `dict` with keys `uri, pinned_uri, repository_commit, blob_sha, sha256, bytes, license` | the exact precedent to copy for the new standard pin |
| `src/hive_mind_os/autopilot_workflow.py:39` | `PortableAutopilotError` | `class PortableAutopilotError(RuntimeError)` | the only error type this module raises |
| `src/hive_mind_os/autopilot_workflow.py:43` | `_canonical_bytes` | `def _canonical_bytes(value: object) -> bytes` — `json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")` | digest material for request/contract ids |
| `src/hive_mind_os/autopilot_workflow.py:60` | `_validate_managed_path` | `def _validate_managed_path(root: Path, path: Path) -> Path` | rejects symlink/junction escape; every managed write goes through it |
| `src/hive_mind_os/autopilot_workflow.py:80` | `_atomic_write_json` | `def _atomic_write_json(root: Path, path: Path, value: object) -> None` — NamedTemporaryFile + fsync + `os.replace` | the write idiom `_atomic_write_text` must mirror |
| `src/hive_mind_os/autopilot_workflow.py:214` | `_canonical_contract_id` | `def _canonical_contract_id(value: Mapping[str, Any]) -> str` — pops `contract_id`, returns `"sha256:" + sha256(_canonical_bytes(material)).hexdigest()` | why any new contract field rotates every contract id |
| `src/hive_mind_os/autopilot_workflow.py:447` | `_load_bootstrap_request` | `def _load_bootstrap_request(path: Path, root: Path) -> Mapping[str, Any]` | validates `required` key set (`:455-460`), recomputes `request_id` over material minus `request_id` (`:464-468`), pins `source["sha256"]` against `GENERIC_PROMPT_SOURCE` (`:495-497`) |
| `src/hive_mind_os/autopilot_workflow.py:817` | `_requests_read_only` | `def _requests_read_only(request: str) -> bool` | selects the CHECK contract branch (`:986`) that must stay task-free |
| `src/hive_mind_os/autopilot_workflow.py:858` | `initialize_repository` | writes `.hive-mind/autopilot-request.json` (`:931`, `:952`); `stable_keys` re-init comparison at `:934-948` | where the standard is pinned and materialized |
| `src/hive_mind_os/autopilot_workflow.py:964` | `_uninstalled_contract` | `def _uninstalled_contract(root: Path, request: str) -> Mapping[str, Any]` | emits the bootstrap contract; `task_prompt` at `:1009-1022`; contract at `:1023-1058` |
| `src/hive_mind_os/autopilot_workflow.py:1061` | `inspect_repository` | `def inspect_repository(repository, *, request="", apply=False, actor=..., trust_state_root=None) -> Mapping[str, Any]` | calls `_uninstalled_contract` only when `.autopilot/bin/autopilot.py` is absent (`:1071-1073`) |
| `tests/test_autopilot_workflow.py:123` | `test_initialize_and_inspect_uninstalled_repository` | asserts `contract["intent"]["intent"] == "BUILD_DAG"`, task title regex, and `assertNotIn("kb4beast/hive-mind-os", contract["tasks"][0]["prompt"])` (`:141`) | the test that must grow standard assertions |
| `tests/test_autopilot_workflow.py:223,230,236` | CHECK-branch tests | assert `contract["tasks"] == []` and `bootstrap_required` | the CHECK contract must stay task-free after the change |
| `.autopilot/bin/autopilot.py:660` | `parser` | `def parser() -> argparse.ArgumentParser` with `commands = root.add_subparsers(dest="command", required=True)` (`:663`) then `commands.add_parser("<name>")` per subcommand; `add_dag_standard_arguments(commands)` at `:796`; `def main(argv: list[str] \| None = None) -> int` at `:866`, with the `if args.command in {"dag-rounds", "dag-lint"}:` plan-only branch at `:869-872` and the `from dag_standard import ...` import at `:15` | the wiring pattern the *standard* prescribes for a generated `dag-lint`; Package A does not implement it |

**Verbatim current DAG-build task prompt** (`src/hive_mind_os/autopilot_workflow.py:1009-1022`) — quoted so the worker never has to open the file to diff it:

```python
    task_prompt = (
        "Build the governed repository-resident Autopilot DAG described by "
        ".hive-mind/autopilot-request.json. Inspect the repository and applicable agent "
        "instructions. Treat the pinned GenericPrompt as an unadmitted evidence obligation, "
        "not authority to copy or redistribute its wording. Create "
        "machine-readable node contracts, conflict/lock data, release/integration "
        "boundaries, receipts, tests, rollback, and the portable orchestration policy. "
        "Before any push or PR, verify current protected-ref rules and fail closed if they "
        "cannot be established. Target the configured release branch, never a protected "
        "branch. The active host must independently review the clean controller bundle "
        "and execute it only inside its approved deny-by-default sandbox; checked-in "
        "provenance alone is not execution trust. Finish the DAG "
        "bootstrap candidate and independent validation in this durable task."
    )
```

### 2.2 Package B

| Path:line | Symbol | Real signature | Role in this work |
|---|---|---|---|
| `src/hive_mind_os/brain_kernel/role_runtime.py:40` (`class RoleRuntime:`; `__init__` at `:49`) | `RoleRuntime` | `def __init__(self, provider: ModelProvider \| None = None, *, backend: ModelBackend \| None = None, role_providers: Mapping[Role \| str, ModelProvider] \| None = None, ledger: EvidenceLedger \| None = None) -> None` | the runtime being changed |
| `src/hive_mind_os/brain_kernel/role_runtime.py:74` | `RoleRuntime.roles` | `@property def roles(self) -> tuple[str, ...]` → `KERNEL_IMPLEMENTED_ROLES` | fixed lifecycle |
| `src/hive_mind_os/brain_kernel/role_runtime.py:113` | `RoleRuntime.execute` | `async def execute(self, invocation: RoleInvocation, *, prior_results: Sequence[RoleResult] = ()) -> RoleResult` | one provider call per invocation |
| `src/hive_mind_os/brain_kernel/role_runtime.py:157` | `RoleRuntime.run_mission` | `async def run_mission(self, invocations: Sequence[RoleInvocation]) -> tuple[RoleResult, ...]` — rejects any ordering other than each canonical role exactly once in lifecycle order (`:160-165`) | the 28-delivery loop at `:168` |
| `src/hive_mind_os/brain_kernel/role_runtime.py:183` | `RoleRuntime._instruction` | `@staticmethod def _instruction(invocation: RoleInvocation, prior_results: Sequence[RoleResult]) -> str` — JSON binding incl. `"prior_role_result_digests": [item.result_digest for item in prior_results]` (`:202`) | already digest-only for priors; the *bodies* leak through `_agent_context` |
| `src/hive_mind_os/brain_kernel/role_runtime.py:211` | `RoleRuntime._agent_context` | `@staticmethod def _agent_context(result: RoleResult) -> AgentResult` | converts each prior result into a full `AgentResult` passed to the backend at `:148-149` |
| `src/hive_mind_os/brain_kernel/role_runtime.py:227` | `RoleRuntime._to_role_result` | `@staticmethod def _to_role_result(invocation, required_outputs, agent_result) -> RoleResult` — builds the provisional then `replace(provisional, result_digest=result_digest(provisional))` (`:266`) | the exact construction a deterministic disposition must reuse |
| `src/hive_mind_os/brain_kernel/role_runtime.py:36` | `RoleCapabilityDenied` | `class RoleCapabilityDenied(RoleProtocolError)` | precedent for the new fail-closed error |
| `src/hive_mind_os/brain_kernel/roles.py:38-60` | `RoleCapabilities` | frozen dataclass `allowed_actions, forbidden_actions, required_outputs`; `allows(action) -> bool` | required outputs must still be produced by deterministic dispositions |
| `src/hive_mind_os/brain_kernel/roles.py:63-98` | `RoleInvocation` | frozen dataclass `mission_id, work_id, attempt_id, role, executor_id, context: CompiledContext, authority_envelope_digest, evidence_refs, base_artifact_refs, candidate_artifact_refs`; `__post_init__` requires non-empty `evidence_refs` and full mission/work/attempt/role/authority binding to the context manifest | the invocation shape; never relax its bindings |
| `src/hive_mind_os/brain_kernel/roles.py:129,225,234,242,251` | `result_digest`, `role_capabilities`, `role_allows_action`, `next_role`, `role_prompt` | `result_digest(result: RoleResult) -> str`; `role_capabilities(role: str) -> RoleCapabilities`; `role_allows_action(role: str, action: str) -> bool`; `next_role(role: str) -> str \| None`; `role_prompt(role: str) -> str` | reuse verbatim |
| `src/hive_mind_os/brain_kernel/contracts.py:398-426` | `RoleResult` | frozen dataclass: `mission_id, work_id, attempt_id, role, executor_id, context_manifest_digest, authority_envelope_digest, base_artifact_refs, candidate_artifact_refs, output_artifact_refs, claims, effect_receipt_refs, unresolved_risks, requested_next_role, self_assessment, result_digest` | the typed result every disposition must still emit |
| `src/hive_mind_os/brain_kernel/context.py:436` | `ContextCompiler` | `def __init__(self, catalog: MemoryCatalog, manifests: ContextManifestStore \| None = None) -> None` | **the** context system (B3) |
| `src/hive_mind_os/brain_kernel/context.py:443` | `ContextCompiler.compile` | `def compile(self, request: ContextRequest) -> CompiledContext` — hard budget check `if hot_tokens > request.token_budget: raise ValueError("required hot context exceeds the hard token budget")` (`:444-446`), provenance filter (`:460`, `_exclude_unprovenanced` `:514`), evaluator isolation (`:461-464`, `_exclude_evaluator_material` `:521`), warm/cold tiering (`:465`, `_tier` `:531`), immutable manifest store (`:483`) | already provides hard token budgets, hot/warm/cold, provenance filtering, evaluator isolation, immutable manifests — connect to it, do not rebuild it |
| `src/hive_mind_os/brain_kernel/context.py:486` | `ContextCompiler.retrieve_cold` | `def retrieve_cold(self, compiled: CompiledContext, record_id: str) -> CompiledContext` — raises `KeyError("requested item is not an available cold reference")`, otherwise recompiles with the pin added to `explicit_pins` | **recorded** cold expansion: a new immutable manifest revision *is* the record (lesson 2) |
| `src/hive_mind_os/brain_kernel/context.py:29-39` | `HotContextItem` | frozen dataclass `reference: str, token_count: int`; rejects empty reference or negative tokens | declared token cost before compilation |
| `src/hive_mind_os/brain_kernel/context.py:41-67` | `ContextRequest` | frozen dataclass `mission_id, work_id, attempt_id, role, charter_digest, authority_digest, token_budget, query, now, data_scopes, hot_items, repository_key=None, evaluator_mode=False, explicit_pins=(), sensitivity_scopes=("public","internal"), required_sensitivities=()` | request shape |
| `src/hive_mind_os/brain_kernel/context.py:69-81` | `CompiledContext` | frozen dataclass `request, manifest: ContextManifest, warm: tuple[RankedMemory, ...], cold: tuple[RankedMemory, ...], bindings=()`; `estimated_tokens` property → `manifest.estimated_tokens` | what `RoleInvocation.context` already holds |
| `src/hive_mind_os/model_backend.py:82-104` | `ModelBackend.__init__` | `def __init__(self, provider: ModelProvider, *, ledger: EvidenceLedger \| None = None, budget: AutonomyBudget \| None = None, context_limit_chars: int = 8000, role_providers: Mapping[Role, ModelProvider] \| None = None, prompt_registry: PromptRegistry \| None = None) -> None` | `context_limit_chars` default 8000 at `:89`, guard at `:93`, stored at `:103` |
| `src/hive_mind_os/model_backend.py:106-115` | `ModelBackend.execute` | `async def execute(self, contract: RoleContract, work_item: WorkItem, objective: Objective, context: tuple[AgentResult, ...], *, repository_context: RepositoryContext \| None = None, result_validator: Callable[[AgentResult], None] \| None = None) -> AgentResult` | the signature gaining one keyword-only parameter |
| `src/hive_mind_os/model_backend.py:236-297` | `ModelBackend._prompt` | `def _prompt(self, contract, work_item, objective, context, repository_context) -> tuple[str, str, bool, str]` returning `(system, user, truncated, artifact_digest)` | holds the char-truncation loop at `:276-278` |
| `src/hive_mind_os/model_backend.py:71-79` | `_render_context` | `def _render_context(prior_roles: list[dict[str, object]], omitted_roles: list[str]) -> str` | already emits `{"prior_roles": …, "omitted_roles": …}` — the shape the envelope generalizes |
| `src/hive_mind_os/model_backend.py:344-397` | `ModelBackend._record_call` | `def _record_call(self, objective, contract, work_item, request_body, response, retry_index, duration_s, outcome, context_truncated, provider, context_manifest, prompt_artifact_digest, *, error: str \| None = None) -> None` — payload already carries `"prompt_tokens": response.prompt_tokens if response else None` and `"completion_tokens": …` (`:383-384`), ends with `self.ledger.append_event(objective.id, "model.call", contract.role.value, payload)` (`:395-397`) | the single receipt seam the token ledger extends |
| `src/hive_mind_os/model_backend.py:139-142` | estimator | `estimated_tokens = max(1, len(body) // 4)`; `request_compute = (estimated_tokens + provider.config.max_output_tokens) / 1000.0` | the existing estimator; reuse it, do not invent a second one |
| `src/hive_mind_os/model_backend.py:413-438` | `ModelBackend._context_manifest` | `def _context_manifest(self, context: tuple[AgentResult, ...], *, role: Role, provider: ModelProvider) -> dict[str, object]` | receipt-side manifest that must gain routing fields |
| `src/hive_mind_os/model_provider.py:108-113` | `ModelResponse` | frozen dataclass `content: str, raw_body: bytes, prompt_tokens: int \| None, completion_tokens: int \| None, transport_retry_index: int = 0` | `None` token counts are exactly why `MEASURED`/`ESTIMATED`/`UNAVAILABLE` is required |
| `src/hive_mind_os/ledger.py:17,104` | `EvidenceLedger`, `append_event` | `def __init__(self, path: str \| Path = ":memory:") -> None`; `def append_event(self, run_id: str, event_type: str, actor: str, payload: dict[str, Any]) -> int` — hash-chained, `events_no_update`/`events_no_delete` triggers make it append-only | the durable home of token records |
| `.autopilot/bin/sidecar_execution.py:271` | `plan_sidecars` | `def plan_sidecars(tasks: Sequence[Mapping[str, object]], nodes: Mapping[str, Mapping[str, object]], policy: Mapping[str, object]) -> tuple[dict[str, object], ...]` — sorts by `-estimated_net_savings_tokens` (`:290`) and admits under `min_net_savings_tokens` / `max_sidecars_per_primary` / `max_total_sidecars` / `total_token_budget` (`:297-302`) | the consumer of the calibration artifact; **not edited by this runbook** |

**Layering constraint (do not violate).** `model_backend.py` imports only
`.autonomy`, `.contracts`, `.ledger`, `.model_provider`, `.models`,
`.prompt_registry`, `.roles` — it imports **nothing** from `brain_kernel`, while
`brain_kernel/role_runtime.py:17-20` imports `..ledger`, `..model_backend`,
`..model_provider`, `..models`. The dependency direction is
`brain_kernel → outer modules`. Therefore the new envelope type lives in
`model_backend.py` and the new token-ledger module lives at
`src/hive_mind_os/token_ledger.py` (outer layer), while the applicability policy
lives at `src/hive_mind_os/brain_kernel/role_applicability.py`. Importing
`brain_kernel` from `model_backend.py` creates a cycle and is forbidden.

---

## 3. Design — Package A

### 3.1 Standard pin constant (`autopilot_workflow.py`, beside `GENERIC_PROMPT_SOURCE`)

```python
DAG_AUTHORING_STANDARD = {
    "standard_version": 1,
    "source_path": "docs/execution/DAG_AUTHORING_STANDARD.md",
    "installed_path": ".hive-mind/dag-authoring-standard.md",
    "sha256": "<64 lowercase hex of the landed file's bytes>",
    "bytes": <exact byte length>,
}
```

Same shape discipline as `GENERIC_PROMPT_SOURCE` (`:19-30`): a plain `dict` of
JSON-safe scalars, no `Path`, no runtime interpolation. `sha256` here is bare
hex (no `sha256:` prefix), matching `GENERIC_PROMPT_SOURCE["sha256"]` at `:27`.

```python
def _standard_source_path() -> Path:
    """Locate the packaged authoring standard for the running Hive Mind OS."""
    return Path(__file__).resolve().parents[2] / DAG_AUTHORING_STANDARD["source_path"]


def _read_authoring_standard() -> tuple[bytes, dict[str, Any]]:
    """Return the standard bytes and its verified pin, or fail closed."""
```

`_read_authoring_standard` reads `_standard_source_path()` in binary; raises
`PortableAutopilotError("packaged DAG authoring standard is missing: <path>")`
when absent, and
`PortableAutopilotError("packaged DAG authoring standard does not match its pin")`
when `sha256(body).hexdigest() != DAG_AUTHORING_STANDARD["sha256"]` or
`len(body) != DAG_AUTHORING_STANDARD["bytes"]`. It returns
`(body, dict(DAG_AUTHORING_STANDARD))`. `parents[2]` resolves
`src/hive_mind_os/autopilot_workflow.py` → repository root; if a deployment
packages the module without `docs/`, the missing-file branch fires and
initialization fails closed with a nameable remediation. Never silently skip.

### 3.2 `_atomic_write_text` (mirror of `_atomic_write_json:80`)

```python
def _atomic_write_text(root: Path, path: Path, body: str) -> None:
```

Byte-for-byte the same body as `_atomic_write_json` except it writes `body`
directly instead of `json.dumps(...) + "\n"`: `_validate_managed_path`, `mkdir`,
`_validate_managed_path` again, `NamedTemporaryFile("w", encoding="utf-8",
dir=path.parent, prefix=f".{path.name}.", delete=False)`, `flush`,
`os.fsync(handle.fileno())`, `os.replace(temporary, path)`. Do not refactor
`_atomic_write_json` to share a helper — a shared helper changes an existing
call path for zero benefit.

### 3.3 `initialize_repository` (`:858`) — pin, materialize, record

Insert **after** the target-branch validation at `:895` (`_git(root,
["check-ref-format", …])`) and **before** the `request` dict is built at `:896`:

```python
    standard_body, standard_pin = _read_authoring_standard()
```

Add exactly one new key to the `request` dict, placed alphabetically among the
literals so the source stays sorted-ish (position is irrelevant to the digest —
`_canonical_bytes` sorts keys):

```python
        "dag_authoring_standard": standard_pin,
```

After the existing early-return / conflict logic (`:931-951`) and immediately
before `_atomic_write_json(root, path, request)` at `:952`, materialize the
standard into the target repository:

```python
    _atomic_write_text(
        root,
        root / ".hive-mind" / "dag-authoring-standard.md",
        standard_body.decode("utf-8"),
    )
```

Rationale: the target repository is an arbitrary clone that does not contain
Hive Mind OS's `docs/` tree. The DAG-build task runs *inside the target
repository*; it can only read the standard if the standard is there. `.hive-mind/`
is already the managed directory and every write goes through
`_validate_managed_path`, so no new escape surface is created.

**`stable_keys` (`:934-948`) is NOT extended.** This is deliberate and must be
stated in the code as a comment plus in `PORTABLE_AUTOPILOT.md`: a repository
initialized against standard v1 stays bound to standard v1. If
`dag_authoring_standard` were a stable key, re-pinning the standard would make
every existing initialized repository raise "request already exists; inspect it
before replacing" (`:949-951`) on the next `init`. Binding a built DAG to *the
standard version it was authored against* is precisely the requirement; a later
standard bump must not retroactively invalidate or silently rewrite an existing
request. The already-initialized branch therefore returns the stored request
with its original pin.

`_load_bootstrap_request` (`:447`): do **not** add `dag_authoring_standard` to
the `required` set at `:455-460`. Requests written before this change are still
structurally valid and still verify their `request_id`; they simply carry no
standard. Fail-closed handling for them belongs one layer up, in §3.4, where a
precise remediation can be given.

### 3.4 `_uninstalled_contract` (`:964`) — carry the pin, revise the prompt

Immediately after `bootstrap = _load_bootstrap_request(request_path, root)`
(`:970`):

```python
    standard = bootstrap.get("dag_authoring_standard")
    if not isinstance(standard, Mapping) or not standard.get("sha256"):
        raise PortableAutopilotError(
            "portable Autopilot request predates the DAG authoring standard; "
            "remove .hive-mind/autopilot-request.json and re-run "
            "`hive-mind autopilot init` to bind this repository to a standard version"
        )
    standard_pin = {
        "standard_version": standard.get("standard_version"),
        "installed_path": standard.get("installed_path"),
        "sha256": standard.get("sha256"),
        "bytes": standard.get("bytes"),
    }
```

Place this **after** the `_requests_read_only(request)` CHECK branch at
`:986-1008`? **No — before it.** A CHECK inspection of a repository whose
request predates the standard must also fail closed rather than report a clean
idle state; the block goes at `:971`, before `repository_id` is computed. The
CHECK contract itself stays task-free (`"tasks": []`) and gains the same
`"dag_authoring_standard": standard_pin` top-level field, so that a read-only
inspection reports which standard the repository is bound to.

**Exact new `task_prompt`** replacing `:1009-1022` verbatim. Every sentence of
the current prompt is preserved; three requirements are added (conformance,
lint-before-success, and no-success-without-a-clean-lint-receipt). The standard
path and digest are interpolated so the prompt is self-binding:

```python
    task_prompt = (
        "Build the governed repository-resident Autopilot DAG described by "
        ".hive-mind/autopilot-request.json. Inspect the repository and applicable agent "
        "instructions. Treat the pinned GenericPrompt as an unadmitted evidence obligation, "
        "not authority to copy or redistribute its wording. Create "
        "machine-readable node contracts, conflict/lock data, release/integration "
        "boundaries, receipts, tests, rollback, and the portable orchestration policy. "
        "The DAG you build MUST satisfy the DAG authoring standard retained in this "
        f"repository at {standard_pin['installed_path']} "
        f"(sha256 {standard_pin['sha256']}, standard version {standard_pin['standard_version']}); "
        "verify those exact bytes before you rely on them and fail closed if they differ. "
        "That standard is binding on node contracts, scaffold-file ownership, read-scope "
        "concreteness and recorded cold expansion, durability ordering before any node that "
        "asserts crash, restart, resume, interruption, or replay recovery or performs an "
        "external effect, executable dispatch rounds rather than dependency levels, "
        "per-round repository-wide validation, and prompt-as-contract worker rendering. "
        "The control plane you generate MUST implement the standard's `dag-lint` command, "
        "and `python .autopilot/bin/autopilot.py --repo-root . dag-lint --json` MUST exit "
        "zero with an empty error list against the DAG you built. Do NOT report this task "
        "successful before that clean lint receipt exists; a lint error is a defect in your "
        "DAG, never a reason to weaken the standard, the linter, or this contract. "
        "Before any push or PR, verify current protected-ref rules and fail closed if they "
        "cannot be established. Target the configured release branch, never a protected "
        "branch. The active host must independently review the clean controller bundle "
        "and execute it only inside its approved deny-by-default sandbox; checked-in "
        "provenance alone is not execution trust. Finish the DAG "
        "bootstrap candidate and independent validation in this durable task."
    )
```

Add to the BUILD_DAG contract dict (`:1023-1056`), as a top-level sibling of
`"target_branch"`:

```python
        "dag_authoring_standard": standard_pin,
```

and add to the single task object (`:1036-1051`), beside `"expected_artifact"`:

```python
                "required_receipts": [
                    "dag-lint --json exit 0 with zero errors",
                    "independent validation of the generated control plane",
                ],
```

`contract["contract_id"] = "sha256:" + sha256(_canonical_bytes(contract)).hexdigest()`
at `:1057` is unchanged and now covers the new fields.

### 3.5 Contract-id impact — update the tests, never the hash

`_canonical_contract_id` (`:214-217`) and the inline id computations at `:1007`
and `:1057` hash the **entire** canonical contract minus `contract_id`. Adding
`dag_authoring_standard` and `required_receipts` therefore rotates **every**
bootstrap contract id — both the CHECK contract and the BUILD_DAG contract. The
same is true of `request_id` (`:930`) once `dag_authoring_standard` joins the
request.

This is correct and intended: a contract bound to a different standard version
*is* a different contract, and its identity must say so. The required response
is to update `tests/test_autopilot_workflow.py` to the new shape.

**Forbidden responses** (any of these is a failed implementation): removing
`contract_id`/`request_id` from the digest material; excluding the new fields
from `_canonical_bytes` input; adding a "compatibility" branch that omits the
standard when a test asks for it; loosening `_load_bootstrap_request`'s
`request_id` equality check at `:467`; or pinning an expected digest literal in
a test so the test must be edited on every future field addition.

Verified current state, so the worker knows the blast radius exactly: no test in
`tests/` asserts a literal `contract_id` or `request_id` value —
`tests/test_autopilot_workflow.py:143-147` only asserts *self-consistency*
(`first["request"]["request_id"] == repeated["request"]["request_id"]`), and
`:244-249` recomputes the digest over mutated material. So the update is
additive assertions plus fixture wiring, not digest surgery. Confirm this with a
grep for `contract_id` before editing; if a literal digest has appeared since,
recompute it from the new canonical material — do not delete the assertion.

### 3.6 `docs/execution/PORTABLE_AUTOPILOT.md` — one new subsection

Insert after the "Bootstrap another repository" section: **"DAG authoring
standard binding"** — five short paragraphs: (1) `init` pins the standard by
sha256 and materializes it at `.hive-mind/dag-authoring-standard.md`; (2) the
bootstrap contract and its `contract_id` cover that pin, so a built DAG is
bound to the standard version it was authored against; (3) the DAG-build task
may not report success without a zero-error `dag-lint` receipt; (4) the pin is
deliberately excluded from the re-init `stable_keys` comparison so a standard
bump never retroactively invalidates an initialized repository — re-binding is
an explicit operator action (remove the request and re-init); (5) a request that
predates the standard fails closed on `inspect` with that exact remediation.

---

## 4. Design — Package B

### 4.1 New module `src/hive_mind_os/brain_kernel/role_applicability.py` (pure, deterministic)

Imports: stdlib + `.canonical` (`canonical_digest`), `.roles`
(`KERNEL_IMPLEMENTED_ROLES`, `RoleProtocolError`, `role_capabilities`,
`next_role`). No I/O, no provider, no `model_backend` import.

```python
class ApplicabilityDenied(RoleProtocolError):
    """A role disposition cannot be resolved without weakening lifecycle accountability."""


class RoleDisposition(StrEnum):
    MODEL_EXECUTE = "model_execute"          # a bounded provider call is warranted
    DETERMINISTIC_CHECK = "deterministic_check"  # resolved by code + evidence, no model call
    NOT_APPLICABLE = "not_applicable"        # archetype cannot produce work for this role
    DEFERRED = "deferred"                    # applicable, intentionally postponed with a named trigger
    BLOCKED = "blocked"                      # cannot proceed; carries a blocking reason


class TaskArchetype(StrEnum):
    DOC_ONLY = "doc_only"
    TEST_ONLY = "test_only"
    SINGLE_MODULE_CHANGE = "single_module_change"
    MULTI_MODULE_CHANGE = "multi_module_change"
    EXTERNAL_EFFECT = "external_effect"
    INVESTIGATION = "investigation"


@dataclass(frozen=True, slots=True)
class ArchetypeSignals:
    """Observable, evidence-bound facts that select an archetype — never a model guess."""
    write_scope: tuple[str, ...]          # declared node write scope, sorted+unique
    performs_external_effect: bool        # push/PR/comment/deploy declared
    asserts_recovery: bool                # acceptance mentions crash/restart/resume/replay
    acceptance_count: int
    evidence_refs: tuple[str, ...]        # >= 1 required

    def __post_init__(self) -> None: ...  # ApplicabilityDenied on empty evidence_refs
                                          # or unsorted/duplicated write_scope

    @property
    def archetype(self) -> TaskArchetype: ...


@dataclass(frozen=True, slots=True)
class RoleDispositionRecord:
    role: str
    disposition: RoleDisposition
    rationale: str                        # non-empty; machine-stable phrasing
    evidence_refs: tuple[str, ...]        # >= 1; the facts that justify it
    trigger: str | None = None            # required iff disposition is DEFERRED
    blocking_reason: str | None = None    # required iff disposition is BLOCKED

    @property
    def digest(self) -> str: ...          # canonical_digest over all fields


@dataclass(frozen=True, slots=True)
class ApplicabilityPolicy:
    """Closed archetype -> role -> disposition table; immutable and digestible."""
    table: Mapping[str, Mapping[str, RoleDisposition]]

    def __post_init__(self) -> None: ...  # every TaskArchetype key present; every
                                          # KERNEL_IMPLEMENTED_ROLES key present per archetype

    @property
    def policy_digest(self) -> str: ...


DEFAULT_APPLICABILITY_POLICY: ApplicabilityPolicy


def resolve_dispositions(
    signals: ArchetypeSignals, *, policy: ApplicabilityPolicy = DEFAULT_APPLICABILITY_POLICY
) -> tuple[RoleDispositionRecord, ...]:
    """Return exactly len(KERNEL_IMPLEMENTED_ROLES) records in lifecycle order."""
```

`DEFAULT_APPLICABILITY_POLICY` rules (the table is data, so a downstream repo
can supply its own without forking code). Non-negotiable invariants enforced in
`resolve_dispositions`:

- **Exactly eight records, lifecycle order.** `tuple(r.role for r in records) ==
  KERNEL_IMPLEMENTED_ROLES`. Never fewer. Accountability is preserved by the
  *record*, not by the model call.
- `curator` is **never** `NOT_APPLICABLE` in any archetype. Independent
  evaluation is the one thing that may never be skipped; at minimum it is
  `DETERMINISTIC_CHECK`.
- `signals.performs_external_effect` forces `integrator` and `steward` to at
  least `DETERMINISTIC_CHECK` and forbids `NOT_APPLICABLE` for both (lesson 3's
  runtime shadow).
- `signals.asserts_recovery` forbids `NOT_APPLICABLE` for `steward`.
- `DEFERRED` without a `trigger`, or `BLOCKED` without a `blocking_reason`,
  raises `ApplicabilityDenied`. A disposition that cannot say what would undefer
  it is a silent skip wearing a label.
- Representative table rows: `DOC_ONLY` → `orchestrator`/`explorer` =
  `DETERMINISTIC_CHECK`, `architect` = `NOT_APPLICABLE`, `builder` =
  `MODEL_EXECUTE`, `curator` = `MODEL_EXECUTE`, `integrator`/`steward`/
  `optimizer` = `DETERMINISTIC_CHECK` → two model calls, eight records.
  `MULTI_MODULE_CHANGE` and `EXTERNAL_EFFECT` → all eight `MODEL_EXECUTE`
  (no saving, and none is wanted).

### 4.2 Deterministic dispositions still produce `RoleResult`s

In `role_runtime.py`, add:

```python
    def deterministic_result(
        self, invocation: RoleInvocation, record: RoleDispositionRecord
    ) -> RoleResult:
        """Build the typed result for a non-model disposition, with no provider call."""
```

It reuses the exact construction of `_to_role_result` (`:227-266`): required
outputs from `role_capabilities(invocation.role).required_outputs`;
`output_artifact_refs` built with the same `canonical_digest({"role": …,
"work_id": …, "output": name, "content": …})` shape, where `content` is the
record's `rationale` prefixed by the disposition value (so the digest is
deterministic and self-describing); `executor_id = invocation.executor_id`;
`self_assessment = f"{record.disposition}: {record.rationale}"`;
`unresolved_risks` carrying the `trigger`/`blocking_reason` when present;
`requested_next_role = next_role(invocation.role)`; and the same two-step
`replace(provisional, result_digest=result_digest(provisional))` finish at
`:266`. `base_artifact_refs` must include `record.digest` so the disposition is
evidence-bound in the result itself.

`BLOCKED` is the one disposition that does **not** produce a `RoleResult`:
`run_mission` raises `ApplicabilityDenied` naming the role and
`blocking_reason`. Fail closed; never emit a passing result for a blocked role.

### 4.3 Dependency-routed context

Add to `role_applicability.py` (it is pure data, and keeps `role_runtime` thin):

```python
ROLE_DEPENDENCIES: Mapping[str, tuple[str, ...]] = {
    "orchestrator": (),
    "explorer": ("orchestrator",),
    "architect": ("explorer",),
    "builder": ("architect",),
    "curator": ("builder",),
    "integrator": ("curator",),
    "steward": ("integrator",),
    "optimizer": ("steward",),
}


class ContextTier(StrEnum):
    FULL = "full"           # direct dependency: whole body
    DIGEST = "digest"       # transitive ancestor: identity + digest + one-line claim
    OMITTED = "omitted"     # unrelated: named only, retrievable cold


def route_prior_results(role: str, prior_roles: Sequence[str]) -> Mapping[str, ContextTier]:
    """Classify every prior role for one consumer role. Total function: every
    prior role appears exactly once in the result."""
```

Rules: a role in `ROLE_DEPENDENCIES[role]` → `FULL`; a transitive ancestor
(closure of `ROLE_DEPENDENCIES` from `role`) → `DIGEST`; anything else →
`OMITTED`. `ROLE_DEPENDENCIES` is *declared* separately from
`KERNEL_IMPLEMENTED_ROLES` order on purpose: lifecycle order is not the same
claim as data dependency, and a downstream repository may legitimately supply a
different graph. Validate at import that its keys equal
`set(KERNEL_IMPLEMENTED_ROLES)` and that it is acyclic; otherwise
`ApplicabilityDenied`.

Cost change: today every role receives every predecessor (28 deliveries per
mission). With routing, each role receives 1 full body + (k-1) digests, so full
bodies drop from 28 to 7 per mission while every prior role remains *named* and
*reachable*. Omission is disclosed, never silent.

### 4.4 Connecting `ContextCompiler` to the backend (B3 — no second system)

New frozen dataclass in **`model_backend.py`** (outer layer — see the layering
constraint in §2.2):

```python
@dataclass(frozen=True, slots=True)
class ContextEnvelope:
    """A pre-compiled, budget-bound context selection supplied by the caller.

    The backend renders this envelope verbatim. It performs no selection, no
    ranking, and no character truncation when an envelope is present.
    """
    manifest_digest: str                       # ContextManifest.manifest_digest
    token_budget: int                          # ContextRequest.token_budget
    estimated_tokens: int                      # CompiledContext.estimated_tokens
    full_bodies: tuple[tuple[str, str], ...]   # (role, rendered body), FULL tier
    digests: tuple[tuple[str, str], ...]       # (role, result_digest), DIGEST tier
    omitted_roles: tuple[str, ...]             # OMITTED tier, disclosed by name
    cold_references: tuple[str, ...]           # retrievable via ContextCompiler.retrieve_cold
    generator_evaluator_separated: bool        # from ContextManifest

    def to_prompt(self) -> dict[str, object]: ...
    def to_receipt(self) -> dict[str, object]: ...   # digests and counts only, no bodies
```

`ModelBackend.execute` (`:106`) gains **one keyword-only parameter**, defaulted
so every existing caller and `tests/test_model_backend.py` keep working
unchanged:

```python
    async def execute(
        self,
        contract: RoleContract,
        work_item: WorkItem,
        objective: Objective,
        context: tuple[AgentResult, ...],
        *,
        repository_context: RepositoryContext | None = None,
        result_validator: Callable[[AgentResult], None] | None = None,
        context_envelope: ContextEnvelope | None = None,
    ) -> AgentResult:
```

It threads `context_envelope` into `_prompt` (`:236`), whose signature becomes
`def _prompt(self, contract, work_item, objective, context, repository_context,
context_envelope)` and whose behavior branches exactly once:

- `context_envelope is None` → the current code path is untouched, including the
  `while prior_roles and len(rendered) > self.context_limit_chars` loop at
  `:276-278`. Legacy callers see zero behavior change (B5).
- `context_envelope is not None` → build `rendered =
  json.dumps(context_envelope.to_prompt(), ensure_ascii=False, sort_keys=True,
  separators=(",", ":"))`, set `truncated = bool(context_envelope.omitted_roles)`,
  and **never** enter the truncation loop. If
  `context_envelope.estimated_tokens > context_envelope.token_budget`, raise
  `ValueError("context envelope exceeds its declared token budget")` — the hard
  budget is the compiler's (`context.py:444-446`), and the backend refuses to
  silently exceed it rather than trimming.

`_context_manifest` (`:413`) gains, when an envelope is present:
`"context_envelope": context_envelope.to_receipt()` and
`"manifest_digest": context_envelope.manifest_digest`. Bodies never enter the
receipt — the module docstring at `model_backend.py:1-5` commits to excluding
prompt bodies, and that commitment is not negotiable.

In `role_runtime.py`, replace the unconditional
`context = tuple(self._agent_context(item) for item in prior_results)` at `:148`
with a routed build, and pass the envelope through:

```python
    @staticmethod
    def _context_envelope(
        invocation: RoleInvocation, prior_results: Sequence[RoleResult]
    ) -> ContextEnvelope:
        """Project the already-compiled CompiledContext plus routed priors into
        the backend envelope. Reads invocation.context.manifest / .cold only —
        it never ranks, re-tiers, or re-budgets anything."""
```

`manifest_digest`, `token_budget`, `estimated_tokens`,
`generator_evaluator_separated` all come from
`invocation.context.manifest` / `invocation.context.request` /
`CompiledContext.estimated_tokens` (`context.py:79-81`);
`cold_references` from `manifest.cold_references`. Prior-result tiers come from
`route_prior_results(invocation.role, [r.role for r in prior_results])`. FULL
bodies reuse `_agent_context` (`:211`) verbatim so the existing `AgentResult`
shape is preserved; DIGEST entries carry `(role, result.result_digest)` only.

`RoleRuntime.execute` (`:113`) keeps its signature and passes both the narrowed
`context` tuple (FULL tier only) and `context_envelope=` to
`self.backend.execute(...)` at `:149`. `_instruction` (`:183`) is unchanged —
it already sends `prior_role_result_digests` only (`:202`), which is exactly the
DIGEST tier and is why it needs no change.

**Cold retrieval is the escape hatch and it is recorded.** When a role
genuinely needs an omitted body, the caller calls
`ContextCompiler.retrieve_cold(compiled, record_id)` (`context.py:486-511`),
which recompiles with the record added to `explicit_pins` and stores a **new
immutable manifest revision** through `ContextManifestStore.store`
(`context.py:273-312`, which refuses to rewrite an existing digest). The
manifest chain *is* the budgeted, recorded cold-expansion record demanded by
lesson 2. Do not add a separate "expansion log"; the manifest store already is
one, and a second one would drift.

### 4.5 Token ledger — `src/hive_mind_os/token_ledger.py` (new, outer layer)

Pure and deterministic; imports stdlib + `.ledger` (`EvidenceLedger`) only. No
provider, no `brain_kernel`.

```python
class TokenAccountingError(ValueError):
    """A token record cannot be built without misstating what was measured."""


class TokenSource(StrEnum):
    MEASURED = "measured"        # provider reported the count
    ESTIMATED = "estimated"      # derived locally; estimator named
    UNAVAILABLE = "unavailable"  # neither reported nor derivable


@dataclass(frozen=True, slots=True)
class TokenMeasurement:
    input_tokens: int | None
    output_tokens: int | None
    input_source: TokenSource
    output_source: TokenSource
    estimator: str | None        # required iff either source is ESTIMATED

    def __post_init__(self) -> None: ...
    def to_document(self) -> dict[str, object]: ...


def measure_call(
    *, request_bytes: int, prompt_tokens: int | None, completion_tokens: int | None,
    max_output_tokens: int, estimator: str = "bytes-div-4",
) -> TokenMeasurement:
    """Prefer provider counts; fall back to the estimator already used at
    model_backend.py:139 (`max(1, len(body) // 4)`); never silently report a
    guess as MEASURED."""


@dataclass(frozen=True, slots=True)
class TokenRecord:
    run_id: str
    role: str
    work_item_id: str
    outcome: str                 # mirrors _record_call's outcome vocabulary
    retry_index: int
    measurement: TokenMeasurement
    context_manifest_digest: str | None
    omitted_role_count: int
    def to_document(self) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class PurposeCalibration:
    purpose: str                 # e.g. "bounded_read_only_research", "independent_review"
    sample_count: int
    median_input_tokens: int
    median_output_tokens: int
    observed_net_savings_tokens: int
    confidence: str              # "insufficient" | "provisional" | "calibrated"


def calibrate(records: Sequence[TokenRecord], *, minimum_samples: int = 5
              ) -> tuple[PurposeCalibration, ...]:
    """Deterministic per-purpose calibration. Fewer than `minimum_samples`
    observations yields confidence "insufficient" and observed savings 0 —
    never an extrapolated number."""


def calibration_document(calibrations: Sequence[PurposeCalibration]) -> dict[str, object]:
    """Canonical JSON document a controller may read. This module never writes
    into .autopilot/ and never imports controller code."""
```

Wiring: `ModelBackend._record_call` (`:344-397`) builds
`measure_call(request_bytes=len(request_body),
prompt_tokens=response.prompt_tokens if response else None,
completion_tokens=response.completion_tokens if response else None,
max_output_tokens=provider.config.max_output_tokens)` and adds one payload key
`"token_accounting": measurement.to_document()`. The existing
`"prompt_tokens"` / `"completion_tokens"` keys at `:383-384` stay **exactly as
they are** — `tests/test_model_backend.py` is an out-of-scope guard, and the new
block is additive. The `self.ledger.append_event(objective.id, "model.call",
contract.role.value, payload)` call at `:395-397` is unchanged; the ledger is
already append-only and hash-chained (`ledger.py:17-60`).

**Why this replaces the hardcoded sidecar constants.** `plan_sidecars`
(`.autopilot/bin/sidecar_execution.py:271`) admits sidecars by comparing
`estimated_net_savings_tokens` against `policy["min_net_savings_tokens"]`
(`:297`), where the estimate comes from the constants quoted in §1.2 —
`4_800 + 250 * min(scope_count, 8)` and
`{"moderate": 5_200, "high": 6_600, "critical": 7_800}.get(risk, 5_400) +
150 * min(evidence_count, 8)`. Those numbers are guesses about *this*
repository. `calibration_document` gives a controller measured per-purpose
medians from real history, so admission can be calibrated per repository.

**Package B does not edit `.autopilot/bin/sidecar_execution.py`.** The controller
bundle is sealed and trust-pinned (`docs/execution/PORTABLE_AUTOPILOT.md`:
"Any controller-bundle change invalidates trust and requires a fresh independent
review"). Product code *publishes* the calibration; adopting it is a separate,
independently reviewed controller change. Say this in `TOKEN_ECONOMY.md`.

### 4.6 `docs/execution/TOKEN_ECONOMY.md` (new, ~1 page)

Sections: (1) the measured baseline with the three citations from §1.2
(`role_runtime.py:168`, `model_backend.py:89/276-278`,
`sidecar_execution.py:285-289`); (2) the disposition vocabulary and the
"eight records, fewer than eight calls" accountability rule; (3) the
dependency-routing table and the FULL/DIGEST/OMITTED contract, stating that
omission is always disclosed and cold retrieval is always recorded as a new
manifest revision; (4) that `ContextCompiler` is the single context system and
the backend never re-selects; (5) the token-record schema and the
measured/estimated/unavailable rule (an unavailable count is reported as
unavailable, never as zero); (6) the calibration artifact and the explicit
statement that adopting it in the controller is a separate reviewed change.

---

## 5. Implementation order

**Package A** (small commits):

1. `DAG_AUTHORING_STANDARD`, `_standard_source_path`, `_read_authoring_standard`,
   `_atomic_write_text` (§3.1-3.2). No call sites yet.
2. `initialize_repository`: pin read, request key, materialization, the
   `stable_keys` comment (§3.3).
3. `_uninstalled_contract`: the predates-standard guard, `standard_pin`, both
   contract branches, the new `task_prompt`, `required_receipts` (§3.4).
4. `tests/test_autopilot_workflow.py` updates (§6.1); focused command green.
5. `docs/execution/PORTABLE_AUTOPILOT.md` subsection (§3.6).
6. Re-verify the pin: recompute the standard's sha256 and byte length from the
   landed `docs/execution/DAG_AUTHORING_STANDARD.md` as the **last** step before
   the PR, since the other agent may have revised it mid-flight.

**Package B** (only after the §1.3 authority question is resolved):

1. `role_applicability.py`: enums, `ArchetypeSignals`, `RoleDispositionRecord`,
   `ApplicabilityPolicy`, `DEFAULT_APPLICABILITY_POLICY`, `resolve_dispositions`.
2. `role_applicability.py`: `ROLE_DEPENDENCIES`, `ContextTier`,
   `route_prior_results` + the acyclicity/coverage import-time validation.
3. `token_ledger.py`: `TokenSource`, `TokenMeasurement`, `measure_call`,
   `TokenRecord`, `PurposeCalibration`, `calibrate`, `calibration_document`.
4. `model_backend.py`: `ContextEnvelope`, the `execute`/`_prompt` parameter and
   the single branch, `_context_manifest` additions, `_record_call`
   `token_accounting` key. Run the guard suite `tests/test_model_backend.py`
   before writing any new test.
5. `role_runtime.py`: `_context_envelope`, `deterministic_result`, the
   `run_mission` disposition loop. Run the guard suite
   `tests/test_hive_cortex_role_runtime.py`.
6. New tests (§6.2), then `docs/execution/TOKEN_ECONOMY.md`.

Both packages: push the node branch, open a **draft** PR to `main`, record the
node receipt. Never merge, never touch the release branch, never
rebase/squash/amend the node branch, never run repo-wide discovery (that is the
round integrator's single leased pass — lesson 5).

---

## 6. Test plan

### 6.1 Package A — `tests/test_autopilot_workflow.py` (existing file, additive)

Conventions already in the file: `unittest.TestCase`, `tempfile.TemporaryDirectory`,
a `git init -b main` fixture repo with one commit, `initialize_repository` /
`inspect_repository` called directly.

Focused command (the only one this package runs):

```
PYTHONPATH=src python -m unittest tests.test_autopilot_workflow -v
```

| required_tests name | Test class / method | Assertions |
|---|---|---|
| `dag-standard-binding-tests` | `test_initialize_pins_and_materializes_the_authoring_standard` | request has `dag_authoring_standard` with `standard_version`, `installed_path`, `sha256`, `bytes`; `(root/".hive-mind"/"dag-authoring-standard.md").read_bytes()` sha256 equals the pin and length equals `bytes`; `request_id` still verifies against `_canonical_bytes(material)` |
| | `test_bootstrap_contract_carries_the_standard_and_requires_lint` | `contract["dag_authoring_standard"]["sha256"]` equals the request pin; the task prompt contains `.hive-mind/dag-authoring-standard.md`, the literal digest, `dag-lint`, and `exit zero`; `contract["tasks"][0]["required_receipts"]` is non-empty; `contract["contract_id"] == "sha256:" + sha256(_canonical_bytes({k: v for k, v in contract.items() if k != "contract_id"})).hexdigest()` (recomputed, never a literal) |
| | `test_check_contract_reports_the_standard_without_tasks` | read-only request → `intent == "CHECK"`, `tasks == []`, `bootstrap_required is True`, and `dag_authoring_standard` present |
| | `test_request_predating_the_standard_fails_closed` | write a request without `dag_authoring_standard`, re-seal its `request_id` over the mutated material (the `:244-249` idiom), then `assertRaises(PortableAutopilotError)` on `inspect_repository`; assert the message names re-running `init` |
| | `test_missing_or_mismatched_packaged_standard_fails_closed` | `unittest.mock.patch` `_standard_source_path` to a nonexistent path → `PortableAutopilotError`; patch it to a file with different bytes → `PortableAutopilotError`; in neither case is `.hive-mind/autopilot-request.json` created |
| | `test_standard_pin_matches_the_checked_in_standard` | recompute sha256 and byte length of `docs/execution/DAG_AUTHORING_STANDARD.md` and assert equality with `DAG_AUTHORING_STANDARD` — the freshness guard that fails loudly when the standard is revised without re-pinning |
| | `test_reinitialization_keeps_the_originally_bound_standard` | init, then patch `DAG_AUTHORING_STANDARD` to a v2 pin, re-init → `status == "already-initialized"` and the returned request still carries the v1 pin (proves `stable_keys` was deliberately not extended) |

Existing tests to update, not weaken: `test_initialize_and_inspect_uninstalled_repository`
(`:123`) keeps its `intent`, title-regex, and `assertNotIn("kb4beast/hive-mind-os",
…)` assertions and gains the standard assertions; the three CHECK-branch tests
(`:223`, `:230`, `:236`) keep `tasks == []`.

### 6.2 Package B — two new test files

```
PYTHONPATH=src python -m unittest tests.test_hive_cortex_role_applicability -v
PYTHONPATH=src python -m unittest tests.test_hive_cortex_token_economy -v
PYTHONPATH=src python -m unittest tests.test_hive_cortex_role_runtime -v   # out-of-scope guard, unmodified
PYTHONPATH=src python -m unittest tests.test_model_backend -v              # out-of-scope guard, unmodified
```

Conventions: copy `tests/test_hive_cortex_role_runtime.py:1-45` — a `_Provider`
test double with `kind = ProviderKind.OPENAI_COMPATIBLE`, a `ProviderConfig`,
`build_request_body`, and a `complete_once` that parses the required output
names out of the system prompt; `asyncio.run(...)` for the async entry points;
`_DIGEST = "sha256:" + "a" * 64`.

| required_tests name | Test class | Methods (minimum) |
|---|---|---|
| `role-applicability-tests` | `RoleApplicabilityTests` | `test_every_archetype_resolves_all_eight_roles_in_lifecycle_order`; `test_small_task_costs_fewer_than_eight_model_calls_but_eight_records` (DOC_ONLY signals → count `MODEL_EXECUTE` < 8 and `len(records) == 8`); `test_curator_is_never_not_applicable` (loop every archetype); `test_external_effect_forces_integrator_and_steward_accountability`; `test_recovery_assertion_forces_steward_accountability`; `test_deferred_without_trigger_and_blocked_without_reason_are_denied`; `test_policy_digest_is_deterministic_and_covers_every_role`; `test_signals_require_evidence_refs` |
| `context-routing-tests` | `ContextRoutingTests` | `test_direct_dependency_gets_full_body_transitive_gets_digest_unrelated_omitted`; `test_every_prior_role_is_classified_exactly_once` (total function); `test_role_dependencies_cover_the_canonical_roles_and_are_acyclic`; `test_envelope_never_exceeds_its_declared_token_budget` (`ContextEnvelope` with `estimated_tokens > token_budget` → `ValueError` from `_prompt`); `test_backend_without_envelope_keeps_legacy_truncation` (construct `ModelBackend(provider, context_limit_chars=64)` with oversized priors and assert `omitted_roles` still populated by the `:276-278` loop); `test_backend_with_envelope_never_truncates_by_characters` (tiny `context_limit_chars`, large envelope → no character-driven omission; `truncated` reflects only the envelope's declared omissions); `test_cold_retrieval_produces_a_new_recorded_manifest_revision` (`ContextCompiler.retrieve_cold` → different `manifest_digest`, the pin present in the new request's `explicit_pins`, and the old manifest still readable from the store); `test_full_body_deliveries_drop_from_quadratic_to_linear` (recording backend double over `run_mission`; assert total FULL-tier deliveries `== 7` and that the pre-change count would be 28) |
| `token-ledger-tests` | `TokenLedgerTests` | `test_provider_counts_are_recorded_as_measured`; `test_missing_counts_fall_back_to_the_named_estimator` (source `ESTIMATED`, `estimator == "bytes-div-4"`); `test_unavailable_counts_are_never_reported_as_zero` (source `UNAVAILABLE`, values `None`); `test_estimated_source_requires_an_estimator_name` (`TokenAccountingError`); `test_model_call_event_carries_token_accounting` (in-memory `EvidenceLedger`, run one turn, read the `model.call` event, assert `payload["token_accounting"]` present **and** `prompt_tokens`/`completion_tokens` still present unchanged); `test_calibration_is_deterministic_and_refuses_to_extrapolate` (4 samples → `confidence == "insufficient"` and `observed_net_savings_tokens == 0`; 5+ → `"provisional"`/`"calibrated"` with a stable median across two identical calls); `test_calibration_document_is_canonical_json` (two calls → byte-identical `json.dumps(..., sort_keys=True, separators=(",", ":"))`) |
| `lifecycle-accountability-tests` | `LifecycleAccountabilityTests` | `test_run_mission_returns_eight_typed_results_with_verifiable_digests` (every `result_digest` re-verifies via `roles.result_digest`); `test_deterministic_result_makes_no_provider_call` (provider double records zero calls for `DETERMINISTIC_CHECK` roles); `test_blocked_disposition_fails_closed` (`ApplicabilityDenied`, and no `RoleResult` for that role); `test_deterministic_result_binds_the_disposition_digest` (`record.digest in result.base_artifact_refs`); `test_curator_still_requires_evaluator_isolated_context` (`RoleRuntime._validate_invocation` at `:172-180` (called from `execute` at `:121`) unchanged: `evaluator_mode` must equal `role == "curator"`) |

Do NOT run `python -m unittest discover`, pytest, or any other test module.

---

## 7. Acceptance self-check → receipt evidence

| Criterion | Demonstrated by | Receipt evidence |
|---|---|---|
| A1 pin + materialize + fail closed | §3.1-3.3; `test_initialize_pins_and_materializes_the_authoring_standard`, `test_missing_or_mismatched_packaged_standard_fails_closed` | focused transcript; `git diff` of `initialize_repository` |
| A2 contract carries the pin, id covers it | §3.4; `test_bootstrap_contract_carries_the_standard_and_requires_lint` (recomputed id) | focused transcript; sample contract JSON in the receipt |
| A3 prompt requires standard + zero-error lint | §3.4 exact prompt text | prompt diff hunk; the assertion lines |
| A4 pre-standard request fails closed | §3.4 guard; `test_request_predating_the_standard_fails_closed` | focused transcript incl. the remediation message |
| A5 tests updated, no hash weakened | §3.5; all §6.1 rows | full focused transcript; grep receipt showing no literal digest was introduced and `_canonical_contract_id` is unchanged |
| B1 eight records, fewer calls | §4.1-4.2; `role-applicability-tests`, `lifecycle-accountability-tests` | focused transcript; observed model-call count per archetype |
| B2 dependency-routed context | §4.3-4.4; `context-routing-tests` | focused transcript; the 28→7 full-body delivery assertion |
| B3 one context system | §4.4; no new tiering/budget/manifest code; `context.py` untouched | `git diff --stat` proving `brain_kernel/context.py` is unmodified |
| B4 token ledger with sources | §4.5; `token-ledger-tests` | focused transcript; a sample `model.call` payload with `token_accounting` |
| B5 truncation demoted to fallback | §4.4 single branch; `test_backend_without_envelope_keeps_legacy_truncation` + `test_backend_with_envelope_never_truncates_by_characters` | both pass lines; `tests/test_model_backend.py` green unmodified |
| Evidence requirements | base + final commit SHAs, changed-path inventory ⊆ write_scope, exact focused-test transcripts, role/authority identities, rollback ref = revert of the node commit | node completion receipt |

---

## 8. Out-of-scope traps (do NOT do these)

- **Do NOT modify `.autopilot/plan.json`.** It is sealed and fingerprint-bound;
  every completed receipt is bound to its fingerprint. Read it only.
- **Do NOT attempt an authority amendment for Package B.** `release_barrier.py:85-86`
  restricts amendments to `RECON-010`, `:169-173` allows exactly one, and
  `:153-157` forbids any `src/` or `tests/` path. A malformed amendments file
  makes `validate_configuration` (`:215-218`) fail and blocks *every* dispatch.
  Escalate per §1.3 instead.
- **Do NOT edit `.autopilot/bin/*.py`** — not `release_barrier.py`, not
  `controller.py`, not `autopilot.py`, not `sidecar_execution.py`. The bundle is
  trust-pinned; any change invalidates controller trust and requires a fresh
  independent review. Reuse `_nodes_conflict` (`release_barrier.py:244`),
  `dispatch` (`:299-372`), and `controller.scopes_overlap` by *citing* them, and
  never fork their logic into `src/**`.
- **Do NOT create `docs/execution/DAG_AUTHORING_STANDARD.md`, edit it, or
  paraphrase its contents into product code.** Another agent owns that exact
  path. Package A binds it by path + digest only.
- **Do NOT build a second context system.** No new ranking, tiering, token
  budgeting, manifest, or "expansion log". `brain_kernel/context.py` must show
  zero diff lines. If it genuinely lacks something, `autopilot fail` with a
  blocker naming the missing capability.
- **Do NOT delete the 8,000-character truncation path.** It is the legacy
  fallback for envelope-less callers and is covered by an out-of-scope guard
  test. Demote it behind the envelope branch; do not remove it, and do not
  change the `context_limit_chars: int = 8000` default at `model_backend.py:89`.
- **Do NOT import `brain_kernel` from `model_backend.py`** (import cycle — see
  §2.2), and do not import `model_backend` into
  `brain_kernel/role_applicability.py` (it must stay pure and provider-free).
- **Do NOT skip a role to save tokens.** `NOT_APPLICABLE` without a
  `RoleDispositionRecord`, a `DEFERRED` without a trigger, or a `BLOCKED` that
  still emits a passing `RoleResult` are all accountability failures, not
  optimizations. Eight records, always.
- **Do NOT report an unavailable token count as `0`.** `UNAVAILABLE` with
  `None` values is the honest record; a zero is a false measurement that would
  silently corrupt calibration.
- **Do NOT weaken any digest.** Not `contract_id`, not `request_id`, not
  `result_digest`, not `manifest_digest`, not the ledger hash chain. If a test
  breaks because a digest rotated, update the test's *recomputation*, never the
  digest material.
- **Do NOT edit `tests/test_model_backend.py`, `tests/test_hive_cortex_role_runtime.py`,
  or `tests/test_hive_cortex_context.py`.** They are compatibility guards. If one
  breaks, the change is wrong, not the test.
- **Do NOT run repo-wide test discovery** (lesson 5 — that is the round
  integrator's single leased pass), rebase/squash/amend the node branch, merge
  the draft PR, touch the release branch, or create/modify any `__init__.py`,
  `conftest.py`, or `pyproject.toml`. New modules are imported by full module
  path; no package re-exports.
