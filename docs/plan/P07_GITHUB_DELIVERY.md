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

---
## Completion record

- Date (UTC): 2026-07-28T01:40:00Z
- Executor: Codex primary Builder/Integrator. The complete candidate still requires the
  one consolidated independent Curator, Judge, and Orchestrator review; it does not
  approve itself.
- Branch and audited implementation commit: `phase/P07-github-delivery`;
  `1b47163a8da8f3ba30d77889b6a1366fac72086a`.
- Development gate: 277 passed, 2 skipped, 1,722 subtests on the audited commit; Ruff
  passed; Pyright 1.1.411 passed with 0 errors.
- Audit: `evidence/audits/P07-post.json`; canonical digest
  `sha256:8defb16adba482b1e8ee9cf07296e244741c4ad8513c06f438858a524743a9ef`;
  `complete=true`; failures none; audited head
  `1b47163a8da8f3ba30d77889b6a1366fac72086a`.
- Live delivery: draft PR
  [#18](https://github.com/kb4beast/hive-mind-os/pull/18), exact head
  `1b47163a8da8f3ba30d77889b6a1366fac72086a`. The pipeline created the branch and
  draft PR; it did not merge or deploy.
- CI evidence: 17 completed check-run observations across the push and pull-request
  event paths, all accepted (`success`, plus one dependency-review `skipped` observation
  from the push event). The canonical check-list digest is
  `sha256:7d7559c9f23961b689b69bd699b3cfe898ce54a6b97bba4769c2f1d0d46cc090`.
  `evidence/live/P07/live-run.json` has raw-file digest
  `sha256:aa0e2d0945851030ddd466cad21aaa4f1c75b2fa87c4ea5befde564646ee127e`.
- Protection evidence: the pre-change report
  `sha256:def2f4345229b9091e41fe490e3eea3ad3c382ce91feb6aa85fab940b4016079`
  preserves the exact mismatch. After repository-admin activation, report
  `sha256:08a83cef968780637af62692028800ae7d612766a8a33a2ecf141a73b9fa16e7`
  matches every declared rule. B-GOV-01 is resolved for activation and verification.
  One-maintainer review independence and administrator bypass remain explicit and are
  not converted into an independence claim.
- Token posture: a byte scan of every P07 live evidence file found zero occurrences of
  the bearer token or its Git Basic-auth encoding. Git remotes and configuration did not
  persist the token.
- Reproduced live-boundary repairs:
  - Codex desktop bookkeeping refs exceeded Windows path limits during local staging;
    the adapter now excludes only `refs/codex`, with a regression.
  - An empty Git environment omitted Windows runtime/TLS requirements. The adapter now
    passes `SYSTEMROOT`, binds Schannel explicitly, retains certificate-chain and hostname
    checks, and records the managed host's unavailable revocation lookup.
  - Python 3.14 strict X.509 parsing rejected the trusted managed interception CA's legacy
    encoding. The REST transport clears only `VERIFY_X509_STRICT`; chain, root, and
    hostname validation remain required and tested.
  - Git credentials were initially scoped to the URL without `.git`, so authenticated
    push did not receive the header. The header is now scoped to the exact remote URL.
  - GitHub's CodeQL check uses `/runs/<id>` rather than an Actions job URL; both documented
    live URL shapes are now parsed and receipted.
- Failed attempts caused no PR duplication. One branch created at
  `bf7ca0c14307e049bfdf3c73a3358e7d6596a642` before REST transport failure was removed
  only after confirming it had no PR; the commit remains recoverable by SHA. PR #18 was
  created once and later exact-head runs adopted it.
- New blockers: none. Existing source, authenticated-identity, external-ledger,
  hostile-code isolation, and operational obligations remain open.
- Capability boundary: P07 establishes idempotent exact-head branch delivery, one draft
  PR, externally observed GitHub checks, and verified host rules. It does not establish
  release or production readiness, independent human approval, source completeness,
  signed provider identity, merge authority, deployment authority, or superiority.

### Consolidated-review appeal

- Challenged exact candidate:
  `ba6c8bfaed29bfafa5b4f62268652ed32443c6d3`.
- The independent Curator issued `BLOCK` after reproducing an active ruleset that included
  `~DEFAULT_BRANCH` but explicitly excluded `refs/heads/main`; the verifier ignored the
  exclusion and returned an empty mismatch set. The Curator also found that the declared
  rules file and its governance test still asserted the superseded
  `not_verified_on_remote` state. The independent Judge issued `adopt/PERMIT`, and the
  independent Orchestrator issued `READY/PERMIT`; the concrete Curator counterexample
  controls and all three dispositions remain preserved.
- Repair: ruleset applicability now requires well-formed include and exclude lists,
  rejects an exact/default-branch exclusion, and treats wildcard exclusions as ambiguous
  rather than assuming they do not match. Excluded, malformed, missing, or ambiguous
  conditions therefore cannot establish active protection. Regression subtests preserve
  the exact counterexample and malformed variants.
- Truth-contract repair: `.github/governance/required-repository-rules.json` now binds
  `verified_on_remote` to the exact committed post-change protection report and retains
  the one-maintainer/admin-bypass residual. The governance test recomputes the evidence
  digest. ADR-004 preserves its original Stage 0 state and records the P07 supersession.
- Repaired-candidate deterministic validation: 278 passed, 2 skipped, 1,726 subtests;
  focused GitHub/governance tests 18 passed with 8 subtests; Ruff passed; Pyright 1.1.411
  passed with 0 errors. Delivery remains blocked until a fresh consolidated Curator,
  Judge, and Orchestrator review permits the repaired exact head.

### Consolidated-review appeal 2

- Challenged exact candidate:
  `b91f7550f8f5d150ac7cd698653345da473bd7be`.
- The independent Curator issued `PERMIT`, and the independent Judge issued
  `adopt/PERMIT`. The independent Orchestrator issued `BLOCK` after reproducing a
  late-materialization race: one visible completed successful check caused
  `poll_checks()` to return before a second declared required check appeared and failed.
  The concrete fail-open counterexample controls; all three dispositions remain
  preserved.
- Repair: `poll_checks()` now requires the declared required-check names and cannot
  return until every one is visible and terminal with an accepted result. Missing and
  nonterminal required names are included in the timeout observation and exception.
  `deliver()` validates and binds the desired-rules check set before any push or pull
  request side effect. The regression presents one completed success first and a late
  required failure second; polling makes two observations and raises
  `CheckRunFailed`.
- Audited repair implementation:
  `2eee66d3636fa5ed5d618510b1bbf0d25be729e7`. Focused GitHub, mission, and governance
  validation passed 33 tests and 8 subtests; Ruff passed; Pyright passed with 0 errors.
  The fresh audit `evidence/audits/P07-post-appeal2.json` is complete with no failures,
  passed 279 tests, and has canonical digest
  `sha256:d7744c41aaaa2817781e2f6b3952470c9624d6a8f63d252dad44c47e6f880408`.
- Three incomplete audit attempts are preserved as adverse operational evidence:
  `P07-post-appeal2-failed.json` (`sha256:5cdda2a6219685013d8455881563b57530f765ec37ce7cd6d25afe03c9bb8375`),
  `P07-post-appeal2-failed-retry.json`
  (`sha256:b2805860398ef9ce0ac388cc0dd37e01df1f5ab6a9b6ec4de64925f66db908bd`),
  and `P07-post-appeal2-failed-import-path.json`
  (`sha256:aecc8fa1181da6a9ffbc0abe87985ab0624ef11cfd53c1ff9d3c6d4ce2f0893f`).
  The audit CLI had resolved an older editable worktree with a 300-second command
  timeout; pinning `PYTHONPATH` to this candidate's `src` restored the intended
  1,200-second audit budget. These attempts do not override the complete audit.
- Delivery remains blocked until a fresh consolidated Curator, Judge, and Orchestrator
  review permits the repaired exact head. No release-readiness, independent-human-
  approval, source-completeness, signed-provider-identity, merge-authority,
  deployment-authority, or superiority claim is made.

### B-GOV-06 administrator-enforcement addendum

- On 2026-08-03, the repository adapter and a separate GitHub CLI REST capture both observed every
  declared rule and `enforce_admins=true` on `main`.
- The adapter report is
  `sha256:74735dc048094b26deee7b17b58a465b00c649b0a9db082eb793ac324bec9041`;
  the bounded reconciliation receipt is
  `sha256:9a2e540a20d7fb83a84157031a63de42b4774c95c450a6e93c8069af48430188`.
- This supersedes only the current host-setting residual. `B-GOV-06` remains open until PR #48
  completes a protected `main` delivery without bypass. `B-GOV-07` and independent-human approval
  remain unresolved.
