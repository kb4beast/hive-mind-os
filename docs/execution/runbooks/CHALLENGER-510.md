# CHALLENGER-510 — Lesson-driven challenger generation (Round R3)

## 1. Contract summary

**Objective.** Generate immutable prompt, planner, policy-rule, retrieval, or
tool-selection challengers from accepted lessons (LEARN-500 output). Current
main can *evaluate* supplied prompt challengers (`experiment_runner.py`) but
cannot autonomously *generate* them.

**Acceptance criteria (compressed).**
1. Every challenger has a champion parent, hypothesis, changed scope, rollback,
   and provenance.
2. Live champions are immutable — generation never moves a champion pointer.
3. Forbidden self-modification classes are rejected.

**Scope table.**

| Kind | Paths |
|---|---|
| write_scope (ONLY these) | `src/hive_mind_os/brain_kernel/challengers.py`, `tests/test_hive_cortex_challengers.py` |
| read_scope | `src/hive_mind_os/prompt_registry.py`, `src/hive_mind_os/recursive_improvement.py`, `src/hive_mind_os/experiment_runner.py` |
| forbidden_scope | `.github/CODEOWNERS`, `.github/governance/**`, `evidence/courts/**`, `docs/architecture/HARDENED_VISION_CONTRACT.md` |

Additionally forbidden (hard rules): any `__init__.py`, `conftest.py`,
`pyproject.toml`, `.autopilot/**`, and any sibling node file (notably
`src/hive_mind_os/brain_kernel/selfheal*.py`, `poison*.py`,
`learning_runtime.py`, `tests/test_hive_cortex_learning.py`,
`tests/test_hive_cortex_selfheal*.py`, `tests/test_hive_cortex_poison*.py`).
The new module is imported by FULL module path
`hive_mind_os.brain_kernel.challengers` — do NOT add re-exports to any package
`__init__.py`.

**Semantic locks:** `challenger-generation`. **Round:** R3, siblings
`SELFHEAL-450` and `POISON-540` run in parallel; never wait for or read their
files. **Branch:** `autopilot/challenger-510`. Never touch the release branch;
never rebase/squash/amend the node branch; run only the focused tests below
(never `python -m unittest discover`). Dependency `LEARN-500`
(`src/hive_mind_os/brain_kernel/learning_runtime.py`) is merged before R3
dispatch, but its API is NOT part of this node's read scope — consume lessons
via the mapping adapter defined in section 3 and do not import
`learning_runtime`.

## 2. Existing-code map (real symbols, verified on branch)

