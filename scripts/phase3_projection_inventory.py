from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import hive_mind_os
import hive_mind_os.package_system as package_system
from hive_mind_os.foundation.authority import decide_foundation_write
from hive_mind_os.foundation.brain import project_memory_pack
from hive_mind_os.foundation.brain_contracts import (
    PROJECTION_SCHEMA_NAMES,
    validate_projection_catalog,
)
from hive_mind_os.foundation.canonical import digest
from hive_mind_os.foundation.store import FoundationStore
from hive_mind_os.models import Role
from hive_mind_os.policy import PolicyDecision
from scripts.phase1_surface_inventory import (
    ARTIFACT_PATH,
    build_inventory,
    cli_inventory,
)

OUTPUT_PATH = Path("evidence/phase3/phase3_projection_inventory.json")
BASE_HEAD = "94e67cde15fa8a75d92561384241f0419c9f589b"


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


def _authority(action: str, *, payload: dict[str, Any] | None = None):
    actor = "foundation-brain-projector-v1" if "projection" in action else "builder"
    decision = decide_foundation_write(
        role=Role.BUILDER,
        action=action,
        policy_decision=PolicyDecision(True, "phase3 inventory fixture"),
        lease_actions={action},
        adapter_actions={action},
        mission_risk_allowed=True,
        budget_available=True,
        tenant_id="tenant:inventory",
        repository_id="repository:inventory",
        actor_id=actor,
        decision_id=f"decision:{action}:{actor}",
        lease_id=f"lease:{action}:{actor}",
        public_release_decision_id=(
            "release:curator-inventory" if payload is not None else None
        ),
        public_release_decided_by=(
            "curator-inventory" if payload is not None else None
        ),
        public_release_subject_digest=digest(payload) if payload is not None else None,
    )
    if not decision.allowed:
        raise RuntimeError(f"inventory authority denied: {decision.reason}")
    return decision


def _fixture_receipt() -> dict[str, Any]:
    clock = iter(
        (
            "2026-07-29T00:00:00+00:00",
            "2026-07-29T00:00:01+00:00",
            "2026-07-29T00:00:02+00:00",
        )
    )
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        store_path = root / "private" / "foundation.sqlite3"
        store_path.parent.mkdir()
        repository = root / "repository"
        repository.mkdir()
        store = FoundationStore(store_path, clock=lambda: next(clock))
        identity = {
            "record_type": "repository-identity",
            "schema_version": 1,
            "tenant_id": "tenant:inventory",
            "repository_id": "repository:inventory",
            "project_lineage_id": "lineage:inventory",
            "instance_id": "instance:inventory",
            "remote_evidence_digest": digest("remote"),
            "controller_build_digest": digest("controller"),
            "self_host_depth": 0,
            "parent_run_id": None,
            "subject_commit": BASE_HEAD,
            "target_cutoff": BASE_HEAD,
        }
        store.register_repository(
            identity,
            authority=_authority("foundation.repository.register"),
        )
        content_digest = digest("safe-public-metadata")
        payload = {
            "record_type": "memory-record",
            "schema_version": 1,
            "memory_id": "memory:inventory",
            "memory_kind": "semantic",
            "repository_id": "repository:inventory",
            "tenant_id": "tenant:inventory",
            "mission_id": "mission:inventory",
            "run_id": "run:inventory",
            "step_id": "step:inventory",
            "actor_id": "builder",
            "payload_digest": content_digest,
            "previous_record_id": None,
            "supersedes_record_id": None,
            "observed_at": "2026-07-29T00:00:01+00:00",
            "recorded_at": "2026-07-29T00:00:02+00:00",
            "causation_id": None,
            "correlation_id": "correlation:inventory",
            "source_refs": ["source:inventory"],
            "claim_refs": ["claim:inventory"],
            "evidence_refs": ["evidence:inventory"],
            "court_refs": ["court:inventory"],
            "code_receipt_refs": [],
            "generation_refs": [],
            "status": "active",
            "confidence_ppm": 1_000_000,
            "freshness_expires_at": None,
            "contradiction_refs": [],
            "relation_refs": [],
            "owner_id": "builder",
            "sensitivity": "safe-public",
            "access_purpose": "inventory",
            "retention": "governed",
            "deletion_policy": "tombstone",
            "quarantine_state": "none",
            "appeal_state": "available",
            "content_digest": content_digest,
            "protected_content_ref": None,
            "retrieval_receipt": None,
        }
        store.append_record(
            authority=_authority("foundation.memory.write", payload=payload),
            foundation_action="foundation.memory.write",
            tenant_id="tenant:inventory",
            repository_id="repository:inventory",
            record_type="memory-record",
            schema_name="memory-record-v1",
            stream_id="memory:inventory",
            payload=payload,
            actor_id="builder",
            idempotency_key="memory:inventory",
            observed_at=payload["observed_at"],
            sensitivity="safe-public",
        )
        store.close()
        result = project_memory_pack(
            store_path,
            repository,
            tenant_id="tenant:inventory",
            repository_id="repository:inventory",
            authority=_authority("foundation.projection.write"),
        )
        manifest = json.loads(
            (repository / "hive-mind" / "generated" / "manifest.json").read_bytes()
        )
        return {
            "manifest_digest": result.manifest_digest,
            "tree_digest": result.tree_digest,
            "source_cursor": result.source_cursor,
            "projected_record_count": result.projected_record_count,
            "generated_paths": sorted(
                entry["path"] for entry in manifest["files"]
            )
            + ["generated/manifest.json"],
        }


