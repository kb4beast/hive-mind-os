from __future__ import annotations

import json
import math
from copy import deepcopy
from importlib.resources import files
from typing import Any, Mapping

from hive_mind_os.roles import DEFAULT_LIFECYCLE

from .builder_playbook_contracts import (
    BASE_DEFINITION_ID,
    BUILDER_SCHEMA_NAMES,
    COURT_ROLES,
    DEFINITION_ID,
    EXPECTED_SUCCESSOR_DIGEST,
    OUTPUT_FIELDS,
    OUTPUT_SCHEMA_BY_FIELD,
    RESOURCE_AXES,
    RESOURCE_SECTIONS,
    load_builder_schema,
    validate_builder,
)
from .canonical import canonical_bytes, digest, reject_private_content
from .contracts import validate_foundation
from .generation import (
    GENERATOR_VERSION,
    compile_generation_zero_candidates,
    digest_bytes,
    verify_generated_candidates,
)

AGENT_ID = "hive-agent:builder:v2-shadow-1"
BASE_CANONICAL_FILE_DIGEST = (
    "sha256:054b264fadeee808ac64165852408cbc2b1b122b4a6992afa4567fe93399ac3a"
)
BASE_CONTENT_DIGEST = (
    "sha256:3dac696aa469f9eaa610b1f38aa6a8d741ab629d39dc33cd0583595f57ee5e78"
)
BASE_PROJECTION_DIGEST = (
    "sha256:f51c05e902cdc3c417e992b2b29a670eed533a71f78be4b34b2eb191f71e4f05"
)
BASE_PROMPT_DIGEST = (
    "sha256:a25a4864b7355eceb423717dc3741c818b8a5a4831e14777bcf59cb467dadf08"
)
BASE_GENERATED_MANIFEST_DIGEST = (
    "sha256:e652f81353af4d0abe41b656ff0a16d71368510b4b3efe985eed99976376659d"
)
BUILTIN_AGENT_DIGEST = (
    "sha256:1436c8dcef9b1051ed17fc747f3f765a4fa747ac4be33c5ecd5e6696c42c5164"
)
BUILTIN_PROMPT_DIGEST = (
    "sha256:1ccb8900cdb41661c48896e95a68578bf824479f43f813300923767d83057a0d"
)
BUILTIN_SKILL_DIGEST = (
    "sha256:1fbff9566b77d83718d7390377d9ab1be289df67f0bd20e3893ecbc7ba514c1c"
)
BUILTIN_SKILL_INSTRUCTION_DIGEST = (
    "sha256:1382047a7a494a7d8be61e256b561008fe8c4321816e17f9ac7b74f6ca00f209"
)

MAX_REQUIREMENTS = 64
MAX_CHANGES = 256
MAX_DEPENDENCIES = 32
MAX_TESTS = 256
MAX_EVIDENCE_ITEMS = 256
MAX_CHECKPOINTS = 64
MAX_ROLLBACK_STEPS = 256
MAX_ARTIFACTS = 256
MAX_TEXT = 4000
MAX_NESTED_VALUES = 16384

_RESPONSIBILITIES = (
    "adjudicated-requirement-intake",
    "acceptance-criterion-mapping",
    "bounded-change-planning",
    "workspace-and-scope-isolation",
    "file-and-change-manifest-planning",
    "dependency-and-supply-chain-impact",
    "failure-before-and-pass-after-test-planning",
    "execution-evidence-and-receipt-planning",
    "interruption-and-recovery-planning",
    "rollback-and-compensation-planning",
    "artifact-manifest-planning",
    "handoff-to-independent-curator",
)
_QUALITY_GATES = (
    "every-requirement-has-adjudicated-sources",
    "every-requirement-maps-to-acceptance-architecture-changes-tests-and-evidence",
    "every-change-remains-inside-the-admitted-worktree-scope",
    "dependency-and-license-obligations-are-known-and-admitted",
    "tests-cannot-be-weakened-and-require-failure-before-pass-after-evidence",
    "every-change-has-a-restart-checkpoint-and-exact-rollback",
    "every-change-and-test-has-a-digest-and-receipt-bearing-artifact",
    "checkpoint-evidence-and-rollback-reserves-remain-funded",
    "caller-execution-and-test-claims-remain-unverified",
    "semantic-resealing-cannot-change-the-canonical-plan",
)
_STOP_CONDITIONS = (
    "unadjudicated-requirement",
    "missing-acceptance-or-architecture-mapping",
    "unresolved-blocking-architecture-contradiction",
    "cross-repository-or-cross-tenant-substitution",
    "out-of-scope-or-unbounded-change",
    "constitutional-or-policy-authority-mutation",
    "test-or-evidence-weakening",
    "unknown-quarantined-or-unlicensed-dependency",
    "missing-failure-before-or-pass-after-evidence",
    "missing-checkpoint-recovery-or-rollback",
    "unrelated-user-work-overwrite",
    "resource-reserves-unknown-or-insufficient",
    "repeated-plan-fingerprint",
    "missing-curator-handoff",
)
_PROHIBITED_ACTIONS = (
    "write-or-modify-a-workspace",
    "invoke-command-provider-tool-host-or-scheduler",
    "claim-code-executed-or-tests-passed",
    "approve-completion-or-release",
    "promote-or-activate-a-candidate",
    "mutate-constitutional-policy-or-authority",
    "weaken-tests-evidence-or-rollback",
    "overwrite-unrelated-user-work",
    "treat-procedural-labels-as-independent-actors",
)
_TYPED_OUTPUTS = tuple(OUTPUT_SCHEMA_BY_FIELD[field] for field in OUTPUT_FIELDS)
_REQUIRED_RECEIPT_FIELDS = (
    "artifact_digest",
    "command",
    "exit_code",
    "finished_at",
    "started_at",
    "subject_commit",
    "subject_tree",
)


class BuilderContractError(ValueError):
    """A Phase 5C request or generated artifact failed closed."""


def _layer(
    position: int,
    layer_id: str,
    kind: str,
    version: str,
    source_digests: list[str],
) -> dict[str, Any]:
    body = {
        "position": position,
        "layer_id": layer_id,
        "kind": kind,
        "version": version,
        "source_digests": source_digests,
    }
    return {**body, "digest": digest(body)}


def _verify_packaged_phase2_bytes(generated: dict[str, bytes]) -> None:
    foundation = files("hive_mind_os.foundation")
    canonical = foundation.joinpath("canonical", "agents", "builder.json").read_bytes()
    if digest_bytes(canonical) != BASE_CANONICAL_FILE_DIGEST:
        raise ValueError("packaged Phase 2 Builder canonical bytes drifted")
    generated_root = foundation.joinpath("generated")
    observed = {
        "manifest.json": generated_root.joinpath("manifest.json").read_bytes(),
        **{
            path: generated_root.joinpath(*path.split("/")).read_bytes()
            for path in generated
            if path != "manifest.json"
        },
    }
    issues = verify_generated_candidates(observed, expected_paths=generated)
    if issues:
        raise ValueError("packaged Phase 2 generated bytes drifted: " + "; ".join(issues))
    if digest_bytes(observed["manifest.json"]) != BASE_GENERATED_MANIFEST_DIGEST:
        raise ValueError("packaged Phase 2 generated manifest bytes drifted")


