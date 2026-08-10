# Verifiable Hive Kernel: Phase 9 local technical closeout

## Purpose and boundary

Phase 9 is the smallest local-only step after Phase 8 exact-candidate verification.
It closes the gap between a passed, accepted work item and an inspectable technical
slice without routing legacy missions through the kernel or changing any historical
evidence. Its only new truth is a replayable statement of what the new local kernel
has verified and what remains incomplete.

The originating local evidence is ADR-052, its Phase 8 completion boundary, and the
implemented Phase 8 candidate `7c027df`. These sources establish that environment
contamination fixtures, adapter wiring, and broader mission-completion integration
are deferred. This phase adopts none of those deferred capabilities.

## Candidate implementation

This phase starts from `7c027df`. It adds `brain_kernel.closeout`, two strict
kernel-only contracts, and a read-only `hive-mind kernel closeout` command. A local
closeout obligation event lists the required roles and optional opaque historical
evidence references. A separately recorded Phase 8 bundle digest/reference is bound
to a passed result before the existing work can be integrated.

The closeout report replays the validated event spine, verifies every supplied local
bundle again, and binds its own digest to the event head and projection digest. It
returns `TECHNICALLY_VERIFIED` only when exactly one valid obligation declaration,
one distinct result for every required role, integrated work, one passed result per
integrated work item, and matching intact bundles are all present. Missing bundles,
duplicate/malformed facts, shared role identities, or tampered bundles are
`BLOCKED`; ordinary incomplete work is `PARTIAL`.

Historical evidence is represented only by its opaque reference, existing digest,
provenance label, and retention note. Phase 9 never opens it for mutation, translates
it into a new effect receipt, or changes a legacy receipt flow.

## Completion boundary

This completes the local technical-closeout slice. It does not create a customer
outcome or courtroom disposition, transition a mission to customer success, run a
provider or external process, access a network, migrate legacy data, or wire a legacy
command to the kernel. Broader adapter wiring, environment-contamination execution,
and legacy migration remain deferred.

## Local verification receipt

Focused kernel and contract tests, bytecode compilation, Ruff, and Pyright passed
locally after this change. The complete local unittest gate retained the pre-existing
Windows failure in
`test_self_history_pins_and_scripted_episode_complete_offline`: its point-in-time
fixture copies workspace-generated `.git/refs/codex/turn-diffs/checkpoints/...` into
a longer temporary directory and receives `WinError 206`. This Phase 9 slice does not
touch the PIT oracle, Git refs, or that copy path; the failure remains an explicit
environment obligation rather than a passing claim.

## Proposed outcome

For a new, caller-owned local kernel database, a deterministic fixture can:

1. record bounded role results and declared local obligations;
2. seal and independently verify an exact local candidate using the existing Phase 8
   path;
3. accept and integrate only the work bound to that recorded passed verdict; and
4. produce a read-only, event-derived `TechnicalCloseoutReport`.

The report is one of `TECHNICALLY_VERIFIED`, `PARTIAL`, or `BLOCKED`. It carries the
kernel event-head digest, projection digest, report digest, obligations, fulfilled
artifacts, missing obligations, evaluation-result digests, and verification-bundle
digests. It never emits a customer-success claim, a courtroom verdict, an external
receipt-authenticity claim, or authorization for any effect.

## Design constraints

| Constraint | Phase 9 rule |
| --- | --- |
| Local-only | No provider, network, remote CI, Git remote, credential, or external process adapter. |
| Exact candidate | An implementation work item may integrate only after its recorded Phase 8 passed result and bundle re-verify. |
| Identity separation | Required Builder and Curator identities must differ; no reported role obligation may be satisfied by an event with a mismatched role or executor. |
| Replay | The reducer derives the same closeout report and digest from the ordered event chain; caller flags and mutable files cannot change it. |
| Fail closed | Missing, duplicate, malformed, forged, stale, or mismatched facts make the report `BLOCKED`. |
| Legacy flows | Existing commands, facades, databases, ledgers, schemas, and receipt validation paths retain current behavior. No dual writer is introduced. |
| Historical receipts | They are immutable, opaque references. A new reference records provenance and an existing digest only; it never alters a receipt body or proves a new effect. |

