from __future__ import annotations

import json
import math
from copy import deepcopy
from importlib.resources import files
from typing import Any, Mapping

from hive_mind_os.roles import DEFAULT_LIFECYCLE

from .architect_playbook_contracts import (
    AGENT_ID,
    ARCHITECT_SCHEMA_NAMES,
    BASE_DEFINITION_ID,
    COURT_ROLES,
    DEFINITION_ID,
    EXPECTED_SUCCESSOR_DIGEST,
    OUTPUT_FIELDS,
    OUTPUT_SCHEMA_BY_FIELD,
    RESOURCE_AXES,
    RESOURCE_SECTIONS,
    SCORE_FIELDS,
    load_architect_schema,
    validate_architect,
)
from .canonical import canonical_bytes, digest, reject_private_content
from .contracts import validate_foundation
from .generation import (
    GENERATOR_VERSION,
    compile_generation_zero_candidates,
    digest_bytes,
    verify_generated_candidates,
)

BASE_CANONICAL_FILE_DIGEST = (
    "sha256:5afba0d6950a95c38331f36b9aa6ca6739ac9cb34a076cb82dd71f71d0fe303f"
)
BASE_CONTENT_DIGEST = (
    "sha256:73e35a8e22d7949397d8a51d4c82a1d885097178470e7299cbe960965f7df040"
)
BASE_PROJECTION_DIGEST = (
    "sha256:10c346ada208a9c4bd13b1f69ebc28741d6beb4536654a70005b25642732d21c"
)
BASE_PROMPT_DIGEST = (
    "sha256:8957ae1467f191efd6eb18c23019c0b69e9aea1cf6ecc276852274196103021f"
)
BASE_GENERATED_MANIFEST_DIGEST = (
    "sha256:e652f81353af4d0abe41b656ff0a16d71368510b4b3efe985eed99976376659d"
)
BUILTIN_AGENT_DIGEST = (
    "sha256:de8d92ed357193fcaab05c74200964960db3d89eb12796210f84ea1c058c0cac"
)
BUILTIN_PROMPT_DIGEST = (
    "sha256:5016b2e55213d1efc47adb81d09e6650a45778565861c6d1a988edd7df07e85e"
)
BUILTIN_SKILL_DIGEST = (
    "sha256:a3e43fbba9a6baacdb904c232f2a5e476517b85ffb7c5246fdebbd6574ec4f71"
)
BUILTIN_SKILL_INSTRUCTION_DIGEST = (
    "sha256:6c92a01ca7685d0a4d902822d360f091e69388352c3ddfd370e21579bb790557"
)

MAX_CLAIMS = 32
MAX_OPTIONS = 8
MAX_DESIGN_RECORDS_PER_OPTION = 176
MAX_EVIDENCE_REFS = 128
MAX_ROLLBACK_REFS = 64
MAX_PRIOR_FINGERPRINTS = 32
MAX_TEXT = 4000
MAX_NESTED_VALUES = 8192
RISK_BLOCKING_THRESHOLD_PPM = 500_000

_SCORE_WEIGHTS = {
    "constraint_fit_ppm": 250_000,
    "reversibility_ppm": 175_000,
    "security_ppm": 250_000,
    "evolvability_ppm": 150_000,
    "evidence_ppm": 100_000,
    "resource_efficiency_ppm": 75_000,
}
if sum(_SCORE_WEIGHTS.values()) != 1_000_000:
    raise RuntimeError("Architect score weights do not sum to one million ppm")

_RESPONSIBILITIES = (
    "integrate-adjudicated-claims",
    "compare-bounded-design-options",
    "specify-components-interfaces-and-invariants",
    "model-trust-boundaries-and-residual-risk",
    "bind-additive-migration-to-digest-pinned-rollback",
    "plan-complete-verification-per-option",
    "reserve-recovery-and-verification-resources",
    "handoff-without-selecting-or-implementing",
)
_QUALITY_GATES = (
    "every-adopted-or-adapted-claim-is-evidence-bound",
    "claim-design-references-remain-option-local",
    "every-option-has-complete-independent-verification",
    "trust-boundaries-reference-only-local-components-and-threats",
    "blocked-options-cannot-win-by-score",
    "migration-and-rollback-are-bidirectionally-bound",
    "resource-reserves-are-positive-and-exact",
    "semantic-resealing-cannot-change-canonical-design",
)
_STOP_CONDITIONS = (
    "unadjudicated-or-unsupported-material-claim",
    "missing-option-local-claim-mapping",
    "incomplete-per-option-verification",
    "uncontained-trust-boundary",
    "blocked-or-recovering-objective",
    "no-viable-option",
    "repeated-design-fingerprint",
    "resource-accounting-unknown-or-insufficient",
    "authenticated-independent-review-unavailable",
)
_PROHIBITED_ACTIONS = (
    "write-implementation",
    "select-or-promote-a-design",
    "accept-residual-risk",
    "issue-budget-or-capability-lease",
    "invoke-provider-tool-host-or-scheduler",
    "merge-role-authority",
    "treat-procedural-labels-as-independent-actors",
    "claim-completion-value-release-readiness-or-superiority",
)
_TYPED_OUTPUTS = tuple(OUTPUT_SCHEMA_BY_FIELD[field] for field in OUTPUT_FIELDS)


