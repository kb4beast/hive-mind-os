from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import hive_mind_os
import hive_mind_os.package_system as package_system
from hive_mind_os.foundation.orchestrator_playbook import (
    compile_orchestrator_plan,
    compile_orchestrator_successor,
    example_orchestrator_request,
)
from hive_mind_os.foundation.orchestrator_playbook_contracts import (
    ORCHESTRATOR_SCHEMA_NAMES,
    validate_orchestrator,
    validate_orchestrator_catalog,
)
from scripts.phase1_surface_inventory import build_inventory, cli_inventory

OUTPUT_PATH = Path("evidence/phase5a/phase5a_orchestrator_inventory.json")
BASE_HEAD = "32f41bbb013464d1c3a98aab95f5bd75705b7ba2"
PHASE4D_INVENTORY_DIGEST = (
    "sha256:d54189883c3d13db297e63192623604d1c377e35f936175bd07b5359e6f7446e"
)


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _digest_json(value: Any) -> str:
    return _digest_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    )


def build_phase5a_inventory(repository: Path) -> dict[str, Any]:
    successor = compile_orchestrator_successor()
    request = example_orchestrator_request()
    plan = compile_orchestrator_plan(request)
    surface = build_inventory(repository)
    implementation_paths = (
        ".github/workflows/ci.yml",
        "docs/architecture/ADR-033-ORCHESTRATOR-DEEP-PLAYBOOK.md",
        "docs/architecture/ADR_INDEX.md",
        "docs/architecture/PHASE5A_MIGRATION_AND_ROLLBACK.md",
        "docs/architecture/PHASE5A_ORCHESTRATOR_CONTRACT.md",
        "evidence/courts/phase5a-orchestrator-playbook-court.md",
        "evidence/phase5a/PHASE5A_AUDIT_LEDGER.md",
        "evidence/phase5a/PHASE5A_DISSENT.md",
        "evidence/phase5a/PHASE5A_INSTALLED_WHEEL_RECEIPT.md",
        "evidence/phase5a/procedural-role-review.json",
        "evidence/sources/PHASE5A_ORCHESTRATOR_SOURCE_REGISTER.md",
        "scripts/phase5a_orchestrator_inventory.py",
        "scripts/verify_phase5a_installed_wheel.py",
        "src/hive_mind_os/foundation/orchestrator_playbook.py",
        "src/hive_mind_os/foundation/orchestrator_playbook_contracts.py",
        "tests/test_phase5a_orchestrator_playbook.py",
    )
    output_validity = {
        field: validate_orchestrator(schema, plan["outputs"][field]).valid
        for schema, field in (
            ("orchestrator-objective-decomposition-v1", "objective_decomposition"),
            ("orchestrator-dependency-graph-v1", "dependency_graph"),
            ("orchestrator-budget-plan-v1", "budget_plan"),
            ("orchestrator-court-schedule-v1", "court_schedule"),
            ("orchestrator-recovery-plan-v1", "recovery_plan"),
            ("orchestrator-stop-decision-v1", "stop_decision"),
            ("orchestrator-handoff-v1", "handoff"),
        )
    }
    body = {
        "schema_version": 1,
        "phase": 5,
        "phase_item": "A",
        "base_head": BASE_HEAD,
        "phase4d_input": {"inventory_digest": PHASE4D_INVENTORY_DIGEST},
        "scope": "inert-orchestrator-deep-playbook",
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
            "max_handoff_refs": successor["budgets"]["max_handoff_refs"],
        },
        "contracts": {
            "names": list(ORCHESTRATOR_SCHEMA_NAMES),
            "count": len(ORCHESTRATOR_SCHEMA_NAMES),
            "catalog_valid": validate_orchestrator_catalog().valid,
        },
        "sample_plan": {
            "request_id": plan["request_id"],
            "request_digest": plan["request_digest"],
            "objective_id": plan["objective_id"],
            "tenant_id": plan["tenant_id"],
            "repository_id": plan["repository_id"],
            "plan_digest": plan["plan_digest"],
            "envelope_valid": validate_orchestrator(
                "orchestrator-plan-envelope-v1", plan
            ).valid,
            "output_count": len(plan["outputs"]),
            "output_validity": output_validity,
            "work_item_count": len(plan["outputs"]["objective_decomposition"]["work_items"]),
            "dependency_count": len(plan["outputs"]["dependency_graph"]["edges"]),
            "budget_status": plan["outputs"]["budget_plan"]["accounting_status"],
            "lease_status": plan["outputs"]["budget_plan"]["lease_status"],
            "independence_status": plan["outputs"]["court_schedule"]["independence_status"],
            "authenticated_distinct_actors": plan["outputs"][
                "court_schedule"
            ]["authenticated_distinct_actors"],
            "stop_decision": plan["outputs"]["stop_decision"]["decision"],
            "evidence_status": plan["outputs"]["stop_decision"]["evidence_status"],
            "handoff_role": plan["outputs"]["handoff"]["next_role"],
            "handoff_required_ref_count": len(
                plan["outputs"]["handoff"]["required_refs"]
            ),
            "completion_authorized": plan["outputs"]["stop_decision"]["completion_authorized"],
            "activation_authorized": plan["outputs"]["handoff"]["activation_authorized"],
        },
        "protected_surfaces": {
            "root_api_count": len(hive_mind_os.__all__),
            "package_api_count": len(package_system.__all__),
            "cli_parser_count": cli_inventory()["parser_count"],
            "definition_count": surface["observable_module_surface"]["definition_count"],
            "json_resource_count": len(tuple((repository / "src/hive_mind_os").rglob("*.json"))),
            "runtime_unclassified_count": surface["runtime_effects"][
                "unclassified_candidate_count"
            ],
            "store_digest": _digest_bytes(
                (repository / "src/hive_mind_os/foundation/store.py").read_bytes()
            ),
            "brain_digest": _digest_bytes(
                (repository / "src/hive_mind_os/foundation/brain.py").read_bytes()
            ),
            "explorer_successor_digest": _digest_bytes(
                (
                    repository
                    / "src/hive_mind_os/foundation/explorer_successor.py"
                ).read_bytes()
            ),
            "explorer_behavior_digest": _digest_bytes(
                (
                    repository
                    / "src/hive_mind_os/foundation/explorer_behavior.py"
                ).read_bytes()
            ),
        },
        "implementation": {
            path: _digest_bytes((repository / path).read_bytes())
            for path in implementation_paths
            if (repository / path).is_file()
        },
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
        "candidate_behavior_measured": False,
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
    inventory = build_phase5a_inventory(repository)
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
