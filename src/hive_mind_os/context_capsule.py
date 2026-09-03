"""Immutable shared round capsules and least-context node deltas."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Sequence

from .runtime_contracts import (
    canonical_digest,
    canonical_json_bytes,
    require_digest,
    require_identifier,
)


class ContextCapsuleError(ValueError):
    """A capsule or node delta is ambiguous, oversized, or misrouted."""


@dataclass(frozen=True, slots=True)
class ContextBody:
    """A small immutable body safe to place directly in a node envelope."""

    context_id: str
    media_type: str
    body: bytes
    digest: str = ""

    def __post_init__(self) -> None:
        require_identifier(self.context_id, "context_id")
        require_identifier(self.media_type, "media_type")
        if type(self.body) is not bytes or not self.body:
            raise ContextCapsuleError("context body must be non-empty immutable bytes")
        expected = canonical_digest(
            {
                "context_id": self.context_id,
                "media_type": self.media_type,
                "body_base64": base64.b64encode(self.body).decode("ascii"),
            }
        )
        if not self.digest:
            object.__setattr__(self, "digest", expected)
        elif self.digest != expected:
            raise ContextCapsuleError("context body digest is invalid")

    def to_document(self, *, include_body: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "context_id": self.context_id,
            "media_type": self.media_type,
            "digest": self.digest,
            "byte_count": len(self.body),
        }
        if include_body:
            result["body_base64"] = base64.b64encode(self.body).decode("ascii")
        return result


@dataclass(frozen=True, slots=True)
class ColdContextReference:
    """Content-addressed context that a worker may retrieve under budget."""

    context_id: str
    digest: str
    byte_count: int
    locator: str

    def __post_init__(self) -> None:
        require_identifier(self.context_id, "context_id")
        require_digest(self.digest, "cold context digest")
        if type(self.byte_count) is not int or self.byte_count < 0:
            raise ContextCapsuleError("cold context byte_count must be non-negative")
        if not isinstance(self.locator, str) or not self.locator.strip():
            raise ContextCapsuleError("cold context locator is required")
        normalized = self.locator.replace("\\", "/")
        parts = normalized.split("/")
        if (
            "://" in normalized
            or normalized.startswith("/")
            or ":" in parts[0]
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise ContextCapsuleError("cold context locator must be an inert relative reference")
        object.__setattr__(self, "locator", "/".join(parts))

    def to_document(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "digest": self.digest,
            "byte_count": self.byte_count,
            "locator": self.locator,
        }


@dataclass(frozen=True, slots=True)
class NodeContextRoute:
    node_id: str
    direct_body_ids: tuple[str, ...]
    cold_reference_ids: tuple[str, ...]
    omitted_context_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        require_identifier(self.node_id, "route node_id")
        values = (
            *self.direct_body_ids,
            *self.cold_reference_ids,
            *self.omitted_context_ids,
        )
        for value in values:
            require_identifier(value, "routed context id")
        if len(set(values)) != len(values):
            raise ContextCapsuleError("a context id must have exactly one route disposition")

    def to_document(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "direct_body_ids": list(self.direct_body_ids),
            "cold_reference_ids": list(self.cold_reference_ids),
            "omitted_context_ids": list(self.omitted_context_ids),
        }


@dataclass(frozen=True, slots=True)
class RoundCapsule:
    """The sole immutable shared context identity for one compiler round."""

    round_id: str
    generation_id: str
    plan_digest: str
    manifest_digest: str
    subject_id: str
    subject_snapshot_digest: str
    authority_digest: str
    model_route_digest: str
    budget_digest: str
    shared_body: ContextBody
    direct_bodies: tuple[ContextBody, ...]
    cold_references: tuple[ColdContextReference, ...]
    routes: tuple[NodeContextRoute, ...]
    capsule_digest: str = ""

    def __post_init__(self) -> None:
        require_identifier(self.round_id, "round_id")
        for label in (
            "generation_id",
            "plan_digest",
            "manifest_digest",
            "subject_id",
            "subject_snapshot_digest",
            "authority_digest",
            "model_route_digest",
            "budget_digest",
        ):
            require_digest(getattr(self, label), label)
        if not isinstance(self.shared_body, ContextBody):
            raise ContextCapsuleError("shared_body must be a ContextBody")
        body_ids = [item.context_id for item in self.direct_bodies]
        cold_ids = [item.context_id for item in self.cold_references]
        route_ids = [item.node_id for item in self.routes]
        if len(set(body_ids)) != len(body_ids):
            raise ContextCapsuleError("direct context ids must be unique")
        if len(set(cold_ids)) != len(cold_ids):
            raise ContextCapsuleError("cold context ids must be unique")
        if set(body_ids) & set(cold_ids):
            raise ContextCapsuleError("context cannot be both direct and cold")
        if len(set(route_ids)) != len(route_ids) or not route_ids:
            raise ContextCapsuleError("capsule requires unique node routes")
        inventory = set(body_ids) | set(cold_ids)
        for route in self.routes:
            routed = (
                set(route.direct_body_ids)
                | set(route.cold_reference_ids)
                | set(route.omitted_context_ids)
            )
            if routed != inventory:
                raise ContextCapsuleError(
                    f"route {route.node_id} must explicitly disposition every context item"
                )
            if not set(route.direct_body_ids).issubset(body_ids):
                raise ContextCapsuleError("route names an unavailable direct body")
            if not set(route.cold_reference_ids).issubset(cold_ids):
                raise ContextCapsuleError("route names an unavailable cold reference")
        expected = canonical_digest(self.to_document(include_digest=False))
        if not self.capsule_digest:
            object.__setattr__(self, "capsule_digest", expected)
        elif self.capsule_digest != expected:
            raise ContextCapsuleError("capsule digest is invalid")

    def to_document(self, *, include_digest: bool = True) -> dict[str, Any]:
        document: dict[str, Any] = {
            "schema_version": 1,
            "round_id": self.round_id,
            "generation_id": self.generation_id,
            "plan_digest": self.plan_digest,
            "manifest_digest": self.manifest_digest,
            "subject_id": self.subject_id,
            "subject_snapshot_digest": self.subject_snapshot_digest,
            "authority_digest": self.authority_digest,
            "model_route_digest": self.model_route_digest,
            "budget_digest": self.budget_digest,
            "shared_body": self.shared_body.to_document(),
            "direct_bodies": [item.to_document() for item in self.direct_bodies],
            "cold_references": [item.to_document() for item in self.cold_references],
            "routes": [item.to_document() for item in self.routes],
        }
        if include_digest:
            document["capsule_digest"] = self.capsule_digest
        return document

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_document())

    def node_delta(
        self,
        node_id: str,
        *,
        node_contract_digest: str,
        objective_digest: str,
    ) -> NodeDelta:
        require_identifier(node_id, "node_id")
        require_digest(node_contract_digest, "node_contract_digest")
        require_digest(objective_digest, "objective_digest")
        route = next((item for item in self.routes if item.node_id == node_id), None)
        if route is None:
            raise ContextCapsuleError("node has no context route in this capsule")
        direct = {item.context_id: item for item in self.direct_bodies}
        cold = {item.context_id: item for item in self.cold_references}
        return NodeDelta(
            node_id=node_id,
            capsule_digest=self.capsule_digest,
            generation_id=self.generation_id,
            subject_id=self.subject_id,
            authority_digest=self.authority_digest,
            model_route_digest=self.model_route_digest,
            budget_digest=self.budget_digest,
            node_contract_digest=node_contract_digest,
            objective_digest=objective_digest,
            shared_body_digest=self.shared_body.digest,
            direct_bodies=tuple(direct[item] for item in route.direct_body_ids),
            cold_references=tuple(cold[item] for item in route.cold_reference_ids),
            omitted_context_ids=route.omitted_context_ids,
        )


@dataclass(frozen=True, slots=True)
class NodeDelta:
    """The complete context unique to one node; unrelated bodies are absent."""

    node_id: str
    capsule_digest: str
    generation_id: str
    subject_id: str
    authority_digest: str
    model_route_digest: str
    budget_digest: str
    node_contract_digest: str
    objective_digest: str
    shared_body_digest: str
    direct_bodies: tuple[ContextBody, ...]
    cold_references: tuple[ColdContextReference, ...]
    omitted_context_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        require_identifier(self.node_id, "node_id")
        for label in (
            "capsule_digest",
            "generation_id",
            "subject_id",
            "authority_digest",
            "model_route_digest",
            "budget_digest",
            "node_contract_digest",
            "objective_digest",
            "shared_body_digest",
        ):
            require_digest(getattr(self, label), label)
        ids = [item.context_id for item in self.direct_bodies]
        ids.extend(item.context_id for item in self.cold_references)
        ids.extend(self.omitted_context_ids)
        if len(set(ids)) != len(ids):
            raise ContextCapsuleError("node delta contains duplicate context dispositions")

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "node_id": self.node_id,
            "capsule_digest": self.capsule_digest,
            "generation_id": self.generation_id,
            "subject_id": self.subject_id,
            "authority_digest": self.authority_digest,
            "model_route_digest": self.model_route_digest,
            "budget_digest": self.budget_digest,
            "node_contract_digest": self.node_contract_digest,
            "objective_digest": self.objective_digest,
            "shared_body_digest": self.shared_body_digest,
            "direct_bodies": [item.to_document() for item in self.direct_bodies],
            "cold_references": [item.to_document() for item in self.cold_references],
            "omitted_context_ids": list(self.omitted_context_ids),
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())

    @property
    def transmitted_bytes(self) -> int:
        """Bytes unique to the node; the shared body is transmitted once per round."""

        return len(canonical_json_bytes(self.to_document()))


@dataclass(frozen=True, slots=True)
class ContextSavings:
    naive_fanout_bytes: int
    capsule_bytes: int
    delta_bytes: int

    @property
    def optimized_bytes(self) -> int:
        return self.capsule_bytes + self.delta_bytes

    @property
    def saved_bytes(self) -> int:
        return self.naive_fanout_bytes - self.optimized_bytes

    @property
    def materially_lower(self) -> bool:
        return self.saved_bytes > 0 and self.optimized_bytes * 100 <= self.naive_fanout_bytes * 80


def measure_context_savings(
    capsule: RoundCapsule,
    deltas: Sequence[NodeDelta],
    *,
    naive_envelopes: Sequence[bytes],
) -> ContextSavings:
    """Compare exact serialized bytes; estimates are intentionally not accepted."""

    if len(deltas) != len(naive_envelopes) or not deltas:
        raise ContextCapsuleError("comparison requires one naive envelope per node delta")
    if any(delta.capsule_digest != capsule.capsule_digest for delta in deltas):
        raise ContextCapsuleError("comparison mixes context capsules")
    if any(type(value) is not bytes for value in naive_envelopes):
        raise ContextCapsuleError("naive envelopes must be measured immutable bytes")
    return ContextSavings(
        naive_fanout_bytes=sum(len(value) for value in naive_envelopes),
        capsule_bytes=len(capsule.canonical_bytes),
        delta_bytes=sum(delta.transmitted_bytes for delta in deltas),
    )


__all__ = [
    "ColdContextReference",
    "ContextBody",
    "ContextCapsuleError",
    "ContextSavings",
    "NodeContextRoute",
    "NodeDelta",
    "RoundCapsule",
    "measure_context_savings",
]
