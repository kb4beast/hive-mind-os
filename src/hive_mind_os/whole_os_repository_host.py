"""Durable local-preparation host for one external Git repository task.

This composes the existing Whole-OS pieces into a trusted ``WholeOSCompositionHost``
that can turn a pinned base commit into a retained, receipt-backed local candidate
and qualify it independently.  It is deliberately generic: every target name, path,
worker, sandbox, Curator and authority is an injected host dependency or a field of
one frozen ``RepositoryTaskBinding`` supplied by trusted code.

Local preparation only.  There is no transport, grant, credential or remote write
here; a later delivery bridge consumes the retained candidate.  Nothing in this
module mints authority, signs, approves its own work, or claims pilot/production
readiness.  A trusted-local (explicitly weaker) sandbox profile is labelled
``trusted-local-unqualified`` in every retained qualification.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable, Mapping, Protocol, Sequence
from uuid import uuid4

from .brain_kernel.canonical import (
    canonical_bytes,
    canonical_digest,
    canonical_document,
)
from .builder_session import (
    BuilderDisposition,
    BuilderSession,
    BuilderSessionResult,
    BuilderSessionSpec,
)
from .candidate_qualification import (
    CandidateQualifier,
    CheckReceipt,
    QualificationDisposition,
    QualificationReceipt,
    QualificationRequest,
)
from .cohort_assurance import (
    TerminalAssessment,
    TerminalEvidence,
    convergence_candidate_digest,
)
from .cohort_runtime import ConvergenceResult, VerificationResult
from .cortex.repository.mission_bindings import (
    ConfiguredMissionBindingsProvider,
    MissionBindingDescriptor,
)
from .delivery_broker import DeliveryBroker
from .git_adapter import GitOperationFailed, GitWorkspace
from .local_codex_worker import _validate_report
from .local_evidence_packet import (
    MAX_CONTENT_BYTES,
    LocalEvidenceError,
    _changed_paths,
    _safe_path,
    apply_proposed_patch,
    build_source_packet,
)
from .outcome_graph import OutcomeWorkPackage
from .path_boundary import is_within
from .policy import Action
from .receipts import FileReceiptValidator, ReceiptReference, filesystem_path
from .repository_profile import (
    HostProfileRegistry,
    ProfileCapability,
    RepositoryProfile,
)
from .runtime_contracts import canonical_digest as service_digest
from .runtime_contracts import canonical_json_bytes, raw_sha256
from .sandbox import ConfinementViolation
from .scoped_learning import LearningScope
from .verification_adapters import (
    SandboxAdapter,
    SandboxCapabilities,
    SandboxRequirements,
    VerificationBudget,
    VerificationError,
    VerificationRegistry,
    verify_repository,
)
from .whole_os_bootstrap import WholeOSHostBootstrap
from .whole_os_composition import (
    BlockerKind,
    BuildOutcome,
    CompositionBlocker,
    CompositionError,
    DeliveryPolicy,
    DiscoveryAdapter,
    DiscoveryOutcome,
    DurableLearningRecorder,
    WholeOSCompositionHost,
    _base_snapshot,
    _plain,
)
from .whole_os_qualification import CompositionManifest
from .whole_os_service import (
    PackageExecutionResult,
    PackageStatus,
    WholeOSServiceConfig,
)

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+)*$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_COMMIT_DATE = "2026-01-03T00:00:00Z"
_MAX_REPAIR_WINDOW = 3
_AMBIENT_ENVIRONMENT_NAMES = frozenset(
    {"TEMP", "TMP", "TMPDIR", "SystemRoot", "USERNAME", "PATH"}
)
_GIT_CREDENTIAL_ENVIRONMENT = (
    "GIT_CONFIG_COUNT",
    "GIT_CONFIG_KEY_0",
    "GIT_CONFIG_VALUE_0",
    "GIT_CONFIG_KEY_1",
    "GIT_CONFIG_VALUE_1",
    "GIT_CONFIG_KEY_2",
    "GIT_CONFIG_VALUE_2",
)
_SUCCESS = frozenset({PackageStatus.COMPLETED, PackageStatus.NO_CHANGE})
# Windows MAX_PATH is 260 including the terminating NUL.  The sandbox and Git receipt
# writers below do not use extended-length paths, so this host bounds its state root
# instead: fixed artifact names and the deepest materialized checkout must fit.
WINDOWS_PATH_LIMIT = 259
DEFAULT_PATH_LIMIT: int | None = WINDOWS_PATH_LIMIT if os.name == "nt" else None
_WORST_TASK_PREFIX = os.sep.join(
    (
        "repository-host",
        "0" * 16,
        "tasks",
        "0" * 16,
        "qualification",
        "0" * 16 + "-run-r99",
    )
)
# state root + separator + the longest fixed sandbox artifact of a verifier clone
_ARTIFACT_SPAN = (
    1
    + len(_WORST_TASK_PREFIX)
    + 1
    + len(os.sep.join(("clone-git", "artifacts", "0" * 64 + ".stdout")))
)
# state root + separator + the prefix before a repository-relative path is appended
_WORKSPACE_SPAN = (
    1 + len(_WORST_TASK_PREFIX) + 1 + len(os.sep.join(("verify-00", "workspace"))) + 1
)
CANDIDATE_KIND_CHANGED = "changed"
CANDIDATE_KIND_NO_CHANGE = "no-change"
PROFILE_TRUSTED_LOCAL = "trusted-local-unqualified"
PROFILE_HOSTILE_REQUIRED = "hostile-isolation-required"


class RepositoryBindingError(ValueError):
    """The frozen task binding is malformed, unbounded, or self-contradictory."""


class RepositoryHostBlocked(CompositionError):
    """Sealed typed blocker: retained evidence is missing, corrupt or contradicted.

    Raised from the builder or qualifier boundary it is sealed by the composition
    host; recovery is an explicit new attempt identity, never deletion or edit.
    """

    blocker = "blocked_capability"


class RepositoryHostUncertain(RuntimeError):
    """Retryable and never sealed: real worker state cannot be proven.

    No duplicate worker starts while this holds; a later scheduler attempt
    re-inspects the retained records.
    """


class RepositoryHostUnavailable(RuntimeError):
    """Factory-time preflight failed; the host must not be registered."""

    blocker = "blocked_capability"

    def __init__(self, blockers: Sequence[CompositionBlocker]) -> None:
        self.blockers = tuple(blockers)
        super().__init__("; ".join(item.message for item in self.blockers))


class _Refusal(Exception):
    """A deterministic, repairable patch refusal (internal control flow)."""


# --------------------------------------------------------------------------- utilities


def _short(digest: str, length: int = 16) -> str:
    return digest.removeprefix("sha256:")[:length]


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _publish_once(path: Path, body: bytes) -> bool:
    """Exclusively create ``path`` with ``body``; identical replays are no-ops.

    The bytes are flushed to a private temporary file and published by a hard link,
    which fails atomically when the name exists, so concurrent writers cannot
    replace each other and a reader never observes a partial record.
    """

    target = filesystem_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != body:
                raise RepositoryHostBlocked(
                    f"retained record conflicts with replay: {path.name}"
                ) from None
            return False
        return True
    finally:
        temporary.unlink(missing_ok=True)


def _sealed(kind: str, body: Mapping[str, Any]) -> dict[str, Any]:
    document: dict[str, Any] = {"schema_version": 1, "kind": kind, **body}
    document["record_digest"] = canonical_digest(document)
    return document


def _store(path: Path, document: Mapping[str, Any]) -> Path:
    _publish_once(path, canonical_bytes(document) + b"\n")
    return path


def _load(path: Path, kind: str) -> dict[str, Any]:
    try:
        raw = filesystem_path(path).read_bytes()
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, ValueError) as error:
        raise RepositoryHostBlocked(
            f"retained record is missing or unreadable: {path.name}"
        ) from error
    if (
        not isinstance(document, dict)
        or document.get("kind") != kind
        or document.get("schema_version") != 1
        or not isinstance(document.get("record_digest"), str)
    ):
        raise RepositoryHostBlocked(f"retained record has the wrong shape: {path.name}")
    claimed = document["record_digest"]
    body = {key: value for key, value in document.items() if key != "record_digest"}
    if claimed != canonical_digest(body) or raw != canonical_bytes(document) + b"\n":
        raise RepositoryHostBlocked(f"retained record is corrupt: {path.name}")
    return document


def _optional(path: Path, kind: str) -> dict[str, Any] | None:
    return _load(path, kind) if filesystem_path(path).exists() else None


def _file_ref(path: Path) -> str:
    return f"file:{path}#{raw_sha256(filesystem_path(path).read_bytes())}"


def _check_file_ref(reference: str, root: Path) -> None:
    if not isinstance(reference, str) or not reference.startswith("file:"):
        raise RepositoryHostBlocked("retained artifact reference is malformed")
    location, _, digest = reference[5:].rpartition("#")
    path = Path(location)
    if not is_within(path, root):
        raise RepositoryHostBlocked("retained artifact lies outside its task root")
    try:
        actual = raw_sha256(filesystem_path(path).read_bytes())
    except OSError as error:
        raise RepositoryHostBlocked(f"retained artifact is missing: {path.name}") from error
    if actual != digest:
        raise RepositoryHostBlocked(f"retained artifact digest changed: {path.name}")


def _git_bytes(repository: Path, *arguments: str, timeout: float = 60) -> bytes:
    environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1"}
    for name in _GIT_CREDENTIAL_ENVIRONMENT:
        environment.pop(name, None)
    try:
        completed = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(repository), *arguments],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout,
            check=False,
            shell=False,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RepositoryHostBlocked(f"git {arguments[0]} could not run") from error
    if completed.returncode:
        raise RepositoryHostBlocked(f"git {arguments[0]} failed on retained state")
    return completed.stdout


def _git(repository: Path, *arguments: str) -> str:
    return _git_bytes(repository, *arguments).decode("utf-8", "strict").strip()


def process_is_alive(pid: int) -> bool:
    """Liveness probe that never signals the process.

    ``os.kill(pid, 0)`` would terminate the process on Windows, so it is not used.
    """

    if os.name == "nt":
        tasklist = (
            Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "tasklist.exe"
        )
        completed = subprocess.run(
            [str(tasklist), "/FI", f"PID eq {int(pid)}", "/FO", "CSV", "/NH"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=15,
            check=False,
        )
        return f'"{int(pid)}"' in completed.stdout.decode("utf-8", "replace")
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _relative_path(value: object, label: str) -> str:
    if (
        type(value) is not str
        or not value
        or "\\" in value
        or ":" in value
        or any(character in value for character in "\x00\r\n\t")
        or PurePosixPath(value).is_absolute()
        or bool(PureWindowsPath(value).drive)
    ):
        raise RepositoryBindingError(f"{label} must be a repository-relative path")
    parts = value.rstrip("/").split("/")
    if any(
        part in {"", ".", ".."} or part.casefold() == ".git" or part.rstrip(" .") != part
        for part in parts
    ):
        raise RepositoryBindingError(f"{label} is not a safe repository path")
    return "/".join(parts)


def _within(path: str, scopes: Sequence[str]) -> bool:
    return any(path == scope or path.startswith(scope.rstrip("/") + "/") for scope in scopes)


def _positive(value: object, label: str, *, integer: bool = False) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or (integer and not isinstance(value, int))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise RepositoryBindingError(f"{label} must be a finite positive number")


def _bounded(text: object, limit: int = 500) -> str:
    cleaned = "".join(
        character if character.isprintable() or character == "\n" else " "
        for character in str(text)
    )
    return cleaned[:limit]


def _same_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(os.path.abspath(str(Path(left).resolve()))) == os.path.normcase(
        os.path.abspath(str(Path(right).resolve()))
    )


def candidate_identity(base_commit: str, commit: str, tree: str) -> str:
    """SHA-256 identity over the documented ``git-candidate-v1`` Git envelope.

    Git object names are SHA-1; the envelope binds them without pretending they
    are raw SHA-256 tree digests.
    """

    return canonical_digest(
        {
            "kind": "git-candidate-v1",
            "base_commit": base_commit,
            "candidate_commit": commit,
            "candidate_tree": tree,
        }
    )


# ------------------------------------------------------------------------- the binding


@dataclass(frozen=True, slots=True)
class AcceptanceSpec:
    """One executable acceptance check: the tests that must run and pass."""

    acceptance_id: str
    test_paths: tuple[str, ...]
    minimum_tests: int = 1

    def __post_init__(self) -> None:
        if type(self.acceptance_id) is not str or _IDENTIFIER.fullmatch(self.acceptance_id) is None:
            raise RepositoryBindingError("acceptance id must be a canonical identifier")
        paths = tuple(sorted({_relative_path(item, "test path") for item in self.test_paths}))
        if not paths:
            raise RepositoryBindingError("acceptance requires at least one test path")
        _positive(self.minimum_tests, "minimum tests", integer=True)
        object.__setattr__(self, "test_paths", paths)


@dataclass(frozen=True, slots=True)
class HoldoutSpec:
    """A sealed held-out test: its path and the digest of its exact bytes."""

    path: str
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _relative_path(self.path, "held-out path"))
        if type(self.sha256) is not str or _DIGEST.fullmatch(self.sha256) is None:
            raise RepositoryBindingError("held-out digest must be lowercase sha256:<64 hex>")


@dataclass(frozen=True, slots=True)
class RepositoryBuildBudget:
    """Finite ceilings for one attempt; ledger records make them cumulative."""

    max_worker_invocations: int = 3
    max_total_worker_seconds: float = 1800.0
    worker_timeout_seconds: float = 600.0
    max_tools: int = 20
    max_host_seconds: float = 3600.0
    packet_max_bytes: int = 120_000

    def __post_init__(self) -> None:
        _positive(self.max_worker_invocations, "worker invocations", integer=True)
        _positive(self.max_total_worker_seconds, "total worker seconds")
        _positive(self.worker_timeout_seconds, "worker timeout")
        _positive(self.max_tools, "tool budget", integer=True)
        _positive(self.max_host_seconds, "host seconds")
        _positive(self.packet_max_bytes, "packet bytes", integer=True)
        if (
            self.max_worker_invocations > _MAX_REPAIR_WINDOW
            or self.packet_max_bytes > MAX_CONTENT_BYTES
            or self.worker_timeout_seconds > self.max_total_worker_seconds
        ):
            raise RepositoryBindingError(
                "budget exceeds one attempt plus two repairs, the packet bound, or its own total"
            )


@dataclass(frozen=True, slots=True)
class RepositoryTaskBinding:
    """Frozen, host-owned identity and policy of one repository task.

    Target metadata may name a binding but never supplies imports, argv,
    credentials, or authority.  The digest of this document namespaces all durable
    state, so a changed binding can never reuse another binding's evidence.
    """

    attempt_id: str
    tenant_id: str
    repository_id: str
    campaign_id: str
    package_id: str
    source_repository: Path
    base_commit: str
    base_tree: str
    graph_digest: str
    context_digest: str
    objective: str
    allowed_paths: tuple[str, ...]
    acceptance: tuple[AcceptanceSpec, ...]
    verifier_adapter_id: str
    sandbox_requirements: SandboxRequirements
    trusted_local: bool
    sandbox_digest: str
    toolchain_digest: str
    environment_digest: str
    evaluator_id: str
    worker_id: str
    worker_protocol: str
    state_root: Path
    learning_authorization_digest: str
    budget: RepositoryBuildBudget = RepositoryBuildBudget()
    protected_paths: tuple[str, ...] = ()
    holdouts: tuple[HoldoutSpec, ...] = ()
    worker_model_prefix: str = ""
    risk_tier: str = "medium"
    verification_wall_seconds: float = 300.0
    no_change_permitted: bool = False
    delivery_label: str = "local-preparation"

    def __post_init__(self) -> None:
        for value, label in (
            (self.attempt_id, "attempt_id"),
            (self.tenant_id, "tenant_id"),
            (self.repository_id, "repository_id"),
            (self.worker_id, "worker_id"),
            (self.evaluator_id, "evaluator_id"),
        ):
            if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
                raise RepositoryBindingError(f"{label} must be a canonical identifier")
        for value, label in (
            (self.campaign_id, "campaign_id"),
            (self.package_id, "package_id"),
            (self.worker_protocol, "worker_protocol"),
            (self.verifier_adapter_id, "verifier_adapter_id"),
            (self.risk_tier, "risk_tier"),
            (self.delivery_label, "delivery_label"),
        ):
            if type(value) is not str or not value.strip() or value != value.strip():
                raise RepositoryBindingError(f"{label} must be a nonempty string")
        if type(self.objective) is not str or not self.objective.strip():
            raise RepositoryBindingError("objective must be a nonempty string")
        if type(self.worker_model_prefix) is not str:
            raise RepositoryBindingError("worker_model_prefix must be a string")
        for value, label in ((self.base_commit, "base_commit"), (self.base_tree, "base_tree")):
            if type(value) is not str or _FULL_SHA.fullmatch(value) is None:
                raise RepositoryBindingError(f"{label} must be a full lowercase Git SHA")
        for value, label in (
            (self.graph_digest, "graph_digest"),
            (self.context_digest, "context_digest"),
            (self.sandbox_digest, "sandbox_digest"),
            (self.toolchain_digest, "toolchain_digest"),
            (self.environment_digest, "environment_digest"),
            (self.learning_authorization_digest, "learning_authorization_digest"),
        ):
            if type(value) is not str or _DIGEST.fullmatch(value) is None:
                raise RepositoryBindingError(f"{label} must be lowercase sha256:<64 hex>")
        source = Path(self.source_repository)
        state = Path(self.state_root)
        if not source.is_absolute() or not state.is_absolute():
            raise RepositoryBindingError("source repository and state root must be absolute")
        if not source.is_dir():
            raise RepositoryBindingError("source repository must be an existing directory")
        source, state = source.resolve(), state.resolve()
        if is_within(state, source) or is_within(source, state):
            raise RepositoryBindingError(
                "private state must remain outside the target repository"
            )
        object.__setattr__(self, "source_repository", source)
        object.__setattr__(self, "state_root", state)
        allowed = tuple(sorted({_relative_path(item, "allowed path") for item in self.allowed_paths}))
        if not allowed and not self.no_change_permitted:
            raise RepositoryBindingError("a change-required task needs allowed paths")
        object.__setattr__(self, "allowed_paths", allowed)
        if not self.acceptance or any(type(item) is not AcceptanceSpec for item in self.acceptance):
            raise RepositoryBindingError("acceptance must be typed executable checks")
        if len({item.acceptance_id for item in self.acceptance}) != len(self.acceptance):
            raise RepositoryBindingError("acceptance ids must be unique")
        if any(type(item) is not HoldoutSpec for item in self.holdouts) or len(
            {item.path for item in self.holdouts}
        ) != len(self.holdouts):
            raise RepositoryBindingError("held-out tests must be unique typed specs")
        object.__setattr__(
            self,
            "protected_paths",
            tuple(sorted({_relative_path(item, "protected path") for item in self.protected_paths})),
        )
        if self.worker_id == self.evaluator_id:
            raise RepositoryBindingError("the evaluator must be independent from the worker")
        if type(self.sandbox_requirements) is not SandboxRequirements or type(
            self.trusted_local
        ) is not bool:
            raise RepositoryBindingError("sandbox requirements and label must be typed")
        if self.trusted_local != (self.sandbox_requirements != SandboxRequirements()):
            raise RepositoryBindingError(
                "a weaker-than-default sandbox must be labelled trusted-local, and only then"
            )
        if type(self.budget) is not RepositoryBuildBudget:
            raise RepositoryBindingError("budget must be a typed finite budget")
        _positive(self.verification_wall_seconds, "verification wall seconds")
        if type(self.no_change_permitted) is not bool:
            raise RepositoryBindingError("no_change_permitted must be boolean")

    @property
    def protected_scope(self) -> tuple[str, ...]:
        """Paths the Builder can never write: visible tests, holdouts, and more."""

        return tuple(
            sorted(
                {
                    *self.protected_paths,
                    *(path for spec in self.acceptance for path in spec.test_paths),
                    *(spec.path for spec in self.holdouts),
                }
            )
        )

    @property
    def withheld_paths(self) -> tuple[str, ...]:
        return tuple(sorted(spec.path for spec in self.holdouts))

    @property
    def profile_label(self) -> str:
        return PROFILE_TRUSTED_LOCAL if self.trusted_local else PROFILE_HOSTILE_REQUIRED

    def to_document(self) -> dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "tenant_id": self.tenant_id,
            "repository_id": self.repository_id,
            "campaign_id": self.campaign_id,
            "package_id": self.package_id,
            "source_repository": str(self.source_repository),
            "base_commit": self.base_commit,
            "base_tree": self.base_tree,
            "graph_digest": self.graph_digest,
            "context_digest": self.context_digest,
            "objective": self.objective,
            "allowed_paths": list(self.allowed_paths),
            "acceptance": [
                {
                    "acceptance_id": item.acceptance_id,
                    "test_paths": list(item.test_paths),
                    "minimum_tests": item.minimum_tests,
                }
                for item in self.acceptance
            ],
            "protected_paths": list(self.protected_paths),
            "holdouts": [{"path": item.path, "sha256": item.sha256} for item in self.holdouts],
            "verifier_adapter_id": self.verifier_adapter_id,
            "sandbox_requirements": asdict(self.sandbox_requirements),
            "trusted_local": self.trusted_local,
            "sandbox_digest": self.sandbox_digest,
            "toolchain_digest": self.toolchain_digest,
            "environment_digest": self.environment_digest,
            "evaluator_id": self.evaluator_id,
            "worker_id": self.worker_id,
            "worker_protocol": self.worker_protocol,
            "worker_model_prefix": self.worker_model_prefix,
            "state_root": str(self.state_root),
            "learning_authorization_digest": self.learning_authorization_digest,
            "budget": asdict(self.budget),
            "risk_tier": self.risk_tier,
            "verification_wall_seconds": self.verification_wall_seconds,
            "no_change_permitted": self.no_change_permitted,
            "delivery_label": self.delivery_label,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())


def service_context_digest(config: WholeOSServiceConfig) -> str:
    """The kickoff ``context_digest`` ``WholeOSService`` will derive for ``config``."""

    return service_digest(
        {
            "campaign_id": config.campaign_id,
            "tenant_id": config.tenant_id,
            "repository_id": config.repository_id,
            "configuration_digest": config.binding_descriptor.digest,
            "graph_digest": config.graph.digest,
            "base_snapshot": config.graph.base_snapshot,
        }
    )


def attempt_key(
    binding: RepositoryTaskBinding, package: OutcomeWorkPackage, payload: Mapping[str, Any]
) -> str:
    """Deterministic identity of one attempt from the binding and full payload.

    Discovery output is deliberately excluded so a re-run cannot mint a fresh
    budget by changing discovery; its digest is recorded as provenance instead.
    """

    kickoff = payload.get("cohort_kickoff")
    return canonical_digest(
        {
            "binding": binding.digest,
            "package_id": package.package_id,
            "allowed_paths": list(package.allowed_paths),
            "acceptance_ids": list(package.acceptance_ids),
            "risk_tier": package.risk_tier,
            "campaign_id": payload.get("campaign_id"),
            "tenant_id": payload.get("tenant_id"),
            "repository_id": payload.get("repository_id"),
            "configuration_digest": payload.get("configuration_digest"),
            "graph_digest": payload.get("graph_digest"),
            "context_digest": kickoff.get("context_digest")
            if isinstance(kickoff, Mapping)
            else None,
            "base_snapshot": _base_snapshot(payload),
        }
    )


# ---------------------------------------------------------- injected host dependencies


class PatchWorker(Protocol):
    """The actual model worker: proposes a patch as JSON; never applies it."""

    def run(
        self,
        *,
        node: dict[str, Any],
        actor_id: str,
        role: str,
        workspace: Path,
        evidence_directory: Path,
        predecessor_reports: list[dict[str, Any]],
        objective: str,
        timeout_seconds: float,
        writable: bool = False,
        source_packet: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class HostAdmission(Protocol):
    """Current-admission check performed by the host's registry, not by this module."""

    def require_current(self) -> None: ...


