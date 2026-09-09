from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

from hive_mind_os.dag_standard import compile_plan
from hive_mind_os.plan_generation import PinnedArtifact, PlanGenerationRequest
from hive_mind_os.portable_plan import RepositorySubject, SubjectBinding
from hive_mind_os.runtime_contracts import (
    AuthorityEnvelope,
    ContractViolation,
    EvidenceReference,
    raw_sha256,
)
from hive_mind_os.tournament_plan_factory import TournamentPlanFactory

REPOSITORY_ID = raw_sha256(b"https://example.invalid/hive-mind-os.git")
COMMIT = "a" * 40
TREE = "b" * 40
REQUEST_ID = raw_sha256(b"fresh tournament request")
OBJECTIVE_DIGEST = raw_sha256(b"improve all governed aspects")
STANDARD = PinnedArtifact.pin("standard", b"external DAG standard bytes\n")


def request() -> PlanGenerationRequest:
    subject = SubjectBinding.for_repository(
        RepositorySubject(REPOSITORY_ID, COMMIT, TREE, "release/tournament")
    )
    return PlanGenerationRequest(
        REQUEST_ID,
        OBJECTIVE_DIGEST,
        subject.subject_id,
        "repository",
        REPOSITORY_ID,
        "release/tournament",
        COMMIT,
        TREE,
        None,
    )


def authority() -> AuthorityEnvelope:
    return AuthorityEnvelope(
        "local-tournament",
        "repository-owner",
        raw_sha256(b"owner-local-tournament-grant"),
        ("inspect", "local-edit", "local-test", "prepare-evidence"),
        (
            "credential",
            "deployment",
            "merge",
            "payment",
            "production-mutation",
            "protected-merge",
            "push",
        ),
        "2030-01-01T00:00:00Z",
        False,
    )


def evidence() -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            "main-snapshot",
            raw_sha256(b"exact main snapshot"),
            "git:main",
            ("TOURNAMENT-BASELINE",),
            "2026-09-05T00:00:00Z",
        ),
    )


