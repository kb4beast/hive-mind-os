# Doctor control-room repair evidence — 2026-08-23

## Scope and provenance

- Candidate base: `44224532dc25b94a95c3184054ec81762a258259`.
- Worktree: `C:\Users\beesp\.codex\worktrees\5d72\hive-mind-os`.
- Interpreter: `C:\Python314\python.exe`, Python 3.14.4.
- This is prospective candidate evidence only. It does not alter the retained
  2026-08-13 deleted-branch adverse history or supply a retroactive verdict.

## Receipt topology

This file and `evidence/courts/CASE-ADR-068-BOUNDED-DOCTOR-REPAIR.json` are **Envelope
B**: an excluded append-only evidence/court record. The immutable executable/normative
**Payload A** is defined in ADR-068 and will be bound here by its exact ordered digest
record before any qualifying focused/full-doctor/CI run. No existing receipt below is
qualified for that not-yet-locked A identity. Later receipt appends may record results,
but cannot modify or extend the qualification scope of Payload A.

The earlier Payload-A lock (`a4892c8ad1942b8f530475590dab3e1bb112a6b81d92173cf8289e2123de0b91`
manifest; `f4c4d9d488bb8a69b4ad87c734dcb2af77b4c2dbb99acde9d6a435027810d055`
raw aggregate) is **superseded**. External review found that the old Job factory could
resolve missing `NtResumeProcess` only after a Job handle existed, leaking that handle
and escaping the typed prelaunch containment path. All prior focused/Judge statements
about that identity remain adverse/intermediate history and do not qualify the repair.
A replacement Payload A will be locked only after the corrected ADR/court evidence is
complete and will receive a fresh external review.

## Superseded Payload A lock record

Locked UTC: `2026-08-23T07:46:50.0488410Z`.

Record format: UTF-8 encoding of the following lines in exactly this order; every line
ends with one LF (`0x0A`), has a lowercase SHA-256 digest, exactly two ASCII spaces,
and a forward-slash relative path. There is no additional leading/trailing content. The
record is 627 bytes and its SHA-256 is
`a4892c8ad1942b8f530475590dab3e1bb112a6b81d92173cf8289e2123de0b91`.

```text
afce0adae94847e5911a1e9390df2d2fab89ec662c3bf1e970f68987fdc7b417  .autopilot/README.md
e93a8ff557500456eed27be88a5f1d3c5d8e8306c9379aa2d65503b3aa95b3e9  .autopilot/bin/autopilot.py
4c816585c8f98475ceb6d5d4874d5aed41b6a961deeea711f61589a3779246db  .autopilot/bin/controller.py
8b9d8fea88875e7e6bc1fcb213b90b2774be4b19eed62fab5062d907aaa4af07  .autopilot/tests/test_doctor_boundary.py
8e3804b610c9bcf5da02da8427e7fd60bb96c2672143971c2f0183d5d882e895  docs/architecture/ADR-068-BOUNDED-DOCTOR-EXECUTION-AND-EXACT-CHECKOUT-BINDING.md
bd2a5be0e4fd90b2fc98d154ca176496e21547ec98303e8c2af6052da7f226e4  docs/architecture/ADR_INDEX.md
```

The six files above are the complete Payload A. Envelope-B bytes, including this lock
record, are deliberately excluded. Qualification tests started after this record may
qualify only these exact A bytes; later Envelope-B appends are evidence-only and cannot
be described as full-CI exact-head coverage.

Raw-content aggregate verification at `2026-08-23T07:49:58.9588572Z` reconfirmed that
all six locked file hashes above are unchanged. Its unambiguous byte algorithm is:

```text
aggregate = UTF8("hive-mind-os/payload-a-content/v1") + NUL
for each file in the exact order above:
    aggregate += UTF8(forward-slash path) + NUL
    aggregate += ASCII(decimal raw-file-byte-count) + NUL
    aggregate += raw file bytes + NUL
aggregate_sha256 = SHA256(aggregate)
```

The aggregate is 302364 bytes and its SHA-256 is
`f4c4d9d488bb8a69b4ad87c734dcb2af77b4c2dbb99acde9d6a435027810d055`.
The ordered raw-byte counts are `20212`, `66963`, `168705`, `24899`, `10375`, and
`10902`, respectively. The earlier 627-byte line-record digest remains the compact
file-list identity; this aggregate independently binds the actual file bytes.

## Superseded replacement Payload A R2 lock record

Locked UTC: `2026-08-23T08:00:53.1198443Z`.

This replacement lock uses the same versioned raw-content algorithm and line-record
format as the superseded lock, but only the following six current file bytes qualify.
The exact 627-byte UTF-8/LF line record has SHA-256
`84610cb9deda152c0571589bc316fd2a324df6c69d2865338149c48ae964b2f3`:

```text
afce0adae94847e5911a1e9390df2d2fab89ec662c3bf1e970f68987fdc7b417  .autopilot/README.md
e93a8ff557500456eed27be88a5f1d3c5d8e8306c9379aa2d65503b3aa95b3e9  .autopilot/bin/autopilot.py
08230e8638296d000cb0e25c53b253f2a03dfc94d2a7770ebb471a941329512b  .autopilot/bin/controller.py
ca455bc24c8f0f6d2ef548a4c36fed596d603438c2f1e357f24c12bd61ea6694  .autopilot/tests/test_doctor_boundary.py
73eb89da303c1af3d6aad736a8e6c06f95d9a99b89603088b2b1a69cdd087674  docs/architecture/ADR-068-BOUNDED-DOCTOR-EXECUTION-AND-EXACT-CHECKOUT-BINDING.md
bd2a5be0e4fd90b2fc98d154ca176496e21547ec98303e8c2af6052da7f226e4  docs/architecture/ADR_INDEX.md
```

The same ordered raw-content algorithm yields 307879 bytes and SHA-256
`ac9a94e1dbf7b814a39451b7825125c643969710498f37e0af1fa0a1b14c3e65`.
The ordered raw-byte counts are `20212`, `66963`, `170351`, `27932`, `11211`, and
`10902`. Envelope B remains explicitly excluded; this replacement A must receive fresh
external focused review before any held full-doctor/CI gate may begin.

R2 is **superseded without qualification** because its first identity computation was
followed by an Envelope-B change marker. R3 below is the only identity sent for external
review, even though the final normative bytes recompute to the same two digests.

