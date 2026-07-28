# P13 — Benchmark Court MVP (One Comparator, One Family, No Claims)

Status: tracked in `00_OVERVIEW.md` | Depends on: P05 | Unlocks: honest measurement; the path toward any future superiority court

## 1. Objective

Stand up the smallest honest benchmark court: one benchmark family (repository
issue-to-verified-delivery on a pinned local task corpus), Hive Mind OS versus one pinned
comparator baseline, equal budgets, repeated runs, raw results with bootstrap confidence
intervals, an independent judge identity issuing the verdict record — and an explicit,
tested prohibition on superiority claims, because a single-comparator, single-family court
cannot support one.

## 2. Rationale

"Stronger than X" is the highest burden in the courtroom and requires multiple pinned
comparators, safety floors, and statistical uncertainty. None of that is buildable in one
phase — but the *harness* that makes any of it possible is, and building it early forces
the measurement discipline (equal budgets, raw retention, losing-case preservation) into
the system while it is still small. The MVP deliberately claims nothing: its output is
honest measurement infrastructure plus a first result set, and a machine-checked guard
that the repository does not convert measurements into marketing.

## 3. Required reading

1. `docs/plan/00_OVERVIEW.md`
2. `docs/architecture/CONGLOMERATED_SYSTEM.md` § "Assurance and benchmark plane"
3. `AGENTS.md` courtroom rule (burdens; superiority requirements)
4. `src/hive_mind_os/mission.py`, `src/hive_mind_os/autonomy.py` (budgets),
   `tests/fixtures/fixture_repo.py` (task-corpus building blocks)
5. `src/hive_mind_os/courtroom.py` (verdict records, identities)

## 4. Prerequisite verification

```bash
python -m pytest -q tests/test_mission.py    # P05 green
```

## 5. Scope

In scope:

- A pinned task corpus: ≥5 deterministic fixture repositories, each with a defect, a
  hidden success check, and a task manifest (objective text, budget, allowed backend).
- Two lanes: `hive-mind` (the P05 pipeline) and `baseline` (a pinned scripted naive
  agent: single-shot patch attempt without roles/verification — implemented in-repo so
  it is fully pinned and offline).
- The harness: equal-budget enforcement, K repetitions per task per lane, raw JSONL
  results, bootstrap CIs (stdlib `random` with fixed seed), losing-case retention.
- A judge verdict record binding harness digest, corpus digest, lane digests, and
  results — with disposition capped below superiority.
- `docs/benchmarks/RESULTS.md` honest-report template + first filled report.
- A claim guard test.

Non-goals:

- No external comparator systems (installing pinned Operator OS/AIOS/OpenHands is the
  full Stage-7 court's job; the MVP's comparator is the in-repo baseline). No model-lane
  benchmarking in CI (scripted lanes only; model lanes runnable manually). No public
  publishing, no README badges, no cross-repo corpora, no safety-floor families yet.

## 6. Design constraints

- **Pinning.** The corpus builder is deterministic (fixed dates/SHAs like P04); the
  harness records: corpus digest (over all task manifests + repo tree digests), code
  digest (`git rev-parse HEAD` of this repo), lane configuration digests, budget
  parameters, seed.
- **Hidden success checks.** Each task's success check (a command + expected outcome)
  lives outside the workspace given to either lane (the harness runs it after the lane
  finishes, P09-style separation-lite); lanes see only the objective text and acceptance
  criteria.
- **Equal budgets.** Both lanes receive identical `AutonomyBudget` parameters; the
  harness asserts consumed ≤ issued and records consumption; a lane that exceeds budget
  scores the task as failed (fail closed, recorded).
- **Raw retention.** Every attempt (success or failure) keeps: mission/lane report,
  receipts index, success-check output, budget consumption — as JSONL under
  `evidence/benchmarks/<run-id>/`. Losing and failing cases are retained with the same
  fidelity as winning ones.
- **Statistics.** Per lane: success rate with a seeded bootstrap 95% CI; per-task
  breakdown. No aggregate weighted "score" — the MVP reports rates and intervals only.
- **Judge identity.** The verdict record is issued under a court identity distinct from
  the identities that ran the lanes (P08 pattern); it binds the digests above and
  carries disposition `measurement-recorded` — a value that the courtroom cannot confuse
  with a superiority adjudication.
- **Claim guard.** A test greps `README.md` and `docs/` for superiority-adjacent claims
  tied to these results (patterns like "outperforms", "beats", "stronger than" adjacent
  to "benchmark"/comparator names) and fails on every match. P13 cannot produce a
  qualifying superiority verdict, so no textual reference can bypass the guard. A later
  multi-comparator phase may replace this prohibition only with fail-closed resolution
  and validation of a genuine court artifact. Crude is fine; the point is a tripwire
  plus the recorded norm.

