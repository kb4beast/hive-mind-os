"""Static Roblox/Rojo profile discovery; no runtime claim (N26)."""

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath

from .brain_kernel.canonical import canonical_digest, canonical_document


class ProfileStatus(StrEnum):
    PROFILE_VALID = "PROFILE_VALID"
    BLOCKED_TOOLCHAIN = "BLOCKED_TOOLCHAIN"
    BLOCKED_SOURCE = "BLOCKED_SOURCE"
    STATIC_VALIDATED = "STATIC_VALIDATED"


@dataclass(frozen=True, slots=True)
class RobloxProfile:
    profile_id: str
    profile_selection_receipt_digest: str
    source_refs: tuple[str, ...]
    toolchain_versions: dict[str, str]
    executable_paths: dict[str, str]
    executable_digests: dict[str, str]
    image_digest: str
    project_manifest_paths: tuple[str, ...]
    source_roots: tuple[str, ...]
    package_lock_digests: tuple[str, ...]
    build_commands: tuple[tuple[str, ...], ...]
    static_check_commands: tuple[tuple[str, ...], ...]
    artifact_paths: tuple[str, ...]
    asset_manifest_digest: str
    runtime_requirements: dict[str, object]
    capability_status: ProfileStatus

    def __post_init__(self):
        if not isinstance(self.capability_status, ProfileStatus):
            object.__setattr__(
                self, "capability_status", ProfileStatus(self.capability_status)
            )
        if any(
            type(x) is not str or not x.strip()
            for x in (
                self.profile_id,
                self.profile_selection_receipt_digest,
                self.image_digest,
                self.asset_manifest_digest,
            )
        ):
            raise ValueError("profile identity is required")
        if not self.project_manifest_paths or not self.source_roots:
            raise ValueError("project manifests and source roots are required")
        digest_fields = (
            self.profile_selection_receipt_digest,
            self.image_digest,
            self.asset_manifest_digest,
            *self.executable_digests.values(),
            *self.package_lock_digests,
        )
        if any(
            re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
            for value in digest_fields
        ):
            raise ValueError("profile digests must be canonical sha256 values")
        for path in (
            *self.project_manifest_paths,
            *self.source_roots,
            *self.artifact_paths,
        ):
            normalized = PurePosixPath(path).as_posix()
            if not path or normalized.startswith("/") or ".." in normalized.split("/"):
                raise ValueError("profile paths must be bounded relative paths")
        if (
            self.capability_status is ProfileStatus.STATIC_VALIDATED
            and (
                not self.source_refs
                or not self.toolchain_versions
                or set(self.toolchain_versions) != set(self.executable_paths)
                or set(self.toolchain_versions) != set(self.executable_digests)
                or not self.package_lock_digests
                or not self.build_commands
                or not self.static_check_commands
                or not self.artifact_paths
                or not self.runtime_requirements
                or not self.runtime_requirements.get("asset_rights_refs")
            )
        ):
            raise ValueError("static validation requires complete sealed profile evidence")
        admitted_executables = set(self.executable_paths.values())
        for command in (*self.build_commands, *self.static_check_commands):
            if (
                not command
                or any(type(arg) is not str or not arg for arg in command)
                or command[0] not in admitted_executables
            ):
                raise ValueError("commands must use an admitted executable argv")

    @property
    def digest(self):
        return canonical_digest(self)

    def to_dict(self):
        return canonical_document(self)

    @classmethod
    def from_dict(cls, value):
        required = set(cls.__dataclass_fields__)
        if set(value) != required:
            raise ValueError("closed Roblox profile schema")
        return cls(
            **{
                **value,
                "capability_status": ProfileStatus(value["capability_status"]),
                "source_refs": tuple(value["source_refs"]),
                "project_manifest_paths": tuple(value["project_manifest_paths"]),
                "source_roots": tuple(value["source_roots"]),
                "package_lock_digests": tuple(value["package_lock_digests"]),
                "build_commands": tuple(tuple(x) for x in value["build_commands"]),
                "static_check_commands": tuple(
                    tuple(x) for x in value["static_check_commands"]
                ),
                "artifact_paths": tuple(value["artifact_paths"]),
            }
        )
