"""Fail-closed, effect-free integration checks for the canonical kernel.

The Integrator is deliberately a gate, not a delivery mechanism.  It compares
already-produced versioned contracts, requires an evidence-bound lineage link,
and emits a Builder work request when it finds a problem.  It never writes a
workspace, invokes an adapter, merges a branch, or hides an incompatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Sequence

from .canonical import canonical_digest


class IntegrationValidationError(ValueError):
    """A proposed integration lacks the immutable data needed for review."""


class IntegrationStatus(StrEnum):
    """The only outcomes an Integrator may report for a bounded handoff."""

    COMPATIBLE = "compatible"
    REMAND = "remand"


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IntegrationValidationError(f"{label} is required")
    return value.strip()


def _items(
    values: Sequence[str],
    label: str,
    *,
    minimum: int = 1,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise IntegrationValidationError(f"{label} must be a sequence of strings")
    normalized = tuple(_text(value, label) for value in values)
    if len(normalized) < minimum:
        raise IntegrationValidationError(f"{label} requires at least {minimum} item(s)")
    if len(set(normalized)) != len(normalized):
        raise IntegrationValidationError(f"{label} must not contain duplicates")
    return normalized


@dataclass(frozen=True, slots=True)
class DataLineage:
    """One immutable lineage declaration for a produced contract artifact."""

    artifact_id: str
    source_artifact_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_id", _text(self.artifact_id, "lineage artifact id"))
        object.__setattr__(
            self,
            "source_artifact_ids",
            _items(self.source_artifact_ids, "lineage source artifact ids", minimum=0),
        )
        object.__setattr__(self, "evidence_refs", _items(self.evidence_refs, "lineage evidence"))
        if self.artifact_id in self.source_artifact_ids:
            raise IntegrationValidationError("lineage cannot cite itself as a source")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())

    def to_document(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "source_artifact_ids": list(self.source_artifact_ids),
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class VersionedContract:
    """A produced interface contract with a pinned schema and lineage record."""

    contract_id: str
    version: int
    runtime_id: str
    schema_digest: str
    lineage: DataLineage

    def __post_init__(self) -> None:
        object.__setattr__(self, "contract_id", _text(self.contract_id, "contract id"))
        if type(self.version) is not int or self.version < 1:
            raise IntegrationValidationError("contract version must be a positive integer")
        object.__setattr__(self, "runtime_id", _text(self.runtime_id, "runtime id"))
        digest = _text(self.schema_digest, "schema digest")
        if not digest.startswith("sha256:"):
            raise IntegrationValidationError("schema digest must be a sha256 reference")
        object.__setattr__(self, "schema_digest", digest)
        if not isinstance(self.lineage, DataLineage):
            raise IntegrationValidationError("contract lineage must be DataLineage")

    @property
    def identity(self) -> tuple[str, int, str]:
        """Return the stable identity the adapter must bind exactly."""

        return (self.contract_id, self.version, self.schema_digest)

    def to_document(self) -> dict[str, object]:
        return {
            "contract_id": self.contract_id,
            "version": self.version,
            "runtime_id": self.runtime_id,
            "schema_digest": self.schema_digest,
            "lineage": self.lineage.to_document(),
        }


@dataclass(frozen=True, slots=True)
class ContractAdapter:
    """An adapter declaration; declaring it never executes it."""

    adapter_id: str
    source_identity: tuple[str, int, str]
    target_identity: tuple[str, int, str]
    evidence_refs: tuple[str, ...]
    preserves_lineage: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "adapter_id", _text(self.adapter_id, "adapter id"))
        object.__setattr__(self, "source_identity", self._identity(self.source_identity, "adapter source"))
        object.__setattr__(self, "target_identity", self._identity(self.target_identity, "adapter target"))
        object.__setattr__(self, "evidence_refs", _items(self.evidence_refs, "adapter evidence"))
        if type(self.preserves_lineage) is not bool:
            raise IntegrationValidationError("adapter preserves_lineage must be boolean")

    @staticmethod
    def _identity(value: tuple[str, int, str], label: str) -> tuple[str, int, str]:
        if not isinstance(value, tuple) or len(value) != 3:
            raise IntegrationValidationError(f"{label} identity must be a three-field tuple")
        contract_id, version, schema_digest = value
        contract_id = _text(contract_id, f"{label} contract id")
        if type(version) is not int or version < 1:
            raise IntegrationValidationError(f"{label} version must be a positive integer")
        schema_digest = _text(schema_digest, f"{label} schema digest")
        if not schema_digest.startswith("sha256:"):
            raise IntegrationValidationError(f"{label} schema digest must be a sha256 reference")
        return (contract_id, version, schema_digest)


@dataclass(frozen=True, slots=True)
class BuilderRemand:
    """A requested Builder work item, not an Integrator-side repair."""

    work_id: str
    reason: str
    affected_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "work_id", _text(self.work_id, "Builder remand work id"))
        object.__setattr__(self, "reason", _text(self.reason, "Builder remand reason"))
        object.__setattr__(self, "affected_refs", _items(self.affected_refs, "Builder remand affected refs"))


@dataclass(frozen=True, slots=True)
class CompatibilityReport:
    """A retained report that keeps every detected incompatibility visible."""

    status: IntegrationStatus
    provider: VersionedContract
    consumer: VersionedContract
    adapter_id: str
    lineage_digest: str
    findings: tuple[str, ...]
    builder_remands: tuple[BuilderRemand, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", IntegrationStatus(self.status))
        if not isinstance(self.provider, VersionedContract) or not isinstance(self.consumer, VersionedContract):
            raise IntegrationValidationError("report requires versioned provider and consumer contracts")
        object.__setattr__(self, "adapter_id", _text(self.adapter_id, "report adapter id"))
        object.__setattr__(self, "lineage_digest", _text(self.lineage_digest, "report lineage digest"))
        object.__setattr__(self, "findings", _items(self.findings, "integration findings"))
        if any(not isinstance(item, BuilderRemand) for item in self.builder_remands):
            raise IntegrationValidationError("Builder remands must be BuilderRemand values")
        if self.status is IntegrationStatus.COMPATIBLE and self.builder_remands:
            raise IntegrationValidationError("compatible report cannot request Builder repairs")
        if self.status is IntegrationStatus.REMAND and not self.builder_remands:
            raise IntegrationValidationError("incompatible report must request Builder repairs")

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "status": self.status.value,
                "provider": self.provider.to_document(),
                "consumer": self.consumer.to_document(),
                "adapter_id": self.adapter_id,
                "lineage_digest": self.lineage_digest,
                "findings": list(self.findings),
                "builder_remands": [
                    {"work_id": item.work_id, "reason": item.reason, "affected_refs": list(item.affected_refs)}
                    for item in self.builder_remands
                ],
            }
        )


class Integrator:
    """Produce compatibility evidence and remand work without changing either runtime."""

    def validate(
        self,
        provider: VersionedContract,
        consumer: VersionedContract,
        adapter: ContractAdapter,
        *,
        accepted_consumer_versions: Iterable[int],
    ) -> CompatibilityReport:
        """Evaluate an adapter declaration against contracts and retained lineage.

        Any gap is returned as a distinct finding and Builder remand.  The
        method intentionally returns a report instead of raising for a normal
        incompatibility, so callers cannot accidentally discard that evidence.
        """

        if not isinstance(provider, VersionedContract) or not isinstance(consumer, VersionedContract):
            raise IntegrationValidationError("Integrator requires versioned provider and consumer contracts")
        if not isinstance(adapter, ContractAdapter):
            raise IntegrationValidationError("Integrator requires a ContractAdapter")
        accepted = tuple(accepted_consumer_versions)
        if not accepted or any(type(version) is not int or version < 1 for version in accepted):
            raise IntegrationValidationError("accepted consumer versions must be positive integers")

        findings: list[str] = []
        affected_refs: list[str] = [provider.lineage.artifact_id, consumer.lineage.artifact_id, adapter.adapter_id]
        if adapter.source_identity != provider.identity:
            findings.append("adapter source identity does not bind the provider contract")
        if adapter.target_identity != consumer.identity:
            findings.append("adapter target identity does not bind the consumer contract")
        if consumer.version not in accepted:
            findings.append("consumer contract version is not accepted by the integration boundary")
        if not adapter.preserves_lineage:
            findings.append("adapter does not declare lineage preservation")
        if provider.lineage.artifact_id not in consumer.lineage.source_artifact_ids:
            findings.append("consumer lineage omits the provider artifact")

        lineage_digest = canonical_digest(
            {
                "provider_lineage": provider.lineage.to_document(),
                "consumer_lineage": consumer.lineage.to_document(),
                "adapter_evidence": list(adapter.evidence_refs),
            }
        )
        if not findings:
            return CompatibilityReport(
                IntegrationStatus.COMPATIBLE,
                provider,
                consumer,
                adapter.adapter_id,
                lineage_digest,
                ("versioned contracts, adapter binding, and data lineage are compatible",),
                (),
            )
        remands = tuple(
            BuilderRemand(
                f"BUILDER-REMAND-{index + 1}",
                finding,
                tuple(dict.fromkeys(affected_refs)),
            )
            for index, finding in enumerate(findings)
        )
        return CompatibilityReport(
            IntegrationStatus.REMAND,
            provider,
            consumer,
            adapter.adapter_id,
            lineage_digest,
            tuple(findings),
            remands,
        )
