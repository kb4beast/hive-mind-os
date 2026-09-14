import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import cast

from hive_mind_os.benchmark_adapters import (
    AdmittedBenchmarkRunner,
    BenchmarkAdapterError,
    BenchmarkAdapterManifest,
    BenchmarkResponse,
    RecipeClass,
    RecipeManifest,
    load_benchmark_adapter_manifest,
)
from hive_mind_os.campaign_metrics import (
    AdmissionRegistry,
    CampaignMetricsError,
    LeaseExhausted,
    canonical_digest,
)
from tests.test_campaign_metrics import (
    _FixtureRegistry,
    lease,
    plain,
    protocol,
    seal_for,
    stage_evidence,
)


class RecordingBroker:
    def __init__(self):
        self.responses = {}
        self.inspected = []
        self.executed = []

    def inspect(self, operation_id):
        self.inspected.append(operation_id)
        return self.responses.get(operation_id)

    def execute(self, request):
        self.executed.append(request)
        response = BenchmarkResponse(
            request.operation_id,
            "success",
            canonical_digest([request.operation_id, "result"]),
            canonical_digest([request.operation_id, "receipt"]),
            1.0,
            2.0,
            3.0,
            4.0,
        )
        self.responses[request.operation_id] = response
        return response


def adapter_manifest(p):
    classes = {
        "MB0": RecipeClass.CURRENT_BASELINE,
        "MB1": RecipeClass.MINIMAL_BUILDER,
        "MB2": RecipeClass.SDK_BUILDER,
        "MB3": RecipeClass.SELECTED_DESIGN,
        "MC0": RecipeClass.CURRENT_BASELINE,
        "MC1": RecipeClass.SELECTED_DESIGN,
        "MH1": RecipeClass.SELECTED_DESIGN,
        "MH2": RecipeClass.SELECTED_DESIGN,
        "MH3": RecipeClass.ABLATION,
        "MH4": RecipeClass.SELECTED_DESIGN,
    }
    recipes = {}
    for variant_id, raw in {
        **dict(p.entrant_recipes),
        **dict(p.hybrid_recipes),
    }.items():
        recipes[variant_id] = RecipeManifest(
            variant_id,
            classes[variant_id],
            raw["source_or_binary_digest"],
            raw["prompt_digest"],
            raw["model_digest"],
            raw["command_profile_digest"],
            raw["tool_digest"],
            raw["context_digest"],
            raw["check_policy_digest"],
            raw["learning_policy_digest"],
            ("benchmark-broker", "--variant", variant_id),
            {"TZ": "UTC", "NO_COLOR": "1"},
            ("dynamic-package-revision",) if variant_id == "MH3" else (),
        )
    signatures = p.experiment_manifest["manifest_signature_refs"]
    return BenchmarkAdapterManifest(
        "adapter-fixture-v1", p.protocol_id, recipes, signatures
    )


def admitted_fixture(root):
    initial = protocol()
    manifest = adapter_manifest(initial)
    experiment_manifest = dict(initial.experiment_manifest)
    experiment_manifest["recipe_manifest_digest"] = manifest.digest
    admitted_protocol = replace(initial, experiment_manifest=experiment_manifest)
    protocol_path = root / "closed-protocol.json"
    document = {
        "kind": "hive-mind-closed-match-protocol",
        "status": "CLOSED_ADMISSION_CANDIDATE",
        "external_evidence_obligations": [],
        **cast(dict[str, object], plain(admitted_protocol.to_document())),
        "protocol_digest": admitted_protocol.protocol_digest,
    }
    protocol_path.write_text(json.dumps(document), encoding="utf-8")
    evidence = stage_evidence(admitted_protocol, "original")
    lease_record = lease(
        admitted_protocol,
        "original",
        operations=("schedule", "execute", "apply", "seal", "aggregate", "decide"),
    )
    seal = seal_for(
        admitted_protocol,
        evidence,
        "MB0",
        1,
        canonical_digest("candidate-MB0"),
        11,
    )
    registry = _FixtureRegistry(
        admitted_protocol, evidence, lease_record, observed_at=20, history=(seal,)
    )
    return admitted_protocol, manifest, protocol_path, registry


def replace_registry_lease(registry, lease_record):
    admission_digest = canonical_digest(
        {
            "protocol_digest": registry.snapshot.protocol_digest,
            "stage_evidence": registry.snapshot.stage_evidence,
            "lease": lease_record,
        }
    )
    registry.snapshot = replace(
        registry.snapshot,
        admission_digest=admission_digest,
        lease=lease_record,
    )


