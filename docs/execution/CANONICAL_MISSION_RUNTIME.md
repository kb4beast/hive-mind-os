# Canonical mission runtime

`MissionRuntime` is the one local, provider-free composition point for a full
eight-role kernel mission. It uses only the existing closed event vocabulary.

| Step | Event types | Reducer gate |
| --- | --- | --- |
| Charter | `mission.created`, `mission.transition` | mission begins `CREATED` then `PLANNING` |
| Plan | `work.created` | an immutable scheduled work graph |
| Obligations | `closeout.obligations.declared` | orchestrator declares all eight roles |
| Start | `mission.transition` | `PLANNING → READY → RUNNING` |
| Consultation | none (digest retained in role evidence) | two non-requesting roles resolve ambiguity first |
| Work | `work.transition`, `role.result` | `PROPOSED → READY → LEASED → RUNNING` |
| Seal | `evaluation.plan.sealed` | architect seals one pre-candidate plan while work runs |
| Verify | `work.transition`, `evaluation.result`, `evaluation.bundle.recorded` | curator records only the exact awaited candidate |
| Accept/integrate | `work.transition` | only a recorded passed digest permits acceptance and integration |
| Close | `mission.transition` | `RUNNING → VERIFYING → INTEGRATING → COMPLETED` |

The event schema is closed: the runner appends only the nine established kernel
types and never changes the reducer. Consultation precedes escalation;
`MissionEscalationRequired` is the only human hand-off and is raised only after
the role-first consultation result proves genuine authority is required.

Effects are authorized exclusively with an `AuthorityRegistry` capability token
and executed via `EffectGateway(store)`, which routes the builder write through
the durable outbox. Replay uses injected times, portable relative references,
and canonical digests; it rebuilds the projection and re-derives technical
closeout from the event spine and verification bundles.

The local suite never calls a provider, pushes, merges, or deploys; it creates
no event types and grants no authority. It also never self-approves. `RoleRuntime`
may later bind through the `RoleExecutor` protocol without changing this
lifecycle. Local assurance and court runtime remain separate evidence consumers.
