# P07 — GitHub Delivery: Push, Draft PR, CI Receipts, Protection Verification

Status: tracked in `00_OVERVIEW.md` | Depends on: P05 (P06 strongly recommended) | Unlocks: real A3 operation

## 1. Objective

Extend delivery beyond the local filesystem: push the mission branch to a real GitHub
repository, open a draft pull request, ingest the resulting GitHub Actions check results as
independent execution receipts, and verify that the repository's declared protection rules
are actually active on the host — closing the long-standing "host-side rule activation
remains explicitly unverified" obligation in `BLOCKERS.md`. Exit requires one real draft PR
with green CI, produced end-to-end by the pipeline.

## 2. Rationale

A pull request is the constitutional delivery artifact ("the result is a reviewable pull
request"), and pinned CI on GitHub's runners is the only genuinely independent executor
available to a single-operator project — every other "independent" identity is procedural.
Wiring CI results in as receipts converts procedural independence into actual independence
cheaply. This phase introduces the first real external side effects, so it leans on P06's
idempotency table (a re-run must not open duplicate PRs) and ships with an ADR for the
external-delivery trust boundary.

## 3. Required reading

1. `docs/plan/00_OVERVIEW.md`
2. `src/hive_mind_os/git_adapter.py`, `src/hive_mind_os/mission.py`,
   `src/hive_mind_os/mission_store.py` (if P06 landed)
3. `src/hive_mind_os/policy.py` — note: `Action.OPEN_PULL_REQUEST` requires
   `AutonomyLevel.REPOSITORY`; `MERGE_PULL_REQUEST` is an `EXTERNAL_GRANT_ACTION` and
   stays denied — merging is out of scope permanently for the agent.
4. `src/hive_mind_os/receipts.py`
5. The repository-protection contract and its tests (search:
   `grep -rn "protection" src/ tests/ --include=*.py -l`) — the declared-rules side
   already exists; you are adding live verification.
6. `.github/workflows/` (pinned CI that will produce the check results)
7. `docs/plan/BLOCKERS.md` (the row this phase closes)

## 4. Prerequisite verification

```bash
python -m pytest -q tests/test_mission.py    # P05 green (plus test_mission_store.py if P06 landed)
git remote -v                                # a GitHub remote exists for this repo
```

## 5. Scope

In scope:

- `GitHubClient` over stdlib `urllib` against the GitHub REST API: push via `git` with a
  token-bearing HTTPS remote configured per-invocation (never persisted), create draft
  PR, poll check runs, fetch protection/ruleset state.
- CI-result ingestion as receipts bound to the head SHA.
- `verify_protection()` comparing declared rules to live API state, recorded as evidence.
- Fake-transport tests for all logic; a manual live script for the real run.
- `Action.OPEN_PULL_REQUEST` policy integration at `AutonomyLevel.REPOSITORY`.
- ADR for the external-delivery trust boundary.

Non-goals:

- No merge, ever, by the agent (external grant). No deploy. No GitHub App or webhooks
  (polling only). No comment/review automation. No multi-remote or non-GitHub forges.
  No secret broker — a fine-grained PAT via env var with redaction, documented as
  interim in the ADR.

## 6. Design constraints

- **Token handling.** Token read from the env var named by `HIVE_MIND_GITHUB_TOKEN_ENV`
  (default `GITHUB_TOKEN`); required scopes documented (fine-grained: contents
  read/write, pull requests read/write on the target repo only). The token must never
  appear in: receipts, ledger, exception text, git config on disk, or the remote URL as
  stored (`git push` uses a one-shot `http.extraheader`-style credential or an
  in-memory askpass helper — pick one, document it, and test that `git config --list`
  and `.git/config` never contain the token).
- **Transport seam.** Same pattern as P02: `GitHubTransport` protocol; tests use
  recorded JSON fixtures; zero live calls in `tests/`.
- **Idempotency.** Push and PR-creation intents register in the P06 idempotency table
  (key = intent digest binding repo, base, head SHA, branch, title). Resume or re-run
  with the same digest returns the recorded receipt instead of acting. If P06 has not
  landed, this phase must implement the same dedup against a receipt-store lookup and
  note it in the ADR — duplicate PRs are a hard failure either way.
- **CI receipts.** After PR creation, poll check runs for the head SHA (bounded
  attempts, configurable interval, fail closed on timeout with recorded state). Persist
  for each completed check: name, status, conclusion, started/completed times, the
  workflow run id and URL, and the digest of the fetched JSON — stored content-addressed
  like other receipts and marked `verifier="github-actions"` to distinguish an external
  executor from local verification. The ADR states plainly what this does and does not
  authenticate (no signature verification of GitHub's response beyond TLS; provider
  authentication remains a later stage, consistent with ADR-005's residual-risk table).
- **Protection verification.** `verify_protection(owner, repo)` fetches live branch
  protection/rulesets, compares against the repository's declared desired rules, and
  writes an evidence artifact (match/mismatch per rule). Mismatch → the delivery
  proceeds only if policy allows (default: proceed for draft PRs but record the
  mismatch as a blocker update; never claim the obligation closed on mismatch).
- **Policy.** Opening the PR consults
  `PolicyEngine.decide(Role.BUILDER, Action.OPEN_PULL_REQUEST, risk)` with the engine
  constructed at `AutonomyLevel.REPOSITORY` for this flow; the default engine level
  elsewhere stays `SANDBOX`. Denial fails closed before any push.
- **URL unlock.** `git_adapter.materialize` gains an explicit opt-in for HTTPS GitHub
  URLs (`allow_remote=True` plus host allowlist `github.com`), keeping the P04 default
  (local-only) intact.

## 7. Deliverables

New files:

- `src/hive_mind_os/github_adapter.py` — `GitHubClient`, `CheckResult`,
  `ProtectionReport`, typed errors; `push_branch()`, `open_draft_pr()`,
  `poll_checks()`, `verify_protection()`.
- `tests/test_github_adapter.py` + `tests/fixtures/github/` recorded responses.
- `scripts/live_github_delivery.py` — manual end-to-end: runs the fixture-or-real
  mission with `--backend scripted` against a designated target repo, pushes, opens the
  draft PR, polls checks, writes all receipts. Clearly marked not-CI.
- `docs/architecture/ADR-008-EXTERNAL-DELIVERY-BOUNDARY.md` — trust boundary, token
  posture, idempotency, what CI receipts attest, residual risks.

Modified files:

- `src/hive_mind_os/git_adapter.py` — guarded remote-URL materialization and push
  support via the sandbox (git remains the executor; the runner's env allowlist passes
  the askpass variable through).
- `src/hive_mind_os/mission.py` — optional delivery target: when a GitHub target is
  configured, Integrator-stage delivery pushes and opens the draft PR, appending the CI
  receipt polling step.
- `docs/plan/BLOCKERS.md` — update the protection-verification row: `resolved` with a
  pointer to the evidence artifact, or narrowed to what remains (e.g. "rules active;
  independent-approval requirement unverifiable with one maintainer").

## 8. Implementation steps

1. Verify prerequisites; branch `phase/P07-github-delivery`.
2. Implement `GitHubClient` with the transport seam; record minimal REST fixtures
   (create PR, list check runs, get rulesets/protection) from the public API docs'
   response shapes.
3. Implement token-safe push (askpass approach) and prove with a test that token bytes
   never land in workspace `.git/config` or receipts.
4. Implement PR creation + check polling + receipt persistence with idempotency.
5. Implement `verify_protection` and its evidence artifact.
6. Wire into `mission.py` behind an explicit delivery-target config; scripted offline
   tests cover the full flow against fakes.
7. Run `scripts/live_github_delivery.py` for real against this repository (or a scratch
   repo you control): one real draft PR, CI green, receipts stored. This live run is the
   exit bar.
8. Update `BLOCKERS.md`; write ADR-008.
9. Gates, audit `evidence/audits/P07-post.json`, status updates, completion record.

## 9. Required tests

`tests/test_github_adapter.py` (all offline against fakes):

1. Draft PR creation builds the correct request and parses the response (number, URL,
   head SHA binding).
2. Idempotency: same intent digest twice → one create call on the fake, second returns
   recorded receipt.
3. Check polling: pending → completed transition across polls; receipt captures
   conclusion and run id; JSON digest recorded.
4. Poll timeout → fail closed with recorded state; no success receipt.
5. Token redaction: sentinel token never appears in any receipt, ledger event, error
   string, or the workspace `.git/config` after a push attempt (fake transport for API;
   local bare repo as push target for the git side).
6. `verify_protection` match and mismatch paths produce correct `ProtectionReport`
   evidence; mismatch does not mark the blocker resolved.
7. Policy: engine below `REPOSITORY` → no push, no PR, denial recorded.
8. Remote materialization: non-GitHub host or `allow_remote=False` → rejected.

## 10. Exit criteria

```bash
python -m pytest -q tests/test_github_adapter.py   # all pass
python -m pytest -q && python -m ruff check src tests && pyright   # clean
test -f docs/architecture/ADR-008-EXTERNAL-DELIVERY-BOUNDARY.md
grep -n "protection" docs/plan/BLOCKERS.md         # row updated with evidence pointer
```

Live exit (recorded in completion record, not CI): URL of one real draft PR opened by the
pipeline with green checks; digest of the stored CI receipt set; digest of the
`ProtectionReport` artifact committed under `evidence/`.

## 11. Evidence

- `evidence/audits/P07-post.json`, the `ProtectionReport` artifact, and the live-run
  receipt set committed.

## 12. Rollback

Revert the branch; close the draft PR (leave it as evidence — do not delete the remote
branch's history from the ledger). ADR-008 is superseded, not deleted, if the boundary
changes.

## 13. Handoff

Later phases may assume: A3 delivery is real (branch → draft PR with CI receipts);
GitHub Actions is the independent executor of record; protection state is verified
evidence, not declaration; all external side effects are idempotent and token-safe.

## 14. Forbidden shortcuts

- No merging, no `MERGE_PULL_REQUEST` policy relaxation, no auto-approve.
- No live API calls or credentials in `tests/`.
- No storing the token anywhere on disk, however temporarily.
- Do not mark the protection blocker resolved on a mismatch or a partial check.
- Do not open non-draft PRs in this phase.
