# Campaign continuity qualification repair record

Status: R1/R2 repair implemented; current focused/static, independent review and
full-gate qualification are **pending the root coordinator**.
Current artifact bindings are in
[CONTINUITY-QUALIFICATION-REPAIR-MANIFEST.json](CONTINUITY-QUALIFICATION-REPAIR-MANIFEST.json).
Current builder: `/root/continuity_repair_builder`, acting under the owner's
bounded repair authority on 2026-09-13. The first repair builder was `/root`.
No independent approval or production authority is claimed here.

## Subject, authority and historical evidence

This repair is limited to the opt-in `campaign_continuity.py` library, its tests
and documentation in `C:\h\continuity-draft1`, on
`codex/unverified-campaign-continuity`. The base is merged PR176 commit
`b19b2a177e2d10ebf49b565dcdd1ad9878bbaeac`; the historical unverified draft is
`1a28b0c0587cc9a576c8f0aa2c287df3e3d2f366` (tree
`aa62d99c767c5d54e8db797a8c354bf59b1098ca`). Repository identity:
`https://github.com/kb4beast/hive-mind-os`; repository license: MIT.

The original [UNVERIFIED manifest](UNVERIFIED-CONTINUITY-MANIFEST.json),
[draft ADR](ADR-UNVERIFIED-CAMPAIGN-CONTINUITY.md) and
[draft overview](../../UNVERIFIED-CONTINUITY-DRAFT.md) remain unchanged historical
snapshots. Their artifact hashes and unexecuted-test statements describe the
original draft, **not these repaired working-tree bytes**. This document is the
current qualification record; it does not retroactively qualify that snapshot.

The owner authorized routine repairs, tests, review and Git delivery while waiving
preimplementation tournaments/courts. For the first repair builder turn the owner expressly
reserved focused checks, comprehensive independent review, the full gate, commits,
pushes and PR publication to the existing launcher, and prohibited a second
runner or agent. That builder reported no execution of tests, static checks, a launcher,
Git delivery, production wiring, credentials, deployment, payment, protected merge,
policy changes or challenger promotion. The target delivery remains a separate
non-draft PR only after launcher qualification; none is claimed published here.

All eight retained files under `C:\h\continuity-qualification\review` were read.
The [documentation copies](continuity-qualification-review/REVIEW.md) are
normalized views: Git changed CRLF to LF in three JSON files. The previous
byte-for-byte statement was incorrect for those committed views. Exact original
bytes now reside under
[`evidence/live/continuity-qualification/original-review`](../../evidence/live/continuity-qualification/original-review/REVIEW.md)
(repository-relative path; the manifest contains exact mappings).
The two reproduction programs have a `.txt` suffix in this evidence copy to keep
historical programs out of current code discovery. Original names and digests
remain in the [review manifest](continuity-qualification-review/REVIEW-MANIFEST.json).
Those files are evidence, not execution instructions. That original review is by
`/root/delivery_curator` against the original draft, with a **repair required**
verdict. Its reproduced failures, positive control, platform limits and dissent
are not superseded by the builder's implementation claims below.

## Dispositions and executable acceptance mapping

These are builder repair dispositions, awaiting independent verification; they
are not self-issued court judgments. Every original test assertion is preserved.

