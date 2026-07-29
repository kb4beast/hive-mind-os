from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hive_mind_os.foundation.authority import decide_foundation_write
from hive_mind_os.foundation.brain import project_memory_pack
from hive_mind_os.foundation.canonical import digest
from hive_mind_os.foundation.cognitive import project_cognitive_notes
from hive_mind_os.foundation.cognitive_views import project_cognitive_views
from hive_mind_os.foundation.public_memory import (
    PUBLIC_MEMORY_RELEASE_ACTION,
    PUBLIC_MEMORY_RELEASER,
    materialize_public_memory,
)
from hive_mind_os.foundation.store import FoundationStore
from hive_mind_os.models import Role
from hive_mind_os.policy import PolicyDecision

TENANT_ID = "tenant:phase3-item5-refresh"
REPOSITORY_ID = "repository:phase3-item5-refresh"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _result_document(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_document"):
        return value.to_document()
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"unsupported projector result: {type(value).__name__}")


def _authority(
    action: str,
    *,
    actor_id: str,
    payload: dict[str, Any] | None = None,
):
    decision = decide_foundation_write(
        role=Role.BUILDER,
        action=action,
        policy_decision=PolicyDecision(True, "phase-3 item-5 runtime fixture"),
        lease_actions={action},
        adapter_actions={action},
        mission_risk_allowed=True,
        budget_available=True,
        tenant_id=TENANT_ID,
        repository_id=REPOSITORY_ID,
        actor_id=actor_id,
        decision_id=f"decision:item5:{action}:{actor_id}",
        lease_id=f"lease:item5:{action}:{actor_id}",
        public_release_decision_id=(
            "release:item5:curator" if payload is not None else None
        ),
        public_release_decided_by=(
            "curator:item5-runtime" if payload is not None else None
        ),
        public_release_subject_digest=digest(payload) if payload is not None else None,
    )
    if not decision.allowed:
        raise RuntimeError(f"fixture authority denied: {decision.reason}")
    return decision


def _identity(subject_commit: str) -> dict[str, Any]:
    return {
        "record_type": "repository-identity",
        "schema_version": 1,
        "tenant_id": TENANT_ID,
        "repository_id": REPOSITORY_ID,
        "project_lineage_id": "lineage:phase3-item5-refresh",
        "instance_id": "instance:phase3-item5-refresh",
        "remote_evidence_digest": digest("local-disposable-clone"),
        "controller_build_digest": digest(subject_commit),
        "self_host_depth": 0,
        "parent_run_id": None,
        "subject_commit": subject_commit,
        "target_cutoff": subject_commit,
    }


def _memory(index: int) -> dict[str, Any]:
    kinds = ("opportunity", "semantic", "decision", "episodic", "social", "resource")
    memory_kind = kinds[index % len(kinds)]
    memory_id = f"memory:item5-refresh:{index:02d}"
    content_digest = digest(
        {"memory_id": memory_id, "memory_kind": memory_kind, "sentinel": index}
    )
    observed_at = f"2026-07-29T20:{index:02d}:00+00:00"
    return {
        "record_type": "memory-record",
        "schema_version": 1,
        "memory_id": memory_id,
        "memory_kind": memory_kind,
        "repository_id": REPOSITORY_ID,
        "tenant_id": TENANT_ID,
        "mission_id": "mission:phase3-item5-refresh",
        "run_id": "run:phase3-item5-refresh",
        "step_id": f"step:phase3-item5-refresh:{index:02d}",
        "actor_id": "builder:phase3-item5-refresh",
        "payload_digest": content_digest,
        "previous_record_id": None,
        "supersedes_record_id": None,
        "observed_at": observed_at,
        "recorded_at": observed_at,
        "causation_id": None,
        "correlation_id": "correlation:phase3-item5-refresh",
        "source_refs": ["source:phase3-item5-refresh"],
        "claim_refs": ["P3-REFRESH-001"],
        "evidence_refs": ["evidence:phase3-item5-refresh"],
        "court_refs": ["P3-OBSIDIAN-REFRESH-001"],
        "code_receipt_refs": [],
        "generation_refs": [],
        "status": "active",
        "confidence_ppm": 1_000_000,
        "freshness_expires_at": None,
        "contradiction_refs": [],
        "relation_refs": [],
        "owner_id": "builder:phase3-item5-refresh",
        "sensitivity": "safe-public",
        "access_purpose": "phase3-item5-runtime",
        "retention": "governed",
        "deletion_policy": "tombstone",
        "quarantine_state": "none",
        "appeal_state": "available",
        "content_digest": content_digest,
        "protected_content_ref": None,
        "retrieval_receipt": None,
    }


