# P19 — Multi-Comparator Benchmark Court

Status: pending in `01_POST_P13_OVERVIEW.md` | Depends on: P14, P15, P17 | Unlocks: P20 and narrowly scoped superiority claims

## 1. Objective

Address `B-OPS-05` by extending P13 into a reproducible, independently judged court with
multiple pinned comparators and task families, equalized authority and budgets, safety floors,
statistical uncertainty, and complete raw-result retention.

## 2. Required reading

1. `docs/plan/01_POST_P13_OVERVIEW.md`
2. `docs/plan/P13_BENCHMARK_COURT_MVP.md`
3. `benchmarks/founding-comparator-suite.json`
4. `docs/architecture/HARDENED_VISION_CONTRACT.md` (`Benchmark position`)
5. `AGENTS.md` (`superiority` burden)
6. `docs/plan/BLOCKERS.md` (`B-OPS-05`)

## 3. Prerequisites and authority

- Branch: `phase/P19-multi-comparator-court`.
- P14 proves the real capability under test; P15 authenticates receipts; P17 isolates
  untrusted comparator workloads.
- Each comparator has an exact version/image/commit, license, configuration, tool contract,
  and permitted-use record.
- Fix hypotheses, primary metrics, safety floors, corpus, seeds, budgets, repetition count,
  exclusions, and stopping rules before revealing results.

## 4. Scope and design constraints

- Use at least three materially distinct pinned comparators and at least two representative
  task families before considering any broad comparative claim.
- Equalize model access, tool capabilities, network, compute, time, token/cost budget, retry
  policy, and human intervention, or disclose and adjudicate every unavoidable asymmetry.
- Keep success checks held out and prevent target/future leakage.
- Retain every raw attempt, failure, losing result, budget receipt, and environment digest.
- Report uncertainty, per-family results, safety failures, and practical effect sizes; do
  not hide behind one aggregate score.
- Use independent lane operators, Curator, expert witnesses, Judge, and Appeals Judge where
  the claim affects a champion.
- Claim text must be machine-bound to the qualifying court artifact and exact tested scope.

## 5. Deliverables

- Comparator/corpus intake records with provenance and licenses.
- Extended harness, safety floors, power/repetition rationale, and claim-binding validator.
- Raw results, environment manifests, generated report, P19 audit, court and appeal records.
- Updated claim guard that permits only a validated court-bound statement.

## 6. Required tests

Cover pin/license rejection, unequal-budget rejection, hidden-check leakage, environment drift,
missing/losing-result detection, safety-floor failure, insufficient comparators/families,
underpowered/invalid statistics, Judge identity collision, tampered court artifacts, scope-
broadened claim text, and exact reproducibility from retained inputs.

## 7. Exit criteria

- Full deterministic gates pass.
- All comparators and corpora are pinned, licensed, and reproducible.
- Equalized repeated held-out runs complete with raw and losing evidence.
- Safety floors pass and uncertainty supports the exact predeclared claim.
- Independent Curator and expert witnesses reproduce the analysis.
- A distinct Judge issues a qualifying disposition; Orchestrator confirms scope and rollback.
- If any condition fails, the outcome is measurement only and superiority language remains
  prohibited.

## 8. Evidence, rollback, and forbidden shortcuts

Retain preregistration, pins, licenses, budgets, raw attempts, losing results, statistics,
environment digests, court/appeal records, audit, and dissent. Rollback restores the strict
P13 no-claim guard and preserves all measurements.

Do not cherry-pick tasks, tune after reveal, omit losses, compare unequal authority, use one
comparator/family, infer production value from benchmark success, or generalize beyond the
court-bound statement.

