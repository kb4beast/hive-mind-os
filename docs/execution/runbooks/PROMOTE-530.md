# PROMOTE-530 — Court-gated atomic champion promotion and rollback

## 1. Contract summary

**Objective.** Authorize atomic champion promotion or rollback only through an
independent, append-only court decision. `PromptRegistry` (already merged)
deliberately blocks unauthenticated or self-issued promotions; this node adds
the one legitimate kernel authority that can satisfy those checks.

**Acceptance criteria (compressed).**
1. KEEP/RETEST/DISCARD/QUARANTINE/STOP decisions are append-only and candidate-bound.
2. Proposer, builder, evaluator, and judge separation is enforced.
3. Only KEEP can move an atomic pointer.
4. Rollback restores the retained prior champion and records a receipt.

**Scope.**

| Kind | Paths |
|---|---|
| write (exact, nothing else) | `src/hive_mind_os/brain_kernel/promotion.py`, `tests/test_hive_cortex_promotion.py`, `docs/execution/PROMOTION_AUTHORITY.md` |
| read (grounding) | `src/hive_mind_os/prompt_registry.py`, `src/hive_mind_os/recursive_improvement.py`, `src/hive_mind_os/courtroom.py`, plus kernel surfaces quoted in §2 |
| forbidden | `.github/CODEOWNERS`, `.github/governance/**`, `evidence/courts/**`, `docs/architecture/HARDENED_VISION_CONTRACT.md` |

Additionally forbidden for the worker (hard rules): any `__init__.py`,
`conftest.py`, `pyproject.toml`, `.autopilot/**`, any sibling node's files, and
any path not in the write list above. Import the new module by full path
`hive_mind_os.brain_kernel.promotion`; do NOT add package re-exports.

**Semantic locks:** `promotion-authority`, `champion-pointer`.
**Round:** R7, ALONE (`parallel_safe: false`) — no siblings this round.
**Branch:** `autopilot/promote-530`. Never touch the release branch; never
rebase/squash/amend the node branch; never run repo-wide test discovery (the
authenticated validation broker exclusively owns the repository-wide gate).

## 2. Existing-code map (verified signatures — do not invent others)

