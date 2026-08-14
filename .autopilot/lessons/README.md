# Lessons — what actually unblocks a stuck run

This directory is the control plane's durable memory, and unlike
`.autopilot/state/` (session-local, gitignored) it is **committed**. A lesson
learned on one machine survives a fresh checkout, reaches every other session,
and travels to any repository this control plane drives.

## Why it is keyed by mechanism, not by incident

Each record is keyed by `<verdict>|<proof kind>|<action>` — for example
`CLAIM_DEFUNCT|expired|reap`. That key deliberately contains **no node id,
branch name, or SHA**. What a lesson is *about* is the control plane's own
mechanism ("an expired claim ref protects nothing and blocks every re-claim"),
never one incident. Instance detail is kept inside the record as evidence, so a
human can audit why a lesson exists, but it is not part of the key.

That makes a lesson meaningful to anyone running this control plane, on any
repository — but note there is **no automatic cross-repository sync**. Lessons
travel the way the control plane itself does: by copying `.autopilot/`, or by
merging from a repository that has them. What the mechanism key buys is that a
lesson stays *true* when it arrives, instead of being about a node id that
doesn't exist there.

## The feedback loop this closes

Before this existed, the healer could attempt the same useless repair forever —
exactly the polling it was written to end.

The crucial part is **when** a repair is judged. Checking right after acting
proves nothing: a reap deletes the very branch it diagnosed, so the wedge is
always "gone" a second later. So every repair is recorded as an **attempt**, and
a **later pass** settles it by re-observing the node:

- the same mechanism is wedging that node again → the repair did not hold,
  `NO_EFFECT`;
- the node has moved on → `UNBLOCKED`.

A repair that has to be re-applied every round is the polling loop this control
plane exists to end, and this is what detects it.

A mechanism settled `NO_EFFECT` three times that has **never once** held is
`DISPROVEN` and **withdrawn**: the healer stops attempting it and reports the
recorded evidence, so a human sees a real finding rather than a loop.
Withdrawal is a cooldown, not a life sentence — after
`retry_disproven_after_minutes` (default 12h) one probation attempt is allowed,
so a mechanism broken by a since-fixed defect can earn its place back.

Confidence is derived, never asserted: `PROVEN` (≥2 held, none failed),
`DISPROVEN` (≥3 failed, none held), `PROVISIONAL`, or `UNTRIED`. Refusals — a
worker won the `--force-with-lease` race, or the controller re-proved liveness —
count toward neither, because they prove nothing about whether the repair holds.

## Format

One append-only JSONL file per mechanism, named after its key, holding two
kinds of record: an `ATTEMPT` (a repair was applied) and the `OUTCOME` that
later settles it (`settles` carries the attempt's `record_id`). Aggregation
happens at read time over settled outcomes only, de-duplicated by `record_id`,
so two sessions appending concurrently produce a union rather than a conflict —
`.gitattributes` sets `merge=union` here for the same reason, and pins LF so a
checkout under `core.autocrlf=true` cannot turn an append into a whole-file
rewrite.

Never hand-edit these files to change a verdict. A lesson is earned by recorded
outcomes, and rewriting one is the same act as fabricating a receipt.

Inspect the record with:

```bash
"${AUTOPILOT[@]}" lessons
```

Here `AUTOPILOT` is the exact namespace-aware command array defined in
`.autopilot/README.md`; do not rely on parser defaults.