class HoldoutSource(Protocol):
    """Private custody of sealed held-out test bytes."""

    def read(self, path: str) -> bytes: ...


@dataclass(frozen=True, slots=True)
class CandidateReview:
    """A separate Curator's decision bound to the exact review packet."""

    reviewer_id: str
    packet_digest: str
    accepted: bool
    receipt_digest: str
    findings: tuple[str, ...] = ()


class CandidateReviewer(Protocol):
    reviewer_id: str

    def review(self, packet: Mapping[str, Any]) -> CandidateReview: ...


class ProfileRegistryAdmission:
    """Admission from the existing host profile registry (revocation-aware)."""

    def __init__(self, profile: RepositoryProfile, registry: HostProfileRegistry) -> None:
        self.profile = profile
        self.registry = registry

    def require_current(self) -> None:
        profile = self.profile
        try:
            current = self.registry.verify_profile(
                registry_handle=profile.registry_handle,
                profile_digest=profile.profile_digest,
                tenant_id=profile.identity.tenant_id,
                repository_id=profile.identity.repository_id,
                authority_digest=profile.identity.authority_digest,
                generation=profile.generation,
            )
            authorized = self.registry.authorize_capability(
                registry_handle=profile.registry_handle,
                profile_digest=profile.profile_digest,
                generation=profile.generation,
                capability=ProfileCapability.LOCAL_BUILD.value,
                destination=None,
            )
        except Exception as error:
            raise RepositoryHostBlocked("host registry could not confirm admission") from error
        if (
            current is not True
            or authorized is not True
            or not profile.allows(ProfileCapability.LOCAL_BUILD)
        ):
            raise RepositoryHostBlocked("repository profile admission is not current")


# ------------------------------------------------------- measured identities and results


def sandbox_identity_digest(capabilities: SandboxCapabilities) -> str:
    return canonical_digest(capabilities.document())


def toolchain_identity_digest(adapter_id: str, adapter_version: str, version_text: str) -> str:
    return canonical_digest(
        {
            "adapter_id": adapter_id,
            "adapter_version": adapter_version,
            "tool_version": version_text,
        }
    )


def environment_identity_digest(fixed_environment: Sequence[Sequence[str]]) -> str:
    return canonical_digest(
        {
            "policy": "scrubbed-environment-v1",
            "fixed": sorted([str(name), str(value)] for name, value in fixed_environment),
            "ambient_allowed": sorted(_AMBIENT_ENVIRONMENT_NAMES),
        }
    )


