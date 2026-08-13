# HUMANLESS-430 — Humanless operation qualification runbook

Worker instructions for node `HUMANLESS-430` on branch `autopilot/humanless-430`
(round R2B, wave `DELIVERY-420 HUMANLESS-430 CHEAT-440 LEARN-500`, released only
after DURABLE-410 has integrated — your acceptance criterion "resumes after
interruption without restating context" depends on it).
This runbook plus the rendered prompt is your complete context; do not re-read
`.autopilot/plan.json` or `.autopilot/README.md` — the controller enforces every
gate deterministically and fails closed.

## 1. Contract summary

**Objective.** Prove role-first end-to-end resolution across five situation
classes — ambiguity, missing tests, design tradeoffs, CI repair, and
recoverable failures — without any human question, using only the already-merged
deterministic kernel surfaces plus retained evidence.

**Compressed acceptance criteria.**
1. All role-resolvable questions are answered by role consultation or
   deterministic evidence.
2. Software defects create repair work, not human questions.
3. Only genuine authority classes produce human escalation packets.
4. The mission resumes after interruption without restating context.

**Scope table.**

| Kind | Paths |
|---|---|
| write (ONLY these) | `tests/hive_cortex/test_humanless_operation.py`, `evidence/autonomy/humanless/**`, `docs/execution/HUMANLESS_OPERATION_RESULTS.md` |
| read | `tests/hive_cortex/**`, `src/hive_mind_os/brain_kernel/**` (plus `src/hive_mind_os/contracts.py` and `src/hive_mind_os/scheduler.py`, which `brain_kernel` imports and this runbook quotes) |
| forbidden | `.github/CODEOWNERS`, `.github/governance/**`, `evidence/courts/**`, `docs/architecture/HARDENED_VISION_CONTRACT.md` |

**Hard rules (restated; violations are remand-on-sight).**
- Create/modify ONLY the three write-scope paths above. Explicitly forbidden:
  ANY `__init__.py` (including `tests/hive_cortex/__init__.py`), any
  `conftest.py`, `pyproject.toml`, `.autopilot/**`, everything in
  forbidden_scope, and every sibling node file — in particular CHEAT-440's
  `tests/hive_cortex/test_no_cheating.py` and `evidence/autonomy/no-cheating/**`.
- No new `src/` modules for this node; if a helper is needed it lives inside
  `tests/hive_cortex/test_humanless_operation.py` itself. Import kernel modules
  by full module path (`hive_mind_os.brain_kernel.consultation`); never edit a
  package re-export.
- Never touch the release branch; never rebase/squash/amend the node branch;
  commit forward only.
- Run ONLY the focused commands in section 5. Never run
  `python -m unittest discover` or any repo-wide test pass — the R2B integrator
  owns the single leased repo-wide run.
- Do not weaken, skip, or fork `tests/hive_cortex/acceptance_harness.py`
  semantics; consume it as-is via relative import.

**Semantic lock:** `humanless-qualification`. **Consultation routes:** orchestrator, curator.
**Stopping condition:** open a draft PR to `main` with a validated node receipt; do not merge; do not start downstream nodes.

## 2. Existing-code map (real signatures; do not re-derive)

All paths repo-relative. These symbols exist on the release branch today.

| Path | Symbol | Real signature / shape | Role in this node |
|---|---|---|---|
| tests/hive_cortex/acceptance_harness.py | `SPECIALIST_ROLES` | `tuple[str, ...]` of the eight role names | canonical role list for run records |
| tests/hive_cortex/acceptance_harness.py | `GENUINE_HUMAN_AUTHORITY` | `set[str]` = {"credential","legal","financial","production-access","protected-branch","owner-value","consent","external-contract"} | harness-side genuine-authority vocabulary |
| tests/hive_cortex/acceptance_harness.py | `AcceptanceRun` | frozen dataclass; fields `roles, consultations, approvals, sealed_candidate, observed_commits, sealed_commits, future_commits, authority_class, human_escalated, expected_effects, receipt_candidate, receipt_roles, receipt_effects` | end-to-end run record |
| tests/hive_cortex/acceptance_harness.py | `Consultation` | `Consultation(requester: str, consulted: tuple[str, ...], independent: bool = True)` | run-record consultation entry |
| tests/hive_cortex/acceptance_harness.py | `Approval`, `EffectReceipt` | `Approval(actor, approved_by, candidate_commit)`; `EffectReceipt(role, effect_id)` | run-record entries |
| tests/hive_cortex/acceptance_harness.py | `validate_run` | `def validate_run(run: AcceptanceRun) -> tuple[str, ...]` | returns issue codes; `"human-escalation-software-defect"` when `human_escalated` without genuine class |
| tests/hive_cortex/acceptance_harness.py | `load_fixture_inventory`, `validate_fixture_inventory` | `load_fixture_inventory(root: Path) -> tuple[FixtureSpec, ...]`; `validate_fixture_inventory(fixtures) -> tuple[str, ...]` | locate the `no-test` fixture (missing-tests scenario evidence) |
| src/hive_mind_os/brain_kernel/consultation.py | `AUTHORITY_CLASSES` | `frozenset({"credential_or_secret","legal_or_regulatory","financial_spend","production_access","protected_branch_merge","owner_value_choice","personal_consent","external_contractual_commitment"})` | the ONLY classes allowed to escalate |
| src/hive_mind_os/brain_kernel/consultation.py | `ConsultationReason` | StrEnum: AMBIGUOUS_DESIGN, MISSING_EVIDENCE, MISSING_EXTERNAL_AUTHORITY, UNSAFE_EFFECT, INDEPENDENCE_CONCERN, SUSPECTED_CHEATING, NO_PROGRESS | typed question reasons |
| src/hive_mind_os/brain_kernel/consultation.py | `ConsultationDecision` | StrEnum: RESOLVED, REMAND, REPLAN, BLOCKED_EVIDENCE, TRUE_AUTHORITY_REQUIRED, QUARANTINE | typed outcomes |
| src/hive_mind_os/brain_kernel/consultation.py | `ConsultationRequest` | frozen dataclass `(request_id, mission_id, question, reason_code, requesting_role, applicable_roles, round=1, suspected_cheating=False, evidence_refs=(), authority_class=None)`; rejects requester in applicable_roles, <2 roles, unknown authority_class | question construction |
| src/hive_mind_os/brain_kernel/consultation.py | `RoleAssessment` | frozen dataclass `(role, identity, answer=None, evidence_refs=(), proposed_decision=ConsultationDecision.RESOLVED, dissent=None, cheating_disposition=CheatingDisposition.NOT_APPLICABLE, authority_required=False, identity_kind="model_role")` | role testimony |
| src/hive_mind_os/brain_kernel/consultation.py | `evaluate_consultation` | `def evaluate_consultation(request: ConsultationRequest, assessments: Iterable[RoleAssessment]) -> ConsultationResult` | the role-first adjudicator |
| src/hive_mind_os/brain_kernel/consultation.py | `ConsultationResult` | frozen dataclass; invariants include `human_escalation == (decision is TRUE_AUTHORITY_REQUIRED)` and escalation requires `authority_class in AUTHORITY_CLASSES` plus non-empty `evidence_refs` | outcome contract to assert against |
| src/hive_mind_os/brain_kernel/consultation.py | `ConsultationLoop` | frozen dataclass `(history=(), max_rounds=3)` with `append(request, assessments) -> tuple[ConsultationLoop, ConsultationResult]`, property `exhausted` | bounded loop |
| src/hive_mind_os/brain_kernel/reconciler.py | `RepairKind` | StrEnum: RELEASE_STALE_LEASE, RETRY, REMAND, REBUILD_WORKSPACE, ROLLBACK, QUARANTINE | finite repair vocabulary (no human channel exists) |
| src/hive_mind_os/brain_kernel/reconciler.py | `ReconciliationPolicy` | frozen dataclass `(max_retries=3, no_progress_limit=3, max_repairs_per_pass=8)` | retry bounds |
| src/hive_mind_os/brain_kernel/reconciler.py | `DesiredStateReconciler` | `__init__(self, policy: ReconciliationPolicy | None = None)`; `reconcile(self, observed: ObservedState | Mapping[str, Any], *, now: float) -> ReconciliationResult` | CI repair + recovery planner |
| src/hive_mind_os/brain_kernel/reconciler.py | `ObservedState.from_document` | `@classmethod from_document(cls, document: Mapping[str, Any]) -> ObservedState`; accepts keys `mission_id, mission_status, work, leases, intents, workspaces, provider_failures, verifications, no_progress_count, progress_signature, authority_scope` | interruption snapshots |
| src/hive_mind_os/brain_kernel/reconciler.py | `ReconciliationResult` | properties `actions: tuple[RepairAction, ...]`, `quarantined: bool`; `apply(handlers: Mapping[str | RepairKind, Callable[[RepairAction], Any]]) -> tuple[str, ...]` | assert repair plans; applied ids |
| src/hive_mind_os/brain_kernel/canonical.py | `canonical_digest` | `def canonical_digest(value: Any) -> str` | evidence-packet digest binding |
| src/hive_mind_os/brain_kernel/workers.py | `KernelWorker` | `__init__(self, scheduler: Scheduler, scope_locks: ScopeLockStore, owner: str, executor: KernelExecutor, *, store: KernelStore | None = None)`; `enqueue(self, mission_id, work_id, write_scope, *, max_attempts=3) -> Job`; `run_once(self) -> bool` | recoverable execution failure e2e |
| src/hive_mind_os/brain_kernel/workers.py | `ScopeLockStore` | `__init__(self, state_dir: str | Path)`; `acquire(paths, owner, now, ttl) -> bool`; `close()` | worker setup |
| src/hive_mind_os/scheduler.py | `Scheduler` | `__init__(self, state_dir: str | Path, *, clock: Clock | None = None, lease_seconds: float = 30.0, backoff_seconds: float = 1.0)`; `get(job_id) -> Job`; `fail(...)` sets state `"ready"` (retry) or `"dead-letter"` when attempts exhausted | retry semantics |
| src/hive_mind_os/scheduler.py | `ManualClock` | dataclass `(value: float = 0.0)` with `now()` and `advance(seconds)` | deterministic time |
| src/hive_mind_os/contracts.py | `ROLE_NAMES` | `frozenset` of the eight role names (consultation validates roles against it) | role validity |

Reference test style to copy: `tests/hive_cortex/test_acceptance_harness.py`
(relative import `from .acceptance_harness import ...`, plain `unittest`,
`if __name__ == "__main__": unittest.main()`), and
`tests/test_brain_kernel_workers.py` (Scheduler/ScopeLockStore/tempdir setup;
retained-evidence verification style as in
`tests/test_brain_kernel_local_assurance_evidence.py`).

Dependency note: MISSION-400 (`src/hive_mind_os/brain_kernel/mission_runtime.py`)
merges in R1 before this node runs. This node's tests are deliberately built on
the stable surfaces above and MUST NOT import `mission_runtime` — that keeps
HUMANLESS-430 lock-disjoint and immune to MISSION-400 API drift. If, at
execution time, an assumption here contradicts merged code, use `autopilot fail`
with a blocker; do not improvise.

## 3. Design

### 3.1 New file: `tests/hive_cortex/test_humanless_operation.py`

One module, standard library + repo imports only:

```python
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.consultation import (
    AUTHORITY_CLASSES,
    ConsultationDecision,
    ConsultationLoop,
    ConsultationReason,
    ConsultationRequest,
    ConsultationResult,
    RoleAssessment,
    evaluate_consultation,
)
from hive_mind_os.brain_kernel.reconciler import (
    DesiredStateReconciler,
    ReconciliationPolicy,
    RepairKind,
)
from hive_mind_os.brain_kernel.workers import KernelWorker, ScopeLockStore
from hive_mind_os.scheduler import ManualClock, Scheduler

from .acceptance_harness import (
    GENUINE_HUMAN_AUTHORITY,
    SPECIALIST_ROLES,
    AcceptanceRun,
    Approval,
    Consultation,
    EffectReceipt,
    load_fixture_inventory,
    validate_run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "hive_cortex"
EVIDENCE_PACKET = REPO_ROOT / "evidence" / "autonomy" / "humanless" / "humanless-qualification.json"
MISSION_ID = "MISSION-humanless-430"
```

**Module-level helpers (exact signatures to implement):**

```python
def _request(request_id: str, reason: ConsultationReason, *, question: str,
             requesting_role: str = "builder",
             applicable_roles: tuple[str, ...] = ("orchestrator", "curator"),
             evidence_refs: tuple[str, ...] = (),
             authority_class: str | None = None,
             round: int = 1) -> ConsultationRequest: ...

def _assessment(role: str, *, answer: str | None = None,
                proposed: ConsultationDecision = ConsultationDecision.RESOLVED,
                evidence_refs: tuple[str, ...] = (),
                dissent: str | None = None,
                authority_required: bool = False) -> RoleAssessment:
    # identity=f"model:{role}-humanless", identity_kind="model_role"
    ...

def qualification_scenarios() -> tuple[dict[str, object], ...]: ...

def build_qualification_packet() -> dict[str, object]: ...
```

`qualification_scenarios()` deterministically re-runs the five situation
classes and returns one plain dict per scenario, sorted by `scenario_id`:

| scenario_id | mechanism | expected fields |
|---|---|---|
| `ambiguity` | `evaluate_consultation` of an `AMBIGUOUS_DESIGN` request with orchestrator+curator assessments (both `RESOLVED`, one carrying `answer=...`, shared `evidence_refs=("evidence/autonomy/humanless/humanless-qualification.json",)`) | `decision="RESOLVED"`, `human_escalation=False`, `answered=True` |
| `missing-tests` | locate the `no-test` fixture via `load_fixture_inventory(FIXTURE_ROOT)`; consultation reason `MISSING_EVIDENCE` with assessments proposing `REMAND` and `evidence_refs=(f"tests/fixtures/hive_cortex/{fixture.fixture_id}",)` | `decision="REMAND"` (repair work), `human_escalation=False` |
| `design-tradeoff` | `AMBIGUOUS_DESIGN` request; orchestrator proposes `REPLAN` with `dissent="prefer smaller interface"`, curator proposes `RESOLVED` with an answer | `decision="REPLAN"`, `dissent_recorded=True`, `human_escalation=False` |
| `ci-repair` | `DesiredStateReconciler().reconcile({... provider_failures: [{"failure_id": "ci-1", "work_id": "WORK-ci", "retryable": True, "attempts": 1}] ...}, now=100.0)` | `repairs=["retry:WORK-ci"]`, `quarantined=False`, `human_escalation=False` |
| `recoverable-interruption` | reconcile a snapshot with an expired lease (`expires_at=10.0`, now 100.0), a missing workspace (`exists=False`), and an `AWAITING_VERIFICATION` work item with `verifications=[{"work_id": ..., "status": "INTERRUPTED"}]` | repair kinds exactly `{release-stale-lease, rebuild-workspace, remand}`, `quarantined=False`, `human_escalation=False` |

Every scenario dict has the same closed key set:
`{"scenario_id", "reason", "mechanism", "decision", "repairs",
"human_escalation", "answered", "dissent_recorded"}` (use `""`/`[]`/`False`
defaults so the packet is canonical). `human_escalation` comes from the
`ConsultationResult.human_escalation` field for consultation scenarios and is
the constant `False` for reconciler scenarios — assert in tests that the
reconciler vocabulary (`RepairKind`) contains no human/escalation member.

`build_qualification_packet()` returns:

```python
{
    "packet_id": "humanless-qualification-v1",
    "node_id": "HUMANLESS-430",
    "semantic_lock": "humanless-qualification",
    "genuine_authority_classes": sorted(AUTHORITY_CLASSES),
    "harness_authority_classes": sorted(GENUINE_HUMAN_AUTHORITY),
    "scenarios": list(qualification_scenarios()),
    "scenario_digest": canonical_digest(list(qualification_scenarios())),
}
```

**`__main__` hook** (this is how the retained evidence file is produced —
regeneration is the verification):

```python
if __name__ == "__main__":
    if "--write-evidence" in sys.argv:
        EVIDENCE_PACKET.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_PACKET.write_text(
            json.dumps(build_qualification_packet(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    else:
        unittest.main()
```

### 3.2 Test classes (required_tests binding)

**`HumanlessOperationSuiteTests(unittest.TestCase)`** — `humanless-operation-suite`
- `test_ambiguity_resolved_by_role_consultation`: run the `ambiguity` request
  through `ConsultationLoop().append(...)`; assert
  `result.decision is ConsultationDecision.RESOLVED`, `result.answer` truthy,
  `result.human_escalation is False`, all `identity_records` have
  `identity_kind == "model_role"`, and `result.role_first_exhausted is True`.
- `test_missing_tests_become_repair_work`: the `missing-tests` scenario yields
  `REMAND` and carries the fixture path in `evidence_refs`; assert
  `human_escalation is False` and the fixture really has
  `tests_present is False`.
- `test_design_tradeoff_replans_with_recorded_dissent`: decision `REPLAN`,
  `result.dissent` non-empty and containing the divergence line
  (`any("diverged" in item for item in result.dissent)`), no escalation.
- `test_ci_failure_creates_bounded_retry_repair`: reconcile the `ci-repair`
  snapshot; assert exactly one action, `kind is RepairKind.RETRY`,
  `target_id == "WORK-ci"`, `attempt == 1`, `max_attempts == 3`,
  `result.quarantined is False`; then
  `result.apply({RepairKind.RETRY: handler})` returns `("retry:WORK-ci",)` and
  unknown-kind handlers are never invented (apply with `{}` returns `()`).
- `test_recoverable_interruption_resumes_without_restating_context`: reconcile
  the `recoverable-interruption` snapshot twice from the same plain document;
  assert the two `ReconciliationResult.desired.desired_digest` values are
  identical and equal actions (resumption is a pure function of retained
  state — no context restatement), repair kinds are exactly
  `{RELEASE_STALE_LEASE, REBUILD_WORKSPACE, REMAND}`, and the affected work
  records carry `desired_status == "READY"`.
- `test_worker_retries_recoverable_execution_failure`: inside
  `tempfile.TemporaryDirectory()`, build
  `Scheduler(root, clock=ManualClock(), backoff_seconds=0)` and
  `ScopeLockStore(root)`; executor raises `RuntimeError("transient")` on first
  call, succeeds on second. `worker.enqueue(MISSION_ID, "WORK-retry", ())`;
  first `run_once()` → `scheduler.get(job.id).state == "ready"` and
  `last_error` startswith `"RuntimeError"`; `clock.advance(1)`; second
  `run_once()` → state `"done"`. Close scheduler and locks in `finally`.
- `test_end_to_end_run_passes_acceptance_harness`: construct a fully wired
  `AcceptanceRun` exactly like `valid_run()` in
  `tests/hive_cortex/test_acceptance_harness.py` (eight roles, one independent
  `Consultation("curator", ("steward", "optimizer"))`, cross-role `Approval`,
  sealed candidate, `human_escalated=False`) and assert
  `validate_run(run) == ()`.

**`GenuineAuthorityClassificationSuiteTests(unittest.TestCase)`** — `genuine-authority-classification-suite`
- `test_every_genuine_authority_class_escalates`: for each class in
  `sorted(AUTHORITY_CLASSES)` (subTest), a `MISSING_EXTERNAL_AUTHORITY` request
  with that `authority_class`, non-empty `evidence_refs`, and two assessments
  with `authority_required=True` yields
  `decision is ConsultationDecision.TRUE_AUTHORITY_REQUIRED`,
  `human_escalation is True`, `authority_class` preserved, `answer is None`.
- `test_unknown_authority_class_is_rejected_at_construction`:
  `ConsultationRequest(..., authority_class="convenience")` raises `ValueError`.
- `test_authority_claim_without_evidence_blocks_instead_of_escalating`: same
  request with `evidence_refs=()` on request and assessments →
  `decision is ConsultationDecision.BLOCKED_EVIDENCE`,
  `human_escalation is False`.
- `test_result_contract_rejects_convenience_escalation`: `replace()` a valid
  escalation `ConsultationResult` with `decision=ConsultationDecision.RESOLVED`
  (keeping `human_escalation=True`) and assert `ValueError`; also assert
  `replace(result, authority_class=None)` raises.
- `test_harness_accepts_only_genuine_authority_packets`: for each class in
  `sorted(GENUINE_HUMAN_AUTHORITY)`, an `AcceptanceRun` with
  `human_escalated=True, authority_class=<class>` passes `validate_run`;
  with `authority_class=None` the issues contain
  `"human-escalation-software-defect"`.

**`SoftwareDefectNotHumanSuiteTests(unittest.TestCase)`** — `software-defect-not-human-suite`
- `test_repair_vocabulary_has_no_human_channel`: assert
  `{item.value for item in RepairKind} == {"release-stale-lease", "retry",
  "remand", "rebuild-workspace", "rollback", "quarantine"}` — no member names
  a human, question, or escalation.
- `test_defect_within_budget_retries_not_escalates`: retryable provider failure
  with `attempts=0` → single `RETRY` action, `quarantined is False`.
- `test_exhausted_defect_quarantines_in_system`: `attempts=3` with
  `ReconciliationPolicy(max_retries=3)` → `QUARANTINE` action for the work id,
  `desired.mission_status == "QUARANTINED"`; quarantine keeps the mission
  inside the system (assert the action's `to_document()` has no human field).
- `test_no_progress_quarantines_within_bound`: `no_progress_count=3` →
  quarantine targeting the mission id with `attempt == 3, max_attempts == 3`.
- `test_defect_consultation_cannot_manufacture_authority`: request WITHOUT
  `authority_class` but with an assessment claiming `authority_required=True`
  and no evidence → `decision is ConsultationDecision.BLOCKED_EVIDENCE`, never
  `TRUE_AUTHORITY_REQUIRED`, `human_escalation is False`.
- `test_retained_evidence_packet_matches_recomputation`: load
  `EVIDENCE_PACKET` JSON; assert it equals `build_qualification_packet()`
  exactly, `packet["scenario_digest"] == canonical_digest(packet["scenarios"])`,
  and every scenario has `human_escalation is False`.

### 3.3 Evidence layout (`evidence/autonomy/humanless/`)

| File | Producer | Content |
|---|---|---|
| `humanless-qualification.json` | `python -m tests.hive_cortex.test_humanless_operation --write-evidence` | the packet from 3.1; deterministic, digest-bound |
| `receipts/focused-tests.txt` | worker, captured verbatim | full output of the three focused commands in section 5 |
| `receipts/commands.json` | worker, hand-written JSON | list of `{"command", "exit_code", "started_branch", "base_commit"}` records for the receipt |

### 3.4 Results document (`docs/execution/HUMANLESS_OPERATION_RESULTS.md`)

Sections, in order: purpose (1 paragraph, cite the four acceptance criteria);
scenario table (five rows: situation class → kernel mechanism → decision →
human questions asked = 0); genuine-authority table (the eight
`AUTHORITY_CLASSES` values ↔ the eight harness `GENUINE_HUMAN_AUTHORITY`
labels, noting they are distinct vocabularies checked by distinct layers);
evidence index (the three files above with the packet's `scenario_digest`);
how to re-verify (the exact commands from section 5 plus the
`--write-evidence` regeneration check: regenerating must produce a
byte-identical file). Keep under ~120 lines; no promises about future nodes.

## 4. Implementation order (small commits, forward only)

1. `git switch autopilot/humanless-430` (create from the current release-branch
   head if the dispatcher has not already created it). Record the base commit
   SHA for the receipt.
2. Commit 1 — `tests/hive_cortex/test_humanless_operation.py` with imports,
   helpers, `qualification_scenarios`, `build_qualification_packet`, the
   `__main__` hook, and `HumanlessOperationSuiteTests`. Run focused command A.
3. Commit 2 — add `GenuineAuthorityClassificationSuiteTests` and
   `SoftwareDefectNotHumanSuiteTests` EXCEPT the retained-packet test. Run
   focused command A again.
4. Commit 3 — generate the packet:
   `python -m tests.hive_cortex.test_humanless_operation --write-evidence`;
   add `test_retained_evidence_packet_matches_recomputation`; write
   `receipts/commands.json`; run commands A–C and capture output into
   `receipts/focused-tests.txt`. Commit evidence + test together.
5. Commit 4 — `docs/execution/HUMANLESS_OPERATION_RESULTS.md`.
6. Push the node branch, open a draft PR to `main`, attach the node receipt
   (base/final SHAs, changed-path inventory — must be exactly the three
   write-scope paths — command receipts, role identities, rollback ref =
   revert of the node commits). STOP.

## 5. Test plan

**required_tests mapping.**

| plan name | unittest binding |
|---|---|
| `humanless-operation-suite` | `tests.hive_cortex.test_humanless_operation.HumanlessOperationSuiteTests` (7 methods, section 3.2) |
| `genuine-authority-classification-suite` | `tests.hive_cortex.test_humanless_operation.GenuineAuthorityClassificationSuiteTests` (5 methods) |
| `software-defect-not-human-suite` | `tests.hive_cortex.test_humanless_operation.SoftwareDefectNotHumanSuiteTests` (6 methods) |

**Exact focused commands (run from repo root; the ONLY test commands this node
may run).**

```
A: PYTHONPATH=src python -m unittest tests.hive_cortex.test_humanless_operation -v
B: PYTHONPATH=src python -m unittest tests.hive_cortex.test_humanless_operation.GenuineAuthorityClassificationSuiteTests -v
C: PYTHONPATH=src python -m unittest tests.hive_cortex.test_humanless_operation.SoftwareDefectNotHumanSuiteTests -v
```

(`tests` is a namespace package — this invocation is proven by the existing
`PYTHONPATH=src python -m unittest tests.hive_cortex.test_acceptance_harness -v`.)

**Edge cases that must be covered (already embedded in 3.2):** all eight
authority classes individually; unknown class rejected; authority claim minus
evidence → blocked, not escalated; retry budget boundary (`attempts == max_retries`);
deterministic double-reconcile digest equality; scheduler retry after
transient executor exception with `backoff_seconds=0` and `ManualClock`;
`apply({})` no-op safety; packet regeneration byte-identity.

## 6. Acceptance self-check → receipt evidence

| Acceptance criterion | Demonstrated by | Receipt evidence |
|---|---|---|
| Role-resolvable questions answered by roles/evidence | ambiguity, missing-tests, design-tradeoff tests: `RESOLVED`/`REMAND`/`REPLAN` with `human_escalation False` | command A output in `receipts/focused-tests.txt`; scenario rows in packet |
| Software defects → repair work, not human questions | ci-repair, exhausted-quarantine, no-progress, worker-retry tests; `RepairKind` vocabulary test | command C output; `human_escalation: false` on every packet scenario |
| Only genuine authority classes escalate | all-eight-classes escalation test; unknown-class rejection; harness `human-escalation-software-defect` negative | command B output; `genuine_authority_classes` list in packet |
| Mission resumes after interruption without restating context | double-reconcile digest-equality test; worker retry-to-done test | command A output; `recoverable-interruption` packet row |
| Evidence requirements (exact commits, changed paths, receipts, roles, rollback) | worker fills the standard node receipt; changed-path inventory must equal the three write-scope paths | draft PR body + `receipts/commands.json` |

## 7. Out-of-scope traps (do NOT)

- Do NOT create or edit `tests/hive_cortex/__init__.py`, `tests/hive_cortex/acceptance_harness.py`, or `tests/hive_cortex/test_acceptance_harness.py`.
- Do NOT touch CHEAT-440's files (`tests/hive_cortex/test_no_cheating.py`, `evidence/autonomy/no-cheating/**`, `docs/execution/NO_CHEATING_RESULTS.md`) even if you notice overlap — siblings run in parallel this round.
- Do NOT import or wait for `hive_mind_os.brain_kernel.mission_runtime` (MISSION-400's file) or any other sibling deliverable; if you believe you need it, `autopilot fail` with a blocker instead.
- Do NOT add fixtures under `tests/fixtures/**` — that is ACCEPT-240's completed scope; only read them.
- Do NOT modify anything under `src/`, `.github/`, `.autopilot/`, `evidence/courts/**`, or `docs/architecture/**`.
- Do NOT run `python -m unittest discover`, pytest, or any repo-wide pass; the R2B integrator owns the single leased run.
- Do NOT loosen assertions to pass (e.g. accepting `TRUE_AUTHORITY_REQUIRED` for a defect scenario) — that violates the no-authority-expansion assumption and the `humanless-qualification` semantic lock.
- Do NOT hand-edit `humanless-qualification.json` (regenerate via `--write-evidence`), and do NOT rebase, squash, amend, force-push, or merge the PR; stop at the draft PR + receipt.
