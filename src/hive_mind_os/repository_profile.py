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
import threading
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Protocol

from .path_boundary import ExternalPathRequired, is_within, require_external_path, resolved_path
from .runtime_contracts import canonical_digest, strict_json_object
from .brain_kernel.authority import AuthorityDenied, AuthorityRegistry, CapabilityToken, token_is_issued

_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+)*$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_ENV = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_PLACEHOLDER = re.compile(r"^\{[a-z][a-z0-9_]*\}$")
_SAFE_ENVIRONMENT = frozenset({"LANG", "LC_ALL", "TZ", "SOURCE_DATE_EPOCH"})
_ALLOWED_PLACEHOLDERS = frozenset({"{workspace}", "{state}", "{cache}", "{output}"})
_SHELLS = frozenset({"cmd", "cmd.exe", "powershell", "powershell.exe", "sh", "bash", "python", "python.exe", "pwsh", "pwsh.exe"})
_STORE_LOCK = threading.RLock()


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


class HostProfileRegistry(Protocol):
    """Composition-injected, persistent host custody boundary (never a module key)."""
    def verify_profile(self, *, registry_handle: str, profile_digest: str, tenant_id: str, repository_id: str, authority_digest: str, generation: int) -> bool: ...
    def authorize_capability(self, *, registry_handle: str, profile_digest: str, generation: int, capability: str, destination: str | None) -> bool: ...


def _raw_absolute(value: str, label: str) -> Path:
    if type(value) is not str or not value or value.startswith("\\\\") or not Path(value).is_absolute():
        raise RepositoryProfileError(f"{label} must be an admitted absolute local path")
    raw = Path(value)
    if ".." in raw.parts:
        raise RepositoryProfileError(f"{label} must not contain parent traversal")
    return raw


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
                paths.extend(resolved_path((base / "objects") / line.strip()) for line in alternate_file.read_text(encoding="utf-8").splitlines() if line.strip())
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
    host_receipt_witness: str = ""

    def __post_init__(self) -> None:
        _id(self.adapter_id, "adapter_id")
        if type(self.version) is not str or not self.version.strip(): raise RepositoryProfileError("version is required")
        if self.executable_path is not None:
            candidate = _raw_absolute(self.executable_path, "executable_path")
            object.__setattr__(self, "executable_path", str(resolved_path(candidate)))
        if self.binary_digest is not None: _digest(self.binary_digest, "binary_digest")
        if type(self.platform) is not str or not self.platform: raise RepositoryProfileError("platform is required")
        if type(self.fixed_argv) is not tuple or not self.fixed_argv: raise RepositoryProfileError("fixed_argv must be immutable and non-empty")
        if any(type(v) is not str or not v or "\x00" in v for v in self.fixed_argv): raise RepositoryProfileError("fixed_argv is invalid")
        _tuple(self.placeholders, "placeholders", _PLACEHOLDER)
        if not set(self.placeholders).issubset(_ALLOWED_PLACEHOLDERS): raise RepositoryProfileError("placeholder is not host admitted")
        if any("{" in v or "}" in v for v in self.fixed_argv if not _PLACEHOLDER.fullmatch(v)): raise RepositoryProfileError("embedded placeholders are forbidden")
        if any(_PLACEHOLDER.fullmatch(v) and v not in self.placeholders for v in self.fixed_argv): raise RepositoryProfileError("fixed_argv uses an unpermitted placeholder")
        if self.fixed_argv[0].lower() in _SHELLS or (self.executable_path and Path(self.executable_path).name.lower() in _SHELLS): raise RepositoryProfileError("shells and interpreters are not admitted tool bindings")
        _tuple(self.safe_environment_names, "safe_environment_names", _ENV)
        if not set(self.safe_environment_names).issubset(_SAFE_ENVIRONMENT): raise RepositoryProfileError("safe_environment_names includes a privileged name")
        _tuple(self.secret_handles, "secret_handles")
        if self.secret_handles: raise RepositoryProfileError("secret handles remain only in the host broker")
        if type(self.timeout_seconds) is not int or isinstance(self.timeout_seconds, bool) or self.timeout_seconds < 0: raise RepositoryProfileError("timeout_seconds must be non-negative")
        if not isinstance(self.status, CapabilityStatus): object.__setattr__(self, "status", CapabilityStatus(self.status))
        if self.status is CapabilityStatus.REAL: raise RepositoryProfileError("REAL tool binding requires injected host discovery verification")
        if self.status is CapabilityStatus.UNAVAILABLE and self.executable_path is not None: raise RepositoryProfileError("unavailable binding must not invent an executable path")
        if self.probe_receipt_digest is not None: _digest(self.probe_receipt_digest, "probe_receipt_digest")

    def _receipt_payload(self) -> dict[str, Any]:
        return {"adapter_id": self.adapter_id, "version": self.version, "executable_path": self.executable_path, "binary_digest": self.binary_digest, "platform": self.platform, "probe_receipt_digest": self.probe_receipt_digest}


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