def build_phase3_inventory(repository: Path) -> dict[str, Any]:
    baseline = json.loads((repository / ARTIFACT_PATH).read_text(encoding="utf-8"))
    phase2_path = repository / "evidence" / "phase2" / "phase2_foundation_inventory.json"
    phase2_bytes = phase2_path.read_bytes()
    current_frozen = build_inventory(repository)
    schema_root = (
        repository
        / "src"
        / "hive_mind_os"
        / "foundation"
        / "projection_schemas"
    )
    projection_resources = {
        path.name: _digest_bytes(path.read_bytes())
        for path in sorted(schema_root.glob("*.json"))
    }
    implementation_paths = (
        "src/hive_mind_os/foundation/authority.py",
        "src/hive_mind_os/foundation/brain.py",
        "src/hive_mind_os/foundation/brain_contracts.py",
        "src/hive_mind_os/foundation/contracts.py",
        "src/hive_mind_os/foundation/store.py",
    )
    body = {
        "schema_version": 1,
        "phase": 3,
        "phase_item": 1,
        "base_head": BASE_HEAD,
        "activation": "opt-in-module-command",
        "generation_zero": {
            "root_api_count": len(hive_mind_os.__all__),
            "package_api_count": len(package_system.__all__),
            "cli_parser_count": cli_inventory()["parser_count"],
            "definition_count": current_frozen["observable_module_surface"][
                "definition_count"
            ],
            "baseline_definition_count": baseline["observable_module_surface"][
                "definition_count"
            ],
            "baseline_inventory_digest": baseline["inventory_digest"],
        },
        "phase2_input": {
            "exact_head": BASE_HEAD,
            "historical_inventory_digest": _digest_bytes(phase2_bytes),
            "foundation_schema_count": 17,
            "generated_candidate_count": 9,
            "canonical_agent_count": 8,
        },
        "projection_contracts": {
            "count": len(PROJECTION_SCHEMA_NAMES),
            "names": list(PROJECTION_SCHEMA_NAMES),
            "catalog_valid": validate_projection_catalog().valid,
            "resource_digests": projection_resources,
            "resource_set_digest": _digest_json(projection_resources),
        },
        "implementation": {
            path: _digest_bytes((repository / path).read_bytes())
            for path in implementation_paths
        },
        "deterministic_fixture": _fixture_receipt(),
        "external_dependencies_added": 0,
        "obsidian_runtime_required": False,
    }
    return {**body, "inventory_digest": _digest_json(body)}


def main() -> int:
    repository = Path(__file__).parents[1]
    inventory = build_phase3_inventory(repository)
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
