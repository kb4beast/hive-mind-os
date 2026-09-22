"""Durable N31/N32 pilot observation runtime without implicit authority."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
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
    PilotRuntimeEvidence,
    QualificationClaimScope,
)


class PilotBlockerCode(StrEnum):
    MISSING_WHOLE_OS_HOST = "missing-whole-os-host"
    MISSING_SUPERVISOR = "missing-supervisor"
    MISSING_TARGETS = "missing-targets"
    MISSING_RUNTIME = "missing-runtime-evidence"
    MISSING_AUTHORITY = "missing-delivery-authority"
    MISSING_BENCHMARK = "missing-benchmark-candidate"
    MISSING_PRODUCTION_CANDIDATE = "missing-production-candidate"


@dataclass(frozen=True, slots=True)
class PilotPrerequisites:
    whole_os_host: EvidenceRef | None = None
    supervisor: EvidenceRef | None = None
    delivery_authority: EvidenceRef | None = None
    benchmark_candidate: EvidenceRef | None = None
    targets: tuple[EvidenceRef, ...] = ()
    runtime: tuple[EvidenceRef, ...] = ()
    production_candidate: EvidenceRef | None = None

    def __post_init__(self) -> None:
        values = tuple(
            item
            for item in (
                self.whole_os_host,
                self.supervisor,
                self.delivery_authority,
                self.benchmark_candidate,
                self.production_candidate,
                *self.targets,
                *self.runtime,
            )
            if item is not None
        )
        if any(type(item) is not EvidenceRef for item in values):
            raise ValueError("pilot prerequisites must be typed evidence receipts")
        if len(self.targets) != len(set(self.targets)) or len(self.runtime) != len(
            set(self.runtime)
        ):
            raise ValueError("pilot prerequisite evidence must be unique")

    @staticmethod
    def _usable(evidence: EvidenceRef | None) -> bool:
        return evidence is not None and evidence.kind in {
            EvidenceKind.ATTESTED_REAL,
            EvidenceKind.EXTERNAL_RECEIPT,
        }

    def blockers(
        self,
        mode: str,
        claim_scope: QualificationClaimScope,
        subject_ids: tuple[str, ...],
    ) -> tuple[ExternalObligation, ...]:
        rows: list[ExternalObligation] = []

        def block(
            code: PilotBlockerCode, kind: Disposition, detail: str, claims: tuple[str, ...]
        ) -> None:
            rows.append(ExternalObligation(code.value, kind, detail, claims))

        if not self._usable(self.whole_os_host):
            block(
                PilotBlockerCode.MISSING_WHOLE_OS_HOST,
                Disposition.BLOCKED_CAPABILITY,
                "A separately attested configured Whole-OS host is required.",
                ("N31" if mode == "self" else "N32",),
            )
        if mode == "self" and not self._usable(self.supervisor):
            block(
                PilotBlockerCode.MISSING_SUPERVISOR,
                Disposition.BLOCKED_AUTHORITY,
                "An external supervisor receipt with a rollback pointer is required.",
                ("N31",),
            )
        if not self._usable(self.delivery_authority):
            block(
                PilotBlockerCode.MISSING_AUTHORITY,
                Disposition.BLOCKED_AUTHORITY,
                "A target-scoped pilot delivery grant is required.",
                ("N31" if mode == "self" else "N32",),
            )
        if not self._usable(self.production_candidate):
            block(
                PilotBlockerCode.MISSING_PRODUCTION_CANDIDATE,
                Disposition.BLOCKED_SOURCE,
                "An independently qualified exact production candidate is required.",
                ("N31" if mode == "self" else "N32",),
            )
        if (
            claim_scope is QualificationClaimScope.FULL_AUTONOMY_OR_SUPERIORITY
            and not self._usable(self.benchmark_candidate)
        ):
            block(
                PilotBlockerCode.MISSING_BENCHMARK,
                Disposition.BLOCKED_SOURCE,
                "Full-autonomy or superiority scope requires an admitted N30 candidate.",
                ("N31" if mode == "self" else "N32",),
            )
        target_minimum = 0 if mode == "self" else (2 if mode == "external" else 1)
        usable_targets = tuple(item for item in self.targets if self._usable(item))
        required_targets = set(subject_ids) if mode != "self" else set()
        usable_target_ids = {item.subject_id for item in usable_targets}
        if (
            len(usable_target_ids) < target_minimum
            or not required_targets.issubset(usable_target_ids)
        ):
            block(
                PilotBlockerCode.MISSING_TARGETS,
                Disposition.BLOCKED_SOURCE,
                f"The pilot requires {target_minimum} distinct admitted real target(s).",
                ("N32",),
            )
        usable_runtime_ids = {
            item.subject_id for item in self.runtime if self._usable(item)
        }
        if mode in {"external", "roblox"} and not required_targets.issubset(
            usable_runtime_ids
        ):
            block(
                PilotBlockerCode.MISSING_RUNTIME,
                Disposition.BLOCKED_CAPABILITY,
                "Attested target runtime capability evidence is required.",
                ("N32", "R14"),
            )
        return tuple(rows)


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
    prerequisites: PilotPrerequisites = PilotPrerequisites()
    claim_scope: QualificationClaimScope = (
        QualificationClaimScope.FULL_AUTONOMY_OR_SUPERIORITY
    )

    def __post_init__(self) -> None:
        for name in ("pilot_id", "candidate_digest", "authority_digest"):
            if (
                not isinstance(getattr(self, name), str)
                or not getattr(self, name).strip()
            ):
                raise ValueError(f"{name} is required")
        if self.mode not in {"self", "external", "roblox"}:
            raise ValueError("invalid pilot mode")
        if type(self.prerequisites) is not PilotPrerequisites:
            raise ValueError("pilot prerequisites must be typed")
        if type(self.claim_scope) is not QualificationClaimScope:
            raise ValueError("pilot claim scope must be typed")
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
        prerequisite_evidence = tuple(
            item
            for item in (
                self.prerequisites.whole_os_host,
                self.prerequisites.supervisor,
                self.prerequisites.delivery_authority,
                self.prerequisites.benchmark_candidate,
                self.prerequisites.production_candidate,
                *self.prerequisites.targets,
                *self.prerequisites.runtime,
            )
            if item is not None
        )
        if any(item.observed_at > self.starts_at for item in prerequisite_evidence):
            raise ValueError("pilot prerequisite evidence cannot come from the future")
        benchmark = self.prerequisites.benchmark_candidate
        if benchmark is not None and benchmark.subject_id != self.candidate_digest:
            raise ValueError("benchmark receipt targets another candidate")
        production = self.prerequisites.production_candidate
        if production is not None and production.subject_id != self.candidate_digest:
            raise ValueError("production receipt targets another candidate")
        host = self.prerequisites.whole_os_host
        if host is not None and host.subject_id != self.candidate_digest:
            raise ValueError("host receipt targets another candidate")
        for evidence, label in (
            (self.prerequisites.supervisor, "supervisor"),
            (self.prerequisites.delivery_authority, "delivery authority"),
        ):
            if evidence is not None and evidence.subject_id != self.pilot_id:
                raise ValueError(f"{label} receipt targets another pilot")
        authority = self.prerequisites.delivery_authority
        if authority is not None and authority.digest != self.authority_digest:
            raise ValueError("pilot authority digest does not match its receipt")
        if any(
            item.subject_id not in self.subject_ids
            for item in (*self.prerequisites.targets, *self.prerequisites.runtime)
        ):
            raise ValueError("target prerequisite evidence is outside the pilot subjects")


@dataclass(frozen=True, slots=True)
class ActivePilotAttempt:
    attempt_id: str
    subject_id: str
    family_id: str
    candidate_digest: str
    started_at: int
    resource_units: int
    domain: str | None = None

    def __post_init__(self) -> None:
        for name in ("attempt_id", "subject_id", "family_id", "candidate_digest"):
            value = getattr(self, name)
            if (
                type(value) is not str
                or not value
                or value != value.strip()
                or any(character.isspace() for character in value)
            ):
                raise ValueError(f"{name} must be an exact nonempty identifier")
        if type(self.started_at) is not int or self.started_at < 0:
            raise ValueError("active pilot timestamp must be a nonnegative integer")
        if type(self.resource_units) is not int or self.resource_units < 1:
            raise ValueError("active pilot resource units must be positive")
        if self.domain is not None and (
            not self.domain or any(character.isspace() for character in self.domain)
        ):
            raise ValueError("active pilot domain must be an exact identifier")


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
    active_attempts: tuple[ActivePilotAttempt, ...] = ()
    restart_evidence: EvidenceRef | None = None
    observation_evidence: EvidenceRef | None = None

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
        if type(self.restart_exercised) is not bool:
            raise ValueError("pilot restart flag must be boolean")
        for value in (self.duplicate_effects, self.avoidable_owner_questions):
            if type(value) is not int or value < 0:
                raise ValueError("pilot counters must be nonnegative integers")
        active_ids = tuple(item.attempt_id for item in self.active_attempts)
        if len(active_ids) != len(set(active_ids)):
            raise ValueError("active pilot attempt identities must be unique")
        if len(self.active_attempts) > self.plan.maximum_concurrent:
            raise ValueError("active pilot attempts exceed maximum concurrency")


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

        def required_evidence(value) -> EvidenceRef:
            result = evidence(value)
            if result is None:
                raise ValueError("required pilot evidence is missing")
            return result

        plan_raw = dict(raw["plan"])
        plan_raw["subject_ids"] = tuple(plan_raw["subject_ids"])
        plan_raw["claim_scope"] = QualificationClaimScope(
            plan_raw.get(
                "claim_scope",
                QualificationClaimScope.FULL_AUTONOMY_OR_SUPERIORITY,
            )
        )
        prerequisites_raw = plan_raw.pop("prerequisites", None)
        if prerequisites_raw is None:
            prerequisites = PilotPrerequisites()
        else:
            prerequisites = PilotPrerequisites(
                evidence(prerequisites_raw["whole_os_host"]),
                evidence(prerequisites_raw["supervisor"]),
                evidence(prerequisites_raw["delivery_authority"]),
                evidence(prerequisites_raw["benchmark_candidate"]),
                tuple(
                    required_evidence(item) for item in prerequisites_raw["targets"]
                ),
                tuple(
                    required_evidence(item) for item in prerequisites_raw["runtime"]
                ),
                evidence(prerequisites_raw.get("production_candidate")),
            )
        plan = PilotPlan(**plan_raw, prerequisites=prerequisites)

        attempts = tuple(
            PilotAttempt(
                item["attempt_id"],
                item["subject_id"],
                item["family_id"],
                item["candidate_digest"],
                item["status"],
                evidence(item["delivery_receipt"]),
                item.get("started_at"),
                item.get("ended_at"),
                item.get("resource_units", 1),
                item.get("domain"),
                tuple(
                    PilotRuntimeEvidence(
                        runtime_item["check_class"],
                        required_evidence(runtime_item["receipt"]),
                    )
                    for runtime_item in item.get("runtime_evidence", ())
                ),
                item.get("target_runs_without_hive"),
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
        active_attempts = tuple(
            ActivePilotAttempt(**item) for item in raw.get("active_attempts", ())
        )
        return PilotState(
            plan=plan,
            attempts=attempts,
            restart_exercised=raw["restart_exercised"],
            duplicate_effects=raw["duplicate_effects"],
            avoidable_owner_questions=raw["avoidable_owner_questions"],
            rollback_evidence=rollback,
            obligations=obligations,
            revision=raw["revision"],
            observed_through=raw.get("observed_through"),
            active_attempts=active_attempts,
            restart_evidence=evidence(raw.get("restart_evidence")),
            observation_evidence=evidence(raw.get("observation_evidence")),
        )


class PilotController:
    def __init__(self, store: PilotStore, plan: PilotPlan) -> None:
        self.store, self.plan = store, plan
        if store.current.exists():
            state = store.load()
            if state.plan != plan:
                raise ValueError("existing pilot state belongs to another plan")
        else:
            store.save(
                PilotState(
                    plan,
                    obligations=plan.prerequisites.blockers(
                        plan.mode, plan.claim_scope, plan.subject_ids
                    ),
                ),
                expected_revision=None,
            )

    def _update(self, transform) -> PilotState:
        state = self.store.load()
        successor = transform(state)
        if successor.revision != state.revision + 1:
            raise ValueError("pilot transition must increment revision exactly once")
        self.store.save(successor, expected_revision=state.revision)
        return successor

    @staticmethod
    def _day(timestamp: int) -> int:
        return timestamp // (24 * 60 * 60)

    def _validate_attempt_scope(self, attempt: PilotAttempt) -> None:
        if (
            attempt.subject_id not in self.plan.subject_ids
            or attempt.candidate_digest != self.plan.candidate_digest
        ):
            raise ValueError("attempt is outside the pilot subject/candidate")
        if attempt.started_at is None or attempt.ended_at is None:
            raise ValueError("attempt requires observed start and end timestamps")
        if not (
            self.plan.starts_at
            <= attempt.started_at
            <= attempt.ended_at
            <= self.plan.ends_at
        ):
            raise ValueError("attempt is outside the planned pilot window")

    def begin_attempt(
        self,
        *,
        attempt_id: str,
        subject_id: str,
        family_id: str,
        started_at: int,
        resource_units: int = 1,
        domain: str | None = None,
    ) -> PilotState:
        active = ActivePilotAttempt(
            attempt_id,
            subject_id,
            family_id,
            self.plan.candidate_digest,
            started_at,
            resource_units,
            domain,
        )
        if subject_id not in self.plan.subject_ids:
            raise ValueError("attempt is outside the pilot subject")
        if not self.plan.starts_at <= started_at <= self.plan.ends_at:
            raise ValueError("attempt is outside the planned pilot window")

        state = self.store.load()
        existing = next(
            (item for item in state.active_attempts if item.attempt_id == attempt_id),
            None,
        )
        if existing is not None:
            if existing != active:
                raise ValueError("attempt identity already has different content")
            return state
        if any(item.attempt_id == attempt_id for item in state.attempts):
            raise ValueError("attempt identity is already complete")

        def apply(current: PilotState) -> PilotState:
            if len(current.active_attempts) >= current.plan.maximum_concurrent:
                raise ValueError("pilot maximum concurrency exhausted")
            day = self._day(started_at)
            consumed = sum(
                item.resource_units
                for item in current.attempts
                if item.started_at is not None and self._day(item.started_at) == day
            ) + sum(
                item.resource_units
                for item in current.active_attempts
                if self._day(item.started_at) == day
            )
            if consumed + resource_units > current.plan.daily_resource_limit:
                raise ValueError("pilot daily resource limit exhausted")
            return replace(
                current,
                active_attempts=(*current.active_attempts, active),
                revision=current.revision + 1,
            )

        return self._update(apply)

    def complete_attempt(self, attempt: PilotAttempt) -> PilotState:
        self._validate_attempt_scope(attempt)
        assert attempt.started_at is not None and attempt.ended_at is not None
        ended_at = attempt.ended_at
        state = self.store.load()
        completed = next(
            (item for item in state.attempts if item.attempt_id == attempt.attempt_id),
            None,
        )
        if completed is not None:
            if completed != attempt:
                raise ValueError("attempt identity already has different content")
            return state
        active = next(
            (
                item
                for item in state.active_attempts
                if item.attempt_id == attempt.attempt_id
            ),
            None,
        )
        if active is None:
            raise ValueError("attempt has no durable active lease")
        if (
            active.subject_id != attempt.subject_id
            or active.family_id != attempt.family_id
            or active.candidate_digest != attempt.candidate_digest
            or active.started_at != attempt.started_at
            or active.resource_units != attempt.resource_units
            or active.domain != attempt.domain
        ):
            raise ValueError("completed attempt does not match its active lease")

        def apply(current: PilotState) -> PilotState:
            if (
                attempt.status == "accepted"
                and sum(
                    row.status == "accepted"
                    and row.ended_at is not None
                    and self._day(row.ended_at) == self._day(ended_at)
                    for row in current.attempts
                )
                >= current.plan.delivery_rate_limit
            ):
                raise ValueError("pilot delivery rate limit exhausted")
            return replace(
                current,
                attempts=(*current.attempts, attempt),
                active_attempts=tuple(
                    item
                    for item in current.active_attempts
                    if item.attempt_id != attempt.attempt_id
                ),
                observed_through=max(
                    current.plan.starts_at
                    if current.observed_through is None
                    else current.observed_through,
                    ended_at,
                ),
                revision=current.revision + 1,
            )

        return self._update(apply)

    def record_attempt(self, attempt: PilotAttempt) -> PilotState:
        """Durably begin and complete an observed attempt, safely resumable between steps."""
        self._validate_attempt_scope(attempt)
        assert attempt.started_at is not None
        state = self.store.load()
        existing = next(
            (item for item in state.attempts if item.attempt_id == attempt.attempt_id),
            None,
        )
        if existing is not None:
            if existing != attempt:
                raise ValueError("attempt identity already has different content")
            return state
        self.begin_attempt(
            attempt_id=attempt.attempt_id,
            subject_id=attempt.subject_id,
            family_id=attempt.family_id,
            started_at=attempt.started_at,
            resource_units=attempt.resource_units,
            domain=attempt.domain,
        )
        return self.complete_attempt(attempt)

    def record_controls(
        self,
        *,
        restart_exercised: bool | None = None,
        duplicate_effects: int = 0,
        avoidable_owner_questions: int = 0,
        rollback_evidence: EvidenceRef | None = None,
        restart_evidence: EvidenceRef | None = None,
        obligations: Iterable[ExternalObligation] = (),
    ) -> PilotState:
        if restart_exercised is not None and type(restart_exercised) is not bool:
            raise ValueError("pilot restart flag must be boolean")
        if any(
            type(value) is not int or value < 0
            for value in (duplicate_effects, avoidable_owner_questions)
        ):
            raise ValueError("pilot control counters must be nonnegative integers")
        if rollback_evidence is not None and (
            rollback_evidence.kind is EvidenceKind.SYNTHETIC
            or rollback_evidence.subject_id != self.plan.pilot_id
        ):
            raise ValueError("pilot rollback evidence is not externally bound")
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
            if state.restart_exercised and restart_exercised is False:
                raise ValueError("pilot restart evidence cannot be cleared")
            effective_restart_evidence = restart_evidence or state.restart_evidence
            if restart_exercised is True and effective_restart_evidence is None:
                raise ValueError("pilot restart requires an external evidence receipt")
            if restart_evidence is not None and (
                restart_evidence.kind is EvidenceKind.SYNTHETIC
                or restart_evidence.subject_id != state.plan.pilot_id
            ):
                raise ValueError("pilot restart evidence is not externally bound")
            return replace(
                state,
                restart_exercised=state.restart_exercised
                if restart_exercised is None
                else restart_exercised,
                duplicate_effects=state.duplicate_effects + duplicate_effects,
                avoidable_owner_questions=(
                    state.avoidable_owner_questions + avoidable_owner_questions
                ),
                rollback_evidence=rollback_evidence or state.rollback_evidence,
                restart_evidence=effective_restart_evidence,
                obligations=tuple(reconciled.values()),
                revision=state.revision + 1,
            )

        return self._update(apply)

    def record_observation(
        self, observed_at: int, *, evidence: EvidenceRef | None = None
    ) -> PilotState:
        """Advance the durable observation watermark without fabricating elapsed time."""
        if type(observed_at) is not int:
            raise ValueError("pilot observation timestamp must be an integer")
        if evidence is not None and (
            evidence.kind is EvidenceKind.SYNTHETIC
            or evidence.subject_id != self.plan.pilot_id
            or evidence.observed_at != observed_at
        ):
            raise ValueError("pilot observation evidence is not externally bound")

        def apply(state: PilotState) -> PilotState:
            prior = (
                state.plan.starts_at
                if state.observed_through is None
                else state.observed_through
            )
            if observed_at < prior:
                raise ValueError("pilot observation timestamp cannot move backward")
            return replace(
                state,
                revision=state.revision + 1,
                observed_through=observed_at,
                observation_evidence=evidence or state.observation_evidence,
            )

        return self._update(apply)

    def report(self) -> PilotReport:
        state = self.store.load()
        observed_through = (
            state.plan.starts_at
            if state.observed_through is None
            else state.observed_through
        )
        obligations = {
            item.obligation_id: item for item in state.obligations
        }
        for item in state.plan.prerequisites.blockers(
            state.plan.mode, state.plan.claim_scope, state.plan.subject_ids
        ):
            obligations.setdefault(item.obligation_id, item)
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
            tuple(obligations.values()),
            tuple(item.attempt_id for item in state.active_attempts),
            state.restart_evidence,
            state.observation_evidence,
            state.plan.subject_ids,
            state.plan.claim_scope,
            state.plan.prerequisites.production_candidate,
            state.plan.prerequisites.benchmark_candidate,
        )
