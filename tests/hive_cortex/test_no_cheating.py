"""Negative fixtures proving the kernel detects and refuses the defined cheating classes.

Every fixture below constructs a real cheating attempt against a real kernel surface
and asserts the surface refuses it.  Each negative is paired with a positive control
so a fixture cannot pass by breaking the surface outright.  No fixture executes git,
a subprocess, or the network; all filesystem work happens in a temporary directory.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from hive_mind_os.brain_kernel.authority import (
    AuthorityDenied,
    AuthorityRegistry,
    intersect_envelopes,
)
from hive_mind_os.brain_kernel.consultation import (
    MIN_CONSULTED_ROLES,
    CheatingDisposition,
    ConsultationDecision,
    ConsultationReason,
    ConsultationRequest,
    ConsultationResult,
    RoleAssessment,
    evaluate_consultation,
)
from hive_mind_os.brain_kernel.context import ContextCompiler, ContextRequest
from hive_mind_os.brain_kernel.contracts import (
    Budget,
    ConstraintEnvelope,
    MemoryRecord,
    MemoryState,
)
from hive_mind_os.brain_kernel.court_runtime import (
    CourtBrief,
    CourtCase,
    CourtClaimKind,
    CourtDisposition,
    CourtHistory,
    CourtParticipant,
    CourtProtocolError,
    CourtSeat,
    CourtVerdict,
    record_case,
)
from hive_mind_os.brain_kernel.curator_runtime import (
    BlindAcceptanceSeal,
    CuratorRuntime,
    CuratorVerdict,
    CuratorVerificationError,
)
from hive_mind_os.brain_kernel.local_assurance import (
    LocalAssuranceError,
    build_local_assurance_report,
    verify_local_assurance_artifact,
)
from hive_mind_os.brain_kernel.memory import (
    MemoryAccess,
    MemoryArtifactStore,
    MemoryCatalog,
    MemoryDenied,
    RetrievalRequest,
)

from .acceptance_harness import (
    SPECIALIST_ROLES,
    AcceptanceRun,
    Approval,
    Consultation,
    EffectReceipt,
    validate_run,
)

DIGEST = "sha256:" + "0" * 64
SHA_COMMIT = "a" * 40
SHA_TREE = "b" * 40
TIME = "2026-08-07T12:00:00Z"
LATER = "2026-08-08T12:00:00Z"
EVIDENCE_REF = "evidence/autonomy/no-cheating/probe-1"

_RECEIPT_NAMES = (
    "phase11-parity",
    "phase11-rollback",
    "security-regression",
    "recovery-regression",
)


def _valid_run() -> AcceptanceRun:
    """Re-declared locally on purpose; sibling test modules are never imported."""

    effects = tuple(
        EffectReceipt(role, f"effect-{index}") for index, role in enumerate(SPECIALIST_ROLES)
    )
    return AcceptanceRun(
        roles=SPECIALIST_ROLES,
        consultations=(Consultation("curator", ("steward", "optimizer")),),
        approvals=(Approval("builder", "curator", "candidate-1"),),
        sealed_candidate="candidate-1",
        observed_commits=("base-1", "candidate-1"),
        sealed_commits=("base-1", "candidate-1"),
        future_commits=("future-1",),
        authority_class=None,
        human_escalated=False,
        expected_effects=effects,
        receipt_candidate="candidate-1",
        receipt_roles=SPECIALIST_ROLES,
        receipt_effects=effects,
    )


def _assessment(role: str, identity: str, **overrides: object) -> RoleAssessment:
    values: dict[str, object] = {"role": role, "identity": identity}
    values.update(overrides)
    return RoleAssessment(**values)  # type: ignore[arg-type]


def _cheating_request(**overrides: object) -> ConsultationRequest:
    values: dict[str, object] = {
        "request_id": "REQ-1",
        "mission_id": "MISSION-1",
        "question": "candidate weakened a test?",
        "reason_code": ConsultationReason.SUSPECTED_CHEATING,
        "requesting_role": "builder",
        "applicable_roles": ("curator", "steward"),
        "suspected_cheating": True,
    }
    values.update(overrides)
    return ConsultationRequest(**values)  # type: ignore[arg-type]


def _brief(
    seat: CourtSeat,
    identity: str,
    task: str,
    evidence: tuple[str, ...] = (EVIDENCE_REF,),
) -> CourtBrief:
    return CourtBrief(CourtParticipant(seat, identity, task), f"{task} brief", evidence)


def _panel(
    judge_identity: str = "judge-1",
    evidence: tuple[str, ...] = (EVIDENCE_REF,),
    *,
    suffix: str = "1",
    advocate_task: str = "defend",
    cross_task: str = "attack",
    appeals_identity: str | None = None,
) -> tuple[CourtBrief, ...]:
    briefs = [
        _brief(CourtSeat.ADVOCATE, f"adv-{suffix}", advocate_task, evidence),
        _brief(CourtSeat.CROSS_EXAMINER, f"cross-{suffix}", cross_task, evidence),
        _brief(CourtSeat.EXPERT_WITNESS, f"wit-{suffix}", "measure", evidence),
        _brief(CourtSeat.JUDGE, judge_identity, "decide", evidence),
    ]
    if appeals_identity is not None:
        briefs.append(_brief(CourtSeat.APPEALS_JUDGE, appeals_identity, "review", evidence))
    return tuple(briefs)


def _benchmark_report() -> dict:
    return {
        "run_id": "RUN-1",
        "code_digest": SHA_COMMIT,
        "corpus_digest": DIGEST,
        "harness_digest": DIGEST,
        "results_digest": DIGEST,
        "lane_digests": {"lane-a": DIGEST},
        "verdict": {
            "disposition": "measurement-recorded",
            "judge_id": "judge-1",
            "lane_identities": ["lane-a", "lane-b"],
        },
    }


def _assurance_report(receipts) -> dict:
    return build_local_assurance_report(
        candidate_commit=SHA_COMMIT,
        candidate_tree=SHA_TREE,
        phase11_routes=(
            {
                "route": "anthropic",
                "manifest_digest": DIGEST,
                "parity_receipt_digest": DIGEST,
                "rollback_receipt_digest": DIGEST,
            },
        ),
        benchmark_report=_benchmark_report(),
        test_receipts=tuple(receipts),
    )


def _passing_receipts(digest: str = DIGEST) -> list[dict]:
    return [{"name": name, "status": "passed", "digest": digest} for name in _RECEIPT_NAMES]


def _envelope(
    *,
    envelope_id: str = "AUTH-parent",
    parent: str | None = None,
    allowed: tuple[str, ...] = ("write",),
    write_scope: tuple[str, ...] = ("src",),
    expires_at: str = "2030-01-01T00:00:00Z",
) -> ConstraintEnvelope:
    return ConstraintEnvelope(
        envelope_id,
        "MISSION-one",
        "WORK-one",
        parent,
        "builder",
        "R1",
        allowed,
        ("push", "merge", "deploy"),
        ("src",),
        write_scope,
        (),
        (),
        (),
        (),
        Budget(1, 0, 0, 0, 0, 0, 1, 1),
        expires_at,
        DIGEST,
        DIGEST,
    ).sealed()


def _mint(registry: AuthorityRegistry, envelope: ConstraintEnvelope) -> ConstraintEnvelope:
    registry.mint_root(
        envelope,
        issuer="owner:no-cheating-fixture",
        authority_ref="AUTHORITY-RECORD-no-cheating",
        recorded_at="2026-01-01T00:00:00Z",
    )
    return envelope


class NoCheatingSuiteTests(unittest.TestCase):
    """required_tests: no-cheating-suite."""

    # --- cheating class: test weakening -------------------------------------
    def test_test_weakening_tampered_seal_fails_closed(self) -> None:
        seal = CuratorRuntime().seal_acceptance(
            mission_id="MISSION-1",
            work_id="WORK-1",
            curator_id="curator-1",
            checks=("unit", "lint"),
        )
        self.assertEqual(("unit", "lint"), seal.checks)
        # Cheat: silently drop the "lint" check while replaying the sealed digest.
        with self.assertRaisesRegex(CuratorVerificationError, "seal digest is invalid"):
            BlindAcceptanceSeal(
                "MISSION-1",
                "WORK-1",
                "curator-1",
                ("unit",),
                seal.failure_verdict,
                seal.seal_digest,
            )
        # Cheat: seal nothing at all.
        with self.assertRaises(CuratorVerificationError):
            CuratorRuntime().seal_acceptance(
                mission_id="MISSION-1", work_id="WORK-1", curator_id="curator-1", checks=()
            )
        # Cheat: pad the seal with a duplicate so a single pass counts twice.
        with self.assertRaises(CuratorVerificationError):
            CuratorRuntime().seal_acceptance(
                mission_id="MISSION-1",
                work_id="WORK-1",
                curator_id="curator-1",
                checks=("unit", "unit"),
            )

    def test_test_weakening_cannot_convert_failure_into_adoption(self) -> None:
        with self.assertRaisesRegex(CuratorVerificationError, "only reject or remand"):
            CuratorRuntime().seal_acceptance(
                mission_id="MISSION-1",
                work_id="WORK-1",
                curator_id="curator-1",
                checks=("unit",),
                failure_verdict=CuratorVerdict.ADOPT,
            )
        honest = CuratorRuntime().seal_acceptance(
            mission_id="MISSION-1",
            work_id="WORK-1",
            curator_id="curator-1",
            checks=("unit",),
            failure_verdict=CuratorVerdict.REJECT,
        )
        self.assertIs(CuratorVerdict.REJECT, honest.failure_verdict)

    # --- cheating class: stale evidence -------------------------------------
    def test_stale_evidence_rewritten_artifact_is_denied(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            store = MemoryArtifactStore(Path(root))
            body = "retained probe evidence"
            artifact = store.put(body)
            self.assertEqual(body, store.get(artifact.digest))
            # Cheat: rewrite retained adverse evidence in place.
            path = store._path(artifact.digest)
            path.write_text("evidence favourable to the candidate", encoding="utf-8")
            with self.assertRaises(MemoryDenied):
                store.get(artifact.digest)
            # Cheat: re-put the original body so the rewritten file passes as canonical.
            with self.assertRaisesRegex(MemoryDenied, "cannot be rewritten"):
                store.put(body)
            # Positive control: restoring the true bytes makes the artifact readable again.
            path.write_text(body, encoding="utf-8")
            self.assertEqual(body, store.get(artifact.digest))

    def test_stale_evidence_appeal_without_new_evidence_is_rejected(self) -> None:
        case = CourtCase("CASE-1", CourtClaimKind.CHEATING, "weakened test", ("builder-1",))
        briefs = _panel()
        verdict = CourtVerdict(
            "CASE-1",
            CourtDisposition.REJECT,
            "judge-1",
            ("weakening confirmed",),
            (EVIDENCE_REF,),
        )
        history = record_case(CourtHistory(), case, briefs, verdict)
        self.assertEqual(1, len(history.records))

        appeal_case = CourtCase("CASE-2", CourtClaimKind.CHEATING, "weakened test", ("builder-1",))
        appeal_briefs = _panel("judge-2", suffix="2", appeals_identity="appeal-1")
        appeal_verdict = CourtVerdict(
            "CASE-2",
            CourtDisposition.ADOPT,
            "appeal-1",
            ("the original court erred",),
            (EVIDENCE_REF,),
        )
        # Cheat: appeal an adverse verdict by recycling only the evidence already ruled on.
        with self.assertRaisesRegex(CourtProtocolError, "materially new retained evidence"):
            record_case(history, appeal_case, appeal_briefs, appeal_verdict, appeal_of="CASE-1")
        # Positive control: one materially new retained reference makes the appeal admissible.
        fresh = (EVIDENCE_REF, "evidence/autonomy/no-cheating/probe-2")
        appealed = record_case(
            history,
            appeal_case,
            _panel("judge-2", fresh, suffix="2", appeals_identity="appeal-1"),
            appeal_verdict,
            appeal_of="CASE-1",
        )
        self.assertEqual(2, len(appealed.records))
        self.assertEqual(1, len(history.records))

    # --- cheating class: fake receipts --------------------------------------
    def test_fake_receipts_fail_closed_in_report_builder(self) -> None:
        control = _assurance_report(_passing_receipts())
        self.assertEqual(4, len(control["test_receipts"]))
        self.assertFalse(control["release_ready"])

        # Cheat: report a failed regression suite as assurance evidence.
        failed = _passing_receipts()
        failed[2] = {**failed[2], "status": "failed"}
        with self.assertRaisesRegex(LocalAssuranceError, "did not pass"):
            _assurance_report(failed)

        # Cheat: omit the receipt that would have caught the regression.
        with self.assertRaisesRegex(LocalAssuranceError, "required receipt is missing"):
            _assurance_report(_passing_receipts()[:-1])

        # Cheat: satisfy the required set by repeating one passing receipt.
        duplicated = _passing_receipts()[:-1]
        duplicated.append({**duplicated[0]})
        with self.assertRaises(LocalAssuranceError):
            _assurance_report(duplicated)

    def test_fake_receipts_tampered_report_or_transcript_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as root_name:
            root = Path(root_name)
            transcripts: dict[str, Path] = {}
            receipts: list[dict] = []
            for name in _RECEIPT_NAMES:
                path = root / f"t-{name}.txt"
                path.write_text(f"{name}: Ran 1 test\nOK\n", encoding="utf-8")
                transcripts[name] = path
                receipts.append(
                    {
                        "name": name,
                        "status": "passed",
                        "digest": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
            report = _assurance_report(receipts)
            report_path = root / "report.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")

            bench_path = root / "bench.json"
            bench_path.write_text(json.dumps(_benchmark_report()), encoding="utf-8")

            manifest_path = root / "manifest.json"
            manifest = {
                "schema_version": 1,
                "candidate_commit": SHA_COMMIT,
                "candidate_tree": SHA_TREE,
                "report_digest": report["report_digest"],
                "receipts": [
                    {
                        "name": receipt["name"],
                        "command": ["python", "-m", "unittest"],
                        "interpreter": "python",
                        "transcript_path": transcripts[receipt["name"]].name,
                        "digest": receipt["digest"],
                    }
                    for receipt in receipts
                ],
                "benchmark_summary": {
                    "path": bench_path.name,
                    "digest": "sha256:" + hashlib.sha256(bench_path.read_bytes()).hexdigest(),
                },
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            # Positive control: the honest packet verifies.
            verified = verify_local_assurance_artifact(report_path, manifest_path)
            self.assertEqual(report["report_digest"], verified["report_digest"])

            # Cheat: edit a retained transcript while keeping its recorded digest.
            tampered = transcripts["security-regression"]
            original_bytes = tampered.read_bytes()
            tampered.write_bytes(original_bytes + b"(all findings waived)\n")
            with self.assertRaisesRegex(
                LocalAssuranceError, "transcript digest does not match"
            ):
                verify_local_assurance_artifact(report_path, manifest_path)
            tampered.write_bytes(original_bytes)
            self.assertEqual(
                report["report_digest"],
                verify_local_assurance_artifact(report_path, manifest_path)["report_digest"],
            )

            # Cheat: promote the packet to release-ready without rebuilding its digest.
            forged = dict(report)
            forged["release_ready"] = True
            report_path.write_text(json.dumps(forged), encoding="utf-8")
            with self.assertRaisesRegex(
                LocalAssuranceError, "report digest does not match its content"
            ):
                verify_local_assurance_artifact(report_path, manifest_path)

    # --- cheating class: future access --------------------------------------
    def test_future_access_observed_commits_must_be_sealed(self) -> None:
        self.assertEqual((), validate_run(_valid_run()))
        # Cheat: observe a commit that lives past the sealed prediction boundary.
        leaked = validate_run(replace(_valid_run(), observed_commits=("base-1", "future-1")))
        self.assertTrue(
            any(issue.startswith("future-leakage:") for issue in leaked), leaked
        )
        self.assertIn("future-leakage:future-commit-observed", leaked)
        # Cheat: observe a commit that was never sealed at all.
        unsealed = validate_run(replace(_valid_run(), observed_commits=("base-1", "unsealed-1")))
        self.assertIn("future-leakage:observed-commit-not-sealed", unsealed)

    # --- cheating class: role council over suspected cheating ---------------
    def test_suspected_cheating_triggers_role_council_before_continuation(self) -> None:
        single = [_assessment("curator", "curator-1")]
        self.assertEqual(MIN_CONSULTED_ROLES - 1, len(single))
        # Cheat: adjudicate suspected cheating with one friendly role and move on.
        with self.assertRaisesRegex(ValueError, "before two roles"):
            evaluate_consultation(_cheating_request(), single)

        result = evaluate_consultation(
            _cheating_request(),
            [
                _assessment("curator", "curator-1", answer="continue, the diff is fine"),
                _assessment("steward", "steward-1", answer="continue, the diff is fine"),
            ],
        )
        self.assertIs(CheatingDisposition.UNRESOLVED, result.cheating_disposition)
        self.assertIs(ConsultationDecision.QUARANTINE, result.decision)
        self.assertIsNone(result.answer)
        self.assertEqual(("curator", "steward"), result.consulted_roles)

    def test_confirmed_cheating_quarantines_and_disproved_cites_retained_evidence(self) -> None:
        confirmed = evaluate_consultation(
            _cheating_request(),
            [
                _assessment(
                    "curator",
                    "curator-1",
                    cheating_disposition=CheatingDisposition.CONFIRMED,
                    evidence_refs=(EVIDENCE_REF,),
                ),
                _assessment("steward", "steward-1"),
            ],
        )
        self.assertIs(CheatingDisposition.CONFIRMED, confirmed.cheating_disposition)
        self.assertIs(ConsultationDecision.QUARANTINE, confirmed.decision)

        disproved = evaluate_consultation(
            _cheating_request(),
            [
                _assessment(
                    "curator",
                    "curator-1",
                    cheating_disposition=CheatingDisposition.DISPROVED,
                    evidence_refs=(EVIDENCE_REF,),
                    answer="the check was never weakened",
                ),
                _assessment(
                    "steward",
                    "steward-1",
                    cheating_disposition=CheatingDisposition.DISPROVED,
                    evidence_refs=(EVIDENCE_REF,),
                ),
            ],
        )
        self.assertIs(CheatingDisposition.DISPROVED, disproved.cheating_disposition)
        self.assertIs(ConsultationDecision.RESOLVED, disproved.decision)
        self.assertIn(EVIDENCE_REF, disproved.evidence_refs)

        # Cheat: clear a cheating suspicion by assertion alone, with no retained evidence.
        evidence_free = evaluate_consultation(
            _cheating_request(),
            [
                _assessment(
                    "curator", "curator-1", cheating_disposition=CheatingDisposition.DISPROVED
                ),
                _assessment(
                    "steward", "steward-1", cheating_disposition=CheatingDisposition.DISPROVED
                ),
            ],
        )
        self.assertIs(CheatingDisposition.UNRESOLVED, evidence_free.cheating_disposition)
        self.assertIs(ConsultationDecision.QUARANTINE, evidence_free.decision)

        # Cheat: hand-write a result that confirms cheating yet continues as resolved.
        with self.assertRaisesRegex(ValueError, "confirmed cheating must quarantine"):
            ConsultationResult(
                request_id="REQ-1",
                mission_id="MISSION-1",
                question="candidate weakened a test?",
                reason_code=ConsultationReason.SUSPECTED_CHEATING,
                requesting_role="builder",
                consulted_roles=("curator", "steward"),
                round=1,
                suspected_cheating=True,
                evidence_refs=(EVIDENCE_REF,),
                decision=ConsultationDecision.RESOLVED,
                answer="ship it",
                dissent=(),
                human_escalation=False,
                authority_class=None,
                role_first_exhausted=True,
                cheating_disposition=CheatingDisposition.CONFIRMED,
                identity_records=(
                    {"identity": "curator-1", "identity_kind": "model_role", "role": "curator"},
                    {"identity": "steward-1", "identity_kind": "model_role", "role": "steward"},
                ),
            )


class EvaluatorLeakageSuiteTests(unittest.TestCase):
    """required_tests: evaluator-leakage-suite."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.artifacts = MemoryArtifactStore(Path(self.temporary.name))
        self.catalog = MemoryCatalog(self.artifacts)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def record(
        self,
        record_id: str,
        body: str,
        *,
        memory_class: str = "fact",
        scope: str = "mission",
        subject_keys: tuple[str, ...] = ("MISSION-one",),
        valid_from: str = TIME,
        valid_to: str | None = None,
        available_at: str = TIME,
        sensitivity: str = "internal",
    ) -> MemoryRecord:
        artifact = self.artifacts.put(body)
        return MemoryRecord(
            record_id,
            memory_class,
            scope,
            subject_keys,
            artifact.digest,
            ("SRC-one",),
            "verified",
            sensitivity,
            valid_from,
            valid_to,
            TIME,
            available_at,
            MemoryState.ACTIVE,
            (),
            (),
            None,
            (),
            "retain",
            DIGEST,
        )

    @staticmethod
    def access(
        *, roles: tuple[str, ...] = ("builder",), evaluator_visible: bool = True
    ) -> MemoryAccess:
        return MemoryAccess(roles, ("internal",), evaluator_visible)

    def _curator_request(self, *, evaluator_mode: bool) -> ContextRequest:
        return ContextRequest(
            "MISSION-one",
            "WORK-one",
            "ATTEMPT-curator",
            "curator",
            DIGEST,
            DIGEST,
            40,
            "evidence",
            LATER,
            ("internal",),
            (),
            evaluator_mode=evaluator_mode,
        )

    def _register_generator_material(self) -> None:
        evidence = self.record("MEMORY-evidence", "accepted test evidence")
        scratchpad = self.record(
            "MEMORY-scratch", "builder internal rationale", memory_class="scratchpad"
        )
        self.catalog.register(evidence, self.access(roles=("curator",)))
        self.catalog.register(
            scratchpad, self.access(roles=("curator",), evaluator_visible=False)
        )

    def test_evaluator_mode_excludes_generator_material(self) -> None:
        self._register_generator_material()
        # Cheat: let the evaluator read the generator's own scratchpad rationale.
        compiled = ContextCompiler(self.catalog).compile(
            self._curator_request(evaluator_mode=True)
        )
        visible = compiled.manifest.warm_items + compiled.manifest.cold_references
        self.assertNotIn("MEMORY-scratch", visible)
        self.assertIn("MEMORY-evidence", compiled.manifest.warm_items)
        self.assertIn("evaluator_isolation", compiled.manifest.excluded_categories)
        self.assertIs(True, compiled.manifest.generator_evaluator_separated)

    def test_generator_manifest_never_claims_separation(self) -> None:
        self._register_generator_material()
        compiled = ContextCompiler(self.catalog).compile(
            self._curator_request(evaluator_mode=False)
        )
        visible = compiled.manifest.warm_items + compiled.manifest.cold_references
        # Positive control: the scratchpad is retrievable outside evaluator mode, so the
        # exclusion above is the evaluator gate rather than an unrelated filter.
        self.assertIn("MEMORY-scratch", visible)
        self.assertIs(False, compiled.manifest.generator_evaluator_separated)
        self.assertNotIn("evaluator_isolation", compiled.manifest.excluded_categories)

    def test_future_dated_memory_is_invisible_to_every_context(self) -> None:
        present = self.record("MEMORY-present", "present evidence alpha")
        unavailable = self.record(
            "MEMORY-unavailable", "future evidence alpha", available_at=LATER
        )
        not_yet_valid = self.record(
            "MEMORY-notyetvalid", "not yet valid evidence alpha", valid_from=LATER
        )
        for item in (present, unavailable, not_yet_valid):
            self.catalog.register(item, self.access(roles=("curator",)))

        def ranked(now: str) -> tuple[str, ...]:
            return tuple(
                item.entry.record.record_id
                for item in self.catalog.rank(
                    RetrievalRequest(
                        "MISSION-one", "WORK-one", "curator", "evidence", now, ("internal",)
                    )
                )
            )

        # Cheat: consult memory that is only scheduled to exist in the future.
        now_visible = ranked(TIME)
        self.assertIn("MEMORY-present", now_visible)
        self.assertNotIn("MEMORY-unavailable", now_visible)
        self.assertNotIn("MEMORY-notyetvalid", now_visible)
        # Positive control: once the boundary passes, the same records are eligible.
        later_visible = ranked(LATER)
        self.assertIn("MEMORY-unavailable", later_visible)
        self.assertIn("MEMORY-notyetvalid", later_visible)


