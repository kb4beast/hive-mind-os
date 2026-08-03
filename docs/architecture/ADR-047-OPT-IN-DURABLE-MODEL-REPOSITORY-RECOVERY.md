# ADR-047: Opt-in Durable Model-backed Repository Mission Recovery

- **Status:** Adapted — bounded injected lane after independent Curator and Judge review
- **Date:** 2026-08-03
- **Prior decisions:** ADR-040, ADR-041, ADR-044, ADR-046
- **Scope:** an additive, Python-injected `durable-model-repository-v1` lane. It does
  not enable CLI, worker, generic `ModelBackend`, delivery, source custody, or
  hostile-code/credential-isolation recovery.

## Context

ADR-046 makes one model role recoverable but deliberately stops before repository
capability effects. The existing repository mission rebuilt random work IDs and empty
prior context on restart, while `ModelRoleResult.to_agent_result()` creates new evidence
timestamps. Connecting the paths without a role journal could change a request, repeat
a provider call, or treat a model response as a successful repository role before its
capability receipts exist.

No provider idempotency key, provider outcome lookup, provider-signed result, external
lease/budget, external retention, credential isolation, or hostile-code containment is
available in this worktree. Local SQLite and SHA-256 bindings are integrity evidence,
not authentication of a provider, host, result, source, policy, authority, or receipt.

## Court record

- **Advocate:** deterministic role plans, an explicit sealed profile, one-shot model
  turns, admission witnessing, P06 receipt adoption, and an immutable final context
  projection permit a narrow resumable repository mission without invoking the legacy
  retry path.
- **Cross-examiner:** reject a design that regenerates work IDs, rereads a prompt
  champion, reconstructs timestamps, omits a material redaction policy, expands policy
  authority on resume, dispatches before both stores witness admission, fails to bind
  raw effect receipts into the final result, retries a dispatch-started turn, or silently
  falls back to a CLI, worker, default model backend, delivery, or generic execution.
- **Independent Architect/Cross-Examiner:** provisional `adapt` only for the described
  injected lane, subject to crash/tamper/rehydration evidence and independent Curator
  and Judge dispositions.
- **Independent Curator:** `adapt` after reproducing the 15-test durable suite, the
  25-test executor/state suite, forged-witness rejection before provider access, a
  redaction scan over eight provider calls, replacement-store blocking, ambiguity,
  missing resolver/redaction, and additive migration checks. Its dissent remains that
  local stores, hashes, and redaction commitments are not external authentication.
- **Independent Judge:** `adapt` after reproducing 26 focused repository-model/executor
  tests, static/type/compile/diff checks, and inspecting the exact built-in policy,
  concrete mission-store witness, model-turn revalidation, and receipt bindings. Its
  dissent remains that this seals the wrapper API only; privileged in-process code is not
  hostile-code or credential isolation.
- **Dissent / blocking evidence:** the adapter cannot know whether a timed-out provider
  call executed. Availability is intentionally sacrificed by blocking that turn rather
  than retrying it. The redaction commitment detects local runtime drift only; it is not
  an external authentication or key-custody mechanism.

## Decision

1. `DurableRepositoryModelProfile` seals exactly one typed acceptance specification, a
   `ModelTurnBudget`, every lifecycle prompt digest, provider identity, provider
   configuration and selection digests, policy-decision reference, exact
   `PolicyEngine` autonomy level, lease reference, and a `RedactionPolicy` identifier,
   digest, and local material commitment. The profile excludes endpoints, API values,
   environment-variable names, prompts, requests, responses, and raw redaction values.
   A wrapper rejects raw redaction material in the profile. A resolver must supply the
   same complete runtime `RedactionPolicy`; omitting its material fails closed before a
   provider call. The local commitment is expressly not authentication.
2. `DurableRepositoryModelBackend` is the only non-scripted backend admitted to a
   mission store. Its `ModelTurnStore` must be the path below that mission root. It
   rederives and verifies the injected backend and runtime redaction policy against the
   sealed profile before a provider call. Its regular `execute` and convenience
   `execute_prepared` entry points refuse direct use; it is bound to the concrete
   `MissionStore` that owns its turn-store path, and `execute_admitted` re-queries that
   store's canonical witness and model-store admission immediately before dispatch.
   It never accepts a caller-supplied witness mapping. Within the sealed wrapper API,
   only the repository role journal can dispatch it; privileged in-process code can still
   reach underlying objects and is addressed only by the separate hostile-code/credential
   isolation tranche. The mission also
   requires the exact sealed built-in `PolicyEngine`; resumption with a different or
   custom policy fails closed rather than silently expanding authority.
