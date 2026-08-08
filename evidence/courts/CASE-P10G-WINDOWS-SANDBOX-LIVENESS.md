# CASE-P10G-WINDOWS-SANDBOX-LIVENESS

## Scope and provenance

- **Date:** 2026-08-08
- **Decision requested:** `adapt`, `defer`, `reject`, or `quarantine` the local P10.G
  Windows process-liveness repair.
- **Sources:** `ADR-007-PROCESS-SANDBOX-GATEWAY.md`,
  `ADR-008-WINDOWS-PROCESS-TREE-LIVENESS.md`, and
  `PHASE_10G_WINDOWS_SANDBOX_LIVENESS.md`.
- **Boundary:** local Windows process handling only. No provider, API, credential,
  network, remote Git, remote CI, legacy mutation, kernel capability, or hard-isolation
  claim is authorized.

## Atomic claims

1. An assigned Windows Job Object observes a background child that can be missed after
   its parent exits.
2. Closing that Job Object on timeout terminates assigned descendants and permits local
   temporary-workspace cleanup.
3. Job Object tracking is liveness/teardown plumbing, not a hard-isolation control.

## Local Builder evidence

The prior failing background-child test passed after the candidate change. The full sandbox
suite passed 23 tests with one expected POSIX-only skip. The complete local gate was run
with a short temporary root; it did not pass because an unrelated long-path fixture was
one character below its explicit precondition. The former sandbox failure passed.

### Builder correction ledger

The long-path fixture was repaired by lengthening only its synthetic final directory segment;
the prior failure occurred at its 259-character precondition, before receipt validation. On
2026-08-08, the Builder reran the required command with `TEMP` and `TMP` set to `C:\t` on the
local Python 3.14 virtual environment: `python -m unittest discover -s tests -v` passed 524
tests in 847.304 seconds with five expected skips. The sandbox suite passed 22 tests with one
expected POSIX-only skip, including the early-parent-exit/background-child regression.

This is correction of Builder-local evidence, not an independent reproduction or a court
disposition. The repository-gate obligation remains open pending the participants below.

## Independent obligations and disposition

| Participant    | Obligation                                                                              | State                                                                |
| -------------- | --------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| Advocate       | Bound local repair claim and rollback.                                                  | Recorded by this case.                                               |
| Cross-Examiner | Probe pre-assignment, breakaway, job-assignment failure, PID reuse, and teardown races. | Static refutation recorded; external reproduction remains pending.   |
| Expert Witness | Reproduce on a separately controlled Windows environment.                               | Human-run receipt recorded; control and transcript evidence pending. |
| Curator        | Reproduce focused and complete local checks; reject unsupported isolation claims.       | Completed; receipt below.                                            |
| Judge          | Issue an independent disposition after the above evidence exists.                       | Deferred; no adoption or Phase 11 authority.                         |

This case does not supersede or complete the pending Phase 10 courtroom case. No local test
result is an independent Curator or Judge approval.

### Cross-examination and Judge disposition

Cross-examination found that Toolhelp fallback could miss a child after early parent exit.
The Builder adapted the candidate to create the Job Object before spawn, assign the suspended
root before resume, deny unavailable/failed setup, and fail closed on active-process query
failure. The final Builder-local sandbox suite ran 25 tests with one expected skip and the
short-root full gate passed 526 tests in 1043.431 seconds with five expected skips.

The separate Judge identity issued `defer`: it did not execute commands and no separately
controlled Windows environment or independent Curator execution existed in that session.
The Expert Witness obligation remains open; the later independent Curator reproduction is
recorded below. Phase 11 is not authorized.

### Independent Curator reproduction

On 2026-08-08, the Curator independently reran the local compatibility, closeout, and
Windows sandbox checks with `TEMP` and `TMP` set to `C:\t` on the Python 3.14 virtual
environment. `tests.test_brain_kernel_compatibility`,
`tests.test_brain_kernel_closeout`, and `tests.test_sandbox` passed 32 tests in 5.669
seconds with one expected POSIX-only skip. The required local CI command,
`python -m unittest discover -s tests -v`, then passed 526 tests in 978.893 seconds with
five expected skips.

This is independent local Curator evidence for the checked working tree only. It does not
provide the required separately controlled Windows-environment reproduction or a Judge
disposition. The Judge's `defer` remains in force and Phase 11 remains unauthorized.

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
