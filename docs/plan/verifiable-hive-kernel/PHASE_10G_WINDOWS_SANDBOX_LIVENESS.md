# Verifiable Hive Kernel: Phase 10.G Windows sandbox liveness repair

## Purpose and boundary

P10.G is a local Windows repair required after Phase 10's complete local gate reproduced
an early-parent-exit/background-child sandbox failure. It repairs process-tree liveness
only. It adds no provider, API, credential, network, remote Git, remote CI, kernel event,
schema, adapter, migration, challenger, learning, promotion, or historical-receipt path.

It does not close the Phase 10 independent-court obligation or claim hard sandbox
isolation. `B-OPS-06` remains open.

## Local hypothesis and discriminating check

The hypothesis is that a Windows child can outlive an early-exiting parent before a
Toolhelp snapshot observes the child. Creating a Job Object before `Popen`, assigning a
suspended root before resuming it, and failing closed when that liveness boundary is
unavailable prevent a child from escaping before job membership exists.

The discriminating check is the existing
`test_timeout_covers_early_parent_exit_and_background_child`: it requires a
`SandboxTimeout`, a timeout receipt, no surviving child marker, and successful temporary
workspace cleanup.

## Implementation

1. Create a Windows Job Object with `KILL_ON_JOB_CLOSE` before `Popen`; deny the command
  before spawn when it cannot be created.
2. Start the root suspended, assign it to the job, then resume it. Assignment or resume
  failure terminates the suspended root and is a receipted spawn denial.
3. After the root process exits, use the job's active-process count to determine tree
  liveness. A query failure is liveness-unknown until timeout teardown closes the job.
4. Close the job on successful completion after all assigned processes have exited.

## Acceptance criteria

- The early-parent-exit/background-child regression raises `SandboxTimeout`, emits a
  timeout receipt, leaves no marker, and does not lock temporary workspace cleanup.
- Existing timeout-tree, stale-PID, and short-lived Windows command regressions retain
  their prior behavior.
- Job creation or assignment failure denies before the root can run.
- The full sandbox suite passes locally.
- The required complete local gate is run and recorded honestly. Its failure cannot be
  suppressed, skipped, normalized, or treated as a Phase 10 court disposition.

## Local verification receipt

On 2026-08-08 with the local Python 3.14 virtual environment:

- The reproduced single regression passed in 1.220 seconds.
- `python -m unittest tests.test_sandbox -v` passed 23 tests with one expected
  POSIX-only skip in 3.585 seconds.
- With `TEMP` and `TMP` set to `C:\t`, `python -m unittest discover -s tests -v` ran 524
  tests in 926.435 seconds with five expected skips and one failure. The prior sandbox
  liveness test passed. The remaining failure was the unrelated long-path receipt test:
  its fixture root measured 259 characters, below its explicit greater-than-260 assertion.

This is local Builder evidence. Phase 10's independent court remains open, and this result
does not prove hard isolation, a clean repository gate, or any external capability.

### Correction ledger: Builder recheck

The earlier short-root gate result exposed a fixture defect rather than a receipt-validator
failure: `test_long_windows_path_receipt_validates` constructed a 259-character root while
asserting a length greater than 260. The synthetic final path segment was lengthened without
changing validator behavior. On the same local Python 3.14 virtual environment, with `TEMP`
and `TMP` set to `C:\t`, the Builder reran
`python -m unittest discover -s tests -v`: 524 tests passed in 847.304 seconds with five
expected skips. The focused receipt suite passed 9 tests with two expected Windows
symlink-privilege skips; the sandbox suite passed 22 tests with one expected POSIX-only skip;
and the Phase 10 closeout and compatibility suites passed 7 tests.

This recheck removes the prior Builder-local full-gate failure only. The repository-gate
obligation remains open pending separate Cross-Examiner, Expert Witness, Curator, and Judge
evidence, and the result remains neither a hard-isolation claim nor an independent court
disposition.

### Correction ledger: liveness boundary adaptation

Cross-examination refuted the prior Toolhelp fallback claim: a child can escape after an
early parent exit before a snapshot observes it. The runner now creates the Job Object before
spawn, assigns a suspended root before resume, denies when the Job Object is unavailable, and
treats an active-process query failure as liveness-unknown until timeout teardown. The focused
sandbox suite passed 24 tests with one expected POSIX-only skip, including forced assignment
failure and unavailable-Job denial. With `TEMP` and `TMP` set to `C:\t`, the final Builder run
of `python -m unittest discover -s tests -v` passed 526 tests in 1043.431 seconds with five
expected skips.

The Judge disposition is `defer`, not adoption: separate Windows-environment and Curator
reproductions remain open. Phase 11 is not authorized.

## Rollback and deferred work

Rollback removes the Job Object attachment and restores the earlier Toolhelp-only path;
it does not alter receipts, event streams, kernel state, or legacy data. A replacement
with a Job Object used for resource or isolation policy requires a separate architecture
decision and adversarial cross-platform evidence.