## Work slices

### P9.1 — Contracts and event invariants

Add versioned kernel-only contracts for a declared local obligation, an immutable
historical-evidence reference, and `TechnicalCloseoutReport`. Add only additive event
types required to declare obligations, record opaque references, integrate accepted
work, and record a derived closeout report.

The reducer must reject unknown fields and reject each event unless its mission/work,
role, result digest, predecessor digest, and current projected state agree. It must
not change the validation semantics of Phase 1–8 event types.

### P9.2 — Independent evidence reconciliation

Implement a pure reconciler that reads validated events and calls the existing Phase
8 bundle verifier for each referenced local evidence bundle. The reconciler compares
the report's named head and projection digest against its own replay and returns a
complete, partial, or blocked report. A persisted report is a convenience receipt;
the pure recomputation is authoritative.

An opaque historical reference is valid only when its identifier, immutable digest,
provenance label, and retention note are present. It is never opened for mutation or
silently upgraded to a Phase 8 evidence bundle.

### P9.3 — Local fixture and inspection surface

Extend the deterministic kernel fixture—not a legacy runtime path—to exercise the
full local sequence. Add a read-only `hive-mind kernel closeout MISSION_ID` inspection
surface that opens an existing state database read-only and prints the derived report.
It must report a missing database or invalid event chain without creating state.

The fixture operates only under a caller-selected temporary/local root. It cannot
invoke a registered effect adapter beyond the existing Phase 7 confined fixture write,
cannot access a remote, and must leave its base tree untouched.

### P9.4 — Compatibility and receipt-preservation proof

Create golden fixtures for Phase 1–8 event streams and representative legacy receipt
references. Prove byte-for-byte non-mutation of every historical receipt fixture and
identical event/projection digests before and after read-only closeout inspection.
Prove that legacy CLI routes and stores do not import the new closeout service or write
new kernel events.

## Acceptance criteria

- A valid new-kernel fixture with all declared obligations, separated Builder/Curator,
  integrated work, passed exact-candidate result, and intact bundle derives
  `TECHNICALLY_VERIFIED`.
- Removing a required role result, leaving work accepted but not integrated, using one
  identity for Builder and Curator, or adding an unmet obligation derives `PARTIAL` or
  `BLOCKED` as appropriate; none can report technical verification.
- Tampering with the event head, projection digest, evaluation-result digest, bundle,
  historical-reference digest, or a persisted report fails closed on replay.
- A closeout cannot promote a mission to customer success or alter policy, authority,
  prompt champions, effect receipts, or legacy mission state.
- Existing Phase 1–8 tests, legacy-flow regression tests, and historical receipt
  fixtures retain their prior behaviors and digests.
- The full CI gate passes: `python -m unittest discover -s tests -v`.

## Courtroom record and delivery evidence

Before implementation, retain an append-only Phase 9 case record containing the
atomic claim, Phase 8 source references and digests, an Advocate case, a separate
Cross-Examiner case, relevant local-domain testimony, a Curator reproduction plan,
and a Judge disposition. The judge cannot be the architect or builder.

Implementation evidence must include the exact base and candidate commits, test
commands and outputs, fixture paths/digests, report/bundle digests, compatibility
comparison receipts, known failures, dissent, rollback rehearsal, and an explicit
statement that no external authority or legacy data mutation occurred. Do not claim
independent courtroom completion merely from local unit tests.

## Rollback and deferred work

Rollback disables the Phase 9 command and fixture path while retaining all additive
kernel events and evidence. It never restores a competing legacy writer, deletes a
historical receipt, or rewrites an older event stream.

Deferred beyond Phase 9 are environment-contamination execution, general adapter
wiring, legacy migration, real process/network/provider/Git/remote effects, external
authenticity, customer outcome measurement, and independent courtroom promotion.
Each needs a separately scoped proposal and evidence burden.
