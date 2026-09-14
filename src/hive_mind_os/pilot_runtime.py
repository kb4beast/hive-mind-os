"""Durable N31/N32 pilot observation runtime without implicit authority."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import RLock
from typing import Iterable

from .whole_os_qualification import (
    Disposition,
    EvidenceKind,
    EvidenceRef,
    ExternalObligation,
    PilotAttempt,
    PilotReport,
)


@dataclass(frozen=True, slots=True)
class PilotPlan:
    pilot_id: str
    mode: str
    candidate_digest: str
    subject_ids: tuple[str, ...]
    starts_at: int
    ends_at: int
    maximum_concurrent: int
    daily_resource_limit: int
    delivery_rate_limit: int
    authority_digest: str

    def __post_init__(self) -> None:
        for name in ("pilot_id", "candidate_digest", "authority_digest"):
            if (
                not isinstance(getattr(self, name), str)
                or not getattr(self, name).strip()
            ):
                raise ValueError(f"{name} is required")
        if self.mode not in {"self", "external", "roblox"}:
            raise ValueError("invalid pilot mode")
        if not self.subject_ids or len(set(self.subject_ids)) != len(self.subject_ids):
            raise ValueError("pilot subjects must be unique and nonempty")
        if self.ends_at <= self.starts_at:
            raise ValueError("pilot window must be positive")
        for value in (
            self.maximum_concurrent,
            self.daily_resource_limit,
            self.delivery_rate_limit,
        ):
            if type(value) is not int or value < 1:
                raise ValueError("pilot limits must be positive integers")
        if self.ends_at - self.starts_at < 72 * 60 * 60:
            raise ValueError("pilot window must cover the required 72-hour observation")


@dataclass(frozen=True, slots=True)
class PilotState:
    plan: PilotPlan
    attempts: tuple[PilotAttempt, ...] = ()
    restart_exercised: bool = False
    duplicate_effects: int = 0
    avoidable_owner_questions: int = 0
    rollback_evidence: EvidenceRef | None = None
    obligations: tuple[ExternalObligation, ...] = ()
    revision: int = 0
    observed_through: int | None = None

    def __post_init__(self) -> None:
        observed = (
            self.plan.starts_at
            if self.observed_through is None
            else self.observed_through
        )
        if not self.plan.starts_at <= observed <= self.plan.ends_at:
            raise ValueError("pilot observation must stay inside the planned window")
        if type(self.revision) is not int or self.revision < 0:
            raise ValueError("pilot revision must be a nonnegative integer")


class PilotStore:
    """Atomic successor-state store; old revisions are retained as JSONL events."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.current = self.root / "pilot-current.json"
        self.history = self.root / "pilot-history.jsonl"
        self._lock = RLock()

    @staticmethod
    def _document(state: PilotState) -> dict[str, object]:
        return asdict(state)

    def save(self, state: PilotState, *, expected_revision: int | None = None) -> None:
        with self._lock:
            prior = self.load() if self.current.exists() else None
            actual = prior.revision if prior else None
            if actual != expected_revision:
                raise ValueError("stale pilot state revision")
            document = self._document(state)
            encoded = json.dumps(
                document, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
            temporary = self.current.with_suffix(".tmp")
            temporary.write_text(encoded + "\n", encoding="utf-8")
            temporary.replace(self.current)
            with self.history.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(encoded + "\n")

    def load(self) -> PilotState:
        raw = json.loads(self.current.read_text(encoding="utf-8"))
        plan = PilotPlan(**raw["plan"])

        def evidence(value):
            if value is None:
                return None
            return EvidenceRef(
                value["uri"],
                value["digest"],
                EvidenceKind(value["kind"]),
                value["subject_id"],
                value["observed_at"],
            )

        attempts = tuple(
            PilotAttempt(
                item["attempt_id"],
                item["subject_id"],
                item["family_id"],
                item["candidate_digest"],
                item["status"],
                evidence(item["delivery_receipt"]),
            )
            for item in raw["attempts"]
        )
        rollback = evidence(raw["rollback_evidence"])
        obligations = tuple(
            ExternalObligation(
                item["obligation_id"],
                Disposition(item["kind"]),
                item["description"],
                tuple(item["blocks_claims"]),
            )
            for item in raw["obligations"]
        )
        return PilotState(
            plan,
            attempts,
            raw["restart_exercised"],
            raw["duplicate_effects"],
            raw["avoidable_owner_questions"],
            rollback,
            obligations,
            raw["revision"],
            raw.get("observed_through"),
        )


class PilotController:
    def __init__(self, store: PilotStore, plan: PilotPlan) -> None:
        self.store, self.plan = store, plan
        if store.current.exists():
            state = store.load()
            if state.plan != plan:
                raise ValueError("existing pilot state belongs to another plan")
        else:
            store.save(PilotState(plan), expected_revision=None)

    def _update(self, transform) -> PilotState:
        state = self.store.load()
        successor = transform(state)
        if successor.revision != state.revision + 1:
            raise ValueError("pilot transition must increment revision exactly once")
        self.store.save(successor, expected_revision=state.revision)
        return successor

    def record_attempt(self, attempt: PilotAttempt) -> PilotState:
        if (
            attempt.subject_id not in self.plan.subject_ids
            or attempt.candidate_digest != self.plan.candidate_digest
        ):
            raise ValueError("attempt is outside the pilot subject/candidate")

        def apply(state: PilotState) -> PilotState:
            if any(row.attempt_id == attempt.attempt_id for row in state.attempts):
                existing = next(
                    row
                    for row in state.attempts
                    if row.attempt_id == attempt.attempt_id
                )
                if existing != attempt:
                    raise ValueError("attempt identity already has different content")
                return state
            if len(state.attempts) >= state.plan.daily_resource_limit:
                raise ValueError("pilot daily resource limit exhausted")
            if (
                attempt.status == "accepted"
                and sum(row.status == "accepted" for row in state.attempts)
                >= state.plan.delivery_rate_limit
            ):
                raise ValueError("pilot delivery rate limit exhausted")
            return PilotState(
                state.plan,
                (*state.attempts, attempt),
                state.restart_exercised,
                state.duplicate_effects,
                state.avoidable_owner_questions,
                state.rollback_evidence,
                state.obligations,
                state.revision + 1,
                state.observed_through,
            )

        state = self.store.load()
        if any(row.attempt_id == attempt.attempt_id for row in state.attempts):
            existing = next(
                row for row in state.attempts if row.attempt_id == attempt.attempt_id
            )
            if existing != attempt:
                raise ValueError("attempt identity already has different content")
            return state
        return self._update(apply)

    def record_controls(
        self,
        *,
        restart_exercised: bool | None = None,
        duplicate_effects: int = 0,
        avoidable_owner_questions: int = 0,
        rollback_evidence: EvidenceRef | None = None,
        obligations: Iterable[ExternalObligation] = (),
    ) -> PilotState:
        if duplicate_effects < 0 or avoidable_owner_questions < 0:
            raise ValueError("pilot control counters cannot decrease")
        supplied_obligations = tuple(obligations)

        def apply(state: PilotState) -> PilotState:
            reconciled = {item.obligation_id: item for item in state.obligations}
            for obligation in supplied_obligations:
                previous = reconciled.get(obligation.obligation_id)
                if previous is not None and previous != obligation:
                    raise ValueError(
                        "obligation identity already has different content"
                    )
                reconciled[obligation.obligation_id] = obligation
            return PilotState(
                state.plan,
                state.attempts,
                state.restart_exercised
                if restart_exercised is None
                else restart_exercised,
                state.duplicate_effects + duplicate_effects,
                state.avoidable_owner_questions + avoidable_owner_questions,
                rollback_evidence or state.rollback_evidence,
                tuple(reconciled.values()),
                state.revision + 1,
                state.observed_through,
            )

        return self._update(apply)

    def record_observation(self, observed_at: int) -> PilotState:
        """Advance the durable observation watermark without fabricating elapsed time."""
        if type(observed_at) is not int:
            raise ValueError("pilot observation timestamp must be an integer")

        def apply(state: PilotState) -> PilotState:
            prior = (
                state.plan.starts_at
                if state.observed_through is None
                else state.observed_through
            )
            if observed_at < prior:
                raise ValueError("pilot observation timestamp cannot move backward")
            return PilotState(
                state.plan,
                state.attempts,
                state.restart_exercised,
                state.duplicate_effects,
                state.avoidable_owner_questions,
                state.rollback_evidence,
                state.obligations,
                state.revision + 1,
                observed_at,
            )

        return self._update(apply)

    def report(self) -> PilotReport:
        state = self.store.load()
        observed_through = (
            state.plan.starts_at
            if state.observed_through is None
            else state.observed_through
        )
        return PilotReport(
            state.plan.pilot_id,
            state.plan.mode,
            state.plan.candidate_digest,
            state.plan.starts_at,
            observed_through,
            state.attempts,
            state.restart_exercised,
            state.duplicate_effects,
            state.avoidable_owner_questions,
            state.rollback_evidence,
            state.obligations,
        )
