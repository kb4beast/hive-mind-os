from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

from .acceptance_harness import (
    REQUIRED_RECEIPT_TESTS,
    SPECIALIST_ROLES,
    AcceptanceRun,
    Approval,
    Consultation,
    EffectReceipt,
    load_fixture_inventory,
    validate_fixture_inventory,
    validate_run,
)

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "hive_cortex"


def valid_run() -> AcceptanceRun:
    effects = tuple(EffectReceipt(role, f"effect-{index}") for index, role in enumerate(SPECIALIST_ROLES))
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


class AcceptanceHarnessTests(unittest.TestCase):
    def test_acceptance_harness_self_tests(self) -> None:
        fixtures = load_fixture_inventory(FIXTURE_ROOT)
        self.assertEqual(validate_fixture_inventory(fixtures), ())
        self.assertEqual(validate_run(valid_run()), ())
        self.assertEqual(set(REQUIRED_RECEIPT_TESTS), {
            "acceptance-harness-self-tests",
            "negative-control-tests",
            "cross-language-fixture-tests",
        })

    def test_negative_control_tests(self) -> None:
        controls = (
            (replace(valid_run(), roles=SPECIALIST_ROLES[:-1]), "missing-role-wiring"),
            (replace(valid_run(), consultations=(Consultation("curator", ("curator",)),)), "fake-consultation"),
            (replace(valid_run(), approvals=(Approval("builder", "builder", "candidate-1"),)), "self-approval"),
            (replace(valid_run(), observed_commits=("base-1", "future-1")), "future-leakage"),
            (replace(valid_run(), human_escalated=True), "human-escalation-software-defect"),
            (replace(valid_run(), receipt_candidate="forged-candidate"), "receipt-candidate-mismatch"),
            (replace(valid_run(), receipt_effects=valid_run().expected_effects[:-1]), "receipt-effect-sequence-mismatch"),
        )
        for run, expected_code in controls:
            with self.subTest(expected_code=expected_code):
                self.assertTrue(any(issue.startswith(expected_code) for issue in validate_run(run)))

    def test_humanless_gate_distinguishes_real_authority(self) -> None:
        run = replace(valid_run(), authority_class="protected-branch", human_escalated=True)
        self.assertEqual(validate_run(run), ())

    def test_cross_language_fixture_tests(self) -> None:
        fixtures = load_fixture_inventory(FIXTURE_ROOT)
        self.assertEqual(validate_fixture_inventory(fixtures), ())
        self.assertIn(frozenset({"python", "node", "csharp"}), {
            frozenset(item.languages) for item in fixtures if item.scenario == "monorepo"
        })
        self.assertEqual({item.language for item in fixtures}, {"python", "node", "csharp", "mixed"})


if __name__ == "__main__":
    unittest.main()
