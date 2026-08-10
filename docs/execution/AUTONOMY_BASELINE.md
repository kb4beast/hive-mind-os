# BASE-020 Autonomy Baseline

## Binding

- Node: `BASE-020`
- Plan fingerprint: `sha256:9769f9796efb351da9b764fd49983b1130adccc0b8592e42581714d3727f8b39`
- Exact source `main`: `ffaaed5531ad4535a1fce59ffcf81b8442836c58`
- Exact source tree: `87a92782680a967afd29bceab218c61fc562a5e4`
- Remote claim commit: `34c8e3296348e9be265c128f45c0665c7461a42a`
- Claimed branch: `autopilot/base-020`
- Product runtime mutation: **none**. This node records current truth only.

This baseline distinguishes executable behavior from contracts, prompts, fixtures, historical branches, and aspirational documentation. A capability is called operational below only when a current runtime path actually reaches it.

## Deterministic baseline

The exact source commit was exercised by GitHub Actions run `31371653163`. The Linux Python 3.11 job checked out exactly `ffaaed5531ad4535a1fce59ffcf81b8442836c58` and ran:

```text
python -m unittest discover -s tests -v
```

Result: **611 tests, 5 skipped, OK**. The skipped Linux tests are platform-specific Windows regressions; the same workflow's Windows Python 3.12 job completed successfully. Python 3.12 and 3.14 Linux jobs also completed successfully. Static/type checks, CodeQL, secret scan, and SBOM/build provenance completed successfully. `dependency-and-license-review` was explicitly `skipped`, not converted into a success claim.

The baseline therefore preserves the observed skips rather than normalizing them away.

## Public CLI route trace

The installed script `hive-mind` resolves to `hive_mind_os.cli:main`. The following table traces every first-level public route and every public nested route exposed by its parser to the concrete runtime/effect boundary on this source commit.

