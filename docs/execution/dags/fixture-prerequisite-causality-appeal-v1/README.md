# Fixture prerequisite causality appeal v1

This is an Appeals-Judge-authorized, no-code six-node court. It exists because
the predecessor causality receipt is incomplete: deterministic discovery found
1,059 tests (digest `sha256:8c6047bd0457cd3b880437c466695527e6a8bc342724bab008aac5cebf0d477c`),
while the prior predicate expected 1,050 tests.

The only execution authority is `FPC-EXECUTE-020`: one fresh source-installed,
hermetic root-CI invocation with a 2,700-second serialized limit and a durable
transcript. The runner cannot implement or retry. Every other node is evidence,
cross-examination, integration, or judgment.

No node may edit code, tests, `.autopilot/plan.json`, existing DAGs, predecessor
evidence, or `main`; contact remotes; make a performance claim; promote fixture
or GCO work; or retry knowledge `BASELINE-000`. A future implementation requires
a separate court and a separately sealed plan.
