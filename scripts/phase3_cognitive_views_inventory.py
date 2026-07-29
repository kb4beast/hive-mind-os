from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import hive_mind_os
import hive_mind_os.package_system as package_system
import scripts.phase3_cognitive_notes_inventory as item3_inventory
from hive_mind_os.foundation.brain_contracts import PROJECTION_SCHEMA_NAMES
from hive_mind_os.foundation.cognitive import (
    MANAGED_NAMESPACE as COGNITIVE_NAMESPACE,
)
from hive_mind_os.foundation.cognitive import (
    project_cognitive_notes,
)
from hive_mind_os.foundation.cognitive_contracts import COGNITIVE_SCHEMA_NAMES
from hive_mind_os.foundation.cognitive_view_contracts import (
    COGNITIVE_VIEW_SCHEMA_NAMES,
    validate_cognitive_view_catalog,
)
from hive_mind_os.foundation.cognitive_views import (
    MANAGED_NAMESPACE,
    SOURCE_NAMESPACE,
    project_cognitive_views,
)
from hive_mind_os.foundation.contracts import PHASE2_SCHEMA_NAMES
from hive_mind_os.foundation.public_memory import (
    PUBLIC_MEMORY_RELEASE_ACTION,
    PUBLIC_MEMORY_RELEASER,
    materialize_public_memory,
)
from hive_mind_os.foundation.public_memory_contracts import PUBLIC_MEMORY_SCHEMA_NAMES
from hive_mind_os.foundation.store import FoundationStore
from scripts.phase1_surface_inventory import (
    ARTIFACT_PATH,
    build_inventory,
    cli_inventory,
)

