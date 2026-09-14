# Whole-OS recovery

| Observed state | Deterministic next action | Stop condition |
| --- | --- | --- |
| stale lease | discard the stale return and reclaim through `Scheduler` | a current lease completes or reaches its attempt cap |
| uncertain effect | inspect by operation ID before retry | authoritative receipt, authoritative absence, or typed unknown |
| provider failure | retain the attempt and apply the leased route policy | recovery, route escalation, or budget exhaustion |
| invalidated candidate | seal a successor candidate and invalidate dependent receipts | exact successor is independently qualified |
| blocked export | retain the draft obligation without publishing | authority/destination appears or the obligation is quarantined |
| unavailable runtime | record `BLOCKED_CAPABILITY`; continue unrelated profiles | an attested runtime appears |
| supervisor rollback | restore the prior immutable release pointer | prior version health is observed |
| missing host factory | register the exact independently admitted factory in the trusted launcher; do not load code from JSON | one descriptor-bound factory resolves or `BLOCKED_CAPABILITY` is retained |
| pending tournament intent | re-plan from the live admission and inspect the operation ID before execution | a genuine receipt is retained or the admission/lease becomes a typed blocker |
| active pilot attempt after restart | reload the active lease and reconcile its target receipt before completing or replacing it | the same attempt closes or its lease reaches a recorded terminal state |

State is reconstructed from the scheduler, descriptor, graph digest, qualification
ledger, and broker receipts. Chat history is not a recovery dependency.
