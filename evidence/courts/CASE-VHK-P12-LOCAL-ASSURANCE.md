# Case: VHK Phase 12 local assurance

## Claim

The local assurance packet can fail closed on incomplete post-migration evidence while
retaining deterministic benchmark, security, recovery, and route evidence without claiming
release, production, comparator superiority, signing, provider use, or independent review.

## Disposition boundary

This is a local measurement/adaptation case. The output is intentionally non-promoting and
hard-codes all release and promotion fields to false. G2-G8 and the retained blocker backlog
remain controlling for real-model, signing, retention, production, comparator, source, and
independent-human components.

## Required evidence

The final local packet must bind an exact committed candidate, Phase 11 route manifest and
parity/rollback digests, an offline `measurement-recorded` benchmark report, and named
passing security and recovery receipts. Missing or contradictory values are a failure, not a
reason to relax the packet.

## Local measurement receipt

`evidence/local_assurance/phase12-54020b7.json` has report digest
`sha256:af3f4600d0d64a250cfb78a2a016e2ba4e2cecf28a766785c393185f7ec59ab8`. It records
the existing offline benchmark run `p13-19f89e32e6980c82`, whose verdict is
`measurement-recorded`; it does not make a comparative quality or superiority claim.

### Procedural Curator reproduction

A separately prompted procedural Curator verified that the packet candidate commit/tree
match Git and that its scope is `local-deterministic` with every release, production,
provider, signing, and comparative-promotion flag false. It also reproduced the focused
enqueue and assurance tests: 6 passed in 1.512 seconds. The result remains local technical
evidence and does not close G2-G8 or create an authenticated independent review claim.

## Retained evidence repair

The earlier packet retained only receipt hashes. The later
`evidence/local_assurance/phase12-9efe64b/` packet retains the receipt bytes and an
explicit manifest. `verify_local_assurance_artifact` fails closed if any transcript or
the benchmark summary is unavailable, path-escaping, or digest-mismatched. Its report
digest is `sha256:1f48147213ba98d0bd1c00f6b4da4df0679a2880a7394c1f9d8e41b670ebb064`.
The retained failed Windows benchmark materialization and successful fresh-root rerun are
both preserved; neither supports a release, superiority, or independent-review claim.