3. Mission-store schema v5 additively adds insert-only
   `mission_role_work_plans`, `mission_role_inputs`, `mission_role_admissions`,
   `mission_role_effects`, and `mission_role_completions`. Work plans carry deterministic
   `WORK-<digest>` IDs. Inputs bind prior completion digests, the exact model-context
   projection digest, prompt-relevant execution-objective digest, model-turn ID, and
   model-turn plan digest. An admission record is written only after the model-turn
   store has durably admitted the matching plan and reservation, and before provider
   dispatch.
4. The required ordering is:

   `work plan -> role input -> model-turn admission/reservation -> mission-store
   admission witness -> dispatch_started -> one provider call -> sanitized model result
   -> P06 effect checkpoints/receipts -> immutable final AgentResult projection + role
   succeeded`.

   On an existing admission witness, the model-turn store must already contain the exact
   admitted plan and reservation. A missing or replacement store therefore blocks before
   dispatch rather than recreating or replaying the turn.
5. Final completion is closed-deserialized before acceptance. It preserves original
   evidence timestamps and requires the exact, ordered raw receipt digests for every
   adopted model-role capability effect in receipt-bearing evidence, in addition to the
   synthetic P06 capability references. Reopening a completed role revalidates the
   model-turn record, plan/result bindings, outcome, and receipt bindings before exact
   rehydration. Later model roles consume that exact projection; they do not reconstruct
   it from a model-turn artifact.
6. A completed model turn without role completion can resume only pending capability
   effects. A `dispatch_started`, uncertain, quarantined, missing, or otherwise ambiguous
   model turn becomes mission `blocked`, never retried. Any plan, profile, policy,
   redaction, input, admission, completion, receipt, workspace, or model-store mismatch
   fails closed.
7. `resume_mission` requires an explicit in-process `ModelBackendResolver` for this
   backend. The resolver must return the matching sealed wrapper before network access.
   Generic CLI and workers pass no resolver and therefore remain fail-closed. External
   delivery is explicitly refused for this lane.

## Migration and rollback

Schema v5 is additive with no backfill. Version-1 through version-4 stores migrate by
creating the new append-only tables; an existing non-model version-3 mission record is
preserved unchanged. Existing or legacy model missions are never reinterpreted as this
lane. Rollback disables new durable-model repository starts and blocks active
model-profile missions while retaining both append-only journals and their evidence; it
must never route a sealed model turn through `ModelBackend.execute`.

## Threat model and non-claims

| Threat | Control | Residual / non-claim |
|---|---|---|
| Restart changes work, prompt, provider, policy, redaction material, result context, or receipts | Deterministic plans, sealed profile/input/admission/completion digests, exact policy/redaction checks, append-only journals | A local host can deny service or rewrite all local state; hashes and commitments are not authentication |
| Crash after model-store admission but before dispatch | Mission-store admission witness and cross-store validation | A crash in the gap sacrifices availability; provider is not called without a witness |
| Crash after provider dispatch | Durable one-call reservation and ambiguity quarantine | No provider outcome lookup/idempotency; intentional permanent availability loss |
| Later role sees regenerated timestamps or receipt semantics | Persist exact closed `AgentResult` and raw ordered receipt-digest binding | Model output and local receipts still lack external authenticity |
| Resolver substitutes configuration, redaction policy, or authority | Profile/policy/redaction verification before dispatch | Resolver authority and credentials remain process-local |
| Generic resume widens authority | Resolver required only by Python API; CLI/worker have none | A future authorized runtime resolver needs a separate ADR |
| Privileged in-process code bypasses the sealed wrapper | Wrapper API requires the concrete admission journal and rejects direct dispatch | Underlying objects are not hostile-code isolation; separate isolation is required |
| Model actions affect repository state | Existing P06 checkpoint/receipt adoption | No source custody or hostile-code/credential isolation; separate admission boundaries remain required |

## Acceptance evidence reproduced for adaptation

- An eight-role fixture completes through the injected lane with deterministic work plans,
  durable admission/completion records, and exact final role projections.
- Interruption after a model completion rehydrates it, adopts remaining effects, and makes
  no second provider call for that role.
- Missing resolver, changed resolver profile, changed policy, omitted redaction material,
  and replacement model-turn store after admission reject or block before provider access.
- Ambiguous provider outcome blocks the mission with no retry.
- Profile/input/admission/completion/effect/receipt/model-turn/workspace tampering,
  multi-spec profiles, mutable prompt substitution, direct legacy or wrapper dispatch,
  and generic CLI/worker model resumption fail closed.
- Version-3 schema migration is additive and preserves a non-model mission record.
- Independent Curator and Judge reproduced targeted hostile tests and separately issued
  `adapt`; their dissent and the non-claims above remain part of this decision.