class ArchitectContractError(ValueError):
    """A Phase 5B request or generated artifact failed closed."""


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
    canonical = foundation.joinpath("canonical", "agents", "architect.json").read_bytes()
    if digest_bytes(canonical) != BASE_CANONICAL_FILE_DIGEST:
        raise ValueError("packaged Phase 2 Architect canonical bytes drifted")
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
    architect_bytes = generated["agents/architect.json"]
    architect = json.loads(architect_bytes)
    if not validate_foundation("agent-definition-v2", architect).valid:
        raise ValueError("Phase 2 Architect projection is contract-invalid")
    if (
        architect["definition_id"] != BASE_DEFINITION_ID
        or architect["content_digest"] != BASE_CONTENT_DIGEST
        or architect["generator_version"] != GENERATOR_VERSION
        or digest_bytes(architect_bytes) != BASE_PROJECTION_DIGEST
    ):
        raise ValueError("Phase 2 Architect identity or projection drifted")
    prompt_layers = architect["prompt_layers"]
    if (
        len(prompt_layers) != 1
        or prompt_layers[0]["layer_id"] != "generation-zero:architect"
        or prompt_layers[0]["version"] != "1"
        or prompt_layers[0]["digest"] != BASE_PROMPT_DIGEST
    ):
        raise ValueError("Generation Zero Architect prompt binding drifted")

    builtin_agent = _read_builtin_json(("agents", "architect.json"), BUILTIN_AGENT_DIGEST)
    _read_builtin_json(("prompts", "architect.json"), BUILTIN_PROMPT_DIGEST)
    builtin_skill = _read_builtin_json(("skills", "architect.json"), BUILTIN_SKILL_DIGEST)
    builtin_instruction = _read_builtin_json(
        ("skills", "instructions", "architect.json"),
        BUILTIN_SKILL_INSTRUCTION_DIGEST,
    )
    if builtin_agent.get("role_binding") != "architect":
        raise ValueError("built-in Architect role binding drifted")
    if builtin_agent.get("skill_ids") != ["skill.architect"]:
        raise ValueError("built-in Architect skill binding drifted")
    if builtin_skill.get("component_id") != "skill.architect":
        raise ValueError("built-in Architect skill identity drifted")
    if builtin_instruction.get("skill_id") != "skill.architect":
        raise ValueError("built-in Architect skill instruction drifted")

    schema_digests = {
        name: digest(load_architect_schema(name)) for name in ARCHITECT_SCHEMA_NAMES
    }
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
            "generation-zero:architect",
            "prompt",
            "1",
            [BASE_PROMPT_DIGEST, BUILTIN_PROMPT_DIGEST],
        ),
        _layer(3, "architect:deep-playbook", "playbook", "1", [digest(playbook)]),
        _layer(
            4,
            "skill.architect",
            "skills",
            "1",
            [BUILTIN_SKILL_DIGEST, BUILTIN_SKILL_INSTRUCTION_DIGEST],
        ),
        _layer(
            5,
            "architect:design-request",
            "input",
            "1",
            [schema_digests["architect-design-request-v1"]],
        ),
        _layer(
            6,
            "architect:typed-outputs",
            "outputs",
            "1",
            [digest({key: schema_digests[key] for key in _TYPED_OUTPUTS})],
        ),
        _layer(
            7,
            "architect:phase5b-governance",
            "governance",
            "1",
            [
                digest(
                    {
                        "sources": [
                            "phase1-canonical-contracts",
                            "phase5a-orchestrator-candidate",
                            "phase5b-architect-source-register",
                        ],
                        "court": "P5B-001",
                    }
                )
            ],
        ),
        _layer(8, "generation-zero:lifecycle", "lifecycle", "1", [digest({"stages": lifecycle})]),
    ]
    requested = list(architect["requested_capabilities"])
    body = {
        "record_type": "architect-agent-successor",
        "schema_version": 1,
        "agent_id": AGENT_ID,
        "definition_id": DEFINITION_ID,
        "role_id": "architect",
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
        "input_contract_refs": ["architect-design-request-v1"],
        "output_contract_refs": list(_TYPED_OUTPUTS),
        "workflow_refs": ["generation-zero:lifecycle", "phase5b:architect-design"],
        "budgets": {
            "max_claims": MAX_CLAIMS,
            "max_options": MAX_OPTIONS,
            "max_design_records_per_option": MAX_DESIGN_RECORDS_PER_OPTION,
            "max_evidence_refs": MAX_EVIDENCE_REFS,
            "max_rollback_refs": MAX_ROLLBACK_REFS,
            "max_prior_fingerprints": MAX_PRIOR_FINGERPRINTS,
            "max_text": MAX_TEXT,
            "max_nested_values": MAX_NESTED_VALUES,
        },
        "playbook": playbook,
        "governance": {
            "source_refs": [
                "phase1-canonical-contracts",
                "phase2-foundation-contract",
                "phase5a-orchestrator-candidate",
                "phase5b-architect-source-register",
            ],
            "court_refs": ["P2-FOUNDATION-001", "P5A-001", "P5B-001"],
            "dissent_ref": "evidence/phase5b/PHASE5B_DISSENT.md",
            "activation_prerequisites": [
                "authenticated-independent-actors",
                "held-out-architect-behavioral-evaluation",
                "independent-curator",
                "independent-judge",
                "separate-activation-court",
            ],
        },
        "activation": "inert",
        "authority": "none",
        "public": False,
    }
    candidate = {**body, "content_digest": digest(body)}
    validation = validate_architect(
        "architect-agent-successor-v1",
        candidate,
        enforce_reviewed_successor=False,
    )
    if not validation.valid:
        raise ValueError("Architect successor failed its contract: " + "; ".join(validation.issues))
    return candidate


def compile_architect_successor() -> dict[str, Any]:
    candidate = _compile_unpinned_successor()
    if candidate["content_digest"] != EXPECTED_SUCCESSOR_DIGEST:
        raise ValueError("Architect successor differs from its reviewed digest")
    return deepcopy(candidate)


