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
