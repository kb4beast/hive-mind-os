from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import stat
import sys
import unicodedata
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from hive_mind_os.models import Role, utc_now
from hive_mind_os.policy import PolicyDecision

from .authority import (
    AuthorityDecision,
    authority_decision_is_authentic,
    decide_foundation_write,
)
from .canonical import canonical_bytes
from .cognitive_contracts import validate_cognitive
from .public_memory import (
    PublicMemorySeparationError,
    read_public_memory_release_snapshot,
)

COGNITIVE_PROJECTION_CONTRACT = "hive-cognitive-projection/v1"
COGNITIVE_PROJECTOR_VERSION = "hive-cognitive-projector/v1"
COGNITIVE_MAPPING_VERSION = "hive-cognitive-mapping/v1"
MANAGED_NAMESPACE = "hive-mind/generated-cognitive"
MANIFEST_NAME = "manifest.json"
MAX_RECORDS = 100_000
MAX_NOTE_BYTES = 1_048_576
MAX_MANIFEST_BYTES = 16_777_216
MAX_PACK_BYTES = 268_435_456
MAX_PUBLIC_STORE_BYTES = 536_870_912
MAX_TRANSACTION_BYTES = 268_435_456
MAX_STRING_LENGTH = 4_096
MAX_LIST_ITEMS = 256
MAX_STATE_FILES = 200_010
NOTE_IDENTITY_DOMAIN = "hive-cognitive-note-identity/v1"
HOME_IDENTITY_DOMAIN = "hive-cognitive-home-identity/v1"
FOLDERS = ("ideas", "evidence", "courts", "runs", "agents", "telemetry")
MEMORY_KIND_TO_FOLDER = {
    "opportunity": "ideas",
    "semantic": "evidence",
    "procedural": "evidence",
    "not-applicable": "evidence",
    "decision": "courts",
    "counterfactual": "courts",
    "governance": "courts",
    "working": "runs",
    "episodic": "runs",
    "prospective": "runs",
    "social": "agents",
    "evaluation": "telemetry",
    "resource": "telemetry",
}
_LIST_FIELDS = (
    "source_refs",
    "claim_refs",
    "evidence_refs",
    "court_refs",
    "code_receipt_refs",
    "generation_refs",
    "contradiction_refs",
    "relation_refs",
)
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_SAFE_RELATIVE_PATH = re.compile(
    r"^(?:HOME\.md|manifest\.json|"
    r"(?:ideas|evidence|courts|runs|agents|telemetry)/[0-9a-f]{64}\.md)$"
)


class CognitiveProjectionError(RuntimeError):
    """The cognitive projection could not proceed without weakening its contract."""


class CognitiveProjectionConflict(CognitiveProjectionError):
    """The managed namespace changed or contains an unsafe target."""

    def __init__(self, paths: Sequence[str]) -> None:
        self.paths = tuple(sorted(set(paths)))
        super().__init__("cognitive projection conflict: " + ", ".join(self.paths))


@dataclass(frozen=True, slots=True)
class CognitiveProjectionResult:
    schema_version: str
    status: str
    tenant_id: str
    repository_id: str
    repository_identity_digest: str
    namespace_path: str
    manifest_digest: str
    source_cursor: str
    tree_digest: str
    source_record_count: int
    projected_record_count: int
    note_counts: dict[str, int]
    recovery_status: str
    conflict_paths: tuple[str, ...] = ()
    receipt_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["conflict_paths"] = list(self.conflict_paths)
        check = validate_cognitive("cognitive-result-v1", value)
        if not check.valid:
            raise CognitiveProjectionError("; ".join(check.issues))
        return value


@dataclass(frozen=True, slots=True)
class CognitiveProjectionFailure:
    schema_version: str
    status: str
    error: str

    def to_dict(self) -> dict[str, str]:
        value = asdict(self)
        check = validate_cognitive("cognitive-failure-v1", value)
        if not check.valid:
            raise CognitiveProjectionError("; ".join(check.issues))
        return value


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _digest_document(value: Any) -> str:
    return _digest_bytes(canonical_bytes(value))


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        .encode("utf-8")
        + b"\n"
    )


def _linklike(path: Path) -> bool:
    if path.is_symlink():
        return True
    junction = getattr(path, "is_junction", None)
    if callable(junction) and junction():
        return True
    try:
        flags = getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(flags & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _file_digest(path: Path, limit: int) -> str | None:
    try:
        before = path.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size > limit
            or _linklike(path)
        ):
            return None
        content = path.read_bytes()
        after = path.stat(follow_symlinks=False)
    except OSError:
        return None
    if len(content) > limit or (before.st_dev, before.st_ino, before.st_size) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
    ):
        return None
    return _digest_bytes(content)


def _read_json(path: Path, limit: int, label: str) -> dict[str, Any]:
    digest = _file_digest(path, limit)
    if digest is None:
        raise CognitiveProjectionError(f"{label} is unsafe or exceeds its bound")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CognitiveProjectionError(f"{label} is invalid") from error
    if not isinstance(value, dict):
        raise CognitiveProjectionError(f"{label} is not an object")
    return value


def _safe_value(value: Any, label: str) -> Any:
    if isinstance(value, str):
        if len(value) > MAX_STRING_LENGTH or value != unicodedata.normalize(
            "NFC", value
        ):
            raise CognitiveProjectionError(f"{label} is not bounded NFC text")
        if any(unicodedata.category(char) in {"Cc", "Cf", "Cs"} for char in value):
            raise CognitiveProjectionError(f"{label} contains a control character")
        return value
    if isinstance(value, list):
        if len(value) > MAX_LIST_ITEMS:
            raise CognitiveProjectionError(f"{label} exceeds the list bound")
        return [_safe_value(item, f"{label}[]") for item in value]
    if value is None or type(value) in {bool, int, float}:
        return value
    raise CognitiveProjectionError(f"{label} has an unsupported value")


