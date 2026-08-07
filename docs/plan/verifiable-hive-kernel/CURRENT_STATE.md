# Verifiable Hive Kernel: Phase 0 Current State

## Scope and provenance

- Phase: 0 — Reground, adopt, and create an executable kernel baseline.
- Handoff source: `docs/plan/HIVE_MIND_OS_VERIFIABLE_HIVE_KERNEL_STANDALONE_HANDOFF.md`.
- Handoff baseline: `56cdf8b7a25294a0e1fbe73d8f732575e8c6b9a2`.
- Local `main` inspected: `ec3ab7e7277c2ecc13ba928d597fc9ad9f82ab1e`.
- Remote `origin/main` observed during Phase 0: `56cdf8b7a25294a0e1fbe73d8f732575e8c6b9a2`.

The local branch is ahead of the handoff baseline. The handoff therefore remains a
proposal and task source, not a substitute for current code or adopted contracts.

## Contract reconciliation

| Question | Current repository truth | Phase 0 disposition |
| --- | --- | --- |
| Next ADR identifier | `docs/architecture/ADR_INDEX.md` reserves ADR-044 | Create ADR-044, not the handoff's unavailable ADR-045 reference |
| `ADR-045-AUTONOMOUS-REPOSITORY-BRAIN.md` | Not present in the repository | Preserve as a blocking evidence obligation; do not invent content |
| Runtime role contracts | Eight contracts exist; only Explorer, Builder, and Curator are executable repository roles | Reuse and extend later through adapters; do not claim all roles are operational |
| Existing mission paths | `mission.py`, `mission_loop.py`, `mission_store.py`, and `autonomous_os.py` overlap | No migration in Phase 0; map and converge through additive adapters |
| Existing evidence and verification | Ledger, receipts, Curator, verifier, PIT, and prompt/experiment components exist | Retain as kernel-spine candidates, pending Phase-specific adapter tests |

## Baseline gate observations

The required baseline commands were started in the isolated Phase 0 worktree before
editing. Observations are intentionally not normalized into a passing claim:

| Gate | Observation |
| --- | --- |
| Editable install and compileall | Started successfully as part of the baseline command; no failure was emitted before the suite began |
| Full unittest discovery | Pre-edit baseline on Python 3.14: 456 tests in 499.144 seconds; 19 failures, 41 errors, and 5 skips. Failures span benchmark receipts, current-state audit, GitHub, governance, mission, mission-store, policy invariants, and the verifier example. Errors cluster in experiment artifacts, mission-store crash recovery, PIT oracle, and projections. |
| Ruff | Not installed in the local environment (`ruff` command unavailable). |
| Pyright | Existing error: `src/hive_mind_os/mission.py:2094`, optional operand `/` on `None`. |

No Phase 0 code change may weaken these gates or erase their pre-existing failures.

The full-suite result predates the additive doctor files. The doctor-specific focused
suite is maintained separately so the pre-existing baseline failure count is not
misrepresented as a Phase 0 regression.

## Local baseline repair provenance

The local repository contained user-authored repair commit
`b9ac2373e964dfe840fb63643b1b29b336eb1274` on
`codex/green-trunk-repair`. Phase 0 inspected and applied that local commit as
`880ca992d9f036cd82eec93a14a222d4af85dc44`. Its repairs verify historical benchmark
and experiment receipts through the existing immutable local archive tag instead of
restoring or modifying receipt files. It also closes local capability, sandbox-path,
and recovery accounting mismatches exposed by the baseline gate.

Two follow-up local repairs complete the same deterministic gate reconciliation:

- synchronize the Builder facade with its already committed package manifest;
- normalize copied example source and patch bytes before applying them on Windows.

These changes do not access a provider, remote Git, remote CI, a draft pull request,
or an existing receipt artifact. The final full-suite receipt is pending.

## Phase 0 implementation boundary

The only new runtime capability is the additive, read-only `hive-mind kernel doctor`
surface. It does not create a kernel database or move any existing state. The new
`brain_kernel` package must not import repository-cortex code.
