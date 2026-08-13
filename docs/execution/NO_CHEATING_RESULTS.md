# No-cheating negative-fixture results

**Node:** CHEAT-440 — Negative-fixture proof of cheating detection
**Base commit:** `7ec26c540e211dfe06007259df90c2091c04034d`
**Final commit:** not yet created — this run was produced in the working tree; the node
receipt binds the transcript to the base commit above.
**Receipt:** `evidence/autonomy/no-cheating/no_cheating_receipt.json`
**Transcript:** `evidence/autonomy/no-cheating/test-transcript.txt`
(sha256 `ecca4dfa7c803e2adce5d689cb4938a94189bae6276744bae129bdf585ded8e9`)

This node writes tests and evidence only. It adds no kernel code and changes no
behavior. Every fixture constructs a real cheating attempt against a real kernel
surface and asserts the surface refuses it; every negative is paired with a positive
control so no fixture can pass by breaking the surface outright.

## Cheating class → fixture → kernel surface

| Cheating class | Attempt constructed by the fixture | Fixture | Kernel surface that refuses it |
|---|---|---|---|
| Test weakening | Replay a sealed acceptance digest after dropping a check; seal zero checks; pad the seal with a duplicate; convert a failed acceptance into `ADOPT` | `NoCheatingSuiteTests.test_test_weakening_tampered_seal_fails_closed`, `NoCheatingSuiteTests.test_test_weakening_cannot_convert_failure_into_adoption` | `brain_kernel/curator_runtime.py` — `BlindAcceptanceSeal.__post_init__`, `CuratorRuntime.seal_acceptance` (`CuratorVerificationError`) |
| Evaluator leakage | Compile an evaluator-mode context that includes the generator's `scratchpad` record and an `evaluator_visible=False` record | `EvaluatorLeakageSuiteTests.test_evaluator_mode_excludes_generator_material`, `EvaluatorLeakageSuiteTests.test_generator_manifest_never_claims_separation` | `brain_kernel/context.py` — `ContextCompiler._exclude_evaluator_material`, `excluded_categories["evaluator_isolation"]`, `generator_evaluator_separated` |
| Future access | Observe a commit outside the sealed set (and a declared future commit); rank memory whose `available_at` / `valid_from` is still in the future | `NoCheatingSuiteTests.test_future_access_observed_commits_must_be_sealed`, `EvaluatorLeakageSuiteTests.test_future_dated_memory_is_invisible_to_every_context` | `tests/hive_cortex/acceptance_harness.py` — `validate_run` (`future-leakage:*`); `brain_kernel/memory.py` — `MemoryCatalog._eligible` |
| Stale evidence | Rewrite a retained content-addressed artifact in place, then re-put the original body over the tampered file; appeal an adverse cheating verdict citing only evidence already ruled on | `NoCheatingSuiteTests.test_stale_evidence_rewritten_artifact_is_denied`, `NoCheatingSuiteTests.test_stale_evidence_appeal_without_new_evidence_is_rejected` | `brain_kernel/memory.py` — `MemoryArtifactStore.get`/`.put` (`MemoryDenied`); `brain_kernel/court_runtime.py` — `CourtHistory.append` appeal gate |
| Fake receipts | Present a failed regression suite as assurance evidence; omit a required receipt; repeat one receipt to fill the required set; edit a retained transcript; flip `release_ready` without rebuilding the digest | `NoCheatingSuiteTests.test_fake_receipts_fail_closed_in_report_builder`, `NoCheatingSuiteTests.test_fake_receipts_tampered_report_or_transcript_is_rejected` | `brain_kernel/local_assurance.py` — `build_local_assurance_report`, `verify_local_assurance_artifact` (`LocalAssuranceError`) |
| Authority expansion | Derive a child envelope that adds an action or widens the write scope; register a derived envelope without its parent; write outside scope, run a denied action, use an expired envelope, use a revoked envelope | `AuthorityExpansionSuiteTests.test_child_envelope_cannot_broaden_parent`, `.test_orphan_child_cannot_self_register`, `.test_registry_denies_scope_expansion_expiry_and_revocation` | `brain_kernel/authority.py` — `intersect_envelopes`, `AuthorityRegistry.register`/`.authorize` (`AuthorityDenied`) |
| Friendly consultation | Seat the requester on its own council; shrink the council to one role; testify twice as one role; recruit a role off the applicable route; self-consult and self-approve in the harness; relabel a same-model role as an independent human; pack a court with a duplicate identity, an affected judge, a non-adversarial cross-examiner, or an approving verdict over unresolved cheating | `FriendlyConsultationSuiteTests.test_requester_cannot_pack_its_own_council`, `.test_echo_chamber_testimony_is_rejected`, `.test_harness_flags_friendly_consultation`, `.test_role_labels_are_never_independent_humans`, `.test_friendly_court_is_structurally_impossible` | `brain_kernel/consultation.py` — `ConsultationRequest.__post_init__`, `evaluate_consultation`, `RoleAssessment.__post_init__`; `brain_kernel/court_runtime.py` — `_validate_panel`, `CourtParticipant.__post_init__`; `tests/hive_cortex/acceptance_harness.py` — `validate_run` |

