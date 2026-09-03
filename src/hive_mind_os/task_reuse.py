"""Exact task fingerprints and fail-closed durable reuse decisions."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import Any, Mapping, Sequence

from .brain_kernel.canonical import canonical_bytes, canonical_digest
from .runtime_contracts import strict_json_object
from .wave_manifest import CandidateIdentity


class TaskReuseError(RuntimeError):
    """Task reuse evidence is malformed, corrupt, or contradictory."""


class TaskRecordState(StrEnum):
    ACTIVE = "ACTIVE"
    CHECKPOINTED = "CHECKPOINTED"
    CANDIDATE_SEALED = "CANDIDATE_SEALED"
    VERIFIED = "VERIFIED"
    INTEGRATED = "INTEGRATED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class ReuseDisposition(StrEnum):
    EXACT_REUSE = "exact-reuse"
    VERIFY_EXISTING = "verify-existing"
    RESUME_ACTIVE = "resume-active"
    REPAIR_EXISTING = "repair-existing"
    EXECUTE_NEW = "execute-new"
    STALE = "stale"
    CONFLICT = "conflict"
    BLOCKED = "blocked"


_STATE_RANK = {
    TaskRecordState.ACTIVE: 1,
    TaskRecordState.CHECKPOINTED: 2,
    TaskRecordState.CANDIDATE_SEALED: 3,
    TaskRecordState.VERIFIED: 4,
    TaskRecordState.INTEGRATED: 5,
}
_TERMINAL_TASK_STATES = {
    TaskRecordState.INTEGRATED,
    TaskRecordState.FAILED,
    TaskRecordState.BLOCKED,
    TaskRecordState.CANCELLED,
}


def _valid_state_successor(previous: TaskRecordState, current: TaskRecordState) -> bool:
    if previous in _TERMINAL_TASK_STATES:
        return current is previous
    if current in {TaskRecordState.FAILED, TaskRecordState.BLOCKED, TaskRecordState.CANCELLED}:
        return True
    return _STATE_RANK.get(current, 0) >= _STATE_RANK.get(previous, 0)


def _required(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value


def _digest(value: str, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("sha256:")
        or len(value) != 71
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{label} must be a lowercase sha256 digest")
    return value


def _unique_digests(values: Sequence[str], label: str) -> tuple[str, ...]:
    result = tuple(values)
    for value in result:
        _digest(value, label)
    if len(set(result)) != len(result):
        raise ValueError(f"{label} must not contain duplicates")
    return result


@dataclass(frozen=True, slots=True)
class TaskFingerprint:
    """All inputs whose equality is necessary for safe task reuse."""

    plan_digest: str
    node_id: str
    subject_id: str
    subject_snapshot_digest: str
    relevant_surface_digest: str
    direct_dependency_receipt_digests: tuple[str, ...]
    authority_digest: str
    compiler_digest: str
    policy_digest: str
    environment_digest: str
    task_contract_digest: str

    def __post_init__(self) -> None:
        _required(self.node_id, "node_id")
        _required(self.subject_id, "subject_id")
        for label in (
            "plan_digest",
            "subject_snapshot_digest",
            "relevant_surface_digest",
            "authority_digest",
            "compiler_digest",
            "policy_digest",
            "environment_digest",
            "task_contract_digest",
        ):
            _digest(getattr(self, label), label)
        dependencies = _unique_digests(
            self.direct_dependency_receipt_digests,
            "direct_dependency_receipt_digest",
        )
        # Dependency order is semantically meaningful and must come from the
        # plan; silently sorting would let a caller fingerprint a different DAG.
        object.__setattr__(self, "direct_dependency_receipt_digests", dependencies)

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "plan_digest": self.plan_digest,
            "node_id": self.node_id,
            "subject_id": self.subject_id,
            "subject_snapshot_digest": self.subject_snapshot_digest,
            "relevant_surface_digest": self.relevant_surface_digest,
            "direct_dependency_receipt_digests": list(
                self.direct_dependency_receipt_digests
            ),
            "authority_digest": self.authority_digest,
            "compiler_digest": self.compiler_digest,
            "policy_digest": self.policy_digest,
            "environment_digest": self.environment_digest,
            "task_contract_digest": self.task_contract_digest,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> TaskFingerprint:
        fields = {
            "schema_version",
            "plan_digest",
            "node_id",
            "subject_id",
            "subject_snapshot_digest",
            "relevant_surface_digest",
            "direct_dependency_receipt_digests",
            "authority_digest",
            "compiler_digest",
            "policy_digest",
            "environment_digest",
            "task_contract_digest",
        }
        dependencies = value.get("direct_dependency_receipt_digests")
        if (
            set(value) != fields
            or type(value.get("schema_version")) is not int
            or value.get("schema_version") != 1
            or not isinstance(dependencies, list)
            or not all(isinstance(item, str) for item in dependencies)
        ):
            raise TaskReuseError("task fingerprint has an unknown shape")
        try:
            return cls(
                plan_digest=value["plan_digest"],
                node_id=value["node_id"],
                subject_id=value["subject_id"],
                subject_snapshot_digest=value["subject_snapshot_digest"],
                relevant_surface_digest=value["relevant_surface_digest"],
                direct_dependency_receipt_digests=tuple(dependencies),
                authority_digest=value["authority_digest"],
                compiler_digest=value["compiler_digest"],
                policy_digest=value["policy_digest"],
                environment_digest=value["environment_digest"],
                task_contract_digest=value["task_contract_digest"],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise TaskReuseError("task fingerprint is invalid") from error


@dataclass(frozen=True, slots=True)
class TaskReceipt:
    receipt_id: str
    fingerprint: TaskFingerprint
    state: TaskRecordState
    sequence: int
    candidate: CandidateIdentity | None = None
    validation_receipt_digest: str | None = None
    integrated_target: CandidateIdentity | None = None
    blocker_digest: str | None = None
    previous_receipt_digest: str | None = None

    def __post_init__(self) -> None:
        _required(self.receipt_id, "receipt_id")
        if not isinstance(self.fingerprint, TaskFingerprint):
            raise ValueError("fingerprint must be a TaskFingerprint")
        if not isinstance(self.state, TaskRecordState):
            raise ValueError("state must be a TaskRecordState")
        if type(self.sequence) is not int or self.sequence < 1:
            raise ValueError("sequence must be a positive integer")
        for label in (
            "validation_receipt_digest",
            "blocker_digest",
            "previous_receipt_digest",
        ):
            value = getattr(self, label)
            if value is not None:
                _digest(value, label)
        if self.state in {
            TaskRecordState.CANDIDATE_SEALED,
            TaskRecordState.VERIFIED,
            TaskRecordState.INTEGRATED,
        } and self.candidate is None:
            raise ValueError(f"{self.state.value} task receipt requires a candidate")
        if self.state is TaskRecordState.VERIFIED and self.validation_receipt_digest is None:
            raise ValueError("verified task receipt requires validation evidence")
        if self.state is TaskRecordState.INTEGRATED and (
            self.validation_receipt_digest is None or self.integrated_target is None
        ):
            raise ValueError("integrated task receipt requires validation and target evidence")
        if self.candidate is not None and self.candidate.subject_id != self.fingerprint.subject_id:
            raise ValueError("candidate belongs to another subject")
        if (
            self.integrated_target is not None
            and self.integrated_target.subject_id != self.fingerprint.subject_id
        ):
            raise ValueError("integrated target belongs to another subject")
        if self.state in {
            TaskRecordState.BLOCKED,
            TaskRecordState.FAILED,
        } and self.blocker_digest is None:
            raise ValueError("blocked or failed task receipt requires failure evidence")

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "receipt_id": self.receipt_id,
            "fingerprint": self.fingerprint.to_document(),
            "fingerprint_digest": self.fingerprint.digest,
            "state": self.state.value,
            "sequence": self.sequence,
            "candidate": None if self.candidate is None else self.candidate.to_document(),
            "validation_receipt_digest": self.validation_receipt_digest,
            "integrated_target": (
                None if self.integrated_target is None else self.integrated_target.to_document()
            ),
            "blocker_digest": self.blocker_digest,
            "previous_receipt_digest": self.previous_receipt_digest,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> TaskReceipt:
        fields = {
            "schema_version",
            "receipt_id",
            "fingerprint",
            "fingerprint_digest",
            "state",
            "sequence",
            "candidate",
            "validation_receipt_digest",
            "integrated_target",
            "blocker_digest",
            "previous_receipt_digest",
        }
        if (
            set(value) != fields
            or type(value.get("schema_version")) is not int
            or value.get("schema_version") != 1
        ):
            raise TaskReuseError("task receipt has an unknown shape")
        fingerprint_value = value.get("fingerprint")
        candidate_value = value.get("candidate")
        target_value = value.get("integrated_target")
        if not isinstance(fingerprint_value, Mapping):
            raise TaskReuseError("task receipt fingerprint is malformed")
        if candidate_value is not None and not isinstance(candidate_value, Mapping):
            raise TaskReuseError("task receipt candidate is malformed")
        if target_value is not None and not isinstance(target_value, Mapping):
            raise TaskReuseError("task receipt target is malformed")
        try:
            fingerprint = TaskFingerprint.from_document(fingerprint_value)
            if value["fingerprint_digest"] != fingerprint.digest:
                raise TaskReuseError("task receipt fingerprint digest is invalid")
            return cls(
                receipt_id=value["receipt_id"],
                fingerprint=fingerprint,
                state=TaskRecordState(value["state"]),
                sequence=value["sequence"],
                candidate=(
                    None
                    if candidate_value is None
                    else CandidateIdentity.from_document(candidate_value)
                ),
                validation_receipt_digest=value["validation_receipt_digest"],
                integrated_target=(
                    None
                    if target_value is None
                    else CandidateIdentity.from_document(target_value)
                ),
                blocker_digest=value["blocker_digest"],
                previous_receipt_digest=value["previous_receipt_digest"],
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, TaskReuseError):
                raise
            raise TaskReuseError("task receipt is invalid") from error


@dataclass(frozen=True, slots=True)
class ReuseDecision:
    disposition: ReuseDisposition
    fingerprint_digest: str
    reason: str
    receipt: TaskReceipt | None = None

    @property
    def complete(self) -> bool:
        return self.disposition is ReuseDisposition.EXACT_REUSE


class TaskReuseIndex:
    """Append-only receipt index used before any worker launch."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._lock = RLock()
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS task_receipts (
                    global_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    receipt_id TEXT NOT NULL,
                    receipt_sequence INTEGER NOT NULL,
                    plan_digest TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    fingerprint_digest TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    receipt_digest TEXT NOT NULL UNIQUE,
                    UNIQUE(receipt_id, receipt_sequence)
                );
                CREATE TRIGGER IF NOT EXISTS task_receipts_no_update
                BEFORE UPDATE ON task_receipts
                BEGIN SELECT RAISE(ABORT, 'task receipts are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS task_receipts_no_delete
                BEFORE DELETE ON task_receipts
                BEGIN SELECT RAISE(ABORT, 'task receipts are append-only'); END;
                """
            )
        self.verify()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> TaskReuseIndex:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _decode(row: sqlite3.Row) -> TaskReceipt:
        try:
            value = strict_json_object(str(row["payload_json"]).encode("utf-8"))
        except (UnicodeError, ValueError) as error:
            raise TaskReuseError("task receipt history contains invalid JSON") from error
        receipt = TaskReceipt.from_document(value)
        if (
            receipt.receipt_id != row["receipt_id"]
            or receipt.sequence != row["receipt_sequence"]
            or receipt.fingerprint.plan_digest != row["plan_digest"]
            or receipt.fingerprint.node_id != row["node_id"]
            or receipt.fingerprint.digest != row["fingerprint_digest"]
            or receipt.digest != row["receipt_digest"]
        ):
            raise TaskReuseError("task receipt index disagrees with payload")
        if row["payload_json"] != canonical_bytes(receipt.to_document()).decode():
            raise TaskReuseError("task receipt payload is not canonical")
        return receipt

    def verify(self) -> None:
        previous: dict[str, str | None] = {}
        sequences: dict[str, int] = {}
        fingerprints: dict[str, str] = {}
        states: dict[str, TaskRecordState] = {}
        for row in self.connection.execute(
            "SELECT * FROM task_receipts ORDER BY global_sequence"
        ):
            receipt = self._decode(row)
            expected = sequences.get(receipt.receipt_id, 1)
            if receipt.sequence != expected:
                raise TaskReuseError("task receipt sequence is discontinuous")
            if receipt.previous_receipt_digest != previous.get(receipt.receipt_id):
                raise TaskReuseError("task receipt chain is broken")
            prior_fingerprint = fingerprints.setdefault(
                receipt.receipt_id, receipt.fingerprint.digest
            )
            if prior_fingerprint != receipt.fingerprint.digest:
                raise TaskReuseError("task receipt history changed its fingerprint")
            prior_state = states.get(receipt.receipt_id)
            if prior_state is not None and not _valid_state_successor(
                prior_state, receipt.state
            ):
                raise TaskReuseError("task receipt history contains a state regression")
            previous[receipt.receipt_id] = receipt.digest
            sequences[receipt.receipt_id] = expected + 1
            states[receipt.receipt_id] = receipt.state

    def append(self, receipt: TaskReceipt, *, idempotency_key: str) -> TaskReceipt:
        _required(idempotency_key, "idempotency_key")
        encoded = canonical_bytes(receipt.to_document()).decode()
        with self._lock:
            try:
                self.connection.execute("BEGIN IMMEDIATE")
                retry = self.connection.execute(
                    "SELECT * FROM task_receipts WHERE idempotency_key=?",
                    (idempotency_key,),
                ).fetchone()
                if retry is not None:
                    if retry["payload_json"] != encoded:
                        raise TaskReuseError("idempotency key is bound to another task receipt")
                    result = self._decode(retry)
                    self.connection.commit()
                    return result
                last = self.connection.execute(
                    """
                    SELECT * FROM task_receipts WHERE receipt_id=?
                     ORDER BY receipt_sequence DESC LIMIT 1
                    """,
                    (receipt.receipt_id,),
                ).fetchone()
                expected = 1 if last is None else int(last["receipt_sequence"]) + 1
                if receipt.sequence != expected:
                    raise TaskReuseError("task receipt compare-and-swap sequence failed")
                previous_digest = None if last is None else str(last["receipt_digest"])
                if receipt.previous_receipt_digest != previous_digest:
                    raise TaskReuseError("task receipt does not extend the exact prior receipt")
                if last is not None:
                    prior = self._decode(last)
                    if receipt.fingerprint != prior.fingerprint:
                        raise TaskReuseError("task receipt fingerprint is immutable")
                    if not _valid_state_successor(prior.state, receipt.state):
                        raise TaskReuseError("task receipt state cannot regress")
                self.connection.execute(
                    """
                    INSERT INTO task_receipts(
                        receipt_id, receipt_sequence, plan_digest, node_id,
                        fingerprint_digest, idempotency_key, payload_json, receipt_digest
                    ) VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (
                        receipt.receipt_id,
                        receipt.sequence,
                        receipt.fingerprint.plan_digest,
                        receipt.fingerprint.node_id,
                        receipt.fingerprint.digest,
                        idempotency_key,
                        encoded,
                        receipt.digest,
                    ),
                )
                self.connection.commit()
                return receipt
            except BaseException:
                self.connection.rollback()
                raise

    def receipts_for(self, plan_digest: str, node_id: str) -> tuple[TaskReceipt, ...]:
        _digest(plan_digest, "plan_digest")
        _required(node_id, "node_id")
        with self._lock:
            self.verify()
            rows = tuple(
                self.connection.execute(
                    """
                    SELECT * FROM task_receipts WHERE plan_digest=? AND node_id=?
                     ORDER BY global_sequence
                    """,
                    (plan_digest, node_id),
                )
            )
            latest: dict[str, TaskReceipt] = {}
            for row in rows:
                receipt = self._decode(row)
                latest[receipt.receipt_id] = receipt
            return tuple(latest.values())

    def decide(self, fingerprint: TaskFingerprint) -> ReuseDecision:
        try:
            records = self.receipts_for(fingerprint.plan_digest, fingerprint.node_id)
        except (TaskReuseError, sqlite3.DatabaseError) as error:
            return ReuseDecision(
                ReuseDisposition.BLOCKED,
                fingerprint.digest,
                f"task reuse evidence is corrupt: {type(error).__name__}",
            )
        return classify_reuse(fingerprint, records)


