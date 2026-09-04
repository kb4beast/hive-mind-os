"""Bounded, dependency-ready execution for the eight repository specialists.

This module is deliberately additive.  It does not reinterpret the sealed v1
tournament and it does not claim that an in-process Python boundary is an OS
sandbox.  Handlers receive a distinct workspace, all observable workspace
writes are checked after execution, and the resulting limitation is carried in
every receipt.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import re
import stat
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Awaitable, Callable, Mapping, Protocol, Sequence, cast

from .artifacts import ArtifactStore, StoredArtifact
from .canonical import canonical_bytes, canonical_digest
from .contracts import normalize_portable_path

SPECIALIST_ROLES = (
    "orchestrator",
    "explorer",
    "architect",
    "builder",
    "curator",
    "integrator",
    "steward",
    "optimizer",
)
ISOLATION_ASSURANCE = (
    "isolated-node-workspace-with-post-execution-scope-validation;"
    "cooperative-in-process-boundary-not-an-os-sandbox"
)
_NODE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


class DagValidationError(ValueError):
    """The requested DAG cannot be executed without weakening an invariant."""


class WorkspaceViolation(RuntimeError):
    """A handler produced an observable write outside its declared boundary."""


class NativeEvidenceRequired(RuntimeError):
    """A generic or misbound handler cannot satisfy a specialist node."""


class NodeStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ArtifactType:
    """The exact schema and media type a node promises to produce."""

    schema_id: str
    schema_version: str
    schema_digest: str
    media_type: str = "application/json"

    def __post_init__(self) -> None:
        for value, label in (
            (self.schema_id, "artifact schema id"),
            (self.schema_version, "artifact schema version"),
            (self.media_type, "artifact media type"),
        ):
            if (
                not isinstance(value, str)
                or not value.strip()
                or value != value.strip()
            ):
                raise DagValidationError(f"{label} must be an exact non-empty string")
        if (
            not isinstance(self.schema_digest, str)
            or _DIGEST.fullmatch(self.schema_digest) is None
        ):
            raise DagValidationError(
                "artifact schema digest must be lowercase sha256:<64 hex>"
            )

    def to_document(self) -> dict[str, str]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "schema_digest": self.schema_digest,
            "media_type": self.media_type,
        }


@dataclass(frozen=True, slots=True)
class ArtifactRequirement:
    """A typed edge from one producer node to one consumer node."""

    producer_node_id: str
    schema_id: str
    schema_version: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.producer_node_id, "artifact producer node id"),
            (self.schema_id, "required artifact schema id"),
            (self.schema_version, "required artifact schema version"),
        ):
            if (
                not isinstance(value, str)
                or not value.strip()
                or value != value.strip()
            ):
                raise DagValidationError(f"{label} must be an exact non-empty string")

    def to_document(self) -> dict[str, str]:
        return {
            "producer_node_id": self.producer_node_id,
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class DagNode:
    """One bounded specialist invocation and its complete artifact contract."""

    node_id: str
    role: str
    executor_id: str
    dependencies: tuple[str, ...]
    required_artifacts: tuple[ArtifactRequirement, ...]
    produces: ArtifactType
    write_scope: tuple[str, ...] = ()
    timeout_seconds: float = 60.0
    native_symbol: str = ""
    requires_native_evidence: bool = True

    def __post_init__(self) -> None:
        if (
            not isinstance(self.node_id, str)
            or _NODE_ID.fullmatch(self.node_id) is None
        ):
            raise DagValidationError("node id must be a portable identifier")
        if self.role not in SPECIALIST_ROLES:
            raise DagValidationError(f"unknown specialist role: {self.role}")
        if (
            not isinstance(self.executor_id, str)
            or not self.executor_id.strip()
            or self.executor_id != self.executor_id.strip()
        ):
            raise DagValidationError(
                "executor identity must be an exact non-empty string"
            )
        dependencies = tuple(self.dependencies)
        if len(set(dependencies)) != len(dependencies) or any(
            not isinstance(value, str) or _NODE_ID.fullmatch(value) is None
            for value in dependencies
        ):
            raise DagValidationError(
                "node dependencies must be unique portable node ids"
            )
        object.__setattr__(self, "dependencies", dependencies)
        requirements = tuple(self.required_artifacts)
        if any(not isinstance(value, ArtifactRequirement) for value in requirements):
            raise DagValidationError("required artifacts must be typed requirements")
        if len({value.producer_node_id for value in requirements}) != len(requirements):
            raise DagValidationError(
                "each dependency must have exactly one typed artifact requirement"
            )
        object.__setattr__(self, "required_artifacts", requirements)
        if not isinstance(self.produces, ArtifactType):
            raise DagValidationError("node must declare its produced artifact type")
        try:
            normalized_scope = tuple(
                normalize_portable_path(value) for value in self.write_scope
            )
        except (TypeError, ValueError) as error:
            raise DagValidationError(
                "write scope must contain confined portable paths"
            ) from error
        if len(set(normalized_scope)) != len(normalized_scope):
            raise DagValidationError("write scope paths must be unique")
        object.__setattr__(self, "write_scope", normalized_scope)
        if (
            not isinstance(self.timeout_seconds, (int, float))
            or isinstance(self.timeout_seconds, bool)
            or not 0 < self.timeout_seconds <= 300
        ):
            raise DagValidationError(
                "node timeout must be greater than zero and at most 300 seconds"
            )
        if self.requires_native_evidence and (
            not isinstance(self.native_symbol, str)
            or not self.native_symbol.strip()
            or self.native_symbol != self.native_symbol.strip()
        ):
            raise DagValidationError(
                "native specialist nodes must name the concrete symbol they exercise"
            )
        if type(self.requires_native_evidence) is not bool:
            raise DagValidationError("requires_native_evidence must be boolean")

    def to_document(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "role": self.role,
            "executor_id": self.executor_id,
            "dependencies": list(self.dependencies),
            "required_artifacts": [
                value.to_document() for value in self.required_artifacts
            ],
            "produces": self.produces.to_document(),
            "write_scope": list(self.write_scope),
            "timeout_seconds": self.timeout_seconds,
            "native_symbol": self.native_symbol,
            "requires_native_evidence": self.requires_native_evidence,
        }


@dataclass(frozen=True, slots=True)
class DagPlan:
    """A complete eight-role DAG with deterministic validation and identity."""

    plan_id: str
    nodes: tuple[DagNode, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise DagValidationError("unsupported specialist DAG schema version")
        if (
            not isinstance(self.plan_id, str)
            or not self.plan_id.strip()
            or self.plan_id != self.plan_id.strip()
        ):
            raise DagValidationError("plan id must be an exact non-empty string")
        nodes = tuple(self.nodes)
        if any(not isinstance(node, DagNode) for node in nodes):
            raise DagValidationError("plan nodes must be DagNode values")
        by_id = {node.node_id: node for node in nodes}
        if len(by_id) != len(nodes):
            raise DagValidationError("node ids must be unique")
        roles = tuple(node.role for node in nodes)
        missing = sorted(set(SPECIALIST_ROLES) - set(roles))
        duplicates = sorted(role for role in set(roles) if roles.count(role) > 1)
        extras = sorted(set(roles) - set(SPECIALIST_ROLES))
        if missing or duplicates or extras or len(nodes) != len(SPECIALIST_ROLES):
            raise DagValidationError(
                "plan must contain every specialist role exactly once "
                f"(missing={missing}, duplicates={duplicates}, extras={extras})"
            )
        executor_ids = tuple(node.executor_id for node in nodes)
        if len(set(executor_ids)) != len(executor_ids):
            raise DagValidationError("every node requires a unique executor identity")
        builder = next(node for node in nodes if node.role == "builder")
        curator = next(node for node in nodes if node.role == "curator")
        if (
            builder.executor_id == curator.executor_id
        ):  # defensive clarity beyond global uniqueness
            raise DagValidationError(
                "Curator identity must be separate from Builder identity"
            )
        for node in nodes:
            unknown = sorted(set(node.dependencies) - set(by_id))
            if unknown or node.node_id in node.dependencies:
                raise DagValidationError(
                    f"node {node.node_id} has unknown or self dependencies: {unknown}"
                )
            requirement_sources = {
                value.producer_node_id for value in node.required_artifacts
            }
            if requirement_sources != set(node.dependencies):
                raise DagValidationError(
                    f"node {node.node_id} must type every dependency exactly once"
                )
            for requirement in node.required_artifacts:
                produced = by_id[requirement.producer_node_id].produces
                if (requirement.schema_id, requirement.schema_version) != (
                    produced.schema_id,
                    produced.schema_version,
                ):
                    raise DagValidationError(
                        f"node {node.node_id} requires an artifact type its dependency does not produce"
                    )
        order = _topological_order(by_id)
        ancestors = _ancestor_sets(by_id, order)
        for index, left in enumerate(nodes):
            for right in nodes[index + 1 :]:
                if not _scopes_overlap(left.write_scope, right.write_scope):
                    continue
                ordered = (
                    left.node_id in ancestors[right.node_id]
                    or right.node_id in ancestors[left.node_id]
                )
                if not ordered:
                    raise DagValidationError(
                        "overlapping write scopes require a dependency path: "
                        f"{left.node_id}, {right.node_id}"
                    )
        object.__setattr__(self, "nodes", nodes)

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())

    @property
    def topological_order(self) -> tuple[str, ...]:
        return _topological_order({node.node_id: node for node in self.nodes})

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "nodes": [
                node.to_document()
                for node in sorted(self.nodes, key=lambda value: value.node_id)
            ],
        }


@dataclass(frozen=True, slots=True)
class SpecialistResult:
    """A handler result; the coordinator owns artifact persistence and ordering."""

    content: object
    native_evidence: bool
    invoked_symbol: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.native_evidence) is not bool:
            raise TypeError("native_evidence must be boolean")
        if not isinstance(self.invoked_symbol, str):
            raise TypeError("invoked_symbol must be text")
        if any(
            not isinstance(value, str) or not value.strip()
            for value in self.evidence_refs
        ):
            raise ValueError("evidence references must be non-empty strings")
        _result_bytes(self.content)


@dataclass(frozen=True, slots=True)
class SpecialistContext:
    """The immutable inputs and confined workspace supplied to one specialist."""

    plan_digest: str
    candidate_digest: str
    node: DagNode
    workspace: Path
    workspaces_root: Path
    artifacts: Mapping[str, StoredArtifact]

    def artifact_for(self, producer_node_id: str) -> StoredArtifact:
        try:
            return self.artifacts[producer_node_id]
        except KeyError as error:
            raise KeyError(
                f"node has no artifact dependency from {producer_node_id}"
            ) from error

    def confined_path(self, relative_path: str) -> Path:
        try:
            normalized = normalize_portable_path(relative_path)
        except (TypeError, ValueError) as error:
            raise WorkspaceViolation(
                "workspace path must be confined and portable"
            ) from error
        result = (self.workspace / Path(*normalized.split("/"))).resolve()
        try:
            result.relative_to(self.workspace.resolve())
        except ValueError as error:
            raise WorkspaceViolation(
                "workspace path escapes the node workspace"
            ) from error
        return result

    def write_text(self, relative_path: str, content: str) -> Path:
        """A cooperative convenience; independent post-validation is still applied."""

        path = self.confined_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path


SpecialistHandler = Callable[
    [SpecialistContext], SpecialistResult | Awaitable[SpecialistResult]
]


class SpecialistHandlerRegistry(Protocol):
    def handler_for(self, role: str) -> SpecialistHandler: ...


@dataclass(frozen=True, slots=True)
class NodeReceipt:
    """Canonical outcome evidence for one logical node invocation."""

    plan_digest: str
    candidate_digest: str
    node_id: str
    role: str
    executor_id: str
    status: NodeStatus
    dependency_artifact_digests: tuple[str, ...]
    artifact_digest: str | None
    native_evidence: bool
    invoked_symbol: str | None
    written_paths: tuple[str, ...]
    error_type: str | None
    error_message: str | None
    isolation_assurance: str = ISOLATION_ASSURANCE

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", NodeStatus(self.status))
        if (
            tuple(sorted(set(self.dependency_artifact_digests)))
            != self.dependency_artifact_digests
        ):
            raise ValueError("receipt dependency artifacts must be sorted and unique")
        if tuple(sorted(set(self.written_paths))) != self.written_paths:
            raise ValueError("receipt written paths must be sorted and unique")
        if self.status is NodeStatus.SUCCEEDED:
            if (
                self.artifact_digest is None
                or self.error_type is not None
                or self.error_message is not None
            ):
                raise ValueError("successful receipt requires an artifact and no error")
        elif self.artifact_digest is not None:
            raise ValueError("failed or blocked receipts cannot claim an artifact")
        if type(self.native_evidence) is not bool:
            raise ValueError("receipt native evidence must be boolean")
        if self.isolation_assurance != ISOLATION_ASSURANCE:
            raise ValueError("receipt must preserve the exact isolation limitation")

    @property
    def receipt_digest(self) -> str:
        return canonical_digest(self.to_document())

    def to_document(self) -> dict[str, object]:
        return {
            "plan_digest": self.plan_digest,
            "candidate_digest": self.candidate_digest,
            "node_id": self.node_id,
            "role": self.role,
            "executor_id": self.executor_id,
            "status": self.status.value,
            "dependency_artifact_digests": list(self.dependency_artifact_digests),
            "artifact_digest": self.artifact_digest,
            "native_evidence": self.native_evidence,
            "invoked_symbol": self.invoked_symbol,
            "written_paths": list(self.written_paths),
            "error_type": self.error_type,
            "error_message": self.error_message,
            "isolation_assurance": self.isolation_assurance,
        }


@dataclass(frozen=True, slots=True)
class DagEvent:
    sequence: int
    node_id: str
    event_type: str
    receipt_digest: str
    previous_digest: str | None
    event_digest: str

    @classmethod
    def create(
        cls,
        *,
        sequence: int,
        receipt: NodeReceipt,
        previous_digest: str | None,
    ) -> DagEvent:
        event_type = f"node.{receipt.status.value}"
        material = {
            "sequence": sequence,
            "node_id": receipt.node_id,
            "event_type": event_type,
            "receipt_digest": receipt.receipt_digest,
            "previous_digest": previous_digest,
        }
        return cls(
            sequence,
            receipt.node_id,
            event_type,
            receipt.receipt_digest,
            previous_digest,
            canonical_digest(material),
        )


@dataclass(frozen=True, slots=True)
class DagRunResult:
    plan_digest: str
    candidate_digest: str
    receipts: tuple[NodeReceipt, ...]
    events: tuple[DagEvent, ...]
    logical_digest: str
    max_observed_parallelism: int

    def receipt_for(self, node_id: str) -> NodeReceipt:
        try:
            return next(value for value in self.receipts if value.node_id == node_id)
        except StopIteration as error:
            raise KeyError(node_id) from error


@dataclass(frozen=True, slots=True)
class _Attempt:
    node: DagNode
    result: SpecialistResult | None
    written_paths: tuple[str, ...]
    error_type: str | None = None
    error_message: str | None = None


class ExecutableDagRuntime:
    """Execute dependency-ready nodes and then derive one canonical receipt chain."""

    def __init__(
        self,
        run_root: str | Path,
        *,
        candidate_digest: str,
        artifact_store: ArtifactStore | None = None,
        max_concurrency: int = 8,
    ) -> None:
        if (
            not isinstance(candidate_digest, str)
            or _DIGEST.fullmatch(candidate_digest) is None
        ):
            raise DagValidationError(
                "candidate digest must be lowercase sha256:<64 hex>"
            )
        if type(max_concurrency) is not int or not 1 <= max_concurrency <= 8:
            raise DagValidationError("max_concurrency must be between one and eight")
        self.run_root = Path(run_root).resolve()
        self.workspaces_root = self.run_root / "workspaces"
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.workspaces_root.mkdir(parents=True, exist_ok=True)
        self.candidate_digest = candidate_digest
        self.artifact_store = artifact_store or ArtifactStore(
            self.run_root / "evidence"
        )
        self.max_concurrency = max_concurrency
        self._completed: dict[str, dict[str, NodeReceipt]] = {}

    async def run(
        self,
        plan: DagPlan,
        handlers: SpecialistHandlerRegistry | Mapping[str, SpecialistHandler],
        *,
        resume_receipts: Sequence[NodeReceipt] = (),
    ) -> DagRunResult:
        if not isinstance(plan, DagPlan):
            raise DagValidationError("runtime requires a validated DagPlan")
        by_id = {node.node_id: node for node in plan.nodes}
        order = plan.topological_order
        receipts: dict[str, NodeReceipt] = {}
        artifacts: dict[str, StoredArtifact] = {}
        saved = dict(self._completed.get(plan.digest, {}))
        for receipt in resume_receipts:
            previous_receipt = saved.setdefault(receipt.node_id, receipt)
            if previous_receipt != receipt:
                raise DagValidationError("conflicting resume receipts for one node")
        for node_id in order:
            receipt = saved.get(node_id)
            if receipt is None:
                continue
            node = by_id[node_id]
            missing_dependencies = tuple(
                dependency
                for dependency in node.dependencies
                if dependency not in receipts
            )
            if missing_dependencies:
                raise DagValidationError(
                    f"resume receipt set is not dependency-closed for {node_id}: "
                    + ", ".join(missing_dependencies)
                )
            artifact = self._validate_resumed_receipt(plan, node, receipt)
            if receipt.dependency_artifact_digests != _dependency_digests(
                node, artifacts
            ):
                raise DagValidationError(
                    f"resume receipt dependency artifacts do not bind node {node_id}"
                )
            receipts[node_id] = receipt
            artifacts[node_id] = artifact

        for node in plan.nodes:
            workspace = self.workspaces_root / node.node_id
            if node.node_id in receipts:
                continue
            if workspace.exists() and any(workspace.iterdir()):
                raise DagValidationError(
                    f"fresh node workspace is not empty: {node.node_id}"
                )
            workspace.mkdir(parents=True, exist_ok=True)

        pending = set(by_id) - set(receipts)
        running: dict[asyncio.Task[_Attempt], str] = {}
        active = 0
        peak = 0

        async def invoke(node: DagNode) -> _Attempt:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                return await self._attempt(
                    plan,
                    node,
                    handlers,
                    artifacts,
                    allowed_workspace_ids=frozenset(by_id),
                )
            finally:
                active -= 1

        while pending or running:
            changed = True
            while changed:
                changed = False
                for node_id in sorted(tuple(pending)):
                    node = by_id[node_id]
                    failed_dependencies = tuple(
                        dependency
                        for dependency in node.dependencies
                        if dependency in receipts
                        and receipts[dependency].status is not NodeStatus.SUCCEEDED
                    )
                    if not failed_dependencies:
                        continue
                    dependency_digests = _dependency_digests(node, artifacts)
                    receipts[node_id] = NodeReceipt(
                        plan.digest,
                        self.candidate_digest,
                        node.node_id,
                        node.role,
                        node.executor_id,
                        NodeStatus.BLOCKED,
                        dependency_digests,
                        None,
                        False,
                        None,
                        (),
                        "DependencyFailed",
                        "blocked by adverse dependency receipts: "
                        + ", ".join(sorted(failed_dependencies)),
                    )
                    pending.remove(node_id)
                    changed = True

            ready = [
                by_id[node_id]
                for node_id in sorted(pending)
                if all(
                    dependency in receipts
                    and receipts[dependency].status is NodeStatus.SUCCEEDED
                    for dependency in by_id[node_id].dependencies
                )
            ]
            capacity = self.max_concurrency - len(running)
            for node in ready[:capacity]:
                pending.remove(node.node_id)
                task = asyncio.create_task(
                    invoke(node), name=f"specialist:{node.node_id}"
                )
                running[task] = node.node_id

            if not running:
                if pending:
                    raise DagValidationError(
                        "DAG scheduler reached an impossible dependency state"
                    )
                break
            completed, _ = await asyncio.wait(
                tuple(running), return_when=asyncio.FIRST_COMPLETED
            )
            attempts: list[_Attempt] = []
            for task in completed:
                running.pop(task)
                attempts.append(task.result())
            for attempt in sorted(attempts, key=lambda value: value.node.node_id):
                receipt, artifact = self._commit_attempt(plan, attempt, artifacts)
                receipts[attempt.node.node_id] = receipt
                if artifact is not None:
                    artifacts[attempt.node.node_id] = artifact

        ordered_receipts = tuple(receipts[node_id] for node_id in order)
        events: list[DagEvent] = []
        previous: str | None = None
        for sequence, receipt in enumerate(ordered_receipts, start=1):
            event = DagEvent.create(
                sequence=sequence,
                receipt=receipt,
                previous_digest=previous,
            )
            events.append(event)
            previous = event.event_digest
        logical_digest = canonical_digest(
            {
                "plan_digest": plan.digest,
                "candidate_digest": self.candidate_digest,
                "event_digests": [event.event_digest for event in events],
            }
        )
        self._completed[plan.digest] = {
            receipt.node_id: receipt
            for receipt in ordered_receipts
            if receipt.status is NodeStatus.SUCCEEDED
        }
        return DagRunResult(
            plan.digest,
            self.candidate_digest,
            ordered_receipts,
            tuple(events),
            logical_digest,
            peak,
        )

    async def _attempt(
        self,
        plan: DagPlan,
        node: DagNode,
        handlers: SpecialistHandlerRegistry | Mapping[str, SpecialistHandler],
        artifacts: Mapping[str, StoredArtifact],
        *,
        allowed_workspace_ids: frozenset[str],
    ) -> _Attempt:
        workspace = (self.workspaces_root / node.node_id).resolve()
        inputs = {
            requirement.producer_node_id: artifacts[requirement.producer_node_id]
            for requirement in node.required_artifacts
        }
        context = SpecialistContext(
            plan.digest,
            self.candidate_digest,
            node,
            workspace,
            self.workspaces_root,
            MappingProxyType(inputs),
        )
        unexpected_before = frozenset(
            _unexpected_workspace_entries(self.workspaces_root, allowed_workspace_ids)
        )
        run_entries_before = frozenset(_unexpected_run_entries(self.run_root))
        try:
            handler = _resolve_handler(handlers, node.role)
            result = await asyncio.wait_for(
                _invoke_handler(handler, context), timeout=float(node.timeout_seconds)
            )
            if not isinstance(result, SpecialistResult):
                raise TypeError("specialist handler must return SpecialistResult")
            if node.requires_native_evidence and (
                not result.native_evidence
                or result.invoked_symbol != node.native_symbol
            ):
                raise NativeEvidenceRequired(
                    f"{node.role} requires direct evidence from {node.native_symbol}"
                )
            written_paths = _snapshot_workspace(workspace)
            outside = tuple(
                path
                for path in written_paths
                if not _path_in_scope(path, node.write_scope)
            )
            unexpected = tuple(
                value
                for value in _unexpected_workspace_entries(
                    self.workspaces_root, allowed_workspace_ids
                )
                if value not in unexpected_before
            )
            run_escapes = tuple(
                value
                for value in _unexpected_run_entries(self.run_root)
                if value not in run_entries_before
            )
            if outside or unexpected or run_escapes:
                details = []
                if outside:
                    details.append("out-of-scope paths: " + ", ".join(outside))
                if unexpected:
                    details.append("workspace-root escapes: " + ", ".join(unexpected))
                if run_escapes:
                    details.append("run-root escapes: " + ", ".join(run_escapes))
                raise WorkspaceViolation("; ".join(details))
            return _Attempt(node, result, written_paths)
        except BaseException as error:
            if isinstance(
                error, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)
            ):
                raise
            try:
                written_paths = _snapshot_workspace(workspace)
            except Exception:
                written_paths = ()
            return _Attempt(
                node,
                None,
                written_paths,
                type(error).__name__,
                _stable_error_message(error),
            )

    def _commit_attempt(
        self,
        plan: DagPlan,
        attempt: _Attempt,
        artifacts: Mapping[str, StoredArtifact],
    ) -> tuple[NodeReceipt, StoredArtifact | None]:
        node = attempt.node
        dependency_digests = _dependency_digests(node, artifacts)
        if attempt.result is None:
            return (
                NodeReceipt(
                    plan.digest,
                    self.candidate_digest,
                    node.node_id,
                    node.role,
                    node.executor_id,
                    NodeStatus.FAILED,
                    dependency_digests,
                    None,
                    False,
                    None,
                    attempt.written_paths,
                    attempt.error_type,
                    attempt.error_message,
                ),
                None,
            )
        result = attempt.result
        envelope = self.artifact_store.put(
            _result_bytes(result.content),
            media_type=node.produces.media_type,
            candidate_digest=self.candidate_digest,
            dependency_digests=dependency_digests,
            schema_id=node.produces.schema_id,
            schema_version=node.produces.schema_version,
            schema_digest=node.produces.schema_digest,
            producer_id=node.executor_id,
        )
        stored = self.artifact_store.read(envelope.artifact_digest)
        return (
            NodeReceipt(
                plan.digest,
                self.candidate_digest,
                node.node_id,
                node.role,
                node.executor_id,
                NodeStatus.SUCCEEDED,
                dependency_digests,
                envelope.artifact_digest,
                result.native_evidence,
                result.invoked_symbol,
                attempt.written_paths,
                None,
                None,
            ),
            stored,
        )

    def _validate_resumed_receipt(
        self, plan: DagPlan, node: DagNode, receipt: NodeReceipt
    ) -> StoredArtifact:
        if (
            not isinstance(receipt, NodeReceipt)
            or receipt.status is not NodeStatus.SUCCEEDED
            or receipt.plan_digest != plan.digest
            or receipt.candidate_digest != self.candidate_digest
            or receipt.node_id != node.node_id
            or receipt.role != node.role
            or receipt.executor_id != node.executor_id
            or receipt.artifact_digest is None
        ):
            raise DagValidationError(
                f"resume receipt does not bind node {node.node_id}"
            )
        stored = self.artifact_store.read(receipt.artifact_digest)
        envelope = stored.envelope
        if node.requires_native_evidence and (
            not receipt.native_evidence or receipt.invoked_symbol != node.native_symbol
        ):
            raise DagValidationError(
                f"resume receipt lacks native evidence for node {node.node_id}"
            )
        if (
            envelope.candidate_digest != self.candidate_digest
            or envelope.schema_id != node.produces.schema_id
            or envelope.schema_version != node.produces.schema_version
            or envelope.schema_digest != node.produces.schema_digest
            or envelope.media_type != node.produces.media_type
            or envelope.producer_id != node.executor_id
            or envelope.dependency_digests != receipt.dependency_artifact_digests
        ):
            raise DagValidationError(
                f"resume artifact does not bind node {node.node_id}"
            )
        return stored


def _result_bytes(content: object) -> bytes:
    if isinstance(content, bytes):
        return content
    if isinstance(content, str):
        return content.encode("utf-8")
    try:
        return canonical_bytes(content)
    except (TypeError, ValueError) as error:
        raise TypeError(
            "specialist result content must be finite canonical JSON, bytes, or text"
        ) from error


async def _invoke_handler(
    handler: SpecialistHandler, context: SpecialistContext
) -> SpecialistResult:
    value = await asyncio.to_thread(handler, context)
    if inspect.isawaitable(value):
        value = await cast(Awaitable[SpecialistResult], value)
    return cast(SpecialistResult, value)


def _resolve_handler(
    handlers: SpecialistHandlerRegistry | Mapping[str, SpecialistHandler], role: str
) -> SpecialistHandler:
    if isinstance(handlers, Mapping):
        try:
            return handlers[role]
        except KeyError as error:
            raise NativeEvidenceRequired(
                f"no handler is registered for {role}"
            ) from error
    handler_for = getattr(handlers, "handler_for", None)
    if not callable(handler_for):
        raise TypeError("handlers must be a mapping or SpecialistHandlerRegistry")
    return cast(SpecialistHandler, handler_for(role))


def _dependency_digests(
    node: DagNode, artifacts: Mapping[str, StoredArtifact]
) -> tuple[str, ...]:
    return tuple(
        sorted(
            artifacts[dependency].envelope.artifact_digest
            for dependency in node.dependencies
            if dependency in artifacts
        )
    )


def _topological_order(nodes: Mapping[str, DagNode]) -> tuple[str, ...]:
    indegree = {node_id: len(node.dependencies) for node_id, node in nodes.items()}
    dependants: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    for node in nodes.values():
        for dependency in node.dependencies:
            if dependency in dependants:
                dependants[dependency].append(node.node_id)
    ready = sorted(node_id for node_id, value in indegree.items() if value == 0)
    result: list[str] = []
    while ready:
        node_id = ready.pop(0)
        result.append(node_id)
        for dependant in sorted(dependants[node_id]):
            indegree[dependant] -= 1
            if indegree[dependant] == 0:
                ready.append(dependant)
                ready.sort()
    if len(result) != len(nodes):
        raise DagValidationError("specialist DAG contains a cycle")
    return tuple(result)


def _ancestor_sets(
    nodes: Mapping[str, DagNode], order: tuple[str, ...]
) -> dict[str, frozenset[str]]:
    result: dict[str, frozenset[str]] = {}
    for node_id in order:
        ancestors: set[str] = set(nodes[node_id].dependencies)
        for dependency in nodes[node_id].dependencies:
            ancestors.update(result[dependency])
        result[node_id] = frozenset(ancestors)
    return result


def _scopes_overlap(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    return any(
        left_path == right_path
        or left_path.startswith(right_path + "/")
        or right_path.startswith(left_path + "/")
        for left_path in left
        for right_path in right
    )


def _path_in_scope(path: str, scopes: tuple[str, ...]) -> bool:
    return any(path == scope or path.startswith(scope + "/") for scope in scopes)


def _is_reparse_or_link(path: Path) -> bool:
    metadata = path.lstat()
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse)


def _snapshot_workspace(root: Path) -> tuple[str, ...]:
    if _is_reparse_or_link(root):
        raise WorkspaceViolation("node workspace cannot be a link or reparse point")
    files: list[str] = []
    for current, directories, names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in tuple(directories):
            directory = current_path / name
            if _is_reparse_or_link(directory):
                raise WorkspaceViolation(
                    "node workspace contains a link or reparse point"
                )
        for name in names:
            path = current_path / name
            if _is_reparse_or_link(path) or not path.is_file():
                raise WorkspaceViolation("node workspace contains a non-regular file")
            files.append(normalize_portable_path(path.relative_to(root).as_posix()))
    return tuple(sorted(files))


def _unexpected_workspace_entries(
    workspaces_root: Path, allowed_workspace_ids: frozenset[str]
) -> tuple[str, ...]:
    unexpected: list[str] = []
    for path in workspaces_root.iterdir():
        if (
            path.name not in allowed_workspace_ids
            or not path.is_dir()
            or _is_reparse_or_link(path)
        ):
            unexpected.append(path.name)
    return tuple(sorted(unexpected))


def _unexpected_run_entries(run_root: Path) -> tuple[str, ...]:
    expected = {"evidence", "workspaces"}
    return tuple(
        sorted(path.name for path in run_root.iterdir() if path.name not in expected)
    )


def _stable_error_message(error: BaseException) -> str:
    message = " ".join(str(error).split())
    return message[:1000] or type(error).__name__
