"""Intent-aware, host-neutral orchestration contracts for Autopilot DAGs.

The deterministic controller owns repository truth.  This module translates that
truth into an executable host contract without pretending that a repository process
can directly control every supported chat/task host.  Host adapters consume the
contract and persist their task identifiers outside repository source files.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

from sidecar_execution import plan_sidecars, validate_sidecar_policy

INTENTS = ("BUILD_DAG", "START", "CONTINUE", "CHECK", "FINISH")
ACTIVE_STATES = {"CLAIMED", "RUNNING", "WAITING_FOR_RECEIPT", "PR_OPEN"}
RECOVERY_STATES = {
    "CI_FAILED",
    "REPAIR_REQUIRED",
    "RECONCILIATION_REQUIRED",
    "REPLAN_REQUIRED",
}
TERMINAL_STATES = {"COMPLETE", "SUPERSEDED", "CANCELLED", "QUARANTINED"}
SUCCESS_STATES = {"COMPLETE", "SUPERSEDED"}
BLOCKING_STATES = {
    "BLOCKED",
    "BOOTSTRAP_INVALID",
    "CANCELLED",
    "ESCALATION_REQUIRED",
    "QUARANTINED",
}
ACTIVE_BINDING_STATES = {
    "PREPARED",
    "CREATED",
    "BOUND",
    "HOST_EVENT_OBSERVED",
    "ATTENTION_ACKNOWLEDGED",
}
READY_STATES = {"READY", "INTEGRATION_READY", "PROMOTION_READY"}
SECRET_TEXT = re.compile(
    r"(?i)(?:\b(?:api[_ -]?key|access[_ -]?token|client[_ -]?secret|password)\b\s*[:=]\s*\S+|"
    r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}|\b(?:gh[oprsu]_|sk-)[A-Za-z0-9_-]{12,})"
)


class OrchestrationError(RuntimeError):
    """The orchestration contract cannot be produced safely."""


def _canonical(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _is_link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(callable(is_junction) and is_junction())


def _managed_path(repo_root: Path, *parts: str) -> Path:
    root = repo_root.resolve()
    current = root
    for part in parts:
        current = current / part
        if _is_link_like(current):
            raise OrchestrationError(
                f"task binding path uses a symlink or junction: {current}"
            )
        if current.exists() and not current.resolve().is_relative_to(root):
            raise OrchestrationError(f"task binding path escapes the repository: {current}")
    return current


def _binding_path(repo_root: Path) -> Path:
    return _managed_path(repo_root, ".autopilot", "state", "task-bindings.jsonl")


def singleton_target_branch(repo_root: Path) -> str:
    """Return the only live execution target from the trusted control plane."""

    path = _managed_path(repo_root, ".autopilot", "control-plane.json")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise OrchestrationError(f"cannot read singleton control plane: {error}") from error
    if not isinstance(value, Mapping) or not isinstance(value.get("target"), Mapping):
        raise OrchestrationError("control-plane target must be an object")
    target = value["target"]
    branch = target.get("branch")
    final = target.get("final_integration_branch")
    if target.get("execution_mode") != "singleton-release-branch":
        raise OrchestrationError("control plane must use singleton-release-branch execution")
    if not isinstance(branch, str) or not branch.strip():
        raise OrchestrationError("singleton target branch is required")
    if not isinstance(final, str) or not final.strip():
        raise OrchestrationError("final integration branch is required")
    protected = target.get("protected_until_final_integration")
    if branch == final or branch == "main" or not isinstance(protected, list) or final not in protected:
        raise OrchestrationError("singleton execution target must not be main or the protected final branch")
    return branch


@contextmanager
def _binding_lock(repo_root: Path):
    path = _managed_path(repo_root, ".autopilot", "task-bindings.lock")
    if not path.is_file() or _is_link_like(path):
        raise OrchestrationError("required task binding lock file is missing")
    deadline = time.monotonic() + 10.0
    descriptor = os.open(path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
    locked = False
    while not locked:
        try:
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                if os.fstat(descriptor).st_size == 0:
                    os.write(descriptor, b"0")
                    os.fsync(descriptor)
                    os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError:
            if time.monotonic() >= deadline:
                os.close(descriptor)
                raise OrchestrationError(
                    "task binding ledger is locked; recover the owning host operation before retrying"
                )
            time.sleep(0.01)
    try:
        yield
    finally:
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _binding_events_unlocked(repo_root: Path) -> tuple[Mapping[str, object], ...]:
    path = _binding_path(repo_root)
    if not path.exists():
        return ()
    events: list[Mapping[str, object]] = []
    previous: str | None = None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise OrchestrationError(f"cannot read task binding ledger: {error}") from error
    for index, line in enumerate(lines, start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise OrchestrationError(f"task binding ledger line {index} is invalid") from error
        if not isinstance(event, Mapping):
            raise OrchestrationError(f"task binding ledger line {index} must be an object")
        material = dict(event)
        event_id = material.pop("event_id", None)
        if material.get("previous_event_id") != previous:
            raise OrchestrationError(f"task binding ledger line {index} breaks the hash chain")
        expected = "sha256:" + sha256(_canonical(material)).hexdigest()
        if event_id != expected:
            raise OrchestrationError(f"task binding ledger line {index} has an invalid digest")
        previous = str(event_id)
        events.append(event)
    return tuple(events)


def binding_events(repo_root: Path) -> tuple[Mapping[str, object], ...]:
    with _binding_lock(repo_root):
        return _binding_events_unlocked(repo_root)


def _append_binding_event_unlocked(
    repo_root: Path,
    value: Mapping[str, object],
    events: Sequence[Mapping[str, object]],
) -> Mapping[str, object]:
    material = {
        "schema_version": 1,
        **dict(value),
        "previous_event_id": events[-1]["event_id"] if events else None,
        "recorded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    event = {**material, "event_id": "sha256:" + sha256(_canonical(material)).hexdigest()}
    path = _binding_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path = _binding_path(repo_root)
    encoded = json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return event


def launch_binding(repo_root: Path, instruction_id: str) -> Mapping[str, object] | None:
    latest: Mapping[str, object] | None = None
    for event in binding_events(repo_root):
        if event.get("launch_instruction_id") == instruction_id:
            latest = event
    return latest


def active_launch_bindings(repo_root: Path) -> tuple[Mapping[str, object], ...]:
    latest: dict[str, Mapping[str, object]] = {}
    for event in binding_events(repo_root):
        instruction_id = event.get("launch_instruction_id")
        if isinstance(instruction_id, str):
            latest[instruction_id] = event
    return tuple(
        latest[key]
        for key in sorted(latest)
        if latest[key].get("state") in ACTIVE_BINDING_STATES
    )


def _capability_digest(capability: str) -> str:
    if not isinstance(capability, str) or not capability.strip():
        raise OrchestrationError("host task capability is required")
    return "sha256:" + sha256(capability.encode("utf-8")).hexdigest()


def _same_capability(event: Mapping[str, object], capability: str) -> bool:
    expected = event.get("capability_digest")
    return isinstance(expected, str) and hmac.compare_digest(expected, _capability_digest(capability))


def prepare_launch(
    repo_root: Path,
    instruction_id: str,
    host: str,
    *,
    attempt: int = 1,
    retry_of: str | None = None,
) -> Mapping[str, object]:
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", instruction_id):
        raise OrchestrationError("launch instruction id must be a SHA-256 digest")
    if not host.strip():
        raise OrchestrationError("launch host is required")
    if type(attempt) is not int or attempt < 1:
        raise OrchestrationError("launch attempt must be a positive integer")
    with _binding_lock(repo_root):
        events = _binding_events_unlocked(repo_root)
        existing = next(
            (event for event in reversed(events) if event.get("launch_instruction_id") == instruction_id),
            None,
        )
        if existing is not None and existing.get("state") != "RELEASED":
            if (
                existing.get("host") != host
                or existing.get("attempt") != attempt
                or existing.get("retry_of") != retry_of
            ):
                raise OrchestrationError("prepared launch identity or retry lineage changed")
            return existing
        if existing is not None:
            if existing.get("terminal_state") == "SUCCEEDED":
                return existing
            raise OrchestrationError(
                "an unsuccessful released launch requires a new instruction id and explicit retry lineage"
            )
        if retry_of is not None:
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", retry_of):
                raise OrchestrationError("retry lineage must name a released event digest")
            prior = next((event for event in events if event.get("event_id") == retry_of), None)
            if (
                prior is None
                or prior.get("state") != "RELEASED"
                or prior.get("terminal_state") not in {"FAILED", "CANCELLED"}
                or prior.get("launch_instruction_id") == instruction_id
            ):
                raise OrchestrationError(
                    "retry lineage must name a failed or cancelled release for another instruction"
                )
            prior_attempt = prior.get("attempt")
            if type(prior_attempt) is not int or prior_attempt < 1:
                raise OrchestrationError("retry lineage has an invalid prior attempt")
            expected_attempt = prior_attempt + 1
            if attempt != expected_attempt:
                raise OrchestrationError("launch attempt does not match retry lineage")
        elif attempt != 1:
            raise OrchestrationError("a retry attempt requires explicit retry lineage")
        return _append_binding_event_unlocked(
            repo_root,
            {
                "kind": "hive-mind-task-binding-event-v1",
                "launch_instruction_id": instruction_id,
                "host": host,
                "attempt": attempt,
                "retry_of": retry_of,
                "state": "PREPARED",
            },
            events,
        )


def bind_launch(
    repo_root: Path,
    instruction_id: str,
    host: str,
    task_id: str,
    *,
    host_id: str | None = None,
    cursor: str | None = None,
    capability: str,
) -> Mapping[str, object]:
    capability_digest = _capability_digest(capability)
    with _binding_lock(repo_root):
        events = list(_binding_events_unlocked(repo_root))
        existing = next(
            (event for event in reversed(events) if event.get("launch_instruction_id") == instruction_id),
            None,
        )
        if existing is None or existing.get("state") not in ACTIVE_BINDING_STATES:
            raise OrchestrationError("prepare the launch before binding a host task")
        if existing.get("host") != host:
            raise OrchestrationError("prepared launch host cannot be rebound by another host")
        if existing.get("state") in {"BOUND", "HOST_EVENT_OBSERVED", "ATTENTION_ACKNOWLEDGED"}:
            if (
                existing.get("task_id") != task_id
                or existing.get("host") != host
                or existing.get("host_id") != host_id
                or existing.get("cursor") != cursor
                or not _same_capability(existing, capability)
            ):
                raise OrchestrationError("launch instruction is already bound to another task")
            return existing
        if existing.get("state") == "CREATED" and (
            existing.get("task_id") != task_id
            or existing.get("host_id") != host_id
            or existing.get("cursor") != cursor
            or not _same_capability(existing, capability)
        ):
            raise OrchestrationError("created launch cannot adopt a different host task")
        if not host.strip() or not task_id.strip():
            raise OrchestrationError("host and task id are required")
        if existing.get("state") == "PREPARED":
            created = _append_binding_event_unlocked(
                repo_root,
                {
                    "kind": "hive-mind-task-binding-event-v1",
                    "launch_instruction_id": instruction_id,
                    "host": host,
                    "host_id": host_id,
                    "task_id": task_id,
                    "cursor": cursor,
                    "capability_digest": capability_digest,
                    "attempt": existing.get("attempt", 1),
                    "retry_of": existing.get("retry_of"),
                    "state": "CREATED",
                },
                events,
            )
            events.append(created)
        return _append_binding_event_unlocked(
            repo_root,
            {
                "kind": "hive-mind-task-binding-event-v1",
                "launch_instruction_id": instruction_id,
                "host": host,
                "host_id": host_id,
                "task_id": task_id,
                "cursor": cursor,
                "capability_digest": capability_digest,
                "attempt": existing.get("attempt", 1),
                "retry_of": existing.get("retry_of"),
                "state": "BOUND",
            },
            events,
        )


def record_host_progress(
    repo_root: Path,
    instruction_id: str,
    *,
    host: str,
    host_id: str,
    task_id: str,
    cursor: str,
    capability: str,
    host_state: str,
    host_event_id: str,
    host_event_cursor: str,
    message_id: str | None = None,
) -> Mapping[str, object]:
    if host_state not in {"ACTIVE", "NEEDS_ATTENTION"}:
        raise OrchestrationError("progress state must be ACTIVE or NEEDS_ATTENTION")
    if not host_event_id.strip() or not host_event_cursor.strip():
        raise OrchestrationError("host event id and cursor are required")
    if host_state == "NEEDS_ATTENTION" and (not isinstance(message_id, str) or not message_id.strip()):
        raise OrchestrationError("attention recovery requires an acknowledged message id")
    with _binding_lock(repo_root):
        events = list(_binding_events_unlocked(repo_root))
        existing = next(
            (event for event in reversed(events) if event.get("launch_instruction_id") == instruction_id),
            None,
        )
        if existing is None or existing.get("state") not in ACTIVE_BINDING_STATES - {"PREPARED", "CREATED"}:
            raise OrchestrationError("only a capability-bound launch can record host progress")
        expected = {
            "host": host,
            "host_id": host_id,
            "task_id": task_id,
            "cursor": cursor,
        }
        if any(existing.get(key) != value for key, value in expected.items()) or not _same_capability(existing, capability):
            raise OrchestrationError("host progress does not match the capability-bound task")
        prior = next(
            (
                event
                for event in reversed(events)
                if event.get("launch_instruction_id") == instruction_id
                and (
                    event.get("host_event_id") == host_event_id
                    or event.get("host_event_cursor") == host_event_cursor
                )
            ),
            None,
        )
        if prior is not None:
            if (
                prior.get("host_event_id") == host_event_id
                and prior.get("host_event_cursor") == host_event_cursor
                and prior.get("host_state") == host_state
                and prior.get("message_id") == message_id
            ):
                return prior
            raise OrchestrationError("host event id or cursor replayed with different evidence")
        return _append_binding_event_unlocked(
            repo_root,
            {
                "kind": "hive-mind-task-binding-event-v1",
                "launch_instruction_id": instruction_id,
                **expected,
                "capability_digest": existing.get("capability_digest"),
                "host_state": host_state,
                "host_event_id": host_event_id,
                "host_event_cursor": host_event_cursor,
                "message_id": message_id,
                "attempt": existing.get("attempt", 1),
                "retry_of": existing.get("retry_of"),
                "state": (
                    "ATTENTION_ACKNOWLEDGED"
                    if host_state == "NEEDS_ATTENTION"
                    else "HOST_EVENT_OBSERVED"
                ),
            },
            events,
        )


def release_terminal_launch(
    repo_root: Path,
    instruction_id: str,
    *,
    host: str,
    host_id: str,
    task_id: str,
    cursor: str,
    capability: str,
    terminal_state: str,
    host_event_id: str,
    host_event_cursor: str,
) -> Mapping[str, object]:
    if terminal_state not in {"SUCCEEDED", "FAILED", "CANCELLED"}:
        raise OrchestrationError("host terminal state must be SUCCEEDED, FAILED, or CANCELLED")
    if not host_event_id.strip() or not host_event_cursor.strip():
        raise OrchestrationError("host terminal event id and cursor are required")
    with _binding_lock(repo_root):
        events = _binding_events_unlocked(repo_root)
        existing = next(
            (event for event in reversed(events) if event.get("launch_instruction_id") == instruction_id),
            None,
        )
        expected = {"host": host, "host_id": host_id, "task_id": task_id, "cursor": cursor}
        if existing is not None and existing.get("state") == "RELEASED":
            if (
                all(existing.get(key) == value for key, value in expected.items())
                and existing.get("terminal_state") == terminal_state
                and existing.get("host_event_id") == host_event_id
                and existing.get("host_event_cursor") == host_event_cursor
                and _same_capability(existing, capability)
            ):
                return existing
            raise OrchestrationError("released launch cannot be replaced by different terminal evidence")
        if existing is None or existing.get("state") not in ACTIVE_BINDING_STATES - {"PREPARED", "CREATED"}:
            raise OrchestrationError("only a capability-bound launch can record terminal evidence")
        if any(existing.get(key) != value for key, value in expected.items()) or not _same_capability(existing, capability):
            raise OrchestrationError("terminal event does not match the capability-bound task")
        if any(
            event.get("host_event_id") == host_event_id
            or event.get("host_event_cursor") == host_event_cursor
            for event in events
            if event.get("launch_instruction_id") == instruction_id
        ):
            raise OrchestrationError("terminal host event replays previously observed evidence")
        return _append_binding_event_unlocked(
            repo_root,
            {
                "kind": "hive-mind-task-binding-event-v1",
                "launch_instruction_id": instruction_id,
                **expected,
                "capability_digest": existing.get("capability_digest"),
                "terminal_state": terminal_state,
                "host_event_id": host_event_id,
                "host_event_cursor": host_event_cursor,
                "observed_by": f"host-execution:{host}",
                "reason": "capability-authenticated host terminal event",
                "attempt": existing.get("attempt", 1),
                "retry_of": existing.get("retry_of"),
                "state": "RELEASED",
            },
            events,
        )


@dataclass(frozen=True, slots=True)
class IntentDecision:
    intent: str
    confidence: str
    explicit: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "explicit": self.explicit,
            "reasons": list(self.reasons),
        }


def _words(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.casefold()))


def _requests_read_only(value: str) -> bool:
    text = re.sub(r'"[^"]*"|“[^”]*”', " ", value).casefold()
    action = r"(?:start(?:ing)?|run(?:ning)?|execute|continue|resume|finish|complete|build|create|generate|launch|kick\s+off|modif(?:y|ies|ied|ying)|chang(?:e|es|ed|ing)|writ(?:e|es|ing)|apply|dispatch)"
    if re.search(r"\b(?:do\s+nothing|don['’]?t\s+do\s+anything|dont\s+do\s+anything|no\s+changes?)\b", text):
        return True
    if re.search(rf"\b(?:do\s+not|don['’]?t|dont|never)\s+(?:\w+\s+){{0,3}}{action}\b", text):
        return True
    if re.search(r"\b(?:only|just)\s+(?:check|inspect|report|summari[sz]e|explain|review)\b", text):
        return True
    if re.search(r"\b(?:explain|describe|summari[sz]e|tell\s+me|show\s+me)\s+(?:how|why|what|when|where|whether)\b", text):
        return True
    if re.search(r"\b(?:review|audit|analy[sz]e|discuss)\s+(?:how|why|what|when|where|whether)\b", text):
        return True
    if re.search(r"\bhow\s+(?:can|could|would|should|do|does|did)\s+(?:i|we|you|this|it|the\s+dag)\b", text):
        return True
    if re.search(r"\b(?:check|inspect|report|summari[sz]e|explain|review)\s+only\b", text):
        return True
    if re.search(r"\bshould\s+(?:i|we|you)\b", text):
        return True
    if re.search(r"\b(?:is|would)\s+it\b.*\b(?:start|finish|continue|run|execute)\b", text):
        return True
    if re.search(r"\b(?:can|could)\s+(?:this|it|the\s+dag)\b", text):
        return True
    return any(
        phrase in text
        for phrase in (
            "read only",
            "read-only",
            "explain the",
            "summarize the",
            "what would you do",
            "what should we do",
            "how would you",
            "how do i",
            "how do we",
            "why did",
            "why didn",
        )
    )


def _node_rows(status: Mapping[str, object]) -> list[Mapping[str, object]]:
    rows = status.get("nodes", [])
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, Mapping)]


def infer_intent(request: str, status: Mapping[str, object] | None) -> IntentDecision:
    """Infer operator intent from ordinary language and current controller truth.

    Explicit action language wins.  Otherwise the current state supplies the least
    surprising safe action: resume active/recovery work, start released/eligible work,
    build when no plan is installed, and inspect a completed graph.
    """

    if SECRET_TEXT.search(request):
        raise OrchestrationError(
            "operator request appears to contain a credential; remove it and use the host secret store"
        )
    text = request.strip()
    # Quoted examples and documentation excerpts are context, not authority.
    actionable = re.sub(r'"[^"]*"|“[^”]*”', " ", text)
    if _requests_read_only(actionable):
        return IntentDecision(
            "CHECK",
            "high",
            True,
            ("explicit non-execution language overrides action words",),
        )
    text = actionable
    words = _words(text)
    normalized = " ".join(re.findall(r"[a-z0-9]+", text.casefold()))

    def explicit(intent: str, reason: str) -> IntentDecision:
        return IntentDecision(intent, "high", True, (reason,))

    if words & {"finish", "complete", "quiescence", "quiescent"} or any(
        phrase in normalized
        for phrase in ("end to end", "until done", "do not stop", "all the way")
    ):
        return explicit("FINISH", "completion language requests execution to quiescence")
    if words & {"continue", "resume", "recover"} or any(
        phrase in normalized for phrase in ("pick up", "keep going", "carry on")
    ):
        return explicit("CONTINUE", "continuation language requests recovery of existing work")
    if words & {"check", "status", "inspect", "progress", "report"} or any(
        phrase in normalized for phrase in ("where are we", "what is left", "whats left")
    ):
        return explicit("CHECK", "inspection language requests a read-only controller view")
    if words & {"start", "begin", "kickoff", "launch", "execute", "run"} or any(
        phrase in normalized for phrase in ("kick off", "start now")
    ):
        return explicit("START", "execution language requests the next released wave")
    if (
        words & {"build", "create", "generate", "design", "plan"}
        and words & {"dag", "autopilot", "plan", "graph", "hivemind", "workflow"}
    ):
        return explicit("BUILD_DAG", "planning language requests an Autopilot DAG")

    if status is None:
        return IntentDecision(
            "BUILD_DAG",
            "medium",
            False,
            ("no installed Autopilot plan exists, so the reusable workflow begins with DAG construction",),
        )

    rows = _node_rows(status)
    states = {str(row.get("state", "")) for row in rows}
    if states & (ACTIVE_STATES | RECOVERY_STATES):
        return IntentDecision(
            "CONTINUE",
            "medium",
            False,
            ("live DAG state contains active or recoverable work",),
        )
    release = status.get("dispatch_release")
    released = []
    if isinstance(release, Mapping) and release.get("valid") is True:
        raw = release.get("released_wave", [])
        if isinstance(raw, list):
            released = [str(item) for item in raw]
    eligible = status.get("eligible", status.get("ready", []))
    if released or (isinstance(eligible, list) and eligible):
        return IntentDecision(
            "START",
            "medium",
            False,
            ("live DAG state contains released or dependency-eligible work",),
        )
    if status.get("complete") is True:
        return IntentDecision(
            "CHECK",
            "medium",
            False,
            ("the installed DAG reports terminal completion, so inspection is safest",),
        )
    return IntentDecision(
        "CONTINUE",
        "low",
        False,
        ("an installed non-terminal DAG exists and no contradictory intent was expressed",),
    )


def load_policy(repo_root: Path) -> Mapping[str, Any]:
    path = repo_root / ".autopilot" / "orchestration-policy.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise OrchestrationError(f"cannot read orchestration policy: {error}") from error
    issues = validate_policy(value)
    if issues:
        raise OrchestrationError("invalid orchestration policy: " + "; ".join(issues))
    assert isinstance(value, Mapping)
    return value


def validate_policy(value: object) -> tuple[str, ...]:
    if not isinstance(value, Mapping):
        return ("policy must be an object",)
    issues: list[str] = []
    issues.extend(validate_sidecar_policy(value.get("sidecars")))
    if value.get("schema_version") != 1:
        issues.append("schema_version must be 1")
    if value.get("kind") != "hive-mind-autopilot-orchestration-policy-v1":
        issues.append("kind is invalid")
    transport = value.get("task_transport")
    if not isinstance(transport, Mapping):
        issues.append("task_transport must be an object")
    else:
        if transport.get("primary") != "durable_user_owned_task":
            issues.append("primary task transport must be durable_user_owned_task")
        if transport.get("nested_primary_forbidden") is not True:
            issues.append("nested primary tasks must be forbidden")
    polling = value.get("polling")
    if not isinstance(polling, Mapping):
        issues.append("polling must be an object")
    else:
        minimum = polling.get("minimum_primary_completions_before_parent_yield")
        if type(minimum) is not int or minimum < 1:
            issues.append("polling must require at least one primary completion")
        if polling.get("parent_final_while_required_tasks_active") is not False:
            issues.append("parent final must be forbidden while required tasks are active")
        for key in ("poll_until_terminal", "answer_questions_then_resume"):
            if polling.get(key) is not True:
                issues.append(f"polling.{key} must be true")
    closure = value.get("closure_first")
    if not isinstance(closure, Mapping) or closure.get("enabled") is not True:
        issues.append("closure_first.enabled must be true")
    elif type(closure.get("before_optional_audits")) is not int or closure.get("before_optional_audits", 0) < 1:
        issues.append("closure_first must require completion before optional audits")
    recovery = value.get("recovery")
    if not isinstance(recovery, Mapping):
        issues.append("recovery must be an object")
    else:
        if recovery.get("blocker_is_completion") is not False:
            issues.append("a blocker must not count as completion")
        for key in (
            "consult_roles_before_human",
            "record_resolved_questions",
            "resume_same_task_after_fix",
        ):
            if recovery.get(key) is not True:
                issues.append(f"recovery.{key} must be true")
    wave = value.get("wave")
    if not isinstance(wave, Mapping):
        issues.append("wave must be an object")
    else:
        if wave.get("mode") != "deterministic_priority_ordered_maximal_conflict_free":
            issues.append("wave mode must be deterministic priority-ordered maximal conflict-free")
        if wave.get("never_start_next_level_before_required_current_cohort_quiescence") is not True:
            issues.append("wave must wait for current cohort quiescence")
    cohort = value.get("parallel_task_cohort")
    if not isinstance(cohort, Mapping):
        issues.append("parallel_task_cohort must be an object")
    else:
        for key in (
            "create_released_tasks_even_when_recovery_tasks_exist",
            "create_eligible_preparation_tasks",
            "create_entire_cohort_before_first_wait",
            "poll_every_created_task_to_terminal",
            "closure_target_prioritizes_collection_not_creation",
        ):
            if cohort.get(key) is not True:
                issues.append(f"parallel_task_cohort.{key} must be true")
        if cohort.get("preparation_authority") != "read_only_until_start_now":
            issues.append("parallel preparation authority must be read_only_until_start_now")
        if cohort.get("title_fields") != [
            "node_id", "action", "authority_mode", "instruction_digest"
        ]:
            issues.append("parallel task titles must be unambiguous")
    if isinstance(transport, Mapping):
        for key in ("record_host_id", "record_task_id", "resume_by_node_identity"):
            if transport.get(key) is not True:
                issues.append(f"task_transport.{key} must be true")
        if transport.get("binding_ledger") != ".autopilot/state/task-bindings.jsonl":
            issues.append("task binding ledger path is invalid")
        if transport.get("binding_sequence") != [
            "PREPARED",
            "CREATED",
            "BOUND",
            "TERMINAL_OBSERVED",
            "RELEASED",
        ]:
            issues.append("task binding sequence is invalid")
    adapters = value.get("host_adapters")
    codex = adapters.get("codex") if isinstance(adapters, Mapping) else None
    if not isinstance(codex, Mapping):
        issues.append("Codex host adapter is required")
    else:
        expected = {
            "create": "create_thread",
            "wait": "wait_threads",
            "message": "send_message_to_thread",
            "nested_sidecar": "multi_agent_v1.spawn_agent",
            "sidecar_close": "multi_agent_v1.close_agent",
            "sidecar_lookup": "lookup_sidecar",
            "sidecar_message": "multi_agent_v1.send_input",
            "sidecar_wait": "wait_activity",
        }
        for key, expected_value in expected.items():
            if codex.get(key) != expected_value:
                issues.append(f"Codex adapter {key} must be {expected_value}")
    executor = value.get("host_executor")
    if not isinstance(executor, Mapping):
        issues.append("host_executor is required")
    else:
        if executor.get("module") != ".autopilot/bin/host_execution.py":
            issues.append("host executor module is invalid")
        if executor.get("entrypoint") != "execute_contract":
            issues.append("host executor entrypoint is invalid")
        for key in (
            "capability_bound_events",
            "create_entire_wave_before_wait",
            "bounded_no_progress_blocker",
        ):
            if executor.get(key) is not True:
                issues.append(f"host_executor.{key} must be true")
    return tuple(dict.fromkeys(issues))


def should_publish_release(
    decision: IntentDecision,
    status: Mapping[str, object],
) -> bool:
    if decision.intent not in {"START", "CONTINUE", "FINISH"}:
        return False
    if status.get("reconciliation_required") is True:
        return False
    states = {str(row.get("state", "")) for row in _node_rows(status)}
    if states & (ACTIVE_STATES | RECOVERY_STATES):
        return False
    release = status.get("dispatch_release")
    if isinstance(release, Mapping) and release.get("valid") is True:
        return False
    eligible = status.get("eligible", [])
    return isinstance(eligible, list) and bool(eligible)


def _node_map(plane: Any) -> dict[str, Mapping[str, Any]]:
    return {str(node.get("id")): node for node in plane.nodes()}


def _task_prompt(plane: Any, node_id: str, action: str, authority_mode: str) -> str:
    base = plane.render_worker_prompt(node_id)
    return (
        "Read .autopilot/orchestration-policy.json and obey its durable-task, "
        "closure-first, polling, recovery, and quiescence contract.\n"
        f"Primary task action: {action}. Authority mode: {authority_mode}. "
        "PREPARATION_ONLY may inspect, diagnose, and prepare an exact handoff but may "
        "not claim, write, commit, push, or publish completion until START NOW. "
        f"Reuse existing work for {node_id}; do not "
        "duplicate a valid claim, branch, candidate, receipt, or PR. A blocker is not "
        "completion: record it, recover within authority, and resume.\n\n"
        + base
    )


def _task(
    plane: Any,
    policy: Mapping[str, Any],
    node: Mapping[str, Any],
    row: Mapping[str, object],
    *,
    action: str,
    required: bool = True,
    authority_mode: str = "RECOVERY_AUTHORIZED",
) -> dict[str, object]:
    node_id = str(node.get("id"))
    adapters = policy.get("host_adapters", {})
    target = getattr(plane, "control", {}).get("target", {})
    repository = (
        str(target.get("repository"))
        if isinstance(target, Mapping) and target.get("repository")
        else str(Path(plane.repo_root).resolve())
    )
    target_branch = str(getattr(plane, "target_branch", "") or node.get("pr_target", ""))
    if not target_branch:
        raise OrchestrationError("the controller has no singleton target branch")
    instruction_material = {
        "repository": repository,
        "node_id": node_id,
        # All actions from claim through receipt are one durable node-delivery
        # lifecycle and must resume the same task. Target advancement or an
        # explicit failed retry creates a distinct identity below.
        "lifecycle": "NODE_DELIVERY",
        # CREATE, RESUME, repair, and receipt work are one write-authorized
        # lifecycle. Preparation is intentionally a different identity so a
        # read-only task can never be mistaken for an execution grant.
        "authority_class": (
            "PREPARATION_ONLY"
            if authority_mode == "PREPARATION_ONLY"
            else "WRITE_AUTHORIZED"
        ),
        "branch": str(node.get("branch")),
        "target_branch": target_branch,
        "plan_fingerprint": str(getattr(plane, "expected_plan_fingerprint", "unknown")),
        "target_sha": str(plane.current_target_sha()) if hasattr(plane, "current_target_sha") else "unknown",
        "attempt": 1,
        "retry_of": None,
    }
    def instruction_digest(material: Mapping[str, object]) -> str:
        return "sha256:" + sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    instruction_id = instruction_digest(instruction_material)
    binding = launch_binding(Path(plane.repo_root), instruction_id)
    retry_of: str | None = None
    while (
        binding is not None
        and binding.get("state") == "RELEASED"
        and binding.get("terminal_state") in {"FAILED", "CANCELLED"}
    ):
        retry_of = str(binding.get("event_id"))
        prior_attempt = binding.get("attempt")
        if type(prior_attempt) is not int or prior_attempt < 1:
            raise OrchestrationError("released launch has an invalid retry attempt")
        instruction_material["attempt"] = prior_attempt + 1
        instruction_material["retry_of"] = retry_of
        instruction_id = instruction_digest(instruction_material)
        binding = launch_binding(Path(plane.repo_root), instruction_id)
    effective_action = action
    if binding is not None and binding.get("state") in {
        "BOUND",
        "HOST_EVENT_OBSERVED",
        "ATTENTION_ACKNOWLEDGED",
    }:
        effective_action = "RESUME_BOUND"
    elif binding is not None and binding.get("state") in {"PREPARED", "CREATED"}:
        effective_action = "RECOVER_PREPARED"
    raw_reasons = row.get("reasons", [])
    reasons = list(raw_reasons) if isinstance(raw_reasons, (list, tuple)) else []
    return {
        "task_key": node_id,
        "node_id": node_id,
        "launch_instruction_id": instruction_id,
        "idempotency_key": instruction_id,
        "attempt": instruction_material["attempt"],
        "retry_of": retry_of,
        "title": f"Hive Mind {node_id} — {action} — {authority_mode} [{instruction_id[7:19]}]",
        "action": effective_action,
        "authority_mode": authority_mode,
        "may_claim_or_write": authority_mode != "PREPARATION_ONLY",
        "start_condition": (
            "current dispatcher release says START NOW for this exact node"
            if authority_mode == "PREPARATION_ONLY"
            else "authority already established by release, claim, or checked-in repair grant"
        ),
        "required": required,
        "state": str(row.get("state", "UNKNOWN")),
        "branch": str(node.get("branch")),
        "target_branch": target_branch,
        "write_scope": list(node.get("write_scope", [])),
        "reasons": reasons,
        "expected_artifact": (
            "validated candidate, durable receipt, released claim, and draft PR "
            "targeting the configured integration branch"
        ),
        "transport": "durable_user_owned_task",
        "binding_required": True,
        "binding": dict(binding) if binding is not None else None,
        "host_adapters": adapters,
        "prompt": _task_prompt(plane, node_id, effective_action, authority_mode),
    }


def _closure_key(task: Mapping[str, object], nodes: Mapping[str, Mapping[str, Any]]) -> tuple[int, int, int, str]:
    state_rank = {
        "WAITING_FOR_RECEIPT": 0,
        "PR_OPEN": 1,
        "CI_FAILED": 2,
        "RUNNING": 3,
        "CLAIMED": 4,
        "REPAIR_REQUIRED": 5,
        "RECONCILIATION_REQUIRED": 6,
        "INTEGRATION_READY": 7,
        "PROMOTION_READY": 7,
        "READY": 8,
    }
    node_id = str(task.get("node_id"))
    node = nodes.get(node_id, {})
    return (
        state_rank.get(str(task.get("state")), 99),
        -int(node.get("critical_path_importance", 0)),
        -int(node.get("downstream_unlock_value", 0)),
        node_id,
    )


def build_orchestration_contract(
    plane: Any,
    request: str,
    *,
    status: Mapping[str, object] | None = None,
) -> dict[str, object]:
    policy = load_policy(Path(plane.repo_root))
    current = dict(status or plane.status())
    decision = infer_intent(request, current)
    node_defs = _node_map(plane)
    rows = {
        str(row.get("node_id")): row
        for row in _node_rows(current)
        if isinstance(row.get("node_id"), str)
    }

    tasks: list[dict[str, object]] = []
    if decision.intent != "CHECK" and current.get("complete") is not True:
        if current.get("reconciliation_required") is True:
            reconciliation_material = {
                "repository": str(
                    getattr(plane, "control", {}).get("target", {}).get(
                        "repository", Path(plane.repo_root).resolve()
                    )
                ),
                "action": "RECONCILE",
                "target_sha": current.get("target_sha"),
                "plan_fingerprint": current.get("plan_fingerprint"),
            }
            reconciliation_id = "sha256:" + sha256(
                json.dumps(
                    reconciliation_material,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            tasks.append(
                {
                    "task_key": "RECONCILIATION",
                    "node_id": None,
                    "launch_instruction_id": reconciliation_id,
                    "idempotency_key": reconciliation_id,
                    "title": f"Hive Mind Reconciliation [{reconciliation_id[7:19]}]",
                    "action": "RECONCILE",
                    "required": True,
                    "state": "RECONCILIATION_REQUIRED",
                    "transport": "durable_user_owned_task",
                    "binding_required": True,
                    "host_adapters": policy.get("host_adapters", {}),
                    "expected_artifact": "current verified snapshot and append-only reconciliation record",
                    "prompt": (
                        "Read .autopilot/README.md and .autopilot/orchestration-policy.json. "
                        "Refresh verified repository/GitHub truth, reconcile the exact target, "
                        "run doctor/status, and return the newly eligible wave. Do not implement "
                        "product work or mutate a protected branch."
                    ),
                }
            )
        else:
            for node_id, row in sorted(rows.items()):
                state = str(row.get("state"))
                node = node_defs.get(node_id)
                if node is None:
                    continue
                if state in ACTIVE_STATES:
                    action = {
                        "WAITING_FOR_RECEIPT": "PUBLISH_RECEIPT",
                        "PR_OPEN": "VALIDATE_PR",
                    }.get(state, "RESUME")
                    tasks.append(_task(plane, policy, node, row, action=action))
                elif state in RECOVERY_STATES:
                    action = {
                        "CI_FAILED": "REPAIR_CI",
                        "REPAIR_REQUIRED": "REPAIR_NODE",
                        "RECONCILIATION_REQUIRED": "RECONCILE_NODE",
                        "REPLAN_REQUIRED": "REPLAN_NODE",
                    }[state]
                    tasks.append(_task(plane, policy, node, row, action=action))

            release = current.get("dispatch_release")
            released: list[str] = []
            if isinstance(release, Mapping) and release.get("valid") is True:
                raw = release.get("released_wave", [])
                if isinstance(raw, list):
                    released = [str(item) for item in raw]
            existing = {str(task.get("node_id")) for task in tasks}
            for node_id in released:
                if node_id in existing or node_id not in node_defs:
                    continue
                row = rows.get(node_id, {"node_id": node_id, "state": "READY"})
                tasks.append(
                    _task(
                        plane, policy, node_defs[node_id], row, action="CREATE",
                        authority_mode="EXECUTION_AUTHORIZED",
                    )
                )
                existing.add(node_id)

            eligible = current.get("eligible", [])
            if isinstance(eligible, list):
                for node_id in sorted(str(item) for item in eligible):
                    if node_id in existing or node_id not in node_defs:
                        continue
                    row = rows.get(node_id, {"node_id": node_id, "state": "READY"})
                    tasks.append(
                        _task(
                            plane, policy, node_defs[node_id], row,
                            action="PREPARE_READ_ONLY", authority_mode="PREPARATION_ONLY",
                        )
                    )
                    existing.add(node_id)

    primary_tasks = [task for task in tasks if task.get("required") is True]
    closure_target = None
    if primary_tasks:
        closure_target = min(primary_tasks, key=lambda item: _closure_key(item, node_defs)).get("task_key")

    release = current.get("dispatch_release", {})
    release_valid = isinstance(release, Mapping) and release.get("valid") is True
    eligible = current.get("eligible", [])
    dispatch_required = (
        decision.intent in {"START", "CONTINUE", "FINISH"}
        and not release_valid
        and current.get("reconciliation_required") is not True
        and isinstance(eligible, list)
        and bool(eligible)
    )
    observed_states = {str(row.get("state", "")) for row in rows.values()}
    live_bindings = active_launch_bindings(Path(plane.repo_root))
    active_claims = current.get("active_claims", [])
    active_validation_lease = current.get("active_validation_lease")
    runtime_authority_active = (
        isinstance(active_claims, list) and bool(active_claims)
    ) or isinstance(active_validation_lease, Mapping)
    if tasks or live_bindings or runtime_authority_active:
        outcome = "ACTIVE"
        quiescent = False
    elif observed_states and observed_states.issubset(SUCCESS_STATES):
        outcome = "SUCCESS"
        quiescent = True
    elif observed_states & BLOCKING_STATES:
        outcome = "BLOCKED"
        quiescent = bool(
            current.get("complete") is True
            and observed_states
            and observed_states.issubset(TERMINAL_STATES)
        )
    else:
        outcome = "IDLE"
        quiescent = False

    authority_counts: dict[str, int] = {}
    for task in tasks:
        mode = str(task.get("authority_mode", "UNKNOWN"))
        authority_counts[mode] = authority_counts.get(mode, 0) + 1

    sidecars = plan_sidecars(tasks, node_defs, policy["sidecars"])
    sidecars_by_parent: dict[str, list[dict[str, object]]] = {}
    for sidecar in sidecars:
        sidecars_by_parent.setdefault(str(sidecar["parent_launch_instruction_id"]), []).append(sidecar)
    for task in tasks:
        task["sidecars"] = sidecars_by_parent.get(str(task.get("launch_instruction_id")), [])

    material = {
        "schema_version": 1,
        "kind": "hive-mind-autopilot-orchestration-contract-v1",
        "request": request,
        "intent": decision.to_dict(),
        "target_branch": current.get("target_branch"),
        "target_sha": current.get("target_sha"),
        "plan_id": current.get("plan_id"),
        "plan_fingerprint": current.get("plan_fingerprint"),
        "dispatch_required": dispatch_required,
        "dispatch_release": release,
        "eligible": list(eligible) if isinstance(eligible, list) else [],
        "tasks": tasks,
        "task_cohort": {
            "size": len(tasks),
            "task_keys": [str(task.get("task_key")) for task in tasks],
            "authority_counts": dict(sorted(authority_counts.items())),
            "created_together_before_first_wait": True,
            "every_task_polled_to_terminal": True,
        },
        "sidecar_cohort": {
            "size": len(sidecars),
            "sidecar_ids": [str(item["sidecar_id"]) for item in sidecars],
            "planned_token_budget": sum(int(item["token_budget"]) for item in sidecars),
            "estimated_net_savings_tokens": sum(
                int(item["estimated_net_savings_tokens"]) for item in sidecars
            ),
            "root_mediated": True,
            "all_parents_require_terminal_ack": True,
            "policy": dict(policy["sidecars"]),
        },
        "active_host_bindings": [dict(item) for item in live_bindings],
        "active_claims": list(active_claims) if isinstance(active_claims, list) else [],
        "active_validation_lease": (
            dict(active_validation_lease)
            if isinstance(active_validation_lease, Mapping)
            else None
        ),
        "closure_target": closure_target,
        "outcome": outcome,
        "successful": outcome == "SUCCESS",
        "quiescent": quiescent,
        "execution": {
            "executor_module": policy["host_executor"]["module"],
            "executor_entrypoint": policy["host_executor"]["entrypoint"],
            "primary_transport": "durable_user_owned_task",
            "nested_agents": "bounded_sidecars_only",
            "create_all_parallel_safe_primary_tasks": True,
            "create_released_tasks_even_when_recovery_tasks_exist": True,
            "create_eligible_read_only_preparation_tasks": True,
            "closure_target_prioritizes_collection_not_task_creation": True,
            "resume_by_node_identity_before_create": True,
            "recover_unbound_launch_by_instruction_id": True,
            "record_task_id_host_id_and_cursor": True,
            "poll_until_terminal": True,
            "answer_and_resume_blocked_tasks": True,
            "minimum_primary_completions_before_parent_yield": policy["polling"][
                "minimum_primary_completions_before_parent_yield"
            ],
            "parent_final_while_required_tasks_active": False,
        },
        "stop_condition": (
            "current DAG is quiescent: every required node is terminal, all claims and "
            "leases are released, required receipts and integration evidence are valid, "
            "and no required primary task is active"
        ),
    }
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    material["contract_id"] = "sha256:" + sha256(encoded.encode("utf-8")).hexdigest()
    return material


def simple_prompt() -> str:
    return (
        "Use Hive Mind OS Autopilot on this repository. Infer whether I mean build, "
        "start, continue, check, or finish; execute its durable parallel-task contract, "
        "recover blockers, and continue until the current DAG is quiescent."
    )
