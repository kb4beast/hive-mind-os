# ADR-063: Shared repository runtime authority and session fencing

## Status

Adapted implementation candidate. Promotion requires the exact focused and
repository-wide gates, a separate Curator reproduction, and an independent Judge
disposition. This record requires host-local capacity arbitration across applications,
repository arbitration inside each Git family, and multiple independent execution
namespaces inside each repository. It does not claim cross-machine federation or
cancellation of unmanaged external Codex sessions.

## Context and preserved incident record

On 2026-08-12 and 2026-08-13, two independently controlled worktrees for the same Git
repository admitted overlapping repository-wide validation. Each controller rooted its
supposedly global lease in its own worktree's `.autopilot/state`. The primary attended
ledger also retained multiple nonterminal `BOUND` launches for the same MISSION-400
resource after the target changed. Those launches had different target-specific
instruction IDs, and no terminal host observation or explicit supersession closed the
older launch.

The incident supports these distinct claims:

1. A worktree-local mutex can be correct while two linked worktrees still hold mutually
   invisible authority.
2. A target-specific instruction ID is useful for idempotent delivery but is not a
   stable resource identity.
3. A card or attended-host ledger entry is not proof that an external Codex session is
   live, stopped, or cancelled.
4. Prompted cooperation is useful defense in depth, but a stale worker must also be
   rejected by durable fences at controller transitions.
5. Sharing every ignored runtime file would create new cross-process races and would
   incorrectly merge worktree-local caches. Every fact that changes eligibility,
   terminality, recovery, or fixed-point truth must instead live in its canonical
   host, repository, or execution authority tier; non-authoritative caches remain local.
6. Replacing worktree-local schedulers with one repository-wide execution singleton
   prevents corruption but also prevents independent applications from using the same
   repository. Repository arbitration and execution identity are different layers.

The original ledger, card, process, lease, and Git observations remain in the incident
thread and repository runtime state. This ADR summarizes them; it does not replace or
rewrite that evidence.

External capability evidence was retrieved from the official OpenAI documentation on
2026-08-14: `https://developers.openai.com/codex/sdk` and
`https://developers.openai.com/codex/app-server`. The atomic claims used here are that
the SDK starts/continues/resumes local threads, and App Server starts, reads, lists,
resumes, interrupts, and archives managed threads/turns. No source code was copied; the
documentation remains governed by OpenAI's published documentation terms. This evidence
also shows no documented idempotency field on `thread/start`; `serviceName` tags metrics
and is not returned as creation identity. The installed schema inspected by the adapter
is Codex CLI 0.146.0. This evidence does not establish control of unrelated ChatGPT or
Codex cloud conversations.

## Court record

- **Advocate (Architecture):** adopt one repository authority for all standard linked
  worktrees so autonomy does not become duplicate scheduler sovereignty.
- **Cross-Examiner (Concurrency):** reject a simple shared-directory switch. Existing
  read/modify/write operations, stale reapers, owner-only releases, and attended-ledger
  rewrites would become cross-process races or ABA deletion paths.
- **Expert Witness (Integration):** use the validated Git common-directory topology to
  converge standard linked worktrees on the primary worktree's existing state. Adopt
  decision-critical receipts into the execution namespace, preserve local caches only
  as non-authoritative evidence, and fail closed on unsupported metadata layouts, path
  links, identity collisions, and noncanonical legacy authority.
- **Steward:** require exact claim and validation-lease identities, one lock around each
  authority transition, atomic durable replacement, and stale-generation rejection.
- **Curator:** require real multi-process or linked-worktree tests, legacy migration and
  tamper tests, sidecar terminal-race tests, and explicit evidence that read-only checks
  do not manufacture authority state.
- **Optimizer:** duplicate repository-wide validation is waste and contention, but this
  candidate makes no superiority claim and supplies no host-wide capacity benchmark.
