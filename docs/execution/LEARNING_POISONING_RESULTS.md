# POISON-540 — Learning-poisoning qualification results

| Field | Value |
|---|---|
| Node | POISON-540 (R3, level 8; wave `SELFHEAL-450 CHALLENGER-510 POISON-540`) |
| Dependencies | LEARN-500, CHEAT-440 (both integrated before this run) |
| Working branch | `release/hive-mind-os-singleton-20260812-r5` |
| Base commit | `a0a84c84faec5e63e4e61a95a16b599532008113` |
| Date | 2026-08-12 |
| Interpreter | CPython 3.14.4 (Windows) |
| Focused test command | `PYTHONPATH=src python -m unittest tests.hive_cortex.test_learning_poisoning -v` |
| Changed paths | `tests/hive_cortex/test_learning_poisoning.py`, `docs/execution/LEARNING_POISONING_RESULTS.md` |
| Result | 22 tests, `OK` |

This node writes no kernel code. It is a qualification node: every fixture
constructs a real poisoning attempt against a real kernel surface
(`hive_mind_os.brain_kernel.memory`, `hive_mind_os.brain_kernel.learning_runtime`)
and asserts the surface refuses or contains it. Every rejection assertion is
paired with a positive control at the same seam, so a fixture cannot pass by
breaking the surface outright.

## 1. Attack matrix

Attack classes: **P** poisoning/injection, **S** stale evidence, **G**
provenance gap, **O** overgeneralization, **X** scope-and-expiry.

### `MemoryPoisoningSuite` — `required_tests: memory-poisoning-suite` (9 methods)

| # | Class | Attack constructed | Defending symbol | Observed outcome | Test method |
|---|---|---|---|---|---|
| 1 | P | `put("api_key = AKIA…")`, `put("ghp_…")`, `put(body, content_kind="model_transcript")`, `put("")` | `MemoryArtifactStore.put` | denied (`MemoryDenied`: "secret-like data", "raw transcripts", non-empty body) | `test_secret_and_transcript_bodies_are_rejected` |
| 2 | P | Overwrite the stored body at `artifacts._path(digest)` with a favourable claim, then re-`put` the true body to relaunder the file | `MemoryArtifactStore.get` / `.put` | denied ("digest mismatch"; "cannot be rewritten"); readable again only after true bytes restored | `test_tampered_artifact_fails_closed_on_read` |
| 3 | P | Re-register `MEMORY-a` with a different body; then with the same body but widened access roles | `MemoryCatalog.register` | denied ("memory record cannot be rewritten"); identical re-register is an idempotent no-op | `test_registered_records_cannot_be_rewritten` |
| 4 | G | `memory_class="evidence"` with `source_refs=()`; an unregistered `memory_class="policy"`; a `content_ref` naming a body never stored | `MemoryCatalog._validate_class`, `MemoryCatalog._verified_artifact` | denied ("evidence memory requires source references", "memory class is not registered", `KeyError` on the dangling artifact) | `test_evidence_without_provenance_is_rejected` |
| 5 | P | Register poisoned guidance ("always disable the verifier"), quarantine it, then transition it silently back to `ACTIVE` | `MemoryCatalog.quarantine`, `.transition` | quarantined: body still readable via `artifacts.get`, record absent from `active_records`/`rank`; revival denied ("transition is not legal") | `test_quarantine_retains_evidence_and_blocks_retrieval` |
| 6 | P | Contradict two incompatible retry-budget records | `MemoryCatalog.contradict` | one `MemoryConflict` + two events; both sides `CONTRADICTED`, both bodies retained and inspectable, both absent from `rank`; only the uncontradicted third record survives | `test_contradiction_preserves_history_and_terminates_both_sides` |
| 7 | P | Retire a rival by "contradicting" it against nothing (`("MEMORY-a",)`), then by repeating it (`("MEMORY-a","MEMORY-a")`) | `MemoryConflict.__post_init__` | denied (`ValueError`: "a conflict requires at least two distinct records"); record stays `ACTIVE` | `test_single_record_contradiction_is_rejected` |
| 8 | P | Assert an unresolved conflict over two of three identical-body records to knock rivals out of retrieval | `MemoryCatalog.record_conflict` + `MemoryCatalog.rank` | confidence-reduced, not deleted: all three stay `ACTIVE` and present in `rank`; conflicted records carry `unresolved_conflict_penalty == 1.0` and score exactly `0.18` below the unconflicted one, sorting last | `test_unresolved_conflict_reduces_rank_confidence` |
| 9 | P | Edit a retained lifecycle `reason` inside a persisted snapshot so the file still parses as JSON | `MemoryCatalogStore.restore` | denied ("memory snapshot digest mismatch"); restores again only after the true bytes are returned | `test_snapshot_tamper_fails_closed` |

