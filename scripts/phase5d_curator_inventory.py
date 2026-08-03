from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

import hive_mind_os
import hive_mind_os.package_system as package_system
from hive_mind_os import cli
from hive_mind_os.foundation.curator_playbook import (
    compile_curator_successor,
    compile_curator_verification,
    example_curator_request,
)
from hive_mind_os.foundation.curator_playbook_contracts import (
    CURATOR_SCHEMA_NAMES,
    OUTPUT_FIELDS,
    OUTPUT_SCHEMA_BY_FIELD,
    RESOURCE_AXES,
    RESOURCE_SECTIONS,
    validate_curator,
    validate_curator_catalog,
)

OUTPUT_PATH = Path("evidence/phase5d/phase5d_curator_inventory.json")
BASE_HEAD = "92a7f6ed96186a2a1c8fd1fd55147663f25588d9"
PHASE5C_INVENTORY_DIGEST = "sha256:95655303cf9f130d99c4aa64a1fa2a9e2ec0d9a2ce7cd464311520c6fbcd9034"


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
        (repository / "tests/test_phase5d_curator_playbook.py").read_text(encoding="utf-8")
    )
    return sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
        for node in ast.walk(tree)
    )


def _compatibility_test_count(repository: Path) -> int:
    tree = ast.parse(
        (repository / "tests/test_phase5d_curator_playbook.py").read_text(encoding="utf-8")
    )
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "CuratorCompatibilityTests":
            return sum(
                isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name.startswith("test_")
                for item in node.body
            )
    return 0


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