- **Official Codex capability witness:** the Codex SDK can start, continue, and resume
  local Codex threads. Codex App Server additionally exposes authenticated thread
  start/read/list/resume/archive, streamed turn events, and in-flight turn interruption.
  Those APIs support managed lifecycle after a thread ID is durably bound, but the
  documented `thread/start` schema has no caller idempotency key or atomically visible
  adoption token. Version 0.146.0 therefore cannot truthfully claim crash-exact autonomous
  thread creation. It also cannot retroactively control an unrelated ChatGPT or Codex
  cloud chat.
- **Judge:** **remand** the first implementation candidate. Its public round path exposed
  a caller-selected validation runner, mutated an ambient checkout, held broad authority
  across network/test effects, and could misclassify an uncertain push. A successor may
  return for judgment only with the private pinned transaction, exact remote binding,
  mandatory cross-namespace inventories, fixed gate, failure-preserving lease cleanup,
  and typed publication outcomes required below. The architecture disposition remains
  **adapt candidate**, not adopted production authority.

## Decision

### 1. Split host, repository, execution, and local-evidence authority

`ControlPlane.state_dir` remains the current worktree's evidence directory. Receipts,
blockers, questions, repair journals, snapshots, and other evidence retain their
existing worktree-local behavior.

The operating kernel has three authority tiers:

- the canonical per-user host runtime owns host capability generations and aggregate
  primary, sidecar, and validation reservations across every participating repository;
- `ControlPlane.coordination_dir` is one repository-family runtime root whose `arbiter/`
  owns short-held Git, remote, target, claim, and cross-execution resource authority; and
- `executions/<execution-id>/` owns one application's dispatcher release/history,
  admission generation, snapshot observation/candidates, primary and sidecar binding
  ledgers, attended registry, immutable cards, and execution-local locks.

The host runtime has its own immutable host identity and a single canonical OS-account
state location. Discovery is anchored in the operating-system account/known-folder
identity, not selected anew from mutable `HOME`, `XDG_STATE_HOME`, `LOCALAPPDATA`, or
similar process environment. A test/admin override may select that location only before
initialization and must thereafter resolve to the bound identity from every environment.
It cannot create a peer host scheduler.
Global host-reservation rows include repository identity and execution identity: all rows
consume the machine budget, while file/Git conflict comparison applies only to the same
authenticated repository and remote resource.

An execution namespace has a strict stable name. Its `execution_id` is the canonical
digest of repository identity plus that namespace name; its immutable manifest also
binds target branch and plan fingerprint. Reusing the same namespace with another target
or plan fails closed. Different namespaces may coexist—even with the same plan—subject
only to real arbiter capacity and resource conflicts. Supplying a different state
directory never creates a second repository sovereign.

For a normal repository, the coordination directory remains the checkout's existing
`.autopilot/state`. For a standard linked worktree, Git's common metadata identifies the
primary worktree and every linked worktree converges on the primary worktree's existing
`.autopilot/state`. An explicit `--state-dir` or environment override is permitted only
when the directory is bound to the same repository identity.

The repository coordination root is likewise bound once in both shared Git common
metadata and the host runtime's append-only repository registry. The host registry maps
the sealed repository/remote identity to one root, so a separate clone on the same host
adopts the existing arbiter instead of creating a peer. An explicit state-directory
override may select the canonical root during bootstrap but cannot create a second
repository sovereign. Every later process discovers and cross-validates both bindings
before reading or mutating authority.

### 2. Fail closed on identity and path ambiguity

The shared directory carries an immutable schema and repository-identity manifest.
Authority mutations create it under an OS lock; authority reads validate it without
creating directories, manifests, or lock files. Malformed `.git` indirection,
unsupported separate Git directories, symlinks or junctions in authority paths,
identity mismatch, corrupt ledgers, and noncanonical legacy authority become explicit
reconciliation obligations rather than silent per-worktree fallback.

### 3. Serialize claims and validation leases with exact fences

