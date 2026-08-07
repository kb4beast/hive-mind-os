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

`ContextCompiler` is a deterministic hot/warm/cold selector. It filters memory by
record scope, explicitly granted role and data scopes, availability, validity, and
lifecycle state. It scores eligible records with the Phase 6 fixed weights, selects
whole records under a declared hard token budget, and leaves the rest as cold
references. Explicit cold retrieval creates a new immutable manifest revision;
existing manifests remain addressable. Evaluator mode excludes scratchpad and
self-assessment material marked unavailable to evaluators.

`ContextManifestStore` may persist canonical manifests below a caller-selected local
root. Restore verifies the contract and digest and refuses corrupted files. Lesson
consolidation is explicit and deterministic: it requires separately evidenced active
episodes from distinct caller-declared contexts plus an evaluator and outcome reference;
it creates a successor and append-only supersession facts.

The current implementation intentionally does not add a database projection,
background job, CLI command, model invocation adapter, or legacy-command rewiring. The
catalog can reproduce its active-memory view from a deterministic local snapshot of
immutable records, lifecycle facts, and conflicts. Callers pass `now` explicitly; no
selection depends on wall clock state or provider tokenization.

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
