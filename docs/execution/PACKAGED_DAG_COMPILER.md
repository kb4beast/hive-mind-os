# Packaged portable DAG compiler

`hive_mind_os.dag_standard` is the sole compiler for the portable-plan product
surface. It is separate from the frozen `.autopilot` controller and never imports,
modifies, or executes that controller.

Compilation requires canonical plan bytes, a caller-supplied expected plan digest,
and the exact bytes named by the plan's V2 authoring-standard binding. The compiler
checks the standard version, source path, SHA-256, byte count, Git blob, and compiler
package identity before producing output. A stale request or subject can be bound by
the caller and fails before rounds are returned.

The output is inert data. Dependency levels are computed deterministically. Each
level is split by the smallest declared worker allowance and by resource capacity;
no later level is pulled forward. All eight specialist roles, all seven lifecycle
stages, and evidence on every node are mandatory. A successful receipt therefore has
zero errors and zero warnings, but it grants no lease and launches no process.

Rollback is deletion or reversion of this package surface. Historical plans,
standards, compiler bytes, rejected plans, and receipts remain evidence.
