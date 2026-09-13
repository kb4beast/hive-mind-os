"""UNVERIFIED DRAFT: bounded post-delivery campaign continuity, not activated.

The supplied adapter must independently observe repository/evidence/owner authority
and implement an idempotent operation-ID namespace. This library has no Git,
network, credential, deployment, promotion or protected-merge implementation.
Hash chains provide corruption detection, not authenticated storage custody.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Callable, Iterator, Protocol


def _bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + sha256(_bytes(value)).hexdigest()


def _text(value: str) -> None:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError("an exact nonempty identifier is required")


def _sha(value: str) -> None:
    _text(value)
    if len(value) != 71 or not value.startswith("sha256:") or set(value[7:]) - set("0123456789abcdef"):
        raise ValueError("a full lowercase SHA-256 digest is required")


class ContinuityError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class Phase(StrEnum):
    WAITING = "waiting"
    SELECTED = "selected"
    RECONCILING = "reconciling"
    LAUNCHED = "launched"
    BLOCKED = "blocked"
    EXHAUSTED = "exhausted"


class LaunchStatus(StrEnum):
    ABSENT = "absent"
    STARTED = "started"
    UNKNOWN = "unknown"
    DENIED = "denied"


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    uri: str
    digest: str

    def __post_init__(self) -> None:
        _text(self.uri)
        _sha(self.digest)


@dataclass(frozen=True, slots=True)
class RepositorySubject:
    repository_id: str
    worktree_id: str
    commit: str
    tree: str

    def __post_init__(self) -> None:
        _text(self.repository_id)
        _text(self.worktree_id)
        for value in (self.commit, self.tree):
            if type(value) is not str or len(value) not in (40, 64) or set(value) - set("0123456789abcdef"):
                raise ValueError("subject requires complete lowercase Git object IDs")


def _references(values: tuple[EvidenceReference, ...]) -> None:
    if type(values) is not tuple or not values or any(not isinstance(item, EvidenceReference) for item in values):
        raise ValueError("retained evidence references are required")
    if len(set(values)) != len(values):
        raise ValueError("evidence references must be unique")


@dataclass(frozen=True, slots=True)
class ContinuityScope:
    campaign_id: str
    delivery_id: str
    subject: RepositorySubject
    owner_id: str
    scope_digest: str
    authority_digest: str
    evidence: tuple[EvidenceReference, ...]
    allowed_candidate_ids: tuple[str, ...]
    expires_at: int
    maximum_launches: int = 2
    maximum_reconciliations: int = 4
    observation_max_age: int = 60

    def __post_init__(self) -> None:
        for value in (self.campaign_id, self.delivery_id, self.owner_id):
            _text(value)
        if not isinstance(self.subject, RepositorySubject):
            raise ValueError("an immutable repository subject is required")
        for value in (self.scope_digest, self.authority_digest):
            _sha(value)
        _references(self.evidence)
        if type(self.allowed_candidate_ids) is not tuple or not self.allowed_candidate_ids:
            raise ValueError("an explicit bounded candidate allowlist is required")
        for value in self.allowed_candidate_ids:
            _text(value)
        if len(set(self.allowed_candidate_ids)) != len(self.allowed_candidate_ids):
            raise ValueError("candidate allowlist must be unique")
        for value in (self.expires_at, self.maximum_launches, self.maximum_reconciliations, self.observation_max_age):
            if type(value) is not int or value < 1:
                raise ValueError("expiry and resource bounds must be positive integers")


@dataclass(frozen=True, slots=True)
class CompletedDelivery:
    delivery_id: str
    subject: RepositorySubject
    scope_digest: str
    merged: bool
    required_checks_green: bool
    evidence: tuple[EvidenceReference, ...]

    def __post_init__(self) -> None:
        _text(self.delivery_id)
        _sha(self.scope_digest)
        if not isinstance(self.subject, RepositorySubject):
            raise ValueError("delivery subject is required")
        if type(self.merged) is not bool or type(self.required_checks_green) is not bool:
            raise ValueError("delivery completion flags must be booleans")
        _references(self.evidence)


@dataclass(frozen=True, slots=True)
class CampaignCandidate:
    candidate_id: str
    version_digest: str
    subject: RepositorySubject
    scope_digest: str
    authority_digest: str
    priority: int
    reversible: bool
    disposition: str
    evidence: tuple[EvidenceReference, ...]
    dissent: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.candidate_id)
        for value in (self.version_digest, self.scope_digest, self.authority_digest):
            _sha(value)
        if not isinstance(self.subject, RepositorySubject):
            raise ValueError("candidate subject is required")
        if type(self.priority) is not int or type(self.reversible) is not bool:
            raise ValueError("priority and reversibility require exact types")
        if self.disposition not in {"adopt", "adapt", "defer", "reject", "quarantine"}:
            raise ValueError("candidate disposition is invalid")
        _references(self.evidence)
        if type(self.dissent) is not tuple:
            raise ValueError("dissent must be an immutable tuple")
        for value in self.dissent:
            _text(value)


@dataclass(frozen=True, slots=True)
class AuthorityObservation:
    subject: RepositorySubject
    scope_digest: str
    authority_digest: str
    owner_id: str
    observer_id: str
    observed_at: int
    launch_allowed: bool
    verified_evidence: tuple[EvidenceReference, ...]
    receipt: EvidenceReference


@dataclass(frozen=True, slots=True)
class LaunchReceipt:
    operation_id: str
    candidate_digest: str
    status: LaunchStatus
    authoritative: bool
    receipt: EvidenceReference
    detail: str = ""


class CampaignAdapter(Protocol):
    """Host-supplied independent observer and idempotent bounded launcher.

    inspect's authoritative ABSENT asserts this operation produced no side effect.
    UNKNOWN cannot authorize a launch. STARTED identifies exactly the requested
    immutable candidate. launch must deduplicate the operation ID across restarts.
    """

    def observe(self, scope: ContinuityScope, required_evidence: tuple[EvidenceReference, ...]) -> AuthorityObservation: ...
    def inspect(self, operation_id: str, candidate: CampaignCandidate) -> LaunchReceipt: ...
    def launch(self, operation_id: str, candidate: CampaignCandidate, scope: ContinuityScope) -> LaunchReceipt: ...


_LOCKS: dict[Path, RLock] = {}
_LOCK_GUARD = Lock()
_TERMINAL = {Phase.LAUNCHED, Phase.BLOCKED, Phase.EXHAUSTED}


class CampaignContinuityController:
    """One immutable scope, one completed delivery, at most one campaign launch.

    Every published event also contains a versioned full checkpoint. No separate
    mutable pointer is needed. Intake conflicts and terminal refusals are retained;
    recovery never edits old state or silently expands scope/resource authority.
    """

    def __init__(self, root: str | Path, scope: ContinuityScope, *, clock: Callable[[], float] = time.time) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.scope = scope
        self.clock = clock
        self.scope_binding = _digest(asdict(scope))
        with _LOCK_GUARD:
            self._lock = _LOCKS.setdefault(self.root, RLock())
        with self._transaction():
            events = self._events()
            if not events:
                self._append("initialized", {"scope": asdict(scope)}, {
                    "schema_version": 1, "scope_binding": self.scope_binding,
                    "phase": Phase.WAITING, "delivery": None, "candidates": {},
                    "selected": None, "operation_id": None, "launches": 0,
                    "reconciliations": 0, "blocker": None,
                })
            elif events[0]["checkpoint"]["scope_binding"] != self.scope_binding:
                raise ContinuityError("scope-changed", "existing campaign cannot adopt different owner scope")

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock, (self.root / ".writer.lock").open("a+b") as handle:
            if handle.seek(0, os.SEEK_END) == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise ContinuityError("writer-busy", "another controller owns this checkpoint transaction") from error
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _events(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        prior = None
        binding = None
        try:
            for sequence, path in enumerate(sorted(self.root.glob("event-*.json")), 1):
                raw = path.read_bytes()
                document = json.loads(raw)
                body = {key: value for key, value in document.items() if key != "event_digest"}
                if binding is None:
                    binding = document["checkpoint"]["scope_binding"]
                if (path.name != f"event-{sequence:08d}.json" or document["schema_version"] != 1
                        or document["sequence"] != sequence or document["previous_digest"] != prior
                        or document["event_digest"] != _digest(body) or raw != _bytes(document) + b"\n"
                        or document["checkpoint"]["schema_version"] != 1
                        or document["checkpoint"]["scope_binding"] != binding):
                    raise ValueError("checkpoint chain mismatch")
                prior = document["event_digest"]
                events.append(document)
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise ContinuityError("checkpoint-corrupt", "retained checkpoints cannot be safely resumed") from error
        return events

    def _append(self, kind: str, payload: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        events = self._events()
        document = {
            "schema_version": 1, "sequence": len(events) + 1,
            "previous_digest": events[-1]["event_digest"] if events else None,
            "kind": kind, "payload": payload, "checkpoint": state,
        }
        document["event_digest"] = _digest(document)
        destination = self.root / f"event-{len(events) + 1:08d}.json"
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.root, prefix=".pending-", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(_bytes(document) + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
            # Same-filesystem atomic create without overwriting an existing event.
            os.link(temporary, destination)
        except OSError as error:
            raise ContinuityError("checkpoint-persistence", "checkpoint publication failed; inspect before resuming") from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return state

    def checkpoint(self) -> dict[str, Any]:
        with self._transaction():
            return self._events()[-1]["checkpoint"]

    def events(self) -> tuple[dict[str, Any], ...]:
        with self._transaction():
            return tuple(self._events())

    def _stop(self, state: dict[str, Any], code: str, *, exhausted: bool = False,
              evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        updated = state if state["phase"] in _TERMINAL else {
            **state, "phase": Phase.EXHAUSTED if exhausted else Phase.BLOCKED, "blocker": code,
        }
        return self._append("stopped", {"code": code, "evidence": evidence}, updated)

    def record_delivery(self, delivery: CompletedDelivery) -> dict[str, Any]:
        with self._transaction():
            state = self._events()[-1]["checkpoint"]
            document = json.loads(_bytes(asdict(delivery)))
            if state["delivery"] == document:
                return state
            if state["delivery"] is not None or state["phase"] != Phase.WAITING:
                return self._stop(state, "delivery-conflict", evidence=document)
            if (delivery.delivery_id != self.scope.delivery_id or delivery.subject != self.scope.subject
                    or delivery.scope_digest != self.scope.scope_digest):
                return self._stop(state, "delivery-binding-mismatch", evidence=document)
            if not delivery.merged or not delivery.required_checks_green:
                return self._stop(state, "delivery-incomplete", evidence=document)
            return self._append("delivery-recorded", document, {**state, "delivery": document})

    def record_candidate(self, candidate: CampaignCandidate) -> dict[str, Any]:
        with self._transaction():
            state = self._events()[-1]["checkpoint"]
            document = json.loads(_bytes(asdict(candidate)))
            previous = state["candidates"].get(candidate.candidate_id)
            if previous == document:
                return state
            if previous is not None or state["phase"] != Phase.WAITING:
                return self._stop(state, "candidate-conflict", evidence=document)
            return self._append("candidate-recorded", document, {
                **state, "candidates": {**state["candidates"], candidate.candidate_id: document},
            })

    @staticmethod
    def _candidate(document: dict[str, Any]) -> CampaignCandidate:
        return CampaignCandidate(**{**document, "subject": RepositorySubject(**document["subject"]),
                                    "evidence": tuple(EvidenceReference(**item) for item in document["evidence"]),
                                    "dissent": tuple(document["dissent"])})

    def _observe(self, state: dict[str, Any], adapter: CampaignAdapter,
                 evidence: tuple[EvidenceReference, ...]) -> tuple[dict[str, Any], bool]:
        try:
            observed = adapter.observe(self.scope, evidence)
            if not isinstance(observed, AuthorityObservation):
                raise ValueError("adapter returned no authority observation")
            document = asdict(observed)
            state = self._append("authority-observed", document, state)
            now = int(self.clock())
            if now >= self.scope.expires_at:
                code = "authority-expired"
            elif observed.subject != self.scope.subject:
                code = "subject-changed"
            elif observed.scope_digest != self.scope.scope_digest or observed.owner_id != self.scope.owner_id:
                code = "scope-changed"
            elif observed.authority_digest != self.scope.authority_digest:
                code = "authority-changed"
            elif type(observed.launch_allowed) is not bool or not observed.launch_allowed:
                code = "authority-denied"
            elif (type(observed.observed_at) is not int or observed.observed_at > now
                  or now - observed.observed_at > self.scope.observation_max_age):
                code = "observation-stale"
            elif not observed.observer_id or observed.observer_id == self.scope.owner_id:
                code = "observer-not-independent"
            elif (not isinstance(observed.receipt, EvidenceReference)
                  or set(observed.verified_evidence) != set(evidence)):
                code = "evidence-mismatch"
            else:
                return state, True
            return self._stop(state, code), False
        except ContinuityError:
            raise
        except Exception as error:
            return self._stop(state, "observation-unavailable", evidence={"error": type(error).__name__}), False

    def _receipt(self, state: dict[str, Any], receipt: LaunchReceipt, kind: str) -> dict[str, Any]:
        candidate = state["candidates"][state["selected"]]
        if (not isinstance(receipt, LaunchReceipt) or receipt.operation_id != state["operation_id"]
                or receipt.candidate_digest != candidate["version_digest"]
                or type(receipt.authoritative) is not bool or not isinstance(receipt.receipt, EvidenceReference)
                or not isinstance(receipt.status, LaunchStatus)):
            return self._stop(state, "launch-receipt-mismatch", evidence={"receipt": repr(receipt)})
        updated = state
        if receipt.status == LaunchStatus.DENIED:
            updated = {**state, "phase": Phase.BLOCKED, "blocker": "launch-denied"}
        elif receipt.status == LaunchStatus.STARTED and receipt.authoritative:
            updated = {**state, "phase": Phase.LAUNCHED}
        return self._append(kind, asdict(receipt), updated)

    def step(self, adapter: CampaignAdapter) -> dict[str, Any]:
        """Advance one bounded phase; persist intent before invoking launch.

        Terminal state is durable. No denied authority or unknown side effect is
        retried by resetting counters, changing operation IDs or dropping evidence.
        """
        with self._transaction():
            state = self._events()[-1]["checkpoint"]
            if state["phase"] in _TERMINAL or state["delivery"] is None:
                return state
            selected = state["selected"]
            evidence = (*self.scope.evidence, *(EvidenceReference(**item) for item in state["delivery"]["evidence"]))
            if selected:
                evidence += self._candidate(state["candidates"][selected]).evidence
            evidence = tuple(dict.fromkeys(evidence))
            state, allowed = self._observe(state, adapter, evidence)
            if not allowed:
                return state
            if state["phase"] == Phase.WAITING:
                choices = [self._candidate(item) for item in state["candidates"].values()]
                eligible = [item for item in choices if item.candidate_id in self.scope.allowed_candidate_ids
                            and item.subject == self.scope.subject and item.scope_digest == self.scope.scope_digest
                            and item.authority_digest == self.scope.authority_digest and item.reversible
                            and item.disposition in {"adopt", "adapt"}]
                if not eligible:
                    return self._stop(state, "no-eligible-candidate")
                candidate = sorted(eligible, key=lambda item: (-item.priority, item.candidate_id))[0]
                operation = _digest({"scope": self.scope_binding, "delivery": state["delivery"],
                                     "candidate": asdict(candidate)})
                return self._append("candidate-selected", {
                    "selected": candidate.candidate_id,
                    "dispositions": [{"candidate_id": item.candidate_id,
                                      "source_disposition": item.disposition,
                                      "eligible": item in eligible, "dissent": list(item.dissent)}
                                     for item in sorted(choices, key=lambda value: value.candidate_id)],
                    "eligible": sorted(item.candidate_id for item in eligible),
                    "not_selected": sorted(item.candidate_id for item in choices if item != candidate),
                }, {**state, "phase": Phase.SELECTED, "selected": candidate.candidate_id, "operation_id": operation})
            candidate = self._candidate(state["candidates"][state["selected"]])
            if state["reconciliations"] >= self.scope.maximum_reconciliations:
                return self._stop(state, "reconciliation-budget-exhausted", exhausted=True)
            state = self._append("reconciliation-intent", {}, {
                **state, "phase": Phase.RECONCILING, "reconciliations": state["reconciliations"] + 1,
            })
            try:
                receipt = adapter.inspect(state["operation_id"], candidate)
            except Exception as error:
                return self._append("reconciliation-unknown", {"error": type(error).__name__}, state)
            state = self._receipt(state, receipt, "reconciliation-receipt")
            if state["phase"] in _TERMINAL or not receipt.authoritative or receipt.status != LaunchStatus.ABSENT:
                return state
            if state["launches"] >= self.scope.maximum_launches:
                return self._stop(state, "launch-budget-exhausted", exhausted=True)
            state, allowed = self._observe(state, adapter, evidence)
            if not allowed:
                return state
            state = self._append("launch-intent", {"operation_id": state["operation_id"]}, {
                **state, "phase": Phase.RECONCILING, "launches": state["launches"] + 1,
            })
            try:
                launched = adapter.launch(state["operation_id"], candidate, self.scope)
            except Exception as error:
                return self._append("launch-outcome-unknown", {"error": type(error).__name__}, state)
            return self._receipt(state, launched, "launch-receipt")
