"""Authenticated identities and carry-forward rules for generated plans."""

from __future__ import annotations

import re
from dataclasses import dataclass
from threading import RLock
from typing import Any, Iterable, Mapping

from .runtime_contracts import (
    ContractViolation,
    canonical_digest,
    canonical_json_bytes,
    raw_sha256,
    require_digest,
    require_identifier,
    strict_json_object,
)

_GIT_OBJECT = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True, slots=True)
class GenerationRecord:
    schema_version: int
    generation_id: str
    request_id: str
    objective_digest: str
    repository_id: str | None
    subject_id: str
    subject_kind: str
    target: str
    parent_generation_id: str | None
    parent_commit: str | None
    parent_tree: str | None
    node_mappings_digest: str
    source_inventory_digest: str
    standard_version: int
    standard_digest: str
    compiler_digest: str
    plan_digest: str

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ContractViolation("unsupported generation-record schema version")
        for value, label in (
            (self.request_id, "request_id"),
            (self.objective_digest, "objective_digest"),
            (self.subject_id, "subject_id"),
            (self.node_mappings_digest, "node_mappings_digest"),
            (self.source_inventory_digest, "source_inventory_digest"),
            (self.standard_digest, "standard_digest"),
            (self.compiler_digest, "compiler_digest"),
            (self.plan_digest, "plan_digest"),
        ):
            require_digest(value, label)
        if self.repository_id is not None:
            require_digest(self.repository_id, "repository_id")
        require_identifier(self.subject_kind, "subject_kind")
        if type(self.target) is not str or not self.target:
            raise ContractViolation("generation target is required")
        if self.parent_generation_id is not None:
            require_digest(self.parent_generation_id, "parent_generation_id")
        if (self.parent_commit is None) != (self.parent_tree is None):
            raise ContractViolation("parent commit and tree must be supplied together")
        if self.subject_kind == "repository":
            if self.repository_id is None or self.parent_commit is None:
                raise ContractViolation(
                    "repository generation requires repository and parent Git identity"
                )
        elif self.repository_id is not None or self.parent_commit is not None:
            raise ContractViolation(
                "non-repository generation cannot carry repository Git identity"
            )
        for value in (self.parent_commit, self.parent_tree):
            if value is not None and _GIT_OBJECT.fullmatch(value) is None:
                raise ContractViolation("parent Git identity must be lowercase 40-hex")
        if type(self.standard_version) is not int or self.standard_version < 1:
            raise ContractViolation("standard_version must be a positive integer")
        require_digest(self.generation_id, "generation_id")
        if self.generation_id != canonical_digest(self.identity_material()):
            raise ContractViolation(
                "generation_id does not authenticate the complete generation identity"
            )

    def identity_material(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "objective_digest": self.objective_digest,
            "repository_id": self.repository_id,
            "subject_id": self.subject_id,
            "subject_kind": self.subject_kind,
            "target": self.target,
            "parent_generation_id": self.parent_generation_id,
            "parent_commit": self.parent_commit,
            "parent_tree": self.parent_tree,
            "node_mappings_digest": self.node_mappings_digest,
            "source_inventory_digest": self.source_inventory_digest,
            "standard_version": self.standard_version,
            "standard_digest": self.standard_digest,
            "compiler_digest": self.compiler_digest,
            "plan_digest": self.plan_digest,
        }

    def to_document(self) -> dict[str, Any]:
        return {"generation_id": self.generation_id, **self.identity_material()}

    @classmethod
    def create(
        cls,
        *,
        request_id: str,
        objective_digest: str,
        repository_id: str | None,
        subject_id: str,
        subject_kind: str,
        target: str,
        parent_generation_id: str | None,
        parent_commit: str | None,
        parent_tree: str | None,
        node_mappings_digest: str,
        source_inventory_digest: str,
        standard_version: int,
        standard_digest: str,
        compiler_digest: str,
        plan_digest: str,
    ) -> "GenerationRecord":
        material = {
            "schema_version": 1,
            "request_id": request_id,
            "objective_digest": objective_digest,
            "repository_id": repository_id,
            "subject_id": subject_id,
            "subject_kind": subject_kind,
            "target": target,
            "parent_generation_id": parent_generation_id,
            "parent_commit": parent_commit,
            "parent_tree": parent_tree,
            "node_mappings_digest": node_mappings_digest,
            "source_inventory_digest": source_inventory_digest,
            "standard_version": standard_version,
            "standard_digest": standard_digest,
            "compiler_digest": compiler_digest,
            "plan_digest": plan_digest,
        }
        return cls(generation_id=canonical_digest(material), **material)

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "GenerationRecord":
        fields = {
            "schema_version",
            "generation_id",
            "request_id",
            "objective_digest",
            "repository_id",
            "subject_id",
            "subject_kind",
            "target",
            "parent_generation_id",
            "parent_commit",
            "parent_tree",
            "node_mappings_digest",
            "source_inventory_digest",
            "standard_version",
            "standard_digest",
            "compiler_digest",
            "plan_digest",
        }
        if not isinstance(document, Mapping) or set(document) != fields:
            raise ContractViolation(
                "generation record has missing or unsupported fields"
            )
        return cls(**document)


