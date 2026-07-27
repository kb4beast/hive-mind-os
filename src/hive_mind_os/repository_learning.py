from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


def _bounded(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class RepositoryCandidate:
    """Public repository signal record used by the autonomous learning scout."""

    full_name: str
    source_uri: str
    license_spdx: str | None
    relevance: float
    activity: float
    engineering_quality: float
    security_posture: float
    documentation_quality: float
    community_signal: float
    provenance_complete: bool = True

    def __post_init__(self) -> None:
        if not self.full_name.strip() or not self.source_uri.strip():
            raise ValueError("repository identity and source URI are required")
        for name in (
            "relevance",
            "activity",
            "engineering_quality",
            "security_posture",
            "documentation_quality",
            "community_signal",
        ):
            _bounded(name, getattr(self, name))

    @property
    def strength_score(self) -> float:
        score = (
            0.30 * self.relevance
            + 0.20 * self.engineering_quality
            + 0.15 * self.activity
            + 0.15 * self.security_posture
            + 0.10 * self.documentation_quality
            + 0.10 * self.community_signal
        )
        return round(score, 6)


class RepositoryScout:
    """Ranks strong learning sources while enforcing license and provenance gates."""

    def __init__(
        self,
        allowed_licenses: Iterable[str] = (
            "Apache-2.0",
            "BSD-2-Clause",
            "BSD-3-Clause",
            "MIT",
            "MPL-2.0",
        ),
        minimum_relevance: float = 0.50,
    ) -> None:
        _bounded("minimum_relevance", minimum_relevance)
        self.allowed_licenses = frozenset(allowed_licenses)
        self.minimum_relevance = minimum_relevance

    def eligible(self, candidate: RepositoryCandidate) -> bool:
        return (
            candidate.provenance_complete
            and candidate.license_spdx in self.allowed_licenses
            and candidate.relevance >= self.minimum_relevance
            and candidate.source_uri.startswith(("https://", "http://"))
        )

    def rank(self, candidates: Iterable[RepositoryCandidate]) -> tuple[RepositoryCandidate, ...]:
        eligible = (candidate for candidate in candidates if self.eligible(candidate))
        return tuple(
            sorted(
                eligible,
                key=lambda item: (-item.strength_score, item.full_name.casefold()),
            )
        )


@dataclass(frozen=True, slots=True)
class CommitState:
    sha: str
    tree_hash: str
    parent_shas: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.sha.strip() or not self.tree_hash.strip():
            raise ValueError("commit SHA and tree hash are required")


@dataclass(frozen=True, slots=True)
class LeakageDecision:
    allowed: bool
    leaked_shas: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RepositoryLearningEpisode:
    """One historical prediction episode with target and future commits hidden."""

    target: CommitState
    visible_history: tuple[CommitState, ...]
    hidden_commits: tuple[CommitState, ...]

    @property
    def observable_base(self) -> CommitState | None:
        return self.visible_history[-1] if self.visible_history else None

    def validate_access(self, accessed_shas: Iterable[str]) -> LeakageDecision:
        hidden = {commit.sha for commit in self.hidden_commits}
        leaked = tuple(sorted(set(accessed_shas) & hidden))
        return LeakageDecision(not leaked, leaked)

    def require_no_leakage(self, accessed_shas: Iterable[str]) -> None:
        decision = self.validate_access(accessed_shas)
        if not decision.allowed:
            raise RuntimeError(
                "point-in-time leakage detected: " + ", ".join(decision.leaked_shas)
            )


class RepositoryLearningCurriculum:
    """Builds a first-commit-forward curriculum without target or future leakage."""

    def __init__(self, commits: Iterable[CommitState]) -> None:
        ordered = tuple(commits)
        if not ordered:
            raise ValueError("repository curriculum requires at least one commit")
        shas = [commit.sha for commit in ordered]
        if len(shas) != len(set(shas)):
            raise ValueError("repository history contains duplicate commit SHAs")

        observed: set[str] = set()
        for commit in ordered:
            missing_parents = set(commit.parent_shas) - observed
            if missing_parents:
                raise ValueError(
                    f"commit {commit.sha} appears before parent(s): "
                    + ", ".join(sorted(missing_parents))
                )
            observed.add(commit.sha)
        self._commits = ordered

    def episodes(self) -> tuple[RepositoryLearningEpisode, ...]:
        return tuple(
            RepositoryLearningEpisode(
                target=target,
                visible_history=self._commits[:index],
                hidden_commits=self._commits[index:],
            )
            for index, target in enumerate(self._commits)
        )


@dataclass(frozen=True, slots=True)
class PatternLesson:
    """An abstract, provenance-bearing lesson rather than copied source code."""

    source_repository: str
    source_commit_sha: str
    source_uri: str
    license_spdx: str
    pattern: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        required = (
            self.source_repository,
            self.source_commit_sha,
            self.source_uri,
            self.license_spdx,
            self.pattern,
        )
        if any(not value.strip() for value in required):
            raise ValueError("pattern lessons require complete source provenance")
        if not self.evidence_refs:
            raise ValueError("pattern lessons require supporting evidence")
        if not self.source_uri.startswith(("https://", "http://")):
            raise ValueError("pattern lesson source URI must be network-addressable")
