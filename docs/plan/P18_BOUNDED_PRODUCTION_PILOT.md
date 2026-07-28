# P18 — Bounded Production Pilot

Status: pending in `01_POST_P13_OVERVIEW.md` | Depends on: P14–P17 and applicable source appeals | Unlocks: P20

## 1. Objective

Address `B-OPS-04` by operating one explicitly bounded product scope under real conditions
and retaining independent reliability, recovery, safety, cost, and customer-outcome evidence.

## 2. Required reading

1. `docs/plan/01_POST_P13_OVERVIEW.md`
2. `docs/plan/P14_REAL_PROVIDER_CAPABILITY_APPEAL.md`
3. `docs/plan/P15_AUTHENTICATED_IDENTITY_AND_RECEIPTS.md`
4. `docs/plan/P16_EXTERNAL_EVIDENCE_RETENTION.md`
5. `docs/plan/P17_HARD_ISOLATION.md`
6. `docs/plan/BLOCKERS.md` (`B-OPS-04` and applicable `B-SRC` rows)
7. `docs/architecture/HARDENED_VISION_CONTRACT.md`

## 3. Prerequisites and authority

- Branch: `phase/P18-bounded-production-pilot`.
- P14–P17 have permitting dispositions.
- Every source/license obligation used by the pilot is verified or its dependent behavior is
  excluded.
- A human approves users/tenants, environment, duration, spend, data classes, credentials,
  change window, rollback authority, and emergency-stop owners.

## 4. Scope and design constraints

- Define the exact supported provider, model, repository/task class, operating system,
  isolation tier, user cohort, and exclusions.
- Publish measurable SLOs for success, latency, availability, evidence completeness,
  recovery time/objective, cost, safety, and customer outcome.
- Add telemetry, alerting, health/readiness, capacity controls, incident classification,
  backup/restore, upgrade, rollback, and emergency-stop runbooks.
- Use canary or similarly bounded exposure. Capability never expands pilot authority.
- Preserve failures, manual interventions, aborted runs, customer feedback, and rollback.
- Keep production readiness distinct from a successful pilot.

## 5. Deliverables

- Pilot charter and authority envelope.
- SLOs, safety/regression budgets, held-out outcome measures, dashboards, and alerts.
- Deployment, rollback, incident, backup/restore, key rotation, upgrade, and support runbooks.
- Versioned release candidate and bill of materials.
- Raw operational/outcome evidence, P18 audit, pilot court, and blocker updates.

## 6. Required tests and exercises

Run deployment/rollback, backup/restore, provider outage, identity/retention outage, worker
crash, stale lease, isolation failure, quota/spend exhaustion, corrupted evidence, secret
rotation, bad release, alert delivery, and emergency-stop exercises. Verify no action exceeds
the pilot authority and all failures remain observable and recoverable.

## 7. Exit criteria

- All deterministic gates pass.
- The bounded pilot completes its declared observation window.
- SLO, recovery, safety, cost, evidence-completeness, and customer-outcome thresholds pass
  with raw retained receipts; failures and dissent remain visible.
- Independent Curator reproduces sampled outcomes and disaster recovery.
- Separate Judge and Orchestrator may permit only the tested pilot scope.
- `B-OPS-04` is resolved narrowly; general release readiness remains P20.

## 8. Evidence, rollback, and forbidden shortcuts

Retain authority, deployment digests, telemetry exports, incidents, interventions, feedback,
costs, recovery exercises, audit, court records, and dissent. Rollback stops the pilot,
revokes its authority, restores the prior release, verifies state/evidence integrity, and
preserves all records.

Do not use synthetic traffic as customer-outcome proof, erase failed runs, expand the cohort
after success, or describe a bounded permit as general production readiness.