### `StaleEvidenceSuite` — `required_tests: stale-evidence-suite` (4 methods)

| # | Class | Attack constructed | Defending symbol | Observed outcome | Test method |
|---|---|---|---|---|---|
| 10 | S/X | Re-run `expire` to mint a second, differently-dated expiry history; then revive expired guidance to `ACTIVE` | `MemoryCatalog.expire`, `.transition` | expired terminally: one event, repeat `expire` at two later instants returns `()`, lifecycle event count stays 1; revival denied ("transition is not legal") | `test_expiry_is_deterministic_and_terminal` |
| 11 | S/X | Cite guidance that is embargoed (`available_at` in the future), not yet valid (`valid_from` in the future), or past `valid_to` — the last queried **before** any `expire` fact exists | `MemoryCatalog._eligible` | all three absent from `active_records` at the relevant instant with zero lifecycle events appended; each becomes eligible only once its own boundary passes | `test_expired_and_embargoed_records_are_not_retrievable` |
| 12 | S | Two identical bodies, one closing in 1 h and one in 24 h, both still eligible at the query instant | `MemoryCatalog.rank` (`freshness_score`, weight 0.10) | confidence-reduced: stale freshness and total score strictly below fresh; ranks second | `test_stale_evidence_ranks_below_fresh_evidence` |
| 13 | X | Reuse a mission-scoped finding on `MISSION-two`, a work-item finding on `WORK-two`, and a role-scoped finding from `curator`. All three records grant **both** roles, so each exclusion is the scope filter and not the access filter | `MemoryCatalog._eligible` (scope arms) | each foreign-scope request omits exactly the out-of-scope record and keeps the in-scope ones | `test_scope_prevents_cross_mission_reuse` |

### `OvergeneralizationSuite` — `required_tests: overgeneralization-suite` (5 methods)

| # | Class | Attack constructed | Defending symbol | Observed outcome | Test method |
|---|---|---|---|---|---|
| 14 | G/O | Promote a lesson with `evaluator_id=None`; with `outcome_refs=()`; superseding one episode while citing two; relabelled `memory_class="opinion"` | `MemoryCatalog.consolidate` | denied ("lesson consolidation lacks a complete independent approval"); the fully approved lesson promotes | `test_unproven_lesson_is_rejected` |
| 15 | O | Generalize a rule from a single anecdote; then weaken the burden itself with `ConsolidationPolicy(1,2)`, `(2,1)`, `(0,0)` | `MemoryCatalog.consolidate`, `ConsolidationPolicy.__post_init__` | denied ("too few episodes"; `ValueError` "minimums must be integers of at least two"); default policy confirmed at the floor `(2, 2)` | `test_too_few_episodes_is_rejected` |
| 16 | O | Two episodes sharing one `independence_keys` context; an omitted key; an empty-string key | `MemoryCatalog.consolidate` | denied ("lesson consolidation lacks independent contexts"); two genuinely distinct contexts promote | `test_dependent_contexts_are_rejected` |
| 17 | G/O | Support the lesson with (a) a plain `fact`, (b) an already-quarantined episode, (c) an episode with `outcome_refs=()`, (d) an episode with `source_refs=()` — (c) and (d) bypass the helper defaults | `MemoryCatalog.consolidate` | denied ("lesson consolidation requires active evidenced episodes") in all four cases; two active, sourced, measured episodes promote | `test_unevidenced_or_inactive_support_is_rejected` |
| 18 | X | Accept path: promote a properly evidenced lesson, then let its validity window elapse | `MemoryCatalog.consolidate` → `.supersede`, `.expire` | two `SUPERSEDED` events with `successor_id="MEMORY-lesson"`; episodes leave `active_records` but stay inspectable; lesson active at `SOON`, `expire` is a no-op at `SOON`, and the lesson is `EXPIRED` and absent past `valid_to` | `test_valid_consolidation_retires_episodes_and_lesson_expires` |

### `LearningRuntimePoisoningSuite` — conditional suite against LEARN-500 (4 methods)

Section 3.1 of the runbook made this suite conditional on the real
`learning_runtime.py` exposing a directly testable seam. It does:
`LessonGenerator.generate`, `LessonProvenance`, `LessonApplicability`,
`Lesson`, `retain_counterexample`, `record_dissent`, and
`lesson_memory_record` are all constructible from public symbols, so the suite
is included. No sibling-node file is imported.