def _resource_reconciles(verification: dict[str, Any]) -> bool:
    resource = verification["resource_accounting"]
    if resource["accounting_status"] == "unknown":
        return all(
            resource["axes"][axis]["ceiling"] is None
            and resource["axes"][axis]["verification_reserve"] is None
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
        for reserve in ("verification_reserve", "evidence_reserve", "rollback_reserve"):
            if allocation[reserve] <= 0:
                return False
        if set(allocation["section_allocations"]) != set(RESOURCE_SECTIONS):
            return False
        if any(value <= 0 for value in allocation["section_allocations"].values()):
            return False
        observed = (
            allocation["verification_reserve"]
            + allocation["evidence_reserve"]
            + allocation["rollback_reserve"]
            + sum(allocation["section_allocations"].values())
        )
        if observed != allocation["ceiling"]:
            return False
    return True


def build_phase5d_inventory(repository: Path) -> dict[str, Any]:
    successor = compile_curator_successor()
    request = example_curator_request()
    verification = compile_curator_verification(request)
    output_validity = {
        field: validate_curator(
            OUTPUT_SCHEMA_BY_FIELD[field], verification["outputs"][field]
        ).valid
        for field in OUTPUT_FIELDS
    }
    implementation_paths = (
        ".github/workflows/ci.yml",
        "docs/architecture/ADR-036-CURATOR-DEEP-PLAYBOOK.md",
        "docs/architecture/ADR_INDEX.md",
        "docs/architecture/PHASE5D_CURATOR_CONTRACT.md",
        "docs/architecture/PHASE5D_MIGRATION_AND_ROLLBACK.md",
        "evidence/courts/phase5d-curator-playbook-court.md",
        "evidence/phase5a/phase5a_orchestrator_inventory.json",
        "evidence/phase5b/phase5b_architect_inventory.json",
        "evidence/phase5c/phase5c_builder_inventory.json",
        "evidence/phase5d/PHASE5D_AUDIT_LEDGER.md",
        "evidence/phase5d/PHASE5D_DISSENT.md",
        "evidence/phase5d/PHASE5D_INSTALLED_WHEEL_RECEIPT.md",
        "evidence/phase5d/procedural-role-review.json",
        "evidence/sources/PHASE5D_CURATOR_SOURCE_REGISTER.md",
        "scripts/phase5c_builder_inventory.py",
        "scripts/phase5d_curator_inventory.py",
        "scripts/verify_phase5d_installed_wheel.py",
        "src/hive_mind_os/foundation/curator_playbook.py",
        "src/hive_mind_os/foundation/curator_playbook_contracts.py",
        "tests/test_phase5d_curator_playbook.py",
    )
    output_leaf_counts = {
        field: _scalar_leaf_count(verification["outputs"][field])
        for field in OUTPUT_FIELDS
    }
    root = Path(hive_mind_os.__file__).parent
    recommendation = verification["outputs"]["release_recommendation"]
    body = {
        "schema_version": 1,
        "phase": 5,
        "phase_item": "D",
        "base_head": BASE_HEAD,
        "phase5c_input": {"inventory_digest": PHASE5C_INVENTORY_DIGEST},
        "scope": "inert-curator-deep-playbook",
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
            "names": list(CURATOR_SCHEMA_NAMES),
            "count": len(CURATOR_SCHEMA_NAMES),
            "catalog_valid": validate_curator_catalog().valid,
        },
        "sample_verification": {
            "request_id": verification["request_id"],
            "request_digest": verification["request_digest"],
            "objective_id": verification["objective_id"],
            "tenant_id": verification["tenant_id"],
            "repository_id": verification["repository_id"],
            "verification_digest": verification["verification_digest"],
            "envelope_valid": validate_curator(
                "curator-verification-envelope-v1", verification
            ).valid,
            "output_count": len(verification["outputs"]),
            "output_validity": output_validity,
            "claim_count": len(verification["request_snapshot"]["claims"]),
            "acceptance_count": len(
                verification["request_snapshot"]["acceptance_criteria"]
            ),
            "sealed_check_count": len(
                verification["request_snapshot"]["sealed_checks"]
            ),
            "evidence_count": len(
                verification["request_snapshot"]["observed_evidence"]
            ),
            "source_count": len(verification["request_snapshot"]["sources"]),
            "regression_target_count": len(
                verification["request_snapshot"]["regression_targets"]
            ),
            "resource_accounting_status": verification["resource_accounting"][
                "accounting_status"
            ],
            "resource_reconciles": _resource_reconciles(verification),
            "structural_status": recommendation["structural_status"],
            "recommendation": recommendation["recommendation"],
            "authenticated_distinct_actors": recommendation[
                "authenticated_distinct_actors"
            ],
            "same_assistant_performed_procedural_passes": recommendation[
                "same_assistant_performed_procedural_passes"
            ],
            "independence_claimed": recommendation["independence_claimed"],
            "implementation_authorized": recommendation["authority_state"][
                "implementation_authorized"
            ],
            "execution_authorized": recommendation["authority_state"][
                "execution_authorized"
            ],
            "test_results_authorized": recommendation["authority_state"][
                "test_result_authorized"
            ],
            "completion_authorized": recommendation["authority_state"][
                "completion_authorized"
            ],
            "release_authorized": recommendation["release_authorized"],
            "approval_authorized": recommendation["approval_authorized"],
            "promotion_authorized": recommendation["authority_state"][
                "promotion_authorized"
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
            "legacy_curator_digest": _digest_bytes(
                (repository / "src/hive_mind_os/curator.py").read_bytes()
            ),
            "phase5a_orchestrator_digest": _digest_bytes(
                (repository / "src/hive_mind_os/foundation/orchestrator_playbook.py").read_bytes()
            ),
            "phase5b_architect_digest": _digest_bytes(
                (repository / "src/hive_mind_os/foundation/architect_playbook.py").read_bytes()
            ),
            "phase5c_builder_digest": _digest_bytes(
                (repository / "src/hive_mind_os/foundation/builder_playbook.py").read_bytes()
            ),
        },
        "implementation": {
            path: _digest_bytes((repository / path).read_bytes())
            for path in implementation_paths
            if (repository / path).is_file()
        },
        "focused_test_method_count": _test_method_count(repository),
        "compatibility_test_method_count": _compatibility_test_count(repository),
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
        "commands_executed_by_playbook": False,
        "tests_executed_by_playbook": False,
        "completion_claimed_by_playbook": False,
        "release_authorized": False,
        "approval_authorized": False,
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
    inventory = build_phase5d_inventory(repository)
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