| CLI route | Concrete runtime path | Actual side-effect boundary / truth |
|---|---|---|
| `hive-mind <goal>` | `cli._run` → `HiveKernel.run_objective` | Serial eight-role lifecycle. Deterministic backend by default; `--backend model` invokes `ModelBackend`. Generic kernel itself performs no repository tools/effects. |
| `audit` | `cli._run_audit` → `collect_current_state_audit` | Reads repository/docket and may execute configured tests. `--output` writes an audit artifact; optional HMAC input is read, never embedded as a key. |
| `deliver` | `cli._run_deliver` → `RepositoryMission.run` | Real local repository mission path. Can materialize isolated Git workspaces, run bounded commands/tests, write Builder changes, commit, independently verify as Curator, and publish a local evidence bundle. Model backend affects cognition, not authority. |
| `demo` | `cli._run_demo` → fixture `RepositoryMission` | Creates a temporary fixture repository and writes an external/local demo receipt bundle. It is explicitly fixture-only for arbitrary-repository capability claims. |
| `resume` | `cli._run_resume` → `resume_mission` | Reopens durable local mission state and may resume/reconcile the previously sealed repository mission; preserves prior effects/receipts rather than treating resume as read-only. |
| `missions` | `cli._run_missions` → `MissionStore.list_missions` | Read-only projection of local durable mission inventory. |
| `benchmark run` | `cli._run_benchmark` → `BenchmarkHarness.run` | Runs offline measurement lanes and writes append-only benchmark evidence under the selected output root. It does not prove production superiority by itself. |
| `ingest` | `cli._run_ingest` → `register_exhibit` / `ExhibitStore` | Writes content-addressed source evidence and provenance under the configured evidence root. |
| `defer` | `cli._run_defer` → `defer_obligation` | Writes a dated retained evidence obligation/court disposition; it does not fabricate unavailable source content. |
| `pit-episode` | `cli._run_pit_episode` → `PointInTimeOracle.run_scripted_episode` | Creates isolated point-in-time state/workspaces and retained episode/receipt evidence; target/future access remains guarded. |
| `experiment run` | `cli._run_experiment` | **Intentionally unavailable**. Returns `EVALUATION_SURFACE_UNAVAILABLE` and failure; no live evaluation/promotion capability is inferred from the command name. |
| `verify` | `cli._run_verify` → `verify_repository` | Materializes/verifies an exact immutable candidate in isolated workspaces and writes a verification bundle. Does not execute against caller's live worktree. |
| `enqueue` | `cli._run_enqueue` → `Scheduler.enqueue` + optional `record_legacy_enqueue` | Writes durable local scheduler state and, in default `kernel-v1` compatibility mode, a kernel migration/ingress record. Requires typed executable acceptance specs. |
| `serve` | `cli._run_serve` → `workers.serve` | Consumes local scheduler jobs; workers currently execute the durable legacy repository-mission path, so real local repository effects are possible within that mission's policy. |
| `status` | `cli._run_status` → `build_projection` | Read-only state projection unless `--html` is supplied, in which case a static HTML projection file is written. |
| `continuation export` | `cli._run_continuation` → `export_packet` / `write_packet` | Reads a clean bound repository and writes a local continuation packet to the requested external path. No remote authority is granted. |
| `continuation validate` | `cli._run_continuation` → `validate_packet` | Read-only validation of packet/repository binding. |
| `autonomous kickoff` | `AutonomousBrain.start_run` | Creates governed local autonomous run state and an isolated non-protected worktree/branch; remote push/comment authority is opt-in. |
| `autonomous turn` | `AutonomousBrain.run_host_turn` | Invokes the selected signed-in coding host locally under the run contract; host changes are bounded to the isolated run worktree. |
| `autonomous register-pr` | `AutonomousBrain.register_pull_request` | Writes local binding from a run to its draft PR metadata. |
| `autonomous open-draft-pr` | `AutonomousBrain.open_draft_pull_request` + `GitHubRestCommentGateway` | Authorized remote push/draft-PR effect through a token-backed gateway; no merge path is exposed. |
| `autonomous poll-pr` | `AutonomousBrain.handle_pull_request_feedback` | Reads untrusted PR feedback and may issue bounded replies/host turns; deduplication and run binding are enforced. |
| `autonomous push` | `AutonomousBrain.push_own_branch` | Pushes only the run's own non-protected branch. |
| `autonomous learn` | `AutonomousBrain.learn_from_human_outcome_with_host` | Produces point-in-time grading/learning records from later human commits. It does not silently mutate a champion prompt. |
| `autonomous supervise` | `AutonomousBrain.supervise` | Bounded polling/feedback and local-human-commit processing; remote feedback requires both owner and repository arguments. |
| `autonomous events` | `AutonomousBrain` event-ledger read path | Prints the run's safe append-only event ledger; no authority expansion is implied. |
| `autonomous requirements` | `AutonomousBrain.requirements` | Read-only projection of sealed carry-forward requirements. |
| `kernel doctor` | `inspect_kernel_environment` | Read-only local prerequisite inspection; intentionally performs no remote effect. |
| `kernel status` | read-only `KernelStore.status` | Opens existing kernel SQLite state read-only; refuses missing state. |
| `kernel plan` | `DeterministicFixturePlanner` + `persist_plan` | Writes deterministic fixture plan events to existing local kernel state. This is fixture planning, not provider cognition. |
| `kernel graph` | `graph_from_events` | Read-only event-derived work graph. |
| `kernel closeout` | `derive_technical_closeout` | Read-only closeout over retained local event/evidence state. |
| `kernel memory search` | `MemoryCatalogStore.restore` + `rank` | Read-only ranked retrieval from an immutable memory snapshot. |
| `kernel memory inspect` | `MemoryCatalogStore.restore` + `inspect` | Read-only metadata inspection; does not expose an unauthorized body. |
| `kernel memory expire` | `catalog.expire` + `MemoryCatalogStore.persist` | Appends expiration facts and writes a successor immutable snapshot. |
| `kernel context` | `ContextManifestStore.restore/get` | Read-only persisted context-manifest lookup. |

## Current runtime families

There is no single canonical eight-role autonomy runtime yet. Current executable behavior is split across these families:

