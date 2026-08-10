# Role Wiring Audit — BASE-020

## Binding

- Node: `BASE-020`
- Exact source `main`: `ffaaed5531ad4535a1fce59ffcf81b8442836c58`
- Exact source tree: `87a92782680a967afd29bceab218c61fc562a5e4`
- Plan fingerprint: `sha256:9769f9796efb351da9b764fd49983b1130adccc0b8592e42581714d3727f8b39`
- Claim: `34c8e3296348e9be265c128f45c0665c7461a42a` on `autopilot/base-020`

This audit classifies actual executable paths. A role name, prompt, manifest, fixture, planned capability, or synthetic contract output is not counted as a real repository effect.

## Verdict

All eight roles have current contracts and are reachable through the generic serial `HiveKernel`. When `--backend model` is selected, `ModelBackend` provides a structured model turn to each role in that lifecycle. That makes generic provider-backed cognition reachable, but it does **not** wire role-specific tools/effects into that runtime.

A separate current runtime, `RepositoryMission`, explicitly implements only **Explorer, Builder, and Curator** as repository-execution roles. A third runtime family, `brain_kernel`, has all eight executable typed local handlers, but its source explicitly prohibits model, network, repository-write, promotion, and legacy-runtime effects. Those handlers are therefore provider-free/effect-free executable fixtures/contracts rather than the finished autonomy runtime.

No single current product runtime gives all eight roles meaningful provider cognition, bounded role-authorized tools/effects, role-first consultation, recovery, independent acceptance, and learning.

## Classification matrix

The requested labels are non-exclusive. `fixture-only` below means an executable path exists whose semantic behavior is deliberately fixture/provider-free; it does not erase another generic model path for the same named role.

| Role | contract-only | model-backed | tool-backed | effect-backed | fixture-only | Current execution truth |
|---|---:|---:|---:|---:|---:|---|
| Orchestrator | yes | yes | no | no | yes | Generic `HiveKernel` deterministic/model turn; brain-kernel local handler can query/plan/request gates but explicitly has no provider/network/direct effect. Not a real `RepositoryMission` execution role. |
| Explorer | yes | yes | yes | yes | yes | Generic model turn exists. `RepositoryMission` performs real bounded repository reads/analysis/tests/commands; policy prevents mutation. Brain-kernel handler remains provider/effect free. |
| Architect | yes | yes | no | no | yes | Generic model turn exists; `mission_loop` can use architectural/design inputs, but there is no canonical role-specific repository tool/effect runtime. Brain-kernel handler only proposes typed design artifacts. |
| Builder | yes | yes | yes | yes | yes | Generic model turn exists. `RepositoryMission` has real isolated branch/write/command/test/commit effects under policy and receipts. Brain-kernel handler may only request isolated effects and cannot directly perform them. |
| Curator | yes | yes | yes | yes | yes | Generic model turn exists. `RepositoryMission` performs fresh-workspace independent verification, tests/diff inspection, and adoption/remand logic without candidate mutation. Brain-kernel handler remains provider/effect free. |
| Integrator | yes | yes | no | no | yes | Generic model turn exists. Brain-kernel Integrator can request contract tests/Builder work but is explicitly prohibited from writing/merging. No current real repository integration role path. |
| Steward | yes | yes | no | no | yes | Generic model turn exists; `mission_loop` contains stewardship/risk lanes, but no canonical operations-controller effect path is wired to the named role. Brain-kernel Steward only requests recovery/maintenance work. |
| Optimizer | yes | yes | no | no | yes | Generic model turn exists and experiment/benchmark/prompt-registry components are reusable, but the public experiment surface is deliberately unavailable and brain-kernel Optimizer cannot promote/change a champion. |

## Evidence from current code

### Generic all-eight-role path

`roles.DEFAULT_LIFECYCLE` contains all eight roles. `HiveKernel` constructs one `SpecialistAgent` for every lifecycle role and executes them serially. With no backend argument, `DeterministicBackend` emits synthetic `contract-output` evidence. With `ModelBackend`, the same role contract receives a provider-backed structured turn. This path does not itself bind role capabilities to repository tools/effects.

### Real repository mission path

`roles.IMPLEMENTED_REPOSITORY_ROLES` is exactly:

```text
Explorer, Builder, Curator
```

`PLANNED_ROLES` is every remaining role. Current tests assert this exact division. `RepositoryMission` composes bounded Git workspaces, sandbox execution, policy, receipts, model cognition where configured, and independent Curator verification.

### Brain-kernel all-role path

`brain_kernel.roles.KERNEL_IMPLEMENTED_ROLES` lists all eight roles, but that module's own executable contract states that its handlers do not invoke a model, access a network, write a repository, promote a candidate, or call the legacy mission runtime. The capability envelopes mostly express **requests** for effects, not direct effects. This is meaningful reusable contract/event-spine machinery, but it must not be represented as fully wired autonomy.

## Focused role-wiring validation retained from exact-main CI

Exact-main GitHub Actions run `31371653163` executed the full deterministic suite. The Python 3.11 log records **611 tests, 5 skipped, OK** and includes the focused assertions below as passing:

- `test_brain_kernel_roles.KernelRoleHandlerTests.test_all_eight_roles_are_executable_and_evidence_bound`
- `test_brain_kernel_roles.KernelRoleHandlerTests.test_fixture_mission_runs_all_roles_and_persists_separate_results`
- `test_brain_kernel_roles.KernelRoleHandlerTests.test_integrator_requests_builder_work_instead_of_patching`
- `test_brain_kernel_roles.KernelRoleHandlerTests.test_optimizer_cannot_promote_or_change_a_champion`
- `test_brain_kernel_roles.KernelRoleHandlerTests.test_orchestrator_cannot_write_or_accept`
- `test_brain_kernel_roles.KernelRoleHandlerTests.test_role_and_context_mismatch_fails_closed`
- `test_roles.RoleLifecycleTests.test_repository_lifecycle_lists_only_implemented_roles`
- `test_roles.RoleLifecycleTests.test_role_capabilities_resolve_to_policy_actions`
- `test_model_backend.ModelBackendTests.test_offline_backend_completes_all_roles`
- `test_model_backend.ModelBackendTests.test_subscription_receipt_identifies_session_auth_without_an_api_key`
- `test_model_provider.ModelProviderTests.test_subscription_provider_uses_a_scrubbed_read_only_ephemeral_codex_command`
- `test_cli_provider_config.DeliverProviderConfigurationTests.test_subscription_provider_configuration_needs_no_api_key_or_model`
- `test_mission.RepositoryMissionTests.test_model_backend_uses_the_same_capability_path`

The Linux skips were preserved. The workflow's Windows Python 3.12 job separately completed successfully.

## Consultation, learning, and independence truth

- Role-first consultation exists in the Autopilot control-plane contract, but is not yet a single product-runtime path used by all eight roles.
- Same-model role labels are procedural identities, not independent humans.
- Curator independence is materially implemented in the repository mission and exact-candidate verification paths, but generic eight-role execution is not by itself proof of independent acceptance.
- Optimizer/learning primitives exist across experiment, recursive-improvement, benchmark, autonomous/PIT, and prompt-registry code. They are not a single fully wired Optimizer lifecycle that autonomously creates, independently evaluates, and promotes challengers.

## Required downstream interpretation

Later nodes should **reuse** the verified primitives above rather than replace them, while treating the missing cross-runtime wiring as real implementation work. In particular, ARCH-100/ROLE-200 and role-specific nodes must not infer completed role autonomy from the existence of these contracts, fixtures, or generic model turns.