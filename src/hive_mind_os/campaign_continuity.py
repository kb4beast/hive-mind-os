"""Opt-in bounded post-delivery campaign continuity; no production activation.

The supplied adapter must independently observe repository/evidence/owner authority
and implement an idempotent operation-ID namespace. This library has no Git,
network, credential, deployment, promotion or protected-merge implementation.
Hash chains provide corruption detection, not authenticated storage custody.
"""
from __future__ import annotations

import json
import os
import stat
import sys
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
    if type(values) is not tuple or not values or any(type(item) is not EvidenceReference for item in values):
        raise ValueError("retained evidence references are required")
    for item in values:
        item.__post_init__()
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
    maximum_recoveries: int = 4

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
        for value in (self.expires_at, self.maximum_launches, self.maximum_reconciliations,
                      self.observation_max_age, self.maximum_recoveries):
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

    def __post_init__(self) -> None:
        if type(self.subject) is not RepositorySubject:
            raise ValueError("observation requires an exact repository subject")
        self.subject.__post_init__()
        for value in (self.scope_digest, self.authority_digest):
            _sha(value)
        for value in (self.owner_id, self.observer_id):
            _text(value)
        if type(self.observed_at) is not int or self.observed_at < 0 or type(self.launch_allowed) is not bool:
            raise ValueError("observation timestamp and permission require exact types")
        _references(self.verified_evidence)
        if type(self.receipt) is not EvidenceReference:
            raise ValueError("observation receipt is required")
        self.receipt.__post_init__()


@dataclass(frozen=True, slots=True)
class LaunchReceipt:
    operation_id: str
    candidate_digest: str
    status: LaunchStatus
    authoritative: bool
    receipt: EvidenceReference
    detail: str = ""

    def __post_init__(self) -> None:
        _sha(self.operation_id)
        _sha(self.candidate_digest)
        if type(self.status) is not LaunchStatus or type(self.authoritative) is not bool:
            raise ValueError("receipt status and authority require exact types")
        if type(self.receipt) is not EvidenceReference or type(self.detail) is not str:
            raise ValueError("receipt evidence and text detail are required")
        self.receipt.__post_init__()


