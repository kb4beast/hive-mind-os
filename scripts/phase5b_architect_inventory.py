from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import hive_mind_os
import hive_mind_os.package_system as package_system
from hive_mind_os.foundation.architect_playbook import (
    compile_architect_design,
    compile_architect_successor,
    example_architect_request,
)
from hive_mind_os.foundation.architect_playbook_contracts import (
    ARCHITECT_SCHEMA_NAMES,
    OUTPUT_FIELDS,
    OUTPUT_SCHEMA_BY_FIELD,
    RESOURCE_AXES,
    RESOURCE_SECTIONS,
    validate_architect,
    validate_architect_catalog,
)
from scripts.phase1_surface_inventory import build_inventory, cli_inventory

OUTPUT_PATH = Path("evidence/phase5b/phase5b_architect_inventory.json")
BASE_HEAD = "ed1c0a76c52335e7cf92ba92b2f4d401116f85e1"
PHASE5A_INVENTORY_DIGEST = (
    "sha256:a972c2618e779f5031495189362e4bccf2f3c5ed96c403a2d4731be3ba65ef43"
)


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _digest_json(value: Any) -> str:
    return _digest_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    )


def _resource_reconciles(design: dict[str, Any]) -> bool:
    resource = design["outputs"]["resource_plan"]
    if resource["accounting_status"] == "unknown":
        return all(
            resource["axes"][axis]["ceiling"] is None
            and resource["axes"][axis]["rollback_reserve"] is None
            and resource["axes"][axis]["verification_reserve"] is None
            and all(
                value is None
                for value in resource["axes"][axis]["section_allocations"].values()
            )
            for axis in RESOURCE_AXES
        )
    for axis in RESOURCE_AXES:
        allocation = resource["axes"][axis]
        if allocation["rollback_reserve"] <= 0:
            return False
        if allocation["verification_reserve"] <= 0:
            return False
        if set(allocation["section_allocations"]) != set(RESOURCE_SECTIONS):
            return False
        if any(value <= 0 for value in allocation["section_allocations"].values()):
            return False
        observed = (
            allocation["rollback_reserve"]
            + allocation["verification_reserve"]
            + sum(allocation["section_allocations"].values())
        )
        if observed != allocation["ceiling"]:
            return False
    return True


def build_phase5b_inventory(repository: Path) -> dict[str, Any]:
    successor = compile_architect_successor()
    design = compile_architect_design(example_architect_request())
    surface = build_inventory(repository)
    output_validity = {
        field: validate_architect(
            OUTPUT_SCHEMA_BY_FIELD[field], design["outputs"][field]
        ).valid
        for field in OUTPUT_FIELDS
    }
    rankings = design["outputs"]["option_analysis"]["rankings"]
    options = design["request_snapshot"]["options"]
    implementation_paths = (
        ".github/workflows/ci.yml",
        "docs/architecture/ADR-034-ARCHITECT-DEEP-PLAYBOOK.md",
        "docs/architecture/ADR_INDEX.md",
        "docs/architecture/PHASE5B_ARCHITECT_CONTRACT.md",
        "docs/architecture/PHASE5B_MIGRATION_AND_ROLLBACK.md",
        "evidence/courts/phase5b-architect-playbook-court.md",
        "evidence/phase5a/phase5a_orchestrator_inventory.json",
        "evidence/phase5b/PHASE5B_AUDIT_LEDGER.md",
        "evidence/phase5b/PHASE5B_DISSENT.md",
        "evidence/phase5b/PHASE5B_INSTALLED_WHEEL_RECEIPT.md",
        "evidence/phase5b/procedural-role-review.json",
        "evidence/sources/PHASE5B_ARCHITECT_SOURCE_REGISTER.md",
        "scripts/phase5b_architect_inventory.py",
        "scripts/verify_phase5b_installed_wheel.py",
        "src/hive_mind_os/foundation/architect_playbook.py",
        "src/hive_mind_os/foundation/architect_playbook_contracts.py",
        "tests/test_phase5b_architect_playbook.py",
    )
    body = {
        "schema_version": 1,
        "phase": 5,
        "phase_item": "B",
        "base_head": BASE_HEAD,
        "phase5a_input": {"inventory_digest": PHASE5A_INVENTORY_DIGEST},
        "scope": "inert-architect-deep-playbook",
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
            "names": list(ARCHITECT_SCHEMA_NAMES),
            "count": len(ARCHITECT_SCHEMA_NAMES),
            "catalog_valid": validate_architect_catalog().valid,
        },
        "sample_design": {
            "request_id": design["request_id"],
            "request_digest": design["request_digest"],
            "objective_id": design["objective_id"],
            "tenant_id": design["tenant_id"],
            "repository_id": design["repository_id"],
            "design_digest": design["design_digest"],
            "envelope_valid": validate_architect(
                "architect-design-envelope-v1", design
            ).valid,
            "output_count": len(design["outputs"]),
            "output_validity": output_validity,
            "option_count": len(options),
            "claim_count": len(design["request_snapshot"]["claims"]),
            "claim_mapping_count": len(
                design["outputs"]["claim_integration"]["mappings"]
            ),
            "ranking_count": len(rankings),
            "viable_option_count": sum(
                item["viability_status"] == "viable" for item in rankings
            ),
            "blocked_option_count": sum(
                item["viability_status"] == "blocked" for item in rankings
            ),
            "requested_option_id": design["outputs"]["option_analysis"][
                "requested_option_id"
            ],
            "requested_option_eligible": design["outputs"]["option_analysis"][
                "requested_option_eligible"
            ],
            "provisional_preferred_option_id": design["outputs"]["option_analysis"][
                "provisional_preferred_option_id"
            ],
            "selection_status": design["outputs"]["option_analysis"][
                "selection_status"
            ],
            "resource_accounting_status": design["outputs"]["resource_plan"][
                "accounting_status"
            ],
            "resource_reconciles": _resource_reconciles(design),
            "handoff_role": design["outputs"]["handoff"]["next_role"],
            "implementation_authorized": design["outputs"]["handoff"][
                "implementation_authorized"
            ],
            "selection_authorized": design["outputs"]["handoff"][
                "selection_authorized"
            ],
            "activation_authorized": design["outputs"]["handoff"][
                "activation_authorized"
            ],
        },
        "protected_surfaces": {
            "root_api_count": len(hive_mind_os.__all__),
            "package_api_count": len(package_system.__all__),
            "cli_parser_count": cli_inventory()["parser_count"],
            "definition_count": surface["observable_module_surface"][
                "definition_count"
            ],
            "json_resource_count": len(
                tuple(Path(hive_mind_os.__file__).parent.rglob("*.json"))
            ),
            "runtime_unclassified_count": surface["runtime_effects"][
                "unclassified_candidate_count"
            ],
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
        },
        "implementation": {
            path: _digest_bytes((repository / path).read_bytes())
            for path in implementation_paths
            if (repository / path).is_file()
        },
        "focused_test_method_count": 51,
        "adversarial_resealed_leaf_count": 442,
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
        "design_quality_measured": False,
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
    inventory = build_phase5b_inventory(repository)
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
