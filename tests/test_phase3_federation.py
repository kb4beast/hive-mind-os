from __future__ import annotations

import json
import os
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from hive_mind_os.foundation.authority import decide_foundation_write
from hive_mind_os.foundation.canonical import canonical_bytes
from hive_mind_os.foundation.federation import (
    FEDERATION_ACTION,
    FEDERATION_ACTOR,
    FederationError,
    evaluate_self_host_context,
    project_federation,
)
from hive_mind_os.foundation.federation_contracts import (
    FEDERATION_SCHEMA_NAMES,
    validate_federation_catalog,
)
from hive_mind_os.models import Role
from hive_mind_os.policy import PolicyDecision
from scripts.phase3_federation_inventory import build_phase3_item6_inventory


def _digest_bytes(content: bytes) -> str:
    return f"sha256:{sha256(content).hexdigest()}"


def _digest_document(document: object) -> str:
    return _digest_bytes(canonical_bytes(document))


def _authority(tenant: str = "tenant-a", repository: str = "portfolio"):
    return decide_foundation_write(
        role=Role.BUILDER,
        action=FEDERATION_ACTION,
        policy_decision=PolicyDecision(True, "test"),
        lease_actions={FEDERATION_ACTION},
        adapter_actions={FEDERATION_ACTION},
        mission_risk_allowed=True,
        budget_available=True,
        tenant_id=tenant,
        repository_id=repository,
        actor_id=FEDERATION_ACTOR,
        decision_id="decision:test-federation",
        lease_id="lease:test-federation",
    )