Every claim conflict check, creation, heartbeat, stale cleanup, release, failure, and
completion runs under the repository arbiter and names its `execution_id`. Cross-
namespace file, semantic, branch, and target conflicts are checked there. A claim
receives an exact `claim_id`; later transitions must present that ID, so an old owner
string cannot mutate a replacement claim after expiry and reacquisition.

Validation leases are keyed by authenticated target/resource rather than stored in one
repository singleton. Two different targets may validate concurrently when their host
capacity generations admit it; the same target may not. Each lease receives an exact
`lease_id`. Acquire, renew, exact release, and expiry break run under arbiter authority.
Hosted validation also names the exact execution, claim, and launch generation; a
bounded renewal loop keeps long gates leased and turns renewal failure into a failed
verdict. Archive names are derived from validated identities and installed exclusively-
or-identically, so crash retry cannot overwrite adverse bytes and stale-owner ABA
removal cannot delete a successor.

### 4. Separate stable resource identity from launch delivery identity

A primary launch has three identities:

- `execution_id` names the immutable application namespace;
- `launch_instruction_id` remains specific to target SHA, plan fingerprint, authority
  class, attempt, and delivery material; and
- `resource_key` is stable for the repository, target branch, lifecycle, and DAG node.

The append-only binding ledger assigns a monotonic `authority_epoch` for each resource.
Every bind, host-progress, terminal-observation, and release transition must present the
exact instruction, resource, and epoch. A stale or superseded generation is rejected.
Omission from a contract is never cancellation proof, and a new instruction does not
silently revoke an old one. While a resource has active authority, successor preparation
fails closed until terminal host evidence or an explicit audited fence exists.

An administrative fence records `SUPERSEDED`, actor, reason, old epoch, and any known
successor proof. It revokes Hive Mind execution authority; it does not claim that the
external chat process was cancelled. A managed App Server adapter interrupts the exact
active turn and archives only after observing terminal lifecycle evidence. An unmanaged
chat receives only a best-effort operational stop request, and every later
controller-mediated effect still needs a current claim and launch fence. This control
plane cannot prevent a process with independent filesystem or Git credentials from
bypassing its commands; that requires the host sandbox and capability kernel.

### 5. Make shared append-only registries transactionally monotonic

Task binding, sidecar binding, and attended-host registry operations use execution-local
locks. A sidecar transition holds one lock across latest-state validation
and append so two processes cannot publish conflicting terminal states. Attended cards
are immutable per task rather than mutable per node. Pending-card and relay eligibility
derive from the primary binding ledger instead of a second independently written
authority flag.

### 6. Require explicit, evidence-preserving migration

`runtime-authority-migrate` is the only path that initializes shared authority around an
existing ledger. Under a dedicated bootstrap lock it freezes the linked-worktree
inventory, validates every legacy authority source, and records a `PREPARED` manifest
containing exact bytes, digests, identities, expiries, source paths, and rollback paths.
Provably expired noncanonical claims and validation leases are archived immutably and
retired at their source without being imported as live authority. Live, malformed,
identity-mismatched, or ambiguous authority and any secondary binding ledger fail closed.

The same bootstrap transaction stages repository identity and arbiter locks, creates the
strict `default` execution manifest, then migrates canonical task, sidecar, release,
snapshot, and attended entries into that execution under its locks. Original ledger and card bytes are
archived by digest; normalized entries record card digests and use immutable task-specific
cards. Both migration manifests are crash-retryable and tamper-evident. A repository-bound
runtime-ready marker is published last; ordinary authority operations reject staged or
partially migrated state.

### 7. Arbitrate globally, dispatch per execution, and fence the whole round

Each execution serializes its own dispatch, hosted launch transitions, and public round
integration on its execution dispatcher lock. Short repository-arbiter transactions
reserve real shared capacity/resources and perform target-ref compare-and-swap; they are
never held through a host wait or repository test. Each release records its
`execution_id`, monotonic admission epoch, repository, target branch and SHA, plan
fingerprint, exact released wave, and the exact host-capacity ID/generation that admitted
it.

