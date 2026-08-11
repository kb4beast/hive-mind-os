"""Confined, receipt-producing repository discovery for the Explorer role.

The Explorer is deliberately a read-only observation boundary.  Repository text and
command output are returned as untrusted data; neither is interpreted as an
instruction or passed to a shell.  Source intake records preserve the information a
later courtroom process needs, but do not admit, approve, or mutate a source.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

from .canonical import canonical_digest

_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_RFC3339 = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z")
_GIT_SUBCOMMANDS = frozenset({"diff", "log", "ls-files", "rev-parse", "show", "status"})


class ExplorerDenied(ValueError):
    """An Explorer request would escape its read-only, local boundary."""


def _digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _rfc3339(value: str, label: str) -> None:
    if not isinstance(value, str) or _RFC3339.fullmatch(value) is None:
        raise ExplorerDenied(f"{label} must be RFC 3339 with an explicit offset")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ExplorerDenied(f"{label} must be RFC 3339 with an explicit offset") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExplorerDenied(f"{label} must include an explicit offset")


@dataclass(frozen=True, slots=True)
class RepositoryText:
    """A repository observation which is explicitly inert, untrusted data."""

    path: str
    content: str
    content_digest: str
    trust_boundary: str = "untrusted-repository-data"

    def __post_init__(self) -> None:
        if not self.path or self.path.startswith("/") or "\\" in self.path:
            raise ExplorerDenied("repository text path must be a portable relative path")
        if self.trust_boundary != "untrusted-repository-data":
            raise ExplorerDenied("repository text must retain its untrusted boundary")
        if self.content_digest != _digest(self.content.encode("utf-8")):
            raise ExplorerDenied("repository text digest does not match its content")


@dataclass(frozen=True, slots=True)
class CommandReceipt:
    """An immutable receipt for one allowlisted local observation command."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    stdout_digest: str
    stderr_digest: str
    trust_boundary: str = "untrusted-command-output"

    def __post_init__(self) -> None:
        if not self.argv or any(not isinstance(item, str) or not item for item in self.argv):
            raise ExplorerDenied("command receipt requires a non-empty argv")
        if self.stdout_digest != _digest(self.stdout.encode("utf-8")):
            raise ExplorerDenied("command stdout digest does not match")
        if self.stderr_digest != _digest(self.stderr.encode("utf-8")):
            raise ExplorerDenied("command stderr digest does not match")
        if self.trust_boundary != "untrusted-command-output":
            raise ExplorerDenied("command output must retain its untrusted boundary")

    @property
    def receipt_digest(self) -> str:
        return canonical_digest(
            {
                "argv": self.argv,
                "returncode": self.returncode,
                "stdout_digest": self.stdout_digest,
                "stderr_digest": self.stderr_digest,
                "trust_boundary": self.trust_boundary,
            }
        )


@dataclass(frozen=True, slots=True)
class SourceIntake:
    """Provenance-complete source metadata awaiting independent court review."""

    source_uri: str
    version_ref: str
    content_digest: str
    retrieved_at: str
    license_spdx: str | None
    provenance_complete: bool
    source_text: str = ""
    trust_boundary: str = "untrusted-source-data"

    def __post_init__(self) -> None:
        if not isinstance(self.source_uri, str) or "://" not in self.source_uri:
            raise ExplorerDenied("source URI is required")
        if not isinstance(self.version_ref, str) or not self.version_ref:
            raise ExplorerDenied("source version or immutable digest is required")
        if _SHA256.fullmatch(self.content_digest) is None:
            raise ExplorerDenied("source content digest must be SHA-256")
        _rfc3339(self.retrieved_at, "source retrieval time")
        if self.license_spdx is not None and (not isinstance(self.license_spdx, str) or not self.license_spdx):
            raise ExplorerDenied("source license must be a non-empty string or null")
        if type(self.provenance_complete) is not bool:
            raise ExplorerDenied("source provenance completeness must be boolean")
        if self.trust_boundary != "untrusted-source-data":
            raise ExplorerDenied("source text must retain its untrusted boundary")

    @property
    def intake_digest(self) -> str:
        return canonical_digest(
            {
                "source_uri": self.source_uri,
                "version_ref": self.version_ref,
                "content_digest": self.content_digest,
                "retrieved_at": self.retrieved_at,
                "license_spdx": self.license_spdx,
                "provenance_complete": self.provenance_complete,
                "source_text_digest": _digest(self.source_text.encode("utf-8")),
                "trust_boundary": self.trust_boundary,
            }
        )