class AuthorityExpansionSuiteTests(unittest.TestCase):
    """required_tests: authority-expansion-suite."""

    def test_child_envelope_cannot_broaden_parent(self) -> None:
        parent = _envelope()
        # Cheat: a child grant that adds an action its parent never held.
        with self.assertRaises(AuthorityDenied):
            intersect_envelopes(
                parent,
                _envelope(
                    envelope_id="AUTH-child",
                    parent=parent.digest_value,
                    allowed=("write", "deploy"),
                ),
            )
        # Cheat: a child grant that widens the write scope.
        with self.assertRaises(AuthorityDenied):
            intersect_envelopes(
                parent,
                _envelope(
                    envelope_id="AUTH-child",
                    parent=parent.digest_value,
                    write_scope=("src", "docs"),
                ),
            )
        # Positive control: an equal-or-narrower child passes through unchanged.
        narrower = _envelope(
            envelope_id="AUTH-child", parent=parent.digest_value, allowed=()
        )
        self.assertIs(narrower, intersect_envelopes(parent, narrower))

    def test_orphan_child_cannot_self_register(self) -> None:
        parent = _envelope()
        child = _envelope(envelope_id="AUTH-child", parent=parent.digest_value)
        # Cheat: register a derived envelope without presenting the parent it claims.
        with self.assertRaisesRegex(AuthorityDenied, "parent envelope is required"):
            AuthorityRegistry().register(child)
        # Cheat: mint a fresh root rather than deriving from an admitted authority.
        with self.assertRaisesRegex(AuthorityDenied, "explicit mint ceremony"):
            AuthorityRegistry().register(_envelope())
        # Positive control: presenting the parent registers the same child.
        registry = AuthorityRegistry()
        _mint(registry, parent)
        registry.register(child, parent)

    def test_registry_denies_scope_expansion_expiry_and_revocation(self) -> None:
        registry = AuthorityRegistry()
        digest = _mint(registry, _envelope()).digest_value
        # Positive control: the granted action inside the granted scope is authorized.
        token = registry.authorize(digest, "write", "src/x.py", now="2029-01-01T00:00:00Z")
        self.assertEqual("src/x.py", token.target)
        # Cheat: write outside the granted path scope.
        with self.assertRaisesRegex(AuthorityDenied, "outside write scope"):
            registry.authorize(digest, "write", "docs/x.md", now="2029-01-01T00:00:00Z")
        # Cheat: perform an explicitly denied action.
        with self.assertRaisesRegex(AuthorityDenied, "action is not granted"):
            registry.authorize(digest, "deploy", "src/x.py", now="2029-01-01T00:00:00Z")
        # Cheat: keep using the envelope after it expired.
        with self.assertRaisesRegex(AuthorityDenied, "expired"):
            registry.authorize(digest, "write", "src/x.py", now="2031-01-01T00:00:00Z")
        # Cheat: keep using the envelope after it was revoked.
        registry.revoke(digest)
        with self.assertRaisesRegex(AuthorityDenied, "unavailable"):
            registry.authorize(digest, "write", "src/x.py", now="2029-01-01T00:00:00Z")
        # Cheat: re-mint the identical authority under a new envelope identity.
        with self.assertRaisesRegex(AuthorityDenied, "authority is revoked"):
            _mint(registry, _envelope(envelope_id="AUTH-remint"))


