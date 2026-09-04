from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from hive_mind_os.brain_kernel.artifacts import ArtifactStore
from hive_mind_os.brain_kernel.canonical import canonical_bytes, canonical_digest
from hive_mind_os.brain_kernel.challenger_runtime import (
    ChallengerFinding,
    ChallengerRuntimeError,
    KeepPromotionUnsupportedError,
    PlannedSurface,
    V2ChallengerRuntime,
    V2PromotionDisposition,
)
from hive_mind_os.brain_kernel.court_runtime import (
    CourtBrief,
    CourtCase,
    CourtClaimKind,
    CourtDisposition,
    CourtHistory,
    CourtParticipant,
    CourtSeat,
    CourtVerdict,
    record_case,
)
from hive_mind_os.brain_kernel.evaluation_authority import (
    BoundSurfaceEvidence,
    canonical_holdout_commitment,
    load_evaluation_authority_manifest,
    store_bound_surface_evidence,
)
from hive_mind_os.brain_kernel.evaluation_runtime import (
    EvaluationRuntime,
    EvaluationVerdict,
    SealedHoldout,
    SurfaceKind,
    SurfaceResult,
)
from hive_mind_os.brain_kernel.promotion import PromotionAuthority
from hive_mind_os.brain_kernel.qualification import (
    EvidenceKind,
    EvidenceReceipt,
    ExecutionMode,
    IssuerAuthority,
    QualificationLevel,
    QualificationRequest,
    qualify_claim,
)
from hive_mind_os.ledger import EvidenceLedger
from hive_mind_os.models import Role
from hive_mind_os.prompt_registry import (
    PromptRegistry,
    generation_zero_prompt,
)
from hive_mind_os.roles import ROLE_CONTRACTS

NOW = "2030-01-02T00:00:00+00:00"
EXPIRY = "2030-01-03T00:00:00+00:00"


def _clock() -> str:
    return NOW


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


