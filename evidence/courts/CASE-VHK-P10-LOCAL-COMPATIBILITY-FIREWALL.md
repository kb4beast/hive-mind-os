# CASE-VHK-P10-LOCAL-COMPATIBILITY-FIREWALL

## Scope and provenance

- **Date:** 2026-08-08
- **Decision requested:** adopt, adapt, defer, reject, or quarantine the Phase 10 local
  compatibility firewall described by ADR-054.
- **Sources:** ADR-052, ADR-053, `PHASE_9_LOCAL_TECHNICAL_CLOSEOUT.md`, and
  `PHASE_10_LOCAL_COMPATIBILITY_FIREWALL.md`.
- **Boundary:** new kernel missions and synthetic local fixtures only. No provider, API,
  network, remote Git, remote CI, credential, external process, legacy migration, or
  historical receipt mutation is authorized.

## Atomic claims

1. A `kernel closeout` inspection can be loaded only from its own CLI execution path.
2. Read-only closeout inspection preserves the event spine, replayed projection, and
   SQLite database bytes for Phase 2-8 fixture streams.
3. Historical receipt fixtures remain opaque and byte-identical for successful,
   blocked, malformed-input, and missing-state closeout outcomes.
4. This phase does not grant authority for a challenger, learning/promotion, adapter,
   migration, provider, Git, network, or process capability.

## Positions and independent work

| Participant    | Position or obligation                                                                                           | State                                                                         |
| -------------- | ---------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Advocate       | Add a narrow compatibility proof before expanding the kernel.                                                    | Recorded; Builder implementation evidence below.                              |
| Cross-Examiner | Attempt to cause import leakage, event/projection drift, database mutation, or historical-receipt byte drift.    | Static refutation recorded; repaired candidate remains externally unverified. |
| Expert Witness | Reproduce the fixture matrix on the selected local interpreter and inspect the import boundary.                  | Human-run receipt recorded; control and transcript evidence pending.          |
| Curator        | Reproduce focused and full local checks from a separate identity and reject unsupported compatibility claims.    | Completed; receipt below.                                                     |
| Judge          | Issue an `adopt`, `adapt`, `defer`, `reject`, or `quarantine` disposition after the independent evidence exists. | Deferred; no adoption or Phase 11 authority.                                  |

## Acceptance and rollback

The Builder evidence must bind the exact base/candidate, focused test output, full-gate
output, fixture event heads, projection digests, database digests, receipt manifests,
known failures, and a statement that no external authority or legacy mutation occurred.

## Local builder evidence

On 2026-08-08, the local Phase 9-10 focused suite passed 7 tests and the complete
kernel test family passed 68 tests in 3.842 seconds. The compatibility fixtures prove
that Phase 2-8 closeout inspection preserves event heads, replayed projections, and
database bytes; the receipt fixture tree remains byte-identical for successful,
partial, blocked, malformed-input, and missing-state outcomes.

The complete repository gate did not pass: 524 tests ran in 990.353 seconds with 5
skips, 1 failure, and 2 errors. A PIT path-length error passes under the local short
temporary root `C:\t`; the remaining sandbox timeout/file-lock failure is outside the
Phase 10 surface. This is Builder-local evidence only, not Curator or Judge approval.

### Builder correction ledger

The remaining short-root failure was traced to the synthetic long-path receipt fixture: its
constructed root was 259 characters although the test required a value greater than 260. Its
final synthetic segment was lengthened, with no production receipt or kernel behavior changed.
On 2026-08-08, the Builder reran `python -m unittest discover -s tests -v` on the local Python
3.14 virtual environment with `TEMP` and `TMP` set to `C:\t`; all 524 tests passed in 847.304
seconds with five expected skips. The Phase 10 closeout/compatibility suite passed 7 tests, the
sandbox suite passed 22 tests with one expected POSIX-only skip, and the receipt-validator
class passed 9 tests with two expected Windows symlink-privilege skips.

This corrects Builder-local repository-gate evidence only. At the time of this Builder
recheck, Cross-Examiner, Expert Witness, Curator, and Judge obligations remained pending;
the later independent Curator reproduction is recorded below. The passing Builder run is
neither an independent disposition nor authorization to start Phase 11.

### Cross-examination and Judge disposition

Cross-examination refuted the prior candidate's eager transitive closeout import, omitted
Phase 1 replay, and parser-only route check. The repaired compatibility suite passed its
three cases, and the focused closeout/compatibility suite passed 7 tests. The final Builder
short-root repository gate passed 526 tests in 1043.431 seconds with five expected skips.

The separate Judge identity issued `defer`: it did not execute tests, and neither separately
controlled Windows evidence nor independent Curator execution was available in that session.
The Expert Witness obligation remains open; the later independent Curator reproduction is
recorded below. Phase 11 is not authorized.

### Court resumption check

On 2026-08-08, the acting Builder reran the focused local compatibility, closeout, and
Windows sandbox checks with `TEMP` and `TMP` set to `C:\t` on the Python 3.14 virtual
environment. `tests.test_brain_kernel_compatibility`, `tests.test_brain_kernel_closeout`,
and `tests.test_sandbox` passed 32 tests in 5.158 seconds with one expected POSIX-only
skip. This is a same-identity local freshness check, not Expert Witness or Curator
evidence; it neither replaces the separately controlled Windows reproduction nor changes
the Judge's `defer` disposition. Phase 11 remains unauthorized.

### Independent Curator reproduction

On 2026-08-08, the Curator independently reran the focused local compatibility,
closeout, and Windows sandbox checks with `TEMP` and `TMP` set to `C:\t` on the Python
3.14 virtual environment. `tests.test_brain_kernel_compatibility`,
`tests.test_brain_kernel_closeout`, and `tests.test_sandbox` passed 32 tests in 5.669
seconds with one expected POSIX-only skip. The required local CI command,
`python -m unittest discover -s tests -v`, then passed 526 tests in 978.893 seconds with
five expected skips.

This is independent local Curator evidence for the checked working tree only. It does not
provide a separately controlled Windows reproduction, authenticate an external identity,
or promote the phase. The Judge's `defer` disposition remains in force, and Phase 11
remains unauthorized.

### Human-run Windows reproduction receipt

On 2026-08-08, a human-run Windows reproduction recorded
`C:\Phase10Full\reproduction-receipt.json`. It binds the frozen candidate base
`7c027df5e553cad086dbf432720b71fb28c740b2`, packet
`sha256:0d7fcc0c1fd0a7050d135497b589e1f435bf23b18de6e90d03bc8c6b4dacbf01`,
25 overlay files, and Python 3.14.4. It reports focused and full test exit codes of zero
with result `passed`.

The receipt does not attest a separately controlled Windows environment or an authenticated
witness identity. Its earlier runner version also did not retain the full test-count and
expected-skip summary in `C:\Phase10Full\logs\full-tests.log`. It is therefore a retained
witness exhibit, not completion of the Expert Witness obligation or a Judge disposition.

Rollback removes the additive compatibility route and tests while retaining append-only
kernel events, local bundles, fixtures, legacy state, and all historical receipt bytes.
No court participant may treat local tests as an independent promotion or customer
outcome claim.
