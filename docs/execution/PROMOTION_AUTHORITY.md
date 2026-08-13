# Promotion authority — court-gated atomic champion promotion and rollback

Module: `src/hive_mind_os/brain_kernel/promotion.py`
Tests: `tests/test_hive_cortex_promotion.py`
Node: PROMOTE-530. Semantic locks: `promotion-authority`, `champion-pointer`.

`PromptRegistry` already refuses unauthenticated or self-issued promotions.
This module is the one legitimate kernel authority that can satisfy those
refusals, and it can only do so by consuming an **independent, already
validated court record**. Nothing here schedules model work, and nothing here
invents a registry API: the only pointer mutations are `PromptRegistry.promote`
and `PromptRegistry.rollback_champion`.

Import it by full path. There is deliberately no package re-export:

```python
from hive_mind_os.brain_kernel.promotion import PromotionAuthority
```

## 1. Authority model

Four identities, four separate powers. No identity may hold two of them for the
same candidate.

| Identity | Power | Where it is enforced |
|---|---|---|
| proposer | registers the candidate artifact (`PromptRegistry.register(created_by=...)`) | `PromotionCandidate.__post_init__` requires `proposer_id != builder_id`; `PromptRegistry._validate_decision_event` requires `registration_author == proposer_id` |
| builder | produced the change under test | `PromotionCandidate.__post_init__` |
| evaluator | measured the candidate | `PromotionDecision.__post_init__` |
| judge | issues the verdict and is the only actor that touches the pointer | `PromotionDecision.__post_init__`; `court_runtime._validate_panel`; `PromptRegistry._validate_decision_event` |

`PromotionDecision.__post_init__` requires that
`{candidate.proposer_id, candidate.builder_id, evaluator_id, judge_id}` contains
exactly four distinct, non-blank values. That is the same rule
`PromptRegistry._validate_decision_event` enforces on the ledger payload, so a
decision that would be refused by the registry cannot even be constructed.

Separation is enforced twice, independently:

1. **In the court.** `court_runtime._validate_panel` refuses to seat a judge
   whose identity appears in `CourtCase.source_identities` (the affected
   identities plus every role-result executor). A self-judged court record
   therefore cannot exist.
2. **In this module.** `PromotionDecisionLog.append` requires that
   `{proposer_id, builder_id, evaluator_id}` is a subset of
   `record.case.affected_identities`, so the panel check above has provably
   already been applied to all three of them, and requires
   `record.verdict.decided_by == decision.judge_id` so a bystander cannot borrow
   someone else's verdict.

## 2. Append-only decision log

`PromotionDecisionLog` is a frozen dataclass; `append` returns a **new** log and
never mutates the old one, exactly like `CourtHistory.append`. It raises
`PromotionAuthorityError` unless all seven hold:

1. `decision_id` is unused, and `court_case_id` has not already been consumed —
   one decision per court case, ids are never replaced.
2. A `CourtRecord` with `case.case_id == decision.court_case_id` exists in the
   supplied `CourtHistory`.
3. Candidate binding: `record.case.subject == candidate.artifact_digest`.
4. Identity binding (section 1).
5. The verdict and the court disposition agree (table in section 3).
6. A `KEEP` verdict requires `CourtClaimKind.SUPERIORITY` — beating the live
   champion carries the superiority burden of proof.
7. No prior decision for the same `candidate_id` carries a terminal verdict.
   `RETEST` may be followed; `KEEP`, `DISCARD`, `QUARANTINE`, and `STOP` close
   the candidate.

## 3. Verdict → court disposition compatibility

The five-verdict vocabulary is owned by
`hive_mind_os.recursive_improvement.ExperimentVerdict` and is reused verbatim;
this module defines no new enum.

| `ExperimentVerdict` | Compatible `CourtDisposition` | Pointer effect | Terminal |
|---|---|---|---|
| `KEEP` | `ADOPT`, `ADAPT` | promote (the only pointer move) | yes |
| `RETEST` | `DEFER` | none — champion retained | no |
| `DISCARD` | `REJECT` | none on `apply`; may authorize `rollback` | yes |
| `QUARANTINE` | `QUARANTINE` | none on `apply` (candidate quarantined); may authorize `rollback` | yes |
| `STOP` | `DEFER`, `REJECT` | none — champion retained | yes |

## 4. Surface

```python
class PromotionAuthority:
    def __init__(self, registry: PromptRegistry) -> None: ...
    @property
    def log(self) -> PromotionDecisionLog: ...
    @property
    def receipts(self) -> tuple[dict[str, Any], ...]: ...
    def submit(self, decision: PromotionDecision, *, court_history: CourtHistory) -> PromotionDecision: ...
    def apply(self, decision_id: str) -> dict[str, Any]: ...
    def rollback(self, decision_id: str) -> dict[str, Any]: ...
```