Capacity authority is never inferred from the DAG compiler's concurrency constant. In
the absence of sealed product/operator evidence, the host kernel publishes an expiring
conservative aggregate ceiling of one; any higher ceiling requires an authenticated,
expiring capability record declaring what that host can actually support. Repository
policy may lower but never raise the host declaration. Publication uses expected-generation
compare-and-swap and retains predecessor history, so an older observation cannot replace
a newer still-valid capability. Primary tasks, initial and descendant sidecars, and
validation slots are reserved in one strict append-only arbiter ledger across all
repositories and execution namespaces owned by that OS account. A provider or adapter
identity is authenticated provenance, not a caller-selected capacity partition: aliases
such as `host-A` and `host-B` cannot each obtain the machine ceiling. Dispatch reserves
expiring primary admission permits
for the exact released wave; launch atomically consumes and binds a permit before
execution-local `PREPARED`. Required sidecars are either included in that admission or
rejected before a host effect, while optional sidecars use only demonstrably remaining
capacity. Release requires the exact execution, release, resource, reservation, and
authority fence. Expired crash-left reservations become explicit recovery obligations and
may be retired only by an exact fenced recovery transition. A crash may conservatively
leak a recoverable reservation but can never over-admit. A `parallel_safe: false` node
occupies its primary wave alone. An attended
adapter that cannot discover capacity or observe optional lifecycles must say so and fail
closed or use an explicitly sealed conservative capability; it may not claim that eight
slots exist merely because the DAG compiler supports eight.
Provider evidence binds the exact executable/module/schema identity plus a hash-only
digest of behavior-changing backend, proxy, and certificate-trust inputs; it never stores
their raw values. Cross-repository recovery observes the exact external task identity
directly. A repository/worktree-filtered host listing cannot prove absence, so an
unreadable task remains charged until terminal lifecycle is authenticated.

Snapshot acquisition reserves an execution-local monotonic observation epoch and opaque
`observation_id` before `git fetch`, `gh`, or any other external observation. Beginning an
observation joins an already-unexpired `PENDING`/`INSTALLING` single flight instead of
rotating tokens until all callers starve. Only a provably expired observation may be
archived immutably and superseded. Installation must present the exact ID and canonical
execution/repository/target/plan identity, durably retain its exact candidate bytes, and
move through `PENDING -> INSTALLING -> INSTALLED`. Target-ref publication uses a short
repository-arbiter CAS. An identical interrupted install may recover from the retained
candidate; a stale observation cannot alter canonical refs or execution authority.
Because independent clones do not share a Git object database, any snapshot or
publication state advertised as cross-clone recoverable must first install its objects
under immutable namespaced remote evidence refs with exact compare-and-swap. A successor
clone re-fetches only those sealed refs and revalidates commit/tree/receipt ancestry;
clone-local refs alone are never durable shared authority.

Only an issuer with fresh snapshot and reconciliation evidence may publish a new
execution generation; every consumer authenticates it against the live target, execution
manifest, plan, capacity generation, and arbiter reservations. Active write launches,
sidecars, and claims—not claims alone—freeze replacement or invalidation for that
execution. Other execution namespaces remain live unless they conflict on an arbiter
resource.

Every hosted claim and validation transition revalidates the exact active release under
one documented order: host authority, repository arbiter, execution dispatcher, task
binding, sidecar, claim, then keyed validation. A stale session therefore cannot heartbeat, fail, release,
complete, or renew after its execution, launch, release, target, or plan fence changes.

