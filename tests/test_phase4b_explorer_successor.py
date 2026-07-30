from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import hive_mind_os
import hive_mind_os.foundation.explorer_successor as successor_module
import hive_mind_os.package_system as package_system
from hive_mind_os.foundation.canonical import digest
from hive_mind_os.foundation.explorer_successor import (
    EXPECTED_SUCCESSOR_DIGEST,
    compile_explorer_successor,
    explorer_successor_bytes,
)
from hive_mind_os.foundation.explorer_successor_contracts import (
    validate_explorer_successor,
    validate_explorer_successor_catalog,
)
from hive_mind_os.foundation.generation import (
    compile_generation_zero_candidates,
    digest_bytes,
    verify_generated_candidates,
)
from scripts.phase1_surface_inventory import build_inventory, cli_inventory

REPOSITORY = Path(__file__).parents[1]
EXPECTED_LAYER_KINDS = (
    "base",
    "prompt",
    "playbook",
    "skills",
    "context",
    "output",
    "admission",
    "lifecycle",
)
FROZEN_FILES = {
    "src/hive_mind_os/foundation/canonical/agents/explorer.json": (
        "sha256:d20ac6051f772aecd25e4215eafac57c82da51f4a12eda3a7c20d0316112258a"
    ),
    "src/hive_mind_os/foundation/generated/agents/explorer.json": (
        "sha256:a9c3758f4a64d486c72e389871e4ea06521ea74b46b64969f881d0b05880308a"
    ),
    "src/hive_mind_os/foundation/generated/manifest.json": (
        "sha256:e652f81353af4d0abe41b656ff0a16d71368510b4b3efe985eed99976376659d"
    ),
}


def _reseal(document: dict[str, object]) -> None:
    body = {key: value for key, value in document.items() if key != "content_digest"}
    document["content_digest"] = digest(body)


