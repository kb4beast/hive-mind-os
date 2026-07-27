# P09 — Physically Enforced Point-in-Time Replay

Status: tracked in `00_OVERVIEW.md` | Depends on: P04 | Unlocks: P10

## 1. Objective

Build the first physically enforced point-in-time learning harness: an oracle that
constructs a learner environment containing *only* the ancestor commits of a target — the
target and all future objects are absent from the environment, not merely hidden by
convention — with sealed predictions recorded before reveal, graded outcomes, and
adversarial leakage regression tests, exercised over a deterministic fixture history and
over a pinned slice of this repository's own history.

## 2. Rationale

First-commit-forward anti-cheat learning is a founding claim (vision contract § "no
cheating") and the project's most differentiated research asset. The existing
`RepositoryLearningCurriculum` / `RepositoryLearningEpisode` do the bookkeeping (hidden
sets, access validation) but trust the caller to report what was accessed. The master
prompt's Stage 4 requires replacing caller-reported access with an oracle-created
ancestor-only environment. That is this phase: leakage becomes impossible at the object
level, and the existing bookkeeping becomes defense in depth.

## 3. Required reading

1. `docs/plan/00_OVERVIEW.md`
2. `src/hive_mind_os/repository_learning.py` (entire file — you are building under its
   contracts: `CommitState`, `RepositoryLearningCurriculum`, `RepositoryLearningEpisode`,
   `require_no_leakage`)
3. `src/hive_mind_os/learning.py` (`PointInTimeReplay` — the older primitive; note the
   overlap and keep both working)
4. `src/hive_mind_os/git_adapter.py` and `src/hive_mind_os/sandbox.py`
5. `docs/architecture/HARDENED_VISION_CONTRACT.md` § "Point-in-time repository learning"
6. `tests/test_repository_learning.py`

## 4. Prerequisite verification

```bash
python -m pytest -q tests/test_git_adapter.py tests/test_repository_learning.py   # pass
git rev-list --count HEAD    # this repo has usable history (>25 commits expected)
```

## 5. Scope

In scope:

- `PointInTimeOracle` producing ancestor-only environments via
  `git fast-export` / `fast-import` (or `git bundle` over an ancestor rev-range —
  executor chooses one, proves object absence either way).
- Sealed predictions (digest to ledger before reveal), reveal, and grading records.
- Episode runner integrating oracle env + curriculum bookkeeping + sandbox execution.
- Leakage regression tests, including adversarial probes run *inside* the environment.
- A pinned self-history curriculum: the first N commits of hive-mind-os itself.

Non-goals:

- No forge metadata (issues, PRs, CI history) cutoffs — file/commit level only for now;
  record this openly in episode metadata. No dependency-version time travel. No model
  intelligence for predictions (P10 supplies learners; this phase's test learner is
  scripted). No benchmark scoring beyond simple graded records.

## 6. Design constraints

- **Physical absence.** For target commit `N` with parent `P`: build a fresh repository
  containing exactly the ancestor closure of `P`. Construction runs through
  `SandboxRunner` (git allowlisted). Verification (part of the oracle, not just tests):
  (a) `git rev-list --all` of the environment equals the expected ancestor set;
  (b) `git cat-file -e <sha>` fails inside the environment for the target commit SHA,
  the target tree SHA, and every future commit SHA; (c) for merge-heavy histories, all
  ancestors via all parents are present (use the fixture to cover an octopus-free merge
  DAG). The oracle refuses to hand out an environment that fails its own verification.
- **Seal before reveal.** A prediction is a JSON document (episode id, target position,
  learner identity, prediction content); its SHA-256 digest is appended to the ledger as
  `pit.prediction.sealed` before the oracle's `reveal(episode)` will return the target
  diff/message. `reveal` without a recorded seal → typed error plus a
  `pit.violation` ledger event. This ordering is enforced by the oracle object, and the
  ledger is the proof.
- **Defense in depth.** The episode runner still records accessed SHAs into
  `RepositoryLearningEpisode.validate_access` — both layers active; a discrepancy
  (bookkeeping says leaked, physics says impossible) fails closed loudly since it
  indicates a harness bug.
- **Deterministic fixture DAG.** Extend `tests/fixtures/fixture_repo.py` (or add
  `fixture_history.py`) with a ~10-commit history including one merge and one tag,
  fixed dates → stable SHAs, giving leakage tests exact SHA expectations.
- **Self-history curriculum.** `build_self_curriculum(repo_path, first_n)` maps the
  repository's own earliest `first_n` commits (pinned list committed as a fixture file
  with their SHAs) into `CommitState` records. Grading for the scripted learner:
  predict which files change in the target commit given the environment — graded by
  overlap; trivial by design, the harness is the deliverable.
