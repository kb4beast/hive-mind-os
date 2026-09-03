from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

from hive_mind_os.token_benchmark import (
    BenchmarkControls,
    TokenBenchmarkError,
    TokenBenchmarkLane,
    build_token_benchmark_report,
    controlled_fixture_report,
    measure_lexical_tokens,
)


def digest(character: str) -> str:
    return "sha256:" + character * 64


CONTROLS = BenchmarkControls(
    digest("1"), digest("2"), digest("3"), digest("4"), digest("5")
)
ROOT = Path(__file__).resolve().parents[1]
CHECKED_REPORT = (
    ROOT / "evidence/audits/v4-successor-recovery/TOKEN-BENCHMARK.json"
)


def lane(name: str, comparator: int, challenger: int) -> TokenBenchmarkLane:
    return TokenBenchmarkLane(
        f"lane-{name}",
        name,
        digest("a"),
        digest("b"),
        CONTROLS,
        comparator,
        challenger,
        5,
        "tokenizer-measured",
        "fixture-tokenizer-v1",
        digest("c"),
    )


class GenericDagTokenBenchmarkTests(unittest.TestCase):
    def test_controlled_representative_lanes_exceed_thirty_percent(self) -> None:
        report = controlled_fixture_report()
        self.assertTrue(report.threshold_met)
        self.assertGreaterEqual(report.reduction_basis_points, 3_000)
        self.assertGreater(
            report.comparator_input_tokens, report.challenger_input_tokens
        )
        self.assertIn("No product superiority", report.forbidden_claim)
        self.assertEqual(4, len(report.to_document()["lanes"]))
        self.assertEqual(report, controlled_fixture_report())
        self.assertEqual(4, measure_lexical_tokens("alpha, beta!"))
        self.assertEqual(
            report.to_document(),
            json.loads(CHECKED_REPORT.read_text(encoding="utf-8")),
        )

    def test_estimates_missing_measurements_and_losing_lane_fail_qualification(
        self,
    ) -> None:
        with self.assertRaisesRegex(TokenBenchmarkError, "estimates"):
            replace(lane("repository", 100, 50), measurement_source="static-estimate")
        with self.assertRaisesRegex(TokenBenchmarkError, "positive"):
            replace(lane("repository", 100, 50), challenger_input_tokens=0)
        report = build_token_benchmark_report(
            (lane("repository", 1_000, 500), lane("workflow", 1_000, 1_100))
        )
        self.assertFalse(report.threshold_met)
        self.assertEqual("THRESHOLD_NOT_MET", report.disposition)

    def test_comparator_identity_and_controls_are_retained(self) -> None:
        report = build_token_benchmark_report((lane("repository", 1_000, 650),))
        document = report.to_document()
        retained = document["lanes"][0]
        self.assertEqual(digest("a"), retained["comparator_digest"])
        self.assertEqual(CONTROLS.to_document(), retained["controls"])
        self.assertEqual(digest("c"), retained["accepted_outcome_digest"])
        with self.assertRaisesRegex(TokenBenchmarkError, "distinct"):
            replace(lane("repository", 100, 50), challenger_digest=digest("a"))


if __name__ == "__main__":
    unittest.main()