## 7. Deliverables

New files:

- `benchmarks/corpus.py` — deterministic task-corpus builder (tasks as code, not
  committed repos).
- `benchmarks/harness.py` — lane runner, budget equality, success checks, JSONL raw
  results, bootstrap stats, verdict record emission.
- `benchmarks/baseline_agent.py` — the pinned naive comparator lane.
- `tests/test_benchmark_harness.py`.
- `docs/benchmarks/RESULTS.md` — template + first scripted-lane results.

Modified files:

- `src/hive_mind_os/cli.py` — `hive-mind benchmark run --lanes hive,baseline
  --repetitions K --seed S --output evidence/benchmarks/`.

## 8. Implementation steps

1. Verify prerequisites; branch `phase/P13-benchmark-mvp`.
2. Build the corpus: 5+ tasks spanning: failing test fix, off-by-one defect with green
   tests (hidden check catches it), missing-edge-case defect, doc/code drift task,
   dependency-free refactor with behavior lock. Each deterministic with a hidden check.
3. Implement the baseline agent (single-shot scripted patch attempt per task — it should
   legitimately win some and lose some against the fixture set; tune the corpus so
   neither lane is at 0% or 100%, or the statistics demonstrate nothing).
4. Implement the harness: lanes → repetitions → raw JSONL → stats → verdict record.
5. Wire budget equality assertions and the fail-closed overspend path.
6. First full run (scripted lanes, seeded): commit raw results + filled RESULTS.md.
7. Add the claim-guard test.
8. Gates; audit `evidence/audits/P13-post.json`; status updates; completion record.

## 9. Required tests

`tests/test_benchmark_harness.py`:

1. Corpus determinism: two builds → identical corpus digest.
2. Hidden checks are invisible to lanes: workspace trees contain no success-check
   files/commands (assert on materialized tree file lists).
3. Budget equality: lanes receive identical budget parameters; an overspending lane
   (rigged) records task failure, not partial credit.
4. Raw retention: failed attempts produce the same artifact set as successes.
5. Stats: bootstrap CI is deterministic under the seed; rates match hand-computed values
   on a rigged small result set.
6. Verdict record: binds corpus/code/lane digests; disposition is
   `measurement-recorded`; judge identity differs from lane identities; a superiority
   disposition from this harness is impossible (constructor rejects it).
7. Claim guard: planting "Hive Mind OS outperforms the baseline benchmark" in a docs
   file makes the guard fail, and adding an arbitrary `superiority-verdict:` marker
   cannot bypass it (use tmp copy or fixture injection — do not commit the violation).
8. End-to-end: `benchmark run` on a 2-task subset with K=2 completes offline in CI
   within reasonable time (mark the full corpus run as the manual/exit path if CI time
   is a concern; the subset proves the machinery).

## 10. Exit criteria

```bash
python -m pytest -q tests/test_benchmark_harness.py   # pass
python -m pytest -q && python -m ruff check src tests && pyright   # clean
hive-mind benchmark run --lanes hive,baseline --repetitions 3 --seed 7 --output evidence/benchmarks/   # full corpus, completes offline
test -f docs/benchmarks/RESULTS.md && grep -q "measurement-recorded" docs/benchmarks/RESULTS.md
```

## 11. Evidence

- `evidence/benchmarks/<run-id>/` raw JSONL + verdict record committed for the first
  full run; `evidence/audits/P13-post.json` committed.

## 12. Rollback

Revert the branch. Benchmark evidence already recorded is append-only history.

## 13. Handoff

Later phases may assume: a working, pinned, budget-equal benchmark harness with raw
retention and honest reporting; adding a real external comparator or a new family is an
extension of `benchmarks/`, not a new design; superiority remains impossible to claim
until a full multi-comparator court exists.

## 14. Forbidden shortcuts

- No cherry-picked result reporting; RESULTS.md is generated from the raw JSONL, not
  hand-written numbers.
- No corpus tuning *after* seeing results to flatter a lane (corpus changes invalidate
  prior runs — new corpus digest, new run, both retained).
- No superiority language anywhere, including commit messages and the completion record.
- No CI-time network or model lanes.

---
## Completion record

- Date (UTC): 2026-07-28T01:45:36Z
- Executor (model/agent identity): Codex `/root/p13_builder` acting as Builder;
  independent exact-SHA Curator, Judge, and Orchestrator review remains required.
- Branch and audited implementation commit: `phase/P13-benchmark-mvp`;
  `c582cc0f5d5c962dd0e9954c9f6b576712678856`.
- Gates: P13 suite 8 passed; full pytest 273 passed, 2 skipped, 1,718 subtests;
  Ruff passed; Pyright 1.1.411 passed with 0 errors.
