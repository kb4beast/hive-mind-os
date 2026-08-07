# Verifiable Hive Kernel: Phase 4 local workers

Phase 4 adds bounded local worker orchestration only. It reuses the existing scheduler
for leases, heartbeats, stale-worker rejection, retry/backoff, dead-lettering, and
recovery. `KernelWorker` adds kernel job bindings and expiring exclusive write-scope
locks. It records the work transition before local scheduler completion and stops at
`AWAITING_VERIFICATION`; no role, provider, or external effect is run.

The scope-lock and scheduler databases are local and separate. A lock failure retries
the job without executor invocation; an expired lock can recover. This is not a claim
of distributed atomicity. Rollback stops workers and removes the additive lock store.

Full local-gate receipt is recorded in the committed branch history. Courtroom
disposition remains open.
