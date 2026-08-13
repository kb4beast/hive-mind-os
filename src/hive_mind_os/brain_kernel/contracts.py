"""Immutable, repository-neutral contracts for the Verifiable Hive Kernel."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any, ClassVar, Mapping

from ..contracts import ROLE_NAMES, ContractValidation, validate_contract
from .canonical import canonical_digest, canonical_document

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_IDS = {
    "mission": re.compile(r"MISSION-[A-Za-z0-9][A-Za-z0-9._-]*\Z"),
    "work": re.compile(r"WORK-[A-Za-z0-9][A-Za-z0-9._-]*\Z"),
    "authority": re.compile(r"AUTH-[A-Za-z0-9][A-Za-z0-9._-]*\Z"),
    "lease": re.compile(r"LEASE-[A-Za-z0-9][A-Za-z0-9._-]*\Z"),
    "attempt": re.compile(r"ATTEMPT-[A-Za-z0-9][A-Za-z0-9._-]*\Z"),
    "memory": re.compile(r"MEMORY-[A-Za-z0-9][A-Za-z0-9._-]*\Z"),
    "candidate": re.compile(r"CANDIDATE-[A-Za-z0-9][A-Za-z0-9._-]*\Z"),
}
_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z")


class MissionState(StrEnum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    READY = "READY"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    INTEGRATING = "INTEGRATING"
    COMPLETED = "COMPLETED"
    WAITING_HUMAN = "WAITING_HUMAN"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ROLLING_BACK = "ROLLING_BACK"


class WorkState(StrEnum):
    PROPOSED = "PROPOSED"
    READY = "READY"
    LEASED = "LEASED"
    RUNNING = "RUNNING"
    AWAITING_VERIFICATION = "AWAITING_VERIFICATION"
    ACCEPTED = "ACCEPTED"
    INTEGRATED = "INTEGRATED"
    BLOCKED_DEPENDENCY = "BLOCKED_DEPENDENCY"
    WAITING_HUMAN = "WAITING_HUMAN"
    RETRYABLE_FAILED = "RETRYABLE_FAILED"
    TERMINAL_FAILED = "TERMINAL_FAILED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


class LeaseState(StrEnum):
    ACTIVE = "ACTIVE"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class MemoryState(StrEnum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    CONTRADICTED = "CONTRADICTED"
    RETRACTED = "RETRACTED"
    EXPIRED = "EXPIRED"
    QUARANTINED = "QUARANTINED"


class EvaluationState(StrEnum):
    SEALED = "SEALED"
    PASSED = "PASSED"
    FAILED = "FAILED"
    ABSTAINED = "ABSTAINED"


class CandidateState(StrEnum):
    PROPOSED = "PROPOSED"
    EVALUATING = "EVALUATING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    QUARANTINED = "QUARANTINED"


class TechnicalCloseoutState(StrEnum):
    TECHNICALLY_VERIFIED = "TECHNICALLY_VERIFIED"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"


def _require(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")


def _identifier(value: str, kind: str) -> None:
    _require(value, f"{kind} id")
    if _IDS[kind].fullmatch(value) is None:
        raise ValueError(f"invalid {kind} id")


def _digest(value: str, label: str = "digest") -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{label} must be lowercase sha256:<64 hex>")


def _sha(value: str) -> None:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise ValueError("base_commit must be a lowercase 40-hex SHA")


def _time(value: str, label: str) -> None:
    if not isinstance(value, str) or _TIME.fullmatch(value) is None:
        raise ValueError(f"{label} must be an RFC 3339 time")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} must be an RFC 3339 time") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must include an offset")


def normalize_portable_path(value: str) -> str:
    """Normalize a relative Windows or POSIX path to portable POSIX spelling."""

    if not isinstance(value, str) or not value:
        raise ValueError("path is required")
    path = value.replace("\\", "/")
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        raise ValueError("path must be relative")
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("path has unsafe segments")
    result = PurePosixPath(*parts).as_posix()
    if result == ".":
        raise ValueError("path is required")
    return result


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _role(value: str) -> None:
    if value not in ROLE_NAMES:
        raise ValueError("role is not registered")


def _nonnegative(value: int, label: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class Budget:
    max_wall_seconds: int
    max_model_calls: int
    max_input_tokens: int
    max_output_tokens: int
    max_cost_microunits: int
    max_tool_calls: int
    max_work_items: int
    max_depth: int

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            _nonnegative(getattr(self, name), name)


class _Contract:
    schema_name: ClassVar[str]

    def to_document(self) -> dict[str, Any]:
        return canonical_document(self)

    def canonical_bytes(self) -> bytes:
        from .canonical import canonical_bytes

        return canonical_bytes(self.to_document())

    def digest(self) -> str:
        return canonical_digest(self.to_document())

    def validate(self) -> ContractValidation:
        return validate_contract(self.schema_name, self.to_document())

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> _Contract:
        """Construct a contract only from a schema-valid, complete JSON object."""

        if not isinstance(document, Mapping):
            raise ValueError("kernel contract document must be an object")
        result = validate_contract(cls.schema_name, dict(document))
        if not result.valid:
            raise ValueError("invalid kernel contract: " + "; ".join(result.issues))
        values = dict(document)
        if cls in {MissionCharter, ConstraintEnvelope, EvaluationPlan}:
            budget_name = "budget" if cls is MissionCharter else "budgets" if cls is ConstraintEnvelope else "regression_budget"
            values[budget_name] = Budget(**values[budget_name])
        enum_fields: dict[type[_Contract], tuple[str, type[StrEnum]]] = {
            MissionCharter: ("status", MissionState),
            WorkItem: ("status", WorkState),
            MemoryRecord: ("state", MemoryState),
            EvaluationPlan: ("state", EvaluationState),
            Candidate: ("state", CandidateState),
            TechnicalCloseoutReport: ("state", TechnicalCloseoutState),
        }
        field = enum_fields.get(cls)
        if field is not None:
            values[field[0]] = field[1](values[field[0]])
        if cls in {ConstraintEnvelope, MemoryRecord, Candidate}:
            values["digest_value"] = values.pop("digest")
        return cls(**values)


@dataclass(frozen=True, slots=True)
class MissionCharter(_Contract):
    schema_name: ClassVar[str] = "brain-kernel-charter"
    schema_version: int
    mission_id: str
    created_at: str
    objective: str
    acceptance_specs: tuple[str, ...]
    repository_root: str
    base_commit: str
    target_branch: str
    policy_fingerprint: str
    role_registry_fingerprint: str
    model_route_fingerprint: str
    budget: Budget
    external_grants: tuple[str, ...]
    protected_branches: tuple[str, ...]
    human_gates: tuple[str, ...]
    status: MissionState

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported schema version")
        _identifier(self.mission_id, "mission")
        _time(self.created_at, "created_at")
        _require(self.objective, "objective")
        if not self.acceptance_specs:
            raise ValueError("acceptance_specs is required")
        if not isinstance(self.repository_root, str) or not self.repository_root:
            raise ValueError("repository_root is required")
        _sha(self.base_commit)
        _require(self.target_branch, "target_branch")
        if self.target_branch in self.protected_branches:
            raise ValueError("target_branch must not be protected")
        for value in (self.policy_fingerprint, self.role_registry_fingerprint, self.model_route_fingerprint):
            _digest(value, "fingerprint")


@dataclass(frozen=True, slots=True)
class WorkItem(_Contract):
    schema_name: ClassVar[str] = "brain-kernel-work-item"
    work_id: str
    mission_id: str
    parent_work_id: str | None
    depth: int
    title: str
    objective: str
    role: str
    risk_tier: str
    dependencies: tuple[str, ...]
    required_inputs: tuple[str, ...]
    expected_outputs: tuple[str, ...]
    acceptance_specs: tuple[str, ...]
    write_scope: tuple[str, ...]
    requested_actions: tuple[str, ...]
    context_request: Mapping[str, Any]
    max_attempts: int
    status: WorkState
    authority_envelope_digest: str
    idempotency_key: str

    def __post_init__(self) -> None:
        _identifier(self.work_id, "work")
        _identifier(self.mission_id, "mission")
        if self.parent_work_id is not None:
            _identifier(self.parent_work_id, "work")
        _nonnegative(self.depth, "depth")
        _require(self.title, "title")
        _require(self.objective, "objective")
        _role(self.role)
        if self.risk_tier not in {"R0", "R1", "R2", "R3", "R4"}:
            raise ValueError("invalid risk_tier")
        object.__setattr__(
            self, "write_scope", tuple(normalize_portable_path(path) for path in self.write_scope)
        )
        if type(self.max_attempts) is not int or self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        _digest(self.authority_envelope_digest)
        _digest(self.idempotency_key, "idempotency_key")


@dataclass(frozen=True, slots=True)
class ConstraintEnvelope(_Contract):
    schema_name: ClassVar[str] = "brain-kernel-authority"
    envelope_id: str
    mission_id: str
    work_id: str
    parent_envelope_digest: str | None
    actor_role: str
    risk_tier: str
    allowed_actions: tuple[str, ...]
    denied_actions: tuple[str, ...]
    path_read_scope: tuple[str, ...]
    path_write_scope: tuple[str, ...]
    network_allowlist: tuple[str, ...]
    data_scopes: tuple[str, ...]
    secret_scopes: tuple[str, ...]
    human_gates: tuple[str, ...]
    budgets: Budget
    expires_at: str
    policy_fingerprint: str
    digest_value: str

    def __post_init__(self) -> None:
        _identifier(self.envelope_id, "authority")
        _identifier(self.mission_id, "mission")
        _identifier(self.work_id, "work")
        if self.parent_envelope_digest is not None:
            _digest(self.parent_envelope_digest, "parent_envelope_digest")
        _role(self.actor_role)
        if self.risk_tier not in {"R0", "R1", "R2", "R3", "R4"}:
            raise ValueError("invalid risk_tier")
        object.__setattr__(
            self,
            "path_read_scope",
            tuple(normalize_portable_path(path) for path in self.path_read_scope),
        )
        object.__setattr__(
            self,
            "path_write_scope",
            tuple(normalize_portable_path(path) for path in self.path_write_scope),
        )
        _time(self.expires_at, "expires_at")
        _digest(self.policy_fingerprint, "policy_fingerprint")
        _digest(self.digest_value, "digest")

    def to_document(self) -> dict[str, Any]:
        document = _Contract.to_document(self)
        document["digest"] = document.pop("digest_value")
        return document

    def content_digest(self) -> str:
        """Pure seal over every field of this envelope except the seal itself."""

        document = self.to_document()
        document.pop("digest")
        return canonical_digest(document)

    def sealed(self) -> ConstraintEnvelope:
        """Return the same authority carrying the digest its contents imply."""

        return replace(self, digest_value=self.content_digest())

    def authority_key(self) -> str:
        """Pure digest of the authority itself, independent of envelope identity."""

        document = self.to_document()
        for name in ("digest", "envelope_id", "parent_envelope_digest"):
            document.pop(name)
        return canonical_digest(document)

    def is_no_broader_than(self, parent: ConstraintEnvelope) -> bool:
        """Pure comparison used by later authority issuers; it performs no effects."""

        return (
            set(self.allowed_actions).issubset(parent.allowed_actions)
            and set(parent.denied_actions).issubset(self.denied_actions)
            and set(self.path_read_scope).issubset(parent.path_read_scope)
            and set(self.path_write_scope).issubset(parent.path_write_scope)
            and set(self.network_allowlist).issubset(parent.network_allowlist)
            and set(self.data_scopes).issubset(parent.data_scopes)
            and set(self.secret_scopes).issubset(parent.secret_scopes)
            and set(parent.human_gates).issubset(self.human_gates)
            and _instant(self.expires_at) <= _instant(parent.expires_at)
            and all(
                getattr(self.budgets, name) <= getattr(parent.budgets, name)
                for name in Budget.__dataclass_fields__
            )
        )


@dataclass(frozen=True, slots=True)
class ExecutionLease:
    lease_id: str
    mission_id: str
    work_id: str
    attempt_id: str
    worker_id: str
    role: str
    lease_token_digest: str
    acquired_at: str
    heartbeat_at: str
    expires_at: str
    authority_envelope_digest: str
    base_state_sequence: int
    read_lock_ids: tuple[str, ...]
    write_lock_ids: tuple[str, ...]
    cancellation_generation: int
    state: LeaseState

    def __post_init__(self) -> None:
        _identifier(self.lease_id, "lease")
        _identifier(self.mission_id, "mission")
        _identifier(self.work_id, "work")
        _identifier(self.attempt_id, "attempt")
        _require(self.worker_id, "worker_id")
        _role(self.role)
        _digest(self.lease_token_digest, "lease_token_digest")
        for label in ("acquired_at", "heartbeat_at", "expires_at"):
            _time(getattr(self, label), label)
        _digest(self.authority_envelope_digest)
        _nonnegative(self.base_state_sequence, "base_state_sequence")
        _nonnegative(self.cancellation_generation, "cancellation_generation")


@dataclass(frozen=True, slots=True)
class RoleResult:
    mission_id: str
    work_id: str
    attempt_id: str
    role: str
    executor_id: str
    context_manifest_digest: str
    authority_envelope_digest: str
    base_artifact_refs: tuple[str, ...]
    candidate_artifact_refs: tuple[str, ...]
    output_artifact_refs: tuple[str, ...]
    claims: tuple[str, ...]
    effect_receipt_refs: tuple[str, ...]
    unresolved_risks: tuple[str, ...]
    requested_next_role: str | None
    self_assessment: str
    result_digest: str

    def __post_init__(self) -> None:
        _identifier(self.mission_id, "mission")
        _identifier(self.work_id, "work")
        _identifier(self.attempt_id, "attempt")
        _role(self.role)
        _require(self.executor_id, "executor_id")
        _digest(self.context_manifest_digest)
        _digest(self.authority_envelope_digest)
        if self.requested_next_role is not None:
            _role(self.requested_next_role)
        _digest(self.result_digest, "result_digest")


@dataclass(frozen=True, slots=True)
class ContextManifest(_Contract):
    schema_name: ClassVar[str] = "brain-kernel-context-manifest"
    mission_id: str
    work_id: str
    attempt_id: str
    role: str
    charter_digest: str
    authority_digest: str
    token_budget: int
    estimated_tokens: int
    hot_items: tuple[str, ...]
    warm_items: tuple[str, ...]
    cold_references: tuple[str, ...]
    excluded_categories: tuple[str, ...]
    excluded_counts: Mapping[str, int]
    conflict_records: tuple[str, ...]
    generator_evaluator_separated: bool
    manifest_digest: str

    def __post_init__(self) -> None:
        _identifier(self.mission_id, "mission")
        _identifier(self.work_id, "work")
        _identifier(self.attempt_id, "attempt")
        _role(self.role)
        _digest(self.charter_digest)
        _digest(self.authority_digest)
        _nonnegative(self.token_budget, "token_budget")
        _nonnegative(self.estimated_tokens, "estimated_tokens")
        if self.estimated_tokens > self.token_budget:
            raise ValueError("estimated_tokens exceeds token_budget")
        if type(self.generator_evaluator_separated) is not bool:
            raise ValueError("generator_evaluator_separated must be boolean")
        _digest(self.manifest_digest, "manifest_digest")


@dataclass(frozen=True, slots=True)
class MemoryRecord(_Contract):
    schema_name: ClassVar[str] = "brain-kernel-memory-record"
    record_id: str
    memory_class: str
    scope: str
    subject_keys: tuple[str, ...]
    content_ref: str
    source_refs: tuple[str, ...]
    authority_level: str
    sensitivity: str
    valid_from: str
    valid_to: str | None
    recorded_at: str
    available_at: str
    state: MemoryState
    supersedes: tuple[str, ...]
    superseded_by: tuple[str, ...]
    evaluator_id: str | None
    outcome_refs: tuple[str, ...]
    retention_policy: str
    digest_value: str

    def __post_init__(self) -> None:
        _identifier(self.record_id, "memory")
        _require(self.memory_class, "memory_class")
        if self.scope not in {"global", "repository", "mission", "role", "work_item"}:
            raise ValueError("invalid memory scope")
        _require(self.content_ref, "content_ref")
        for label in ("valid_from", "recorded_at", "available_at"):
            _time(getattr(self, label), label)
        if self.valid_to is not None:
            _time(self.valid_to, "valid_to")
        _require(self.retention_policy, "retention_policy")
        _digest(self.digest_value, "digest")

    def to_document(self) -> dict[str, Any]:
        document = _Contract.to_document(self)
        document["digest"] = document.pop("digest_value")
        return document


@dataclass(frozen=True, slots=True)
class EffectIntent(_Contract):
    schema_name: ClassVar[str] = "brain-kernel-effect-intent"
    mission_id: str
    work_id: str
    attempt_id: str
    actor_id: str
    role: str
    action: str
    risk_tier: str
    target_adapter: str
    target: str
    parameters_digest: str
    idempotency_key: str
    authority_envelope_digest: str
    expected_preconditions: tuple[str, ...]
    rollback_description: str
    policy_decision_ref: str
    intent_digest: str

    def __post_init__(self) -> None:
        for value, kind in ((self.mission_id, "mission"), (self.work_id, "work"), (self.attempt_id, "attempt")):
            _identifier(value, kind)
        _require(self.actor_id, "actor_id")
        _role(self.role)
        for label in ("action", "target_adapter", "target", "rollback_description", "policy_decision_ref"):
            _require(getattr(self, label), label)
        object.__setattr__(self, "target", normalize_portable_path(self.target))
        for value in (self.parameters_digest, self.idempotency_key, self.authority_envelope_digest, self.intent_digest):
            _digest(value)


@dataclass(frozen=True, slots=True)
class EffectReceipt(_Contract):
    schema_name: ClassVar[str] = "brain-kernel-effect-receipt"
    intent_digest: str
    started_at: str
    ended_at: str
    adapter_identity: str
    adapter_version: str
    observed_precondition_digest: str
    status: str
    stdout_digest: str | None
    stderr_digest: str | None
    produced_identifiers: tuple[str, ...]
    postcondition_digest: str
    retry_of: str | None
    rollback_receipt: str | None

    def __post_init__(self) -> None:
        for label in ("intent_digest", "observed_precondition_digest", "postcondition_digest"):
            _digest(getattr(self, label), label)
        for label in ("started_at", "ended_at"):
            _time(getattr(self, label), label)
        _require(self.adapter_identity, "adapter_identity")
        _require(self.adapter_version, "adapter_version")
        if self.status not in {"SUCCEEDED", "FAILED", "ABSTAINED"}:
            raise ValueError("invalid receipt status")
        for value in (self.stdout_digest, self.stderr_digest, self.retry_of, self.rollback_receipt):
            if value is not None:
                _digest(value)


@dataclass(frozen=True, slots=True)
class EvaluationPlan(_Contract):
    schema_name: ClassVar[str] = "brain-kernel-evaluation"
    plan_id: str
    base_commit: str
    base_tree_digest: str
    acceptance_commands: tuple[str, ...]
    environment_requirements: tuple[str, ...]
    allowed_test_paths: tuple[str, ...]
    test_digests: tuple[str, ...]
    security_checks: tuple[str, ...]
    contamination_checks: tuple[str, ...]
    evaluator_requirements: tuple[str, ...]
    evidence_bundle_format: str
    pass_fail_abstain_rules: tuple[str, ...]
    regression_budget: Budget
    state: EvaluationState
    plan_digest: str

    def __post_init__(self) -> None:
        _require(self.plan_id, "plan_id")
        _sha(self.base_commit)
        _digest(self.base_tree_digest)
        if not self.acceptance_commands:
            raise ValueError("acceptance_commands is required")
        object.__setattr__(
            self,
            "allowed_test_paths",
            tuple(normalize_portable_path(path) for path in self.allowed_test_paths),
        )
        for digest in (*self.test_digests, self.plan_digest):
            _digest(digest)
        _require(self.evidence_bundle_format, "evidence_bundle_format")


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    plan_digest: str
    candidate_digest: str
    evaluator_id: str
    state: EvaluationState
    check_results: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    result_digest: str

    def __post_init__(self) -> None:
        for label in ("plan_digest", "candidate_digest", "result_digest"):
            _digest(getattr(self, label), label)
        _require(self.evaluator_id, "evaluator_id")


@dataclass(frozen=True, slots=True)
class HistoricalEvidenceReference(_Contract):
    """Opaque, immutable metadata for evidence produced before the kernel."""

    schema_name: ClassVar[str] = "brain-kernel-historical-evidence-reference"
    receipt_ref: str
    receipt_digest: str
    provenance_label: str
    retention_note: str

    def __post_init__(self) -> None:
        _require(self.receipt_ref, "receipt_ref")
        _digest(self.receipt_digest, "receipt_digest")
        _require(self.provenance_label, "provenance_label")
        _require(self.retention_note, "retention_note")


@dataclass(frozen=True, slots=True)
class TechnicalCloseoutReport(_Contract):
    """A replayable local technical finding, never a customer-success claim."""

    schema_name: ClassVar[str] = "brain-kernel-technical-closeout-report"
    mission_id: str
    event_head_digest: str
    projection_digest: str
    required_roles: tuple[str, ...]
    fulfilled_roles: tuple[str, ...]
    missing_obligations: tuple[str, ...]
    integrated_work_ids: tuple[str, ...]
    evaluation_result_digests: tuple[str, ...]
    evidence_bundle_digests: tuple[str, ...]
    state: TechnicalCloseoutState
    report_digest: str

    def __post_init__(self) -> None:
        _identifier(self.mission_id, "mission")
        for value in (self.event_head_digest, self.projection_digest, self.report_digest):
            _digest(value)
        if not self.required_roles or len(set(self.required_roles)) != len(self.required_roles):
            raise ValueError("required_roles must be non-empty and unique")
        if len(set(self.fulfilled_roles)) != len(self.fulfilled_roles):
            raise ValueError("fulfilled_roles must be unique")
        for role in (*self.required_roles, *self.fulfilled_roles):
            _role(role)
        if not set(self.fulfilled_roles).issubset(self.required_roles):
            raise ValueError("fulfilled_roles must be required roles")
        for work_id in self.integrated_work_ids:
            _identifier(work_id, "work")
        for digest in (*self.evaluation_result_digests, *self.evidence_bundle_digests):
            _digest(digest)
        if not isinstance(self.state, TechnicalCloseoutState):
            raise ValueError("invalid technical closeout state")


@dataclass(frozen=True, slots=True)
class Candidate(_Contract):
    schema_name: ClassVar[str] = "brain-kernel-candidate"
    candidate_id: str
    mission_id: str
    base_commit: str
    artifact_refs: tuple[str, ...]
    state: CandidateState
    evaluation_plan_digest: str
    digest_value: str

    def __post_init__(self) -> None:
        _identifier(self.candidate_id, "candidate")
        _identifier(self.mission_id, "mission")
        _sha(self.base_commit)
        _digest(self.evaluation_plan_digest)
        _digest(self.digest_value, "digest")

    def to_document(self) -> dict[str, Any]:
        document = _Contract.to_document(self)
        document["digest"] = document.pop("digest_value")
        return document