## Final replacement Payload A R3 lock record

All six included file mtimes preceded this freeze; the latest was ADR-068 at
`2026-08-23T07:59:56.5876355Z`. R3 locked at
`2026-08-23T08:02:23.3791820Z`.

R3 line-record format is UTF-8 ordered lines of lowercase SHA-256, two ASCII spaces,
forward-slash relative path, and one LF—no other bytes. It is 627 bytes with SHA-256
`84610cb9deda152c0571589bc316fd2a324df6c69d2865338149c48ae964b2f3`:

```text
afce0adae94847e5911a1e9390df2d2fab89ec662c3bf1e970f68987fdc7b417  .autopilot/README.md
e93a8ff557500456eed27be88a5f1d3c5d8e8306c9379aa2d65503b3aa95b3e9  .autopilot/bin/autopilot.py
08230e8638296d000cb0e25c53b253f2a03dfc94d2a7770ebb471a941329512b  .autopilot/bin/controller.py
ca455bc24c8f0f6d2ef548a4c36fed596d603438c2f1e357f24c12bd61ea6694  .autopilot/tests/test_doctor_boundary.py
73eb89da303c1af3d6aad736a8e6c06f95d9a99b89603088b2b1a69cdd087674  docs/architecture/ADR-068-BOUNDED-DOCTOR-EXECUTION-AND-EXACT-CHECKOUT-BINDING.md
bd2a5be0e4fd90b2fc98d154ca176496e21547ec98303e8c2af6052da7f226e4  docs/architecture/ADR_INDEX.md
```

The raw-content aggregate is exactly the versioned algorithm declared above: header
`UTF8("hive-mind-os/payload-a-content/v1") + NUL`, then each listed path as UTF-8 +
NUL, ASCII decimal raw byte count + NUL, raw file bytes + NUL. It is 307879 bytes with
SHA-256 `ac9a94e1dbf7b814a39451b7825125c643969710498f37e0af1fa0a1b14c3e65`.
The corresponding byte counts are `20212`, `66963`, `170351`, `27932`, `11211`, and
`10902`. Envelope B is excluded and will next receive only a second post-append
verification plus external-review receipts; no R3 Payload-A byte may change.

Second verification after this Envelope-B append completed at
`2026-08-23T08:03:24.8783489Z`: all six R3 file hashes, the 627-byte line-record digest,
and the 307879-byte raw-content aggregate matched exactly. R3 is now the only payload
identity eligible for external review.

Independent Curator R3 focused receipt:

| Field | Observed value |
| --- | --- |
| Qualified Payload A R3 manifest / raw aggregate | `84610cb9deda152c0571589bc316fd2a324df6c69d2865338149c48ae964b2f3` / `ac9a94e1dbf7b814a39451b7825125c643969710498f37e0af1fa0a1b14c3e65` |
| Command | `python -m unittest discover -s .autopilot/tests -p test_doctor_boundary.py -v` |
| Started UTC | `2026-08-23T08:04:40.9183502Z` |
| Finished UTC | `2026-08-23T08:04:45.7248155Z` |
| Outer measured duration | `4.806s` |
| Test runner result | 25 run: 24 passed; inner runner duration `4.625s` |
| Exit | `0` |
| Exact skipped test/reason | `DoctorSubprocessBoundaryTests.test_posix_detached_descendant_is_typed_not_ready` — `POSIX setsid residual is not applicable on Windows` |
| Scope | Focused validation only; no full-doctor, repository-CI, or Envelope-B exact-head claim |

The Curator independently confirmed the no-handle-before-API-resolution/no-child tests,
untransferred-handle cleanup, protected plan/overlay identities, forbidden-path absence,
and clean diff. This receipt appends only Envelope B.

Corrected independent Judge disposition for R3: **ADOPT_CANDIDATE** for focused
evidence only. The Judge rechecked both R3 identities after the Envelope-B append and
accepted only the Curator receipt above. All earlier Payload-A/R2 receipts and the
Judge's earlier R3 pre-receipt disposition are superseded and qualify nothing. The
remaining blockers are exclusively the held full-doctor and repository-CI gates; their
receipts must bind these exact R3 identities. Envelope B remains evidence-only and is
not covered by this or any future exact-head CI claim.

## Unattested leased full-doctor execution — UNATTESTED_TERMINAL_DETACH

The lease-release run was started once with the intended command,
`C:\Python314\python.exe .autopilot/bin/autopilot.py --repo-root . doctor --json`, in
this worktree, with `PYTHONPATH` set only to this worktree's resolved `src` and inherited
`GIT_PAGER` removed. Windows process observation confirms the doctor process and its
isolated exact-worktree controller-test child existed (doctor process creation observed
at `2026-08-23T08:08:18Z`; controller child at `2026-08-23T08:08:22Z`) and later exited.

The terminal capture session detached before its buffered stdout/stderr, exit code, and
start/end/duration markers were recoverable. Consequently, this envelope has **no**
complete JSON document, parse result, exit code, `READY` state, controller-test result,
or definitive descendant-cleanup receipt for that run. A failed preliminary launcher
attempt before it selected multiple `python` paths and started no Python process. No
full CI was started. This is not a full-doctor pass and must not be repaired by claiming
success from process disappearance; it requires replanning/re-authorizing an auditable
single-run capture method.

The durable owner directive authorized recovery without repeating authority. Exact
process-tree inspection later found no surviving doctor/controller/known descendant PID
or direct child. The only discoverable temp doctor logs predate this run (latest
`2026-08-23T07:15:35.1468790Z`); no AppData evidence file or temp artifact can supply
the missing 08:08 JSON, exit, or timing metadata.

## External durable-capture harness and dry-run

The retry harness is outside the repository and R3 at
`C:\Users\beesp\AppData\Local\HiveMindOS\evidence\durable-doctor-capture\Invoke-DurableCapturedProcess.ps1`.
Its `Launch` mode creates a dedicated external run directory and precreates
`stdout.tmp`/`stderr.tmp`, writes an atomic request, then starts the same script's `Run`
mode with `Start-Process -WindowStyle Hidden`. The detached helper pins the absolute
interpreter/cwd/`PYTHONPATH`, removes inherited `GIT_PAGER`, streams child stdout and
stderr to the dedicated files, and in `finally` atomically promotes output and receipt
files before atomically writing the completion sentinel. Its receipt has start/end,
duration, child PID, exit, command identity, and exact paths.

