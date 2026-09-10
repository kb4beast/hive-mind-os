# ADR: Gate recorded-patch recovery on focused checks

Status: proposed implementation; independent verification pending.

## Context and source

At commit `e4213bb40c8626490c59df012c14595339acddf1`,
`local_dag_runtime.py` rejects unsuccessful focused checks during ordinary
building but permits recorded-patch recovery to commit without the same gate.
The repository MIT license applies. Source acquisition is host-attributed;
this decision does not claim fresh test execution.

## Decision and challenge

Mirror the existing `host_checks.get('all_passed', False)` condition in recovery
after host and elapsed-time checks and before committing. Raise the existing
execution error so the existing handler appends `node_failed`; execution then
blocks before dependent dispatch. Preserve the copied report and any returned
check receipt, recovery sequence, and original authenticated history.

An adapter that always raises would avoid the returned-failure path, but the
existing ordinary failure regression exercises a returned unsuccessful result.
A truthy malformed success field remains outside this Boolean-result repair.
No receipt schema, public signature, acceptance threshold, or authority changes.

## Acceptance and ownership

The runtime maintainer owns this branch consistency rule. The regression in
`tests/test_local_dag_runtime.py` covers false, missing, exceptional, and successful
checks through recovery admission and execution. Measure absence of commits and
dependent dispatch on failure and preserved completion on success. Host execution
through a sealed adapter and separate verifier assessment remain required.

## Migration and rollback

No state migration is needed. Failure can leave an applied uncommitted patch;
retain receipts and supersede or revert only the isolated candidate. Existing
drift detection and recovery admission remain in force. No promotion is granted.
