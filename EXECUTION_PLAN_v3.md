# Hive Mind OS — Execution Plan v3 (Reimagined)

- **Plan version:** 3.0
- **Written:** 2026-08-03
- **Supersedes for sequencing:** `docs/plan/00_OVERVIEW.md` (v1.1), `docs/plan/01_POST_P13_OVERVIEW.md` (v2.0-proposed), and the `NEXT_SESSION_HANDOFF_OBSIDIAN_AGENT_REDESIGN.md` Phase 0–8 sequence.
- **Does NOT supersede:** `AGENTS.md` non-negotiable rules, the fail-closed principle, the receipts design, or any ADR's *architecture* content.
- **Status:** proposed to the repository owner. Nothing here is adopted until the owner says so.

---

## 0. Read this first (the whole plan in 12 lines)

This repository contains an excellent **evidence substrate** attached to a **product that does not yet
do anything for a user**, wrapped in a **governance corpus 12× larger than its own source code**.

The measured facts, all regenerated on 2026-08-03:

| Measure | Value |
|---|---|
| Source (`src/**/*.py`) | 23,565 lines |
| Tests (`tests/**/*.py`) | 11,541 lines |
| Evidence corpus (`evidence/**`, 1,022 files) | 274,456 lines |
| Evidence : source ratio | **11.6 : 1** |
| Roles with runtime behavior | **3 of 8** (Explorer, Builder, Curator) |
| Real model calls ever made by the system | **0** (blocker B-OPS-03, open since P01) |
| Git tags / GitHub releases | **0 / 0** |
| CI status, `main` | **red** since PR #27 |
| CI status, `codex/p1-correctness-hardening` | **red** as of today's run 30818413739 |
| Local suite, Windows 11 / Python 3.14 | **382 tests, 4 errors**, 703s (reproduced twice) |
| Commits on `main` since 2026-07-28 | **1** (the red one) |
| Insertions parked on the side branch | **118,764** across 382 commits / 563 files |
| Project's own published benchmark | hive-mind **0.400** vs baseline **0.600** |
| Tracked files that are `evidence/` | **998 of 1,255 (79.5%)** |
| `CONTRIBUTING.md` / `CODE_OF_CONDUCT.md` / `SECURITY.md` | **none exist** |
| Required PR approvals vs maintainer count | **2 + code-owner review, with 1 maintainer** — outside PRs cannot merge |

The plan below spends its first phase making the repository green and honest, its second phase making
the system do **one real thing** (fix a real bug in a real repository using a real model), and its
third phase turning the one genuinely differentiated asset — **verifiable agent execution** — into the
product. Everything else is deferred, deleted, or archived.

---

## 1. Diagnosis: why 118,764 lines produced no product

### 1.1 The autocatalytic paperwork loop

The project's governance rule is *evidence before authority*. Correct. But the work that produces
capability requires **external inputs the agents cannot supply** — an API key, a real user, a human
reviewer, a deployment account. The work that produces **evidence about the project itself** requires
nothing but a text editor.

So when the roadmap hit its first gate needing a human (`ADR-015` adoption disposition; P14–P20 all
`pending`), the agents did the only work available: they wrote records. Then records reconciling those
records. The observed chain is:

```
5H (court about roles)
 → 5I (docket about adoption)      → "ADR-015 adopted: false. P14 eligible: false"
 → 5J (packet about the docket)    → "packet ready; external review not run"
 → 5K (intake code for packets)    → evidence/phase5k/ contains zero submissions
 → 5L, 5M, 5N, 5O, 5P (reconciliations of the above)
 → BGOV06, BGOV07 (reconciliations of the reconciliations)
```

Post-P13, **78% of new program units are governance about the project itself** (18 of 23), up from 25%
in P01–P20. By line, ~77% of the 118,764-line branch is meta-work. This is not laziness or dishonesty —
the corpus contains no overclaims anywhere the panel checked. It is a **structural incentive defect**:
the plan had no rule that stops work when a gate needs a human, and no rule that requires each unit of
work to move a user-visible needle.

**This plan's central fix is two standing rules (§6): a hard stop at human gates, and no phase without a
user-visible delta.**

### 1.2 The gate that was never the gate

`docs/plan/00_OVERVIEW.md` §5 tells every executor the standard gate is:

```bash
python -m pytest -q
```

`.github/workflows/ci.yml:29-34` actually runs:

```bash
python -m pip install --disable-pip-version-check --no-deps -e .
python -m compileall -q src tests
python -m unittest discover -s tests -v
```

Two different runners, and `--no-deps` means **any third-party import in `tests/` breaks CI**. Nothing
tests this contract: `tests/test_governance.py` checks pinned action SHAs, job names, code owners, and
the build-backend pin — but never that the tests can actually run in CI's environment.

This has now caused the same failure twice:

- **PR #27** merged 4 test files importing `pytest` → `ModuleNotFoundError: No module named 'pytest'` on
  3.11/3.12/3.14. Merged anyway with zero reviews while checks were pending (the project honestly logged
  this against itself as B-GOV-06).
- **Today's p1 commit** added `tests/test_custody.py`, `test_hard_isolation.py`, `test_source_custody.py`
  importing `cryptography`, declared only as an optional `custody` extra CI never installs → identical
  failure class. Plus `scripts/verify_installed_wheel.py` fails on hand-maintained magic numbers
  (`schema_count: 20` vs 32 actual).

An executor can follow the written protocol perfectly and still ship red CI. **Fixed in P0.1.**

### 1.3 The product is a puppet show, and the strings are in the source

`hive-mind deliver --backend scripted` is the documented, default, and (for the scheduler, workers, and
durable-resume paths) **only permitted** backend. Its behavior:

- `mission.py:66` hardcodes `_GOOD_FIX = b"def increment(value: int) -> int:\n    return value + 1\n"`.
- `ScriptedRepositoryBackend` writes `tiny_pkg/maths.py` regardless of the objective text.

So the ~2,300 lines of durable-mission, checkpoint, scheduler, and worker machinery exclusively replay
one hardcoded fix to one bundled fixture. That machinery is well-built. It has never carried a payload.

The real path, `--backend model`, is **structurally incapable of the job**:

- `model_backend.py:205-215` — the user message contains `objective.goal`, `acceptance_criteria`,
  `constraints`, `base_workspace` (**a path string**), `work_item.instruction`, and truncated prior
  prose. **No file contents. No failing-test output. No read tool. No second turn.** The Builder model
  is asked to emit a complete file fix for a repository it has never been shown.
- The action-JSON protocol (`name`/`path`/`content_base64`/`message`) is **never described to the
  model**; the Builder's entire guidance is one sentence naming the verbs. A wrong key raises
  `MissionFailed`, which — unlike `ModelTurnError` — is **not retryable**. The mission dies.
- `model_backend.py:203` truncates the serialized context with `rendered[:context_limit_chars]`, a
  **character-boundary slice** that hands the model syntactically broken JSON, flagged only by a
  boolean. A test asserts this truncation is "actual and deterministic," institutionalizing it.
