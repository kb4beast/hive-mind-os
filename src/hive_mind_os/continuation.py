"""Strict, local-only continuation packets for safe replacement sessions.

This additive contract does not alter mission state or the legacy handoff schema.  It
binds a short, structured resumption instruction to one clean local Git worktree and
content-addressed local evidence.  It never captures model/chat transcripts or secrets.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .contracts import validate_contract
from .receipts import path_traverses_link_or_reparse_point, portable_path_parts, sha256_digest

_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SAFE_TEXT = re.compile(r"[A-Za-z0-9][A-Za-z0-9 .,:;()/_-]*\Z")
_FORBIDDEN_TEXT = re.compile(
    r"(?i)(api[_ -]?key|authorization|bearer[ _-]|password|secret|"
    r"sk-[a-z0-9_-]{8,}|gh[pousr]_[a-z0-9_]{8,})"
)
_SOURCE_FIELDS = frozenset(
    {
        "schema_version", "packet_id", "created_at", "objective", "scope",
        "granted_authority", "forbidden_authority", "artifact_paths", "decision",
        "reason", "independent_verification", "blockers", "next_action", "resume_instruction",
    }
)
_REQUIRED_FORBIDDEN = frozenset(
    {"network", "remote_git", "credentials", "secrets", "external_message", "deploy", "payment", "policy_mutation"}
)


class ContinuationPacketError(ValueError):
    """A continuation packet is malformed, stale, or unsafe to resume."""


@dataclass(frozen=True, slots=True)
class PacketValidation:
    valid: bool
    issues: tuple[str, ...] = ()


def _canonical_bytes(document: Mapping[str, Any]) -> bytes:
    payload = {key: value for key, value in document.items() if key != "integrity"}
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def canonical_digest(document: Mapping[str, Any]) -> str:
    """Return the digest binding every packet field except its digest wrapper."""

    return sha256_digest(_canonical_bytes(document))


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
        timeout=30,
    )
    if completed.returncode:
        raise ContinuationPacketError("local Git repository could not be verified")
    return completed.stdout.decode("utf-8", "strict").strip()


def _repository_root(repository: str | Path) -> Path:
    supplied = Path(repository).resolve()
    if not supplied.is_dir():
        raise ContinuationPacketError("repository must be an existing directory")
    return Path(_git(supplied, "rev-parse", "--show-toplevel")).resolve()


def _safe_text(value: object, label: str, issues: list[str]) -> None:
    if not isinstance(value, str) or not _SAFE_TEXT.fullmatch(value):
        issues.append(f"{label} must be a short plain-English summary")
    elif _FORBIDDEN_TEXT.search(value):
        issues.append(f"{label} contains a prohibited secret-like marker")


def _safe_identifier(value: object, label: str, issues: list[str]) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value) is None:
        issues.append(f"{label} must be a single-line safe identifier")
    elif _FORBIDDEN_TEXT.search(value):
        issues.append(f"{label} contains a prohibited secret-like marker")


def _verify_artifact(root: Path, reference: object, issues: list[str]) -> None:
    if not isinstance(reference, Mapping):
        return
    raw_path = reference.get("path")
    digest = reference.get("digest")
    if not isinstance(raw_path, str) or not isinstance(digest, str):
        return
    try:
        parts = portable_path_parts(raw_path)
    except ValueError:
        return
    candidate = root.joinpath(*parts)
    if path_traverses_link_or_reparse_point(candidate):
        issues.append(f"artifact {raw_path} traverses a link or reparse point")
        return
    if not candidate.is_file():
        issues.append(f"artifact {raw_path} is not a regular file")
        return
    if sha256_digest(candidate.read_bytes()) != digest:
        issues.append(f"artifact {raw_path} digest mismatch")


def validate_packet(
    document: object,
    repository: str | Path,
) -> PacketValidation:
    """Verify structure, semantics, local evidence, and current Git binding."""

    structural = validate_contract("continuation-packet", document)
    issues = list(structural.issues)
    if not isinstance(document, Mapping):
        return PacketValidation(False, tuple(issues))
    try:
        root = _repository_root(repository)
    except ContinuationPacketError as error:
        return PacketValidation(False, tuple(issues + [str(error)]))

    integrity = document.get("integrity")
    try:
        observed_digest = canonical_digest(document)
    except (TypeError, ValueError, UnicodeError):
        issues.append("packet cannot be canonically digested")
    else:
        if not isinstance(integrity, Mapping) or integrity.get("canonical_digest") != observed_digest:
            issues.append("packet canonical digest mismatch")

    repository_record = document.get("repository")
    if isinstance(repository_record, Mapping):
        if repository_record.get("path") != root.as_posix():
            issues.append("repository path policy does not match this local worktree")
        expected_commit = repository_record.get("expected_commit")
        if isinstance(expected_commit, str):
            try:
                _git(root, "cat-file", "-e", f"{expected_commit}^{{commit}}")
                if _git(root, "rev-parse", "HEAD") != expected_commit:
                    issues.append("repository HEAD is stale relative to the packet")
            except ContinuationPacketError as error:
                issues.append(str(error))
        if _git(root, "status", "--porcelain=v1", "--untracked-files=all"):
            issues.append("repository worktree is not clean")

    granted = document.get("granted_authority")
    forbidden = document.get("forbidden_authority")
    if isinstance(granted, list) and isinstance(forbidden, list):
        if set(granted) & set(forbidden):
            issues.append("granted authority overlaps forbidden authority")
        missing = _REQUIRED_FORBIDDEN - set(forbidden)
        if missing:
            issues.append("required forbidden authority is missing: " + ", ".join(sorted(missing)))

    decision = document.get("decision")
    reason = document.get("reason")
    _safe_identifier(document.get("packet_id"), "packet identifier", issues)
    if decision in {"approved", "no-decision"} and reason is not None:
        issues.append("approval or no-decision packet must not include a reason")
    if reason is not None:
        _safe_text(reason, "reason", issues)
    verification = document.get("independent_verification")
    if isinstance(verification, list):
        if decision == "no-decision" and verification:
            issues.append("no-decision packet must not claim independent verification")
        if decision != "no-decision" and not verification:
            issues.append("a decided packet requires independent verification")
        for index, record in enumerate(verification):
            if isinstance(record, Mapping):
                _safe_identifier(record.get("verifier_id"), f"verifier {index}", issues)
                if record.get("decision") != decision:
                    issues.append(f"independent verification {index} does not preserve the packet decision")
    _safe_text(document.get("objective"), "objective", issues)
    _safe_text(document.get("scope"), "scope", issues)
    _safe_text(document.get("resume_instruction"), "resume instruction", issues)

    blockers = document.get("blockers")
    if isinstance(blockers, list):
        for index, blocker in enumerate(blockers):
            if isinstance(blocker, Mapping):
                _safe_text(blocker.get("summary"), f"blocker {index}", issues)
    next_action = document.get("next_action")
    if isinstance(next_action, Mapping):
        for field in ("action", "success_condition", "stopping_condition"):
            _safe_text(next_action.get(field), f"next action {field}", issues)

    artifacts = document.get("verified_artifacts")
    if isinstance(artifacts, list):
        for artifact in artifacts:
            _verify_artifact(root, artifact, issues)
    return PacketValidation(not issues, tuple(dict.fromkeys(issues)))


def export_packet(source: Mapping[str, Any], repository: str | Path) -> dict[str, Any]:
    """Create a deterministic packet from a short structured local source document."""

    unknown = set(source) - _SOURCE_FIELDS
    missing = _SOURCE_FIELDS - set(source) - {"reason"}
    if unknown or missing:
        details = []
        if unknown:
            details.append("unknown source fields: " + ", ".join(sorted(unknown)))
        if missing:
            details.append("missing source fields: " + ", ".join(sorted(missing)))
        raise ContinuationPacketError("; ".join(details))
    root = _repository_root(repository)
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ContinuationPacketError("repository worktree must be clean before export")
    artifact_paths = source.get("artifact_paths")
    if not isinstance(artifact_paths, list):
        raise ContinuationPacketError("artifact_paths must be a list")
    artifacts: list[dict[str, str]] = []
    for raw_path in artifact_paths:
        if not isinstance(raw_path, str):
            raise ContinuationPacketError("artifact path must be a string")
        try:
            parts = portable_path_parts(raw_path)
        except ValueError as error:
            raise ContinuationPacketError(f"artifact path is unsafe: {error}") from None
        candidate = root.joinpath(*parts)
        if path_traverses_link_or_reparse_point(candidate) or not candidate.is_file():
            raise ContinuationPacketError("artifact must be a regular local file without links")
        artifacts.append({"path": raw_path, "digest": sha256_digest(candidate.read_bytes())})
    if len({item["path"] for item in artifacts}) != len(artifacts):
        raise ContinuationPacketError("artifact paths must be unique")
    packet = {key: value for key, value in source.items() if key != "artifact_paths"}
    packet["repository"] = {
        "path_policy": "absolute-local-path",
        "path": root.as_posix(),
        "expected_commit": _git(root, "rev-parse", "HEAD"),
        "worktree_clean": True,
    }
    packet["verified_artifacts"] = artifacts
    packet["integrity"] = {"algorithm": "sha256", "canonical_digest": canonical_digest(packet)}
    validation = validate_packet(packet, root)
    if not validation.valid:
        raise ContinuationPacketError("packet is unsafe: " + "; ".join(validation.issues))
    return packet


def write_packet(packet: Mapping[str, Any], output: str | Path, repository: str | Path) -> Path:
    """Write one new packet outside its bound repository without overwriting evidence."""

    root = _repository_root(repository)
    target = Path(output).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        pass
    else:
        raise ContinuationPacketError("packet output must be outside the bound repository")
    validation = validate_packet(packet, root)
    if not validation.valid:
        raise ContinuationPacketError("packet is unsafe: " + "; ".join(validation.issues))
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    try:
        with target.open("xb") as stream:
            stream.write(encoded)
    except FileExistsError as error:
        raise ContinuationPacketError("packet output already exists") from error
    return target
