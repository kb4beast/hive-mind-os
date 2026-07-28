# P10 — Champion/Challenger Learning Loop on Real Artifacts

Status: tracked in `00_OVERVIEW.md` | Depends on: P05, P09 | Unlocks: continuous self-improvement

## 1. Objective

Close the learning loop for the first real artifact class — versioned role prompt/policy
templates — by wiring mission and PIT-episode outcomes into the existing
`RecursiveImprovementGate`: a challenger prompt variant is evaluated against the champion
on repeated episodes, the gate issues KEEP/RETEST/DISCARD/QUARANTINE/STOP verdicts with
noise floors and guardrails, and promotion atomically updates a content-addressed prompt
registry with full lineage and rollback — never mutating the live champion.

## 2. Rationale

The recursive-improvement machinery (`recursive_improvement.py`, CLM-067–073) is fully
implemented and fully unused by anything real. The smallest honest artifact class to
improve is the prompt template a role runs on, because P02 made prompts explicit and
receipted, and P05/P09 provide two evaluation surfaces (fixture missions, PIT episodes)
with measurable outcomes. This phase turns "self-improvement through challengers" from a
tested library into an operating loop, while keeping every constitutional boundary
(challenger-only mutation, independent evaluator identity, holdout protection) intact.

## 3. Required reading

1. `docs/plan/00_OVERVIEW.md`
2. `src/hive_mind_os/recursive_improvement.py` (entire file — the gate you must drive:
   `RecursiveImprovementContract`, `ExperimentCandidate`, `MetricSpec`,
   `MetricObservation`, `ExperimentEvidence`, `RecursiveImprovementGate`,
   `RecursiveImprovementController`)
3. `docs/architecture/RECURSIVE_SELF_IMPROVEMENT_DOCKET.md` (non-delegable boundaries)
4. `src/hive_mind_os/model_backend.py` (where prompts are built today)
5. `src/hive_mind_os/pit_oracle.py` (P09 episodes) and `src/hive_mind_os/mission.py`
   (P05 missions) — the two evaluation surfaces
6. `src/hive_mind_os/learning.py` (`LearningPromotionGate` — note overlap; the RSI gate
   is the operative one here)