Two preliminary dry launch directories (`dry-r3-20260823t0817` and
`dry-r3-20260823t0821`) are preserved without completion sentinels: each exposed a
harness path-guard bug before it launched the harmless child. After correcting the
external harness, dry run `dry-r3-20260823t0822` completed through a hidden helper
(`38172`) and harmless child (`79028`): exit `0`, duration `0.072s`, atomic final
stdout/stderr/receipt files, and sentinel all validated. Its stdout bytes are
`durable-dry-stdout\r\n`; stderr is `durable-dry-stderr`; no temporary output file or
child process remained. The dry receipt and sentinel are at
`...\runs\dry-r3-20260823t0822\receipt.json` and `...\complete` respectively.

This validates the capture mechanism, not doctor. R3 is unchanged. The next full doctor
is explicitly labeled `RETRY-AFTER-CAPTURE-FAILURE` and is permitted solely because the
first execution has no qualifying receipt.

## Reproduced pre-repair distinction

The supplied incident command was reproduced from this worktree with its ordinary
ambient binding:

```powershell
python .autopilot/bin/autopilot.py --repo-root . doctor --json
```

The original implementation had a direct `subprocess.run(..., timeout=180)` controller
test boundary with no `TimeoutExpired` handler. The initial reproduction began at
`2026-08-23T06:38:36Z`; the 180-second parent boundary expired and left child test
processes, which were terminated by exact PID before repair work continued. The desktop
launcher did not preserve that initial parent stdout, so this receipt does not invent a
replacement transcript. The source request's traceback/exit-1 evidence remains the
authoritative retained adverse record for that initial execution.

The reduced observations below distinguish environment binding from full validation;
neither is a full-doctor pass.

| Command environment | Result | Measured duration |
| --- | --- | --- |
| `PYTHONPATH` removed; `python .autopilot/bin/autopilot.py --repo-root . doctor --skip-controller-tests --json` | exit 1; valid JSON; isolated child bound correctly but ambient package origin was `C:\Repos\HiveMind\hive-mind-os\src`, reported as `severity: error` | 4.627s |
| `PYTHONPATH=C:\Users\beesp\.codex\worktrees\5d72\hive-mind-os\src`; same command | exit 0; valid JSON; `READY_REDUCED`, `validation_scope: reduced`, controller tests explicitly skipped | 4.646s |

No editable install was changed for either observation.

Independent Curator reproduction on the same worktree confirmed the distinction without
mutating any install:

| Command environment | Started UTC | Finished UTC | Duration | Result |
| --- | --- | --- | --- | --- |
| `PYTHONPATH` removed; reduced doctor command above | `2026-08-23T07:41:59.9411882Z` | `2026-08-23T07:42:05.6421583Z` | `5.701s` | exit `1`; `BOOTSTRAP_INVALID`/reduced; exact child origin was this worktree but ambient origin was `C:\Repos\HiveMind\hive-mind-os\src\hive_mind_os\__init__.py` |
| `PYTHONPATH=C:\Users\beesp\.codex\worktrees\5d72\hive-mind-os\src`; reduced doctor command above | `2026-08-23T07:42:05.6475320Z` | `2026-08-23T07:42:11.1501472Z` | `5.503s` | exit `0`; `READY_REDUCED`; both origins were this worktree |

These independent reduced diagnostics are not a full doctor pass.

## Candidate focused validation

```powershell
python -m unittest discover -s .autopilot/tests -p test_doctor_boundary.py -v
```

The early pre-containment candidate passed 15 tests in 3.517s. That result is retained
as a superseded intermediate receipt, not current acceptance evidence.

The earlier statement of “19 passed, 1 skipped, in 5.786s” is a **superseded,
pre-correction reviewer receipt**. It is not evidence for this candidate and must not
be reused.

The subsequent 22-run receipt is also superseded: it predates the adversarial
reader-`RuntimeError` fix and must not be treated as current acceptance evidence.
Its recorded measurements are retained as intermediate history only:

| Field | Observed value |
| --- | --- |
| Command | `python -m unittest discover -s .autopilot/tests -p test_doctor_boundary.py -v` |
| Started UTC | `2026-08-23T07:37:15.5915032Z` |
| Finished UTC | `2026-08-23T07:37:20.3472317Z` |
| Outer measured duration | `4.756s` |
| Test runner result | 22 run: 21 passed, 1 POSIX-only `setsid` residual test skipped on Windows; inner runner duration `4.563s` |
| Exit | `0` |

The intermediate run after the reader fix is retained separately for reproducibility,
but is not the acceptance receipt because the court/evidence edits had not yet frozen:

| Field | Observed value |
| --- | --- |
| Command | `python -m unittest discover -s .autopilot/tests -p test_doctor_boundary.py -v` |
| Started UTC | `2026-08-23T07:39:58.4258863Z` |
| Finished UTC | `2026-08-23T07:40:03.5565482Z` |
| Outer measured duration | `5.131s` |
| Test runner result | 23 run: 22 passed, 1 POSIX-only `setsid` residual test skipped on Windows; inner runner duration `4.878s` |
| Exit | `0` |

Independent Curator pre-evidence-freeze focused receipt:

| Field | Observed value |
| --- | --- |
| Command | `python -m unittest discover -s .autopilot/tests -p test_doctor_boundary.py -v` |
| Started UTC | `2026-08-23T07:41:26.8518940Z` |
| Finished UTC | `2026-08-23T07:41:31.9151597Z` |
| Outer measured duration | `5.063s` |
| Test runner result | 23 run: 22 passed; inner runner duration `4.859s` |
| Exit | `0` |
| Host OS/capability | `Windows-11-10.0.26200-SP0`, x64; Windows has no POSIX `setsid` session-isolation capability used by the skipped test |
| Exact skipped test | `DoctorSubprocessBoundaryTests.test_posix_detached_descendant_is_typed_not_ready` |
| Exact skip reason | `POSIX setsid residual is not applicable on Windows` |

