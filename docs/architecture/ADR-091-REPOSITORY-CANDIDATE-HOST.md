# ADR-091: Durable local candidate host for an external repository

## Status

Adapted implementation candidate for the first bounded slice (H1). It is architecture
implementation, not a grant, a delivery, a pilot completion, an isolation qualification
or a production claim. Independent Curator reproduction and a separate Judge verdict on
the final bytes remain required and are arranged outside the Builder.

## Decision

Add one generic host, `whole_os_repository_host.py`, that composes the existing
`WholeOSCompositionHost` seams into a local *preparation* path for one external Git
repository task:

1. A frozen, host-owned `RepositoryTaskBinding` seals tenant, repository, source path,
   full base commit and tree, package/graph/context identity, allowed and protected paths,
   the acceptance manifest, held-out digests, worker and evaluator identities, sandbox
   requirements and measured identities, finite budgets and a private state root. Its
   digest namespaces every durable record. Target metadata can name a binding but cannot
   supply imports, argv, credentials or authority.
2. `RepositoryBuilderAdapter` implements the existing `BuilderAdapter` protocol over a
   real injected patch-proposing worker. Every model call is bracketed by an exclusive
   start record and an outcome record. The host, not the worker, applies the patch.
3. `ReceiptBoundCandidateQualifier` overrides `CandidateQualifier.qualify`. It verifies a
   retained candidate in a separate remote-free clone and never returns a count-based pass.
4. `RepositoryCompositionHost` wraps replay, namespace and the terminal Curator.
   `compose_repository_factory` preflights every dependency before any service attempt
   exists and returns a factory for `WholeOSHostBootstrap`; it never registers it.

`local_claude_worker.py` is an optional, thin, tool-free worker for the installed Claude
Code CLI. It is used only when the root supplies no other compatible worker.

## Judge conditions and how they are met

- **Terminal replay is guarded.** The composition receipt path is namespaced by the full
  host binding digest. A retained COMPLETED or NO_CHANGE result is returned only after
  the subject is revalidated, current admission is confirmed by the injected host
  registry, the candidate is re-derived from Git and disk (commit, tree, parent, change
  set, patch bytes, remotes, cleanliness, Git operation receipts) and the retained
  qualification is reloaded (artifact digests, measured identities, executed-test counts).
  A failing check preserves the old result as a historical receipt and returns a typed,
  unsealed blocker. `assess_terminal_candidate` performs the same revalidation.
- **Held-out tests never reach the Builder.** `build_source_packet` gained a
  `withheld_paths` parameter: withheld tracked files stay listed as omitted with no size
  or blob hash. Held-out bytes are supplied only at verification by an injected custody
  object and overlaid onto the verifier clone; the overlay is digest-checked and recorded
  separately from the candidate tree. A backstop refuses to start a worker if held-out
  bytes or digests appear in its input. Repair feedback is host-authored text only.
- **Repair lineage is explicit.** Each proposal is a complete replacement patch for the
  same admitted base and is applied to a fresh clean detached clone. Only the selected
  proposal is committed, as a single commit whose parent is exactly the admitted base.
  Prior proposals, refusals and losing clones are retained and charged. At most one call
  plus two repairs fit the budget ceiling; an identical repeated refusal fails closed.
- **NO_CHANGE is faithful.** A verified no-change candidate makes no delivery call. The
  composition host gained a `_no_change_permitted` hook: NO_CHANGE closes a package only
  when the binding permits it and publication is not required; otherwise the unmet
  outcome is a sealed FAILED result. A worker failure, malformed report, missing
  capability or failing tests are never relabelled NO_CHANGE.

## Persistence and interruption

Records live under the private state root, outside the source and the Hive tree, and are
created exclusively (temporary file, flush, fsync, hard-link publish). Differing bytes for
an existing name are a conflict. The attempt key is derived from the binding and the full
package payload and excludes discovery output, so a re-run cannot mint a new budget.

- Restart after `candidate.json` returns the identical candidate with no model call.
- A slot with a start record and no outcome is adopted only if the worker's own receipt
  exists and its process is proven ended; a dead process without a receipt is charged and
  terminal; a live or unprovable process raises `RepositoryHostUncertain`, which is never
  sealed. No duplicate worker starts.