| Path | Symbol | Real signature | Role |
|---|---|---|---|
| `src/hive_mind_os/recursive_improvement.py` | `ExperimentVerdict` | `class ExperimentVerdict(StrEnum): KEEP="keep"; RETEST="retest"; DISCARD="discard"; QUARANTINE="quarantine"; STOP="stop"` | THE five-verdict vocabulary; reuse, do not redefine |
| `src/hive_mind_os/prompt_registry.py` | `PromptRegistry.__init__` | `(self, root: str | Path, *, ledger: EvidenceLedger | None = None)` | atomic champion pointer store |
| `src/hive_mind_os/prompt_registry.py` | `PromptRegistry.register` | `(self, role, content, *, parent_digest: str | None, created_by: str, experiment_id: str | None = None) -> str` | content-addressed candidate registration (proposer-authored) |
| `src/hive_mind_os/prompt_registry.py` | `PromptRegistry.promote` | `(self, role, digest, *, promoted_by: str, experiment_id: str, expected_current: str | None, decision_event_sequence: int | None = None) -> str | None` | atomic pointer move; validates the `experiment.decision` ledger event (see §3.4) and raises `RuntimeError` otherwise |
| `src/hive_mind_os/prompt_registry.py` | `PromptRegistry.rollback_champion` | `(self, role, to_digest: str, *, actor: str, reason: str) -> str` | restores a previously promoted champion; returns prior digest |
| `src/hive_mind_os/prompt_registry.py` | `PromptRegistry.quarantine` | `(self, role, digest, *, actor: str, experiment_id: str, reasons: tuple[str, ...]) -> None` | append-only quarantine record; reasons must be nonempty, unique, nonblank |
| `src/hive_mind_os/prompt_registry.py` | `PromptRegistry.champion_digest` | `(self, role) -> str | None` | reads the pointer (re-validates its promotion record) |
| `src/hive_mind_os/prompt_registry.py` | `PromptRegistry.is_quarantined` | `(self, digest: str) -> bool` | quarantine check |
| `src/hive_mind_os/prompt_registry.py` | `PromptRegistry.close` | `(self) -> None` | closes the owned ledger (call via `addCleanup` in tests) |
| `src/hive_mind_os/prompt_registry.py` | `prompt_digest` | `(content: str | bytes) -> str` | canonical `sha256:<64hex>` prompt identity |
| `src/hive_mind_os/ledger.py` | `EvidenceLedger.append_event` | `(self, run_id: str, event_type: str, actor: str, payload: dict[str, Any]) -> int` | returns the event **sequence** used as `decision_event_sequence` |
| `src/hive_mind_os/models.py` | `Role` | `class Role(str, Enum)` — values `orchestrator, explorer, architect, builder, curator, optimizer, steward, integrator` | role vocabulary |
| `src/hive_mind_os/models.py` | `utc_now` | `() -> str` | timestamp receipts |
| `src/hive_mind_os/brain_kernel/court_runtime.py` | `CourtCase` | `CourtCase(case_id, claim_kind, subject, affected_identities, role_results=(), consultations=())` | candidate-bound court case (`subject` carries the artifact digest) |
| `src/hive_mind_os/brain_kernel/court_runtime.py` | `CourtRecord` / `CourtHistory.append` | `CourtHistory.append(record: CourtRecord) -> CourtHistory`; `record_case(history, case, briefs, verdict, *, appeal_of=None) -> CourtHistory` | append-only court records; enforces seat/identity separation |
| `src/hive_mind_os/brain_kernel/court_runtime.py` | `CourtDisposition` | `ADOPT/ADAPT/DEFER/REJECT/QUARANTINE` | court outcome vocabulary mapped in §3.2 |
| `src/hive_mind_os/brain_kernel/court_runtime.py` | `CourtClaimKind` | `ORDINARY/CHEATING/SUPERIORITY` | KEEP requires a `SUPERIORITY` case |
| `src/hive_mind_os/brain_kernel/court_runtime.py` | `CourtProtocolError` | `class CourtProtocolError(ValueError)` | court-side failure type |
| `src/hive_mind_os/brain_kernel/canonical.py` | `canonical_digest` | `(value: Any) -> str` | binding/receipt digests |

Import style precedent: kernel modules import the parent package relatively
(`from ..models import Role`, see `role_runtime.py` lines 17–21) and siblings
via `from .court_runtime import ...`. Follow it.

## 3. Design — `src/hive_mind_os/brain_kernel/promotion.py`

One new module; no changes anywhere else. All classes are frozen slotted
dataclasses in the house style (validate in `__post_init__`, raise the module
error type).

### 3.1 Error type and helpers

```python
class PromotionAuthorityError(ValueError):
    """A promotion input would weaken authority separation or pointer safety."""

def _text(value: str, label: str) -> str            # nonempty str or raise
def _refs(values, label) -> tuple[str, ...]         # nonempty, unique, nonblank tuple
def _artifact_digest(value: str, label: str) -> str # exactly "sha256:" + 64 lowercase hex
```

### 3.2 Verdict vocabulary and court compatibility

Reuse `ExperimentVerdict` (import `from ..recursive_improvement import
ExperimentVerdict`). Module constants:

```python
_TERMINAL_VERDICTS = frozenset({KEEP, DISCARD, QUARANTINE, STOP})
_ROLLBACK_VERDICTS = frozenset({DISCARD, QUARANTINE})
_COMPATIBLE_DISPOSITIONS: Mapping[ExperimentVerdict, frozenset[CourtDisposition]] = {
    KEEP:       frozenset({ADOPT, ADAPT}),
    RETEST:     frozenset({DEFER}),
    DISCARD:    frozenset({REJECT}),
    QUARANTINE: frozenset({QUARANTINE}),
    STOP:       frozenset({DEFER, REJECT}),
}
```

### 3.3 Dataclasses