def undiscovered_capability_report(adapter_ids: tuple[str, ...]) -> tuple[CapabilityReport, ...]:
    """Host discovery seam: PATH presence is not an execution attestation."""
    _tuple(adapter_ids, "adapter_ids")
    return tuple(CapabilityReport(item, CapabilityStatus.UNTESTED, "host-issued discovery receipt required") for item in adapter_ids)


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
    registry_handle: str = ""
    generation: int = 0
    profile_digest: str = ""

    def __post_init__(self) -> None:
        _id(self.profile_id, "profile_id")
        if type(self.identity) is not HostIdentity: raise RepositoryProfileError("identity must be host-issued HostIdentity")
        root = resolved_path(_raw_absolute(self.repository_root, "repository_root"))
        object.__setattr__(self, "repository_root", str(root))
        controls = _git_control_paths(root)
        for name in ("workspace_root", "state_root", "cache_root"):
            try:
                value = require_external_path(_raw_absolute(getattr(self, name), name), root, label=name)
            except ExternalPathRequired as error:
                raise RepositoryProfileError(str(error)) from error
            if any(is_within(value, control) or is_within(control, value) for control in controls):
                raise RepositoryProfileError(f"{name} must not overlap Git common-dir or alternates")
            if is_within(root, value):
                raise RepositoryProfileError(f"{name} must not contain the target repository")
            object.__setattr__(self, name, str(value))
        roots = tuple(resolved_path(getattr(self, n)) for n in ("workspace_root", "state_root", "cache_root"))
        if any(is_within(left, right) or is_within(right, left) for index, left in enumerate(roots) for right in roots[index + 1:]): raise RepositoryProfileError("workspace/state/cache roots must be distinct and non-nested")
        if type(self.grants) is not tuple or len({g.capability for g in self.grants}) != len(self.grants): raise RepositoryProfileError("grants must have one immutable record per capability")
        if any(type(g) is not CapabilityGrant for g in self.grants): raise RepositoryProfileError("grants must be typed")
        if type(self.tools) is not tuple or len({t.adapter_id for t in self.tools}) != len(self.tools): raise RepositoryProfileError("tools must have unique admitted adapter IDs")
        if any(type(t) is not HostToolBinding for t in self.tools): raise RepositoryProfileError("tools must be typed")
        if type(self.reports) is not tuple or any(type(r) is not CapabilityReport for r in self.reports): raise RepositoryProfileError("reports must be typed")
        if {report.adapter_id for report in self.reports} != {tool.adapter_id for tool in self.tools}: raise RepositoryProfileError("reports must exactly cover tool bindings")
        if any(next(tool for tool in self.tools if tool.adapter_id == report.adapter_id).status is not report.status for report in self.reports): raise RepositoryProfileError("capability report contradicts tool binding")
        if type(self.external_destinations) is not tuple or self.external_destinations != tuple(sorted(set(self.external_destinations))): raise RepositoryProfileError("external_destinations must be sorted immutable")
        if any(type(v) is not str or not v.startswith("https://") or "?" in v or "#" in v for v in self.external_destinations): raise RepositoryProfileError("external destination is not admitted")
        if self.sensitivity not in {"unknown", "private", "public"}: raise RepositoryProfileError("sensitivity is unknown, private, or public")
        if type(self.generation) is not int or isinstance(self.generation, bool) or self.generation < 1: raise RepositoryProfileError("generation must be positive")
        sealed = self.to_document(include_digest=False); sealed.pop("registry_handle")
        expected = canonical_digest(sealed)
        if not self.profile_digest: object.__setattr__(self, "profile_digest", expected)
        elif self.profile_digest != expected: raise RepositoryProfileError("profile_digest does not seal profile fields")
        if type(self.registry_handle) is not str or not self.registry_handle.strip() or self.registry_handle != self.registry_handle.strip(): raise RepositoryProfileError("profile requires an opaque host registry handle")

    def to_document(self, *, include_digest: bool = True) -> dict[str, Any]:
        result = {"profile_id": self.profile_id, "identity": {"tenant_id":self.identity.tenant_id,"repository_id":self.identity.repository_id,"issuer_id":self.identity.issuer_id,"authority_digest":self.identity.authority_digest}, "repository_root":self.repository_root,"workspace_root":self.workspace_root,"state_root":self.state_root,"cache_root":self.cache_root,"grants":[{"capability":g.capability.value,"grant_id":g.grant_id,"grant_digest":g.grant_digest,"revoked":g.revoked} for g in self.grants], "tools":[{"adapter_id":t.adapter_id,"version":t.version,"executable_path":t.executable_path,"binary_digest":t.binary_digest,"platform":t.platform,"fixed_argv":list(t.fixed_argv),"placeholders":list(t.placeholders),"safe_environment_names":list(t.safe_environment_names),"secret_handles":list(t.secret_handles),"timeout_seconds":t.timeout_seconds,"status":t.status.value,"probe_receipt_digest":t.probe_receipt_digest,"host_receipt_witness":t.host_receipt_witness} for t in self.tools], "reports":[{"adapter_id":r.adapter_id,"status":r.status.value,"reason":r.reason,"receipt_digest":r.receipt_digest} for r in self.reports], "external_destinations":list(self.external_destinations),"sensitivity":self.sensitivity,"registry_handle":self.registry_handle,"generation":self.generation}
        if include_digest: result["profile_digest"] = self.profile_digest
        return result

    def allows(self, capability: ProfileCapability, *, destination: str | None = None) -> bool:
        capability = ProfileCapability(capability)
        if capability is ProfileCapability.READ_ONLY_PLAN: return True
        grant = next((g for g in self.grants if g.capability is capability), None)
        if grant is None or grant.revoked: return False
        if capability in {ProfileCapability.CODE_PR, ProfileCapability.LEARNING_EXPORT, ProfileCapability.DEPLOYMENT} and (destination is None or self.sensitivity == "unknown" or destination not in self.external_destinations): return False
        if destination is not None and (self.sensitivity == "unknown" or destination not in self.external_destinations): return False
        return True

    def projection(self) -> Mapping[str, Any]:
        from types import MappingProxyType
        return MappingProxyType({"profile_id": self.profile_id, "tenant_id": self.identity.tenant_id, "repository_id": self.identity.repository_id, "issuer_id": self.identity.issuer_id, "authority_digest": self.identity.authority_digest, "registry_handle": self.registry_handle, "profile_digest": self.profile_digest, "generation": self.generation, "capabilities": MappingProxyType({c.value: self.allows(c) for c in ProfileCapability})})

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "RepositoryProfile":
        fields = {"profile_id", "identity", "repository_root", "workspace_root", "state_root", "cache_root", "grants", "tools", "reports", "external_destinations", "sensitivity", "registry_handle", "generation", "profile_digest"}
        if not isinstance(document, Mapping) or set(document) != fields:
            raise RepositoryProfileError("repository profile has unknown or missing fields")
        identity = document["identity"]
        if not isinstance(identity, Mapping) or set(identity) != {"tenant_id", "repository_id", "issuer_id", "authority_digest"}:
            raise RepositoryProfileError("identity is not a closed host identity")
        try:
            return cls(
                document["profile_id"], HostIdentity(**identity), document["repository_root"], document["workspace_root"], document["state_root"], document["cache_root"],
                tuple(CapabilityGrant(**item) for item in document["grants"]),
                tuple(_binding_from_document(item) for item in document["tools"]),
                tuple(CapabilityReport(**item) for item in document["reports"]), tuple(document["external_destinations"]), document["sensitivity"], document["registry_handle"], document["generation"], document["profile_digest"])
        except (KeyError, TypeError, ValueError) as error:
            raise RepositoryProfileError("repository profile document is invalid") from error