class RepositoryExplorer:
    """Run a small closed set of repository observations without mutation rights."""

    def __init__(self, repository_root: str | Path) -> None:
        root = Path(repository_root).resolve()
        if not root.is_dir() or not (root / ".git").exists():
            raise ExplorerDenied("repository root must be a Git working tree")
        self.root = root

    def _path(self, relative_path: str) -> tuple[str, Path]:
        if not isinstance(relative_path, str) or not relative_path:
            raise ExplorerDenied("repository path is required")
        candidate = Path(relative_path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ExplorerDenied("repository path must stay below the repository root")
        resolved = (self.root / candidate).resolve()
        try:
            portable = resolved.relative_to(self.root).as_posix()
        except ValueError as error:
            raise ExplorerDenied("repository path escapes the repository root") from error
        if resolved.is_symlink() or not resolved.is_file():
            raise ExplorerDenied("repository path must name a regular file")
        return portable, resolved

    def read_text(self, relative_path: str, *, max_bytes: int = 1_000_000) -> RepositoryText:
        """Read one confined UTF-8 file as data, never as an instruction."""

        if type(max_bytes) is not int or max_bytes < 1:
            raise ExplorerDenied("maximum bytes must be a positive integer")
        portable, path = self._path(relative_path)
        content = path.read_bytes()
        if len(content) > max_bytes:
            raise ExplorerDenied("repository text exceeds the configured read limit")
        try:
            decoded = content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ExplorerDenied("repository text must be UTF-8") from error
        return RepositoryText(portable, decoded, _digest(content))

    def discover_tests(self) -> tuple[str, ...]:
        """List conventional test files without importing or executing their code."""

        tests = self.root / "tests"
        if not tests.is_dir():
            return ()
        return tuple(
            sorted(
                path.relative_to(self.root).as_posix()
                for path in tests.rglob("test_*.py")
                if path.is_file() and not path.is_symlink()
            )
        )

    @staticmethod
    def _approved(argv: Sequence[str]) -> tuple[str, ...]:
        normalized = tuple(argv)
        if not normalized or any(not isinstance(part, str) or not part for part in normalized):
            raise ExplorerDenied("command must be a non-empty argv sequence")
        if normalized[0] == "git" and len(normalized) >= 2 and normalized[1] in _GIT_SUBCOMMANDS:
            if any(part in {"-C", "--work-tree", "--git-dir"} for part in normalized[2:]):
                raise ExplorerDenied("Git repository redirection is not allowed")
            return normalized
        if normalized == ("rg", "--files"):
            return normalized
        raise ExplorerDenied("Explorer command is not on the read-only allowlist")

    def run(self, argv: Sequence[str], *, timeout_seconds: int = 30) -> CommandReceipt:
        """Execute an allowlisted observation command without a shell."""

        command = self._approved(argv)
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 60:
            raise ExplorerDenied("command timeout must be between one and sixty seconds")
        try:
            completed = subprocess.run(
                command,
                cwd=self.root,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ExplorerDenied(f"approved observation command could not complete: {type(error).__name__}") from error
        return CommandReceipt(
            command,
            completed.returncode,
            completed.stdout,
            completed.stderr,
            _digest(completed.stdout.encode("utf-8")),
            _digest(completed.stderr.encode("utf-8")),
        )

    @staticmethod
    def retain_source_intake(intake: SourceIntake) -> SourceIntake:
        """Return typed source data without admitting it or changing repository state."""

        return intake
