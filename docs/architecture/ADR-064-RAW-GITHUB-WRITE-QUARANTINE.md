# ADR-064: Raw GitHub write quarantine and effect-bound push execution

## Status

Implemented local candidate; independent Curator and Judge review are pending. This ADR
narrows the raw-GitHub residual recorded by ADR-063. It neither provisions nor substitutes
for the external root required for real remote authority.

## Context

ADR-063 retired direct mission delivery, but the production
`WorkspacePushExecutor` still delegated to `GitHubClient.push_branch`. That meant the
controlled adapter reached a legacy high-level write API that could also be called directly.
The public `GitHubClient` surface also retained direct push, draft-PR, and composite-delivery
methods.

The court record is the retained ADR-063 residual plus the reproduced call path. The advocate
favoured reusing the legacy client for durable receipts; the cross-examiner showed that reuse
preserved a parallel raw authority path. The selected design keeps the established workspace
and receipt mechanics but makes the effect gateway the only production route to a push.

## Decision

- `GitHubClient.push_branch`, `open_draft_pr`, and `deliver` are quarantined. Each raises
  `GitHubRawWriteQuarantined` before reading credentials, running Git, parsing delivery files,
  or issuing HTTP.
- `WorkspacePushExecutor` no longer depends on `GitHubClient`. It requires an explicit remote,
  reads the credential only after admission, invokes `GitWorkspace.push_branch` directly, and
  accepts no fallback branch.
- The executor requires the active `github-push` effect invocation that an
  `EffectGateway` or `DurableEffectOutbox` installs only after validating the issued capability.
  Direct executor calls fail before Git I/O.
- The executor receives the immutable `DeliveryGrant` and re-checks grant action, branch scope,
  and (for production HTTPS remotes) the exact `github.com/<owner>/<repository>.git` target.
- Controlled-delivery host declarations include both the REST API host and the Git push host, so
  an envelope that permits only `api.github.com` cannot silently permit a GitHub push.

Read-only check/protection observations remain on `GitHubClient`; they do not create a remote
effect. Historical receipt/recovery mechanics remain exercised by a test-only subclass and do
not restore a package-consumer bypass.

## Threats and limits

| Threat | Control | Retained limit |
| --- | --- | --- |
| Raw client invocation | Public write entry points reject before transport | Python private implementation code is not a cryptographic boundary |
| Direct workspace executor call | Active effect-invocation guard | A caller that can alter process code is outside this local control |
| Wrong Git remote | Grant/repository comparison and host allowlist | Local test remotes are explicitly test-only fixtures |
| Grant reused in a second gateway | Grant action and branch are rechecked in executor | Current grant anchoring is process-local until ROOT-3000 supplies external custody |
| Lost execution marker | Marker is scoped around the adapter call and reset in `finally` | It is not an external root or signed receipt |

## Acceptance evidence

The focused command is:

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_delivery_grants tests.test_hive_cortex_effects tests.test_hive_cortex_delivery tests.test_github_adapter -v
```

It includes raw-write no-I/O probes, direct-executor denial, host declaration and allowlist
checks, grant-target checks, controlled local-push execution, durable effect coverage, and
existing GitHub response/recovery regressions. The exact candidate, full CI, independent
Curator disposition, and rollback receipt remain mandatory before `RAW-GITHUB-2070` can be
adopted.

## Rollback

Revert this ADR's implementation commit as one atomic candidate. Do not restore raw writes in
place; any successor must retain this negative evidence, use an authority-bound adapter, and
receive a new independent disposition.
