"""Immutable wave and candidate-seal contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, Mapping

from .runtime_contracts import (
    ContractViolation,
    WaveState,
    _closed,
    canonical_digest,
    canonical_json_bytes,
    require_digest,
    require_identifier,
    require_time,
    strict_json_object,
)

_GIT_OBJECT = re.compile(r"[0-9a-f]{40}\Z")


class WaveNodeState(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    CHECKPOINTED = "CHECKPOINTED"
    COMPLETED = "COMPLETED"
    RECOVERABLE = "RECOVERABLE"
    REPLAN_REQUIRED = "REPLAN_REQUIRED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class CandidateIdentity:
    commit: str
    tree: str
    subject_id: str

    def __post_init__(self) -> None:
        if (
            _GIT_OBJECT.fullmatch(self.commit) is None
            or _GIT_OBJECT.fullmatch(self.tree) is None
        ):
            raise ContractViolation(
                "candidate identity requires lowercase 40-hex commit and tree"
            )
        require_digest(self.subject_id, "candidate subject_id")

    def to_document(self) -> dict[str, str]:
        return {"commit": self.commit, "tree": self.tree, "subject_id": self.subject_id}

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "CandidateIdentity":
        _closed(document, {"commit", "tree", "subject_id"}, "candidate identity")
        return cls(document["commit"], document["tree"], document["subject_id"])

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())


@dataclass(frozen=True, slots=True)
class WaveNode:
    node_id: str
    state: WaveNodeState
    attempt: int
    checkpoint_digest: str | None
    result_digest: str | None

    def __post_init__(self) -> None:
        require_identifier(self.node_id, "wave node_id")
        if not isinstance(self.state, WaveNodeState):
            raise ContractViolation("wave node state must be typed")
        if type(self.attempt) is not int or self.attempt < 0:
            raise ContractViolation("wave node attempt must be a non-negative integer")
        for value, label in (
            (self.checkpoint_digest, "checkpoint_digest"),
            (self.result_digest, "result_digest"),
        ):
            if value is not None:
                require_digest(value, label)
        if self.state is WaveNodeState.CHECKPOINTED and self.checkpoint_digest is None:
            raise ContractViolation("CHECKPOINTED node requires a checkpoint digest")
        if self.state is WaveNodeState.COMPLETED and self.result_digest is None:
            raise ContractViolation("COMPLETED node requires a result digest")

    def to_document(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "state": self.state.value,
            "attempt": self.attempt,
            "checkpoint_digest": self.checkpoint_digest,
            "result_digest": self.result_digest,
        }


@dataclass(frozen=True, slots=True)
class WaveManifest:
    schema_version: int
    wave_id: str
    plan_digest: str
    generation_id: str
    subject_id: str
    parent_wave_digest: str | None
    state: WaveState
    nodes: tuple[WaveNode, ...]
    checkpoint_digest: str | None
    candidate: CandidateIdentity | None
    created_at: str
    manifest_digest: str = ""

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ContractViolation("unsupported wave-manifest schema version")
        require_identifier(self.wave_id, "wave_id")
        require_digest(self.plan_digest, "plan_digest")
        require_digest(self.generation_id, "generation_id")
        require_digest(self.subject_id, "subject_id")
        if self.parent_wave_digest is not None:
            require_digest(self.parent_wave_digest, "parent_wave_digest")
        if not isinstance(self.state, WaveState):
            raise ContractViolation("wave state must be typed")
        if not self.nodes or len({node.node_id for node in self.nodes}) != len(
            self.nodes
        ):
            raise ContractViolation("wave nodes are required and must be unique")
        if self.checkpoint_digest is not None:
            require_digest(self.checkpoint_digest, "wave checkpoint_digest")
        require_time(self.created_at, "wave created_at")
        checkpoint_states = {
            WaveState.CHECKPOINTED,
            WaveState.CANDIDATE_SEALED,
            WaveState.VERIFYING,
            WaveState.INTEGRATION_READY,
            WaveState.INTEGRATED,
        }
        candidate_states = {
            WaveState.CANDIDATE_SEALED,
            WaveState.VERIFYING,
            WaveState.INTEGRATION_READY,
            WaveState.INTEGRATED,
        }
        if self.state in checkpoint_states and self.checkpoint_digest is None:
            raise ContractViolation(
                f"{self.state.value} wave requires a checkpoint digest"
            )
        if self.state in candidate_states and self.candidate is None:
            raise ContractViolation(
                f"{self.state.value} wave requires a sealed candidate"
            )
        if self.candidate is not None and self.candidate.subject_id != self.subject_id:
            raise ContractViolation("candidate subject differs from wave subject")
        if (
            self.state in {WaveState.PLANNED, WaveState.RUNNING, WaveState.CHECKPOINTED}
            and self.candidate is not None
        ):
            raise ContractViolation("candidate cannot exist before CANDIDATE_SEALED")
        expected = canonical_digest(self.to_document(include_digest=False))
        if not self.manifest_digest:
            object.__setattr__(self, "manifest_digest", expected)
        elif self.manifest_digest != expected:
            raise ContractViolation("wave manifest digest is invalid")

    def to_document(self, *, include_digest: bool = True) -> dict[str, Any]:
        document: dict[str, Any] = {
            "schema_version": self.schema_version,
            "wave_id": self.wave_id,
            "plan_digest": self.plan_digest,
            "generation_id": self.generation_id,
            "subject_id": self.subject_id,
            "parent_wave_digest": self.parent_wave_digest,
            "state": self.state.value,
            "nodes": [node.to_document() for node in self.nodes],
            "checkpoint_digest": self.checkpoint_digest,
            "candidate": None
            if self.candidate is None
            else self.candidate.to_document(),
            "created_at": self.created_at,
        }
        if include_digest:
            document["manifest_digest"] = self.manifest_digest
        return document

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_document())

    @classmethod
    def from_bytes(cls, raw: bytes) -> "WaveManifest":
        return cls.from_document(strict_json_object(raw))

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "WaveManifest":
        fields = {
            "schema_version",
            "wave_id",
            "plan_digest",
            "generation_id",
            "subject_id",
            "parent_wave_digest",
            "state",
            "nodes",
            "checkpoint_digest",
            "candidate",
            "created_at",
            "manifest_digest",
        }
        _closed(document, fields, "wave manifest")
        if not isinstance(document["nodes"], list) or any(
            not isinstance(item, Mapping) for item in document["nodes"]
        ):
            raise ContractViolation("wave nodes must be an object list")
        nodes: list[WaveNode] = []
        for item in document["nodes"]:
            _closed(
                item,
                {"node_id", "state", "attempt", "checkpoint_digest", "result_digest"},
                "wave node",
            )
            try:
                state = WaveNodeState(item["state"])
            except (TypeError, ValueError) as error:
                raise ContractViolation("unsupported wave node state") from error
            nodes.append(
                WaveNode(
                    item["node_id"],
                    state,
                    item["attempt"],
                    item["checkpoint_digest"],
                    item["result_digest"],
                )
            )
        candidate = None
        if document["candidate"] is not None:
            item = document["candidate"]
            if not isinstance(item, Mapping):
                raise ContractViolation("candidate must be an object")
            candidate = CandidateIdentity.from_document(item)
        try:
            state = WaveState(document["state"])
        except (TypeError, ValueError) as error:
            raise ContractViolation("unsupported wave state") from error
        return cls(
            document["schema_version"],
            document["wave_id"],
            document["plan_digest"],
            document["generation_id"],
            document["subject_id"],
            document["parent_wave_digest"],
            state,
            tuple(nodes),
            document["checkpoint_digest"],
            candidate,
            document["created_at"],
            document["manifest_digest"],
        )

    def transition(
        self,
        state: WaveState,
        *,
        nodes: tuple[WaveNode, ...] | None = None,
        checkpoint_digest: str | None = None,
        candidate: CandidateIdentity | None = None,
        created_at: str,
    ) -> "WaveManifest":
        if state not in _ALLOWED_TRANSITIONS[self.state]:
            raise ContractViolation(
                f"invalid wave transition {self.state.value} -> {state.value}"
            )
        return replace(
            self,
            parent_wave_digest=self.manifest_digest,
            state=state,
            nodes=self.nodes if nodes is None else nodes,
            checkpoint_digest=self.checkpoint_digest
            if checkpoint_digest is None
            else checkpoint_digest,
            candidate=self.candidate if candidate is None else candidate,
            created_at=created_at,
            manifest_digest="",
        )


_ALLOWED_TRANSITIONS: dict[WaveState, frozenset[WaveState]] = {
    WaveState.PLANNED: frozenset({WaveState.RUNNING, WaveState.CANCELLED}),
    WaveState.RUNNING: frozenset(
        {
            WaveState.CHECKPOINTED,
            WaveState.RECOVERABLE,
            WaveState.REPLAN_REQUIRED,
            WaveState.FAILED,
            WaveState.CANCELLED,
        }
    ),
    WaveState.CHECKPOINTED: frozenset(
        {
            WaveState.RUNNING,
            WaveState.CANDIDATE_SEALED,
            WaveState.RECOVERABLE,
            WaveState.REPLAN_REQUIRED,
            WaveState.FAILED,
            WaveState.CANCELLED,
        }
    ),
    WaveState.CANDIDATE_SEALED: frozenset(
        {WaveState.VERIFYING, WaveState.REPLAN_REQUIRED, WaveState.FAILED}
    ),
    WaveState.VERIFYING: frozenset(
        {WaveState.INTEGRATION_READY, WaveState.REPLAN_REQUIRED, WaveState.FAILED}
    ),
    WaveState.INTEGRATION_READY: frozenset(
        {WaveState.INTEGRATED, WaveState.REPLAN_REQUIRED, WaveState.FAILED}
    ),
    WaveState.RECOVERABLE: frozenset(
        {
            WaveState.RUNNING,
            WaveState.REPLAN_REQUIRED,
            WaveState.FAILED,
            WaveState.CANCELLED,
        }
    ),
    WaveState.REPLAN_REQUIRED: frozenset(),
    WaveState.INTEGRATED: frozenset(),
    WaveState.FAILED: frozenset(),
    WaveState.CANCELLED: frozenset(),
}


__all__ = [
    "CandidateIdentity",
    "WaveManifest",
    "WaveNode",
    "WaveNodeState",
    "WaveState",
]