External App Server effects use a durable execution-local intent and bounded operation
lease. Authority locks protect only intent installation and result reconciliation; they
are never held over JSON-RPC I/O. The documented `thread/start` method does not expose a
caller idempotency key or atomically visible adoption token. `turn/start` does expose
`clientUserMessageId`; the adapter binds it to the durable operation token and reconciles
the exact thread/turn evidence. No request accepted immediately before client failure is
blindly retried: if the adapter cannot prove whether the effect happened, it records
`RECOVERY_REQUIRED` and does not issue a duplicate effect.
The adapter persists `ATTEMPTED` before `thread/start`; even an empty later inventory
cannot turn that accepted-unknown request back into a retry. A concurrent controller that
sees another live effect operation lease returns a typed durable wait/adoption outcome;
it never fences the active launch merely because the external result is not yet known.
In particular, an App Server provider without an atomic thread-creation adoption field
publishes `autonomous_launch=false`; the supervisor returns `WAITING_FOR_HOST` before
admission. Autonomous progression requires another authenticated provider that offers an
exact creation capability, or a future App Server schema that makes the durable token
observable in the creation transaction.
Such a provider may still be an authenticated observer: it can reconcile known threads
and certify an already-terminal execution, but the controller must return
`WAITING_FOR_HOST` before dispatch, reservation, binding, or creation whenever work
remains.

The public `run-round` command accepts only the exact execution and `release_id`. A short
arbiter-then-execution transaction validates the generation, requires its worker claims
to be settled, requires the selected compiled round to equal the released wave,
preflights every exact receipt head, and reserves the conflicting target resource before
Git effects. It then releases both locks; the durable opaque transaction reservation,
not a long-held global lock, fences integration and validation. Lease renewal uses short
arbiter transitions, and final publication reacquires arbiter then execution and
revalidates the complete transaction. A partial wave returns `PENDING` without healing,
reconciliation, merge, push, validation, or a lingering reservation. Recovery runs
separately and is followed by a fresh release.

For a whole wave, integration occurs in a disposable per-execution worktree on a private
transaction ref, never in an application's ambient checkout or directly on the shared
target ref. The transaction has an exact expiring coordinator lease that is renewed
through integration and validation; expiry fences the old coordinator and preserves its
private ref before a successor attempt. Publication advances through `PREPARED` (the
private ref must equal the exact base), `PINNED` (an immutable namespaced remote evidence
ref seals the exact integrated SHA), and `PUBLISHING`. A successor clone materializes and
authenticates that remote evidence before it may construct a workspace; an arbitrary
descendant already present at the transaction ref is never accepted as authority. The
integrated commit is pinned before a fixed repository validation gate;
public callers cannot inject a runner or alter the validated commit. Validation consumes
host capacity and runs under a keyed lease bound to repository, execution, release,
transaction SHA, and capability generation. After validation the arbiter revalidates the
release, every receipt head and terminal descendant, the canonical remote transport, and
the exact remote target, then publishes the pinned commit once by fast-forward
compare-and-swap. A durable journal distinguishes `PUBLISHED`, `REJECTED` (known no remote
update), and `PUBLISH_UNKNOWN` (the transport outcome must be reconciled); it never calls
an uncertain remote update rolled back. Failed validation retains typed adverse private
transaction evidence and cannot reset another application's checkout. `--no-push`
retains a named authenticated transaction artifact. Public callers cannot skip
validation, invent capacity, select privileged authority, or choose a validation runner.

### 8. Drive an execution to a truthful fixed point

An autonomous execution is a durable state machine, not a sequence of manually repeated
one-wave commands. A namespaced supervisor persists its current frontier and advances
snapshot, reconciliation, dispatch, host execution, integration, validation, and the next
frontier until one exact disposition is reached: `WAITING`, `BLOCKED`, `ROUND_COMPLETE`,
`WAITING_FOR_HOST`, `PLAN_QUIESCENT`, or `RECOVERY_REQUIRED`. Only `PLAN_QUIESCENT` means the DAG is complete
and every execution-local launch, descendant sidecar, claim, validation lease,
transaction, and global reservation is terminal. Empty released work, absence of a
claim, or one host contract becoming quiet is not plan quiescence.

