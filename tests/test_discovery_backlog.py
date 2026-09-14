import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hive_mind_os.discovery_backlog import BacklogCandidate, DiscoveryBacklog


class DiscoveryBacklogTests(unittest.TestCase):
    def candidate(self, idea="idea-1", impact=10):
        return BacklogCandidate(
            idea,
            ("atomic claim",),
            impact,
            "observable acceptance",
            2,
            0.2,
            dissent=("no-change remains an alternative",),
        )

    def test_candidates_survive_restart_and_selection_is_deterministic(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)
            first = DiscoveryBacklog(path)
            first.add(self.candidate("lower", 2))
            first.add(self.candidate("higher", 10))
            first.close()
            resumed = DiscoveryBacklog(path)
            try:
                self.assertEqual(resumed.select().selected_ids, ("higher",))
            finally:
                resumed.close()

    def test_same_idea_cannot_be_rebound_to_different_evidence(self):
        backlog = DiscoveryBacklog()
        backlog.add(self.candidate())
        with self.assertRaises(ValueError):
            backlog.add(self.candidate(impact=99))


if __name__ == "__main__":
    unittest.main()
