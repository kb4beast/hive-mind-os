# When to Start and Stop

## Start a node only when

- its dependencies have validated receipts integrated into current `main`;
- current `main` equals the reconciled target;
- no active file or semantic lock conflicts;
- its remote claim succeeds;
- its model route is available; and
- its acceptance and write scope are still valid against current code.

## Stop a worker when

- the node’s stopping condition is met and a draft PR plus receipt exist;
- current code contradicts a sealed assumption;
- write scope must broaden;
- the same actor would generate and independently approve its own result;
- suspected cheating is confirmed or unresolved;
- a true external authority is missing;
- a semantic conflict appears;
- the third semantic attempt fails;
- progress fingerprints repeat; or
- CI/verification requires a repair or remand.

Stopping safely means retaining evidence, releasing or allowing the claim lease to expire, and
recording `failure`, `escalation`, `repair`, `replan`, or `quarantine`. It never means silently
weakening acceptance.
