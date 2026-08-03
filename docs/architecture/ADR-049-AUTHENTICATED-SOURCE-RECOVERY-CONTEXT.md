# ADR-049: Authenticated Source Context in Durable Workspace Recovery

- **Status:** Proposed implementation candidate; independent Curator and Judge review pending
- **Date:** 2026-08-03
- **Originating requirement:** P1 correctness hardening after ADR-048
- **Prior decisions:** ADR-043, ADR-047, ADR-048
- **Capability maturity:** bounded durable-recovery correction; no new authority

## Context

ADR-048 seals signed source-lock evidence into an authenticated remote mission and
requires the verifier when that mission resumes.  Its durable workspace rehydration path
recreated a `GitWorkspace` from a reconciled local directory but discarded the already
revalidated lock and attestation.  A resumed Builder workspace could therefore create a
delivery manifest without the `source_custody` record carried by the original workspace.
That is a provenance regression, even though the outer mission constructor rechecked the
signed lock before reopening the workspace.

This correction does not authenticate the local workspace, prove that a signer is a
repository provider, or authorize any remote, provider, delivery, governance, or
isolation capability.  The external source-custody protocol specification remains
unavailable and is not invented here.

## Court record

- **Atomic claim:** a recovered authenticated-source workspace preserves the exact sealed
  source-lock evidence only when its recovered Git mission ID and state reference still
  match the signed lock; otherwise recovery fails before the adapter is rebuilt.
- **Advocate / Builder:** pass the lock and evidence already verified by the resumed
  `RepositoryMission` into `reopen_workspace`, retaining them in the reconstructed
  adapter so any later delivery emits the same source-custody manifest evidence.
- **Cross-examination:** reject a half-present lock/evidence pair, a substituted
  evidence lock, or a checkpoint-supplied Git mission identity/state that differs from
  the signed binding.  Do not infer remote authority from the recovered directory.
- **Expert testimony:** ADR-043 verification remains the authentication mechanism;
  this change merely preserves its already admitted immutable context through the
  ADR-047 reconstruction boundary.
- **Curator disposition:** pending. Focused tests are Builder evidence only.
- **Judge disposition:** pending. No adoption, production, or superiority conclusion is
  authorized by this record.

## Decision candidate

1. `reopen_workspace` accepts source-lock context only as an exact lock/evidence pair.
   It rejects non-identical lock documents and requires their mission/state bindings to
   equal the recovered Git mission identity and `MISSION_STATE:<mission-id>:1`.
2. The authenticated `RepositoryMission` recovery path passes its sealed, reverified
   context into that function. Local legacy workspaces continue with no source context.
3. The reconstructed `GitWorkspace` retains the lock, evidence, and bound state reference
   used by its original materialization. A subsequent reversible delivery therefore
   preserves the evidence record rather than silently downgrading its manifest.

## Migration and rollback

This is additive and schema-free. Existing local workspaces remain local. An active
authenticated mission with an inconsistent recovered checkpoint now stops with a
reconciliation error; it must be rematerialized under the existing ADR-048 source lock.
Rollback removes the propagation code but retains all sealed mission/source evidence; it
must not relabel a recovered manifest as authenticated.

## Builder acceptance evidence

- `tests/test_authenticated_repository_source.py` reopens a committed workspace with
  sealed evidence and confirms the recovered delivery manifest retains it.
- The same focused test rejects a source lock whose mission/state does not match the
  recovered workspace identity before filesystem reconstruction.

## Open court obligations

Independent Curator and Judge review remain required. External retention, signer and
provider authentication, source safety/licensing, hostile-code isolation, credential
mediation, and production authority remain outside this tranche.
