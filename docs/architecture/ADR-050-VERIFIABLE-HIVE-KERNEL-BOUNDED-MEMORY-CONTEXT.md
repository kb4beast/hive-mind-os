# ADR-050: Verifiable Hive Kernel bounded memory and context primitives

## Status

Proposed Phase 6 candidate. This is a local deterministic primitive only; it does
not invoke a model, create a role handler, dispatch an effect, access a network, or
alter any legacy memory path.

## Decision

`MemoryArtifactStore` accepts only immutable UTF-8 bodies under a caller-chosen local
root and addresses them by SHA-256. Secret-like values and explicit raw transcript
content types are rejected before persistence. `MemoryCatalog` retains immutable
`MemoryRecord` metadata, append-only lifecycle facts, and conflict records. A new
record supersedes old records through lifecycle facts; neither source content nor
prior metadata is rewritten.

Memory classes are closed to evidence, facts, episodes, opinions, lessons, working
context, scratchpad, and self-assessment. Policy remains outside the memory plane.
Working memory must be scoped to one work item and carry an explicit expiry.

`ContextCompiler` is a deterministic hot/warm/cold selector. It filters memory by
record scope, explicitly granted role and data scopes, availability, validity, and
lifecycle state. Explicit sensitivity scopes also filter the view; the fixed retrieval
score penalizes material whose sensitivity was not required and derives freshness from
the record validity window plus caller-supplied time. It selects whole records under a
declared hard token budget and leaves the rest as cold references. Explicit cold
retrieval creates a new immutable manifest revision; existing manifests remain
addressable. Evaluator mode excludes scratchpad and self-assessment material marked
unavailable to evaluators.

`ContextManifestStore` may persist canonical manifests below a caller-selected local
root. Restore verifies the contract and digest and refuses corrupted files. Lesson
consolidation is explicit and deterministic: it requires separately evidenced active
episodes from distinct caller-declared contexts plus an evaluator and outcome reference;
it creates a successor and append-only supersession facts.

`MemoryCatalogStore` persists content-addressed catalog snapshots and reconstructs the
active view only by replaying their immutable records, lifecycle facts, and conflicts.
The local CLI exposes `kernel memory search`, `kernel memory inspect`, `kernel memory
expire`, and `kernel context`. Search and inspection return metadata and scores, never
durable body text; expiration writes a successor snapshot and leaves prior snapshots
untouched.

The current implementation intentionally does not add a database projection,
background scheduler, model invocation adapter, or legacy-command rewiring. Callers
pass `now` explicitly; no selection depends on wall clock state or provider
tokenization.

## Consequences and rollback

The addition is isolated to `brain_kernel.memory` and `brain_kernel.context` plus
focused tests. It creates artifacts only when a caller supplies a local directory;
the primitive does not select an application state directory. Rollback removes these
additive files and leaves legacy state untouched. Content-addressed bodies and
append-only manifest/lifecycle facts are not rewritten by rollback.

## Evidence obligations

Focused tests demonstrate artifact integrity, secret/transcript refusal, lifecycle
facts, conflict preservation, deterministic ranking, scope exclusion, canonical
manifests, evaluator isolation, explicit cold retrieval, and hard whole-record token
budgets. Advocate, Cross-Examiner, Expert Witness, Curator, and Judge dispositions
remain open; this ADR makes no adoption or promotion claim.
