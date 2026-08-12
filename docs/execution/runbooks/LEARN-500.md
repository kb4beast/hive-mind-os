# LEARN-500 — Scoped evidence-bound lesson generation (learning_runtime)

Read this runbook plus your rendered prompt only. Do not re-read
`.autopilot/plan.json`, `.autopilot/README.md`, or policy files. The wave
protocol is `docs/execution/runbooks/README.md`; you are a worker, not the
integrator.

## 1. Contract summary

**Objective.** Generate scoped, evidence-bound lessons from outcomes,
incidents, remands, repairs, and human corrections — without turning anecdotes
or raw transcripts into policy.

**Acceptance criteria (compressed).**
1. Every lesson binds: source episode(s), outcome, error class, applicability,
   confidence, provenance, and expiry.
2. Counterexamples and dissent are retained (append-only, never deleted).
3. NO lesson mutates policy, prompt, or champion directly — lessons are
   advisory data records only.

**Scope table.**

| Kind | Paths |
|---|---|
| write_scope (ONLY these) | `src/hive_mind_os/brain_kernel/learning_runtime.py`, `tests/test_hive_cortex_learning.py`, `docs/execution/LEARNING_RUNTIME.md` |
| read_scope | `src/hive_mind_os/learning.py`, `src/hive_mind_os/repository_learning.py`, `src/hive_mind_os/pit_oracle.py` (plus kernel contracts named below, read-only) |
| forbidden_scope | `.github/CODEOWNERS`, `.github/governance/**`, `evidence/courts/**`, `docs/architecture/HARDENED_VISION_CONTRACT.md` |

Additionally forbidden (hard rules): any `__init__.py`, any `conftest.py`,
`pyproject.toml`, `.autopilot/**`, and every file owned by a sibling node.
Round **R2** siblings running in parallel: `DURABLE-410`, `DELIVERY-420`,
`HUMANLESS-430`, `CHEAT-440`. Never touch their files; never wait or poll for
them — if you discover a real dependency on a sibling, run `autopilot fail`
with a blocker.

