# Generic portable DAG executor

The executor accepts only canonical, compiler-qualified plan bytes and an
`AuthorizedOneRun` produced after external attestation, issuer verification, and
host-owned nonce consumption. It is subject-neutral: every physical operation is
performed through an injected host adapter and a durable `HostRuntime` journal.
Prepared, attested, verified, and authorized stages are opaque process-local
capabilities; their public constructors reject, and every consumer revalidates an
integrity seal. The host receives the complete signed review, frozen-host, and
issuer proof plus all five principal identities. Its durable request and lease
bind the activation and proof digests; manifest, repository, request, target,
candidate parent/commit/tree/content, and execution-client identities; issuance
and expiry; the protected-merge denial; and the nonce digest. A durable host
activation claim binds that proof and nonce to one create idempotency key,
subject, and observed host identity before host preparation, so another create
against the same journal fails closed even after restart.
Message, cancellation, and checkpoint operations accept only the exact lease
retained as the successful response for that claimed create/adoption; a merely
field-valid caller-created lease cannot cross an adapter boundary.
Activation claims derive their proof, nonce, candidate, and request bindings
from the validated capability and exact runtime-built request. Public callers
cannot append host outcomes or manufacture claims from scalar fields. Host
creation accepts the exact signed canonical plan bytes and derives subject,
nodes, authority digest, and required capabilities from them; `generation_id`
is retained only as provenance and is not treated as an authority source.
Checkpoint authentication matches the successful message request containing
the complete lease document, node, and input digest, so a repeated host
`lease_id` cannot replay a receipt from another activation.
The internal seal is deliberately classified as `trusted-process-integrity-only`:
Python code already executing in the same interpreter can inspect module-private
state, so it is not claimed to be cryptographically unforgeable against hostile
in-process code. External signature custody, the host-owned nonce CAS, and an
isolated host adapter remain the authority and security boundaries.

Nonce reservation returns a canonical externally signed receipt. After process
loss, the caller freshly parses every activation artifact, repeats all external
signature verification, and calls `restore_one_run` with that receipt; it does
not consume the nonce again. The capability is a durable bearer at that point.
Preventing concurrent effects across independent journal databases therefore
still requires the host-owned global nonce/run journal and adapter-side
idempotency. The process-local HMAC makes no global-single-run claim.
The host and execution journal writer guards are likewise trusted-process
encapsulation, not cryptographic defenses against hostile in-process code.
Restart authentication assumes exclusive, trusted custody of the SQLite files;
an attacker able to rewrite storage and recompute chains is outside this claim.
Every compound journal verification uses one SQLite read snapshot across all
related tables, and pure result selection remains inside that snapshot. A
concurrent valid commit cannot make a reader combine old events with new claims
and report false corruption. Writers finish verification before acquiring their
`BEGIN IMMEDIATE` transaction, so verification never upgrades a live read
snapshot into the terminal compare-and-swap.
Host operation admission uses a single SQLite compare-and-swap transaction;
create, message, checkpoint, cancellation, and adoption aliases are durably
collapsed onto their canonical activation or lease/node identity. Exact aliases
converge, while conflicting node input, checkpoint identity, cancellation
reason, or adoption rebinding fails before an adapter effect. Only the caller
that inserts the canonical intent owns the adapter call. Global exclusion across
independent stores remains the external nonce ledger and adapter's obligation.
Separate handles to the same store also converge: an exact alias waits for the
durable owner's terminal record until its bounded settle timeout. Process-local
ownership is not evidence that another handle has crashed. If no owner publishes
a terminal record, recovery is required and the effect is not retried.
The public execution journal can record inert initialization for read-only
status fixtures, but host-backed progress and terminal events are
executor-owned, preventing a caller-built completed run from being trusted.
Run completion is sealed against the exact lease in the host journal only after
all leased node receipts and canonical checkpoints exist. That atomic seal and
the typed cancellation claim are mutually exclusive: a committed cancellation
becomes `run.cancelled` with its durable reason, an ambiguous cancellation keeps
the run blocked, and completion prevents any later cancel adapter call.

Before dispatch it checks the exact plan, standard and compiler identities,
available adapters, live authority through the one-run deadline, explicit
capability grants, positive wall/tool admission capacity, and the compiler's
declared concurrency limit. The same admission runs again at the public host
boundary. Effect classes have a closed vocabulary and all external classes
require explicit external-effect authority. The plan request, repository, base
commit/tree, and target branch must equal the activation claims; the current
repository-scoped activation version rejects non-repository plans. Protected-
merge operations are never delegated. A not-yet-valid authorization fails
before execution-journal initialization, including an in-call clock rollback;
an exact already-authenticated `COMPLETED` or `CANCELLED` journal terminal may
still be returned because that read-only lookup grants no live authority.
The run journal records a hash-chained initialization and node intent before
any worker starts. Runtime reconciliation of model calls, tokens, cost, and
complete per-node wall/tool counters is not implemented because the host
receipt contract does not carry those counters; this candidate therefore makes
no enforced-budget or all-dimension metering claim.

For each compiler round, all eligible calls are submitted before results are
polled. Every worker receives the same frozen run manifest plus only its node
delta and direct-dependency output digests. Successful siblings checkpoint even
when another result is blocked. Restart re-observes the complete executable and
adapter identity, trust-evidence digest, cleanliness, and required capabilities
with a fresh poll identity. This includes a cached successful host create when
the execution journal crashed before recording `host.lease-ready`; that lease is
never returned directly. Cached, stale, or future observations fail. Receipt
times must fall at or after issuance and strictly before both lease and runtime
deadlines. Fresh adapter returns may not be in the future; authenticated
historical or independently verified adopted evidence remains valid across a
later wall-clock rollback. Live effects also recheck those bounds immediately
before invocation, and prepare rechecks the full activation interval immediately
before reservation. Ambiguous outcomes require `HostRuntime.adopt` to authenticate exact
external evidence and `HostRuntime.checkpoint` to bind the adopted result before
the executor records adoption; a caller-fabricated receipt cannot checkpoint.
Post-expiry reconciliation uses a separate read-only fresh-observation path for
the already-recorded lease. It may authenticate and adopt a receipt whose
observation time fell inside the original lease, then checkpoint it, but it does
not revive authority: create, message, cancel, and ordinary resume still reject
the expired lease. Exact durable proof closes executor-only crash windows after
host create, host message, checkpoint, all-node completion, or cancellation.
Cancellation is checked before historical node/run completion and needs no
caller to restate its reason after a crash.
The checkpoint step is journal-local and uses the sole digest derived from the
full lease and receipt. A dedicated recovered-node event is legal while the run
is blocked, so one proven sibling can close without clearing another unresolved
sibling.
Cancellation is rejected before the adapter boundary once its lease expires.
Ambiguous effects are never blindly retried.

The local bounded wait detects a timeout but cannot kill a Python thread. Every
accepted host must advertise `host-enforced-deadline-v1`, and the lease binds
that capability. A late in-process return remains recoverable and cannot be
automatically retried, but actual effect containment is an external adapter
obligation; this module does not claim process-level containment.

Authenticated graph patches may add constraints or work, but may not remove or
alter existing inventory, evidence, authority, budgets, acceptance, roles,
lifecycle coverage, rollback, subject, integration, or deadline bindings.

Rollback reverts this executor package while retaining run, host, candidate,
checkpoint, failure, and reconciliation evidence.
