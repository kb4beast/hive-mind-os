# Durable wave runtime

`WAVE-HOST-300` provides durable state without making a worker or its chat
session authoritative. The immutable `WaveManifest` content-addresses its
self-declared generation identifier, compiler-plan digest, subject identifier,
node states and order, checkpoint, and final candidate. Its self-hash proves
content integrity, not origin authenticity. Version 1 does not carry node
contracts, resources, context, tests, budgets, effect policy, or an authenticated
`GenerationRecord`, and it does not bind its `generation_id` to the candidate
journal's integer generation. Those are explicit future receipt-chain
obligations, not current safety claims. The manifest digest is the identity used
by every candidate journal entry.

## Candidate lifecycle

`CandidateStateJournal` is an append-only SQLite hash chain. A candidate begins
at `CHECKPOINTED`. `CANDIDATE_SEALED` introduces its exact subject, commit, and
tree identity and no later transition may change that identity. The remaining
states are `VERIFYING`, `INTEGRATION_READY`, `RECOVERABLE`,
`REPLAN_REQUIRED`, `INTEGRATED`, `FAILED`, and `CANCELLED`. Optimistic sequence
checks prevent two parents from advancing the same candidate. Database triggers
reject history updates and deletes, and a reopened journal verifies canonical
payloads, indexes, sequence continuity, and the full digest chain.

Sealing ends mutable workspace authority. A lost worker claim therefore does not
erase a sealed candidate: another parent can load its exact identity and resume
verification or adoption. Drift or conflicting identity goes to
`REPLAN_REQUIRED`; it is never repaired by rewriting history.

## One integration transaction per activation and wave

`IntegrationCoordinator` accepts only `INTEGRATION_READY` candidates present in
the supplied, internally consistent journal and in the supplied manifest's
explicit order. Neither caller-supplied artifact authenticates an external
issuer. Their order is evidence metadata only: it cannot select the CAS target,
which must exactly match the candidate commit and tree in `AuthorizedOneRun`.
Before any target-adapter call, the coordinator loads the exact signed-digest
plan through the canonical compiler boundary using exact authoring-standard
bytes. Noncanonical plan encoding, standard or compiler substitution, and
incomplete eight-role or lifecycle governance coverage fail closed.
Caller round labels are non-authoritative correlation hints. The durable round
identity is derived from the exact activation-proof digest and wave-manifest
digest, so aliases for that same pair converge on one canonical transaction and
cannot multiply CAS ownership. The coordinator records that complete intent
before asking the
`IntegrationTarget` for its sole mutating primitive: an atomic compare-and-swap
from one exact target identity to that preauthorized proposed identity. Workers
never receive that primitive. Transition to `EXECUTING` is an atomic SQLite
insertion-ownership claim: among concurrent identical commits using the same
durable journal, only the inserter may invoke compare-and-swap. Other callers
wait for and adopt the durable outcome without a second CAS or duplicate
`COMMITTED` event. Adapter-side transaction-id idempotency remains defense in
depth and is still required for independent journal stores or a lost process
boundary; the local journal does not claim global exclusion across such stores.

The live target binding includes the adapter id, exact `integration.target`
interface, version, configuration digest, trust digest, and target-protection
status. Interface-only or version-only drift changes the persisted binding digest
and fails before target observation or CAS. The adapter receives that complete
binding, the ordered sealed candidates, a stable transaction id, the
exact `AuthorizedOneRun`, the plan-derived integration-authority expiry, and the
earlier of that expiry and the activation expiry. The trusted target binding
must report protection status for the selected target; protected or unknown
status is denied even when the plan claims an unprotected target. At the atomic
boundary, the adapter must revalidate the exact authorization, binding,
protection denial, and effective deadline against its own clock before mutation.
The authorization interval is half-open: the adapter must also atomically enforce
`issued_at <= now < expires_at`, so a rolled-back target clock cannot make a
pre-issuance capability effective.
The coordinator repeats the deadline check immediately before the call as
defense in depth; an adapter that cannot enforce it atomically is not a conforming
`IntegrationTarget`.

After the call, the coordinator observes the target. Only the exact proposed
identity is `COMMITTED`. The unchanged base is `RECOVERABLE`, and any third
identity is `REPLAN_REQUIRED`. A timeout, exception, crash, or lost response is
resolved by observation and never by a blind second integration. The integration
journal is append-only and enforces one transaction identity per round.

Preparing or starting a CAS requires an `AuthorizedOneRun` whose issuance time
has arrived and whose expiry has not, plus live
plan integration authority. The exact plan-authority deadline is part of the
durable transaction intent, and the effect deadline is always the earlier of it
and activation expiry. A `commit` lookup that finds an already `COMMITTED`
transaction validates the same genuine sealed authorization against every
persisted activation, plan, target, base, and candidate binding without requiring
that authorization to remain live, then returns the durable terminal record. It
does not read the target binding, observe the target, or invoke compare-and-swap;
a substituted historical authorization still fails closed. Once the
journal is already `EXECUTING` or `RECOVERABLE`, reconciliation needs no live
effect capability. After restart it may rely on the verified durable intent under
trusted journal-file custody, or additionally check the same genuine sealed
authorization after expiry as historical identity. This exception permits only
read-only observation, classification, and a local journal append; it never
invokes or retries compare-and-swap, and any target-binding substitution still
fails closed.

The journal's preparation table stores an unkeyed digest of the exact initial
transaction. It detects mismatched or missing preparation records across reopen
and the public API denies direct event insertion. This is self-consistency under
trusted journal-file custody and trusted in-process module internals; it is not
issuer authentication against a pre-crafted or externally modified database.
The signed `AuthorizedOneRun`, exact target/base checks, adapter binding, and
bracketed observations remain the authorization boundary for the CAS effect.

## Traceability and rollback

- `V1-WAVE-HOST-300-OBJ` is adapted to the manifest, candidate journal, bounded
  host runtime, and single CAS transaction.
- `V1-WAVE-HOST-300-AC-01` maps to the closed `WaveManifest` seal.
- `V1-WAVE-HOST-300-AC-02` maps to the explicit lifecycle and transition table.
- `V1-WAVE-HOST-300-AC-03` is retained as the immutable candidate and restart
  adoption invariant.
- `V1-WAVE-HOST-300-AC-04` maps to the operations in `HOST_RUNTIME.md`.
- `V1-WAVE-HOST-300-AC-05` is retained as the one-integrator/one-CAS invariant.
- `V1-WAVE-HOST-300-AC-06` is retained by observation-based recovery and
  fail-closed drift classification.

Rollback removes the runtime implementation only. Journals, sealed candidate
identities, failed transactions, and effect evidence remain evidence and must not
be deleted.