def _read_builtin_json(path: tuple[str, ...], expected_digest: str) -> dict[str, Any]:
    raw = files("hive_mind_os").joinpath("builtin_packages", "hive-core", *path).read_bytes()
    if digest_bytes(raw) != expected_digest:
        raise ValueError(f"packaged {'/'.join(path)} bytes drifted")
    document = json.loads(raw)
    if type(document) is not dict:
        raise ValueError(f"packaged {'/'.join(path)} is not an object")
    return document


def _compile_unpinned_successor() -> dict[str, Any]:
    generated = compile_generation_zero_candidates()
    _verify_packaged_phase2_bytes(generated)
    builder_bytes = generated["agents/builder.json"]
    builder = json.loads(builder_bytes)
    if not validate_foundation("agent-definition-v2", builder).valid:
        raise ValueError("Phase 2 Builder projection is contract-invalid")
    if (
        builder["definition_id"] != BASE_DEFINITION_ID
        or builder["content_digest"] != BASE_CONTENT_DIGEST
        or builder["generator_version"] != GENERATOR_VERSION
        or digest_bytes(builder_bytes) != BASE_PROJECTION_DIGEST
    ):
        raise ValueError("Phase 2 Builder identity or projection drifted")
    prompt_layers = builder["prompt_layers"]
    if (
        len(prompt_layers) != 1
        or prompt_layers[0]["layer_id"] != "generation-zero:builder"
        or prompt_layers[0]["version"] != "1"
        or prompt_layers[0]["digest"] != BASE_PROMPT_DIGEST
    ):
        raise ValueError("Generation Zero Builder prompt binding drifted")

    builtin_agent = _read_builtin_json(("agents", "builder.json"), BUILTIN_AGENT_DIGEST)
    _read_builtin_json(("prompts", "builder.json"), BUILTIN_PROMPT_DIGEST)
    builtin_skill = _read_builtin_json(("skills", "builder.json"), BUILTIN_SKILL_DIGEST)
    builtin_instruction = _read_builtin_json(
        ("skills", "instructions", "builder.json"),
        BUILTIN_SKILL_INSTRUCTION_DIGEST,
    )
    if builtin_agent.get("role_binding") != "builder":
        raise ValueError("built-in Builder role binding drifted")
    if builtin_agent.get("skill_ids") != ["skill.builder"]:
        raise ValueError("built-in Builder skill binding drifted")
    if builtin_skill.get("component_id") != "skill.builder":
        raise ValueError("built-in Builder skill identity drifted")
    if builtin_instruction.get("skill_id") != "skill.builder":
        raise ValueError("built-in Builder skill instruction drifted")

    schema_digests = {name: digest(load_builder_schema(name)) for name in BUILDER_SCHEMA_NAMES}
    playbook = {
        "responsibilities": list(_RESPONSIBILITIES),
        "typed_outputs": list(_TYPED_OUTPUTS),
        "quality_gates": list(_QUALITY_GATES),
        "stop_conditions": list(_STOP_CONDITIONS),
        "prohibited_actions": list(_PROHIBITED_ACTIONS),
    }
    lifecycle = [role.value for role in DEFAULT_LIFECYCLE]
    if lifecycle != [
        "orchestrator",
        "explorer",
        "architect",
        "builder",
        "curator",
        "integrator",
        "steward",
        "optimizer",
    ]:
        raise ValueError("constitutional lifecycle order drifted")
    layers = [
        _layer(
            1,
            BASE_DEFINITION_ID,
            "base",
            "2-candidate",
            [BASE_CONTENT_DIGEST, BASE_PROJECTION_DIGEST],
        ),
        _layer(
            2,
            "generation-zero:builder",
            "prompt",
            "1",
            [BASE_PROMPT_DIGEST, BUILTIN_PROMPT_DIGEST],
        ),
        _layer(3, "builder:deep-playbook", "playbook", "1", [digest(playbook)]),
        _layer(
            4,
            "skill.builder",
            "skills",
            "1",
            [BUILTIN_SKILL_DIGEST, BUILTIN_SKILL_INSTRUCTION_DIGEST],
        ),
        _layer(
            5,
            "builder:implementation-request",
            "input",
            "1",
            [schema_digests["builder-implementation-request-v1"]],
        ),
        _layer(
            6,
            "builder:typed-outputs",
            "outputs",
            "1",
            [digest({key: schema_digests[key] for key in _TYPED_OUTPUTS})],
        ),
        _layer(
            7,
            "builder:phase5c-governance",
            "governance",
            "1",
            [
                digest(
                    {
                        "sources": [
                            "phase1-canonical-contracts",
                            "phase5a-orchestrator-candidate",
                            "phase5b-architect-candidate",
                            "phase5c-builder-source-register",
                        ],
                        "court": "P5C-001",
                    }
                )
            ],
        ),
        _layer(8, "generation-zero:lifecycle", "lifecycle", "1", [digest({"stages": lifecycle})]),
    ]
    requested = list(builder["requested_capabilities"])
    body = {
        "record_type": "builder-agent-successor",
        "schema_version": 1,
        "agent_id": AGENT_ID,
        "definition_id": DEFINITION_ID,
        "role_id": "builder",
        "version": "2-shadow-1",
        "status": "candidate",
        "lineage_relation": "extends-inert",
        "base_definition_ref": BASE_DEFINITION_ID,
        "rollback_ref": BASE_DEFINITION_ID,
        "layers": layers,
        "requested_capabilities": requested,
        "effective_capabilities": [],
        "unsupported_capabilities": requested,
        "tool_refs": [],
        "input_contract_refs": ["builder-implementation-request-v1"],
        "output_contract_refs": list(_TYPED_OUTPUTS),
        "workflow_refs": ["generation-zero:lifecycle", "phase5c:builder-planning"],
        "budgets": {
            "max_requirements": MAX_REQUIREMENTS,
            "max_changes": MAX_CHANGES,
            "max_dependencies": MAX_DEPENDENCIES,
            "max_tests": MAX_TESTS,
            "max_evidence_items": MAX_EVIDENCE_ITEMS,
            "max_checkpoints": MAX_CHECKPOINTS,
            "max_rollback_steps": MAX_ROLLBACK_STEPS,
            "max_artifacts": MAX_ARTIFACTS,
        },
        "playbook": playbook,
        "constitutional_lifecycle": lifecycle,
        "activation": "inert",
        "authority": "none",
        "public": False,
        "implementation_authorized": False,
        "execution_authorized": False,
        "test_result_authorized": False,
        "completion_authorized": False,
        "promotion_authorized": False,
    }
    candidate = {**body, "content_digest": digest(body)}
    validation = validate_builder(
        "builder-agent-successor-v1",
        candidate,
        enforce_reviewed_successor=False,
    )
    if not validation.valid:
        raise ValueError("Builder successor failed its contract: " + "; ".join(validation.issues))
    return candidate


def compile_builder_successor() -> dict[str, Any]:
    candidate = _compile_unpinned_successor()
    if candidate["content_digest"] != EXPECTED_SUCCESSOR_DIGEST:
        raise ValueError("Builder successor differs from its reviewed digest")
    return deepcopy(candidate)


def builder_successor_bytes() -> bytes:
    return canonical_bytes(compile_builder_successor())


