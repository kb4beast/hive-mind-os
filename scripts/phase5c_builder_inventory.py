from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

import hive_mind_os
import hive_mind_os.package_system as package_system
from hive_mind_os import cli
from hive_mind_os.foundation.builder_playbook import (
    compile_builder_implementation,
    compile_builder_successor,
    example_builder_request,
)
from hive_mind_os.foundation.builder_playbook_contracts import (
    BUILDER_SCHEMA_NAMES,
    OUTPUT_FIELDS,
    OUTPUT_SCHEMA_BY_FIELD,
    RESOURCE_AXES,
    RESOURCE_SECTIONS,
    validate_builder,
    validate_builder_catalog,
)

OUTPUT_PATH = Path("evidence/phase5c/phase5c_builder_inventory.json")
BASE_HEAD = "43db53de7a41d9bc02e987776edc260594def4c8"
PHASE5B_INVENTORY_DIGEST = "sha256:193ad19a5a0ff9438d9c288a4dda7e23ce0c4df416520817126e1dbbd936c166"


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _digest_json(value: Any) -> str:
    return _digest_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    )


def _cli_parser_count() -> int:
    builders = (
        cli.build_parser,
        cli.build_audit_parser,
        cli.build_benchmark_parser,
        cli.build_defer_parser,
        cli.build_deliver_parser,
        cli.build_enqueue_parser,
        cli.build_experiment_parser,
        cli.build_ingest_parser,
        cli.build_missions_parser,
        cli.build_pit_episode_parser,
        cli.build_resume_parser,
        cli.build_serve_parser,
        cli.build_status_parser,
    )
    return len(tuple(builder() for builder in builders))


def _test_method_count(repository: Path) -> int:
    tree = ast.parse(
        (repository / "tests/test_phase5c_builder_playbook.py").read_text(encoding="utf-8")
    )
    return sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
        for node in ast.walk(tree)
    )


def _scalar_leaf_count(value: object) -> int:
    if type(value) is dict:
        return sum(
            _scalar_leaf_count(child)
            for key, child in value.items()  # type: ignore[union-attr]
            if key != "output_digest"
        )
    if type(value) is list:
        return sum(_scalar_leaf_count(child) for child in value)  # type: ignore[arg-type]
    return 1


def _resource_reconciles(implementation: dict[str, Any]) -> bool:
    resource = implementation["resource_accounting"]
    if resource["accounting_status"] == "unknown":
        return all(
            resource["axes"][axis]["ceiling"] is None
            and resource["axes"][axis]["checkpoint_reserve"] is None
            and resource["axes"][axis]["evidence_reserve"] is None
            and resource["axes"][axis]["rollback_reserve"] is None
            and all(
                value is None
                for value in resource["axes"][axis]["section_allocations"].values()
            )
            for axis in RESOURCE_AXES
        )
    for axis in RESOURCE_AXES:
        allocation = resource["axes"][axis]
        if allocation["checkpoint_reserve"] <= 0:
            return False
        if allocation["evidence_reserve"] <= 0:
            return False
        if allocation["rollback_reserve"] <= 0:
            return False
        if set(allocation["section_allocations"]) != set(RESOURCE_SECTIONS):
            return False
        if any(value <= 0 for value in allocation["section_allocations"].values()):
            return False
        observed = (
            allocation["checkpoint_reserve"]
            + allocation["evidence_reserve"]
            + allocation["rollback_reserve"]
            + sum(allocation["section_allocations"].values())
        )
        if observed != allocation["ceiling"]:
            return False
    return True