def sandbox_gaps(
    capabilities: SandboxCapabilities, requirements: SandboxRequirements
) -> tuple[str, ...]:
    """Requirement gaps, mirroring ``verify_repository`` so none is executed."""

    gaps = []
    if not capabilities.available:
        gaps.append("sandbox adapter unavailable")
    if requirements.hostile_code_isolation and not capabilities.hostile_code_isolation:
        gaps.append("hostile-code isolation unavailable")
    if requirements.network_policy == "deny" and not capabilities.network_deny:
        gaps.append("network-deny enforcement unavailable")
    if requirements.hostile_code_isolation and not capabilities.cpu_memory_limits:
        gaps.append("CPU/memory enforcement unavailable")
    return tuple(gaps)


def read_unittest_results(stdout: bytes, stderr: bytes) -> dict[str, Any]:
    """Host-owned reader for ``python -m unittest`` summaries (stderr channel).

    This is evidence inside an admitted trusted harness; it does not defend
    against a hostile interpreter forging its own summary line.
    """

    del stdout
    text = stderr.decode("utf-8", "replace").replace("\r\n", "\n")
    ran = re.findall(r"(?m)^Ran (\d+) tests? in [0-9.]+s$", text)
    verdict = re.findall(r"(?m)^(OK|FAILED)(?: \(([^)]*)\))?$", text)
    if not ran or not verdict:
        return {"parsed": False, "ok": False, "ran": 0, "skipped": 0, "executed": 0}
    label, extras = verdict[-1]
    counts = {name.strip(): int(number) for name, number in re.findall(r"([a-z ]+)=(\d+)", extras or "")}
    total = int(ran[-1])
    skipped = counts.get("skipped", 0)
    expected = counts.get("expected failures", 0)
    return {
        "parsed": True,
        "ok": label == "OK",
        "ran": total,
        "skipped": skipped,
        "expected_failures": expected,
        "executed": max(total - skipped - expected, 0),
    }


_RESULT_READERS: Mapping[str, Callable[[bytes, bytes], dict[str, Any]]] = {
    "python-unittest": read_unittest_results,
}


def _evaluate_verification(
    binding: RepositoryTaskBinding,
    spec: AcceptanceSpec,
    evidence_directory: Path,
    *,
    returned: Mapping[str, Any] | None,
    command_digest: str | None,
    fixed_environment: Sequence[Sequence[str]],
    source: Path | None,
) -> dict[str, Any]:
    """Independently read a ``verify_repository`` receipt from disk and judge it."""

    reasons: list[str] = []
    receipt_path = evidence_directory / "receipt.json"
    try:
        raw = filesystem_path(receipt_path).read_bytes()
        receipt = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, ValueError):
        return {"status": "incomplete", "count": 0, "reasons": ["verification-receipt-missing"],
                "artifacts": [], "observed": {}}
    if not isinstance(receipt, dict):
        return {"status": "failed", "count": 0, "reasons": ["verification-receipt-malformed"],
                "artifacts": [], "observed": {}}
    if returned is not None and dict(returned) != receipt:
        reasons.append("verification-receipt-differs-from-return")
    body = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    if (
        raw != canonical_json_bytes(receipt) + b"\n"
        or receipt.get("receipt_digest") != raw_sha256(canonical_json_bytes(body))
    ):
        reasons.append("verification-receipt-corrupt")
    if receipt.get("status") in {"BLOCKED", "VERIFICATION_OBLIGATION"}:
        return {"status": "incomplete", "count": 0,
                "reasons": [*reasons, f"verification-{str(receipt['status']).lower()}"],
                "artifacts": [_file_ref(receipt_path)], "observed": {}}
    runtime = receipt.get("runtime")
    if not isinstance(runtime, dict) or canonical_digest(runtime) != binding.sandbox_digest:
        reasons.append("sandbox-identity-mismatch")
    else:
        if binding.sandbox_requirements.hostile_code_isolation and not runtime.get(
            "hostile_code_isolation"
        ):
            reasons.append("hostile-isolation-not-observed")
        if binding.sandbox_requirements.network_policy == "deny" and not runtime.get(
            "network_deny"
        ):
            reasons.append("network-deny-not-observed")
    tool = receipt.get("tool_version")
    if (
        receipt.get("adapter_id") != binding.verifier_adapter_id
        or not isinstance(tool, dict)
        or toolchain_identity_digest(
            str(receipt.get("adapter_id")), str(receipt.get("adapter_version")), str(tool.get("text"))
        )
        != binding.toolchain_digest
    ):
        reasons.append("toolchain-identity-mismatch")
    fixed_names = {str(name) for name, _ in fixed_environment}
    names = set(receipt.get("environment") or ())
    if (
        environment_identity_digest(fixed_environment) != binding.environment_digest
        or not fixed_names <= names
        or not names <= fixed_names | _AMBIENT_ENVIRONMENT_NAMES
    ):
        reasons.append("environment-identity-mismatch")
    if command_digest is not None and receipt.get("sealed_command_digest") != command_digest:
        reasons.append("sealed-command-mismatch")
    if receipt.get("selected_tests") != list(spec.test_paths):
        reasons.append("selected-tests-differ-from-acceptance")
    if receipt.get("verification_kind") != "test-execution" or receipt.get("tests_executed") is not True:
        reasons.append("no-test-execution")
    if source is not None and not (
        isinstance(receipt.get("source_repository"), str)
        and _same_path(receipt["source_repository"], source)
    ):
        reasons.append("verified-repository-is-not-the-candidate-clone")
    if receipt.get("status") != "PASSED" or receipt.get("exit_code") != 0 or receipt.get("timed_out"):
        reasons.append("verification-did-not-pass")
    artifacts = [_file_ref(receipt_path)]
    streams: dict[str, bytes] = {}
    for name in ("stdout", "stderr"):
        info = receipt.get(name)
        if not isinstance(info, dict):
            reasons.append(f"{name}-artifact-invalid")
            continue
        try:
            location = Path(info["path"])
            data = filesystem_path(location).read_bytes()
            if not is_within(location, evidence_directory) or raw_sha256(data) != info["digest"]:
                raise ValueError("artifact does not match its receipt")
        except (OSError, KeyError, TypeError, ValueError):
            reasons.append(f"{name}-artifact-invalid")
            continue
        streams[name] = data
        artifacts.append(_file_ref(location))
    reader = _RESULT_READERS.get(binding.verifier_adapter_id)
    observed: dict[str, Any] = {}
    if reader is None or len(streams) != 2:
        reasons.append("no-reviewed-result-reader")
    else:
        observed = reader(streams["stdout"], streams["stderr"])
        if not observed.get("parsed"):
            reasons.append("results-unparsed")
        elif not observed.get("ok"):
            reasons.append("tests-failed")
        elif observed["executed"] < max(1, spec.minimum_tests):
            reasons.append("insufficient-executed-tests")
    count = int(observed.get("executed", 0)) if observed else 0
    if not reasons:
        status = "passed"
    elif "results-unparsed" in reasons or "no-reviewed-result-reader" in reasons:
        status = "incomplete"
    else:
        status = "failed"
    return {"status": status, "count": count, "reasons": reasons, "artifacts": artifacts,
            "observed": observed}


# ------------------------------------------------------------------- durable state store


@dataclass(slots=True)
class _Slot:
    index: int
    start: dict[str, Any]
    outcome: dict[str, Any] | None
    decision: dict[str, Any] | None

    @property
    def elapsed(self) -> float:
        return float(self.outcome["elapsed_seconds"]) if self.outcome else 0.0


@dataclass(frozen=True, slots=True)
class CandidateRecord:
    key: str
    kind: str
    base_commit: str
    base_tree: str
    commit: str
    tree: str
    identity: str
    changed_paths: tuple[str, ...]
    patch_sha256: str | None
    clone_root: Path
    record_digest: str
    worker_session_id: str
    reference: str
    document: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class RetainedQualification:
    receipt: QualificationReceipt
    envelope: Mapping[str, Any]
    reference: str


