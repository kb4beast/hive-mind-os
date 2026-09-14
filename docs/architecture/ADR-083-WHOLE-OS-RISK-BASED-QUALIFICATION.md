# ADR-083: Risk-based checks, content-bound reuse, and independent qualification

Date: 2026-09-14  
Status: proposed by N01 Architect/Advocate; independent Examiner, Witness, and Judge disposition pending

## Requirements and sources

Requirements: R03, R05, R06, R10, R14, R15, R18. Sources: `OWNER-IMPLEMENTATION-01`, `HANDOFF-01`, `LOCAL-01`, `GOV-ADR-077`, `GOV-ADR-078`, RUNBOOK C04/C09, and the accepted N00 classification of task-reuse, cache, verification, and sandbox seams.

## Decision proposed by the Advocate

Schedule checks when claim inputs or trust purpose change. Cache keys bind candidate, tests, configuration, dependencies, platform, adapter, isolation, environment, policy, tenant, reviewer domain, and freshness. Builder observations never become Curator judgments by relabeling. Exact candidate qualification, integration CI, publication observation, domain runtime evidence, and promotion evaluation remain distinct purposes. Missing dependency coverage or runtime capability is a miss/incomplete obligation, not a pass.

Alternative considered: run the full suite after every edit, which wastes resources without adding independent purpose; rejected converse shortcuts include filename-only selection, branch-name caches, compile-only-as-runtime, and self-verification.

## Court record and pending independent work

Advocate argument: content/purpose binding reduces demonstrably duplicate work while keeping high-burden checks at the boundaries whose claims they support.

Examiner objection to investigate: dependency impact analysis can be incomplete, environments can contain nondeterministic state, and cache reuse can silently preserve a false pass. No independent N01 Examiner conclusion is asserted.

Expert testimony requested: an independent Curator/Optimizer should reproduce invalidation matrices and quantify overhead/savings without counting required independent CI as duplication.

Independent disposition requested: a Judge separate from the Architect/Builder must disposition correctness and any efficiency claim. Speed, cost, noninferiority, Roblox runtime, and production readiness remain deferred to N27/N30/N32.

## Tests, migration, and rollback

N01 rejects missing outputs, lost requirements, altered standards, unknown routes, and unauthorized effects. N06/N14/N27/N29 later own exact cache/invalidation/runtime/adversarial tests. Migration reads old receipts only under their old purpose/version and defaults unknown dependencies to a miss. Rollback disables new cache reads and executes checks; historical successes/failures stay retained and no acceptance criterion is weakened.
