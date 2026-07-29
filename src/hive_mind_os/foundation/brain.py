from __future__ import annotations

import argparse
import json
import os
import re
import shutil
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
from .brain_contracts import validate_projection
from .canonical import canonical_bytes
from .store import FoundationStore, PublicMemorySnapshot

PACK_SCHEMA_VERSION = "hive-brain-pack/v1"
PROJECTION_CONTRACT = "hive-obsidian-projection/v1"
PROJECTOR_VERSION = "hive-brain-projection/v1"
PACK_DIRECTORY = "hive-mind"
GENERATED_DIRECTORY = "generated"
STATE_DIRECTORY = ".hive-mind-projection-state"
MANIFEST_PATH = f"{GENERATED_DIRECTORY}/manifest.json"
README_PATH = f"{GENERATED_DIRECTORY}/README.md"
MAX_RECORDS = 100_000
MAX_LIST_ITEMS = 256
MAX_STRING_LENGTH = 4_096
MAX_NOTE_BYTES = 1_048_576
MAX_PACK_BYTES = 268_435_456
MAX_MANIFEST_BYTES = 16_777_216

_SAFE_COMPONENT = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_BIDI_CONTROLS = frozenset(
    {
        "\u061c",
        "\u200e",
        "\u200f",
        "\u202a",
        "\u202b",
        "\u202c",
        "\u202d",
        "\u202e",
        "\u2066",
        "\u2067",
        "\u2068",
        "\u2069",
    }
)
_PUBLIC_MEMORY_FIELDS = (
    "record_type",
    "schema_version",
    "memory_id",
    "memory_kind",
    "repository_id",
    "tenant_id",
    "mission_id",
    "run_id",
    "step_id",
    "actor_id",
    "payload_digest",
    "previous_record_id",
    "supersedes_record_id",
    "observed_at",
    "recorded_at",
    "causation_id",
    "correlation_id",
    "source_refs",
    "claim_refs",
    "evidence_refs",
    "court_refs",
    "code_receipt_refs",
    "generation_refs",
    "status",
    "confidence_ppm",
    "freshness_expires_at",
    "contradiction_refs",
    "relation_refs",
    "owner_id",
    "sensitivity",
    "access_purpose",
    "retention",
    "deletion_policy",
    "quarantine_state",
    "appeal_state",
    "content_digest",
)


class ProjectionError(RuntimeError):
    """Raised when a projection cannot proceed without weakening its contract."""


class ProjectionConflictError(ProjectionError):
    """Raised when the generated namespace changes during publication."""

    def __init__(self, conflict_paths: Sequence[str]) -> None:
        self.conflict_paths = tuple(sorted(set(conflict_paths)))
        super().__init__(
            "projection conflict during publication: "
            + ", ".join(self.conflict_paths)
        )


@dataclass(frozen=True, slots=True)
class ProjectionResult:
    schema_version: str
    status: str
    tenant_id: str
    repository_id: str
    repository_identity_digest: str
    pack_path: str
    manifest_digest: str
    source_cursor: str
    tree_digest: str
    source_record_count: int
    projected_record_count: int
    omitted_sensitive_count: int
    omitted_unsupported_count: int
    omitted_quarantined_count: int
    recovery_status: str
    conflict_paths: tuple[str, ...] = ()
    receipt_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        document = asdict(self)
        document["conflict_paths"] = list(self.conflict_paths)
        validation = validate_projection("brain-result-v1", document)
        if not validation.valid:
            raise ProjectionError(
                "projection result contract failed: "
                + "; ".join(validation.issues)
            )
        return document


@dataclass(frozen=True, slots=True)
class ProjectionFailure:
    schema_version: str
    status: str
    error: str

    def to_dict(self) -> dict[str, str]:
        document = asdict(self)
        validation = validate_projection("brain-failure-v1", document)
        if not validation.valid:
            raise ProjectionError(
                "projection failure contract failed: "
                + "; ".join(validation.issues)
            )
        return document


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _digest_document(value: Any) -> str:
    return _digest_bytes(canonical_bytes(value))


