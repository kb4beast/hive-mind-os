# Whole-OS configured composition host

`hive_mind_os.whole_os_composition.WholeOSCompositionHost` is the configured
N28 host for `WholeOSService`. It removes the prior all-in-one package callback
gap without moving credentials or privileged executors into the product kernel.

For each dependency-ready package, the host now applies these typed boundaries
in order:

1. Match the sealed composition manifest and host-issued repository profile to
   the queue tenant, repository, and configuration. Require the scoped local
   build grant.
2. Select one evidence-backed discovery candidate through
   `DiscoveryBacklog` and retain its evidence and court receipt.
3. Run the injected builder through `BuilderSession`, including its operation,
   repair, time, and path bounds. The builder must return exact commit and tree
   identities and confirm that the delivered app has no Hive runtime import.
4. Run `CandidateQualifier` with the package acceptance manifest and an
   independently identified evaluator. Anything short of `PASSED` blocks the
   candidate.
5. Persist an idempotent `DeliveryRequest` intent before invoking
   `DeliveryBroker`. A retained intent without a result stops at
   `RECONCILIATION_REQUIRED`; it never blindly repeats the remote action.
6. Bind PR feedback to the published PR and current head through
   `FeedbackObserver`. Misrouted callbacks, stale heads, authority changes, and
   actionable failures stop at their typed boundary.
7. Record only a digest-based `LearningRoute`. Target-app routes cannot cross
   subjects, and an export-draft route additionally requires the profile's
   learning-export grant and admitted destination. This recorder does not
   activate a challenger.
8. Ask the separately identified terminal Curator for the existing
   candidate-bound terminal assessment after package convergence.

Package composition results are content-addressed and replayed from the host
state directory before any adapter is called again. Target source and target
runtime remain independent of Hive's scheduler and state paths.

The composition manifest continues to declare the full self-Python, external
Python, Node/TypeScript, Go, Rust compile-only, and Roblox matrix. Missing
Roblox Studio/device evidence and missing pinned tournament recipes are exposed
by `readiness()`. They do not block unrelated generic service work. A policy
that explicitly requires Roblox runtime evidence fails closed until a qualified
N27 receipt is injected. Tournament adapters remain pinned N30 inputs; merely
installing a tool does not admit or run a benchmark.

The deterministic protocol test uses an owned external fixture, fake forge,
and injected evaluator. It proves composition, tenant/head binding, scoped
learning, and replay behavior; it does not claim a live PR, hostile-code
sandbox, Roblox runtime, or measured tournament:

```text
PYTHONPATH=src python -m unittest tests.test_whole_os_composition -v
```
