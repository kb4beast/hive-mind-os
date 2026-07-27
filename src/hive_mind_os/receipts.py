from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Mapping, Protocol


_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_RFC3339_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z"
)


def _portable_path_parts(value: str) -> tuple[str, ...]:
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or re.match(r"^[A-Za-z]:", value)
    ):
        raise ValueError("path must use portable relative POSIX syntax")
    raw_parts = value.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ValueError("path must not contain empty, current, or parent segments")
    normalized = PurePosixPath(*raw_parts).as_posix()
    if normalized != value:
        raise ValueError("path must use canonical portable relative POSIX syntax")
    return tuple(raw_parts)


class ReceiptResult(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ReceiptReference:
    """A content-addressed pointer into an explicitly trusted receipt store."""

    path: str
    digest: str

    def __post_init__(self) -> None:
        if not self.path.strip():
            raise ValueError("receipt path is required")
        _portable_path_parts(self.path)
        if not _SHA256_PATTERN.fullmatch(self.digest):
            raise ValueError("receipt digest must be lowercase sha256:<64 hex>")


@dataclass(frozen=True, slots=True)
class ReceiptValidation:
    valid: bool
    succeeded: bool
    issues: tuple[str, ...] = ()
    receipt_id: str | None = None


def sha256_digest(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


class ReceiptValidator(Protocol):
    def validate(
        self,
        reference: ReceiptReference,
        *,
        mission_id: str,
        state_ref: str,
        actor_id: str,
        action_id: str,
        action_kind: str,
        action_digest: str,
    ) -> ReceiptValidation: ...


class FileReceiptValidator:
    """Read-only structural verifier for local enforcement-point receipt artifacts."""

    def __init__(self, trusted_root: str | Path) -> None:
        root = Path(trusted_root).resolve()
        if not root.is_dir():
            raise ValueError("trusted receipt root must be an existing directory")
        self.trusted_root = root

    def _read_bound_file(
        self,
        relative_path: object,
        expected_digest: object,
        *,
        label: str,
    ) -> tuple[bytes | None, list[str]]:
        issues: list[str] = []
        if not isinstance(relative_path, str) or not relative_path.strip():
            return None, [f"{label} path is required"]
        if not isinstance(expected_digest, str) or not _SHA256_PATTERN.fullmatch(expected_digest):
            return None, [f"{label} digest must be lowercase sha256:<64 hex>"]

        try:
            path_parts = _portable_path_parts(relative_path)
        except ValueError as error:
            return None, [f"{label} {error}"]
        candidate = Path(*path_parts)
        resolved = (self.trusted_root / candidate).resolve()
        try:
            resolved.relative_to(self.trusted_root)
        except ValueError:
            return None, [f"{label} path escapes the trusted root"]
        if not resolved.is_file():
            return None, [f"{label} path is not a regular file"]

        try:
            content = resolved.read_bytes()
        except OSError as error:
            return None, [f"{label} could not be read: {type(error).__name__}"]
        observed_digest = sha256_digest(content)
        if observed_digest != expected_digest:
            issues.append(f"{label} digest mismatch")
        return content, issues

    def validate(
        self,
        reference: ReceiptReference,
        *,
        mission_id: str,
        state_ref: str,
        actor_id: str,
        action_id: str,
        action_kind: str,
        action_digest: str,
    ) -> ReceiptValidation:
        content, issues = self._read_bound_file(
            reference.path,
            reference.digest,
            label="receipt",
        )
        if content is None or issues:
            return ReceiptValidation(False, False, tuple(issues))

        try:
            document = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return ReceiptValidation(False, False, ("receipt must be UTF-8 JSON",))
        if not isinstance(document, Mapping):
            return ReceiptValidation(False, False, ("receipt must be a JSON object",))

        if type(document.get("schema_version")) is not int or document.get("schema_version") != 1:
            issues.append("unsupported receipt schema version")

        receipt_id = document.get("receipt_id")
        for field_name in (
            "receipt_id",
            "provider",
            "execution_id",
            "policy_decision_ref",
            "lease_id",
            "observed_at",
            "verified_by",
        ):
            value = document.get(field_name)
            if not isinstance(value, str) or not value.strip():
                issues.append(f"receipt {field_name} is required")

        expected_bindings = {
            "mission_id": mission_id,
            "state_ref": state_ref,
            "actor_id": actor_id,
            "action_id": action_id,
            "action_kind": action_kind,
            "action_digest": action_digest,
        }
        for field_name, expected in expected_bindings.items():
            if document.get(field_name) != expected:
                issues.append(f"receipt {field_name} does not match the action")

        if document.get("verified_by") == actor_id:
            issues.append("receipt verifier must be independent from the acting identity")

        observed_at = document.get("observed_at")
        if isinstance(observed_at, str) and observed_at.strip():
            if not _RFC3339_PATTERN.fullmatch(observed_at):
                issues.append("receipt observed_at must be RFC 3339")
            try:
                parsed_time = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
            except ValueError:
                issues.append("receipt observed_at must be RFC 3339")
            else:
                if parsed_time.tzinfo is None:
                    issues.append("receipt observed_at must include a timezone")

        if document.get("executed") is not True:
            issues.append("receipt does not prove execution")

        raw_result = document.get("result")
        try:
            result = ReceiptResult(raw_result)
        except (TypeError, ValueError):
            issues.append("receipt result is unsupported")
            result = None

        artifacts = document.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            issues.append("receipt must identify at least one artifact")
        else:
            for index, artifact in enumerate(artifacts):
                if not isinstance(artifact, Mapping):
                    issues.append(f"artifact {index} must be an object")
                    continue
                _, artifact_issues = self._read_bound_file(
                    artifact.get("path"),
                    artifact.get("digest"),
                    label=f"artifact {index}",
                )
                issues.extend(artifact_issues)

        return ReceiptValidation(
            valid=not issues,
            succeeded=not issues and result is ReceiptResult.SUCCEEDED,
            issues=tuple(dict.fromkeys(issues)),
            receipt_id=receipt_id if isinstance(receipt_id, str) and receipt_id.strip() else None,
        )
