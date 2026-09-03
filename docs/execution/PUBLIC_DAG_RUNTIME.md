# Public portable DAG runtime

The installed `hive-mind dag` surface provides `build`, `validate`, `rounds`,
`execute`, `resume`, `status`, `cancel`, `graph`, `reconcile`, and
`prepare-powershell` commands. Plan inspection takes explicit paths and works from
any current directory. `validate`, `rounds`, `graph`, and missing-state `status`
are read-only and do not create repository or state files.

`build` writes only an explicitly named local output after the proposal passes the
canonical compiler. It never runs a plan. The Python `SubjectExecutionService`
accepts repository, offline-local, research-artifact, and workflow modes through
the same plan contract.

Execution commands intentionally fail with `EXTERNAL_RUNTIME_REQUIRED` in the
unconfigured CLI. A filename is not an authority capability. A host integration
must independently verify the review, host attestation, issuer signature, and
one-use nonce through `verify_external_attestations`,
`verify_external_signature`, and `reserve_one_run`; inject its bounded host
adapter; and then call the same public service. `AuthorizedOneRun` and its prior
stages cannot be directly constructed. A restart must freshly repeat artifact
parsing and external signature checks, then use `restore_one_run` with the
canonical signed nonce-reservation receipt. This durable bearer still depends
on a shared host-owned nonce/run journal and adapter idempotency for global
single-effect enforcement. The preparation command emits inert PowerShell for
validation, round inspection, and status only.

The generated script invokes one absolute caller-authenticated client path and
rehashes that path immediately before each invocation. This detects substitution
visible at those checks, but PowerShell closes the hash input before launching the
path and does not provide handle-relative execution. Preventing a concurrent
hash-to-launch replacement therefore remains an immutable/read-only host-custody
and ACL requirement; the preparation receipt makes no stronger TOCTOU claim.
