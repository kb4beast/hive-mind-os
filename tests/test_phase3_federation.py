from __future__ import annotations

import json
import os
import subprocess
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

import pytest

import hive_mind_os.foundation.federation as federation_module
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
    payload_updates: Mapping[str, object] | None = None,
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
        "status": "active",
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
    if payload_updates:
        payload.update(payload_updates)
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


def test_rejects_private_unknown_and_inconsistent_payloads(tmp_path: Path) -> None:
    second = _write_source(
        tmp_path / "second",
        tenant="tenant-a",
        repository="repo-two",
        identity_seed="two",
        record_id="record:two",
    )
    for name, updates in (
        ("private", {"sensitivity": "private"}),
        ("unknown", {"password": "must-not-publish"}),
    ):
        first = _write_source(
            tmp_path / name,
            tenant="tenant-a",
            repository=f"repo-{name}",
            identity_seed=name,
            record_id=f"record:{name}",
            payload_updates=updates,
        )
        with pytest.raises(FederationError, match="payload"):
            project_federation(
                [first, second],
                tmp_path / f"portfolio-{name}",
                tenant_id="tenant-a",
                portfolio_repository_id="portfolio",
                check=True,
            )


def test_rejects_unmanaged_source_and_target_state(tmp_path: Path) -> None:
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
    (sources[0] / "unmanaged.txt").write_text("unmanaged", encoding="utf-8")
    with pytest.raises(FederationError, match="unmanaged"):
        project_federation(
            sources,
            tmp_path / "portfolio",
            tenant_id="tenant-a",
            portfolio_repository_id="portfolio",
            check=True,
        )
    (sources[0] / "unmanaged.txt").unlink()
    project_federation(
        sources,
        tmp_path / "portfolio",
        tenant_id="tenant-a",
        portfolio_repository_id="portfolio",
        authority=_authority(),
    )
    namespace = tmp_path / "portfolio" / "hive-mind" / "federated-cognitive"
    (namespace / "unmanaged-empty-directory").mkdir()
    with pytest.raises(FederationError, match="unmanaged directories"):
        project_federation(
            sources,
            tmp_path / "portfolio",
            tenant_id="tenant-a",
            portfolio_repository_id="portfolio",
            authority=_authority(),
        )


def test_rejects_interrupted_staging_and_excess_sources(tmp_path: Path) -> None:
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
    staging = tmp_path / "portfolio" / "hive-mind" / ".federation-interrupted"
    staging.mkdir(parents=True)
    with pytest.raises(FederationError, match="operator recovery"):
        project_federation(
            sources,
            tmp_path / "portfolio",
            tenant_id="tenant-a",
            portfolio_repository_id="portfolio",
            authority=_authority(),
        )
    with pytest.raises(FederationError, match="source bound"):
        project_federation(
            (sources[index % 2] for index in range(65)),
            tmp_path / "other-portfolio",
            tenant_id="tenant-a",
            portfolio_repository_id="portfolio",
            check=True,
        )


def test_interrupted_staging_blocks_unchanged_rerun(tmp_path: Path) -> None:
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
    portfolio = tmp_path / "portfolio"
    project_federation(
        sources,
        portfolio,
        tenant_id="tenant-a",
        portfolio_repository_id="portfolio",
        authority=_authority(),
    )
    staging = portfolio / "hive-mind" / ".federation-interrupted"
    staging.mkdir()
    (staging / "partial").write_text("preserve", encoding="utf-8")
    with pytest.raises(FederationError, match="operator recovery"):
        project_federation(
            sources,
            portfolio,
            tenant_id="tenant-a",
            portfolio_repository_id="portfolio",
            authority=_authority(),
        )
    assert (staging / "partial").read_text(encoding="utf-8") == "preserve"


def test_tree_enumeration_stops_at_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "many"
    root.mkdir()
    for index in range(10):
        (root / f"{index}.txt").write_text("x", encoding="utf-8")
    real_scandir = os.scandir
    consumed = [0]

    class CountingScandir:
        def __init__(self, path: str | os.PathLike[str]) -> None:
            self._inner = real_scandir(path)

        def __enter__(self) -> "CountingScandir":
            return self

        def __exit__(self, *_args: object) -> None:
            self._inner.close()

        def __iter__(self) -> "CountingScandir":
            return self

        def __next__(self) -> Any:
            item = next(self._inner)
            consumed[0] += 1
            return item

    monkeypatch.setattr(federation_module, "MAX_TREE_ENTRIES", 2)
    monkeypatch.setattr(federation_module.os, "scandir", CountingScandir)
    with pytest.raises(FederationError, match="entry bound"):
        federation_module._enumerate_tree(root)
    assert consumed[0] == 3


