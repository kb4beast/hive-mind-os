from __future__ import annotations

import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from hive_mind_os.plan_generation import (
    PinnedArtifact,
    PlanGenerationRequest,
    PlanGenerator,
)
from hive_mind_os.portable_plan import StandardBinding
from hive_mind_os.runtime_contracts import ContractViolation, raw_sha256
from tests.test_portable_plan import make_plan


def generation_fixture(*, repository: bool = True):
    standard_bytes = b"portable DAG standard v2\n"
    plan = make_plan(repository=repository)
    plan = replace(
        plan,
        standard=StandardBinding(
            2,
            "docs/execution/DAG_AUTHORING_STANDARD_V2.md",
            raw_sha256(standard_bytes),
            len(standard_bytes),
            "c" * 40,
            "hive-mind-standard-v2",
            "sha256:" + "9" * 64,
        ),
    )
    repository_binding = plan.subject.repository
    request = PlanGenerationRequest(
        plan.request_id,
        plan.objective_digest,
        plan.subject.subject_id,
        plan.subject.kind.value,
        None if repository_binding is None else repository_binding.repository_id,
        "artifact/channel"
        if repository_binding is None
        else repository_binding.target_branch,
        None if repository_binding is None else repository_binding.commit,
        None if repository_binding is None else repository_binding.tree,
        None,
    )
    arguments = {
        "node_mappings": PinnedArtifact.pin("node-mappings", b"node mappings\n"),
        "sources": (
            PinnedArtifact.pin("source-a", b"source a\n"),
            PinnedArtifact.pin("source-b", b"source b\n"),
        ),
        "standard": PinnedArtifact.pin("standard", standard_bytes),
        "standard_version": 2,
        "compiler": PinnedArtifact.pin("compiler", b"compiler bytes\n"),
    }
    return plan, request, arguments


class PlanGenerationTests(unittest.TestCase):
    def test_generation_exports_complete_plan_and_external_manifest_bytes(self) -> None:
        plan, request, arguments = generation_fixture()
        generated, inserted = PlanGenerator().generate(request, plan, **arguments)
        self.assertTrue(inserted)
        self.assertEqual(
            plan.canonical_bytes(), generated.activation_material.complete_plan_bytes
        )
        manifest = json.loads(generated.activation_material.external_manifest_bytes)
        self.assertEqual(
            generated.record.generation_id, manifest["generation"]["generation_id"]
        )
        self.assertEqual(generated.record.plan_digest, manifest["plan_digest"])
        self.assertEqual(
            {
                "host_signature_required": True,
                "distinct_key_required": True,
                "repository_signature_forbidden": True,
            },
            manifest["authentication"],
        )

    def test_exact_generation_repeat_is_idempotent_even_under_concurrency(self) -> None:
        plan, request, arguments = generation_fixture()
        generator = PlanGenerator()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(
                pool.map(
                    lambda _: generator.generate(request, plan, **arguments), range(16)
                )
            )
        self.assertEqual(1, sum(1 for _, inserted in results if inserted))
        self.assertEqual(1, len({item.record.generation_id for item, _ in results}))
        self.assertEqual(1, len(generator.lineage.records()))

    def test_stale_request_tree_or_standard_substitution_fails_closed(self) -> None:
        plan, request, arguments = generation_fixture()
        with self.assertRaisesRegex(ContractViolation, "stale or bound"):
            PlanGenerator().generate(
                replace(request, parent_tree="d" * 40), plan, **arguments
            )
        with self.assertRaisesRegex(ContractViolation, "standard binding"):
            PlanGenerator().generate(
                request, plan, **{**arguments, "standard_version": 1}
            )
        with self.assertRaisesRegex(ContractViolation, "digest mismatch"):
            PinnedArtifact("source", b"actual", "sha256:" + "0" * 64)

    def test_non_repository_generation_has_no_implicit_git_or_host_authority(
        self,
    ) -> None:
        plan, request, arguments = generation_fixture(repository=False)
        generated, _ = PlanGenerator().generate(request, plan, **arguments)
        self.assertIsNone(generated.record.repository_id)
        self.assertIsNone(generated.record.parent_commit)
        self.assertFalse(hasattr(generated, "execute"))
        with self.assertRaisesRegex(ContractViolation, "repository bindings"):
            PlanGenerator().generate(
                replace(request, repository_id="sha256:" + "0" * 64), plan, **arguments
            )

    def test_generation_identity_changes_for_source_mapping_compiler_or_plan(
        self,
    ) -> None:
        plan, request, arguments = generation_fixture()
        first, _ = PlanGenerator().generate(request, plan, **arguments)
        changed_arguments = {
            **arguments,
            "node_mappings": PinnedArtifact.pin("node-mappings", b"changed\n"),
        }
        second, _ = PlanGenerator().generate(request, plan, **changed_arguments)
        compiler_arguments = {
            **arguments,
            "compiler": PinnedArtifact.pin("compiler", b"changed compiler\n"),
        }
        third, _ = PlanGenerator().generate(request, plan, **compiler_arguments)
        self.assertEqual(
            3,
            len(
                {
                    first.record.generation_id,
                    second.record.generation_id,
                    third.record.generation_id,
                }
            ),
        )


if __name__ == "__main__":
    unittest.main()