This is a POSIX-only residual-risk test, not a Windows-specific skip. It demonstrates
the documented limitation that a POSIX descendant can call `setsid`; it does not waive
Windows containment. The same Windows run exercises the Job-backed timeout descendant
cleanup and inherited-handle paths, while the dedicated forced Job-resume failure test
asserts `containment_setup_failed`. It also covers the generic reader-failure JSON
boundary, strict drainers, no-PID test cleanup, post-launch cleanup, and deterministic
binding/target tests. ADR case counts remain static design information, not a
substitute for this execution receipt.

Independent Curator focused receipt before the Payload-A lock:

| Field | Observed value |
| --- | --- |
| Command | `python -m unittest discover -s .autopilot/tests -p test_doctor_boundary.py -v` |
| Started UTC | `2026-08-23T07:44:27.8360716Z` |
| Finished UTC | `2026-08-23T07:44:32.9159100Z` |
| Outer measured duration | `5.080s` |
| Test runner result | 23 run: 22 passed; inner runner duration `4.885s`; the one skip is the exact POSIX-only test and reason recorded above |
| Exit | `0` |

This is pre-Payload-A-lock focused validation only. It is not a full-doctor pass and is
not repository CI.

Pre-replacement-lock focused implementation receipt:

| Field | Observed value |
| --- | --- |
| Command | `python -m unittest discover -s .autopilot/tests -p test_doctor_boundary.py -v` |
| Started UTC | `2026-08-23T07:58:27.2145900Z` |
| Finished UTC | `2026-08-23T07:58:32.0403202Z` |
| Outer measured duration | `4.826s` |
| Test runner result | 25 run: 24 passed; inner runner duration `4.597s`; one POSIX-only test skipped on Windows |
| Exit | `0` |
| New adversarial coverage | Missing `NtResumeProcess` and `CreateJobObjectW` produce typed `containment_unavailable` with no Job/child launch; a failed Job configuration closes its untransferred handle and still launches no child |

This receipt predates the replacement lock and is not qualifying focused, full-doctor,
or CI evidence.

Latest pre-replacement-lock focused receipt (after the final API-error normalization):

| Field | Observed value |
| --- | --- |
| Command | `python -m unittest discover -s .autopilot/tests -p test_doctor_boundary.py -v` |
| Started UTC | `2026-08-23T08:00:09.7150177Z` |
| Finished UTC | `2026-08-23T08:00:14.6073099Z` |
| Outer measured duration | `4.892s` |
| Test runner result | 25 run: 24 passed; inner runner duration `4.686s`; one POSIX-only test skipped on Windows |
| Exit | `0` |

It is still non-qualifying until the replacement Payload A is locked and independently
reviewed.

Post-Payload-A-lock independent Curator focused receipt:

| Field | Observed value |
| --- | --- |
| Qualified Payload A ordered-record SHA-256 | `a4892c8ad1942b8f530475590dab3e1bb112a6b81d92173cf8289e2123de0b91` (627 bytes; all six constituent hashes independently matched) |
| Command | `python -m unittest discover -s .autopilot/tests -p test_doctor_boundary.py -v` |
| Started UTC | `2026-08-23T07:48:52.7704797Z` |
| Finished UTC | `2026-08-23T07:48:57.7905464Z` |
| Outer measured duration | `5.020s` |
| Test runner result | 23 run: 22 passed; inner runner duration `4.829s` |
| Exit | `0` |
| Host OS/capability | Windows x64 host; the POSIX `setsid` session-isolation capability is unavailable |
| Exact skipped test | `DoctorSubprocessBoundaryTests.test_posix_detached_descendant_is_typed_not_ready` |
| Exact skip reason | `POSIX setsid residual is not applicable on Windows` |
| Scope | Focused validation only; no full-doctor or repository-CI claim |

The skip is a POSIX residual-containment observation, not a waived Windows requirement.
Windows Job descendant timeout/inherited-handle coverage and forced Job-resume failure
coverage ran in this same focused suite. This is an Envelope-B append and does not alter
Payload A or claim coverage for Envelope-B bytes.

Independent Judge disposition: **conditional approval** of Payload A as a candidate.
The Judge independently verified the 627-byte manifest
`a4892c8ad1942b8f530475590dab3e1bb112a6b81d92173cf8289e2123de0b91`,
the 302364-byte raw-content aggregate
`f4c4d9d488bb8a69b4ad87c734dcb2af77b4c2dbb99acde9d6a435027810d055`, and
all six constituent hashes. The Judge states that the focused receipt qualifies only
those exact Payload-A identities; Envelope B may append bindings but cannot enlarge
qualification or be described as full-CI exact-head coverage. Commit/promotion remains
blocked until the held lease permits a successful ordinary full doctor and repository
CI, each bound to those same two A identities.

## Candidate full doctor, bound environment

```powershell
$env:PYTHONPATH = 'C:\Users\beesp\.codex\worktrees\5d72\hive-mind-os\src'
python .autopilot/bin/autopilot.py --repo-root . doctor --json
```

Started `2026-08-23T07:00:14.9802165Z`. The result was valid JSON with empty stderr and
the exact-child plus ambient binding both correct. It was **not** a full pass:

- `controller-tests`: `passed: false`, `failure_kind: nonzero_exit`, `returncode: 1`;
- bounded controller-test duration: `322.832s` of `600s`;
- The then-candidate's byte counts, SHA-256 values, and truncation metadata are not
  repeated here: later threat review correctly classified them as secret-derived
  offline-guessing telemetry. Raw child output was never retained or emitted.

This is an adverse candidate receipt. It proves the new timeout/json boundary stayed
bounded and typed under load, but it does not establish `READY` or a clean full doctor.
An intermediate bound run started at `2026-08-23T07:09:55.655Z` produced a `READY`
JSON document at `2026-08-23T07:15:35.004209Z`; its controller-test duration was
334.026s. The desktop wrapper detached before it could retain the outer process exit
code. It is **superseded and non-qualifying** because the subsequent independent review
found inherited-pipe, PID-containment, target-test, and output-fingerprint defects.

The final corrected full-doctor receipt must be rerun only after the root releases the
repository-wide validation lease. No current `READY` claim is made from either prior
candidate run.

## Held repository-wide gate

The required repository CI command has not been run in this candidate because the DAG
standard prerequisite owns the repository-wide validation lease:

```powershell
python -m unittest discover -s tests -v
```

