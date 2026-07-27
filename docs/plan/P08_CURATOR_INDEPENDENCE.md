# P08 — Structural Curator Independence

Status: tracked in `00_OVERVIEW.md` | Depends on: P05 | Unlocks: stronger verification for all later phases

## 1. Objective

Upgrade Curator independence from workspace separation (P05) to structural separation:
blind acceptance-test authoring before the Curator ever sees the Builder's diff, a
kernel-level conflict-of-interest gate that rejects contaminated context or same-identity
verification, and optional per-role model/provider configuration so the Curator can run on
a different model than the Builder.

## 2. Rationale

The vision contract's hard failure list includes "self-review presented as independent
review", and AGENTS.md requires that an acting variant may not approve its own work. P05
enforced separate workspaces and context filtering inside `mission.py`; this phase moves
the guarantee down into enforced checks (so a future orchestration bug cannot silently
reintroduce contamination) and makes the Curator's judgment *blind-first*: it decides what
evidence would prove the objective before seeing what the Builder claims, which is the
strongest cheap defense against verification anchoring. P02's context-manifest receipts
make contamination machine-detectable — this phase uses them.

## 3. Required reading

1. `docs/plan/00_OVERVIEW.md`
2. `src/hive_mind_os/mission.py` (P05 context construction and Curator flow)
3. `src/hive_mind_os/model_backend.py` (context manifests in `model.call` receipts)
4. `src/hive_mind_os/runtime.py` (`_validate_result` — the pattern for kernel-level
   checks)
5. `docs/architecture/HARDENED_VISION_CONTRACT.md` § "Required specialist agents"
   (Curator "must not" column) and § "Hard failure conditions"
6. `tests/test_mission.py` (independence test from P05 — you are strengthening it)

## 4. Prerequisite verification

```bash
python -m pytest -q tests/test_mission.py    # P05 green
```

## 5. Scope

In scope:

- `CuratorReview` pipeline: blind phase → reproduction phase → adversarial checklist →
  verdict.
- Kernel/mission-level conflict-of-interest enforcement (identity and context).
- Per-role provider configuration (`HIVE_MIND_MODEL_PROVIDER__CURATOR=…` style
  overrides).
- Contamination detection over recorded context manifests.

Non-goals:

- No security scanners or SAST integration (a checklist item records "not run" honestly
  rather than pretending). No multi-judge ensembles (P13 introduces independent judges
  for benchmarks; broader ensembles are later). No human review-request flow.

## 6. Design constraints

- **Blind phase.** Curator input in the blind phase is exactly: the objective, acceptance
  criteria, and the base workspace at the mission's base SHA. From this it produces
  `acceptance_checks`: executable commands (sandbox argv form) plus expected outcomes.
  These are sealed — digest recorded in the ledger — before the Curator receives the
  Builder's head. With `ScriptedRepositoryBackend`, the scripted blind output is the
  fixture's canonical failing-test command; with `ModelBackend`, it is a real model turn
  (schema: extend `model-turn` usage, not the schema itself — the checks ride in
  `outputs` as a JSON string field validated by the mission layer).
- **Reproduction phase.** Curator materializes the delivery into a fresh workspace
  (P05 mechanism), runs the sealed `acceptance_checks` plus the repository's own test
  command, and compares against expectations. Only sealed checks and its own runs count
  as verification evidence.
- **Adversarial checklist.** A fixed, versioned checklist recorded with explicit
  tri-state findings (`pass` / `fail` / `not-evaluated`): tests weakened? (diff touches
  test files in ways that reduce assertions — heuristic: assertion-count and
  test-function-count deltas per changed test file), rollback artifact verifies?
  (`verify_delivery`), diff confined to declared scope? provenance receipts resolve?
  license of introduced code declared? `not-evaluated` is honest and allowed; `fail` on
  any item fails the review.
- **Conflict-of-interest gate.** A new check in the mission's result-acceptance path
  (mirroring `HiveKernel._validate_result` placement): (a) the verifying identity must
  differ from the acting identity for any verification-class result; (b) the Curator's
  recorded context manifest (from the `model.call` receipt, or the scripted equivalent)
  must contain no Builder-attributed content: no Builder receipt digests, no Builder
  rationale strings, no diff bytes prior to the blind seal. Violation → the mission
  fails closed with a `contaminated-verification` ledger event. The check runs on
  recorded evidence, not on trust in the orchestration code.
