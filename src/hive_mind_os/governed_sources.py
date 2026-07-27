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


def governance_digest(manifest: Mapping[str, object]) -> str:
    bound = {key: value for key, value in manifest.items() if key != "governance_digest"}
    return f"sha256:{sha256(_canonical_bytes(bound)).hexdigest()}"


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
    expected_manifest_keys = {
        "schema_version",
        "source_id",
        "title",
        "source_uri",
        "captured_at",
        "license_spdx",
        "provenance_complete",
        "canonical_instruction_file",
        "module_load_order",
        "generated_all_in_one",
        "generation_recipe",
        "inventory_digest",
        "governance_digest",
        "files",
        "historical_manifest_corrections",
        "relationships",
        "image_exhibits",
        "blocking_obligations",
    }
    if set(manifest) != expected_manifest_keys:
        issues.append("governed source manifest has an invalid shape")
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
    try:
        actual_governance_digest = governance_digest(manifest)
    except (TypeError, ValueError, UnicodeError):
        issues.append("governed source manifest is not canonical JSON")
    else:
        if manifest.get("governance_digest") != actual_governance_digest:
            issues.append("governance digest does not bind source adjudication metadata")

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
    relationships = manifest.get("relationships")
    expected_relationships = {
        (
            "SRC-022",
            "refines_and_expands",
            "Preserve both sources. SRC-023 supplies a broader earlier simulation pack; "
            "SRC-022 supplies later truth-boundary and receipt hardening. Neither silently "
            "supersedes the other.",
        ),
        (
            "SRC-002",
            "possible_common_origin",
            "imgo.jpg is a new non-independent exhibit with unresolved chain of custody. "
            "Its digest does not replace the pseudo digest or missing original bytes "
            "recorded for SRC-002.",
        ),
    }
    if not isinstance(relationships, list) or any(
        not isinstance(item, dict)
        or set(item) != {"target_source_id", "relationship", "adjudication"}
        or any(not isinstance(item.get(key), str) for key in item)
        for item in relationships
    ):
        issues.append("source relationships have an invalid shape")
    else:
        observed_relationships = {
            (
                item["target_source_id"],
                item["relationship"],
                item["adjudication"],
            )
            for item in relationships
        }
        if observed_relationships != expected_relationships:
            issues.append("source relationships do not preserve the adjudicated overlap")

    exhibits = manifest.get("image_exhibits")
    if not isinstance(exhibits, list) or len(exhibits) != 2:
        issues.append("image exhibits have an invalid shape")
    else:
        exhibits_by_path: dict[object, dict[str, object]] = {}
        for item in exhibits:
            if not isinstance(item, dict) or set(item) != {
                "path",
                "related_source_ids",
                "independent",
                "chain_of_custody",
                "evidence_use",
            }:
                issues.append("image exhibit has an invalid shape")
                continue
            path_value = item.get("path")
            if not isinstance(path_value, str):
                issues.append("image exhibit has a non-string path")
                continue
            exhibits_by_path[path_value] = item
        expected_exhibits = {
            "raw/imgo.jpg": {
                "related_source_ids": ["SRC-002", "SRC-023"],
                "independent": False,
                "chain_of_custody": "unresolved",
                "evidence_use": "context_only_until_chain_of_custody_is_resolved",
            },
            "raw/Logo.png": {
                "related_source_ids": ["SRC-022", "SRC-023"],
                "independent": False,
                "chain_of_custody": "user-supplied-derived-visual",
                "evidence_use": "derived_summary_not_independent_proof",
            },
        }
        if set(exhibits_by_path) != set(expected_exhibits):
            issues.append("image exhibit inventory is incomplete")
        else:
            for path, expected in expected_exhibits.items():
                observed = exhibits_by_path[path]
                if any(observed.get(key) != value for key, value in expected.items()):
                    issues.append(f"image exhibit adjudication changed: {path}")

    expected_obligations = {
        "Resolve a compatible license or explicit reuse grant.",
        "Resolve authorship and chain of custody for the pack and imgo.jpg.",
        "Do not treat Logo.png as independent proof of its underlying architecture claims.",
    }
    obligations = manifest.get("blocking_obligations")
    if (
        not isinstance(obligations, list)
        or len(obligations) != len(set(obligations))
        or set(obligations) != expected_obligations
    ):
        issues.append("source blocking obligations are incomplete")
    return GovernedSourceAudit(
        not issues,
        source_id if isinstance(source_id, str) else None,
        actual_digest,
        tuple(dict.fromkeys(issues)),
    )