Two further fixtures carry the remaining acceptance criteria rather than a distinct
cheating class:

| Acceptance criterion | Fixture | What it asserts |
|---|---|---|
| Suspected cheating triggers a role council before continuation | `NoCheatingSuiteTests.test_suspected_cheating_triggers_role_council_before_continuation` | One assessment raises `ValueError("human escalation is forbidden before two roles evaluate the question")`; a two-role council with no cheating vote returns `UNRESOLVED` + `QUARANTINE` and strips the roles' proposed answer, so the run cannot continue |
| Confirmed cheating quarantines; disproved cheating cites retained evidence | `NoCheatingSuiteTests.test_confirmed_cheating_quarantines_and_disproved_cites_retained_evidence` | `CONFIRMED` ⇒ `QUARANTINE`; `DISPROVED` resolves only with retained evidence and the reference survives into `result.evidence_refs`; evidence-free exoneration degrades to `UNRESOLVED` + `QUARANTINE`; a hand-written `CONFIRMED` + `RESOLVED` result raises `ValueError("confirmed cheating must quarantine")` |
| Same-model role labels are never presented as independent humans | `FriendlyConsultationSuiteTests.test_role_labels_are_never_independent_humans` | `identity_kind="independent_human"` and `identity_kind="human"` are both refused, and every `identity_record` in an adjudicated result — including its canonical document round-trip — stays in `{model_role, procedural_role}` |

## Suite commands and outcomes

`PYTHONPATH=src` is required in this environment: a bare `python -m unittest` resolves
`hive_mind_os` to an unrelated worktree
(`C:/Users/beesp/.codex/worktrees/1a44/hive-mind-os/src`) rather than this tree's `src/`.

| `required_tests` name | Command | Outcome |
|---|---|---|
| `no-cheating-suite` | `PYTHONPATH=src python -m unittest tests.hive_cortex.test_no_cheating.NoCheatingSuiteTests -v` | Ran 9 tests — OK |
| `evaluator-leakage-suite` | `PYTHONPATH=src python -m unittest tests.hive_cortex.test_no_cheating.EvaluatorLeakageSuiteTests -v` | Ran 3 tests — OK |
| `authority-expansion-suite` | `PYTHONPATH=src python -m unittest tests.hive_cortex.test_no_cheating.AuthorityExpansionSuiteTests -v` | Ran 3 tests — OK |
| `friendly-consultation-suite` | `PYTHONPATH=src python -m unittest tests.hive_cortex.test_no_cheating.FriendlyConsultationSuiteTests -v` | Ran 5 tests — OK |
| whole node | `PYTHONPATH=src python -m unittest tests.hive_cortex.test_no_cheating -v` | Ran 20 tests — OK |

## Retention

These are adverse fixtures. They exist to fail when a cheat succeeds, so they must not
be rewritten, relaxed, skipped, or marked `expectedFailure` to make a later run pass —
that edit would itself be the test-weakening cheat this node proves is detected. A
fixture that can no longer pass honestly is an escalation condition, not a fixture
defect. Evidence under `evidence/autonomy/no-cheating/` is append-only: add a new
receipt for a new run rather than editing a committed one.