| Path | Symbol | Real signature | Role here |
|---|---|---|---|
| `src/hive_mind_os/recursive_improvement.py` | `ExperimentCandidate` | `@dataclass(frozen=True, slots=True) ExperimentCandidate(id: str, parent_champion_id: str, hypothesis: str, changed_paths: tuple[str, ...], rollback_ref: str)` | Bridge target; its `__post_init__` already rejects `id == parent_champion_id` ("a challenger cannot mutate the live champion in place") and empty `changed_paths` |
| `src/hive_mind_os/recursive_improvement.py` | `RecursiveImprovementContract` | frozen dataclass; field `forbidden_behaviors: tuple[str, ...] = ("goal_mutation", "policy_mutation", "live_champion_mutation", "self_evaluation", "holdout_access", "metric_gaming", "evidence_concealment", "unbounded_resource_acquisition", "self_weight_modification")` | Canonical list of forbidden self-modification classes; reuse verbatim, do not redefine strings |
| `src/hive_mind_os/prompt_registry.py` | `PromptRegistry.__init__` | `(self, root: str | Path, *, ledger: EvidenceLedger | None = None)` | Content-addressed prompt store used for PROMPT-surface challengers |
| `src/hive_mind_os/prompt_registry.py` | `PromptRegistry.register` | `(self, role: Role | str, content: str | bytes, *, parent_digest: str | None, created_by: str, experiment_id: str | None = None) -> str` | Registers an immutable challenger artifact WITHOUT touching champions |
| `src/hive_mind_os/prompt_registry.py` | `PromptRegistry.champion_digest` | `(self, role: Role | str) -> str | None` | Read-only champion parent lookup |
| `src/hive_mind_os/prompt_registry.py` | `PromptRegistry.champion_prompt` | `(self, role: Role | str) -> tuple[str, str]` | Returns `(content, digest)` of the live champion |
| `src/hive_mind_os/prompt_registry.py` | `PromptRegistry.promote` | `(self, role, digest, *, promoted_by: str, experiment_id: str, expected_current: str | None, decision_event_sequence: int | None = None) -> str | None` | MUST NEVER be called by this node's code — promotion belongs to EVAL-520/PROMOTE-530 |
| `src/hive_mind_os/prompt_registry.py` | `prompt_digest` | `(content: str | bytes) -> str` (`sha256:<64hex>`) | Content digest for prompt challenger content |
| `src/hive_mind_os/prompt_registry.py` | `generation_zero_prompt` | `(contract: RoleContract) -> str` | Test fixture: exact P02 prompt content that `promote` accepts as generation-zero |
| `src/hive_mind_os/experiment_runner.py` | `ExperimentRunner.run` | `(self, role, challenger: str | bytes, *, surface: EvaluationSurface, repetitions: int, author_id="author:cli", builder_id="builder:prompt-registry", evaluator_id=SCRIPTED_EVALUATOR_ID, judge_id=SCRIPTED_JUDGE_ID, contract=None) -> ExperimentRun` | Downstream consumer of generated prompt challenger content (EVAL-520); this node only produces compatible `str` content + provenance, it does NOT call `run` |
| `src/hive_mind_os/models.py` | `Role` | `class Role(str, Enum)` with values `orchestrator, explorer, architect, builder, curator, optimizer, steward, integrator` | Role keys for prompt champions |
| `src/hive_mind_os/models.py` | `utc_now` | `() -> str` (UTC ISO-8601) | Timestamps in specs/records |
| `src/hive_mind_os/ledger.py` | `EvidenceLedger.__init__` / `append_event` | `(self, path: str | Path = ":memory:")`; `append_event(self, run_id: str, event_type: str, actor: str, payload: dict[str, Any]) -> int` | Test fixture ledger for `PromptRegistry` |
| `src/hive_mind_os/roles.py` | `ROLE_CONTRACTS` | `dict[Role, RoleContract]` | Test fixture: feeds `generation_zero_prompt` |
| `src/hive_mind_os/brain_kernel/canonical.py` | `canonical_digest` | `(value: Any) -> str` (`sha256:<64hex>` of canonical JSON) | Deterministic challenger identity digest |

Imports allowed in `challengers.py`: stdlib, `hive_mind_os.models`,
`hive_mind_os.recursive_improvement`, `hive_mind_os.prompt_registry`,
`hive_mind_os.brain_kernel.canonical`. Nothing else.

## 3. Design — `src/hive_mind_os/brain_kernel/challengers.py`

Module docstring: `"""Generate immutable challengers from accepted lessons
without touching live champions."""` Pure, side-effect-free generation; the
only optional side effect is content-addressed artifact registration through
`PromptRegistry.register` (which never moves a pointer).

### 3.1 Constants and errors

```python
FORBIDDEN_SELF_MODIFICATION_CLASSES: frozenset[str] = frozenset(
    RecursiveImprovementContract.forbidden_behaviors  # class-level default tuple
)
# NOTE: dataclass field defaults are reachable via
# RecursiveImprovementContract(primary=..., guardrails=()).forbidden_behaviors;
# simplest robust form: instantiate once at module import with a dummy
# MetricSpec("task_success_rate", MetricDirection.MAXIMIZE) and empty guardrails,
# or copy the literal 9-string tuple and assert equality against a constructed
# contract in tests (choose the constructed-contract form; never hand-drift).

_SURFACE_TAG_PREFIXES = {
    "prompt": ChallengerSurface.PROMPT,          # tag "prompt:<role>"
    "planner": ChallengerSurface.PLANNER,        # tag "planner:<component>"
    "policy-rule": ChallengerSurface.POLICY_RULE,# tag "policy-rule:<rule-id>"
    "retrieval": ChallengerSurface.RETRIEVAL,    # tag "retrieval:<index>"
    "tool-selection": ChallengerSurface.TOOL_SELECTION,  # "tool-selection:<tool>"
}

class ChallengerGenerationError(ValueError): ...   # malformed lesson/spec input
class ChampionMutationError(RuntimeError): ...     # any attempt to alter a champion
class ForbiddenChallengerClass(RuntimeError):
    def __init__(self, lesson_id: str, forbidden_class: str) -> None: ...
```

