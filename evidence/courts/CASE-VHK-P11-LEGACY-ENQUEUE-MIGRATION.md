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

### Builder full-gate receipt

The exact implementation candidate `54020b72d2fff602b355c99924b01b5cfb5d8ec5` passed
`python -m unittest discover -s tests -v`: 530 passed, 5 expected skips, 1066.055 seconds.
The retained stdout/stderr transcript SHA-256 is
`e95e2b7c4c78cd08842025f56297adc04dc251bab62dbaafdd54b5451f2e2cb4`. This is local
Builder evidence; the planned procedural Curator reproduction remains distinct.

### Procedural Curator reproduction

A separately prompted procedural Curator inspected commit
`54020b72d2fff602b355c99924b01b5cfb5d8ec5` and its tree
`a54dcc7b58055be8850f4461191746fc94bd453d`. It reran
`python -m unittest tests.test_cli_enqueue tests.test_brain_kernel_local_assurance -v`:
6 passed in 1.512 seconds, exit 0. This is a distinct local procedural check, not an
externally authenticated identity or independent-human promotion claim.
