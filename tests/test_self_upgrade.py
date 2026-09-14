import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hive_mind_os.self_upgrade import (
    RuntimeChallenger,
    UpgradeController,
    UpgradeDecision,
)

D = "sha256:" + "a" * 64


class Host:
    def __init__(self, uncertain=False):
        self.uncertain = uncertain
        self.activations = 0
        self.rollbacks = 0

    def activate(self, challenger):
        self.activations += 1
        if self.uncertain:
            raise TimeoutError("pointer response lost")
        return "ref:activation/1"

    def observe(self, challenger):
        return "ref:activation/observed"

    def rollback(self, challenger):
        self.rollbacks += 1
        return "ref:rollback/1"


class SelfUpgradeTests(unittest.TestCase):
    def challenger(self, **changes):
        values = {
            "version": "2",
            "artifact_digest": D,
            "champion_parent": "sha256:" + "b" * 64,
            "source_ref": "ref:pr/1",
            "dependency_manifest": D,
            "migration_manifest": D,
            "rollback_artifact": "ref:rollback/artifact",
            "evaluation_plan": D,
            "evaluation_result": "ref:evaluation/1",
            "builder_id": "builder",
            "evaluator_id": "curator",
            "judge_id": "judge",
            "canary_scope": "one-tenant-shadow",
        }
        values.update(changes)
        return RuntimeChallenger(**values)

    def test_uncertain_activation_reconciles_after_restart_without_retry(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "upgrade.json"
            host = Host(uncertain=True)
            challenger = self.challenger()
            first = UpgradeController(host, state_path=path)
            receipt = first.decide(
                challenger,
                qualification_passed=True,
                heldout_passed=True,
                rollback_valid=True,
            )
            self.assertEqual(receipt.decision, UpgradeDecision.DEFER)
            resumed = UpgradeController(host, state_path=path)
            reconciled = resumed.reconcile(challenger)
            self.assertEqual(reconciled.decision, UpgradeDecision.PROMOTE)
            self.assertEqual(host.activations, 1)
            rolled_back = resumed.rollback(challenger)
            self.assertEqual(rolled_back.decision, UpgradeDecision.ROLLBACK)

    def test_self_judgment_and_missing_authority_never_activate(self):
        challenger = self.challenger(evaluator_id="builder")
        self.assertEqual(
            UpgradeController(Host()).decide(
                challenger,
                qualification_passed=True,
                heldout_passed=True,
                rollback_valid=True,
            ).decision,
            UpgradeDecision.QUARANTINE,
        )
        self.assertEqual(
            UpgradeController().decide(
                self.challenger(),
                qualification_passed=True,
                heldout_passed=True,
                rollback_valid=True,
            ).decision,
            UpgradeDecision.CANARY,
        )


if __name__ == "__main__":
    unittest.main()
