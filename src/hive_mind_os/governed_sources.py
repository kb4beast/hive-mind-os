from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Mapping


@dataclass(frozen=True, slots=True)
class GovernedSourceAudit:
    valid: bool
    source_id: str | None
    inventory_digest: str | None
    issues: tuple[str, ...] = ()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def inventory_digest(records: object) -> str:
    return f"sha256:{sha256(_canonical_bytes(records)).hexdigest()}"


def generate_classic_gpt_all_in_one(
    module_documents: Mapping[str, bytes],
    *,
    repository: str,
    pull_request: int,
    analyzed_head: str,
    load_order: tuple[str, ...],
) -> bytes:
    header = (
        "# HIVE OS CLASSIC GPT — ALL-IN-ONE KNOWLEDGE SOURCE\n\n"
        f"Repository: {repository}\n"
        f"PR: #{pull_request}\n"
        f"Analyzed head: {analyzed_head}\n\n\n"
        "---\n\n"
    ).encode("utf-8")
    parts: list[bytes] = [header]
    for index, path in enumerate(load_order):
        name = PurePosixPath(path).name
        content = module_documents[path]
        parts.append(f"# FILE: {name}\n\n".encode("utf-8"))
        parts.append(content)
        if index < len(load_order) - 1:
            parts.append(b"\n\n---\n\n")
    return b"".join(parts)


def audit_governed_source(snapshot_root: Path) -> GovernedSourceAudit:
    root = snapshot_root.resolve()
    manifest_path = root / "manifest.json"
    issues: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return GovernedSourceAudit(
            False,
            None,
            None,
            (f"cannot read governed source manifest: {type(error).__name__}: {error}",),
        )
    if not isinstance(manifest, dict):
        return GovernedSourceAudit(False, None, None, ("manifest must be an object",))
    source_id = manifest.get("source_id")
    if type(manifest.get("schema_version")) is not int or manifest.get("schema_version") != 1:
        issues.append("unsupported governed source manifest schema")
    if not isinstance(source_id, str) or not source_id.startswith("SRC-"):
        issues.append("manifest has invalid source identity")
    records = manifest.get("files")
    if not isinstance(records, list) or not records:
        return GovernedSourceAudit(
            False,
            source_id if isinstance(source_id, str) else None,
            None,
            tuple((*issues, "manifest requires a non-empty file inventory")),
        )

    expected_paths: list[str] = []
    actual_digest: str | None = None
    for index, record in enumerate(records):
        if not isinstance(record, dict) or set(record) != {
            "path",
            "bytes",
            "sha256",
            "classification",
        }:
            issues.append(f"file record {index} has an invalid shape")
            continue
        path_text = record["path"]
        if not isinstance(path_text, str):
            issues.append(f"file record {index} has a non-string path")
            continue
        path = PurePosixPath(path_text)
        if (
            path.is_absolute()
            or not path.parts
            or path.parts[0] != "raw"
            or ".." in path.parts
            or "\\" in path_text
        ):
            issues.append(f"file record {index} has a nonportable path")
            continue
        if path_text in expected_paths:
            issues.append(f"duplicate inventoried path: {path_text}")
            continue
        expected_paths.append(path_text)
        disk_path = root.joinpath(*path.parts)
        if not disk_path.is_file():
            issues.append(f"missing inventoried file: {path_text}")
            continue
        content = disk_path.read_bytes()
        if type(record["bytes"]) is not int or len(content) != record["bytes"]:
            issues.append(f"byte count mismatch: {path_text}")
        digest = f"sha256:{sha256(content).hexdigest()}"
        if digest != record["sha256"]:
            issues.append(f"digest mismatch: {path_text}")

    raw_root = root / "raw"
    actual_paths = sorted(
        f"raw/{path.relative_to(raw_root).as_posix()}"
        for path in raw_root.rglob("*")
        if path.is_file()
    ) if raw_root.is_dir() else []
    if sorted(expected_paths) != actual_paths:
        extra = sorted(set(actual_paths) - set(expected_paths))
        missing = sorted(set(expected_paths) - set(actual_paths))
        if extra:
            issues.append("uninventoried files: " + ", ".join(extra))
        if missing:
            issues.append("inventory paths absent on disk: " + ", ".join(missing))

    actual_digest = inventory_digest(records)
    if manifest.get("inventory_digest") != actual_digest:
        issues.append("inventory digest does not bind the ordered file records")

    instruction = manifest.get("canonical_instruction_file")
    if instruction not in expected_paths:
        issues.append("canonical instruction file is not inventoried")
    load_order = manifest.get("module_load_order")
    if not isinstance(load_order, list) or any(path not in expected_paths for path in load_order):
        issues.append("module load order references uninventoried bytes")
    elif len(load_order) != len(set(load_order)):
        issues.append("module load order contains duplicates")
    elif manifest.get("generation_recipe") == "classic-gpt-all-in-one-v1":
        historical_manifest_path = root / "raw" / "manifest.json"
        try:
            historical = json.loads(historical_manifest_path.read_text(encoding="utf-8"))
            module_documents = {
                path: root.joinpath(*PurePosixPath(path).parts).read_bytes()
                for path in load_order
            }
            generated = generate_classic_gpt_all_in_one(
                module_documents,
                repository=historical["repository"],
                pull_request=historical["pull_request"],
                analyzed_head=historical["analyzed_head"],
                load_order=tuple(load_order),
            )
            generated_path = manifest.get("generated_all_in_one")
            if not isinstance(generated_path, str) or generated_path not in expected_paths:
                issues.append("generated all-in-one path is not inventoried")
            elif generated != root.joinpath(*PurePosixPath(generated_path).parts).read_bytes():
                issues.append("generated all-in-one bytes differ from canonical modules")
        except (OSError, KeyError, TypeError, UnicodeError, json.JSONDecodeError) as error:
            issues.append(f"cannot reproduce all-in-one source: {type(error).__name__}: {error}")

    if manifest.get("provenance_complete") is not False:
        issues.append("source snapshot incorrectly claims complete provenance")
    if manifest.get("license_spdx") is not None:
        issues.append("source snapshot license must remain unresolved until proven")
    return GovernedSourceAudit(
        not issues,
        source_id if isinstance(source_id, str) else None,
        actual_digest,
        tuple(dict.fromkeys(issues)),
    )
