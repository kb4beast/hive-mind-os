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

[`DAG_AUTHORING_STANDARD.md`](DAG_AUTHORING_STANDARD.md) is the repository-neutral
normative standard for node contracts, scaffold ownership, ordering rules beyond raw
dependencies, round compilation, execution invariants, and token economy. `autopilot
dag-lint` is written against it and enforces the mechanizable subset — the standard's §8
states per requirement which rules are machine-checked and which are author-verified. Lint
errors block; lint warnings require a recorded justification.

The standard is **not yet bound to the `BUILD_DAG` flow.** Binding the DAG-build task to
the standard by digest — pinning it at `init`, materializing it in the target repository,
and forbidding the task from reporting success without a zero-error `dag-lint` receipt — is
specified in [`runbooks/PRODUCT-GENERIC-DAG.md`](runbooks/PRODUCT-GENERIC-DAG.md) §3.1-3.4
and is **not implemented**. The `DAG-BUILD-<digest>` task prompt emitted today does not
name the standard. Until that change lands, conformance for a DAG built by that task is an
authoring discipline plus a separately run `dag-lint`, not a product gate.

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

### Three-tier runtime authority

The runtime has three authenticated tiers: one per-OS-user host kernel arbitrates the
aggregate primary, sidecar, and validation budget across repositories; one repository
arbiter owns transport, target-watermark, claim, publication, and conflict truth; and one
execution namespace owns a particular DAG's receipts, blockers, repair journals,
snapshots, launch bindings, and validation state. Linked worktrees and independently
registered clones resolve the same repository arbiter and execution directory instead of
creating another local scheduler. A malformed or unsupported Git/runtime locator fails
closed.

Resolve the exact coordinates once. Do not substitute `.` or the implicit `default`
namespace in a copied command:

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
STATE_DIR="<absolute repository coordination root>"
HOST_RUNTIME_DIR="<absolute canonical per-user host runtime>"
EXECUTION_NAMESPACE="<exact execution namespace>"
HOST_ID="<canonical authenticated host id>"
PYTHON="<absolute interpreter from the sealed execution identity>"
AUTOPILOT=("$PYTHON" "$REPO_ROOT/.autopilot/bin/autopilot.py" --repo-root "$REPO_ROOT" \
  --state-dir "$STATE_DIR" --host-runtime-dir "$HOST_RUNTIME_DIR" \
  --execution-namespace "$EXECUTION_NAMESPACE")
SNAPSHOT=("$PYTHON" "$REPO_ROOT/.autopilot/bin/github_snapshot.py" --repo-root "$REPO_ROOT" \
  --state-dir "$STATE_DIR" --host-runtime-dir "$HOST_RUNTIME_DIR" \
  --execution-namespace "$EXECUTION_NAMESPACE")
```

Before a repository with existing attended cards or task bindings uses this version,
quiesce its controllers and run the explicit evidence-preserving migration once:

```bash
"${AUTOPILOT[@]}" runtime-authority-migrate --mode dry-run \
  --actor <stable-operator-identity>
"${AUTOPILOT[@]}" runtime-authority-migrate --mode apply \
  --actor <stable-operator-identity>
"${AUTOPILOT[@]}" runtime-authority-migrate --mode verify \
  --actor <stable-operator-identity>
```

The migration binds the authority directory to the configured repository, inventories a
frozen set of linked worktrees, archives the exact legacy authority, ledger, and card bytes
by digest, and creates immutable per-task cards. Provably expired secondary claims and
leases are retired only after their exact bytes and source provenance are durably archived;
they are never imported as live authority. Live, malformed, identity-mismatched, linked,
tampered, or incomplete evidence fails closed for explicit reconciliation. A repository-
bound readiness marker is published only after both bootstrap and attended migration are
complete, so ordinary commands cannot observe a half-initialized authority directory.
The local `actor` label is audit provenance, not cryptographic authentication. The
command does not cancel an external host session.

Before READY only, `--mode rollback-before-ready --reason <reason>` installs an
append-only `ABORTED_FENCED` receipt and prevents the CLI from resuming that exact
operation. It deliberately does not restore retired claims, quarantined ledgers,
attended authority, the repository registry, or the Git-common runtime locator: those
are monotonic evidence, and reactivation would create split authority.

Acquire scheduling evidence through the checked-in helper:

```bash
"${SNAPSHOT[@]}" --reconcile --actor <stable-operator-identity>
```

Before `git fetch`, `gh`, or any other remote read, the helper invokes
`snapshot-observation-begin` and reserves a monotonic shared `observation_id`.
`install-github-snapshot` must present that exact ID and matching canonical target.
Beginning a newer observation invalidates the old admission generation, so a slower
older read is refused if it finishes after the newer reservation. Reconciliation must
consume the installed digest before a fresh dispatcher release can be issued.

For an installed controller, the host runs:

```bash
"${AUTOPILOT[@]}" orchestrate --host-id "$HOST_ID" \
  --request "actual user message" --apply --json