def _receipt_from_document(document: Mapping[str, Any]) -> QualificationReceipt:
    try:
        return QualificationReceipt(
            document["request_digest"],
            QualificationDisposition(document["disposition"]),
            tuple(
                CheckReceipt(
                    item["name"],
                    item["kind"],
                    item["input_digest"],
                    item["origin"],
                    item["status"],
                    item["actual_count"],
                    tuple(item["artifacts"]),
                    tuple(item["omitted"]),
                )
                for item in document["checks"]
            ),
            tuple(document["invalidations"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RepositoryHostBlocked("retained qualification receipt is malformed") from error


class RepositoryStateStore:
    """Append-only, binding-namespaced records; every load re-verifies its bytes."""

    def __init__(self, binding: RepositoryTaskBinding) -> None:
        self.binding = binding
        self.root = binding.state_root / "repository-host" / _short(binding.digest)

    def seal_binding(self) -> None:
        _store(
            self.root / "binding.json",
            _sealed("repository-host-binding", self.binding.to_document()),
        )

    def task_dir(self, key: str) -> Path:
        return self.root / "tasks" / _short(key)

    def candidate_path(self, key: str) -> Path:
        return self.task_dir(key) / "candidate.json"

    def slot_path(self, key: str, index: int, part: str) -> Path:
        return self.task_dir(key) / f"slot-{index:03d}.{part}.json"

    def publish(self, path: Path, document: Mapping[str, Any]) -> bool:
        return _publish_once(path, canonical_bytes(document) + b"\n")

    def _slot_document(self, key: str, index: int, part: str, kind: str) -> dict[str, Any] | None:
        document = _optional(self.slot_path(key, index, part), kind)
        if document is not None and (
            document.get("attempt_key") != key
            or document.get("slot") != index
            or document.get("binding_digest") != self.binding.digest
        ):
            raise RepositoryHostBlocked("worker slot record targets another attempt")
        return document

    def load_slot(self, key: str, index: int) -> _Slot | None:
        start = self._slot_document(key, index, "start", "repository-host-worker-start")
        if start is None:
            return None
        return _Slot(
            index,
            start,
            self._slot_document(key, index, "outcome", "repository-host-worker-outcome"),
            self._slot_document(key, index, "decision", "repository-host-decision"),
        )

    def load_slots(self, key: str) -> list[_Slot]:
        task = self.task_dir(key)
        present = sorted(task.glob("slot-*.start.json")) if task.is_dir() else []
        slots = []
        for index, path in enumerate(present):
            if path.name != f"slot-{index:03d}.start.json":
                raise RepositoryHostBlocked("worker slot records are not contiguous")
            slot = self.load_slot(key, index)
            assert slot is not None
            slots.append(slot)
        return slots

    def register_identity(self, identity: str, key: str) -> None:
        _store(
            self.root / "identities" / f"{_short(identity)}.json",
            _sealed(
                "repository-host-identity",
                {"candidate_identity": identity, "attempt_key": key,
                 "binding_digest": self.binding.digest},
            ),
        )

    def key_for_identity(self, identity: str) -> str:
        document = _load(
            self.root / "identities" / f"{_short(identity)}.json", "repository-host-identity"
        )
        if (
            document["candidate_identity"] != identity
            or document["binding_digest"] != self.binding.digest
        ):
            raise RepositoryHostBlocked("candidate identity index targets another candidate")
        return str(document["attempt_key"])

    def _confined(self, task: Path, relative: object) -> Path:
        if type(relative) is not str or not relative:
            raise RepositoryHostBlocked("retained path is malformed")
        target = (task / relative).resolve()
        if not is_within(target, task):
            raise RepositoryHostBlocked("retained path escapes its task root")
        return target

    def _validate_git_receipts(self, root: Path, records: object) -> None:
        if not isinstance(records, list) or not records or not root.is_dir():
            raise RepositoryHostBlocked("candidate has no retained Git operation receipts")
        try:
            validator = FileReceiptValidator(root)
            for record in records:
                validation = validator.validate(
                    ReceiptReference(record["path"], record["digest"]),
                    mission_id=record["mission_id"],
                    state_ref=record["state_ref"],
                    actor_id=record["actor_id"],
                    action_id=record["action_id"],
                    action_kind=record["action_kind"],
                    action_digest=record["action_digest"],
                )
                if not validation.valid:
                    raise RepositoryHostBlocked("a retained Git operation receipt is invalid")
        except (KeyError, TypeError, ValueError) as error:
            raise RepositoryHostBlocked("retained Git operation receipts are malformed") from error

    def load_candidate(self, key: str) -> CandidateRecord:
        """Reopen a retained candidate and re-derive every claim from Git and disk."""

        binding = self.binding
        task = self.task_dir(key)
        path = self.candidate_path(key)
        document = _load(path, "repository-host-candidate")
        expected = {
            "attempt_key": key,
            "binding_digest": binding.digest,
            "package_id": binding.package_id,
            "base_commit": binding.base_commit,
            "base_tree": binding.base_tree,
        }
        if any(document.get(name) != value for name, value in expected.items()):
            raise RepositoryHostBlocked("candidate receipt targets another task or binding")
        kind = document.get("candidate_kind")
        commit = document.get("candidate_commit")
        tree = document.get("candidate_tree")
        changed = document.get("changed_paths")
        if (
            kind not in {CANDIDATE_KIND_CHANGED, CANDIDATE_KIND_NO_CHANGE}
            or type(commit) is not str
            or type(tree) is not str
            or not isinstance(changed, list)
            or any(type(item) is not str for item in changed)
            or document.get("candidate_identity") != candidate_identity(binding.base_commit, commit, tree)
        ):
            raise RepositoryHostBlocked("candidate receipt identity is inconsistent")
        clone = document.get("clone")
        if not isinstance(clone, dict):
            raise RepositoryHostBlocked("candidate receipt lacks its clone")
        clone_root = self._confined(task, clone.get("root"))
        if not clone_root.is_dir():
            raise RepositoryHostBlocked("retained candidate clone is missing")
        if (
            _git(clone_root, "rev-parse", "HEAD") != commit
            or _git(clone_root, "rev-parse", "HEAD^{tree}") != tree
        ):
            raise RepositoryHostBlocked("retained candidate clone differs from its receipt")
        if _git(clone_root, "remote"):
            raise RepositoryHostBlocked("retained candidate clone has a remote")
        if _git(clone_root, "status", "--porcelain", "--untracked-files=all"):
            raise RepositoryHostBlocked("retained candidate clone is dirty")
        patch_sha: str | None = None
        if kind == CANDIDATE_KIND_CHANGED:
            if _git(clone_root, "rev-list", "--parents", "-n", "1", commit).split() != [
                commit,
                binding.base_commit,
            ]:
                raise RepositoryHostBlocked("candidate commit parent is not the admitted base")
            names = sorted(
                item.decode("utf-8")
                for item in _git_bytes(
                    clone_root, "diff", "--name-only", "-z", binding.base_commit, commit
                ).split(b"\0")
                if item
            )
            if names != sorted(changed) or not names:
                raise RepositoryHostBlocked("candidate change set differs from its receipt")
            if any(
                not _within(item, binding.allowed_paths) or _within(item, binding.protected_scope)
                for item in names
            ):
                raise RepositoryHostBlocked("candidate changes paths outside its scope")
            patch_sha = document.get("patch_sha256")
            try:
                patch_bytes = filesystem_path(task / "candidate.patch").read_bytes()
            except OSError as error:
                raise RepositoryHostBlocked("retained candidate patch is missing") from error
            if patch_sha != raw_sha256(patch_bytes):
                raise RepositoryHostBlocked("retained candidate patch digest changed")
        elif commit != binding.base_commit or tree != binding.base_tree or changed:
            raise RepositoryHostBlocked("no-change candidate differs from the admitted base")
        worker = document.get("worker")
        if not isinstance(worker, dict):
            raise RepositoryHostBlocked("candidate receipt lacks its worker linkage")
        outcome = _load(
            self.slot_path(key, int(worker.get("slot", -1)), "outcome"),
            "repository-host-worker-outcome",
        )
        if outcome["record_digest"] != worker.get("outcome_digest"):
            raise RepositoryHostBlocked("worker outcome differs from the candidate receipt")
        self._validate_git_receipts(self._confined(task, clone.get("receipts")), document.get("git_receipts"))
        return CandidateRecord(
            key,
            kind,
            binding.base_commit,
            binding.base_tree,
            commit,
            tree,
            document["candidate_identity"],
            tuple(sorted(changed)),
            patch_sha,
            clone_root,
            document["record_digest"],
            str(worker.get("session_id")),
            _file_ref(path),
            document,
        )

    # qualification retention is keyed by the full request digest

    def qualification_paths(self, key: str, request_digest: str) -> tuple[Path, Path]:
        base = self.task_dir(key) / "qualification"
        stem = _short(request_digest)
        return base / f"{stem}.receipt.json", base / f"{stem}.envelope.json"

    def load_qualification(
        self, key: str, request_digest: str, candidate: CandidateRecord
    ) -> RetainedQualification | None:
        binding = self.binding
        receipt_path, envelope_path = self.qualification_paths(key, request_digest)
        present = (filesystem_path(receipt_path).exists(), filesystem_path(envelope_path).exists())
        if not any(present):
            return None
        if not all(present):
            raise RepositoryHostBlocked("qualification retention is partial")
        stored = _load(receipt_path, "repository-host-qualification-receipt")
        envelope = _load(envelope_path, "repository-host-qualification-envelope")
        receipt = _receipt_from_document(stored.get("receipt", {}))
        task = self.task_dir(key)
        identity_ok = (
            stored.get("request_digest") == request_digest == receipt.request_digest
            == envelope.get("request_digest")
            and stored.get("receipt_digest") == receipt.digest == envelope.get("receipt_digest")
            and envelope.get("attempt_key") == key == stored.get("attempt_key")
            and envelope.get("binding_digest") == binding.digest
            and envelope.get("evaluator_id") == binding.evaluator_id
            and envelope.get("profile") == binding.profile_label
            and envelope.get("sandbox_digest") == binding.sandbox_digest
            and envelope.get("toolchain_digest") == binding.toolchain_digest
            and envelope.get("environment_digest") == binding.environment_digest
        )
        bound = envelope.get("candidate")
        if not identity_ok or not isinstance(bound, dict) or bound != {
            "identity": candidate.identity,
            "commit": candidate.commit,
            "tree": candidate.tree,
            "base_commit": candidate.base_commit,
            "base_tree": candidate.base_tree,
            "changed_paths": list(candidate.changed_paths),
            "record_digest": candidate.record_digest,
            "kind": candidate.kind,
        }:
            raise RepositoryHostBlocked("qualification receipt is not bound to this candidate")
        for check in receipt.checks:
            for reference in check.artifacts:
                _check_file_ref(reference, task)
        if receipt.disposition is QualificationDisposition.PASSED:
            self._revalidate_passed(task, receipt, envelope)
        return RetainedQualification(receipt, envelope, _file_ref(receipt_path))

    def _revalidate_passed(
        self, task: Path, receipt: QualificationReceipt, envelope: Mapping[str, Any]
    ) -> None:
        binding = self.binding
        recorded = envelope.get("checks")
        if (
            not isinstance(recorded, list)
            or [item.name for item in receipt.checks] != [s.acceptance_id for s in binding.acceptance]
            or len(recorded) != len(receipt.checks)
        ):
            raise RepositoryHostBlocked("passed qualification does not cover the acceptance manifest")
        for spec, check, item in zip(binding.acceptance, receipt.checks, recorded):
            try:
                verdict = _evaluate_verification(
                    binding,
                    spec,
                    self._confined(task, item["evidence_directory"]),
                    returned=None,
                    command_digest=item["sealed_command_digest"],
                    fixed_environment=item["fixed_environment"],
                    source=None,
                )
            except (KeyError, TypeError) as error:
                raise RepositoryHostBlocked("qualification envelope check is malformed") from error
            if (
                check.status != "passed"
                or verdict["status"] != "passed"
                or verdict["count"] != check.actual_count
                or check.actual_count < max(1, spec.minimum_tests)
            ):
                raise RepositoryHostBlocked(
                    "retained verification evidence no longer supports a passed qualification"
                )


# --------------------------------------------------------------------- host context


class RepositoryHostContext:
    """Everything one repository task needs, shared by builder, qualifier, curator."""

    def __init__(
        self,
        binding: RepositoryTaskBinding,
        *,
        repository_profile: RepositoryProfile,
        admission: HostAdmission,
        worker: PatchWorker,
        sandbox: SandboxAdapter,
        reviewer: CandidateReviewer,
        holdouts: HoldoutSource | None = None,
        path_limit: int | None = DEFAULT_PATH_LIMIT,
    ) -> None:
        if path_limit is not None and (
            isinstance(path_limit, bool)
            or not isinstance(path_limit, int)
            or path_limit < 1
        ):
            raise RepositoryBindingError("path limit must be a positive integer or None")
        self.binding = binding
        self.repository_profile = repository_profile
        self.admission = admission
        self.worker = worker
        self.sandbox = sandbox
        self.reviewer = reviewer
        self.holdouts = holdouts
        self.path_limit = path_limit
        self.store = RepositoryStateStore(binding)
        self._keys: dict[str, str] = {}
        self._longest_tracked: int | None = None

    def _longest_tracked_path(self) -> int:
        """Length of the longest tracked path at the admitted base (read-only)."""

        if self._longest_tracked is None:
            listing = _git_bytes(
                self.binding.source_repository,
                "ls-tree",
                "-r",
                "--name-only",
                "-z",
                self.binding.base_commit,
            )
            self._longest_tracked = max(
                (len(item.decode("utf-8", "replace")) for item in listing.split(b"\0") if item),
                default=0,
            )
        return self._longest_tracked

    def max_relative_path(self) -> int | None:
        """Longest repository-relative path the host can materialize, if bounded."""

        if self.path_limit is None:
            return None
        return self.path_limit - len(str(self.binding.state_root)) - _WORKSPACE_SPAN

    def path_problems(self) -> tuple[str, ...]:
        """Early typed unsupported-path check; it runs before any effect.

        The underlying sandbox and Git receipt writers do not use Windows
        extended-length paths, so a state root that pushes their fixed artifact
        names past the limit failed deep inside a run.  H1 bounds the root
        instead of rewriting those writers.
        """

        limit = self.path_limit
        if limit is None:
            return ()
        root_length = len(str(self.binding.state_root))
        problems: list[str] = []
        worst = root_length + _ARTIFACT_SPAN
        if worst > limit:
            problems.append(
                f"private state root is too deep: the longest fixed host artifact path "
                f"would be {worst} characters, above the supported {limit}; use a state "
                f"root of at most {limit - _ARTIFACT_SPAN} characters"
            )
            return tuple(problems)
        room = limit - root_length - _WORKSPACE_SPAN
        try:
            longest = self._longest_tracked_path()
        except RepositoryHostBlocked:
            problems.append("tracked path lengths at the admitted base could not be measured")
        else:
            if longest > room:
                problems.append(
                    f"a tracked repository path of {longest} characters exceeds the {room} "
                    f"the host can materialize under this state root (limit {limit})"
                )
        return tuple(problems)

    def require_supported_paths(self) -> None:
        problems = self.path_problems()
        if problems:
            raise RepositoryHostBlocked("unsupported path length: " + "; ".join(problems))

    def require_admission(self) -> None:
        try:
            self.admission.require_current()
        except RepositoryHostBlocked:
            raise
        except Exception as error:
            raise RepositoryHostBlocked(f"current admission is not confirmed: {error}") from error

    def remember(self, commit: str, key: str) -> None:
        self._keys[commit] = key

    def key_for_commit(self, commit: str) -> str | None:
        return self._keys.get(commit)

    def qualification_request(self, record: CandidateRecord) -> QualificationRequest:
        binding = self.binding
        return QualificationRequest(
            record.commit,
            binding.base_commit,
            tuple(spec.acceptance_id for spec in binding.acceptance),
            record.changed_paths,
            binding.risk_tier,
            binding.sandbox_digest,
            binding.toolchain_digest,
            binding.environment_digest,
            binding.evaluator_id,
        )

    def revalidate(
        self, candidate_digest: str, evidence_refs: Sequence[str], *, expect_kind: str
    ) -> tuple[CandidateRecord, RetainedQualification]:
        """Current admission plus every retained artifact behind a terminal result."""

        self.require_admission()
        key = self.store.key_for_identity(candidate_digest)
        record = self.store.load_candidate(key)
        if record.identity != candidate_digest or record.kind != expect_kind:
            raise RepositoryHostBlocked("terminal result does not match its retained candidate")
        request = self.qualification_request(record)
        retained = self.store.load_qualification(key, canonical_digest(request), record)
        if retained is None:
            raise RepositoryHostBlocked("retained qualification is absent")
        if retained.receipt.disposition is not QualificationDisposition.PASSED:
            raise RepositoryHostBlocked("retained qualification is not a pass")
        if retained.receipt.digest not in evidence_refs:
            raise RepositoryHostBlocked("terminal result does not cite the retained qualification")
        return record, retained

    def _source_problems(self) -> list[str]:
        binding = self.binding
        source = binding.source_repository
        git_directory = source / ".git"
        if not git_directory.is_dir() or git_directory.is_symlink():
            return ["source must be a real Git checkout with its own .git directory"]
        if (git_directory / "objects" / "info" / "alternates").exists():
            return ["source repository uses Git alternates"]
        try:
            commit = _git(source, "rev-parse", "--verify", f"{binding.base_commit}^{{commit}}")
            tree = _git(source, "rev-parse", "--verify", f"{binding.base_commit}^{{tree}}")
        except RepositoryHostBlocked:
            return ["admitted base commit is absent from the source repository"]
        if commit != binding.base_commit or tree != binding.base_tree:
            return ["admitted base commit or tree differs from the binding"]
        return []

    def preflight(self) -> tuple[CompositionBlocker, ...]:
        """Read-only dependency check that runs before any worker budget is spent."""

        blockers: list[CompositionBlocker] = []

        def add(stage: str, kind: BlockerKind, detail: str) -> None:
            blockers.append(CompositionBlocker(stage, kind, detail))

        binding, profile = self.binding, self.repository_profile
        authority, capability = BlockerKind.BLOCKED_AUTHORITY, BlockerKind.BLOCKED_CAPABILITY
        try:
            self.require_admission()
        except RepositoryHostBlocked as error:
            add("admission", authority, str(error))
        identity = profile.identity
        if (identity.tenant_id, identity.repository_id) != (binding.tenant_id, binding.repository_id):
            add("profile", authority, "repository profile targets another tenant or repository")
        if not profile.allows(ProfileCapability.LOCAL_BUILD):
            add("profile", authority, "repository profile does not grant local build")
        if not _same_path(profile.repository_root, binding.source_repository):
            add("profile", authority, "repository profile admits another repository root")
        for problem in self._source_problems():
            add("source", capability, problem)
        if not callable(getattr(self.worker, "run", None)):
            add("worker", capability, "no actual patch-proposing worker is supplied")
        else:
            checker = getattr(self.worker, "preflight", None)
            found: object = checker() if callable(checker) else ()
            if not isinstance(found, (list, tuple)):
                add("worker", capability, "worker preflight returned an untyped result")
            else:
                for problem in found:
                    add("worker", capability, str(problem))
        for problem in self.path_problems():
            add("paths", capability, problem)
        try:
            capabilities = self.sandbox.capabilities
        except Exception as error:
            add("sandbox", capability, f"sandbox capabilities are unreadable: {error}")
        else:
            for gap in sandbox_gaps(capabilities, binding.sandbox_requirements):
                add("sandbox", capability, gap)
            if sandbox_identity_digest(capabilities) != binding.sandbox_digest:
                add("sandbox", capability, "sandbox identity differs from the sealed requirement")
        registry_ids = {adapter.adapter_id for adapter in VerificationRegistry().adapters}
        if binding.verifier_adapter_id not in registry_ids:
            add("verifier", capability, "verification adapter is not allowlisted")
        elif binding.verifier_adapter_id not in _RESULT_READERS:
            add("verifier", capability, "no reviewed host result reader exists for this adapter")
        reviewer_id = getattr(self.reviewer, "reviewer_id", None)
        if (
            not callable(getattr(self.reviewer, "review", None))
            or not isinstance(reviewer_id, str)
            or not reviewer_id.strip()
        ):
            add("curator", capability, "no separate actual Curator is supplied")
        elif reviewer_id in {binding.worker_id, binding.repository_id}:
            add("curator", authority, "Curator must be independent from the Builder")
        for spec in binding.holdouts:
            if self.holdouts is None:
                add("holdout", capability, "held-out tests are declared but no custody is supplied")
                break
            try:
                if raw_sha256(self.holdouts.read(spec.path)) != spec.sha256:
                    add("holdout", authority, "held-out bytes differ from their sealed digest")
            except Exception as error:
                add("holdout", capability, f"held-out test is unreadable: {error}")
        return tuple(blockers)


# ------------------------------------------------------------------------ the builder


class RepositoryBuilderAdapter:
    """Durable ``BuilderAdapter``: one retained candidate per attempt identity.

    Every worker call is preceded by an exclusive start record and followed by an
    outcome record, so a restart adopts or refuses existing work instead of
    repeating it.  Each proposal is a complete replacement patch for the same base
    applied to a fresh clean clone; only the selected candidate is committed.
    """

    def __init__(self, context: RepositoryHostContext) -> None:
        self.context = context

    # -- protocol entry -----------------------------------------------------------

    def build(
        self,
        package: OutcomeWorkPackage,
        discovery: DiscoveryOutcome,
        payload: Mapping[str, Any],
    ) -> BuildOutcome:
        context, binding, store = self.context, self.context.binding, self.context.store
        key = attempt_key(binding, package, payload)
        # Before any write: an unsupported path length is a typed blocker, never a
        # failure discovered midway through a run.
        context.require_supported_paths()
        store.seal_binding()
        task = store.task_dir(key)
        task.mkdir(parents=True, exist_ok=True)
        if filesystem_path(store.candidate_path(key)).exists():
            return self._outcome(store.load_candidate(key))
        context.require_admission()
        session = BuilderSession(
            BuilderSessionSpec(
                package.package_id,
                key,
                binding.tenant_id,
                binding.base_commit,
                binding.allowed_paths,
                acceptance_refs=tuple(package.acceptance_ids),
                sandbox_profile="trusted-local" if binding.trusted_local else "isolated",
                model_profile=binding.worker_id,
                max_tools=binding.budget.max_tools,
                max_repairs=binding.budget.max_worker_invocations - 1,
                max_seconds=binding.budget.max_host_seconds,
            )
        )
        result = session.run(lambda live: self._drive(live, package, discovery, key, task))
        # A candidate published during this call wins over any later wall-time
        # bookkeeping: the retained receipt is the single source of truth.
        if filesystem_path(store.candidate_path(key)).exists():
            return self._outcome(store.load_candidate(key))
        return BuildOutcome(
            BuilderSessionResult(
                result.disposition,
                binding.base_commit,
                (),
                result.checks,
                result.failures,
                result.evidence_refs,
            ),
            binding.base_commit,
            candidate_identity(binding.base_commit, binding.base_commit, binding.base_tree),
            False,
        )

    def _outcome(self, record: CandidateRecord) -> BuildOutcome:
        self.context.store.register_identity(record.identity, record.key)
        self.context.remember(record.commit, record.key)
        return BuildOutcome(
            BuilderSessionResult(
                BuilderDisposition.NO_CHANGE
                if record.kind == CANDIDATE_KIND_NO_CHANGE
                else BuilderDisposition.READY_FOR_VERIFICATION,
                record.commit,
                record.changed_paths,
                (),
                (),
                (record.reference,),
            ),
            record.commit,
            record.identity,
            False,
        )

    def _terminal(
        self, disposition: BuilderDisposition, reason: str, slots: Sequence[_Slot], key: str
    ) -> BuilderSessionResult:
        store = self.context.store
        refs = tuple(
            _file_ref(store.slot_path(key, slot.index, part))
            for slot in slots
            for part in ("start", "outcome", "decision")
            if filesystem_path(store.slot_path(key, slot.index, part)).exists()
        )
        return BuilderSessionResult(
            disposition, self.context.binding.base_commit, (), (), (reason,), refs
        )

    # -- the slot loop ------------------------------------------------------------

    def _drive(
        self,
        session: BuilderSession,
        package: OutcomeWorkPackage,
        discovery: DiscoveryOutcome,
        key: str,
        task: Path,
    ) -> BuilderSessionResult:
        binding, store = self.context.binding, self.context.store
        feedback: list[dict[str, Any]] = []
        index = 0
        while True:
            slot = store.load_slot(key, index)
            try:
                if slot is None:
                    if index >= binding.budget.max_worker_invocations:
                        return self._terminal(
                            BuilderDisposition.BUDGET_EXHAUSTED,
                            "worker invocation budget exhausted",
                            store.load_slots(key),
                            key,
                        )
                    spent = sum(item.elapsed for item in store.load_slots(key))
                    if spent >= binding.budget.max_total_worker_seconds:
                        return self._terminal(
                            BuilderDisposition.BUDGET_EXHAUSTED,
                            "worker time budget exhausted",
                            store.load_slots(key),
                            key,
                        )
                    session.record_tool("read")
                    slot = self._start_worker(package, discovery, key, task, index, feedback, spent)
                else:
                    session.record_tool("read")
                    if slot.outcome is None:
                        slot = self._resolve_uncertain(key, task, slot)
                finished = self._decide(session, package, discovery, key, task, slot, feedback)
            except RuntimeError as error:
                # Only BuilderSession's own bare RuntimeError is a budget signal;
                # typed host blockers and any other subclass keep propagating.
                if type(error) is not RuntimeError:
                    raise
                return self._terminal(
                    BuilderDisposition.BUDGET_EXHAUSTED, str(error), store.load_slots(key), key
                )
            if finished is not None:
                return finished
            index += 1

    def _start_worker(
        self,
        package: OutcomeWorkPackage,
        discovery: DiscoveryOutcome,
        key: str,
        task: Path,
        index: int,
        feedback: list[dict[str, Any]],
        spent: float,
    ) -> _Slot:
        context, binding, store = self.context, self.context.binding, self.context.store
        packet = self._packet(package, task, index, feedback)
        packet_digest = canonical_digest(packet)
        timeout = min(binding.budget.worker_timeout_seconds, binding.budget.max_total_worker_seconds - spent)
        evidence = task / f"w{index:03d}"
        scratch = task / f"w{index:03d}-scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        start = _sealed(
            "repository-host-worker-start",
            {
                "attempt_key": key,
                "slot": index,
                "binding_digest": binding.digest,
                "package_id": package.package_id,
                "discovery_digest": discovery.digest,
                "packet_digest": packet_digest,
                "feedback_digest": canonical_digest(feedback),
                "timeout_seconds": timeout,
                "worker_id": binding.worker_id,
                "evidence_directory": evidence.name,
                "host_process_id": os.getpid(),
            },
        )
        if not store.publish(store.slot_path(key, index, "start"), start):
            raise RepositoryHostUncertain("a worker slot record already exists for this attempt")
        node = {
            "id": package.package_id,
            "objective": binding.objective,
            "base_snapshot": binding.base_commit,
            "allowed_paths": list(binding.allowed_paths),
            "acceptance_ids": [spec.acceptance_id for spec in binding.acceptance],
        }
        objective = (
            f"{binding.objective}\n\nReturn ONE complete unified Git diff against exactly the "
            "base commit in the source packet. Each proposal is a full replacement for any "
            "earlier proposal, never an increment on it. Do not touch protected acceptance "
            "or test paths. If the requirement is already satisfied, return status completed "
            "with proposed_patch null and changed_paths []."
        )
        started = time.monotonic()
        receipt: Any = None
        failure: str | None = None
        try:
            receipt = context.worker.run(
                node=node,
                actor_id=binding.worker_id,
                role="builder",
                workspace=scratch,
                evidence_directory=evidence,
                predecessor_reports=list(feedback),
                objective=objective,
                timeout_seconds=timeout,
                writable=True,
                source_packet=packet,
            )
        except Exception as error:
            failure = f"{type(error).__name__}: {_bounded(error)}"
        elapsed = time.monotonic() - started
        outcome = self._outcome_document(key, index, receipt, failure, elapsed, adopted=False)
        store.publish(store.slot_path(key, index, "outcome"), outcome)
        slot = store.load_slot(key, index)
        assert slot is not None
        return slot

    def _outcome_document(
        self,
        key: str,
        index: int,
        receipt: Any,
        failure: str | None,
        elapsed: float,
        *,
        adopted: bool,
    ) -> dict[str, Any]:
        status, reason = "failed", failure
        session_id = model = None
        if failure is None:
            try:
                canonical_bytes(receipt)
                if not isinstance(receipt, dict):
                    raise ValueError("worker receipt is not an object")
                status = str(receipt.get("status"))
                if status not in {"completed", "blocked", "failed"}:
                    status = "failed"
                reason = receipt.get("reason")
                session_id, model = receipt.get("session_id"), receipt.get("model")
            except (TypeError, ValueError):
                status, reason, receipt = "failed", "worker receipt is not canonical JSON", None
        return _sealed(
            "repository-host-worker-outcome",
            {
                "attempt_key": key,
                "slot": index,
                "binding_digest": self.context.binding.digest,
                "status": status,
                "reason": None if reason is None else _bounded(reason),
                "elapsed_seconds": float(elapsed),
                "session_id": session_id if isinstance(session_id, str) else None,
                "model": model if isinstance(model, str) else None,
                "adopted": adopted,
                "receipt": receipt,
                "receipt_digest": canonical_digest(receipt),
            },
        )

    def _resolve_uncertain(self, key: str, task: Path, slot: _Slot) -> _Slot:
        """A slot started without an outcome: adopt proven work or refuse a duplicate."""

        store, binding = self.context.store, self.context.binding
        evidence = task / str(slot.start["evidence_directory"])
        alive: bool | None = None
        process_file = evidence / "process.json"
        if process_file.is_file():
            try:
                alive = process_is_alive(int(json.loads(process_file.read_text("utf-8"))["pid"]))
            except (OSError, ValueError, KeyError, TypeError):
                alive = None
        if alive is True:
            raise RepositoryHostUncertain(f"worker slot {slot.index} process is still running")
        receipt_file = evidence / "receipt.json"
        charged = float(binding.budget.worker_timeout_seconds)
        if receipt_file.is_file():
            try:
                receipt = json.loads(receipt_file.read_text("utf-8"), object_pairs_hook=_unique_object)
            except (OSError, ValueError) as error:
                raise RepositoryHostBlocked("uncertain worker receipt is corrupt") from error
            outcome = self._outcome_document(key, slot.index, receipt, None, charged, adopted=True)
        elif alive is False:
            outcome = self._outcome_document(
                key, slot.index, None, "interrupted: worker process ended without a receipt",
                charged, adopted=True,
            )
        else:
            raise RepositoryHostUncertain(
                f"worker slot {slot.index} has no proven outcome or process end"
            )
        store.publish(store.slot_path(key, slot.index, "outcome"), outcome)
        resolved = store.load_slot(key, slot.index)
        assert resolved is not None
        return resolved

    # -- packet and worker verdict ------------------------------------------------

    @staticmethod
    def _fresh(task: Path, prefix: str) -> Path:
        attempt = 0
        while True:
            name = prefix if attempt == 0 else f"{prefix}-r{attempt}"
            if not (task / name).exists() and not (task / f"{name}-git").exists():
                return task / name
            attempt += 1

    def _materialize(self, container: Path) -> GitWorkspace:
        """A remote-free, detached, hook-free clone of exactly the admitted base."""

        binding = self.context.binding
        try:
            workspace = GitWorkspace.materialize(
                binding.source_repository,
                binding.base_commit,
                container,
                container.with_name(container.name + "-git"),
            )
            workspace._run_git(
                ["remote", "remove", "origin"], Action.READ_REPOSITORY, "remove the clone remote"
            )
            if (
                workspace._git_text(["rev-parse", "HEAD^{tree}"], Action.READ_REPOSITORY, "read base tree")
                != binding.base_tree
            ):
                raise RepositoryHostBlocked("materialized tree differs from the admitted base tree")
            _, listing = workspace._run_git(
                ["ls-tree", "-r", "-z", "--full-tree", "HEAD"],
                Action.READ_REPOSITORY,
                "inspect tracked entry modes",
            )
            for entry in listing.split(b"\0"):
                if entry and (
                    entry.split(b" ", 1)[0] in {b"120000", b"160000"}
                    or entry.split(b"\t", 1)[-1] == b".gitmodules"
                ):
                    raise RepositoryHostBlocked("source contains links or submodules")
            if (workspace.root / ".git" / "objects" / "info" / "alternates").exists():
                raise RepositoryHostBlocked("clone unexpectedly uses Git alternates")
        except (GitOperationFailed, ConfinementViolation, OSError) as error:
            raise RepositoryHostBlocked(f"clean base clone could not be materialized: {_bounded(error)}") from error
        return workspace

    def _packet(
        self, package: OutcomeWorkPackage, task: Path, index: int, feedback: list[dict[str, Any]]
    ) -> dict[str, Any]:
        binding = self.context.binding
        workspace = self._materialize(self._fresh(task, f"p{index:03d}"))
        try:
            packet = build_source_packet(
                workspace.root,
                f"BUILD-{package.package_id}",
                list(feedback),
                max_content_bytes=binding.budget.packet_max_bytes,
                withheld_paths=frozenset(binding.withheld_paths),
            )
        except LocalEvidenceError as error:
            raise RepositoryHostBlocked(f"source packet could not be built: {_bounded(error)}") from error
        if packet["head"] != binding.base_commit:
            raise RepositoryHostBlocked("source packet was not built at the admitted base")
        packet["workspace"] = "host-private-clone"
        packet["host_task"] = {
            "acceptance": [
                {
                    "acceptance_id": spec.acceptance_id,
                    "visible_test_paths": [
                        path for path in spec.test_paths if path not in binding.withheld_paths
                    ],
                    "minimum_tests": spec.minimum_tests,
                }
                for spec in binding.acceptance
            ],
            "allowed_paths": list(binding.allowed_paths),
            "protected_paths": [
                path for path in binding.protected_scope if path not in binding.withheld_paths
            ],
            "withheld_acceptance_checks": len(binding.holdouts),
            "note": "Sealed held-out acceptance content is withheld; its bytes never enter this packet.",
        }
        self._assert_withheld(packet, workspace)
        return packet

    def _assert_withheld(self, packet: Mapping[str, Any], workspace: GitWorkspace) -> None:
        """Backstop: no sealed held-out byte sequence may appear in worker input."""

        provider = self.context.holdouts
        if provider is None:
            return
        rendered = json.dumps(packet, ensure_ascii=False)
        for spec in self.context.binding.holdouts:
            content = provider.read(spec.path).decode("utf-8", "replace").strip()
            if len(content) >= 8 and (
                content in rendered or json.dumps(content, ensure_ascii=False)[1:-1] in rendered
            ):
                raise RepositoryHostBlocked("held-out content reached the builder packet")
            if spec.sha256.removeprefix("sha256:") in rendered:
                raise RepositoryHostBlocked("a held-out digest reached the builder packet")

    def _verdict(
        self, task: Path, slot: _Slot, earlier: Sequence[_Slot]
    ) -> tuple[str, Any]:
        """Classify a recorded worker outcome: patch | no-change | refused | terminal."""

        binding = self.context.binding
        outcome = slot.outcome
        assert outcome is not None
        if outcome["status"] != "completed":
            return "terminal", f"worker {outcome['status']}: {outcome.get('reason') or 'no reason recorded'}"
        receipt = outcome["receipt"]
        if not isinstance(receipt, dict):
            return "terminal", "worker outcome carries no receipt"
        if (
            receipt.get("protocol") != binding.worker_protocol
            or receipt.get("actor_id") != binding.worker_id
            or receipt.get("role") != "builder"
            or receipt.get("execution_mode") != "source-packet"
        ):
            return "terminal", "worker receipt identity differs from the binding"
        session_id = receipt.get("session_id")
        if (
            not isinstance(session_id, str)
            or not session_id.strip()
            or session_id in {item.outcome.get("session_id") for item in earlier if item.outcome}
        ):
            return "terminal", "worker did not report a fresh session identity"
        model = receipt.get("model")
        if binding.worker_model_prefix and not (
            isinstance(model, str) and model.startswith(binding.worker_model_prefix)
        ):
            return "terminal", "worker model differs from the binding"
        evidence = task / str(slot.start["evidence_directory"])
        try:
            packet_bytes = (evidence / "source-packet.json").read_bytes()
            on_disk = json.loads((evidence / "receipt.json").read_text("utf-8"))
            packet_ok = canonical_digest(json.loads(packet_bytes)) == slot.start["packet_digest"]
        except (OSError, ValueError):
            return "terminal", "worker evidence is missing or unreadable"
        if not packet_ok or canonical_digest(on_disk) != canonical_digest(receipt):
            return "terminal", "worker evidence does not match the recorded packet or receipt"
        request = receipt.get("request")
        if isinstance(request, Mapping) and "source_packet_sha256" in request:
            if request["source_packet_sha256"] != hashlib.sha256(packet_bytes).hexdigest():
                return "terminal", "worker receipt binds a different source packet"
        report = receipt.get("report")
        if not isinstance(report, dict):
            return "terminal", "worker report is not an object"
        try:
            _validate_report(report, writable=True, packet_mode=True)
        except ValueError as error:
            declared = report.get("changed_paths")
            if isinstance(declared, list) and any(not _safe_declared(item) for item in declared):
                return "refused", "declared paths must be repository-relative and stay in scope"
            return "terminal", f"worker report failed validation: {_bounded(error)}"
        if report["status"] != "completed":
            return "terminal", f"worker reported blocked: {_bounded(report['summary'])}"
        return ("no-change" if report["proposed_patch"] is None else "patch"), report

    # -- decision and candidate construction --------------------------------------

    def _decide(
        self,
        session: BuilderSession,
        package: OutcomeWorkPackage,
        discovery: DiscoveryOutcome,
        key: str,
        task: Path,
        slot: _Slot,
        feedback: list[dict[str, Any]],
    ) -> BuilderSessionResult | None:
        store = self.context.store
        session.record_tool("edit")
        decision = slot.decision
        if decision is None:
            earlier = store.load_slots(key)[: slot.index]
            kind, detail = self._verdict(task, slot, earlier)
            if kind in {"patch", "no-change"}:
                try:
                    record = self._build_candidate(package, discovery, key, task, slot, kind, detail)
                except _Refusal as refusal:
                    kind, detail = "refused", str(refusal)
                else:
                    return BuilderSessionResult(
                        BuilderDisposition.NO_CHANGE
                        if record.kind == CANDIDATE_KIND_NO_CHANGE
                        else BuilderDisposition.READY_FOR_VERIFICATION,
                        record.commit,
                        record.changed_paths,
                        (),
                        (),
                        (record.reference,),
                    )
            decision = _sealed(
                "repository-host-decision",
                {
                    "attempt_key": key,
                    "slot": slot.index,
                    "binding_digest": self.context.binding.digest,
                    "decision": kind,
                    "reason": _bounded(detail),
                },
            )
            store.publish(store.slot_path(key, slot.index, "decision"), decision)
        slots = store.load_slots(key)
        if decision["decision"] == "terminal":
            return self._terminal(BuilderDisposition.BLOCKED, decision["reason"], slots, key)
        feedback.append(
            {
                "kind": "host-patch-refusal",
                "attempt": slot.index,
                "reason": decision["reason"],
                "instruction": "return a complete replacement patch against the same base commit",
            }
        )
        try:
            fresh = session.record_failure(decision["reason"])
        except RuntimeError:
            return self._terminal(
                BuilderDisposition.BUDGET_EXHAUSTED, "repair budget exhausted", slots, key
            )
        if not fresh:
            return self._terminal(
                BuilderDisposition.BLOCKED, "identical repair failure repeated", slots, key
            )
        return None

    def _require_scope(self, paths: Sequence[str]) -> None:
        binding = self.context.binding
        room = self.context.max_relative_path()
        for item in paths:
            if not _safe_declared(item):
                raise _Refusal("declared paths must be repository-relative and stay in scope")
            if room is not None and len(item) > room:
                raise _Refusal("patch path exceeds the supported path length bound")
            if _within(item, binding.protected_scope):
                raise _Refusal("patch touches sealed protected acceptance or test content")
            if not _within(item, binding.allowed_paths):
                raise _Refusal("patch touches a path outside the admitted write scope")

    def _build_candidate(
        self,
        package: OutcomeWorkPackage,
        discovery: DiscoveryOutcome,
        key: str,
        task: Path,
        slot: _Slot,
        kind: str,
        report: Mapping[str, Any],
    ) -> CandidateRecord:
        binding, store = self.context.binding, self.context.store
        declared: list[str] = []
        patch_text: str | None = None
        if kind == "patch":
            proposed = report["proposed_patch"]
            if not isinstance(proposed, str):
                raise _Refusal("proposed patch is not text")
            patch_text = proposed
            declared = sorted(report["changed_paths"])
            self._require_scope(declared)
        container = self._fresh(task, f"c{slot.index:03d}")
        workspace = self._materialize(container)
        root = workspace.root
        branch: str | None = None
        try:
            if patch_text is not None:
                try:
                    apply_proposed_patch(root, patch_text, list(declared))
                except LocalEvidenceError as error:
                    raise _Refusal(_bounded(error)) from error
                actual = _changed_paths(root)
                if actual != declared:
                    raise _Refusal("observed change set differs from the declared paths")
                self._require_scope(actual)
                branch = f"hive-candidate/{_short(key)}"
                workspace.create_branch(branch)
                commit = workspace.commit(
                    f"Hive candidate for {package.package_id} ({_short(key, 12)})",
                    author_date=_COMMIT_DATE,
                    committer_date=_COMMIT_DATE,
                )
            else:
                commit = binding.base_commit
                if not workspace.status_clean():
                    raise RepositoryHostBlocked("no-change clone is not clean")
            head = workspace._git_text(["rev-parse", "HEAD"], Action.READ_REPOSITORY, "read candidate head")
            tree = workspace._git_text(["rev-parse", "HEAD^{tree}"], Action.READ_REPOSITORY, "read candidate tree")
            if head != commit:
                raise RepositoryHostBlocked("candidate head differs from the committed identity")
            if kind == "patch":
                parents = workspace._git_text(
                    ["rev-list", "--parents", "-n", "1", "HEAD"], Action.READ_REPOSITORY, "read commit parent"
                ).split()
                _, names = workspace._run_git(
                    ["diff", "--name-only", "-z", binding.base_commit, "HEAD"],
                    Action.READ_REPOSITORY,
                    "read committed change set",
                )
                committed = sorted(item.decode("utf-8") for item in names.split(b"\0") if item)
                if parents != [commit, binding.base_commit] or committed != declared:
                    raise RepositoryHostBlocked("committed candidate differs from the applied patch")
                if not workspace.status_clean():
                    raise RepositoryHostBlocked("candidate clone is not clean after commit")
            elif tree != binding.base_tree:
                raise RepositoryHostBlocked("no-change tree differs from the admitted base")
        except (
            GitOperationFailed,
            ConfinementViolation,
            LocalEvidenceError,
            subprocess.SubprocessError,
            OSError,
        ) as error:
            raise RepositoryHostBlocked(f"candidate could not be committed: {_bounded(error)}") from error
        patch_sha: str | None = None
        if patch_text is not None:
            patch_bytes = patch_text.encode("utf-8")
            patch_sha = raw_sha256(patch_bytes)
            _publish_once(task / "candidate.patch", patch_bytes)
        identity = candidate_identity(binding.base_commit, commit, tree)
        assert slot.outcome is not None
        document = _sealed(
            "repository-host-candidate",
            {
                "attempt_key": key,
                "binding_digest": binding.digest,
                "package_id": package.package_id,
                "discovery_digest": discovery.digest,
                "candidate_kind": CANDIDATE_KIND_CHANGED if kind == "patch" else CANDIDATE_KIND_NO_CHANGE,
                "base_commit": binding.base_commit,
                "base_tree": binding.base_tree,
                "candidate_commit": commit,
                "candidate_tree": tree,
                "candidate_identity": identity,
                "changed_paths": declared,
                "patch_sha256": patch_sha,
                "branch": branch,
                "clone": {
                    "root": root.relative_to(task).as_posix(),
                    "receipts": container.with_name(container.name + "-git").relative_to(task).as_posix(),
                },
                "git_receipts": [dict(item) for item in workspace.receipt_records],
                "worker": {
                    "slot": slot.index,
                    "session_id": slot.outcome.get("session_id"),
                    "model": slot.outcome.get("model"),
                    "outcome_digest": slot.outcome["record_digest"],
                },
                "budget_used": {
                    "worker_invocations": len(store.load_slots(key)),
                    "worker_seconds": sum(item.elapsed for item in store.load_slots(key)),
                },
            },
        )
        store.register_identity(identity, key)
        store.publish(store.candidate_path(key), document)
        return store.load_candidate(key)


def _safe_declared(value: object) -> bool:
    try:
        _relative_path(value, "declared path")
    except RepositoryBindingError:
        return False
    return True


# ---------------------------------------------------------------------- the qualifier


class ReceiptBoundCandidateQualifier(CandidateQualifier):
    """Qualify one retained candidate in a separate, verified, remote-free clone.

    The legacy count-only executor is deliberately absent.  A pass needs sealed
    request/candidate/base/tree/test bindings, measured sandbox/toolchain/
    environment identities, and independently parsed test results.
    """

    def __init__(self, context: RepositoryHostContext) -> None:
        super().__init__(None)
        self.context = context

    def _rejection(self, request: QualificationRequest) -> str | None:
        binding = self.context.binding
        expected = {
            "base": (request.base_id, binding.base_commit),
            "acceptance": (
                request.acceptance_manifest,
                tuple(spec.acceptance_id for spec in binding.acceptance),
            ),
            "risk-tier": (request.risk_tier, binding.risk_tier),
            "sandbox": (request.sandbox_digest, binding.sandbox_digest),
            "toolchain": (request.toolchain_digest, binding.toolchain_digest),
            "environment": (request.environment_digest, binding.environment_digest),
            "evaluator": (request.evaluator_id, binding.evaluator_id),
            "cache-origins": (request.allowed_cache_origins, ()),
        }
        for name, (actual, wanted) in expected.items():
            if actual != wanted:
                return f"request-mismatch:{name}"
        return None

    def qualify(self, request: QualificationRequest) -> QualificationReceipt:
        digest = canonical_digest(request)
        try:
            return self._qualify(request, digest)
        except RepositoryHostBlocked as error:
            # Missing or corrupt retained evidence is a typed non-pass, never a
            # silent re-run or a success.
            return QualificationReceipt(
                digest,
                QualificationDisposition.QUARANTINED,
                (),
                (f"blocked:{_bounded(error, 200)}",),
            )

    def _qualify(self, request: QualificationRequest, digest: str) -> QualificationReceipt:
        context, binding, store = self.context, self.context.binding, self.context.store

        def rejected(reason: str) -> QualificationReceipt:
            return QualificationReceipt(digest, QualificationDisposition.QUARANTINED, (), (reason,))

        reason = self._rejection(request)
        if reason is not None:
            return rejected(reason)
        key = context.key_for_commit(request.candidate_id)
        if key is None:
            return rejected("unknown-candidate")
        candidate = store.load_candidate(key)
        if request.candidate_id != candidate.commit or tuple(request.changed_surfaces) != candidate.changed_paths:
            return rejected("candidate-differs-from-request")
        retained = store.load_qualification(key, digest, candidate)
        if retained is not None:
            context.require_admission()
            return retained.receipt
        unsupported = context.path_problems()
        if unsupported:
            return QualificationReceipt(
                digest,
                QualificationDisposition.INCOMPLETE,
                (),
                tuple(f"unsupported-path:{item}" for item in unsupported),
            )
        try:
            capabilities = context.sandbox.capabilities
        except Exception:
            return QualificationReceipt(digest, QualificationDisposition.INCOMPLETE, (), ("sandbox-unreadable",))
        gaps = sandbox_gaps(capabilities, binding.sandbox_requirements)
        if gaps:
            return QualificationReceipt(
                digest,
                QualificationDisposition.INCOMPLETE,
                (),
                tuple(f"sandbox:{gap}" for gap in gaps),
            )
        return self._execute(request, digest, key, candidate)

    def _clone(self, run: Path, candidate: CandidateRecord) -> GitWorkspace:
        try:
            workspace = GitWorkspace.materialize(
                candidate.clone_root, candidate.commit, run / "clone", run / "clone-git"
            )
            workspace._run_git(
                ["remote", "remove", "origin"], Action.READ_REPOSITORY, "remove the clone remote"
            )
            head = workspace._git_text(["rev-parse", "HEAD"], Action.READ_REPOSITORY, "read verifier head")
            tree = workspace._git_text(["rev-parse", "HEAD^{tree}"], Action.READ_REPOSITORY, "read verifier tree")
            if (head, tree) != (candidate.commit, candidate.tree) or not workspace.status_clean():
                raise RepositoryHostBlocked("verifier clone differs from the retained candidate")
            _, listing = workspace._run_git(
                ["ls-tree", "-r", "-z", "--full-tree", "HEAD"], Action.READ_REPOSITORY, "inspect entry modes"
            )
            if any(
                entry.split(b" ", 1)[0] in {b"120000", b"160000"} for entry in listing.split(b"\0") if entry
            ):
                raise RepositoryHostBlocked("candidate contains links or submodules")
        except (GitOperationFailed, ConfinementViolation, OSError) as error:
            raise RepositoryHostBlocked(f"verifier clone could not be materialized: {_bounded(error)}") from error
        return workspace

    def _overlay(self, workspace: GitWorkspace) -> list[dict[str, str]]:
        binding = self.context.binding
        overlay: list[dict[str, str]] = []
        for spec in binding.holdouts:
            provider = self.context.holdouts
            if provider is None:
                raise RepositoryHostBlocked("held-out custody is unavailable at qualification")
            data = provider.read(spec.path)
            if raw_sha256(data) != spec.sha256:
                raise RepositoryHostBlocked("held-out bytes differ from their sealed digest")
            try:
                target = _safe_path(workspace.root, spec.path)
            except LocalEvidenceError as error:
                raise RepositoryHostBlocked(f"held-out path is unsafe: {_bounded(error)}") from error
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            overlay.append({"path": spec.path, "sha256": spec.sha256})
        return overlay

    @staticmethod
    def _drift(workspace: GitWorkspace, candidate: CandidateRecord, overlay: Sequence[Mapping[str, str]]) -> list[str]:
        problems = []
        head = workspace._git_text(["rev-parse", "HEAD"], Action.READ_REPOSITORY, "recheck head")
        tree = workspace._git_text(["rev-parse", "HEAD^{tree}"], Action.READ_REPOSITORY, "recheck tree")
        if (head, tree) != (candidate.commit, candidate.tree):
            problems.append("candidate-drift")
        _, status = workspace._run_git(
            ["status", "--porcelain", "--untracked-files=all"], Action.READ_REPOSITORY, "recheck status"
        )
        allowed = {item["path"] for item in overlay}
        for line in status.decode("utf-8", "replace").splitlines():
            if line[3:].strip('"') not in allowed:
                problems.append("unexpected-workspace-change")
        for item in overlay:
            try:
                current = raw_sha256((workspace.root / item["path"]).read_bytes())
            except OSError:
                current = ""
            if current != item["sha256"]:
                problems.append("held-out-overlay-drift")
        return problems

    def _execute(
        self, request: QualificationRequest, digest: str, key: str, candidate: CandidateRecord
    ) -> QualificationReceipt:
        context, binding, store = self.context, self.context.binding, self.context.store
        qualification = store.task_dir(key) / "qualification"
        run = qualification / f"{_short(digest)}-run"
        attempt = 0
        while run.exists():
            attempt += 1
            run = qualification / f"{_short(digest)}-run-r{attempt}"
        run.mkdir(parents=True)
        workspace = self._clone(run, candidate)
        overlay = self._overlay(workspace)
        drift = self._drift(workspace, candidate, overlay)
        checks: list[CheckReceipt] = []
        recorded: list[dict[str, Any]] = []
        invalidations: list[str] = list(drift)
        origin = (
            "host-sandbox:trusted-local-unqualified"
            if binding.trusted_local
            else "host-sandbox:hostile-isolation"
        )
        for position, spec in enumerate(binding.acceptance):
            evidence = run / f"verify-{position:02d}"
            command = VerificationRegistry().seal(
                workspace.root, spec.test_paths, binding.verifier_adapter_id
            )
            if drift or command is None:
                verdict = {"status": "incomplete", "count": 0,
                           "reasons": ["candidate-drift" if drift else "no-sealed-command"],
                           "artifacts": [], "observed": {}}
                sealed_digest, fixed = "", []
            else:
                sealed_digest = command.digest
                fixed = [list(item) for item in command.fixed_environment]
                try:
                    returned = verify_repository(
                        workspace.root,
                        evidence_directory=evidence,
                        selected_paths=spec.test_paths,
                        adapter_id=binding.verifier_adapter_id,
                        sandbox=context.sandbox,
                        requirements=binding.sandbox_requirements,
                        budget=VerificationBudget(wall_seconds=binding.verification_wall_seconds),
                    )
                except (VerificationError, OSError) as error:
                    verdict = {"status": "failed", "count": 0,
                               "reasons": [f"verification-error:{_bounded(error, 120)}"],
                               "artifacts": [], "observed": {}}
                else:
                    verdict = _evaluate_verification(
                        binding,
                        spec,
                        evidence,
                        returned=returned,
                        command_digest=sealed_digest,
                        fixed_environment=fixed,
                        source=workspace.root,
                    )
            input_digest = canonical_digest(
                {
                    "candidate": candidate.identity,
                    "base_commit": candidate.base_commit,
                    "tree": candidate.tree,
                    "acceptance_id": spec.acceptance_id,
                    "test_paths": list(spec.test_paths),
                    "overlay": overlay,
                    "sealed_command_digest": sealed_digest,
                }
            )
            checks.append(
                CheckReceipt(
                    spec.acceptance_id,
                    "acceptance",
                    input_digest,
                    origin,
                    verdict["status"],
                    int(verdict["count"]),
                    tuple(verdict["artifacts"]),
                    ("held-out-content-withheld-from-builder",) if binding.holdouts else (),
                )
            )
            invalidations.extend(f"{spec.acceptance_id}:{reason}" for reason in verdict["reasons"])
            recorded.append(
                {
                    "name": spec.acceptance_id,
                    "test_paths": list(spec.test_paths),
                    "minimum_tests": spec.minimum_tests,
                    "sealed_command_digest": sealed_digest,
                    "fixed_environment": fixed,
                    "evidence_directory": evidence.relative_to(store.task_dir(key)).as_posix(),
                    "status": verdict["status"],
                    "count": verdict["count"],
                    "observed": verdict["observed"],
                }
            )
        invalidations.extend(f"post-run:{item}" for item in self._drift(workspace, candidate, overlay))
        statuses = {item.status for item in checks}
        if invalidations and "passed" in statuses and statuses == {"passed"}:
            disposition = QualificationDisposition.QUARANTINED
        elif statuses == {"passed"}:
            disposition = QualificationDisposition.PASSED
        elif "failed" in statuses:
            disposition = QualificationDisposition.FAILED
        else:
            disposition = QualificationDisposition.INCOMPLETE
        receipt = QualificationReceipt(digest, disposition, tuple(checks), tuple(dict.fromkeys(invalidations)))
        envelope = _sealed(
            "repository-host-qualification-envelope",
            {
                "attempt_key": key,
                "binding_digest": binding.digest,
                "request_digest": digest,
                "profile": binding.profile_label,
                "pilot_production_qualified": False,
                "candidate": {
                    "identity": candidate.identity,
                    "commit": candidate.commit,
                    "tree": candidate.tree,
                    "base_commit": candidate.base_commit,
                    "base_tree": candidate.base_tree,
                    "changed_paths": list(candidate.changed_paths),
                    "record_digest": candidate.record_digest,
                    "kind": candidate.kind,
                },
                "evaluator_id": binding.evaluator_id,
                "sandbox_digest": binding.sandbox_digest,
                "toolchain_digest": binding.toolchain_digest,
                "environment_digest": binding.environment_digest,
                "overlay": overlay,
                "checks": recorded,
                "disposition": disposition.value,
                "receipt_digest": receipt.digest,
            },
        )
        receipt_path, envelope_path = store.qualification_paths(key, digest)
        _store(envelope_path, envelope)
        _store(
            receipt_path,
            _sealed(
                "repository-host-qualification-receipt",
                {
                    "attempt_key": key,
                    "request_digest": digest,
                    "receipt": canonical_document(receipt),
                    "receipt_digest": receipt.digest,
                },
            ),
        )
        return receipt


# ----------------------------------------------------------------------- the Curator


class RepositoryTerminalCurator:
    """Bind a separately supplied Curator to the exact retained candidate."""

    def __init__(self, context: RepositoryHostContext) -> None:
        self.context = context
        self.curator_id = str(getattr(context.reviewer, "reviewer_id", ""))

    def assess(
        self, candidate: ConvergenceResult, payload: Mapping[str, Any]
    ) -> TerminalAssessment:
        context, binding = self.context, self.context.binding
        candidate_digest = convergence_candidate_digest(candidate)
        packages = candidate.output.get("packages")
        entries = [
            item
            for item in (packages if isinstance(packages, (list, tuple)) else [])
            if isinstance(item, Mapping) and item.get("package_id") == binding.package_id
        ]
        if len(entries) != 1:
            raise RepositoryHostBlocked("terminal candidate lacks exactly this package")
        entry = entries[0]
        identity = entry.get("candidate_digest")
        refs = entry.get("evidence_refs")
        if not isinstance(identity, str) or not isinstance(refs, (list, tuple)):
            raise RepositoryHostBlocked("terminal candidate entry is malformed")
        key = context.store.key_for_identity(identity)
        task = context.store.task_dir(key)
        record, retained = context.revalidate(
            identity, refs, expect_kind=context.store.load_candidate(key).kind
        )
        patch = ""
        if record.kind == CANDIDATE_KIND_CHANGED:
            patch = (task / "candidate.patch").read_text(encoding="utf-8")
        packet = {
            "kind": "repository-host-review-packet",
            "candidate_digest": candidate_digest,
            "package_id": binding.package_id,
            "candidate_identity": record.identity,
            "candidate_kind": record.kind,
            "base_commit": record.base_commit,
            "candidate_commit": record.commit,
            "changed_paths": list(record.changed_paths),
            "patch": patch,
            "acceptance_ids": [spec.acceptance_id for spec in binding.acceptance],
            "qualification_receipt_digest": retained.receipt.digest,
            "qualification_envelope_digest": retained.envelope["record_digest"],
            "qualification_profile": binding.profile_label,
            "pilot_production_qualified": False,
            "builder_id": binding.worker_id,
        }
        packet_digest = canonical_digest(packet)
        review = context.reviewer.review(packet)
        if (
            type(review) is not CandidateReview
            or review.reviewer_id != self.curator_id
            or review.reviewer_id == binding.worker_id
            or review.packet_digest != packet_digest
            or _DIGEST.fullmatch(review.receipt_digest) is None
        ):
            raise RepositoryHostBlocked("Curator review is not bound to the exact candidate packet")
        passed = bool(candidate.accepted and review.accepted)
        label = (
            "trusted-local qualification only; not pilot or production qualified"
            if binding.trusted_local
            else "hostile-isolation profile required; isolation not independently reviewed here"
        )
        return TerminalAssessment(
            VerificationResult(
                passed,
                (
                    f"candidate:{record.identity}",
                    f"qualification:{retained.receipt.digest}",
                    f"profile:{binding.profile_label}",
                ),
                label if passed else f"Curator did not accept the candidate; {label}",
            ),
            TerminalEvidence(
                candidate_digest,
                binding.worker_id,
                review.reviewer_id,
                (f"review:{candidate_digest}:{review.receipt_digest}",),
                (f"aggregate:{candidate_digest}:{retained.receipt.digest}",),
                (f"verification:{candidate_digest}:{retained.envelope['record_digest']}",),
            ),
        )


# ------------------------------------------------------------- the composition host


class _LocalPreparationBroker(DeliveryBroker):
    """Transport-free broker: re-preparing a local artifact is idempotent.

    ``DeliveryBroker.reconcile`` reports a missing intent as BLOCKED, which is right
    when a transport may have written. With no transport and no grants there is no
    remote effect to reconcile, so an interrupted local preparation simply repeats.
    """

    def reconcile(self, r):  # type: ignore[no-untyped-def]
        return self.prepare(r)


class RepositoryCompositionHost(WholeOSCompositionHost):
    """``WholeOSCompositionHost`` for local preparation of one repository task."""

    def __init__(
        self,
        context: RepositoryHostContext,
        *,
        manifest: CompositionManifest,
        profile_id: str,
        discovery: DiscoveryAdapter,
        delivery: DeliveryBroker | None = None,
        publish_required: bool = False,
    ) -> None:
        binding = context.binding
        broker = delivery or _LocalPreparationBroker(
            state_path=context.store.root / "delivery.json"
        )
        if broker.transport is not None or broker.grants:
            raise RepositoryBindingError(
                "local preparation accepts no delivery transport or grant"
            )
        self.context = context
        super().__init__(
            state_directory=context.store.root / "composition",
            manifest=manifest,
            profile_id=profile_id,
            repository_profile=context.repository_profile,
            discovery=discovery,
            builder=RepositoryBuilderAdapter(context),
            qualifier=ReceiptBoundCandidateQualifier(context),
            delivery=broker,
            delivery_policy=DeliveryPolicy(
                binding.delivery_label,
                binding.base_commit,
                "hive-candidate",
                "no-external-delivery-grant",
                binding.sandbox_digest,
                binding.toolchain_digest,
                binding.environment_digest,
                binding.evaluator_id,
                LearningScope.TARGET_APP,
                learning_authorization_digest=binding.learning_authorization_digest,
                publish_required=publish_required,
                feedback_required=False,
            ),
            feedback_source=None,
            learning=DurableLearningRecorder(context.store.root / "learning"),
            curator=RepositoryTerminalCurator(context),
            producer_id=binding.worker_id,
        )

    def _receipt_path(self, payload: Mapping[str, Any], package_id: str) -> Path:
        key = canonical_digest(
            {
                "campaign_id": payload.get("campaign_id"),
                "tenant_id": payload.get("tenant_id"),
                "repository_id": payload.get("repository_id"),
                "graph_digest": payload.get("graph_digest"),
                "package_id": package_id,
                "repository_host_binding": payload.get("repository_host_binding_digest"),
            }
        ).removeprefix("sha256:")
        return self.state_directory / "composition-receipts" / f"{key}.json"

    def _validate_subject(self, payload: Mapping[str, Any]) -> CompositionBlocker | None:
        blocker = super()._validate_subject(payload)
        if blocker is not None:
            return blocker
        binding = self.context.binding
        kickoff = payload.get("cohort_kickoff")
        mismatches = []
        if payload.get("repository_host_binding_digest") != binding.digest:
            mismatches.append("host binding")
        if payload.get("package_id") != binding.package_id:
            mismatches.append("package")
        if payload.get("campaign_id") != binding.campaign_id:
            mismatches.append("campaign")
        if payload.get("graph_digest") != binding.graph_digest:
            mismatches.append("graph")
        if not isinstance(kickoff, Mapping) or kickoff.get("context_digest") != binding.context_digest:
            mismatches.append("context")
        try:
            if _base_snapshot(payload) != binding.base_commit:
                mismatches.append("base")
        except CompositionError:
            mismatches.append("base")
        if payload.get("allowed_paths") != list(binding.allowed_paths):
            mismatches.append("allowed paths")
        if payload.get("acceptance_ids") != [spec.acceptance_id for spec in binding.acceptance]:
            mismatches.append("acceptance manifest")
        if mismatches:
            return CompositionBlocker(
                "profile",
                BlockerKind.BLOCKED_AUTHORITY,
                "task differs from the frozen host binding: " + ", ".join(mismatches),
            )
        return None

    def _no_change_permitted(self, package: OutcomeWorkPackage, payload: Mapping[str, Any]) -> bool:
        return self.context.binding.no_change_permitted and super()._no_change_permitted(
            package, payload
        )

    def _preserve_history(self, path: Path, reason: str) -> None:
        """Keep an invalidated terminal result as a historical receipt."""

        try:
            retained = filesystem_path(path).read_bytes()
        except OSError:
            return
        name = raw_sha256(retained + reason.encode("utf-8")).removeprefix("sha256:")
        _publish_once(
            self.context.store.root / "historical-results" / f"{name}.json",
            canonical_bytes(
                {
                    "kind": "repository-host-invalidated-result",
                    "reason": reason,
                    "result_sha256": raw_sha256(retained),
                    "result": retained.decode("utf-8", "replace"),
                }
            )
            + b"\n",
        )

    def _unsealed(
        self, package: OutcomeWorkPackage, blocker: CompositionBlocker
    ) -> PackageExecutionResult:
        if blocker.stage != "paths":
            # An unsupported private root must not be written to at all, not even
            # with the blocker record; the typed result still carries the reason.
            _store(
                self.context.store.root / "blockers" / f"{_short(blocker.reference)}.json",
                _sealed(
                    "repository-host-blocker",
                    {"stage": blocker.stage, "kind": blocker.kind.value, "detail": blocker.detail},
                ),
            )
        return PackageExecutionResult(
            package.package_id,
            PackageStatus.BLOCKED_AUTHORITY
            if blocker.kind is BlockerKind.BLOCKED_AUTHORITY
            else PackageStatus.BLOCKED_CAPABILITY,
            None,
            (blocker.reference,),
            blocker.message,
        )

    def execute_package(
        self,
        package: OutcomeWorkPackage,
        bindings: tuple[Any, Any],
        payload: Mapping[str, Any],
    ) -> PackageExecutionResult:
        namespaced = dict(_plain(payload))
        namespaced["repository_host_binding_digest"] = self.context.binding.digest
        payload_digest = canonical_digest(_plain(namespaced))
        path = self._receipt_path(namespaced, package.package_id)
        retained = self._load_result(path, payload_digest)
        if retained is not None and retained.status in _SUCCESS:
            reason = self._replay_rejection(package, namespaced, retained)
            if reason is None:
                return retained
            self._preserve_history(path, reason)
            return self._unsealed(
                package,
                CompositionBlocker(
                    "replay",
                    BlockerKind.BLOCKED_CAPABILITY,
                    f"retained success no longer validates: {reason}",
                ),
            )
        if retained is None:
            subject = self._validate_subject(namespaced)
            if subject is not None:
                return self._unsealed(package, subject)
            blockers = self.context.preflight()
            if blockers:
                return self._unsealed(package, blockers[0])
        return super().execute_package(package, bindings, namespaced)

    def _replay_rejection(
        self, package: OutcomeWorkPackage, payload: Mapping[str, Any], retained: PackageExecutionResult
    ) -> str | None:
        subject = self._validate_subject(payload)
        if subject is not None:
            return subject.message
        expect = (
            CANDIDATE_KIND_CHANGED
            if retained.status is PackageStatus.COMPLETED
            else CANDIDATE_KIND_NO_CHANGE
        )
        try:
            self.context.revalidate(
                str(retained.candidate_digest), retained.evidence_refs, expect_kind=expect
            )
        except (RepositoryHostBlocked, KeyError, TypeError, ValueError, OSError) as error:
            return f"{type(error).__name__}: {error}"
        return None

    def validate_retained_package_result(
        self,
        package: OutcomeWorkPackage,
        result: PackageExecutionResult,
        payload: Mapping[str, Any],
    ) -> str | None:
        """Outer-replay guard used by ``WholeOSService`` (see ``WholeOSReplayValidator``).

        The service keeps its own package receipt, so it would report a finished
        package as complete forever.  This read-only check is what makes a resumed
        success current: the full host binding and payload, the host's own terminal
        receipt, current admission, and the retained candidate and qualification
        artifacts must all still hold.  It never runs a worker or mutates Git.
        """

        if result.status not in _SUCCESS:
            return "retained result is not a success"
        if result.package_id != package.package_id:
            return "retained result belongs to another package"
        namespaced = dict(_plain(payload))
        namespaced["repository_host_binding_digest"] = self.context.binding.digest
        payload_digest = canonical_digest(_plain(namespaced))
        try:
            own = self._load_result(
                self._receipt_path(namespaced, package.package_id), payload_digest
            )
        except CompositionError as error:
            return f"host terminal receipt is invalid: {error}"
        if own is None:
            return "host terminal receipt is absent for this binding"
        if (own.status, own.candidate_digest, own.evidence_refs) != (
            result.status,
            result.candidate_digest,
            result.evidence_refs,
        ):
            return "service receipt differs from the host terminal receipt"
        return self._replay_rejection(package, namespaced, own)

    def assess_terminal_candidate(
        self, candidate: ConvergenceResult, payload: Mapping[str, Any]
    ) -> TerminalAssessment:
        self.context.require_admission()
        return super().assess_terminal_candidate(candidate, payload)


# ---------------------------------------------------------------------------- factory


def compose_repository_factory(
    *,
    context: RepositoryHostContext,
    descriptor: MissionBindingDescriptor,
    manifest: CompositionManifest,
    profile_id: str,
    discovery: DiscoveryAdapter,
    delivery: DeliveryBroker | None = None,
    publish_required: bool = False,
) -> Callable[[WholeOSServiceConfig], WholeOSHostBootstrap]:
    """Build a factory for ``WholeOSHostBootstrap``; refuse it if a dependency is missing.

    Preflight runs here, before any service attempt exists, so a missing worker,
    sandbox, Curator or authority binding never becomes a sealed dead-letter.  The
    returned factory is *not* registered: registration and its independent
    validation evidence belong to the trusted launcher.
    """

    binding = context.binding
    if (descriptor.tenant_id, descriptor.repository_id) != (binding.tenant_id, binding.repository_id):
        raise RepositoryBindingError("mission descriptor targets another tenant or repository")
    blockers = context.preflight()
    if blockers:
        raise RepositoryHostUnavailable(blockers)

    def factory(supplied: WholeOSServiceConfig) -> WholeOSHostBootstrap:
        if (
            supplied.binding_descriptor.digest != descriptor.digest
            or supplied.graph.digest != binding.graph_digest
            or supplied.campaign_id != binding.campaign_id
            or supplied.graph.base_snapshot != binding.base_commit
            or service_context_digest(supplied) != binding.context_digest
            or (supplied.tenant_id, supplied.repository_id)
            != (binding.tenant_id, binding.repository_id)
        ):
            raise RepositoryHostUnavailable(
                (
                    CompositionBlocker(
                        "factory",
                        BlockerKind.BLOCKED_AUTHORITY,
                        "service configuration differs from the frozen host binding",
                    ),
                )
            )
        provider = ConfiguredMissionBindingsProvider(
            descriptor,
            lambda _descriptor, _payload, _state: (
                {"repository_id": binding.repository_id, "base_commit": binding.base_commit},
                {"delivery": "local-preparation-only", "credential_values": "not-present"},
            ),
        )
        host = RepositoryCompositionHost(
            context,
            manifest=manifest,
            profile_id=profile_id,
            discovery=discovery,
            delivery=delivery,
            publish_required=publish_required,
        )
        return WholeOSHostBootstrap(provider, host)

    return factory


__all__ = [
    "AcceptanceSpec",
    "CandidateRecord",
    "CandidateReview",
    "CandidateReviewer",
    "DEFAULT_PATH_LIMIT",
    "HoldoutSource",
    "HoldoutSpec",
    "HostAdmission",
    "PatchWorker",
    "ProfileRegistryAdmission",
    "ReceiptBoundCandidateQualifier",
    "RepositoryBindingError",
    "RepositoryBuildBudget",
    "RepositoryBuilderAdapter",
    "RepositoryCompositionHost",
    "RepositoryHostBlocked",
    "RepositoryHostContext",
    "RepositoryHostUncertain",
    "RepositoryHostUnavailable",
    "RepositoryStateStore",
    "RepositoryTaskBinding",
    "RepositoryTerminalCurator",
    "attempt_key",
    "candidate_identity",
    "compose_repository_factory",
    "environment_identity_digest",
    "process_is_alive",
    "read_unittest_results",
    "sandbox_gaps",
    "sandbox_identity_digest",
    "service_context_digest",
    "toolchain_identity_digest",
    "WINDOWS_PATH_LIMIT",
]