| # | Class | Attack constructed | Defending symbol | Observed outcome | Test method |
|---|---|---|---|---|---|
| 19 | G | Let the generator sign off on its own lesson (`generator == evaluator_id`); claim a lesson with no signal ids; inflate evidence by repeating one signal id; cite a signal with `evidence_refs=()`; bind a signal to a non-`MEMORY-` episode id | `LessonProvenance.__post_init__`, `LearningSignal.__post_init__` | denied (`LearningDenied`: "evaluator identity must differ from the generator", "at least one signal id", "signal_ids must be sorted and unique", "requires at least one evidence digest", "must be a MEMORY- identifier"); a generated lesson always carries `GENERATOR_IDENTITY` and the separate evaluator id | `test_lesson_provenance_cannot_be_self_certified_or_unsourced` |
| 20 | P/X | Collapse a lesson's expiry window (`valid_to = valid_from`); request `ttl_days` of 0 and -1; give an unapproved lesson the memorable id `LESSON-always-pin-deps`; swap the statement under an approved lesson identity | `Lesson.__post_init__`, `LessonGenerator.generate`, `Lesson.digest` | denied ("expiry must be strictly after valid_from", "ttl_days must be a positive integer", "lesson_id must be a derived LESSON- digest prefix"); the tampered statement changes `Lesson.digest` and regenerating with it yields a different derived `lesson_id`; `lesson_memory_record` carries the derived digest and the bounded window through to `MemoryRecord` | `test_lesson_identity_and_expiry_cannot_be_forged` |
| 21 | O/S/P | Generalize from one episode in one context, and from two episodes in one shared context; teach from a signal observed after `now`; replay one `signal_id` twice so a single incident looks like a pattern; attribute the lesson to an error class no signal carries; smuggle a credential into the statement; widen applicability past the scope vocabulary or drop its subject keys | `LessonGenerator._require_independence`, `.attribute`, `.generate`, `LessonApplicability.__post_init__` | denied ("lesson lacks independent evidence", "future-dated signal cannot inform a lesson", "duplicate signal id in attribution batch", "no signal carries the requested error class", "contains secret-like data", "applicability scope is outside the memory vocabulary", "non-global applicability requires subject_keys"); independent past-dated signals yield a mission-scoped lesson | `test_unproven_future_dated_or_secret_signals_cannot_yield_a_lesson` |
| 22 | P | Bury a disagreeing signal instead of recording it; re-file the same counterexample to drown out the rest; hide a counterexample behind a credential-bearing note; pad the record with the same dissent twice | `LessonGenerator.generate`, `retain_counterexample`, `record_dissent`, `Counterexample.__post_init__` | contained: the contrary signal is retained as a `Counterexample` and lowers confidence below the clean lesson; `retain_counterexample` returns a new lesson with strictly lower confidence and leaves the original object untouched; duplicates denied ("counterexample signal is already retained", "dissent position is already recorded"); secret-bearing note denied | `test_counterexamples_and_dissent_are_retained_and_reduce_confidence` |

## 2. Acceptance criteria

| Criterion | Demonstrated by |
|---|---|
| 1. Poisoned / stale / unproven lessons are rejected or quarantined | Rows 1–5, 9 (injection, tamper, rewrite, provenance gap, quarantine), 14–17 (every consolidation rejection path), 19–21 (learning-runtime rejection paths), 10–11 (stale windows) |
| 2. Contradictions reduce confidence rather than silently overwrite history | Row 8 (exact −0.18 penalty with all records retained and `ACTIVE`), row 6 (both sides `CONTRADICTED`, both bodies retained), row 22 (counterexamples appended, never removed; original lesson object unmutated), rows 2/3/9 (retained history is not rewritable) |
| 3. Expiry and scope prevent broad reuse | Rows 10, 11, 13, 18 (scope filters per mission/work item/role; deterministic terminal expiry; a promoted lesson expires with its window), row 20 (a lesson cannot be granted an unbounded TTL) |

## 3. Anti-tautology verification

A fake anti-poisoning test is itself the poison it claims to detect, so the
suite was mutation-checked. Six real defences were neutered **at runtime only**
(monkeypatched in a throwaway script outside the repository; no kernel source
was edited and nothing was committed), and the affected tests were re-run:

