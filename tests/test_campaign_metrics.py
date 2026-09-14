from __future__ import annotations

import unittest

from hive_mind_os.campaign_metrics import (
    AttemptMetric, CampaignMetricsError, MatchProtocol, PairedInterval, ScheduledPair,
    VariantSeal, decide_match, noninferior, paired_family_bootstrap,
    schedule_round, summarize_attempts,
)

D = "sha256:" + "a" * 64


def metric(*, family="repo-a", result="success", eligibility="eligible", usage=2.0, usage_basis="measured"):
    return AttemptMetric(family, "task", "MB0", D, D, D, D, eligibility, result,
                         1.0, 0.0, 1.0, usage, usage_basis, None, "unknown")


class CampaignMetricsTests(unittest.TestCase):
    def test_unknown_is_not_zero_and_failures_and_ineligible_are_retained(self):
        rows = (metric(result="success"), metric(result="failure"),
                metric(eligibility="ineligible", result="not_attempted"),
                metric(eligibility="unknown", result="unknown", usage=None, usage_basis="unknown"))
        summary = summarize_attempts(rows)
        self.assertEqual(summary, {"records": 4, "eligible_attempted": 2,
                                   "eligible_successes": 1, "eligible_failures": 1,
                                   "ineligible": 1, "unknown_eligibility": 1,
                                   "unknown_result": 1, "inconclusive": 0})
        self.assertIsNone(rows[-1].usage_units)
        with self.assertRaises(CampaignMetricsError):
            metric(usage=0.0, usage_basis="unknown")

    def test_family_bootstrap_is_deterministic_and_clusters_repetitions(self):
        pairs = {"repo-a": (1.0, 1.0, 1.0), "repo-b": (-1.0,)}
        self.assertEqual(paired_family_bootstrap(pairs, seed=9), paired_family_bootstrap(pairs, seed=9))
        interval = paired_family_bootstrap(pairs, seed=9)
        self.assertEqual(interval.family_count, 2)
        self.assertEqual(interval.estimate, 0.0)
        self.assertEqual(interval.resamples, 10_000)

    def test_noninferiority_is_strict_and_requires_hard_gates(self):
        interval = PairedInterval(0, -0.04, 0.1, 30)
        self.assertTrue(noninferior(interval, hard_gates_pass=True))
        self.assertFalse(noninferior(interval, hard_gates_pass=False))
        self.assertFalse(noninferior(PairedInterval(0, -0.05, 0.1, 30), hard_gates_pass=True))

    def test_scheduler_gives_odd_only_bye_and_skips_two_inconclusives(self):
        first = schedule_round(("MB0", "MB1", "MB2"), {"MB0": 0, "MB1": 0, "MB2": 0}, {"MB0": 1, "MB1": 0, "MB2": 0}, round_number=1)
        self.assertEqual([p.left for p in first if p.bye], ["MB1"])
        pairs = schedule_round(("MB0", "MB1", "MB2", "MB3"), {x: 0 for x in ("MB0", "MB1", "MB2", "MB3")}, {}, round_number=1,
                               inconclusive_meetings={frozenset(("MB0", "MB1")): 2})
        self.assertNotIn(("MB0", "MB1"), [(p.left, p.right) for p in pairs])
        self.assertEqual(schedule_round(("MB0", "MB1"), {"MB0": 0, "MB1": 0}, {}, round_number=2), (ScheduledPair("MB1", "MB0"),))

    def test_protocol_requires_frozen_rules_and_distinct_final_seals(self):
        protocol = MatchProtocol("WOS-N02", "1", "builder", {"MB0": {"recipe_digest": D}},
                                 {"all": "immutable source/binary/prompt/model/command/profile/tool/context/check/learning digests"},
                                 "independent evaluator seals candidate bytes before stage", ("small-bug",), ("dev-a",),
                                 "loss/id rotate; odd-only bye; two-inconclusive skip", "paired intervals and hard gates", {})
        seal = VariantSeal("MB0", D, D, "curator-1", "development")
        protocol.validate_seals((seal,))
        with self.assertRaises(CampaignMetricsError): protocol.validate_seals((seal,), final=True)
        with self.assertRaises(CampaignMetricsError): MatchProtocol("x", "1", "x", {"MB0": {"recipe_digest": D}}, {}, "seal", ("t",), ("b",), "pair", "decide", {}, elimination_losses=2)

    def test_decision_never_lexically_breaks_draws(self):
        equal = PairedInterval(0, -0.04, 0.04, 30)
        self.assertEqual(decide_match(equal, PairedInterval(1, .9, 1.1, 30), PairedInterval(1, .9, 1.1, 30), left_hard_gates=True, right_hard_gates=True), "DRAW")
        self.assertEqual(decide_match(PairedInterval(.1, .01, .2, 30), equal, equal, left_hard_gates=True, right_hard_gates=True), "LEFT")


if __name__ == "__main__":
    unittest.main()