class CampaignAdapter(Protocol):
    """Host-supplied independent observer and idempotent bounded launcher.

    inspect's authoritative ABSENT asserts this operation produced no side effect.
    UNKNOWN cannot authorize a launch. STARTED identifies exactly the requested
    immutable candidate. launch must deduplicate the operation ID across restarts.
    inspect is read-only and must remain usable after dispatch authority expires.
    The host enforces deadlines/cancellation, authenticates principals and evidence,
    and supplies sanitized exception messages suitable for durable audit storage.
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
        if type(scope) is not ContinuityScope:
            raise ValueError("an exact immutable scope is required")
        scope.__post_init__()
        supplied = Path(root)
        self._supplied_root = supplied if supplied.is_absolute() else Path.cwd() / supplied
        self.root = self._supplied_root
        self._check_root()
        self.root = Path(os.path.abspath(self._supplied_root))
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise ContinuityError("checkpoint-storage", "cannot create state directory") from error
        self.scope = scope
        self.clock = clock
        self.scope_binding = _digest(asdict(scope))
        self._seen: tuple[int, str] | None = None
        with _LOCK_GUARD:
            self._lock = _LOCKS.setdefault(self.root, RLock())
        with self._transaction():
            events = self._events(allow_empty=self._new_lock)
            if not events:
                self._append("initialized", {"scope": asdict(scope)}, {
                    "schema_version": 2, "scope_binding": self.scope_binding,
                    "phase": Phase.WAITING, "delivery": None, "candidates": {},
                    "selected": None, "operation_id": None, "launches": 0,
                    "reconciliations": 0, "recoveries": 0, "outcome_pending": False, "blocker": None,
                })

    def _check_root(self) -> None:
        # Check the supplied absolute path before resolving: junctions count too.
        # These checks prevent accidental aliases, not races by a hostile custodian.
        try:
            for path in (*reversed(self._supplied_root.parents), self._supplied_root):
                try:
                    info = path.lstat()
                except FileNotFoundError:
                    continue
                if self._linked(info) or not stat.S_ISDIR(info.st_mode):
                    raise ContinuityError("unsafe-storage-path", "state directory must not traverse links or reparse points")
        except OSError as error:
            raise ContinuityError("checkpoint-storage", "cannot inspect state directory") from error

    @staticmethod
    def _linked(info: os.stat_result) -> bool:
        return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)

    @classmethod
    def _regular(cls, path: Path) -> os.stat_result:
        info = path.lstat()
        if cls._linked(info) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ContinuityError("unsafe-storage-path", "journal and lock files must be regular unlinked files")
        return info

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock:
            self._check_root()
            path = self.root / ".writer.lock"
            try:
                try:
                    handle = path.open("x+b")
                    self._new_lock = True
                except FileExistsError:
                    before = self._regular(path)
                    handle = path.open("r+b")
                    self._new_lock = False
                    if not os.path.samestat(before, os.fstat(handle.fileno())):
                        handle.close()
                        raise ContinuityError("unsafe-storage-path", "lock identity changed")
            except OSError as error:
                raise ContinuityError("checkpoint-storage", "cannot open writer lock") from error
            with handle:
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or self._linked(info):
                    raise ContinuityError("unsafe-storage-path", "writer lock is linked")
                # Windows permits locking a byte beyond EOF: lock BEFORE initializing.
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
                    try:
                        if info.st_size == 0:
                            handle.write(b"\0")
                            handle.flush()
                            os.fsync(handle.fileno())
                    except OSError as error:
                        raise ContinuityError("checkpoint-storage", "cannot initialize writer lock") from error
                    yield
                finally:
                    active_error = sys.exc_info()[0] is not None
                    try:
                        handle.seek(0)
                        if os.name == "nt":
                            import msvcrt
                            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    except OSError as error:
                        if not active_error:
                            raise ContinuityError("checkpoint-storage", "writer lock release failed") from error

    def _validate_state(self, state: dict[str, Any]) -> None:
        if type(state) is not dict or set(state) != {
            "schema_version", "scope_binding", "phase", "delivery", "candidates", "selected",
            "operation_id", "launches", "reconciliations", "recoveries", "outcome_pending", "blocker",
        }:
            raise ValueError("invalid checkpoint fields")
        if state["scope_binding"] != self.scope_binding:
            raise ContinuityError("scope-changed", "journal does not belong to this controller scope")
        if type(state["schema_version"]) is not int or state["schema_version"] != 2:
            raise ValueError("unsupported checkpoint schema")
        phase = Phase(state["phase"])
        if type(state["outcome_pending"]) is not bool:
            raise ValueError("invalid pending outcome")
        for key, maximum in (("launches", self.scope.maximum_launches),
                             ("reconciliations", self.scope.maximum_reconciliations),
                             ("recoveries", self.scope.maximum_recoveries)):
            if type(state[key]) is not int or not 0 <= state[key] <= maximum:
                raise ValueError("invalid attempt budget")
        if state["blocker"] is not None:
            _text(state["blocker"])
        if phase in {Phase.BLOCKED, Phase.EXHAUSTED} and state["blocker"] is None:
            raise ValueError("terminal refusal requires a blocker")
        delivery = state["delivery"]
        if delivery is not None:
            parsed = CompletedDelivery(**{**delivery, "subject": RepositorySubject(**delivery["subject"]),
                "evidence": tuple(EvidenceReference(**item) for item in delivery["evidence"])})
            if (parsed.delivery_id != self.scope.delivery_id or parsed.subject != self.scope.subject
                    or parsed.scope_digest != self.scope.scope_digest or not parsed.merged
                    or not parsed.required_checks_green or _bytes(asdict(parsed)) != _bytes(delivery)):
                raise ValueError("invalid delivery binding")
        if type(state["candidates"]) is not dict:
            raise ValueError("invalid candidate registry")
        for key, value in state["candidates"].items():
            candidate = self._candidate(value)
            if candidate.candidate_id != key or _bytes(asdict(candidate)) != _bytes(value):
                raise ValueError("invalid candidate record")
        selected = state["selected"]
        if selected is None:
            if (state["operation_id"] is not None or any(state[k] for k in ("launches", "reconciliations", "recoveries"))
                    or state["outcome_pending"] or phase in {Phase.SELECTED, Phase.RECONCILING, Phase.LAUNCHED}):
                raise ValueError("operation missing from checkpoint")
        else:
            _text(selected)
            candidate = self._candidate(state["candidates"][selected])
            if (delivery is None or phase == Phase.WAITING or not self._eligible(candidate)
                    or state["operation_id"] != self._operation(delivery, candidate)):
                raise ValueError("invalid selected operation binding")
        if state["outcome_pending"] and (not state["launches"] or phase == Phase.LAUNCHED):
            raise ValueError("invalid unresolved launch state")
        if ((phase == Phase.SELECTED and any(state[k] for k in ("launches", "reconciliations", "recoveries")))
                or (phase in {Phase.RECONCILING, Phase.LAUNCHED} and not state["reconciliations"])
                or (state["launches"] and not state["reconciliations"])
                or (state["recoveries"] and phase not in _TERMINAL)):
            raise ValueError("phase and attempt counters disagree")

    def _eligible(self, item: CampaignCandidate) -> bool:
        return (item.candidate_id in self.scope.allowed_candidate_ids and item.subject == self.scope.subject
                and item.scope_digest == self.scope.scope_digest and item.authority_digest == self.scope.authority_digest
                and item.reversible and item.disposition in {"adopt", "adapt"})

    def _operation(self, delivery: dict[str, Any], candidate: CampaignCandidate) -> str:
        return _digest({"scope": self.scope_binding, "delivery": delivery, "candidate": asdict(candidate)})

    def _finish_pending_link(self, path: Path) -> None:
        info = path.lstat()
        if stat.S_ISREG(info.st_mode) and not self._linked(info) and info.st_nlink == 2:
            # A crash or cleanup failure may leave BOTH names from publication.
            # Only remove a same-inode pending name inside the private state root.
            for pending in self.root.glob(".pending-*"):
                other = pending.lstat()
                if not self._linked(other) and os.path.samestat(info, other):
                    pending.unlink()
                    break

    def _events(self, *, allow_empty: bool = False) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        prior = None
        try:
            for sequence, path in enumerate(sorted(self.root.glob("event-*.json")), 1):
                self._finish_pending_link(path)
                before = self._regular(path)
                with path.open("rb") as handle:
                    if not os.path.samestat(before, os.fstat(handle.fileno())):
                        raise ValueError("event identity changed")
                    raw = handle.read()
                document = json.loads(raw)
                if type(document) is not dict or set(document) != {
                    "schema_version", "sequence", "previous_digest", "kind", "payload", "checkpoint", "event_digest",
                }:
                    raise ValueError("invalid event fields")
                body = {key: value for key, value in document.items() if key != "event_digest"}
                if (path.name != f"event-{sequence:08d}.json" or type(document["schema_version"]) is not int
                        or document["schema_version"] != 2 or type(document["sequence"]) is not int
                        or document["sequence"] != sequence or document["previous_digest"] != prior
                        or document["event_digest"] != _digest(body) or raw != _bytes(document) + b"\n"
                        or type(document["payload"]) is not dict):
                    raise ValueError("checkpoint chain mismatch")
                _text(document["kind"])
                self._validate_state(document["checkpoint"])
                if sequence == 1 and (document["kind"] != "initialized"
                        or _bytes(document["payload"]) != _bytes({"scope": asdict(self.scope)})):
                    raise ValueError("invalid initialization")
                if events:
                    previous = events[-1]["checkpoint"]
                    current = document["checkpoint"]
                    for key in ("launches", "reconciliations", "recoveries"):
                        if current[key] < previous[key]:
                            raise ValueError("attempt counter regressed")
                    for key in ("delivery", "selected", "operation_id"):
                        if previous[key] is not None and previous[key] != current[key]:
                            raise ValueError("immutable operation changed")
                    if any(current["candidates"].get(k) != v for k, v in previous["candidates"].items()):
                        raise ValueError("retained candidate disappeared")
                prior = document["event_digest"]
                events.append(document)
            if not events and not allow_empty:
                raise ValueError("initialized journal is missing")
            if self._seen is not None:
                count, digest = self._seen
                if len(events) < count or events[count - 1]["event_digest"] != digest:
                    raise ValueError("previously observed journal history changed")
        except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, RecursionError) as error:
            raise ContinuityError("checkpoint-corrupt", "retained checkpoints cannot be safely resumed") from error
        if events:
            self._seen = (len(events), events[-1]["event_digest"])
        return events

    def _append(self, kind: str, payload: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        events = self._events(allow_empty=kind == "initialized" and self._seen is None and self._new_lock)
        self._validate_state(state)
        document = {
            "schema_version": 2, "sequence": len(events) + 1,
            "previous_digest": events[-1]["event_digest"] if events else None,
            "kind": kind, "payload": payload, "checkpoint": state,
        }
        document["event_digest"] = _digest(document)
        destination = self.root / f"event-{len(events) + 1:08d}.json"
        temporary: Path | None = None
        failure: OSError | None = None
        published = False
        try:
            with tempfile.NamedTemporaryFile(dir=self.root, prefix=".pending-", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(_bytes(document) + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
            # Same-filesystem atomic create without overwriting an existing event.
            os.link(temporary, destination)
            published = True
        except OSError as error:
            failure = error
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError as error:
                    if failure is None:
                        failure = error
        if published:
            self._seen = (document["sequence"], document["event_digest"])
        if failure is not None:
            code = "checkpoint-cleanup" if published else "checkpoint-persistence"
            raise ContinuityError(code, "event published; cleanup pending" if published else
                                  "checkpoint publication failed; inspect before resuming") from failure
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
        except Exception as error:
            detail = self._adapter_error(error)
            return self._stop(state, detail.get("code", "observation-unavailable"), evidence=detail), False
        try:
            if type(observed) is not AuthorityObservation:
                raise ValueError("adapter returned no authority observation")
            observed.__post_init__()
            document = asdict(observed)
            _bytes(document)
        except Exception as error:
            return self._stop(state, "observation-malformed", evidence=self._adapter_error(error)), False
        # Storage failures must escape, never be mislabeled as adapter failures.
        state = self._append("authority-observed", document, state)
        try:
            now = self.clock()
            if type(now) not in (int, float) or not 0 <= now < float("inf"):
                raise ValueError("clock must return a finite nonnegative timestamp")
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
            elif observed.observer_id == self.scope.owner_id:
                code = "observer-not-independent"
            elif (not isinstance(observed.receipt, EvidenceReference)
                  or set(observed.verified_evidence) != set(evidence)):
                code = "evidence-mismatch"
            else:
                return state, True
        except Exception as error:
            return self._stop(state, "clock-unavailable", evidence=self._adapter_error(error)), False
        return self._stop(state, code), False

    @staticmethod
    def _adapter_error(error: Exception) -> dict[str, str]:
        detail = {"error": type(error).__name__}
        # Typed adapter messages are contractually sanitized by the host. Generic
        # exception messages may contain secrets, so retain only their class.
        if isinstance(error, ContinuityError):
            try:
                _text(error.code)
                detail.update(code=error.code, message=str(error))
            except (ValueError, TypeError):
                pass
        return detail

    def _unknown(self, state: dict[str, Any], error: Exception, kind: str) -> dict[str, Any]:
        detail = self._adapter_error(error)
        # A typed refusal cannot be retried as ordinary dispatch. It still says
        # nothing about whether an attempted effect exists; recovery stays open.
        if "code" in detail and state["phase"] not in _TERMINAL:
            state = {**state, "phase": Phase.BLOCKED, "blocker": detail["code"]}
        return self._append(kind, detail, state)

    def _receipt(self, state: dict[str, Any], receipt: LaunchReceipt, kind: str) -> dict[str, Any]:
        candidate = state["candidates"][state["selected"]]
        try:
            if type(receipt) is not LaunchReceipt:
                raise ValueError("adapter returned no launch receipt")
            receipt.__post_init__()
            document = asdict(receipt)
            _bytes(document)
        except Exception as error:
            return self._stop(state, "launch-receipt-mismatch", evidence={"receipt": {
                "type": type(receipt).__name__, **self._adapter_error(error),
            }})
        if receipt.operation_id != state["operation_id"] or receipt.candidate_digest != candidate["version_digest"]:
            return self._stop(state, "launch-receipt-mismatch", evidence={"receipt": document})
        updated = state
        if receipt.status == LaunchStatus.DENIED:
            updated = {**state, "phase": Phase.BLOCKED, "blocker": state["blocker"] or "launch-denied"}
        elif receipt.status == LaunchStatus.STARTED and receipt.authoritative:
            updated = {**state, "phase": Phase.LAUNCHED, "outcome_pending": False}
        elif receipt.status == LaunchStatus.ABSENT and receipt.authoritative:
            updated = {**state, "outcome_pending": False}
        return self._append(kind, document, updated)

    def recover(self, adapter: CampaignAdapter) -> dict[str, Any]:
        """Inspect a possible effect even after dispatch has stopped; never launch.

        The immutable scope reserves maximum_recoveries read-only attempts. Each
        intent consumes one before the adapter call, even if interrupted. Exhaustion
        leaves outcome_pending true for explicit handoff to the original adapter;
        this API cannot replenish budgets or restore dispatch authority.
        """
        with self._transaction():
            state = self._events()[-1]["checkpoint"]
            if not state["outcome_pending"]:
                return state
            if state["recoveries"] >= self.scope.maximum_recoveries:
                if self._events()[-1]["kind"] == "recovery-exhausted":
                    return state
                return self._append("recovery-exhausted", {"code": "recovery-budget-exhausted",
                    "handoff_required": True}, {**state, "phase": Phase.EXHAUSTED,
                    "blocker": state["blocker"] or "recovery-budget-exhausted"})
            state = self._append("recovery-intent", {"operation_id": state["operation_id"]}, {
                **state, "phase": Phase.BLOCKED, "blocker": state["blocker"] or "recovery-only",
                "recoveries": state["recoveries"] + 1,
            })
            candidate = self._candidate(state["candidates"][state["selected"]])
            try:
                receipt = adapter.inspect(state["operation_id"], candidate)
            except Exception as error:
                return self._append("recovery-unknown", self._adapter_error(error), state)
            return self._receipt(state, receipt, "recovery-receipt")

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
                eligible = [item for item in choices if self._eligible(item)]
                if not eligible:
                    return self._stop(state, "no-eligible-candidate")
                candidate = sorted(eligible, key=lambda item: (-item.priority, item.candidate_id))[0]
                operation = self._operation(state["delivery"], candidate)
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
                return self._unknown(state, error, "reconciliation-unknown")
            state = self._receipt(state, receipt, "reconciliation-receipt")
            if state["phase"] in _TERMINAL or not receipt.authoritative or receipt.status != LaunchStatus.ABSENT:
                return state
            if state["launches"] >= self.scope.maximum_launches:
                return self._stop(state, "launch-budget-exhausted", exhausted=True)
            state, allowed = self._observe(state, adapter, evidence)
            if not allowed:
                return state
            state = self._append("launch-intent", {"operation_id": state["operation_id"]}, {
                **state, "phase": Phase.RECONCILING, "launches": state["launches"] + 1, "outcome_pending": True,
            })
            try:
                launched = adapter.launch(state["operation_id"], candidate, self.scope)
            except Exception as error:
                return self._unknown(state, error, "launch-outcome-unknown")
            return self._receipt(state, launched, "launch-receipt")