class GenerationLineage:
    """Thread-safe in-memory identity index; persistence belongs to the caller."""

    def __init__(self, records: Iterable[GenerationRecord] = ()) -> None:
        self._records: dict[str, GenerationRecord] = {}
        self._plan_subjects: dict[str, str] = {}
        self._lock = RLock()
        pending = tuple(records)
        while pending:
            progress = False
            remainder: list[GenerationRecord] = []
            for record in pending:
                if (
                    record.parent_generation_id is None
                    or record.parent_generation_id in self._records
                ):
                    self.register(record)
                    progress = True
                else:
                    remainder.append(record)
            if not progress:
                raise ContractViolation(
                    "generation lineage has a cycle or missing parent"
                )
            pending = tuple(remainder)

    def register(self, record: GenerationRecord) -> tuple[GenerationRecord, bool]:
        """Record once; exact repetition is idempotent and every collision fails."""

        with self._lock:
            previous = self._records.get(record.generation_id)
            if previous is not None:
                if canonical_json_bytes(previous.to_document()) != canonical_json_bytes(
                    record.to_document()
                ):
                    raise ContractViolation("generation identity collision")
                return previous, False
            parent = None
            if record.parent_generation_id is not None:
                parent = self._records.get(record.parent_generation_id)
                if parent is None:
                    raise ContractViolation("generation parent is missing")
                if (
                    parent.subject_id != record.subject_id
                    or parent.subject_kind != record.subject_kind
                ):
                    raise ContractViolation(
                        "cross-subject generation lineage is forbidden"
                    )
                if (
                    parent.repository_id != record.repository_id
                    or parent.target != record.target
                ):
                    raise ContractViolation(
                        "generation repository or target binding changed"
                    )
                if (
                    parent.request_id != record.request_id
                    or parent.objective_digest != record.objective_digest
                ):
                    raise ContractViolation(
                        "stale or substituted request in generation lineage"
                    )
                if record.standard_version < parent.standard_version:
                    raise ContractViolation(
                        "generation standard downgrade is forbidden"
                    )
            previous_subject = self._plan_subjects.get(record.plan_digest)
            if previous_subject is not None and previous_subject != record.subject_id:
                raise ContractViolation(
                    "flat plan fingerprint cannot be reused across subjects"
                )
            self._records[record.generation_id] = record
            self._plan_subjects[record.plan_digest] = record.subject_id
            return record, True

    def require_expected(
        self,
        generation_id: str,
        *,
        request_id: str,
        objective_digest: str,
        subject_id: str,
        repository_id: str | None,
        target: str,
        parent_commit: str | None,
        parent_tree: str | None,
    ) -> GenerationRecord:
        require_digest(generation_id, "generation_id")
        with self._lock:
            record = self._records.get(generation_id)
        if record is None:
            raise ContractViolation("generation is unknown")
        expected = (
            request_id,
            objective_digest,
            subject_id,
            repository_id,
            target,
            parent_commit,
            parent_tree,
        )
        observed = (
            record.request_id,
            record.objective_digest,
            record.subject_id,
            record.repository_id,
            record.target,
            record.parent_commit,
            record.parent_tree,
        )
        if observed != expected:
            raise ContractViolation(
                "generation does not match the current request, subject, target, or tree"
            )
        return record

    def records(self) -> tuple[GenerationRecord, ...]:
        with self._lock:
            return tuple(self._records.values())


