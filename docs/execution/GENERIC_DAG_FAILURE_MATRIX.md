# Generic DAG failure qualification

The focused matrix injects concurrency, target snapshot drift, an undeclared
dependency, host loss after sibling dispatch, candidate mutation, integration
target conflict, restart, and duplicate-effect replay. All subjects and hosts are
disposable local fixtures.

Expected outcomes are fail-closed: drift and substitution stop before a node
effect; a lost host becomes `RECONCILIATION_REQUIRED`; completed siblings retain
their checkpoint; an integration conflict performs no compare-and-swap; and a
completed run returns its durable receipt without invoking the host again.

The matrix does not simulate physical host custody, external signatures, atomic
storage failure across machines, protected-branch merge, deployment, or
production. Those remain separate evidence obligations and authority gates.
