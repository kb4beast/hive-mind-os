# ADR-007: Process Sandbox as the Command-Execution Gateway

- **Status:** Proposed for independent P03 court review
- **Date:** 2026-07-27
- **Case:** `CASE-P03-PROCESS-SANDBOX-GATEWAY`
- **Originating work order:** `docs/plan/P03_SANDBOX_RUNNER.md`
- **Prior decisions:** ADR-003 and ADR-006
- **Capability maturity:** structurally prototyped

## Context

The runtime has typed tool-intent and tool-receipt contracts plus a file-backed receipt
validator, but it has no sanctioned executor connecting those contracts to a real process.
Later Git and vertical-slice phases need a bounded command gateway without granting ambient
shell authority.

The original schemas also lack two facts required by P03. A command intent cannot represent
its argument vector or identify path arguments, and a receipt cannot bind the executed
argument vector, exit status, duration, captured streams, sandbox policy, or enforcement
identity. Both schemas reject unknown properties, so encoding these facts in free-form
description text would be unverifiable.

## Court record

The P03 Builder/Integrator advocates a single stdlib process gateway with typed inputs,
pre-spawn policy and allowance checks, exact output artifacts, and independently
verifiable receipts. The complete candidate must be cross-examined by a separate Curator,
assessed for completion and rollback by a separate Orchestrator, and receive an independent
Judge disposition of `adopt`, `adapt`, `defer`, `reject`, or `quarantine`. Their exact-SHA
findings belong on the P03 pull request; until that review, this ADR remains proposed.

No external-source content is asserted by this decision. Its evidence is the canonical P03
work order, the existing local contracts and ADR-003, executable tests, a clean audit
artifact, and the final independent pull-request review. Existing source-ingestion and
licensing obligations remain assigned to P12.

### Initial candidate appeal

The first consolidated review rejected exact candidate
`68f061396547ec9d1d89b056c76370035e5173ac`; green local and GitHub checks did not override
three reproduced counterexamples:

- an early-exiting parent left a background descendant alive or retained its pipes past the
  configured deadline, yet emitted a successful receipt;
- synchronized calls overbooked one shared episode allowance; and
- digest, confinement, and embedded-NUL failures could bypass `sandbox.denied` evidence or
  reach raw process creation.

The repaired challenger applies one absolute deadline to parent execution, process-tree
liveness, and pipe draining; reserves allowance under a lock; rejects NUL before spawn; and
routes every reproduced pre-spawn denial through the append-only ledger path. The adverse
candidate and dissent remain preserved in Git history and the P03 pull request.

## Decision

Add `SandboxSpec` and `SandboxRunner` as the only sanctioned command-execution API for new
runtime work.

The runner:

1. validates a canonical, digest-bound command intent;
2. obtains a policy decision for `Action.RUN_COMMANDS`;
3. checks the fixed episode allowance before process creation;
4. resolves an allowlisted executable and every caller-declared path argument;
5. rejects traversal, absolute/nonportable paths, and resolved symlink escapes;
6. executes an argv list with `shell=False`, a fixed working root, closed stdin, and an
   explicitly allowlisted environment;
7. bounds wall time and captured bytes, killing the process tree on timeout;
8. writes stdout, stderr, and the receipt atomically under a trusted root outside the
   executable workspace;
9. validates the receipt against the catalog schema and exposes a content-addressed
   `ReceiptReference` accepted by `FileReceiptValidator`.

Extend the version-1 schemas without weakening legacy validation:

- `tool-intent.command` contains nonempty `argv` and unique, one-based `path_args`;
- a command-kind intent must contain `command`;
- `tool-receipt.execution` binds argv, exit code, duration, outcome, per-stream digest,
  byte count and truncation flag, sandbox-spec digest, and runner identity;
- `execution` remains optional for historical non-P03 receipts, while every receipt emitted
  by `SandboxRunner` includes it.

The sandbox-spec digest binds the resolved root, declared writable paths, executable and
environment allowlists, wall/output limits, and optional POSIX CPU/memory limits.

## Enforcement tiers and residual limits

This is a process-tier control, not a container, VM, WASM runtime, or security boundary
against a hostile allowed executable.

- POSIX starts a new session, kills the process group on timeout, and applies configured
  `RLIMIT_CPU`/`RLIMIT_AS`.
- Windows starts a new process group and uses `taskkill /T /F`, with a Toolhelp
  parent-process snapshot and direct termination as fallback. It does not use a Job Object
  or implement CPU/memory limits.
