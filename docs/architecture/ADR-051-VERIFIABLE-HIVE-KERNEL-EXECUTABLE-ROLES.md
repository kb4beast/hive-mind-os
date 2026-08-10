# ADR-051: Verifiable Hive Kernel executable local role contracts

## Status

Proposed Phase 7 candidate. The implementation is local and deterministic only; it
does not invoke a provider, access a network, alter prompt champions, or rewire a
legacy mission path.

## Decision

`brain_kernel.roles` defines the closed role protocol; the repository-cortex registry
implements all eight specialist roles. Every invocation binds one role identity,
authority-envelope digest, bounded context manifest, retained evidence references,
base/candidate identifiers, and a separately named executor identity. A mismatched
role, manifest, work, attempt, or authority digest fails before a result is emitted.

Each handler has a fixed allow/forbid capability contract and required output names.
Handlers produce deterministic `RoleResult` values whose digest binds every semantic
field. Results retain evidence references and an output-artifact reference. Curator
requires evaluator-isolated context. Integrator can only request Builder work for a
repair, and Optimizer cannot promote or change a champion.

`append_role_result` appends a validated result as a `role.result` event to the local
kernel hash chain. The reducer accepts it only for running work and verifies the
mission, work, attempt, executor, role, and result digest bindings. This event does
not transition work, execute an effect, or constitute verification/acceptance.

The repository adapter may register deterministic version-zero prompt artifacts for
all eight roles through the existing local `PromptRegistry`. Registration does not
promote a champion or invoke a provider.

`run_fixture_role_mission` is a deterministic local integration fixture. It creates
eight bounded running work items, gives every role its own context and executor
identity, and appends all eight results. It creates no effect receipt and leaves all
work unaccepted, so it cannot be mistaken for a delivered repository change.

`LocalWorkspaceAdapter` is the sole Phase 7 write adapter. It copies a caller-chosen
base directory to an isolated local candidate, rejects root and symlink escapes, and
writes only a registered byte payload when `EffectGateway` presents a matching local
capability token. The Builder/Curator fixture seals an `AcceptanceCheck` before the
gateway write exposes the candidate. It then checks a fresh Curator context without
Builder receipts or rationale and uses the existing `CuratorReview` to derive a
confined local verdict. The base directory remains unchanged.

The registry is deliberately separate from `IMPLEMENTED_REPOSITORY_ROLES` in the
legacy runtime. Advertising local kernel handlers does not make the legacy,
provider-capable repository mission execute additional roles or broaden authority.
The fixture-only adapter routes its effect through the existing local gateway and
binds Builder/Curator to sealed verification. It does not make the legacy mission
path executable.

## Consequences and rollback

The addition is limited to additive modules, their public exports, and focused tests.
Importing it creates no state or external side effect. A caller may create additive
local prompt-registration records and isolated fixture workspaces; rollback does not
delete historical records. No legacy event, provider configuration, or candidate
outside the caller-chosen local root is changed.

## Evidence obligations

Focused tests cover all eight executable handlers, separate executor/context identity,
result digest binding, Orchestrator write denial, Curator evaluator isolation,
Integrator's Builder-work request, Optimizer promotion denial, role/context mismatch
refusal, durable ledger/replay integrity, and local non-promoting prompt registration.
They also cover the all-role deterministic fixture ledger run, root-escape denial,
gateway-only isolated Builder write, and blind-first fresh Curator verification. The
remaining non-code Advocate, Cross-Examiner, Expert Witness, Curator, and Judge
dispositions remain open.
