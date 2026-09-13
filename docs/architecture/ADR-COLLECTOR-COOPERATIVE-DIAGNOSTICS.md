# Collector diagnostics must not crash validation

Status: proposed implementation; independent review and final delivery qualification
are recorded separately for their exact candidate commits.

## Evidence and decision

The Windows Python 3.12 job for PR179 candidate
`3bfd4edd504a1c1dc6b4448941dc38f4fdfcdbba` failed inside the activation-evidence
collector's nested executor tests. Its retained transcript ended during a
15-second `faulthandler` stack dump, without a successful terminal receipt.
The collector's generic failure path and short duration do not support an
enforced deadline exhaustion. The original job did not retain the numeric
child exit code, so its exact native failure cannot be proven from that log.

Separate experiments on Python 3.12.10 ran the unchanged frozen executor
module successfully, then reproduced access violations (`0xC0000005`) when
the C diagnostic timer was accelerated to exercise repeated live-frame
sampling. Both failed experiments and their passing control are retained.
Pinned CPython 3.12.10 source shows the watchdog traversing live frames from
its native thread. These experiments establish a diagnostic crash mechanism;
they do not retroactively supply the missing original CI process receipt.

Use a Python diagnostic thread to call `faulthandler.dump_traceback` every
15 seconds. On the supported ordinary GIL-enabled interpreters, the diagnostic
call runs while owning the interpreter lock. Signal the thread to stop and
join it before emitting any successful terminal marker. Retain a diagnostic
exception and fail the bootstrap if sampling fails. The integration test now
prints the collector's complete receipt alongside the transcript on failure,
preserving process outcome metadata before its temporary directory disappears.

## Threats and unchanged acceptance

Diagnostics must not create false failures by corrupting their subject, hide
their own failure, or continue writing after a terminal receipt. The extracted
real-bootstrap regressions exercise frequent sampling during executor frame
churn and an injected diagnostic exception. The former must retain a valid
complete test receipt; the latter must exit unsuccessfully without a terminal
success marker. Existing process drainage, descendant termination, timeout,
adverse outcome, source binding and no-activation assertions remain intact.

A Python diagnostic thread cannot acquire the interpreter lock during a native
hang that retains that lock. A stack dump may therefore be unavailable in that
case. The independent parent process still enforces the unchanged 300-second
module limit and 900-second overall limit, retains available output, and rejects
the incomplete run. Missing stacks or receipts never count as successful
validation. This is a diagnostic tradeoff, not an extension of either deadline.
No free-threaded interpreter qualification is claimed by this decision.

## Compatibility, migration and rollback

No receipt schema, candidate identity, expected test count, authority boundary,
historical source bundle or activation rule changes. Existing receipts keep
their original meaning. The generated bootstrap changes for subsequent
collector runs; there is no persisted-state migration. The diagnostic banner
explicitly identifies sampling rather than implying an enforced timeout.

Rollback is an ordinary revert of this bounded change. Retain its failed
attempts and qualification evidence; a rollback reintroduces the diagnostic
crash mechanism and must not be represented as a passing challenger. Historical
failure records and external custody/signing obligations remain separate.