The only permitted future environment adjustment is removal of inherited `GIT_PAGER`.
No commit or promotion is authorized from this receipt.

## Capture-harness adverse history and current review hold

The first leased ordinary full-doctor attempt remains
**UNATTESTED_TERMINAL_DETACH**: its terminal capture detached after the doctor and
controller subprocess were observed, leaving no complete stdout, exit, or duration
receipt. Later process inspection found no known residual PID, but that cannot attest
the missing outcome.

The initially labelled retry was allowed only to test the capture path, but is now
retained as **NONQUALIFYING_HARNESS_DESIGN_MISMATCH**. Its external receipt is:

C:\Users\beesp\AppData\Local\HiveMindOS\evidence\durable-doctor-capture\runs\r3-retry-capture-failure-20260823t0825\receipt.json

It recorded child exit 0 from 2026-08-23T08:22:32.2943801Z to
2026-08-23T08:27:43.9699387Z (311.676s), with a 3371-byte JSON stdout file and
empty stderr, but it used managed redirected readers and CopyToAsync. It therefore
does not establish READY, a qualifying full doctor, or permission for CI.

The subsequent direct-file dry attempts dry-r3-direct-handles-20260823t0830 and
dry-r3-direct-handles-20260823t0832 are nonqualifying harness diagnostics
(pre-child MethodException), while dry-r3-direct-handles-20260823t0833 is also
nonqualifying: it demonstrated direct output files but was externally rejected for
the remaining broad-handle inheritance, identity/exit, and handshake defects.

No doctor or dry run has been launched with the replacement helper. The current
external helper is outside the repository and Payload A:

| Field | Value |
| --- | --- |
| Path | C:\Users\beesp\AppData\Local\HiveMindOS\evidence\durable-doctor-capture\Invoke-DurableCapturedProcess.ps1 |
| SHA-256 | 8df519b758af98c1aa6b8a9d2a024b945303d4f5fbc68eeea95ec1294b605329 |
| Bytes | 25562 |
| Static parser check | 2026-08-23T08:46:26.1880139Z; zero PowerShell parse errors |
| Design | Native one-method STARTUPINFOEXW launch; only NUL/stdout/stderr in PROC_THREAD_ATTRIBUTE_HANDLE_LIST; durable nonce/ready/grant handshake; direct output-file handles |
| State | **HOLD_FOR_TWO_INDEPENDENT_HARNESS_REVIEWS** |

The R3 immutable payload was independently rechecked at
2026-08-23T08:37:21.4703721Z: all six constituent hashes matched,
the 627-byte line record remained
84610cb9deda152c0571589bc316fd2a324df6c69d2865338149c48ae964b2f3,
and the raw aggregate remained
ac9a94e1dbf7b814a39451b7825125c643969710498f37e0af1fa0a1b14c3e65.
.autopilot/plan.json retained Git blob
ee7ec9f2756fcff2b7010238d7064d017c4df7af; both generic overlay checks were
clean. These Envelope-B bytes do not alter or receive R3 qualification.

The helper identity cited above was replaced before completion of review and is
superseded. The latest reviewed freeze is:

| Field | Value |
| --- | --- |
| SHA-256 | 7ffc59315ae511571fb0b44c1bf8fd3e87c8b6b6a24357dada133a391d30cf87 |
| Bytes | 29540 |
| Frozen UTC | 2026-08-23T08:54:37.8280452Z |
| Parser | zero errors |
| Execution since freeze | none |

Independent Curator and Win32-expert reviews confirm the promotion correction: a
missing temporary output is typed as a failure, and a qualifying capture requires a
terminal child identity/result, no cleanup failure, both output promotions, disk-file
types, stable final output identities, and the complete request/helper/nonce/ready/
grant hash chain.

They nevertheless withhold dry-run approval. Direct regular-file stdout/stderr have
no hard storage quota, so an adversarial child could consume storage before the
post-run receipt gate. In addition, an equal-privilege same-user writer can read the
declared on-disk nonce/hash values and prewrite a syntactically valid grant between
ready and the launcher's no-replace publication. The documented same-user ACL
residual is not a parent-authority boundary. These are current blockers; no claim of
full doctor, READY, CI, or commit is permitted.

## 2026-08-23 reviewed e679 dry run — adverse, nonqualifying

The preceding harness holds are adverse history. They were superseded for one
review-authorized harmless dry run by the external helper frozen at SHA-256
e679f8e6b26645f5e4c975a879a1387ba93268a535a203a193d56e21a7e3a45c
(42,953 bytes; mtime 2026-08-23T09:08:24.9161993Z). This did not authorize a
full doctor or repository CI.

Exactly one dry run was launched as
`r3-dry-e679-20260823t0918-dbd652887004` under
`C:\Users\beesp\AppData\Local\HiveMindOS\evidence\durable-doctor-capture\runs\r3-dry-e679-20260823t0918-dbd652887004`.
It used `C:\Python314\python.exe`, the isolated worktree as cwd, that worktree's
`src` as `PYTHONPATH`, a 60-second bound, and command identity
`harmless-native-capture-dry-run-e679`. Its only child arguments wrote the fixed
22-byte stdout and stderr marker lines and exited 0; both final output files match
those markers, are below 16 MiB, and their recorded identities match.

The dry run is nevertheless **NONQUALIFYING_HARNESS_FAILURE**. Its receipt reports
`child_failure_kind=DescendantProcessesRemain`,
`termination_reason=descendants_after_root_exit`, `terminal_child_result=false`,
`qualifying_capture=false`, and helper exit 70. The job subsequently reported tree
empty and independent PID plus creation-time inspection found no surviving captured
child, but neither fact repairs the nonterminal result. Separately, the `complete`
file contains the receipt SHA-256 followed by CRLF (66 bytes), rather than the
required SHA-256 plus one LF (65 bytes), so the independent exact-sentinel assertion
also failed. The request/helper/nonce/ready/grant hashes all recomputed correctly;
no temporary files remained; and all six R3 constituent hashes still matched. No
retry, full doctor, CI, commit, or promotion is authorized from this result.