def architect_successor_bytes() -> bytes:
    return canonical_bytes(compile_architect_successor())


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
        raise ArchitectContractError("request exceeds the bounded nested-value limit")
    if depth > 20:
        raise ArchitectContractError("request exceeds the bounded nesting depth")
    if value is None or type(value) in {bool, int}:
        return value
    if type(value) is str:
        if len(value) > MAX_TEXT:
            raise ArchitectContractError(f"{path} exceeds the bounded text limit")
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ArchitectContractError(f"{path} contains a non-finite number")
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
                raise ArchitectContractError(f"{path} contains a non-string key")
            copied[key] = _strict_json_copy(
                item,
                path=f"{path}.{key}",
                depth=depth + 1,
                counter=counter,
            )
        return copied
    raise ArchitectContractError(f"{path} contains unsupported type {type(value).__name__}")


def _unique_ids(values: list[Mapping[str, Any]], field: str, label: str) -> list[str]:
    identifiers = [str(item[field]) for item in values]
    if len(identifiers) != len(set(identifiers)):
        raise ArchitectContractError(f"duplicate {label} identifier")
    return identifiers


def _option_design_ids(option: Mapping[str, Any]) -> set[str]:
    return {
        *[item["component_id"] for item in option["components"]],
        *[item["interface_id"] for item in option["interfaces"]],
        *[item["invariant_id"] for item in option["invariants"]],
        *[item["boundary_id"] for item in option["trust_boundaries"]],
        *[item["threat_id"] for item in option["threats"]],
        *[item["step_id"] for item in option["migration_steps"]],
        *[item["rollback_step_id"] for item in option["rollback_steps"]],
        *[item["verification_id"] for item in option["verification_steps"]],
    }


def _validate_option_semantics(
    option: Mapping[str, Any],
    acceptance_ids: set[str],
) -> set[str]:
    option_id = option["option_id"]
    components = set(_unique_ids(option["components"], "component_id", f"{option_id} component"))
    interfaces = _unique_ids(option["interfaces"], "interface_id", f"{option_id} interface")
    invariants = set(_unique_ids(option["invariants"], "invariant_id", f"{option_id} invariant"))
    boundaries = _unique_ids(option["trust_boundaries"], "boundary_id", f"{option_id} boundary")
    threats = set(_unique_ids(option["threats"], "threat_id", f"{option_id} threat"))
    migration_ids = _unique_ids(option["migration_steps"], "step_id", f"{option_id} migration step")
    rollback_ids = set(_unique_ids(option["rollback_steps"], "rollback_step_id", f"{option_id} rollback step"))
    verification_ids = _unique_ids(
        option["verification_steps"],
        "verification_id",
        f"{option_id} verification step",
    )
    design_ids = _option_design_ids(option)
    expected_count = (
        len(components)
        + len(interfaces)
        + len(invariants)
        + len(boundaries)
        + len(threats)
        + len(migration_ids)
        + len(rollback_ids)
        + len(verification_ids)
    )
    if len(design_ids) != expected_count:
        raise ArchitectContractError(f"{option_id} reuses a design identifier across record kinds")
    for interface in option["interfaces"]:
        if interface["source_component_id"] not in components or interface["target_component_id"] not in components:
            raise ArchitectContractError(f"{option_id} interface crosses outside its option")
        if interface["source_component_id"] == interface["target_component_id"]:
            raise ArchitectContractError(f"{option_id} interface must connect distinct components")
    component_data = {
        data_class
        for component in option["components"]
        for data_class in component["data_classes"]
    }
    boundary_threats: set[str] = set()
    for boundary in option["trust_boundaries"]:
        if boundary["source_component_id"] not in components or boundary["target_component_id"] not in components:
            raise ArchitectContractError(f"{option_id} trust boundary crosses outside its option")
        if boundary["source_component_id"] == boundary["target_component_id"]:
            raise ArchitectContractError(f"{option_id} trust boundary must connect distinct components")
        if not set(boundary["data_classes"]).issubset(component_data):
            raise ArchitectContractError(f"{option_id} trust boundary contains undeclared data classes")
        if not set(boundary["threat_ids"]).issubset(threats):
            raise ArchitectContractError(f"{option_id} trust boundary borrows another option's threat")
        boundary_threats.update(boundary["threat_ids"])
    if boundary_threats != threats:
        raise ArchitectContractError(f"{option_id} trust boundaries do not cover exactly its threats")
    prior: set[str] = set()
    referenced_rollbacks: set[str] = set()
    for step in option["migration_steps"]:
        dependencies = set(step["depends_on"])
        if not dependencies.issubset(prior):
            raise ArchitectContractError(f"{option_id} migration dependency is not an earlier local step")
        if step["rollback_step_id"] not in rollback_ids:
            raise ArchitectContractError(f"{option_id} migration step lacks a local rollback step")
        referenced_rollbacks.add(step["rollback_step_id"])
        prior.add(step["step_id"])
    if referenced_rollbacks != rollback_ids:
        raise ArchitectContractError(f"{option_id} rollback steps are not exactly migration-bound")
    coverage = {
        "acceptance_refs": set(),
        "invariant_refs": set(),
        "threat_refs": set(),
        "migration_step_refs": set(),
        "rollback_step_refs": set(),
    }
    for step in option["verification_steps"]:
        for field in coverage:
            coverage[field].update(step[field])
    expected_coverage = {
        "acceptance_refs": acceptance_ids,
        "invariant_refs": invariants,
        "threat_refs": threats,
        "migration_step_refs": set(migration_ids),
        "rollback_step_refs": rollback_ids,
    }
    for field, expected in expected_coverage.items():
        if coverage[field] != expected:
            raise ArchitectContractError(
                f"{option_id} verification {field} does not exactly cover its own design"
            )
    return design_ids