- Corrupt, partial or contradicted retained evidence is `RepositoryHostBlocked` (a sealed
  typed blocker at the builder boundary, a non-passing receipt at the qualifier boundary).
- Budgets are cumulative because they are derived from ledger records. Recovery after an
  exhausted or blocked attempt uses a new explicit attempt identity, with its own admitted
  budget; nothing is deleted or rewritten.

## Qualification

The qualifier validates every request field against the frozen binding and the retained
candidate, seals the verifier command independently, runs each acceptance check through
the existing `verify_repository` in a distinct clone, and then reads the resulting receipt
from disk: digest self-consistency, sealed command, selected tests, sandbox and toolchain
identity digests, allowed environment names, stdout/stderr digests and a host-owned result
reader. Only executed, non-skipped tests count; a zero, all-skipped, failing or unparsed
result never passes. The default hostile-code isolation and network-deny requirements are
unchanged; a missing sandbox blocks before any test executes.

An explicitly weaker profile is allowed only when the binding is labelled trusted-local.
Every retained receipt, check origin and terminal message then carries
`trusted-local-unqualified`, and `pilot_production_qualified` is always false. There is no
automatic fallback between profiles.

## Authority and boundaries

No grant, credential, owner anchor, key or service is created. The Curator, admission
registry, worker, sandbox and held-out custody are injected dependencies. A Builder-issued
identity string is never accepted as a Curator. Delivery is local only: the host refuses a
broker with a transport or grants, and `LOCAL_ARTIFACT_READY` re-preparation is idempotent.
The retained candidate is consumable by a later controlled-delivery bridge without
rerunning the Builder or changing the request.

## Limitations

- The host runs no tests during the build phase; tests execute only in the qualifier.
- The result reader covers the Python `unittest` adapter only; other adapters are typed
  incomplete. The reader is evidence inside a trusted harness, not a defence against a
  hostile interpreter forging its own summary.
- Identity digests for the sandbox, toolchain and environment are supplied by the trusted
  host; this module measures and reconciles them but does not discover them.
- Hosts other than this one keep the original service contract: without the optional
  `validate_retained_package_result` method the service trusts its own package receipt
  (see the repair section). No default verifier exists, on purpose.
- The Claude worker's command and stream contract are derived from the retained help and
  a retained canary; a changed CLI version needs fresh interface evidence.
- Sandbox isolation, model availability and independent review are not established by any
  synthetic test double used in the tests.

## Repair after independent baseline review

An independent Curator reproduced counterexamples against the first candidate. This
section records the repair choices exactly. **The Builder ran none of the tests below;
every claim here is UNRUN by the Builder until the root and a separate Curator run them.**

### R1. Outer terminal replay (was: cached success delivered after revocation/corruption)

Threat: `WholeOSService` keeps its own package and terminal receipts, so
`run_to_completion` reported `complete` from cache after admission was revoked (same or
recreated service) or after `candidate.json` was replaced, never asking the host. The
host's own replay guard was correct but unreachable on that path.

Choice: a minimal, optional seam in `whole_os_service.py`. A host may implement
`validate_retained_package_result(package, result, payload) -> str | None` (protocol
`WholeOSReplayValidator`). When present, every place the service counts a package as
complete asks it: `_completed()`/`_classify_done()` (used by enqueue, claim, terminal
candidate, terminal assessment and `observe`), and `_retained_package_result()` (crash
window replay). A reason, an exception, or a non-`None` untyped verdict all reject
(fail closed). A rejected package is reported `blocked` with a
`retained success failed revalidation: ...` message; it is not in
`completed_packages`, its dependents are blocked, a queued dependent of it is not claimed,
and no terminal assessment is loaded or run. Retained receipts are left untouched as
history; nothing is deleted or rewritten. Verdicts are memoized only inside one public
operation, so every resume, recreated service or factory, and every `observe` asks again.

`RepositoryCompositionHost` implements the method read-only: it recomputes the
binding-namespaced payload, loads the host's own terminal receipt (absent for another
binding), requires the service receipt to equal it, then applies the same replay check the
direct path uses (subject, current admission via the injected registry, candidate re-derived
from Git and disk, qualification artifacts and executed-test counts). It never runs a
worker, writes a record or mutates Git, so a rejected replay causes no duplicate model
work. Recovery from a rejected replay is an explicit new attempt identity, as before.

