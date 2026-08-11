# Provider-backed RoleRuntime

`hive_mind_os.brain_kernel.role_runtime.RoleRuntime` is the canonical adapter for
provider-backed cognition in the Verifiable Hive Cortex. It runs the fixed lifecycle
of orchestrator, explorer, architect, builder, curator, integrator, steward, and
optimizer through the existing structured `ModelBackend`.

Each invocation binds its mission/work/attempt identity, executor identity, authority
digest, context manifest, evidence and artifact references, role capabilities, and
required output names into the bounded prompt. `ModelBackend` retains provider-call
receipts and validates structured output before `RoleRuntime` emits a typed
`brain_kernel.contracts.RoleResult` whose output references are content-addressed.

Provider routing is explicit: a shared provider is the default and a role-specific
provider override is selected by the role. `provider_for()` exposes that selection for
diagnostics without invoking it. Same-model role identities are procedural separation,
not independent humans.

The runtime has no effect executor. Model-proposed actions remain proposals, and
`request_capability()` returns inert request metadata only. Forbidden actions fail
closed with `RoleCapabilityDenied`; authorization, durable effects, verification,
acceptance, merge, deployment, promotion, and protected-branch operations remain
separate adapters.

`run_mission()` requires every canonical role exactly once and in lifecycle order. It
passes prior typed results as bounded context, preserving cross-role handoff digests
without allowing a role to approve or execute itself.
