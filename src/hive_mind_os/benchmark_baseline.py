"""Pinned single-shot comparator for P13."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .autonomy import AutonomyBudget
from .benchmark_corpus import LaneTask
from .receipts import sha256_digest

_GOOD_FIX = b"def increment(value: int) -> int:\n    return value + 1\n"


@dataclass(frozen=True, slots=True)
class BaselineExecution:
    status: str
    identity: str
    report: dict[str, object]
    receipts: tuple[dict[str, object], ...]


class BaselineAgent:
    """One patch attempt, with no role decomposition and no self-verification."""

    identity = "p13-pinned-naive-baseline-v1"
    version = "1"

    def execute(
        self,
        task: LaneTask,
        budget: AutonomyBudget,
        workspace: Path,
    ) -> BaselineExecution:
        allowance = budget.issue_allowance()
        attempted = task.task_id in {
            "failing-test-fix",
            "missing-edge-case",
            "doc-code-drift",
            "dependency-free-refactor",
        }
        if attempted:
            destination = workspace / "tiny_pkg" / "maths.py"
            destination.write_bytes(_GOOD_FIX)
        budget.consume(allowance, tool_calls=1, compute_units=1.0)
        action_digest = sha256_digest(
            (task.task_id + "\0" + ("write" if attempted else "no-change")).encode()
        )
        receipt = {
            "schema_version": 1,
            "actor_id": self.identity,
            "action_kind": "single-shot-patch",
            "action_digest": action_digest,
            "result": "succeeded",
        }
        return BaselineExecution(
            status="succeeded",
            identity=self.identity,
            report={
                "schema_version": 1,
                "task_id": task.task_id,
                "strategy": "single-shot-scripted-patch",
                "attempted_patch": attempted,
                "verification_performed": False,
            },
            receipts=(receipt,),
        )


__all__ = ["BaselineAgent", "BaselineExecution"]
