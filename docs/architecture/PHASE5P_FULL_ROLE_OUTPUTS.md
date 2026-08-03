# Phase 5P full-role output contracts

## Decision

Phase 5P adds supplementary, package-private output envelopes for the Phase 5E Integrator, Phase
5F Steward, and Phase 5G Optimizer. It does not replace or reinterpret their original intake
envelopes. Each of the 22 previously absent outputs has a distinct schema version, exact source
scope digest, payload digest, evidence requirements, authority boundary, and fail-closed status.

## Invariants

1. The original Phase 5E/F/G intake validates before supplementary outputs compile.
2. Every output reconstructs the same exact request-scope digest as its source intake.
3. Every output ID binds role, field, and exact scope digest.
4. Unknown evidence remains unknown; structural records never imply execution.
5. Authority is `none`; execution and release authorization are false at every output boundary.
6. Optimizer metrics, comparators, regressions, experiments, and rollback remain unobserved or
   not-run. No protected holdout content is accessed.
7. The modules remain package-private and add no provider, tool, storage, scheduler, Git, runtime,
   credential, or deployment binding.
8. Installed-wheel verification must import the supplementary modules from the isolated wheel and
   reproduce all 22 outputs.

## Migration and rollback

This is an additive contract version. Consumers may opt in only after validating their original
intake and the supplementary envelope. Rollback is a normal revert of the Phase 5P files and the
corresponding Phase 5E-K inventory regeneration. Earlier evidence, failed runs, and debt records
must remain preserved.

## Limits

This decision supplies structural contracts only. It does not close external execution,
authenticated-independence, compatibility, recovery, evaluation, learning, release, production,
deployment, promotion, or superiority obligations. `B-OPS-08`, ADR-015, P14, and P20 remain
unchanged.