def _validate_request_semantics(request: dict[str, Any]) -> None:
    acceptance_ids = set(_unique_ids(request["acceptance_criteria"], "acceptance_id", "acceptance"))
    claim_ids = set(_unique_ids(request["claims"], "claim_id", "claim"))
    option_ids = _unique_ids(request["options"], "option_id", "option")
    option_id_set = set(option_ids)
    if request["requested_option_id"] is not None and request["requested_option_id"] not in option_id_set:
        raise ArchitectContractError("requested option is not one of the admitted options")
    actor_roles = _unique_ids(request["actors"], "role", "procedural actor role")
    actor_ids = _unique_ids(request["actors"], "actor_id", "procedural actor")
    if set(actor_roles) != set(COURT_ROLES) or len(actor_ids) != len(COURT_ROLES):
        raise ArchitectContractError("procedural actor coverage differs from the required role set")
    if any(actor["authenticated"] is not False for actor in request["actors"]):
        raise ArchitectContractError("caller-supplied authenticated independence is prohibited")

    evidence_set = set(request["evidence_refs"])
    for claim in request["claims"]:
        if not set(claim["evidence_refs"]).issubset(evidence_set):
            raise ArchitectContractError(f"{claim['claim_id']} references unadmitted evidence")
        if not set(claim["acceptance_refs"]).issubset(acceptance_ids):
            raise ArchitectContractError(f"{claim['claim_id']} references unknown acceptance criteria")
        if claim["disposition"] in {"adopt", "adapt"}:
            # The caller-controlled material flag never weakens the burden.
            if not claim["evidence_refs"]:
                raise ArchitectContractError(f"{claim['claim_id']} adopted claim lacks evidence")
            if not claim["acceptance_refs"]:
                raise ArchitectContractError(f"{claim['claim_id']} adopted claim lacks acceptance criteria")

    budgets = request["budgets"]
    values = [budgets[name] for name in RESOURCE_AXES]
    all_unknown = all(value is None for value in values)
    all_known = all(type(value) is int for value in values)
    if not (all_unknown or all_known):
        raise ArchitectContractError("resource axes must be wholly known or wholly unknown")
    if all_unknown:
        if request["rollback_reserve_ppm"] is not None or request["verification_reserve_ppm"] is not None:
            raise ArchitectContractError("unknown resource axes cannot manufacture reserve percentages")
    else:
        rollback_ppm = request["rollback_reserve_ppm"]
        verification_ppm = request["verification_reserve_ppm"]
        if type(rollback_ppm) is not int or type(verification_ppm) is not int:
            raise ArchitectContractError("known resource axes require both reserve percentages")
        if rollback_ppm + verification_ppm >= 1_000_000:
            raise ArchitectContractError("resource reserves leave no bounded design allocation")

    option_design_ids: dict[str, set[str]] = {}
    all_design_ids: set[str] = set()
    for option in request["options"]:
        local_ids = _validate_option_semantics(option, acceptance_ids)
        if all_design_ids.intersection(local_ids):
            raise ArchitectContractError("design identifiers are not globally unique across options")
        all_design_ids.update(local_ids)
        option_design_ids[option["option_id"]] = local_ids

    mapping_pairs: set[tuple[str, str]] = set()
    mappings_by_claim: dict[str, set[str]] = {claim_id: set() for claim_id in claim_ids}
    claim_by_id = {claim["claim_id"]: claim for claim in request["claims"]}
    for mapping in request["claim_mappings"]:
        claim_id = mapping["claim_id"]
        option_id = mapping["option_id"]
        pair = (claim_id, option_id)
        if pair in mapping_pairs:
            raise ArchitectContractError("duplicate claim-to-option mapping")
        mapping_pairs.add(pair)
        if claim_id not in claim_ids or option_id not in option_id_set:
            raise ArchitectContractError("claim mapping references an unknown claim or option")
        if claim_by_id[claim_id]["disposition"] not in {"adopt", "adapt"}:
            raise ArchitectContractError("non-adopted claim cannot be represented as integrated design")
        if not set(mapping["design_refs"]).issubset(option_design_ids[option_id]):
            raise ArchitectContractError("claim mapping borrows design records from another option")
        mappings_by_claim[claim_id].add(option_id)
    for claim in request["claims"]:
        expected = option_id_set if claim["disposition"] in {"adopt", "adapt"} else set()
        if mappings_by_claim[claim["claim_id"]] != expected:
            raise ArchitectContractError(
                f"{claim['claim_id']} does not have exactly one option-local mapping per design option"
            )


def _validated_request(request: Mapping[str, Any]) -> dict[str, Any]:
    if type(request) is not dict:
        raise ArchitectContractError("Architect request must be an exact object")
    copied = _strict_json_copy(request)
    try:
        reject_private_content(copied)
    except ValueError as error:
        raise ArchitectContractError(str(error)) from error
    validation = validate_architect("architect-design-request-v1", copied)
    if not validation.valid:
        raise ArchitectContractError("invalid Architect request: " + "; ".join(validation.issues))
    _validate_request_semantics(copied)
    return copied


def _with_output_digest(document: dict[str, Any]) -> dict[str, Any]:
    return {**document, "output_digest": digest(document)}


def _output_scope(request: Mapping[str, Any], request_digest: str) -> dict[str, Any]:
    return {
        "request_id": request["request_id"],
        "request_digest": request_digest,
        "objective_id": request["objective_id"],
        "tenant_id": request["tenant_id"],
        "repository_id": request["repository_id"],
    }


def _design_fingerprint(request: Mapping[str, Any]) -> str:
    return digest(
        {
            "objective": request["objective"],
            "constraints": request["constraints"],
            "acceptance_criteria": request["acceptance_criteria"],
            "claims": request["claims"],
            "claim_mappings": request["claim_mappings"],
            "options": request["options"],
        }
    )


def _weighted_score(score_inputs: Mapping[str, int]) -> int:
    return sum(score_inputs[field] * _SCORE_WEIGHTS[field] for field in SCORE_FIELDS) // 1_000_000


def _option_blocking_reasons(option: Mapping[str, Any], objective_state: str) -> list[str]:
    reasons = [*option["violations"], *option["unknowns"]]
    reasons.extend(
        threat["threat_id"]
        for threat in option["threats"]
        if threat["residual_risk_ppm"] >= RISK_BLOCKING_THRESHOLD_PPM
    )
    if objective_state == "blocked":
        reasons.append("objective-blocked")
    elif objective_state == "recovering":
        reasons.append("objective-recovering")
    return list(dict.fromkeys(reasons))


