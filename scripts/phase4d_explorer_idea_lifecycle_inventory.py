from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import hive_mind_os
import hive_mind_os.package_system as package_system
from hive_mind_os.foundation.canonical import digest
from hive_mind_os.foundation.contracts import validate_foundation
from hive_mind_os.foundation.explorer_idea_lifecycle import (
    LIFECYCLE_STAGES,
    compile_explorer_idea_lifecycle_event,
    semantic_relationship_reference,
)
from scripts.phase1_surface_inventory import build_inventory, cli_inventory

OUTPUT_PATH = Path("evidence/phase4d/phase4d_explorer_idea_lifecycle_inventory.json")
BASE_HEAD = "59df5f5f2d0af45f403f74dac9781d2664f227cd"
PHASE4C_INVENTORY_DIGEST = (
    "sha256:86e1ec6bf309ce98fb12aa38c3a78f878e14b1cf786810166538a4e3bed22d1e"
)


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _digest_json(value: Any) -> str:
    return _digest_bytes(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    )


def build_phase4d_inventory(repository: Path) -> dict[str, Any]:
    relationship = semantic_relationship_reference(
        tenant_id="tenant:inventory",
        repository_id="repository:inventory",
        source_record_id="record:encounter",
        target_record_id="record:opportunity",
        relationship="new",
        evidence_digest=digest("inventory evidence"),
    )
    prepared = compile_explorer_idea_lifecycle_event(
        lifecycle_id="idea:inventory",
        event_id="idea:inventory:encounter",
        stage="encounter",
        tenant_id="tenant:inventory",
        repository_id="repository:inventory",
        mission_id="mission:inventory",
        run_id="run:inventory",
        actor_id="explorer",
        owner_id="orchestrator",
        observed_at="2026-07-30T00:00:00+00:00",
        recorded_at="2026-07-30T00:00:01+00:00",
        subject_ref={
            "ref": "generation-zero:explorer",
            "digest": digest("generation-zero"),
        },
        stage_reference={
            "ref": "observation:inventory",
            "digest": digest("observation"),
        },
        encounter_record_id="record:encounter",
    )
    surface = build_inventory(repository)
    implementation_paths = (
        "docs/architecture/ADR-031-EXPLORER-IDEA-LIFECYCLE-REFERENCE-EVENTS.md",
        "docs/architecture/ADR_INDEX.md",
        "evidence/courts/phase4d-explorer-idea-lifecycle-court.md",
        "evidence/phase4d/PHASE4D_AUDIT_AND_DISSENT.md",
        "evidence/sources/PHASE4D_EXPLORER_IDEA_LIFECYCLE_SOURCE_REGISTER.md",
        "scripts/phase4d_explorer_idea_lifecycle_inventory.py",
        "src/hive_mind_os/foundation/explorer_idea_lifecycle.py",
        "tests/test_phase4d_explorer_idea_lifecycle.py",
    )
    body = {
        "schema_version": 1,
        "phase": 4,
        "phase_item": "D",
        "base_head": BASE_HEAD,
        "phase4c_input": {"inventory_digest": PHASE4C_INVENTORY_DIGEST},
        "scope": "append-only-reference-events",
        "stages": list(LIFECYCLE_STAGES),
        "sample_event": {
            "receipt_digest": prepared["receipt"]["content_digest"],
            "memory_contract_valid": validate_foundation(
                "memory-record-v1", prepared["memory"]
            ).valid,
            "reference_status": prepared["receipt"]["reference_status"],
            "remaining_stage_status": prepared["receipt"][
                "remaining_stage_status"
            ],
            "sensitivity": prepared["receipt"]["sensitivity"],
            "comparison_status": prepared["receipt"]["comparison_status"],
            "lifecycle_complete_claimed": prepared["receipt"][
                "lifecycle_complete_claimed"
            ],
            "value_claimed": prepared["receipt"]["value_claimed"],
            "promotion_authorized": prepared["receipt"]["promotion_authorized"],
            "activation_authorized": prepared["receipt"]["activation_authorized"],
        },
        "sample_relationship": relationship,
        "protected_surfaces": {
            "root_api_count": len(hive_mind_os.__all__),
            "package_api_count": len(package_system.__all__),
            "cli_parser_count": cli_inventory()["parser_count"],
            "definition_count": surface["observable_module_surface"][
                "definition_count"
            ],
            "json_resource_count": len(
                tuple((repository / "src/hive_mind_os").rglob("*.json"))
            ),
            "runtime_unclassified_count": surface["runtime_effects"][
                "unclassified_candidate_count"
            ],
            "opportunity_ledger_digest": _digest_bytes(
                (
                    repository / "src/hive_mind_os/foundation/opportunities.py"
                ).read_bytes()
            ),
            "store_digest": _digest_bytes(
                (repository / "src/hive_mind_os/foundation/store.py").read_bytes()
            ),
            "cognitive_projector_digest": _digest_bytes(
                (repository / "src/hive_mind_os/foundation/cognitive.py").read_bytes()
            ),
            "cognitive_views_digest": _digest_bytes(
                (
                    repository / "src/hive_mind_os/foundation/cognitive_views.py"
                ).read_bytes()
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
        "projector_changed": False,
        "view_mapping_changed": False,
        "automatic_public_release": False,
        "backfill_claimed": False,
        "artifact_truth_claimed": False,
        "lifecycle_complete_claimed": False,
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
    inventory = build_phase4d_inventory(repository)
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