def _write_source(
    root: Path,
    *,
    tenant: str,
    repository: str,
    identity_seed: str,
    record_id: str,
) -> Path:
    root.mkdir(parents=True)
    identity_digest = _digest_document({"identity": identity_seed})
    source_digest = _digest_document({"record": record_id})
    content_digest = _digest_document({"content": record_id})
    note_key = sha256(
        canonical_bytes(
            {
                "identity_domain": "hive-cognitive-note/v1",
                "subject": record_id,
            }
        )
    ).hexdigest()
    note_id = f"cognitive-note:{note_key}"
    payload = {
        "record_type": "memory-record",
        "schema_version": 1,
        "memory_id": f"memory:{record_id}",
        "memory_kind": "semantic",
        "repository_id": repository,
        "tenant_id": tenant,
        "mission_id": "mission:test",
        "run_id": "run:test",
        "step_id": "step:test",
        "actor_id": "actor:test",
        "payload_digest": content_digest,
        "previous_record_id": None,
        "supersedes_record_id": None,
        "observed_at": "2026-07-29T00:00:00Z",
        "recorded_at": "2026-07-29T00:00:01Z",
        "causation_id": None,
        "correlation_id": None,
        "source_refs": [],
        "claim_refs": [],
        "evidence_refs": [],
        "court_refs": [],
        "code_receipt_refs": [],
        "generation_refs": [],
        "status": "accepted",
        "confidence_ppm": 900000,
        "freshness_expires_at": None,
        "contradiction_refs": [],
        "relation_refs": [],
        "owner_id": "owner:test",
        "sensitivity": "safe-public",
        "access_purpose": "test",
        "retention": "project",
        "deletion_policy": "tombstone",
        "quarantine_state": "none",
        "appeal_state": "none",
        "content_digest": content_digest,
        "protected_content_ref": None,
        "retrieval_receipt": None,
    }
    properties = {
        "schema_version": "hive-cognitive-note/v1",
        "note_id": note_id,
        "note_kind": "evidence",
        "subject_id": payload["memory_id"],
        "source_record_id": record_id,
        "memory_kind": "semantic",
        "tenant_id": tenant,
        "repository_id": repository,
        "repository_identity_digest": identity_digest,
        "mission_id": payload["mission_id"],
        "run_id": payload["run_id"],
        "step_id": payload["step_id"],
        "actor_id": payload["actor_id"],
        "owner_id": payload["owner_id"],
        "observed_at": payload["observed_at"],
        "recorded_at": payload["recorded_at"],
        "status": payload["status"],
        "confidence_ppm": payload["confidence_ppm"],
        "freshness_expires_at": None,
        "sensitivity": "safe-public",
        "source_schema": "memory-record-v1",
        "source_digest": source_digest,
        "source_previous_digest": None,
        "previous_record_id": None,
        "supersedes_record_id": None,
        "source_refs": [],
        "claim_refs": [],
        "evidence_refs": [],
        "court_refs": [],
        "code_receipt_refs": [],
        "generation_refs": [],
        "contradiction_refs": [],
        "relation_refs": [],
        "public_release_decision_id": "decision:release",
        "public_release_decided_by": "curator:test",
        "projection_cursor": "memory-set:" + "1" * 64,
        "content_digest": content_digest,
        "generator_version": "hive-cognitive-projector/v1",
        "mapping_version": "hive-cognitive-mapping/v1",
        "is_generated": True,
        "is_authoritative": False,
    }
    note = "\n".join(
        [
            "---",
            *(
                f"{name}: {json.dumps(value, sort_keys=True)}"
                for name, value in properties.items()
            ),
            "---",
            "",
            "# Released cognitive record",
            "",
            "## Safe-public metadata",
            "",
            *(
                f"    {line}"
                for line in json.dumps(payload, indent=2, sort_keys=True).splitlines()
            ),
            "",
        ]
    ).encode()
    note_path = f"evidence/{note_key}.md"
    (root / "evidence").mkdir()
    (root / note_path).write_bytes(note)
    home = b"# Source HOME\n"
    (root / "HOME.md").write_bytes(home)
    manifest = {
        "schema_version": "hive-cognitive-manifest/v1",
        "projection_contract": "hive-cognitive-projection/v1",
        "projector_version": "hive-cognitive-projector/v1",
        "mapping_version": "hive-cognitive-mapping/v1",
        "tenant_id": tenant,
        "repository_id": repository,
        "repository_identity_digest": identity_digest,
        "source_cursor": "memory-set:" + "1" * 64,
        "source_digest": _digest_document({"source": identity_seed}),
        "generated_namespace": "hive-mind/generated-cognitive",
        "note_counts": {
            "ideas": 0,
            "evidence": 1,
            "courts": 0,
            "runs": 0,
            "agents": 0,
            "telemetry": 0,
            "total": 1,
        },
        "files": [
            {
                "path": "HOME.md",
                "note_id": "cognitive-home:" + "2" * 64,
                "source_record_id": None,
                "source_digest": _digest_bytes(home),
                "content_digest": _digest_bytes(home),
            },
            {
                "path": note_path,
                "note_id": note_id,
                "source_record_id": record_id,
                "source_digest": source_digest,
                "content_digest": _digest_bytes(note),
            },
        ],
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return root


def _context(**updates: object) -> dict[str, object]:
    context: dict[str, object] = {
        "schema_version": "hive-self-host-context/v1",
        "controller_os_build_id": "build:controller",
        "controller_instance_id": "instance:controller",
        "tenant_id": "tenant-a",
        "project_lineage_id": "lineage:hive",
        "repo_instance_id": "repo-instance:hive",
        "subject_commit": "commit:a",
        "parent_run_id": None,
        "observation_epoch": 1,
        "self_host_depth": 1,
        "origin_record_id": "record:external",
        "origin_digest": "sha256:" + "1" * 64,
        "idempotency_key": "idempotency:one",
        "origin_kind": "external-evidence",
        "event_kind": "self-analysis",
        "delegation_hops": 0,
        "target_boundary": "repo-instance:hive",
    }
    context.update(updates)
    return context


def test_federation_catalog_is_strict() -> None:
    assert len(FEDERATION_SCHEMA_NAMES) == 5
    assert validate_federation_catalog().valid


def test_projects_deterministic_sanitized_portfolio(tmp_path: Path) -> None:
    first = _write_source(
        tmp_path / "first",
        tenant="tenant-a",
        repository="private-repository-one",
        identity_seed="one",
        record_id="record:one",
    )
    second = _write_source(
        tmp_path / "second",
        tenant="tenant-a",
        repository="private-repository-two",
        identity_seed="two",
        record_id="record:two",
    )
    checked = project_federation(
        [second, first],
        tmp_path / "portfolio",
        tenant_id="tenant-a",
        portfolio_repository_id="portfolio",
        check=True,
    )
    projected = project_federation(
        [first, second],
        tmp_path / "portfolio",
        tenant_id="tenant-a",
        portfolio_repository_id="portfolio",
        authority=_authority(),
    )
    unchanged = project_federation(
        [second, first],
        tmp_path / "portfolio",
        tenant_id="tenant-a",
        portfolio_repository_id="portfolio",
        authority=_authority(),
    )
    assert checked.status == "checked"
    assert projected.status == "projected"
    assert unchanged.status == "unchanged"
    assert (checked.manifest_digest, checked.tree_digest) == (
        projected.manifest_digest,
        projected.tree_digest,
    )
    namespace = tmp_path / "portfolio" / "hive-mind" / "federated-cognitive"
    all_bytes = b"".join(
        path.read_bytes() for path in namespace.rglob("*") if path.is_file()
    )
    assert b"tenant-a" not in all_bytes
    assert b"private-repository-one" not in all_bytes
    assert b"private-repository-two" not in all_bytes
    assert b"source_identity_role: \"provenance-only\"" in all_bytes
    assert b"is_authoritative: false" in all_bytes


def test_rejects_cross_tenant_and_conflicting_existing_namespace(tmp_path: Path) -> None:
    first = _write_source(
        tmp_path / "first",
        tenant="tenant-a",
        repository="repo-one",
        identity_seed="one",
        record_id="record:one",
    )
    other_tenant = _write_source(
        tmp_path / "other",
        tenant="tenant-b",
        repository="repo-two",
        identity_seed="two",
        record_id="record:two",
    )
    with pytest.raises(FederationError, match="cross-tenant"):
        project_federation(
            [first, other_tenant],
            tmp_path / "portfolio",
            tenant_id="tenant-a",
            portfolio_repository_id="portfolio",
            check=True,
        )
    second = _write_source(
        tmp_path / "second",
        tenant="tenant-a",
        repository="repo-two",
        identity_seed="two",
        record_id="record:two",
    )
    project_federation(
        [first, second],
        tmp_path / "portfolio",
        tenant_id="tenant-a",
        portfolio_repository_id="portfolio",
        authority=_authority(),
    )
    manifest = (
        tmp_path
        / "portfolio"
        / "hive-mind"
        / "federated-cognitive"
        / "manifest.json"
    )
    manifest.write_text("{}\n", encoding="utf-8")
    with pytest.raises(FederationError, match="conflicts"):
        project_federation(
            [first, second],
            tmp_path / "portfolio",
            tenant_id="tenant-a",
            portfolio_repository_id="portfolio",
            authority=_authority(),
        )


def test_requires_authentic_exact_scope_authority(tmp_path: Path) -> None:
    sources = [
        _write_source(
            tmp_path / name,
            tenant="tenant-a",
            repository=f"repo-{name}",
            identity_seed=name,
            record_id=f"record:{name}",
        )
        for name in ("one", "two")
    ]
    with pytest.raises(PermissionError):
        project_federation(
            sources,
            tmp_path / "portfolio",
            tenant_id="tenant-a",
            portfolio_repository_id="portfolio",
        )
    assert not (tmp_path / "portfolio").exists()
    wrong_scope = replace(_authority(), repository_id="other")
    with pytest.raises(PermissionError):
        project_federation(
            sources,
            tmp_path / "portfolio",
            tenant_id="tenant-a",
            portfolio_repository_id="portfolio",
            authority=wrong_scope,
        )
    assert not (tmp_path / "portfolio").exists()


def test_rejects_linked_content_duplicate_identity_and_nested_vaults(
    tmp_path: Path,
) -> None:
    first = _write_source(
        tmp_path / "first",
        tenant="tenant-a",
        repository="repo-one",
        identity_seed="same",
        record_id="record:one",
    )
    duplicate_identity = _write_source(
        tmp_path / "duplicate",
        tenant="tenant-a",
        repository="repo-two",
        identity_seed="same",
        record_id="record:two",
    )
    with pytest.raises(FederationError, match="repeat a repository identity"):
        project_federation(
            [first, duplicate_identity],
            tmp_path / "portfolio",
            tenant_id="tenant-a",
            portfolio_repository_id="portfolio",
            check=True,
        )
    second = _write_source(
        tmp_path / "second",
        tenant="tenant-a",
        repository="repo-two",
        identity_seed="two",
        record_id="record:two",
    )
    note = next((first / "evidence").glob("*.md"))
    os.link(note, tmp_path / "linked-note.md")
    with pytest.raises(FederationError, match="single-link"):
        project_federation(
            [first, second],
            tmp_path / "portfolio",
            tenant_id="tenant-a",
            portfolio_repository_id="portfolio",
            check=True,
        )
    (tmp_path / "linked-note.md").unlink()
    with pytest.raises(FederationError, match="inside a source vault"):
        project_federation(
            [first, second],
            first / "nested-portfolio",
            tenant_id="tenant-a",
            portfolio_repository_id="portfolio",
            check=True,
        )


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        (
            {"origin_kind": "generated-memory", "event_kind": "evidence-ingestion"},
            "generated-memory-reingestion",
        ),
        (
            {"origin_kind": "projection-event", "event_kind": "projection"},
            "projection-feedback",
        ),
        (
            {"origin_kind": "telemetry-event", "event_kind": "telemetry"},
            "telemetry-feedback",
        ),
        (
            {"origin_kind": "idea-event", "event_kind": "idea"},
            "idea-feedback",
        ),
        (
            {"origin_kind": "delegation-event", "event_kind": "delegation"},
            "delegation-feedback",
        ),
        ({"delegation_hops": 9}, "delegation-hop-limit"),
        ({"self_host_depth": 2}, "self-host-depth-limit"),
        ({"target_boundary": None}, "missing-target-boundary"),
    ],
)
def test_self_host_feedback_guards(updates: dict[str, object], reason: str) -> None:
    decision = evaluate_self_host_context(_context(**updates))
    assert decision["status"] == "rejected"
    assert decision["reason"] == reason


def test_self_host_duplicate_and_epoch_rules() -> None:
    prior = _context()
    duplicate = evaluate_self_host_context(_context(), [prior])
    assert duplicate["status"] == "collapsed"
    assert duplicate["reason"] == "duplicate-origin"
    changed = _context(
        subject_commit="commit:b",
        origin_record_id="record:changed",
        origin_digest="sha256:" + "2" * 64,
        idempotency_key="idempotency:changed",
    )
    stale = evaluate_self_host_context(changed, [prior])
    assert stale["status"] == "rejected"
    assert stale["reason"] == "stale-observation-epoch"
    admitted = evaluate_self_host_context(
        {**changed, "observation_epoch": 2},
        [prior],
    )
    assert admitted["status"] == "accepted"
    assert admitted["reason"] == "admitted"


def test_item6_inventory_is_exact() -> None:
    repository = Path(__file__).parents[1]
    committed = json.loads(
        (
            repository
            / "evidence"
            / "phase3"
            / "phase3_federation_inventory.json"
        ).read_text(encoding="utf-8")
    )
    assert build_phase3_item6_inventory(repository) == committed
