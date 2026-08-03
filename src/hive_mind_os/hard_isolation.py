"""Fail-closed hard-isolation gateway contracts.

The existing :mod:`hive_mind_os.sandbox` runner is deliberately a process-tier
control.  This module does not treat it, a local SHA-256 digest, or a detected
container executable as hostile-code isolation.  It provides the narrow
replaceable boundary that a separately authorized OCI, Hyper-V, or VM adapter
must satisfy before a hostile workload may run.

No adapter in this module reads or passes raw provider, Git, or delivery
credentials to a guest.  A production adapter must use an independently
privileged credential broker and a host-owned receipt collector.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from enum import StrEnum
from ipaddress import ip_address
from pathlib import Path
from typing import Any, Mapping, Protocol
from uuid import uuid4

from .contracts import tool_intent_digest, validate_contract
from .custody import CustodyError, Ed25519CustodyVerifier
from .receipts import portable_path_parts, sha256_digest

_DIGEST_PREFIX = "sha256:"
_RECEIPT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_HOSTNAME = re.compile(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?\Z")
_EXECUTION_ID = re.compile(r"HIEXEC-[0-9a-f]{64}\Z")
_SENSITIVE_ARG = re.compile(
    r"(?:api[-_]?key|authorization|bearer|credential|password|secret|token)", re.IGNORECASE
)
HARD_ISOLATION_AUDIENCE = "hive-mind-os/hard-isolation/v1"
_HARD_ISOLATION_CAPABILITY_DOMAIN = b"hive-mind-os/hard-isolation-capability/v1\0"


class HardIsolationError(RuntimeError):
    """Base error for the hard-isolation boundary."""


class HardIsolationUnavailable(HardIsolationError):
    """A hostile workload has no verified, authorized hard-isolation runtime."""


class HardIsolationRejected(HardIsolationError):
    """A profile, intent, or returned host observation failed closed."""


class IsolationRuntime(StrEnum):
    OCI = "oci-container"
    HYPERV = "hyperv-container"
    EPHEMERAL_VM = "ephemeral-vm"


class IsolationOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DENIED = "denied"
    TIMEOUT = "timeout"


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _require_digest(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != len(_DIGEST_PREFIX) + 64
        or not value.startswith(_DIGEST_PREFIX)
        or any(character not in "0123456789abcdef" for character in value[len(_DIGEST_PREFIX) :])
    ):
        raise ValueError(f"{label} must be a lowercase sha256 digest")


def _require_identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError(f"{label} is required")


@dataclass(frozen=True, slots=True)
class NetworkGrant:
    """An explicit guest egress grant; the default empty set is deny-all."""

    protocol: str
    destination: str
    port: int
    dns_pin_digest: str

    def __post_init__(self) -> None:
        if self.protocol not in {"tcp", "udp"}:
            raise ValueError("network protocol must be tcp or udp")
        destination = self.destination.casefold()
        if not _HOSTNAME.fullmatch(destination) or "." not in destination:
            raise ValueError("network destination must be a public DNS hostname")
        try:
            parsed = ip_address(destination)
        except ValueError:
            parsed = None
        if parsed is not None:
            raise ValueError("network destination must not be an IP address")
        if (
            destination in {"metadata.google.internal", "metadata.azure.com"}
            or destination.startswith("metadata.")
            or ".metadata." in destination
        ):
            raise ValueError("metadata services are never guest network destinations")
        if not 1 <= self.port <= 65535:
            raise ValueError("network port is out of range")
        _require_digest(self.dns_pin_digest, "DNS pin digest")
        object.__setattr__(self, "destination", destination)

    def to_contract(self) -> dict[str, object]:
        return {
            "protocol": self.protocol,
            "destination": self.destination,
            "port": self.port,
            "dns_pin_digest": self.dns_pin_digest,
        }


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    cpu_millis: int
    memory_bytes: int
    process_count: int
    disk_bytes: int
    output_bytes: int
    wall_time_seconds: int
    file_count: int = 10_000

    def __post_init__(self) -> None:
        for label, value in (
            ("cpu_millis", self.cpu_millis),
            ("memory_bytes", self.memory_bytes),
            ("process_count", self.process_count),
            ("disk_bytes", self.disk_bytes),
            ("output_bytes", self.output_bytes),
            ("wall_time_seconds", self.wall_time_seconds),
            ("file_count", self.file_count),
        ):
            if type(value) is not int or value < 1:
                raise ValueError(f"{label} must be a positive integer")

    def to_contract(self) -> dict[str, int]:
        return {
            "cpu_millis": self.cpu_millis,
            "memory_bytes": self.memory_bytes,
            "process_count": self.process_count,
            "disk_bytes": self.disk_bytes,
            "output_bytes": self.output_bytes,
            "wall_time_seconds": self.wall_time_seconds,
            "file_count": self.file_count,
        }


@dataclass(frozen=True, slots=True)
class HardIsolationProfile:
    """Sealed, credential-free guest policy for a hostile workload."""

    profile_id: str
    runtime: IsolationRuntime
    runtime_digest: str
    image_digest: str
    guest_executable_digest: str
    guest_executable_path: str
    source_snapshot_digest: str
    source_mount: str
    writable_overlay: str
    limits: ResourceLimits
    controller_identity: str
    credential_broker_identity: str
    rootfs_read_only: bool = True
    source_read_only: bool = True
    host_home_mounted: bool = False
    host_evidence_mounted: bool = False
    host_socket_mounted: bool = False
    host_devices_mounted: bool = False
    no_new_privileges: bool = True
    egress_enforcement: str = "deny-all"
    egress_proxy_identity: str | None = None
    egress_proxy_digest: str | None = None
    network_grants: tuple[NetworkGrant, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_identifier(self.profile_id, "profile id")
        _require_digest(self.runtime_digest, "runtime digest")
        _require_digest(self.image_digest, "image digest")
        _require_digest(self.guest_executable_digest, "guest executable digest")
        _require_digest(self.source_snapshot_digest, "source snapshot digest")
        _require_identifier(self.controller_identity, "controller identity")
        _require_identifier(self.credential_broker_identity, "credential broker identity")
        if self.controller_identity == self.credential_broker_identity:
            raise ValueError("controller and credential broker identities must differ")
        mount_parts: dict[str, tuple[str, ...]] = {}
        for label, path in (
            ("guest executable path", self.guest_executable_path),
            ("source mount", self.source_mount),
            ("writable overlay", self.writable_overlay),
        ):
            try:
                mount_parts[label] = portable_path_parts(path)
            except ValueError as error:
                raise ValueError(f"{label} must be a portable relative path") from error
        source_parts = mount_parts["source mount"]
        overlay_parts = mount_parts["writable overlay"]
        executable_parts = mount_parts["guest executable path"]
        if source_parts[: len(overlay_parts)] == overlay_parts or overlay_parts[: len(source_parts)] == source_parts:
            raise ValueError("source mount and writable overlay must be disjoint")
        if executable_parts[: len(source_parts)] != source_parts:
            raise ValueError("guest executable must be under the immutable source mount")
        for label, value, expected in (
            ("root filesystem", self.rootfs_read_only, True),
            ("source mount", self.source_read_only, True),
            ("host home mount", self.host_home_mounted, False),
            ("host evidence mount", self.host_evidence_mounted, False),
            ("host socket mount", self.host_socket_mounted, False),
            ("host device mount", self.host_devices_mounted, False),
            ("no-new-privileges", self.no_new_privileges, True),
        ):
            if value is not expected:
                raise ValueError(f"{label} hard-isolation requirement is mandatory")
        if self.schema_version != 1:
            raise ValueError("unsupported hard-isolation profile schema version")
        grants = tuple(self.network_grants)
        if len({(grant.protocol, grant.destination, grant.port) for grant in grants}) != len(grants):
            raise ValueError("network grants must be unique")
        if self.egress_enforcement not in {"deny-all", "pinned-egress-proxy"}:
            raise ValueError("unsupported hard-isolation egress enforcement")
        if grants and self.egress_enforcement != "pinned-egress-proxy":
            raise ValueError("network grants require a pinned egress proxy")
        if not grants and self.egress_enforcement != "deny-all":
            raise ValueError("empty network grants require deny-all egress")
        if self.egress_enforcement == "pinned-egress-proxy":
            if self.egress_proxy_identity is None or self.egress_proxy_digest is None:
                raise ValueError("pinned egress proxy identity and digest are required")
            _require_identifier(self.egress_proxy_identity, "egress proxy identity")
            _require_digest(self.egress_proxy_digest, "egress proxy digest")
        elif self.egress_proxy_identity is not None or self.egress_proxy_digest is not None:
            raise ValueError("deny-all egress cannot declare a proxy")
        object.__setattr__(self, "network_grants", grants)

    def to_contract(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "runtime": self.runtime.value,
            "runtime_digest": self.runtime_digest,
            "image_digest": self.image_digest,
            "guest_executable_digest": self.guest_executable_digest,
            "guest_executable_path": self.guest_executable_path,
            "source_snapshot_digest": self.source_snapshot_digest,
            "source_mount": self.source_mount,
            "writable_overlay": self.writable_overlay,
            "limits": self.limits.to_contract(),
            "controller_identity": self.controller_identity,
            "credential_broker_identity": self.credential_broker_identity,
            "rootfs_read_only": self.rootfs_read_only,
            "source_read_only": self.source_read_only,
            "host_home_mounted": self.host_home_mounted,
            "host_evidence_mounted": self.host_evidence_mounted,
            "host_socket_mounted": self.host_socket_mounted,
            "host_devices_mounted": self.host_devices_mounted,
            "no_new_privileges": self.no_new_privileges,
            "egress_enforcement": self.egress_enforcement,
            "egress_proxy_identity": self.egress_proxy_identity,
            "egress_proxy_digest": self.egress_proxy_digest,
            "network_grants": [grant.to_contract() for grant in self.network_grants],
        }

    def digest(self) -> str:
        return sha256_digest(_canonical_json(self.to_contract()))


@dataclass(frozen=True, slots=True)
class HardIsolationCapability:
    """A runtime adapter's host observation, never a declaration of equivalence."""

    capability_id: str
    adapter_identity: str
    runtime: IsolationRuntime
    runtime_digest: str
    supported: bool
    conformance_status: str
    reason: str
    adapter_version: str

    def __post_init__(self) -> None:
        _require_identifier(self.capability_id, "capability ID")
        _require_identifier(self.adapter_identity, "adapter identity")
        _require_digest(self.runtime_digest, "runtime digest")
        _require_identifier(self.reason, "capability reason")
        _require_identifier(self.adapter_version, "adapter version")
        if self.conformance_status not in {"unverified", "failed", "passed"}:
            raise ValueError("invalid hard-isolation conformance status")
        if self.supported != (self.conformance_status == "passed"):
            raise ValueError("only passed conformance may report hard isolation supported")

    def to_subject(self, profile: HardIsolationProfile) -> dict[str, object]:
        return {
            "capability_id": self.capability_id,
            "adapter_identity": self.adapter_identity,
            "adapter_version": self.adapter_version,
            "profile_digest": profile.digest(),
            "runtime": self.runtime.value,
            "runtime_digest": self.runtime_digest,
            "image_digest": profile.image_digest,
            "guest_executable_digest": profile.guest_executable_digest,
            "conformance_status": self.conformance_status,
        }