Compatibility: a host without the method behaves exactly as before. This is an explicit
contract, not a fabricated default; a default could only pretend to verify evidence it
cannot see. Limitation: a dependent already running when its dependency is later rejected
is not interrupted.

### R2. Claude stream parser (was: bag-of-events acceptance)

Threat: the parser accepted a missing or duplicated internal tool_result, an unlisted
nested event type, an assistant event without a session, an assistant/init model conflict
and events after the terminal result.

Choice: `parse_claude_stream` is an explicit state machine built from the retained canary
sequence (init, status, message_start, tool block start/deltas, assistant envelope, block
stop, tool_result, message_delta, message_stop, rate limit, result). Every event must name
the init session; init must be first and unique; every model field equals the init model;
only the listed stream events, one message, one `StructuredOutput` tool block (and inert
text blocks) are allowed; the streamed JSON, the assistant envelope, the result's
`structured_output` and the result text must agree; exactly one tool_result must answer
that envelope with the retained acknowledgement text; nested-agent events, subagents,
denials, other-model usage and anything after the terminal result are rejected. The
acknowledgement text is pinned to the canary, so a CLI version change fails closed until
fresh interface evidence is retained. Limitation: a real run that emits more than one
message is rejected until evidence shows it is harmless.

### R3. Process pipes (was: ResourceWarning after a deadline)

`_run_claude_process` now closes stdin/stdout/stderr after reader termination and reaping,
but only for pipes whose reader thread has finished (closing a buffer another thread is
blocked in could itself block). Joins stay bounded; a reader that outlives its process
raises `RuntimeError` and the worker records a failed receipt.

### R4. Windows path length (was: WinError 3 inside a run at a 268-character path)

Root cause: `SandboxRunner` and `GitWorkspace` publish fixed-name artifacts without
extended-length paths, so a deep private state root failed after effects had begun.

Choice: bounded H1 validation instead of a filesystem rewrite. `RepositoryHostContext`
computes the worst-case fixed artifact path of a verifier clone and the deepest
materialized checkout path, and checks them against a limit (259 on Windows, none
elsewhere; injectable so it is tested on every platform). It runs in `preflight()` (before
factory admission and before any worker budget), at the top of `build()` before any write,
and before qualification executes. A worker patch path beyond the bound is a repairable
refusal. The unsupported-root blocker is not persisted under the rejected root.
**Supported bound:** on Windows the private state root must be at most 72 characters
(259 minus the 187-character fixed span), and every tracked repository path must fit in
`259 - len(state root) - 116` characters. Roots beyond it are a typed
`BLOCKED_CAPABILITY`, never a pass and never silently shortened.

### R5. Static findings

The eight pyright errors were fixed by real narrowing (dictionary checks before
subscripting, a `str` patch type, a typed preflight result) and the two ruff import
findings by sorting and wrapping; no suppression and no weakened validation.

### Threats not addressed

Model availability, sandbox isolation, held-out custody strength and independent Curator
identity remain external dependencies. Nothing here claims pilot, production or delivery
readiness, and the trusted-local profile stays labelled unqualified.

### Repair tests (UNRUN by the Builder)

`tests/test_local_claude_worker.py` (mutation table over a canary-shaped transcript, pipe
regression), `tests/test_whole_os_integration.py::WholeOSRetainedReplayTests` (service seam
with a synthetic validating host), `tests/test_whole_os_repository_host.py`
(`RepositoryHostOuterReplayTests`, `RepositoryHostPathBoundTests`).

## Correction 2026-09-21: three boundary defects found by the independent Judge and a real canary

The sections above are kept as written; three of their claims were wrong or incomplete and
are corrected here. **All repair tests below are UNRUN by the Builder.** Earlier evidence
(the failed real-canary run, its retained-replay pass with a clone-local
`core.autocrlf=false`, and the Judge's reproductions) is preserved and unaltered; the
replay pass proves the proposal was valid, not that this host was deterministic.

### C1. Retained-success memo was instance-wide (corrects R1)

R1 said verdicts were "memoized only inside one public operation". They were held in an
attribute of the service object, so two overlapping public calls shared one dictionary:
with a barrier between them, admission revoked after the first call classified the package,
the second `observe()` returned `complete` without asking the host (validator count
unchanged) and only the next non-overlapping call blocked. Repair: the memo now lives in a
module `ContextVar`, keyed by service identity. A public call opens a fresh scope unless its
own execution context already holds one for that service, which is exactly a nested call
made for the same invocation (so `observe()` still asks the host once, not once per
internal `_completed()`). Independent threads, tasks and resumed calls start from their own
context and never share a verdict. Cohort pool workers start with an empty context and ask
the host directly. No lock is added and no verdict outlives its outermost call.
Residual scope: a thread that deliberately copies its parent's context (or a runtime that
inherits context into new threads) shares that parent's invocation, by design; a verdict
is still never shared across invocations. Regression: forced overlap with revocation
between the calls asserts fresh validation, a blocked second call, and one worker and one
terminal assessment in total.