@dataclass(frozen=True, slots=True)
class QualifiedNodeReceipt:
    node_id: str
    contract_digest: str
    subject_id: str
    receipt_bytes: bytes
    receipt_digest: str

    def __post_init__(self) -> None:
        require_identifier(self.node_id, "receipt node_id")
        require_digest(self.contract_digest, "receipt contract_digest")
        require_digest(self.subject_id, "receipt subject_id")
        if type(self.receipt_bytes) is not bytes or not self.receipt_bytes:
            raise ContractViolation("qualified receipt bytes are required")
        require_digest(self.receipt_digest, "receipt_digest")
        if raw_sha256(self.receipt_bytes) != self.receipt_digest:
            raise ContractViolation("receipt digest does not match exact bytes")

    @classmethod
    def create(
        cls, node_id: str, contract_digest: str, subject_id: str, receipt_bytes: bytes
    ) -> "QualifiedNodeReceipt":
        return cls(
            node_id,
            contract_digest,
            subject_id,
            receipt_bytes,
            raw_sha256(receipt_bytes),
        )


@dataclass(frozen=True, slots=True)
class CarryForwardResult:
    carried: tuple[QualifiedNodeReceipt, ...]
    requalify: tuple[str, ...]
    historical: tuple[QualifiedNodeReceipt, ...]
    new_nodes: tuple[str, ...]


def carry_forward_receipts(
    *,
    previous_contracts: Mapping[str, str],
    next_contracts: Mapping[str, str],
    receipts: Iterable[QualifiedNodeReceipt],
    subject_id: str,
) -> CarryForwardResult:
    """Carry only byte-identical receipts for unchanged contracts on one subject."""

    require_digest(subject_id, "subject_id")
    for inventory, label in (
        (previous_contracts, "previous"),
        (next_contracts, "next"),
    ):
        for node_id, digest in inventory.items():
            require_identifier(node_id, f"{label} node_id")
            require_digest(digest, f"{label} contract digest")
    receipt_by_node: dict[str, QualifiedNodeReceipt] = {}
    for receipt in receipts:
        if receipt.node_id in receipt_by_node:
            raise ContractViolation("qualified receipt inventory contains duplicates")
        if receipt.subject_id != subject_id:
            raise ContractViolation("cross-subject receipt carry-forward is forbidden")
        if previous_contracts.get(receipt.node_id) != receipt.contract_digest:
            raise ContractViolation(
                "receipt is not qualified for the previous contract"
            )
        receipt_by_node[receipt.node_id] = receipt
    carried: list[QualifiedNodeReceipt] = []
    requalify: list[str] = []
    historical: list[QualifiedNodeReceipt] = []
    for node_id, old_digest in previous_contracts.items():
        receipt = receipt_by_node.get(node_id)
        if node_id not in next_contracts:
            if receipt is not None:
                historical.append(receipt)
        elif next_contracts[node_id] == old_digest:
            if receipt is not None:
                carried.append(receipt)
            else:
                requalify.append(node_id)
        else:
            requalify.append(node_id)
    new_nodes = sorted(set(next_contracts) - set(previous_contracts))
    return CarryForwardResult(
        tuple(sorted(carried, key=lambda item: item.node_id)),
        tuple(sorted(set(requalify))),
        tuple(sorted(historical, key=lambda item: item.node_id)),
        tuple(new_nodes),
    )


