"""Drive one dispatch round: integrate, validate, and triage, as code.

The wave supervisor in ``host_execution`` ends when every worker is terminal. The
work that follows it — merging node branches in the wave's declared order, running
the round's single leased repository-wide gate, and deciding what a blocker means
— lived only in ``docs/execution/runbooks/README.md`` as prose an operator or a
model had to re-read and re-obey every round.

This module is that prose as a program. Every phase is idempotent, so re-running
after a stall resumes instead of repeating: integration skips branches already in
the target's ancestry, validation refuses to run before the wave is whole, and
triage acts only on the mechanical class of blocker. Anything requiring judgement
is reported with its evidence rather than guessed at.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import healing
from attended_host import RECEIPT_IDENTITY
from dag_standard import Round, compile_rounds, load_plan_graph

# A blocker naming any of these is sealed or external: repairing it would rotate
# the plan fingerprint or fabricate authority, so the driver never touches it.
# The tuple lives in healing so triage and the healer never disagree about what
# is untouchable.
_SEALED_MARKERS = healing.SEALED_MARKERS
# A blocker naming any of these is a stale artifact the control plane owns a verb
# for. These are the only blockers the driver resolves without being asked.
_STALE_MARKERS = (
    "remote branch already exists",
    "already exists; reconcile",
    "does not descend",
    "stale claim",
    "stale target",
)


class RoundDriverError(RuntimeError):
    """Raised when the driver is asked to act from an unsafe position."""


@dataclass(frozen=True, slots=True)
class Step:
    phase: str
    node_id: str | None
    outcome: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "node_id": self.node_id,
            "outcome": self.outcome,
            "detail": self.detail,
        }


@dataclass
class RoundReport:
    round_id: str | None = None
    nodes: tuple[str, ...] = ()
    steps: list[Step] = field(default_factory=list)
    blocked: bool = False

    def record(self, phase: str, node_id: str | None, outcome: str, detail: str) -> Step:
        step = Step(phase=phase, node_id=node_id, outcome=outcome, detail=detail)
        self.steps.append(step)
        if outcome in {"CONFLICT", "FAILED", "CLASS_A", "CLASS_C"}:
            self.blocked = True
        return step

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_id": self.round_id,
            "nodes": list(self.nodes),
            "blocked": self.blocked,
            "steps": [step.to_dict() for step in self.steps],
        }


def _git(plane: Any, *arguments: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return plane._git(tuple(arguments), check=check)


def receipt_head(plane: Any, node_id: str) -> str | None:
    """Return the node branch head only when a durable receipt commit seals it."""

    branch = str(plane.node(node_id).get("branch"))
    head = plane.remote_branch_sha(branch)
    if head is None:
        return None
    _git(plane, "fetch", "origin", f"refs/heads/{branch}")
    author = _git(plane, "show", "-s", "--format=%ae", head).stdout.strip()
    return head if author == RECEIPT_IDENTITY else None


def select_round(
    plane: Any,
    status: Mapping[str, Any],
    *,
    max_sessions: int = 8,
    plan_path: Path | None = None,
) -> Round | None:
    """Return the first compiled round that is not already complete."""

    graph = load_plan_graph(plan_path or Path(plane.ap_root) / "plan.json")
    complete = completed_nodes(status)
    for candidate in compile_rounds(graph, max_sessions=max_sessions):
        if not set(candidate.nodes) <= complete:
            return candidate
    return None


def completed_nodes(status: Mapping[str, Any]) -> set[str]:
    """Return the nodes the control plane currently recognises as COMPLETE.

    ``status["complete"]`` is a plan-wide boolean, not a node list; per-node truth
    lives in the ``nodes`` rows. Reading the boolean as a collection silently
    yields an empty set, which makes every compiled round look unfinished and
    re-selects rounds that were integrated weeks ago.
    """

    rows = status.get("nodes")
    if not isinstance(rows, Sequence):
        return set()
    return {
        str(row.get("node_id"))
        for row in rows
        if isinstance(row, Mapping) and row.get("state") == "COMPLETE"
    }


def integrate_round(
    plane: Any,
    round_: Round,
    report: RoundReport,
    *,
    push: bool = True,
) -> bool:
    """Merge sealed node branches in declared order. Returns True when whole.

    Order is the wave's declared ``--node`` order, never finish order, so the
    integrated history is identical no matter how the workers interleaved.
    """

    target = str(plane.target_branch)
    current = _git(plane, "symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip()
    if current != target:
        raise RoundDriverError(
            f"integration must run on {target!r}; HEAD is {current or 'detached'!r}"
        )
    whole = True
    for node_id in round_.nodes:
        head = receipt_head(plane, node_id)
        if head is None:
            whole = False
            report.record("integrate", node_id, "PENDING", "no sealed receipt on the node branch")
            continue
        if _git(plane, "merge-base", "--is-ancestor", head, "HEAD").returncode == 0:
            report.record("integrate", node_id, "ALREADY", f"{head[:7]} is already in the target")
            continue
        branch = str(plane.node(node_id).get("branch"))
        merged = _git(plane, "merge", "--no-ff", "--no-edit", head)
        if merged.returncode != 0:
            _git(plane, "merge", "--abort")
            whole = False
            report.record(
                "integrate",
                node_id,
                "CONFLICT",
                "scopes are disjoint by contract, so a conflict is a scope violation: "
                f"remand {branch} to its repair flow",
            )
            break
        if push:
            pushed = _git(plane, "push", "origin", target)
            if pushed.returncode != 0:
                whole = False
                report.record(
                    "integrate", node_id, "FAILED", f"push rejected: {pushed.stderr.strip()}"
                )
                break
        report.record("integrate", node_id, "INTEGRATED", f"merged {head[:7]} --no-ff")
    return whole


def validate_round(
    plane: Any,
    round_: Round,
    report: RoundReport,
    *,
    owner: str,
    runner: Callable[[], tuple[bool, str]],
    lease_minutes: int = 60,
) -> None:
    """Run the round's one leased repository-wide gate, then always release."""

    anchor = round_.nodes[0]
    plane.acquire_global_validation_lease(anchor, owner, lease_minutes=lease_minutes)
    try:
        passed, summary = runner()
    finally:
        plane.release_global_validation_lease(anchor, owner)
    report.record(
        "validate", anchor, "PASSED" if passed else "FAILED", summary
    )