### 3.2 Enums and dataclasses (all `@dataclass(frozen=True, slots=True)`)

```python
class ChallengerSurface(StrEnum):
    PROMPT = "prompt"
    PLANNER = "planner"
    POLICY_RULE = "policy-rule"
    RETRIEVAL = "retrieval"
    TOOL_SELECTION = "tool-selection"

@dataclass(frozen=True, slots=True)
class AcceptedLesson:
    lesson_id: str
    source_episode_id: str
    outcome: str                    # e.g. "failure", "remand", "human-correction"
    error_class: str
    applicability: tuple[str, ...]  # surface tags, e.g. ("prompt:optimizer",)
    confidence: float               # (0.0, 1.0]
    provenance: tuple[str, ...]     # evidence refs; must be nonempty
    expires_at: str                 # ISO-8601
    status: str = "accepted"
    # __post_init__: all str fields nonempty; 0 < confidence <= 1;
    # applicability and provenance nonempty; status == "accepted" else
    # ChallengerGenerationError("only accepted lessons may seed challengers")

def lesson_from_document(document: Mapping[str, Any]) -> AcceptedLesson:
    """Adapter from a LEARN-500 lesson record; tolerant key mapping.
    Reads lesson_id|id, source_episode_id|episode_id, outcome, error_class,
    applicability, confidence, provenance|evidence_refs, expires_at|expiry,
    status. Raises ChallengerGenerationError on any missing/invalid field.
    This is the ONLY LEARN-500 coupling point."""

@dataclass(frozen=True, slots=True)
class ChallengerSpec:
    challenger_id: str          # "chal:" + canonical_digest of identity fields
    surface: ChallengerSurface
    champion_ref: str           # parent champion identity (prompt digest, or
                                # "champion:<surface>:<target>" for non-prompt)
    target: str                 # role name / component / rule-id / index / tool
    hypothesis: str
    changed_scope: tuple[str, ...]  # nonempty, e.g. ("prompt:optimizer",)
    rollback_ref: str           # == champion_ref (revert = keep champion)
    lesson_id: str
    provenance: tuple[str, ...] # lesson provenance + lesson_id ref; nonempty
    created_by: str
    created_at: str
    content: str                # proposed artifact content (prompt text or
                                # JSON-rendered rule/plan/config delta)
    content_digest: str         # prompt_digest(content)
    # __post_init__ validation (acceptance criterion 1):
    #  - challenger_id, champion_ref, hypothesis, rollback_ref, created_by,
    #    lesson_id, target, content all nonempty after .strip()
    #  - changed_scope and provenance nonempty tuples of nonempty strings
    #  - challenger_id != champion_ref and content_digest != champion_ref
    #    else ChampionMutationError("challenger may not alias the live champion")
    #  - content_digest == prompt_digest(content) else ChallengerGenerationError

    def to_experiment_candidate(self) -> ExperimentCandidate:
        return ExperimentCandidate(
            id=self.content_digest,
            parent_champion_id=self.champion_ref,
            hypothesis=self.hypothesis,
            changed_paths=self.changed_scope,
            rollback_ref=self.rollback_ref,
        )

@dataclass(frozen=True, slots=True)
class ChallengerRejection:
    lesson_id: str
    reason: str
    forbidden_class: str | None = None

@dataclass(frozen=True, slots=True)
class GenerationResult:
    challengers: tuple[ChallengerSpec, ...]
    rejections: tuple[ChallengerRejection, ...]
```