```python
@dataclass(frozen=True, slots=True)
class PromotionCandidate:
    candidate_id: str
    role: str                          # coerced via Role(self.role).value
    experiment_id: str
    artifact_digest: str               # _artifact_digest
    parent_champion_digest: str | None # _artifact_digest when not None
    proposer_id: str
    builder_id: str
    evidence_refs: tuple[str, ...]     # _refs -> becomes retained_artifact_refs
```
`__post_init__` also requires `artifact_digest != parent_champion_digest`
(mirrors `ExperimentCandidate`: "a challenger cannot mutate the live champion
in place") and `proposer_id != builder_id`.

```python
@dataclass(frozen=True, slots=True)
class PromotionDecision:
    decision_id: str
    court_case_id: str
    candidate: PromotionCandidate
    verdict: ExperimentVerdict         # coerced via ExperimentVerdict(...)
    judge_id: str
    evaluator_id: str
    reasons: tuple[str, ...]           # _refs (unique/nonblank -> valid quarantine reasons)
    contract_fingerprint: str
    decided_at: str = ""               # default to utc_now() when empty

    @property
    def binding_digest(self) -> str:   # canonical_digest(self.candidate)
```
`__post_init__` enforces the four-identity separation: `{candidate.proposer_id,
candidate.builder_id, evaluator_id, judge_id}` must contain 4 distinct
nonempty values (acceptance criterion 2; also exactly what
`PromptRegistry._validate_decision_event` demands).

```python
@dataclass(frozen=True, slots=True)
class PromotionDecisionLog:
    decisions: tuple[PromotionDecision, ...] = ()

    def append(self, decision: PromotionDecision, *, court_history: CourtHistory) -> "PromotionDecisionLog"
    def for_candidate(self, candidate_id: str) -> tuple[PromotionDecision, ...]
```
`append` returns a NEW log (immutable, like `CourtHistory.append`) and raises
`PromotionAuthorityError` unless ALL hold:
1. `decision.decision_id` is unused and `decision.court_case_id` is not already
   consumed by a prior decision (append-only, one decision per court case).
2. A `CourtRecord` with `case.case_id == decision.court_case_id` exists in
   `court_history.records` (independent, already-validated court decision).
3. Candidate binding: `record.case.subject == decision.candidate.artifact_digest`.
4. Identity binding: `record.verdict.decided_by == decision.judge_id`, and
   `{proposer_id, builder_id, evaluator_id} <= set(record.case.affected_identities)`
   (so `court_runtime._validate_panel` has already refused any of them as judge).
5. `decision.verdict in _COMPATIBLE_DISPOSITIONS` and
   `record.verdict.disposition in _COMPATIBLE_DISPOSITIONS[decision.verdict]`.
6. For KEEP only: `record.case.claim_kind is CourtClaimKind.SUPERIORITY`
   (champion-beating claims carry the superiority burden).
7. No prior decision for the same `candidate_id` has a verdict in
   `_TERMINAL_VERDICTS` (RETEST may be followed; terminal verdicts may not).

### 3.4 `PromotionAuthority` — the only pointer-moving surface

```python
class PromotionAuthority:
    def __init__(self, registry: PromptRegistry) -> None:
        self.registry = registry
        self._log = PromotionDecisionLog()
        self._applied: frozenset[str] = frozenset()
        self._receipts: tuple[dict[str, Any], ...] = ()

    @property
    def log(self) -> PromotionDecisionLog: ...
    @property
    def receipts(self) -> tuple[dict[str, Any], ...]: ...

    def submit(self, decision: PromotionDecision, *, court_history: CourtHistory) -> PromotionDecision
    def apply(self, decision_id: str) -> dict[str, Any]
    def rollback(self, decision_id: str) -> dict[str, Any]
```

`submit` = `self._log = self._log.append(decision, court_history=court_history)`,
then return the decision. No pointer motion here, ever.

`apply(decision_id)` control flow:
1. Look up the decision in `self._log`; unknown id or id in `self._applied` →
   `PromotionAuthorityError` ("only a logged, unapplied decision can act").
2. `current = self.registry.champion_digest(candidate.role)`. If
   `candidate.artifact_digest == current` → error: decisions against the
   active champion must go through `rollback()`.
3. Non-KEEP verdicts NEVER touch the pointer (acceptance criterion 3):
   - `QUARANTINE`: `self.registry.quarantine(candidate.role, candidate.artifact_digest,
     actor=decision.judge_id, experiment_id=candidate.experiment_id,
     reasons=decision.reasons)`; receipt `action="quarantine-candidate"`.
   - `RETEST`/`DISCARD`/`STOP`: no registry call; receipt `action="retain-champion"`.
4. KEEP path — build the EXACT ledger payload `PromptRegistry._validate_decision_event`
   verifies (every key below is checked verbatim; get one wrong and `promote`
   raises `RuntimeError`):
   ```python
   payload = {
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
   sequence = self.registry.ledger.append_event(
       candidate.experiment_id, "experiment.decision", decision.judge_id, payload)
   ```
   Then, inside `try`:
   ```python
   prior = self.registry.promote(
       candidate.role, candidate.artifact_digest,
       promoted_by=decision.judge_id,
       experiment_id=candidate.experiment_id,
       expected_current=candidate.parent_champion_digest,
       decision_event_sequence=sequence)
   ```
   `except RuntimeError as error:` record a receipt with `status="failed"`,
   `pointer_after=self.registry.champion_digest(candidate.role)`, and the error
   text in `reasons`; then `raise PromotionAuthorityError("atomic promotion was
   refused: " + str(error)) from error`. The pointer is untouched because
   `promote` validates before its `_atomic_json` write (atomic-pointer-failure
   evidence).
5. On success record `self._applied |= {decision_id}` and a receipt
   `action="promote"`, `status="applied"`, `prior_digest=prior`.

`rollback(decision_id)` control flow (acceptance criterion 4):
1. Same logged/unapplied lookup as `apply` step 1.
2. `decision.verdict in _ROLLBACK_VERDICTS` else error (KEEP/RETEST/STOP never
   authorize rollback).
3. `candidate.parent_champion_digest` must be non-None (the retained prior
   champion) and `registry.champion_digest(role)` must equal
   `candidate.artifact_digest` (the adverse decision binds the ACTIVE champion).
4. `restored = candidate.parent_champion_digest`;
   `prior = self.registry.rollback_champion(candidate.role, restored,
   actor=decision.judge_id, reason="; ".join(decision.reasons))` — wrap
   `RuntimeError` like apply step 4 (failure receipt + `PromotionAuthorityError`).
5. If verdict is `QUARANTINE`, additionally quarantine the demoted digest via
   `registry.quarantine(...)` AFTER the pointer is restored.
6. Mark applied; receipt `action="rollback"`, `restored_digest=restored`,
   `prior_digest=prior`.

### 3.5 Receipt shape (durable + in-memory)

Private helper `_record_receipt(self, decision, *, action, status, prior_digest,
restored_digest=None, reasons=(), pointer_after=None) -> dict[str, Any]` builds:

```python
{
  "schema_version": 1,
  "kind": "promotion.receipt",
  "decision_id": ..., "court_case_id": ..., "verdict": decision.verdict.value,
  "role": candidate.role, "candidate_digest": candidate.artifact_digest,
  "binding_digest": decision.binding_digest,
  "action": "promote" | "retain-champion" | "quarantine-candidate" | "rollback",
  "status": "applied" | "failed",
  "prior_digest": ..., "restored_digest": ..., "pointer_after": ...,
  "reasons": list(...), "recorded_at": utc_now(),
}
```
then sets `receipt["receipt_digest"] = canonical_digest(receipt_body)` (digest of
the dict before the key is added), appends
`self.registry.ledger.append_event(candidate.experiment_id, "promotion.receipt",
decision.judge_id, receipt)` for durability, extends `self._receipts`, returns it.

### 3.6 Module docstring + imports (top of file)

```python
"""Court-gated atomic champion promotion and rollback authority."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping

from ..models import Role, utc_now
from ..prompt_registry import PromptRegistry
from ..recursive_improvement import ExperimentVerdict
from .canonical import canonical_digest
from .court_runtime import CourtClaimKind, CourtDisposition, CourtHistory
```

## 4. Implementation order (small commits on `autopilot/promote-530`)

1. `promotion.py`: error type, helpers, verdict constants, `PromotionCandidate`,
   `PromotionDecision` (§3.1–3.3 through the dataclasses).
2. `promotion.py`: `PromotionDecisionLog.append` with the seven checks.
3. `promotion.py`: `PromotionAuthority` submit/apply/rollback + receipts.
4. `tests/test_hive_cortex_promotion.py`: helpers + the four required tests (§5).
5. `docs/execution/PROMOTION_AUTHORITY.md`: authority model, verdict→disposition
   table (§3.2), exact `experiment.decision` payload (§3.4), receipt shape
   (§3.5), invariants "only KEEP moves the pointer" and "rollback restores the
   retained prior champion", and the escalation rule that no caller may bypass
   `PromotionAuthority` to call `PromptRegistry.promote` directly.
6. Run focused tests, capture receipts, open the draft PR (stopping condition:
   draft PR + node receipt; do not merge, do not start downstream nodes).

## 5. Test plan — `tests/test_hive_cortex_promotion.py`

Follow the exact convention of `tests/test_hive_cortex_court.py`: stdlib
`unittest`, module-level helper functions, ONE test class, one method per
required test name, `if __name__ == "__main__": unittest.main()`.

Shared helpers (module functions / setUp):
- `_registry(testcase)`: `tempfile.TemporaryDirectory()` +
  `PromptRegistry(root)`; register cleanup with `testcase.addCleanup(registry.close)`
  and the tempdir's cleanup (Windows-safe ordering: close before rmdir).
- `_court_history(subject_digest, *, disposition, claim_kind, case_id, judge="judge-1")`:
  builds four `CourtBrief`s (advocate/cross-examiner/expert/judge with distinct
  identities and distinct advocate vs cross tasks, each with `evidence_refs`),
  `CourtCase(case_id, claim_kind, subject_digest, ("proposer-1","builder-1","evaluator-1"))`,
  `CourtVerdict(case_id, disposition, "judge-1", ("reason",), ("evidence:1",))`,
  returns `record_case(CourtHistory(), case, briefs, verdict)`.
- `_registered_candidate(registry, *, content, parent, candidate_id, experiment_id)`:
  calls `registry.register(Role.BUILDER, content, parent_digest=parent,
  created_by="proposer-1", experiment_id=experiment_id)` and returns a
  `PromotionCandidate` with that digest.
- `_decision(candidate, verdict, case_id, decision_id)`: judge `judge-1`,
  evaluator `evaluator-1`, reasons `("court-authorized",)`,
  contract_fingerprint `"fp-1"`.
- `_keep(authority, registry, *, content, parent, ids...)`: full authorized KEEP
  (register → SUPERIORITY/ADOPT court → submit → apply); used to establish
  champions A and B.

| required_tests name | test method | asserts |
|---|---|---|
| `promotion-authority-tests` | `test_promotion_authority_tests` | full KEEP flow moves the pointer (`registry.champion_digest == candidate digest`; receipt `action=="promote"`, `status=="applied"`); RETEST (DEFER court) apply leaves the pointer unchanged with a `retain-champion` receipt; KEEP submitted against a DEFER court record raises `PromotionAuthorityError`; duplicate `decision_id` and a second decision after a terminal verdict for the same `candidate_id` both raise (append-only); `apply` of an unlogged decision raises |
| `self-promotion-attack-tests` | `test_self_promotion_attack_tests` | constructing `PromotionDecision` with `judge_id == candidate.proposer_id` (and with `evaluator_id == builder_id`) raises `PromotionAuthorityError`; `submit` with `judge_id != record.verdict.decided_by` raises; `record_case` with the judge listed in `affected_identities` raises `CourtProtocolError` (court refuses the panel, so no such record can exist); direct `registry.promote(...)` without a decision event still raises `RuntimeError` matching `"experiment.decision"` (the blocked path stays blocked) |
| `atomic-pointer-failure-tests` | `test_atomic_pointer_failure_tests` | establish champion A then B via `_keep`; craft candidate C registered with `parent_digest == A` (stale), ADOPT superiority court, submit, then `apply` raises `PromotionAuthorityError`; `registry.champion_digest` is STILL B; last receipt has `status=="failed"`, `action=="promote"`, `pointer_after == B`; a second `apply` of an already-applied decision raises and the pointer is unchanged |
| `rollback-promotion-tests` | `test_rollback_promotion_tests` | champions A then B (B's parent is A); adverse QUARANTINE court case bound to subject B; decision verdict QUARANTINE with candidate `{artifact: B, parent: A}` and a fresh `candidate_id`/`case_id`; `rollback` restores A (`champion_digest == A`), quarantines B (`registry.is_quarantined(B)`), receipt `action=="rollback"`, `restored_digest == A`; `rollback` with a KEEP decision raises; `rollback` when the candidate is not the active champion raises |

Edge cases folded in above: `expected_current=None` first promotion,
one-decision-per-court-case, verdict/disposition mismatch, KEEP requiring
`CourtClaimKind.SUPERIORITY`.

**Exact focused commands (the ONLY tests the worker runs):**

```bash
PYTHONPATH=src python -m unittest tests.test_hive_cortex_promotion -v
```
PowerShell equivalent: `$env:PYTHONPATH="src"; PYTHONPATH=src python -m unittest tests.test_hive_cortex_promotion -v`.
(`PYTHONPATH=src` is required: the repo is a src-layout package and a stale
editable install may shadow it. Verified working for
`tests.test_hive_cortex_court` on this branch.) Never run
`python -m unittest discover` — that gate belongs exclusively to the authenticated
validation broker.

## 6. Acceptance self-check → completion-receipt evidence

| Criterion | Demonstrated by | Receipt evidence |
|---|---|---|
| Append-only, candidate-bound decisions | `PromotionDecisionLog.append` checks 1–3 and 7; duplicate/terminal assertions in `test_promotion_authority_tests` | focused-test transcript naming the raising assertions |
| Proposer/builder/evaluator/judge separation | `PromotionDecision.__post_init__` four-distinct-identity rule + court `_validate_panel` reuse; `test_self_promotion_attack_tests` | test transcript + quoted `PromotionAuthorityError` messages |
| Only KEEP moves the pointer | `apply` step 3 performs no registry pointer call for non-KEEP; RETEST assertion; failed-KEEP pointer check in `test_atomic_pointer_failure_tests` | `champion_digest` before/after values in the test transcript |
| Rollback restores retained prior champion + receipt | `rollback` steps 3–6; `test_rollback_promotion_tests` asserts restored digest and `rollback` receipt | receipt dict (with `receipt_digest`) echoed in the test transcript |
| Plus node evidence requirements | base/final commit SHAs, `git diff --name-only` bound to the 3 write paths, focused-test command output, role/authority identities, rollback reference (`git revert <node commit>`) | node completion receipt |

## 7. Out-of-scope traps — do NOT

- Do not modify `prompt_registry.py`, `court_runtime.py`,
  `recursive_improvement.py`, `courtroom.py`, `ledger.py`, or ANY file outside
  the three write paths — even a one-line "fix". If a registry check seems to
  block a legitimate flow, the flow is wrong: escalate via `autopilot fail`
  rather than weakening the gate (node assumption: no node may expand its own
  authority or weaken acceptance to pass).
- Do not touch any `__init__.py` (no re-export of `promotion`), `conftest.py`,
  `pyproject.toml`, `.autopilot/**`, `.github/CODEOWNERS`,
  `.github/governance/**`, `evidence/courts/**`, or
  `docs/architecture/HARDENED_VISION_CONTRACT.md`.
- Do not define a new five-verdict enum — reuse `ExperimentVerdict`. Do not
  invent APIs on `PromptRegistry` (e.g. there is NO `set_champion`); the only
  pointer mutations are `promote` and `rollback_champion` as quoted in §2.
- Do not import `hive_mind_os.brain_kernel.evaluation_runtime`,
  `challengers`, or `learning_runtime` — sibling nodes own those; promotion
  consumes court records and registry state only.
- Do not call `registry.bootstrap` or the generation-zero path in tests; use
  first-champion promotion with `expected_current=None` through the full
  authorized flow instead.
- Do not write to `evidence/**` or add benchmark claims; do not run repo-wide
  test discovery; do not merge the draft PR or push to the release branch.
- Do not let quarantine precede pointer restoration in `rollback` (the champion
  must never be left both active and quarantined).