| Neutered defence | Tests re-run | Result with the defence removed |
|---|---|---|
| `MemoryCatalog._unresolved_conflict_ids` → always empty | `test_unresolved_conflict_reduces_rank_confidence` | 1 failure / 1 run |
| `MemoryArtifactStore.get` → return file bytes without the digest check | `test_tampered_artifact_fails_closed_on_read` | 1 failure / 1 run |
| `MemoryCatalogStore.restore` → rebuild without the snapshot digest comparison | `test_snapshot_tamper_fails_closed` | 1 failure / 1 run |
| `MemoryCatalog.consolidate` → supersede without the approval/episode/context gates | `OvergeneralizationSuite` | 4 failures / 5 runs |
| `MemoryCatalog._eligible` → state and role checks only (windows and scope dropped) | `StaleEvidenceSuite` | 2 failures / 4 runs |
| `LessonGenerator._require_independence` → no-op | `LearningRuntimePoisoningSuite` | 1 failure / 4 runs |

The partial counts are expected and are themselves evidence of correct
attribution: `test_expiry_is_deterministic_and_terminal` and
`test_stale_evidence_ranks_below_fresh_evidence` do not depend on the window and
scope arms of `_eligible`, and only one of the four learning-runtime tests
depends on `_require_independence`. Every mutation produced at least one
failure, so no assertion in this suite passes vacuously.

## 4. Residual risks

These are recorded, not patched: `memory.py` and `learning_runtime.py` are
outside this node's write scope and were not modified.

1. **`MemoryRecord.digest_value` is pattern-validated, not content-bound.**
   `MemoryRecord.__post_init__` (`src/hive_mind_os/brain_kernel/contracts.py`
   line 499) only checks `_digest(...)`, i.e. the `sha256:<64 hex>` shape. The
   fixtures in this suite all pass the constant `sha256:0…0` and every record
   registers. Integrity of the *body* is enforced separately and genuinely — via
   `content_ref` and `MemoryArtifactStore.get` (row 2) — but the record's own
   self-declared digest is not verified against its metadata, so a caller can
   record a digest that commits to nothing. Note that `learning_runtime`'s
   `lesson_memory_record` does better: it sets `digest_value=lesson.digest`, a
   real content-derived digest (row 20).
2. **`independence_keys` are caller-asserted.** `MemoryCatalog.consolidate`
   (`memory.py` lines 648–650) only checks that the keys are non-empty and
   distinct; it never derives context from the episode records themselves. A
   caller that labels two episodes from the same run `ctx-0` and `ctx-1` clears
   the anti-overgeneralization gate. The gate stops omission and obvious
   duplication (row 16) but is only as strong as the caller's honesty. The same
   holds for `LessonGenerator._require_independence`, which trusts
   `LearningSignal.context_key`.
3. **`Lesson.lesson_id` is shape-checked, not recomputed, on construction.**
   `Lesson.__post_init__` enforces `LESSON-[0-9a-f]{20}` but does not recompute
   the digest prefix from the lesson's own fields, so a hand-built `Lesson` may
   carry any well-formed 20-hex id. What *is* defended, and asserted in row 20:
   a non-derived meaningful id is refused, tampering with the statement changes
   `Lesson.digest`, and regenerating through `LessonGenerator.generate` produces
   a different id — so a forged id cannot inherit an approved lesson's digest.
   A consumer must therefore trust `Lesson.digest`, not `lesson_id`, as the
   identity of record.
4. **`MemoryCatalog.record_conflict` accepts any caller-supplied conflict and
   there is no resolution path.** An adversarial caller can suppress a truthful
   record's rank by 0.18 simply by asserting a conflict against it (row 8), and
   nothing in `memory.py` clears `_conflicts`. This is a deliberate
   fail-closed trade — confidence is reduced rather than history overwritten —
   but the penalty is permanent for the life of the catalog.
5. **Not covered here by design.** Challenger/champion promotion machinery is
   owned by CHALLENGER-510 and PROMOTE-530 and was not exercised. This node's
   challenger-path coverage is the contradiction / quarantine / conflict-penalty
   surface of `MemoryCatalog` plus the `learning_runtime` suite above. Separately,
   `learning_runtime` exposes no policy, prompt, or champion mutation seam at all
   — consistent with its stated contract — so "no lesson mutates policy/prompt/
   champion" is verified by the absence of such a symbol rather than by a test.

## 5. Receipt — verbatim focused-test output

