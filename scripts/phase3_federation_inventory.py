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
from hive_mind_os.foundation.cognitive_contracts import COGNITIVE_SCHEMA_NAMES
from hive_mind_os.foundation.cognitive_view_contracts import (
    COGNITIVE_VIEW_SCHEMA_NAMES,
)
from hive_mind_os.foundation.contracts import PHASE2_SCHEMA_NAMES
from hive_mind_os.foundation.federation import (
    FEDERATION_ACTION,
    FEDERATION_ACTOR,
    evaluate_self_host_context,
    project_federation,
)
from hive_mind_os.foundation.federation_contracts import (
    FEDERATION_SCHEMA_NAMES,
    validate_federation_catalog,
)
from hive_mind_os.foundation.public_memory_contracts import PUBLIC_MEMORY_SCHEMA_NAMES
from hive_mind_os.models import Role
from hive_mind_os.policy import PolicyDecision
from scripts.phase1_surface_inventory import (
    ARTIFACT_PATH,
    build_inventory,
    cli_inventory,
)

OUTPUT_PATH = Path("evidence/phase3/phase3_federation_inventory.json")
BASE_HEAD = "376a4a6082f6bdf154ba6252ccb70062a17a549b"
TENANT_ID = "tenant:item6-inventory"
PORTFOLIO_ID = "portfolio:item6-inventory"


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


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for name, value in pairs:
        if name in document:
            raise ValueError(f"duplicate JSON object name: {name}")
        document[name] = value
    return document


def _canonical_json_file_digest(path: Path) -> str:
    return _digest_json(
        json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    )