`submit` only appends to the log. It never moves a pointer, ever.

`apply` and `rollback` both require a **logged, unapplied** decision; an unknown
or already-applied `decision_id` raises `PromotionAuthorityError`. A decision
whose candidate is already the active champion cannot be `apply`-ed at all — it
must go through `rollback`.

## 5. The exact `experiment.decision` payload

`PromptRegistry._validate_decision_event` checks every key below verbatim. This
is the payload `apply` appends to `PromptRegistry.ledger` (run id =
`candidate.experiment_id`, event type `experiment.decision`, actor =
`decision.judge_id`) immediately before calling `promote`. The returned event
sequence becomes `decision_event_sequence`.

```python
{
    "verdict": "keep",
    "role": candidate.role,
    "candidate_digest": candidate.artifact_digest,
    "current_digest": candidate.parent_champion_digest,
    "registration_experiment_id": candidate.experiment_id,
    "registration_role": candidate.role,
    "registration_author": candidate.proposer_id,
    "registration_parent_digest": candidate.parent_champion_digest,
    "proposer_id": candidate.proposer_id,
    "builder_id": candidate.builder_id,
    "evaluator_id": decision.evaluator_id,
    "judge_id": decision.judge_id,
    "retained_artifact_refs": list(candidate.evidence_refs),
    "contract_fingerprint": decision.contract_fingerprint,
    "decision_id": decision.decision_id,
    "court_case_id": decision.court_case_id,
    "decision_binding_digest": decision.binding_digest,
}
```

`decision_binding_digest` is `canonical_digest(decision.candidate)` — the
decision can never be re-pointed at a different candidate after the fact.

If `promote` raises `RuntimeError` (stale `expected_current`, quarantined
artifact, missing registration, malformed decision event), `apply` records a
`status="failed"` receipt carrying the refusal text and the observed
`pointer_after`, then raises
`PromotionAuthorityError("atomic promotion was refused: ...")`. The pointer is
untouched, because `promote` validates everything before its `_atomic_json`
write.

## 6. Receipt shape

Every outcome — including the ones that move nothing — produces a receipt. It is
appended to the evidence ledger as event type `promotion.receipt` (run id =
`candidate.experiment_id`, actor = `decision.judge_id`) and retained in
`PromotionAuthority.receipts`.

```python
{
    "schema_version": 1,
    "kind": "promotion.receipt",
    "decision_id": ..., "court_case_id": ...,
    "verdict": decision.verdict.value,
    "role": candidate.role,
    "candidate_digest": candidate.artifact_digest,
    "binding_digest": decision.binding_digest,
    "action": "promote" | "retain-champion" | "quarantine-candidate" | "rollback",
    "status": "applied" | "failed",
    "prior_digest": ..., "restored_digest": ..., "pointer_after": ...,
    "reasons": [...],
    "recorded_at": utc_now(),
    "receipt_digest": canonical_digest(<the dict above, before this key>),
}
```

## 7. Invariants

- **Only `KEEP` moves the pointer.** `apply` performs no pointer call for
  `RETEST`, `DISCARD`, `QUARANTINE`, or `STOP`. `QUARANTINE` records a registry
  quarantine for the candidate; the other three call the registry not at all and
  emit a `retain-champion` receipt.
- **Rollback restores the retained prior champion.** `rollback` requires an
  adverse verdict (`DISCARD` or `QUARANTINE`), a non-`None`
  `candidate.parent_champion_digest`, and that
  `registry.champion_digest(role) == candidate.artifact_digest`. It restores the
  parent digest through `PromptRegistry.rollback_champion` and records a
  `rollback` receipt with `restored_digest`.
- **Quarantine never precedes restoration.** In the `QUARANTINE` rollback path
  the demoted digest is quarantined strictly *after* the pointer is restored, so
  a champion is never simultaneously active and quarantined.
- **Decisions are append-only and candidate-bound.** See section 2.
- **A failed promotion leaves the pointer where it was**, and the failure itself
  is retained as a receipt rather than being swallowed.

## 8. Escalation rule — no bypass

No caller may reach `PromptRegistry.promote` or
`PromptRegistry.rollback_champion` directly. Champion pointer motion goes
through `PromotionAuthority` and therefore through an independent court record.

If a registry check appears to block a legitimate flow, **the flow is wrong**.
Do not weaken the gate, do not add a registry API, do not hand-roll an
`experiment.decision` event outside this module. Escalate instead: no component
may expand its own authority or weaken an acceptance criterion in order to pass.

## 9. Running the tests

```bash
PYTHONPATH=src python -m unittest tests.test_hive_cortex_promotion -v
```

`PYTHONPATH=src` is mandatory. This is a src-layout package and a stale editable
install elsewhere on the machine will otherwise shadow the working tree.
