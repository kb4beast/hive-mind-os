# ADR-008: External GitHub Delivery Boundary

- **Status:** Proposed for independent P07 court review
- **Date:** 2026-07-28
- **Case:** `CASE-P07-GITHUB-DELIVERY`
- **Originating work order:** `docs/plan/P07_GITHUB_DELIVERY.md`
- **Prior decisions:** ADR-003, ADR-005, ADR-007, ADR-011
- **Capability maturity:** implemented offline; live exact-head evidence required

Identifier note: P07 reserved this filename before P03 created
`ADR-008-WINDOWS-PROCESS-TREE-LIVENESS.md`. Both records are preserved. The complete
filename, not the duplicated ordinal, identifies each decision.

## Context

P05 and P06 produce a locally verified, durable delivery candidate. They do not push a
branch, create a pull request, observe an independent executor, or prove that declared
repository rules are active on GitHub. P07 introduces those external effects without
granting merge or deployment authority.

The boundary has three independent truth domains:

1. local Git proves the exact clean commit selected for delivery;
2. GitHub's versioned REST API reports the draft pull request, check runs, and rules;
3. repository evidence preserves canonical requests, responses, receipts, and digests.

TLS and a bearer token authenticate the session to GitHub, but the stored response is not
cryptographically signed by GitHub. A CI receipt therefore attests that the API reported
a GitHub Actions result bound to the exact head SHA. It does not prove provider identity
after capture, runner isolation from GitHub administrators, or the truth of a job that
does not itself test the claimed property.

## Operational source record

The implementation adapts response shapes and behavior from GitHub's official REST
documentation for [pull requests](https://docs.github.com/en/rest/pulls/pulls),
[check runs](https://docs.github.com/en/enterprise-cloud%40latest/rest/checks/runs),
[repository rules](https://docs.github.com/en/rest/repos/rules), and
[branch protection](https://docs.github.com/en/rest/branches/branch-protection), retrieved
2026-07-28. Requests pin `X-GitHub-Api-Version: 2022-11-28`.

At retrieval, the official `github/docs` repository `main` resolved to
`cd664a7b671173b1b4c35060017ad9d694f73297`. Its content-license blob was
`9238c8f9388066fe7cb3b308de35104bb3c9596b` and its code-license blob was
`6bc46813523b6b375bd5c31e2b8c2d5a6a4f55e9`. No documentation code or prose is copied.
P12 retains any broader source-ingestion obligation; these operational references do not
resolve the founding docket.

## Court record

- **Advocate:** a small stdlib client plus Git's existing sandbox boundary can deliver an
  exact commit with less credential and dependency surface than a forge SDK.
- **Cross-Examiner:** search for token persistence, request replay, duplicate PRs, mutable
  heads, check polling that treats absence as success, protection false positives, API
  shape drift, and authority expansion into merge.
- **Expert witness:** offline fake-transport tests reproduce documented response shapes;
  a real exact-head draft PR and its GitHub Actions receipts remain the external witness.
- **Judge:** a separately identified Judge must disposition the complete immutable P07
  candidate. This proposal cannot approve itself.

## Decision

1. Use `GitHubClient` over stdlib `urllib` with an injected transport seam. Tests make no
   network calls and use recorded minimal JSON fixtures.
2. Read the fine-grained token only from the configured environment variable. Git uses a
   per-process `http.extraheader`; the token is absent from argv, stored remotes, Git
   configuration, receipts, ledger events, and error text. On managed Windows hosts where
   Schannel cannot reach a revocation service, the same transient configuration disables
   only Schannel's revocation lookup; certificate-chain and hostname verification remain
   enabled. The live receipt and this ADR disclose that residual instead of inheriting an
   unrecorded ambient Git setting.
3. Push the exact clean workspace `HEAD` to one explicitly named branch. Adopt an existing
   remote branch only when it already resolves to the same SHA; a different SHA fails
   closed.
4. Require repository-level policy before push or draft-PR creation. `MERGE_PULL_REQUEST`
   and deployment remain outside this boundary.
5. Bind push and PR intents to owner, repository, base, branch, title, and exact head SHA.
   Use P06's durable intent index so replay adopts the recorded result instead of creating
   a second PR.
6. Search for an existing open draft with the same owner, branch, base, and exact SHA
   before creating one. A non-draft or SHA mismatch fails closed.
7. Poll checks with explicit attempt and interval bounds. Zero, pending, malformed,
   unsuccessful, or timed-out observations never become success receipts.
8. Preserve each completed check's name, status, conclusion, times, workflow run ID and
   URL, exact head SHA, response-object digest, and validated tool receipt with
   `verifier="github-actions"`.
9. Fetch active rulesets and classic branch protection, normalize both, and compare them
   field-by-field to `.github/governance/required-repository-rules.json`. A mismatch is
   evidence and a blocker, not a successful verification.
10. Keep HTTPS remote materialization disabled by default. Callers must opt in and the
    adapter accepts only credential-free `https://github.com/<owner>/<repo>.git` URLs.

## Threats and residuals

| Threat | Control | Residual obligation |
|---|---|---|
| Token disclosure | Environment-only read, transient extra header, redacted exceptions, persistence regression | Host process inspection and secret brokering remain operational concerns |
| Duplicate remote effect | P06 intent digest plus exact remote-state adoption | An out-of-band actor can still create a confusing PR and cause a fail-closed stop |
| Mutable or wrong PR head | Exact SHA checked on create/adoption and every CI receipt | A later force-push is prevented only when host rules are active |
| Missing checks treated as green | Non-empty completed set required; bounded timeout is a failed receipt | Workflow configuration can still omit a required semantic test |
| False protection claim | Live normalized comparison and committed mismatch report | Administrator bypasses and single-maintainer independence must be disclosed separately |
| API/provider forgery | HTTPS chain and hostname validation, GitHub token, versioned API, raw response digest | The managed Windows live runner cannot perform Schannel revocation lookup; there is no GitHub-signed response or externally authenticated verifier identity; B-GOV-02/03 remain open |
| Authority expansion | Repository-level push/draft only; no merge method | A human or separately authorized system must merge |

## Acceptance evidence

- Offline tests cover request construction, exact-head parsing, durable idempotency,
  pending-to-complete polling, fail-closed timeout, token persistence and redaction,
  protection match/mismatch, policy denial before effects, guarded remote materialization,
  and the mission-to-delivery integration boundary.
- `scripts/live_github_delivery.py` can deliver only the current exact commit, opens or
  adopts a draft, waits for checks, records receipts, and never merges.
- P07 exits only after the exact candidate has a real draft PR, green GitHub checks, a
  committed CI receipt set, a committed protection observation, the full local gate, one
  post-commit audit, and one consolidated independent review.

## Rollback

Revert the local P07 commits. Close the draft PR and preserve its number, URL, remote branch
history, CI receipts, protection report, failures, and dissent as append-only evidence.
Token rotation is required if disclosure is ever reproduced. A protection change is
reverted by a repository administrator using the recorded pre-change observation.

This decision does not establish production readiness, release readiness, source
completeness, structural Curator independence, signed provider identity, hostile-code
isolation, or superiority.