def _is_linklike(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction) and is_junction():
        return True
    try:
        attributes = getattr(
            path.stat(follow_symlinks=False),
            "st_file_attributes",
            0,
        )
    except (FileNotFoundError, OSError):
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attributes & reparse_flag)


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _write_durable(path: Path, content: bytes) -> None:
    if path.exists() and (not path.is_file() or _is_linklike(path)):
        raise ProjectionError(f"durable write target is unsafe: {path.name}")
    with path.open("wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _yaml_scalar(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _validate_render_value(value: Any, path: str) -> Any:
    if isinstance(value, str):
        if len(value) > MAX_STRING_LENGTH:
            raise ProjectionError(f"{path}: string exceeds projection bound")
        if unicodedata.normalize("NFC", value) != value:
            raise ProjectionError(f"{path}: string is not NFC-normalized")
        if any(character in _BIDI_CONTROLS for character in value):
            raise ProjectionError(f"{path}: bidirectional control is prohibited")
        if any(
            unicodedata.category(character) in {"Cc", "Cs"}
            and character not in {"\t", "\n", "\r"}
            for character in value
        ):
            raise ProjectionError(f"{path}: control character is prohibited")
        return value
    if isinstance(value, list):
        if len(value) > MAX_LIST_ITEMS:
            raise ProjectionError(f"{path}: list exceeds projection bound")
        return [
            _validate_render_value(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if value is None or type(value) in {bool, int, float}:
        return value
    raise ProjectionError(f"{path}: unsupported projected value")


def _public_memory_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if set(payload) - set(_PUBLIC_MEMORY_FIELDS) != {"protected_content_ref", "retrieval_receipt"}:
        raise ProjectionError("memory payload fields differ from the projection allowlist")
    projected = {
        field: _validate_render_value(payload[field], f"payload.{field}")
        for field in _PUBLIC_MEMORY_FIELDS
    }
    return projected


def _safe_record_type(value: object) -> str:
    record_type = str(value)
    if _SAFE_COMPONENT.fullmatch(record_type) is None:
        raise ProjectionError(f"unsafe record type: {record_type!r}")
    return record_type


def _record_path(record: Mapping[str, Any]) -> str:
    record_type = _safe_record_type(record["record_type"])
    record_key = sha256(str(record["record_id"]).encode("utf-8")).hexdigest()
    return f"{GENERATED_DIRECTORY}/records/{record_type}/{record_key}.md"


def _projection_cursor(records: Sequence[Mapping[str, Any]]) -> str:
    eligible = [
        {
            "record_id": str(record["record_id"]),
            "semantic_digest": str(record["semantic_digest"]),
        }
        for record in sorted(records, key=lambda item: str(item["record_id"]))
    ]
    return f"memory-set:{_digest_document(eligible).removeprefix('sha256:')}"


def _render_note(record: Mapping[str, Any], cursor: str) -> bytes:
    payload = record["payload"]
    if not isinstance(payload, Mapping):
        raise ProjectionError(f"{record['record_id']}: payload is not an object")
    public_payload = _public_memory_payload(payload)
    sensitivity_decision = {
        "sensitivity": record["sensitivity"],
        "public_release_decision_id": record["public_release_decision_id"],
        "public_release_decided_by": record["public_release_decided_by"],
        "public_release_subject_digest": record["public_release_subject_digest"],
    }
    frontmatter = {
        "schema_version": PROJECTION_CONTRACT,
        "note_id": "brain-note:"
        + sha256(str(record["record_id"]).encode("utf-8")).hexdigest(),
        "record_id": record["record_id"],
        "record_type": record["record_type"],
        "tenant_id": record["tenant_id"],
        "repository_id": record["repository_id"],
        "run_id": payload.get("run_id"),
        "actor_id": record["actor_id"],
        "observed_at": record["observed_at"],
        "recorded_at": record["recorded_at"],
        "status": payload.get("status", record["status"]),
        "source_event_status": record["status"],
        "sensitivity": record["sensitivity"],
        "source_schema": record["schema_name"],
        "source_digest": record["semantic_digest"],
        "source_previous_digest": record["previous_digest"],
        "public_release_decision_id": record["public_release_decision_id"],
        "public_release_decided_by": record["public_release_decided_by"],
        "sensitivity_decision_digest": _digest_document(sensitivity_decision),
        "redaction_receipt_digest": _digest_document(
            {
                "omitted_fields": [
                    "protected_content_ref",
                    "retrieval_receipt",
                ],
                "policy": "phase3-public-memory-metadata-v1",
            }
        ),
        "projection_cursor": cursor,
        "generator_version": PROJECTOR_VERSION,
        "is_generated": True,
        "is_authoritative": False,
    }
    validation = validate_projection("brain-note-v1", frontmatter)
    if not validation.valid:
        raise ProjectionError(
            f"{record['record_id']}: note contract failed: "
            + "; ".join(validation.issues)
        )
    lines = ["---"]
    lines.extend(
        f"{key}: {_yaml_scalar(_validate_render_value(value, f'frontmatter.{key}'))}"
        for key, value in frontmatter.items()
    )
    lines.extend(
        [
            "---",
            "",
            "# Generated memory record",
            "",
            "> This file is a deterministic, read-only projection. The append-only",
            "> Foundation store remains authoritative. Do not place human proposals here.",
            "",
            "## Canonical safe-public payload",
            "",
        ]
    )
    payload_text = json.dumps(
        public_payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    )
    lines.extend(f"    {line}" for line in payload_text.splitlines())
    lines.append("")
    content = "\n".join(lines).encode("utf-8")
    if len(content) > MAX_NOTE_BYTES:
        raise ProjectionError(f"{record['record_id']}: note exceeds projection bound")
    return content


def _render_readme(
    *,
    tenant_id: str,
    repository_id: str,
    cursor: str,
    safe_public_count: int,
) -> bytes:
    lines = [
        "---",
        f"schema_version: {_yaml_scalar(PROJECTION_CONTRACT)}",
        f"tenant_id: {_yaml_scalar(_validate_render_value(tenant_id, 'tenant_id'))}",
        "repository_id: "
        + _yaml_scalar(_validate_render_value(repository_id, "repository_id")),
        f"projection_cursor: {_yaml_scalar(cursor)}",
        f"generator_version: {_yaml_scalar(PROJECTOR_VERSION)}",
        f"safe_public_record_count: {safe_public_count}",
        "is_generated: true",
        "is_authoritative: false",
        "---",
        "",
        "# Hive Mind open memory pack",
        "",
        "This directory is a deterministic, read-only projection of explicitly released",
        "safe-public records. The append-only Foundation store remains authoritative.",
        "",
        "It works with an ordinary filesystem, Git, any Markdown editor, and Obsidian",
        "without an account, paid service, importer, community plugin, or network.",
        "",
        "Do not edit files under `generated/`. Put human notes outside that namespace.",
        "No Inbox or write-back path is active in this phase.",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _desired_pack(
    snapshot: PublicMemorySnapshot,
    *,
    tenant_id: str,
    repository_id: str,
) -> tuple[dict[str, bytes], dict[str, Any], int]:
    records = snapshot.records
    if len(records) > MAX_RECORDS:
        raise ProjectionError("eligible record count exceeds projection bound")
    safe_public: list[Mapping[str, Any]] = []
    omitted_quarantined = 0
    for record in records:
        payload = record["payload"]
        if not isinstance(payload, Mapping):
            raise ProjectionError(f"{record['record_id']}: payload is not an object")
        if payload.get("status") == "quarantined" or payload.get("quarantine_state") != "none":
            omitted_quarantined += 1
            continue
        source_digest = str(record["semantic_digest"])
        if (
            record["schema_name"] != "memory-record-v1"
            or record["record_type"] != "memory-record"
            or payload.get("sensitivity") != "safe-public"
            or _DIGEST.fullmatch(source_digest) is None
            or record["public_release_decision_id"] is None
            or record["public_release_decided_by"] is None
            or record["public_release_subject_digest"] != source_digest
        ):
            raise ProjectionError(
                f"{record['record_id']}: safe-public release provenance is invalid"
            )
        safe_public.append(record)
    safe_public.sort(key=lambda item: str(item["record_id"]))
    cursor = _projection_cursor(safe_public)
    files: dict[str, bytes] = {}
    file_entries: list[dict[str, str]] = []
    for record in safe_public:
        relative_path = _record_path(record)
        content = _render_note(record, cursor)
        files[relative_path] = content
        file_entries.append(
            {
                "path": relative_path,
                "record_id": str(record["record_id"]),
                "source_digest": str(record["semantic_digest"]),
                "content_digest": _digest_bytes(content),
            }
        )
    readme = _render_readme(
        tenant_id=tenant_id,
        repository_id=repository_id,
        cursor=cursor,
        safe_public_count=len(safe_public),
    )
    files[README_PATH] = readme
    file_entries.append(
        {
            "path": README_PATH,
            "record_id": "pack-readme",
            "source_digest": _digest_document(
                {
                    "cursor": cursor,
                    "tenant_id": tenant_id,
                    "repository_id": repository_id,
                    "safe_public_count": len(safe_public),
                }
            ),
            "content_digest": _digest_bytes(readme),
        }
    )
    source_receipt = [
        {
            "record_id": record["record_id"],
            "semantic_digest": record["semantic_digest"],
        }
        for record in sorted(safe_public, key=lambda item: str(item["record_id"]))
    ]
    manifest = {
        "schema_version": PACK_SCHEMA_VERSION,
        "projection_contract": PROJECTION_CONTRACT,
        "projector_version": PROJECTOR_VERSION,
        "tenant_id": tenant_id,
        "repository_id": repository_id,
        "repository_identity_digest": snapshot.repository_identity_digest,
        "foundation_schema_version": snapshot.schema_version,
        "foundation_schema_digest": snapshot.schema_digest,
        "source_cursor": cursor,
        "source_digest": _digest_document(source_receipt),
        "source_recorded_through": max(
            (str(record["recorded_at"]) for record in safe_public),
            default=None,
        ),
        "safe_public_record_count": len(safe_public),
        "generated_namespace": GENERATED_DIRECTORY,
        "files": sorted(file_entries, key=lambda item: item["path"]),
    }
    validation = validate_projection("brain-manifest-v1", manifest)
    if not validation.valid:
        raise ProjectionError(
            "projection manifest contract failed: " + "; ".join(validation.issues)
        )
    files[MANIFEST_PATH] = _json_bytes(manifest)
    if sum(len(content) for content in files.values()) > MAX_PACK_BYTES:
        raise ProjectionError("memory pack exceeds projection bound")
    return files, manifest, omitted_quarantined


def _path_from_relative(root: Path, relative_path: str) -> Path:
    if "\\" in relative_path:
        raise ProjectionError(f"non-portable projection path: {relative_path}")
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ProjectionError(f"unsafe projection path: {relative_path}")
    absolute_root = root.absolute()
    resolved_root = root.resolve(strict=False)
    if resolved_root != absolute_root:
        raise ProjectionError("projection root is linked or escaped")
    candidate = root.joinpath(*relative.parts)
    if candidate.resolve(strict=False).is_relative_to(resolved_root) is False:
        raise ProjectionError(f"projection path escapes pack: {relative_path}")
    return candidate


def _validate_projection_roots(
    repository_root: Path,
    *,
    pack_root: Path,
    state_root: Path | None = None,
) -> None:
    if (
        not repository_root.is_dir()
        or _is_linklike(repository_root)
        or repository_root.resolve(strict=True) != repository_root
    ):
        raise ProjectionError("repository root changed during projection")
    for label, root in (("memory pack", pack_root), ("projection state", state_root)):
        if root is None or not root.exists():
            continue
        if not root.is_dir() or _is_linklike(root):
            raise ProjectionError(f"{label} path must be a regular directory")
        if root.resolve(strict=True) != root:
            raise ProjectionError(f"{label} path escaped the repository")


def _reject_source_overlap(source: Path, pack_root: Path) -> None:
    if not pack_root.exists():
        return
    for directory, directory_names, file_names in os.walk(
        pack_root,
        followlinks=False,
    ):
        current = Path(directory)
        safe_directories: list[str] = []
        for name in directory_names:
            child = current / name
            if not _is_linklike(child):
                safe_directories.append(name)
        directory_names[:] = safe_directories
        for name in file_names:
            candidate = current / name
            if _is_linklike(candidate) or not candidate.is_file():
                continue
            try:
                overlaps = candidate.samefile(source)
            except OSError:
                overlaps = False
            if overlaps:
                raise ProjectionError(
                    "foundation store cannot overlap the public memory pack"
                )


def _validate_state_tree(state_root: Path) -> None:
    if not state_root.exists():
        return
    for directory, directory_names, file_names in os.walk(
        state_root,
        followlinks=False,
    ):
        current = Path(directory)
        for name in (*directory_names, *file_names):
            candidate = current / name
            if _is_linklike(candidate):
                raise ProjectionError(
                    "projection state contains a linked or reparse path"
                )


def _expected_generated_directories(
    desired_files: Mapping[str, bytes],
) -> set[str]:
    expected = {GENERATED_DIRECTORY}
    for relative_path in desired_files:
        parent = Path(relative_path).parent
        while parent.as_posix() not in {".", ""}:
            expected.add(parent.as_posix())
            parent = parent.parent
    return expected


def _read_manifest(pack_root: Path) -> tuple[dict[str, Any] | None, str | None]:
    path = _path_from_relative(pack_root, MANIFEST_PATH)
    if not path.exists():
        return None, None
    if not path.is_file() or _is_linklike(path):
        raise ProjectionError("projection manifest is not a regular file")
    content = path.read_bytes()
    if len(content) > MAX_MANIFEST_BYTES:
        raise ProjectionError("projection manifest exceeds the size bound")
    try:
        manifest = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProjectionError(f"projection manifest is invalid: {error}") from error
    if not isinstance(manifest, dict):
        raise ProjectionError("projection manifest is not an object")
    return manifest, _digest_bytes(content)


def _manifest_files(
    manifest: Mapping[str, Any] | None,
    *,
    tenant_id: str,
    repository_id: str,
    repository_identity_digest: str,
) -> dict[str, str]:
    if manifest is None:
        return {}
    validation = validate_projection("brain-manifest-v1", manifest)
    if not validation.valid:
        raise ProjectionError(
            "existing projection manifest contract failed: "
            + "; ".join(validation.issues)
        )
    for field, expected in (
        ("schema_version", PACK_SCHEMA_VERSION),
        ("projection_contract", PROJECTION_CONTRACT),
        ("projector_version", PROJECTOR_VERSION),
        ("tenant_id", tenant_id),
        ("repository_id", repository_id),
        ("repository_identity_digest", repository_identity_digest),
        ("generated_namespace", GENERATED_DIRECTORY),
    ):
        if manifest.get(field) != expected:
            raise ProjectionError(f"manifest {field} does not match this projection")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise ProjectionError("manifest files must be a list")
    observed: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ProjectionError("manifest file entry is not an object")
        path = entry.get("path")
        content_digest = entry.get("content_digest")
        if (
            not isinstance(path, str)
            or not isinstance(content_digest, str)
            or _DIGEST.fullmatch(content_digest) is None
            or path == MANIFEST_PATH
            or path in observed
        ):
            raise ProjectionError("manifest contains an invalid file entry")
        observed[path] = content_digest
    return observed


def _manifest_has_receipt(
    state_root: Path,
    manifest_digest: str | None,
) -> bool:
    if manifest_digest is None:
        return False
    transaction_id = manifest_digest.removeprefix("sha256:")
    receipt_path = _path_from_relative(
        state_root,
        f"receipts/{transaction_id}.json",
    )
    if not receipt_path.exists():
        return False
    if not receipt_path.is_file() or _is_linklike(receipt_path):
        raise ProjectionError("projection ownership receipt is unsafe")
    try:
        receipt = json.loads(receipt_path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProjectionError("projection ownership receipt is invalid") from error
    validation = validate_projection("brain-receipt-v1", receipt)
    if not validation.valid:
        raise ProjectionError(
            "projection ownership receipt contract failed: "
            + "; ".join(validation.issues)
        )
    if (
        receipt.get("transaction_id") != transaction_id
        or receipt.get("desired_manifest_digest") != manifest_digest
        or receipt.get("verified_manifest_digest") != manifest_digest
    ):
        raise ProjectionError("projection ownership receipt does not match manifest")
    return True


def _find_conflicts(
    pack_root: Path,
    desired_files: Mapping[str, bytes],
    prior_files: Mapping[str, str],
    *,
    manifest_owned: bool,
    prior_manifest_digest: str | None,
) -> tuple[str, ...]:
    conflicts: set[str] = set()
    generated_root = pack_root / GENERATED_DIRECTORY
    if generated_root.exists() and _is_linklike(generated_root):
        raise ProjectionError("generated namespace cannot be a symbolic link")
    if generated_root.exists():
        expected_directories = _expected_generated_directories(desired_files)
        for path in generated_root.rglob("*"):
            if _is_linklike(path):
                conflicts.add(path.relative_to(pack_root).as_posix())
            elif path.is_dir():
                relative = path.relative_to(pack_root).as_posix()
                if relative not in expected_directories:
                    conflicts.add(relative)
            elif path.is_file():
                relative = path.relative_to(pack_root).as_posix()
                expected_digest = (
                    prior_manifest_digest
                    if relative == MANIFEST_PATH and manifest_owned
                    else prior_files.get(relative)
                )
                if expected_digest is None:
                    desired = desired_files.get(relative)
                    if desired is None or _digest_bytes(path.read_bytes()) != _digest_bytes(
                        desired
                    ):
                        conflicts.add(relative)
                else:
                    desired = desired_files.get(relative)
                    desired_digest = (
                        None if desired is None else _digest_bytes(desired)
                    )
                    actual_digest = _digest_bytes(path.read_bytes())
                    if actual_digest not in {expected_digest, desired_digest}:
                        conflicts.add(relative)
    for relative_path, expected_digest in prior_files.items():
        destination = _path_from_relative(pack_root, relative_path)
        if not destination.is_file() or _is_linklike(destination):
            conflicts.add(relative_path)
        else:
            actual_digest = _digest_bytes(destination.read_bytes())
            desired = desired_files.get(relative_path)
            desired_digest = None if desired is None else _digest_bytes(desired)
            if actual_digest not in {expected_digest, desired_digest}:
                conflicts.add(relative_path)
        if relative_path not in desired_files:
            conflicts.add(relative_path)
    return tuple(sorted(conflicts))


def _prior_projection_state(
    *,
    pack_root: Path,
    state_root: Path,
    desired_files: Mapping[str, bytes],
    tenant_id: str,
    repository_id: str,
    repository_identity_digest: str,
) -> tuple[dict[str, str], str | None, tuple[str, ...]]:
    try:
        prior_manifest, prior_manifest_digest = _read_manifest(pack_root)
    except ProjectionError:
        manifest_path = _path_from_relative(pack_root, MANIFEST_PATH)
        observed_digest = (
            _digest_bytes(manifest_path.read_bytes())
            if manifest_path.is_file() and not _is_linklike(manifest_path)
            else None
        )
        return {}, observed_digest, (MANIFEST_PATH,)
    manifest_owned = _manifest_has_receipt(state_root, prior_manifest_digest)
    prior_files = (
        _manifest_files(
            prior_manifest,
            tenant_id=tenant_id,
            repository_id=repository_id,
            repository_identity_digest=repository_identity_digest,
        )
        if manifest_owned
        else {}
    )
    conflicts = _find_conflicts(
        pack_root,
        desired_files,
        prior_files,
        manifest_owned=manifest_owned,
        prior_manifest_digest=prior_manifest_digest,
    )
    return prior_files, prior_manifest_digest, conflicts


def _pack_matches(
    pack_root: Path,
    desired_files: Mapping[str, bytes],
) -> bool:
    generated_root = pack_root / GENERATED_DIRECTORY
    if not generated_root.is_dir() or _is_linklike(generated_root):
        return False
    expected_files = set(desired_files)
    expected_directories = _expected_generated_directories(desired_files)
    observed_files: set[str] = set()
    observed_directories = {GENERATED_DIRECTORY}
    for path in generated_root.rglob("*"):
        relative = path.relative_to(pack_root).as_posix()
        if _is_linklike(path):
            return False
        if path.is_file():
            observed_files.add(relative)
        elif path.is_dir():
            observed_directories.add(relative)
        else:
            return False
    if (
        observed_files != expected_files
        or not observed_directories.issubset(expected_directories)
    ):
        return False
    for relative_path, desired in desired_files.items():
        destination = _path_from_relative(pack_root, relative_path)
        if (
            not destination.is_file()
            or _is_linklike(destination)
            or _digest_bytes(destination.read_bytes()) != _digest_bytes(desired)
        ):
            return False
    return True


def _require_projection_authority(
    authority: AuthorityDecision | None,
    *,
    tenant_id: str,
    repository_id: str,
) -> AuthorityDecision:
    if authority is None or not authority_decision_is_authentic(authority):
        raise ProjectionError("projection authority decision is not authentic")
    if (
        not authority.allowed
        or authority.foundation_action != "foundation.projection.write"
        or authority.tenant_id != tenant_id
        or authority.repository_id != repository_id
        or not authority.actor_id
        or not authority.decision_id
        or not authority.lease_id
    ):
        raise ProjectionError("projection authority does not allow this scope")
    return authority


def _staged_path(staged_root: Path, relative_path: str) -> Path:
    name = sha256(relative_path.encode("utf-8")).hexdigest()
    return _path_from_relative(staged_root, f"{name}.tmp")


@contextmanager
def _projection_lock(state_root: Path) -> Iterator[None]:
    state_root.mkdir(parents=True, exist_ok=True)
    if not state_root.is_dir() or _is_linklike(state_root):
        raise ProjectionError("projection state path must be a regular directory")
    lock_path = _path_from_relative(state_root, "projection.lock")
    handle = lock_path.open("a+b")
    try:
        handle.seek(0)
        if handle.read(1) == b"":
            handle.seek(0)
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ProjectionError("another projector holds the repository lock") from error
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


def _write_transaction(
    *,
    repository_root: Path,
    pack_root: Path,
    desired_files: Mapping[str, bytes],
    prior_files: Mapping[str, str],
    prior_manifest_digest: str | None,
    desired_manifest_digest: str,
    authority: AuthorityDecision,
    fail_after_replacements: int | None,
) -> tuple[str, str]:
    state_root = repository_root / STATE_DIRECTORY
    transaction_id = desired_manifest_digest.removeprefix("sha256:")
    transaction_root = _path_from_relative(
        state_root,
        f"transactions/{transaction_id}",
    )
    staged_root = _path_from_relative(
        state_root,
        f"transactions/{transaction_id}/files",
    )
    receipt_root = _path_from_relative(state_root, "receipts")
    receipt_path = _path_from_relative(
        state_root,
        f"receipts/{transaction_id}.json",
    )
    if receipt_path.exists():
        if _pack_matches(pack_root, desired_files):
            if transaction_root.exists():
                if not transaction_root.is_dir() or _is_linklike(transaction_root):
                    raise ProjectionError("stale transaction path is unsafe")
                shutil.rmtree(transaction_root)
            transactions_root = _path_from_relative(state_root, "transactions")
            if transactions_root.exists() and not any(transactions_root.iterdir()):
                transactions_root.rmdir()
            return (
                receipt_path.relative_to(repository_root).as_posix(),
                "already-committed",
            )
        raise ProjectionError("completed projection receipt disagrees with the pack")
    stable_journal = {
        "schema_version": "hive-brain-projection-transaction/v1",
        "transaction_id": transaction_id,
        "pack_path": PACK_DIRECTORY,
        "prior_manifest_digest": prior_manifest_digest,
        "desired_manifest_digest": desired_manifest_digest,
        "authority_decision_id": authority.decision_id,
        "authority_actor_id": authority.actor_id,
        "authority_lease_id": authority.lease_id,
        "operations": [
            {
                "path": relative_path,
                "expected_prior_digest": (
                    prior_manifest_digest
                    if relative_path == MANIFEST_PATH
                    else prior_files.get(relative_path)
                ),
                "desired_digest": _digest_bytes(content),
            }
            for relative_path, content in sorted(desired_files.items())
        ],
    }
    journal_path = _path_from_relative(
        state_root,
        f"transactions/{transaction_id}/transaction.json",
    )
    recovering = journal_path.exists()
    if recovering:
        try:
            journal = json.loads(journal_path.read_bytes())
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProjectionError("pending projection journal is invalid") from error
        comparable = dict(journal) if isinstance(journal, dict) else {}
        comparable.pop("attempted_at", None)
        if comparable != stable_journal:
            raise ProjectionError("pending projection transaction is inconsistent")
    else:
        journal = {**stable_journal, "attempted_at": utc_now()}
    validation = validate_projection("brain-transaction-v1", journal)
    if not validation.valid:
        raise ProjectionError(
            "projection transaction contract failed: "
            + "; ".join(validation.issues)
        )
    journal_bytes = _json_bytes(journal)
    if not recovering:
        staged_root.mkdir(parents=True, exist_ok=False)
        for relative_path, content in desired_files.items():
            staged = _staged_path(staged_root, relative_path)
            _write_durable(staged, content)
        _write_durable(journal_path, journal_bytes)
    replacements = 0
    ordered_paths = sorted(
        desired_files,
        key=lambda path: (path == MANIFEST_PATH, path),
    )
    late_conflicts = _find_conflicts(
        pack_root,
        desired_files,
        prior_files,
        manifest_owned=prior_manifest_digest is not None,
        prior_manifest_digest=prior_manifest_digest,
    )
    if late_conflicts:
        raise ProjectionConflictError(late_conflicts)
    for relative_path in ordered_paths:
        if relative_path == MANIFEST_PATH:
            late_conflicts = _find_conflicts(
                pack_root,
                desired_files,
                prior_files,
                manifest_owned=prior_manifest_digest is not None,
                prior_manifest_digest=prior_manifest_digest,
            )
            if late_conflicts:
                raise ProjectionConflictError(late_conflicts)
        desired = desired_files[relative_path]
        desired_digest = _digest_bytes(desired)
        destination = _path_from_relative(pack_root, relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if not destination.is_file() or _is_linklike(destination):
                raise ProjectionError(f"projection target is unsafe: {relative_path}")
            actual_digest = _digest_bytes(destination.read_bytes())
        else:
            actual_digest = None
        expected_digest = (
            prior_manifest_digest
            if relative_path == MANIFEST_PATH
            else prior_files.get(relative_path)
        )
        if actual_digest == desired_digest:
            continue
        if actual_digest != expected_digest:
            raise ProjectionError(
                f"projection conflict at {relative_path}: expected "
                f"{expected_digest}, observed {actual_digest}"
            )
        staged = _staged_path(staged_root, relative_path)
        if not staged.is_file() or _digest_bytes(staged.read_bytes()) != desired_digest:
            raise ProjectionError(f"staged projection content is invalid: {relative_path}")
        os.replace(staged, destination)
        replacements += 1
        if fail_after_replacements is not None and replacements >= fail_after_replacements:
            raise InterruptedError("injected projection interruption")
    if not _pack_matches(pack_root, desired_files):
        late_conflicts = _find_conflicts(
            pack_root,
            desired_files,
            prior_files,
            manifest_owned=prior_manifest_digest is not None,
            prior_manifest_digest=prior_manifest_digest,
        )
        if late_conflicts:
            raise ProjectionConflictError(late_conflicts)
        raise ProjectionError("projection verification failed after replacement")
    receipt = {
        **journal,
        "schema_version": "hive-brain-projection-receipt/v1",
        "status": "committed",
        "committed_at": utc_now(),
        "verified_manifest_digest": desired_manifest_digest,
    }
    validation = validate_projection("brain-receipt-v1", receipt)
    if not validation.valid:
        raise ProjectionError(
            "projection receipt contract failed: " + "; ".join(validation.issues)
        )
    receipt_root.mkdir(parents=True, exist_ok=True)
    temporary_receipt = _path_from_relative(
        state_root,
        f"transactions/{transaction_id}/receipt.json",
    )
    _write_durable(temporary_receipt, _json_bytes(receipt))
    os.replace(temporary_receipt, receipt_path)
    shutil.rmtree(transaction_root)
    transactions_root = _path_from_relative(state_root, "transactions")
    if transactions_root.exists() and not any(transactions_root.iterdir()):
        transactions_root.rmdir()
    return (
        receipt_path.relative_to(repository_root).as_posix(),
        "recovered" if recovering else "committed",
    )


def _preserve_conflict(
    *,
    repository_root: Path,
    pack_root: Path,
    desired_files: Mapping[str, bytes],
    prior_files: Mapping[str, str],
    prior_manifest_digest: str | None,
    desired_manifest_digest: str,
    conflict_paths: Sequence[str],
    authority: AuthorityDecision,
) -> str:
    state_root = repository_root / STATE_DIRECTORY
    observations = []
    for relative_path in conflict_paths:
        destination = _path_from_relative(pack_root, relative_path)
        observed_digest = (
            _digest_bytes(destination.read_bytes())
            if destination.is_file() and not _is_linklike(destination)
            else None
        )
        desired = desired_files.get(relative_path)
        observations.append(
            {
                "path": relative_path,
                "expected_prior_digest": (
                    prior_manifest_digest
                    if relative_path == MANIFEST_PATH
                    else prior_files.get(relative_path)
                ),
                "observed_digest": observed_digest,
                "desired_digest": None if desired is None else _digest_bytes(desired),
            }
        )
    stable_body = {
        "schema_version": "hive-brain-projection-conflict/v1",
        "status": "conflict",
        "prior_manifest_digest": prior_manifest_digest,
        "desired_manifest_digest": desired_manifest_digest,
        "authority_decision_id": authority.decision_id,
        "authority_actor_id": authority.actor_id,
        "authority_lease_id": authority.lease_id,
        "conflicts": observations,
    }
    conflict_id = _digest_document(stable_body).removeprefix("sha256:")
    receipt_path = _path_from_relative(
        state_root,
        f"conflicts/{conflict_id}/receipt.json",
    )
    if receipt_path.exists():
        try:
            body = json.loads(receipt_path.read_bytes())
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProjectionError("existing conflict receipt is invalid") from error
        comparable = dict(body) if isinstance(body, dict) else {}
        comparable.pop("attempted_at", None)
        if comparable != stable_body:
            raise ProjectionError("existing conflict receipt is inconsistent")
        return receipt_path.relative_to(repository_root).as_posix()
    body = {**stable_body, "attempted_at": utc_now()}
    validation = validate_projection("brain-conflict-v1", body)
    if not validation.valid:
        raise ProjectionError(
            "projection conflict contract failed: "
            + "; ".join(validation.issues)
        )
    staged_root = _path_from_relative(
        state_root,
        f"conflicts/{conflict_id}/desired",
    )
    staged_root.mkdir(parents=True, exist_ok=True)
    for relative_path, desired in desired_files.items():
        staged = _staged_path(staged_root, relative_path)
        if staged.exists():
            if not staged.is_file() or _digest_bytes(staged.read_bytes()) != _digest_bytes(
                desired
            ):
                raise ProjectionError("existing desired conflict bytes are inconsistent")
        else:
            _write_durable(staged, desired)
    temporary_receipt = _path_from_relative(
        state_root,
        f"conflicts/{conflict_id}/receipt.tmp",
    )
    _write_durable(temporary_receipt, _json_bytes(body))
    os.replace(temporary_receipt, receipt_path)
    return receipt_path.relative_to(repository_root).as_posix()


def project_memory_pack(
    store_path: str | Path,
    repository_root: str | Path,
    *,
    tenant_id: str,
    repository_id: str,
    check: bool = False,
    authority: AuthorityDecision | None = None,
    fail_after_replacements: int | None = None,
) -> ProjectionResult:
    supplied_source = Path(store_path)
    if _is_linklike(supplied_source):
        raise ProjectionError("foundation store cannot be a symbolic link")
    source = supplied_source.resolve(strict=False)
    if not source.is_file():
        raise ProjectionError("foundation store must be an existing regular file")
    supplied_repository = Path(repository_root)
    if _is_linklike(supplied_repository):
        raise ProjectionError("repository root cannot be a symbolic link")
    repository = supplied_repository.resolve(strict=True)
    if not repository.is_dir():
        raise ProjectionError("repository root must be an existing regular directory")
    pack_root = repository / PACK_DIRECTORY
    state_root = repository / STATE_DIRECTORY
    _validate_projection_roots(
        repository,
        pack_root=pack_root,
        state_root=state_root,
    )
    if source.is_relative_to(pack_root.resolve(strict=False)):
        raise ProjectionError("foundation store cannot overlap the public memory pack")
    _reject_source_overlap(source, pack_root)
    snapshot = FoundationStore.read_public_memory_snapshot(
        source,
        tenant_id=tenant_id,
        repository_id=repository_id,
    )
    if snapshot.integrity_issues:
        raise ProjectionError(
            "foundation integrity failed: " + "; ".join(snapshot.integrity_issues)
        )
    if (
        snapshot.repository_identity is None
        or snapshot.repository_identity_digest is None
    ):
        raise ProjectionError("repository scope is not registered")
    desired_files, manifest, excluded = _desired_pack(
        snapshot,
        tenant_id=tenant_id,
        repository_id=repository_id,
    )
    desired_manifest_digest = _digest_bytes(desired_files[MANIFEST_PATH])
    tree_digest = _digest_document(
        {
            path: _digest_bytes(content)
            for path, content in sorted(desired_files.items())
        }
    )
    prior_files, prior_manifest_digest, conflicts = _prior_projection_state(
        pack_root=pack_root,
        state_root=state_root,
        desired_files=desired_files,
        tenant_id=tenant_id,
        repository_id=repository_id,
        repository_identity_digest=snapshot.repository_identity_digest,
    )
    common = {
        "schema_version": "hive-brain-projection-result/v1",
        "tenant_id": tenant_id,
        "repository_id": repository_id,
        "repository_identity_digest": snapshot.repository_identity_digest,
        "pack_path": str(pack_root),
        "manifest_digest": desired_manifest_digest,
        "source_cursor": str(manifest["source_cursor"]),
        "tree_digest": tree_digest,
        "source_record_count": snapshot.source_record_count,
        "projected_record_count": int(manifest["safe_public_record_count"]),
        "omitted_sensitive_count": snapshot.omitted_sensitive_count,
        "omitted_unsupported_count": snapshot.omitted_unsupported_count,
        "omitted_quarantined_count": excluded,
    }
    if check:
        if conflicts:
            return ProjectionResult(
                status="conflict",
                conflict_paths=conflicts,
                recovery_status="read-only",
                **common,
            )
        return ProjectionResult(
            status="unchanged" if _pack_matches(pack_root, desired_files) else "drift",
            recovery_status="read-only",
            **common,
        )
    verified_authority = _require_projection_authority(
        authority,
        tenant_id=tenant_id,
        repository_id=repository_id,
    )
    with _projection_lock(state_root):
        _validate_projection_roots(
            repository,
            pack_root=pack_root,
            state_root=state_root,
        )
        _validate_state_tree(state_root)
        _reject_source_overlap(source, pack_root)
        prior_files, prior_manifest_digest, conflicts = _prior_projection_state(
            pack_root=pack_root,
            state_root=state_root,
            desired_files=desired_files,
            tenant_id=tenant_id,
            repository_id=repository_id,
            repository_identity_digest=snapshot.repository_identity_digest,
        )
        if conflicts:
            receipt_path = _preserve_conflict(
                repository_root=repository,
                pack_root=pack_root,
                desired_files=desired_files,
                prior_files=prior_files,
                prior_manifest_digest=prior_manifest_digest,
                desired_manifest_digest=desired_manifest_digest,
                conflict_paths=conflicts,
                authority=verified_authority,
            )
            return ProjectionResult(
                status="conflict",
                conflict_paths=conflicts,
                receipt_path=receipt_path,
                recovery_status="conflict-preserved",
                **common,
            )
        transaction_id = desired_manifest_digest.removeprefix("sha256:")
        pending_transaction = _path_from_relative(
            state_root,
            f"transactions/{transaction_id}/transaction.json",
        ).is_file()
        if _pack_matches(pack_root, desired_files) and not pending_transaction:
            return ProjectionResult(
                status="unchanged",
                recovery_status="not-required",
                **common,
            )
        try:
            receipt_path, recovery_status = _write_transaction(
                repository_root=repository,
                pack_root=pack_root,
                desired_files=desired_files,
                prior_files=prior_files,
                prior_manifest_digest=prior_manifest_digest,
                desired_manifest_digest=desired_manifest_digest,
                authority=verified_authority,
                fail_after_replacements=fail_after_replacements,
            )
        except ProjectionConflictError as error:
            receipt_path = _preserve_conflict(
                repository_root=repository,
                pack_root=pack_root,
                desired_files=desired_files,
                prior_files=prior_files,
                prior_manifest_digest=prior_manifest_digest,
                desired_manifest_digest=desired_manifest_digest,
                conflict_paths=error.conflict_paths,
                authority=verified_authority,
            )
            return ProjectionResult(
                status="conflict",
                conflict_paths=error.conflict_paths,
                receipt_path=receipt_path,
                recovery_status="conflict-preserved",
                **common,
            )
        return ProjectionResult(
            status="projected",
            receipt_path=receipt_path,
            recovery_status=recovery_status,
            **common,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m hive_mind_os.foundation.brain",
        description="Project a safe-public Foundation store into an open memory pack.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("project", "check"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--store", required=True)
        command_parser.add_argument("--repo", required=True)
        command_parser.add_argument("--tenant", required=True)
        command_parser.add_argument("--repository-id", required=True)
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    check = arguments.command == "check"
    authority = None
    if not check:
        authority = decide_foundation_write(
            role=Role.BUILDER,
            action="foundation.projection.write",
            policy_decision=PolicyDecision(True, "explicit local projection command"),
            lease_actions={"foundation.projection.write"},
            adapter_actions={"foundation.projection.write"},
            mission_risk_allowed=True,
            budget_available=True,
            tenant_id=arguments.tenant,
            repository_id=arguments.repository_id,
            actor_id="foundation-brain-projector-v1",
            decision_id="decision:explicit-local-projection",
            lease_id="lease:single-local-projection",
        )
    try:
        result = project_memory_pack(
            arguments.store,
            arguments.repo,
            tenant_id=arguments.tenant,
            repository_id=arguments.repository_id,
            check=check,
            authority=authority,
        )
    except (OSError, ProjectionError, ValueError) as error:
        failure = ProjectionFailure(
            schema_version="hive-brain-projection-failure/v1",
            status="failed",
            error=f"{type(error).__name__}: {error}"[:8192],
        )
        print(
            json.dumps(failure.to_dict(), indent=2, sort_keys=True),
            file=sys.stderr,
        )
        return 2
    stream = sys.stderr if result.status in {"conflict", "drift"} else sys.stdout
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True), file=stream)
    return 1 if result.status in {"conflict", "drift"} else 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
