from __future__ import annotations

import json
import runpy
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

from hive_mind_os.dag_standard import (
    WORK_PACKAGE_COMPILER_PACKAGE_DIGEST,
    WORK_PACKAGE_COMPILER_PACKAGE_ID,
    compile_plan,
)
from hive_mind_os.plan_generation import PinnedArtifact, PlanGenerationRequest
from hive_mind_os.plan_lineage import ActivationMaterial
from hive_mind_os.portable_plan import PortablePlanBundle
from hive_mind_os.runtime_contracts import ContractViolation, raw_sha256
from hive_mind_os.tournament_plan_factory import (
    TournamentPlanFactory,
    WholeOSPlanFactory,
)
from tests.test_tournament_plan_factory import authority, evidence, request

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/plan/whole-os-implementation"
HANDOFF = ROOT / "docs/plan/whole-os-tournament-2026-09-13"
STANDARD = (ROOT / "docs/execution/DAG_AUTHORING_STANDARD_V2.md").read_bytes()
SOURCE_INVENTORY = (OUTPUT / "source-inventory.json").read_bytes()
REQUIREMENTS_PATH = HANDOFF / "requirements.json"
REQUIREMENTS = REQUIREMENTS_PATH.read_bytes()


def load_plan() -> PortablePlanBundle:
    return PortablePlanBundle.from_bytes(
        (OUTPUT / "whole-os-plan-v2.json").read_bytes()
    )