- The environment is scrubbed, but the process tier does **not** block network syscalls.
- Declared path arguments are confined and replaced with their checked resolved targets.
  An allowed program can still synthesize an undeclared absolute path internally.
- POSIX descendants remain bounded while they stay in the runner-created process group. A
  hostile descendant that creates a new session can escape that process-tier group; that
  case belongs to the hard-isolation obligation in `B-OPS-06`, not to a production claim.
- `writable` records and validates intended in-root write locations for policy evolution,
  but this tier does not impose filesystem ACLs. Container/VM enforcement must convert that
  declaration into a real mount or ACL policy before hostile-code isolation is claimed.
- Output artifacts are byte-capped per stream. Bytes beyond the cap are drained and
  discarded with `truncated=true`; they are never silently represented as complete.
- The trusted receipt directory is outside the configured workspace, but process-tier
  checks alone do not make local evidence externally authenticated or append-only.

Accordingly, this ADR does not establish hard filesystem isolation, network isolation,
provider authenticity, production readiness, or a non-bypassable migration of pre-existing
audit subprocesses.

## Threats and controls

| Threat | Control | Residual |
|---|---|---|
| Shell injection | argv list and `shell=False` | Allowed executable semantics remain trusted |
| PATH substitution | Resolve executable to a real path; compare normalized basename to allowlist | Allowlist does not pin executable bytes |
| Path traversal or symlink escape | Portable path grammar plus resolved-root containment | Undeclared paths synthesized by a program are not intercepted |
| Ambient credentials | Empty-by-default environment allowlist | Explicitly allowlisted values can appear in child output |
| Hung command or descendant | One absolute deadline covers parent wait, tree liveness, and pipe drain; then POSIX group / Windows snapshot-backed tree kill | A hostile POSIX `setsid` escape and Windows snapshot races require the hard tier |
| Unbounded captured output | Per-stream byte cap and explicit truncation receipts | Process continues while excess bytes are drained until timeout/exit |
| Forged or substituted evidence | Trusted root outside workspace, exact artifact/receipt digests, atomic publication | Local process-tier evidence is not externally signed |
| Self-verification | Runner identity must differ from actor identity | Structural identity is not yet cryptographic |
| Budget/policy bypass | Both checks occur before executable resolution and spawn; spawn count is tested | Existing out-of-scope subprocess callers are not migrated here |
| Partial publication | Artifacts may remain orphaned, but no receipt reference is published until receipt write succeeds | Orphan cleanup is deferred operational work |

## Compatibility and migration

Historical non-command intents and receipts continue to validate because the new objects are
optional outside command intents. A version-1 intent with `kind="command"` but no typed
`command` object now fails intentionally. No such repository fixture or runtime caller
existed before P03.

New phases must use `SandboxRunner`; `current_state_audit.py` remains an explicitly
out-of-scope legacy executor and must not be cited as proof that the gateway is globally
non-bypassable. P04 may depend on the runner only after P03 merges.

## Acceptance evidence

`tests/test_sandbox.py` covers:

- a successful command with schema-valid output accepted by `FileReceiptValidator`;
- canonical intent mutation rejection;
- executable, traversal, symlink, policy, and allowance denials before spawn;
- empty-by-default and explicit environment propagation;
- process-tree timeout with a failed receipt;
- early-parent-exit background-child timeout;
- exact capped-output bytes, digest, and truncation flag;
- atomic allowance reservation under concurrent calls;
- ledger evidence for invalid-digest, confinement, and NUL denials;
- interrupted publication without a receipt claim;
- deterministic nonvolatile receipt content;
- golden intent/receipt contract fixtures; and
- rejection of a trusted receipt store inside the workspace.

The final candidate must also pass the full suite, schema catalog, Ruff, Pyright, a concrete
runner/validator smoke, the P03 audit, and exact-head GitHub checks.

## Rollback

Revert the P03 implementation and schema extensions before P04 depends on them. Preserve
this ADR, emitted receipts, audit evidence, rejected candidates, and independent dissent.
If a receipt has already been used downstream, rollback is an additive superseding
decision; never delete or rewrite that evidence.

## Ownership and follow-up

- Integrator owns schema and validator compatibility.
- Steward owns process termination, resource bounds, atomic publication, and Windows/POSIX
  divergence.
- Curator owns independent reproduction and residual-risk review.
- P04 owns adoption by the Git adapter.
- Later container/VM work owns hard filesystem and network isolation.
- P07 owns secret-scoped execution and redaction.
- P08 owns structural identity independence.
- P11 owns durable operational monitoring and orphan cleanup.
