# ADR-090: Two-repository external pilot without a required game platform

## Status and source

Adapted for review. The source is the repository owner's explicit 2026-09-21
directive: "forget roblox for now, its to complex. lets pick a new project." The
owner selected Coupon Hive as the first application and requested a smaller
replacement project, which is now Reese's Rainbow Web.

## Decision

N32 qualifies two distinct externally admitted repositories through the generic
`external` pilot mode. A particular domain or game platform is not a prerequisite.
Each target still needs an exact commit and tree, an acceptance and runtime profile,
reuse rights, isolated target state, scoped delivery and cleanup authority, and real
receipts proving that it runs without Hive Mind OS.

The owner selected this first candidate pair. Selection records scope; it is not a
host-issued target profile or an external authority receipt.

- Coupon Hive at `f9b695d90ec74764709a1547d60821910ece5705`, tree
  `9582c2410f20c916b580d7d4704b6263360c0631`.
- Reese's Rainbow Web at
  `main@44b22e5f88a3f3a9e6656a48cea7787c5d20ab4e`, tree
  `af67971e1b7f9f920a01cc59176435fba142edf9`, after PR #1 merged. The merged
  tree is identical to the independently reviewed PR head
  `fb5d9a84780dd9f6e4c3f46352bdd3beec141d4e`.

Roblox adapters and N26/N27 evidence remain available as a separately qualified
optional domain. This decision does not claim Roblox runtime or production support.

## Rationale and cross-examination

The typed pilot runtime already requires two distinct externally receipted subjects
for `mode="external"`; it does not require one of them to be Roblox. Keeping Roblox
as an N32 prerequisite would add accounts, Studio automation, device testing,
assets, persistence, multiplayer, and publishing concerns that are unrelated to
testing the operating system's two-tenant repository workflow.

The main risk is that two small repositories provide narrower evidence than a game
platform. The pilot verdict must therefore stay scoped to the declared repository,
runtime, and acceptance profiles. It cannot be generalized to Roblox, arbitrary
hostile repositories, public deployment, or production superiority.

Rejected alternatives:

- Keeping Roblox mandatory conflicts with the current owner scope and delays the
  generic external-pilot evidence.
- Using only one repository would remove the existing cross-tenant isolation burden.
- Shortening the 72-hour observation or accepting synthetic receipts would weaken
  the production evidence bar.

## Acceptance and rollback

The existing `PilotPrerequisites` and `PilotPlan` checks remain unchanged: two
distinct admitted targets, a configured Whole-OS host, scoped delivery authority,
an admitted N30 candidate, attested runtime evidence, and a minimum 72-hour window
are still required. `tests.test_pilot_runtime` records schema compatibility for two
non-Roblox subjects. It is not cross-tenant, runtime, delivery, N30, elapsed-window,
restart, or rollback qualification evidence.

Rollback reverts this record and its N32 documentation changes. It does not alter
target repositories or delete retained evidence. A later Roblox pilot requires a
new explicit owner scope and the existing N27 runtime evidence.

The independent cross-examination and final disposition are retained in
`ADR-090-TWO-REPOSITORY-EXTERNAL-PILOT-REVIEW.md`.
