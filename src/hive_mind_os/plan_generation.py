"""Deterministic generation of inert portable-plan candidates."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any, Iterable

from .plan_lineage import ActivationMaterial, GenerationLineage, GenerationRecord
from .portable_plan import PortablePlanBundle, SubjectKind
from .runtime_contracts import (
    ContractViolation,
    canonical_digest,
    canonical_json_bytes,
    raw_sha256,
    require_digest,
    require_identifier,
)


@dataclass(frozen=True, slots=True)
class PinnedArtifact:
    name: str
    content: bytes
    digest: str

    def __post_init__(self) -> None:
        require_identifier(self.name, "artifact name")
        if type(self.content) is not bytes or not self.content:
            raise ContractViolation("pinned artifact requires complete immutable bytes")
        require_digest(self.digest, "artifact digest")
        if raw_sha256(self.content) != self.digest:
            raise ContractViolation(f"pinned artifact digest mismatch: {self.name}")

    @classmethod
    def pin(cls, name: str, content: bytes) -> "PinnedArtifact":
        return cls(name, content, raw_sha256(content))

    def inventory_document(self) -> dict[str, Any]:
        return {"name": self.name, "bytes": len(self.content), "digest": self.digest}


@dataclass(frozen=True, slots=True)
class PlanGenerationRequest:
    request_id: str
    objective_digest: str
    subject_id: str
    subject_kind: str
    repository_id: str | None
    target: str
    parent_commit: str | None
    parent_tree: str | None
    parent_generation_id: str | None

    def __post_init__(self) -> None:
        for value, label in (
            (self.request_id, "request_id"),
            (self.objective_digest, "objective_digest"),
            (self.subject_id, "subject_id"),
        ):
            require_digest(value, label)
        require_identifier(self.subject_kind, "subject_kind")
        if type(self.target) is not str or not self.target:
            raise ContractViolation("generation target is required")
        if self.repository_id is not None:
            require_digest(self.repository_id, "repository_id")
        if self.parent_generation_id is not None:
            require_digest(self.parent_generation_id, "parent_generation_id")
        if (self.parent_commit is None) != (self.parent_tree is None):
            raise ContractViolation("parent commit and tree must be supplied together")


@dataclass(frozen=True, slots=True)
class GeneratedPlan:
    record: GenerationRecord
    portable_plan: PortablePlanBundle
    activation_material: ActivationMaterial
    source_inventory: tuple[PinnedArtifact, ...]

    def __post_init__(self) -> None:
        if self.record.plan_digest != self.portable_plan.digest():
            raise ContractViolation("generated record and portable plan differ")
        if self.activation_material.generation_id != self.record.generation_id:
            raise ContractViolation("activation material has a different generation")


class PlanGenerator:
    """Single-writer generator; exact repeats return the original immutable result."""

    def __init__(self, lineage: GenerationLineage | None = None) -> None:
        self.lineage = lineage or GenerationLineage()
        self._results: dict[str, GeneratedPlan] = {}
        self._lock = RLock()

    def generate(
        self,
        request: PlanGenerationRequest,
        plan: PortablePlanBundle,
        *,
        node_mappings: PinnedArtifact,
        sources: Iterable[PinnedArtifact],
        standard: PinnedArtifact,
        standard_version: int,
        compiler: PinnedArtifact,
    ) -> tuple[GeneratedPlan, bool]:
        """Create an inert sealed generation; ``bool`` is false for exact replay."""

        self._validate_request_plan(request, plan)
        if (
            plan.standard.version != standard_version
            or plan.standard.raw_sha256 != standard.digest
            or plan.standard.byte_count != len(standard.content)
        ):
            raise ContractViolation(
                "portable plan standard binding differs from the pinned standard bytes"
            )
        source_inventory = tuple(sources)
        names = [item.name for item in source_inventory]
        if not source_inventory or len(set(names)) != len(names):
            raise ContractViolation(
                "source inventory is required and names must be unique"
            )
        if node_mappings.name in names:
            raise ContractViolation(
                "node mappings must have an independent artifact identity"
            )
        ordered_sources = tuple(sorted(source_inventory, key=lambda item: item.name))
        source_inventory_digest = canonical_digest(
            [item.inventory_document() for item in ordered_sources]
        )
        plan_bytes = plan.canonical_bytes()
        plan_digest = raw_sha256(plan_bytes)
        record = GenerationRecord.create(
            request_id=request.request_id,
            objective_digest=request.objective_digest,
            repository_id=request.repository_id,
            subject_id=request.subject_id,
            subject_kind=request.subject_kind,
            target=request.target,
            parent_generation_id=request.parent_generation_id,
            parent_commit=request.parent_commit,
            parent_tree=request.parent_tree,
            node_mappings_digest=node_mappings.digest,
            source_inventory_digest=source_inventory_digest,
            standard_version=standard_version,
            standard_digest=standard.digest,
            compiler_digest=compiler.digest,
            plan_digest=plan_digest,
        )
        manifest = {
            "schema_version": 1,
            "kind": "external-plan-activation-manifest",
            "generation": record.to_document(),
            "plan_digest": plan_digest,
            "authentication": {
                "host_signature_required": True,
                "distinct_key_required": True,
                "repository_signature_forbidden": True,
            },
        }
        manifest_bytes = canonical_json_bytes(manifest)
        activation = ActivationMaterial(
            record.generation_id,
            plan_bytes,
            manifest_bytes,
            plan_digest,
            raw_sha256(manifest_bytes),
        )
        result = GeneratedPlan(record, plan, activation, ordered_sources)
        with self._lock:
            existing = self._results.get(record.generation_id)
            if existing is not None:
                if (
                    existing.activation_material.complete_plan_bytes != plan_bytes
                    or existing.activation_material.external_manifest_bytes
                    != manifest_bytes
                ):
                    raise ContractViolation("generation result identity collision")
                return existing, False
            _, inserted = self.lineage.register(record)
            if not inserted:
                raise ContractViolation("lineage/result registries disagree")
            self._results[record.generation_id] = result
            return result, True

    @staticmethod
    def _validate_request_plan(
        request: PlanGenerationRequest, plan: PortablePlanBundle
    ) -> None:
        if (
            request.request_id != plan.request_id
            or request.objective_digest != plan.objective_digest
        ):
            raise ContractViolation("portable plan is stale for the generation request")
        if (
            request.subject_id != plan.subject.subject_id
            or request.subject_kind != plan.subject.kind.value
        ):
            raise ContractViolation(
                "portable plan subject differs from generation request"
            )
        if plan.subject.kind is SubjectKind.REPOSITORY:
            repository = plan.subject.repository
            assert repository is not None
            observed = (
                request.repository_id,
                request.target,
                request.parent_commit,
                request.parent_tree,
            )
            expected = (
                repository.repository_id,
                repository.target_branch,
                repository.commit,
                repository.tree,
            )
            if observed != expected:
                raise ContractViolation(
                    "repository request is stale or bound to a different tree"
                )
        elif request.repository_id is not None or request.parent_commit is not None:
            raise ContractViolation(
                "non-repository request contains repository bindings"
            )

    def get(self, generation_id: str) -> GeneratedPlan:
        require_digest(generation_id, "generation_id")
        with self._lock:
            try:
                return self._results[generation_id]
            except KeyError as error:
                raise ContractViolation("generation result is unknown") from error


__all__ = ["GeneratedPlan", "PinnedArtifact", "PlanGenerationRequest", "PlanGenerator"]
