# EVAL-520 — Independent challenger evaluation runtime

## 1. Contract summary

**Objective.** Evaluate challengers on held-out, PIT, adversarial, and comparator
surfaces with independent evaluators. A self-learning OS needs measured
generalization rather than same-run self-congratulation.

**Compressed acceptance criteria.**

| # | Criterion |
|---|---|
| AC1 | Evaluator is distinct from proposer and builder. |
| AC2 | Holdout remains hidden until prediction/plan seal. |
| AC3 | Repeated measurements, noise floor, hard guardrails, and losing evidence are retained. |
| AC4 | Missing artifacts quarantine rather than retest optimistically. |

**Scope.**

| Kind | Paths |
|---|---|
| write (exact, nothing else) | `src/hive_mind_os/brain_kernel/evaluation_runtime.py`, `tests/test_hive_cortex_evaluation.py`, `evidence/experiments/hive-cortex/**` |
| read | `src/hive_mind_os/experiment_runner.py`, `src/hive_mind_os/pit_oracle.py`, `src/hive_mind_os/benchmark_harness.py` |
| forbidden | `.github/CODEOWNERS`, `.github/governance/**`, `evidence/courts/**`, `docs/architecture/HARDENED_VISION_CONTRACT.md` |

**HARD RULES (restated, binding).**
- Create/modify ONLY the three write-scope paths above. Never touch any
  `__init__.py`, `conftest.py`, `pyproject.toml`, sibling nodes' files,
  `.autopilot/**`, or anything in forbidden scope. `evidence/experiments/hive-cortex/`
  does not exist yet — this node creates it.
- The new module is imported by full path
  `hive_mind_os.brain_kernel.evaluation_runtime`; do NOT edit any package
  `__init__.py` to re-export it.
