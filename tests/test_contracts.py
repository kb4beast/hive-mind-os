from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from hive_mind_os.classic_gpt import ClassicGptSourcePack
from hive_mind_os.contracts import (
    LEGACY_SCHEMA_NAMES,
    ROLE_NAMES,
    SCHEMA_NAMES,
    load_schema,
    tool_intent_digest,
    validate_contract,
    validate_runtime_state,
    validate_schema_catalog,
)
from hive_mind_os.package_system import OODAState, validate_ooda_contract
from hive_mind_os.source_docket import load_default_source_docket

ROOT = Path(__file__).resolve().parents[1]
LEGACY_SCHEMA_IDS = {
    name: f"https://hive-mind-os.invalid/schemas/v1/{name}.schema.json"
    for name in LEGACY_SCHEMA_NAMES
}


class ContractSchemaTests(unittest.TestCase):
    def runtime_state(self) -> dict[str, object]:
        state = json.loads((ROOT / "gpt_sources" / "01_RUNTIME_STATE_SCHEMA.json").read_text())
        self.assertIsInstance(state, dict)
        return state

    def test_catalog_is_complete_strict_and_draft_2020_12(self) -> None:
        schema_names_on_disk = {
            path.name.removesuffix(".schema.json")
            for path in (ROOT / "src" / "hive_mind_os" / "schemas").glob(
                "*.schema.json"
            )
        }
        self.assertEqual(set(SCHEMA_NAMES), schema_names_on_disk)
        result = validate_schema_catalog()
        self.assertTrue(result.valid, result.issues)
        for name in SCHEMA_NAMES:
            schema = load_schema(name)
            self.assertEqual(schema["additionalProperties"], False)

    def test_legacy_schema_names_and_identifiers_are_unchanged(self) -> None:
        self.assertEqual(
            {name: load_schema(name)["$id"] for name in LEGACY_SCHEMA_NAMES},
            LEGACY_SCHEMA_IDS,
        )

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
                "actor_id": (
                    "builder-example-1" if role == "builder" else f"{role}-actor"
                ),
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
                    [{"actor_id": "builder-example-1", "evidence_refs": ["self"]}],
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
        for path in (
            "../secret",
            "artifacts\\result.bin",
            "/absolute/result.bin",
            "C:/secret",
            "carrier.txt:stream",
            "CON",
            "a//b",
            "a/./b",
            "trailing.",
            "trailing ",
        ):
            invalid = dict(base, path=path)
            self.assertFalse(validate_contract("artifact-manifest", invalid).valid)
        self.assertFalse(
            validate_contract(
                "artifact-manifest",
                dict(base, digest=base["digest"] + "\n"),
            ).valid
        )

    def test_rfc3339_and_finite_number_contracts_fail_closed(self) -> None:
        lease = {
            "schema_version": 1,
            "lease_id": "LEASE-1",
            "subject_actor_id": "builder-1",
            "mission_id": "MISSION-1",
            "capabilities": ["read"],
            "resource_limits": {"seconds": 1.0},
            "issued_at": "2026-07-27T00:00:00Z",
            "expires_at": "2026-07-27T01:00:00+00:00",
            "revocation_ref": "revocation:LEASE-1",
            "issuer_actor_id": "orchestrator-1",
        }
        self.assertTrue(validate_contract("capability-lease", lease).valid)
        for timestamp in (
            "2026-07-27 00:00:00Z",
            "2026-07-27T00:00:00",
            "2026-07-27T00:00:00+00:00:01",
        ):
            candidate = copy.deepcopy(lease)
            candidate["issued_at"] = timestamp
            self.assertFalse(validate_contract("capability-lease", candidate).valid)
        nonfinite = copy.deepcopy(lease)
        nonfinite["resource_limits"]["seconds"] = float("nan")
        self.assertFalse(validate_contract("capability-lease", nonfinite).valid)

    def test_actions_bind_mission_state_actor_digest_and_receipt_verifier(self) -> None:
        baseline = self.runtime_state()
        action = baseline["proposed_actions"][0]
        self.assertEqual(action["action_digest"], tool_intent_digest(action))

        foreign = copy.deepcopy(baseline)
        foreign["proposed_actions"][0]["mission_id"] = "MISSION-FOREIGN"
        result = validate_runtime_state(foreign)
        self.assertIn("action ACT-000 belongs to another mission", result.issues)

        fabricated = copy.deepcopy(baseline)
        fabricated["proposed_actions"][0]["action_digest"] = "sha256:" + "f" * 64
        fabricated["tool_receipts"][0]["action_digest"] = "sha256:" + "f" * 64
        result = validate_runtime_state(fabricated)
        self.assertIn("action ACT-000 digest does not bind its intent", result.issues)

        self_verified = copy.deepcopy(baseline)
        self_verified["tool_receipts"][0]["verified_by"] = "builder-example-1"
        result = validate_runtime_state(self_verified)
        self.assertIn("receipt REC-000 was self-verified", result.issues)

    def test_live_source_and_claim_records_conform_to_formal_contracts(self) -> None:
        docket = load_default_source_docket()
        for source in docket.sources:
            result = validate_contract("source", source.to_contract())
            self.assertTrue(result.valid, (source.id, result.issues))
        for claim in docket.claims:
            result = validate_contract("claim", claim.to_contract())
            self.assertTrue(result.valid, (claim.id, result.issues))

    def test_extension_component_identifiers_match_runtime_rules(self) -> None:
        documents = {
            "agent-component": {
                "schema_version": 1,
                "component_id": "agent.example",
                "role_binding": "builder",
                "mission": "Build the bounded change.",
                "required_outputs": ["implementation"],
                "requested_capabilities": ["read_repository"],
                "quality_gates": ["evidence exists"],
                "prompt_path": "prompts/builder.json",
                "skill_ids": [],
                "tool_ids": [],
            },
            "skill-component": {
                "schema_version": 1,
                "component_id": "skill.example",
                "name": "Example",
                "description": "An inert example skill.",
                "instruction_path": "skills/example.json",
                "requested_capabilities": [],
                "reference_paths": [],
                "test_refs": ["tests/test_example.py"],
            },
            "tool-component": {
                "schema_version": 1,
                "component_id": "tool.example",
                "capability_id": "read_repository",
                "input_schema_ref": "schemas/input.json",
                "output_schema_ref": "schemas/output.json",
                "side_effecting": False,
                "idempotency_required": False,
                "rollback_required": False,
            },
            "workflow-component": {
                "schema_version": 1,
                "component_id": "workflow.example",
                "initial_state": "start",
                "terminal_states": ["complete"],
                "transitions": [
                    {
                        "from_state": "start",
                        "to_state": "complete",
                        "event": "advance",
                        "allowed_role_bindings": ["builder"],
                        "required_evidence": ["implementation"],
                    }
                ],
            },
        }
        for schema_name, document in documents.items():
            self.assertTrue(
                validate_contract(schema_name, document).valid,
                schema_name,
            )
            invalid = copy.deepcopy(document)
            invalid["component_id"] = "INVALID ID"
            self.assertFalse(validate_contract(schema_name, invalid).valid)

    def test_package_trust_and_ooda_contracts_fail_closed(self) -> None:
        package = json.loads(
            (
                ROOT
                / "src"
                / "hive_mind_os"
                / "builtin_packages"
                / "hive-core"
                / "package.json"
            ).read_text()
        )
        self.assertTrue(validate_contract("package-manifest", package).valid)
        package["trust_state"] = "trusted"
        package["license_status"] = "pending"
        self.assertFalse(validate_contract("package-manifest", package).valid)

        state = OODAState.initial(cycle_id="OODA-CONTRACT", mission_id="MISSION-1")
        document = state.to_contract()
        self.assertTrue(validate_contract("ooda-state", document).valid)
        self.assertTrue(validate_ooda_contract(document).valid)


if __name__ == "__main__":
    unittest.main()