Run artifact SHA-256 values: request.json
935dd3801a85ac462f006eed4a175581903e438f6d479a55c963202c603ec1f6;
launch-nonce.bin 67a110c6c5836b13d9e5396cd094298bc17857ab1b2504a9563300723e531bc5;
ready.json 56f6f158f490f749832fdfe338fe60cc93d2ed71f7c84da438a29fb2278e30c9;
launch.json f6ca4c95e2d278c28784368c23dc9a4a2dc948df4a373cf3acf1d4acaaaa2c65;
receipt.json 188b4844ff99a7a4a781d7aee7c4ff5c4f1202d97e21968161cae9d604e01b94;
complete cba8a87a4b022d578a7f1af3092cca44152cfcbef29f60854aeba44d7600adcc;
stdout.txt 3f34bc286c02e7f4a7ca3e7296ecc8a01caa1a228615cd486e16ed349ad134bc;
stderr.txt 20b7de84ba8960d23229a3f79f66c5f5306c0852fc6ad03e41b7894cb72c3b44.
This is an Envelope-B append only; it is excluded from Payload A R3 and does not
claim exact-head qualification for itself.

Clarification: the raw sentinel form is the lowercase receipt SHA-256 followed by
the Windows CRLF newline sequence. It therefore has the required textual
SHA-256-plus-newline content; the prior sentence records only that it did not meet a
stricter single-LF byte assertion used in the independent checker. The qualifying
failure and stop decision rest independently on the recorded nonterminal child
result, not on newline style.

The durable receipt timestamps are 2026-08-23T09:20:34.2578699Z through
2026-08-23T09:20:34.5395659Z (0.281696 seconds). Its complete terminal receipt,
rather than this Envelope-B append, remains the authoritative timing and field-level
record for the adverse dry run.

## Accounting-drain replacement frozen for review

The e679 helper is **superseded for future execution only**. Its adverse dry-run
directory and all of its request, nonce, ready, grant, receipt, sentinel, and output
artifacts remain preserved exactly as adverse evidence; in particular, the recorded
false-positive `DescendantProcessesRemain` result is not relabelled as a pass.

The replacement external helper is frozen pending independent review at:

| Field | Value |
| --- | --- |
| Path | C:\Users\beesp\AppData\Local\HiveMindOS\evidence\durable-doctor-capture\Invoke-DurableCapturedProcess.ps1 |
| SHA-256 | 61b2c7a33e8da54035c48ca19add70d2c992119d3412483a95176448a9eaf263 |
| Bytes | 49,888 |
| Mtime UTC | 2026-08-23T09:28:54.3804159Z |
| Freeze observed UTC | 2026-08-23T09:30:13.0763522Z |
| Static validation | PowerShell parser: zero errors; both embedded C# blocks compiled without invoking the helper or a child |

The C# root-exit observation now uses a bounded, complete
`JobObjectBasicProcessIdList` snapshot (information class 3). A non-root PID is
treated as a real descendant and immediately causes owned-Job termination. An empty
or root-only snapshot uses the existing bounded cleanup interval solely to wait for
job accounting to drain; query failure, incomplete data, a non-root PID after drain,
or drain timeout remains typed and fail-closed. Receipt fields record bounded query
counts, snapshot completeness, root-only status, accounting-drain polls, duration,
and outcome. No dry run, doctor, focused test, or repository CI was launched for
this replacement. All six R3 Payload-A constituent hashes were rechecked and still
matched at freeze; this Envelope-B append is excluded from Payload A.

## Process-list review correction — replacement pending review

The 61b2c7a33e8da54035c48ca19add70d2c992119d3412483a95176448a9eaf263
external helper freeze is rejected and superseded without execution. The e679 adverse
run and every existing Envelope-B record remain preserved. The replacement pending
the same independent reviewers is:

| Field | Value |
| --- | --- |
| SHA-256 | 31056332b635ac038c1af6cf9fc457b89d6de17d59e71de7f12572ceab2ec128 |
| Bytes | 51,445 |
| Mtime UTC | 2026-08-23T09:38:57.2877988Z |
| Frozen UTC | 2026-08-23T09:39:23.1021824Z |
| Static validation | PowerShell parser: zero errors; both embedded C# blocks compiled without helper or child execution |

The revised class-3 observer returns on any non-`ERROR_MORE_DATA` query failure
before reading unmanaged output, retries documented partial snapshots until a bounded
complete list is obtained, decodes `ULONG_PTR` PID values separately on x86 and x64,
and records empty-at-signal separately from root-only-at-signal. It also corrects the
Job limit ABI fields and records whether a child exit was actually observed, emitting
null plus `ChildExitObservationFailure` rather than a default zero when it cannot be
obtained after bounded Job cleanup. No dry run, doctor, focused test, or CI was
launched. This is an Envelope-B append only and does not qualify or modify Payload A.

## Receipt final-exit semantic correction — replacement pending review

The 31056332b635ac038c1af6cf9fc457b89d6de17d59e71de7f12572ceab2ec128
freeze is superseded without execution. Its review found that a receipt could publish
before a later sentinel-publication failure changed the actual helper exit. The new
external-only freeze is:

| Field | Value |
| --- | --- |
| SHA-256 | 19430f3a2df705a7279c41a2e57b83d67b726cb0abe0d2e5bdbe2b53c470b386 |
| Bytes | 51,594 |
| Mtime UTC | 2026-08-23T09:42:28.0333672Z |
| Frozen UTC | 2026-08-23T09:42:39.8279183Z |
| Static validation | PowerShell parser: zero errors; both embedded C# blocks compiled without helper or child execution |

The receipt now calls the pre-publication value `helper_exit_code_selected` and
states that it is authoritative only if the completion sentinel exists. Thus a
receipt left behind by a failed sentinel publication does not claim the helper's
final exit. No execution occurred, and this append preserves the e679 adverse run,
all prior evidence, and Payload A unchanged.

## Handle-signaled child-exit correction — replacement pending review

The 19430f3a2df705a7279c41a2e57b83d67b726cb0abe0d2e5bdbe2b53c470b386
freeze is superseded without execution because numeric exit value 259 cannot by
itself distinguish an observed terminal exit from `STILL_ACTIVE`. The pending
external-only replacement is:

| Field | Value |
| --- | --- |
| SHA-256 | c0ad343293094e5e3a07d2773e83c03002fd962b512706f2cc34ebc5aeda4bef |
| Bytes | 51,963 |
| Mtime UTC | 2026-08-23T09:43:32.8812226Z |
| Frozen UTC | 2026-08-23T09:43:53.1488252Z |
| Static validation | PowerShell parser: zero errors; both embedded C# blocks compiled without helper or child execution |

