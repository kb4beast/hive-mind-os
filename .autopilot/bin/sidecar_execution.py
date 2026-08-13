"""Token-aware planning and durable settlement for ephemeral execution sidecars.

Sidecars accelerate a durable primary task. They are not DAG nodes and never carry
claim, write, receipt, validation-lease, publication, or judgment authority.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Mapping, Sequence

SIDECAR_KINDS = frozenset(
    {"bounded_read_only_research", "independent_review", "non_blocking_validation"}
)
ACTIVE_SIDECAR_STATES = frozenset({"PREPARED", "BOUND", "ACTIVE", "ATTENTION_ACKNOWLEDGED"})
TERMINAL_SIDECAR_STATES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED", "SPAWN_FAILED"})


class SidecarPolicyError(ValueError):
    """A sidecar policy, specification, or durable event is unsafe."""


def _canonical(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _managed(repo_root: Path, *parts: str) -> Path:
    root = repo_root.resolve()
    current = root
    for part in parts:
        current /= part
        is_junction = getattr(current, "is_junction", None)
        if current.is_symlink() or (callable(is_junction) and is_junction()):
            raise SidecarPolicyError(f"sidecar state path uses a link: {current}")
        if current.exists() and not current.resolve().is_relative_to(root):
            raise SidecarPolicyError(f"sidecar state path escapes repository: {current}")
    return current


@contextmanager
def _ledger_lock(repo_root: Path):
    path = _managed(repo_root, ".autopilot", "sidecar-bindings.lock")
    if not path.is_file():
        raise SidecarPolicyError("required sidecar binding lock file is missing")
    descriptor = os.open(path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
    deadline = time.monotonic() + 10.0
    while True:
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
            break
        except OSError:
            if time.monotonic() >= deadline:
                os.close(descriptor)
                raise SidecarPolicyError("sidecar binding ledger lock timed out")
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


def _events_unlocked(repo_root: Path) -> tuple[Mapping[str, object], ...]:
    path = _managed(repo_root, ".autopilot", "state", "sidecar-bindings.jsonl")
    if not path.exists():
        return ()
    previous: str | None = None
    events: list[Mapping[str, object]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise SidecarPolicyError(f"cannot read sidecar ledger: {error}") from error
    for index, line in enumerate(lines, 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise SidecarPolicyError(f"sidecar ledger line {index} is invalid") from error
        if not isinstance(event, Mapping):
            raise SidecarPolicyError(f"sidecar ledger line {index} must be an object")
        material = dict(event)
        event_id = material.pop("event_id", None)
        if material.get("previous_event_id") != previous:
            raise SidecarPolicyError(f"sidecar ledger line {index} breaks the hash chain")
        expected = "sha256:" + sha256(_canonical(material)).hexdigest()
        if event_id != expected:
            raise SidecarPolicyError(f"sidecar ledger line {index} has an invalid digest")
        previous = str(event_id)
        events.append(event)
    return tuple(events)


def sidecar_events(repo_root: Path) -> tuple[Mapping[str, object], ...]:
    with _ledger_lock(repo_root):
        return _events_unlocked(repo_root)


def _append(repo_root: Path, value: Mapping[str, object]) -> Mapping[str, object]:
    with _ledger_lock(repo_root):
        events = _events_unlocked(repo_root)
        material = {
            "schema_version": 1,
            **dict(value),
            "previous_event_id": events[-1]["event_id"] if events else None,
            "recorded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
        event = {**material, "event_id": "sha256:" + sha256(_canonical(material)).hexdigest()}
        path = _managed(repo_root, ".autopilot", "state", "sidecar-bindings.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600
        )
        with os.fdopen(descriptor, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return event


def latest_sidecars(repo_root: Path) -> dict[str, Mapping[str, object]]:
    latest: dict[str, Mapping[str, object]] = {}
    for event in sidecar_events(repo_root):
        sidecar_id = event.get("sidecar_id")
        if isinstance(sidecar_id, str):
            latest[sidecar_id] = event
    return latest


def active_sidecars(repo_root: Path) -> tuple[Mapping[str, object], ...]:
    latest = latest_sidecars(repo_root)
    return tuple(
        latest[key]
        for key in sorted(latest)
        if latest[key].get("state") in ACTIVE_SIDECAR_STATES
    )


def record_sidecar_state(repo_root: Path, sidecar_id: str, state: str, **fields: object) -> Mapping[str, object]:
    if state not in ACTIVE_SIDECAR_STATES | TERMINAL_SIDECAR_STATES:
        raise SidecarPolicyError("invalid sidecar state")
    prior = latest_sidecars(repo_root).get(sidecar_id)
    if prior is not None and prior.get("state") in TERMINAL_SIDECAR_STATES:
        if prior.get("state") == state and all(prior.get(key) == value for key, value in fields.items()):
            return prior
        raise SidecarPolicyError("terminal sidecar state cannot regress or change")
    return _append(repo_root, {"kind": "hive-mind-sidecar-ledger-event-v1", "sidecar_id": sidecar_id, "state": state, **fields})


def validate_sidecar_policy(value: object) -> tuple[str, ...]:
    if not isinstance(value, Mapping):
        return ("sidecars must be an object",)
    issues: list[str] = []
    flags = {
        "enabled": True,
        "root_mediates_descendants": True,
        "primary_authority_inheritance": False,
        "require_parent_ack": True,
        "close_descendants_before_parent_terminal": True,
    }
    for field, expected in flags.items():
        if value.get(field) is not expected:
            issues.append(f"sidecars.{field} must be {str(expected).lower()}")
    allowed = value.get("allowed_purposes")
    if not isinstance(allowed, list) or set(allowed) != set(SIDECAR_KINDS):
        issues.append("sidecar allowed_purposes must contain the three bounded purposes")
    minima = {
        "max_depth": 1, "max_sidecars_per_primary": 1, "max_total_sidecars": 1,
        "total_token_budget": 1, "per_sidecar_token_budget": 1, "max_result_tokens": 1,
        "coordination_overhead_tokens": 0, "min_net_savings_tokens": 1,
        "max_no_progress_cycles": 1, "max_poll_cycles": 1, "max_replay_events": 1,
        "wait_timeout_seconds": 1, "max_targets_per_wait": 1,
    }
    for field, minimum in minima.items():
        item = value.get(field)
        if type(item) is not int or item < minimum:
            issues.append(f"sidecars.{field} must be an integer >= {minimum}")
    if type(value.get("max_depth")) is int and int(value["max_depth"]) > 2:
        issues.append("sidecars.max_depth must be <= 2")
    if type(value.get("max_targets_per_wait")) is int and int(value["max_targets_per_wait"]) > 8:
        issues.append("sidecars.max_targets_per_wait must be <= 8")
    if type(value.get("per_sidecar_token_budget")) is int and type(value.get("total_token_budget")) is int:
        if int(value["per_sidecar_token_budget"]) > int(value["total_token_budget"]):
            issues.append("per-sidecar budget cannot exceed total budget")
    if type(value.get("max_sidecars_per_primary")) is int and type(value.get("max_total_sidecars")) is int:
        if int(value["max_sidecars_per_primary"]) > int(value["max_total_sidecars"]):
            issues.append("per-primary sidecar count cannot exceed cohort count")
    return tuple(issues)


def _candidate(parent_id: str, node_id: str, purpose: str, prompt: str, saved: int, policy: Mapping[str, object]) -> dict[str, object]:
    budget = int(policy["per_sidecar_token_budget"])
    result = int(policy["max_result_tokens"])
    overhead = int(policy["coordination_overhead_tokens"])
    material: dict[str, object] = {
        "schema_version": 1, "kind": "hive-mind-sidecar-spec-v1",
        "parent_launch_instruction_id": parent_id, "parent_sidecar_id": None,
        "node_id": node_id, "depth": 1, "purpose": purpose, "prompt": prompt,
        "read_only": True, "token_budget": budget, "max_result_tokens": result,
        "estimated_parent_tokens_saved": saved, "estimated_coordination_tokens": overhead,
        "estimated_net_savings_tokens": saved - budget - result - overhead,
    }
    material["sidecar_id"] = "sha256:" + sha256(_canonical(material)).hexdigest()
    material["idempotency_key"] = material["sidecar_id"]
    return material


def make_descendant_spec(parent: Mapping[str, object], request: Mapping[str, object], policy: Mapping[str, object]) -> dict[str, object]:
    """Root-validate and authenticate a requested descendant; never let a child spawn."""
    if set(request) != {"purpose", "prompt", "evidence_refs"}:
        raise SidecarPolicyError("descendant request fields are invalid")
    purpose = request.get("purpose")
    prompt = request.get("prompt")
    evidence_refs = request.get("evidence_refs")
    if purpose not in SIDECAR_KINDS:
        raise SidecarPolicyError("descendant purpose is not allowed")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
        raise SidecarPolicyError("descendant prompt is empty or oversized")
    if not isinstance(evidence_refs, list) or not evidence_refs or not all(isinstance(item, str) and item.strip() for item in evidence_refs):
        raise SidecarPolicyError("descendant request requires independently resolvable evidence")
    depth = int(parent["depth"]) + 1
    if depth > int(policy["max_depth"]):
        raise SidecarPolicyError("descendant depth exceeds policy")
    saved = {
        "bounded_read_only_research": 4_800,
        "independent_review": 5_200,
        "non_blocking_validation": 4_600,
    }[str(purpose)]
    spec = _candidate(
        str(parent["parent_launch_instruction_id"]), str(parent["node_id"]),
        str(purpose), prompt, saved, policy,
    )
    spec["parent_sidecar_id"] = parent["sidecar_id"]
    spec["depth"] = depth
    spec["request_evidence_refs"] = list(evidence_refs)
    # Re-authenticate after parent/depth/evidence are bound.
    material = dict(spec)
    material.pop("sidecar_id", None)
    material.pop("idempotency_key", None)
    spec["sidecar_id"] = "sha256:" + sha256(_canonical(material)).hexdigest()
    spec["idempotency_key"] = spec["sidecar_id"]
    return spec


def plan_sidecars(tasks: Sequence[Mapping[str, object]], nodes: Mapping[str, Mapping[str, object]], policy: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    issues = validate_sidecar_policy(policy)
    if issues:
        raise SidecarPolicyError("; ".join(issues))
    candidates: list[dict[str, object]] = []
    for task in tasks:
        parent_id = str(task.get("launch_instruction_id", ""))
        node_id = str(task.get("node_id") or task.get("task_key") or "UNKNOWN")
        node = nodes.get(node_id, {})
        read_scope = node.get("read_scope", [])
        evidence = node.get("evidence_requirements", [])
        scope_count = len(read_scope) if isinstance(read_scope, list) else 0
        evidence_count = len(evidence) if isinstance(evidence, list) else 0
        risk = str(node.get("risk", "moderate")).lower()
        if task.get("authority_mode") == "PREPARATION_ONLY" or scope_count >= 3:
            candidates.append(_candidate(parent_id, node_id, "bounded_read_only_research", f"Read-only sidecar for {node_id}. Inspect declared read scope; return compact findings, exact evidence, contradictions, and blockers. Never claim, write, commit, push, publish, run a global gate, or spawn directly.", 4_800 + 250 * min(scope_count, 8), policy))
        if risk in {"moderate", "high", "critical"} or evidence_count >= 3:
            saved = {"moderate": 5_200, "high": 6_600, "critical": 7_800}.get(risk, 5_400) + 150 * min(evidence_count, 8)
            candidates.append(_candidate(parent_id, node_id, "independent_review", f"Independent read-only review for {node_id}. Threat-model the work and return compact ranked findings with exact evidence. Never claim, write, approve or judge the parent, run a global gate, or spawn directly.", saved, policy))
    candidates.sort(key=lambda item: (-int(item["estimated_net_savings_tokens"]), str(item["sidecar_id"])))
    admitted: list[dict[str, object]] = []
    counts: dict[str, int] = {}
    consumed = 0
    for item in candidates:
        parent = str(item["parent_launch_instruction_id"])
        budget = int(item["token_budget"])
        if int(item["estimated_net_savings_tokens"]) < int(policy["min_net_savings_tokens"]):
            continue
        if counts.get(parent, 0) >= int(policy["max_sidecars_per_primary"]):
            continue
        if len(admitted) >= int(policy["max_total_sidecars"]) or consumed + budget > int(policy["total_token_budget"]):
            continue
        admitted.append(item)
        counts[parent] = counts.get(parent, 0) + 1
        consumed += budget
    return tuple(sorted(admitted, key=lambda item: str(item["sidecar_id"])))


def sidecar_spec_digest(spec: Mapping[str, object]) -> str:
    material = dict(spec)
    material.pop("sidecar_id", None)
    material.pop("idempotency_key", None)
    return "sha256:" + sha256(_canonical(material)).hexdigest()