**Semantic lock:** `learning-runtime`. **Branch:** `autopilot/learn-500`,
PR target `main` (draft PR only; do not merge). Never touch the release
branch; never rebase/squash/amend the node branch; never run repo-wide test
discovery (`python -m unittest discover` is the integrator's job).

New module is imported by full path
`hive_mind_os.brain_kernel.learning_runtime`. Do NOT add re-exports to any
`__init__.py`.

## 2. Existing-code map (real symbols; do not invent others)

| Path | Symbol | Real signature | Role |
|---|---|---|---|
| `src/hive_mind_os/brain_kernel/canonical.py` | `canonical_digest` | `canonical_digest(value: Any) -> str` | returns `sha256:<64hex>` over canonical JSON; use for lesson digests and ids |
| `src/hive_mind_os/brain_kernel/canonical.py` | `canonical_document` | `canonical_document(value: Any) -> dict[str, Any]` | dataclass → JSON object |
| `src/hive_mind_os/brain_kernel/contracts.py` | `MemoryRecord` | frozen dataclass: `record_id, memory_class, scope, subject_keys, content_ref, source_refs, authority_level, sensitivity, valid_from, valid_to, recorded_at, available_at, state, supersedes, superseded_by, evaluator_id, outcome_refs, retention_policy, digest_value` | the durable form a lesson maps into; `record_id` must match `MEMORY-[A-Za-z0-9][A-Za-z0-9._-]*`; `scope` in `{"global","repository","mission","role","work_item"}`; times RFC 3339 with offset |
| `src/hive_mind_os/brain_kernel/contracts.py` | `MemoryState` | StrEnum `ACTIVE/SUPERSEDED/CONTRADICTED/RETRACTED/EXPIRED/QUARANTINED` | lesson records start `ACTIVE` |
| `src/hive_mind_os/brain_kernel/memory.py` | `MemoryClass` | StrEnum incl. `LESSON = "lesson"`, `EPISODE = "episode"` | memory_class values |
| `src/hive_mind_os/brain_kernel/memory.py` | `MemoryDenied` | `class MemoryDenied(ValueError)` | pattern for this node's own `LearningDenied` |
| `src/hive_mind_os/brain_kernel/memory.py` | `MemoryArtifactStore.put` | `put(self, body: str, *, content_kind: str = "evidence") -> MemoryArtifact` | stores lesson body; rejects transcripts/secrets; returns `MemoryArtifact(digest, token_count)` |
| `src/hive_mind_os/brain_kernel/memory.py` | `MemoryAccess` | frozen dataclass `roles: tuple[str, ...], data_scopes: tuple[str, ...], evaluator_visible: bool = True` | access labels for the lesson record |
| `src/hive_mind_os/brain_kernel/memory.py` | `MemoryCatalog.consolidate` | `consolidate(self, lesson: MemoryRecord, access: MemoryAccess, *, supporting_record_ids: Iterable[str], independence_keys: Mapping[str, str], now: str, reason: str, policy: ConsolidationPolicy = ConsolidationPolicy()) -> tuple[MemoryLifecycleEvent, ...]` | existing gate: lesson must have `memory_class == "lesson"`, `evaluator_id`, `outcome_refs`, `supersedes == sorted supporting episode ids`; episodes must be ACTIVE class `"episode"` with source_refs and outcome_refs |
| `src/hive_mind_os/brain_kernel/memory.py` | `ConsolidationPolicy` | frozen dataclass `minimum_independent_episodes: int = 2, minimum_distinct_contexts: int = 2` (both must be ints ≥ 2) | evidence burden; reuse, do not redefine |
| `src/hive_mind_os/learning.py` | `LearningPromotionGate.evaluate` | `evaluate(self, candidate: EvaluationSummary, champion: EvaluationSummary) -> PromotionDecision` | existing champion gate — lessons must NOT call this or bypass it; cite in docs as the *separate* promotion path |
| `src/hive_mind_os/repository_learning.py` | `PatternLesson` | frozen dataclass `source_repository, source_commit_sha, source_uri, license_spdx, pattern, evidence_refs: tuple[str, ...]` | prior art: provenance-bearing lesson shape; this node generalizes to internal episodes |
| `src/hive_mind_os/repository_learning.py` | `RepositoryLearningEpisode.validate_access` | `validate_access(self, accessed_shas: Iterable[str]) -> LeakageDecision` | leakage-guard precedent; mirror the "no future evidence" check for `observed_at` |

Digest strings everywhere are `sha256:<64 lowercase hex>` (regex in
`contracts.py: _DIGEST`). Times are RFC 3339 with mandatory offset
(`contracts.py: _time`).

## 3. Design — `src/hive_mind_os/brain_kernel/learning_runtime.py`

One new module, pure and deterministic: no I/O, no network, no model calls.
Import only from stdlib, `.canonical`, `.contracts`, and `.memory`.

```python
"""Scoped, evidence-bound lesson generation from governed learning signals."""
from __future__ import annotations
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Iterable, Mapping

from .canonical import canonical_digest
from .contracts import MemoryRecord, MemoryState
from .memory import ConsolidationPolicy
```

### 3.1 Error type

```python
class LearningDenied(ValueError):
    """A lesson operation violates the evidence-bound learning contract."""
```

### 3.2 Signal vocabulary

```python
class SignalKind(StrEnum):
    OUTCOME = "outcome"
    INCIDENT = "incident"
    REMAND = "remand"
    REPAIR = "repair"
    HUMAN_CORRECTION = "human_correction"

class OutcomeClass(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
```

### 3.3 Input record

```python
@dataclass(frozen=True, slots=True)
class LearningSignal:
    signal_id: str                 # non-empty, unique per batch
    kind: SignalKind
    episode_record_id: str         # must match MEMORY-... (reuse regex below)
    outcome: OutcomeClass
    error_class: str               # non-empty machine token, e.g. "scope-violation"
    context_key: str               # independence key (mission/repo/work context)
    evidence_refs: tuple[str, ...] # each sha256:<64hex>; at least one required
    observed_at: str               # RFC 3339 with offset
```

`__post_init__` validation: non-empty `signal_id`/`error_class`/`context_key`;
`episode_record_id` matches `re.compile(r"MEMORY-[A-Za-z0-9][A-Za-z0-9._-]*\Z")`
(same pattern as `contracts.py` `_IDS["memory"]` — copy the literal, do NOT
import the private `_IDS`); `evidence_refs` non-empty and each matches
`re.compile(r"sha256:[0-9a-f]{64}\Z")`; `observed_at` parses via
`datetime.fromisoformat(value.replace("Z", "+00:00"))` and has tzinfo, raising
`LearningDenied` otherwise. Reject transcript-like evidence up front: a
`raw_excerpt`-style free-text field is deliberately absent — signals carry
digests only.

### 3.4 Lesson structure

```python
@dataclass(frozen=True, slots=True)
class LessonApplicability:
    scope: str                     # one of MemoryRecord's scopes
    subject_keys: tuple[str, ...]  # required unless scope == "global"

@dataclass(frozen=True, slots=True)
class LessonProvenance:
    generator: str                 # e.g. "learning_runtime"
    evaluator_id: str              # non-empty; distinct from generator
    signal_ids: tuple[str, ...]    # sorted, unique, non-empty
    roles: tuple[str, ...]         # contributing roles, may be empty

@dataclass(frozen=True, slots=True)
class Counterexample:
    signal_id: str
    episode_record_id: str
    evidence_refs: tuple[str, ...]
    observed_at: str
    note: str

@dataclass(frozen=True, slots=True)
class DissentRecord:
    role: str
    position: str                  # non-empty
    recorded_at: str               # RFC 3339 with offset

@dataclass(frozen=True, slots=True)
class Lesson:
    lesson_id: str                       # "LESSON-" + digest hex prefix (20 chars)
    statement: str                       # abstract guidance text, non-empty
    error_class: str
    outcome: OutcomeClass                # dominant outcome the lesson explains
    episode_record_ids: tuple[str, ...]  # sorted, unique, >= 1
    applicability: LessonApplicability
    confidence: float                    # in [0.0, 1.0]
    provenance: LessonProvenance
    valid_from: str
    valid_to: str                        # expiry is MANDATORY (never None)
    counterexamples: tuple[Counterexample, ...] = ()
    dissent: tuple[DissentRecord, ...] = ()

    @property
    def digest(self) -> str: ...         # canonical_digest over all fields
```

Invariants enforced in `__post_init__` (raise `LearningDenied`):
`valid_to` strictly after `valid_from`; confidence bounded; episode ids sorted
and unique; statement non-empty and free of secret-like tokens (reuse the
regex idea from `memory.py: _SECRET`, copied locally). The `Lesson` class has
**no** method named or shaped like `apply`, `enforce`, `mutate`, `promote`,
`update_policy`, `update_prompt`, or `set_champion` — advisory-only by
construction (acceptance criterion 3).

### 3.5 Generator

```python
class LessonGenerator:
    def __init__(self, *, policy: ConsolidationPolicy = ConsolidationPolicy(),
                 default_ttl_days: int = 90) -> None: ...

    def attribute(self, signals: Iterable[LearningSignal], *, now: str
                  ) -> Mapping[str, tuple[LearningSignal, ...]]:
        """Group validated signals by error_class; reject future-dated or
        duplicate signal_ids (LearningDenied). Point-in-time guard: every
        signal.observed_at must be <= now."""

    def generate(self, signals: Iterable[LearningSignal], *, statement: str,
                 error_class: str, applicability: LessonApplicability,
                 evaluator_id: str, now: str, roles: tuple[str, ...] = (),
                 ttl_days: int | None = None) -> Lesson:
        """Build one Lesson from the signals matching error_class."""
```

`generate` control flow:
1. Run `attribute(signals, now=now)`; select the `error_class` bucket; raise
   `LearningDenied` if absent.
2. Evidence burden (mirrors `ConsolidationPolicy` semantics): distinct
   `episode_record_id` count `>= policy.minimum_independent_episodes` AND
   distinct `context_key` count `>= policy.minimum_distinct_contexts`,
   else `LearningDenied("lesson lacks independent evidence")`.
3. Dominant outcome = the `OutcomeClass` of the majority of supporting
   signals; ties → `LearningDenied` (no coin flips).
4. Confidence, deterministic and bounded:
   `supporting = signals with dominant outcome`, `contrary = the rest`;
   `confidence = round(len(supporting) / (len(supporting) + len(contrary) + 1), 6)`
   (the `+1` Laplace term keeps a single anecdote below certainty). Signals
   with contrary outcomes are recorded as `Counterexample`s at birth, not
   discarded.
5. `valid_from = now`; `valid_to = now + timedelta(days=ttl_days or default_ttl_days)`
   rendered back to RFC 3339 `...Z` form.
6. `lesson_id = "LESSON-" + canonical_digest({...deterministic core fields...})
   .removeprefix("sha256:")[:20]` (same construction pattern as
   `memory.py: MemoryCatalog.record_conflict`'s `CONFLICT-` ids).
7. Return the frozen `Lesson`. The generator never touches
   `LearningPromotionGate`, `PolicyEngine`, prompts, or champion state.

### 3.6 Append-only retention operations (module functions)

```python
def retain_counterexample(lesson: Lesson, counterexample: Counterexample) -> Lesson:
    """Return a NEW Lesson with the counterexample appended and confidence
    recomputed downward: confidence' = round(confidence *
    (supporting_n) / (supporting_n + total_counterexamples + 1), 6) using
    supporting_n = len(lesson.episode_record_ids). Duplicate signal_id ->
    LearningDenied. Existing counterexamples are never removed."""

def record_dissent(lesson: Lesson, dissent: DissentRecord) -> Lesson:
    """Return a NEW Lesson with dissent appended; nothing else changes.
    Duplicate (role, position) pairs -> LearningDenied."""
```

Both use `dataclasses.replace` so the original object is untouched (frozen
dataclasses guarantee it).

### 3.7 Memory binding (advisory export, not mutation)

```python
def lesson_memory_record(lesson: Lesson, *, content_ref: str,
                         recorded_at: str, retention_policy: str = "governed-lesson"
                         ) -> MemoryRecord:
```

Builds a `MemoryRecord` with: `record_id = "MEMORY-" + lesson.lesson_id`
(satisfies the `MEMORY-` regex), `memory_class="lesson"`,
`scope=lesson.applicability.scope`, `subject_keys=lesson.applicability.subject_keys`,
`content_ref=content_ref` (caller stores the lesson body via
`MemoryArtifactStore.put` and passes the digest), `source_refs=` all evidence
digests from provenance signals is not available here — instead pass
`source_refs=lesson.episode_record_ids`, `authority_level="internal"`,
`sensitivity="internal"`, `valid_from/valid_to` from the lesson,
`recorded_at=available_at=recorded_at`, `state=MemoryState.ACTIVE`,
`supersedes=lesson.episode_record_ids` (so the record is *eligible* for the
existing `MemoryCatalog.consolidate` gate — the gate itself stays the sole
promotion path), `superseded_by=()`, `evaluator_id=lesson.provenance.evaluator_id`,
`outcome_refs=(lesson.digest,)`, `digest_value=lesson.digest`. This function
only *constructs* a record; it never registers it, never calls `consolidate`,
and never touches policy/prompt/champion.

## 4. Implementation order (small commits on `autopilot/learn-500`)

1. `learning_runtime.py`: `LearningDenied`, `SignalKind`, `OutcomeClass`,
   `LearningSignal` with full validation.
2. `Lesson` + `LessonApplicability` + `LessonProvenance` + `Counterexample`
   + `DissentRecord` + digest property + invariants.
3. `LessonGenerator.attribute` and `.generate` (evidence burden, dominant
   outcome, confidence, expiry, deterministic id).
4. `retain_counterexample`, `record_dissent`, `lesson_memory_record`.
5. `tests/test_hive_cortex_learning.py` (section 5), run focused tests green.
6. `docs/execution/LEARNING_RUNTIME.md`: ~1 page — signal vocabulary, lesson
   invariants, confidence formula, expiry default, the explicit statement
   that promotion remains with `MemoryCatalog.consolidate` +
   `LearningPromotionGate`, and that lessons are advisory records.
7. Push branch, open draft PR to `main`, produce node completion receipt per
   your rendered prompt. STOP (stopping condition: draft PR + receipt; no
   merge, no downstream work).

## 5. Test plan — `tests/test_hive_cortex_learning.py`

Conventions: `unittest.TestCase`, module-level constants like
`DIGEST = "sha256:" + "0" * 64`, `TIME = "2026-08-07T12:00:00Z"` (see
`tests/test_brain_kernel_memory_context.py`). Import the module by full path:
`from hive_mind_os.brain_kernel.learning_runtime import (...)`.

Focused command (the ONLY test command this node runs):

```
python -m unittest tests.test_hive_cortex_learning -v
```

| required_tests name | Test class | Methods (minimum) |
|---|---|---|
| `lesson-generation-tests` | `LessonGenerationTests` | `test_lesson_binds_episode_outcome_error_class_applicability_confidence_provenance_expiry` (assert every field populated, `valid_to` not None and > `valid_from`); `test_generation_requires_independent_episodes_and_contexts` (1 episode or 1 context → `LearningDenied`); `test_lesson_id_and_digest_are_deterministic` (same inputs twice → identical `lesson_id`/`digest`); `test_lesson_has_no_policy_prompt_or_champion_mutation_surface` (assert no attribute of `Lesson`/`LessonGenerator` named in `{"apply","enforce","promote","mutate","update_policy","update_prompt","set_champion"}` and `import hive_mind_os.brain_kernel.learning_runtime as m; assert not any(x in src for x in ("PolicyEngine","prompt_registry","LearningPromotionGate"))` via `inspect.getsource(m)`); `test_secretlike_statement_rejected` |
| `outcome-attribution-tests` | `OutcomeAttributionTests` | `test_attribute_groups_signals_by_error_class`; `test_future_dated_signal_rejected` (`observed_at > now` → `LearningDenied`); `test_duplicate_signal_ids_rejected`; `test_tied_outcomes_rejected`; `test_contrary_outcome_signals_become_counterexamples_at_birth`; `test_signal_requires_evidence_refs_and_valid_episode_id` |
| `counterexample-retention-tests` | `CounterexampleRetentionTests` | `test_retain_counterexample_appends_and_lowers_confidence` (new object, original unchanged, confidence strictly decreases, count grows); `test_counterexamples_never_removed` (retain two, both present in order); `test_duplicate_counterexample_rejected`; `test_record_dissent_appends_and_preserves_lesson_fields`; `test_lesson_memory_record_maps_to_valid_memory_record` (constructed `MemoryRecord` passes its own `__post_init__`, `memory_class == "lesson"`, `supersedes == episode ids`, `valid_to` set) |

Edge cases to cover inside the above: `ttl_days=0`/negative → `LearningDenied`;
`applicability.scope` outside the MemoryRecord vocabulary → `LearningDenied`;
empty `signals` iterable → `LearningDenied`; confidence stays in `[0, 1]`
after many counterexamples.

Do NOT run `python -m unittest discover`, pytest, or any other test module.

## 6. Acceptance self-check → receipt evidence

| Criterion | Demonstrated by | Receipt evidence |
|---|---|---|
| Lesson binds episode, outcome, error class, applicability, confidence, provenance, expiry | `Lesson` dataclass has all seven as required fields; `valid_to` non-optional; `__post_init__` rejects gaps | `test_lesson_binds_...` pass line in the focused-test receipt; file inventory shows only the three write-scope paths |
| Counterexamples and dissent retained | `retain_counterexample`/`record_dissent` append-only on frozen dataclasses; birth counterexamples kept | `CounterexampleRetentionTests` pass lines |
| No lesson mutates policy/prompt/champion | module imports only stdlib + `.canonical`/`.contracts`/`.memory`; no mutation-shaped methods; source-inspection test | `test_lesson_has_no_policy_prompt_or_champion_mutation_surface` pass line; grep of the new module in the receipt notes |
| Evidence requirements | base + final commit SHAs, changed-path list ⊆ write_scope, exact `python -m unittest tests.test_hive_cortex_learning -v` output, role identities, rollback ref = revert of the node commit | attach to node completion receipt |

## 7. Out-of-scope traps (do NOT do these)

- Do NOT edit `src/hive_mind_os/learning.py`, `repository_learning.py`,
  `pit_oracle.py`, `brain_kernel/memory.py`, or `brain_kernel/contracts.py` —
  they are read-only references. If they contradict this design, escalate via
  `autopilot fail`; never "fix" them.
- Do NOT add exports to `src/hive_mind_os/__init__.py` or
  `src/hive_mind_os/brain_kernel/__init__.py`, and do not create/modify any
  `conftest.py` or `pyproject.toml`.
- Do NOT import `PolicyEngine`, `prompt_registry`, champion/promotion code, or
  call `MemoryCatalog.consolidate`/`register` from the new module — binding a
  lesson into durable memory is a *caller* decision behind existing gates.
- Do NOT store raw transcripts, free-text excerpts of model output, or
  secret-like strings in signals or lesson statements.
- Do NOT touch `.autopilot/**`, the release branch, sibling node files
  (`DURABLE-410`, `DELIVERY-420`, `HUMANLESS-430`, `CHEAT-440` scopes), or
  anything in forbidden_scope (`.github/CODEOWNERS`, `.github/governance/**`,
  `evidence/courts/**`, `docs/architecture/HARDENED_VISION_CONTRACT.md`).
- Do NOT run repo-wide test discovery, rebase/squash/amend the node branch,
  or merge the draft PR. Stop at draft PR + validated receipt.
- Do NOT redefine `ConsolidationPolicy`, `MemoryRecord`, or digest/time
  validation semantics — reuse the imported contracts; copy only the two small
  regex literals noted in section 3.3 (private underscore names must not be
  imported).