- The provider env vars (`HIVE_MIND_MODEL_PROVIDER`, `HIVE_MIND_MODEL_BASE_URL`, `HIVE_MIND_MODEL_MODEL`)
  are documented in **zero** markdown files in the repository.

This is why B-OPS-03 has never closed. It is not waiting on an API key. **It is waiting on the model
being told what repository it is working on.** Fixed in P1.

### 1.4 Five of the eight roles are name-tags

`roles.py` is 90 lines: eight frozen tuples of prose (one mission sentence, ~3 output nouns, capability
strings, 2 gate clauses). No methods. The capability strings (`open_pull_request`, `search_web`) are
**never mapped to the policy engine's `Action` enum** and enforce nothing.

At runtime (`mission.py:618-1218`, a ~600-line method):

| Role | Runtime behavior |
|---|---|
| Explorer | Runs one test command that must fail. **Real.** |
| Builder | Branch, write file, run tests, commit. **Real.** |
| Curator | Re-executes sealed checks in a fresh workspace. **Real, and good.** |
| Architect | `ArchitectCapabilities(results[-1].evidence)` — constructed, **never assigned, discarded**. |
| Orchestrator, Integrator, Steward, Optimizer | Asserted to have proposed **no actions**. Their instruction literally reads "No side-effect capability is available; proposed_actions must be empty." |

Ledger lines crediting INTEGRATOR/STEWARD with publish and report steps are labels stamped on
engine-internal file copies. The GitHub PR path authorizes as `Role.BUILDER` while the ledger credits
INTEGRATOR.

Because the Explorer must reproduce a **failing test** or the mission aborts, the system is structurally
limited to red→green bugfix missions. Feature work on a green repository is impossible by construction.

