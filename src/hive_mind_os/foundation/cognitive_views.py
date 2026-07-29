from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import sys
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Mapping, Sequence

from hive_mind_os.models import Role
from hive_mind_os.policy import PolicyDecision

from . import cognitive
from .authority import (
    AuthorityDecision,
    authority_decision_is_authentic,
    decide_foundation_write,
)
from .cognitive_contracts import validate_cognitive
from .cognitive_view_contracts import validate_cognitive_view

VIEW_PROJECTION_CONTRACT = "hive-cognitive-views-projection/v1"
VIEW_PROJECTOR_VERSION = "hive-cognitive-views-projector/v1"
VIEW_MAPPING_VERSION = "hive-cognitive-views-mapping/v1"
MANAGED_NAMESPACE = "hive-mind/generated-cognitive-views"
MANIFEST_NAME = "manifest.json"
SOURCE_NAMESPACE = cognitive.MANAGED_NAMESPACE
VIEW_NODE_DOMAIN = "hive-cognitive-view-node-identity/v1"
MAX_BASE_BYTES = 65_536
MAX_CANVAS_BYTES = 262_144
MAX_MANIFEST_BYTES = 1_048_576
MAX_PACK_BYTES = 2_097_152
MAX_STATE_FILES = 200_100
MAX_PENDING_TRANSACTIONS = 64
MAX_CONFLICTS = 200
MAX_STATE_DOCUMENT_BYTES = 2_097_152
MAX_WINDOWS_PROTECTED_ROOT_CHARS = 110
VIEW_ACTOR = "foundation-cognitive-view-projector-v1"
_ATOMIC_EVIDENCE_RE = re.compile(
    r"^\.cognitive-view-write-([0-9a-f]{64})$"
)
SUPPORTED_CAPABILITIES = (
    "released-agent-related-memory-metadata",
    "released-idea-metadata",
    "released-static-war-room-metadata",
    "released-telemetry-metadata",
)
UNAVAILABLE_CAPABILITIES = (
    "agent-score-and-health",
    "loop-state",
    "quarantine-inventory",
    "token-and-value-accounting",
)
BASE_SPECS = (
    (
        "bases/agent-records.base",
        "agents",
        "Released agent-related records",
        (
            ("note_id", "Generated note ID"),
            ("subject_id", "Released subject ID"),
            ("memory_kind", "Released memory kind"),
            ("actor_id", "Recorded actor ID"),
            ("owner_id", "Recorded owner ID"),
            ("status", "Released record status"),
            ("confidence_ppm", "Released confidence (ppm)"),
            ("observed_at", "Observed time (display only)"),
            ("source_record_id", "Released source record ID"),
        ),
    ),
    (
        "bases/ideas.base",
        "ideas",
        "Released idea metadata",
        (
            ("note_id", "Generated note ID"),
            ("subject_id", "Released subject ID"),
            ("memory_kind", "Released memory kind"),
            ("mission_id", "Recorded mission ID"),
            ("run_id", "Recorded run ID"),
            ("owner_id", "Recorded owner ID"),
            ("status", "Released record status"),
            ("confidence_ppm", "Released confidence (ppm)"),
            ("observed_at", "Observed time (display only)"),
            ("source_record_id", "Released source record ID"),
        ),
    ),
    (
        "bases/released-war-room.base",
        "",
        "Released static metadata — not live",
        (
            ("note_id", "Generated note ID"),
            ("subject_id", "Released subject ID"),
            ("memory_kind", "Released memory kind"),
            ("mission_id", "Recorded mission ID"),
            ("run_id", "Recorded run ID"),
            ("actor_id", "Recorded actor ID"),
            ("owner_id", "Recorded owner ID"),
            ("status", "Released record status"),
            ("recorded_at", "Recorded time (display only)"),
            ("source_record_id", "Released source record ID"),
        ),
    ),
    (
        "bases/telemetry-metadata.base",
        "telemetry",
        "Released telemetry metadata — accounting unavailable",
        (
            ("note_id", "Generated note ID"),
            ("subject_id", "Released subject ID"),
            ("memory_kind", "Released memory kind"),
            ("mission_id", "Recorded mission ID"),
            ("run_id", "Recorded run ID"),
            ("status", "Released record status"),
            ("observed_at", "Observed time (display only)"),
            ("content_digest", "Released content digest"),
            ("source_record_id", "Released source record ID"),
        ),
    ),
)


class CognitiveViewError(RuntimeError):
    pass


class CognitiveViewConflict(CognitiveViewError):
    def __init__(self, paths: Sequence[str]):
        self.paths = tuple(sorted(set(paths)))
        super().__init__("cognitive view conflict: " + ", ".join(self.paths))


@dataclass(frozen=True, slots=True)
class VerifiedCognitiveProjection:
    tenant_id: str
    repository_id: str
    repository_identity_digest: str
    source_cursor: str
    manifest_digest: str
    source_receipt_digest: str
    manifest: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class CognitiveViewBundle:
    files: Mapping[str, bytes]
    manifest: Mapping[str, Any]
    manifest_digest: str
    tree_digest: str


@dataclass(frozen=True, slots=True)
class CognitiveViewResult:
    schema_version: str
    status: str
    tenant_id: str
    repository_id: str
    repository_identity_digest: str
    namespace_path: str
    manifest_digest: str
    source_manifest_digest: str
    source_cursor: str
    tree_digest: str
    base_count: int
    canvas_count: int
    recovery_status: str
    conflict_paths: tuple[str, ...] = ()
    receipt_path: str | None = None

    def to_document(self) -> dict[str, Any]:
        document = asdict(self)
        document["conflict_paths"] = list(self.conflict_paths)
        return document


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _digest_document(value: Any) -> str:
    return _digest_bytes(_json_bytes(value))


