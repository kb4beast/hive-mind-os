from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Any

from ...receipts import portable_path_parts

_IDENTIFIER = re.compile(r"[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?\Z")
_SEMVER = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?\Z"
)
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_ROLE_BINDINGS = frozenset(
    {
        "orchestrator",
        "explorer",
        "architect",
        "builder",
        "curator",
        "integrator",
        "steward",
        "optimizer",
    }
)


def _require_identifier(value: str, label: str) -> None:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase portable identifier")


def _require_nonempty(value: str, label: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} cannot be empty")


def _require_unique(values: tuple[str, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} cannot contain duplicates")
    if any(not value.strip() for value in values):
        raise ValueError(f"{label} cannot contain empty values")


def _require_path(value: str, label: str) -> None:
    try:
        portable_path_parts(value)
    except ValueError as error:
        raise ValueError(f"{label} must be a portable relative path") from error


def _require_digest(value: str, label: str) -> None:
    if not _DIGEST.fullmatch(value):
        raise ValueError(f"{label} must be lowercase sha256:<64 hex>")


def _require_version(value: str) -> None:
    if not _SEMVER.fullmatch(value):
        raise ValueError("version must be an exact semantic version")


def canonical_json_bytes(document: Any) -> bytes:
    """Return the single canonical byte representation used for package digests."""

    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def content_digest(content: bytes) -> str:
    return f"sha256:{sha256(content).hexdigest()}"


class ComponentKind(StrEnum):
    AGENT = "agent"
    SKILL = "skill"
    TOOL = "tool"
    WORKFLOW = "workflow"


class LicenseStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    INCOMPATIBLE = "incompatible"


class TrustState(StrEnum):
    QUARANTINED = "quarantined"
    TRUSTED = "trusted"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class FileRecord:
    path: str
    digest: str
    media_type: str

    def __post_init__(self) -> None:
        _require_path(self.path, "file path")
        _require_digest(self.digest, "file digest")
        if self.media_type != "application/json":
            raise ValueError("v1 packages permit only application/json files")

    def to_contract(self) -> dict[str, str]:
        return {
            "path": self.path,
            "digest": self.digest,
            "media_type": self.media_type,
        }


@dataclass(frozen=True, slots=True)
class ComponentRef:
    component_id: str
    kind: ComponentKind
    manifest_path: str

    def __post_init__(self) -> None:
        _require_identifier(self.component_id, "component_id")
        _require_path(self.manifest_path, "component manifest_path")

    def to_contract(self) -> dict[str, str]:
        return {
            "component_id": self.component_id,
            "kind": self.kind.value,
            "manifest_path": self.manifest_path,
        }


@dataclass(frozen=True, slots=True)
class PackagePin:
    package_id: str
    version: str
    manifest_digest: str

    def __post_init__(self) -> None:
        _require_identifier(self.package_id, "package_id")
        _require_version(self.version)
        _require_digest(self.manifest_digest, "manifest_digest")

    def to_contract(self) -> dict[str, str]:
        return {
            "package_id": self.package_id,
            "version": self.version,
            "manifest_digest": self.manifest_digest,
        }


@dataclass(frozen=True, slots=True)
class PackageManifest:
    schema_version: int
    package_id: str
    version: str
    license: str
    license_status: LicenseStatus
    trust_state: TrustState
    source_refs: tuple[str, ...]
    court_case_refs: tuple[str, ...]
    components: tuple[ComponentRef, ...]
    files: tuple[FileRecord, ...]
    requires: tuple[PackagePin, ...]
    replaces: tuple[PackagePin, ...]
    rollback_to: PackagePin | None

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported package schema_version")
        _require_identifier(self.package_id, "package_id")
        _require_version(self.version)
        _require_nonempty(self.license, "license")
        _require_unique(self.source_refs, "source_refs")
        _require_unique(self.court_case_refs, "court_case_refs")
        if not self.source_refs:
            raise ValueError("source_refs must preserve at least one source")
        if not self.court_case_refs:
            raise ValueError("court_case_refs must preserve at least one court case")
        if (
            self.license_status is not LicenseStatus.VERIFIED
            and self.trust_state is TrustState.TRUSTED
        ):
            raise ValueError(
                "a package with an unverified or incompatible license must remain "
                "quarantined or revoked"
            )
        component_ids = tuple(item.component_id for item in self.components)
        component_paths = tuple(item.manifest_path for item in self.components)
        file_paths = tuple(item.path for item in self.files)
        dependency_ids = tuple(item.package_id for item in self.requires)
        replaced_ids = tuple(item.package_id for item in self.replaces)
        _require_unique(component_ids, "component ids")
        _require_unique(component_paths, "component paths")
        _require_unique(file_paths, "file paths")
        _require_unique(dependency_ids, "dependency package ids")
        _require_unique(replaced_ids, "replaced package ids")
        if not self.components:
            raise ValueError("package must declare at least one component")
        listed_paths = set(file_paths)
        missing = sorted(set(component_paths) - listed_paths)
        if missing:
            raise ValueError(
                "component manifests must be listed in files: " + ", ".join(missing)
            )
        for pin in (*self.requires, *self.replaces):
            if pin.package_id == self.package_id and pin.version == self.version:
                raise ValueError("package cannot require or replace itself")
        if (
            self.rollback_to is not None
            and self.rollback_to.package_id != self.package_id
        ):
            raise ValueError("rollback_to must refer to the same package_id")

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "package_id": self.package_id,
            "version": self.version,
            "license": self.license,
            "license_status": self.license_status.value,
            "trust_state": self.trust_state.value,
            "source_refs": list(self.source_refs),
            "court_case_refs": list(self.court_case_refs),
            "components": [item.to_contract() for item in self.components],
            "files": [item.to_contract() for item in self.files],
            "requires": [item.to_contract() for item in self.requires],
            "replaces": [item.to_contract() for item in self.replaces],
            "rollback_to": (
                None if self.rollback_to is None else self.rollback_to.to_contract()
            ),
        }