def test_revalidates_sources_after_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    original = federation_module._source_tree_receipt
    calls = 0

    def mutate_before_final(
        source_root: Path,
        expected_digests: Mapping[str, str],
    ) -> str:
        nonlocal calls
        calls += 1
        if calls == 3:
            (sources[0] / "HOME.md").write_text("changed\n", encoding="utf-8")
        return original(source_root, expected_digests)

    monkeypatch.setattr(
        federation_module,
        "_source_tree_receipt",
        mutate_before_final,
    )
    with pytest.raises(FederationError, match="changed"):
        project_federation(
            sources,
            tmp_path / "portfolio",
            tenant_id="tenant-a",
            portfolio_repository_id="portfolio",
            authority=_authority(),
        )
    parent = tmp_path / "portfolio" / "hive-mind"
    assert not (parent / "federated-cognitive").exists()
    assert not list(parent.glob(".federation-*"))


def test_no_replace_publication_preserves_racing_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    original = federation_module._rename_no_replace

    def race(source: Path, destination: Path) -> None:
        destination.mkdir()
        (destination / "racing-owner.txt").write_text("preserve", encoding="utf-8")
        original(source, destination)

    monkeypatch.setattr(federation_module, "_rename_no_replace", race)
    with pytest.raises((FileExistsError, OSError)):
        project_federation(
            sources,
            tmp_path / "portfolio",
            tenant_id="tenant-a",
            portfolio_repository_id="portfolio",
            authority=_authority(),
        )
    namespace = tmp_path / "portfolio" / "hive-mind" / "federated-cognitive"
    assert (namespace / "racing-owner.txt").read_text(encoding="utf-8") == "preserve"
    assert not list(namespace.parent.glob(".federation-*"))


def test_rejects_linked_source_and_target_roots(tmp_path: Path) -> None:
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
    source_link = tmp_path / "source-link"
    target_link = tmp_path / "target-link"
    target_destination = tmp_path / "target-destination"
    target_destination.mkdir()
    try:
        source_link.symlink_to(sources[0], target_is_directory=True)
        target_link.symlink_to(target_destination, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation is unavailable")
    with pytest.raises(FederationError, match="linked or reparse"):
        project_federation(
            [source_link, sources[1]],
            tmp_path / "portfolio",
            tenant_id="tenant-a",
            portfolio_repository_id="portfolio",
            check=True,
        )
    with pytest.raises(FederationError, match="linked or reparse"):
        project_federation(
            sources,
            target_link,
            tenant_id="tenant-a",
            portfolio_repository_id="portfolio",
            authority=_authority(),
        )
    assert not (target_destination / "hive-mind").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows junction regression")
def test_rejects_windows_junction_redirection_into_source(tmp_path: Path) -> None:
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
    portfolio = tmp_path / "portfolio"
    portfolio.mkdir()
    junction = portfolio / "hive-mind"
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(sources[0])],
        capture_output=True,
        check=False,
        text=True,
    )
    if created.returncode != 0:
        pytest.skip("junction creation is unavailable")
    try:
        with pytest.raises(FederationError, match="linked or reparse"):
            project_federation(
                sources,
                portfolio,
                tenant_id="tenant-a",
                portfolio_repository_id="portfolio",
                authority=_authority(),
            )
        assert not (sources[0] / "federated-cognitive").exists()
    finally:
        if os.path.lexists(junction):
            os.rmdir(junction)


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


def test_self_host_prior_scope_epoch_and_history_bounds() -> None:
    prior = _context(observation_epoch=2)
    with pytest.raises(FederationError, match="scope mismatch"):
        evaluate_self_host_context(
            _context(
                origin_record_id="record:new",
                origin_digest="sha256:" + "2" * 64,
                idempotency_key="idempotency:new",
            ),
            [{**prior, "tenant_id": "tenant-b"}],
        )
    regressed = _context(
        subject_commit="commit:b",
        observation_epoch=1,
        origin_record_id="record:changed",
        origin_digest="sha256:" + "3" * 64,
        idempotency_key="idempotency:changed",
    )
    decision = evaluate_self_host_context(regressed, [prior])
    assert decision["status"] == "rejected"
    assert decision["reason"] == "stale-observation-epoch"
    with pytest.raises(FederationError, match="history exceeds"):
        evaluate_self_host_context(
            _context(),
            (_context(idempotency_key=f"idempotency:{index}") for index in range(10_001)),
        )


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