| Retained finding | Builder disposition and resulting behavior | Added acceptance cases in `tests/test_campaign_continuity.py` |
| --- | --- | --- |
| 1 / P1: valid foreign journal accepted after construction | Adapt: every journal read checks the current scope binding, exact delivery and selected candidate, and recomputes the full operation binding before adapter calls. Previously observed history cannot regress within a live controller. | `test_wrong_scope_restore_is_rejected_by_every_public_read`; `test_selected_candidate_and_operation_are_revalidated_on_restart` |
| 2 / P1: possible effect stranded by expiry, denial or budget | Adapt: persist `outcome_pending` at launch intent. Add a separate, bounded `recover(adapter)` inspection-only API usable after dispatch stops. Preserve the original blocker and operation ID. No recovery call can observe dispatch authority or launch. | `test_pending_effect_recovery_after_expiry_denial_and_final_attempt` (six combinations, including actual `os.link` receipt-publication failures); `test_recovery_unknown_is_bounded_and_never_reopens_dispatch`; `test_recovery_absence_closes_unknown_without_launching`; `test_malformed_or_denied_launch_receipt_keeps_effect_recoverable` |
| 3 / P2: typed observation errors escaped without evidence | Adapt: separate adapter calls/validation from journal publication. Persist typed adapter codes and sanitized messages, with typed refusals terminal for dispatch. Persistence failures escape with their storage identity. Typed inspect/launch failures remain unknown, never absence. | `test_typed_observer_denial_is_retained_once`; `test_observation_persistence_failure_is_not_an_adapter_denial`; `test_typed_launch_denial_after_effect_stops_dispatch_but_allows_recovery`; `test_typed_inspect_failure_is_retained_without_authorizing_launch`; original lost-response/interruption assertions retained |
| 4 / P2: malformed observation and receipt fields accepted | Adapt: constructors and response boundaries validate exact identifiers, subject, digests, timestamp, booleans, immutable unique references, receipt status and text detail. Malformed post-launch responses retain a possible effect for recovery. | `test_response_dataclasses_require_exact_fields`; `test_mutated_observation_cannot_bypass_boundary_validation`; `test_malformed_or_denied_launch_receipt_keeps_effect_recoverable` |
| 5 / P2: journal shapes and cleanup failures escaped untyped | Adapt: versioned root/checkpoint shape validation, counter/phase invariants, immutable-record retention, canonical encoding and chain verification precede use. Missing initialized journals fail closed. Publication and cleanup errors remain distinct and preserve the primary cause. | `test_invalid_journal_shapes_fail_closed_even_with_valid_digest`; `test_invalid_json_roots_and_deleted_journal_are_typed`; `test_publication_and_cleanup_errors_preserve_primary_failure`; existing receipt-failure test retained |
| 6 / P2: linked lock wrote outside the root | Adapt: check the supplied path before normalization, reject symlink/reparse ancestors and nonregular or multiply linked locks/events, and check opened-file identity. Initialize a lock only after acquisition, including Windows byte-range locking beyond EOF. | `test_hardlinked_lock_never_writes_external_target`; `test_hardlinked_event_is_rejected_before_adapter`; `test_symbolic_directory_and_lock_are_rejected`; `test_spawned_process_exclusion_and_single_launch` |

## Revised interface, migration and recovery

The journal/checkpoint schema is now **2**. `ContinuityScope.maximum_recoveries`
defaults to four and participates in the immutable scope digest and stable
operation ID. It is a separate inspection reserve, not more launch authority.
Launch and ordinary reconciliation budgets are unchanged. All attempt intents
are published before calls and remain consumed after exceptions or interruption.

Schema 1 journals are rejected; there is no automatic migration or reset. Retain
any historical journal and reconcile its original operation through its original
adapter before creating a fresh qualified journal. A new schema/scope must not be
used to disguise the same pending work as a new operation or replenish its budget.
There are no claimed production schema-1 consumers. Existing continuation and
promotion modules are untouched.

`step` preserves its terminal dispatch behavior. A stopped checkpoint with
`outcome_pending=true` is explicitly an unresolved possible effect, not a no-work
success. `recover` uses only `inspect` and persists `recovery-intent` first. An
authoritative STARTED result records LAUNCHED and clears the pending flag while
retaining prior refusal evidence. Authoritative ABSENT clears the pending flag
but leaves dispatch stopped. UNKNOWN, DENIED, malformed receipts and exceptions
cannot prove absence. Exhausting recovery retains the pending flag, durable
`recovery-budget-exhausted` evidence and an explicit original-adapter handoff
requirement. Reopening never replenishes any of these budgets.