### 3.3 Forbidden-class classification (acceptance criterion 3)

`def classify_forbidden(lesson: AcceptedLesson) -> str | None` returns the
matching forbidden class or `None`. Rules (checked in order, first hit wins):
- any applicability tag whose prefix (text before first `:`) is NOT in
  `_SURFACE_TAG_PREFIXES` maps to a rejection: tags starting with
  `champion`, `goal`, `objective` → `"goal_mutation"` /
  `"live_champion_mutation"`; `policy` (bare, i.e. not `policy-rule`) →
  `"policy_mutation"`; `weights`, `model` → `"self_weight_modification"`;
  `holdout` → `"holdout_access"`; `evaluator`, `judge`, `metric` →
  `"self_evaluation"` / `"metric_gaming"`; `evidence`, `ledger` →
  `"evidence_concealment"`; `budget`, `resource` →
  `"unbounded_resource_acquisition"`; anything else unknown → generic
  rejection (reason `"unrecognized applicability tag"`, `forbidden_class=None`).
- `lesson.error_class` equal to any member of
  `FORBIDDEN_SELF_MODIFICATION_CLASSES` → that class (a lesson *about* e.g.
  `metric_gaming` must not seed a challenger that edits the metric itself).

### 3.4 Generator

```python
class ChallengerGenerator:
    def __init__(
        self,
        *,
        generated_by: str,
        registry: PromptRegistry | None = None,
    ) -> None:
        # generated_by nonempty else ChallengerGenerationError

    def generate(
        self,
        lessons: Sequence[AcceptedLesson | Mapping[str, Any]],
        *,
        champions: Mapping[str, str],
    ) -> GenerationResult: ...
```

`champions` maps `"<surface>:<target>"` → champion ref (for PROMPT the ref is
the champion prompt digest; when `registry` is provided, PROMPT champions are
resolved via `registry.champion_prompt(target)` instead and the `champions`
entry is optional). Control flow per lesson:
1. If a `Mapping`, adapt via `lesson_from_document` (adapter errors become a
   `ChallengerRejection`, not an exception — generation is total).
2. `classify_forbidden` → nonnull: append
   `ChallengerRejection(lesson_id, "forbidden self-modification class", cls)`;
   also raise nothing (rejections are recorded, generation continues).
3. For each applicability tag `prefix:target`: resolve champion ref. Missing
   champion → rejection `"no live champion for <surface>:<target>"` (a
   challenger MUST have a champion parent — never synthesize a parentless one).
4. Build content: PROMPT surface → champion content + two-line appended
   `"\n\nLesson {lesson_id}: avoid {error_class}; evidence: {provenance[0]}"`
   guidance block (deterministic, so `prompt_digest` is stable). Non-prompt
   surfaces → `json.dumps` (sort_keys, compact separators) of
   `{"surface":..., "target":..., "champion_ref":..., "lesson_id":...,
   "error_class":..., "directive": "counteract <error_class>"}`.
5. Construct `ChallengerSpec` with `hypothesis =
   f"applying lesson {lesson_id} to {surface}:{target} reduces {error_class}"`,
   `changed_scope = (f"{surface}:{target}",)`, `rollback_ref = champion_ref`,
   `provenance = lesson.provenance + (f"lesson:{lesson_id}",)`,
   `challenger_id = "chal:" + canonical_digest((surface, target, champion_ref,
   lesson_id, content_digest))[7:]` (strip the `sha256:` prefix inside the id).
6. If `registry` is provided and surface is PROMPT: call
   `registry.register(target, content, parent_digest=champion_ref,
   created_by=self.generated_by, experiment_id=f"challenger:{lesson_id}")` —
   this stores an immutable artifact and lineage record only. NEVER call
   `registry.promote`, `registry.rollback_champion`, or `registry.quarantine`,
   and never write `champions.json`.