The retained process HANDLE is now zero-waited first. Only `WAIT_OBJECT_0` permits
`GetExitCodeProcess`, which then accepts every uint32 value including 259; timeout
and other wait results are typed exit-observation failures. The PowerShell
native-success path also requires `ChildExitObserved` before it maps a child exit to
the selected helper exit. No PID operation, dry run, doctor, focused test, or CI was
performed. This Envelope-B append preserves the e679 adverse run and leaves Payload
A unchanged.

## c0ad awaited-subprocess analysis and handle-member replacement

The c0ad343293094e5e3a07d2773e83c03002fd962b512706f2cc34ebc5aeda4bef
helper is superseded for execution after the preserved V2 adverse run. That run's
root Python process had awaited its harmless `subprocess.run` probe, yet a complete
Job list still named one non-root PID after the retained root handle signaled. This
is the same class of timing a full doctor can encounter while its controller tests
create and await subprocesses: a numeric Job-list PID alone does not establish a
currently live descendant. The adverse run remains unchanged and nonqualifying.

The replacement external helper is frozen pending the two root reviewers:

| Field | Value |
| --- | --- |
| SHA-256 | 7fed1715beb8c5df79d1bff74dbba7c4a01cc1986f03aae16f6f8508450ffee5 |
| Bytes | 64,024 |
| Mtime UTC | 2026-08-23T10:05:36.4875861Z |
| Frozen UTC | 2026-08-23T10:06:30.5869720Z |
| Static validation | PowerShell parser: zero errors; both embedded C# blocks compiled without helper or child execution |

After the retained root HANDLE signals, every non-root Job-list PID is now opened
only with `SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION`, non-inheritable. The
helper verifies `GetProcessId` and exact owned-Job membership, observes state with a
zero-time handle wait, records capped PID/creation/state evidence, and closes every
observation handle. Vanished and outside-Job reuse is re-queried; a verified live
member, API ambiguity, access denial, malformed snapshot, deadline, record cap, or
close error terminates only the owned Job and fails closed. Each accounting-drain
poll obtains a fresh complete list and re-observes every member. No dry run, doctor,
focused test, CI, commit, or promotion was performed. This Envelope-B append is
excluded from Payload A, whose six constituent hashes were rechecked at freeze.

## c0ad native Job-descendant dry run — adverse, nonqualifying

Exactly one authorized c0ad helper dry run was launched as
`r3-dry-c0ad-20260823t0946-8bb817c61ab8` at
`C:\Users\beesp\AppData\Local\HiveMindOS\evidence\durable-doctor-capture\runs\r3-dry-c0ad-20260823t0946-8bb817c61ab8`.
The Mode-Launch wrapper exited 0. The receipt spans
2026-08-23T09:49:17.8915066Z through 2026-08-23T09:49:18.2849653Z
(0.3934587 seconds), used exact helper SHA-256
c0ad343293094e5e3a07d2773e83c03002fd962b512706f2cc34ebc5aeda4bef,
`C:\Python314\python.exe`, the isolated worktree cwd and `src` binding,
30-second bound, and command identity `ADR068-R3-DURABLE-NATIVE-DRY-V2`.

This run is **NONQUALIFYING_CONTAINMENT_OBSERVATION_FAILURE**. It produced an
observed child exit 0 and the exact requested 34-byte stdout/stderr records, but its
complete one-PID Job snapshot was neither empty-at-signal nor root-only-at-signal.
The receipt therefore reports `child_failure_kind=DescendantProcessesRemain`,
terminates the owned Job, selects helper exit 70, and sets both
`terminal_child_result` and `qualifying_capture` false. Tree-empty and cleanup were
subsequently true; independent PID plus creation-time checks found neither captured
helper nor child still alive. Those cleanup facts do not convert the nonterminal
capture into a pass.

All other independent checks matched: exact eight ordinary final artifacts with no
temporary/reparse object; the request/helper/nonce/ready/grant hash chain; 66-byte
receipt-SHA-plus-CRLF sentinel; disk output handles, promotions, identities, and
strict sub-16-MiB sizes; correct child arguments, Python/cwd/binding; and unchanged
pre-Envelope-B HEAD, status, diff, inventory, plan blob, and generic overlay trees.
Payload A R3 retained both the 627-byte line record
84610cb9deda152c0571589bc316fd2a324df6c69d2865338149c48ae964b2f3 and
the 307879-byte raw aggregate
ac9a94e1dbf7b814a39451b7825125c643969710498f37e0af1fa0a1b14c3e65.

Artifact SHA-256 values: request.json
433360abaf2f7fc55f26744a4eaeaeff8b7bbefbacb72be89f7cb6321af05bf4;
launch-nonce.bin ee36194ac88a4ce9192e2c1e3f53ffdb254cb8a73cb465d695092406c55f31f7;
ready.json 034dd00c2d132b2ae9a2b2b3f2142d30aa7366bc5a1b3baa3ae802bafcf0384f;
launch.json a1158d252baa740f3b47ec6c5b84fa853c176081b961b6dbc31b023dee35bab3;
receipt.json 72457e9cd30c5cac2de72f32bdfa3765df2b01a6657bba16ddf4d6f9adc386fe;
complete bac231181f4afe45baafe13996d8061f778761ca1c44ce38ef1e876c19cd8796;
stdout.txt cfc3dbe76c584cb8028c5641723bda19110e518f9aad72292f0826f8ed477b93;
stderr.txt e103ac7de3b7d08e57c028827ee657b9eadf42191cd65f294e8adb316fb4b1a4.
No retry, doctor, test suite, CI, commit, or promotion is authorized by this result.
This is an excluded Envelope-B append and does not alter Payload A qualification.

## V3 stable-array evidence adaptation and final gate receipts

### 3ada V3 dry run — native success, schema-nonqualifying adverse history