def _write_empty_source(root: Path, repository_id: str, seed: str) -> Path:
    root = root / "hive-mind" / "generated-cognitive"
    root.mkdir(parents=True)
    home = b"# Empty safe-public cognitive source\n"
    (root / "HOME.md").write_bytes(home)
    manifest = {
        "schema_version": "hive-cognitive-manifest/v1",
        "projection_contract": "hive-cognitive-projection/v1",
        "projector_version": "hive-cognitive-projector/v1",
        "mapping_version": "hive-cognitive-mapping/v1",
        "tenant_id": TENANT_ID,
        "repository_id": repository_id,
        "repository_identity_digest": _digest_json({"identity": seed}),
        "source_cursor": "memory-set:" + hashlib.sha256(seed.encode()).hexdigest(),
        "source_digest": _digest_json({"source": seed}),
        "generated_namespace": "hive-mind/generated-cognitive",
        "note_counts": {
            "ideas": 0,
            "evidence": 0,
            "courts": 0,
            "runs": 0,
            "agents": 0,
            "telemetry": 0,
            "total": 0,
        },
        "files": [
            {
                "path": "HOME.md",
                "note_id": "cognitive-home:" + hashlib.sha256(seed.encode()).hexdigest(),
                "source_record_id": None,
                "source_digest": _digest_bytes(home),
                "content_digest": _digest_bytes(home),
            }
        ],
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return root


def _authority():
    return decide_foundation_write(
        role=Role.BUILDER,
        action=FEDERATION_ACTION,
        policy_decision=PolicyDecision(True, "item-6 inventory fixture"),
        lease_actions={FEDERATION_ACTION},
        adapter_actions={FEDERATION_ACTION},
        mission_risk_allowed=True,
        budget_available=True,
        tenant_id=TENANT_ID,
        repository_id=PORTFOLIO_ID,
        actor_id=FEDERATION_ACTOR,
        decision_id="decision:item6-inventory",
        lease_id="lease:item6-inventory",
    )


def _self_host_context(**updates: Any) -> dict[str, Any]:
    context = {
        "schema_version": "hive-self-host-context/v1",
        "controller_os_build_id": "build:item6",
        "controller_instance_id": "controller:item6",
        "tenant_id": TENANT_ID,
        "project_lineage_id": "lineage:hive-mind-os",
        "repo_instance_id": "repo-instance:hive-mind-os",
        "subject_commit": BASE_HEAD,
        "parent_run_id": None,
        "observation_epoch": 1,
        "self_host_depth": 1,
        "origin_record_id": "record:item6",
        "origin_digest": _digest_json({"origin": "item6"}),
        "idempotency_key": "idempotency:item6",
        "origin_kind": "external-evidence",
        "event_kind": "self-analysis",
        "delegation_hops": 0,
        "target_boundary": "repo-instance:hive-mind-os",
    }
    context.update(updates)
    return context


def _fixture() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        first = _write_empty_source(root / "first", "repository:first", "first")
        second = _write_empty_source(root / "second", "repository:second", "second")
        portfolio = root / "portfolio"
        checked = project_federation(
            [second, first],
            portfolio,
            tenant_id=TENANT_ID,
            portfolio_repository_id=PORTFOLIO_ID,
            check=True,
        )
        projected = project_federation(
            [first, second],
            portfolio,
            tenant_id=TENANT_ID,
            portfolio_repository_id=PORTFOLIO_ID,
            authority=_authority(),
        )
        namespace = portfolio / "hive-mind" / "federated-cognitive"
        output = b"".join(
            path.read_bytes() for path in sorted(namespace.rglob("*")) if path.is_file()
        )
        feedback = evaluate_self_host_context(
            _self_host_context(
                origin_kind="projection-event",
                event_kind="projection",
            )
        )
        admitted = evaluate_self_host_context(_self_host_context())
        return {
            "check_status": checked.status,
            "projection_status": projected.status,
            "order_independent_manifest": (
                checked.manifest_digest == projected.manifest_digest
            ),
            "order_independent_tree": checked.tree_digest == projected.tree_digest,
            "source_count": projected.source_count,
            "note_count": projected.note_count,
            "explicit_source_tenant_absent_in_fixture": TENANT_ID.encode() not in output,
            "explicit_source_repository_ids_absent_in_fixture": (
                b"repository:first" not in output
                and b"repository:second" not in output
            ),
            "portfolio_repository_id_disclosed": PORTFOLIO_ID.encode() in output,
            "result_namespace_path_disclosed": bool(projected.namespace_path),
            "projection_feedback": feedback,
            "self_analysis_admission": admitted,
        }


def build_phase3_item6_inventory(repository: Path) -> dict[str, Any]:
    baseline = json.loads((repository / ARTIFACT_PATH).read_text(encoding="utf-8"))
    frozen = build_inventory(repository)
    prior_inventory = (
        repository
        / "evidence"
        / "phase3"
        / "phase3_obsidian_vault_refresh_inventory.json"
    )
    schema_root = (
        repository / "src" / "hive_mind_os" / "foundation" / "federation_schemas"
    )
    resources = {
        path.name: _digest_bytes(path.read_bytes())
        for path in sorted(schema_root.glob("*.json"))
    }
    implementation_paths = (
        "pyproject.toml",
        "scripts/phase3_federation_inventory.py",
        "scripts/verify_installed_wheel.py",
        "src/hive_mind_os/foundation/authority.py",
        "src/hive_mind_os/foundation/federation.py",
        "src/hive_mind_os/foundation/federation_contracts.py",
        "tests/test_phase3_federation.py",
    )
    body = {
        "schema_version": 1,
        "phase": 3,
        "phase_item": 6,
        "base_head": BASE_HEAD,
        "activation": "opt-in-safe-public-federation-module-command",
        "generation_zero": {
            "root_api_count": len(hive_mind_os.__all__),
            "package_api_count": len(package_system.__all__),
            "cli_parser_count": cli_inventory()["parser_count"],
            "definition_count": frozen["observable_module_surface"]["definition_count"],
            "baseline_definition_count": baseline["observable_module_surface"][
                "definition_count"
            ],
        },
        "phase3_item5_input": {
            "historical_inventory_digest": _canonical_json_file_digest(
                prior_inventory
            ),
        },
        "prior_contracts": {
            "phase2_count": len(PHASE2_SCHEMA_NAMES),
            "item1_count": len(PROJECTION_SCHEMA_NAMES),
            "item2_count": len(PUBLIC_MEMORY_SCHEMA_NAMES),
            "item3_count": len(COGNITIVE_SCHEMA_NAMES),
            "item4_count": len(COGNITIVE_VIEW_SCHEMA_NAMES),
        },
        "federation_contracts": {
            "count": len(FEDERATION_SCHEMA_NAMES),
            "names": list(FEDERATION_SCHEMA_NAMES),
            "catalog_valid": validate_federation_catalog().valid,
            "resource_digests": resources,
            "resource_set_digest": _digest_json(resources),
        },
        "implementation": {
            path: _digest_bytes((repository / path).read_bytes())
            for path in implementation_paths
        },
        "deterministic_fixture": _fixture(),
        "external_dependencies_added": 0,
        "community_plugins_required": False,
        "obsidian_required": False,
        "inbox_or_import_started": False,
        "cross_tenant_federation_allowed": False,
        "production_activation": False,
        "generation_zero_activated": False,
    }
    return {**body, "inventory_digest": _digest_json(body)}


def main() -> int:
    repository = Path(__file__).parents[1]
    inventory = build_phase3_item6_inventory(repository)
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