class WholeOSPlanContractTests(unittest.TestCase):
    def test_checked_plan_compiles_all_handoff_nodes_and_requirements(self) -> None:
        plan = load_plan()
        dag = json.loads((HANDOFF / "dag-index.json").read_text(encoding="utf-8"))
        receipt = compile_plan(
            plan.canonical_bytes(),
            expected_plan_digest=plan.digest(),
            standard_bytes=STANDARD,
            expected_request_id=plan.request_id,
            expected_subject_id=plan.subject.subject_id,
            source_inventory_bytes=SOURCE_INVENTORY,
            requirements_bytes=REQUIREMENTS,
        )
        self.assertEqual(2, plan.schema_version)
        self.assertEqual(WORK_PACKAGE_COMPILER_PACKAGE_ID, receipt.compiler_package_id)
        self.assertEqual(
            WORK_PACKAGE_COMPILER_PACKAGE_DIGEST,
            receipt.compiler_package_digest,
        )
        self.assertEqual(34, receipt.metrics.node_count)
        self.assertEqual(
            {item["id"]: tuple(item["dependencies"]) for item in dag["nodes"]},
            {item.node_id: item.dependencies for item in plan.nodes},
        )
        self.assertEqual(
            {f"R{index:02d}" for index in range(1, 19)},
            {
                requirement
                for node in plan.nodes
                for requirement in node.work_package.requirement_ids
            },
        )
        self.assertFalse(
            any(
                capability.effect_class == "external-reversible"
                for capability in plan.capabilities
            )
        )
        self.assertFalse(plan.authority[0].external_effects)

    def test_checked_plan_is_exact_factory_output_and_v1_profile_survives(self) -> None:
        plan = load_plan()
        repository = plan.subject.repository
        assert repository is not None
        generation_request = PlanGenerationRequest(
            plan.request_id,
            plan.objective_digest,
            plan.subject.subject_id,
            plan.subject.kind.value,
            repository.repository_id,
            repository.target_branch,
            repository.commit,
            repository.tree,
            None,
        )
        contracts = json.loads(
            (OUTPUT / "whole-os-node-contracts-v2.json").read_text(encoding="utf-8")
        )
        rebuilt = WholeOSPlanFactory().build(
            generation_request,
            standard=PinnedArtifact.pin("dag-standard-v2", STANDARD),
            authority=plan.authority[0],
            evidence=plan.evidence,
            node_contracts=contracts,
            source_inventory=PinnedArtifact.pin(
                "n00-source-inventory", SOURCE_INVENTORY
            ),
            requirements=PinnedArtifact.pin("n00-requirements", REQUIREMENTS),
        )
        self.assertEqual(plan.canonical_bytes(), rebuilt.canonical_bytes())

        substituted_inventory = json.loads(json.dumps(contracts))
        substituted_inventory["source_inventory"]["sha256"] = raw_sha256(
            b"substituted inventory"
        )
        with self.assertRaisesRegex(ContractViolation, "accepted N00 inventory"):
            WholeOSPlanFactory().build(
                generation_request,
                standard=PinnedArtifact.pin("dag-standard-v2", STANDARD),
                authority=plan.authority[0],
                evidence=plan.evidence,
                node_contracts=substituted_inventory,
                source_inventory=PinnedArtifact.pin(
                    "n00-source-inventory", SOURCE_INVENTORY
                ),
                requirements=PinnedArtifact.pin("n00-requirements", REQUIREMENTS),
            )

        compatibility = TournamentPlanFactory().build(
            request(),
            standard=PinnedArtifact.pin("standard", STANDARD),
            authority=authority(),
            evidence=evidence(),
        )
        compatibility_receipt = compile_plan(
            compatibility.canonical_bytes(),
            expected_plan_digest=compatibility.digest(),
            standard_bytes=STANDARD,
        )
        self.assertEqual(1, compatibility.schema_version)
        self.assertEqual(13, compatibility_receipt.metrics.node_count)

    def test_prose_contracts_bind_exact_locks_paths_and_sections(self) -> None:
        source = runpy.run_path(
            str(ROOT / "scripts/generate_whole_os_plan_artifacts.py")
        )
        contracts = json.loads(
            (OUTPUT / "whole-os-node-contracts-v2.json").read_text(encoding="utf-8")
        )
        inventory = json.loads(
            (OUTPUT / "source-inventory.json").read_text(encoding="utf-8")
        )
        source_ids = {item["id"] for item in inventory["sources"]}
        by_id = {item["id"]: item for item in contracts["nodes"]}
        self.assertEqual(set(source["LOCKS"]), set(by_id))
        self.assertEqual(set(source["WRITE_PATHS"]), set(by_id))
        for node_id, item in by_id.items():
            self.assertEqual(list(source["LOCKS"][node_id]), item["semantic_locks"])
            self.assertEqual(list(source["WRITE_PATHS"][node_id]), item["write_paths"])
            self.assertNotIn("planning_group", item)
            self.assertTrue(item["output_contracts"])
            self.assertTrue(item["source_ids"])
            self.assertLessEqual(set(item["source_ids"]), source_ids)
            self.assertTrue(item["acceptance_criteria"])
            self.assertTrue(item["contract_digest"].startswith("sha256:"))
            self.assertTrue(all("\\" not in path for path in item["write_paths"]))
            self.assertNotIn("planning_group", item["semantic_locks"])
            sections = source["_sections"](ROOT / item["contract_path"])
            self.assertEqual(
                raw_sha256(sections[node_id].encode("utf-8")),
                item["contract_digest"],
            )
        self.assertEqual(
            ["plan-schema", "architecture-decision-index"],
            by_id["N01"]["semantic_locks"],
        )
        self.assertEqual(
            "draft:subject:external-mission-id:claim-id",
            by_id["N20"]["semantic_locks"][0],
        )

    def test_lock_aware_rounds_serialize_shared_paths(self) -> None:
        plan = load_plan()
        receipt = compile_plan(
            plan.canonical_bytes(),
            expected_plan_digest=plan.digest(),
            standard_bytes=STANDARD,
            source_inventory_bytes=SOURCE_INVENTORY,
            requirements_bytes=REQUIREMENTS,
        )
        rounds = {
            node_id: item.round_index
            for item in receipt.rounds
            for node_id in item.node_ids
        }
        self.assertNotEqual(rounds["N11"], rounds["N15"])
        self.assertNotEqual(rounds["N14"], rounds["N18"])

    def test_factory_and_compiler_reject_namespace_substitution_before_seal(
        self,
    ) -> None:
        plan = load_plan()
        repository = plan.subject.repository
        assert repository is not None
        generation_request = PlanGenerationRequest(
            plan.request_id,
            plan.objective_digest,
            plan.subject.subject_id,
            plan.subject.kind.value,
            repository.repository_id,
            repository.target_branch,
            repository.commit,
            repository.tree,
            None,
        )
        contracts = json.loads(
            (OUTPUT / "whole-os-node-contracts-v2.json").read_text(encoding="utf-8")
        )
        source_artifact = PinnedArtifact.pin("n00-source-inventory", SOURCE_INVENTORY)
        requirements_artifact = PinnedArtifact.pin("n00-requirements", REQUIREMENTS)

        bogus_source = json.loads(json.dumps(contracts))
        bogus_source["nodes"][1]["source_ids"].append("GOV-NONEXISTENT")
        with self.assertRaisesRegex(ContractViolation, "unadmitted source"):
            WholeOSPlanFactory().build(
                generation_request,
                standard=PinnedArtifact.pin("dag-standard-v2", STANDARD),
                authority=plan.authority[0],
                evidence=plan.evidence,
                node_contracts=bogus_source,
                source_inventory=source_artifact,
                requirements=requirements_artifact,
            )
        sealer = Mock()
        with self.assertRaisesRegex(ContractViolation, "unadmitted source"):
            WholeOSPlanFactory(generator=sealer).generate(
                generation_request,
                standard=PinnedArtifact.pin("dag-standard-v2", STANDARD),
                authority=plan.authority[0],
                evidence=plan.evidence,
                node_contracts=bogus_source,
                source_inventory=source_artifact,
                requirements=requirements_artifact,
                node_mappings=PinnedArtifact.pin("node-mappings", b"mapping"),
                sources=(),
                compiler=PinnedArtifact.pin("compiler", b"compiler"),
            )
        sealer.generate.assert_not_called()

        substituted_source_evidence = tuple(
            replace(item, claim_ids=("N00-SUBSTITUTED",))
            if item.evidence_id == "accepted-n00-inventory"
            else item
            for item in plan.evidence
        )
        with self.assertRaisesRegex(ContractViolation, "evidence bindings"):
            WholeOSPlanFactory().build(
                generation_request,
                standard=PinnedArtifact.pin("dag-standard-v2", STANDARD),
                authority=plan.authority[0],
                evidence=substituted_source_evidence,
                node_contracts=contracts,
                source_inventory=source_artifact,
                requirements=requirements_artifact,
            )

        colluding_requirements = json.loads(json.dumps(contracts))
        for node in colluding_requirements["nodes"]:
            node["requirement_ids"] = [
                "R99" if item == "R01" else item for item in node["requirement_ids"]
            ]
        colluding_requirements["requirement_inventory"]["requirement_ids"] = [
            "R99" if item == "R01" else item
            for item in colluding_requirements["requirement_inventory"][
                "requirement_ids"
            ]
        ]
        with self.assertRaisesRegex(ContractViolation, "not accepted N00"):
            WholeOSPlanFactory().build(
                generation_request,
                standard=PinnedArtifact.pin("dag-standard-v2", STANDARD),
                authority=plan.authority[0],
                evidence=plan.evidence,
                node_contracts=colluding_requirements,
                source_inventory=source_artifact,
                requirements=requirements_artifact,
            )

        altered_requirements = json.loads(REQUIREMENTS)
        altered_requirements["requirements"][0]["id"] = "R99"
        with self.assertRaisesRegex(ContractViolation, "accepted N00 bytes"):
            WholeOSPlanFactory().build(
                generation_request,
                standard=PinnedArtifact.pin("dag-standard-v2", STANDARD),
                authority=plan.authority[0],
                evidence=plan.evidence,
                node_contracts=contracts,
                source_inventory=source_artifact,
                requirements=PinnedArtifact.pin(
                    "altered-requirements",
                    json.dumps(altered_requirements, sort_keys=True).encode("utf-8"),
                ),
            )

        colluding_plan = plan.to_document()
        for node in colluding_plan["nodes"]:
            node["work_package"]["requirement_ids"] = [
                "R99" if item == "R01" else item
                for item in node["work_package"]["requirement_ids"]
            ]
        accepted_evidence = next(
            item
            for item in colluding_plan["evidence"]
            if item["evidence_id"] == "accepted-n00-requirements"
        )
        accepted_evidence["claim_ids"] = [
            "R99" if item == "R01" else item for item in accepted_evidence["claim_ids"]
        ]
        candidate = PortablePlanBundle.from_document(colluding_plan)
        with self.assertRaisesRegex(ContractViolation, "accepted N00 evidence"):
            compile_plan(
                candidate.canonical_bytes(),
                expected_plan_digest=candidate.digest(),
                standard_bytes=STANDARD,
                source_inventory_bytes=SOURCE_INVENTORY,
                requirements_bytes=REQUIREMENTS,
            )

        with self.assertRaisesRegex(ContractViolation, "pinned requirements bytes"):
            compile_plan(
                plan.canonical_bytes(),
                expected_plan_digest=plan.digest(),
                standard_bytes=STANDARD,
                source_inventory_bytes=SOURCE_INVENTORY,
            )

    def test_missing_role_output_unknown_route_cycle_and_lost_claim_reject(
        self,
    ) -> None:
        base = load_plan().to_document()

        missing_role = json.loads(json.dumps(base))
        missing_role["nodes"][0]["roles"] = []
        with self.assertRaisesRegex(ContractViolation, "roles"):
            PortablePlanBundle.from_document(missing_role)

        missing_output = json.loads(json.dumps(base))
        missing_output["nodes"][0]["work_package"]["output_contracts"] = []
        with self.assertRaisesRegex(ContractViolation, "output_contracts"):
            PortablePlanBundle.from_document(missing_output)

        missing_execution = json.loads(json.dumps(base))
        del missing_execution["nodes"][0]["execution"]
        with self.assertRaisesRegex(ContractViolation, "execution contract"):
            PortablePlanBundle.from_document(missing_execution)

        mismatched_output = json.loads(json.dumps(base))
        mismatched_output["nodes"][0]["execution"]["required_outputs"] = [
            "substituted-output"
        ]
        with self.assertRaisesRegex(ContractViolation, "outputs do not match"):
            PortablePlanBundle.from_document(mismatched_output)

        control_path = json.loads(json.dumps(base))
        control_path["nodes"][0]["work_package"]["write_paths"][0] = (
            "docs/plan\u0000injected.md"
        )
        with self.assertRaisesRegex(ContractViolation, "control character"):
            PortablePlanBundle.from_document(control_path)

        unicode_path = json.loads(json.dumps(base))
        unicode_path["nodes"][0]["work_package"]["write_paths"][0] = "docs/caf\u00e9.md"
        with self.assertRaisesRegex(ContractViolation, "ASCII"):
            PortablePlanBundle.from_document(unicode_path)

        unknown_route = json.loads(json.dumps(base))
        unknown_route["nodes"][0]["work_package"]["minimum_route"] = "T4"
        with self.assertRaisesRegex(ContractViolation, "minimum route"):
            PortablePlanBundle.from_document(unknown_route)

        cycle = json.loads(json.dumps(base))
        cycle["nodes"][0]["dependencies"] = ["N33"]
        with self.assertRaisesRegex(ContractViolation, "cycle"):
            PortablePlanBundle.from_document(cycle)

        lost_claim = json.loads(json.dumps(base))
        lost_claim["nodes"][1]["work_package"]["requirement_ids"].remove("R16")
        candidate = PortablePlanBundle.from_document(lost_claim)
        with self.assertRaisesRegex(ContractViolation, "lose or substitute"):
            compile_plan(
                candidate.canonical_bytes(),
                expected_plan_digest=candidate.digest(),
                standard_bytes=STANDARD,
                source_inventory_bytes=SOURCE_INVENTORY,
                requirements_bytes=REQUIREMENTS,
            )

        bogus_source = json.loads(json.dumps(base))
        bogus_source["nodes"][1]["work_package"]["source_ids"].append("BOGUS-SOURCE-99")
        candidate = PortablePlanBundle.from_document(bogus_source)
        with self.assertRaisesRegex(ContractViolation, "unadmitted source"):
            compile_plan(
                candidate.canonical_bytes(),
                expected_plan_digest=candidate.digest(),
                standard_bytes=STANDARD,
                source_inventory_bytes=SOURCE_INVENTORY,
                requirements_bytes=REQUIREMENTS,
            )

        with self.assertRaisesRegex(ContractViolation, "source-inventory bytes"):
            compile_plan(
                load_plan().canonical_bytes(),
                expected_plan_digest=load_plan().digest(),
                standard_bytes=STANDARD,
                requirements_bytes=REQUIREMENTS,
            )

        substituted_sources = json.loads(SOURCE_INVENTORY)
        substituted_sources["sources"][0]["id"] = "SUBSTITUTED-SOURCE"
        with self.assertRaisesRegex(ContractViolation, "accepted N00"):
            compile_plan(
                load_plan().canonical_bytes(),
                expected_plan_digest=load_plan().digest(),
                standard_bytes=STANDARD,
                source_inventory_bytes=(
                    json.dumps(substituted_sources, sort_keys=True).encode("utf-8")
                ),
                requirements_bytes=REQUIREMENTS,
            )

    def test_altered_standard_and_unauthorized_effect_reject(self) -> None:
        plan = load_plan()
        with self.assertRaisesRegex(ContractViolation, "standard raw digest"):
            compile_plan(
                plan.canonical_bytes(),
                expected_plan_digest=plan.digest(),
                standard_bytes=STANDARD + b"altered",
                source_inventory_bytes=SOURCE_INVENTORY,
                requirements_bytes=REQUIREMENTS,
            )
        unauthorized = replace(
            plan,
            capabilities=(
                replace(plan.capabilities[0], effect_class="external-reversible"),
                *plan.capabilities[1:],
            ),
        )
        with self.assertRaisesRegex(ContractViolation, "lacks authority"):
            compile_plan(
                unauthorized.canonical_bytes(),
                expected_plan_digest=unauthorized.digest(),
                standard_bytes=STANDARD,
                source_inventory_bytes=SOURCE_INVENTORY,
                requirements_bytes=REQUIREMENTS,
            )

    def test_generation_and_dispatcher_are_permanent_inert_artifacts(self) -> None:
        plan_bytes = (OUTPUT / "whole-os-plan-v2.json").read_bytes()
        manifest_bytes = (OUTPUT / "generation-manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes)
        activation = ActivationMaterial(
            manifest["generation"]["generation_id"],
            plan_bytes,
            manifest_bytes,
            raw_sha256(plan_bytes),
            raw_sha256(manifest_bytes),
        )
        self.assertEqual(raw_sha256(plan_bytes), activation.plan_digest)
        self.assertNotIn("signature", manifest)
        self.assertTrue(manifest["authentication"]["host_signature_required"])

        copied_signature = json.loads(json.dumps(manifest))
        copied_signature["signature"] = "copied-old-signature"
        copied_bytes = json.dumps(
            copied_signature, separators=(",", ":"), sort_keys=True
        ).encode()
        with self.assertRaisesRegex(ContractViolation, "not closed"):
            ActivationMaterial(
                manifest["generation"]["generation_id"],
                plan_bytes,
                copied_bytes,
                raw_sha256(plan_bytes),
                raw_sha256(copied_bytes),
            )

        dispatcher = json.loads(
            (OUTPUT / "DISPATCHER.json").read_text(encoding="utf-8")
        )
        self.assertEqual("INACTIVE", dispatcher["status"])
        self.assertFalse(dispatcher["authority_granted"])
        self.assertFalse(dispatcher["dispatch_policy"]["planning_group_is_lock"])
        for path_key, digest_key in (
            ("plan_path", "plan_digest"),
            ("generation_manifest_path", "generation_manifest_digest"),
            ("node_contracts_path", "node_contracts_digest"),
            ("node_prompt_path", "node_prompt_digest"),
            ("node_prompt_renderer_path", "node_prompt_renderer_digest"),
            ("source_inventory_path", "source_inventory_digest"),
        ):
            self.assertEqual(
                dispatcher[digest_key],
                raw_sha256((ROOT / dispatcher[path_key]).read_bytes()),
            )
        self.assertTrue(dispatcher["dispatch_policy"]["structured_renderer_required"])

    def test_canonical_contract_path_is_closed_across_permanent_artifacts(
        self,
    ) -> None:
        source = runpy.run_path(
            str(ROOT / "scripts/generate_whole_os_plan_artifacts.py")
        )
        current = source["CURRENT_NODE_CONTRACTS_PATH"]
        historical = source["HISTORICAL_NODE_CONTRACTS_PATH"]
        current_declaration = source["CURRENT_CONTRACT_DECLARATION"]
        historical_declaration = source["HISTORICAL_CONTRACT_DECLARATION"]
        contracts = json.loads((ROOT / current).read_text(encoding="utf-8"))
        prompt_text = (OUTPUT / "NODE_PROMPT.md").read_text(encoding="utf-8")
        plan_text = (OUTPUT / "PLAN.md").read_text(encoding="utf-8")
        dispatcher = json.loads(
            (OUTPUT / "DISPATCHER.json").read_text(encoding="utf-8")
        )

        self.assertEqual(
            "docs/plan/whole-os-implementation/whole-os-node-contracts-v2.json",
            current,
        )
        self.assertEqual("whole-os-node-contracts/v2", contracts["schema"])
        self.assertEqual(current, dispatcher["node_contracts_path"])
        self.assertEqual(historical, dispatcher["historical_node_contracts"]["path"])
        self.assertFalse(dispatcher["historical_node_contracts"]["admission_allowed"])
        for content in (prompt_text, plan_text):
            self.assertEqual(1, content.count(current_declaration))
            self.assertEqual(1, content.count(historical_declaration))

        validate = source["_validate_contract_selection"]
        validate(
            contracts,
            template_text=prompt_text,
            plan_text=plan_text,
            dispatcher=dispatcher,
        )
        with self.assertRaisesRegex(ValueError, "current canonical contract"):
            validate(
                contracts,
                template_text=prompt_text.replace(current, historical, 1),
                plan_text=plan_text,
                dispatcher=dispatcher,
            )
        with self.assertRaisesRegex(ValueError, "current canonical contract"):
            validate(
                contracts,
                template_text=prompt_text,
                plan_text=plan_text.replace(current, historical, 1),
                dispatcher=dispatcher,
            )
        divergent_dispatcher = json.loads(json.dumps(dispatcher))
        divergent_dispatcher["node_contracts_path"] = historical
        with self.assertRaisesRegex(ValueError, "canonical v2 contract"):
            validate(
                contracts,
                template_text=prompt_text,
                plan_text=plan_text,
                dispatcher=divergent_dispatcher,
            )

    def test_regeneration_is_byte_deterministic(self) -> None:
        paths = tuple(
            OUTPUT / name
            for name in (
                "whole-os-node-contracts-v2.json",
                "whole-os-plan-v2.json",
                "generation-manifest.json",
                "DISPATCHER.json",
            )
        )
        expected = {path: path.read_bytes() for path in paths}
        source = runpy.run_path(
            str(ROOT / "scripts/generate_whole_os_plan_artifacts.py")
        )
        source["main"]()
        self.assertEqual(expected, {path: path.read_bytes() for path in paths})

    def test_generator_admission_failure_precedes_every_artifact_write(self) -> None:
        paths = tuple(
            OUTPUT / name
            for name in (
                "whole-os-node-contracts-v2.json",
                "whole-os-plan-v2.json",
                "generation-manifest.json",
                "DISPATCHER.json",
            )
        )
        expected = {path: path.read_bytes() for path in paths}
        source = runpy.run_path(
            str(ROOT / "scripts/generate_whole_os_plan_artifacts.py")
        )

        class RefusingFactory:
            def build(self, *args: object, **kwargs: object) -> None:
                raise ContractViolation("fixture admission refusal")

        source["main"].__globals__["WholeOSPlanFactory"] = RefusingFactory
        with self.assertRaisesRegex(ContractViolation, "admission refusal"):
            source["main"]()
        self.assertEqual(expected, {path: path.read_bytes() for path in paths})


if __name__ == "__main__":
    unittest.main()
