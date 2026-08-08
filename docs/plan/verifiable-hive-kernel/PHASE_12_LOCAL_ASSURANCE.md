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

## Local packet receipt

[`phase12-54020b7.json`](../../../evidence/local_assurance/phase12-54020b7.json) binds
commit `54020b72d2fff602b355c99924b01b5cfb5d8ec5`, tree
`a54dcc7b58055be8850f4461191746fc94bd453d`, the retained two-task/two-repetition offline
benchmark, and named Phase 11, security, and recovery transcripts. Its report digest is
`sha256:af3f4600d0d64a250cfb78a2a016e2ba4e2cecf28a766785c393185f7ec59ab8`.

## Retained, content-addressed packet

[`phase12-9efe64b`](../../../evidence/local_assurance/phase12-9efe64b/) retains the raw
Phase 11 parity and rollback, security, and recovery transcripts beside its receipt
manifest. The validator verifies every transcript digest and the copied benchmark summary
before accepting the report. It binds commit `9efe64b80b4bf7b50c7bcf20e9aef5acb8fc55a7`,
tree `25839e21173160052189044ba4b6be16214ff8e7`, and report digest
`sha256:1f48147213ba98d0bd1c00f6b4da4df0679a2880a7394c1f9d8e41b670ebb064`.

The first attempt to materialize its benchmark beneath this repository hit Windows
`WinError 145` during failed-evidence cleanup. That failed attempt is retained under
`benchmark/` with its error receipt. A fresh external output root then completed the same
deterministic two-task/two-repetition run; its complete output is copied under
`benchmark-success/`. This remains local measurement only, not a completion or promotion
of Phase 12.
