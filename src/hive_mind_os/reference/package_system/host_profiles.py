from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable

from .models import canonical_json_bytes, content_digest

_MAX_PROFILE_BYTES = 4 * 1024 * 1024


class HostCapability(StrEnum):
    PACKAGE_DISCOVERY = "package_discovery"
    INSTRUCTION_PROJECTION = "instruction_projection"
    SKILL_MD = "skill_md"
    CUSTOM_AGENTS = "custom_agents"
    AGENT_TOOL_RESTRICTION = "agent_tool_restriction"
    MCP_CLIENT = "mcp_client"
    LIFECYCLE_HOOKS = "lifecycle_hooks"
    WORKTREE_ISOLATION = "worktree_isolation"
    BACKGROUND_AGENTS = "background_agents"
    RESUME = "resume"
    STRUCTURED_OUTPUT = "structured_output"
    EVENT_STREAM = "event_stream"
    CANCELLATION = "cancellation"
    RECEIPTS = "receipts"


class EvidenceLevel(StrEnum):
    DECLARED = "declared"
    DOCUMENTED = "documented"
    TESTED = "tested"


class ConformanceStatus(StrEnum):
    UNVERIFIED = "unverified"
    FAILED = "failed"
    PASSED = "passed"


@dataclass(frozen=True, slots=True)
class HostCapabilityProfile:
    host_id: str
    host_version_ref: str
    adapter_version: str
    evidence_level: EvidenceLevel
    conformance_status: ConformanceStatus
    capabilities: frozenset[HostCapability]
    evidence_refs: tuple[str, ...]
    evidence_obligations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.host_id.strip():
            raise ValueError("host_id cannot be empty")
        if not self.host_version_ref.strip():
            raise ValueError("host_version_ref requires a nonempty evidence snapshot reference")
        if not self.adapter_version.strip():
            raise ValueError("adapter_version cannot be empty")
        if not self.evidence_refs:
            raise ValueError("host capability profile requires evidence")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("evidence_refs cannot contain duplicates")
        if any(not item.strip() for item in self.evidence_refs):
            raise ValueError("evidence_refs cannot contain empty values")
        if len(self.evidence_obligations) != len(set(self.evidence_obligations)):
            raise ValueError("evidence_obligations cannot contain duplicates")
        if any(not item.strip() for item in self.evidence_obligations):
            raise ValueError("evidence_obligations cannot contain empty values")
        if (
            self.conformance_status is ConformanceStatus.PASSED
            and self.evidence_level is not EvidenceLevel.TESTED
        ):
            raise ValueError("passed conformance requires tested evidence")
        if (
            self.conformance_status is ConformanceStatus.PASSED
            and self.evidence_obligations
        ):
            raise ValueError("passed conformance cannot retain evidence obligations")

    def missing(
        self, required: frozenset[HostCapability]
    ) -> frozenset[HostCapability]:
        return required - self.capabilities

    def supports(
        self,
        required: frozenset[HostCapability],
        *,
        conformance_verifier: Callable[[HostCapabilityProfile], bool] | None = None,
    ) -> bool:
        return (
            self.conformance_status is ConformanceStatus.PASSED
            and not self.missing(required)
            and conformance_verifier is not None
            and conformance_verifier(self) is True
        )

    def declares(self, required: frozenset[HostCapability]) -> bool:
        """Report profile contents without making a runtime-support claim."""

        return not self.missing(required)

    @property
    def fingerprint(self) -> str:
        return content_digest(canonical_json_bytes(self.to_contract()))

    def to_contract(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "host_id": self.host_id,
            "host_version_ref": self.host_version_ref,
            "adapter_version": self.adapter_version,
            "evidence_level": self.evidence_level.value,
            "conformance_status": self.conformance_status.value,
            "capabilities": sorted(item.value for item in self.capabilities),
            "evidence_refs": list(self.evidence_refs),
            "evidence_obligations": list(self.evidence_obligations),
        }

    @classmethod
    def from_contract(cls, document: object) -> HostCapabilityProfile:
        if not isinstance(document, dict):
            raise ValueError("host capability profile must be an object")
        expected = {
            "schema_version",
            "host_id",
            "host_version_ref",
            "adapter_version",
            "evidence_level",
            "conformance_status",
            "capabilities",
            "evidence_refs",
            "evidence_obligations",
        }
        missing = expected - document.keys()
        unknown = document.keys() - expected
        if missing:
            raise ValueError(
                "host capability profile missing fields: "
                + ", ".join(sorted(missing))
            )
        if unknown:
            raise ValueError(
                "host capability profile unknown fields: "
                + ", ".join(sorted(unknown))
            )
        if document["schema_version"] != 1 or type(document["schema_version"]) is not int:
            raise ValueError("unsupported host capability profile schema_version")
        capabilities = document["capabilities"]
        evidence_refs = document["evidence_refs"]
        evidence_obligations = document["evidence_obligations"]
        if not isinstance(capabilities, list) or any(
            not isinstance(item, str) for item in capabilities
        ):
            raise ValueError("capabilities must be an array of strings")
        if len(capabilities) != len(set(capabilities)):
            raise ValueError("capabilities cannot contain duplicates")
        if not isinstance(evidence_refs, list) or any(
            not isinstance(item, str) for item in evidence_refs
        ):
            raise ValueError("evidence_refs must be an array of strings")
        if not isinstance(evidence_obligations, list) or any(
            not isinstance(item, str) for item in evidence_obligations
        ):
            raise ValueError("evidence_obligations must be an array of strings")
        for field in ("host_id", "host_version_ref", "adapter_version"):
            if not isinstance(document[field], str):
                raise ValueError(f"{field} must be a string")
        try:
            return cls(
                host_id=document["host_id"],
                host_version_ref=document["host_version_ref"],
                adapter_version=document["adapter_version"],
                evidence_level=EvidenceLevel(document["evidence_level"]),
                conformance_status=ConformanceStatus(
                    document["conformance_status"]
                ),
                capabilities=frozenset(HostCapability(item) for item in capabilities),
                evidence_refs=tuple(evidence_refs),
                evidence_obligations=tuple(evidence_obligations),
            )
        except (TypeError, ValueError) as error:
            raise ValueError(f"invalid host capability profile: {error}") from error


