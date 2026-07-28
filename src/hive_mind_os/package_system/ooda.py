from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping

_RFC3339_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z"
)


class OODAPhase(StrEnum):
    OBSERVE = "observe"
    ORIENT = "orient"
    DECIDE = "decide"
    ACT = "act"


class OODAStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    FAILED = "failed"


_TERMINAL_STATUSES = frozenset(
    {OODAStatus.SUCCEEDED, OODAStatus.BLOCKED, OODAStatus.FAILED}
)
_NEXT_PHASE = {
    OODAPhase.OBSERVE: OODAPhase.ORIENT,
    OODAPhase.ORIENT: OODAPhase.DECIDE,
    OODAPhase.DECIDE: OODAPhase.ACT,
    OODAPhase.ACT: OODAPhase.OBSERVE,
}


def _require_rfc3339(value: str, label: str) -> None:
    try:
        if _RFC3339_PATTERN.fullmatch(value) is None:
            raise ValueError("not RFC 3339")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("offset is required")
    except ValueError as error:
        raise ValueError(f"{label} must be an RFC 3339 date-time") from error


def _require_evidence(values: tuple[str, ...], label: str) -> None:
    if not values:
        raise ValueError(f"{label} requires evidence")
    if len(values) != len(set(values)):
        raise ValueError(f"{label} evidence_refs cannot contain duplicates")
    if any(not value.strip() for value in values):
        raise ValueError(f"{label} evidence_refs cannot contain empty values")


def _require_optional_ref(value: str | None, label: str) -> None:
    if value is not None and not value.strip():
        raise ValueError(f"{label} cannot be empty")


@dataclass(frozen=True, slots=True)
class OODATransition:
    sequence: int
    from_phase: OODAPhase
    to_phase: OODAPhase
    actor_id: str
    occurred_at: str
    evidence_refs: tuple[str, ...]
    decision_ref: str | None
    policy_decision_ref: str | None
    action_intent_ref: str | None
    action_receipt_ref: str | None
    outcome_ref: str | None

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("transition sequence must be positive")
        if not self.actor_id.strip():
            raise ValueError("transition actor_id cannot be empty")
        _require_rfc3339(self.occurred_at, "transition occurred_at")
        _require_evidence(self.evidence_refs, "every OODA transition")
        for value, label in (
            (self.decision_ref, "decision_ref"),
            (self.policy_decision_ref, "policy_decision_ref"),
            (self.action_intent_ref, "action_intent_ref"),
            (self.action_receipt_ref, "action_receipt_ref"),
            (self.outcome_ref, "outcome_ref"),
        ):
            _require_optional_ref(value, label)
        expected = _NEXT_PHASE[self.from_phase]
        if self.to_phase is not expected:
            raise ValueError(
                f"illegal OODA transition: {self.from_phase.value} to "
                f"{self.to_phase.value}"
            )
        if self.to_phase is OODAPhase.ACT:
            if not all(
                (
                    self.decision_ref,
                    self.policy_decision_ref,
                    self.action_intent_ref,
                )
            ):
                raise ValueError(
                    "entering act requires decision, policy, and action-intent refs"
                )
        if self.from_phase is OODAPhase.ACT:
            if not self.action_receipt_ref or not self.outcome_ref:
                raise ValueError(
                    "act-to-observe requires action receipt and outcome refs"
                )

    def to_contract(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "from_phase": self.from_phase.value,
            "to_phase": self.to_phase.value,
            "actor_id": self.actor_id,
            "occurred_at": self.occurred_at,
            "evidence_refs": list(self.evidence_refs),
            "decision_ref": self.decision_ref,
            "policy_decision_ref": self.policy_decision_ref,
            "action_intent_ref": self.action_intent_ref,
            "action_receipt_ref": self.action_receipt_ref,
            "outcome_ref": self.outcome_ref,
        }


