"""Host-issued repository execution profiles.

This is deliberately an admission and persistence boundary, not an executor.
Target metadata can select a named binding, but it can never supply a command,
path, environment value, grant, or export destination to a privileged host.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

from .path_boundary import ExternalPathRequired, is_within, require_external_path, resolved_path
from .runtime_contracts import canonical_digest, strict_json_object

_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+)*$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_ENV = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_PLACEHOLDER = re.compile(r"^\{[a-z][a-z0-9_]*\}$")


class RepositoryProfileError(ValueError):
    """Profile data is ambiguous, target-owned, or outside its host boundary."""


class CapabilityStatus(StrEnum):
    REAL = "real"
    MOCK = "mock"
    UNAVAILABLE = "unavailable"
    DENIED = "denied"
    UNTESTED = "untested"


class ProfileCapability(StrEnum):
    READ_ONLY_PLAN = "read_only_plan"
    LOCAL_BUILD = "local_build"
    CODE_PR = "code_pr"
    LEARNING_EXPORT = "learning_export"
    DEPLOYMENT = "deployment"


def _id(value: str, label: str) -> None:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise RepositoryProfileError(f"{label} must be a canonical identifier")


def _digest(value: str, label: str) -> None:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise RepositoryProfileError(f"{label} must be a lowercase sha256 digest")


def _tuple(values: tuple[str, ...], label: str, pattern: re.Pattern[str] = _ID) -> None:
    if type(values) is not tuple or values != tuple(sorted(set(values))):
        raise RepositoryProfileError(f"{label} must be a sorted immutable tuple")
    if any(type(value) is not str or pattern.fullmatch(value) is None for value in values):
        raise RepositoryProfileError(f"{label} contains an invalid value")


def _git_control_paths(root: Path) -> tuple[Path, ...]:
    """Find Git metadata and alternates without treating them as authority."""
    dot_git = root / ".git"
    paths: list[Path] = [dot_git]
    if dot_git.is_file():
        try:
            line = dot_git.read_text(encoding="utf-8").splitlines()[0]
            if line.startswith("gitdir: "):
                paths.append(resolved_path(root / line[8:]))
        except (OSError, IndexError, UnicodeError):
            pass
    git_dir = next((p for p in paths if p.is_dir()), dot_git)
    common = git_dir / "commondir"
    if common.is_file():
        try:
            paths.append(resolved_path(git_dir / common.read_text(encoding="utf-8").strip()))
        except (OSError, UnicodeError):
            pass
    for base in tuple(paths):
        alternate_file = base / "objects" / "info" / "alternates"
        if alternate_file.is_file():
            try:
                paths.extend(resolved_path(base / line.strip()) for line in alternate_file.read_text(encoding="utf-8").splitlines() if line.strip())
            except (OSError, UnicodeError):
                pass
    return tuple(paths)


@dataclass(frozen=True, slots=True)
class HostIdentity:
    tenant_id: str
    repository_id: str
    issuer_id: str
    authority_digest: str

    def __post_init__(self) -> None:
        _id(self.tenant_id, "tenant_id"); _id(self.repository_id, "repository_id")
        _id(self.issuer_id, "issuer_id"); _digest(self.authority_digest, "authority_digest")
        if self.issuer_id in {self.tenant_id, self.repository_id}:
            raise RepositoryProfileError("identity issuer must be a distinct host authority")


@dataclass(frozen=True, slots=True)
class CapabilityGrant:
    capability: ProfileCapability
    grant_id: str
    grant_digest: str
    revoked: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.capability, ProfileCapability):
            object.__setattr__(self, "capability", ProfileCapability(self.capability))
        _id(self.grant_id, "grant_id"); _digest(self.grant_digest, "grant_digest")
        if type(self.revoked) is not bool: raise RepositoryProfileError("revoked must be boolean")


@dataclass(frozen=True, slots=True)
class HostToolBinding:
    adapter_id: str
    version: str
    executable_path: str | None
    binary_digest: str | None
    platform: str
    fixed_argv: tuple[str, ...]
    placeholders: tuple[str, ...]
    safe_environment_names: tuple[str, ...] = ()
    secret_handles: tuple[str, ...] = ()
    timeout_seconds: int = 0
    status: CapabilityStatus = CapabilityStatus.UNTESTED
    probe_receipt_digest: str | None = None

    def __post_init__(self) -> None:
        _id(self.adapter_id, "adapter_id")
        if type(self.version) is not str or not self.version.strip(): raise RepositoryProfileError("version is required")
        if self.executable_path is not None:
            candidate = Path(self.executable_path)
            if not candidate.is_absolute(): raise RepositoryProfileError("executable_path must be absolute")
            object.__setattr__(self, "executable_path", str(resolved_path(candidate)))
        if self.binary_digest is not None: _digest(self.binary_digest, "binary_digest")
        if type(self.platform) is not str or not self.platform: raise RepositoryProfileError("platform is required")
        if type(self.fixed_argv) is not tuple or not self.fixed_argv: raise RepositoryProfileError("fixed_argv must be immutable and non-empty")
        if any(type(v) is not str or not v or "\x00" in v for v in self.fixed_argv): raise RepositoryProfileError("fixed_argv is invalid")
        _tuple(self.placeholders, "placeholders", _PLACEHOLDER)
        if any(_PLACEHOLDER.fullmatch(v) and v not in self.placeholders for v in self.fixed_argv): raise RepositoryProfileError("fixed_argv uses an unpermitted placeholder")
        _tuple(self.safe_environment_names, "safe_environment_names", _ENV)
        _tuple(self.secret_handles, "secret_handles")
        if type(self.timeout_seconds) is not int or isinstance(self.timeout_seconds, bool) or self.timeout_seconds < 0: raise RepositoryProfileError("timeout_seconds must be non-negative")
        if not isinstance(self.status, CapabilityStatus): object.__setattr__(self, "status", CapabilityStatus(self.status))
        if self.status is CapabilityStatus.REAL and (self.executable_path is None or self.binary_digest is None or self.probe_receipt_digest is None): raise RepositoryProfileError("real tool binding requires path, digest, and probe receipt")
        if self.status is CapabilityStatus.UNAVAILABLE and self.executable_path is not None: raise RepositoryProfileError("unavailable binding must not invent an executable path")
        if self.probe_receipt_digest is not None: _digest(self.probe_receipt_digest, "probe_receipt_digest")


@dataclass(frozen=True, slots=True)
class CapabilityReport:
    adapter_id: str
    status: CapabilityStatus
    reason: str
    receipt_digest: str | None = None
    def __post_init__(self) -> None:
        _id(self.adapter_id, "adapter_id")
        if not isinstance(self.status, CapabilityStatus): object.__setattr__(self, "status", CapabilityStatus(self.status))
        if type(self.reason) is not str or not self.reason.strip(): raise RepositoryProfileError("capability report reason is required")
        if self.receipt_digest is not None: _digest(self.receipt_digest, "receipt_digest")


@dataclass(frozen=True, slots=True)
class RepositoryProfile:
    profile_id: str
    identity: HostIdentity
    repository_root: str
    workspace_root: str
    state_root: str
    cache_root: str
    grants: tuple[CapabilityGrant, ...]
    tools: tuple[HostToolBinding, ...]
    reports: tuple[CapabilityReport, ...]
    external_destinations: tuple[str, ...] = ()
    sensitivity: str = "unknown"
    profile_digest: str = ""

    def __post_init__(self) -> None:
        _id(self.profile_id, "profile_id")
        if type(self.identity) is not HostIdentity: raise RepositoryProfileError("identity must be host-issued HostIdentity")
        root = resolved_path(self.repository_root)
        if not root.is_absolute(): raise RepositoryProfileError("repository_root must be absolute")
        object.__setattr__(self, "repository_root", str(root))
        controls = _git_control_paths(root)
        for name in ("workspace_root", "state_root", "cache_root"):
            try:
                value = require_external_path(getattr(self, name), root, label=name)
            except ExternalPathRequired as error:
                raise RepositoryProfileError(str(error)) from error
            if any(is_within(value, control) for control in controls):
                raise RepositoryProfileError(f"{name} must not overlap Git common-dir or alternates")
            object.__setattr__(self, name, str(value))
        if len({os.path.normcase(str(resolved_path(getattr(self, n)))) for n in ("workspace_root", "state_root", "cache_root")}) != 3: raise RepositoryProfileError("workspace/state/cache roots must be distinct")
        if type(self.grants) is not tuple or len({g.capability for g in self.grants}) != len(self.grants): raise RepositoryProfileError("grants must have one immutable record per capability")
        if any(type(g) is not CapabilityGrant for g in self.grants): raise RepositoryProfileError("grants must be typed")
        if type(self.tools) is not tuple or len({t.adapter_id for t in self.tools}) != len(self.tools): raise RepositoryProfileError("tools must have unique admitted adapter IDs")
        if any(type(t) is not HostToolBinding for t in self.tools): raise RepositoryProfileError("tools must be typed")
        if type(self.reports) is not tuple or any(type(r) is not CapabilityReport for r in self.reports): raise RepositoryProfileError("reports must be typed")
        if type(self.external_destinations) is not tuple or self.external_destinations != tuple(sorted(set(self.external_destinations))): raise RepositoryProfileError("external_destinations must be sorted immutable")
        if any(type(v) is not str or not v.startswith("https://") or "?" in v or "#" in v for v in self.external_destinations): raise RepositoryProfileError("external destination is not admitted")
        if self.sensitivity not in {"unknown", "private", "public"}: raise RepositoryProfileError("sensitivity is unknown, private, or public")
        expected = canonical_digest(self.to_document(include_digest=False))
        if not self.profile_digest: object.__setattr__(self, "profile_digest", expected)
        elif self.profile_digest != expected: raise RepositoryProfileError("profile_digest does not seal profile fields")

    def to_document(self, *, include_digest: bool = True) -> dict[str, Any]:
        result = {"profile_id": self.profile_id, "identity": self.identity.__dict__ if hasattr(self.identity, "__dict__") else {"tenant_id":self.identity.tenant_id,"repository_id":self.identity.repository_id,"issuer_id":self.identity.issuer_id,"authority_digest":self.identity.authority_digest}, "repository_root":self.repository_root,"workspace_root":self.workspace_root,"state_root":self.state_root,"cache_root":self.cache_root,"grants":[{"capability":g.capability.value,"grant_id":g.grant_id,"grant_digest":g.grant_digest,"revoked":g.revoked} for g in self.grants], "tools":[{"adapter_id":t.adapter_id,"version":t.version,"executable_path":t.executable_path,"binary_digest":t.binary_digest,"platform":t.platform,"fixed_argv":list(t.fixed_argv),"placeholders":list(t.placeholders),"safe_environment_names":list(t.safe_environment_names),"secret_handles":list(t.secret_handles),"timeout_seconds":t.timeout_seconds,"status":t.status.value,"probe_receipt_digest":t.probe_receipt_digest} for t in self.tools], "reports":[{"adapter_id":r.adapter_id,"status":r.status.value,"reason":r.reason,"receipt_digest":r.receipt_digest} for r in self.reports], "external_destinations":list(self.external_destinations),"sensitivity":self.sensitivity}
        if include_digest: result["profile_digest"] = self.profile_digest
        return result

    def allows(self, capability: ProfileCapability, *, destination: str | None = None) -> bool:
        capability = ProfileCapability(capability)
        if capability is ProfileCapability.READ_ONLY_PLAN: return True
        grant = next((g for g in self.grants if g.capability is capability), None)
        if grant is None or grant.revoked: return False
        if destination is not None and (self.sensitivity == "unknown" or destination not in self.external_destinations): return False
        return True

    def projection(self) -> Mapping[str, Any]:
        return {"profile_id": self.profile_id, "tenant_id": self.identity.tenant_id, "repository_id": self.identity.repository_id, "profile_digest": self.profile_digest, "capabilities": {c.value: self.allows(c) for c in ProfileCapability}}

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "RepositoryProfile":
        fields = {"profile_id", "identity", "repository_root", "workspace_root", "state_root", "cache_root", "grants", "tools", "reports", "external_destinations", "sensitivity", "profile_digest"}
        if not isinstance(document, Mapping) or set(document) != fields:
            raise RepositoryProfileError("repository profile has unknown or missing fields")
        identity = document["identity"]
        if not isinstance(identity, Mapping) or set(identity) != {"tenant_id", "repository_id", "issuer_id", "authority_digest"}:
            raise RepositoryProfileError("identity is not a closed host identity")
        try:
            return cls(
                document["profile_id"], HostIdentity(**identity), document["repository_root"], document["workspace_root"], document["state_root"], document["cache_root"],
                tuple(CapabilityGrant(**item) for item in document["grants"]),
                tuple(HostToolBinding(adapter_id=item["adapter_id"], version=item["version"], executable_path=item["executable_path"], binary_digest=item["binary_digest"], platform=item["platform"], fixed_argv=tuple(item["fixed_argv"]), placeholders=tuple(item["placeholders"]), safe_environment_names=tuple(item["safe_environment_names"]), secret_handles=tuple(item["secret_handles"]), timeout_seconds=item["timeout_seconds"], status=item["status"], probe_receipt_digest=item["probe_receipt_digest"]) for item in document["tools"]),
                tuple(CapabilityReport(**item) for item in document["reports"]), tuple(document["external_destinations"]), document["sensitivity"], document["profile_digest"])
        except (KeyError, TypeError, ValueError) as error:
            raise RepositoryProfileError("repository profile document is invalid") from error


class RepositoryProfileStore:
    """Atomic host-side storage; the target repository is never a valid store."""
    def __init__(self, directory: str | Path, *, repository_root: str | Path) -> None:
        try:
            self.directory = require_external_path(directory, repository_root, label="profile store")
        except ExternalPathRequired as error:
            raise RepositoryProfileError(str(error)) from error
        self.directory.mkdir(parents=True, exist_ok=True)
    def write(self, profile: RepositoryProfile) -> Path:
        if is_within(self.directory, profile.repository_root): raise RepositoryProfileError("profile store overlaps target repository")
        target = self.directory / f"{profile.profile_id}.json"
        data = json.dumps(profile.to_document(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        fd, name = tempfile.mkstemp(prefix=".profile-", suffix=".tmp", dir=self.directory)
        try:
            with os.fdopen(fd, "wb") as stream: stream.write(data); stream.flush(); os.fsync(stream.fileno())
            os.replace(name, target)
        finally:
            if os.path.exists(name): os.unlink(name)
        return target
    def read_document(self, profile_id: str) -> dict[str, Any]:
        _id(profile_id, "profile_id")
        return strict_json_object((self.directory / f"{profile_id}.json").read_bytes())
    def load(self, profile_id: str) -> RepositoryProfile:
        return RepositoryProfile.from_document(self.read_document(profile_id))


__all__ = ["CapabilityGrant", "CapabilityReport", "CapabilityStatus", "HostIdentity", "HostToolBinding", "ProfileCapability", "RepositoryProfile", "RepositoryProfileError", "RepositoryProfileStore"]
