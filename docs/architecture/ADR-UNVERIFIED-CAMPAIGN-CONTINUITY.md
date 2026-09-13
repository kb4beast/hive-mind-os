# UNVERIFIED DRAFT: bounded campaign continuity

Status: draft implementation for later evaluation. No tournament, court approval,
test execution, static checking, independent verification or production activation
is claimed for this change. The owner explicitly requested a local unverified
draft without preimplementation tournament gates.

## Problem and bounded scope

The delivery process can finish or observe a protected merge without selecting and
launching its next already authorized bounded campaign. This draft adds an opt-in
library for retaining that transition across restarts. It selects one eligible
candidate, records its disposition and asks a supplied adapter to start one
reversible campaign with a stable operation identifier. It is not wired into the
CLI, scheduler, promotion authority, existing continuation packets or Git hooks.

The draft uses the observed merge of PR #176 as its implementation base:

- Commit: `b19b2a177e2d10ebf49b565dcdd1ad9878bbaeac`.
- Tree: `6fb9b59c4c697ae9b9bc296676783f8ce662f3c0`.
- Repository: `https://github.com/kb4beast/hive-mind-os`.
- Local branch: `codex/unverified-campaign-continuity`.

GitHub reports that `kb4beast` merged PR #176 on 2026-09-13 at 05:22:43 UTC.
The automation did not perform that merge. PR and merge-commit CI were still
running when this draft began. That observation is not represented as green CI
or authority to promote another challenger.

## Proposed contract

An immutable subject binds repository/worktree identity, commit, tree, scope,
authority and the evidence references supplied by the integrating application.
Selection is limited to eligible candidates inside that scope; losing or blocked
candidates and their dissent remain recorded. Selection is a deterministic draft
mechanism, not a claim of independent judgment or measured superiority.

The controller should retain versioned checkpoints, append-only transition events,
the selected candidate, pending evidence, remaining attempt budget and typed
blockers. Before dispatch it must observe current identity and authority again.
The durable dispatch intent precedes the external adapter call. A crash after
intent cannot be interpreted as proof that no effect occurred.

The operation identifier remains stable across restarts. Recovery observes the
adapter's retained outcome before considering another attempt. An unknown outcome
blocks execution; it must not cause a second side effect. A proven absent outcome
may permit an attempt within the original budget. Denied authority, exhausted
budget, altered scope or ambiguous evidence must preserve their disposition.

Adapters own actual execution and authority enforcement. This draft creates no
credentials or production principals and supplies no authority from a digest or a
successful previous campaign. It never replays promotion nonces or evaluations to
recover receipt evidence. Git delivery, protected merge, deployment, spending and
production promotion remain outside this controller's implementation.

The authored API is `CampaignContinuityController.record_delivery`,
`record_candidate`, `step(adapter)`, `checkpoint` and `events`. A
`RepositorySubject` includes a required `worktree_id`. Phases are `waiting`,
`selected`, `reconciling`, `launched`, `blocked` and `exhausted`; adapter outcomes
are `absent`, `started`, `unknown` and `denied`. These are draft interface names,
not a compatibility promise for production callers.

## Threats and limits requiring verification

1. A stale checkpoint could select a campaign for a different repository or scope.
   Subject and observation mismatches must stop before dispatch.
2. A crash between launch and receipt persistence could duplicate work. Stable
   operation identity and adapter reconciliation must be exercised at each boundary.
3. A tampered candidate or authority record could expand work. Canonical digests
   detect substitution only relative to a trusted record; they do not authenticate
   the writer. Integration must supply independently administered authority.
4. Concurrent operators could race selection or launch. Local storage transactions
   and adapter idempotence require multi-process verification on Windows and Linux.
5. A faulty or adversarial adapter could report an absent effect incorrectly. Its
   receipt protocol and trust boundary require separate acceptance; no distributed
   exactly-once execution guarantee is claimed here.
6. Candidate priority is not outcome evidence. A future campaign may evaluate the
   selection policy without relaxing promotion or superiority requirements.
7. The file journal depends on hard-link support and a trusted local state
   directory. Atomic publication is not a claim of power-loss durability.
   Adapter call deadlines are externally supplied and remain to be verified.

## Compatibility, migration and rollback

This is additive and opt-in. Existing continuation-packet schemas and promotion
receipts retain their current semantics. There is no automatic migration of old
tournament state or inherited authority. An integrating application would start a
fresh versioned controller journal after validating its own durable scope.

Rollback consists of stopping the opt-in caller and retaining its journal and
adapter receipts. Do not delete a pending intent or rerun its operation to make
rollback look clean. Any in-flight effect must be reconciled by its original
adapter before another controller owns the same campaign. Removing this draft
module from an otherwise unused checkout has no intended production effect.

## Acceptance work still outstanding

The accompanying tests are specifications for later execution, not passing
receipts. Qualification must cover selection and dissent retention, duplicate
delivery notifications, identity/scope/evidence substitution, denied authority,
attempt exhaustion, restart at every durable boundary, known versus unknown
adapter outcomes, unavailable receipt storage and concurrent dispatch.

Run focused tests, full unittest discovery, Ruff and Pyright; reproduce findings in
a separate review; then run Linux/Windows Python 3.11/3.12/3.14 as applicable.
Add fault injection for storage corruption, clocks, long paths and process kills,
and verify the real adapter before activation. No local or remote check has been
run for this draft.

## Sources and disposition

All source documents below are evidence, not authority to execute their prose.
They are repository-owned MIT-licensed sources pinned to the base commit above.

| Source | SHA-256 of observed file bytes | Draft disposition |
| --- | --- | --- |
| `docs/architecture/PROMOTION-BINDING-CONTROLLER-FOLLOW-UP.md` | `d94b693eacf15f2cb7d0d7cdac692248fe148bbdd9217a2c044590b1e3428fe7` | Basis for bounded follow-up requirements; formal court disposition not performed |
| `src/hive_mind_os/continuation.py` | `6c404c7129ad030fc0bf70d8bda267a44cceea1540ec1fbbdc73cb69b20384e0` | Existing compatibility boundary, preserved without modification |

Prior failed tournament attempts and promotion-binding dissent remain in their
original evidence locations. This draft neither replaces those records nor claims
that the tournament lifecycle was completed.