Temporary files are fsynced before same-filesystem no-overwrite hard-link
publication. If publication fails and cleanup also fails, the publication error
remains primary. If publication succeeds but cleanup fails, `checkpoint-cleanup`
reports that the event was published. The next journal read under the lock may
remove exactly a same-inode `.pending-*` alias inside the root; it never removes
the published event. Unpublished orphan temporary files are inert and retained.

Rollback remains stopping the opt-in caller while preserving the journal and
adapter receipts, then reconciling pending effects through their original
adapter. Do not delete journals, reset scope budgets or discard failed attempts
to manufacture a clean rollback.

## Boundaries and evidence still owed

The adapter must independently verify repository/worktree, scope, owner authority
and every evidence reference; structurally distinct IDs do not prove independent
administration. The adapter must authenticate its receipts, enforce authority at
the actual side effect, durably deduplicate operation IDs across restarts and
controllers, and keep inspection read-only after dispatch authority expires.
It must provide bounded deadlines/cancellation and classify interrupted effects
as unknown. The synchronous library cannot safely interrupt an arbitrary Python
adapter. Typed `ContinuityError` messages supplied by the host must be sanitized
for audit retention; generic exception messages are not copied into the journal.

The host must enforce private local-directory custody and hard-link support.
Path and file-identity checks reduce accidental aliasing; they do not establish
ACLs or defeat a hostile writer racing filesystem operations. Checksums do not
authenticate custody. A live controller detects loss of a previously seen tail;
a new controller cannot detect a valid same-scope tail truncation or wholesale
replacement without an external trusted anchor. The surviving lock marker makes
an empty initialized journal fail closed, including an interrupted first
initialization; host investigation must preserve the evidence. Deleting the
whole root also destroys that marker. Power-loss durability, network filesystems
and cross-host leases are not guaranteed.

The historical Windows spawned-process receipt records one excluded competitor
(`writer-busy`), one fixture launch and both process exit codes zero, against
the **original** draft only. It is not current repair verification. Current
spawn-based acceptance exercises the native lock path on the platform running
the test, using bounded waits and child cleanup. The symlink fixture reports a
skip if Windows does not grant symlink creation; hard-link and process-exclusion
cases do not silently skip that behavior.

The first repair builder claimed no tests, static checks, independent review or
full CI receipts at that handoff. The launcher must append actual focused/platform
results, skips and independent finding dispositions before the final full gate
and delivery. Linux/Windows Python-version coverage, process-kill and long-path
fault matrices, production adapter authority/idempotence/deadlines, trusted
storage and any activation remain outstanding evidence obligations. Neither
this library nor its fixture tests constitute a complete autonomous production
controller or evidence of superiority.

## Consolidated R1/R2 repair after independent review of 5118508

The independent `/root/delivery_curator` review of commit
`511850802afe2b58c0609f12d469f3751be4a3cb` (tree
`48824828bb2c571c0ae4f25ad85361bda5bedffd`) returned **revise**. Its R1 probe
appended an impossible BLOCKED-to-RECONCILING event and observed a launch; another
appended LAUNCHED without receipt evidence. R2 found five qualification hashes
bound CRLF working-tree bytes instead of committed LF bytes. That adverse verdict,
its probes, source blob snapshots and root hash audit are retained exactly under
`evidence/live/continuity-qualification/`. The sealed review manifest SHA-256 is
`36b2458b1f83d7918c1558325a773c137012475cd0d3c41e8a5c66edb5e7181b`.
These are repository-owned MIT source/evidence artifacts, not new external
licensed code or execution authority. The earlier six findings and all 38 prior
test methods remain; no current test run is claimed by this builder.
The consolidated review attributes 38 tests (one skip), Ruff success and Pyright
zero errors/six warnings to the earlier runner against 5118508, with receipt/log
hashes checked by the Curator and root. Those historical receipts are retained;
they do not qualify this subsequent repair. The failed CLI reviewer remains
blocked evidence, and contributes no clean-review result.

