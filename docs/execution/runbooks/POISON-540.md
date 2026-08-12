# POISON-540 — Learning-poisoning qualification (tests and docs only)

## 1. Contract summary

**Objective.** Test and harden memory, lesson, and challenger paths against
poisoning, stale evidence, provenance gaps, and overgeneralization. This node
writes NO kernel code: it is a qualification node that produces an adversarial
unittest suite plus a results document proving the existing defenses hold.

**Acceptance criteria (compressed).**
1. Poisoned / stale / unproven lessons are rejected or quarantined.
2. Contradictions reduce confidence rather than silently overwrite history.
3. Expiry and scope prevent broad reuse.

**Scope table.**

| Kind | Paths |
|---|---|
| write_scope (ONLY these) | `tests/hive_cortex/test_learning_poisoning.py`, `docs/execution/LEARNING_POISONING_RESULTS.md` |
| read_scope | `src/hive_mind_os/brain_kernel/memory.py`, `src/hive_mind_os/brain_kernel/learning_runtime.py`, `tests/hive_cortex/**` |
| forbidden_scope | `.github/CODEOWNERS`, `.github/governance/**`, `evidence/courts/**`, `docs/architecture/HARDENED_VISION_CONTRACT.md` |

**Hard rules (state and obey).**
- Create/modify ONLY the two write_scope paths. Explicitly forbidden: ANY
  `__init__.py` (including `tests/hive_cortex/__init__.py`, which already
  exists — leave it byte-identical), any `conftest.py`, `pyproject.toml`,
  sibling nodes' files (`SELFHEAL-450`, `CHALLENGER-510` are R3 siblings),
  `.autopilot/**`, and everything in forbidden_scope.
- All imports in the test file use full module paths
  (`hive_mind_os.brain_kernel.memory`, `hive_mind_os.brain_kernel.contracts`);
  never edit package re-exports.
- Never touch the release branch; never rebase/squash/amend the node branch
  `autopilot/poison-540`; never run repo-wide test discovery. Run only the
  focused command in section 5; the round integrator owns the single leased
  repo-wide pass.
- If a real dependency on a sibling's files appears, `autopilot fail` with a
  blocker; never wait for or read a sibling's branch.

**Semantic locks:** `learning-poisoning-qualification`.
**Round:** R3 (level 8), wave `SELFHEAL-450 CHALLENGER-510 POISON-540`,
3 parallel sessions. **Dependencies:** LEARN-500, CHEAT-440 (both merged
before R3 dispatch). **Branch:** `autopilot/poison-540`, PR target `main`,
stop at draft PR + receipt (do not merge).

## 2. Existing-code map

All symbols below were read from the current tree and are real. Paths are
repo-relative; signatures are exact.

