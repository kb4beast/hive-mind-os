"""Durable executor for an externally authorized portable DAG.

All effects cross an injected :class:`HostRuntime`.  The executor authenticates
the plan and one-run capability, writes intent before dispatch, launches a whole
permitted round before waiting, and reuses the host runtime's idempotent receipts
on restart.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import Any, Iterator

from .activation_bundle import (
    ActivationBundleError,
    AuthorizedOneRun,
    validate_authorized_one_run,
)
from .dag_standard import CompilationReceipt, compile_plan, load_bound_plan
from .host_adapter import (
    HostExecutionReceipt,
    HostLease,
    HostReceiptState,
    canonical_checkpoint_digest,
)
from .host_runtime import HostRecoveryRequired, HostRuntime, HostRuntimeError
from .portable_plan import (
    PortableNode,
    PortablePlanBundle,
    validate_activation_plan_binding,
    validate_runtime_plan_admission,
)
from .runtime_contracts import (
    ContractViolation,
    DecisionMemoryDraft,
    DecisionMemoryEntry,
    SelectionBlocker,
    canonical_digest,
    canonical_json_bytes,
    raw_sha256,
    require_digest,
    require_identifier,
    require_time,
    select_decision,
)

# Like the host journal writer token, this is a trusted-process encapsulation
# boundary rather than a cryptographic defense against hostile code in the
# interpreter.  It prevents the public append API from asserting host-backed
# progress or terminal success; restart trust additionally requires custody of
# the verified journal store.
_EXECUTION_JOURNAL_AUTHORITY = object()


class DagExecutionError(RuntimeError):
    """The generic executor refused or could not safely complete a run."""


class ExecutionBlockerCode(StrEnum):
    ACTIVATION_INVALID = "ACTIVATION_INVALID"
    ADAPTER_MISSING = "ADAPTER_MISSING"
    AUTHORITY_INVALID = "AUTHORITY_INVALID"
    BUDGET_INVALID = "BUDGET_INVALID"
    HOST_RECOVERY_REQUIRED = "HOST_RECOVERY_REQUIRED"
    NODE_FAILED = "NODE_FAILED"
    PLAN_INVALID = "PLAN_INVALID"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class RunState(StrEnum):
    INITIALIZED = "INITIALIZED"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class NodeState(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    ADOPTED = "ADOPTED"


@dataclass(frozen=True, slots=True)
class NodeOutcome:
    node_id: str
    state: NodeState
    input_digest: str | None
    output_digest: str | None
    evidence_digest: str | None
    checkpoint_digest: str | None
    reason: str | None

    @property
    def complete(self) -> bool:
        return self.state in {NodeState.SUCCEEDED, NodeState.ADOPTED}


@dataclass(frozen=True, slots=True)
class ExecutionSnapshot:
    run_id: str
    plan_digest: str
    generation_id: str
    subject_id: str
    compilation_digest: str
    state: RunState
    lease_id: str | None
    sequence: int
    nodes: tuple[NodeOutcome, ...]
    blocker_code: ExecutionBlockerCode | None
    blocker_reason: str | None

    def node(self, node_id: str) -> NodeOutcome:
        for item in self.nodes:
            if item.node_id == node_id:
                return item
        raise DagExecutionError(f"run has no node {node_id}")

    def to_document(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "plan_digest": self.plan_digest,
            "generation_id": self.generation_id,
            "subject_id": self.subject_id,
            "compilation_digest": self.compilation_digest,
            "state": self.state.value,
            "lease_id": self.lease_id,
            "sequence": self.sequence,
            "nodes": [
                {
                    "node_id": node.node_id,
                    "state": node.state.value,
                    "input_digest": node.input_digest,
                    "output_digest": node.output_digest,
                    "evidence_digest": node.evidence_digest,
                    "checkpoint_digest": node.checkpoint_digest,
                    "reason": node.reason,
                }
                for node in self.nodes
            ],
            "blocker_code": None
            if self.blocker_code is None
            else self.blocker_code.value,
            "blocker_reason": self.blocker_reason,
        }


@dataclass(frozen=True, slots=True)
class ExecutionEvent:
    run_id: str
    sequence: int
    kind: str
    payload: Mapping[str, Any]
    previous_digest: str | None
    event_digest: str

    def to_document(self, *, include_digest: bool = True) -> dict[str, Any]:
        result = {
            "schema_version": 1,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "kind": self.kind,
            "payload": dict(self.payload),
            "previous_digest": self.previous_digest,
        }
        if include_digest:
            result["event_digest"] = self.event_digest
        return result


class ExecutionJournal:
    """Append-only hash-chained execution facts with deterministic replay."""

    def __init__(
        self, path: str | Path = ":memory:", *, read_only: bool = False
    ) -> None:
        self.path = str(path)
        self.read_only = read_only
        self._lock = RLock()
        if read_only:
            if self.path == ":memory:" or not Path(self.path).is_file():
                raise DagExecutionError("read-only execution journal does not exist")
            uri = Path(self.path).resolve().as_uri() + "?mode=ro"
            self.connection = sqlite3.connect(uri, uri=True, check_same_thread=False)
        else:
            self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        try:
            if not read_only:
                with self.connection:
                    self.connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS dag_execution_events (
                        run_id TEXT NOT NULL,
                        sequence INTEGER NOT NULL,
                        payload_json TEXT NOT NULL,
                        previous_digest TEXT,
                        event_digest TEXT NOT NULL UNIQUE,
                        PRIMARY KEY(run_id, sequence)
                    );
                    CREATE TRIGGER IF NOT EXISTS dag_execution_events_no_update
                    BEFORE UPDATE ON dag_execution_events
                    BEGIN SELECT RAISE(ABORT, 'DAG execution history is append-only'); END;
                    CREATE TRIGGER IF NOT EXISTS dag_execution_events_no_delete
                    BEFORE DELETE ON dag_execution_events
                    BEGIN SELECT RAISE(ABORT, 'DAG execution history is append-only'); END;
                    """
                    )
            self.verify()
        except BaseException:
            self.connection.close()
            raise

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> ExecutionJournal:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _decode(row: sqlite3.Row) -> ExecutionEvent:
        try:
            value = json.loads(str(row["payload_json"]))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise DagExecutionError(
                "execution journal contains invalid JSON"
            ) from error
        fields = {
            "schema_version",
            "run_id",
            "sequence",
            "kind",
            "payload",
            "previous_digest",
            "event_digest",
        }
        if not isinstance(value, Mapping) or set(value) != fields:
            raise DagExecutionError("execution event has an unknown shape")
        if (
            type(value["schema_version"]) is not int
            or value["schema_version"] != 1
            or type(value["run_id"]) is not str
            or type(value["sequence"]) is not int
            or value["sequence"] < 1
            or type(value["kind"]) is not str
            or not value["kind"]
            or not isinstance(value["payload"], Mapping)
            or (
                value["previous_digest"] is not None
                and type(value["previous_digest"]) is not str
            )
            or type(value["event_digest"]) is not str
        ):
            raise DagExecutionError("execution event is malformed")
        event = ExecutionEvent(
            run_id=value["run_id"],
            sequence=value["sequence"],
            kind=value["kind"],
            payload=dict(value["payload"]),
            previous_digest=value["previous_digest"],
            event_digest=value["event_digest"],
        )
        if (
            event.run_id != row["run_id"]
            or event.sequence != row["sequence"]
            or event.previous_digest != row["previous_digest"]
            or event.event_digest != row["event_digest"]
        ):
            raise DagExecutionError("execution event index disagrees with its payload")
        return event

    @staticmethod
    def _payload(event: ExecutionEvent, expected_fields: set[str]) -> Mapping[str, Any]:
        if set(event.payload) != expected_fields:
            raise DagExecutionError(f"{event.kind} has an invalid payload shape")
        return event.payload

    @staticmethod
    def _digest(value: Any, label: str) -> str:
        try:
            require_digest(value, label)
        except ContractViolation as error:
            raise DagExecutionError(str(error)) from error
        return value

    @staticmethod
    def _identifier(value: Any, label: str) -> str:
        try:
            require_identifier(value, label)
        except ContractViolation as error:
            raise DagExecutionError(str(error)) from error
        return value

    @staticmethod
    def _reason(value: Any, label: str) -> str:
        if type(value) is not str or not value.strip():
            raise DagExecutionError(f"{label} must be a non-empty string")
        return value

    @classmethod
    def _replay(
        cls, run_id: str, events: tuple[ExecutionEvent, ...]
    ) -> ExecutionSnapshot:
        if not events or events[0].kind != "run.initialized":
            raise DagExecutionError("execution run does not begin with initialization")
        cls._digest(run_id, "execution run id")
        if any(event.run_id != run_id for event in events):
            raise DagExecutionError("execution run contains a foreign event")

        first = events[0]
        payload = cls._payload(
            first,
            {
                "plan_digest",
                "generation_id",
                "subject_id",
                "compilation_digest",
                "node_ids",
            },
        )
        plan_digest = cls._digest(payload["plan_digest"], "execution plan digest")
        generation_id = cls._digest(payload["generation_id"], "execution generation id")
        subject_id = cls._digest(payload["subject_id"], "execution subject id")
        compilation_digest = cls._digest(
            payload["compilation_digest"], "execution compilation digest"
        )
        node_ids = payload["node_ids"]
        if (
            not isinstance(node_ids, list)
            or not node_ids
            or any(type(item) is not str for item in node_ids)
            or len(set(node_ids)) != len(node_ids)
        ):
            raise DagExecutionError("execution initialization has invalid node ids")
        for node_id in node_ids:
            cls._identifier(node_id, "execution node id")
        nodes = {
            node_id: NodeOutcome(
                node_id, NodeState.PENDING, None, None, None, None, None
            )
            for node_id in node_ids
        }
        state = RunState.INITIALIZED
        lease_id: str | None = None
        blocker_code: ExecutionBlockerCode | None = None
        blocker_reason: str | None = None

        for event in events[1:]:
            if state in {RunState.COMPLETED, RunState.CANCELLED}:
                raise DagExecutionError("execution event follows a terminal run state")
            if event.kind == "host.lease-ready":
                item = cls._payload(event, {"lease_id"})
                if (
                    state not in {RunState.INITIALIZED, RunState.BLOCKED}
                    or lease_id is not None
                ):
                    raise DagExecutionError("host lease event is out of order")
                lease_id = cls._identifier(item["lease_id"], "execution lease id")
            elif event.kind == "run.started":
                cls._payload(event, set())
                if (
                    state not in {RunState.INITIALIZED, RunState.BLOCKED}
                    or lease_id is None
                    or any(
                        node.state
                        in {NodeState.FAILED, NodeState.RECONCILIATION_REQUIRED}
                        for node in nodes.values()
                    )
                ):
                    raise DagExecutionError("run start event is out of order")
                state = RunState.RUNNING
                blocker_code = None
                blocker_reason = None
            elif event.kind == "node.started":
                item = cls._payload(event, {"node_id", "input_digest"})
                node_id = cls._identifier(item["node_id"], "started node id")
                if state is not RunState.RUNNING or node_id not in nodes:
                    raise DagExecutionError("node start event is out of order")
                prior = nodes[node_id]
                if prior.state is not NodeState.PENDING:
                    raise DagExecutionError("node was started more than once")
                nodes[node_id] = NodeOutcome(
                    node_id,
                    NodeState.RUNNING,
                    cls._digest(item["input_digest"], "node input digest"),
                    None,
                    None,
                    None,
                    None,
                )
            elif event.kind in {
                "node.succeeded",
                "node.recovered",
                "node.adopted",
            }:
                item = cls._payload(
                    event,
                    {
                        "node_id",
                        "input_digest",
                        "output_digest",
                        "evidence_digest",
                        "checkpoint_digest",
                    },
                )
                node_id = cls._identifier(item["node_id"], "result node id")
                if node_id not in nodes:
                    raise DagExecutionError("node result names an unknown node")
                prior = nodes[node_id]
                required_state = (
                    {NodeState.FAILED, NodeState.RECONCILIATION_REQUIRED}
                    if event.kind == "node.adopted"
                    else {NodeState.RUNNING}
                )
                required_run_states = (
                    {RunState.BLOCKED}
                    if event.kind == "node.adopted"
                    else (
                        {RunState.RUNNING, RunState.BLOCKED}
                        if event.kind == "node.recovered"
                        else {RunState.RUNNING}
                    )
                )
                if state not in required_run_states or prior.state not in required_state:
                    raise DagExecutionError("node result event is out of order")
                input_digest = cls._digest(item["input_digest"], "node input digest")
                if prior.input_digest != input_digest:
                    raise DagExecutionError(
                        "node result does not match its frozen input"
                    )
                nodes[node_id] = NodeOutcome(
                    node_id,
                    NodeState.ADOPTED
                    if event.kind == "node.adopted"
                    else NodeState.SUCCEEDED,
                    prior.input_digest,
                    cls._digest(item["output_digest"], "node output digest"),
                    cls._digest(item["evidence_digest"], "node evidence digest"),
                    cls._digest(item["checkpoint_digest"], "node checkpoint digest"),
                    None,
                )
            elif event.kind in {"node.failed", "node.reconciliation-required"}:
                item = cls._payload(event, {"node_id", "reason", "evidence_digest"})
                node_id = cls._identifier(item["node_id"], "failed node id")
                if (
                    state is not RunState.RUNNING
                    or node_id not in nodes
                    or nodes[node_id].state is not NodeState.RUNNING
                ):
                    raise DagExecutionError("node failure event is out of order")
                evidence_digest = item["evidence_digest"]
                if evidence_digest is not None:
                    evidence_digest = cls._digest(
                        evidence_digest, "node failure evidence digest"
                    )
                prior = nodes[node_id]
                nodes[node_id] = NodeOutcome(
                    node_id,
                    NodeState.FAILED
                    if event.kind == "node.failed"
                    else NodeState.RECONCILIATION_REQUIRED,
                    prior.input_digest,
                    None,
                    evidence_digest,
                    None,
                    cls._reason(item["reason"], "node failure reason"),
                )
            elif event.kind == "run.blocked":
                item = cls._payload(event, {"code", "reason"})
                if state not in {RunState.INITIALIZED, RunState.RUNNING}:
                    raise DagExecutionError("run blocker event is out of order")
                try:
                    blocker_code = ExecutionBlockerCode(item["code"])
                except (TypeError, ValueError) as error:
                    raise DagExecutionError("run blocker code is invalid") from error
                blocker_reason = cls._reason(item["reason"], "run blocker reason")
                state = RunState.BLOCKED
            elif event.kind == "run.completed":
                cls._payload(event, set())
                if state is not RunState.RUNNING or not all(
                    node.complete for node in nodes.values()
                ):
                    raise DagExecutionError(
                        "incomplete or inactive run claims completion"
                    )
                state = RunState.COMPLETED
            elif event.kind == "run.cancelled":
                item = cls._payload(event, {"reason"})
                if (
                    state
                    not in {RunState.INITIALIZED, RunState.RUNNING, RunState.BLOCKED}
                    or lease_id is None
                ):
                    raise DagExecutionError("run cancellation event is out of order")
                cls._reason(item["reason"], "run cancellation reason")
                state = RunState.CANCELLED
            else:
                raise DagExecutionError(
                    f"unsupported execution event kind: {event.kind}"
                )
        return ExecutionSnapshot(
            run_id=run_id,
            plan_digest=plan_digest,
            generation_id=generation_id,
            subject_id=subject_id,
            compilation_digest=compilation_digest,
            state=state,
            lease_id=lease_id,
            sequence=len(events),
            nodes=tuple(nodes[node_id] for node_id in node_ids),
            blocker_code=blocker_code,
            blocker_reason=blocker_reason,
        )

    def _rows(self, run_id: str | None = None) -> tuple[sqlite3.Row, ...]:
        if run_id is None:
            return tuple(
                self.connection.execute(
                    "SELECT * FROM dag_execution_events ORDER BY run_id, sequence"
                )
            )
        return tuple(
            self.connection.execute(
                "SELECT * FROM dag_execution_events WHERE run_id=? ORDER BY sequence",
                (run_id,),
            )
        )

    @contextmanager
    def _read_snapshot(self) -> Iterator[None]:
        """Hold one SQLite snapshot for a complete journal read."""

        owns_transaction = not self.connection.in_transaction
        if owns_transaction:
            self.connection.execute("BEGIN")
        try:
            yield
            if owns_transaction:
                self.connection.commit()
        except BaseException:
            if owns_transaction:
                self.connection.rollback()
            raise

    def verify(self) -> None:
        with self._lock, self._read_snapshot():
            self._verify_snapshot()

    def _verify_snapshot(self) -> None:
        prior: dict[str, str | None] = {}
        sequence: dict[str, int] = {}
        grouped: dict[str, list[ExecutionEvent]] = {}
        for row in self._rows():
            event = self._decode(row)
            expected_sequence = sequence.get(event.run_id, 1)
            if event.sequence != expected_sequence:
                raise DagExecutionError("execution journal sequence is discontinuous")
            if event.previous_digest != prior.get(event.run_id):
                raise DagExecutionError("execution journal hash chain is broken")
            expected_digest = canonical_digest(event.to_document(include_digest=False))
            if event.event_digest != expected_digest:
                raise DagExecutionError("execution event digest is invalid")
            if (
                str(row["payload_json"])
                != canonical_json_bytes(event.to_document()).decode()
            ):
                raise DagExecutionError("execution event is not canonical")
            prior[event.run_id] = event.event_digest
            sequence[event.run_id] = expected_sequence + 1
            grouped.setdefault(event.run_id, []).append(event)
        for run_id, events in grouped.items():
            self._replay(run_id, tuple(events))

    def events(self, run_id: str) -> tuple[ExecutionEvent, ...]:
        with self._lock, self._read_snapshot():
            self.verify()
            return tuple(self._decode(row) for row in self._rows(run_id))

    def run_ids(self) -> tuple[str, ...]:
        with self._lock, self._read_snapshot():
            self.verify()
            return tuple(
                str(row[0])
                for row in self.connection.execute(
                    "SELECT DISTINCT run_id FROM dag_execution_events ORDER BY run_id"
                )
            )

    def append(
        self,
        run_id: str,
        kind: str,
        payload: Mapping[str, Any],
        *,
        _executor_authority: object | None = None,
    ) -> ExecutionEvent:
        if not run_id or not kind:
            raise DagExecutionError("run_id and event kind are required")
        if self.read_only:
            raise DagExecutionError("read-only execution journal cannot be mutated")
        if (
            kind != "run.initialized"
            and _executor_authority is not _EXECUTION_JOURNAL_AUTHORITY
        ):
            raise DagExecutionError(
                "host-backed execution journal writes are executor-owned"
            )
        with self._lock:
            rows = self._rows(run_id)
            previous = None if not rows else str(rows[-1]["event_digest"])
            sequence = len(rows) + 1
            provisional = ExecutionEvent(
                run_id, sequence, kind, dict(payload), previous, ""
            )
            digest = canonical_digest(provisional.to_document(include_digest=False))
            event = ExecutionEvent(
                run_id, sequence, kind, dict(payload), previous, digest
            )
            prior_events = tuple(self._decode(row) for row in rows)
            self._replay(run_id, (*prior_events, event))
            encoded = canonical_json_bytes(event.to_document()).decode()
            try:
                self.connection.execute("BEGIN IMMEDIATE")
                current = self.connection.execute(
                    "SELECT COUNT(*) FROM dag_execution_events WHERE run_id=?",
                    (run_id,),
                ).fetchone()[0]
                if int(current) != sequence - 1:
                    raise DagExecutionError("execution journal compare-and-swap failed")
                self.connection.execute(
                    "INSERT INTO dag_execution_events VALUES(?,?,?,?,?)",
                    (run_id, sequence, encoded, previous, digest),
                )
                self.connection.commit()
            except BaseException:
                self.connection.rollback()
                raise
            return event

    def snapshot(self, run_id: str) -> ExecutionSnapshot | None:
        events = self.events(run_id)
        if not events:
            return None
        return self._replay(run_id, events)


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    plan_bytes: bytes
    expected_plan_digest: str
    standard_bytes: bytes
    generation_id: str
    authorization: AuthorizedOneRun
    available_adapter_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.plan_bytes) is not bytes or type(self.standard_bytes) is not bytes:
            raise ContractViolation("execution inputs must be immutable bytes")
        require_digest(self.expected_plan_digest, "expected plan digest")
        require_digest(self.generation_id, "generation_id")
        try:
            validate_authorized_one_run(self.authorization)
        except ActivationBundleError as error:
            raise ContractViolation(
                "a sealed external one-run authorization is required"
            ) from error
        if type(self.available_adapter_ids) is not tuple or len(
            set(self.available_adapter_ids)
        ) != len(self.available_adapter_ids):
            raise ContractViolation(
                "available adapter ids must be an immutable unique tuple"
            )
        for adapter_id in self.available_adapter_ids:
            require_identifier(adapter_id, "available adapter id")