### C2. Executable was not rechecked at dispatch (corrects "preflight recheck")

`preflight()` saw a replaced executable but `run()` still invoked the runner and returned
`completed` under the old hash. `run()` now re-hashes the sealed executable on every
dispatch and, on drift or an unreadable file, records a failed receipt (`dispatch.dispatched`
false, sealed and observed digests, `matches_sealed` false) before the runner is reached: no
process, transcript or `process.json` exists. A successful run records the observed digest
that matched. **Residual TOCTOU:** the check is hash-then-launch, not atomic. The file can
still be replaced between the hash and the operating system starting the process. Closing
that would need an exclusive or content-addressed launch this worker does not have, so no
atomicity is claimed; the per-dispatch check narrows the window from "since construction"
to one read and one spawn.

### C3. Ambient Git configuration changed accepted bytes (real Haiku canary)

Root cause, observed on Windows: the host materializes clones under `core.autocrlf=false`
but called `apply_proposed_patch` directly, which ran Git with the machine's configuration.
System `core.autocrlf=true` made `git apply` write the one-line, LF proposal as CRLF (26
bytes became 28), and the exact-byte guard failed before any test ran. The retained replay
that passed set clone-local `autocrlf=false`, which is precisely the untrusted, clone-local
reliance to avoid.

Repair, in `local_evidence_packet.apply_proposed_patch(..., isolate_git_config=True)`, which
the host now always passes:
- Ambient user, system and every `GIT_*` variable are excluded **for the child processes
  only** (`GIT_CONFIG_NOSYSTEM=1`, an empty per-call `GIT_CONFIG_GLOBAL`, all other `GIT_*`
  dropped). No global, user or system Git file is read for these calls or modified.
- The keys that decide written bytes are pinned on the command line, which outranks the
  clone's own `.git/config`: `core.autocrlf=false`, `apply.whitespace=nowarn`,
  `apply.ignoreWhitespace=no`, and an empty `core.attributesFile`. This mirrors
  `GitWorkspace`'s policy, so materialization and application agree.
- Repository `.gitattributes` are part of the pinned tree and remain honored, exactly as at
  checkout; a `text eol=crlf` repository therefore keeps CRLF consistently. Filter drivers
  cannot come from the excluded global config. The clone's remaining local config is still
  read, acceptable only because the host creates that clone.
- Detection, not normalization: if neither the old file nor the patch contains a carriage
  return and one appears after apply, the files are restored byte for byte and the patch is
  refused. Acceptance bytes are never rewritten to hide a change.
- The host now uses the receipt's own observed change set instead of re-reading the tree
  under ambient config, and its read-only retained-clone checks pin `core.autocrlf=false`.
Existing callers are deliberately unchanged: the default remains ambient behavior, which
local DAG runs rely on for genuine Windows CRLF checkouts (the existing autocrlf test still
covers it). The new mode is opt-in per call; forcing it globally would break those runs.

Threats and limits: a repository that intentionally converts line endings is not refused
(it is deterministic per pinned tree); an attacker able to write `.git/info/attributes` or
filter drivers into the clone before application is out of scope because the clone is
host-created; the carriage-return guard does not detect other filter effects.

### Repair tests added (UNRUN by the Builder)

`tests/test_whole_os_integration.py` (nested calls share one verdict, forced-overlap
revocation, concurrent independent runs), `tests/test_local_claude_worker.py` (dispatch
recheck recorded on success; drift and removal refused before dispatch; sealed bytes
restored dispatch again), `tests/test_local_evidence_packet.py` (real Git with ambient
`autocrlf=true` reproduces the CRLF growth in the ambient mode, isolated mode preserves the
exact bytes, hostile clone-local settings ignored, conversion guard restores and refuses,
default unchanged), `tests/test_whole_os_repository_host.py`
(`RepositoryHostAmbientGitConfigTests`: exact committed and worktree bytes, qualification
passes with two actually executed tests, one model call). The ambient reproduction skips
with an explicit message on a Git that does not convert on apply.