class CapabilityAuthorizer(Protocol):
    """Verify an externally issued, fresh capability statement before guest launch."""

    def authorize(
        self,
        profile: HardIsolationProfile,
        capability: HardIsolationCapability,
        attestation: Mapping[str, object],
    ) -> None: ...


class UnavailableCapabilityAuthorizer:
    """Default: adapter self-assertion is never authorization."""

    def authorize(
        self,
        profile: HardIsolationProfile,
        capability: HardIsolationCapability,
        attestation: Mapping[str, object],
    ) -> None:
        raise HardIsolationUnavailable(
            "hard-isolation capability lacks a configured external authorizer"
        )


class ExternalCapabilityAuthorizer:
    """Verify a signed adapter capability via the custody root/keyset lifecycle.

    The verifier's pinned root, authenticated keyset history, freshness checks, key
    rotation and revocation rules remain outside this adapter. The supplied attestation
    remains a statement by that external authority; it is not a claim that the local host
    itself is trustworthy.
    """

    def __init__(
        self,
        verifier: Ed25519CustodyVerifier,
        provenance: CapabilityAttestationProvenance,
    ) -> None:
        self.verifier = verifier
        self.provenance = provenance

    def authorize(
        self,
        profile: HardIsolationProfile,
        capability: HardIsolationCapability,
        attestation: Mapping[str, object],
    ) -> None:
        validation = validate_contract("hard-isolation-capability-attestation", dict(attestation))
        if not validation.valid:
            raise HardIsolationUnavailable(
                "hard-isolation capability attestation is invalid: " + "; ".join(validation.issues)
            )
        subject = attestation.get("subject")
        if not isinstance(subject, Mapping) or dict(subject) != capability.to_subject(profile):
            raise HardIsolationUnavailable(
                "hard-isolation capability attestation has foreign profile/adapter bindings"
            )
        if str(attestation["signer_identity"]) in {
            capability.adapter_identity,
            profile.controller_identity,
            profile.credential_broker_identity,
        }:
            raise HardIsolationUnavailable(
                "hard-isolation capability signer must be external to adapter/controller/broker"
            )
        custody_path = str(self.verifier.provenance.path).strip().casefold()
        if (
            not custody_path
            or custody_path == ":memory:"
            or ":memory:" in custody_path
            or "mode=memory" in custody_path
        ):
            raise HardIsolationUnavailable(
                "hard-isolation capability verification requires durable custody key provenance"
            )
        try:
            self.verifier.verify_signed_envelope(
                attestation,
                audience=HARD_ISOLATION_AUDIENCE,
                domain=_HARD_ISOLATION_CAPABILITY_DOMAIN,
            )
        except CustodyError as error:
            raise HardIsolationUnavailable(
                f"hard-isolation capability attestation was not externally verified: {error}"
            ) from error
        self.provenance.record(attestation)


