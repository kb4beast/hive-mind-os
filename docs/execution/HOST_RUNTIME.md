# Bounded host supervision

`HostRuntime` is the durable boundary around the subject-neutral `HostAdapter`.
It does not turn host capability into authority. The caller supplies an already
approved plan digest, generation, authority digest, subject identity, one-run
deadline, node set, and single-use nonce. The returned `HostLease` must match all
of them and may expire sooner, never later.

Every potentially effecting call records a canonical intent before crossing the
adapter. `create` prepares a lease, `poll` obtains a fresh observation, `message`
delivers one exact node envelope, `checkpoint` records successful evidence,
`cancel` requests bounded cancellation, `resume` rehydrates a lease after a
fresh clean-host observation, and `adopt` resolves an ambiguous result from an
explicit evidence digest. `execute` is an alias for the `message` boundary.

Operations are idempotent by an immutable key-to-request binding. A retry returns
the recorded exact result. Reusing a key for different bytes is denied. A crash
after intent recording, an adapter exception, or a wall-clock timeout is
`RECOVERABLE`: the runtime does not invoke the effect again. An operator or
orchestrator must observe and adopt an exact host lease or receipt. This prevents
duplicate external effects after response loss.

Each call is bounded by both an operation timeout and the one-run deadline.
Usage records measured wall time and input/output bytes. Model input/output
tokens remain `null` when the adapter cannot measure them; unavailable never
means zero. The SQLite journal is append-only, hash chained, canonically encoded,
and verified on restart.

These controls implement `AC-WAVE-HOST` while preserving the authority,
sealing, failure, and integration invariants described in `WAVE_RUNTIME.md`.
