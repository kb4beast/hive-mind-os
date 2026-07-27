import unittest
from dataclasses import replace

from hive_mind_os.models import Role
from hive_mind_os.vision import (
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
        )

    def test_complete_autonomous_lifecycle_is_compliant(self) -> None:
        decision = self.gate.evaluate(self.evidence)
        self.assertTrue(decision.compliant, decision.reasons)

    def test_original_sources_are_part_of_immutable_contract(self) -> None:
        self.assertIn(
            "https://www.youtube.com/watch?v=mazBhCg3urw",
            self.contract.source_references,
        )
        self.assertIn(
            "https://www.youtube.com/watch?v=Gw_hnD7m00M",
            self.contract.source_references,
        )
        self.assertIn(
            "https://github.com/rangerrick337/operator-os/tree/main",
            self.contract.source_references,
        )
        self.assertIn(
            "https://github.com/nousresearch/hermes-agent",
            self.contract.source_references,
        )

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


if __name__ == "__main__":
    unittest.main()
