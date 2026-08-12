# CHEAT-440 — Negative-fixture proof of cheating detection

## 1. Contract summary

**Objective.** Prove cheating detection and independent challenge against the seven
defined cheating classes: test weakening, evaluator leakage, future access, stale
evidence, fake receipts, authority expansion, and friendly consultation. This node
writes TESTS and EVIDENCE only — it adds no kernel code and changes no behavior.

**Acceptance criteria (compressed).**
1. Every defined cheating class has a negative fixture (a test that proves the
   kernel rejects the cheat).
2. Suspected cheating triggers a role council before continuation.
3. Confirmed cheating quarantines; disproved cheating cites retained evidence.
4. Same-model role labels are never presented as independent humans.

**Scope table.**

| Kind | Paths |
|---|---|
| write_scope | `tests/hive_cortex/test_no_cheating.py`, `evidence/autonomy/no-cheating/**`, `docs/execution/NO_CHEATING_RESULTS.md` |
| read_scope | `tests/hive_cortex/**`, `src/hive_mind_os/brain_kernel/**`, `src/hive_mind_os/verify.py` |
| forbidden_scope | `.github/CODEOWNERS`, `.github/governance/**`, `evidence/courts/**`, `docs/architecture/HARDENED_VISION_CONTRACT.md` |

**HARD RULES (restated; violating any of these is a scope violation, stop and
`autopilot fail`):**
- Create/modify ONLY the three write_scope paths above. Explicitly forbidden: any
  `__init__.py` (including `tests/hive_cortex/__init__.py`, which already exists —
  do not touch it), any `conftest.py`, `pyproject.toml`, `.autopilot/**`, all
  forbidden_scope paths, and every sibling node's files — in particular
  `tests/hive_cortex/test_humanless_operation.py` and any other HUMANLESS-430,
  DURABLE-410, DELIVERY-420, or LEARN-500 file.
- This node creates NO new source modules; all imports are full module paths of
  EXISTING modules (`hive_mind_os.brain_kernel.consultation`, etc.). No package
  re-export edits anywhere.
- Never touch the release branch; never rebase/squash/amend the node branch
  `autopilot/cheat-440`; plain forward commits only.