class CapabilityAttestationProvenance:
    """Filesystem-backed replay/collision provenance for verified capability envelopes.

    The external signature authenticates the statement. This store only preserves local
    admission history, so a writable host can still deny service; it is not external
    immutable retention.
    """

    def __init__(self, root: str | Path, *, require_durable: bool = True) -> None:
        self.root = Path(root).resolve()
        raw = str(root).strip().casefold()
        if require_durable and (not raw or raw == ":memory:" or ":memory:" in raw):
            raise ValueError("capability attestation provenance requires a filesystem path")
        self.root.mkdir(parents=True, exist_ok=True)

    def record(self, attestation: Mapping[str, object]) -> None:
        raw = _canonical_json(attestation)
        authority = str(attestation["authority_id"])
        attestation_id = str(attestation["attestation_id"])
        key_id = str(attestation["key_id"])
        nonce = str(attestation["nonce"])
        for category, identifier in (
            ("attestation-id", f"{authority}\0{attestation_id}"),
            ("nonce", f"{authority}\0{key_id}\0{nonce}"),
        ):
            filename = sha256_digest(identifier.encode("utf-8")).removeprefix("sha256:")
            directory = self.root / category
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / f"{filename}.json"
            try:
                with target.open("xb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
            except FileExistsError:
                if target.read_bytes() != raw:
                    raise HardIsolationUnavailable(
                        "hard-isolation capability attestation ID or nonce was replayed"
                    ) from None


@dataclass(frozen=True, slots=True)
class HardIsolationExecutionPlan:
    """Sealed credential-free guest execution plan bound to one command intent/profile."""

    execution_id: str
    tool_intent_digest: str
    profile_digest: str
    mission_id: str
    state_ref: str
    actor_id: str
    lease_id: str
    guest_argv: tuple[str, ...]
    credential_operation_id: str | None
    schema_version: int = 1

    @classmethod
    def create(
        cls,
        profile: HardIsolationProfile,
        intent: Mapping[str, object],
        *,
        guest_argv: tuple[str, ...],
        credential_operation_id: str | None = None,
    ) -> HardIsolationExecutionPlan:
        try:
            digest = tool_intent_digest(intent)
        except (TypeError, ValueError, UnicodeError) as error:
            raise HardIsolationRejected("hard-isolation execution intent is not canonical") from error
        payload = {
            "schema_version": 1,
            "tool_intent_digest": digest,
            "profile_digest": profile.digest(),
            "mission_id": intent.get("mission_id"),
            "state_ref": intent.get("state_ref"),
            "actor_id": intent.get("actor_id"),
            "lease_id": intent.get("lease_id"),
            "guest_argv": list(guest_argv),
            "credential_operation_id": credential_operation_id,
        }
        execution_id = "HIEXEC-" + sha256_digest(_canonical_json(payload)).removeprefix("sha256:")
        payload["execution_id"] = execution_id
        validation = validate_contract("hard-isolation-execution-plan", payload)
        if not validation.valid:
            raise HardIsolationRejected("invalid hard-isolation execution plan: " + "; ".join(validation.issues))
        plan = cls(
            execution_id,
            digest,
            profile.digest(),
            str(payload["mission_id"]),
            str(payload["state_ref"]),
            str(payload["actor_id"]),
            str(payload["lease_id"]),
            tuple(guest_argv),
            credential_operation_id,
        )
        plan._validate(profile)
        return plan

    def _validate(self, profile: HardIsolationProfile) -> None:
        if not _EXECUTION_ID.fullmatch(self.execution_id):
            raise HardIsolationRejected("hard-isolation execution ID is malformed")
        if self.schema_version != 1:
            raise HardIsolationRejected("unsupported hard-isolation execution plan schema version")
        _require_digest(self.tool_intent_digest, "tool intent digest")
        _require_digest(self.profile_digest, "profile digest")
        for label, value in (
            ("execution mission", self.mission_id),
            ("execution state", self.state_ref),
            ("execution actor", self.actor_id),
            ("execution lease", self.lease_id),
        ):
            _require_identifier(value, label)
        if self.profile_digest != profile.digest() or not self.guest_argv:
            raise HardIsolationRejected("hard-isolation execution plan does not bind profile/argv")
        expected_payload = {
            "schema_version": self.schema_version,
            "tool_intent_digest": self.tool_intent_digest,
            "profile_digest": self.profile_digest,
            "mission_id": self.mission_id,
            "state_ref": self.state_ref,
            "actor_id": self.actor_id,
            "lease_id": self.lease_id,
            "guest_argv": list(self.guest_argv),
            "credential_operation_id": self.credential_operation_id,
        }
        expected_id = "HIEXEC-" + sha256_digest(
            _canonical_json(expected_payload)
        ).removeprefix("sha256:")
        if self.execution_id != expected_id:
            raise HardIsolationRejected("hard-isolation execution ID does not bind its plan")
        if self.guest_argv[0] != profile.guest_executable_path:
            raise HardIsolationRejected("guest argv does not name the pinned guest executable path")
        for argument in self.guest_argv:
            if not isinstance(argument, str) or not argument or len(argument) > 16_384:
                raise HardIsolationRejected("guest argv is invalid")
            if _SENSITIVE_ARG.search(argument):
                raise HardIsolationRejected("guest argv must not carry credentials or secrets")
        if self.credential_operation_id is not None:
            _require_identifier(self.credential_operation_id, "credential broker operation")

    def to_contract(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "execution_id": self.execution_id,
            "tool_intent_digest": self.tool_intent_digest,
            "profile_digest": self.profile_digest,
            "mission_id": self.mission_id,
            "state_ref": self.state_ref,
            "actor_id": self.actor_id,
            "lease_id": self.lease_id,
            "guest_argv": list(self.guest_argv),
            "credential_operation_id": self.credential_operation_id,
        }

    @property
    def digest(self) -> str:
        return sha256_digest(_canonical_json(self.to_contract()))


@dataclass(frozen=True, slots=True)
class HardIsolationReceipt:
    """A controller observation. Guest output remains an untrusted digest-only artifact."""

    receipt_id: str
    execution_id: str
    execution_plan_digest: str
    intent_digest: str
    profile_id: str
    profile_digest: str
    runtime: IsolationRuntime
    runtime_digest: str
    image_digest: str
    guest_executable_digest: str
    source_snapshot_digest: str
    controller_identity: str
    actor_id: str
    outcome: IsolationOutcome
    exit_code: int | None
    output_digest: str
    output_bytes: int
    mounts_enforced: bool
    network_enforced: bool
    resource_limits_enforced: bool
    cleanup_completed: bool
    observed_at: str
    adapter_version: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not _RECEIPT_ID.fullmatch(self.receipt_id):
            raise ValueError("receipt id must be a bounded portable single segment")
        if not _EXECUTION_ID.fullmatch(self.execution_id):
            raise ValueError("receipt execution ID is malformed")
        for label, value in (
            ("controller identity", self.controller_identity),
            ("actor id", self.actor_id),
            ("observed at", self.observed_at),
            ("adapter version", self.adapter_version),
        ):
            _require_identifier(value, label)
        for label, value in (
            ("intent digest", self.intent_digest),
            ("execution plan digest", self.execution_plan_digest),
            ("profile digest", self.profile_digest),
            ("runtime digest", self.runtime_digest),
            ("image digest", self.image_digest),
            ("guest executable digest", self.guest_executable_digest),
            ("source snapshot digest", self.source_snapshot_digest),
            ("output digest", self.output_digest),
        ):
            _require_digest(value, label)
        if self.controller_identity == self.actor_id:
            raise ValueError("controller must differ from guest actor")
        if self.schema_version != 1 or self.output_bytes < 0:
            raise ValueError("invalid hard-isolation receipt")
        if self.outcome == IsolationOutcome.SUCCEEDED and self.exit_code != 0:
            raise ValueError("successful isolation receipt requires exit code 0")
        if self.outcome != IsolationOutcome.SUCCEEDED and self.exit_code == 0:
            raise ValueError("non-success isolation receipt cannot claim exit code 0")
        if not all(
            value is True
            for value in (
                self.mounts_enforced,
                self.network_enforced,
                self.resource_limits_enforced,
                self.cleanup_completed,
            )
        ):
            raise ValueError("controller receipt requires enforced boundary and cleanup observations")

    def to_contract(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "execution_id": self.execution_id,
            "execution_plan_digest": self.execution_plan_digest,
            "intent_digest": self.intent_digest,
            "profile_id": self.profile_id,
            "profile_digest": self.profile_digest,
            "runtime": self.runtime.value,
            "runtime_digest": self.runtime_digest,
            "image_digest": self.image_digest,
            "guest_executable_digest": self.guest_executable_digest,
            "source_snapshot_digest": self.source_snapshot_digest,
            "controller_identity": self.controller_identity,
            "actor_id": self.actor_id,
            "outcome": self.outcome.value,
            "exit_code": self.exit_code,
            "output_digest": self.output_digest,
            "output_bytes": self.output_bytes,
            "mounts_enforced": self.mounts_enforced,
            "network_enforced": self.network_enforced,
            "resource_limits_enforced": self.resource_limits_enforced,
            "cleanup_completed": self.cleanup_completed,
            "observed_at": self.observed_at,
            "adapter_version": self.adapter_version,
        }


class HardIsolationAdapter(Protocol):
    """An external privileged runtime adapter; it owns no guest-visible credentials."""

    def capability(self, profile: HardIsolationProfile) -> HardIsolationCapability: ...

    def capability_attestation(
        self, profile: HardIsolationProfile, capability: HardIsolationCapability
    ) -> Mapping[str, object]: ...

    def execute(
        self, profile: HardIsolationProfile, plan: HardIsolationExecutionPlan
    ) -> HardIsolationReceipt: ...


class UnavailableHardIsolationAdapter:
    """Default adapter: no silent local/container executable downgrade is allowed."""

    def __init__(self, reason: str = "no authorized hard-isolation runtime is configured") -> None:
        self.reason = reason

    def capability(self, profile: HardIsolationProfile) -> HardIsolationCapability:
        return HardIsolationCapability(
            capability_id="unavailable-hard-isolation",
            adapter_identity="unavailable-hard-isolation-adapter",
            runtime=profile.runtime,
            runtime_digest=profile.runtime_digest,
            supported=False,
            conformance_status="unverified",
            reason=self.reason,
            adapter_version="unavailable-hard-isolation-adapter-v1",
        )

    def execute(
        self, profile: HardIsolationProfile, plan: HardIsolationExecutionPlan
    ) -> HardIsolationReceipt:
        raise HardIsolationUnavailable(self.reason)

    def capability_attestation(
        self, profile: HardIsolationProfile, capability: HardIsolationCapability
    ) -> Mapping[str, object]:
        return {}


class HardIsolationGateway:
    """Admission gate that will not substitute the process sandbox for hard isolation."""

    def __init__(
        self,
        adapter: HardIsolationAdapter | None = None,
        *,
        authorizer: CapabilityAuthorizer | None = None,
        collector: HardIsolationReceiptCollector | None = None,
    ) -> None:
        self.adapter = adapter or UnavailableHardIsolationAdapter()
        self.authorizer = authorizer or UnavailableCapabilityAuthorizer()
        if collector is None:
            raise ValueError("hard-isolation gateway requires a host receipt collector")
        self.collector = collector

    def execute(
        self,
        profile: HardIsolationProfile,
        intent: Mapping[str, Any],
        plan: HardIsolationExecutionPlan,
    ) -> HardIsolationReceipt:
        profile_validation = validate_contract("hard-isolation-profile", profile.to_contract())
        if not profile_validation.valid:
            raise HardIsolationRejected("invalid hard-isolation profile: " + "; ".join(profile_validation.issues))
        if not isinstance(intent, Mapping):
            raise HardIsolationRejected("hard-isolation intent must be an object")
        intent_document = dict(intent)
        intent_validation = validate_contract("tool-intent", intent_document)
        if not intent_validation.valid:
            raise HardIsolationRejected("invalid hard-isolation intent: " + "; ".join(intent_validation.issues))
        try:
            intent_digest = tool_intent_digest(intent_document)
        except (TypeError, ValueError, UnicodeError) as error:
            raise HardIsolationRejected("hard-isolation intent cannot be canonically digested") from error
        if intent_document.get("action_digest") != intent_digest:
            raise HardIsolationRejected("hard-isolation intent digest mismatch")
        self._validate_execution_plan(profile, intent_document, plan, intent_digest)
        capability = self.adapter.capability(profile)
        if (
            not capability.supported
            or capability.conformance_status != "passed"
            or capability.runtime is not profile.runtime
            or capability.runtime_digest != profile.runtime_digest
        ):
            raise HardIsolationUnavailable(
                "hard isolation is unavailable for this exact sealed profile: " + capability.reason
            )
        self.authorizer.authorize(
            profile,
            capability,
            self.adapter.capability_attestation(profile, capability),
        )
        self.collector.reserve(plan)
        try:
            receipt = self.adapter.execute(profile, plan)
            self._validate_receipt(profile, intent_document, plan, receipt, capability)
            self.collector.persist(plan, receipt)
        except BaseException as error:
            self.collector.quarantine(plan, type(error).__name__)
            raise
        return receipt

    @staticmethod
    def _validate_execution_plan(
        profile: HardIsolationProfile,
        intent: Mapping[str, Any],
        plan: HardIsolationExecutionPlan,
        intent_digest: str,
    ) -> None:
        validation = validate_contract("hard-isolation-execution-plan", plan.to_contract())
        if not validation.valid:
            raise HardIsolationRejected("invalid hard-isolation execution plan: " + "; ".join(validation.issues))
        plan._validate(profile)
        expected = {
            "tool_intent_digest": intent_digest,
            "mission_id": intent["mission_id"],
            "state_ref": intent["state_ref"],
            "actor_id": intent["actor_id"],
            "lease_id": intent["lease_id"],
        }
        for field, value in expected.items():
            if getattr(plan, field) != value:
                raise HardIsolationRejected(f"hard-isolation execution plan has foreign {field}")
        command = intent.get("command")
        if not isinstance(command, Mapping) or command.get("argv") != list(plan.guest_argv):
            raise HardIsolationRejected(
                "hard-isolation execution plan guest argv is not exactly approved by the intent"
            )

    @staticmethod
    def _validate_receipt(
        profile: HardIsolationProfile,
        intent: Mapping[str, Any],
        plan: HardIsolationExecutionPlan,
        receipt: HardIsolationReceipt,
        capability: HardIsolationCapability,
    ) -> None:
        validation = validate_contract("hard-isolation-receipt", receipt.to_contract())
        if not validation.valid:
            raise HardIsolationRejected("invalid hard-isolation receipt: " + "; ".join(validation.issues))
        expected = {
            "receipt_id": "HIRECEIPT-" + plan.execution_id.removeprefix("HIEXEC-"),
            "intent_digest": tool_intent_digest(intent),
            "execution_id": plan.execution_id,
            "execution_plan_digest": plan.digest,
            "profile_id": profile.profile_id,
            "profile_digest": profile.digest(),
            "runtime": profile.runtime,
            "runtime_digest": profile.runtime_digest,
            "image_digest": profile.image_digest,
            "guest_executable_digest": profile.guest_executable_digest,
            "source_snapshot_digest": profile.source_snapshot_digest,
            "controller_identity": profile.controller_identity,
            "actor_id": intent["actor_id"],
            "adapter_version": capability.adapter_version,
        }
        for field, value in expected.items():
            if getattr(receipt, field) != value:
                raise HardIsolationRejected(f"hard-isolation receipt has foreign {field}")
        if receipt.output_bytes > profile.limits.output_bytes:
            raise HardIsolationRejected("hard-isolation receipt exceeds sealed output budget")


class HardIsolationReceiptCollector:
    """Host-side collector for digest-only observations, outside the guest mount plan.

    This is local durable provenance, not external authentication.  Deployment must put
    it under the controller identity; callers must not put it under a guest mount.
    """

    def __init__(self, root: str | Path, *, guest_root: str | Path | None = None) -> None:
        self.root = Path(root).resolve()
        if guest_root is not None:
            guest = Path(guest_root).resolve()
            try:
                self.root.relative_to(guest)
            except ValueError:
                pass
            else:
                raise ValueError("receipt collector root must be outside guest root")
        self.root.mkdir(parents=True, exist_ok=True)

    def reserve(self, plan: HardIsolationExecutionPlan) -> Path:
        """Durably reserve a logical guest execution before adapter dispatch.

        A leftover reservation has an unknowable guest outcome after process interruption,
        so a later caller must quarantine it rather than re-dispatch the same plan.
        """

        validation = validate_contract("hard-isolation-execution-plan", plan.to_contract())
        if not validation.valid:
            raise HardIsolationRejected("invalid hard-isolation execution plan: " + "; ".join(validation.issues))
        directory = self._directory("reservations")
        target = directory / f"{plan.execution_id}.json"
        raw = _canonical_json({"execution_plan_digest": plan.digest})
        try:
            with target.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError as error:
            raise HardIsolationUnavailable(
                "hard-isolation execution was already reserved and is ambiguous/replayed"
            ) from error
        return target

    def quarantine(self, plan: HardIsolationExecutionPlan, reason: str) -> Path:
        _require_identifier(reason, "hard-isolation quarantine reason")
        target = self._directory("quarantine") / f"{plan.execution_id}.json"
        raw = _canonical_json(
            {"execution_plan_digest": plan.digest, "reason": reason}
        )
        try:
            with target.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            if target.read_bytes() != raw:
                raise HardIsolationRejected("hard-isolation quarantine record conflicts") from None
        return target

    def persist(self, plan: HardIsolationExecutionPlan, receipt: HardIsolationReceipt) -> Path:
        validation = validate_contract("hard-isolation-receipt", receipt.to_contract())
        if not validation.valid:
            raise HardIsolationRejected("invalid hard-isolation receipt: " + "; ".join(validation.issues))
        if receipt.execution_id != plan.execution_id or receipt.execution_plan_digest != plan.digest:
            raise HardIsolationRejected("hard-isolation receipt has foreign execution plan")
        reservation = self._directory("reservations") / f"{plan.execution_id}.json"
        if not reservation.is_file() or reservation.read_bytes() != _canonical_json(
            {"execution_plan_digest": plan.digest}
        ):
            raise HardIsolationRejected("hard-isolation receipt lacks its durable execution reservation")
        directory = self._directory("receipts")
        target = directory / f"{plan.execution_id}.json"
        raw = _canonical_json(receipt.to_contract())
        receipt_id_index = self._directory("receipt-ids") / (
            sha256_digest(receipt.receipt_id.encode("utf-8")).removeprefix("sha256:")
            + ".json"
        )
        if receipt_id_index.is_symlink():
            raise HardIsolationRejected("hard-isolation receipt ID index must not be a symlink")
        try:
            with receipt_id_index.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            if receipt_id_index.read_bytes() != raw:
                raise HardIsolationRejected(
                    "hard-isolation receipt ID was replayed with different bytes"
                ) from None
        if target.exists() or target.is_symlink():
            if target.is_symlink() or not target.is_file():
                raise HardIsolationRejected("hard-isolation receipt target is not a regular file")
            if target.read_bytes() != raw:
                raise HardIsolationRejected("hard-isolation receipt id was replayed with different bytes")
            return target
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                if target.is_symlink() or not target.is_file():
                    raise HardIsolationRejected(
                        "hard-isolation receipt target is not a regular file"
                    ) from None
                if target.read_bytes() != raw:
                    raise HardIsolationRejected(
                        "hard-isolation receipt id was replayed with different bytes"
                    ) from None
                return target
            except OSError as error:
                raise HardIsolationRejected(
                    "hard-isolation receipt publication could not reserve an exact target"
                ) from error
        finally:
            if temporary.exists():
                temporary.unlink()
        return target

    def _directory(self, name: str) -> Path:
        directory = self.root / "hard-isolation" / name
        directory.mkdir(parents=True, exist_ok=True)
        if directory.is_symlink():
            raise HardIsolationRejected("hard-isolation collector directory must not be a symlink")
        resolved = directory.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as error:
            raise HardIsolationRejected("hard-isolation collector directory escapes root") from error
        return directory


def local_hard_isolation_capability(profile: HardIsolationProfile) -> HardIsolationCapability:
    """Explicitly report that this package detects no authorized hard runtime by itself."""

    return UnavailableHardIsolationAdapter().capability(profile)
