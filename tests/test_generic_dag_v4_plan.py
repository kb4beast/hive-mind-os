"""Product-level checks for the canonical Generic Hive Mind V4 plan."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from types import ModuleType

from hive_mind_os.activation_bundle import request_sha256, validate_draft_manifest
from hive_mind_os.dag_standard import (
    REQUIRED_LIFECYCLE_STAGES,
    REQUIRED_ROLES,
    compile_plan,
)
from hive_mind_os.portable_plan import PortablePlanBundle

ROOT = Path(__file__).resolve().parents[1]
V4 = ROOT / "docs/execution/dags/generic-hive-mind-product-v4"
PLAN = V4 / "plan.json"
MANIFEST = V4 / "manifest.json"
STANDARD = ROOT / "docs/execution/DAG_AUTHORING_STANDARD_V2.md"
V3_CONTRACTS = (
    ROOT / "docs/execution/dags/generic-hive-mind-product-v3/node-contracts.json"
)
EXPECTED_PLAN_SHA256 = (
    "sha256:283099b3d74af76c4320043044f763f2067d8c626a0e4e4e390560c1029176c1"
)
EXPECTED_PREDECESSOR_COMMIT = "ce692c0145d9c7611b34383974fde1c78903c5ef"
EXPECTED_PREDECESSOR_TREE = "86e502763fcfd924094ba8194dd0c31b114652a9"
PREDECESSOR_RECEIPT = (
    ROOT / "evidence/audits/generic-v3-baseline-recovery/V3-R4-QUALIFICATION.json"
)


def load_builder() -> ModuleType:
    path = V4 / "build_plan.py"
    spec = importlib.util.spec_from_file_location("_generic_v4_plan_builder", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import V4 builder: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GenericDagV4PlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.builder = load_builder()
        cls.raw = PLAN.read_bytes()
        cls.plan = PortablePlanBundle.from_bytes(cls.raw)

    def test_checked_plan_is_exact_canonical_builder_output(self) -> None:
        built = self.builder.build_plan().canonical_bytes()
        self.assertEqual(built, self.raw)
        self.assertFalse(self.raw.endswith(b"\n"))
        self.assertEqual(
            EXPECTED_PLAN_SHA256,
            "sha256:" + hashlib.sha256(self.raw).hexdigest(),
        )
        completed = subprocess.run(
            [sys.executable, "-B", str(V4 / "build_plan.py")],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr.decode("utf-8"))
        self.assertEqual(self.raw, completed.stdout)

    def test_compiler_reproduces_exact_topology_and_governance_coverage(self) -> None:
        receipt = compile_plan(
            self.raw,
            expected_plan_digest=EXPECTED_PLAN_SHA256,
            standard_bytes=STANDARD.read_bytes(),
            expected_request_id=self.plan.request_id,
            expected_subject_id=self.plan.subject.subject_id,
        )
        self.assertEqual(
            (20, 28, 17, 6),
            (
                receipt.metrics.node_count,
                receipt.metrics.raw_edge_count,
                receipt.metrics.dependency_level_count,
                receipt.metrics.transitive_direct_edge_count,
            ),
        )
        roles = {role for node in self.plan.nodes for role in node.roles}
        stages = {stage for node in self.plan.nodes for stage in node.lifecycle_stages}
        self.assertEqual(REQUIRED_ROLES, roles)
        self.assertEqual(REQUIRED_LIFECYCLE_STAGES, stages)
        source = json.loads(V3_CONTRACTS.read_text(encoding="utf-8"))
        self.assertEqual(
            [node["id"] for node in source["nodes"]],
            [node.node_id for node in self.plan.nodes],
        )

    def test_plan_is_bounded_to_main_and_denies_external_effects(self) -> None:
        repository = self.plan.subject.repository
        self.assertIsNotNone(repository)
        assert repository is not None
        self.assertEqual(self.builder.BASE_COMMIT, repository.commit)
        self.assertEqual(self.builder.BASE_TREE, repository.tree)
        self.assertEqual("main", repository.target_branch)
        self.assertEqual(
            request_sha256(self.builder.REQUEST_TEXT), self.plan.request_id
        )
        self.assertEqual("2026-12-31T23:59:59Z", self.plan.authority[0].expires_at)
        self.assertFalse(self.plan.authority[0].external_effects)
        self.assertGreaterEqual(
            set(self.plan.authority[0].denied_actions),
            {"credential", "deployment", "merge", "protected-merge", "push"},
        )

    def test_manifest_binds_plan_predecessor_candidate_base_and_request(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        validate_draft_manifest(manifest)
        self.assertEqual(self.builder.REQUEST_TEXT, manifest["request_text"])
        self.assertEqual(self.plan.request_id, manifest["request_sha256"])
        repository = self.plan.subject.repository
        assert repository is not None
        self.assertEqual(repository.repository_id, manifest["repository_id"])
        self.assertEqual(EXPECTED_PLAN_SHA256, manifest["plan"]["sha256"])
        self.assertEqual(20, manifest["plan"]["node_count"])
        self.assertEqual(
            {"commit": self.builder.BASE_COMMIT, "tree": self.builder.BASE_TREE},
            manifest["candidate_base"],
        )
        self.assertEqual(EXPECTED_PREDECESSOR_COMMIT, manifest["predecessor"]["commit"])
        self.assertEqual(EXPECTED_PREDECESSOR_TREE, manifest["predecessor"]["tree"])
        self.assertEqual(
            str(PREDECESSOR_RECEIPT.relative_to(ROOT)).replace("\\", "/"),
            manifest["predecessor"]["qualification_receipt_path"],
        )
        self.assertEqual(
            "sha256:" + hashlib.sha256(PREDECESSOR_RECEIPT.read_bytes()).hexdigest(),
            manifest["predecessor"]["qualification_receipt_sha256"],
        )
        self.assertFalse(manifest["execution_authorized"])


if __name__ == "__main__":
    unittest.main()