def _strict_json_copy(
    value: Any,
    *,
    path: str = "$",
    depth: int = 0,
    counter: list[int] | None = None,
) -> Any:
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > MAX_NESTED_VALUES:
        raise BuilderContractError("request exceeds the bounded nested-value limit")
    if depth > 20:
        raise BuilderContractError("request exceeds the bounded nesting depth")
    if value is None or type(value) in {bool, int}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise BuilderContractError(f"{path} contains a non-finite number")
        return value
    if type(value) is str:
        if len(value) > MAX_TEXT:
            raise BuilderContractError(f"{path} exceeds the bounded text limit")
        return value
    if type(value) is list:
        return [
            _strict_json_copy(item, path=f"{path}[{index}]", depth=depth + 1, counter=counter)
            for index, item in enumerate(value)
        ]
    if type(value) is dict:
        copied: dict[str, Any] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise BuilderContractError(f"{path} contains a non-string key")
            copied[key] = _strict_json_copy(
                item,
                path=f"{path}.{key}",
                depth=depth + 1,
                counter=counter,
            )
        return copied
    raise BuilderContractError(f"{path} contains an unsupported type {type(value).__name__}")


def _unique_ids(values: list[Mapping[str, Any]], field: str, label: str) -> list[str]:
    identifiers = [str(item[field]) for item in values]
    if len(identifiers) != len(set(identifiers)):
        raise BuilderContractError(f"duplicate {label} identifier")
    return identifiers


def _path_matches_prefix(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix.rstrip("/") + "/")


def _require_subset(values: list[str], admitted: set[str], label: str) -> None:
    unknown = sorted(set(values) - admitted)
    if unknown:
        raise BuilderContractError(f"{label} references unknown identifiers: {', '.join(unknown)}")


def _current_fingerprint(request: Mapping[str, Any]) -> str:
    return digest(
        {
            "objective_id": request["objective_id"],
            "requirements": [
                {
                    "requirement_id": item["requirement_id"],
                    "acceptance_refs": item["acceptance_refs"],
                    "architecture_refs": item["architecture_refs"],
                }
                for item in sorted(
                    request["adjudicated_requirements"],
                    key=lambda item: item["requirement_id"],
                )
            ],
            "design_digest": request["architecture_decision"]["design_digest"],
            "subject_commit": request["scope"]["subject_commit"],
            "subject_tree": request["scope"]["subject_tree"],
            "changes": [
                {
                    "change_id": item["change_id"],
                    "path": item["path"],
                    "operation": item["operation"],
                }
                for item in sorted(request["changes"], key=lambda item: item["change_id"])
            ],
            "tests": [
                {
                    "test_id": item["test_id"],
                    "command": item["command"],
                    "expected_before": item["expected_before"],
                    "expected_after": item["expected_after"],
                }
                for item in sorted(request["tests"], key=lambda item: item["test_id"])
            ],
        }
    )