### Rollback for this correction

Each part is independent and additive. C1: revert the `ContextVar` scope only if the
validating-host seam is also reverted; alone it would reopen the overlap defect. C2:
revert the dispatch recheck; `preflight()` is unchanged. C3: pass
`isolate_git_config=False` (or revert the parameter) to restore ambient behavior, which
reopens the Windows conversion failure; evidence and candidates are never deleted.

## Correction 2026-09-21 (remand 3): copied context, fsmonitor helper, test cleanup

Earlier text is kept as written. **Every repair test named here is UNRUN by the Builder.**

### C4. WITHDRAWN: "inherited context is the same invocation" (corrects C1)

C1 said a scope inherited through `contextvars` "is the same invocation, by design", and
that verdicts are never shared across invocations. **That claim is withdrawn.** The
independent Judge showed it false: a context copied inside a first public `observe()` and
run after revocation returned `complete` with no host call, both while the first call was
still open and after it had exited. Treating "an entry exists in the context" as proof of
nesting let any caller-held scope authorize a public call.

Repair (still no scheduler redesign): **every public entry establishes a fresh scope
unconditionally** through one private context manager, `_invocation()`, whatever the
inherited context holds. The public entries are the constructor, `run_once`,
`run_cohort` and `observe`; `run_to_completion` opens a fresh scope on each of its public
`run_cohort`/`observe` calls, so a long loop is also re-validated per wave. Private helpers
(`_observe`, `_run_cohort`, `_run_once`, `_classify_done`) assume their public caller opened
the scope and share its memo, so one call still asks the host once per package. The scope
object is closed and emptied when its call exits, so a copied context kept alive afterwards
holds only a dead scope that memoizes nothing. A re-entrant public call (for example from a
host callback) validates fresh. No thread id or context identity is used to infer
invocation. Regressions: the original two-thread overlap; a context copied inside a public
call used for `observe`, `run_once`, `run_cohort` and `run_to_completion` while the first
call is open and again after it exits; four concurrent calls in copies; and the
nested-call efficiency count (one host validation per `observe()`), with worker and terminal
assessment counts asserted at 1/1.

### C5. Read-only Git helper executed an ambient `core.fsmonitor` command

Root cause: the host's retained-state reader (`_git_bytes`) scrubbed only a few
`GIT_CONFIG_*` names and left the user's global Git configuration, so a global
`core.fsmonitor` command was launched by `git status` and the status still returned clean.
Repair: the reader now reuses the patch helper's per-child isolation
(`_isolated_git_invocation`, which gained `core.fsmonitor=false`): every `GIT_*` variable
dropped, `GIT_CONFIG_NOSYSTEM=1`, an empty global config and attributes file in a per-call
scratch directory, and `core.autocrlf=false` plus `core.fsmonitor=false` pinned on the
command line, which outranks the inspected repository's own `.git/config`. The parent's
environment is never mutated and no Git file is edited. The retained target, base and
commit paths are unchanged. The added `core.fsmonitor=false` also applies to the opted-in
patch mode; it only prevents a helper launch and changes no written bytes, and the previously
accepted patch behavior is otherwise unchanged.
Regression: an inert marker-writing fsmonitor command as an ambient global setting, as a
clone-local setting, and both; a control run proves the plain Git launches it (skipped with a
message on a Git that does not), the reader does not launch it, the parent environment is
unchanged, and status/diff/rev-parse/ls-tree/remote reads still report real state, including
a real edit. The store's own retained-candidate load is covered end to end.
Limits, stated honestly: this is trusted-host hygiene, not hostile-code isolation. The
repository's other local configuration is still read; other helper-launching keys not
listed above are not enumerated; a repository that needs a global `safe.directory` entry now
fails closed instead of being trusted; `GitWorkspace` remains the owner of clone creation and
is unchanged. Legacy callers of the patch helper keep the ambient default.

### C6. New service tests leaked SQLite handles on Windows

