# Singleton release-branch execution policy

The active execution target is the singleton branch
`release/hive-mind-os-singleton-20260810-r2`. The controller reads this target from
`.autopilot/control-plane.json`.

All level work, tests, claims, receipts, reconciliations, and PRs bind to this branch.
`main` is never used as a node target and is reserved for final integration after the
full L0–L15 completion audit.

A branch advance, merge, new claim, or reconciliation event invalidates earlier release
instructions. The dispatcher must fetch the singleton branch and issue a fresh explicit
release before any worker starts.