def default_validation_runner(repo_root: Path) -> Callable[[], tuple[bool, str]]:
    def run() -> tuple[bool, str]:
        completed = subprocess.run(
            ("python", "-m", "unittest", "discover", "-s", "tests"),
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        tail = (completed.stderr or completed.stdout).strip().splitlines()
        return completed.returncode == 0, tail[-1] if tail else "no test output"

    return run


def classify_blocker(text: str) -> str:
    """Classify a blocker by what authority its repair would need."""

    lowered = text.lower()
    if any(marker in lowered for marker in _SEALED_MARKERS):
        return "CLASS_C"
    if any(marker in lowered for marker in _STALE_MARKERS):
        return "CLASS_B"
    return "CLASS_A"


def _last_blocker(plane: Any, node_id: str) -> str | None:
    path = Path(plane.blockers_dir) / f"{node_id}.jsonl"
    if not path.is_file():
        return None
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return lines[-1] if lines else None


def triage_round(
    plane: Any,
    nodes: Sequence[str],
    report: RoundReport,
    *,
    resolve_stale: bool = True,
) -> None:
    """Classify each node's blocker and resolve only the mechanical class."""

    for node_id in nodes:
        packet = _last_blocker(plane, node_id)
        if packet is None:
            continue
        if getattr(plane, "blockers_fully_resolved", lambda _node: False)(node_id):
            # Every recorded cause carries a verified resolution; the ledger's
            # last line is a resolution event, not a live blocker.
            continue
        verdict = classify_blocker(packet)
        if verdict == "CLASS_B" and resolve_stale:
            outcome, resolved = _resolve_stale_claim(plane, node_id)
            if resolved is not None:
                report.record("triage", node_id, outcome, resolved)
                continue
        report.record(
            "triage",
            node_id,
            verdict,
            {
                "CLASS_A": "runbook may contradict real source; verify and correct the "
                "runbook, then re-dispatch",
                "CLASS_B": "stale artifact blocks a lawful re-claim; retire it through "
                "the controller",
                "CLASS_C": "sealed or external authority; record and continue other rounds",
            }[verdict],
        )


def _resolve_stale_claim(plane: Any, node_id: str) -> tuple[str, str | None]:
    """Retire a dead worker's defunct claim ref, or explain why it must wait.

    Returns ``(outcome, detail)`` so a refusal is reported as RETAINED — a
    refusal used to be recorded as REPAIRED, which read as progress while the
    node stayed wedged.
    """

    policy = healing.load_policy(plane.ap_root)
    if not policy["enabled"]:
        return ("RETAINED", None)
    branch = str(plane.node(node_id).get("branch"))
    head = plane.remote_branch_sha(branch)
    if head is None:
        return ("RETAINED", None)
    _git(plane, "fetch", "origin", f"refs/heads/{branch}")
    record = plane.remote_claim_record(head)
    if not isinstance(record, Mapping):
        return ("RETAINED", None)
    try:
        released = plane.reap_defunct_remote_claim(
            node_id,
            actor="autopilot:round-driver",
            reason="round driver retired a dead worker's defunct claim",
            stall_minutes=int(policy["claim_stall_minutes"]),
        )
    except Exception as error:  # refusal is information, not a driver failure
        return ("RETAINED", f"claim retained: {error}")
    if released.get("outcome") == "absent":
        return ("RETAINED", None)
    proof = released.get("proof", {})
    return (
        "REPAIRED",
        f"retired defunct claim {str(head)[:7]} for {released.get('owner')} "
        f"({proof.get('kind', 'expired')})",
    )


def drive_round(
    plane: Any,
    *,
    actor: str,
    max_sessions: int = 8,
    push: bool = True,
    validate: bool = True,
    heal: bool = True,
    runner: Callable[[], tuple[bool, str]] | None = None,
) -> dict[str, Any]:
    """Advance the current round as far as evidence allows, then report.

    With ``heal`` (the default) the driver repairs what a careful operator was
    always entitled to repair by hand — a missing reconciliation, a defunct
    claim, a dead worker's stalled branch, an expired validation lease — and
    the result carries a ``disposition`` plus ``wake_at`` so the caller knows
    whether looping again can change anything, and if not, until when.
    """

    report = RoundReport()

    def finish(disposition: str, wake_at: str | None = None, **extra: Any) -> dict[str, Any]:
        result = report.to_dict()
        result["disposition"] = disposition
        result["wake_at"] = wake_at
        result.update(extra)
        return result

    status = plane.status()
    if status.get("reconciliation_required"):
        # Every verdict is untrustworthy until the session reconciles: nodes read
        # RECONCILIATION_REQUIRED rather than COMPLETE, so round selection would
        # walk back to rounds that were integrated long ago.
        if heal:
            ok, detail = healing.reconcile_with_snapshot(plane, actor=actor)
            report.record(
                "heal", None, "RECONCILED" if ok else "FAILED", detail
            )
            if ok:
                status = plane.status()
        if status.get("reconciliation_required"):
            report.record(
                "select",
                None,
                "RECONCILE_REQUIRED",
                "run: python .autopilot/bin/github_snapshot.py --reconcile --actor "
                f"{actor} — no round is selectable until then",
            )
            report.blocked = True
            return finish("RECONCILE_REQUIRED")
    round_ = select_round(plane, status, max_sessions=max_sessions)
    if round_ is None:
        report.record("select", None, "QUIESCENT", "every compiled round is complete")
        return finish("QUIESCENT")
    report.round_id = round_.round_id
    report.nodes = round_.nodes
    report.record(
        "select", None, "SELECTED", f"{round_.round_id} level {round_.level}: {round_.reason}"
    )
    # --no-heal means observe-only everywhere: triage classification still runs,
    # but its mechanical claim repairs are healing actions and obey the flag.
    triage_round(plane, round_.nodes, report, resolve_stale=heal)
    whole = integrate_round(plane, round_, report, push=push)
    if not whole:
        report.record(
            "validate", None, "SKIPPED", "the wave is not whole; validation gates a full round"
        )
        if not heal:
            return finish("PENDING")
        healed = healing.heal_round(
            plane, actor=actor, nodes=round_.nodes, allow_push=push
        )
        for action in healed.get("actions", []):
            report.record(
                "heal",
                action.get("node_id"),
                str(action.get("outcome")),
                f"{action.get('kind')}: {action.get('detail')}",
            )
        disposition = str(healed.get("disposition"))
        if disposition == "QUIESCENT":
            # The healer found nothing to repair, but this round is not whole:
            # QUIESCENT here would read as plan-complete, which it is not.
            disposition = "PENDING"
        report.record(
            "heal",
            None,
            disposition,
            "state changed; run run-round again"
            if disposition == "HEALED"
            else "waiting is provably useful until "
            + str(healed.get("wake_at") or "new evidence arrives"),
        )
        return finish(disposition, healed.get("wake_at"), healing=healed)
    if not validate:
        report.record("validate", None, "SKIPPED", "validation disabled by request")
        return finish("ROUND_INTEGRATED")
    if heal:
        try:
            broken = plane.break_expired_validation_lease(actor=actor)
        except Exception:  # a live lease is not the driver's to break
            broken = None
        if broken is not None:
            report.record(
                "heal",
                None,
                "REPAIRED",
                f"archived expired validation lease of {broken.get('owner')}",
            )
    validate_round(
        plane,
        round_,
        report,
        owner=actor,
        runner=runner or default_validation_runner(Path(plane.repo_root)),
    )
    passed = any(
        step.phase == "validate" and step.outcome == "PASSED" for step in report.steps
    )
    return finish("ROUND_COMPLETE" if passed else "VALIDATION_FAILED")
