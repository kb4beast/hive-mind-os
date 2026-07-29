from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import hive_mind_os
import hive_mind_os.package_system as package_system
from hive_mind_os.foundation.contracts import (
    PHASE2_SCHEMA_NAMES,
    validate_foundation_catalog,
)
from hive_mind_os.foundation.generation import compile_generation_zero_candidates
from hive_mind_os.foundation.store import FOUNDATION_SCHEMA_VERSION, FoundationStore
from scripts.phase1_surface_inventory import (
    ARTIFACT_PATH,
    build_inventory,
    cli_inventory,
)

OUTPUT_PATH = Path("evidence/phase2/phase2_foundation_inventory.json")


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _digest_json(value: Any) -> str:
    return _digest_bytes(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    )


def build_phase2_inventory(repository: Path) -> dict[str, Any]:
    current = build_inventory(repository, include_additive=True)
    baseline = json.loads((repository / ARTIFACT_PATH).read_text(encoding="utf-8"))
    schema_root = repository / "src" / "hive_mind_os" / "foundation" / "schemas"
    schema_resources = {
        path.name: _digest_bytes(path.read_bytes())
        for path in sorted(schema_root.glob("*.json"))
    }
    canonical_root = (
        repository / "src" / "hive_mind_os" / "foundation" / "canonical" / "agents"
    )
    canonical_resources = {
        path.name: _digest_bytes(path.read_bytes())
        for path in sorted(canonical_root.glob("*.json"))
    }
    generated = compile_generation_zero_candidates()
    with tempfile.TemporaryDirectory() as temporary:
        store = FoundationStore(Path(temporary) / "foundation.sqlite3")
        try:
            objects = [
                list(row)
                for row in store._connection.execute(
                    "SELECT type,name,sql FROM sqlite_master "
                    "WHERE type IN ('table','index','trigger') ORDER BY type,name"
                )
                if row[1] != "sqlite_sequence"
            ]
            tables = [
                row[0]
                for row in store._connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            ]
            triggers = [
                row[0]
                for row in store._connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name"
                )
            ]
            journal_mode = store.journal_mode()
        finally:
            store.close()
    body = {
        "schema_version": 1,
        "phase": 2,
        "base_head": "3298078c41ce69103eb2bdce61960a69dc6aab93",
        "activation": "inert-opt-in",
        "generation_zero": {
            "root_api_count": len(hive_mind_os.__all__),
            "package_api_count": len(package_system.__all__),
            "cli_parser_count": cli_inventory()["parser_count"],
            "baseline_inventory_digest": baseline["inventory_digest"],
            "baseline_module_definition_count": baseline[
                "observable_module_surface"
            ]["definition_count"],
            "baseline_event_sink_count": baseline["runtime_effects"][
                "event_sink_count"
            ],
            "legacy_schema_count": 20,
            "legacy_package_resource_count": 48,
            "legacy_total_resource_count": 68,
        },
        "additive_surface": {
            "current_module_definition_count": current[
                "observable_module_surface"
            ]["definition_count"],
            "current_event_sink_count": current["runtime_effects"][
                "event_sink_count"
            ],
            "unclassified_candidate_count": current["runtime_effects"][
                "unclassified_candidate_count"
            ],
        },
        "foundation_contracts": {
            "count": len(PHASE2_SCHEMA_NAMES),
            "names": list(PHASE2_SCHEMA_NAMES),
            "catalog_valid": validate_foundation_catalog().valid,
            "resource_digests": schema_resources,
            "resource_set_digest": _digest_json(schema_resources),
        },
        "generated_candidates": {
            "count": len(generated),
            "resource_digests": {
                path: _digest_bytes(content)
                for path, content in sorted(generated.items())
            },
        },
        "canonical_agent_sources": {
            "count": len(canonical_resources),
            "resource_digests": canonical_resources,
            "resource_set_digest": _digest_json(canonical_resources),
        },
        "foundation_store": {
            "schema_version": FOUNDATION_SCHEMA_VERSION,
            "journal_mode": journal_mode,
            "tables": tables,
            "triggers": triggers,
            "schema_digest": _digest_json(objects),
        },
        "provider_fixtures": {
            path.name: _digest_bytes(path.read_bytes())
            for path in sorted((repository / "tests" / "fixtures" / "phase2").glob("*.json"))
        },
    }
    return {**body, "inventory_digest": _digest_json(body)}


def main() -> int:
    repository = Path(__file__).parents[1]
    inventory = build_phase2_inventory(repository)
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