7. `tests/test_recursive_improvement.py` (the gate's expected use)

## 4. Prerequisite verification

```bash
python -m pytest -q tests/test_mission.py tests/test_pit_oracle.py tests/test_recursive_improvement.py   # pass
```

## 5. Scope

In scope:

- A content-addressed, versioned prompt registry with per-role champion pointers and
  lineage.
- `ModelBackend` reads its role prompt from the registry (with the current built-in
  prompt becoming champion generation 0).
- An experiment runner: evaluate champion vs. challenger over K scripted episodes,
  produce `MetricObservation`s, feed the gate, apply verdicts.
- Atomic promotion/rollback of champion pointers with ledger records.
- A first real experiment executed end-to-end (scripted surfaces; model surfaces
  optional/manual).

Non-goals:

- No automatic challenger *generation* (a challenger is authored — by a human or a
  separate agent turn — and registered; auto-generation is a later phase). No skill or
  workflow artifact classes yet. No cross-repository evaluation corpora. No teaching
  packets beyond what `EvolutionArena`/`TeachingPacket` already provide (do not wire
  them in this phase unless trivially adjacent).

## 6. Design constraints

- **Registry.** `src/hive_mind_os/prompt_registry.py`: artifacts stored content-addressed
  (SHA-256 of canonical bytes) under a registry root; a small SQLite or JSON index maps
  `(role) -> champion_artifact_digest` plus lineage rows
  `(artifact, parent, created_by, created_at, experiment_id)`. Champion updates are
  atomic (temp + `os.replace`) and ledger-evented. Artifacts are immutable once
  registered.
- **Generation 0.** The exact prompt text `ModelBackend` currently builds becomes the
  committed generation-0 artifact per role; `ModelBackend` falls back to it if no
  registry is supplied (no behavior change for existing users/tests).
- **Experiment protocol.** An experiment binds: a `RecursiveImprovementContract`
  (fingerprinted), champion + challenger artifact digests, the evaluation surface
  (fixture-mission suite or PIT-episode set with pinned episode ids), K repetitions,
  and metric specs. Minimum metrics: primary = task success rate (mission success /
  episode grade); guardrails = token cost per episode (from P02 receipts; direction:
  must not regress beyond contract bound) and evidence completeness (receipts resolve;
  hard guardrail). Repetitions satisfy the gate's repeated-measurement requirements
  (read the gate's expectations from its tests and honor them).
- **Independent evaluator identity.** The evaluator identity recorded in
  `ExperimentEvidence` must differ from the identity that authored/registered the
  challenger; reuse the P08 conflict-of-interest check pattern. Scripted surfaces run
  under an `evaluator:scripted-harness` identity.
- **Verdict application.** KEEP → atomic champion pointer update + lineage row +
  `promotion` ledger event with rollback reference (prior digest). DISCARD/QUARANTINE →
  recorded, artifact retained (append-only; quarantined artifacts flagged, never
  deleted). RETEST → runner may re-run up to the contract's patience. STOP → experiment
  closed, recorded.
- **Holdout protection.** If the evaluation surface is a PIT episode set, the runner
  requests environments from the P09 oracle per episode; the challenger's author
  identity must not appear in any oracle reveal event before the experiment closes
  (no peeking at targets while authoring — enforced by checking ledger event ordering
  for the author identity).
- **Rollback.** `rollback_champion(role, to_digest)` restores a prior champion with its
  own ledger event; it never deletes the rolled-back artifact.

## 7. Deliverables

New files:

- `src/hive_mind_os/prompt_registry.py` — registry, lineage, atomic promotion,
  rollback.
- `src/hive_mind_os/experiment_runner.py` — experiment protocol, metric collection,
  gate driving, verdict application.
- `tests/test_prompt_registry.py`, `tests/test_experiment_runner.py`.
- `prompts/` — committed generation-0 artifacts per role (plain text/markdown, one file
  per role, content-addressed copies land in the registry at runtime; the committed
  files are the source of record).

Modified files:

- `src/hive_mind_os/model_backend.py` — optional registry parameter; prompt provenance
  (artifact digest) recorded in every `model.call` receipt.
- `src/hive_mind_os/cli.py` — `hive-mind experiment run --role builder --challenger
  <path> --surface fixture-missions --repetitions K [--state-dir …]`.

## 8. Implementation steps

1. Verify prerequisites; branch `phase/P10-learning-loop`.
2. Extract generation-0 prompts from `ModelBackend` into `prompts/`; registry + fallback
   seam; receipts now carry prompt digests (P02 tests updated additively).
3. Implement the registry with atomic promotion and lineage; unit-test in isolation.
4. Implement the experiment runner against the fixture-mission surface first: champion
   vs. a trivially different challenger, scripted outcomes rigged per test case to
   exercise each verdict path.
5. Add the PIT-episode surface using pinned fixture-DAG episodes.
6. Wire holdout/author-identity ordering check.
7. Run one real end-to-end experiment (scripted surface) whose evidence lands in
   `evidence/experiments/`; this is the exit artifact.
8. CLI; gates; audit `evidence/audits/P10-post.json`; status updates; completion record.

## 9. Required tests

`tests/test_prompt_registry.py`:

1. Content addressing: same bytes → same digest, single storage; different bytes → new
   artifact.
2. Atomic promotion: champion pointer update is all-or-nothing under simulated crash
   (monkeypatch `os.replace` to raise after temp write); registry never points at a
   missing artifact.
3. Lineage: promotion records parent; rollback restores prior digest and records its own
   event; quarantined artifacts remain readable and flagged.
4. Immutability: attempting to overwrite a registered artifact fails.

`tests/test_experiment_runner.py`:

5. KEEP path: rigged observations showing a real repeated improvement → gate KEEP →
   champion updated, lineage correct, ledger events complete.
6. Noise path: sub-noise lift → RETEST then (per patience) no promotion.
7. Guardrail path: primary improves but token-cost guardrail regresses → DISCARD,
   champion unchanged.
8. Quarantine path: evaluator identity equals author identity → QUARANTINE (or typed
   rejection before the gate, matching the gate's contract), champion unchanged.
9. Holdout ordering: author identity appears in an oracle reveal before experiment close
   → experiment invalidated and recorded.
10. Receipt provenance: after promotion, new `model.call` receipts carry the new champion
    digest; after rollback, the prior digest.
11. `ModelBackend` without a registry behaves exactly as before (P02 regression).

## 10. Exit criteria

```bash
python -m pytest -q tests/test_prompt_registry.py tests/test_experiment_runner.py   # pass
python -m pytest -q && python -m ruff check src tests && pyright                    # clean
hive-mind experiment run --role builder --challenger <path-to-a-variant-prompt-file> --surface fixture-missions --repetitions 3   # completes; prints verdict + evidence path (a challenger byte-identical to the champion is rejected by the experiment runner — supply a real variant, e.g. one produced for the KEEP-path test)
test -d evidence/experiments        # contains the real experiment record
```

## 11. Evidence

- `evidence/audits/P10-post.json` and the end-to-end experiment record committed.

## 12. Rollback

Revert the branch; `ModelBackend`'s fallback prompts mean no runtime depends on the
registry. Registered artifacts under a local registry root are user data, untouched.

## 13. Handoff

Later phases may assume: prompts are versioned, content-addressed, receipted artifacts
with champions per role; experiments drive the RSI gate end-to-end; promotion and
rollback are atomic, ledgered, and append-only; the loop is ready for additional artifact
classes and auto-generated challengers.

## 14. Forbidden shortcuts

- Never edit a registered artifact or the champion in place — challenger-only mutation
  is constitutional (CLM-067).
- No promotion on a single measurement, whatever the lift.
- No evaluator == author, even for scripted surfaces.
- Do not bypass the gate with a custom "simpler" promotion path; `LearningPromotionGate`
  overlap is resolved in favor of the RSI gate here.

---

## Completion record

- Date (UTC): 2026-07-28T12:01:52Z
- Executor (model/agent identity): Codex primary Builder/Integrator. Per the user's
  consolidated-review instruction, independent Curator, Judge, and Orchestrator review
  remains deferred until the remaining approved phase PRs are merged; this record is not
  self-approval.
- Branch and audited implementation commit: `phase/P10-learning-loop`;
  `809630224065151cfc3b38e972d27ae79a698300`. The audit was collected from that clean
  commit; the pull-request head carries this append-only audit/status metadata because a
  commit cannot contain its own SHA.
- Gates: P10 exit tests passed (13); full pytest passed (334 passed, 2 pre-existing
  skips, 1,744 subtests); Ruff 0.16.0 passed; Pyright 1.1.411 passed with 0 errors.
- End-to-end experiment:
  `evidence/experiments/EXP-663f252d-8320-47ae-9694-21d2ce36a282.json` recorded a
  repeated scripted-fixture `keep` verdict, distinct author/builder/evaluator
  identities, valid holdout ordering, the prior rollback digest, and atomic Builder
  champion promotion.
- Audit artifact: `evidence/audits/P10-post.json`
  (digest: `sha256:d0d0de25a475199922972133f55c095c75d9e4c390bfd7edef537351e6612221`;
  complete: true; failures: none).
- Deviations from the phase spec: none. The CLI intentionally exposes the required
  fixture-mission surface; the library also supplies the specified pinned P09 episode
  surface without claiming model-backed outcome improvement.
- New blockers discovered (mirrored into `docs/plan/BLOCKERS.md`): none. Existing
  real-provider, source, authenticated-identity, and hostile-isolation obligations remain
  explicitly unresolved and are not promoted by P10.
