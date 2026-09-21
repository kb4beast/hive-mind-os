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
- The service keeps its own package receipt store, which is consulted before the host.
  The terminal Curator revalidates retained artifacts, but the service-level receipt seam
  itself is unchanged.
- The Claude worker's command and stream contract are derived from the retained help and
  a retained canary; a changed CLI version needs fresh interface evidence.
- Sandbox isolation, model availability and independent review are not established by any
  synthetic test double used in the tests.

## Rollback

Stop only the new registered host attempt and keep all receipts and candidates as local
artifacts; disable the factory registration through ordinary reviewed configuration. No
source branch reset, evidence deletion or remote cleanup is needed, because H1 performs no
remote write.
