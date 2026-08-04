import unittest
from dataclasses import replace

from hive_mind_os.models import Role
from hive_mind_os.source_docket import load_default_source_docket
from hive_mind_os.reference.vision import (
    REQUIRED_CAPABILITIES,
    REQUIRED_ROLES,
    REQUIRED_STAGES,
    HardenedVisionContract,
    VisionComplianceGate,
    VisionRunEvidence,
)


class HardenedVisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = HardenedVisionContract()
        self.gate = VisionComplianceGate(self.contract)
        self.evidence = VisionRunEvidence(
            contract_fingerprint=self.contract.fingerprint,
            completed_roles=REQUIRED_ROLES,
            completed_stages=REQUIRED_STAGES,
            exercised_capabilities=REQUIRED_CAPABILITIES,
            evidence_refs=("ledger:event:1", "artifact:test-report"),
            actor_variant_ids=("orchestrator-v1", "builder-v1"),
            verifier_variant_ids=("curator-v1",),
            rollback_evidence_ref="artifact:rollback-plan",
            court_case_refs=("CASE-001", "CASE-003"),
            source_docket_audit_ref="artifact:source-docket-audit",
            source_inventory_complete=True,
        )

    def test_complete_autonomous_lifecycle_is_compliant(self) -> None:
        decision = self.gate.evaluate(self.evidence)
        self.assertTrue(decision.compliant, decision.reasons)

    def test_vision_sources_exactly_match_the_authoritative_docket(self) -> None:
        docket_uris = tuple(
            source.uri for source in load_default_source_docket().sources
        )
        self.assertEqual(self.contract.source_references, docket_uris)
        self.assertEqual(
            len(self.contract.source_references),
            len(set(self.contract.source_references)),
        )

    def test_recursive_improvement_shortcuts_are_forbidden(self) -> None:
        expected = {
            "live_champion_mutation",
            "single_metric_optimization_without_guardrails",
            "promotion_below_measured_noise",
            "protected_holdout_access",
            "unbounded_recursive_improvement",
            "self_weight_modification",
        }
        self.assertTrue(expected.issubset(set(self.contract.forbidden_shortcuts)))

    def test_classic_gpt_simulation_shortcuts_are_forbidden(self) -> None:
        expected = {
            "simulated_tool_execution_claimed_as_real",
            "implicit_memory_as_authoritative",
            "unlabeled_role_blending",
        }
        self.assertTrue(expected.issubset(set(self.contract.forbidden_shortcuts)))

    def test_missing_role_and_capability_fail_closed(self) -> None:
        evidence = replace(
            self.evidence,
            completed_roles=tuple(role for role in REQUIRED_ROLES if role is not Role.OPTIMIZER),
            exercised_capabilities=REQUIRED_CAPABILITIES[:-1],
        )
        decision = self.gate.evaluate(evidence)
        self.assertFalse(decision.compliant)
        self.assertTrue(any("missing autonomous roles" in reason for reason in decision.reasons))
        self.assertTrue(
            any("missing autonomous capabilities" in reason for reason in decision.reasons)
        )

    def test_future_knowledge_and_self_approval_are_rejected(self) -> None:
        evidence = replace(
            self.evidence,
            actor_variant_ids=("builder-v1",),
            verifier_variant_ids=("builder-v1",),
            accessed_future_commits=("future-sha",),
        )
        decision = self.gate.evaluate(evidence)
        self.assertFalse(decision.compliant)
        self.assertIn(
            "point-in-time learner accessed target or future commits",
            decision.reasons,
        )
        self.assertIn("acting agent attempted to approve its own work", decision.reasons)

    def test_only_policy_required_human_intervention_is_acceptable(self) -> None:
        policy_gate = replace(
            self.evidence,
            human_interventions=1,
            policy_required_interventions=1,
        )
        self.assertTrue(self.gate.evaluate(policy_gate).compliant)

        supervised_routine = replace(
            self.evidence,
            human_interventions=1,
            policy_required_interventions=0,
        )
        decision = self.gate.evaluate(supervised_routine)
        self.assertFalse(decision.compliant)
        self.assertIn("routine work required human supervision", decision.reasons)

    def test_contract_mutation_is_detected(self) -> None:
        evidence = replace(self.evidence, contract_fingerprint="mutated")
        decision = self.gate.evaluate(evidence)
        self.assertFalse(decision.compliant)
        self.assertIn("vision contract changed", decision.reasons)

    def test_missing_court_and_source_docket_fail_closed(self) -> None:
        evidence = replace(
            self.evidence,
            court_case_refs=(),
            source_docket_audit_ref=None,
            source_inventory_complete=False,
            unresolved_source_ids=("SRC-005",),
        )
        decision = self.gate.evaluate(evidence)
        self.assertFalse(decision.compliant)
        self.assertIn("courtroom review evidence is missing", decision.reasons)
        self.assertIn("source docket audit is missing", decision.reasons)
        self.assertIn("source idea inventory is incomplete", decision.reasons)
        self.assertTrue(any("SRC-005" in reason for reason in decision.reasons))

    def test_superiority_claim_requires_comparative_benchmark(self) -> None:
        evidence = replace(self.evidence, superiority_claimed=True)
        decision = self.gate.evaluate(evidence)
        self.assertFalse(decision.compliant)
        self.assertIn("superiority claim lacks comparative benchmark evidence", decision.reasons)

        benchmarked = replace(
            evidence,
            comparative_benchmark_ref="artifact:comparator-court-result",
        )
        self.assertTrue(self.gate.evaluate(benchmarked).compliant)


if __name__ == "__main__":
    unittest.main()