7. Deduplicate: identical `challenger_id` produced twice (same lesson/tag)
   collapses to one spec via `dict.fromkeys`-style ordering.

Determinism: `created_at = utc_now()` is the ONLY non-deterministic field and
is excluded from `challenger_id`; everything else is pure so repeated
generation yields identical ids (tested).

### 3.5 Champion immutability (acceptance criterion 2)

Guarantees, each individually tested: (a) `ChallengerGenerator` has no code
path that calls `promote`/`rollback_champion` or writes `champions.json`; (b)
`ChallengerSpec.__post_init__` raises `ChampionMutationError` when
`challenger_id == champion_ref` or `content_digest == champion_ref`; (c)
`to_experiment_candidate()` inherits `ExperimentCandidate`'s own guard; (d)
after `generate()` with a live registry, `registry.champion_digest(role)` is
byte-identical to its pre-generation value and the champion artifact bytes are
unchanged.

## 4. Implementation order (small commits on `autopilot/challenger-510`)

1. `feat(kernel): add challenger surfaces, lesson adapter, and errors` —
   enums, errors, `AcceptedLesson`, `lesson_from_document`,
   `FORBIDDEN_SELF_MODIFICATION_CLASSES`.
2. `feat(kernel): add immutable challenger specs with champion guards` —
   `ChallengerSpec`, `ChallengerRejection`, `GenerationResult`,
   `to_experiment_candidate`.
3. `feat(kernel): generate challengers from accepted lessons` —
   `classify_forbidden`, `ChallengerGenerator.generate`, registry binding.
4. `test(kernel): cover challenger generation, immutability, and scope denial`
   — full test file (may be committed alongside 1–3 incrementally).
5. Run focused tests, push branch, open draft PR to `main`, attach receipts.

## 5. Test plan — `tests/test_hive_cortex_challengers.py`

File conventions (match `tests/test_hive_cortex_effects.py`): `from __future__
import annotations`, stdlib `tempfile`/`unittest`/`pathlib`, absolute imports
from `hive_mind_os.brain_kernel.challengers`, module-level fixture helpers,
and a trailing `if __name__ == "__main__": unittest.main()`.

Registry fixture recipe (no `bootstrap`, no prompt files needed):

```python
registry = PromptRegistry(tmp_root, ledger=EvidenceLedger(":memory:"))
content = generation_zero_prompt(ROLE_CONTRACTS[Role.OPTIMIZER])
digest = registry.register(Role.OPTIMIZER, content, parent_digest=None,
                           created_by="repository:generation-0")
registry.promote(Role.OPTIMIZER, digest,
                 promoted_by="repository:generation-0",
                 experiment_id="generation-0", expected_current=None)
```

| required_tests name | Test class | Methods |
|---|---|---|
| `challenger-generation-tests` | `ChallengerGenerationTests` | `test_prompt_challenger_binds_champion_hypothesis_scope_rollback_provenance`; `test_planner_policy_retrieval_tool_surfaces_generate_specs` (one accepted lesson per non-prompt surface against a `champions` mapping); `test_generation_is_deterministic_across_repeats` (equal `challenger_id`/`content_digest`); `test_mapping_lessons_adapt_via_lesson_from_document`; `test_missing_champion_yields_rejection_not_parentless_challenger`; `test_to_experiment_candidate_round_trips_fields` |
| `champion-immutability-tests` | `ChampionImmutabilityTests` | `test_generate_leaves_champion_digest_and_artifact_bytes_unchanged` (registry fixture; compare `champion_digest` and `read(digest)` before/after); `test_spec_aliasing_champion_raises_champion_mutation_error` (construct spec with `challenger_id == champion_ref`); `test_registered_challenger_is_content_addressed_not_promoted` (`registry.champion_digest` still generation-zero; lineage contains a `registration` record with `parent_digest == champion`); `test_specs_are_frozen` (`dataclasses.FrozenInstanceError` on attribute assignment) |
| `scope-denial-tests` | `ScopeDenialTests` | `test_forbidden_class_lessons_are_rejected_with_class_named` (tags `champion:optimizer`, `policy:core`, `weights:backbone`, `holdout:p09`, `evaluator:gate`, `budget:tokens` each rejected; `forbidden_class` in `FORBIDDEN_SELF_MODIFICATION_CLASSES`); `test_error_class_matching_forbidden_behavior_is_rejected` (`error_class="metric_gaming"`); `test_forbidden_classes_mirror_recursive_improvement_contract` (constructed `RecursiveImprovementContract` `forbidden_behaviors` == module frozenset); `test_unaccepted_lesson_status_rejected`; `test_unknown_applicability_tag_rejected_without_challenger` |

