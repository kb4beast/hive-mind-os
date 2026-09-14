"""Bounded N31/N32 orchestration over the configured Whole-OS service.

The controller intent is durable before a host call.  An interrupted or ambiguous
call is never repeated automatically: the active attempt remains present until a
read-only observation and externally receipt-backed evaluator reconcile it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Protocol

from .pilot_runtime import PilotController, PilotState
from .whole_os_qualification import ExternalObligation, PilotAttempt
from .whole_os_service import ServiceObservation


class PilotExecutionBlocker(StrEnum):
    PREREQUISITES_UNRESOLVED = "pilot-prerequisites-unresolved"
    RECONCILIATION_REQUIRED = "pilot-reconciliation-required"
    INVALID_HOST_RESULT = "pilot-invalid-host-result"


class PilotExecutionError(RuntimeError):
    def __init__(
        self,
        blocker: PilotExecutionBlocker,
        detail: str,
        *,
        obligations: tuple[ExternalObligation, ...] = (),
    ) -> None:
        super().__init__(f"{blocker.value}: {detail}")
        self.blocker = blocker
        self.obligations = obligations


class BoundedWholeOSService(Protocol):
    def run_once(self) -> ServiceObservation: ...

    def observe(self) -> ServiceObservation: ...


class PilotAttemptEvaluator(Protocol):
    def __call__(
        self,
        *,
        attempt_id: str,
        subject_id: str,
        family_id: str,
        candidate_digest: str,
        started_at: int,
        ended_at: int,
        resource_units: int,
        domain: str | None,
        observation: ServiceObservation,
    ) -> PilotAttempt: ...


@dataclass(frozen=True, slots=True)
class PilotRunResult:
    observation: ServiceObservation
    attempt: PilotAttempt
    state: PilotState


class WholeOSPilotRunner:
    """Execute at most one configured service step under one durable pilot lease."""

    def __init__(
        self,
        controller: PilotController,
        service: BoundedWholeOSService,
        evaluator: PilotAttemptEvaluator,
        *,
        clock: Callable[[], int],
    ) -> None:
        self.controller = controller
        self.service = service
        self.evaluator = evaluator
        self.clock = clock

    def _ready(self) -> None:
        report = self.controller.report()
        if report.obligations:
            raise PilotExecutionError(
                PilotExecutionBlocker.PREREQUISITES_UNRESOLVED,
                "sealed pilot prerequisites are unresolved",
                obligations=report.obligations,
            )

    @staticmethod
    def _time(clock: Callable[[], int]) -> int:
        value = clock()
        if type(value) is not int or value < 0:
            raise PilotExecutionError(
                PilotExecutionBlocker.INVALID_HOST_RESULT,
                "pilot clock returned an invalid timestamp",
            )
        return value

    def run_once(
        self,
        *,
        attempt_id: str,
        subject_id: str,
        family_id: str,
        resource_units: int = 1,
        domain: str | None = None,
    ) -> PilotRunResult:
        self._ready()
        current = self.controller.store.load()
        if any(item.attempt_id == attempt_id for item in current.active_attempts):
            raise PilotExecutionError(
                PilotExecutionBlocker.RECONCILIATION_REQUIRED,
                "the durable attempt is already active; observe before retrying",
            )
        started_at = self._time(self.clock)
        self.controller.begin_attempt(
            attempt_id=attempt_id,
            subject_id=subject_id,
            family_id=family_id,
            started_at=started_at,
            resource_units=resource_units,
            domain=domain,
        )
        try:
            observation = self.service.run_once()
            ended_at = self._time(self.clock)
            attempt = self.evaluator(
                attempt_id=attempt_id,
                subject_id=subject_id,
                family_id=family_id,
                candidate_digest=self.controller.plan.candidate_digest,
                started_at=started_at,
                ended_at=ended_at,
                resource_units=resource_units,
                domain=domain,
                observation=observation,
            )
            state = self.controller.complete_attempt(attempt)
        except PilotExecutionError:
            raise
        except Exception as exc:
            raise PilotExecutionError(
                PilotExecutionBlocker.RECONCILIATION_REQUIRED,
                "host outcome is uncertain; inspect the service before completing",
            ) from exc
        return PilotRunResult(observation, attempt, state)

    def reconcile_from_observation(self, attempt_id: str) -> PilotRunResult:
        """Reconcile an active attempt through the service's read-only observation."""
        self._ready()
        state = self.controller.store.load()
        active = next(
            (item for item in state.active_attempts if item.attempt_id == attempt_id),
            None,
        )
        if active is None:
            raise PilotExecutionError(
                PilotExecutionBlocker.INVALID_HOST_RESULT,
                "no active durable attempt exists for reconciliation",
            )
        try:
            observation = self.service.observe()
            ended_at = self._time(self.clock)
            attempt = self.evaluator(
                attempt_id=active.attempt_id,
                subject_id=active.subject_id,
                family_id=active.family_id,
                candidate_digest=active.candidate_digest,
                started_at=active.started_at,
                ended_at=ended_at,
                resource_units=active.resource_units,
                domain=active.domain,
                observation=observation,
            )
            successor = self.controller.complete_attempt(attempt)
        except PilotExecutionError:
            raise
        except Exception as exc:
            raise PilotExecutionError(
                PilotExecutionBlocker.RECONCILIATION_REQUIRED,
                "read-only observation did not establish a final exact attempt",
            ) from exc
        return PilotRunResult(observation, attempt, successor)
