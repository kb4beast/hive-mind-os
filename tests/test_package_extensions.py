from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hive_mind_os.reference.package_system import (
    AgentManifest,
    PackageCatalog,
    PackageValidationError,
    SkillManifest,
    ToolManifest,
    WorkflowManifest,
    canonical_json_bytes,
    content_digest,
)
from hive_mind_os.roles import DEFAULT_LIFECYCLE, ROLE_CONTRACTS
from hive_mind_os.source_docket import load_default_source_docket


def _write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def _component_id(kind: str, package_id: str) -> str:
    return f"{kind}.{package_id}"


def _third_party_package(
    parent: Path,
    package_id: str,
    *,
    agent_skill_ids: list[str] | None = None,
    agent_tool_ids: list[str] | None = None,
    agent_capabilities: list[str] | None = None,
    skill_capabilities: list[str] | None = None,
    requires: list[dict[str, str]] | None = None,
) -> tuple[Path, str]:
    root = parent / package_id
    agent_id = _component_id("agent", package_id)
    skill_id = _component_id("skill", package_id)
    tool_id = _component_id("tool", package_id)
    workflow_id = _component_id("workflow", package_id)
    documents: dict[str, object] = {
        "agent.json": {
            "schema_version": 1,
            "component_id": agent_id,
            "role_binding": "explorer",
            "mission": "Inspect a repository through inert bounded components.",
            "required_outputs": ["evidence"],
            "requested_capabilities": agent_capabilities or ["read_repository"],
            "quality_gates": ["evidence is preserved"],
            "prompt_path": "prompt.json",
            "skill_ids": agent_skill_ids if agent_skill_ids is not None else [skill_id],
            "tool_ids": agent_tool_ids if agent_tool_ids is not None else [tool_id],
        },
        "prompt.json": {"instructions": "Use only catalog-validated inert components."},
        "skill.json": {
            "schema_version": 1,
            "component_id": skill_id,
            "name": "Third-party inspection",
            "description": "A bounded inert test procedure.",
            "instruction_path": "instruction.json",
            "requested_capabilities": skill_capabilities or ["read_repository"],
            "reference_paths": [],
            "test_refs": ["test:third-party"],
        },
        "instruction.json": {
            "schema_version": 1,
            "skill_id": skill_id,
            "procedure": ["Inspect declared repository evidence."],
            "fail_closed_on": ["missing evidence"],
            "source_refs": ["test:fixture-source"],
            "deferred_obligations": ["runtime execution remains disabled"],
        },
        "tool.json": {
            "schema_version": 1,
            "component_id": tool_id,
            "capability_id": "read_repository",
            "input_schema_ref": "input.json",
            "output_schema_ref": "output.json",
            "side_effecting": False,
            "idempotency_required": False,
            "rollback_required": False,
        },
        "input.json": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"https://example.invalid/{package_id}/input.json",
            "type": "object",
            "additionalProperties": False,
            "required": ["path"],
            "properties": {"path": {"type": "string"}},
        },
        "output.json": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"https://example.invalid/{package_id}/output.json",
            "type": "object",
            "additionalProperties": False,
            "required": ["evidence"],
            "properties": {"evidence": {"type": "string"}},
        },
        "workflow.json": {
            "schema_version": 1,
            "component_id": workflow_id,
            "initial_state": "pending",
            "terminal_states": ["complete"],
            "transitions": [
                {
                    "from_state": "pending",
                    "to_state": "complete",
                    "event": "record",
                    "allowed_role_bindings": ["explorer"],
                    "required_evidence": ["inspection evidence"],
                }
            ],
        },
    }
    for relative, document in documents.items():
        _write_json(root / relative, document)
    components = [
        {"component_id": agent_id, "kind": "agent", "manifest_path": "agent.json"},
        {"component_id": skill_id, "kind": "skill", "manifest_path": "skill.json"},
        {"component_id": tool_id, "kind": "tool", "manifest_path": "tool.json"},
        {
            "component_id": workflow_id,
            "kind": "workflow",
            "manifest_path": "workflow.json",
        },
    ]
    manifest = {
        "schema_version": 1,
        "package_id": package_id,
        "version": "1.0.0",
        "license": "MIT",
        "license_status": "verified",
        "trust_state": "trusted",
        "source_refs": ["test:fixture"],
        "court_case_refs": ["court:test"],
        "components": components,
        "files": [
            {
                "path": relative,
                "digest": content_digest((root / relative).read_bytes()),
                "media_type": "application/json",
            }
            for relative in sorted(documents)
        ],
        "requires": requires or [],
        "replaces": [],
        "rollback_to": None,
    }
    _write_json(root / "package.json", manifest)
    return root, content_digest(canonical_json_bytes(manifest))


def _rewrite_and_rehash(root: Path, relative: str, document: object) -> None:
    _write_json(root / relative, document)
    manifest_path = root / "package.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for record in manifest["files"]:
        if record["path"] == relative:
            record["digest"] = content_digest((root / relative).read_bytes())
            break
    _write_json(manifest_path, manifest)


class PackageExtensionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.tmp_path = Path(temporary_directory.name)

    def test_third_party_agent_skill_tool_and_workflow_remain_inert(self) -> None:
        role_contracts_before = dict(ROLE_CONTRACTS)
        lifecycle_before = DEFAULT_LIFECYCLE
        root, _ = _third_party_package(self.tmp_path, "third-party")
        catalog = PackageCatalog.from_roots((root,))
        assert isinstance(catalog.component("agent.third-party"), AgentManifest)
        assert isinstance(catalog.component("skill.third-party"), SkillManifest)
        tool = catalog.component("tool.third-party")
        assert isinstance(tool, ToolManifest)
        assert not tool.side_effecting
        assert isinstance(catalog.component("workflow.third-party"), WorkflowManifest)
        assert not hasattr(catalog, "activate")
        assert ROLE_CONTRACTS == role_contracts_before
        assert DEFAULT_LIFECYCLE == lifecycle_before

    def test_missing_and_wrong_kind_agent_refs_fail_closed(self) -> None:
        cases = (
            (["skill.missing"], ["tool.boundary"], "missing component"),
            (["workflow.boundary"], ["tool.boundary"], "expected .* to be skill"),
            (["skill.boundary"], ["workflow.boundary"], "expected .* to be tool"),
        )
        for skill_ids, tool_ids, match in cases:
            with self.subTest(match=match):
                root, _ = _third_party_package(
                    self.tmp_path,
                    "boundary",
                    agent_skill_ids=skill_ids,
                    agent_tool_ids=tool_ids,
                )
                with self.assertRaisesRegex(PackageValidationError, match):
                    PackageCatalog.from_roots((root,))

    def test_skill_capability_escalation_fails_closed(self) -> None:
        root, _ = _third_party_package(
            self.tmp_path,
            "escalation",
            agent_capabilities=["read_repository"],
            skill_capabilities=["read_repository", "network"],
        )
        with self.assertRaisesRegex(PackageValidationError, "escalates agent"):
            PackageCatalog.from_roots((root,))

    def test_undeclared_package_reach_is_rejected_but_exact_dependency_is_allowed(
        self,
    ) -> None:
        provider, _ = _third_party_package(self.tmp_path, "provider")
        consumer, _ = _third_party_package(
            self.tmp_path,
            "consumer",
            agent_skill_ids=["skill.provider"],
            agent_tool_ids=["tool.provider"],
        )
        with self.assertRaisesRegex(PackageValidationError, "undeclared package"):
            PackageCatalog.from_roots((provider, consumer))

        dependent_parent = self.tmp_path / "declared"
        provider, provider_digest = _third_party_package(dependent_parent, "provider")
        consumer, _ = _third_party_package(
            dependent_parent,
            "consumer",
            agent_skill_ids=["skill.provider"],
            agent_tool_ids=["tool.provider"],
            requires=[
                {
                    "package_id": "provider",
                    "version": "1.0.0",
                    "manifest_digest": provider_digest,
                }
            ],
        )
        catalog = PackageCatalog.from_roots((consumer, provider))
        agent = catalog.component("agent.consumer")
        assert isinstance(agent, AgentManifest)
        assert agent.skill_ids == ("skill.provider",)

    def test_skill_instruction_and_tool_schema_resources_are_strict(self) -> None:
        root, _ = _third_party_package(self.tmp_path, "hostile-resource")
        instruction = json.loads((root / "instruction.json").read_text())
        instruction.pop("deferred_obligations")
        _rewrite_and_rehash(root, "instruction.json", instruction)
        with self.assertRaisesRegex(PackageValidationError, "missing fields"):
            PackageCatalog.from_roots((root,))

        root, _ = _third_party_package(self.tmp_path, "hostile-schema")
        schema = json.loads((root / "input.json").read_text())
        schema["additionalProperties"] = True
        _rewrite_and_rehash(root, "input.json", schema)
        with self.assertRaisesRegex(PackageValidationError, "fail closed"):
            PackageCatalog.from_roots((root,))

        root, _ = _third_party_package(self.tmp_path, "referenced-schema")
        schema = json.loads((root / "input.json").read_text())
        schema["properties"]["path"]["$dynamicRef"] = "#/$defs/path"
        schema["$defs"] = {"path": {"type": "string"}}
        _rewrite_and_rehash(root, "input.json", schema)
        with self.assertRaisesRegex(PackageValidationError, "schema references"):
            PackageCatalog.from_roots((root,))

    def test_malformed_tool_schema_keywords_fail_closed(self) -> None:
        cases = (
            (
                lambda schema: schema["properties"].__setitem__("path", "not-a-schema"),
                "object or boolean schema",
            ),
            (
                lambda schema: schema["properties"]["path"].__setitem__(
                    "minLength", "one"
                ),
                "nonnegative integer",
            ),
            (
                lambda schema: schema["properties"]["path"].__setitem__(
                    "enum", "anything"
                ),
                "nonempty array",
            ),
            (lambda schema: schema.__setitem__("$id", "not a uri"), "absolute HTTP"),
        )
        for mutation, match in cases:
            with self.subTest(match=match):
                root, _ = _third_party_package(self.tmp_path, "invalid-meta-schema")
                schema = json.loads((root / "input.json").read_text())
                mutation(schema)
                _rewrite_and_rehash(root, "input.json", schema)
                with self.assertRaisesRegex(PackageValidationError, match):
                    PackageCatalog.from_roots((root,))

    def test_source_docket_remains_fail_closed_after_extension_packaging(self) -> None:
        audit = load_default_source_docket().audit()
        assert not audit.release_ready
        blockers = {issue.source_id for issue in audit.issues if issue.source_id}
        assert {
            "SRC-005",
            "SRC-006",
            "SRC-016",
            "SRC-017",
            "SRC-018",
            "SRC-019",
            "SRC-020",
        } <= blockers