@dataclass(frozen=True, slots=True)
class ActivationMaterial:
    generation_id: str
    complete_plan_bytes: bytes
    external_manifest_bytes: bytes
    plan_digest: str
    manifest_digest: str

    def __post_init__(self) -> None:
        require_digest(self.generation_id, "generation_id")
        if type(self.complete_plan_bytes) is not bytes or not self.complete_plan_bytes:
            raise ContractViolation("complete sealed plan bytes are required")
        if (
            type(self.external_manifest_bytes) is not bytes
            or not self.external_manifest_bytes
        ):
            raise ContractViolation("complete external manifest bytes are required")
        require_digest(self.plan_digest, "plan_digest")
        require_digest(self.manifest_digest, "manifest_digest")
        if raw_sha256(self.complete_plan_bytes) != self.plan_digest:
            raise ContractViolation("sealed plan digest does not match complete bytes")
        if raw_sha256(self.external_manifest_bytes) != self.manifest_digest:
            raise ContractViolation(
                "external manifest digest does not match complete bytes"
            )
        manifest = strict_json_object(self.external_manifest_bytes)
        required = {
            "schema_version",
            "kind",
            "generation",
            "plan_digest",
            "authentication",
        }
        if set(manifest) != required:
            raise ContractViolation("external activation manifest is not closed")
        if (
            type(manifest["schema_version"]) is not int
            or manifest["schema_version"] != 1
            or manifest["kind"] != "external-plan-activation-manifest"
        ):
            raise ContractViolation("unsupported external activation manifest")
        if manifest["plan_digest"] != self.plan_digest:
            raise ContractViolation("external manifest plan digest mismatch")
        if (
            not isinstance(manifest["generation"], Mapping)
            or manifest["generation"].get("generation_id") != self.generation_id
        ):
            raise ContractViolation("external manifest generation mismatch")
        authentication = manifest["authentication"]
        if not isinstance(authentication, Mapping) or set(authentication) != {
            "host_signature_required",
            "distinct_key_required",
            "repository_signature_forbidden",
        }:
            raise ContractViolation(
                "external manifest authentication contract is incomplete"
            )
        if set(authentication.values()) != {True}:
            raise ContractViolation(
                "external manifest cannot weaken host authentication"
            )


@dataclass(frozen=True, slots=True)
class TraceabilityDisposition:
    row_id: str
    disposition: str
    target_acceptance_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        require_identifier(self.row_id, "traceability row_id")
        require_identifier(self.disposition, "traceability disposition")
        if not self.target_acceptance_ids or len(
            set(self.target_acceptance_ids)
        ) != len(self.target_acceptance_ids):
            raise ContractViolation(
                "traceability target criteria are required and unique"
            )
        for value in self.target_acceptance_ids:
            require_identifier(value, "target acceptance id")


def validate_traceability(
    rows: Iterable[TraceabilityDisposition],
    *,
    expected_row_ids: Iterable[str],
    required_acceptance_id: str,
) -> tuple[TraceabilityDisposition, ...]:
    require_identifier(required_acceptance_id, "required acceptance id")
    expected = set(expected_row_ids)
    observed: dict[str, TraceabilityDisposition] = {}
    for row in rows:
        if row.row_id in observed:
            raise ContractViolation("traceability contains duplicate rows")
        observed[row.row_id] = row
    if set(observed) != expected:
        raise ContractViolation(
            "traceability row coverage is incomplete or substituted"
        )
    if any(
        required_acceptance_id not in row.target_acceptance_ids
        for row in observed.values()
    ):
        raise ContractViolation("traceability row omits the required target criterion")
    return tuple(observed[row_id] for row_id in sorted(observed))


def verify_historical_bytes(raw: bytes, expected_digest: str) -> None:
    """Prove an historical plan remained byte-identical; never reinterpret it."""

    require_digest(expected_digest, "historical plan digest")
    if type(raw) is not bytes or raw_sha256(raw) != expected_digest:
        raise ContractViolation("historical plan bytes changed")


__all__ = [
    "ActivationMaterial",
    "CarryForwardResult",
    "GenerationLineage",
    "GenerationRecord",
    "QualifiedNodeReceipt",
    "TraceabilityDisposition",
    "carry_forward_receipts",
    "validate_traceability",
    "verify_historical_bytes",
]
