from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import hive_mind_os
import hive_mind_os.package_system as package_system
from hive_mind_os.foundation.brain_contracts import PROJECTION_SCHEMA_NAMES
from hive_mind_os.foundation.cognitive_contracts import COGNITIVE_SCHEMA_NAMES
from hive_mind_os.foundation.cognitive_view_contracts import COGNITIVE_VIEW_SCHEMA_NAMES
from hive_mind_os.foundation.contracts import PHASE2_SCHEMA_NAMES
from hive_mind_os.foundation.explorer_contracts import (
    EXPLORER_SCHEMA_NAMES,
    validate_explorer_catalog,
)
from hive_mind_os.foundation.explorer_shadow import (
    CRITICAL_CLASSES,
    ContextRecord,
    ContextRequest,
    compile_shadow_skills,
    select_context,
)
from hive_mind_os.foundation.federation_contracts import FEDERATION_SCHEMA_NAMES
from hive_mind_os.foundation.public_memory_contracts import PUBLIC_MEMORY_SCHEMA_NAMES
from scripts.phase1_surface_inventory import (
    ARTIFACT_PATH,
    build_inventory,
    cli_inventory,
)
from scripts.phase3_federation_inventory import _canonical_json_file_digest

OUTPUT_PATH = Path("evidence/phase4/phase4_explorer_shadow_inventory.json")
BASE_HEAD = "2cbfe1d0e4dccd6f1758e5ddba10f799834bf857"


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _digest_json(value: Any) -> str:
    return _digest_bytes(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    )


def _fixture() -> dict[str, Any]:
    records = [
        ContextRecord(
            f"memory:{name}",
            "tenant:inventory",
            "repository:inventory",
            index,
            name,
            100,
            "private",
            "clear",
            "source",
            None,
            0,
            f"{name} evidence",
        )
        for index, name in enumerate(CRITICAL_CLASSES, 1)
    ]
    selection, _ = select_context(
        ContextRequest(
            "tenant:inventory",
            "repository:inventory",
            "run:inventory",
            "inventory fixture",
            len(CRITICAL_CLASSES),
            len(CRITICAL_CLASSES),
            100_000,
            1,
        ),
        records,
    )
    bundle = compile_shadow_skills()
    return {
        "selection_digest": selection.selection_digest,
        "skill_bundle_digest": bundle["bundle_digest"],
    }


def build_phase4_inventory(repository: Path) -> dict[str, Any]:
    baseline = json.loads((repository / ARTIFACT_PATH).read_text(encoding="utf-8"))
    current = build_inventory(repository)
    implementation_paths = (
        "scripts/phase3_projection_inventory.py",
        "scripts/phase4_explorer_shadow_inventory.py",
        "src/hive_mind_os/foundation/explorer_contracts.py",
        "src/hive_mind_os/foundation/explorer_shadow.py",
        "src/hive_mind_os/foundation/explorer_skill_resources.py",
        "src/hive_mind_os/foundation/store.py",
        "tests/test_phase4_explorer_shadow.py",
    )
    bundle = compile_shadow_skills()
    body = {
        "schema_version": 1,
        "phase": 4,
        "phase_item": "A",
        "base_head": BASE_HEAD,
        "activation": "inert-opt-in-shadow-only",
        "phase3_input": {
            "inventory_digest": _canonical_json_file_digest(
                repository
                / "evidence"
                / "phase3"
                / "phase3_federation_inventory.json"
            )
        },
        "generation_zero": {
            "root_api_count": len(hive_mind_os.__all__),
            "package_api_count": len(package_system.__all__),
            "cli_parser_count": cli_inventory()["parser_count"],
            "definition_count": current["observable_module_surface"]["definition_count"],
            "baseline_definition_count": baseline["observable_module_surface"][
                "definition_count"
            ],
        },
        "prior_contracts": {
            "phase2_count": len(PHASE2_SCHEMA_NAMES),
            "phase3_item1_count": len(PROJECTION_SCHEMA_NAMES),
            "phase3_item2_count": len(PUBLIC_MEMORY_SCHEMA_NAMES),
            "phase3_item3_count": len(COGNITIVE_SCHEMA_NAMES),
            "phase3_item4_count": len(COGNITIVE_VIEW_SCHEMA_NAMES),
            "phase3_item6_count": len(FEDERATION_SCHEMA_NAMES),
        },
        "explorer_contracts": {
            "count": len(EXPLORER_SCHEMA_NAMES),
            "names": list(EXPLORER_SCHEMA_NAMES),
            "catalog_valid": validate_explorer_catalog().valid,
        },
        "skill_bundle": {
            "count": len(bundle["skills"]),
            "digest": bundle["bundle_digest"],
            "activation": bundle["activation"],
            "authority": bundle["authority"],
        },
        "implementation": {
            path: _digest_bytes((repository / path).read_bytes())
            for path in implementation_paths
        },
        "deterministic_fixture": _fixture(),
        "external_dependencies_added": 0,
        "public_api_added": 0,
        "cli_added": 0,
        "provider_or_tool_calls": False,
        "production_activation": False,
        "generation_zero_activated": False,
    }
    return {**body, "inventory_digest": _digest_json(body)}


def main() -> int:
    repository = Path(__file__).parents[1]
    inventory = build_phase4_inventory(repository)
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
