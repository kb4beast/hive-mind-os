# ADR-090: Reject stale isolation attestations

Status: ADAPT for the scoped freshness repair, subject to integrated CI.

Source: the N18 fail-closed isolation requirement in AGENTS.md and
`docs/plan/whole-os-tournament-2026-09-13/NODES-LEARNING.md`. An independent
release audit reproduced `require_attested` accepting ENFORCED evidence whose
expiry was in 1970. No production execution was performed by that probe.

Both `admits_untrusted` and `require_attested` now check the current UTC time on
every call. Expiry equality rejects. A trusted host may pass an aware datetime
for deterministic testing; target data must not supply this clock. Constructor
validation rejects malformed or timezone-naive expiries. Valid expired records
remain loadable and retain their original digest for historical evidence.

This small repair was selected ahead of implementing external custody because
it closes a demonstrated local defect without inventing external authority.
Alternatives rejected: changing a fixture to a far-future date, checking only
at registration, or treating the ENFORCED enum as sufficient forever. The
existing pinned-image registry rule remains intact. No issued-at or maximum
lifetime policy is invented by this change.

Threats and limits: local clock errors can affect freshness. These functions
check structure/status/time only; a production broker must also authenticate
provenance, scope, revocation and probe bindings before every effect. The repair
does not implement that broker or grant permission to run untrusted code.

Tests cover malformed/naive time, invalid clocks, before/equal/after expiry,
offset-equivalent boundaries, repeated use of one immutable record, the default
clock, unavailable status and retained historical records. The unavailable
boundary fixture now uses a valid historical timestamp so it continues to test
status rejection instead of failing earlier at construction.

Migration: no serialized fields or digest algorithm change. Malformed legacy
records fail parsing and require a separately issued corrected record; expired
well-formed records remain inspectable. Rollback selects the prior implementation
only with untrusted execution disabled, retaining all records; returning to the
old helper must not restore permission to use stale attestations.

Builder assistance: Claude Haiku 4.5, session a60feb7a-19e3-4143-9ba8-72e0152c9592.
Root review corrected its missed direct helper path, incomplete clock tests and
inaccurate migration/rollback statements. This dissent is retained; no claim of
independent external authentication is made for model sessions.

Independent Curator `product_readiness_witness` reproduced the original stale
acceptance and checked 45 additional cases. Independent Judge `readiness_judge`
reproduced all 19 focused tests against the corrected candidate and issued ADAPT.
The dated closeout evidence retains both reviews and the original builder result;
the judge report SHA-256 is
`df51a247a001bc2cb5c468b8a032629f7e161792f92a9bdbfb79a56307672f60`.
This disposition covers local freshness enforcement only, with integrated CI
still required; N18 external attestation and production isolation remain open.