@dataclass(frozen=True, slots=True)
class AgentManifest:
    component_id: str
    role_binding: str
    mission: str
    required_outputs: tuple[str, ...]
    requested_capabilities: tuple[str, ...]
    quality_gates: tuple[str, ...]
    prompt_path: str
    skill_ids: tuple[str, ...]
    tool_ids: tuple[str, ...]

    kind = ComponentKind.AGENT

    def __post_init__(self) -> None:
        _require_identifier(self.component_id, "component_id")
        if self.role_binding not in _ROLE_BINDINGS:
            raise ValueError("role_binding is not a constitutional role")
        _require_nonempty(self.mission, "mission")
        _require_unique(self.required_outputs, "required_outputs")
        _require_unique(self.requested_capabilities, "requested_capabilities")
        _require_unique(self.quality_gates, "quality_gates")
        _require_path(self.prompt_path, "prompt_path")
        _require_unique(self.skill_ids, "skill_ids")
        _require_unique(self.tool_ids, "tool_ids")
        for component_id in (*self.skill_ids, *self.tool_ids):
            _require_identifier(component_id, "bound component id")

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "component_id": self.component_id,
            "role_binding": self.role_binding,
            "mission": self.mission,
            "required_outputs": list(self.required_outputs),
            "requested_capabilities": list(self.requested_capabilities),
            "quality_gates": list(self.quality_gates),
            "prompt_path": self.prompt_path,
            "skill_ids": list(self.skill_ids),
            "tool_ids": list(self.tool_ids),
        }


@dataclass(frozen=True, slots=True)
class SkillManifest:
    component_id: str
    name: str
    description: str
    instruction_path: str
    requested_capabilities: tuple[str, ...]
    reference_paths: tuple[str, ...]
    test_refs: tuple[str, ...]

    kind = ComponentKind.SKILL

    def __post_init__(self) -> None:
        _require_identifier(self.component_id, "component_id")
        _require_nonempty(self.name, "name")
        _require_nonempty(self.description, "description")
        _require_path(self.instruction_path, "instruction_path")
        _require_unique(self.requested_capabilities, "requested_capabilities")
        _require_unique(self.reference_paths, "reference_paths")
        _require_unique(self.test_refs, "test_refs")
        for path in self.reference_paths:
            _require_path(path, "reference path")

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "component_id": self.component_id,
            "name": self.name,
            "description": self.description,
            "instruction_path": self.instruction_path,
            "requested_capabilities": list(self.requested_capabilities),
            "reference_paths": list(self.reference_paths),
            "test_refs": list(self.test_refs),
        }


@dataclass(frozen=True, slots=True)
class ToolManifest:
    component_id: str
    capability_id: str
    input_schema_ref: str
    output_schema_ref: str
    side_effecting: bool
    idempotency_required: bool
    rollback_required: bool

    kind = ComponentKind.TOOL

    def __post_init__(self) -> None:
        _require_identifier(self.component_id, "component_id")
        _require_identifier(self.capability_id, "capability_id")
        _require_path(self.input_schema_ref, "input_schema_ref")
        _require_path(self.output_schema_ref, "output_schema_ref")
        if not self.side_effecting and (
            self.idempotency_required or self.rollback_required
        ):
            raise ValueError(
                "read-only tools cannot require idempotency or rollback handling"
            )
        if self.side_effecting and not self.idempotency_required:
            raise ValueError("side-effecting tools must require idempotency")

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "component_id": self.component_id,
            "capability_id": self.capability_id,
            "input_schema_ref": self.input_schema_ref,
            "output_schema_ref": self.output_schema_ref,
            "side_effecting": self.side_effecting,
            "idempotency_required": self.idempotency_required,
            "rollback_required": self.rollback_required,
        }


