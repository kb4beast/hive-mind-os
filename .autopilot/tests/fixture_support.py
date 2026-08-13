from __future__ import annotations

import atexit
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


class FixtureIntegrityError(RuntimeError):
    """The pinned source or its materialized seed no longer matches its seal."""


class FixturePolicyError(RuntimeError):
    """The requested seed contains material forbidden by the fixture policy."""


_CREDENTIAL_PATTERNS = (
    re.compile(rb"github_pat_[A-Za-z0-9_]{40,}"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
_SEED_METADATA = "fixture-seal.json"
_WORKSPACES = "workspaces"
_RECLAIM_PREFIX = ".reclaim-"
_WORKSPACE_LOCK = threading.RLock()
_ACTIVE_WORKSPACES: dict[Path, str] = {}


def _run_git(root: Path, *arguments: str) -> bytes:
    environment = {
        **os.environ,
        "GIT_ALLOW_PROTOCOL": "file",
        "GIT_TERMINAL_PROMPT": "0",
    }
    completed = subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=True,
        capture_output=True,
        env=environment,
    )
    return completed.stdout


def _repository_for(source_ap_root: Path) -> tuple[Path, Path]:
    source = source_ap_root.resolve(strict=True)
    if source.name != ".autopilot" or source.is_symlink():
        raise FixturePolicyError("fixture source must be a real .autopilot directory")
    repository_text = _run_git(source.parent, "rev-parse", "--show-toplevel").decode().strip()
    repository = Path(repository_text).resolve(strict=True)
    if source.parent != repository:
        raise FixturePolicyError("fixture source must be the repository-root .autopilot")
    return source, repository


def _repository_identity(repository: Path) -> dict[str, str]:
    return {
        "commit": _run_git(repository, "rev-parse", "HEAD").decode().strip(),
        "tree": _run_git(repository, "rev-parse", "HEAD^{tree}").decode().strip(),
    }


def _manifest(repository: Path) -> tuple[dict[str, str], ...]:
    output = _run_git(repository, "ls-files", "-s", "-z", "--", ".autopilot")
    entries: list[dict[str, str]] = []
    for record in output.split(b"\0"):
        if not record:
            continue
        metadata, encoded_path = record.split(b"\t", 1)
        mode, blob, stage = metadata.decode("ascii").split()
        if stage != "0":
            raise FixtureIntegrityError("unmerged index entries cannot seed a fixture")
        repository_path = encoded_path.decode("utf-8")
        prefix = ".autopilot/"
        if not repository_path.startswith(prefix):
            raise FixturePolicyError("tracked fixture entry escaped .autopilot")
        relative = repository_path[len(prefix) :]
        parts = Path(relative).parts
        if (
            not relative
            or parts[:1] == ("state",)
            or "__pycache__" in parts
            or relative.endswith((".pyc", ".pyo"))
        ):
            continue
        if mode == "120000":
            raise FixturePolicyError("symlinks are forbidden in fixture seeds")
        if mode not in {"100644", "100755"}:
            raise FixturePolicyError(f"unsupported fixture index mode: {mode}")
        entries.append({"path": relative, "mode": mode, "blob": blob})
    return tuple(sorted(entries, key=lambda item: item["path"]))


def _fixture_digest(
    identity: dict[str, str], manifest: tuple[dict[str, str], ...]
) -> str:
    body = json.dumps(
        {"commit": identity["commit"], "tree": identity["tree"], "entries": manifest},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _blob(repository: Path, oid: str) -> bytes:
    return _run_git(repository, "cat-file", "blob", oid)


def _safe_destination(root: Path, relative: str) -> Path:
    candidate = root.joinpath(*Path(relative).parts)
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise FixturePolicyError("fixture path escaped its destination") from error
    return candidate


def _write_manifest_files(
    repository: Path, destination: Path, manifest: tuple[dict[str, str], ...]
) -> None:
    for entry in manifest:
        body = _blob(repository, entry["blob"])
        if any(pattern.search(body) for pattern in _CREDENTIAL_PATTERNS):
            raise FixturePolicyError(
                f"credential-shaped content is forbidden: {entry['path']}"
            )
        target = _safe_destination(destination, entry["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        target.chmod(0o755 if entry["mode"] == "100755" else 0o644)


def _hash_files(root: Path, *, exclude_metadata: bool = False) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise FixtureIntegrityError(f"seed contains a symlink: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if exclude_metadata and relative == _SEED_METADATA:
            continue
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel32.OpenProcess
        open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        open_process.restype = wintypes.HANDLE
        wait = kernel32.WaitForSingleObject
        wait.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        wait.restype = wintypes.DWORD
        close = kernel32.CloseHandle
        close.argtypes = (wintypes.HANDLE,)
        close.restype = wintypes.BOOL
        handle = open_process(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return ctypes.get_last_error() == 5  # access denied means it exists
        try:
            return wait(handle, 0) == 0x00000102  # WAIT_TIMEOUT means still running
        finally:
            close(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _remove_tree(path: Path) -> None:
    """Remove Git's read-only object files on Windows as well as POSIX."""

    def make_writable_and_retry(function, target, _error) -> None:
        try:
            os.chmod(target, stat.S_IREAD | stat.S_IWRITE)
            function(target)
        except FileNotFoundError:
            return

    for attempt in range(5):
        if not path.exists():
            return
        try:
            shutil.rmtree(path, onexc=make_writable_and_retry)
            return
        except FileNotFoundError:
            return
        except OSError:
            if attempt == 4:
                raise
            time.sleep(0.02 * (attempt + 1))


@dataclass(frozen=True)
class DerivedFixture:
    root: Path
    origin: Path
    workspace: Path


class ContentAddressedFixtureSeed:
    """A sealed tracked snapshot that derives fully independent Git repositories."""

    def __init__(
        self, source_ap_root: Path, storage: Path, rebuild: bool = False
    ) -> None:
        self.source_ap_root, self.repository = _repository_for(Path(source_ap_root))
        self.storage = Path(storage).resolve()
        self.storage.mkdir(parents=True, exist_ok=True)
        self.repository_identity = _repository_identity(self.repository)
        self.manifest = _manifest(self.repository)
        self.digest = _fixture_digest(self.repository_identity, self.manifest)
        self.seed_path = self.storage / self.digest.removeprefix("sha256:")
        if rebuild and self.seed_path.exists():
            _remove_tree(self.seed_path)
        if not self.seed_path.exists():
            self._materialize()
        self._validate_source()
        self._validate_seed()

    def _materialize(self) -> None:
        temporary = Path(
            tempfile.mkdtemp(prefix="fixture-seed-", dir=str(self.storage))
        )
        try:
            snapshot = temporary / "snapshot" / ".autopilot"
            snapshot.mkdir(parents=True)
            _write_manifest_files(self.repository, snapshot, self.manifest)
            work = temporary / "repository"
            shutil.copytree(snapshot.parent, work)
            _run_git(work, "init", "--initial-branch=main")
            _run_git(work, "config", "user.name", "Fixture")
            _run_git(work, "config", "user.email", "fixture@hive-mind.invalid")
            _run_git(work, "add", "-A")
            environment = {
                **os.environ,
                "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
                "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
            }
            subprocess.run(
                ("git", "-C", str(work), "commit", "-m", "fixture base"),
                check=True,
                capture_output=True,
                env=environment,
            )
            template = temporary / "template.git"
            subprocess.run(
                ("git", "clone", "--bare", "--no-local", str(work), str(template)),
                check=True,
                capture_output=True,
                env={**os.environ, "GIT_ALLOW_PROTOCOL": "file"},
            )
            _remove_tree(work)
            seal = {
                "schema_version": 1,
                "digest": self.digest,
                "repository_identity": self.repository_identity,
                "manifest": self.manifest,
                "files": _hash_files(temporary, exclude_metadata=True),
            }
            (temporary / _SEED_METADATA).write_text(
                json.dumps(seal, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            try:
                temporary.replace(self.seed_path)
            except FileExistsError:
                _remove_tree(temporary)
        except BaseException:
            if temporary.exists():
                _remove_tree(temporary)
            raise

    def _validate_source(self) -> None:
        if _repository_identity(self.repository) != self.repository_identity:
            raise FixtureIntegrityError("source repository identity changed")
        if _manifest(self.repository) != self.manifest:
            raise FixtureIntegrityError("source tracked manifest changed")
        comparison = subprocess.run(
            (
                "git",
                "-C",
                str(self.repository),
                "diff-files",
                "--quiet",
                "--",
                ".autopilot",
            ),
            capture_output=True,
            env={**os.environ, "GIT_ALLOW_PROTOCOL": "file"},
        )
        if comparison.returncode == 1:
            raise FixtureIntegrityError("tracked fixture source has working-tree mutations")
        if comparison.returncode != 0:
            raise FixtureIntegrityError("tracked fixture source could not be revalidated")

    def _validate_seed(self) -> None:
        metadata = self.seed_path / _SEED_METADATA
        try:
            seal = json.loads(metadata.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise FixtureIntegrityError("fixture seed metadata is unreadable") from error
        if (
            seal.get("digest") != self.digest
            or seal.get("repository_identity") != self.repository_identity
            or seal.get("manifest") != list(self.manifest)
        ):
            raise FixtureIntegrityError("fixture seed metadata does not match source")
        if _hash_files(self.seed_path, exclude_metadata=True) != seal.get("files"):
            raise FixtureIntegrityError("fixture seed content was mutated")

    def _reclaim_abandoned(self) -> None:
        workspaces = self.storage / _WORKSPACES
        if not workspaces.is_dir():
            return
        claimed: list[Path] = []
        with _WORKSPACE_LOCK:
            for workspace in tuple(workspaces.iterdir()):
                if not workspace.is_dir() or workspace in _ACTIVE_WORKSPACES:
                    continue
                if workspace.name.startswith(_RECLAIM_PREFIX):
                    try:
                        claiming_pid = int(workspace.name.split("-", 2)[1])
                    except (IndexError, ValueError):
                        claiming_pid = -1
                    if _pid_is_alive(claiming_pid):
                        continue
                else:
                    marker = workspace / "owner.json"
                    try:
                        owner = json.loads(marker.read_text(encoding="utf-8"))
                        if _pid_is_alive(int(owner["pid"])):
                            continue
                    except (OSError, ValueError, KeyError, TypeError):
                        pass
                claim = workspaces / (
                    f"{_RECLAIM_PREFIX}{os.getpid()}-{uuid.uuid4().hex}"
                )
                try:
                    workspace.replace(claim)
                except FileNotFoundError:
                    continue
                claimed.append(claim)
        for claim in claimed:
            _remove_tree(claim)

    @contextmanager
    def derive(self) -> Iterator[DerivedFixture]:
        self._validate_source()
        self._validate_seed()
        self._reclaim_abandoned()
        workspaces = self.storage / _WORKSPACES
        token = uuid.uuid4().hex
        with _WORKSPACE_LOCK:
            workspaces.mkdir(parents=True, exist_ok=True)
            workspace = workspaces / f"{os.getpid()}-{token}"
            workspace.mkdir()
            (workspace / "owner.json").write_text(
                json.dumps({"pid": os.getpid(), "token": token}) + "\n",
                encoding="utf-8",
            )
            _ACTIVE_WORKSPACES[workspace] = token
        origin = workspace / "origin.git"
        root = workspace / "work"
        try:
            shutil.copytree(self.seed_path / "template.git", origin)
            subprocess.run(
                ("git", "clone", "--no-local", str(origin), str(root)),
                check=True,
                capture_output=True,
                env={**os.environ, "GIT_ALLOW_PROTOCOL": "file"},
            )
            _run_git(root, "config", "user.name", "Fixture")
            _run_git(root, "config", "user.email", "fixture@hive-mind.invalid")
            yield DerivedFixture(root=root, origin=origin, workspace=workspace)
        finally:
            with _WORKSPACE_LOCK:
                if _ACTIVE_WORKSPACES.get(workspace) == token:
                    del _ACTIVE_WORKSPACES[workspace]
                claim = workspaces / (
                    f"{_RECLAIM_PREFIX}{os.getpid()}-{uuid.uuid4().hex}"
                )
                try:
                    workspace.replace(claim)
                except FileNotFoundError:
                    claim = None
            if claim is not None:
                _remove_tree(claim)


_INVOCATION_TEMPORARY = tempfile.TemporaryDirectory(prefix="healing-fixtures-")
_INVOCATION_STORAGE = Path(_INVOCATION_TEMPORARY.name)
_INVOCATION_LOCK = threading.Lock()
_INVOCATION_SEEDS: dict[Path, ContentAddressedFixtureSeed] = {}
atexit.register(_INVOCATION_TEMPORARY.cleanup)


def invocation_scoped_fixture(source_ap_root: Path):
    """Derive from this test-process's nonpersistent, content-addressed seed."""

    source = Path(source_ap_root).resolve()
    with _INVOCATION_LOCK:
        seed = _INVOCATION_SEEDS.get(source)
        if seed is None:
            seed = ContentAddressedFixtureSeed(source, _INVOCATION_STORAGE)
            _INVOCATION_SEEDS[source] = seed
    return seed.derive()


def copy_autopilot_fixture(source: Path, destination: Path) -> Path:
    """Copy only tracked ``.autopilot`` inputs into an isolated fixture."""

    fixture_root, repository = _repository_for(Path(source))
    manifest = _manifest(repository)
    destination.mkdir(parents=True)
    _write_manifest_files(repository, destination, manifest)
    (destination / "state").mkdir()
    return destination
