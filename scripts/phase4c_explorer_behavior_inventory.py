from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import hive_mind_os
import hive_mind_os.package_system as package_system
from hive_mind_os.foundation.explorer_behavior import (
    compile_explorer_behavior_suite,
    compile_explorer_evaluation_subjects,
    score_explorer_behavior,
)
from hive_mind_os.foundation.explorer_behavior_contracts import (
    BEHAVIOR_FAMILIES,
    EXPLORER_BEHAVIOR_SCHEMA_NAMES,
    SAFETY_FAMILIES,
    validate_explorer_behavior_catalog,
)
from scripts.phase1_surface_inventory import build_inventory, cli_inventory

OUTPUT_PATH = Path("evidence/phase4c/phase4c_explorer_behavior_inventory.json")
BASE_HEAD = "55ec59828dcd999723627219210e5b224c65a36f"
PHASE4B_INVENTORY_DIGEST = (
    "sha256:8a8208c3e57f4e0f52b14954a3df36c7c9c02c4b9d39e677593dee94e73bde3c"
)


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _digest_json(value: Any) -> str:
    return _digest_bytes(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    )


def build_phase4c_inventory(repository: Path) -> dict[str, Any]:
    suite = compile_explorer_behavior_suite()
    subjects = compile_explorer_evaluation_subjects()
    not_run = score_explorer_behavior(
        [],
        evaluator_id="evaluator:inventory",
        budget_manifest_digest=_digest_json({"state": "not-issued"}),
        measurement_id="explorer-development-inventory:not-run",
    )
    surface = build_inventory(repository)
    implementation_paths = (
        "docs/architecture/ADR-030-EXPLORER-DEVELOPMENT-EVALUATION-SUBSTRATE.md",
        "docs/architecture/ADR_INDEX.md",
        "evidence/courts/phase4c-explorer-behavior-court.md",
        "evidence/phase4c/PHASE4C_AUDIT_AND_DISSENT.md",
        "evidence/sources/PHASE4C_EXPLORER_BEHAVIOR_SOURCE_REGISTER.md",
        "scripts/phase4c_explorer_behavior_inventory.py",
        "src/hive_mind_os/foundation/explorer_behavior.py",
        "src/hive_mind_os/foundation/explorer_behavior_contracts.py",
        "tests/test_phase4c_explorer_behavior.py",
    )
    body = {
        "schema_version": 1,
        "phase": 4,
        "phase_item": "C",
        "base_head": BASE_HEAD,
        "phase4b_input": {"inventory_digest": PHASE4B_INVENTORY_DIGEST},
        "scope": "development-visible-evaluation-substrate",
        "suite": {
            "suite_id": suite["suite_id"],
            "content_digest": suite["content_digest"],
            "visibility": suite["visibility"],
            "holdout": suite["holdout"],
            "comparison": suite["comparison"],
            "promotion": suite["promotion"],
            "families": list(BEHAVIOR_FAMILIES),
            "safety_families": sorted(SAFETY_FAMILIES),
            "case_count": len(suite["cases"]),
            "metric_weight_total_ppm": sum(
                case["metric_weight_ppm"] for case in suite["cases"]
            ),
        },
        "subjects": {
            name: {
                "subject_id": subject["subject_id"],
                "content_digest": subject["content_digest"],
                "execution_state": subject["execution_state"],
                "executable": subject["executable"],
                "authority": subject["authority"],
            }
            for name, subject in subjects.items()
        },
        "empty_observation_receipt": {
            "status": not_run["status"],
            "comparison_status": not_run["comparison_status"],
            "metric_statuses": sorted(
                {metric["status"] for metric in not_run["metrics"]}
            ),
            "promotion_authorized": not_run["promotion_authorized"],
            "activation_authorized": not_run["activation_authorized"],
            "content_digest": not_run["content_digest"],
        },
        "contracts": {
            "names": list(EXPLORER_BEHAVIOR_SCHEMA_NAMES),
            "catalog_valid": validate_explorer_behavior_catalog().valid,
        },
        "protected_surfaces": {
            "root_api_count": len(hive_mind_os.__all__),
            "package_api_count": len(package_system.__all__),
            "cli_parser_count": cli_inventory()["parser_count"],
            "definition_count": surface["observable_module_surface"]["definition_count"],
            "json_resource_count": len(
                tuple((repository / "src/hive_mind_os").rglob("*.json"))
            ),
            "runtime_unclassified_count": surface["runtime_effects"][
                "unclassified_candidate_count"
            ],
            "benchmark_harness_digest": _digest_bytes(
                (repository / "src/hive_mind_os/benchmark_harness.py").read_bytes()
            ),
            "experiment_runner_digest": _digest_bytes(
                (repository / "src/hive_mind_os/experiment_runner.py").read_bytes()
            ),
        },
        "implementation": {
            path: _digest_bytes((repository / path).read_bytes())
            for path in implementation_paths
        },
        "external_dependencies_added": 0,
        "public_api_added": 0,
        "cli_added": 0,
        "runtime_binding_added": False,
        "store_or_migration_added": False,
        "provider_or_tool_calls": False,
        "held_out_claimed": False,
        "candidate_behavior_measured": False,
        "comparison_complete": False,
        "value_claimed": False,
        "promotion_authorized": False,
        "activation_authorized": False,
        "superiority_claimed": False,
    }
    return {**body, "inventory_digest": _digest_json(body)}


def main() -> int:
    repository = Path(__file__).parents[1]
    inventory = build_phase4c_inventory(repository)
    destination = repository / OUTPUT_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
