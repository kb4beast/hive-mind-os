# Verifiable Hive Kernel: Phase 7 executable roles

## Candidate implementation

This phase begins from `5711ab9` with a local-only role registry. It makes all eight
roles executable as deterministic, evidence-bound kernel handlers without presenting
them as legacy repository-mission actors. The handlers have no provider, network,
filesystem, Git, GitHub, prompt-promotion, or effect-adapter-registration capability.

`RoleInvocation` binds the requested role to an explicit bounded context manifest and
authority envelope. `RepositoryRoleHandlers` rejects cross-role context reuse and
produces a hashed `RoleResult`. Curator accepts only evaluator-isolated context;
Integrator requests a Builder item rather than patching; Optimizer cannot promote.
Validated results append idempotently to the local kernel event spine; replay refuses
forged result bindings. A result remains distinct from an effect or acceptance.
Version-zero prompts register through the existing local registry without setting a
champion or calling a provider.
A deterministic local fixture creates one running work item per role and appends all
eight identity-bound results; it deliberately produces no effect, verdict, or
accepted work.

The Builder/Curator fixture separately materializes a caller-chosen base into an
isolated candidate, routes the one candidate write through the local capability
gateway, and seals Curator's check before candidate access. Curator uses a fresh,
evaluator-isolated context and derives an `adopt`/`reject` verdict through the
existing local review contract. The fixture never accepts work or changes the base.

## Completion boundary

This completes the local executable-role implementation and fixture exit criterion.
It does not adopt or promote the phase: the independent courtroom dispositions in
ADR-051 remain open. No legacy runtime path is advertised as newly implemented.
