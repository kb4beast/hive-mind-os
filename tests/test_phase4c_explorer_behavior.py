from __future__ import annotations

import math
import unittest
from pathlib import Path
from typing import Any, Mapping, Sequence

import hive_mind_os
import hive_mind_os.package_system as package_system
from hive_mind_os.foundation.canonical import digest
from hive_mind_os.foundation.explorer_behavior import (
    compile_explorer_behavior_suite,
    compile_explorer_evaluation_subjects,
    explorer_behavior_suite_bytes,
    score_explorer_behavior,
)
from hive_mind_os.foundation.explorer_behavior_contracts import (
    BASELINE_SUBJECT_ID,
    BEHAVIOR_FAMILIES,
    CANDIDATE_SUBJECT_ID,
    EXPLORER_BEHAVIOR_SCHEMA_NAMES,
    SAFETY_FAMILIES,
    validate_explorer_behavior,
    validate_explorer_behavior_catalog,
)
from scripts.phase1_surface_inventory import build_inventory, cli_inventory

REPOSITORY = Path(__file__).parents[1]
BUDGET_DIGEST = "sha256:" + ("1" * 64)


def _reseal(document: dict[str, Any]) -> None:
    document["content_digest"] = digest(
        {key: value for key, value in document.items() if key != "content_digest"}
    )


def _observations(
    *,
    fail_family: str | None = None,
    violation_family: str | None = None,
) -> list[dict[str, Any]]:
    suite = compile_explorer_behavior_suite()
    baseline = compile_explorer_evaluation_subjects()["baseline"]
    values = []
    for index, case in enumerate(suite["cases"]):
        outcomes = [
            {
                "assertion_id": assertion["assertion_id"],
                "outcome": (
                    "fail"
                    if case["family"] == fail_family and position == 0
                    else "pass"
                ),
            }
            for position, assertion in enumerate(case["assertions"])
        ]
        violation_codes = (
            [case["allowed_violation_codes"][0]]
            if case["family"] == violation_family
            else []
        )
        body = {
            "record_type": "explorer-behavior-observation",
            "schema_version": 1,
            "observation_id": f"observation:{index}",
            "suite_digest": suite["content_digest"],
            "case_id": case["case_id"],
            "case_digest": digest(case),
            "subject_id": BASELINE_SUBJECT_ID,
            "subject_digest": baseline["content_digest"],
            "dataset_digest": case["fixture_digest"],
            "evaluator_id": "evaluator:independent",
            "repetition": 0,
            "seed": index,
            "input_manifest_digest": case["fixture_digest"],
            "status": "completed",
            "assertion_outcomes": outcomes,
            "evidence_digests": [digest({"case": case["case_id"], "result": "fixture"})],
            "violation_codes": violation_codes,
            "error_code": None,
        }
        values.append({**body, "content_digest": digest(body)})
    return values


class _HostileSequence(Sequence[Mapping[str, Any]]):
    def __len__(self) -> int:
        return 0

    def __getitem__(self, index: int) -> Mapping[str, Any]:
        raise AssertionError(index)

    def __iter__(self):
        raise AssertionError("hostile sequence must not be iterated")


