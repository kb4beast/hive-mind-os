# ADR-068: Bounded doctor execution and exact-checkout binding

## Status

Implemented candidate. It is not promotable until an independent Curator and a distinct
Judge reproduce the focused evidence and the repository CI gate under the released
repository-wide validation lease.

## Qualification payload topology

Qualification has two deliberately different identities. **Payload A** is the immutable
executable/normative payload: `.autopilot/README.md`,
`.autopilot/bin/autopilot.py`, `.autopilot/bin/controller.py`,
`.autopilot/tests/test_doctor_boundary.py`, this ADR, and `ADR_INDEX.md`. After its
ordered hash record is published, no byte in Payload A may change during its focused
tests, full doctor, or repository CI. A qualification result applies only to that exact
Payload A identity; it never covers a later edit, including a documentation edit.

**Envelope B** is the explicitly excluded append-only receipt/court envelope:
`evidence/autopilot/DOCTOR-CONTROL-ROOM-REPAIR-2026-08-23.md` and
`evidence/courts/CASE-ADR-068-BOUNDED-DOCTOR-REPAIR.json`. It records later execution
results and binds each result to Payload A without mutating A. Its reproducible binding
record is UTF-8 lines in the declared path order, each exactly
`<lowercase SHA-256><two ASCII spaces><forward-slash path><LF>`; the record digest is
SHA-256 of those bytes. Envelope B is not itself frozen and cannot expand the scope of
a Payload A qualification. A final Judge must name the tested Payload A digest and say
which post-run Envelope-B entries are evidence-only appends; no full-CI claim may cover
those later B bytes.

## Context

On Python 3.14, the ordinary Autopilot doctor started its controller-test subprocess
with a fixed 180-second timeout but let `subprocess.TimeoutExpired` escape. The JSON
contract was therefore replaced by a traceback. The pre-repair execution also inherited
the machine-wide editable `hive_mind_os` binding, which can point at a different linked
checkout. A reduced `--skip-controller-tests` observation was useful for identifying
that environmental fault but was not full-doctor evidence.

The 2026-08-13 post-merge branch-resolution failure is retained adverse history. A
present-day successful target resolution can be prospective evidence only; it cannot
rewrite that failure or certify the historical merge retroactively.

## Decision

- Doctor runs controller tests with a fixed 600-second timeout. The maximum observed
  bounded controller run on this Windows/Python-3.14 worktree is 334.026 seconds under
  concurrent validation load. Rounding 1.75 times that observed worst case (584.546s)
  to the next minute leaves 265.974 seconds (79.63%) headroom, or a 1.796x bound; it is
  a finite, load-tolerant limit and does not remove or weaken controller tests.
- The child uses the invoking `sys.executable`, `cwd=<repo-root>`, isolated mode
  (`-I`), and an explicit first `sys.path` entry for `<repo-root>/src`. It ignores
  inherited `PYTHONPATH`, `PYTHONHOME`, and user-site state. Doctor never mutates the
  machine-wide editable install.
- Runtime coordination reports two distinct facts. The isolated child must resolve the
  exact source origin to gate the run; the ambient invoking-process import must also
  resolve that same origin or emit an `error`-severity ambient-binding mismatch. Neither
  a forced child binding nor a foreign editable install can satisfy the other claim.
- Controller-test stdout and stderr are drained by daemon readers using strict
  incremental UTF-8 decoding. Doctor retains no child text, byte count, digest, tail,
  truncation flag, or other value-derived telemetry. The only safe stream evidence is
  whether each stream was observed, UTF-8-valid, or had a reader error. This preserves
  typed invalid-output detection without creating an offline guessing oracle for a
  credential emitted by arbitrary tests.
- On Windows, doctor resolves and types every required Job and resume API, including
  `NtResumeProcess` and correctly typed `CloseHandle`, before creating a Job handle.
  Lookup/compatibility failure returns typed `containment_unavailable` and launches no
  child. Once a Job handle exists, setup transfers it only after
  `KILL_ON_JOB_CLOSE` configuration succeeds; failed setup closes the untransferred
  handle. Doctor then launches the child with `CREATE_SUSPENDED`, assigns its owned
  process handle to that Job, and resumes it. Assignment, resume, or close failure is a
  typed fail-closed `controller-tests` result; no PID-addressed `taskkill` operation is
  used. On POSIX, the child starts in a new session and timeout cleanup kills its
  process group.
- Timeout, containment setup/termination failure, spawn failure, killed child, nonzero
  exit, reader failure, incomplete output stream, and undecodable output each produce a
  typed failed `controller-tests` check. `doctor --json` has a final fail-closed JSON
  boundary.
- `--skip-controller-tests` produces `READY_REDUCED`, `validation_scope: reduced`, and
  an explicit skipped record. It is not full-doctor evidence and cannot satisfy sealed
  recovery requirements.