class ExplorerSuccessorTests(unittest.TestCase):
    def test_compiler_is_deterministic_pinned_and_defensive(self) -> None:
        first = compile_explorer_successor()
        first["layers"][0]["layer_id"] = "forged"
        second = compile_explorer_successor()

        self.assertEqual(second["content_digest"], EXPECTED_SUCCESSOR_DIGEST)
        self.assertEqual(explorer_successor_bytes(), explorer_successor_bytes())
        self.assertNotEqual(second["layers"][0]["layer_id"], "forged")
        self.assertTrue(validate_explorer_successor_catalog().valid)
        self.assertTrue(validate_explorer_successor(second).valid)

    def test_successor_is_unique_ordered_and_inert(self) -> None:
        candidate = compile_explorer_successor()

        self.assertEqual(candidate["agent_id"], "hive-agent:explorer:v2-shadow-1")
        self.assertEqual(
            candidate["definition_id"],
            "hive-agent-definition:explorer:v2-shadow-1",
        )
        self.assertEqual(candidate["lineage_relation"], "extends-inert")
        self.assertEqual(
            tuple(layer["kind"] for layer in candidate["layers"]),
            EXPECTED_LAYER_KINDS,
        )
        self.assertEqual(
            tuple(layer["position"] for layer in candidate["layers"]),
            tuple(range(1, 9)),
        )
        self.assertEqual(
            candidate["requested_capabilities"],
            candidate["unsupported_capabilities"],
        )
        self.assertEqual(candidate["effective_capabilities"], [])
        self.assertEqual(candidate["tool_refs"], [])
        self.assertEqual(candidate["activation"], "inert")
        self.assertEqual(candidate["authority"], "none")
        self.assertFalse(candidate["public"])

    def test_phase2_sources_and_generated_outputs_remain_exact(self) -> None:
        generated = compile_generation_zero_candidates()
        observed = {
            path: (
                REPOSITORY / "src" / "hive_mind_os" / "foundation" / "generated" / path
            ).read_bytes()
            for path in generated
        }

        self.assertEqual(verify_generated_candidates(observed), ())
        self.assertEqual(set(generated), set(observed))
        for path, expected_digest in FROZEN_FILES.items():
            self.assertEqual(
                digest_bytes((REPOSITORY / path).read_bytes()),
                expected_digest,
            )

    def test_contract_rejects_layer_and_authority_tampering(self) -> None:
        candidate = compile_explorer_successor()
        mutations = []

        reversed_layers = deepcopy(candidate)
        reversed_layers["layers"].reverse()
        _reseal(reversed_layers)
        mutations.append(reversed_layers)

        duplicate_id = deepcopy(candidate)
        duplicate_id["layers"][1]["layer_id"] = duplicate_id["layers"][0]["layer_id"]
        _reseal(duplicate_id)
        mutations.append(duplicate_id)

        bad_layer_digest = deepcopy(candidate)
        bad_layer_digest["layers"][0]["digest"] = "sha256:" + ("0" * 64)
        _reseal(bad_layer_digest)
        mutations.append(bad_layer_digest)

        effective = deepcopy(candidate)
        effective["effective_capabilities"] = ["read_repository"]
        _reseal(effective)
        mutations.append(effective)

        unknown = deepcopy(candidate)
        unknown["runtime_binding"] = "forbidden"
        _reseal(unknown)
        mutations.append(unknown)

        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.assertFalse(validate_explorer_successor(mutation).valid)

    def test_contract_rejects_resealed_fixed_identity_substitutions(self) -> None:
        candidate = compile_explorer_successor()
        substitutions = []

        base = deepcopy(candidate)
        base["layers"][0]["layer_id"] = "substituted-base"
        base["layers"][0]["version"] = "99"
        base["layers"][0]["source_digests"][0] = "sha256:" + ("0" * 64)
        base["layers"][0]["digest"] = digest(
            {
                key: value
                for key, value in base["layers"][0].items()
                if key != "digest"
            }
        )
        _reseal(base)
        substitutions.append(base)

        playbook = deepcopy(candidate)
        playbook["playbook"]["lenses"][0] = "substituted-lens"
        _reseal(playbook)
        substitutions.append(playbook)

        governance = deepcopy(candidate)
        governance["governance"]["source_refs"][0] = "substituted-source"
        _reseal(governance)
        substitutions.append(governance)

        capability = deepcopy(candidate)
        capability["requested_capabilities"] = ["delete_repository"]
        capability["unsupported_capabilities"] = ["delete_repository"]
        _reseal(capability)
        substitutions.append(capability)

        for substitution in substitutions:
            with self.subTest(substitution=substitution):
                validation = validate_explorer_successor(substitution)
                self.assertFalse(validation.valid)
                self.assertIn("fixed-identity", " ".join(validation.issues))

    def test_dependency_drift_fails_closed(self) -> None:
        generated = compile_generation_zero_candidates()
        changed_generated = dict(generated)
        changed_generated["agents/explorer.json"] += b" "
        with patch.object(
            successor_module,
            "compile_generation_zero_candidates",
            return_value=changed_generated,
        ):
            with self.assertRaisesRegex(ValueError, "projection drifted"):
                compile_explorer_successor()

        changed_skills = successor_module.compile_shadow_skills()
        changed_skills["bundle_digest"] = "sha256:" + ("0" * 64)
        with patch.object(
            successor_module,
            "compile_shadow_skills",
            return_value=changed_skills,
        ):
            with self.assertRaisesRegex(ValueError, "reviewed.*digest"):
                compile_explorer_successor()

        with patch.object(
            successor_module,
            "_LENSES",
            successor_module._LENSES + ("unreviewed-lens",),
        ):
            with self.assertRaisesRegex(ValueError, "reviewed.*digest"):
                compile_explorer_successor()

    def test_packaged_phase2_byte_drift_fails_closed(self) -> None:
        generated = compile_generation_zero_candidates()
        with patch.object(
            successor_module,
            "verify_generated_candidates",
            return_value=("generated artifact drift: agents/explorer.json",),
        ):
            with self.assertRaisesRegex(ValueError, "packaged.*bytes drifted"):
                successor_module._verify_packaged_phase2_bytes(generated)

    def test_candidate_contains_only_bounded_definition_metadata(self) -> None:
        candidate = compile_explorer_successor()
        encoded = json.dumps(candidate, sort_keys=True)

        self.assertNotIn("IGNORE POLICY", encoded)
        self.assertNotIn("fixture discovery", encoded)
        self.assertNotIn("private memory", encoded)
        self.assertEqual(
            set(candidate["layers"][0]),
            {"position", "layer_id", "kind", "version", "source_digests", "digest"},
        )

    def test_no_supported_surface_or_runtime_activation_delta(self) -> None:
        inventory = build_inventory(REPOSITORY)

        self.assertEqual(len(hive_mind_os.__all__), 131)
        self.assertEqual(len(package_system.__all__), 33)
        self.assertEqual(cli_inventory()["parser_count"], 13)
        self.assertEqual(
            inventory["observable_module_surface"]["definition_count"],
            304,
        )
        self.assertEqual(
            inventory["runtime_effects"]["unclassified_candidate_count"],
            0,
        )


if __name__ == "__main__":
    unittest.main()
