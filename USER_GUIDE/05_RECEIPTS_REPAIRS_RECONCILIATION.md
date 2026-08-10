# Receipts, Repairs, and Reconciliation

A completion receipt must bind the plan fingerprint, node contract, exact base/final commit and
tree, branch/PR, changed paths, passing tests, evidence, model route, role identities, authority,
consultations, acceptance decision, timestamp, and rollback.

A merged PR without a valid receipt is `WAITING_FOR_RECEIPT`, not complete. A closed unmerged PR is
`REPAIR_REQUIRED`. Failed CI is `CI_FAILED`. A stale lease is reaped; a stale branch is repaired or
superseded. Three repeated semantic failures quarantine the node.

When `main` advances:

```bash
python .autopilot/bin/autopilot.py --repo-root . status
python .autopilot/bin/autopilot.py --repo-root . reconcile \
  --target-sha <EXACT_CURRENT_MAIN_SHA> \
  --actor dispatcher:<session> \
  --reason "Reconcile newly merged or unplanned target work" \
  --changed-path <PATH>
```

Reconciliation must map absorbed work, conflicts, changed acceptance, and new risks. It may update
the graph through append-only records; it may not rewrite old receipts.