An empty authenticated dispatcher wave may produce only
`CONTROLLER_QUIESCENT_CANDIDATE`. That candidate is not a successful command outcome and
cannot be promoted by the round driver or host adapter. The supervisor alone may promote
it to `PLAN_QUIESCENT` after independently authenticating the same controller authority
cut and a zero-activity App Server lifecycle observation. Promotion atomically installs
an execution-terminal fence in that same cut; later dispatch, launch, claim, sidecar,
publication, and validation admission reject the terminal execution. A crash after the
fence but before the supervisor journal is recovered idempotently from that exact fence,
not by reopening admission.

Every command and process exit maps truthfully to those dispositions; blocked, adverse,
waiting-for-host, validation-failed, and recovery-required outcomes cannot exit as
success. Resume adopts the persisted frontier and content-bound receipts instead of
replaying completed rounds. An adapter without an authenticated host
create/query/resume/interrupt/archive API declares that limitation and yields
`WAITING_FOR_HOST`; writing an attended card and printing an instruction is not
represented as autonomous session launch. The production managed-Codex adapter targets
the documented local Codex SDK/App Server lifecycle and records the returned thread,
session, turn, and terminal-event identities. A card-only adapter remains an explicitly
non-autonomous compatibility surface.

A crash after `STEP_STARTED` creates one durable unknown-attempt obligation. The
controller—not the host adapter—derives the reconciled scheduler disposition from exact
release, effect, publication, and terminal-fence state; the host contributes only typed
lifecycle/effect observations. That exact attempt must reconcile before another callback
is admitted.

`WAITING` and `WAITING_FOR_HOST` seal an observation fingerprint, resume token, and
optional `wake_at`. Re-observing the same wait before its wake or evidence change returns
the same durable result without appending another attempt. A crash after a step begins is
never silently retried: the exact pending attempt becomes a reconciliation obligation,
and only an authenticated controller/host observation can append its terminal recovery
transition before another step is admitted.

A validation unit whose semantics require class/process lifetime longer than one polling
command runs as a durable host-reserved validation execution. Polling commands adopt its
exact process/job identity and output checkpoint; they do not kill and retry the same
class until a fixed command budget is exhausted, nor split a class across processes when
that would change `setUpClass`/`tearDownClass` semantics. Completion seals one receipt;
timeout, lost process identity, or corrupt output becomes adverse predecessor evidence
and a new execution attempt rather than rewriting the old composite.

## Threats and limitations

- **Stale external session continues running:** controller-mediated effects are denied by
  claim and launch fences. A managed local App Server turn is interrupted and observed;
  an unrelated external/cloud chat cannot be assumed controllable, and independently
  credentialed Git/filesystem commands remain outside this kernel.
- **ABA reuse of an owner label:** exact claim, lease, resource, and epoch identities
  prevent an old generation from releasing or completing a successor.
- **Cross-process lost update:** one authority lock covers the entire validate-and-write
  transition; atomic writes and fsync preserve durable state.
- **Path spoofing or state aliasing:** links, malformed Git metadata, unsupported layouts,
  and repository-identity mismatch fail closed.
- **Migration crash or tamper:** original bytes and digests are retained and migration is
  retry-idempotent; ambiguity remains a blocking reconciliation obligation.
- **Downgrade revival:** reverting code while old worktrees remain active could make them
  ignore shared authority. Rollback therefore requires quiescence and explicit fencing;
  a source revert alone is not an operational rollback.
- **Cross-repository host contention:** the canonical per-user host runtime accounts for
  every participating repository on this machine. It cannot police an old or malicious
  binary that bypasses the kernel, another OS user's scheduler, or another machine;
  cross-user enforcement and cross-machine federation remain later kernel boundaries.
- **Execution namespace collision:** the execution manifest binds repository, namespace,
  target branch, and plan fingerprint. Same namespace with different identity fails;
  separate state-directory overrides cannot bypass the repository arbiter.
- **Mutable Git remote configuration:** repository identity also seals the canonical
  transport. Push URLs, URL rewrites, injected Git configuration, or a changed remote are
  rejected before observation and rechecked immediately before publication.
