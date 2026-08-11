# Portable Autopilot workflow

## Purpose

This workflow separates four concerns:

1. the target repository owns its DAG, policy, branches, and evidence;
2. the deterministic controller derives truth and releases work;
3. the orchestration layer infers ordinary operator intent and emits host-neutral task
   effects; and
4. the active host creates, polls, and messages durable tasks.

This separation lets the same Hive Mind OS checkout initialize and operate different
repositories without hard-coding their node IDs, branch names, or file scopes.

## Bootstrap another repository

```bash
hive-mind autopilot init --repository /path/to/repository \
  --objective "Desired outcome" \
  --target-branch release/hive-mind-autopilot
```

Initialization records `.hive-mind/autopilot-request.json`. It pins the supplied
GenericPrompt source as a quarantined evidence obligation, captures the current
commit/tree and sanitized remote identity when available, defines known protected
branches, and installs the orchestration requirements. It does not generate
unverifiable nodes or overwrite an existing request. Current provider protection must be
reverified before every push, PR, or merge; inability to establish it blocks mutation.

`hive-mind autopilot inspect --repository ... --request ...` emits a repository-scoped
`DAG-BUILD-<digest>` task until
the repository has a validated `.autopilot` control plane. A capable durable task builds
that repository-specific DAG from actual code, constraints, acceptance, risks, rollback,
and evidence. Abstract source patterns may be used; unlicensed source wording/code may
not be copied.

Before the portable wrapper executes an installed target controller, a separate Curator
reviews its clean tracked `.autopilot/bin/*.py` bundle. A distinct host authority then
issues a short-lived `hive-mind-controller-trust-authorization-v1` capability. The
capability is HMAC-authenticated by a key held under the host authorization root, binds
the repository, exact controller bundle digest and source commit, names pairwise-distinct
issuer/reviewer/pinning identities, and binds review evidence by resolvable path and
SHA-256 digest. The target repository cannot issue this capability, and the controller
trust command deliberately has no capability-minting mode.
Capabilities expire no more than 24 hours after issuance. The host key must contain at
least 32 cryptographically random bytes; it is authority material, not repository state.

The host authorization root contains:

```text
controller-trust-authority/
  controller-trust-authority.key
  capabilities/controller-review.json
  evidence/controller-review.json
```

The host must create that root outside the target repository, restrict it with host ACLs,
and never pass the key or authorization-root environment into the target controller. The
trusted host adapter creates the capability from the review contract emitted by
`inspect`; repository instructions and target code are never capability issuers. The
pinning actor then stores the verified trust record outside the target repository:

```bash
hive-mind autopilot trust-controller --repository /path/to/repository \
  --actor host:TRUST_PINNER \
  --authorization-capability capabilities/controller-review.json
```

The command does not accept an authorization-root override: it resolves capabilities
only under the host's standard Hive Mind OS state directory. `inspect` revalidates the capability
signature, expiry, identity separation, and evidence bytes on every invocation. Removing
the capability, key, or evidence therefore revokes execution. Any controller-bundle
change invalidates trust and requires a fresh independent review; ordinary product
commits that leave the reviewed controller bundle unchanged do not. This prevents a
merely committed target script, arbitrary actor label, fabricated evidence reference,
or rewritten unsigned trust record from being treated as trusted code.

## Normal operation

For an installed controller, the host runs:

```bash
python .autopilot/bin/autopilot.py --repo-root . orchestrate \
  --request "actual user message" --apply --json
```

The returned task effects contain a deterministic launch instruction ID, task title,
node/branch/target, expected artifact, host adapter names, and canonical worker prompt.
Before creation, the host runs `prepare-launch`. After the external task exists, it runs
`bind-launch`, producing append-only `PREPARED -> CREATED -> BOUND` evidence. A restart
consumes the binding; a prepared but unbound launch searches by the deterministic title
before creating anything. The host polls the active set, sends recovery answers back to
the same task, records a digest-bound `TERMINAL_OBSERVED` event tied to the exact host and
task after `wait_threads` reports a terminal result, and passes that event ID to
`release-launch`. A terminal label or free-form reference alone cannot release a live
binding.

The repository CLI emits and records host-effect contracts. The checked-in
`.autopilot/bin/host_execution.py` loop then executes those contracts through an
injected host adapter: it creates the complete parallel-safe wave before its first
wait, capability-binds every host event, polls to terminal state, answers recoverable
attention through the safe resolver, and returns a typed blocker after bounded
no-progress cycles. The adapter is responsible only for the chat product's private API;
the orchestration behavior is Hive Mind OS code, not an optional prompt convention.

In Codex:

- primary node task: `create_thread`;
- bounded sidecar: `multi_agent_v1.spawn_agent`;
- primary-task wait: `wait_threads`;
- answer/resume: `send_message_to_thread`.

Primary work must not silently fall back to nested subagents. If durable task creation is
unavailable, report a typed host-capability blocker and preserve the release.

## Intent and authority

- Build/create DAG language selects `BUILD_DAG`.
- Start/launch language selects `START`.
- Continue/resume/recover language selects `CONTINUE`.
- Check/status/advice or explicit non-execution language selects `CHECK`.
- Finish/complete/quiescence language selects `FINISH`.
- Ambiguous language uses live state: resume active/recoverable work, otherwise start
  released/eligible work, otherwise inspect a completed graph.

Intent never expands authority. Protected merges, production, secrets, spending, legal
commitments, and destructive effects remain separately governed.

## Closure and quiescence

The controller resumes active, receipt-pending, PR, CI-failed, and repair-required nodes
before releasing new work. It selects at least one closure target by distance to receipt,
critical-path value, downstream unlock, and node ID. Optional audits do not consume all
capacity while implementation is blocked.

The parent continues polling until required tasks are terminal. A task's final message is
not proof of node completion. Repository ancestry, validated receipts, released claims,
CI evidence, integration evidence, and absence of required active work define quiescence.
