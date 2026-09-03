"""Content-addressed test results reusable only for one exact candidate context."""

from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .runtime_contracts import (
    canonical_digest,
    canonical_json_bytes,
    require_digest,
    strict_json_object,
)
from .wave_manifest import CandidateIdentity


class TestCacheError(RuntimeError):
    """A cache key, record, or filesystem boundary failed closed."""


class TestOutcome(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


def _is_link_or_reparse_point(path: Path) -> bool:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError as error:
        raise TestCacheError("cache path metadata cannot be inspected") from error
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _absolute_path_without_link_ancestors(path: Path) -> Path:
    absolute = Path(os.path.abspath(os.fspath(path)))
    for component in reversed((absolute, *absolute.parents)):
        if _is_link_or_reparse_point(component):
            raise TestCacheError(
                f"cache path traverses a symbolic link or reparse point: {component}"
            )
    return absolute


def _portable_path(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("working directory is required")
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or ":" in normalized.split("/", 1)[0]:
        raise ValueError("working directory must be relative")
    if any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise ValueError("working directory contains an unsafe segment")
    return PurePosixPath(normalized).as_posix()


@dataclass(frozen=True, slots=True)
class CommandDescriptor:
    argv: tuple[str, ...]
    working_directory: str
    stdin_digest: str | None
    timeout_seconds: int

    def __post_init__(self) -> None:
        if not self.argv or any(
            not isinstance(item, str) or not item for item in self.argv
        ):
            raise ValueError("command argv must contain non-empty strings")
        object.__setattr__(
            self, "working_directory", _portable_path(self.working_directory)
        )
        if self.stdin_digest is not None:
            require_digest(self.stdin_digest, "stdin_digest")
        if type(self.timeout_seconds) is not int or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

    def to_document(self) -> dict[str, Any]:
        return {
            "argv": list(self.argv),
            "working_directory": self.working_directory,
            "stdin_digest": self.stdin_digest,
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> CommandDescriptor:
        if set(value) != {
            "argv",
            "working_directory",
            "stdin_digest",
            "timeout_seconds",
        }:
            raise TestCacheError("command descriptor has an unknown shape")
        argv = value.get("argv")
        if not isinstance(argv, list) or not all(
            isinstance(item, str) for item in argv
        ):
            raise TestCacheError("command argv is malformed")
        try:
            return cls(
                tuple(argv),
                value["working_directory"],
                value["stdin_digest"],
                value["timeout_seconds"],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise TestCacheError("command descriptor is invalid") from error


@dataclass(frozen=True, slots=True)
class TestCacheKey:
    candidate: CandidateIdentity
    command: CommandDescriptor
    test_set_digest: str
    semantic_locks: tuple[str, ...]
    configuration_digest: str
    toolchain_digest: str
    os_identity_digest: str
    safe_environment_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, CandidateIdentity):
            raise ValueError("candidate must be a CandidateIdentity")
        if not isinstance(self.command, CommandDescriptor):
            raise ValueError("command must be a CommandDescriptor")
        for label in (
            "test_set_digest",
            "configuration_digest",
            "toolchain_digest",
            "os_identity_digest",
            "safe_environment_digest",
        ):
            require_digest(getattr(self, label), label)
        if any(not isinstance(item, str) or not item for item in self.semantic_locks):
            raise ValueError("semantic locks must contain non-empty strings")
        if tuple(sorted(set(self.semantic_locks))) != self.semantic_locks:
            raise ValueError("semantic locks must be sorted and unique")

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "candidate": self.candidate.to_document(),
            "command": self.command.to_document(),
            "test_set_digest": self.test_set_digest,
            "semantic_locks": list(self.semantic_locks),
            "configuration_digest": self.configuration_digest,
            "toolchain_digest": self.toolchain_digest,
            "os_identity_digest": self.os_identity_digest,
            "safe_environment_digest": self.safe_environment_digest,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> TestCacheKey:
        fields = {
            "schema_version",
            "candidate",
            "command",
            "test_set_digest",
            "semantic_locks",
            "configuration_digest",
            "toolchain_digest",
            "os_identity_digest",
            "safe_environment_digest",
        }
        candidate = value.get("candidate")
        command = value.get("command")
        locks = value.get("semantic_locks")
        if (
            set(value) != fields
            or type(value.get("schema_version")) is not int
            or value.get("schema_version") != 1
            or not isinstance(candidate, Mapping)
            or not isinstance(command, Mapping)
            or not isinstance(locks, list)
            or not all(isinstance(item, str) for item in locks)
        ):
            raise TestCacheError("test cache key has an unknown shape")
        try:
            return cls(
                candidate=CandidateIdentity.from_document(candidate),
                command=CommandDescriptor.from_document(command),
                test_set_digest=value["test_set_digest"],
                semantic_locks=tuple(locks),
                configuration_digest=value["configuration_digest"],
                toolchain_digest=value["toolchain_digest"],
                os_identity_digest=value["os_identity_digest"],
                safe_environment_digest=value["safe_environment_digest"],
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, TestCacheError):
                raise
            raise TestCacheError("test cache key is invalid") from error


@dataclass(frozen=True, slots=True)
class CachedTestResult:
    key: TestCacheKey
    outcome: TestOutcome
    exit_code: int
    evidence_digest: str
    tool_receipt_digest: str
    record_digest: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.key, TestCacheKey):
            raise ValueError("key must be a TestCacheKey")
        if not isinstance(self.outcome, TestOutcome):
            raise ValueError("outcome must be a TestOutcome")
        if type(self.exit_code) is not int:
            raise ValueError("exit_code must be an integer")
        require_digest(self.evidence_digest, "evidence_digest")
        require_digest(self.tool_receipt_digest, "tool_receipt_digest")
        if self.outcome is TestOutcome.PASSED and self.exit_code != 0:
            raise ValueError("passing test result must have exit code zero")
        if self.outcome is TestOutcome.FAILED and self.exit_code == 0:
            raise ValueError("failed test result cannot have exit code zero")
        expected = canonical_digest(self.to_document(include_digest=False))
        if not self.record_digest:
            object.__setattr__(self, "record_digest", expected)
        elif self.record_digest != expected:
            raise TestCacheError("cached test record digest is invalid")

    def to_document(self, *, include_digest: bool = True) -> dict[str, Any]:
        value: dict[str, Any] = {
            "schema_version": 1,
            "key": self.key.to_document(),
            "key_digest": self.key.digest,
            "outcome": self.outcome.value,
            "exit_code": self.exit_code,
            "evidence_digest": self.evidence_digest,
            "tool_receipt_digest": self.tool_receipt_digest,
        }
        if include_digest:
            value["record_digest"] = self.record_digest
        return value

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> CachedTestResult:
        fields = {
            "schema_version",
            "key",
            "key_digest",
            "outcome",
            "exit_code",
            "evidence_digest",
            "tool_receipt_digest",
            "record_digest",
        }
        key_value = value.get("key")
        if (
            set(value) != fields
            or type(value.get("schema_version")) is not int
            or value.get("schema_version") != 1
            or not isinstance(key_value, Mapping)
        ):
            raise TestCacheError("cached test result has an unknown shape")
        try:
            key = TestCacheKey.from_document(key_value)
            if value["key_digest"] != key.digest:
                raise TestCacheError("cached test key digest is invalid")
            return cls(
                key=key,
                outcome=TestOutcome(value["outcome"]),
                exit_code=value["exit_code"],
                evidence_digest=value["evidence_digest"],
                tool_receipt_digest=value["tool_receipt_digest"],
                record_digest=value["record_digest"],
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, TestCacheError):
                raise
            raise TestCacheError("cached test result is invalid") from error


class TestResultCache:
    """A local content-addressed cache with immutable, verified entries."""

    def __init__(self, root: str | Path) -> None:
        requested = _absolute_path_without_link_ancestors(Path(root))
        if requested.exists() and not requested.is_dir():
            raise TestCacheError("cache root must be a real directory")
        requested.mkdir(parents=True, exist_ok=True)
        requested = _absolute_path_without_link_ancestors(requested)
        self.root = requested.resolve(strict=True)
        root_metadata = os.stat(self.root, follow_symlinks=False)
        self._root_identity = (root_metadata.st_dev, root_metadata.st_ino)

    def _assert_root_unchanged(self) -> None:
        _absolute_path_without_link_ancestors(self.root)
        if not self.root.is_dir() or _is_link_or_reparse_point(self.root):
            raise TestCacheError("cache root is no longer a real directory")
        try:
            metadata = os.stat(self.root, follow_symlinks=False)
        except OSError as error:
            raise TestCacheError("cache root cannot be inspected") from error
        if (metadata.st_dev, metadata.st_ino) != self._root_identity:
            raise TestCacheError("cache root identity changed")

    def _path(self, key: TestCacheKey) -> Path:
        self._assert_root_unchanged()
        return self.root / f"{key.digest.removeprefix('sha256:')}.json"

    def _failure_path(self, result: CachedTestResult) -> Path:
        self._assert_root_unchanged()
        key_digest = result.key.digest.removeprefix("sha256:")
        record_digest = result.record_digest.removeprefix("sha256:")
        # Keep failure evidence flat under the authenticated root. A nested
        # ``failures`` directory would introduce an attacker-replaceable path
        # component before the final hard-link publication.
        return self.root / f"failure-{key_digest}-{record_digest}.json"

    def publish(self, result: CachedTestResult) -> Path:
        destination = (
            self._path(result.key)
            if result.outcome is TestOutcome.PASSED
            else self._failure_path(result)
        )
        encoded = canonical_json_bytes(result.to_document())
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink() or not destination.is_file():
                raise TestCacheError("cache entry path is not a regular file")
            try:
                existing = destination.read_bytes()
            except OSError as error:
                raise TestCacheError("cache entry cannot be read") from error
            if existing != encoded:
                raise TestCacheError("cache key is already bound to another result")
            return destination
        handle_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.root, delete=False) as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
                handle_name = handle.name
            try:
                self._assert_root_unchanged()
                os.link(handle_name, destination)
            except FileExistsError as error:
                if destination.is_symlink() or not destination.is_file():
                    raise TestCacheError(
                        "concurrent cache publication found an unsafe path"
                    ) from error
                try:
                    existing = destination.read_bytes()
                except OSError as read_error:
                    raise TestCacheError(
                        "concurrent cache entry cannot be read"
                    ) from read_error
                if existing != encoded:
                    raise TestCacheError("concurrent cache publication conflicts")
            return destination
        finally:
            if handle_name is not None:
                try:
                    os.unlink(handle_name)
                except FileNotFoundError:
                    pass

    def lookup(self, key: TestCacheKey) -> CachedTestResult | None:
        path = self._path(key)
        if not path.exists() and not path.is_symlink():
            return None
        if path.is_symlink() or not path.is_file():
            raise TestCacheError("cache entry is not a regular file")
        try:
            raw = path.read_bytes()
            value = strict_json_object(raw)
        except (OSError, UnicodeError, ValueError) as error:
            raise TestCacheError("cache entry is corrupt") from error
        result = CachedTestResult.from_document(value)
        if raw != canonical_json_bytes(result.to_document()):
            raise TestCacheError("cache entry is not canonical")
        if result.key != key or result.key.digest != key.digest:
            raise TestCacheError("cache entry belongs to another exact key")
        # Failure observations remain available as evidence but are never a
        # reason to skip execution in a later control decision.
        return result if result.outcome is TestOutcome.PASSED else None


__all__ = [
    "CachedTestResult",
    "CommandDescriptor",
    "TestCacheError",
    "TestCacheKey",
    "TestOutcome",
    "TestResultCache",
]
