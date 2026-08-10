# ADR-054: Verifiable Hive Kernel local compatibility firewall

## Status

Implemented locally; the complete local Builder gate has passed, but the independent
courtroom disposition remains deferred. This phase is local and deterministic only. It
does not invoke providers, APIs, network services, remote Git, remote CI, credentials,
or external processes. It does not migrate, rewire, or write to a legacy flow, and it
does not alter a historical receipt body.

## Context

Phase 9 adds a read-only kernel technical-closeout inspection path and preserves
historical receipts as opaque references. Its local behavior is covered, but the
required compatibility proof has not yet established all of the following together:

1. Phase 1-8 event/projection fixtures replay identically before and after closeout
   inspection;
2. representative historical receipt bytes remain unchanged across success, partial,
   blocked, malformed, and missing-state inspection paths; and
3. legacy CLI routes do not load the closeout service merely by importing their route.

Those facts are a prerequisite for a later local challenger or learning lane. Without
them, adding any new kernel improvement mechanism would widen the compatibility surface
before its preservation boundary is executable.

## Decision

Add a narrow compatibility firewall around the Phase 9 closeout surface.

1. Load `brain_kernel.closeout` only from the `kernel closeout` execution path; no
   module-level legacy CLI route imports it.
2. Introduce deterministic, checked-in Phase 1-8 event-stream fixtures and a
   compatibility harness that records each fixture's event head, replayed projection
   digest, and canonical byte manifest before read-only closeout inspection. The same
   values must match afterward.
3. Use representative historical receipt fixture trees only as byte baselines. The
   kernel may retain an opaque reference and its existing digest, but may not open,
   copy, normalize, re-sign, translate, delete, or rewrite receipt contents.
4. Exercise successful, partial, blocked, corrupted-bundle, missing-state, and
   malformed-input closeout paths. Every path must leave the state database event
   sequence, projection, and receipt-tree byte manifest unchanged.
5. Make no new kernel event type, schema, store, legacy adapter, dual writer, prompt
   champion, experiment record, provider configuration, or effect adapter.

The compatibility harness is authoritative only for its checked-in local fixtures. It
does not claim that an arbitrary external, provider, Git, or historical system is
compatible.

## Consequences and rollback

The expected implementation is confined to a lazy closeout import, a test-only
compatibility harness and fixtures, and focused tests. Existing CLI command behavior,
legacy stores, ledgers, receipt validators, schemas, and Phase 1-9 event semantics
remain unchanged.

Rollback removes the additive compatibility test surface and disables the additive
`kernel closeout` route if necessary. It retains existing kernel events, local evidence
bundles, golden fixtures, legacy state, and historical receipt artifacts. It never
restores a dual writer, deletes receipts, or rewrites an event stream.

## Evidence obligations

Before implementation, retain an append-only case record with the Phase 9 source
references, an Advocate case, a separate Cross-Examiner case, local compatibility
testimony, a Curator reproduction plan, and a Judge disposition. The Judge must be a
different identity from the Architect and Builder.

Focused tests must prove lazy-import containment, Phase 1-8 replay equivalence,
historical-receipt byte preservation, read-only database preservation, and unchanged
legacy route behavior. The complete local CI gate remains required for a passing
technical claim. Independent courtroom promotion remains an open obligation.

## Local implementation evidence

On 2026-08-08, the focused Phase 9-10 suite passed 7 tests and the full
`test_brain_kernel*.py` family passed 68 tests in 3.842 seconds using the local virtual
environment. Those tests cover lazy closeout import containment, Phase 2-8 read-only
replay, successful/partial/blocked/malformed/missing closeout outcomes, historical
receipt-tree byte manifests, and existing kernel behavior.

The required complete local gate ran 524 tests in 990.353 seconds with 5 expected
skips, 1 failure, and 2 errors. The PIT path-length error passes when `TEMP` and `TMP`
are set to the local short root `C:\t`; the remaining reproducible failure is
`test_timeout_covers_early_parent_exit_and_background_child` in the unrelated sandbox
surface, which leaves a Windows file lock and does not raise its expected timeout.
This ADR therefore makes no full-gate-passed claim.

### Correction ledger: final Builder gate and court resumption

The remaining short-root failure was a synthetic long-path fixture whose constructed root
measured 259 characters despite its greater-than-260 precondition. Lengthening only its
synthetic final segment corrected the fixture without changing receipt validation or any
Phase 10 behavior. On 2026-08-08 with `TEMP` and `TMP` set to `C:\t`, the local Python
3.14 virtual environment ran `python -m unittest discover -s tests -v`: 526 tests passed
in 1043.431 seconds with five expected skips. This supersedes the prior local Builder
full-gate failure only.

During court resumption, the same Builder identity reran
`tests.test_brain_kernel_compatibility`, `tests.test_brain_kernel_closeout`, and
`tests.test_sandbox`; 32 tests passed in 5.158 seconds with one expected POSIX-only skip.
Neither check is independent Curator or Expert Witness evidence. The Judge disposition
remains `defer` until a separately controlled Windows reproduction and independent Curator
execution exist; Phase 11 is not authorized.