- **Timestamps honesty.** Episode records include `environment_built_at` and note that
  external-world knowledge cutoffs (model training data) are NOT controlled — a model
  may "know" this public repo's future. Record the caveat in every self-history episode
  (`contamination_caveats` field) per the vision contract's honesty requirements.

## 7. Deliverables

New files:

- `src/hive_mind_os/pit_oracle.py` — `PointInTimeOracle`, `PITEnvironment`,
  `SealedPrediction`, `EpisodeGrade`, typed errors (`LeakageError`, `SealViolation`).
- `tests/fixtures/fixture_history.py` — deterministic multi-commit DAG builder.
- `tests/fixtures/self_history_pins.json` — pinned first-N SHAs of this repository.
- `tests/test_pit_oracle.py`.

Modified files:

- `src/hive_mind_os/cli.py` — `hive-mind pit-episode --repository <path> --target <sha>
  --learner scripted --state-dir …` (single-episode runner for manual use).

## 8. Implementation steps

1. Verify prerequisites; branch `phase/P09-pit-oracle`.
2. Build the fixture DAG with stable SHAs; commit the expected-SHA table as constants.
3. Implement environment construction + the oracle's self-verification; get object-absence
   checks green on the fixture (including the merge case).
4. Implement seal/reveal/grade flow with ledger events.
5. Integrate curriculum bookkeeping (defense in depth) in the episode runner.
6. Add adversarial probes: a scripted "cheating learner" that, inside the environment,
   attempts `git cat-file` on the target SHA, `git log --all`, reflog inspection, and
   packed-refs reading — all must come back empty-handed, and the attempts must be
   receipted (they run through the sandbox).
7. Build the self-history curriculum and run one full scripted episode against it.
8. CLI subcommand; gates; audit `evidence/audits/P09-post.json`; status updates;
   completion record.

## 9. Required tests

`tests/test_pit_oracle.py`:

1. Ancestor-set equality on the fixture DAG for a mid-history target (exact SHA set).
2. Object absence: target commit, target tree, and all future SHAs fail `cat-file -e`
   inside the environment; pre-target blobs succeed.
3. Merge correctness: environment for a target after the merge contains both parent
   lines.
4. Oracle self-verification failure (simulate by injecting a future object into the
   environment) → environment refused.
5. Seal-before-reveal: reveal without seal → `SealViolation` + `pit.violation` event;
   with seal → reveal returns target diff and grading proceeds.
6. Prediction immutability: altering the prediction after sealing is detected (digest
   mismatch at grading).
7. Cheating-learner probes all fail and are receipted.
8. Defense-in-depth discrepancy: bookkeeping reporting an access the environment cannot
   contain → loud harness error (not silent pass).
9. Episode record completeness: environment digest, seal digest, grade, caveats,
   receipts — all present and resolvable.
10. Self-history: one scripted episode over the pinned slice completes end-to-end
    offline.

## 10. Exit criteria

```bash
python -m pytest -q tests/test_pit_oracle.py    # all pass
python -m pytest -q && python -m ruff check src tests && pyright   # clean
hive-mind pit-episode --repository . --target <pinned-sha-from-fixture-file> --learner scripted   # exits 0; prints episode record path
```

## 11. Evidence

- `evidence/audits/P09-post.json` committed.
- One complete episode record from the self-history run committed under
  `evidence/pit/` (volatile fields intact — this is real evidence, not a normalized
  fixture).

## 12. Rollback

Revert the branch. `repository_learning.py` and `learning.py` are untouched consumers-of
record; nothing else imports the oracle until P10.

## 13. Handoff

Later phases may assume: leakage is physically impossible at the git-object level;
predictions are sealed before reveal with ledger proof; a deterministic fixture DAG and a
pinned self-history curriculum exist; every episode carries honest contamination caveats.

## 14. Forbidden shortcuts

- No `git checkout <parent>` + "please don't look" environments — absence, not privacy.
- No reveal path that skips the seal check in any code path (including CLI).
- No scrubbing of the contamination caveat from self-history episodes.
- Do not modify `repository_learning.py` semantics to fit the oracle; the oracle
  conforms to the existing contracts.