def _option_analysis(
    request: Mapping[str, Any],
    request_digest: str,
) -> tuple[dict[str, Any], str | None, str]:
    fingerprint = _design_fingerprint(request)
    iteration_status = (
        "repeated" if fingerprint in set(request["prior_design_fingerprints"]) else "new"
    )
    ranking_bodies: list[dict[str, Any]] = []
    for option in request["options"]:
        blocking = _option_blocking_reasons(option, request["objective_state"])
        ranking_bodies.append(
            {
                "option_id": option["option_id"],
                "weighted_score_ppm": _weighted_score(option["score_inputs"]),
                "viability_status": "blocked" if blocking else "viable",
                "blocking_reasons": blocking,
                "residual_risk_ppm": max(
                    threat["residual_risk_ppm"] for threat in option["threats"]
                ),
            }
        )
    ranking_bodies.sort(
        key=lambda item: (
            item["viability_status"] != "viable",
            -item["weighted_score_ppm"],
            item["option_id"],
        )
    )
    rankings = [{**item, "rank": index + 1} for index, item in enumerate(ranking_bodies)]
    preferred = next(
        (item["option_id"] for item in rankings if item["viability_status"] == "viable"),
        None,
    )
    reasons = ["authenticated-independent-review-unavailable"]
    if preferred is None:
        reasons.append("no-viable-option")
    if iteration_status == "repeated":
        reasons.append("design-fingerprint-repeated")
    if request["objective_state"] != "proposed":
        reasons.append(f"objective-{request['objective_state']}")
    requested = request["requested_option_id"]
    output = _with_output_digest(
        {
            "record_type": "architect-option-analysis",
            "schema_version": 1,
            **_output_scope(request, request_digest),
            "rankings": rankings,
            "provisional_preferred_option_id": preferred,
            "requested_option_id": requested,
            "requested_option_eligible": requested is not None and requested == preferred,
            "selection_status": "defer",
            "selection_reasons": reasons,
            "iteration_status": iteration_status,
            "design_fingerprint": fingerprint,
            "selection_authorized": False,
        }
    )
    return output, preferred, iteration_status


def _claim_integration(request: Mapping[str, Any], request_digest: str) -> dict[str, Any]:
    claims = {claim["claim_id"]: claim for claim in request["claims"]}
    option_order = {option["option_id"]: index for index, option in enumerate(request["options"])}
    claim_order = {claim["claim_id"]: index for index, claim in enumerate(request["claims"])}
    mappings = []
    for mapping in sorted(
        request["claim_mappings"],
        key=lambda item: (option_order[item["option_id"]], claim_order[item["claim_id"]]),
    ):
        claim = claims[mapping["claim_id"]]
        mappings.append(
            {
                "claim_id": claim["claim_id"],
                "option_id": mapping["option_id"],
                "disposition": claim["disposition"],
                "status": "mapped",
                "evidence_refs": list(claim["evidence_refs"]),
                "acceptance_refs": list(claim["acceptance_refs"]),
                "design_refs": list(mapping["design_refs"]),
            }
        )
    unresolved = [
        claim["claim_id"]
        for claim in request["claims"]
        if claim["disposition"] not in {"adopt", "adapt"}
    ]
    return _with_output_digest(
        {
            "record_type": "architect-claim-integration",
            "schema_version": 1,
            **_output_scope(request, request_digest),
            "mappings": mappings,
            "unresolved_claim_ids": unresolved,
            "completion_authorized": False,
        }
    )


def _architecture(
    request: Mapping[str, Any],
    request_digest: str,
    preferred: str | None,
    iteration_status: str,
) -> dict[str, Any]:
    status = (
        "recovery-required"
        if request["objective_state"] == "recovering"
        else "blocked"
        if request["objective_state"] == "blocked" or preferred is None
        else "repeated"
        if iteration_status == "repeated"
        else "proposed"
    )
    return _with_output_digest(
        {
            "record_type": "architect-architecture",
            "schema_version": 1,
            **_output_scope(request, request_digest),
            "objective": request["objective"],
            "constraints": list(request["constraints"]),
            "options": [
                {
                    "option_id": option["option_id"],
                    "summary": option["summary"],
                    "rationale": option["rationale"],
                    "components": deepcopy(option["components"]),
                    "invariants": deepcopy(option["invariants"]),
                    "trust_boundaries": deepcopy(option["trust_boundaries"]),
                }
                for option in request["options"]
            ],
            "provisional_preferred_option_id": preferred,
            "architecture_status": status,
            "implementation_authorized": False,
        }
    )


def _interfaces(request: Mapping[str, Any], request_digest: str) -> dict[str, Any]:
    options = []
    for option in request["options"]:
        states = {interface["compatibility"] for interface in option["interfaces"]}
        compatibility = (
            "unknown"
            if "unknown" in states
            else "migration-required"
            if "migration-required" in states
            else "compatible"
        )
        options.append(
            {
                "option_id": option["option_id"],
                "interfaces": deepcopy(option["interfaces"]),
                "compatibility_status": compatibility,
            }
        )
    return _with_output_digest(
        {
            "record_type": "architect-interface-contract",
            "schema_version": 1,
            **_output_scope(request, request_digest),
            "options": options,
            "implementation_authorized": False,
        }
    )