def _validate_request_semantics(request: dict[str, Any]) -> None:
    acceptance = request["acceptance_criteria"]
    requirements = request["adjudicated_requirements"]
    changes = request["changes"]
    dependencies = request["dependencies"]
    tests = request["tests"]
    evidence_plan = request["evidence_plan"]
    checkpoints = request["checkpoints"]
    rollback_steps = request["rollback_steps"]
    artifacts = request["artifacts"]

    acceptance_ids = set(_unique_ids(acceptance, "acceptance_id", "acceptance"))
    requirement_ids = set(_unique_ids(requirements, "requirement_id", "requirement"))
    change_ids = set(_unique_ids(changes, "change_id", "change"))
    dependency_ids = set(_unique_ids(dependencies, "dependency_id", "dependency"))
    test_ids = set(_unique_ids(tests, "test_id", "test"))
    evidence_ids = set(_unique_ids(evidence_plan, "evidence_id", "evidence"))
    checkpoint_ids = set(_unique_ids(checkpoints, "checkpoint_id", "checkpoint"))
    rollback_ids = set(_unique_ids(rollback_steps, "rollback_id", "rollback"))
    artifact_ids = set(_unique_ids(artifacts, "artifact_id", "artifact"))

    architecture = request["architecture_decision"]
    architecture_refs = set(architecture["architecture_refs"])
    scope = request["scope"]
    if (
        architecture["subject_commit"] != scope["subject_commit"]
        or architecture["subject_tree"] != scope["subject_tree"]
    ):
        raise BuilderContractError("architecture decision and implementation scope subject differ")
    if architecture["unresolved_blocking_contradiction_refs"]:
        raise BuilderContractError("architecture contains unresolved blocking contradictions")

    evidence_refs = set(request["evidence_refs"])
    requirement_acceptance: dict[str, set[str]] = {}
    for requirement in requirements:
        _require_subset(requirement["acceptance_refs"], acceptance_ids, "requirement acceptance")
        _require_subset(requirement["architecture_refs"], architecture_refs, "requirement architecture")
        _require_subset(requirement["evidence_refs"], evidence_refs, "requirement evidence")
        requirement_acceptance[requirement["requirement_id"]] = set(requirement["acceptance_refs"])
    referenced_acceptance = set().union(
        *(set(item["acceptance_refs"]) for item in requirements)
    )
    if referenced_acceptance != acceptance_ids:
        missing = sorted(acceptance_ids - referenced_acceptance)
        raise BuilderContractError(
            "requirements do not cover every acceptance criterion: " + ", ".join(missing)
        )

    if len(changes) > scope["max_files"]:
        raise BuilderContractError("change count exceeds the admitted scope maximum")
    paths = [item["path"] for item in changes]
    if len(paths) != len(set(paths)):
        raise BuilderContractError("duplicate or conflicting change path")
    for change in changes:
        path = change["path"]
        if any(_path_matches_prefix(path, prefix) for prefix in scope["denied_paths"]):
            raise BuilderContractError(f"change path is denied by the admitted scope: {path}")
        if not any(_path_matches_prefix(path, prefix) for prefix in scope["allowed_paths"]):
            raise BuilderContractError(f"change path is outside the admitted scope: {path}")
        _require_subset(change["requirement_refs"], requirement_ids, "change requirement")
        _require_subset(change["acceptance_refs"], acceptance_ids, "change acceptance")
        _require_subset(change["architecture_refs"], architecture_refs, "change architecture")
        _require_subset(change["dependency_refs"], dependency_ids, "change dependency")
        mapped_acceptance = set().union(
            *(requirement_acceptance[ref] for ref in change["requirement_refs"])
        )
        if not set(change["acceptance_refs"]).issubset(mapped_acceptance):
            raise BuilderContractError("change borrows acceptance outside its requirement mapping")
    requirements_with_changes = set().union(
        *(set(item["requirement_refs"]) for item in changes)
    )
    if requirements_with_changes != requirement_ids:
        raise BuilderContractError("every requirement must map to at least one bounded change")

    dependency_change_count = sum(
        item["current_version"] != item["proposed_version"] for item in dependencies
    )
    if dependency_change_count > scope["max_dependency_changes"]:
        raise BuilderContractError("dependency change count exceeds the admitted scope maximum")
    for dependency in dependencies:
        _require_subset(dependency["change_refs"], change_ids, "dependency change")
    dependency_refs_from_changes = set().union(
        *(set(item["dependency_refs"]) for item in changes),
        set(),
    )
    if dependency_refs_from_changes != dependency_ids:
        raise BuilderContractError("dependency plan contains an unreferenced or missing dependency")

    for test in tests:
        _require_subset(test["requirement_refs"], requirement_ids, "test requirement")
        _require_subset(test["acceptance_refs"], acceptance_ids, "test acceptance")
        _require_subset(test["change_refs"], change_ids, "test change")
        mapped_requirements = set().union(
            *(
                set(change["requirement_refs"])
                for change in changes
                if change["change_id"] in test["change_refs"]
            )
        )
        if not set(test["requirement_refs"]).issubset(mapped_requirements):
            raise BuilderContractError("test borrows requirements from unrelated changes")
        mapped_acceptance = set().union(
            *(requirement_acceptance[ref] for ref in test["requirement_refs"])
        )
        if not set(test["acceptance_refs"]).issubset(mapped_acceptance):
            raise BuilderContractError("test borrows acceptance outside its requirement mapping")
    if not any(item["expected_before"] == "fail" for item in tests):
        raise BuilderContractError("test plan lacks a failure-before requirement")
    acceptance_with_tests = set().union(*(set(item["acceptance_refs"]) for item in tests))
    if acceptance_with_tests != acceptance_ids:
        raise BuilderContractError("tests do not cover every acceptance criterion")
    changes_with_tests = set().union(*(set(item["change_refs"]) for item in tests))
    if changes_with_tests != change_ids:
        raise BuilderContractError("tests do not cover every change")

    for evidence in evidence_plan:
        _require_subset(evidence["change_refs"], change_ids, "evidence change")
        _require_subset(evidence["test_refs"], test_ids, "evidence test")
        if set(evidence["required_receipt_fields"]) != set(_REQUIRED_RECEIPT_FIELDS):
            raise BuilderContractError("evidence receipt fields are incomplete or noncanonical")
    for test in tests:
        if test["expected_before"] == "fail" and not any(
            item["kind"] == "failure-before" and test["test_id"] in item["test_refs"]
            for item in evidence_plan
        ):
            raise BuilderContractError("failure-before evidence is incomplete")
        if not any(
            item["kind"] == "pass-after" and test["test_id"] in item["test_refs"]
            for item in evidence_plan
        ):
            raise BuilderContractError("pass-after evidence is incomplete")
    if not any(
        item["kind"] == "diff" and set(item["change_refs"]) == change_ids
        for item in evidence_plan
    ):
        raise BuilderContractError("change plan lacks complete diff evidence")
    if dependencies and not any(item["kind"] == "license" for item in evidence_plan):
        raise BuilderContractError("dependency plan lacks license evidence")

    covered_by_checkpoints = set()
    for checkpoint in checkpoints:
        _require_subset(checkpoint["after_change_refs"], change_ids, "checkpoint change")
        _require_subset(checkpoint["evidence_refs"], evidence_ids, "checkpoint evidence")
        covered_by_checkpoints.update(checkpoint["after_change_refs"])
    if covered_by_checkpoints != change_ids:
        raise BuilderContractError("checkpoints do not cover every planned change")

    change_to_rollback: dict[str, str] = {}
    change_operation = {item["change_id"]: item["operation"] for item in changes}
    inverse = {"add": "delete", "delete": "add", "modify": "modify"}
    for step in rollback_steps:
        _require_subset(step["change_refs"], change_ids, "rollback change")
        if step["checkpoint_ref"] not in checkpoint_ids:
            raise BuilderContractError("rollback references an unknown checkpoint")
        _require_subset(step["verification_test_refs"], test_ids, "rollback verification test")
        _require_subset(step["evidence_refs"], evidence_ids, "rollback evidence")
        for change_id in step["change_refs"]:
            if change_id in change_to_rollback:
                raise BuilderContractError("change maps to more than one rollback step")
            change_to_rollback[change_id] = step["rollback_id"]
            if step["inverse_operation"] != inverse[change_operation[change_id]]:
                raise BuilderContractError("rollback inverse operation does not match the change")
    if set(change_to_rollback) != change_ids:
        raise BuilderContractError("rollback steps do not cover every change exactly once")
    if set(change_to_rollback.values()) != rollback_ids:
        raise BuilderContractError("rollback plan contains an empty rollback step")

    artifact_change_coverage: set[str] = set()
    artifact_test_coverage: set[str] = set()
    for artifact in artifacts:
        path = artifact["path"]
        if any(_path_matches_prefix(path, prefix) for prefix in scope["denied_paths"]):
            raise BuilderContractError(f"artifact path is denied by the admitted scope: {path}")
        if not any(_path_matches_prefix(path, prefix) for prefix in scope["allowed_paths"]):
            raise BuilderContractError(f"artifact path is outside the admitted scope: {path}")
        _require_subset(artifact["change_refs"], change_ids, "artifact change")
        _require_subset(artifact["test_refs"], test_ids, "artifact test")
        artifact_change_coverage.update(artifact["change_refs"])
        artifact_test_coverage.update(artifact["test_refs"])
    if artifact_change_coverage != change_ids:
        raise BuilderContractError("artifact manifest does not cover every change")
    if artifact_test_coverage != test_ids:
        raise BuilderContractError("artifact manifest does not cover every test")
    if not any(item["kind"] == "manifest" for item in artifacts):
        raise BuilderContractError("artifact manifest lacks a manifest artifact")
    if not any(item["kind"] == "receipt" for item in artifacts):
        raise BuilderContractError("artifact manifest lacks a receipt artifact")

    roles = [item["role"] for item in request["actors"]]
    actor_ids = [item["actor_id"] for item in request["actors"]]
    if roles != list(COURT_ROLES):
        raise BuilderContractError("procedural actor roles differ from the fixed lifecycle order")
    if len(actor_ids) != len(set(actor_ids)):
        raise BuilderContractError("duplicate procedural actor identifier")

    budgets = request["budgets"]
    budget_values = [budgets[axis] for axis in RESOURCE_AXES]
    known = all(type(value) is int for value in budget_values)
    unknown = all(value is None for value in budget_values)
    if not (known or unknown):
        raise BuilderContractError("resource axes must be wholly known or wholly unknown")
    reserve_fields = (
        request["checkpoint_reserve_ppm"],
        request["evidence_reserve_ppm"],
        request["rollback_reserve_ppm"],
    )
    if unknown:
        if any(value is not None for value in reserve_fields):
            raise BuilderContractError("unknown resources cannot manufacture reserves")
    else:
        if not all(type(value) is int and value > 0 for value in reserve_fields):
            raise BuilderContractError("known resources require positive reserves")
        reserve_total = sum(reserve_fields)
        if reserve_total >= 1_000_000:
            raise BuilderContractError("resource reserves leave no bounded plan allocation")
        for axis, ceiling in zip(RESOURCE_AXES, budget_values, strict=True):
            if not isinstance(ceiling, int):
                continue
            reserves = [max(1, ceiling * value // 1_000_000) for value in reserve_fields]
            if ceiling - sum(reserves) < len(RESOURCE_SECTIONS):
                raise BuilderContractError(f"known {axis} budget cannot fund all plan sections")

    if _current_fingerprint(request) in request["prior_fingerprints"]:
        raise BuilderContractError("repeated implementation fingerprint")


def _validated_request(request: Mapping[str, Any]) -> dict[str, Any]:
    if type(request) is not dict:
        raise BuilderContractError("Builder request must be an exact object")
    try:
        reject_private_content(request)
    except ValueError as error:
        raise BuilderContractError(str(error)) from error
    copied = _strict_json_copy(request)
    validation = validate_builder("builder-implementation-request-v1", copied)
    if not validation.valid:
        raise BuilderContractError("invalid Builder request: " + "; ".join(validation.issues))
    _validate_request_semantics(copied)
    return copied


def _with_output_digest(document: dict[str, Any]) -> dict[str, Any]:
    return {**document, "output_digest": digest(document)}


def _budget_state(request: Mapping[str, Any]) -> str:
    return "known" if all(type(request["budgets"][axis]) is int for axis in RESOURCE_AXES) else "unknown"


def _authority_state() -> dict[str, Any]:
    return {
        "authority": "none",
        "activation": "inert",
        "effective_capability_count": 0,
        "tool_count": 0,
        "implementation_authorized": False,
        "execution_authorized": False,
        "test_result_authorized": False,
        "completion_authorized": False,
        "promotion_authorized": False,
    }


def _output_scope(request: Mapping[str, Any], request_digest: str) -> dict[str, Any]:
    architecture = request["architecture_decision"]
    return {
        "request_id": request["request_id"],
        "request_digest": request_digest,
        "objective_id": request["objective_id"],
        "tenant_id": request["tenant_id"],
        "repository_id": request["repository_id"],
        "builder_definition_id": DEFINITION_ID,
        "builder_version": "2-shadow-1",
        "architecture_decision_id": architecture["decision_id"],
        "design_digest": architecture["design_digest"],
        "subject_commit": architecture["subject_commit"],
        "subject_tree": architecture["subject_tree"],
        "requirement_refs": sorted(
            item["requirement_id"] for item in request["adjudicated_requirements"]
        ),
        "acceptance_refs": sorted(
            item["acceptance_id"] for item in request["acceptance_criteria"]
        ),
        "authority_state": _authority_state(),
        "budget_state": _budget_state(request),
        "evidence_refs": sorted(request["evidence_refs"]),
        "rollback_refs": sorted(request["rollback_refs"]),
    }


def _requirement_trace(request: Mapping[str, Any], request_digest: str) -> dict[str, Any]:
    traces = []
    for requirement in sorted(
        request["adjudicated_requirements"],
        key=lambda item: item["requirement_id"],
    ):
        requirement_id = requirement["requirement_id"]
        change_refs = sorted(
            item["change_id"]
            for item in request["changes"]
            if requirement_id in item["requirement_refs"]
        )
        test_refs = sorted(
            item["test_id"]
            for item in request["tests"]
            if requirement_id in item["requirement_refs"]
        )
        evidence_refs = sorted(
            item["evidence_id"]
            for item in request["evidence_plan"]
            if set(item["change_refs"]) & set(change_refs)
            or set(item["test_refs"]) & set(test_refs)
        )
        traces.append(
            {
                "requirement_id": requirement_id,
                "source_claim_refs": sorted(requirement["source_claim_refs"]),
                "acceptance_refs": sorted(requirement["acceptance_refs"]),
                "architecture_refs": sorted(requirement["architecture_refs"]),
                "change_refs": change_refs,
                "test_refs": test_refs,
                "evidence_refs": evidence_refs,
            }
        )
    return _with_output_digest(
        {
            "record_type": "builder-requirement-trace",
            "schema_version": 1,
            **_output_scope(request, request_digest),
            "traces": traces,
            "complete": True,
            "traceability_authorized": False,
        }
    )


def _implementation_scope(request: Mapping[str, Any], request_digest: str) -> dict[str, Any]:
    scope = request["scope"]
    return _with_output_digest(
        {
            "record_type": "builder-implementation-scope",
            "schema_version": 1,
            **_output_scope(request, request_digest),
            "worktree_id": scope["worktree_id"],
            "allowed_paths": sorted(scope["allowed_paths"]),
            "denied_paths": sorted(scope["denied_paths"]),
            "max_files": scope["max_files"],
            "change_refs": sorted(item["change_id"] for item in request["changes"]),
            "outside_scope_refs": [],
            "bounded": True,
            "overwrite_unrelated_work": False,
            "implementation_authorized": False,
        }
    )


def _change_plan(request: Mapping[str, Any], request_digest: str) -> dict[str, Any]:
    rollback_by_change = {
        change_id: step["rollback_id"]
        for step in request["rollback_steps"]
        for change_id in step["change_refs"]
    }
    ordered = []
    for sequence, change in enumerate(
        sorted(request["changes"], key=lambda item: (item["path"], item["change_id"])),
        start=1,
    ):
        change_id = change["change_id"]
        ordered.append(
            {
                "sequence": sequence,
                "change_id": change_id,
                "path": change["path"],
                "operation": change["operation"],
                "requirement_refs": sorted(change["requirement_refs"]),
                "acceptance_refs": sorted(change["acceptance_refs"]),
                "architecture_refs": sorted(change["architecture_refs"]),
                "dependency_refs": sorted(change["dependency_refs"]),
                "test_refs": sorted(
                    item["test_id"]
                    for item in request["tests"]
                    if change_id in item["change_refs"]
                ),
                "rollback_ref": rollback_by_change[change_id],
                "artifact_refs": sorted(
                    item["artifact_id"]
                    for item in request["artifacts"]
                    if change_id in item["change_refs"]
                ),
            }
        )
    return _with_output_digest(
        {
            "record_type": "builder-change-plan",
            "schema_version": 1,
            **_output_scope(request, request_digest),
            "ordered_changes": ordered,
            "change_count": len(ordered),
            "execution_authorized": False,
            "completion_claimed": False,
        }
    )


def _workspace_plan(request: Mapping[str, Any], request_digest: str) -> dict[str, Any]:
    checkpoints = sorted(request["checkpoints"], key=lambda item: item["checkpoint_id"])
    return _with_output_digest(
        {
            "record_type": "builder-workspace-plan",
            "schema_version": 1,
            **_output_scope(request, request_digest),
            "workspace_id": request["scope"]["worktree_id"],
            "isolation": "separate-worktree-proposed",
            "checkpoint_refs": [item["checkpoint_id"] for item in checkpoints],
            "interruption_recovery": deepcopy(checkpoints),
            "clean_start_required": True,
            "execution_authorized": False,
        }
    )


def _dependency_plan(request: Mapping[str, Any], request_digest: str) -> dict[str, Any]:
    dependencies = sorted(request["dependencies"], key=lambda item: item["dependency_id"])
    obligations = [
        {
            "dependency_id": item["dependency_id"],
            "license_id": item["license_id"],
            "obligation_refs": sorted(item["license_obligation_refs"]),
        }
        for item in dependencies
    ]
    return _with_output_digest(
        {
            "record_type": "builder-dependency-plan",
            "schema_version": 1,
            **_output_scope(request, request_digest),
            "dependencies": deepcopy(dependencies),
            "license_obligations": obligations,
            "unknown_dependency_refs": [],
            "quarantined_dependency_refs": [],
            "supply_chain_review_required": True,
            "dependency_change_authorized": False,
        }
    )


def _test_plan(request: Mapping[str, Any], request_digest: str) -> dict[str, Any]:
    tests = sorted(request["tests"], key=lambda item: item["test_id"])
    return _with_output_digest(
        {
            "record_type": "builder-test-plan",
            "schema_version": 1,
            **_output_scope(request, request_digest),
            "tests": deepcopy(tests),
            "failure_before_required": True,
            "pass_after_required": True,
            "tests_executed": False,
            "test_results_authorized": False,
            "test_weakening_allowed": False,
        }
    )


def _execution_evidence_plan(request: Mapping[str, Any], request_digest: str) -> dict[str, Any]:
    items = sorted(request["evidence_plan"], key=lambda item: item["evidence_id"])
    return _with_output_digest(
        {
            "record_type": "builder-execution-evidence-plan",
            "schema_version": 1,
            **_output_scope(request, request_digest),
            "evidence_items": deepcopy(items),
            "required_receipt_fields": list(_REQUIRED_RECEIPT_FIELDS),
            "code_executed_claim_accepted": False,
            "tests_passed_claim_accepted": False,
            "completion_claim_accepted": False,
            "evidence_sealed": False,
        }
    )


def _rollback_plan(request: Mapping[str, Any], request_digest: str) -> dict[str, Any]:
    return _with_output_digest(
        {
            "record_type": "builder-rollback-plan",
            "schema_version": 1,
            **_output_scope(request, request_digest),
            "steps": deepcopy(
                sorted(request["rollback_steps"], key=lambda item: item["rollback_id"])
            ),
            "checkpoints": deepcopy(
                sorted(request["checkpoints"], key=lambda item: item["checkpoint_id"])
            ),
            "full_change_coverage": True,
            "rollback_required": True,
            "rollback_executed": False,
            "rollback_authorized": False,
        }
    )


def _artifact_manifest(request: Mapping[str, Any], request_digest: str) -> dict[str, Any]:
    return _with_output_digest(
        {
            "record_type": "builder-artifact-manifest",
            "schema_version": 1,
            **_output_scope(request, request_digest),
            "artifacts": deepcopy(
                sorted(request["artifacts"], key=lambda item: item["artifact_id"])
            ),
            "every_change_covered": True,
            "every_test_covered": True,
            "digests_required": True,
            "artifacts_created": False,
        }
    )


def _curator_handoff(request: Mapping[str, Any], request_digest: str) -> dict[str, Any]:
    reason = "independent-clean-boundary-reconstruction-required"
    required = sorted(
        {
            *request["evidence_refs"],
            *request["rollback_refs"],
            *(item["evidence_id"] for item in request["evidence_plan"]),
            *(item["checkpoint_id"] for item in request["checkpoints"]),
            *(item["artifact_id"] for item in request["artifacts"]),
            reason,
        }
    )
    requested = request["requested_next_role"]
    return _with_output_digest(
        {
            "record_type": "builder-curator-handoff",
            "schema_version": 1,
            **_output_scope(request, request_digest),
            "next_role": "curator",
            "requested_next_role": requested,
            "requested_role_eligible": requested == "curator",
            "reason": reason,
            "required_refs": required,
            "independent_reconstruction_required": True,
            "authenticated_distinct_actors": False,
            "same_assistant_performed_procedural_passes": True,
            "independence_claimed": False,
            "implementation_authorized": False,
            "completion_authorized": False,
            "promotion_authorized": False,
            "activation_authorized": False,
        }
    )


def _allocate_axis(
    ceiling: int | None,
    checkpoint_ppm: int | None,
    evidence_ppm: int | None,
    rollback_ppm: int | None,
) -> dict[str, Any]:
    if ceiling is None:
        return {
            "ceiling": None,
            "checkpoint_reserve": None,
            "evidence_reserve": None,
            "rollback_reserve": None,
            "section_allocations": {section: None for section in RESOURCE_SECTIONS},
        }
    if not all(type(value) is int for value in (checkpoint_ppm, evidence_ppm, rollback_ppm)):
        raise BuilderContractError("known budget lacks resource reserve percentages")
    checkpoint = max(1, ceiling * checkpoint_ppm // 1_000_000)
    evidence = max(1, ceiling * evidence_ppm // 1_000_000)
    rollback = max(1, ceiling * rollback_ppm // 1_000_000)
    remaining = ceiling - checkpoint - evidence - rollback
    if remaining < len(RESOURCE_SECTIONS):
        raise BuilderContractError("known budget cannot fund all Builder sections")
    base, remainder = divmod(remaining, len(RESOURCE_SECTIONS))
    allocations = {
        section: base + (1 if index < remainder else 0)
        for index, section in enumerate(RESOURCE_SECTIONS)
    }
    return {
        "ceiling": ceiling,
        "checkpoint_reserve": checkpoint,
        "evidence_reserve": evidence,
        "rollback_reserve": rollback,
        "section_allocations": allocations,
    }


def _resource_accounting(request: Mapping[str, Any]) -> dict[str, Any]:
    state = _budget_state(request)
    return {
        "accounting_status": state,
        "lease_status": "not-issued",
        "axes": {
            axis: _allocate_axis(
                request["budgets"][axis],
                request["checkpoint_reserve_ppm"],
                request["evidence_reserve_ppm"],
                request["rollback_reserve_ppm"],
            )
            for axis in RESOURCE_AXES
        },
        "budget_authorized": False,
    }


def compile_builder_implementation(request: Mapping[str, Any]) -> dict[str, Any]:
    copied = _validated_request(request)
    successor = compile_builder_successor()
    request_digest = digest(copied)
    resource = _resource_accounting(copied)
    outputs = {
        "requirement_trace": _requirement_trace(copied, request_digest),
        "implementation_scope": _implementation_scope(copied, request_digest),
        "change_plan": _change_plan(copied, request_digest),
        "workspace_plan": _workspace_plan(copied, request_digest),
        "dependency_plan": _dependency_plan(copied, request_digest),
        "test_plan": _test_plan(copied, request_digest),
        "execution_evidence_plan": _execution_evidence_plan(copied, request_digest),
        "rollback_plan": _rollback_plan(copied, request_digest),
        "artifact_manifest": _artifact_manifest(copied, request_digest),
        "curator_handoff": _curator_handoff(copied, request_digest),
    }
    body = {
        "record_type": "builder-implementation-envelope",
        "schema_version": 1,
        "request_id": copied["request_id"],
        "objective_id": copied["objective_id"],
        "tenant_id": copied["tenant_id"],
        "repository_id": copied["repository_id"],
        "successor_digest": successor["content_digest"],
        "request_digest": request_digest,
        "request_snapshot": deepcopy(copied),
        "outputs": outputs,
        "resource_accounting": resource,
        "activation": "inert",
        "authority": "none",
        "public": False,
    }
    envelope = {**body, "implementation_digest": digest(body)}
    validation = validate_builder(
        "builder-implementation-envelope-v1",
        envelope,
        enforce_canonical_envelope=False,
    )
    if not validation.valid:
        raise BuilderContractError(
            "generated Builder implementation plan is invalid: " + "; ".join(validation.issues)
        )
    return deepcopy(envelope)


def builder_implementation_bytes(request: Mapping[str, Any]) -> bytes:
    return canonical_bytes(compile_builder_implementation(request))


def _receipt_fields() -> list[str]:
    return list(_REQUIRED_RECEIPT_FIELDS)


def example_builder_request(*, known_budget: bool = True) -> dict[str, Any]:
    subject_commit = "43db53de7a41d9bc02e987776edc260594def4c8"
    subject_tree = "1" * 40
    requirements = [
        {
            "requirement_id": "requirement:typed-builder-contracts",
            "statement": "Represent Builder responsibilities as strict, separately digest-bound outputs.",
            "disposition": "adopt",
            "source_claim_refs": ["claim:phase5c-typed-outputs"],
            "acceptance_refs": ["acceptance:strict-contracts"],
            "architecture_refs": ["architecture:package-private-modules"],
            "evidence_refs": ["evidence:phase5b-head"],
        },
        {
            "requirement_id": "requirement:authority-isolation",
            "statement": "Keep the Builder candidate inert, authority-free, and unable to claim execution.",
            "disposition": "adapt",
            "source_claim_refs": ["claim:builder-authority-boundary"],
            "acceptance_refs": ["acceptance:authority-free"],
            "architecture_refs": ["architecture:inert-boundary"],
            "evidence_refs": ["evidence:constitution"],
        },
        {
            "requirement_id": "requirement:installed-wheel-evidence",
            "statement": "Verify deterministic installed-wheel behavior and preserved public surfaces.",
            "disposition": "adopt",
            "source_claim_refs": ["claim:installed-wheel-contract"],
            "acceptance_refs": ["acceptance:installed-wheel"],
            "architecture_refs": ["architecture:package-verification"],
            "evidence_refs": ["evidence:phase5b-wheel"],
        },
    ]
    changes = [
        {
            "change_id": "change:contracts",
            "path": "src/hive_mind_os/foundation/builder_playbook_contracts.py",
            "operation": "add",
            "rationale": "Add strict schemas and canonical validation for the Builder candidate.",
            "requirement_refs": [
                "requirement:typed-builder-contracts",
                "requirement:authority-isolation",
            ],
            "acceptance_refs": [
                "acceptance:strict-contracts",
                "acceptance:authority-free",
            ],
            "architecture_refs": [
                "architecture:package-private-modules",
                "architecture:inert-boundary",
            ],
            "dependency_refs": [],
        },
        {
            "change_id": "change:compiler",
            "path": "src/hive_mind_os/foundation/builder_playbook.py",
            "operation": "add",
            "rationale": "Compile a deterministic, proposal-only Builder envelope.",
            "requirement_refs": [
                "requirement:typed-builder-contracts",
                "requirement:authority-isolation",
            ],
            "acceptance_refs": [
                "acceptance:strict-contracts",
                "acceptance:authority-free",
            ],
            "architecture_refs": [
                "architecture:package-private-modules",
                "architecture:inert-boundary",
            ],
            "dependency_refs": [],
        },
        {
            "change_id": "change:tests",
            "path": "tests/test_phase5c_builder_playbook.py",
            "operation": "add",
            "rationale": "Add deterministic, adversarial, compatibility, and wheel verification tests.",
            "requirement_refs": [
                "requirement:typed-builder-contracts",
                "requirement:authority-isolation",
                "requirement:installed-wheel-evidence",
            ],
            "acceptance_refs": [
                "acceptance:strict-contracts",
                "acceptance:authority-free",
                "acceptance:installed-wheel",
            ],
            "architecture_refs": [
                "architecture:package-private-modules",
                "architecture:inert-boundary",
                "architecture:package-verification",
            ],
            "dependency_refs": [],
        },
        {
            "change_id": "change:evidence",
            "path": "evidence/phase5c/phase5c_builder_inventory.json",
            "operation": "add",
            "rationale": "Retain a deterministic implementation inventory and authority boundary receipt.",
            "requirement_refs": ["requirement:installed-wheel-evidence"],
            "acceptance_refs": ["acceptance:installed-wheel"],
            "architecture_refs": ["architecture:package-verification"],
            "dependency_refs": [],
        },
    ]
    tests = [
        {
            "test_id": "test:strict-contract-catalog",
            "kind": "contract",
            "command": "python -m unittest tests.test_phase5c_builder_playbook.BuilderSuccessorTests",
            "expected_before": "fail",
            "expected_after": "pass",
            "requirement_refs": ["requirement:typed-builder-contracts"],
            "acceptance_refs": ["acceptance:strict-contracts"],
            "change_refs": ["change:contracts", "change:compiler", "change:tests"],
            "hostile_case": False,
            "test_weakening": False,
        },
        {
            "test_id": "test:authority-and-resealing",
            "kind": "security",
            "command": "python -m unittest tests.test_phase5c_builder_playbook.BuilderAdversarialTests",
            "expected_before": "fail",
            "expected_after": "pass",
            "requirement_refs": [
                "requirement:typed-builder-contracts",
                "requirement:authority-isolation",
            ],
            "acceptance_refs": [
                "acceptance:strict-contracts",
                "acceptance:authority-free",
            ],
            "change_refs": ["change:contracts", "change:compiler", "change:tests"],
            "hostile_case": True,
            "test_weakening": False,
        },
        {
            "test_id": "test:installed-wheel",
            "kind": "package",
            "command": "PYTHONPATH=.wheel-install python scripts/verify_phase5c_installed_wheel.py --installed-root .wheel-install",
            "expected_before": "fail",
            "expected_after": "pass",
            "requirement_refs": ["requirement:installed-wheel-evidence"],
            "acceptance_refs": ["acceptance:installed-wheel"],
            "change_refs": ["change:compiler", "change:tests", "change:evidence"],
            "hostile_case": False,
            "test_weakening": False,
        },
        {
            "test_id": "test:public-surface-compatibility",
            "kind": "integration",
            "command": "python -m unittest tests.test_phase5c_builder_playbook.BuilderCompatibilityTests",
            "expected_before": "not-applicable",
            "expected_after": "pass",
            "requirement_refs": [
                "requirement:authority-isolation",
                "requirement:installed-wheel-evidence",
            ],
            "acceptance_refs": [
                "acceptance:authority-free",
                "acceptance:installed-wheel",
            ],
            "change_refs": ["change:contracts", "change:compiler", "change:tests", "change:evidence"],
            "hostile_case": False,
            "test_weakening": False,
        },
    ]
    receipt_fields = _receipt_fields()
    evidence_plan = [
        {
            "evidence_id": "evidence-plan:failure-before",
            "kind": "failure-before",
            "change_refs": ["change:contracts", "change:compiler", "change:tests", "change:evidence"],
            "test_refs": [
                "test:strict-contract-catalog",
                "test:authority-and-resealing",
                "test:installed-wheel",
            ],
            "required_receipt_fields": receipt_fields,
        },
        {
            "evidence_id": "evidence-plan:pass-after",
            "kind": "pass-after",
            "change_refs": ["change:contracts", "change:compiler", "change:tests", "change:evidence"],
            "test_refs": [item["test_id"] for item in tests],
            "required_receipt_fields": receipt_fields,
        },
        {
            "evidence_id": "evidence-plan:diff",
            "kind": "diff",
            "change_refs": [item["change_id"] for item in changes],
            "test_refs": [],
            "required_receipt_fields": receipt_fields,
        },
        {
            "evidence_id": "evidence-plan:artifact",
            "kind": "artifact",
            "change_refs": [item["change_id"] for item in changes],
            "test_refs": [item["test_id"] for item in tests],
            "required_receipt_fields": receipt_fields,
        },
        {
            "evidence_id": "evidence-plan:rollback",
            "kind": "rollback",
            "change_refs": [item["change_id"] for item in changes],
            "test_refs": ["test:public-surface-compatibility"],
            "required_receipt_fields": receipt_fields,
        },
        {
            "evidence_id": "evidence-plan:checkpoint",
            "kind": "checkpoint",
            "change_refs": [item["change_id"] for item in changes],
            "test_refs": [],
            "required_receipt_fields": receipt_fields,
        },
    ]
    checkpoints = [
        {
            "checkpoint_id": "checkpoint:contracts-and-compiler",
            "after_change_refs": ["change:contracts", "change:compiler"],
            "restart_procedure": "Reopen the isolated worktree at the pinned subject and rerun the focused contract tests.",
            "evidence_refs": ["evidence-plan:checkpoint", "evidence-plan:diff"],
        },
        {
            "checkpoint_id": "checkpoint:tests-and-evidence",
            "after_change_refs": ["change:tests", "change:evidence"],
            "restart_procedure": "Reopen the isolated worktree, verify inventory equality, and rerun the full deterministic suite.",
            "evidence_refs": ["evidence-plan:checkpoint", "evidence-plan:artifact"],
        },
    ]
    rollback_steps = [
        {
            "rollback_id": "rollback:contracts",
            "change_refs": ["change:contracts"],
            "inverse_operation": "delete",
            "checkpoint_ref": "checkpoint:contracts-and-compiler",
            "verification_test_refs": ["test:public-surface-compatibility"],
            "evidence_refs": ["evidence-plan:rollback", "evidence-plan:diff"],
        },
        {
            "rollback_id": "rollback:compiler",
            "change_refs": ["change:compiler"],
            "inverse_operation": "delete",
            "checkpoint_ref": "checkpoint:contracts-and-compiler",
            "verification_test_refs": ["test:public-surface-compatibility"],
            "evidence_refs": ["evidence-plan:rollback", "evidence-plan:diff"],
        },
        {
            "rollback_id": "rollback:tests",
            "change_refs": ["change:tests"],
            "inverse_operation": "delete",
            "checkpoint_ref": "checkpoint:tests-and-evidence",
            "verification_test_refs": ["test:public-surface-compatibility"],
            "evidence_refs": ["evidence-plan:rollback", "evidence-plan:diff"],
        },
        {
            "rollback_id": "rollback:evidence",
            "change_refs": ["change:evidence"],
            "inverse_operation": "delete",
            "checkpoint_ref": "checkpoint:tests-and-evidence",
            "verification_test_refs": ["test:public-surface-compatibility"],
            "evidence_refs": ["evidence-plan:rollback", "evidence-plan:artifact"],
        },
    ]
    artifacts = [
        {
            "artifact_id": "artifact:builder-source",
            "kind": "source",
            "path": "src/hive_mind_os/foundation/builder_playbook.py",
            "change_refs": ["change:compiler"],
            "test_refs": ["test:strict-contract-catalog", "test:authority-and-resealing"],
            "digest_required": True,
            "receipt_required": True,
        },
        {
            "artifact_id": "artifact:builder-contracts",
            "kind": "source",
            "path": "src/hive_mind_os/foundation/builder_playbook_contracts.py",
            "change_refs": ["change:contracts"],
            "test_refs": ["test:strict-contract-catalog", "test:authority-and-resealing"],
            "digest_required": True,
            "receipt_required": True,
        },
        {
            "artifact_id": "artifact:builder-tests",
            "kind": "test",
            "path": "tests/test_phase5c_builder_playbook.py",
            "change_refs": ["change:tests"],
            "test_refs": [item["test_id"] for item in tests],
            "digest_required": True,
            "receipt_required": True,
        },
        {
            "artifact_id": "artifact:builder-manifest",
            "kind": "manifest",
            "path": "evidence/phase5c/phase5c_builder_inventory.json",
            "change_refs": ["change:evidence"],
            "test_refs": ["test:installed-wheel", "test:public-surface-compatibility"],
            "digest_required": True,
            "receipt_required": True,
        },
        {
            "artifact_id": "artifact:builder-receipt",
            "kind": "receipt",
            "path": "evidence/phase5c/PHASE5C_INSTALLED_WHEEL_RECEIPT.md",
            "change_refs": ["change:evidence"],
            "test_refs": ["test:installed-wheel"],
            "digest_required": True,
            "receipt_required": True,
        },
    ]
    budgets = (
        {
            "tokens": 100_000,
            "cost_microunits": 1_000_000,
            "elapsed_ms": 3_600_000,
            "tool_calls": 100,
        }
        if known_budget
        else {axis: None for axis in RESOURCE_AXES}
    )
    reserve = 100_000 if known_budget else None
    return {
        "record_type": "builder-implementation-request",
        "schema_version": 1,
        "request_id": "request:phase5c-example",
        "objective_id": "objective:phase5c-example",
        "tenant_id": "tenant:local",
        "repository_id": "repository:hive-mind-os",
        "objective": "Add an inert, package-private Builder deep-playbook candidate.",
        "objective_state": "ready",
        "constraints": [
            "do-not-modify-main",
            "no-runtime-provider-tool-store-or-scheduler-binding",
            "no-execution-test-completion-promotion-or-activation-claim",
            "preserve-root-api-cli-and-existing-runtime",
        ],
        "acceptance_criteria": [
            {
                "acceptance_id": "acceptance:strict-contracts",
                "statement": "Thirteen strict schemas and ten separately digest-bound outputs validate deterministically.",
            },
            {
                "acceptance_id": "acceptance:authority-free",
                "statement": "The candidate remains inert, package-private, authority-free, capability-free, and tool-free.",
            },
            {
                "acceptance_id": "acceptance:installed-wheel",
                "statement": "The isolated wheel imports and verifies the Builder while public API and CLI remain unchanged.",
            },
        ],
        "adjudicated_requirements": requirements,
        "architecture_decision": {
            "decision_id": "decision:phase5c-builder-deep-playbook",
            "status": "adapted",
            "design_digest": "sha256:" + ("2" * 64),
            "subject_commit": subject_commit,
            "subject_tree": subject_tree,
            "architecture_refs": [
                "architecture:package-private-modules",
                "architecture:inert-boundary",
                "architecture:package-verification",
            ],
            "unresolved_blocking_contradiction_refs": [],
        },
        "scope": {
            "worktree_id": "worktree:phase5c-builder-shadow",
            "subject_commit": subject_commit,
            "subject_tree": subject_tree,
            "allowed_paths": [
                ".github/workflows",
                "docs/architecture",
                "evidence",
                "scripts",
                "src/hive_mind_os/foundation",
                "tests",
            ],
            "denied_paths": [
                "src/hive_mind_os/__init__.py",
                "src/hive_mind_os/cli.py",
                "src/hive_mind_os/foundation/store.py",
            ],
            "max_files": 32,
            "max_dependency_changes": 0,
        },
        "changes": changes,
        "dependencies": [],
        "tests": tests,
        "evidence_plan": evidence_plan,
        "checkpoints": checkpoints,
        "rollback_steps": rollback_steps,
        "artifacts": artifacts,
        "evidence_refs": [
            "evidence:constitution",
            "evidence:phase5b-head",
            "evidence:phase5b-wheel",
        ],
        "rollback_refs": [
            "rollback:remove-phase5c-files",
            "rollback:restore-ci-and-adr-index",
        ],
        "budgets": budgets,
        "checkpoint_reserve_ppm": reserve,
        "evidence_reserve_ppm": reserve,
        "rollback_reserve_ppm": reserve,
        "actors": [
            {"role": role, "actor_id": f"procedural:{role}", "authenticated": False}
            for role in COURT_ROLES
        ],
        "prior_fingerprints": [],
        "requested_next_role": "curator",
        "caller_claims": {
            "code_executed": False,
            "tests_passed": False,
            "completion_established": False,
        },
    }