- **Indeterminate network publication:** transport failure after the server may have
  accepted an update is recorded as `PUBLISH_UNKNOWN`; no later scheduler may assume
  success or historical rejection from a point-in-time ref alone. Seeing the exact
  pinned SHA proves current publication; seeing the predecessor only permits a fenced
  retry/current-state transition while preserving that the original outcome was unknown.
- **Supervisor crash or host limitation:** the persisted namespaced frontier resumes from
  authenticated receipts. A host adapter that cannot launch or inspect sessions stops at
  a truthful waiting disposition rather than looping, fabricating quiescence, or asking a
  stale session to repeat completed work.

## Migration and rollback

1. Quiesce all known controllers for the repository.
2. Run the explicit migration once from the canonical primary repository.
3. Inspect the identity and migration receipts and enumerate every latest launch state.
4. Append explicit fences for stale active launches. Send best-effort stop/reconciliation
   messages to the corresponding external sessions without claiming host cancellation.
5. Start new controllers only from a version that understands shared authority and
   exact fences.

Rollback preserves the manifest, ledgers, archives, cards, `SUPERSEDED` events, and
claim/lease archives. First stop dispatch and reach verified quiescence. Reverting the
source is allowed only after every linked worktree is reconciled to a single supported
authority reader; never revive a lower epoch or delete adverse migration evidence.

## Acceptance evidence

Promotion requires executable evidence for:

- two real linked worktrees resolving to one authority directory;
- two different explicit state directories for one Git common directory producing one
  canonical-root winner and one pre-effect identity rejection;
- two independent clones of the same canonical remote adopting the host registry's one
  repository arbiter, while a conflicting root registration fails before mutation;
- unrelated repositories retaining separate Git/execution authority while consuming one
  canonical host capacity budget;
- two repositories concurrently reserving the last host slot with exactly one winner,
  plus disjoint capacity becoming reusable only after an exact terminal/expiry fence;
- two authenticated provider labels and two caller-supplied host aliases still sharing
  one OS-account ceiling rather than multiplying it;
- two processes with conflicting `HOME`, `XDG_STATE_HOME`, or `LOCALAPPDATA` values
  resolving the same canonical host kernel or rejecting the disagreement before writes;
- two execution namespaces with different plan/target identities progressing
  concurrently under one repository arbiter;
- same namespace with a different plan or target failing before state mutation;
- cross-namespace file/branch/resource conflicts and aggregate host-capacity overflow
  being rejected, while disjoint work remains live;
- a crash between global reservation and execution-local `PREPARED` leaking at most a
  recoverable slot and never over-admitting;
- an unrelated repository recovering a predecessor repository's expired reservation only
  after authenticated terminal/cancellation lifecycle evidence, while unknown work stays
  charged;
- another repository/worktree hiding a live task from its cwd-filtered host list while
  exact task observation keeps the reservation charged;
- malformed, linked, aliased, and identity-mismatched paths failing closed;
- read-only absent-ledger checks creating no state;
- concurrent first mutation producing one valid identity and ledger chain;
- overlapping claim admission, stale cleanup versus heartbeat, and claim-owner ABA;
- validation acquire/release/break ABA with successor survival;
- cross-worktree launch preparation admitting only one active resource generation;
- same-resource stale epoch rejection and unrelated-resource preservation;
- omission from a contract leaving unrelated live work untouched;
- cross-worktree host adoption using the exact creation schema;
- attended migration byte/digest preservation, retry, tamper, and conflict behavior;
- simultaneous sidecar terminal transitions producing exactly one terminal event;
- divergent linked-worktree local releases being ignored in favor of one shared
  generation;
- concurrent snapshot starts in one execution joining one unexpired single flight,
  expired observations archiving immutably, and different execution namespaces retaining
  independent observations;
