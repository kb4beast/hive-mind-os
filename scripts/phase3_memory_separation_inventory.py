from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import hive_mind_os
import hive_mind_os.package_system as package_system
from hive_mind_os.foundation.authority import decide_foundation_write
from hive_mind_os.foundation.brain import (
    project_memory_pack,
    project_released_memory_pack,
)
from hive_mind_os.foundation.canonical import digest
from hive_mind_os.foundation.public_memory import (
    PUBLIC_MEMORY_RELEASE_ACTION,
    PUBLIC_MEMORY_RELEASER,
    PublicMemoryReleaseStore,
    materialize_public_memory,
)
from hive_mind_os.foundation.public_memory_contracts import (
    PUBLIC_MEMORY_SCHEMA_NAMES,
    validate_public_memory_catalog,
)
from hive_mind_os.foundation.store import FoundationStore
from hive_mind_os.models import Role
from hive_mind_os.policy import PolicyDecision
from scripts.phase1_surface_inventory import (
    ARTIFACT_PATH,
    build_inventory,
    cli_inventory,
)

OUTPUT_PATH = Path("evidence/phase3/phase3_memory_separation_inventory.json")
BASE_HEAD = "7f7013c99d86bbd34f966b902bb873cf5c10d740"
TENANT_ID = "tenant:item2-inventory"
REPOSITORY_ID = "repository:item2-inventory"


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
        policy_decision=PolicyDecision(True, "item-2 inventory fixture"),
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
            "release:item2-inventory-curator"
            if public_payload is not None
            else None
        ),
        public_release_decided_by=(
            "curator:item2-inventory" if public_payload is not None else None
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
        "project_lineage_id": "lineage:item2-inventory",
        "instance_id": "instance:item2-inventory",
        "remote_evidence_digest": digest("remote"),
        "controller_build_digest": digest("controller"),
        "self_host_depth": 0,
        "parent_run_id": None,
        "subject_commit": BASE_HEAD,
        "target_cutoff": BASE_HEAD,
    }


def _memory(memory_id: str, sensitivity: str) -> dict[str, Any]:
    content_digest = digest(memory_id)
    return {
        "record_type": "memory-record",
        "schema_version": 1,
        "memory_id": memory_id,
        "memory_kind": "semantic",
        "repository_id": REPOSITORY_ID,
        "tenant_id": TENANT_ID,
        "mission_id": "mission:item2-inventory",
        "run_id": "run:item2-inventory",
        "step_id": "step:item2-inventory",
        "actor_id": "builder",
        "payload_digest": content_digest,
        "previous_record_id": None,
        "supersedes_record_id": None,
        "observed_at": "2026-07-29T16:00:00+00:00",
        "recorded_at": "2026-07-29T16:00:01+00:00",
        "causation_id": None,
        "correlation_id": "correlation:item2-inventory",
        "source_refs": ["source:item2-inventory"],
        "claim_refs": ["SEP-002"],
        "evidence_refs": ["evidence:item2-inventory"],
        "court_refs": ["P3-MEMORY-SEPARATION-002"],
        "code_receipt_refs": [],
        "generation_refs": [],
        "status": "active",
        "confidence_ppm": 1_000_000,
        "freshness_expires_at": None,
        "contradiction_refs": [],
        "relation_refs": [],
        "owner_id": "builder",
        "sensitivity": sensitivity,
        "access_purpose": "item2-inventory",
        "retention": "governed",
        "deletion_policy": "tombstone",
        "quarantine_state": "none",
        "appeal_state": "available",
        "content_digest": content_digest,
        "protected_content_ref": None,
        "retrieval_receipt": None,
    }