def build_phase5c_inventory(repository: Path) -> dict[str, Any]:
    successor = compile_builder_successor()
    request = example_builder_request()
    implementation = compile_builder_implementation(request)
    output_validity = {
        field: validate_builder(
            OUTPUT_SCHEMA_BY_FIELD[field], implementation["outputs"][field]
        ).valid
        for field in OUTPUT_FIELDS
    }
    implementation_paths = (
        ".github/workflows/ci.yml",
        "docs/architecture/ADR-035-BUILDER-DEEP-PLAYBOOK.md",
        "docs/architecture/ADR_INDEX.md",
        "docs/architecture/PHASE5C_BUILDER_CONTRACT.md",
        "docs/architecture/PHASE5C_MIGRATION_AND_ROLLBACK.md",
        "evidence/courts/phase5c-builder-playbook-court.md",
        "evidence/phase5a/phase5a_orchestrator_inventory.json",
        "evidence/phase5b/phase5b_architect_inventory.json",
        "evidence/phase5c/PHASE5C_AUDIT_LEDGER.md",
        "evidence/phase5c/PHASE5C_DISSENT.md",
        "evidence/phase5c/PHASE5C_INSTALLED_WHEEL_RECEIPT.md",
        "evidence/phase5c/procedural-role-review.json",
        "evidence/sources/PHASE5C_BUILDER_SOURCE_REGISTER.md",
        "scripts/phase5b_architect_inventory.py",
        "scripts/phase5c_builder_inventory.py",
        "scripts/verify_phase5c_installed_wheel.py",
        "src/hive_mind_os/foundation/builder_playbook.py",
        "src/hive_mind_os/foundation/builder_playbook_contracts.py",
        "tests/test_phase5c_builder_playbook.py",
    )
    output_leaf_counts = {
        field: _scalar_leaf_count(implementation["outputs"][field])
        for field in OUTPUT_FIELDS
    }
    root = Path(hive_mind_os.__file__).parent
    body = {
        "schema_version": 1,
        "phase": 5,
        "phase_item": "C",
        "base_head": BASE_HEAD,
        "phase5b_input": {"inventory_digest": PHASE5B_INVENTORY_DIGEST},
        "scope": "inert-builder-deep-playbook",
        "successor": {
            "agent_id": successor["agent_id"],
            "definition_id": successor["definition_id"],
            "content_digest": successor["content_digest"],
            "layer_count": len(successor["layers"]),
            "effective_capabilities": successor["effective_capabilities"],
            "tool_refs": successor["tool_refs"],
            "activation": successor["activation"],
            "authority": successor["authority"],
            "public": successor["public"],
        },
        "contracts": {
            "names": list(BUILDER_SCHEMA_NAMES),
            "count": len(BUILDER_SCHEMA_NAMES),
            "catalog_valid": validate_builder_catalog().valid,
        },
        "sample_implementation": {
            "request_id": implementation["request_id"],
            "request_digest": implementation["request_digest"],
            "objective_id": implementation["objective_id"],
            "tenant_id": implementation["tenant_id"],
            "repository_id": implementation["repository_id"],
            "implementation_digest": implementation["implementation_digest"],
            "envelope_valid": validate_builder(
                "builder-implementation-envelope-v1", implementation
            ).valid,
            "output_count": len(implementation["outputs"]),
            "output_validity": output_validity,
            "requirement_count": len(
                implementation["request_snapshot"]["adjudicated_requirements"]
            ),
            "acceptance_count": len(
                implementation["request_snapshot"]["acceptance_criteria"]
            ),
            "change_count": len(implementation["outputs"]["change_plan"]["ordered_changes"]),
            "test_count": len(implementation["outputs"]["test_plan"]["tests"]),
            "evidence_item_count": len(
                implementation["outputs"]["execution_evidence_plan"]["evidence_items"]
            ),
            "checkpoint_count": len(
                implementation["outputs"]["rollback_plan"]["checkpoints"]
            ),
            "rollback_step_count": len(
                implementation["outputs"]["rollback_plan"]["steps"]
            ),
            "artifact_count": len(
                implementation["outputs"]["artifact_manifest"]["artifacts"]
            ),
            "resource_accounting_status": implementation["resource_accounting"][
                "accounting_status"
            ],
            "resource_reconciles": _resource_reconciles(implementation),
            "handoff_role": implementation["outputs"]["curator_handoff"]["next_role"],
            "authenticated_distinct_actors": implementation["outputs"][
                "curator_handoff"
            ]["authenticated_distinct_actors"],
            "same_assistant_performed_procedural_passes": implementation["outputs"][
                "curator_handoff"
            ]["same_assistant_performed_procedural_passes"],
            "independence_claimed": implementation["outputs"]["curator_handoff"][
                "independence_claimed"
            ],
            "implementation_authorized": implementation["outputs"][
                "implementation_scope"
            ]["implementation_authorized"],
            "execution_authorized": implementation["outputs"]["change_plan"][
                "execution_authorized"
            ],
            "test_results_authorized": implementation["outputs"]["test_plan"][
                "test_results_authorized"
            ],
            "completion_authorized": implementation["outputs"]["curator_handoff"][
                "completion_authorized"
            ],
            "promotion_authorized": implementation["outputs"]["curator_handoff"][
                "promotion_authorized"
            ],
            "activation_authorized": implementation["outputs"]["curator_handoff"][
                "activation_authorized"
            ],
        },
        "protected_surfaces": {
            "root_api_count": len(hive_mind_os.__all__),
            "package_api_count": len(package_system.__all__),
            "cli_parser_count": _cli_parser_count(),
            "json_resource_count": len(tuple(root.rglob("*.json"))),
            "root_api_digest": _digest_bytes(
                (repository / "src/hive_mind_os/__init__.py").read_bytes()
            ),
            "cli_digest": _digest_bytes(
                (repository / "src/hive_mind_os/cli.py").read_bytes()
            ),
            "store_digest": _digest_bytes(
                (repository / "src/hive_mind_os/foundation/store.py").read_bytes()
            ),
            "brain_digest": _digest_bytes(
                (repository / "src/hive_mind_os/foundation/brain.py").read_bytes()
            ),
            "phase5a_orchestrator_digest": _digest_bytes(
                (
                    repository
                    / "src/hive_mind_os/foundation/orchestrator_playbook.py"
                ).read_bytes()
            ),
            "phase5b_architect_digest": _digest_bytes(
                (
                    repository
                    / "src/hive_mind_os/foundation/architect_playbook.py"
                ).read_bytes()
            ),
        },
        "implementation": {
            path: _digest_bytes((repository / path).read_bytes())
            for path in implementation_paths
            if (repository / path).is_file()
        },
        "focused_test_method_count": _test_method_count(repository),
        "adversarial_resealed_leaf_count": sum(output_leaf_counts.values()),
        "adversarial_resealed_leaf_counts": output_leaf_counts,
        "external_dependencies_added": 0,
        "json_resources_added": 0,
        "public_api_added": 0,
        "cli_added": 0,
        "runtime_binding_added": False,
        "store_or_migration_added": False,
        "provider_or_tool_binding_added": False,
        "scheduler_binding_added": False,
        "budget_lease_issued": False,
        "authenticated_independence_claimed": False,
        "implementation_executed_by_playbook": False,
        "tests_executed_by_playbook": False,
        "completion_claimed_by_playbook": False,
        "value_claimed": False,
        "learning_claimed": False,
        "promotion_authorized": False,
        "activation_authorized": False,
        "production_ready": False,
        "release_ready": False,
        "superiority_claimed": False,
    }
    return {**body, "inventory_digest": _digest_json(body)}


def main() -> int:
    repository = Path(__file__).parents[1]
    inventory = build_phase5c_inventory(repository)
    destination = repository / OUTPUT_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(destination)
    print(inventory["inventory_digest"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
