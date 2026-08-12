# Learning runtime — scoped, evidence-bound lessons

`src/hive_mind_os/brain_kernel/learning_runtime.py` turns recorded learning
signals into scoped, expiring, advisory lesson records. It is pure and
deterministic: no I/O, no network, no model calls, no wall-clock reads. Every
time value is injected by the caller. The module imports only the standard
library, `.canonical`, `.contracts`, and `.memory`, and it is used by full path
(`hive_mind_os.brain_kernel.learning_runtime`) — no package re-exports.

## Signal vocabulary

A `LearningSignal` is one already-recorded fact. It carries digests, never
free-text excerpts of model or tool output; there is deliberately no
`raw_excerpt` field.

| Field | Rule |
|---|---|
| `signal_id` | non-empty, unique within an attribution batch |
| `kind` | `SignalKind`: `outcome`, `incident`, `remand`, `repair`, `human_correction` |
| `episode_record_id` | matches `MEMORY-[A-Za-z0-9][A-Za-z0-9._-]*` |
| `outcome` | `OutcomeClass`: `success`, `failure`, `partial` |
| `error_class` | non-empty machine token; the attribution bucket key |
| `context_key` | independence key (mission / repository / work context) |
| `evidence_refs` | one or more `sha256:<64 lowercase hex>` digests |
| `observed_at` | RFC 3339 with a mandatory offset |

Any violation raises `LearningDenied` (a `ValueError`, mirroring
`memory.MemoryDenied`).

## Attribution and the point-in-time guard

`LessonGenerator.attribute(signals, now=...)` validates the batch, rejects
duplicate `signal_id`s, rejects any signal whose `observed_at` is after `now`,
and returns signals grouped by `error_class` and ordered by
`(observed_at, signal_id)`. The future-dating rejection is the learning-side
analogue of `repository_learning.RepositoryLearningEpisode.validate_access`:
evidence that did not exist yet may not explain an outcome.

## Lesson invariants

`Lesson` binds seven things and cannot be constructed without them: source
episodes, dominant outcome, error class, applicability, confidence, provenance,
and expiry.

- `valid_to` is **mandatory** and must be strictly after `valid_from`. There is
  no immortal lesson.
- `episode_record_ids` is sorted, unique, non-empty, and every entry is a
  `MEMORY-` identifier.
- `applicability.scope` is one of `MemoryRecord`'s scopes (`global`,
  `repository`, `mission`, `role`, `work_item`); non-global scopes require
  `subject_keys`.
- `provenance.evaluator_id` must differ from the generator identity, keeping the
  generator and the evaluator separate identities.
- `statement` is non-empty and rejected if it contains secret-like tokens (the
  same shape `memory.MemoryArtifactStore.put` refuses).
- `lesson_id` is `"LESSON-"` plus the first 20 hex characters of
  `canonical_digest` over the deterministic core, which **includes the sorted
  evidence digests of every contributing signal**. Two lessons that cite
  different evidence cannot share an identity. `Lesson.digest` is the canonical
  digest of the whole record.

## Evidence burden

Reused from `memory.ConsolidationPolicy` (default: at least two independent
episodes and two distinct contexts), never redefined. `generate` applies it
twice: to the whole `error_class` bucket, and again to the supporting signals
that actually carry the dominant outcome. Otherwise
`LearningDenied("lesson lacks independent evidence")`.

The dominant outcome is the strict majority outcome of the bucket. A tie raises
`LearningDenied` — no coin flips.

## Confidence

At birth, with `supporting` = signals carrying the dominant outcome and
`contrary` = the rest:

```
confidence = round(len(supporting) / (len(supporting) + len(contrary) + 1), 6)
```

The `+1` Laplace term keeps a single anecdote below certainty. Contrary signals
are **not discarded**: each becomes a `Counterexample` on the lesson at birth.

When a counterexample is later retained:

```
confidence' = round(confidence * n / (n + total_counterexamples + 1), 6)
```

with `n = len(lesson.episode_record_ids)` and `total_counterexamples` counted
after the append. Confidence therefore only moves downward and stays in
`[0.0, 1.0]`.

## Expiry

`valid_from = now`; `valid_to = now + default_ttl_days` (90) unless the caller
passes a positive `ttl_days`. Zero or negative windows are refused. The expiry
is rendered in UTC `...Z` form, so `MemoryCatalog.expire` can retire the record
without further interpretation.

## Append-only retention

`retain_counterexample` and `record_dissent` return **new** frozen `Lesson`
objects via `dataclasses.replace`; the original is untouched and nothing is ever
removed. Duplicate counterexample `signal_id`s and duplicate `(role, position)`
dissent pairs are refused so retention cannot be used to overwrite a dissenting
position.

## Advisory only — lessons never promote themselves

Nothing here mutates policy, an instruction template, or champion state. The
module imports no policy or champion code, defines no method shaped like
`apply` / `enforce` / `promote` / `mutate` / `update_policy` / `update_prompt` /
`set_champion`, and a test inspects the module source to keep it that way.

Two separate gates remain the only promotion paths, and both stay with the
caller:

- `MemoryCatalog.consolidate` — promotes a lesson record into durable memory,
  and independently re-checks the same evidence burden against *registered*
  active episodes.
- `learning.LearningPromotionGate.evaluate` — the champion/challenger gate for
  self-improvement; lessons neither call it nor bypass it.

`lesson_memory_record(lesson, content_ref=..., recorded_at=...)` only
*constructs* the `MemoryRecord` form (`memory_class="lesson"`,
`state=ACTIVE`, `supersedes = source_refs = lesson.episode_record_ids`,
`outcome_refs = digest_value = lesson.digest`) so it is *eligible* for that
gate. It registers nothing and calls nothing. The caller stores the lesson body
with `MemoryArtifactStore.put` and passes the resulting digest as
`content_ref`.