class _RuntimeCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.repository = self.root / "source"
        self.repository.mkdir()
        _git(self.repository, "init", "--quiet")
        _git(self.repository, "config", "user.name", "Tournament Test")
        _git(self.repository, "config", "user.email", "test@example.invalid")
        _git(self.repository, "config", "core.autocrlf", "false")
        (self.repository / "source.txt").write_text("sealed source\n", encoding="utf-8")
        _git(self.repository, "add", "source.txt")
        _git(self.repository, "commit", "--quiet", "-m", "sealed source")
        self.head = _git(self.repository, "rev-parse", "HEAD^{commit}")
        self.tree = _git(self.repository, "rev-parse", "HEAD^{tree}")

        self.run_root = self.root / "run"
        self.run_root.mkdir()
        self.registry_root = self.run_root / "registry"
        self.ledger = EvidenceLedger(":memory:")
        self.registry = PromptRegistry(self.registry_root, ledger=self.ledger)
        self.addCleanup(self.registry.close)
        self.addCleanup(self.ledger.close)
        prompt_root = self.root / "generation-zero"
        prompt_root.mkdir()
        for role in Role:
            (prompt_root / f"{role.value}.txt").write_text(
                generation_zero_prompt(ROLE_CONTRACTS[role]), encoding="utf-8"
            )
        self.champions = self.registry.bootstrap(prompt_root)
        self.pointer_before = self.registry.pointer_path.read_bytes()
        self.source_before = (self.repository / "source.txt").read_bytes()

        self.store = ArtifactStore(self.run_root / "artifact-store")
        self.evaluation_runtime = EvaluationRuntime()
        self.holdout_cases = {
            "case-a": {"expected": "repair-regression"},
            "case-b": {"expected": "preserve-safety"},
        }
        self.authority_root = self.root / "authority"
        self.authority_root.mkdir()
        self.manifest_path = self.authority_root / "evaluation-authority.json"
        document: dict[str, object] = {
            "schema_id": "hive-mind-os/evaluation-authority",
            "schema_version": 1,
            "authority_id": "authority:test-v2",
            "repository": {"head_commit": self.head, "tree_oid": self.tree},
            "role_champions": self.champions,
            "evaluation": {
                "contract_fingerprint": self.evaluation_runtime.contract.fingerprint,
                "harness_fingerprint": canonical_digest({"harness": "test-v2"}),
            },
            "holdout": {
                "holdout_id": "holdout:test-v2",
                "commitment": canonical_holdout_commitment(
                    "holdout:test-v2", self.holdout_cases
                ),
            },
            "comparators": [
                {
                    "comparator_id": "comparator:baseline-a",
                    "pin": canonical_digest({"baseline": "a", "version": 1}),
                    "license": "MIT",
                },
                {
                    "comparator_id": "comparator:baseline-b",
                    "pin": canonical_digest({"baseline": "b", "version": 3}),
                    "license": "Apache-2.0",
                },
            ],
            "identities": {
                "proposer_id": "optimizer:proposer",
                "builder_id": "builder:isolated",
                "evaluator_id": "curator:evaluator",
                "judge_id": "judge:independent",
            },
            "budgets": {
                "max_generations": 2,
                "max_candidates": 4,
                "max_evaluations": 4,
                "max_surface_receipts": 8,
                "max_prompt_bytes": 100_000,
                "max_wall_seconds": 3_600,
            },
            "validity": {
                "not_before": "2030-01-01T00:00:00+00:00",
                "expires_at": EXPIRY,
            },
        }
        document["manifest_digest"] = canonical_digest(document)
        self.manifest_path.write_bytes(canonical_bytes(document) + b"\n")
        self.manifest = load_evaluation_authority_manifest(
            self.manifest_path,
            expected_digest=str(document["manifest_digest"]),
            repository_root=self.repository,
            candidate_root=self.registry_root,
            run_root=self.run_root,
            as_of=NOW,
        )
        self.promotion = PromotionAuthority(self.registry)
        self.runtime = V2ChallengerRuntime(
            manifest=self.manifest,
            repository_root=self.repository,
            run_root=self.run_root,
            registry=self.registry,
            artifact_store=self.store,
            promotion_authority=self.promotion,
            evaluation_runtime=self.evaluation_runtime,
            now=_clock,
        )
        self.planned = tuple(
            PlannedSurface(kind=kind, name=f"{kind.value}-surface")
            for kind in SurfaceKind
        )
        self.issuer_authorities = (
            IssuerAuthority(
                issuer_id=self.manifest.identities.evaluator_id,
                trust_domain="independent-curator",
                evidence_kinds=(EvidenceKind.STRUCTURAL,),
            ),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def finding(
        self,
        finding_id: str = "finding:optimizer-1",
        *,
        evidence_refs: tuple[str, ...] = ("evidence:run-1", "evidence:failure-1"),
    ) -> ChallengerFinding:
        return ChallengerFinding(
            finding_id=finding_id,
            role=Role.OPTIMIZER.value,
            source_episode_id="episode:failed-1",
            summary="optimizer promoted before independent verification",
            error_class="premature_promotion",
            proposed_change="require an explicit independent evidence checkpoint",
            falsifier=(
                "held-out success fails to exceed noise or any hard guardrail regresses"
            ),
            evidence_refs=evidence_refs,
            owner_id=self.manifest.identities.proposer_id,
            expires_at="2030-12-31T00:00:00+00:00",
        )

    def prepare(self, finding: ChallengerFinding | None = None):
        proposal = self.runtime.propose(finding or self.finding())
        holdout = SealedHoldout(
            self.manifest.holdout_id,
            self.holdout_cases,
        )
        plan = self.runtime.seal_evaluation(
            proposal,
            holdout=holdout,
            prediction={"expected_verdict": "retest", "risk": "guardrail"},
            surfaces=self.planned,
        )
        materialized = self.runtime.materialize(proposal, plan, holdout=holdout)
        return proposal, holdout, plan, materialized

    def make_surfaces(
        self,
        materialized,
        plan,
        *,
        held_out=((0.5, 0.5, 0.5), (0.8, 0.8, 0.8)),
        candidate_digest: str | None = None,
    ) -> tuple[BoundSurfaceEvidence, ...]:
        pairs = {
            SurfaceKind.HELD_OUT: held_out,
            SurfaceKind.PIT: ((0.6, 0.6, 0.6), (0.65, 0.65, 0.65)),
            SurfaceKind.ADVERSARIAL: ((0.9, 0.9, 0.9), (0.9, 0.9, 0.9)),
            SurfaceKind.COMPARATOR: ((0.7, 0.7, 0.7), (0.72, 0.72, 0.72)),
        }
        result: list[BoundSurfaceEvidence] = []
        for kind in SurfaceKind:
            raw = (
                self.run_root
                / "raw"
                / (f"g{materialized.binding.generation}-{kind.value}.log")
            )
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_text(f"surface={kind.value}\n", encoding="utf-8")
            raw_ref = f"{raw.as_posix()}#sha256:{sha256(raw.read_bytes()).hexdigest()}"
            surface = SurfaceResult(
                kind,
                f"{kind.value}-surface",
                pairs[kind][0],
                pairs[kind][1],
                (raw_ref,),
            )
            comparator = self.manifest.comparators[0]
            comparator_id = (
                comparator.comparator_id if kind is SurfaceKind.COMPARATOR else None
            )
            comparator_pin = comparator.pin if kind is SurfaceKind.COMPARATOR else None
            result.append(
                store_bound_surface_evidence(
                    self.store,
                    surface=surface,
                    receipt_id=(
                        f"receipt:g{materialized.binding.generation}:{kind.value}"
                    ),
                    claim_id=materialized.proposal.hypothesis.hypothesis_id,
                    candidate_digest=(
                        materialized.binding.candidate_digest
                        if candidate_digest is None
                        else candidate_digest
                    ),
                    parent_champion_digest=materialized.binding.parent_champion_digest,
                    authority_manifest_digest=self.manifest.manifest_digest,
                    evaluation_plan_digest=plan.plan_digest,
                    generation=materialized.binding.generation,
                    evaluator_id=self.manifest.identities.evaluator_id,
                    evaluator_trust_domain="independent-curator",
                    repository_head=self.manifest.repository_head,
                    repository_tree=self.manifest.repository_tree,
                    contract_fingerprint=self.manifest.contract_fingerprint,
                    harness_fingerprint=self.manifest.harness_fingerprint,
                    holdout_commitment=self.manifest.holdout_commitment,
                    observed_at=NOW,
                    expires_at=EXPIRY,
                    evidence_kind=EvidenceKind.STRUCTURAL,
                    execution_mode=ExecutionMode.LOCAL,
                    prior_outcome_digest=plan.prior_outcome_digest,
                    comparator_id=comparator_id,
                    comparator_pin=comparator_pin,
                )
            )
        return tuple(result)

    def evaluate(
        self,
        materialized,
        plan,
        holdout,
        surfaces,
        *,
        qualification_receipts=(),
        issuer_authorities=None,
        target_level=QualificationLevel.STRUCTURAL,
        as_of=NOW,
    ):
        holdout.reveal(plan.holdout_seal)
        return self.runtime.evaluate(
            materialized,
            plan,
            holdout=holdout,
            surfaces=surfaces,
            qualification_receipts=qualification_receipts,
            issuer_authorities=(
                self.issuer_authorities
                if issuer_authorities is None
                else issuer_authorities
            ),
            candidate_trust_domain="optimizer-domain",
            target_level=target_level,
            as_of=as_of,
        )

    def court(self, outcome, disposition: CourtDisposition) -> tuple[CourtHistory, str]:
        case_id = f"court:{outcome.outcome_digest[7:19]}"
        affected = (
            self.manifest.identities.proposer_id,
            self.manifest.identities.builder_id,
            self.manifest.identities.evaluator_id,
        )
        case = CourtCase(
            case_id=case_id,
            claim_kind=(
                CourtClaimKind.SUPERIORITY
                if outcome.verdict is EvaluationVerdict.KEEP
                else CourtClaimKind.ORDINARY
            ),
            subject=outcome.materialized.binding.candidate_digest,
            affected_identities=affected,
        )
        participants = (
            CourtParticipant(CourtSeat.ADVOCATE, "advocate:one", "make case"),
            CourtParticipant(
                CourtSeat.CROSS_EXAMINER, "cross:one", "seek counterexample"
            ),
            CourtParticipant(CourtSeat.EXPERT_WITNESS, "expert:one", "test evidence"),
            CourtParticipant(
                CourtSeat.JUDGE,
                self.manifest.identities.judge_id,
                "adjudicate evidence",
            ),
        )
        evidence_ref = f"outcome:{outcome.outcome_digest}"
        briefs = tuple(
            CourtBrief(
                participant=participant,
                conclusion=f"{participant.seat.value} conclusion",
                evidence_refs=(evidence_ref,),
            )
            for participant in participants
        )
        verdict = CourtVerdict(
            case_id=case_id,
            disposition=disposition,
            decided_by=self.manifest.identities.judge_id,
            reasons=outcome.reasons,
            evidence_refs=(evidence_ref,),
            dissent=("cross-examiner preserved uncertainty",),
        )
        return record_case(CourtHistory(), case, briefs, verdict), case_id


class SealedChallengerFlowTests(_RuntimeCase):
    def test_generation_one_seals_before_materialization_and_keeps_pointer_immutable(
        self,
    ) -> None:
        proposal, holdout, plan, materialized = self.prepare()

        self.assertEqual(1, proposal.hypothesis.generation)
        self.assertIn("expected effect", proposal.hypothesis.statement)
        self.assertIn("guardrail", proposal.hypothesis.falsifier)
        self.assertIsNone(holdout.ordering["reveal_sequence"])
        plan_document = json.loads(plan.record_path.read_text(encoding="utf-8"))
        self.assertNotIn(
            "expected_verdict", plan.record_path.read_text(encoding="utf-8")
        )
        self.assertEqual(
            self.manifest.holdout_commitment, plan_document["holdout_commitment"]
        )
        self.assertEqual(
            self.champions[Role.OPTIMIZER.value],
            materialized.binding.parent_champion_digest,
        )
        self.assertNotEqual(
            materialized.binding.candidate_digest,
            materialized.binding.parent_champion_digest,
        )
        self.assertEqual(self.pointer_before, self.registry.pointer_path.read_bytes())
        self.assertEqual(
            self.source_before, (self.repository / "source.txt").read_bytes()
        )
        self.assertEqual(
            [],
            [
                item
                for item in self.registry.lineage(materialized.binding.candidate_digest)
                if item.get("kind") == "promotion"
            ],
        )

    def test_keep_is_retained_but_v2_promotion_is_typed_defer(self) -> None:
        _proposal, holdout, plan, materialized = self.prepare()
        surfaces = self.make_surfaces(materialized, plan)
        outcome = self.evaluate(materialized, plan, holdout, surfaces)

        self.assertEqual(EvaluationVerdict.KEEP, outcome.verdict)
        self.assertEqual(
            V2PromotionDisposition.DEFER_UNSUPPORTED,
            outcome.promotion_disposition,
        )
        self.assertTrue(outcome.record_path.is_file())
        self.assertIsNotNone(outcome.evaluation_record)
        self.assertIsNotNone(outcome.qualification)
        assert outcome.evaluation_record is not None
        assert outcome.qualification is not None
        self.assertTrue(outcome.evaluation_record.record_path.is_file())
        self.assertTrue(outcome.qualification.qualified)
        self.assertEqual(
            QualificationLevel.STRUCTURAL, outcome.qualification.target_level
        )
        self.assertEqual(
            self.champions[Role.OPTIMIZER.value],
            self.registry.champion_digest(Role.OPTIMIZER),
        )
        history, case_id = self.court(outcome, CourtDisposition.ADOPT)
        with self.assertRaisesRegex(
            KeepPromotionUnsupportedError, "externally attestable"
        ) as raised:
            self.runtime.submit_appeal(
                outcome,
                court_history=history,
                court_case_id=case_id,
                decision_id="decision:unsupported-v2-keep",
            )
        self.assertEqual(
            V2PromotionDisposition.DEFER_UNSUPPORTED,
            raised.exception.disposition,
        )
        self.assertEqual((), self.promotion.log.decisions)
        self.assertEqual(
            self.champions[Role.OPTIMIZER.value],
            self.registry.champion_digest(Role.OPTIMIZER),
        )

    def test_caller_forged_nonexistent_qualification_cannot_reach_promotion(
        self,
    ) -> None:
        _proposal, holdout, plan, materialized = self.prepare()
        kinds = (
            EvidenceKind.BOUNDED_LOCAL,
            EvidenceKind.CONTROL_PLANE,
            EvidenceKind.FULL_SUITE,
            EvidenceKind.PROVIDER_BACKED,
            EvidenceKind.INDEPENDENT_E2E,
            EvidenceKind.PRODUCTION,
            EvidenceKind.SUPERIORITY,
            EvidenceKind.SUPERIORITY,
            EvidenceKind.SUPERIORITY,
            EvidenceKind.SUPERIORITY,
        )
        forged_issuer = "caller:forged-laboratory"
        forged_domain = "caller-controlled"
        nonexistent_digests = tuple(
            canonical_digest({"nonexistent-artifact": index})
            for index in range(len(kinds))
        )
        forged_budget = canonical_digest({"caller-selected-budget": "arbitrary"})
        forged_receipts = tuple(
            EvidenceReceipt(
                receipt_id=f"forged:qualification:{index}",
                claim_id=materialized.proposal.hypothesis.hypothesis_id,
                candidate_digest=materialized.binding.candidate_digest,
                evidence_kind=kind,
                passed=True,
                issuer_id=forged_issuer,
                issuer_trust_domain=forged_domain,
                observed_at=NOW,
                expires_at=EXPIRY,
                artifact_digest=nonexistent_digests[index],
                execution_mode=(
                    ExecutionMode.PRODUCTION
                    if kind is EvidenceKind.PRODUCTION
                    else ExecutionMode.PROVIDER
                ),
                strict=kind in {EvidenceKind.CONTROL_PLANE, EvidenceKind.FULL_SUITE},
                comparator_digest=(
                    canonical_digest(
                        {"unauthorized-comparator": ("a" if index in {6, 7} else "b")}
                    )
                    if kind is EvidenceKind.SUPERIORITY
                    else None
                ),
                budget_digest=(
                    forged_budget if kind is EvidenceKind.SUPERIORITY else None
                ),
                run_id=(
                    f"caller-selected-run:{index}"
                    if kind is EvidenceKind.SUPERIORITY
                    else None
                ),
            )
            for index, kind in enumerate(kinds)
        )
        caller_authority = IssuerAuthority(
            issuer_id=forged_issuer,
            trust_domain=forged_domain,
            evidence_kinds=tuple(dict.fromkeys(kinds)),
        )
        surfaces = self.make_surfaces(materialized, plan)
        # This recreates the old false-authority geometry: the pure classifier
        # accepts caller-supplied trust plus nonexistent, unpinned artifacts.
        seemingly_qualified = qualify_claim(
            QualificationRequest(
                claim_id=materialized.proposal.hypothesis.hypothesis_id,
                candidate_digest=materialized.binding.candidate_digest,
                candidate_trust_domain="optimizer-domain",
                target_level=QualificationLevel.SUPERIORITY,
                as_of=NOW,
            ),
            (*tuple(item.receipt for item in surfaces), *forged_receipts),
            (*self.issuer_authorities, caller_authority),
        )
        self.assertTrue(seemingly_qualified.qualified)
        outcome = self.evaluate(
            materialized,
            plan,
            holdout,
            surfaces,
            qualification_receipts=forged_receipts,
            issuer_authorities=(*self.issuer_authorities, caller_authority),
            target_level=QualificationLevel.SUPERIORITY,
        )

        self.assertEqual(EvaluationVerdict.QUARANTINE, outcome.verdict)
        self.assertIsNone(outcome.qualification)
        self.assertIsNone(outcome.evaluation_record)
        self.assertIn(
            "separate qualification receipts are unsupported",
            " ".join(outcome.reasons),
        )
        self.assertEqual(nonexistent_digests, outcome.qualification_artifact_digests)
        self.assertTrue(outcome.record_path.is_file())
        history, case_id = self.court(outcome, CourtDisposition.QUARANTINE)
        with self.assertRaisesRegex(
            ChallengerRuntimeError, "unqualified outcome cannot enter"
        ):
            self.runtime.submit_appeal(
                outcome,
                court_history=history,
                court_case_id=case_id,
                decision_id="decision:forged-qualification",
            )
        self.assertEqual((), self.promotion.log.decisions)
        self.assertEqual(self.pointer_before, self.registry.pointer_path.read_bytes())

    def test_holdout_commitment_mismatch_fails_before_seal_or_materialization(
        self,
    ) -> None:
        proposal = self.runtime.propose(self.finding())
        artifact_count = len(tuple(self.registry.artifact_root.glob("*.prompt")))
        mismatched = SealedHoldout(
            self.manifest.holdout_id,
            {"case-a": {"expected": "caller-substituted-answer"}},
        )

        with self.assertRaisesRegex(ChallengerRuntimeError, "authority commitment"):
            self.runtime.seal_evaluation(
                proposal,
                holdout=mismatched,
                prediction={"prediction": "must not be sealed"},
                surfaces=self.planned,
            )
        self.assertIsNone(mismatched.ordering["seal_sequence"])
        self.assertEqual(
            artifact_count,
            len(tuple(self.registry.artifact_root.glob("*.prompt"))),
        )
        self.assertEqual(self.pointer_before, self.registry.pointer_path.read_bytes())

        mutable_cases = {
            case_id: dict(payload) for case_id, payload in self.holdout_cases.items()
        }
        changed_after_seal = SealedHoldout(self.manifest.holdout_id, mutable_cases)
        plan = self.runtime.seal_evaluation(
            proposal,
            holdout=changed_after_seal,
            prediction={"prediction": "sealed before mutation"},
            surfaces=self.planned,
        )
        mutable_cases["case-a"]["expected"] = "mutated-after-seal"
        with self.assertRaisesRegex(ChallengerRuntimeError, "authority commitment"):
            self.runtime.materialize(proposal, plan, holdout=changed_after_seal)
        self.assertEqual(
            artifact_count,
            len(tuple(self.registry.artifact_root.glob("*.prompt"))),
        )
        self.assertEqual(self.pointer_before, self.registry.pointer_path.read_bytes())

    def test_holdout_mutation_after_materialization_fails_before_evaluation(
        self,
    ) -> None:
        proposal = self.runtime.propose(self.finding())
        mutable_cases = {
            case_id: dict(payload) for case_id, payload in self.holdout_cases.items()
        }
        holdout = SealedHoldout(self.manifest.holdout_id, mutable_cases)
        plan = self.runtime.seal_evaluation(
            proposal,
            holdout=holdout,
            prediction={"prediction": "sealed before mutation"},
            surfaces=self.planned,
        )
        materialized = self.runtime.materialize(proposal, plan, holdout=holdout)
        mutable_cases["case-b"]["expected"] = "mutated-after-build"
        holdout.reveal(plan.holdout_seal)

        with self.assertRaisesRegex(ChallengerRuntimeError, "authority commitment"):
            self.runtime.evaluate(
                materialized,
                plan,
                holdout=holdout,
                surfaces=(),
                qualification_receipts=(),
                issuer_authorities=self.issuer_authorities,
                candidate_trust_domain="optimizer-domain",
                target_level=QualificationLevel.STRUCTURAL,
                as_of=NOW,
            )
        self.assertEqual((), self.runtime.retained_outcomes)
        self.assertEqual(self.pointer_before, self.registry.pointer_path.read_bytes())

    def test_qualification_time_cannot_be_caller_selected(self) -> None:
        _proposal, holdout, plan, materialized = self.prepare()
        holdout.reveal(plan.holdout_seal)

        with self.assertRaisesRegex(ChallengerRuntimeError, "runtime clock"):
            self.runtime.evaluate(
                materialized,
                plan,
                holdout=holdout,
                surfaces=self.make_surfaces(materialized, plan),
                qualification_receipts=(),
                issuer_authorities=self.issuer_authorities,
                candidate_trust_domain="optimizer-domain",
                target_level=QualificationLevel.STRUCTURAL,
                as_of="2030-01-01T23:59:59+00:00",
            )
        self.assertEqual((), self.runtime.retained_outcomes)

    def test_reveal_before_materialization_and_dirty_source_are_refused(self) -> None:
        proposal = self.runtime.propose(self.finding())
        holdout = SealedHoldout(self.manifest.holdout_id, self.holdout_cases)
        plan = self.runtime.seal_evaluation(
            proposal,
            holdout=holdout,
            prediction={"prediction": "sealed"},
            surfaces=self.planned,
        )
        holdout.reveal(plan.holdout_seal)
        with self.assertRaisesRegex(ChallengerRuntimeError, "revealed before"):
            self.runtime.materialize(proposal, plan, holdout=holdout)

        second = self.runtime.propose(self.finding("finding:dirty-source"))
        second_holdout = SealedHoldout(self.manifest.holdout_id, self.holdout_cases)
        second_plan = self.runtime.seal_evaluation(
            second,
            holdout=second_holdout,
            prediction={"prediction": "sealed"},
            surfaces=self.planned,
        )
        (self.repository / "source.txt").write_text("mutated\n", encoding="utf-8")
        with self.assertRaisesRegex(ChallengerRuntimeError, "must be clean"):
            self.runtime.materialize(second, second_plan, holdout=second_holdout)


class FeedbackReentryTests(_RuntimeCase):
    def test_retest_returns_to_beginning_once_and_gen2_receipts_bind_prior_outcome(
        self,
    ) -> None:
        _proposal, holdout, plan, materialized = self.prepare()
        surfaces = self.make_surfaces(
            materialized,
            plan,
            held_out=((0.5, 0.5, 0.5), (0.5, 0.5, 0.5)),
        )
        outcome = self.evaluate(materialized, plan, holdout, surfaces)
        self.assertEqual(EvaluationVerdict.RETEST, outcome.verdict)
        self.assertTrue(outcome.record_path.is_file())

        feedback = self.finding(
            "finding:optimizer-rethink",
            evidence_refs=(outcome.outcome_digest, "evidence:cross-examination"),
        )
        proposal2 = self.runtime.reenter(outcome, feedback)
        self.assertEqual(2, proposal2.hypothesis.generation)
        self.assertEqual(
            outcome.outcome_digest, proposal2.hypothesis.prior_outcome_digest
        )
        with self.assertRaisesRegex(ChallengerRuntimeError, "already used"):
            self.runtime.reenter(outcome, feedback)

        holdout2 = SealedHoldout(
            self.manifest.holdout_id,
            self.holdout_cases,
        )
        plan2 = self.runtime.seal_evaluation(
            proposal2,
            holdout=holdout2,
            prediction={"generation": 2, "expected_verdict": "retest"},
            surfaces=self.planned,
        )
        materialized2 = self.runtime.materialize(proposal2, plan2, holdout=holdout2)
        self.assertNotEqual(
            materialized.binding.candidate_digest,
            materialized2.binding.candidate_digest,
        )
        surfaces2 = self.make_surfaces(materialized2, plan2)
        for item in surfaces2:
            self.assertEqual(outcome.outcome_digest, item.prior_outcome_digest)
            envelope = self.store.read(item.receipt.artifact_digest).envelope
            self.assertIn(outcome.outcome_digest, envelope.dependency_digests)
        outcome2 = self.evaluate(materialized2, plan2, holdout2, surfaces2)
        self.assertEqual(EvaluationVerdict.KEEP, outcome2.verdict)
        with self.assertRaisesRegex(ChallengerRuntimeError, "only generation-1"):
            self.runtime.reenter(
                outcome2,
                self.finding(
                    "finding:no-generation-three",
                    evidence_refs=(outcome2.outcome_digest,),
                ),
            )

    def test_wrong_candidate_surface_quarantines_and_retains_losing_evidence(
        self,
    ) -> None:
        _proposal, holdout, plan, materialized = self.prepare()
        forged = canonical_digest({"forged": "candidate"})
        surfaces = self.make_surfaces(materialized, plan, candidate_digest=forged)
        outcome = self.evaluate(materialized, plan, holdout, surfaces)

        self.assertEqual(EvaluationVerdict.QUARANTINE, outcome.verdict)
        self.assertIn("wrong candidate binding", " ".join(outcome.reasons))
        self.assertTrue(outcome.record_path.is_file())
        document = json.loads(outcome.record_path.read_text(encoding="utf-8"))
        self.assertEqual("quarantine", document["verdict"])
        self.assertEqual(4, len(document["surface_receipts"]))
        self.assertEqual(
            self.champions[Role.OPTIMIZER.value],
            self.registry.champion_digest(Role.OPTIMIZER),
        )

    def test_runtime_source_has_no_champion_mutation_call_sites(self) -> None:
        from hive_mind_os.brain_kernel import challenger_runtime

        source = Path(challenger_runtime.__file__).read_text(encoding="utf-8")
        code = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        for forbidden in (
            ".apply(",
            ".promote(",
            ".rollback_champion(",
            ".quarantine(",
            ".bootstrap(",
        ):
            self.assertNotIn(forbidden, code)

    def test_authority_and_keep_flow_are_order_independent_in_fresh_processes(
        self,
    ) -> None:
        authority = "tests.test_evaluation_authority"
        keep = (
            "tests.test_challenger_runtime.SealedChallengerFlowTests."
            "test_keep_is_retained_but_v2_promotion_is_typed_defer"
        )
        environment = os.environ.copy()
        repository_root = str(Path(__file__).resolve().parents[1])
        pythonpath = str(
            Path(repository_root) / "src"
        )
        environment["PYTHONPATH"] = os.pathsep.join(
            (repository_root, pythonpath)
        )
        for order in ((authority, keep), (keep, authority)):
            completed = subprocess.run(
                (sys.executable, "-m", "unittest", "-q", *order),
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
                env=environment,
            )
            self.assertEqual(
                0,
                completed.returncode,
                f"order {order} failed:\n{completed.stdout}\n{completed.stderr}",
            )


if __name__ == "__main__":
    unittest.main()
