from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import hive_mind_os
import hive_mind_os.package_system as package_system
from hive_mind_os.foundation.authority import decide_foundation_write
from hive_mind_os.foundation.brain_contracts import PROJECTION_SCHEMA_NAMES
from hive_mind_os.foundation.canonical import digest
from hive_mind_os.foundation.cognitive import (
    MANAGED_NAMESPACE,
    project_cognitive_notes,
)
from hive_mind_os.foundation.cognitive_contracts import (
    COGNITIVE_SCHEMA_NAMES,
    validate_cognitive_catalog,
)
from hive_mind_os.foundation.contracts import PHASE2_SCHEMA_NAMES
from hive_mind_os.foundation.public_memory import (
    PUBLIC_MEMORY_RELEASE_ACTION,
    PUBLIC_MEMORY_RELEASER,
    PublicMemoryReleaseStore,
    materialize_public_memory,
    read_public_memory_release_snapshot,
)
from hive_mind_os.foundation.public_memory_contracts import PUBLIC_MEMORY_SCHEMA_NAMES
from hive_mind_os.foundation.store import FoundationStore
from hive_mind_os.models import Role
from hive_mind_os.policy import PolicyDecision
from scripts.phase1_surface_inventory import (
    ARTIFACT_PATH,
    build_inventory,
    cli_inventory,
)

OUTPUT_PATH = Path("evidence/phase3/phase3_cognitive_notes_inventory.json")
BASE_HEAD = "40a508b6b1bfb4a8624cf1ef8169384d32a39d44"
TENANT_ID = "tenant:item3-inventory"
REPOSITORY_ID = "repository:item3-inventory"


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


def _authority(
    action: str,
    *,
    actor_id: str = "builder",
    public_payload: dict[str, Any] | None = None,
):
    decision = decide_foundation_write(
        role=Role.BUILDER,
        action=action,
        policy_decision=PolicyDecision(True, "item-3 inventory fixture"),
        lease_actions={action},
        adapter_actions={action},
        mission_risk_allowed=True,
        budget_available=True,
        tenant_id=TENANT_ID,
        repository_id=REPOSITORY_ID,
        actor_id=actor_id,
        decision_id=f"decision:{action}:{actor_id}",
        lease_id=f"lease:{action}:{actor_id}",
        public_release_decision_id=(
            "release:item3-inventory-curator"
            if public_payload is not None
            else None
        ),
        public_release_decided_by=(
            "curator:item3-inventory" if public_payload is not None else None
        ),
        public_release_subject_digest=(
            digest(public_payload) if public_payload is not None else None
        ),
    )
    if not decision.allowed:
        raise RuntimeError(f"inventory authority denied: {decision.reason}")
    return decision


def _identity() -> dict[str, Any]:
    return {
        "record_type": "repository-identity",
        "schema_version": 1,
        "tenant_id": TENANT_ID,
        "repository_id": REPOSITORY_ID,
        "project_lineage_id": "lineage:item3-inventory",
        "instance_id": "instance:item3-inventory",
        "remote_evidence_digest": digest("remote"),
        "controller_build_digest": digest("controller"),
        "self_host_depth": 0,
        "parent_run_id": None,
        "subject_commit": BASE_HEAD,
        "target_cutoff": BASE_HEAD,
    }


