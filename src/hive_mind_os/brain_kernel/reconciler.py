"""Deterministic desired-state reconciliation for kernel mission recovery.

The event spine and scheduler remain authoritative.  This module only derives a
bounded repair plan from an observed snapshot.  Applying a plan is an explicit
caller action, so reconciliation cannot silently execute an effect, rewrite an
event, or acquire authority that was not present in the observation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable, Iterable, Mapping

from .canonical import canonical_digest


class RepairKind(StrEnum):
    """Finite repair vocabulary understood by the reconciliation boundary."""

    RELEASE_STALE_LEASE = "release-stale-lease"
    RETRY = "retry"
    REMAND = "remand"
    REBUILD_WORKSPACE = "rebuild-workspace"
    ROLLBACK = "rollback"
    QUARANTINE = "quarantine"


@dataclass(frozen=True, slots=True)
class ReconciliationPolicy:
    """Bounds for automatic recovery decisions."""

    max_retries: int = 3
    no_progress_limit: int = 3
    max_repairs_per_pass: int = 8

    def __post_init__(self) -> None:
        if self.max_retries < 1:
            raise ValueError("max_retries must be positive")
        if self.no_progress_limit < 1:
            raise ValueError("no_progress_limit must be positive")
        if self.max_repairs_per_pass < 1:
            raise ValueError("max_repairs_per_pass must be positive")


@dataclass(frozen=True, slots=True)
class ObservedState:
    """Canonical, immutable-in-shape input to the reconciler.

    The records intentionally remain plain mappings: observations come from
    different adapters (event projections, scheduler rows, workspace probes,
    and provider callbacks).  :meth:`from_document` sorts and copies them so
    equivalent observations produce byte-identical projections.
    """

    mission_id: str
    mission_status: str
    work: tuple[Mapping[str, Any], ...] = ()
    leases: tuple[Mapping[str, Any], ...] = ()
    intents: tuple[Mapping[str, Any], ...] = ()
    workspaces: tuple[Mapping[str, Any], ...] = ()
    provider_failures: tuple[Mapping[str, Any], ...] = ()
    verifications: tuple[Mapping[str, Any], ...] = ()
    no_progress_count: int = 0
    progress_signature: str | None = None
    authority_scope: tuple[str, ...] = ()

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "ObservedState":
        if not isinstance(document, Mapping):
            raise TypeError("observed state must be a mapping")
        mission = document.get("mission")
        mission_document = mission if isinstance(mission, Mapping) else {}
        mission_id = document.get("mission_id", mission_document.get("mission_id"))
        missions = document.get("missions")
        if mission_id is None and isinstance(missions, Mapping) and len(missions) == 1:
            mission_id = next(iter(missions))
        if mission_id is not None and isinstance(missions, Mapping):
            mission_document = missions.get(mission_id, mission_document)
        status = document.get(
            "mission_status",
            document.get(
                "status",
                mission_document
                if isinstance(mission_document, str)
                else mission_document.get("status", "CREATED"),
            ),
        )
        if not isinstance(mission_id, str) or not mission_id.strip():
            raise ValueError("observed mission_id is required")
        if not isinstance(status, str) or not status.strip():
            raise ValueError("observed mission status is required")

        work = _records(document.get("work", {}), "work_id")
        leases = _records(document.get("leases", ()), "lease_id")
        intents = _records(document.get("intents", ()), "intent_id")
        workspaces = _records(document.get("workspaces", ()), "workspace_id")
        provider_failures = _records(
            document.get("provider_failures", ()), "failure_id", fallback="work_id"
        )
        verifications = _records(
            document.get("verifications", ()), "verification_id", fallback="work_id"
        )
        progress = document.get("progress", {})
        progress_document = progress if isinstance(progress, Mapping) else {}
        count = document.get(
            "no_progress_count",
            progress_document.get("no_progress_count", 0),
        )
        if type(count) is not int or count < 0:
            raise ValueError("no_progress_count must be a non-negative integer")
        signature = document.get(
            "progress_signature", progress_document.get("signature")
        )
        if signature is not None and not isinstance(signature, str):
            raise ValueError("progress_signature must be a string or null")
        scope = document.get("authority_scope", ())
        if isinstance(scope, str) or not isinstance(scope, Iterable):
            raise ValueError("authority_scope must be an iterable of paths")
        authority_scope = tuple(sorted({str(item) for item in scope}))
        return cls(
            mission_id=mission_id,
            mission_status=status.upper(),
            work=work,
            leases=leases,
            intents=intents,
            workspaces=workspaces,
            provider_failures=provider_failures,
            verifications=verifications,
            no_progress_count=count,
            progress_signature=signature,
            authority_scope=authority_scope,
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "mission_status": self.mission_status,
            "work": [dict(item) for item in self.work],
            "leases": [dict(item) for item in self.leases],
            "intents": [dict(item) for item in self.intents],
            "workspaces": [dict(item) for item in self.workspaces],
            "provider_failures": [dict(item) for item in self.provider_failures],
            "verifications": [dict(item) for item in self.verifications],
            "no_progress_count": self.no_progress_count,
            "progress_signature": self.progress_signature,
            "authority_scope": list(self.authority_scope),
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())


@dataclass(frozen=True, slots=True)
class RepairAction:
    """One deterministic, bounded proposal; it is not an executed effect."""

    kind: RepairKind
    target_id: str
    reason: str
    attempt: int = 0
    max_attempts: int = 1
    authority_scope: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.target_id.strip() or not self.reason.strip():
            raise ValueError("repair target and reason are required")
        if self.attempt < 0 or self.max_attempts < 1:
            raise ValueError("repair attempts are out of bounds")
        if self.attempt > self.max_attempts:
            raise ValueError("repair attempt exceeds its bound")
        if tuple(sorted(set(self.authority_scope))) != self.authority_scope:
            raise ValueError("authority_scope must be sorted and unique")

    @property
    def action_id(self) -> str:
        return f"{self.kind.value}:{self.target_id}"

    def to_document(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "kind": self.kind.value,
            "target_id": self.target_id,
            "reason": self.reason,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "authority_scope": list(self.authority_scope),
        }


@dataclass(frozen=True, slots=True)
class DesiredState:
    """Reconciled projection and the finite repairs needed to approach it."""

    mission_id: str
    mission_status: str
    work: tuple[Mapping[str, Any], ...]
    actions: tuple[RepairAction, ...]
    quarantined: bool
    observed_digest: str
    desired_digest: str

    def to_document(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "mission_status": self.mission_status,
            "work": [dict(item) for item in self.work],
            "actions": [action.to_document() for action in self.actions],
            "quarantined": self.quarantined,
            "observed_digest": self.observed_digest,
            "desired_digest": self.desired_digest,
        }


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Result of one pass; callers must explicitly apply its actions."""

    observed: ObservedState
    desired: DesiredState
    now: float

    @property
    def actions(self) -> tuple[RepairAction, ...]:
        return self.desired.actions

    @property
    def quarantined(self) -> bool:
        return self.desired.quarantined

    def apply(
        self,
        handlers: Mapping[str | RepairKind, Callable[[RepairAction], Any]],
    ) -> tuple[str, ...]:
        """Apply only explicitly supplied handlers, once, in action order.

        Missing handlers are a safe no-op.  The reconciler never invents a
        handler and never turns a proposal into an external side effect.
        """

        applied: list[str] = []
        for action in self.actions:
            handler = handlers.get(action.kind) or handlers.get(action.kind.value)
            if handler is None:
                continue
            handler(action)
            applied.append(action.action_id)
        return tuple(applied)