def _append(source: Path, index: int, subject_commit: str) -> None:
    first = not source.exists()
    source.parent.mkdir(parents=True, exist_ok=True)
    store = FoundationStore(source, clock=_utc_now)
    try:
        if first:
            store.register_repository(
                _identity(subject_commit),
                authority=_authority(
                    "foundation.repository.register",
                    actor_id="builder:phase3-item5-refresh",
                ),
            )
        payload = _memory(index)
        store.append_record(
            authority=_authority(
                "foundation.memory.write",
                actor_id=payload["actor_id"],
                payload=payload,
            ),
            foundation_action="foundation.memory.write",
            tenant_id=TENANT_ID,
            repository_id=REPOSITORY_ID,
            record_type="memory-record",
            schema_name="memory-record-v1",
            stream_id=f"item5-refresh:{index:02d}",
            payload=payload,
            actor_id=payload["actor_id"],
            idempotency_key=f"item5-refresh:{index:02d}",
            observed_at=payload["observed_at"],
            sensitivity="safe-public",
        )
    finally:
        store.close()


def _project(repository: Path, state: Path, subject_commit: str) -> dict[str, Any]:
    source = state / "private" / "foundation.sqlite3"
    public_store = state / "public" / "released.sqlite3"
    public_store.parent.mkdir(parents=True, exist_ok=True)
    item1 = project_memory_pack(
        source,
        repository,
        tenant_id=TENANT_ID,
        repository_id=REPOSITORY_ID,
        authority=_authority(
            "foundation.projection.write",
            actor_id="foundation-brain-projector-v1",
        ),
    )
    item2 = materialize_public_memory(
        source,
        public_store,
        repository,
        state / "protected-release",
        tenant_id=TENANT_ID,
        repository_id=REPOSITORY_ID,
        authority=_authority(
            PUBLIC_MEMORY_RELEASE_ACTION,
            actor_id=PUBLIC_MEMORY_RELEASER,
        ),
        clock=_utc_now,
    )
    item3 = project_cognitive_notes(
        public_store,
        repository,
        state / "protected-cognitive",
        tenant_id=TENANT_ID,
        repository_id=REPOSITORY_ID,
        authority=_authority(
            "foundation.projection.write",
            actor_id="foundation-cognitive-projector-v1",
        ),
    )
    item4 = project_cognitive_views(
        repository,
        state / "protected-cognitive",
        state / "protected-views",
        tenant_id=TENANT_ID,
        repository_id=REPOSITORY_ID,
        authority=_authority(
            "foundation.projection.write",
            actor_id="foundation-cognitive-view-projector-v1",
        ),
        clock=_utc_now,
    )
    targets = (
        "hive-mind/generated/README.md",
        "hive-mind/generated-cognitive/HOME.md",
        "hive-mind/generated-cognitive-views/bases/ideas.base",
        "hive-mind/generated-cognitive-views/canvases/war-room.canvas",
    )
    return {
        "schema_version": 1,
        "completed_at": _utc_now(),
        "subject_commit": subject_commit,
        "item1": _result_document(item1),
        "item2": _result_document(item2),
        "item3": _result_document(item3),
        "item4": _result_document(item4),
        "targets": {
            path: _sha256(repository / path)
            for path in targets
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("initialize", "append"))
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--subject-commit", required=True)
    parser.add_argument("--index", type=int)
    args = parser.parse_args()
    repository = args.repository.resolve()
    state = args.state.resolve()
    if repository == state or repository in state.parents or state in repository.parents:
        raise SystemExit("repository and protected state must be disjoint")
    source = state / "private" / "foundation.sqlite3"
    if args.command == "initialize":
        if source.exists():
            raise SystemExit("fixture is already initialized")
        for index in range(6):
            _append(source, index, args.subject_commit)
    else:
        if args.index is None or args.index < 6:
            raise SystemExit("append requires --index >= 6")
        _append(source, args.index, args.subject_commit)
    receipt = _project(repository, state, args.subject_commit)
    receipt["command"] = args.command
    receipt["index"] = args.index
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
