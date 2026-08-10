# Verifiable Hive Kernel: Phase 10 local compatibility firewall

## Purpose and boundary

Phase 10 is the next local-only kernel phase after the Phase 9 technical-closeout
delivery. It makes the Phase 9 compatibility and historical-receipt preservation
boundary executable before any local challenger, learning, environment-contamination,
adapter, or migration work is considered.

This phase adds no provider, API, network, remote Git, remote CI, credential, external
process, effect adapter, prompt champion, experiment runner, legacy migration, or
legacy dual writer. It makes no customer-outcome, external-authenticity, courtroom
disposition, or learning-promotion claim.

## Local hypothesis and discriminating check

The local hypothesis is that the `kernel closeout` path can remain entirely additive:
loading a legacy CLI route or replaying a prior kernel event stream will neither load
the closeout service nor mutate a legacy receipt, event spine, projection, or store.

The cheap discriminating check is a fixture-backed before/after comparison. It records
the event head, replayed projection digest, state-file digest, and a recursive
byte-and-path manifest of historical-receipt fixtures; it then exercises one read-only
inspection outcome and requires every value to be identical. An AST/import-boundary
test separately rejects a module-level closeout import from `hive_mind_os.cli`.

## Entry criteria

- Phase 9 remains a local, read-only technical-closeout delivery; its focused tests
  pass on the selected local interpreter.
- The Phase 10 court case exists before implementation with separate Advocate,
  Cross-Examiner, Curator, and Judge identities. It records ADR-053 and ADR-054 as
  source references and marks all independent dispositions honestly.
- Fixtures are synthetic or already-checked-in local test material. No real historical
  receipt, repository state root, or external artifact is copied into the test corpus.

## Work slices

### P10.1 - CLI import containment

Move the closeout-service import from the module scope of
`src/hive_mind_os/cli.py` into the private `kernel closeout` execution path. Preserve
parser text, command arguments, return codes, JSON shape, and all existing legacy
command behavior. The import itself must have no side effect other than making the
closeout symbols available to that command.

Add a focused AST-level regression test that rejects a module-level
`brain_kernel.closeout` import. Keep the assertion narrow: the existing CLI has other
legacy and kernel imports, so this phase must not claim a whole-package provider or
legacy-import ban.

### P10.2 - Golden replay baseline

Create deterministic fixtures for valid Phase 1 through Phase 8 kernel event streams.
For each fixture, record and assert the ordered event digests, final event head,
replayed projection digest, and read-only state-file digest. The fixture builder may
construct a new temporary kernel database, but the inspection target must already
exist before the command is invoked.

Run `kernel closeout` against each fixture in a read-only mode. A missing closeout
obligation may result in the documented blocked or partial outcome; it must not append
an event, update a snapshot, create a database, or change a pre-existing digest.

### P10.3 - Historical receipt byte firewall

Add a test-only recursive byte manifest helper that records each relative path and its
SHA-256 digest under a representative historical-receipt fixture root. Use it before
and after every closeout outcome: technically verified, partial, blocked due to bundle
tampering, malformed bundle reference, and absent database.

The test data is opaque to the closeout service. The compatibility test may calculate
the baseline manifest, but the implementation may not pass receipt bytes to the kernel,
copy them into a bundle, or turn them into an effect receipt. A changed path, added
file, removed file, or changed byte digest fails the test closed.

### P10.4 - Legacy route and receipt regression

Exercise representative legacy parser and read-only store routes before and after the
closeout fixture sequence. Assert their command results and fixture-tree manifests are
unchanged. Verify that legacy stores, ledgers, receipt validators, prompt registry,
experiment runner, model backend/provider, Git/GitHub adapters, and network libraries
are not imported by the new compatibility harness or the lazy closeout import path.

Keep this proof scoped to the newly added surface. Existing runtime modules may have
their own historical dependencies; Phase 10 neither refactors nor certifies them.

## Acceptance criteria

- The only CLI import of `brain_kernel.closeout` is scoped to `kernel closeout`
  execution, and all existing parser and CLI regression tests retain their behavior.
- For every Phase 1-8 golden stream, closeout inspection leaves the event sequence,
  event head, replayed projection digest, and state-file digest byte-identical.
- Every tested closeout outcome leaves the historical-receipt fixture-tree manifest
  byte-identical. Historical receipts are never passed as bundles or new effect
  evidence.
- A missing state database and malformed closeout input fail without creating a kernel
  database, changing a legacy fixture, or adding a kernel event.
- The new compatibility module and closeout route do not import model-provider,
  model-backend, prompt-registry, experiment-runner, ledger, Git/GitHub adapter, or
  network modules.
- Existing Phase 1-9 focused tests pass, followed by the complete local CI gate:
  `python -m unittest discover -s tests -v`.

## Evidence interpretation