class DesiredStateReconciler:
    """Pure planner for bounded mission repair."""

    def __init__(self, policy: ReconciliationPolicy | None = None) -> None:
        self.policy = policy or ReconciliationPolicy()

    def reconcile(
        self,
        observed: ObservedState | Mapping[str, Any],
        *,
        now: float,
    ) -> ReconciliationResult:
        if now < 0:
            raise ValueError("reconciliation time cannot be negative")
        state = observed if isinstance(observed, ObservedState) else ObservedState.from_document(observed)
        work = {str(item["work_id"]): dict(item) for item in state.work}
        leases = {str(item["lease_id"]): item for item in state.leases}
        workspaces = {str(item["workspace_id"]): item for item in state.workspaces}
        failures = {str(item["failure_id"]): item for item in state.provider_failures}
        verifications = {}
        for item in state.verifications:
            work_id = item.get("work_id")
            if work_id is None:
                work_id = item.get("verification_id")
            if work_id is not None:
                verifications[str(work_id)] = item
        actions: dict[str, RepairAction] = {}
        desired_work = {work_id: dict(item) for work_id, item in work.items()}

        def add(
            kind: RepairKind,
            target_id: str,
            reason: str,
            *,
            attempt: int = 0,
            max_attempts: int = 1,
            scope: Iterable[str] = (),
        ) -> None:
            action = RepairAction(
                kind,
                target_id,
                reason,
                attempt=attempt,
                max_attempts=max_attempts,
                authority_scope=tuple(sorted(set(str(item) for item in scope))),
            )
            actions.setdefault(action.action_id, action)

        for lease_id in sorted(leases):
            lease = leases[lease_id]
            expiry = lease.get("expires_at", lease.get("lease_expiry"))
            status = str(lease.get("state", lease.get("status", "ACTIVE"))).upper()
            if status not in {"ACTIVE", "LEASED"} or not _expired(expiry, now):
                continue
            work_id = str(lease.get("work_id", lease_id))
            record = work.get(work_id, {})
            add(
                RepairKind.RELEASE_STALE_LEASE,
                lease_id,
                "lease expired; release it before retrying work",
                scope=record.get("authority_scope", state.authority_scope),
            )
            if work_id in desired_work and _nonterminal(record.get("status")):
                desired_work[work_id]["desired_status"] = "READY"

        for intent in sorted(state.intents, key=_record_key):
            intent_id = str(intent["intent_id"])
            work_id = intent.get("work_id")
            record = work.get(str(work_id)) if work_id is not None else None
            if record is None or record.get("mission_id", state.mission_id) != state.mission_id:
                add(
                    RepairKind.QUARANTINE,
                    intent_id,
                    "orphaned intent is not bound to this mission's work projection",
                    scope=state.authority_scope,
                )
                continue
            if str(record.get("status", "")).upper() in {
                "PROPOSED",
                "READY",
                "LEASED",
                "RUNNING",
                "AWAITING_VERIFICATION",
            }:
                add(
                    RepairKind.REMAND,
                    str(work_id),
                    "intent requires a fresh bounded work decision",
                    attempt=int(record.get("attempts", 0)),
                    max_attempts=self.policy.max_retries,
                    scope=record.get("authority_scope", state.authority_scope),
                )

        for workspace_id in sorted(workspaces):
            workspace = workspaces[workspace_id]
            exists = workspace.get("exists")
            if exists is None:
                exists = workspace.get("present", True)
            if bool(exists):
                continue
            work_id = str(workspace.get("work_id", workspace_id))
            record = work.get(work_id, {})
            attempts = int(workspace.get("rebuild_attempts", record.get("attempts", 0)))
            scope = record.get("authority_scope", state.authority_scope)
            if attempts < self.policy.max_retries:
                add(
                    RepairKind.REBUILD_WORKSPACE,
                    workspace_id,
                    "workspace is missing; rebuild only the recorded workspace",
                    attempt=attempts,
                    max_attempts=self.policy.max_retries,
                    scope=scope,
                )
                if work_id in desired_work:
                    desired_work[work_id]["desired_status"] = "READY"
            else:
                add(
                    RepairKind.QUARANTINE,
                    workspace_id,
                    "workspace rebuild budget is exhausted",
                    attempt=attempts,
                    max_attempts=self.policy.max_retries,
                    scope=scope,
                )

        for failure_id in sorted(failures):
            failure = failures[failure_id]
            if failure.get("resolved") is True:
                continue
            work_id = str(failure.get("work_id", failure_id))
            record = work.get(work_id, {})
            attempts = int(failure.get("attempts", record.get("attempts", 0)))
            retryable = bool(failure.get("retryable", failure.get("transient", True)))
            scope = record.get("authority_scope", state.authority_scope)
            if retryable and attempts < self.policy.max_retries:
                add(
                    RepairKind.RETRY,
                    work_id,
                    "provider failure is retryable within the attempt budget",
                    attempt=attempts,
                    max_attempts=self.policy.max_retries,
                    scope=scope,
                )
            else:
                add(
                    RepairKind.QUARANTINE,
                    work_id,
                    "provider failure is terminal or retry budget is exhausted",
                    attempt=attempts,
                    max_attempts=self.policy.max_retries,
                    scope=scope,
                )

        for work_id in sorted(work):
            record = work[work_id]
            verification = verifications.get(work_id)
            verification_status = (
                str(verification.get("status", "")).upper() if verification else ""
            )
            if str(record.get("status", "")).upper() != "AWAITING_VERIFICATION":
                continue
            if verification_status not in {"INTERRUPTED", "MISSING", "ABORTED"}:
                continue
            attempts = int(
                verification.get("attempts", record.get("verification_attempts", 0))
            ) if verification else int(record.get("verification_attempts", 0))
            scope = record.get("authority_scope", state.authority_scope)
            if attempts < self.policy.max_retries:
                add(
                    RepairKind.REMAND,
                    work_id,
                    "verification was interrupted; remand without re-running the effect",
                    attempt=attempts,
                    max_attempts=self.policy.max_retries,
                    scope=scope,
                )
            else:
                add(
                    RepairKind.QUARANTINE,
                    work_id,
                    "verification retry budget is exhausted",
                    attempt=attempts,
                    max_attempts=self.policy.max_retries,
                    scope=scope,
                )

        for work_id in sorted(work):
            record = work[work_id]
            integration_status = str(record.get("integration_status", "")).upper()
            if record.get("rollback_required") is True or (
                str(record.get("status", "")).upper() == "INTEGRATING"
                and integration_status in {"FAILED", "PARTIAL", "INTERRUPTED"}
            ):
                add(
                    RepairKind.ROLLBACK,
                    work_id,
                    "integration diverged; restore the last recorded accepted state",
                    scope=record.get("authority_scope", state.authority_scope),
                )
                desired_work[work_id]["desired_status"] = "ROLLING_BACK"

        if state.no_progress_count >= self.policy.no_progress_limit:
            add(
                RepairKind.QUARANTINE,
                state.mission_id,
                "no progress repeated beyond the configured bound",
                attempt=state.no_progress_count,
                max_attempts=self.policy.no_progress_limit,
                scope=state.authority_scope,
            )

        ordered_actions = tuple(
            sorted(actions.values(), key=lambda item: (_priority(item.kind), item.action_id))
        )
        if len(ordered_actions) > self.policy.max_repairs_per_pass:
            ordered_actions = ordered_actions[: self.policy.max_repairs_per_pass - 1] + (
                RepairAction(
                    RepairKind.QUARANTINE,
                    state.mission_id,
                    "repair pass exceeded its bounded action budget",
                    attempt=0,
                    max_attempts=1,
                    authority_scope=state.authority_scope,
                ),
            )
        quarantined = any(action.kind is RepairKind.QUARANTINE for action in ordered_actions)
        desired_status = "QUARANTINED" if quarantined else state.mission_status
        desired_work_records = tuple(
            desired_work[work_id] for work_id in sorted(desired_work)
        )
        desired_document = {
            "mission_id": state.mission_id,
            "mission_status": desired_status,
            "work": [dict(item) for item in desired_work_records],
            "actions": [action.to_document() for action in ordered_actions],
            "quarantined": quarantined,
            "observed_digest": state.digest,
        }
        desired_digest = canonical_digest(desired_document)
        desired = DesiredState(
            state.mission_id,
            desired_status,
            desired_work_records,
            ordered_actions,
            quarantined,
            state.digest,
            desired_digest,
        )
        return ReconciliationResult(state, desired, float(now))