def _threat_model(
    request: Mapping[str, Any], request_digest: str, preferred: str | None
) -> dict[str, Any]:
    options = []
    by_id: dict[str, dict[str, Any]] = {}
    for option in request["options"]:
        blocking = [
            threat["threat_id"]
            for threat in option["threats"]
            if threat["residual_risk_ppm"] >= RISK_BLOCKING_THRESHOLD_PPM
        ]
        record = {
            "option_id": option["option_id"],
            "threats": deepcopy(option["threats"]),
            "residual_risk_ppm": max(
                threat["residual_risk_ppm"] for threat in option["threats"]
            ),
            "blocking_threat_ids": blocking,
        }
        options.append(record)
        by_id[option["option_id"]] = record
    risk_status = (
        "blocked"
        if preferred is None or by_id[preferred]["blocking_threat_ids"]
        else "bounded"
    )
    return _with_output_digest(
        {
            "record_type": "architect-threat-model",
            "schema_version": 1,
            **_output_scope(request, request_digest),
            "options": options,
            "risk_status": risk_status,
            "risk_acceptance_authorized": False,
        }
    )


def _migration_status(objective_state: str) -> str:
    return (
        "blocked"
        if objective_state == "blocked"
        else "recovery-required"
        if objective_state == "recovering"
        else "proposed"
    )


def _migration_plan(request: Mapping[str, Any], request_digest: str) -> dict[str, Any]:
    return _with_output_digest(
        {
            "record_type": "architect-migration-plan",
            "schema_version": 1,
            **_output_scope(request, request_digest),
            "options": [
                {
                    "option_id": option["option_id"],
                    "steps": deepcopy(option["migration_steps"]),
                    "status": _migration_status(request["objective_state"]),
                }
                for option in request["options"]
            ],
            "migration_authorized": False,
        }
    )


def _rollback_status(objective_state: str) -> str:
    return (
        "blocked"
        if objective_state == "blocked"
        else "recovery-required"
        if objective_state == "recovering"
        else "required"
    )


def _rollback_plan(request: Mapping[str, Any], request_digest: str) -> dict[str, Any]:
    return _with_output_digest(
        {
            "record_type": "architect-rollback-plan",
            "schema_version": 1,
            **_output_scope(request, request_digest),
            "options": [
                {
                    "option_id": option["option_id"],
                    "steps": deepcopy(option["rollback_steps"]),
                    "status": _rollback_status(request["objective_state"]),
                }
                for option in request["options"]
            ],
            "rollback_authorized": False,
        }
    )


def _verification_plan(request: Mapping[str, Any], request_digest: str) -> dict[str, Any]:
    return _with_output_digest(
        {
            "record_type": "architect-verification-plan",
            "schema_version": 1,
            **_output_scope(request, request_digest),
            "options": [
                {
                    "option_id": option["option_id"],
                    "steps": deepcopy(option["verification_steps"]),
                    "coverage_complete": True,
                }
                for option in request["options"]
            ],
            "verification_status": "planned",
            "verification_executed": False,
        }
    )


def _allocate_axis(
    ceiling: int,
    rollback_ppm: int,
    verification_ppm: int,
) -> dict[str, Any]:
    rollback = ceiling * rollback_ppm // 1_000_000
    verification = ceiling * verification_ppm // 1_000_000
    if rollback <= 0 or verification <= 0:
        raise ArchitectContractError("known resource axis cannot fund both required reserves")
    available = ceiling - rollback - verification
    if available < len(RESOURCE_SECTIONS):
        raise ArchitectContractError(
            "known resource axis cannot fund both reserves and all design sections"
        )
    quotient, remainder = divmod(available, len(RESOURCE_SECTIONS))
    allocations = {
        section: quotient + (1 if index < remainder else 0)
        for index, section in enumerate(RESOURCE_SECTIONS)
    }
    if any(value <= 0 for value in allocations.values()):
        raise ArchitectContractError("known resource allocation contains an unfunded section")
    if rollback + verification + sum(allocations.values()) != ceiling:
        raise ArchitectContractError("known resource allocation does not reconcile exactly")
    return {
        "ceiling": ceiling,
        "rollback_reserve": rollback,
        "verification_reserve": verification,
        "section_allocations": allocations,
    }


def _resource_plan(request: Mapping[str, Any], request_digest: str) -> dict[str, Any]:
    budgets = request["budgets"]
    if all(budgets[axis] is None for axis in RESOURCE_AXES):
        status = "unknown"
        axes = {
            axis: {
                "ceiling": None,
                "rollback_reserve": None,
                "verification_reserve": None,
                "section_allocations": {section: None for section in RESOURCE_SECTIONS},
            }
            for axis in RESOURCE_AXES
        }
    else:
        status = "known"
        rollback_ppm = request["rollback_reserve_ppm"]
        verification_ppm = request["verification_reserve_ppm"]
        if type(rollback_ppm) is not int or type(verification_ppm) is not int:
            raise ArchitectContractError("known budgets lack exact reserve percentages")
        axes = {
            axis: _allocate_axis(budgets[axis], rollback_ppm, verification_ppm)
            for axis in RESOURCE_AXES
        }
    return _with_output_digest(
        {
            "record_type": "architect-resource-plan",
            "schema_version": 1,
            **_output_scope(request, request_digest),
            "accounting_status": status,
            "lease_status": "not-issued",
            "rollback_reserve_ppm": request["rollback_reserve_ppm"],
            "verification_reserve_ppm": request["verification_reserve_ppm"],
            "sections": list(RESOURCE_SECTIONS),
            "axes": axes,
            "budget_authorized": False,
        }
    )