```

The returned task effects contain a deterministic launch instruction ID, task title,
node/branch/target, explicit authority mode, expected artifact, host adapter names, and
canonical worker prompt. Titles include node, action, authority mode, and instruction
digest so operators and recovery logic can distinguish tasks without guessing.
Before creation, the host runs `prepare-launch`. After the external task exists, it runs
`bind-launch`, producing append-only `PREPARED -> CREATED -> BOUND` evidence. A restart
consumes the binding; a prepared but unbound launch searches by the deterministic title
before creating anything. The host polls the active set, sends recovery answers back to
the same task, and records a capability-bound `RELEASED` transition tied to the exact host,
task, event ID, and cursor after `wait_threads` reports a terminal result. There is deliberately no raw
CLI that can assert host terminal evidence. A terminal label or free-form reference alone
cannot release a live binding.

The host distinguishes a stable `resource_key` (repository, target branch, lifecycle,
and node) from the target-specific `launch_instruction_id`. Preparation allocates a
monotonic `authority_epoch`. Bind, progress, relay, terminal, and release operations
present the exact instruction/resource/epoch fence; a stale generation is refused. A
new instruction cannot silently evict an active one, and omission from a later contract
is not cancellation proof. Terminal host evidence or an explicit audited
`fence-launch` transition is required before a successor can own the same resource.

`claim` returns an exact nonce-backed `claim_id`; heartbeat, fail, release, and complete
must carry it together with the same launch instruction, resource key, and authority
epoch. Hosted validation acquire, renew, and release carry that claim/launch fence;
`validation-lease-acquire` returns the exact `lease_id` required by renewal or release.
Reusing an owner label cannot mutate a later generation.

Dispatch, hosted claim transitions, and public round integration serialize on one shared
dispatcher-admission lock. Each release carries a monotonic admission epoch, the live
repository/target/plan identity, its exact wave, and an authenticated provider ceiling.
Primary, sidecar, and validation reservations consume one per-user host budget across
every registered repository; the current App Server ceiling is conservatively one unless
stronger expiring capability evidence is sealed. A serial node occupies the primary wave alone. Active
host demand is persisted in `host-scheduler.jsonl`. Deterministic weighted round-robin
issues expiring single-use grant IDs, so a barrier wider than capacity advances in
bounded batches and a small execution cannot starve behind a wide execution from either
the same or another repository. No grant returns `WAITING_FOR_CAPACITY` with an
authenticated wake observation; it never becomes an integrity failure or a request to
open one session per ready sibling. Unused grant expiry restores only its exact candidate.
Active claims freeze replacement of the release; a target, plan, snapshot observation, or
reconciliation change invalidates it once claims settle. The public
`run-round --release-id <exact-id>` path refuses stale or mismatched authority, requires
no active worker claims, and preflights the exact receipt head for every released node
before triage or Git effects. A partial wave returns `PENDING` without healing,
reconciliation, merge, push, or validation. Recovery must run separately, followed by a
fresh snapshot/reconciliation and dispatcher release. A whole wave performs integration
plus validation as one fenced transaction. The public path offers no skip-validation or
caller-selected privilege switch.

Publication validation also requires an independently attestable sandbox that denies
candidate code access to repository authority, credentials, and network. The current
Windows environment cannot prove that boundary, so its broker fails closed before
running candidate tests and cannot mint `VALIDATED`; there is no direct-runner fallback.

An attended-host fence revokes Hive Mind authority but cannot prove or force cancellation
of the real Codex chat. Send the corresponding stop message and treat the external
session as untrusted until it acknowledges; current claim and launch fences still guard
controller-mediated effects.

The repository CLI emits and records host-effect contracts. The checked-in
`.autopilot/bin/host_execution.py` loop then executes those contracts through an
injected host adapter: it creates the complete parallel-safe wave before its first
wait, capability-binds every host event, polls to terminal state, answers recoverable
attention through the safe resolver, and returns a typed blocker after bounded
no-progress cycles. The adapter is responsible only for the chat product's private API;
the orchestration behavior is Hive Mind OS code, not an optional prompt convention.

For adapters that can lifecycle-manage every task, the visible cohort may be broader than
the write-authorized wave: mandatory active and recovery tasks, every node in the current
dispatcher release, then deterministic read-only `PREPARATION_ONLY` tasks only while
capacity remains. An existing recovery task never suppresses mandatory released work.
`START NOW` and `START TOGETHER NOW` govern claims and writes. Closure-first prioritizes
which result is collected first; every created task remains managed and is polled to
terminal state.

The attended Codex adapter cannot observe a preparation-only lifecycle and exposes no
sidecar API. Its contract therefore sets both optional transports off: no
`PREPARATION_ONLY` tasks and no sidecars are created. Mandatory active, recovery, and
released work is never silently truncated; if it exceeds the hard total capacity, host
validation fails before creating or binding a task.

For a provider with an exact, crash-recoverable create protocol:

- primary node task: `create_thread`;
- bounded sidecar: `multi_agent_v1.spawn_agent`;
- primary-task wait: `wait_threads`;
- answer/resume: `send_message_to_thread`.

Primary work must not silently fall back to nested subagents. If durable task creation is
unavailable, report a typed host-capability blocker and preserve the release.

The currently pinned Codex App Server protocol does not expose an atomically observable
thread-create idempotency token. Its adapter therefore advertises
`autonomous_launch=false`: it can observe and recover an existing task but an unfinished
execution returns `WAITING_FOR_HOST` rather than risking a duplicate fresh launch.

The host kernel arbitrates Hive Mind session permits across registered repositories. It
does not claim OS-level CPU, memory, disk, network, CI, or process-cancellation control,
and it cannot forcibly cancel an external chat; those remain external host capabilities.

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
