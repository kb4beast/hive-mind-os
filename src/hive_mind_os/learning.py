from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Iterator


@dataclass(frozen=True, slots=True)
class CommitSnapshot:
    sha: str
    committed_at: datetime
    changed_paths: tuple[str, ...]
    message: str = ""


@dataclass(frozen=True, slots=True)
class ReplayFrame:
    target: CommitSnapshot
    visible_history: tuple[CommitSnapshot, ...]


class PointInTimeReplay:
    """Yields commit frames without exposing future commits to the learner."""

    def __init__(self, commits: Iterable[CommitSnapshot]) -> None:
        ordered = sorted(commits, key=lambda item: (item.committed_at, item.sha))
        shas = [item.sha for item in ordered]
        if len(shas) != len(set(shas)):
            raise ValueError("commit history contains duplicate SHAs")
        self._commits = tuple(ordered)

    def frames(self) -> Iterator[ReplayFrame]:
        for index, target in enumerate(self._commits):
            # The target commit is the outcome. The learner sees only prior state.
            yield ReplayFrame(target=target, visible_history=self._commits[:index])


@dataclass(frozen=True, slots=True)
class EvaluationSummary:
    runs: int
    successes: int
    regressions: int

    @property
    def success_rate(self) -> float:
        return self.successes / self.runs if self.runs else 0.0

    @property
    def regression_rate(self) -> float:
        return self.regressions / self.runs if self.runs else 1.0


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    promote: bool
    reason: str


class LearningPromotionGate:
    """Prevents unverified self-modification from becoming the champion."""

    def __init__(
        self,
        minimum_runs: int = 20,
        minimum_success_rate: float = 0.80,
        maximum_regression_rate: float = 0.05,
    ) -> None:
        self.minimum_runs = minimum_runs
        self.minimum_success_rate = minimum_success_rate
        self.maximum_regression_rate = maximum_regression_rate

    def evaluate(self, candidate: EvaluationSummary, champion: EvaluationSummary) -> PromotionDecision:
        if candidate.runs < self.minimum_runs:
            return PromotionDecision(False, "candidate lacks enough independent evaluations")
        if candidate.success_rate < self.minimum_success_rate:
            return PromotionDecision(False, "candidate success rate is below the minimum")
        if candidate.regression_rate > self.maximum_regression_rate:
            return PromotionDecision(False, "candidate regression rate exceeds the budget")
        if candidate.success_rate <= champion.success_rate:
            return PromotionDecision(False, "candidate did not beat the current champion")
        return PromotionDecision(True, "candidate passed evidence and regression gates")
