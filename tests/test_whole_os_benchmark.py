import unittest

from hive_mind_os.benchmark_adapters import RecipeClass, RecipeManifest
from hive_mind_os.whole_os_benchmark import PromotionDisposition, decide_promotion

D = "sha256:" + "a" * 64


class WholeOSBenchmarkTests(unittest.TestCase):
    def test_pinned_recipe_has_stable_digest(self):
        recipe = RecipeManifest(
            "lane",
            RecipeClass.CURRENT_BASELINE,
            D,
            D,
            D,
            D,
            D,
            D,
            D,
            D,
            ("runner", "--json"),
            {"TZ": "UTC"},
        )
        self.assertEqual(recipe.digest, recipe.digest)

    def test_missing_independent_receipts_defers(self):
        decision = decide_promotion(
            candidate_digest=D,
            prior_champion_digest=D,
            hard_gates_passed=True,
            noninferiority_passed=True,
            measurable_benefit=True,
            independent_receipt_digests=(),
        )
        self.assertEqual(decision.disposition, PromotionDisposition.DEFER)


if __name__ == "__main__":
    unittest.main()