class DagExecutor:
    def __init__(
        self,
        host_runtime: HostRuntime,
        journal: ExecutionJournal,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.host_runtime = host_runtime
        self.journal = journal
        self.clock = clock or (lambda: datetime.now(UTC))

    def _append_event(
        self, run_id: str, kind: str, payload: Mapping[str, Any]
    ) -> ExecutionEvent:
        return self.journal.append(
            run_id,
            kind,
            payload,
            _executor_authority=_EXECUTION_JOURNAL_AUTHORITY,
        )

    @staticmethod
    def _run_id(request: ExecutionRequest) -> str:
        return canonical_digest(
            {
                "activation_digest": request.authorization.activation_digest,
                "generation_id": request.generation_id,
                "plan_digest": request.expected_plan_digest,
            }
        )

    @classmethod
    def _authenticated_run_id(cls, request: ExecutionRequest) -> str:
        """Derive a lookup identity only from a genuine sealed capability."""

        try:
            validate_authorized_one_run(request.authorization)
        except ActivationBundleError as error:
            raise DagExecutionError(
                "ACTIVATION_INVALID: one-run capability seal is invalid"
            ) from error
        return cls._run_id(request)

    def _prepare(
        self,
        request: ExecutionRequest,
        *,
        allow_expired: bool = False,
        allow_preissued_terminal: bool = False,
    ) -> tuple[PortablePlanBundle, CompilationReceipt, str]:
        plan = load_bound_plan(
            request.plan_bytes,
            expected_plan_digest=request.expected_plan_digest,
            standard_bytes=request.standard_bytes,
        )
        compilation = compile_plan(
            request.plan_bytes,
            expected_plan_digest=request.expected_plan_digest,
            standard_bytes=request.standard_bytes,
        )
        authorization = request.authorization
        try:
            validate_authorized_one_run(authorization)
            validate_activation_plan_binding(
                plan,
                request_sha256=authorization.request_sha256,
                repository_id=authorization.repository_id,
                candidate_parent_commit=authorization.candidate_parent_commit,
                candidate_parent_tree=authorization.candidate_parent_tree,
                target_branch=authorization.target_branch,
            )
        except (ActivationBundleError, ContractViolation) as error:
            raise DagExecutionError(
                "ACTIVATION_INVALID: one-run capability or plan binding is invalid: "
                + str(error)
            ) from error
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise DagExecutionError("executor clock must be timezone-aware")
        if authorization.issued_at > now and not allow_preissued_terminal:
            raise DagExecutionError(
                "ACTIVATION_INVALID: one-run authorization is not yet valid"
            )
        if authorization.expires_at <= now and not allow_expired:
            raise DagExecutionError("ACTIVATION_INVALID: one-run authorization expired")
        if authorization.plan_sha256 != request.expected_plan_digest:
            raise DagExecutionError(
                "ACTIVATION_INVALID: authorization names another plan"
            )
        required_adapters = {item.adapter_id for item in plan.adapters}
        asserted_adapters = set(request.available_adapter_ids)
        unexpected = asserted_adapters - required_adapters
        if unexpected:
            raise DagExecutionError(
                "ADAPTER_INVALID: caller asserted adapters outside the signed plan: "
                + ", ".join(sorted(unexpected))
            )
        missing = required_adapters - asserted_adapters
        if missing:
            raise DagExecutionError("ADAPTER_MISSING: " + ", ".join(sorted(missing)))
        self._validate_authority_and_budgets(plan, authorization.expires_at)
        return plan, compilation, self._run_id(request)

    @staticmethod
    def _validate_authority_and_budgets(
        plan: PortablePlanBundle, deadline: datetime
    ) -> None:
        try:
            validate_runtime_plan_admission(
                plan,
                execution_deadline=deadline,
            )
        except ContractViolation as error:
            code = (
                ExecutionBlockerCode.BUDGET_INVALID
                if "budget" in str(error).lower()
                else ExecutionBlockerCode.AUTHORITY_INVALID
            )
            raise DagExecutionError(f"{code.value}: {error}") from error

    @staticmethod
    def _idempotency(run_id: str, action: str, node_id: str | None = None) -> str:
        return canonical_digest(
            {"run_id": run_id, "action": action, "node_id": node_id}
        )

    @staticmethod
    def _deadline(value: datetime) -> str:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    def execute(self, request: ExecutionRequest) -> ExecutionSnapshot:
        requested_run_id = self._authenticated_run_id(request)
        historical = self.journal.snapshot(requested_run_id)
        allow_preissued_terminal = historical is not None and historical.state in {
            RunState.COMPLETED,
            RunState.CANCELLED,
        }
        plan, compilation, run_id = self._prepare(
            request,
            allow_expired=True,
            allow_preissued_terminal=allow_preissued_terminal,
        )
        snapshot = self.journal.snapshot(run_id)
        if snapshot is not None and (
            snapshot.plan_digest != plan.digest()
            or snapshot.generation_id != request.generation_id
            or snapshot.compilation_digest != compilation.digest
        ):
            raise DagExecutionError("PLAN_INVALID: durable run identity drifted")
        if snapshot is not None and snapshot.state in {
            RunState.COMPLETED,
            RunState.CANCELLED,
        }:
            return snapshot
        live_now = self.clock()
        if live_now.tzinfo is None or live_now.utcoffset() is None:
            raise DagExecutionError("executor clock must be timezone-aware")
        if request.authorization.issued_at > live_now:
            raise DagExecutionError(
                "ACTIVATION_INVALID: one-run authorization is not yet valid"
            )
        if request.authorization.expires_at <= live_now:
            if snapshot is None:
                raise DagExecutionError(
                    "ACTIVATION_INVALID: expired authorization has no durable run"
                )
            return self._recover_expired_run(run_id, snapshot)
        if snapshot is None:
            self._append_event(
                run_id,
                "run.initialized",
                {
                    "plan_digest": plan.digest(),
                    "generation_id": request.generation_id,
                    "subject_id": plan.subject.subject_id,
                    "compilation_digest": compilation.digest,
                    "node_ids": [node.node_id for node in plan.nodes],
                },
            )
        if snapshot is not None and any(
            node.state in {NodeState.FAILED, NodeState.RECONCILIATION_REQUIRED}
            for node in snapshot.nodes
        ):
            return snapshot

        create_key = self._idempotency(run_id, "create")
        try:
            if snapshot is not None and snapshot.lease_id is not None:
                lease = self.host_runtime.resume(
                    create_idempotency_key=create_key,
                    poll_idempotency_key=self._idempotency(
                        run_id, f"resume-poll-{snapshot.sequence}"
                    ),
                )
            else:
                lease = self.host_runtime.create(
                    plan_bytes=request.plan_bytes,
                    standard_bytes=request.standard_bytes,
                    generation_id=request.generation_id,
                    lease_deadline=self._deadline(request.authorization.expires_at),
                    authorization=request.authorization,
                    idempotency_key=create_key,
                )
        except (HostRecoveryRequired, HostRuntimeError) as error:
            self._block(run_id, ExecutionBlockerCode.HOST_RECOVERY_REQUIRED, str(error))
            result = self.journal.snapshot(run_id)
            assert result is not None
            return result
        current = self.journal.snapshot(run_id)
        assert current is not None
        if current.lease_id is None:
            self._append_event(
                run_id, "host.lease-ready", {"lease_id": lease.lease_id}
            )
        if current.state in {RunState.INITIALIZED, RunState.BLOCKED}:
            self._append_event(run_id, "run.started", {})

        by_id = {node.node_id: node for node in plan.nodes}
        for dispatch_round in compilation.rounds:
            current = self.journal.snapshot(run_id)
            assert current is not None
            pending = [
                node_id
                for node_id in dispatch_round.node_ids
                if not current.node(node_id).complete
            ]
            if not pending:
                continue
            dependency_outputs = {
                node.node_id: node.output_digest
                for node in current.nodes
                if node.complete and node.output_digest is not None
            }
            envelopes: dict[str, bytes] = {}
            for node_id in pending:
                node = by_id[node_id]
                if any(
                    dependency not in dependency_outputs
                    for dependency in node.dependencies
                ):
                    self._block(
                        run_id,
                        ExecutionBlockerCode.RECONCILIATION_REQUIRED,
                        f"{node_id} has an incomplete dependency",
                    )
                    result = self.journal.snapshot(run_id)
                    assert result is not None
                    return result
                envelopes[node_id] = self._node_envelope(
                    plan,
                    compilation,
                    dispatch_round.to_document(),
                    node,
                    dependency_outputs,
                    request.authorization,
                )
                prior = current.node(node_id)
                if prior.state is NodeState.PENDING:
                    self._append_event(
                        run_id,
                        "node.started",
                        {
                            "node_id": node_id,
                            "input_digest": raw_sha256(envelopes[node_id]),
                        },
                    )
            futures = {}
            with ThreadPoolExecutor(max_workers=len(pending)) as pool:
                for node_id in pending:
                    futures[node_id] = pool.submit(
                        self.host_runtime.message,
                        lease=lease,
                        node_id=node_id,
                        input_bytes=envelopes[node_id],
                        idempotency_key=self._idempotency(run_id, "message", node_id),
                    )
                results: dict[str, HostExecutionReceipt | BaseException] = {}
                for node_id in pending:
                    try:
                        results[node_id] = futures[node_id].result()
                    except BaseException as error:
                        results[node_id] = error
            blocked = False
            for node_id in pending:
                result = results[node_id]
                if isinstance(result, BaseException):
                    self._append_event(
                        run_id,
                        "node.reconciliation-required",
                        {
                            "node_id": node_id,
                            "reason": f"ambiguous host result: {type(result).__name__}",
                            "evidence_digest": None,
                        },
                    )
                    blocked = True
                    continue
                if (
                    result.state is not HostReceiptState.SUCCEEDED
                    or result.output_digest is None
                ):
                    self._append_event(
                        run_id,
                        "node.failed",
                        {
                            "node_id": node_id,
                            "reason": f"host returned {result.state.value}",
                            "evidence_digest": result.evidence_digest,
                        },
                    )
                    blocked = True
                    continue
                checkpoint_digest = canonical_checkpoint_digest(lease, result)
                checkpoint = self.host_runtime.checkpoint(
                    lease=lease,
                    receipt=result,
                    checkpoint_digest=checkpoint_digest,
                    candidate_digest=result.output_digest,
                    idempotency_key=self._idempotency(run_id, "checkpoint", node_id),
                )
                self._append_event(
                    run_id,
                    "node.succeeded",
                    {
                        "node_id": node_id,
                        "input_digest": result.input_digest,
                        "output_digest": result.output_digest,
                        "evidence_digest": result.evidence_digest,
                        "checkpoint_digest": checkpoint.checkpoint_digest,
                    },
                )
            if blocked:
                self._block(
                    run_id,
                    ExecutionBlockerCode.RECONCILIATION_REQUIRED,
                    "one or more host outcomes require reconciliation",
                )
                result = self.journal.snapshot(run_id)
                assert result is not None
                return result
        return self._seal_run_terminal(run_id, lease)

    def _recover_expired_run(
        self,
        run_id: str,
        snapshot: ExecutionSnapshot,
    ) -> ExecutionSnapshot:
        """Close executor-local crash windows using durable host proof only."""

        try:
            lease = self.host_runtime.resume_for_reconciliation(
                create_idempotency_key=self._idempotency(run_id, "create"),
                poll_idempotency_key=self._idempotency(
                    run_id, f"expired-recovery-poll-{snapshot.sequence}"
                ),
            )
        except (HostRecoveryRequired, HostRuntimeError) as error:
            raise DagExecutionError(
                "expired run host identity could not be authenticated"
            ) from error
        if snapshot.lease_id is None:
            # Host create may have committed immediately before the executor
            # crashed.  The historical observer can authenticate that exact
            # cached lease without calling prepare; only then may the missing
            # executor-local lease fact be appended.
            self._append_event(
                run_id, "host.lease-ready", {"lease_id": lease.lease_id}
            )
            refreshed = self.journal.snapshot(run_id)
            assert refreshed is not None
            snapshot = refreshed
        elif lease.lease_id != snapshot.lease_id:
            raise DagExecutionError("expired run lease identity drifted")

        try:
            cancellation = self.host_runtime.committed_cancellation(lease)
        except HostRecoveryRequired as error:
            self._block(
                run_id,
                ExecutionBlockerCode.HOST_RECOVERY_REQUIRED,
                str(error),
            )
            result = self.journal.snapshot(run_id)
            assert result is not None
            return result
        if cancellation is not None:
            self._append_event(
                run_id, "run.cancelled", {"reason": cancellation[0]}
            )
            result = self.journal.snapshot(run_id)
            assert result is not None
            return result

        for node in snapshot.nodes:
            if node.state is not NodeState.RUNNING or node.input_digest is None:
                continue
            receipt = self.host_runtime.historical_message_success(
                lease=lease,
                node_id=node.node_id,
                input_digest=node.input_digest,
            )
            if receipt is None:
                continue
            if receipt.output_digest is None:
                raise DagExecutionError(
                    "historical host success is not bound to the node intent"
                )
            expected_checkpoint = canonical_checkpoint_digest(lease, receipt)
            checkpoint = self.host_runtime.historical_checkpoint(
                lease=lease,
                receipt=receipt,
                checkpoint_digest=expected_checkpoint,
                candidate_digest=receipt.output_digest,
            )
            if checkpoint is None:
                # Checkpointing is a journal-only operation.  It is safe after
                # expiry because the exact successful message receipt has
                # already been authenticated and no adapter method is called.
                checkpoint = self.host_runtime.checkpoint(
                    lease=lease,
                    receipt=receipt,
                    checkpoint_digest=expected_checkpoint,
                    candidate_digest=receipt.output_digest,
                    idempotency_key=self._idempotency(
                        run_id, "checkpoint", node.node_id
                    ),
                )
            if checkpoint.checkpoint_digest != expected_checkpoint:
                raise DagExecutionError(
                    "historical host checkpoint differs from executor binding"
                )
            if (
                checkpoint.lease_id != lease.lease_id
                or checkpoint.node_id != node.node_id
                or checkpoint.input_digest != node.input_digest
                or checkpoint.candidate_digest != receipt.output_digest
            ):
                raise DagExecutionError(
                    "historical host success is not bound to the node intent"
                )
            self._append_event(
                run_id,
                "node.recovered",
                {
                    "node_id": node.node_id,
                    "input_digest": receipt.input_digest,
                    "output_digest": receipt.output_digest,
                    "evidence_digest": receipt.evidence_digest,
                    "checkpoint_digest": checkpoint.checkpoint_digest,
                },
            )

        current = self.journal.snapshot(run_id)
        assert current is not None
        if all(node.complete for node in current.nodes):
            # Re-authenticate every terminal node against its exact durable
            # host message/checkpoint pair before closing the run.
            for node in current.nodes:
                assert node.input_digest is not None
                receipt = self.host_runtime.historical_message_success(
                    lease=lease,
                    node_id=node.node_id,
                    input_digest=node.input_digest,
                )
                if receipt is None or node.checkpoint_digest is None:
                    raise DagExecutionError(
                        "run completion lacks durable host checkpoint proof"
                    )
                checkpoint = self.host_runtime.historical_checkpoint(
                    lease=lease,
                    receipt=receipt,
                    checkpoint_digest=node.checkpoint_digest,
                    candidate_digest=receipt.output_digest,
                )
                if checkpoint is None:
                    raise DagExecutionError(
                        "run completion lacks durable host checkpoint proof"
                    )
                if (
                    node.output_digest != receipt.output_digest
                    or node.checkpoint_digest != checkpoint.checkpoint_digest
                    or (
                        node.state is NodeState.SUCCEEDED
                        and node.evidence_digest != receipt.evidence_digest
                    )
                ):
                    raise DagExecutionError(
                        "executor node result differs from durable host proof"
                    )
            return self._seal_run_terminal(run_id, lease)
        elif current.state in {RunState.INITIALIZED, RunState.RUNNING}:
            self._block(
                run_id,
                ExecutionBlockerCode.HOST_RECOVERY_REQUIRED,
                "activation expired; only historical host proof may close the run",
            )
        result = self.journal.snapshot(run_id)
        assert result is not None
        return result

    def _seal_run_terminal(
        self, run_id: str, lease: HostLease
    ) -> ExecutionSnapshot:
        """Order completion against cancellation in the authoritative host journal."""

        try:
            cancellation_reason = self.host_runtime.seal_completion(lease)
        except HostRecoveryRequired as error:
            self._block(
                run_id,
                ExecutionBlockerCode.HOST_RECOVERY_REQUIRED,
                str(error),
            )
            result = self.journal.snapshot(run_id)
            assert result is not None
            return result
        except HostRuntimeError as error:
            self._block(
                run_id,
                ExecutionBlockerCode.RECONCILIATION_REQUIRED,
                str(error),
            )
            result = self.journal.snapshot(run_id)
            assert result is not None
            return result
        if cancellation_reason is not None:
            self._append_event(
                run_id, "run.cancelled", {"reason": cancellation_reason}
            )
        else:
            current = self.journal.snapshot(run_id)
            assert current is not None
            if current.state is RunState.BLOCKED:
                self._append_event(run_id, "run.started", {})
            self._append_event(run_id, "run.completed", {})
        result = self.journal.snapshot(run_id)
        assert result is not None
        return result

    @staticmethod
    def _node_envelope(
        plan: PortablePlanBundle,
        compilation: CompilationReceipt,
        dispatch_round: Mapping[str, Any],
        node: PortableNode,
        dependency_outputs: Mapping[str, str],
        authorization: AuthorizedOneRun,
    ) -> bytes:
        manifest = {
            "schema_version": 1,
            "kind": "hive-mind-frozen-run-manifest-v1",
            "plan_digest": plan.digest(),
            "request_id": plan.request_id,
            "subject_id": plan.subject.subject_id,
            "compilation_digest": compilation.digest,
            "activation_digest": authorization.activation_digest,
            "expires_at": authorization.expires_at.astimezone(UTC)
            .isoformat()
            .replace("+00:00", "Z"),
        }
        delta = {
            "node": node.to_document(),
            "round": dict(dispatch_round),
            "direct_dependency_outputs": {
                dependency: dependency_outputs[dependency]
                for dependency in node.dependencies
            },
        }
        return canonical_json_bytes({"frozen_manifest": manifest, "node_delta": delta})

    def _block(self, run_id: str, code: ExecutionBlockerCode, reason: str) -> None:
        current = self.journal.snapshot(run_id)
        if current is not None and current.state is RunState.BLOCKED:
            return
        self._append_event(
            run_id, "run.blocked", {"code": code.value, "reason": reason}
        )

    def reconcile(
        self,
        *,
        run_id: str,
        receipt: HostExecutionReceipt,
        adoption_evidence_digest: str,
    ) -> ExecutionSnapshot:
        require_digest(adoption_evidence_digest, "adoption_evidence_digest")
        snapshot = self.journal.snapshot(run_id)
        if snapshot is None:
            raise DagExecutionError("no such durable run")
        node = snapshot.node(receipt.node_id)
        if node.state is not NodeState.RECONCILIATION_REQUIRED:
            raise DagExecutionError("node has no ambiguous host intent to reconcile")
        if (
            receipt.state is not HostReceiptState.SUCCEEDED
            or receipt.input_digest != node.input_digest
            or receipt.output_digest is None
            or receipt.lease_id != snapshot.lease_id
        ):
            raise DagExecutionError(
                "adopted receipt does not bind the exact node intent"
            )
        assert node.input_digest is not None
        lease = self.host_runtime.resume_for_reconciliation(
            create_idempotency_key=self._idempotency(run_id, "create"),
            poll_idempotency_key=self._idempotency(
                run_id, f"reconcile-poll-{snapshot.sequence}"
            ),
        )
        message_request = {
            "lease": lease.to_document(),
            "node_id": receipt.node_id,
            "input_digest": node.input_digest,
        }
        try:
            adopted = self.host_runtime.adopt(
                operation_idempotency_key=self._idempotency(
                    run_id, "message", receipt.node_id
                ),
                request=message_request,
                response_type="execution-receipt",
                response=receipt,
                evidence_digest=adoption_evidence_digest,
            )
        except (HostRecoveryRequired, HostRuntimeError) as error:
            raise DagExecutionError(
                "reconciliation evidence was not authenticated"
            ) from error
        if not isinstance(adopted, HostExecutionReceipt):
            raise DagExecutionError("host adoption returned the wrong receipt type")
        combined_evidence_digest = canonical_digest(
            {
                "host_receipt_evidence": adopted.evidence_digest,
                "adoption_evidence": adoption_evidence_digest,
            }
        )
        checkpoint_digest = canonical_checkpoint_digest(lease, adopted)
        checkpoint = self.host_runtime.checkpoint(
            lease=lease,
            receipt=adopted,
            checkpoint_digest=checkpoint_digest,
            candidate_digest=adopted.output_digest,
            idempotency_key=self._idempotency(
                run_id, "checkpoint", adopted.node_id
            ),
        )
        if (
            checkpoint.lease_id != lease.lease_id
            or checkpoint.node_id != adopted.node_id
            or checkpoint.input_digest != adopted.input_digest
            or checkpoint.checkpoint_digest != checkpoint_digest
            or checkpoint.candidate_digest != adopted.output_digest
        ):
            raise DagExecutionError("host checkpoint does not bind adopted receipt")
        self._append_event(
            run_id,
            "node.adopted",
            {
                "node_id": adopted.node_id,
                "input_digest": adopted.input_digest,
                "output_digest": adopted.output_digest,
                "evidence_digest": combined_evidence_digest,
                "checkpoint_digest": checkpoint.checkpoint_digest,
            },
        )
        result = self.journal.snapshot(run_id)
        assert result is not None
        return result

    def cancel(self, request: ExecutionRequest, *, reason: str) -> ExecutionSnapshot:
        if type(reason) is not str or not reason.strip():
            raise DagExecutionError("cancellation reason must be a non-empty string")
        requested_run_id = self._authenticated_run_id(request)
        historical = self.journal.snapshot(requested_run_id)
        allow_preissued_terminal = historical is not None and historical.state in {
            RunState.COMPLETED,
            RunState.CANCELLED,
        }
        _, _, run_id = self._prepare(
            request,
            allow_expired=True,
            allow_preissued_terminal=allow_preissued_terminal,
        )
        snapshot = self.journal.snapshot(run_id)
        if snapshot is None or snapshot.lease_id is None:
            raise DagExecutionError("no active durable run can be cancelled")
        if snapshot.state is RunState.CANCELLED:
            cancellation = self.journal.events(run_id)[-1]
            if (
                cancellation.kind != "run.cancelled"
                or cancellation.payload.get("reason") != reason
            ):
                raise DagExecutionError(
                    "cancelled durable run cannot be rebound to another reason"
                )
            return snapshot
        if snapshot.state is RunState.COMPLETED:
            raise DagExecutionError("completed durable run cannot be cancelled")
        historical_lease = self.host_runtime.resume_for_reconciliation(
            create_idempotency_key=self._idempotency(run_id, "create"),
            poll_idempotency_key=self._idempotency(
                run_id, f"cancel-recovery-poll-{snapshot.sequence}"
            ),
        )
        try:
            historical_cancel = self.host_runtime.historical_cancellation(
                lease=historical_lease,
                reason=reason,
            )
        except HostRuntimeError:
            historical_cancel = None
        if historical_cancel is not None:
            self._append_event(run_id, "run.cancelled", {"reason": reason})
            result = self.journal.snapshot(run_id)
            assert result is not None
            return result
        if request.authorization.expires_at <= self.clock():
            raise DagExecutionError(
                "ACTIVATION_INVALID: expired run has no committed cancellation"
            )
        lease = self.host_runtime.resume(
            create_idempotency_key=self._idempotency(run_id, "create"),
            poll_idempotency_key=self._idempotency(
                run_id, f"cancel-poll-{snapshot.sequence}"
            ),
        )
        self.host_runtime.cancel(
            lease=lease,
            reason=reason,
            idempotency_key=self._idempotency(run_id, "cancel"),
        )
        self._append_event(run_id, "run.cancelled", {"reason": reason})
        result = self.journal.snapshot(run_id)
        assert result is not None
        return result

    def decide(
        self,
        draft: DecisionMemoryDraft,
        *,
        observed_snapshot: str,
        now: str,
    ) -> DecisionMemoryEntry:
        result = select_decision(draft, observed_snapshot=observed_snapshot, now=now)
        if isinstance(result, SelectionBlocker):
            raise DagExecutionError(
                f"{result.code.value}: " + "; ".join(result.reasons)
            )
        return result


@dataclass(frozen=True, slots=True)
class GraphPatch:
    base_plan_digest: str
    successor_plan_digest: str
    previous_patch_digest: str | None
    one_run_expires_at: str
    signer_id: str
    key_id: str
    signature: str

    def __post_init__(self) -> None:
        require_digest(self.base_plan_digest, "base plan digest")
        require_digest(self.successor_plan_digest, "successor plan digest")
        if self.previous_patch_digest is not None:
            require_digest(self.previous_patch_digest, "previous patch digest")
        require_time(self.one_run_expires_at, "patch deadline")
        if not all(
            isinstance(item, str) and item
            for item in (self.signer_id, self.key_id, self.signature)
        ):
            raise ContractViolation("patch signer, key, and signature are required")

    def signed_bytes(self) -> bytes:
        return canonical_json_bytes(
            {
                "base_plan_digest": self.base_plan_digest,
                "successor_plan_digest": self.successor_plan_digest,
                "previous_patch_digest": self.previous_patch_digest,
                "one_run_expires_at": self.one_run_expires_at,
                "signer_id": self.signer_id,
                "key_id": self.key_id,
            }
        )

    @property
    def digest(self) -> str:
        return canonical_digest(
            {"signed": json.loads(self.signed_bytes()), "signature": self.signature}
        )


PatchVerifier = Callable[[GraphPatch, bytes], bool]


def validate_graph_patch(
    base_plan_bytes: bytes,
    successor_plan_bytes: bytes,
    *,
    standard_bytes: bytes,
    patch: GraphPatch,
    expected_one_run_expires_at: str,
    verifier: PatchVerifier,
) -> CompilationReceipt:
    """Authenticate a monotonic graph successor; weakening requires a new run."""

    if patch.one_run_expires_at != expected_one_run_expires_at:
        raise DagExecutionError("graph patch changes the one-run deadline")
    if not verifier(patch, patch.signed_bytes()):
        raise DagExecutionError("graph patch signature is invalid")
    base = load_bound_plan(
        base_plan_bytes,
        expected_plan_digest=patch.base_plan_digest,
        standard_bytes=standard_bytes,
    )
    successor = load_bound_plan(
        successor_plan_bytes,
        expected_plan_digest=patch.successor_plan_digest,
        standard_bytes=standard_bytes,
    )
    for field in (
        "request_id",
        "objective_digest",
        "subject",
        "standard",
        "recovery",
        "integration",
        "token_policy",
    ):
        if getattr(base, field) != getattr(successor, field):
            raise DagExecutionError(f"graph patch weakens or changes {field}")
    _require_inventory_superset(base.resources, successor.resources, "resource_id")
    _require_inventory_superset(
        base.capabilities, successor.capabilities, "capability_id"
    )
    _require_inventory_superset(base.adapters, successor.adapters, "adapter_id")
    _require_inventory_superset(base.authority, successor.authority, "authority_id")
    _require_inventory_superset(base.budgets, successor.budgets, "budget_id")
    _require_inventory_superset(base.evidence, successor.evidence, "evidence_id")
    successor_nodes = {node.node_id: node for node in successor.nodes}
    for prior in base.nodes:
        current = successor_nodes.get(prior.node_id)
        if current is None:
            raise DagExecutionError(f"graph patch removes node {prior.node_id}")
        exact_fields = ("objective", "authority_id", "budget_id", "rollback")
        if any(
            getattr(prior, field) != getattr(current, field) for field in exact_fields
        ):
            raise DagExecutionError(
                f"graph patch changes protected node {prior.node_id}"
            )
        monotonic_fields = (
            "dependencies",
            "resource_ids",
            "capability_ids",
            "adapter_ids",
            "evidence_ids",
            "acceptance_criteria",
            "roles",
            "lifecycle_stages",
        )
        if any(
            not set(getattr(prior, field)) <= set(getattr(current, field))
            for field in monotonic_fields
        ):
            raise DagExecutionError(f"graph patch weakens node {prior.node_id}")
    return compile_plan(
        successor_plan_bytes,
        expected_plan_digest=patch.successor_plan_digest,
        standard_bytes=standard_bytes,
    )


def _require_inventory_superset(
    prior: tuple[Any, ...], current: tuple[Any, ...], identity_field: str
) -> None:
    current_by_id = {getattr(item, identity_field): item for item in current}
    for item in prior:
        identity = getattr(item, identity_field)
        if current_by_id.get(identity) != item:
            raise DagExecutionError(f"graph patch changes or removes {identity}")


__all__ = [
    "DagExecutionError",
    "DagExecutor",
    "ExecutionBlockerCode",
    "ExecutionEvent",
    "ExecutionJournal",
    "ExecutionRequest",
    "ExecutionSnapshot",
    "GraphPatch",
    "NodeOutcome",
    "NodeState",
    "RunState",
    "validate_graph_patch",
]
