from __future__ import annotations

import unittest

from hive_mind_os.brain_kernel.canonical import canonical_bytes
from hive_mind_os.brain_kernel.contracts import MissionCharter, MissionState, Budget
from hive_mind_os.contracts import KERNEL_SCHEMA_NAMES, validate_contract, validate_schema_catalog


DIGEST = "sha256:" + "0" * 64
SHA = "0" * 40


class HiveCortexContractCompatibilityTests(unittest.TestCase):
    def test_catalog_is_complete_and_fail_closed(self) -> None:
        result = validate_schema_catalog()
        self.assertTrue(result.valid, result.issues)
        self.assertIn("brain-kernel-charter", KERNEL_SCHEMA_NAMES)
        charter = {
            "schema_version": 1,
            "mission_id": "MISSION-compatibility",
            "created_at": "2026-08-10T12:00:00Z",
            "objective": "verify contract compatibility",
            "acceptance_specs": [DIGEST],
            "repository_root": "repo",
            "base_commit": SHA,
            "target_branch": "release/test",
            "policy_fingerprint": DIGEST,
            "role_registry_fingerprint": DIGEST,
            "model_route_fingerprint": DIGEST,
            "budget": {
                "max_wall_seconds": 1,
                "max_model_calls": 1,
                "max_input_tokens": 1,
                "max_output_tokens": 1,
                "max_cost_microunits": 1,
                "max_tool_calls": 1,
                "max_work_items": 1,
                "max_depth": 1,
            },
            "external_grants": [],
            "protected_branches": ["main"],
            "human_gates": [],
            "status": "CREATED",
        }
        self.assertTrue(validate_contract("brain-kernel-charter", charter).valid)
        self.assertFalse(validate_contract("brain-kernel-charter", charter | {"extra": True}).valid)

    def test_typed_contract_is_frozen_and_canonical(self) -> None:
        value = MissionCharter(
            1, "MISSION-compatibility", "2026-08-10T12:00:00Z",
            "verify contract compatibility", (DIGEST,), "repo", SHA,
            "release/test", DIGEST, DIGEST, DIGEST,
            Budget(1, 1, 1, 1, 1, 1, 1, 1), (), ("main",), (),
            MissionState.CREATED,
        )
        self.assertTrue(value.validate().valid, value.validate().issues)
        document = value.to_document()
        reordered = dict(reversed(tuple(document.items())))
        self.assertEqual(canonical_bytes(document), canonical_bytes(reordered))
        with self.assertRaises((AttributeError, TypeError)):
            value.objective = "changed"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