- Work only on branch `autopilot/eval-520`. Never touch the release branch;
  never rebase/squash/amend the node branch; never run repo-wide test
  discovery (`python -m unittest discover` is the round integrator's job).
  Run only the focused commands in §5.
- Semantic locks: `challenger-evaluation`, `holdout-boundary`. Do not weaken
  either to make a test pass.

**Round / siblings.** Round R5, level 9, solo wave (`--node EVAL-520`), so no
siblings to conflict with. Stopping condition: open a draft PR with a validated
node receipt; do not merge or start downstream nodes (BENCH-600, PROMOTE-530).

## 2. Existing-code map

Quote-grounded surfaces. Files marked (read scope) may be opened; files marked
(reference only) must NOT be read or imported — their signatures are quoted
here as design precedent so nothing has to be invented.

| Path | Symbol | Real signature | Role |
|---|---|---|---|
| `src/hive_mind_os/pit_oracle.py` (read scope) | `PointInTimeOracle.seal_prediction` | `def seal_prediction(self, environment: PITEnvironment, *, target_position: int, learner_identity: str, prediction_content: Mapping[str, Any]) -> SealedPrediction` | Prediction sealed before any reveal; the ordering EVAL-520 mirrors. |
| `src/hive_mind_os/pit_oracle.py` | `PointInTimeOracle.reveal` | `def reveal(self, environment: PITEnvironment, sealed: SealedPrediction | None = None) -> dict[str, Any]` | Refuses reveal without an intact prior seal (`_require_intact_seal`). |
| `src/hive_mind_os/pit_oracle.py` | `SealViolation(RuntimeError)` | class; docstring "Reveal or grading was attempted without an intact prior seal." | Fail-closed seal error precedent. |
| `src/hive_mind_os/pit_oracle.py` | `SealedPrediction` | frozen dataclass: `episode_id, target_position, target_sha, environment_digest, learner_identity, prediction_content, digest, ledger_sequence` | Seal payload shape precedent. |
| `src/hive_mind_os/experiment_runner.py` (read scope) | `ExperimentRunner.run` | `def run(self, role, challenger, *, surface, repetitions, author_id=..., builder_id=..., evaluator_id=..., judge_id=..., contract=None) -> ExperimentRun` | Existing prompt-experiment flow; enforces four distinct identities and `accessed_holdout` quarantine. |
| `src/hive_mind_os/experiment_runner.py` | `SurfaceObservation` | frozen dataclass: `task_success: float, token_cost: float, evidence_completeness: float, artifact_refs: tuple[str, ...]` | Per-repetition observation shape precedent. |
| `src/hive_mind_os/experiment_runner.py` | `_artifact_reference(path: Path, digest: str) -> str` / `_validate_artifact_reference(reference: str) -> str \| None` | module-private | `path#sha256:<digest>` artifact-reference format; validation returns an issue string or None. Re-implement locally; do not import privates. |
| `src/hive_mind_os/experiment_runner.py` | `ExperimentRunner._write_new_json` | `@staticmethod def _write_new_json(path: Path, document: dict[str, Any]) -> None` — opens with mode `"x"` | Append-only evidence write precedent. |
| `src/hive_mind_os/benchmark_harness.py` (read scope) | `bootstrap_interval` | `def bootstrap_interval(outcomes: Sequence[bool | int], *, seed: int, samples: int = 2000) -> tuple[float, float, float]` | Comparator statistics precedent (rate, ci-lo, ci-hi). |
| `src/hive_mind_os/benchmark_harness.py` | `MeasurementVerdict.__post_init__` | raises if `self.judge_id in self.lane_identities` | Independence-of-judge precedent (AC1 analogue). |
| `src/hive_mind_os/recursive_improvement.py` (reference only — do NOT read/import) | `RecursiveImprovementGate.evaluate` | `def evaluate(self, evidence: ExperimentEvidence, *, consecutive_non_improvements: int = 0, experiments_completed: int = 0) -> ExperimentDecision` | Verdict-ladder precedent: quarantine on identity overlap / missing artifacts / holdout access; noise floor `max(pstdev(baseline), pstdev(candidate))`; required effect `max(minimum_effect, noise_multiplier * noise_floor)`. |
| `src/hive_mind_os/recursive_improvement.py` (reference only) | `ExperimentVerdict` | `StrEnum`: `KEEP/RETEST/DISCARD/QUARANTINE/STOP` | Verdict vocabulary to mirror locally. |
| `src/hive_mind_os/brain_kernel/canonical.py` (kernel sibling, import allowed) | `canonical_digest` | `def canonical_digest(value: Any) -> str` → `"sha256:<hex>"` | The only permitted digest helper for kernel contracts. |
| `src/hive_mind_os/brain_kernel/canonical.py` | `canonical_bytes` | `def canonical_bytes(value: Any) -> bytes` | Deterministic JSON bytes for retained records. |
| `src/hive_mind_os/brain_kernel/optimizer.py` (kernel sibling, do not modify) | `ChallengerProposal` | immutable tuple subclass with properties `challenger_id, parent_champion_id, change_ref, author_id, lesson, proposal_digest` | The upstream proposal shape the descriptor in §3 mirrors field-for-field. |

Kernel style rules observed in `curator_runtime.py` / `local_assurance.py` /
`optimizer.py`: stdlib-only, relative imports of kernel siblings only
(`from .canonical import canonical_digest`), frozen dataclasses or immutable
tuples, dedicated error types, fail-closed validation in `__post_init__`.
`evaluation_runtime.py` MUST follow the same style and must NOT import
`hive_mind_os.experiment_runner`, `hive_mind_os.pit_oracle`,
`hive_mind_os.recursive_improvement`, or `hive_mind_os.benchmark_harness`
(they pull ledger/sandbox/subprocess machinery into the kernel). CHALLENGER-510's
`challengers.py` may or may not exist at execution time — do not import it;
couple only through the plain descriptor below.

## 3. Design — `src/hive_mind_os/brain_kernel/evaluation_runtime.py`

Single new module, no I/O except append-only evidence retention. All names below
are NEW and owned by this node.

```python
"""Independent challenger evaluation across held-out, PIT, adversarial, and
comparator surfaces, with sealed holdouts and append-only losing evidence."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any, Mapping, Sequence

from .canonical import canonical_bytes, canonical_digest


class EvaluationError(ValueError):
    """An evaluation input violates the independent-evaluation contract."""


class HoldoutViolation(RuntimeError):
    """Holdout content was requested before an intact prediction seal."""


class SurfaceKind(StrEnum):
    HELD_OUT = "held-out"
    PIT = "pit"
    ADVERSARIAL = "adversarial"
    COMPARATOR = "comparator"


class EvaluationVerdict(StrEnum):
    KEEP = "keep"
    RETEST = "retest"
    DISCARD = "discard"
    QUARANTINE = "quarantine"
```

**Identities (AC1).**

```python
@dataclass(frozen=True, slots=True)
class EvaluationIdentities:
    proposer_id: str
    builder_id: str
    evaluator_id: str
    def __post_init__(self) -> None: ...
```
`__post_init__` raises `EvaluationError` when any identity is empty/untrimmed,
when `proposer_id == builder_id`, or when
`evaluator_id in {proposer_id, builder_id}` (mirrors
`RecursiveImprovementGate` quarantine reasons and
`MeasurementVerdict.__post_init__` independence). Construction failure is the
fail-closed path; `evaluate()` additionally re-checks and quarantines if given
a raw mapping (defense in depth is NOT needed — only accept the dataclass).

**Challenger descriptor.** Plain mirror of `optimizer.ChallengerProposal`
fields, so CHALLENGER-510 output maps 1:1 without an import:

```python
@dataclass(frozen=True, slots=True)
class ChallengerDescriptor:
    challenger_id: str
    parent_champion_id: str
    change_ref: str
    proposal_digest: str
```
`__post_init__`: all fields nonempty trimmed strings;
`challenger_id != parent_champion_id` else `EvaluationError`.

**Sealed holdout (AC2, semantic lock `holdout-boundary`).**

```python
@dataclass(frozen=True, slots=True)
class HoldoutSeal:
    holdout_id: str
    evaluator_id: str
    prediction_digest: str   # canonical_digest of prediction content
    sequence: int            # monotonic order stamp issued by SealedHoldout


class SealedHoldout:
    def __init__(self, holdout_id: str, cases: Mapping[str, Any]) -> None: ...
    @property
    def case_ids(self) -> tuple[str, ...]: ...          # ids only, never payloads
    @property
    def violations(self) -> tuple[str, ...]: ...
    @property
    def ordering(self) -> dict[str, Any]: ...           # {"seal_sequence", "reveal_sequence", "valid"}
    def seal_prediction(self, evaluator_id: str,
                        prediction_content: Mapping[str, Any]) -> HoldoutSeal: ...
    def reveal(self, seal: HoldoutSeal) -> dict[str, Any]: ...
```
Behavior (mirrors `PointInTimeOracle.seal_prediction` → `reveal` ordering):
an internal counter stamps every state change. `seal_prediction` is one-shot
(second call → `HoldoutViolation` "holdout already sealed"). `reveal` raises
`HoldoutViolation` and appends `"reveal_without_seal"` to `violations` when no
seal exists; raises and appends `"prediction_digest_mismatch"` when the passed
seal's `holdout_id`/`prediction_digest` does not match the recorded one
(recompute via `canonical_digest`). Any attempt to read a case payload before
reveal — there is deliberately NO accessor other than `reveal` — is therefore
impossible by construction; `ordering["valid"]` is True iff exactly one seal
exists, reveal (if any) came after it, and `violations` is empty.

**Surface results and artifacts (AC3/AC4).**

```python
@dataclass(frozen=True, slots=True)
class SurfaceResult:
    kind: SurfaceKind
    name: str
    baseline_samples: tuple[float, ...]
    candidate_samples: tuple[float, ...]
    artifact_refs: tuple[str, ...]       # "path#sha256:<digest>" per experiment_runner
```
`__post_init__`: nonempty name, at least one sample per side, all finite.

Module-private `_artifact_issue(reference: str) -> str | None` re-implements
`experiment_runner._validate_artifact_reference` exactly: reference must split
on the last `#` into a path and a `sha256:`-prefixed digest; path must resolve
to an existing file; file bytes must hash to the digest (`hashlib.sha256`
via `canonical` is NOT right here — hash raw bytes:
`f"sha256:{sha256(path.read_bytes()).hexdigest()}"`). Return an issue string
or `None`.

**Contract and guardrails.**

```python
@dataclass(frozen=True, slots=True)
class GuardrailSpec:
    surface: SurfaceKind
    maximum_regression: float = 0.0      # >= 0

@dataclass(frozen=True, slots=True)
class EvaluationContract:
    minimum_repetitions: int = 3         # >= 2 enforced
    noise_multiplier: float = 2.0        # >= 0
    minimum_effect: float = 0.0          # >= 0
    guardrails: tuple[GuardrailSpec, ...] = (
        GuardrailSpec(SurfaceKind.ADVERSARIAL),
        GuardrailSpec(SurfaceKind.COMPARATOR),
    )
    @property
    def fingerprint(self) -> str:        # canonical_digest of the field dict
```

**Runtime and record.**

```python
@dataclass(frozen=True, slots=True)
class EvaluationRecord:
    evaluation_id: str
    verdict: EvaluationVerdict
    reasons: tuple[str, ...]
    primary_effect: float | None
    required_effect: float | None
    noise_floor: float | None
    record_path: Path
    record_digest: str


class EvaluationRuntime:
    def __init__(self, contract: EvaluationContract | None = None) -> None: ...
    def evaluate(self, descriptor: ChallengerDescriptor,
                 identities: EvaluationIdentities,
                 surfaces: Sequence[SurfaceResult],
                 holdout: SealedHoldout,
                 *, evidence_root: str | Path) -> EvaluationRecord: ...
```

`evaluate` control flow (ordered; first quarantine set wins, and a record is
retained for EVERY verdict — losing evidence included, AC3):

1. Collect `quarantine_reasons`:
   - `holdout.ordering["valid"] is False` or `holdout.violations` →
     `"holdout boundary violated: <violation kinds>"` (AC2).
   - Any surface whose `artifact_refs` is empty →
     `"surface has no retained artifacts: <name>"`.
   - Any `_artifact_issue` on any reference →
     `"missing or mutated artifact: <issue>"` (AC4 — quarantine, never
     retest, when evidence is absent).
   - Duplicate `(kind, name)` surfaces → `"duplicate surface: <name>"`.
2. If `quarantine_reasons`: verdict `QUARANTINE`; skip statistics entirely
   (no optimistic retest), go to retention (step 6).
3. Missing surface kinds (all four of `SurfaceKind` required) → verdict
   `RETEST` with reason `"missing surfaces: ..."`. Insufficient repetitions on
   any surface (`min(len(baseline), len(candidate)) < minimum_repetitions`)
   → `RETEST`, reason `"insufficient repeated measurements: <names>"` (AC3;
   distinct from artifact loss, which already quarantined in step 2).
4. Guardrails: for each `GuardrailSpec`, on the matching surface compute
   `effect = fmean(candidate) - fmean(baseline)`; `regression = max(0.0, -effect)`;
   if `regression > maximum_regression` → verdict `DISCARD`, reason
   `"hard guardrail regressed: <surface>"` (AC3; retained as losing evidence).
5. Primary decision on the HELD_OUT surface:
   `primary_effect = fmean(candidate) - fmean(baseline)`;
   `noise_floor = max(pstdev(baseline_samples), pstdev(candidate_samples))`;
   `required_effect = max(minimum_effect, noise_multiplier * noise_floor)`
   (exactly the `RecursiveImprovementGate` formula).
   `effect > required` → `KEEP`; `effect < -required` → `DISCARD`
   ("materially underperformed"); otherwise `RETEST`
   ("did not exceed the measured noise floor").
6. Retention (always): build the record document —
   `{"schema_version": 1, "evaluation_id", "descriptor": {...}, "identities":
   {...}, "contract_fingerprint", "verdict", "reasons", "primary_effect",
   "required_effect", "noise_floor", "holdout": {"holdout_id", "ordering",
   "violations", "prediction_digest_or_null"}, "surfaces": [{kind, name,
   baseline_samples, candidate_samples, artifact_refs}, ...]}` —
   with `evaluation_id = "EVAL-" + canonical_digest(<doc sans id>)[7:23]`
   (deterministic, no uuid/clock). Write
   `<evidence_root>/<evaluation_id>.json` append-only: `path.open("x")` after
   `mkdir(parents=True, exist_ok=True)` on the root; on `FileExistsError`
   verify existing bytes equal the new canonical bytes, else raise
   `EvaluationError("retained evaluation record was mutated")` (mirrors
   `_retain_prompt_artifact`). Bytes are `canonical_bytes(document) + b"\n"`.
   `record_digest = canonical_digest(document)`.

No other public names. `__all__` lists the twelve public symbols above.

## 4. Implementation order (small commits on `autopilot/eval-520`)

1. `feat(kernel): add evaluation contracts and sealed holdout` — module with
   errors, enums, `EvaluationIdentities`, `ChallengerDescriptor`,
   `HoldoutSeal`, `SealedHoldout`, `GuardrailSpec`, `EvaluationContract`.
2. `feat(kernel): add independent evaluation runtime` — `_artifact_issue`,
   `SurfaceResult`, `EvaluationRuntime.evaluate`, `EvaluationRecord`,
   append-only retention.
3. `test(kernel): cover evaluation surfaces and quarantine paths` —
   `tests/test_hive_cortex_evaluation.py` (all classes in §5).
4. `docs(evidence): retain demonstration evaluation receipts` — run the two
   demonstration evaluations (one KEEP, one QUARANTINE with a deliberately
   missing artifact) against `evidence_root=evidence/experiments/hive-cortex`
   via a throwaway snippet (do not commit the snippet); commit the two JSON
   records plus `evidence/experiments/hive-cortex/README.md` describing them.
5. Node receipt + draft PR per the rendered prompt's completion protocol.

## 5. Test plan — `tests/test_hive_cortex_evaluation.py`

File conventions: `from __future__ import annotations`, stdlib `unittest`,
`tempfile.TemporaryDirectory` per test class, `unittest.main()` guard —
match `tests/test_hive_cortex_curator.py`. Helper `_make_artifact(root)` writes
a small file and returns a valid `path#sha256:<hex>` reference; helper
`_surfaces(...)` builds all four kinds with valid artifacts.

Focused commands (the ONLY test commands this node runs):

```
python -m unittest tests.test_hive_cortex_evaluation -v
```

| required_tests name | Test class | Key methods |
|---|---|---|
| `held-out-evaluation-tests` | `HeldOutEvaluationTests` | `test_keep_when_effect_beats_noise_floor`; `test_discard_when_candidate_materially_underperforms`; `test_retest_when_a_surface_kind_is_missing`; `test_evaluator_must_differ_from_proposer_and_builder` (constructing `EvaluationIdentities` with overlapping ids raises `EvaluationError`); `test_record_is_retained_append_only` (same doc re-written OK, mutated doc raises). |
| `pit-leakage-tests` | `PITLeakageTests` | `test_reveal_before_seal_raises_and_quarantines` (call `reveal` unsealed → `HoldoutViolation`; then `evaluate` → `QUARANTINE`, reason mentions holdout boundary); `test_foreign_seal_digest_is_rejected` (seal from a different `SealedHoldout` → `HoldoutViolation`, violations recorded); `test_second_seal_is_refused`; `test_case_payloads_are_invisible_until_reveal` (`case_ids` exposes ids only; payloads reachable solely via a valid `reveal`). |
| `noise-floor-tests` | `NoiseFloorTests` | `test_retest_when_improvement_is_within_noise` (high-variance samples, small mean gain → `RETEST`, `required_effect == noise_multiplier * pstdev` branch); `test_minimum_effect_dominates_when_noise_is_zero`; `test_hard_guardrail_regression_discards_and_retains_losing_evidence` (adversarial surface regresses → `DISCARD`, record file exists with full samples and reasons); `test_insufficient_repetitions_retest`. |
| `missing-artifact-quarantine-tests` | `MissingArtifactQuarantineTests` | `test_missing_artifact_file_quarantines_not_retests` (reference to a deleted file → verdict is `QUARANTINE` and NOT `RETEST`); `test_digest_mismatch_quarantines` (mutate the artifact file after building the reference); `test_empty_artifact_refs_quarantine`; `test_quarantine_record_is_still_retained`. |

Edge cases folded into the above: duplicate surface names; non-finite samples
rejected by `SurfaceResult`; `ChallengerDescriptor` equal to its champion
rejected; deterministic `evaluation_id` (same inputs → same id → append-only
re-write accepted).

## 6. Acceptance self-check → completion-receipt evidence

| Criterion | Demonstrated by | Receipt evidence |
|---|---|---|
| AC1 evaluator independent | `EvaluationIdentities.__post_init__` raises on overlap; `test_evaluator_must_differ_from_proposer_and_builder` | test entry `held-out-evaluation-tests` passed, command + file ref |
| AC2 holdout hidden until seal | `SealedHoldout` has no payload accessor besides `reveal`, which requires the intact one-shot seal; `PITLeakageTests` | test entry `pit-leakage-tests` passed |
| AC3 repetitions/noise/guardrails/losing evidence | contract `minimum_repetitions>=2`; pstdev noise floor; guardrail `DISCARD`; record retained on every verdict; `NoiseFloorTests` | test entry `noise-floor-tests` passed; retained KEEP + QUARANTINE records under `evidence/experiments/hive-cortex/` listed in changed paths |
| AC4 missing artifacts quarantine | step-2-before-step-3 ordering in `evaluate` (artifact issues checked before any retest branch); `MissingArtifactQuarantineTests` | test entry `missing-artifact-quarantine-tests` passed |
| Evidence requirements | base/final commit+tree ids, changed-path inventory limited to the three write-scope paths, command receipts, role identities (curator/optimizer/steward), rollback ref `git-revert:<final>` | HIVE-MIND-AUTOPILOT-COMPLETION-V1 payload per rendered prompt |

## 7. Out-of-scope traps — do NOT

- Do not modify `experiment_runner.py`, `pit_oracle.py`, `benchmark_harness.py`,
  `recursive_improvement.py`, `optimizer.py`, `challengers.py`, or ANY existing
  file: read scope is read-only, and only the three write-scope paths change.
- Do not import `hive_mind_os.experiment_runner` / `pit_oracle` /
  `benchmark_harness` / `recursive_improvement` / `brain_kernel.challengers`
  into `evaluation_runtime.py` — kernel modules import kernel siblings only
  (`.canonical` here). Their APIs are precedent, not dependencies.
- Do not edit any `__init__.py`, `conftest.py`, or `pyproject.toml`; do not
  add package re-exports; import the module by full path in tests.
- Do not touch `.autopilot/**`, `evidence/courts/**`, `.github/**`, or
  `docs/architecture/HARDENED_VISION_CONTRACT.md`; do not write evidence
  anywhere except `evidence/experiments/hive-cortex/**`.
- Do not run `python -m unittest discover`, pytest, or any other test target;
  only `python -m unittest tests.test_hive_cortex_evaluation -v`.
- Do not add promotion logic: `KEEP` is a recommendation for a later court
  (PROMOTE-530), never a champion mutation. Do not let a missing-artifact case
  fall through to `RETEST`, and do not add clock- or uuid-based ids (records
  must be deterministic and append-only).
- Do not delete or rewrite anything already under `evidence/`; retention is
  append-only, including your own demonstration records once committed.
- Do not rebase/squash/amend the node branch, and never push to
  `release/hive-mind-os-singleton-20260812-r5` or `main`.