def _binding_from_document(item: Any) -> HostToolBinding:
    fields = {"adapter_id", "version", "executable_path", "binary_digest", "platform", "fixed_argv", "placeholders", "safe_environment_names", "secret_handles", "timeout_seconds", "status", "probe_receipt_digest", "host_receipt_witness"}
    if not isinstance(item, Mapping) or set(item) != fields:
        raise RepositoryProfileError("tool binding has unknown or missing fields")
    return HostToolBinding(adapter_id=item["adapter_id"], version=item["version"], executable_path=item["executable_path"], binary_digest=item["binary_digest"], platform=item["platform"], fixed_argv=tuple(item["fixed_argv"]), placeholders=tuple(item["placeholders"]), safe_environment_names=tuple(item["safe_environment_names"]), secret_handles=tuple(item["secret_handles"]), timeout_seconds=item["timeout_seconds"], status=item["status"], probe_receipt_digest=item["probe_receipt_digest"], host_receipt_witness=item["host_receipt_witness"])


class HostProfileIssuer:
    """Pure assembler; host composition supplies the opaque persistent registry handle."""
    def issue(self, **values: Any) -> RepositoryProfile:
        if "registry_handle" not in values:
            raise RepositoryProfileError("host issuer must supply a registry handle")
        return RepositoryProfile(**values)


