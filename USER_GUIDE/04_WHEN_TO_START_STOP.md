# When to Start and Stop

## Start a node only when

- its dependencies have validated receipts integrated into the singleton release branch;
- the singleton release branch equals the reconciled target;
- the dispatcher has installed a current GitHub-state snapshot;
- no active file or semantic lock conflicts;
- the latest current dispatcher release gives this exact node `START NOW`;
- if it is part of a parallel wave, that same release says `START TOGETHER NOW` and names the wave;
- its remote claim succeeds;
- its model route is available; and
- its acceptance and effective write scope are still valid against current code.

A node shown in a static DAG level, or even deterministically classified as dependency-eligible, is still `WAIT` until explicitly released. The `ready` command reports only currently released `START NOW` nodes; `status` separately exposes static eligibility.

Every dispatcher candidate receives exactly one verdict:

- `START NOW` — current explicit execution authority exists for that node;
- `WAIT` — do not open/claim/implement yet; or
- `STOP` — the candidate is already active/complete, failed/repair-bound, or otherwise not a start candidate.

For a released multi-node wave, open the sessions together only when the dispatcher says `START TOGETHER NOW`. Dispatcher output must also say plainly how many worker sessions to open, or `Do not open any worker sessions yet`.

## Release invalidation

Never reuse an old START instruction after any of these events:

- the singleton release target advances, including a merge;
- a new conflicting claim appears;
- the live GitHub snapshot changes; or
- a new reconciliation event is recorded.

Those events make the prior release stale. Run the dispatcher again and wait for a new explicit verdict.

## Stop a worker when

- the node’s stopping condition is met and a draft PR plus receipt exist;
- current code contradicts a sealed assumption;
- write scope must broaden without an authorized reconciliation/replan amendment;
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