```
$ PYTHONPATH=src python -m unittest tests.hive_cortex.test_learning_poisoning -v
test_counterexamples_and_dissent_are_retained_and_reduce_confidence (tests.hive_cortex.test_learning_poisoning.LearningRuntimePoisoningSuite.test_counterexamples_and_dissent_are_retained_and_reduce_confidence) ... ok
test_lesson_identity_and_expiry_cannot_be_forged (tests.hive_cortex.test_learning_poisoning.LearningRuntimePoisoningSuite.test_lesson_identity_and_expiry_cannot_be_forged) ... ok
test_lesson_provenance_cannot_be_self_certified_or_unsourced (tests.hive_cortex.test_learning_poisoning.LearningRuntimePoisoningSuite.test_lesson_provenance_cannot_be_self_certified_or_unsourced) ... ok
test_unproven_future_dated_or_secret_signals_cannot_yield_a_lesson (tests.hive_cortex.test_learning_poisoning.LearningRuntimePoisoningSuite.test_unproven_future_dated_or_secret_signals_cannot_yield_a_lesson) ... ok
test_contradiction_preserves_history_and_terminates_both_sides (tests.hive_cortex.test_learning_poisoning.MemoryPoisoningSuite.test_contradiction_preserves_history_and_terminates_both_sides) ... ok
test_evidence_without_provenance_is_rejected (tests.hive_cortex.test_learning_poisoning.MemoryPoisoningSuite.test_evidence_without_provenance_is_rejected) ... ok
test_quarantine_retains_evidence_and_blocks_retrieval (tests.hive_cortex.test_learning_poisoning.MemoryPoisoningSuite.test_quarantine_retains_evidence_and_blocks_retrieval) ... ok
test_registered_records_cannot_be_rewritten (tests.hive_cortex.test_learning_poisoning.MemoryPoisoningSuite.test_registered_records_cannot_be_rewritten) ... ok
test_secret_and_transcript_bodies_are_rejected (tests.hive_cortex.test_learning_poisoning.MemoryPoisoningSuite.test_secret_and_transcript_bodies_are_rejected) ... ok
test_single_record_contradiction_is_rejected (tests.hive_cortex.test_learning_poisoning.MemoryPoisoningSuite.test_single_record_contradiction_is_rejected) ... ok
test_snapshot_tamper_fails_closed (tests.hive_cortex.test_learning_poisoning.MemoryPoisoningSuite.test_snapshot_tamper_fails_closed) ... ok
test_tampered_artifact_fails_closed_on_read (tests.hive_cortex.test_learning_poisoning.MemoryPoisoningSuite.test_tampered_artifact_fails_closed_on_read) ... ok
test_unresolved_conflict_reduces_rank_confidence (tests.hive_cortex.test_learning_poisoning.MemoryPoisoningSuite.test_unresolved_conflict_reduces_rank_confidence) ... ok
test_dependent_contexts_are_rejected (tests.hive_cortex.test_learning_poisoning.OvergeneralizationSuite.test_dependent_contexts_are_rejected) ... ok
test_too_few_episodes_is_rejected (tests.hive_cortex.test_learning_poisoning.OvergeneralizationSuite.test_too_few_episodes_is_rejected) ... ok
test_unevidenced_or_inactive_support_is_rejected (tests.hive_cortex.test_learning_poisoning.OvergeneralizationSuite.test_unevidenced_or_inactive_support_is_rejected) ... ok
test_unproven_lesson_is_rejected (tests.hive_cortex.test_learning_poisoning.OvergeneralizationSuite.test_unproven_lesson_is_rejected) ... ok
test_valid_consolidation_retires_episodes_and_lesson_expires (tests.hive_cortex.test_learning_poisoning.OvergeneralizationSuite.test_valid_consolidation_retires_episodes_and_lesson_expires) ... ok
test_expired_and_embargoed_records_are_not_retrievable (tests.hive_cortex.test_learning_poisoning.StaleEvidenceSuite.test_expired_and_embargoed_records_are_not_retrievable) ... ok
test_expiry_is_deterministic_and_terminal (tests.hive_cortex.test_learning_poisoning.StaleEvidenceSuite.test_expiry_is_deterministic_and_terminal) ... ok
test_scope_prevents_cross_mission_reuse (tests.hive_cortex.test_learning_poisoning.StaleEvidenceSuite.test_scope_prevents_cross_mission_reuse) ... ok
test_stale_evidence_ranks_below_fresh_evidence (tests.hive_cortex.test_learning_poisoning.StaleEvidenceSuite.test_stale_evidence_ranks_below_fresh_evidence) ... ok

----------------------------------------------------------------------
Ran 22 tests in 0.192s

OK
```
