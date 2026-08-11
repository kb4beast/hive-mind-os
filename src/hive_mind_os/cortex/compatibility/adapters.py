"""Additive typed adapters for the pre-Cortex runtime surfaces.

Adapters never run a legacy and canonical implementation for the same operation.
They either invoke the selected legacy owner or produce a read-only projection that
can later be compared with an independently supplied canonical observation.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Generic, Mapping, TypeVar

from ...brain_kernel.canonical import canonical_digest
from .models import (
    AdapterDescriptor,
    AdapterMode,
    AuthorityPath,
    CompatibilityError,
    CompatibilityObservation,
    CompatibilityRequest,
    RetirementBlocker,
)

_T = TypeVar("_T")


def _plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _plain(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if hasattr(value, "value") and not isinstance(value, (str, bytes)):
        return value.value
    return value


class LegacyAdapter(Generic[_T]):
    """Common single-owner routing and projection behavior."""

    descriptor: AdapterDescriptor

    def __init__(self, legacy: _T | None = None, *, mode: AdapterMode = AdapterMode.LEGACY) -> None:
        self.legacy = legacy
        self.mode = AdapterMode(mode)

    def request(
        self,
        mission_id: str,
        operation: str,
        payload: Mapping[str, Any] | None = None,
    ) -> CompatibilityRequest:
        return CompatibilityRequest.from_payload(
            self.descriptor.entry_point,
            operation,
            mission_id,
            payload,
            authority_path=AuthorityPath(self.mode.value),
            rollback_ref=self.descriptor.retirement_blocker.rollback_ref,
        )

    def invoke(self, operation: str, *args: Any, **kwargs: Any) -> Any:
        """Invoke exactly the selected owner; projections are never a second write."""

        if self.mode is not AdapterMode.LEGACY:
            raise CompatibilityError(
                f"{self.descriptor.entry_point} has no qualified {self.mode.value} owner"
            )
        if self.legacy is None:
            raise CompatibilityError(f"{self.descriptor.entry_point} legacy owner is unavailable")
        target = getattr(self.legacy, operation, None)
        if not callable(target):
            raise CompatibilityError(
                f"{self.descriptor.entry_point} has no legacy operation {operation!r}"
            )
        return target(*args, **kwargs)

    def project(
        self,
        operation: str,
        result: Any,
        *,
        status: str = "succeeded",
        behavior_keys: tuple[str, ...] = (),
        evidence_keys: tuple[str, ...] = (),
        effect_count: int = 0,
    ) -> CompatibilityObservation:
        document = _plain(result)
        if not isinstance(document, Mapping):
            document = {"value": document}
        behavior = {
            key: document[key]
            for key in behavior_keys
            if key in document
        }
        evidence = {
            key: document[key]
            for key in evidence_keys
            if key in document
        }
        if not behavior:
            behavior = {"status": status, "result_digest": canonical_digest(document)}
        return CompatibilityObservation(
            self.descriptor.entry_point,
            operation,
            AuthorityPath(self.mode.value),
            status,
            behavior,
            evidence,
            effect_count,
        )


class RepositoryMissionAdapter(LegacyAdapter[Any]):
    descriptor = AdapterDescriptor(
        "RepositoryMission",
        "hive_mind_os.mission.RepositoryMission",
        "repository effect adapter plus Curator verifier",
        AuthorityPath.LEGACY,
        RetirementBlocker(
            "RepositoryMission",
            "canonical repository effect ownership has not passed candidate/effect/receipt parity",
            ("candidate parity", "effect receipt parity", "fresh Curator verification", "rollback rehearsal"),
            "rollback:repository-mission-legacy",
        ),
    )

    def project_report(self, report: Any) -> CompatibilityObservation:
        return self.project(
            "run",
            report.to_dict() if hasattr(report, "to_dict") else report,
            status=str(getattr(getattr(report, "status", None), "value", "succeeded")),
            behavior_keys=("status", "curator_verdict", "failure", "head_sha"),
            evidence_keys=("receipts", "receipt_root", "tree_digest", "event_types", "ledger_events"),
            # The report is already produced by the selected legacy owner.  This
            # projection itself is read-only and must not be counted as another effect.
            effect_count=0,
        )


class MissionLoopAdapter(LegacyAdapter[Any]):
    descriptor = AdapterDescriptor(
        "MissionLoop",
        "hive_mind_os.mission_loop.MissionLoop",
        "canonical role/action protocol",
        AuthorityPath.LEGACY,
        RetirementBlocker(
            "MissionLoop",
            "typed Builder action and retry parity has not been accepted",
            ("action parity", "retry parity", "policy decision parity", "rollback rehearsal"),
            "rollback:mission-loop-legacy",
        ),
    )
    _ACTIONS = frozenset({"search", "write_file", "apply_patch", "run_command", "checkpoint_candidate", "remand"})

    def translate_action(self, action: Any) -> CompatibilityRequest:
        name = str(getattr(action, "name", ""))
        payload = getattr(action, "payload", {})
        if name not in self._ACTIONS:
            raise CompatibilityError(f"unsupported MissionLoop action: {name!r}")
        if not isinstance(payload, Mapping):
            raise CompatibilityError("MissionLoop action payload must be a mapping")
        mission_id = str(getattr(self.legacy, "_state", {}).mission_id) if self.legacy is not None and hasattr(getattr(self.legacy, "_state", None), "mission_id") else "MISSION-compatibility"
        return self.request(mission_id, name, payload)

    def project_state(self, state: Any) -> CompatibilityObservation:
        document = state.to_dict() if hasattr(state, "to_dict") else _plain(state)
        return self.project(
            "state",
            document,
            status=str(getattr(getattr(state, "status", None), "value", "unknown")),
            behavior_keys=("status", "current_role", "revision"),
            evidence_keys=("work_items", "budget", "events", "receipts"),
        )


class AutonomousBrainAdapter(LegacyAdapter[Any]):
    descriptor = AdapterDescriptor(
        "AutonomousBrain",
        "hive_mind_os.autonomous_os.AutonomousBrain",
        "canonical host/effect and outcome-learning adapters",
        AuthorityPath.LEGACY,
        RetirementBlocker(
            "AutonomousBrain",
            "run charter, feedback, and point-in-time learning parity has not been accepted",
            ("run charter parity", "feedback projection parity", "PIT learning parity", "rollback rehearsal"),
            "rollback:autonomous-brain-legacy",
        ),
    )

    def project_run(self, run: Mapping[str, Any]) -> CompatibilityObservation:
        return self.project(
            "run",
            run,
            status=str(run.get("status", "unknown")),
            behavior_keys=("run_id", "status", "branch", "start_commit", "host"),
            evidence_keys=("prompt_digest", "authority", "protected_branches"),
        )

    def project_feedback(self, feedback: Mapping[str, Any]) -> CompatibilityObservation:
        return self.project(
            "feedback",
            feedback,
            status=str(feedback.get("status", "recorded")),
            behavior_keys=("kind", "remote_id", "status"),
            evidence_keys=("payload_digest", "run_id", "deduplicated"),
        )


class LegacyWorkerAdapter(LegacyAdapter[Any]):
    descriptor = AdapterDescriptor(
        "legacy workers",
        "hive_mind_os.workers.Worker / execute_mission_job",
        "canonical leases and delivery workers",
        AuthorityPath.LEGACY,
        RetirementBlocker(
            "legacy workers",
            "canonical lease recovery and idempotent delivery parity has not been accepted",
            ("lease recovery", "idempotent completion", "failure/dead-letter parity", "rollback rehearsal"),
            "rollback:legacy-workers",
        ),
    )

    def project_job(self, job: Any) -> CompatibilityObservation:
        payload = _plain(getattr(job, "payload", {}))
        evidence = {
            "job_id": getattr(job, "id", None),
            "payload_digest": getattr(job, "payload_digest", None),
            "attempts": getattr(job, "attempts", None),
            "lease_owner": getattr(job, "lease_owner", None),
            "lease_expiry": getattr(job, "lease_expiry", None),
            "mission_id": getattr(job, "mission_id", None),
            "payload": payload,
        }
        return self.project(
            "job",
            {
                "state": getattr(job, "state", "unknown"),
                "kind": getattr(job, "kind", "unknown"),
                **evidence,
            },
            status=str(getattr(job, "state", "unknown")),
            behavior_keys=("state", "kind", "mission_id"),
            evidence_keys=tuple(evidence),
        )


class CompatibilityRegistry:
    """Closed registry proving every in-scope legacy entry point is typed."""

    def __init__(self, adapters: tuple[LegacyAdapter[Any], ...] | None = None) -> None:
        values = adapters or (
            RepositoryMissionAdapter(),
            MissionLoopAdapter(),
            AutonomousBrainAdapter(),
            LegacyWorkerAdapter(),
        )
        self._adapters = {adapter.descriptor.entry_point: adapter for adapter in values}
        if len(self._adapters) != len(values):
            raise ValueError("compatibility entry points must be unique")

    def adapter_for(self, entry_point: str) -> LegacyAdapter[Any]:
        try:
            return self._adapters[entry_point]
        except KeyError as error:
            raise CompatibilityError(f"unregistered legacy entry point: {entry_point}") from error

    def descriptors(self) -> tuple[AdapterDescriptor, ...]:
        return tuple(self._adapters[key].descriptor for key in sorted(self._adapters))

    def retirement_blockers(self) -> tuple[RetirementBlocker, ...]:
        return tuple(descriptor.retirement_blocker for descriptor in self.descriptors())


def default_compatibility_registry() -> CompatibilityRegistry:
    return CompatibilityRegistry()