class ExplorerBehaviorTests(unittest.TestCase):
    def test_catalog_suite_subjects_are_deterministic_and_defensive(self) -> None:
        self.assertTrue(validate_explorer_behavior_catalog().valid)
        first = compile_explorer_behavior_suite()
        first["cases"][0]["family"] = "forged"
        second = compile_explorer_behavior_suite()
        subjects = compile_explorer_evaluation_subjects()
        subjects["candidate"]["executable"] = True

        self.assertEqual(second, compile_explorer_behavior_suite())
        self.assertEqual(explorer_behavior_suite_bytes(), explorer_behavior_suite_bytes())
        self.assertEqual(tuple(case["family"] for case in second["cases"]), BEHAVIOR_FAMILIES)
        self.assertEqual(sum(case["metric_weight_ppm"] for case in second["cases"]), 1_000_000)
        self.assertEqual(
            compile_explorer_evaluation_subjects()["candidate"]["execution_state"],
            "forced-not-run",
        )

    def test_candidate_is_forced_not_run_and_cannot_submit_observations(self) -> None:
        candidate = compile_explorer_evaluation_subjects()["candidate"]
        self.assertEqual(candidate["subject_id"], CANDIDATE_SUBJECT_ID)
        self.assertFalse(candidate["executable"])
        self.assertIsNone(candidate["runtime_binding_ref"])
        self.assertEqual(candidate["not_run_reason"], "runtime-binding-absent")

        observation = _observations()[0]
        observation["subject_id"] = CANDIDATE_SUBJECT_ID
        observation["subject_digest"] = candidate["content_digest"]
        _reseal(observation)
        validation = validate_explorer_behavior(
            EXPLORER_BEHAVIOR_SCHEMA_NAMES[2], observation
        )
        self.assertFalse(validation.valid)

    def test_complete_measurement_uses_exact_integer_ppm(self) -> None:
        result = score_explorer_behavior(
            _observations(),
            evaluator_id="evaluator:independent",
            budget_manifest_digest=BUDGET_DIGEST,
        )
        self.assertEqual(result["status"], "measurement-recorded")
        self.assertEqual(result["comparison_status"], "not-run")
        self.assertEqual(result["aggregate_score_ppm"], 1_000_000)
        self.assertFalse(result["promotion_authorized"])
        self.assertFalse(result["activation_authorized"])

    def test_missing_failed_and_safety_floor_semantics(self) -> None:
        incomplete = score_explorer_behavior(
            _observations()[:-1],
            evaluator_id="evaluator:independent",
            budget_manifest_digest=BUDGET_DIGEST,
        )
        self.assertEqual(incomplete["status"], "incomplete")
        self.assertIsNone(incomplete["aggregate_score_ppm"])
        self.assertEqual(len(incomplete["missing_case_ids"]), 1)

        for family in SAFETY_FAMILIES:
            with self.subTest(family=family):
                failed = score_explorer_behavior(
                    _observations(fail_family=family),
                    evaluator_id="evaluator:independent",
                    budget_manifest_digest=BUDGET_DIGEST,
                )
                self.assertEqual(failed["status"], "safety-floor-failed")
                metric = next(
                    item for item in failed["metrics"] if item["family"] == family
                )
                self.assertEqual(metric["score_ppm"], 500_000)

        violation = score_explorer_behavior(
            _observations(violation_family="authority"),
            evaluator_id="evaluator:independent",
            budget_manifest_digest=BUDGET_DIGEST,
        )
        metric = next(
            item for item in violation["metrics"] if item["family"] == "authority"
        )
        self.assertEqual(metric["score_ppm"], 0)
        self.assertEqual(violation["status"], "safety-floor-failed")

    def test_resealed_suite_and_subject_substitutions_fail_fixed_identity(self) -> None:
        suite = compile_explorer_behavior_suite()
        suite["cases"][0]["fixture_ref"] = "substituted"
        _reseal(suite)
        self.assertFalse(
            validate_explorer_behavior(EXPLORER_BEHAVIOR_SCHEMA_NAMES[0], suite).valid
        )

        candidate = compile_explorer_evaluation_subjects()["candidate"]
        candidate["runtime_binding_ref"] = "forged:runtime"
        candidate["execution_state"] = "development-executable"
        candidate["executable"] = True
        candidate["not_run_reason"] = None
        _reseal(candidate)
        validation = validate_explorer_behavior(
            EXPLORER_BEHAVIOR_SCHEMA_NAMES[1], candidate
        )
        self.assertFalse(validation.valid)
        self.assertIn("forced-not-run", " ".join(validation.issues))

    def test_observation_pin_order_duplicate_and_private_body_attacks_fail(self) -> None:
        cases = []

        changed_pin = _observations()
        changed_pin[0]["dataset_digest"] = "sha256:" + ("0" * 64)
        _reseal(changed_pin[0])
        cases.append(changed_pin)

        reordered = _observations()
        reordered[0]["assertion_outcomes"].reverse()
        _reseal(reordered[0])
        cases.append(reordered)

        duplicate = _observations()
        duplicate[1]["case_id"] = duplicate[0]["case_id"]
        _reseal(duplicate[1])
        cases.append(duplicate)

        private = _observations()
        private[0]["response_body"] = "prohibited"
        _reseal(private[0])
        cases.append(private)

        for observations in cases:
            with self.subTest(observations=observations):
                with self.assertRaises(ValueError):
                    score_explorer_behavior(
                        observations,
                        evaluator_id="evaluator:independent",
                        budget_manifest_digest=BUDGET_DIGEST,
                    )

    def test_invalid_numbers_and_hostile_containers_fail_closed(self) -> None:
        invalid = _observations()
        invalid[0]["seed"] = True
        _reseal(invalid[0])
        with self.assertRaises(ValueError):
            score_explorer_behavior(
                invalid,
                evaluator_id="evaluator:independent",
                budget_manifest_digest=BUDGET_DIGEST,
            )
        self.assertFalse(math.isfinite(float("nan")))
        with self.assertRaisesRegex(ValueError, "bounded built-in sequence"):
            score_explorer_behavior(
                _HostileSequence(),
                evaluator_id="evaluator:independent",
                budget_manifest_digest=BUDGET_DIGEST,
            )

    def test_supported_surfaces_and_generic_evaluators_remain_frozen(self) -> None:
        inventory = build_inventory(REPOSITORY)
        self.assertEqual(len(hive_mind_os.__all__), 131)
        self.assertEqual(len(package_system.__all__), 33)
        self.assertEqual(cli_inventory()["parser_count"], 13)
        self.assertEqual(
            inventory["observable_module_surface"]["definition_count"], 304
        )
        self.assertEqual(
            inventory["runtime_effects"]["unclassified_candidate_count"], 0
        )
        self.assertEqual(
            len(tuple((REPOSITORY / "src/hive_mind_os").rglob("*.json"))), 133
        )


if __name__ == "__main__":
    unittest.main()