- two execution namespaces interleaving target-ref snapshot CAS/finalization without
  leaving either observation permanently `INSTALLING`; the later exact ref winner either
  fences or evidence-preservingly overtakes the earlier transaction;
- a separately cloned repository resuming snapshot and publication transactions after
  the originating clone exits by fetching immutable namespaced remote evidence refs;
- cross-worktree claim admission without matching local snapshot evidence, provided the
  shared generation and live canonical target remain exact;
- serial-wave and exact host-capability-generation enforcement across namespaces,
  primaries, initial sidecars, descendant sidecars, and validation reservations;
- attended-host omission of preparation-only tasks and optional sidecars that the adapter
  cannot lifecycle-manage;
- target or reconciliation invalidation fencing later hosted claim transitions;
- stale, wrong-wave, or missing round authority failing before triage, healing, Git, or
  validation effects;
- a partial released wave returning `PENDING` without healing, reconciliation, merge,
  push, or validation effects;
- a completed worker wave with no remaining claims integrating and validating under its
  exact shared release;
- fixed-gate validation of a pinned private transaction commit, with an injected runner,
  checkout switch, untracked-file mutation, or ambient-branch mutation unable to change
  the published SHA;
- canonical remote URL/push URL/config binding and pre-publication revalidation;
- publication receipts distinguishing verified success, verified rejection, and unknown
  transport outcome without destructive ambient-checkout rollback;
- fenced re-observation after `PUBLISH_UNKNOWN` resolving separately the cases where the
  remote currently holds the exact SHA, the expected predecessor, or an unrelated SHA;
  predecessor equality remains retryable/unknown rather than being mislabeled as proof
  that the original push was rejected, and every original unknown event is preserved;
- renewal, runner, and lease-release failures all retained in one recovery-required
  transaction verdict rather than masking one another;
- a crash/restart run-to-quiescence test that resumes the exact frontier, never replays a
  completed round, and reports `PLAN_QUIESCENT` only when every execution and arbiter
  authority is terminal;
- a barrier race in which validation admission overlaps the terminal controller cut,
  proving that either the lease is present in the cut or the execution-terminal fence
  rejects it, plus crash adoption between that fence and the supervisor success event;
- post-terminal snapshot, dispatch, launch, claim, sidecar, validation, and publication
  admission each rejecting before any arbiter or execution byte changes;
- repeated identical waiting observations producing one durable attempt until `wake_at`
  or the evidence/resume token changes, and crash-after-step-start requiring an exact
  authenticated reconciliation before another callback is admitted;
- attended execution returning `WAITING_FOR_HOST` without claiming that a card is a host
  launch, plus an authenticated fake-host end-to-end run reaching `PLAN_QUIESCENT`;
- an authenticated observation-only provider certifying an already-terminal execution
  but producing zero dispatch/reservation/binding/creation effects for incomplete work;
- an App Server adapter contract test covering start, streamed status, resume/adoption,
  exact turn interruption, terminal observation, and archive, with
  thread/session/turn-identity mismatch failing before an authority transition;
- backend/proxy/trust-route changes altering only a sealed hash identity, and executable
  replacement across process creation terminating the unauthenticated child fail closed;
- crash points after App Server accepts thread creation, turn start/message, sidecar
  start, interrupt, or archive but before the client receives the response, proving an
  exact observed effect is adopted and an ambiguous effect is never issued twice;
- two controllers entering the same live prepared host effect while one is paused, with
  one external effect, one wait/adoption result, and no launch-fence event;
- a class-safe validation unit longer than one poll budget surviving coordinator exit,
  being adopted without duplicate execution, and publishing one terminal receipt while
  preserving an exhausted predecessor composite;
- the complete Autopilot tests and repository CI gate; and
- independent Curator reproduction from the pushed commit.

The result may be promoted only as host-local multi-application capacity arbitration,
repository coherence, and isolated multi-execution scheduling. A claim that it is already
a cross-user or cross-machine federated AI operating-system scheduler is rejected.
