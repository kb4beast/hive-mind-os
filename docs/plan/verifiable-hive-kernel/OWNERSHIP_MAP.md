# Verifiable Hive Kernel: Ownership Map

This is a Phase 0 routing map, not a claim that any subsystem has been replaced.

| Kernel concern | Existing path | Phase 0 classification | Later direction |
| --- | --- | --- | --- |
| Mission aggregate and continuation | `mission.py`, `mission_loop.py`, `mission_store.py`, `autonomous_os.py` | merge-later | One additive kernel mission/event façade with compatibility adapters |
| Durable scheduling | `scheduler.py`, `workers.py` | reuse | Extend existing leases and workers; do not replace the queue |
| Policy and authority | `policy.py`, `roles.py`, `autonomy.py` | reuse | Wrap in narrowed authority envelopes and effect mediation |
| Evidence and receipts | `ledger.py`, `receipts.py`, `contracts.py` | reuse | Reference existing content-addressed evidence rather than copying it |
| Candidate verification | `curator.py`, `verify.py`, `git_adapter.py` | reuse | Bind sealed evaluation plans to exact candidate artifacts |
| PIT learning | `pit_oracle.py`, `repository_learning.py` | reuse | Preserve physical anti-cheat isolation |
| Prompt and experiment governance | `prompt_registry.py`, `recursive_improvement.py`, `experiment_runner.py`, `learning.py` | reuse | Route challengers through existing independent-promotion gates |
| Provider and host controls | `model_provider.py`, `model_backend.py`, `sandbox.py` | wrap | Keep adapters replaceable and expose only non-secret diagnostics in Phase 0 |
| Operational projection | `projection.py`, `cli.py` | wrap | Add `kernel doctor` without changing legacy commands |
| Repository-specific cortex | Not yet present as a package | missing | Introduce only after kernel contracts exist; kernel must not depend on it |

## Ownership rule

Existing subsystem owners remain authoritative for their current data and side effects.
The additive kernel owns only its own code and diagnostics until a later phase has an
approved migration, compatibility tests, and rollback evidence.
