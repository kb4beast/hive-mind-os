# Blocker recovery protocol

Every failed attempt is an operating-system learning event.  The controller
must preserve an actionable blocker packet containing:

- the exact cause and category;
- the concrete fix required;
- the safe condition that permits retry;
- the attempted command and evidence references;
- a content-addressed blocker ID and timestamp.

Workers must report the packet to the operator and stop when the fix requires
credentials, protected-branch authority, legal consent, spending, production
access, or another authority outside the lease.  They may retry automatically
only after the packet's retry condition is verifiably true.  A security
control may not be disabled merely to make the retry pass.

Owner permission changes who may authorize an action; it does not change the
security meaning of that action. Disabling TLS verification, certificate
revocation, provenance checks, protected-branch rules, or evidence validation
is an unsafe remediation and remains ineligible for automatic retry. The
controller may pursue safe alternatives, but must stop and report the exact
repair when no safe alternative is available.

Known orchestration blockers are actionable: a missing or stale dispatcher
release produces a `SPAWN_SUBTASK` recovery action for an orchestrator child
task. That child refreshes the current singleton snapshot, reconciles the
target, emits a new explicit release, and retries the blocked claim. It must
stop again if the target changes or if the only workaround weakens a security
or provenance control.

Every child task follows this exact order:

1. fetch the current singleton release;
2. install the current GitHub snapshot;
3. reconcile the target;
4. run doctor and status;
5. dispatch an explicit `START NOW` release;
6. claim the remote node branch.

A child must never attempt step 6 before step 5 has produced a valid release.

Runtime packets are append-only under `.autopilot/state/blockers/`.  The
protocol, tests, and failed-attempt evidence are repository artifacts, so a
fresh session learns the recovery rule rather than repeating an opaque failure.

## Human-question learning rule

If a human question is unavoidable, record it under
`.autopilot/state/questions/<node>.jsonl` with `record_human_question`. When the
human and system establish the result, immediately call
`resolve_human_question`. That appends the fix and an explicit `RETRY_NOW`
action, allowing the controller to resume the failed operation in the same
turn. The answer is stored only as a digest; credentials, proxy secrets, and
other sensitive values must never be copied into repository files or evidence.
An unresolved question remains a blocker, not a reason to repeat the same
question on the next run.