def _handoff(
    request: Mapping[str, Any],
    request_digest: str,
    analysis: Mapping[str, Any],
    resource: Mapping[str, Any],
) -> dict[str, Any]:
    preferred = analysis["provisional_preferred_option_id"]
    if request["objective_state"] in {"blocked", "recovering"}:
        next_role, reason = "steward", "objective-recovery-or-block-review"
    elif analysis["iteration_status"] == "repeated":
        next_role, reason = "steward", "repeated-design-review"
    elif preferred is None:
        next_role, reason = "steward", "no-viable-option-review"
    elif resource["accounting_status"] == "unknown":
        next_role, reason = "steward", "resource-accounting-review"
    else:
        # Caller labels cannot establish independent review, so Builder is not eligible.
        next_role, reason = "curator", "independence-and-evidence-review"
    required = sorted(
        {
            *request["evidence_refs"],
            *request["rollback_refs"],
            *analysis["selection_reasons"],
            reason,
        }
    )
    requested = request["requested_next_role"]
    return _with_output_digest(
        {
            "record_type": "architect-handoff",
            "schema_version": 1,
            **_output_scope(request, request_digest),
            "next_role": next_role,
            "requested_next_role": requested,
            "requested_role_eligible": requested == next_role,
            "reason": reason,
            "provisional_option_id": preferred,
            "required_refs": required,
            "implementation_authorized": False,
            "activation_authorized": False,
        }
    )


def compile_architect_design(request: Mapping[str, Any]) -> dict[str, Any]:
    copied = _validated_request(request)
    successor = compile_architect_successor()
    request_digest = digest(copied)
    option_analysis, preferred, iteration_status = _option_analysis(copied, request_digest)
    resource = _resource_plan(copied, request_digest)
    outputs = {
        "claim_integration": _claim_integration(copied, request_digest),
        "option_analysis": option_analysis,
        "architecture": _architecture(copied, request_digest, preferred, iteration_status),
        "interface_contract": _interfaces(copied, request_digest),
        "threat_model": _threat_model(copied, request_digest, preferred),
        "migration_plan": _migration_plan(copied, request_digest),
        "rollback_plan": _rollback_plan(copied, request_digest),
        "verification_plan": _verification_plan(copied, request_digest),
        "resource_plan": resource,
        "handoff": _handoff(copied, request_digest, option_analysis, resource),
    }
    body = {
        "record_type": "architect-design-envelope",
        "schema_version": 1,
        "request_id": copied["request_id"],
        "objective_id": copied["objective_id"],
        "tenant_id": copied["tenant_id"],
        "repository_id": copied["repository_id"],
        "successor_digest": successor["content_digest"],
        "request_digest": request_digest,
        "request_snapshot": deepcopy(copied),
        "outputs": outputs,
        "activation": "inert",
        "authority": "none",
        "public": False,
    }
    envelope = {**body, "design_digest": digest(body)}
    validation = validate_architect(
        "architect-design-envelope-v1",
        envelope,
        enforce_canonical_envelope=False,
    )
    if not validation.valid:
        raise ArchitectContractError(
            "generated Architect design is invalid: " + "; ".join(validation.issues)
        )
    return deepcopy(envelope)


def architect_design_bytes(request: Mapping[str, Any]) -> bytes:
    return canonical_bytes(compile_architect_design(request))


def _option(
    *,
    prefix: str,
    summary: str,
    rationale: str,
    unknowns: list[str],
    violations: list[str],
    residual_risks: tuple[int, int],
    score: int,
) -> dict[str, Any]:
    component_a = f"component:{prefix}:contracts"
    component_b = f"component:{prefix}:compiler"
    interface = f"interface:{prefix}:compile"
    invariant_a = f"invariant:{prefix}:inert"
    invariant_b = f"invariant:{prefix}:deterministic"
    threat_a = f"threat:{prefix}:authority"
    threat_b = f"threat:{prefix}:tamper"
    boundary = f"boundary:{prefix}:input"
    migration_a = f"migration:{prefix}:additive"
    migration_b = f"migration:{prefix}:verify"
    rollback_a = f"rollback:{prefix}:remove-code"
    rollback_b = f"rollback:{prefix}:remove-evidence"
    verification = f"verification:{prefix}:complete"
    return {
        "option_id": f"option:{prefix}",
        "summary": summary,
        "rationale": rationale,
        "unknowns": unknowns,
        "violations": violations,
        "components": [
            {
                "component_id": component_a,
                "responsibility": "Validate strict Architect inputs and typed outputs.",
                "authority": "none",
                "data_classes": ["safe-public-metadata", "design-contract"],
            },
            {
                "component_id": component_b,
                "responsibility": "Compile deterministic inert architecture metadata.",
                "authority": "none",
                "data_classes": ["safe-public-metadata", "design-envelope"],
            },
        ],
        "interfaces": [
            {
                "interface_id": interface,
                "source_component_id": component_a,
                "target_component_id": component_b,
                "contract": "Strict validated request enters a deterministic compiler.",
                "version": "1",
                "compatibility": "compatible" if not violations else "unknown",
            }
        ],
        "invariants": [
            {
                "invariant_id": invariant_a,
                "statement": "The candidate remains package-private, authority-free, and inert.",
            },
            {
                "invariant_id": invariant_b,
                "statement": "Equivalent admitted requests produce byte-identical designs.",
            },
        ],
        "trust_boundaries": [
            {
                "boundary_id": boundary,
                "source_component_id": component_a,
                "target_component_id": component_b,
                "data_classes": ["safe-public-metadata", "design-contract"],
                "threat_ids": [threat_a, threat_b],
            }
        ],
        "threats": [
            {
                "threat_id": threat_a,
                "statement": "Planning metadata is mistaken for implementation authority.",
                "likelihood": "medium",
                "impact": "critical",
                "mitigation_refs": [invariant_a, rollback_a],
                "residual_risk_ppm": residual_risks[0],
            },
            {
                "threat_id": threat_b,
                "statement": "A nested output is changed and coherently resealed.",
                "likelihood": "medium",
                "impact": "high",
                "mitigation_refs": [invariant_b, verification],
                "residual_risk_ppm": residual_risks[1],
            },
        ],
        "migration_steps": [
            {
                "step_id": migration_a,
                "description": "Add package-private Architect modules without selecting them.",
                "depends_on": [],
                "rollback_step_id": rollback_a,
            },
            {
                "step_id": migration_b,
                "description": "Verify contracts, compatibility, wheel contents, and evidence.",
                "depends_on": [migration_a],
                "rollback_step_id": rollback_b,
            },
        ],
        "rollback_steps": [
            {
                "rollback_step_id": rollback_a,
                "description": "Remove the package-private Architect modules.",
                "restores_ref": BASE_DEFINITION_ID,
            },
            {
                "rollback_step_id": rollback_b,
                "description": "Remove Phase 5B projections while retaining Git history.",
                "restores_ref": "phase5a:terminal-head",
            },
        ],
        "verification_steps": [
            {
                "verification_id": verification,
                "method": "Run strict contract, adversarial, compatibility, and wheel checks.",
                "acceptance_refs": [
                    "acceptance:authority",
                    "acceptance:contracts",
                    "acceptance:resources",
                    "acceptance:rollback",
                    "acceptance:verification",
                ],
                "invariant_refs": [invariant_a, invariant_b],
                "threat_refs": [threat_a, threat_b],
                "migration_step_refs": [migration_a, migration_b],
                "rollback_step_refs": [rollback_a, rollback_b],
            }
        ],
        "score_inputs": {field: score for field in SCORE_FIELDS},
    }


