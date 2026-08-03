from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from hive_mind_os.foundation.full_role_output_contracts import (
    OUTPUT_FIELDS_BY_ROLE,
    validate_full_role_envelope,
)
from hive_mind_os.foundation.full_role_outputs import (
    compile_integrator_full_outputs,
    compile_optimizer_full_outputs,
    compile_steward_full_outputs,
)

OUTPUT_PATH = Path("evidence/phase5p/phase5_full_role_output_inventory.json")
BASE_HEAD = "b82c1a2b9cb83e5f4207387ae279f0720c66fb00"
IMPLEMENTATION_PATHS = (
    "src/hive_mind_os/foundation/full_role_output_contracts.py",
    "src/hive_mind_os/foundation/full_role_outputs.py",
    "scripts/phase5e_to_k_inventory.py",
    "scripts/verify_phase5e_to_k_installed_wheel.py",
    "scripts/phase5p_full_role_output_inventory.py",
    "tests/test_phase5p_full_role_outputs.py",
    "tests/test_phase5p_full_role_output_inventory.py",
)


def _digest_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def build_inventory(repository: Path) -> dict[str, Any]:
    compilers = {
        "integrator": compile_integrator_full_outputs,
        "steward": compile_steward_full_outputs,
        "optimizer": compile_optimizer_full_outputs,
    }
    roles: dict[str, Any] = {}
    for role, compiler in compilers.items():
        envelope = compiler()
        validate_full_role_envelope(envelope)
        roles[role] = {
            "schema_version": envelope["schema_version"],
            "scope_digest": envelope["scope_digest"],
            "envelope_digest": envelope["envelope_digest"],
            "output_fields": list(OUTPUT_FIELDS_BY_ROLE[role]),
            "output_schema_versions": {
                field: envelope["outputs"][field]["schema_version"]
                for field in OUTPUT_FIELDS_BY_ROLE[role]
            },
            "output_digests": dict(envelope["output_digests"]),
            "claims": dict(envelope["claims"]),
        }
    missing = [
        path for path in IMPLEMENTATION_PATHS if not (repository / path).is_file()
    ]
    if missing:
        raise RuntimeError(f"Phase 5P inventory paths are missing: {missing}")
    body = {
        "schema_version": 1,
        "record_type": "phase5p-full-role-output-inventory",
        "base_head": BASE_HEAD,
        "roles": roles,
        "role_count": len(roles),
        "output_count": sum(len(fields) for fields in OUTPUT_FIELDS_BY_ROLE.values()),
        "implementation": {
            path: _digest_bytes((repository / path).read_bytes())
            for path in IMPLEMENTATION_PATHS
        },
        "external_sources_added": 0,
        "external_dependencies_added": 0,
        "runtime_binding_added": False,
        "authority_added": False,
        "execution_performed": False,
        "authenticated_independence_claimed": False,
        "release_ready": False,
        "production_ready": False,
        "deployment_authorized": False,
        "promotion_authorized": False,
        "superiority_claimed": False,
    }
    return {**body, "inventory_digest": _digest_json(body)}


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    inventory = build_inventory(repository)
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
