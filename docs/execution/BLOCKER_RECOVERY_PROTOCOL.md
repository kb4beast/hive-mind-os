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

Runtime packets are append-only under `.autopilot/state/blockers/`.  The
protocol, tests, and failed-attempt evidence are repository artifacts, so a
fresh session learns the recovery rule rather than repeating an opaque failure.
