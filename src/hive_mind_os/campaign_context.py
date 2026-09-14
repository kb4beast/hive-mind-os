"""N05: campaign-scoped immutable context assembly.

This is intentionally a compiler, not a store.  Callers supply only already-admitted
facts; the resulting packet contains no authority to fetch arbitrary repository data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .context_capsule import ColdContextReference, ContextBody, NodeDelta, RoundCapsule
from .runtime_contracts import canonical_digest, require_digest, require_identifier


class CampaignContextError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CampaignContextRequest:
    subject_id: str
    subject_snapshot_digest: str
    node_id: str
    node_contract_digest: str
    objective_digest: str
    role_purpose: str
    permitted_handles: tuple[str, ...]

    def __post_init__(self) -> None:
        require_identifier(self.subject_id, "subject_id")
        require_identifier(self.node_id, "node_id")
        require_identifier(self.role_purpose, "role_purpose")
        for value in (
            self.subject_snapshot_digest,
            self.node_contract_digest,
            self.objective_digest,
        ):
            require_digest(value, "request digest")
        if not self.permitted_handles or len(set(self.permitted_handles)) != len(
            self.permitted_handles
        ):
            raise CampaignContextError("handles must be a nonempty unique tuple")


@dataclass(frozen=True, slots=True)
class ContextSelectionReceipt:
    request_digest: str
    selected_ids: tuple[str, ...]
    cold_ids: tuple[str, ...]
    omitted_ids: tuple[str, ...]
    reason: str

    @property
    def digest(self) -> str:
        return canonical_digest(
            self.__dict__
            if hasattr(self, "__dict__")
            else {
                "request_digest": self.request_digest,
                "selected_ids": self.selected_ids,
                "cold_ids": self.cold_ids,
                "omitted_ids": self.omitted_ids,
                "reason": self.reason,
            }
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "request_digest": self.request_digest,
            "selected_ids": list(self.selected_ids),
            "cold_ids": list(self.cold_ids),
            "omitted_ids": list(self.omitted_ids),
            "reason": self.reason,
            "receipt_digest": self.digest,
        }


def assemble_campaign_delta(
    capsule: RoundCapsule, request: CampaignContextRequest
) -> tuple[NodeDelta, ContextSelectionReceipt]:
    if (
        capsule.subject_id != request.subject_id
        or capsule.subject_snapshot_digest != request.subject_snapshot_digest
    ):
        raise CampaignContextError("cross-subject or stale snapshot context request")
    delta = capsule.node_delta(
        request.node_id,
        node_contract_digest=request.node_contract_digest,
        objective_digest=request.objective_digest,
    )
    permitted = set(request.permitted_handles)
    visible = {item.context_id for item in delta.direct_bodies} | {
        item.context_id for item in delta.cold_references
    }
    if not visible.issubset(permitted):
        raise CampaignContextError("capsule exposes an unpermitted handle")
    receipt = ContextSelectionReceipt(
        canonical_digest(
            {
                "subject": request.subject_id,
                "node": request.node_id,
                "contract": request.node_contract_digest,
                "purpose": request.role_purpose,
            }
        ),
        tuple(x.context_id for x in delta.direct_bodies),
        tuple(x.context_id for x in delta.cold_references),
        delta.omitted_context_ids,
        "frozen capsule route",
    )
    return delta, receipt


def expand_cold_reference(
    delta: NodeDelta, reference: ColdContextReference, body: ContextBody, *, reason: str
) -> NodeDelta:
    """Return a new delta only when a content-addressed cold object was supplied."""
    if not reason.strip() or reference.context_id not in {
        x.context_id for x in delta.cold_references
    }:
        raise CampaignContextError("cold reference is not admitted for this delta")
    if (
        reference.context_id != body.context_id
        or reference.digest != body.digest
        or reference.byte_count != len(body.body)
    ):
        raise CampaignContextError("cold body does not match its reference")
    if body.context_id in {x.context_id for x in delta.direct_bodies}:
        raise CampaignContextError("cold body was already expanded")
    return NodeDelta(
        delta.node_id,
        delta.capsule_digest,
        delta.generation_id,
        delta.subject_id,
        delta.authority_digest,
        delta.model_route_digest,
        delta.budget_digest,
        delta.node_contract_digest,
        delta.objective_digest,
        delta.shared_body_digest,
        delta.direct_bodies + (body,),
        tuple(x for x in delta.cold_references if x.context_id != reference.context_id),
        delta.omitted_context_ids,
    )