1. **`runtime.py` / `HiveKernel`** — one serial lifecycle containing all eight roles. Its default `DeterministicBackend` synthesizes contract-output evidence and does not inspect or mutate a repository. With `ModelBackend`, every lifecycle role can receive a provider-backed model turn, but the generic kernel does not thereby acquire role-specific repository tools/effects.
2. **`mission.py` / `RepositoryMission`** — the real local repository vertical slice. Source and tests explicitly constrain its implemented repository roles to **Explorer, Builder, Curator**. It combines bounded Git, sandboxed commands/tests, policy, receipts, and independent Curator verification.
3. **`brain_kernel/*`** — all eight roles have executable local typed handlers and event-spine results, but the module explicitly states these handlers do **not** invoke a model, access a network, write a repository, promote a candidate, or reach the legacy mission runtime. Their effect requests are contracts/fixtures awaiting later integration.
4. **`mission_loop.py`** — richer evidence-driven orchestration/retry/remand behavior with partial role lanes. It is not the sole runtime authority and must not be counted as complete eight-role wiring.
5. **`autonomous_os.py`** — durable host-driven repository work, draft delivery, feedback, recovery, and PIT grading. It is a real effect path, but it is a separate run brain rather than an eight-role product runtime.
6. **`scheduler.py` / `workers.py`** — durable local queue/lease/recovery machinery. Workers execute the legacy repository mission rather than a canonical all-eight-role mission.

## Provider preflight

### OpenAI-compatible

Code path exists and is structurally exercised: `provider_from_env` creates `OpenAICompatibleProvider`, requires a model identifier and the named API-key environment, performs HTTPS `/chat/completions`, and fails before transport when the credential is absent. BASE-020 did not inspect or retain credential values.

### Anthropic

Code path exists and is structurally exercised: `provider_from_env` creates `AnthropicProvider`, requires model and `ANTHROPIC_API_KEY` (unless explicitly overridden), and uses the HTTPS `/messages` API. BASE-020 did not inspect or retain credential values.

### Codex subscription

A real local subscription adapter exists. `CodexSubscriptionProvider`:

- requires `chatgpt.com` and no API-key environment;
- resolves a local `codex` executable;
- invokes `codex exec` in a new temporary directory;
- uses `--sandbox read-only`, `--ephemeral`, `--ignore-user-config`, and `--skip-git-repo-check`;
- removes inherited environment names containing API keys, tokens, credentials, authorization, or secrets;
- supplies a strict outer output schema and re-validates the decoded Hive Mind model turn;
- never gives the Codex subprocess a repository checkout.

Exact-main CI structurally exercises the provider factory, scrubbed read-only ephemeral command construction, fail-closed response behavior, and subscription receipt identity. **Live subscription transport was not executable from this ChatGPT Classic connector-only environment because no local `codex` executable/session surface is exposed here.** This is retained as a blocker, not converted into proof of a live Codex call.

## Reusable capability versus incomplete wiring

### Reusable now

- Exact-candidate verification and isolated local Git/test execution.
- Evidence ledger, receipt binding, scheduler/lease/recovery primitives.
- Generic eight-role deterministic/model lifecycle and role contracts.
- Real repository read/write/test/commit/verification path for Explorer, Builder, Curator.
- All-eight-role provider-free kernel handlers and event-spine recording.
- OpenAI-compatible, Anthropic, and Codex-subscription provider adapters.
- Autonomous isolated host worktree, draft PR delivery, feedback handling, recovery, and PIT grading foundations.
- Bounded memory/context, courtroom, benchmark, and challenger/prompt-registry primitives.

### Incomplete or unwired

- No single runtime combines all eight roles with meaningful provider cognition **and** role-authorized tools/effects.
- Orchestrator, Architect, Integrator, Steward, and Optimizer are not implemented as real repository-execution roles in `RepositoryMission`.
- The all-eight-role brain-kernel handlers are intentionally provider/network/effect free.
- Role-first product-runtime consultation is not wired across all role execution paths.
- The `experiment run` public route is deliberately unavailable; a command name does not establish live evaluation capability.
- Optimizer learning/promotion components exist, but there is no canonical end-to-end challenger-generation/evaluation/promotion role runtime.
- Codex subscription transport has structural CI proof but no live BASE-020 subscription invocation from the available Classic environment.
- Competing runtime brains/state stores remain; later architecture/migration nodes must reconcile them instead of reimplementing existing foundations.

## BASE-020 conclusion

Current `main` contains substantial reusable autonomy machinery, but its strongest capabilities are split among separate runtimes. The truthful baseline is therefore **partial, heterogeneous wiring**, not “all eight agents are fully autonomous.” BASE-020 changes documentation/evidence only and preserves current product behavior.