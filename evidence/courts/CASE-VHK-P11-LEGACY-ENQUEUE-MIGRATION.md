# Case: VHK Phase 11 legacy enqueue migration

## Claim

The `legacy-enqueue-v1` adapter can add a separate kernel migration binding while preserving
the existing legacy enqueue contract and scheduler execution authority.

## Roles and evidence

| Participant | Finding |
| --- | --- |
| Architect | Selected `enqueue` because it is deterministic ingress; `deliver`, `resume`, and projection lack kernel parity. |
| Builder | Added an outer adapter, separate kernel state, versioned event binding, and explicit rollback mode. |
| Integrator | Confirmed parser, mission ID, scheduler payload, stdout, and legacy database boundaries are preserved. |
| Steward | Confirmed legacy worker recovery and effect-adoption tests remain the authority for execution. |
| Curator | Procedural reproduction remains required after the full gate; it is not externally authenticated. |
| Judge | Owner authorization permits local Phase 11 `adapt` work only; no release or independent-human disposition is issued here. |

## Acceptance and rollback

The required parity facts are covered by `tests/test_cli_enqueue.py`; recovery is covered by
`tests/test_workers.py`, `tests/test_scheduler.py`, and `tests/test_brain_kernel_workers.py`.
The adapter never migrates a legacy database in place. `--compatibility-mode legacy` is the
operational rollback path and preserves the existing job through scheduler idempotency.

## Disposition

`adapt — local implementation pending the required full gate and procedural Curator
reproduction`. The route may not be generalized to legacy execution, external delivery, or
release claims without separate parity and authority evidence.
