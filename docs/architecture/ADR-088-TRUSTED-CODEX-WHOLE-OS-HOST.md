# ADR-088: Trusted local Codex host for WholeOSService

## Decision

Adopt a repository-owned PowerShell/Python launcher for the first concrete
`WholeOSService` deployment host. The launcher admits one exact clean `codex/`
checkout, resolves the native installed Codex executable through the existing local
worker adapter, hashes and probes that executable, and stores its sealed service
configuration and evidence outside the target repository. It obtains a fresh
read-only Curator receipt before registering the host factory in the service process.

The registered factory composes the existing configured mission bindings,
`WholeOSCompositionHost`, backlog discovery, bounded builder session, real
`CodexLocalWorker`, candidate qualification, local-only delivery result, scoped
learning, and terminal assessment. The bootstrap mission changes no repository
bytes. It proves the installed non-interactive runtime and durable composition path,
not autonomous PR publication or production isolation.

## Evidence and authority boundaries

The public service JSON remains inert and contains no imports, commands, callbacks,
credential values, secret names, or tokens. Codex authentication remains in the
user-owned Codex session store and is available only to the spawned native process.
The admitted profile grants `local_build` but no `code_pr`, `learning_export`, or
`deployment` capability. The delivery adapter therefore retains a local artifact
receipt and cannot publish.

A complete startup receipt requires a passing copied-worktree focused verification,
one fresh read-only Curator Codex session, one distinct fresh read-only Builder Codex
session executed through `WholeOSService`, unchanged Git HEAD/tree/status, and a
terminal service observation. Synthetic unit fixtures test the protocol but are
never accepted by the real launcher as startup evidence.

## Recovery and rollback

The service configuration is content-addressed by checkout, Codex binary, authority,
and N28 contract identities. Durable queue state is scoped to that seal. Restarting
the launcher reconstructs the same bindings and lets `WholeOSService` reconcile its
existing receipts. Append-only attempt receipts remain under the external state
root; only `startup-current.json` is replaced as a convenience pointer.

Rollback selects the prior repository commit and its separate content-addressed
state. No repository file is reverted by the startup mission, no remote effect is
issued, and retained evidence is not deleted.

## Verification

`tests/test_whole_os_codex_host.py` proves the closed service document, exact factory
registration, real service scheduling seam, read-only worker scope, external state,
and fail-closed dirty-worktree behavior. The PowerShell pipeline test parses and
inspects the trusted launcher. Real qualification additionally runs the launcher in
a fresh process and checks the persisted non-synthetic startup receipt.