- Never run repo-wide test discovery (`python -m unittest discover` is the round
  integrator's single leased pass). Run ONLY the focused commands in §5.
- Do not weaken any acceptance check to make a fixture pass (node assumption:
  "No node may expand its own authority or weaken acceptance to pass"). If an
  existing kernel surface contradicts an expectation below, that is an escalation
  condition — `autopilot fail` with the evidence; do not adjust the expectation.

**Semantic locks:** `no-cheating-qualification`.
**Round/siblings:** R2B, dispatched with `DELIVERY-420 HUMANLESS-430 CHEAT-440 LEARN-500` (all scope-disjoint; never wait on a sibling). DURABLE-410 integrated in R2A.
**Stopping condition:** draft PR to `main` with a validated node receipt; do not merge.

## 2. Existing-code map (verified signatures — build ONLY on these)

All paths relative to repo root. Every fixture below drives one of these real surfaces.

| Path | Symbol | Real signature / shape | Role in this node |
|---|---|---|---|
| `src/hive_mind_os/brain_kernel/consultation.py` | `ConsultationRequest` | dataclass `(request_id, mission_id, question, reason_code, requesting_role, applicable_roles, round=1, suspected_cheating=False, evidence_refs=(), authority_class=None)`; rejects requester in `applicable_roles`, needs >=2 applicable roles | friendly-consultation negatives |
| same | `RoleAssessment` | dataclass `(role, identity, answer=None, evidence_refs=(), proposed_decision=RESOLVED, dissent=None, cheating_disposition=NOT_APPLICABLE, authority_required=False, identity_kind="model_role")`; `identity_kind` must be `model_role`/`procedural_role` | council testimony; human-label negative |
| same | `evaluate_consultation(request, assessments) -> ConsultationResult` | raises `ValueError("human escalation is forbidden before two roles evaluate the question")` on <2 assessments; adjudicates `CheatingDisposition` | role-council + quarantine/disproved proofs |
| same | `ConsultationResult` | frozen dataclass; `__post_init__` enforces CONFIRMED⇒QUARANTINE, UNRESOLVED⇒QUARANTINE, identity_records shape `{identity, identity_kind, role}` | direct-construction negatives |
| same | `ConsultationDecision`, `ConsultationReason`, `CheatingDisposition`, `MIN_CONSULTED_ROLES` | StrEnums; `MIN_CONSULTED_ROLES == 2` | assertions |
| `src/hive_mind_os/brain_kernel/court_runtime.py` | `CourtParticipant` | dataclass `(seat, identity, task, identity_kind="procedural_role")`; non-{model_role, procedural_role} kind raises `CourtProtocolError("court participants cannot claim independent human status")` | human-label negative |
| same | `CourtBrief` | dataclass `(participant, conclusion, evidence_refs, role_result_refs=(), consultation_refs=(), dissent=None)`; evidence_refs must be non-empty | court fixtures |
| same | `CourtCase` | dataclass `(case_id, claim_kind, subject, affected_identities, role_results=(), consultations=())` | cheating-claim court |
| same | `CourtVerdict` | dataclass `(case_id, disposition, decided_by, reasons, evidence_refs, dissent=())` | verdicts |
| same | `CourtRecord`, `CourtHistory.append(record)`, `record_case(history, case, briefs, verdict, *, appeal_of=None)` | panel needs seats {ADVOCATE, CROSS_EXAMINER, EXPERT_WITNESS, JUDGE}, distinct identities, distinct advocate/cross tasks; judge ∉ `case.source_identities`; unresolved cheating cannot be approved; appeal needs adverse parent verdict, fresh appeals judge, and materially NEW evidence | stale-evidence + friendly-court negatives |
| same | `CourtSeat`, `CourtDisposition`, `CourtClaimKind`, `CourtProtocolError` | StrEnums / `ValueError` subclass | assertions |
| `src/hive_mind_os/brain_kernel/curator_runtime.py` | `CuratorRuntime.seal_acceptance(*, mission_id, work_id, curator_id, checks, failure_verdict=CuratorVerdict.REMAND) -> BlindAcceptanceSeal` | seals checks BEFORE any candidate exists | test-weakening fixtures |
| same | `BlindAcceptanceSeal` | dataclass `(mission_id, work_id, curator_id, checks, failure_verdict, seal_digest)`; rejects tampered `seal_digest`, empty/duplicate checks, and `failure_verdict` not in {REJECT, REMAND} | test-weakening negatives |
| same | `CuratorVerdict`, `CuratorVerificationError` | Enum / `RuntimeError` subclass | assertions |
| `src/hive_mind_os/brain_kernel/memory.py` | `MemoryArtifactStore(root)`, `.put(body, *, content_kind="evidence") -> MemoryArtifact`, `.get(digest) -> str`, `._path(digest) -> Path` | content-addressed; `.get` raises `MemoryDenied("memory artifact digest mismatch")` on tampered bytes (tamper-via-`_path` pattern already used by `tests/test_brain_kernel_memory_context.py:92`) | stale-evidence fixture |
| same | `MemoryCatalog(artifacts)`, `.register(record, access)`, `.rank(request) -> tuple[RankedMemory, ...]` | eligibility drops records with `available_at`/`valid_from` in the future (`memory.py:821`) | future-access fixture |
| same | `MemoryAccess(roles, data_scopes, evaluator_visible=True)`, `RetrievalRequest(mission_id, work_id, role, query, now, data_scopes, ...)`, `MemoryDenied` | access labels + retrieval | fixtures |
| `src/hive_mind_os/brain_kernel/context.py` | `ContextCompiler(catalog, manifests=None)`, `.compile(request) -> CompiledContext` | `evaluator_mode=True` strips `evaluator_visible=False` records and `scratchpad`/`self_assessment` classes; manifest gets `"evaluator_isolation"` in `excluded_categories` and `generator_evaluator_separated=True` | evaluator-leakage fixtures |
| same | `ContextRequest(mission_id, work_id, attempt_id, role, charter_digest, authority_digest, token_budget, query, now, data_scopes, hot_items, repository_key=None, evaluator_mode=False, ...)`, `HotContextItem(reference, token_count)` | request shape | fixtures |
| `src/hive_mind_os/brain_kernel/contracts.py` | `MemoryRecord` | positional order: `record_id, memory_class, scope, subject_keys, content_ref, source_refs, authority_level, sensitivity, valid_from, valid_to, recorded_at, available_at, state, supersedes, superseded_by, evaluator_id, outcome_refs, retention_policy, digest_value` | future-dated records |
| same | `ConstraintEnvelope` (line 300), `Budget` (8 non-negative ints: `max_wall_seconds, max_model_calls, max_input_tokens, max_output_tokens, max_cost_microunits, max_tool_calls, max_work_items, max_depth`), `MemoryState` | authority envelopes | authority fixtures |
| `src/hive_mind_os/brain_kernel/authority.py` | `intersect_envelopes(parent, child) -> ConstraintEnvelope` | raises `AuthorityDenied("child envelope broadens or is not bound to its parent")` | authority-expansion negative |
| same | `AuthorityRegistry.register(envelope, parent=None)`, `.revoke(digest)`, `.authorize(digest, action, target, *, now) -> CapabilityToken`; `AuthorityDenied(PermissionError)` | denies orphan children, out-of-scope writes, denied actions, expiry, revocation | authority-expansion negatives |
| `src/hive_mind_os/brain_kernel/local_assurance.py` | `build_local_assurance_report(*, candidate_commit, candidate_tree, phase11_routes, benchmark_report, test_receipts) -> dict` | requires receipts `{"phase11-parity","phase11-rollback","security-regression","recovery-regression"}` all `status=="passed"`; caps `release_ready=False` etc. | fake-receipt negatives |
| same | `verify_local_assurance_artifact(report_path, receipt_manifest_path) -> dict`; `LocalAssuranceError(ValueError)` | recomputes `report_digest`, re-hashes every transcript file, rejects mismatches | fake-receipt tamper fixture |
| `tests/hive_cortex/acceptance_harness.py` | `AcceptanceRun`, `Consultation(requester, consulted, independent=True)`, `Approval(actor, approved_by, candidate_commit)`, `EffectReceipt(role, effect_id)`, `validate_run(run) -> tuple[str, ...]`, `SPECIALIST_ROLES` | issue codes incl. `future-leakage:*`, `fake-consultation:*`, `self-approval:*` | future-access + friendly-consultation harness checks |
| `tests/hive_cortex/test_acceptance_harness.py` | `valid_run()` pattern | copy the construction style (do NOT import from a sibling test module; re-declare a local `_valid_run()` helper) | fixture template |

Copyable construction patterns (do not invent alternatives):
`tests/test_brain_kernel_memory_context.py` lines 25–83 (DIGEST/TIME constants, `record()`,
`access()`, `request()` helpers) and 249–261 (evaluator-mode compile);
`tests/test_brain_kernel_authority.py` lines 9–32 (`envelope()` helper with
`Budget(1, 0, 0, 0, 0, 0, 1, 1)` and placeholder `DIGEST = "sha256:" + "0" * 64`).

## 3. Design — `tests/hive_cortex/test_no_cheating.py` (the only new code file)

Standard-library `unittest` only, absolute imports from `hive_mind_os.*`, plus a
relative import of the harness: `from .acceptance_harness import ...` (same style as
`tests/hive_cortex/test_acceptance_harness.py`). Module constants:

```python
DIGEST = "sha256:" + "0" * 64
SHA_COMMIT = "a" * 40
SHA_TREE = "b" * 40
TIME = "2026-08-07T12:00:00Z"
LATER = "2026-08-08T12:00:00Z"
EVIDENCE_REF = "evidence/autonomy/no-cheating/probe-1"
```

Module helpers (top level, no new public API):
- `_valid_run() -> AcceptanceRun` — verbatim shape of `valid_run()` in
  `tests/hive_cortex/test_acceptance_harness.py` (roles=`SPECIALIST_ROLES`, sealed
  candidate `"candidate-1"`, one clean consultation and approval).
- `_assessment(role, identity, **overrides) -> RoleAssessment`.
- `_cheating_request(**overrides) -> ConsultationRequest` — defaults:
  `request_id="REQ-1", mission_id="MISSION-1", question="candidate weakened a test?",
  reason_code=ConsultationReason.SUSPECTED_CHEATING, requesting_role="builder",
  applicable_roles=("curator", "steward"), suspected_cheating=True`.
- `_brief(seat, identity, task, evidence=(EVIDENCE_REF,)) -> CourtBrief` and
  `_panel(judge_identity="judge-1", evidence=(EVIDENCE_REF,)) -> tuple[CourtBrief, ...]`
  building the four required seats: advocate `adv-1`/task `"defend"`, cross-examiner
  `cross-1`/task `"attack"`, expert witness `wit-1`/task `"measure"`, judge
  `judge-1`/task `"decide"`.
- `_benchmark_report() -> dict` and `_assurance_report(receipts) -> dict` for
  local-assurance fixtures:

```python
def _benchmark_report() -> dict:
    return {
        "run_id": "RUN-1", "code_digest": SHA_COMMIT,
        "corpus_digest": DIGEST, "harness_digest": DIGEST, "results_digest": DIGEST,
        "lane_digests": {"lane-a": DIGEST},
        "verdict": {"disposition": "measurement-recorded", "judge_id": "judge-1",
                    "lane_identities": ["lane-a", "lane-b"]},
    }

_RECEIPT_NAMES = ("phase11-parity", "phase11-rollback", "security-regression", "recovery-regression")

def _assurance_report(receipts) -> dict:
    return build_local_assurance_report(
        candidate_commit=SHA_COMMIT, candidate_tree=SHA_TREE,
        phase11_routes=({"route": "anthropic", "manifest_digest": DIGEST,
                         "parity_receipt_digest": DIGEST, "rollback_receipt_digest": DIGEST},),
        benchmark_report=_benchmark_report(), test_receipts=tuple(receipts),
    )
```

Four test classes — one per `required_tests` suite name:

### class `NoCheatingSuiteTests(unittest.TestCase)` → `no-cheating-suite`
- `test_test_weakening_tampered_seal_fails_closed` — seal via
  `CuratorRuntime().seal_acceptance(mission_id="MISSION-1", work_id="WORK-1",
  curator_id="curator-1", checks=("unit", "lint"))`; then construct
  `BlindAcceptanceSeal("MISSION-1", "WORK-1", "curator-1", ("unit",), seal.failure_verdict,
  seal.seal_digest)` (dropped check, reused digest) → `assertRaisesRegex(
  CuratorVerificationError, "seal digest is invalid")`. Also empty `checks=()` and
  duplicate checks each raise `CuratorVerificationError`.
- `test_test_weakening_cannot_convert_failure_into_adoption` —
  `seal_acceptance(..., failure_verdict=CuratorVerdict.ADOPT)` →
  `assertRaisesRegex(CuratorVerificationError, "only reject or remand")`.
- `test_stale_evidence_rewritten_artifact_is_denied` — `tempfile.TemporaryDirectory`;
  `store = MemoryArtifactStore(root)`; `artifact = store.put("retained probe evidence")`;
  overwrite `store._path(artifact.digest)` with different bytes;
  `store.get(artifact.digest)` → `assertRaises(MemoryDenied)`; re-`put` of a different
  body colliding with the tampered file raises `MemoryDenied` ("cannot be rewritten").
- `test_stale_evidence_appeal_without_new_evidence_is_rejected` — build parent
  `CourtRecord`: `CourtCase("CASE-1", CourtClaimKind.CHEATING, "weakened test",
  ("builder-1",))`, briefs `_panel()`, verdict `CourtVerdict("CASE-1",
  CourtDisposition.REJECT, "judge-1", ("weakening confirmed",), (EVIDENCE_REF,))`;
  `history = record_case(CourtHistory(), case, briefs, verdict)`. Appeal record
  `CASE-2` with `appeal_of="CASE-1"`: five seats (the four required with NEW identities
  `adv-2/cross-2/wit-2/judge-2` plus `CourtSeat.APPEALS_JUDGE` identity `appeal-1`,
  verdict `decided_by="appeal-1"`) but ONLY recycled evidence refs →
  `assertRaisesRegex(CourtProtocolError, "materially new retained evidence")`. Then the
  same appeal with one extra fresh ref appends successfully (control).
- `test_fake_receipts_fail_closed_in_report_builder` —
  `_assurance_report` with one receipt `status="failed"` →
  `assertRaisesRegex(LocalAssuranceError, "did not pass")`; with a required name missing
  → `"required receipt is missing"`; duplicate names → `LocalAssuranceError`.
- `test_fake_receipts_tampered_report_or_transcript_is_rejected` — in a tmp dir:
  write four transcript files `t-<name>.txt`, compute
  `"sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()` per file, build receipts
  with those digests, `report = _assurance_report(receipts)`; write
  `bench.json` = `json.dumps(_benchmark_report())` and manifest
  `{"schema_version": 1, "candidate_commit": SHA_COMMIT, "candidate_tree": SHA_TREE,
  "report_digest": report["report_digest"], "receipts": [{"name", "command":
  ["python", "-m", "unittest"], "interpreter": "python", "transcript_path", "digest"}...],
  "benchmark_summary": {"path": "bench.json", "digest": <file digest>}}`;
  `verify_local_assurance_artifact(report_path, manifest_path)` passes (control);
  then (a) append bytes to one transcript → `assertRaisesRegex(LocalAssuranceError,
  "transcript digest does not match")`; (b) restore transcript, set
  `report["release_ready"] = True`, rewrite report.json →
  `"report digest does not match its content"`.
- `test_future_access_observed_commits_must_be_sealed` — harness:
  `validate_run(replace(_valid_run(), observed_commits=("base-1", "future-1")))` yields
  a code starting `"future-leakage:"`; `observed_commits=("base-1", "unsealed-1")`
  yields `"future-leakage:observed-commit-not-sealed"`; `_valid_run()` yields `()`.
- `test_suspected_cheating_triggers_role_council_before_continuation` —
  `evaluate_consultation(_cheating_request(), [_assessment("curator", "curator-1")])`
  → `assertRaisesRegex(ValueError, "before two roles")`; with two assessments carrying
  no cheating votes, result has `cheating_disposition is CheatingDisposition.UNRESOLVED`,
  `decision is ConsultationDecision.QUARANTINE`, `answer is None` (no continuation).
- `test_confirmed_cheating_quarantines_and_disproved_cites_retained_evidence` —
  (a) one assessment votes `CheatingDisposition.CONFIRMED` → result CONFIRMED +
  QUARANTINE; (b) both vote DISPROVED with `evidence_refs=(EVIDENCE_REF,)` → result
  DISPROVED, decision RESOLVED, and `EVIDENCE_REF in result.evidence_refs`;
  (c) both vote DISPROVED with NO evidence anywhere → UNRESOLVED + QUARANTINE;
  (d) direct `ConsultationResult(...)` with `cheating_disposition=CONFIRMED` and
  `decision=RESOLVED` → `assertRaisesRegex(ValueError, "confirmed cheating must quarantine")`.

### class `EvaluatorLeakageSuiteTests(unittest.TestCase)` → `evaluator-leakage-suite`
`setUp`/`tearDown` and `record()`/`access()` helpers copied from
`tests/test_brain_kernel_memory_context.py:31-83` (tmp `MemoryArtifactStore` +
`MemoryCatalog`); extend `record()` with an `available_at: str = TIME` parameter.
- `test_evaluator_mode_excludes_generator_material` — register visible evidence for
  role `curator` and a `memory_class="scratchpad"` record with
  `access(roles=("curator",), evaluator_visible=False)`; compile
  `ContextRequest("MISSION-one", "WORK-one", "ATTEMPT-curator", "curator", DIGEST,
  DIGEST, 40, "evidence", LATER, ("internal",), (), evaluator_mode=True)`; assert the
  scratch record is absent from `manifest.warm_items` and `manifest.cold_references`,
  `"evaluator_isolation" in manifest.excluded_categories`, and
  `manifest.generator_evaluator_separated is True`.
- `test_generator_manifest_never_claims_separation` — same compile with
  `evaluator_mode=False` → `generator_evaluator_separated is False` and the scratchpad
  IS retrievable (proving the exclusion is the evaluator gate, not accident).
- `test_future_dated_memory_is_invisible_to_every_context` — register a record with
  `available_at=LATER` (and one with `valid_from=LATER`); `catalog.rank(
  RetrievalRequest("MISSION-one", "WORK-one", "curator", "evidence", TIME, ("internal",)))`
  contains neither; at `now=LATER` both appear (control). This is the memory-layer
  future-access fixture backing `memory.py:821`.

### class `AuthorityExpansionSuiteTests(unittest.TestCase)` → `authority-expansion-suite`
Module helper `_envelope(*, envelope_id="AUTH-parent", parent=None, allowed=("write",),
write_scope=("src",), expires_at="2030-01-01T00:00:00Z") -> ConstraintEnvelope` modeled
exactly on `tests/test_brain_kernel_authority.py:12-32` (risk `"R1"`, actor `"builder"`,
denied `("push", "merge", "deploy")`, `Budget(1, 0, 0, 0, 0, 0, 1, 1)`, placeholder
`DIGEST` for `policy_fingerprint`/`digest_value`; child envelopes set
`parent_envelope_digest=parent.digest_value`).
- `test_child_envelope_cannot_broaden_parent` — child with
  `allowed=("write", "deploy")` → `assertRaises(AuthorityDenied)` from
  `intersect_envelopes(parent, child)`; child with `write_scope=("src", "docs")` →
  same; an equal-or-narrower child returns unchanged (control).
- `test_orphan_child_cannot_self_register` — `AuthorityRegistry().register(child)`
  where `child.parent_envelope_digest` is set but `parent=None` →
  `assertRaisesRegex(AuthorityDenied, "parent envelope is required")`.
- `test_registry_denies_scope_expansion_expiry_and_revocation` — register parent;
  `authorize(DIGEST, "write", "docs/x.md", now=...)` → denied (outside write scope);
  `authorize(DIGEST, "deploy", "src/x.py", ...)` → denied (denied action);
  `now` past `expires_at` → denied; after `revoke(DIGEST)` even a valid request →
  denied. Positive control: `authorize(DIGEST, "write", "src/x.py", now="2029-01-01T00:00:00Z")`.

### class `FriendlyConsultationSuiteTests(unittest.TestCase)` → `friendly-consultation-suite`
- `test_requester_cannot_pack_its_own_council` — `_cheating_request(
  applicable_roles=("builder", "curator"))` (requester `builder` inside) →
  `assertRaisesRegex(ValueError, "cannot approve its own consultation")`; fewer than
  two applicable roles → `ValueError`.
- `test_echo_chamber_testimony_is_rejected` — `evaluate_consultation` with two
  assessments from the SAME role → `assertRaisesRegex(ValueError, "only once")`;
  an assessment from a role outside `applicable_roles` → `ValueError`.
- `test_harness_flags_friendly_consultation` — `validate_run` on `_valid_run()` with
  `consultations=(Consultation("curator", ("curator", "steward")),)` →
  `"fake-consultation:curator"`; `Consultation("curator", ("steward", "optimizer"),
  independent=False)` → same code; `approvals=(Approval("builder", "builder",
  "candidate-1"),)` → `"self-approval:builder"`.
- `test_role_labels_are_never_independent_humans` —
  `RoleAssessment("curator", "curator-1", identity_kind="independent_human")` →
  `assertRaisesRegex(ValueError, "cannot claim to be independent humans")`;
  `CourtParticipant(CourtSeat.JUDGE, "judge-1", "decide", identity_kind="human")` →
  `assertRaisesRegex(CourtProtocolError, "cannot claim independent human status")`;
  a `ConsultationResult` document round-trip via `evaluate_consultation` has every
  `identity_records[i]["identity_kind"]` in `{"model_role", "procedural_role"}`.
- `test_friendly_court_is_structurally_impossible` — (a) briefs where two seats share
  identity `"judge-1"` → `assertRaisesRegex(CourtProtocolError, "distinct identity")`;
  (b) judge identity inside `case.affected_identities` →
  `"cannot adjudicate an affected"`; (c) advocate and cross-examiner with the same
  task string → `"distinct tasks"`; (d) a case whose `consultations` include an
  UNRESOLVED-cheating `ConsultationResult` (build via `evaluate_consultation` with
  `_cheating_request()` and two non-voting assessments) receiving
  `CourtDisposition.ADOPT` → `"unresolved cheating cannot receive an approving verdict"`.

## 4. Implementation order (small commits on `autopilot/cheat-440`)

1. Commit 1: `tests/hive_cortex/test_no_cheating.py` with constants, helpers, and
   `NoCheatingSuiteTests` (curator seal + stale evidence + fake receipts + future
   access + council/quarantine/disproved). Run the focused command; all green.
2. Commit 2: add `EvaluatorLeakageSuiteTests` and `AuthorityExpansionSuiteTests`. Run.
3. Commit 3: add `FriendlyConsultationSuiteTests`. Run full focused file with `-v`;
   capture the transcript to `evidence/autonomy/no-cheating/test-transcript.txt`.
4. Commit 4: write `evidence/autonomy/no-cheating/no_cheating_receipt.json` (§6 shape)
   and `docs/execution/NO_CHEATING_RESULTS.md` (§6 matrix). Final focused rerun.
5. Push branch, open the draft PR against `main`, attach the node completion receipt.
   Do not merge; do not start downstream nodes.

## 5. Test plan

| required_tests name | unittest class (all in `tests/hive_cortex/test_no_cheating.py`) | Focused command |
|---|---|---|
| `no-cheating-suite` | `NoCheatingSuiteTests` (9 methods, §3) | `PYTHONPATH=src python -m unittest tests.hive_cortex.test_no_cheating.NoCheatingSuiteTests -v` |
| `evaluator-leakage-suite` | `EvaluatorLeakageSuiteTests` (3 methods) | `PYTHONPATH=src python -m unittest tests.hive_cortex.test_no_cheating.EvaluatorLeakageSuiteTests -v` |
| `authority-expansion-suite` | `AuthorityExpansionSuiteTests` (3 methods) | `PYTHONPATH=src python -m unittest tests.hive_cortex.test_no_cheating.AuthorityExpansionSuiteTests -v` |
| `friendly-consultation-suite` | `FriendlyConsultationSuiteTests` (5 methods) | `PYTHONPATH=src python -m unittest tests.hive_cortex.test_no_cheating.FriendlyConsultationSuiteTests -v` |

Whole-node run (from repo root; this invocation style is verified working in this repo):
`PYTHONPATH=src python -m unittest tests.hive_cortex.test_no_cheating -v`

Edge cases baked into §3: every negative has an adjacent positive control so a fixture
cannot pass by breaking the surface entirely; tamper tests restore state before the
next assertion; all filesystem work uses `tempfile.TemporaryDirectory` (never the repo
tree); no network, no subprocesses, no git worktrees (deliberately avoid
`CuratorRuntime.verify` / `verify_exact_candidate`, which need real git repos).

## 6. Acceptance self-check → completion-receipt evidence

| Acceptance criterion | Demonstrated by | Receipt evidence |
|---|---|---|
| Every defined cheating class has a negative fixture | class→method matrix: test weakening (curator seal x2), evaluator leakage (x2), future access (harness + memory layer), stale evidence (artifact tamper + evidence-free appeal), fake receipts (builder x1 + tamper x1), authority expansion (x3), friendly consultation (x5) | `NO_CHEATING_RESULTS.md` matrix + `-v` transcript listing every method `ok` |
| Suspected cheating triggers a role council before continuation | `test_suspected_cheating_triggers_role_council_before_continuation` | transcript + receipt `class_map` entry |
| Confirmed cheating quarantines; disproved cites retained evidence | `test_confirmed_cheating_quarantines_and_disproved_cites_retained_evidence` (asserts `EVIDENCE_REF in result.evidence_refs`) | transcript + receipt entry |
| Same-model role labels never presented as independent humans | `test_role_labels_are_never_independent_humans` + court identity checks | transcript + receipt entry |

`evidence/autonomy/no-cheating/no_cheating_receipt.json` shape:
`{"node": "CHEAT-440", "base_commit": <sha>, "final_commit": <sha>,
"command": "PYTHONPATH=src python -m unittest tests.hive_cortex.test_no_cheating -v",
"outcome": "passed", "transcript_path": "test-transcript.txt",
"transcript_sha256": <hex>, "class_map": {<cheating class>: [<test ids>...]},
"changed_paths": [exactly the write_scope files touched], "rollback": "revert <final_commit>"}`.
Compute the digest portably:
`python -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" evidence/autonomy/no-cheating/test-transcript.txt`.
`docs/execution/NO_CHEATING_RESULTS.md`: title, node id, commit identities, the seven-row
class→fixture→kernel-surface matrix, the four suite commands with outcomes, and a
note that adverse fixtures are retained and must not be rewritten (contract rollback rule).

## 7. Out-of-scope traps (do NOT do)

- Do NOT create or edit any module under `src/` — if a kernel surface behaves
  differently than §2 states, that is evidence for `autopilot fail`, not a code fix.
- Do NOT touch `tests/hive_cortex/__init__.py`, `tests/hive_cortex/acceptance_harness.py`,
  `tests/hive_cortex/test_acceptance_harness.py`, or create
  `tests/hive_cortex/test_humanless_operation.py` (HUMANLESS-430 owns it).
- Do NOT write under `evidence/courts/**` (forbidden_scope) — this node's evidence goes
  ONLY under `evidence/autonomy/no-cheating/`.
- Do NOT import from sibling test modules (`from .test_acceptance_harness import ...`);
  re-declare the `_valid_run()` helper locally.
- Do NOT run `python -m unittest discover`, pytest, or any repo-wide runner; do not
  acquire the validation lease — that is the round integrator's job.
- Do NOT add fixtures that execute git, subprocesses, or the network; do not build
  fixtures under `tests/fixtures/**` (outside write_scope).
- Do NOT mark any expected-failure as `skip`/`expectedFailure` to force green; a
  fixture that cannot be made to pass honestly is an escalation.
- Do NOT rewrite, squash, or amend commits; do not delete or edit
  `evidence/autonomy/no-cheating/**` files once a run's receipt is committed —
  append a new receipt instead.