def _yaml(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _cursor(records: Sequence[Mapping[str, Any]]) -> str:
    body = [
        {"record_id": item["record_id"], "source_digest": item["semantic_digest"]}
        for item in sorted(records, key=lambda row: str(row["record_id"]))
    ]
    return "memory-set:" + _digest_document(body).removeprefix("sha256:")


def _identity_key(domain: str, subject: str) -> str:
    return sha256(
        canonical_bytes({"identity_domain": domain, "subject": subject})
    ).hexdigest()


def _admit_record(
    record: Mapping[str, Any],
    *,
    tenant_id: str,
    repository_id: str,
) -> Mapping[str, Any]:
    payload = record.get("payload")
    source_digest = record.get("semantic_digest")
    if (
        not isinstance(payload, Mapping)
        or record.get("record_type") != "memory-record"
        or record.get("schema_name") != "memory-record-v1"
        or record.get("tenant_id") != tenant_id
        or record.get("repository_id") != repository_id
        or record.get("sensitivity") != "safe-public"
        or record.get("status") == "quarantined"
        or not isinstance(source_digest, str)
        or not _DIGEST.fullmatch(source_digest)
        or record.get("public_release_subject_digest") != source_digest
        or payload.get("record_type") != "memory-record"
        or payload.get("schema_version") != 1
        or payload.get("tenant_id") != tenant_id
        or payload.get("repository_id") != repository_id
        or payload.get("actor_id") != record.get("actor_id")
        or payload.get("observed_at") != record.get("observed_at")
        or payload.get("sensitivity") != "safe-public"
        or payload.get("quarantine_state") != "none"
        or payload.get("protected_content_ref") is not None
        or payload.get("retrieval_receipt") is not None
    ):
        raise CognitiveProjectionError(
            "released record does not satisfy the cognitive public boundary"
        )
    return payload


def _render_note(
    record: Mapping[str, Any],
    identity_digest: str,
    cursor: str,
) -> tuple[str, str, bytes]:
    payload = record.get("payload")
    if not isinstance(payload, Mapping):
        raise CognitiveProjectionError("released memory payload is not an object")
    memory_kind = payload.get("memory_kind")
    folder = MEMORY_KIND_TO_FOLDER.get(str(memory_kind))
    if folder is None:
        raise CognitiveProjectionError(f"unknown memory_kind: {memory_kind!r}")
    record_id = _safe_value(record["record_id"], "record_id")
    key = _identity_key(NOTE_IDENTITY_DOMAIN, record_id)
    note_id = f"cognitive-note:{key}"
    props = {
        "schema_version": "hive-cognitive-note/v1",
        "note_id": note_id,
        "note_kind": folder.removesuffix("s") if folder != "evidence" else "evidence",
        "subject_id": _safe_value(payload["memory_id"], "memory_id"),
        "source_record_id": record_id,
        "memory_kind": memory_kind,
        "tenant_id": record["tenant_id"],
        "repository_id": record["repository_id"],
        "repository_identity_digest": identity_digest,
        "mission_id": payload.get("mission_id"),
        "run_id": payload.get("run_id"),
        "step_id": payload.get("step_id"),
        "actor_id": record["actor_id"],
        "owner_id": payload.get("owner_id"),
        "observed_at": record["observed_at"],
        "recorded_at": record["recorded_at"],
        "status": payload.get("status", record["status"]),
        "confidence_ppm": payload["confidence_ppm"],
        "freshness_expires_at": payload.get("freshness_expires_at"),
        "sensitivity": "safe-public",
        "source_schema": "memory-record-v1",
        "source_digest": record["semantic_digest"],
        "source_previous_digest": record["previous_digest"],
        "previous_record_id": payload.get("previous_record_id"),
        "supersedes_record_id": payload.get("supersedes_record_id"),
        **{name: payload[name] for name in _LIST_FIELDS},
        "public_release_decision_id": record["public_release_decision_id"],
        "public_release_decided_by": record["public_release_decided_by"],
        "projection_cursor": cursor,
        "content_digest": payload["content_digest"],
        "generator_version": COGNITIVE_PROJECTOR_VERSION,
        "mapping_version": COGNITIVE_MAPPING_VERSION,
        "is_generated": True,
        "is_authoritative": False,
    }
    props = {key_name: _safe_value(value, key_name) for key_name, value in props.items()}
    check = validate_cognitive("cognitive-note-v1", props)
    if not check.valid:
        raise CognitiveProjectionError(f"{record_id}: " + "; ".join(check.issues))
    lines = ["---", *(f"{name}: {_yaml(value)}" for name, value in props.items()), "---", ""]
    if folder == "telemetry":
        lines += [
            "# Telemetry metadata",
            "",
            (
                "Usage accounting is unavailable in this released cognitive note; "
                "no zero usage is implied."
            ),
            "",
            "    " + json.dumps(
                {
                    "memory_id": payload["memory_id"],
                    "memory_kind": memory_kind,
                    "run_id": payload.get("run_id"),
                    "actor_id": record["actor_id"],
                    "observed_at": record["observed_at"],
                    "recorded_at": record["recorded_at"],
                    "status": payload["status"],
                    "content_digest": payload["content_digest"],
                },
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            ),
            "",
        ]
    else:
        safe_payload = {
            name: _safe_value(value, f"payload.{name}")
            for name, value in payload.items()
            if name not in {"protected_content_ref", "retrieval_receipt"}
        }
        text = json.dumps(
            safe_payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        lines += [
            "# Released cognitive record",
            "",
            "## Safe-public metadata",
            "",
            *(f"    {line}" for line in text.splitlines()),
            "",
        ]
    content = "\n".join(lines).encode("utf-8")
    if len(content) > MAX_NOTE_BYTES:
        raise CognitiveProjectionError(f"{record_id}: note exceeds size bound")
    return f"{folder}/{key}.md", note_id, content


def _desired(
    snapshot: Any,
    tenant_id: str,
    repository_id: str,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    if snapshot.integrity_issues:
        raise CognitiveProjectionError("public snapshot integrity failed")
    if snapshot.repository_identity_digest is None:
        raise CognitiveProjectionError("repository identity is unavailable")
    if len(snapshot.records) > MAX_RECORDS:
        raise CognitiveProjectionError("released record count exceeds bound")
    cursor = _cursor(snapshot.records)
    files: dict[str, bytes] = {}
    entries: list[dict[str, Any]] = []
    counts = {folder: 0 for folder in FOLDERS}
    for record in snapshot.records:
        _admit_record(
            record,
            tenant_id=tenant_id,
            repository_id=repository_id,
        )
        path, note_id, content = _render_note(
            record,
            snapshot.repository_identity_digest,
            cursor,
        )
        if path in files:
            raise CognitiveProjectionError("duplicate cognitive note path")
        files[path] = content
        counts[path.split("/", 1)[0]] += 1
        entries.append(
            {
                "path": path,
                "note_id": note_id,
                "source_record_id": record["record_id"],
                "source_digest": record["semantic_digest"],
                "content_digest": _digest_bytes(content),
            }
        )
    counts["total"] = len(snapshot.records)
    home_key = _identity_key(
        HOME_IDENTITY_DOMAIN,
        snapshot.repository_identity_digest,
    )
    home_props = {
        "schema_version": "hive-cognitive-home/v1",
        "note_id": f"cognitive-home:{home_key}",
        "note_kind": "home",
        "tenant_id": tenant_id,
        "repository_id": repository_id,
        "repository_identity_digest": snapshot.repository_identity_digest,
        "projection_cursor": cursor,
        "idea_count": counts["ideas"],
        "evidence_count": counts["evidence"],
        "court_count": counts["courts"],
        "run_count": counts["runs"],
        "agent_count": counts["agents"],
        "telemetry_count": counts["telemetry"],
        "total_count": counts["total"],
        "sensitivity": "safe-public",
        "generator_version": COGNITIVE_PROJECTOR_VERSION,
        "mapping_version": COGNITIVE_MAPPING_VERSION,
        "is_generated": True,
        "is_authoritative": False,
    }
    home_validation = validate_cognitive("cognitive-home-v1", home_props)
    if not home_validation.valid:
        raise CognitiveProjectionError(
            "HOME note contract failed: " + "; ".join(home_validation.issues)
        )
    home = "\n".join(
        [
            "---",
            *(f"{key}: {_yaml(value)}" for key, value in home_props.items()),
            "---",
            "",
            "# Cognitive memory",
            "",
            "This generated, nonauthoritative index contains safe-public metadata only.",
            "",
            "Counts in this generated index:",
            "",
            *(f"- {folder}: {counts[folder]}" for folder in FOLDERS),
            f"- total: {counts['total']}",
            "",
        ]
    ).encode("utf-8")
    files["HOME.md"] = home
    entries.append(
        {
            "path": "HOME.md",
            "note_id": home_props["note_id"],
            "source_record_id": None,
            "source_digest": _digest_document(
                {
                    "repository_identity_digest": (
                        snapshot.repository_identity_digest
                    ),
                    "cursor": cursor,
                }
            ),
            "content_digest": _digest_bytes(home),
        }
    )
    manifest = {
        "schema_version": "hive-cognitive-manifest/v1",
        "projection_contract": COGNITIVE_PROJECTION_CONTRACT,
        "projector_version": COGNITIVE_PROJECTOR_VERSION,
        "mapping_version": COGNITIVE_MAPPING_VERSION,
        "tenant_id": tenant_id,
        "repository_id": repository_id,
        "repository_identity_digest": snapshot.repository_identity_digest,
        "source_cursor": cursor,
        "source_digest": _digest_document(
            [
                entry["source_digest"]
                for entry in entries
                if entry["source_record_id"] is not None
            ]
        ),
        "generated_namespace": MANAGED_NAMESPACE,
        "note_counts": counts,
        "files": sorted(entries, key=lambda item: item["path"]),
    }
    check = validate_cognitive("cognitive-manifest-v1", manifest)
    if not check.valid:
        raise CognitiveProjectionError("; ".join(check.issues))
    _validate_manifest_semantics(manifest)
    manifest_bytes = _json_bytes(manifest)
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise CognitiveProjectionError("cognitive manifest exceeds size bound")
    files[MANIFEST_NAME] = manifest_bytes
    if sum(map(len, files.values())) > MAX_PACK_BYTES:
        raise CognitiveProjectionError("cognitive projection exceeds pack bound")
    return files, manifest


def _validate_manifest_semantics(manifest: Mapping[str, Any]) -> None:
    entries = manifest["files"]
    paths = [entry["path"] for entry in entries]
    if (
        paths != sorted(paths)
        or len(paths) != len(set(paths))
        or paths.count("HOME.md") != 1
        or any(not _SAFE_RELATIVE_PATH.fullmatch(path) for path in paths)
    ):
        raise CognitiveProjectionError("cognitive manifest paths are invalid")
    record_entries = [
        entry for entry in entries if entry["source_record_id"] is not None
    ]
    if len(record_entries) != manifest["note_counts"]["total"]:
        raise CognitiveProjectionError("cognitive manifest record count is inconsistent")
    observed_counts = {folder: 0 for folder in FOLDERS}
    for entry in record_entries:
        folder = entry["path"].split("/", 1)[0]
        observed_counts[folder] += 1
    if any(
        observed_counts[folder] != manifest["note_counts"][folder]
        for folder in FOLDERS
    ):
        raise CognitiveProjectionError("cognitive manifest note counts are inconsistent")


def _validated_receipt(
    path: Path,
    *,
    manifest_digest: str,
    tenant_id: str,
    repository_id: str,
    repository_identity_digest: str,
    manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    receipt_root = path.parent
    current_path = path
    current_digest = manifest_digest
    seen: set[str] = set()
    child_operations: list[dict[str, Any]] | None = None
    head_receipt: dict[str, Any] | None = None
    while True:
        expected_id = current_digest.removeprefix("sha256:")
        if expected_id in seen:
            raise CognitiveProjectionError(
                "cognitive receipt chain contains a cycle"
            )
        seen.add(expected_id)
        if len(seen) > MAX_RECORDS:
            raise CognitiveProjectionError(
                "cognitive receipt chain exceeds record bound"
            )
        if (
            current_path.parent != receipt_root
            or current_path.name != f"{expected_id}.json"
            or not current_path.exists()
        ):
            raise CognitiveProjectionError(
                "cognitive ownership receipt prior receipt is missing"
            )
        receipt = _read_json(
            current_path,
            MAX_TRANSACTION_BYTES,
            "cognitive receipt",
        )
        check = validate_cognitive("cognitive-receipt-v1", receipt)
        if not check.valid:
            raise CognitiveProjectionError(
                "cognitive ownership receipt contract failed"
            )
        if (
            receipt["transaction_id"] != expected_id
            or receipt["desired_manifest_digest"] != current_digest
            or receipt["verified_manifest_digest"] != current_digest
            or receipt["tenant_id"] != tenant_id
            or receipt["repository_id"] != repository_id
            or receipt["repository_identity_digest"]
            != repository_identity_digest
        ):
            raise CognitiveProjectionError(
                "cognitive ownership receipt is inconsistent"
            )
        operations = _validate_operations(receipt["operations"])
        operation_by_path = {
            operation["path"]: operation for operation in operations
        }
        if operation_by_path[MANIFEST_NAME]["desired_digest"] != current_digest:
            raise CognitiveProjectionError(
                "cognitive ownership receipt manifest operation is inconsistent"
            )
        desired_plan = {
            operation["path"]: operation["desired_digest"]
            for operation in operations
            if operation["desired_digest"] is not None
        }
        if child_operations is not None:
            child_expected_prior = {
                operation["path"]: operation["expected_prior_digest"]
                for operation in child_operations
                if operation["expected_prior_digest"] is not None
            }
            if child_expected_prior != desired_plan:
                raise CognitiveProjectionError(
                    "cognitive ownership receipt prior plan is inconsistent"
                )
        if head_receipt is None:
            head_receipt = receipt
            if manifest is not None:
                if (
                    manifest["source_cursor"] != receipt["source_cursor"]
                    or manifest["repository_identity_digest"]
                    != receipt["repository_identity_digest"]
                ):
                    raise CognitiveProjectionError(
                        "cognitive ownership receipt source is inconsistent"
                    )
                desired_by_path = {
                    MANIFEST_NAME: manifest_digest,
                    **{
                        entry["path"]: entry["content_digest"]
                        for entry in manifest["files"]
                    },
                }
                if desired_plan != desired_by_path:
                    raise CognitiveProjectionError(
                        "cognitive ownership receipt file plan is inconsistent"
                    )
        prior_manifest_digest = receipt["prior_manifest_digest"]
        if prior_manifest_digest is None:
            if any(
                operation["expected_prior_digest"] is not None
                for operation in operations
            ):
                raise CognitiveProjectionError(
                    "cognitive ownership receipt prior plan is inconsistent"
                )
            return head_receipt
        child_operations = operations
        current_digest = prior_manifest_digest
        current_path = (
            receipt_root
            / f"{prior_manifest_digest.removeprefix('sha256:')}.json"
        )


def _manifest_state(
    root: Path,
    state: Path,
    tenant: str,
    repository_id: str,
    identity: str,
) -> tuple[dict[str, str], str | None, bool]:
    path = root / MANIFEST_NAME
    if not path.exists():
        return {}, None, False
    manifest = _read_json(path, MAX_MANIFEST_BYTES, "cognitive manifest")
    check = validate_cognitive("cognitive-manifest-v1", manifest)
    if not check.valid:
        raise CognitiveProjectionError("existing manifest contract failed")
    _validate_manifest_semantics(manifest)
    if (manifest["tenant_id"], manifest["repository_id"], manifest["repository_identity_digest"]) != (tenant, repository_id, identity):
        raise CognitiveProjectionError("existing manifest scope mismatch")
    digest = _file_digest(path, MAX_MANIFEST_BYTES)
    assert digest is not None
    receipt_path = state / "receipts" / f"{digest.removeprefix('sha256:')}.json"
    owned = (
        _validated_receipt(
            receipt_path,
            manifest_digest=digest,
            tenant_id=tenant,
            repository_id=repository_id,
            repository_identity_digest=identity,
            manifest=manifest,
        )
        is not None
    )
    prior = {entry["path"]: entry["content_digest"] for entry in manifest["files"]} if owned else {}
    return prior, digest, owned


def _conflicts(
    root: Path,
    desired: Mapping[str, bytes],
    prior: Mapping[str, str],
    prior_manifest: str | None,
    owned: bool,
) -> tuple[str, ...]:
    found: set[str] = set()
    visited = 0
    if root.exists():
        if not root.is_dir() or _linklike(root):
            raise CognitiveProjectionError("managed namespace is unsafe")
        for path in root.rglob("*"):
            visited += 1
            if visited > MAX_STATE_FILES:
                raise CognitiveProjectionError("managed namespace exceeds path bound")
            rel = path.relative_to(root).as_posix()
            if _linklike(path):
                found.add(rel)
            elif path.is_file():
                expected = prior_manifest if rel == MANIFEST_NAME and owned else prior.get(rel)
                desired_digest = _digest_bytes(desired[rel]) if rel in desired else None
                actual = _file_digest(path, MAX_MANIFEST_BYTES if rel == MANIFEST_NAME else MAX_NOTE_BYTES)
                if not owned or actual not in {expected, desired_digest}:
                    found.add(rel)
            elif path.is_dir() and rel not in FOLDERS:
                found.add(rel)
    for rel, digest in prior.items():
        path = root / rel
        actual = _file_digest(path, MAX_NOTE_BYTES)
        desired_digest = _digest_bytes(desired[rel]) if rel in desired else None
        if actual not in {digest, desired_digest}:
            found.add(rel)
    return tuple(sorted(found))


def _matches(root: Path, desired: Mapping[str, bytes]) -> bool:
    if not root.is_dir() or _linklike(root):
        return False
    paths = list(root.rglob("*"))
    if len(paths) > MAX_STATE_FILES or any(_linklike(path) for path in paths):
        return False
    observed = {
        path.relative_to(root).as_posix() for path in paths if path.is_file()
    }
    if observed != set(desired):
        return False
    return all(
        _file_digest(
            root / rel,
            MAX_MANIFEST_BYTES if rel == MANIFEST_NAME else MAX_NOTE_BYTES,
        )
        == _digest_bytes(content)
        for rel, content in desired.items()
    )


def _write_durable(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise CognitiveProjectionError("protected destination already exists")
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise CognitiveProjectionError("protected temporary path already exists")
    with temporary.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _validate_protected_tree(state: Path) -> None:
    if not state.exists():
        return
    if not state.is_dir() or _linklike(state):
        raise CognitiveProjectionError("protected state root is unsafe")
    visited = 0
    for path in state.rglob("*"):
        visited += 1
        if visited > MAX_STATE_FILES:
            raise CognitiveProjectionError("protected state exceeds path bound")
        try:
            metadata = path.stat(follow_symlinks=False)
        except OSError as error:
            raise CognitiveProjectionError("protected state changed while read") from error
        if _linklike(path) or (stat.S_ISREG(metadata.st_mode) and metadata.st_nlink != 1):
            raise CognitiveProjectionError(
                "protected state contains a linked or multi-link path"
            )


@contextmanager
def _lock(state: Path) -> Iterator[None]:
    state.mkdir(parents=True, exist_ok=True)
    _validate_protected_tree(state)
    lock = state / "cognitive.lock"
    if lock.exists() and (_linklike(lock) or lock.stat().st_nlink != 1):
        raise CognitiveProjectionError("projection lock is unsafe")
    handle = lock.open("a+b")
    try:
        handle.seek(0)
        if not handle.read(1):
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _validate_operations(operations: Any) -> list[dict[str, Any]]:
    if not isinstance(operations, list):
        raise CognitiveProjectionError("cognitive transaction operations are invalid")
    paths: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for operation in operations:
        if (
            not isinstance(operation, dict)
            or set(operation)
            != {"path", "expected_prior_digest", "desired_digest"}
        ):
            raise CognitiveProjectionError(
                "cognitive transaction operation is invalid"
            )
        rel = operation["path"]
        if (
            not isinstance(rel, str)
            or not _SAFE_RELATIVE_PATH.fullmatch(rel)
            or rel in paths
        ):
            raise CognitiveProjectionError(
                "cognitive transaction operation path is invalid"
            )
        for key in ("expected_prior_digest", "desired_digest"):
            value = operation[key]
            if value is not None and (
                not isinstance(value, str) or not _DIGEST.fullmatch(value)
            ):
                raise CognitiveProjectionError(
                    "cognitive transaction operation digest is invalid"
                )
        if (
            operation["expected_prior_digest"] is None
            and operation["desired_digest"] is None
        ):
            raise CognitiveProjectionError(
                "cognitive transaction operation cannot be a no-op"
            )
        paths.add(rel)
        normalized.append(operation)
    manifest_operations = [
        item for item in normalized if item["path"] == MANIFEST_NAME
    ]
    if (
        len(manifest_operations) != 1
        or manifest_operations[0]["desired_digest"] is None
    ):
        raise CognitiveProjectionError(
            "cognitive transaction lacks one desired manifest"
        )
    return normalized


def _validate_transaction_plan(
    root: Path,
    transaction_root: Path,
    journal: Mapping[str, Any],
) -> list[dict[str, Any]]:
    operations = _validate_operations(journal["operations"])
    desired_manifest_digest = journal["desired_manifest_digest"]
    if (
        journal["transaction_id"]
        != str(desired_manifest_digest).removeprefix("sha256:")
    ):
        raise CognitiveProjectionError(
            "cognitive transaction identity does not match its manifest"
        )
    operation_by_path = {item["path"]: item for item in operations}
    manifest_operation = operation_by_path[MANIFEST_NAME]
    if manifest_operation["desired_digest"] != desired_manifest_digest:
        raise CognitiveProjectionError(
            "cognitive transaction manifest operation is inconsistent"
        )
    staged_manifest = (
        transaction_root / "files" / sha256(MANIFEST_NAME.encode()).hexdigest()
    )
    manifest_source = (
        staged_manifest
        if staged_manifest.exists()
        else root / MANIFEST_NAME
    )
    if _file_digest(manifest_source, MAX_MANIFEST_BYTES) != desired_manifest_digest:
        raise CognitiveProjectionError("staged cognitive manifest digest is invalid")
    manifest = _read_json(
        manifest_source,
        MAX_MANIFEST_BYTES,
        "transaction cognitive manifest",
    )
    validation = validate_cognitive("cognitive-manifest-v1", manifest)
    if not validation.valid:
        raise CognitiveProjectionError("staged cognitive manifest contract failed")
    _validate_manifest_semantics(manifest)
    for field in (
        "tenant_id",
        "repository_id",
        "repository_identity_digest",
        "source_cursor",
    ):
        if manifest[field] != journal[field]:
            raise CognitiveProjectionError(
                f"staged cognitive manifest {field} is inconsistent"
            )
    desired_paths = {MANIFEST_NAME}
    for entry in manifest["files"]:
        desired_paths.add(entry["path"])
        operation = operation_by_path.get(entry["path"])
        if operation is None or operation["desired_digest"] != entry["content_digest"]:
            raise CognitiveProjectionError(
                "cognitive transaction file plan disagrees with its manifest"
            )
    observed_desired_paths = {
        item["path"] for item in operations if item["desired_digest"] is not None
    }
    if observed_desired_paths != desired_paths:
        raise CognitiveProjectionError(
            "cognitive transaction desired paths disagree with its manifest"
        )
    return operations


def _validate_recovery_prior_plan(
    state: Path,
    journal: Mapping[str, Any],
) -> None:
    operations = _validate_operations(journal["operations"])
    prior_manifest_digest = journal["prior_manifest_digest"]
    expected_prior: dict[str, str] = {}
    if prior_manifest_digest is not None:
        receipt_path = (
            state
            / "receipts"
            / f"{prior_manifest_digest.removeprefix('sha256:')}.json"
        )
        receipt = _validated_receipt(
            receipt_path,
            manifest_digest=prior_manifest_digest,
            tenant_id=journal["tenant_id"],
            repository_id=journal["repository_id"],
            repository_identity_digest=journal["repository_identity_digest"],
        )
        if receipt is None:
            raise CognitiveProjectionError(
                "pending transaction prior ownership receipt is missing"
            )
        for operation in _validate_operations(receipt["operations"]):
            if operation["desired_digest"] is not None:
                expected_prior[operation["path"]] = operation["desired_digest"]
        expected_prior[MANIFEST_NAME] = prior_manifest_digest
    for operation in operations:
        if operation["expected_prior_digest"] != expected_prior.get(
            operation["path"]
        ):
            raise CognitiveProjectionError(
                "pending transaction prior plan is inconsistent"
            )


def _destination_digest(path: Path, limit: int) -> str | None:
    if not path.exists() and not path.is_symlink():
        return None
    digest = _file_digest(path, limit)
    if digest is None:
        raise CognitiveProjectionError("projection destination is unsafe")
    return digest


def _validate_managed_write_target(root: Path, destination: Path) -> None:
    if root.parent.exists() and (
        not root.parent.is_dir() or _linklike(root.parent)
    ):
        raise CognitiveProjectionConflict((root.parent.name,))
    if root.exists() and (not root.is_dir() or _linklike(root)):
        raise CognitiveProjectionConflict((".",))
    relative = destination.relative_to(root)
    current = root
    for component in relative.parts[:-1]:
        current = current / component
        if current.exists() and (not current.is_dir() or _linklike(current)):
            raise CognitiveProjectionConflict(
                (current.relative_to(root).as_posix(),)
            )


def _directory_identity(path: Path) -> tuple[int, int]:
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError as error:
        raise CognitiveProjectionConflict((path.name,)) from error
    if not stat.S_ISDIR(metadata.st_mode) or _linklike(path):
        raise CognitiveProjectionConflict((path.name,))
    return metadata.st_dev, metadata.st_ino


@contextmanager
def _no_delete_lease(path: Path, *, directory: bool) -> Iterator[None]:
    if os.name != "nt":
        yield
        return
    import ctypes
    from ctypes import wintypes

    create_file = ctypes.windll.kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    close_handle = ctypes.windll.kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    generic_read = 0x80000000
    file_share_read_write = 0x0001 | 0x0002
    open_existing = 3
    flags = 0x00200000
    if directory:
        flags |= 0x02000000
    handle = create_file(
        str(path),
        generic_read,
        file_share_read_write,
        None,
        open_existing,
        flags,
        None,
    )
    if handle == wintypes.HANDLE(-1).value:
        raise CognitiveProjectionConflict((path.name,))
    try:
        yield
    finally:
        close_handle(handle)


def _preflight_transaction_siblings(
    root: Path,
    operations: Sequence[Mapping[str, Any]],
    transaction_id: str,
) -> None:
    if not root.exists():
        return
    allowed: set[str] = set()
    for operation in operations:
        destination = root / operation["path"]
        allowed.add(
            destination.with_name(
                f".{destination.name}.cognitive-prior-{transaction_id}"
            )
            .relative_to(root)
            .as_posix()
        )
        allowed.add(
            destination.with_name(
                f".{destination.name}.cognitive-next-{transaction_id}"
            )
            .relative_to(root)
            .as_posix()
        )
    visited = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            children = list(directory.iterdir())
        except OSError as error:
            raise CognitiveProjectionConflict(
                (directory.relative_to(root).as_posix(),)
            ) from error
        for path in children:
            visited += 1
            if visited > MAX_STATE_FILES:
                raise CognitiveProjectionError(
                    "managed namespace exceeds path bound during recovery"
                )
            rel = path.relative_to(root).as_posix()
            if (
                ".cognitive-prior-" in path.name
                or ".cognitive-next-" in path.name
            ) and rel not in allowed:
                raise CognitiveProjectionConflict((rel,))
            if path.is_dir() and not _linklike(path):
                pending.append(path)


def _receipt_from_journal(journal: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **journal,
        "schema_version": "hive-cognitive-receipt/v1",
        "status": "committed",
        "committed_at": utc_now(),
        "verified_manifest_digest": journal["desired_manifest_digest"],
    }


def _publish_receipt(state: Path, journal: Mapping[str, Any]) -> Path:
    receipt = _receipt_from_journal(journal)
    check = validate_cognitive("cognitive-receipt-v1", receipt)
    if not check.valid:
        raise CognitiveProjectionError("; ".join(check.issues))
    receipt_bytes = _json_bytes(receipt)
    if len(receipt_bytes) > MAX_TRANSACTION_BYTES:
        raise CognitiveProjectionError("cognitive receipt exceeds size bound")
    receipts = state / "receipts"
    receipts.mkdir(exist_ok=True)
    path = receipts / f"{journal['transaction_id']}.json"
    if path.exists():
        prior = _validated_receipt(
            path,
            manifest_digest=journal["desired_manifest_digest"],
            tenant_id=journal["tenant_id"],
            repository_id=journal["repository_id"],
            repository_identity_digest=journal["repository_identity_digest"],
        )
        assert prior is not None
        comparable_prior = dict(prior)
        comparable_receipt = dict(receipt)
        comparable_prior.pop("committed_at")
        comparable_receipt.pop("committed_at")
        if comparable_prior != comparable_receipt:
            raise CognitiveProjectionError(
                "existing cognitive receipt is inconsistent"
            )
        return path
    _write_durable(path, receipt_bytes)
    return path


def _preserve_conflict(
    root: Path,
    state: Path,
    desired: Mapping[str, bytes],
    prior: Mapping[str, str],
    prior_manifest: str | None,
    paths: Sequence[str],
    authority: AuthorityDecision,
) -> str:
    desired_manifest_digest = _digest_bytes(desired[MANIFEST_NAME])
    entries: list[dict[str, Any]] = []
    for rel in sorted(set(paths)):
        destination = root / rel
        limit = MAX_MANIFEST_BYTES if rel == MANIFEST_NAME else MAX_NOTE_BYTES
        observed = _file_digest(destination, limit) if destination.is_file() else None
        entries.append(
            {
                "path": rel,
                "expected_prior_digest": (
                    prior_manifest if rel == MANIFEST_NAME else prior.get(rel)
                ),
                "observed_digest": observed,
                "desired_digest": (
                    _digest_bytes(desired[rel]) if rel in desired else None
                ),
            }
        )
    conflict_identity = _digest_document(
        {
            "desired_manifest_digest": desired_manifest_digest,
            "conflicts": entries,
        }
    ).removeprefix("sha256:")
    document = {
        "schema_version": "hive-cognitive-conflict/v1",
        "status": "conflict",
        "prior_manifest_digest": prior_manifest,
        "desired_manifest_digest": desired_manifest_digest,
        "authority_decision_id": authority.decision_id,
        "authority_actor_id": authority.actor_id,
        "authority_lease_id": authority.lease_id,
        "attempted_at": utc_now(),
        "conflicts": entries,
    }
    validation = validate_cognitive("cognitive-conflict-v1", document)
    if not validation.valid:
        raise CognitiveProjectionError(
            "cognitive conflict contract failed: " + "; ".join(validation.issues)
        )
    content = _json_bytes(document)
    if len(content) > MAX_TRANSACTION_BYTES:
        raise CognitiveProjectionError("cognitive conflict exceeds size bound")
    conflict_root = state / "conflicts" / conflict_identity
    path = conflict_root / "conflict.json"
    if path.exists():
        prior_document = _read_json(
            path,
            MAX_TRANSACTION_BYTES,
            "cognitive conflict receipt",
        )
        prior_validation = validate_cognitive(
            "cognitive-conflict-v1",
            prior_document,
        )
        if not prior_validation.valid:
            raise CognitiveProjectionError(
                "existing cognitive conflict receipt contract failed"
            )
        prior_comparable = dict(prior_document)
        current_comparable = dict(document)
        prior_comparable.pop("attempted_at", None)
        current_comparable.pop("attempted_at", None)
        if prior_comparable != current_comparable:
            raise CognitiveProjectionError(
                "existing cognitive conflict receipt is inconsistent"
            )
    else:
        conflict_root.mkdir(parents=True, exist_ok=False)
        _write_durable(path, content)
    return f"protected-state:conflicts/{conflict_identity}/conflict.json"


def _apply_transaction(
    root: Path,
    state: Path,
    transaction_root: Path,
    journal: Mapping[str, Any],
    *,
    fail_after_replacements: int | None = None,
) -> str:
    operations = _validate_transaction_plan(root, transaction_root, journal)
    _preflight_transaction_siblings(
        root,
        operations,
        journal["transaction_id"],
    )
    _validate_managed_write_target(root, root / MANIFEST_NAME)
    root.mkdir(parents=True, exist_ok=True)
    for folder in FOLDERS:
        folder_path = root / folder
        _validate_managed_write_target(root, folder_path / "placeholder")
        folder_path.mkdir(exist_ok=True)
    replacements = 0
    for operation in sorted(
        operations,
        key=lambda item: (item["path"] == MANIFEST_NAME, item["path"]),
    ):
        rel = operation["path"]
        destination = root / rel
        _validate_managed_write_target(root, destination)
        limit = MAX_MANIFEST_BYTES if rel == MANIFEST_NAME else MAX_NOTE_BYTES
        swap_path = destination.with_name(
            f".{destination.name}.cognitive-prior-{journal['transaction_id']}"
        )
        install_path = destination.with_name(
            f".{destination.name}.cognitive-next-{journal['transaction_id']}"
        )
        if install_path.exists():
            if destination.exists():
                try:
                    same_file = os.path.samefile(install_path, destination)
                except OSError:
                    same_file = False
                if not same_file:
                    raise CognitiveProjectionConflict((rel,))
                install_path.unlink()
            elif _file_digest(install_path, limit) != operation["desired_digest"]:
                raise CognitiveProjectionConflict((rel,))
        actual = _destination_digest(destination, limit)
        if actual == operation["desired_digest"]:
            if swap_path.exists():
                if (
                    operation["expected_prior_digest"] is None
                    or _file_digest(swap_path, limit)
                    != operation["expected_prior_digest"]
                ):
                    raise CognitiveProjectionConflict((rel,))
                swap_path.unlink()
            continue
        if swap_path.exists():
            swap_digest = _file_digest(swap_path, limit)
            if (
                actual is not None
                or swap_digest != operation["expected_prior_digest"]
            ):
                raise CognitiveProjectionConflict((rel,))
        elif actual != operation["expected_prior_digest"]:
            raise CognitiveProjectionConflict((rel,))
        elif actual is not None:
            if swap_path.exists() or swap_path.is_symlink():
                raise CognitiveProjectionConflict((rel,))
            os.replace(destination, swap_path)
            if _file_digest(swap_path, limit) != operation["expected_prior_digest"]:
                if not destination.exists():
                    os.replace(swap_path, destination)
                raise CognitiveProjectionConflict((rel,))
        if operation["desired_digest"] is None:
            if destination.exists():
                raise CognitiveProjectionConflict((rel,))
            if swap_path.exists():
                swap_path.unlink()
        else:
            _validate_managed_write_target(root, destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            _validate_managed_write_target(root, destination)
            staged_path = (
                transaction_root / "files" / sha256(rel.encode()).hexdigest()
            )
            if _file_digest(staged_path, limit) != operation["desired_digest"]:
                raise CognitiveProjectionError("staged projection content is invalid")
            content = staged_path.read_bytes()
            if _digest_bytes(content) != operation["desired_digest"]:
                raise CognitiveProjectionError("staged projection content changed")
            if not install_path.exists():
                _write_durable(install_path, content)
            if _file_digest(install_path, limit) != operation["desired_digest"]:
                raise CognitiveProjectionError("prepared projection content is invalid")
            if destination.exists():
                raise CognitiveProjectionConflict((rel,))
            with (
                _no_delete_lease(root, directory=True),
                _no_delete_lease(destination.parent, directory=True),
                _no_delete_lease(install_path, directory=False),
            ):
                _validate_managed_write_target(root, destination)
                parent_identity = _directory_identity(destination.parent)
                try:
                    os.link(install_path, destination)
                except OSError as error:
                    raise CognitiveProjectionConflict((rel,)) from error
                try:
                    parent_changed = (
                        _directory_identity(destination.parent)
                        != parent_identity
                    )
                    _validate_managed_write_target(root, destination)
                    same_file = os.path.samefile(
                        install_path,
                        destination,
                    )
                except (OSError, CognitiveProjectionConflict) as error:
                    raise CognitiveProjectionConflict((rel,)) from error
                if parent_changed or not same_file:
                    raise CognitiveProjectionConflict((rel,))
            install_path.unlink()
            if _destination_digest(destination, limit) != operation["desired_digest"]:
                raise CognitiveProjectionConflict((rel,))
            if swap_path.exists():
                swap_path.unlink()
        replacements += 1
        if (
            fail_after_replacements is not None
            and replacements >= fail_after_replacements
        ):
            raise InterruptedError("injected cognitive projection interruption")
    expected_paths = {
        operation["path"]
        for operation in operations
        if operation["desired_digest"] is not None
    }
    observed_paths = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }
    if observed_paths != expected_paths:
        raise CognitiveProjectionError("projection file-set verification failed")
    for operation in operations:
        if operation["desired_digest"] is not None:
            rel = operation["path"]
            limit = MAX_MANIFEST_BYTES if rel == MANIFEST_NAME else MAX_NOTE_BYTES
            if _file_digest(root / rel, limit) != operation["desired_digest"]:
                raise CognitiveProjectionError("projection digest verification failed")
    receipt_path = _publish_receipt(state, journal)
    shutil.rmtree(transaction_root)
    return f"protected-state:receipts/{receipt_path.name}"


def _recover_pending_transactions(
    root: Path,
    state: Path,
    authority: AuthorityDecision,
    *,
    tenant_id: str,
    repository_id: str,
    repository_identity_digest: str,
) -> str | None:
    transactions = state / "transactions"
    if not transactions.exists():
        return None
    if not transactions.is_dir() or _linklike(transactions):
        raise CognitiveProjectionError("protected transaction root is unsafe")
    candidates = sorted(transactions.iterdir(), key=lambda path: path.name)
    if len(candidates) > MAX_RECORDS:
        raise CognitiveProjectionError("pending transaction count exceeds bound")
    latest_receipt: str | None = None
    for transaction_root in candidates:
        if (
            not transaction_root.is_dir()
            or _linklike(transaction_root)
            or not re.fullmatch(r"[0-9a-f]{64}", transaction_root.name)
        ):
            raise CognitiveProjectionError("pending transaction path is invalid")
        expected_manifest_digest = f"sha256:{transaction_root.name}"
        completed_receipt = state / "receipts" / f"{transaction_root.name}.json"
        if completed_receipt.exists():
            _validated_receipt(
                completed_receipt,
                manifest_digest=expected_manifest_digest,
                tenant_id=tenant_id,
                repository_id=repository_id,
                repository_identity_digest=repository_identity_digest,
            )
            shutil.rmtree(transaction_root)
            continue
        journal_path = transaction_root / "transaction.json"
        if not journal_path.exists():
            shutil.rmtree(transaction_root)
            continue
        journal = _read_json(
            journal_path,
            MAX_TRANSACTION_BYTES,
            "pending transaction",
        )
        check = validate_cognitive("cognitive-transaction-v1", journal)
        if not check.valid:
            raise CognitiveProjectionError("pending transaction contract failed")
        if (
            journal["transaction_id"] != transaction_root.name
            or journal["desired_manifest_digest"]
            != f"sha256:{transaction_root.name}"
            or journal["tenant_id"] != tenant_id
            or journal["repository_id"] != repository_id
            or journal["repository_identity_digest"]
            != repository_identity_digest
            or journal["authority_decision_id"] != authority.decision_id
            or journal["authority_actor_id"] != authority.actor_id
            or journal["authority_lease_id"] != authority.lease_id
        ):
            raise CognitiveProjectionError(
                "pending transaction scope or authority is inconsistent"
            )
        _validate_recovery_prior_plan(state, journal)
        latest_receipt = _apply_transaction(
            root,
            state,
            transaction_root,
            journal,
        )
    if transactions.exists() and not any(transactions.iterdir()):
        transactions.rmdir()
    return latest_receipt


def _publish(
    root: Path,
    state: Path,
    desired: Mapping[str, bytes],
    manifest: Mapping[str, Any],
    prior: Mapping[str, str],
    prior_manifest: str | None,
    authority: AuthorityDecision,
    fail_after_replacements: int | None,
) -> str:
    manifest_digest = _digest_bytes(desired[MANIFEST_NAME])
    transaction_id = manifest_digest.removeprefix("sha256:")
    tx_root = state / "transactions" / transaction_id
    journal_path = tx_root / "transaction.json"
    operations = [
        {
            "path": rel,
            "expected_prior_digest": (
                prior_manifest if rel == MANIFEST_NAME else prior.get(rel)
            ),
            "desired_digest": _digest_bytes(content),
        }
        for rel, content in sorted(desired.items())
    ] + [
        {
            "path": rel,
            "expected_prior_digest": digest,
            "desired_digest": None,
        }
        for rel, digest in sorted(prior.items())
        if rel not in desired
    ]
    journal = {
        "schema_version": "hive-cognitive-transaction/v1",
        "transaction_id": transaction_id,
        "tenant_id": manifest["tenant_id"],
        "repository_id": manifest["repository_id"],
        "repository_identity_digest": manifest["repository_identity_digest"],
        "source_cursor": manifest["source_cursor"],
        "prior_manifest_digest": prior_manifest,
        "desired_manifest_digest": manifest_digest,
        "authority_decision_id": authority.decision_id,
        "authority_actor_id": authority.actor_id,
        "authority_lease_id": authority.lease_id,
        "attempted_at": utc_now(),
        "operations": operations,
    }
    check = validate_cognitive("cognitive-transaction-v1", journal)
    if not check.valid:
        raise CognitiveProjectionError("; ".join(check.issues))
    journal_bytes = _json_bytes(journal)
    if len(journal_bytes) > MAX_TRANSACTION_BYTES:
        raise CognitiveProjectionError("cognitive transaction exceeds size bound")
    if tx_root.exists():
        raise CognitiveProjectionError("unexpected pending cognitive transaction")
    staged = tx_root / "files"
    staged.mkdir(parents=True)
    for rel, content in desired.items():
        _write_durable(staged / sha256(rel.encode()).hexdigest(), content)
    _write_durable(journal_path, journal_bytes)
    return _apply_transaction(
        root,
        state,
        tx_root,
        journal,
        fail_after_replacements=fail_after_replacements,
    )


def project_cognitive_notes(
    public_store_path: str | Path,
    repository_root: str | Path,
    protected_state_root: str | Path,
    *,
    tenant_id: str,
    repository_id: str,
    check: bool = False,
    authority: AuthorityDecision | None = None,
    fail_after_replacements: int | None = None,
) -> CognitiveProjectionResult:
    if fail_after_replacements is not None and fail_after_replacements < 1:
        raise CognitiveProjectionError("failure injection count must be positive")
    source_candidate = Path(public_store_path).absolute()
    repository_candidate = Path(repository_root).absolute()
    state_candidate = Path(protected_state_root).absolute()
    if (
        not source_candidate.is_file()
        or _linklike(source_candidate)
        or source_candidate.stat(follow_symlinks=False).st_nlink != 1
    ):
        raise CognitiveProjectionError("public store must be a safe existing file")
    if (
        source_candidate.stat(follow_symlinks=False).st_size
        > MAX_PUBLIC_STORE_BYTES
    ):
        raise CognitiveProjectionError("public store exceeds cognitive read bound")
    source = source_candidate.resolve(strict=True)
    if not repository_candidate.is_dir() or _linklike(repository_candidate):
        raise CognitiveProjectionError("repository root must be a safe existing directory")
    repository = repository_candidate.resolve(strict=True)
    if state_candidate.exists():
        if not state_candidate.is_dir() or _linklike(state_candidate):
            raise CognitiveProjectionError("protected state root is unsafe")
        state = state_candidate.resolve(strict=True)
    else:
        try:
            state_parent = state_candidate.parent.resolve(strict=True)
        except OSError as error:
            raise CognitiveProjectionError(
                "protected state parent must be a safe existing directory"
            ) from error
        if _linklike(state_candidate.parent):
            raise CognitiveProjectionError("protected state parent is unsafe")
        state = state_parent / state_candidate.name
    if state.parent == state or state.is_relative_to(repository) or repository.is_relative_to(state):
        raise CognitiveProjectionError("protected state and repository must be disjoint")
    if state == source.parent or state.is_relative_to(source.parent) or source.parent.is_relative_to(state):
        raise CognitiveProjectionError("protected state and public persistence must be disjoint")
    root = repository / MANAGED_NAMESPACE
    for ancestor in (root.parent, root):
        if ancestor.exists() and (
            not ancestor.is_dir() or _linklike(ancestor)
        ):
            raise CognitiveProjectionError("managed namespace ancestry is unsafe")
    if source.is_relative_to(root):
        raise CognitiveProjectionError("public store overlaps managed namespace")
    try:
        snapshot = read_public_memory_release_snapshot(source, tenant_id=tenant_id, repository_id=repository_id)
    except PublicMemorySeparationError as error:
        raise CognitiveProjectionError(f"public release snapshot failed: {error}") from error
    desired, manifest = _desired(snapshot, tenant_id, repository_id)
    repository_identity_digest = snapshot.repository_identity_digest
    if not isinstance(repository_identity_digest, str):
        raise CognitiveProjectionError("repository identity digest is unavailable")
    manifest_digest = _digest_bytes(desired[MANIFEST_NAME])
    tree_digest = _digest_document(
        {
            rel: _digest_bytes(content)
            for rel, content in sorted(desired.items())
        }
    )
    common = {
        "schema_version": "hive-cognitive-result/v1",
        "tenant_id": tenant_id,
        "repository_id": repository_id,
        "repository_identity_digest": repository_identity_digest,
        "namespace_path": str(root),
        "manifest_digest": manifest_digest,
        "source_cursor": manifest["source_cursor"],
        "tree_digest": tree_digest,
        "source_record_count": snapshot.source_record_count,
        "projected_record_count": manifest["note_counts"]["total"],
        "note_counts": manifest["note_counts"],
    }
    if check:
        _validate_protected_tree(state)
        prior, prior_manifest, owned = _manifest_state(
            root,
            state,
            tenant_id,
            repository_id,
            repository_identity_digest,
        )
        conflicts = _conflicts(root, desired, prior, prior_manifest, owned)
        return CognitiveProjectionResult(
            status=(
                "conflict"
                if conflicts
                else ("unchanged" if _matches(root, desired) else "drift")
            ),
            recovery_status="read-only",
            conflict_paths=conflicts,
            **common,
        )
    if (
        authority is None
        or not authority_decision_is_authentic(authority)
        or not authority.allowed
        or authority.foundation_action != "foundation.projection.write"
        or authority.tenant_id != tenant_id
        or authority.repository_id != repository_id
    ):
        raise CognitiveProjectionError("projection authority does not allow this scope")
    with _lock(state):
        try:
            prior, prior_manifest, owned = _manifest_state(
                root,
                state,
                tenant_id,
                repository_id,
                repository_identity_digest,
            )
        except CognitiveProjectionError:
            if not (state / "transactions").exists():
                raise
            prior, prior_manifest, owned = {}, None, False
        try:
            recovered_receipt = _recover_pending_transactions(
                root,
                state,
                authority,
                tenant_id=tenant_id,
                repository_id=repository_id,
                repository_identity_digest=repository_identity_digest,
            )
        except CognitiveProjectionConflict as conflict:
            conflict_receipt = _preserve_conflict(
                root,
                state,
                desired,
                prior,
                prior_manifest,
                conflict.paths,
                authority,
            )
            return CognitiveProjectionResult(
                status="conflict",
                recovery_status="conflict-preserved",
                conflict_paths=conflict.paths,
                receipt_path=conflict_receipt,
                **common,
            )
        prior, prior_manifest, owned = _manifest_state(
            root,
            state,
            tenant_id,
            repository_id,
            repository_identity_digest,
        )
        conflicts = _conflicts(root, desired, prior, prior_manifest, owned)
        if conflicts:
            conflict_receipt = _preserve_conflict(
                root,
                state,
                desired,
                prior,
                prior_manifest,
                conflicts,
                authority,
            )
            return CognitiveProjectionResult(
                status="conflict",
                recovery_status="conflict-preserved",
                conflict_paths=conflicts,
                receipt_path=conflict_receipt,
                **common,
            )
        if _matches(root, desired):
            return CognitiveProjectionResult(
                status="projected" if recovered_receipt else "unchanged",
                recovery_status="recovered" if recovered_receipt else "not-required",
                receipt_path=recovered_receipt,
                **common,
            )
        try:
            receipt = _publish(
                root,
                state,
                desired,
                manifest,
                prior,
                prior_manifest,
                authority,
                fail_after_replacements,
            )
        except CognitiveProjectionConflict as conflict:
            conflict_receipt = _preserve_conflict(
                root,
                state,
                desired,
                prior,
                prior_manifest,
                conflict.paths,
                authority,
            )
            return CognitiveProjectionResult(
                status="conflict",
                recovery_status="conflict-preserved",
                conflict_paths=conflict.paths,
                receipt_path=conflict_receipt,
                **common,
            )
        return CognitiveProjectionResult(
            status="projected",
            recovery_status="recovered" if recovered_receipt else "committed",
            receipt_path=receipt,
            **common,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m hive_mind_os.foundation.cognitive")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("project", "check"):
        item = commands.add_parser(name)
        item.add_argument("--public-store", required=True)
        item.add_argument("--repo", required=True)
        item.add_argument("--protected-state", required=True)
        item.add_argument("--tenant", required=True)
        item.add_argument("--repository-id", required=True)
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    check = args.command == "check"
    authority = None if check else decide_foundation_write(
        role=Role.BUILDER,
        action="foundation.projection.write",
        policy_decision=PolicyDecision(True, "explicit local cognitive projection"),
        lease_actions={"foundation.projection.write"},
        adapter_actions={"foundation.projection.write"},
        mission_risk_allowed=True,
        budget_available=True,
        tenant_id=args.tenant,
        repository_id=args.repository_id,
        actor_id="foundation-cognitive-projector-v1",
        decision_id="decision:explicit-local-cognitive-projection",
        lease_id="lease:single-local-cognitive-projection",
    )
    try:
        result = project_cognitive_notes(args.public_store, args.repo, args.protected_state, tenant_id=args.tenant, repository_id=args.repository_id, check=check, authority=authority)
    except (CognitiveProjectionError, OSError, ValueError, sqlite3.Error) as error:
        failure = CognitiveProjectionFailure("hive-cognitive-failure/v1", "failed", f"{type(error).__name__}: {error}"[:8192])
        print(json.dumps(failure.to_dict(), indent=2, sort_keys=True), file=sys.stderr)
        return 2
    stream = sys.stderr if result.status in {"drift", "conflict"} else sys.stdout
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True), file=stream)
    return 1 if result.status in {"drift", "conflict"} else 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
