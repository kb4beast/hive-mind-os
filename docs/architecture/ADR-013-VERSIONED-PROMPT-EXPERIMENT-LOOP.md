# ADR-013: Versioned Prompt Experiment Loop

- **Status:** Proposed for P10 consolidated court review
- **Date:** 2026-07-28
- **Originating work order:** `docs/plan/P10_LEARNING_LOOP.md`
- **Prior decisions:** RECURSIVE_SELF_IMPROVEMENT_DOCKET, ADR-010-P05,
  ADR-012-P08
- **Capability maturity:** scripted and locally reproducible

## Context

The recursive-improvement gate already defined the constitutional burden for a
champion/challenger decision, but no operating path supplied it with a real artifact.
Role prompts were assembled inside `ModelBackend`, had no stable artifact identity, and
could not be promoted or rolled back without changing code. P05 fixture missions and P09
point-in-time episodes now provide bounded evaluation surfaces, while P08 requires the
evaluator to remain distinct from the candidate author and builder.

P10 therefore needs one operating-kernel seam: immutable prompt artifacts, prompt
provenance on model receipts, repeated evaluation through the existing gate, and atomic
champion selection. This decision does not authorize automatic challenger generation or
weaken any promotion burden.

## Court record

- **Advocate:** make role prompts the first real, reversible improvement artifact because
  they can be content-addressed without changing provider, policy, or mission contracts.
- **Cross-examiner:** require immutable storage, atomic pointer failure tests, hard
  guardrails, retained losing artifacts, author/evaluator separation, holdout ordering,
  and a rollback receipt.
- **Expert testimony:** P05 mission outcomes supply a deterministic fixture surface; P09
  supplies physically isolated, sealed episode records; the existing
  `RecursiveImprovementGate` supplies the only permitted promotion decision.
- **Judge:** reserved for the independent consolidated P10 review.

## Decision

1. Canonical UTF-8 prompt bytes are stored under their SHA-256 digest. A registered
   artifact is never rewritten or deleted.
2. Each role has one champion digest in a small JSON pointer document. Pointer publication
   uses a same-directory temporary file, flush, and `os.replace`; a failed replacement
   leaves the prior pointer valid.
3. Registration, promotion, quarantine, and rollback retain immutable records and
   append ledger events. Promotion binds the expected prior champion so a stale
   experiment fails closed.
4. The committed files under `prompts/` are generation zero. Without a registry,
   `ModelBackend` renders the byte-equivalent P02 prompt and preserves prior behavior.
   Every `model.call` records the effective prompt artifact digest.
5. `ExperimentRunner` binds the contract fingerprint, champion and challenger digests,
   surface, pinned episode identifiers, repetitions, metrics, artifacts, and identities.
   It delegates every verdict to `RecursiveImprovementGate`.
6. Task success is primary. Token cost and evidence completeness are hard guardrails.
   Only `KEEP` changes the champion pointer. `QUARANTINE` flags but retains the artifact;
   all other outcomes retain the challenger without promotion.
7. The scripted evaluator identity is `evaluator:scripted-harness` and must differ from
   author and builder identities. On PIT surfaces, a prior reveal event attributed to
   the author for a pinned episode sets `accessed_holdout` and therefore quarantines the
   experiment.
8. Challenger generation is not implemented. A caller must supply a distinct artifact.

## Threats and controls

| Threat | Control | Residual |
|---|---|---|
| Live champion is edited in place | Content addressing and create-only artifact writes | Local filesystem administrators can tamper; digest verification then fails closed |
| Crash leaves a dangling champion | Flush plus atomic replace; pointer reads verify artifact presence | Cross-host replication is outside P10 |
| Stale experiment overwrites newer champion | Promotion requires the expected current digest | Multi-process advisory locking is deferred |
| Candidate judges itself | Gate quarantines evaluator equal to author or builder | Authenticated external identities remain deferred |
| Single lucky run promotes | Contract enforces repeated samples and a noise floor | Scripted fixtures are not production outcome evidence |
| Improvement hides cost or evidence loss | Token and evidence-completeness hard guardrails | Provider token reports remain provider-dependent |
| Author sees protected target | Ledger ordering check turns prior author reveal into holdout access | External knowledge and unauthenticated identity claims remain explicit caveats |
| Losing evidence disappears | All artifacts and verdict records are retained | Long-term evidence retention belongs to P11 |

## Migration

Existing callers need no change: omitting `prompt_registry` keeps the generation-zero
prompt path. Registry-aware callers bootstrap the committed `prompts/` directory into a
local state root and then pass that registry to `ModelBackend`. No existing audit schema,
source docket, policy behavior, or mission contract is changed.

## Rollback

Revert the P10 delivery to remove the runtime integration. Local registry roots are user
data and remain untouched. Within P10, `rollback_champion(role, digest)` atomically
restores a retained earlier artifact and records a new ledger event; it deletes nothing.

## Limits

This decision establishes only a scripted local prompt-learning loop. It does not claim
production readiness, superiority, complete source coverage, authenticated independence,
hostile-code isolation, or automatic recursive improvement. Real provider evidence
remains tracked by `B-OPS-03`; durable operations and retention remain P11 obligations.
