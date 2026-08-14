# Validation provenance remand v1

This is a bounded, evidence-only remand from the VTC defer judgment.  It may
reduce one narrow uncertainty: whether the retained corrected-source discovery
inventory can be deterministically bound, exactly once per ID, to terminal
outcomes in the sole retained FPCR transcript.  It is not an implementation,
candidate, promotion, performance, or baseline-retry court.

Every observation binds only to commit
`b789b68e7d6a741e0b85a3ac33cbce846e1e32c9` and its real tree
`b909b7b7e374bff22912059387ef0fe639498af6`.  The historic FPC tuples remain
rejected.  The rejected fixture candidate `41950b74bdec2b6e1c48ee7f5ef3ce947d0c8378`
and non-promoted GCO candidate `d02c2d2` remain ineligible for reuse,
relabeling, qualification, or composition.

The remand has five nodes: a Clerk seal; parallel Explorer ledger construction
and Cross-Examiner review; integration; and a distinct Judge.  A successful
ledger only narrows provenance uncertainty.  It cannot by itself authorize
source or test changes, candidate execution, CI, promotion, a performance
claim, or `BASELINE-000` retry.

The ledger parser is deliberately fail-closed.  It accepts terminal test lines
only through its specified state machine, tolerates warnings between a header
and terminal label, accepts explicit custom terminal labels only when they are
declared, and rejects any duplicate, unknown, missing, malformed, or unbound
discovery ID.