The fixed limit is selected against two measurements: the 180-second timeout reproduced
on the prior implementation and the 334.026-second maximum exact-worktree controller
duration in the retained intermediate receipts. The 600-second limit is the next
one-minute bound above 1.75 times that observed worst case. A `_MonotonicDeadline` supplies the remaining
test-body budget to `wait`; after it expires, only the separately bounded 10-second
termination wait and one shared 10-second output-reader grace remain. Thus the
**controller-test phase after successful launch** is bounded to 620 seconds plus
ordinary local call overhead. It is not a claimed bound for
the entire doctor command: runtime-binding, configuration, and Git checks have their
own finite/error paths and are not charged to this test budget. Every prospective
full-doctor receipt records its duration. A result at or above 450 seconds reaches 75%
of the hard ceiling and requires a new performance/risk review; it must never silently
increase this limit. At 600 seconds the controller test fails closed.

The Windows suspension/resume step depends on the local OS `NtResumeProcess` interface
solely to eliminate pre-Job user-code execution; this is a compatibility risk because
the interface is not a documented `CreateProcessW`/`ResumeThread` wrapper. Its symbol
and every other required API are now resolved and typed before Job-handle creation; a
missing/ill-typed API is `containment_unavailable`, closes any untransferred handle when
applicable, and launches no child. The focused suite exercises missing `NtResumeProcess`
and `CreateJobObjectW`, plus an untransferred-handle configuration failure, and requires
typed no-launch results. It separately exercises a forced post-launch resume failure as
`containment_setup_failed`. POSIX
process groups cannot contain a malicious descendant that calls `setsid`; doctor returns
a typed timeout plus `output_stream_incomplete` within the phase budget if it retains a
pipe, but does not claim that such an escaped process was killed. A normal leader exit
with a surviving POSIX pipe holder likewise fails rather than reporting `READY`. That
residual is documented and tested as a non-Windows adverse boundary.

## Threats and failure modes

- **Wrong checkout or interpreter:** denied by isolated invocation, explicit source
  insertion, exact-origin/interpreter evidence, and separately failing ambient evidence.
- **Hung, killed, orphaned, or prelaunch-containment faults:** Windows resolves and
  types required APIs before any Job handle/child, closes an untransferred handle on
  setup failure, and owns a kill-on-close Job before the suspended child can execute;
  close failure is typed. POSIX kills only the original process group and explicitly
  does not claim containment after `setsid`.
- **Output, inherited handles, and secret telemetry:** daemon readers retain no output
  bytes, text, length, or digest; they use one bounded grace and are never closed from
  another thread. A held pipe therefore becomes `output_stream_incomplete`, not a
  blocking doctor or a secret verifier.
- **JSON consumer confusion:** every expected doctor execution failure is a valid,
  failed JSON document with no traceback or child output on stderr.
- **Historical evidence laundering:** the older deleted-branch incident remains in its
  existing tests and court history; prospective branch-resolution tests add no
  retroactive verdict.

## Migration and compatibility

Doctor result JSON adds `validation_scope`, `controller_tests_run`, typed evidence, and
the `READY_REDUCED` state for an intentionally reduced invocation. No persistent state
schema, plan, generic overlay, target branch, editable install, protected branch, or
external service is changed. Existing full successful doctor results remain `READY`.

## Rollback

Revert only the bounded execution implementation and this ADR in a reviewed successor
while retaining the pre-repair failure evidence, court disposition, focused tests, and
all current receipts. Do not delete or rewrite the 2026-08-13 adverse branch history.

## Acceptance evidence

- `.autopilot/tests/test_doctor_boundary.py` declares 25 focused cases, including one
  POSIX-only residual case skipped on Windows: 
  `DoctorSubprocessBoundaryTests.test_posix_detached_descendant_is_typed_not_ready`,
  with the exact reason `POSIX setsid residual is not applicable on Windows`. The
  2026-08-23 independent receipt identifies the host as x64
  `Windows-11-10.0.26200-SP0`, which cannot exercise that POSIX `setsid` capability.
  That skip does not waive Windows containment: the same run exercises the Job-backed
  timeout descendant and inherited-handle paths, and a forced Job-resume failure must
  yield `containment_setup_failed`. All earlier focused receipts predate the replacement
  Payload-A lock and are retained only as adverse/intermediate history. A newly run,
  bound receipt must qualify the replacement locked Payload A; it remains focused
  evidence only.
  The cases cover
  timeout and Windows Job descendant cleanup while a separate unrelated process remains
  alive, prelaunch missing-API/no-child behavior, untransferred-Job-handle cleanup,
  direct-parent exit with inherited handles, containment termination failure,
  monotonic remaining-budget accounting, spawn failure, killed/nonzero children,
  typed invalid output with no fingerprint metadata, generic reader-failure handling
  and CLI JSON, post-launch reader-start cleanup, deterministic exact
  isolated/ambient binding, deterministic remote/local target selection, flexible clone
  integration observation, and prospective missing-target JSON failure.
- The ordinary full doctor must pass with controller tests enabled in this exact
  worktree. Its receipt records duration; a duration of 450 seconds or more invokes
  the bounded-time review above, while 600 seconds remains the fail-closed ceiling.
- The repository CI command remains `python -m unittest discover -s tests -v`, run only
  after the repository-wide validation lease is explicitly released.