| Path | Symbol | Signature | Role |
|---|---|---|---|
| `src/hive_mind_os/brain_kernel/memory.py` | `MemoryArtifactStore.put` | `put(self, body: str, *, content_kind: str = "evidence") -> MemoryArtifact` | Rejects secrets (`MemoryDenied`) and transcript kinds; content-addressed, immutable. |
| ″ | `MemoryArtifactStore.get` | `get(self, digest: str) -> str` | Raises `MemoryDenied` on digest mismatch (tamper detection). |
| ″ | `MemoryDenied` | `class MemoryDenied(ValueError)` | The single denial error type. |
| ″ | `MemoryAccess` | `MemoryAccess(roles: tuple[str, ...], data_scopes: tuple[str, ...], evaluator_visible: bool = True)` | Explicit access labels; roles must be in `ROLE_NAMES`. |
| ″ | `MemoryCatalog.__init__` | `__init__(self, artifacts: MemoryArtifactStore) -> None` | Append-only catalog. |
| ″ | `MemoryCatalog.register` | `register(self, record: MemoryRecord, access: MemoryAccess) -> None` | Denies rewrite of an existing id; validates class (evidence needs `source_refs`). |
| ″ | `MemoryCatalog.transition` | `transition(self, record_id: str, state: MemoryState, *, event_id: str, occurred_at: str, reason: str, successor_id: str \| None = None) -> MemoryLifecycleEvent` | Only ACTIVE → terminal is legal. |
| ″ | `MemoryCatalog.quarantine` | `quarantine(self, record_id: str, *, now: str, reason: str, event_id: str \| None = None) -> MemoryLifecycleEvent` | Quarantine fact, evidence retained. |
| ″ | `MemoryCatalog.contradict` | `contradict(self, record_ids: Iterable[str], *, now: str, reason: str) -> tuple[MemoryConflict, tuple[MemoryLifecycleEvent, ...]]` | Preserves conflict + terminal CONTRADICTED facts. |
| ″ | `MemoryCatalog.record_conflict` | `record_conflict(self, record_ids: Iterable[str], *, reason: str, recorded_at: str) -> MemoryConflict` | Conflict without termination; feeds rank penalty. |
| ″ | `MemoryCatalog.consolidate` | `consolidate(self, lesson: MemoryRecord, access: MemoryAccess, *, supporting_record_ids: Iterable[str], independence_keys: Mapping[str, str], now: str, reason: str, policy: ConsolidationPolicy = ConsolidationPolicy()) -> tuple[MemoryLifecycleEvent, ...]` | Lesson promotion gate (anti-overgeneralization). |
| ″ | `MemoryCatalog.expire` | `expire(self, *, now: str) -> tuple[MemoryLifecycleEvent, ...]` | Deterministic expiry of past-`valid_to` records. |
| ″ | `MemoryCatalog.active_records` | `active_records(self, request: RetrievalRequest) -> tuple[MemoryEntry, ...]` | Eligibility filter (state, windows, role, scope, sensitivity). |
| ″ | `MemoryCatalog.rank` | `rank(self, request: RetrievalRequest) -> tuple[RankedMemory, ...]` | Scored retrieval; `unresolved_conflict_penalty` weight −0.18. |
| ″ | `MemoryCatalog.inspect` | `inspect(self, record_id: str) -> tuple[MemoryEntry, MemoryState]` | Metadata + derived state, never body. |
| ″ | `MemoryCatalogStore` | `persist(self, catalog: MemoryCatalog) -> str` / `restore(self, digest: str) -> MemoryCatalog` | Snapshot round-trip; `restore` fails closed on tamper. |
| ″ | `ConsolidationPolicy` | `ConsolidationPolicy(minimum_independent_episodes: int = 2, minimum_distinct_contexts: int = 2)` | Evidence burden; minimums must be ≥ 2. |
| ″ | `RetrievalRequest` | `RetrievalRequest(mission_id, work_id, role, query, now, data_scopes, repository_key=None, explicit_pins=(), graph_proximity=None, prior_usefulness=None, sensitivity_scopes=("public","internal"), required_sensitivities=())` | Retrieval envelope; role must be in `ROLE_NAMES`. |
| ″ | `RankedMemory` | fields `entry, token_count, terms`; property `score` | Score comparisons in tests. |
| `src/hive_mind_os/brain_kernel/contracts.py` | `MemoryRecord` | 19 positional fields, in order: `record_id, memory_class, scope, subject_keys, content_ref, source_refs, authority_level, sensitivity, valid_from, valid_to, recorded_at, available_at, state, supersedes, superseded_by, evaluator_id, outcome_refs, retention_policy, digest_value` | The immutable record contract. `record_id` must match `MEMORY-[A-Za-z0-9][A-Za-z0-9._-]*`; times RFC 3339 with offset; `digest_value` must match `sha256:<64 hex>` (pattern only). |
| ″ | `MemoryState` | StrEnum: `ACTIVE, SUPERSEDED, CONTRADICTED, RETRACTED, EXPIRED, QUARANTINED` | Lifecycle states. |
| `src/hive_mind_os/contracts.py` | `ROLE_NAMES` | frozenset: orchestrator, explorer, architect, builder, curator, integrator, steward, optimizer | Valid roles for access/requests. |
| `tests/test_brain_kernel_memory_context.py` | `KernelMemoryContextTests.record(...)` helper | — | The fixture pattern to copy (do NOT import it; replicate locally). |
| `tests/hive_cortex/test_acceptance_harness.py` | — | — | Naming/run convention for this package: plain `unittest.TestCase`, run via `PYTHONPATH=src python -m unittest tests.hive_cortex.<module> -v`. |