R1 builder disposition: adapt, pending independent verification. Schema 2 is
unchanged. Replay and publication now validate the allowed event kind, its
predecessor and its entire checkpoint delta. Counters increment exactly at their
corresponding intent. Delivery/candidate intake and deterministic selection must
have their matching payloads. Dispatch transitions require the preceding retained
observation and launch requires the immediately preceding reconciliation's
authoritative ABSENT receipt. Every result requires its adjacent unmatched intent;
receipt fields, operation and candidate binding are reconstructed with the same
typed receipt contract as execution. The live and replay paths share receipt
state updates. Unsupported kinds, unexplained counter changes, cleared blockers,
premature success and unknown-result pending clearance fail with
`checkpoint-corrupt` before adapter calls.

BLOCKED, EXHAUSTED and LAUNCHED never reopen dispatch. A terminal checkpoint may
retain additional stop evidence. Pending-effect recovery may consume its separate
inspection reserve, retain UNKNOWN/DENIED, clear pending on authoritative ABSENT,
or record LAUNCHED on authoritative STARTED, preserving the earlier blocker.
Recovery exhaustion retains the handoff requirement. The existing recovery path's
EXHAUSTED-to-BLOCKED recovery-intent transition remains legal; it grants no dispatch
authority. Interrupted unmatched intents remain consumed and can be inspected
after restart. Self-consistent forged history, replay-time proof of historical
wall-clock freshness, authenticated custody and external truncation anchors remain
outside the library's guarantees.

R1 acceptance additions cover all three terminal dispatch regressions, success
without intent/payload, ten receipt/state or binding contradictions, unexplained
counter/blocker/pending changes, unknown event kinds, and all four receipt outcomes
after exhausted dispatch. All checks are authored and await root execution.

R2 builder disposition: adapt, pending immutable commit audit. The earlier
`CONTINUITY-QUALIFICATION-MANIFEST.json` remains unchanged historical evidence;
its recorded hashes describe the first repair's working-tree representation and
are not corrected retroactively. The new repair manifest specifies each artifact's
representation: repository text uses canonical LF bytes and an expected immutable
Git blob object ID; exact retained evidence uses raw bytes under the existing
`evidence/live/** -text -diff` attributes. SHA-256 and byte counts bind those stated
bytes. Historical source blobs are pinned to the reviewed commit and retained
exactly so shallow CI can validate them without fetching history. Original raw
review hashes and normalized-view mappings are explicit. No repository-wide Git
attribute change is needed. The manifest excludes itself to avoid a circular
digest; the root must bind its eventual committed blob in the delivery receipt.
The current artifact set must be checked against the root's immutable repair
commit before qualification, not inferred from working-tree checks alone.

The manifest regression checks canonical SHA-256/length, the actual Git clean
representation's blob ID, retained historical blob bytes, and exact original
review-to-normalized-view mappings. It requires Git, already a repository gate
dependency, and does not fetch or mutate Git state. It is pending execution.

Two bounded platform cases were added for later execution. A spawned fixture is
killed after launch intent, both before and after a flushed synthetic local effect;
restart must regain the native lock and inspect the stable operation without
observing authority or relaunching. Waits and cleanup are bounded. This covers
abrupt process death at two library/fixture boundaries, not power loss, adapter
cancellation, distributed effects or every publication microstep. A journal path
longer than 320 characters exercises registration, launch and restart; a Windows
host that explicitly returns error 206 records a skip and typed storage refusal
before any adapter call. Broader filesystem/long-path matrices and Windows/Linux
Python 3.11/3.12/3.14 execution remain unclaimed until actual receipts are appended.

Migration is validation tightening within schema 2: structurally legal prior
journals continue to replay; inconsistent journals fail closed and must be
retained for host investigation, not rewritten into compliance. Schema 1 remains
unsupported. Rollback stops the opt-in caller, retains all versions of code,
journals, failed reviews and manifest receipts, and reconciles possible effects
through the original adapter. Do not downgrade replay checks to resume a rejected
journal, erase evidence, replenish budgets or activate a production caller.
Root owns focused/static gates, separate Curator review, the subsequent full gate
and any reversible Git delivery. No launcher, test/static execution, commit, push,
PR, protected merge, production activation or external effect was performed by
this repair builder.