class RepositoryProfileStore:
    """Atomic host-side storage; the target repository is never a valid store."""
    def __init__(self, directory: str | Path, *, repository_root: str | Path, registry: HostProfileRegistry) -> None:
        if registry is None or not callable(getattr(registry, "verify_profile", None)): raise RepositoryProfileError("store requires injected host profile registry")
        self.registry = registry
        try:
            self.directory = require_external_path(directory, repository_root, label="profile store")
        except ExternalPathRequired as error:
            raise RepositoryProfileError(str(error)) from error
        self.directory.mkdir(parents=True, exist_ok=True)
    def write(self, profile: RepositoryProfile) -> Path:
        if type(profile) is not RepositoryProfile:
            raise RepositoryProfileError("profile store requires an exact issued RepositoryProfile")
        if not self.registry.verify_profile(registry_handle=profile.registry_handle, profile_digest=profile.profile_digest, tenant_id=profile.identity.tenant_id, repository_id=profile.identity.repository_id, authority_digest=profile.identity.authority_digest, generation=profile.generation): raise RepositoryProfileError("host registry did not authenticate profile")
        if is_within(self.directory, profile.repository_root): raise RepositoryProfileError("profile store overlaps target repository")
        target = self.directory / f"{profile.profile_id}.{profile.profile_digest[7:]}.json"
        pointer = self.directory / f"{profile.profile_id}.active.json"
        data = json.dumps(profile.to_document(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        lock_path = self.directory / ".profile-cas.lock"
        with _STORE_LOCK:
            try:
                lock_path.mkdir()
            except FileExistsError as error:
                raise RepositoryProfileError("profile activation is concurrently locked; retry from host") from error
            try:
                for active in self.directory.glob("*.active.json"):
                    if active.is_symlink() or active.stat().st_nlink != 1:
                        raise RepositoryProfileError("active profile pointer must not be linked or redirected")
                    other_id = active.name.removesuffix(".active.json")
                    if other_id != profile.profile_id:
                        other = self.load(other_id)
                        if other.repository_root == profile.repository_root and (other.identity.tenant_id, other.identity.repository_id) != (profile.identity.tenant_id, profile.identity.repository_id):
                            raise RepositoryProfileError("physical repository root is already bound to another tenant or repository")
                if pointer.exists():
                    current = self.read_document(profile.profile_id)
                    old = RepositoryProfile.from_document(current)
                    if (old.identity.tenant_id, old.identity.repository_id, old.repository_root) != (profile.identity.tenant_id, profile.identity.repository_id, profile.repository_root):
                        raise RepositoryProfileError("profile id is already bound to another tenant, repository, or root")
                    if profile.generation <= old.generation:
                        raise RepositoryProfileError("profile generation must advance monotonically")
                fd, name = tempfile.mkstemp(prefix=".profile-", suffix=".tmp", dir=self.directory)
                try:
                    with os.fdopen(fd, "wb") as stream: stream.write(data); stream.flush(); os.fsync(stream.fileno())
                    os.replace(name, target)
                    pointer_data = json.dumps({"profile_id":profile.profile_id,"profile_digest":profile.profile_digest,"generation":profile.generation}, sort_keys=True, separators=(",", ":")).encode("utf-8")
                    pfd, pname = tempfile.mkstemp(prefix=".pointer-", suffix=".tmp", dir=self.directory)
                    try:
                        with os.fdopen(pfd, "wb") as stream: stream.write(pointer_data); stream.flush(); os.fsync(stream.fileno())
                        os.replace(pname, pointer)
                    finally:
                        if os.path.exists(pname): os.unlink(pname)
                finally:
                    if os.path.exists(name): os.unlink(name)
            finally:
                try: lock_path.rmdir()
                except OSError: pass
        return target
    def read_document(self, profile_id: str) -> dict[str, Any]:
        _id(profile_id, "profile_id")
        pointer_path = self.directory / f"{profile_id}.active.json"
        if pointer_path.is_symlink() or pointer_path.stat().st_nlink != 1:
            raise RepositoryProfileError("active profile pointer must not be linked or redirected")
        pointer = strict_json_object(pointer_path.read_bytes())
        if set(pointer) != {"profile_id", "profile_digest", "generation"} or pointer["profile_id"] != profile_id:
            raise RepositoryProfileError("active profile pointer is invalid")
        _digest(pointer["profile_digest"], "pointer profile_digest")
        path = self.directory / f"{profile_id}.{pointer['profile_digest'][7:]}.json"
        if path.is_symlink() or path.stat().st_nlink != 1:
            raise RepositoryProfileError("profile record must not be linked or redirected")
        return strict_json_object(path.read_bytes())
    def load(self, profile_id: str) -> RepositoryProfile:
        profile = RepositoryProfile.from_document(self.read_document(profile_id))
        if not self.registry.verify_profile(registry_handle=profile.registry_handle, profile_digest=profile.profile_digest, tenant_id=profile.identity.tenant_id, repository_id=profile.identity.repository_id, authority_digest=profile.identity.authority_digest, generation=profile.generation): raise RepositoryProfileError("stored profile is not current in host registry")
        return profile


class ProfileEffectAuthorizer:
    """The required just-before-effect check for a worker projection."""
    def require(self, projection: Mapping[str, Any], *, store: RepositoryProfileStore, authority: AuthorityRegistry, capability: ProfileCapability, destination: str | None = None) -> RepositoryProfile:
        if not isinstance(projection, Mapping): raise RepositoryProfileError("effect requires an authenticated profile projection")
        required = {"profile_id", "tenant_id", "repository_id", "issuer_id", "authority_digest", "registry_handle", "profile_digest", "generation", "capabilities"}
        if set(projection) != required: raise RepositoryProfileError("projection is incomplete or substituted")
        profile_id = projection.get("profile_id"); digest = projection.get("profile_digest"); generation = projection.get("generation")
        if type(profile_id) is not str or type(digest) is not str or type(generation) is not int: raise RepositoryProfileError("projection is incomplete")
        current = store.load(profile_id)
        if current.profile_digest != digest or current.generation != generation: raise RepositoryProfileError("projection is stale or substituted")
        if projection != current.projection(): raise RepositoryProfileError("projection does not bind current host profile")
        try: authority.envelope(current.identity.authority_digest)
        except AuthorityDenied as error: raise RepositoryProfileError("profile authority is revoked") from error
        verifier = getattr(store.registry, "authorize_capability", None)
        if not callable(verifier) or not verifier(registry_handle=current.registry_handle, profile_digest=current.profile_digest, generation=current.generation, capability=ProfileCapability(capability).value, destination=destination):
            raise RepositoryProfileError("host registry denied capability, version, or revocation state")
        if not current.allows(capability, destination=destination): raise RepositoryProfileError("capability is absent, revoked, or route-denied")
        return current


__all__ = ["CapabilityGrant", "CapabilityReport", "CapabilityStatus", "HostIdentity", "HostProfileIssuer", "HostToolBinding", "ProfileCapability", "ProfileEffectAuthorizer", "RepositoryProfile", "RepositoryProfileError", "RepositoryProfileStore", "undiscovered_capability_report"]