**LEARN-500 surface (`src/hive_mind_os/brain_kernel/learning_runtime.py`).**
This module is created by dependency LEARN-500 (round R2B) and does not exist
in the tree this runbook was authored from; its runbook was not yet present.
At execution time it WILL exist (R2B merges before R3 dispatch). Read it and
`docs/execution/LEARNING_RUNTIME.md` (also LEARN-500 output) before writing
suite 4 in section 3. Do not guess its API — quote real symbols from the file
you read. Its contract guarantees: lessons bind source episode, outcome,
error class, applicability, confidence, provenance, and expiry;
counterexamples/dissent retained; no lesson mutates policy/prompt/champion.

## 3. Design

### 3.1 `tests/hive_cortex/test_learning_poisoning.py`

One new test module, standard library `unittest` only. No new production
code, no fixtures directory changes, no conftest.

Module header and shared fixture base:

```python
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hive_mind_os.brain_kernel.contracts import MemoryRecord, MemoryState
from hive_mind_os.brain_kernel.memory import (
    ConsolidationPolicy,
    MemoryAccess,
    MemoryArtifactStore,
    MemoryCatalog,
    MemoryCatalogStore,
    MemoryDenied,
    RetrievalRequest,
)

DIGEST = "sha256:" + "0" * 64
TIME = "2026-08-07T12:00:00Z"       # baseline instant
SOON = "2026-08-08T12:00:00Z"       # +1 day
LATER = "2026-08-09T12:00:00Z"      # +2 days


class _PoisoningFixture(unittest.TestCase):
    def setUp(self) -> None: ...      # TemporaryDirectory -> MemoryArtifactStore -> MemoryCatalog
    def tearDown(self) -> None: ...   # cleanup
    def record(self, record_id: str, body: str, *, memory_class: str = "fact",
               scope: str = "mission", subject_keys: tuple[str, ...] = ("MISSION-one",),
               source_refs: tuple[str, ...] = ("SRC-one",),
               valid_from: str = TIME, valid_to: str | None = None,
               available_at: str = TIME, supersedes: tuple[str, ...] = (),
               outcome_refs: tuple[str, ...] = (), evaluator_id: str | None = None,
               sensitivity: str = "internal") -> MemoryRecord: ...
    def access(self, roles: tuple[str, ...] = ("builder",)) -> MemoryAccess: ...
    def request(self, *, mission_id: str = "MISSION-one", role: str = "builder",
                query: str = "", now: str = SOON) -> RetrievalRequest: ...
```

`record` calls `self.artifacts.put(body)` and builds the 19-field
`MemoryRecord` exactly as `tests/test_brain_kernel_memory_context.py` does
(copy that constructor ordering verbatim; `state=MemoryState.ACTIVE`,
`superseded_by=()`, `retention_policy="retain"`, `digest_value=DIGEST`).
`access` returns `MemoryAccess(roles, ("internal",), True)`. `request`
returns `RetrievalRequest(mission_id, "WORK-one", role, query, now,
("internal",))`.

Three required-suite classes plus one conditional class, each subclassing
`_PoisoningFixture`:

**`class MemoryPoisoningSuite(_PoisoningFixture)`** — injection, tamper,
rewrite, quarantine, contradiction, provenance gaps.
- `test_secret_and_transcript_bodies_are_rejected` — `put("api_key = ...")`
  and `put(body, content_kind="model_transcript")` both raise `MemoryDenied`.
- `test_tampered_artifact_fails_closed_on_read` — put a body, overwrite the
  file at `self.artifacts._path(digest)`, assert `get` raises `MemoryDenied`.
- `test_registered_records_cannot_be_rewritten` — register `MEMORY-a`, then
  register a different record with the same id → `MemoryDenied`; re-register
  the identical entry is a no-op (no raise).
- `test_evidence_without_provenance_is_rejected` — a record with
  `memory_class="evidence", source_refs=()` → `register` raises
  `MemoryDenied` ("evidence memory requires source references").
- `test_quarantine_retains_evidence_and_blocks_retrieval` — register, assert
  present in `active_records`; `quarantine(record_id, now=SOON, reason=...)`;
  assert `inspect` returns state `QUARANTINED`, body still readable via
  `artifacts.get`, and record absent from `active_records`/`rank`.