def _records(
    value: Any,
    primary: str,
    *,
    fallback: str | None = None,
) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, Mapping):
        records = []
        for key, item in value.items():
            if not isinstance(item, Mapping):
                raise ValueError(f"{primary} record must be a mapping")
            record = dict(item)
            record.setdefault(primary, str(key))
            records.append(record)
    elif isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        records = []
        for item in value:
            if not isinstance(item, Mapping):
                raise ValueError(f"{primary} record must be a mapping")
            record = dict(item)
            if primary not in record and fallback and fallback in record:
                record[primary] = str(record[fallback])
            records.append(record)
    else:
        raise ValueError(f"{primary} records must be a mapping or sequence")
    for record in records:
        if not isinstance(record.get(primary), str) or not record[primary].strip():
            raise ValueError(f"{primary} is required")
    identifiers = [str(record[primary]) for record in records]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError(f"duplicate {primary} records are ambiguous")
    return tuple(sorted(records, key=_record_key))


def _record_key(record: Mapping[str, Any]) -> tuple[str, str]:
    identifier = str(
        record.get(
            "work_id",
            record.get(
                "lease_id",
                record.get(
                    "intent_id",
                    record.get(
                        "workspace_id",
                        record.get("failure_id", record.get("verification_id", "")),
                    ),
                ),
            ),
        )
    )
    return identifier, canonical_digest(dict(record))


def _expired(value: Any, now: float) -> bool:
    try:
        return float(value) <= now
    except (TypeError, ValueError):
        return False


def _nonterminal(status: Any) -> bool:
    return str(status or "").upper() not in {
        "COMPLETED",
        "CANCELLED",
        "INTEGRATED",
        "TERMINAL_FAILED",
        "QUARANTINED",
    }


def _priority(kind: RepairKind) -> int:
    return {
        RepairKind.QUARANTINE: 0,
        RepairKind.ROLLBACK: 1,
        RepairKind.RELEASE_STALE_LEASE: 2,
        RepairKind.REBUILD_WORKSPACE: 3,
        RepairKind.REMAND: 4,
        RepairKind.RETRY: 5,
    }[kind]


__all__ = [
    "DesiredState",
    "DesiredStateReconciler",
    "ObservedState",
    "ReconciliationPolicy",
    "ReconciliationResult",
    "RepairAction",
    "RepairKind",
]