OUTPUT_PATH = Path("evidence/phase3/phase3_cognitive_views_inventory.json")
BASE_HEAD = "7e26a56eab5fe79f075cccc57a6ff0a01fb9ef9a"


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _digest_json(value: Any) -> str:
    return _digest_bytes(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _fixture() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        private = root / "private"
        private.mkdir()
        public = root / "public"
        public.mkdir()
        repository = root / "repository"
        repository.mkdir()
        source = private / "foundation.sqlite3"
        public_store = public / "released.sqlite3"

        def fixed_clock() -> str:
            return "2026-07-29T20:00:02+00:00"

        store = FoundationStore(source, clock=fixed_clock)
        store.register_repository(
            item3_inventory._identity(),
            authority=item3_inventory._authority("foundation.repository.register"),
        )
        for index, memory_kind in enumerate(
            ("opportunity", "semantic", "decision", "episodic", "social", "resource")
        ):
            payload = item3_inventory._memory(f"memory:item4:{index}", memory_kind)
            store.append_record(
                authority=item3_inventory._authority(
                    "foundation.memory.write",
                    actor_id=payload["actor_id"],
                    public_payload=payload,
                ),
                foundation_action="foundation.memory.write",
                tenant_id=item3_inventory.TENANT_ID,
                repository_id=item3_inventory.REPOSITORY_ID,
                record_type="memory-record",
                schema_name="memory-record-v1",
                stream_id=f"item4:{index}",
                payload=payload,
                actor_id=payload["actor_id"],
                idempotency_key=f"item4:{index}",
                observed_at=payload["observed_at"],
                sensitivity="safe-public",
            )
        store.close()
        materialize_public_memory(
            source,
            public_store,
            repository,
            root / "protected-release",
            tenant_id=item3_inventory.TENANT_ID,
            repository_id=item3_inventory.REPOSITORY_ID,
            authority=item3_inventory._authority(
                PUBLIC_MEMORY_RELEASE_ACTION,
                actor_id=PUBLIC_MEMORY_RELEASER,
            ),
            clock=fixed_clock,
        )
        source.rename(source.with_suffix(".unavailable"))
        cognitive_state = root / "protected-cognitive"
        project_cognitive_notes(
            public_store,
            repository,
            cognitive_state,
            tenant_id=item3_inventory.TENANT_ID,
            repository_id=item3_inventory.REPOSITORY_ID,
            authority=item3_inventory._authority(
                "foundation.projection.write",
                actor_id="foundation-cognitive-projector-v1",
            ),
        )
        cognitive_before = _tree(repository / COGNITIVE_NAMESPACE)
        result = project_cognitive_views(
            repository,
            cognitive_state,
            root / "protected-views",
            tenant_id=item3_inventory.TENANT_ID,
            repository_id=item3_inventory.REPOSITORY_ID,
            authority=item3_inventory._authority(
                "foundation.projection.write",
                actor_id="foundation-cognitive-view-projector-v1",
            ),
            clock=fixed_clock,
        )
        view_root = repository / MANAGED_NAMESPACE
        view_tree = _tree(view_root)
        manifest = json.loads(view_tree["manifest.json"])
        canvas = json.loads(view_tree["canvases/war-room.canvas"])
        stable_files = {
            path: _digest_bytes(content)
            for path, content in sorted(view_tree.items())
            if path != "manifest.json"
        }
        return {
            "status": result.status,
            "manifest_digest": result.manifest_digest,
            "tree_digest": result.tree_digest,
            "source_cursor": result.source_cursor,
            "source_manifest_digest": result.source_manifest_digest,
            "source_namespace": SOURCE_NAMESPACE,
            "generated_namespace": MANAGED_NAMESPACE,
            "generated_paths": sorted(view_tree),
            "stable_artifact_digests": stable_files,
            "cognitive_source_tree_unchanged": (
                _tree(repository / COGNITIVE_NAMESPACE) == cognitive_before
            ),
            "base_count": manifest["base_count"],
            "canvas_count": manifest["canvas_count"],
            "canvas_node_count": len(canvas["nodes"]),
            "canvas_edge_count": len(canvas["edges"]),
            "canvas_node_ids": [node["id"] for node in canvas["nodes"]],
            "supported_capabilities": manifest["supported_capabilities"],
            "unavailable_capabilities": manifest["unavailable_capabilities"],
            "private_foundation_available_during_view_projection": False,
            "public_store_read_by_view_projection": False,
        }


def build_phase3_item4_inventory(repository: Path) -> dict[str, Any]:
    baseline = json.loads((repository / ARTIFACT_PATH).read_text(encoding="utf-8"))
    frozen = build_inventory(repository)
    prior_inventory = (
        repository / "evidence" / "phase3" / "phase3_cognitive_notes_inventory.json"
    )
    schema_root = repository / "src" / "hive_mind_os" / "foundation" / "generated"
    resources = {
        path.name: _digest_bytes(path.read_bytes())
        for path in sorted(schema_root.glob("*.json"))
        if path.name.startswith("cognitive-view-")
    }
    implementation_paths = (
        "pyproject.toml",
        "src/hive_mind_os/foundation/cognitive_view_contracts.py",
        "src/hive_mind_os/foundation/cognitive_views.py",
    )
    body = {
        "schema_version": 1,
        "phase": 3,
        "phase_item": 4,
        "base_head": BASE_HEAD,
        "activation": "opt-in-item3-derived-module-command",
        "generation_zero": {
            "root_api_count": len(hive_mind_os.__all__),
            "package_api_count": len(package_system.__all__),
            "cli_parser_count": cli_inventory()["parser_count"],
            "definition_count": frozen["observable_module_surface"]["definition_count"],
            "baseline_definition_count": baseline["observable_module_surface"][
                "definition_count"
            ],
        },
        "phase3_item3_input": {
            "historical_inventory_digest": _digest_bytes(prior_inventory.read_bytes()),
        },
        "prior_contracts": {
            "phase2_count": len(PHASE2_SCHEMA_NAMES),
            "item1_count": len(PROJECTION_SCHEMA_NAMES),
            "item2_count": len(PUBLIC_MEMORY_SCHEMA_NAMES),
            "item3_count": len(COGNITIVE_SCHEMA_NAMES),
        },
        "cognitive_view_contracts": {
            "count": len(COGNITIVE_VIEW_SCHEMA_NAMES),
            "names": list(COGNITIVE_VIEW_SCHEMA_NAMES),
            "catalog_valid": validate_cognitive_view_catalog().valid,
            "resource_digests": resources,
            "resource_set_digest": _digest_json(resources),
        },
        "implementation": {
            path: _digest_bytes((repository / path).read_bytes())
            for path in implementation_paths
        },
        "official_source_pins": {
            "obsidian_help_commit": "29e89022c6aeb0a9e9971b6f0c98733dbc2eb716",
            "json_canvas_commit": "456f843cb293df4f4ab1763e22ccb46a80b307c8",
            "json_canvas_version": "1.0",
            "json_canvas_license": "MIT",
            "bases_license": "NOASSERTION",
        },
        "deterministic_fixture": _fixture(),
        "external_dependencies_added": 0,
        "obsidian_runtime_required": False,
        "automatic_refresh_started": False,
        "federation_started": False,
        "generation_zero_activated": False,
    }
    return {**body, "inventory_digest": _digest_json(body)}


def main() -> int:
    repository = Path(__file__).parents[1]
    inventory = build_phase3_item4_inventory(repository)
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
