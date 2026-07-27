from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from hive_mind_os.classic_gpt import ClassicGptSourcePack
from hive_mind_os.contracts import (
    ROLE_NAMES,
    SCHEMA_NAMES,
    load_schema,
    validate_contract,
    validate_runtime_state,
    validate_schema_catalog,
)

ROOT = Path(__file__).resolve().parents[1]


class ContractSchemaTests(unittest.TestCase):
    def runtime_state(self) -> dict[str, object]:
        state = json.loads((ROOT / "gpt_sources" / "01_RUNTIME_STATE_SCHEMA.json").read_text())
        self.assertIsInstance(state, dict)
        return state

    def test_catalog_is_complete_strict_and_draft_2020_12(self) -> None:
        self.assertEqual(len(SCHEMA_NAMES), 11)
        result = validate_schema_catalog()
        self.assertTrue(result.valid, result.issues)
        for name in SCHEMA_NAMES:
            schema = load_schema(name)
            self.assertEqual(schema["additionalProperties"], False)

    def test_runtime_example_validates_against_formal_contract(self) -> None:
        state = self.runtime_state()
        pack = ClassicGptSourcePack.load(ROOT)
        placeholder = validate_runtime_state(
            state,
            expected_source_pack_fingerprint=pack.fingerprint,
        )
        self.assertFalse(placeholder.valid)
        self.assertIn(
            "mission source-pack fingerprint does not match validated bytes",
            placeholder.issues,
        )
        state["mission"]["source_pack_fingerprint"] = pack.fingerprint
        result = validate_runtime_state(
            state,
            expected_source_pack_fingerprint=pack.fingerprint,
        )
        self.assertTrue(result.valid, result.issues)

    def test_unknown_fields_and_runtime_type_confusion_fail_closed(self) -> None:
        state = self.runtime_state()
        state["invented_authority"] = True
        state["schema_version"] = 3.0
        result = validate_runtime_state(state)
        self.assertFalse(result.valid)
        self.assertTrue(any("unknown properties" in issue for issue in result.issues))
        self.assertTrue(any("does not match const" in issue for issue in result.issues))

    def test_completion_requires_all_roles_independence_and_receipts(self) -> None:
        state = self.runtime_state()
        state["mission"]["status"] = "complete"
        state["mission"]["active_phase"] = "complete"
        state["role_runs"] = [
            {
                "role": role,
                "actor_id": f"{role}-actor",
                "status": "succeeded",
                "evidence_refs": [f"evidence:{role}"],
            }
            for role in sorted(ROLE_NAMES)
        ]
        state["blockers"] = []
        state["independent_verification"] = [
            {"actor_id": "independent-curator", "evidence_refs": ["receipt:curator"]}
        ]
        state["tool_receipts"][0]["result"] = "succeeded"
        valid = validate_runtime_state(state)
        self.assertTrue(valid.valid, valid.issues)

        for mutation, expected in (
            (
                lambda value: value["role_runs"].pop(),
                "missing successful role runs",
            ),
            (
                lambda value: value.__setitem__("blockers", ["source incomplete"]),
                "blockers remain",
            ),
            (
                lambda value: value.__setitem__(
                    "independent_verification",
                    [{"actor_id": "builder-actor", "evidence_refs": ["self"]}],
                ),
                "attempted to verify",
            ),
            (
                lambda value: value["tool_receipts"][0].__setitem__("result", "failed"),
                "lacks successful receipt",
            ),
        ):
            candidate = copy.deepcopy(state)
            mutation(candidate)
            result = validate_runtime_state(candidate)
            self.assertFalse(result.valid)
            self.assertTrue(
                any(expected in issue for issue in result.issues),
                result.issues,
            )

    def test_foreign_receipt_and_handoff_bindings_fail(self) -> None:
        state = self.runtime_state()
        state["tool_receipts"][0]["mission_id"] = "foreign"
        state["handoff"]["state_ref"] = "MISSION_STATE:foreign:1"
        result = validate_runtime_state(state)
        self.assertFalse(result.valid)
        self.assertIn("receipt REC-000 has foreign mission_id", result.issues)
        self.assertIn("handoff references another mission state", result.issues)

    def test_portable_path_contract_rejects_escape_and_windows_paths(self) -> None:
        base = {
            "path": "artifacts/result.bin",
            "digest": "sha256:" + "0" * 64,
        }
        self.assertTrue(validate_contract("artifact-manifest", base).valid)
        for path in ("../secret", "artifacts\\result.bin", "/absolute/result.bin"):
            invalid = dict(base, path=path)
            self.assertFalse(validate_contract("artifact-manifest", invalid).valid)


if __name__ == "__main__":
    unittest.main()
