# Verifiable Hive Kernel: Phase 11 compatibility migration

## Scope

Phase 11 begins with the narrowest legacy ingress route: `hive-mind enqueue`.
It preserves the legacy scheduler as the execution authority while appending a separate,
idempotent `legacy-enqueue-v1` binding in `brain-kernel.sqlite3`. The kernel never imports
the legacy runtime; `repository_compatibility.py` is an outer adapter.

## Contract and migration

The legacy parser, validation errors, semantic payload, `M-...` mission ID, scheduler job
ID, deduplication digest, output JSON, and exit code remain unchanged. On the default
`--compatibility-mode kernel-v1`, the legacy scheduler job is created first and the adapter
records the matching kernel mission `MISSION-legacy-...` with the versioned route, legacy
mission/job IDs, scheduler payload digest, and repository pin.

No legacy SQLite file is migrated or modified in place. The default kernel state root is the
sibling `.hive-mind-kernel-state`; `--kernel-state-dir` makes that new state location
explicit. Repeating the same enqueue reuses both the legacy job and its idempotent kernel
record.

## Acceptance and rollback

`tests/test_cli_enqueue.py` proves parser and payload parity, legacy deduplication, the
kernel migration binding, and rollback. The rollback switch
`--compatibility-mode legacy` performs legacy-only dispatch and reuses the same existing job
without adding another kernel event. Existing worker, scheduler, and kernel-worker tests
prove that legacy execution and recovery remain available.

Rollback is immediate: invoke `hive-mind enqueue` with `--compatibility-mode legacy`, or
revert the adapter change. Do not delete either state root; old jobs, mission checkpoints,
receipts, and kernel migration records remain readable evidence.

## Local receipt

Commit `54020b72d2fff602b355c99924b01b5cfb5d8ec5` (tree
`a54dcc7b58055be8850f4461191746fc94bd453d`) passed the focused parity and rollback
checks and the full gate: 530 tests passed with 5 expected skips in 1066.055 seconds.
The complete local full-gate transcript is retained at
`C:\t\phase11-12-full-gate-attempt2.log` with SHA-256
`e95e2b7c4c78cd08842025f56297adc04dc251bab62dbaafdd54b5451f2e2cb4`.

## Explicitly deferred routes

`serve`, `resume`, `missions`, `status`, and `deliver` require a richer versioned adapter.
In particular, kernel events do not yet model legacy checkpoint/effect adoption or the full
legacy projection schema. They remain legacy-authoritative rather than being cosmetically
rewired.
