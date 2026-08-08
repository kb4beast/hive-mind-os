# Verifiable Hive Kernel: Phase 12 local assurance

## Scope

Phase 12 supplies a deterministic local assurance packet for the architecture after a
Phase 11 migration. It binds a candidate commit/tree, one or more versioned Phase 11 route
records, the existing offline benchmark measurement report, and named parity, rollback,
security, and recovery receipts.

The packet is deliberately fail-closed. It rejects malformed or mismatched candidate
bindings, duplicate routes or receipts, missing Phase 11 parity/rollback evidence, missing
security or recovery evidence, non-passing tests, non-measurement benchmark verdicts, and a
benchmark judge identity that collides with a lane identity.

## Non-promoting result

Every generated packet has these immutable values:

- `scope: local-deterministic`
- `release_ready: false`
- `production_ready: false`
- `comparative_claim_authorized: false`
- `signed_attestation_present: false`
- `real_provider_used: false`

It reuses the offline benchmark harness, which retains failed and losing attempts and caps
its own verdict at `measurement-recorded`. The packet therefore measures local fixtures but
does not claim a release, superiority, production behavior, signing, external provider use,
or independent-human review.

## External gates retained

G2 (real-model access), G3 (signing), G4 (external retention), G5 (production pilot), G6
(comparator execution), G7 (source licensing), and G8 (authenticated independent-human
promotion) remain open. Those gates, plus the named release/production blockers in
`docs/plan/BLOCKERS.md`, are not defeatable by local tests or this packet.