def _tree_digest(root: Path) -> str:
    files = {
        path.relative_to(root).as_posix(): _digest_bytes(path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
    return _digest_json(files)


def _fixture() -> dict[str, Any]:
    clock_values = iter(
        (
            "2026-07-29T16:00:00+00:00",
            "2026-07-29T16:00:01+00:00",
            "2026-07-29T16:00:02+00:00",
            "2026-07-29T16:00:03+00:00",
            "2026-07-29T16:00:04+00:00",
            "2026-07-29T16:00:05+00:00",
        )
    )
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        private_root = root / "private"
        private_root.mkdir()
        public_root = root / "public"
        public_root.mkdir()
        direct_repository = root / "direct-repository"
        direct_repository.mkdir()
        separated_repository = root / "separated-repository"
        separated_repository.mkdir()
        source = private_root / "foundation.sqlite3"
        public_store_path = public_root / "safe-public.sqlite3"
        store = FoundationStore(source, clock=lambda: next(clock_values))
        store.register_repository(
            _identity(),
            authority=_authority("foundation.repository.register"),
        )
        for memory_id, sensitivity in (
            ("memory:item2-public", "safe-public"),
            ("memory:item2-private", "private"),
        ):
            payload = _memory(memory_id, sensitivity)
            store.append_record(
                authority=_authority(
                    "foundation.memory.write",
                    public_payload=payload if sensitivity == "safe-public" else None,
                ),
                foundation_action="foundation.memory.write",
                tenant_id=TENANT_ID,
                repository_id=REPOSITORY_ID,
                record_type="memory-record",
                schema_name="memory-record-v1",
                stream_id=memory_id,
                payload=payload,
                actor_id="builder",
                idempotency_key=memory_id,
                observed_at=payload["observed_at"],
                sensitivity=sensitivity,
            )
        store.close()
        release_authority = _authority(
            PUBLIC_MEMORY_RELEASE_ACTION,
            actor_id=PUBLIC_MEMORY_RELEASER,
        )
        materialization = materialize_public_memory(
            source,
            public_store_path,
            separated_repository,
            root / "protected-release",
            tenant_id=TENANT_ID,
            repository_id=REPOSITORY_ID,
            authority=release_authority,
            clock=lambda: next(clock_values),
        )
        projection_authority = _authority(
            "foundation.projection.write",
            actor_id="foundation-brain-projector-v1",
        )
        project_memory_pack(
            source,
            direct_repository,
            tenant_id=TENANT_ID,
            repository_id=REPOSITORY_ID,
            authority=projection_authority,
        )
        separated = project_released_memory_pack(
            public_store_path,
            separated_repository,
            root / "protected-projection",
            tenant_id=TENANT_ID,
            repository_id=REPOSITORY_ID,
            authority=projection_authority,
        )
        release_store = PublicMemoryReleaseStore(
            public_store_path,
            tenant_id=TENANT_ID,
            repository_id=REPOSITORY_ID,
            repository_identity_digest=separated.repository_identity_digest,
            source_foundation_schema_version=1,
            source_foundation_schema_digest=json.loads(
                (
                    separated_repository
                    / "hive-mind"
                    / "generated"
                    / "manifest.json"
                ).read_bytes()
            )["foundation_schema_digest"],
        )
        try:
            logical_digest = release_store.logical_digest()
        finally:
            release_store.close()
        direct_tree = _tree_digest(direct_repository / "hive-mind")
        separated_tree = _tree_digest(separated_repository / "hive-mind")
        return {
            "materialization_status": materialization.status,
            "released_record_count": materialization.released_record_count,
            "public_store_logical_digest": logical_digest,
            "source_cursor": materialization.source_cursor,
            "direct_tree_digest": direct_tree,
            "separated_tree_digest": separated_tree,
            "trees_equal": direct_tree == separated_tree,
            "private_projection_state_in_repository": (
                separated_repository / ".hive-mind-projection-state"
            ).exists(),
            "public_projection_tree_digest": separated.tree_digest,
        }


def build_phase3_item2_inventory(repository: Path) -> dict[str, Any]:
    baseline = json.loads((repository / ARTIFACT_PATH).read_text(encoding="utf-8"))
    current_frozen = build_inventory(repository)
    phase2_path = repository / "evidence" / "phase2" / "phase2_foundation_inventory.json"
    phase3_path = repository / "evidence" / "phase3" / "phase3_projection_inventory.json"
    schema_root = (
        repository
        / "src"
        / "hive_mind_os"
        / "foundation"
        / "public_memory_schemas"
    )
    resources = {
        path.name: _digest_bytes(path.read_bytes())
        for path in sorted(schema_root.glob("*.json"))
    }
    implementation_paths = (
        "src/hive_mind_os/foundation/authority.py",
        "src/hive_mind_os/foundation/brain.py",
        "src/hive_mind_os/foundation/public_memory.py",
        "src/hive_mind_os/foundation/public_memory_contracts.py",
    )
    body = {
        "schema_version": 1,
        "phase": 3,
        "phase_item": 2,
        "base_head": BASE_HEAD,
        "activation": "opt-in-release-store-and-module-command",
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
            "historical_inventory_digest": _digest_bytes(phase2_path.read_bytes()),
            "foundation_schema_count": 17,
        },
        "phase3_item1_input": {
            "exact_head": BASE_HEAD,
            "historical_inventory_digest": _digest_bytes(phase3_path.read_bytes()),
            "projection_schema_count": 7,
        },
        "public_memory_contracts": {
            "count": len(PUBLIC_MEMORY_SCHEMA_NAMES),
            "names": list(PUBLIC_MEMORY_SCHEMA_NAMES),
            "catalog_valid": validate_public_memory_catalog().valid,
            "resource_digests": resources,
            "resource_set_digest": _digest_json(resources),
        },
        "implementation": {
            path: _digest_bytes((repository / path).read_bytes())
            for path in implementation_paths
        },
        "deterministic_fixture": _fixture(),
        "external_dependencies_added": 0,
        "generation_zero_activated": False,
        "later_phase3_scope_started": False,
    }
    return {**body, "inventory_digest": _digest_json(body)}


def main() -> int:
    repository = Path(__file__).parents[1]
    inventory = build_phase3_item2_inventory(repository)
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