@dataclass(frozen=True, slots=True)
class OODATerminalRecord:
    """An append-only terminal event; it never rewrites an earlier transition."""

    sequence: int
    status: OODAStatus
    actor_id: str
    occurred_at: str
    evidence_refs: tuple[str, ...]
    outcome_ref: str
    reason: str

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("terminal sequence must be positive")
        if self.status not in _TERMINAL_STATUSES:
            raise ValueError("terminal record status must be terminal")
        if not self.actor_id.strip():
            raise ValueError("terminal actor_id cannot be empty")
        _require_rfc3339(self.occurred_at, "terminal occurred_at")
        _require_evidence(self.evidence_refs, "terminal record")
        if not self.reason.strip() or not self.outcome_ref.strip():
            raise ValueError("terminal record requires reason and outcome_ref")

    def to_contract(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "status": self.status.value,
            "actor_id": self.actor_id,
            "occurred_at": self.occurred_at,
            "evidence_refs": list(self.evidence_refs),
            "outcome_ref": self.outcome_ref,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class OODAContractValidation:
    valid: bool
    issues: tuple[str, ...] = ()


def _valid_evidence_contract(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
        and len(value) == len(set(value))
    )


def _valid_timestamp_contract(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        _require_rfc3339(value, "occurred_at")
    except ValueError:
        return False
    return True


def validate_ooda_contract(document: object) -> OODAContractValidation:
    """Validate OODA invariants the supported JSON Schema subset cannot express.

    The repository's small schema evaluator deliberately does not implement
    cross-field equality or arithmetic. This deterministic validator therefore
    proves phase/sequence consistency and append-only termination after structural
    JSON Schema validation.
    """

    issues: list[str] = []
    if not isinstance(document, Mapping):
        return OODAContractValidation(False, ("OODA contract must be an object",))

    phase_value = document.get("phase")
    status_value = document.get("status")
    sequence = document.get("sequence")
    iteration = document.get("iteration")
    try:
        phase = OODAPhase(phase_value)
    except (TypeError, ValueError):
        phase = None
        issues.append("state phase is invalid")
    try:
        status = OODAStatus(status_value)
    except (TypeError, ValueError):
        status = None
        issues.append("state status is invalid")
    if type(sequence) is not int or sequence < 0:
        issues.append("state sequence must be a nonnegative integer")
    if type(iteration) is not int or iteration < 1:
        issues.append("state iteration must be a positive integer")

    transition = document.get("last_transition")
    transition_sequence: int | None = None
    if transition is not None:
        if not isinstance(transition, Mapping):
            issues.append("last_transition must be an object or null")
        else:
            transition_sequence_value = transition.get("sequence")
            if type(transition_sequence_value) is not int or transition_sequence_value < 1:
                issues.append("transition sequence must be a positive integer")
            else:
                transition_sequence = transition_sequence_value
            try:
                from_phase = OODAPhase(transition.get("from_phase"))
                to_phase = OODAPhase(transition.get("to_phase"))
            except (TypeError, ValueError):
                from_phase = None
                to_phase = None
                issues.append("transition phases are invalid")
            if (
                from_phase is not None
                and to_phase is not None
                and _NEXT_PHASE[from_phase] is not to_phase
            ):
                issues.append("transition violates the legal OODA phase cycle")
            if phase is not None and to_phase is not None and phase is not to_phase:
                issues.append("state phase does not match the last transition")
            if not _valid_timestamp_contract(transition.get("occurred_at")):
                issues.append("transition occurred_at is not RFC 3339")
            if not _valid_evidence_contract(transition.get("evidence_refs")):
                issues.append("transition requires unique nonempty evidence_refs")
            if to_phase is OODAPhase.ACT and not all(
                isinstance(value := transition.get(name), str)
                and bool(value.strip())
                for name in (
                    "decision_ref",
                    "policy_decision_ref",
                    "action_intent_ref",
                )
            ):
                issues.append(
                    "entering act requires decision, policy, and action-intent refs"
                )
            if from_phase is OODAPhase.ACT and not all(
                isinstance(value := transition.get(name), str)
                and bool(value.strip())
                for name in ("action_receipt_ref", "outcome_ref")
            ):
                issues.append(
                    "act-to-observe requires action receipt and outcome refs"
                )

    terminal = document.get("terminal_record")
    stop_reason = document.get("stop_reason")
    terminal_sequence: int | None = None
    terminal_status: OODAStatus | None = None
    if terminal is not None:
        if not isinstance(terminal, Mapping):
            issues.append("terminal_record must be an object or null")
        else:
            terminal_sequence_value = terminal.get("sequence")
            if type(terminal_sequence_value) is not int or terminal_sequence_value < 1:
                issues.append("terminal sequence must be a positive integer")
            else:
                terminal_sequence = terminal_sequence_value
            try:
                terminal_status = OODAStatus(terminal.get("status"))
            except (TypeError, ValueError):
                issues.append("terminal status is invalid")
            else:
                if terminal_status not in _TERMINAL_STATUSES:
                    issues.append("terminal record status must be terminal")
            if not _valid_timestamp_contract(terminal.get("occurred_at")):
                issues.append("terminal occurred_at is not RFC 3339")
            if not _valid_evidence_contract(terminal.get("evidence_refs")):
                issues.append("terminal record requires unique nonempty evidence_refs")
            for name in ("actor_id", "reason", "outcome_ref"):
                value = terminal.get(name)
                if not isinstance(value, str) or not value.strip():
                    issues.append(f"terminal {name} is required")

    if status is OODAStatus.RUNNING:
        if terminal is not None:
            issues.append("running state cannot contain a terminal record")
        if stop_reason is not None:
            issues.append("running state cannot contain a stop reason")
        if type(sequence) is int:
            if sequence == 0:
                if transition is not None:
                    issues.append("initial state cannot contain a transition")
                if phase is not OODAPhase.OBSERVE or iteration != 1:
                    issues.append("initial state must be observe iteration 1")
            elif transition_sequence != sequence:
                issues.append("running state sequence must match its last transition")
    elif status in _TERMINAL_STATUSES:
        if terminal is None:
            issues.append("terminal state requires a terminal record")
        if terminal_status is not None and terminal_status is not status:
            issues.append("state status does not match terminal record")
        if (
            isinstance(terminal, Mapping)
            and terminal.get("reason") != stop_reason
        ):
            issues.append("stop_reason does not mirror the terminal record")
        if type(sequence) is int and terminal_sequence != sequence:
            issues.append("state sequence must match terminal record")
        expected_transition_sequence = sequence - 1 if type(sequence) is int else None
        if expected_transition_sequence == 0:
            if transition is not None:
                issues.append("first terminal event cannot rewrite a transition")
        elif transition_sequence != expected_transition_sequence:
            issues.append(
                "terminal sequence must append directly after the last transition"
            )

    return OODAContractValidation(not issues, tuple(dict.fromkeys(issues)))


@dataclass(frozen=True, slots=True)
class OODAState:
    """Replay-only OODA state; it deliberately has no tool execution facility."""

    schema_version: int
    cycle_id: str
    mission_id: str
    iteration: int
    phase: OODAPhase
    status: OODAStatus
    sequence: int
    last_transition: OODATransition | None
    stop_reason: str | None
    terminal_record: OODATerminalRecord | None

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported OODA schema_version")
        if not self.cycle_id.strip() or not self.mission_id.strip():
            raise ValueError("cycle_id and mission_id are required")
        if self.iteration < 1:
            raise ValueError("OODA iteration must be positive")
        if self.sequence < 0:
            raise ValueError("OODA sequence cannot be negative")
        if self.last_transition is not None:
            if self.last_transition.to_phase is not self.phase:
                raise ValueError("last transition phase does not match state")
        if self.status is OODAStatus.RUNNING:
            if self.terminal_record is not None:
                raise ValueError("running OODA state cannot have a terminal record")
            if self.stop_reason is not None:
                raise ValueError("running OODA state cannot have a stop reason")
            if self.sequence == 0:
                if self.last_transition is not None:
                    raise ValueError("initial OODA state cannot have a transition")
                if self.phase is not OODAPhase.OBSERVE or self.iteration != 1:
                    raise ValueError("initial OODA state must be observe iteration 1")
            elif (
                self.last_transition is None
                or self.last_transition.sequence != self.sequence
            ):
                raise ValueError(
                    "running OODA sequence must match its last transition"
                )
        else:
            if self.terminal_record is None:
                raise ValueError("terminal OODA state requires a terminal record")
            if self.terminal_record.status is not self.status:
                raise ValueError("terminal record status does not match state")
            if self.stop_reason != self.terminal_record.reason:
                raise ValueError("stop_reason must mirror the terminal record")
            if self.terminal_record.sequence != self.sequence:
                raise ValueError("terminal record sequence does not match state")
            expected_last = self.sequence - 1
            if expected_last == 0:
                if self.last_transition is not None:
                    raise ValueError("first terminal event cannot rewrite a transition")
            elif (
                self.last_transition is None
                or self.last_transition.sequence != expected_last
            ):
                raise ValueError(
                    "terminal record must append directly after the last transition"
                )

    @classmethod
    def initial(cls, *, cycle_id: str, mission_id: str) -> OODAState:
        return cls(
            schema_version=1,
            cycle_id=cycle_id,
            mission_id=mission_id,
            iteration=1,
            phase=OODAPhase.OBSERVE,
            status=OODAStatus.RUNNING,
            sequence=0,
            last_transition=None,
            stop_reason=None,
            terminal_record=None,
        )

    def apply(self, transition: OODATransition) -> OODAState:
        if self.status is not OODAStatus.RUNNING:
            raise ValueError("cannot apply a transition to a stopped OODA cycle")
        if transition.sequence != self.sequence + 1:
            raise ValueError("OODA transition sequence must increase by exactly one")
        if transition.from_phase is not self.phase:
            raise ValueError("OODA transition does not continue the current phase")
        iteration = self.iteration
        if (
            transition.from_phase is OODAPhase.ACT
            and transition.to_phase is OODAPhase.OBSERVE
        ):
            iteration += 1
        return replace(
            self,
            iteration=iteration,
            phase=transition.to_phase,
            sequence=transition.sequence,
            last_transition=transition,
        )

    def stop(
        self,
        *,
        status: OODAStatus,
        actor_id: str,
        occurred_at: str,
        evidence_refs: tuple[str, ...],
        outcome_ref: str,
        reason: str,
    ) -> OODAState:
        if self.status is not OODAStatus.RUNNING:
            raise ValueError("OODA cycle is already stopped")
        terminal_record = OODATerminalRecord(
            sequence=self.sequence + 1,
            status=status,
            actor_id=actor_id,
            occurred_at=occurred_at,
            evidence_refs=evidence_refs,
            outcome_ref=outcome_ref,
            reason=reason,
        )
        return replace(
            self,
            status=terminal_record.status,
            sequence=terminal_record.sequence,
            stop_reason=terminal_record.reason,
            terminal_record=terminal_record,
        )

    def to_contract(self) -> dict[str, Any]:
        document = {
            "schema_version": self.schema_version,
            "cycle_id": self.cycle_id,
            "mission_id": self.mission_id,
            "iteration": self.iteration,
            "phase": self.phase.value,
            "status": self.status.value,
            "sequence": self.sequence,
            "last_transition": (
                None
                if self.last_transition is None
                else self.last_transition.to_contract()
            ),
            "stop_reason": self.stop_reason,
            "terminal_record": (
                None
                if self.terminal_record is None
                else self.terminal_record.to_contract()
            ),
        }
        validation = validate_ooda_contract(document)
        if not validation.valid:
            raise RuntimeError(
                "internal OODA state violates its contract: "
                + "; ".join(validation.issues)
            )
        return document


__all__ = [
    "OODAContractValidation",
    "OODAPhase",
    "OODAState",
    "OODAStatus",
    "OODATerminalRecord",
    "OODATransition",
    "validate_ooda_contract",
]