@dataclass(frozen=True, slots=True)
class WorkflowTransition:
    from_state: str
    to_state: str
    event: str
    allowed_role_bindings: tuple[str, ...]
    required_evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        for value, label in (
            (self.from_state, "from_state"),
            (self.to_state, "to_state"),
            (self.event, "event"),
        ):
            _require_identifier(value, label)
        _require_unique(self.allowed_role_bindings, "allowed_role_bindings")
        unknown = set(self.allowed_role_bindings) - _ROLE_BINDINGS
        if unknown:
            raise ValueError("workflow contains unknown role bindings")
        _require_unique(self.required_evidence, "required_evidence")
        if not self.allowed_role_bindings:
            raise ValueError("workflow transition requires an allowed role binding")
        if not self.required_evidence:
            raise ValueError("workflow transition requires evidence")

    def to_contract(self) -> dict[str, Any]:
        return {
            "from_state": self.from_state,
            "to_state": self.to_state,
            "event": self.event,
            "allowed_role_bindings": list(self.allowed_role_bindings),
            "required_evidence": list(self.required_evidence),
        }


@dataclass(frozen=True, slots=True)
class WorkflowManifest:
    component_id: str
    initial_state: str
    terminal_states: tuple[str, ...]
    transitions: tuple[WorkflowTransition, ...]

    kind = ComponentKind.WORKFLOW

    def __post_init__(self) -> None:
        _require_identifier(self.component_id, "component_id")
        _require_identifier(self.initial_state, "initial_state")
        _require_unique(self.terminal_states, "terminal_states")
        if not self.terminal_states:
            raise ValueError("workflow requires at least one terminal state")
        state_names = {self.initial_state, *self.terminal_states}
        identities: set[tuple[str, str]] = set()
        for transition in self.transitions:
            state_names.update((transition.from_state, transition.to_state))
            identity = (transition.from_state, transition.event)
            if identity in identities:
                raise ValueError(
                    "workflow transitions must be deterministic by state and event"
                )
            identities.add(identity)
        if self.initial_state in self.terminal_states:
            raise ValueError("initial_state cannot be terminal")
        reachable = {self.initial_state}
        changed = True
        while changed:
            changed = False
            for transition in self.transitions:
                if (
                    transition.from_state in reachable
                    and transition.to_state not in reachable
                ):
                    reachable.add(transition.to_state)
                    changed = True
        unreachable = state_names - reachable
        if unreachable:
            raise ValueError(
                "workflow contains unreachable states: " + ", ".join(sorted(unreachable))
            )
        missing_terminal = set(self.terminal_states) - reachable
        if missing_terminal:
            raise ValueError(
                "workflow terminal states are unreachable: "
                + ", ".join(sorted(missing_terminal))
            )

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "component_id": self.component_id,
            "initial_state": self.initial_state,
            "terminal_states": list(self.terminal_states),
            "transitions": [item.to_contract() for item in self.transitions],
        }


ComponentManifest = AgentManifest | SkillManifest | ToolManifest | WorkflowManifest


@dataclass(frozen=True, slots=True)
class LoadedPackage:
    manifest: PackageManifest
    manifest_digest: str
    root: Path
    components: tuple[ComponentManifest, ...]

    def __post_init__(self) -> None:
        _require_digest(self.manifest_digest, "manifest_digest")
        if not self.root.is_absolute():
            raise ValueError("loaded package root must be absolute")
        declared = {item.component_id for item in self.manifest.components}
        loaded = {item.component_id for item in self.components}
        if declared != loaded:
            raise ValueError("loaded components do not match declared components")


@dataclass(frozen=True, slots=True)
class CatalogSnapshot:
    packages: tuple[PackagePin, ...]
    fingerprint: str

    def __post_init__(self) -> None:
        _require_digest(self.fingerprint, "catalog fingerprint")


__all__ = [
    "AgentManifest",
    "CatalogSnapshot",
    "ComponentKind",
    "ComponentManifest",
    "ComponentRef",
    "FileRecord",
    "LoadedPackage",
    "LicenseStatus",
    "PackageManifest",
    "PackagePin",
    "SkillManifest",
    "ToolManifest",
    "TrustState",
    "WorkflowManifest",
    "WorkflowTransition",
    "canonical_json_bytes",
    "content_digest",
]