The three tests added in remand 2 used a `with TemporaryDirectory()` block whose exit ran
before the registered `service.close`. They and the new regressions now enter the temporary
directory with `enterContext`, so cleanup runs in last-in-first-out order and the service
closes first. No cleanup or `ResourceWarning` is suppressed.

### Rollback for this correction

C4: reverting `_invocation()` to a presence check reopens the copied-context defect. C5:
restoring the old reader reopens ambient helper execution. Neither deletes evidence.

## Rollback

Stop only the new registered host attempt and keep all receipts and candidates as local
artifacts; disable the factory registration through ordinary reviewed configuration. No
source branch reset, evidence deletion or remote cleanup is needed, because H1 performs no
remote write.

The service seam is additive and inert without a validating host: reverting the
`whole_os_service.py` change restores the previous behavior for every other host. For this
host the seam can only make a success stricter, so rolling it back reopens the stale-success
defect; keep it unless the host is disabled.

Root validation after the first repair: 18 worker tests, 41 repository-host tests and 17 service integration tests pass locally; Ruff and Pyright pass. The first integration-test run failed Windows TemporaryDirectory cleanup because service.close had been registered for the later unittest cleanup phase. Root placed the seven new directories on unittest's cleanup stack before registering service closers, preserving LIFO lifetime ordering and every behavioral assertion. The failed first log is retained. These focused passes do not substitute for independent counterexample replay, an actual provider canary or the full integrated CI gate; those remain separate obligations.

## Independent disposition and validation, 2026-09-21

The final remand-3 candidate passed 22 service integration tests, 47 repository-host
tests, 23 evidence-packet tests (one platform skip), and 20 Claude-worker tests.
Ruff and Pyright passed. These are root-executed results; the Builder's earlier
UNRUN statements remain historical and are not retroactively rewritten.

The separate Curator adopted the bounded trusted-host repair after replaying the
original 39 assertions, three positive exact-byte Git policy assertions, the
preserved legacy ambient-CRLF negative control, and 19 fsmonitor assertions with
real global/local inert-helper controls. The source seal was unchanged throughout.
Report SHA-256: `2a6bf52259af3b1fdd8b9c85b9c34e3d6e77cdd5506dd14a4181896511750ffb`;
manifest: `268ec4ac0fc971f74735fd3bbf624ebb4709a22ff1d3f1c56c786a86f7052898`.

The separate Judge issued scoped ADAPT for the retained-replay and executable
binding repairs. Original ordinary-thread and executable-drift probes, copied-context
overlap and post-exit probes, and 12 retained-replay tests passed without duplicate
worker or terminal execution. Report SHA-256:
`9f39de8f20e37a48d38b7854ce9d3ddc8b93dcb0e12717532b3f2a9f181fe5a7`;
manifest: `62a4f7f4281dab8dbdff47b925c13b701592418560fc01ee44b3a37f914c1ba8`.
The Judge's independent Git condition is supplied by the Curator evidence above.

One actual Haiku call produced a valid structured proposal. The original host run
rejected Git's ambient LF-to-CRLF conversion before tests; that failed receipt is
preserved. Retained proposal replay and the final real-Git isolation controls passed
without another model call. This does not claim a newly completed live mission.

Mandatory full integrated CI on the stacked delivery checkout is still pending at
this dated entry. Local H1 preparation does not grant remote-delivery authority,
complete H2, admit a pilot, provide hostile isolation, or close production readiness.
All losing probes and receipt corrections remain in the operator's append-only
production-closeout evidence bundle.

## Correction 2026-09-21 (Builder local repair): process pipe ownership bounds

The initial GitHub Python 3.14 run reported one failure in
`ClaudeProcessRunnerTests.test_no_pipe_is_left_open_after_a_deadline_an_output_cap_or_a_normal_exit`
(run log: `h1-github-linux314-job.log`). The global `gc.collect()` captured four unrelated
SQLite ResourceWarnings from earlier tests, not from the process runner. The test's
warnings oracle could not distinguish actual pipe leaks from ambient finalization.

**Repair:** Replaced the global gc/warnings oracle with direct ownership-bound checks
patterned after `tests/test_docker_verification.py::BoundedRunnerTests`. The new test:

1. Wraps `subprocess.Popen` via `mock.patch` to capture each real child process
2. Retains the original `Popen` factory and calls it once per test case (three real
   children: timeout, output-cap, normal exit)