Edge cases folded into the above: empty `provenance` raises
`ChallengerGenerationError`; `confidence` 0 or >1 raises; rejection list
preserves lesson order; generation with zero lessons returns empty result.

Exact focused commands (the ONLY test invocations this node may run):

```bash
python -m unittest tests.test_hive_cortex_challengers -v
python -m unittest tests.test_hive_cortex_challengers.ChallengerGenerationTests -v
python -m unittest tests.test_hive_cortex_challengers.ChampionImmutabilityTests -v
python -m unittest tests.test_hive_cortex_challengers.ScopeDenialTests -v
```

No `discover`, no other test modules; the R3 integrator runs the single leased
repo-wide pass.

## 6. Acceptance self-check → completion receipt evidence

| Criterion | Demonstrated by | Receipt evidence |
|---|---|---|
| Champion parent + hypothesis + changed scope + rollback + provenance on every challenger | `ChallengerSpec.__post_init__` hard validation; `test_prompt_challenger_binds_...` | Focused test receipt (command + PASS output), spec field inventory in PR description |
| Live champions immutable | No promote/rollback call sites (grep receipt: `grep -n "promote\|rollback\|champions.json" src/hive_mind_os/brain_kernel/challengers.py` shows none outside comments); `ChampionImmutabilityTests` PASS | Grep output + test receipt |
| Forbidden self-modification classes rejected | `classify_forbidden` + `ScopeDenialTests` PASS, including the contract-mirror test | Test receipt naming all six rejected tag families |
| Scope discipline | `git diff --name-only <base>..HEAD` == exactly the two write_scope paths | Changed-path inventory + base/final commit SHAs |
| Rollback | Single revertable commit chain; no retained-evidence rewrites | Rollback ref (base SHA) in receipt |

## 7. Out-of-scope traps — do NOT

- Do not create or edit any `__init__.py`, `conftest.py`, `pyproject.toml`,
  anything under `.autopilot/`, `.github/`, `evidence/courts/`, or
  `docs/architecture/HARDENED_VISION_CONTRACT.md`. Do not write ANY docs file.
- Do not import, read, or modify `hive_mind_os.brain_kernel.learning_runtime`
  or `tests/test_hive_cortex_learning.py` (LEARN-500's files) — consume lesson
  documents only through `lesson_from_document`.
- Do not touch sibling R3 nodes' files (SELFHEAL-450, POISON-540) or wait for
  them; a genuine cross-dependency is an `autopilot fail` blocker.
- Do not call `PromptRegistry.promote`, `rollback_champion`, `quarantine`, or
  `bootstrap`, and do not write `champions.json` — promotion/evaluation belong
  to EVAL-520 and PROMOTE-530.
- Do not call `ExperimentRunner.run` or add an evaluation surface; this node
  generates challengers, it does not score them.
- Do not add new members to `Role`, new forbidden-behavior strings, or edit
  `recursive_improvement.py` / `prompt_registry.py` / `experiment_runner.py`
  in any way (read-only).
- Do not run `python -m unittest discover`, pytest, or repo-wide checks; do
  not merge the PR or start downstream nodes (stopping condition: draft PR +
  validated node receipt).
- Do not weaken acceptance to pass (e.g. making `classify_forbidden` return
  `None` for unknown tags, or making champion checks warnings instead of
  raised errors).