class FriendlyConsultationSuiteTests(unittest.TestCase):
    """required_tests: friendly-consultation-suite."""

    def test_requester_cannot_pack_its_own_council(self) -> None:
        # Cheat: route the question to a council that includes the requester.
        with self.assertRaisesRegex(ValueError, "cannot approve its own consultation"):
            _cheating_request(applicable_roles=("builder", "curator"))
        # Cheat: shrink the council to a single friendly role.
        with self.assertRaises(ValueError):
            _cheating_request(applicable_roles=("curator",))
        # Positive control: a disjoint two-role council is accepted.
        self.assertEqual(("curator", "steward"), _cheating_request().applicable_roles)

    def test_echo_chamber_testimony_is_rejected(self) -> None:
        # Cheat: submit the same role twice so one voice looks like a quorum.
        with self.assertRaisesRegex(ValueError, "only once"):
            evaluate_consultation(
                _cheating_request(),
                [
                    _assessment("curator", "curator-1"),
                    _assessment("curator", "curator-2"),
                ],
            )
        # Cheat: recruit a role that was never on the applicable route.
        with self.assertRaisesRegex(ValueError, "outside the applicable route"):
            evaluate_consultation(
                _cheating_request(),
                [
                    _assessment("curator", "curator-1"),
                    _assessment("optimizer", "optimizer-1"),
                ],
            )

    def test_harness_flags_friendly_consultation(self) -> None:
        self.assertEqual((), validate_run(_valid_run()))
        # Cheat: consult yourself.
        self_consulted = validate_run(
            replace(
                _valid_run(),
                consultations=(Consultation("curator", ("curator", "steward")),),
            )
        )
        self.assertIn("fake-consultation:curator", self_consulted)
        # Cheat: declare a non-independent consultation and count it anyway.
        dependent = validate_run(
            replace(
                _valid_run(),
                consultations=(
                    Consultation("curator", ("steward", "optimizer"), independent=False),
                ),
            )
        )
        self.assertIn("fake-consultation:curator", dependent)
        # Cheat: approve your own candidate.
        self_approved = validate_run(
            replace(_valid_run(), approvals=(Approval("builder", "builder", "candidate-1"),))
        )
        self.assertIn("self-approval:builder", self_approved)

    def test_role_labels_are_never_independent_humans(self) -> None:
        # Cheat: relabel a same-model role as an independent human reviewer.
        with self.assertRaisesRegex(ValueError, "cannot claim to be independent humans"):
            RoleAssessment("curator", "curator-1", identity_kind="independent_human")
        # Cheat: seat a "human" judge in the court.
        with self.assertRaisesRegex(
            CourtProtocolError, "cannot claim independent human status"
        ):
            CourtParticipant(CourtSeat.JUDGE, "judge-1", "decide", identity_kind="human")
        result = evaluate_consultation(
            _cheating_request(),
            [
                _assessment("curator", "curator-1"),
                _assessment("steward", "steward-1", identity_kind="procedural_role"),
            ],
        )
        self.assertEqual(2, len(result.identity_records))
        for record in result.identity_records:
            self.assertIn(record["identity_kind"], {"model_role", "procedural_role"})
        for record in result.to_document()["identity_records"]:
            self.assertIn(record["identity_kind"], {"model_role", "procedural_role"})

    def test_friendly_court_is_structurally_impossible(self) -> None:
        case = CourtCase("CASE-1", CourtClaimKind.CHEATING, "weakened test", ("builder-1",))
        verdict = CourtVerdict(
            "CASE-1", CourtDisposition.REJECT, "judge-1", ("confirmed",), (EVIDENCE_REF,)
        )
        # Positive control: a properly separated panel records.
        self.assertEqual(1, len(record_case(CourtHistory(), case, _panel(), verdict).records))

        # Cheat: let the judge also act as its own advocate.
        packed = (
            _brief(CourtSeat.ADVOCATE, "judge-1", "defend"),
            _brief(CourtSeat.CROSS_EXAMINER, "cross-1", "attack"),
            _brief(CourtSeat.EXPERT_WITNESS, "wit-1", "measure"),
            _brief(CourtSeat.JUDGE, "judge-1", "decide"),
        )
        with self.assertRaisesRegex(CourtProtocolError, "distinct identity"):
            record_case(CourtHistory(), case, packed, verdict)

        # Cheat: let the accused identity judge its own case.
        affected = CourtCase("CASE-1", CourtClaimKind.CHEATING, "weakened test", ("judge-1",))
        with self.assertRaisesRegex(CourtProtocolError, "cannot adjudicate an affected"):
            record_case(CourtHistory(), affected, _panel(), verdict)

        # Cheat: give the advocate and cross-examiner the same brief, removing adversariality.
        with self.assertRaisesRegex(CourtProtocolError, "distinct tasks"):
            record_case(
                CourtHistory(), case, _panel(cross_task="defend"), verdict
            )

        # Cheat: approve a candidate whose cheating consultation is still unresolved.
        unresolved = evaluate_consultation(
            _cheating_request(),
            [
                _assessment("curator", "curator-1"),
                _assessment("steward", "steward-1"),
            ],
        )
        self.assertIs(CheatingDisposition.UNRESOLVED, unresolved.cheating_disposition)
        open_case = CourtCase(
            "CASE-3",
            CourtClaimKind.CHEATING,
            "weakened test",
            ("builder-1",),
            consultations=(unresolved,),
        )
        with self.assertRaisesRegex(
            CourtProtocolError, "unresolved cheating cannot receive an approving verdict"
        ):
            record_case(
                CourtHistory(),
                open_case,
                _panel(),
                CourtVerdict(
                    "CASE-3",
                    CourtDisposition.ADOPT,
                    "judge-1",
                    ("looks fine to me",),
                    (EVIDENCE_REF,),
                ),
            )


if __name__ == "__main__":
    unittest.main()