def _strict_json(path: Path) -> tuple[dict[str, Any], bytes]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        content = path.read_bytes()
        if len(content) > _MAX_PROFILE_BYTES:
            raise ValueError("host profile exceeds the JSON size limit")
        text = content.decode("utf-8")
        document = json.loads(
            text,
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number: {value}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"host profile is unreadable: {type(error).__name__}") from error
    if not isinstance(document, dict):
        raise ValueError("host profile must contain an object")
    return document, content


def load_builtin_host_profile(host_id: str) -> HostCapabilityProfile:
    from .builtins import hive_core_catalog, hive_core_root

    allowed = {"codex", "claude-code", "hermes"}
    if host_id not in allowed:
        raise KeyError(f"unknown built-in host profile: {host_id}")
    catalog = hive_core_catalog()
    package = catalog.package("hive-core")
    relative = f"host_profiles/{host_id}.json"
    records = tuple(
        record for record in package.manifest.files if record.path == relative
    )
    if not records:
        raise ValueError("built-in host profile is absent from package inventory")
    document, content = _strict_json(hive_core_root() / relative)
    if content_digest(content) != records[0].digest:
        raise ValueError("built-in host profile digest changed after validation")
    profile = HostCapabilityProfile.from_contract(document)
    if profile.host_id != host_id:
        raise ValueError("built-in host profile id does not match its resource")
    return profile


def load_builtin_host_profiles() -> tuple[HostCapabilityProfile, ...]:
    return tuple(
        load_builtin_host_profile(host_id)
        for host_id in ("codex", "claude-code", "hermes")
    )


__all__ = [
    "ConformanceStatus",
    "EvidenceLevel",
    "HostCapability",
    "HostCapabilityProfile",
    "load_builtin_host_profile",
    "load_builtin_host_profiles",
]
