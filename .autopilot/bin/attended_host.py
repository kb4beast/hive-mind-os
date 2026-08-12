"""Host adapter whose transport is an attended Codex parent.

Codex cloud exposes no API a program can call, so this adapter does not pretend to
launch anything. ``create_thread`` writes a durable session card that the operator
opens, and progress is read back from repository evidence rather than from the
host: claim commits, pushed work, and receipt commits are authored by fixed
autopilot identities, and blocker packets land in the control plane's own state.

That inversion is the point. ``wait_threads`` polls Git under a wall-clock
deadline instead of waiting on a conversation no API can observe, so the wave
supervisor in ``host_execution.execute_contract`` cannot hang on this host —
nothing in the loop waits on the host at all. A run ends either with terminal
evidence or with a bounded no-progress verdict naming exactly which sessions the
operator still has to open.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any

HOST_ID = "codex-attended"
CAPABILITY = "durable_user_owned_task"
CURSOR = "attended-v1"
CREATE_KIND = "hive-mind-host-task-binding-v1"
EVENT_KIND = "hive-mind-host-event-v1"
ACK_KIND = "hive-mind-host-message-ack-v1"
RECEIPT_IDENTITY = "autopilot-receipt@hive-mind.invalid"
CLAIM_IDENTITY = "autopilot-claim@hive-mind.invalid"


class AttendedHostError(RuntimeError):
    """Raised when the attended host is asked for something it cannot honour."""


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


class AttendedCodexHost:
    """A ``HostAdapter`` for a host that only a human can actually drive."""

    def __init__(
        self,
        plane: Any,
        *,
        wait_seconds: int = 60,
        poll_seconds: int = 5,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if wait_seconds < 1 or poll_seconds < 1:
            raise AttendedHostError("attended host wait bounds must be positive")
        self.plane = plane
        self.repo_root = Path(plane.repo_root)
        self.wait_seconds = wait_seconds
        self.poll_seconds = poll_seconds
        self.clock = clock
        self.sleep = sleep
        self.host_dir = Path(plane.state_dir) / "host"
        self.cards_dir = self.host_dir / "cards"
        self.ledger_path = self.host_dir / "attended-threads.json"
        self._nodes: dict[str, str] = {}

    # ------------------------------------------------------------------ ledger

    def _ledger(self) -> dict[str, Any]:
        if not self.ledger_path.is_file():
            return {}
        try:
            value = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _write_ledger(self, value: Mapping[str, Any]) -> None:
        self.host_dir.mkdir(parents=True, exist_ok=True)
        self.ledger_path.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def bind_tasks(self, tasks: Sequence[Mapping[str, object]]) -> None:
        """Record which node each launch instruction belongs to.

        ``create_thread`` receives only a title, a prompt, and an idempotency key,
        but every evidence probe is per node, so the contract's own mapping is
        captured before execution rather than parsed back out of a title.
        """

        for task in tasks:
            instruction = task.get("launch_instruction_id")
            node_id = task.get("node_id")
            if isinstance(instruction, str) and isinstance(node_id, str):
                self._nodes[instruction] = node_id

    def pending_cards(self) -> tuple[Mapping[str, Any], ...]:
        """Return the session cards the operator has not yet shown any evidence for.

        The ledger accumulates one entry per launch attempt, but the operator
        opens one session per node, so entries are deduplicated by node.  Every
        attempt for a node writes the same per-node card file, so whichever
        entry survives points at identical instructions.
        """

        pending: dict[str, Mapping[str, Any]] = {}
        for entry in self._ledger().values():
            node_id = entry.get("node_id")
            if not isinstance(node_id, str) or self._observe(node_id) is None:
                key = node_id if isinstance(node_id, str) else str(entry.get("task_id"))
                pending[key] = entry
        return tuple(pending.values())

    # ------------------------------------------------------------------ adapter

    def trusted_singleton_target(self, *, repo_root: Path) -> str:
        del repo_root
        return str(self.plane.target_branch)

    def inspect_runtime_authority(self, *, repo_root: Path) -> Mapping[str, object]:
        """Report live claim and lease authority from the control plane's state.

        The attended host has no runtime of its own to inspect; the control
        plane's session-local claim files and validation lease ARE the runtime
        authority a wave must not trample.
        """

        del repo_root
        claims = [dict(value) for value in self.plane.active_claims().values()]
        lease: dict[str, Any] | None = None
        lease_path = Path(self.plane.validation_lease_path)
        if lease_path.is_file():
            try:
                value = json.loads(lease_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                value = None
            if isinstance(value, Mapping):
                lease = dict(value)
        return {
            "target_branch": str(self.plane.target_branch),
            "active_claims": claims,
            "active_validation_lease": lease,
            "quiescent": not claims and lease is None,
        }

    def lookup_thread(self, *, idempotency_key: str) -> Mapping[str, object] | None:
        entry = self._ledger().get(idempotency_key)
        if not isinstance(entry, Mapping):
            return None
        return {
            "host_id": entry.get("host_id"),
            "task_id": entry.get("task_id"),
            "cursor": entry.get("cursor"),
            "capability_digest": entry.get("capability_digest"),
        }

    def create_thread(
        self, *, title: str, prompt: str, idempotency_key: str
    ) -> Mapping[str, object]:
        if not title.strip() or not prompt.strip():
            raise AttendedHostError("an attended session card requires a title and prompt")
        task_id = "attended-" + _digest(idempotency_key)[:32]
        node_id = self._nodes.get(idempotency_key, "")
        ledger = self._ledger()
        existing = ledger.get(idempotency_key)
        if isinstance(existing, Mapping) and existing.get("task_id") != task_id:
            raise AttendedHostError("attended ledger conflicts with the launch identity")
        self.cards_dir.mkdir(parents=True, exist_ok=True)
        card_name = f"{node_id or task_id}.md"
        card_path = self.cards_dir / card_name
        card_path.write_text(
            f"# {title}\n\n"
            f"Open one Codex session named exactly `{title}` and paste everything\n"
            f"below the rule. Do not add instructions of your own.\n\n---\n\n{prompt}\n",
            encoding="utf-8",
        )
        ledger[idempotency_key] = {
            "host_id": HOST_ID,
            "task_id": task_id,
            "cursor": CURSOR,
            "capability": CAPABILITY,
            "capability_digest": "sha256:" + _digest(CAPABILITY),
            "node_id": node_id,
            "title": title,
            "card": str(card_path.relative_to(self.repo_root)),
        }
        self._write_ledger(ledger)
        return {
            "kind": CREATE_KIND,
            "host_id": HOST_ID,
            "task_id": task_id,
            "cursor": CURSOR,
            "capability": CAPABILITY,
            "idempotency_key": idempotency_key,
        }

    def wait_threads(
        self, targets: Sequence[Mapping[str, object]]
    ) -> Sequence[Mapping[str, object]]:
        """Poll repository evidence under a deadline; never wait on the host."""

        by_task = {
            str(entry.get("task_id")): entry
            for entry in self._ledger().values()
            if isinstance(entry, Mapping)
        }
        deadline = self.clock() + self.wait_seconds
        while True:
            events: list[Mapping[str, object]] = []
            for target in targets:
                task_id = str(target.get("task_id"))
                entry = by_task.get(task_id)
                if entry is None:
                    raise AttendedHostError(f"unknown attended task {task_id!r}")
                node_id = str(entry.get("node_id") or "")
                observed = self._observe(node_id) if node_id else None
                if observed is None:
                    continue
                state, cursor = observed
                if cursor == target.get("after_event_cursor"):
                    continue
                events.append(
                    {
                        "kind": EVENT_KIND,
                        "host_id": HOST_ID,
                        "task_id": task_id,
                        "cursor": CURSOR,
                        "capability": CAPABILITY,
                        "state": state,
                        "event_id": f"{task_id}:{cursor}",
                        "event_cursor": cursor,
                    }
                )
            if events or self.clock() >= deadline:
                return tuple(events)
            self.sleep(self.poll_seconds)

    def send_message_to_thread(
        self,
        *,
        host_id: str,
        task_id: str,
        cursor: str,
        capability: str,
        message: str,
        idempotency_key: str,
    ) -> Mapping[str, object]:
        """Record a relay instruction; the operator is the only delivery channel."""

        if host_id != HOST_ID:
            raise AttendedHostError("attended host cannot message another host")
        ledger = self._ledger()
        entry = next(
            (
                item
                for item in ledger.values()
                if isinstance(item, Mapping) and item.get("task_id") == task_id
            ),
            None,
        )
        if entry is None:
            raise AttendedHostError(f"unknown attended task {task_id!r}")
        relay = self.cards_dir / f"{entry.get('node_id') or task_id}.relay.md"
        relay.write_text(
            f"# Relay to {entry.get('title')}\n\n"
            f"Paste this into that session, then leave it running.\n\n---\n\n{message}\n",
            encoding="utf-8",
        )
        return {
            "kind": ACK_KIND,
            "host_id": host_id,
            "task_id": task_id,
            "cursor": cursor,
            "capability": capability,
            "accepted": True,
            "message_id": "relay-" + _digest(idempotency_key)[:24],
            "idempotency_key": idempotency_key,
        }

    # ----------------------------------------------------------------- evidence

    def _observe(self, node_id: str) -> tuple[str, str] | None:
        """Classify a node from durable evidence alone, or return None if silent."""

        failure = self._recorded_failure(node_id)
        if failure is not None:
            return ("FAILED", failure)
        try:
            branch = str(self.plane.node(node_id).get("branch"))
        except Exception as error:  # unknown node is a contract fault, not a wait
            raise AttendedHostError(f"cannot observe node {node_id!r}") from error
        head = self.plane.remote_branch_sha(branch)
        if head is None:
            return None
        self.plane._git(("fetch", "origin", f"refs/heads/{branch}"), check=False)
        author = self.plane._git(
            ("show", "-s", "--format=%ae", head), check=False
        ).stdout.strip()
        if author == RECEIPT_IDENTITY:
            return ("SUCCEEDED", head)
        return ("ACTIVE", head)

    def _recorded_failure(self, node_id: str) -> str | None:
        path = Path(self.plane.blockers_dir) / f"{node_id}.jsonl"
        if not path.is_file():
            return None
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            return None
        if getattr(self.plane, "blockers_fully_resolved", lambda _node: False)(node_id):
            # Every recorded cause carries a verified resolution; the ledger is
            # a history of healed failures, not live failure evidence.
            return None
        return "blocker:" + _digest(lines[-1])[:32]


class EvidenceResolver:
    """Answer an attention event with a bounded instruction, never a judgement call.

    The resolver deliberately does not attempt to solve a worker's problem. It
    restates the one thing that makes a session terminal, so a stalled worker
    either produces evidence or records a blocker instead of idling.
    """

    def resolve_attention(
        self, task: Mapping[str, object], event: Mapping[str, object]
    ) -> str:
        node_id = str(task.get("node_id") or "this node")
        attention = str(event.get("attention") or "").strip()
        return (
            f"Continue {node_id}. Report WHAT I DID / NEXT STEPS / BLOCKS. "
            "You are terminal only at a pushed durable receipt commit or an "
            "`autopilot fail` blocker record; chat prose is never completion. "
            "Never wait on a sibling node — record a blocker instead."
            + (f" Attention reported: {attention}" if attention else "")
        )