- **Per-role providers.** `provider_from_env()` gains role-scoped overrides:
  `HIVE_MIND_MODEL_MODEL__CURATOR`, etc. Absent overrides, the Curator uses the same
  provider — the receipt records which; a *different* model is recommended posture, not
  a hard requirement (single-provider users must not be blocked). The receipt makes the
  sameness visible for later audit.
- **Backward compatibility.** P05's tests keep passing; the scripted golden path now
  includes the blind seal and checklist events.

## 7. Deliverables

New files:

- `src/hive_mind_os/curator.py` — `CuratorReview`, `AcceptanceCheck`, `ChecklistItem`,
  `ReviewVerdict`, `ContaminationError`, `check_context_manifest()`.
- `tests/test_curator.py`.

Modified files:

- `src/hive_mind_os/mission.py` — Curator stage delegates to `CuratorReview`; result
  acceptance calls the conflict-of-interest gate for verification-class results.
- `src/hive_mind_os/model_provider.py` — role-scoped env overrides.
- `tests/test_mission.py` — strengthen independence assertions to use the new gate's
  evidence (do not delete existing assertions).

## 8. Implementation steps

1. Verify prerequisites; branch `phase/P08-curator-independence`.
2. Implement `AcceptanceCheck` sealing (digest into ledger) and the blind-phase context
   builder; test that the blind context physically lacks the head workspace and diff.
3. Implement the reproduction phase over sealed checks.
4. Implement the adversarial checklist with its heuristics; keep each heuristic small,
   deterministic, and separately tested.
5. Implement `check_context_manifest()` and wire the gate into result acceptance.
6. Add role-scoped provider overrides + receipts recording model identity per role.
7. Update mission golden path and tests.
8. Gates, audit `evidence/audits/P08-post.json`, status updates, completion record.

## 9. Required tests

`tests/test_curator.py`:

1. Blind seal ordering: ledger shows `acceptance_checks` digest event strictly before any
   Curator access to the head workspace; reordering (simulated) → `ContaminationError`.
2. Sealed-check enforcement: a check added after the seal is rejected as verification
   evidence.
3. Reproduction catches the sabotage fixture (test-weakening patch from P05): checklist
   `tests weakened?` fails on assertion-delta heuristic AND the sealed original check
   fails on the head → review verdict negative.
4. Contamination: inject a Builder receipt digest into the Curator context (simulated
   orchestration bug) → gate rejects, mission fails closed, `contaminated-verification`
   event recorded.
5. Same-identity verification: a verification result attributed to the Builder identity →
   rejected.
6. Checklist honesty: an item that cannot run records `not-evaluated` (never silently
   `pass`); verdict logic treats `not-evaluated` as non-blocking but recorded.
7. Per-role override: sentinel env config → Curator receipt shows the overridden model;
   absence → receipt shows shared model explicitly.
8. Full mission golden path (scripted) passes with the new pipeline; sabotage path still
   fails closed.

## 10. Exit criteria

```bash
python -m pytest -q tests/test_curator.py tests/test_mission.py   # all pass
python -m pytest -q && python -m ruff check src tests && pyright  # clean
```

## 11. Evidence

- `evidence/audits/P08-post.json` committed.
- Golden mission report updated with blind-seal and checklist events (normalized) in
  `tests/fixtures/mission/`.

## 12. Rollback

Revert the branch; P05's simpler Curator flow returns intact (its tests are preserved).

## 13. Handoff

Later phases may assume: verification is blind-first and sealed; contamination and
self-verification are machine-detected from recorded evidence; per-role model
configuration exists and is receipted; the adversarial checklist is versioned and
honest about what it did not evaluate.

## 14. Forbidden shortcuts

- No skipping the blind phase "because the scripted backend makes it trivial" — the
  ordering evidence is the point.
- No checklist items that silently pass when their heuristic cannot run.
- Do not let a same-model configuration masquerade as different-model in receipts.
- Do not relax P05 assertions while strengthening them.
