"""Durable, fail-closed provenance for a single logical model-backed role turn.

The ledger deliberately stores neither a prompt, a provider response, credentials, nor
free-form provider error text.  It preserves only bounded identifiers and SHA-256
content locators.  Those locators detect an inconsistent local record; they are not
authentication of a provider, host, or model result.

Callers must persist :meth:`ModelTurnStore.start_dispatch` immediately before making a
provider call.  A process interruption after that transition is deliberately ambiguous:
the store quarantines the logical turn rather than permitting a replayed provider call.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Callable, Mapping, Sequence

from .contracts import ROLE_NAMES, validate_contract
from .model_provider import redact
from .models import AgentResult, Evidence, Role

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_HOST = re.compile(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_STATE_REF = re.compile(r"MISSION_STATE:[^:\s]+:[1-9][0-9]*\Z")
_LOGICAL_TURN = re.compile(r"MTURN-[0-9a-f]{64}\Z")


class ModelTurnStateError(RuntimeError):
    """Raised when durable model-turn provenance is incomplete or contradictory."""


class ModelTurnPhase(StrEnum):
    PLANNED = "planned"
    DISPATCH_STARTED = "dispatch_started"
    COMPLETED = "completed"
    AMBIGUOUS = "ambiguous"


class ModelTurnOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    INVALID_OUTPUT = "invalid_output"
    PROVIDER_RESPONSE_FAILURE = "provider_response_failure"


class ModelTurnAmbiguity(StrEnum):
    PROVIDER_OUTCOME_UNKNOWN = "provider_outcome_unknown"
    INTERRUPTED_AFTER_DISPATCH_START = "interrupted_after_dispatch_start"


@dataclass(frozen=True, slots=True)
class ModelTurnBudget:
    """The immutable local resource ceiling for one durable model mission.

    This is deliberately an accounting ceiling, not an externally authorized lease.
    Reservations are retained after an ambiguous call: releasing a reservation would
    make an uncertain provider invocation look free and permit budget evasion.
    """

    mission_id: str
    max_episodes: int
    max_tool_calls: int
    max_compute_units: float
    max_tool_calls_per_episode: int
    max_compute_units_per_episode: float

    def __post_init__(self) -> None:
        _require_identifier(self.mission_id, "model-turn budget mission ID")
        values = (
            self.max_episodes,
            self.max_tool_calls,
            self.max_compute_units,
            self.max_tool_calls_per_episode,
            self.max_compute_units_per_episode,
        )
        numeric = (self.max_compute_units, self.max_compute_units_per_episode)
        if (
            type(self.max_episodes) is not int
            or type(self.max_tool_calls) is not int
            or type(self.max_tool_calls_per_episode) is not int
            or any(
                not isinstance(value, (int, float)) or isinstance(value, bool)
                for value in numeric
            )
            or any(value < 0 for value in values)
            or not math.isfinite(float(self.max_compute_units))
            or not math.isfinite(float(self.max_compute_units_per_episode))
        ):
            raise ModelTurnStateError("model-turn budget limits must be finite nonnegative values")

    def to_dict(self) -> dict[str, object]:
        return {
            "mission_id": self.mission_id,
            "max_episodes": self.max_episodes,
            "max_tool_calls": self.max_tool_calls,
            "max_compute_units": self.max_compute_units,
            "max_tool_calls_per_episode": self.max_tool_calls_per_episode,
            "max_compute_units_per_episode": self.max_compute_units_per_episode,
        }

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


@dataclass(frozen=True, slots=True)
class ModelTurnBudgetReservation:
    """A non-releasable pre-dispatch allowance bound to one logical turn."""

    logical_turn_id: str
    mission_id: str
    episodes: int
    tool_calls: int
    compute_units: float

    @classmethod
    def create(
        cls,
        plan: "ModelTurnPlan",
        *,
        tool_calls: int = 1,
        compute_units: float,
    ) -> "ModelTurnBudgetReservation":
        if type(tool_calls) is not int or tool_calls != 1:
            raise ModelTurnStateError("a durable model turn must reserve exactly one call")
        if (
            not isinstance(compute_units, (int, float))
            or isinstance(compute_units, bool)
            or compute_units <= 0
            or not math.isfinite(float(compute_units))
        ):
            raise ModelTurnStateError("model-turn reserved compute must be a positive finite number")
        return cls(
            plan.logical_turn_id,
            plan.mission_id,
            1,
            tool_calls,
            float(compute_units),
        )

    @classmethod
    def from_dict(cls, document: Mapping[str, object]) -> "ModelTurnBudgetReservation":
        logical_turn_id = document.get("logical_turn_id")
        if not isinstance(logical_turn_id, str) or not _LOGICAL_TURN.fullmatch(logical_turn_id):
            raise ModelTurnStateError("model-turn reservation logical ID is malformed")
        mission_id = _require_identifier(document.get("mission_id"), "model-turn reservation mission ID")
        episodes = document.get("episodes")
        tool_calls = document.get("tool_calls")
        compute_units = document.get("compute_units")
        if type(episodes) is not int or episodes != 1:
            raise ModelTurnStateError("model-turn reservation must reserve exactly one episode")
        if type(tool_calls) is not int or tool_calls != 1:
            raise ModelTurnStateError("model-turn reservation must reserve exactly one call")
        if (
            not isinstance(compute_units, (int, float))
            or isinstance(compute_units, bool)
            or compute_units <= 0
            or not math.isfinite(float(compute_units))
        ):
            raise ModelTurnStateError("model-turn reservation compute is malformed")
        return cls(logical_turn_id, mission_id, episodes, tool_calls, float(compute_units))

    def to_dict(self) -> dict[str, object]:
        return {
            "logical_turn_id": self.logical_turn_id,
            "mission_id": self.mission_id,
            "episodes": self.episodes,
            "tool_calls": self.tool_calls,
            "compute_units": self.compute_units,
        }

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise ModelTurnStateError("model-turn provenance is not canonical JSON") from error


def _digest(value: object) -> str:
    return f"sha256:{sha256(_canonical_json(value)).hexdigest()}"


def _utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ModelTurnStateError("model-turn clock must produce an offset-aware time")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _require_identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ModelTurnStateError(f"{label} must be a bounded non-secret identifier")
    return value


def _require_digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ModelTurnStateError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _ensure_contract(name: str, document: Mapping[str, object]) -> None:
    validation = validate_contract(name, dict(document))
    if not validation.valid:
        raise ModelTurnStateError(
            f"{name} violates its closed contract: " + "; ".join(validation.issues)
        )


@dataclass(frozen=True, slots=True)
class ModelProviderIdentity:
    """A redacted provider selector, never a credential or endpoint URL."""

    kind: str
    base_url_host: str
    model_id: str

    @classmethod
    def from_dict(cls, document: Mapping[str, object]) -> ModelProviderIdentity:
        kind = _require_identifier(document.get("kind"), "provider kind")
        model_id = _require_identifier(document.get("model_id"), "provider model ID")
        host = document.get("base_url_host")
        if not isinstance(host, str) or not _HOST.fullmatch(host):
            raise ModelTurnStateError("provider base URL host must be a bounded hostname")
        if host != host.casefold():
            raise ModelTurnStateError("provider base URL host must be lowercase")
        return cls(kind, host, model_id)

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "base_url_host": self.base_url_host,
            "model_id": self.model_id,
        }


@dataclass(frozen=True, slots=True)
class ModelTurnPlan:
    """A deterministic, non-secret intent for exactly one logical provider turn."""

    logical_turn_id: str
    mission_id: str
    state_ref: str
    role: str
    work_item_id: str
    provider: ModelProviderIdentity
    prompt_digest: str
    request_digest: str
    acceptance_specification_id: str
    acceptance_specification_digest: str
    role_contract_digest: str
    configuration_digest: str
    selection_digest: str
    policy_decision_ref: str
    lease_id: str
    redaction_policy_digest: str

    @classmethod
    def create(
        cls,
        *,
        mission_id: str,
        state_ref: str,
        role: str,
        work_item_id: str,
        provider: ModelProviderIdentity,
        prompt_digest: str,
        request_digest: str,
        acceptance_specification_id: str,
        acceptance_specification_digest: str,
        role_contract_digest: str,
        configuration_digest: str,
        selection_digest: str,
        policy_decision_ref: str,
        lease_id: str,
        redaction_policy_digest: str,
    ) -> ModelTurnPlan:
        payload = {
            "schema_version": 1,
            "mission_id": mission_id,
            "state_ref": state_ref,
            "role": role,
            "work_item_id": work_item_id,
            "provider": provider.to_dict(),
            "prompt_digest": prompt_digest,
            "request_digest": request_digest,
            "acceptance_specification_id": acceptance_specification_id,
            "acceptance_specification_digest": acceptance_specification_digest,
            "role_contract_digest": role_contract_digest,
            "configuration_digest": configuration_digest,
            "selection_digest": selection_digest,
            "policy_decision_ref": policy_decision_ref,
            "lease_id": lease_id,
            "redaction_policy_digest": redaction_policy_digest,
        }
        logical_turn_id = "MTURN-" + sha256(_canonical_json(payload)).hexdigest()
        payload["logical_turn_id"] = logical_turn_id
        _ensure_contract("model-turn-plan", payload)
        return cls(
            logical_turn_id,
            mission_id,
            state_ref,
            role,
            work_item_id,
            provider,
            prompt_digest,
            request_digest,
            acceptance_specification_id,
            acceptance_specification_digest,
            role_contract_digest,
            configuration_digest,
            selection_digest,
            policy_decision_ref,
            lease_id,
            redaction_policy_digest,
        )

    @classmethod
    def from_dict(cls, document: Mapping[str, object]) -> ModelTurnPlan:
        _ensure_contract("model-turn-plan", document)
        provider_value = document.get("provider")
        if not isinstance(provider_value, Mapping):
            raise ModelTurnStateError("model-turn plan provider is required")
        provider = ModelProviderIdentity.from_dict(provider_value)
        values = {
            field: _require_identifier(document.get(field), f"model-turn plan {field}")
            for field in (
                "mission_id",
                "work_item_id",
                "acceptance_specification_id",
                "policy_decision_ref",
                "lease_id",
            )
        }
        state_ref = document.get("state_ref")
        if not isinstance(state_ref, str) or not _STATE_REF.fullmatch(state_ref):
            raise ModelTurnStateError("model-turn plan state_ref is malformed")
        if not state_ref.startswith(f"MISSION_STATE:{values['mission_id']}:"):
            raise ModelTurnStateError("model-turn plan state_ref does not bind mission")
        role = document.get("role")
        if not isinstance(role, str) or role not in ROLE_NAMES:
            raise ModelTurnStateError("model-turn plan role is not a registered role")
        prompt_digest = _require_digest(document.get("prompt_digest"), "prompt digest")
        request_digest = _require_digest(document.get("request_digest"), "request digest")
        digests = {
            field: _require_digest(document.get(field), field.replace("_", " "))
            for field in (
                "acceptance_specification_digest",
                "role_contract_digest",
                "configuration_digest",
                "selection_digest",
                "redaction_policy_digest",
            )
        }
        supplied_id = document.get("logical_turn_id")
        if not isinstance(supplied_id, str) or not _LOGICAL_TURN.fullmatch(supplied_id):
            raise ModelTurnStateError("model-turn logical ID is malformed")
        expected = cls.create(
            mission_id=values["mission_id"],
            state_ref=state_ref,
            role=role,
            work_item_id=values["work_item_id"],
            provider=provider,
            prompt_digest=prompt_digest,
            request_digest=request_digest,
            acceptance_specification_id=values["acceptance_specification_id"],
            acceptance_specification_digest=digests["acceptance_specification_digest"],
            role_contract_digest=digests["role_contract_digest"],
            configuration_digest=digests["configuration_digest"],
            selection_digest=digests["selection_digest"],
            policy_decision_ref=values["policy_decision_ref"],
            lease_id=values["lease_id"],
            redaction_policy_digest=digests["redaction_policy_digest"],
        )
        if supplied_id != expected.logical_turn_id:
            raise ModelTurnStateError("model-turn logical ID does not bind its plan")
        return expected

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "logical_turn_id": self.logical_turn_id,
            "mission_id": self.mission_id,
            "state_ref": self.state_ref,
            "role": self.role,
            "work_item_id": self.work_item_id,
            "provider": self.provider.to_dict(),
            "prompt_digest": self.prompt_digest,
            "request_digest": self.request_digest,
            "acceptance_specification_id": self.acceptance_specification_id,
            "acceptance_specification_digest": self.acceptance_specification_digest,
            "role_contract_digest": self.role_contract_digest,
            "configuration_digest": self.configuration_digest,
            "selection_digest": self.selection_digest,
            "policy_decision_ref": self.policy_decision_ref,
            "lease_id": self.lease_id,
            "redaction_policy_digest": self.redaction_policy_digest,
        }

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


@dataclass(frozen=True, slots=True)
class ModelTurnResult:
    """A terminal, response-observed result; no raw response or error is retained."""

    logical_turn_id: str
    outcome: ModelTurnOutcome
    response_digest: str
    structured_result_digest: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    transport_retry_index: int

    @classmethod
    def from_dict(cls, document: Mapping[str, object]) -> ModelTurnResult:
        _ensure_contract("model-turn-result", document)
        logical_turn_id = document.get("logical_turn_id")
        if not isinstance(logical_turn_id, str) or not _LOGICAL_TURN.fullmatch(logical_turn_id):
            raise ModelTurnStateError("model-turn result logical ID is malformed")
        try:
            outcome = ModelTurnOutcome(document.get("outcome", ""))
        except ValueError:
            raise ModelTurnStateError("model-turn result outcome is invalid") from None
        response_digest = _require_digest(document.get("response_digest"), "response digest")
        raw_result = document.get("structured_result_digest")
        structured_result_digest = (
            _require_digest(raw_result, "structured result digest")
            if raw_result is not None
            else None
        )
        if (outcome is ModelTurnOutcome.SUCCEEDED) != (structured_result_digest is not None):
            raise ModelTurnStateError(
                "only a succeeded model-turn result may retain a structured result digest"
            )
        token_values: dict[str, int | None] = {}
        for field in ("prompt_tokens", "completion_tokens"):
            value = document.get(field)
            if value is not None and (type(value) is not int or value < 0):
                raise ModelTurnStateError(f"model-turn result {field} must be nonnegative")
            token_values[field] = value
        retry = document.get("transport_retry_index")
        if type(retry) is not int or retry < 0:
            raise ModelTurnStateError("model-turn result retry index must be nonnegative")
        return cls(
            logical_turn_id,
            outcome,
            response_digest,
            structured_result_digest,
            token_values["prompt_tokens"],
            token_values["completion_tokens"],
            retry,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "logical_turn_id": self.logical_turn_id,
            "outcome": self.outcome.value,
            "response_digest": self.response_digest,
            "structured_result_digest": self.structured_result_digest,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "transport_retry_index": self.transport_retry_index,
        }

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


def _safe_text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ModelTurnStateError(f"{label} must be nonempty text of at most {maximum} characters")
    return value


@dataclass(frozen=True, slots=True)
class ModelRoleEvidence:
    """One selected, redacted model output retained for downstream role context."""

    kind: str
    summary: str
    source: str
    content: str

    @classmethod
    def from_dict(cls, document: Mapping[str, object]) -> ModelRoleEvidence:
        return cls(
            _safe_text(document.get("kind"), "role evidence kind", 128),
            _safe_text(document.get("summary"), "role evidence summary", 4_000),
            _safe_text(document.get("source"), "role evidence source", 256),
            _safe_text(document.get("content"), "role evidence content", 16_384),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "summary": self.summary,
            "source": self.source,
            "content": self.content,
        }


@dataclass(frozen=True, slots=True)
class ModelRoleResult:
    """A selected and caller-redacted role result, never a raw provider response.

    Redaction values are supplied only while this object is constructed and are not
    retained.  A redaction-policy digest is sealed in the plan/result to make the caller's
    choice reviewable without persisting sensitive rule material.
    """

    logical_turn_id: str
    role: str
    work_item_id: str
    summary: str
    evidence: tuple[ModelRoleEvidence, ...]
    proposed_actions: tuple[str, ...]
    lessons: tuple[str, ...]
    success: bool
    completed_at: str
    redaction_policy_digest: str

    @classmethod
    def from_dict(cls, document: Mapping[str, object]) -> ModelRoleResult:
        _ensure_contract("model-role-result", document)
        logical_turn_id = document.get("logical_turn_id")
        if not isinstance(logical_turn_id, str) or not _LOGICAL_TURN.fullmatch(logical_turn_id):
            raise ModelTurnStateError("model role result logical ID is malformed")
        role = document.get("role")
        if not isinstance(role, str) or role not in ROLE_NAMES:
            raise ModelTurnStateError("model role result role is not registered")
        work_item_id = _require_identifier(document.get("work_item_id"), "role result work item")
        evidence_value = document.get("evidence")
        if not isinstance(evidence_value, list):
            raise ModelTurnStateError("model role result evidence is malformed")
        evidence = tuple(
            ModelRoleEvidence.from_dict(value)
            for value in evidence_value
            if isinstance(value, Mapping)
        )
        if len(evidence) != len(evidence_value) or len(evidence) > 64:
            raise ModelTurnStateError("model role result evidence is invalid")

        def text_list(field: str) -> tuple[str, ...]:
            value = document.get(field)
            if not isinstance(value, list) or len(value) > 64:
                raise ModelTurnStateError(f"model role result {field} is invalid")
            return tuple(_safe_text(item, f"role result {field}", 4_000) for item in value)

        success = document.get("success")
        if type(success) is not bool:
            raise ModelTurnStateError("model role result success must be boolean")
        return cls(
            logical_turn_id,
            role,
            work_item_id,
            _safe_text(document.get("summary"), "role result summary", 8_000),
            evidence,
            text_list("proposed_actions"),
            text_list("lessons"),
            success,
            _safe_text(document.get("completed_at"), "role result completed_at", 128),
            _require_digest(document.get("redaction_policy_digest"), "redaction policy digest"),
        )

    @classmethod
    def from_agent_result(
        cls,
        logical_turn_id: str,
        result: AgentResult,
        *,
        redaction_policy_digest: str,
        redaction_secrets: Sequence[str] = (),
    ) -> ModelRoleResult:
        """Create a bounded canonical context artifact after caller-supplied redaction."""

        secrets = tuple(value for value in redaction_secrets if isinstance(value, str) and value)

        def clean(value: object, label: str, maximum: int) -> str:
            text = _safe_text(value, label, maximum)
            redacted = redact(text, secrets)
            if any(secret in redacted for secret in secrets):
                raise ModelTurnStateError(f"{label} contains an unredacted configured secret")
            return redacted

        evidence: list[dict[str, str]] = []
        for item in result.evidence:
            content = item.payload.get("content")
            if set(item.payload) != {"content"}:
                raise ModelTurnStateError("role evidence payload must contain only selected content")
            evidence.append(
                {
                    "kind": clean(item.kind, "role evidence kind", 128),
                    "summary": clean(item.summary, "role evidence summary", 4_000),
                    "source": clean(item.source, "role evidence source", 256),
                    "content": clean(content, "role evidence content", 16_384),
                }
            )
        return cls.from_dict(
            {
                "schema_version": 1,
                "logical_turn_id": logical_turn_id,
                "role": result.role.value,
                "work_item_id": result.work_item_id,
                "summary": clean(result.summary, "role result summary", 8_000),
                "evidence": evidence,
                "proposed_actions": [
                    clean(value, "role result proposed action", 4_000)
                    for value in result.proposed_actions
                ],
                "lessons": [clean(value, "role result lesson", 4_000) for value in result.lessons],
                "success": result.success,
                "completed_at": result.completed_at,
                "redaction_policy_digest": redaction_policy_digest,
            }
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "logical_turn_id": self.logical_turn_id,
            "role": self.role,
            "work_item_id": self.work_item_id,
            "summary": self.summary,
            "evidence": [item.to_dict() for item in self.evidence],
            "proposed_actions": list(self.proposed_actions),
            "lessons": list(self.lessons),
            "success": self.success,
            "completed_at": self.completed_at,
            "redaction_policy_digest": self.redaction_policy_digest,
        }

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())

    def to_agent_result(self) -> AgentResult:
        return AgentResult(
            role=Role(self.role),
            work_item_id=self.work_item_id,
            summary=self.summary,
            evidence=tuple(
                Evidence(item.kind, item.summary, item.source, {"content": item.content})
                for item in self.evidence
            ),
            proposed_actions=self.proposed_actions,
            lessons=self.lessons,
            success=self.success,
            completed_at=self.completed_at,
        )


@dataclass(frozen=True, slots=True)
class ModelTurnRecord:
    plan: ModelTurnPlan
    phase: ModelTurnPhase
    result: ModelTurnResult | None
    role_result: ModelRoleResult | None
    events: tuple[Mapping[str, object], ...]

    @property
    def may_dispatch(self) -> bool:
        return self.phase is ModelTurnPhase.PLANNED


class ModelTurnStore:
    """SQLite append-only state for deterministic model turn planning and recovery.

    This is intentionally only a state/provenance adapter.  It does not construct
    prompts, call providers, parse responses, release credentials, or authenticate a
    provider.  A filesystem-backed database is required by default.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        require_durable: bool = True,
        clock: Callable[[], datetime] | None = None,
        redaction_secrets: Sequence[str] = (),
    ) -> None:
        self.path = str(path)
        if require_durable and not self.is_durable_path(self.path):
            raise ModelTurnStateError("durable model-turn state requires a filesystem path")
        self._clock = clock or (lambda: datetime.now(UTC))
        self._redaction_secrets = tuple(
            value for value in redaction_secrets if isinstance(value, str) and value
        )
        self._lock = RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        try:
            self._initialize()
        except BaseException:
            self._connection.close()
            raise

    @staticmethod
    def is_durable_path(path: str | Path) -> bool:
        candidate = str(path).strip().casefold()
        return (
            bool(candidate)
            and candidate != ":memory:"
            and ":memory:" not in candidate
            and "mode=memory" not in candidate
        )

    def _initialize(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                PRAGMA foreign_keys=ON;
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS model_turn_plans (
                    logical_turn_id TEXT PRIMARY KEY,
                    plan_digest TEXT NOT NULL UNIQUE,
                    plan_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS model_turn_events (
                    logical_turn_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_kind TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    event_digest TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    PRIMARY KEY(logical_turn_id, sequence),
                    UNIQUE(logical_turn_id, event_digest),
                    FOREIGN KEY(logical_turn_id) REFERENCES model_turn_plans(logical_turn_id)
                );
                CREATE TABLE IF NOT EXISTS model_turn_slots (
                    mission_id TEXT NOT NULL,
                    state_ref TEXT NOT NULL,
                    role TEXT NOT NULL,
                    work_item_id TEXT NOT NULL,
                    logical_turn_id TEXT NOT NULL UNIQUE,
                    plan_digest TEXT NOT NULL,
                    PRIMARY KEY(mission_id, state_ref, role, work_item_id),
                    FOREIGN KEY(logical_turn_id) REFERENCES model_turn_plans(logical_turn_id)
                );
                CREATE TABLE IF NOT EXISTS model_turn_budget_configs (
                    mission_id TEXT PRIMARY KEY,
                    budget_digest TEXT NOT NULL UNIQUE,
                    budget_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS model_turn_budget_reservations (
                    logical_turn_id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    reservation_digest TEXT NOT NULL UNIQUE,
                    reservation_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    FOREIGN KEY(logical_turn_id) REFERENCES model_turn_plans(logical_turn_id),
                    FOREIGN KEY(mission_id) REFERENCES model_turn_budget_configs(mission_id)
                );
                CREATE TRIGGER IF NOT EXISTS model_turn_plans_no_update
                BEFORE UPDATE ON model_turn_plans BEGIN
                    SELECT RAISE(ABORT, 'model turn plans are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS model_turn_plans_no_delete
                BEFORE DELETE ON model_turn_plans BEGIN
                    SELECT RAISE(ABORT, 'model turn plans are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS model_turn_events_no_update
                BEFORE UPDATE ON model_turn_events BEGIN
                    SELECT RAISE(ABORT, 'model turn events are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS model_turn_events_no_delete
                BEFORE DELETE ON model_turn_events BEGIN
                    SELECT RAISE(ABORT, 'model turn events are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS model_turn_slots_no_update
                BEFORE UPDATE ON model_turn_slots BEGIN
                    SELECT RAISE(ABORT, 'model turn slots are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS model_turn_slots_no_delete
                BEFORE DELETE ON model_turn_slots BEGIN
                    SELECT RAISE(ABORT, 'model turn slots are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS model_turn_budget_configs_no_update
                BEFORE UPDATE ON model_turn_budget_configs BEGIN
                    SELECT RAISE(ABORT, 'model turn budget configurations are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS model_turn_budget_configs_no_delete
                BEFORE DELETE ON model_turn_budget_configs BEGIN
                    SELECT RAISE(ABORT, 'model turn budget configurations are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS model_turn_budget_reservations_no_update
                BEFORE UPDATE ON model_turn_budget_reservations BEGIN
                    SELECT RAISE(ABORT, 'model turn budget reservations are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS model_turn_budget_reservations_no_delete
                BEFORE DELETE ON model_turn_budget_reservations BEGIN
                    SELECT RAISE(ABORT, 'model turn budget reservations are append-only');
                END;
                """
            )

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> ModelTurnStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def register_plan(self, plan: ModelTurnPlan | Mapping[str, object]) -> ModelTurnRecord:
        typed_plan = ModelTurnPlan.from_dict(
            plan.to_dict() if isinstance(plan, ModelTurnPlan) else plan
        )
        with self._lock, self._connection:
            return self._register_plan_locked(typed_plan, _utc(self._clock()))

    def register_durable_plan(
        self,
        plan: ModelTurnPlan | Mapping[str, object],
        *,
        budget: ModelTurnBudget,
        reservation: ModelTurnBudgetReservation,
    ) -> ModelTurnRecord:
        """Atomically seal a role plan and permanently reserve its local budget.

        Calling this is the only supported admission path for the opt-in live executor.
        A planned role without its reservation is never dispatchable by that executor.
        """

        if not isinstance(budget, ModelTurnBudget):
            raise ModelTurnStateError("durable model admission requires a typed model-turn budget")
        if not isinstance(reservation, ModelTurnBudgetReservation):
            raise ModelTurnStateError(
                "durable model admission requires a typed model-turn budget reservation"
            )
        typed_plan = ModelTurnPlan.from_dict(
            plan.to_dict() if isinstance(plan, ModelTurnPlan) else plan
        )
        typed_reservation = ModelTurnBudgetReservation.from_dict(reservation.to_dict())
        if budget.mission_id != typed_plan.mission_id:
            raise ModelTurnStateError("model-turn budget belongs to another mission")
        if (
            typed_reservation.logical_turn_id != typed_plan.logical_turn_id
            or typed_reservation.mission_id != typed_plan.mission_id
        ):
            raise ModelTurnStateError("model-turn budget reservation has foreign plan bindings")
        if (
            typed_reservation.tool_calls > budget.max_tool_calls_per_episode
            or typed_reservation.compute_units > budget.max_compute_units_per_episode
        ):
            raise ModelTurnStateError("model-turn reservation exceeds the per-episode budget")
        try:
            with self._lock, self._connection:
                now = _utc(self._clock())
                self._configure_budget_locked(budget, now)
                record = self._register_plan_locked(typed_plan, now)
                self._reserve_budget_locked(typed_plan, typed_reservation, budget, now)
                return self._record_locked(record.plan.logical_turn_id)
        except sqlite3.IntegrityError as error:
            raise ModelTurnStateError(
                "concurrent durable model-turn admission was rejected before provider invocation"
            ) from error

    def durable_record(
        self,
        plan: ModelTurnPlan | Mapping[str, object],
        *,
        budget: ModelTurnBudget,
        reservation: ModelTurnBudgetReservation,
    ) -> ModelTurnRecord:
        """Revalidate all durable-admission bindings before recovery or dispatch."""

        if not isinstance(budget, ModelTurnBudget):
            raise ModelTurnStateError("durable model recovery requires a typed model-turn budget")
        if not isinstance(reservation, ModelTurnBudgetReservation):
            raise ModelTurnStateError(
                "durable model recovery requires a typed model-turn budget reservation"
            )
        typed_plan = ModelTurnPlan.from_dict(
            plan.to_dict() if isinstance(plan, ModelTurnPlan) else plan
        )
        typed_reservation = ModelTurnBudgetReservation.from_dict(reservation.to_dict())
        with self._lock:
            self._assert_budget_locked(budget)
            self._assert_slot_locked(typed_plan)
            self._assert_reservation_locked(typed_plan, typed_reservation)
            return self._record_locked(typed_plan.logical_turn_id)

    def budget_usage(self, mission_id: str) -> dict[str, int | float]:
        """Return verified permanent reservations; no reservation is silently released."""

        _require_identifier(mission_id, "model-turn budget mission ID")
        with self._lock:
            budget = self._budget_locked(mission_id)
            rows = self._connection.execute(
                "SELECT reservation_json,reservation_digest FROM model_turn_budget_reservations "
                "WHERE mission_id=? ORDER BY logical_turn_id",
                (mission_id,),
            ).fetchall()
            reservations = [self._reservation_from_row(row) for row in rows]
            usage = {
                "episodes": sum(item.episodes for item in reservations),
                "tool_calls": sum(item.tool_calls for item in reservations),
                "compute_units": sum(item.compute_units for item in reservations),
            }
            if (
                usage["episodes"] > budget.max_episodes
                or usage["tool_calls"] > budget.max_tool_calls
                or usage["compute_units"] > budget.max_compute_units
            ):
                raise ModelTurnStateError("stored model-turn reservations exceed the sealed budget")
            return usage

    def _assert_slot_available_locked(self, plan: ModelTurnPlan) -> None:
        row = self._connection.execute(
            "SELECT logical_turn_id,plan_digest FROM model_turn_slots "
            "WHERE mission_id=? AND state_ref=? AND role=? AND work_item_id=?",
            (plan.mission_id, plan.state_ref, plan.role, plan.work_item_id),
        ).fetchone()
        if row is not None and (
            row["logical_turn_id"] != plan.logical_turn_id
            or row["plan_digest"] != plan.digest
        ):
            raise ModelTurnStateError(
                "durable model role slot is already sealed to another planning input"
            )

    def _ensure_slot_locked(self, plan: ModelTurnPlan) -> None:
        row = self._connection.execute(
            "SELECT logical_turn_id,plan_digest FROM model_turn_slots "
            "WHERE mission_id=? AND state_ref=? AND role=? AND work_item_id=?",
            (plan.mission_id, plan.state_ref, plan.role, plan.work_item_id),
        ).fetchone()
        if row is None:
            self._connection.execute(
                "INSERT INTO model_turn_slots(mission_id,state_ref,role,work_item_id,"
                "logical_turn_id,plan_digest) VALUES(?,?,?,?,?,?)",
                (
                    plan.mission_id,
                    plan.state_ref,
                    plan.role,
                    plan.work_item_id,
                    plan.logical_turn_id,
                    plan.digest,
                ),
            )
            return
        if (
            row["logical_turn_id"] != plan.logical_turn_id
            or row["plan_digest"] != plan.digest
        ):
            raise ModelTurnStateError("stored durable model role slot has foreign bindings")

    def _assert_slot_locked(self, plan: ModelTurnPlan) -> None:
        row = self._connection.execute(
            "SELECT logical_turn_id,plan_digest FROM model_turn_slots "
            "WHERE mission_id=? AND state_ref=? AND role=? AND work_item_id=?",
            (plan.mission_id, plan.state_ref, plan.role, plan.work_item_id),
        ).fetchone()
        if row is None:
            raise ModelTurnStateError("durable model role slot is absent")
        if (
            row["logical_turn_id"] != plan.logical_turn_id
            or row["plan_digest"] != plan.digest
        ):
            raise ModelTurnStateError("stored durable model role slot has foreign bindings")

    def _configure_budget_locked(self, budget: ModelTurnBudget, now: str) -> None:
        row = self._connection.execute(
            "SELECT budget_json,budget_digest FROM model_turn_budget_configs WHERE mission_id=?",
            (budget.mission_id,),
        ).fetchone()
        budget_json = _canonical_json(budget.to_dict()).decode("utf-8")
        if row is None:
            self._connection.execute(
                "INSERT INTO model_turn_budget_configs(mission_id,budget_digest,budget_json,recorded_at) "
                "VALUES(?,?,?,?)",
                (budget.mission_id, budget.digest, budget_json, now),
            )
            return
        if row["budget_json"] != budget_json or row["budget_digest"] != budget.digest:
            raise ModelTurnStateError("durable model mission budget differs from its sealed budget")

    def _budget_locked(self, mission_id: str) -> ModelTurnBudget:
        row = self._connection.execute(
            "SELECT budget_json,budget_digest FROM model_turn_budget_configs WHERE mission_id=?",
            (mission_id,),
        ).fetchone()
        if row is None:
            raise ModelTurnStateError("durable model mission budget is absent")
        try:
            document = json.loads(row["budget_json"])
        except (TypeError, json.JSONDecodeError) as error:
            raise ModelTurnStateError("stored durable model budget is unreadable") from error
        if not isinstance(document, Mapping):
            raise ModelTurnStateError("stored durable model budget is malformed")
        try:
            budget = ModelTurnBudget(
                mission_id=_require_identifier(document.get("mission_id"), "model-turn budget mission ID"),
                max_episodes=document.get("max_episodes"),  # type: ignore[arg-type]
                max_tool_calls=document.get("max_tool_calls"),  # type: ignore[arg-type]
                max_compute_units=document.get("max_compute_units"),  # type: ignore[arg-type]
                max_tool_calls_per_episode=document.get("max_tool_calls_per_episode"),  # type: ignore[arg-type]
                max_compute_units_per_episode=document.get("max_compute_units_per_episode"),  # type: ignore[arg-type]
            )
        except (ModelTurnStateError, TypeError) as error:
            raise ModelTurnStateError("stored durable model budget is malformed") from error
        if row["budget_digest"] != budget.digest:
            raise ModelTurnStateError("stored durable model budget digest is inconsistent")
        return budget

    def _assert_budget_locked(self, budget: ModelTurnBudget) -> None:
        stored = self._budget_locked(budget.mission_id)
        if stored != budget:
            raise ModelTurnStateError("durable model mission budget differs from its sealed budget")

    def _reservation_from_row(self, row: sqlite3.Row) -> ModelTurnBudgetReservation:
        try:
            document = json.loads(row["reservation_json"])
        except (TypeError, json.JSONDecodeError) as error:
            raise ModelTurnStateError("stored model-turn reservation is unreadable") from error
        if not isinstance(document, Mapping):
            raise ModelTurnStateError("stored model-turn reservation is malformed")
        reservation = ModelTurnBudgetReservation.from_dict(document)
        if row["reservation_digest"] != reservation.digest:
            raise ModelTurnStateError("stored model-turn reservation digest is inconsistent")
        return reservation

    def _reserve_budget_locked(
        self,
        plan: ModelTurnPlan,
        reservation: ModelTurnBudgetReservation,
        budget: ModelTurnBudget,
        now: str,
    ) -> None:
        existing = self._connection.execute(
            "SELECT reservation_json,reservation_digest FROM model_turn_budget_reservations "
            "WHERE logical_turn_id=?",
            (plan.logical_turn_id,),
        ).fetchone()
        if existing is not None:
            stored = self._reservation_from_row(existing)
            if stored != reservation:
                raise ModelTurnStateError("model-turn reservation differs from its sealed reservation")
            return
        rows = self._connection.execute(
            "SELECT reservation_json,reservation_digest FROM model_turn_budget_reservations "
            "WHERE mission_id=?",
            (plan.mission_id,),
        ).fetchall()
        existing_reservations = [self._reservation_from_row(row) for row in rows]
        episodes = sum(item.episodes for item in existing_reservations) + reservation.episodes
        tool_calls = sum(item.tool_calls for item in existing_reservations) + reservation.tool_calls
        compute_units = (
            sum(item.compute_units for item in existing_reservations)
            + reservation.compute_units
        )
        if (
            episodes > budget.max_episodes
            or tool_calls > budget.max_tool_calls
            or compute_units > budget.max_compute_units
        ):
            raise ModelTurnStateError("durable model budget is exhausted before dispatch")
        self._connection.execute(
            "INSERT INTO model_turn_budget_reservations(logical_turn_id,mission_id,"
            "reservation_digest,reservation_json,recorded_at) VALUES(?,?,?,?,?)",
            (
                plan.logical_turn_id,
                plan.mission_id,
                reservation.digest,
                _canonical_json(reservation.to_dict()).decode("utf-8"),
                now,
            ),
        )

    def _assert_reservation_locked(
        self,
        plan: ModelTurnPlan,
        reservation: ModelTurnBudgetReservation,
    ) -> None:
        row = self._connection.execute(
            "SELECT reservation_json,reservation_digest FROM model_turn_budget_reservations "
            "WHERE logical_turn_id=?",
            (plan.logical_turn_id,),
        ).fetchone()
        if row is None:
            raise ModelTurnStateError("durable model-turn budget reservation is absent")
        stored = self._reservation_from_row(row)
        if stored != reservation or stored.mission_id != plan.mission_id:
            raise ModelTurnStateError("stored model-turn reservation has foreign bindings")

    def _register_plan_locked(
        self,
        typed_plan: ModelTurnPlan,
        now: str,
    ) -> ModelTurnRecord:
        plan_json = _canonical_json(typed_plan.to_dict()).decode("utf-8")
        self._assert_slot_available_locked(typed_plan)
        existing = self._connection.execute(
            "SELECT plan_json FROM model_turn_plans WHERE logical_turn_id=?",
            (typed_plan.logical_turn_id,),
        ).fetchone()
        if existing is not None:
            if existing["plan_json"] != plan_json:
                raise ModelTurnStateError("logical model-turn ID maps to another plan")
            self._ensure_slot_locked(typed_plan)
            return self._record_locked(typed_plan.logical_turn_id)
        digest_row = self._connection.execute(
            "SELECT logical_turn_id FROM model_turn_plans WHERE plan_digest=?",
            (typed_plan.digest,),
        ).fetchone()
        if digest_row is not None:
            raise ModelTurnStateError("model-turn plan digest was replayed")
        self._connection.execute(
            "INSERT INTO model_turn_plans(logical_turn_id,plan_digest,plan_json,recorded_at) "
            "VALUES(?,?,?,?)",
            (typed_plan.logical_turn_id, typed_plan.digest, plan_json, now),
        )
        self._ensure_slot_locked(typed_plan)
        self._append_event_locked(
            typed_plan.logical_turn_id,
            ModelTurnPhase.PLANNED,
            {"plan_digest": typed_plan.digest},
            now,
        )
        return self._record_locked(typed_plan.logical_turn_id)

    def start_dispatch(self, logical_turn_id: str) -> ModelTurnRecord:
        """Seal intent immediately before an external provider invocation."""

        try:
            with self._lock, self._connection:
                record = self._record_locked(logical_turn_id)
                if record.phase is not ModelTurnPhase.PLANNED:
                    raise ModelTurnStateError(
                        f"model-turn dispatch is forbidden from {record.phase.value}"
                    )
                self._append_event_locked(
                    logical_turn_id,
                    ModelTurnPhase.DISPATCH_STARTED,
                    {},
                    _utc(self._clock()),
                )
                return self._record_locked(logical_turn_id)
        except sqlite3.IntegrityError as error:
            raise ModelTurnStateError(
                "concurrent model-turn dispatch was rejected before provider invocation"
            ) from error

    def adopt_result(
        self, result: ModelTurnResult | Mapping[str, object]
    ) -> ModelTurnRecord:
        """Persist a terminal response observation without a resumable role artifact.

        This legacy primitive remains useful for failed/invalid provider outcomes. A
        successful model role that must resume downstream context must use
        :meth:`adopt_role_result` instead.
        """

        typed_result = ModelTurnResult.from_dict(
            result.to_dict() if isinstance(result, ModelTurnResult) else result
        )
        if typed_result.outcome is ModelTurnOutcome.SUCCEEDED:
            raise ModelTurnStateError(
                "a succeeded model turn requires a resumable sanitized role result"
            )
        with self._lock, self._connection:
            record = self._record_locked(typed_result.logical_turn_id)
            if record.phase is not ModelTurnPhase.DISPATCH_STARTED:
                raise ModelTurnStateError(
                    "model-turn result is forbidden without one in-progress dispatch"
                )
            if record.plan.logical_turn_id != typed_result.logical_turn_id:
                raise ModelTurnStateError("model-turn result has a foreign plan")
            self._append_event_locked(
                typed_result.logical_turn_id,
                ModelTurnPhase.COMPLETED,
                {"result": typed_result.to_dict(), "result_digest": typed_result.digest},
                _utc(self._clock()),
            )
            return self._record_locked(typed_result.logical_turn_id)

    def adopt_role_result(
        self,
        result: ModelTurnResult | Mapping[str, object],
        role_result: ModelRoleResult | Mapping[str, object],
    ) -> ModelTurnRecord:
        """Atomically adopt a successful response observation and sanitized role state."""

        typed_result = ModelTurnResult.from_dict(
            result.to_dict() if isinstance(result, ModelTurnResult) else result
        )
        typed_role_result = ModelRoleResult.from_dict(
            role_result.to_dict() if isinstance(role_result, ModelRoleResult) else role_result
        )
        if typed_result.outcome is not ModelTurnOutcome.SUCCEEDED:
            raise ModelTurnStateError("only a succeeded model turn may adopt role state")
        if typed_result.structured_result_digest != typed_role_result.digest:
            raise ModelTurnStateError("model-turn result does not bind the role result")
        self._assert_no_configured_secrets(typed_role_result)
        with self._lock, self._connection:
            record = self._record_locked(typed_result.logical_turn_id)
            if record.phase is not ModelTurnPhase.DISPATCH_STARTED:
                raise ModelTurnStateError(
                    "model-turn role result is forbidden without one in-progress dispatch"
                )
            plan = record.plan
            if (
                typed_role_result.logical_turn_id != plan.logical_turn_id
                or typed_role_result.role != plan.role
                or typed_role_result.work_item_id != plan.work_item_id
                or typed_role_result.redaction_policy_digest != plan.redaction_policy_digest
            ):
                raise ModelTurnStateError("model-turn role result has foreign plan bindings")
            self._append_event_locked(
                typed_result.logical_turn_id,
                ModelTurnPhase.COMPLETED,
                {
                    "result": typed_result.to_dict(),
                    "result_digest": typed_result.digest,
                    "role_result": typed_role_result.to_dict(),
                    "role_result_digest": typed_role_result.digest,
                },
                _utc(self._clock()),
            )
            return self._record_locked(typed_result.logical_turn_id)

    def recover(self, logical_turn_id: str) -> ModelTurnRecord:
        """Quarantine an interrupted dispatch rather than guess whether it reached a provider."""

        with self._lock, self._connection:
            record = self._record_locked(logical_turn_id)
            if record.phase is ModelTurnPhase.DISPATCH_STARTED:
                return self._mark_ambiguous_locked(
                    logical_turn_id,
                    ModelTurnAmbiguity.INTERRUPTED_AFTER_DISPATCH_START,
                )
            return record

    def mark_ambiguous(
        self,
        logical_turn_id: str,
        reason: ModelTurnAmbiguity = ModelTurnAmbiguity.PROVIDER_OUTCOME_UNKNOWN,
    ) -> ModelTurnRecord:
        """Quarantine a turn whenever a provider outcome cannot be observed exactly."""

        with self._lock, self._connection:
            return self._mark_ambiguous_locked(logical_turn_id, reason)

    def record(self, logical_turn_id: str) -> ModelTurnRecord:
        with self._lock:
            return self._record_locked(logical_turn_id)

    def event_count(self, logical_turn_id: str) -> int:
        with self._lock:
            return int(
                self._connection.execute(
                    "SELECT COUNT(*) FROM model_turn_events WHERE logical_turn_id=?",
                    (logical_turn_id,),
                ).fetchone()[0]
            )

    def _assert_no_configured_secrets(self, role_result: ModelRoleResult) -> None:
        values = (
            role_result.summary,
            *role_result.proposed_actions,
            *role_result.lessons,
            *(value for item in role_result.evidence for value in item.to_dict().values()),
        )
        for secret in self._redaction_secrets:
            if any(secret in value for value in values):
                raise ModelTurnStateError(
                    "model role result contains an unredacted configured secret"
                )

    def _mark_ambiguous_locked(
        self, logical_turn_id: str, reason: ModelTurnAmbiguity
    ) -> ModelTurnRecord:
        record = self._record_locked(logical_turn_id)
        if record.phase is not ModelTurnPhase.DISPATCH_STARTED:
            raise ModelTurnStateError(
                f"ambiguous model-turn outcome is forbidden from {record.phase.value}"
            )
        self._append_event_locked(
            logical_turn_id,
            ModelTurnPhase.AMBIGUOUS,
            {"reason_code": reason.value},
            _utc(self._clock()),
        )
        return self._record_locked(logical_turn_id)

    def _append_event_locked(
        self,
        logical_turn_id: str,
        phase: ModelTurnPhase,
        payload: Mapping[str, object],
        now: str,
    ) -> None:
        row = self._connection.execute(
            "SELECT COUNT(*) FROM model_turn_events WHERE logical_turn_id=?",
            (logical_turn_id,),
        ).fetchone()
        sequence = int(row[0])
        event = {
            "schema_version": 1,
            "logical_turn_id": logical_turn_id,
            "sequence": sequence,
            "phase": phase.value,
            "payload": dict(payload),
        }
        event_json = _canonical_json(event).decode("utf-8")
        self._connection.execute(
            "INSERT INTO model_turn_events(logical_turn_id,sequence,event_kind,event_json,"
            "event_digest,recorded_at) VALUES(?,?,?,?,?,?)",
            (logical_turn_id, sequence, phase.value, event_json, _digest(event), now),
        )

    def _record_locked(self, logical_turn_id: str) -> ModelTurnRecord:
        if not isinstance(logical_turn_id, str) or not _LOGICAL_TURN.fullmatch(logical_turn_id):
            raise ModelTurnStateError("model-turn logical ID is malformed")
        plan_row = self._connection.execute(
            "SELECT plan_digest,plan_json FROM model_turn_plans WHERE logical_turn_id=?",
            (logical_turn_id,),
        ).fetchone()
        if plan_row is None:
            raise ModelTurnStateError("model-turn plan is absent")
        try:
            plan_document = json.loads(plan_row["plan_json"])
        except (TypeError, json.JSONDecodeError) as error:
            raise ModelTurnStateError("stored model-turn plan is unreadable") from error
        if not isinstance(plan_document, Mapping):
            raise ModelTurnStateError("stored model-turn plan is not an object")
        plan = ModelTurnPlan.from_dict(plan_document)
        if plan_row["plan_digest"] != plan.digest:
            raise ModelTurnStateError("stored model-turn plan digest is inconsistent")
        rows = self._connection.execute(
            "SELECT sequence,event_kind,event_json,event_digest FROM model_turn_events "
            "WHERE logical_turn_id=? ORDER BY sequence",
            (logical_turn_id,),
        ).fetchall()
        if not rows:
            raise ModelTurnStateError("model-turn plan lacks append-only event provenance")
        events: list[Mapping[str, object]] = []
        phase: ModelTurnPhase | None = None
        result: ModelTurnResult | None = None
        role_result: ModelRoleResult | None = None
        for index, row in enumerate(rows):
            if row["sequence"] != index:
                raise ModelTurnStateError("model-turn event sequences are not contiguous")
            try:
                event = json.loads(row["event_json"])
            except (TypeError, json.JSONDecodeError) as error:
                raise ModelTurnStateError("stored model-turn event is unreadable") from error
            if not isinstance(event, Mapping) or _digest(event) != row["event_digest"]:
                raise ModelTurnStateError("stored model-turn event digest is inconsistent")
            if event.get("logical_turn_id") != logical_turn_id or event.get("sequence") != index:
                raise ModelTurnStateError("stored model-turn event has foreign binding")
            event_phase = event.get("phase")
            if not isinstance(event_phase, str):
                raise ModelTurnStateError("stored model-turn event phase is absent")
            try:
                current = ModelTurnPhase(event_phase)
            except ValueError:
                raise ModelTurnStateError("stored model-turn event phase is unknown") from None
            if row["event_kind"] != current.value:
                raise ModelTurnStateError("stored model-turn event kind is inconsistent")
            if index == 0:
                if current is not ModelTurnPhase.PLANNED:
                    raise ModelTurnStateError("model-turn provenance must start planned")
                if event.get("payload") != {"plan_digest": plan.digest}:
                    raise ModelTurnStateError("planned event does not bind stored plan")
            elif index == 1:
                if current is not ModelTurnPhase.DISPATCH_STARTED:
                    raise ModelTurnStateError("model-turn provenance has invalid dispatch transition")
                if event.get("payload") != {}:
                    raise ModelTurnStateError("dispatch-started event has unexpected payload")
            elif index == 2:
                if current is ModelTurnPhase.COMPLETED:
                    payload = event.get("payload")
                    if not isinstance(payload, Mapping):
                        raise ModelTurnStateError("completed event has no result payload")
                    raw_result = payload.get("result")
                    if not isinstance(raw_result, Mapping):
                        raise ModelTurnStateError("completed event has no result")
                    result = ModelTurnResult.from_dict(raw_result)
                    if (
                        result.logical_turn_id != logical_turn_id
                        or payload.get("result_digest") != result.digest
                    ):
                        raise ModelTurnStateError("completed event result does not bind plan")
                    has_role_result = "role_result" in payload or "role_result_digest" in payload
                    expected_keys = (
                        {"result", "result_digest", "role_result", "role_result_digest"}
                        if has_role_result
                        else {"result", "result_digest"}
                    )
                    if set(payload) != expected_keys:
                        raise ModelTurnStateError("completed event has unexpected payload")
                    if has_role_result:
                        raw_role_result = payload.get("role_result")
                        if not isinstance(raw_role_result, Mapping):
                            raise ModelTurnStateError("completed event has no role result")
                        role_result = ModelRoleResult.from_dict(raw_role_result)
                        self._assert_no_configured_secrets(role_result)
                        if (
                            result.outcome is not ModelTurnOutcome.SUCCEEDED
                            or result.structured_result_digest != role_result.digest
                            or payload.get("role_result_digest") != role_result.digest
                            or role_result.logical_turn_id != logical_turn_id
                            or role_result.role != plan.role
                            or role_result.work_item_id != plan.work_item_id
                            or role_result.redaction_policy_digest != plan.redaction_policy_digest
                        ):
                            raise ModelTurnStateError(
                                "completed model role result does not bind plan/result"
                            )
                    elif result.outcome is ModelTurnOutcome.SUCCEEDED:
                        raise ModelTurnStateError(
                            "completed successful model turn lacks resumable role state"
                        )
                elif current is ModelTurnPhase.AMBIGUOUS:
                    payload = event.get("payload")
                    if not isinstance(payload, Mapping) or payload.get("reason_code") not in {
                        reason.value for reason in ModelTurnAmbiguity
                    } or set(payload) != {"reason_code"}:
                        raise ModelTurnStateError("ambiguous event has unexpected payload")
                else:
                    raise ModelTurnStateError("model-turn provenance has invalid terminal transition")
            else:
                raise ModelTurnStateError("model-turn provenance has too many transitions")
            events.append(dict(event))
            phase = current
        if phase is None:
            raise ModelTurnStateError("model-turn provenance has no phase")
        if phase is ModelTurnPhase.COMPLETED and result is None:
            raise ModelTurnStateError("completed model-turn provenance lacks a result")
        return ModelTurnRecord(plan, phase, result, role_result, tuple(events))
