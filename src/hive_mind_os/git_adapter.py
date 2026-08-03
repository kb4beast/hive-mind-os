"""Typed, local-only Git workspace operations over the receipted process sandbox."""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import sys
import tempfile
import threading
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence
from urllib.parse import urlsplit
from uuid import uuid4

from .autonomy import EpisodeAllowance
from .contracts import tool_intent_digest
from .models import AutonomyLevel, RiskTier, Role
from .policy import Action, PolicyEngine
from .receipts import (
    FileReceiptValidator,
    ReceiptReference,
    portable_path_parts,
    sha256_digest,
)
from .sandbox import ConfinementViolation, SandboxDenied, SandboxRunner, SandboxSpec
from .source_custody import (
    SourceCustodyError,
    SourceCustodyVerifier,
    SourceLock,
    SourceLockEvidence,
)

_FULL_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")
_BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*\Z")
_GIT_ENV_LOCK = threading.RLock()
_GIT_CREDENTIAL_ENV = (
    "GIT_CONFIG_COUNT",
    "GIT_CONFIG_KEY_0",
    "GIT_CONFIG_VALUE_0",
    "GIT_CONFIG_KEY_1",
    "GIT_CONFIG_VALUE_1",
    "GIT_CONFIG_KEY_2",
    "GIT_CONFIG_VALUE_2",
)
_GIT_PLATFORM_ENV = ("SYSTEMROOT",) if os.name == "nt" else ()


class GitOperationFailed(RuntimeError):
    """Raised when a typed Git operation cannot produce its required result."""


class PinViolation(GitOperationFailed):
    """Raised when materialization is not bound to a local source and full commit SHA."""


class WorkspaceDirty(GitOperationFailed):
    """Raised when delivery export observes uncommitted workspace bytes."""


class GitPolicyDenied(GitOperationFailed):
    """Raised before execution when policy does not authorize the Git operation."""


@dataclass(frozen=True, slots=True)
class DeliveryArtifact:
    root: Path
    bundle_path: Path
    patch_path: Path
    manifest_path: Path
    base_sha: str
    head_sha: str
    tree_digest: str
    diff_digest: str
    receipts: tuple[dict[str, Any], ...]


def _atomic_write(destination: Path, content: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=destination.parent,
        delete=False,
    ) as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, destination)


def _validated_delivery_target(
    value: str | Path,
    workspace_root: Path,
) -> Path:
    destination = Path(os.path.abspath(value))
    parent = destination.parent
    if not parent.is_dir():
        raise ValueError("delivery parent must be an existing directory")
    if parent.resolve() != parent:
        raise ConfinementViolation(
            "delivery parent must not traverse a symlink or junction"
        )
    if destination.exists() or destination.is_symlink():
        raise WorkspaceDirty("delivery root must not already exist")
    try:
        destination.relative_to(workspace_root)
    except ValueError:
        return destination
    raise ConfinementViolation("delivery directory must be outside the Git workspace")


@contextmanager
def _staged_delivery(destination: Path) -> Iterator[Path]:
    staging = Path(
        tempfile.mkdtemp(
            dir=destination.parent,
            prefix=".s-",
        )
    )
    try:
        yield staging
        if destination.exists() or destination.is_symlink():
            raise WorkspaceDirty("delivery root appeared during export")
        os.replace(staging, destination)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def _local_source(value: str | Path) -> Path:
    raw = str(value)
    if "://" in raw or raw.startswith(("git@", "ssh:", "file:", "\\\\", "//")):
        raise PinViolation("repository URLs are disabled until P07")
    source = Path(value).resolve()
    if str(source).startswith(("\\\\", "//")):
        raise PinViolation("network filesystem repositories are disabled until P07")
    if not source.is_dir() or not (source / ".git").exists():
        raise PinViolation("source must be a local Git repository")
    return source


def _github_remote(
    value: str,
    *,
    allowed_hosts: Sequence[str] = ("github.com",),
) -> str:
    parsed = urlsplit(value)
    hosts = {host.casefold() for host in allowed_hosts}
    path_parts = tuple(part for part in parsed.path.split("/") if part)
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.hostname.casefold() not in hosts
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or parsed.query
        or parsed.fragment
        or len(path_parts) != 2
        or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in path_parts)
    ):
        raise PinViolation(
            "remote must be a credential-free HTTPS GitHub repository URL"
        )
    repository = path_parts[1].removesuffix(".git")
    if not repository:
        raise PinViolation("remote repository name is required")
    return f"https://{parsed.hostname.casefold()}/{path_parts[0]}/{repository}.git"


def _materialization_source(
    value: str | Path,
    *,
    allow_remote: bool,
    allowed_hosts: Sequence[str],
) -> tuple[Path | str, bool]:
    raw = str(value)
    if "://" not in raw:
        return _local_source(value), False
    if not allow_remote:
        raise PinViolation("repository URLs require explicit allow_remote=True")
    return _github_remote(raw, allowed_hosts=allowed_hosts), True


def _ignore_local_app_refs(directory: str, names: list[str]) -> list[str]:
    """Exclude Codex desktop bookkeeping refs from the staged source copy."""

    path = Path(directory)
    if path.name == "refs" and path.parent.name == ".git" and "codex" in names:
        return ["codex"]
    return []