- Benchmark evidence: `evidence/benchmarks/p13-19083f235b2820d7/` binds repaired
  harness code commit `a2669a874c00633d986df8f078cf4b841555cbc1`, five tasks,
  two lanes, three repetitions, seed 7, 30 raw attempts, and disposition
  `measurement-recorded`; raw-results digest
  `sha256:665a2d0e1b4f56b93acceeae5a7b451db1a96c64b066d3d7f206c7e29cc40c87`.
- Audit artifact: `evidence/audits/P13-post.json` (canonical digest:
  `sha256:7c9382e091e5bb563862b77e8430f0f4d844310099b0793f834078650dfbbb02`;
  complete: true; failures: none; audited commit:
  `c582cc0f5d5c962dd0e9954c9f6b576712678856`; audit pytest: 273 passed).
- Deviations from the phase spec: the unavailable global `pyright` launcher was replaced
  by the installed equivalent `python -m pyright`. The first uncommitted exit run
  reproduced a Windows path-length failure while staging raw attempt evidence. The
  candidate was repaired to use bounded content-addressed attempt directories, the P13
  suite was rerun, and the complete 30-attempt measurement was regenerated on the
  repaired code before any benchmark evidence was committed.
- New blockers discovered (mirrored into `docs/plan/BLOCKERS.md`): none. Existing
  multi-comparator and multi-family evidence obligations remain open; this run records
  measurements only and makes no comparative quality claim.

### Constitutional-CI appeal

- Challenged exact candidate:
  `8c852eef09ba00e685d02a352dc1bead805aa67c`. All six Python unit-test jobs failed
  because `tests/test_benchmark_harness.py` imported the undeclared `pytest` package
  while constitutional CI installs the project without development dependencies and
  runs `python -m unittest discover -s tests -v`.
- Removing only the import would have made the module importable while silently leaving
  its eight top-level pytest functions undiscovered by the constitutional runner. The
  repair therefore converted the complete P13 suite to `unittest.TestCase`, replaced
  pytest fixtures and exception helpers with stdlib equivalents, and retained pytest
  compatibility.
- Repaired implementation commit:
  `24bba32113c46d3e5490bd075f90b9e394fc0cf7`. The focused suite passed all 8 tests
  under both the constitutional unittest runner and pytest. The full constitutional
  runner passed 275 tests with 2 skipped in 560.532 seconds; Ruff passed; Pyright
  1.1.411 passed with 0 errors.
- Fresh audit: `evidence/audits/P13-post-ci-repair.json`; canonical digest
  `sha256:2c043414301b24a678e3bfe6ae3aab0cfbc8281659d1fd0668c504070dfa57b1`;
  `complete=true`; failures none; audited head
  `24bba32113c46d3e5490bd075f90b9e394fc0cf7`; audit pytest 273 passed.
- The benchmark corpus, harness, raw 30-attempt measurement, verdict, budgets, and
  comparative-claim guard are unchanged. Delivery remains blocked until one
  consolidated independent Curator, Judge, and Orchestrator review permits the repaired
  exact head. This appeal makes no comparative quality, source-completeness, release-
  readiness, or superiority claim.

### Consolidated-review appeal

- Challenged exact candidate:
  `d6c99863e132d36cab20b4b0daa9be48a1460561`.
- The independent Curator issued `BLOCK`, the independent Judge issued `adapt/BLOCK`,
  and the independent Orchestrator issued `BLOCK`. Each independently reproduced the
  same controlling counterexample: adding arbitrary text
  `superiority-verdict: court-123` made the guard accept
  `Hive Mind OS outperforms the baseline benchmark` without resolving or validating a
  court artifact, digest, disposition, comparator/family coverage, safety floors, or
  claim binding. All three dispositions remain preserved.
- Repair: P13 now rejects every superiority-adjacent claim matched by the guard. Because
  this one-family, one-comparator phase cannot produce a qualifying superiority verdict,
  no textual marker can bypass the prohibition. The regression retains the arbitrary
  marker and requires the claim file to remain reported. A later phase may relax the
  prohibition only by implementing fail-closed resolution and validation of a genuine
  qualifying court artifact.
- Repaired implementation:
  `365b106a867c0b2d0d7a5878de86fc1be0396d8b`. The focused suite passed all 8 tests
  under both unittest and pytest; Ruff passed; Pyright passed with 0 errors. Fresh audit
  `evidence/audits/P13-post-claim-appeal.json` is complete with no failures, passed 273
  tests, and has canonical digest
  `sha256:0381ef6af588f5fa22f4e5c17dc0c8d46ff34659314d352b89fe37ff5699c9c2`.
- The benchmark corpus, raw measurements, lane results, and `measurement-recorded`
  verdict are unchanged. Delivery remains blocked until a fresh consolidated Curator,
  Judge, and Orchestrator review permits the repaired exact head. No comparative quality,
  source-completeness, release-readiness, or superiority claim is made.