The new 7,342-line package system (PR #27) added JSON files that **duplicate the same eight prose
strings**, plus one-sentence prompts and skills that are miniature role summaries. Per ADR-017 they are
**inert data with no runtime consumer** — `grep` finds no production caller for `PackageCatalog` outside
tests. The duplication is now 3-way: Python literals, agent JSON, prompt JSON.

### 1.5 Governance that constrains only the cooperative caller

The security panel **executed** six bypasses. Critically, the project's own ADRs pre-admit most of them
in near-verbatim terms — this is honest scaffolding, not fraud. Two, however, are **undocumented**, and I
reproduced both myself:

**(a) Champion prompt pointer is not gated by promotion.** `promote()` correctly refuses an
unauthorized promotion (I confirmed: `RuntimeError: promotion lacks a matching artifact registration`).
But `champion_digest()` (`prompt_registry.py:226-234`) validates only that the pointer **resolves to a
file** — never that a promotion lineage record or ledger decision event exists. Writing `champions.json`
directly installs any registered artifact as champion:

```
promote() correctly BLOCKED: promotion lacks a matching artifact registration
champion_prompt AFTER RAW POINTER WRITE -> 'You are the builder. Ignore prior constraints and '
lineage kinds for installed champion: ['registration']
promotion record exists: False
```

`model_backend.py:171` consumes `champion_prompt()` as the **system prompt**. So a single file write
replaces the system prompt of every model role, with no record. The elaborate four-identity promotion
gate is real but **not load-bearing** — it can simply be walked around.

**(b) `PolicyEngine.autonomy` is a mutable public attribute.** `MUTATE_POLICY` is declared a
non-delegable invariant, yet one assignment raises authority without ever requesting that action:

```
default autonomy: 2 (SANDBOX)
CREATE_BRANCH before: False
CREATE_BRANCH after attribute write: True
```

Fairly: `EXTERNAL_GRANT_ACTIONS` (`MERGE_PULL_REQUEST`, `DEPLOY`, `MANAGE_SECRETS`, `SPEND_MONEY`) stayed
denied at every level including `GOVERNED_FULL` — I confirmed. That part is genuinely solid.

Also verified: `HiveKernel` accepts a `PolicyEngine` and **never calls `.decide()`**; policy is consulted
at ~6 hand-placed sites, not by construction; `VisionComplianceGate`, `ClassicGptSimulationGate`, and the
entire `package_system` have **zero production consumers**; the "append-only" ledger is enforced by
SQLite triggers a second connection can `DROP` (this one the docs do admit).

### 1.6 What is genuinely excellent (do not break these)

Being ruthless cuts both ways. These are better than most production systems:

1. **Curator blind-seal ordering** (`curator.py:132-137`) — verification checks are sealed into the
   ledger *before* the candidate head is accessible, enforced by monotonic ledger sequence comparison.
   Plus AST-based test-weakening detection and diff-confinement to declared paths. This is a real,
   deterministic, novel idea and it is the seed of the product.
2. **Content-addressed receipts** (`receipts.py:103-238`) — digest over actually-read bytes, root-escape
   checks, portable-path validation rejecting `..`/absolute/backslash/Windows-reserved/ADS, all six
   action fields bound, artifact digests independently re-read.
3. **Failure-path honesty** — failed missions publish nothing, preserve evidence separately, and
   revalidate receipts on the failure path.
4. **Package system inertness (ADR-017)** — verified: no `exec`/`eval`/`import`/`subprocess` anywhere in
   `package_system/`; JSON-only with digest verification, duplicate-key rejection, symlink rejection;
   `import hive_mind_os` does **not** load hive-core.
5. **Secret hygiene** — keys read at request time, redacted from exceptions, bodies digested not stored.
6. **Determinism and portability** — two scripted runs produce identical head SHA and tree digest;
   stdlib-only runtime holds; POSIX+Windows path discipline is real.
7. **Blocker-backlog schema** — ID, obligation, exit condition, owner, review-by, append-only status.
   Excellent pattern; keep it.
8. **The external-input register held.** No credentials, identities, or verdicts were ever fabricated.
   The failure mode of this project is inflation of *process*, never inflation of *claims*. That is a
   rare and valuable cultural asset — the plan below redirects it rather than discarding it.

---

## 2. The reimagined product

### 2.1 The vision, restated

The current README opens with "an evidence-driven agentic operating system for autonomous product and
software delivery" and reaches insider jargon (docket, courtroom, atomic claims, burden, Stage 0) before
a newcomer sees a single reason to care. The eight-role table is the second thing on the page, and five
of those roles do nothing.

**"Eight autonomous agents" is not a differentiator in 2026.** Every framework has that. It is the most
crowded, least defensible position available.

**Verifiable agent execution is a differentiator, and this repo already has the hard part built.**

The unmet need: teams now merge code written by agents they cannot audit. CI tells you the tests pass —
*after* you have already decided to trust the diff. Agent frameworks give you orchestration. Observability
tools give you traces. **Nobody gives you a verdict you can check without redoing the work.**

The Curator blind-seal is exactly that primitive: checks committed *before* the candidate exists, so the
verifier cannot be tuned to the answer. Bind it to content-addressed receipts and you get a portable,
tamper-evident answer to "did this agent actually do what it says?"

### 2.2 Positioning statement

> **For developers and teams shipping AI-authored code, Hive Mind OS produces a tamper-evident receipt
> bundle proving what an agent actually did — the commands it ran, their exit codes, the diff it
> produced, and whether an independently sealed check passed — unlike CI, which runs only after you've
> decided to trust the change, and unlike agent frameworks, which orchestrate work but prove nothing.**

Tagline candidate: **"Don't trust your coding agent. Verify it."**

### 2.3 What this repositioning changes

| Asset | Old role | New role |
|---|---|---|
| Curator blind-seal | One step of eight | **The product** |
| Receipts + portable paths | Internal plumbing | **The deliverable artifact** |
| 8-role lifecycle | The headline | An internal pipeline; shrink to what exists |
| Courtroom / dockets | Front-page framing | Archived project history; *not* user-facing |
| Package system | New extensibility layer | Frozen; no consumer, no user need yet |
| Obsidian brain (2,630-line handoff) | Next major program | **Deferred entirely** until there is a user |

### 2.4 Who this is NOT for (state it plainly)

Not for people who want an autonomous agent that writes features unattended. It cannot do that, and the
plan does not promise it. Honesty here is a feature: the project's culture already refuses to overclaim,
and that is exactly what a verification tool must sell.

---

## 3. Standing rules (these prevent the recurrence)

Every task below inherits these. An executor that violates one has failed the task regardless of tests.

- **R1 — The gate is CI, and CI is one command.** The command in `README.md`, `AGENTS.md`,
  `docs/plan/*`, and `.github/workflows/ci.yml` must be byte-identical, and a test must enforce that.
- **R2 — No phase without a user-visible delta.** Every phase names one thing a user can do afterward
  that they could not do before. A phase whose entire output is records is forbidden.
- **R3 — Evidence budget.** `evidence/**` may not grow. Currently 274,456 lines against 23,565 lines of
  source. Until that ratio is under 2:1, every new evidence file requires deleting or archiving an old
  one. Receipts generated by *runs* live outside the repo by default.
- **R4 — No meta-work.** A document whose subject is another document in this repository may not be
  created. No reconciliation phases. No dockets about dockets. If records disagree, delete the wrong one.
- **R5 — Human gates get exactly one packet, then STOP.** When a task needs an API key, a human
  reviewer, a deployment account, or a spend authority, the executor writes **one** handoff file listing
  precisely what it needs, and stops. It may not build intake machinery, adoption dockets, or review
  packets against that gate. (§7 lists every such gate.)
- **R6 — Trunk-based. `main` is always green and releasable.** No 118,764-line side branches. Maximum
  branch lifetime: one phase. If a branch cannot merge in a week, it is too big.
- **R7 — Counts are generated, never hand-maintained.** No magic numbers in verification scripts. Any
  expected inventory is derived from the tree or from a manifest regenerated in the same commit.
- **R8 — No new subsystem without a production consumer in the same PR.** If nothing in `src/` outside
  the new module calls it, it does not merge.
- **R9 — Don't weaken tests, gates, or claims to pass.** (Retained verbatim from `AGENTS.md`; it worked.)

---

## 3A. Executor quick start (read this if you are the implementing model)

You do not need to read anything else in this repository to begin. Do exactly this:

1. **Confirm the trunk.** `git fetch origin && git log --oneline -1 origin/main`. If it is not green in
   CI, your task is P0 and nothing else.
2. **Take the lowest-numbered unfinished task in §4.** One task, one branch, one PR. Never two.
3. **Before writing code, write the acceptance test named in the task.** Watch it fail. Then implement.
4. **Run the single gate:** `python -m unittest discover -s tests`. It must end `OK`.
5. **Check the task's "Forbidden" list against your own diff** before you open the PR.
6. **Stop.** Do not start the next task. Do not write a summary document about what you did — the PR
   description is the record (R4).

**If you get stuck or the repository state contradicts this plan:** stop and write one file,
`docs/BLOCKED_<task-id>.md`, containing the exact command you ran, its exact output, and the specific
contradiction. Do not improvise a fix to another task's scope. Do not build machinery to work around a
missing human input (R5).

**Task sizing** (for scope calibration — if your change is 3× this, you have misread the task):

| Phase | Rough size | Human input needed |
|---|---|---|
| P0.1–P0.35 | small — config, one new test file | none |
| P0.2–P0.3 | medium — mechanical conversions + 4 bug fixes | none |
| P0.4 | medium — cherry-picks, one PR each | **G1: owner decision** |
| P0.5 | small — README restructure | none |
| P1.1 | small — flags + docs | none |
| P1.2–P1.4 | **large — the real work of this plan** | none |
| P1.5 | small to run, unbounded to interpret | **G2: API key + spend authority** |
| P2.1 | large — refactor `run()` | none |
| P2.2–P2.3 | medium — move/freeze, one decision each | none |
| P3.1 | large — the new product surface | none |
| P3.2–P3.3 | medium — three targeted fixes | none |
| P4 | medium — docs, release | owner tags the release |
| P5 | medium — archival, mostly deletion | owner approves archive repo |

## 4. Phase plan

Nine phases. Each is one PR. Each states its user-visible delta. Ordering is strict — later phases
assume earlier ones.

**Executor protocol for every task:** branch from green `main` → implement → run the single gate
command → verify each acceptance check literally → open PR → stop. Never begin the next phase in the
same branch.

---

### P0 — Stop the bleeding (green trunk, honest README)

**User-visible delta:** a newcomer can clone `main`, run one command, and have it pass.

#### P0.1 — Single-source and self-test the CI contract

- **Files:** `.github/workflows/ci.yml`, `docs/plan/00_OVERVIEW.md` §5, `AGENTS.md`, `README.md`,
  `tests/test_ci_contract.py` (new).
- **Decision (made — do not re-litigate):** keep `python -m unittest discover -s tests` and the
  zero-third-party-dependency test contract. Rationale: it is what CI already enforces, it preserves the
  stdlib-only constitution, and it removes a dependency class that has now broken CI twice. Do **not**
  switch to pytest.
  - *For the owner only, not the executor:* the defensible alternative is pytest with a declared `dev`
    extra and CI running `pip install -e ".[dev]"`. If you choose it, the guard in step 1 changes from
    "no third-party imports in tests" to "every third-party import in `tests/` appears in the `dev`
    extra, and CI installs that extra." Either choice works; having **neither** guard is what broke CI
    twice. Pick one before the executor starts.
- **Steps:**
  1. Write `tests/test_ci_contract.py` with three test methods:
     - `test_documented_gate_matches_workflow`: parse `.github/workflows/ci.yml`, extract the `run:`
       string of the step named `Run deterministic test suite`; assert that exact string appears in
       `README.md`, `AGENTS.md`, and `docs/plan/00_OVERVIEW.md`. Parse YAML **without** a third-party
       library (the file is simple; use a line scan keyed on `- name:` / `run:` — do not add PyYAML).
     - `test_no_test_module_imports_third_party`: walk `tests/*.py`, parse each with `ast`, collect every
       `Import`/`ImportFrom` root module name; assert each is in `sys.stdlib_module_names` or equals
       `hive_mind_os`. This is the test that would have caught both the `pytest` and `cryptography`
       breakages.
     - `test_workflow_installs_no_extras`: assert the install step contains `--no-deps` (so the previous
       test's guarantee is the one CI relies on).
  2. Make the three documents quote the workflow command verbatim.
- **Acceptance:**
  ```bash
  python -m unittest tests.test_ci_contract -v
  ```
  Expected: 3 tests, OK.
- **Forbidden:** adding PyYAML or any dependency; making the test read a duplicated constant instead of
  the workflow file; skipping the AST check because "we'll remember."

#### P0.2 — Convert the four pytest-importing test modules to unittest

- **Files:** `tests/test_host_capability_profiles.py`, `tests/test_ooda_workflow.py`,
  `tests/test_package_catalog.py`, `tests/test_package_extensions.py`.
- **Steps:** replace `import pytest` and `pytest.raises(X)` with `unittest.TestCase` +
  `self.assertRaises(X)`; convert `@pytest.mark.parametrize` to `subTest` loops; convert bare
  `assert x == y` to `self.assertEqual`. Preserve every assertion — do not drop cases.
- **Acceptance:**
  ```bash
  python -m unittest discover -s tests -v
  ```
  Expected: no `ModuleNotFoundError`; test count ≥ the count before the change.
- **Forbidden:** deleting tests instead of converting; adding `pytest` to dependencies.

#### P0.3 — Fix the four Windows subprocess failures

- **Evidence:** a full local run on Windows 11 / Python 3.14 produced
  `Ran 382 tests in 703.621s / FAILED (errors=4, skipped=2)`, with
  `NotADirectoryError: [WinError 267] The directory name is invalid` from
  `subprocess._execute_child`. CI is Linux-only and never sees this; development is on Windows.
- **The four failures are already identified** (regenerated 2026-08-03, Windows 11 / Python 3.14, two
  independent runs — 703.6s and 814.0s, same result):

  ```
  ERROR: test_benchmark_harness.BenchmarkHarnessTests.test_committed_benchmark_receipts_survive_clean_checkout
  ERROR: test_current_state_audit.CurrentStateAuditTests.test_collects_repository_docket_without_broken_receipts_or_running_tests
  ERROR: test_current_state_audit.CurrentStateAuditTests.test_test_time_worktree_mutation_is_reported
  ERROR: test_current_state_audit.CurrentStateAuditTests.test_unrecognized_overall_pytest_result_cannot_complete
  Ran 382 tests / FAILED (errors=4, skipped=2)
  ```

  **Three of four are in the current-state audit** — the subsystem whose entire purpose is establishing
  ground truth about the repository. The project's own truth-telling machinery does not run on the
  platform its author develops on, and Linux-only CI has never revealed this.

- **Steps:**
  1. **Do P0.35 first, then re-run these four before writing any code.** Hypothesis worth 60 seconds:
     `core.worktree=/workspace` makes every git invocation in this clone fail, and
     `current_state_audit` shells out to git. These failures may be a symptom of the broken clone
     config rather than independent bugs. Verify with:
     `python -m unittest tests.test_current_state_audit -v`
     If they pass after unsetting `core.worktree`, P0.3 shrinks to the single `test_benchmark_harness`
     failure — **record that finding and do not "fix" tests that were never broken.**
  2. For whatever genuinely remains: the signature is `NotADirectoryError: [WinError 267]` from
     `subprocess._execute_child`, i.e. a `cwd` argument that is not an existing directory. Fix the call
     sites, not the tests.
  3. Add `windows-latest` to the CI matrix for Python 3.12 only (keep cost bounded) so this class cannot
     regress silently. This is the highest-value single line in P0: the project develops on Windows and
     tests only on Linux.
- **Acceptance:** `python -m unittest discover -s tests` → `OK` on Windows; CI green on both OSes.
- **Forbidden:** skipping the tests on Windows; `@unittest.skipIf(os.name == "nt")` as the fix.

#### P0.35 — Repair the local clone's broken `core.worktree` (do this first; it takes 30 seconds)

- **Symptom:** on this machine, `git status` fails with
  `fatal: this operation must be run in a work tree`, while `git rev-parse`, `git log`, and `git config`
  all succeed.
- **Cause:** `.git/config` contains `core.worktree=/workspace` — a Linux container path (the Codex cloud
  working directory) baked into a Windows clone. Confirmed pre-existing: `.git/config` mtime is
  2026-08-03 08:32, before this review began, and `git rev-parse --is-inside-work-tree` returns `false`.
- **Fix:**
  ```bash
  git config --unset core.worktree
  ```
  Then confirm `git status --short` returns without error.
- **Why this belongs in the plan, not a footnote:** every executor protocol in `docs/plan/00_OVERVIEW.md`
  depends on inspecting worktree state ("a dirty worktree keeps the audit incomplete"), and
  `hive-mind audit` reports on the Git worktree. On this clone those checks cannot run at all. A
  container-authored config leaking into a developer clone is also a plausible contributor to the
  branch-sprawl problem: agents and humans have not been operating on the same view of the repository.
- **Guard:** add `core.worktree` to a documented "clone health" check in `CONTRIBUTING.md` (P4.2).

#### P0.4 — Resolve the branch fork (owner decision required — see §7 G1)

- **Situation:** `main` is 1 red commit past P13. `codex/p1-correctness-hardening` holds 382 commits /
  118,764 insertions / 563 files, is also red, and contains both genuinely valuable hardening
  (ADR-040–046: criterion-bound Curator seals, risk-tier propagation, HTTPS-only providers, enqueue SHA
  pinning, typed executable acceptance specs) and ~92,000 lines of meta-work.
- **Recommended action (owner confirms, executor performs):** do **not** merge the branch. Instead:
  1. Tag it `archive/p1-correctness-hardening-2026-08-03` and push the tag so nothing is lost.
  2. Cherry-pick **only** these into `main` as separate small PRs, in this order:
     - `src/hive_mind_os/acceptance.py` + `--acceptance-spec` CLI wiring + schema (ADR-041). This is the
       single most valuable item on the branch: it converts prose acceptance criteria into a sealed,
       executable command bound into the Curator receipt.
     - Criterion-to-check seal coverage in `curator.py` (ADR-040 decision 1).
     - HTTPS-only provider validation + response size caps in `model_provider.py` (ADR-040 decision 3).
     - Enqueue full-SHA pinning + deterministic mission-ID dedup (ADR-040 decision 5).
  3. Leave `custody.py`, `hard_isolation.py`, `model_turn_state.py`, `durable_model_execution.py` on the
     archived branch. They are large, they add a `cryptography` dependency that breaks the zero-dep
     contract, and they solve problems the project does not yet have (it has no users to protect).
     Revisit only when §7 G3/G4 open.
- **Acceptance:** `git tag --list 'archive/*'` shows the tag; `main` is green after each cherry-pick PR;
  `evidence/` line count does not increase.
- **Forbidden:** merging the branch wholesale; cherry-picking the phase5 evidence tree; adding
  `cryptography` to runtime or test dependencies.

#### P0.45 — Fix the Windows MAX_PATH bug that masks every failure

- **Symptom:** running `hive-mind deliver --backend scripted` against a user's own repository fails with
  `MissionFailed: failed-run receipt failed validation: receipt path is not a regular file`.
- **Real cause:** the receipt path was measured at **265 characters** against Windows' 260-char default
  (`LongPathsEnabled = 0`). `pathlib.Path(p).is_file()` returns `False`; the same path with the `\\?\`
  prefix returns `True`. The genuine underlying error — the scripted backend having nothing to do on a
  non-fixture repo — is **swallowed and replaced by a nonsense message**.
- **Why this is P0:** it is the first error a newcomer sees, it is on the default path, and it makes the
  system look broken in a way that has nothing to do with the actual limitation.
- **Steps:**
  1. In `receipts.py`, normalize paths through a `\\?\`-prefixing helper on Windows before any
     `is_file()`/`open()` check (guard with `os.name == "nt"` and only for absolute paths).
  2. Shorten the receipt directory layout — content-addressed names nested several levels deep are the
     proximate cause of the length.
  3. Make failure-evidence validation errors **chain** the original mission failure rather than replace
     it: report "mission failed because X; additionally, evidence preservation failed because Y."
- **Acceptance:** a test constructs a receipt root at a >260-char path and asserts validation succeeds;
  a test asserts a failing mission's error message names the mission cause, not only the receipt cause.
- **Forbidden:** telling users to enable `LongPathsEnabled`; catching and discarding the original error.

#### P0.5 — README truth pass

- **Files:** `README.md`.
- **Steps:** add a section directly under the title, before any architecture prose:

  ```markdown
  ## Status: early. Here is exactly what works.

  | Capability | Status |
  |---|---|
  | Verify an agent-authored change against sealed checks (`hive-mind deliver --backend scripted`) | Works, offline, deterministic |
  | Real model drives the change (`--backend model`) | Not yet — see #<issue> |
  | Remote push / pull requests | Local git only |
  | Production use | No. No release, no tag, no user yet. |
  ```

  Then move the courtroom/docket/Stage-0 material **below** the quickstart, or into
  `docs/architecture/`. A newcomer must reach a runnable command before they meet the word "docket."
- **Acceptance:** the first 40 lines of `README.md` contain a runnable command and contain none of:
  "docket", "atomic claim", "burden", "Stage 0", "courtroom". Enforce with a test in
  `tests/test_ci_contract.py`.
- **Forbidden:** deleting the courtroom docs (they are real history — move them, don't erase them).

---

### P1 — Make one real thing work (close B-OPS-03)

**User-visible delta:** a real model fixes a real bug in a real repository, and you get a receipt bundle.

This is the phase the project has been unable to reach for its entire life. The blocker was never the
API key.

#### P1.1 — Document and flag the provider configuration

- **Files:** `README.md`, `src/hive_mind_os/cli.py`.
- **Evidence of the gap (measured, and corrected mid-review — see §9):** `HIVE_MIND_MODEL_*` appears
  **6 times across 3 documents** — `docs/plan/P02_MODEL_ADAPTER.md` (3), `docs/plan/P08_CURATOR_INDEPENDENCE.md`
  (2), `docs/architecture/ADR-012` (1) — and **0 times in `README.md` or `AGENTS.md`**.
  `HIVE_MIND_MODEL_BASE_URL` specifically appears in no markdown at all. None of the six mentions is a
  copy-pasteable setup recipe; they are prose inside phase plans a user will never open.
  `provider_from_env()` reads `HIVE_MIND_MODEL_PROVIDER` (`openai_compatible`|`anthropic`),
  `HIVE_MIND_MODEL_BASE_URL`, `HIVE_MIND_MODEL_MODEL` / `HIVE_MIND_MODEL_ID`, and the provider's key env
  (`OPENAI_API_KEY` / `ANTHROPIC_API_KEY`).
- **Steps:**
  1. Add a README section "Using a real model" with a copy-pasteable block for both provider kinds.
  2. Add explicit `--model`, `--base-url`, `--provider` flags to `build_deliver_parser()` that override
     the env vars. Keep the API key env-only (never a flag — it would land in shell history).
  3. When `--backend model` fails configuration, the error must name the exact missing variable. (It
     partly does; make it list all of them.)
- **Acceptance:**
  ```bash
  python -m hive_mind_os.cli deliver --help
  ```
  shows `--model`, `--base-url`, `--provider`; README block exists.
- **Forbidden:** accepting an API key as a CLI flag; hardcoding a default model ID.

#### P1.2 — Give the model the repository (the fatal gap)

- **Files:** `src/hive_mind_os/model_backend.py`, `src/hive_mind_os/mission.py`.
- **Problem:** the Builder is asked to write a complete file fix for a repository it has never seen.
- **Steps:**
  1. Add a `RepositoryContext` payload assembled by the mission and passed into `backend.execute()`:
     - the failing test command's **actual stdout/stderr** (currently only digests are attached; the
       text is on disk in the receipt — read it back via the receipt store);
     - the contents of every file the failing test names in its traceback, capped at N bytes each;
     - a file tree listing (paths only) capped at M entries;
     - the current diff, if any.
  2. Include this in the user message as **structured fields**, not concatenated prose.
  3. Cap by *tokens-approximated-by-bytes per field* with per-field truncation markers — never one global
     slice (see P1.4).
- **Acceptance:** a new test `tests/test_model_backend.py::test_builder_prompt_includes_failing_test_output_and_named_files`
  asserts the assembled user payload contains the failing test's stderr text and the content of the file
  named in it. Assert on the payload, not on a mock call count.
- **Forbidden:** sending the whole repository; reading files outside the mission workspace; inventing a
  vector store or embedding index (out of scope, and there is no user asking for it).

#### P1.3 — Specify the action protocol and make parse failure retryable

- **Files:** `src/hive_mind_os/model_backend.py`, `src/hive_mind_os/mission.py` (~lines 786-827,
  2471-2494).
- **Steps:**
  1. Put the exact action JSON schema **and one worked example** into the Builder role instruction.
     Today the guidance is one sentence naming verbs; the parser hard-requires `name`, `path`,
     `content_base64`, `message`.

     **Copy the pattern the repo already uses correctly.** `_instruction_for(Role.CURATOR)`
     (`mission.py:2477-2483`) already embeds a literal JSON shape:
     `{"acceptance_checks":[{"name":...,"argv":[...],"expected":"succeeded"}]}`. The Builder's
     instruction is the one-line verb list. This is not a design problem to solve — it is an omission to
     correct, using the Curator instruction as the template.
  2. Convert Builder action-parse failures from `MissionFailed` (fatal) into a retryable corrective turn:
     re-prompt once, including the model's own invalid output and the specific validation error, then
     fail if the retry also fails. Mirror the existing `ModelTurnError` retry pattern.
  3. Record both the invalid attempt and the correction in the ledger — the project's honesty discipline
     demands the failed attempt survive.
- **Acceptance:** `tests/test_mission.py::test_builder_invalid_action_json_is_corrected_not_fatal` — a
  fixture provider emits a wrong-key action, then a valid one; the mission succeeds and the ledger
  contains both turns.
- **Forbidden:** silently retrying without recording; unbounded retries (exactly one correction).

#### P1.4 — Structure-aware context budgeting

- **Files:** `src/hive_mind_os/model_backend.py:199-204`.
- **Problem:** `rendered[:context_limit_chars]` hands the model broken JSON.
- **Steps:** replace with whole-record eviction — drop **entire** prior-role entries oldest-first until
  under budget; keep the JSON valid; add an explicit `omitted_roles: [...]` field so the model knows what
  is missing. Never truncate mid-record. Never drop the current work item, the acceptance criteria, or
  any blocker/dissent field.
- **Acceptance:** update the existing truncation test to assert the output **parses as JSON** and that
  `omitted_roles` names what was dropped. The current test asserts the corruption is deterministic —
  replace it, and say so in the PR description.
- **Forbidden:** raising the limit instead of fixing the algorithm.

#### P1.5 — HUMAN GATE: the first real mission (see §7 G2)

- **Needs from the owner:** one API key in the environment, a spending limit, and permission to make
  real calls.
- **Executor steps once authorized:**
  1. Create a throwaway repo with one genuinely failing test (not `tiny_pkg`).
  2. Run `hive-mind deliver --backend model` against it.
  3. Retain the complete receipt bundle, the mission report, and — critically — **the failures**. Expect
     several. Each failure is the highest-information artifact this project has ever produced.
  4. Write **one** results file: `docs/FIRST_REAL_MISSION.md` — what was attempted, what broke, what the
     receipts show. One file. (R4.)
- **Acceptance:** B-OPS-03 status changes only if a real, reversible delivery artifact exists with no
  deterministic substitution. If it fails, **the blocker stays open** and the failures are the deliverable.
- **Forbidden:** substituting a fake provider and calling it done (this is precisely the substitution
  B-OPS-03 was written to prevent); writing an adoption docket about the attempt.

---

### P2 — Collapse the fiction

**User-visible delta:** the README's promises equal the system's behavior.

#### P2.1 — Reduce the role system to what exists

- **Decision (made):** ship **three** honest roles — Explorer (reproduce), Builder (fix), Curator
  (verify) — and describe the other five as *planned*, not implemented. Do not implement five roles to
  justify a table.
- **Files:** `src/hive_mind_os/roles.py`, `src/hive_mind_os/mission.py`, `README.md`.
- **Steps:**
  1. Extract a `RoleExecutor` protocol so the `if role is X / elif` ladder in `run()` becomes a
     dispatch table. This is the extension point the branch name "harden-extensible-architecture"
     promised and did not deliver.
  2. Move the four inaction-only roles behind an explicit `PLANNED_ROLES` constant that the lifecycle
     skips, with a one-line log saying they are not implemented.
  3. Either map `default_capabilities` strings to `policy.Action` members and enforce them, or delete the
     field. A capability list that enforces nothing is worse than none.
- **Acceptance:** `mission.py`'s `run()` is under 200 lines; a test asserts every string in
  `default_capabilities` resolves to a `policy.Action` member (or the field is gone).
- **Forbidden:** deleting the *concept* of the eight roles from the architecture docs (it is a legitimate
  design target); writing prose playbooks for the five unimplemented roles.

#### P2.2 — Wire or freeze the unconsumed subsystems

- **Verified unconsumed by any production code path:** `VisionComplianceGate` (`vision.py`),
  `ClassicGptSimulationGate` (`classic_gpt.py`), the entire `package_system/` (7,342 lines from PR #27),
  and `contracts.validate_runtime_state` (440 lines, zero `src/` callers).
- **Steps:** for each, choose exactly one and record it in a **one-line** ADR entry:
  - **Wire it:** add a production caller in the same PR (R8), or
  - **Freeze it:** move it under `src/hive_mind_os/reference/` and add a module docstring reading
    "Reference implementation. No runtime consumer. Not a gate."
- **Recommendation:** wire `validate_runtime_state` (it is the best contract in the repo and the mission
  should assemble a state document to validate); freeze `vision.py`, `classic_gpt.py`, and
  `package_system/`.
- **Acceptance:** a test asserts every public symbol exported from `__init__.py` has either a caller in
  `src/` or a `reference/` path.
- **Forbidden:** deleting them (they encode real design thinking); leaving them ambiguous.

#### P2.3 — Fix or disable the experiment runner

- **Problem:** `experiment_runner.py:79-107` scores a challenger prompt with substring checks —
  `"Return only a JSON object" in prompt` (+0.25), `"receipt" in prompt.casefold()` (+0.10) — plus a
  scripted mission run that **never uses the prompt**. No challenger is ever shown to a model. In the one
  place this project's measurement rhetoric matters most, the measurement is keyword stuffing.
- **Steps:** either (a) make `FixtureMissionSurface.evaluate` actually run the challenger prompt through
  the configured backend on the fixture mission and score by outcome, or (b) have `hive-mind experiment
  run` exit non-zero with "evaluation surface not implemented" until it does.
- **Recommendation:** (b) now, (a) after P1 makes model runs real.
- **Acceptance:** no code path assigns fitness from a substring check.
- **Forbidden:** leaving it callable and scoring by keywords.

---

### P3 — Make verification the product

**User-visible delta:** `hive-mind verify` — usable against any agent's work, not just this system's.

This is the phase that turns the repo's best asset into something a stranger would install.

#### P3.1 — Standalone `hive-mind verify`

- **New:** `src/hive_mind_os/verify.py`, `tests/test_verify.py`, README section.
- **Contract:**
  ```bash
  hive-mind verify --repository <path> --spec <acceptance-spec.json> --output <bundle-dir>
  ```
  Seals the acceptance spec into the ledger **before** reading the working tree, runs the declared
  commands in the sandbox, checks the diff against declared paths, runs the AST test-weakening detector,
  and emits a receipt bundle with a single top-level verdict.
- **Why this works:** every primitive already exists (`curator.py` seal ordering, `receipts.py`,
  `sandbox.py`, the ADR-041 acceptance spec cherry-picked in P0.4). This phase is **composition, not
  invention**.
- **Key design rule:** it must work on a repository this system did not create. No `tiny_pkg`. No
  mission. No roles. Just: here is a diff, here is a sealed check, here is the verdict.
- **Acceptance:** verify runs against a repository with an agent-authored commit from *any* tool
  (Claude Code, Cursor, a human) and emits a bundle; a test proves the seal is written to the ledger at a
  lower sequence number than the first working-tree read.
- **Forbidden:** requiring the full 8-role mission; requiring the fixture; requiring network.

#### P3.2 — Close the two undocumented enforcement gaps

- **(a) Champion pointer** — `prompt_registry.py:226-234`: `champion_digest()` must reject any digest
  lacking a matching `kind: "promotion"` lineage record whose cited decision event still resolves in the
  ledger. Today a 3-line file write installs an arbitrary system prompt into the model backend with no
  record. **Cheapest fix, largest blast-radius reduction, and the only undocumented critical bypass.**
  - Acceptance: `tests/test_prompt_registry.py::test_raw_pointer_write_without_promotion_is_rejected` —
    write `champions.json` directly, assert `champion_prompt()` raises.
- **(b) Policy mutability** — `policy.py:85`: make `PolicyEngine` a frozen dataclass so raising authority
  requires constructing a new engine rather than assigning an attribute.
  - Acceptance: `tests/test_policy_invariants.py::test_autonomy_cannot_be_mutated_after_construction` —
    assert `FrozenInstanceError`.
- **(c) Ledger integrity** — add `prev_digest`/`row_digest` columns over
  `(sequence, run_id, event_type, actor, payload, created_at, prev_digest)` and verify the chain on every
  `events()` read. The SQLite triggers are droppable by a second connection (the docs admit this); a hash
  chain makes the rewrite *detectable*, which is the honest achievable goal locally.
  - Acceptance: a test drops the triggers, rewrites a row, and asserts `events()` raises on chain
    mismatch.
- **Forbidden:** claiming any of this is cryptographic authentication — it is local integrity. Say so in
  the receipts.

#### P3.3 — Receipts must declare what was NOT enforced

- **Problem:** a sandbox receipt attests argv, exit code, and a spec digest. A reader reasonably infers
  confinement that does not exist: the panel executed a write **outside** the sandbox root and an
  outbound TCP connection, and the receipt recorded `succeeded` with no indication.
- **Steps:** add to every sandbox receipt an explicit block:
  ```json
  "enforced": {"filesystem": "none", "network": "none", "resources": "posix-rlimit-only",
               "executable_identity": "name-allowlist-only"}
  ```
  and narrow the default `argv_allowlist` away from bare interpreters (or reject `-c`/`-m` for them), and
  validate **all** argv path-like tokens rather than only caller-declared `path_args`.
- **Acceptance:** a test asserts the block is present and that a `python -c` argv is rejected by default.
- **Forbidden:** claiming isolation the process tier does not provide (ADR-007 already says this
  correctly — make the *receipts* say it too).

---

### P4 — Ship it

**User-visible delta:** someone who is not the author can install and use this.

#### P4.0 — `hive-mind demo`: make the first five minutes end in a real patch

- **Problem:** the only command that does real work is hardcoded to a fixture that exists solely inside
  `tests/` and is never mentioned in the README. An independent reviewer running the documented
  quickstart on their own repository got a masked Windows path error in 1.34s and zero value. The same
  reviewer, after reverse-engineering `tests/fixtures/fixture_repo.py`, got a **correct 2-line patch,
  exit 0, in 4.65s** — the machinery works, it is just unreachable.
- **Steps:**
  1. Add `hive-mind demo` that builds the fixture repository itself (reusing
     `tests/fixtures/fixture_repo.py`), runs the delivery, and prints a **human-readable** summary —
     e.g. "Curator independently reproduced the fix. Published 3 artifacts to ./demo-out." Today a
     sabotage run dumps **131,122 bytes of JSON to stderr** with no summary line.
  2. Then print the identical command shape pointed at the user's own repository, with the honest
     caveat about what the scripted backend can and cannot do.
  3. **Rename `--backend scripted` to `--backend fixture-demo`.** It is not a general capability and its
     current name implies it is one.
- **Acceptance:** `hive-mind demo` succeeds offline from a clean clone in under 60 seconds and prints
  fewer than 20 lines to stdout.
- **Forbidden:** leaving the fixture reachable only from `tests/`; keeping the name `scripted`.

#### P4.05 — Make contribution structurally possible

- **Measured blocker:** `.github/governance/required-repository-rules.json` requires **2 approving
  reviews plus code-owner review**, and `CODEOWNERS` is `* @kb4beast` — a single maintainer. An outside
  contributor's PR **cannot merge under any circumstances**. The file itself concedes that
  one-maintainer review independence "is not resolved by configuration alone."
- **Steps:** drop required approvals to 1 until a second maintainer exists; add `CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CHANGELOG.md`, and issue/PR templates (`.github/` currently holds
  exactly 4 files, none of them these); define a **governance-lite tier** so a docs or typo PR does not
  nominally require a courtroom disposition, evidence from all eight roles, and an ADR.
- **Acceptance:** a hypothetical outside contributor can merge a typo fix by following one documented
  path with one approval.
- **Forbidden:** weakening the governance tier for changes to the kernel, policy, courtroom, or schemas —
  the tier split must be explicit about what stays heavyweight.

#### P4.1 — README rewrite around the new positioning
Lead with the positioning statement (§2.2), then a 60-second quickstart, then the status table from P0.5,
then architecture. Courtroom/dockets move to `docs/architecture/`.

#### P4.2 — Repository hygiene
`CONTRIBUTING.md` (currently absent), issue templates, `CODE_OF_CONDUCT.md`, and 3–5 genuinely
good-first-issues. `AGENTS.md` is 76 dense constitutional rules — add a short "Contributing as a human"
preface so a newcomer is not asked to internalize a constitution before fixing a typo.

#### P4.3 — First release
Tag `v0.7.0`, publish a GitHub release with honest notes (what works, what does not), and decide on PyPI.
There are currently **zero tags and zero releases** at version 0.6.0.

#### P4.4 — One real example, end to end
`examples/verify-an-agent-change/` with a real repository, a real agent-authored diff, and the resulting
bundle — runnable in under 5 minutes offline.

---

### P5 — Re-earn the governance

**User-visible delta:** the repository is navigable; the evidence that remains is evidence someone reads.

#### P5.1 — Archive the corpus
Move `evidence/phase*`, the phase5 receipts, and the superseded plan documents into a separate
`hive-mind-os-history` repository (or an `archive/` branch), preserving them intact — R3, not deletion.
Target: `evidence/` under 2× `src/` line count.

#### P5.2 — Retire the plan lineage
`docs/plan/00_OVERVIEW.md` and `01_POST_P13_OVERVIEW.md` get a header pointing to this plan.
`P14`–`P20` are formally withdrawn as a program; their *content* survives as the §7 gate list. The
`NEXT_SESSION_HANDOFF_OBSIDIAN_AGENT_REDESIGN.md` program (2,630 lines, Obsidian brain, memory planes,
telemetry, federation) is **deferred in full** until there is at least one user asking for it.

#### P5.3 — Make the blocker backlog the single source of truth
Keep `BLOCKERS.md` — the schema is genuinely good. Delete every competing status record. One file
answers "what is not done."

---

## 5. What to delete, defer, and keep

| Item | Disposition | Why |
|---|---|---|
| Curator blind-seal, receipts, sandbox receipts | **Keep — this is the product** | Novel, working, differentiating |
| Mission store, checkpoints, determinism | Keep | Well-built; will carry real payloads after P1 |
| ADR-041 acceptance specs | **Cherry-pick to main** | Highest-value item on the side branch |
| ADR-040 seal coverage, HTTPS-only, enqueue pinning | Cherry-pick | Real hardening, small |
| `custody.py`, `hard_isolation.py`, `model_turn_state.py` | Archive on branch | Solves problems with no users yet; breaks zero-dep contract |
| `package_system/` (7,342 lines) | Freeze under `reference/` | Zero consumers; duplicates role prose |
| `vision.py`, `classic_gpt.py` gates | Freeze under `reference/` | Zero consumers; audit caller self-reports |
| Phase 5A–5P, BGOV06/07 program | **Withdraw** | 78% meta-work; no user-visible delta |
| P14–P20 program | Withdraw as a program; keep as §7 gates | Unexecutable by agents; gate is human-only |
| Obsidian brain program (2,630-line handoff) | **Defer entirely** | No user has asked; would repeat the failure at 10× scale |
| `evidence/phase*` (274k lines) | Archive to history repo | R3 |
| Courtroom / dockets / founding sources | Keep as history, move out of README | Real provenance; wrong front door |

---

## 6. Honest scorecard of the current system

| Claim in README | Reality | Evidence |
|---|---|---|
| "Eight independent specialist agents" | 3 have runtime behavior; 5 are checked for inaction | `mission.py:960`, `roles.py` |
| "Autonomous delivery" | One hardcoded fix to one bundled fixture | `mission.py:66` |
| "Real model boundary composed by `hive-mind deliver`" | Model never sees repository content | `model_backend.py:205-215` |
| "Deny-by-default policy engine" | True for cooperative callers; `HiveKernel` never calls `.decide()`; autonomy is a mutable attribute | `runtime.py:86-91`, verified by execution |
| "Append-only ledger" | SQLite triggers a second connection can DROP (docs admit) | `ledger.py:45-52` |
| "Champion/challenger with no self-promotion" | `promote()` holds; raw pointer write bypasses it entirely | verified by execution |
| "23 sources and 84 atomic claims" | **Accurate** — regenerates exactly | `load_source_docket()` |
| "Tests and commit-pinned CI" | CI red on both branches; 4 Windows failures locally | run 30818413739; local run |
| Benchmarked quality | **The project's own published benchmark shows its lane losing to the trivial baseline: 0.400 vs 0.600** | `docs/benchmarks/RESULTS.md` |

On that last row, in fairness: the document itself states plainly that these measurements "authorize no
comparative quality or superiority claim," and the lane under test is the scripted fixture backend, not a
model. That honesty is genuinely admirable. But the adoption consequence is unavoidable — a visitor who
opens `RESULTS.md` sees the tool losing to the baseline on a per-task table where hive-mind fails
`missing-edge-case` (0.000) that the baseline passes (1.000), and wins nothing the baseline loses. Until
P1 makes a model lane real, **this file should not be linked from the README.**

The pattern: **claims about the governance layer are accurate and admirably self-limiting; claims about
the capability layer are ahead of the code.** The project's own audit says exactly this —
"Governance already exceeds capability" (`00_OVERVIEW.md:52`) — and then the roadmap did the opposite of
what that sentence implies.

---

## 7. Human gates (R5 — write one packet, then STOP)

An executor reaching any of these writes a single file naming what it needs and stops. It does **not**
build machinery against the gate.

| ID | Gate | Needed from a human | Blocks |
|---|---|---|---|
| **G1** | Branch fork resolution | Owner decision on P0.4 (archive + cherry-pick vs merge) | P0.4 |
| **G2** | First real model mission | API key, spend limit, permission | P1.5, B-OPS-03 |
| **G3** | External identity/signing authority | Non-agent-controlled credentials | B-GOV-02/03 |
| **G4** | External append-only retention | Storage account + recovery authority | B-GOV-04 |
| **G5** | Production pilot | Deployment account, scope, users, rollback authority | B-OPS-04 |
| **G6** | Comparator access | Licensing for benchmark comparators | B-OPS-05 |
| **G7** | Founding-source licensing | 7 video ingestions, 17 license resolutions | B-SRC-01..11 |
| **G8** | Independent human reviewer | A second person, or an explicit "solo project" declaration | Every "independent Judge" claim |

**G8 deserves emphasis.** The plan repeatedly requires "an independent Curator/Judge." The project's own
debt register admits every such identity to date is "one assistant … procedurally," and independence "is
not claimed." Either recruit a second human, or replace the requirement with something honest: a second
isolated agent session with a retained transcript, explicitly labeled as *procedural, not authenticated*
separation. Do not keep generating court records that the repo itself footnotes as non-independent.

---

## 8. Corrections ledger (what this review got wrong)

A review that never corrects itself was not a real review. These were caught by adversarial cross-checks
during this pass and are recorded rather than silently cleaned:

| Claim first made | Correction | How it was caught |
|---|---|---|
| "`HIVE_MIND_MODEL_*` appears in **zero** markdown files" | False. It appears **6 times in 3 files** (`P02_MODEL_ADAPTER.md` ×3, `P08_CURATOR_INDEPENDENCE.md` ×2, `ADR-012` ×1). Zero times in README/AGENTS, and never as a copy-pasteable recipe — the practical conclusion survives, the literal claim did not. | My grep searched `README.md docs/*.md`, missing `docs/plan/` and `docs/architecture/` subdirectories. Independent reviewer re-ran it correctly. |
| "~125,956 insertions on the side branch" | **118,764** against `origin/main`. My first number was measured against a stale local `main`. | Plan auditor regenerated from the correct base; I re-derived and confirmed both numbers. |
| "Six debt-reconciliation phases (5L–5P)" | **Five** (5L, 5M, 5N, 5O, 5P), plus BGOV06/07 as two further reconciliation tranches. | Plan auditor's enumeration. |
| "The champion pointer bypass defeats the promotion gate" | Imprecise. `promote()` **correctly refuses** the unauthorized promotion — I reproduced the refusal. The defect is narrower and still serious: `champion_digest()` never checks that a promotion happened, so the gate can be *walked around* by a file write rather than defeated. | My own reproduction attempt failed at the guard, forcing a more precise statement. |
| Implicit: "the security panel's findings are all novel" | Most were **already documented** by the project's own ADRs and blockers, sometimes verbatim. Only two (champion pointer, mutable `PolicyEngine.autonomy`) were undocumented; I reproduced both myself. | Explicitly hunting for the project's own admissions before crediting a finding as new. |

One claim I deliberately did **not** upgrade: §2's positioning recommendation is a *judgment*, not a
verified fact. I have no user research showing demand for "verifiable agent execution." Validate it
cheaply before committing engineering to it — publish the positioning statement and the P4.0 demo, and
see whether anyone engages — rather than treating it as established.

## 9. Definition of done for this plan

The program is complete when a stranger can:

1. `git clone`, run one command, and see it pass — on Windows and Linux.
2. Read the README in 60 seconds and correctly state what the tool does and does not do.
3. Run `hive-mind verify` against a change **some other agent** wrote and get a receipt bundle.
4. Point a real model at a real failing test and watch it fixed — or read an honest record of why not.
5. Find `CONTRIBUTING.md`, a tagged release, and an open good-first-issue.
6. See `evidence/` smaller than `src/`.

None of those six require a courtroom, a docket, an Obsidian vault, or a benchmark comparator. All six
are reachable in weeks by one executor following §4.