def _linklike(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return True
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(metadata, "st_file_attributes", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse)


def _safe_file_digest(path: Path, limit: int, label: str) -> str:
    if (
        not path.is_file()
        or _linklike(path)
        or path.stat(follow_symlinks=False).st_nlink != 1
        or path.stat(follow_symlinks=False).st_size > limit
    ):
        raise CognitiveViewError(f"{label} is not a safe bounded file")
    return _digest_bytes(path.read_bytes())


def _journal_link_digest(path: Path, limit: int, label: str) -> str:
    if (
        not path.is_file()
        or _linklike(path)
        or path.stat(follow_symlinks=False).st_nlink not in {1, 2}
        or path.stat(follow_symlinks=False).st_size > limit
    ):
        raise CognitiveViewError(f"{label} is not a safe journal-owned file")
    return _digest_bytes(path.read_bytes())


def _read_json(path: Path, limit: int, label: str) -> dict[str, Any]:
    _safe_file_digest(path, limit, label)
    try:
        value = json.loads(path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CognitiveViewError(f"{label} is not canonical JSON") from error
    raw = path.read_bytes()
    if not isinstance(value, dict) or raw not in (
        _json_bytes(value),
        cognitive._json_bytes(value),  # type: ignore[attr-defined]
    ):
        raise CognitiveViewError(f"{label} is not a canonical object")
    return value


def _safe_relative(path: str) -> bool:
    pure = PurePosixPath(path)
    return (
        bool(path)
        and len(path) <= 240
        and "\\" not in path
        and not pure.is_absolute()
        and ".." not in pure.parts
        and "." not in pure.parts
        and all(part and not part.endswith((" ", ".")) for part in pure.parts)
    )


def _validate_disjoint(paths: Sequence[Path]) -> None:
    resolved = [path.resolve(strict=path.exists()) for path in paths]
    for index, left in enumerate(resolved):
        for right in resolved[index + 1 :]:
            if (
                left == right
                or left.is_relative_to(right)
                or right.is_relative_to(left)
            ):
                raise CognitiveViewError(
                    "repository and protected roots must be disjoint"
                )


def _source_receipt(
    state: Path,
    manifest: Mapping[str, Any],
    manifest_digest: str,
    tenant_id: str,
    repository_id: str,
) -> tuple[dict[str, Any], str]:
    receipt_path = (
        state / "receipts" / f"{manifest_digest.removeprefix('sha256:')}.json"
    )
    try:
        receipt = cognitive._validated_receipt(  # type: ignore[attr-defined]
            receipt_path,
            manifest_digest=manifest_digest,
            tenant_id=tenant_id,
            repository_id=repository_id,
            repository_identity_digest=manifest["repository_identity_digest"],
            manifest=manifest,
        )
    except cognitive.CognitiveProjectionError as error:
        raise CognitiveViewError(f"source ownership failed: {error}") from error
    if receipt is None:
        raise CognitiveViewError("source ownership receipt is missing")
    return receipt, _safe_file_digest(
        receipt_path, cognitive.MAX_TRANSACTION_BYTES, "source ownership receipt"
    )


def read_verified_cognitive_projection(
    repository_root: str | Path,
    cognitive_protected_state: str | Path,
    *,
    tenant_id: str,
    repository_id: str,
) -> VerifiedCognitiveProjection:
    repository = Path(repository_root).absolute()
    state = Path(cognitive_protected_state).absolute()
    if not repository.is_dir() or _linklike(repository):
        raise CognitiveViewError("repository root must be a safe existing directory")
    if not state.is_dir() or _linklike(state):
        raise CognitiveViewError(
            "cognitive protected state must be a safe existing directory"
        )
    source_transactions = state / "transactions"
    if source_transactions.exists():
        if not source_transactions.is_dir() or _linklike(source_transactions):
            raise CognitiveViewError("source transaction root is unsafe")
        if any(source_transactions.iterdir()):
            raise CognitiveViewError(
                "source has pending transactions; run item-3 projector"
            )
    root = repository / SOURCE_NAMESPACE
    if not root.is_dir() or _linklike(root):
        raise CognitiveViewError("cognitive source namespace is unavailable")
    manifest_path = root / cognitive.MANIFEST_NAME
    manifest = _read_json(
        manifest_path, cognitive.MAX_MANIFEST_BYTES, "cognitive source manifest"
    )
    check = validate_cognitive("cognitive-manifest-v1", manifest)
    if not check.valid:
        raise CognitiveViewError("cognitive source manifest contract failed")
    try:
        cognitive._validate_manifest_semantics(manifest)  # type: ignore[attr-defined]
    except cognitive.CognitiveProjectionError as error:
        raise CognitiveViewError(
            f"cognitive source manifest failed: {error}"
        ) from error
    if (
        manifest["tenant_id"] != tenant_id
        or manifest["repository_id"] != repository_id
        or manifest["projection_contract"] != cognitive.COGNITIVE_PROJECTION_CONTRACT
        or manifest["projector_version"] != cognitive.COGNITIVE_PROJECTOR_VERSION
        or manifest["mapping_version"] != cognitive.COGNITIVE_MAPPING_VERSION
        or manifest["generated_namespace"] != SOURCE_NAMESPACE
    ):
        raise CognitiveViewError("cognitive source scope or version is inconsistent")
    expected = {
        cognitive.MANIFEST_NAME: _digest_bytes(manifest_path.read_bytes()),
        **{entry["path"]: entry["content_digest"] for entry in manifest["files"]},
    }
    observed: dict[str, str] = {}
    visited = 0
    for path in sorted(root.rglob("*")):
        visited += 1
        if visited > cognitive.MAX_STATE_FILES:
            raise CognitiveViewError("cognitive source exceeds path bound")
        rel = path.relative_to(root).as_posix()
        if _linklike(path):
            raise CognitiveViewError(f"cognitive source path is linked: {rel}")
        if path.is_file():
            observed[rel] = _safe_file_digest(
                path,
                cognitive.MAX_MANIFEST_BYTES
                if rel == cognitive.MANIFEST_NAME
                else cognitive.MAX_NOTE_BYTES,
                "cognitive source file",
            )
        elif not path.is_dir():
            raise CognitiveViewError(f"cognitive source path is unsupported: {rel}")
    directories = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_dir()
    }
    if directories != set(cognitive.FOLDERS):
        raise CognitiveViewError("cognitive source directories are not exact")
    if observed != expected:
        raise CognitiveViewError("cognitive source tree does not match its manifest")
    manifest_digest = expected[cognitive.MANIFEST_NAME]
    _, receipt_digest = _source_receipt(
        state, manifest, manifest_digest, tenant_id, repository_id
    )
    return VerifiedCognitiveProjection(
        tenant_id=tenant_id,
        repository_id=repository_id,
        repository_identity_digest=manifest["repository_identity_digest"],
        source_cursor=manifest["source_cursor"],
        manifest_digest=manifest_digest,
        source_receipt_digest=receipt_digest,
        manifest=manifest,
    )


def _base_document(
    folder: str, identity: str, name: str, properties: Sequence[tuple[str, str]]
) -> dict[str, Any]:
    source_folder = SOURCE_NAMESPACE + (f"/{folder}" if folder else "")
    document = {
        "filters": {
            "and": [
                f'file.inFolder("{source_folder}")',
                'schema_version == "hive-cognitive-note/v1"',
                f'generator_version == "{cognitive.COGNITIVE_PROJECTOR_VERSION}"',
                f'mapping_version == "{cognitive.COGNITIVE_MAPPING_VERSION}"',
                'sensitivity == "safe-public"',
                "is_generated == true",
                "is_authoritative == false",
                f'repository_identity_digest == "{identity}"',
            ]
        },
        "properties": {
            key: {"displayName": display_name} for key, display_name in properties
        },
        "views": [
            {
                "type": "table",
                "name": name,
                "order": [key for key, _ in properties],
            }
        ],
    }
    check = validate_cognitive_view("cognitive-view-base-v1", document)
    if not check.valid:
        raise CognitiveViewError(
            "generated Base contract failed: " + "; ".join(check.issues)
        )
    return document


def _yaml_scalar(value: str) -> str:
    ambiguous = {
        "",
        "~",
        "y",
        "yes",
        "n",
        "no",
        "on",
        "off",
        "null",
        "true",
        "false",
        ".nan",
        ".inf",
        "-.inf",
    }
    looks_typed = bool(
        value
        and (
            value[0].isdigit()
            or (
                value[0] in "+-."
                and len(value) > 1
                and value[1].isdigit()
            )
        )
    )
    if (
        value != value.strip()
        or value.casefold() in ambiguous
        or looks_typed
        or value[0] in "-?:,[]{}#&*!|>'\"%@`"
        or "\n" in value
        or "\r" in value
        or "\t" in value
        or any(ord(character) < 0x20 for character in value)
        or ": " in value
        or value.endswith(":")
        or " #" in value
        or value in {"---", "..."}
        or any(character in "[]{},"
               for character in value)
    ):
        return json.dumps(value, ensure_ascii=False)
    return value


def _render_base(document: Mapping[str, Any]) -> bytes:
    lines = ["filters:", "  and:"]
    lines.extend(f"    - {_yaml_scalar(item)}" for item in document["filters"]["and"])
    lines.append("properties:")
    for key, value in document["properties"].items():
        lines.extend(
            (f"  {key}:", f"    displayName: {_yaml_scalar(value['displayName'])}")
        )
    lines.append("views:")
    for view in document["views"]:
        lines.extend(
            (
                f"  - type: {view['type']}",
                f"    name: {_yaml_scalar(view['name'])}",
                "    order:",
            )
        )
        lines.extend(f"      - {item}" for item in view["order"])
    content = ("\n".join(lines) + "\n").encode("utf-8")
    if len(content) > MAX_BASE_BYTES:
        raise CognitiveViewError("generated Base exceeds size bound")
    return content


def _node_id(identity: str, role: str) -> str:
    material = "\n".join((VIEW_NODE_DOMAIN, identity, role)).encode("utf-8")
    return sha256(material).hexdigest()


def _canvas(identity: str) -> dict[str, Any]:
    texts = (
        (
            "disclosure",
            0,
            0,
            720,
            180,
            "# Released cognitive views\n\nStatic, safe-public, generated, nonauthoritative metadata. This is not live operational state.",
        ),
        (
            "agent-unavailable",
            0,
            220,
            340,
            160,
            "Agent scores and health are unavailable. Released agent-related records are not scorecards.",
        ),
        (
            "accounting-unavailable",
            380,
            220,
            340,
            160,
            "Token and value accounting are unavailable. Unknown does not imply zero.",
        ),
        (
            "loops-unavailable",
            0,
            420,
            340,
            160,
            "Loop state is unavailable because the released cognitive source exposes no loop signal.",
        ),
        (
            "quarantine-unavailable",
            380,
            420,
            340,
            160,
            "Quarantine inventory is unavailable because the source admits only nonquarantined public memory. No all-clear is implied.",
        ),
    )
    nodes: list[dict[str, Any]] = [
        {
            "id": _node_id(identity, role),
            "type": "text",
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "text": text,
        }
        for role, x, y, width, height, text in texts
    ]
    for index, (path, _, _, _) in enumerate(BASE_SPECS):
        nodes.append(
            {
                "id": _node_id(identity, f"base:{path}"),
                "type": "file",
                "x": 800,
                "y": index * 180,
                "width": 420,
                "height": 140,
                "file": f"{MANAGED_NAMESPACE}/{path}",
            }
        )
    document = {"nodes": nodes, "edges": []}
    check = validate_cognitive_view("cognitive-view-canvas-v1", document)
    if not check.valid:
        raise CognitiveViewError(
            "generated Canvas contract failed: " + "; ".join(check.issues)
        )
    return document


def _render_canvas(document: Mapping[str, Any]) -> bytes:
    nodes = [
        json.dumps(
            node,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        for node in document["nodes"]
    ]
    lines = ["{", '\t"edges":[],', '\t"nodes":[']
    lines.extend(
        f"\t\t{node}{',' if index < len(nodes) - 1 else ''}"
        for index, node in enumerate(nodes)
    )
    lines.extend(["\t]", "}"])
    return "\n".join(lines).encode("utf-8")


def compile_cognitive_views(source: VerifiedCognitiveProjection) -> CognitiveViewBundle:
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", source.repository_identity_digest):
        raise CognitiveViewError("source repository identity digest is invalid")
    files: dict[str, bytes] = {}
    entries: list[dict[str, str]] = []
    for path, folder, name, properties in BASE_SPECS:
        content = _render_base(
            _base_document(folder, source.repository_identity_digest, name, properties)
        )
        files[path] = content
        entries.append(
            {
                "path": path,
                "kind": "base",
                "semantic_role": path.removeprefix("bases/").removesuffix(".base"),
                "content_digest": _digest_bytes(content),
            }
        )
    canvas_path = "canvases/war-room.canvas"
    canvas_bytes = _render_canvas(_canvas(source.repository_identity_digest))
    if len(canvas_bytes) > MAX_CANVAS_BYTES:
        raise CognitiveViewError("generated Canvas exceeds size bound")
    files[canvas_path] = canvas_bytes
    entries.append(
        {
            "path": canvas_path,
            "kind": "canvas",
            "semantic_role": "war-room-navigation-and-limitations",
            "content_digest": _digest_bytes(canvas_bytes),
        }
    )
    manifest = {
        "schema_version": "hive-cognitive-view-manifest/v1",
        "projection_contract": VIEW_PROJECTION_CONTRACT,
        "projector_version": VIEW_PROJECTOR_VERSION,
        "mapping_version": VIEW_MAPPING_VERSION,
        "tenant_id": source.tenant_id,
        "repository_id": source.repository_id,
        "repository_identity_digest": source.repository_identity_digest,
        "source_cursor": source.source_cursor,
        "source_manifest_digest": source.manifest_digest,
        "generated_namespace": MANAGED_NAMESPACE,
        "base_count": 4,
        "canvas_count": 1,
        "supported_capabilities": list(SUPPORTED_CAPABILITIES),
        "unavailable_capabilities": list(UNAVAILABLE_CAPABILITIES),
        "files": sorted(entries, key=lambda item: item["path"]),
    }
    check = validate_cognitive_view("cognitive-view-manifest-v1", manifest)
    if not check.valid:
        raise CognitiveViewError(
            "generated manifest contract failed: " + "; ".join(check.issues)
        )
    manifest_bytes = _json_bytes(manifest)
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise CognitiveViewError("generated manifest exceeds size bound")
    files[MANIFEST_NAME] = manifest_bytes
    if sum(map(len, files.values())) > MAX_PACK_BYTES:
        raise CognitiveViewError("generated view pack exceeds size bound")
    manifest_digest = _digest_bytes(manifest_bytes)
    tree_digest = _digest_document(
        {path: _digest_bytes(content) for path, content in sorted(files.items())}
    )
    return CognitiveViewBundle(files, manifest, manifest_digest, tree_digest)


def _validate_view_manifest(manifest: Mapping[str, Any]) -> None:
    check = validate_cognitive_view("cognitive-view-manifest-v1", manifest)
    if not check.valid:
        raise CognitiveViewError("existing view manifest contract failed")
    paths = [entry["path"] for entry in manifest["files"]]
    expected = sorted(path for path, *_ in BASE_SPECS) + ["canvases/war-room.canvas"]
    if paths != sorted(expected) or len(paths) != len(set(paths)):
        raise CognitiveViewError("existing view manifest paths are invalid")
    if tuple(manifest["supported_capabilities"]) != SUPPORTED_CAPABILITIES:
        raise CognitiveViewError("existing supported capabilities are invalid")
    if tuple(manifest["unavailable_capabilities"]) != UNAVAILABLE_CAPABILITIES:
        raise CognitiveViewError("existing unavailable capabilities are invalid")
    if any(not _safe_relative(path) for path in paths):
        raise CognitiveViewError("existing view manifest path is unsafe")


def _validate_operations(operations: Any) -> list[dict[str, Any]]:
    if not isinstance(operations, list) or not 1 <= len(operations) <= 12:
        raise CognitiveViewError("view transaction operations are invalid")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for operation in operations:
        if (
            not isinstance(operation, dict)
            or set(operation) != {"path", "expected_prior_digest", "desired_digest"}
            or not _safe_relative(operation["path"])
            or operation["path"] in seen
        ):
            raise CognitiveViewError("view transaction operation is invalid")
        seen.add(operation["path"])
        result.append(operation)
    if result[-1]["path"] != MANIFEST_NAME:
        raise CognitiveViewError("view manifest operation must be last")
    return result


def _validated_view_receipt(
    state: Path,
    manifest: Mapping[str, Any],
    manifest_digest: str,
    cognitive_state: Path | None = None,
) -> dict[str, Any] | None:
    current_digest: str | None = manifest_digest
    child: list[dict[str, Any]] | None = None
    head: dict[str, Any] | None = None
    seen: set[str] = set()
    validated_source_digests: set[str] = set()
    while current_digest is not None:
        if current_digest in seen or len(seen) >= MAX_STATE_FILES:
            raise CognitiveViewError("view receipt chain is cyclic or oversized")
        seen.add(current_digest)
        path = state / "receipts" / f"{current_digest.removeprefix('sha256:')}.json"
        if not path.exists():
            if head is None:
                return None
            raise CognitiveViewError("view prior receipt is missing")
        receipt = _read_json(path, MAX_STATE_DOCUMENT_BYTES, "view receipt")
        check = validate_cognitive_view("cognitive-view-receipt-v1", receipt)
        if not check.valid:
            raise CognitiveViewError("view receipt contract failed")
        if (
            receipt["transaction_id"] != current_digest.removeprefix("sha256:")
            or receipt["desired_manifest_digest"] != current_digest
            or receipt["verified_manifest_digest"] != current_digest
            or receipt["tenant_id"] != manifest["tenant_id"]
            or receipt["repository_id"] != manifest["repository_id"]
            or receipt["repository_identity_digest"]
            != manifest["repository_identity_digest"]
        ):
            raise CognitiveViewError("view receipt scope is inconsistent")
        if cognitive_state is not None:
            _validate_source_receipt_for_journal(
                cognitive_state,
                receipt,
                validated_source_digests,
            )
        operations = _validate_operations(receipt["operations"])
        desired = {
            operation["path"]: operation["desired_digest"]
            for operation in operations
            if operation["desired_digest"] is not None
        }
        if head is None:
            head = receipt
            if (
                receipt["source_cursor"] != manifest["source_cursor"]
                or receipt["source_manifest_digest"]
                != manifest["source_manifest_digest"]
            ):
                raise CognitiveViewError("view receipt source evidence is inconsistent")
            expected = {
                MANIFEST_NAME: manifest_digest,
                **{
                    entry["path"]: entry["content_digest"]
                    for entry in manifest["files"]
                },
            }
            if desired != expected:
                raise CognitiveViewError("view receipt desired plan is inconsistent")
        if child is not None:
            prior = {
                operation["path"]: operation["expected_prior_digest"]
                for operation in child
                if operation["expected_prior_digest"] is not None
            }
            if desired != prior:
                raise CognitiveViewError("view receipt chain plan is inconsistent")
        child = operations
        current_digest = receipt["prior_manifest_digest"]
    return head


def _existing_state(
    root: Path,
    state: Path,
    cognitive_state: Path,
    source: VerifiedCognitiveProjection,
) -> tuple[dict[str, str], str | None, bool]:
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.exists():
        return {}, None, False
    manifest = _read_json(manifest_path, MAX_MANIFEST_BYTES, "view manifest")
    _validate_view_manifest(manifest)
    if (
        manifest["tenant_id"],
        manifest["repository_id"],
        manifest["repository_identity_digest"],
    ) != (
        source.tenant_id,
        source.repository_id,
        source.repository_identity_digest,
    ):
        raise CognitiveViewError("existing view scope is inconsistent")
    digest = _digest_bytes(manifest_path.read_bytes())
    head_receipt = _validated_view_receipt(state, manifest, digest, cognitive_state)
    owned = head_receipt is not None
    prior = (
        {entry["path"]: entry["content_digest"] for entry in manifest["files"]}
        if owned
        else {}
    )
    return prior, digest, owned


def _validate_receipt_reachability(
    root: Path,
    state: Path,
    cognitive_state: Path,
) -> None:
    receipt_root = state / "receipts"
    if not receipt_root.exists():
        return
    receipt_paths = set(receipt_root.glob("*.json"))
    if not receipt_paths:
        return
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.exists():
        raise CognitiveViewError("view receipts lack an installed manifest")
    manifest = _read_json(manifest_path, MAX_MANIFEST_BYTES, "installed view manifest")
    _validate_view_manifest(manifest)
    current: str | None = _digest_bytes(manifest_path.read_bytes())
    _validated_view_receipt(
        state,
        manifest,
        current,
        cognitive_state,
    )
    reachable: set[Path] = set()
    while current is not None:
        path = receipt_root / f"{current.removeprefix('sha256:')}.json"
        if path in reachable:
            raise CognitiveViewError("view receipt reachability contains a cycle")
        reachable.add(path)
        receipt = _read_json(path, MAX_STATE_DOCUMENT_BYTES, "reachable view receipt")
        current = receipt["prior_manifest_digest"]
    if receipt_paths != reachable:
        raise CognitiveViewError("view receipt evidence is not reachable from head")


def _observed_tree(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    if not root.is_dir() or _linklike(root):
        raise CognitiveViewError("view namespace is unsafe")
    observed: dict[str, str] = {}
    visited = 0
    for path in sorted(root.rglob("*")):
        visited += 1
        if visited > MAX_STATE_FILES:
            raise CognitiveViewError("view namespace exceeds path bound")
        rel = path.relative_to(root).as_posix()
        if _linklike(path):
            observed[rel] = "linked"
        elif path.is_file():
            try:
                observed[rel] = _safe_file_digest(
                    path,
                    MAX_MANIFEST_BYTES if rel == MANIFEST_NAME else MAX_CANVAS_BYTES,
                    "view file",
                )
            except CognitiveViewError:
                observed[rel] = "unsafe"
        elif not path.is_dir():
            observed[rel] = "unsupported"
    return observed


def _conflicts(
    root: Path,
    bundle: CognitiveViewBundle,
    prior: Mapping[str, str],
    prior_manifest: str | None,
    owned: bool,
) -> tuple[str, ...]:
    observed = _observed_tree(root)
    expected_prior = {**prior, **({MANIFEST_NAME: prior_manifest} if owned else {})}
    expected_paths = set(bundle.files)
    conflicts = {
        path
        for path, digest in observed.items()
        if path not in expected_paths or expected_prior.get(path) != digest
    }
    if owned:
        conflicts.update(path for path in expected_prior if path not in observed)
    if observed and not owned:
        conflicts.update(observed)
    ordered = sorted(conflicts)
    if len(ordered) > MAX_CONFLICTS:
        omitted = len(ordered) - (MAX_CONFLICTS - 1)
        ordered = ordered[: MAX_CONFLICTS - 1] + [f"conflict-overflow:{omitted}"]
    return tuple(ordered)


def _atomic_evidence_digest(path: Path) -> str | None:
    matched = _ATOMIC_EVIDENCE_RE.fullmatch(path.name)
    if matched is None:
        return None
    return f"sha256:{matched.group(1)}"


def _atomic_evidence_paths(state: Path) -> list[Path]:
    if not state.exists():
        return []
    return sorted(
        path
        for path in state.rglob("*")
        if path.is_file() and _atomic_evidence_digest(path) is not None
    )


def _validate_windows_protected_root(path: Path) -> None:
    if os.name == "nt" and len(str(path)) > MAX_WINDOWS_PROTECTED_ROOT_CHARS:
        raise CognitiveViewError(
            "view protected-state path exceeds Windows path budget"
        )


def _rename_no_replace(source: Path, destination: Path) -> None:
    if os.name == "nt":
        os.rename(source, destination)
        return
    import ctypes
    import errno

    library = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)
    if sys.platform.startswith("linux") and hasattr(library, "renameat2"):
        result = library.renameat2(
            -100,
            ctypes.c_char_p(source_bytes),
            -100,
            ctypes.c_char_p(destination_bytes),
            1,
        )
    elif sys.platform == "darwin" and hasattr(library, "renamex_np"):
        result = library.renamex_np(
            ctypes.c_char_p(source_bytes),
            ctypes.c_char_p(destination_bytes),
            0x00000004,
        )
    else:
        raise CognitiveViewError(
            "atomic no-replace rename is unsupported on this platform"
        )
    if result != 0:
        error_number = ctypes.get_errno()
        if error_number == errno.EEXIST:
            raise FileExistsError(destination)
        raise OSError(error_number, os.strerror(error_number), destination)


def _validate_abandoned_preparations(state: Path) -> None:
    abandoned = state / "abandoned"
    if not abandoned.exists():
        return
    if not abandoned.is_dir() or _linklike(abandoned):
        raise CognitiveViewError("abandoned view preparation root is unsafe")
    receipts: dict[str, Path] = {}
    directories: dict[str, Path] = {}
    for child in abandoned.iterdir():
        if _atomic_evidence_digest(child) is not None:
            continue
        if child.is_file() and re.fullmatch(r"[0-9a-f]{64}\.json", child.name):
            receipts[child.stem] = child
        elif child.is_dir() and re.fullmatch(r"[0-9a-f]{64}", child.name):
            directories[child.name] = child
        else:
            raise CognitiveViewError("abandoned view preparation path is invalid")
    if not set(directories).issubset(receipts):
        raise CognitiveViewError("abandoned view preparation receipt is missing")
    preparations = state / "preparations"
    for identity, receipt_path in receipts.items():
        receipt = _read_json(
            receipt_path,
            MAX_STATE_DOCUMENT_BYTES,
            "abandoned view preparation receipt",
        )
        if (
            set(receipt) != {"record_kind", "transaction_id", "files"}
            or receipt["record_kind"] != "cognitive-view-abandonment"
            or not isinstance(receipt["transaction_id"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", receipt["transaction_id"])
            or not isinstance(receipt["files"], list)
            or len(receipt["files"]) > 16
            or _digest_document(receipt).removeprefix("sha256:") != identity
        ):
            raise CognitiveViewError(
                "abandoned view preparation receipt is inconsistent"
            )
        files: dict[str, str] = {}
        for item in receipt["files"]:
            if (
                not isinstance(item, dict)
                or set(item) != {"path", "digest"}
                or not isinstance(item["path"], str)
                or not isinstance(item["digest"], str)
                or item["path"] in files
                or (
                    item["path"] != "transaction.json"
                    and not re.fullmatch(r"files/[0-9a-f]{64}", item["path"])
                )
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", item["digest"])
            ):
                raise CognitiveViewError(
                    "abandoned view preparation file receipt is inconsistent"
                )
            files[item["path"]] = item["digest"]
        if list(files) != sorted(files):
            raise CognitiveViewError(
                "abandoned view preparation file receipt is not ordered"
            )
        preserved = directories.get(identity)
        pending = preparations / receipt["transaction_id"]
        if preserved is not None and pending.exists():
            raise CognitiveViewError("abandoned and pending view preparations overlap")
        evidence_root = preserved if preserved is not None else pending
        if (
            not evidence_root.exists()
            or not evidence_root.is_dir()
            or _linklike(evidence_root)
        ):
            raise CognitiveViewError("abandoned view preparation evidence is missing")
        observed: dict[str, str] = {}
        for path in sorted(evidence_root.rglob("*")):
            rel = path.relative_to(evidence_root).as_posix()
            if path.is_file():
                observed[rel] = _safe_file_digest(
                    path,
                    MAX_STATE_DOCUMENT_BYTES,
                    "abandoned view preparation file",
                )
            elif not path.is_dir() or rel != "files":
                raise CognitiveViewError(
                    "abandoned view preparation evidence path is invalid"
                )
        if observed != files:
            raise CognitiveViewError(
                "abandoned view preparation evidence is inconsistent"
            )
        journal_path = evidence_root / "transaction.json"
        if journal_path.exists():
            try:
                journal = _read_json(
                    journal_path,
                    MAX_STATE_DOCUMENT_BYTES,
                    "abandoned view preparation journal",
                )
            except CognitiveViewError:
                pass
            else:
                if (
                    not isinstance(journal.get("transaction_id"), str)
                    or journal["transaction_id"] != receipt["transaction_id"]
                ):
                    raise CognitiveViewError(
                        "abandoned view preparation journal scope is inconsistent"
                    )


def _validate_view_state(state: Path) -> None:
    if not state.exists():
        return
    if not state.is_dir() or _linklike(state):
        raise CognitiveViewError("view protected state is unsafe")
    allowed_top = {
        "abandoned",
        "cognitive-views.lock",
        "conflicts",
        "preparations",
        "receipts",
        "transactions",
    }
    visited = 0
    for path in sorted(state.rglob("*")):
        visited += 1
        if visited > MAX_STATE_FILES:
            raise CognitiveViewError("view protected state exceeds path bound")
        rel = path.relative_to(state)
        if rel.parts[0] not in allowed_top:
            raise CognitiveViewError("view protected state contains unmanaged paths")
        if _linklike(path):
            raise CognitiveViewError("view protected state contains a linked path")
        if path.is_file():
            metadata = path.stat(follow_symlinks=False)
            if metadata.st_nlink != 1 or metadata.st_size > MAX_STATE_DOCUMENT_BYTES:
                raise CognitiveViewError("view protected file is unsafe or oversized")
            if _atomic_evidence_digest(path) is not None:
                if (
                    len(rel.parts) != 2
                    or rel.parts[0] not in {"abandoned", "conflicts", "receipts"}
                ):
                    raise CognitiveViewError(
                        "pending atomic view evidence path is invalid"
                    )
                continue
            if rel.parts[0] == "receipts":
                if len(rel.parts) != 2 or not re.fullmatch(
                    r"[0-9a-f]{64}\.json", rel.name
                ):
                    raise CognitiveViewError("view receipt path is invalid")
                receipt = _read_json(
                    path, MAX_STATE_DOCUMENT_BYTES, "protected view receipt"
                )
                check = validate_cognitive_view("cognitive-view-receipt-v1", receipt)
                if (
                    not check.valid
                    or receipt["transaction_id"] != path.stem
                    or receipt["desired_manifest_digest"] != f"sha256:{path.stem}"
                    or receipt["verified_manifest_digest"] != f"sha256:{path.stem}"
                ):
                    raise CognitiveViewError("protected view receipt is inconsistent")
            elif rel.parts[0] == "conflicts":
                if len(rel.parts) != 2 or not re.fullmatch(
                    r"[0-9a-f]{64}\.json", rel.name
                ):
                    raise CognitiveViewError("view conflict path is invalid")
                conflict = _read_json(
                    path, MAX_STATE_DOCUMENT_BYTES, "protected view conflict"
                )
                check = validate_cognitive_view("cognitive-view-conflict-v1", conflict)
                if (
                    not check.valid
                    or _digest_document(conflict).removeprefix("sha256:") != path.stem
                ):
                    raise CognitiveViewError("protected view conflict is inconsistent")
            elif rel.parts[0] == "cognitive-views.lock":
                if len(rel.parts) != 1:
                    raise CognitiveViewError("view lock path is invalid")
        elif not path.is_dir():
            raise CognitiveViewError("view protected path type is unsupported")
        elif rel.parts[0] in {"conflicts", "receipts"} and len(rel.parts) != 1:
            raise CognitiveViewError("view protected evidence directory is invalid")
    _validate_abandoned_preparations(state)


def _write_exclusive(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def _atomic_evidence_target(path: Path, document: Mapping[str, Any]) -> Path:
    schema = document.get("schema_version")
    if schema == "hive-cognitive-view-receipt/v1":
        if (
            path.parent.name != "receipts"
            or not validate_cognitive_view("cognitive-view-receipt-v1", document).valid
        ):
            raise CognitiveViewError("pending view receipt evidence is inconsistent")
        name = document["transaction_id"]
    elif schema == "hive-cognitive-view-conflict/v1":
        if (
            path.parent.name != "conflicts"
            or not validate_cognitive_view("cognitive-view-conflict-v1", document).valid
        ):
            raise CognitiveViewError("pending view conflict evidence is inconsistent")
        name = _digest_document(document).removeprefix("sha256:")
    elif document.get("record_kind") == "cognitive-view-abandonment":
        if path.parent.name != "abandoned":
            raise CognitiveViewError(
                "pending view abandonment evidence is inconsistent"
            )
        name = _digest_document(document).removeprefix("sha256:")
    else:
        raise CognitiveViewError("pending atomic view evidence kind is unsupported")
    if not isinstance(name, str) or not re.fullmatch(r"[0-9a-f]{64}", name):
        raise CognitiveViewError("pending atomic view evidence target is invalid")
    return path.parent / f"{name}.json"


def _write_atomic_evidence(path: Path, content: bytes) -> None:
    expected = _digest_bytes(content)
    temporary = path.parent / f".cognitive-view-write-{expected.removeprefix('sha256:')}"
    if temporary.exists():
        if _safe_file_digest(
            temporary,
            MAX_STATE_DOCUMENT_BYTES,
            "pending atomic view evidence",
        ) != expected:
            temporary.unlink()
            _write_exclusive(temporary, content)
    else:
        _write_exclusive(temporary, content)
    try:
        _rename_no_replace(temporary, path)
    except FileExistsError as error:
        if (
            _safe_file_digest(
                path,
                MAX_STATE_DOCUMENT_BYTES,
                "existing atomic view evidence",
            )
            != expected
        ):
            raise CognitiveViewError(
                "atomic view evidence target already exists"
            ) from error
        temporary.unlink()


def _recover_atomic_evidence(state: Path) -> None:
    for temporary in _atomic_evidence_paths(state):
        expected = _atomic_evidence_digest(temporary)
        assert expected is not None
        if (
            _safe_file_digest(
                temporary,
                MAX_STATE_DOCUMENT_BYTES,
                "pending atomic view evidence",
            )
            != expected
        ):
            temporary.unlink()
            continue
        document = _read_json(
            temporary,
            MAX_STATE_DOCUMENT_BYTES,
            "pending atomic view evidence",
        )
        target = _atomic_evidence_target(temporary, document)
        try:
            _rename_no_replace(temporary, target)
        except FileExistsError as error:
            if (
                _safe_file_digest(
                    target,
                    MAX_STATE_DOCUMENT_BYTES,
                    "existing atomic view evidence",
                )
                != expected
            ):
                raise CognitiveViewError(
                    "pending atomic view evidence target is inconsistent"
                ) from error
            temporary.unlink()


def _preflight_view_siblings(
    root: Path,
    operations: Sequence[Mapping[str, Any]],
    transaction_id: str,
) -> None:
    if not root.exists():
        return
    allowed: dict[str, tuple[str | None, Path, str]] = {}
    for operation in operations:
        destination = root / Path(*PurePosixPath(operation["path"]).parts)
        prior = destination.with_name(
            f".{destination.name}.cognitive-view-prior-{transaction_id}"
        )
        next_path = destination.with_name(
            f".{destination.name}.cognitive-view-next-{transaction_id}"
        )
        allowed[prior.relative_to(root).as_posix()] = (
            operation["expected_prior_digest"],
            destination,
            "prior",
        )
        allowed[next_path.relative_to(root).as_posix()] = (
            operation["desired_digest"],
            destination,
            "next",
        )
    visited = 0
    for path in root.rglob("*"):
        visited += 1
        if visited > MAX_STATE_FILES:
            raise CognitiveViewError(
                "view namespace exceeds path bound during recovery"
            )
        rel = path.relative_to(root).as_posix()
        if (
            ".cognitive-view-prior-" in path.name
            or ".cognitive-view-next-" in path.name
        ):
            if rel not in allowed or allowed[rel][0] is None:
                raise CognitiveViewConflict((rel,))
            expected, destination, kind = allowed[rel]
            assert expected is not None
            if (
                _journal_link_digest(
                    path, MAX_STATE_DOCUMENT_BYTES, "reserved view sibling"
                )
                != expected
            ):
                raise CognitiveViewConflict((rel,))
            links = path.stat(follow_symlinks=False).st_nlink
            if links == 2:
                try:
                    same_file = (
                        kind == "next"
                        and destination.exists()
                        and not _linklike(destination)
                        and os.path.samefile(path, destination)
                    )
                except OSError:
                    same_file = False
                if (
                    not same_file
                    or _journal_link_digest(
                        destination,
                        MAX_STATE_DOCUMENT_BYTES,
                        "installed view destination",
                    )
                    != expected
                ):
                    raise CognitiveViewConflict((rel,))


@contextmanager
def _view_lock(state: Path) -> Iterator[None]:
    state.mkdir(exist_ok=True)
    lock = state / "cognitive-views.lock"
    if lock.exists() and (_linklike(lock) or lock.stat().st_nlink != 1):
        raise CognitiveViewError("view lock is unsafe")
    handle = lock.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            if handle.read(1) == b"":
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    except OSError as error:
        raise CognitiveViewError("view projection is already locked") from error
    finally:
        try:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _validate_source_receipt_for_journal(
    cognitive_state: Path,
    journal: Mapping[str, Any],
    validated_source_digests: set[str] | None = None,
) -> None:
    path = (
        cognitive_state
        / "receipts"
        / f"{journal['source_manifest_digest'].removeprefix('sha256:')}.json"
    )
    if (
        _safe_file_digest(
            path, cognitive.MAX_TRANSACTION_BYTES, "historic source receipt"
        )
        != journal["source_receipt_digest"]
    ):
        raise CognitiveViewError("historic source receipt digest is inconsistent")
    source_manifest_digest = journal["source_manifest_digest"]
    if (
        validated_source_digests is not None
        and source_manifest_digest in validated_source_digests
    ):
        direct = _read_json(
            path,
            cognitive.MAX_TRANSACTION_BYTES,
            "historic source receipt",
        )
        check = validate_cognitive("cognitive-receipt-v1", direct)
        if (
            not check.valid
            or direct["transaction_id"]
            != source_manifest_digest.removeprefix("sha256:")
            or direct["desired_manifest_digest"] != source_manifest_digest
            or direct["verified_manifest_digest"] != source_manifest_digest
            or direct["source_cursor"] != journal["source_cursor"]
            or direct["tenant_id"] != journal["tenant_id"]
            or direct["repository_id"] != journal["repository_id"]
            or direct["repository_identity_digest"]
            != journal["repository_identity_digest"]
        ):
            raise CognitiveViewError("historic source receipt is inconsistent")
        return
    try:
        receipt = cognitive._validated_receipt(  # type: ignore[attr-defined]
            path,
            manifest_digest=journal["source_manifest_digest"],
            tenant_id=journal["tenant_id"],
            repository_id=journal["repository_id"],
            repository_identity_digest=journal["repository_identity_digest"],
        )
    except cognitive.CognitiveProjectionError as error:
        raise CognitiveViewError(f"historic source receipt failed: {error}") from error
    if receipt is None or receipt["source_cursor"] != journal["source_cursor"]:
        raise CognitiveViewError("historic source receipt is inconsistent")
    if validated_source_digests is not None:
        current: str | None = source_manifest_digest
        visited = 0
        while current is not None and current not in validated_source_digests:
            visited += 1
            if visited > cognitive.MAX_RECORDS:
                raise CognitiveViewError("historic source receipt chain is oversized")
            validated_source_digests.add(current)
            current_path = (
                cognitive_state / "receipts" / f"{current.removeprefix('sha256:')}.json"
            )
            current_receipt = _read_json(
                current_path,
                cognitive.MAX_TRANSACTION_BYTES,
                "historic source receipt",
            )
            current = current_receipt["prior_manifest_digest"]


def _validate_transaction_plan(
    state: Path,
    tx_root: Path,
    journal: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if (
        journal["transaction_id"]
        != journal["desired_manifest_digest"].removeprefix("sha256:")
        or tx_root.name != journal["transaction_id"]
    ):
        raise CognitiveViewError("view transaction identity is inconsistent")
    operations = _validate_operations(journal["operations"])
    staged_root = tx_root / "files"
    if not staged_root.is_dir() or _linklike(staged_root):
        raise CognitiveViewError("staged view root is unsafe")
    expected_names = {
        sha256(operation["path"].encode()).hexdigest() for operation in operations
    }
    observed_names: set[str] = set()
    for path in staged_root.iterdir():
        if (
            not path.is_file()
            or _linklike(path)
            or path.stat(follow_symlinks=False).st_nlink != 1
        ):
            raise CognitiveViewError("staged view path is unsafe")
        observed_names.add(path.name)
    if observed_names != expected_names:
        raise CognitiveViewError("staged view file set is inconsistent")
    manifest_stage = staged_root / sha256(MANIFEST_NAME.encode()).hexdigest()
    manifest = _read_json(manifest_stage, MAX_MANIFEST_BYTES, "staged view manifest")
    _validate_view_manifest(manifest)
    if (
        _digest_bytes(manifest_stage.read_bytes()) != journal["desired_manifest_digest"]
        or manifest["tenant_id"] != journal["tenant_id"]
        or manifest["repository_id"] != journal["repository_id"]
        or manifest["repository_identity_digest"]
        != journal["repository_identity_digest"]
        or manifest["source_cursor"] != journal["source_cursor"]
        or manifest["source_manifest_digest"] != journal["source_manifest_digest"]
    ):
        raise CognitiveViewError("staged view manifest is inconsistent")
    desired_plan = {
        operation["path"]: operation["desired_digest"] for operation in operations
    }
    manifest_plan = {
        MANIFEST_NAME: journal["desired_manifest_digest"],
        **{entry["path"]: entry["content_digest"] for entry in manifest["files"]},
    }
    if desired_plan != manifest_plan:
        raise CognitiveViewError("view transaction desired plan is inconsistent")
    prior_digest = journal["prior_manifest_digest"]
    if prior_digest is None:
        if any(
            operation["expected_prior_digest"] is not None for operation in operations
        ):
            raise CognitiveViewError("view transaction prior plan is inconsistent")
    else:
        receipt_path = (
            state / "receipts" / f"{prior_digest.removeprefix('sha256:')}.json"
        )
        receipt = _read_json(
            receipt_path, MAX_STATE_DOCUMENT_BYTES, "prior view receipt"
        )
        check = validate_cognitive_view("cognitive-view-receipt-v1", receipt)
        if (
            not check.valid
            or receipt["desired_manifest_digest"] != prior_digest
            or receipt["verified_manifest_digest"] != prior_digest
            or receipt["tenant_id"] != journal["tenant_id"]
            or receipt["repository_id"] != journal["repository_id"]
            or receipt["repository_identity_digest"]
            != journal["repository_identity_digest"]
        ):
            raise CognitiveViewError("view transaction prior receipt is inconsistent")
        expected_prior = {
            operation["path"]: operation["expected_prior_digest"]
            for operation in operations
        }
        prior_plan = {
            operation["path"]: operation["desired_digest"]
            for operation in _validate_operations(receipt["operations"])
        }
        if expected_prior != prior_plan:
            raise CognitiveViewError("view transaction prior plan is inconsistent")
    return operations


def _apply_transaction(
    root: Path,
    state: Path,
    tx_root: Path,
    journal: Mapping[str, Any],
    *,
    fail_after_replacements: int | None = None,
    source_revalidate: Any | None = None,
) -> str:
    operations = _validate_transaction_plan(state, tx_root, journal)
    _preflight_view_siblings(root, operations, journal["transaction_id"])
    files = tx_root / "files"
    replaced = 0
    for operation in operations:
        rel = operation["path"]
        if rel == MANIFEST_NAME and source_revalidate is not None:
            source_revalidate()
        destination = root / Path(*PurePosixPath(rel).parts)
        next_path = destination.with_name(
            f".{destination.name}.cognitive-view-next-{journal['transaction_id']}"
        )
        prior_path = destination.with_name(
            f".{destination.name}.cognitive-view-prior-{journal['transaction_id']}"
        )
        staged = files / sha256(rel.encode()).hexdigest()
        desired_digest = operation["desired_digest"]
        expected_prior = operation["expected_prior_digest"]
        if next_path.exists() and destination.exists():
            try:
                installed_pair = os.path.samefile(next_path, destination)
            except OSError:
                installed_pair = False
            if installed_pair:
                if (
                    _journal_link_digest(
                        next_path,
                        MAX_STATE_DOCUMENT_BYTES,
                        "next view file",
                    )
                    != desired_digest
                    or _journal_link_digest(
                        destination,
                        MAX_STATE_DOCUMENT_BYTES,
                        "installed view destination",
                    )
                    != desired_digest
                ):
                    raise CognitiveViewConflict((rel,))
                next_path.unlink()
        try:
            cognitive._validate_managed_write_target(  # type: ignore[attr-defined]
                root, destination
            )
        except cognitive.CognitiveProjectionConflict as error:
            raise CognitiveViewConflict((rel,)) from error
        if (
            _safe_file_digest(staged, MAX_STATE_DOCUMENT_BYTES, "staged view file")
            != desired_digest
        ):
            raise CognitiveViewError("staged view file digest is inconsistent")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if next_path.exists():
            if (
                _safe_file_digest(next_path, MAX_STATE_DOCUMENT_BYTES, "next view file")
                != desired_digest
            ):
                raise CognitiveViewConflict((rel,))
        elif (
            not destination.exists()
            or _safe_file_digest(
                destination, MAX_STATE_DOCUMENT_BYTES, "view destination"
            )
            != desired_digest
        ):
            _write_exclusive(next_path, staged.read_bytes())
        if (
            destination.exists()
            and _safe_file_digest(
                destination, MAX_STATE_DOCUMENT_BYTES, "view destination"
            )
            == desired_digest
        ):
            if next_path.exists():
                try:
                    same_file = os.path.samefile(next_path, destination)
                except OSError:
                    same_file = False
                if not same_file:
                    raise CognitiveViewConflict((rel,))
                next_path.unlink()
            if prior_path.exists():
                if (
                    expected_prior is None
                    or _safe_file_digest(
                        prior_path,
                        MAX_STATE_DOCUMENT_BYTES,
                        "prior view file",
                    )
                    != expected_prior
                ):
                    raise CognitiveViewConflict((rel,))
                prior_path.unlink()
            continue
        if not prior_path.exists():
            observed = (
                _safe_file_digest(
                    destination, MAX_STATE_DOCUMENT_BYTES, "view destination"
                )
                if destination.exists()
                else None
            )
            if observed != expected_prior:
                raise CognitiveViewConflict((rel,))
            if destination.exists():
                try:
                    _rename_no_replace(destination, prior_path)
                except (FileExistsError, OSError) as error:
                    raise CognitiveViewConflict((rel,)) from error
        elif (
            expected_prior is None
            or _safe_file_digest(
                prior_path, MAX_STATE_DOCUMENT_BYTES, "prior view file"
            )
            != expected_prior
        ):
            raise CognitiveViewConflict((rel,))
        if destination.exists():
            raise CognitiveViewConflict((rel,))
        try:
            with (
                cognitive._no_delete_lease(  # type: ignore[attr-defined]
                    root, directory=True
                ),
                cognitive._no_delete_lease(  # type: ignore[attr-defined]
                    destination.parent, directory=True
                ),
                cognitive._no_delete_lease(  # type: ignore[attr-defined]
                    next_path, directory=False
                ),
            ):
                parent_identity = cognitive._directory_identity(  # type: ignore[attr-defined]
                    destination.parent
                )
                cognitive._validate_managed_write_target(  # type: ignore[attr-defined]
                    root, destination
                )
                os.link(next_path, destination)
                if cognitive._directory_identity(  # type: ignore[attr-defined]
                    destination.parent
                ) != parent_identity or not os.path.samefile(next_path, destination):
                    raise CognitiveViewConflict((rel,))
                cognitive._validate_managed_write_target(  # type: ignore[attr-defined]
                    root, destination
                )
        except (OSError, cognitive.CognitiveProjectionConflict) as error:
            raise CognitiveViewConflict((rel,)) from error
        next_path.unlink()
        if prior_path.exists():
            prior_path.unlink()
        replaced += 1
        if fail_after_replacements == replaced:
            raise CognitiveViewError("injected cognitive view publication failure")
    receipt = dict(journal)
    receipt.update(
        {
            "schema_version": "hive-cognitive-view-receipt/v1",
            "status": "committed",
            "committed_at": journal["attempted_at"],
            "verified_manifest_digest": journal["desired_manifest_digest"],
        }
    )
    check = validate_cognitive_view("cognitive-view-receipt-v1", receipt)
    if not check.valid:
        raise CognitiveViewError("view receipt contract failed")
    receipts = state / "receipts"
    receipts.mkdir(exist_ok=True)
    receipt_path = receipts / f"{journal['transaction_id']}.json"
    if receipt_path.exists():
        if (
            _read_json(receipt_path, MAX_STATE_DOCUMENT_BYTES, "view receipt")
            != receipt
        ):
            raise CognitiveViewError("existing view receipt is inconsistent")
    else:
        _write_atomic_evidence(receipt_path, _json_bytes(receipt))
    shutil.rmtree(tx_root)
    transactions = state / "transactions"
    if transactions.exists() and not any(transactions.iterdir()):
        transactions.rmdir()
    return f"protected-state:receipts/{receipt_path.name}"


def _quarantine_preparation(state: Path, preparation: Path) -> None:
    evidence: list[dict[str, str]] = []
    visited = 0
    for path in sorted(preparation.rglob("*")):
        visited += 1
        if visited > 16:
            raise CognitiveViewError("view preparation exceeds path bound")
        rel = path.relative_to(preparation).as_posix()
        if _linklike(path):
            raise CognitiveViewError("view preparation contains a linked path")
        if path.is_file():
            if rel != "transaction.json" and not re.fullmatch(
                r"files/[0-9a-f]{64}", rel
            ):
                raise CognitiveViewError("view preparation evidence path is invalid")
            evidence.append(
                {
                    "path": rel,
                    "digest": _safe_file_digest(
                        path,
                        MAX_STATE_DOCUMENT_BYTES,
                        "abandoned view preparation file",
                    ),
                }
            )
        elif not path.is_dir():
            raise CognitiveViewError("view preparation path type is unsupported")
        elif rel != "files":
            raise CognitiveViewError("view preparation evidence directory is invalid")
    abandonment = {
        "record_kind": "cognitive-view-abandonment",
        "transaction_id": preparation.name,
        "files": evidence,
    }
    identity = _digest_document(abandonment).removeprefix("sha256:")
    abandoned = state / "abandoned"
    abandoned.mkdir(exist_ok=True)
    receipt = abandoned / f"{identity}.json"
    if receipt.exists():
        if (
            _read_json(
                receipt,
                MAX_STATE_DOCUMENT_BYTES,
                "abandoned view preparation receipt",
            )
            != abandonment
        ):
            raise CognitiveViewError(
                "abandoned view preparation receipt is inconsistent"
            )
    else:
        _write_atomic_evidence(receipt, _json_bytes(abandonment))
    destination = abandoned / identity
    try:
        _rename_no_replace(preparation, destination)
    except FileExistsError as error:
        raise CognitiveViewError(
            "abandoned view preparation evidence already exists"
        ) from error
    for item in evidence:
        preserved = destination / Path(*PurePosixPath(item["path"]).parts)
        if (
            _safe_file_digest(
                preserved,
                MAX_STATE_DOCUMENT_BYTES,
                "preserved abandoned view preparation file",
            )
            != item["digest"]
        ):
            raise CognitiveViewError(
                "abandoned view preparation evidence was not preserved"
            )


def _recover_preparations(
    root: Path,
    state: Path,
    cognitive_state: Path,
) -> None:
    preparations = state / "preparations"
    if not preparations.exists():
        return
    if not preparations.is_dir() or _linklike(preparations):
        raise CognitiveViewError("view preparation root is unsafe")
    candidates = sorted(preparations.iterdir())
    if len(candidates) > MAX_PENDING_TRANSACTIONS:
        raise CognitiveViewError("view preparation count exceeds bound")
    for preparation in candidates:
        if (
            not preparation.is_dir()
            or _linklike(preparation)
            or not re.fullmatch(r"[0-9a-f]{64}", preparation.name)
        ):
            raise CognitiveViewError("view preparation path is invalid")
        journal_path = preparation / "transaction.json"
        try:
            journal = _read_json(
                journal_path,
                MAX_STATE_DOCUMENT_BYTES,
                "view preparation journal",
            )
            check = validate_cognitive_view("cognitive-view-transaction-v1", journal)
            if not check.valid:
                raise CognitiveViewError("view preparation journal contract failed")
            _validate_source_receipt_for_journal(cognitive_state, journal)
            _validate_transaction_plan(state, preparation, journal)
        except CognitiveViewError:
            _quarantine_preparation(state, preparation)
            continue
        _preflight_view_siblings(root, journal["operations"], journal["transaction_id"])
        transactions = state / "transactions"
        transactions.mkdir(exist_ok=True)
        sealed = transactions / preparation.name
        try:
            _rename_no_replace(preparation, sealed)
        except FileExistsError as error:
            raise CognitiveViewError(
                "sealed view transaction already exists"
            ) from error
    if preparations.exists() and not any(preparations.iterdir()):
        preparations.rmdir()


def _recover(
    root: Path,
    state: Path,
    cognitive_state: Path,
    authority: AuthorityDecision,
) -> str | None:
    transactions = state / "transactions"
    if not transactions.exists():
        return None
    if not transactions.is_dir() or _linklike(transactions):
        raise CognitiveViewError("view transaction root is unsafe")
    latest: str | None = None
    candidates = sorted(transactions.iterdir())
    if len(candidates) > MAX_PENDING_TRANSACTIONS:
        raise CognitiveViewError("pending view transaction count exceeds bound")
    for tx_root in candidates:
        if (
            not tx_root.is_dir()
            or _linklike(tx_root)
            or not re.fullmatch(r"[0-9a-f]{64}", tx_root.name)
        ):
            raise CognitiveViewError("pending view transaction path is invalid")
        completed_receipt = state / "receipts" / f"{tx_root.name}.json"
        if completed_receipt.exists():
            manifest_path = root / MANIFEST_NAME
            if not manifest_path.exists():
                raise CognitiveViewError(
                    "completed view receipt lacks installed manifest"
                )
            manifest = _read_json(
                manifest_path, MAX_MANIFEST_BYTES, "installed view manifest"
            )
            _validate_view_manifest(manifest)
            manifest_digest = _digest_bytes(manifest_path.read_bytes())
            if (
                manifest_digest != f"sha256:{tx_root.name}"
                or _validated_view_receipt(
                    state, manifest, manifest_digest, cognitive_state
                )
                is None
            ):
                raise CognitiveViewError(
                    "completed view transaction receipt is inconsistent"
                )
            latest = f"protected-state:receipts/{completed_receipt.name}"
            shutil.rmtree(tx_root)
            continue
        journal = _read_json(
            tx_root / "transaction.json",
            MAX_STATE_DOCUMENT_BYTES,
            "pending view transaction",
        )
        check = validate_cognitive_view("cognitive-view-transaction-v1", journal)
        if not check.valid or journal["transaction_id"] != tx_root.name:
            raise CognitiveViewError("pending view transaction contract failed")
        if (
            journal["tenant_id"] != authority.tenant_id
            or journal["repository_id"] != authority.repository_id
        ):
            raise CognitiveViewError(
                "pending view transaction recovery scope is inconsistent"
            )
        _validate_source_receipt_for_journal(cognitive_state, journal)
        latest = _apply_transaction(root, state, tx_root, journal)
    return latest


def _publish(
    root: Path,
    state: Path,
    source: VerifiedCognitiveProjection,
    bundle: CognitiveViewBundle,
    prior: Mapping[str, str],
    prior_manifest: str | None,
    authority: AuthorityDecision,
    clock: Any,
    fail_after_replacements: int | None,
    source_revalidate: Any,
) -> str:
    operations = [
        {
            "path": path,
            "expected_prior_digest": (
                prior_manifest if path == MANIFEST_NAME else prior.get(path)
            ),
            "desired_digest": _digest_bytes(content),
        }
        for path, content in sorted(
            bundle.files.items(), key=lambda item: (item[0] == MANIFEST_NAME, item[0])
        )
    ]
    journal = {
        "schema_version": "hive-cognitive-view-transaction/v1",
        "transaction_id": bundle.manifest_digest.removeprefix("sha256:"),
        "tenant_id": source.tenant_id,
        "repository_id": source.repository_id,
        "repository_identity_digest": source.repository_identity_digest,
        "source_cursor": source.source_cursor,
        "source_manifest_digest": source.manifest_digest,
        "source_receipt_digest": source.source_receipt_digest,
        "prior_manifest_digest": prior_manifest,
        "desired_manifest_digest": bundle.manifest_digest,
        "authority_decision_id": authority.decision_id,
        "authority_actor_id": authority.actor_id,
        "authority_lease_id": authority.lease_id,
        "attempted_at": clock(),
        "operations": operations,
    }
    check = validate_cognitive_view("cognitive-view-transaction-v1", journal)
    if not check.valid:
        raise CognitiveViewError(
            "view transaction contract failed: " + "; ".join(check.issues)
        )
    preparations = state / "preparations"
    preparations.mkdir(exist_ok=True)
    preparation = preparations / journal["transaction_id"]
    preparation.mkdir()
    _write_exclusive(preparation / "transaction.json", _json_bytes(journal))
    staged = preparation / "files"
    staged.mkdir()
    for path, content in bundle.files.items():
        _write_exclusive(staged / sha256(path.encode()).hexdigest(), content)
    transactions = state / "transactions"
    transactions.mkdir(exist_ok=True)
    tx_root = transactions / journal["transaction_id"]
    try:
        _rename_no_replace(preparation, tx_root)
    except FileExistsError as error:
        raise CognitiveViewError("sealed view transaction already exists") from error
    if not any(preparations.iterdir()):
        preparations.rmdir()
    return _apply_transaction(
        root,
        state,
        tx_root,
        journal,
        fail_after_replacements=fail_after_replacements,
        source_revalidate=source_revalidate,
    )


def _preserve_conflict(
    root: Path,
    state: Path,
    bundle: CognitiveViewBundle,
    prior: Mapping[str, str],
    prior_manifest: str | None,
    conflicts: Sequence[str],
    authority: AuthorityDecision,
    clock: Any,
) -> str:
    observed = _observed_tree(root)
    document = {
        "schema_version": "hive-cognitive-view-conflict/v1",
        "status": "conflict",
        "prior_manifest_digest": prior_manifest,
        "desired_manifest_digest": bundle.manifest_digest,
        "authority_decision_id": authority.decision_id,
        "authority_actor_id": authority.actor_id,
        "authority_lease_id": authority.lease_id,
        "attempted_at": clock(),
        "conflicts": [
            {
                "path": path,
                "expected_prior_digest": (
                    prior_manifest if path == MANIFEST_NAME else prior.get(path)
                ),
                "observed_digest": (
                    observed.get(path)
                    if isinstance(observed.get(path), str)
                    and re.fullmatch(r"sha256:[0-9a-f]{64}", observed[path])
                    else None
                ),
                "desired_digest": (
                    _digest_bytes(bundle.files[path]) if path in bundle.files else None
                ),
            }
            for path in sorted(conflicts)
        ],
    }
    check = validate_cognitive_view("cognitive-view-conflict-v1", document)
    if not check.valid:
        raise CognitiveViewError("view conflict contract failed")
    conflict_root = state / "conflicts"
    conflict_root.mkdir(exist_ok=True)
    name = _digest_document(document).removeprefix("sha256:") + ".json"
    path = conflict_root / name
    if path.exists():
        existing = _read_json(path, MAX_STATE_DOCUMENT_BYTES, "existing view conflict")
        existing_check = validate_cognitive_view("cognitive-view-conflict-v1", existing)
        if not existing_check.valid or existing != document:
            raise CognitiveViewError("existing view conflict evidence is inconsistent")
    else:
        _write_atomic_evidence(path, _json_bytes(document))
    return f"protected-state:conflicts/{name}"


def _default_clock() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def project_cognitive_views(
    repository_root: str | Path,
    cognitive_protected_state: str | Path,
    protected_state_root: str | Path,
    *,
    tenant_id: str,
    repository_id: str,
    check: bool = False,
    authority: AuthorityDecision | None = None,
    clock: Any = _default_clock,
    fail_after_replacements: int | None = None,
) -> CognitiveViewResult:
    if fail_after_replacements is not None and fail_after_replacements < 1:
        raise CognitiveViewError("failure injection count must be positive")
    repository = Path(repository_root).absolute()
    cognitive_state = Path(cognitive_protected_state).absolute()
    state_candidate = Path(protected_state_root).absolute()
    if state_candidate.exists():
        if not state_candidate.is_dir() or _linklike(state_candidate):
            raise CognitiveViewError("view protected state is unsafe")
        state = state_candidate.resolve(strict=True)
    else:
        parent = state_candidate.parent.resolve(strict=True)
        if _linklike(state_candidate.parent):
            raise CognitiveViewError("view protected-state parent is unsafe")
        state = parent / state_candidate.name
    _validate_windows_protected_root(state)
    _validate_disjoint((repository, cognitive_state, state))
    root = repository / MANAGED_NAMESPACE
    for ancestor in (root.parent, root):
        if ancestor.exists() and (not ancestor.is_dir() or _linklike(ancestor)):
            raise CognitiveViewError("view namespace ancestry is unsafe")
    if check:
        _validate_view_state(state)
        if _atomic_evidence_paths(state):
            raise CognitiveViewError(
                "view has pending atomic evidence; run item-4 projector"
            )
        before = read_verified_cognitive_projection(
            repository,
            cognitive_state,
            tenant_id=tenant_id,
            repository_id=repository_id,
        )
        bundle = compile_cognitive_views(before)
        view_preparations = state / "preparations"
        if view_preparations.exists() and any(view_preparations.iterdir()):
            raise CognitiveViewError(
                "view has pending preparation; run item-4 projector"
            )
        view_transactions = state / "transactions"
        if view_transactions.exists() and any(view_transactions.iterdir()):
            raise CognitiveViewError(
                "view has pending transactions; run item-4 projector"
            )
        _validate_receipt_reachability(root, state, cognitive_state)
        prior, prior_manifest, owned = _existing_state(
            root, state, cognitive_state, before
        )
        conflicts = _conflicts(root, bundle, prior, prior_manifest, owned)
        after = read_verified_cognitive_projection(
            repository,
            cognitive_state,
            tenant_id=tenant_id,
            repository_id=repository_id,
        )
        if before != after:
            raise CognitiveViewError("cognitive source changed during check")
        status = (
            "conflict"
            if conflicts
            else (
                "unchanged"
                if _observed_tree(root)
                == {
                    path: _digest_bytes(content)
                    for path, content in bundle.files.items()
                }
                else "drift"
            )
        )
        result = CognitiveViewResult(
            "hive-cognitive-view-result/v1",
            status,
            tenant_id,
            repository_id,
            before.repository_identity_digest,
            str(root),
            bundle.manifest_digest,
            before.manifest_digest,
            before.source_cursor,
            bundle.tree_digest,
            4,
            1,
            "read-only",
            conflicts,
            None,
        )
        if not validate_cognitive_view(
            "cognitive-view-result-v1", result.to_document()
        ).valid:
            raise CognitiveViewError("view result contract failed")
        return result
    if (
        authority is None
        or not authority_decision_is_authentic(authority)
        or not authority.allowed
        or authority.foundation_action != "foundation.projection.write"
        or authority.tenant_id != tenant_id
        or authority.repository_id != repository_id
    ):
        raise CognitiveViewError("view projection authority does not allow this scope")
    if not (cognitive_state / "cognitive.lock").is_file():
        raise CognitiveViewError("existing item-3 lock is required")
    with cognitive._lock(cognitive_state):  # type: ignore[attr-defined]
        source = read_verified_cognitive_projection(
            repository,
            cognitive_state,
            tenant_id=tenant_id,
            repository_id=repository_id,
        )
        bundle = compile_cognitive_views(source)

        def revalidate_source() -> None:
            current = read_verified_cognitive_projection(
                repository,
                cognitive_state,
                tenant_id=tenant_id,
                repository_id=repository_id,
            )
            if current != source:
                raise CognitiveViewError("cognitive source changed during publication")

        with _view_lock(state):
            _validate_view_state(state)
            _recover_atomic_evidence(state)
            _validate_view_state(state)
            _recover_preparations(root, state, cognitive_state)
            try:
                recovered = _recover(root, state, cognitive_state, authority)
            except CognitiveViewConflict as conflict:
                receipt = _preserve_conflict(
                    root,
                    state,
                    bundle,
                    {},
                    None,
                    conflict.paths,
                    authority,
                    clock,
                )
                return CognitiveViewResult(
                    "hive-cognitive-view-result/v1",
                    "conflict",
                    tenant_id,
                    repository_id,
                    source.repository_identity_digest,
                    str(root),
                    bundle.manifest_digest,
                    source.manifest_digest,
                    source.source_cursor,
                    bundle.tree_digest,
                    4,
                    1,
                    "conflict-preserved",
                    conflict.paths,
                    receipt,
                )
            _validate_receipt_reachability(root, state, cognitive_state)
            prior, prior_manifest, owned = _existing_state(
                root, state, cognitive_state, source
            )
            conflicts = _conflicts(root, bundle, prior, prior_manifest, owned)
            if conflicts:
                receipt = _preserve_conflict(
                    root,
                    state,
                    bundle,
                    prior,
                    prior_manifest,
                    conflicts,
                    authority,
                    clock,
                )
                return CognitiveViewResult(
                    "hive-cognitive-view-result/v1",
                    "conflict",
                    tenant_id,
                    repository_id,
                    source.repository_identity_digest,
                    str(root),
                    bundle.manifest_digest,
                    source.manifest_digest,
                    source.source_cursor,
                    bundle.tree_digest,
                    4,
                    1,
                    "conflict-preserved",
                    conflicts,
                    receipt,
                )
            desired_digests = {
                path: _digest_bytes(content) for path, content in bundle.files.items()
            }
            if _observed_tree(root) == desired_digests:
                receipt = recovered
                status = "projected" if recovered else "unchanged"
                recovery_status = "recovered" if recovered else "not-required"
            else:
                try:
                    receipt = _publish(
                        root,
                        state,
                        source,
                        bundle,
                        prior,
                        prior_manifest,
                        authority,
                        clock,
                        fail_after_replacements,
                        revalidate_source,
                    )
                except CognitiveViewConflict as conflict:
                    receipt = _preserve_conflict(
                        root,
                        state,
                        bundle,
                        prior,
                        prior_manifest,
                        conflict.paths,
                        authority,
                        clock,
                    )
                    return CognitiveViewResult(
                        "hive-cognitive-view-result/v1",
                        "conflict",
                        tenant_id,
                        repository_id,
                        source.repository_identity_digest,
                        str(root),
                        bundle.manifest_digest,
                        source.manifest_digest,
                        source.source_cursor,
                        bundle.tree_digest,
                        4,
                        1,
                        "conflict-preserved",
                        conflict.paths,
                        receipt,
                    )
                status = "projected"
                recovery_status = "recovered" if recovered else "committed"
            result = CognitiveViewResult(
                "hive-cognitive-view-result/v1",
                status,
                tenant_id,
                repository_id,
                source.repository_identity_digest,
                str(root),
                bundle.manifest_digest,
                source.manifest_digest,
                source.source_cursor,
                bundle.tree_digest,
                4,
                1,
                recovery_status,
                (),
                receipt,
            )
            check_result = validate_cognitive_view(
                "cognitive-view-result-v1", result.to_document()
            )
            if not check_result.valid:
                raise CognitiveViewError(
                    "view result contract failed: " + "; ".join(check_result.issues)
                )
            return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m hive_mind_os.foundation.cognitive_views"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("project", "check"):
        command = commands.add_parser(name)
        command.add_argument("--repo", required=True)
        command.add_argument("--cognitive-protected-state", required=True)
        command.add_argument("--protected-state", required=True)
        command.add_argument("--tenant", required=True)
        command.add_argument("--repository-id", required=True)
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    check = args.command == "check"
    authority = (
        None
        if check
        else decide_foundation_write(
            role=Role.BUILDER,
            action="foundation.projection.write",
            policy_decision=PolicyDecision(
                True, "explicit cognitive view CLI projection"
            ),
            lease_actions={"foundation.projection.write"},
            adapter_actions={"foundation.projection.write"},
            mission_risk_allowed=True,
            budget_available=True,
            tenant_id=args.tenant,
            repository_id=args.repository_id,
            actor_id=VIEW_ACTOR,
            decision_id="decision:cognitive-views-cli",
            lease_id="lease:cognitive-views-cli",
        )
    )
    try:
        result = project_cognitive_views(
            args.repo,
            args.cognitive_protected_state,
            args.protected_state,
            tenant_id=args.tenant,
            repository_id=args.repository_id,
            check=check,
            authority=authority,
        )
    except CognitiveViewError as error:
        print(
            json.dumps(
                {
                    "schema_version": "hive-cognitive-view-failure/v1",
                    "status": "failed",
                    "error": str(error),
                },
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result.to_document(), sort_keys=True))
    return 2 if result.status in {"drift", "conflict"} else 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