3. Safely cleans up retained processes in a try-finally block even if assertions fail
4. Asserts each real child is reaped (`poll()` is not None, `returncode` is not None)
5. Asserts each pipe handle present (stdin/stdout/stderr) is closed when the reader thread
   finished and the child was reaped

Expected results (timeout/cap/normal exit) are retained: timeout=True, limited=True,
code=0. No production `_run_claude_process` behavior changed; the test verifies the
existing `_close_pipes` implementation closes only after reader termination and reaping.

**Unrun tests:** `ClaudeProcessRunnerTests.test_no_pipe_is_left_open_*`. Root did not
re-run the full CI after the repair; the separate Curator will validate the closed-handle
assertions and verify that the three real children exit as expected and no warnings remain.
No production-worker authority, mission or source changes; the repair is test-only.

### Root correction and independent pipe-test disposition

The Builder's first replacement cleaned up children before inspecting them and
called `poll()` in the assertion. That could conceal an unreaped child. Root
revised the test to inspect the exact runner child's already-set `returncode`
and all three present, closed pipe handles immediately after each runner call,
before any poll, wait, kill or test cleanup. The finally block cleans up even
when those observations fail. Exact argv separates the worker child from a
Windows process-tree termination helper. No production worker code changed.

The independent Curator executed seven controls: the real normal/deadline/cap
test and genuine unrelated SQLite finalization both pass; deliberately open
stdout/stderr, open stdin, a genuinely running unreaped child and a corrupted
raw returncode each fail the intended assertion. All owned children and handles
were cleaned after observation. Report SHA-256:
`b8caad3dc26cde492ca46e5f6c12d54e30c9d310956dc452e1f096d25f5e4a51`;
manifest: `09c122d6d19afb65afdb7f647348bfc31b45fd00e8a273f941a3a3dde30dee36`.
Root's 20 worker tests pass; Pyright passes. Removing the Builder's unused
`threading` import then made Ruff pass without a behavioral change.

The original Linux Python 3.14 result is 2,244 tests, one failed cleanup-oracle
test and 34 skips. The initial local integrated run was deliberately stopped
after that failure was known; its partial log remains incomplete evidence.
Both are preserved. A corrected-head full local and GitHub gate remains required;
neither this correction nor the scoped Curator verdict substitutes for it.

## Correction 2026-09-21: clock-independent test fixture identities

At `8a9dda3e2a7fce8482d2cdc9b54e1b51212d5553`, the complete local gate
passed 2,244 tests with 14 skips. GitHub run `35558867283` passed nine jobs
but Windows Python 3.12 failed with nine fixture-creation errors. Multiple
`time.monotonic_ns()` calls returned the same tick, so scratch paths collided
before worker assertions ran. The original CI log remains retained as
`h1-github-windows312-failure-35558867283.log`.

The repair assigns fixture names from a per-test counter inside the existing
unique temporary root. Scratch creation, stream contents and intentionally
uncreated evidence paths retain their original semantics. One new regression
freezes the clock while creating 60 distinct scratch, stream and evidence paths.
No existing acceptance assertion was removed or changed, and production worker
SHA-256 remains `e0beaeca61cc86bd091d2d39ebb86450cb535ed054ef3e946e69a1ec6d8c4254`.

Independent Curator `/root/readiness_judge` reproduced 13 collision errors in
the original 20 methods under a frozen clock on Python 3.12.10; the repaired
21 methods pass with zero skips. AST comparison preserves all original methods
and assertions. Separate controls retain 20 different stream contents, 20 empty
scratch directories, and distinct completed-worker evidence directories.
The exact repaired test SHA-256 is
`e82b8c47880dcab65ce2a14afe728a131eaccdec1cd020558e24592a0e4a5d18`.
The scoped disposition is ADOPT, subject to the complete CI gate. Review digest:
`2f2a5903aa046487cb485bda0f8010842daf3068e74f4c91464102d64de7e36c`;
receipt: `dc302110c421767c5eb5393789a68dcfe5ddd4fd5290f8d6b64a25915eddd9b3`.

Root's focused 21-test run also passes. This test-only correction supplies no
additional runtime authority or pilot admission. Rollback reverts the test
counter and new regression, retaining the failed CI and independent controls.
The full corrected-head local and remote gates remain required.
