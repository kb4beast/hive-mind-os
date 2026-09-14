import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from hive_mind_os.benchmark_adapters import (
    AdmittedBenchmarkRunner,
    BenchmarkAdapterError,
    PinnedRecipeAdapter,
    RecipeClass,
    RecipeManifest,
)
from hive_mind_os.campaign_metrics import canonical_digest
from hive_mind_os.whole_os_benchmark import (
    PromotionDecision,
    PromotionDisposition,
    TournamentError,
    WholeOSTournament,
    decide_promotion,
)
from tests.test_benchmark_adapters import RecordingBroker, admitted_fixture

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

    def test_promotion_requires_two_distinct_well_formed_receipts(self):
        common = {
            "candidate_digest": D,
            "prior_champion_digest": D,
            "hard_gates_passed": True,
            "noninferiority_passed": True,
            "measurable_benefit": True,
        }
        receipt_one = canonical_digest("independent-one")
        receipt_two = canonical_digest("independent-two")
        for receipts in ((receipt_one,), (receipt_one, receipt_one), ("forged", D)):
            with self.subTest(receipts=receipts):
                self.assertEqual(
                    PromotionDisposition.DEFER,
                    decide_promotion(
                        **common, independent_receipt_digests=receipts
                    ).disposition,
                )
        self.assertEqual(
            PromotionDisposition.ADOPT,
            decide_promotion(
                **common,
                independent_receipt_digests=(receipt_one, receipt_two),
            ).disposition,
        )
        with self.assertRaisesRegex(TournamentError, "measured evidence"):
            PromotionDecision(
                D,
                PromotionDisposition.ADOPT,
                D,
                True,
                True,
                True,
                (receipt_one,),
            )

    def test_tournament_executes_only_the_exact_admitted_lane_and_reloads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, manifest, protocol_path, registry = admitted_fixture(root)
            broker = RecordingBroker()
            runner = AdmittedBenchmarkRunner(
                protocol_path, manifest, registry, registry.handle, broker
            )
            state_path = root / "tournament.json"
            tournament = WholeOSTournament(runner, state_path=state_path)

            recorded = tournament.run(
                stage="original", variant_id="MB0", task_id="task-00"
            )

            self.assertEqual(1, len(broker.executed))
            request = broker.executed[0]
            self.assertEqual("family-00", request.family_id)
            self.assertEqual(request.operation_id, recorded.operation_id)
            self.assertEqual(registry.snapshot.lease.lease_digest, recorded.lease_digest)
            self.assertEqual(
                manifest.recipes["MB0"].model_digest,
                recorded.metric.model_digest,
            )
            self.assertEqual(recorded, tournament.run(
                stage="original", variant_id="MB0", task_id="task-00"
            ))
            self.assertEqual(1, len(broker.executed))

            restored = WholeOSTournament(runner, state_path=state_path)
            self.assertEqual((recorded,), restored.attempts)
            document = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIsNone(document["pending"])
            self.assertEqual(2, document["schema_version"])

    def test_tournament_has_no_arbitrary_adapter_or_family_bypass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, manifest, protocol_path, registry = admitted_fixture(root)
            runner = AdmittedBenchmarkRunner(
                protocol_path, manifest, registry, registry.handle, RecordingBroker()
            )
            tournament = WholeOSTournament(runner, state_path=root / "state.json")
            with self.assertRaises(TypeError):
                cast(Any, tournament.run)(
                    stage="original",
                    variant_id="MB0",
                    task_id="task-00",
                    family_id="forged-family",
                    adapter=PinnedRecipeAdapter(manifest.recipes["MB1"]),
                )

    def test_forged_planned_lane_is_rejected_before_broker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, manifest, protocol_path, registry = admitted_fixture(root)
            broker = RecordingBroker()
            runner = AdmittedBenchmarkRunner(
                protocol_path, manifest, registry, registry.handle, broker
            )
            invocation = runner.plan(
                stage="original", variant_id="MB0", task_id="task-00"
            )
            forged = replace(
                invocation,
                request=replace(invocation.request, family_id="forged-family"),
            )
            with self.assertRaisesRegex(BenchmarkAdapterError, "live admitted lane"):
                runner.execute(forged)
            self.assertEqual([], broker.executed)

    def test_execution_exception_is_not_converted_to_a_receipt(self):
        class FailingBroker(RecordingBroker):
            def execute(self, request):
                self.executed.append(request)
                raise RuntimeError("external host unavailable")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, manifest, protocol_path, registry = admitted_fixture(root)
            broker = FailingBroker()
            runner = AdmittedBenchmarkRunner(
                protocol_path, manifest, registry, registry.handle, broker
            )
            state_path = root / "state.json"
            tournament = WholeOSTournament(runner, state_path=state_path)
            with self.assertRaisesRegex(RuntimeError, "host unavailable"):
                tournament.run(
                    stage="original", variant_id="MB0", task_id="task-00"
                )
            self.assertEqual((), tournament.attempts)
            document = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIsNotNone(document["pending"])
            self.assertNotIn("adapter_exception", state_path.read_text(encoding="utf-8"))

    def test_result_write_failure_reconciles_without_duplicate_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, manifest, protocol_path, registry = admitted_fixture(root)
            broker = RecordingBroker()
            runner = AdmittedBenchmarkRunner(
                protocol_path, manifest, registry, registry.handle, broker
            )
            tournament = WholeOSTournament(runner, state_path=root / "state.json")
            real_persist = tournament._persist
            calls = 0

            def fail_result_write():
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise TournamentError("RESULT_STORE_UNAVAILABLE")
                real_persist()

            with patch.object(tournament, "_persist", side_effect=fail_result_write):
                with self.assertRaisesRegex(TournamentError, "RESULT_STORE_UNAVAILABLE"):
                    tournament.run(
                        stage="original", variant_id="MB0", task_id="task-00"
                    )
            self.assertEqual((), tournament.attempts)
            recovered = tournament.run(
                stage="original", variant_id="MB0", task_id="task-00"
            )
            self.assertEqual(1, len(broker.executed))
            self.assertEqual(2, len(broker.inspected))
            self.assertEqual((recovered,), tournament.attempts)

    def test_execution_requires_a_durable_result_store(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, manifest, protocol_path, registry = admitted_fixture(root)
            broker = RecordingBroker()
            runner = AdmittedBenchmarkRunner(
                protocol_path, manifest, registry, registry.handle, broker
            )
            with self.assertRaisesRegex(TournamentError, "RESULT_STORE_REQUIRED"):
                WholeOSTournament(runner).run(
                    stage="original", variant_id="MB0", task_id="task-00"
                )
            self.assertEqual([], broker.executed)


if __name__ == "__main__":
    unittest.main()
