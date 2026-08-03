# ADR-040: P1 Control-Plane Integrity Boundaries

- **Status:** Adapted; independently reviewed local implementation
- **Date:** 2026-08-02
- **Originating review:** independent principal review of release `version_1.1`
- **Prior decisions:** ADR-007, ADR-010, ADR-011, ADR-012, ADR-014
- **Capability maturity:** local, reversible, and fail-closed where evidence is absent

## Context

The review reproduced several control-plane gaps: acceptance criteria could be present
without a sealed criterion-specific check; risk labels did not constrain authority;
provider credentials could be sent over plaintext HTTP; queued work could omit a fixed
revision and defeat deduplication with a random mission identifier; and mutable durable
state could be adopted without verifying its local bindings.

## Court record

- **Advocate:** make the already-declared mission controls executable at every adapter
  boundary while preserving the existing local, reversible delivery model.
- **Cross-examiner:** reject controls that only add metadata, ensure every downstream
  Git and verification path receives the actual risk tier, and distinguish local
  integrity checks from cryptographic hostile-host authentication.
- **Expert testimony:** canonical JSON plus SHA-256 detects inconsistent local state;
  full Git object identifiers pin a reproducible source revision; HTTPS prevents sending
  configured model credentials over plaintext transport.
- **Judge disposition:** `adapt`, following separately identified Curator reproduction
  and Judge review. This ADR records the implementation boundary and its dissent; it
  is not a promotion or a production-security claim.

## Decision

1. Every sealed Curator check declares the exact acceptance criteria it covers. A blind
   seal fails when a criterion is uncovered or a check names an undeclared criterion.
2. Policy evaluates both required autonomy and an action-specific maximum autonomous
   risk. High-risk work cannot execute commands or modify a workspace; critical-risk
   work cannot begin repository access. The declared risk is passed through mission,
   Git, GitHub, sandbox, and delivery-verification paths.
3. Model providers accept only HTTPS base URLs without URL credentials, query strings,
   or fragments. HTTP responses are capped before parsing, including error bodies.
4. Durable mission configuration is canonical-digest-bound and checkpoint receipts are
   accepted only after a recorded effect start, schema validation, intent binding, and
   receipt-reference verification. Scheduler payloads are re-digested before leasing or
   mutating a job.
5. `enqueue` resolves a full local Git SHA before creating the job. It derives a bounded
   deterministic mission identifier from repository, objective, normalized criteria,
   backend, and pin, so equivalent work deduplicates. Workers dead-letter unpinned
   repository jobs before execution.

## Threats and controls

| Threat | Control | Residual |
|---|---|---|
| A success label bypasses an objective criterion | Complete criterion-to-check seal coverage | Superseded for repository delivery by ADR-041's typed command specification and receipt binding; adequacy of formalizing the original prose remains a separate judgment |
| High-risk work executes through a lower adapter | Risk propagated into sandbox, Git, GitHub, and verifier decisions | Direct callers may choose their own declared risk; authenticated authorization remains future work |
| Model credential crosses plaintext transport | HTTPS-only provider configuration | TLS endpoint authenticity still depends on the host trust store |
| Queued job runs a later repository HEAD | Enqueue-time full SHA pin | Repository locks and remote source custody remain deferred |
| Ordinary local mutation changes mission configuration or job payload | Canonical digest verification before use | A hostile user able to alter all local state can recompute digests; external signing is not implemented |
| Pre-created checkpoint receipt is adopted | Require durable effect start and validate receipt bindings | Receipt files are not cryptographically authenticated outside the local store boundary |

## Migration and rollback

Mission-store schema version 2 adds and backfills `config_digest` for version-1 local
stores. Existing checkpoint receipts remain readable when their stored content and
bindings validate. Existing queued repository jobs without a pin now fail closed and
dead-letter; they must be explicitly re-enqueued. Reverting this ADR's implementation
does not delete retained mission or scheduler data, but restores the prior weaker
runtime behavior and is therefore a rollback only for a local implementation defect.

## Verification

- `tests/test_curator.py`: missing and undeclared criterion coverage is rejected.
- `tests/test_model_provider.py`: plaintext/ambiguous provider URLs and oversized
  responses are rejected.
- `tests/test_policy_invariants.py`, `tests/test_mission.py`, and
  `tests/test_git_adapter.py`: risk ceilings reach mission and delivery execution.
- `tests/test_mission_store.py` and `tests/test_scheduler.py`: configuration, receipt,
  and payload mutation fail closed.
- `tests/test_cli_enqueue.py` and `tests/test_workers.py`: enqueue resolves pins,
  semantic duplicates share one job, and workers reject unpinned jobs.

## Limits and follow-up

ADR-041 now makes the selected executable predicate objectively verifiable for repository
delivery and records its independent `adapt` disposition; it does not establish that the
predicate faithfully formalizes the original human prose. ADR-046 separately adapts a
local opt-in, one-shot model-role recovery lane; it does not provide model-backed
repository-mission lifecycle resumption, provider idempotency, or authentication.
ADR-047 adapts an additive Python-injected repository-model recovery journal following
separate Curator and Judge review; it does not widen CLI, worker, delivery,
authentication, or isolation authority.
External or threshold receipt authentication, repository locking, hostile-code isolation,
production branch governance, and multi-host operation remain open P1/P2 work and must
not be represented as completed by this ADR.