def _memory(memory_id: str, memory_kind: str) -> dict[str, Any]:
    content_digest = digest({"memory_id": memory_id, "memory_kind": memory_kind})
    return {
        "record_type": "memory-record",
        "schema_version": 1,
        "memory_id": memory_id,
        "memory_kind": memory_kind,
        "repository_id": REPOSITORY_ID,
        "tenant_id": TENANT_ID,
        "mission_id": "mission:item3-inventory",
        "run_id": "run:item3-inventory",
        "step_id": "step:item3-inventory",
        "actor_id": "builder:item3-inventory",
        "payload_digest": content_digest,
        "previous_record_id": None,
        "supersedes_record_id": None,
        "observed_at": "2026-07-29T17:00:00+00:00",
        "recorded_at": "2026-07-29T17:00:01+00:00",
        "causation_id": None,
        "correlation_id": "correlation:item3-inventory",
        "source_refs": ["source:item3-inventory"],
        "claim_refs": ["COG-003"],
        "evidence_refs": ["evidence:item3-inventory"],
        "court_refs": ["P3-COGNITIVE-NOTES-003"],
        "code_receipt_refs": [],
        "generation_refs": [],
        "status": "active",
        "confidence_ppm": 1_000_000,
        "freshness_expires_at": None,
        "contradiction_refs": [],
        "relation_refs": [],
        "owner_id": "builder:item3-inventory",
        "sensitivity": "safe-public",
        "access_purpose": "item3-inventory",
        "retention": "governed",
        "deletion_policy": "tombstone",
        "quarantine_state": "none",
        "appeal_state": "available",
        "content_digest": content_digest,
        "protected_content_ref": None,
        "retrieval_receipt": None,
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
            return "2026-07-29T17:00:02+00:00"

        store = FoundationStore(source, clock=fixed_clock)
        store.register_repository(
            _identity(),
            authority=_authority("foundation.repository.register"),
        )
        for index, memory_kind in enumerate(
            ("opportunity", "semantic", "decision", "episodic", "social", "resource")
        ):
            payload = _memory(f"memory:item3:{index}", memory_kind)
            store.append_record(
                authority=_authority(
                    "foundation.memory.write",
                    actor_id=payload["actor_id"],
                    public_payload=payload,
                ),
                foundation_action="foundation.memory.write",
                tenant_id=TENANT_ID,
                repository_id=REPOSITORY_ID,
                record_type="memory-record",
                schema_name="memory-record-v1",
                stream_id=f"item3:{index}",
                payload=payload,
                actor_id=payload["actor_id"],
                idempotency_key=f"item3:{index}",
                observed_at=payload["observed_at"],
                sensitivity="safe-public",
            )
        store.close()
        materialize_public_memory(
            source,
            public_store,
            repository,
            root / "protected-release",
            tenant_id=TENANT_ID,
            repository_id=REPOSITORY_ID,
            authority=_authority(
                PUBLIC_MEMORY_RELEASE_ACTION,
                actor_id=PUBLIC_MEMORY_RELEASER,
            ),
            clock=fixed_clock,
        )
        source.rename(source.with_suffix(".unavailable"))
        result = project_cognitive_notes(
            public_store,
            repository,
            root / "protected-cognitive",
            tenant_id=TENANT_ID,
            repository_id=REPOSITORY_ID,
            authority=_authority(
                "foundation.projection.write",
                actor_id="foundation-cognitive-projector-v1",
            ),
        )
        namespace = repository / MANAGED_NAMESPACE
        manifest = json.loads((namespace / "manifest.json").read_bytes())
        snapshot = read_public_memory_release_snapshot(
            public_store,
            tenant_id=TENANT_ID,
            repository_id=REPOSITORY_ID,
        )
        if not isinstance(snapshot.repository_identity_digest, str):
            raise AssertionError("fixture repository identity digest is unavailable")
        release_store = PublicMemoryReleaseStore(
            public_store,
            tenant_id=TENANT_ID,
            repository_id=REPOSITORY_ID,
            repository_identity_digest=snapshot.repository_identity_digest,
            source_foundation_schema_version=snapshot.schema_version,
            source_foundation_schema_digest=snapshot.schema_digest,
        )
        try:
            public_logical_digest = release_store.logical_digest()
        finally:
            release_store.close()
        return {
            "status": result.status,
            "tree_digest": result.tree_digest,
            "manifest_digest": result.manifest_digest,
            "source_cursor": result.source_cursor,
            "public_store_logical_digest": public_logical_digest,
            "note_counts": manifest["note_counts"],
            "note_ids": sorted(entry["note_id"] for entry in manifest["files"]),
            "generated_paths": sorted(
                [entry["path"] for entry in manifest["files"]] + ["manifest.json"]
            ),
            "private_foundation_available_during_projection": False,
            "private_projection_state_in_repository": False,
        }


def build_phase3_item3_inventory(repository: Path) -> dict[str, Any]:
    baseline = json.loads((repository / ARTIFACT_PATH).read_text(encoding="utf-8"))
    frozen = build_inventory(repository)
    item2_path = (
        repository
        / "evidence"
        / "phase3"
        / "phase3_memory_separation_inventory.json"
    )
    schema_root = (
        repository / "src" / "hive_mind_os" / "foundation" / "cognitive_schemas"
    )
    cognitive_resources = {
        path.name: _digest_bytes(path.read_bytes())
        for path in sorted(schema_root.glob("*.json"))
    }
    prior_resources = {}
    for label, directory in (
        ("phase2", "schemas"),
        ("item1", "projection_schemas"),
        ("item2", "public_memory_schemas"),
    ):
        root = repository / "src" / "hive_mind_os" / "foundation" / directory
        prior_resources[label] = {
            path.name: _digest_bytes(path.read_bytes())
            for path in sorted(root.glob("*.json"))
        }
    implementation_paths = (
        "pyproject.toml",
        "src/hive_mind_os/foundation/cognitive.py",
        "src/hive_mind_os/foundation/cognitive_contracts.py",
    )
    body = {
        "schema_version": 1,
        "phase": 3,
        "phase_item": 3,
        "base_head": BASE_HEAD,
        "activation": "opt-in-public-store-module-command",
        "generation_zero": {
            "root_api_count": len(hive_mind_os.__all__),
            "package_api_count": len(package_system.__all__),
            "cli_parser_count": cli_inventory()["parser_count"],
            "definition_count": frozen["observable_module_surface"]["definition_count"],
            "baseline_definition_count": baseline["observable_module_surface"][
                "definition_count"
            ],
        },
        "phase3_item2_input": {
            "historical_inventory_digest": _digest_bytes(item2_path.read_bytes()),
        },
        "prior_contracts": {
            "phase2_count": len(PHASE2_SCHEMA_NAMES),
            "item1_count": len(PROJECTION_SCHEMA_NAMES),
            "item2_count": len(PUBLIC_MEMORY_SCHEMA_NAMES),
            "resource_digests": prior_resources,
        },
        "cognitive_contracts": {
            "count": len(COGNITIVE_SCHEMA_NAMES),
            "names": list(COGNITIVE_SCHEMA_NAMES),
            "catalog_valid": validate_cognitive_catalog().valid,
            "resource_digests": cognitive_resources,
            "resource_set_digest": _digest_json(cognitive_resources),
        },
        "implementation": {
            path: _digest_bytes((repository / path).read_bytes())
            for path in implementation_paths
        },
        "deterministic_fixture": _fixture(),
        "telemetry_coverage": "released-metadata-only",
        "usage_accounting_status": "unavailable",
        "external_dependencies_added": 0,
        "obsidian_runtime_required": False,
        "bases_canvas_started": False,
        "federation_started": False,
        "watchers_sync_started": False,
        "generation_zero_activated": False,
    }
    return {**body, "inventory_digest": _digest_json(body)}


def main() -> int:
    repository = Path(__file__).parents[1]
    inventory = build_phase3_item3_inventory(repository)
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
