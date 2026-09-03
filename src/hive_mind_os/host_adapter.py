"""Subject-neutral host boundary contracts.

The protocol describes the boundary; it provides no default host implementation
and never derives authority from capability.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Protocol, runtime_checkable

from .activation_bundle import AuthorizedOneRun
from .runtime_contracts import (
    ContractViolation,
    canonical_digest,
    require_digest,
    require_identifier,
    require_time,
)

_GIT_ID = re.compile(r"[0-9a-f]{40}\Z")
HOST_DEADLINE_CAPABILITY = "host-enforced-deadline-v1"


class HostReceiptState(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    DENIED = "DENIED"


@dataclass(frozen=True, slots=True)
class HostIdentity:
    host_id: str
    platform: str
    architecture: str
    runtime_version: str
    executable_digest: str
    adapter_digest: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.host_id, "host_id"),
            (self.platform, "platform"),
            (self.architecture, "architecture"),
            (self.runtime_version, "runtime_version"),
        ):
            require_identifier(value, label)
        require_digest(self.executable_digest, "executable_digest")
        require_digest(self.adapter_digest, "adapter_digest")

    def to_document(self) -> dict[str, str]:
        return {
            "host_id": self.host_id,
            "platform": self.platform,
            "architecture": self.architecture,
            "runtime_version": self.runtime_version,
            "executable_digest": self.executable_digest,
            "adapter_digest": self.adapter_digest,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())


@dataclass(frozen=True, slots=True)
class HostObservation:
    identity: HostIdentity
    subject_id: str
    observed_at: str
    capabilities: tuple[str, ...]
    trust_evidence_digest: str
    clean: bool

    def __post_init__(self) -> None:
        if not isinstance(self.identity, HostIdentity):
            raise ContractViolation("host observation requires a typed identity")
        require_digest(self.subject_id, "host subject_id")
        require_time(self.observed_at, "host observed_at")
        if type(self.capabilities) is not tuple or any(
            type(item) is not str or not item for item in self.capabilities
        ):
            raise ContractViolation("host capabilities must contain strings")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ContractViolation("host capabilities contain duplicates")
        require_digest(self.trust_evidence_digest, "trust_evidence_digest")
        if type(self.clean) is not bool:
            raise ContractViolation("host clean flag must be boolean")

    def to_document(self) -> dict[str, Any]:
        return {
            "identity": self.identity.to_document(),
            "subject_id": self.subject_id,
            "observed_at": self.observed_at,
            "capabilities": list(self.capabilities),
            "trust_evidence_digest": self.trust_evidence_digest,
            "clean": self.clean,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())


@dataclass(frozen=True, slots=True)
class HostLease:
    lease_id: str
    host_id: str
    subject_id: str
    generation_id: str
    authority_digest: str
    adapter_inventory_digest: str
    external_effects_required: bool
    compilation_digest: str
    activation_digest: str
    activation_proof_digest: str
    candidate_commit: str
    candidate_tree: str
    candidate_content_sha256: str
    candidate_parent_commit: str
    candidate_parent_tree: str
    manifest_sha256: str
    repository_id: str
    request_sha256: str
    target_branch: str
    execution_client_sha256: str
    activation_issued_at: str
    protected_merge_authorized: bool
    host_identity_digest: str
    trust_evidence_digest: str
    required_capabilities: tuple[str, ...]
    issued_at: str
    expires_at: str
    allowed_node_ids: tuple[str, ...]
    nonce_digest: str

    def __post_init__(self) -> None:
        require_identifier(self.lease_id, "lease_id")
        require_identifier(self.host_id, "lease host_id")
        for value, label in (
            (self.subject_id, "lease subject_id"),
            (self.generation_id, "lease generation_id"),
            (self.authority_digest, "lease authority_digest"),
            (
                self.adapter_inventory_digest,
                "lease adapter_inventory_digest",
            ),
            (self.compilation_digest, "lease compilation_digest"),
            (self.activation_digest, "lease activation_digest"),
            (self.activation_proof_digest, "lease activation_proof_digest"),
            (
                self.candidate_content_sha256,
                "lease candidate_content_sha256",
            ),
            (self.manifest_sha256, "lease manifest_sha256"),
            (self.repository_id, "lease repository_id"),
            (self.request_sha256, "lease request_sha256"),
            (
                self.execution_client_sha256,
                "lease execution_client_sha256",
            ),
            (self.host_identity_digest, "lease host_identity_digest"),
            (self.trust_evidence_digest, "lease trust_evidence_digest"),
            (self.nonce_digest, "lease nonce_digest"),
        ):
            require_digest(value, label)
        if type(self.external_effects_required) is not bool:
            raise ContractViolation(
                "lease external_effects_required must be boolean"
            )
        for value, label in (
            (self.candidate_commit, "lease candidate_commit"),
            (self.candidate_tree, "lease candidate_tree"),
            (self.candidate_parent_commit, "lease candidate_parent_commit"),
            (self.candidate_parent_tree, "lease candidate_parent_tree"),
        ):
            if type(value) is not str or not _GIT_ID.fullmatch(value):
                raise ContractViolation(
                    f"{label} must be a 40-character lowercase Git ID"
                )
        require_identifier(self.target_branch, "lease target_branch")
        activation_issued = require_time(
            self.activation_issued_at, "lease activation_issued_at"
        )
        if self.protected_merge_authorized is not False:
            raise ContractViolation("host lease cannot authorize a protected merge")
        if type(self.required_capabilities) is not tuple or any(
            type(item) is not str or not item for item in self.required_capabilities
        ):
            raise ContractViolation("lease required capabilities must be strings")
        if len(set(self.required_capabilities)) != len(self.required_capabilities):
            raise ContractViolation("lease required capabilities contain duplicates")
        if HOST_DEADLINE_CAPABILITY not in self.required_capabilities:
            raise ContractViolation(
                "lease lacks externally enforced deadline capability"
            )
        issued = require_time(self.issued_at, "lease issued_at")
        expires = require_time(self.expires_at, "lease expires_at")
        if issued < activation_issued:
            raise ContractViolation("host lease predates its activation")
        if expires <= issued:
            raise ContractViolation("host lease must expire after it is issued")
        if not self.allowed_node_ids or any(
            type(item) is not str or not item for item in self.allowed_node_ids
        ):
            raise ContractViolation("host lease requires allowed node ids")
        if len(set(self.allowed_node_ids)) != len(self.allowed_node_ids):
            raise ContractViolation("host lease node ids contain duplicates")

    def to_document(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "host_id": self.host_id,
            "subject_id": self.subject_id,
            "generation_id": self.generation_id,
            "authority_digest": self.authority_digest,
            "adapter_inventory_digest": self.adapter_inventory_digest,
            "external_effects_required": self.external_effects_required,
            "compilation_digest": self.compilation_digest,
            "activation_digest": self.activation_digest,
            "activation_proof_digest": self.activation_proof_digest,
            "candidate_commit": self.candidate_commit,
            "candidate_tree": self.candidate_tree,
            "candidate_content_sha256": self.candidate_content_sha256,
            "candidate_parent_commit": self.candidate_parent_commit,
            "candidate_parent_tree": self.candidate_parent_tree,
            "manifest_sha256": self.manifest_sha256,
            "repository_id": self.repository_id,
            "request_sha256": self.request_sha256,
            "target_branch": self.target_branch,
            "execution_client_sha256": self.execution_client_sha256,
            "activation_issued_at": self.activation_issued_at,
            "protected_merge_authorized": self.protected_merge_authorized,
            "host_identity_digest": self.host_identity_digest,
            "trust_evidence_digest": self.trust_evidence_digest,
            "required_capabilities": list(self.required_capabilities),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "allowed_node_ids": list(self.allowed_node_ids),
            "nonce_digest": self.nonce_digest,
        }


@dataclass(frozen=True, slots=True)
class HostExecutionReceipt:
    receipt_id: str
    lease_id: str
    node_id: str
    state: HostReceiptState
    input_digest: str
    output_digest: str | None
    evidence_digest: str
    observed_at: str

    def __post_init__(self) -> None:
        require_identifier(self.receipt_id, "receipt_id")
        require_identifier(self.lease_id, "receipt lease_id")
        require_identifier(self.node_id, "receipt node_id")
        if not isinstance(self.state, HostReceiptState):
            raise ContractViolation("host receipt state must be typed")
        require_digest(self.input_digest, "receipt input_digest")
        if self.output_digest is not None:
            require_digest(self.output_digest, "receipt output_digest")
        require_digest(self.evidence_digest, "receipt evidence_digest")
        require_time(self.observed_at, "receipt observed_at")
        if self.state is HostReceiptState.SUCCEEDED and self.output_digest is None:
            raise ContractViolation("successful host receipt requires output_digest")

    def to_document(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "lease_id": self.lease_id,
            "node_id": self.node_id,
            "state": self.state.value,
            "input_digest": self.input_digest,
            "output_digest": self.output_digest,
            "evidence_digest": self.evidence_digest,
            "observed_at": self.observed_at,
        }


def canonical_checkpoint_digest(
    lease: HostLease, receipt: HostExecutionReceipt
) -> str:
    """Derive the sole checkpoint identity for one authenticated host result."""

    if type(lease) is not HostLease or type(receipt) is not HostExecutionReceipt:
        raise ContractViolation("checkpoint identity requires typed host contracts")
    if (
        receipt.state is not HostReceiptState.SUCCEEDED
        or receipt.output_digest is None
        or receipt.lease_id != lease.lease_id
        or receipt.node_id not in lease.allowed_node_ids
    ):
        raise ContractViolation(
            "checkpoint identity requires a successful receipt inside the lease"
        )
    return canonical_digest(
        {
            "schema_version": 1,
            "kind": "hive-mind-host-checkpoint-v1",
            "lease_digest": canonical_digest(lease.to_document()),
            "receipt": receipt.to_document(),
        }
    )


@runtime_checkable
class HostAdapter(Protocol):
    """Explicit host boundary; implementations must enforce authority and CAS.

    Effect-capable implementations must atomically reject work outside
    ``lease.issued_at <= now < lease.expires_at`` and the bound one-run
    deadline. Preparation must likewise enforce
    ``authorization.issued_at <= now < min(authorization.expires_at,
    lease_deadline)`` in the same reservation boundary. The Python caller's
    pre-invocation check narrows races but is not a substitute for this
    adapter-owned containment boundary.
    """

    def observe(self, *, subject_id: str) -> HostObservation:
        """Return a fresh observation without changing the subject."""

        ...

    def prepare(
        self,
        *,
        plan_digest: str,
        generation_id: str,
        authority_digest: str,
        adapter_inventory_digest: str,
        external_effects_required: bool,
        compilation_receipt: Mapping[str, Any],
        subject_id: str,
        node_ids: tuple[str, ...],
        nonce_digest: str,
        lease_deadline: str,
        authorization: AuthorizedOneRun,
        required_capabilities: tuple[str, ...],
    ) -> HostLease:
        """Authenticate proof and atomically reserve inside its full interval."""

        ...

    def execute(
        self,
        *,
        node_id: str,
        input_bytes: bytes,
        lease: HostLease,
    ) -> HostExecutionReceipt:
        """Execute one bound node inside the lease's exclusive time interval."""

        ...

    def cancel(self, *, lease: HostLease, reason: str) -> HostExecutionReceipt:
        """Cancel inside the lease interval without replacing its authority."""

        ...


__all__ = [
    "canonical_checkpoint_digest",
    "HostAdapter",
    "HostExecutionReceipt",
    "HOST_DEADLINE_CAPABILITY",
    "HostIdentity",
    "HostLease",
    "HostObservation",
    "HostReceiptState",
]
