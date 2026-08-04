# P14 — Real-Provider Capability Appeal

> **Withdrawn as an executable phase by P5.2 (2026-08-03).** Do not schedule this
> work. Its required external authority is retained in
> [Human Authority Gates](../architecture/HUMAN_AUTHORITY_GATES.md).

Status: withdrawn | Historical dependencies: P05, P07, P08

## 1. Objective

Close `B-OPS-03` by independently reproducing one real-provider, objective-to-reversible-
delivery mission through all eight roles without deterministic substitution for the model
capability under test.

## 2. Required reading

1. `docs/plan/01_POST_P13_OVERVIEW.md`
2. `docs/plan/P02_MODEL_ADAPTER.md`
3. `docs/plan/P05_VERTICAL_SLICE.md`
4. `docs/plan/P07_GITHUB_DELIVERY.md`
5. `docs/plan/P08_CURATOR_INDEPENDENCE.md`
6. `docs/plan/BLOCKERS.md` (`B-OPS-03`, `B-GOV-02`, `B-GOV-03`)
7. `docs/architecture/ADR-010-P05-VERIFICATION-AND-FAILURE-EVIDENCE.md`

## 3. Prerequisites and authority

- Branch: `phase/P14-real-provider-capability`.
- The deterministic suite and exact `main` audit pass.
- A human supplies the provider kind, model ID, key through an environment variable,
  maximum spend, allowed repository, and expiry for the real-call authority.
- The objective and acceptance criteria are fixed before any model call.
- Missing credentials or authority records a blocked attempt; it is not a test failure and
  cannot be replaced with a fake provider.

## 4. Scope and design constraints

- Use the existing provider-neutral `ModelBackend` and the same capability boundaries as
  the scripted mission.
- Use a disposable or explicitly approved repository with a reproducible failing test and
  a reversible change.
- Run every mandatory specialist role. Builder and Curator use separate materializations.
- Seal Curator acceptance criteria before candidate access.
- Correlate every model, policy, sandbox, Git, delivery, and verification receipt to one
  mission and exact repository SHAs.
- Record provider/model labels truthfully but do not claim authenticated provider identity;
  that remains P15.
- Preserve failed attempts and actual costs. Never commit secrets or raw sensitive prompts.
- Produce a delivery artifact and rollback proof; do not deploy or merge the artifact.

## 5. Deliverables

- A manual capability-appeal command or script that invokes the existing delivery path.
- Redaction, correlation, non-substitution, authority-expiry, and failed-run regressions.
- Content-addressed evidence under `evidence/capability/P14/`.
- A P05 appeal court record and audit `evidence/audits/P14-post.json`.
- Narrow `B-OPS-03` status update only after independent reproduction.

## 6. Required tests

1. Missing/expired authority fails before network or spend.
2. Fake, scripted, replayed, or mismatched provider evidence cannot satisfy the appeal.
3. Every issued call and side effect is correlated and budgeted.
4. Secret sentinels never enter output, receipts, logs, exceptions, or committed artifacts.
5. Curator materializes independently and re-executes sealed acceptance checks.
6. Failed runs retain complete reachable evidence but publish no delivery artifact.
7. Rollback restores the base tree and is independently verified.

## 7. Exit criteria

- Deterministic full suite, Ruff, and Pyright pass.
- One authorized real-provider mission completes all eight roles.
- Its reversible artifact, request/response digests, receipts, budgets, provider/model
  configuration, exact SHAs, Curator reproduction, and rollback all validate.
- An independent Curator reproduces the artifact from retained evidence.
- A separate Judge issues `adopt` or `adapt`; Orchestrator permits delivery.
- `B-OPS-03` is resolved only for the exact provider, model, repository class, and capability
  demonstrated. P15–P20 and source blockers remain open.

## 8. Evidence, rollback, and forbidden shortcuts

Retain the authority envelope without secrets, mission report, artifacts, receipts, costs,
failed attempts, review dispositions, and final audit. Rollback revokes the temporary
authority, removes disposable provider/runtime state, and preserves all evidence.

Do not use a deterministic fallback, equate TLS with provider authentication, reuse Builder
conclusions as Curator evidence, broaden authority after success, or claim production
readiness.