def classify_reuse(
    fingerprint: TaskFingerprint, records: Sequence[TaskReceipt]
) -> ReuseDecision:
    """Classify existing work without treating an unaccepted branch as complete."""

    exact = [item for item in records if item.fingerprint == fingerprint]
    stale = [item for item in records if item.fingerprint != fingerprint]
    if exact:
        blocked = [item for item in exact if item.state is TaskRecordState.BLOCKED]
        if blocked:
            return ReuseDecision(
                ReuseDisposition.BLOCKED,
                fingerprint.digest,
                "exact task retains an unresolved evidence-bound blocker",
                blocked[-1],
            )
        integrated = [item for item in exact if item.state is TaskRecordState.INTEGRATED]
        if integrated and any(item.state is TaskRecordState.ACTIVE for item in exact):
            return ReuseDecision(
                ReuseDisposition.CONFLICT,
                fingerprint.digest,
                "an active attempt competes with an exact integrated receipt",
            )
        exact_targets = {
            canonical_digest(item.integrated_target.to_document())
            for item in integrated
            if item.integrated_target is not None
        }
        exact_candidates = {
            canonical_digest(item.candidate.to_document())
            for item in integrated
            if item.candidate is not None
        }
        if len(exact_targets) > 1 or len(exact_candidates) > 1:
            return ReuseDecision(
                ReuseDisposition.CONFLICT,
                fingerprint.digest,
                "exact fingerprint has conflicting integrated identities",
            )
        if integrated:
            receipt = integrated[-1]
            if (
                receipt.candidate is None
                or receipt.integrated_target is None
                or receipt.validation_receipt_digest is None
            ):
                return ReuseDecision(
                    ReuseDisposition.BLOCKED,
                    fingerprint.digest,
                    "integrated receipt lacks exact validation evidence",
                )
            return ReuseDecision(
                ReuseDisposition.EXACT_REUSE,
                fingerprint.digest,
                "validated integrated receipt exactly matches every fingerprint input",
                receipt,
            )
        active = [item for item in exact if item.state is TaskRecordState.ACTIVE]
        if len(active) > 1:
            return ReuseDecision(
                ReuseDisposition.CONFLICT,
                fingerprint.digest,
                "multiple active attempts claim the exact task",
            )
        if active:
            return ReuseDecision(
                ReuseDisposition.RESUME_ACTIVE,
                fingerprint.digest,
                "one exact active attempt is adoptable",
                active[-1],
            )
        verifiable = [
            item
            for item in exact
            if item.state in {TaskRecordState.CANDIDATE_SEALED, TaskRecordState.VERIFIED}
        ]
        if verifiable:
            identities = {
                canonical_digest(item.candidate.to_document())
                for item in verifiable
                if item.candidate is not None
            }
            if len(identities) != 1:
                return ReuseDecision(
                    ReuseDisposition.CONFLICT,
                    fingerprint.digest,
                    "exact task has competing sealed candidates",
                )
            return ReuseDecision(
                ReuseDisposition.VERIFY_EXISTING,
                fingerprint.digest,
                "an exact sealed candidate exists but is not integrated",
                verifiable[-1],
            )
        repairable = [
            item
            for item in exact
            if item.state in {
                TaskRecordState.CHECKPOINTED,
                TaskRecordState.FAILED,
                TaskRecordState.CANCELLED,
            }
        ]
        if repairable:
            return ReuseDecision(
                ReuseDisposition.REPAIR_EXISTING,
                fingerprint.digest,
                "exact prior work is incomplete or failed",
                repairable[-1],
            )
    if stale:
        return ReuseDecision(
            ReuseDisposition.STALE,
            fingerprint.digest,
            "existing work differs in content, dependency, authority, policy, environment, contract, or subject identity",
            stale[-1],
        )
    return ReuseDecision(
        ReuseDisposition.EXECUTE_NEW,
        fingerprint.digest,
        "no prior work exists for this exact task",
    )


def task_fingerprint(**values: Any) -> TaskFingerprint:
    """Named constructor retained as the single public fingerprinting entry point."""

    return TaskFingerprint(**values)


__all__ = [
    "ReuseDecision",
    "ReuseDisposition",
    "TaskFingerprint",
    "TaskReceipt",
    "TaskRecordState",
    "TaskReuseError",
    "TaskReuseIndex",
    "classify_reuse",
    "task_fingerprint",
]
