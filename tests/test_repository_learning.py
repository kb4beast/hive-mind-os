import unittest

from hive_mind_os.repository_learning import (
    CommitState,
    PatternLesson,
    RepositoryCandidate,
    RepositoryLearningCurriculum,
    RepositoryScout,
)


class RepositoryLearningTests(unittest.TestCase):
    def candidate(
        self,
        name: str,
        *,
        license_spdx: str | None = "MIT",
        relevance: float = 0.9,
        quality: float = 0.9,
        provenance: bool = True,
    ) -> RepositoryCandidate:
        return RepositoryCandidate(
            full_name=name,
            source_uri=f"https://github.com/{name}",
            license_spdx=license_spdx,
            relevance=relevance,
            activity=0.8,
            engineering_quality=quality,
            security_posture=0.7,
            documentation_quality=0.8,
            community_signal=0.8,
            provenance_complete=provenance,
        )

    def test_scout_ranks_strong_sources_and_filters_unsafe_sources(self) -> None:
        scout = RepositoryScout(minimum_relevance=0.6)
        strong = self.candidate("org/strong", quality=0.95)
        weaker = self.candidate("org/weaker", quality=0.65)
        unknown_license = self.candidate("org/unknown", license_spdx=None)
        incompatible = self.candidate("org/incompatible", license_spdx="AGPL-3.0")
        incomplete = self.candidate("org/incomplete", provenance=False)

        ranked = scout.rank((weaker, incompatible, strong, unknown_license, incomplete))
        self.assertEqual(ranked, (strong, weaker))

    def test_curriculum_starts_at_first_commit_and_hides_target_and_future(self) -> None:
        commits = (
            CommitState("a", "tree-a"),
            CommitState("b", "tree-b", ("a",)),
            CommitState("c", "tree-c", ("b",)),
        )
        episodes = RepositoryLearningCurriculum(commits).episodes()

        self.assertEqual(len(episodes), 3)
        self.assertEqual(episodes[0].target.sha, "a")
        self.assertEqual(episodes[0].visible_history, ())
        self.assertEqual(tuple(item.sha for item in episodes[0].hidden_commits), ("a", "b", "c"))
        self.assertEqual(tuple(item.sha for item in episodes[1].visible_history), ("a",))
        self.assertEqual(tuple(item.sha for item in episodes[1].hidden_commits), ("b", "c"))
        self.assertEqual(episodes[2].observable_base.sha, "b")

    def test_access_to_target_or_future_commit_is_detected(self) -> None:
        commits = (
            CommitState("a", "tree-a"),
            CommitState("b", "tree-b", ("a",)),
            CommitState("c", "tree-c", ("b",)),
        )
        episode = RepositoryLearningCurriculum(commits).episodes()[1]
        allowed = episode.validate_access(("a",))
        leaked = episode.validate_access(("a", "b", "c"))

        self.assertTrue(allowed.allowed)
        self.assertFalse(leaked.allowed)
        self.assertEqual(leaked.leaked_shas, ("b", "c"))
        with self.assertRaises(RuntimeError):
            episode.require_no_leakage(("b",))

    def test_non_topological_history_is_rejected(self) -> None:
        commits = (
            CommitState("b", "tree-b", ("a",)),
            CommitState("a", "tree-a"),
        )
        with self.assertRaises(ValueError):
            RepositoryLearningCurriculum(commits)

    def test_pattern_lesson_requires_provenance_and_evidence(self) -> None:
        lesson = PatternLesson(
            source_repository="org/repo",
            source_commit_sha="abc123",
            source_uri="https://github.com/org/repo/commit/abc123",
            license_spdx="MIT",
            pattern="separate probabilistic planning from deterministic execution",
            evidence_refs=("evaluation:42",),
        )
        self.assertEqual(lesson.source_commit_sha, "abc123")

        with self.assertRaises(ValueError):
            PatternLesson(
                source_repository="org/repo",
                source_commit_sha="abc123",
                source_uri="https://github.com/org/repo/commit/abc123",
                license_spdx="MIT",
                pattern="unsupported",
                evidence_refs=(),
            )


if __name__ == "__main__":
    unittest.main()