class BenchmarkAdapterTests(unittest.TestCase):
    def test_manifest_round_trip_is_closed_and_digest_bound(self):
        p = protocol()
        manifest = adapter_manifest(p)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest.to_document()), encoding="utf-8")
            restored = load_benchmark_adapter_manifest(path)
            self.assertEqual(restored.digest, manifest.digest)
            document = dict(manifest.to_document())
            document["unexpected"] = True
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(BenchmarkAdapterError):
                load_benchmark_adapter_manifest(path)

    def test_checked_in_open_protocol_never_reaches_registry_or_broker(self):
        class ExplodingRegistry:
            def resolve(self, *_):
                raise AssertionError("OPEN protocol reached registry")

        p = protocol()
        with self.assertRaisesRegex(CampaignMetricsError, "OPEN"):
            AdmittedBenchmarkRunner(
                "docs/benchmarks/whole-os-match-protocol.json",
                adapter_manifest(p),
                cast(AdmissionRegistry, ExplodingRegistry()),
                object(),
                RecordingBroker(),
            )

    def test_admitted_runner_generates_exact_request_and_reconciles_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            p, manifest, protocol_path, registry = admitted_fixture(root)
            broker = RecordingBroker()
            runner = AdmittedBenchmarkRunner(
                protocol_path, manifest, registry, registry.handle, broker
            )
            first = runner.plan(
                stage="original", variant_id="MB0", task_id="task-00"
            )
            second = runner.plan(
                stage="original", variant_id="MB0", task_id="task-00"
            )
            self.assertEqual(first.request, second.request)
            self.assertEqual(first.request.argv, manifest.recipes["MB0"].argv)
            self.assertEqual(first.request.candidate_digest, canonical_digest("candidate-MB0"))
            self.assertEqual(first.request.lease_handle, registry.snapshot.lease.lease_digest)
            self.assertEqual(first.request.execution_binding_digest, first.execution_binding_digest)
            one = runner.execute(first)
            two = runner.execute(second)
            self.assertEqual(one, two)
            self.assertEqual(len(broker.executed), 1)
            self.assertEqual(len(broker.inspected), 2)
            self.assertGreaterEqual(registry.resolve_calls.count("execute"), 4)
            self.assertEqual(p.protocol_id, first.request.experiment_id)

    def test_runner_rejects_unsealed_variant_manifest_drift_and_revoked_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            p, manifest, protocol_path, registry = admitted_fixture(root)
            runner = AdmittedBenchmarkRunner(
                protocol_path, manifest, registry, registry.handle, RecordingBroker()
            )
            with self.assertRaisesRegex(BenchmarkAdapterError, "candidate seal"):
                runner.plan(stage="original", variant_id="MB1", task_id="task-00")

            changed = dict(manifest.recipes)
            changed["MB0"] = replace(changed["MB0"], argv=("different",))
            drifted = BenchmarkAdapterManifest(
                manifest.manifest_id, manifest.protocol_id, changed, manifest.signature_refs
            )
            with self.assertRaisesRegex(BenchmarkAdapterError, "admitted manifest"):
                AdmittedBenchmarkRunner(
                    protocol_path,
                    drifted,
                    registry,
                    registry.handle,
                    RecordingBroker(),
                ).plan(stage="original", variant_id="MB0", task_id="task-00")

            replace_registry_lease(
                registry, replace(registry.snapshot.lease, revoked_at=19)
            )
            with self.assertRaises(LeaseExhausted):
                runner.plan(stage="original", variant_id="MB0", task_id="task-00")

    def test_runner_requires_execute_operation_and_exact_repetition(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            p, manifest, protocol_path, registry = admitted_fixture(root)
            runner = AdmittedBenchmarkRunner(
                protocol_path, manifest, registry, registry.handle, RecordingBroker()
            )
            with self.assertRaisesRegex(BenchmarkAdapterError, "repetition"):
                runner.plan(
                    stage="original",
                    variant_id="MB0",
                    task_id="task-00",
                    repetition=1,
                )
            replace_registry_lease(
                registry,
                replace(
                    registry.snapshot.lease,
                    operations=frozenset(("schedule", "apply", "seal", "aggregate", "decide")),
                ),
            )
            with self.assertRaisesRegex(CampaignMetricsError, "does not allow"):
                runner.plan(stage="original", variant_id="MB0", task_id="task-00")

    def test_runner_revalidates_lease_after_planning_before_broker(self):
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
            replace_registry_lease(
                registry, replace(registry.snapshot.lease, revoked_at=19)
            )

            with self.assertRaises(LeaseExhausted):
                runner.execute(invocation)
            self.assertEqual([], broker.inspected)
            self.assertEqual([], broker.executed)


if __name__ == "__main__":
    unittest.main()