- `test_contradiction_preserves_history_and_terminates_both_sides` —
  register `MEMORY-a`, `MEMORY-b`; `contradict(("MEMORY-a","MEMORY-b"),
  now=SOON, reason=...)` returns one `MemoryConflict` and two events; both
  states are `CONTRADICTED`; both records still inspectable; `conflicts_for`
  names both; neither appears in `rank`.
- `test_single_record_contradiction_is_rejected` — `contradict(("MEMORY-a",),
  ...)` raises `ValueError` (MemoryConflict needs ≥ 2 distinct ids).
- `test_unresolved_conflict_reduces_rank_confidence` — register `MEMORY-a`,
  `MEMORY-b`, `MEMORY-c` with the SAME body text; `record_conflict(
  ("MEMORY-a","MEMORY-b"), reason=..., recorded_at=SOON)` (no termination —
  records stay ACTIVE); `rank(self.request(query=<body words>))`: conflicted
  records score exactly `0.18` below the unconflicted one and sort last.
  This is criterion 2: confidence reduced, history intact.
- `test_snapshot_tamper_fails_closed` — build a catalog with one record and
  one lifecycle event; `store = MemoryCatalogStore(root)`;
  `digest = store.persist(catalog)`; corrupt the snapshot file at
  `store._path(digest)` by editing a character INSIDE an existing JSON
  string value (e.g. replace one character of a string field's value) so
  the document still parses as JSON; `store.restore(digest)` then raises
  `MemoryDenied` on the snapshot digest mismatch. Do NOT flip an arbitrary
  byte: if the corruption makes the file unparseable, `restore` raises
  `KeyError` instead (its `json.loads` error path), not `MemoryDenied`.

**`class StaleEvidenceSuite(_PoisoningFixture)`** — expiry, embargo,
freshness decay.
- `test_expiry_is_deterministic_and_terminal` — record with `valid_to=SOON`;
  `expire(now=LATER)` returns one event with state `EXPIRED`; second
  `expire(now=LATER)` returns `()` (idempotent); record absent from
  `active_records(request(now=LATER))`.
- `test_expired_and_embargoed_records_are_not_retrievable` — one record with
  `valid_to=SOON` queried at `now=LATER` (past window, even before `expire`
  runs — `_eligible` checks `valid_to`), one with `available_at=LATER`
  queried at `now=SOON`, one with `valid_from=LATER` queried at `now=SOON`:
  all absent from `active_records`.
- `test_stale_evidence_ranks_below_fresh_evidence` — two records, same body:
  `MEMORY-fresh` with `valid_to=LATER`, `MEMORY-stale` with `valid_to`
  slightly after `now` (e.g. `"2026-08-08T13:00:00Z"` with `now=SOON`); rank
  at `now=SOON`: fresh scores strictly higher (freshness term, weight 0.10).
- `test_scope_prevents_cross_mission_reuse` — mission-scoped record with
  `subject_keys=("MISSION-one",)` is returned for `request(
  mission_id="MISSION-one")` and NOT for `request(mission_id="MISSION-two")`;
  same for `scope="work_item"` vs a foreign `work_id`, and `scope="role"` vs
  a foreign role. This is criterion 3 (scope half).

**`class OvergeneralizationSuite(_PoisoningFixture)`** — the `consolidate`
gate. Helper `episode(record_id, body)` = `self.record(record_id, body,
memory_class="episode", outcome_refs=("OUT-1",))`; helper
`lesson(supersedes)` = `self.record("MEMORY-lesson", "always pin deps",
memory_class="lesson", supersedes=supersedes, evaluator_id="EVAL-court-1",
outcome_refs=("OUT-1",), valid_to=LATER)`.
- `test_unproven_lesson_is_rejected` — lesson with `evaluator_id=None`, or
  `outcome_refs=()`, or `supersedes` not equal to the sorted support tuple:
  each `consolidate` call raises `MemoryDenied` ("complete independent
  approval").
- `test_too_few_episodes_is_rejected` — one episode only → `MemoryDenied`
  ("too few episodes"); also `ConsolidationPolicy(1, 2)` itself raises
  `ValueError` (minimums cannot be weakened below two).
- `test_dependent_contexts_are_rejected` — two episodes with
  `independence_keys={"MEMORY-e1": "ctx", "MEMORY-e2": "ctx"}` (same
  context) and with a missing key (empty string path) → `MemoryDenied`
  ("independent contexts").
- `test_unevidenced_or_inactive_support_is_rejected` — a supporting record
  that is (a) `memory_class="fact"` not episode, (b) an episode already
  quarantined, or (c) an episode with `outcome_refs=()` → `MemoryDenied`
  ("active evidenced episodes"). Note (c) must bypass the helper default.
- `test_valid_consolidation_retires_episodes_and_lesson_expires` — two
  episodes, distinct independence keys; `consolidate` succeeds returning two
  SUPERSEDED events with `successor_id="MEMORY-lesson"`; episodes leave
  `active_records`; lesson present at `now=SOON`; after `expire(now=<past
  LATER>)` the lesson is EXPIRED and absent — criterion 3 (expiry half) and
  criterion 1 for the accept path.

**`class LearningRuntimePoisoningSuite(_PoisoningFixture)` (conditional).**
After reading the real `learning_runtime.py` (read_scope), add 2–4 tests
that its lesson-generation entry point (whatever LEARN-500 actually named)
rejects lessons missing provenance, applicability scope, or expiry, and
retains counterexamples — using only symbols you can quote from that file.
If the module's API offers no such directly testable seam, OMIT this class
and record the gap explicitly in the results doc instead (do not fabricate
imports; the three required suites above fully cover the node's
`required_tests`). Never import from sibling-node files.

### 3.2 `docs/execution/LEARNING_POISONING_RESULTS.md`

Adversarial results document (the node's "decision artifact"). Structure:
- Header: node id, branch, base commit SHA, date, focused-test command.
- Attack matrix table: one row per test method — columns: attack class
  (poisoning / stale evidence / provenance gap / overgeneralization /
  scope-and-expiry), attack description, defending symbol
  (e.g. `MemoryCatalog.consolidate`), observed outcome (denied / quarantined
  / confidence-reduced / expired), test method name.
- Residual-risk section: at minimum (a) `digest_value` on `MemoryRecord` is
  pattern-validated, not content-bound, (b) `independence_keys` are
  caller-asserted, so context independence is only as strong as the caller,
  (c) whatever you found (or could not test) in `learning_runtime.py`.
- Verbatim focused-test output (the `OK` tail) as the receipt evidence block.

## 4. Implementation order

1. Read `src/hive_mind_os/brain_kernel/memory.py`,
   `src/hive_mind_os/brain_kernel/learning_runtime.py`, and
   `tests/test_brain_kernel_memory_context.py` (fixture pattern).
2. Commit 1: `test_learning_poisoning.py` with `_PoisoningFixture` +
   `MemoryPoisoningSuite`; run the focused command; green.
3. Commit 2: add `StaleEvidenceSuite`; run; green.
4. Commit 3: add `OvergeneralizationSuite` (and
   `LearningRuntimePoisoningSuite` if section 3.1's condition holds); run.
5. Commit 4: `docs/execution/LEARNING_POISONING_RESULTS.md` with the attack
   matrix and the verbatim test output.
6. Push branch, open draft PR to `main`, produce the node completion receipt
   (base/final commits, changed paths = exactly the two write_scope files,
   command receipts, roles curator/optimizer/steward, rollback = revert the
   node commit). STOP — do not merge, do not start downstream nodes.

## 5. Test plan

| required_tests name | Test class | Methods |
|---|---|---|
| `memory-poisoning-suite` | `MemoryPoisoningSuite` | `test_secret_and_transcript_bodies_are_rejected`, `test_tampered_artifact_fails_closed_on_read`, `test_registered_records_cannot_be_rewritten`, `test_evidence_without_provenance_is_rejected`, `test_quarantine_retains_evidence_and_blocks_retrieval`, `test_contradiction_preserves_history_and_terminates_both_sides`, `test_single_record_contradiction_is_rejected`, `test_unresolved_conflict_reduces_rank_confidence`, `test_snapshot_tamper_fails_closed` |
| `stale-evidence-suite` | `StaleEvidenceSuite` | `test_expiry_is_deterministic_and_terminal`, `test_expired_and_embargoed_records_are_not_retrievable`, `test_stale_evidence_ranks_below_fresh_evidence`, `test_scope_prevents_cross_mission_reuse` |
| `overgeneralization-suite` | `OvergeneralizationSuite` | `test_unproven_lesson_is_rejected`, `test_too_few_episodes_is_rejected`, `test_dependent_contexts_are_rejected`, `test_unevidenced_or_inactive_support_is_rejected`, `test_valid_consolidation_retires_episodes_and_lesson_expires` |

Exact focused command (matches `tests/hive_cortex/` conventions — the
package has an `__init__.py`, modules run by dotted path):

```
PYTHONPATH=src python -m unittest tests.hive_cortex.test_learning_poisoning -v
```

Never run `python -m unittest discover`. Edge cases already embedded above:
idempotent double-expire, identical re-register no-op, single-record
conflict, missing independence key, policy floor (`ConsolidationPolicy(1,2)`
rejected), embargoed `available_at`.

Gotchas verified against the real code:
- `MemoryRecord` ids must start `MEMORY-`; mission ids `MISSION-`; work ids
  `WORK-`; all times RFC 3339 WITH offset (`Z` accepted).
- `rank` reads every eligible body via `artifacts.get`, so every registered
  record's artifact must exist and be untampered in rank tests.
- `contradict`/`quarantine` leave records inspectable but non-ACTIVE, so
  they vanish from `rank`; the confidence-REDUCTION assertion must use
  `record_conflict` (records stay ACTIVE, penalty term −0.18 applies).
- `supersedes` on a lesson must equal `tuple(sorted(set(support_ids)))`.

## 6. Acceptance self-check

| Criterion | Demonstrated by | Receipt evidence |
|---|---|---|
| Poisoned/stale/unproven lessons rejected or quarantined | `MemoryPoisoningSuite` (denials + quarantine), `OvergeneralizationSuite` (all rejection paths), `StaleEvidenceSuite` expiry tests | Focused-test output block in results doc; attack matrix rows |
| Contradictions reduce confidence, never overwrite | `test_unresolved_conflict_reduces_rank_confidence` (exact −0.18 delta), `test_contradiction_preserves_history_and_terminates_both_sides` (records retained), `test_snapshot_tamper_fails_closed` (history not rewritable) | Same output block; matrix rows citing `contradict`/`record_conflict`/`rank` |
| Expiry and scope prevent broad reuse | `test_scope_prevents_cross_mission_reuse`, `test_valid_consolidation_retires_episodes_and_lesson_expires`, `test_expired_and_embargoed_records_are_not_retrievable` | Same output block; matrix rows |
| Evidence requirements | Base/final SHAs, changed-path inventory (exactly 2 files), command receipts, role identities, rollback ref | Node completion receipt attached to the draft PR |

## 7. Out-of-scope traps (do NOT do)

- Do NOT modify `src/hive_mind_os/brain_kernel/memory.py` or
  `learning_runtime.py` — even if a test exposes a real weakness. Record it
  under Residual risks in the results doc and, if it breaches an acceptance
  criterion, `autopilot fail` with an escalation ("current code contradicts
  a node assumption") instead of patching outside write_scope.
- Do NOT touch `tests/hive_cortex/__init__.py`, `tests/hive_cortex/
  acceptance_harness.py`, `test_acceptance_harness.py`, or any
  `tests/fixtures/**` file.
- Do NOT create helper modules, conftest.py, or edit `pyproject.toml`; the
  test file is self-contained.
- Do NOT import from `tests.test_brain_kernel_memory_context` (outside this
  node's package and not part of its contract surface) — replicate the
  fixture locally.
- Do NOT test challenger/champion promotion machinery (CHALLENGER-510 and
  PROMOTE-530 own that); this node's "challenger path" coverage is the
  contradiction/quarantine/conflict-penalty surface of `MemoryCatalog` plus
  the conditional `learning_runtime` suite.
- Do NOT run repo-wide discovery, touch `.autopilot/**`, rewrite retained
  evidence, or merge the draft PR.