class TournamentPlanFactoryTests(unittest.TestCase):
    def test_factory_emits_a_parallel_all_role_external_plan(self) -> None:
        plan = TournamentPlanFactory().build(
            request(), standard=STANDARD, authority=authority(), evidence=evidence()
        )
        receipt = compile_plan(
            plan.canonical_bytes(),
            expected_plan_digest=plan.digest(),
            standard_bytes=STANDARD.content,
            expected_request_id=REQUEST_ID,
            expected_subject_id=request().subject_id,
        )

        self.assertEqual("external-all-aspect-tournament-v2", plan.plan_id)
        self.assertEqual(13, receipt.metrics.node_count)
        self.assertEqual(4, receipt.maximum_workers)
        self.assertEqual(
            ("AGENTS-010", "LEARNING-040", "ORCHESTRATION-020", "RUNTIME-030"),
            receipt.rounds[1].node_ids,
        )
        self.assertEqual(
            (
                ("PROPOSE-042",),
                ("CROSS-045",),
                ("REVISE-048",),
                ("COURT-050",),
                ("CHALLENGER-060",),
                ("VERIFY-070",),
                ("JUDGE-075",),
                ("INTEGRATE-080",),
            ),
            tuple(round_.node_ids for round_ in receipt.rounds[2:]),
        )
        self.assertFalse(hasattr(plan, "execute"))
        challenger = next(node for node in plan.nodes if node.node_id == "CHALLENGER-060")
        self.assertIn("candidate-workspace", challenger.resource_ids)
        self.assertIn("no Hive Mind workspace or DAG-plan dependency", challenger.acceptance_criteria[1])

    def test_experiment_selection_follows_independent_challenge_and_response(self) -> None:
        plan = TournamentPlanFactory().build(
            request(), standard=STANDARD, authority=authority(), evidence=evidence()
        )
        nodes = {node.node_id: node for node in plan.nodes}
        self.assertEqual(("PROPOSE-042",), nodes["CROSS-045"].dependencies)
        self.assertEqual(("CROSS-045",), nodes["REVISE-048"].dependencies)
        self.assertEqual(("REVISE-048",), nodes["COURT-050"].dependencies)
        self.assertEqual(("VERIFY-070",), nodes["JUDGE-075"].dependencies)
        challenge = " ".join(nodes["CROSS-045"].acceptance_criteria)
        selection = " ".join(nodes["COURT-050"].acceptance_criteria)
        judgment = " ".join(nodes["JUDGE-075"].acceptance_criteria)
        self.assertIn("distinct from its advocate", challenge)
        self.assertIn("may find no blocking defect", challenge)
        self.assertIn("material revisions receive independent re-examination", selection)
        self.assertIn("only at their later applicable stages", selection)
        self.assertIn("authority gaps still stop", selection)
        self.assertIn("independent verification receipts", judgment)
        self.assertIn("multiple pinned comparators", judgment)

    def test_generic_repository_uses_external_workers_and_preserves_idea_history(self) -> None:
        repository = RepositorySubject(
            raw_sha256(b"FOO BAR"), "c" * 40, "d" * 40, "feature/customer-value"
        )
        subject = SubjectBinding.for_repository(repository)
        generic = replace(
            request(),
            repository_id=repository.repository_id,
            subject_id=subject.subject_id,
            parent_commit=repository.commit,
            parent_tree=repository.tree,
            target=repository.target_branch,
        )
        plan = TournamentPlanFactory().build(
            generic, standard=STANDARD, authority=authority(), evidence=evidence()
        )
        receipt = compile_plan(
            plan.canonical_bytes(),
            expected_plan_digest=plan.digest(),
            standard_bytes=STANDARD.content,
            expected_request_id=generic.request_id,
            expected_subject_id=generic.subject_id,
        )
        self.assertEqual(subject, plan.subject)
        self.assertEqual(13, receipt.metrics.node_count)
        text = plan.canonical_bytes().decode("utf-8")
        self.assertNotIn("one class per agent file", text)
        self.assertNotIn("Every constitutional role is inspected as a direct source file", text)
        nodes = {node.node_id: node for node in plan.nodes}
        revision = " ".join(nodes["REVISE-048"].acceptance_criteria)
        brain = " ".join(nodes["INTEGRATE-080"].acceptance_criteria)
        self.assertIn("stable idea identity and immutable version history", revision)
        self.assertIn("explicitly linked child idea", revision)
        self.assertIn("one revision round", revision)
        self.assertIn("who returned it, why, the receiving role", revision)
        self.assertIn("even when no challenger is selected", brain)
        self.assertIn("local Markdown without requiring Obsidian", brain)
        self.assertEqual(
            {"orchestrator", "explorer", "architect", "builder", "curator", "integrator", "steward", "optimizer"},
            {role for node in plan.nodes for role in node.roles},
        )
        self.assertEqual(
            {"discover", "design", "build", "validate", "grow", "maintain", "integrate"},
            {stage for node in plan.nodes for stage in node.lifecycle_stages},
        )

    def test_factory_seals_a_fresh_plan_without_activating_it(self) -> None:
        factory = TournamentPlanFactory()
        arguments = {
            "standard": STANDARD,
            "authority": authority(),
            "evidence": evidence(),
            "node_mappings": PinnedArtifact.pin("node-mappings", b"role mappings\n"),
            "sources": (PinnedArtifact.pin("source", b"court source\n"),),
            "compiler": PinnedArtifact.pin("compiler", b"compiler source\n"),
        }
        first, inserted = factory.generate(request(), **arguments)
        second, repeated = factory.generate(request(), **arguments)

        self.assertTrue(inserted)
        self.assertFalse(repeated)
        self.assertEqual(first.record.generation_id, second.record.generation_id)
        self.assertEqual(first.portable_plan.digest(), first.record.plan_digest)
        self.assertFalse(hasattr(first, "execute"))
        self.assertIn(b'"host_signature_required":true', first.activation_material.external_manifest_bytes)

    def test_factory_rejects_authority_escalation_and_missing_evidence(self) -> None:
        with self.assertRaisesRegex(ContractViolation, "cannot declare external effects"):
            TournamentPlanFactory().build(
                request(),
                standard=STANDARD,
                authority=replace(authority(), external_effects=True),
                evidence=evidence(),
            )
        with self.assertRaisesRegex(ContractViolation, "requires typed evidence"):
            TournamentPlanFactory().build(
                request(), standard=STANDARD, authority=authority(), evidence=()
            )

    def test_factory_rejects_non_repository_or_incomplete_authority(self) -> None:
        non_repository_request = replace(
            request(),
            subject_kind="non_repository",
            repository_id=None,
            parent_commit=None,
            parent_tree=None,
        )
        with self.assertRaisesRegex(ContractViolation, "requires a repository subject"):
            TournamentPlanFactory().build(
                non_repository_request,
                standard=STANDARD,
                authority=authority(),
                evidence=evidence(),
            )
        with self.assertRaisesRegex(ContractViolation, "deny external control actions"):
            TournamentPlanFactory().build(
                request(),
                standard=STANDARD,
                authority=replace(authority(), denied_actions=("merge",)),
                evidence=evidence(),
            )

    def test_orchestration_factory_does_not_live_with_or_import_agents(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "hive_mind_os"
            / "tournament_plan_factory.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn(".agents", source)
        self.assertFalse(
            (Path(__file__).resolve().parents[1] / "src" / "hive_mind_os" / "agents" / "tournament_plan_factory.py").exists()
        )


if __name__ == "__main__":
    unittest.main()
