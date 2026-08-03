# ADR-048: Authenticated Repository-Source Mission Admission

- **Status:** Proposed implementation candidate; independent Curator and Judge review pending
- **Date:** 2026-08-03
- **Originating requirement:** P1 correctness hardening, authenticated repository source custody and locking
- **Prior decisions:** ADR-040, ADR-042, ADR-043, ADR-047
- **Capability maturity:** bounded, opt-in remote mission admission; no production authority or governance mutation

## Context

ADR-043 supplies a signed remote source-lock verifier at the `GitWorkspace` boundary.
That boundary was not reachable from `RepositoryMission`, which accepted only a local
worktree. Consequently, a repository mission could neither claim authenticated remote
source custody nor retain the exact lock that would need to be rechecked on resume and
delivery verification.

A Git commit SHA, tree SHA, local digest, successful clone, and durable SQLite row are
integrity or reproducibility observations. They do not authenticate a repository,
provider, owner, revision provenance, or source-custody authority. This tranche does
not change that distinction.

The external source-custody protocol specification and a production authority operating
record remain unavailable in this worktree. No content has been invented for either;
they remain blocking source-evidence obligations for any production promotion.

## Court record

- **Atomic claim:** A repository mission can admit an HTTPS remote source only after a
  separately controlled source-custody verifier authenticates a source lock bound to
  the exact mission/state, canonical repository URL, commit, tree, and asserted source
  identity; a local Git SHA alone cannot unlock that lane.
- **Advocate / Builder:** the candidate adds an opt-in remote `RepositoryMission`
  admission seam. It requires explicit mission identity, a durable `MissionStore`,
  durable keyset/source-lock provenance, and ADR-043 signed evidence before mission
  registration. The admitted evidence digest is included in the sealed mission
  configuration and source fingerprint.
- **Cross-examination:** reject a source lock supplied without a verifier, a verifier
  without durable provenance, a remote source without an explicit mission identity, a
  URL/pin/state mismatch, an unsigned resume, or a delivery verification that changes
  the authenticated source URL. Require every later materialization and delivery
  verification to pass the same evidence back through ADR-043 rather than trusting the
  cached configuration or Git object IDs.
- **Expert testimony:** ADR-042/ADR-043’s public-key/keyset boundary remains the only
  authentication mechanism used here. The candidate adds no signer, private key,
  provider API, network identity lookup, or claim that Git object identifiers confer
  identity.
- **Curator disposition:** pending. The focused acceptance suite is Builder evidence,
  not independent Curator reproduction.
- **Judge disposition:** pending. No `adopt`, production-readiness, or superiority
  conclusion is authorized until a separately identified Judge evaluates the retained
  candidate and Curator evidence.
- **Dissent:** a trusted source-custody authority can authenticate only its statement
  about upstream source identity. It does not prove code safety, licensing,
  commit/tag-signature validity, provider control, remote availability, or branch
  protection.

## Decision candidate

1. A remote `RepositoryMission` is recognized only for an explicit HTTPS URL and only
   with `source_lock`, `source_custody`, an explicit mission identity, and a durable
   mission journal. It fails closed before source materialization when any required
   item is absent. Local worktrees retain their existing, explicitly unauthenticated
   pin/reproducibility behavior.
2. Admission re-verifies ADR-043 evidence against the externally pinned key history
   and binds it to `MISSION_STATE:<mission-id>:1`. The mission stores the signed lock,
   attestation, and their evidence digest in the canonical configuration. The source
   fingerprint incorporates that evidence digest so a different source assertion cannot
   silently reuse the same durable mission configuration.
3. Every repository workspace materialization supplies the authenticated lock, verifier,
   durable-provenance requirement, mission ID, and state reference to `GitWorkspace`.
   The Git adapter continues to verify the signed lock before clone and its tree before
   and after detached checkout.
4. Delivery verification recognizes an authenticated-source manifest as a remote
   verification lane. It re-verifies the signed evidence, requires the caller’s base
   URL to canonically equal the signed URL, and supplies the same strict bindings to
   both fresh verification workspaces. A signed manifest cannot redirect verification
   from an operator-selected local/different remote source.
5. Durable resume reconstructs source evidence only from the sealed configuration and
   fails closed unless the caller injects the original class of source-custody verifier.
   The evidence digest is recomputed before reconstruction; no local auto-upgrade or
   fallback to a bare pin is permitted.

## Threats and controls

| Threat | Control | Residual / explicit non-claim |
|---|---|---|
| Remote SHA is presented as source authentication | Remote mission constructor rejects it without external signed source-lock evidence | Pin still gives reproducibility only |
| Source lock is replayed for another mission/state | Explicit mission identity and initial state are verified before registration, then again at materialization | Existing local clock/keyset freshness limits remain |
| Stored mission config swaps signed source data | The existing canonical configuration digest binds the evidence; resume recomputes source-evidence digest | A hostile host can deny service or roll back all local state absent external retention |
| Remote verification fetches from a different URL | Delivery verifier canonicalizes the caller’s URL and requires equality to the signed lock | DNS/TLS and authority upstream validation remain outside this code |
| Resume silently degrades to a pin | Authenticated-source config requires injected source verifier and signed evidence | Operator must retain/provide verifier configuration |
| Branch protection or governance is altered | No hosting API, branch policy, or governance file is called or changed | Existing governance posture is unchanged |

## Migration and rollback

- This is additive: existing local mission configurations remain local and
  unauthenticated. No local pin, lock file, or historic delivery is relabeled as
  authenticated.
- An authenticated remote mission must be newly admitted with a source lock that names
  its explicit mission ID and state version 1. Existing local missions cannot be
  migrated by adding a digest.
- Rollback removes the opt-in remote mission caller path but retains mission-store,
  keyset, and source-lock provenance. It cannot justify treating the mission as an
  authenticated local-pin run.

## Builder acceptance evidence

- `tests/test_authenticated_repository_source.py`: rejects a remote Git SHA without
  source custody; seals authenticated lock evidence into durable configuration; requires
  the verifier on resume; and verifies strict lock/verifier/mission/state propagation to
  Git materialization.
- `tests/test_source_custody.py`: retains the adversarial ADR-043 checks for signature
  tampering, replay, rotation/revocation, durable provenance, materialization state,
  tree mismatch, and delivery cross-binding.
- `ruff`, bytecode compilation, and `git diff --check` are required before an
  independent review request.

## Open court obligations

1. A separate Curator must reproduce the candidate tests, inspect the exact source and
   delivery cross-bindings, and record a distinct disposition.
2. A separate Judge must decide `adopt`, `adapt`, `defer`, `reject`, or `quarantine`
   after Curator evidence; this ADR deliberately does not self-approve.
3. Production promotion remains blocked on the unavailable source-custody protocol,
   authority operating evidence, external retention/fresh keyset supply, source
   ingestion/license evidence, commit/tag policy, hostile-code isolation, and the
   existing governance review path.
