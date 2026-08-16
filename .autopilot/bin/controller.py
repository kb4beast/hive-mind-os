"""Deterministic implementation control plane for the Hive Mind OS autonomy program.

This module coordinates repository implementation work. It is not the Hive Mind OS
product runtime. It intentionally uses only the Python standard library so the control
plane remains inspectable, portable, and independent of model providers.
"""

from __future__ import annotations

import base64
import builtins
import codecs
import fnmatch
import getpass
import json
import os
import platform
import re
import secrets
import stat
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlparse

import host_scheduler as host_scheduler_policy

SCHEMA_VERSION = 1
FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
CLAIM_AUTHORITY_CLASSES = frozenset({"HOSTED_LAUNCH", "PRIVILEGED_INTERNAL"})
HOSTED_CLAIM_AUTHORITY = "HOSTED_LAUNCH"
INTERNAL_CLAIM_AUTHORITY = "PRIVILEGED_INTERNAL"
_INTERNAL_CLAIM_CAPABILITY = object()
CLAIM_COMMIT_EMAIL = "autopilot-claim@hive-mind.invalid"
RECEIPT_COMMIT_EMAIL = "autopilot-receipt@hive-mind.invalid"
ROLE_NAMES = (
    "orchestrator",
    "explorer",
    "architect",
    "builder",
    "curator",
    "integrator",
    "steward",
    "optimizer",
)
UNSAFE_REMEDIATION_MARKERS = (
    "disable tls",
    "skip tls",
    "disable certificate",
    "skip certificate",
    "disable revocation",
    "skip revocation",
    "sslverify=false",
    "verify=false",
    "ignore certificate",
)
UNSAFE_RETRY_ARGUMENT_MARKERS = (
    "git_ssl_no_verify",
    "curl_insecure",
    "sslverify=false",
    "sslverify=0",
    "http.sslverify=false",
    "http.sslverify=0",
    "schannel.checkrevoke=false",
    "schannel.checkrevoke=0",
    "gnutlsverify=false",
    "--insecure",
    "-k",
)
SUBTASK_EXECUTION_SEQUENCE = (
    "fetch_current_singleton_release",
    "install_current_github_snapshot",
    "reconcile_target",
    "run_doctor_and_status",
    "dispatch_explicit_start_now",
    "claim_remote_node_branch",
)
STALE_TARGET_RECOVERY_SEQUENCE = (
    "preserve_scoped_work_with_node_named_stash",
    "verify_current_singleton_remote_sha",
    "refresh_validated_github_snapshot",
    "archive_stale_runtime_projection",
    "retire_exact_stale_remote_claim_ref",
    "install_snapshot_and_reconcile",
    "doctor_status_dispatch_and_reclaim",
    "apply_exact_node_named_stash",
    "verify_changed_paths_against_node_scope",
)
SAFE_GIT_TRANSPORT_ENVIRONMENT_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)
SAFE_GIT_RUNTIME_ENVIRONMENT_KEYS = (
    "PATH",
    "PATHEXT",
    "SystemRoot",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "LOCALAPPDATA",
    "APPDATA",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "LANG",
    "LC_ALL",
)
SUBTASK_STATES = frozenset(
    {
        "PENDING",
        "ACTIVE",
        "IDLE_UNCOLLECTED",
        "BLOCKED_RECOVERABLE",
        "SUCCEEDED",
        "BLOCKED_EXTERNAL_AUTHORITY",
    }
)
SUBTASK_SETTLED_STATES = frozenset({"SUCCEEDED", "BLOCKED_EXTERNAL_AUTHORITY"})
LEGAL_STATES = (
    "BOOTSTRAP_REQUIRED",
    "BOOTSTRAP_INVALID",
    "READY",
    "CLAIMED",
    "RUNNING",
    "WAITING_FOR_RECEIPT",
    "PR_OPEN",
    "CI_FAILED",
    "REPAIR_REQUIRED",
    "RECONCILIATION_REQUIRED",
    "INTEGRATION_READY",
    "INTEGRATING",
    "PROMOTION_READY",
    "BLOCKED",
    "ESCALATION_REQUIRED",
    "QUARANTINED",
    "COMPLETE",
    "SUPERSEDED",
    "CANCELLED",
    "REPLAN_REQUIRED",
)
TERMINAL_STATES = {
    "COMPLETE",
    "SUPERSEDED",
    "CANCELLED",
    "QUARANTINED",
}
HUMAN_AUTHORITY_CLASSES = {
    "credential_or_secret",
    "legal_or_regulatory_signoff",
    "financial_spend",
    "production_access",
    "protected_branch_merge",
    "owner_value_choice",
    "personal_consent",
    "external_contractual_commitment",
}
CONSULTATION_DECISIONS = {
    "RESOLVED",
    "REMAND",
    "REPLAN",
    "BLOCKED_EVIDENCE",
    "TRUE_AUTHORITY_REQUIRED",
    "QUARANTINE",
}
CHEATING_DISPOSITIONS = {"NOT_APPLICABLE", "CONFIRMED", "DISPROVED", "UNRESOLVED"}
_STATUS_READ_ONLY_GIT_COMMANDS = frozenset(
    {"cat-file", "diff", "log", "merge-base", "rev-parse", "show"}
)
AUTHORITY_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _compact_authority_path_id(authority_id: str) -> str:
    """Bound authority filenames while their documents retain the full digest."""

    if AUTHORITY_ID.fullmatch(authority_id) is None:
        raise ConfigurationError("authority path identity is invalid")
    return authority_id.removeprefix("sha256:")[:20]


_LOADED_CONTROLLER_PATH = Path(__file__).resolve()
_LOADED_CONTROLLER_DIGEST = "sha256:" + sha256(
    _LOADED_CONTROLLER_PATH.read_bytes()
).hexdigest()
if not hasattr(builtins, "_hive_mind_runtime_lock_local_v1"):
    setattr(builtins, "_hive_mind_runtime_lock_local_v1", threading.local())
_RUNTIME_LOCK_LOCAL = getattr(builtins, "_hive_mind_runtime_lock_local_v1")
if not hasattr(builtins, "_hive_mind_loaded_kernel_identities_v1"):
    setattr(builtins, "_hive_mind_loaded_kernel_identities_v1", {})
_LOADED_RUNTIME_KERNEL_IDENTITIES = getattr(
    builtins, "_hive_mind_loaded_kernel_identities_v1"
)


class AutopilotError(RuntimeError):
    """The deterministic control plane cannot safely continue."""


class ConfigurationError(AutopilotError):
    """Repository-resident control-plane configuration is invalid."""


class CapacityAdmissionDenied(ConfigurationError):
    """A valid host-capacity request lost admission to the aggregate budget."""


class ClaimError(AutopilotError):
    """A node claim or lease operation is invalid."""


class ReceiptError(AutopilotError):
    """A node completion receipt is invalid."""


def _is_link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(callable(is_junction) and is_junction())


def _absolute_without_resolving(path: str | Path) -> Path:
    return Path(os.path.abspath(os.fspath(path))).absolute()


def _reject_link_components(path: str | Path, *, label: str) -> Path:
    """Reject every existing link/junction before any canonicalizing resolve."""

    absolute = _absolute_without_resolving(path)
    chain = [absolute, *absolute.parents]
    for component in reversed(chain):
        if _is_link_like(component):
            raise ConfigurationError(f"{label} contains a link component: {component}")
    return absolute


def _linked_worktree_common_dir(repo_root: Path) -> Path | None:
    """Return Git's common directory without invoking Git or mutating its locks."""

    marker = repo_root / ".git"
    if _is_link_like(marker):
        raise ConfigurationError("Git metadata path must not be a link")
    if marker.is_dir():
        return marker.resolve()
    if not marker.exists():
        return None
    if not marker.is_file():
        raise ConfigurationError("Git metadata marker is not a file or directory")
    try:
        text = marker.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as error:
        raise ConfigurationError(f"cannot read Git worktree marker: {error}") from error
    prefix = "gitdir:"
    if not text.casefold().startswith(prefix):
        raise ConfigurationError("Git worktree marker has an unsupported format")
    raw_git_dir = text[len(prefix):].strip()
    if not raw_git_dir:
        raise ConfigurationError("Git worktree marker has no gitdir")
    git_dir = Path(raw_git_dir)
    if not git_dir.is_absolute():
        git_dir = marker.parent / git_dir
    git_dir = _reject_link_components(git_dir, label="Git metadata path")
    git_dir = git_dir.resolve()
    common_marker = git_dir / "commondir"
    if _is_link_like(common_marker):
        raise ConfigurationError("Git commondir marker must not be a link")
    if not common_marker.is_file():
        raise ConfigurationError(
            "separate Git metadata requires an explicit supported commondir"
        )
    try:
        raw_common = common_marker.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as error:
        raise ConfigurationError(f"cannot read Git commondir marker: {error}") from error
    if not raw_common:
        raise ConfigurationError("Git commondir marker is empty")
    common = Path(raw_common)
    if not common.is_absolute():
        common = git_dir / common
    common = _reject_link_components(common, label="Git common directory")
    common = common.resolve()
    if not common.is_dir():
        raise ConfigurationError("Git common directory does not exist")
    return common


def resolve_repository_state_dir(
    repo_root: str | Path,
    state_dir: str | Path | None = None,
) -> Path:
    """Resolve one runtime-state authority for every linked Git worktree.

    An explicit argument (or ``HIVE_MIND_RUNTIME_STATE_DIR``) is the federation
    boundary for independent clones/applications.  Otherwise linked worktrees use
    the primary worktree's existing ``.autopilot/state`` so legacy state is adopted
    in place instead of copied or split across competing ledgers.
    """

    root = _reject_link_components(repo_root, label="repository root").resolve()
    repository_identity = runtime_repository_identity(root)
    sealed_repository = (
        str(repository_identity["repository"])
        if repository_identity is not None
        else None
    )
    sealed_transport = (
        str(repository_identity["transport_digest"])
        if repository_identity is not None
        else None
    )
    common = _linked_worktree_common_dir(root)
    locator_path = (
        common / "hive-mind-runtime-root.json" if common is not None else None
    )
    bound_path: Path | None = None
    if locator_path is not None and (
        locator_path.exists() or _is_link_like(locator_path)
    ):
        _reject_link_components(
            locator_path, label="repository runtime-root locator"
        )
        if not locator_path.is_file():
            raise ConfigurationError(
                "repository runtime-root locator is not a regular file"
            )
        try:
            raw = locator_path.read_bytes()
            value = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_strict_json_pairs,
                parse_constant=_reject_json_constant,
            )
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            raise ConfigurationError("repository runtime-root locator is malformed") from error
        expected_fields = {
            "schema_version",
            "kind",
            "repository",
            "transport_digest",
            "coordination_dir",
            "record_id",
        }
        material = dict(value) if isinstance(value, Mapping) else {}
        record_id = material.pop("record_id", None)
        if (
            not isinstance(value, Mapping)
            or set(value) != expected_fields
            or value.get("schema_version") != 1
            or value.get("kind") != "hive-mind-repository-runtime-root-v1"
            or (
                sealed_repository is not None
                and value.get("repository") != sealed_repository
            )
            or (
                sealed_transport is not None
                and value.get("transport_digest") != sealed_transport
            )
            or record_id != digest_json(material)
            or raw
            != (
                json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                    allow_nan=False,
                )
                + "\n"
            ).encode("utf-8")
        ):
            raise ConfigurationError("repository runtime-root locator is invalid")
        configured_root = value.get("coordination_dir")
        if not isinstance(configured_root, str) or not Path(configured_root).is_absolute():
            raise ConfigurationError("repository runtime-root locator path is invalid")
        bound_path = _reject_link_components(
            configured_root, label="bound repository runtime root"
        ).resolve()
    registry_bound: Path | None = None
    if sealed_repository is not None:
        host_root = resolve_host_runtime_dir()
        if (host_root / "host-runtime-identity.json").is_file():
            host_root = require_host_runtime(host_root)
            registry_events = _host_repository_registry_events(host_root)
            repository_matches = [
                event
                for event in registry_events
                if event.get("repository") == sealed_repository
            ]
            transport_matches = [
                event
                for event in registry_events
                if event.get("transport_digest") == sealed_transport
            ]
            if any(
                event.get("transport_digest") != sealed_transport
                for event in repository_matches
            ) or any(
                event.get("repository") != sealed_repository
                for event in transport_matches
            ):
                raise ConfigurationError(
                    "host repository registry aliases repository name or Git transport"
                )
            registry_matches = repository_matches or transport_matches
            if registry_matches:
                selected_root = str(registry_matches[-1]["coordination_dir"])
                registry_bound = _reject_link_components(
                    selected_root,
                    label="host-registered repository runtime root",
                ).resolve()
                if bound_path is not None and bound_path != registry_bound:
                    raise ConfigurationError(
                        "Git-common and host repository locators disagree"
                    )
                bound_path = registry_bound
    selected = state_dir
    if selected is None:
        configured = os.environ.get("HIVE_MIND_RUNTIME_STATE_DIR", "").strip()
        selected = configured or None
    if selected is not None:
        selected_path = Path(selected).expanduser()
        if not selected_path.is_absolute():
            raise ConfigurationError("explicit runtime state path must be absolute")
        selected_path = _reject_link_components(
            selected_path,
            label="runtime state path",
        )
        candidate = selected_path.resolve()
        if bound_path is not None and candidate != bound_path:
            raise ConfigurationError(
                "repository runtime root is already immutably bound; an override cannot create a peer arbiter"
            )
    else:
        if bound_path is not None:
            candidate = bound_path
        elif common is not None and common.name != ".git":
            raise ConfigurationError(
                "nonstandard Git common directories require an explicit runtime state path"
            )
        else:
            primary = common.parent if common is not None else None
            candidate = (
                primary / ".autopilot" / "state"
                if primary is not None
                else root / ".autopilot" / "state"
            )
            candidate = _reject_link_components(candidate, label="runtime state path")
            candidate = candidate.resolve()
    if candidate.exists() and (not candidate.is_dir() or _is_link_like(candidate)):
        raise ConfigurationError("runtime state path must be a real directory")
    return candidate


def bind_repository_runtime_root(
    repo_root: str | Path,
    coordination_dir: str | Path,
    repository_identity: Mapping[str, object],
) -> Path:
    """Install the sole coordination-root pointer with Git-common O_EXCL/CAS."""

    root = _reject_link_components(repo_root, label="repository root").resolve()
    common = _linked_worktree_common_dir(root)
    if common is None:
        common = root / ".git"
    if common.name != ".git" or not common.is_dir():
        raise ConfigurationError(
            "canonical runtime-root binding requires the standard shared Git common directory"
        )
    directory = _reject_link_components(
        coordination_dir, label="runtime state path"
    ).resolve()
    repository = repository_identity.get("repository")
    transport_digest = repository_identity.get("transport_digest")
    if not isinstance(repository, str) or not repository.strip():
        raise ConfigurationError("runtime-root binding repository identity is invalid")
    if (
        not isinstance(transport_digest, str)
        or AUTHORITY_ID.fullmatch(transport_digest) is None
    ):
        raise ConfigurationError("runtime-root binding Git transport identity is invalid")
    material: dict[str, object] = {
        "schema_version": 1,
        "kind": "hive-mind-repository-runtime-root-v1",
        "repository": repository,
        "transport_digest": transport_digest,
        "coordination_dir": str(directory),
    }
    value = {**material, "record_id": digest_json(material)}
    payload = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        + "\n"
    ).encode("utf-8")
    locator = common / "hive-mind-runtime-root.json"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(locator, flags, 0o600)
    except FileExistsError:
        try:
            installed = locator.read_bytes()
        except OSError as error:
            raise ConfigurationError("cannot read repository runtime-root locator") from error
        if installed != payload:
            raise ConfigurationError(
                "repository already has a conflicting canonical runtime root"
            )
    else:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            common_descriptor = os.open(common, os.O_RDONLY)
            try:
                os.fsync(common_descriptor)
            finally:
                os.close(common_descriptor)
    return locator


def runtime_lock_order_key(path: str | Path) -> tuple[int, str]:
    """Return the one process-wide authority lock order.

    The path, rather than the importing module, determines the authority plane.
    This keeps linked worktrees and separately imported controller modules on the
    same ordering contract.  Unknown locks may be held alone but cannot be mixed
    into an authority transaction until their rank is deliberately registered.
    """

    absolute = _absolute_without_resolving(path)
    normalized = os.path.normcase(os.path.normpath(str(absolute)))
    name = absolute.name.casefold()
    parts = tuple(part.casefold() for part in absolute.parts)
    execution_scoped = any(
        part == "executions"
        and index + 2 < len(parts)
        and re.fullmatch(r"(?:[0-9a-f]{20}|[0-9a-f]{64})", parts[index + 1])
        is not None
        and parts[index + 2] == "locks"
        for index, part in enumerate(parts)
    )
    if name in {"github-snapshot-coordinator.lock", "execution-supervisor.lock"}:
        rank = 5
    elif name == "host-authority.lock":
        rank = 10
    elif name == "runtime-authority-bootstrap-migration.lock":
        rank = 20
    elif name == "arbiter-authority.lock":
        rank = 30
    elif name == "host-reservations.lock":
        rank = 35
    elif execution_scoped:
        rank = {
            "dispatcher-admission.lock": 50,
            "authority-ledger-initialization.lock": 60,
            "task-bindings.lock": 70,
            "sidecar-bindings.lock": 80,
            "attended-host.lock": 110,
            "runtime-identity.lock": 130,
        }.get(name, 1000)
    else:
        # Pre-READY migration locks occupy their own ordered plane between the
        # raw repository arbiter and initialized execution authority.
        rank = {
            "dispatcher-admission.lock": 40,
            "authority-ledger-initialization.lock": 41,
            "task-bindings.lock": 42,
            "sidecar-bindings.lock": 43,
            # This is the migration-only repository-root attended ledger.  It
            # must be frozen before default-execution locks are materialized;
            # the execution-scoped attended lock retains its late rank above.
            "attended-host.lock": 44,
            "claim-authority.lock": 90,
            "global-validation-lease.lock": 100,
            "runtime-identity.lock": 130,
        }.get(name, 1000)
    return rank, normalized


@contextmanager
def runtime_file_lock(
    path: str | Path,
    *,
    timeout_seconds: float = 10.0,
):
    """Hold a cross-process one-byte lock in durable runtime state."""

    lock_path = _reject_link_components(path, label="runtime lock path")
    if timeout_seconds <= 0:
        raise ConfigurationError("runtime lock timeout must be positive")
    lock_key = os.path.normcase(os.path.normpath(str(lock_path)))
    held = getattr(_RUNTIME_LOCK_LOCAL, "held", None)
    if held is None:
        held = {}
        _RUNTIME_LOCK_LOCAL.held = held
    if lock_key in held:
        held[lock_key] += 1
        try:
            yield
        finally:
            held[lock_key] -= 1
        return
    held_order = getattr(_RUNTIME_LOCK_LOCAL, "held_order", None)
    if held_order is None:
        held_order = []
        _RUNTIME_LOCK_LOCAL.held_order = held_order
    requested_order = runtime_lock_order_key(lock_path)
    if held_order:
        prior_order = held_order[-1]
        if prior_order[0] == 1000 or requested_order[0] == 1000:
            raise ConfigurationError(
                "unclassified runtime locks cannot be combined with authority locks"
            )
        if requested_order < prior_order:
            raise ConfigurationError(
                "runtime lock order inversion: "
                f"requested {lock_path} after {prior_order[1]}"
            )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = _reject_link_components(lock_path, label="runtime lock path")
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_BINARY", 0)
    )
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        _verify_open_regular_file_identity(
            descriptor,
            lock_path,
            label="runtime lock path",
        )
    except BaseException:
        os.close(descriptor)
        raise
    locked = False
    deadline = time.monotonic() + timeout_seconds
    while not locked:
        try:
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"0")
                os.fsync(descriptor)
                os.lseek(descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError:
            if time.monotonic() >= deadline:
                os.close(descriptor)
                raise ConfigurationError(f"runtime lock timed out: {lock_path}")
            time.sleep(0.01)
    held[lock_key] = 1
    held_order.append(requested_order)
    try:
        _verify_open_regular_file_identity(
            descriptor,
            lock_path,
            label="runtime lock path",
        )
        yield
    finally:
        held.pop(lock_key, None)
        if not held_order or held_order[-1] != requested_order:
            os.close(descriptor)
            raise ConfigurationError("runtime lock ownership stack is corrupted")
        held_order.pop()
        try:
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_UN)
            _verify_open_regular_file_identity(
                descriptor,
                lock_path,
                label="runtime lock path",
            )
        finally:
            os.close(descriptor)


def runtime_file_lock_is_held(path: str | Path) -> bool:
    """Return whether this thread currently owns the exact runtime lock.

    This is intentionally only an ownership verifier.  It never creates a path,
    waits, or grants authority, so bootstrap-only migration code can safely prove
    that a caller already holds the standard lock before using an unlocked helper.
    """

    lock_path = _reject_link_components(path, label="runtime lock path")
    lock_key = os.path.normcase(os.path.normpath(str(lock_path)))
    held = getattr(_RUNTIME_LOCK_LOCAL, "held", None)
    return isinstance(held, dict) and int(held.get(lock_key, 0)) > 0


@dataclass(frozen=True, slots=True)
class NodeView:
    node_id: str
    state: str
    reasons: tuple[str, ...]
    dependencies: tuple[str, ...]
    active_claim_owner: str | None = None
    branch: str | None = None
    pr_number: int | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class _StatusCommitGraph:
    """Commit facts proven by one immutable target-history observation."""

    parents: dict[str, tuple[str, ...]]
    trees: dict[str, str]
    ancestor_cache: dict[str, frozenset[str]]

    @classmethod
    def from_log(cls, output: str) -> _StatusCommitGraph:
        parents: dict[str, tuple[str, ...]] = {}
        trees: dict[str, str] = {}
        for raw_record in output.split("\x1e"):
            parts = raw_record.strip("\n").split("\x1f", 3)
            if len(parts) != 4:
                continue
            commit, parents_text, tree, _ = parts
            commit_parents = tuple(parents_text.split())
            if (
                FULL_SHA.fullmatch(commit) is None
                or FULL_SHA.fullmatch(tree) is None
                or any(FULL_SHA.fullmatch(parent) is None for parent in commit_parents)
            ):
                continue
            parents[commit] = commit_parents
            trees[commit] = tree
        return cls(parents, trees, {})

    def is_ancestor(self, ancestor: str, descendant: str) -> bool | None:
        """Return graph truth, or ``None`` when the descendant was not observed."""

        if descendant not in self.parents:
            return None
        cached = self.ancestor_cache.get(descendant)
        if cached is None:
            observed: set[str] = set()
            pending = [descendant]
            while pending:
                commit = pending.pop()
                if commit in observed:
                    continue
                observed.add(commit)
                pending.extend(self.parents.get(commit, ()))
            cached = frozenset(observed)
            self.ancestor_cache[descendant] = cached
        return ancestor in cached


def utc_now() -> datetime:
    return datetime.now(UTC)


def format_time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_time(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be non-empty text")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest_json(value: object) -> str:
    return "sha256:" + sha256(canonical_bytes(value)).hexdigest()


def read_json(path: Path) -> Any:
    try:
        raw = _read_regular_authority_bytes(path, label=f"JSON file {path}")
        # UTF-8 is the only admitted text encoding.  In particular, do not let
        # ``utf-8-sig`` silently turn a BOM-bearing authority file into a peer
        # representation of the same object.
        text = raw.decode("utf-8")
        if text.startswith("\ufeff"):
            raise UnicodeError("UTF-8 BOM is not admitted")
        return json.loads(
            text,
            object_pairs_hook=_strict_json_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number is forbidden: {value}")
            ),
        )
    except FileNotFoundError as error:
        raise ConfigurationError(f"required file is missing: {path}") from error
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise ConfigurationError(f"cannot parse JSON file {path}: {error}") from error


def read_strict_canonical_json(
    path: Path,
    *,
    label: str,
    expected_fields: set[str] | frozenset[str] | None = None,
) -> Any:
    """Read one bounded UTF-8 JSON representation with no peer encodings."""

    raw = _read_regular_authority_bytes(path, label=label)
    return parse_strict_canonical_json_bytes(
        raw,
        label=label,
        expected_fields=expected_fields,
    )


def parse_strict_canonical_json_bytes(
    raw: bytes,
    *,
    label: str,
    expected_fields: set[str] | frozenset[str] | None = None,
) -> Any:
    """Strict canonical JSON parser for authenticated Git/blob bytes."""

    try:
        text = raw.decode("utf-8")
        if text.startswith("\ufeff"):
            raise UnicodeError("UTF-8 BOM is not admitted")
        value = json.loads(
            text,
            object_pairs_hook=_strict_json_pairs,
            parse_constant=_reject_json_constant,
        )
        canonical = (
            json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        ).encode("utf-8")
    except (UnicodeError, ValueError, json.JSONDecodeError, TypeError) as error:
        raise ConfigurationError(f"{label} is malformed") from error
    if raw != canonical:
        raise ConfigurationError(f"{label} has a noncanonical JSON encoding")
    if expected_fields is not None and (
        not isinstance(value, Mapping) or set(value) != set(expected_fields)
    ):
        raise ConfigurationError(f"{label} schema is ambiguous")
    return value


def windows_replace_retry_enabled() -> bool:
    """Return whether atomic replacement needs the bounded Windows retry."""

    return os.name == "nt"


def _fsync_parent_directory(directory: Path) -> None:
    """Persist a namespace entry where the platform exposes directory fsync."""

    if os.name == "nt":
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        # Keep the temporary basename independent of a content-addressed target
        # name.  Repeating a 64-byte digest here crosses legacy Windows MAX_PATH
        # even when the final authority path itself is valid.
        prefix=".tmp.",
        delete=False,
    ) as temporary:
        temporary.write(encoded)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    # Windows cannot reliably replace an open NamedTemporaryFile. Close the
    # handle first, then retain a bounded retry for transient scanner/indexer locks.
    for attempt in range(5):
        try:
            os.replace(temporary_path, path)
            break
        except PermissionError:
            if not windows_replace_retry_enabled() or attempt == 4:
                raise
            time.sleep(0.01 * (2**attempt))
    _fsync_parent_directory(path.parent)


def exclusive_write_bytes_or_identical(path: Path, payload: bytes) -> bool:
    """Create immutable evidence atomically, accepting only identical retries."""

    path = _absolute_without_resolving(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _reject_link_components(path.parent, label="immutable evidence directory")
    if path.exists() or _is_link_like(path):
        _reject_link_components(path, label="immutable evidence path")
        try:
            current = path.read_bytes()
        except OSError as error:
            raise ConfigurationError(
                f"cannot read immutable evidence {path}: {error}"
            ) from error
        if current != payload:
            raise ConfigurationError(
                f"immutable evidence conflicts with existing bytes: {path}"
            )
        return False
    with tempfile.NamedTemporaryFile(
        "wb",
        dir=path.parent,
        prefix=".tmp.",
        delete=False,
    ) as temporary:
        temporary.write(payload)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    try:
        try:
            os.link(temporary_path, path, follow_symlinks=False)
        except FileExistsError:
            _reject_link_components(path, label="immutable evidence path")
            if path.read_bytes() != payload:
                raise ConfigurationError(
                    f"immutable evidence conflicts with concurrent bytes: {path}"
                )
            return False
        _fsync_parent_directory(path.parent)
        return True
    except OSError as error:
        if isinstance(error, ConfigurationError):
            raise
        raise ConfigurationError(
            f"cannot create immutable evidence {path}: {error}"
        ) from error
    finally:
        temporary_path.unlink(missing_ok=True)


def exclusive_write_json_or_identical(path: Path, value: object) -> bool:
    encoded = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    return exclusive_write_bytes_or_identical(path, encoded)


def exclusive_transition_archive(
    path: Path,
    current: Mapping[str, Any],
    updates: Mapping[str, Any],
    *,
    timestamp_key: str,
    now: datetime,
) -> Mapping[str, Any]:
    """Create or exactly resume one immutable authority transition archive."""

    timestamp = format_time(now)
    if path.exists() or _is_link_like(path):
        _reject_link_components(path, label="authority transition archive")
        existing = read_json(path)
        if isinstance(existing, Mapping) and isinstance(
            existing.get(timestamp_key), str
        ):
            timestamp = str(existing[timestamp_key])
    record = {**current, **updates, timestamp_key: timestamp}
    exclusive_write_json_or_identical(path, record)
    return record


def _canonical_remote_transport(value: str, *, repo_root: Path) -> str:
    raw = value.strip()
    if not raw or any(character in raw for character in "\r\n\0"):
        raise ConfigurationError("canonical Git remote transport is empty or unsafe")
    scp = re.fullmatch(r"(?:(?P<user>[^@/:]+)@)?(?P<host>[^/:]+):(?P<path>.+)", raw)
    if scp is not None and "://" not in raw:
        host = str(scp.group("host")).casefold()
        path = "/" + str(scp.group("path")).replace("\\", "/").lstrip("/")
        return f"ssh://{host}{path.rstrip('/')}"
    parsed = urlparse(raw)
    if parsed.scheme:
        if parsed.query or parsed.fragment or parsed.password is not None:
            raise ConfigurationError(
                "canonical Git remote transport cannot contain query, fragment, or password"
            )
        scheme = parsed.scheme.casefold()
        if scheme == "file":
            path = Path(parsed.path)
            if not path.is_absolute():
                raise ConfigurationError("file Git remote must be absolute")
            return "file://" + str(
                _reject_link_components(path, label="canonical file remote").resolve()
            ).replace("\\", "/")
        host = (parsed.hostname or "").casefold()
        if not host:
            raise ConfigurationError("canonical Git remote has no host")
        port = f":{parsed.port}" if parsed.port is not None else ""
        path = parsed.path.replace("\\", "/").rstrip("/")
        if not path or path == "/":
            raise ConfigurationError("canonical Git remote has no repository path")
        # User names are authentication routing, not repository identity. Secrets
        # are rejected above and never persisted in shared authority metadata.
        return f"{scheme}://{host}{port}{path}"
    path = Path(raw)
    if not path.is_absolute():
        path = repo_root / path
    return str(
        _reject_link_components(path, label="canonical local Git remote").resolve()
    ).replace("\\", "/")


def _origin_transport_identity(repo_root: Path) -> Mapping[str, object]:
    environment = {
        key: value
        for key in SAFE_GIT_RUNTIME_ENVIRONMENT_KEYS
        if (value := os.environ.get(key))
    }

    common = _linked_worktree_common_dir(repo_root)
    if common is None:
        raise ConfigurationError("canonical Git remote requires repository metadata")
    config_path = _reject_link_components(
        common / "config", label="canonical Git configuration"
    )
    if not config_path.is_file():
        raise ConfigurationError("canonical Git configuration is absent")

    def values(key: str) -> tuple[str, ...]:
        completed = subprocess.run(
            (
                "git",
                "config",
                "--file",
                str(config_path),
                "--get-all",
                key,
            ),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            env=environment,
        )
        if completed.returncode not in {0, 1}:
            raise ConfigurationError(
                f"cannot authenticate canonical Git remote {key}: {completed.stderr.strip()}"
            )
        return tuple(line.strip() for line in completed.stdout.splitlines() if line.strip())

    fetch_values = values("remote.origin.url")
    push_values = values("remote.origin.pushurl")
    if len(fetch_values) != 1 or len(push_values) > 1:
        raise ConfigurationError(
            "canonical origin must have exactly one fetch URL and at most one push URL"
        )
    fetch = _canonical_remote_transport(fetch_values[0], repo_root=repo_root)
    push = _canonical_remote_transport(
        push_values[0] if push_values else fetch_values[0], repo_root=repo_root
    )
    material: dict[str, object] = {
        "kind": "hive-mind-canonical-git-transport-v1",
        "remote_name": "origin",
        "fetch": fetch,
        "push": push,
    }
    return {**material, "transport_digest": digest_json(material)}


def runtime_repository_identity(
    repo_root: str | Path,
) -> Mapping[str, object] | None:
    root = _reject_link_components(repo_root, label="repository root").resolve()
    control_path = root / ".autopilot" / "control-plane.json"
    if not control_path.is_file():
        # Lightweight unit fixtures without a control plane retain their isolated
        # local ledgers; production repositories always carry this document.
        return None
    control = read_strict_canonical_json(
        control_path, label="runtime repository control plane"
    )
    target = control.get("target") if isinstance(control, Mapping) else None
    repository = target.get("repository") if isinstance(target, Mapping) else None
    if not isinstance(repository, str) or not repository.strip():
        raise ConfigurationError("control-plane target repository identity is required")
    transport = _origin_transport_identity(root)
    return {
        "schema_version": 1,
        "kind": "hive-mind-runtime-authority-identity-v1",
        "repository": repository.strip(),
        "canonical_remote_fetch": transport["fetch"],
        "canonical_remote_push": transport["push"],
        "transport_digest": transport["transport_digest"],
    }


KERNEL_TEMPLATE_COMPONENTS = (
    ".autopilot/templates/worker.md",
    ".autopilot/templates/repair.md",
    ".autopilot/templates/consultation.md",
    ".autopilot/templates/reconciliation.md",
    ".autopilot/templates/integration.md",
    ".autopilot/templates/promotion.md",
    ".autopilot/templates/replan.md",
    ".autopilot/templates/human-escalation.md",
)

KERNEL_BUNDLE_COMPONENTS = (
    ".autopilot/bin/controller.py",
    ".autopilot/bin/autopilot.py",
    ".autopilot/bin/orchestration.py",
    ".autopilot/bin/sidecar_execution.py",
    ".autopilot/bin/host_execution.py",
    ".autopilot/bin/attended_host.py",
    ".autopilot/bin/app_server_host.py",
    ".autopilot/bin/execution_supervisor.py",
    ".autopilot/bin/release_barrier.py",
    ".autopilot/bin/round_driver.py",
    ".autopilot/bin/healing.py",
    ".autopilot/bin/learning.py",
    ".autopilot/bin/github_snapshot.py",
    ".autopilot/bin/sealed_recovery.py",
    ".autopilot/bin/durable_controller.py",
    ".autopilot/bin/dag_standard.py",
    ".autopilot/bin/hermetic_ci.py",
    ".autopilot/bin/host_scheduler.py",
    ".autopilot/orchestration-policy.json",
    ".autopilot/workflow-policy.json",
    *KERNEL_TEMPLATE_COMPONENTS,
)


def _runtime_kernel_identity_from_disk(
    repo_root: str | Path,
) -> Mapping[str, object]:
    """Compute the exact on-disk FSM bundle without granting writer authority."""

    root = _reject_link_components(repo_root, label="repository root").resolve()
    components: list[Mapping[str, object]] = []
    for relative in KERNEL_BUNDLE_COMPONENTS:
        path = root.joinpath(*Path(relative).parts)
        if path.exists() or _is_link_like(path):
            _reject_link_components(path, label=f"kernel component {relative}")
            if not path.is_file():
                raise ConfigurationError(
                    f"kernel component is not a regular file: {relative}"
                )
            payload = path.read_bytes()
            component_digest: str | None = "sha256:" + sha256(payload).hexdigest()
        else:
            if relative in KERNEL_TEMPLATE_COMPONENTS:
                raise ConfigurationError(
                    f"required kernel prompt template is missing: {relative}"
                )
            component_digest = None
        components.append({"path": relative, "digest": component_digest})
    # ``sys.executable`` is supplied by the already-running interpreter rather
    # than by a repository/runtime authority document.  Hosted Python
    # installations conventionally expose it through a stable launcher
    # symlink (for example, ``/opt/.../bin/python`` on GitHub Actions).  Bind
    # the canonical target bytes, while retaining link rejection for every
    # caller-controlled repository and authority path above.
    try:
        executable = Path(sys.executable).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ConfigurationError(
            f"Python interpreter executable is unavailable: {error}"
        ) from error
    _reject_link_components(executable, label="resolved Python interpreter executable")
    if not executable.is_file():
        raise ConfigurationError("Python interpreter executable is unavailable")
    interpreter: dict[str, object] = {
        "implementation": sys.implementation.name,
        "cache_tag": sys.implementation.cache_tag,
        "version": [
            sys.version_info.major,
            sys.version_info.minor,
            sys.version_info.micro,
        ],
        "byteorder": sys.byteorder,
        "optimize": sys.flags.optimize,
        "executable_digest": "sha256:"
        + sha256(executable.read_bytes()).hexdigest(),
    }
    interpreter_policy_digest = digest_json(
        {"kind": "hive-mind-interpreter-policy-v1", **interpreter}
    )
    bundle_material: dict[str, object] = {
        "kind": "hive-mind-kernel-bundle-v1",
        "components": components,
        "interpreter_policy_digest": interpreter_policy_digest,
    }
    identity = {
        "schema_version": 1,
        **bundle_material,
        "bundle_digest": digest_json(bundle_material),
        "interpreter": interpreter,
    }
    controller_component = next(
        (
            item
            for item in components
            if item.get("path") == ".autopilot/bin/controller.py"
        ),
        None,
    )
    if (
        not isinstance(controller_component, Mapping)
        or controller_component.get("digest") != _LOADED_CONTROLLER_DIGEST
    ):
        raise ConfigurationError(
            "the loaded controller differs from the selected repository kernel; "
            "restart from the selected checkout before mutating authority"
        )
    return identity


def runtime_kernel_identity(repo_root: str | Path) -> Mapping[str, object]:
    """Return this process's immutable execution-kernel writer identity.

    Re-reading bytes alone is not a writer fence: a long-lived interpreter can
    continue executing the old state machine after its files are replaced.  The
    first authenticated bundle observed for a repository is therefore pinned to
    the loaded process.  Later disk drift fails closed; an explicit upgrade must
    be launched by a fresh interpreter loaded from the successor checkout.
    """

    root = _reject_link_components(repo_root, label="repository root").resolve()
    cache_key = (
        str(_LOADED_CONTROLLER_PATH),
        _LOADED_CONTROLLER_DIGEST,
        os.path.normcase(str(root)),
    )
    current = _runtime_kernel_identity_from_disk(root)
    cached = _LOADED_RUNTIME_KERNEL_IDENTITIES.get(cache_key)
    if cached is None:
        _LOADED_RUNTIME_KERNEL_IDENTITIES[cache_key] = dict(current)
        return dict(current)
    if not isinstance(cached, Mapping) or dict(cached) != dict(current):
        raise ConfigurationError(
            "execution kernel bytes changed after this process loaded; "
            "restart before initialization, upgrade, or mutation"
        )
    return dict(cached)


def execution_namespace_identity(
    repository_identity: Mapping[str, object],
    *,
    kernel_identity: Mapping[str, object],
    namespace: str,
    target_branch: str,
    plan_fingerprint: str,
) -> Mapping[str, object]:
    """Derive one stable namespace path and its immutable execution binding."""

    if EXECUTION_NAMESPACE.fullmatch(namespace) is None:
        raise ConfigurationError(
            "execution namespace must match [a-z0-9][a-z0-9._-]{0,63}"
        )
    repository = repository_identity.get("repository")
    transport_digest = repository_identity.get("transport_digest")
    if not isinstance(repository, str) or not repository.strip():
        raise ConfigurationError("execution namespace repository identity is required")
    if (
        not isinstance(transport_digest, str)
        or AUTHORITY_ID.fullmatch(transport_digest) is None
    ):
        raise ConfigurationError("execution namespace Git transport identity is required")
    if not isinstance(target_branch, str) or not target_branch.strip():
        raise ConfigurationError("execution namespace target branch is required")
    if (
        not isinstance(plan_fingerprint, str)
        or AUTHORITY_ID.fullmatch(plan_fingerprint) is None
    ):
        raise ConfigurationError("execution namespace plan fingerprint is invalid")
    kernel_bundle_digest = kernel_identity.get("bundle_digest")
    interpreter_policy_digest = kernel_identity.get("interpreter_policy_digest")
    if (
        AUTHORITY_ID.fullmatch(str(kernel_bundle_digest)) is None
        or AUTHORITY_ID.fullmatch(str(interpreter_policy_digest)) is None
    ):
        raise ConfigurationError("execution namespace kernel identity is invalid")
    key = {
        "kind": EXECUTION_NAMESPACE_KEY_KIND,
        "repository": repository,
        "repository_transport_digest": transport_digest,
        "namespace": namespace,
    }
    execution_id = digest_json(key)
    identity: dict[str, object] = {
        "schema_version": 1,
        "kind": EXECUTION_IDENTITY_KIND,
        "execution_id": execution_id,
        "namespace": namespace,
        "repository": repository,
        "repository_transport_digest": transport_digest,
        "canonical_remote_fetch": repository_identity["canonical_remote_fetch"],
        "canonical_remote_push": repository_identity["canonical_remote_push"],
        "target_branch": target_branch,
        "plan_fingerprint": plan_fingerprint,
        "kernel_bundle_digest": kernel_bundle_digest,
        "interpreter_policy_digest": interpreter_policy_digest,
    }
    identity["record_id"] = digest_json(identity)
    return identity


EXECUTION_IDENTITY_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "execution_id",
        "namespace",
        "repository",
        "repository_transport_digest",
        "canonical_remote_fetch",
        "canonical_remote_push",
        "target_branch",
        "plan_fingerprint",
        "kernel_bundle_digest",
        "interpreter_policy_digest",
        "record_id",
    }
)
EXECUTION_KERNEL_HISTORY_KIND = "hive-mind-execution-kernel-generation-event-v1"
EXECUTION_KERNEL_TRANSITION_KIND = "hive-mind-execution-kernel-transition-v1"
KERNEL_TRANSITION_COMPLETE_KIND = "hive-mind-kernel-transition-complete-v1"
KERNEL_TRANSITION_DIRECTORY = "kt"
KERNEL_TRANSITION_POINTER = "kt.json"
KERNEL_TRANSITION_RECOVERY_DIRECTORY = "kr"
PUBLICATION_RESERVATION_KIND = "hive-mind-publication-reservation-v1"
PUBLICATION_TRANSACTION_KIND = "hive-mind-publication-transaction-v1"
PUBLICATION_ACTIVE_STATUSES = frozenset(
    {"PREPARED", "PINNED", "VALIDATED", "PUBLISHING", "PUBLISH_UNKNOWN"}
)
PUBLICATION_TERMINAL_STATUSES = frozenset(
    {
        "PUBLISHED",
        "SUPERSEDED_INTEGRATED",
        "REJECTED",
        "VALIDATION_FAILED",
        "RECOVERY_REQUIRED",
        "NO_PUSH",
        "INTEGRATION_CONFLICT",
        "EXPIRED_FENCED",
    }
)
PUBLICATION_RESOURCE_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "status",
        "transaction_id",
        "execution_id",
        "release_id",
        "repository",
        "target_branch",
        "expected_target_sha",
        "expires_at",
        "outcome",
        "transaction",
        "record_id",
    }
)
PUBLICATION_TRANSACTION_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "status",
        "transaction_key",
        "attempt_epoch",
        "nonce",
        "transaction_id",
        "execution_namespace",
        "execution_id",
        "release_id",
        "round_id",
        "repository",
        "target_branch",
        "expected_target_sha",
        "authority_digest",
        "authority_baseline_digest",
        "receipt_heads",
        "receipt_heads_digest",
        "transaction_ref",
        "coordinator_id",
        "transaction_lease_nonce",
        "transaction_lease_id",
        "lease_expires_at",
        "publishing_lease_nonce",
        "publishing_lease_id",
        "publishing_lease_expires_at",
        "pinned_sha",
        "validation_evidence",
        "outcome",
        "detail",
        "actor",
        "reserved_at",
        "updated_at",
        "completed_at",
        "record_id",
    }
)
EXECUTION_KERNEL_HISTORY_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "state",
        "identity",
        "actor",
        "reason",
        "recorded_at",
        "previous_identity_record_id",
        "previous_event_id",
        "event_id",
    }
)
KERNEL_TRANSITION_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "authority_plane",
        "state",
        "predecessor_record_id",
        "predecessor_generation",
        "previous_event_id",
        "successor_identity",
        "history_event",
        "history_payload_digest",
        "history_payload_bytes",
        "actor",
        "reason",
        "prepared_at",
        "transition_id",
        "record_id",
    }
)


def _validate_execution_identity_document(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != EXECUTION_IDENTITY_FIELDS:
        raise ConfigurationError("execution namespace identity schema is ambiguous")
    material = dict(value)
    record_id = material.pop("record_id", None)
    if (
        value.get("schema_version") != 1
        or value.get("kind") != EXECUTION_IDENTITY_KIND
        or AUTHORITY_ID.fullmatch(str(value.get("execution_id"))) is None
        or EXECUTION_NAMESPACE.fullmatch(str(value.get("namespace"))) is None
        or not isinstance(value.get("repository"), str)
        or not str(value["repository"]).strip()
        or AUTHORITY_ID.fullmatch(
            str(value.get("repository_transport_digest"))
        )
        is None
        or not isinstance(value.get("canonical_remote_fetch"), str)
        or not isinstance(value.get("canonical_remote_push"), str)
        or not isinstance(value.get("target_branch"), str)
        or not str(value["target_branch"]).strip()
        or AUTHORITY_ID.fullmatch(str(value.get("plan_fingerprint"))) is None
        or AUTHORITY_ID.fullmatch(str(value.get("kernel_bundle_digest"))) is None
        or AUTHORITY_ID.fullmatch(
            str(value.get("interpreter_policy_digest"))
        )
        is None
        or record_id != digest_json(material)
    ):
        raise ConfigurationError("execution namespace identity is invalid")
    expected_id = digest_json(
        {
            "kind": EXECUTION_NAMESPACE_KEY_KIND,
            "repository": value["repository"],
            "repository_transport_digest": value[
                "repository_transport_digest"
            ],
            "namespace": value["namespace"],
        }
    )
    if value.get("execution_id") != expected_id:
        raise ConfigurationError("execution namespace path identity is noncanonical")
    return dict(value)


def _execution_kernel_history(
    execution_dir: str | Path,
    *,
    raw_override: bytes | None = None,
) -> tuple[Mapping[str, object], ...]:
    path = Path(execution_dir) / "execution-kernel-history.jsonl"
    records = (
        _strict_jsonl_records_bytes(
            raw_override, label="execution-kernel generation history"
        )
        if raw_override is not None
        else strict_jsonl_records(path, label="execution-kernel generation history")
    )
    previous_event_id: str | None = None
    previous_identity: Mapping[str, object] | None = None
    seen_kernels: set[tuple[str, str]] = set()
    events: list[Mapping[str, object]] = []
    for index, event in enumerate(records, 1):
        if set(event) != EXECUTION_KERNEL_HISTORY_FIELDS:
            raise ConfigurationError(
                f"execution-kernel history line {index} schema is ambiguous"
            )
        material = dict(event)
        event_id = material.pop("event_id", None)
        identity = _validate_execution_identity_document(event.get("identity"))
        try:
            parse_time(event.get("recorded_at"))
        except (TypeError, ValueError) as error:
            raise ConfigurationError(
                f"execution-kernel history line {index} time is invalid"
            ) from error
        kernel_key = (
            str(identity["kernel_bundle_digest"]),
            str(identity["interpreter_policy_digest"]),
        )
        if (
            event.get("schema_version") != 1
            or event.get("kind") != EXECUTION_KERNEL_HISTORY_KIND
            or event.get("state") != "INSTALLED"
            or not isinstance(event.get("actor"), str)
            or not str(event["actor"]).strip()
            or not isinstance(event.get("reason"), str)
            or not str(event["reason"]).strip()
            or event.get("previous_event_id") != previous_event_id
            or event.get("previous_identity_record_id")
            != (
                previous_identity.get("record_id")
                if previous_identity is not None
                else None
            )
            or event_id != digest_json(material)
            or (
                previous_identity is not None
                and any(
                    identity.get(field) != previous_identity.get(field)
                    for field in EXECUTION_IDENTITY_FIELDS
                    - {
                        "kernel_bundle_digest",
                        "interpreter_policy_digest",
                        "record_id",
                    }
                )
            )
            or kernel_key in seen_kernels
        ):
            raise ConfigurationError(
                f"execution-kernel history line {index} is invalid or replays a retired kernel"
            )
        previous_event_id = str(event_id)
        previous_identity = identity
        seen_kernels.add(kernel_key)
        events.append(dict(event))
    return tuple(events)


def _execution_kernel_generation_event(
    identity: Mapping[str, object],
    *,
    actor: str,
    reason: str,
    recorded_at: str,
    history: Sequence[Mapping[str, object]],
) -> Mapping[str, object]:
    material: dict[str, object] = {
        "schema_version": 1,
        "kind": EXECUTION_KERNEL_HISTORY_KIND,
        "state": "INSTALLED",
        "identity": dict(identity),
        "actor": actor,
        "reason": reason,
        "recorded_at": recorded_at,
        "previous_identity_record_id": (
            history[-1]["identity"]["record_id"] if history else None
        ),
        "previous_event_id": history[-1]["event_id"] if history else None,
    }
    return {**material, "event_id": digest_json(material)}


def _append_execution_kernel_generation(
    execution_dir: Path,
    identity: Mapping[str, object],
    *,
    actor: str,
    reason: str,
    recorded_at: str,
    history: Sequence[Mapping[str, object]],
) -> Mapping[str, object]:
    event = _execution_kernel_generation_event(
        identity,
        actor=actor,
        reason=reason,
        recorded_at=recorded_at,
        history=history,
    )
    _append_canonical_jsonl(
        execution_dir / "execution-kernel-history.jsonl", event
    )
    return event


def _canonical_jsonl_payload(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _validate_kernel_transition(
    value: object,
    *,
    kind: str,
    authority_plane: str,
    identity_validator: Callable[[object], Mapping[str, object]],
) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != KERNEL_TRANSITION_FIELDS:
        raise ConfigurationError("kernel transition PREPARED schema is ambiguous")
    material = dict(value)
    record_id = material.pop("record_id", None)
    successor = identity_validator(value.get("successor_identity"))
    event = value.get("history_event")
    if not isinstance(event, Mapping):
        raise ConfigurationError("kernel transition history event is missing")
    payload = _canonical_jsonl_payload(event)
    transition_material = {
        "kind": kind,
        "authority_plane": authority_plane,
        "predecessor_record_id": value.get("predecessor_record_id"),
        "predecessor_generation": value.get("predecessor_generation"),
        "previous_event_id": value.get("previous_event_id"),
        "successor_identity_record_id": successor.get("record_id"),
        "history_event_id": event.get("event_id"),
        "actor": value.get("actor"),
        "reason": value.get("reason"),
    }
    for optional_digest in (
        value.get("predecessor_record_id"),
        value.get("predecessor_generation"),
        value.get("previous_event_id"),
    ):
        if optional_digest is not None and AUTHORITY_ID.fullmatch(
            str(optional_digest)
        ) is None:
            raise ConfigurationError("kernel transition predecessor is invalid")
    try:
        parse_time(value.get("prepared_at"))
    except (TypeError, ValueError) as error:
        raise ConfigurationError("kernel transition time is invalid") from error
    if (
        value.get("schema_version") != 1
        or value.get("kind") != kind
        or value.get("authority_plane") != authority_plane
        or value.get("state") != "PREPARED"
        or not isinstance(value.get("actor"), str)
        or not str(value["actor"]).strip()
        or not isinstance(value.get("reason"), str)
        or not str(value["reason"]).strip()
        or value.get("history_payload_digest")
        != "sha256:" + sha256(payload).hexdigest()
        or value.get("history_payload_bytes") != len(payload)
        or value.get("transition_id") != digest_json(transition_material)
        or record_id != digest_json(material)
    ):
        raise ConfigurationError("kernel transition PREPARED receipt is invalid")
    return dict(value)


def _prepare_kernel_transition(
    authority_dir: Path,
    *,
    kind: str,
    authority_plane: str,
    predecessor_record_id: str | None,
    predecessor_generation: str | None,
    previous_event_id: str | None,
    successor_identity: Mapping[str, object],
    history_event: Mapping[str, object],
    actor: str,
    reason: str,
    prepared_at: str,
    identity_validator: Callable[[object], Mapping[str, object]],
) -> Mapping[str, object]:
    payload = _canonical_jsonl_payload(history_event)
    transition_material = {
        "kind": kind,
        "authority_plane": authority_plane,
        "predecessor_record_id": predecessor_record_id,
        "predecessor_generation": predecessor_generation,
        "previous_event_id": previous_event_id,
        "successor_identity_record_id": successor_identity["record_id"],
        "history_event_id": history_event["event_id"],
        "actor": actor,
        "reason": reason,
    }
    transition_id = digest_json(transition_material)
    prepared_material: dict[str, object] = {
        "schema_version": 1,
        "kind": kind,
        "authority_plane": authority_plane,
        "state": "PREPARED",
        "predecessor_record_id": predecessor_record_id,
        "predecessor_generation": predecessor_generation,
        "previous_event_id": previous_event_id,
        "successor_identity": dict(successor_identity),
        "history_event": dict(history_event),
        "history_payload_digest": "sha256:" + sha256(payload).hexdigest(),
        "history_payload_bytes": len(payload),
        "actor": actor,
        "reason": reason,
        "prepared_at": prepared_at,
        "transition_id": transition_id,
    }
    prepared = {
        **prepared_material,
        "record_id": digest_json(prepared_material),
    }
    transitions = authority_dir / KERNEL_TRANSITION_DIRECTORY
    transitions.mkdir(parents=True, exist_ok=True)
    _reject_link_components(
        transitions, label="kernel transition authority directory"
    )
    if not transitions.is_dir():
        raise ConfigurationError(
            "kernel transition authority path is not a directory"
        )
    prepared_path = transitions / (_compact_authority_path_id(transition_id) + ".p")
    pointer_path = authority_dir / KERNEL_TRANSITION_POINTER
    # The pointer is the exclusive contender CAS.  Publishing it first means a
    # crash cannot leave an undiscoverable immutable intent and let a retry mint
    # a second timestamp/event for the same predecessor.  The immutable twin is
    # installed immediately after and is also repaired by the finisher.
    exclusive_write_json_or_identical(pointer_path, prepared)
    exclusive_write_json_or_identical(prepared_path, prepared)
    installed = _validate_kernel_transition(
        read_strict_canonical_json(
            pointer_path, label="kernel transition PREPARED pointer"
        ),
        kind=kind,
        authority_plane=authority_plane,
        identity_validator=identity_validator,
    )
    if installed != prepared:
        raise ConfigurationError("another kernel transition owns this predecessor")
    return prepared


def _read_kernel_transition(
    authority_dir: Path,
    *,
    kind: str,
    authority_plane: str,
    identity_validator: Callable[[object], Mapping[str, object]],
) -> Mapping[str, object] | None:
    pointer_path = authority_dir / KERNEL_TRANSITION_POINTER
    if not pointer_path.exists() and not _is_link_like(pointer_path):
        return None
    return _validate_kernel_transition(
        read_strict_canonical_json(
            pointer_path, label="kernel transition PREPARED pointer"
        ),
        kind=kind,
        authority_plane=authority_plane,
        identity_validator=identity_validator,
    )


def _validate_execution_kernel_transition(value: object) -> Mapping[str, object]:
    prepared = _validate_kernel_transition(
        value,
        kind=EXECUTION_KERNEL_TRANSITION_KIND,
        authority_plane="EXECUTION",
        identity_validator=_validate_execution_identity_document,
    )
    event = prepared["history_event"]
    assert isinstance(event, Mapping)
    material = dict(event)
    event_id = material.pop("event_id", None)
    if (
        set(event) != EXECUTION_KERNEL_HISTORY_FIELDS
        or event.get("schema_version") != 1
        or event.get("kind") != EXECUTION_KERNEL_HISTORY_KIND
        or event.get("state") != "INSTALLED"
        or event.get("identity") != prepared.get("successor_identity")
        or event.get("actor") != prepared.get("actor")
        or event.get("reason") != prepared.get("reason")
        or event.get("recorded_at") != prepared.get("prepared_at")
        or event.get("previous_identity_record_id")
        != prepared.get("predecessor_record_id")
        or prepared.get("predecessor_generation") is not None
        or event.get("previous_event_id") != prepared.get("previous_event_id")
        or event_id != digest_json(material)
    ):
        raise ConfigurationError("execution-kernel transition event is invalid")
    return prepared


def _ensure_kernel_transition_immutable(
    authority_dir: Path, prepared: Mapping[str, object]
) -> None:
    path = authority_dir / KERNEL_TRANSITION_DIRECTORY / (
        _compact_authority_path_id(str(prepared["transition_id"])) + ".p"
    )
    exclusive_write_json_or_identical(path, prepared)
    if read_strict_canonical_json(
        path, label="immutable kernel transition PREPARED receipt"
    ) != prepared:
        raise ConfigurationError("immutable kernel transition receipt changed")


def _prepare_execution_kernel_transition(
    execution_dir: Path,
    successor: Mapping[str, object],
    *,
    predecessor: Mapping[str, object] | None,
    history: Sequence[Mapping[str, object]],
    actor: str,
    reason: str,
    recorded_at: str,
) -> Mapping[str, object]:
    event = _execution_kernel_generation_event(
        successor,
        actor=actor,
        reason=reason,
        recorded_at=recorded_at,
        history=history,
    )
    prepared = _prepare_kernel_transition(
        execution_dir,
        kind=EXECUTION_KERNEL_TRANSITION_KIND,
        authority_plane="EXECUTION",
        predecessor_record_id=(
            predecessor.get("record_id") if predecessor is not None else None
        ),
        predecessor_generation=None,
        previous_event_id=history[-1].get("event_id") if history else None,
        successor_identity=successor,
        history_event=event,
        actor=actor,
        reason=reason,
        prepared_at=recorded_at,
        identity_validator=_validate_execution_identity_document,
    )
    return _validate_execution_kernel_transition(prepared)


def _finish_execution_kernel_transition(
    execution_dir: Path,
    identity_path: Path,
    prepared: Mapping[str, object],
) -> Mapping[str, object]:
    prepared = _validate_execution_kernel_transition(prepared)
    _ensure_kernel_transition_immutable(execution_dir, prepared)
    _repair_or_append_prepared_kernel_event(
        execution_dir / "execution-kernel-history.jsonl",
        prepared,
        validate_prefix=lambda raw: _execution_kernel_history(
            execution_dir, raw_override=raw
        ),
    )
    successor = _validate_execution_identity_document(
        prepared["successor_identity"]
    )
    atomic_write_json(identity_path, successor)
    installed = _validate_execution_identity_document(
        read_strict_canonical_json(
            identity_path,
            label="execution-kernel successor identity",
            expected_fields=EXECUTION_IDENTITY_FIELDS,
        )
    )
    if installed != successor:
        raise ConfigurationError("execution-kernel successor projection changed")
    _complete_kernel_transition(execution_dir, prepared)
    return installed


def _repair_or_append_prepared_kernel_event(
    history_path: Path,
    prepared: Mapping[str, object],
    *,
    validate_prefix: Callable[[bytes], Sequence[Mapping[str, object]]],
) -> tuple[Mapping[str, object], ...]:
    """Install exactly the PREPARED event, recovering only its exact torn bytes."""

    event = prepared["history_event"]
    if not isinstance(event, Mapping):
        raise ConfigurationError("kernel transition has no history event")
    candidate = _canonical_jsonl_payload(event)
    recovery_dir = history_path.parent / KERNEL_TRANSITION_RECOVERY_DIRECTORY
    if recovery_dir.exists() or _is_link_like(recovery_dir):
        _reject_link_components(
            recovery_dir, label="kernel transition recovery directory"
        )
        if not recovery_dir.is_dir():
            raise ConfigurationError(
                "kernel transition recovery path is not a directory"
            )
        for receipt_path in sorted(recovery_dir.glob("*.r")):
            receipt = read_strict_canonical_json(
                receipt_path, label="kernel transition torn-tail receipt"
            )
            fields = {
                "schema_version",
                "kind",
                "transition_id",
                "prepared_record_id",
                "history_path",
                "prefix_digest",
                "tail_digest",
                "tail_bytes",
                "archive_path",
                "record_id",
            }
            receipt_material = (
                dict(receipt) if isinstance(receipt, Mapping) else {}
            )
            receipt_record_id = receipt_material.pop("record_id", None)
            tail_digest = receipt.get("tail_digest") if isinstance(receipt, Mapping) else None
            expected_archive = (
                KERNEL_TRANSITION_RECOVERY_DIRECTORY
                + "/"
                + _compact_authority_path_id(str(tail_digest))
                + ".b"
            )
            expected_receipt_id = digest_json(
                {
                    "kind": "hive-mind-kernel-transition-tail-evidence-v1",
                    "transition_id": receipt.get("transition_id"),
                    "tail_digest": tail_digest,
                }
            )
            if (
                not isinstance(receipt, Mapping)
                or set(receipt) != fields
                or receipt.get("schema_version") != 1
                or receipt.get("kind")
                != "hive-mind-kernel-transition-torn-tail-recovery-v1"
                or AUTHORITY_ID.fullmatch(str(receipt.get("transition_id"))) is None
                or AUTHORITY_ID.fullmatch(
                    str(receipt.get("prepared_record_id"))
                )
                is None
                or receipt.get("history_path") != history_path.name
                or AUTHORITY_ID.fullmatch(str(receipt.get("prefix_digest"))) is None
                or AUTHORITY_ID.fullmatch(str(tail_digest)) is None
                or type(receipt.get("tail_bytes")) is not int
                or int(receipt["tail_bytes"]) < 1
                or receipt.get("archive_path") != expected_archive
                or receipt_record_id != digest_json(receipt_material)
                or receipt_path.name
                != _compact_authority_path_id(expected_receipt_id) + ".r"
            ):
                raise ConfigurationError(
                    "kernel transition torn-tail receipt is invalid"
                )
            archive_path = history_path.parent / expected_archive
            archived = _read_regular_authority_bytes(
                archive_path, label="kernel transition torn-tail evidence"
            )
            if (
                "sha256:" + sha256(archived).hexdigest() != tail_digest
                or len(archived) != receipt["tail_bytes"]
            ):
                raise ConfigurationError(
                    "kernel transition torn-tail evidence changed"
                )
            same_transition = receipt.get("transition_id") == prepared.get(
                "transition_id"
            )
            if same_transition and (
                receipt.get("prepared_record_id") != prepared.get("record_id")
                or not candidate[:-1].startswith(archived)
            ):
                raise ConfigurationError(
                    "kernel transition torn-tail evidence conflicts with PREPARED bytes"
                )
    raw = (
        _read_regular_authority_bytes(history_path, label="kernel generation history")
        if history_path.exists() or _is_link_like(history_path)
        else b""
    )
    prefix = raw
    tail = b""
    if raw and not raw.endswith(b"\n"):
        split = raw.rfind(b"\n") + 1
        prefix, tail = raw[:split], raw[split:]
    prefix_records = tuple(validate_prefix(prefix))
    previous_event_id = (
        prefix_records[-1].get("event_id") if prefix_records else None
    )
    expected_previous = prepared.get("previous_event_id")
    if previous_event_id != expected_previous:
        # A complete exact candidate is an idempotent append receipt.
        if (
            not tail
            and prefix_records
            and prefix_records[-1].get("event_id") == event.get("event_id")
        ):
            return prefix_records
        raise ConfigurationError(
            "kernel transition history head differs from its PREPARED predecessor"
        )
    # Authenticate the complete prospective ledger before touching the torn
    # bytes.  This runs the full state-machine reducer, including retired-kernel
    # replay and legacy-evidence checks, so a self-sealed but semantically
    # impossible PREPARED pointer cannot corrupt a valid prefix.
    candidate_records = tuple(validate_prefix(prefix + candidate))
    if (
        len(candidate_records) != len(prefix_records) + 1
        or candidate_records[-1].get("event_id") != event.get("event_id")
    ):
        raise ConfigurationError(
            "kernel transition candidate does not extend the authenticated history"
        )
    if tail:
        candidate_without_newline = candidate[:-1]
        if not candidate_without_newline.startswith(tail):
            raise ConfigurationError(
                "kernel history torn bytes do not belong to the PREPARED event"
            )
        tail_digest = "sha256:" + sha256(tail).hexdigest()
        archive_path = recovery_dir / (
            _compact_authority_path_id(tail_digest) + ".b"
        )
        exclusive_write_bytes_or_identical(archive_path, tail)
        receipt_material: dict[str, object] = {
            "schema_version": 1,
            "kind": "hive-mind-kernel-transition-torn-tail-recovery-v1",
            "transition_id": prepared["transition_id"],
            "prepared_record_id": prepared["record_id"],
            "history_path": history_path.name,
            "prefix_digest": "sha256:" + sha256(prefix).hexdigest(),
            "tail_digest": tail_digest,
            "tail_bytes": len(tail),
            "archive_path": str(archive_path.relative_to(history_path.parent)).replace(
                "\\", "/"
            ),
        }
        receipt = {
            **receipt_material,
            "record_id": digest_json(receipt_material),
        }
        recovery_receipt_id = digest_json(
            {
                "kind": "hive-mind-kernel-transition-tail-evidence-v1",
                "transition_id": prepared["transition_id"],
                "tail_digest": tail_digest,
            }
        )
        exclusive_write_json_or_identical(
            recovery_dir / (_compact_authority_path_id(recovery_receipt_id) + ".r"),
            receipt,
        )
        _truncate_authenticated_authority_file(
            history_path, expected=raw, prefix=prefix
        )
    _append_canonical_jsonl(history_path, event)
    installed = tuple(validate_prefix(_read_regular_authority_bytes(
        history_path, label="kernel generation history"
    )))
    if not installed or installed[-1].get("event_id") != event.get("event_id"):
        raise ConfigurationError("kernel transition history append was not durable")
    return installed


def _complete_kernel_transition(
    authority_dir: Path,
    prepared: Mapping[str, object],
) -> Mapping[str, object]:
    complete_material: dict[str, object] = {
        "schema_version": 1,
        "kind": KERNEL_TRANSITION_COMPLETE_KIND,
        "authority_plane": prepared["authority_plane"],
        "transition_id": prepared["transition_id"],
        "prepared_record_id": prepared["record_id"],
        "successor_identity_record_id": prepared["successor_identity"]["record_id"],
        "history_event_id": prepared["history_event"]["event_id"],
        "completed_at": prepared["prepared_at"],
    }
    complete = {**complete_material, "record_id": digest_json(complete_material)}
    complete_path = authority_dir / KERNEL_TRANSITION_DIRECTORY / (
        _compact_authority_path_id(str(prepared["transition_id"])) + ".c"
    )
    exclusive_write_json_or_identical(complete_path, complete)
    pointer_path = authority_dir / KERNEL_TRANSITION_POINTER
    installed_pointer = read_strict_canonical_json(
        pointer_path, label="kernel transition PREPARED pointer"
    )
    if installed_pointer != prepared:
        raise ConfigurationError("kernel transition pointer changed before completion")
    pointer_path.unlink()
    _fsync_parent_directory(pointer_path.parent)
    return complete


def execution_namespace_dir(
    coordination_dir: str | Path,
    execution_id: str,
) -> Path:
    if AUTHORITY_ID.fullmatch(execution_id) is None:
        raise ConfigurationError("execution id must be a SHA-256 digest")
    directory = _reject_link_components(
        coordination_dir, label="repository runtime root"
    ).resolve()
    return directory / "executions" / _compact_authority_path_id(execution_id)


def require_execution_namespace(
    coordination_dir: str | Path,
    expected: Mapping[str, object],
) -> Path:
    """Resolve an already initialized namespace; reads never create it."""

    execution_id = expected.get("execution_id")
    if not isinstance(execution_id, str):
        raise ConfigurationError("expected execution identity has no execution id")
    directory = execution_namespace_dir(coordination_dir, execution_id)
    identity_path = directory / "execution-identity.json"
    if not identity_path.is_file() or _is_link_like(identity_path):
        raise ConfigurationError(
            "execution namespace is absent; run explicit runtime namespace initialization"
        )
    try:
        raw = identity_path.read_bytes()
        decoded = raw.decode("utf-8")
        installed = json.loads(
            decoded,
            object_pairs_hook=_strict_json_pairs,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ConfigurationError("execution namespace identity is malformed") from error
    expected_fields = {
        "schema_version",
        "kind",
        "execution_id",
        "namespace",
        "repository",
        "repository_transport_digest",
        "canonical_remote_fetch",
        "canonical_remote_push",
        "target_branch",
        "plan_fingerprint",
        "kernel_bundle_digest",
        "interpreter_policy_digest",
        "record_id",
    }
    if not isinstance(installed, Mapping) or set(installed) != expected_fields:
        raise ConfigurationError("execution namespace identity schema is ambiguous")
    canonical = (
        json.dumps(
            installed,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    if raw != canonical:
        raise ConfigurationError("execution namespace identity is noncanonical")
    material = dict(installed)
    record_id = material.pop("record_id", None)
    if (
        installed.get("schema_version") != 1
        or installed.get("kind") != EXECUTION_IDENTITY_KIND
        or record_id != digest_json(material)
    ):
        raise ConfigurationError("execution namespace identity digest is invalid")
    _validate_execution_identity_document(installed)
    transition_path = directory / KERNEL_TRANSITION_POINTER
    if transition_path.exists() or _is_link_like(transition_path):
        raise ConfigurationError(
            "execution-kernel transition is PREPARED; retry the exact upgrade"
        )
    history = _execution_kernel_history(directory)
    if not history or history[-1].get("identity") != installed:
        raise ConfigurationError(
            "execution namespace identity has no exact append-only kernel generation"
        )
    if installed != expected:
        raise ConfigurationError(
            "execution namespace name is already bound to another target or plan"
        )
    for lock_name in EXECUTION_LOCKS:
        path = directory / "locks" / lock_name
        if not path.is_file() or _is_link_like(path):
            raise ConfigurationError(
                f"execution namespace lock is unavailable: {lock_name}"
            )
    return directory


def require_execution_authority_dir(
    repo_root: str | Path,
    execution_dir: str | Path,
    *,
    execution_id: str,
    execution_namespace: str | None = None,
) -> Path:
    """Authenticate an explicit execution root without deriving authority from a path.

    This lower-level verifier is used by host/orchestration modules that receive an
    already authenticated contract.  It never creates a namespace and refuses a
    directory selected merely through ``state_dir``.
    """

    if AUTHORITY_ID.fullmatch(execution_id) is None:
        raise ConfigurationError("execution authority id is invalid")
    if execution_namespace is not None and EXECUTION_NAMESPACE.fullmatch(
        execution_namespace
    ) is None:
        raise ConfigurationError("execution authority namespace is invalid")
    coordination_dir = resolve_repository_state_dir(repo_root)
    expected_dir = execution_namespace_dir(coordination_dir, execution_id).resolve()
    supplied = _reject_link_components(
        execution_dir, label="execution authority directory"
    ).resolve()
    if supplied != expected_dir:
        raise ConfigurationError(
            "execution authority directory does not match the repository namespace key"
        )
    identity_path = supplied / "execution-identity.json"
    if not identity_path.is_file() or _is_link_like(identity_path):
        raise ConfigurationError("execution authority is not explicitly initialized")
    raw = identity_path.read_bytes()
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_json_pairs,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ConfigurationError("execution authority identity is malformed") from error
    if not isinstance(value, Mapping):
        raise ConfigurationError("execution authority identity must be an object")
    material = dict(value)
    record_id = material.pop("record_id", None)
    if (
        set(value)
        != {
            "schema_version",
            "kind",
            "execution_id",
            "namespace",
            "repository",
            "repository_transport_digest",
            "canonical_remote_fetch",
            "canonical_remote_push",
            "target_branch",
            "plan_fingerprint",
            "kernel_bundle_digest",
            "interpreter_policy_digest",
            "record_id",
        }
        or value.get("schema_version") != 1
        or value.get("kind") != EXECUTION_IDENTITY_KIND
        or value.get("execution_id") != execution_id
        or (
            execution_namespace is not None
            and value.get("namespace") != execution_namespace
        )
        or record_id != digest_json(material)
        or raw
        != (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    ):
        raise ConfigurationError("execution authority identity is invalid")
    _validate_execution_identity_document(value)
    transition_path = supplied / KERNEL_TRANSITION_POINTER
    if transition_path.exists() or _is_link_like(transition_path):
        raise ConfigurationError(
            "execution-kernel transition is PREPARED; ordinary writers are fenced"
        )
    history = _execution_kernel_history(supplied)
    if not history or history[-1].get("identity") != value:
        raise ConfigurationError(
            "execution authority identity differs from its kernel history"
        )
    repository_identity = runtime_repository_identity(repo_root)
    if repository_identity is None or any(
        value.get(field) != repository_identity.get(expected_field)
        for field, expected_field in (
            ("repository", "repository"),
            ("repository_transport_digest", "transport_digest"),
            ("canonical_remote_fetch", "canonical_remote_fetch"),
            ("canonical_remote_push", "canonical_remote_push"),
        )
    ):
        raise ConfigurationError(
            "execution authority Git transport does not match the current repository"
        )
    current_kernel = runtime_kernel_identity(repo_root)
    if (
        value.get("kernel_bundle_digest") != current_kernel.get("bundle_digest")
        or value.get("interpreter_policy_digest")
        != current_kernel.get("interpreter_policy_digest")
    ):
        raise ConfigurationError(
            "execution authority kernel bundle or interpreter policy changed; "
            "an explicit zero-activity execution upgrade is required"
        )
    return supplied


def assert_execution_authority_open(execution_dir: str | Path) -> None:
    """Fail closed when an immutable PLAN_QUIESCENT fence exists.

    Callers must hold the execution dispatcher lock before this check and keep
    it through their local ledger mutation.  The terminal sealer uses the same
    dispatcher lock, making the absence check and append one ordered operation.
    """

    directory = Path(os.path.abspath(os.fspath(execution_dir))).absolute()
    dispatcher_lock = directory / "locks" / "dispatcher-admission.lock"
    if not runtime_file_lock_is_held(dispatcher_lock):
        raise ConfigurationError(
            "execution mutation requires caller-held dispatcher authority"
        )
    fence = directory / "plan-terminal-fence.json"
    if fence.exists() or _is_link_like(fence):
        raise ConfigurationError(
            "execution authority is terminal; new mutation is prohibited"
        )


def initialize_execution_namespace(
    coordination_dir: str | Path,
    expected: Mapping[str, object],
    *,
    actor: str = "execution-namespace-initialize",
    initialized_at: str | None = None,
) -> Path:
    """Explicitly publish one execution identity and its writer generation.

    The history append precedes the replaceable current projection.  A crash in
    that interval is recovered by adopting the one exact pending genesis event;
    ordinary readers refuse the incomplete pair and never lazily manufacture it.
    """

    identity = _validate_execution_identity_document(expected)
    if not isinstance(actor, str) or not actor.strip():
        raise ConfigurationError("execution namespace initialization actor is required")
    recorded_at = initialized_at or format_time(utc_now())
    try:
        parse_time(recorded_at)
    except (TypeError, ValueError) as error:
        raise ConfigurationError(
            "execution namespace initialization time is invalid"
        ) from error

    root = _reject_link_components(
        coordination_dir, label="repository runtime root"
    ).resolve()
    arbiter_lock_path = root / "arbiter" / "locks" / "arbiter-authority.lock"
    if not runtime_file_lock_is_held(arbiter_lock_path):
        raise ConfigurationError(
            "execution namespace initialization requires global arbiter authority"
        )
    execution_id = identity.get("execution_id")
    if not isinstance(execution_id, str):
        raise ConfigurationError("execution namespace identity is malformed")
    directory = execution_namespace_dir(root, execution_id)
    identity_path = directory / "execution-identity.json"
    # Materialize every declared lock before publishing authority.  They are
    # acquired only one at a time under the outer arbiter lock, so their tuple
    # ranks cannot invert one another during explicit initialization.
    for lock_name in EXECUTION_LOCKS:
        with runtime_file_lock(directory / "locks" / lock_name):
            pass
    with runtime_file_lock(directory / "locks" / "dispatcher-admission.lock"):
        installed: Mapping[str, object] | None = None
        if identity_path.exists() or _is_link_like(identity_path):
            installed = read_strict_canonical_json(
                identity_path,
                label="execution namespace identity",
                expected_fields=EXECUTION_IDENTITY_FIELDS,
            )
            installed = _validate_execution_identity_document(installed)
            if installed != identity:
                raise ConfigurationError(
                    "execution namespace name is already bound to another target or plan"
                )
        pending_path = directory / KERNEL_TRANSITION_POINTER
        pending: Mapping[str, object] | None = None
        if pending_path.exists() or _is_link_like(pending_path):
            pending = _validate_execution_kernel_transition(
                read_strict_canonical_json(
                    pending_path,
                    label="execution namespace pending kernel transition",
                )
            )
            if (
                pending.get("predecessor_record_id") is not None
                or pending.get("successor_identity") != identity
                or pending.get("actor") != actor.strip()
                or pending.get("reason")
                != "initial execution-kernel writer generation"
            ):
                raise ConfigurationError(
                    "execution namespace pending initialization differs from this retry"
                )
            installed = _finish_execution_kernel_transition(
                directory, identity_path, pending
            )
        history = _execution_kernel_history(directory)
        if history:
            # An installed namespace may legitimately have any number of
            # append-only kernel generations.  Only an absent current
            # projection is the genesis crash boundary, in which case exactly
            # one history row may be adopted.
            if history[-1].get("identity") != identity or (
                installed is None and len(history) != 1
            ):
                raise ConfigurationError(
                    "execution namespace kernel history conflicts with initialization"
                )
        else:
            if installed is not None:
                raise ConfigurationError(
                    "execution namespace identity has no append-only kernel provenance"
                )
            pending = _prepare_execution_kernel_transition(
                directory,
                identity,
                predecessor=None,
                history=history,
                actor=actor.strip(),
                reason="initial execution-kernel writer generation",
                recorded_at=recorded_at,
            )
            installed = _finish_execution_kernel_transition(
                directory, identity_path, pending
            )
        if installed is None:
            atomic_write_json(identity_path, identity)
    return require_execution_namespace(root, identity)


def _validate_publication_authority_cut(
    value: object,
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    """Authenticate the exact publication projection and embedded transaction."""

    if not isinstance(value, Mapping) or set(value) != PUBLICATION_RESOURCE_FIELDS:
        raise ConfigurationError("publication reservation exact schema is invalid")
    resource_material = dict(value)
    resource_record_id = resource_material.pop("record_id", None)
    transaction = value.get("transaction")
    if (
        value.get("schema_version") != 1
        or value.get("kind") != PUBLICATION_RESERVATION_KIND
        or AUTHORITY_ID.fullmatch(str(resource_record_id)) is None
        or resource_record_id != digest_json(resource_material)
        or not isinstance(transaction, Mapping)
        or set(transaction) != PUBLICATION_TRANSACTION_FIELDS
    ):
        raise ConfigurationError("publication reservation seal is invalid")
    transaction_material = dict(transaction)
    transaction_record_id = transaction_material.pop("record_id", None)
    status = transaction.get("status")
    if (
        transaction.get("schema_version") != 1
        or transaction.get("kind") != PUBLICATION_TRANSACTION_KIND
        or status not in PUBLICATION_ACTIVE_STATUSES | PUBLICATION_TERMINAL_STATUSES
        or AUTHORITY_ID.fullmatch(str(transaction_record_id)) is None
        or transaction_record_id != digest_json(transaction_material)
        or any(
            AUTHORITY_ID.fullmatch(str(transaction.get(field))) is None
            for field in (
                "transaction_key",
                "transaction_id",
                "execution_id",
                "release_id",
                "authority_digest",
                "authority_baseline_digest",
                "receipt_heads_digest",
                "transaction_lease_id",
            )
        )
        or not isinstance(transaction.get("execution_namespace"), str)
        or EXECUTION_NAMESPACE.fullmatch(
            str(transaction["execution_namespace"])
        )
        is None
        or type(transaction.get("attempt_epoch")) is not int
        or int(transaction["attempt_epoch"]) < 1
        or not isinstance(transaction.get("repository"), str)
        or not str(transaction["repository"]).strip()
        or not isinstance(transaction.get("target_branch"), str)
        or not str(transaction["target_branch"]).strip()
        or FULL_SHA.fullmatch(str(transaction.get("expected_target_sha"))) is None
        or not isinstance(transaction.get("actor"), str)
        or not str(transaction["actor"]).strip()
        or not isinstance(transaction.get("detail"), str)
    ):
        raise ConfigurationError("publication transaction is invalid")
    for field in ("reserved_at", "updated_at", "lease_expires_at"):
        try:
            parse_time(transaction.get(field))
        except (TypeError, ValueError) as error:
            raise ConfigurationError(
                "publication transaction time is invalid"
            ) from error
    if status in PUBLICATION_TERMINAL_STATUSES:
        try:
            parse_time(transaction.get("completed_at"))
        except (TypeError, ValueError) as error:
            raise ConfigurationError(
                "terminal publication transaction lacks completion time"
            ) from error
    elif transaction.get("completed_at") is not None:
        raise ConfigurationError(
            "active publication transaction claims terminal completion"
        )
    expected_resource = {
        "status": transaction["status"],
        "transaction_id": transaction["transaction_id"],
        "execution_id": transaction["execution_id"],
        "release_id": transaction["release_id"],
        "repository": transaction["repository"],
        "target_branch": transaction["target_branch"],
        "expected_target_sha": transaction["expected_target_sha"],
        "expires_at": transaction["lease_expires_at"],
        "outcome": transaction["outcome"],
    }
    if any(value.get(field) != expected for field, expected in expected_resource.items()):
        raise ConfigurationError(
            "publication reservation differs from its embedded transaction"
        )
    return dict(value), dict(transaction)


def _execution_kernel_upgrade_activity_unlocked(
    repo_root: Path,
    coordination_dir: Path,
    execution_dir: Path,
    identity: Mapping[str, object],
    *,
    host_runtime_dir: Path,
) -> tuple[str, ...]:
    """Return exact zero-activity blockers while all authority locks are held."""

    from orchestration import (
        _active_binding_events_unlocked,
        _validate_binding_event_schema,
        _validate_binding_replay,
    )
    from sidecar_execution import (
        ACTIVE_SIDECAR_STATES,
        _validate_sidecar_replay,
    )
    from sidecar_execution import (
        _validate_event_schema as _validate_sidecar_event_schema,
    )

    blockers: list[str] = []
    execution_id = str(identity["execution_id"])
    global_active = tuple(
        item
        for item in active_global_host_reservations(host_runtime_dir)
        if item.get("repository") == identity.get("repository")
        and item.get("execution_id") == execution_id
    )
    if global_active:
        blockers.append("GLOBAL_HOST_RESERVATION")
    scheduler_events = _host_scheduler_events_unlocked(host_runtime_dir)
    if scheduler_events:
        scheduler = _host_scheduler_projection_unlocked(
            host_runtime_dir,
            host_id=str(scheduler_events[-1]["host_id"]),
        )
        if any(
            demand.get("execution_id") == execution_id
            and scheduler["remaining_candidates"].get(demand_id)
            for demand_id, demand in scheduler["demands"].items()
        ):
            blockers.append("HOST_SCHEDULER_DEMAND")
        if any(
            grant.get("execution_id") == execution_id
            for grant in scheduler["outstanding_grants"].values()
        ):
            blockers.append("HOST_SCHEDULER_GRANT")

    binding_records = strict_jsonl_records(
        execution_dir / "task-bindings.jsonl",
        label="execution-kernel upgrade task binding ledger",
    )
    for index, event in enumerate(binding_records, 1):
        _validate_binding_event_schema(event, index)
    _validate_binding_replay(binding_records)
    if _active_binding_events_unlocked(binding_records):
        blockers.append("ACTIVE_LAUNCH_BINDING")
    binding_instruction_ids = {
        str(event["launch_instruction_id"]) for event in binding_records
    }

    dispatcher_release_path = execution_dir / "dispatcher-release.json"
    if dispatcher_release_path.exists() or _is_link_like(dispatcher_release_path):
        release = read_strict_canonical_json(
            dispatcher_release_path,
            label="execution-kernel upgrade dispatcher release",
            expected_fields=DISPATCH_RELEASE_FIELDS,
        )
        release_material = dict(release)
        release_id = release_material.pop("release_id", None)
        if (
            release.get("schema_version") != 1
            or release.get("kind") != "hive-mind-autopilot-dispatch-release-v1"
            or release.get("execution_id") != execution_id
            or release.get("execution_namespace") != identity.get("namespace")
            or release.get("repository") != identity.get("repository")
            or release.get("target_branch") != identity.get("target_branch")
            or release.get("plan_fingerprint") != identity.get("plan_fingerprint")
            or release_id != digest_json(release_material)
        ):
            raise ConfigurationError(
                "execution-kernel upgrade dispatcher release is invalid"
            )
        blockers.append("DISPATCH_RELEASE_AUTHORITY")

    dispatcher_admission_path = execution_dir / "dispatcher-admission.json"
    if dispatcher_admission_path.exists() or _is_link_like(
        dispatcher_admission_path
    ):
        admission = read_strict_canonical_json(
            dispatcher_admission_path,
            label="execution-kernel upgrade dispatcher admission",
        )
        common_fields = {
            "schema_version",
            "kind",
            "status",
            "execution_namespace",
            "execution_id",
            "admission_epoch",
            "release_id",
            "repository",
            "target_branch",
            "target_sha",
            "target_generation",
            "target_watermark_record_id",
            "plan_fingerprint",
            "github_snapshot_digest",
            "reconciliation_digest",
            "snapshot_observation_id",
            "snapshot_observation_epoch",
            "snapshot_observation_record_id",
            "host_id",
            "capacity_generation",
            "capacity_epoch",
            "capacity_record_id",
            "session_cap",
            "generation_id",
            "recorded_at",
        }
        if admission.get("status") == "INVALIDATED":
            common_fields |= {"actor", "reason", "observed_target_sha"}
        admission_material = dict(admission)
        generation_id = admission_material.pop("generation_id", None)
        status = admission.get("status")
        release_id = admission.get("release_id")
        snapshot_digest = admission.get("github_snapshot_digest")
        reconciliation_digest = admission.get("reconciliation_digest")
        capacity_values = (
            admission.get("host_id"),
            admission.get("capacity_generation"),
            admission.get("capacity_epoch"),
            admission.get("capacity_record_id"),
            admission.get("session_cap"),
        )
        observation_values = (
            admission.get("snapshot_observation_id"),
            admission.get("snapshot_observation_epoch"),
            admission.get("snapshot_observation_record_id"),
        )
        semantic_invalid = (
            type(admission.get("admission_epoch")) is not int
            or int(admission.get("admission_epoch", 0)) < 1
            or (
                release_id is not None
                and AUTHORITY_ID.fullmatch(str(release_id)) is None
            )
            or not isinstance(admission.get("repository"), str)
            or not str(admission.get("repository", "")).strip()
            or not isinstance(admission.get("target_branch"), str)
            or not str(admission.get("target_branch", "")).strip()
            or FULL_SHA.fullmatch(str(admission.get("target_sha"))) is None
            or type(admission.get("target_generation")) is not int
            or int(admission.get("target_generation", 0)) < 1
            or AUTHORITY_ID.fullmatch(
                str(admission.get("target_watermark_record_id"))
            )
            is None
            or AUTHORITY_ID.fullmatch(str(admission.get("plan_fingerprint")))
            is None
            or (
                snapshot_digest is not None
                and AUTHORITY_ID.fullmatch(str(snapshot_digest)) is None
            )
            or (
                reconciliation_digest is not None
                and AUTHORITY_ID.fullmatch(str(reconciliation_digest)) is None
            )
            or (
                status == "ACTIVE"
                and (snapshot_digest is None or reconciliation_digest is None)
            )
            or (
                (status == "ACTIVE" or any(item is not None for item in capacity_values))
                and (
                    not isinstance(capacity_values[0], str)
                    or not str(capacity_values[0]).strip()
                    or AUTHORITY_ID.fullmatch(str(capacity_values[1])) is None
                    or type(capacity_values[2]) is not int
                    or int(capacity_values[2]) < 1
                    or AUTHORITY_ID.fullmatch(str(capacity_values[3])) is None
                    or type(capacity_values[4]) is not int
                    or int(capacity_values[4]) < 1
                )
            )
            or (
                (status == "ACTIVE" or any(item is not None for item in observation_values))
                and (
                    AUTHORITY_ID.fullmatch(str(observation_values[0])) is None
                    or type(observation_values[1]) is not int
                    or int(observation_values[1]) < 1
                    or AUTHORITY_ID.fullmatch(str(observation_values[2])) is None
                )
            )
        )
        if status == "INVALIDATED":
            semantic_invalid = semantic_invalid or (
                not isinstance(admission.get("actor"), str)
                or not str(admission.get("actor", "")).strip()
                or not isinstance(admission.get("reason"), str)
                or not str(admission.get("reason", "")).strip()
                or FULL_SHA.fullmatch(
                    str(admission.get("observed_target_sha"))
                )
                is None
                or admission.get("observed_target_sha")
                != admission.get("target_sha")
            )
        try:
            parse_time(admission.get("recorded_at"))
        except (TypeError, ValueError):
            semantic_invalid = True
        if (
            set(admission) != common_fields
            or admission.get("schema_version") != 1
            or admission.get("kind")
            != "hive-mind-shared-dispatch-admission-v1"
            or status not in {"ACTIVE", "INVALIDATED"}
            or admission.get("execution_id") != execution_id
            or admission.get("execution_namespace") != identity.get("namespace")
            or admission.get("repository") != identity.get("repository")
            or admission.get("target_branch") != identity.get("target_branch")
            or admission.get("plan_fingerprint") != identity.get("plan_fingerprint")
            or generation_id != digest_json(admission_material)
            or semantic_invalid
        ):
            raise ConfigurationError(
                "execution-kernel upgrade dispatcher admission is invalid"
            )
        if status == "ACTIVE":
            blockers.append("DISPATCH_ADMISSION_AUTHORITY")

    attended_path = execution_dir / "host" / "attended-threads.json"
    if attended_path.exists() or _is_link_like(attended_path):
        from attended_host import AttendedCodexHost, AttendedHostError

        class _AttendedExecutionPlane:
            pass

        attended_plane = _AttendedExecutionPlane()
        attended_plane.repo_root = repo_root
        attended_plane.state_dir = execution_dir
        attended_plane.coordination_dir = coordination_dir
        attended_plane.execution_dir = execution_dir
        attended_host = AttendedCodexHost(attended_plane)
        try:
            attended, _migrated, _cards = attended_host._ledger_unlocked(
                allow_legacy=False
            )
        except (AttendedHostError, OSError) as error:
            raise ConfigurationError(
                f"execution-kernel upgrade attended authority is invalid: {error}"
            ) from error
        for instruction_id, entry in attended.items():
            if (
                AUTHORITY_ID.fullmatch(str(instruction_id)) is None
                or not isinstance(entry, Mapping)
            ):
                raise ConfigurationError(
                    "execution-kernel upgrade attended registry is invalid"
                )
            if str(instruction_id) not in binding_instruction_ids:
                blockers.append("ATTENDED_HOST_AUTHORITY")
                break

    sidecar_records = strict_jsonl_records(
        execution_dir / "sidecar-bindings.jsonl",
        label="execution-kernel upgrade sidecar ledger",
    )
    for index, event in enumerate(sidecar_records, 1):
        _validate_sidecar_event_schema(event, index)
    _validate_sidecar_replay(sidecar_records)
    latest_sidecars: dict[str, Mapping[str, object]] = {}
    for event in sidecar_records:
        latest_sidecars[str(event["sidecar_id"])] = event
    if any(
        event.get("state") in ACTIVE_SIDECAR_STATES
        for event in latest_sidecars.values()
    ):
        blockers.append("ACTIVE_SIDECAR_BINDING")

    if execution_host_effect_obligations(execution_dir):
        blockers.append("HOST_EFFECT_RECOVERY_REQUIRED")

    claims_dir = coordination_dir / "arbiter" / "claims"
    if claims_dir.exists() or _is_link_like(claims_dir):
        _reject_link_components(claims_dir, label="execution-kernel upgrade claims")
        if not claims_dir.is_dir():
            raise ConfigurationError("claim authority directory is not a directory")
        for path in sorted(claims_dir.iterdir(), key=lambda item: item.name):
            if not path.is_file() or path.suffix != ".json":
                raise ConfigurationError(
                    "claim authority directory contains an unclassified entry"
                )
            claim, _expires, _raw = read_claim_authority_file(path)
            if claim.get("execution_id") == execution_id:
                blockers.append("CLAIM_AUTHORITY")
                break

    validation_key = digest_json(
        {
            "kind": "hive-mind-validation-resource-key-v1",
            "repository": identity["repository"],
            "repository_transport_digest": identity[
                "repository_transport_digest"
            ],
            "target_branch": identity["target_branch"],
        }
    )
    validation_path = (
        coordination_dir
        / "arbiter"
        / "validation-leases"
        / (validation_key.removeprefix("sha256:") + ".json")
    )
    if validation_path.exists() or _is_link_like(validation_path):
        # A keyed lease may protect a peer execution on the same target.  It is
        # still activity for this zero-activity writer transition and must be
        # terminalized by its normal recovery path first.
        read_strict_canonical_json(
            validation_path, label="execution-kernel upgrade validation lease"
        )
        blockers.append("VALIDATION_AUTHORITY")

    publication_key = digest_json(
        {
            "kind": "hive-mind-publication-resource-v1",
            "repository": identity["repository"],
            "target_branch": identity["target_branch"],
        }
    )
    publication_path = (
        coordination_dir
        / "arbiter"
        / "publication-reservations"
        / (publication_key.removeprefix("sha256:") + ".json")
    )
    if publication_path.exists() or _is_link_like(publication_path):
        publication = read_strict_canonical_json(
            publication_path,
            label="execution-kernel upgrade publication reservation",
        )
        publication, transaction = _validate_publication_authority_cut(publication)
        if (
            transaction.get("execution_id") == execution_id
            and publication.get("status") in PUBLICATION_ACTIVE_STATUSES
        ):
            blockers.append("PUBLICATION_AUTHORITY")

    terminal_fence = execution_dir / "plan-terminal-fence.json"
    if terminal_fence.exists() or _is_link_like(terminal_fence):
        read_strict_canonical_json(
            terminal_fence, label="execution-kernel upgrade terminal fence"
        )
        blockers.append("PLAN_TERMINAL_FENCE")
    return tuple(sorted(set(blockers)))


def upgrade_execution_namespace_kernel(
    repo_root: str | Path,
    coordination_dir: str | Path,
    *,
    host_runtime_dir: str | Path,
    execution_namespace: str,
    execution_id: str,
    actor: str,
    reason: str,
    expected_identity_record_id: str,
    upgraded_at: str | None = None,
) -> Mapping[str, object]:
    """CAS-install this checkout's execution kernel at a strict zero-activity cut."""

    if EXECUTION_NAMESPACE.fullmatch(execution_namespace) is None:
        raise ConfigurationError("execution-kernel upgrade namespace is invalid")
    if AUTHORITY_ID.fullmatch(execution_id) is None:
        raise ConfigurationError("execution-kernel upgrade id is invalid")
    if AUTHORITY_ID.fullmatch(expected_identity_record_id) is None:
        raise ConfigurationError("execution-kernel upgrade identity CAS is invalid")
    if not isinstance(actor, str) or not actor.strip():
        raise ConfigurationError("execution-kernel upgrade actor is required")
    if not isinstance(reason, str) or not reason.strip():
        raise ConfigurationError("execution-kernel upgrade reason is required")
    recorded_at = upgraded_at or format_time(utc_now())
    try:
        parse_time(recorded_at)
    except (TypeError, ValueError) as error:
        raise ConfigurationError("execution-kernel upgrade time is invalid") from error

    root = _reject_link_components(repo_root, label="repository root").resolve()
    supplied_coordination = _reject_link_components(
        coordination_dir, label="repository runtime root"
    ).resolve()
    canonical_coordination = resolve_repository_state_dir(root)
    if supplied_coordination != canonical_coordination:
        raise ConfigurationError("execution-kernel upgrade selected a peer runtime root")
    ensure_repository_runtime_identity(root, supplied_coordination, create=False)
    host_root = require_host_runtime(host_runtime_dir)
    execution_dir = execution_namespace_dir(supplied_coordination, execution_id)
    identity_path = execution_dir / "execution-identity.json"
    if not identity_path.is_file() or _is_link_like(identity_path):
        raise ConfigurationError("execution namespace is absent")
    required_locks = tuple(execution_dir / "locks" / name for name in EXECUTION_LOCKS)
    if any(not path.is_file() or _is_link_like(path) for path in required_locks):
        raise ConfigurationError("execution namespace lock set is incomplete")

    with runtime_file_lock(host_root / "locks" / "host-authority.lock", timeout_seconds=120.0):
        # Freshly validate the host writer after acquiring its authority.
        _host_runtime_identity_unlocked(host_root)
        with runtime_file_lock(
            supplied_coordination / "arbiter" / "locks" / "arbiter-authority.lock",
            timeout_seconds=120.0,
        ):
            with runtime_file_lock(
                execution_dir / "locks" / "dispatcher-admission.lock",
                timeout_seconds=120.0,
            ):
                current_value = read_strict_canonical_json(
                    identity_path,
                    label="execution-kernel upgrade current identity",
                    expected_fields=EXECUTION_IDENTITY_FIELDS,
                )
                current = _validate_execution_identity_document(current_value)
                if (
                    current.get("execution_id") != execution_id
                    or current.get("namespace") != execution_namespace
                ):
                    raise ConfigurationError(
                        "execution-kernel upgrade identity coordinates changed"
                    )
                requested_kernel = runtime_kernel_identity(root)
                requested_pair = (
                    str(requested_kernel["bundle_digest"]),
                    str(requested_kernel["interpreter_policy_digest"]),
                )
                pending_path = execution_dir / KERNEL_TRANSITION_POINTER
                pending: Mapping[str, object] | None = None
                if pending_path.exists() or _is_link_like(pending_path):
                    pending = _validate_execution_kernel_transition(
                        read_strict_canonical_json(
                            pending_path,
                            label="pending execution-kernel upgrade",
                        )
                    )
                    pending_successor = pending["successor_identity"]
                    assert isinstance(pending_successor, Mapping)
                    if (
                        pending.get("actor") != actor.strip()
                        or pending.get("reason") != reason.strip()
                        or pending.get("predecessor_record_id")
                        != expected_identity_record_id
                        or (
                            str(pending_successor["kernel_bundle_digest"]),
                            str(pending_successor["interpreter_policy_digest"]),
                        )
                        != requested_pair
                        or current.get("record_id")
                        not in {
                            pending.get("predecessor_record_id"),
                            pending_successor.get("record_id"),
                        }
                    ):
                        raise ConfigurationError(
                            "pending execution-kernel upgrade differs from this retry"
                        )
                    _repair_or_append_prepared_kernel_event(
                        execution_dir / "execution-kernel-history.jsonl",
                        pending,
                        validate_prefix=lambda raw: _execution_kernel_history(
                            execution_dir, raw_override=raw
                        ),
                    )
                history = _execution_kernel_history(execution_dir)
                if not history:
                    raise ConfigurationError(
                        "execution-kernel upgrade requires an initialized generation history"
                    )
                latest_identity = dict(history[-1]["identity"])
                history_ahead = latest_identity != current
                if history_ahead:
                    if (
                        history[-1].get("previous_identity_record_id")
                        != current.get("record_id")
                        or len(history) < 2
                        or history[-2].get("identity") != current
                    ):
                        raise ConfigurationError(
                            "execution-kernel history is ambiguously ahead of its projection"
                        )
                elif history[-1].get("identity") != current:
                    raise ConfigurationError(
                        "execution-kernel projection differs from its history"
                    )

                current_pair = (
                    str(current["kernel_bundle_digest"]),
                    str(current["interpreter_policy_digest"]),
                )
                if (
                    current_pair == requested_pair
                    and not history_ahead
                    and pending is None
                ):
                    exact_current_cas = (
                        expected_identity_record_id == current.get("record_id")
                    )
                    completed_retry_cas = (
                        expected_identity_record_id
                        == history[-1].get("previous_identity_record_id")
                        and history[-1].get("identity") == current
                        and history[-1].get("actor") == actor.strip()
                        and history[-1].get("reason") == reason.strip()
                    )
                    if not exact_current_cas and not completed_retry_cas:
                        raise ConfigurationError(
                            "execution-kernel upgrade identity CAS mismatch"
                        )
                    return current

                if pending is not None:
                    successor = dict(pending["successor_identity"])
                    if history[-1].get("event_id") != pending[
                        "history_event"
                    ].get("event_id"):
                        raise ConfigurationError(
                            "pending execution-kernel event is not the history head"
                        )
                elif history_ahead:
                    if (
                        latest_identity.get("kernel_bundle_digest")
                        != requested_kernel.get("bundle_digest")
                        or latest_identity.get("interpreter_policy_digest")
                        != requested_kernel.get("interpreter_policy_digest")
                        or history[-1].get("actor") != actor.strip()
                        or history[-1].get("reason") != reason.strip()
                        or expected_identity_record_id != current.get("record_id")
                    ):
                        raise ConfigurationError(
                            "pending execution-kernel upgrade differs from this retry"
                        )
                    successor = latest_identity
                else:
                    if expected_identity_record_id != current.get("record_id"):
                        raise ConfigurationError(
                            "execution-kernel upgrade identity CAS mismatch"
                        )
                    if any(
                        (
                            event["identity"]["kernel_bundle_digest"],
                            event["identity"]["interpreter_policy_digest"],
                        )
                        == requested_pair
                        for event in history
                    ):
                        raise ConfigurationError(
                            "execution-kernel downgrade or retired-writer replay is prohibited"
                        )
                    successor = execution_namespace_identity(
                        runtime_repository_identity(root) or {},
                        kernel_identity=requested_kernel,
                        namespace=execution_namespace,
                        target_branch=str(current["target_branch"]),
                        plan_fingerprint=str(current["plan_fingerprint"]),
                    )
                    for field in EXECUTION_IDENTITY_FIELDS - {
                        "kernel_bundle_digest",
                        "interpreter_policy_digest",
                        "record_id",
                    }:
                        if successor.get(field) != current.get(field):
                            raise ConfigurationError(
                                "execution-kernel successor mutates execution identity"
                            )

                with runtime_file_lock(
                    execution_dir / "locks" / "task-bindings.lock",
                    timeout_seconds=120.0,
                ):
                    with runtime_file_lock(
                        execution_dir / "locks" / "sidecar-bindings.lock",
                        timeout_seconds=120.0,
                    ):
                        with runtime_file_lock(
                            supplied_coordination
                            / "arbiter"
                            / "locks"
                            / "claim-authority.lock",
                            timeout_seconds=120.0,
                        ):
                            with runtime_file_lock(
                                supplied_coordination
                                / "arbiter"
                                / "locks"
                                / "global-validation-lease.lock",
                                timeout_seconds=120.0,
                            ):
                                with runtime_file_lock(
                                    execution_dir
                                    / "locks"
                                    / "attended-host.lock",
                                    timeout_seconds=120.0,
                                ):
                                    blockers = _execution_kernel_upgrade_activity_unlocked(
                                        root,
                                        supplied_coordination,
                                        execution_dir,
                                        current,
                                        host_runtime_dir=host_root,
                                    )
                                    if blockers:
                                        raise ConfigurationError(
                                            "execution-kernel upgrade requires zero activity: "
                                            + ", ".join(blockers)
                                        )
                                    if pending is not None:
                                        return _finish_execution_kernel_transition(
                                            execution_dir, identity_path, pending
                                        )
                                    if not history_ahead:
                                        pending = _prepare_execution_kernel_transition(
                                            execution_dir,
                                            successor,
                                            predecessor=current,
                                            history=history,
                                            actor=actor.strip(),
                                            reason=reason.strip(),
                                            recorded_at=recorded_at,
                                        )
                                        return _finish_execution_kernel_transition(
                                            execution_dir, identity_path, pending
                                        )
                                    atomic_write_json(identity_path, successor)
                                    return dict(successor)


HOST_CAPACITY_KIND = "hive-mind-host-capacity-v1"
HOST_RESERVATION_EVENT_KIND = "hive-mind-host-reservation-event-v1"
HOST_SCHEDULER_EVENT_KIND = "hive-mind-host-scheduler-event-v1"
HOST_SCHEDULER_EVENT_STATES = frozenset({"DEMAND", "GRANT", "EXPIRY"})
HOST_CAPACITY_HISTORY_KIND = "hive-mind-host-capacity-history-event-v1"
HOST_RUNTIME_IDENTITY_KIND = "hive-mind-host-runtime-identity-v1"
HOST_KERNEL_HISTORY_KIND = "hive-mind-host-kernel-generation-event-v1"
HOST_KERNEL_TRANSITION_KIND = "hive-mind-host-kernel-transition-v1"
HOST_KERNEL_BUNDLE_KIND = "hive-mind-host-kernel-bundle-v1"
HOST_PROVIDER_BINDING_KIND = "hive-mind-host-provider-binding-v1"
HOST_PROVIDER_ATTESTATION_KIND = "hive-mind-host-provider-attestation-v1"
HOST_RUNTIME_IDENTITY_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "machine_user_id",
        "host_kernel_generation",
        "host_kernel_epoch",
        "host_kernel_bundle_digest",
        "interpreter_policy_digest",
        "installed_at",
        "previous_host_kernel_generation",
        "previous_host_kernel_record_id",
        "record_id",
    }
)
HOST_KERNEL_HISTORY_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "state",
        "identity",
        "actor",
        "reason",
        "recorded_at",
        "legacy_predecessor_record_id",
        "legacy_predecessor_path",
        "legacy_predecessor_blob_digest",
        "previous_event_id",
        "event_id",
    }
)
HOST_PROVIDER_ATTESTATION_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "machine_user_id",
        "host_id",
        "provider_identity_source",
        "provider_identity_material",
        "provider_identity_digest",
        "record_id",
    }
)
EXECUTION_ADAPTER_IDENTITY_KIND = "hive-mind-execution-adapter-identity-v1"
EXECUTION_ADAPTER_IDENTITY_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "execution_namespace",
        "execution_id",
        "repository",
        "host_id",
        "provider_generation",
        "provider_epoch",
        "provider_identity_digest",
        "adapter_identity_kind",
        "adapter_identity_record_id",
        "adapter_identity_blob_digest",
        "adapter_identity_source_path",
        "record_id",
    }
)
CODEX_APP_SERVER_IDENTITY_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "execution_namespace",
        "execution_id",
        "host_id",
        "machine_user_id",
        "provider_identity_digest",
        "adapter_module_path",
        "adapter_module_digest",
        "launcher_path",
        "launcher_digest",
        "cli_module_path",
        "cli_module_digest",
        "executable_path",
        "executable_digest",
        "executable_version",
        "schema_bundle_digest",
        "thread_start_schema_digest",
        "turn_start_schema_digest",
        "environment_root_digest",
        "behavior_environment_digest",
        "provider_config_digest",
        "execution_config_digest",
        "account_identity_digest",
        "effective_model",
        "effective_model_provider",
        "transport",
        "initialize_result_digest",
        "created_at",
        "record_id",
    }
)
HOST_PROVIDER_LEGACY_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "machine_user_id",
        "host_id",
        "provider_generation",
        "provider_epoch",
        "provider_identity_source",
        "provider_identity_digest",
        "bound_at",
        "previous_provider_generation",
        "previous_provider_record_id",
        "record_id",
    }
)
HOST_PROVIDER_FIELDS = HOST_PROVIDER_LEGACY_FIELDS | frozenset(
    {
        "host_kernel_generation",
        "provider_attestation_record_id",
        "provider_attestation_path",
        "provider_attestation_blob_digest",
    }
)
HOST_RESERVATION_STATES = frozenset(
    {"RESERVED", "RENEWED", "RELEASED", "EXPIRED_FENCED"}
)
HOST_RESERVATION_ACTIVE_STATES = frozenset({"RESERVED", "RENEWED"})
HOST_RESERVATION_KINDS = frozenset({"PRIMARY", "SIDECAR", "VALIDATION"})
HOST_CAPACITY_LEGACY_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "host_id",
        "provider_generation",
        "provider_epoch",
        "capacity_generation",
        "capacity_epoch",
        "max_total_sessions",
        "validation_slots",
        "issued_at",
        "expires_at",
        "capability_source",
        "capability_digest",
        "declarative",
        "record_id",
    }
)
HOST_CAPACITY_FIELDS = HOST_CAPACITY_LEGACY_FIELDS | frozenset(
    {"host_kernel_generation"}
)
PRE_LAUNCH_ABORT_KIND = "hive-mind-dispatcher-pre-launch-abort-v1"
VALIDATION_TERMINAL_RECEIPT_KIND = (
    "hive-mind-validation-host-reservation-terminal-receipt-v1"
)
VALIDATION_TERMINAL_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "state",
        "execution_namespace",
        "execution_id",
        "repository",
        "reservation_id",
        "local_reservation_id",
        "resource_key",
        "host_id",
        "provider_generation",
        "capacity_generation",
        "validation_resource_key",
        "release_id",
        "transaction_sha",
        "lease_id",
        "terminal_status",
        "terminal_lease",
        "terminal_lease_blob_digest",
        "recorded_at",
        "record_id",
    }
)
VALIDATION_NEVER_ACQUIRED_KIND = "hive-mind-validation-never-acquired-v1"
VALIDATION_NEVER_ACQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "state",
        "execution_namespace",
        "execution_id",
        "repository",
        "reservation_id",
        "local_reservation_id",
        "resource_key",
        "host_id",
        "provider_generation",
        "capacity_generation",
        "validation_resource_key",
        "release_id",
        "transaction_sha",
        "node_id",
        "owner",
        "reason",
        "actor",
        "recorded_at",
        "record_id",
    }
)
DISPATCH_ADMISSION_INTENT_KIND = "hive-mind-dispatcher-admission-intent-v1"
LEGACY_DISPATCH_ADMISSION_INTENT_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "execution_namespace",
        "execution_id",
        "repository",
        "release_admission_id",
        "release_id",
        "admission_epoch",
        "target_sha",
        "target_generation",
        "target_watermark_record_id",
        "plan_fingerprint",
        "snapshot_observation_record_id",
        "host_id",
        "provider_generation",
        "provider_epoch",
        "capacity_generation",
        "capacity_epoch",
        "reservations",
        "release",
        "actor",
        "issued_at",
        "record_id",
    }
)
DISPATCH_ADMISSION_INTENT_FIELDS = frozenset(
    {
        *LEGACY_DISPATCH_ADMISSION_INTENT_FIELDS,
        "host_kernel_generation",
        "execution_adapter_identity_record_id",
        "execution_adapter_identity_path",
        "execution_adapter_identity_blob_digest",
    }
)
DISPATCH_RELEASE_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "actor",
        "execution_namespace",
        "execution_id",
        "repository",
        "target_branch",
        "target_sha",
        "target_generation",
        "target_watermark_record_id",
        "plan_fingerprint",
        "reconciliation_digest",
        "github_snapshot_digest",
        "snapshot_observation_id",
        "snapshot_observation_epoch",
        "snapshot_observation_record_id",
        "host_id",
        "capacity_generation",
        "capacity_epoch",
        "capacity_record_id",
        "capacity_max_total_sessions",
        "capacity_validation_slots",
        "session_cap",
        "admission_epoch",
        "supersedes_release_id",
        "released_wave",
        "directive",
        "action",
        "verdicts",
        "issued_at",
        "receipt_retirement_execution_digest",
        "primary_host_reservations",
        "release_admission_id",
        "release_id",
    }
)
PRE_LAUNCH_ABORT_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "state",
        "execution_namespace",
        "execution_id",
        "repository",
        "release_id",
        "release_admission_id",
        "admission_epoch",
        "intent_record_id",
        "reservation_id",
        "local_reservation_id",
        "resource_key",
        "node_id",
        "host_id",
        "provider_generation",
        "capacity_generation",
        "active_write_launch_reservation_ids",
        "active_host_reservation_ids",
        "host_effect_obligation_ids",
        "empty_activity_digest",
        "reason",
        "actor",
        "recorded_at",
        "record_id",
    }
)


def _host_runtime_base_dir() -> Path:
    if os.name == "nt":
        # Environment variables are caller-controlled and cannot select a
        # machine-user kernel. Ask Windows for the account's LocalAppData known
        # folder, then reject a contradictory environment instead of creating a
        # peer locator there.
        try:
            import ctypes
            import uuid

            class _GUID(ctypes.Structure):
                _fields_ = (
                    ("Data1", ctypes.c_uint32),
                    ("Data2", ctypes.c_uint16),
                    ("Data3", ctypes.c_uint16),
                    ("Data4", ctypes.c_ubyte * 8),
                )

            guid_bytes = uuid.UUID(
                "f1b32785-6fba-4fcf-9d55-7b8e7f157091"
            ).bytes_le
            folder_id = _GUID.from_buffer_copy(guid_bytes)
            selected = ctypes.c_wchar_p()
            result = ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(folder_id), 0, None, ctypes.byref(selected)
            )
            if result != 0 or not selected.value:
                raise OSError(f"SHGetKnownFolderPath failed with HRESULT {result}")
            try:
                canonical = Path(selected.value)
            finally:
                ctypes.windll.ole32.CoTaskMemFree(selected)
        except Exception as error:
            raise ConfigurationError(
                "cannot resolve the canonical Windows account authority root"
            ) from error
        configured = os.environ.get("LOCALAPPDATA", "").strip()
        if configured and Path(configured).resolve() != canonical.resolve():
            raise ConfigurationError(
                "LOCALAPPDATA disagrees with the canonical Windows account location"
            )
        return _reject_link_components(
            canonical, label="host runtime OS-user base"
        ).resolve() / "HiveMindOS"
    try:
        import pwd

        canonical_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    except Exception as error:
        raise ConfigurationError(
            "cannot resolve the canonical POSIX account authority root"
        ) from error
    configured_home = os.environ.get("HOME", "").strip()
    if configured_home and Path(configured_home).resolve() != canonical_home.resolve():
        raise ConfigurationError(
            "HOME disagrees with the canonical operating-system account"
        )
    canonical_state = canonical_home / ".local" / "state"
    configured_state = os.environ.get("XDG_STATE_HOME", "").strip()
    if configured_state and Path(configured_state).resolve() != canonical_state.resolve():
        raise ConfigurationError(
            "XDG_STATE_HOME cannot select a peer host authority root"
        )
    return _reject_link_components(
        canonical_state, label="host runtime OS-user base"
    ).resolve() / "hive-mind-os"


def _machine_user_identity(*, create: bool = False) -> str:
    """Return a sealed installation identity, never a mutable display name alone."""

    base = _reject_link_components(
        _host_runtime_base_dir(), label="host runtime authority base"
    )
    path = base / "machine-user-identity.json"
    if not path.is_file():
        if not create:
            raise ConfigurationError("sealed machine-user identity is absent")
        base.mkdir(parents=True, exist_ok=True)
        material: dict[str, object] = {
            "schema_version": 1,
            "kind": "hive-mind-machine-user-installation-v1",
            "installation_nonce": secrets.token_hex(32),
            "machine_hint": platform.node().casefold(),
            "user_hint": getpass.getuser().casefold(),
        }
        exclusive_write_json_or_identical(
            path, {**material, "record_id": digest_json(material)}
        )
    try:
        raw = _read_regular_authority_bytes(path, label="sealed machine-user identity")
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_json_pairs,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ConfigurationError("sealed machine-user identity is malformed") from error
    material = dict(value) if isinstance(value, Mapping) else {}
    record_id = material.pop("record_id", None)
    if (
        not isinstance(value, Mapping)
        or set(value)
        != {
            "schema_version",
            "kind",
            "installation_nonce",
            "machine_hint",
            "user_hint",
            "record_id",
        }
        or value.get("schema_version") != 1
        or value.get("kind") != "hive-mind-machine-user-installation-v1"
        or not isinstance(value.get("installation_nonce"), str)
        or len(str(value["installation_nonce"])) != 64
        or record_id != digest_json(material)
    ):
        raise ConfigurationError("sealed machine-user identity is invalid")
    return digest_json(
        {
            "kind": "hive-mind-machine-user-key-v1",
            "installation_record_id": record_id,
        }
    )


def resolve_host_runtime_dir(
    host_runtime_dir: str | Path | None = None,
) -> Path:
    """Resolve the one machine-user capacity arbiter without creating it."""

    base = _reject_link_components(
        _host_runtime_base_dir(), label="host runtime authority base"
    )
    locator = base / "host-runtime-root.json"
    bound: Path | None = None
    if locator.exists() or _is_link_like(locator):
        _reject_link_components(locator, label="host-runtime root locator")
        if not locator.is_file():
            raise ConfigurationError("host-runtime root locator is not a regular file")
        try:
            raw = locator.read_bytes()
            value = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_strict_json_pairs,
                parse_constant=_reject_json_constant,
            )
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            raise ConfigurationError("host-runtime root locator is malformed") from error
        material = dict(value) if isinstance(value, Mapping) else {}
        record_id = material.pop("record_id", None)
        if (
            not isinstance(value, Mapping)
            or set(value)
            != {"schema_version", "kind", "machine_user_id", "host_runtime_dir", "record_id"}
            or value.get("schema_version") != 1
            or value.get("kind") != "hive-mind-host-runtime-root-v1"
            or value.get("machine_user_id") != _machine_user_identity()
            or record_id != digest_json(material)
        ):
            raise ConfigurationError("host-runtime root locator is invalid")
        selected = value.get("host_runtime_dir")
        if not isinstance(selected, str) or not Path(selected).is_absolute():
            raise ConfigurationError("host-runtime root locator path is invalid")
        bound = _reject_link_components(selected, label="bound host runtime root").resolve()
    requested = (
        _reject_link_components(host_runtime_dir, label="host runtime root").resolve()
        if host_runtime_dir is not None
        else None
    )
    if bound is not None:
        if requested is not None and requested != bound:
            raise ConfigurationError(
                "machine-user host runtime is already bound to another root"
            )
        return bound
    return requested if requested is not None else (base / "host-runtime").resolve()


def host_kernel_identity() -> Mapping[str, object]:
    """Return the immutable loaded identity of the machine-user authority writer.

    Repository executions may run different application revisions concurrently,
    but only the controller revision sealed into the host runtime may mutate the
    machine-user capacity/registry FSM.  The controller digest was captured when
    this module loaded and is compared with the path at every authority open.  A
    file replacement therefore cannot make already-loaded old code impersonate
    the successor writer generation.
    """

    controller_path = _reject_link_components(
        Path(__file__), label="host-kernel controller module"
    ).resolve()
    if not controller_path.is_file():
        raise ConfigurationError("host-kernel controller module is unavailable")
    controller_bytes = _read_regular_authority_bytes(
        controller_path, label="host-kernel controller module"
    )
    if (
        controller_path != _LOADED_CONTROLLER_PATH
        or "sha256:" + sha256(controller_bytes).hexdigest()
        != _LOADED_CONTROLLER_DIGEST
    ):
        raise ConfigurationError(
            "host-kernel controller bytes changed after this process loaded; "
            "restart before opening machine-user authority"
        )
    executable = _reject_link_components(
        Path(sys.executable), label="host-kernel Python executable"
    ).resolve()
    if not executable.is_file():
        raise ConfigurationError("host-kernel Python executable is unavailable")
    executable_bytes = _read_regular_authority_bytes(
        executable, label="host-kernel Python executable"
    )
    interpreter_material: dict[str, object] = {
        "kind": "hive-mind-host-kernel-interpreter-policy-v1",
        "implementation": sys.implementation.name,
        "cache_tag": sys.implementation.cache_tag,
        "version": [
            sys.version_info.major,
            sys.version_info.minor,
            sys.version_info.micro,
        ],
        "byteorder": sys.byteorder,
        "optimize": sys.flags.optimize,
        "executable_digest": "sha256:" + sha256(executable_bytes).hexdigest(),
    }
    interpreter_policy_digest = digest_json(interpreter_material)
    bundle_material: dict[str, object] = {
        "kind": HOST_KERNEL_BUNDLE_KIND,
        "components": [
            {
                # The machine-user writer is shared by linked worktrees and
                # independent clones.  Its semantic identity is the logical
                # component plus exact bytes, never a checkout-specific path.
                "path": ".autopilot/bin/controller.py",
                "digest": _LOADED_CONTROLLER_DIGEST,
            }
        ],
        "interpreter_policy_digest": interpreter_policy_digest,
    }
    return {
        "schema_version": 1,
        **bundle_material,
        "bundle_digest": digest_json(bundle_material),
        "interpreter": interpreter_material,
    }


def _validate_host_runtime_identity(
    value: object,
    *,
    machine_user_id: str,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != HOST_RUNTIME_IDENTITY_FIELDS:
        raise ConfigurationError("host-global runtime identity schema is ambiguous")
    material = dict(value)
    record_id = material.pop("record_id", None)
    try:
        parse_time(value.get("installed_at"))
    except (TypeError, ValueError) as error:
        raise ConfigurationError("host-global runtime installation time is invalid") from error
    previous_generation = value.get("previous_host_kernel_generation")
    previous_record = value.get("previous_host_kernel_record_id")
    epoch = value.get("host_kernel_epoch")
    generation_material = {
        "kind": "hive-mind-host-kernel-generation-key-v1",
        "machine_user_id": value.get("machine_user_id"),
        "host_kernel_epoch": epoch,
        "host_kernel_bundle_digest": value.get("host_kernel_bundle_digest"),
        "interpreter_policy_digest": value.get("interpreter_policy_digest"),
    }
    if (
        value.get("schema_version") != 1
        or value.get("kind") != HOST_RUNTIME_IDENTITY_KIND
        or value.get("machine_user_id") != machine_user_id
        or type(epoch) is not int
        or int(epoch) < 1
        or AUTHORITY_ID.fullmatch(str(value.get("host_kernel_bundle_digest"))) is None
        or AUTHORITY_ID.fullmatch(str(value.get("interpreter_policy_digest"))) is None
        or value.get("host_kernel_generation") != digest_json(generation_material)
        or ((previous_generation is None) != (previous_record is None))
        or (
            int(epoch) == 1
            and (previous_generation is not None or previous_record is not None)
        )
        or (
            int(epoch) > 1
            and (
                AUTHORITY_ID.fullmatch(str(previous_generation)) is None
                or AUTHORITY_ID.fullmatch(str(previous_record)) is None
            )
        )
        or record_id != digest_json(material)
    ):
        raise ConfigurationError("host-global runtime identity is invalid")
    return dict(value)


def _host_kernel_history(
    host_runtime_dir: str | Path,
    *,
    machine_user_id: str,
    raw_override: bytes | None = None,
) -> tuple[Mapping[str, object], ...]:
    path = Path(host_runtime_dir) / "host-kernel-history.jsonl"
    records = (
        _strict_jsonl_records_bytes(
            raw_override, label="host-kernel generation history"
        )
        if raw_override is not None
        else strict_jsonl_records(path, label="host-kernel generation history")
    )
    previous_event_id: str | None = None
    previous_identity: Mapping[str, object] | None = None
    seen_bundles: set[tuple[str, str]] = set()
    events: list[Mapping[str, object]] = []
    for index, raw in enumerate(records, 1):
        if set(raw) != HOST_KERNEL_HISTORY_FIELDS:
            raise ConfigurationError(
                f"host-kernel generation history line {index} schema is ambiguous"
            )
        material = dict(raw)
        event_id = material.pop("event_id", None)
        identity = _validate_host_runtime_identity(
            raw.get("identity"), machine_user_id=machine_user_id
        )
        try:
            parse_time(raw.get("recorded_at"))
        except (TypeError, ValueError) as error:
            raise ConfigurationError(
                f"host-kernel generation history line {index} time is invalid"
            ) from error
        bundle_key = (
            str(identity["host_kernel_bundle_digest"]),
            str(identity["interpreter_policy_digest"]),
        )
        expected_epoch = 1 if previous_identity is None else int(
            previous_identity["host_kernel_epoch"]
        ) + 1
        if (
            raw.get("schema_version") != 1
            or raw.get("kind") != HOST_KERNEL_HISTORY_KIND
            or raw.get("state") != "INSTALLED"
            or not isinstance(raw.get("actor"), str)
            or not str(raw["actor"]).strip()
            or not isinstance(raw.get("reason"), str)
            or not str(raw["reason"]).strip()
            or raw.get("previous_event_id") != previous_event_id
            or event_id != digest_json(material)
            or identity.get("host_kernel_epoch") != expected_epoch
            or identity.get("previous_host_kernel_generation")
            != (
                previous_identity.get("host_kernel_generation")
                if previous_identity is not None
                else None
            )
            or identity.get("previous_host_kernel_record_id")
            != (previous_identity.get("record_id") if previous_identity is not None else None)
            or (bundle_key in seen_bundles and previous_identity is not None)
        ):
            raise ConfigurationError(
                f"host-kernel generation history line {index} is invalid or replays a retired writer"
            )
        legacy_id = raw.get("legacy_predecessor_record_id")
        legacy_path = raw.get("legacy_predecessor_path")
        legacy_blob = raw.get("legacy_predecessor_blob_digest")
        if any(item is not None for item in (legacy_id, legacy_path, legacy_blob)):
            if (
                index != 1
                or not all(
                    isinstance(item, str) and AUTHORITY_ID.fullmatch(item) is not None
                    for item in (legacy_id, legacy_blob)
                )
                or not isinstance(legacy_path, str)
                or legacy_path
                != "legacy-host-runtime-identities/"
                + str(legacy_id).removeprefix("sha256:")
                + ".json"
            ):
                raise ConfigurationError(
                    "host-kernel legacy predecessor evidence is invalid"
                )
            evidence_path = Path(host_runtime_dir) / legacy_path
            evidence_bytes = _read_regular_authority_bytes(
                evidence_path, label="legacy host-runtime identity evidence"
            )
            evidence = parse_strict_canonical_json_bytes(
                evidence_bytes, label="legacy host-runtime identity evidence"
            )
            evidence_material = dict(evidence) if isinstance(evidence, Mapping) else {}
            evidence_record_id = evidence_material.pop("record_id", None)
            if (
                not isinstance(evidence, Mapping)
                or set(evidence)
                != {"schema_version", "kind", "machine_user_id", "record_id"}
                or evidence.get("schema_version") != 1
                or evidence.get("kind") != HOST_RUNTIME_IDENTITY_KIND
                or evidence.get("machine_user_id") != machine_user_id
                or evidence_record_id != legacy_id
                or evidence_record_id != digest_json(evidence_material)
                or "sha256:" + sha256(evidence_bytes).hexdigest() != legacy_blob
            ):
                raise ConfigurationError(
                    "host-kernel legacy predecessor evidence changed"
                )
        seen_bundles.add(bundle_key)
        previous_event_id = str(event_id)
        previous_identity = identity
        events.append(dict(raw))
    return tuple(events)


def _new_host_runtime_identity(
    *,
    machine_user_id: str,
    kernel: Mapping[str, object],
    epoch: int,
    installed_at: str,
    previous: Mapping[str, object] | None,
) -> Mapping[str, object]:
    generation_material: dict[str, object] = {
        "kind": "hive-mind-host-kernel-generation-key-v1",
        "machine_user_id": machine_user_id,
        "host_kernel_epoch": epoch,
        "host_kernel_bundle_digest": kernel["bundle_digest"],
        "interpreter_policy_digest": kernel["interpreter_policy_digest"],
    }
    material: dict[str, object] = {
        "schema_version": 1,
        "kind": HOST_RUNTIME_IDENTITY_KIND,
        "machine_user_id": machine_user_id,
        "host_kernel_generation": digest_json(generation_material),
        "host_kernel_epoch": epoch,
        "host_kernel_bundle_digest": kernel["bundle_digest"],
        "interpreter_policy_digest": kernel["interpreter_policy_digest"],
        "installed_at": installed_at,
        "previous_host_kernel_generation": (
            previous.get("host_kernel_generation") if previous is not None else None
        ),
        "previous_host_kernel_record_id": (
            previous.get("record_id") if previous is not None else None
        ),
    }
    return {**material, "record_id": digest_json(material)}


def _host_kernel_generation_event(
    identity: Mapping[str, object],
    *,
    actor: str,
    reason: str,
    recorded_at: str,
    history: Sequence[Mapping[str, object]],
    legacy_predecessor: Mapping[str, object] | None = None,
) -> Mapping[str, object]:
    material: dict[str, object] = {
        "schema_version": 1,
        "kind": HOST_KERNEL_HISTORY_KIND,
        "state": "INSTALLED",
        "identity": dict(identity),
        "actor": actor,
        "reason": reason,
        "recorded_at": recorded_at,
        "legacy_predecessor_record_id": (
            legacy_predecessor.get("record_id")
            if legacy_predecessor is not None
            else None
        ),
        "legacy_predecessor_path": (
            legacy_predecessor.get("path")
            if legacy_predecessor is not None
            else None
        ),
        "legacy_predecessor_blob_digest": (
            legacy_predecessor.get("blob_digest")
            if legacy_predecessor is not None
            else None
        ),
        "previous_event_id": history[-1]["event_id"] if history else None,
    }
    return {**material, "event_id": digest_json(material)}


def _append_host_kernel_generation(
    host_runtime_dir: Path,
    identity: Mapping[str, object],
    *,
    actor: str,
    reason: str,
    recorded_at: str,
    history: Sequence[Mapping[str, object]],
    legacy_predecessor: Mapping[str, object] | None = None,
) -> Mapping[str, object]:
    event = _host_kernel_generation_event(
        identity,
        actor=actor,
        reason=reason,
        recorded_at=recorded_at,
        history=history,
        legacy_predecessor=legacy_predecessor,
    )
    _append_canonical_jsonl(host_runtime_dir / "host-kernel-history.jsonl", event)
    return event


def _validate_host_kernel_transition(
    value: object,
    *,
    machine_user_id: str,
) -> Mapping[str, object]:
    prepared = _validate_kernel_transition(
        value,
        kind=HOST_KERNEL_TRANSITION_KIND,
        authority_plane="HOST",
        identity_validator=lambda raw: _validate_host_runtime_identity(
            raw, machine_user_id=machine_user_id
        ),
    )
    event = prepared["history_event"]
    assert isinstance(event, Mapping)
    material = dict(event)
    event_id = material.pop("event_id", None)
    successor = prepared["successor_identity"]
    assert isinstance(successor, Mapping)
    legacy = event.get("legacy_predecessor_record_id") is not None
    if (
        set(event) != HOST_KERNEL_HISTORY_FIELDS
        or event.get("schema_version") != 1
        or event.get("kind") != HOST_KERNEL_HISTORY_KIND
        or event.get("state") != "INSTALLED"
        or event.get("identity") != successor
        or event.get("actor") != prepared.get("actor")
        or event.get("reason") != prepared.get("reason")
        or event.get("recorded_at") != prepared.get("prepared_at")
        or event.get("previous_event_id") != prepared.get("previous_event_id")
        or (
            legacy
            and (
                prepared.get("predecessor_generation") is not None
                or successor.get("previous_host_kernel_record_id") is not None
                or successor.get("previous_host_kernel_generation") is not None
                or event.get("legacy_predecessor_record_id")
                != prepared.get("predecessor_record_id")
            )
        )
        or (
            not legacy
            and (
                successor.get("previous_host_kernel_record_id")
                != prepared.get("predecessor_record_id")
                or successor.get("previous_host_kernel_generation")
                != prepared.get("predecessor_generation")
                or any(
                    event.get(field) is not None
                    for field in (
                        "legacy_predecessor_record_id",
                        "legacy_predecessor_path",
                        "legacy_predecessor_blob_digest",
                    )
                )
            )
        )
        or event_id != digest_json(material)
    ):
        raise ConfigurationError("host-kernel transition event is invalid")
    return prepared


def _prepare_host_kernel_transition(
    host_runtime_dir: Path,
    successor: Mapping[str, object],
    *,
    predecessor: Mapping[str, object] | None,
    history: Sequence[Mapping[str, object]],
    actor: str,
    reason: str,
    recorded_at: str,
    legacy_predecessor: Mapping[str, object] | None = None,
) -> Mapping[str, object]:
    event = _host_kernel_generation_event(
        successor,
        actor=actor,
        reason=reason,
        recorded_at=recorded_at,
        history=history,
        legacy_predecessor=legacy_predecessor,
    )
    predecessor_record_id = (
        predecessor.get("record_id")
        if predecessor is not None
        else (
            legacy_predecessor.get("record_id")
            if legacy_predecessor is not None
            else None
        )
    )
    prepared = _prepare_kernel_transition(
        host_runtime_dir,
        kind=HOST_KERNEL_TRANSITION_KIND,
        authority_plane="HOST",
        predecessor_record_id=(
            str(predecessor_record_id)
            if predecessor_record_id is not None
            else None
        ),
        predecessor_generation=(
            str(predecessor["host_kernel_generation"])
            if predecessor is not None
            else None
        ),
        previous_event_id=history[-1].get("event_id") if history else None,
        successor_identity=successor,
        history_event=event,
        actor=actor,
        reason=reason,
        prepared_at=recorded_at,
        identity_validator=lambda raw: _validate_host_runtime_identity(
            raw, machine_user_id=str(successor["machine_user_id"])
        ),
    )
    return _validate_host_kernel_transition(
        prepared, machine_user_id=str(successor["machine_user_id"])
    )


def _finish_host_kernel_transition(
    host_runtime_dir: Path,
    identity_path: Path,
    prepared: Mapping[str, object],
    *,
    machine_user_id: str,
) -> Mapping[str, object]:
    prepared = _validate_host_kernel_transition(
        prepared, machine_user_id=machine_user_id
    )
    _ensure_kernel_transition_immutable(host_runtime_dir, prepared)
    _repair_or_append_prepared_kernel_event(
        host_runtime_dir / "host-kernel-history.jsonl",
        prepared,
        validate_prefix=lambda raw: _host_kernel_history(
            host_runtime_dir,
            machine_user_id=machine_user_id,
            raw_override=raw,
        ),
    )
    successor = _validate_host_runtime_identity(
        prepared["successor_identity"], machine_user_id=machine_user_id
    )
    atomic_write_json(identity_path, successor)
    installed = _validate_host_runtime_identity(
        read_strict_canonical_json(
            identity_path,
            label="host-kernel successor identity",
            expected_fields=HOST_RUNTIME_IDENTITY_FIELDS,
        ),
        machine_user_id=machine_user_id,
    )
    if installed != successor:
        raise ConfigurationError("host-kernel successor projection changed")
    _complete_kernel_transition(host_runtime_dir, prepared)
    return installed


def initialize_host_runtime(
    host_runtime_dir: str | Path | None = None,
) -> Mapping[str, object]:
    """Explicitly bind and initialize the machine-user capacity arbiter."""

    directory = resolve_host_runtime_dir(host_runtime_dir)
    base = _reject_link_components(
        _host_runtime_base_dir(), label="host runtime authority base"
    )
    base.mkdir(parents=True, exist_ok=True)
    machine_user_id = _machine_user_identity(create=True)
    locator_material: dict[str, object] = {
        "schema_version": 1,
        "kind": "hive-mind-host-runtime-root-v1",
        "machine_user_id": machine_user_id,
        "host_runtime_dir": str(directory),
    }
    locator = {
        **locator_material,
        "record_id": digest_json(locator_material),
    }
    exclusive_write_json_or_identical(base / "host-runtime-root.json", locator)
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / "locks" / "host-authority.lock"
    with runtime_file_lock(lock_path):
        identity_path = directory / "host-runtime-identity.json"
        transition_path = directory / KERNEL_TRANSITION_POINTER
        if transition_path.exists() or _is_link_like(transition_path):
            pending = _validate_host_kernel_transition(
                read_strict_canonical_json(
                    transition_path,
                    label="pending host-runtime initialization",
                ),
                machine_user_id=machine_user_id,
            )
            successor = pending["successor_identity"]
            assert isinstance(successor, Mapping)
            kernel = host_kernel_identity()
            if (
                pending.get("predecessor_record_id") is not None
                or pending.get("predecessor_generation") is not None
                or pending.get("actor") != "host-runtime-initialize"
                or pending.get("reason")
                != "initial canonical machine-user host-kernel writer"
                or successor.get("host_kernel_bundle_digest")
                != kernel.get("bundle_digest")
                or successor.get("interpreter_policy_digest")
                != kernel.get("interpreter_policy_digest")
            ):
                raise ConfigurationError(
                    "host runtime has a pending upgrade; retry the exact upgrade command"
                )
            return _finish_host_kernel_transition(
                directory,
                identity_path,
                pending,
                machine_user_id=machine_user_id,
            )
        if identity_path.exists() or _is_link_like(identity_path):
            installed = read_strict_canonical_json(
                identity_path,
                label="host-global runtime identity",
            )
            try:
                identity = _validate_host_runtime_identity(
                    installed, machine_user_id=machine_user_id
                )
            except ConfigurationError as error:
                raise ConfigurationError(
                    "legacy or invalid host runtime requires explicit zero-activity host-kernel upgrade"
                ) from error
            history = _host_kernel_history(
                directory, machine_user_id=machine_user_id
            )
            if not history or history[-1].get("identity") != identity:
                raise ConfigurationError(
                    "host runtime identity has no exact append-only kernel history"
                )
            current_kernel = host_kernel_identity()
            if (
                identity.get("host_kernel_bundle_digest")
                != current_kernel.get("bundle_digest")
                or identity.get("interpreter_policy_digest")
                != current_kernel.get("interpreter_policy_digest")
            ):
                raise ConfigurationError(
                    "host runtime is bound to another writer generation; explicit zero-activity upgrade is required"
                )
            return identity
        history = _host_kernel_history(directory, machine_user_id=machine_user_id)
        if history:
            if len(history) != 1:
                raise ConfigurationError(
                    "host-kernel history is ahead of an absent current identity"
                )
            genesis = history[0]
            identity = dict(genesis["identity"])
            loaded_kernel = host_kernel_identity()
            if (
                genesis.get("actor") != "host-runtime-initialize"
                or genesis.get("reason")
                != "initial canonical machine-user host-kernel writer"
                or genesis.get("legacy_predecessor_record_id") is not None
                or genesis.get("legacy_predecessor_path") is not None
                or genesis.get("legacy_predecessor_blob_digest") is not None
                or identity.get("host_kernel_epoch") != 1
                or identity.get("previous_host_kernel_generation") is not None
                or identity.get("previous_host_kernel_record_id") is not None
                or identity.get("host_kernel_bundle_digest")
                != loaded_kernel.get("bundle_digest")
                or identity.get("interpreter_policy_digest")
                != loaded_kernel.get("interpreter_policy_digest")
            ):
                raise ConfigurationError(
                    "absent host-runtime projection has no exact current-kernel "
                    "initialization receipt"
                )
        else:
            installed_at = format_time(utc_now())
            identity = _new_host_runtime_identity(
                machine_user_id=machine_user_id,
                kernel=host_kernel_identity(),
                epoch=1,
                installed_at=installed_at,
                previous=None,
            )
            pending = _prepare_host_kernel_transition(
                directory,
                identity,
                predecessor=None,
                history=history,
                actor="host-runtime-initialize",
                reason="initial canonical machine-user host-kernel writer",
                recorded_at=installed_at,
            )
            return _finish_host_kernel_transition(
                directory,
                identity_path,
                pending,
                machine_user_id=machine_user_id,
            )
        atomic_write_json(identity_path, identity)
        return _validate_host_runtime_identity(identity, machine_user_id=machine_user_id)


def require_host_runtime(host_runtime_dir: str | Path | None = None) -> Path:
    directory = resolve_host_runtime_dir(host_runtime_dir)
    identity_path = directory / "host-runtime-identity.json"
    lock_path = directory / "locks" / "host-authority.lock"
    if not identity_path.is_file() or not lock_path.is_file():
        raise ConfigurationError(
            "host-global runtime is absent; run explicit host-runtime initialization"
        )
    machine_user_id = _machine_user_identity()
    value = read_strict_canonical_json(
        identity_path,
        label="host-global runtime identity",
        expected_fields=HOST_RUNTIME_IDENTITY_FIELDS,
    )
    identity = _validate_host_runtime_identity(
        value, machine_user_id=machine_user_id
    )
    transition_path = directory / KERNEL_TRANSITION_POINTER
    if transition_path.exists() or _is_link_like(transition_path):
        raise ConfigurationError(
            "host-kernel transition is PREPARED; retry or recover the exact upgrade"
        )
    if _pending_host_torn_tail_recoveries(directory):
        raise ConfigurationError(
            "host authority has an incomplete torn-tail recovery; complete it before mutation"
        )
    history = _host_kernel_history(directory, machine_user_id=machine_user_id)
    if not history or history[-1].get("identity") != identity:
        raise ConfigurationError(
            "host-global runtime identity differs from its append-only writer history"
        )
    current_kernel = host_kernel_identity()
    if (
        identity.get("host_kernel_bundle_digest") != current_kernel.get("bundle_digest")
        or identity.get("interpreter_policy_digest")
        != current_kernel.get("interpreter_policy_digest")
    ):
        raise ConfigurationError(
            "stale host-kernel writer generation cannot mutate machine-user authority"
        )
    return directory


def _preflight_host_stores_for_kernel_upgrade(
    host_runtime_dir: Path,
    *,
    current_writer: Mapping[str, object] | None,
) -> tuple[Mapping[str, object], ...]:
    """Strictly reduce every host-global ledger before rotating its writer.

    A successor must never strand a torn or history-ahead store that only the
    predecessor can classify.  This helper performs no writes and is called
    under ``host-authority.lock`` before legacy evidence or PREPARED transition
    publication.
    """

    _host_repository_registry_events(host_runtime_dir)
    reservations = _host_reservation_events_unlocked(host_runtime_dir)
    scheduler_events = _host_scheduler_events_unlocked(host_runtime_dir)
    if scheduler_events:
        scheduler = _host_scheduler_projection_unlocked(
            host_runtime_dir,
            host_id=str(scheduler_events[-1]["host_id"]),
        )
        if scheduler["outstanding_grants"] or any(
            scheduler["remaining_candidates"].values()
        ):
            raise ConfigurationError(
                "host scheduler demand or grant authority blocks kernel upgrade"
            )

    provider_path = host_runtime_dir / "host-provider.json"
    provider_history_path = host_runtime_dir / "host-provider-history.jsonl"
    provider_present = any(
        path.exists() or _is_link_like(path)
        for path in (provider_path, provider_history_path)
    )
    if provider_present:
        if current_writer is None:
            raise ConfigurationError(
                "legacy host runtime has provider authority requiring explicit recovery"
            )
        if not provider_path.is_file() or _is_link_like(provider_path):
            raise ConfigurationError("host provider projection is unavailable")
        provider_value = read_strict_canonical_json(
            provider_path, label="host-kernel upgrade provider projection"
        )
        if not isinstance(provider_value, Mapping) or not isinstance(
            provider_value.get("host_id"), str
        ):
            raise ConfigurationError("host provider projection is invalid")
        _host_provider_binding(
            host_runtime_dir,
            host_id=str(provider_value["host_id"]),
            _writer_override=current_writer,
        )
        provider_history = strict_jsonl_records(
            provider_history_path,
            label="host provider generation history",
        )
        if not provider_history or provider_history[-1] != provider_value:
            raise ConfigurationError(
                "host provider transition is incomplete before kernel upgrade"
            )

    hosts_root = host_runtime_dir / "hosts"
    if hosts_root.exists() or _is_link_like(hosts_root):
        _reject_link_components(hosts_root, label="host capacity authority root")
        if not hosts_root.is_dir():
            raise ConfigurationError("host capacity authority root is not a directory")
        for host_directory in sorted(hosts_root.iterdir(), key=lambda item: item.name):
            _reject_link_components(
                host_directory, label="host capacity authority directory"
            )
            if (
                not host_directory.is_dir()
                or re.fullmatch(r"[0-9a-f]{64}", host_directory.name) is None
            ):
                raise ConfigurationError(
                    "host capacity authority contains an unclassified entry"
                )
            capacity_path = host_directory / "capacity.json"
            history_path = host_directory / "capacity-history.jsonl"
            if not capacity_path.is_file() or _is_link_like(capacity_path):
                raise ConfigurationError(
                    "host capacity generation lacks its current projection"
                )
            value = read_strict_canonical_json(
                capacity_path, label="host-kernel upgrade capacity projection"
            )
            if not isinstance(value, Mapping) or not isinstance(
                value.get("host_id"), str
            ):
                raise ConfigurationError("host capacity projection is invalid")
            host_id = str(value["host_id"])
            if host_capacity_path(host_runtime_dir, host_id).parent != host_directory:
                raise ConfigurationError("host capacity directory key is invalid")
            capacity = validate_host_capacity(
                value,
                host_id=host_id,
                now=datetime.max.replace(tzinfo=UTC),
                require_live=False,
            )
            if not history_path.is_file() or _is_link_like(history_path):
                raise ConfigurationError("host capacity has no append-only history")
            history = _strict_capacity_history(history_path)
            if (
                not history
                or history[-1].get("capacity_record_id")
                != capacity.get("record_id")
            ):
                raise ConfigurationError(
                    "host capacity transition is incomplete before kernel upgrade"
                )
    return reservations


def upgrade_host_runtime_kernel(
    host_runtime_dir: str | Path | None = None,
    *,
    actor: str,
    reason: str,
    expected_host_kernel_generation: str | None,
    upgraded_at: str | None = None,
) -> Mapping[str, object]:
    """Install this controller as the sole host-global writer at zero activity.

    The function intentionally authenticates the existing projection without
    calling :func:`require_host_runtime`, because a legitimate successor must be
    able to open a runtime whose current generation rejects it.  All other host
    APIs retain the fresh writer check and cannot use this bootstrap aperture.
    """

    if not isinstance(actor, str) or not actor.strip():
        raise ConfigurationError("host-kernel upgrade actor is required")
    if not isinstance(reason, str) or not reason.strip():
        raise ConfigurationError("host-kernel upgrade reason is required")
    actor = actor.strip()
    reason = reason.strip()
    recorded_at = upgraded_at or format_time(utc_now())
    try:
        parse_time(recorded_at)
    except (TypeError, ValueError) as error:
        raise ConfigurationError("host-kernel upgrade time is invalid") from error
    directory = resolve_host_runtime_dir(host_runtime_dir)
    identity_path = directory / "host-runtime-identity.json"
    if not identity_path.is_file() or _is_link_like(identity_path):
        raise ConfigurationError("host runtime must be initialized before upgrade")
    machine_user_id = _machine_user_identity()
    with runtime_file_lock(directory / "locks" / "host-authority.lock"):
        if _pending_host_torn_tail_recoveries(directory):
            raise ConfigurationError(
                "host-kernel upgrade requires completion of pending torn-tail recovery"
            )
        raw = _read_regular_authority_bytes(
            identity_path, label="host-runtime identity selected for upgrade"
        )
        value = parse_strict_canonical_json_bytes(
            raw, label="host-runtime identity selected for upgrade"
        )
        legacy: Mapping[str, object] | None = None
        try:
            current = _validate_host_runtime_identity(
                value, machine_user_id=machine_user_id
            )
        except ConfigurationError:
            material = dict(value) if isinstance(value, Mapping) else {}
            legacy_record_id = material.pop("record_id", None)
            if (
                not isinstance(value, Mapping)
                or set(value)
                != {"schema_version", "kind", "machine_user_id", "record_id"}
                or value.get("schema_version") != 1
                or value.get("kind") != HOST_RUNTIME_IDENTITY_KIND
                or value.get("machine_user_id") != machine_user_id
                or legacy_record_id != digest_json(material)
                or expected_host_kernel_generation is not None
            ):
                raise ConfigurationError(
                    "host-kernel upgrade predecessor identity is invalid or CAS-mismatched"
                )
            legacy_path = (
                directory
                / "legacy-host-runtime-identities"
                / (str(legacy_record_id).removeprefix("sha256:") + ".json")
            )
            legacy = {
                "record_id": legacy_record_id,
                "path": str(legacy_path.relative_to(directory)).replace("\\", "/"),
                "blob_digest": "sha256:" + sha256(raw).hexdigest(),
            }
            current = None
        requested_kernel = host_kernel_identity()
        requested_key = (
            str(requested_kernel["bundle_digest"]),
            str(requested_kernel["interpreter_policy_digest"]),
        )
        transition_path = directory / KERNEL_TRANSITION_POINTER
        if transition_path.exists() or _is_link_like(transition_path):
            # PREPARED is the durable zero-activity capability.  Once it is
            # published every ordinary host writer is fenced, so an exact
            # retry must finish that transition before consulting provider or
            # capacity projections that still legitimately name the
            # predecessor kernel.
            prepared_transition = _validate_host_kernel_transition(
                read_strict_canonical_json(
                    transition_path, label="pending host-kernel upgrade"
                ),
                machine_user_id=machine_user_id,
            )
            successor = prepared_transition["successor_identity"]
            assert isinstance(successor, Mapping)
            current_matches = (
                current is not None
                and current.get("record_id")
                in {
                    prepared_transition.get("predecessor_record_id"),
                    successor.get("record_id"),
                }
            )
            legacy_matches = (
                current is None
                and legacy is not None
                and prepared_transition.get("predecessor_record_id")
                == legacy.get("record_id")
            )
            if (
                prepared_transition.get("actor") != actor
                or prepared_transition.get("reason") != reason
                or prepared_transition.get("predecessor_generation")
                != expected_host_kernel_generation
                or (
                    str(successor["host_kernel_bundle_digest"]),
                    str(successor["interpreter_policy_digest"]),
                )
                != requested_key
                or not (current_matches or legacy_matches)
            ):
                raise ConfigurationError(
                    "pending host-kernel upgrade differs from this retry"
                )
            return _finish_host_kernel_transition(
                directory,
                identity_path,
                prepared_transition,
                machine_user_id=machine_user_id,
            )

        retry_history = _host_kernel_history(
            directory, machine_user_id=machine_user_id
        )
        if current is not None and retry_history:
            current_key = (
                str(current["host_kernel_bundle_digest"]),
                str(current["interpreter_policy_digest"]),
            )
            head = retry_history[-1]
            if head.get("identity") == current and current_key == requested_key:
                if expected_host_kernel_generation == current.get(
                    "host_kernel_generation"
                ):
                    return current
                if (
                    expected_host_kernel_generation
                    == current.get("previous_host_kernel_generation")
                    and head.get("actor") == actor
                    and head.get("reason") == reason
                ):
                    # Lost-response retry after COMPLETE is authenticated by
                    # the exact predecessor CAS and immutable history row.  It
                    # is read-only and must remain possible after ordinary
                    # provider/capacity activity resumes.
                    return current
        reservation_events = _preflight_host_stores_for_kernel_upgrade(
            directory, current_writer=current
        )
        latest_reservations: dict[str, Mapping[str, object]] = {}
        for reservation_event in reservation_events:
            latest_reservations[str(reservation_event["reservation_id"])] = (
                reservation_event
            )
        if any(
            event.get("state") in HOST_RESERVATION_ACTIVE_STATES
            for event in latest_reservations.values()
        ):
            raise ConfigurationError(
                "host-kernel upgrade requires zero active or unreconciled reservations"
            )
        if legacy is not None:
            # Legacy bytes become durable evidence only after every read-only
            # writer/ledger/zero-activity preflight succeeds.  A rejected or
            # stale upgrade therefore leaves no authority-shaped artifact.
            exclusive_write_bytes_or_identical(
                directory / str(legacy["path"]), raw
            )
        transition_path = directory / KERNEL_TRANSITION_POINTER
        prepared_transition: Mapping[str, object] | None = None
        if transition_path.exists() or _is_link_like(transition_path):
            prepared_transition = _validate_host_kernel_transition(
                read_strict_canonical_json(
                    transition_path, label="pending host-kernel upgrade"
                ),
                machine_user_id=machine_user_id,
            )
            successor = prepared_transition["successor_identity"]
            assert isinstance(successor, Mapping)
            expected_predecessor_record = (
                prepared_transition.get("predecessor_record_id")
                if current is not None
                and current.get("record_id")
                in {
                    prepared_transition.get("predecessor_record_id"),
                    successor.get("record_id"),
                }
                else legacy.get("record_id") if legacy is not None else None
            )
            if (
                prepared_transition.get("actor") != actor.strip()
                or prepared_transition.get("reason") != reason.strip()
                or prepared_transition.get("predecessor_record_id")
                != expected_predecessor_record
                or prepared_transition.get("predecessor_generation")
                != expected_host_kernel_generation
                or (
                    str(successor["host_kernel_bundle_digest"]),
                    str(successor["interpreter_policy_digest"]),
                )
                != requested_key
                or (
                    current is not None
                    and current.get("record_id")
                    not in {
                        prepared_transition.get("predecessor_record_id"),
                        successor.get("record_id"),
                    }
                )
            ):
                raise ConfigurationError(
                    "pending host-kernel upgrade differs from this retry"
                )
            _ensure_kernel_transition_immutable(directory, prepared_transition)
            _repair_or_append_prepared_kernel_event(
                directory / "host-kernel-history.jsonl",
                prepared_transition,
                validate_prefix=lambda history_raw: _host_kernel_history(
                    directory,
                    machine_user_id=machine_user_id,
                    raw_override=history_raw,
                ),
            )
        history = _host_kernel_history(
            directory, machine_user_id=machine_user_id
        )
        history_ahead = False
        legacy_history_ahead = False
        if current is not None:
            if not history:
                raise ConfigurationError(
                    "host-kernel upgrade predecessor differs from its history"
                )
            latest_identity = history[-1].get("identity")
            history_ahead = latest_identity != current
            if history_ahead and (
                len(history) < 2
                or history[-2].get("identity") != current
                or latest_identity.get("previous_host_kernel_generation")
                != current.get("host_kernel_generation")
                or latest_identity.get("previous_host_kernel_record_id")
                != current.get("record_id")
            ):
                raise ConfigurationError(
                    "host-kernel history is ambiguously ahead of its projection"
                )
        elif history:
            # Legacy adoption is also history-first.  A crash after the first
            # generation was appended leaves the legacy projection in place;
            # only the one exact event that cites the immutable legacy bytes may
            # be adopted.  No other history shape is classifiable.
            if (
                legacy is None
                or len(history) != 1
                or history[0].get("legacy_predecessor_record_id")
                != legacy.get("record_id")
                or history[0].get("legacy_predecessor_path") != legacy.get("path")
                or history[0].get("legacy_predecessor_blob_digest")
                != legacy.get("blob_digest")
            ):
                raise ConfigurationError(
                    "legacy host-kernel projection conflicts with an existing generation history"
                )
            legacy_history_ahead = True
        if current is not None:
            current_key = (
                str(current["host_kernel_bundle_digest"]),
                str(current["interpreter_policy_digest"]),
            )
            exact_current_cas = (
                expected_host_kernel_generation
                == current.get("host_kernel_generation")
            )
            completed_retry_cas = (
                not history_ahead
                and expected_host_kernel_generation
                == current.get("previous_host_kernel_generation")
                and current_key == requested_key
                and history[-1].get("identity") == current
                and history[-1].get("actor") == actor.strip()
                and history[-1].get("reason") == reason.strip()
            )
            if not exact_current_cas and not completed_retry_cas:
                raise ConfigurationError("host-kernel upgrade generation CAS mismatch")
        elif expected_host_kernel_generation is not None:
            raise ConfigurationError("host-kernel upgrade generation CAS mismatch")
        if current is not None and (
            (
                str(current["host_kernel_bundle_digest"]),
                str(current["interpreter_policy_digest"]),
            )
            == requested_key
            and not history_ahead
            and prepared_transition is None
        ):
            return current
        if any(
            (
                str(event["identity"]["host_kernel_bundle_digest"]),
                str(event["identity"]["interpreter_policy_digest"]),
            )
            == requested_key
            for event in (
                history[:-1]
                if (history_ahead or legacy_history_ahead)
                else history
            )
        ):
            raise ConfigurationError(
                "host-kernel downgrade or retired-writer replay is prohibited"
            )
        if prepared_transition is not None:
            identity = dict(prepared_transition["successor_identity"])
            if history[-1].get("event_id") != prepared_transition[
                "history_event"
            ].get("event_id"):
                raise ConfigurationError(
                    "pending host-kernel event is not the history head"
                )
        elif history_ahead or legacy_history_ahead:
            pending = dict(history[-1]["identity"])
            if (
                pending.get("host_kernel_bundle_digest")
                != requested_kernel.get("bundle_digest")
                or pending.get("interpreter_policy_digest")
                != requested_kernel.get("interpreter_policy_digest")
                or history[-1].get("actor") != actor.strip()
                or history[-1].get("reason") != reason.strip()
                or (
                    current is not None
                    and expected_host_kernel_generation
                    != current.get("host_kernel_generation")
                )
            ):
                raise ConfigurationError(
                    "pending host-kernel upgrade differs from this retry"
                )
            identity = pending
        else:
            identity = _new_host_runtime_identity(
                machine_user_id=machine_user_id,
                kernel=requested_kernel,
                epoch=(1 if current is None else int(current["host_kernel_epoch"]) + 1),
                installed_at=recorded_at,
                previous=current,
            )
            prepared_transition = _prepare_host_kernel_transition(
                directory,
                identity,
                predecessor=current,
                history=history,
                actor=actor,
                reason=reason,
                recorded_at=recorded_at,
                legacy_predecessor=legacy,
            )
        if prepared_transition is not None:
            return _finish_host_kernel_transition(
                directory,
                identity_path,
                prepared_transition,
                machine_user_id=machine_user_id,
            )
        atomic_write_json(identity_path, identity)
        return _validate_host_runtime_identity(identity, machine_user_id=machine_user_id)


def _host_runtime_identity_unlocked(host_runtime_dir: Path) -> Mapping[str, object]:
    """Return the already-authenticated current writer under host authority."""

    if not runtime_file_lock_is_held(
        host_runtime_dir / "locks" / "host-authority.lock"
    ):
        raise ConfigurationError("host writer identity requires host authority")
    machine_user_id = _machine_user_identity()
    value = read_strict_canonical_json(
        host_runtime_dir / "host-runtime-identity.json",
        label="host-global runtime identity",
        expected_fields=HOST_RUNTIME_IDENTITY_FIELDS,
    )
    identity = _validate_host_runtime_identity(
        value, machine_user_id=machine_user_id
    )
    transition_path = host_runtime_dir / KERNEL_TRANSITION_POINTER
    if transition_path.exists() or _is_link_like(transition_path):
        raise ConfigurationError(
            "host-kernel transition is PREPARED; ordinary writers are fenced"
        )
    if _pending_host_torn_tail_recoveries(host_runtime_dir):
        raise ConfigurationError(
            "host authority has an incomplete torn-tail recovery; ordinary writers are fenced"
        )
    history = _host_kernel_history(
        host_runtime_dir, machine_user_id=machine_user_id
    )
    if not history or history[-1].get("identity") != identity:
        raise ConfigurationError(
            "host writer projection differs from append-only kernel history"
        )
    current_kernel = host_kernel_identity()
    if (
        identity.get("host_kernel_bundle_digest") != current_kernel.get("bundle_digest")
        or identity.get("interpreter_policy_digest")
        != current_kernel.get("interpreter_policy_digest")
    ):
        raise ConfigurationError("stale host-kernel writer cannot publish evidence")
    return identity


def read_current_host_runtime_identity(
    host_runtime_dir: str | Path | None = None,
) -> Mapping[str, object]:
    """Return the current host writer while the caller holds host authority.

    This is the public replacement for consumers that used to infer a host id
    by permissively parsing ``host-runtime-identity.json`` themselves.  It
    authenticates the loaded writer, full append-only generation history, and
    the caller-held canonical host lock before exposing ``machine_user_id`` or
    generation coordinates.
    """

    root = require_host_runtime(host_runtime_dir)
    if not runtime_file_lock_is_held(root / "locks" / "host-authority.lock"):
        raise ConfigurationError(
            "current host writer read requires caller-held host authority"
        )
    return dict(_host_runtime_identity_unlocked(root))


def _validate_host_provider_attestation(
    value: object,
    *,
    machine_user_id: str,
    host_id: str,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != HOST_PROVIDER_ATTESTATION_FIELDS:
        raise ConfigurationError("host provider attestation schema is ambiguous")
    material = dict(value)
    record_id = material.pop("record_id", None)
    provider_material = value.get("provider_identity_material")
    if (
        value.get("schema_version") != 1
        or value.get("kind") != HOST_PROVIDER_ATTESTATION_KIND
        or value.get("machine_user_id") != machine_user_id
        or value.get("host_id") != host_id
        or not isinstance(value.get("provider_identity_source"), str)
        or not str(value["provider_identity_source"]).strip()
        or not isinstance(provider_material, Mapping)
        or not provider_material
        or value.get("provider_identity_digest") != digest_json(provider_material)
        or AUTHORITY_ID.fullmatch(str(value.get("provider_identity_digest"))) is None
        or record_id != digest_json(material)
    ):
        raise ConfigurationError("host provider attestation is invalid")
    return dict(value)


def build_host_provider_attestation(
    host_runtime_dir: str | Path,
    *,
    host_id: str,
    provider_identity_source: str,
    provider_identity_material: Mapping[str, object],
) -> Mapping[str, object]:
    """Build the exact immutable global subset supplied by a host adapter."""

    root = require_host_runtime(host_runtime_dir)
    runtime_identity = read_strict_canonical_json(
        root / "host-runtime-identity.json",
        label="host-global runtime identity",
        expected_fields=HOST_RUNTIME_IDENTITY_FIELDS,
    )
    material: dict[str, object] = {
        "schema_version": 1,
        "kind": HOST_PROVIDER_ATTESTATION_KIND,
        "machine_user_id": runtime_identity["machine_user_id"],
        "host_id": host_id,
        "provider_identity_source": provider_identity_source,
        "provider_identity_material": dict(provider_identity_material),
        "provider_identity_digest": digest_json(provider_identity_material),
    }
    return _validate_host_provider_attestation(
        {**material, "record_id": digest_json(material)},
        machine_user_id=str(runtime_identity["machine_user_id"]),
        host_id=host_id,
    )


def install_host_provider_attestation(
    host_runtime_dir: str | Path,
    *,
    host_id: str,
    provider_attestation: Mapping[str, object],
) -> Mapping[str, object]:
    """Persist the exact host-global provider subset as immutable evidence.

    Execution-local model/config/module identity is intentionally excluded from
    ``provider_identity_material``.  It is sealed separately for each execution;
    the provider generation represents only the account/executable/configuration
    that is genuinely shared by every repository on this machine-user kernel.
    """

    root = require_host_runtime(host_runtime_dir)
    if not runtime_file_lock_is_held(root / "locks" / "host-authority.lock"):
        raise ConfigurationError("provider attestation requires host authority")
    writer = _host_runtime_identity_unlocked(root)
    validated = _validate_host_provider_attestation(
        provider_attestation,
        machine_user_id=str(writer["machine_user_id"]),
        host_id=host_id,
    )
    record_id = str(validated["record_id"])
    path = (
        root
        / "provider-attestations"
        / (record_id.removeprefix("sha256:") + ".json")
    )
    exclusive_write_json_or_identical(path, validated)
    raw = _read_regular_authority_bytes(path, label="host provider attestation")
    if parse_strict_canonical_json_bytes(
        raw,
        label="host provider attestation",
        expected_fields=HOST_PROVIDER_ATTESTATION_FIELDS,
    ) != validated:
        raise ConfigurationError("host provider attestation changed after installation")
    return {
        **validated,
        "evidence_path": str(path.relative_to(root)).replace("\\", "/"),
        "evidence_blob_digest": "sha256:" + sha256(raw).hexdigest(),
    }


def _host_provider_binding(
    host_runtime_dir: Path,
    *,
    host_id: str,
    create: bool = False,
    bound_at: str | None = None,
    provider_identity_source: str | None = None,
    provider_identity_digest: str | None = None,
    provider_attestation: Mapping[str, object] | None = None,
    _history_raw_override: bytes | None = None,
    _allow_pending_history: bool = False,
    _writer_override: Mapping[str, object] | None = None,
) -> Mapping[str, object]:
    """Read or CAS-rotate the authenticated machine-user provider generation."""

    if not isinstance(host_id, str) or not host_id.strip():
        raise ConfigurationError("host provider id is required")
    if _writer_override is None:
        root = require_host_runtime(host_runtime_dir)
        writer = read_strict_canonical_json(
            root / "host-runtime-identity.json",
            label="host-global runtime identity",
            expected_fields=HOST_RUNTIME_IDENTITY_FIELDS,
        )
        writer = _validate_host_runtime_identity(
            writer, machine_user_id=_machine_user_identity()
        )
    else:
        root = _reject_link_components(
            host_runtime_dir, label="host runtime authority"
        ).resolve()
        if create:
            raise ConfigurationError(
                "a recovery writer override cannot mutate provider authority"
            )
        if not runtime_file_lock_is_held(root / "locks" / "host-authority.lock"):
            raise ConfigurationError(
                "provider recovery validation requires host authority"
            )
        writer = _validate_host_runtime_identity(
            _writer_override, machine_user_id=_machine_user_identity()
        )
    path = root / "host-provider.json"
    history_path = root / "host-provider-history.jsonl"

    def validate(value: object) -> Mapping[str, object]:
        if not isinstance(value, Mapping) or frozenset(value) not in {
            HOST_PROVIDER_LEGACY_FIELDS,
            HOST_PROVIDER_FIELDS,
        }:
            raise ConfigurationError("host provider generation schema is ambiguous")
        legacy = frozenset(value) == HOST_PROVIDER_LEGACY_FIELDS
        material = dict(value)
        record_id = material.pop("record_id", None)
        generation_material = {
            "kind": "hive-mind-host-provider-generation-key-v1",
            "machine_user_id": value.get("machine_user_id"),
            "host_id": value.get("host_id"),
            "provider_epoch": value.get("provider_epoch"),
            "provider_identity_source": value.get("provider_identity_source"),
            "provider_identity_digest": value.get("provider_identity_digest"),
        }
        if not legacy:
            generation_material["host_kernel_generation"] = value.get(
                "host_kernel_generation"
            )
        try:
            parse_time(value.get("bound_at"))
        except (TypeError, ValueError) as error:
            raise ConfigurationError("host provider binding time is invalid") from error
        previous_generation = value.get("previous_provider_generation")
        previous_record = value.get("previous_provider_record_id")
        if (
            value.get("schema_version") != 1
            or value.get("kind") != HOST_PROVIDER_BINDING_KIND
            or value.get("machine_user_id") != _machine_user_identity()
            or not isinstance(value.get("host_id"), str)
            or not str(value["host_id"]).strip()
            or type(value.get("provider_epoch")) is not int
            or int(value["provider_epoch"]) < 1
            or value.get("provider_generation") != digest_json(generation_material)
            or not isinstance(value.get("provider_identity_source"), str)
            or not str(value["provider_identity_source"]).strip()
            or AUTHORITY_ID.fullmatch(
                str(value.get("provider_identity_digest"))
            )
            is None
            or ((previous_generation is None) != (previous_record is None))
            or (
                previous_generation is not None
                and (
                    AUTHORITY_ID.fullmatch(str(previous_generation)) is None
                    or AUTHORITY_ID.fullmatch(str(previous_record)) is None
                )
            )
            or (
                not legacy
                and AUTHORITY_ID.fullmatch(
                    str(value.get("host_kernel_generation"))
                )
                is None
            )
            or record_id != digest_json(material)
        ):
            raise ConfigurationError("host provider generation is invalid")
        if not legacy:
            attestation_id = value.get("provider_attestation_record_id")
            attestation_path = value.get("provider_attestation_path")
            attestation_blob = value.get("provider_attestation_blob_digest")
            if (
                AUTHORITY_ID.fullmatch(str(attestation_id)) is None
                or attestation_path
                != "provider-attestations/"
                + str(attestation_id).removeprefix("sha256:")
                + ".json"
                or AUTHORITY_ID.fullmatch(str(attestation_blob)) is None
            ):
                raise ConfigurationError("host provider attestation fence is invalid")
            evidence_path = root / str(attestation_path)
            evidence_raw = _read_regular_authority_bytes(
                evidence_path, label="host provider attestation evidence"
            )
            evidence = parse_strict_canonical_json_bytes(
                evidence_raw,
                label="host provider attestation evidence",
                expected_fields=HOST_PROVIDER_ATTESTATION_FIELDS,
            )
            validated_evidence = _validate_host_provider_attestation(
                evidence,
                machine_user_id=str(value["machine_user_id"]),
                host_id=str(value["host_id"]),
            )
            if (
                validated_evidence.get("record_id") != attestation_id
                or validated_evidence.get("provider_identity_source")
                != value.get("provider_identity_source")
                or validated_evidence.get("provider_identity_digest")
                != value.get("provider_identity_digest")
                or "sha256:" + sha256(evidence_raw).hexdigest() != attestation_blob
            ):
                raise ConfigurationError("host provider attestation evidence changed")
        return dict(value)

    history_records = (
        _strict_jsonl_records_bytes(
            _history_raw_override,
            label="host provider generation history",
        )
        if _history_raw_override is not None
        else (
            strict_jsonl_records(
                history_path, label="host provider generation history"
            )
            if history_path.is_file()
            else ()
        )
    )
    history = tuple(validate(item) for item in history_records)
    previous: Mapping[str, object] | None = None
    for index, item in enumerate(history, 1):
        if previous is None:
            valid_lineage = (
                item.get("provider_epoch") == 1
                and item.get("previous_provider_generation") is None
                and item.get("previous_provider_record_id") is None
            )
        else:
            valid_lineage = (
                item.get("provider_epoch") == int(previous["provider_epoch"]) + 1
                and item.get("previous_provider_generation")
                == previous.get("provider_generation")
                and item.get("previous_provider_record_id")
                == previous.get("record_id")
            )
        if not valid_lineage:
            raise ConfigurationError(
                f"host provider generation history line {index} is non-monotonic"
            )
        previous = item

    current: Mapping[str, object] | None = None
    if path.is_file():
        current_value = read_strict_canonical_json(
            path, label="host provider generation"
        )
        current = validate(current_value)
        if not history:
            raise ConfigurationError("host provider current record has no history")
        if history[-1] != current:
            pending = history[-1]
            if (
                pending.get("previous_provider_generation")
                != current.get("provider_generation")
                or pending.get("previous_provider_record_id")
                != current.get("record_id")
            ):
                raise ConfigurationError(
                    "host provider history diverges from current generation"
                )
    elif history:
        if len(history) != 1:
            raise ConfigurationError(
                "host provider current record is absent after multiple generations"
            )
        current = None
    elif not create:
        raise ConfigurationError("host provider identity is not initialized")

    requested_identity = (
        provider_identity_source,
        provider_identity_digest,
        host_id,
    )
    if current is not None and requested_identity[:2] == (None, None):
        if current.get("host_id") != host_id:
            raise ConfigurationError(
                "host provider differs from the machine-user capacity authority"
            )
        if history[-1] != current and not _allow_pending_history:
            raise ConfigurationError(
                "host provider rotation is incomplete and requires the new provider"
            )
        if current.get("host_kernel_generation") != writer.get(
            "host_kernel_generation"
        ):
            raise ConfigurationError(
                "host provider is bound to a retired host-kernel writer; rotate it explicitly"
            )
        return current
    if not create:
        if (
            current is None
            or current.get("host_id") != host_id
            or current.get("provider_identity_source") != provider_identity_source
            or current.get("provider_identity_digest") != provider_identity_digest
            or history[-1] != current
            or current.get("host_kernel_generation")
            != writer.get("host_kernel_generation")
        ):
            raise ConfigurationError(
                "host provider differs from the machine-user capacity authority"
            )
        return current
    if not runtime_file_lock_is_held(
        root / "locks" / "host-authority.lock"
    ):
        raise ConfigurationError("host provider rotation requires host authority")
    if (
        not isinstance(bound_at, str)
        or not isinstance(provider_identity_source, str)
        or not provider_identity_source.strip()
        or not isinstance(provider_identity_digest, str)
        or AUTHORITY_ID.fullmatch(provider_identity_digest) is None
        or provider_attestation is None
    ):
        raise ConfigurationError(
            "host provider requires authenticated identity provenance"
        )
    try:
        parse_time(bound_at)
    except (TypeError, ValueError) as error:
        raise ConfigurationError("host provider binding time is invalid") from error
    installed_attestation = install_host_provider_attestation(
        root,
        host_id=host_id,
        provider_attestation=provider_attestation,
    )
    if (
        installed_attestation.get("provider_identity_source")
        != provider_identity_source
        or installed_attestation.get("provider_identity_digest")
        != provider_identity_digest
    ):
        raise ConfigurationError(
            "host provider attestation differs from requested provider identity"
        )
    attestation_coordinates = {
        "provider_attestation_record_id": installed_attestation["record_id"],
        "provider_attestation_path": installed_attestation["evidence_path"],
        "provider_attestation_blob_digest": installed_attestation[
            "evidence_blob_digest"
        ],
    }
    if current is not None and all(
        current.get(field) == expected
        for field, expected in {
            "host_id": host_id,
            "provider_identity_source": provider_identity_source,
            "provider_identity_digest": provider_identity_digest,
            "host_kernel_generation": writer["host_kernel_generation"],
            **attestation_coordinates,
        }.items()
    ):
        if history[-1] != current:
            raise ConfigurationError(
                "host provider rotation pending candidate differs from requested identity"
            )
        return current
    if current is not None and any(
        item.get("host_id") == host_id
        and item.get("provider_identity_source") == provider_identity_source
        and item.get("provider_identity_digest") == provider_identity_digest
        and item.get("host_kernel_generation")
        == writer.get("host_kernel_generation")
        for item in history[:-1]
    ):
        raise ConfigurationError("host provider downgrade or replay is prohibited")
    if current is not None:
        latest_reservations: dict[str, Mapping[str, object]] = {}
        for event in _host_reservation_events_unlocked(root):
            latest_reservations[str(event["reservation_id"])] = event
        if any(
            event.get("state") in HOST_RESERVATION_ACTIVE_STATES
            for event in latest_reservations.values()
        ):
            raise ConfigurationError(
                "host provider cannot rotate while reservations remain active or unreconciled"
            )
    pending = history[-1] if history and history[-1] != current else None
    if pending is not None:
        if any(
            pending.get(field) != expected
            for field, expected in {
                "host_id": host_id,
                "provider_identity_source": provider_identity_source,
                "provider_identity_digest": provider_identity_digest,
                "host_kernel_generation": writer["host_kernel_generation"],
                **attestation_coordinates,
            }.items()
        ):
            raise ConfigurationError(
                "host provider pending rotation conflicts with requested identity"
            )
        candidate = pending
    else:
        epoch = 1 if current is None else int(current["provider_epoch"]) + 1
        generation_material = {
            "kind": "hive-mind-host-provider-generation-key-v1",
            "machine_user_id": _machine_user_identity(),
            "host_id": host_id,
            "provider_epoch": epoch,
            "provider_identity_source": provider_identity_source,
            "provider_identity_digest": provider_identity_digest,
            "host_kernel_generation": writer["host_kernel_generation"],
        }
        material: dict[str, object] = {
            "schema_version": 1,
            "kind": HOST_PROVIDER_BINDING_KIND,
            "machine_user_id": _machine_user_identity(),
            "host_id": host_id,
            "provider_generation": digest_json(generation_material),
            "provider_epoch": epoch,
            "provider_identity_source": provider_identity_source,
            "provider_identity_digest": provider_identity_digest,
            "host_kernel_generation": writer["host_kernel_generation"],
            "bound_at": bound_at,
            "previous_provider_generation": (
                current.get("provider_generation") if current is not None else None
            ),
            "previous_provider_record_id": (
                current.get("record_id") if current is not None else None
            ),
            **attestation_coordinates,
        }
        candidate = validate({**material, "record_id": digest_json(material)})
        _append_canonical_jsonl(history_path, candidate)
    atomic_write_json(path, candidate)
    return validate(candidate)


def _validate_codex_app_server_execution_identity(
    value: object,
    *,
    execution_namespace: str,
    execution_id: str,
    host_id: str,
    machine_user_id: str,
    provider_identity_digest: str,
    verify_live_sources: bool = False,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != CODEX_APP_SERVER_IDENTITY_FIELDS:
        raise ConfigurationError("execution adapter identity schema is ambiguous")
    material = dict(value)
    record_id = material.pop("record_id", None)
    try:
        parse_time(value.get("created_at"))
    except (TypeError, ValueError) as error:
        raise ConfigurationError("execution adapter identity time is invalid") from error
    digest_fields = {
        "adapter_module_digest",
        "launcher_digest",
        "executable_digest",
        "schema_bundle_digest",
        "thread_start_schema_digest",
        "turn_start_schema_digest",
        "environment_root_digest",
        "behavior_environment_digest",
        "provider_config_digest",
        "execution_config_digest",
        "account_identity_digest",
        "initialize_result_digest",
    }
    if (
        value.get("schema_version") != 1
        or value.get("kind") != "hive-mind-codex-app-server-identity-v1"
        or value.get("execution_namespace") != execution_namespace
        or value.get("execution_id") != execution_id
        or value.get("host_id") != host_id
        or value.get("machine_user_id") != machine_user_id
        or value.get("provider_identity_digest") != provider_identity_digest
        or any(
            AUTHORITY_ID.fullmatch(str(value.get(field))) is None
            for field in digest_fields
        )
        or not isinstance(value.get("effective_model"), str)
        or not str(value["effective_model"]).strip()
        or not (
            value.get("effective_model_provider") is None
            or (
                isinstance(value.get("effective_model_provider"), str)
                and str(value["effective_model_provider"]).strip()
            )
        )
        or value.get("transport") != "stdio://"
        or record_id != digest_json(material)
    ):
        raise ConfigurationError("execution adapter identity is invalid")
    for path_field, digest_field, optional in (
        ("adapter_module_path", "adapter_module_digest", False),
        ("launcher_path", "launcher_digest", False),
        ("cli_module_path", "cli_module_digest", True),
        ("executable_path", "executable_digest", False),
    ):
        raw_path = value.get(path_field)
        raw_digest = value.get(digest_field)
        if optional and raw_path is None and raw_digest is None:
            continue
        if (
            not isinstance(raw_path, str)
            or not Path(raw_path).is_absolute()
            or AUTHORITY_ID.fullmatch(str(raw_digest)) is None
        ):
            raise ConfigurationError(
                f"execution adapter identity {path_field} provenance is invalid"
            )
        if verify_live_sources:
            source = _reject_link_components(
                raw_path, label=f"execution adapter {path_field}"
            ).resolve()
            source_bytes = _read_regular_authority_bytes(
                source, label=f"execution adapter {path_field}"
            )
            if "sha256:" + sha256(source_bytes).hexdigest() != raw_digest:
                raise ConfigurationError(
                    f"execution adapter identity {path_field} bytes changed"
                )
    return dict(value)


def _validate_execution_adapter_identity_binding(
    host_runtime_dir: Path,
    value: object,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != EXECUTION_ADAPTER_IDENTITY_FIELDS:
        raise ConfigurationError("execution adapter binding schema is ambiguous")
    material = dict(value)
    record_id = material.pop("record_id", None)
    source_record_id = value.get("adapter_identity_record_id")
    source_path = value.get("adapter_identity_source_path")
    source_blob = value.get("adapter_identity_blob_digest")
    if (
        value.get("schema_version") != 1
        or value.get("kind") != EXECUTION_ADAPTER_IDENTITY_KIND
        or EXECUTION_NAMESPACE.fullmatch(
            str(value.get("execution_namespace"))
        )
        is None
        or AUTHORITY_ID.fullmatch(str(value.get("execution_id"))) is None
        or not isinstance(value.get("repository"), str)
        or not str(value["repository"]).strip()
        or not isinstance(value.get("host_id"), str)
        or not str(value["host_id"]).strip()
        or AUTHORITY_ID.fullmatch(str(value.get("provider_generation"))) is None
        or type(value.get("provider_epoch")) is not int
        or int(value["provider_epoch"]) < 1
        or AUTHORITY_ID.fullmatch(
            str(value.get("provider_identity_digest"))
        )
        is None
        or value.get("adapter_identity_kind")
        != "hive-mind-codex-app-server-identity-v1"
        or AUTHORITY_ID.fullmatch(str(source_record_id)) is None
        or source_path
        != "execution-adapter-identities/"
        + str(source_record_id).removeprefix("sha256:")
        + ".json"
        or AUTHORITY_ID.fullmatch(str(source_blob)) is None
        or record_id != digest_json(material)
    ):
        raise ConfigurationError("execution adapter binding is invalid")
    source_file = host_runtime_dir / str(source_path)
    source_raw = _read_regular_authority_bytes(
        source_file, label="execution adapter identity evidence"
    )
    source = parse_strict_canonical_json_bytes(
        source_raw,
        label="execution adapter identity evidence",
        expected_fields=CODEX_APP_SERVER_IDENTITY_FIELDS,
    )
    _validate_codex_app_server_execution_identity(
        source,
        execution_namespace=str(value["execution_namespace"]),
        execution_id=str(value["execution_id"]),
        host_id=str(value["host_id"]),
        machine_user_id=_machine_user_identity(),
        provider_identity_digest=str(value["provider_identity_digest"]),
    )
    if (
        source.get("record_id") != source_record_id
        or "sha256:" + sha256(source_raw).hexdigest() != source_blob
    ):
        raise ConfigurationError("execution adapter identity evidence changed")
    return dict(value)


def install_execution_adapter_identity(
    host_runtime_dir: str | Path,
    *,
    repo_root: str | Path,
    execution_dir: str | Path,
    execution_namespace: str,
    execution_id: str,
    host_id: str,
    adapter_identity_path: str | Path,
    adapter_identity: Mapping[str, object],
) -> Mapping[str, object]:
    """Seal the exact execution-local adapter identity into host evidence."""

    root = require_host_runtime(host_runtime_dir)
    if not runtime_file_lock_is_held(root / "locks" / "host-authority.lock"):
        raise ConfigurationError("execution adapter installation requires host authority")
    execution = require_execution_authority_dir(
        repo_root,
        execution_dir,
        execution_id=execution_id,
        execution_namespace=execution_namespace,
    )
    source_path = _reject_link_components(
        adapter_identity_path, label="execution adapter identity source"
    ).resolve()
    expected_source = (
        execution / "host" / "codex-app-server-v1" / "identity.json"
    ).resolve()
    if source_path != expected_source:
        raise ConfigurationError(
            "execution adapter identity must come from the authenticated execution root"
        )
    source_raw = _read_regular_authority_bytes(
        source_path, label="execution adapter identity source"
    )
    source = parse_strict_canonical_json_bytes(
        source_raw,
        label="execution adapter identity source",
        expected_fields=CODEX_APP_SERVER_IDENTITY_FIELDS,
    )
    if source != adapter_identity:
        raise ConfigurationError("execution adapter identity differs from installed bytes")
    provider = _host_provider_binding(root, host_id=host_id)
    execution_manifest = read_strict_canonical_json(
        execution / "execution-identity.json",
        label="execution namespace identity",
    )
    repository = (
        execution_manifest.get("repository")
        if isinstance(execution_manifest, Mapping)
        else None
    )
    validated_source = _validate_codex_app_server_execution_identity(
        source,
        execution_namespace=execution_namespace,
        execution_id=execution_id,
        host_id=host_id,
        machine_user_id=_machine_user_identity(),
        provider_identity_digest=str(provider["provider_identity_digest"]),
        verify_live_sources=True,
    )
    source_record_id = str(validated_source["record_id"])
    installed_source = (
        root
        / "execution-adapter-identities"
        / (source_record_id.removeprefix("sha256:") + ".json")
    )
    exclusive_write_bytes_or_identical(installed_source, source_raw)
    material: dict[str, object] = {
        "schema_version": 1,
        "kind": EXECUTION_ADAPTER_IDENTITY_KIND,
        "execution_namespace": execution_namespace,
        "execution_id": execution_id,
        "repository": repository,
        "host_id": host_id,
        "provider_generation": provider["provider_generation"],
        "provider_epoch": provider["provider_epoch"],
        "provider_identity_digest": provider["provider_identity_digest"],
        "adapter_identity_kind": validated_source["kind"],
        "adapter_identity_record_id": source_record_id,
        "adapter_identity_blob_digest": "sha256:" + sha256(source_raw).hexdigest(),
        "adapter_identity_source_path": str(
            installed_source.relative_to(root)
        ).replace("\\", "/"),
    }
    binding = {**material, "record_id": digest_json(material)}
    binding_path = (
        root
        / "execution-adapter-bindings"
        / (str(binding["record_id"]).removeprefix("sha256:") + ".json")
    )
    exclusive_write_json_or_identical(binding_path, binding)
    return _validate_execution_adapter_identity_binding(root, binding)


def read_execution_adapter_identity(
    host_runtime_dir: str | Path,
    record_id: str,
) -> Mapping[str, object]:
    """Dereference one immutable adapter binding under caller-held host authority."""

    root = require_host_runtime(host_runtime_dir)
    if not runtime_file_lock_is_held(root / "locks" / "host-authority.lock"):
        raise ConfigurationError("execution adapter read requires host authority")
    if AUTHORITY_ID.fullmatch(record_id) is None:
        raise ConfigurationError("execution adapter identity id is invalid")
    path = (
        root
        / "execution-adapter-bindings"
        / (record_id.removeprefix("sha256:") + ".json")
    )
    value = read_strict_canonical_json(
        path,
        label="execution adapter binding",
        expected_fields=EXECUTION_ADAPTER_IDENTITY_FIELDS,
    )
    validated = _validate_execution_adapter_identity_binding(root, value)
    if validated.get("record_id") != record_id:
        raise ConfigurationError("execution adapter binding id is mismatched")
    return validated


def _host_repository_registry_events(
    host_runtime_dir: str | Path,
    *,
    raw_override: bytes | None = None,
) -> tuple[Mapping[str, object], ...]:
    path = Path(host_runtime_dir) / "repository-registry.jsonl"
    if raw_override is None and not path.exists() and not _is_link_like(path):
        return ()
    if raw_override is None:
        _reject_link_components(path, label="host repository registry")
        if not path.is_file():
            raise ConfigurationError("host repository registry is not a regular file")
        raw = _read_regular_authority_bytes(path, label="host repository registry")
    else:
        raw = raw_override
    records = _strict_jsonl_records_bytes(raw, label="host repository registry")
    legacy_fields = {
        "schema_version",
        "kind",
        "repository",
        "transport_digest",
        "coordination_dir",
        "bound_at",
        "previous_event_id",
        "event_id",
    }
    current_fields = legacy_fields | {"checkout_roots"}
    kernel_fields = current_fields | {"host_kernel_generation"}
    previous: str | None = None
    seen: dict[str, Mapping[str, object]] = {}
    seen_transport: dict[str, Mapping[str, object]] = {}
    events: list[Mapping[str, object]] = []
    for index, event in enumerate(records, 1):
        material = dict(event)
        event_id = material.pop("event_id", None)
        if (
            frozenset(event)
            not in {
                frozenset(legacy_fields),
                frozenset(current_fields),
                frozenset(kernel_fields),
            }
            or event.get("schema_version") != 1
            or event.get("kind")
            not in {
                "hive-mind-host-repository-binding-v1",
                "hive-mind-host-repository-binding-v2",
                "hive-mind-host-repository-binding-v3",
            }
            or (
                event.get("kind") == "hive-mind-host-repository-binding-v1"
                and set(event) != legacy_fields
            )
            or (
                event.get("kind") == "hive-mind-host-repository-binding-v2"
                and set(event) != current_fields
            )
            or (
                event.get("kind") == "hive-mind-host-repository-binding-v3"
                and set(event) != kernel_fields
            )
            or (
                event.get("kind") == "hive-mind-host-repository-binding-v3"
                and AUTHORITY_ID.fullmatch(
                    str(event.get("host_kernel_generation"))
                )
                is None
            )
            or not isinstance(event.get("repository"), str)
            or not str(event.get("repository")).strip()
            or not isinstance(event.get("transport_digest"), str)
            or AUTHORITY_ID.fullmatch(str(event.get("transport_digest"))) is None
            or not isinstance(event.get("coordination_dir"), str)
            or not Path(str(event.get("coordination_dir"))).is_absolute()
            or event.get("previous_event_id") != previous
            or event_id != digest_json(material)
        ):
            raise ConfigurationError(
                f"host repository registry line {index} is invalid"
            )
        repository = str(event["repository"])
        transport_digest = str(event["transport_digest"])
        try:
            parse_time(event.get("bound_at"))
        except (TypeError, ValueError) as error:
            raise ConfigurationError(
                f"host repository registry line {index} time is invalid"
            ) from error
        try:
            canonical_coordination = _reject_link_components(
                str(event["coordination_dir"]),
                label="host repository registry coordination root",
            ).resolve()
        except (OSError, RuntimeError) as error:
            raise ConfigurationError(
                f"host repository registry line {index} path is invalid"
            ) from error
        if str(canonical_coordination) != event.get("coordination_dir"):
            raise ConfigurationError(
                f"host repository registry line {index} path is noncanonical"
            )
        checkout_roots = event.get("checkout_roots", [])
        if (
            not isinstance(checkout_roots, list)
            or checkout_roots != sorted(set(checkout_roots))
        ):
            raise ConfigurationError(
                f"host repository registry line {index} checkout roots are invalid"
            )
        for checkout in checkout_roots:
            if not isinstance(checkout, str) or not Path(checkout).is_absolute():
                raise ConfigurationError(
                    f"host repository registry line {index} checkout root is invalid"
                )
            canonical_checkout = _reject_link_components(
                checkout, label="host repository registry checkout root"
            ).resolve()
            if str(canonical_checkout) != checkout:
                raise ConfigurationError(
                    f"host repository registry line {index} checkout root is noncanonical"
                )
        prior = seen.get(repository)
        if prior is not None and (
            prior.get("coordination_dir") != event.get("coordination_dir")
            or prior.get("transport_digest") != event.get("transport_digest")
            or not set(prior.get("checkout_roots", [])) <= set(checkout_roots)
        ):
            raise ConfigurationError(
                "host repository registry contains split coordination roots"
            )
        transport_prior = seen_transport.get(transport_digest)
        if transport_prior is not None and (
            transport_prior.get("repository") != repository
            or transport_prior.get("coordination_dir")
            != event.get("coordination_dir")
        ):
            raise ConfigurationError(
                "host repository registry aliases one Git transport to multiple authorities"
            )
        seen[repository] = event
        seen_transport[transport_digest] = event
        previous = str(event_id)
        events.append(event)
    return tuple(events)


def bind_host_repository_runtime(
    host_runtime_dir: str | Path,
    *,
    repository: str,
    transport_digest: str,
    coordination_dir: str | Path,
    bound_at: str,
    repo_root: str | Path | None = None,
) -> Mapping[str, object]:
    """CAS-bind every clone of one sealed repository identity to one arbiter."""

    root = require_host_runtime(host_runtime_dir)
    if not runtime_file_lock_is_held(root / "locks" / "host-authority.lock"):
        raise ConfigurationError("repository registry binding requires host authority")
    writer = _host_runtime_identity_unlocked(root)
    if (
        not repository.strip()
        or not isinstance(transport_digest, str)
        or AUTHORITY_ID.fullmatch(transport_digest) is None
    ):
        raise ConfigurationError("repository registry identity is required")
    try:
        parse_time(bound_at)
    except (TypeError, ValueError) as error:
        raise ConfigurationError("repository registry binding time is invalid") from error
    directory = _reject_link_components(
        coordination_dir, label="repository coordination root"
    ).resolve()
    checkout = repo_root
    if checkout is None and directory.name == "state" and directory.parent.name == ".autopilot":
        checkout = directory.parent.parent
    if checkout is None:
        raise ConfigurationError(
            "repository registry binding requires an authenticated checkout root"
        )
    checkout_root = _reject_link_components(
        checkout, label="repository registry checkout root"
    ).resolve()
    identity = runtime_repository_identity(checkout_root)
    if (
        identity is None
        or identity.get("repository") != repository
        or identity.get("transport_digest") != transport_digest
    ):
        raise ConfigurationError(
            "repository registry checkout differs from sealed repository transport"
        )
    events = list(_host_repository_registry_events(root))
    existing = next(
        (
            event
            for event in reversed(events)
            if event.get("repository") == repository
            or event.get("transport_digest") == transport_digest
        ),
        None,
    )
    if existing is not None:
        if (
            existing.get("repository") != repository
            or
            existing.get("coordination_dir") != str(directory)
            or existing.get("transport_digest") != transport_digest
        ):
            raise ConfigurationError(
                "sealed repository identity is already bound to another coordination root"
            )
        roots = sorted(
            set(str(item) for item in existing.get("checkout_roots", []))
            | {str(checkout_root)}
        )
        if (
            roots == existing.get("checkout_roots")
            and existing.get("host_kernel_generation")
            == writer.get("host_kernel_generation")
        ):
            return existing
    else:
        roots = [str(checkout_root)]
    material: dict[str, object] = {
        "schema_version": 1,
        "kind": "hive-mind-host-repository-binding-v3",
        "repository": repository,
        "transport_digest": transport_digest,
        "coordination_dir": str(directory),
        "checkout_roots": roots,
        "host_kernel_generation": writer["host_kernel_generation"],
        "bound_at": bound_at,
        "previous_event_id": events[-1]["event_id"] if events else None,
    }
    event = {**material, "event_id": digest_json(material)}
    _append_canonical_jsonl(root / "repository-registry.jsonl", event)
    return event


def host_repository_registry_bindings(
    host_runtime_dir: str | Path,
) -> tuple[Mapping[str, object], ...]:
    """Return the authenticated repository registry under host authority."""

    root = require_host_runtime(host_runtime_dir)
    if not runtime_file_lock_is_held(root / "locks" / "host-authority.lock"):
        raise ConfigurationError(
            "host repository inventory requires caller-held host authority"
        )
    latest: dict[str, Mapping[str, object]] = {}
    for event in _host_repository_registry_events(root):
        latest[str(event["repository"])] = event
    return tuple(latest[key] for key in sorted(latest))


def _host_key(host_id: str) -> str:
    if not isinstance(host_id, str) or not host_id.strip():
        raise ConfigurationError("host capacity requires a stable host id")
    return digest_json({"kind": "hive-mind-host-key-v1", "host_id": host_id})


def host_capacity_path(host_runtime_dir: str | Path, host_id: str) -> Path:
    key = _host_key(host_id).removeprefix("sha256:")
    return Path(host_runtime_dir).resolve() / "hosts" / key / "capacity.json"


def validate_host_capacity(
    value: object,
    *,
    host_id: str,
    now: datetime,
    require_live: bool = True,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ConfigurationError("host capacity is missing or malformed")
    field_set = frozenset(value)
    if field_set not in {HOST_CAPACITY_LEGACY_FIELDS, HOST_CAPACITY_FIELDS}:
        raise ConfigurationError("host capacity schema is ambiguous")
    legacy = field_set == HOST_CAPACITY_LEGACY_FIELDS
    material = dict(value)
    record_id = material.pop("record_id")
    if (
        value.get("schema_version") != 1
        or value.get("kind") != HOST_CAPACITY_KIND
        or value.get("host_id") != host_id
        or AUTHORITY_ID.fullmatch(str(value.get("provider_generation"))) is None
        or type(value.get("provider_epoch")) is not int
        or int(value["provider_epoch"]) < 1
        or (
            not legacy
            and AUTHORITY_ID.fullmatch(
                str(value.get("host_kernel_generation"))
            )
            is None
        )
        or record_id != digest_json(material)
    ):
        raise ConfigurationError("host capacity identity or digest is invalid")
    generation = value.get("capacity_generation")
    capability_digest = value.get("capability_digest")
    if (
        not isinstance(generation, str)
        or AUTHORITY_ID.fullmatch(generation) is None
        or not isinstance(capability_digest, str)
        or AUTHORITY_ID.fullmatch(capability_digest) is None
    ):
        raise ConfigurationError("host capacity generation is invalid")
    if type(value.get("capacity_epoch")) is not int or int(value["capacity_epoch"]) < 1:
        raise ConfigurationError("host capacity epoch is invalid")
    for field in ("max_total_sessions", "validation_slots"):
        number = value.get(field)
        if type(number) is not int or number < 0:
            raise ConfigurationError(f"host capacity {field} is invalid")
    if int(value["max_total_sessions"]) < 1:
        raise ConfigurationError("host capacity must admit at least one session")
    if int(value["validation_slots"]) > int(value["max_total_sessions"]):
        raise ConfigurationError("validation capacity cannot exceed total capacity")
    if type(value.get("declarative")) is not bool:
        raise ConfigurationError("host capacity provenance classification is invalid")
    if value.get("declarative") is True and (
        int(value["max_total_sessions"]) > 1
        or int(value["validation_slots"]) > 1
    ):
        raise ConfigurationError(
            "declarative capacity has no external ceiling evidence and is limited to one"
        )
    if not isinstance(value.get("capability_source"), str) or not value.get(
        "capability_source"
    ):
        raise ConfigurationError("host capacity capability source is required")
    try:
        issued = parse_time(value.get("issued_at"))
        expires = parse_time(value.get("expires_at"))
    except (TypeError, ValueError) as error:
        raise ConfigurationError("host capacity time bounds are malformed") from error
    if expires <= issued or (
        require_live and (issued > now or expires <= now)
    ):
        raise ConfigurationError("host capacity generation is stale or not yet valid")
    return dict(value)


def _read_host_capacity_record(
    host_runtime_dir: str | Path,
    host_id: str,
    *,
    now: datetime,
    require_live: bool,
    require_current_provider: bool = True,
    _writer_override: Mapping[str, object] | None = None,
) -> Mapping[str, object]:
    root = (
        require_host_runtime(host_runtime_dir)
        if _writer_override is None
        else _reject_link_components(
            host_runtime_dir, label="host runtime authority"
        ).resolve()
    )
    provider = _host_provider_binding(
        root, host_id=host_id, _writer_override=_writer_override
    )
    path = host_capacity_path(root, host_id)
    if not path.is_file() or _is_link_like(path):
        raise ConfigurationError("authenticated host capacity is missing")
    try:
        raw = _read_regular_authority_bytes(path, label="authenticated host capacity")
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_json_pairs,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ConfigurationError("authenticated host capacity is malformed") from error
    if not isinstance(value, Mapping) or raw != (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8"):
        raise ConfigurationError("authenticated host capacity is noncanonical")
    validated = validate_host_capacity(
        value, host_id=host_id, now=now, require_live=require_live
    )
    current_provider = (
        validated.get("provider_generation") == provider.get("provider_generation")
        and validated.get("provider_epoch") == provider.get("provider_epoch")
        and validated.get("host_kernel_generation")
        == provider.get("host_kernel_generation")
    )
    immediate_predecessor = (
        validated.get("provider_generation")
        == provider.get("previous_provider_generation")
        and validated.get("provider_epoch") == int(provider["provider_epoch"]) - 1
    )
    if not current_provider and (require_current_provider or not immediate_predecessor):
        raise ConfigurationError(
            "host capacity is fenced by a retired provider generation"
        )
    return validated


def read_host_capacity(
    host_runtime_dir: str | Path,
    host_id: str,
    *,
    now: datetime,
) -> Mapping[str, object]:
    """Read capacity for admission; expired generations fail closed."""

    return _read_host_capacity_record(
        host_runtime_dir, host_id, now=now, require_live=True
    )


def read_host_capacity_predecessor_for_writer_rotation(
    host_runtime_dir: str | Path,
    host_id: str,
    *,
    now: datetime,
) -> Mapping[str, object]:
    """Read an exact retired-writer capacity predecessor for successor CAS.

    This is deliberately not an admission read.  It requires current host-writer
    authority, authenticates the replaceable projection against the complete
    append-only history, and permits the provider/kernel coordinates to be stale
    only so ``publish_host_capacity`` can rotate them.  Callers must never return
    this record as live capacity or attempt same-generation renewal with it.
    """

    root = require_host_runtime(host_runtime_dir)
    if not runtime_file_lock_is_held(root / "locks" / "host-authority.lock"):
        raise ConfigurationError(
            "capacity predecessor rotation read requires host authority"
        )
    writer = _host_runtime_identity_unlocked(root)
    path = host_capacity_path(root, host_id)
    if not path.is_file() or _is_link_like(path):
        raise ConfigurationError("capacity predecessor projection is unavailable")
    value = read_strict_canonical_json(
        path, label="capacity predecessor projection"
    )
    predecessor = validate_host_capacity(
        value,
        host_id=host_id,
        now=now,
        require_live=False,
    )
    history_path = path.parent / "capacity-history.jsonl"
    if not history_path.is_file() or _is_link_like(history_path):
        raise ConfigurationError("capacity predecessor has no append-only history")
    history = _strict_capacity_history(history_path)
    if (
        not history
        or history[-1].get("capacity_record_id") != predecessor.get("record_id")
    ):
        raise ConfigurationError(
            "capacity predecessor differs from its append-only history"
        )
    if predecessor.get("host_kernel_generation") == writer.get(
        "host_kernel_generation"
    ):
        raise ConfigurationError(
            "current-writer capacity must use ordinary admission or renewal reads"
        )
    return predecessor


def publish_host_capacity(
    host_runtime_dir: str | Path,
    *,
    host_id: str,
    capacity_generation: str,
    capacity_epoch: int,
    max_total_sessions: int,
    validation_slots: int,
    issued_at: str,
    expires_at: str,
    capability_source: str,
    capability_digest: str,
    provider_identity_source: str,
    provider_identity_digest: str,
    provider_attestation: Mapping[str, object],
    declarative: bool,
    now: datetime,
    expected_generation: str | None,
) -> Mapping[str, object]:
    root = require_host_runtime(host_runtime_dir)
    lock_path = root / "locks" / "host-authority.lock"
    if not runtime_file_lock_is_held(lock_path):
        raise ConfigurationError("host capacity publication requires host authority")
    provider = _host_provider_binding(
        root,
        host_id=host_id,
        create=True,
        bound_at=issued_at,
        provider_identity_source=provider_identity_source,
        provider_identity_digest=provider_identity_digest,
        provider_attestation=provider_attestation,
    )
    material: dict[str, object] = {
        "schema_version": 1,
        "kind": HOST_CAPACITY_KIND,
        "host_id": host_id,
        "provider_generation": provider["provider_generation"],
        "provider_epoch": provider["provider_epoch"],
        "host_kernel_generation": provider["host_kernel_generation"],
        "capacity_generation": capacity_generation,
        "capacity_epoch": capacity_epoch,
        "max_total_sessions": max_total_sessions,
        "validation_slots": validation_slots,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "capability_source": capability_source,
        "capability_digest": capability_digest,
        "declarative": declarative,
    }
    material["record_id"] = digest_json(material)
    requested = validate_host_capacity(material, host_id=host_id, now=now)
    path = host_capacity_path(root, host_id)
    history_path = path.parent / "capacity-history.jsonl"
    history = _strict_capacity_history(history_path) if history_path.is_file() else ()
    current: Mapping[str, object] | None = None
    predecessor_terminal_event_ids: list[str] = []
    rotation_reason = "INITIAL"
    if path.is_file():
        # CAS must authenticate historical bytes even after their admission
        # window expires. Public ``read_host_capacity`` remains live-only.
        current = _read_host_capacity_record(
            root,
            host_id,
            now=now,
            require_live=False,
            require_current_provider=False,
        )
        if isinstance(current, Mapping) and current.get("capacity_generation") == capacity_generation:
            if (
                history
                and history[-1].get("capacity_generation") == capacity_generation
                and history[-1].get("capacity_record_id")
                != current.get("record_id")
            ):
                raise ConfigurationError(
                    "host capacity history has a pending same-generation renewal"
                )
            stable_fields = set(current) - {"issued_at", "expires_at", "record_id"}
            if any(current.get(field) != requested.get(field) for field in stable_fields):
                raise ConfigurationError("host capacity generation conflicts with installed bytes")
            return dict(current)
        if expected_generation != current.get("capacity_generation"):
            raise ConfigurationError("host capacity compare-and-swap generation mismatch")
        if int(requested["capacity_epoch"]) != int(current["capacity_epoch"]) + 1:
            raise ConfigurationError("host capacity epoch must advance exactly once")
        reservation_events = _host_reservation_events_unlocked(root)
        predecessor_latest: dict[str, Mapping[str, object]] = {}
        for reservation_event in reservation_events:
            if (
                reservation_event.get("host_id") == host_id
                and reservation_event.get("capacity_generation")
                == current.get("capacity_generation")
            ):
                predecessor_latest[str(reservation_event["reservation_id"])] = (
                    reservation_event
                )
        if any(
            item.get("state") in HOST_RESERVATION_ACTIVE_STATES
            for item in predecessor_latest.values()
        ):
            raise ConfigurationError(
                "host capacity generation cannot rotate while reservations remain active"
            )
        for predecessor in predecessor_latest.values():
            if predecessor.get("reservation_kind") == "VALIDATION":
                evidence_type = predecessor.get(
                    "validation_terminal_evidence_type"
                )
                if (
                    predecessor.get("state") != "RELEASED"
                    or evidence_type not in {"TERMINAL_LEASE", "NEVER_ACQUIRED"}
                    or not isinstance(
                        predecessor.get("validation_terminal_evidence_id"), str
                    )
                    or not isinstance(
                        predecessor.get("validation_terminal_evidence_path"), str
                    )
                    or not isinstance(
                        predecessor.get("validation_terminal_evidence_blob_digest"),
                        str,
                    )
                    or predecessor.get("external_cancellation")
                    != (
                        "CONFIRMED_VALIDATION_TERMINAL"
                        if evidence_type == "TERMINAL_LEASE"
                        else "CONFIRMED_VALIDATION_NEVER_ACQUIRED"
                    )
                ):
                    raise ConfigurationError(
                        "validation capacity predecessor lacks authenticated terminal evidence"
                    )
            elif predecessor.get("state") == "RELEASED":
                terminal_release = (
                    predecessor.get("lifecycle_state") == "TERMINAL"
                    and predecessor.get("external_cancellation")
                    == "CONFIRMED_TERMINAL"
                    and isinstance(
                        predecessor.get("local_terminal_event_id"), str
                    )
                )
                pre_launch_abort = (
                    predecessor.get("external_cancellation")
                    == "CONFIRMED_NEVER_LAUNCHED"
                    and predecessor.get("pre_launch_abort_state")
                    == "NEVER_LAUNCHED"
                    and isinstance(
                        predecessor.get("pre_launch_abort_receipt_id"), str
                    )
                    and isinstance(
                        predecessor.get("pre_launch_abort_receipt_path"), str
                    )
                    and isinstance(
                        predecessor.get("pre_launch_abort_receipt_blob_digest"),
                        str,
                    )
                    and isinstance(
                        predecessor.get("pre_launch_abort_release_id"), str
                    )
                    and type(
                        predecessor.get("pre_launch_abort_admission_epoch")
                    )
                    is int
                )
                if not (terminal_release or pre_launch_abort):
                    raise ConfigurationError(
                        "host capacity predecessor release lacks authenticated terminal evidence"
                    )
            elif predecessor.get("state") == "EXPIRED_FENCED":
                if (
                    predecessor.get("lifecycle_state")
                    not in HOST_LIFECYCLE_TERMINAL_STATES
                    or not isinstance(
                        predecessor.get("lifecycle_observation_id"), str
                    )
                    or not isinstance(
                        predecessor.get("local_terminal_event_id"), str
                    )
                ):
                    raise ConfigurationError(
                        "expired host capacity predecessor lacks lifecycle reconciliation"
                    )
            else:
                raise ConfigurationError(
                    "host capacity predecessor has no recognized terminal disposition"
                )
        predecessor_terminal_event_ids = sorted(
            str(item["event_id"]) for item in predecessor_latest.values()
        )
        rotation_reason = (
            "EXPIRED_GENERATION_RECONCILED"
            if parse_time(current.get("expires_at")) <= now
            else "CAPABILITY_ROTATION"
        )
    elif expected_generation is not None or capacity_epoch != 1:
        raise ConfigurationError("first host capacity generation requires epoch one and no CAS")
    prior_event_id = str(history[-1]["event_id"]) if history else None
    predecessor_generation = (
        current.get("capacity_generation") if current is not None else None
    )
    pending_history = (
        history[-1]
        if history
        and history[-1].get("capacity_generation") == capacity_generation
        and history[-1].get("previous_capacity_generation")
        == predecessor_generation
        else None
    )
    validated = requested
    if pending_history is not None:
        sealed_candidate = pending_history.get("capacity_record")
        if sealed_candidate is None:
            if pending_history.get("capacity_record_id") != requested.get("record_id"):
                pending_history = None
        else:
            sealed = validate_host_capacity(
                sealed_candidate,
                host_id=host_id,
                now=now,
                require_live=False,
            )
            if pending_history.get("capacity_record_id") != sealed.get("record_id"):
                raise ConfigurationError(
                    "host capacity pending history candidate digest is invalid"
                )
            stable_fields = set(sealed) - {"issued_at", "expires_at", "record_id"}
            if any(sealed.get(field) != requested.get(field) for field in stable_fields):
                raise ConfigurationError(
                    "host capacity retry conflicts with the sealed pending candidate"
                )
            validated = sealed
    if history and pending_history is None:
        installed_generation = (
            current.get("capacity_generation") if current is not None else None
        )
        if (
            history[-1].get("capacity_generation") != installed_generation
            or (
                current is not None
                and history[-1].get("capacity_record_id")
                != current.get("record_id")
            )
        ):
            raise ConfigurationError(
                "host capacity history is ahead of current state with an ambiguous transition"
            )
    history_material: dict[str, object] = {
        "schema_version": 1,
        "kind": HOST_CAPACITY_HISTORY_KIND,
        "host_id": host_id,
        "provider_generation": validated["provider_generation"],
        "provider_epoch": validated["provider_epoch"],
        "host_kernel_generation": validated["host_kernel_generation"],
        "capacity_generation": capacity_generation,
        "capacity_epoch": capacity_epoch,
        "capacity_record_id": validated["record_id"],
        "capacity_record": dict(validated),
        "previous_capacity_generation": (
            current.get("capacity_generation") if current is not None else None
        ),
        "recorded_at": format_time(now),
        "rotation_reason": rotation_reason,
        "previous_capacity_expires_at": (
            current.get("expires_at") if current is not None else None
        ),
        "predecessor_terminal_event_ids": predecessor_terminal_event_ids,
        "previous_event_id": prior_event_id,
    }
    history_event = {
        **history_material,
        "event_id": digest_json(history_material),
    }
    if pending_history is None:
        _append_canonical_jsonl(history_path, history_event)
    atomic_write_json(path, validated)
    return validated


def _append_canonical_jsonl(path: Path, value: Mapping[str, object]) -> None:
    """Durably append one canonical record and its directory entry."""

    absolute = _absolute_without_resolving(path)
    absolute.parent.mkdir(parents=True, exist_ok=True)
    _reject_link_components(absolute.parent, label="host append-only ledger directory")
    if absolute.exists() or _is_link_like(absolute):
        _reject_link_components(absolute, label="host append-only ledger path")
        if not absolute.is_file():
            raise ConfigurationError("host append-only ledger is not a regular file")
    encoded = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_APPEND
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_BINARY", 0)
    )
    descriptor = os.open(absolute, flags, 0o600)
    try:
        _verify_open_regular_file_identity(
            descriptor,
            absolute,
            label="host append-only ledger",
        )
        offset = 0
        while offset < len(encoded):
            written = os.write(descriptor, encoded[offset:])
            if written <= 0:
                raise ConfigurationError("host append-only ledger write made no progress")
            offset += written
        os.fsync(descriptor)
        _verify_open_regular_file_identity(
            descriptor,
            absolute,
            label="host append-only ledger",
        )
    finally:
        os.close(descriptor)
    _fsync_parent_directory(absolute.parent)


def _verify_open_regular_file_identity(
    descriptor: int,
    path: Path,
    *,
    label: str,
) -> None:
    """Prove an opened authority handle still names the requested non-link path.

    ``O_NOFOLLOW`` is unavailable on some supported Windows Python builds and it
    does not protect parent components on any platform.  The before/after link
    walk plus the opened-handle/path identity comparison closes both the final
    component link and rename/junction swap windows.  A platform that cannot
    expose a stable file identity fails closed rather than appending elsewhere.
    """

    absolute = _reject_link_components(path, label=label)
    try:
        opened = os.fstat(descriptor)
        named = os.stat(absolute, follow_symlinks=False)
    except OSError as error:
        raise ConfigurationError(f"cannot authenticate opened {label}: {error}") from error
    if not stat.S_ISREG(opened.st_mode) or not stat.S_ISREG(named.st_mode):
        raise ConfigurationError(f"{label} is not a regular file")
    opened_identity = (opened.st_dev, opened.st_ino)
    named_identity = (named.st_dev, named.st_ino)
    if (
        opened_identity != named_identity
        or any(type(item) is not int or item <= 0 for item in opened_identity)
    ):
        raise ConfigurationError(f"opened {label} no longer names the requested path")


def _strict_capacity_history(
    path: Path,
    *,
    raw_override: bytes | None = None,
) -> tuple[Mapping[str, object], ...]:
    try:
        raw = (
            raw_override
            if raw_override is not None
            else _read_regular_authority_bytes(path, label="host capacity history")
        )
        records = _strict_jsonl_records_bytes(
            raw, label="host capacity history"
        )
    except (OSError, ConfigurationError) as error:
        raise ConfigurationError(f"cannot read host capacity history: {error}") from error
    legacy_fields = {
        "schema_version",
        "kind",
        "host_id",
        "provider_generation",
        "provider_epoch",
        "capacity_generation",
        "capacity_epoch",
        "capacity_record_id",
        "previous_capacity_generation",
        "recorded_at",
        "previous_event_id",
        "event_id",
    }
    rotation_fields = legacy_fields | {
        "rotation_reason",
        "previous_capacity_expires_at",
        "predecessor_terminal_event_ids",
    }
    candidate_fields = rotation_fields | {"capacity_record"}
    renewal_fields = candidate_fields | {
        "previous_capacity_record_id",
        "active_reservation_event_ids",
        "renewal_actor",
    }
    current_legacy_fields = legacy_fields | {"host_kernel_generation"}
    current_rotation_fields = rotation_fields | {"host_kernel_generation"}
    current_candidate_fields = candidate_fields | {"host_kernel_generation"}
    current_renewal_fields = renewal_fields | {"host_kernel_generation"}
    rotation_schemas = {
        frozenset(rotation_fields),
        frozenset(candidate_fields),
        frozenset(renewal_fields),
        frozenset(current_rotation_fields),
        frozenset(current_candidate_fields),
        frozenset(current_renewal_fields),
    }
    candidate_schemas = {
        frozenset(candidate_fields),
        frozenset(renewal_fields),
        frozenset(current_candidate_fields),
        frozenset(current_renewal_fields),
    }
    renewal_schemas = {
        frozenset(renewal_fields),
        frozenset(current_renewal_fields),
    }
    prior_event: str | None = None
    prior_generation: str | None = None
    prior_capacity_record_id: str | None = None
    prior_epoch = 0
    events: list[Mapping[str, object]] = []
    for index, value in enumerate(records, 1):
        field_set = frozenset(value)
        if field_set not in {
            frozenset(legacy_fields),
            frozenset(rotation_fields),
            frozenset(candidate_fields),
            frozenset(renewal_fields),
            frozenset(current_legacy_fields),
            frozenset(current_rotation_fields),
            frozenset(current_candidate_fields),
            frozenset(current_renewal_fields),
        }:
            raise ConfigurationError(
                f"host capacity history line {index} schema is invalid"
            )
        material = dict(value)
        event_id = material.pop("event_id", None)
        rotation_reason = value.get("rotation_reason")
        same_policy_renewal = rotation_reason == "SAME_POLICY_RENEWAL"
        expected_epoch = prior_epoch if same_policy_renewal else prior_epoch + 1
        if (
            value.get("schema_version") != 1
            or value.get("kind") != HOST_CAPACITY_HISTORY_KIND
            or value.get("previous_event_id") != prior_event
            or value.get("previous_capacity_generation") != prior_generation
            or AUTHORITY_ID.fullmatch(str(value.get("provider_generation"))) is None
            or type(value.get("provider_epoch")) is not int
            or int(value["provider_epoch"]) < 1
            or (
                "host_kernel_generation" in value
                and AUTHORITY_ID.fullmatch(
                    str(value.get("host_kernel_generation"))
                )
                is None
            )
            or type(value.get("capacity_epoch")) is not int
            or int(value["capacity_epoch"]) != expected_epoch
            or (
                same_policy_renewal
                and (
                    prior_generation is None
                    or value.get("capacity_generation") != prior_generation
                )
            )
            or event_id != digest_json(material)
        ):
            raise ConfigurationError(
                f"host capacity history line {index} lineage is invalid"
            )
        if field_set in rotation_schemas:
            if (
                value.get("rotation_reason")
                not in {
                    "INITIAL",
                    "CAPABILITY_ROTATION",
                    "EXPIRED_GENERATION_RECONCILED",
                    "SAME_POLICY_RENEWAL",
                }
                or not isinstance(
                    value.get("predecessor_terminal_event_ids"), list
                )
                or not all(
                    isinstance(item, str) and AUTHORITY_ID.fullmatch(item)
                    for item in value["predecessor_terminal_event_ids"]
                )
                or (
                    value.get("previous_capacity_generation") is None
                    and (
                        value.get("rotation_reason") != "INITIAL"
                        or value.get("previous_capacity_expires_at") is not None
                        or value.get("predecessor_terminal_event_ids") != []
                    )
                )
                or (
                    value.get("previous_capacity_generation") is not None
                    and (
                        not isinstance(
                            value.get("previous_capacity_expires_at"), str
                        )
                        or value.get("rotation_reason") == "INITIAL"
                    )
                )
                or (
                    value.get("rotation_reason") == "SAME_POLICY_RENEWAL"
                    and field_set not in renewal_schemas
                )
            ):
                raise ConfigurationError(
                    f"host capacity history line {index} rotation receipt is invalid"
                )
        if field_set in renewal_schemas:
            if (
                value.get("rotation_reason") != "SAME_POLICY_RENEWAL"
                or AUTHORITY_ID.fullmatch(
                    str(value.get("previous_capacity_record_id"))
                )
                is None
                or value.get("previous_capacity_record_id")
                != prior_capacity_record_id
                or not isinstance(value.get("active_reservation_event_ids"), list)
                or not all(
                    isinstance(item, str) and AUTHORITY_ID.fullmatch(item)
                    for item in value["active_reservation_event_ids"]
                )
                or len(set(value["active_reservation_event_ids"]))
                != len(value["active_reservation_event_ids"])
                or not isinstance(value.get("renewal_actor"), str)
                or not str(value["renewal_actor"]).strip()
            ):
                raise ConfigurationError(
                    f"host capacity history line {index} renewal evidence is invalid"
                )
        if field_set in candidate_schemas:
            candidate = validate_host_capacity(
                value.get("capacity_record"),
                host_id=str(value.get("host_id")),
                now=datetime.max.replace(tzinfo=UTC),
                require_live=False,
            )
            if (
                candidate.get("capacity_generation")
                != value.get("capacity_generation")
                or candidate.get("capacity_epoch") != value.get("capacity_epoch")
                or candidate.get("provider_generation")
                != value.get("provider_generation")
                or candidate.get("provider_epoch") != value.get("provider_epoch")
                or candidate.get("host_kernel_generation")
                != value.get("host_kernel_generation")
                or candidate.get("record_id") != value.get("capacity_record_id")
            ):
                raise ConfigurationError(
                    f"host capacity history line {index} candidate is invalid"
                )
        prior_event = str(event_id)
        prior_generation = str(value["capacity_generation"])
        prior_capacity_record_id = str(value["capacity_record_id"])
        prior_epoch = int(value["capacity_epoch"])
        events.append(value)
    return tuple(events)


def _strict_canonical_json_line(line: str, *, label: str) -> Mapping[str, object]:
    try:
        value = json.loads(
            line,
            object_pairs_hook=_strict_json_pairs,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise ConfigurationError(f"{label} is malformed") from error
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{label} must be an object")
    if line != json.dumps(
        value, ensure_ascii=False, sort_keys=True, allow_nan=False
    ):
        raise ConfigurationError(f"{label} is noncanonical")
    return value


def _host_reservation_path(host_runtime_dir: str | Path) -> Path:
    return Path(host_runtime_dir).resolve() / "host-reservations.jsonl"


def _host_scheduler_path(host_runtime_dir: str | Path) -> Path:
    return Path(host_runtime_dir).resolve() / "host-scheduler.jsonl"


def _host_scheduler_events_unlocked(
    host_runtime_dir: str | Path,
    *,
    raw_override: bytes | None = None,
) -> tuple[Mapping[str, object], ...]:
    path = _host_scheduler_path(host_runtime_dir)
    if raw_override is None and not path.is_file():
        return ()
    raw = (
        raw_override
        if raw_override is not None
        else _read_regular_authority_bytes(path, label="host scheduler ledger")
    )
    records = _strict_jsonl_records_bytes(raw, label="host scheduler ledger")
    fields = {
        "schema_version",
        "kind",
        "state",
        "host_id",
        "host_kernel_generation",
        "capacity_generation",
        "payload",
        "actor",
        "recorded_at",
        "previous_event_id",
        "event_id",
    }
    previous: str | None = None
    events: list[Mapping[str, object]] = []
    demand_ids: set[str] = set()
    demands: dict[str, Mapping[str, object]] = {}
    grant_ids: set[str] = set()
    expired_ids: set[str] = set()
    for index, event in enumerate(records, 1):
        material = dict(event)
        event_id = material.pop("event_id", None)
        state = event.get("state")
        payload = event.get("payload")
        try:
            parse_time(event.get("recorded_at"))
        except (TypeError, ValueError) as error:
            raise ConfigurationError(
                f"host scheduler ledger line {index} time is invalid"
            ) from error
        if (
            set(event) != fields
            or event.get("schema_version") != 1
            or event.get("kind") != HOST_SCHEDULER_EVENT_KIND
            or state not in HOST_SCHEDULER_EVENT_STATES
            or not isinstance(event.get("host_id"), str)
            or not str(event["host_id"]).strip()
            or AUTHORITY_ID.fullmatch(
                str(event.get("host_kernel_generation"))
            )
            is None
            or AUTHORITY_ID.fullmatch(str(event.get("capacity_generation")))
            is None
            or not isinstance(event.get("actor"), str)
            or not str(event["actor"]).strip()
            or event.get("previous_event_id") != previous
            or event_id != digest_json(material)
            or not isinstance(payload, Mapping)
        ):
            raise ConfigurationError(
                f"host scheduler ledger line {index} is invalid"
            )
        try:
            if state == "DEMAND":
                if set(payload) != {"demand"} or not isinstance(
                    payload.get("demand"), Mapping
                ):
                    raise host_scheduler_policy.HostSchedulerError(
                        "host scheduling demand payload is invalid"
                    )
                demand = host_scheduler_policy.validate_demand(payload["demand"])
                demand_id = str(demand["demand_id"])
                if demand_id in demand_ids:
                    raise host_scheduler_policy.HostSchedulerError(
                        "host scheduling demand is duplicated"
                    )
                if any(
                    demand.get(field) != event.get(field)
                    for field in (
                        "host_id",
                        "host_kernel_generation",
                        "capacity_generation",
                    )
                ):
                    raise host_scheduler_policy.HostSchedulerError(
                        "host scheduling demand envelope differs"
                    )
                demand_ids.add(demand_id)
                demands[demand_id] = demand
            elif state == "GRANT":
                if set(payload) != {"schedule", "grants"} or not isinstance(
                    payload.get("schedule"), Mapping
                ) or not isinstance(payload.get("grants"), list):
                    raise host_scheduler_policy.HostSchedulerError(
                        "host scheduling grant payload is invalid"
                    )
                schedule = host_scheduler_policy.validate_schedule(
                    payload["schedule"]
                )
                if any(
                    str(item) not in demand_ids
                    for item in schedule["demand_ids"]
                ):
                    raise host_scheduler_policy.HostSchedulerError(
                        "host scheduling grant cites an unknown demand"
                    )
                grants_by_demand: dict[str, int] = {}
                for raw_grant in payload["grants"]:
                    if not isinstance(raw_grant, Mapping):
                        raise host_scheduler_policy.HostSchedulerError(
                            "host scheduling grant is not an object"
                        )
                    grant = host_scheduler_policy.validate_grant(raw_grant)
                    grant_id = str(grant["grant_id"])
                    if grant_id in grant_ids or str(grant["demand_id"]) not in demand_ids:
                        raise host_scheduler_policy.HostSchedulerError(
                            "host scheduling grant is duplicated or orphaned"
                        )
                    if any(
                        grant.get(field) != event.get(field)
                        for field in (
                            "host_id",
                            "host_kernel_generation",
                            "capacity_generation",
                        )
                    ) or grant.get("schedule_id") != schedule.get("schedule_id"):
                        raise host_scheduler_policy.HostSchedulerError(
                            "host scheduling grant envelope differs"
                        )
                    demand = demands[str(grant["demand_id"])]
                    if (
                        grant.get("execution_id") != demand.get("execution_id")
                        or grant.get("local_reservation_id")
                        not in demand.get("candidate_reservation_ids", ())
                        or parse_time(grant.get("expires_at"))
                        <= parse_time(grant.get("issued_at"))
                    ):
                        raise host_scheduler_policy.HostSchedulerError(
                            "host scheduling grant differs from its demand"
                        )
                    grants_by_demand[str(grant["demand_id"])] = (
                        grants_by_demand.get(str(grant["demand_id"]), 0) + 1
                    )
                    grant_ids.add(grant_id)
                expected_counts = {
                    str(row["demand_id"]): int(row["slots"])
                    for row in schedule["grants"]
                }
                if grants_by_demand != expected_counts:
                    raise host_scheduler_policy.HostSchedulerError(
                        "host scheduling grant tokens differ from allocation"
                    )
            else:
                if (
                    set(payload) != {"grant_ids", "reason"}
                    or not isinstance(payload.get("grant_ids"), list)
                    or not payload["grant_ids"]
                    or len(payload["grant_ids"]) != len(set(payload["grant_ids"]))
                    or any(
                        AUTHORITY_ID.fullmatch(str(item)) is None
                        or str(item) not in grant_ids
                        or str(item) in expired_ids
                        for item in payload["grant_ids"]
                    )
                    or not isinstance(payload.get("reason"), str)
                    or not str(payload["reason"]).strip()
                ):
                    raise host_scheduler_policy.HostSchedulerError(
                        "host scheduling expiry payload is invalid"
                    )
                expired_ids.update(str(item) for item in payload["grant_ids"])
        except host_scheduler_policy.HostSchedulerError as error:
            raise ConfigurationError(
                f"host scheduler ledger line {index} is invalid: {error}"
            ) from error
        previous = str(event_id)
        events.append(event)
    return tuple(events)


def _append_host_scheduler_event_unlocked(
    host_runtime_dir: str | Path,
    *,
    state: str,
    host_id: str,
    host_kernel_generation: str,
    capacity_generation: str,
    payload: Mapping[str, object],
    actor: str,
    recorded_at: str,
    events: Sequence[Mapping[str, object]],
) -> Mapping[str, object]:
    material: dict[str, object] = {
        "schema_version": 1,
        "kind": HOST_SCHEDULER_EVENT_KIND,
        "state": state,
        "host_id": host_id,
        "host_kernel_generation": host_kernel_generation,
        "capacity_generation": capacity_generation,
        "payload": dict(payload),
        "actor": actor,
        "recorded_at": recorded_at,
        "previous_event_id": events[-1]["event_id"] if events else None,
    }
    event = {**material, "event_id": digest_json(material)}
    _append_canonical_jsonl(_host_scheduler_path(host_runtime_dir), event)
    return event


def _host_scheduler_projection_unlocked(
    host_runtime_dir: str | Path,
    *,
    host_id: str,
) -> Mapping[str, object]:
    events = list(_host_scheduler_events_unlocked(host_runtime_dir))
    demands: dict[str, Mapping[str, object]] = {}
    grants: dict[str, Mapping[str, object]] = {}
    expired: set[str] = set()
    cursor: str | None = None
    for event in events:
        payload = event["payload"]
        assert isinstance(payload, Mapping)
        if event["state"] == "DEMAND":
            demand = payload["demand"]
            assert isinstance(demand, Mapping)
            demands[str(demand["demand_id"])] = demand
        elif event["state"] == "GRANT":
            schedule = payload["schedule"]
            assert isinstance(schedule, Mapping)
            raw_cursor = schedule.get("cursor_execution_id")
            cursor = str(raw_cursor) if raw_cursor is not None else cursor
            for grant in payload["grants"]:
                assert isinstance(grant, Mapping)
                grants[str(grant["grant_id"])] = grant
        else:
            expired.update(str(item) for item in payload["grant_ids"])
    consumed = {
        str(event["host_scheduler_grant_id"])
        for event in _host_reservation_events_unlocked(host_runtime_dir)
        if event.get("host_scheduler_grant_id") is not None
    }
    unknown = consumed - set(grants)
    if unknown:
        raise ConfigurationError(
            "host reservation ledger consumes an unknown scheduler grant"
        )
    outstanding = {
        grant_id: grant
        for grant_id, grant in grants.items()
        if grant_id not in expired and grant_id not in consumed
    }
    active_grant_ids = set(grants) - expired
    remaining_candidates: dict[str, list[str]] = {}
    for demand_id, demand in demands.items():
        allocated = {
            str(grant["local_reservation_id"])
            for grant_id, grant in grants.items()
            if str(grant["demand_id"]) == demand_id
            and grant_id in active_grant_ids
        }
        remaining_candidates[demand_id] = [
            str(item)
            for item in demand["candidate_reservation_ids"]
            if str(item) not in allocated
        ]
    return {
        "events": events,
        "demands": demands,
        "grants": grants,
        "expired_grant_ids": expired,
        "consumed_grant_ids": consumed,
        "outstanding_grants": outstanding,
        "remaining_candidates": remaining_candidates,
        "cursor_execution_id": cursor,
        "host_id": host_id,
    }


def record_host_scheduler_demand(
    host_runtime_dir: str | Path,
    *,
    host_id: str,
    repository: str,
    repository_transport_digest: str,
    execution_namespace: str,
    execution_id: str,
    plan_fingerprint: str,
    capacity_generation: str,
    execution_adapter_identity: Mapping[str, object],
    candidate_reservation_ids: Sequence[str],
    weight: int,
    actor: str,
    recorded_at: str,
) -> Mapping[str, object]:
    """Persist one exact execution demand under caller-held host authority."""

    root = require_host_runtime(host_runtime_dir)
    if not runtime_file_lock_is_held(root / "locks" / "host-authority.lock"):
        raise ConfigurationError("host scheduler demand requires host authority")
    if not isinstance(actor, str) or not actor.strip():
        raise ConfigurationError("host scheduler demand actor is required")
    try:
        recorded = parse_time(recorded_at)
    except (TypeError, ValueError) as error:
        raise ConfigurationError("host scheduler demand time is invalid") from error
    writer = _host_runtime_identity_unlocked(root)
    capacity = read_host_capacity(root, host_id, now=recorded)
    if capacity.get("capacity_generation") != capacity_generation:
        raise ConfigurationError("host scheduler demand capacity is stale")
    adapter_record_id = str(execution_adapter_identity.get("record_id"))
    installed_adapter = read_execution_adapter_identity(root, adapter_record_id)
    adapter_path = (
        root
        / "execution-adapter-bindings"
        / (adapter_record_id.removeprefix("sha256:") + ".json")
    )
    adapter_raw = _read_regular_authority_bytes(
        adapter_path, label="host scheduler execution adapter"
    )
    if (
        installed_adapter != execution_adapter_identity
        or installed_adapter.get("execution_namespace") != execution_namespace
        or installed_adapter.get("execution_id") != execution_id
        or installed_adapter.get("host_id") != host_id
        or installed_adapter.get("repository") != repository
    ):
        raise ConfigurationError("host scheduler demand adapter fence differs")
    projection = _host_scheduler_projection_unlocked(root, host_id=host_id)
    open_demands = [
        demand
        for demand_id, demand in projection["demands"].items()
        if demand.get("execution_id") == execution_id
        and projection["remaining_candidates"].get(demand_id)
    ]
    candidate_ids = list(candidate_reservation_ids)
    stable = {
        "repository": repository,
        "repository_transport_digest": repository_transport_digest,
        "execution_namespace": execution_namespace,
        "execution_id": execution_id,
        "plan_fingerprint": plan_fingerprint,
        "host_kernel_generation": writer["host_kernel_generation"],
        "capacity_generation": capacity_generation,
        "execution_adapter_identity_record_id": adapter_record_id,
        "execution_adapter_identity_path": str(adapter_path.relative_to(root)).replace(
            "\\", "/"
        ),
        "execution_adapter_identity_blob_digest": "sha256:"
        + sha256(adapter_raw).hexdigest(),
        "candidate_reservation_ids": candidate_ids,
        "requested_slots": len(candidate_ids),
        "weight": weight,
    }
    for existing in open_demands:
        if all(existing.get(field) == value for field, value in stable.items()):
            return existing
        if set(existing.get("candidate_reservation_ids", ())) & set(candidate_ids):
            raise ConfigurationError(
                "execution has overlapping outstanding host scheduling demands"
            )
    demand = host_scheduler_policy.make_demand(
        host_id=host_id,
        repository=repository,
        repository_transport_digest=repository_transport_digest,
        execution_namespace=execution_namespace,
        execution_id=execution_id,
        plan_fingerprint=plan_fingerprint,
        host_kernel_generation=str(writer["host_kernel_generation"]),
        capacity_generation=capacity_generation,
        execution_adapter_identity_record_id=adapter_record_id,
        execution_adapter_identity_path=str(adapter_path.relative_to(root)).replace(
            "\\", "/"
        ),
        execution_adapter_identity_blob_digest="sha256:"
        + sha256(adapter_raw).hexdigest(),
        candidate_reservation_ids=candidate_ids,
        requested_slots=len(candidate_ids),
        weight=weight,
        enqueued_epoch=1
        + sum(event.get("state") == "DEMAND" for event in projection["events"]),
    )
    events = list(projection["events"])
    _append_host_scheduler_event_unlocked(
        root,
        state="DEMAND",
        host_id=host_id,
        host_kernel_generation=str(writer["host_kernel_generation"]),
        capacity_generation=capacity_generation,
        payload={"demand": demand},
        actor=actor,
        recorded_at=recorded_at,
        events=events,
    )
    return demand


def grant_host_scheduler_capacity(
    host_runtime_dir: str | Path,
    *,
    host_id: str,
    actor: str,
    now: datetime,
    grant_seconds: int = 300,
) -> Mapping[str, object]:
    """Expire unused grants and issue a deterministic work-conserving schedule."""

    root = require_host_runtime(host_runtime_dir)
    if not runtime_file_lock_is_held(root / "locks" / "host-authority.lock"):
        raise ConfigurationError("host scheduler grant requires host authority")
    if (
        not isinstance(actor, str)
        or not actor.strip()
        or type(grant_seconds) is not int
        or not 1 <= grant_seconds <= 900
    ):
        raise ConfigurationError("host scheduler grant lifetime is invalid")
    writer = _host_runtime_identity_unlocked(root)
    capacity = read_host_capacity(root, host_id, now=now)
    projection = _host_scheduler_projection_unlocked(root, host_id=host_id)
    events = list(projection["events"])
    expired_now = sorted(
        grant_id
        for grant_id, grant in projection["outstanding_grants"].items()
        if parse_time(grant["expires_at"]) <= now
    )
    if expired_now:
        event = _append_host_scheduler_event_unlocked(
            root,
            state="EXPIRY",
            host_id=host_id,
            host_kernel_generation=str(writer["host_kernel_generation"]),
            capacity_generation=str(capacity["capacity_generation"]),
            payload={
                "grant_ids": expired_now,
                "reason": "unused scheduler grant reached its sealed expiry",
            },
            actor=actor,
            recorded_at=format_time(now),
            events=events,
        )
        events.append(event)
        projection = _host_scheduler_projection_unlocked(root, host_id=host_id)
    active = active_global_host_reservations(root)
    unexpired_outstanding = {
        grant_id: grant
        for grant_id, grant in projection["outstanding_grants"].items()
        if parse_time(grant["expires_at"]) > now
    }
    available = max(
        0,
        int(capacity["max_total_sessions"])
        - len(active)
        - len(unexpired_outstanding),
    )
    current_demands = [
        demand
        for demand_id, demand in projection["demands"].items()
        if projection["remaining_candidates"].get(demand_id)
        and demand.get("host_id") == host_id
        and demand.get("host_kernel_generation")
        == writer.get("host_kernel_generation")
        and demand.get("capacity_generation")
        == capacity.get("capacity_generation")
    ]
    remaining_counts = {
        str(demand["demand_id"]): len(
            projection["remaining_candidates"][str(demand["demand_id"])]
        )
        for demand in current_demands
    }
    if current_demands:
        schedule = host_scheduler_policy.weighted_round_robin(
            current_demands,
            available_slots=available,
            cursor_execution_id=projection["cursor_execution_id"],
            remaining_slots_by_demand_id=remaining_counts,
        )
    else:
        schedule = host_scheduler_policy.weighted_round_robin(
            [], available_slots=0, cursor_execution_id=None
        )
    new_grants: list[Mapping[str, object]] = []
    if schedule["grants"]:
        expiry = min(
            parse_time(capacity["expires_at"]),
            now + timedelta(seconds=grant_seconds),
        )
        new_grants = host_scheduler_policy.make_grant_tokens(
            schedule,
            current_demands,
            remaining_candidates_by_demand_id=projection["remaining_candidates"],
            issued_at=format_time(now),
            expires_at=format_time(expiry),
        )
        _append_host_scheduler_event_unlocked(
            root,
            state="GRANT",
            host_id=host_id,
            host_kernel_generation=str(writer["host_kernel_generation"]),
            capacity_generation=str(capacity["capacity_generation"]),
            payload={"schedule": schedule, "grants": new_grants},
            actor=actor,
            recorded_at=format_time(now),
            events=list(projection["events"]),
        )
        projection = _host_scheduler_projection_unlocked(root, host_id=host_id)
    return {
        "schedule": schedule,
        "new_grants": list(new_grants),
        "outstanding_grants": list(projection["outstanding_grants"].values()),
        "scheduler_event_id": (
            projection["events"][-1]["event_id"]
            if projection["events"]
            else None
        ),
    }


def host_scheduler_observation(
    host_runtime_dir: str | Path,
    *,
    host_id: str,
    execution_id: str,
) -> Mapping[str, object]:
    """Return a digest-bound read-only wake observation under the host lock."""

    root = require_host_runtime(host_runtime_dir)
    if not runtime_file_lock_is_held(root / "locks" / "host-authority.lock"):
        raise ConfigurationError("host scheduler observation requires host authority")
    projection = _host_scheduler_projection_unlocked(root, host_id=host_id)
    open_demand_ids = sorted(
        demand_id
        for demand_id, demand in projection["demands"].items()
        if demand.get("execution_id") == execution_id
        and projection["remaining_candidates"].get(demand_id)
    )
    outstanding_grant_ids = sorted(
        grant_id
        for grant_id, grant in projection["outstanding_grants"].items()
        if grant.get("execution_id") == execution_id
    )
    material: dict[str, object] = {
        "kind": "hive-mind-host-scheduler-observation-v1",
        "host_id": host_id,
        "execution_id": execution_id,
        "event_id": (
            projection["events"][-1]["event_id"]
            if projection["events"]
            else None
        ),
        "open_demand_ids": open_demand_ids,
        "outstanding_grant_ids": outstanding_grant_ids,
    }
    return {**material, "observation_id": digest_json(material)}


def _validate_pre_launch_abort_receipt(
    value: Mapping[str, object],
    *,
    reservation: Mapping[str, object],
) -> Mapping[str, object]:
    if set(value) != PRE_LAUNCH_ABORT_FIELDS:
        raise ConfigurationError("pre-launch abort receipt schema is ambiguous")
    material = dict(value)
    record_id = material.pop("record_id", None)
    try:
        parse_time(value.get("recorded_at"))
    except (TypeError, ValueError) as error:
        raise ConfigurationError("pre-launch abort receipt time is invalid") from error
    empty_activity = {
        "active_write_launch_reservation_ids": [],
        "active_host_reservation_ids": [],
        "host_effect_obligation_ids": [],
    }
    if (
        value.get("schema_version") != 1
        or value.get("kind") != PRE_LAUNCH_ABORT_KIND
        or value.get("state") != "NEVER_LAUNCHED"
        or value.get("reason")
        != "DISPATCH_ADMISSION_ABORTED_BEFORE_LAUNCH"
        or any(value.get(field) != [] for field in empty_activity)
        or value.get("empty_activity_digest") != digest_json(empty_activity)
        or EXECUTION_NAMESPACE.fullmatch(
            str(value.get("execution_namespace"))
        )
        is None
        or AUTHORITY_ID.fullmatch(str(value.get("release_id"))) is None
        or AUTHORITY_ID.fullmatch(str(value.get("release_admission_id"))) is None
        or AUTHORITY_ID.fullmatch(str(value.get("intent_record_id"))) is None
        or type(value.get("admission_epoch")) is not int
        or int(value["admission_epoch"]) < 1
        or not isinstance(value.get("node_id"), str)
        or not str(value["node_id"]).strip()
        or not isinstance(value.get("actor"), str)
        or not str(value["actor"]).strip()
        or record_id != digest_json(material)
        or any(
            value.get(field) != reservation.get(field)
            for field in (
                "execution_id",
                "repository",
                "reservation_id",
                "local_reservation_id",
                "resource_key",
                "host_id",
                "provider_generation",
                "capacity_generation",
            )
        )
    ):
        raise ConfigurationError("pre-launch abort receipt is invalid")
    return dict(value)


def _validation_terminal_evidence_path(
    host_runtime_dir: str | Path, reservation_id: str
) -> Path:
    if AUTHORITY_ID.fullmatch(reservation_id) is None:
        raise ConfigurationError("validation reservation id is invalid")
    return (
        Path(host_runtime_dir).resolve()
        / "validation-terminal-receipts"
        / (reservation_id.removeprefix("sha256:") + ".json")
    )


def _validate_validation_terminal_lease(
    value: Mapping[str, object],
    *,
    reservation: Mapping[str, object],
) -> Mapping[str, object]:
    base_fields = {
        "schema_version",
        "node_id",
        "owner",
        "target_sha",
        "acquired_at",
        "expires_at",
        "renewal_count",
        "status",
        "execution_id",
        "validation_resource_key",
        "authority_nonce",
        "claim_id",
        "claim_authority_class",
        "launch_instruction_id",
        "resource_key",
        "authority_epoch",
        "release_id",
        "transaction_sha",
        "host_reservation_id",
        "capacity_host_id",
        "capacity_generation",
        "lease_id",
    }
    optional = {"renewed_at"}
    if value.get("status") == "RELEASED":
        optional |= {"released_at"}
        required_terminal = {"released_at"}
    elif value.get("status") == "EXPIRED_BROKEN":
        optional |= {"broken_by", "broken_at"}
        required_terminal = {"broken_by", "broken_at"}
    else:
        raise ConfigurationError("validation terminal lease is not terminal")
    if not base_fields.issubset(value) or not required_terminal.issubset(value):
        raise ConfigurationError("validation terminal lease lacks required fields")
    if not set(value).issubset(base_fields | optional):
        raise ConfigurationError("validation terminal lease schema is ambiguous")
    try:
        acquired_at = parse_time(value.get("acquired_at"))
        expires_at = parse_time(value.get("expires_at"))
        terminal_at = parse_time(
            value.get("released_at")
            if value.get("status") == "RELEASED"
            else value.get("broken_at")
        )
        renewed_at = (
            parse_time(value.get("renewed_at"))
            if "renewed_at" in value
            else None
        )
    except (TypeError, ValueError) as error:
        raise ConfigurationError("validation terminal lease time is invalid") from error
    if (
        value.get("schema_version") != SCHEMA_VERSION
        or reservation.get("reservation_kind") != "VALIDATION"
        or value.get("execution_id") != reservation.get("execution_id")
        or value.get("host_reservation_id") != reservation.get("reservation_id")
        or value.get("capacity_host_id") != reservation.get("host_id")
        or value.get("capacity_generation")
        != reservation.get("capacity_generation")
        or value.get("validation_resource_key") != reservation.get("resource_key")
        or AUTHORITY_ID.fullmatch(str(value.get("lease_id"))) is None
        or AUTHORITY_ID.fullmatch(str(value.get("release_id"))) is None
        or FULL_SHA.fullmatch(str(value.get("transaction_sha"))) is None
        or not isinstance(value.get("owner"), str)
        or not str(value["owner"]).strip()
        or not isinstance(value.get("node_id"), str)
        or not str(value["node_id"]).strip()
        or type(value.get("renewal_count")) is not int
        or int(value["renewal_count"]) < 0
        or (int(value["renewal_count"]) == 0) != (renewed_at is None)
        or expires_at <= acquired_at
        or terminal_at < acquired_at
        or (
            value.get("status") == "EXPIRED_BROKEN"
            and terminal_at < expires_at
        )
        or (renewed_at is not None and renewed_at < acquired_at)
        or not isinstance(value.get("authority_nonce"), str)
        or len(str(value["authority_nonce"])) != 64
        or re.fullmatch(r"[0-9a-f]{64}", str(value["authority_nonce"])) is None
    ):
        raise ConfigurationError("validation terminal lease fence is invalid")
    return dict(value)


def _validate_validation_never_acquired_receipt(
    value: Mapping[str, object],
    *,
    reservation: Mapping[str, object],
) -> Mapping[str, object]:
    if set(value) != VALIDATION_NEVER_ACQUIRED_FIELDS:
        raise ConfigurationError("validation never-acquired receipt schema is ambiguous")
    material = dict(value)
    record_id = material.pop("record_id", None)
    try:
        parse_time(value.get("recorded_at"))
    except (TypeError, ValueError) as error:
        raise ConfigurationError(
            "validation never-acquired receipt time is invalid"
        ) from error
    if (
        value.get("schema_version") != 1
        or value.get("kind") != VALIDATION_NEVER_ACQUIRED_KIND
        or value.get("state") != "NEVER_ACQUIRED"
        or value.get("execution_id") != reservation.get("execution_id")
        or value.get("repository") != reservation.get("repository")
        or value.get("reservation_id") != reservation.get("reservation_id")
        or value.get("local_reservation_id")
        != reservation.get("local_reservation_id")
        or value.get("resource_key") != reservation.get("resource_key")
        or value.get("validation_resource_key") != reservation.get("resource_key")
        or value.get("host_id") != reservation.get("host_id")
        or value.get("provider_generation")
        != reservation.get("provider_generation")
        or value.get("capacity_generation")
        != reservation.get("capacity_generation")
        or EXECUTION_NAMESPACE.fullmatch(
            str(value.get("execution_namespace"))
        )
        is None
        or AUTHORITY_ID.fullmatch(str(value.get("release_id"))) is None
        or FULL_SHA.fullmatch(str(value.get("transaction_sha"))) is None
        or not isinstance(value.get("node_id"), str)
        or not str(value["node_id"]).strip()
        or not isinstance(value.get("owner"), str)
        or not str(value["owner"]).strip()
        or value.get("reason")
        != "VALIDATION_LEASE_ACQUIRE_FAILED_BEFORE_AUTHORITY"
        or not isinstance(value.get("actor"), str)
        or not str(value["actor"]).strip()
        or record_id != digest_json(material)
    ):
        raise ConfigurationError("validation never-acquired receipt is invalid")
    return dict(value)


def _validate_validation_terminal_receipt(
    value: Mapping[str, object],
    *,
    reservation: Mapping[str, object],
) -> Mapping[str, object]:
    if set(value) != VALIDATION_TERMINAL_RECEIPT_FIELDS:
        raise ConfigurationError("validation terminal receipt schema is ambiguous")
    material = dict(value)
    record_id = material.pop("record_id", None)
    terminal = value.get("terminal_lease")
    if not isinstance(terminal, Mapping):
        raise ConfigurationError("validation terminal receipt lease is malformed")
    validated_terminal = _validate_validation_terminal_lease(
        terminal,
        reservation=reservation,
    )
    terminal_bytes = (
        json.dumps(
            validated_terminal,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    try:
        parse_time(value.get("recorded_at"))
    except (TypeError, ValueError) as error:
        raise ConfigurationError("validation terminal receipt time is invalid") from error
    if (
        value.get("schema_version") != 1
        or value.get("kind") != VALIDATION_TERMINAL_RECEIPT_KIND
        or value.get("state") != "TERMINAL_LEASE"
        or value.get("execution_id") != reservation.get("execution_id")
        or value.get("repository") != reservation.get("repository")
        or value.get("reservation_id") != reservation.get("reservation_id")
        or value.get("local_reservation_id")
        != reservation.get("local_reservation_id")
        or value.get("resource_key") != reservation.get("resource_key")
        or value.get("validation_resource_key") != reservation.get("resource_key")
        or value.get("host_id") != reservation.get("host_id")
        or value.get("provider_generation")
        != reservation.get("provider_generation")
        or value.get("capacity_generation")
        != reservation.get("capacity_generation")
        or EXECUTION_NAMESPACE.fullmatch(
            str(value.get("execution_namespace"))
        )
        is None
        or value.get("release_id") != validated_terminal.get("release_id")
        or value.get("transaction_sha")
        != validated_terminal.get("transaction_sha")
        or value.get("lease_id") != validated_terminal.get("lease_id")
        or value.get("terminal_status") != validated_terminal.get("status")
        or value.get("terminal_lease_blob_digest")
        != "sha256:" + sha256(terminal_bytes).hexdigest()
        or record_id != digest_json(material)
    ):
        raise ConfigurationError("validation terminal receipt is invalid")
    return dict(value)


def _validation_never_acquired_source_path(
    execution_dir: str | Path,
    reservation_id: str,
) -> Path:
    if AUTHORITY_ID.fullmatch(reservation_id) is None:
        raise ConfigurationError("validation reservation id is invalid")
    return (
        Path(execution_dir).resolve()
        / "va"
        / (reservation_id.removeprefix("sha256:") + ".json")
    )


def _verify_validation_release_evidence_cut(
    *,
    repo_root: str | Path,
    coordination_dir: str | Path,
    execution_dir: str | Path,
    execution_id: str,
    execution_namespace: str,
    reservation: Mapping[str, object],
    terminal_lease: Mapping[str, object] | None,
    never_acquired_receipt: Mapping[str, object] | None,
) -> tuple[Mapping[str, object], str]:
    """Derive validation release authority under the complete negative/terminal cut."""

    if (terminal_lease is None) == (never_acquired_receipt is None):
        raise ConfigurationError(
            "validation release requires exactly one terminal or never-acquired receipt"
        )
    if reservation.get("reservation_kind") != "VALIDATION":
        raise ConfigurationError("validation evidence cannot release another reservation kind")
    repository_root = _reject_link_components(
        repo_root, label="validation reservation repository root"
    ).resolve()
    coordination = _reject_link_components(
        coordination_dir, label="validation reservation coordination root"
    ).resolve()
    execution = require_execution_authority_dir(
        repository_root,
        execution_dir,
        execution_id=execution_id,
        execution_namespace=execution_namespace,
    )
    if execution.parents[1] != coordination:
        raise ConfigurationError(
            "validation reservation execution does not belong to coordination root"
        )
    validation_path = (
        coordination
        / "arbiter"
        / "validation-leases"
        / (str(reservation["resource_key"]).removeprefix("sha256:") + ".json")
    )
    with runtime_file_lock(
        coordination / "arbiter" / "locks" / "arbiter-authority.lock",
        timeout_seconds=120.0,
    ):
        with runtime_file_lock(
            execution / "locks" / "dispatcher-admission.lock",
            timeout_seconds=120.0,
        ):
            with runtime_file_lock(
                coordination / "arbiter" / "locks" / "claim-authority.lock",
                timeout_seconds=120.0,
            ):
                with runtime_file_lock(
                    coordination
                    / "arbiter"
                    / "locks"
                    / "global-validation-lease.lock",
                    timeout_seconds=120.0,
                ):
                    active: Mapping[str, object] | None = None
                    if validation_path.is_file():
                        candidate = read_strict_canonical_json(
                            validation_path,
                            label="active keyed validation lease",
                        )
                        if not isinstance(candidate, Mapping):
                            raise ConfigurationError(
                                "active keyed validation lease is malformed"
                            )
                        active = candidate
                    archive_roots = (
                        execution / "validation-leases",
                        coordination / "validation-leases",
                    )
                    matching_archives: list[tuple[Path, Mapping[str, object]]] = []
                    for archive_root in archive_roots:
                        if not archive_root.is_dir():
                            continue
                        for archive_path in sorted(archive_root.glob("*.json")):
                            candidate = read_strict_canonical_json(
                                archive_path,
                                label="keyed validation terminal archive",
                            )
                            if not isinstance(candidate, Mapping):
                                raise ConfigurationError(
                                    "keyed validation terminal archive is malformed"
                                )
                            if candidate.get("host_reservation_id") == reservation.get(
                                "reservation_id"
                            ):
                                matching_archives.append((archive_path, candidate))
                    if terminal_lease is not None:
                        validated = _validate_validation_terminal_lease(
                            terminal_lease,
                            reservation=reservation,
                        )
                        if (
                            active is not None
                            and active.get("host_reservation_id")
                            == reservation.get("reservation_id")
                        ):
                            raise ConfigurationError(
                                "validation lease remains active during terminal host release"
                            )
                        if not matching_archives or not any(
                            archived == validated
                            for _path, archived in matching_archives
                        ):
                            raise ConfigurationError(
                                "validation terminal lease is not the authoritative archive"
                            )
                        if any(
                            archived != validated
                            for _path, archived in matching_archives
                        ):
                            raise ConfigurationError(
                                "validation terminal archives conflict"
                            )
                        return validated, "TERMINAL_LEASE"
                    assert never_acquired_receipt is not None
                    validated = _validate_validation_never_acquired_receipt(
                        never_acquired_receipt,
                        reservation=reservation,
                    )
                    if validated.get("execution_namespace") != execution_namespace:
                        raise ConfigurationError(
                            "validation never-acquired execution namespace mismatches"
                        )
                    source_path = _validation_never_acquired_source_path(
                        execution, str(reservation["reservation_id"])
                    )
                    source = read_strict_canonical_json(
                        source_path,
                        label="validation never-acquired receipt",
                        expected_fields=VALIDATION_NEVER_ACQUIRED_FIELDS,
                    )
                    if source != validated:
                        raise ConfigurationError(
                            "validation never-acquired receipt differs from execution evidence"
                        )
                    if (
                        active is not None
                        and active.get("host_reservation_id")
                        == reservation.get("reservation_id")
                    ) or matching_archives:
                        raise ConfigurationError(
                            "validation never-acquired cut contains lease authority"
                        )
                    return validated, "NEVER_ACQUIRED"


def _validate_dispatcher_admission_intent(
    value: Mapping[str, object],
    *,
    execution_id: str,
    execution_namespace: str,
) -> Mapping[str, object]:
    """Strictly validate the immutable dispatcher transaction that owns permits."""

    intent_fields = set(value)
    schema_version = value.get("schema_version")
    is_current = (
        intent_fields == DISPATCH_ADMISSION_INTENT_FIELDS
        and schema_version in {2, 3}
    )
    is_scheduler = is_current and schema_version == 3
    is_legacy = (
        intent_fields == LEGACY_DISPATCH_ADMISSION_INTENT_FIELDS
        and schema_version == 1
    )
    if not is_current and not is_legacy:
        raise ConfigurationError("dispatcher admission intent schema is ambiguous")
    material = dict(value)
    record_id = material.pop("record_id", None)
    reservations = value.get("reservations")
    release = value.get("release")
    try:
        parse_time(value.get("issued_at"))
    except (TypeError, ValueError) as error:
        raise ConfigurationError("dispatcher admission intent time is invalid") from error
    if (
        value.get("kind") != DISPATCH_ADMISSION_INTENT_KIND
        or value.get("execution_id") != execution_id
        or value.get("execution_namespace") != execution_namespace
        or EXECUTION_NAMESPACE.fullmatch(execution_namespace) is None
        or not isinstance(value.get("repository"), str)
        or not str(value["repository"]).strip()
        or not isinstance(value.get("host_id"), str)
        or not str(value["host_id"]).strip()
        or type(value.get("admission_epoch")) is not int
        or int(value["admission_epoch"]) < 1
        or type(value.get("target_generation")) is not int
        or int(value["target_generation"]) < 1
        or type(value.get("provider_epoch")) is not int
        or int(value["provider_epoch"]) < 1
        or type(value.get("capacity_epoch")) is not int
        or int(value["capacity_epoch"]) < 1
        or FULL_SHA.fullmatch(str(value.get("target_sha"))) is None
        or any(
            AUTHORITY_ID.fullmatch(str(value.get(field))) is None
            for field in (
                "release_admission_id",
                "release_id",
                "target_watermark_record_id",
                "plan_fingerprint",
                "snapshot_observation_record_id",
                "provider_generation",
                "capacity_generation",
            )
        )
        or (
            is_current
            and (
                AUTHORITY_ID.fullmatch(
                    str(value.get("host_kernel_generation"))
                )
                is None
                or AUTHORITY_ID.fullmatch(
                    str(value.get("execution_adapter_identity_record_id"))
                )
                is None
                or AUTHORITY_ID.fullmatch(
                    str(value.get("execution_adapter_identity_blob_digest"))
                )
                is None
                or not isinstance(
                    value.get("execution_adapter_identity_path"), str
                )
                or not str(value["execution_adapter_identity_path"]).startswith(
                    "execution-adapter-bindings/"
                )
                or Path(str(value["execution_adapter_identity_path"])).is_absolute()
                or ".."
                in Path(str(value["execution_adapter_identity_path"])).parts
            )
        )
        or not isinstance(value.get("actor"), str)
        or not str(value["actor"]).strip()
        or record_id != digest_json(material)
        or not isinstance(reservations, list)
        or not reservations
        or not isinstance(release, Mapping)
        or set(release) != DISPATCH_RELEASE_FIELDS
    ):
        raise ConfigurationError("dispatcher admission intent is invalid")
    seen: set[str] = set()
    for reservation in reservations:
        reservation_fields = {
            "node_id",
            "resource_key",
            "local_reservation_id",
            "reservation_id",
        }
        if is_scheduler:
            reservation_fields.add("host_scheduler_grant_id")
        if (
            not isinstance(reservation, Mapping)
            or set(reservation) != reservation_fields
            or not isinstance(reservation.get("node_id"), str)
            or not str(reservation["node_id"]).strip()
            or any(
                AUTHORITY_ID.fullmatch(str(reservation.get(field))) is None
                for field in (
                    "resource_key",
                    "local_reservation_id",
                    "reservation_id",
                    *(("host_scheduler_grant_id",) if is_scheduler else ()),
                )
            )
            or str(reservation["reservation_id"]) in seen
        ):
            raise ConfigurationError(
                "dispatcher admission intent reservation inventory is invalid"
            )
        seen.add(str(reservation["reservation_id"]))
        reservation_identity: dict[str, object] = {
                "kind": "hive-mind-host-reservation-key-v1",
                "repository": value["repository"],
                "execution_id": execution_id,
                "host_id": value["host_id"],
                "provider_generation": value["provider_generation"],
                "capacity_generation": value["capacity_generation"],
                "local_reservation_id": reservation["local_reservation_id"],
                "reservation_kind": "PRIMARY",
        }
        if is_current:
            reservation_identity.update(
                {
                    "host_kernel_generation": value["host_kernel_generation"],
                    "execution_adapter_identity_record_id": value[
                        "execution_adapter_identity_record_id"
                    ],
                }
            )
        if is_scheduler:
            reservation_identity["host_scheduler_grant_id"] = reservation[
                "host_scheduler_grant_id"
            ]
        expected_reservation_id = digest_json(reservation_identity)
        if reservation.get("reservation_id") != expected_reservation_id:
            raise ConfigurationError(
                "dispatcher admission intent reservation digest is invalid"
            )
    release_material = dict(release)
    embedded_release_id = release_material.pop("release_id", None)
    admission_material = dict(release_material)
    embedded_admission_id = admission_material.pop("release_admission_id", None)
    embedded_reservations = admission_material.pop(
        "primary_host_reservations", None
    )
    expected_admission_id = digest_json(
        {
            "kind": "hive-mind-release-admission-key-v1",
            "release": admission_material,
        }
    )
    expected_reservations = [
        {
            "node_id": item["node_id"],
            "resource_key": item["resource_key"],
            "reservation_id": item["reservation_id"],
        }
        for item in reservations
    ]
    if (
        embedded_release_id != digest_json(release_material)
        or embedded_release_id != value.get("release_id")
        or embedded_admission_id != expected_admission_id
        or embedded_admission_id != value.get("release_admission_id")
        or embedded_reservations != expected_reservations
        or release.get("execution_namespace") != execution_namespace
        or release.get("execution_id") != execution_id
        or release.get("repository") != value.get("repository")
        or release.get("admission_epoch") != value.get("admission_epoch")
        or release.get("host_id") != value.get("host_id")
        or release.get("capacity_generation")
        != value.get("capacity_generation")
        or release.get("capacity_epoch") != value.get("capacity_epoch")
    ):
        raise ConfigurationError(
            "dispatcher admission intent embedded release is invalid"
        )
    return dict(value)


def _verify_pre_launch_abort_negative_cut(
    *,
    repo_root: str | Path,
    coordination_dir: str | Path,
    execution_dir: str | Path,
    execution_id: str,
    execution_namespace: str,
    reservation: Mapping[str, object],
    receipt: Mapping[str, object],
) -> Mapping[str, object]:
    """Recompute the never-launched fact under the canonical authority cut."""

    repository_root = _reject_link_components(
        repo_root, label="pre-launch abort repository root"
    ).resolve()
    coordination = _reject_link_components(
        coordination_dir, label="pre-launch abort coordination root"
    ).resolve()
    execution = require_execution_authority_dir(
        repository_root,
        execution_dir,
        execution_id=execution_id,
        execution_namespace=execution_namespace,
    )
    if execution.parents[1] != coordination:
        raise ConfigurationError(
            "pre-launch abort execution does not belong to the coordination root"
        )
    from orchestration import (
        OrchestrationError,
        active_host_reservations,
        active_write_launch_reservations,
        binding_authority_guard,
        binding_events,
    )

    intent_path = (
        execution
        / "di"
        / (
            str(receipt["release_admission_id"]).removeprefix("sha256:")
            + ".json"
        )
    )
    with runtime_file_lock(
        coordination / "arbiter" / "locks" / "arbiter-authority.lock",
        timeout_seconds=120.0,
    ):
        with runtime_file_lock(
            execution / "locks" / "dispatcher-admission.lock",
            timeout_seconds=120.0,
        ):
            with binding_authority_guard(
                repository_root, state_dir=execution
            ):
                try:
                    writes = active_write_launch_reservations(
                        repository_root,
                        execution_dir=execution,
                        execution_id=execution_id,
                        execution_namespace=execution_namespace,
                    )
                    hosts = active_host_reservations(
                        repository_root,
                        execution_dir=execution,
                        execution_id=execution_id,
                        execution_namespace=execution_namespace,
                    )
                except OrchestrationError as error:
                    raise ConfigurationError(str(error)) from error
                effects = execution_host_effect_obligations(execution)
                prior_bindings = tuple(
                    event
                    for event in binding_events(
                        repository_root, state_dir=execution
                    )
                    if event.get("host_reservation_id")
                    == reservation.get("reservation_id")
                )
                claim_lock = coordination / "arbiter" / "locks" / "claim-authority.lock"
                with runtime_file_lock(claim_lock, timeout_seconds=120.0):
                    live_claims: list[Mapping[str, object]] = []
                    claims_dir = coordination / "arbiter" / "claims"
                    if claims_dir.is_dir():
                        for path in sorted(claims_dir.glob("*.json")):
                            claim, expires, _raw = read_claim_authority_file(path)
                            if (
                                claim.get("execution_id") == execution_id
                                and expires > utc_now()
                            ):
                                live_claims.append(claim)
                if writes or hosts or effects or prior_bindings or live_claims:
                    raise ConfigurationError(
                        "pre-launch abort negative activity cut is not empty"
                    )
                intent_value = read_strict_canonical_json(
                    intent_path,
                    label="dispatcher admission intent",
                )
                if not isinstance(intent_value, Mapping):
                    raise ConfigurationError(
                        "dispatcher admission intent is not an object"
                    )
                intent = _validate_dispatcher_admission_intent(
                    intent_value,
                    execution_id=execution_id,
                    execution_namespace=execution_namespace,
                )
                matching = [
                    item
                    for item in intent["reservations"]
                    if isinstance(item, Mapping)
                    and item.get("reservation_id")
                    == reservation.get("reservation_id")
                ]
                if (
                    len(matching) != 1
                    or intent.get("record_id") != receipt.get("intent_record_id")
                    or intent.get("release_id") != receipt.get("release_id")
                    or intent.get("release_admission_id")
                    != receipt.get("release_admission_id")
                    or intent.get("admission_epoch")
                    != receipt.get("admission_epoch")
                    or matching[0].get("local_reservation_id")
                    != reservation.get("local_reservation_id")
                    or matching[0].get("resource_key")
                    != reservation.get("resource_key")
                    or matching[0].get("node_id") != receipt.get("node_id")
                ):
                    raise ConfigurationError(
                        "pre-launch abort does not match its dispatcher admission intent"
                    )
                current_release_path = execution / "dispatcher-release.json"
                if current_release_path.is_file():
                    current_release = read_strict_canonical_json(
                        current_release_path,
                        label="current dispatcher release",
                        expected_fields=DISPATCH_RELEASE_FIELDS,
                    )
                    if (
                        isinstance(current_release, Mapping)
                        and current_release.get("release_id")
                        == receipt.get("release_id")
                    ):
                        raise ConfigurationError(
                            "pre-launch abort cannot retire a published dispatcher release"
                        )
    return dict(receipt)


def _pre_launch_abort_evidence_path(
    host_runtime_dir: str | Path,
    reservation_id: str,
) -> Path:
    if AUTHORITY_ID.fullmatch(reservation_id) is None:
        raise ConfigurationError("pre-launch abort reservation id is invalid")
    return (
        Path(host_runtime_dir).resolve()
        / "pre-launch-aborts"
        / (reservation_id.removeprefix("sha256:") + ".json")
    )


def _local_terminal_event_evidence_path(
    host_runtime_dir: str | Path,
    event_id: str,
) -> Path:
    if AUTHORITY_ID.fullmatch(event_id) is None:
        raise ConfigurationError("local terminal event id is invalid")
    return (
        Path(host_runtime_dir).resolve()
        / "terminal-events"
        / (event_id.removeprefix("sha256:") + ".json")
    )


def _verify_local_terminal_event_cut(
    *,
    repo_root: str | Path,
    coordination_dir: str | Path,
    execution_dir: str | Path,
    execution_id: str,
    execution_namespace: str,
    reservation: Mapping[str, object],
    local_terminal_event: Mapping[str, object],
) -> tuple[Mapping[str, object], str, str]:
    """Authenticate a terminal local ledger event under the canonical cut."""

    repository_root = _reject_link_components(
        repo_root, label="terminal reservation repository root"
    ).resolve()
    coordination = _reject_link_components(
        coordination_dir, label="terminal reservation coordination root"
    ).resolve()
    execution = require_execution_authority_dir(
        repository_root,
        execution_dir,
        execution_id=execution_id,
        execution_namespace=execution_namespace,
    )
    if execution.parents[1] != coordination:
        raise ConfigurationError(
            "terminal reservation execution does not belong to coordination root"
        )
    from orchestration import (
        OrchestrationError,
        binding_authority_guard,
        binding_events,
    )
    from sidecar_execution import SidecarPolicyError, latest_sidecars

    with runtime_file_lock(
        coordination / "arbiter" / "locks" / "arbiter-authority.lock",
        timeout_seconds=120.0,
    ):
        with runtime_file_lock(
            execution / "locks" / "dispatcher-admission.lock",
            timeout_seconds=120.0,
        ):
            with binding_authority_guard(repository_root, state_dir=execution):
                try:
                    if reservation.get("reservation_kind") == "PRIMARY":
                        latest: dict[str, Mapping[str, object]] = {}
                        for event in binding_events(
                            repository_root, state_dir=execution
                        ):
                            instruction_id = event.get("launch_instruction_id")
                            if isinstance(instruction_id, str):
                                latest[instruction_id] = event
                        matches = [
                            event
                            for event in latest.values()
                            if event.get("host_reservation_id")
                            == reservation.get("reservation_id")
                        ]
                        event_kind = "PRIMARY_BINDING"
                        terminal_ok = (
                            len(matches) == 1
                            and matches[0].get("state") == "RELEASED"
                            and matches[0].get("terminal_state")
                            in {"SUCCEEDED", "FAILED", "CANCELLED"}
                            and isinstance(matches[0].get("host_event_id"), str)
                            and bool(str(matches[0]["host_event_id"]).strip())
                        )
                    elif reservation.get("reservation_kind") == "SIDECAR":
                        matches = [
                            event
                            for event in latest_sidecars(
                                repository_root, state_dir=execution
                            ).values()
                            if event.get("host_reservation_id")
                            == reservation.get("reservation_id")
                        ]
                        event_kind = "SIDECAR"
                        state = matches[0].get("state") if len(matches) == 1 else None
                        terminal_ok = len(matches) == 1 and (
                            (
                                state in {"SUCCEEDED", "FAILED", "CANCELLED"}
                                and isinstance(
                                    matches[0].get("host_event_id"), str
                                )
                                and bool(
                                    str(matches[0]["host_event_id"]).strip()
                                )
                            )
                            or state in {"SPAWN_FAILED", "SKIPPED_CAPACITY"}
                        )
                    else:
                        raise ConfigurationError(
                            "local terminal event is only valid for primary or sidecar reservations"
                        )
                except (OrchestrationError, SidecarPolicyError) as error:
                    raise ConfigurationError(str(error)) from error
                if (
                    not terminal_ok
                    or matches[0] != local_terminal_event
                    or matches[0].get("event_id")
                    != local_terminal_event.get("event_id")
                    or local_terminal_event.get("capacity_generation")
                    != reservation.get("capacity_generation")
                    or local_terminal_event.get("host_reservation_id")
                    != reservation.get("reservation_id")
                    or any(
                        local_terminal_event.get(field) != reservation.get(field)
                        for field in (
                            "host_kernel_generation",
                            "execution_adapter_identity_record_id",
                            "execution_adapter_identity_path",
                            "execution_adapter_identity_blob_digest",
                        )
                    )
                ):
                    raise ConfigurationError(
                        "local terminal event does not match the authoritative ledger"
                    )
                event = dict(matches[0])
    return event, event_kind, str(event.get("state"))


def _host_reservation_events_unlocked(
    host_runtime_dir: str | Path,
    *,
    raw_override: bytes | None = None,
) -> tuple[Mapping[str, object], ...]:
    path = _host_reservation_path(host_runtime_dir)
    if raw_override is None and not path.is_file():
        return ()
    try:
        raw = (
            raw_override
            if raw_override is not None
            else _read_regular_authority_bytes(path, label="host reservation ledger")
        )
        records = _strict_jsonl_records_bytes(raw, label="host reservation ledger")
    except (OSError, ConfigurationError) as error:
        raise ConfigurationError(f"cannot read host reservation ledger: {error}") from error
    previous: str | None = None
    events: list[Mapping[str, object]] = []
    legacy_reserve_fields = {
        "schema_version",
        "kind",
        "state",
        "reservation_id",
        "reservation_kind",
        "repository",
        "execution_id",
        "host_id",
        "provider_generation",
        "provider_epoch",
        "capacity_generation",
        "capacity_epoch",
        "local_reservation_id",
        "resource_key",
        "write_scopes",
        "reserved_at",
        "expires_at",
        "previous_event_id",
        "event_id",
    }
    authority_provenance_fields = {
        "host_kernel_generation",
        "execution_adapter_identity_record_id",
        "execution_adapter_identity_path",
        "execution_adapter_identity_blob_digest",
    }
    scheduler_provenance_fields = {"host_scheduler_grant_id"}
    pre_scheduler_reserve_fields = legacy_reserve_fields | authority_provenance_fields
    reserve_fields = pre_scheduler_reserve_fields | scheduler_provenance_fields
    release_fields = reserve_fields | {
        "released_at",
        "release_actor",
        "release_reason",
        "external_cancellation",
    }
    renewal_fields = reserve_fields | {
        "renewed_at",
        "renewal_actor",
        "renewal_reason",
        "prior_expires_at",
        "renewal_count",
    }
    renewed_release_fields = renewal_fields | {
        "released_at",
        "release_actor",
        "release_reason",
        "external_cancellation",
    }
    pre_scheduler_release_fields = pre_scheduler_reserve_fields | {
        "released_at",
        "release_actor",
        "release_reason",
        "external_cancellation",
    }
    pre_scheduler_renewal_fields = pre_scheduler_reserve_fields | {
        "renewed_at",
        "renewal_actor",
        "renewal_reason",
        "prior_expires_at",
        "renewal_count",
    }
    pre_scheduler_renewed_release_fields = pre_scheduler_renewal_fields | {
        "released_at",
        "release_actor",
        "release_reason",
        "external_cancellation",
    }
    terminal_release_evidence_fields = {
        "local_terminal_event_id",
        "local_terminal_event_path",
        "local_terminal_event_blob_digest",
        "local_terminal_event_kind",
        "local_terminal_state",
        "lifecycle_state",
    }
    pre_launch_abort_fields = {
        "pre_launch_abort_receipt_id",
        "pre_launch_abort_receipt_path",
        "pre_launch_abort_receipt_blob_digest",
        "pre_launch_abort_release_id",
        "pre_launch_abort_admission_epoch",
        "pre_launch_abort_state",
    }
    validation_terminal_evidence_fields = {
        "validation_terminal_evidence_id",
        "validation_terminal_evidence_path",
        "validation_terminal_evidence_blob_digest",
        "validation_terminal_evidence_type",
        "validation_terminal_status",
    }
    recovery_evidence_fields = {
        "lifecycle_observation_id",
        "lifecycle_observation_path",
        "lifecycle_observation_blob_digest",
        "lifecycle_state",
        "lifecycle_host_id",
        "local_terminal_event_id",
    }
    legacy_release_fields = legacy_reserve_fields | {
        "released_at",
        "release_actor",
        "release_reason",
        "external_cancellation",
    }
    legacy_renewal_fields = legacy_reserve_fields | {
        "renewed_at",
        "renewal_actor",
        "renewal_reason",
        "prior_expires_at",
        "renewal_count",
    }
    legacy_renewed_release_fields = legacy_renewal_fields | {
        "released_at",
        "release_actor",
        "release_reason",
        "external_cancellation",
    }

    def _schema_variants(
        current_base: set[str],
        pre_scheduler_base: set[str],
        legacy_base: set[str],
        extra: set[str],
    ) -> tuple[set[str], set[str], set[str]]:
        return (
            current_base | extra,
            pre_scheduler_base | extra,
            legacy_base | extra,
        )

    evidenced_release_fields = _schema_variants(
        release_fields,
        pre_scheduler_release_fields,
        legacy_release_fields,
        terminal_release_evidence_fields,
    )
    renewed_evidenced_release_fields = _schema_variants(
        renewed_release_fields,
        pre_scheduler_renewed_release_fields,
        legacy_renewed_release_fields,
        terminal_release_evidence_fields,
    )
    pre_launch_release_fields = _schema_variants(
        release_fields,
        pre_scheduler_release_fields,
        legacy_release_fields,
        pre_launch_abort_fields,
    )
    renewed_pre_launch_release_fields = _schema_variants(
        renewed_release_fields,
        pre_scheduler_renewed_release_fields,
        legacy_renewed_release_fields,
        pre_launch_abort_fields,
    )
    validation_release_fields = _schema_variants(
        release_fields,
        pre_scheduler_release_fields,
        legacy_release_fields,
        validation_terminal_evidence_fields,
    )
    renewed_validation_release_fields = _schema_variants(
        renewed_release_fields,
        pre_scheduler_renewed_release_fields,
        legacy_renewed_release_fields,
        validation_terminal_evidence_fields,
    )
    recovery_fields = _schema_variants(
        release_fields,
        pre_scheduler_release_fields,
        legacy_release_fields,
        recovery_evidence_fields,
    )
    renewed_recovery_fields = _schema_variants(
        renewed_release_fields,
        pre_scheduler_renewed_release_fields,
        legacy_renewed_release_fields,
        recovery_evidence_fields,
    )
    latest: dict[str, Mapping[str, object]] = {}
    for index, value in enumerate(records, 1):
        state = value.get("state")
        valid_schemas = {
            "RESERVED": (
                reserve_fields,
                pre_scheduler_reserve_fields,
                legacy_reserve_fields,
            ),
            "RENEWED": (
                renewal_fields,
                pre_scheduler_reserve_fields
                | {
                    "renewed_at",
                    "renewal_actor",
                    "renewal_reason",
                    "prior_expires_at",
                    "renewal_count",
                },
                legacy_renewal_fields,
            ),
            "RELEASED": (
                release_fields,
                pre_scheduler_release_fields,
                legacy_release_fields,
                renewed_release_fields,
                pre_scheduler_renewed_release_fields,
                legacy_renewed_release_fields,
                *evidenced_release_fields,
                *renewed_evidenced_release_fields,
                *pre_launch_release_fields,
                *renewed_pre_launch_release_fields,
                *validation_release_fields,
                *renewed_validation_release_fields,
            ),
            # The release-shaped EXPIRED_FENCED schema is an explicitly
            # enumerated pre-lifecycle-evidence legacy row. New writers cannot
            # emit it; replay preserves evidence without silently broadening it.
            "EXPIRED_FENCED": (
                release_fields,
                pre_scheduler_release_fields,
                legacy_release_fields,
                renewed_release_fields,
                pre_scheduler_renewed_release_fields,
                legacy_renewed_release_fields,
                *recovery_fields,
                *renewed_recovery_fields,
            ),
        }
        if state not in HOST_RESERVATION_STATES or not any(
            set(value) == schema for schema in valid_schemas.get(str(state), ())
        ):
            raise ConfigurationError(
                f"host reservation ledger line {index} schema is invalid"
            )
        if value.get("schema_version") != 1 or value.get("kind") != HOST_RESERVATION_EVENT_KIND:
            raise ConfigurationError(
                f"host reservation ledger line {index} kind is invalid"
            )
        material = dict(value)
        event_id = material.pop("event_id")
        if material.get("previous_event_id") != previous or event_id != digest_json(material):
            raise ConfigurationError(
                f"host reservation ledger line {index} hash chain is invalid"
            )
        reservation_id = value.get("reservation_id")
        if not isinstance(reservation_id, str) or AUTHORITY_ID.fullmatch(reservation_id) is None:
            raise ConfigurationError(
                f"host reservation ledger line {index} identity is invalid"
            )
        current_schema = authority_provenance_fields.issubset(value)
        scheduler_schema = scheduler_provenance_fields.issubset(value)
        identity = {
            "kind": "hive-mind-host-reservation-key-v1",
            "repository": value.get("repository"),
            "execution_id": value.get("execution_id"),
            "host_id": value.get("host_id"),
            "provider_generation": value.get("provider_generation"),
            "capacity_generation": value.get("capacity_generation"),
            "local_reservation_id": value.get("local_reservation_id"),
            "reservation_kind": value.get("reservation_kind"),
        }
        if current_schema:
            identity.update(
                {
                    "host_kernel_generation": value.get(
                        "host_kernel_generation"
                    ),
                    "execution_adapter_identity_record_id": value.get(
                        "execution_adapter_identity_record_id"
                    ),
                }
            )
        if scheduler_schema:
            identity["host_scheduler_grant_id"] = value.get(
                "host_scheduler_grant_id"
            )
        if reservation_id != digest_json(identity):
            raise ConfigurationError(
                f"host reservation ledger line {index} reservation digest is invalid"
            )
        if (
            value.get("reservation_kind") not in HOST_RESERVATION_KINDS
            or not isinstance(value.get("repository"), str)
            or not str(value.get("repository")).strip()
            or not isinstance(value.get("execution_id"), str)
            or AUTHORITY_ID.fullmatch(str(value.get("execution_id"))) is None
            or not isinstance(value.get("host_id"), str)
            or not str(value.get("host_id")).strip()
            or AUTHORITY_ID.fullmatch(
                str(value.get("provider_generation"))
            )
            is None
            or type(value.get("provider_epoch")) is not int
            or int(value["provider_epoch"]) < 1
            or not isinstance(value.get("capacity_generation"), str)
            or AUTHORITY_ID.fullmatch(str(value.get("capacity_generation"))) is None
            or type(value.get("capacity_epoch")) is not int
            or int(value["capacity_epoch"]) < 1
            or not isinstance(value.get("local_reservation_id"), str)
            or AUTHORITY_ID.fullmatch(str(value.get("local_reservation_id"))) is None
            or not isinstance(value.get("resource_key"), str)
            or AUTHORITY_ID.fullmatch(str(value.get("resource_key"))) is None
            or not isinstance(value.get("write_scopes"), list)
            or not all(isinstance(scope, str) for scope in value["write_scopes"])
        ):
            raise ConfigurationError(
                f"host reservation ledger line {index} coordinates are invalid"
            )
        if current_schema:
            adapter_record_id = value.get("execution_adapter_identity_record_id")
            adapter_path = value.get("execution_adapter_identity_path")
            adapter_blob = value.get("execution_adapter_identity_blob_digest")
            if AUTHORITY_ID.fullmatch(
                str(value.get("host_kernel_generation"))
            ) is None:
                raise ConfigurationError(
                    f"host reservation ledger line {index} has no writer generation"
                )
            if value.get("reservation_kind") == "VALIDATION":
                if any(
                    item is not None
                    for item in (adapter_record_id, adapter_path, adapter_blob)
                ):
                    raise ConfigurationError(
                        f"host reservation ledger line {index} gives internal validation an external adapter"
                    )
            else:
                if (
                    AUTHORITY_ID.fullmatch(str(adapter_record_id)) is None
                    or adapter_path
                    != "execution-adapter-bindings/"
                    + str(adapter_record_id).removeprefix("sha256:")
                    + ".json"
                    or AUTHORITY_ID.fullmatch(str(adapter_blob)) is None
                ):
                    raise ConfigurationError(
                        f"host reservation ledger line {index} adapter fence is invalid"
                    )
                adapter_file = Path(host_runtime_dir) / str(adapter_path)
                adapter_raw = _read_regular_authority_bytes(
                    adapter_file,
                    label="host reservation execution adapter evidence",
                )
                adapter_binding = parse_strict_canonical_json_bytes(
                    adapter_raw,
                    label="host reservation execution adapter evidence",
                    expected_fields=EXECUTION_ADAPTER_IDENTITY_FIELDS,
                )
                validated_adapter = _validate_execution_adapter_identity_binding(
                    Path(host_runtime_dir), adapter_binding
                )
                if (
                    validated_adapter.get("record_id") != adapter_record_id
                    or "sha256:" + sha256(adapter_raw).hexdigest() != adapter_blob
                    or any(
                        validated_adapter.get(field) != value.get(field)
                        for field in (
                            "repository",
                            "execution_id",
                            "host_id",
                            "provider_generation",
                            "provider_epoch",
                        )
                    )
                ):
                    raise ConfigurationError(
                        f"host reservation ledger line {index} adapter evidence changed"
                    )
        if scheduler_schema:
            grant_id = value.get("host_scheduler_grant_id")
            if value.get("reservation_kind") == "VALIDATION":
                if grant_id is not None:
                    raise ConfigurationError(
                        f"host reservation ledger line {index} gives validation a scheduler grant"
                    )
            elif AUTHORITY_ID.fullmatch(str(grant_id)) is None:
                raise ConfigurationError(
                    f"host reservation ledger line {index} scheduler grant is invalid"
                )
        try:
            reserved = parse_time(value.get("reserved_at"))
            expires = parse_time(value.get("expires_at"))
        except (TypeError, ValueError) as error:
            raise ConfigurationError(
                f"host reservation ledger line {index} bounds are malformed"
            ) from error
        if expires <= reserved:
            raise ConfigurationError(
                f"host reservation ledger line {index} has an empty lifetime"
            )
        try:
            normalized_scopes = [normalize_path(scope) for scope in value["write_scopes"]]
        except ValueError as error:
            raise ConfigurationError(
                f"host reservation ledger line {index} has an invalid scope"
            ) from error
        if value.get("reservation_kind") == "VALIDATION":
            if normalized_scopes:
                raise ConfigurationError(
                    f"host reservation ledger line {index} gives validation a write scope"
                )
        elif normalized_scopes != value.get("write_scopes"):
            raise ConfigurationError(
                f"host reservation ledger line {index} has noncanonical scopes"
            )
        if state == "RENEWED":
            try:
                renewed_at = parse_time(value.get("renewed_at"))
                prior_expiry = parse_time(value.get("prior_expires_at"))
            except (TypeError, ValueError) as error:
                raise ConfigurationError(
                    f"host reservation ledger line {index} renewal is malformed"
                ) from error
            if (
                renewed_at < reserved
                or expires <= prior_expiry
                or type(value.get("renewal_count")) is not int
                or int(value["renewal_count"]) < 1
                or not isinstance(value.get("renewal_actor"), str)
                or not str(value["renewal_actor"]).strip()
                or not isinstance(value.get("renewal_reason"), str)
                or not str(value["renewal_reason"]).strip()
            ):
                raise ConfigurationError(
                    f"host reservation ledger line {index} renewal evidence is invalid"
                )
        if state in {"RELEASED", "EXPIRED_FENCED"}:
            try:
                released_at = parse_time(value.get("released_at"))
            except (TypeError, ValueError) as error:
                raise ConfigurationError(
                    f"host reservation ledger line {index} release is malformed"
                ) from error
            if (
                released_at < reserved
                or not isinstance(value.get("release_actor"), str)
                or not str(value["release_actor"]).strip()
                or not isinstance(value.get("release_reason"), str)
                or not str(value["release_reason"]).strip()
            ):
                raise ConfigurationError(
                    f"host reservation ledger line {index} release evidence is invalid"
                )
            if recovery_evidence_fields.issubset(value):
                if (
                    value.get("lifecycle_state")
                    not in {"TERMINAL", "ABSENT", "INTERRUPTED_ARCHIVED"}
                    or value.get("lifecycle_host_id") != value.get("host_id")
                    or not isinstance(value.get("lifecycle_observation_id"), str)
                    or AUTHORITY_ID.fullmatch(
                        str(value["lifecycle_observation_id"])
                    )
                    is None
                    or not isinstance(value.get("local_terminal_event_id"), str)
                    or AUTHORITY_ID.fullmatch(
                        str(value["local_terminal_event_id"])
                    )
                    is None
                    or value.get("external_cancellation")
                    not in {
                        "CONFIRMED_TERMINAL",
                        "CONFIRMED_ABSENT",
                        "CONFIRMED_INTERRUPTED_ARCHIVED",
                    }
                    or value.get("lifecycle_observation_path")
                    != (
                        "lifecycle-observations/"
                        + str(value.get("lifecycle_observation_id")).removeprefix(
                            "sha256:"
                        )
                        + ".json"
                    )
                    or AUTHORITY_ID.fullmatch(
                        str(value.get("lifecycle_observation_blob_digest"))
                    )
                    is None
                ):
                    raise ConfigurationError(
                        f"host reservation ledger line {index} lifecycle recovery evidence is invalid"
                    )
                observation_path = (
                    Path(host_runtime_dir)
                    / str(value["lifecycle_observation_path"])
                )
                observation = read_strict_canonical_json(
                    observation_path,
                    label="host lifecycle observation evidence",
                )
                if not isinstance(observation, Mapping):
                    raise ConfigurationError(
                        f"host reservation ledger line {index} lifecycle observation is malformed"
                    )
                observation_bytes = observation_path.read_bytes()
                if (
                    "sha256:" + sha256(observation_bytes).hexdigest()
                    != value.get("lifecycle_observation_blob_digest")
                    or observation.get("observation_id")
                    != value.get("lifecycle_observation_id")
                ):
                    raise ConfigurationError(
                        f"host reservation ledger line {index} lifecycle observation evidence changed"
                    )
                validate_host_lifecycle_observation(
                    observation,
                    reservation=value,
                    now=datetime.max.replace(tzinfo=UTC),
                )
            elif terminal_release_evidence_fields.issubset(value):
                if (
                    state != "RELEASED"
                    or value.get("lifecycle_state") != "TERMINAL"
                    or value.get("external_cancellation")
                    != "CONFIRMED_TERMINAL"
                    or not isinstance(value.get("local_terminal_event_id"), str)
                    or AUTHORITY_ID.fullmatch(
                        str(value["local_terminal_event_id"])
                    )
                    is None
                    or value.get("local_terminal_event_kind")
                    not in {"PRIMARY_BINDING", "SIDECAR"}
                    or not isinstance(value.get("local_terminal_state"), str)
                    or value.get("local_terminal_event_path")
                    != (
                        "terminal-events/"
                        + str(value["local_terminal_event_id"]).removeprefix(
                            "sha256:"
                        )
                        + ".json"
                    )
                    or AUTHORITY_ID.fullmatch(
                        str(value.get("local_terminal_event_blob_digest"))
                    )
                    is None
                ):
                    raise ConfigurationError(
                        f"host reservation ledger line {index} terminal release evidence is invalid"
                    )
                terminal_path = (
                    Path(host_runtime_dir)
                    / str(value["local_terminal_event_path"])
                )
                terminal_event = read_strict_canonical_json(
                    terminal_path,
                    label="local terminal event evidence",
                )
                if not isinstance(terminal_event, Mapping):
                    raise ConfigurationError(
                        f"host reservation ledger line {index} local terminal event is malformed"
                    )
                terminal_bytes = terminal_path.read_bytes()
                terminal_material = dict(terminal_event)
                terminal_event_id = terminal_material.pop("event_id", None)
                if (
                    "sha256:" + sha256(terminal_bytes).hexdigest()
                    != value.get("local_terminal_event_blob_digest")
                    or terminal_event_id != value.get("local_terminal_event_id")
                    or terminal_event_id != digest_json(terminal_material)
                    or terminal_event.get("state")
                    != value.get("local_terminal_state")
                    or terminal_event.get("host_reservation_id")
                    != value.get("reservation_id")
                    or terminal_event.get("capacity_generation")
                    != value.get("capacity_generation")
                ):
                    raise ConfigurationError(
                        f"host reservation ledger line {index} local terminal evidence changed"
                    )
            elif pre_launch_abort_fields.issubset(value):
                if (
                    state != "RELEASED"
                    or value.get("reservation_kind") != "PRIMARY"
                    or value.get("external_cancellation")
                    != "CONFIRMED_NEVER_LAUNCHED"
                    or value.get("pre_launch_abort_state") != "NEVER_LAUNCHED"
                    or AUTHORITY_ID.fullmatch(
                        str(value.get("pre_launch_abort_receipt_id"))
                    )
                    is None
                    or AUTHORITY_ID.fullmatch(
                        str(value.get("pre_launch_abort_release_id"))
                    )
                    is None
                    or type(value.get("pre_launch_abort_admission_epoch")) is not int
                    or int(value["pre_launch_abort_admission_epoch"]) < 1
                    or value.get("pre_launch_abort_receipt_path")
                    != (
                        "pre-launch-aborts/"
                        + str(value.get("reservation_id")).removeprefix("sha256:")
                        + ".json"
                    )
                    or AUTHORITY_ID.fullmatch(
                        str(value.get("pre_launch_abort_receipt_blob_digest"))
                    )
                    is None
                ):
                    raise ConfigurationError(
                        f"host reservation ledger line {index} pre-launch abort evidence is invalid"
                    )
                abort_path = (
                    Path(host_runtime_dir)
                    / str(value["pre_launch_abort_receipt_path"])
                )
                abort_receipt = read_strict_canonical_json(
                    abort_path,
                    label="pre-launch abort evidence",
                    expected_fields=PRE_LAUNCH_ABORT_FIELDS,
                )
                if not isinstance(abort_receipt, Mapping):
                    raise ConfigurationError(
                        f"host reservation ledger line {index} pre-launch abort receipt is malformed"
                    )
                abort_bytes = abort_path.read_bytes()
                if (
                    "sha256:" + sha256(abort_bytes).hexdigest()
                    != value.get("pre_launch_abort_receipt_blob_digest")
                    or abort_receipt.get("record_id")
                    != value.get("pre_launch_abort_receipt_id")
                ):
                    raise ConfigurationError(
                        f"host reservation ledger line {index} pre-launch abort evidence changed"
                    )
                _validate_pre_launch_abort_receipt(
                    abort_receipt,
                    reservation=value,
                )
            elif validation_terminal_evidence_fields.issubset(value):
                evidence_type = value.get("validation_terminal_evidence_type")
                expected_external = (
                    "CONFIRMED_VALIDATION_TERMINAL"
                    if evidence_type == "TERMINAL_LEASE"
                    else "CONFIRMED_VALIDATION_NEVER_ACQUIRED"
                )
                if (
                    state != "RELEASED"
                    or value.get("reservation_kind") != "VALIDATION"
                    or evidence_type not in {"TERMINAL_LEASE", "NEVER_ACQUIRED"}
                    or value.get("external_cancellation") != expected_external
                    or AUTHORITY_ID.fullmatch(
                        str(value.get("validation_terminal_evidence_id"))
                    )
                    is None
                    or AUTHORITY_ID.fullmatch(
                        str(value.get("validation_terminal_evidence_blob_digest"))
                    )
                    is None
                    or value.get("validation_terminal_evidence_path")
                    != (
                        "validation-terminal-receipts/"
                        + str(value.get("reservation_id")).removeprefix("sha256:")
                        + ".json"
                    )
                    or (
                        evidence_type == "TERMINAL_LEASE"
                        and value.get("validation_terminal_status")
                        not in {"RELEASED", "EXPIRED_BROKEN"}
                    )
                    or (
                        evidence_type == "NEVER_ACQUIRED"
                        and value.get("validation_terminal_status")
                        != "NEVER_ACQUIRED"
                    )
                ):
                    raise ConfigurationError(
                        f"host reservation ledger line {index} validation terminal evidence is invalid"
                    )
                evidence_path = (
                    Path(host_runtime_dir)
                    / str(value["validation_terminal_evidence_path"])
                )
                evidence = read_strict_canonical_json(
                    evidence_path,
                    label="validation host reservation terminal evidence",
                    expected_fields=(
                        VALIDATION_TERMINAL_RECEIPT_FIELDS
                        if evidence_type == "TERMINAL_LEASE"
                        else VALIDATION_NEVER_ACQUIRED_FIELDS
                    ),
                )
                if not isinstance(evidence, Mapping):
                    raise ConfigurationError(
                        f"host reservation ledger line {index} validation terminal receipt is malformed"
                    )
                evidence_bytes = evidence_path.read_bytes()
                if (
                    "sha256:" + sha256(evidence_bytes).hexdigest()
                    != value.get("validation_terminal_evidence_blob_digest")
                    or evidence.get("record_id")
                    != value.get("validation_terminal_evidence_id")
                ):
                    raise ConfigurationError(
                        f"host reservation ledger line {index} validation terminal evidence changed"
                    )
                if evidence_type == "TERMINAL_LEASE":
                    validated_evidence = _validate_validation_terminal_receipt(
                        evidence,
                        reservation=value,
                    )
                    if validated_evidence.get("terminal_status") != value.get(
                        "validation_terminal_status"
                    ):
                        raise ConfigurationError(
                            f"host reservation ledger line {index} validation terminal status changed"
                        )
                else:
                    _validate_validation_never_acquired_receipt(
                        evidence,
                        reservation=value,
                    )
            elif value.get("reservation_kind") == "VALIDATION":
                raise ConfigurationError(
                    f"host reservation ledger line {index} validation release lacks terminal evidence"
                )
        prior = latest.get(reservation_id)
        if prior is None and state != "RESERVED":
            raise ConfigurationError(
                f"host reservation ledger line {index} release has no reservation"
            )
        if prior is not None:
            if prior.get("state") not in HOST_RESERVATION_ACTIVE_STATES or state not in {
                "RENEWED",
                "RELEASED",
                "EXPIRED_FENCED",
            }:
                raise ConfigurationError(
                    f"host reservation ledger line {index} has an impossible transition"
                )
            invariant_fields = reserve_fields - {
                "state",
                "expires_at",
                "previous_event_id",
                "event_id",
            }
            for field in invariant_fields:
                if prior.get(field) != value.get(field):
                    raise ConfigurationError(
                        f"host reservation ledger line {index} mutates {field}"
                    )
            if state == "RENEWED":
                prior_count = (
                    int(prior["renewal_count"])
                    if prior.get("state") == "RENEWED"
                    else 0
                )
                if (
                    value.get("prior_expires_at") != prior.get("expires_at")
                    or int(value["renewal_count"]) != prior_count + 1
                ):
                    raise ConfigurationError(
                        f"host reservation ledger line {index} renewal lineage is invalid"
                    )
            else:
                for field in set(prior) - {
                    "schema_version",
                    "kind",
                    "state",
                    "previous_event_id",
                    "event_id",
                }:
                    if prior.get(field) != value.get(field):
                        raise ConfigurationError(
                            f"host reservation ledger line {index} terminal transition mutates {field}"
                        )
        latest[reservation_id] = value
        previous = str(event_id)
        events.append(value)
    return tuple(events)


def _append_host_reservation_unlocked(
    host_runtime_dir: str | Path,
    value: Mapping[str, object],
    events: Sequence[Mapping[str, object]],
) -> Mapping[str, object]:
    material = {
        "schema_version": 1,
        "kind": HOST_RESERVATION_EVENT_KIND,
        **dict(value),
        "previous_event_id": events[-1]["event_id"] if events else None,
    }
    event = {**material, "event_id": digest_json(material)}
    path = _host_reservation_path(host_runtime_dir)
    _append_canonical_jsonl(path, event)
    return event


def active_global_host_reservations(
    host_runtime_dir: str | Path,
) -> tuple[Mapping[str, object], ...]:
    root = require_host_runtime(host_runtime_dir)
    lock_path = root / "locks" / "host-authority.lock"
    if not runtime_file_lock_is_held(lock_path):
        raise ConfigurationError("host reservation inventory requires host authority")
    latest: dict[str, Mapping[str, object]] = {}
    for event in _host_reservation_events_unlocked(root):
        latest[str(event["reservation_id"])] = event
    return tuple(
        latest[key]
        for key in sorted(latest)
        if latest[key].get("state") in HOST_RESERVATION_ACTIVE_STATES
    )


def global_host_reservation_record(
    host_runtime_dir: str | Path,
    reservation_id: str,
) -> Mapping[str, object] | None:
    """Return the latest exact event for one reservation under host authority.

    Terminal cleanup uses this lookup to recover the reservation-local fence
    after a crash between the execution-ledger terminal append and the global
    release append.  Callers cannot substitute a launch id for that fence.
    """

    root = require_host_runtime(host_runtime_dir)
    lock_path = root / "locks" / "host-authority.lock"
    if not runtime_file_lock_is_held(lock_path):
        raise ConfigurationError("host reservation lookup requires host authority")
    if AUTHORITY_ID.fullmatch(reservation_id) is None:
        raise ConfigurationError("host reservation id is invalid")
    return next(
        (
            event
            for event in reversed(_host_reservation_events_unlocked(root))
            if event.get("reservation_id") == reservation_id
        ),
        None,
    )


HOST_AUTHORITY_TORN_TAIL_RECOVERY_KIND = (
    "hive-mind-host-authority-torn-tail-recovery-v1"
)
HOST_AUTHORITY_TORN_TAIL_COMPLETE_KIND = (
    "hive-mind-host-authority-torn-tail-complete-v1"
)
HOST_AUTHORITY_TORN_TAIL_ACTIONS = frozenset({"TRUNCATE", "APPEND_NEWLINE"})
HOST_AUTHORITY_TORN_TAIL_PREPARED_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "status",
        "ledger_kind",
        "ledger_path",
        "host_id",
        "raw_digest",
        "prefix_digest",
        "tail_digest",
        "tail_bytes",
        "action",
        "output_digest",
        "archive_path",
        "host_kernel_generation",
        "host_kernel_record_id",
        "actor",
        "reason",
        "recovery_id",
        "record_id",
    }
)
HOST_AUTHORITY_TORN_TAIL_COMPLETE_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "status",
        "recovery_id",
        "prepared_record_id",
        "ledger_kind",
        "ledger_path",
        "prefix_digest",
        "output_digest",
        "action",
        "archive_path",
        "completed_by",
        "completed_at",
        "record_id",
    }
)


def _pending_host_torn_tail_recoveries(
    host_runtime_dir: Path,
) -> tuple[Path, ...]:
    recovery_base = host_runtime_dir / "torn-tail-recoveries"
    if not recovery_base.exists() and not _is_link_like(recovery_base):
        return ()
    _reject_link_components(
        recovery_base, label="host torn-tail recovery authority"
    )
    if not recovery_base.is_dir():
        raise ConfigurationError(
            "host torn-tail recovery authority is not a directory"
        )
    pending: list[Path] = []
    for prepared_path in sorted(recovery_base.glob("*/*.prepared.json")):
        prepared = read_strict_canonical_json(
            prepared_path, label="host torn-tail PREPARED fence"
        )
        prepared_material = (
            dict(prepared) if isinstance(prepared, Mapping) else {}
        )
        prepared_record_id = prepared_material.pop("record_id", None)
        recovery_id = prepared.get("recovery_id") if isinstance(prepared, Mapping) else None
        recovery_material = (
            {
                key: prepared[key]
                for key in (
                    "ledger_kind",
                    "ledger_path",
                    "host_id",
                    "raw_digest",
                    "prefix_digest",
                    "tail_digest",
                    "tail_bytes",
                    "action",
                    "output_digest",
                    "host_kernel_generation",
                    "host_kernel_record_id",
                )
            }
            if isinstance(prepared, Mapping)
            and HOST_AUTHORITY_TORN_TAIL_PREPARED_FIELDS.issubset(prepared)
            else {}
        )
        ledger_kind = prepared.get("ledger_kind") if isinstance(prepared, Mapping) else None
        ledger_path = prepared.get("ledger_path") if isinstance(prepared, Mapping) else None
        expected_directory = (
            recovery_base
            / digest_json({"kind": ledger_kind, "path": ledger_path}).removeprefix(
                "sha256:"
            )
            if isinstance(ledger_kind, str) and isinstance(ledger_path, str)
            else None
        )
        expected_archive = (
            str(
                (
                    prepared_path.parent
                    / (
                        str(prepared.get("tail_digest")).removeprefix("sha256:")
                        + ".bin"
                    )
                ).relative_to(host_runtime_dir)
            ).replace("\\", "/")
            if isinstance(prepared, Mapping)
            and AUTHORITY_ID.fullmatch(str(prepared.get("tail_digest")))
            else None
        )
        if (
            not isinstance(prepared, Mapping)
            or set(prepared) != HOST_AUTHORITY_TORN_TAIL_PREPARED_FIELDS
            or prepared.get("schema_version") != 1
            or prepared.get("kind") != HOST_AUTHORITY_TORN_TAIL_RECOVERY_KIND
            or prepared.get("status") != "PREPARED"
            or ledger_kind
            not in {
                "repository-registry",
                "provider-history",
                "capacity-history",
                "reservation-history",
                "scheduler-history",
                "host-kernel-history",
            }
            or not isinstance(ledger_path, str)
            or Path(ledger_path).is_absolute()
            or ".." in Path(ledger_path).parts
            or prepared.get("action") not in HOST_AUTHORITY_TORN_TAIL_ACTIONS
            or AUTHORITY_ID.fullmatch(str(prepared.get("raw_digest"))) is None
            or AUTHORITY_ID.fullmatch(str(prepared.get("prefix_digest"))) is None
            or AUTHORITY_ID.fullmatch(str(prepared.get("tail_digest"))) is None
            or AUTHORITY_ID.fullmatch(str(prepared.get("output_digest"))) is None
            or AUTHORITY_ID.fullmatch(
                str(prepared.get("host_kernel_generation"))
            )
            is None
            or AUTHORITY_ID.fullmatch(str(prepared.get("host_kernel_record_id")))
            is None
            or type(prepared.get("tail_bytes")) is not int
            or int(prepared["tail_bytes"]) < 1
            or not isinstance(prepared.get("actor"), str)
            or not str(prepared["actor"]).strip()
            or not isinstance(prepared.get("reason"), str)
            or not str(prepared["reason"]).strip()
            or AUTHORITY_ID.fullmatch(str(recovery_id)) is None
            or recovery_id != digest_json(recovery_material)
            or prepared_record_id != digest_json(prepared_material)
            or expected_directory is None
            or prepared_path.parent != expected_directory
            or prepared_path.name
            != str(recovery_id).removeprefix("sha256:") + ".prepared.json"
            or prepared.get("archive_path") != expected_archive
        ):
            raise ConfigurationError("host torn-tail PREPARED fence is invalid")
        archive_path = host_runtime_dir / str(prepared["archive_path"])
        archive = _read_regular_authority_bytes(
            archive_path, label="host torn-tail PREPARED archive"
        )
        if (
            len(archive) != prepared.get("tail_bytes")
            or "sha256:" + sha256(archive).hexdigest()
            != prepared.get("tail_digest")
        ):
            raise ConfigurationError("host torn-tail PREPARED archive changed")
        complete_path = prepared_path.with_name(
            str(recovery_id).removeprefix("sha256:") + ".complete.json"
        )
        if not complete_path.exists() and not _is_link_like(complete_path):
            pending.append(prepared_path)
            continue
        complete = read_strict_canonical_json(
            complete_path, label="host torn-tail COMPLETE fence"
        )
        complete_material = (
            dict(complete) if isinstance(complete, Mapping) else {}
        )
        complete_record_id = complete_material.pop("record_id", None)
        if (
            not isinstance(complete, Mapping)
            or set(complete) != HOST_AUTHORITY_TORN_TAIL_COMPLETE_FIELDS
            or complete.get("schema_version") != 1
            or complete.get("kind") != HOST_AUTHORITY_TORN_TAIL_COMPLETE_KIND
            or complete.get("status") != "COMPLETE"
            or complete.get("recovery_id") != recovery_id
            or complete.get("prepared_record_id") != prepared.get("record_id")
            or complete.get("ledger_kind") != prepared.get("ledger_kind")
            or complete.get("ledger_path") != prepared.get("ledger_path")
            or complete.get("prefix_digest") != prepared.get("prefix_digest")
            or complete.get("output_digest") != prepared.get("output_digest")
            or complete.get("action") != prepared.get("action")
            or complete.get("archive_path") != prepared.get("archive_path")
            or not isinstance(complete.get("completed_by"), str)
            or not str(complete["completed_by"]).strip()
            or complete_record_id != digest_json(complete_material)
        ):
            raise ConfigurationError("host torn-tail COMPLETE fence is invalid")
        try:
            parse_time(complete.get("completed_at"))
        except (TypeError, ValueError) as error:
            raise ConfigurationError(
                "host torn-tail COMPLETE fence time is invalid"
            ) from error
    return tuple(pending)


def _provably_incomplete_authority_json_tail(tail: bytes) -> bool:
    """Return true only for a syntactic prefix of canonical one-line JSON.

    ``JSONDecodeError.pos`` is not a prefix proof (for example ``{"a" x``
    reports an error at EOF-adjacent input).  This small recursive recognizer
    distinguishes an actually incomplete token/container from invalid complete
    syntax and also verifies the syntax preceding a partial UTF-8 code point.
    """

    if not tail or not tail.startswith(b"{"):
        return False

    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    try:
        text = decoder.decode(tail, final=False)
    except UnicodeDecodeError:
        return False
    pending_utf8 = bool(decoder.getstate()[0])

    class Incomplete(Exception):
        def __init__(self, string_prefix: str | None = None) -> None:
            super().__init__()
            self.string_prefix = string_prefix

    class Invalid(Exception):
        pass

    length = len(text)

    def need(position: int) -> str:
        if position >= length:
            raise Incomplete
        return text[position]

    def parse_string(position: int) -> int:
        start = position
        if need(position) != '"':
            raise Invalid
        position += 1
        decoded_prefix: list[str] = []
        while True:
            if position >= length:
                raise Incomplete("".join(decoded_prefix))
            character = text[position]
            if character == '"':
                end = position + 1
                token = text[start:end]
                try:
                    decoded = json.loads(token)
                    canonical = json.dumps(
                        decoded,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    )
                except (json.JSONDecodeError, TypeError, ValueError):
                    raise Invalid
                if not isinstance(decoded, str) or token != canonical:
                    raise Invalid
                return end
            if ord(character) < 0x20:
                raise Invalid
            if character != "\\":
                decoded_prefix.append(character)
                position += 1
                continue
            position += 1
            if position >= length:
                raise Incomplete("".join(decoded_prefix))
            escape = text[position]
            simple_escapes = {
                '"': '"',
                "\\": "\\",
                "b": "\b",
                "f": "\f",
                "n": "\n",
                "r": "\r",
                "t": "\t",
            }
            if escape in simple_escapes:
                decoded_prefix.append(simple_escapes[escape])
                position += 1
                continue
            if escape != "u":
                raise Invalid
            position += 1
            digits: list[str] = []
            for _ in range(4):
                if position >= length:
                    raise Incomplete("".join(decoded_prefix))
                if text[position] not in "0123456789abcdef":
                    raise Invalid
                digits.append(text[position])
                position += 1
            codepoint = int("".join(digits), 16)
            if codepoint >= 0x20 or codepoint in {8, 9, 10, 12, 13}:
                raise Invalid
            decoded_prefix.append(chr(codepoint))

    def parse_number(position: int) -> int:
        if need(position) == "-":
            position += 1
            need(position)
        if need(position) == "0":
            position += 1
            if position < length and text[position].isdigit():
                raise Invalid
        elif need(position) in "123456789":
            while position < length and text[position].isdigit():
                position += 1
        else:
            raise Invalid
        if position < length and text[position] == ".":
            position += 1
            if position >= length:
                raise Incomplete
            if not text[position].isdigit():
                raise Invalid
            while position < length and text[position].isdigit():
                position += 1
        if position < length and text[position] in "eE":
            position += 1
            if position >= length:
                raise Incomplete
            if text[position] in "+-":
                position += 1
                if position >= length:
                    raise Incomplete
            if not text[position].isdigit():
                raise Invalid
            while position < length and text[position].isdigit():
                position += 1
        return position

    def parse_value(position: int) -> int:
        character = need(position)
        if character == '"':
            return parse_string(position)
        if character == "{":
            return parse_object(position)
        if character == "[":
            return parse_array(position)
        if character in "-0123456789":
            return parse_number(position)
        for literal in ("true", "false", "null"):
            available = text[position : min(length, position + len(literal))]
            if literal.startswith(available):
                if len(available) < len(literal):
                    raise Incomplete
                return position + len(literal)
        raise Invalid

    def canonical_separator(position: int) -> int:
        if position >= length:
            raise Incomplete
        if text[position] != " ":
            raise Invalid
        return position + 1

    def parse_object(position: int) -> int:
        if need(position) != "{":
            raise Invalid
        position += 1
        if position >= length:
            raise Incomplete
        if text[position] == "}":
            return position + 1
        keys: set[str] = set()
        previous_key: str | None = None
        while True:
            key_start = position
            try:
                position = parse_string(position)
            except Incomplete as error:
                prefix = error.string_prefix
                if (
                    previous_key is not None
                    and prefix is not None
                    and prefix < previous_key
                    and not previous_key.startswith(prefix)
                ):
                    raise Invalid
                raise
            try:
                key = json.loads(text[key_start:position])
            except (json.JSONDecodeError, TypeError, ValueError):
                raise Invalid
            if (
                not isinstance(key, str)
                or key in keys
                or (previous_key is not None and key <= previous_key)
            ):
                raise Invalid
            keys.add(key)
            previous_key = key
            if need(position) != ":":
                raise Invalid
            position = canonical_separator(position + 1)
            position = parse_value(position)
            if position >= length:
                raise Incomplete
            if text[position] == "}":
                return position + 1
            if text[position] != ",":
                raise Invalid
            position = canonical_separator(position + 1)

    def parse_array(position: int) -> int:
        if need(position) != "[":
            raise Invalid
        position += 1
        if position >= length:
            raise Incomplete
        if text[position] == "]":
            return position + 1
        while True:
            position = parse_value(position)
            if position >= length:
                raise Incomplete
            if text[position] == "]":
                return position + 1
            if text[position] != ",":
                raise Invalid
            position = canonical_separator(position + 1)

    def classify(candidate: str) -> str:
        nonlocal text, length
        original_text, original_length = text, length
        text, length = candidate, len(candidate)
        try:
            end = parse_object(0)
            return "COMPLETE" if end == length else "INVALID"
        except Incomplete:
            return "INCOMPLETE"
        except Invalid:
            return "INVALID"
        finally:
            text, length = original_text, original_length

    classification = classify(text)
    if classification != "INCOMPLETE":
        return False
    if pending_utf8 and classify(text + "x") == "INVALID":
        return False
    return True


def _truncate_authenticated_authority_file(
    path: Path,
    *,
    expected: bytes,
    prefix: bytes,
) -> None:
    flags = (
        os.O_RDWR
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_BINARY", 0)
    )
    descriptor = os.open(path, flags)
    try:
        _verify_open_regular_file_identity(
            descriptor, path, label="host torn-tail recovery ledger"
        )
        chunks: list[bytes] = []
        os.lseek(descriptor, 0, os.SEEK_SET)
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        if b"".join(chunks) != expected:
            raise ConfigurationError(
                "host authority ledger changed during torn-tail recovery"
            )
        os.ftruncate(descriptor, len(prefix))
        os.fsync(descriptor)
        _verify_open_regular_file_identity(
            descriptor, path, label="host torn-tail recovery ledger"
        )
    finally:
        os.close(descriptor)
    _fsync_parent_directory(path.parent)


def _append_authenticated_authority_suffix(
    path: Path,
    *,
    expected: bytes,
    suffix: bytes,
) -> None:
    """Append an exact recovery suffix after revalidating handle, path and bytes."""

    if not suffix:
        raise ConfigurationError("host authority recovery suffix is empty")
    flags = (
        os.O_RDWR
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_BINARY", 0)
    )
    descriptor = os.open(path, flags)
    try:
        _verify_open_regular_file_identity(
            descriptor, path, label="host torn-tail recovery ledger"
        )
        chunks: list[bytes] = []
        os.lseek(descriptor, 0, os.SEEK_SET)
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        if b"".join(chunks) != expected:
            raise ConfigurationError(
                "host authority ledger changed during torn-tail recovery"
            )
        os.lseek(descriptor, 0, os.SEEK_END)
        offset = 0
        while offset < len(suffix):
            written = os.write(descriptor, suffix[offset:])
            if written <= 0:
                raise ConfigurationError(
                    "host authority recovery append made no progress"
                )
            offset += written
        os.fsync(descriptor)
        _verify_open_regular_file_identity(
            descriptor, path, label="host torn-tail recovery ledger"
        )
    finally:
        os.close(descriptor)
    _fsync_parent_directory(path.parent)


def recover_host_authority_jsonl_torn_tail(
    host_runtime_dir: str | Path,
    *,
    ledger_kind: str,
    actor: str,
    reason: str,
    host_id: str | None = None,
    completed_at: str | None = None,
) -> Mapping[str, object] | None:
    """Recover one provably incomplete host-global JSONL append.

    Exact tail bytes and a PREPARED receipt are fsynced before an opened-handle
    identity-checked truncation.  A second immutable COMPLETE receipt makes every
    crash boundary deterministic.  Complete-but-unterminated JSON, malformed
    interior lines and semantically invalid prefixes remain unrecoverable.
    """

    if ledger_kind not in {
        "repository-registry",
        "provider-history",
        "capacity-history",
        "reservation-history",
        "scheduler-history",
        "host-kernel-history",
    }:
        raise ConfigurationError("host torn-tail ledger kind is invalid")
    if not isinstance(actor, str) or not actor.strip():
        raise ConfigurationError("host torn-tail recovery actor is required")
    if not isinstance(reason, str) or not reason.strip():
        raise ConfigurationError("host torn-tail recovery reason is required")
    actor = actor.strip()
    reason = reason.strip()
    root = resolve_host_runtime_dir(host_runtime_dir)
    identity_path = root / "host-runtime-identity.json"
    lock_path = root / "locks" / "host-authority.lock"
    if not identity_path.is_file() or not lock_path.is_file():
        raise ConfigurationError("host runtime is absent")
    machine_user_id = _machine_user_identity()
    writer = _validate_host_runtime_identity(
        read_strict_canonical_json(
            identity_path,
            label="host torn-tail recovery writer",
            expected_fields=HOST_RUNTIME_IDENTITY_FIELDS,
        ),
        machine_user_id=machine_user_id,
    )
    current_kernel = host_kernel_identity()
    writer_matches_loaded_kernel = (
        writer.get("host_kernel_bundle_digest")
        == current_kernel.get("bundle_digest")
        and writer.get("interpreter_policy_digest")
        == current_kernel.get("interpreter_policy_digest")
    )
    if ledger_kind == "repository-registry":
        path = root / "repository-registry.jsonl"
    elif ledger_kind == "provider-history":
        path = root / "host-provider-history.jsonl"
    elif ledger_kind == "reservation-history":
        path = root / "host-reservations.jsonl"
    elif ledger_kind == "scheduler-history":
        if not isinstance(host_id, str) or not host_id.strip():
            raise ConfigurationError(
                "scheduler history recovery requires an authenticated host id"
            )
        path = root / "host-scheduler.jsonl"
    elif ledger_kind == "host-kernel-history":
        path = root / "host-kernel-history.jsonl"
    else:
        if not isinstance(host_id, str) or not host_id.strip():
            raise ConfigurationError(
                "capacity history recovery requires an authenticated host id"
            )
        path = host_capacity_path(root, host_id).parent / "capacity-history.jsonl"
    if not path.is_file() or _is_link_like(path):
        raise ConfigurationError("selected host authority ledger is unavailable")
    relative_path = str(path.relative_to(root)).replace("\\", "/")
    recovery_root = root / "torn-tail-recoveries" / digest_json(
        {"kind": ledger_kind, "path": relative_path}
    ).removeprefix("sha256:")

    def validate_prefix(prefix: bytes) -> tuple[Mapping[str, object], ...]:
        if ledger_kind == "repository-registry":
            return _host_repository_registry_events(root, raw_override=prefix)
        if ledger_kind == "reservation-history":
            return _host_reservation_events_unlocked(root, raw_override=prefix)
        if ledger_kind == "scheduler-history":
            events = _host_scheduler_events_unlocked(root, raw_override=prefix)
            if host_id is not None and any(
                event.get("host_id") != host_id for event in events
            ):
                raise ConfigurationError(
                    "scheduler-history prefix belongs to another host"
                )
            return events
        if ledger_kind == "capacity-history":
            assert host_id is not None
            history = _strict_capacity_history(path, raw_override=prefix)
            if any(event.get("host_id") != host_id for event in history):
                raise ConfigurationError(
                    "capacity-history prefix belongs to another authenticated host"
                )
            current_path = host_capacity_path(root, host_id)
            current: Mapping[str, object] | None = None
            if current_path.exists() or _is_link_like(current_path):
                current = _read_host_capacity_record(
                    root,
                    host_id,
                    now=datetime.max.replace(tzinfo=UTC),
                    require_live=False,
                    require_current_provider=False,
                    _writer_override=writer,
                )
            if current is None:
                if history and (
                    len(history) != 1
                    or history[0].get("previous_capacity_generation") is not None
                ):
                    raise ConfigurationError(
                        "capacity-history prefix is ahead of an absent current projection"
                    )
                return history
            if not history:
                raise ConfigurationError(
                    "capacity current projection has no authenticated history prefix"
                )
            head = history[-1]
            if head.get("capacity_record_id") == current.get("record_id"):
                return history
            pending_successor = (
                len(history) >= 2
                and history[-2].get("capacity_record_id")
                == current.get("record_id")
                and head.get("previous_capacity_generation")
                == current.get("capacity_generation")
            )
            if not pending_successor:
                raise ConfigurationError(
                    "capacity-history prefix differs from its current projection"
                )
            return history
        if ledger_kind == "host-kernel-history":
            history = _host_kernel_history(
                root,
                machine_user_id=machine_user_id,
                raw_override=prefix,
            )
            if not history or history[-1].get("identity") != writer:
                raise ConfigurationError(
                    "host-kernel valid prefix does not authenticate current writer"
                )
            return history
        provider_path = root / "host-provider.json"
        if not prefix:
            if provider_path.exists() or _is_link_like(provider_path):
                raise ConfigurationError(
                    "provider current record has no complete history prefix"
                )
            return ()
        provider = read_strict_canonical_json(
            provider_path, label="host provider current generation"
        )
        if not isinstance(provider, Mapping) or not isinstance(
            provider.get("host_id"), str
        ):
            raise ConfigurationError("host provider current generation is invalid")
        _host_provider_binding(
            root,
            host_id=str(provider["host_id"]),
            _history_raw_override=prefix,
            _allow_pending_history=True,
            _writer_override=writer,
        )
        return _strict_jsonl_records_bytes(
            prefix, label="host provider generation history"
        )

    def validate_prepared(value: object) -> Mapping[str, object]:
        if (
            not isinstance(value, Mapping)
            or set(value) != HOST_AUTHORITY_TORN_TAIL_PREPARED_FIELDS
        ):
            raise ConfigurationError("host torn-tail PREPARED receipt schema is invalid")
        material = dict(value)
        record_id = material.pop("record_id", None)
        recovery_material = {
            key: value[key]
            for key in (
                "ledger_kind",
                "ledger_path",
                "host_id",
                "raw_digest",
                "prefix_digest",
                "tail_digest",
                "tail_bytes",
                "action",
                "output_digest",
                "host_kernel_generation",
                "host_kernel_record_id",
            )
        }
        expected_host_id = (
            host_id
            if ledger_kind in {"capacity-history", "scheduler-history"}
            else None
        )
        expected_archive = (
            str(
                (
                    recovery_root
                    / (str(value.get("tail_digest")).removeprefix("sha256:") + ".bin")
                ).relative_to(root)
            ).replace("\\", "/")
            if AUTHORITY_ID.fullmatch(str(value.get("tail_digest"))) is not None
            else None
        )
        if (
            value.get("schema_version") != 1
            or value.get("kind") != HOST_AUTHORITY_TORN_TAIL_RECOVERY_KIND
            or value.get("status") != "PREPARED"
            or value.get("ledger_kind") != ledger_kind
            or value.get("ledger_path") != relative_path
            or value.get("host_id") != expected_host_id
            or value.get("archive_path") != expected_archive
            or value.get("host_kernel_generation")
            != writer.get("host_kernel_generation")
            or value.get("host_kernel_record_id") != writer.get("record_id")
            or value.get("action") not in HOST_AUTHORITY_TORN_TAIL_ACTIONS
            or AUTHORITY_ID.fullmatch(str(value.get("raw_digest"))) is None
            or AUTHORITY_ID.fullmatch(str(value.get("prefix_digest"))) is None
            or AUTHORITY_ID.fullmatch(str(value.get("tail_digest"))) is None
            or AUTHORITY_ID.fullmatch(str(value.get("output_digest"))) is None
            or type(value.get("tail_bytes")) is not int
            or int(value["tail_bytes"]) < 1
            or value.get("actor") != actor
            or value.get("reason") != reason
            or value.get("recovery_id") != digest_json(recovery_material)
            or record_id != digest_json(material)
        ):
            raise ConfigurationError("host torn-tail PREPARED receipt is invalid")
        return dict(value)

    def complete_recovery(
        prepared: Mapping[str, object], output: bytes
    ) -> Mapping[str, object]:
        archive_path = root / str(prepared["archive_path"])
        archive = _read_regular_authority_bytes(
            archive_path, label="host torn-tail archived bytes"
        )
        if (
            "sha256:" + sha256(archive).hexdigest() != prepared.get("tail_digest")
            or len(archive) != prepared.get("tail_bytes")
        ):
            raise ConfigurationError("host torn-tail archive evidence changed")
        complete_path = recovery_root / (
            str(prepared["recovery_id"]).removeprefix("sha256:") + ".complete.json"
        )
        if complete_path.exists() or _is_link_like(complete_path):
            installed = read_strict_canonical_json(
                complete_path, label="host torn-tail COMPLETE receipt"
            )
            installed_material = dict(installed) if isinstance(installed, Mapping) else {}
            installed_record_id = installed_material.pop("record_id", None)
            if (
                not isinstance(installed, Mapping)
                or set(installed) != HOST_AUTHORITY_TORN_TAIL_COMPLETE_FIELDS
                or installed.get("schema_version") != 1
                or installed.get("kind")
                != HOST_AUTHORITY_TORN_TAIL_COMPLETE_KIND
                or installed.get("status") != "COMPLETE"
                or installed.get("recovery_id") != prepared.get("recovery_id")
                or installed.get("prepared_record_id") != prepared.get("record_id")
                or installed.get("ledger_kind") != ledger_kind
                or installed.get("ledger_path") != relative_path
                or installed.get("prefix_digest")
                != prepared.get("prefix_digest")
                or installed.get("output_digest")
                != "sha256:" + sha256(output).hexdigest()
                or installed.get("output_digest")
                != prepared.get("output_digest")
                or installed.get("action") != prepared.get("action")
                or installed.get("archive_path") != prepared.get("archive_path")
                or installed_record_id != digest_json(installed_material)
            ):
                raise ConfigurationError("host torn-tail COMPLETE receipt is invalid")
            parse_time(installed.get("completed_at"))
            return dict(installed)
        completion_time = completed_at or format_time(utc_now())
        parse_time(completion_time)
        complete_material: dict[str, object] = {
            "schema_version": 1,
            "kind": HOST_AUTHORITY_TORN_TAIL_COMPLETE_KIND,
            "status": "COMPLETE",
            "recovery_id": prepared["recovery_id"],
            "prepared_record_id": prepared["record_id"],
            "ledger_kind": ledger_kind,
            "ledger_path": relative_path,
            "prefix_digest": prepared["prefix_digest"],
            "output_digest": prepared["output_digest"],
            "action": prepared["action"],
            "archive_path": prepared["archive_path"],
            "completed_by": actor,
            "completed_at": completion_time,
        }
        complete = {**complete_material, "record_id": digest_json(complete_material)}
        exclusive_write_json_or_identical(complete_path, complete)
        installed = read_strict_canonical_json(
            complete_path,
            label="host torn-tail COMPLETE receipt",
            expected_fields=set(complete),
        )
        if installed != complete:
            raise ConfigurationError("host torn-tail COMPLETE receipt changed")
        return complete

    with runtime_file_lock(lock_path, timeout_seconds=120.0):
        # The pre-lock check is only a fast rejection.  A waiter may have been
        # queued behind a host-kernel upgrade, so authenticate the writer again
        # after acquiring authority and require the same generation/record that
        # selected this recovery operation.  A retired process writes zero
        # bytes even if it began waiting while it was current.
        locked_writer = _validate_host_runtime_identity(
            read_strict_canonical_json(
                identity_path,
                label="host torn-tail locked writer",
                expected_fields=HOST_RUNTIME_IDENTITY_FIELDS,
            ),
            machine_user_id=machine_user_id,
        )
        if (root / KERNEL_TRANSITION_POINTER).exists() or _is_link_like(
            root / KERNEL_TRANSITION_POINTER
        ):
            raise ConfigurationError(
                "host-kernel transition prevents unrelated torn-tail recovery"
            )
        locked_kernel = host_kernel_identity()
        if (
            locked_writer.get("host_kernel_generation")
            != writer.get("host_kernel_generation")
            or locked_writer.get("record_id") != writer.get("record_id")
        ):
            raise ConfigurationError(
                "host-kernel writer changed while torn-tail recovery waited"
            )
        writer = locked_writer
        writer_matches_loaded_kernel = (
            locked_writer.get("host_kernel_bundle_digest")
            == locked_kernel.get("bundle_digest")
            and locked_writer.get("interpreter_policy_digest")
            == locked_kernel.get("interpreter_policy_digest")
        )
        if ledger_kind != "host-kernel-history":
            writer_history = _host_kernel_history(
                root, machine_user_id=machine_user_id
            )
            if not writer_history or writer_history[-1].get("identity") != writer:
                raise ConfigurationError(
                    "host-kernel history is pending; unrelated recovery is fenced"
                )
        raw = _read_regular_authority_bytes(path, label="host authority torn-tail ledger")
        if not raw or raw.endswith(b"\n"):
            validate_prefix(raw)
            if not recovery_root.is_dir():
                return None
            pending: list[Mapping[str, object]] = []
            for prepared_path in sorted(recovery_root.glob("*.prepared.json")):
                candidate = validate_prepared(
                    read_strict_canonical_json(
                        prepared_path, label="host torn-tail PREPARED receipt"
                    )
                )
                if candidate.get("output_digest") == (
                    "sha256:" + sha256(raw).hexdigest()
                ):
                    complete_path = recovery_root / (
                        str(candidate["recovery_id"]).removeprefix("sha256:")
                        + ".complete.json"
                    )
                    if complete_path.exists() or _is_link_like(complete_path):
                        complete_recovery(candidate, raw)
                        continue
                    pending.append(candidate)
            if not pending:
                return None
            if len(pending) != 1:
                raise ConfigurationError(
                    "host torn-tail recovery has ambiguous PREPARED receipts"
                )
            return complete_recovery(pending[0], raw)
        split = raw.rfind(b"\n") + 1
        prefix = raw[:split]
        tail = raw[split:]
        if _provably_incomplete_authority_json_tail(tail):
            action = "TRUNCATE"
            output = prefix
            validate_prefix(prefix)
        else:
            # Losing only the final newline is a normal append crash boundary.
            # It is recoverable only when the exact completed row extends the
            # authenticated reducer; malformed or semantically impossible JSON
            # remains fail-closed.
            action = "APPEND_NEWLINE"
            output = raw + b"\n"
            try:
                validate_prefix(output)
            except ConfigurationError as error:
                raise ConfigurationError(
                    "host authority final bytes are neither a provable JSON prefix "
                    "nor an authenticated complete record missing its newline"
                ) from error
        raw_digest = "sha256:" + sha256(raw).hexdigest()
        prefix_digest = "sha256:" + sha256(prefix).hexdigest()
        tail_digest = "sha256:" + sha256(tail).hexdigest()
        archive_path = recovery_root / (tail_digest.removeprefix("sha256:") + ".bin")
        archive_relative = str(archive_path.relative_to(root)).replace("\\", "/")
        recovery_material = {
            "ledger_kind": ledger_kind,
            "ledger_path": relative_path,
            "host_id": (
                host_id
                if ledger_kind in {"capacity-history", "scheduler-history"}
                else None
            ),
            "raw_digest": raw_digest,
            "prefix_digest": prefix_digest,
            "tail_digest": tail_digest,
            "tail_bytes": len(tail),
            "action": action,
            "output_digest": "sha256:" + sha256(output).hexdigest(),
            "host_kernel_generation": writer["host_kernel_generation"],
            "host_kernel_record_id": writer["record_id"],
        }
        prepared_material: dict[str, object] = {
            "schema_version": 1,
            "kind": HOST_AUTHORITY_TORN_TAIL_RECOVERY_KIND,
            "status": "PREPARED",
            **recovery_material,
            "archive_path": archive_relative,
            "actor": actor,
            "reason": reason,
            "recovery_id": digest_json(recovery_material),
        }
        prepared = {
            **prepared_material,
            "record_id": digest_json(prepared_material),
        }
        prepared_path = recovery_root / (
            str(prepared["recovery_id"]).removeprefix("sha256:")
            + ".prepared.json"
        )
        if not writer_matches_loaded_kernel and not (
            prepared_path.exists() or _is_link_like(prepared_path)
        ):
            raise ConfigurationError(
                "a successor host kernel may complete only an existing exact "
                "torn-tail recovery capability"
            )
        exclusive_write_bytes_or_identical(archive_path, tail)
        if _read_regular_authority_bytes(
            archive_path, label="host torn-tail archived bytes"
        ) != tail:
            raise ConfigurationError("host torn-tail archive bytes changed")
        exclusive_write_json_or_identical(prepared_path, prepared)
        validate_prepared(
            read_strict_canonical_json(
                prepared_path, label="host torn-tail PREPARED receipt"
            )
        )
        if _read_regular_authority_bytes(
            path, label="host authority torn-tail ledger"
        ) != raw:
            raise ConfigurationError(
                "host authority ledger changed before torn-tail truncation"
            )
        if action == "TRUNCATE":
            _truncate_authenticated_authority_file(
                path, expected=raw, prefix=prefix
            )
        else:
            _append_authenticated_authority_suffix(
                path, expected=raw, suffix=b"\n"
            )
        if _read_regular_authority_bytes(
            path, label="host authority recovered ledger"
        ) != output:
            raise ConfigurationError("host authority recovery mutation was not durable")
        validate_prefix(output)
        return complete_recovery(prepared, output)


def _scope_conflicts(first: Sequence[str], second: Sequence[str]) -> bool:
    try:
        return any(scopes_overlap(left, right) for left in first for right in second)
    except ValueError as error:
        raise ConfigurationError("host reservation scope is invalid") from error


def reserve_global_host_session(
    host_runtime_dir: str | Path,
    *,
    repository: str,
    execution_id: str,
    host_id: str,
    capacity_generation: str,
    local_reservation_id: str,
    reservation_kind: str,
    resource_key: str,
    write_scopes: Sequence[str],
    actor_time: str,
    expires_at: str,
    now: datetime,
    execution_adapter_identity: Mapping[str, object] | None = None,
    host_scheduler_grant_id: str | None = None,
    policy_cap: int | None = None,
) -> Mapping[str, object]:
    root = require_host_runtime(host_runtime_dir)
    lock_path = root / "locks" / "host-authority.lock"
    if not runtime_file_lock_is_held(lock_path):
        raise ConfigurationError("host reservation requires outer host authority")
    writer = _host_runtime_identity_unlocked(root)
    capacity = read_host_capacity(root, host_id, now=now)
    if capacity.get("capacity_generation") != capacity_generation:
        raise ConfigurationError("host reservation capacity generation is stale")
    if capacity.get("host_kernel_generation") != writer.get(
        "host_kernel_generation"
    ):
        raise ConfigurationError("host reservation capacity uses a retired writer")
    capacity_epoch = int(capacity["capacity_epoch"])
    maximum = int(capacity["max_total_sessions"])
    if policy_cap is not None:
        if type(policy_cap) is not int or policy_cap < 1:
            raise ConfigurationError("host reservation policy cap is invalid")
        maximum = min(maximum, policy_cap)
    if (
        not isinstance(repository, str)
        or not repository.strip()
        or AUTHORITY_ID.fullmatch(execution_id) is None
        or AUTHORITY_ID.fullmatch(local_reservation_id) is None
        or AUTHORITY_ID.fullmatch(resource_key) is None
        or reservation_kind not in HOST_RESERVATION_KINDS
    ):
        raise ConfigurationError("host reservation coordinates are invalid")
    try:
        reserved_time = parse_time(actor_time)
        reservation_expiry = parse_time(expires_at)
    except (TypeError, ValueError) as error:
        raise ConfigurationError("host reservation time bounds are invalid") from error
    if reserved_time > now or reservation_expiry <= now or reservation_expiry <= reserved_time:
        raise ConfigurationError("host reservation lifetime is stale or invalid")
    try:
        normalized_scopes = [normalize_path(item) for item in write_scopes]
    except ValueError as error:
        raise ConfigurationError("host reservation scope is invalid") from error
    if reservation_kind == "VALIDATION":
        if normalized_scopes:
            raise ConfigurationError("validation reservations cannot own write scopes")
        adapter_coordinates: dict[str, object] = {
            "execution_adapter_identity_record_id": None,
            "execution_adapter_identity_path": None,
            "execution_adapter_identity_blob_digest": None,
        }
        if host_scheduler_grant_id is not None:
            raise ConfigurationError(
                "internal validation cannot consume an external scheduler grant"
            )
    else:
        if not isinstance(execution_adapter_identity, Mapping):
            raise ConfigurationError(
                "external host reservation requires an execution adapter identity"
            )
        adapter_record_id = execution_adapter_identity.get("record_id")
        if AUTHORITY_ID.fullmatch(str(adapter_record_id)) is None:
            raise ConfigurationError("execution adapter identity id is invalid")
        installed_adapter = read_execution_adapter_identity(
            root, str(adapter_record_id)
        )
        if installed_adapter != execution_adapter_identity or any(
            installed_adapter.get(field) != expected
            for field, expected in {
                "repository": repository,
                "execution_id": execution_id,
                "host_id": host_id,
                "provider_generation": capacity["provider_generation"],
                "provider_epoch": capacity["provider_epoch"],
            }.items()
        ):
            raise ConfigurationError(
                "execution adapter identity differs from reservation authority"
            )
        adapter_path = (
            root
            / "execution-adapter-bindings"
            / (str(adapter_record_id).removeprefix("sha256:") + ".json")
        )
        adapter_raw = _read_regular_authority_bytes(
            adapter_path, label="execution adapter binding evidence"
        )
        adapter_coordinates = {
            "execution_adapter_identity_record_id": adapter_record_id,
            "execution_adapter_identity_path": str(
                adapter_path.relative_to(root)
            ).replace("\\", "/"),
            "execution_adapter_identity_blob_digest": "sha256:"
            + sha256(adapter_raw).hexdigest(),
        }
        if AUTHORITY_ID.fullmatch(str(host_scheduler_grant_id)) is None:
            raise ConfigurationError(
                "primary and sidecar reservations require an exact scheduler grant"
            )
        scheduler = _host_scheduler_projection_unlocked(root, host_id=host_id)
        grant = scheduler["outstanding_grants"].get(str(host_scheduler_grant_id))
        if not isinstance(grant, Mapping):
            raise ConfigurationError(
                "host scheduler grant is absent, expired, or already consumed"
            )
        demand = scheduler["demands"].get(str(grant.get("demand_id")))
        if (
            not isinstance(demand, Mapping)
            or parse_time(grant.get("expires_at")) <= now
            or any(
                grant.get(field) != expected
                for field, expected in {
                    "host_id": host_id,
                    "host_kernel_generation": writer["host_kernel_generation"],
                    "capacity_generation": capacity_generation,
                    "execution_id": execution_id,
                    "local_reservation_id": local_reservation_id,
                }.items()
            )
            or any(
                demand.get(field) != expected
                for field, expected in {
                    "host_id": host_id,
                    "repository": repository,
                    "execution_id": execution_id,
                    "host_kernel_generation": writer["host_kernel_generation"],
                    "capacity_generation": capacity_generation,
                    "execution_adapter_identity_record_id": adapter_record_id,
                    "execution_adapter_identity_path": adapter_coordinates[
                        "execution_adapter_identity_path"
                    ],
                    "execution_adapter_identity_blob_digest": adapter_coordinates[
                        "execution_adapter_identity_blob_digest"
                    ],
                }.items()
            )
        ):
            raise ConfigurationError(
                "host scheduler grant differs from reservation authority"
            )
    reservation_id = digest_json(
        {
            "kind": "hive-mind-host-reservation-key-v1",
            "repository": repository,
            "execution_id": execution_id,
            "host_id": host_id,
            "provider_generation": capacity["provider_generation"],
            "capacity_generation": capacity_generation,
            "local_reservation_id": local_reservation_id,
            "reservation_kind": reservation_kind,
            "host_kernel_generation": writer["host_kernel_generation"],
            "execution_adapter_identity_record_id": adapter_coordinates[
                "execution_adapter_identity_record_id"
            ],
            "host_scheduler_grant_id": host_scheduler_grant_id,
        }
    )
    events = list(_host_reservation_events_unlocked(root))
    active = {
        str(event["reservation_id"]): event
        for event in events
        if event.get("state") in HOST_RESERVATION_ACTIVE_STATES
    }
    # Replay active state rather than selecting all historical RESERVED events.
    latest: dict[str, Mapping[str, object]] = {}
    for event in events:
        latest[str(event["reservation_id"])] = event
    active = {
        key: event
        for key, event in latest.items()
        if event.get("state") in HOST_RESERVATION_ACTIVE_STATES
    }
    logical_matches = [
        event
        for event in active.values()
        if event.get("repository") == repository
        and event.get("execution_id") == execution_id
        and event.get("local_reservation_id") == local_reservation_id
        and event.get("reservation_kind") == reservation_kind
    ]
    if any(event.get("reservation_id") != reservation_id for event in logical_matches):
        raise ConfigurationError(
            "an active legacy or retired-writer permit already owns these local coordinates; "
            "explicitly reconcile it before reserving a successor"
        )
    if len(logical_matches) > 1:
        raise ConfigurationError(
            "host reservation ledger contains duplicate active logical coordinates"
        )
    existing = active.get(reservation_id)
    candidate = {
        "state": "RESERVED",
        "reservation_id": reservation_id,
        "reservation_kind": reservation_kind,
        "repository": repository,
        "execution_id": execution_id,
        "host_id": host_id,
        "provider_generation": capacity["provider_generation"],
        "provider_epoch": capacity["provider_epoch"],
        "capacity_generation": capacity_generation,
        "capacity_epoch": capacity_epoch,
        "host_kernel_generation": writer["host_kernel_generation"],
        **adapter_coordinates,
        "host_scheduler_grant_id": host_scheduler_grant_id,
        "local_reservation_id": local_reservation_id,
        "resource_key": resource_key,
        "write_scopes": normalized_scopes,
        "reserved_at": actor_time,
        "expires_at": expires_at,
    }
    if existing is not None:
        if all(existing.get(key) == value for key, value in candidate.items()):
            return existing
        raise ConfigurationError("host reservation replay conflicts with active generation")
    # Capacity belongs to this machine-user kernel, not to a caller-selected
    # host-id partition. The provider binding above permits only its one sealed
    # host id, and every repository/execution consumes the same aggregate.
    kernel_active = list(active.values())
    scheduler_outstanding = _host_scheduler_projection_unlocked(
        root, host_id=host_id
    )["outstanding_grants"]
    if len(kernel_active) + len(scheduler_outstanding) > maximum:
        raise ConfigurationError(
            "host reservation and scheduler grant authority exceed capacity"
        )
    if reservation_kind == "VALIDATION" and (
        len(kernel_active) + len(scheduler_outstanding) >= maximum
    ):
        raise CapacityAdmissionDenied("authenticated host capacity is exhausted")
    if reservation_kind != "VALIDATION" and len(kernel_active) >= maximum:
        raise CapacityAdmissionDenied("authenticated host capacity is exhausted")
    if reservation_kind == "VALIDATION":
        validation_active = [
            event
            for event in kernel_active
            if event.get("reservation_kind") == "VALIDATION"
        ]
        if len(validation_active) >= int(capacity["validation_slots"]):
            raise CapacityAdmissionDenied(
                "authenticated host validation capacity is exhausted"
            )
    for other in active.values():
        if other.get("execution_id") == execution_id:
            continue
        if other.get("repository") != repository:
            continue
        if other.get("resource_key") == resource_key or _scope_conflicts(
            normalized_scopes, list(other.get("write_scopes", []))
        ):
            raise ConfigurationError(
                "cross-namespace host reservation conflicts with active repository scope"
            )
    return _append_host_reservation_unlocked(root, candidate, events)


def renew_global_host_session(
    host_runtime_dir: str | Path,
    reservation_id: str,
    *,
    execution_id: str,
    local_reservation_id: str,
    capacity_generation: str,
    actor: str,
    reason: str,
    renewed_at: str,
    expires_at: str,
    now: datetime,
    execution_adapter_identity: Mapping[str, object] | None = None,
) -> Mapping[str, object]:
    """Extend one live permit under the same authenticated capacity generation."""

    root = require_host_runtime(host_runtime_dir)
    lock_path = root / "locks" / "host-authority.lock"
    if not runtime_file_lock_is_held(lock_path):
        raise ConfigurationError("host reservation renewal requires host authority")
    if (
        AUTHORITY_ID.fullmatch(reservation_id) is None
        or not isinstance(actor, str)
        or not actor.strip()
        or not isinstance(reason, str)
        or not reason.strip()
    ):
        raise ConfigurationError("host reservation renewal evidence is invalid")
    events = list(_host_reservation_events_unlocked(root))
    prior = next(
        (event for event in reversed(events) if event.get("reservation_id") == reservation_id),
        None,
    )
    if prior is None:
        raise ConfigurationError("host reservation is absent")
    if any(
        prior.get(field) != expected
        for field, expected in {
            "execution_id": execution_id,
            "local_reservation_id": local_reservation_id,
            "capacity_generation": capacity_generation,
        }.items()
    ):
        raise ConfigurationError("host reservation renewal fence mismatch")
    if prior.get("state") not in HOST_RESERVATION_ACTIVE_STATES:
        raise ConfigurationError("only an active host reservation can be renewed")
    writer = _host_runtime_identity_unlocked(root)
    provider = _host_provider_binding(root, host_id=str(prior["host_id"]))
    adapter_record_id = prior.get("execution_adapter_identity_record_id")
    if prior.get("reservation_kind") == "VALIDATION":
        if execution_adapter_identity is not None or adapter_record_id is not None:
            raise ConfigurationError(
                "internal validation renewal cannot claim an external adapter"
            )
    else:
        if not isinstance(execution_adapter_identity, Mapping) or not isinstance(
            adapter_record_id, str
        ):
            raise ConfigurationError(
                "host reservation renewal requires its exact execution adapter identity"
            )
        installed_adapter = read_execution_adapter_identity(root, adapter_record_id)
        adapter_path = (
            root
            / "execution-adapter-bindings"
            / (adapter_record_id.removeprefix("sha256:") + ".json")
        )
        adapter_raw = _read_regular_authority_bytes(
            adapter_path, label="host reservation renewal adapter identity"
        )
        if (
            dict(execution_adapter_identity) != installed_adapter
            or any(
                prior.get(field) != installed_adapter.get(expected_field)
                for field, expected_field in (
                    ("execution_adapter_identity_record_id", "record_id"),
                    ("repository", "repository"),
                    ("execution_id", "execution_id"),
                    ("host_id", "host_id"),
                    ("provider_generation", "provider_generation"),
                    ("provider_epoch", "provider_epoch"),
                )
            )
            or prior.get("execution_adapter_identity_path")
            != str(adapter_path.relative_to(root)).replace("\\", "/")
            or prior.get("execution_adapter_identity_blob_digest")
            != "sha256:" + sha256(adapter_raw).hexdigest()
            or prior.get("host_kernel_generation")
            != writer.get("host_kernel_generation")
            or provider.get("host_kernel_generation")
            != writer.get("host_kernel_generation")
            or provider.get("provider_generation")
            != prior.get("provider_generation")
            or provider.get("provider_epoch") != prior.get("provider_epoch")
            or provider.get("provider_identity_digest")
            != installed_adapter.get("provider_identity_digest")
        ):
            raise ConfigurationError(
                "host reservation renewal adapter or writer fence changed"
            )
    try:
        renewed_time = parse_time(renewed_at)
        requested_expiry = parse_time(expires_at)
        prior_expiry = parse_time(prior.get("expires_at"))
    except (TypeError, ValueError) as error:
        raise ConfigurationError("host reservation renewal bounds are malformed") from error
    if renewed_time > now or prior_expiry <= now:
        raise ConfigurationError(
            "expired host reservation requires lifecycle reconciliation, not renewal"
        )
    if requested_expiry <= prior_expiry or requested_expiry <= now:
        raise ConfigurationError("host reservation renewal does not extend the live lease")
    capacity = read_host_capacity(root, str(prior["host_id"]), now=now)
    if (
        capacity.get("capacity_generation") != capacity_generation
        or int(capacity["capacity_epoch"]) != int(prior["capacity_epoch"])
        or capacity.get("host_kernel_generation")
        != writer.get("host_kernel_generation")
        or capacity.get("provider_generation")
        != provider.get("provider_generation")
        or capacity.get("provider_epoch") != provider.get("provider_epoch")
    ):
        raise ConfigurationError("host reservation renewal capacity fence is stale")
    if requested_expiry > parse_time(capacity.get("expires_at")):
        raise ConfigurationError("host reservation cannot outlive host capacity authority")
    payload = {
        key: value
        for key, value in prior.items()
        if key
        not in {
            "schema_version",
            "kind",
            "state",
            "expires_at",
            "renewed_at",
            "renewal_actor",
            "renewal_reason",
            "prior_expires_at",
            "renewal_count",
            "previous_event_id",
            "event_id",
        }
    }
    prior_count = int(prior.get("renewal_count", 0))
    return _append_host_reservation_unlocked(
        root,
        {
            "state": "RENEWED",
            **payload,
            "expires_at": expires_at,
            "renewed_at": renewed_at,
            "renewal_actor": actor,
            "renewal_reason": reason,
            "prior_expires_at": str(prior["expires_at"]),
            "renewal_count": prior_count + 1,
        },
        events,
    )


def _complete_same_policy_capacity_renewal_unlocked(
    root: Path,
    *,
    host_id: str,
    pending: Mapping[str, object],
    current: Mapping[str, object],
    now: datetime,
) -> Mapping[str, object]:
    """Finish one history-sealed renewal after any writer crash boundary."""

    if pending.get("rotation_reason") != "SAME_POLICY_RENEWAL":
        raise ConfigurationError("host capacity renewal receipt kind is invalid")
    sealed_candidate = pending.get("capacity_record")
    if not isinstance(sealed_candidate, Mapping):
        raise ConfigurationError("host capacity renewal candidate is missing")
    candidate = validate_host_capacity(
        sealed_candidate,
        host_id=host_id,
        now=now,
    )
    if (
        current.get("capacity_generation")
        != candidate.get("capacity_generation")
        or current.get("provider_generation")
        != candidate.get("provider_generation")
        or current.get("provider_epoch") != candidate.get("provider_epoch")
        or current.get("capacity_epoch") != candidate.get("capacity_epoch")
        or current.get("record_id")
        not in {
            pending.get("previous_capacity_record_id"),
            pending.get("capacity_record_id"),
        }
        or pending.get("capacity_record_id") != candidate.get("record_id")
    ):
        raise ConfigurationError(
            "host capacity renewal current/candidate lineage is inconsistent"
        )
    capacity_path = host_capacity_path(root, host_id)
    if current.get("record_id") != candidate.get("record_id"):
        atomic_write_json(capacity_path, candidate)

    all_events = list(_host_reservation_events_unlocked(root))
    by_event = {str(event["event_id"]): event for event in all_events}
    latest_by_reservation: dict[str, Mapping[str, object]] = {}
    for event in all_events:
        latest_by_reservation[str(event["reservation_id"])] = event
    active_event_ids = pending.get("active_reservation_event_ids")
    if not isinstance(active_event_ids, list):
        raise ConfigurationError("host capacity renewal active cut is malformed")
    actor = pending.get("renewal_actor")
    if not isinstance(actor, str) or not actor.strip():
        raise ConfigurationError("host capacity renewal actor is malformed")
    for event_id in active_event_ids:
        predecessor = by_event.get(str(event_id))
        if predecessor is None:
            raise ConfigurationError(
                "host capacity renewal predecessor reservation is missing"
            )
        reservation_id = str(predecessor["reservation_id"])
        latest = latest_by_reservation.get(reservation_id)
        if latest is None:
            raise ConfigurationError("host reservation disappeared during renewal")
        if latest.get("state") not in HOST_RESERVATION_ACTIVE_STATES:
            continue
        if (
            latest.get("expires_at") == candidate.get("expires_at")
            and latest.get("renewal_reason") == "SAME_POLICY_CAPACITY_RENEWAL"
        ):
            continue
        if latest.get("event_id") != event_id:
            raise ConfigurationError(
                "host reservation changed outside its capacity renewal transaction"
            )
        payload = {
            key: value
            for key, value in latest.items()
            if key
            not in {
                "schema_version",
                "kind",
                "state",
                "expires_at",
                "renewed_at",
                "renewal_actor",
                "renewal_reason",
                "prior_expires_at",
                "renewal_count",
                "previous_event_id",
                "event_id",
            }
        }
        renewed = _append_host_reservation_unlocked(
            root,
            {
                "state": "RENEWED",
                **payload,
                "expires_at": str(candidate["expires_at"]),
                "renewed_at": str(candidate["issued_at"]),
                "renewal_actor": actor,
                "renewal_reason": "SAME_POLICY_CAPACITY_RENEWAL",
                "prior_expires_at": str(latest["expires_at"]),
                "renewal_count": int(latest.get("renewal_count", 0)) + 1,
            },
            all_events,
        )
        all_events.append(renewed)
        latest_by_reservation[reservation_id] = renewed
    return candidate


def reconcile_pending_host_capacity_renewal(
    host_runtime_dir: str | Path,
    *,
    host_id: str,
    now: datetime,
) -> Mapping[str, object]:
    """Complete a history-first same-policy renewal before any admission read.

    The caller must hold ``host-authority.lock``.  Returning without appending is
    safe only after the last renewal's exact active-reservation cut has either
    been renewed to the successor expiry or reached a separately authenticated
    terminal state.
    """

    root = require_host_runtime(host_runtime_dir)
    if not runtime_file_lock_is_held(root / "locks" / "host-authority.lock"):
        raise ConfigurationError(
            "host capacity renewal reconciliation requires host authority"
        )
    current = _read_host_capacity_record(
        root,
        host_id,
        now=now,
        require_live=False,
    )
    history_path = host_capacity_path(root, host_id).parent / "capacity-history.jsonl"
    history = _strict_capacity_history(history_path) if history_path.is_file() else ()
    pending = (
        history[-1]
        if history
        and history[-1].get("rotation_reason") == "SAME_POLICY_RENEWAL"
        and history[-1].get("capacity_generation")
        == current.get("capacity_generation")
        else None
    )
    if pending is None:
        return dict(current)
    return _complete_same_policy_capacity_renewal_unlocked(
        root,
        host_id=host_id,
        pending=pending,
        current=current,
        now=now,
    )


def host_capacity_record_in_current_lineage(
    host_runtime_dir: str | Path,
    host_id: str,
    *,
    capacity_generation: str,
    record_id: str,
) -> Mapping[str, object]:
    """Authenticate one issuance record against the installed renewal lineage."""

    root = require_host_runtime(host_runtime_dir)
    if not runtime_file_lock_is_held(root / "locks" / "host-authority.lock"):
        raise ConfigurationError("host capacity lineage read requires host authority")
    if (
        AUTHORITY_ID.fullmatch(capacity_generation) is None
        or AUTHORITY_ID.fullmatch(record_id) is None
    ):
        raise ConfigurationError("host capacity lineage identity is invalid")
    current = _read_host_capacity_record(
        root,
        host_id,
        now=utc_now(),
        require_live=False,
    )
    if current.get("capacity_generation") != capacity_generation:
        raise ConfigurationError("host capacity lineage generation is not current")
    history_path = host_capacity_path(root, host_id).parent / "capacity-history.jsonl"
    history = _strict_capacity_history(history_path) if history_path.is_file() else ()
    generation_events: list[Mapping[str, object]] = []
    for event in reversed(history):
        if event.get("capacity_generation") != capacity_generation:
            if generation_events:
                break
            continue
        generation_events.append(event)
        if event.get("rotation_reason") != "SAME_POLICY_RENEWAL":
            break
    generation_events.reverse()
    if (
        not generation_events
        or generation_events[-1].get("capacity_record_id")
        != current.get("record_id")
    ):
        raise ConfigurationError(
            "installed host capacity is not the authenticated history head"
        )
    matching = [
        event
        for event in generation_events
        if event.get("capacity_record_id") == record_id
    ]
    if len(matching) != 1:
        raise ConfigurationError(
            "host capacity issuance record is outside the current lineage"
        )
    record = matching[0].get("capacity_record")
    if not isinstance(record, Mapping):
        if current.get("record_id") == record_id:
            return dict(current)
        raise ConfigurationError(
            "historical host capacity issuance bytes are unavailable"
        )
    validated = validate_host_capacity(
        record,
        host_id=host_id,
        now=datetime.max.replace(tzinfo=UTC),
        require_live=False,
    )
    if (
        validated.get("record_id") != record_id
        or validated.get("capacity_generation") != capacity_generation
    ):
        raise ConfigurationError("host capacity issuance record is malformed")
    return validated


def renew_host_capacity_authority(
    host_runtime_dir: str | Path,
    *,
    host_id: str,
    capacity_generation: str,
    expected_capacity_record_id: str,
    issued_at: str,
    expires_at: str,
    capability_source: str,
    capability_digest: str,
    provider_identity_source: str,
    provider_identity_digest: str,
    actor: str,
    now: datetime,
) -> Mapping[str, object]:
    """Extend one unchanged provider/policy and every live bound permit.

    This is a short host-kernel transaction for polling long-running work.  It
    does not rotate provider, generation, epoch, limits, or provenance.  A
    history-first candidate seals the exact active reservation cut so a crash
    can finish the same extension after the predecessor wall-clock expiry; it
    can never widen a different or already-expired unsealed authority.
    """

    root = require_host_runtime(host_runtime_dir)
    if not runtime_file_lock_is_held(root / "locks" / "host-authority.lock"):
        raise ConfigurationError("host capacity renewal requires host authority")
    if (
        AUTHORITY_ID.fullmatch(capacity_generation) is None
        or AUTHORITY_ID.fullmatch(expected_capacity_record_id) is None
        or AUTHORITY_ID.fullmatch(capability_digest) is None
        or AUTHORITY_ID.fullmatch(provider_identity_digest) is None
        or not isinstance(capability_source, str)
        or not capability_source.strip()
        or not isinstance(provider_identity_source, str)
        or not provider_identity_source.strip()
        or not isinstance(actor, str)
        or not actor.strip()
    ):
        raise ConfigurationError("host capacity renewal identity is invalid")
    provider = _host_provider_binding(
        root,
        host_id=host_id,
        provider_identity_source=provider_identity_source,
        provider_identity_digest=provider_identity_digest,
    )
    current = _read_host_capacity_record(
        root,
        host_id,
        now=now,
        require_live=False,
    )
    if (
        current.get("provider_generation") != provider.get("provider_generation")
        or current.get("provider_epoch") != provider.get("provider_epoch")
        or current.get("capacity_generation") != capacity_generation
        or current.get("capability_source") != capability_source
        or current.get("capability_digest") != capability_digest
    ):
        raise ConfigurationError(
            "host capacity renewal changes provider, policy, or capability evidence"
        )
    try:
        requested_issued = parse_time(issued_at)
        requested_expiry = parse_time(expires_at)
        current_issued = parse_time(current.get("issued_at"))
        current_expiry = parse_time(current.get("expires_at"))
    except (TypeError, ValueError) as error:
        raise ConfigurationError("host capacity renewal bounds are malformed") from error
    if (
        requested_issued > now
        or requested_issued < current_issued
        or requested_expiry <= requested_issued
    ):
        raise ConfigurationError("host capacity renewal time window is invalid")

    capacity_path = host_capacity_path(root, host_id)
    history_path = capacity_path.parent / "capacity-history.jsonl"
    history = _strict_capacity_history(history_path) if history_path.is_file() else ()
    pending = (
        history[-1]
        if history
        and history[-1].get("rotation_reason") == "SAME_POLICY_RENEWAL"
        and history[-1].get("capacity_generation") == capacity_generation
        and history[-1].get("previous_capacity_record_id")
        == expected_capacity_record_id
        else None
    )
    if current.get("record_id") == expected_capacity_record_id:
        if pending is None:
            if current_expiry <= now:
                raise ConfigurationError(
                    "expired host capacity requires lifecycle reconciliation, not renewal"
                )
            if requested_expiry <= current_expiry:
                raise ConfigurationError(
                    "host capacity renewal must extend the live authority window"
                )
            candidate_material = {
                key: value
                for key, value in current.items()
                if key not in {"issued_at", "expires_at", "record_id"}
            }
            candidate_material.update(
                {"issued_at": issued_at, "expires_at": expires_at}
            )
            candidate = validate_host_capacity(
                {
                    **candidate_material,
                    "record_id": digest_json(candidate_material),
                },
                host_id=host_id,
                now=now,
            )
            reservation_events = list(_host_reservation_events_unlocked(root))
            latest: dict[str, Mapping[str, object]] = {}
            for event in reservation_events:
                latest[str(event["reservation_id"])] = event
            active = sorted(
                (
                    event
                    for event in latest.values()
                    if event.get("state") in HOST_RESERVATION_ACTIVE_STATES
                    and event.get("provider_generation")
                    == current.get("provider_generation")
                    and event.get("capacity_generation") == capacity_generation
                ),
                key=lambda event: str(event["reservation_id"]),
            )
            if any(parse_time(event.get("expires_at")) <= now for event in active):
                raise ConfigurationError(
                    "expired host reservation requires lifecycle reconciliation before capacity renewal"
                )
            prior_event_id = str(history[-1]["event_id"]) if history else None
            history_material: dict[str, object] = {
                "schema_version": 1,
                "kind": HOST_CAPACITY_HISTORY_KIND,
                "host_id": host_id,
                "provider_generation": candidate["provider_generation"],
                "provider_epoch": candidate["provider_epoch"],
                "host_kernel_generation": candidate["host_kernel_generation"],
                "capacity_generation": capacity_generation,
                "capacity_epoch": candidate["capacity_epoch"],
                "capacity_record_id": candidate["record_id"],
                "capacity_record": dict(candidate),
                "previous_capacity_generation": capacity_generation,
                "recorded_at": format_time(now),
                "rotation_reason": "SAME_POLICY_RENEWAL",
                "previous_capacity_expires_at": current["expires_at"],
                "predecessor_terminal_event_ids": [],
                "previous_capacity_record_id": expected_capacity_record_id,
                "active_reservation_event_ids": [
                    str(event["event_id"]) for event in active
                ],
                "renewal_actor": actor,
                "previous_event_id": prior_event_id,
            }
            pending = {
                **history_material,
                "event_id": digest_json(history_material),
            }
            _append_canonical_jsonl(history_path, pending)
        sealed_candidate = pending.get("capacity_record")
        if not isinstance(sealed_candidate, Mapping):
            raise ConfigurationError("host capacity renewal candidate is missing")
        candidate = validate_host_capacity(
            sealed_candidate,
            host_id=host_id,
            now=now,
        )
    elif (
        pending is not None
        and current.get("record_id") == pending.get("capacity_record_id")
    ):
        sealed_candidate = pending.get("capacity_record")
        candidate = validate_host_capacity(
            sealed_candidate,
            host_id=host_id,
            now=now,
        )
    else:
        raise ConfigurationError("host capacity renewal compare-and-swap mismatch")
    if any(
        candidate.get(field) != expected
        for field, expected in {
            "capacity_generation": capacity_generation,
            "provider_generation": provider["provider_generation"],
            "provider_epoch": provider["provider_epoch"],
            "capability_source": capability_source,
            "capability_digest": capability_digest,
        }.items()
    ):
        raise ConfigurationError("sealed host capacity renewal candidate conflicts")
    return _complete_same_policy_capacity_renewal_unlocked(
        root,
        host_id=host_id,
        pending=pending,
        current=current,
        now=now,
    )


def release_global_host_session(
    host_runtime_dir: str | Path,
    reservation_id: str,
    *,
    execution_id: str,
    local_reservation_id: str,
    capacity_generation: str,
    actor: str,
    reason: str,
    released_at: str,
    local_terminal_event_id: str | None = None,
    lifecycle_state: str | None = None,
    local_terminal_event: Mapping[str, object] | None = None,
    pre_launch_abort_receipt: Mapping[str, object] | None = None,
    validation_terminal_lease: Mapping[str, object] | None = None,
    validation_never_acquired_receipt: Mapping[str, object] | None = None,
    repo_root: str | Path | None = None,
    coordination_dir: str | Path | None = None,
    execution_dir: str | Path | None = None,
    execution_namespace: str | None = None,
) -> Mapping[str, object]:
    root = require_host_runtime(host_runtime_dir)
    lock_path = root / "locks" / "host-authority.lock"
    if not runtime_file_lock_is_held(lock_path):
        raise ConfigurationError("host reservation release requires host authority")
    if AUTHORITY_ID.fullmatch(reservation_id) is None or not actor.strip() or not reason.strip():
        raise ConfigurationError("host reservation release evidence is invalid")
    if local_terminal_event is not None and local_terminal_event_id is not None:
        raise ConfigurationError(
            "local terminal event mapping and scalar id are mutually exclusive"
        )
    if (local_terminal_event_id is None) != (lifecycle_state is None):
        raise ConfigurationError(
            "host reservation terminal evidence must be supplied as one exact pair"
        )
    if local_terminal_event_id is not None and (
        AUTHORITY_ID.fullmatch(local_terminal_event_id) is None
        or lifecycle_state != "TERMINAL"
    ):
        raise ConfigurationError("host reservation terminal evidence is invalid")
    evidence_count = sum(
        (
            local_terminal_event_id is not None
            or local_terminal_event is not None,
            pre_launch_abort_receipt is not None,
            validation_terminal_lease is not None,
            validation_never_acquired_receipt is not None,
        )
    )
    if evidence_count > 1:
        raise ConfigurationError(
            "host reservation release evidence choices are mutually exclusive"
        )
    events = list(_host_reservation_events_unlocked(root))
    prior = next(
        (event for event in reversed(events) if event.get("reservation_id") == reservation_id),
        None,
    )
    if prior is None:
        raise ConfigurationError("host reservation is absent")
    if any(
        prior.get(field) != expected
        for field, expected in {
            "execution_id": execution_id,
            "local_reservation_id": local_reservation_id,
            "capacity_generation": capacity_generation,
        }.items()
    ):
        raise ConfigurationError("host reservation release fence mismatch")
    reservation_kind = str(prior.get("reservation_kind"))
    if reservation_kind == "VALIDATION":
        if (validation_terminal_lease is None) == (
            validation_never_acquired_receipt is None
        ):
            raise ConfigurationError(
                "validation reservation release requires terminal lease or never-acquired evidence"
            )
    elif (
        validation_terminal_lease is not None
        or validation_never_acquired_receipt is not None
    ):
        raise ConfigurationError(
            "validation release evidence cannot release another reservation kind"
        )
    validated_terminal: Mapping[str, object] | None = None
    terminal_event_kind: str | None = None
    terminal_event_state: str | None = None
    terminal_event_relative_path: str | None = None
    terminal_event_blob_digest: str | None = None
    if local_terminal_event is not None:
        if (
            repo_root is None
            or coordination_dir is None
            or execution_dir is None
            or execution_namespace is None
        ):
            raise ConfigurationError(
                "terminal host release requires the exact repository and execution authority"
            )
        (
            validated_terminal,
            terminal_event_kind,
            terminal_event_state,
        ) = _verify_local_terminal_event_cut(
            repo_root=repo_root,
            coordination_dir=coordination_dir,
            execution_dir=execution_dir,
            execution_id=execution_id,
            execution_namespace=execution_namespace,
            reservation=prior,
            local_terminal_event=local_terminal_event,
        )
        local_terminal_event_id = str(validated_terminal["event_id"])
        lifecycle_state = "TERMINAL"
        terminal_path = _local_terminal_event_evidence_path(
            root, local_terminal_event_id
        )
        terminal_event_relative_path = terminal_path.relative_to(root).as_posix()
        terminal_bytes = (
            json.dumps(
                dict(validated_terminal),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        exclusive_write_bytes_or_identical(terminal_path, terminal_bytes)
        terminal_event_blob_digest = "sha256:" + sha256(terminal_bytes).hexdigest()
    elif (
        prior.get("reservation_kind") in {"PRIMARY", "SIDECAR"}
        and local_terminal_event_id is not None
    ):
        raise ConfigurationError(
            "primary and sidecar release require full authenticated terminal event bytes"
        )
    validated_abort: Mapping[str, object] | None = None
    abort_relative_path: str | None = None
    abort_blob_digest: str | None = None
    if pre_launch_abort_receipt is not None:
        if prior.get("reservation_kind") != "PRIMARY":
            raise ConfigurationError(
                "only an unlaunched primary dispatcher admission can use pre-launch abort"
            )
        validated_abort = _validate_pre_launch_abort_receipt(
            pre_launch_abort_receipt,
            reservation=prior,
        )
        if (
            repo_root is None
            or coordination_dir is None
            or execution_dir is None
            or execution_namespace is None
        ):
            raise ConfigurationError(
                "pre-launch abort requires the exact repository and execution authority"
            )
        validated_abort = _verify_pre_launch_abort_negative_cut(
            repo_root=repo_root,
            coordination_dir=coordination_dir,
            execution_dir=execution_dir,
            execution_id=execution_id,
            execution_namespace=execution_namespace,
            reservation=prior,
            receipt=validated_abort,
        )
        abort_path = _pre_launch_abort_evidence_path(root, reservation_id)
        abort_relative_path = abort_path.relative_to(root).as_posix()
        abort_bytes = (
            json.dumps(
                dict(validated_abort),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        exclusive_write_bytes_or_identical(abort_path, abort_bytes)
        abort_blob_digest = "sha256:" + sha256(abort_bytes).hexdigest()
    validated_validation: Mapping[str, object] | None = None
    validation_evidence_type: str | None = None
    validation_evidence_relative_path: str | None = None
    validation_evidence_blob_digest: str | None = None
    validation_evidence_id: str | None = None
    validation_terminal_status: str | None = None
    if (
        validation_terminal_lease is not None
        or validation_never_acquired_receipt is not None
    ):
        if (
            repo_root is None
            or coordination_dir is None
            or execution_dir is None
            or execution_namespace is None
        ):
            raise ConfigurationError(
                "validation release requires the exact repository and execution authority"
            )
        validated_validation, validation_evidence_type = (
            _verify_validation_release_evidence_cut(
                repo_root=repo_root,
                coordination_dir=coordination_dir,
                execution_dir=execution_dir,
                execution_id=execution_id,
                execution_namespace=execution_namespace,
                reservation=prior,
                terminal_lease=validation_terminal_lease,
                never_acquired_receipt=validation_never_acquired_receipt,
            )
        )
        if validation_evidence_type == "TERMINAL_LEASE":
            terminal_bytes = (
                json.dumps(
                    dict(validated_validation),
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                    allow_nan=False,
                )
                + "\n"
            ).encode("utf-8")
            receipt: dict[str, object] = {
                "schema_version": 1,
                "kind": VALIDATION_TERMINAL_RECEIPT_KIND,
                "state": "TERMINAL_LEASE",
                "execution_namespace": execution_namespace,
                "execution_id": execution_id,
                "repository": prior["repository"],
                "reservation_id": prior["reservation_id"],
                "local_reservation_id": prior["local_reservation_id"],
                "resource_key": prior["resource_key"],
                "host_id": prior["host_id"],
                "provider_generation": prior["provider_generation"],
                "capacity_generation": prior["capacity_generation"],
                "validation_resource_key": prior["resource_key"],
                "release_id": validated_validation["release_id"],
                "transaction_sha": validated_validation["transaction_sha"],
                "lease_id": validated_validation["lease_id"],
                "terminal_status": validated_validation["status"],
                "terminal_lease": dict(validated_validation),
                "terminal_lease_blob_digest": "sha256:"
                + sha256(terminal_bytes).hexdigest(),
                "recorded_at": released_at,
            }
            receipt["record_id"] = digest_json(receipt)
            validated_validation = _validate_validation_terminal_receipt(
                receipt,
                reservation=prior,
            )
            validation_evidence_id = str(validated_validation["record_id"])
            validation_terminal_status = str(
                validated_validation["terminal_status"]
            )
        else:
            validation_evidence_id = str(validated_validation["record_id"])
            validation_terminal_status = "NEVER_ACQUIRED"
        validation_path = _validation_terminal_evidence_path(root, reservation_id)
        validation_evidence_relative_path = validation_path.relative_to(root).as_posix()
        validation_bytes = (
            json.dumps(
                dict(validated_validation),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        exclusive_write_bytes_or_identical(validation_path, validation_bytes)
        validation_evidence_blob_digest = (
            "sha256:" + sha256(validation_bytes).hexdigest()
        )
    if prior.get("state") in {"RELEASED", "EXPIRED_FENCED"}:
        if validated_abort is not None and (
            prior.get("pre_launch_abort_receipt_id")
            != validated_abort.get("record_id")
            or prior.get("pre_launch_abort_receipt_blob_digest")
            != abort_blob_digest
        ):
            raise ConfigurationError(
                "pre-launch abort retry differs from terminal host evidence"
            )
        if validated_terminal is not None and (
            prior.get("local_terminal_event_id")
            != validated_terminal.get("event_id")
            or prior.get("local_terminal_event_blob_digest")
            != terminal_event_blob_digest
        ):
            raise ConfigurationError(
                "local terminal retry differs from terminal host evidence"
            )
        if validated_validation is not None and (
            prior.get("validation_terminal_evidence_id")
            != validation_evidence_id
            or prior.get("validation_terminal_evidence_blob_digest")
            != validation_evidence_blob_digest
        ):
            raise ConfigurationError(
                "validation release retry differs from terminal host evidence"
            )
        return prior
    if pre_launch_abort_receipt is not None and prior.get("reservation_kind") != "PRIMARY":
        raise ConfigurationError(
            "only an unlaunched primary dispatcher admission can use pre-launch abort"
        )
    if reservation_kind in {"PRIMARY", "SIDECAR"} and (
        validated_terminal is None and validated_abort is None
    ):
        raise ConfigurationError(
            "primary and sidecar release require authenticated terminal or never-launched evidence"
        )
    payload = {
        key: value
        for key, value in prior.items()
        if key
        not in {
            "schema_version",
            "kind",
            "state",
            "previous_event_id",
            "event_id",
        }
    }
    terminal_evidence = (
        {
            "local_terminal_event_id": local_terminal_event_id,
            "local_terminal_event_path": terminal_event_relative_path,
            "local_terminal_event_blob_digest": terminal_event_blob_digest,
            "local_terminal_event_kind": terminal_event_kind,
            "local_terminal_state": terminal_event_state,
            "lifecycle_state": lifecycle_state,
        }
        if validated_terminal is not None
        else {}
    )
    pre_launch_evidence = (
        {
            "pre_launch_abort_receipt_id": validated_abort["record_id"],
            "pre_launch_abort_receipt_path": abort_relative_path,
            "pre_launch_abort_receipt_blob_digest": abort_blob_digest,
            "pre_launch_abort_release_id": validated_abort["release_id"],
            "pre_launch_abort_admission_epoch": validated_abort[
                "admission_epoch"
            ],
            "pre_launch_abort_state": "NEVER_LAUNCHED",
        }
        if validated_abort is not None
        else {}
    )
    validation_evidence = (
        {
            "validation_terminal_evidence_id": validation_evidence_id,
            "validation_terminal_evidence_path": validation_evidence_relative_path,
            "validation_terminal_evidence_blob_digest": validation_evidence_blob_digest,
            "validation_terminal_evidence_type": validation_evidence_type,
            "validation_terminal_status": validation_terminal_status,
        }
        if validated_validation is not None
        else {}
    )
    return _append_host_reservation_unlocked(
        root,
        {
            "state": "RELEASED",
            **payload,
            "released_at": released_at,
            "release_actor": actor,
            "release_reason": reason,
            "external_cancellation": (
                "CONFIRMED_TERMINAL"
                if validated_terminal is not None
                else (
                    "CONFIRMED_NEVER_LAUNCHED"
                    if validated_abort is not None
                    else (
                        "CONFIRMED_VALIDATION_TERMINAL"
                        if validation_evidence_type == "TERMINAL_LEASE"
                        else (
                            "CONFIRMED_VALIDATION_NEVER_ACQUIRED"
                            if validation_evidence_type == "NEVER_ACQUIRED"
                            else "NOT_CLAIMED"
                        )
                    )
                )
            ),
            **terminal_evidence,
            **pre_launch_evidence,
            **validation_evidence,
        },
        events,
    )


HOST_LIFECYCLE_OBSERVATION_KIND = "hive-mind-host-lifecycle-observation-v1"
HOST_LIFECYCLE_TERMINAL_STATES = frozenset(
    {"TERMINAL", "ABSENT", "INTERRUPTED_ARCHIVED"}
)


def validate_host_lifecycle_observation(
    value: Mapping[str, object],
    *,
    reservation: Mapping[str, object],
    now: datetime,
) -> Mapping[str, object]:
    legacy_fields = {
        "schema_version",
        "kind",
        "host_id",
        "reservation_id",
        "execution_id",
        "local_reservation_id",
        "capacity_generation",
        "host_task_id",
        "host_cursor",
        "capability_digest",
        "state",
        "terminal_state",
        "observed_at",
        "source_event_id",
        "observation_id",
    }
    provenance_fields = {
        "host_kernel_generation",
        "execution_adapter_identity_record_id",
        "execution_adapter_identity_path",
        "execution_adapter_identity_blob_digest",
        "adapter_observation_id",
    }
    expected_fields = legacy_fields | provenance_fields
    reservation_has_provenance = isinstance(
        reservation.get("execution_adapter_identity_record_id"), str
    )
    if set(value) != (
        expected_fields if reservation_has_provenance else legacy_fields
    ):
        raise ConfigurationError("host lifecycle observation schema is invalid")
    material = dict(value)
    observation_id = material.pop("observation_id", None)
    if (
        value.get("schema_version") != 1
        or value.get("kind") != HOST_LIFECYCLE_OBSERVATION_KIND
        or observation_id != digest_json(material)
        or not isinstance(observation_id, str)
        or AUTHORITY_ID.fullmatch(observation_id) is None
        or value.get("state") not in HOST_LIFECYCLE_TERMINAL_STATES
    ):
        raise ConfigurationError("host lifecycle observation identity is invalid")
    for field, expected in {
        "host_id": reservation.get("host_id"),
        "reservation_id": reservation.get("reservation_id"),
        "execution_id": reservation.get("execution_id"),
        "local_reservation_id": reservation.get("local_reservation_id"),
        "capacity_generation": reservation.get("capacity_generation"),
    }.items():
        if value.get(field) != expected:
            raise ConfigurationError(
                f"host lifecycle observation has mismatched {field}"
            )
    if reservation_has_provenance:
        for field in (
            "host_kernel_generation",
            "execution_adapter_identity_record_id",
            "execution_adapter_identity_path",
            "execution_adapter_identity_blob_digest",
        ):
            if value.get(field) != reservation.get(field):
                raise ConfigurationError(
                    f"host lifecycle observation has mismatched {field}"
                )
        adapter_material = {
            field: value[field]
            for field in legacy_fields
            if field != "observation_id"
        }
        if (
            AUTHORITY_ID.fullmatch(
                str(value.get("adapter_observation_id"))
            )
            is None
            or value.get("adapter_observation_id")
            != digest_json(adapter_material)
        ):
            raise ConfigurationError(
                "host lifecycle observation adapter source provenance is invalid"
            )
    if any(
        not isinstance(value.get(field), str) or not str(value[field]).strip()
        for field in ("host_task_id", "host_cursor")
    ) or (
        not isinstance(value.get("capability_digest"), str)
        or AUTHORITY_ID.fullmatch(str(value["capability_digest"])) is None
    ):
        raise ConfigurationError("host lifecycle observation task fence is invalid")
    state = str(value["state"])
    terminal_state = value.get("terminal_state")
    source_event_id = value.get("source_event_id")
    if state == "TERMINAL":
        if (
            terminal_state not in {"SUCCEEDED", "FAILED", "CANCELLED"}
            or not isinstance(source_event_id, str)
            or AUTHORITY_ID.fullmatch(source_event_id) is None
        ):
            raise ConfigurationError(
                "terminal host lifecycle observation lacks terminal evidence"
            )
    elif terminal_state is not None or source_event_id is not None:
        raise ConfigurationError(
            "nonterminal host lifecycle disposition carries forged terminal evidence"
        )
    try:
        observed_at = parse_time(value.get("observed_at"))
    except (TypeError, ValueError) as error:
        raise ConfigurationError("host lifecycle observation time is malformed") from error
    if observed_at > now:
        raise ConfigurationError("host lifecycle observation is from the future")
    return value


def fence_expired_global_host_session(
    host_runtime_dir: str | Path,
    reservation_id: str,
    *,
    execution_id: str,
    local_reservation_id: str,
    capacity_generation: str,
    actor: str,
    reason: str,
    fenced_at: str,
    now: datetime,
    lifecycle_observation: Mapping[str, object],
    local_terminal_event_id: str,
) -> Mapping[str, object]:
    """Retire an expired permit only after host truth and local fencing agree."""

    root = require_host_runtime(host_runtime_dir)
    lock_path = root / "locks" / "host-authority.lock"
    if not runtime_file_lock_is_held(lock_path):
        raise ConfigurationError("expired reservation fencing requires host authority")
    events = list(_host_reservation_events_unlocked(root))
    prior = next(
        (event for event in reversed(events) if event.get("reservation_id") == reservation_id),
        None,
    )
    if prior is None:
        raise ConfigurationError("host reservation is absent")
    if any(
        prior.get(field) != expected
        for field, expected in {
            "execution_id": execution_id,
            "local_reservation_id": local_reservation_id,
            "capacity_generation": capacity_generation,
        }.items()
    ):
        raise ConfigurationError("expired host reservation fence mismatch")
    if prior.get("state") in {"RELEASED", "EXPIRED_FENCED"}:
        return prior
    if prior.get("state") not in HOST_RESERVATION_ACTIVE_STATES:
        raise ConfigurationError("expired host reservation is not active")
    try:
        if parse_time(prior.get("expires_at")) > now:
            raise ConfigurationError("host reservation remains live")
        parse_time(fenced_at)
    except (TypeError, ValueError) as error:
        raise ConfigurationError("expired reservation evidence is malformed") from error
    if (
        not isinstance(local_terminal_event_id, str)
        or AUTHORITY_ID.fullmatch(local_terminal_event_id) is None
    ):
        raise ConfigurationError("local terminal host fence evidence is invalid")
    observation = validate_host_lifecycle_observation(
        lifecycle_observation, reservation=prior, now=now
    )
    observation_relative_path = (
        "lifecycle-observations/"
        + str(observation["observation_id"]).removeprefix("sha256:")
        + ".json"
    )
    observation_path = root / observation_relative_path
    observation_bytes = (
        json.dumps(
            dict(observation),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    exclusive_write_bytes_or_identical(observation_path, observation_bytes)
    observation_blob_digest = "sha256:" + sha256(observation_bytes).hexdigest()
    disposition = {
        "TERMINAL": "CONFIRMED_TERMINAL",
        "ABSENT": "CONFIRMED_ABSENT",
        "INTERRUPTED_ARCHIVED": "CONFIRMED_INTERRUPTED_ARCHIVED",
    }[str(observation["state"])]
    payload = {
        key: value
        for key, value in prior.items()
        if key not in {"schema_version", "kind", "state", "previous_event_id", "event_id"}
    }
    return _append_host_reservation_unlocked(
        root,
        {
            "state": "EXPIRED_FENCED",
            **payload,
            "released_at": fenced_at,
            "release_actor": actor,
            "release_reason": reason,
            "external_cancellation": disposition,
            "lifecycle_observation_id": observation["observation_id"],
            "lifecycle_observation_path": observation_relative_path,
            "lifecycle_observation_blob_digest": observation_blob_digest,
            "lifecycle_state": observation["state"],
            "lifecycle_host_id": observation["host_id"],
            "local_terminal_event_id": local_terminal_event_id,
        },
        events,
    )


def _require_repository_runtime_ready(
    coordination_dir: Path,
    expected_identity: Mapping[str, object],
) -> Mapping[str, object]:
    ready_path = coordination_dir / RUNTIME_READY_MANIFEST
    if not ready_path.is_file() or _is_link_like(ready_path):
        raise ConfigurationError(
            "runtime authority migration is not ready; run runtime-authority-migrate"
        )
    value = read_json(ready_path)
    ready_fields = {
        "schema_version",
        "kind",
        "status",
        "repository_identity",
        "bootstrap_migration_id",
        "attended_migration_digest",
        "default_execution_id",
        "default_execution_identity_digest",
        "default_execution_adoption_digest",
        "default_execution_dir",
        "repository_target_watermark_record_id",
        "kernel_bundle_digest",
        "interpreter_policy_digest",
        "record_id",
    }
    material = dict(value) if isinstance(value, Mapping) else {}
    record_id = material.pop("record_id", None)
    if (
        not isinstance(value, Mapping)
        or set(value) != ready_fields
        or value.get("schema_version") != 1
        or value.get("kind") != RUNTIME_READY_KIND
        or value.get("status") != "COMPLETE"
        or value.get("repository_identity") != expected_identity
        or not isinstance(value.get("bootstrap_migration_id"), str)
        or AUTHORITY_ID.fullmatch(str(value.get("bootstrap_migration_id"))) is None
        or not isinstance(value.get("attended_migration_digest"), str)
        or AUTHORITY_ID.fullmatch(str(value.get("attended_migration_digest"))) is None
        or not isinstance(value.get("default_execution_id"), str)
        or AUTHORITY_ID.fullmatch(str(value.get("default_execution_id"))) is None
        or not isinstance(value.get("default_execution_identity_digest"), str)
        or AUTHORITY_ID.fullmatch(
            str(value.get("default_execution_identity_digest"))
        )
        is None
        or not isinstance(value.get("default_execution_adoption_digest"), str)
        or AUTHORITY_ID.fullmatch(
            str(value.get("default_execution_adoption_digest"))
        )
        is None
        or not isinstance(value.get("default_execution_dir"), str)
        or AUTHORITY_ID.fullmatch(
            str(value.get("repository_target_watermark_record_id"))
        )
        is None
        or AUTHORITY_ID.fullmatch(str(value.get("kernel_bundle_digest"))) is None
        or AUTHORITY_ID.fullmatch(
            str(value.get("interpreter_policy_digest"))
        )
        is None
        or record_id != digest_json(material)
    ):
        raise ConfigurationError(
            "runtime authority readiness is malformed or belongs to another repository"
        )
    return dict(value)


def ensure_repository_runtime_identity(
    repo_root: str | Path,
    coordination_dir: str | Path,
    *,
    create: bool = True,
) -> Mapping[str, object] | None:
    """Bind an external/shared authority directory to one configured repository."""

    root = _reject_link_components(repo_root, label="repository root").resolve()
    expected = runtime_repository_identity(root)
    if expected is None:
        return None
    directory = Path(coordination_dir).resolve()
    if create and not runtime_file_lock_is_held(directory / RUNTIME_BOOTSTRAP_LOCK):
        raise ConfigurationError(
            "runtime authority identity creation requires the bootstrap migration lock"
        )
    obligations = legacy_runtime_authority_paths(root, directory)
    if obligations:
        raise ConfigurationError(
            "legacy worktree authority requires explicit reconciliation: "
            + ", ".join(str(path) for path in obligations)
        )
    manifest = directory / "runtime-identity.json"
    identity_lock = directory / "locks" / "runtime-identity.lock"
    if not create and (not manifest.is_file() or not identity_lock.is_file()):
        raise ConfigurationError(
            "runtime authority identity is absent; run an explicit authority migration"
        )
    with runtime_file_lock(identity_lock):
        if manifest.is_file():
            current = read_json(manifest)
            if current != expected:
                raise ConfigurationError(
                    "runtime authority directory is bound to another repository"
                )
        elif create:
            atomic_write_json(manifest, expected)
        else:
            raise ConfigurationError(
                "runtime authority identity is absent; run an explicit authority migration"
            )
    if not create:
        _require_repository_runtime_ready(directory, expected)
    return expected


def _linked_worktree_roots(repo_root: Path) -> tuple[Path, ...]:
    repo_root = _reject_link_components(
        repo_root,
        label="repository root",
    ).resolve()
    common = _linked_worktree_common_dir(repo_root)
    if common is None or common.name != ".git":
        return (repo_root.resolve(),)
    roots: set[Path] = {common.parent.resolve()}
    worktrees = common / "worktrees"
    if _is_link_like(worktrees):
        raise ConfigurationError("Git worktree inventory must not be a link")
    if not worktrees.is_dir():
        return tuple(sorted(roots, key=str))
    for gitdir_marker in sorted(worktrees.glob("*/gitdir")):
        _reject_link_components(gitdir_marker, label="linked-worktree gitdir marker")
        if not gitdir_marker.is_file():
            raise ConfigurationError("linked-worktree gitdir marker is invalid")
        try:
            raw = gitdir_marker.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as error:
            raise ConfigurationError(
                f"cannot inspect linked worktree authority: {error}"
            ) from error
        if not raw:
            raise ConfigurationError("linked-worktree gitdir marker is empty")
        marker = Path(raw)
        if not marker.is_absolute():
            marker = gitdir_marker.parent / marker
        marker = _reject_link_components(marker, label="linked worktree marker")
        roots.add(
            _reject_link_components(
                marker.parent,
                label="linked worktree root",
            ).resolve()
        )
    return tuple(sorted(roots, key=str))


def legacy_runtime_authority_paths(
    repo_root: str | Path,
    coordination_dir: str | Path,
) -> tuple[Path, ...]:
    """List noncanonical authority files that must never be silently orphaned."""

    canonical = _reject_link_components(
        coordination_dir,
        label="runtime state path",
    ).resolve()
    found: list[Path] = []
    for root in _linked_worktree_roots(
        _reject_link_components(repo_root, label="repository root").resolve()
    ):
        state = root / ".autopilot" / "state"
        if state.exists() or _is_link_like(state):
            state = _reject_link_components(
                state,
                label="linked-worktree runtime state",
            )
        if state.resolve() == canonical or not state.is_dir():
            continue
        for relative in (
            "global-validation-lease.json",
            "dispatcher-release.json",
            "task-bindings.jsonl",
            "sidecar-bindings.jsonl",
            "host/attended-threads.json",
            "dispatcher-generation.json",
        ):
            path = state / relative
            if path.exists() or _is_link_like(path):
                _reject_link_components(path, label="legacy runtime authority")
            if path.is_file() and path.stat().st_size > 0:
                found.append(path)
        claims = state / "claims"
        if claims.exists() or _is_link_like(claims):
            claims = _reject_link_components(
                claims,
                label="legacy claims directory",
            )
        if claims.is_dir():
            for path in sorted(claims.glob("*.json")):
                _reject_link_components(path, label="legacy claim authority")
                if path.is_file():
                    found.append(path)
    return tuple(found)


RUNTIME_BOOTSTRAP_MIGRATION_KIND = (
    "hive-mind-runtime-authority-bootstrap-migration-v1"
)
RUNTIME_BOOTSTRAP_MANIFEST = "runtime-authority-bootstrap-migration.json"
RUNTIME_BOOTSTRAP_LOCK = "runtime-authority-bootstrap-migration.lock"
RUNTIME_READY_MANIFEST = "runtime-authority-ready.json"
RUNTIME_READY_KIND = "hive-mind-runtime-authority-ready-v1"
LEGACY_SEMANTIC_RECONCILIATION_KIND = (
    "hive-mind-legacy-worktree-authority-reconciliation-v1"
)
LEGACY_SEMANTIC_RECONCILIATION_MANIFEST = (
    "legacy-worktree-authority-reconciliation.json"
)
LEGACY_AUTHORITY_QUARANTINE_KIND = (
    "hive-mind-legacy-authority-quarantine-obligation-v1"
)
LEGACY_AUTHORITY_QUARANTINE_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "state",
        "repository",
        "repository_transport_digest",
        "reconciliation_id",
        "source_root",
        "relative_path",
        "authority_kind",
        "source_digest",
        "target_branch",
        "plan_fingerprint",
        "execution_namespace",
        "execution_id",
        "active_authority_ids",
        "reason",
        "external_cancellation",
        "archive_path",
        "recorded_at",
        "record_id",
    }
)
ATTENDED_MIGRATION_KIND = "hive-mind-attended-ledger-migration-v1"
EXECUTION_NAMESPACE_KEY_KIND = "hive-mind-execution-namespace-key-v1"
EXECUTION_IDENTITY_KIND = "hive-mind-execution-identity-v1"
PLAN_TERMINAL_FENCE_KIND = "hive-mind-plan-terminal-fence-v1"
REPOSITORY_TARGET_WATERMARK_KIND = "hive-mind-repository-target-watermark-v1"
INITIAL_REMOTE_TARGET_OBSERVATION_KIND = (
    "hive-mind-initial-remote-target-observation-v1"
)
INITIAL_REMOTE_TARGET_OBSERVATION_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "repository",
        "repository_transport_digest",
        "target_ref",
        "target_sha",
        "transport_record_id",
        "execution_id",
        "execution_namespace",
        "observed_at",
        "record_id",
    }
)
SUPERSEDED_PUBLICATION_TARGET_OBSERVATION_KIND = (
    "hive-mind-superseded-publication-target-observation-v1"
)
SUPERSEDED_PUBLICATION_TARGET_OBSERVATION_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "repository",
        "repository_transport_digest",
        "target_ref",
        "expected_target_sha",
        "pinned_sha",
        "observed_target_sha",
        "observation_ref",
        "observation_ref_sha",
        "transaction_ref",
        "observed_transaction_sha",
        "receipt_heads",
        "execution_namespace",
        "execution_id",
        "release_id",
        "publication_transaction_id",
        "observed_at",
        "record_id",
    }
)
SUPERSEDED_PUBLICATION_RECEIPT_HEAD_FIELDS = frozenset(
    {"node_id", "branch", "expected_sha", "observed_sha"}
)
TARGET_WATERMARK_TRANSITION_EVIDENCE_KIND = (
    "hive-mind-target-watermark-transition-evidence-v1"
)
TARGET_WATERMARK_TRANSITION_EVIDENCE_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "transition_id",
        "source_kind",
        "repository",
        "repository_transport_digest",
        "target_ref",
        "previous_target_generation",
        "previous_target_sha",
        "previous_watermark_record_id",
        "target_sha",
        "execution_namespace",
        "execution_id",
        "plan_fingerprint",
        "source_release_id",
        "publication_transaction_id",
        "source_record_id",
        "source_blob_digest",
        "source_blob_path",
        "observed_at",
        "record_id",
    }
)
# These are exact cross-module authority schemas.  The controller retains the
# source bytes and validates them independently so replay cannot silently trust
# a SHA-shaped observation or publication id from an adapter.
SNAPSHOT_WATERMARK_SOURCE_FIELDS = frozenset(
    {
        "schema_version", "kind", "status", "execution_namespace",
        "execution_id", "observation_epoch", "observation_id", "fetch_ref",
        "branch_fetches", "repository", "target_branch", "base_target_sha",
        "target_sha", "plan_fingerprint", "snapshot_digest",
        "candidate_artifact", "supersedes_observation_id", "actor",
        "began_at", "expires_at", "installed_at", "record_id",
    }
)
PUBLICATION_WATERMARK_SOURCE_FIELDS = frozenset(
    {
        "schema_version", "kind", "status", "transaction_key",
        "attempt_epoch", "nonce", "transaction_id", "execution_namespace",
        "execution_id", "release_id", "round_id", "repository",
        "target_branch", "expected_target_sha", "authority_digest",
        "authority_baseline_digest", "receipt_heads", "receipt_heads_digest",
        "transaction_ref", "coordinator_id", "transaction_lease_nonce",
        "transaction_lease_id", "lease_expires_at", "publishing_lease_nonce",
        "publishing_lease_id", "publishing_lease_expires_at", "pinned_sha",
        "validation_evidence", "outcome", "detail", "actor", "reserved_at",
        "updated_at", "completed_at", "record_id",
    }
)
REPOSITORY_TARGET_WATERMARK_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "repository",
        "repository_transport_digest",
        "target_branch",
        "target_generation",
        "target_sha",
        "previous_record_id",
        "source_kind",
        "source_execution_id",
        "source_release_id",
        "publication_transaction_id",
        "source_observation_id",
        "actor",
        "recorded_at",
        "record_id",
    }
)
PLAN_TERMINAL_FENCE_OBSERVATION_KIND = (
    "hive-mind-plan-terminal-controller-observation-v1"
)
PLAN_TERMINAL_FENCE_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "execution_id",
        "execution_namespace",
        "release_id",
        "admission_epoch",
        "target_sha",
        "target_generation",
        "target_watermark_record_id",
        "plan_fingerprint",
        "authority_digest",
        "controller_observation_id",
        "sealed_by",
        "sealed_at",
        "state",
        "record_id",
    }
)
EXECUTION_NAMESPACE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
EXECUTION_COORDINATOR_LOCKS = (
    "github-snapshot-coordinator.lock",
    "execution-supervisor.lock",
)
EXECUTION_LOCKS = (
    "authority-ledger-initialization.lock",
    "dispatcher-admission.lock",
    "task-bindings.lock",
    "sidecar-bindings.lock",
    "attended-host.lock",
)
ARBITER_LOCKS = (
    "arbiter-authority.lock",
    "claim-authority.lock",
    "global-validation-lease.lock",
    "host-reservations.lock",
)
STANDARD_RUNTIME_LOCKS = (
    "authority-ledger-initialization.lock",
    "task-bindings.lock",
    "sidecar-bindings.lock",
    "attended-host.lock",
    "dispatcher-admission.lock",
    "claim-authority.lock",
    "global-validation-lease.lock",
)
_NONCANONICAL_LEDGER_PATHS = (
    "task-bindings.jsonl",
    "sidecar-bindings.jsonl",
    "host/attended-threads.json",
    "dispatcher-generation.json",
)

_LEGACY_CLAIM_SCHEMAS = frozenset(
    {
        frozenset(
            {
                "schema_version",
                "node_id",
                "owner",
                "status",
                "claimed_at",
                "heartbeat_at",
                "expires_at",
                "plan_fingerprint",
                "remote",
                "remote_claim_commit",
                "target_sha",
                "branch",
            }
        ),
        frozenset(
            {
                "schema_version",
                "kind",
                "node_id",
                "owner",
                "status",
                "claimed_at",
                "heartbeat_at",
                "expires_at",
                "plan_fingerprint",
                "remote",
                "remote_claim_commit",
                "target_sha",
                "branch",
                "grant_id",
                "release_id",
                "authority_digest",
                "github_snapshot_digest",
                "reconciliation_digest",
                "doctor_evidence_digest",
                "repair_id",
                "old_receipt_commit",
                "execution_merge_commit",
                "remote_head_commit",
            }
        ),
        frozenset(
            {
                "schema_version",
                "node_id",
                "owner",
                "status",
                "claimed_at",
                "heartbeat_at",
                "expires_at",
                "plan_fingerprint",
                "remote",
                "remote_claim_commit",
                "target_sha",
                "branch",
                "authority_nonce",
                "claim_authority_class",
                "launch_instruction_id",
                "resource_key",
                "authority_epoch",
                "claim_id",
            }
        ),
    }
)
_CURRENT_CLAIM_FIELDS = frozenset(
    {
        "schema_version",
        "node_id",
        "owner",
        "status",
        "claimed_at",
        "heartbeat_at",
        "expires_at",
        "plan_fingerprint",
        "remote",
        "remote_claim_commit",
        "target_sha",
        "branch",
        "repository",
        "file_locks",
        "semantic_locks",
        "execution_id",
        "authority_nonce",
        "claim_authority_class",
        "launch_instruction_id",
        "resource_key",
        "authority_epoch",
        "dispatcher_release_id",
        "dispatcher_admission_epoch",
        "launch_binding_event_id",
        "claim_id",
    }
)
_LEGACY_LEASE_SCHEMAS = frozenset(
    {
        frozenset(
            {
                "schema_version",
                "node_id",
                "owner",
                "target_sha",
                "acquired_at",
                "expires_at",
                "status",
                "lease_id",
            }
        ),
        frozenset(
            {
                "schema_version",
                "node_id",
                "owner",
                "target_sha",
                "acquired_at",
                "expires_at",
                "renewed_at",
                "renewal_count",
                "status",
                "authority_nonce",
                "claim_id",
                "claim_authority_class",
                "launch_instruction_id",
                "resource_key",
                "authority_epoch",
                "lease_id",
            }
        ),
        frozenset(
            {
                "schema_version",
                "node_id",
                "owner",
                "target_sha",
                "acquired_at",
                "expires_at",
                "renewal_count",
                "status",
                "authority_nonce",
                "claim_id",
                "claim_authority_class",
                "launch_instruction_id",
                "resource_key",
                "authority_epoch",
                "lease_id",
            }
        ),
    }
)
_LEGACY_DISPATCH_RELEASE_SCHEMAS = frozenset(
    {
        frozenset(
            {
                "schema_version",
                "kind",
                "actor",
                "target_sha",
                "plan_fingerprint",
                "reconciliation_digest",
                "github_snapshot_digest",
                "released_wave",
                "directive",
                "action",
                "verdicts",
                "issued_at",
                "release_id",
            }
        ),
        frozenset(
            {
                "schema_version",
                "kind",
                "actor",
                "target_sha",
                "plan_fingerprint",
                "reconciliation_digest",
                "github_snapshot_digest",
                "released_wave",
                "directive",
                "action",
                "verdicts",
                "issued_at",
                "receipt_retirement_execution_digest",
                "release_id",
            }
        ),
        frozenset(
            {
                "schema_version",
                "kind",
                "actor",
                "target_sha",
                "plan_fingerprint",
                "reconciliation_digest",
                "github_snapshot_digest",
                "released_wave",
                "directive",
                "action",
                "verdicts",
                "issued_at",
                "receipt_retirement_execution_digest",
                "builder_retirement_execution_digest",
                "release_id",
            }
        ),
    }
)


def _read_regular_authority_bytes(path: Path, *, label: str) -> bytes:
    absolute = _reject_link_components(path, label=label)
    if not absolute.is_file():
        raise ConfigurationError(f"{label} is not a regular file: {absolute}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(absolute, flags)
    except OSError as error:
        raise ConfigurationError(f"cannot open {label} {absolute}: {error}") from error
    try:
        _verify_open_regular_file_identity(descriptor, absolute, label=label)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        _verify_open_regular_file_identity(descriptor, absolute, label=label)
        return b"".join(chunks)
    except OSError as error:
        raise ConfigurationError(f"cannot read {label} {absolute}: {error}") from error
    finally:
        os.close(descriptor)


def _strict_json_pairs(pairs: Sequence[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON constant {value}")


def _strict_authority_object(
    path: Path,
    raw: bytes,
    *,
    kind: str,
    schemas: frozenset[frozenset[str]],
) -> Mapping[str, Any]:
    try:
        decoded = raw.decode("utf-8")
        value = json.loads(
            decoded,
            object_pairs_hook=_strict_json_pairs,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ConfigurationError(
            f"noncanonical {kind} authority is malformed: {path}: {error}"
        ) from error
    if not isinstance(value, Mapping):
        raise ConfigurationError(
            f"noncanonical {kind} authority must be an object: {path}"
        )
    if frozenset(value) not in schemas:
        raise ConfigurationError(
            f"noncanonical {kind} authority has an unexpected schema: {path}"
        )
    if value.get("schema_version") != 1:
        raise ConfigurationError(
            f"noncanonical {kind} authority schema version is invalid: {path}"
        )
    canonical_lf = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        + "\n"
    ).encode("utf-8")
    canonical_crlf = canonical_lf.replace(b"\n", b"\r\n")
    if raw not in {canonical_lf, canonical_crlf}:
        raise ConfigurationError(
            f"noncanonical {kind} authority uses a noncanonical encoding: {path}"
        )
    return value


def _parse_expired_legacy_authority(
    path: Path,
    raw: bytes,
    *,
    kind: str,
    now: datetime,
) -> tuple[Mapping[str, Any], datetime, str]:
    schemas = _LEGACY_CLAIM_SCHEMAS if kind == "claim" else _LEGACY_LEASE_SCHEMAS
    value = _strict_authority_object(path, raw, kind=kind, schemas=schemas)
    node_id = value.get("node_id")
    owner = value.get("owner")
    if not isinstance(node_id, str) or not node_id.strip():
        raise ConfigurationError(
            f"noncanonical {kind} node identity is malformed: {path}"
        )
    if not isinstance(owner, str) or not owner.strip():
        raise ConfigurationError(
            f"noncanonical {kind} owner identity is malformed: {path}"
        )
    try:
        expires = parse_time(value.get("expires_at"))
    except (TypeError, ValueError) as error:
        raise ConfigurationError(
            f"noncanonical {kind} expiry is malformed: {path}"
        ) from error
    if expires > now:
        raise ConfigurationError(
            f"noncanonical {kind} authority is still live: {path}"
        )
    raw_digest = "sha256:" + sha256(raw).hexdigest()
    if kind == "claim":
        if path.stem != node_id:
            raise ConfigurationError(
                f"noncanonical claim file and node identity disagree: {path}"
            )
        if value.get("status") not in {"CLAIMED", "RUNNING"}:
            raise ConfigurationError(
                f"noncanonical claim state is ambiguous: {path}"
            )
        claim_id = value.get("claim_id")
        if claim_id is not None and (
            not isinstance(claim_id, str) or AUTHORITY_ID.fullmatch(claim_id) is None
        ):
            raise ConfigurationError(
                f"noncanonical claim fence is malformed: {path}"
            )
        identity = str(claim_id) if claim_id is not None else raw_digest
    else:
        if value.get("status") != "ACTIVE":
            raise ConfigurationError(
                f"noncanonical validation lease state is ambiguous: {path}"
            )
        lease_id = value.get("lease_id")
        if lease_id is not None and (
            not isinstance(lease_id, str) or AUTHORITY_ID.fullmatch(lease_id) is None
        ):
            raise ConfigurationError(
                f"noncanonical validation lease fence is malformed: {path}"
            )
        identity = str(lease_id) if lease_id is not None else raw_digest
    return value, expires, identity


def _parse_stale_legacy_dispatch_release(
    path: Path,
    raw: bytes,
    *,
    canonical_target_sha: str,
    canonical_plan_fingerprint: str,
) -> tuple[Mapping[str, Any], str, str]:
    value = _strict_authority_object(
        path,
        raw,
        kind="dispatcher-release",
        schemas=_LEGACY_DISPATCH_RELEASE_SCHEMAS,
    )
    if value.get("kind") != "hive-mind-autopilot-dispatch-release-v1":
        raise ConfigurationError(
            f"noncanonical dispatcher release kind is invalid: {path}"
        )
    material = dict(value)
    release_id = material.pop("release_id", None)
    if (
        not isinstance(release_id, str)
        or AUTHORITY_ID.fullmatch(release_id) is None
        or release_id != digest_json(material)
    ):
        raise ConfigurationError(
            f"noncanonical dispatcher release digest is invalid: {path}"
        )
    try:
        issued_at = format_time(parse_time(value.get("issued_at")))
    except (TypeError, ValueError) as error:
        raise ConfigurationError(
            f"noncanonical dispatcher release time is malformed: {path}"
        ) from error
    if (
        value.get("target_sha") == canonical_target_sha
        and value.get("plan_fingerprint") == canonical_plan_fingerprint
    ):
        raise ConfigurationError(
            f"noncanonical dispatcher release may still be live: {path}"
        )
    return value, issued_at, release_id


def _canonical_migration_dispatch_identity(repo_root: Path) -> tuple[str, str]:
    control_path = repo_root / ".autopilot" / "control-plane.json"
    control = read_json(control_path)
    if not isinstance(control, Mapping) or not isinstance(control.get("target"), Mapping):
        raise ConfigurationError("runtime migration control-plane target is malformed")
    plan_fingerprint = control.get("plan_fingerprint")
    target = control["target"]
    target_branch = target.get("branch")
    if (
        not isinstance(plan_fingerprint, str)
        or AUTHORITY_ID.fullmatch(plan_fingerprint) is None
        or not isinstance(target_branch, str)
        or not target_branch.strip()
    ):
        raise ConfigurationError("runtime migration dispatch identity is incomplete")
    target_sha: str | None = None
    for reference in (
        f"refs/remotes/origin/{target_branch}",
        f"refs/heads/{target_branch}",
    ):
        completed = subprocess.run(
            ("git", "-C", str(repo_root), "rev-parse", "--verify", reference),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        candidate = completed.stdout.strip()
        if completed.returncode == 0 and FULL_SHA.fullmatch(candidate):
            target_sha = candidate
            break
    if target_sha is None:
        candidate = target.get("baseline_sha")
        if isinstance(candidate, str) and FULL_SHA.fullmatch(candidate):
            target_sha = candidate
    if target_sha is None:
        raise ConfigurationError(
            "runtime migration cannot authenticate the canonical target SHA"
        )
    return target_sha, plan_fingerprint


def _migration_material(
    repository_identity: Mapping[str, object],
    inventory: Sequence[str],
    sources: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    return {
        "repository_identity": dict(repository_identity),
        "worktree_inventory": list(inventory),
        "sources": [
            {
                key: source[key]
                for key in (
                    "source_path",
                    "source_root",
                    "relative_path",
                    "authority_kind",
                    "source_digest",
                    "authority_identity",
                    "expires_at",
                    "classification",
                )
            }
            for source in sources
        ],
    }


def _migration_root_id(root: str) -> str:
    return sha256(os.path.normcase(root).encode("utf-8")).hexdigest()[:20]


def _migration_storage_id(authority_id: str) -> str:
    """Return a compact path component while the manifest retains the full id."""

    return _compact_authority_path_id(authority_id)


def _migration_evidence_name(source: Mapping[str, Any]) -> str:
    """Name one migration blob without reproducing an unbounded source path."""

    relative = str(source.get("relative_path"))
    source_digest = str(source.get("source_digest"))
    if (
        not relative
        or AUTHORITY_ID.fullmatch(source_digest) is None
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
    ):
        raise ConfigurationError("migration evidence identity is invalid")
    material = (relative + "\0" + source_digest).encode("utf-8")
    return sha256(material).hexdigest()[:20] + ".bin"


def _assert_distinct_migration_paths(
    records: Sequence[Mapping[str, Any]],
    *,
    label: str,
) -> None:
    """Fail closed if compact path tokens collide within one sealed cut."""

    for field in ("archive_path", "retired_path"):
        values = [str(record.get(field)) for record in records]
        if len(values) != len(set(values)):
            raise ConfigurationError(f"{label} {field} paths collide")


def _inspect_noncanonical_authority(
    repo_root: Path,
    coordination_dir: Path,
    *,
    now: datetime,
) -> tuple[tuple[Path, ...], list[dict[str, Any]]]:
    roots = _linked_worktree_roots(repo_root)
    canonical = _reject_link_components(
        coordination_dir,
        label="runtime state path",
    ).resolve()
    sources: list[dict[str, Any]] = []
    canonical_target_sha, canonical_plan_fingerprint = (
        _canonical_migration_dispatch_identity(repo_root)
    )
    for root in roots:
        root = _reject_link_components(root, label="linked worktree root").resolve()
        state = root / ".autopilot" / "state"
        if state.exists() or _is_link_like(state):
            state = _reject_link_components(
                state,
                label="noncanonical runtime state",
            )
        if state.resolve() == canonical or not state.is_dir():
            continue
        for relative in _NONCANONICAL_LEDGER_PATHS:
            ledger = state / relative
            if not ledger.exists() and not _is_link_like(ledger):
                continue
            raw = _read_regular_authority_bytes(
                ledger,
                label="noncanonical runtime ledger",
            )
            if raw:
                raise ConfigurationError(
                    "noncanonical task, sidecar, or attended ledger requires "
                    f"explicit semantic reconciliation: {ledger}"
                )
        claims_dir = state / "claims"
        if claims_dir.exists() or _is_link_like(claims_dir):
            claims_dir = _reject_link_components(
                claims_dir,
                label="noncanonical claims directory",
            )
            if not claims_dir.is_dir():
                raise ConfigurationError(
                    f"noncanonical claims path is not a directory: {claims_dir}"
                )
            unexpected = [
                path
                for path in claims_dir.iterdir()
                if path.is_file() and path.suffix != ".json"
            ]
            if unexpected:
                raise ConfigurationError(
                    "noncanonical claims inventory is ambiguous: "
                    + ", ".join(str(path) for path in unexpected)
                )
            for path in sorted(claims_dir.glob("*.json")):
                raw = _read_regular_authority_bytes(
                    path,
                    label="noncanonical claim authority",
                )
                _value, expires, identity = _parse_expired_legacy_authority(
                    path,
                    raw,
                    kind="claim",
                    now=now,
                )
                sources.append(
                    {
                        "source_path": str(path),
                        "source_root": str(root),
                        "relative_path": f"claims/{path.name}",
                        "authority_kind": "claim",
                        "source_digest": "sha256:" + sha256(raw).hexdigest(),
                        "authority_identity": identity,
                        "expires_at": format_time(expires),
                        "classification": "EXPIRED_CLAIM",
                        "source_bytes_base64": base64.b64encode(raw).decode("ascii"),
                    }
                )
        lease_path = state / "global-validation-lease.json"
        if lease_path.exists() or _is_link_like(lease_path):
            raw = _read_regular_authority_bytes(
                lease_path,
                label="noncanonical validation lease",
            )
            _value, expires, identity = _parse_expired_legacy_authority(
                lease_path,
                raw,
                kind="validation-lease",
                now=now,
            )
            sources.append(
                {
                    "source_path": str(lease_path),
                    "source_root": str(root),
                    "relative_path": "global-validation-lease.json",
                    "authority_kind": "validation-lease",
                    "source_digest": "sha256:" + sha256(raw).hexdigest(),
                    "authority_identity": identity,
                    "expires_at": format_time(expires),
                    "classification": "EXPIRED_VALIDATION_LEASE",
                    "source_bytes_base64": base64.b64encode(raw).decode("ascii"),
                }
            )
        dispatcher_path = state / "dispatcher-release.json"
        if dispatcher_path.exists() or _is_link_like(dispatcher_path):
            raw = _read_regular_authority_bytes(
                dispatcher_path,
                label="noncanonical dispatcher release",
            )
            _value, issued_at, identity = _parse_stale_legacy_dispatch_release(
                dispatcher_path,
                raw,
                canonical_target_sha=canonical_target_sha,
                canonical_plan_fingerprint=canonical_plan_fingerprint,
            )
            sources.append(
                {
                    "source_path": str(dispatcher_path),
                    "source_root": str(root),
                    "relative_path": "dispatcher-release.json",
                    "authority_kind": "dispatcher-release",
                    "source_digest": "sha256:" + sha256(raw).hexdigest(),
                    "authority_identity": identity,
                    "expires_at": None,
                    "classification": "STALE_DISPATCH_RELEASE@" + issued_at,
                    "source_bytes_base64": base64.b64encode(raw).decode("ascii"),
                }
            )
    return roots, sorted(sources, key=lambda item: str(item["source_path"]))


def _plan_migration_paths(
    coordination_dir: Path,
    migration_id: str,
    source: Mapping[str, Any],
) -> dict[str, Any]:
    root = Path(str(source["source_root"]))
    archive = (
        coordination_dir
        / "ma"
        / _migration_storage_id(migration_id)
        / _migration_root_id(str(root))
        / _migration_evidence_name(source)
    )
    retired = (
        root
        / ".autopilot"
        / "state"
        / "rr"
        / _migration_storage_id(migration_id)
        / _migration_evidence_name(source)
    )
    return {
        **source,
        "archive_path": str(archive),
        "retired_path": str(retired),
        "rollback": {
            "from": str(retired),
            "to": str(source["source_path"]),
            "requires_digest": str(source["source_digest"]),
        },
    }


def _validate_migration_manifest(
    manifest: Mapping[str, Any],
    *,
    repository_identity: Mapping[str, object],
    inventory: Sequence[str],
    coordination_dir: Path,
) -> list[Mapping[str, Any]]:
    expected_manifest_fields = {
        "schema_version",
        "kind",
        "status",
        "migration_id",
        "repository_identity",
        "actor",
        "prepared_at",
        "worktree_inventory",
        "sources",
    }
    if manifest.get("status") == "COMPLETE":
        expected_manifest_fields.add("completed_at")
    if set(manifest) != expected_manifest_fields:
        raise ConfigurationError("runtime bootstrap migration manifest schema is ambiguous")
    if manifest.get("schema_version") != 1 or manifest.get("kind") != RUNTIME_BOOTSTRAP_MIGRATION_KIND:
        raise ConfigurationError("runtime bootstrap migration manifest is malformed")
    if manifest.get("status") not in {"PREPARED", "COMPLETE"}:
        raise ConfigurationError("runtime bootstrap migration status is malformed")
    if manifest.get("repository_identity") != repository_identity:
        raise ConfigurationError("runtime bootstrap migration repository identity changed")
    if manifest.get("worktree_inventory") != list(inventory):
        raise ConfigurationError("runtime bootstrap migration worktree inventory changed")
    if not isinstance(manifest.get("actor"), str) or not str(manifest["actor"]).strip():
        raise ConfigurationError("runtime bootstrap migration actor is invalid")
    try:
        prepared_at = parse_time(manifest.get("prepared_at"))
        completed_at = (
            parse_time(manifest.get("completed_at"))
            if manifest.get("status") == "COMPLETE"
            else None
        )
    except (TypeError, ValueError) as error:
        raise ConfigurationError("runtime bootstrap migration time is invalid") from error
    if completed_at is not None and completed_at < prepared_at:
        raise ConfigurationError("runtime bootstrap migration completion predates preparation")
    raw_sources = manifest.get("sources")
    if not isinstance(raw_sources, list) or not all(
        isinstance(item, Mapping) for item in raw_sources
    ):
        raise ConfigurationError("runtime bootstrap migration sources are malformed")
    sources = [dict(item) for item in raw_sources]
    material = _migration_material(repository_identity, inventory, sources)
    migration_id = digest_json(material)
    if manifest.get("migration_id") != migration_id:
        raise ConfigurationError("runtime bootstrap migration identity is malformed")
    allowed_roots = {str(item) for item in inventory}
    for source in sources:
        if set(source) != {
            "source_path",
            "source_root",
            "relative_path",
            "authority_kind",
            "source_digest",
            "authority_identity",
            "expires_at",
            "classification",
            "source_bytes_base64",
            "archive_path",
            "retired_path",
            "rollback",
        }:
            raise ConfigurationError("runtime bootstrap migration source schema is ambiguous")
        root = str(source.get("source_root"))
        relative_text = str(source.get("relative_path"))
        if root not in allowed_roots or (
            relative_text
            not in {"global-validation-lease.json", "dispatcher-release.json"}
            and not re.fullmatch(r"claims/[^/\\]+\.json", relative_text)
        ):
            raise ConfigurationError("runtime bootstrap migration source scope is invalid")
        expected_source = Path(root) / ".autopilot" / "state" / Path(relative_text)
        if Path(str(source.get("source_path"))) != expected_source:
            raise ConfigurationError("runtime bootstrap migration source path is invalid")
        planned = _plan_migration_paths(
            coordination_dir,
            migration_id,
            source,
        )
        for key in ("archive_path", "retired_path", "rollback"):
            if source.get(key) != planned[key]:
                raise ConfigurationError(
                    f"runtime bootstrap migration {key} is invalid"
                )
        try:
            payload = base64.b64decode(
                str(source.get("source_bytes_base64")),
                validate=True,
            )
        except (ValueError, TypeError) as error:
            raise ConfigurationError(
                "runtime bootstrap migration source bytes are malformed"
            ) from error
        if "sha256:" + sha256(payload).hexdigest() != source.get("source_digest"):
            raise ConfigurationError("runtime bootstrap migration source digest changed")
    _assert_distinct_migration_paths(
        sources,
        label="runtime bootstrap migration",
    )
    return sources


def _retire_migration_source(source: Mapping[str, Any]) -> None:
    try:
        payload = base64.b64decode(
            str(source["source_bytes_base64"]),
            validate=True,
        )
    except (ValueError, TypeError) as error:
        raise ConfigurationError("migration source bytes are malformed") from error
    source_path = Path(str(source["source_path"]))
    retired_path = Path(str(source["retired_path"]))
    archive_path = Path(str(source["archive_path"]))
    _reject_link_components(archive_path, label="migration authority archive")
    if not archive_path.is_file() or archive_path.read_bytes() != payload:
        raise ConfigurationError(
            f"migration authority archive is absent or changed: {archive_path}"
        )
    retired_path.parent.mkdir(parents=True, exist_ok=True)
    _reject_link_components(retired_path.parent, label="retired authority directory")
    if retired_path.exists() or _is_link_like(retired_path):
        _reject_link_components(retired_path, label="retired authority path")
        if retired_path.read_bytes() != payload:
            raise ConfigurationError(
                f"retired authority conflicts with prepared bytes: {retired_path}"
            )
    else:
        link_source = source_path if source_path.is_file() else archive_path
        _reject_link_components(link_source, label="prepared authority evidence")
        if link_source.read_bytes() != payload:
            raise ConfigurationError(
                f"prepared authority evidence changed before retirement: {link_source}"
            )
        try:
            os.link(link_source, retired_path, follow_symlinks=False)
        except FileExistsError:
            if retired_path.read_bytes() != payload:
                raise ConfigurationError(
                    f"retired authority raced with conflicting bytes: {retired_path}"
                )
        except OSError:
            # Cross-volume runtime roots cannot hard-link. The exclusive,
            # byte-identical copy is equally durable evidence after parent fsync.
            exclusive_write_bytes_or_identical(retired_path, payload)
        _fsync_parent_directory(retired_path.parent)
    if not retired_path.is_file() or retired_path.read_bytes() != payload:
        raise ConfigurationError(
            f"retired authority evidence is not durable: {retired_path}"
        )
    _fsync_parent_directory(retired_path.parent)
    if source_path.exists() or _is_link_like(source_path):
        _reject_link_components(source_path, label="prepared authority source")
        if source_path.read_bytes() != payload:
            raise ConfigurationError(
                f"prepared authority source changed during retirement: {source_path}"
            )
        source_path.unlink()
        _fsync_parent_directory(source_path.parent)
    if source_path.exists() or _is_link_like(source_path):
        raise ConfigurationError(
            f"prepared authority source retirement was not durable: {source_path}"
        )


def _legacy_semantic_context(
    root: Path,
    repository_identity: Mapping[str, object],
) -> Mapping[str, object]:
    """Return one strict worktree plan/target identity for reconciliation."""

    from orchestration import OrchestrationError, _live_launch_context

    control_path = root / ".autopilot" / "control-plane.json"
    plan_path = root / ".autopilot" / "plan.json"
    control_raw = _read_regular_authority_bytes(
        control_path, label="legacy reconciliation control plane"
    )
    plan_raw = _read_regular_authority_bytes(
        plan_path, label="legacy reconciliation plan"
    )
    try:
        context = _live_launch_context(root)
    except OrchestrationError as error:
        raise ConfigurationError(
            f"legacy worktree plan identity is invalid: {root}: {error}"
        ) from error
    if context.get("repository") != repository_identity.get("repository"):
        raise ConfigurationError(
            "legacy worktree repository differs from canonical transport identity"
        )
    return {
        "repository": context["repository"],
        "target_branch": context["target_branch"],
        "target_sha": context["target_sha"],
        "plan_fingerprint": context["plan_fingerprint"],
        "control_digest": "sha256:" + sha256(control_raw).hexdigest(),
        "plan_digest": "sha256:" + sha256(plan_raw).hexdigest(),
    }


def _legacy_semantic_inventory(
    repo_root: Path,
    coordination_dir: Path,
    *,
    repository_identity: Mapping[str, object],
) -> tuple[tuple[Path, ...], list[dict[str, Any]]]:
    """Classify exact noncanonical ledgers without mutating any source."""

    from orchestration import (
        ACTIVE_BINDING_STATES,
        OrchestrationError,
        _binding_events_unlocked,
    )
    from sidecar_execution import (
        ACTIVE_SIDECAR_STATES,
        SidecarPolicyError,
    )
    from sidecar_execution import (
        _events_unlocked as _sidecar_events_unlocked,
    )

    roots = _linked_worktree_roots(repo_root)
    canonical = coordination_dir.resolve()
    kernel = runtime_kernel_identity(repo_root)
    entries: list[dict[str, Any]] = []
    for raw_root in roots:
        root = _reject_link_components(
            raw_root, label="legacy semantic worktree root"
        ).resolve()
        state = root / ".autopilot" / "state"
        if state.resolve() == canonical or not state.is_dir():
            continue
        paths = [
            state / relative
            for relative in _NONCANONICAL_LEDGER_PATHS
            if (state / relative).is_file() and (state / relative).stat().st_size
        ]
        if not paths:
            continue
        context_error: str | None = None
        try:
            context = _legacy_semantic_context(root, repository_identity)
        except ConfigurationError as error:
            context_error = str(error)
            context = {
                "repository": repository_identity["repository"],
                "target_branch": None,
                "target_sha": None,
                "plan_fingerprint": None,
                "control_digest": None,
                "plan_digest": None,
            }
        task_path = state / "task-bindings.jsonl"
        task_events: tuple[Mapping[str, object], ...] = ()
        task_adoptable = False
        task_active_ids: list[str] = []
        task_reason = context_error
        if task_path in paths and context_error is None:
            try:
                task_events = _binding_events_unlocked(root, state)
                identity_fields_present = [
                    any(
                        field in event
                        for field in ("execution_id", "execution_namespace")
                    )
                    for event in task_events
                ]
                if any(identity_fields_present):
                    task_reason = (
                        "NONCANONICAL_EXECUTION_IDENTITY_REQUIRES_QUARANTINE"
                    )
                elif any(
                    (
                        event.get("repository") is not None
                        and event.get("repository") != context["repository"]
                    )
                    or (
                        event.get("target_branch") is not None
                        and event.get("target_branch")
                        != context["target_branch"]
                    )
                    or (
                        event.get("target_sha") is not None
                        and event.get("target_sha") != context["target_sha"]
                    )
                    or (
                        event.get("plan_fingerprint") is not None
                        and event.get("plan_fingerprint")
                        != context["plan_fingerprint"]
                    )
                    for event in task_events
                ):
                    task_reason = "TASK_LEDGER_PLAN_OR_TARGET_IDENTITY_CONFLICT"
                else:
                    task_adoptable = True
                    task_reason = "LEGACY_TASK_AUTHORITY_FENCED_DURING_ADOPTION"
                    latest: dict[str, Mapping[str, object]] = {}
                    for event in task_events:
                        latest[str(event["launch_instruction_id"])] = event
                    task_active_ids = sorted(
                        instruction_id
                        for instruction_id, event in latest.items()
                        if event.get("state") in ACTIVE_BINDING_STATES
                    )
            except (OrchestrationError, OSError) as error:
                task_reason = f"TASK_LEDGER_INVALID:{error}"
        namespace = "legacy-" + _migration_root_id(str(root))
        execution_identity: Mapping[str, object] | None = None
        if task_adoptable:
            execution_identity = execution_namespace_identity(
                repository_identity,
                kernel_identity=kernel,
                namespace=namespace,
                target_branch=str(context["target_branch"]),
                plan_fingerprint=str(context["plan_fingerprint"]),
            )
        sidecar_latest: dict[str, Mapping[str, object]] = {}
        sidecar_valid = False
        sidecar_reason = context_error
        sidecar_path = state / "sidecar-bindings.jsonl"
        if sidecar_path in paths and context_error is None:
            try:
                sidecar_events = _sidecar_events_unlocked(root, state)
                for event in sidecar_events:
                    sidecar_latest[str(event["sidecar_id"])] = event
                parent_ids = {
                    str(event["launch_instruction_id"])
                    for event in task_events
                }
                if not task_adoptable:
                    sidecar_reason = "SIDECAR_PARENT_LEDGER_NOT_ADOPTABLE"
                elif any(
                    event.get("parent_launch_instruction_id") not in parent_ids
                    for event in sidecar_latest.values()
                ):
                    sidecar_reason = "SIDECAR_PARENT_AUTHORITY_IS_AMBIGUOUS"
                elif any(
                    event.get("state") in ACTIVE_SIDECAR_STATES
                    for event in sidecar_latest.values()
                ):
                    sidecar_reason = "ACTIVE_SIDECAR_REQUIRES_HOST_RECONCILIATION"
                else:
                    sidecar_valid = True
                    sidecar_reason = "TERMINAL_SIDECAR_EVIDENCE_ADOPTED"
            except (SidecarPolicyError, OSError) as error:
                sidecar_reason = f"SIDECAR_LEDGER_INVALID:{error}"
        for path in sorted(paths, key=str):
            relative = path.relative_to(state).as_posix()
            raw = _read_regular_authority_bytes(
                path, label="legacy semantic authority"
            )
            if relative == "task-bindings.jsonl":
                adopt = task_adoptable
                reason = str(task_reason)
                active_ids = task_active_ids
                authority_kind = "task-binding-ledger"
            elif relative == "sidecar-bindings.jsonl":
                adopt = sidecar_valid
                reason = str(sidecar_reason)
                active_ids = sorted(
                    sidecar_id
                    for sidecar_id, event in sidecar_latest.items()
                    if event.get("state") in ACTIVE_SIDECAR_STATES
                )
                authority_kind = "sidecar-binding-ledger"
            elif relative == "host/attended-threads.json":
                # A card ledger is not host lifecycle evidence.  Preserve it as
                # a typed obligation rather than pretending its threads were
                # cancelled or can be adopted autonomously.
                read_strict_canonical_json(
                    path, label="legacy attended thread ledger"
                )
                adopt = False
                reason = "ATTENDED_THREADS_REQUIRE_AUTHENTICATED_HOST_RECONCILIATION"
                active_ids = []
                authority_kind = "attended-thread-ledger"
            else:
                read_strict_canonical_json(
                    path, label="legacy dispatcher generation"
                )
                adopt = False
                reason = "DISPATCHER_GENERATION_IS_NOT_PORTABLE_EXECUTION_AUTHORITY"
                active_ids = []
                authority_kind = "dispatcher-generation"
            entries.append(
                {
                    "source_path": str(path),
                    "source_root": str(root),
                    "relative_path": relative,
                    "authority_kind": authority_kind,
                    "source_digest": "sha256:" + sha256(raw).hexdigest(),
                    "source_bytes_base64": base64.b64encode(raw).decode("ascii"),
                    "classification": "ADOPT_FENCED" if adopt else "QUARANTINE",
                    "reason": reason,
                    "target_branch": context["target_branch"],
                    "target_sha": context["target_sha"],
                    "plan_fingerprint": context["plan_fingerprint"],
                    "control_digest": context["control_digest"],
                    "plan_digest": context["plan_digest"],
                    "execution_namespace": namespace if adopt else None,
                    "execution_identity": (
                        dict(execution_identity)
                        if adopt and execution_identity is not None
                        else None
                    ),
                    "active_authority_ids": active_ids,
                }
            )
    return roots, sorted(entries, key=lambda item: str(item["source_path"]))


def _legacy_semantic_material(
    repository_identity: Mapping[str, object],
    inventory: Sequence[str],
    entries: Sequence[Mapping[str, Any]],
) -> Mapping[str, object]:
    fields = (
        "source_path",
        "source_root",
        "relative_path",
        "authority_kind",
        "source_digest",
        "classification",
        "reason",
        "target_branch",
        "target_sha",
        "plan_fingerprint",
        "control_digest",
        "plan_digest",
        "execution_namespace",
        "execution_identity",
        "active_authority_ids",
    )
    return {
        "repository_identity": dict(repository_identity),
        "worktree_inventory": list(inventory),
        "entries": [{field: entry[field] for field in fields} for entry in entries],
    }


def _plan_legacy_semantic_paths(
    coordination_dir: Path,
    reconciliation_id: str,
    entry: Mapping[str, Any],
) -> Mapping[str, Any]:
    root = Path(str(entry["source_root"]))
    relative = Path(str(entry["relative_path"]))
    archive = (
        coordination_dir
        / "ms"
        / _migration_storage_id(reconciliation_id)
        / _migration_root_id(str(root))
        / _migration_evidence_name(entry)
    )
    retired = (
        root
        / ".autopilot"
        / "state"
        / "rr"
        / _migration_storage_id(reconciliation_id)
        / _migration_evidence_name(entry)
    )
    destination: str | None = None
    quarantine: str | None = None
    identity = entry.get("execution_identity")
    if entry.get("classification") == "ADOPT_FENCED":
        if not isinstance(identity, Mapping):
            raise ConfigurationError(
                "adopted legacy semantic authority has no execution identity"
            )
        execution = execution_namespace_dir(
            coordination_dir, str(identity["execution_id"])
        )
        destination = str(execution / relative)
    else:
        quarantine_key = digest_json(
            {
                "kind": "hive-mind-legacy-quarantine-path-key-v1",
                "reconciliation_id": reconciliation_id,
                "source_path": entry["source_path"],
                "source_digest": entry["source_digest"],
            }
        )
        quarantine = str(
            coordination_dir
            / "arbiter"
            / "reconciliation-obligations"
            / (quarantine_key.removeprefix("sha256:") + ".json")
        )
    return {
        **dict(entry),
        "archive_path": str(archive),
        "retired_path": str(retired),
        "destination_path": destination,
        "quarantine_path": quarantine,
        "rollback": {
            "from": str(retired),
            "to": str(entry["source_path"]),
            "requires_digest": str(entry["source_digest"]),
        },
    }


def _validate_legacy_semantic_manifest(
    manifest: Mapping[str, Any],
    *,
    repository_identity: Mapping[str, object],
    inventory: Sequence[str],
    coordination_dir: Path,
) -> list[Mapping[str, Any]]:
    manifest_fields = {
        "schema_version",
        "kind",
        "status",
        "reconciliation_id",
        "repository_identity",
        "actor",
        "prepared_at",
        "worktree_inventory",
        "entries",
    }
    if manifest.get("status") == "COMPLETE":
        manifest_fields.add("completed_at")
    if set(manifest) != manifest_fields:
        raise ConfigurationError(
            "legacy semantic reconciliation manifest schema is ambiguous"
        )
    if (
        manifest.get("schema_version") != 1
        or manifest.get("kind") != LEGACY_SEMANTIC_RECONCILIATION_KIND
        or manifest.get("status") not in {"PREPARED", "COMPLETE"}
        or manifest.get("repository_identity") != repository_identity
        or manifest.get("worktree_inventory") != list(inventory)
        or not isinstance(manifest.get("actor"), str)
        or not str(manifest["actor"]).strip()
    ):
        raise ConfigurationError("legacy semantic reconciliation manifest is invalid")
    try:
        prepared = parse_time(manifest.get("prepared_at"))
        completed = (
            parse_time(manifest.get("completed_at"))
            if manifest.get("status") == "COMPLETE"
            else None
        )
    except (TypeError, ValueError) as error:
        raise ConfigurationError(
            "legacy semantic reconciliation manifest time is invalid"
        ) from error
    if completed is not None and completed < prepared:
        raise ConfigurationError(
            "legacy semantic reconciliation completion predates preparation"
        )
    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, list) or not all(
        isinstance(entry, Mapping) for entry in raw_entries
    ):
        raise ConfigurationError(
            "legacy semantic reconciliation entries are malformed"
        )
    entries = [dict(entry) for entry in raw_entries]
    reconciliation_id = digest_json(
        _legacy_semantic_material(repository_identity, inventory, entries)
    )
    if manifest.get("reconciliation_id") != reconciliation_id:
        raise ConfigurationError(
            "legacy semantic reconciliation identity is invalid"
        )
    base_fields = set(
        _legacy_semantic_material(repository_identity, inventory, entries)[
            "entries"
        ][0]
    ) if entries else {
        "source_path", "source_root", "relative_path", "authority_kind",
        "source_digest", "classification", "reason", "target_branch",
        "target_sha", "plan_fingerprint", "control_digest", "plan_digest",
        "execution_namespace", "execution_identity", "active_authority_ids",
    }
    planned_fields = base_fields | {
        "source_bytes_base64",
        "archive_path",
        "retired_path",
        "destination_path",
        "quarantine_path",
        "rollback",
    }
    allowed_roots = set(inventory)
    for entry in entries:
        if set(entry) != planned_fields:
            raise ConfigurationError(
                "legacy semantic reconciliation entry schema is ambiguous"
            )
        if (
            entry.get("source_root") not in allowed_roots
            or entry.get("relative_path") not in _NONCANONICAL_LEDGER_PATHS
            or entry.get("classification") not in {"ADOPT_FENCED", "QUARANTINE"}
            or not isinstance(entry.get("active_authority_ids"), list)
            or entry["active_authority_ids"]
            != sorted(set(entry["active_authority_ids"]))
        ):
            raise ConfigurationError(
                "legacy semantic reconciliation entry scope is invalid"
            )
        expected_source = (
            Path(str(entry["source_root"]))
            / ".autopilot"
            / "state"
            / str(entry["relative_path"])
        )
        if Path(str(entry["source_path"])) != expected_source:
            raise ConfigurationError(
                "legacy semantic reconciliation source path is invalid"
            )
        planned = _plan_legacy_semantic_paths(
            coordination_dir, reconciliation_id, entry
        )
        for field in (
            "archive_path",
            "retired_path",
            "destination_path",
            "quarantine_path",
            "rollback",
        ):
            if entry.get(field) != planned.get(field):
                raise ConfigurationError(
                    f"legacy semantic reconciliation {field} is invalid"
                )
        try:
            payload = base64.b64decode(
                str(entry.get("source_bytes_base64")), validate=True
            )
        except (TypeError, ValueError) as error:
            raise ConfigurationError(
                "legacy semantic reconciliation bytes are malformed"
            ) from error
        if "sha256:" + sha256(payload).hexdigest() != entry.get("source_digest"):
            raise ConfigurationError(
                "legacy semantic reconciliation source digest changed"
            )
    _assert_distinct_migration_paths(
        entries,
        label="legacy semantic reconciliation",
    )
    return entries


def _legacy_quarantine_receipt(
    *,
    repository_identity: Mapping[str, object],
    reconciliation_id: str,
    entry: Mapping[str, Any],
    recorded_at: str,
) -> Mapping[str, object]:
    material: dict[str, object] = {
        "schema_version": 1,
        "kind": LEGACY_AUTHORITY_QUARANTINE_KIND,
        "state": "QUARANTINED",
        "repository": repository_identity["repository"],
        "repository_transport_digest": repository_identity["transport_digest"],
        "reconciliation_id": reconciliation_id,
        "source_root": entry["source_root"],
        "relative_path": entry["relative_path"],
        "authority_kind": entry["authority_kind"],
        "source_digest": entry["source_digest"],
        "target_branch": entry["target_branch"],
        "plan_fingerprint": entry["plan_fingerprint"],
        "execution_namespace": entry["execution_namespace"],
        "execution_id": (
            entry["execution_identity"].get("execution_id")
            if isinstance(entry.get("execution_identity"), Mapping)
            else None
        ),
        "active_authority_ids": list(entry["active_authority_ids"]),
        "reason": entry["reason"],
        "external_cancellation": "NOT_CLAIMED",
        "archive_path": entry["archive_path"],
        "recorded_at": recorded_at,
    }
    return {**material, "record_id": digest_json(material)}


def _legacy_authority_quarantine_obligations_unlocked(
    coordination_dir: str | Path,
) -> tuple[Mapping[str, object], ...]:
    directory = (
        Path(coordination_dir).resolve()
        / "arbiter"
        / "reconciliation-obligations"
    )
    if not directory.exists() and not _is_link_like(directory):
        return ()
    _reject_link_components(
        directory, label="legacy reconciliation obligation directory"
    )
    if not directory.is_dir():
        raise ConfigurationError(
            "legacy reconciliation obligation path is not a directory"
        )
    result: list[Mapping[str, object]] = []
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        _reject_link_components(path, label="legacy reconciliation obligation")
        if (
            not path.is_file()
            or re.fullmatch(r"[0-9a-f]{64}\.json", path.name) is None
        ):
            raise ConfigurationError(
                "legacy reconciliation obligation inventory is ambiguous"
            )
        value = read_strict_canonical_json(
            path,
            label="legacy reconciliation obligation",
            expected_fields=LEGACY_AUTHORITY_QUARANTINE_FIELDS,
        )
        if not isinstance(value, Mapping):
            raise ConfigurationError(
                "legacy reconciliation obligation is not an object"
            )
        material = dict(value)
        record_id = material.pop("record_id", None)
        try:
            parse_time(value.get("recorded_at"))
        except (TypeError, ValueError) as error:
            raise ConfigurationError(
                "legacy reconciliation obligation time is invalid"
            ) from error
        if (
            value.get("schema_version") != 1
            or value.get("kind") != LEGACY_AUTHORITY_QUARANTINE_KIND
            or value.get("state") != "QUARANTINED"
            or value.get("external_cancellation") != "NOT_CLAIMED"
            or AUTHORITY_ID.fullmatch(str(value.get("reconciliation_id")))
            is None
            or AUTHORITY_ID.fullmatch(str(value.get("source_digest"))) is None
            or value.get("active_authority_ids")
            != sorted(set(value.get("active_authority_ids", [])))
            or record_id != digest_json(material)
            or path.stem
            != digest_json(
                {
                    "kind": "hive-mind-legacy-quarantine-path-key-v1",
                    "reconciliation_id": value.get("reconciliation_id"),
                    "source_path": str(
                        Path(str(value.get("source_root")))
                        / ".autopilot"
                        / "state"
                        / str(value.get("relative_path"))
                    ),
                    "source_digest": value.get("source_digest"),
                }
            ).removeprefix("sha256:")
        ):
            raise ConfigurationError(
                "legacy reconciliation obligation is invalid"
            )
        archive = Path(str(value.get("archive_path")))
        if (
            not archive.is_file()
            or "sha256:" + sha256(archive.read_bytes()).hexdigest()
            != value.get("source_digest")
        ):
            raise ConfigurationError(
                "legacy reconciliation obligation archive evidence changed"
            )
        result.append(dict(value))
    return tuple(result)


def reconcile_legacy_worktree_execution_authority(
    repo_root: str | Path,
    coordination_dir: str | Path,
    *,
    host_runtime_dir: str | Path,
    actor: str,
    clock: Callable[[], datetime] = utc_now,
) -> Mapping[str, Any]:
    """Reconcile competing worktree ledgers before runtime READY.

    The caller holds the machine-user host lock and repository bootstrap lock.
    Compatible legacy task ledgers are moved to deterministic execution
    namespaces and every active launch is append-only fenced.  Terminal sidecar
    evidence follows its parent ledger.  Attended, active-sidecar, conflicting,
    or newer worktree-local authority is archived and represented by a typed
    arbiter obligation; external cancellation is never claimed.
    """

    if not actor.strip():
        raise ConfigurationError("legacy semantic reconciliation actor is required")
    root = _reject_link_components(
        repo_root, label="legacy semantic repository root"
    ).resolve()
    directory = _reject_link_components(
        coordination_dir, label="legacy semantic coordination root"
    ).resolve()
    host_root = require_host_runtime(host_runtime_dir)
    if not runtime_file_lock_is_held(
        host_root / "locks" / "host-authority.lock"
    ):
        raise ConfigurationError(
            "legacy semantic reconciliation requires host authority"
        )
    if not runtime_file_lock_is_held(directory / RUNTIME_BOOTSTRAP_LOCK):
        raise ConfigurationError(
            "legacy semantic reconciliation requires bootstrap authority"
        )
    if (directory / RUNTIME_READY_MANIFEST).exists():
        raise ConfigurationError(
            "legacy semantic reconciliation is a pre-READY transaction"
        )
    repository_identity = runtime_repository_identity(root)
    if repository_identity is None:
        raise ConfigurationError(
            "legacy semantic reconciliation requires repository identity"
        )
    manifest_path = directory / LEGACY_SEMANTIC_RECONCILIATION_MANIFEST
    arbiter_lock = directory / "arbiter" / "locks" / "arbiter-authority.lock"
    with runtime_file_lock(arbiter_lock, timeout_seconds=120.0):
        roots = _linked_worktree_roots(root)
        inventory = [str(item) for item in roots]
        if manifest_path.exists() or _is_link_like(manifest_path):
            _reject_link_components(
                manifest_path,
                label="legacy semantic reconciliation manifest",
            )
            value = read_strict_canonical_json(
                manifest_path,
                label="legacy semantic reconciliation manifest",
            )
            if not isinstance(value, Mapping):
                raise ConfigurationError(
                    "legacy semantic reconciliation manifest is not an object"
                )
            manifest = dict(value)
            entries = _validate_legacy_semantic_manifest(
                manifest,
                repository_identity=repository_identity,
                inventory=inventory,
                coordination_dir=directory,
            )
        else:
            roots, inspected = _legacy_semantic_inventory(
                root,
                directory,
                repository_identity=repository_identity,
            )
            inventory = [str(item) for item in roots]
            reconciliation_id = digest_json(
                _legacy_semantic_material(
                    repository_identity, inventory, inspected
                )
            )
            entries = [
                _plan_legacy_semantic_paths(
                    directory, reconciliation_id, entry
                )
                for entry in inspected
            ]
            _assert_distinct_migration_paths(
                entries,
                label="legacy semantic reconciliation",
            )
            manifest = {
                "schema_version": 1,
                "kind": LEGACY_SEMANTIC_RECONCILIATION_KIND,
                "status": "PREPARED",
                "reconciliation_id": reconciliation_id,
                "repository_identity": dict(repository_identity),
                "actor": actor,
                "prepared_at": format_time(clock()),
                "worktree_inventory": inventory,
                "entries": entries,
            }
            exclusive_write_json_or_identical(manifest_path, manifest)

        lock_paths: set[Path] = set()
        for entry in entries:
            source_root = Path(str(entry["source_root"]))
            state = source_root / ".autopilot" / "state"
            relative = str(entry["relative_path"])
            if relative == "task-bindings.jsonl":
                names = ("task-bindings.lock",)
            elif relative == "sidecar-bindings.jsonl":
                names = ("task-bindings.lock", "sidecar-bindings.lock")
            elif relative == "host/attended-threads.json":
                names = ("attended-host.lock",)
            else:
                names = ("dispatcher-admission.lock",)
            for name in names:
                lock_paths.add(state / "locks" / name)
                lock_paths.add(source_root / ".autopilot" / name)
        with ExitStack() as legacy_locks:
            for path in sorted(lock_paths, key=runtime_lock_order_key):
                legacy_locks.enter_context(
                    runtime_file_lock(path, timeout_seconds=120.0)
                )
            for entry in entries:
                payload = base64.b64decode(
                    str(entry["source_bytes_base64"]), validate=True
                )
                exclusive_write_bytes_or_identical(
                    Path(str(entry["archive_path"])), payload
                )
            identities: dict[str, Mapping[str, object]] = {}
            for entry in entries:
                identity = entry.get("execution_identity")
                if entry.get("classification") != "ADOPT_FENCED":
                    continue
                if not isinstance(identity, Mapping):
                    raise ConfigurationError(
                        "adopted legacy authority lost execution identity"
                    )
                execution_id = str(identity["execution_id"])
                if execution_id not in identities:
                    initialize_execution_namespace(directory, identity)
                    identities[execution_id] = identity
                elif identities[execution_id] != identity:
                    raise ConfigurationError(
                        "legacy authority partitions one execution id ambiguously"
                    )
            for entry in entries:
                payload = base64.b64decode(
                    str(entry["source_bytes_base64"]), validate=True
                )
                if entry.get("classification") == "ADOPT_FENCED":
                    destination = Path(str(entry["destination_path"]))
                    if destination.is_file():
                        installed = destination.read_bytes()
                        if not installed.startswith(payload):
                            raise ConfigurationError(
                                "legacy adopted authority does not retain its exact source prefix"
                            )
                    else:
                        exclusive_write_bytes_or_identical(destination, payload)
                    if entry.get("relative_path") == "task-bindings.jsonl":
                        from orchestration import (
                            ACTIVE_BINDING_STATES,
                            _append_binding_event_unlocked,
                            _binding_events_unlocked,
                            _latest_binding_events,
                            _transition_payload,
                        )

                        execution = destination.parent
                        with runtime_file_lock(
                            execution / "locks" / "dispatcher-admission.lock",
                            timeout_seconds=120.0,
                        ):
                            with runtime_file_lock(
                                execution / "locks" / "task-bindings.lock",
                                timeout_seconds=120.0,
                            ):
                                events = list(
                                    _binding_events_unlocked(root, execution)
                                )
                                latest = _latest_binding_events(events)
                                for instruction_id in sorted(latest):
                                    prior = latest[instruction_id]
                                    if prior.get("state") not in ACTIVE_BINDING_STATES:
                                        continue
                                    fenced = _append_binding_event_unlocked(
                                        root,
                                        _transition_payload(
                                            prior,
                                            resource_key=(
                                                prior.get("resource_key")
                                                or f"legacy:{instruction_id}"
                                            ),
                                            authority_epoch=(
                                                prior.get("authority_epoch")
                                                if type(prior.get("authority_epoch"))
                                                is int
                                                else 0
                                            ),
                                            state="SUPERSEDED",
                                            superseded_by=None,
                                            superseded_by_actor=actor,
                                            reason=(
                                                "pre-READY worktree authority reconciliation; "
                                                "external cancellation NOT_CLAIMED"
                                            ),
                                        ),
                                        events,
                                        execution,
                                    )
                                    events.append(fenced)
                                remaining = [
                                    event
                                    for event in _latest_binding_events(events).values()
                                    if event.get("state") in ACTIVE_BINDING_STATES
                                ]
                                if remaining:
                                    raise ConfigurationError(
                                        "legacy task authority remained active after fencing"
                                    )
                else:
                    receipt = _legacy_quarantine_receipt(
                        repository_identity=repository_identity,
                        reconciliation_id=str(manifest["reconciliation_id"]),
                        entry=entry,
                        recorded_at=str(manifest["prepared_at"]),
                    )
                    exclusive_write_json_or_identical(
                        Path(str(entry["quarantine_path"])), receipt
                    )
                _retire_migration_source(entry)
        current_inventory = [str(item) for item in _linked_worktree_roots(root)]
        if current_inventory != inventory:
            raise ConfigurationError(
                "legacy semantic reconciliation worktree inventory changed"
            )
        if manifest.get("status") != "COMPLETE":
            manifest = {
                **manifest,
                "status": "COMPLETE",
                "completed_at": format_time(clock()),
            }
            atomic_write_json(manifest_path, manifest)
        return manifest


def bootstrap_runtime_authority_migration(
    repo_root: str | Path,
    coordination_dir: str | Path,
    *,
    actor: str,
    clock: Callable[[], datetime] = utc_now,
) -> Mapping[str, Any]:
    """Retire only provably expired split authority before normal identity locks."""

    if not actor.strip():
        raise ConfigurationError("runtime bootstrap migration actor is required")
    root = _reject_link_components(repo_root, label="repository root").resolve()
    directory = _reject_link_components(
        coordination_dir,
        label="runtime state path",
    ).resolve()
    repository_identity = runtime_repository_identity(root)
    if repository_identity is None:
        raise ConfigurationError("runtime bootstrap migration requires repository identity")
    direct_lock = directory / RUNTIME_BOOTSTRAP_LOCK
    manifest_path = directory / RUNTIME_BOOTSTRAP_MANIFEST
    with runtime_file_lock(direct_lock, timeout_seconds=120.0):
        roots = _linked_worktree_roots(root)
        inventory = [str(item) for item in roots]
        if manifest_path.exists() or _is_link_like(manifest_path):
            _reject_link_components(
                manifest_path,
                label="runtime bootstrap migration manifest",
            )
            manifest_value = read_strict_canonical_json(
                manifest_path, label="runtime bootstrap migration manifest"
            )
            if not isinstance(manifest_value, Mapping):
                raise ConfigurationError(
                    "runtime bootstrap migration manifest must be an object"
                )
            manifest = dict(manifest_value)
            sources = _validate_migration_manifest(
                manifest,
                repository_identity=repository_identity,
                inventory=inventory,
                coordination_dir=directory,
            )
        else:
            roots, inspected = _inspect_noncanonical_authority(
                root,
                directory,
                now=clock(),
            )
            inventory = [str(item) for item in roots]
            material = _migration_material(
                repository_identity,
                inventory,
                inspected,
            )
            migration_id = digest_json(material)
            sources = [
                _plan_migration_paths(directory, migration_id, source)
                for source in inspected
            ]
            _assert_distinct_migration_paths(
                sources,
                label="runtime bootstrap migration",
            )
            manifest = {
                "schema_version": 1,
                "kind": RUNTIME_BOOTSTRAP_MIGRATION_KIND,
                "status": "PREPARED",
                "migration_id": migration_id,
                "repository_identity": dict(repository_identity),
                "actor": actor,
                "prepared_at": format_time(clock()),
                "worktree_inventory": inventory,
                "sources": sources,
            }
            exclusive_write_json_or_identical(manifest_path, manifest)
        for source in sources:
            payload = base64.b64decode(
                str(source["source_bytes_base64"]),
                validate=True,
            )
            exclusive_write_bytes_or_identical(
                Path(str(source["archive_path"])),
                payload,
            )
            _retire_migration_source(source)
        current_roots = [str(item) for item in _linked_worktree_roots(root)]
        if current_roots != inventory:
            raise ConfigurationError(
                "runtime bootstrap migration worktree inventory changed during execution"
            )
        remaining = legacy_runtime_authority_paths(root, directory)
        if remaining:
            raise ConfigurationError(
                "runtime bootstrap migration discovered unprepared authority: "
                + ", ".join(str(path) for path in remaining)
            )
        if manifest.get("status") != "COMPLETE":
            manifest = {
                **manifest,
                "status": "COMPLETE",
                "completed_at": format_time(clock()),
            }
            atomic_write_json(manifest_path, manifest)
        return manifest


def _completed_bootstrap_manifest(
    repo_root: str | Path,
    coordination_dir: str | Path,
) -> tuple[Path, Path, Mapping[str, object], Mapping[str, Any]]:
    """Return authenticated bootstrap state without publishing runtime readiness."""

    root = _reject_link_components(repo_root, label="repository root").resolve()
    directory = _reject_link_components(
        coordination_dir,
        label="runtime state path",
    ).resolve()
    expected = runtime_repository_identity(root)
    if expected is None:
        raise ConfigurationError("runtime authority initialization requires repository identity")
    manifest_path = directory / RUNTIME_BOOTSTRAP_MANIFEST
    if not manifest_path.is_file() or _is_link_like(manifest_path):
        raise ConfigurationError(
            "runtime authority initialization requires a completed bootstrap migration"
        )
    manifest = read_strict_canonical_json(
        manifest_path,
        label="completed runtime bootstrap migration manifest",
    )
    if not isinstance(manifest, Mapping) or manifest.get("status") != "COMPLETE":
        raise ConfigurationError(
            "runtime authority bootstrap migration is incomplete or belongs to another repository"
        )
    inventory = manifest.get("worktree_inventory")
    if not isinstance(inventory, list) or not all(
        isinstance(item, str) and Path(item).is_absolute() for item in inventory
    ):
        raise ConfigurationError("completed bootstrap worktree inventory is invalid")
    sources = _validate_migration_manifest(
        manifest,
        repository_identity=expected,
        inventory=inventory,
        coordination_dir=directory,
    )
    for source in sources:
        payload = base64.b64decode(
            str(source["source_bytes_base64"]), validate=True
        )
        archive_path = Path(str(source["archive_path"]))
        _reject_link_components(archive_path, label="completed migration archive")
        if not archive_path.is_file() or archive_path.read_bytes() != payload:
            raise ConfigurationError(
                "completed runtime migration archive is absent or changed"
            )
        source_root = Path(str(source["source_root"]))
        if source_root.exists() or _is_link_like(source_root):
            _reject_link_components(source_root, label="historical migration root")
            source_path = Path(str(source["source_path"]))
            retired_path = Path(str(source["retired_path"]))
            if source_path.exists() or _is_link_like(source_path):
                raise ConfigurationError(
                    "completed runtime migration source authority reappeared"
                )
            _reject_link_components(retired_path, label="completed retired authority")
            if not retired_path.is_file() or retired_path.read_bytes() != payload:
                raise ConfigurationError(
                    "completed retired authority evidence is absent or changed"
                )
    return root, directory, expected, dict(manifest)


def stage_repository_runtime_authority(
    repo_root: str | Path,
    coordination_dir: str | Path,
    *,
    host_runtime_dir: str | Path | None = None,
) -> Mapping[str, object]:
    """Create identity and standard locks while authority remains unpublished.

    The caller must own the bootstrap migration lock.  Other processes continue
    to fail closed because the final ready marker does not exist yet.
    """

    root, directory, expected, _manifest = _completed_bootstrap_manifest(
        repo_root,
        coordination_dir,
    )
    bootstrap_lock = directory / RUNTIME_BOOTSTRAP_LOCK
    if not runtime_file_lock_is_held(bootstrap_lock):
        raise ConfigurationError(
            "runtime authority staging requires the bootstrap migration lock"
        )
    if host_runtime_dir is not None:
        host_root = require_host_runtime(host_runtime_dir)
        if not runtime_file_lock_is_held(host_root / "locks" / "host-authority.lock"):
            raise ConfigurationError(
                "runtime authority staging requires outer host authority"
            )
        bind_host_repository_runtime(
            host_root,
            repository=str(expected["repository"]),
            transport_digest=str(expected["transport_digest"]),
            coordination_dir=directory,
            bound_at=format_time(utc_now()),
            repo_root=root,
        )
    bind_repository_runtime_root(root, directory, expected)
    identity = ensure_repository_runtime_identity(root, directory, create=True)
    if identity != expected:
        raise ConfigurationError("runtime authority identity initialization failed")
    for lock_name in STANDARD_RUNTIME_LOCKS:
        with runtime_file_lock(directory / "locks" / lock_name):
            pass
    for lock_name in ARBITER_LOCKS:
        with runtime_file_lock(directory / "arbiter" / "locks" / lock_name):
            pass
    return identity


def _validated_attended_migration_receipt(
    coordination_dir: Path,
    value: Mapping[str, object],
) -> Mapping[str, object]:
    if value.get("outcome") == "ABSENT" and value.get("entries") == 0:
        ledger_path = coordination_dir / "host" / "attended-threads.json"
        if ledger_path.exists() or _is_link_like(ledger_path):
            raise ConfigurationError(
                "attended-host migration reported ABSENT while a canonical ledger exists"
            )
        return {"outcome": "ABSENT", "entries": 0}
    if (
        value.get("schema_version") != 1
        or value.get("kind") != ATTENDED_MIGRATION_KIND
        or value.get("status") != "COMPLETE"
        or type(value.get("entries")) is not int
        or int(value["entries"]) < 0
    ):
        raise ConfigurationError(
            "runtime authority requires a completed attended-host migration receipt"
        )
    manifest_path = (
        coordination_dir / "migrations" / "attended-host-v1" / "manifest.json"
    )
    if not manifest_path.is_file() or _is_link_like(manifest_path):
        raise ConfigurationError(
            "completed attended-host migration manifest is unavailable"
        )
    installed = read_json(manifest_path)
    if installed != value:
        raise ConfigurationError(
            "attended-host migration receipt does not match its durable manifest"
        )
    return dict(value)


def _adopt_default_execution_authority(
    repo_root: Path,
    coordination_dir: Path,
    repository_identity: Mapping[str, object],
) -> tuple[Path, Mapping[str, object], str]:
    """Move singleton execution ledgers into the explicit ``default`` namespace."""

    target_sha, plan_fingerprint = _canonical_migration_dispatch_identity(repo_root)
    del target_sha
    control = read_json(repo_root / ".autopilot" / "control-plane.json")
    target = control.get("target") if isinstance(control, Mapping) else None
    target_branch = target.get("branch") if isinstance(target, Mapping) else None
    if not isinstance(target_branch, str) or not target_branch.strip():
        raise ConfigurationError("default execution migration target branch is invalid")
    identity = execution_namespace_identity(
        repository_identity,
        kernel_identity=runtime_kernel_identity(repo_root),
        namespace="default",
        target_branch=target_branch,
        plan_fingerprint=plan_fingerprint,
    )
    execution_dir = initialize_execution_namespace(coordination_dir, identity)
    manifest_path = execution_dir / "migrations" / "singleton-default-adoption.json"
    # Every singleton execution-authority surface is either adopted byte for
    # byte or represented by an explicit absence proof.  This inventory is
    # deliberately closed: adding a new executable admission surface requires
    # extending migration rather than letting it remain repository-global.
    file_candidates = (
        "task-bindings.jsonl",
        "sidecar-bindings.jsonl",
        "dispatcher-release.json",
        "dispatcher-admission.json",
        "dispatcher-generation.json",
        "dispatcher-releases.jsonl",
        "github-snapshot-observation.json",
        "github-state.json",
        "target.json",
        "graph-changes.jsonl",
        "receipt-index.jsonl",
        "releases.jsonl",
        "quarantines.jsonl",
        "recoveries.jsonl",
        "host/attended-threads.json",
    )
    tree_candidates = (
        "github-snapshot-observation-archive",
        "github-snapshot-candidates",
        "host/cards",
        "receipts",
        "failures",
        "blockers",
        "questions",
        "subtask-waves",
        "quarantine",
        "escalations",
        "recoveries",
    )
    archive_root = (
        coordination_dir
        / "runtime-authority-migrations"
        / "default-execution-adoption"
    )
    entries: list[dict[str, object]] = []

    def adopt_file(relative: str) -> None:
        source = coordination_dir / relative
        destination = execution_dir / relative
        archive = archive_root / relative
        for candidate, label in (
            (source, "default execution authority source"),
            (destination, "default execution authority destination"),
            (archive, "default execution authority archive"),
        ):
            if candidate.exists() or _is_link_like(candidate):
                _reject_link_components(candidate, label=label)
                if not candidate.is_file():
                    raise ConfigurationError(f"{label} is not a regular file: {candidate}")
        if source.is_file():
            raw = _read_regular_authority_bytes(
                source, label="default execution authority source"
            )
            exclusive_write_bytes_or_identical(archive, raw)
            exclusive_write_bytes_or_identical(destination, raw)
            if source.read_bytes() != raw or destination.read_bytes() != raw:
                raise ConfigurationError(
                    "default execution authority changed during adoption"
                )
            source.unlink()
            _fsync_parent_directory(source.parent)
        elif destination.is_file():
            raw = destination.read_bytes()
            if not archive.is_file() or archive.read_bytes() != raw:
                raise ConfigurationError(
                    "default execution destination lacks its exact adoption archive"
                )
        elif archive.is_file():
            raise ConfigurationError(
                "default execution adoption archive exists without installed authority"
            )
        else:
            entries.append(
                {
                    "relative_path": relative,
                    "outcome": "ABSENT",
                    "digest": None,
                    "bytes": 0,
                    "archive_path": None,
                }
            )
            return
        entries.append(
            {
                "relative_path": relative,
                "outcome": "ADOPTED",
                "digest": "sha256:" + sha256(raw).hexdigest(),
                "bytes": len(raw),
                "archive_path": str(archive),
            }
        )

    for relative in file_candidates:
        adopt_file(relative)
    for relative_root in tree_candidates:
        source_root = coordination_dir / relative_root
        destination_root = execution_dir / relative_root
        archive_tree_root = archive_root / relative_root
        for candidate, label in (
            (source_root, "default execution authority tree source"),
            (destination_root, "default execution authority tree destination"),
            (archive_tree_root, "default execution authority tree archive"),
        ):
            if candidate.exists() or _is_link_like(candidate):
                _reject_link_components(candidate, label=label)
                if not candidate.is_dir():
                    raise ConfigurationError(f"{label} is not a directory: {candidate}")
        relatives: set[Path] = set()
        for root_candidate in (source_root, destination_root, archive_tree_root):
            if root_candidate.is_dir():
                for item in root_candidate.rglob("*"):
                    if item.is_file() or _is_link_like(item):
                        _reject_link_components(
                            item, label="default execution authority tree member"
                        )
                        if not item.is_file():
                            raise ConfigurationError(
                                "default execution authority tree contains a non-file member"
                            )
                        relatives.add(item.relative_to(root_candidate))
        if not relatives:
            entries.append(
                {
                    "relative_path": relative_root + "/",
                    "outcome": "ABSENT",
                    "digest": None,
                    "bytes": 0,
                    "archive_path": None,
                }
            )
        else:
            for nested in sorted(relatives, key=lambda item: item.as_posix()):
                adopt_file((Path(relative_root) / nested).as_posix())
        if source_root.is_dir():
            directories = sorted(
                (item for item in source_root.rglob("*") if item.is_dir()),
                key=lambda item: len(item.parts),
                reverse=True,
            )
            for directory in directories:
                directory.rmdir()
                _fsync_parent_directory(directory.parent)
            source_root.rmdir()
            _fsync_parent_directory(source_root.parent)
    material: dict[str, object] = {
        "schema_version": 1,
        "kind": "hive-mind-default-execution-adoption-v1",
        "execution_identity": dict(identity),
        "entries": entries,
    }
    manifest = {**material, "record_id": digest_json(material)}
    exclusive_write_json_or_identical(manifest_path, manifest)
    return execution_dir, identity, str(manifest["record_id"])


def _validate_completed_default_execution_adoption(
    coordination_dir: Path,
    ready: Mapping[str, object],
) -> tuple[Path, Mapping[str, object], str]:
    """Authenticate the exact adoption chain without replaying source moves."""

    execution_id = str(ready.get("default_execution_id"))
    execution_dir = execution_namespace_dir(coordination_dir, execution_id)
    if str(execution_dir) != ready.get("default_execution_dir"):
        raise ConfigurationError("READY default execution path is not canonical")
    identity_path = execution_dir / "execution-identity.json"
    identity = read_strict_canonical_json(
        identity_path,
        label="default execution identity",
    )
    if (
        not isinstance(identity, Mapping)
        or identity.get("execution_id") != execution_id
        or identity.get("namespace") != "default"
        or digest_json(identity) != ready.get("default_execution_identity_digest")
    ):
        raise ConfigurationError("READY default execution identity is invalid")
    require_execution_namespace(coordination_dir, identity)
    manifest_path = execution_dir / "migrations" / "singleton-default-adoption.json"
    manifest = read_strict_canonical_json(
        manifest_path,
        label="default execution adoption manifest",
        expected_fields={
            "schema_version",
            "kind",
            "execution_identity",
            "entries",
            "record_id",
        },
    )
    material = dict(manifest)
    manifest_id = material.pop("record_id", None)
    entries = manifest.get("entries") if isinstance(manifest, Mapping) else None
    if (
        manifest.get("schema_version") != 1
        or manifest.get("kind") != "hive-mind-default-execution-adoption-v1"
        or manifest.get("execution_identity") != identity
        or manifest_id != digest_json(material)
        or manifest_id != ready.get("default_execution_adoption_digest")
        or not isinstance(entries, list)
    ):
        raise ConfigurationError("default execution adoption manifest is invalid")
    seen: set[str] = set()
    archive_root = (
        coordination_dir
        / "runtime-authority-migrations"
        / "default-execution-adoption"
    )
    for index, entry in enumerate(entries, 1):
        if (
            not isinstance(entry, Mapping)
            or set(entry)
            != {"relative_path", "outcome", "digest", "bytes", "archive_path"}
            or not isinstance(entry.get("relative_path"), str)
            or str(entry["relative_path"]) in seen
            or entry.get("outcome") not in {"ADOPTED", "ABSENT"}
        ):
            raise ConfigurationError(
                f"default execution adoption entry {index} is malformed"
            )
        relative = str(entry["relative_path"])
        seen.add(relative)
        if relative.startswith(("/", "\\")) or ".." in Path(relative).parts:
            raise ConfigurationError("default execution adoption path escapes authority")
        source = coordination_dir / relative.rstrip("/")
        destination = execution_dir / relative.rstrip("/")
        if source.exists() or _is_link_like(source):
            raise ConfigurationError(
                "retired singleton authority reappeared after default adoption"
            )
        if entry.get("outcome") == "ABSENT":
            if any(
                entry.get(field) is not expected
                for field, expected in {
                    "digest": None,
                    "archive_path": None,
                }.items()
            ) or entry.get("bytes") != 0:
                raise ConfigurationError("default execution absence proof is malformed")
            absent_archive = archive_root / relative.rstrip("/")
            if absent_archive.exists() or _is_link_like(absent_archive):
                raise ConfigurationError(
                    "default execution absence archive was created after the cut"
                )
            # ABSENT authenticates only the migration cut. Normal execution may
            # create the canonical destination later; it must remain a regular,
            # non-linked member of the execution authority.
            if destination.exists() or _is_link_like(destination):
                _reject_link_components(
                    destination, label="post-adoption execution authority"
                )
                expected_directory = relative.endswith("/")
                if expected_directory != destination.is_dir() or (
                    not expected_directory and not destination.is_file()
                ):
                    raise ConfigurationError(
                        "post-adoption execution authority has the wrong type"
                    )
            continue
        archive_path = entry.get("archive_path")
        digest = entry.get("digest")
        byte_count = entry.get("bytes")
        if (
            not isinstance(archive_path, str)
            or not isinstance(digest, str)
            or AUTHORITY_ID.fullmatch(digest) is None
            or type(byte_count) is not int
            or byte_count < 0
        ):
            raise ConfigurationError("default execution adoption evidence is malformed")
        archive = _reject_link_components(
            Path(archive_path), label="default execution adoption archive"
        )
        expected_archive = (archive_root / relative).resolve()
        if (
            not archive.is_absolute()
            or archive.resolve() != expected_archive
            or not archive.resolve().is_relative_to(archive_root.resolve())
        ):
            raise ConfigurationError("default execution adoption archive escapes root")
        archived_raw = _read_regular_authority_bytes(
            archive, label="default execution adoption archive"
        )
        if (
            len(archived_raw) != byte_count
            or "sha256:" + sha256(archived_raw).hexdigest() != digest
        ):
            raise ConfigurationError(
                "default execution adoption archive differs from its receipt"
            )
        current_raw = _read_regular_authority_bytes(
            destination, label="default execution adopted destination"
        )
        if relative.endswith(".jsonl"):
            if not current_raw.startswith(archived_raw):
                raise ConfigurationError(
                    "adopted append-only authority lost its archived prefix"
                )
            records = strict_jsonl_records(
                destination, label="adopted append-only execution authority"
            )
            previous_event_id: object = None
            for record_index, record in enumerate(records, 1):
                if not isinstance(record.get("schema_version"), int):
                    raise ConfigurationError(
                        "adopted append-only execution authority lacks a schema version"
                    )
                if "event_id" in record or "previous_event_id" in record:
                    material_record = dict(record)
                    event_id = material_record.pop("event_id", None)
                    if (
                        AUTHORITY_ID.fullmatch(str(event_id)) is None
                        or record.get("previous_event_id") != previous_event_id
                        or event_id != digest_json(material_record)
                    ):
                        raise ConfigurationError(
                            "adopted append-only execution authority has an invalid chain "
                            f"at line {record_index}"
                        )
                    previous_event_id = event_id
        elif relative in {
            "dispatcher-release.json",
            "dispatcher-admission.json",
            "github-snapshot-observation.json",
            "github-state.json",
            "target.json",
            "host/attended-threads.json",
        }:
            current = read_strict_canonical_json(
                destination,
                label=f"current adopted {relative}",
            )
            if not isinstance(current, Mapping):
                raise ConfigurationError(
                    f"current adopted {relative} must be an object"
                )
            if relative == "target.json":
                if set(current) != {
                    "schema_version",
                    "target_sha",
                    "actor",
                    "reason",
                    "changed_paths",
                    "timestamp",
                    "plan_fingerprint",
                } or (
                    current.get("schema_version") != 1
                    or FULL_SHA.fullmatch(str(current.get("target_sha"))) is None
                    or current.get("plan_fingerprint")
                    != identity.get("plan_fingerprint")
                    or not isinstance(current.get("changed_paths"), list)
                ):
                    raise ConfigurationError(
                        "current adopted target authority is invalid"
                    )
            elif relative == "github-state.json":
                if set(current) != {"target_sha", "pull_requests", "branches"} or (
                    FULL_SHA.fullmatch(str(current.get("target_sha"))) is None
                    or not isinstance(current.get("pull_requests"), list)
                    or not isinstance(current.get("branches"), list)
                ):
                    raise ConfigurationError(
                        "current adopted GitHub state is invalid"
                    )
            elif relative == "dispatcher-release.json":
                release_fields = {
                    "schema_version",
                    "kind",
                    "actor",
                    "execution_namespace",
                    "execution_id",
                    "repository",
                    "target_branch",
                    "target_sha",
                    "plan_fingerprint",
                    "reconciliation_digest",
                    "github_snapshot_digest",
                    "snapshot_observation_id",
                    "snapshot_observation_epoch",
                    "snapshot_observation_record_id",
                    "host_id",
                    "capacity_generation",
                    "capacity_epoch",
                    "capacity_record_id",
                    "capacity_max_total_sessions",
                    "capacity_validation_slots",
                    "session_cap",
                    "admission_epoch",
                    "supersedes_release_id",
                    "released_wave",
                    "directive",
                    "action",
                    "verdicts",
                    "issued_at",
                    "receipt_retirement_execution_digest",
                    "primary_host_reservations",
                    "release_admission_id",
                    "release_id",
                }
                material_current = dict(current)
                release_id = material_current.pop("release_id", None)
                if (
                    set(current) != release_fields
                    or current.get("schema_version") != 1
                    or current.get("kind")
                    != "hive-mind-autopilot-dispatch-release-v1"
                    or current.get("execution_namespace") != "default"
                    or current.get("execution_id") != execution_id
                    or current.get("repository") != identity.get("repository")
                    or current.get("target_branch") != identity.get("target_branch")
                    or current.get("plan_fingerprint")
                    != identity.get("plan_fingerprint")
                    or release_id != digest_json(material_current)
                ):
                    raise ConfigurationError(
                        "current adopted dispatcher release is invalid"
                    )
            elif relative == "dispatcher-admission.json":
                common_fields = {
                    "schema_version",
                    "kind",
                    "status",
                    "execution_namespace",
                    "execution_id",
                    "admission_epoch",
                    "release_id",
                    "repository",
                    "target_branch",
                    "target_sha",
                    "plan_fingerprint",
                    "github_snapshot_digest",
                    "reconciliation_digest",
                    "snapshot_observation_id",
                    "snapshot_observation_epoch",
                    "snapshot_observation_record_id",
                    "host_id",
                    "capacity_generation",
                    "capacity_epoch",
                    "capacity_record_id",
                    "session_cap",
                    "generation_id",
                    "recorded_at",
                }
                if current.get("status") == "INVALIDATED":
                    common_fields |= {"actor", "reason", "observed_target_sha"}
                generation_material = dict(current)
                generation_id = generation_material.pop("generation_id", None)
                if (
                    set(current) != common_fields
                    or current.get("schema_version") != 1
                    or current.get("kind")
                    != "hive-mind-shared-dispatch-admission-v1"
                    or current.get("status") not in {"ACTIVE", "INVALIDATED"}
                    or current.get("execution_namespace") != "default"
                    or current.get("execution_id") != execution_id
                    or current.get("repository") != identity.get("repository")
                    or current.get("target_branch") != identity.get("target_branch")
                    or current.get("plan_fingerprint")
                    != identity.get("plan_fingerprint")
                    or generation_id != digest_json(generation_material)
                ):
                    raise ConfigurationError(
                        "current adopted dispatcher generation is invalid"
                    )
            elif relative == "github-snapshot-observation.json":
                observation_fields = {
                    "schema_version",
                    "kind",
                    "status",
                    "execution_namespace",
                    "execution_id",
                    "observation_epoch",
                    "observation_id",
                    "fetch_ref",
                    "branch_fetches",
                    "repository",
                    "target_branch",
                    "base_target_sha",
                    "target_sha",
                    "plan_fingerprint",
                    "snapshot_digest",
                    "candidate_artifact",
                    "supersedes_observation_id",
                    "actor",
                    "began_at",
                    "expires_at",
                    "installed_at",
                    "record_id",
                }
                observation_material = dict(current)
                observation_record_id = observation_material.pop("record_id", None)
                if (
                    set(current) != observation_fields
                    or current.get("schema_version") != 2
                    or current.get("kind")
                    != "hive-mind-github-snapshot-observation-v2"
                    or current.get("execution_namespace") != "default"
                    or current.get("execution_id") != execution_id
                    or current.get("repository") != identity.get("repository")
                    or current.get("target_branch") != identity.get("target_branch")
                    or current.get("plan_fingerprint")
                    != identity.get("plan_fingerprint")
                    or observation_record_id != digest_json(observation_material)
                ):
                    raise ConfigurationError(
                        "current adopted GitHub snapshot observation is invalid"
                    )
            else:
                # The attended-host adapter owns the exact entry/card schema.
                # READY authenticates only its canonical execution path and
                # strict JSON bytes; adapter startup performs the live reducer.
                pass
        elif current_raw != archived_raw:
            # Immutable adopted files (receipts, cards, recovery packets and
            # legacy evidence) remain byte-identical to their exact archive.
            raise ConfigurationError(
                "immutable adopted execution authority differs from its archive"
            )
    return execution_dir, dict(identity), str(manifest_id)


def validate_repository_runtime_ready_chain(
    repo_root: str | Path,
    coordination_dir: str | Path,
) -> Mapping[str, object]:
    """Authenticate a completed migration chain without replaying any move."""

    root, directory, expected, bootstrap = _completed_bootstrap_manifest(
        repo_root, coordination_dir
    )
    ready = _require_repository_runtime_ready(directory, expected)
    if ready.get("bootstrap_migration_id") != bootstrap.get("migration_id"):
        raise ConfigurationError("READY bootstrap migration lineage is invalid")
    attended_manifest = (
        directory / "migrations" / "attended-host-v1" / "manifest.json"
    )
    attended_value: Mapping[str, object]
    if attended_manifest.is_file():
        value = read_strict_canonical_json(
            attended_manifest, label="attended-host migration manifest"
        )
        if not isinstance(value, Mapping):
            raise ConfigurationError("attended-host migration manifest is malformed")
        attended_value = dict(value)
    elif not attended_manifest.exists() and not _is_link_like(attended_manifest):
        attended_value = {"outcome": "ABSENT", "entries": 0}
    else:
        raise ConfigurationError("attended-host migration manifest is not regular")
    attended = _validated_attended_migration_receipt(directory, attended_value)
    if ready.get("attended_migration_digest") != digest_json(attended):
        raise ConfigurationError("READY attended migration lineage is invalid")
    execution_dir, execution_identity, adoption_digest = (
        _validate_completed_default_execution_adoption(directory, ready)
    )
    current_kernel = runtime_kernel_identity(root)
    if (
        execution_identity.get("kernel_bundle_digest")
        != current_kernel.get("bundle_digest")
        or execution_identity.get("interpreter_policy_digest")
        != current_kernel.get("interpreter_policy_digest")
    ):
        raise ConfigurationError(
            "READY execution kernel differs from this checkout or interpreter; "
            "explicit zero-activity upgrade is required"
        )
    target_watermark = _read_repository_target_watermark_unlocked(
        directory,
        repository_identity=expected,
        target_branch=str(execution_identity["target_branch"]),
    )
    target_history = _repository_target_watermark_events_unlocked(
        directory,
        repository_identity=expected,
        target_branch=str(execution_identity["target_branch"]),
    )
    if (
        not target_history
        or ready.get("repository_target_watermark_record_id")
        != target_history[0].get("record_id")
        or ready.get("kernel_bundle_digest")
        != execution_identity.get("kernel_bundle_digest")
        or ready.get("interpreter_policy_digest")
        != execution_identity.get("interpreter_policy_digest")
    ):
        raise ConfigurationError("READY repository target watermark lineage is invalid")
    return {
        "schema_version": 1,
        "kind": "hive-mind-runtime-ready-chain-v1",
        "runtime_identity": dict(expected),
        "bootstrap_authority": dict(bootstrap),
        "attended_host": dict(attended),
        "ready": dict(ready),
        "execution_dir": str(execution_dir),
        "execution_identity": dict(execution_identity),
        "default_execution_adoption_digest": adoption_digest,
        "repository_target_watermark": dict(target_watermark),
    }


def initialize_repository_runtime_authority(
    repo_root: str | Path,
    coordination_dir: str | Path,
    *,
    attended_migration: Mapping[str, object],
) -> Mapping[str, object]:
    """Publish runtime readiness only after every legacy authority migration."""

    root, directory, expected, bootstrap = _completed_bootstrap_manifest(
        repo_root,
        coordination_dir,
    )
    bootstrap_lock = directory / RUNTIME_BOOTSTRAP_LOCK
    if not runtime_file_lock_is_held(bootstrap_lock):
        raise ConfigurationError(
            "runtime authority publication requires the bootstrap migration lock"
        )
    attended_lock = directory / "locks" / "attended-host.lock"
    if not runtime_file_lock_is_held(attended_lock):
        raise ConfigurationError(
            "runtime authority publication requires the attended-host migration lock"
        )
    arbiter_lock = directory / "arbiter" / "locks" / "arbiter-authority.lock"
    if not runtime_file_lock_is_held(arbiter_lock):
        raise ConfigurationError(
            "runtime authority publication requires outer repository arbiter authority"
        )
    identity_path = directory / "runtime-identity.json"
    identity = read_json(identity_path) if identity_path.is_file() else None
    if identity != expected:
        raise ConfigurationError(
            "runtime authority must be staged before readiness publication"
        )
    ready_path = directory / RUNTIME_READY_MANIFEST
    if ready_path.exists() or _is_link_like(ready_path):
        ready = _require_repository_runtime_ready(directory, expected)
        if ready.get("bootstrap_migration_id") != bootstrap.get("migration_id"):
            raise ConfigurationError("READY bootstrap migration lineage is invalid")
        attended = _validated_attended_migration_receipt(
            directory, attended_migration
        )
        if ready.get("attended_migration_digest") != digest_json(attended):
            raise ConfigurationError("READY attended migration lineage is invalid")
        _, installed_execution, _ = _validate_completed_default_execution_adoption(
            directory, ready
        )
        current_kernel = runtime_kernel_identity(root)
        if (
            installed_execution.get("kernel_bundle_digest")
            != current_kernel.get("bundle_digest")
            or installed_execution.get("interpreter_policy_digest")
            != current_kernel.get("interpreter_policy_digest")
        ):
            raise ConfigurationError(
                "runtime READY kernel differs from this checkout or interpreter"
            )
        target_watermark = _read_repository_target_watermark_unlocked(
            directory,
            repository_identity=expected,
            target_branch=str(installed_execution["target_branch"]),
        )
        target_history = _repository_target_watermark_events_unlocked(
            directory,
            repository_identity=expected,
            target_branch=str(installed_execution["target_branch"]),
        )
        if (
            ready.get("repository_target_watermark_record_id")
            != target_history[0].get("record_id")
            or int(target_watermark["target_generation"]) < 1
            or ready.get("kernel_bundle_digest")
            != installed_execution.get("kernel_bundle_digest")
            or ready.get("interpreter_policy_digest")
            != installed_execution.get("interpreter_policy_digest")
        ):
            raise ConfigurationError(
                "READY repository target watermark lineage is invalid"
            )
        return dict(expected)
    for lock_name in STANDARD_RUNTIME_LOCKS:
        lock_path = directory / "locks" / lock_name
        if not lock_path.is_file() or _is_link_like(lock_path):
            raise ConfigurationError(
                f"runtime authority staged lock is unavailable: {lock_name}"
            )
    for lock_name in ARBITER_LOCKS:
        lock_path = directory / "arbiter" / "locks" / lock_name
        if not lock_path.is_file() or _is_link_like(lock_path):
            raise ConfigurationError(
                f"global arbiter staged lock is unavailable: {lock_name}"
            )
    claims_dir = directory / "claims"
    if claims_dir.exists() or _is_link_like(claims_dir):
        _reject_link_components(claims_dir, label="canonical claims directory")
        if not claims_dir.is_dir():
            raise ConfigurationError("canonical claims authority is not a directory")
        claim_paths = sorted(claims_dir.glob("*.json"))
        unexpected_claim_paths = sorted(
            path for path in claims_dir.iterdir() if path.is_file() and path.suffix != ".json"
        )
        if unexpected_claim_paths:
            raise ConfigurationError(
                "canonical claim authority is unclassified before READY: "
                + ", ".join(str(path) for path in unexpected_claim_paths)
            )
        for claim_path in claim_paths:
            raw = _read_regular_authority_bytes(
                claim_path, label="canonical claim authority"
            )
            _strict_authority_object(
                claim_path,
                raw,
                kind="claim",
                schemas=_LEGACY_CLAIM_SCHEMAS,
            )
        if claim_paths:
            raise ConfigurationError(
                "canonical claim authority must be explicitly reconciled before READY"
            )
    lease_path = directory / "global-validation-lease.json"
    if lease_path.exists() or _is_link_like(lease_path):
        raw = _read_regular_authority_bytes(
            lease_path, label="canonical validation lease"
        )
        _strict_authority_object(
            lease_path,
            raw,
            kind="validation-lease",
            schemas=_LEGACY_LEASE_SCHEMAS,
        )
        raise ConfigurationError(
            "canonical validation lease must be explicitly reconciled before READY"
        )
    attended = _validated_attended_migration_receipt(directory, attended_migration)
    execution_dir, execution_identity, adoption_digest = (
        _adopt_default_execution_authority(root, directory, expected)
    )
    initial_target_sha, _ = _canonical_migration_dispatch_identity(root)
    target_watermark = _initialize_repository_target_watermark(
        directory,
        repository_identity=expected,
        target_branch=str(execution_identity["target_branch"]),
        target_sha=initial_target_sha,
        source_execution_id=str(execution_identity["execution_id"]),
        source_observation=None,
        actor="runtime-authority-migration",
        recorded_at=format_time(utc_now()),
    )
    ready_material: dict[str, object] = {
        "schema_version": 1,
        "kind": RUNTIME_READY_KIND,
        "status": "COMPLETE",
        "repository_identity": dict(expected),
        "bootstrap_migration_id": bootstrap["migration_id"],
        "attended_migration_digest": digest_json(attended),
        "default_execution_id": execution_identity["execution_id"],
        "default_execution_identity_digest": digest_json(execution_identity),
        "default_execution_adoption_digest": adoption_digest,
        "default_execution_dir": str(execution_dir),
        "repository_target_watermark_record_id": target_watermark["record_id"],
        "kernel_bundle_digest": execution_identity["kernel_bundle_digest"],
        "interpreter_policy_digest": execution_identity[
            "interpreter_policy_digest"
        ],
    }
    ready = {**ready_material, "record_id": digest_json(ready_material)}
    exclusive_write_json_or_identical(directory / RUNTIME_READY_MANIFEST, ready)
    if identity != expected:
        raise ConfigurationError("runtime authority readiness publication failed")
    return identity


def append_jsonl(path: Path, value: Mapping[str, object]) -> None:
    _append_canonical_jsonl(path, value)


def strict_jsonl_records(
    path: Path,
    *,
    label: str,
) -> tuple[Mapping[str, Any], ...]:
    """Read a complete canonical JSONL ledger; never skip authority bytes."""

    if not path.exists() and not _is_link_like(path):
        return ()
    _reject_link_components(path, label=label)
    if not path.is_file():
        raise ConfigurationError(f"{label} is not a regular file")
    try:
        raw = _read_regular_authority_bytes(path, label=label)
    except (OSError, ConfigurationError) as error:
        raise ConfigurationError(f"{label} is unreadable: {error}") from error
    return _strict_jsonl_records_bytes(raw, label=label)


def _strict_jsonl_records_bytes(
    raw: bytes,
    *,
    label: str,
) -> tuple[Mapping[str, Any], ...]:
    """Validate already authenticated JSONL bytes without touching a path."""

    try:
        text = raw.decode("utf-8")
    except UnicodeError as error:
        raise ConfigurationError(f"{label} is not UTF-8: {error}") from error
    if raw and not raw.endswith(b"\n"):
        raise ConfigurationError(
            f"{label} has a torn final append; explicit recovery is required"
        )
    records: list[Mapping[str, Any]] = []
    for index, line in enumerate(text.splitlines(), 1):
        if not line:
            raise ConfigurationError(f"{label} line {index} is empty")
        try:
            value = json.loads(
                line,
                object_pairs_hook=_strict_json_pairs,
                parse_constant=_reject_json_constant,
            )
        except (json.JSONDecodeError, ValueError) as error:
            raise ConfigurationError(
                f"{label} line {index} is malformed: {error}"
            ) from error
        if not isinstance(value, Mapping):
            raise ConfigurationError(f"{label} line {index} is not an object")
        canonical = json.dumps(
            value, ensure_ascii=False, sort_keys=True, allow_nan=False
        )
        if line != canonical:
            raise ConfigurationError(f"{label} line {index} is noncanonical")
        records.append(value)
    return tuple(records)


def _validate_repository_target_watermark(
    value: Mapping[str, object],
    *,
    repository_identity: Mapping[str, object],
    target_branch: str,
) -> Mapping[str, object]:
    if set(value) != REPOSITORY_TARGET_WATERMARK_FIELDS:
        raise ConfigurationError("repository target watermark schema is ambiguous")
    material = dict(value)
    record_id = material.pop("record_id", None)
    source_kind = value.get("source_kind")
    source_execution_id = value.get("source_execution_id")
    source_release_id = value.get("source_release_id")
    publication_transaction_id = value.get("publication_transaction_id")
    source_observation_id = value.get("source_observation_id")
    if source_kind == "INITIAL_MIGRATION":
        source_valid = (
            isinstance(source_execution_id, str)
            and AUTHORITY_ID.fullmatch(source_execution_id) is not None
            and source_release_id is None
            and publication_transaction_id is None
            and source_observation_id is None
        )
    elif source_kind == "INITIAL_REMOTE":
        source_valid = (
            isinstance(source_execution_id, str)
            and AUTHORITY_ID.fullmatch(source_execution_id) is not None
            and source_release_id is None
            and publication_transaction_id is None
            and isinstance(source_observation_id, str)
            and AUTHORITY_ID.fullmatch(source_observation_id) is not None
        )
    elif source_kind == "SNAPSHOT_INSTALL":
        source_valid = (
            isinstance(source_execution_id, str)
            and AUTHORITY_ID.fullmatch(source_execution_id) is not None
            and source_release_id is None
            and publication_transaction_id is None
            and isinstance(source_observation_id, str)
            and AUTHORITY_ID.fullmatch(source_observation_id) is not None
        )
    elif source_kind == "PUBLICATION":
        source_valid = (
            isinstance(source_execution_id, str)
            and AUTHORITY_ID.fullmatch(source_execution_id) is not None
            and isinstance(source_release_id, str)
            and AUTHORITY_ID.fullmatch(source_release_id) is not None
            and isinstance(publication_transaction_id, str)
            and AUTHORITY_ID.fullmatch(publication_transaction_id) is not None
            and isinstance(source_observation_id, str)
            and AUTHORITY_ID.fullmatch(source_observation_id) is not None
        )
    elif source_kind == "SUPERSEDED_PUBLICATION":
        source_valid = (
            isinstance(source_execution_id, str)
            and AUTHORITY_ID.fullmatch(source_execution_id) is not None
            and isinstance(source_release_id, str)
            and AUTHORITY_ID.fullmatch(source_release_id) is not None
            and isinstance(publication_transaction_id, str)
            and AUTHORITY_ID.fullmatch(publication_transaction_id) is not None
            and isinstance(source_observation_id, str)
            and AUTHORITY_ID.fullmatch(source_observation_id) is not None
        )
    else:
        source_valid = False
    previous = value.get("previous_record_id")
    try:
        parse_time(value.get("recorded_at"))
    except (TypeError, ValueError) as error:
        raise ConfigurationError(
            "repository target watermark timestamp is invalid"
        ) from error
    if (
        value.get("schema_version") != 1
        or value.get("kind") != REPOSITORY_TARGET_WATERMARK_KIND
        or value.get("repository") != repository_identity.get("repository")
        or value.get("repository_transport_digest")
        != repository_identity.get("transport_digest")
        or value.get("target_branch") != target_branch
        or type(value.get("target_generation")) is not int
        or int(value["target_generation"]) < 1
        or FULL_SHA.fullmatch(str(value.get("target_sha"))) is None
        or (
            previous is not None
            and (
                not isinstance(previous, str)
                or AUTHORITY_ID.fullmatch(previous) is None
            )
        )
        or not source_valid
        or not isinstance(value.get("actor"), str)
        or not str(value["actor"]).strip()
        or record_id != digest_json(material)
    ):
        raise ConfigurationError("repository target watermark is invalid")
    return dict(value)


def repository_target_resource_key(
    repository_identity: Mapping[str, object],
    target_branch: str,
) -> str:
    """Return the repository-arbiter key for one mutable target ref.

    A repository may host independent executions against different target
    branches.  The authority is therefore keyed by the sealed Git transport
    and the exact mutable ref, rather than by one repository-wide singleton.
    """

    repository = repository_identity.get("repository")
    transport_digest = repository_identity.get("transport_digest")
    if not isinstance(repository, str) or not repository.strip():
        raise ConfigurationError("target resource repository identity is invalid")
    if (
        not isinstance(transport_digest, str)
        or AUTHORITY_ID.fullmatch(transport_digest) is None
    ):
        raise ConfigurationError("target resource transport identity is invalid")
    if (
        not isinstance(target_branch, str)
        or not target_branch
        or target_branch != target_branch.strip()
    ):
        raise ConfigurationError("target resource branch is invalid")
    checked = subprocess.run(
        ("git", "check-ref-format", "--branch", target_branch),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if checked.returncode != 0 or checked.stdout.strip() != target_branch:
        raise ConfigurationError("target resource branch is noncanonical")
    return digest_json(
        {
            "kind": "hive-mind-target-resource-key-v1",
            "repository": repository,
            "repository_transport_digest": transport_digest,
            "mutable_ref": f"refs/heads/{target_branch}",
        }
    )


def _repository_target_watermark_paths(
    coordination_dir: Path,
    *,
    repository_identity: Mapping[str, object],
    target_branch: str,
) -> tuple[Path, Path]:
    target_key = repository_target_resource_key(
        repository_identity, target_branch
    ).removeprefix("sha256:")
    directory = coordination_dir / "arbiter" / "target-watermarks" / target_key
    return directory / "current.json", directory / "history.jsonl"


def _validate_initial_remote_target_observation(
    value: Mapping[str, object],
    *,
    repository_identity: Mapping[str, object],
    target_branch: str,
    target_sha: str,
    execution_id: str,
) -> Mapping[str, object]:
    if set(value) != INITIAL_REMOTE_TARGET_OBSERVATION_FIELDS:
        raise ConfigurationError("initial remote target observation schema is ambiguous")
    material = dict(value)
    record_id = material.pop("record_id", None)
    try:
        parse_time(value.get("observed_at"))
    except (TypeError, ValueError) as error:
        raise ConfigurationError(
            "initial remote target observation time is invalid"
        ) from error
    expected_execution_id = digest_json(
        {
            "kind": EXECUTION_NAMESPACE_KEY_KIND,
            "repository": repository_identity.get("repository"),
            "repository_transport_digest": repository_identity.get(
                "transport_digest"
            ),
            "namespace": value.get("execution_namespace"),
        }
    )
    if (
        value.get("schema_version") != 1
        or value.get("kind") != INITIAL_REMOTE_TARGET_OBSERVATION_KIND
        or value.get("repository") != repository_identity.get("repository")
        or value.get("repository_transport_digest")
        != repository_identity.get("transport_digest")
        or value.get("target_ref") != f"refs/heads/{target_branch}"
        or value.get("target_sha") != target_sha
        or value.get("execution_id") != execution_id
        or value.get("execution_id") != expected_execution_id
        or AUTHORITY_ID.fullmatch(str(value.get("execution_id"))) is None
        or EXECUTION_NAMESPACE.fullmatch(
            str(value.get("execution_namespace"))
        )
        is None
        or AUTHORITY_ID.fullmatch(str(value.get("transport_record_id"))) is None
        or record_id != digest_json(material)
    ):
        raise ConfigurationError("initial remote target observation is invalid")
    return dict(value)


def _initial_remote_target_observation_path(
    coordination_dir: Path,
    *,
    repository_identity: Mapping[str, object],
    target_branch: str,
    observation_id: str,
) -> Path:
    if AUTHORITY_ID.fullmatch(observation_id) is None:
        raise ConfigurationError("initial remote target observation id is invalid")
    current_path, _history_path = _repository_target_watermark_paths(
        coordination_dir,
        repository_identity=repository_identity,
        target_branch=target_branch,
    )
    return (
        current_path.parent
        / "initial-observations"
        / (observation_id.removeprefix("sha256:") + ".json")
    )


def _read_initial_remote_target_observation_unlocked(
    coordination_dir: Path,
    *,
    repository_identity: Mapping[str, object],
    target_branch: str,
    watermark: Mapping[str, object],
) -> Mapping[str, object]:
    observation_id = str(watermark.get("source_observation_id"))
    path = _initial_remote_target_observation_path(
        coordination_dir,
        repository_identity=repository_identity,
        target_branch=target_branch,
        observation_id=observation_id,
    )
    value = read_strict_canonical_json(
        path,
        label="initial remote target observation",
        expected_fields=INITIAL_REMOTE_TARGET_OBSERVATION_FIELDS,
    )
    if not isinstance(value, Mapping):
        raise ConfigurationError("initial remote target observation is not an object")
    validated = _validate_initial_remote_target_observation(
        value,
        repository_identity=repository_identity,
        target_branch=target_branch,
        target_sha=str(watermark["target_sha"]),
        execution_id=str(watermark["source_execution_id"]),
    )
    if validated.get("record_id") != observation_id:
        raise ConfigurationError(
            "initial remote target observation does not match watermark lineage"
        )
    transport_path = (
        coordination_dir / "arbiter" / "canonical-remote-transport.json"
    )
    transport_fields = {
        "schema_version",
        "kind",
        "repository",
        "remote_name",
        "fetch_url",
        "push_url",
        "record_id",
    }
    transport = read_strict_canonical_json(
        transport_path,
        label="canonical remote transport authority",
        expected_fields=transport_fields,
    )
    if not isinstance(transport, Mapping):
        raise ConfigurationError("canonical remote transport authority is malformed")
    transport_material = dict(transport)
    transport_record_id = transport_material.pop("record_id", None)
    if (
        transport.get("schema_version") != 1
        or transport.get("kind")
        != "hive-mind-canonical-remote-transport-v1"
        or transport.get("repository") != repository_identity.get("repository")
        or transport.get("remote_name") != "origin"
        or transport.get("fetch_url")
        != repository_identity.get("canonical_remote_fetch")
        or transport.get("push_url")
        != repository_identity.get("canonical_remote_push")
        or transport_record_id != digest_json(transport_material)
        or validated.get("transport_record_id") != transport_record_id
    ):
        raise ConfigurationError(
            "initial remote target observation transport provenance is invalid"
        )
    return validated


def publication_observation_evidence_ref(
    execution_id: str,
    publication_transaction_id: str,
    observation_key: str,
) -> str:
    """Derive one short, opaque, execution-bound GitHub-compatible evidence ref."""

    for value in (execution_id, publication_transaction_id, observation_key):
        if AUTHORITY_ID.fullmatch(value) is None:
            raise ConfigurationError("publication observation ref authority is invalid")
    reference_id = digest_json(
        {
            "kind": "hive-mind-publication-observation-evidence-ref-v1",
            "execution_id": execution_id,
            "publication_transaction_id": publication_transaction_id,
            "observation_key": observation_key,
        }
    )
    return "refs/heads/hme/p/" + reference_id.removeprefix("sha256:")


def _validate_superseded_publication_target_observation(
    value: Mapping[str, object],
    *,
    repository_identity: Mapping[str, object],
    target_branch: str,
    expected_target_sha: str,
    target_sha: str,
    execution_id: str,
    source_release_id: str,
    publication_transaction_id: str,
) -> Mapping[str, object]:
    """Validate the portable evidence for an overtaken publication.

    The snapshot adapter proves Git ancestry and creates the immutable evidence
    refs before this authority transition.  The arbiter seals their exact
    identities and bytes so a later replay never depends on that adapter's
    checkout-local state.
    """

    if set(value) != SUPERSEDED_PUBLICATION_TARGET_OBSERVATION_FIELDS:
        raise ConfigurationError(
            "superseded publication target observation schema is ambiguous"
        )
    material = dict(value)
    record_id = material.pop("record_id", None)
    receipt_heads = value.get("receipt_heads")
    if not isinstance(receipt_heads, list) or not receipt_heads:
        raise ConfigurationError(
            "superseded publication target observation receipts are invalid"
        )
    for receipt in receipt_heads:
        if not isinstance(receipt, Mapping) or set(receipt) != (
            SUPERSEDED_PUBLICATION_RECEIPT_HEAD_FIELDS
        ):
            raise ConfigurationError(
                "superseded publication receipt head schema is ambiguous"
            )
        if (
            not isinstance(receipt.get("node_id"), str)
            or not str(receipt["node_id"]).strip()
            or not isinstance(receipt.get("branch"), str)
            or not str(receipt["branch"]).strip()
            or FULL_SHA.fullmatch(str(receipt.get("expected_sha"))) is None
            or FULL_SHA.fullmatch(str(receipt.get("observed_sha"))) is None
        ):
            raise ConfigurationError(
                "superseded publication receipt head is invalid"
            )
    namespace = value.get("execution_namespace")
    expected_execution_id = digest_json(
        {
            "kind": EXECUTION_NAMESPACE_KEY_KIND,
            "repository": repository_identity.get("repository"),
            "repository_transport_digest": repository_identity.get(
                "transport_digest"
            ),
            "namespace": namespace,
        }
    )
    observation_key = digest_json(
        {
            "kind": "hive-mind-superseded-publication-observation-ref-key-v1",
            "execution_id": execution_id,
            "publication_transaction_id": publication_transaction_id,
            "expected_target_sha": expected_target_sha,
            "observed_target_sha": target_sha,
            "receipt_heads": [dict(item) for item in receipt_heads],
            "observed_at": value.get("observed_at"),
        }
    )
    expected_observation_ref = publication_observation_evidence_ref(
        execution_id,
        publication_transaction_id,
        observation_key,
    )
    try:
        parse_time(value.get("observed_at"))
    except (TypeError, ValueError) as error:
        raise ConfigurationError(
            "superseded publication target observation time is invalid"
        ) from error
    if (
        value.get("schema_version") != 1
        or value.get("kind")
        != SUPERSEDED_PUBLICATION_TARGET_OBSERVATION_KIND
        or value.get("repository") != repository_identity.get("repository")
        or value.get("repository_transport_digest")
        != repository_identity.get("transport_digest")
        or value.get("target_ref") != f"refs/heads/{target_branch}"
        or value.get("expected_target_sha") != expected_target_sha
        or value.get("observed_target_sha") != target_sha
        or FULL_SHA.fullmatch(str(value.get("pinned_sha"))) is None
        or value.get("observation_ref_sha") != target_sha
        or value.get("observed_transaction_sha") != value.get("pinned_sha")
        or value.get("observation_ref") != expected_observation_ref
        or not isinstance(value.get("transaction_ref"), str)
        or not str(value["transaction_ref"]).startswith("refs/")
        or namespace is None
        or EXECUTION_NAMESPACE.fullmatch(str(namespace)) is None
        or value.get("execution_id") != execution_id
        or execution_id != expected_execution_id
        or value.get("release_id") != source_release_id
        or value.get("publication_transaction_id")
        != publication_transaction_id
        or AUTHORITY_ID.fullmatch(source_release_id) is None
        or AUTHORITY_ID.fullmatch(publication_transaction_id) is None
        or record_id != digest_json(material)
    ):
        raise ConfigurationError(
            "superseded publication target observation is invalid"
        )
    return dict(value)


def _superseded_publication_target_observation_path(
    coordination_dir: Path,
    *,
    repository_identity: Mapping[str, object],
    target_branch: str,
    observation_id: str,
) -> Path:
    if AUTHORITY_ID.fullmatch(observation_id) is None:
        raise ConfigurationError(
            "superseded publication target observation id is invalid"
        )
    # Keep immutable observations at a short arbiter-global path.  The sealed
    # record itself binds repository transport and target ref, while the full
    # digest filename prevents cross-target aliasing and avoids MAX_PATH
    # failures in deeply nested Windows worktrees.
    repository_target_resource_key(repository_identity, target_branch)
    return (
        coordination_dir
        / "arbiter"
        / "target-observations"
        / (observation_id.removeprefix("sha256:") + ".json")
    )


def _read_superseded_publication_target_observation_unlocked(
    coordination_dir: Path,
    *,
    repository_identity: Mapping[str, object],
    target_branch: str,
    watermark: Mapping[str, object],
    expected_target_sha: str,
) -> Mapping[str, object]:
    observation_id = str(watermark.get("source_observation_id"))
    path = _superseded_publication_target_observation_path(
        coordination_dir,
        repository_identity=repository_identity,
        target_branch=target_branch,
        observation_id=observation_id,
    )
    value = read_strict_canonical_json(
        path,
        label="superseded publication target observation",
        expected_fields=SUPERSEDED_PUBLICATION_TARGET_OBSERVATION_FIELDS,
    )
    if not isinstance(value, Mapping):
        raise ConfigurationError(
            "superseded publication target observation is not an object"
        )
    validated = _validate_superseded_publication_target_observation(
        value,
        repository_identity=repository_identity,
        target_branch=target_branch,
        expected_target_sha=expected_target_sha,
        target_sha=str(watermark["target_sha"]),
        execution_id=str(watermark["source_execution_id"]),
        source_release_id=str(watermark["source_release_id"]),
        publication_transaction_id=str(
            watermark["publication_transaction_id"]
        ),
    )
    if validated.get("record_id") != observation_id:
        raise ConfigurationError(
            "superseded publication observation does not match watermark lineage"
        )
    return validated


def _target_transition_directory(
    coordination_dir: Path,
    *,
    repository_identity: Mapping[str, object],
    target_branch: str,
) -> Path:
    current_path, _history_path = _repository_target_watermark_paths(
        coordination_dir,
        repository_identity=repository_identity,
        target_branch=target_branch,
    )
    return current_path.parent


def _validate_target_transition_source_record(
    value: Mapping[str, object],
    *,
    source_kind: str,
    repository_identity: Mapping[str, object],
    target_branch: str,
    expected_target_sha: str,
    target_sha: str,
    execution_id: str,
    execution_namespace: str,
    plan_fingerprint: str,
    source_release_id: str | None,
    publication_transaction_id: str | None,
) -> Mapping[str, object]:
    """Validate the exact adapter record retained by a target transition."""

    expected_fields = (
        SNAPSHOT_WATERMARK_SOURCE_FIELDS
        if source_kind == "SNAPSHOT_INSTALL"
        else PUBLICATION_WATERMARK_SOURCE_FIELDS
        if source_kind == "PUBLICATION"
        else None
    )
    if expected_fields is None or set(value) != expected_fields:
        raise ConfigurationError(
            "repository target transition source schema is ambiguous"
        )
    material = dict(value)
    record_id = material.pop("record_id", None)
    if (
        AUTHORITY_ID.fullmatch(str(record_id)) is None
        or record_id != digest_json(material)
        or value.get("execution_id") != execution_id
        or value.get("execution_namespace") != execution_namespace
        or value.get("repository") != repository_identity.get("repository")
        or value.get("target_branch") != target_branch
    ):
        raise ConfigurationError(
            "repository target transition source identity is invalid"
        )
    if source_kind == "SNAPSHOT_INSTALL":
        if (
            value.get("schema_version") != 2
            or value.get("kind") != "hive-mind-github-snapshot-observation-v2"
            or value.get("status") not in {"INSTALLING", "INSTALLED"}
            or value.get("target_sha") != target_sha
            or value.get("plan_fingerprint") != plan_fingerprint
            or AUTHORITY_ID.fullmatch(str(value.get("observation_id"))) is None
            or source_release_id is not None
            or publication_transaction_id is not None
        ):
            raise ConfigurationError(
                "snapshot target transition source is invalid"
            )
    else:
        if (
            value.get("schema_version") != 1
            or value.get("kind") != "hive-mind-publication-transaction-v1"
            or value.get("status") not in {
                "PUBLISHING",
                "PUBLISH_UNKNOWN",
                "PUBLISHED",
            }
            or value.get("expected_target_sha") != expected_target_sha
            or value.get("pinned_sha") != target_sha
            or value.get("release_id") != source_release_id
            or value.get("transaction_id") != publication_transaction_id
            or AUTHORITY_ID.fullmatch(str(source_release_id)) is None
            or AUTHORITY_ID.fullmatch(str(publication_transaction_id)) is None
        ):
            raise ConfigurationError(
                "publication target transition source is invalid"
            )
    return dict(value)


def _read_transition_execution_identity_unlocked(
    coordination_dir: Path,
    *,
    repository_identity: Mapping[str, object],
    execution_id: str,
    execution_namespace: str,
    target_branch: str,
    plan_fingerprint: str,
) -> Mapping[str, object]:
    path = execution_namespace_dir(coordination_dir, execution_id) / (
        "execution-identity.json"
    )
    expected_fields = {
        "schema_version", "kind", "execution_id", "namespace", "repository",
        "repository_transport_digest", "canonical_remote_fetch",
        "canonical_remote_push", "target_branch", "plan_fingerprint",
        "kernel_bundle_digest", "interpreter_policy_digest", "record_id",
    }
    value = read_strict_canonical_json(
        path,
        label="target transition execution identity",
        expected_fields=expected_fields,
    )
    material = dict(value) if isinstance(value, Mapping) else {}
    record_id = material.pop("record_id", None)
    if (
        not isinstance(value, Mapping)
        or value.get("schema_version") != 1
        or value.get("kind") != EXECUTION_IDENTITY_KIND
        or value.get("execution_id") != execution_id
        or value.get("namespace") != execution_namespace
        or value.get("repository") != repository_identity.get("repository")
        or value.get("repository_transport_digest")
        != repository_identity.get("transport_digest")
        or value.get("target_branch") != target_branch
        or value.get("plan_fingerprint") != plan_fingerprint
        or record_id != digest_json(material)
    ):
        raise ConfigurationError(
            "target transition execution identity is invalid"
        )
    return dict(value)


def _target_transition_stable_material(
    *,
    source_kind: str,
    repository_identity: Mapping[str, object],
    target_branch: str,
    previous: Mapping[str, object],
    target_sha: str,
    execution_id: str,
    execution_namespace: str,
    plan_fingerprint: str,
    source_release_id: str | None,
    publication_transaction_id: str | None,
    source_record_id: str,
    source_blob_digest: str,
    source_blob_path: str,
) -> dict[str, object]:
    return {
        "source_kind": source_kind,
        "repository": repository_identity["repository"],
        "repository_transport_digest": repository_identity["transport_digest"],
        "target_ref": f"refs/heads/{target_branch}",
        "previous_target_generation": previous["target_generation"],
        "previous_target_sha": previous["target_sha"],
        "previous_watermark_record_id": previous["record_id"],
        "target_sha": target_sha,
        "execution_namespace": execution_namespace,
        "execution_id": execution_id,
        "plan_fingerprint": plan_fingerprint,
        "source_release_id": source_release_id,
        "publication_transaction_id": publication_transaction_id,
        "source_record_id": source_record_id,
        "source_blob_digest": source_blob_digest,
        "source_blob_path": source_blob_path,
    }


def _install_target_transition_evidence_unlocked(
    coordination_dir: Path,
    *,
    repository_identity: Mapping[str, object],
    target_branch: str,
    previous: Mapping[str, object],
    target_sha: str,
    execution_id: str,
    execution_namespace: str,
    plan_fingerprint: str,
    source_kind: str,
    source_release_id: str | None,
    publication_transaction_id: str | None,
    source_record: Mapping[str, object],
    observed_at: str,
) -> Mapping[str, object]:
    lock = coordination_dir / "arbiter" / "locks" / "arbiter-authority.lock"
    if not runtime_file_lock_is_held(lock):
        raise ConfigurationError(
            "target transition evidence requires arbiter authority"
        )
    _read_transition_execution_identity_unlocked(
        coordination_dir,
        repository_identity=repository_identity,
        execution_id=execution_id,
        execution_namespace=execution_namespace,
        target_branch=target_branch,
        plan_fingerprint=plan_fingerprint,
    )
    source = _validate_target_transition_source_record(
        source_record,
        source_kind=source_kind,
        repository_identity=repository_identity,
        target_branch=target_branch,
        expected_target_sha=str(previous["target_sha"]),
        target_sha=target_sha,
        execution_id=execution_id,
        execution_namespace=execution_namespace,
        plan_fingerprint=plan_fingerprint,
        source_release_id=source_release_id,
        publication_transaction_id=publication_transaction_id,
    )
    source_bytes = (
        json.dumps(
            source,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    source_blob_digest = "sha256:" + sha256(source_bytes).hexdigest()
    directory = _target_transition_directory(
        coordination_dir,
        repository_identity=repository_identity,
        target_branch=target_branch,
    )
    source_path = (
        directory
        / "transition-source-blobs"
        / (source_blob_digest.removeprefix("sha256:") + ".json")
    )
    source_relative = source_path.relative_to(coordination_dir).as_posix()
    stable = _target_transition_stable_material(
        source_kind=source_kind,
        repository_identity=repository_identity,
        target_branch=target_branch,
        previous=previous,
        target_sha=target_sha,
        execution_id=execution_id,
        execution_namespace=execution_namespace,
        plan_fingerprint=plan_fingerprint,
        source_release_id=source_release_id,
        publication_transaction_id=publication_transaction_id,
        source_record_id=str(source["record_id"]),
        source_blob_digest=source_blob_digest,
        source_blob_path=source_relative,
    )
    transition_id = digest_json(
        {"kind": "hive-mind-target-transition-key-v1", **stable}
    )
    evidence_path = (
        directory
        / "transition-evidence"
        / (transition_id.removeprefix("sha256:") + ".json")
    )
    if evidence_path.is_file():
        existing = read_strict_canonical_json(
            evidence_path,
            label="target transition evidence",
            expected_fields=TARGET_WATERMARK_TRANSITION_EVIDENCE_FIELDS,
        )
        return _validate_target_transition_evidence_unlocked(
            coordination_dir,
            existing,
            repository_identity=repository_identity,
            target_branch=target_branch,
            previous=previous,
            watermark_target_sha=target_sha,
            expected_transition_id=transition_id,
        )
    try:
        parse_time(observed_at)
    except (TypeError, ValueError) as error:
        raise ConfigurationError(
            "target transition evidence time is invalid"
        ) from error
    exclusive_write_bytes_or_identical(source_path, source_bytes)
    material: dict[str, object] = {
        "schema_version": 1,
        "kind": TARGET_WATERMARK_TRANSITION_EVIDENCE_KIND,
        "transition_id": transition_id,
        **stable,
        "observed_at": observed_at,
    }
    evidence = {**material, "record_id": digest_json(material)}
    exclusive_write_json_or_identical(evidence_path, evidence)
    return _validate_target_transition_evidence_unlocked(
        coordination_dir,
        evidence,
        repository_identity=repository_identity,
        target_branch=target_branch,
        previous=previous,
        watermark_target_sha=target_sha,
        expected_transition_id=transition_id,
    )


def _validate_target_transition_evidence_unlocked(
    coordination_dir: Path,
    value: object,
    *,
    repository_identity: Mapping[str, object],
    target_branch: str,
    previous: Mapping[str, object],
    watermark_target_sha: str,
    expected_transition_id: str,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != (
        TARGET_WATERMARK_TRANSITION_EVIDENCE_FIELDS
    ):
        raise ConfigurationError("target transition evidence schema is ambiguous")
    material = dict(value)
    record_id = material.pop("record_id", None)
    try:
        parse_time(value.get("observed_at"))
    except (TypeError, ValueError) as error:
        raise ConfigurationError("target transition evidence time is invalid") from error
    stable = {
        field: value[field]
        for field in TARGET_WATERMARK_TRANSITION_EVIDENCE_FIELDS
        if field
        not in {"schema_version", "kind", "transition_id", "observed_at", "record_id"}
    }
    transition_id = digest_json(
        {"kind": "hive-mind-target-transition-key-v1", **stable}
    )
    if (
        value.get("schema_version") != 1
        or value.get("kind") != TARGET_WATERMARK_TRANSITION_EVIDENCE_KIND
        or value.get("transition_id") != transition_id
        or transition_id != expected_transition_id
        or value.get("repository") != repository_identity.get("repository")
        or value.get("repository_transport_digest")
        != repository_identity.get("transport_digest")
        or value.get("target_ref") != f"refs/heads/{target_branch}"
        or value.get("previous_target_generation")
        != previous.get("target_generation")
        or value.get("previous_target_sha") != previous.get("target_sha")
        or value.get("previous_watermark_record_id")
        != previous.get("record_id")
        or value.get("target_sha") != watermark_target_sha
        or AUTHORITY_ID.fullmatch(str(value.get("execution_id"))) is None
        or EXECUTION_NAMESPACE.fullmatch(
            str(value.get("execution_namespace"))
        )
        is None
        or AUTHORITY_ID.fullmatch(str(value.get("plan_fingerprint"))) is None
        or AUTHORITY_ID.fullmatch(str(value.get("source_record_id"))) is None
        or AUTHORITY_ID.fullmatch(str(value.get("source_blob_digest"))) is None
        or record_id != digest_json(material)
    ):
        raise ConfigurationError("target transition evidence is invalid")
    _read_transition_execution_identity_unlocked(
        coordination_dir,
        repository_identity=repository_identity,
        execution_id=str(value["execution_id"]),
        execution_namespace=str(value["execution_namespace"]),
        target_branch=target_branch,
        plan_fingerprint=str(value["plan_fingerprint"]),
    )
    directory = _target_transition_directory(
        coordination_dir,
        repository_identity=repository_identity,
        target_branch=target_branch,
    )
    expected_source_path = (
        directory
        / "transition-source-blobs"
        / (str(value["source_blob_digest"]).removeprefix("sha256:") + ".json")
    )
    if value.get("source_blob_path") != expected_source_path.relative_to(
        coordination_dir
    ).as_posix():
        raise ConfigurationError("target transition source path is invalid")
    source_bytes = _read_regular_authority_bytes(
        expected_source_path,
        label="target transition source blob",
    )
    if "sha256:" + sha256(source_bytes).hexdigest() != value.get(
        "source_blob_digest"
    ):
        raise ConfigurationError("target transition source blob changed")
    source = parse_strict_canonical_json_bytes(
        source_bytes,
        label="target transition source blob",
        expected_fields=(
            set(SNAPSHOT_WATERMARK_SOURCE_FIELDS)
            if value.get("source_kind") == "SNAPSHOT_INSTALL"
            else set(PUBLICATION_WATERMARK_SOURCE_FIELDS)
            if value.get("source_kind") == "PUBLICATION"
            else set()
        ),
    )
    validated_source = _validate_target_transition_source_record(
        source,
        source_kind=str(value["source_kind"]),
        repository_identity=repository_identity,
        target_branch=target_branch,
        expected_target_sha=str(previous["target_sha"]),
        target_sha=watermark_target_sha,
        execution_id=str(value["execution_id"]),
        execution_namespace=str(value["execution_namespace"]),
        plan_fingerprint=str(value["plan_fingerprint"]),
        source_release_id=(
            str(value["source_release_id"])
            if value.get("source_release_id") is not None
            else None
        ),
        publication_transaction_id=(
            str(value["publication_transaction_id"])
            if value.get("publication_transaction_id") is not None
            else None
        ),
    )
    if validated_source.get("record_id") != value.get("source_record_id"):
        raise ConfigurationError(
            "target transition source record differs from retained evidence"
        )
    return dict(value)


def _read_target_transition_evidence_unlocked(
    coordination_dir: Path,
    *,
    repository_identity: Mapping[str, object],
    target_branch: str,
    watermark: Mapping[str, object],
    previous: Mapping[str, object],
) -> Mapping[str, object]:
    transition_id = str(watermark.get("source_observation_id"))
    if AUTHORITY_ID.fullmatch(transition_id) is None:
        raise ConfigurationError("target transition evidence id is invalid")
    directory = _target_transition_directory(
        coordination_dir,
        repository_identity=repository_identity,
        target_branch=target_branch,
    )
    path = (
        directory
        / "transition-evidence"
        / (transition_id.removeprefix("sha256:") + ".json")
    )
    value = read_strict_canonical_json(
        path,
        label="target transition evidence",
        expected_fields=TARGET_WATERMARK_TRANSITION_EVIDENCE_FIELDS,
    )
    validated = _validate_target_transition_evidence_unlocked(
        coordination_dir,
        value,
        repository_identity=repository_identity,
        target_branch=target_branch,
        previous=previous,
        watermark_target_sha=str(watermark["target_sha"]),
        expected_transition_id=transition_id,
    )
    for field, expected in {
        "source_kind": watermark.get("source_kind"),
        "execution_id": watermark.get("source_execution_id"),
        "source_release_id": watermark.get("source_release_id"),
        "publication_transaction_id": watermark.get(
            "publication_transaction_id"
        ),
    }.items():
        if validated.get(field) != expected:
            raise ConfigurationError(
                f"target transition evidence has mismatched {field}"
            )
    return validated


def _repository_target_watermark_events_unlocked(
    coordination_dir: Path,
    *,
    repository_identity: Mapping[str, object],
    target_branch: str,
) -> tuple[Mapping[str, object], ...]:
    _current_path, history_path = _repository_target_watermark_paths(
        coordination_dir,
        repository_identity=repository_identity,
        target_branch=target_branch,
    )
    records = strict_jsonl_records(
        history_path,
        label="repository target watermark history",
    )
    validated: list[Mapping[str, object]] = []
    previous: Mapping[str, object] | None = None
    for record in records:
        current = _validate_repository_target_watermark(
            record,
            repository_identity=repository_identity,
            target_branch=target_branch,
        )
        if current.get("source_kind") == "INITIAL_REMOTE":
            _read_initial_remote_target_observation_unlocked(
                coordination_dir,
                repository_identity=repository_identity,
                target_branch=target_branch,
                watermark=current,
            )
        if current.get("source_kind") == "SUPERSEDED_PUBLICATION":
            if previous is None:
                raise ConfigurationError(
                    "superseded publication watermark has no predecessor"
                )
            _read_superseded_publication_target_observation_unlocked(
                coordination_dir,
                repository_identity=repository_identity,
                target_branch=target_branch,
                watermark=current,
                expected_target_sha=str(previous["target_sha"]),
            )
        if current.get("source_kind") in {"SNAPSHOT_INSTALL", "PUBLICATION"}:
            if previous is None:
                raise ConfigurationError(
                    "target transition evidence has no watermark predecessor"
                )
            _read_target_transition_evidence_unlocked(
                coordination_dir,
                repository_identity=repository_identity,
                target_branch=target_branch,
                watermark=current,
                previous=previous,
            )
        if previous is None:
            if (
                current.get("target_generation") != 1
                or current.get("previous_record_id") is not None
                or current.get("source_kind")
                not in {"INITIAL_MIGRATION", "INITIAL_REMOTE"}
            ):
                raise ConfigurationError(
                    "repository target watermark history has no canonical initial event"
                )
        elif (
            current.get("target_generation")
            != int(previous["target_generation"]) + 1
            or current.get("previous_record_id") != previous.get("record_id")
            or current.get("target_sha") == previous.get("target_sha")
        ):
            raise ConfigurationError(
                "repository target watermark history is non-monotonic"
            )
        validated.append(current)
        previous = current
    return tuple(validated)


def _read_repository_target_watermark_current_unlocked(
    coordination_dir: Path,
    *,
    repository_identity: Mapping[str, object],
    target_branch: str,
) -> Mapping[str, object]:
    path, _history_path = _repository_target_watermark_paths(
        coordination_dir,
        repository_identity=repository_identity,
        target_branch=target_branch,
    )
    value = read_strict_canonical_json(
        path,
        label="repository target watermark",
        expected_fields=REPOSITORY_TARGET_WATERMARK_FIELDS,
    )
    if not isinstance(value, Mapping):
        raise ConfigurationError("repository target watermark is not an object")
    return _validate_repository_target_watermark(
        value,
        repository_identity=repository_identity,
        target_branch=target_branch,
    )


def _read_repository_target_watermark_unlocked(
    coordination_dir: Path,
    *,
    repository_identity: Mapping[str, object],
    target_branch: str,
) -> Mapping[str, object]:
    current = _read_repository_target_watermark_current_unlocked(
        coordination_dir,
        repository_identity=repository_identity,
        target_branch=target_branch,
    )
    history = _repository_target_watermark_events_unlocked(
        coordination_dir,
        repository_identity=repository_identity,
        target_branch=target_branch,
    )
    if not history or history[-1] != current:
        raise ConfigurationError(
            "repository target watermark current record diverges from history"
        )
    return current


def _target_watermark_candidate(
    *,
    repository_identity: Mapping[str, object],
    target_branch: str,
    target_generation: int,
    target_sha: str,
    previous_record_id: str | None,
    source_kind: str,
    source_execution_id: str,
    source_release_id: str | None,
    publication_transaction_id: str | None,
    source_observation_id: str | None,
    actor: str,
    recorded_at: str,
) -> Mapping[str, object]:
    material: dict[str, object] = {
        "schema_version": 1,
        "kind": REPOSITORY_TARGET_WATERMARK_KIND,
        "repository": repository_identity["repository"],
        "repository_transport_digest": repository_identity["transport_digest"],
        "target_branch": target_branch,
        "target_generation": target_generation,
        "target_sha": target_sha,
        "previous_record_id": previous_record_id,
        "source_kind": source_kind,
        "source_execution_id": source_execution_id,
        "source_release_id": source_release_id,
        "publication_transaction_id": publication_transaction_id,
        "source_observation_id": source_observation_id,
        "actor": actor,
        "recorded_at": recorded_at,
    }
    candidate = {**material, "record_id": digest_json(material)}
    return _validate_repository_target_watermark(
        candidate,
        repository_identity=repository_identity,
        target_branch=target_branch,
    )


def _initialize_repository_target_watermark(
    coordination_dir: Path,
    *,
    repository_identity: Mapping[str, object],
    target_branch: str,
    target_sha: str,
    source_execution_id: str,
    source_observation: Mapping[str, object] | None,
    actor: str,
    recorded_at: str,
) -> Mapping[str, object]:
    lock = coordination_dir / "arbiter" / "locks" / "arbiter-authority.lock"
    if not runtime_file_lock_is_held(lock):
        raise ConfigurationError(
            "repository target watermark initialization requires arbiter authority"
        )
    source_observation_id: str | None = None
    if source_observation is not None:
        observed = _validate_initial_remote_target_observation(
            source_observation,
            repository_identity=repository_identity,
            target_branch=target_branch,
            target_sha=target_sha,
            execution_id=source_execution_id,
        )
        source_observation_id = str(observed["record_id"])
        observation_path = _initial_remote_target_observation_path(
            coordination_dir,
            repository_identity=repository_identity,
            target_branch=target_branch,
            observation_id=source_observation_id,
        )
        exclusive_write_json_or_identical(observation_path, observed)
    current_path, history_path = _repository_target_watermark_paths(
        coordination_dir,
        repository_identity=repository_identity,
        target_branch=target_branch,
    )
    history = _repository_target_watermark_events_unlocked(
        coordination_dir,
        repository_identity=repository_identity,
        target_branch=target_branch,
    )
    if current_path.is_file():
        current = _read_repository_target_watermark_unlocked(
            coordination_dir,
            repository_identity=repository_identity,
            target_branch=target_branch,
        )
        if current.get("target_sha") != target_sha:
            raise ConfigurationError(
                "installed repository target watermark differs from migration target"
            )
        return current
    if history:
        if (
            len(history) != 1
            or history[0].get("source_kind")
            not in {"INITIAL_MIGRATION", "INITIAL_REMOTE"}
            or history[0].get("target_sha") != target_sha
            or history[0].get("source_execution_id") != source_execution_id
            or history[0].get("source_observation_id")
            != source_observation_id
        ):
            raise ConfigurationError(
                "repository target watermark initialization has ambiguous history"
            )
        candidate = history[0]
    else:
        candidate = _target_watermark_candidate(
            repository_identity=repository_identity,
            target_branch=target_branch,
            target_generation=1,
            target_sha=target_sha,
            previous_record_id=None,
            source_kind=(
                "INITIAL_REMOTE"
                if source_observation_id is not None
                else "INITIAL_MIGRATION"
            ),
            source_execution_id=source_execution_id,
            source_release_id=None,
            publication_transaction_id=None,
            source_observation_id=source_observation_id,
            actor=actor,
            recorded_at=recorded_at,
        )
        append_jsonl(history_path, candidate)
    atomic_write_json(current_path, candidate)
    return _read_repository_target_watermark_unlocked(
        coordination_dir,
        repository_identity=repository_identity,
        target_branch=target_branch,
    )


def _advance_repository_target_watermark_unlocked(
    coordination_dir: Path,
    *,
    repository_identity: Mapping[str, object],
    target_branch: str,
    execution_id: str,
    expected_generation: int,
    expected_target_sha: str,
    target_sha: str,
    source_kind: str,
    source_release_id: str | None,
    publication_transaction_id: str | None,
    source_observation_id: str | None,
    actor: str,
    recorded_at: str,
) -> Mapping[str, object]:
    lock = coordination_dir / "arbiter" / "locks" / "arbiter-authority.lock"
    if not runtime_file_lock_is_held(lock):
        raise ConfigurationError(
            "repository target watermark advance requires caller-held arbiter authority"
        )
    if (
        type(expected_generation) is not int
        or expected_generation < 1
        or FULL_SHA.fullmatch(expected_target_sha) is None
        or FULL_SHA.fullmatch(target_sha) is None
        or expected_target_sha == target_sha
        or AUTHORITY_ID.fullmatch(execution_id) is None
        or not actor.strip()
    ):
        raise ConfigurationError("repository target watermark advance fence is invalid")
    current_path, history_path = _repository_target_watermark_paths(
        coordination_dir,
        repository_identity=repository_identity,
        target_branch=target_branch,
    )
    current = _read_repository_target_watermark_current_unlocked(
        coordination_dir,
        repository_identity=repository_identity,
        target_branch=target_branch,
    )
    history = _repository_target_watermark_events_unlocked(
        coordination_dir,
        repository_identity=repository_identity,
        target_branch=target_branch,
    )
    expected_source = {
        "source_kind": source_kind,
        "source_execution_id": execution_id,
        "source_release_id": source_release_id,
        "publication_transaction_id": publication_transaction_id,
        "source_observation_id": source_observation_id,
        "target_sha": target_sha,
    }
    # A crash may append the exact candidate before replacing current. Reuse its
    # original clock bytes; never synthesize a second generation on retry.
    if (
        history
        and history[-1].get("previous_record_id") == current.get("record_id")
        and history[-1].get("target_generation")
        == int(current["target_generation"]) + 1
        and all(history[-1].get(key) == value for key, value in expected_source.items())
    ):
        candidate = history[-1]
        if (
            current.get("target_generation") != expected_generation
            or current.get("target_sha") != expected_target_sha
        ):
            raise ConfigurationError(
                "repository target watermark retry predecessor fence changed"
            )
        atomic_write_json(current_path, candidate)
        return _read_repository_target_watermark_unlocked(
            coordination_dir,
            repository_identity=repository_identity,
            target_branch=target_branch,
        )
    if (
        current.get("target_sha") == target_sha
        and all(current.get(key) == value for key, value in expected_source.items())
    ):
        return current
    if (
        current.get("target_generation") != expected_generation
        or current.get("target_sha") != expected_target_sha
    ):
        raise ConfigurationError(
            "repository target watermark compare-and-swap fence mismatch"
        )
    candidate = _target_watermark_candidate(
        repository_identity=repository_identity,
        target_branch=target_branch,
        target_generation=expected_generation + 1,
        target_sha=target_sha,
        previous_record_id=str(current["record_id"]),
        source_kind=source_kind,
        source_execution_id=execution_id,
        source_release_id=source_release_id,
        publication_transaction_id=publication_transaction_id,
        source_observation_id=source_observation_id,
        actor=actor,
        recorded_at=recorded_at,
    )
    append_jsonl(history_path, candidate)
    atomic_write_json(current_path, candidate)
    return _read_repository_target_watermark_unlocked(
        coordination_dir,
        repository_identity=repository_identity,
        target_branch=target_branch,
    )


def validate_host_effect_reconciliation_evidence(
    value: object,
    *,
    effect: Mapping[str, object],
) -> Mapping[str, object]:
    """Replay one adapter observation enriched with the exact writer fence."""

    raw_fields = {
        "schema_version",
        "kind",
        "execution_namespace",
        "execution_id",
        "host_id",
        "effect_kind",
        "idempotency_key",
        "outcome",
        "external_identity",
        "result",
        "unobserved_host_lifecycle_items",
        "observed_at",
    }
    provenance_fields = {
        "host_kernel_generation",
        "execution_adapter_identity_record_id",
        "execution_adapter_identity_path",
        "execution_adapter_identity_blob_digest",
        "adapter_observation_id",
    }
    expected_fields = raw_fields | provenance_fields | {"record_id"}
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        raise ConfigurationError(
            "host-effect reconciliation evidence schema is invalid"
        )
    material = dict(value)
    record_id = material.pop("record_id", None)
    raw_material = {field: value[field] for field in raw_fields}
    if (
        value.get("schema_version") != 1
        or value.get("kind")
        != "hive-mind-host-effect-reconciliation-observation-v1"
        or record_id != digest_json(material)
        or value.get("adapter_observation_id") != digest_json(raw_material)
        or value.get("effect_kind") != effect.get("effect_kind")
        or value.get("idempotency_key") != effect.get("idempotency_key")
        or any(
            value.get(field) != effect.get(field)
            for field in (
                "host_kernel_generation",
                "execution_adapter_identity_record_id",
                "execution_adapter_identity_path",
                "execution_adapter_identity_blob_digest",
            )
        )
        or value.get("outcome") not in {"COMPLETED", "UNKNOWN"}
    ):
        raise ConfigurationError(
            "host-effect reconciliation evidence identity is invalid"
        )
    try:
        parse_time(value.get("observed_at"))
    except (TypeError, ValueError) as error:
        raise ConfigurationError(
            "host-effect reconciliation evidence time is invalid"
        ) from error
    external_fields = {
        "schema_version",
        "kind",
        "execution_namespace",
        "execution_id",
        "host_id",
        "effect_kind",
        "idempotency_key",
        "external_id",
        "record_id",
    }
    item_fields = {
        "schema_version",
        "kind",
        "execution_namespace",
        "execution_id",
        "host_id",
        "effect_kind",
        "idempotency_key",
        "item_type",
        "item_identity",
        "record_id",
    }
    external = value.get("external_identity")
    if not isinstance(external, Mapping) or set(external) != external_fields:
        raise ConfigurationError(
            "host-effect reconciliation external identity schema is invalid"
        )
    external_material = dict(external)
    external_record_id = external_material.pop("record_id", None)
    coordinate_fields = (
        "execution_namespace",
        "execution_id",
        "host_id",
        "effect_kind",
        "idempotency_key",
    )
    if (
        external.get("schema_version") != 1
        or external.get("kind")
        != "hive-mind-host-effect-external-identity-v1"
        or external_record_id != digest_json(external_material)
        or any(external.get(field) != value.get(field) for field in coordinate_fields)
    ):
        raise ConfigurationError(
            "host-effect reconciliation external identity is invalid"
        )
    items = value.get("unobserved_host_lifecycle_items")
    if not isinstance(items, list):
        raise ConfigurationError(
            "host-effect reconciliation unresolved inventory is invalid"
        )
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping) or set(item) != item_fields:
            raise ConfigurationError(
                "host-effect reconciliation unresolved item schema is invalid"
            )
        item_material = dict(item)
        item_id = item_material.pop("record_id", None)
        if (
            item.get("schema_version") != 1
            or item.get("kind")
            != "hive-mind-unobserved-host-lifecycle-item-v1"
            or item.get("item_type") not in {"THREAD", "TURN", "EFFECT"}
            or not isinstance(item.get("item_identity"), str)
            or not str(item["item_identity"]).strip()
            or item_id != digest_json(item_material)
            or any(item.get(field) != value.get(field) for field in coordinate_fields)
            or str(item_id) in seen
        ):
            raise ConfigurationError(
                "host-effect reconciliation unresolved item is invalid"
            )
        seen.add(str(item_id))
    external_id = external.get("external_id")
    result = value.get("result")
    if value.get("outcome") == "COMPLETED":
        if (
            not isinstance(external_id, str)
            or not external_id.strip()
            or not isinstance(result, Mapping)
            or items
        ):
            raise ConfigurationError(
                "completed host-effect reconciliation is incomplete"
            )
    elif external_id is not None or result is not None or not items:
        raise ConfigurationError(
            "unknown host-effect reconciliation fabricates terminal evidence"
        )
    return dict(value)


def validate_host_effect_ledger_records(
    records: Sequence[Mapping[str, object]],
    *,
    launch_instruction_id: str,
    execution_dir: str | Path | None = None,
) -> tuple[Mapping[str, object], ...]:
    """Validate the canonical external-effect state machine once for all readers."""

    legacy_fields = {
        "schema_version",
        "kind",
        "state",
        "effect_id",
        "operation_lease_id",
        "attempt",
        "launch_instruction_id",
        "resource_key",
        "authority_epoch",
        "dispatcher_release_id",
        "dispatcher_admission_epoch",
        "effect_kind",
        "idempotency_key",
        "request_digest",
        "prepared_at",
        "lease_expires_at",
        "completed_at",
        "result_digest",
        "error_code",
        "reconciliation_observation_id",
        "previous_event_id",
        "event_id",
    }
    adapter_fields = {
        "host_kernel_generation",
        "execution_adapter_identity_record_id",
        "execution_adapter_identity_path",
        "execution_adapter_identity_blob_digest",
    }
    fields = legacy_fields | adapter_fields
    identity_fields = {
        "effect_id",
        "operation_lease_id",
        "attempt",
        "launch_instruction_id",
        "resource_key",
        "authority_epoch",
        "dispatcher_release_id",
        "dispatcher_admission_epoch",
        "effect_kind",
        "idempotency_key",
        "request_digest",
        "prepared_at",
        "lease_expires_at",
    } | adapter_fields
    effect_kinds = {
        "CREATE_THREAD",
        "SEND_PRIMARY_MESSAGE",
        "SPAWN_SIDECAR",
        "SEND_SIDECAR_MESSAGE",
        "CLOSE_SIDECAR",
    }
    previous: str | None = None
    attempts: dict[str, int] = {}
    latest_attempts: dict[tuple[str, int], Mapping[str, object]] = {}
    result: list[Mapping[str, object]] = []
    for index, record in enumerate(records, 1):
        material = dict(record)
        event_id = material.pop("event_id", None)
        if (
            frozenset(record)
            not in {frozenset(fields), frozenset(legacy_fields)}
            or record.get("schema_version") != 1
            or record.get("kind") != "hive-mind-host-effect-event-v1"
            or record.get("state")
            not in {"PREPARED", "COMPLETED", "RECONCILIATION_REQUIRED"}
            or record.get("previous_event_id") != previous
            or event_id != digest_json(material)
            or record.get("launch_instruction_id") != launch_instruction_id
        ):
            raise ConfigurationError(
                f"host-effect intent ledger line {index} has invalid lineage"
            )
        has_adapter_identity = adapter_fields.issubset(record)
        if has_adapter_identity:
            for field in (
                "host_kernel_generation",
                "execution_adapter_identity_record_id",
                "execution_adapter_identity_blob_digest",
            ):
                if AUTHORITY_ID.fullmatch(str(record.get(field))) is None:
                    raise ConfigurationError(
                        f"host-effect intent ledger line {index} has invalid {field}"
                    )
            adapter_record_id = str(
                record["execution_adapter_identity_record_id"]
            )
            if record.get("execution_adapter_identity_path") != (
                "execution-adapter-bindings/"
                + adapter_record_id.removeprefix("sha256:")
                + ".json"
            ):
                raise ConfigurationError(
                    f"host-effect intent ledger line {index} has invalid adapter evidence path"
                )
        for field in (
            "effect_id",
            "operation_lease_id",
            "launch_instruction_id",
            "resource_key",
            "idempotency_key",
            "request_digest",
        ):
            if AUTHORITY_ID.fullmatch(str(record.get(field))) is None:
                raise ConfigurationError(
                    f"host-effect intent ledger line {index} has invalid {field}"
                )
        if (
            record.get("effect_kind") not in effect_kinds
            or type(record.get("authority_epoch")) is not int
            or int(record["authority_epoch"]) < 1
            or type(record.get("attempt")) is not int
            or int(record["attempt"]) < 1
        ):
            raise ConfigurationError(
                f"host-effect intent ledger line {index} has invalid authority"
            )
        release_id = record.get("dispatcher_release_id")
        admission_epoch = record.get("dispatcher_admission_epoch")
        if (release_id is None) != (admission_epoch is None) or (
            release_id is not None
            and (
                AUTHORITY_ID.fullmatch(str(release_id)) is None
                or type(admission_epoch) is not int
                or int(admission_epoch) < 1
            )
        ):
            raise ConfigurationError(
                f"host-effect intent ledger line {index} has invalid dispatcher authority"
            )
        effect_material = {
            "kind": "hive-mind-host-effect-key-v1",
            "launch_instruction_id": record["launch_instruction_id"],
            "resource_key": record["resource_key"],
            "authority_epoch": record["authority_epoch"],
            "dispatcher_release_id": release_id,
            "dispatcher_admission_epoch": admission_epoch,
            "effect_kind": record["effect_kind"],
            "idempotency_key": record["idempotency_key"],
            "request_digest": record["request_digest"],
        }
        if has_adapter_identity:
            effect_material.update(
                {
                    field: record[field]
                    for field in sorted(adapter_fields)
                }
            )
        if record.get("effect_id") != digest_json(effect_material):
            raise ConfigurationError(
                f"host-effect intent ledger line {index} has invalid effect digest"
            )
        try:
            prepared_at = parse_time(record.get("prepared_at"))
            lease_expires_at = parse_time(record.get("lease_expires_at"))
        except (TypeError, ValueError) as error:
            raise ConfigurationError(
                f"host-effect intent ledger line {index} has invalid time bounds"
            ) from error
        if lease_expires_at <= prepared_at:
            raise ConfigurationError(
                f"host-effect intent ledger line {index} has empty operation lease"
            )
        lease_material = {
            "kind": "hive-mind-host-effect-operation-lease-v1",
            "effect_id": record["effect_id"],
            "attempt": record["attempt"],
            "prepared_at": record["prepared_at"],
            "lease_expires_at": record["lease_expires_at"],
        }
        if record.get("operation_lease_id") != digest_json(lease_material):
            raise ConfigurationError(
                f"host-effect intent ledger line {index} has invalid lease digest"
            )
        effect_id = str(record["effect_id"])
        attempt = int(record["attempt"])
        key = (effect_id, attempt)
        prior = latest_attempts.get(key)
        state = str(record["state"])
        if state == "PREPARED":
            if prior is not None or attempt != attempts.get(effect_id, 0) + 1:
                raise ConfigurationError(
                    f"host-effect intent ledger line {index} reuses an attempt"
                )
            if any(
                record.get(field) is not None
                for field in (
                    "completed_at",
                    "result_digest",
                    "error_code",
                    "reconciliation_observation_id",
                )
            ):
                raise ConfigurationError(
                    f"host-effect intent ledger line {index} fabricates prepared evidence"
                )
            attempts[effect_id] = attempt
        else:
            if prior is None or prior.get("state") == "COMPLETED":
                raise ConfigurationError(
                    f"host-effect intent ledger line {index} has impossible ancestry"
                )
            if any(prior.get(field) != record.get(field) for field in identity_fields):
                raise ConfigurationError(
                    f"host-effect intent ledger line {index} mutates its authority"
                )
            try:
                completed_at = parse_time(record.get("completed_at"))
            except (TypeError, ValueError) as error:
                raise ConfigurationError(
                    f"host-effect intent ledger line {index} lacks completion time"
                ) from error
            if completed_at < prepared_at:
                raise ConfigurationError(
                    f"host-effect intent ledger line {index} predates preparation"
                )
            observation_id = record.get("reconciliation_observation_id")
            if observation_id is not None and AUTHORITY_ID.fullmatch(
                str(observation_id)
            ) is None:
                raise ConfigurationError(
                    f"host-effect intent ledger line {index} has invalid reconciliation evidence"
                )
            if observation_id is not None and has_adapter_identity:
                if execution_dir is None:
                    raise ConfigurationError(
                        "current host-effect reconciliation requires its execution root"
                    )
                evidence_path = (
                    Path(execution_dir).resolve()
                    / "host-effect-reconciliations"
                    / (str(observation_id).removeprefix("sha256:") + ".json")
                )
                evidence = read_strict_canonical_json(
                    evidence_path,
                    label="host-effect reconciliation evidence",
                )
                validated_evidence = validate_host_effect_reconciliation_evidence(
                    evidence, effect=record
                )
                if validated_evidence.get("record_id") != observation_id:
                    raise ConfigurationError(
                        f"host-effect intent ledger line {index} reconciliation evidence changed"
                    )
            if state == "COMPLETED":
                if (
                    AUTHORITY_ID.fullmatch(str(record.get("result_digest"))) is None
                    or record.get("error_code") is not None
                ):
                    raise ConfigurationError(
                        f"host-effect intent ledger line {index} has invalid completion"
                    )
            elif (
                not isinstance(record.get("error_code"), str)
                or not str(record["error_code"]).strip()
                or (
                    record.get("result_digest") is not None
                    and AUTHORITY_ID.fullmatch(str(record.get("result_digest")))
                    is None
                )
            ):
                raise ConfigurationError(
                    f"host-effect intent ledger line {index} has invalid recovery evidence"
                )
        latest_attempts[key] = record
        previous = str(event_id)
        result.append(record)
    return tuple(result)


def execution_host_effect_obligations(
    execution_dir: str | Path,
) -> tuple[Mapping[str, object], ...]:
    """Return every nonterminal external effect from one authenticated execution.

    Callers forming an authority cut hold ``task-bindings.lock``.  Every effect
    transition uses that same lock, so the returned inventory cannot miss a
    concurrent PREPARED append or external-outcome reconciliation.
    """

    root = _reject_link_components(
        execution_dir, label="execution host-effect root"
    ).resolve()
    directory = root / "host-effects"
    if not directory.exists() and not _is_link_like(directory):
        return ()
    _reject_link_components(directory, label="execution host-effect directory")
    if not directory.is_dir():
        raise ConfigurationError("execution host-effect directory is not a directory")
    latest: dict[str, Mapping[str, object]] = {}
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        _reject_link_components(path, label="host-effect intent ledger")
        if not path.is_file() or re.fullmatch(r"[0-9a-f]{64}\.jsonl", path.name) is None:
            raise ConfigurationError(
                "execution host-effect directory contains an unclassified entry"
            )
        records = validate_host_effect_ledger_records(
            strict_jsonl_records(path, label="host-effect intent ledger"),
            launch_instruction_id="sha256:" + path.stem,
            execution_dir=root,
        )
        for event in records:
            latest[str(event["effect_id"])] = event
    return tuple(
        dict(latest[key])
        for key in sorted(latest)
        if latest[key].get("state") != "COMPLETED"
    )


def archive_file_without_overwrite(
    source: Path,
    archive_dir: Path,
    stem: str,
) -> Path:
    """Hard-link exact bytes to the first unused archive name, then retire source."""

    if not re.fullmatch(r"[a-zA-Z0-9._-]+", stem):
        raise ConfigurationError("archive identity is invalid")
    if _is_link_like(source) or not source.is_file():
        raise ConfigurationError(f"authority file is not a regular file: {source}")
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_dir = _reject_link_components(
        archive_dir,
        label="runtime archive directory",
    )
    for generation in range(1, 10_001):
        suffix = "" if generation == 1 else f"-{generation}"
        candidate = archive_dir / f"{stem}{suffix}.json"
        try:
            os.link(source, candidate, follow_symlinks=False)
        except FileExistsError:
            continue
        except OSError as error:
            raise ConfigurationError(
                f"cannot preserve authority archive {candidate}: {error}"
            ) from error
        source.unlink()
        return candidate
    raise ConfigurationError("authority archive collision budget exhausted")


def read_claim_authority_file(
    path: Path,
) -> tuple[Mapping[str, Any], datetime, bytes]:
    """Read a claim exactly; malformed identity or expiry is never treated stale."""

    _reject_link_components(path, label="claim authority path")
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_json_pairs,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ConfigurationError(f"claim authority is malformed: {path}: {error}") from error
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"claim authority must be an object: {path}")
    if frozenset(value) not in (_LEGACY_CLAIM_SCHEMAS | {_CURRENT_CLAIM_FIELDS}):
        raise ConfigurationError(f"claim authority schema is ambiguous: {path}")
    if raw != (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8"):
        raise ConfigurationError(f"claim authority encoding is noncanonical: {path}")
    node_id = value.get("node_id")
    if not isinstance(node_id, str) or not node_id.strip():
        raise ConfigurationError(f"claim authority node identity is ambiguous: {path}")
    if frozenset(value) == _CURRENT_CLAIM_FIELDS:
        execution_id = value.get("execution_id")
        repository = value.get("repository")
        expected_name = digest_json(
            {
                "kind": "hive-mind-claim-file-key-v1",
                "repository": repository,
                "execution_id": execution_id,
                "node_id": node_id,
            }
        ).removeprefix("sha256:") + ".json"
        if path.name != expected_name:
            raise ConfigurationError(f"claim authority file key is invalid: {path}")
        material = dict(value)
        claim_id = material.pop("claim_id", None)
        if claim_id != digest_json(material):
            raise ConfigurationError(f"claim authority digest is invalid: {path}")
    elif path.stem != node_id:
        raise ConfigurationError(f"legacy claim authority file key is ambiguous: {path}")
    try:
        expires = parse_time(value.get("expires_at"))
    except (TypeError, ValueError) as error:
        raise ConfigurationError(
            f"claim authority expiry is malformed; reconciliation is required: {path}"
        ) from error
    return value, expires, raw


def normalize_path(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("path must be non-empty text")
    raw = value.replace("\\", "/").strip()
    if raw.startswith("/") or re.match(r"^[A-Za-z]:/", raw):
        raise ValueError("absolute paths are prohibited")
    parts: list[str] = []
    for part in raw.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            raise ValueError("path traversal is prohibited")
        parts.append(part)
    if not parts:
        raise ValueError("path cannot normalize to repository root")
    return "/".join(parts)


def _scope_static_prefix(scope: str) -> str:
    normalized = scope.replace("\\", "/").strip().rstrip("/")
    wildcard_index = min(
        (index for marker in ("*", "?", "[") if (index := normalized.find(marker)) >= 0),
        default=len(normalized),
    )
    prefix = normalized[:wildcard_index].rstrip("/")
    if not prefix:
        raise ValueError("scope wildcard must retain a repository-relative prefix")
    return normalize_path(prefix)


def path_matches_scope(path: str, scope: str) -> bool:
    normalized_path = normalize_path(path)
    normalized_scope = scope.replace("\\", "/").strip().rstrip("/")
    if any(marker in normalized_scope for marker in ("*", "?", "[")):
        # ``fnmatch`` gives exact portable glob semantics. ``/**`` additionally
        # includes the named root itself so directory-scoped locks remain useful.
        if normalized_scope.endswith("/**"):
            root = normalize_path(normalized_scope[:-3])
            if normalized_path == root:
                return True
        return fnmatch.fnmatchcase(normalized_path, normalized_scope)
    root = normalize_path(normalized_scope)
    return normalized_path == root or normalized_path.startswith(root + "/")


def scopes_overlap(first: str, second: str) -> bool:
    first_root = _scope_static_prefix(first)
    second_root = _scope_static_prefix(second)
    if (
        first_root == second_root
        or first_root.startswith(second_root + "/")
        or second_root.startswith(first_root + "/")
    ):
        return True
    # Distinct sibling glob scopes may still collide on one concrete path. Probe the
    # static prefixes against both patterns without claiming disjointness from names.
    return path_matches_scope(first_root, second) or path_matches_scope(second_root, first)


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{label} must be an object")
    return value


def _require_list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ConfigurationError(f"{label} must be a list")
    return value


def _require_nonempty_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{label} must be non-empty text")
    return value.strip()


class ControlPlane:
    """Read, validate, and mutate deterministic implementation-plan state."""

    REQUIRED_FILES = (
        ".autopilot/README.md",
        ".autopilot/plan.json",
        ".autopilot/control-plane.json",
        ".autopilot/provider-catalog.json",
        ".autopilot/model-routing.json",
        ".autopilot/receipt.schema.json",
        ".autopilot/consultation.schema.json",
        ".autopilot/role-wiring.schema.json",
        ".autopilot/orchestration-policy.json",
        ".autopilot/orchestration-policy.schema.json",
        ".autopilot/bin/orchestration.py",
        ".autopilot/task-bindings.lock",
        ".autopilot/acceptance-matrix.json",
        ".autopilot/templates/worker.md",
        ".autopilot/templates/repair.md",
        ".autopilot/templates/consultation.md",
        ".autopilot/templates/reconciliation.md",
        ".autopilot/templates/integration.md",
        ".autopilot/templates/promotion.md",
        ".autopilot/templates/replan.md",
        ".autopilot/templates/human-escalation.md",
    )

    def __init__(
        self,
        repo_root: str | Path,
        *,
        clock: Callable[[], datetime] = utc_now,
        state_dir: str | Path | None = None,
        execution_namespace: str = "default",
        host_runtime_dir: str | Path | None = None,
    ) -> Mapping[str, Any]:
        self.repo_root = Path(repo_root).resolve()
        self.ap_root = self.repo_root / ".autopilot"
        self.clock = clock
        self.plan_path = self.ap_root / "plan.json"
        self.control_path = self.ap_root / "control-plane.json"
        self.provider_path = self.ap_root / "provider-catalog.json"
        self.routing_path = self.ap_root / "model-routing.json"
        self.role_matrix_path = self.ap_root / "role-wiring.json"
        self.acceptance_path = self.ap_root / "acceptance-matrix.json"
        self._legacy_state_dir = self.ap_root / "state"
        self.coordination_dir = resolve_repository_state_dir(self.repo_root, state_dir)
        self.host_runtime_dir = resolve_host_runtime_dir(host_runtime_dir)
        self.plan = _require_mapping(read_json(self.plan_path), "plan")
        self.control = _require_mapping(read_json(self.control_path), "control plane")
        self.provider_catalog = _require_mapping(
            read_json(self.provider_path), "provider catalog"
        )
        self.model_routing = _require_mapping(
            read_json(self.routing_path), "model routing"
        )
        self.role_matrix = _require_mapping(
            read_json(self.role_matrix_path), "role wiring matrix"
        )
        self.acceptance_matrix = _require_mapping(
            read_json(self.acceptance_path), "acceptance matrix"
        )
        repository_identity = runtime_repository_identity(self.repo_root)
        if repository_identity is None:
            fixture_transport = digest_json(
                {
                    "kind": "hive-mind-fixture-repository-transport-v1",
                    "repository_path": str(self.repo_root),
                }
            )
            repository_identity = {
                "schema_version": 1,
                "kind": "hive-mind-runtime-authority-identity-v1",
                "repository": str(self.repo_root),
                "canonical_remote_fetch": str(self.repo_root),
                "canonical_remote_push": str(self.repo_root),
                "transport_digest": fixture_transport,
            }
        self.repository_identity = dict(repository_identity)
        self.execution_namespace = execution_namespace
        self.execution_identity = execution_namespace_identity(
            repository_identity,
            kernel_identity=runtime_kernel_identity(self.repo_root),
            namespace=execution_namespace,
            target_branch=self.target_branch,
            plan_fingerprint=self.expected_plan_fingerprint,
        )
        self.execution_id = str(self.execution_identity["execution_id"])
        self.execution_dir = execution_namespace_dir(
            self.coordination_dir, self.execution_id
        )
        if (self.execution_dir / "execution-identity.json").is_file():
            require_execution_namespace(
                self.coordination_dir, self.execution_identity
            )
        # Construction is non-mutating and is also used by the explicit
        # execution-init coordinator command.  Every execution-local property,
        # lock and mutator below still calls require_execution_namespace, so an
        # absent identity cannot be treated as authority or lazily created.
        self.arbiter_dir = self.coordination_dir / "arbiter"
        self.claims_dir = self.arbiter_dir / "claims"
        validation_key = digest_json(
            {
                "kind": "hive-mind-validation-resource-key-v1",
                "repository": repository_identity["repository"],
                "repository_transport_digest": repository_identity[
                    "transport_digest"
                ],
                "target_branch": self.target_branch,
            }
        )
        self.validation_resource_key = validation_key
        self.validation_lease_path = (
            self.arbiter_dir
            / "validation-leases"
            / (validation_key.removeprefix("sha256:") + ".json")
        )
        self._nodes = {
            str(node["id"]): node
            for node in _require_list(self.plan.get("nodes"), "plan.nodes")
            if isinstance(node, Mapping) and "id" in node
        }

    @property
    def state_dir(self) -> Path:
        """Return the live execution state, switching atomically after migration."""

        if (self.execution_dir / "execution-identity.json").is_file():
            return self._fresh_execution_authority()
        if (self.coordination_dir / RUNTIME_READY_MANIFEST).is_file():
            raise ConfigurationError(
                "runtime READY has no authenticated execution namespace; run execution-init"
            )
        return self._legacy_state_dir

    def _fresh_execution_authority(self) -> Path:
        """Reauthenticate the installed identity and executable FSM bytes.

        A long-lived plane must not continue mutating shared authority after its
        checkout's controller/interpreter/template bundle changes underneath it.
        The namespace check authenticates the sealed plan/target identity; the
        authority-dir check independently hashes the current kernel bytes.
        """

        require_execution_namespace(
            self.coordination_dir, self.execution_identity
        )
        return require_execution_authority_dir(
            self.repo_root,
            self.execution_dir,
            execution_id=self.execution_id,
            execution_namespace=self.execution_namespace,
        )

    @property
    def receipts_dir(self) -> Path:
        return self.state_dir / "receipts"

    @property
    def failures_dir(self) -> Path:
        return self.state_dir / "failures"

    @property
    def blockers_dir(self) -> Path:
        return self.state_dir / "blockers"

    @property
    def questions_dir(self) -> Path:
        return self.state_dir / "questions"

    @property
    def subtask_waves_dir(self) -> Path:
        return self.state_dir / "subtask-waves"

    @property
    def quarantine_dir(self) -> Path:
        return self.state_dir / "quarantine"

    @property
    def escalations_dir(self) -> Path:
        return self.state_dir / "escalations"

    def runtime_lock(self, name: str, *, timeout_seconds: float = 10.0):
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*\.lock", name):
            raise ConfigurationError("runtime lock name is invalid")
        identity = ensure_repository_runtime_identity(
            self.repo_root,
            self.coordination_dir,
            create=False,
        )
        if name in ARBITER_LOCKS:
            path = self.arbiter_dir / "locks" / name
        elif (self.execution_dir / "execution-identity.json").is_file():
            path = self._fresh_execution_authority() / "locks" / name
        else:
            # Compatibility is read only until the explicit namespace migration
            # moves existing authority; no new execution identity is created here.
            path = self.coordination_dir / "locks" / name
        if identity is not None and not path.is_file():
            raise ConfigurationError(
                "runtime authority lock is absent; run runtime-authority-migrate"
            )
        # Minimal fixtures without a configured repository identity retain an
        # isolated lock surface; production repositories never initialize here.
        if path.parent.parent == self.execution_dir:
            return self._execution_runtime_lock(
                path, timeout_seconds=timeout_seconds
            )
        return runtime_file_lock(path, timeout_seconds=timeout_seconds)

    @contextmanager
    def _execution_runtime_lock(
        self, path: Path, *, timeout_seconds: float
    ):
        """Acquire an execution lock, then reauthenticate the writer generation.

        The pre-acquisition path check is not a fence: a stale process can wait
        behind an upgrade and otherwise write after the successor releases the
        same lock.  The second check occurs while the selected lock is owned.
        """

        with runtime_file_lock(path, timeout_seconds=timeout_seconds):
            self._fresh_execution_authority()
            yield

    def runtime_read_lock(self, name: str, *, timeout_seconds: float = 10.0):
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*\.lock", name):
            raise ConfigurationError("runtime lock name is invalid")
        ensure_repository_runtime_identity(
            self.repo_root,
            self.coordination_dir,
            create=False,
        )
        if name in ARBITER_LOCKS:
            path = self.arbiter_dir / "locks" / name
        elif (self.execution_dir / "execution-identity.json").is_file():
            path = self._fresh_execution_authority() / "locks" / name
        else:
            path = self.coordination_dir / "locks" / name
        if not path.is_file():
            raise ConfigurationError(
                "runtime read lock is absent; run an explicit authority migration"
            )
        if path.parent.parent == self.execution_dir:
            return self._execution_runtime_lock(
                path, timeout_seconds=timeout_seconds
            )
        return runtime_file_lock(path, timeout_seconds=timeout_seconds)

    def arbiter_lock(self, name: str = "arbiter-authority.lock", *, timeout_seconds: float = 10.0):
        if name not in ARBITER_LOCKS:
            raise ConfigurationError("global arbiter lock name is invalid")
        ensure_repository_runtime_identity(
            self.repo_root, self.coordination_dir, create=False
        )
        path = self.arbiter_dir / "locks" / name
        if not path.is_file() or _is_link_like(path):
            raise ConfigurationError(
                "global arbiter lock is absent; run explicit runtime migration"
            )
        return runtime_file_lock(path, timeout_seconds=timeout_seconds)

    def bootstrap_arbiter_lock(
        self,
        *,
        bootstrap_migration_id: str,
        timeout_seconds: float = 10.0,
    ):
        """Acquire the staged arbiter only inside the cold-start transaction.

        Normal arbiter acquisition remains READY-gated.  This narrow bridge is
        authenticated by the already-held host and bootstrap locks, the exact
        completed migration token, and staged repository identity/lock bytes.
        """

        host_root = require_host_runtime(self.host_runtime_dir)
        host_lock = host_root / "locks" / "host-authority.lock"
        bootstrap_lock = self.coordination_dir / RUNTIME_BOOTSTRAP_LOCK
        if (
            not runtime_file_lock_is_held(host_lock)
            or not runtime_file_lock_is_held(bootstrap_lock)
        ):
            raise ConfigurationError(
                "bootstrap arbiter requires outer host and bootstrap authority"
            )
        _root, directory, expected, manifest = _completed_bootstrap_manifest(
            self.repo_root, self.coordination_dir
        )
        if (
            AUTHORITY_ID.fullmatch(bootstrap_migration_id) is None
            or manifest.get("migration_id") != bootstrap_migration_id
        ):
            raise ConfigurationError("bootstrap arbiter migration token is stale")
        if (directory / RUNTIME_READY_MANIFEST).exists() or _is_link_like(
            directory / RUNTIME_READY_MANIFEST
        ):
            raise ConfigurationError(
                "bootstrap arbiter is unavailable after READY publication"
            )
        staged = read_strict_canonical_json(
            directory / "runtime-identity.json",
            label="staged runtime repository identity",
        )
        if staged != expected:
            raise ConfigurationError(
                "bootstrap arbiter staged repository identity is invalid"
            )
        path = directory / "arbiter" / "locks" / "arbiter-authority.lock"
        if not path.is_file() or _is_link_like(path):
            raise ConfigurationError("bootstrap arbiter staged lock is unavailable")
        return runtime_file_lock(path, timeout_seconds=timeout_seconds)

    @contextmanager
    def host_lock(self, *, timeout_seconds: float = 10.0):
        directory = require_host_runtime(self.host_runtime_dir)
        with runtime_file_lock(
            directory / "locks" / "host-authority.lock",
            timeout_seconds=timeout_seconds,
        ):
            _host_runtime_identity_unlocked(directory)
            yield

    def execution_lock(self, name: str, *, timeout_seconds: float = 10.0):
        if name not in EXECUTION_LOCKS + EXECUTION_COORDINATOR_LOCKS:
            raise ConfigurationError("execution lock name is invalid")
        directory = self._fresh_execution_authority()
        return self._execution_runtime_lock(
            directory / "locks" / name, timeout_seconds=timeout_seconds
        )

    def repository_target_watermark(self) -> Mapping[str, object]:
        """Read this execution's target-ref generation under short arbiter authority."""

        with self.arbiter_lock(timeout_seconds=120.0):
            return _read_repository_target_watermark_unlocked(
                self.coordination_dir,
                repository_identity=self.repository_identity,
                target_branch=self.target_branch,
            )

    def initialize_repository_target_watermark(
        self,
        *,
        target_sha: str,
        source_observation: Mapping[str, object],
        actor: str,
    ) -> Mapping[str, object]:
        """Initialize this target ref during explicit execution initialization.

        The caller must already hold repository arbiter authority.  Ordinary
        reads and mutations never create a missing target authority.
        """

        return _initialize_repository_target_watermark(
            self.coordination_dir,
            repository_identity=self.repository_identity,
            target_branch=self.target_branch,
            target_sha=target_sha,
            source_execution_id=self.execution_id,
            source_observation=source_observation,
            actor=actor,
            recorded_at=format_time(self.clock()),
        )

    def advance_repository_target_watermark(
        self,
        *,
        expected_generation: int,
        expected_target_sha: str,
        target_sha: str,
        source_release_id: str,
        publication_transaction_id: str,
        source_record: Mapping[str, object],
        actor: str,
    ) -> Mapping[str, object]:
        """Seal a publication target CAS; caller holds repository arbiter authority."""

        current = _read_repository_target_watermark_current_unlocked(
            self.coordination_dir,
            repository_identity=self.repository_identity,
            target_branch=self.target_branch,
        )
        if (
            current.get("target_sha") == target_sha
            and current.get("source_kind") == "PUBLICATION"
            and current.get("source_execution_id") == self.execution_id
            and current.get("source_release_id") == source_release_id
            and current.get("publication_transaction_id")
            == publication_transaction_id
        ):
            return _read_repository_target_watermark_unlocked(
                self.coordination_dir,
                repository_identity=self.repository_identity,
                target_branch=self.target_branch,
            )
        evidence = _install_target_transition_evidence_unlocked(
            self.coordination_dir,
            repository_identity=self.repository_identity,
            target_branch=self.target_branch,
            previous=current,
            target_sha=target_sha,
            execution_id=self.execution_id,
            execution_namespace=self.execution_namespace,
            plan_fingerprint=self.expected_plan_fingerprint,
            source_kind="PUBLICATION",
            source_release_id=source_release_id,
            publication_transaction_id=publication_transaction_id,
            source_record=source_record,
            observed_at=format_time(self.clock()),
        )

        return _advance_repository_target_watermark_unlocked(
            self.coordination_dir,
            repository_identity=self.repository_identity,
            target_branch=self.target_branch,
            execution_id=self.execution_id,
            expected_generation=expected_generation,
            expected_target_sha=expected_target_sha,
            target_sha=target_sha,
            source_kind="PUBLICATION",
            source_release_id=source_release_id,
            publication_transaction_id=publication_transaction_id,
            source_observation_id=str(evidence["transition_id"]),
            actor=actor,
            recorded_at=format_time(self.clock()),
        )

    def advance_repository_target_watermark_from_superseded_publication(
        self,
        *,
        expected_generation: int,
        expected_target_sha: str,
        target_sha: str,
        source_release_id: str,
        publication_transaction_id: str,
        source_observation: Mapping[str, object],
        actor: str,
    ) -> Mapping[str, object]:
        """Seal an overtaken publication after portable descendant proof.

        The caller holds repository arbiter authority.  The exact observation
        is installed first with O_EXCL-or-identical semantics, so a crash before
        the history append remains a harmless retained evidence blob.
        """

        observed = _validate_superseded_publication_target_observation(
            source_observation,
            repository_identity=self.repository_identity,
            target_branch=self.target_branch,
            expected_target_sha=expected_target_sha,
            target_sha=target_sha,
            execution_id=self.execution_id,
            source_release_id=source_release_id,
            publication_transaction_id=publication_transaction_id,
        )
        observation_id = str(observed["record_id"])
        path = _superseded_publication_target_observation_path(
            self.coordination_dir,
            repository_identity=self.repository_identity,
            target_branch=self.target_branch,
            observation_id=observation_id,
        )
        exclusive_write_json_or_identical(path, observed)
        return _advance_repository_target_watermark_unlocked(
            self.coordination_dir,
            repository_identity=self.repository_identity,
            target_branch=self.target_branch,
            execution_id=self.execution_id,
            expected_generation=expected_generation,
            expected_target_sha=expected_target_sha,
            target_sha=target_sha,
            source_kind="SUPERSEDED_PUBLICATION",
            source_release_id=source_release_id,
            publication_transaction_id=publication_transaction_id,
            source_observation_id=observation_id,
            actor=actor,
            recorded_at=format_time(self.clock()),
        )

    def advance_repository_target_watermark_from_snapshot(
        self,
        *,
        expected_generation: int,
        expected_target_sha: str,
        target_sha: str,
        source_observation: Mapping[str, object],
        actor: str,
    ) -> Mapping[str, object]:
        """Seal an authenticated snapshot target CAS under caller-held arbiter authority."""

        current = _read_repository_target_watermark_current_unlocked(
            self.coordination_dir,
            repository_identity=self.repository_identity,
            target_branch=self.target_branch,
        )
        if (
            current.get("target_sha") == target_sha
            and current.get("source_kind") == "SNAPSHOT_INSTALL"
            and current.get("source_execution_id") == self.execution_id
        ):
            return _read_repository_target_watermark_unlocked(
                self.coordination_dir,
                repository_identity=self.repository_identity,
                target_branch=self.target_branch,
            )
        evidence = _install_target_transition_evidence_unlocked(
            self.coordination_dir,
            repository_identity=self.repository_identity,
            target_branch=self.target_branch,
            previous=current,
            target_sha=target_sha,
            execution_id=self.execution_id,
            execution_namespace=self.execution_namespace,
            plan_fingerprint=self.expected_plan_fingerprint,
            source_kind="SNAPSHOT_INSTALL",
            source_release_id=None,
            publication_transaction_id=None,
            source_record=source_observation,
            observed_at=format_time(self.clock()),
        )

        return _advance_repository_target_watermark_unlocked(
            self.coordination_dir,
            repository_identity=self.repository_identity,
            target_branch=self.target_branch,
            execution_id=self.execution_id,
            expected_generation=expected_generation,
            expected_target_sha=expected_target_sha,
            target_sha=target_sha,
            source_kind="SNAPSHOT_INSTALL",
            source_release_id=None,
            publication_transaction_id=None,
            source_observation_id=str(evidence["transition_id"]),
            actor=actor,
            recorded_at=format_time(self.clock()),
        )

    @property
    def plan_fingerprint(self) -> str:
        document = dict(self.plan)
        document.pop("plan_fingerprint", None)
        return digest_json(document)

    @property
    def expected_plan_fingerprint(self) -> str:
        return _require_nonempty_text(
            self.control.get("plan_fingerprint"),
            "control-plane.plan_fingerprint",
        )

    @property
    def target_branch(self) -> str:
        target = _require_mapping(self.control.get("target"), "control-plane.target")
        return _require_nonempty_text(target.get("branch"), "target.branch")

    @property
    def final_integration_branch(self) -> str:
        target = _require_mapping(self.control.get("target"), "control-plane.target")
        return _require_nonempty_text(
            target.get("final_integration_branch"),
            "target.final_integration_branch",
        )

    @property
    def execution_mode(self) -> str:
        target = _require_mapping(self.control.get("target"), "control-plane.target")
        mode = _require_nonempty_text(target.get("execution_mode"), "target.execution_mode")
        if mode != "singleton-release-branch":
            raise ConfigurationError("target.execution_mode must be singleton-release-branch")
        if self.target_branch == self.final_integration_branch:
            raise ConfigurationError("singleton release target must not equal final integration branch")
        return mode

    @property
    def baseline_sha(self) -> str:
        target = _require_mapping(self.control.get("target"), "control-plane.target")
        sha = _require_nonempty_text(target.get("baseline_sha"), "target.baseline_sha")
        if FULL_SHA.fullmatch(sha) is None:
            raise ConfigurationError("target.baseline_sha must be a full lowercase Git SHA")
        return sha

    @property
    def verify_git_objects(self) -> bool:
        value = self.control.get("verify_git_objects", True)
        if not isinstance(value, bool):
            raise ConfigurationError("verify_git_objects must be boolean")
        return value

    def node(self, node_id: str) -> Mapping[str, Any]:
        try:
            node = self._nodes[node_id]
        except KeyError as error:
            raise AutopilotError(f"unknown node: {node_id}") from error
        # Historical plans named the final integration branch in ``pr_target``.
        # In singleton mode that field is legacy plan provenance, never live
        # authority.  The control-plane target is the only executable target and
        # is overlaid without rewriting the fingerprinted historical plan.
        return {**node, "pr_target": self.target_branch}

    def nodes(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self.node(node_id) for node_id in sorted(self._nodes))

    def validate_configuration(self) -> tuple[str, ...]:
        issues: list[str] = []
        try:
            self.execution_mode
            target = _require_mapping(self.control.get("target"), "control-plane.target")
            protected = target.get("protected_until_final_integration")
            if protected != [self.final_integration_branch]:
                issues.append("target.protected_until_final_integration must protect final integration branch")
            release_base = target.get("release_branch_base")
            if not isinstance(release_base, str) or FULL_SHA.fullmatch(release_base) is None:
                issues.append("target.release_branch_base must be a full lowercase Git SHA")
        except ConfigurationError as error:
            issues.append(str(error))
        if self.plan.get("schema_version") != SCHEMA_VERSION:
            issues.append("plan schema_version is unsupported")
        if self.control.get("schema_version") != SCHEMA_VERSION:
            issues.append("control-plane schema_version is unsupported")
        if self.plan_fingerprint != self.expected_plan_fingerprint:
            issues.append(
                "plan fingerprint mismatch: expected "
                f"{self.expected_plan_fingerprint}, observed {self.plan_fingerprint}"
            )
        raw_nodes = _require_list(self.plan.get("nodes"), "plan.nodes")
        observed_ids = [
            str(item.get("id"))
            for item in raw_nodes
            if isinstance(item, Mapping)
        ]
        if len(observed_ids) != len(set(observed_ids)):
            issues.append("node IDs are not unique")
        if len(self._nodes) != len(raw_nodes):
            issues.append("every node must be an object with an id")
        dependencies: dict[str, tuple[str, ...]] = {}
        for node_id in self._nodes:
            node = self.node(node_id)
            issues.extend(self._validate_node(node_id, node))
            deps = node.get("dependencies", [])
            if not isinstance(deps, list) or any(not isinstance(item, str) for item in deps):
                issues.append(f"{node_id}: dependencies must be a string list")
                continue
            dependencies[node_id] = tuple(deps)
            for dependency in deps:
                if dependency not in self._nodes:
                    issues.append(f"{node_id}: unknown dependency {dependency}")
        cycle = self._find_cycle(dependencies)
        if cycle:
            issues.append("dependency cycle: " + " -> ".join(cycle))
        tiers = self.provider_catalog.get("tiers")
        if not isinstance(tiers, Mapping):
            issues.append("provider catalog tiers must be an object")
            tiers = {}
        for tier in ("T0", "T1", "T2", "T3", "T4"):
            route = tiers.get(tier)
            if not isinstance(route, Mapping):
                issues.append(f"provider route missing for {tier}")
                continue
            for provider in ("openai", "anthropic"):
                provider_route = route.get(provider)
                if not isinstance(provider_route, Mapping):
                    issues.append(f"provider route {tier}.{provider} is missing")
                elif not isinstance(provider_route.get("model"), str):
                    issues.append(f"provider route {tier}.{provider}.model is missing")
        role_rows = self.role_matrix.get("roles")
        if not isinstance(role_rows, list):
            issues.append("role-wiring roles must be a list")
        else:
            role_names = {
                row.get("role") for row in role_rows if isinstance(row, Mapping)
            }
            if role_names != set(ROLE_NAMES):
                issues.append("role-wiring matrix must contain exactly all eight roles")
        required_acceptance = {
            "all_role",
            "humanless_operation",
            "no_cheating",
            "learning",
            "self_healing",
            "repository_safety",
            "staged_autonomy",
        }
        acceptance_suites = self.acceptance_matrix.get("suites")
        if not isinstance(acceptance_suites, Mapping):
            issues.append("acceptance matrix suites must be an object")
        elif not required_acceptance.issubset(acceptance_suites):
            issues.append("acceptance matrix omits required suites")
        for relative in self.REQUIRED_FILES:
            if not (self.repo_root / relative).is_file():
                issues.append(f"required root file is missing: {relative}")
        nested = self.repo_root / "REPO_ROOT" / ".autopilot"
        if nested.exists():
            issues.append(
                "archive-only installation detected: REPO_ROOT contents were not installed "
                "into repository-root paths"
            )
        return tuple(dict.fromkeys(issues))

    def _validate_node(
        self, node_id: str, node: Mapping[str, Any]
    ) -> tuple[str, ...]:
        issues: list[str] = []
        required_text = (
            "objective",
            "rationale",
            "branch",
            "pr_target",
            "risk",
            "reversibility",
            "rollback",
            "stopping_condition",
        )
        for key in required_text:
            if not isinstance(node.get(key), str) or not str(node.get(key)).strip():
                issues.append(f"{node_id}: {key} must be non-empty text")
        if node.get("pr_target") != self.target_branch:
            issues.append(f"{node_id}: effective pr_target must equal the singleton target branch")
        if node.get("contract_version") != 1:
            issues.append(f"{node_id}: contract_version must be 1")
        list_fields = (
            "dependencies",
            "assumptions",
            "required_inputs",
            "expected_outputs",
            "interfaces",
            "read_scope",
            "write_scope",
            "forbidden_scope",
            "roles",
            "consultation_routes",
            "acceptance_criteria",
            "required_tests",
            "evidence_requirements",
            "file_locks",
            "semantic_locks",
            "escalation_conditions",
        )
        for key in list_fields:
            value = node.get(key)
            if not isinstance(value, list) or any(
                not isinstance(item, str) for item in value
            ):
                issues.append(f"{node_id}: {key} must be a string list")
        roles = node.get("roles")
        if isinstance(roles, list) and not set(roles).issubset(ROLE_NAMES):
            issues.append(f"{node_id}: roles contain an unknown role")
        routes = node.get("routes")
        if not isinstance(routes, Mapping):
            issues.append(f"{node_id}: routes must be an object")
        else:
            tier = routes.get("tier")
            if tier not in {"T0", "T1", "T2", "T3", "T4"}:
                issues.append(f"{node_id}: routes.tier is invalid")
            for provider in ("openai", "anthropic"):
                route = routes.get(provider)
                if not isinstance(route, Mapping):
                    issues.append(f"{node_id}: routes.{provider} is missing")
                else:
                    if not isinstance(route.get("model"), str):
                        issues.append(f"{node_id}: routes.{provider}.model missing")
                    if not isinstance(route.get("reasoning_effort"), str):
                        issues.append(
                            f"{node_id}: routes.{provider}.reasoning_effort missing"
                        )
        for scope_key in ("read_scope", "write_scope", "forbidden_scope", "file_locks"):
            scopes = node.get(scope_key)
            if isinstance(scopes, list):
                for scope in scopes:
                    try:
                        normalize_path(str(scope).removesuffix("/**"))
                    except ValueError as error:
                        issues.append(f"{node_id}: invalid {scope_key} {scope!r}: {error}")
        if not isinstance(node.get("parallel_safe"), bool):
            issues.append(f"{node_id}: parallel_safe must be boolean")
        for numeric in ("critical_path_importance", "downstream_unlock_value"):
            value = node.get(numeric)
            if type(value) is not int or not 0 <= value <= 100:
                issues.append(f"{node_id}: {numeric} must be an integer from 0 to 100")
        retries = node.get("max_retries")
        if type(retries) is not int or retries < 0:
            issues.append(f"{node_id}: max_retries must be non-negative integer")
        return tuple(issues)

    @staticmethod
    def _find_cycle(
        dependencies: Mapping[str, Sequence[str]],
    ) -> tuple[str, ...] | None:
        visiting: set[str] = set()
        visited: set[str] = set()
        stack: list[str] = []

        def visit(node_id: str) -> tuple[str, ...] | None:
            if node_id in visited:
                return None
            if node_id in visiting:
                index = stack.index(node_id)
                return tuple((*stack[index:], node_id))
            visiting.add(node_id)
            stack.append(node_id)
            for dependency in dependencies.get(node_id, ()):
                cycle = visit(dependency)
                if cycle:
                    return cycle
            stack.pop()
            visiting.remove(node_id)
            visited.add(node_id)
            return None

        for node_id in dependencies:
            cycle = visit(node_id)
            if cycle:
                return cycle
        return None

    def _git(
        self,
        args: Sequence[str],
        *,
        check: bool = False,
        environment: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        # Git gets only the runtime locations needed by Windows/Schannel and the
        # explicitly validated transport path. Credentials and GIT_CONFIG_*
        # injection variables are never inherited by the child process.
        base_environment = {
            key: value
            for key in SAFE_GIT_RUNTIME_ENVIRONMENT_KEYS
            if (value := os.environ.get(key))
            and not any(character in value for character in "\r\n")
        }
        base_environment["GIT_TERMINAL_PROMPT"] = "0"
        # Keep the controller deterministic while allowing a trusted local
        # proxy/network path to reach GitHub. These values exist only in the
        # child process environment; they are never persisted or printed.
        for key in SAFE_GIT_TRANSPORT_ENVIRONMENT_KEYS:
            value = os.environ.get(key)
            if not value or any(character in value for character in "\r\n"):
                base_environment.pop(key, None)
                continue
            if key.lower() in {"http_proxy", "https_proxy"}:
                parsed = urlparse(value)
                if parsed.scheme not in {"http", "https", "socks5", "socks5h"} or not parsed.hostname:
                    base_environment.pop(key, None)
                    continue
            base_environment[key] = value
        if environment is not None:
            for key, value in environment.items():
                if key.startswith("GIT_CONFIG_"):
                    raise AutopilotError("Git config injection variables are forbidden")
                base_environment[key] = value
        completed = subprocess.run(
            ("git", "-C", str(self.repo_root), *args),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
            env=base_environment,
        )
        if check and completed.returncode:
            raise AutopilotError(
                f"git {' '.join(args)} failed: {completed.stderr.strip()}"
            )
        return completed

    def git_object_exists(self, sha: str) -> bool:
        if FULL_SHA.fullmatch(sha) is None:
            return False
        return self._git(("cat-file", "-e", f"{sha}^{{commit}}"), check=False).returncode == 0

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        if not (self.git_object_exists(ancestor) and self.git_object_exists(descendant)):
            return False
        return (
            self._git(("merge-base", "--is-ancestor", ancestor, descendant)).returncode
            == 0
        )

    def current_target_sha(self) -> str:
        if not self.verify_git_objects:
            snapshot = self.github_snapshot()
            value = snapshot.get("target_sha")
            return value if isinstance(value, str) and FULL_SHA.fullmatch(value) else self.baseline_sha
        candidates = (
            f"refs/remotes/origin/{self.target_branch}",
            f"refs/heads/{self.target_branch}",
        )
        for reference in candidates:
            completed = self._git(("rev-parse", "--verify", reference))
            value = completed.stdout.strip()
            if completed.returncode == 0 and FULL_SHA.fullmatch(value):
                return value
        raise AutopilotError(
            f"cannot resolve target branch {self.target_branch!r}; fetch it before dispatch"
        )

    def reconciled_target_sha(self) -> str:
        path = self.state_dir / "target.json"
        if not path.is_file():
            return self.baseline_sha
        value = read_json(path)
        if not isinstance(value, Mapping):
            raise ConfigurationError("state target record must be an object")
        sha = value.get("target_sha")
        if not isinstance(sha, str) or FULL_SHA.fullmatch(sha) is None:
            raise ConfigurationError("state target record has an invalid SHA")
        return sha

    def target_requires_reconciliation(self) -> bool:
        return self.current_target_sha() != self.reconciled_target_sha()

    def changed_paths_since_reconciliation(self) -> tuple[str, ...]:
        current = self.current_target_sha()
        prior = self.reconciled_target_sha()
        if current == prior or not self.verify_git_objects:
            return ()
        if not self.is_ancestor(prior, current):
            return ("<target-history-diverged>",)
        completed = self._git(("diff", "--name-only", f"{prior}..{current}"), check=True)
        return tuple(
            sorted(
                {
                    normalize_path(line)
                    for line in completed.stdout.splitlines()
                    if line.strip()
                }
            )
        )

    def github_snapshot(self) -> Mapping[str, Any]:
        path = self.state_dir / "github-state.json"
        if not path.is_file():
            return {}
        value = read_json(path)
        if not isinstance(value, Mapping):
            raise ConfigurationError("github-state snapshot must be an object")
        return value

    def github_pr_for_node(self, node_id: str) -> Mapping[str, Any] | None:
        prs = self.github_snapshot().get("pull_requests", [])
        if not isinstance(prs, list):
            return None
        for item in prs:
            if isinstance(item, Mapping) and item.get("node_id") == node_id:
                return item
        return None

    def branch_snapshot(self, branch: str) -> Mapping[str, Any] | None:
        branches = self.github_snapshot().get("branches", [])
        if not isinstance(branches, list):
            return None
        for item in branches:
            if isinstance(item, Mapping) and item.get("name") == branch:
                return item
        return None

    def remote_branch_sha(self, branch: str, *, remote: str = "origin") -> str | None:
        if remote != "origin":
            raise ClaimError("only the configured canonical remote name 'origin' is allowed")
        completed = self._git(
            ("ls-remote", "--heads", remote, f"refs/heads/{branch}"),
            check=False,
        )
        if completed.returncode != 0:
            raise ClaimError(
                f"cannot inspect remote {remote!r}: {completed.stderr.strip()}"
            )
        fields = completed.stdout.strip().split()
        if not fields:
            return None
        sha = fields[0]
        if FULL_SHA.fullmatch(sha) is None:
            raise ClaimError("remote branch returned an invalid commit identity")
        return sha

    def publish_remote_claim(
        self,
        node_id: str,
        owner: str,
        expires_at: str,
        *,
        remote: str = "origin",
    ) -> str:
        if remote != "origin":
            raise ClaimError("only the configured canonical remote name 'origin' is allowed")
        node = self.node(node_id)
        branch = str(node.get("branch"))
        if self.remote_branch_sha(branch, remote=remote) is not None:
            raise ClaimError(
                f"remote branch {branch!r} already exists; reconcile it before claiming"
            )
        target = self.current_target_sha()
        tree = self._git(("rev-parse", f"{target}^{{tree}}"), check=True).stdout.strip()
        message = json.dumps(
            {
                "kind": "hive-mind-autopilot-remote-claim-v1",
                "node_id": node_id,
                "owner": owner,
                "expires_at": expires_at,
                "plan_fingerprint": self.expected_plan_fingerprint,
                "target_sha": target,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        created = self._git(
            (
                "-c",
                "user.name=Hive Mind Autopilot Claim",
                "-c",
                "user.email=autopilot-claim@hive-mind.invalid",
                "commit-tree",
                tree,
                "-p",
                target,
                "-m",
                message,
            ),
            check=True,
            environment={
                "GIT_AUTHOR_NAME": "Hive Mind Autopilot Claim",
                "GIT_AUTHOR_EMAIL": "autopilot-claim@hive-mind.invalid",
                "GIT_COMMITTER_NAME": "Hive Mind Autopilot Claim",
                "GIT_COMMITTER_EMAIL": "autopilot-claim@hive-mind.invalid",
            },
        ).stdout.strip()
        if FULL_SHA.fullmatch(created) is None:
            raise ClaimError("failed to create a remote claim commit")
        pushed = self._git(
            ("push", remote, f"{created}:refs/heads/{branch}"),
            check=False,
        )
        if pushed.returncode != 0:
            raise ClaimError(
                "remote claim race or push failure: " + pushed.stderr.strip()
            )
        observed = self.remote_branch_sha(branch, remote=remote)
        if observed != created:
            raise ClaimError("remote claim branch does not bind the created claim commit")
        return created

    def release_remote_claim(
        self,
        node_id: str,
        claim_commit: str,
        *,
        remote: str = "origin",
    ) -> None:
        if remote != "origin":
            raise ClaimError("only the configured canonical remote name 'origin' is allowed")
        branch = str(self.node(node_id).get("branch"))
        observed = self.remote_branch_sha(branch, remote=remote)
        if observed is None:
            return
        if observed != claim_commit:
            # The worker has advanced the implementation branch; never delete it.
            return
        deleted = self._git(
            ("push", remote, f":refs/heads/{branch}"),
            check=False,
        )
        if deleted.returncode != 0:
            raise ClaimError(
                "failed to release untouched remote claim branch: "
                + deleted.stderr.strip()
            )

    def remote_claim_record(self, commit: str) -> Mapping[str, Any] | None:
        """Return the self-attesting claim record a claim commit carries, if any."""

        shown = self._git(("show", "-s", "--format=%B", commit), check=False)
        if shown.returncode != 0:
            return None
        try:
            value = json.loads(shown.stdout.strip())
        except json.JSONDecodeError:
            return None
        if not isinstance(value, Mapping):
            return None
        if value.get("kind") != "hive-mind-autopilot-remote-claim-v1":
            return None
        return value

    def reap_stale_remote_claim(
        self,
        node_id: str,
        owner: str,
        *,
        reason: str,
        remote: str = "origin",
    ) -> Mapping[str, Any]:
        """Delete an expired remote claim ref whose branch carries no published work.

        ``release`` can only reach a claim whose local file still exists, and claim
        state is session-local by design, so a worker session that ends leaves a
        remote claim ref no later session can retire — permanently wedging the node
        against ``publish_remote_claim``.  The claim commit is itself the record:
        identity is read back from the remote object, and the ref is deleted only
        while the branch still carries nothing except that claim.  A live claim is
        never reaped; it is the only real cross-session mutex.
        """

        if remote != "origin":
            raise ClaimError("only the configured canonical remote name 'origin' is allowed")
        if not owner.strip():
            raise ClaimError("stale remote claim release requires the exact claim owner")
        branch = str(self.node(node_id).get("branch"))
        head = self.remote_branch_sha(branch, remote=remote)
        if head is None:
            return {"node_id": node_id, "branch": branch, "outcome": "absent"}
        fetched = self._git(
            ("fetch", remote, f"refs/heads/{branch}"),
            check=False,
        )
        if fetched.returncode != 0:
            raise ClaimError(
                f"cannot inspect remote claim branch {branch!r}: {fetched.stderr.strip()}"
            )
        record = self.remote_claim_record(head)
        if record is None:
            raise ClaimError(
                f"remote branch {branch!r} head is not a claim commit; it carries "
                "published work and must be reconciled, never deleted"
            )
        if record.get("node_id") != node_id:
            raise ClaimError("remote claim identifies a different node")
        if record.get("owner") != owner:
            raise ClaimError("claim owner does not match")
        parents = self._git(
            ("rev-list", "--parents", "-n", "1", head), check=True
        ).stdout.split()
        if len(parents) != 2:
            raise ClaimError("claim commit must have exactly one parent")
        claim_tree = self._git(("rev-parse", f"{head}^{{tree}}"), check=True).stdout.strip()
        parent_tree = self._git(("rev-parse", f"{head}^^{{tree}}"), check=True).stdout.strip()
        if claim_tree != parent_tree:
            raise ClaimError(
                "claim commit changes the target tree; it is not an untouched claim"
            )
        expires_at = record.get("expires_at")
        try:
            expires = parse_time(expires_at)
        except (TypeError, ValueError) as error:
            raise ClaimError("claim record has no readable expiry") from error
        now = self.clock()
        if expires > now:
            raise ClaimError(
                f"claim on {branch!r} is live until {expires_at}; a live claim is the "
                "only cross-session mutex and is never reaped"
            )
        deleted = self._git(
            ("push", remote, f":refs/heads/{branch}"),
            check=False,
        )
        if deleted.returncode != 0:
            raise ClaimError(
                "failed to retire stale remote claim branch: " + deleted.stderr.strip()
            )
        released = {
            "node_id": node_id,
            "branch": branch,
            "owner": owner,
            "reason": reason,
            "claim_commit": head,
            "expired_at": expires_at,
            "released_at": format_time(now),
            "outcome": "retired",
        }
        append_jsonl(self.state_dir / "releases.jsonl", released)
        return released

    # ------------------------------------------------------------- self-healing

    def _remote_ref_sha(self, ref: str, *, remote: str = "origin") -> str | None:
        if remote != "origin":
            raise ClaimError("only the configured canonical remote name 'origin' is allowed")
        completed = self._git(("ls-remote", remote, ref), check=False)
        if completed.returncode != 0:
            raise ClaimError(f"cannot inspect remote ref {ref!r}: {completed.stderr.strip()}")
        fields = completed.stdout.strip().split()
        if not fields:
            return None
        sha = fields[0]
        if FULL_SHA.fullmatch(sha) is None:
            raise ClaimError("remote ref returned an invalid commit identity")
        return sha

    def _commit_time(self, sha: str) -> datetime:
        shown = self._git(("show", "-s", "--format=%ct", sha), check=True).stdout.strip()
        return datetime.fromtimestamp(int(shown), UTC)

    def defunct_remote_claim_proof(
        self, record: Mapping[str, Any]
    ) -> Mapping[str, Any] | None:
        """Return proof that a remote claim can no longer protect integrable work.

        The remote claim is the only cross-session mutex, but a mutex exists to
        protect work that could still become an integrable receipt. Each fact
        below alone forecloses that possibility, and each is read from durable
        evidence rather than any session's memory:

        - ``expired``: the lease bound the owner itself asked for has lapsed;
        - ``unreadable-expiry``: the record carries no bound at all, so no
          session could ever prove it lapsed;
        - ``plan-superseded``: the claim binds a plan fingerprint this plane no
          longer executes, so no receipt under it can ever validate.

        A stale ``target_sha`` is deliberately NOT proof: the round driver
        integrates sealed heads rooted at a round's original target after
        siblings advance it, so a claim bound to an older target may still
        complete.  Dead-but-live-TTL claims are instead retired through the
        stall bound in ``reap_defunct_remote_claim``.
        """

        now = self.clock()
        try:
            expires = parse_time(record.get("expires_at"))
        except (TypeError, ValueError):
            return {"kind": "unreadable-expiry", "observed_at": format_time(now)}
        if expires <= now:
            return {
                "kind": "expired",
                "expired_at": str(record.get("expires_at")),
                "observed_at": format_time(now),
            }
        current_fingerprint = self._target_plan_fingerprint()
        if record.get("plan_fingerprint") != current_fingerprint:
            return {
                "kind": "plan-superseded",
                "claim_plan_fingerprint": str(record.get("plan_fingerprint")),
                "current_plan_fingerprint": current_fingerprint,
                "observed_at": format_time(now),
            }
        return None

    def _target_plan_fingerprint(self) -> str:
        """Read the executing plan's fingerprint from the target commit itself.

        A supersession proof must come from durable evidence: a session whose
        local checkout is behind would otherwise read a stale local plan and
        reap every live claim of the CURRENT plan.  The fetched target commit
        is the durable record; the local file is only the fallback when git
        objects are not verifiable (fixtures) or the file is absent there.
        """

        if self.verify_git_objects:
            target_sha = self.current_target_sha()
            try:
                shown_control = self._git(
                    ("show", f"{target_sha}:.autopilot/control-plane.json"),
                    check=False,
                )
                shown_plan = self._git(
                    ("show", f"{target_sha}:.autopilot/plan.json"),
                    check=False,
                )
            except AutopilotError as error:
                raise ClaimError(
                    "cannot authenticate the target plan for claim supersession"
                ) from error
            if shown_control.returncode != 0 or shown_plan.returncode != 0:
                raise ClaimError(
                    "target commit lacks authenticated control/plan evidence"
                )
            try:
                control = parse_strict_canonical_json_bytes(
                    shown_control.stdout.encode("utf-8"),
                    label="target control plane",
                    expected_fields=set(self.control),
                )
                plan = parse_strict_canonical_json_bytes(
                    shown_plan.stdout.encode("utf-8"),
                    label="target execution plan",
                    expected_fields=set(self.plan),
                )
            except ConfigurationError as error:
                raise ClaimError(
                    "target plan cannot justify destructive claim supersession: "
                    + str(error)
                ) from error
            if not isinstance(control, Mapping) or not isinstance(plan, Mapping):
                raise ClaimError("target plan authority is malformed")
            material = dict(plan)
            embedded = material.pop("plan_fingerprint", None)
            computed = digest_json(material)
            if (
                embedded != computed
                or control.get("plan_fingerprint") != computed
                or control.get("plan_id") != plan.get("plan_id")
            ):
                raise ClaimError(
                    "target control and plan fingerprints do not authenticate each other"
                )
            return computed
        return self.expected_plan_fingerprint

    def reap_defunct_remote_claim(
        self,
        node_id: str,
        *,
        actor: str,
        reason: str,
        stall_minutes: int | None = None,
        remote: str = "origin",
    ) -> Mapping[str, Any]:
        """Retire a remote claim that provably cannot protect integrable work.

        ``reap_stale_remote_claim`` retires only expired claims and requires the
        caller to already know the owner.  This verb reads the owner from the
        claim record itself and also retires claims carrying any
        ``defunct_remote_claim_proof``.  With ``stall_minutes`` it additionally
        retires a live, current claim whose branch never received a single work
        commit within that window — the signature of a worker session that died
        after claiming, which would otherwise wedge the node until TTL.
        The deletion is guarded by ``--force-with-lease`` so a worker pushing
        work at the same moment wins the race, and the retirement is appended to
        ``releases.jsonl`` together with the proof that justified it.
        """

        if remote != "origin":
            raise ClaimError("only the configured canonical remote name 'origin' is allowed")
        if not actor.strip():
            raise ClaimError("defunct claim retirement requires the acting identity")
        branch = str(self.node(node_id).get("branch"))
        head = self.remote_branch_sha(branch, remote=remote)
        if head is None:
            return {"node_id": node_id, "branch": branch, "outcome": "absent"}
        fetched = self._git(("fetch", remote, f"refs/heads/{branch}"), check=False)
        if fetched.returncode != 0:
            raise ClaimError(
                f"cannot inspect remote claim branch {branch!r}: {fetched.stderr.strip()}"
            )
        record = self.remote_claim_record(head)
        if record is None:
            raise ClaimError(
                f"remote branch {branch!r} head is not a claim commit; it carries "
                "published work and must be reconciled or quarantined, never deleted"
            )
        if record.get("node_id") != node_id:
            raise ClaimError("remote claim identifies a different node")
        parents = self._git(
            ("rev-list", "--parents", "-n", "1", head), check=True
        ).stdout.split()
        if len(parents) != 2:
            raise ClaimError("claim commit must have exactly one parent")
        claim_tree = self._git(("rev-parse", f"{head}^{{tree}}"), check=True).stdout.strip()
        parent_tree = self._git(("rev-parse", f"{head}^^{{tree}}"), check=True).stdout.strip()
        if claim_tree != parent_tree:
            raise ClaimError(
                "claim commit changes the target tree; it is not an untouched claim"
            )
        proof = self.defunct_remote_claim_proof(record)
        if proof is None and stall_minutes is not None:
            if type(stall_minutes) is not int or stall_minutes < 1:
                raise ClaimError("stall_minutes must be a positive integer")
            claimed_at = self._commit_time(head)
            now = self.clock()
            idle = now - claimed_at
            if idle >= timedelta(minutes=stall_minutes):
                proof = {
                    "kind": "stalled-bare-claim",
                    "claimed_at": format_time(claimed_at),
                    "idle_minutes": int(idle.total_seconds() // 60),
                    "stall_minutes": stall_minutes,
                    "observed_at": format_time(now),
                }
        if proof is None:
            raise ClaimError(
                f"claim on {branch!r} is live until {record.get('expires_at')} with a "
                "current target and plan; it may still protect integrable work"
            )
        deleted = self._git(
            (
                "push",
                f"--force-with-lease=refs/heads/{branch}:{head}",
                remote,
                f":refs/heads/{branch}",
            ),
            check=False,
        )
        if deleted.returncode != 0:
            raise ClaimError(
                "failed to retire defunct remote claim branch (a worker may have "
                "pushed work at the same moment): " + deleted.stderr.strip()
            )
        released = {
            "node_id": node_id,
            "branch": branch,
            "owner": str(record.get("owner")),
            "actor": actor,
            "reason": reason,
            "claim_commit": head,
            "proof": dict(proof),
            "released_at": format_time(self.clock()),
            "outcome": "retired-defunct",
        }
        append_jsonl(self.state_dir / "releases.jsonl", released)
        return released

    def quarantine_defunct_remote_branch(
        self,
        node_id: str,
        *,
        actor: str,
        reason: str,
        stall_minutes: int = 45,
        remote: str = "origin",
    ) -> Mapping[str, Any]:
        """Archive a dead worker's unsealed work and free the node branch.

        Published work is never deleted, but an unsealed branch whose governing
        claim is expired, superseded, or absent — and whose head has not moved
        within ``stall_minutes`` — blocks every lawful re-claim while no worker
        can still complete it.  The head is preserved verbatim under
        ``refs/hive-mind-autopilot/quarantine/<node>/<sha>`` and the branch ref
        is retired in the same atomic push, each side guarded by
        ``--force-with-lease`` so a worker pushing at the same moment wins.
        """

        if remote != "origin":
            raise ClaimError("only the configured canonical remote name 'origin' is allowed")
        if not actor.strip():
            raise ClaimError("branch quarantine requires the acting identity")
        if type(stall_minutes) is not int or stall_minutes < 1:
            raise ClaimError("stall_minutes must be a positive integer")
        branch = str(self.node(node_id).get("branch"))
        head = self.remote_branch_sha(branch, remote=remote)
        if head is None:
            return {"node_id": node_id, "branch": branch, "outcome": "absent"}
        fetched = self._git(("fetch", remote, f"refs/heads/{branch}"), check=False)
        if fetched.returncode != 0:
            raise ClaimError(
                f"cannot inspect remote branch {branch!r}: {fetched.stderr.strip()}"
            )
        author = self._git(("show", "-s", "--format=%ae", head), check=True).stdout.strip()
        if author == RECEIPT_COMMIT_EMAIL:
            raise ClaimError(
                f"remote branch {branch!r} head is a sealed receipt; it must be "
                "integrated, never quarantined"
            )
        if self.remote_claim_record(head) is not None:
            raise ClaimError(
                f"remote branch {branch!r} head is an untouched claim; retire it "
                "through reap_defunct_remote_claim instead"
            )
        now = self.clock()
        moved_at = self._commit_time(head)
        idle = now - moved_at
        if idle < timedelta(minutes=stall_minutes):
            raise ClaimError(
                f"remote branch {branch!r} moved {int(idle.total_seconds() // 60)} "
                f"minutes ago; a worker may still be publishing (stall bound is "
                f"{stall_minutes} minutes)"
            )
        governing = self._governing_claim_record(node_id, head)
        claim_proof: Mapping[str, Any] | None
        if governing is None:
            claim_proof = {"kind": "no-governing-claim", "observed_at": format_time(now)}
        else:
            claim_proof = self.defunct_remote_claim_proof(governing)
            if claim_proof is None:
                raise ClaimError(
                    f"remote branch {branch!r} is governed by a live claim with a "
                    "current target and plan; wait for its lease to resolve"
                )
        quarantine_ref = (
            f"refs/hive-mind-autopilot/quarantine/{node_id.lower()}/{head}"
        )
        if self._remote_ref_sha(quarantine_ref, remote=remote) is None:
            archived = self._git(
                (
                    "push",
                    "--atomic",
                    f"--force-with-lease={quarantine_ref}:",
                    f"--force-with-lease=refs/heads/{branch}:{head}",
                    remote,
                    f"{head}:{quarantine_ref}",
                    f":refs/heads/{branch}",
                ),
                check=False,
            )
        else:
            # The archive ref already binds this exact head (a previous attempt
            # crashed between archive and retire); only the retirement remains.
            archived = self._git(
                (
                    "push",
                    f"--force-with-lease=refs/heads/{branch}:{head}",
                    remote,
                    f":refs/heads/{branch}",
                ),
                check=False,
            )
        if archived.returncode != 0:
            raise ClaimError(
                "failed to quarantine defunct remote branch (a worker may have "
                "pushed at the same moment): " + archived.stderr.strip()
            )
        if self._remote_ref_sha(quarantine_ref, remote=remote) != head:
            raise ClaimError("quarantine archive ref does not bind the retired head")
        quarantined = {
            "node_id": node_id,
            "branch": branch,
            "head": head,
            "quarantine_ref": quarantine_ref,
            "actor": actor,
            "reason": reason,
            "claim_proof": dict(claim_proof),
            "head_moved_at": format_time(moved_at),
            "idle_minutes": int(idle.total_seconds() // 60),
            "quarantined_at": format_time(now),
            "outcome": "quarantined",
        }
        append_jsonl(self.state_dir / "quarantines.jsonl", quarantined)
        return quarantined

    def _governing_claim_record(self, node_id: str, head: str) -> Mapping[str, Any] | None:
        """Return the claim record governing this branch's unintegrated work.

        Mainline already carries the claim commits of every completed node —
        integration merges them along with the receipts — so the walk must
        exclude everything reachable from the current target: an integrated
        claim belongs to finished history and can never govern live work.
        Among what remains, only a claim naming this exact node counts, and
        the newest one wins (a re-claim supersedes its predecessors).
        """

        exclusions: list[tuple[str, ...]] = []
        try:
            exclusions.append((f"^{self.current_target_sha()}",))
        except AutopilotError:
            pass
        exclusions.append(())  # the target may be unfetchable; never fail closed here
        for exclusion in exclusions:
            listed = self._git(
                ("log", "--format=%H %ae", "--author", CLAIM_COMMIT_EMAIL, head)
                + exclusion,
                check=False,
            )
            if listed.returncode != 0:
                continue
            for line in listed.stdout.strip().splitlines():  # newest first
                if not line.strip():
                    continue
                record = self.remote_claim_record(line.split()[0])
                if record is not None and record.get("node_id") == node_id:
                    return record
            return None
        return None

    def _blocker_ledger(self, node_id: str) -> dict[str, bool]:
        """Map each recorded blocker id to whether a resolution event covers it."""

        path = self.blockers_dir / f"{node_id}.jsonl"
        opened: dict[str, bool] = {}
        for record in strict_jsonl_records(path, label="blocker ledger"):
            blocker_id = record.get("blocker_id")
            if not isinstance(blocker_id, str) or AUTHORITY_ID.fullmatch(
                blocker_id
            ) is None:
                raise ConfigurationError("blocker ledger has an invalid blocker id")
            if record.get("event") == "BLOCKER_RESOLVED":
                opened[blocker_id] = True
            elif record.get("status") == "OPEN":
                opened.setdefault(blocker_id, False)
        return opened

    def unresolved_blockers(self, node_id: str) -> tuple[str, ...]:
        """Return the blocker ids still OPEN without a BLOCKER_RESOLVED event."""

        ledger = self._blocker_ledger(node_id)
        return tuple(sorted(bid for bid, resolved in ledger.items() if not resolved))

    def blockers_fully_resolved(self, node_id: str) -> bool:
        """True when the ledger names at least one cause and every one has a fix.

        An empty or unparseable ledger is NOT fully resolved: nothing was
        provably fixed, so triage must still look at what is there.
        """

        ledger = self._blocker_ledger(node_id)
        return bool(ledger) and all(ledger.values())

    def lift_retry_quarantine(self, node_id: str, *, actor: str) -> Mapping[str, Any] | None:
        """Reopen a spent retry budget after every recorded cause has a fix.

        Quarantine-by-budget protects against blind retry loops, not against
        ever retrying: each failure wrote a blocker naming its exact cause, and
        the lawful way back is a ``BLOCKER_RESOLVED`` event for every one of
        them, each carrying a verified fix and a safe retry command.  When that
        proof is complete, this verb archives the spent failure ledger together
        with the quarantine and escalation records into one recovery document —
        nothing is deleted — and the node becomes dispatchable again with its
        budget reset for the corrected cause.  Returns None when the node is
        not quarantined.
        """

        if not actor.strip():
            raise AutopilotError("lifting a retry quarantine requires the acting identity")
        quarantine_path = self.quarantine_dir / f"{node_id}.json"
        if not quarantine_path.is_file():
            return None
        if not self.blockers_fully_resolved(node_id):
            # An empty or unparseable ledger is NOT proof: the quarantine was
            # earned by real failures, so lifting it needs at least one named
            # cause and a resolution for every one of them.
            unresolved = self.unresolved_blockers(node_id)
            raise AutopilotError(
                "retry quarantine stands while blockers remain unresolved: "
                + (
                    ", ".join(unresolved)
                    if unresolved
                    else "the blocker ledger names no resolvable causes"
                )
            )
        now = self.clock()
        failures_path = self.failures_dir / f"{node_id}.jsonl"
        escalation_path = self.escalations_dir / f"{node_id}.json"
        recovery = {
            "schema_version": SCHEMA_VERSION,
            "kind": "hive-mind-autopilot-retry-quarantine-lift-v1",
            "node_id": node_id,
            "actor": actor,
            "lifted_at": format_time(now),
            "quarantine": read_json(quarantine_path),
            "escalation": read_json(escalation_path) if escalation_path.is_file() else None,
            "failures": list(self.failures(node_id)),
            "plan_fingerprint": self.expected_plan_fingerprint,
        }
        recovery["recovery_id"] = digest_json(recovery)
        archive = (
            self.state_dir
            / "recoveries"
            / f"{node_id}-{format_time(now).replace(':', '-')}.json"
        )
        atomic_write_json(archive, recovery)
        quarantine_path.unlink()
        if escalation_path.is_file():
            escalation_path.unlink()
        if failures_path.is_file():
            failures_path.unlink()
        append_jsonl(
            self.state_dir / "recoveries.jsonl",
            {
                "recovery_id": recovery["recovery_id"],
                "node_id": node_id,
                "actor": actor,
                "lifted_at": recovery["lifted_at"],
                "archive": str(archive.relative_to(self.state_dir)),
            },
        )
        return recovery

    def resolve_escalation(self, node_id: str, *, actor: str) -> Mapping[str, Any] | None:
        """Retire an escalation packet after every recorded cause has a fix.

        An escalation preserves a packet so a human decides before the node
        moves again, and that packet is not tied to the retry budget: a node
        can escalate on its first failure and never earn a quarantine, so
        ``lift_retry_quarantine`` — the only other verb that clears a packet —
        never runs and the escalation outlives every blocker it named.  This
        verb is the lawful way back, and it demands the same proof the
        quarantine lift demands: a ``BLOCKER_RESOLVED`` event for every blocker
        the node recorded, each carrying a verified fix.  When that proof is
        complete it archives the escalation record together with the failure
        ledger into one recovery document — nothing is deleted — and retires
        the packet so the node stops reporting ``ESCALATION_REQUIRED``.  The
        failure ledger and any retry quarantine are left exactly as they were:
        this clears the escalation and nothing else.  Returns None when the
        node holds no escalation packet.

        Resolution is also independent: the identity recorded as the packet's
        ``owner`` may not be the identity that clears it.  A resolved blocker
        proves only that a fix was *claimed*, and the claim is worth nothing
        when the party that failed is the same party that certifies itself
        cleared.  This is the invariant the court refuses a judge listed in
        ``affected_identities`` for, and the one promotion enforces by
        requiring distinct proposer, builder, evaluator, and judge — applied
        here to escalation.
        """

        if not actor.strip():
            raise AutopilotError("resolving an escalation requires the acting identity")
        escalation_path = self.escalations_dir / f"{node_id}.json"
        if not escalation_path.is_file():
            return None
        # Read once: the identity the check runs against and the record the
        # archive preserves must be the same bytes.
        escalation = read_json(escalation_path)
        owner = escalation.get("owner") if isinstance(escalation, Mapping) else None
        # Surrounding whitespace never makes a second identity: ``actor`` is
        # validated with ``strip`` above, so compare on the same footing.
        if isinstance(owner, str) and owner.strip() == actor.strip():
            raise AutopilotError(
                "the identity that escalated may not clear the escalation: "
                f"actor {actor} matches the escalating owner {owner} on {node_id}"
            )
        if not self.blockers_fully_resolved(node_id):
            # An empty or unparseable ledger is NOT proof: a worker deliberately
            # preserved this packet, so retiring it needs at least one named
            # cause and a resolution for every one of them.
            unresolved = self.unresolved_blockers(node_id)
            raise AutopilotError(
                "escalation stands while blockers remain unresolved: "
                + (
                    ", ".join(unresolved)
                    if unresolved
                    else "the blocker ledger names no resolvable causes"
                )
            )
        now = self.clock()
        quarantine_path = self.quarantine_dir / f"{node_id}.json"
        recovery = {
            "schema_version": SCHEMA_VERSION,
            "kind": "hive-mind-autopilot-escalation-resolution-v1",
            "node_id": node_id,
            "actor": actor,
            "lifted_at": format_time(now),
            "escalation": escalation,
            "quarantine": read_json(quarantine_path) if quarantine_path.is_file() else None,
            "failures": list(self.failures(node_id)),
            "plan_fingerprint": self.expected_plan_fingerprint,
        }
        recovery["recovery_id"] = digest_json(recovery)
        # The distinct suffix keeps this archive from ever landing on the name a
        # quarantine lift would choose for the same node at the same instant.
        archive = (
            self.state_dir
            / "recoveries"
            / f"{node_id}-{format_time(now).replace(':', '-')}-escalation.json"
        )
        atomic_write_json(archive, recovery)
        escalation_path.unlink()
        append_jsonl(
            self.state_dir / "recoveries.jsonl",
            {
                "recovery_id": recovery["recovery_id"],
                "node_id": node_id,
                "actor": actor,
                "lifted_at": recovery["lifted_at"],
                "archive": str(archive.relative_to(self.state_dir)),
            },
        )
        return recovery

    def claim_path(self, node_id: str) -> Path:
        target = _require_mapping(self.control.get("target"), "control-plane.target")
        repository = _require_nonempty_text(
            target.get("repository"), "target.repository"
        )
        key = digest_json(
            {
                "kind": "hive-mind-claim-file-key-v1",
                "repository": repository,
                "execution_id": self.execution_id,
                "node_id": node_id,
            }
        ).removeprefix("sha256:")
        return self.claims_dir / f"{key}.json"

    def receipt_path(self, node_id: str) -> Path:
        return self.receipts_dir / f"{node_id}.json"

    def active_claims(self) -> dict[str, Mapping[str, Any]]:
        claims: dict[str, Mapping[str, Any]] = {}
        claim_lock = self.arbiter_dir / "locks" / "claim-authority.lock"
        identity = self.coordination_dir / "runtime-identity.json"
        initialized = claim_lock.is_file() and identity.is_file()
        if self.claims_dir.exists() or _is_link_like(self.claims_dir):
            _reject_link_components(
                self.claims_dir,
                label="claim authority directory",
            )
        paths = (
            sorted(self.claims_dir.glob("*.json"))
            if self.claims_dir.is_dir()
            else []
        )
        if not initialized and not paths:
            return claims
        with self.runtime_read_lock("claim-authority.lock", timeout_seconds=120.0):
            if not self.claims_dir.is_dir():
                return claims
            _reject_link_components(
                self.claims_dir,
                label="claim authority directory",
            )
            now = self.clock()
            for path in sorted(self.claims_dir.glob("*.json")):
                value, expires, _raw = read_claim_authority_file(path)
                if expires <= now:
                    continue
                node_id = str(value["node_id"])
                if value.get("execution_id") != self.execution_id:
                    continue
                if node_id in claims:
                    raise ConfigurationError(
                        f"duplicate live claim authority for node {node_id}"
                    )
                claims[node_id] = value
        return claims

    def _claim_authority_status(
        self,
        claims: Mapping[str, Mapping[str, Any]],
    ) -> tuple[list[Mapping[str, object]], list[Mapping[str, object]]]:
        """Classify ambiguous claims and hosted claims whose launch is fenced."""

        stale_hosted: list[Mapping[str, object]] = []
        unclassified: list[Mapping[str, object]] = []
        for node_id, claim in sorted(claims.items()):
            authority_class = claim.get("claim_authority_class")
            coordinates = {
                "launch_instruction_id": claim.get("launch_instruction_id"),
                "resource_key": claim.get("resource_key"),
                "authority_epoch": claim.get("authority_epoch"),
            }
            summary = {
                "node_id": node_id,
                "claim_id": claim.get("claim_id"),
                "claim_authority_class": authority_class,
                **coordinates,
            }
            if authority_class == INTERNAL_CLAIM_AUTHORITY:
                if any(value is not None for value in coordinates.values()):
                    unclassified.append({**summary, "reason": "INTERNAL_CLAIM_HAS_HOST_FENCE"})
                continue
            if authority_class != HOSTED_CLAIM_AUTHORITY:
                unclassified.append({**summary, "reason": "CLAIM_AUTHORITY_UNCLASSIFIED"})
                continue
            instruction = coordinates["launch_instruction_id"]
            resource = coordinates["resource_key"]
            epoch = coordinates["authority_epoch"]
            try:
                if (
                    not isinstance(instruction, str)
                    or not isinstance(resource, str)
                    or type(epoch) is not int
                ):
                    raise ClaimError("hosted claim fence is incomplete")
                from orchestration import assert_launch_authority

                binding = assert_launch_authority(
                    self.repo_root,
                    instruction,
                    resource_key=resource,
                    authority_epoch=epoch,
                    state_dir=self.execution_dir,
                )
                if binding.get("node_id") != node_id:
                    raise ClaimError("hosted claim node differs from launch binding")
            except Exception as error:
                stale_hosted.append(
                    {
                        **summary,
                        "reason": "HOSTED_LAUNCH_STALE_OR_REVOKED",
                        "detail": str(error),
                    }
                )
        return stale_hosted, unclassified

    def _validation_authority_status(
        self,
        lease: Mapping[str, Any] | None,
        claims: Mapping[str, Mapping[str, Any]],
    ) -> tuple[list[Mapping[str, object]], list[Mapping[str, object]]]:
        """Classify one live validation lease against its claim and launch."""

        if lease is None:
            return [], []
        authority_class = lease.get("claim_authority_class")
        node_id = lease.get("node_id")
        coordinates = {
            "claim_id": lease.get("claim_id"),
            "launch_instruction_id": lease.get("launch_instruction_id"),
            "resource_key": lease.get("resource_key"),
            "authority_epoch": lease.get("authority_epoch"),
        }
        summary = {
            "node_id": node_id,
            "owner": lease.get("owner"),
            "lease_id": lease.get("lease_id"),
            "claim_authority_class": authority_class,
            **coordinates,
        }
        if authority_class == INTERNAL_CLAIM_AUTHORITY:
            if any(value is not None for value in coordinates.values()):
                return [], [
                    {**summary, "reason": "INTERNAL_VALIDATION_LEASE_HAS_HOST_FENCE"}
                ]
            return [], []
        if authority_class != HOSTED_CLAIM_AUTHORITY or not isinstance(node_id, str):
            return [], [
                {**summary, "reason": "VALIDATION_LEASE_AUTHORITY_UNCLASSIFIED"}
            ]
        claim = claims.get(node_id)
        try:
            if claim is None:
                raise ClaimError("hosted validation lease has no live claim")
            if claim.get("owner") != lease.get("owner"):
                raise ClaimError("hosted validation lease owner differs from claim")
            for field, expected in coordinates.items():
                if claim.get(field) != expected:
                    raise ClaimError(
                        f"hosted validation lease {field} differs from live claim"
                    )
            instruction = coordinates["launch_instruction_id"]
            resource = coordinates["resource_key"]
            epoch = coordinates["authority_epoch"]
            if (
                not isinstance(instruction, str)
                or not isinstance(resource, str)
                or type(epoch) is not int
            ):
                raise ClaimError("hosted validation lease launch fence is incomplete")
            from orchestration import assert_launch_authority

            binding = assert_launch_authority(
                self.repo_root,
                instruction,
                resource_key=resource,
                authority_epoch=epoch,
                state_dir=self.execution_dir,
            )
            if binding.get("node_id") != node_id:
                raise ClaimError("hosted validation lease node differs from launch")
        except Exception as error:
            return [
                {
                    **summary,
                    "reason": "HOSTED_VALIDATION_AUTHORITY_STALE_OR_REVOKED",
                    "detail": str(error),
                }
            ], []
        return [], []

    def clean_stale_claims(self) -> tuple[str, ...]:
        with self.runtime_lock("claim-authority.lock", timeout_seconds=120.0):
            return self._clean_stale_claims_unlocked()

    def _clean_stale_claims_unlocked(self) -> tuple[str, ...]:
        removed: list[str] = []
        if not self.claims_dir.is_dir():
            return ()
        _reject_link_components(self.claims_dir, label="claim authority directory")
        now = self.clock()
        for path in sorted(self.claims_dir.glob("*.json")):
            value, expires, raw = read_claim_authority_file(path)
            if expires <= now:
                claim_id = value.get("claim_id")
                archive_stem = (
                    claim_id.replace(":", "-")
                    if isinstance(claim_id, str) and AUTHORITY_ID.fullmatch(claim_id)
                    else "sha256-" + sha256(raw).hexdigest()
                )
                archive_file_without_overwrite(
                    path,
                    self.coordination_dir / "stale-claims",
                    archive_stem,
                )
                removed.append(str(value["node_id"]))
        return tuple(removed)

    def failures(self, node_id: str) -> tuple[Mapping[str, Any], ...]:
        path = self.failures_dir / f"{node_id}.jsonl"
        return strict_jsonl_records(path, label="failure ledger")

    def record_blocker(
        self,
        node_id: str,
        *,
        cause: str,
        fix: str,
        retry_when: str,
        attempted_command: Sequence[str] = (),
        category: str = "unknown",
        evidence_refs: Sequence[str] = (),
    ) -> Mapping[str, Any]:
        """Preserve an actionable blocker instead of emitting an opaque failure.

        A blocker is an operating-system learning record: it names the exact
        cause, the safe fix, and the condition that makes retry valid.  The
        append-only JSONL ledger is runtime state, while the protocol and its
        tests are repository code so future sessions cannot silently repeat the
        same failed attempt.
        """

        for value, label in (
            (cause, "cause"),
            (fix, "fix"),
            (retry_when, "retry_when"),
            (category, "category"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise AutopilotError(f"blocker {label} is required")
        command = [str(item) for item in attempted_command]
        packet_without_id = {
            "schema_version": SCHEMA_VERSION,
            "node_id": node_id,
            "category": category,
            "cause": cause,
            "fix": fix,
            "retry_when": retry_when,
            "attempted_command": command,
            "evidence_refs": [str(item) for item in evidence_refs],
            "plan_fingerprint": self.expected_plan_fingerprint,
            "timestamp": format_time(self.clock()),
            "status": "OPEN",
        }
        packet_without_id["recovery_action"] = self.recovery_action(packet_without_id)
        packet = {
            **packet_without_id,
            "blocker_id": digest_json(packet_without_id),
        }
        append_jsonl(self.blockers_dir / f"{node_id}.jsonl", packet)
        return packet

    def record_human_question(
        self,
        node_id: str,
        *,
        question: str,
        cause: str,
        attempted_command: Sequence[str] = (),
    ) -> Mapping[str, Any]:
        """Track a human question without persisting its potentially sensitive answer.

        Asking a human is a recoverable control-plane event, not a stopping point.
        The question is append-only; ``resolve_human_question`` records the answer
        digest, fix, and immediate retry action so the next run can resume itself.
        """

        for value, label in ((question, "question"), (cause, "cause")):
            if not isinstance(value, str) or not value.strip():
                raise AutopilotError(f"human question {label} is required")
        record = {
            "schema_version": SCHEMA_VERSION,
            "event": "QUESTION_OPENED",
            "node_id": node_id,
            "question": question,
            "cause": cause,
            "attempted_command": [str(item) for item in attempted_command],
            "plan_fingerprint": self.expected_plan_fingerprint,
            "timestamp": format_time(self.clock()),
            "status": "OPEN",
        }
        record["question_id"] = digest_json(record)
        append_jsonl(self.questions_dir / f"{node_id}.jsonl", record)
        return record

    def resolve_blocker(
        self,
        node_id: str,
        blocker_id: str,
        *,
        actor: str,
        fix: str,
        retry_command: Sequence[str],
        evidence_refs: Sequence[str] = (),
    ) -> Mapping[str, Any]:
        """Close one exact runtime blocker and make its verified retry actionable."""

        if not actor.strip() or not fix.strip() or not retry_command:
            raise AutopilotError("blocker resolution requires actor, fix, and retry command")
        path = self.blockers_dir / f"{node_id}.jsonl"
        records = strict_jsonl_records(path, label="blocker ledger")
        opened = next(
            (
                record
                for record in records
                if record.get("blocker_id") == blocker_id
                and record.get("status") == "OPEN"
            ),
            None,
        )
        if not isinstance(opened, Mapping):
            raise AutopilotError("blocker resolution must name an exact open blocker")
        if any(
            record.get("event") == "BLOCKER_RESOLVED"
            and record.get("blocker_id") == blocker_id
            for record in records
        ):
            raise AutopilotError("blocker is already resolved")
        normalized_retry = self.validate_retry_command(retry_command)
        candidate = {**opened, "fix": fix, "retry_when": "retry command is now executable"}
        if not self.safe_retry_allowed(candidate):
            raise AutopilotError("blocker resolution would weaken a security control")
        resolution = {
            "schema_version": SCHEMA_VERSION,
            "event": "BLOCKER_RESOLVED",
            "node_id": node_id,
            "blocker_id": blocker_id,
            "actor": actor,
            "fix": fix,
            "retry_command": list(normalized_retry),
            "evidence_refs": [str(item) for item in evidence_refs],
            "plan_fingerprint": self.expected_plan_fingerprint,
            "timestamp": format_time(self.clock()),
            "status": "RESOLVED",
            "recovery_action": {"action": "RETRY_NOW", "reason": "verified_fix_recorded"},
            "lesson": {
                "trigger_category": opened.get("category"),
                "policy": "spawn a bounded repair task, verify the fix, record the result, and resume the same task",
            },
        }
        resolution["resolution_id"] = digest_json(resolution)
        append_jsonl(path, resolution)
        return resolution

    def resolve_human_question(
        self,
        node_id: str,
        question_id: str,
        *,
        answer: str,
        fix: str,
        retry_command: Sequence[str],
    ) -> Mapping[str, Any]:
        """Record a human result and make the safe retry immediately actionable.

        Only a digest of ``answer`` is retained. Secrets therefore cannot be
        copied into repository or runtime evidence by the learning mechanism.
        """

        for value, label in ((answer, "answer"), (fix, "fix")):
            if not isinstance(value, str) or not value.strip():
                raise AutopilotError(f"question resolution {label} is required")
        if not retry_command:
            raise AutopilotError("question resolution retry_command is required")
        normalized_retry = self.validate_retry_command(retry_command)
        result = {
            "schema_version": SCHEMA_VERSION,
            "event": "QUESTION_RESOLVED",
            "node_id": node_id,
            "question_id": question_id,
            "answer_digest": digest_json({"answer": answer}),
            "fix": fix,
            "retry_command": list(normalized_retry),
            "plan_fingerprint": self.expected_plan_fingerprint,
            "timestamp": format_time(self.clock()),
            "status": "RESOLVED",
            "recovery_action": {"action": "RETRY_NOW", "reason": "human_result_recorded"},
        }
        result["resolution_id"] = digest_json(result)
        append_jsonl(self.questions_dir / f"{node_id}.jsonl", result)
        return result

    def start_subtask_wave(
        self,
        wave_id: str,
        node_ids: Sequence[str],
        *,
        target_sha: str | None = None,
    ) -> Mapping[str, Any]:
        """Register children that the orchestrator must supervise to settlement."""

        if not isinstance(wave_id, str) or not wave_id.strip():
            raise AutopilotError("subtask wave_id is required")
        nodes = tuple(dict.fromkeys(str(node) for node in node_ids))
        if not nodes:
            raise AutopilotError("subtask wave requires at least one node")
        unknown = sorted(set(nodes) - set(self._nodes))
        if unknown:
            raise AutopilotError("subtask wave has unknown nodes: " + ", ".join(unknown))
        target = target_sha or self.current_target_sha()
        if FULL_SHA.fullmatch(target) is None:
            raise AutopilotError("subtask wave target_sha must be a full lowercase Git SHA")
        record = {
            "schema_version": SCHEMA_VERSION,
            "event": "SUBTASK_WAVE_STARTED",
            "wave_id": wave_id,
            "target_sha": target,
            "nodes": list(nodes),
            "statuses": {node: "PENDING" for node in nodes},
            "timestamp": format_time(self.clock()),
            "may_end_turn": False,
            "target_mutation_allowed": False,
            "next_action": "POLL_AGAIN",
            "work_preservation_sequence": list(STALE_TARGET_RECOVERY_SEQUENCE),
        }
        append_jsonl(self.subtask_waves_dir / f"{wave_id}.jsonl", record)
        return record

    def poll_subtask_wave(
        self,
        wave_id: str,
        statuses: Mapping[str, str],
    ) -> Mapping[str, Any]:
        """Record one poll and require supervision until every result is collected.

        UI ``idle`` is deliberately represented as ``IDLE_UNCOLLECTED``. It is
        not success: the parent must read the result and classify it. Recoverable
        blockers require retry; only success or genuine external authority can
        settle a child and permit the parent turn to end.
        """

        path = self.subtask_waves_dir / f"{wave_id}.jsonl"
        if not path.is_file():
            raise AutopilotError(f"unknown subtask wave: {wave_id}")
        records = strict_jsonl_records(path, label="subtask-wave ledger")
        started = next((record for record in records if record.get("event") == "SUBTASK_WAVE_STARTED"), None)
        if not isinstance(started, Mapping):
            raise AutopilotError(f"subtask wave lacks start record: {wave_id}")
        nodes = tuple(str(node) for node in started.get("nodes", ()))
        if set(statuses) != set(nodes):
            raise AutopilotError("subtask poll must classify every wave node exactly once")
        normalized = {node: str(statuses[node]).upper() for node in nodes}
        invalid = sorted({status for status in normalized.values() if status not in SUBTASK_STATES})
        if invalid:
            raise AutopilotError("invalid subtask states: " + ", ".join(invalid))
        actions: dict[str, str] = {}
        for node, state in normalized.items():
            if state in {"PENDING", "ACTIVE"}:
                actions[node] = "POLL_AGAIN"
            elif state == "IDLE_UNCOLLECTED":
                actions[node] = "COLLECT_RESULT_NOW"
            elif state == "BLOCKED_RECOVERABLE":
                actions[node] = "APPLY_FIX_AND_RETRY_NOW"
        settled = all(state in SUBTASK_SETTLED_STATES for state in normalized.values())
        record = {
            "schema_version": SCHEMA_VERSION,
            "event": "SUBTASK_WAVE_POLLED",
            "wave_id": wave_id,
            "target_sha": started.get("target_sha"),
            "statuses": normalized,
            "recovery_actions": actions,
            "timestamp": format_time(self.clock()),
            "may_end_turn": settled,
            "target_mutation_allowed": settled,
            "next_action": "QUIESCENT" if settled else "CONTINUE_SUPERVISION",
        }
        append_jsonl(path, record)
        return record

    @contextmanager
    def _validation_authority_locks(self):
        """Serialize the claim/validation tail of the canonical lock order."""

        with self.runtime_lock("claim-authority.lock", timeout_seconds=120.0):
            with self.runtime_lock(
                "global-validation-lease.lock", timeout_seconds=120.0
            ):
                yield None

    @contextmanager
    def validation_claim_authority_guard(
        self,
        node_id: str,
        *,
        claim_owner: str,
        claim_id: str | None,
        claim_authority_class: str,
        launch_instruction_id: str | None,
        resource_key: str | None,
        authority_epoch: int | None,
        _internal_authority: object | None = None,
    ):
        """Hold launch then claim authority before a validation-lease effect."""

        with self.claim_launch_authority_guard(
            node_id,
            claim_authority_class=claim_authority_class,
            launch_instruction_id=launch_instruction_id,
            resource_key=resource_key,
            authority_epoch=authority_epoch,
            _internal_authority=_internal_authority,
        ):
            if claim_authority_class == INTERNAL_CLAIM_AUTHORITY:
                if claim_id is not None:
                    raise ClaimError(
                        "privileged internal validation authority cannot name a hosted claim"
                    )
                yield None
                return
            if not isinstance(claim_id, str):
                raise ClaimError("hosted validation authority requires an exact claim fence")
            with self.runtime_lock("claim-authority.lock", timeout_seconds=120.0):
                _path, claim = self._fenced_claim(
                    node_id,
                    claim_owner,
                    claim_id,
                    claim_authority_class=claim_authority_class,
                    launch_instruction_id=launch_instruction_id,
                    resource_key=resource_key,
                    authority_epoch=authority_epoch,
                )
                try:
                    claim_expires = parse_time(claim.get("expires_at"))
                except (TypeError, ValueError) as error:
                    raise ClaimError(
                        "hosted validation claim expiry is malformed"
                    ) from error
                if claim_expires <= self.clock():
                    raise ClaimError("hosted validation claim has expired")
                yield claim

    @staticmethod
    def _validation_authority_fields(
        *,
        claim_id: str | None,
        claim_authority_class: str,
        launch_instruction_id: str | None,
        resource_key: str | None,
        authority_epoch: int | None,
        release_id: str | None = None,
        transaction_sha: str | None = None,
        host_reservation_id: str | None = None,
        capacity_host_id: str | None = None,
        capacity_generation: str | None = None,
    ) -> Mapping[str, object]:
        return {
            "claim_id": claim_id,
            "claim_authority_class": claim_authority_class,
            "launch_instruction_id": launch_instruction_id,
            "resource_key": resource_key,
            "authority_epoch": authority_epoch,
            "release_id": release_id,
            "transaction_sha": transaction_sha,
            "host_reservation_id": host_reservation_id,
            "capacity_host_id": capacity_host_id,
            "capacity_generation": capacity_generation,
        }

    def acquire_global_validation_lease(
        self,
        node_id: str,
        owner: str,
        *,
        claim_id: str | None,
        claim_authority_class: str,
        launch_instruction_id: str | None = None,
        resource_key: str | None = None,
        authority_epoch: int | None = None,
        release_id: str | None = None,
        transaction_sha: str | None = None,
        host_reservation_id: str | None = None,
        capacity_host_id: str | None = None,
        capacity_generation: str | None = None,
        pinned_target_sha: str | None = None,
        _internal_authority: object | None = None,
        lease_minutes: int = 10,
    ) -> Mapping[str, Any]:
        """Serialize repository-wide gates while focused node checks stay parallel."""

        if node_id not in self._nodes:
            raise AutopilotError(f"unknown validation node: {node_id}")
        if not isinstance(owner, str) or not owner.strip():
            raise AutopilotError("validation lease owner is required")
        if type(lease_minutes) is not int or lease_minutes < 1:
            raise AutopilotError("validation lease_minutes must be positive")
        if pinned_target_sha is not None and FULL_SHA.fullmatch(
            pinned_target_sha
        ) is None:
            raise AutopilotError("validation pinned target SHA is invalid")
        authority = self._validation_authority_fields(
            claim_id=claim_id,
            claim_authority_class=claim_authority_class,
            launch_instruction_id=launch_instruction_id,
            resource_key=resource_key,
            authority_epoch=authority_epoch,
            release_id=release_id,
            transaction_sha=transaction_sha,
            host_reservation_id=host_reservation_id,
            capacity_host_id=capacity_host_id,
            capacity_generation=capacity_generation,
        )
        with self.validation_claim_authority_guard(
            node_id,
            claim_owner=owner,
            claim_id=claim_id,
            claim_authority_class=claim_authority_class,
            launch_instruction_id=launch_instruction_id,
            resource_key=resource_key,
            authority_epoch=authority_epoch,
            _internal_authority=_internal_authority,
        ):
            with self._validation_authority_locks():
                now = self.clock()
                terminal_fence = self._read_plan_terminal_fence_unlocked()
                if terminal_fence is not None:
                    raise AutopilotError(
                        "validation admission is closed by the execution terminal fence"
                    )
                self._assert_publication_not_indeterminate_unlocked()
                if self.validation_lease_path.is_file():
                    current = read_json(self.validation_lease_path)
                    if isinstance(current, Mapping):
                        try:
                            expires = parse_time(current.get("expires_at"))
                        except (TypeError, ValueError) as error:
                            raise AutopilotError(
                                "global validation lease expiry is malformed"
                            ) from error
                        current_id = current.get("lease_id")
                        if not isinstance(current_id, str) or AUTHORITY_ID.fullmatch(
                            current_id
                        ) is None:
                            raise AutopilotError("global validation lease id is malformed")
                        identity = (
                            current.get("node_id"),
                            current.get("owner"),
                            current.get("execution_id"),
                            current.get("validation_resource_key"),
                        )
                        if expires > now:
                            if identity == (
                                node_id,
                                owner,
                                self.execution_id,
                                self.validation_resource_key,
                            ) and all(
                                current.get(field) == expected
                                for field, expected in authority.items()
                            ):
                                return current
                            raise AutopilotError(
                                "global validation lease is active for "
                                f"{current.get('node_id')} owned by {current.get('owner')}"
                            )
                        raise AutopilotError(
                            "expired global validation lease requires expiry recovery before reacquisition"
                        )
                    raise AutopilotError("global validation lease is malformed")
                lease = {
                    "schema_version": SCHEMA_VERSION,
                    "node_id": node_id,
                    "owner": owner,
                    "target_sha": pinned_target_sha or self.current_target_sha(),
                    "acquired_at": format_time(now),
                    "expires_at": format_time(now + timedelta(minutes=lease_minutes)),
                    "renewal_count": 0,
                    "status": "ACTIVE",
                    "execution_id": self.execution_id,
                    "validation_resource_key": self.validation_resource_key,
                    "authority_nonce": secrets.token_hex(32),
                    **authority,
                }
                lease["lease_id"] = digest_json(lease)
                atomic_write_json(self.validation_lease_path, lease)
                return lease

    def acquire_global_validation_lease_internal(
        self,
        node_id: str,
        owner: str,
        *,
        lease_minutes: int = 10,
    ) -> Mapping[str, Any]:
        """Controller-only validation authority; never selected by CLI text."""

        return self.acquire_global_validation_lease(
            node_id,
            owner,
            claim_id=None,
            claim_authority_class=INTERNAL_CLAIM_AUTHORITY,
            _internal_authority=_INTERNAL_CLAIM_CAPABILITY,
            lease_minutes=lease_minutes,
        )

    def release_global_validation_lease(
        self,
        node_id: str,
        owner: str,
        *,
        lease_id: str,
        claim_id: str | None,
        claim_authority_class: str,
        launch_instruction_id: str | None = None,
        resource_key: str | None = None,
        authority_epoch: int | None = None,
        release_id: str | None = None,
        transaction_sha: str | None = None,
        host_reservation_id: str | None = None,
        capacity_host_id: str | None = None,
        capacity_generation: str | None = None,
        _internal_authority: object | None = None,
    ) -> Mapping[str, Any]:
        if AUTHORITY_ID.fullmatch(lease_id) is None:
            raise AutopilotError("global validation lease id is invalid")
        authority = self._validation_authority_fields(
            claim_id=claim_id,
            claim_authority_class=claim_authority_class,
            launch_instruction_id=launch_instruction_id,
            resource_key=resource_key,
            authority_epoch=authority_epoch,
            release_id=release_id,
            transaction_sha=transaction_sha,
            host_reservation_id=host_reservation_id,
            capacity_host_id=capacity_host_id,
            capacity_generation=capacity_generation,
        )
        with self.validation_claim_authority_guard(
            node_id,
            claim_owner=owner,
            claim_id=claim_id,
            claim_authority_class=claim_authority_class,
            launch_instruction_id=launch_instruction_id,
            resource_key=resource_key,
            authority_epoch=authority_epoch,
            _internal_authority=_internal_authority,
        ):
            with self._validation_authority_locks():
                if not self.validation_lease_path.is_file():
                    raise AutopilotError("global validation lease is absent")
                current = read_strict_canonical_json(
                    self.validation_lease_path,
                    label="global validation lease",
                )
                identity = (
                    current.get("node_id"),
                    current.get("owner"),
                    current.get("lease_id"),
                    current.get("execution_id"),
                    current.get("validation_resource_key"),
                ) if isinstance(current, Mapping) else (None, None, None)
                if identity != (
                    node_id,
                    owner,
                    lease_id,
                    self.execution_id,
                    self.validation_resource_key,
                ) or any(
                    not isinstance(current, Mapping)
                    or current.get(field) != expected
                    for field, expected in authority.items()
                ):
                    raise AutopilotError("global validation lease identity or fence mismatch")
                archive_name = lease_id.replace(":", "-") + ".json"
                archive = self.coordination_dir / "validation-leases" / archive_name
                terminal = exclusive_transition_archive(
                    archive,
                    current,
                    {"status": "RELEASED"},
                    timestamp_key="released_at",
                    now=self.clock(),
                )
                self.validation_lease_path.unlink()
                _fsync_parent_directory(self.validation_lease_path.parent)
                return terminal

    def release_global_validation_lease_internal(
        self,
        node_id: str,
        owner: str,
        *,
        lease_id: str,
    ) -> Mapping[str, Any]:
        return self.release_global_validation_lease(
            node_id,
            owner,
            lease_id=lease_id,
            claim_id=None,
            claim_authority_class=INTERNAL_CLAIM_AUTHORITY,
            _internal_authority=_INTERNAL_CLAIM_CAPABILITY,
        )

    def renew_global_validation_lease(
        self,
        node_id: str,
        owner: str,
        *,
        lease_id: str,
        claim_id: str | None,
        claim_authority_class: str,
        launch_instruction_id: str | None = None,
        resource_key: str | None = None,
        authority_epoch: int | None = None,
        release_id: str | None = None,
        transaction_sha: str | None = None,
        host_reservation_id: str | None = None,
        capacity_host_id: str | None = None,
        capacity_generation: str | None = None,
        _internal_authority: object | None = None,
        lease_minutes: int = 10,
    ) -> Mapping[str, Any]:
        if AUTHORITY_ID.fullmatch(lease_id) is None:
            raise AutopilotError("global validation lease id is invalid")
        if type(lease_minutes) is not int or lease_minutes < 1:
            raise AutopilotError("validation lease_minutes must be positive")
        authority = self._validation_authority_fields(
            claim_id=claim_id,
            claim_authority_class=claim_authority_class,
            launch_instruction_id=launch_instruction_id,
            resource_key=resource_key,
            authority_epoch=authority_epoch,
            release_id=release_id,
            transaction_sha=transaction_sha,
            host_reservation_id=host_reservation_id,
            capacity_host_id=capacity_host_id,
            capacity_generation=capacity_generation,
        )
        with self.validation_claim_authority_guard(
            node_id,
            claim_owner=owner,
            claim_id=claim_id,
            claim_authority_class=claim_authority_class,
            launch_instruction_id=launch_instruction_id,
            resource_key=resource_key,
            authority_epoch=authority_epoch,
            _internal_authority=_internal_authority,
        ):
            with self._validation_authority_locks():
                terminal_fence = self._read_plan_terminal_fence_unlocked()
                if terminal_fence is not None:
                    raise AutopilotError(
                        "validation renewal is closed by the execution terminal fence"
                    )
                self._assert_publication_not_indeterminate_unlocked()
                if not self.validation_lease_path.is_file():
                    raise AutopilotError("global validation lease is absent")
                current = read_json(self.validation_lease_path)
                if not isinstance(current, Mapping):
                    raise AutopilotError("global validation lease is malformed")
                identity = (
                    current.get("node_id"),
                    current.get("owner"),
                    current.get("lease_id"),
                    current.get("execution_id"),
                    current.get("validation_resource_key"),
                )
                if identity != (
                    node_id,
                    owner,
                    lease_id,
                    self.execution_id,
                    self.validation_resource_key,
                ) or any(
                    current.get(field) != expected
                    for field, expected in authority.items()
                ):
                    raise AutopilotError("global validation lease identity or fence mismatch")
                now = self.clock()
                try:
                    expires = parse_time(current.get("expires_at"))
                except (TypeError, ValueError) as error:
                    raise AutopilotError("global validation lease expiry is malformed") from error
                if expires <= now:
                    raise AutopilotError(
                        "expired global validation lease requires expiry recovery before renewal"
                    )
                renewed = {
                    **current,
                    "renewed_at": format_time(now),
                    "expires_at": format_time(now + timedelta(minutes=lease_minutes)),
                    "renewal_count": int(current.get("renewal_count", 0)) + 1,
                }
                atomic_write_json(self.validation_lease_path, renewed)
                return renewed

    def renew_global_validation_lease_internal(
        self,
        node_id: str,
        owner: str,
        *,
        lease_id: str,
        lease_minutes: int = 10,
    ) -> Mapping[str, Any]:
        return self.renew_global_validation_lease(
            node_id,
            owner,
            lease_id=lease_id,
            claim_id=None,
            claim_authority_class=INTERNAL_CLAIM_AUTHORITY,
            _internal_authority=_INTERNAL_CLAIM_CAPABILITY,
            lease_minutes=lease_minutes,
        )

    def _keyed_validation_release(
        self,
        *,
        release_id: str,
        transaction_sha: str,
    ) -> Mapping[str, Any]:
        if AUTHORITY_ID.fullmatch(release_id) is None:
            raise AutopilotError("keyed validation release id is invalid")
        if FULL_SHA.fullmatch(transaction_sha) is None:
            raise AutopilotError("keyed validation transaction SHA is invalid")
        current_release = getattr(self, "current_release", None)
        release_issues = getattr(self, "_release_issues", None)
        if not callable(current_release) or not callable(release_issues):
            raise AutopilotError("keyed validation requires dispatcher authority")
        release = current_release()
        issues = tuple(str(item) for item in release_issues(release))
        if issues:
            raise AutopilotError(
                "keyed validation dispatcher authority is invalid: "
                + "; ".join(issues)
            )
        if (
            not isinstance(release, Mapping)
            or release.get("release_id") != release_id
            or type(release.get("admission_epoch")) is not int
            or int(release["admission_epoch"]) < 1
        ):
            raise AutopilotError("keyed validation dispatcher fence mismatch")
        return release

    def acquire_keyed_validation_lease_internal(
        self,
        node_id: str,
        owner: str,
        *,
        host_id: str,
        release_id: str,
        transaction_sha: str,
        lease_minutes: int = 10,
    ) -> Mapping[str, Any]:
        """Acquire one host-global validation slot bound to an exact round SHA."""

        if not isinstance(host_id, str) or not host_id.strip():
            raise AutopilotError("keyed validation host id is required")
        if type(lease_minutes) is not int or lease_minutes < 1:
            raise AutopilotError("keyed validation lease_minutes must be positive")
        # Git/target observation happens before global locks; the dispatcher
        # release is revalidated under the short authority transition below.
        pinned_target_sha = self.current_target_sha()
        local_reservation_id = digest_json(
            {
                "kind": "hive-mind-keyed-validation-reservation-v1",
                "execution_id": self.execution_id,
                "release_id": release_id,
                "transaction_sha": transaction_sha,
                "node_id": node_id,
                "owner": owner,
            }
        )
        repository = _require_nonempty_text(
            _require_mapping(self.control.get("target"), "control-plane.target").get(
                "repository"
            ),
            "target.repository",
        )
        reservation: Mapping[str, object] | None = None
        with self.host_lock(timeout_seconds=120.0):
            with self.arbiter_lock(timeout_seconds=120.0):
                with self.execution_lock(
                    "dispatcher-admission.lock", timeout_seconds=120.0
                ):
                    release = self._keyed_validation_release(
                        release_id=release_id,
                        transaction_sha=transaction_sha,
                    )
                    if release.get("target_sha") != pinned_target_sha:
                        raise AutopilotError(
                            "keyed validation target changed before admission"
                        )
                    capacity = read_host_capacity(
                        self.host_runtime_dir, host_id, now=self.clock()
                    )
                    expires_at = min(
                        parse_time(capacity["expires_at"]),
                        self.clock() + timedelta(minutes=90),
                    )
                    if expires_at <= self.clock() + timedelta(minutes=lease_minutes):
                        raise AutopilotError(
                            "host capacity expires before the requested validation lease"
                        )
                    reservation = reserve_global_host_session(
                        self.host_runtime_dir,
                        repository=repository,
                        execution_id=self.execution_id,
                        host_id=host_id,
                        capacity_generation=str(capacity["capacity_generation"]),
                        local_reservation_id=local_reservation_id,
                        reservation_kind="VALIDATION",
                        resource_key=self.validation_resource_key,
                        write_scopes=(),
                        actor_time=format_time(self.clock()),
                        expires_at=format_time(expires_at),
                        now=self.clock(),
                    )
                    try:
                        lease = self.acquire_global_validation_lease(
                            node_id,
                            owner,
                            claim_id=None,
                            claim_authority_class=INTERNAL_CLAIM_AUTHORITY,
                            release_id=release_id,
                            transaction_sha=transaction_sha,
                            host_reservation_id=str(reservation["reservation_id"]),
                            capacity_host_id=host_id,
                            capacity_generation=str(
                                reservation["capacity_generation"]
                            ),
                            pinned_target_sha=pinned_target_sha,
                            _internal_authority=_INTERNAL_CLAIM_CAPABILITY,
                            lease_minutes=lease_minutes,
                        )
                    except Exception as lease_error:
                        try:
                            never_acquired: dict[str, object] = {
                                "schema_version": 1,
                                "kind": VALIDATION_NEVER_ACQUIRED_KIND,
                                "state": "NEVER_ACQUIRED",
                                "execution_namespace": self.execution_namespace,
                                "execution_id": self.execution_id,
                                "repository": repository,
                                "reservation_id": reservation["reservation_id"],
                                "local_reservation_id": reservation[
                                    "local_reservation_id"
                                ],
                                "resource_key": reservation["resource_key"],
                                "host_id": reservation["host_id"],
                                "provider_generation": reservation[
                                    "provider_generation"
                                ],
                                "capacity_generation": reservation[
                                    "capacity_generation"
                                ],
                                "validation_resource_key": self.validation_resource_key,
                                "release_id": release_id,
                                "transaction_sha": transaction_sha,
                                "node_id": node_id,
                                "owner": owner,
                                "reason": "VALIDATION_LEASE_ACQUIRE_FAILED_BEFORE_AUTHORITY",
                                "actor": owner,
                                "recorded_at": format_time(self.clock()),
                            }
                            never_acquired["record_id"] = digest_json(never_acquired)
                            exclusive_write_json_or_identical(
                                _validation_never_acquired_source_path(
                                    self.execution_dir,
                                    str(reservation["reservation_id"]),
                                ),
                                never_acquired,
                            )
                            release_global_host_session(
                                self.host_runtime_dir,
                                str(reservation["reservation_id"]),
                                execution_id=self.execution_id,
                                local_reservation_id=local_reservation_id,
                                capacity_generation=str(
                                    reservation["capacity_generation"]
                                ),
                                actor=owner,
                                reason="rollback failed keyed validation lease admission",
                                released_at=format_time(self.clock()),
                                validation_never_acquired_receipt=never_acquired,
                                repo_root=self.repo_root,
                                coordination_dir=self.coordination_dir,
                                execution_dir=self.execution_dir,
                                execution_namespace=self.execution_namespace,
                            )
                        except Exception as cleanup_error:
                            raise AutopilotError(
                                "keyed validation admission and reservation rollback both failed: "
                                f"{lease_error}; {cleanup_error}"
                            ) from lease_error
                        raise
        return {
            **dict(lease),
            "global_host_reservation_id": reservation["reservation_id"],
            "global_capacity_generation": reservation["capacity_generation"],
        }

    def renew_keyed_validation_lease_internal(
        self,
        node_id: str,
        owner: str,
        *,
        lease_id: str,
        host_id: str,
        release_id: str,
        transaction_sha: str,
        lease_minutes: int = 10,
    ) -> Mapping[str, Any]:
        with self.host_lock(timeout_seconds=120.0):
            with self.arbiter_lock(timeout_seconds=120.0):
                with self.execution_lock(
                    "dispatcher-admission.lock", timeout_seconds=120.0
                ):
                    self._keyed_validation_release(
                        release_id=release_id,
                        transaction_sha=transaction_sha,
                    )
                    if not self.validation_lease_path.is_file():
                        raise AutopilotError("keyed validation lease is absent")
                    current = read_json(self.validation_lease_path)
                    if not isinstance(current, Mapping):
                        raise AutopilotError("keyed validation lease is malformed")
                    reservation_id = current.get("host_reservation_id")
                    generation = current.get("capacity_generation")
                    if (
                        current.get("capacity_host_id") != host_id
                        or current.get("release_id") != release_id
                        or current.get("transaction_sha") != transaction_sha
                        or not isinstance(reservation_id, str)
                        or not isinstance(generation, str)
                    ):
                        raise AutopilotError("keyed validation lease fence mismatch")
                    reservation = global_host_reservation_record(
                        self.host_runtime_dir, reservation_id
                    )
                    if (
                        not isinstance(reservation, Mapping)
                        or reservation.get("state")
                        not in HOST_RESERVATION_ACTIVE_STATES
                        or reservation.get("host_id") != host_id
                        or reservation.get("capacity_generation") != generation
                        or parse_time(reservation.get("expires_at"))
                        <= self.clock() + timedelta(minutes=lease_minutes)
                    ):
                        raise AutopilotError(
                            "keyed validation host reservation cannot cover renewal"
                        )
                    return self.renew_global_validation_lease(
                        node_id,
                        owner,
                        lease_id=lease_id,
                        claim_id=None,
                        claim_authority_class=INTERNAL_CLAIM_AUTHORITY,
                        release_id=release_id,
                        transaction_sha=transaction_sha,
                        host_reservation_id=reservation_id,
                        capacity_host_id=host_id,
                        capacity_generation=generation,
                        _internal_authority=_INTERNAL_CLAIM_CAPABILITY,
                        lease_minutes=lease_minutes,
                    )

    def release_keyed_validation_lease_internal(
        self,
        node_id: str,
        owner: str,
        *,
        lease_id: str,
        host_id: str,
        release_id: str,
        transaction_sha: str,
    ) -> Mapping[str, Any]:
        """Attempt both durable lease and host-slot cleanup, preserving failures."""

        errors: list[str] = []
        lease_released = False
        reservation_released: Mapping[str, object] | None = None
        evidence: Mapping[str, Any] | None = None
        with self.host_lock(timeout_seconds=120.0):
            with self.arbiter_lock(timeout_seconds=120.0):
                with self.execution_lock(
                    "dispatcher-admission.lock", timeout_seconds=120.0
                ):
                    self._keyed_validation_release(
                        release_id=release_id,
                        transaction_sha=transaction_sha,
                    )
                    if self.validation_lease_path.is_file():
                        candidate = read_strict_canonical_json(
                            self.validation_lease_path,
                            label="keyed validation lease cleanup source",
                        )
                        if isinstance(candidate, Mapping):
                            evidence = dict(candidate)
                    else:
                        archive_name = lease_id.replace(":", "-") + ".json"
                        for archive_path in (
                            self.execution_dir / "validation-leases" / archive_name,
                            self.coordination_dir / "validation-leases" / archive_name,
                        ):
                            if not archive_path.is_file():
                                continue
                            candidate = read_strict_canonical_json(
                                archive_path,
                                label="keyed validation lease cleanup archive",
                            )
                            if (
                                isinstance(candidate, Mapping)
                                and candidate.get("status")
                                in {"RELEASED", "EXPIRED_BROKEN"}
                            ):
                                evidence = dict(candidate)
                                lease_released = True
                                break
                    if not isinstance(evidence, Mapping):
                        errors.append("keyed validation lease evidence is absent or malformed")
                    else:
                        reservation_id = evidence.get("host_reservation_id")
                        generation = evidence.get("capacity_generation")
                        if any(
                            evidence.get(field) != expected
                            for field, expected in {
                                "lease_id": lease_id,
                                "execution_id": self.execution_id,
                                "capacity_host_id": host_id,
                                "release_id": release_id,
                                "transaction_sha": transaction_sha,
                            }.items()
                        ) or not isinstance(reservation_id, str) or not isinstance(
                            generation, str
                        ):
                            errors.append("keyed validation lease cleanup fence mismatch")
                        else:
                            reservation = global_host_reservation_record(
                                self.host_runtime_dir, reservation_id
                            )
                            if not isinstance(reservation, Mapping):
                                errors.append("keyed validation host reservation is absent")
                            else:
                                if not lease_released:
                                    try:
                                        evidence = self.release_global_validation_lease(
                                            node_id,
                                            owner,
                                            lease_id=lease_id,
                                            claim_id=None,
                                            claim_authority_class=INTERNAL_CLAIM_AUTHORITY,
                                            release_id=release_id,
                                            transaction_sha=transaction_sha,
                                            host_reservation_id=reservation_id,
                                            capacity_host_id=host_id,
                                            capacity_generation=generation,
                                            _internal_authority=_INTERNAL_CLAIM_CAPABILITY,
                                        )
                                        lease_released = True
                                    except Exception as error:
                                        errors.append(f"lease cleanup failed: {error}")
                                if lease_released and isinstance(evidence, Mapping):
                                    try:
                                        reservation_released = release_global_host_session(
                                            self.host_runtime_dir,
                                            reservation_id,
                                            execution_id=self.execution_id,
                                            local_reservation_id=str(
                                                reservation["local_reservation_id"]
                                            ),
                                            capacity_generation=generation,
                                            actor=owner,
                                            reason="keyed validation transaction settled",
                                            released_at=format_time(self.clock()),
                                            validation_terminal_lease=evidence,
                                            repo_root=self.repo_root,
                                            coordination_dir=self.coordination_dir,
                                            execution_dir=self.execution_dir,
                                            execution_namespace=self.execution_namespace,
                                        )
                                    except Exception as error:
                                        errors.append(
                                            f"host reservation cleanup failed: {error}"
                                        )
        result: dict[str, Any] = {
            "schema_version": 1,
            "kind": "hive-mind-keyed-validation-cleanup-v1",
            "execution_id": self.execution_id,
            "release_id": release_id,
            "transaction_sha": transaction_sha,
            "lease_id": lease_id,
            "lease_released": lease_released,
            "host_reservation": (
                dict(reservation_released)
                if isinstance(reservation_released, Mapping)
                else None
            ),
            "errors": errors,
            "recorded_at": format_time(self.clock()),
        }
        result["record_id"] = digest_json(result)
        if errors:
            append_jsonl(
                self.execution_dir / "validation-cleanup-recovery.jsonl", result
            )
            raise AutopilotError("; ".join(errors))
        return result

    def recover_expired_keyed_validation_lease_internal(
        self,
        *,
        actor: str,
        lease_id: str | None = None,
        host_reservation_id: str | None = None,
        reason: str = "expired keyed validation authority recovery",
    ) -> Mapping[str, Any]:
        """Settle an expired keyed lease and its host-global slot as one retryable saga.

        The lease archive is written before unlink and the global reservation is
        terminalized afterwards.  A restart can therefore resume from either an
        active lease, an already archived lease, or an already released permit;
        no clock-only path frees capacity without the exact lease/reservation
        fence.
        """

        if not actor.strip() or not reason.strip():
            raise AutopilotError("keyed validation expiry recovery evidence is required")
        if lease_id is not None and AUTHORITY_ID.fullmatch(lease_id) is None:
            raise AutopilotError("expired keyed validation lease id is invalid")
        if (
            host_reservation_id is not None
            and AUTHORITY_ID.fullmatch(host_reservation_id) is None
        ):
            raise AutopilotError("expired keyed validation reservation id is invalid")
        if lease_id is None and host_reservation_id is None:
            raise AutopilotError(
                "keyed validation expiry recovery requires a lease or reservation fence"
            )

        archive_roots = (
            self.execution_dir / "validation-leases",
            self.coordination_dir / "validation-leases",  # legacy archive location
        )
        with self.host_lock(timeout_seconds=120.0):
            with self.arbiter_lock(timeout_seconds=120.0):
                with self.execution_lock(
                    "dispatcher-admission.lock", timeout_seconds=120.0
                ):
                    with self._validation_authority_locks():
                        active: Mapping[str, Any] | None = None
                        if self.validation_lease_path.is_file():
                            candidate = read_strict_canonical_json(
                                self.validation_lease_path,
                                label="keyed validation lease",
                            )
                            if isinstance(candidate, Mapping):
                                active = dict(candidate)
                        archived_matches: list[tuple[Path, Mapping[str, Any]]] = []
                        for archive_root in archive_roots:
                            if not archive_root.is_dir():
                                continue
                            for archive_path in sorted(archive_root.glob("*.json")):
                                candidate = read_strict_canonical_json(
                                    archive_path,
                                    label="keyed validation expiry archive",
                                )
                                if not isinstance(candidate, Mapping):
                                    raise AutopilotError(
                                        "keyed validation expiry archive is malformed"
                                    )
                                if (
                                    (lease_id is not None and candidate.get("lease_id") == lease_id)
                                    or (
                                        host_reservation_id is not None
                                        and candidate.get("host_reservation_id")
                                        == host_reservation_id
                                    )
                                ):
                                    archived_matches.append((archive_path, dict(candidate)))
                        evidence: Mapping[str, Any] | None = active
                        if evidence is not None and not (
                            (lease_id is not None and evidence.get("lease_id") == lease_id)
                            or (
                                host_reservation_id is not None
                                and evidence.get("host_reservation_id")
                                == host_reservation_id
                            )
                        ):
                            evidence = None
                        if evidence is None and archived_matches:
                            canonical_archives = {
                                json.dumps(value, sort_keys=True, allow_nan=False)
                                for _path, value in archived_matches
                            }
                            if len(canonical_archives) != 1:
                                raise AutopilotError(
                                    "keyed validation expiry archives conflict"
                                )
                            evidence = archived_matches[0][1]
                        if not isinstance(evidence, Mapping):
                            raise AutopilotError(
                                "keyed validation lease evidence is unavailable"
                            )

                        required_fields = {
                            "schema_version",
                            "node_id",
                            "owner",
                            "target_sha",
                            "acquired_at",
                            "expires_at",
                            "renewal_count",
                            "status",
                            "execution_id",
                            "validation_resource_key",
                            "authority_nonce",
                            "claim_id",
                            "claim_authority_class",
                            "launch_instruction_id",
                            "resource_key",
                            "authority_epoch",
                            "release_id",
                            "transaction_sha",
                            "host_reservation_id",
                            "capacity_host_id",
                            "capacity_generation",
                            "lease_id",
                        }
                        allowed_fields = required_fields | {
                            "renewed_at",
                            "broken_by",
                            "broken_at",
                        }
                        evidence_fields = frozenset(evidence)
                        if evidence_fields not in {
                            frozenset(required_fields),
                            frozenset(required_fields | {"renewed_at"}),
                            frozenset(required_fields | {"broken_by", "broken_at"}),
                            frozenset(
                                required_fields
                                | {"renewed_at", "broken_by", "broken_at"}
                            ),
                        } or not evidence_fields.issubset(allowed_fields):
                            raise AutopilotError(
                                "keyed validation lease schema is ambiguous"
                            )
                        resolved_lease_id = evidence.get("lease_id")
                        reservation_id = evidence.get("host_reservation_id")
                        generation = evidence.get("capacity_generation")
                        host_id = evidence.get("capacity_host_id")
                        release_id = evidence.get("release_id")
                        transaction_sha = evidence.get("transaction_sha")
                        if (
                            not isinstance(resolved_lease_id, str)
                            or AUTHORITY_ID.fullmatch(resolved_lease_id) is None
                            or not isinstance(reservation_id, str)
                            or AUTHORITY_ID.fullmatch(reservation_id) is None
                            or not isinstance(generation, str)
                            or AUTHORITY_ID.fullmatch(generation) is None
                            or not isinstance(host_id, str)
                            or not host_id.strip()
                            or not isinstance(release_id, str)
                            or AUTHORITY_ID.fullmatch(release_id) is None
                            or not isinstance(transaction_sha, str)
                            or FULL_SHA.fullmatch(transaction_sha) is None
                            or evidence.get("execution_id") != self.execution_id
                            or evidence.get("validation_resource_key")
                            != self.validation_resource_key
                            or evidence.get("status") not in {"ACTIVE", "EXPIRED_BROKEN"}
                        ):
                            raise AutopilotError(
                                "keyed validation lease identity is invalid"
                            )
                        if lease_id is not None and resolved_lease_id != lease_id:
                            raise AutopilotError(
                                "expired keyed validation lease fence mismatch"
                            )
                        if (
                            host_reservation_id is not None
                            and reservation_id != host_reservation_id
                        ):
                            raise AutopilotError(
                                "expired keyed validation reservation fence mismatch"
                            )
                        try:
                            expires = parse_time(evidence.get("expires_at"))
                        except (TypeError, ValueError) as error:
                            raise AutopilotError(
                                "keyed validation lease expiry is malformed"
                            ) from error
                        now = self.clock()
                        if expires > now:
                            raise AutopilotError(
                                "keyed validation lease remains live"
                            )
                        local_reservation_id = digest_json(
                            {
                                "kind": "hive-mind-keyed-validation-reservation-v1",
                                "execution_id": self.execution_id,
                                "release_id": release_id,
                                "transaction_sha": transaction_sha,
                                "node_id": evidence.get("node_id"),
                                "owner": evidence.get("owner"),
                            }
                        )
                        reservation = global_host_reservation_record(
                            self.host_runtime_dir, reservation_id
                        )
                        repository = _require_nonempty_text(
                            _require_mapping(
                                self.control.get("target"), "control-plane.target"
                            ).get("repository"),
                            "target.repository",
                        )
                        if (
                            not isinstance(reservation, Mapping)
                            or reservation.get("reservation_kind") != "VALIDATION"
                            or reservation.get("repository") != repository
                            or reservation.get("execution_id") != self.execution_id
                            or reservation.get("host_id") != host_id
                            or reservation.get("capacity_generation") != generation
                            or reservation.get("local_reservation_id")
                            != local_reservation_id
                            or reservation.get("resource_key")
                            != self.validation_resource_key
                        ):
                            raise AutopilotError(
                                "keyed validation host reservation fence mismatch"
                            )

                        # The lease ID already binds execution_id.  Keep the
                        # immutable recovery archive at the short repository
                        # arbiter path so Windows temporary-link publication
                        # cannot exceed MAX_PATH for a 64-byte execution key.
                        archive = self.coordination_dir / "validation-leases" / (
                            resolved_lease_id.replace(":", "-") + ".json"
                        )
                        if active is not None:
                            archive.parent.mkdir(parents=True, exist_ok=True)
                            _reject_link_components(
                                archive.parent,
                                label="keyed validation expiry archive directory",
                            )
                            broken = exclusive_transition_archive(
                                archive,
                                active,
                                {
                                    "status": "EXPIRED_BROKEN",
                                    "broken_by": actor,
                                },
                                timestamp_key="broken_at",
                                now=now,
                            )
                            self.validation_lease_path.unlink()
                            _fsync_parent_directory(
                                self.validation_lease_path.parent
                            )
                        else:
                            broken = dict(evidence)
                        released = release_global_host_session(
                            self.host_runtime_dir,
                            reservation_id,
                            execution_id=self.execution_id,
                            local_reservation_id=local_reservation_id,
                            capacity_generation=generation,
                            actor=actor,
                            reason=reason,
                            released_at=format_time(now),
                            validation_terminal_lease=broken,
                            repo_root=self.repo_root,
                            coordination_dir=self.coordination_dir,
                            execution_dir=self.execution_dir,
                            execution_namespace=self.execution_namespace,
                        )
        result: dict[str, Any] = {
            "schema_version": 1,
            "kind": "hive-mind-keyed-validation-expiry-recovery-v1",
            "state": "RECOVERED",
            "execution_id": self.execution_id,
            "lease": dict(broken),
            "reservation": dict(released),
            "recorded_at": format_time(self.clock()),
        }
        result["record_id"] = digest_json(result)
        return result

    def break_expired_validation_lease(
        self,
        *,
        actor: str,
        lease_id: str,
    ) -> Mapping[str, Any] | None:
        """Archive and remove an expired validation lease whose owner is gone.

        Exact-identity release is the law for a live lease, but an expired lease
        left by a dead session would otherwise wedge every future round: policy
        forbids retrying while the file exists and no other identity may release
        it.  Expiry is the bound the owner itself declared, so past it the lease
        grants nothing and archiving it is bookkeeping, not authority.  Returns
        the broken lease record, or None when no lease file exists.
        """

        if not actor.strip():
            raise AutopilotError(
                "breaking an expired validation lease requires the acting identity"
            )
        if AUTHORITY_ID.fullmatch(lease_id) is None:
            raise AutopilotError("expired global validation lease id is invalid")
        # Keyed validation owns a machine-user slot.  It must recover that
        # permit under the full host -> repository -> execution lock order;
        # unlinking only the execution lease would permanently leak capacity.
        if self.validation_lease_path.is_file():
            observed = read_strict_canonical_json(
                self.validation_lease_path,
                label="expired validation lease observation",
            )
            if (
                isinstance(observed, Mapping)
                and observed.get("lease_id") == lease_id
                and observed.get("host_reservation_id") is not None
            ):
                recovered = self.recover_expired_keyed_validation_lease_internal(
                    actor=actor,
                    lease_id=lease_id,
                )
                return dict(_require_mapping(recovered.get("lease"), "recovered lease"))
        with self._validation_authority_locks():
            if not self.validation_lease_path.is_file():
                return None
            current = read_json(self.validation_lease_path)
            if not isinstance(current, Mapping):
                raise AutopilotError("global validation lease is malformed")
            now = self.clock()
            try:
                expires = parse_time(current.get("expires_at"))
            except (TypeError, ValueError) as error:
                raise AutopilotError(
                    "global validation lease expiry is malformed; reconciliation is required"
                ) from error
            if expires > now:
                raise AutopilotError(
                    "global validation lease is live; only its exact owner may release it"
                )
            raw_lease_id = current.get("lease_id")
            if not isinstance(raw_lease_id, str) or AUTHORITY_ID.fullmatch(
                raw_lease_id
            ) is None:
                raise AutopilotError("expired global validation lease id is malformed")
            if raw_lease_id != lease_id:
                raise AutopilotError("expired global validation lease fence mismatch")
            archive = self.coordination_dir / "validation-leases" / (
                raw_lease_id.replace(":", "-") + ".json"
            )
            broken = exclusive_transition_archive(
                archive,
                current,
                {
                    "status": "EXPIRED_BROKEN",
                    "broken_by": actor,
                },
                timestamp_key="broken_at",
                now=now,
            )
            self.validation_lease_path.unlink()
            _fsync_parent_directory(self.validation_lease_path.parent)
            return broken

    @staticmethod
    def recovery_action(packet: Mapping[str, Any]) -> Mapping[str, Any]:
        """Turn known orchestration blockers into bounded child-task work."""

        text = " ".join(
            str(packet.get(key, "")) for key in ("category", "cause", "fix")
        ).lower()
        if any(
            marker in text
            for marker in ("dispatcher release", "release record", "dispatch release")
        ):
            return {
                "action": "SPAWN_SUBTASK",
                "role": "orchestrator",
                "objective": "refresh the singleton release snapshot, reconcile the current target, dispatch the exact eligible node, and retry its claim",
                "required_sequence": list(SUBTASK_EXECUTION_SEQUENCE),
                "stop_if": "target or snapshot changes again, or a protected/security control would need weakening",
            }
        if "snapshot" in text and any(marker in text for marker in ("stale", "target", "mismatch")):
            return {
                "action": "SPAWN_SUBTASK",
                "role": "orchestrator",
                "objective": "refresh the validated singleton snapshot and resume every child invalidated by the target advance",
                "required_sequence": list(STALE_TARGET_RECOVERY_SEQUENCE),
                "stop_if": "remote SHA cannot be verified normally or recovery would weaken provenance/security controls",
            }
        category = str(packet.get("category", "")).casefold()
        if not category.endswith("authority") and category not in {
            "external-authority",
            "human-authority",
            "credential-authority",
            "destructive-authority",
        } and ControlPlane.safe_retry_allowed(packet):
            return {
                "action": "SPAWN_SUBTASK",
                "role": "steward",
                "objective": "diagnose the exact failure, implement the bounded safe fix, verify it, record the blocker resolution and lesson, then resume the same task",
                "required_sequence": [
                    "inspect_exact_failure_evidence",
                    "verify_current_target_and_authority",
                    "apply_bounded_safe_fix",
                    "rerun_failed_operation",
                    "record_blocker_resolution_and_lesson",
                    "resume_same_task",
                ],
                "stop_if": "the fix requires new external authority, secrets, destructive action, or weaker security/evidence controls",
            }
        return {
            "action": "REPORT_BLOCKER",
            "role": "orchestrator",
            "objective": "report the exact fix and retry condition to the controlling task",
            "stop_if": "the blocker remains unresolved",
        }

    @staticmethod
    def safe_retry_allowed(packet: Mapping[str, Any]) -> bool:
        """Reject remediation that weakens TLS, certificate, or verification controls."""

        remediation = " ".join(
            str(packet.get(key, "")) for key in ("fix", "retry_when")
        ).lower()
        return not any(marker in remediation for marker in UNSAFE_REMEDIATION_MARKERS)

    @staticmethod
    def validate_retry_command(command: Sequence[str]) -> tuple[str, ...]:
        """Validate a tokenized retry without weakening transport or evidence controls."""

        if isinstance(command, (str, bytes)) or not command:
            raise AutopilotError("retry command must be a non-empty argv sequence")
        normalized: list[str] = []
        for item in command:
            if not isinstance(item, str) or not item or len(item) > 4_096:
                raise AutopilotError("retry command contains an invalid argument")
            if any(character in item for character in "\x00\r\n"):
                raise AutopilotError("retry command arguments must be single-line text")
            normalized.append(item)
        if len(normalized) > 128:
            raise AutopilotError("retry command has too many arguments")

        folded = " ".join(normalized).casefold()
        compact = re.sub(r"[\s_-]+", "", folded)
        unsafe = any(marker in folded for marker in UNSAFE_RETRY_ARGUMENT_MARKERS)
        unsafe = unsafe or any(
            marker in compact
            for marker in (
                "gitsslnoverify",
                "curlinsecure",
                "sslverify=false",
                "sslverify=0",
                "schannel.checkrevoke=false",
                "schannel.checkrevoke=0",
            )
        )
        if unsafe or any(
            item.casefold().startswith(("git_config_", "git_config_count="))
            for item in normalized
        ):
            raise AutopilotError("retry command would weaken a security control")
        return tuple(normalized)

    def is_quarantined(self, node_id: str) -> bool:
        return (self.quarantine_dir / f"{node_id}.json").is_file()

    def is_escalated(self, node_id: str) -> bool:
        return (self.escalations_dir / f"{node_id}.json").is_file()

    def validate_consultation(self, value: object) -> tuple[str, ...]:
        issues: list[str] = []
        if not isinstance(value, Mapping):
            return ("consultation must be an object",)
        for key in (
            "request_id",
            "mission_id",
            "question",
            "reason_code",
            "requesting_role",
            "decision",
            "cheating_disposition",
        ):
            if not isinstance(value.get(key), str) or not str(value.get(key)).strip():
                issues.append(f"consultation.{key} must be non-empty text")
        requesting = value.get("requesting_role")
        if requesting not in ROLE_NAMES:
            issues.append("consultation.requesting_role is unknown")
        consulted = value.get("consulted_roles")
        if not isinstance(consulted, list) or any(role not in ROLE_NAMES for role in consulted):
            issues.append("consultation.consulted_roles must contain known roles")
            consulted = []
        elif len(set(consulted)) < 2:
            issues.append("consultation requires at least two distinct consulted roles")
        round_number = value.get("round")
        if type(round_number) is not int or not 1 <= round_number <= 3:
            issues.append("consultation.round must be an integer from 1 to 3")
        decision = value.get("decision")
        if decision not in CONSULTATION_DECISIONS:
            issues.append("consultation.decision is invalid")
        evidence = value.get("evidence_refs")
        if not isinstance(evidence, list) or any(
            not isinstance(item, str) or not item for item in evidence
        ):
            issues.append("consultation.evidence_refs must be a string list")
            evidence = []
        dissent = value.get("dissent", [])
        if not isinstance(dissent, list) or any(not isinstance(item, str) for item in dissent):
            issues.append("consultation.dissent must be a string list")
        suspected = value.get("suspected_cheating")
        if not isinstance(suspected, bool):
            issues.append("consultation.suspected_cheating must be boolean")
        disposition = value.get("cheating_disposition")
        if disposition not in CHEATING_DISPOSITIONS:
            issues.append("consultation.cheating_disposition is invalid")
        if suspected is True:
            if disposition == "DISPROVED" and not evidence:
                issues.append("disproving suspected cheating requires evidence")
            if disposition == "NOT_APPLICABLE":
                issues.append("suspected cheating cannot be marked not applicable")
            if decision == "RESOLVED" and disposition not in {"DISPROVED", "UNRESOLVED"}:
                issues.append("confirmed cheating cannot be resolved as ordinary work")
        human = value.get("human_escalation")
        if not isinstance(human, bool):
            issues.append("consultation.human_escalation must be boolean")
            human = False
        authority_class = value.get("authority_class")
        if human:
            if decision != "TRUE_AUTHORITY_REQUIRED":
                issues.append("human escalation requires TRUE_AUTHORITY_REQUIRED")
            if authority_class not in HUMAN_AUTHORITY_CLASSES:
                issues.append("human escalation lacks a genuine authority class")
            if value.get("role_first_exhausted") is not True:
                issues.append("human escalation requires role-first exhaustion proof")
        elif decision == "TRUE_AUTHORITY_REQUIRED":
            issues.append("TRUE_AUTHORITY_REQUIRED must set human_escalation=true")
        if decision == "RESOLVED" and not isinstance(value.get("answer"), str):
            issues.append("resolved consultation requires an answer")
        identity_records = value.get("identity_records", [])
        if not isinstance(identity_records, list):
            issues.append("consultation.identity_records must be a list")
        else:
            for record in identity_records:
                if not isinstance(record, Mapping):
                    issues.append("consultation identity record must be an object")
                    continue
                if record.get("role") not in consulted:
                    issues.append("consultation identity record role was not consulted")
                if record.get("identity_kind") not in {
                    "model_role",
                    "service",
                    "human",
                }:
                    issues.append("consultation identity kind is invalid")
        return tuple(dict.fromkeys(issues))

    def validate_receipt(
        self,
        node_id: str,
        value: object,
        *,
        require_integrated: bool = False,
    ) -> tuple[str, ...]:
        issues: list[str] = []
        node = self.node(node_id)
        if not isinstance(value, Mapping):
            return ("receipt must be an object",)
        required = (
            "schema_version",
            "plan_fingerprint",
            "node_id",
            "contract_version",
            "base_commit",
            "final_commit",
            "branch",
            "pr",
            "changed_paths",
            "tests",
            "evidence_refs",
            "model_runtime",
            "role_identities",
            "authority",
            "consultations",
            "acceptance_decision",
            "timestamp",
            "rollback_ref",
        )
        for key in required:
            if key not in value:
                issues.append(f"receipt missing {key}")
        if value.get("schema_version") != SCHEMA_VERSION:
            issues.append("receipt schema_version is unsupported")
        if value.get("plan_fingerprint") != self.expected_plan_fingerprint:
            issues.append("receipt plan fingerprint is stale")
        if value.get("node_id") != node_id:
            issues.append("receipt node ID does not match")
        if value.get("contract_version") != node.get("contract_version"):
            issues.append("receipt contract version does not match")
        base = value.get("base_commit")
        final = value.get("final_commit")
        if not isinstance(base, str) or FULL_SHA.fullmatch(base) is None:
            issues.append("receipt base_commit is invalid")
        if not isinstance(final, str) or FULL_SHA.fullmatch(final) is None:
            issues.append("receipt final_commit is invalid")
        if isinstance(base, str) and isinstance(final, str) and base == final:
            issues.append("receipt final commit must differ from base commit")
        if value.get("branch") != node.get("branch"):
            issues.append("receipt branch does not match node contract")
        changed = value.get("changed_paths")
        if not isinstance(changed, list) or not changed:
            issues.append("receipt changed_paths must be a non-empty list")
            changed = []
        else:
            write_scope = node.get("write_scope", [])
            for raw in changed:
                try:
                    path = normalize_path(raw)
                except ValueError as error:
                    issues.append(f"receipt changed path is unsafe: {error}")
                    continue
                if not any(path_matches_scope(path, scope) for scope in write_scope):
                    issues.append(f"changed path outside node write scope: {path}")
                if any(path_matches_scope(path, scope) for scope in node.get("forbidden_scope", [])):
                    issues.append(f"changed path enters forbidden scope: {path}")
        tests = value.get("tests")
        if not isinstance(tests, list):
            issues.append("receipt tests must be a list")
        else:
            test_names = {
                item.get("name")
                for item in tests
                if isinstance(item, Mapping) and item.get("status") == "passed"
            }
            for required_test in node.get("required_tests", []):
                if required_test not in test_names:
                    issues.append(f"required test did not pass: {required_test}")
            if any(
                isinstance(item, Mapping) and item.get("status") != "passed"
                for item in tests
            ):
                issues.append("receipt contains a non-passing test")
        evidence = value.get("evidence_refs")
        if not isinstance(evidence, list) or not evidence:
            issues.append("receipt requires retained evidence references")
        roles = value.get("role_identities")
        observed_roles: set[str] = set()
        if not isinstance(roles, list):
            issues.append("receipt role_identities must be a list")
        else:
            for record in roles:
                if not isinstance(record, Mapping):
                    issues.append("role identity must be an object")
                    continue
                role = record.get("role")
                if role in ROLE_NAMES:
                    observed_roles.add(str(role))
                else:
                    issues.append("role identity contains an unknown role")
                if record.get("identity_kind") not in {
                    "model_role",
                    "service",
                    "human",
                }:
                    issues.append("role identity kind is invalid")
            missing_roles = set(node.get("roles", [])) - observed_roles
            if missing_roles:
                issues.append(
                    "receipt omits required role identities: "
                    + ", ".join(sorted(missing_roles))
                )
        authority = value.get("authority")
        if not isinstance(authority, Mapping):
            issues.append("receipt authority must be an object")
        else:
            if authority.get("node_id") != node_id:
                issues.append("receipt authority is not bound to the node")
            if not isinstance(authority.get("autonomy_level"), str):
                issues.append("receipt authority lacks autonomy_level")
            if not isinstance(authority.get("grants"), list):
                issues.append("receipt authority grants must be a list")
        consultations = value.get("consultations")
        if not isinstance(consultations, list):
            issues.append("receipt consultations must be a list")
        else:
            for index, consultation in enumerate(consultations):
                for issue in self.validate_consultation(consultation):
                    issues.append(f"consultation[{index}]: {issue}")
        if value.get("acceptance_decision") not in {"ADOPT", "ADAPT"}:
            issues.append("receipt acceptance decision must be ADOPT or ADAPT")
        try:
            parse_time(value.get("timestamp"))
        except ValueError:
            issues.append("receipt timestamp is invalid")
        if not isinstance(value.get("rollback_ref"), str) or not value.get("rollback_ref"):
            issues.append("receipt rollback_ref must be non-empty")
        if self.verify_git_objects and isinstance(base, str) and isinstance(final, str):
            if not self.git_object_exists(base):
                issues.append("receipt base commit is unavailable")
            if not self.git_object_exists(final):
                issues.append("receipt final commit is unavailable")
            elif not self.is_ancestor(base, final):
                issues.append("receipt final commit does not descend from base")
            elif self.git_object_exists(base):
                issues.extend(
                    self._receipt_raw_ancestry_issues(
                        node_id,
                        base_commit=base,
                        final_commit=final,
                    )
                )
            if require_integrated and not self.is_ancestor(final, self.current_target_sha()):
                issues.append("receipt final commit is not integrated into target history")
        return tuple(dict.fromkeys(issues))

    def _receipt_raw_ancestry_issues(
        self,
        node_id: str,
        *,
        base_commit: str,
        final_commit: str,
    ) -> tuple[str, ...]:
        """Validate every raw commit edge, not merely the endpoint tree diff.

        A worker could otherwise add an out-of-scope payload, use it in an
        intermediate governed commit, and revert it before writing a receipt.
        Git's endpoint diff would be clean even though the prohibited commit is
        retained in the branch ancestry.  Disable replacement objects, require
        one linear parent at every edge, and validate the union of every raw
        edge path against the node's immutable scopes.
        """

        if FULL_SHA.fullmatch(base_commit) is None or FULL_SHA.fullmatch(
            final_commit
        ) is None:
            return ("receipt raw ancestry fence is invalid",)
        node = self.node(node_id)
        raw_environment = {"GIT_NO_REPLACE_OBJECTS": "1"}
        issues: list[str] = []
        replacements = self._git(
            ("for-each-ref", "--format=%(refname)", "refs/replace/"),
            check=False,
            environment=raw_environment,
        )
        if replacements.returncode != 0:
            return ("receipt raw replacement-ref inventory is unavailable",)
        if replacements.stdout.strip():
            issues.append("receipt ancestry is ambiguous while Git replacement refs exist")
        graft_query = self._git(
            ("rev-parse", "--git-path", "info/grafts"),
            check=False,
            environment=raw_environment,
        )
        if graft_query.returncode != 0 or not graft_query.stdout.strip():
            issues.append("receipt raw graft inventory is unavailable")
        else:
            graft_path = Path(graft_query.stdout.strip())
            if not graft_path.is_absolute():
                graft_path = self.repo_root / graft_path
            try:
                if graft_path.is_file() and graft_path.stat().st_size:
                    issues.append("receipt ancestry is ambiguous while Git grafts exist")
            except OSError:
                issues.append("receipt raw graft inventory is unreadable")
        if issues:
            return tuple(dict.fromkeys(issues))

        ancestry = self._git(
            (
                "rev-list",
                "--reverse",
                "--topo-order",
                "--parents",
                f"{base_commit}..{final_commit}",
            ),
            check=False,
            environment=raw_environment,
        )
        if ancestry.returncode != 0:
            return ("receipt raw commit ancestry is unavailable",)
        rows = [line.split() for line in ancestry.stdout.splitlines() if line.strip()]
        if not rows:
            return ("receipt raw commit ancestry is empty",)
        cursor = base_commit
        observed_paths: set[str] = set()
        write_scope = tuple(str(scope) for scope in node.get("write_scope", []))
        forbidden_scope = tuple(
            str(scope) for scope in node.get("forbidden_scope", [])
        )
        for index, row in enumerate(rows, 1):
            if len(row) != 2 or any(FULL_SHA.fullmatch(item) is None for item in row):
                issues.append(
                    f"receipt raw ancestry commit {index} is a merge or has ambiguous parents"
                )
                continue
            commit, parent = row
            if parent != cursor:
                issues.append(
                    f"receipt raw ancestry commit {index} is not one linear edge from its sealed predecessor"
                )
            changed = self._git(
                (
                    "diff-tree",
                    "--no-commit-id",
                    "--name-only",
                    "-z",
                    "-r",
                    parent,
                    commit,
                ),
                check=False,
                environment=raw_environment,
            )
            if changed.returncode != 0:
                issues.append(
                    f"receipt raw ancestry commit {index} path inventory is unavailable"
                )
                cursor = commit
                continue
            for raw_path in changed.stdout.split("\0"):
                if not raw_path:
                    continue
                try:
                    path = normalize_path(raw_path)
                except ValueError as error:
                    issues.append(
                        f"receipt raw ancestry commit {index} has unsafe path: {error}"
                    )
                    continue
                observed_paths.add(path)
                if not any(
                    path_matches_scope(path, scope) for scope in write_scope
                ):
                    issues.append(
                        f"receipt raw ancestry commit {index} changed path outside node write scope: {path}"
                    )
                if any(
                    path_matches_scope(path, scope) for scope in forbidden_scope
                ):
                    issues.append(
                        f"receipt raw ancestry commit {index} entered forbidden scope: {path}"
                    )
            cursor = commit
        if cursor != final_commit:
            issues.append("receipt raw ancestry does not terminate at final_commit")
        if not observed_paths:
            issues.append("receipt raw ancestry has no changed paths")
        return tuple(dict.fromkeys(issues))

    def stored_receipt(self, node_id: str) -> Mapping[str, Any] | None:
        path = self.receipt_path(node_id)
        if not path.is_file():
            return None
        value = read_json(path)
        return value if isinstance(value, Mapping) else None

    def _receipt_terminal_events(self) -> tuple[Mapping[str, object], ...]:
        fields = {
            "schema_version",
            "kind",
            "execution_id",
            "execution_namespace",
            "plan_fingerprint",
            "node_id",
            "claim_id",
            "receipt_digest",
            "final_commit",
            "receipt_timestamp",
            "recorded_at",
            "previous_event_id",
            "event_id",
        }
        previous: str | None = None
        observed_nodes: set[str] = set()
        events: list[Mapping[str, object]] = []
        for index, event in enumerate(
            strict_jsonl_records(
                self.state_dir / "receipt-index.jsonl",
                label="execution terminal receipt index",
            ),
            1,
        ):
            material = dict(event)
            event_id = material.pop("event_id", None)
            node_id = event.get("node_id")
            if (
                set(event) != fields
                or event.get("schema_version") != 1
                or event.get("kind") != "hive-mind-execution-terminal-receipt-v1"
                or event.get("execution_id") != self.execution_id
                or event.get("execution_namespace") != self.execution_namespace
                or event.get("plan_fingerprint") != self.expected_plan_fingerprint
                or not isinstance(node_id, str)
                or node_id not in self._nodes
                or node_id in observed_nodes
                or AUTHORITY_ID.fullmatch(str(event.get("claim_id"))) is None
                or AUTHORITY_ID.fullmatch(str(event.get("receipt_digest"))) is None
                or FULL_SHA.fullmatch(str(event.get("final_commit"))) is None
                or event.get("previous_event_id") != previous
                or event_id != digest_json(material)
            ):
                raise ReceiptError(
                    f"execution terminal receipt index line {index} is invalid"
                )
            try:
                parse_time(event.get("receipt_timestamp"))
                parse_time(event.get("recorded_at"))
            except (TypeError, ValueError) as error:
                raise ReceiptError(
                    f"execution terminal receipt index line {index} has invalid time"
                ) from error
            observed_nodes.add(node_id)
            previous = str(event_id)
            events.append(event)
        return tuple(events)

    def _publish_terminal_receipt_event(
        self,
        node_id: str,
        *,
        claim_id: str,
        receipt: Mapping[str, Any],
    ) -> Mapping[str, object]:
        events = list(self._receipt_terminal_events())
        receipt_digest = digest_json(receipt)
        existing = next(
            (event for event in events if event.get("node_id") == node_id), None
        )
        if existing is not None:
            if (
                existing.get("claim_id") == claim_id
                and existing.get("receipt_digest") == receipt_digest
                and existing.get("final_commit") == receipt.get("final_commit")
                and existing.get("receipt_timestamp") == receipt.get("timestamp")
            ):
                return existing
            raise ReceiptError(
                "node terminal receipt event conflicts with existing authority"
            )
        material: dict[str, object] = {
            "schema_version": 1,
            "kind": "hive-mind-execution-terminal-receipt-v1",
            "execution_id": self.execution_id,
            "execution_namespace": self.execution_namespace,
            "plan_fingerprint": self.expected_plan_fingerprint,
            "node_id": node_id,
            "claim_id": claim_id,
            "receipt_digest": receipt_digest,
            "final_commit": receipt.get("final_commit"),
            "receipt_timestamp": receipt.get("timestamp"),
            "recorded_at": format_time(self.clock()),
            "previous_event_id": events[-1]["event_id"] if events else None,
        }
        event = {**material, "event_id": digest_json(material)}
        append_jsonl(self.state_dir / "receipt-index.jsonl", event)
        return event

    def completed(self, node_id: str) -> bool:
        receipt = self.stored_receipt(node_id)
        if receipt is None:
            return False
        return not self.validate_receipt(node_id, receipt, require_integrated=True)

    def _claim_conflicts(
        self, node_id: str, claims: Mapping[str, Mapping[str, Any]]
    ) -> tuple[str, ...]:
        node = self.node(node_id)
        conflicts: list[str] = []
        for other_id in claims:
            if other_id == node_id:
                continue
            other = self.node(other_id)
            if any(
                scopes_overlap(first, second)
                for first in node.get("file_locks", [])
                for second in other.get("file_locks", [])
            ):
                conflicts.append(f"file lock conflicts with {other_id}")
            shared_semantic = set(node.get("semantic_locks", [])) & set(
                other.get("semantic_locks", [])
            )
            if shared_semantic:
                conflicts.append(
                    f"semantic lock conflicts with {other_id}: "
                    + ", ".join(sorted(shared_semantic))
                )
        return tuple(conflicts)

    def _cross_namespace_claim_conflicts(self, node_id: str) -> tuple[str, ...]:
        """Compare typed arbiter claims without interpreting another plan's node ID."""

        candidate = self.node(node_id)
        target = _require_mapping(self.control.get("target"), "control-plane.target")
        repository = _require_nonempty_text(target.get("repository"), "target.repository")
        conflicts: list[str] = []
        if not self.claims_dir.is_dir():
            return ()
        now = self.clock()
        for path in sorted(self.claims_dir.glob("*.json")):
            value, expires, _raw = read_claim_authority_file(path)
            if expires <= now or value.get("execution_id") == self.execution_id:
                continue
            if value.get("repository") != repository:
                continue
            other_files = value.get("file_locks")
            other_semantic = value.get("semantic_locks")
            if not isinstance(other_files, list) or not isinstance(other_semantic, list):
                raise ClaimError(
                    "cross-namespace claim lacks typed conflict inventory"
                )
            if value.get("branch") == candidate.get("branch"):
                conflicts.append(
                    f"branch conflicts with claim {value.get('claim_id')}"
                )
            if any(
                scopes_overlap(str(first), str(second))
                for first in candidate.get("file_locks", [])
                for second in other_files
            ):
                conflicts.append(
                    f"file scope conflicts with claim {value.get('claim_id')}"
                )
            shared = set(str(item) for item in candidate.get("semantic_locks", [])) & set(
                str(item) for item in other_semantic
            )
            if shared:
                conflicts.append(
                    f"semantic scope conflicts with claim {value.get('claim_id')}: "
                    + ", ".join(sorted(shared))
                )
        return tuple(conflicts)

    def node_view(self, node_id: str) -> NodeView:
        node = self.node(node_id)
        receipt = self.stored_receipt(node_id)
        if receipt is not None:
            receipt_issues = self.validate_receipt(
                node_id, receipt, require_integrated=True
            )
            if not receipt_issues:
                return NodeView(
                    node_id,
                    "COMPLETE",
                    (),
                    tuple(node.get("dependencies", [])),
                    branch=str(node.get("branch")),
                    pr_number=(
                        int(receipt.get("pr"))
                        if isinstance(receipt.get("pr"), int)
                        else None
                    ),
                )
        if self.is_quarantined(node_id):
            return NodeView(
                node_id,
                "QUARANTINED",
                ("repeated failure or policy violation",),
                tuple(node.get("dependencies", [])),
                branch=str(node.get("branch")),
            )
        if self.is_escalated(node_id):
            return NodeView(
                node_id,
                "ESCALATION_REQUIRED",
                ("worker preserved an escalation packet",),
                tuple(node.get("dependencies", [])),
                branch=str(node.get("branch")),
            )
        if node_id == "BOOT-000" and receipt is None:
            return NodeView(
                node_id,
                "BOOTSTRAP_REQUIRED",
                ("install and validate the repository-resident control plane",),
                (),
                branch=str(node.get("branch")),
            )
        if self.target_requires_reconciliation():
            return NodeView(
                node_id,
                "RECONCILIATION_REQUIRED",
                (
                    f"target advanced from {self.reconciled_target_sha()} to "
                    f"{self.current_target_sha()}",
                ),
                tuple(node.get("dependencies", [])),
                branch=str(node.get("branch")),
            )
        pr = self.github_pr_for_node(node_id)
        if pr is not None:
            number = pr.get("number")
            pr_number = int(number) if isinstance(number, int) else None
            state = pr.get("state")
            merged = pr.get("merged") is True
            ci = pr.get("ci")
            if merged and receipt is None:
                return NodeView(
                    node_id,
                    "WAITING_FOR_RECEIPT",
                    ("PR merged but no validated completion receipt is installed",),
                    tuple(node.get("dependencies", [])),
                    branch=str(node.get("branch")),
                    pr_number=pr_number,
                )
            if state == "open" and ci == "failure":
                return NodeView(
                    node_id,
                    "CI_FAILED",
                    ("open node PR has failing CI",),
                    tuple(node.get("dependencies", [])),
                    branch=str(node.get("branch")),
                    pr_number=pr_number,
                )
            if state == "open":
                return NodeView(
                    node_id,
                    "PR_OPEN",
                    ("node PR is open",),
                    tuple(node.get("dependencies", [])),
                    branch=str(node.get("branch")),
                    pr_number=pr_number,
                )
            if state == "closed" and not merged:
                return NodeView(
                    node_id,
                    "REPAIR_REQUIRED",
                    ("node PR was closed without integration",),
                    tuple(node.get("dependencies", [])),
                    branch=str(node.get("branch")),
                    pr_number=pr_number,
                )
        branch = self.branch_snapshot(str(node.get("branch")))
        if branch is not None and branch.get("stale") is True:
            return NodeView(
                node_id,
                "REPAIR_REQUIRED",
                ("node branch is stale relative to target",),
                tuple(node.get("dependencies", [])),
                branch=str(node.get("branch")),
            )
        claims = self.active_claims()
        claim = claims.get(node_id)
        if claim is not None:
            status = claim.get("status")
            state = "RUNNING" if status == "RUNNING" else "CLAIMED"
            return NodeView(
                node_id,
                state,
                (),
                tuple(node.get("dependencies", [])),
                active_claim_owner=(
                    str(claim.get("owner")) if claim.get("owner") else None
                ),
                branch=str(node.get("branch")),
            )
        dependency_states = {
            dependency: self.node_view(dependency).state
            for dependency in node.get("dependencies", [])
        }
        incomplete = [
            dependency
            for dependency, state in dependency_states.items()
            if state != "COMPLETE"
        ]
        if incomplete:
            return NodeView(
                node_id,
                "BLOCKED",
                ("incomplete dependencies: " + ", ".join(incomplete),),
                tuple(node.get("dependencies", [])),
                branch=str(node.get("branch")),
            )
        conflicts = self._claim_conflicts(node_id, claims)
        conflicts += self._cross_namespace_claim_conflicts(node_id)
        if conflicts:
            return NodeView(
                node_id,
                "BLOCKED",
                conflicts,
                tuple(node.get("dependencies", [])),
                branch=str(node.get("branch")),
            )
        if node.get("category") == "integration":
            state = "INTEGRATION_READY"
        elif node.get("category") == "promotion":
            state = "PROMOTION_READY"
        else:
            state = "READY"
        return NodeView(
            node_id,
            state,
            (),
            tuple(node.get("dependencies", [])),
            branch=str(node.get("branch")),
        )

    @contextmanager
    def snapshot_cache(self):
        """Reuse immutable Git facts for one point-in-time observation.

        Installs the same per-call caches ``_status_document`` has always used —
        dependency recursion, durable receipt reconstruction, and read-only Git
        facts — so other observation paths (prompt rendering, claim eligibility,
        receipt verification) do not replay thousands of Git subprocesses. The
        caches live on the instance only for the ``with`` body and must never
        span a state mutation that could change the cached truth.
        """
        missing = object()
        installed: list[tuple[str, object]] = []

        def install(name: str, value: object) -> None:
            installed.append((name, self.__dict__.get(name, missing)))
            setattr(self, name, value)

        uncached_git = self._git
        git_cache: dict[
            tuple[tuple[str, ...], bool, tuple[tuple[str, str], ...]],
            subprocess.CompletedProcess[str],
        ] = {}

        def cached_git(
            args: Sequence[str],
            *,
            check: bool = False,
            environment: Mapping[str, str] | None = None,
        ) -> subprocess.CompletedProcess[str]:
            if not args or args[0] not in _STATUS_READ_ONLY_GIT_COMMANDS:
                return uncached_git(args, check=check, environment=environment)
            key = (tuple(args), check, tuple(sorted((environment or {}).items())))
            if key not in git_cache:
                git_cache[key] = uncached_git(
                    args,
                    check=check,
                    environment=environment,
                )
            return git_cache[key]

        install("_git", cached_git)
        try:
            target = self.current_target_sha()
            reconciled_target = self.reconciled_target_sha()
            install("current_target_sha", lambda: target)
            install("reconciled_target_sha", lambda: reconciled_target)

            graph: _StatusCommitGraph | None = None
            if self.verify_git_objects and FULL_SHA.fullmatch(target):
                history = self._git(
                    ("log", "--format=%H%x1f%P%x1f%T%x1f%B%x1e", target),
                    check=False,
                )
                if history.returncode == 0:
                    candidate_graph = _StatusCommitGraph.from_log(history.stdout)
                    if target in candidate_graph.parents:
                        graph = candidate_graph
            if graph is not None:
                uncached_object_exists = self.git_object_exists
                uncached_is_ancestor = self.is_ancestor

                def cached_object_exists(sha: str) -> bool:
                    if sha in graph.trees:
                        return True
                    return uncached_object_exists(sha)

                def cached_is_ancestor(ancestor: str, descendant: str) -> bool:
                    observed = graph.is_ancestor(ancestor, descendant)
                    if observed is not None:
                        return observed
                    return uncached_is_ancestor(ancestor, descendant)

                install("git_object_exists", cached_object_exists)
                install("is_ancestor", cached_is_ancestor)

                if hasattr(self, "_commit_tree"):
                    uncached_commit_tree = self._commit_tree

                    def cached_commit_tree(commit: str) -> str | None:
                        tree = graph.trees.get(commit)
                        return tree if tree is not None else uncached_commit_tree(commit)

                    install("_commit_tree", cached_commit_tree)
                if hasattr(self, "_commit_parents"):
                    uncached_commit_parents = self._commit_parents

                    def cached_commit_parents(commit: str) -> tuple[str, ...]:
                        parents = graph.parents.get(commit)
                        return (
                            parents
                            if parents is not None
                            else uncached_commit_parents(commit)
                        )

                    install("_commit_parents", cached_commit_parents)

            active_claims = self.active_claims()
            github_snapshot = self.github_snapshot()
            install("active_claims", lambda: dict(active_claims))
            install("github_snapshot", lambda: github_snapshot)

            if hasattr(self, "_durable_receipt_records"):
                uncached_durable_receipts = self._durable_receipt_records
                durable_receipts: dict[str, list[dict[str, Any]]] | None = None

                def cached_durable_receipts() -> dict[str, list[dict[str, Any]]]:
                    nonlocal durable_receipts
                    if durable_receipts is None:
                        durable_receipts = uncached_durable_receipts()
                    return durable_receipts

                install("_durable_receipt_records", cached_durable_receipts)

            uncached_node_view = self.node_view
            view_cache: dict[str, NodeView] = {}

            def cached_node_view(node_id: str) -> NodeView:
                if node_id not in view_cache:
                    view_cache[node_id] = uncached_node_view(node_id)
                return view_cache[node_id]

            install("node_view", cached_node_view)
            yield
        finally:
            for name, prior in reversed(installed):
                if prior is missing:
                    self.__dict__.pop(name, None)
                else:
                    setattr(self, name, prior)

    def _status_document(self) -> dict[str, object]:
        # Status is a point-in-time observation over a DAG with substantial fan-in.
        # Every expensive fact is scoped to this call through snapshot_cache so a
        # stale truth can never leak into the next snapshot.
        with self.snapshot_cache():
            target = self.current_target_sha()
            changed = self.changed_paths_since_reconciliation()
            active_claims = self.active_claims()

            validation_lease: Mapping[str, Any] | None = None
            expired_validation_lease: Mapping[str, Any] | None = None
            if self.validation_lease_path.is_file():
                ensure_repository_runtime_identity(
                    self.repo_root,
                    self.coordination_dir,
                    create=False,
                )
                candidate = read_json(self.validation_lease_path)
                if not isinstance(candidate, Mapping):
                    raise ConfigurationError("global validation lease is malformed")
                try:
                    validation_expires = parse_time(candidate.get("expires_at"))
                except (TypeError, ValueError) as error:
                    raise ConfigurationError(
                        "global validation lease expiry is malformed; reconciliation is required"
                    ) from error
                if validation_expires > self.clock():
                    validation_lease = candidate
                else:
                    expired_validation_lease = candidate

            views = [self.node_view(node_id) for node_id in sorted(self._nodes)]
            last_reconciled = self.reconciled_target_sha()
            reconciliation_required = self.target_requires_reconciliation()
        with self.arbiter_lock(timeout_seconds=120.0):
            legacy_quarantines = (
                _legacy_authority_quarantine_obligations_unlocked(
                    self.coordination_dir
                )
            )
        counts: dict[str, int] = {state: 0 for state in LEGAL_STATES}
        for view in views:
            counts[view.state] = counts.get(view.state, 0) + 1
        ready = [
            view.node_id
            for view in views
            if view.state in {"READY", "INTEGRATION_READY", "PROMOTION_READY"}
        ]
        stale_hosted_claims, unclassified_active_claims = self._claim_authority_status(
            active_claims
        )
        (
            stale_hosted_validation_leases,
            unclassified_validation_leases,
        ) = self._validation_authority_status(validation_lease, active_claims)
        validation_lease_recovery_required = expired_validation_lease is not None
        authority_reconciliation_required = bool(
            stale_hosted_claims
            or unclassified_active_claims
            or stale_hosted_validation_leases
            or unclassified_validation_leases
            or validation_lease_recovery_required
            or legacy_quarantines
        )
        affected_authority_nodes = {
            str(item.get("node_id"))
            for item in (
                *stale_hosted_claims,
                *unclassified_active_claims,
                *stale_hosted_validation_leases,
                *unclassified_validation_leases,
                *([expired_validation_lease] if expired_validation_lease is not None else []),
            )
        }
        ready = [node_id for node_id in ready if node_id not in affected_authority_nodes]
        return {
            "schema_version": SCHEMA_VERSION,
            "plan_id": self.plan.get("plan_id"),
            "plan_fingerprint": self.expected_plan_fingerprint,
            "target_branch": self.target_branch,
            "target_sha": target,
            "last_reconciled_sha": last_reconciled,
            "reconciliation_required": (
                reconciliation_required or authority_reconciliation_required
            ),
            "claim_authority_reconciliation_required": authority_reconciliation_required,
            "changed_paths_since_reconciliation": list(changed),
            "counts": {key: value for key, value in counts.items() if value},
            "ready": ready,
            "nodes": [view.to_dict() for view in views],
            "complete": (
                all(view.state in TERMINAL_STATES for view in views)
                and not authority_reconciliation_required
            ),
            "active_claims": sorted(active_claims),
            "stale_hosted_claims": stale_hosted_claims,
            "unclassified_active_claims": unclassified_active_claims,
            "stale_hosted_validation_leases": stale_hosted_validation_leases,
            "unclassified_validation_leases": unclassified_validation_leases,
            "validation_lease_recovery_required": validation_lease_recovery_required,
            "legacy_authority_quarantine_obligations": [
                dict(item) for item in legacy_quarantines
            ],
            "active_validation_lease": (
                dict(validation_lease) if validation_lease is not None else None
            ),
            "expired_validation_lease": (
                dict(expired_validation_lease)
                if expired_validation_lease is not None
                else None
            ),
            "generated_at": format_time(self.clock()),
        }

    def observe_status(self) -> dict[str, object]:
        """Return controller truth without reaping or otherwise mutating state."""

        return self._status_document()

    def status(self) -> dict[str, object]:
        self.clean_stale_claims()
        return self._status_document()

    def ready_nodes(self) -> tuple[str, ...]:
        status = self.status()
        ready = status["ready"]
        assert isinstance(ready, list)
        return tuple(str(item) for item in ready)

    def reconcile_orphan_sidecar_reservations(
        self,
        *,
        actor: str,
        reason: str,
        limit: int | None = None,
    ) -> tuple[Mapping[str, object], ...]:
        """Fence local orphans; host capacity waits for lifecycle reconciliation.

        ORPHANED revokes repository effects but does not prove that the external
        process stopped consuming a machine-global host slot. The permit remains
        active until ``recover_expired_host_reservation`` receives authenticated
        host lifecycle evidence.
        """

        if not actor.strip() or not reason.strip():
            raise AutopilotError("orphan reconciliation requires actor and reason")
        from orchestration import OrchestrationError, reconcile_orphaned_sidecars

        with self.host_lock(timeout_seconds=120.0):
            with self.arbiter_lock(timeout_seconds=120.0):
                with self.execution_lock(
                    "dispatcher-admission.lock", timeout_seconds=120.0
                ):
                    try:
                        recovered = reconcile_orphaned_sidecars(
                            self.repo_root,
                            actor=actor,
                            reason=reason,
                            limit=limit,
                            state_dir=self.execution_dir,
                        )
                    except OrchestrationError as error:
                        raise AutopilotError(str(error)) from error
        return tuple(recovered)

    @property
    def plan_terminal_fence_path(self) -> Path:
        return self.execution_dir / "plan-terminal-fence.json"

    def _read_plan_terminal_fence_unlocked(self) -> Mapping[str, object] | None:
        path = self.plan_terminal_fence_path
        if not path.exists() and not _is_link_like(path):
            return None
        _reject_link_components(path, label="plan terminal fence")
        if not path.is_file():
            raise AutopilotError("plan terminal fence is not a regular file")
        value = read_json(path)
        if not isinstance(value, Mapping) or set(value) != PLAN_TERMINAL_FENCE_FIELDS:
            raise AutopilotError("plan terminal fence schema is ambiguous")
        material = dict(value)
        record_id = material.pop("record_id", None)
        observation_material = {
            "kind": PLAN_TERMINAL_FENCE_OBSERVATION_KIND,
            "execution_id": value.get("execution_id"),
            "execution_namespace": value.get("execution_namespace"),
            "release_id": value.get("release_id"),
            "admission_epoch": value.get("admission_epoch"),
            "target_sha": value.get("target_sha"),
            "target_generation": value.get("target_generation"),
            "target_watermark_record_id": value.get(
                "target_watermark_record_id"
            ),
            "plan_fingerprint": value.get("plan_fingerprint"),
            "authority_digest": value.get("authority_digest"),
        }
        try:
            parse_time(value.get("sealed_at"))
        except (TypeError, ValueError) as error:
            raise AutopilotError("plan terminal fence timestamp is invalid") from error
        if (
            value.get("schema_version") != 1
            or value.get("kind") != PLAN_TERMINAL_FENCE_KIND
            or value.get("execution_id") != self.execution_id
            or value.get("execution_namespace") != self.execution_namespace
            or AUTHORITY_ID.fullmatch(str(value.get("release_id"))) is None
            or type(value.get("admission_epoch")) is not int
            or int(value["admission_epoch"]) < 1
            or FULL_SHA.fullmatch(str(value.get("target_sha"))) is None
            or type(value.get("target_generation")) is not int
            or int(value["target_generation"]) < 1
            or AUTHORITY_ID.fullmatch(
                str(value.get("target_watermark_record_id"))
            )
            is None
            or value.get("plan_fingerprint") != self.expected_plan_fingerprint
            or AUTHORITY_ID.fullmatch(str(value.get("authority_digest"))) is None
            or value.get("controller_observation_id")
            != digest_json(observation_material)
            or not isinstance(value.get("sealed_by"), str)
            or not str(value["sealed_by"]).strip()
            or value.get("state") != "PLAN_QUIESCENT"
            or record_id != digest_json(material)
        ):
            raise AutopilotError("plan terminal fence identity or digest is invalid")
        return dict(value)

    def _assert_publication_not_indeterminate_unlocked(self) -> None:
        provider = getattr(self, "_publication_resource_path", None)
        if not callable(provider):
            return
        path = provider()
        if not path.is_file() and not _is_link_like(path):
            return
        _reject_link_components(path, label="publication target reservation")
        value = read_json(path)
        if not isinstance(value, Mapping):
            raise AutopilotError("publication target reservation is malformed")
        material = dict(value)
        record_id = material.pop("record_id", None)
        if record_id != digest_json(material):
            raise AutopilotError("publication target reservation digest is invalid")
        if value.get("status") == "PUBLISH_UNKNOWN":
            raise AutopilotError(
                "publication outcome is indeterminate; execution admission is fenced"
            )

    def plan_terminal_fence(self) -> Mapping[str, object] | None:
        """Read the immutable execution terminal fence without creating it."""

        with self.execution_lock(
            "dispatcher-admission.lock", timeout_seconds=120.0
        ):
            with self._validation_authority_locks():
                return self._read_plan_terminal_fence_unlocked()

    def seal_plan_quiescent(
        self,
        release_id: str,
        *,
        actor: str,
        expected_authority_digest: str,
    ) -> Mapping[str, object]:
        """Close execution admission on the exact verified fixed-point cut.

        The fence is installed while validation admission is serialized.  Once
        this returns, a validator racing immediately after the zero-lease cut is
        rejected rather than turning an instantaneous observation into a false
        terminal result.
        """

        if not isinstance(actor, str) or not actor.strip():
            raise AutopilotError("plan terminal fence actor is required")
        if AUTHORITY_ID.fullmatch(release_id) is None:
            raise AutopilotError("plan terminal fence release id is invalid")
        if AUTHORITY_ID.fullmatch(expected_authority_digest) is None:
            raise AutopilotError("plan terminal authority digest is invalid")
        # Git/receipt reconstruction is observed before authority locks. The
        # locked cut below revalidates every admission surface and the release
        # target; a concurrent completion may cause a conservative retry but
        # can never produce a false terminal result.
        observed_status = self._status_document()
        with self.host_lock(timeout_seconds=120.0):
            with self.arbiter_lock(timeout_seconds=120.0):
                with self.execution_lock(
                    "dispatcher-admission.lock", timeout_seconds=120.0
                ):
                    installed_before_cut = self._read_plan_terminal_fence_unlocked()
                    if installed_before_cut is not None:
                        if installed_before_cut.get("release_id") != release_id:
                            raise AutopilotError(
                                "execution is terminal under another dispatcher release"
                            )
                        return installed_before_cut
                    # Every claim, validation, launch/effect and publication
                    # admission is serialized by dispatcher authority.  Capture
                    # the binding -> claim -> validation inventory while this
                    # outer fence remains held, then reacquire only the tail to
                    # install the immutable terminal record.  This avoids the
                    # former validation -> binding inversion without opening a
                    # post-cut admission window.
                    snapshot = self.round_authority_snapshot(
                        release_id, _observed_status=observed_status
                    )
                    with self._validation_authority_locks():
                        installed = self._read_plan_terminal_fence_unlocked()
                        if installed is not None:
                            if installed.get("release_id") != release_id:
                                raise AutopilotError(
                                    "execution is terminal under another dispatcher release"
                                )
                            return installed
                        if snapshot.get("authority_digest") != expected_authority_digest:
                            raise AutopilotError(
                                "round authority changed before terminal fencing"
                            )
                        status = snapshot.get("status")
                        if not isinstance(status, Mapping) or status.get("complete") is not True:
                            raise AutopilotError("plan is not complete at the terminal cut")
                        blocking_fields = (
                            "active_write_launch_reservations",
                            "active_host_reservations",
                            "execution_global_host_reservations",
                            "active_claims",
                            "active_validation_lease",
                            "publication_transaction_fence",
                            "active_publication_count",
                            "conflicting_global_reservations",
                            "reconciliation_obligations",
                            "host_effect_obligations",
                        )
                        blocked = [
                            field for field in blocking_fields if snapshot.get(field)
                        ]
                        if status.get("reconciliation_required") or blocked:
                            raise AutopilotError(
                                "plan terminal cut is not quiescent: "
                                + ", ".join(blocked or ["status reconciliation"])
                            )
                        release = snapshot.get("release")
                        if not isinstance(release, Mapping):
                            raise AutopilotError("terminal cut release evidence is absent")
                        observation_material = {
                            "kind": PLAN_TERMINAL_FENCE_OBSERVATION_KIND,
                            "execution_id": self.execution_id,
                            "execution_namespace": self.execution_namespace,
                            "release_id": release_id,
                            "admission_epoch": release.get("admission_epoch"),
                            "target_sha": release.get("target_sha"),
                            "target_generation": release.get("target_generation"),
                            "target_watermark_record_id": release.get(
                                "target_watermark_record_id"
                            ),
                            "plan_fingerprint": self.expected_plan_fingerprint,
                            "authority_digest": expected_authority_digest,
                        }
                        fence: dict[str, object] = {
                            "schema_version": 1,
                            "kind": PLAN_TERMINAL_FENCE_KIND,
                            **{
                                key: observation_material[key]
                                for key in (
                                    "execution_id",
                                    "execution_namespace",
                                    "release_id",
                                    "admission_epoch",
                                    "target_sha",
                                    "target_generation",
                                    "target_watermark_record_id",
                                    "plan_fingerprint",
                                    "authority_digest",
                                )
                            },
                            "controller_observation_id": digest_json(
                                observation_material
                            ),
                            "sealed_by": actor.strip(),
                            "sealed_at": format_time(self.clock()),
                            "state": "PLAN_QUIESCENT",
                        }
                        fence["record_id"] = digest_json(fence)
                        exclusive_write_json_or_identical(
                            self.plan_terminal_fence_path, fence
                        )
                        return self._read_plan_terminal_fence_unlocked() or fence

    def round_authority_snapshot(
        self,
        release_id: str,
        *,
        _observed_status: Mapping[str, object] | None = None,
    ) -> Mapping[str, object]:
        """Return one typed, short-held host/repository/execution authority snapshot."""

        if AUTHORITY_ID.fullmatch(release_id) is None:
            raise AutopilotError("round authority release id is invalid")
        current_release = getattr(self, "current_release", None)
        release_issues = getattr(self, "_release_issues", None)
        if not callable(current_release) or not callable(release_issues):
            raise AutopilotError("round authority requires a dispatcher release adapter")
        from orchestration import (
            OrchestrationError,
            active_host_reservations,
            active_write_launch_reservations,
            binding_authority_guard,
            binding_events,
            orphaned_sidecar_obligations,
        )
        from sidecar_execution import latest_sidecars

        status = (
            dict(_observed_status)
            if _observed_status is not None
            else self._status_document()
        )

        with self.host_lock(timeout_seconds=120.0):
            global_reservations = active_global_host_reservations(
                self.host_runtime_dir
            )
            with self.arbiter_lock(timeout_seconds=120.0):
                legacy_quarantines = (
                    _legacy_authority_quarantine_obligations_unlocked(
                        self.coordination_dir
                    )
                )
                with self.execution_lock(
                    "dispatcher-admission.lock", timeout_seconds=120.0
                ):
                    release = current_release()
                    issues = tuple(str(item) for item in release_issues(release))
                    if issues:
                        raise AutopilotError(
                            "round dispatcher release is invalid: " + "; ".join(issues)
                        )
                    if (
                        not isinstance(release, Mapping)
                        or release.get("release_id") != release_id
                        or type(release.get("admission_epoch")) is not int
                        or int(release["admission_epoch"]) < 1
                        or type(release.get("target_generation")) is not int
                        or int(release["target_generation"]) < 1
                        or AUTHORITY_ID.fullmatch(
                            str(release.get("target_watermark_record_id"))
                        )
                        is None
                    ):
                        raise AutopilotError("round dispatcher release fence mismatch")
                    target_watermark = _read_repository_target_watermark_unlocked(
                        self.coordination_dir,
                        repository_identity=self.repository_identity,
                        target_branch=self.target_branch,
                    )
                    if (
                        release.get("target_sha")
                        != target_watermark.get("target_sha")
                        or release.get("target_generation")
                        != target_watermark.get("target_generation")
                        or release.get("target_watermark_record_id")
                        != target_watermark.get("record_id")
                    ):
                        raise AutopilotError(
                            "round dispatcher release is stale against repository target authority"
                        )
                    # One binding lock spans launch, sidecar and host-effect
                    # inventories.  It remains inside dispatcher authority and
                    # outside claim/validation, matching the canonical order.
                    with binding_authority_guard(
                        self.repo_root, state_dir=self.execution_dir
                    ):
                        try:
                            writes = active_write_launch_reservations(
                                self.repo_root,
                                execution_dir=self.execution_dir,
                                execution_id=self.execution_id,
                                execution_namespace=self.execution_namespace,
                            )
                            hosts = active_host_reservations(
                                self.repo_root,
                                execution_dir=self.execution_dir,
                                execution_id=self.execution_id,
                                execution_namespace=self.execution_namespace,
                            )
                            orphans = orphaned_sidecar_obligations(
                                self.repo_root,
                                state_dir=self.execution_dir,
                            )
                            all_bindings = binding_events(
                                self.repo_root, state_dir=self.execution_dir
                            )
                            sidecars = latest_sidecars(
                                self.repo_root, state_dir=self.execution_dir
                            )
                            host_effects = execution_host_effect_obligations(
                                self.execution_dir
                            )
                        except (ConfigurationError, OrchestrationError) as error:
                            raise AutopilotError(str(error)) from error
                        # Claim and validation mutation share this exact tail of
                        # the canonical lock order. Holding both makes the
                        # zero-lease observation a durable admission cut.
                        with self._validation_authority_locks():
                            claims = self.active_claims()
                            validation_lease = (
                                read_json(self.validation_lease_path)
                                if self.validation_lease_path.is_file()
                                else None
                            )
                            if validation_lease is not None:
                                if (
                                    not isinstance(validation_lease, Mapping)
                                    or validation_lease.get("execution_id")
                                    != self.execution_id
                                    or validation_lease.get("validation_resource_key")
                                    != self.validation_resource_key
                                    or AUTHORITY_ID.fullmatch(
                                        str(validation_lease.get("lease_id"))
                                    )
                                    is None
                                ):
                                    raise AutopilotError(
                                        "round validation lease authority is malformed"
                                    )
                            publication_resource: Mapping[str, object] | None = None
                            publication_path_provider = getattr(
                                self, "_publication_resource_path", None
                            )
                            if callable(publication_path_provider):
                                publication_path = publication_path_provider()
                                if publication_path.is_file():
                                    candidate = read_json(publication_path)
                                    if not isinstance(candidate, Mapping):
                                        raise AutopilotError(
                                            "publication target reservation is malformed"
                                        )
                                    sealed = dict(candidate)
                                    record_id = sealed.pop("record_id", None)
                                    if record_id != digest_json(sealed):
                                        raise AutopilotError(
                                            "publication target reservation digest is invalid"
                                        )
                                    publication_resource = dict(candidate)
                            terminal_fence = self._read_plan_terminal_fence_unlocked()
                            # Git/receipt reconstruction occurred before locks.
                            # The locked release/claim/lease inventories below
                            # are the admission cut and can only turn a
                            # concurrent status advance into a conservative retry.
                            if status.get("target_sha") != release.get("target_sha"):
                                raise AutopilotError(
                                    "round status target differs from dispatcher authority"
                                )
            local_ids: set[str] = set()
            local_by_reservation_id: dict[str, Mapping[str, object]] = {}
            for item in hosts:
                reservation_id = item.get("host_reservation_id")
                if not isinstance(reservation_id, str) or AUTHORITY_ID.fullmatch(
                    reservation_id
                ) is None:
                    raise AutopilotError(
                        "execution host reservation lacks its global reservation id"
                    )
                if reservation_id in local_by_reservation_id:
                    raise AutopilotError(
                        "execution host inventory duplicates a global reservation id"
                    )
                local_ids.add(reservation_id)
                local_by_reservation_id[reservation_id] = item
            execution_globals = tuple(
                item
                for item in global_reservations
                if item.get("execution_id") == self.execution_id
            )
            global_ids = {
                str(item.get("reservation_id"))
                for item in execution_globals
                if item.get("reservation_kind") in {"PRIMARY", "SIDECAR"}
            }
            global_by_reservation_id = {
                str(item.get("reservation_id")): item
                for item in execution_globals
                if item.get("reservation_kind") in {"PRIMARY", "SIDECAR"}
            }
            obligations: list[Mapping[str, object]] = []
            for missing in sorted(local_ids - global_ids):
                obligations.append(
                    {"kind": "MISSING_GLOBAL_RESERVATION", "local_reservation_id": missing}
                )
            for orphan in sorted(global_ids - local_ids):
                obligations.append(
                    {"kind": "ORPHAN_GLOBAL_RESERVATION", "reservation_id": orphan}
                )
            for shared_id in sorted(local_ids & global_ids):
                local_item = local_by_reservation_id[shared_id]
                global_item = global_by_reservation_id[shared_id]
                mismatched = tuple(
                    field
                    for field in (
                        "host_kernel_generation",
                        "execution_adapter_identity_record_id",
                        "execution_adapter_identity_path",
                        "execution_adapter_identity_blob_digest",
                    )
                    if local_item.get(field) != global_item.get(field)
                )
                if mismatched:
                    obligations.append(
                        {
                            "kind": "HOST_RESERVATION_PROVENANCE_MISMATCH",
                            "reservation_id": shared_id,
                            "fields": list(mismatched),
                        }
                    )
            obligations.extend(
                {
                    "kind": "ORPHAN_SIDECAR",
                    "sidecar_id": item.get("sidecar_id"),
                    "parent_launch_instruction_id": item.get(
                        "parent_launch_instruction_id"
                    ),
                }
                for item in orphans
            )
            obligations.extend(
                {
                    "kind": "HOST_EFFECT_RECONCILIATION",
                    "effect_id": item.get("effect_id"),
                    "effect_kind": item.get("effect_kind"),
                    "state": item.get("state"),
                    "event_id": item.get("event_id"),
                }
                for item in host_effects
            )
            obligations.extend(
                {
                    "kind": "LEGACY_AUTHORITY_QUARANTINE",
                    "record_id": item.get("record_id"),
                    "source_root": item.get("source_root"),
                    "relative_path": item.get("relative_path"),
                    "authority_kind": item.get("authority_kind"),
                    "active_authority_ids": item.get("active_authority_ids"),
                    "reason": item.get("reason"),
                    "external_cancellation": item.get(
                        "external_cancellation"
                    ),
                }
                for item in legacy_quarantines
            )
            repository = str(self.control["target"]["repository"])
            released_wave = tuple(str(item) for item in release.get("released_wave", []))
            expected_resources = {
                str(item.get("resource_key")) for item in writes
            }
            expected_scopes = [
                str(scope)
                for node_id in released_wave
                for scope in self.node(node_id).get("file_locks", [])
            ]
            conflicts: list[Mapping[str, object]] = []
            for item in global_reservations:
                if item.get("execution_id") == self.execution_id:
                    continue
                if item.get("repository") != repository:
                    continue
                item_scopes = item.get("write_scopes")
                if not isinstance(item_scopes, list):
                    raise AutopilotError(
                        "cross-namespace host reservation has no typed scopes"
                    )
                reasons: list[str] = []
                if item.get("resource_key") in expected_resources:
                    reasons.append("RESOURCE_KEY")
                if _scope_conflicts(expected_scopes, [str(scope) for scope in item_scopes]):
                    reasons.append("WRITE_SCOPE")
                if reasons:
                    conflicts.append(
                        {
                            "kind": "HOST_RESERVATION_CONFLICT",
                            "reservation_id": item.get("reservation_id"),
                            "execution_id": item.get("execution_id"),
                            "reasons": reasons,
                        }
                    )
            for node_id in released_wave:
                for issue in self._cross_namespace_claim_conflicts(node_id):
                    conflicts.append(
                        {
                            "kind": "CLAIM_CONFLICT",
                            "node_id": node_id,
                            "reason": issue,
                        }
                    )
            if publication_resource is not None:
                transaction = publication_resource.get("transaction")
                if not isinstance(transaction, Mapping):
                    raise AutopilotError(
                        "publication target reservation lacks its transaction"
                    )
                if (
                    transaction.get("execution_id") != self.execution_id
                    and publication_resource.get("status")
                    in {
                        "PREPARED",
                        "PINNED",
                        "VALIDATED",
                        "PUBLISHING",
                        "PUBLISH_UNKNOWN",
                    }
                ):
                    conflicts.append(
                        {
                            "kind": "PUBLICATION_CONFLICT",
                            "transaction_id": transaction.get("transaction_id"),
                            "execution_id": transaction.get("execution_id"),
                        }
                    )
            capacity_generations: dict[str, Mapping[str, object]] = {}
            capacity_hosts = {
                str(item.get("host_id")) for item in execution_globals
            }
            if isinstance(release.get("host_id"), str):
                capacity_hosts.add(str(release["host_id"]))
            for host_id in sorted(capacity_hosts):
                if host_id not in capacity_generations:
                    capacity_generations[host_id] = read_host_capacity(
                        self.host_runtime_dir, host_id, now=self.clock()
                    )
            release_capacity_issuance: Mapping[str, object] | None = None
            release_host_id = release.get("host_id")
            release_capacity_generation = release.get("capacity_generation")
            release_capacity_record_id = release.get("capacity_record_id")
            if all(
                isinstance(item, str)
                for item in (
                    release_host_id,
                    release_capacity_generation,
                    release_capacity_record_id,
                )
            ):
                release_capacity_issuance = (
                    host_capacity_record_in_current_lineage(
                        self.host_runtime_dir,
                        str(release_host_id),
                        capacity_generation=str(release_capacity_generation),
                        record_id=str(release_capacity_record_id),
                    )
                )
            terminal_bindings_by_id: dict[str, Mapping[str, object]] = {}
            for event in all_bindings:
                instruction = event.get("launch_instruction_id")
                if isinstance(instruction, str):
                    terminal_bindings_by_id[instruction] = event
            terminal_bindings = [
                dict(value)
                for _, value in sorted(terminal_bindings_by_id.items())
                if value.get("state") in {"RELEASED", "SUPERSEDED"}
            ]
            terminal_sidecars = [
                dict(value)
                for _, value in sorted(sidecars.items())
                if value.get("state")
                in {
                    "SUCCEEDED",
                    "FAILED",
                    "CANCELLED",
                    "SPAWN_FAILED",
                    "SKIPPED_CAPACITY",
                    "ORPHANED",
                }
            ]
        stable_status = {
            "nodes": status.get("nodes"),
            "complete": status.get("complete"),
            "ready": status.get("ready"),
            "reconciliation_required": status.get("reconciliation_required"),
        }
        publication_fence: Mapping[str, object] | None = None
        publication_status: str | None = None
        if publication_resource is not None:
            raw_publication_status = publication_resource.get("status")
            publication_status = (
                str(raw_publication_status)
                if isinstance(raw_publication_status, str)
                else None
            )
            transaction = publication_resource["transaction"]
            assert isinstance(transaction, Mapping)
            if publication_status in {
                "PREPARED",
                "PINNED",
                "VALIDATED",
                "PUBLISHING",
                "PUBLISH_UNKNOWN",
            }:
                publication_fence = {
                    field: transaction.get(field)
                    for field in (
                        "transaction_id",
                        "transaction_key",
                        "execution_id",
                        "release_id",
                        "round_id",
                        "repository",
                        "target_branch",
                        "expected_target_sha",
                        "receipt_heads_digest",
                    )
                }
        authoritative = {
            "schema_version": 1,
            "kind": "hive-mind-round-authority-snapshot-v1",
            "execution_id": self.execution_id,
            "execution_namespace": self.execution_namespace,
            "release_id": release_id,
            "admission_epoch": int(release["admission_epoch"]),
            "release": dict(release),
            "repository_target_watermark": dict(target_watermark),
            "active_write_launch_reservations": [dict(item) for item in writes],
            "active_host_reservations": [dict(item) for item in hosts],
            "execution_global_host_reservations": [
                dict(item) for item in execution_globals
            ],
            "host_capacity_generations": {
                key: dict(value) for key, value in sorted(capacity_generations.items())
            },
            "release_capacity_issuance_record": (
                dict(release_capacity_issuance)
                if isinstance(release_capacity_issuance, Mapping)
                else None
            ),
            "active_claims": [dict(claims[key]) for key in sorted(claims)],
            "active_validation_lease": (
                dict(validation_lease)
                if isinstance(validation_lease, Mapping)
                else None
            ),
            "publication_transaction_fence": publication_fence,
            "active_publication_count": 1 if publication_fence is not None else 0,
            "plan_terminal_fence": (
                dict(terminal_fence)
                if isinstance(terminal_fence, Mapping)
                else None
            ),
            "terminal_launch_bindings": terminal_bindings,
            "terminal_sidecar_bindings": terminal_sidecars,
            "active_host_effect_count": len(host_effects),
            "host_effect_obligations": [dict(item) for item in host_effects],
            "host_effect_obligation_digest": digest_json(
                {
                    "kind": "hive-mind-host-effect-obligation-set-v1",
                    "events": [
                        str(item.get("event_id")) for item in host_effects
                    ],
                }
            ),
            "conflicting_global_reservations": conflicts,
            "reconciliation_obligations": obligations,
            "status": stable_status,
        }
        # ``publication_transaction_fence`` deliberately omits mutable status,
        # outcome, and timestamps.  PREPARED -> PUBLISHING is the expected
        # transition between a publisher's before/after revalidation snapshots.
        authoritative["authority_digest"] = digest_json(authoritative)
        authoritative["publication_transaction_status"] = publication_status
        authoritative["observed_at"] = format_time(self.clock())
        return authoritative

    @contextmanager
    def round_admission_guard(self, *, release_id: str):
        """Compatibility shim for a short snapshot, never a long-held lock.

        Publishers persist a target-resource transaction and later compare the
        returned ``authority_digest``. Holding the arbiter through Git,
        integration, or validation would serialize unrelated applications.
        """

        snapshot = self.round_authority_snapshot(release_id)
        if snapshot.get("reconciliation_obligations"):
            raise ClaimError("round admission requires authority reconciliation")
        if snapshot.get("conflicting_global_reservations"):
            raise ClaimError("round admission conflicts with another execution")
        yield snapshot

    @contextmanager
    def dispatcher_launch_authority_guard(
        self,
        node_id: str,
        *,
        host_id: str | None = None,
        release_id: str | None = None,
    ):
        """Extension hook for a release-barrier-aware public control plane.

        The core controller is also used by isolated internal fixtures that do
        not install the dispatcher barrier. The concrete CLI plane overrides
        this hook to acquire ``dispatcher-admission.lock`` and revalidate the
        current shared release. Concrete adapters acquire host -> repository
        arbiter -> execution dispatcher before entering the binding and claim
        locks; this hook must never acquire an outer authority from a binding.
        """

        del node_id, host_id, release_id
        yield None

    @contextmanager
    def claim_launch_authority_guard(
        self,
        node_id: str,
        *,
        claim_authority_class: str,
        launch_instruction_id: str | None,
        resource_key: str | None,
        authority_epoch: int | None,
        host_id: str | None = None,
        _internal_authority: object | None = None,
    ):
        """Validate claim classification before entering claim authority.

        Hosted transitions acquire host/repository/dispatcher admission first,
        then the execution binding and claim locks. Privileged controller work
        is deliberately explicit and may not smuggle hosted launch coordinates.
        """

        if claim_authority_class not in CLAIM_AUTHORITY_CLASSES:
            raise ClaimError("claim authority class is invalid")
        values = (launch_instruction_id, resource_key, authority_epoch)
        if claim_authority_class == INTERNAL_CLAIM_AUTHORITY:
            if _internal_authority is not _INTERNAL_CLAIM_CAPABILITY:
                raise ClaimError(
                    "privileged internal claim authority is not available to hosted callers"
                )
            if any(value is not None for value in values):
                raise ClaimError(
                    "privileged internal claims cannot carry hosted launch authority"
                )
            with self.execution_lock(
                "dispatcher-admission.lock", timeout_seconds=120.0
            ):
                assert_execution_authority_open(self.execution_dir)
                yield None
            return
        if (
            not isinstance(launch_instruction_id, str)
            or AUTHORITY_ID.fullmatch(launch_instruction_id) is None
            or not isinstance(resource_key, str)
            or AUTHORITY_ID.fullmatch(resource_key) is None
            or type(authority_epoch) is not int
            or authority_epoch < 1
        ):
            raise ClaimError(
                "hosted claims require an exact launch instruction, resource key, and epoch"
            )
        # Lazy import avoids controller <-> orchestration import initialization.
        from orchestration import OrchestrationError, launch_authority_guard

        try:
            with self.dispatcher_launch_authority_guard(
                node_id, host_id=host_id
            ) as release:
                with launch_authority_guard(
                    self.repo_root,
                    launch_instruction_id,
                    resource_key=resource_key,
                    authority_epoch=authority_epoch,
                    state_dir=self.execution_dir,
                ) as binding:
                    if binding.get("node_id") != node_id:
                        raise ClaimError("hosted claim node does not match its launch binding")
                    if host_id is not None and binding.get("capacity_host_id") != host_id:
                        raise ClaimError("hosted claim capacity host differs from its binding")
                    if binding.get("authority_class") != "WRITE_AUTHORIZED":
                        raise ClaimError("hosted claim requires write-authorized launch authority")
                    if binding.get("state") in {"PREPARED", "CREATED"}:
                        raise ClaimError(
                            "hosted claim requires an exact bound host task"
                        )
                    if isinstance(release, Mapping) and (
                        release.get("release_id") != binding.get("dispatcher_release_id")
                        or release.get("admission_epoch")
                        != binding.get("dispatcher_admission_epoch")
                    ):
                        raise ClaimError("hosted claim dispatcher fence differs from binding")
                    yield binding
        except OrchestrationError as error:
            raise ClaimError(f"hosted launch authority is stale or revoked: {error}") from error

    @staticmethod
    def _claim_authority_fields(
        *,
        claim_authority_class: str,
        launch_instruction_id: str | None,
        resource_key: str | None,
        authority_epoch: int | None,
    ) -> Mapping[str, object]:
        return {
            "claim_authority_class": claim_authority_class,
            "launch_instruction_id": launch_instruction_id,
            "resource_key": resource_key,
            "authority_epoch": authority_epoch,
        }

    def claim(
        self,
        node_id: str,
        owner: str,
        *,
        claim_authority_class: str,
        launch_instruction_id: str | None = None,
        resource_key: str | None = None,
        authority_epoch: int | None = None,
        host_id: str | None = None,
        _internal_authority: object | None = None,
        lease_minutes: int = 90,
        publish_remote: bool = False,
        remote: str = "origin",
    ) -> Mapping[str, Any]:
        with self.claim_launch_authority_guard(
            node_id,
            claim_authority_class=claim_authority_class,
            launch_instruction_id=launch_instruction_id,
            resource_key=resource_key,
            authority_epoch=authority_epoch,
            _internal_authority=_internal_authority,
            host_id=host_id,
        ) as binding:
            with self.runtime_lock("claim-authority.lock", timeout_seconds=120.0):
                return self._claim_unlocked(
                    node_id,
                    owner,
                    claim_authority_class=claim_authority_class,
                    launch_instruction_id=launch_instruction_id,
                    resource_key=resource_key,
                    authority_epoch=authority_epoch,
                    binding=binding if isinstance(binding, Mapping) else None,
                    lease_minutes=lease_minutes,
                    publish_remote=publish_remote,
                    remote=remote,
                )

    def claim_internal(
        self,
        node_id: str,
        owner: str,
        *,
        lease_minutes: int = 90,
        publish_remote: bool = False,
        remote: str = "origin",
    ) -> Mapping[str, Any]:
        """Acquire explicitly privileged controller authority, never CLI authority."""

        return self.claim(
            node_id,
            owner,
            claim_authority_class=INTERNAL_CLAIM_AUTHORITY,
            _internal_authority=_INTERNAL_CLAIM_CAPABILITY,
            lease_minutes=lease_minutes,
            publish_remote=publish_remote,
            remote=remote,
        )

    def _claim_unlocked(
        self,
        node_id: str,
        owner: str,
        *,
        claim_authority_class: str,
        launch_instruction_id: str | None,
        resource_key: str | None,
        authority_epoch: int | None,
        binding: Mapping[str, object] | None,
        lease_minutes: int = 90,
        publish_remote: bool = False,
        remote: str = "origin",
    ) -> Mapping[str, Any]:
        if not owner.strip():
            raise ClaimError("claim owner is required")
        if self._read_plan_terminal_fence_unlocked() is not None:
            raise ClaimError("claim admission is closed by the execution terminal fence")
        try:
            self._assert_publication_not_indeterminate_unlocked()
        except AutopilotError as error:
            raise ClaimError(str(error)) from error
        if lease_minutes < 1 or lease_minutes > 1_440:
            raise ClaimError("lease must be between 1 and 1440 minutes")
        self._clean_stale_claims_unlocked()
        # Eligibility is a read-only observation; scope the snapshot cache to it
        # so claim does not replay the durable receipt reconstruction per call.
        with self.snapshot_cache():
            view = self.node_view(node_id)
        if view.state not in {"READY", "INTEGRATION_READY", "PROMOTION_READY"}:
            raise ClaimError(f"node {node_id} is not claimable: {view.state}")
        claims = self.active_claims()
        conflicts = self._claim_conflicts(node_id, claims)
        if conflicts:
            raise ClaimError("; ".join(conflicts))
        now = self.clock()
        expires_at = format_time(now + timedelta(minutes=lease_minutes))
        remote_claim_commit = (
            self.publish_remote_claim(
                node_id, owner, expires_at, remote=remote
            )
            if publish_remote
            else None
        )
        record = {
            "schema_version": SCHEMA_VERSION,
            "node_id": node_id,
            "owner": owner,
            "status": "CLAIMED",
            "claimed_at": format_time(now),
            "heartbeat_at": format_time(now),
            "expires_at": expires_at,
            "plan_fingerprint": self.expected_plan_fingerprint,
            "remote": remote if publish_remote else None,
            "remote_claim_commit": remote_claim_commit,
            "target_sha": self.current_target_sha(),
            "branch": self.node(node_id).get("branch"),
            "repository": _require_nonempty_text(
                _require_mapping(
                    self.control.get("target"), "control-plane.target"
                ).get("repository"),
                "target.repository",
            ),
            "file_locks": list(self.node(node_id).get("file_locks", [])),
            "semantic_locks": list(self.node(node_id).get("semantic_locks", [])),
            "execution_id": self.execution_id,
            "authority_nonce": secrets.token_hex(32),
            "dispatcher_release_id": (
                binding.get("dispatcher_release_id") if binding is not None else None
            ),
            "dispatcher_admission_epoch": (
                binding.get("dispatcher_admission_epoch") if binding is not None else None
            ),
            "launch_binding_event_id": (
                binding.get("event_id") if binding is not None else None
            ),
            **self._claim_authority_fields(
                claim_authority_class=claim_authority_class,
                launch_instruction_id=launch_instruction_id,
                resource_key=resource_key,
                authority_epoch=authority_epoch,
            ),
        }
        record["claim_id"] = digest_json(record)
        path = self.claim_path(node_id)
        if path.exists():
            raise ClaimError(f"node {node_id} already has a claim")
        atomic_write_json(path, record)
        return record

    def _fenced_claim(
        self,
        node_id: str,
        owner: str,
        claim_id: str,
        *,
        claim_authority_class: str,
        launch_instruction_id: str | None,
        resource_key: str | None,
        authority_epoch: int | None,
    ) -> tuple[Path, Mapping[str, Any]]:
        """Read one claim only when the caller holds its exact, single-use fence."""

        if AUTHORITY_ID.fullmatch(claim_id) is None:
            raise ClaimError("claim id is invalid")
        path = self.claim_path(node_id)
        if not path.is_file():
            raise ClaimError("claim is unavailable")
        value = read_json(path)
        if not isinstance(value, Mapping):
            raise ClaimError("claim is malformed")
        if value.get("node_id") != node_id or value.get("owner") != owner:
            raise ClaimError("claim owner or node does not match")
        if value.get("execution_id") not in {None, self.execution_id}:
            raise ClaimError("claim belongs to another execution namespace")
        current_id = value.get("claim_id")
        if not isinstance(current_id, str) or AUTHORITY_ID.fullmatch(current_id) is None:
            raise ClaimError(
                "active claim has no valid fence; explicit authority reconciliation is required"
            )
        if not secrets.compare_digest(current_id, claim_id):
            raise ClaimError("claim fence does not match")
        expected_authority = self._claim_authority_fields(
            claim_authority_class=claim_authority_class,
            launch_instruction_id=launch_instruction_id,
            resource_key=resource_key,
            authority_epoch=authority_epoch,
        )
        if any(value.get(field) != expected for field, expected in expected_authority.items()):
            raise ClaimError(
                "claim launch authority does not match; explicit reconciliation is required"
            )
        return path, value

    def heartbeat(
        self,
        node_id: str,
        owner: str,
        *,
        claim_id: str,
        claim_authority_class: str,
        launch_instruction_id: str | None = None,
        resource_key: str | None = None,
        authority_epoch: int | None = None,
        _internal_authority: object | None = None,
        lease_minutes: int = 90,
        running: bool = True,
    ) -> Mapping[str, Any]:
        with self.claim_launch_authority_guard(
            node_id,
            claim_authority_class=claim_authority_class,
            launch_instruction_id=launch_instruction_id,
            resource_key=resource_key,
            authority_epoch=authority_epoch,
            _internal_authority=_internal_authority,
        ):
            with self.runtime_lock("claim-authority.lock", timeout_seconds=120.0):
                return self._heartbeat_unlocked(
                    node_id,
                    owner,
                    claim_id=claim_id,
                    claim_authority_class=claim_authority_class,
                    launch_instruction_id=launch_instruction_id,
                    resource_key=resource_key,
                    authority_epoch=authority_epoch,
                    lease_minutes=lease_minutes,
                    running=running,
                )

    def heartbeat_internal(
        self,
        node_id: str,
        owner: str,
        *,
        claim_id: str,
        lease_minutes: int = 90,
        running: bool = True,
    ) -> Mapping[str, Any]:
        return self.heartbeat(
            node_id,
            owner,
            claim_id=claim_id,
            claim_authority_class=INTERNAL_CLAIM_AUTHORITY,
            _internal_authority=_INTERNAL_CLAIM_CAPABILITY,
            lease_minutes=lease_minutes,
            running=running,
        )

    def _heartbeat_unlocked(
        self,
        node_id: str,
        owner: str,
        *,
        claim_id: str,
        claim_authority_class: str,
        launch_instruction_id: str | None,
        resource_key: str | None,
        authority_epoch: int | None,
        lease_minutes: int = 90,
        running: bool = True,
    ) -> Mapping[str, Any]:
        if lease_minutes < 1 or lease_minutes > 1_440:
            raise ClaimError("lease must be between 1 and 1440 minutes")
        path, value = self._fenced_claim(
            node_id,
            owner,
            claim_id,
            claim_authority_class=claim_authority_class,
            launch_instruction_id=launch_instruction_id,
            resource_key=resource_key,
            authority_epoch=authority_epoch,
        )
        if parse_time(value.get("expires_at")) <= self.clock():
            raise ClaimError("claim lease has expired")
        now = self.clock()
        updated = dict(value)
        updated["status"] = "RUNNING" if running else "CLAIMED"
        updated["heartbeat_at"] = format_time(now)
        updated["expires_at"] = format_time(now + timedelta(minutes=lease_minutes))
        atomic_write_json(path, updated)
        return updated

    def release(
        self,
        node_id: str,
        owner: str,
        *,
        claim_id: str,
        claim_authority_class: str,
        launch_instruction_id: str | None = None,
        resource_key: str | None = None,
        authority_epoch: int | None = None,
        _internal_authority: object | None = None,
        reason: str,
    ) -> None:
        with self.claim_launch_authority_guard(
            node_id,
            claim_authority_class=claim_authority_class,
            launch_instruction_id=launch_instruction_id,
            resource_key=resource_key,
            authority_epoch=authority_epoch,
            _internal_authority=_internal_authority,
        ):
            with self.runtime_lock("claim-authority.lock", timeout_seconds=120.0):
                self._release_unlocked(
                    node_id,
                    owner,
                    claim_id=claim_id,
                    claim_authority_class=claim_authority_class,
                    launch_instruction_id=launch_instruction_id,
                    resource_key=resource_key,
                    authority_epoch=authority_epoch,
                    reason=reason,
                )

    def release_internal(
        self,
        node_id: str,
        owner: str,
        *,
        claim_id: str,
        reason: str,
    ) -> None:
        self.release(
            node_id,
            owner,
            claim_id=claim_id,
            claim_authority_class=INTERNAL_CLAIM_AUTHORITY,
            _internal_authority=_INTERNAL_CLAIM_CAPABILITY,
            reason=reason,
        )

    def _release_unlocked(
        self,
        node_id: str,
        owner: str,
        *,
        claim_id: str,
        claim_authority_class: str,
        launch_instruction_id: str | None,
        resource_key: str | None,
        authority_epoch: int | None,
        reason: str,
    ) -> None:
        path, value = self._fenced_claim(
            node_id,
            owner,
            claim_id,
            claim_authority_class=claim_authority_class,
            launch_instruction_id=launch_instruction_id,
            resource_key=resource_key,
            authority_epoch=authority_epoch,
        )
        remote_claim_commit = value.get("remote_claim_commit")
        remote = value.get("remote")
        if isinstance(remote_claim_commit, str) and isinstance(remote, str):
            self.release_remote_claim(
                node_id, remote_claim_commit, remote=remote
            )
        append_jsonl(
            self.state_dir / "releases.jsonl",
            {
                "node_id": node_id,
                "owner": owner,
                "claim_id": claim_id,
                "reason": reason,
                "released_at": format_time(self.clock()),
            },
        )
        path.unlink()

    def fail(
        self,
        node_id: str,
        owner: str,
        *,
        claim_id: str,
        claim_authority_class: str,
        launch_instruction_id: str | None = None,
        resource_key: str | None = None,
        authority_epoch: int | None = None,
        _internal_authority: object | None = None,
        error: str,
        kind: str = "failure",
        evidence_refs: Sequence[str] = (),
        blocker_cause: str | None = None,
        blocker_fix: str | None = None,
        retry_when: str | None = None,
        attempted_command: Sequence[str] = (),
        blocker_category: str = "execution",
    ) -> Mapping[str, Any]:
        with self.claim_launch_authority_guard(
            node_id,
            claim_authority_class=claim_authority_class,
            launch_instruction_id=launch_instruction_id,
            resource_key=resource_key,
            authority_epoch=authority_epoch,
            _internal_authority=_internal_authority,
        ):
            with self.runtime_lock("claim-authority.lock", timeout_seconds=120.0):
                return self._fail_unlocked(
                    node_id,
                    owner,
                    claim_id=claim_id,
                    claim_authority_class=claim_authority_class,
                    launch_instruction_id=launch_instruction_id,
                    resource_key=resource_key,
                    authority_epoch=authority_epoch,
                    error=error,
                    kind=kind,
                    evidence_refs=evidence_refs,
                    blocker_cause=blocker_cause,
                    blocker_fix=blocker_fix,
                    retry_when=retry_when,
                    attempted_command=attempted_command,
                    blocker_category=blocker_category,
                )

    def fail_internal(
        self,
        node_id: str,
        owner: str,
        *,
        claim_id: str,
        error: str,
        kind: str = "failure",
        evidence_refs: Sequence[str] = (),
        blocker_cause: str | None = None,
        blocker_fix: str | None = None,
        retry_when: str | None = None,
        attempted_command: Sequence[str] = (),
        blocker_category: str = "execution",
    ) -> Mapping[str, Any]:
        return self.fail(
            node_id,
            owner,
            claim_id=claim_id,
            claim_authority_class=INTERNAL_CLAIM_AUTHORITY,
            _internal_authority=_INTERNAL_CLAIM_CAPABILITY,
            error=error,
            kind=kind,
            evidence_refs=evidence_refs,
            blocker_cause=blocker_cause,
            blocker_fix=blocker_fix,
            retry_when=retry_when,
            attempted_command=attempted_command,
            blocker_category=blocker_category,
        )

    def _fail_unlocked(
        self,
        node_id: str,
        owner: str,
        *,
        claim_id: str,
        claim_authority_class: str,
        launch_instruction_id: str | None,
        resource_key: str | None,
        authority_epoch: int | None,
        error: str,
        kind: str = "failure",
        evidence_refs: Sequence[str] = (),
        blocker_cause: str | None = None,
        blocker_fix: str | None = None,
        retry_when: str | None = None,
        attempted_command: Sequence[str] = (),
        blocker_category: str = "execution",
    ) -> Mapping[str, Any]:
        if not error.strip():
            raise AutopilotError("failure requires an error description")
        path, claim = self._fenced_claim(
            node_id,
            owner,
            claim_id,
            claim_authority_class=claim_authority_class,
            launch_instruction_id=launch_instruction_id,
            resource_key=resource_key,
            authority_epoch=authority_epoch,
        )
        remote_claim_commit = claim.get("remote_claim_commit")
        remote = claim.get("remote")
        if isinstance(remote_claim_commit, str) and isinstance(remote, str):
            # Delete only an untouched claim commit.  release_remote_claim
            # deliberately preserves a branch that a worker already advanced.
            self.release_remote_claim(
                node_id,
                remote_claim_commit,
                remote=remote,
            )
        record = {
            "schema_version": SCHEMA_VERSION,
            "node_id": node_id,
            "owner": owner,
            "claim_id": claim_id,
            "kind": kind,
            "error": error,
            "evidence_refs": list(evidence_refs),
            "timestamp": format_time(self.clock()),
            "plan_fingerprint": self.expected_plan_fingerprint,
        }
        append_jsonl(self.failures_dir / f"{node_id}.jsonl", record)
        blocker = self.record_blocker(
            node_id,
            cause=blocker_cause or error,
            fix=blocker_fix or "Inspect the retained evidence and correct the reported cause.",
            retry_when=retry_when or "Retry only after the cause is corrected and the same checks pass.",
            attempted_command=attempted_command,
            category=blocker_category,
            evidence_refs=evidence_refs,
        )
        path.unlink()
        if kind == "escalation":
            atomic_write_json(self.escalations_dir / f"{node_id}.json", record)
        max_retries = int(self.node(node_id).get("max_retries", 0))
        if len(self.failures(node_id)) > max_retries:
            atomic_write_json(
                self.quarantine_dir / f"{node_id}.json",
                {
                    **record,
                    "reason": "configured retry budget exhausted",
                },
            )
        return {**record, "blocker": blocker}

    def complete(
        self,
        node_id: str,
        owner: str,
        receipt: Mapping[str, Any],
        *,
        claim_id: str,
        claim_authority_class: str,
        launch_instruction_id: str | None = None,
        resource_key: str | None = None,
        authority_epoch: int | None = None,
        _internal_authority: object | None = None,
    ) -> Path:
        with self.claim_launch_authority_guard(
            node_id,
            claim_authority_class=claim_authority_class,
            launch_instruction_id=launch_instruction_id,
            resource_key=resource_key,
            authority_epoch=authority_epoch,
            _internal_authority=_internal_authority,
        ):
            with self.runtime_lock("claim-authority.lock", timeout_seconds=120.0):
                return self._complete_unlocked(
                    node_id,
                    owner,
                    receipt,
                    claim_id=claim_id,
                    claim_authority_class=claim_authority_class,
                    launch_instruction_id=launch_instruction_id,
                    resource_key=resource_key,
                    authority_epoch=authority_epoch,
                )

    def complete_internal(
        self,
        node_id: str,
        owner: str,
        receipt: Mapping[str, Any],
        *,
        claim_id: str,
    ) -> Path | str:
        return self.complete(
            node_id,
            owner,
            receipt,
            claim_id=claim_id,
            claim_authority_class=INTERNAL_CLAIM_AUTHORITY,
            _internal_authority=_INTERNAL_CLAIM_CAPABILITY,
        )

    def _complete_unlocked(
        self,
        node_id: str,
        owner: str,
        receipt: Mapping[str, Any],
        *,
        claim_id: str,
        claim_authority_class: str,
        launch_instruction_id: str | None,
        resource_key: str | None,
        authority_epoch: int | None,
    ) -> Path:
        claim_path, claim = self._fenced_claim(
            node_id,
            owner,
            claim_id,
            claim_authority_class=claim_authority_class,
            launch_instruction_id=launch_instruction_id,
            resource_key=resource_key,
            authority_epoch=authority_epoch,
        )
        if parse_time(claim.get("expires_at")) <= self.clock():
            raise ClaimError("claim expired before receipt publication")
        issues = self.validate_receipt(node_id, receipt, require_integrated=False)
        if issues:
            raise ReceiptError("; ".join(issues))
        path = self.receipt_path(node_id)
        if path.exists():
            existing = read_json(path)
            if digest_json(existing) == digest_json(receipt):
                self._publish_terminal_receipt_event(
                    node_id, claim_id=claim_id, receipt=receipt
                )
                claim_path.unlink(missing_ok=True)
                _fsync_parent_directory(claim_path.parent)
                return path
            raise ReceiptError("node already has a different completion receipt")
        atomic_write_json(path, receipt)
        self._publish_terminal_receipt_event(
            node_id,
            claim_id=claim_id,
            receipt=receipt,
        )
        claim_path.unlink()
        _fsync_parent_directory(claim_path.parent)
        return path

    def reconcile(
        self,
        target_sha: str,
        *,
        actor: str,
        reason: str,
        changed_paths: Sequence[str] = (),
    ) -> Path:
        if FULL_SHA.fullmatch(target_sha) is None:
            raise AutopilotError("reconciled target must be a full lowercase SHA")
        if not actor.strip() or not reason.strip():
            raise AutopilotError("reconciliation actor and reason are required")
        if self.verify_git_objects:
            current = self.current_target_sha()
            if target_sha != current:
                raise AutopilotError(
                    f"reconciled target {target_sha} does not match current target {current}"
                )
            if not self.is_ancestor(self.baseline_sha, target_sha):
                raise AutopilotError("target no longer descends from the sealed baseline")
        normalized = [normalize_path(path) for path in changed_paths]
        record = {
            "schema_version": SCHEMA_VERSION,
            "target_sha": target_sha,
            "actor": actor,
            "reason": reason,
            "changed_paths": normalized,
            "timestamp": format_time(self.clock()),
            "plan_fingerprint": self.expected_plan_fingerprint,
        }
        path = self.state_dir / "target.json"
        atomic_write_json(path, record)
        append_jsonl(self.state_dir / "graph-changes.jsonl", record)
        return path

    def install_github_snapshot(self, source: Path) -> Path:
        value = read_json(source)
        if not isinstance(value, Mapping):
            raise AutopilotError("GitHub snapshot must be an object")
        target = value.get("target_sha")
        if not isinstance(target, str) or FULL_SHA.fullmatch(target) is None:
            raise AutopilotError("GitHub snapshot target_sha is invalid")
        for key in ("pull_requests", "branches"):
            if not isinstance(value.get(key, []), list):
                raise AutopilotError(f"GitHub snapshot {key} must be a list")
        path = self.state_dir / "github-state.json"
        atomic_write_json(path, value)
        return path

    def autopilot_command_prefix(self) -> str:
        """Return the absolute CLI prefix for this authenticated execution."""

        from orchestration import OrchestrationError, launch_fence_command_prefix

        try:
            return launch_fence_command_prefix(
                self.repo_root,
                self.coordination_dir,
                self.execution_namespace,
                self.host_runtime_dir,
            )
        except OrchestrationError as error:
            raise AutopilotError(
                f"cannot render authenticated Autopilot command prefix: {error}"
            ) from error

    def render_worker_prompt(
        self,
        node_id: str,
        *,
        host_id: str | None = None,
    ) -> str:
        node = self.node(node_id)
        view = self.node_view(node_id)
        template_name = {
            "integration": "integration.md",
            "promotion": "promotion.md",
            "reconciliation": "reconciliation.md",
        }.get(str(node.get("category")), "worker.md")
        template = (self.ap_root / "templates" / template_name).read_text(
            encoding="utf-8"
        )
        routes = _require_mapping(node.get("routes"), f"{node_id}.routes")
        openai = _require_mapping(routes.get("openai"), f"{node_id}.routes.openai")
        anthropic = _require_mapping(
            routes.get("anthropic"), f"{node_id}.routes.anthropic"
        )
        autopilot_prefix = self.autopilot_command_prefix()
        effective_host_id = host_id or getattr(
            self, "authenticated_host_id", None
        )
        if effective_host_id is None:
            raise AutopilotError(
                "worker prompt requires an authenticated host identity"
            )
        if (
            not isinstance(effective_host_id, str)
            or not effective_host_id.strip()
            or any(
                character in effective_host_id
                for character in '\r\n"`$&|<>%!^'
            )
        ):
            raise AutopilotError("worker prompt host identity is unsafe")
        values = {
            "REPOSITORY": str(
                _require_mapping(self.control.get("target"), "control-plane.target").get(
                    "repository", "local-repository"
                )
            ),
            "TARGET_BRANCH": self.target_branch,
            "NODE_ID": node_id,
            "NODE_STATE": view.state,
            "OBJECTIVE": str(node.get("objective")),
            "BRANCH": str(node.get("branch")),
            "PR_TARGET": self.target_branch,
            "ROLES": ", ".join(node.get("roles", [])),
            "DEPENDENCIES": ", ".join(node.get("dependencies", [])) or "none",
            "READ_SCOPE": "\n".join(f"- {item}" for item in node.get("read_scope", [])),
            "WRITE_SCOPE": "\n".join(f"- {item}" for item in node.get("write_scope", [])),
            "FORBIDDEN_SCOPE": "\n".join(f"- {item}" for item in node.get("forbidden_scope", [])),
            "ACCEPTANCE": "\n".join(f"- {item}" for item in node.get("acceptance_criteria", [])),
            "TESTS": "\n".join(f"- {item}" for item in node.get("required_tests", [])),
            "STOPPING_CONDITION": str(node.get("stopping_condition")),
            "ESCALATION": "\n".join(f"- {item}" for item in node.get("escalation_conditions", [])),
            "OPENAI_ROUTE": f"{openai.get('model')} / {openai.get('reasoning_effort')}",
            "ANTHROPIC_ROUTE": f"{anthropic.get('model')} / {anthropic.get('reasoning_effort')}",
            "ROUTE_RATIONALE": str(routes.get("rationale")),
            "TARGET_SHA": self.current_target_sha(),
            "PLAN_FINGERPRINT": self.expected_plan_fingerprint,
            "AUTOPILOT_PREFIX": autopilot_prefix,
            "HOST_ID": effective_host_id,
            "EXECUTION_NAMESPACE": self.execution_namespace,
            "REPO_ROOT": str(self.repo_root),
            "COORDINATION_DIR": str(self.coordination_dir),
            "STATE_DIR": str(self.coordination_dir),
            "EXECUTION_DIR": str(self.execution_dir),
            "HOST_RUNTIME_DIR": str(self.host_runtime_dir),
        }
        rendered = template
        for key, value in values.items():
            rendered = rendered.replace("{{" + key + "}}", value)
        return rendered

    def doctor(
        self,
        *,
        run_controller_tests: bool,
    ) -> dict[str, object]:
        issues = list(self.validate_configuration())
        checks: list[dict[str, object]] = []
        checks.append(
            {
                "name": "configuration",
                "passed": not issues,
                "details": list(issues),
            }
        )
        if self.verify_git_objects:
            git_details: list[str] = []
            if not (self.repo_root / ".git").exists():
                git_details.append("repository root lacks .git")
            if not self.git_object_exists(self.baseline_sha):
                git_details.append("sealed baseline commit is unavailable")
            try:
                target = self.current_target_sha()
            except AutopilotError as error:
                git_details.append(str(error))
                target = None
            if target and not self.is_ancestor(self.baseline_sha, target):
                git_details.append("target does not descend from sealed baseline")
            checks.append(
                {
                    "name": "repository",
                    "passed": not git_details,
                    "details": git_details,
                }
            )
        receipt_details: list[str] = []
        if self.receipts_dir.is_dir():
            for path in sorted(self.receipts_dir.glob("*.json")):
                node_id = path.stem
                if node_id not in self._nodes:
                    receipt_details.append(f"receipt exists for unknown node {node_id}")
                    continue
                value = read_json(path)
                receipt_details.extend(
                    f"{node_id}: {issue}"
                    for issue in self.validate_receipt(node_id, value)
                )
        checks.append(
            {
                "name": "receipts",
                "passed": not receipt_details,
                "details": receipt_details,
            }
        )
        consultation_details: list[str] = []
        fixture_dir = self.ap_root / "tests" / "fixtures" / "consultations"
        if fixture_dir.is_dir():
            for path in sorted(fixture_dir.glob("*.json")):
                value = read_json(path)
                if path.name.startswith("valid-"):
                    consultation_details.extend(
                        f"{path.name}: {issue}"
                        for issue in self.validate_consultation(value)
                    )
        checks.append(
            {
                "name": "consultation-contracts",
                "passed": not consultation_details,
                "details": consultation_details,
            }
        )
        test_details: list[str] = []
        if run_controller_tests:
            completed = subprocess.run(
                (
                    sys.executable,
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    str(self.ap_root / "tests"),
                    "-v",
                ),
                cwd=self.repo_root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=180,
            )
            if completed.returncode:
                test_details.append(completed.stdout[-20_000:])
            checks.append(
                {
                    "name": "controller-tests",
                    "passed": completed.returncode == 0,
                    "details": test_details,
                }
            )
        passed = all(bool(check["passed"]) for check in checks)
        return {
            "schema_version": SCHEMA_VERSION,
            "passed": passed,
            "state": "READY" if passed else "BOOTSTRAP_INVALID",
            "plan_fingerprint": self.expected_plan_fingerprint,
            "checks": checks,
            "generated_at": format_time(self.clock()),
        }
