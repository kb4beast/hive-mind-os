from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
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
FIXTURE_REGISTRATION = "fixture-registration.json"
MAX_TRACKED_FILES = 5_000
MAX_GIT_OBJECT_FILES = 20_000
MAX_GIT_OBJECT_DIRECTORIES = 1_000


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _is_reparse(metadata: os.stat_result) -> bool:
    return bool(
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _git(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repository), *args),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode:
        raise SystemExit(
            f"Git fixture validation failed: {' '.join(args)}: "
            f"{completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _validate_fixture(
    repository: Path,
    source_repository: Path,
    state: Path,
    *,
    command: str,
    claimed_subject_commit: str | None,
) -> dict[str, Any]:
    if (
        repository == source_repository
        or repository in source_repository.parents
        or source_repository in repository.parents
    ):
        raise SystemExit("fixture repository must be a separate clone")
    if any(
        left == right or left in right.parents or right in left.parents
        for left, right in (
            (repository, state),
            (source_repository, state),
        )
    ):
        raise SystemExit("repository, source repository, and state must be disjoint")
    subject_commit = _git(repository, "rev-parse", "--verify", "HEAD")
    if (
        len(subject_commit) != 40
        or any(character not in "0123456789abcdef" for character in subject_commit)
    ):
        raise SystemExit("fixture HEAD is not a full Git commit")
    if claimed_subject_commit is not None and claimed_subject_commit != subject_commit:
        raise SystemExit("claimed subject commit does not match fixture HEAD")
    if _git(source_repository, "rev-parse", "--verify", "HEAD") != subject_commit:
        raise SystemExit("source repository and fixture clone HEAD differ")
    origin = Path(_git(repository, "remote", "get-url", "origin")).resolve()
    if origin != source_repository:
        raise SystemExit("fixture clone origin does not match source repository")
    if _git(repository, "status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("fixture clone has tracked changes")
    ignored = {
        line.strip()
        for line in (repository / ".gitignore").read_text(encoding="utf-8").splitlines()
    }
    if ".obsidian/" not in ignored or (source_repository / ".obsidian").exists():
        raise SystemExit("source repository Obsidian-state boundary is invalid")
    tracked = _git(repository, "ls-files").splitlines()
    if not tracked or len(tracked) > MAX_TRACKED_FILES:
        raise SystemExit("fixture tracked-file bound failed")
    checked = 0
    for relative in tracked:
        clone_path = repository / relative
        source_path = source_repository / relative
        clone_stat = clone_path.lstat()
        source_stat = source_path.lstat()
        if (
            not stat.S_ISREG(clone_stat.st_mode)
            or not stat.S_ISREG(source_stat.st_mode)
            or _is_reparse(clone_stat)
            or _is_reparse(source_stat)
        ):
            raise SystemExit(f"tracked fixture path is not a regular file: {relative}")
        if (
            clone_stat.st_dev == source_stat.st_dev
            and clone_stat.st_ino == source_stat.st_ino
        ):
            raise SystemExit(f"hardlinked tracked fixture file: {relative}")
        checked += 1
    if not checked:
        raise SystemExit("fixture no-hardlink validation checked no files")
    clone_git_dir_value = Path(_git(repository, "rev-parse", "--git-dir"))
    source_git_dir_value = Path(_git(source_repository, "rev-parse", "--git-dir"))
    clone_git_dir = (
        clone_git_dir_value
        if clone_git_dir_value.is_absolute()
        else repository / clone_git_dir_value
    ).resolve()
    source_git_dir = (
        source_git_dir_value
        if source_git_dir_value.is_absolute()
        else source_repository / source_git_dir_value
    ).resolve()
    if (clone_git_dir / "objects" / "info" / "alternates").exists():
        raise SystemExit("fixture clone uses a shared Git object alternate")
    clone_objects: list[Path] = []
    directory_count = 0
    object_root = clone_git_dir / "objects"
    for directory, directory_names, file_names in os.walk(
        object_root, followlinks=False
    ):
        directory_count += 1
        if directory_count > MAX_GIT_OBJECT_DIRECTORIES:
            raise SystemExit("fixture Git-object directory bound failed")
        directory_path = Path(directory)
        for name in directory_names:
            metadata = (directory_path / name).lstat()
            if not stat.S_ISDIR(metadata.st_mode) or _is_reparse(metadata):
                raise SystemExit("fixture Git-object directory is not regular")
        for name in file_names:
            clone_object = directory_path / name
            metadata = clone_object.lstat()
            if (
                not stat.S_ISREG(metadata.st_mode)
                or _is_reparse(metadata)
                or metadata.st_nlink != 1
            ):
                raise SystemExit("fixture Git object is not a regular file")
            clone_objects.append(clone_object)
            if len(clone_objects) > MAX_GIT_OBJECT_FILES:
                raise SystemExit("fixture Git-object file bound failed")
    if not clone_objects:
        raise SystemExit("fixture Git-object bound failed")
    common_objects_checked = 0
    for clone_object in clone_objects:
        relative = clone_object.relative_to(clone_git_dir / "objects")
        source_object = source_git_dir / "objects" / relative
        if not source_object.exists():
            continue
        clone_stat = clone_object.lstat()
        source_stat = source_object.lstat()
        if (
            not stat.S_ISREG(clone_stat.st_mode)
            or not stat.S_ISREG(source_stat.st_mode)
            or _is_reparse(clone_stat)
            or _is_reparse(source_stat)
        ):
            raise SystemExit("fixture Git object is not a regular file")
        if (
            clone_stat.st_dev == source_stat.st_dev
            and clone_stat.st_ino == source_stat.st_ino
        ):
            raise SystemExit(f"hardlinked Git fixture object: {relative.as_posix()}")
        common_objects_checked += 1
    registration_path = state / FIXTURE_REGISTRATION
    registration = {
        "schema_version": 1,
        "repository": str(repository),
        "source_repository": str(source_repository),
        "subject_commit": subject_commit,
        "origin": str(origin),
        "tracked_file_count": len(tracked),
        "no_hardlink_file_count": checked,
        "git_object_file_count": len(clone_objects),
        "no_hardlink_git_object_count": len(clone_objects),
    }
    if command == "initialize":
        if registration_path.exists():
            raise SystemExit("fixture registration already exists")
    else:
        if not registration_path.is_file():
            raise SystemExit("fixture registration is unavailable")
        if json.loads(registration_path.read_text(encoding="utf-8")) != registration:
            raise SystemExit("fixture identity changed after initialization")
    return registration


def _sanitized_fixture_validation(
    registration: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": registration["schema_version"],
        "subject_commit": registration["subject_commit"],
        "separate_clone": True,
        "origin_matches_source_repository": True,
        "tracked_file_count": registration["tracked_file_count"],
        "no_hardlink_file_count": registration["no_hardlink_file_count"],
        "git_object_file_count": registration["git_object_file_count"],
        "no_hardlink_git_object_count": registration[
            "no_hardlink_git_object_count"
        ],
        "shared_git_object_alternate": False,
        "local_paths_omitted": True,
    }


def _result_document(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_document"):
        return value.to_document()
    if is_dataclass(value) and not isinstance(value, type):
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


def _project(
    repository: Path,
    state: Path,
    subject_commit: str,
    fixture_validation: dict[str, Any],
) -> dict[str, Any]:
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
        "hive-mind/generated-cognitive-views/bases/agent-records.base",
        "hive-mind/generated-cognitive-views/bases/ideas.base",
        "hive-mind/generated-cognitive-views/bases/released-war-room.base",
        "hive-mind/generated-cognitive-views/bases/telemetry-metadata.base",
        "hive-mind/generated-cognitive-views/canvases/war-room.canvas",
        "hive-mind/generated-cognitive-views/manifest.json",
    )
    return {
        "schema_version": 1,
        "completed_at": _utc_now(),
        "subject_commit": subject_commit,
        "fixture_validation": _sanitized_fixture_validation(
            fixture_validation
        ),
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
    parser.add_argument("--source-repository", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--subject-commit")
    parser.add_argument("--index", type=int)
    args = parser.parse_args()
    repository = args.repository.resolve()
    source_repository = args.source_repository.resolve()
    state = args.state.resolve()
    validation = _validate_fixture(
        repository,
        source_repository,
        state,
        command=args.command,
        claimed_subject_commit=args.subject_commit,
    )
    subject_commit = validation["subject_commit"]
    source = state / "private" / "foundation.sqlite3"
    if args.command == "initialize":
        if source.exists():
            raise SystemExit("fixture is already initialized")
        for index in range(6):
            _append(source, index, subject_commit)
        (state / FIXTURE_REGISTRATION).write_text(
            json.dumps(validation, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    else:
        if args.index is None or args.index < 6:
            raise SystemExit("append requires --index >= 6")
        _append(source, args.index, subject_commit)
    receipt = _project(repository, state, subject_commit, validation)
    receipt["command"] = args.command
    receipt["index"] = args.index
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
