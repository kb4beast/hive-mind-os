# Validation-target composition v1

This is the FPCR Judge-authorized, evidence-only follow-on court.  It answers
one narrow question: how the corrected-source validation target is composed,
and whether fixture API and `GitCommitObservation` contract API are distinct
candidate components.  It grants no implementation authority.

All observations bind exclusively to commit
`b789b68e7d6a741e0b85a3ac33cbce846e1e32c9` and its real tree
`b909b7b7e374bff22912059387ef0fe639498af6`.  The historical FPC tuples
`20e26e3c53d41ec4093b23f0957766cd0cbdab70/f454db6d64120c946ae6700bcf4b4b6ea1bef26c`
and `20e26e3c53d41ec4093b23f0957766cd0cbdab70/4f20bd2` are invalid and
explicitly rejected, never repaired or normalized.

`VTC-DISCOVERY-010` reconciles the claimed discovery inventory of 1,059 IDs
with the sole historical execution's 1,050 executed tests, including
collection, execution, skip, and inventory deltas.  It must not treat either
number as inherited truth, rerun CI, or test any candidate.  `VTC-CROSS-020`
is independently runnable after the seal and preserves counterclaims.  A
distinct later Judge must find zero unresolved material findings before a
separate implementation proposal can be opened.

The DAG retains, but does not reuse, the FPP/FPC/FPCR adverse evidence, the
rejected immutable fixture candidate `41950b74bdec2b6e1c48ee7f5ef3ce947d0c8378`,
and the non-promoted GCO candidate `d02c2d2`.  No node changes source, tests,
fixtures, controller, durable controller, `.autopilot/plan.json`, existing
DAGs, `main`, or any remote.