def example_architect_request(*, known_budget: bool = True) -> dict[str, Any]:
    modular = _option(
        prefix="modular-inert",
        summary="Separate strict contracts from a deterministic package-private compiler.",
        rationale="Preserves authority boundaries, permits additive review, and has direct rollback.",
        unknowns=[],
        violations=[],
        residual_risks=(100_000, 150_000),
        score=900_000,
    )
    monolithic = _option(
        prefix="monolithic-active",
        summary="Combine design, execution, and runtime selection in one active component.",
        rationale="Scores highly on caller preference but violates the constitutional authority boundary.",
        unknowns=["unknown:active-runtime-evidence"],
        violations=["violation:authority-expansion"],
        residual_risks=(900_000, 850_000),
        score=999_000,
    )
    claims = [
        {
            "claim_id": "claim:typed-contracts",
            "statement": "Architect outputs require separate strict typed contracts.",
            "disposition": "adopt",
            "material": False,
            "evidence_refs": ["evidence:phase5a-terminal"],
            "acceptance_refs": ["acceptance:contracts"],
        },
        {
            "claim_id": "claim:no-authority-expansion",
            "statement": "Architecture planning must not confer implementation authority.",
            "disposition": "adapt",
            "material": True,
            "evidence_refs": ["evidence:phase5a-terminal"],
            "acceptance_refs": ["acceptance:authority"],
        },
        {
            "claim_id": "claim:complete-verification",
            "statement": "Each option must carry complete independent verification coverage.",
            "disposition": "adapt",
            "material": True,
            "evidence_refs": ["evidence:phase5a-terminal"],
            "acceptance_refs": ["acceptance:verification"],
        },
        {
            "claim_id": "claim:resource-reserves",
            "statement": "Rollback and verification reserves must remain positive and exact.",
            "disposition": "adopt",
            "material": False,
            "evidence_refs": ["evidence:phase5a-terminal"],
            "acceptance_refs": ["acceptance:resources"],
        },
        {
            "claim_id": "claim:live-runtime-binding",
            "statement": "The Architect candidate should select and activate a runtime design.",
            "disposition": "defer",
            "material": True,
            "evidence_refs": [],
            "acceptance_refs": [],
        },
    ]
    claim_mappings = []
    for option in (modular, monolithic):
        local = sorted(_option_design_ids(option))
        for claim in claims[:4]:
            claim_mappings.append(
                {
                    "claim_id": claim["claim_id"],
                    "option_id": option["option_id"],
                    "design_refs": local,
                }
            )
    budgets = (
        {
            "tokens": 120_000,
            "cost_microunits": 8_000_000,
            "elapsed_ms": 4_800_000,
            "tool_calls": 120,
        }
        if known_budget
        else {axis: None for axis in RESOURCE_AXES}
    )
    return {
        "record_type": "architect-design-request",
        "schema_version": 1,
        "request_id": "request:phase5b-example",
        "objective_id": "objective:phase5b-example",
        "tenant_id": "tenant:local",
        "repository_id": "repository:hive-mind-os",
        "objective": "Design an inert Architect successor with strict, reversible, request-bound outputs.",
        "constraints": ["remain-inert", "preserve-generation-zero", "retain-rollback"],
        "acceptance_criteria": [
            {
                "acceptance_id": "acceptance:contracts",
                "statement": "All thirteen strict contracts validate and fail closed.",
            },
            {
                "acceptance_id": "acceptance:rollback",
                "statement": "Every migration step has an exact local rollback path.",
            },
            {
                "acceptance_id": "acceptance:verification",
                "statement": "Every option independently covers acceptance, invariants, threats, migration, and rollback.",
            },
            {
                "acceptance_id": "acceptance:resources",
                "statement": "Each known resource axis reconciles positive reserves and all design sections.",
            },
            {
                "acceptance_id": "acceptance:authority",
                "statement": "No implementation, selection, risk, or activation authority is created.",
            },
        ],
        "evidence_refs": ["evidence:phase5a-terminal"],
        "rollback_refs": [BASE_DEFINITION_ID, "phase5a:terminal-head"],
        "claims": claims,
        "claim_mappings": claim_mappings,
        "options": [modular, monolithic],
        "budgets": budgets,
        "rollback_reserve_ppm": 100_000 if known_budget else None,
        "verification_reserve_ppm": 150_000 if known_budget else None,
        "actors": [
            {
                "role": role,
                "actor_id": f"procedural:{role}",
                "authenticated": False,
            }
            for role in COURT_ROLES
        ],
        "prior_design_fingerprints": [],
        "objective_state": "proposed",
        "requested_option_id": "option:monolithic-active",
        "requested_next_role": "builder",
    }
