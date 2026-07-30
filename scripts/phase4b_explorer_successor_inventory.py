from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import hive_mind_os
import hive_mind_os.package_system as package_system
from hive_mind_os.foundation.explorer_successor import compile_explorer_successor
from hive_mind_os.foundation.explorer_successor_contracts import (
    EXPLORER_SUCCESSOR_SCHEMA_NAME,
    validate_explorer_successor,
    validate_explorer_successor_catalog,
)
from hive_mind_os.foundation.generation import (
    compile_generation_zero_candidates,
    digest_bytes,
    verify_generated_candidates,
)
from scripts.phase1_surface_inventory import build_inventory, cli_inventory

OUTPUT_PATH = Path("evidence/phase4b/phase4b_explorer_successor_inventory.json")
BASE_HEAD = "316ee55da4ea7449bcdb934ab442ef0d95f54ba5"
PHASE4A_INVENTORY_DIGEST = (
    "sha256:6b5656608a5a53c104d4e9139f0ac485eebec6eab6db3d3350a4581b62816b36"
)


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _digest_json(value: Any) -> str:
    return _digest_bytes(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    )


def build_phase4b_inventory(repository: Path) -> dict[str, Any]:
    candidate = compile_explorer_successor()
    generated = compile_generation_zero_candidates()
    observed_generated = {
        path: (
            repository
            / "src"
            / "hive_mind_os"
            / "foundation"
            / "generated"
            / path
        ).read_bytes()
        for path in generated
    }
    surface = build_inventory(repository)
    implementation_paths = (
        "docs/architecture/ADR-029-EXPLORER-V2-SUCCESSOR-COMPOSITION.md",
        "docs/architecture/ADR_INDEX.md",
        "docs/architecture/PHASE4B_EXPLORER_SUCCESSOR_CONTRACT.md",
        "evidence/courts/phase4b-explorer-successor-court.md",
        "evidence/phase4b/PHASE4B_AUDIT_LEDGER.md",
        "evidence/phase4b/PHASE4B_DISSENT.md",
        "evidence/phase4b/PHASE4B_INSTALLED_WHEEL_RECEIPT.md",
        "evidence/sources/PHASE4B_EXPLORER_SUCCESSOR_SOURCE_REGISTER.md",
        "scripts/phase4b_explorer_successor_inventory.py",
        "src/hive_mind_os/foundation/explorer_successor.py",
        "src/hive_mind_os/foundation/explorer_successor_contracts.py",
        "tests/test_phase4b_explorer_successor.py",
    )
    body = {
        "schema_version": 1,
        "phase": 4,
        "phase_item": "B",
        "base_head": BASE_HEAD,
        "activation": "inert-definition-only",
        "phase4a_input": {"inventory_digest": PHASE4A_INVENTORY_DIGEST},
        "successor": {
            "schema": EXPLORER_SUCCESSOR_SCHEMA_NAME,
            "schema_catalog_valid": validate_explorer_successor_catalog().valid,
            "candidate_valid": validate_explorer_successor(candidate).valid,
            "agent_id": candidate["agent_id"],
            "definition_id": candidate["definition_id"],
            "content_digest": candidate["content_digest"],
            "layer_order": [layer["kind"] for layer in candidate["layers"]],
            "layer_digests": {
                layer["kind"]: layer["digest"] for layer in candidate["layers"]
            },
            "budgets": candidate["budgets"],
            "requested_capabilities": candidate["requested_capabilities"],
            "effective_capabilities": candidate["effective_capabilities"],
            "unsupported_capabilities": candidate["unsupported_capabilities"],
            "tool_refs": candidate["tool_refs"],
            "authority": candidate["authority"],
            "public": candidate["public"],
        },
        "generation_zero": {
            "generated_count": len(generated),
            "generated_verification_issues": list(
                verify_generated_candidates(observed_generated)
            ),
            "canonical_explorer_digest": digest_bytes(
                (
                    repository
                    / "src/hive_mind_os/foundation/canonical/agents/explorer.json"
                ).read_bytes()
            ),
            "generated_explorer_digest": digest_bytes(
                observed_generated["agents/explorer.json"]
            ),
            "generated_manifest_digest": digest_bytes(
                observed_generated["manifest.json"]
            ),
            "root_api_count": len(hive_mind_os.__all__),
            "package_api_count": len(package_system.__all__),
            "cli_parser_count": cli_inventory()["parser_count"],
            "definition_count": surface["observable_module_surface"][
                "definition_count"
            ],
            "source_json_resource_count": len(
                tuple((repository / "src/hive_mind_os").rglob("*.json"))
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
        "provider_or_tool_calls": False,
        "production_activation": False,
        "evaluation_complete": False,
        "value_claimed": False,
        "superiority_claimed": False,
    }
    return {**body, "inventory_digest": _digest_json(body)}


def main() -> int:
    repository = Path(__file__).parents[1]
    inventory = build_phase4b_inventory(repository)
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