def _full_sha(value: str) -> str:
    if not _FULL_SHA.fullmatch(value):
        raise PinViolation("commit pin must be a full 40-hex SHA")
    return value.lower()


def _normalized_executable(value: str) -> str:
    return Path(value).name.casefold().removesuffix(".exe")


def _branch_name(value: str) -> str:
    if (
        not _BRANCH.fullmatch(value)
        or value.endswith((".", "/"))
        or ".." in value
        or "@{" in value
        or value.startswith("-")
        or value.lower() in {"head", "fetch_head"}
    ):
        raise GitOperationFailed("branch name is not a safe local ref")
    return value


@contextmanager
def _git_dates(author_date: str, committer_date: str) -> Iterator[None]:
    names = ("GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE")
    with _GIT_ENV_LOCK:
        previous = {name: os.environ.get(name) for name in names}
        os.environ[names[0]] = author_date
        os.environ[names[1]] = committer_date
        try:
            yield
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


@contextmanager
def _isolated_git_config(config_path: Path) -> Iterator[None]:
    values = {
        "GIT_CONFIG_GLOBAL": str(config_path),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    with _GIT_ENV_LOCK:
        previous = {name: os.environ.get(name) for name in values}
        os.environ.update(values)
        try:
            yield
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


@contextmanager
def _git_http_credentials(remote_url: str, token: str) -> Iterator[tuple[str, ...]]:
    if not token:
        raise GitOperationFailed("GitHub credential is required")
    remote = _github_remote(remote_url)
    encoded = base64.b64encode(f"x-access-token:{token}".encode()).decode("ascii")
    values = {
        "GIT_CONFIG_COUNT": "3" if os.name == "nt" else "1",
        "GIT_CONFIG_KEY_0": f"http.{remote}/.extraHeader",
        "GIT_CONFIG_VALUE_0": f"Authorization: Basic {encoded}",
    }
    if os.name == "nt":
        # Git for Windows uses Schannel. Some managed Windows hosts make CRL/OCSP
        # unavailable; retain chain and hostname verification while making that
        # environment-specific revocation limitation explicit and deterministic.
        values["GIT_CONFIG_KEY_1"] = "http.sslBackend"
        values["GIT_CONFIG_VALUE_1"] = "schannel"
        values["GIT_CONFIG_KEY_2"] = "http.schannelCheckRevoke"
        values["GIT_CONFIG_VALUE_2"] = "false"
    with _GIT_ENV_LOCK:
        previous = {name: os.environ.get(name) for name in values}
        os.environ.update(values)
        try:
            yield (token, encoded)
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


@contextmanager
def _scrubbed_git_environment() -> Iterator[None]:
    names = (
        "GIT_AUTHOR_DATE",
        "GIT_COMMITTER_DATE",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_TERMINAL_PROMPT",
        *_GIT_CREDENTIAL_ENV,
    )
    with _GIT_ENV_LOCK:
        previous = {name: os.environ.pop(name, None) for name in names}
        try:
            yield
        finally:
            for name, value in previous.items():
                if value is not None:
                    os.environ[name] = value


class GitWorkspace:
    """Pinned, isolated local Git workspace with no merge/push/rebase authority."""

    def __init__(
        self,
        *,
        root: Path,
        container_root: Path,
        trusted_root: Path,
        hooks_root: Path,
        git_config: Path,
        base_sha: str,
        runner: SandboxRunner,
        policy: PolicyEngine,
        role: Role,
        risk: RiskTier,
        mission_id: str,
        receipts: list[dict[str, Any]],
        source_lock: SourceLock | None = None,
        source_lock_evidence: SourceLockEvidence | None = None,
        state_ref: str | None = None,
    ) -> None:
        self.root = root
        self.container_root = container_root
        self.trusted_root = trusted_root
        self.hooks_root = hooks_root
        self.git_config = git_config
        self.base_sha = base_sha
        self.runner = runner
        self.policy = policy
        self.role = role
        self.risk = risk
        self.mission_id = mission_id
        self.state_ref = state_ref or f"MISSION_STATE:{mission_id}:1"
        self.branch_name: str | None = None
        self.receipt_records = receipts
        self.source_lock = source_lock
        self.source_lock_evidence = source_lock_evidence

    @classmethod
    def materialize(
        cls,
        source_path_or_url: str | Path,
        commit_sha: str,
        workspace_root: str | Path,
        trusted_root: str | Path,
        *,
        policy: PolicyEngine | None = None,
        role: Role = Role.BUILDER,
        risk: RiskTier = RiskTier.MODERATE,
        allowance: EpisodeAllowance = EpisodeAllowance(200, 200.0),
        test_executables: tuple[str, ...] = (Path(sys.executable).name,),
        allow_remote: bool = False,
        allowed_hosts: tuple[str, ...] = ("github.com",),
        source_lock: SourceLockEvidence | None = None,
        source_custody: SourceCustodyVerifier | None = None,
        require_source_custody: bool = False,
        source_mission_id: str | None = None,
        source_state_ref: str | None = None,
    ) -> GitWorkspace:
        source, remote = _materialization_source(
            source_path_or_url,
            allow_remote=allow_remote,
            allowed_hosts=allowed_hosts,
        )
        pin = _full_sha(commit_sha)
        mission_id = source_mission_id or f"git-workspace-{uuid4()}"
        authenticated_source_lock: SourceLock | None = None
        if source_lock is None:
            if source_custody is not None:
                raise PinViolation("source custody verifier requires signed source-lock evidence")
            if remote and require_source_custody:
                raise PinViolation("remote source requires authenticated source-lock evidence")
        else:
            if source_custody is None:
                raise PinViolation("signed source-lock evidence requires a source custody verifier")
            if not remote:
                raise PinViolation("authenticated source locks are only supported for remote sources")
            if source_mission_id is None:
                raise PinViolation(
                    "authenticated source locks require a caller-supplied mission identity"
                )
            if source_state_ref is None:
                raise PinViolation(
                    "authenticated source locks require a caller-supplied state reference"
                )
            if (
                require_source_custody
                and (
                    not source_custody.provenance.is_durable
                    or not source_custody.custody_verifier.provenance.is_durable
                )
            ):
                raise PinViolation(
                    "strict source custody requires durable source and keyset provenance"
                )
            try:
                authenticated_source_lock = source_custody.verify_for_materialization(
                    source_lock,
                    str(source),
                    pin,
                    mission_id=mission_id,
                    state_ref=source_state_ref,
                    allowed_hosts=allowed_hosts,
                )
            except SourceCustodyError as error:
                raise PinViolation(f"authenticated source lock was rejected: {error}") from error
        engine = policy or PolicyEngine(AutonomyLevel.REPOSITORY)
        decision = engine.decide(role, Action.READ_REPOSITORY, risk)
        if not decision.allowed:
            raise GitPolicyDenied(decision.reason)

        container = Path(workspace_root).resolve()
        if container.exists() and any(container.iterdir()):
            raise WorkspaceDirty("materialization root must be absent or empty")
        container.mkdir(parents=True, exist_ok=True)
        evidence = Path(trusted_root).resolve()
        try:
            evidence.relative_to(container)
        except ValueError:
            pass
        else:
            raise ValueError(
                "trusted receipt root must be outside the workspace container"
            )

        staged_source = container / "source"
        repository = container / "repo"
        hooks = container / "disabled-hooks"
        hooks.mkdir()
        staging_config = container / "isolated-gitconfig"
        _atomic_write(staging_config, b"")
        if not remote:
            assert isinstance(source, Path)
            shutil.copytree(
                source,
                staged_source,
                symlinks=True,
                ignore=_ignore_local_app_refs,
            )
        receipts: list[dict[str, Any]] = []
        git_name = Path(shutil.which("git") or "git").name
        staging_runner = SandboxRunner(
            SandboxSpec(
                container,
                argv_allowlist=(git_name,),
                env_allowlist=(
                    "GIT_CONFIG_GLOBAL",
                    "GIT_CONFIG_NOSYSTEM",
                    "GIT_TERMINAL_PROMPT",
                    *_GIT_CREDENTIAL_ENV,
                    *_GIT_PLATFORM_ENV,
                ),
                timeout_s=60.0,
                max_output_bytes=10_000_000,
            ),
            evidence,
            allowance,
            policy=engine,
            role=role,
            risk=risk,
            runner_identity="git-sandbox-runner-v1",
        )
        clone_args = [
            "clone",
            "--no-hardlinks",
            "--no-checkout",
            str(source) if remote else "source",
            "repo",
        ]
        with _isolated_git_config(staging_config):
            clone_receipt = cls._execute(
                staging_runner,
                cls._git_argv(hooks, clone_args),
                mission_id=mission_id,
                state_ref=source_state_ref if authenticated_source_lock is not None else None,
                role=role,
                description="clone approved source without checkout",
                path_args=[11] if remote else [10, 11],
            )
        cls._append_receipt(receipts, staging_runner, clone_receipt)
        if clone_receipt["result"] != "succeeded":
            raise GitOperationFailed("local repository clone failed")

        remaining = EpisodeAllowance(
            max(0, allowance.tool_calls - staging_runner.tool_calls_used),
            max(0.0, allowance.compute_units - staging_runner.compute_units_used),
        )
        git_config = repository / ".git" / "hive-mind-isolated-config"
        _atomic_write(git_config, b"")
        runner = SandboxRunner(
            SandboxSpec(
                repository,
                argv_allowlist=(git_name, *test_executables),
                env_allowlist=(
                    "GIT_AUTHOR_DATE",
                    "GIT_COMMITTER_DATE",
                    "GIT_CONFIG_GLOBAL",
                    "GIT_CONFIG_NOSYSTEM",
                    "GIT_TERMINAL_PROMPT",
                    *_GIT_CREDENTIAL_ENV,
                    *_GIT_PLATFORM_ENV,
                ),
                timeout_s=60.0,
                max_output_bytes=10_000_000,
            ),
            evidence,
            remaining,
            policy=engine,
            role=role,
            risk=risk,
            runner_identity="git-sandbox-runner-v1",
        )
        workspace = cls(
            root=repository,
            container_root=container,
            trusted_root=evidence,
            hooks_root=hooks,
            git_config=git_config,
            base_sha=pin,
            runner=runner,
            policy=engine,
            role=role,
            risk=risk,
            mission_id=mission_id,
            receipts=receipts,
            source_lock=authenticated_source_lock,
            source_lock_evidence=source_lock if authenticated_source_lock is not None else None,
            state_ref=source_state_ref if authenticated_source_lock is not None else None,
        )
        if authenticated_source_lock is not None:
            cls._verify_authenticated_source_tree(
                workspace,
                f"{pin}^{{tree}}",
                authenticated_source_lock,
            )
        workspace._run_git(
            ["checkout", "--detach", pin],
            Action.READ_REPOSITORY,
            "checkout exact pinned commit",
        )
        observed = workspace._git_text(
            ["rev-parse", "HEAD"],
            Action.READ_REPOSITORY,
            "verify pinned commit",
        )
        if observed != pin:
            raise PinViolation(f"materialized HEAD {observed} does not match pin {pin}")
        if authenticated_source_lock is not None:
            cls._verify_authenticated_source_tree(
                workspace,
                "HEAD^{tree}",
                authenticated_source_lock,
            )
        return workspace

    @staticmethod
    def _verify_authenticated_source_tree(
        workspace: GitWorkspace,
        revision: str,
        source_lock: SourceLock,
    ) -> None:
        materialized_tree = workspace._git_text(
            ["rev-parse", revision],
            Action.READ_REPOSITORY,
            "verify authenticated source tree",
        )
        try:
            source_lock.require_tree(materialized_tree)
        except SourceCustodyError as error:
            raise PinViolation(
                f"materialized source does not match authenticated source lock: {error}"
            ) from error

    @staticmethod
    def _git_argv(hooks_root: Path, args: Sequence[str]) -> list[str]:
        git = shutil.which("git") or "git"
        return [
            git,
            "-c",
            f"core.hooksPath={hooks_root}",
            "-c",
            "core.autocrlf=false",
            "-c",
            "commit.gpgsign=false",
            *args,
        ]

    @staticmethod
    def _execute(
        runner: SandboxRunner,
        argv: list[str],
        *,
        mission_id: str,
        state_ref: str | None = None,
        role: Role,
        description: str,
        path_args: list[int] | None = None,
        acceptance_specification: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        intent: dict[str, Any] = {
            "schema_version": 1,
            "action_id": f"ACT-git-{uuid4()}",
            "mission_id": mission_id,
            "state_ref": state_ref or f"MISSION_STATE:{mission_id}:1",
            "actor_id": role.value,
            "kind": "command",
            "description": description,
            "action_digest": f"sha256:{'0' * 64}",
            "policy_decision_ref": f"POLICY-git-{uuid4()}",
            "lease_id": f"LEASE-git-{uuid4()}",
            "idempotency_key": f"IDEMPOTENCY-git-{uuid4()}",
            "rollback_ref": None,
            "command": {
                "argv": argv,
                "path_args": path_args or [],
            },
            "status": "proposed",
        }
        if acceptance_specification is not None:
            intent["acceptance_specification"] = dict(acceptance_specification)
        intent["action_digest"] = tool_intent_digest(intent)
        return runner.run(intent)

    @staticmethod
    def _append_receipt(
        records: list[dict[str, Any]],
        runner: SandboxRunner,
        receipt: Mapping[str, Any],
    ) -> None:
        reference = runner.last_reference
        if reference is None:
            raise GitOperationFailed("sandbox execution did not publish a receipt")
        records.append(
            {
                "path": reference.path,
                "digest": reference.digest,
                "mission_id": receipt["mission_id"],
                "state_ref": receipt["state_ref"],
                "actor_id": receipt["actor_id"],
                "action_id": receipt["action_id"],
                "action_kind": receipt["action_kind"],
                "action_digest": receipt["action_digest"],
                "result": receipt["result"],
            }
        )

    def _authorize(self, action: Action) -> None:
        decision = self.policy.decide(self.role, action, self.risk)
        if not decision.allowed:
            raise GitPolicyDenied(decision.reason)

    def _artifact(self, receipt: Mapping[str, Any], artifact_id: str) -> bytes:
        for artifact in receipt["artifacts"]:
            if artifact.get("artifact_id") == artifact_id:
                parts = portable_path_parts(artifact["path"])
                return (self.trusted_root / Path(*parts)).read_bytes()
        raise GitOperationFailed(f"git receipt lacks {artifact_id} artifact")

    def _run_git(
        self,
        args: Sequence[str],
        action: Action,
        description: str,
        *,
        path_args: list[int] | None = None,
        extra_config: Sequence[str] = (),
        allow_failure: bool = False,
        credential: tuple[str, str] | None = None,
    ) -> tuple[dict[str, Any], bytes]:
        self._authorize(action)
        argv = self._git_argv(
            self.hooks_root,
            [*extra_config, *args],
        )
        adjusted_paths = (
            [index + 7 + len(extra_config) for index in path_args] if path_args else []
        )
        credential_context = (
            _git_http_credentials(credential[0], credential[1])
            if credential is not None
            else nullcontext(())
        )
        with _isolated_git_config(self.git_config), credential_context as secrets:
            receipt = self._execute(
                self.runner,
                argv,
                mission_id=self.mission_id,
                state_ref=self.state_ref,
                role=self.role,
                description=description,
                path_args=adjusted_paths,
            )
        self._append_receipt(self.receipt_records, self.runner, receipt)
        stdout = self._artifact(receipt, "stdout")
        if receipt["execution"]["stdout"]["truncated"]:
            raise GitOperationFailed(f"{description} exceeded the Git output limit")
        if receipt["result"] != "succeeded" and not allow_failure:
            stderr = (
                self._artifact(receipt, "stderr").decode("utf-8", "replace").strip()
            )
            for secret in secrets:
                stderr = stderr.replace(secret, "[REDACTED]")
            raise GitOperationFailed(f"{description} failed: {stderr}")
        return receipt, stdout

    def _git_text(
        self,
        args: Sequence[str],
        action: Action,
        description: str,
    ) -> str:
        _, stdout = self._run_git(args, action, description)
        return stdout.decode("utf-8", "strict").strip()

    def status_clean(self) -> bool:
        _, output = self._run_git(
            ["status", "--porcelain", "--untracked-files=all"],
            Action.READ_REPOSITORY,
            "inspect workspace status",
        )
        return not output.strip()

    def create_branch(self, name: str) -> None:
        branch = _branch_name(name)
        self._run_git(
            ["check-ref-format", "--branch", branch],
            Action.CREATE_BRANCH,
            "validate local branch name",
        )
        self._run_git(
            ["switch", "-c", branch],
            Action.CREATE_BRANCH,
            "create isolated branch",
        )
        self.branch_name = branch

    def push_branch(
        self,
        remote_url: str | Path,
        token: str,
        *,
        branch: str | None = None,
        allow_local: bool = False,
    ) -> str:
        """Push the exact committed head without persisting a remote or credential."""

        self._authorize(Action.OPEN_PULL_REQUEST)
        target_branch = _branch_name(branch or self.branch_name or "")
        if not self.status_clean():
            raise WorkspaceDirty("push requires a clean committed workspace")
        head_sha = self._git_text(
            ["rev-parse", "HEAD"],
            Action.READ_REPOSITORY,
            "read push head",
        )
        raw_remote = str(remote_url)
        credential: tuple[str, str] | None
        if "://" in raw_remote:
            remote = _github_remote(raw_remote)
            credential = (remote, token)
        else:
            if not allow_local:
                raise PinViolation("push remote must be an HTTPS GitHub repository URL")
            local = Path(remote_url).resolve()
            if not local.is_dir():
                raise PinViolation(
                    "local test push remote must be a repository directory"
                )
            remote = str(local)
            credential = None
        _, existing = self._run_git(
            ["ls-remote", "--heads", remote, f"refs/heads/{target_branch}"],
            Action.READ_REPOSITORY,
            "inspect remote branch before push",
            credential=credential,
        )
        if existing.strip():
            remote_head = existing.decode("utf-8", "strict").split()[0]
            if remote_head != head_sha:
                raise GitOperationFailed(
                    "remote branch already exists at a different commit"
                )
            return head_sha
        self._run_git(
            [
                "push",
                remote,
                f"{head_sha}:refs/heads/{target_branch}",
            ],
            Action.OPEN_PULL_REQUEST,
            "push exact mission branch",
            credential=credential,
        )
        return head_sha

    def write_file(self, relative_path: str, content: bytes) -> Path:
        self._authorize(Action.WRITE_WORKSPACE)
        parts = portable_path_parts(relative_path)
        if parts[0].casefold() == ".git":
            raise ConfinementViolation("writes to Git metadata are forbidden")
        destination = self.root / Path(*parts)
        resolved = destination.resolve()
        try:
            resolved_relative = resolved.relative_to(self.root)
        except ValueError:
            raise ConfinementViolation("write path escapes Git workspace") from None
        if resolved_relative.parts[0].casefold() == ".git":
            raise ConfinementViolation("writes to Git metadata are forbidden")
        _atomic_write(destination, content)
        return destination

    def diff(self) -> tuple[bytes, str]:
        _, content = self._run_git(
            ["diff", "--binary", self.base_sha, "--"],
            Action.READ_REPOSITORY,
            "render workspace diff",
        )
        return content, sha256_digest(content)

    def commit(
        self,
        message: str,
        *,
        author_date: str = "2026-01-03T00:00:00Z",
        committer_date: str | None = None,
    ) -> str:
        if self.branch_name is None:
            raise GitOperationFailed("create an isolated branch before committing")
        if not message.strip():
            raise ValueError("commit message is required")
        self._run_git(
            ["add", "--all"],
            Action.CREATE_BRANCH,
            "stage workspace changes",
        )
        date = committer_date or author_date
        identity = [
            "-c",
            f"user.name={self.role.value}",
            "-c",
            f"user.email={self.role.value}@hive-mind.invalid",
        ]
        with _git_dates(author_date, date):
            self._run_git(
                ["commit", "--no-gpg-sign", "-m", message],
                Action.CREATE_BRANCH,
                "commit isolated branch changes",
                extra_config=identity,
            )
        return self._git_text(
            ["rev-parse", "HEAD"],
            Action.READ_REPOSITORY,
            "read committed head",
        )

    def run_tests(
        self,
        argv: Sequence[str],
        *,
        acceptance_specification: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        if not argv:
            raise ValueError("test argv is required")
        self._authorize(Action.RUN_COMMANDS)
        requested = shutil.which(argv[0])
        git = shutil.which("git")
        if (
            requested is not None
            and git is not None
            and (_normalized_executable(requested) == _normalized_executable(git))
        ):
            raise GitPolicyDenied(
                "direct Git execution is reserved for typed adapter operations"
            )
        with _scrubbed_git_environment():
            receipt = self._execute(
                self.runner,
                list(argv),
                mission_id=self.mission_id,
                state_ref=self.state_ref,
                role=self.role,
                description="run caller-declared repository tests",
                acceptance_specification=acceptance_specification,
            )
        self._append_receipt(self.receipt_records, self.runner, receipt)
        return receipt

    def export_delivery(self, out_dir: str | Path) -> DeliveryArtifact:
        self._authorize(Action.WRITE_WORKSPACE)
        if self.branch_name is None:
            raise GitOperationFailed("delivery requires an isolated branch")
        delivery_root = _validated_delivery_target(out_dir, self.root)
        if not self.status_clean():
            raise WorkspaceDirty("delivery requires a clean committed workspace")
        head_sha = self._git_text(
            ["rev-parse", "HEAD"],
            Action.READ_REPOSITORY,
            "read delivery head",
        )
        tree_digest = self._git_text(
            ["rev-parse", "HEAD^{tree}"],
            Action.READ_REPOSITORY,
            "read delivery tree",
        )
        diff_bytes, diff_digest = self.diff()
        _, files_bytes = self._run_git(
            ["diff", "--name-only", self.base_sha, head_sha],
            Action.READ_REPOSITORY,
            "list delivery files",
        )
        files = [
            line for line in files_bytes.decode("utf-8", "strict").splitlines() if line
        ]
        for relative in files:
            portable_path_parts(relative)
        _, bundle = self._run_git(
            ["bundle", "create", "-", self.branch_name],
            Action.READ_REPOSITORY,
            "export delivery bundle",
        )
        _, patch = self._run_git(
            ["format-patch", "--stdout", "--binary", f"{self.base_sha}..{head_sha}"],
            Action.READ_REPOSITORY,
            "export delivery patch",
        )

        receipt_snapshot = tuple(dict(record) for record in self.receipt_records)
        manifest = {
            "schema_version": 1,
            "base_sha": self.base_sha,
            "branch_name": self.branch_name,
            "head_sha": head_sha,
            "head_tree": tree_digest,
            "diff_digest": diff_digest,
            "bundle_digest": sha256_digest(bundle),
            "patch_digest": sha256_digest(patch),
            "files": files,
            "receipts": list(receipt_snapshot),
        }
        if self.source_lock_evidence is not None:
            manifest["source_custody"] = {
                "digest": self.source_lock_evidence.digest(),
                "source_lock": self.source_lock_evidence.source_lock.to_dict(),
                "attestation": dict(self.source_lock_evidence.attestation),
            }
        with _staged_delivery(delivery_root) as staging:
            _atomic_write(staging / "changes.bundle", bundle)
            _atomic_write(staging / "changes.patch", patch)
            evidence_root = staging / "evidence"
            self._copy_delivery_evidence(receipt_snapshot, evidence_root)
            if not _receipt_index_valid(
                receipt_snapshot,
                evidence_root,
                artifact_root=staging,
            ):
                raise GitOperationFailed("delivery receipt index failed validation")
            _atomic_write(
                staging / "delivery.json",
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8"),
            )
        return DeliveryArtifact(
            delivery_root,
            delivery_root / "changes.bundle",
            delivery_root / "changes.patch",
            delivery_root / "delivery.json",
            self.base_sha,
            head_sha,
            tree_digest,
            diff_digest,
            receipt_snapshot,
        )

    def _copy_delivery_evidence(
        self,
        records: Sequence[Mapping[str, Any]],
        destination_root: Path,
    ) -> None:
        trusted = self.trusted_root.resolve()
        destination = destination_root.resolve()
        copies: dict[Path, bytes] = {}

        def read_source(parts: tuple[str, ...]) -> bytes:
            source = self.trusted_root / Path(*parts)
            try:
                source.resolve().relative_to(trusted)
            except ValueError:
                raise GitOperationFailed(
                    "delivery evidence source escapes trusted root"
                )
            return source.read_bytes()

        def stage_copy(parts: tuple[str, ...], content: bytes) -> None:
            target = destination_root / Path(*parts)
            try:
                target.parent.resolve().relative_to(destination)
            except ValueError:
                raise GitOperationFailed(
                    "delivery evidence destination escapes output root"
                )
            copies[target] = content

        for record in records:
            receipt_parts = portable_path_parts(str(record["path"]))
            receipt_bytes = read_source(receipt_parts)
            receipt = json.loads(receipt_bytes)
            if not isinstance(receipt, dict):
                raise GitOperationFailed("delivery receipt must be a JSON object")
            stage_copy(receipt_parts, receipt_bytes)
            artifacts = receipt.get("artifacts")
            if not isinstance(artifacts, list):
                raise GitOperationFailed("delivery receipt lacks artifacts")
            for artifact in artifacts:
                if not isinstance(artifact, dict) or not isinstance(
                    artifact.get("path"), str
                ):
                    raise GitOperationFailed("delivery receipt artifact is malformed")
                artifact_parts = portable_path_parts(artifact["path"])
                stage_copy(artifact_parts, read_source(artifact_parts))
        for target, content in copies.items():
            _atomic_write(target, content)


def _evidence_file_inventory(evidence_root: Path) -> set[str] | None:
    resolved_root = evidence_root.resolve()
    if not resolved_root.is_dir():
        return None
    inventory: set[str] = set()
    for current, directories, files in os.walk(
        evidence_root,
        topdown=True,
        followlinks=False,
    ):
        current_path = Path(current)
        try:
            current_path.resolve().relative_to(resolved_root)
            for name in directories:
                (current_path / name).resolve().relative_to(resolved_root)
            for name in files:
                path = current_path / name
                path.resolve().relative_to(resolved_root)
                inventory.add(path.relative_to(evidence_root).as_posix())
        except ValueError:
            return None
    return inventory


def _receipt_index_valid(
    records: object,
    evidence_root: Path,
    *,
    artifact_root: Path,
) -> bool:
    if not isinstance(records, (list, tuple)) or not records:
        return False
    resolved_artifact = artifact_root.resolve()
    resolved_evidence = evidence_root.resolve()
    try:
        resolved_evidence.relative_to(resolved_artifact)
    except ValueError:
        return False
    validator = FileReceiptValidator(resolved_evidence)
    required = {
        "path",
        "digest",
        "mission_id",
        "state_ref",
        "actor_id",
        "action_id",
        "action_kind",
        "action_digest",
        "result",
    }
    expected_files: set[str] = set()
    indexed_receipts: set[str] = set()
    for record in records:
        if not isinstance(record, dict) or not required.issubset(record):
            return False
        if not all(isinstance(record[field], str) for field in required):
            return False
        if record["result"] not in {"succeeded", "failed"}:
            return False
        try:
            receipt_parts = portable_path_parts(record["path"])
            receipt_path = evidence_root / Path(*receipt_parts)
            receipt_path.resolve().relative_to(resolved_evidence)
            receipt_relative = Path(*receipt_parts).as_posix()
            if receipt_relative in indexed_receipts:
                return False
            indexed_receipts.add(receipt_relative)
            expected_files.add(receipt_relative)
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if not isinstance(receipt, dict) or not isinstance(
                receipt.get("artifacts"), list
            ):
                return False
            for artifact in receipt["artifacts"]:
                if not isinstance(artifact, dict) or not isinstance(
                    artifact.get("path"), str
                ):
                    return False
                artifact_parts = portable_path_parts(artifact["path"])
                artifact_path = evidence_root / Path(*artifact_parts)
                artifact_path.resolve().relative_to(resolved_evidence)
                expected_files.add(Path(*artifact_parts).as_posix())
            result = validator.validate(
                ReceiptReference(record["path"], record["digest"]),
                mission_id=record["mission_id"],
                state_ref=record["state_ref"],
                actor_id=record["actor_id"],
                action_id=record["action_id"],
                action_kind=record["action_kind"],
                action_digest=record["action_digest"],
            )
        except (OSError, TypeError, ValueError):
            return False
        if not result.valid:
            return False
        expected_result = "succeeded" if result.succeeded else "failed"
        if record["result"] != expected_result:
            return False
    return _evidence_file_inventory(evidence_root) == expected_files


def verify_delivery(
    artifact_dir: str | Path,
    base_source: str | Path,
    *,
    evidence_root: str | Path | None = None,
    receipt_records: list[dict[str, Any]] | None = None,
    policy: PolicyEngine | None = None,
    role: Role = Role.BUILDER,
    risk: RiskTier = RiskTier.MODERATE,
    allowance: EpisodeAllowance = EpisodeAllowance(200, 200.0),
    source_custody: SourceCustodyVerifier | None = None,
) -> bool:
    artifact_root = Path(artifact_dir).resolve()
    try:
        manifest = json.loads(
            (artifact_root / "delivery.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(manifest, dict):
        return False
    if (
        type(manifest.get("schema_version")) is not int
        or manifest["schema_version"] != 1
    ):
        return False
    required = {
        "base_sha",
        "branch_name",
        "head_sha",
        "head_tree",
        "diff_digest",
        "bundle_digest",
        "patch_digest",
        "files",
        "receipts",
    }
    if not required.issubset(manifest):
        return False
    try:
        base_sha = _full_sha(manifest["base_sha"])
        head_sha = _full_sha(manifest["head_sha"])
        head_tree = _full_sha(manifest["head_tree"])
        branch = _branch_name(manifest["branch_name"])
        source = _local_source(base_source)
        source_custody_record = manifest.get("source_custody")
        if source_custody_record is not None:
            if not isinstance(source_custody_record, Mapping) or source_custody is None:
                return False
            source_lock_value = source_custody_record.get("source_lock")
            attestation_value = source_custody_record.get("attestation")
            digest_value = source_custody_record.get("digest")
            if (
                not isinstance(source_lock_value, Mapping)
                or not isinstance(attestation_value, Mapping)
                or not isinstance(digest_value, str)
            ):
                return False
            source_evidence = SourceLockEvidence(
                SourceLock.from_dict(
                    source_lock_value,
                    allowed_hosts=source_custody.allowed_hosts,
                ),
                attestation_value,
            )
            if source_evidence.digest() != digest_value:
                return False
            if source_evidence.source_lock.commit_sha != base_sha:
                return False
            source_custody.verify(source_evidence)
            manifest_receipts = manifest["receipts"]
            if (
                not isinstance(manifest_receipts, list)
                or not manifest_receipts
                or any(
                    not isinstance(record, Mapping)
                    or record.get("mission_id")
                    != source_evidence.source_lock.mission_id
                    or record.get("state_ref")
                    != source_evidence.source_lock.state_ref
                    for record in manifest_receipts
                )
            ):
                return False
        bundle = (artifact_root / "changes.bundle").read_bytes()
        patch = (artifact_root / "changes.patch").read_bytes()
        files = manifest["files"]
        if not isinstance(files, list) or not all(
            isinstance(relative, str) for relative in files
        ):
            return False
        for relative in files:
            portable_path_parts(relative)
        if not _receipt_index_valid(
            manifest["receipts"],
            artifact_root / "evidence",
            artifact_root=artifact_root,
        ):
            return False
    except (GitOperationFailed, SourceCustodyError, OSError, TypeError, ValueError):
        return False
    if (
        sha256_digest(bundle) != manifest["bundle_digest"]
        or sha256_digest(patch) != manifest["patch_digest"]
    ):
        return False

    verification_workspaces: list[GitWorkspace] = []
    temporary_context: tempfile.TemporaryDirectory[str] | None = None
    try:
        temporary_context = tempfile.TemporaryDirectory()
        temporary = temporary_context.name
        temporary_root = Path(temporary)
        verification_evidence = (
            Path(evidence_root).resolve()
            if evidence_root is not None
            else temporary_root / "evidence"
        )
        try:
            workspace = GitWorkspace.materialize(
                source,
                base_sha,
                temporary_root / "workspace",
                verification_evidence,
                policy=policy,
                role=role,
                risk=risk,
                allowance=allowance,
            )
            verification_workspaces.append(workspace)
            workspace.write_file("changes.bundle", bundle)
            workspace._run_git(
                [
                    "fetch",
                    "changes.bundle",
                    f"{branch}:refs/heads/{branch}",
                ],
                Action.READ_REPOSITORY,
                "apply delivery bundle to fresh clone",
                path_args=[1],
            )
            workspace._run_git(
                ["checkout", "--detach", head_sha],
                Action.READ_REPOSITORY,
                "checkout delivered head",
            )
            ancestor = workspace._run_git(
                ["merge-base", "--is-ancestor", base_sha, head_sha],
                Action.READ_REPOSITORY,
                "verify delivery descends from base",
                allow_failure=True,
            )[0]
            if ancestor["result"] != "succeeded":
                return False
            observed_head = workspace._git_text(
                ["rev-parse", "HEAD"],
                Action.READ_REPOSITORY,
                "verify delivered head",
            )
            observed_tree = workspace._git_text(
                ["rev-parse", "HEAD^{tree}"],
                Action.READ_REPOSITORY,
                "verify delivered tree",
            )
            diff, diff_digest = workspace.diff()
            _, observed_files = workspace._run_git(
                ["diff", "--name-only", base_sha, head_sha],
                Action.READ_REPOSITORY,
                "verify delivered file list",
            )
            _, observed_patch = workspace._run_git(
                ["format-patch", "--stdout", "--binary", f"{base_sha}..{head_sha}"],
                Action.READ_REPOSITORY,
                "verify canonical delivery patch",
            )

            patch_workspace = GitWorkspace.materialize(
                source,
                base_sha,
                temporary_root / "patch-workspace",
                verification_evidence,
                policy=policy,
                role=role,
                risk=risk,
                allowance=allowance,
            )
            verification_workspaces.append(patch_workspace)
            patch_workspace.write_file("changes.patch", patch)
            patch_workspace._run_git(
                ["apply", "--check", "changes.patch"],
                Action.WRITE_WORKSPACE,
                "check delivery patch against base",
                path_args=[2],
            )
            patch_workspace._run_git(
                ["apply", "--index", "changes.patch"],
                Action.WRITE_WORKSPACE,
                "apply delivery patch to base",
                path_args=[2],
            )
            patch_tree = patch_workspace._git_text(
                ["write-tree"],
                Action.READ_REPOSITORY,
                "verify delivery patch tree",
            )
        except (
            GitOperationFailed,
            ConfinementViolation,
            SandboxDenied,
            OSError,
            ValueError,
        ):
            return False
        return (
            observed_head == head_sha
            and observed_tree == head_tree
            and patch_tree == head_tree
            and diff_digest == manifest["diff_digest"]
            and sha256_digest(diff) == manifest["diff_digest"]
            and observed_files.decode("utf-8", "strict").splitlines() == files
            and observed_patch == patch
        )
    finally:
        if receipt_records is not None:
            for verification_workspace in verification_workspaces:
                receipt_records.extend(
                    dict(record) for record in verification_workspace.receipt_records
                )
        if temporary_context is not None:
            temporary_context.cleanup()
