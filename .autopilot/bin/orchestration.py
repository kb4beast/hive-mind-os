"""Intent-aware, host-neutral orchestration contracts for Autopilot DAGs.

The deterministic controller owns repository truth.  This module translates that
truth into an executable host contract without pretending that a repository process
can directly control every supported chat/task host.  Host adapters consume the
contract and persist their task identifiers outside repository source files.
"""

from __future__ import annotations

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
READY_STATES = {"READY", "INTEGRATION_READY", "PROMOTION_READY"}


class OrchestrationError(RuntimeError):
    """The orchestration contract cannot be produced safely."""


def _canonical(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _binding_path(repo_root: Path) -> Path:
    return repo_root / ".autopilot" / "state" / "task-bindings.jsonl"


@contextmanager
def _binding_lock(repo_root: Path):
    path = repo_root / ".autopilot" / "task-bindings.lock"
    if not path.is_file():
        raise OrchestrationError("required task binding lock file is missing")
    deadline = time.monotonic() + 10.0
    descriptor = os.open(path, os.O_RDWR)
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
    encoded = json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
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
        if latest[key].get("state")
        in {"PREPARED", "CREATED", "BOUND", "TERMINAL_OBSERVED"}
    )


def prepare_launch(repo_root: Path, instruction_id: str, host: str) -> Mapping[str, object]:
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", instruction_id):
        raise OrchestrationError("launch instruction id must be a SHA-256 digest")
    if not host.strip():
        raise OrchestrationError("launch host is required")
    with _binding_lock(repo_root):
        events = _binding_events_unlocked(repo_root)
        existing = next(
            (event for event in reversed(events) if event.get("launch_instruction_id") == instruction_id),
            None,
        )
        if existing is not None and existing.get("state") != "RELEASED":
            return existing
        return _append_binding_event_unlocked(
            repo_root,
            {
                "kind": "hive-mind-task-binding-event-v1",
                "launch_instruction_id": instruction_id,
                "host": host,
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
) -> Mapping[str, object]:
    with _binding_lock(repo_root):
        events = list(_binding_events_unlocked(repo_root))
        existing = next(
            (event for event in reversed(events) if event.get("launch_instruction_id") == instruction_id),
            None,
        )
        if existing is None or existing.get("state") not in {"PREPARED", "CREATED", "BOUND"}:
            raise OrchestrationError("prepare the launch before binding a host task")
        if existing.get("host") != host:
            raise OrchestrationError("prepared launch host cannot be rebound by another host")
        if existing.get("state") == "BOUND":
            if existing.get("task_id") != task_id or existing.get("host") != host:
                raise OrchestrationError("launch instruction is already bound to another task")
            return existing
        if not host.strip() or not task_id.strip():
            raise OrchestrationError("host and task id are required")
        if existing.get("state") == "PREPARED":
            created = _append_binding_event_unlocked(
                repo_root,
                {
                    "kind": "hive-mind-task-binding-event-v1",
                    "launch_instruction_id": instruction_id,
                    "host": host,
                    "task_id": task_id,
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
                "state": "BOUND",
            },
            events,
        )


def observe_terminal_launch(
    repo_root: Path,
    instruction_id: str,
    *,
    terminal_state: str,
    host_event_ref: str,
    observed_by: str,
) -> Mapping[str, object]:
    if terminal_state not in {"SUCCEEDED", "FAILED", "CANCELLED"}:
        raise OrchestrationError("host terminal state must be SUCCEEDED, FAILED, or CANCELLED")
    if not host_event_ref.strip() or not observed_by.strip():
        raise OrchestrationError("host terminal event reference and observer are required")
    with _binding_lock(repo_root):
        events = _binding_events_unlocked(repo_root)
        existing = next(
            (event for event in reversed(events) if event.get("launch_instruction_id") == instruction_id),
            None,
        )
        if existing is None or existing.get("state") != "BOUND":
            raise OrchestrationError("only a bound launch can record terminal evidence")
        task_id = str(existing.get("task_id", ""))
        if task_id not in host_event_ref:
            raise OrchestrationError("host terminal event reference must bind the exact task id")
        return _append_binding_event_unlocked(
            repo_root,
            {
                "kind": "hive-mind-task-binding-event-v1",
                "launch_instruction_id": instruction_id,
                "host": existing.get("host"),
                "host_id": existing.get("host_id"),
                "task_id": existing.get("task_id"),
                "cursor": existing.get("cursor"),
                "terminal_state": terminal_state,
                "host_terminal_event_ref": host_event_ref,
                "observed_by": observed_by,
                "state": "TERMINAL_OBSERVED",
            },
            events,
        )


def release_launch(
    repo_root: Path,
    instruction_id: str,
    *,
    terminal_event_id: str,
    reason: str,
) -> Mapping[str, object]:
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", terminal_event_id):
        raise OrchestrationError("terminal event id must be a SHA-256 digest")
    if not reason.strip():
        raise OrchestrationError("binding release reason is required")
    with _binding_lock(repo_root):
        events = _binding_events_unlocked(repo_root)
        existing = next(
            (event for event in reversed(events) if event.get("launch_instruction_id") == instruction_id),
            None,
        )
        if (
            existing is None
            or existing.get("state") != "TERMINAL_OBSERVED"
            or existing.get("event_id") != terminal_event_id
        ):
            raise OrchestrationError("release requires the latest bound terminal observation event")
        return _append_binding_event_unlocked(
            repo_root,
            {
                "kind": "hive-mind-task-binding-event-v1",
                "launch_instruction_id": instruction_id,
                "host": existing.get("host"),
                "host_id": existing.get("host_id"),
                "task_id": existing.get("task_id"),
                "cursor": existing.get("cursor"),
                "terminal_state": existing.get("terminal_state"),
                "terminal_event_id": terminal_event_id,
                "reason": reason,
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
        }
        for key, expected_value in expected.items():
            if codex.get(key) != expected_value:
                issues.append(f"Codex adapter {key} must be {expected_value}")
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


def _task_prompt(plane: Any, node_id: str, action: str) -> str:
    base = plane.render_worker_prompt(node_id)
    return (
        "Read .autopilot/orchestration-policy.json and obey its durable-task, "
        "closure-first, polling, recovery, and quiescence contract.\n"
        f"Primary task action: {action}. Reuse existing work for {node_id}; do not "
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
) -> dict[str, object]:
    node_id = str(node.get("id"))
    adapters = policy.get("host_adapters", {})
    target = getattr(plane, "control", {}).get("target", {})
    repository = (
        str(target.get("repository"))
        if isinstance(target, Mapping) and target.get("repository")
        else str(Path(plane.repo_root).resolve())
    )
    instruction_material = {
        "repository": repository,
        "node_id": node_id,
        "branch": str(node.get("branch")),
        "target_branch": str(node.get("pr_target")),
        "plan_fingerprint": str(getattr(plane, "expected_plan_fingerprint", "unknown")),
        "target_sha": str(plane.current_target_sha()) if hasattr(plane, "current_target_sha") else "unknown",
    }
    instruction_id = "sha256:" + sha256(
        json.dumps(instruction_material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    binding = launch_binding(Path(plane.repo_root), instruction_id)
    effective_action = action
    if binding is not None and binding.get("state") == "BOUND":
        effective_action = "RESUME_BOUND"
    elif binding is not None and binding.get("state") in {"PREPARED", "CREATED"}:
        effective_action = "RECOVER_PREPARED"
    elif binding is not None and binding.get("state") == "TERMINAL_OBSERVED":
        effective_action = "RELEASE_TERMINAL"
    return {
        "task_key": node_id,
        "node_id": node_id,
        "launch_instruction_id": instruction_id,
        "idempotency_key": instruction_id,
        "title": f"Hive Mind {node_id} [{instruction_id[7:19]}]",
        "action": effective_action,
        "required": required,
        "state": str(row.get("state", "UNKNOWN")),
        "branch": str(node.get("branch")),
        "target_branch": str(node.get("pr_target")),
        "write_scope": list(node.get("write_scope", [])),
        "reasons": (
            list(row.get("reasons", []))
            if isinstance(row.get("reasons"), (list, tuple))
            else []
        ),
        "expected_artifact": (
            "validated candidate, durable receipt, released claim, and draft PR "
            "targeting the configured integration branch"
        ),
        "transport": "durable_user_owned_task",
        "binding_required": True,
        "binding": dict(binding) if binding is not None else None,
        "host_adapters": adapters,
        "prompt": _task_prompt(plane, node_id, effective_action),
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
            if not tasks:
                for node_id in released:
                    if node_id in existing or node_id not in node_defs:
                        continue
                    row = rows.get(node_id, {"node_id": node_id, "state": "READY"})
                    tasks.append(_task(plane, policy, node_defs[node_id], row, action="CREATE"))

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
    if tasks or live_bindings:
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
        "active_host_bindings": [dict(item) for item in live_bindings],
        "closure_target": closure_target,
        "outcome": outcome,
        "successful": outcome == "SUCCESS",
        "quiescent": quiescent,
        "execution": {
            "primary_transport": "durable_user_owned_task",
            "nested_agents": "bounded_sidecars_only",
            "create_all_parallel_safe_primary_tasks": True,
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