Running the local Windows reproduction script is valid deterministic technical evidence;
it is not cheating, a court disposition, or Phase 11 authority. The script records its
control declaration and always marks the receipt as non-promoting. A separately controlled
environment, an attested witness identity, the complete retained test transcript, and a
distinct Judge disposition are separate requirements before any promotion claim.

## Test inventory

Add `tests/test_brain_kernel_compatibility.py` with cases for import containment,
golden Phase 1-8 replay, each closeout disposition, missing state, malformed bundle
references, receipt-tree byte manifests, and representative legacy parser/store
regressions. Retain and extend `tests/test_brain_kernel_closeout.py` only for
closeout-specific behavior. Do not weaken an existing test or replace immutable bytes
with normalized text comparisons.

The focused development command is:

```powershell
C:/Python314/python.exe -m unittest tests.test_brain_kernel_compatibility tests.test_brain_kernel_closeout -v
```

Before any passing claim, run the required full local CI gate from `AGENTS.md` and
record the exact command, interpreter, test count, expected skips, failures, and
environment limitations. A focused pass is not evidence that the full gate passed.

## Local implementation receipt

Implemented on 2026-08-08 without providers, APIs, API keys, network access, remote
Git actions, or legacy writes. The focused command for the Phase 9-10 closeout and
compatibility suites passed 7 tests. The full local kernel family,
`python -m unittest discover -s tests -p 'test_brain_kernel*.py' -v`, passed 68 tests
in 3.842 seconds when `TEMP` and `TMP` used the local short root `C:\t`.

The required full gate ran 524 tests in 990.353 seconds with 5 skips, 1 failure, and 2
errors. The known PIT self-history copy failure passes with the short temporary root;
the remaining reproducible sandbox timeout/file-lock failure is outside this phase's
files and remains a blocking repository-gate obligation. No full-gate-passed or
independent-court-complete claim is made.

### Correction ledger: Builder recheck

The prior short-root failure was a synthetic long-path test fixture that measured 259
characters while asserting a length greater than 260; it did not exercise the receipt
validator. The fixture's final synthetic segment was lengthened without changing production
receipt code. On 2026-08-08, using the local Python 3.14 virtual environment with `TEMP` and
`TMP` set to `C:\t`, the Builder reran `python -m unittest discover -s tests -v`: 524 tests
passed in 847.304 seconds with 5 expected skips. The focused Phase 9-10 command passed 7
tests; the receipt-validator class passed 9 tests with 2 expected symlink-privilege skips;
and the sandbox suite passed 22 tests with 1 expected POSIX-only skip.

This supersedes only the prior Builder-local failure observation. The repository-gate
obligation remains open until separate Curator reproduction, and the independent court remains
pending; it is not a court disposition or authorization to begin Phase 11.

### Final Builder recheck and court boundary

Cross-examination found and the Builder repaired the transitive closeout import, missing
Phase 1 replay coverage, and parser-only status-route proof. The compatibility suite now
checks a fresh-process CLI import, Phase 1-8 replay, and executed read-only status behavior.
On 2026-08-08 with `TEMP` and `TMP` set to `C:\t`, the final required command
`python -m unittest discover -s tests -v` passed 526 tests in 1043.431 seconds with 5 expected
skips. This remains Builder-local evidence only. The Judge disposition is `defer` pending a
separately controlled Windows reproduction and independent Curator evidence; Phase 11 is not
authorized.

## Compatibility matrix

| Surface                   | Phase 10 rule                                                            | Proof                                                             |
| ------------------------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------- |
| Legacy CLI                | Existing commands, parser grammar, exit codes, and output stay unchanged | Parser and route regressions; scoped AST import check             |
| Legacy stores and ledgers | No open, write, migration, or dual writer                                | Read-only fixture checks and module-import boundary               |
| Historical receipts       | Opaque, immutable, never copied or reinterpreted                         | Recursive path-and-byte manifest before/after every outcome       |
| Phase 1-8 event streams   | Existing event and projection semantics stay unchanged                   | Golden event-head and projection-digest replay checks             |
| Phase 9 closeout          | Read-only and non-creating                                               | Event/state digest equality and missing-state test                |
| External boundaries       | No provider, API, network, remote Git, or process effect                 | New-module import prohibition and monkeypatched failure sentinels |

## Rollback and deferred work

Rollback removes the lazy closeout entry point and additive compatibility harness while
retaining all append-only kernel events, local verification bundles, golden fixtures,
legacy state, and receipt files. It never deletes a historical receipt or restores a
legacy writer.

Deferred beyond Phase 10 are local challenger registration and evaluation, prompt or
context promotion, environment-contamination execution, general adapter wiring, legacy
migration, real process/network/provider/Git effects, external authenticity, customer
outcome measurement, and independent courtroom promotion. A challenger phase may be
proposed only after this phase's compatibility evidence is reproduced independently.
