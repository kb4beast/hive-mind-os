# Windows collector diagnostic crash repair

Builder: `/root/generic_guide_builder`. Source before repair:
`3bfd4edd504a1c1dc6b4448941dc38f4fdfcdbba`, PR179. Root owns final commit,
independent review and CI delivery. Builder source ownership returned after the
two-file batch; root separately authored the architecture decision record.

## Observed failure versus inferred cause

The full failed job log is retained at
`C:\h\node-completeness-audit\delivery-closeout\final-ci-logs\34776733388-103776098899.log`.
Windows Python 3.12 ran 1,772 tests in 2,454.485 seconds with one failure and one skip.
The failing collector integration test included a nested frozen V4 DAG executor
module. Its stderr stopped during a `Timeout (0:00:15)!` diagnostic, midway
through a Python frame. The outer exception was generic validation failure,
not the collector's typed module or overall deadline exception.

The 15-second value is `faulthandler.dump_traceback_later(15, repeat=True)`, a
diagnostic timer with `exit=False` by default. Actual deadlines remain 300 seconds
per module and 900 seconds overall. No evidence supports increasing them. The
CI log omits the nested actual/effective exit code and timeout metadata, so its
exact numeric process outcome cannot be reconstructed from that transcript.

The builder reproduced the frozen V4 module from exact commit
`1038b5a7d2eb49904c59957ad3e989af8bb2fcc5` using a Git archive outside the
repository and the same native Python 3.12.10 interpreter version. The unchanged
bootstrap under the actual bounded PowerShell runner passed all 23 tests in
2.904s; actual/effective exit 0, timed_out=false, total process 3.485 seconds. It finished
before the 15-second diagnostic timer fired.

The external-only stress comparison changed only the diagnostic sampling
interval to 0.01s and 0.001s. Both runs crashed with exit 3221225477
(`0xC0000005`, Windows access violation), after six and five diagnostic dumps,
with truncated frame output and no terminal marker. No production timeout was
modified. This reproduces a diagnostic-triggered native failure on the same
Python version/workload, and supports the original failure mechanism; it does
not establish the missing numeric exit code of the original CI process.

## Corrected behavior

The generated bootstrap now uses a Python daemon thread that waits 15 seconds
and calls `faulthandler.dump_traceback` while owning the GIL. The raw C watchdog
is removed. The thread is stopped and joined before collection and the terminal
receipt. Diagnostic-thread exceptions are captured and raised before a success
marker rather than silently discarded. Diagnostic output explicitly says it is
not a process deadline.

A native operation that holds the GIL can prevent this cooperative diagnostic
thread from producing a stack snapshot. The independent parent process still
enforces its finite deadline, kills the owned process tree and rejects the run
with partial streams and process metadata. No complete-stack claim is made for
that failure mode. The actual process runner is byte-unchanged.

The collector integration test's failure message now retains the generated
`evidence.json` alongside its focused transcript before temporary cleanup.
This preserves actual/effective exit codes, timeout/termination fields and
module receipt outcomes for any later CI failure.

## Reproduction and executable acceptance

- `REPRODUCTION.json`, `MODULE-RESULT.json` and `module.*.txt`: unchanged
  frozen-module baseline through the real PowerShell runner.
- `DIAGNOSTIC-STRESS.json`, `accelerated-*`: two old-watchdog native crashes.
- `THREADED-DIAGNOSTIC-RESULT.json`, `threaded-*`: equivalent external candidate
  runs pass all 23 tests, exit 0 and terminal markers, while producing 201 and 200
  actual snapshots at the same accelerated intervals.
- The new test `test_generated_bootstrap_diagnostics_preserve_module_completion`
  extracts the actual generated bootstrap, substitutes only fixture bindings,
  selected module arguments and an accelerated interval, then runs the real DAG
  module under the bounded PowerShell runner. It requires at least one snapshot,
  normal child completion and a valid full terminal receipt.
- `test_generated_bootstrap_rejects_diagnostic_thread_failure` injects a dump
  failure into that extracted bootstrap and requires nonzero child exit,
  timed_out=false, explicit diagnostic failure and no success marker.
- `FOCUSED-VALIDATION.json` and `focused.*.txt` retain the actual six-test focused
  result: all six passed in 16.682 seconds, with no skips. They cover both new
  tests and existing overall/module timeout, partial-stream, adverse terminal
  outcome, and owned-process-tree termination requirements.
  All 183 original assertion-call ASTs are preserved against the pre-repair pin;
  13 additional assertions cover the new diagnostic behavior.
  No failed checks, skips or timeouts are converted to success.

The source-derived diagnosis is additionally examined independently by
`/root/continuity_repair_builder`. Root retained exact CPython 3.12.10 source
bytes and its PSF license under
`C:\h\node-completeness-audit\windows-collector-sources\SOURCE-MANIFEST.json`.
No external implementation code was copied into the repair. An initial web
search also surfaced a free-threaded Python3.14 issue; it was not treated as
evidence for this normal Python 3.12 build.

## Architecture, compatibility and rollback

The detailed architecture decision is root's
`docs/architecture/ADR-COLLECTOR-COOPERATIVE-DIAGNOSTICS.md`.
This changes diagnostic collection and failure-evidence visibility only.
300-second module / 900-second overall limits, cancellation/termination,
terminal markers, exact test counts, clean outcomes, all authority/evidence
checks and activation=false remain enforced. There is no schema or historical
receipt migration. Successful receipt fields remain compatible; bootstrap
bytes receive their normal newly calculated digest.

Rollback is a revert of the diagnostic implementation/tests/ADR while retaining
all original CI failure, stress failures and independent review evidence. That
would restore the demonstrated unsafe watchdog behavior. No production
activation, release/promotion, credential mutation, Git push or protected merge
is performed by this builder.
