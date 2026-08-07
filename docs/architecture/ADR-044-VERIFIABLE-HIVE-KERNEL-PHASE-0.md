# ADR-044: Verifiable Hive Kernel Phase 0 Baseline

## Status

Proposed. This record authorizes no new remote, secret, spend, merge, deployment, or
policy authority. Its implementation is limited to an additive, read-only local
diagnostic surface while an independent courtroom disposition is still required.

## Context

The supplied Verifiable Hive Kernel handoff calls for a Phase 0 baseline before new
kernel behavior. Its declared baseline is `56cdf8b7a25294a0e1fbe73d8f732575e8c6b9a2`.
The local `main` inspected for this phase is
`ec3ab7e7277c2ecc13ba928d597fc9ad9f82ab1e`, so current repository contracts take
precedence over the handoff where they conflict.

The handoff also lists `ADR-045-AUTONOMOUS-REPOSITORY-BRAIN.md` as required reading.
That record is unavailable. The adopted ADR index instead states that `ADR-044` is the
next available identifier. This ADR records the discrepancy; it does not invent the
missing record or treat it as evidence.

## Decision

Add `hive-mind kernel doctor` as a read-only diagnostic for an additive
`hive_mind_os.brain_kernel` package. It reports, without exposing secret values:

- supported Python and Git availability;
- Git worktree cleanliness and protected-branch verification uncertainty;
- state-directory usability without creating the state directory;
- local model configuration validity and credential availability by environment name;
- whether the doctor command inventory still matches constitutional CI.

The doctor performs no network request, provider request, state-directory creation,
Git write, or remote-protection assertion. A missing local tool or unavailable remote
protection is reported as a condition, never converted into success.

`brain_kernel` remains repository-cortex-neutral. A static test rejects imports from
`hive_mind_os.cortex` so later repository-specific adapters cannot reverse the
dependency direction.

## Evidence and courtroom obligations

| Item | Status |
| --- | --- |
| Supplied handoff source | Preserved at `docs/plan/HIVE_MIND_OS_VERIFIABLE_HIVE_KERNEL_STANDALONE_HANDOFF.md`; SHA-256 `539ccb2f6918f87860ecbbc8b0732523335a988e256e63df22e7291b9a05ff3d` |
| Local repository truth | Recorded in `docs/plan/verifiable-hive-kernel/CURRENT_STATE.md` |
| Advocate, cross-examiner, expert, and independent judge | Open obligations; this implementation must not claim adoption or phase completion until they are recorded |
| Missing ADR-045 source | Blocking evidence obligation; do not infer its contents |

## Consequences

The diagnostic capability is reversible by removing the additive package and CLI
route. Existing mission, scheduler, verifier, policy, ledger, learning, and delivery
paths retain their current behavior. No persistent kernel state is introduced in this
phase.

## Acceptance and rollback

The executable acceptance checks are `tests/test_brain_kernel_doctor.py` and the
existing full local CI commands. Rollback removes the doctor package, CLI route, this
ADR, and the Phase 0 planning documents; it does not modify existing runtime state.
