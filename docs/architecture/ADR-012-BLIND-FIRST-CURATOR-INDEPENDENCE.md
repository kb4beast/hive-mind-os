# ADR-012: Blind-First Curator Independence

- **Status:** Proposed for independent P08 court review
- **Date:** 2026-07-27
- **Case:** `CASE-P08-CURATOR-INDEPENDENCE`
- **Originating work order:** `docs/plan/P08_CURATOR_INDEPENDENCE.md`
- **Prior decisions:** ADR-003, ADR-007, ADR-010, ADR-011
- **Capability maturity:** locally implemented; authenticated external identities deferred

## Context

P05 gave the Curator a separate candidate workspace and removed Builder results from its
ordinary context. Those orchestration choices were necessary but insufficient: a future
caller could attribute verification to the Builder, inject a Builder receipt or rationale
into the Curator context, or let the Curator see the candidate before deciding what would
prove the objective. The founding contract classifies self-review presented as independent
review as a hard failure.

P08 therefore changes the mission result-acceptance boundary. The Curator must first receive
only the objective, acceptance criteria, and base workspace, produce argv-form checks, and
seal their canonical digest in the append-only ledger. Candidate materialization and
reproduction follow the seal. The mission checks recorded context evidence and identity at
both boundaries rather than trusting the call graph.

## Court record

- **Advocate:** structural checks are a small deterministic control that prevents a broad
  class of anchoring and self-approval failures without requiring a second vendor.
- **Cross-examiner:** inject Builder digests and rationale, attribute the Curator result to
  the Builder, reorder seal and head access, add a late check, weaken a test, and leave an
  unevaluated checklist item.
- **Expert evidence:** deterministic tests reproduce each counterexample and exercise both
  scripted and provider-backed context receipts.
- **Judge:** a separately identified Curator and Judge must inspect the exact committed
  candidate. This Builder proposal cannot adopt itself.

No external source or third-party code is introduced by this decision. P12 retains open
source-ingestion and license obligations.

## Decision

1. A Curator review begins with a blind input containing the objective, acceptance
   criteria, and the base-SHA workspace. Prior-role results, Builder rationale, Builder
   receipts, candidate diff, and candidate head are excluded.
2. Acceptance checks are nonempty argv vectors with explicit expected process outcomes.
   Their canonical JSON digest and full check inventory are appended as
   `curator.acceptance.sealed` before any candidate-head materialization.
3. A late check, mutated sealed inventory, absent seal, or seal sequence at or after
   candidate-head access raises `ContaminationError`.
4. Verification-class identity must differ from the acting Builder identity. Recorded
   context manifests must contain no Builder role, Builder receipt digest, or Builder
   rationale. Violations append `contaminated-verification` and fail the mission.
5. Reproduction runs the sealed checks plus the Explorer-sealed repository command in a
   fresh candidate workspace. Only observed command receipts and delivery verification
   count.
6. The versioned adversarial checklist records `pass`, `fail`, or `not-evaluated`.
   Any `fail` rejects; `not-evaluated` is non-blocking but can never be rendered as pass.
7. Test weakening compares assertion and test-function counts and also retains normalized
   assertion signatures, so replacing an original assertion with a candidate-serving
   assertion is a reduction even when the raw count is unchanged.
8. Model configuration accepts role-scoped environment suffixes such as
   `HIVE_MIND_MODEL_MODEL__CURATOR`. Model-call and mission context receipts record the
   effective provider and model, and explicitly distinguish shared configuration from a
   real override.

## Threats and controls

| Threat | Control | Residual |
|---|---|---|
| Curator anchors on Builder claims | Blind model turn and empty prior-result context before the seal | The Curator still knows the objective and base repository |
| Orchestrator injects Builder evidence | Gate evaluates recorded model/scripted manifests against recorded Builder digests and rationale | Cryptographic external agent identity is deferred |
| Builder verifies its own result | Acting and verifying identity inequality is mandatory | Current identities are process-level role identifiers |
| Checks change after candidate access | Canonical digest is recomputed before reproduction and ordering is ledger-derived | Durable provider-turn replay remains later work |
| Test is edited to bless broken behavior | Raw function/assertion deltas plus retained assertion signatures | Heuristic is not a complete semantic test analyzer |
| Missing scanner silently passes | Tri-state checklist records `not-evaluated` | SAST and license classification are explicitly out of P08 scope |
| Same model is presented as diverse | Receipts mark equal effective configurations as `shared` | Model/provider diversity is recommended, not required |

## Acceptance evidence

- Seal ordering and late-check mutation regressions pass.
- The P05 sabotage fixture fails its sealed original criterion and the retained-assertion
  heuristic.
- Builder-receipt injection and Builder-attributed verification fail with a
  `contaminated-verification` event.
- The checklist preserves `not-evaluated` and derives the verdict without converting it to
  pass.
- Role-scoped provider configuration appears in model-call receipts; absent differences
  are explicitly recorded as shared.
- The scripted golden mission succeeds with blind-seal, reproduction, and checklist
  events, while the sabotage mission remains unpublished.
- Full tests, Ruff, Pyright (or an explicitly recorded unavailable executable), the P08
  post-commit audit, and independent Curator/Judge review remain required before adoption.

## Rollback

Revert the P08 implementation and this proposed ADR before later phases depend on its
handoff. P05's simpler workspace separation remains available. Preserve contamination
events, rejected sabotage evidence, this proposal, and later dissent; do not delete or
rewrite them during rollback.

## Deferred limits and ownership

- Independent Curator and Judge identities own final disposition of this proposal.
- P11 owns durable distributed worker identity, scheduling, and operational projection.
- P12 owns source ingestion, external-license classification, and unresolved provenance.
- P13 owns benchmark judges and comparator courts.
- B-OPS-06 owns hard hostile-code filesystem and network isolation.

This decision does not claim authenticated human identity, provider diversity, complete
security scanning, complete license evaluation, production readiness, or superiority.
