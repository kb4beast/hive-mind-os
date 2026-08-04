# P17 — Hard Isolation for Hostile Workloads

> **Withdrawn as an executable phase by P5.2 (2026-08-03).** Do not schedule this
> work. Its required external authority is retained in
> [Human Authority Gates](../architecture/HUMAN_AUTHORITY_GATES.md).

Status: withdrawn | Historical dependency: P03

## 1. Objective

Close `B-OPS-06` by adding a replaceable container, VM, or equivalent hard-isolation adapter
that enforces the typed sandbox policy against hostile code on supported platforms.

## 2. Required reading

1. `docs/plan/01_POST_P13_OVERVIEW.md`
2. `docs/plan/P03_SANDBOX_RUNNER.md`
3. `docs/architecture/ADR-007-PROCESS-SANDBOX-GATEWAY.md`
4. `src/hive_mind_os/sandbox.py`
5. `docs/plan/BLOCKERS.md` (`B-OPS-06`)

## 3. Prerequisites and authority

- Branch: `phase/P17-hard-isolation`.
- Define supported operating systems, isolation runtime, privilege boundary, and CI/manual
  test split in a new ADR.
- A human authorizes installation/use of the isolation runtime and any privileged helper.

## 4. Scope and design constraints

- Default-deny network with explicit destination/protocol grants.
- Read-only base image and explicit filesystem mounts; workspace and receipt roots separated.
- No ambient host secrets or credentials.
- Pin executable image and command identity by digest.
- Enforce CPU, memory, process, file, output, wall-time, and network budgets.
- Contain and kill descendants; prevent host process attachment and privileged escalation.
- Export signed receipts through a protected channel outside the guest.
- Retain P03 as a clearly labeled process-tier fallback; hostile workloads fail closed when
  the hard tier is unavailable.

## 5. Deliverables

- Hard-isolation ADR and adapter contract.
- At least one implementation plus platform capability detection.
- Adversarial corpus and conformance harness.
- Operational installation, update, image-pinning, cleanup, and incident runbooks.
- P17 audit, hostile-attempt receipts, rollback evidence, and court record.

## 6. Required tests

Attempt filesystem escape, undeclared reads/writes, network access, DNS tunneling, secret
discovery, executable substitution, symlink/reparse traversal, process escape, fork/process
bomb, CPU/memory/output exhaustion, timeout evasion, receipt tampering, and runtime absence.
Every denied attempt must fail closed with bounded cleanup and reachable receipts.

## 7. Exit criteria

- Deterministic conformance and full gates pass on every supported platform.
- Independent adversarial execution proves filesystem/network/secret denial, pinned images,
  bounded resources/descendants, protected receipts, and fail-closed fallback.
- The threat model states residual kernel, hypervisor, runtime, and side-channel risks.
- Separate Curator, Judge, and Orchestrator dispositions permit the exact candidate.

## 8. Evidence, rollback, and forbidden shortcuts

Retain runtime/image digests, policy manifests, attack corpus, raw outcomes, cleanup receipts,
audit, dissent, and supported-platform matrix. Rollback disables hostile execution and
retains process-tier mode only for trusted commands.

Do not represent subprocess checks, path validation, user namespaces alone, or an unpinned
container image as a hostile-code security boundary.