The preserved run `r3-dry-3ada-20260823T102541-d730e1b5c02b` completed its
native/operational checks successfully on helper
`3ada019c73da335a9b80ecc0909bc057c08ab232c16c06fde9da23816e4c74d1`.
Its receipt was nevertheless **schema-nonqualifying**: empty
`cleanup_failures` serialized as JSON `null`, and the one-item
`job_member_observation_records` collection serialized as a scalar. The fresh Judge
issued **ADAPT**, preserving the run as successful native-execution evidence but not
as promotion-grade capture evidence. It authorizes neither a doctor pass nor CI by
itself; the adverse history is retained unchanged.

### v7 helper adaptation and static review

The external helper was adapted outside the repository to schema
`hive-mind-durable-capture-v7-stable-receipt-arrays`, forcing stable JSON arrays for
`cleanup_failures`, `job_member_observation_records`, and `child_arguments` for the
0/1/many cases. The frozen helper identity is:

| Field | Value |
| --- | --- |
| SHA-256 | `bf873fb4ecba27fc5ff4caf7bef55f0a78c37a2c28e19354138c83d4f1504f5b` |
| Bytes | 66,161 |
| Mtime UTC | 2026-08-23T10:36:16.7815101Z |
| Static validation | PowerShell parse: zero errors; both embedded C# blocks compiled (2 of 2); two independent static reviewers: **APPROVE** |

This external helper and all receipts in this section are Envelope B only. They are
excluded from Payload A R3 and must not be described as full-CI exact-head coverage
for themselves.

### v7 qualifying harmless dry run

Exactly one qualifying post-adaptation dry run,
`r3-dry-bf873-20260823T103942-2da15e09c401`, used the v7 helper above. Its
receipt SHA-256 is
`79960846fc05832c0bd5ba21ac5f5cce312ee5071808991f8aac327c95f277cc`.
The immutable handshake artifacts were request
`eff2e8b99b983f4e61010f6bbc71649ce2fcd96543fb32dad8b589244e269fe2`, nonce
`47d0760d3af0293db3192e19a2edec6ea92a338e55163db554a49c0851087a2c`, ready
`f848b1eda365ab4f0a323b6f98df98baf5dd1300fa08e4bf82d7c90ff7395a00`, and
launch `94f66ed15003b1777a821d585a5c4bbd13f4b85d6b2ef9c1111fb6ac34ead27a`.

Stdout was exactly 34 bytes with SHA-256
`cfc3dbe76c584cb8028c5641723bda19110e518f9aad72292f0826f8ed477b93`; stderr
was exactly 34 bytes with SHA-256
`e103ac7de3b7d08e57c028827ee657b9eadf42191cd65f294e8adb316fb4b1a4`.
The receipt demonstrated stable 0/1/many collection shapes: child arguments 7,
cleanup failures 0, and observation records 1. Helper and child exits were both 0;
the owned Job drained naturally in 15 ms with final active-process count 0, no
termination, and no same-identity survivor. Two independent reviewers approved.
The Judge issued **ADOPT** only as the prerequisite gate for one ordinary full
doctor; it did not authorize another dry retry or repository CI by itself.

### One bound ordinary full doctor — full READY

Exactly one ordinary full doctor was then captured as
`r3-full-doctor-bf873-20260823T104550-2c4ddb145462`, command identity
`ADR068-R3-FULL-DOCTOR-V1`, through the v7 helper with a 900-second whole-run bound.
It used `C:\Python314\python.exe`, the exact isolated worktree as cwd and repository
root, the exact worktree `src` as `PYTHONPATH`, inherited `GIT_PAGER` removed, and
controller tests enabled. The capture receipt is
`1f52ef254f8789652510441b9c01a248134a7073a5fb3b234503d93a06df25be`.

Artifact identities are: request
`17d54e75b9217e36d3700483659cd2f242c4fcb8adcffce2df8ad3f8ea40543a`; nonce
`0261c8651ea61d7c2a5327f4899a87de95d104f79bd4d33519b5e5d1f0c81666`; ready
`17a1ba9a6a438476331de062dedba7c7f0a9479fe736b21b556114448157f6c1`; launch
`2955cda02420af8892a9dec91ba19d39aa502ed2102aa4d454da66afd81ad9a9`; stdout
3372 bytes / `0f138a50f01ea9a2e497821017ffdcd084cecd3b54bb3d56041fa63a4650fa11`;
stderr 0 bytes / `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`;
and completion sentinel
`5a3a556bac6b5e2fec34cd9dc7193d12a881638ae242ca90b8a1182a4e79281d`.

The receipt had stable collection shapes 5/0/1 (child arguments / cleanup failures /
observation records), helper exit 0, child exit 0, natural Job accounting drain in
16 ms to final active-process count 0, no Job termination, and no same-identity
survivor. The doctor emitted one strict JSON object: exit 0, `READY` rather than
`READY_REDUCED`, `passed=true`, controller tests ran and passed, and all six named
checks passed. Its environment fingerprint was
`sha256:9769f9796efb351da9b764fd49983b1130adccc0b8592e42581714d3727f8b39`.
The isolated Windows controller Job returned 0 in 303.315 seconds, below the
450-second prospective review threshold. The doctor receipt contains no retained
child text, length, or digest. Curator and Cross-Examiner approved; the Judge
**ADOPTED** this full doctor only as the gate permitting the one repository-CI run
below.

### One repository-CI gate — PASS

Exactly one repository CI gate ran against unchanged R3 with only inherited
`GIT_PAGER` removed:

```text
C:\Python314\python.exe -m unittest discover -s tests -v
```

The unified execution session was `84590`, exited 0, and reported `Ran 1119 tests
in 1082.185s` followed by `OK (skipped=7)`. Postflight was recorded at
2026-08-23T11:18:43.3903167Z. The durable evidence identifies the session, exit, and
unittest summary, but no independent raw CI transcript or transcript digest was
retained; no such digest is claimed. Postflight confirmed the six R3 hashes unchanged,
the 627-byte line manifest
`84610cb9deda152c0571589bc316fd2a324df6c69d2865338149c48ae964b2f3`, raw aggregate
`ac9a94e1dbf7b814a39451b7825125c643969710498f37e0af1fa0a1b14c3e65`, plan blob
`ee7ec9f2756fcff2b7010238d7064d017c4df7af`, Python/helper/HEAD unchanged, and status
with exactly the same eight intended entries. This Envelope-B append remains outside
the immutable R3 payload; it records results without asserting exact-head coverage
for the newly appended evidence bytes.
