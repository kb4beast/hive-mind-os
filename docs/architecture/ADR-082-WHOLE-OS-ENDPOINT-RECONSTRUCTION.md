# ADR-082: Endpoint reconstruction alongside strict point-in-time replay

Date: 2026-09-14
Status: proposed by N01 Architect/Advocate; independent Cross-Examiner returned ADAPT; Witness and Judge pending

## Requirements and sources

Requirements: R09, R12, R13, R14, R18. Sources: `OWNER-ORIGINAL-01`, `OWNER-IMPLEMENTATION-01`, `HANDOFF-01`, `LOCAL-01`, EX06, EX07, RUNBOOK C08/C09, and `GOV-VISION-01`. Comparator rights and raw-source archives remain open N00 obligations.

## Decision proposed by the Advocate

Add `endpoint_reconstruction` as a distinct episode mode. A learner receives only the admitted first snapshot and classified README/owner brief. Evaluator custody retains final source, hidden checks, and reference behavior until the candidate is sealed. Keep `strict_pit` unchanged for historical prediction. Split repository families into exact `training|development|promotion_holdout` partitions; reveal retires an episode from fresh holdout use. Grade functional behavior, security, and runtime evidence rather than reference-tree similarity.

Alternative considered: expose ancestor history or infer missing intermediate development. That changes the task and contaminates blind evaluation. Another rejected alternative is exact-tree copying as the success oracle; it can reproduce defects and penalize valid independent structure.

## Court record and pending independent work

Advocate argument: explicit modes preserve PIT truth while implementing the owner's endpoint examples with testable custody and functional outcomes.

Examiner objection to investigate: public-model pretraining, dependency caches, Git alternates, final README clues, and family overlap may still contaminate results; final commits may themselves be unhealthy. The independent `N01_EXAMINER_REVIEW.md` at `78d0f32bfb6b47912e6d06ae33ed94d7647cf2d4` returned ADAPT; CE-05 preserves these learning and production claims as deferred.

Expert testimony requested: an evaluation/PIT expert should inspect seal timing, visible Git objects, family splits, reference health, and reveal retirement.

Independent disposition requested: a separate Judge must determine whether the exact custody and grading boundaries are adequate; no learning lift is adopted by this proposal.

## Tests, migration, and rollback

N22–N24/N29 own package, leakage, seal, reference-health, and functional-grade tests. Migration adds a new mode/schema without reinterpreting historical PIT episodes. Rollback revokes endpoint package admission and quarantines contaminated scores; original exhibits and strict-PIT receipts remain immutable.
