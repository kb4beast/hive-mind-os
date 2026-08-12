"""Confined, receipt-producing repository discovery for the Explorer role.

Repository text and command output are untrusted data.  Git observations use a
closed, purpose-specific grammar: callers supply typed values, never arbitrary
Git argv.  This prevents a seemingly read-only option from becoming a write or
configuration escape.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .canonical import canonical_digest

_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_COMMIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
_RFC3339 = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z")
_BLOCKED_GIT_TOKENS = frozenset({"--output", "--ext-diff", "--textconv", "--refresh", "-c", "--git-dir", "--work-tree", "-C"})
_TRUSTED_GIT_DIRECTORIES = (
    Path("C:/Program Files/Git/cmd"),
    Path("C:/Program Files/Git/bin"),
    Path("/usr/bin"),
    Path("/bin"),
)


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
    """Perform a closed set of read-only repository observations with receipts."""

    def __init__(self, repository_root: str | Path) -> None:
        root = Path(repository_root).resolve()
        if not root.is_dir() or not (root / ".git").exists():
            raise ExplorerDenied("repository root must be a Git working tree")
        self.root = root
        self.git_executable = self._trusted_git_executable()

    @staticmethod
    def _trusted_git_executable() -> Path:
        """Resolve Git only from an OS-managed absolute location, never PATH."""

        executable_names = ("git.exe", "git") if os.name == "nt" else ("git",)
        for directory in _TRUSTED_GIT_DIRECTORIES:
            for executable_name in executable_names:
                candidate = directory / executable_name
                if candidate.is_file() and not candidate.is_symlink():
                    return candidate.resolve()
        raise ExplorerDenied("a trusted absolute Git executable is required")

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
    def _commit_sha(value: str, label: str) -> str:
        if not isinstance(value, str) or _COMMIT_SHA.fullmatch(value) is None:
            raise ExplorerDenied(f"{label} must be exactly a lowercase 40-character Git commit SHA")
        return value

    def _git_environment(self) -> dict[str, str]:
        """Create the entire Git environment; inherited ``GIT_*`` is rejected."""

        if any(key.upper().startswith("GIT_") for key in os.environ):
            raise ExplorerDenied("inherited Git environment injection is not allowed")
        environment: dict[str, str] = {}
        for key in ("COMSPEC", "SYSTEMROOT", "TEMP", "TMP", "WINDIR"):
            value = os.environ.get(key)
            if value:
                environment[key] = value
        environment.update(
            {
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_PAGER": "cat",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "PATH": str(self.git_executable.parent),
            }
        )
        return environment

    @staticmethod
    def _validate_command(command: tuple[str, ...]) -> tuple[str, ...]:
        """Defend the internal boundary too: no unsafe Git option may be spawned."""

        if not command or command[0] != "git":
            raise ExplorerDenied("Explorer only executes constructed Git observations")
        for token in command[1:]:
            if token in _BLOCKED_GIT_TOKENS or token.startswith("--output="):
                raise ExplorerDenied("unsafe Git option is not allowed")
        return command

    def _observe(self, command: tuple[str, ...], *, timeout_seconds: int = 30) -> CommandReceipt:
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 60:
            raise ExplorerDenied("command timeout must be between one and sixty seconds")
        command = self._validate_command(command)
        executable_command = (str(self.git_executable), *command[1:])
        try:
            completed = subprocess.run(
                executable_command,
                cwd=self.root,
                env=self._git_environment(),
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
            executable_command,
            completed.returncode,
            completed.stdout,
            completed.stderr,
            _digest(completed.stdout.encode("utf-8")),
            _digest(completed.stderr.encode("utf-8")),
        )

    def history(self, *, limit: int = 20) -> CommandReceipt:
        """Return commit identifiers from a bounded local history observation."""

        if type(limit) is not int or not 1 <= limit <= 100:
            raise ExplorerDenied("history limit must be an integer between one and one hundred")
        return self._observe(("git", "log", "--no-decorate", "--no-patch", "--format=%H", "-n", str(limit)))

    def commit(self, commit_sha: str) -> CommandReceipt:
        """Return fuller metadata for one fully qualified immutable commit SHA."""

        commit_sha = self._commit_sha(commit_sha, "commit SHA")
        return self._observe(("git", "show", "--no-decorate", "--no-patch", "--format=fuller", commit_sha))

    def tracked_files(self) -> CommandReceipt:
        """Return NUL-delimited tracked file names without filesystem traversal."""

        return self._observe(("git", "ls-files", "--cached", "-z"))

    def working_diff(self, base_sha: str, head_sha: str) -> CommandReceipt:
        """Return a binary-safe diff between two fully qualified immutable commits."""

        base_sha = self._commit_sha(base_sha, "base SHA")
        head_sha = self._commit_sha(head_sha, "head SHA")
        return self._observe(
            ("git", "diff", "--no-ext-diff", "--no-textconv", "--no-renames", "--binary", base_sha, head_sha, "--")
        )

    def status(self) -> CommandReceipt:
        """Return a NUL-delimited status that cannot discover untracked files."""

        return self._observe(("git", "status", "--porcelain=v1", "--untracked-files=no", "-z"))

    @staticmethod
    def retain_source_intake(intake: SourceIntake) -> SourceIntake:
        """Return typed source data without admitting it or changing repository state."""

        return intake
