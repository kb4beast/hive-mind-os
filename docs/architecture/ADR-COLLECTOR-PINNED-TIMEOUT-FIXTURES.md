# Pin collector timeout fixtures independently of the outer Git topology

Status: proposed bounded repair; independent disposition and qualification are
recorded separately for the reviewed candidate.

## Problem and evidence

Post-merge Constitutional CI run `34785092456` tested main commit
`0d161d869a9a717b891872fc9b8203ae07eae51f`, tree
`81d638986bf3553bdf2ebd45d224bd40a526fbc4`. Both Windows Python 3.12 and
3.14 failed exactly the two collector timeout tests. They invoked the collector
against ambient `HEAD`. The collector correctly rejected that merge commit
because its V4 candidate contract requires exactly one parent. Validation never
reached either timeout. A local run of the original two tests reproduced both
failures. This explains a difference between linear PR heads and merged main;
it is not evidence that the timeout enforcement itself failed.

## Architecture and acceptance

Materialize the already pinned V4 candidate
`1038b5a7d2eb49904c59957ad3e989af8bb2fcc5` in a temporary detached worktree for
each timeout test. Overlay the current collector and process runner scripts,
as the existing successful collector integration test already does. Pass that
root explicitly to the invocation helper. Remove only that temporary worktree
on context exit, including exceptional exits. The invoking checkout and its
branch are never switched.

The regression synthesizes a two-parent outer commit even when CI tests a
linear PR branch. Direct collection must reject that merge without producing
an evidence receipt. A nested pinned candidate created from the same outer
checkout must instead reach the one-millisecond module timeout and retain its
actual candidate commit, parent, sole-parent verification, failure code and
disabled qualification/activation flags. The outer commit must remain intact.
Replacing the pinned fixture revision with ambient `HEAD` makes this regression
fail at topology validation rather than silently relying on a linear checkout.

The original overall timeout and module timeout assertions remain unchanged.
The actual collector and process-runner scripts are byte-identical to main;
the 900-second overall and 300-second module production limits, historical
source inventory, expected validation counts, topology and authority gates
are unchanged.

## Threats and limitations

Using an arbitrary single-parent commit could pass the initial topology check
while testing the wrong historical source or manifest. The fixture therefore
uses the immutable V4 candidate, not a newly minted child of current main.
The synthetic merge is test input, not a release candidate or authority receipt.
Overlaid scripts deliberately make a non-qualifying test fixture; no successful
activation or independent custody claim follows from these tests.

The fixture requires the historical candidate object, like the existing full
collector integration test. Missing history remains an explicit test failure;
there is no shallow-history skip or replacement source. Worktree operations
use unique temporary paths and explicit revisions; no global worktree pruning
or repository checkout mutation is introduced. Tests cover the supported
Windows interpreters; Linux skips Windows PowerShell tests by existing policy.

## Compatibility, migration and rollback

Only test fixtures change. No public CLI contract, receipt format, source bundle,
dependency, production code or persisted state changes; no migration is needed.
Historical receipts and failed attempts retain their meaning. Revert this
bounded test change for rollback, retaining all failure and review evidence;
the known post-merge false failures would return and cannot be called passing.

The bounded alternatives are to pin the valid historical subject (proposed),
relax the production topology burden (rejected by the required invariant), or
skip tests on merge commits (rejected because it would remove timeout coverage).
These are builder recommendations, not a fabricated independent court verdict.
No superiority, full node completion, promotion or deployment claim is made.
