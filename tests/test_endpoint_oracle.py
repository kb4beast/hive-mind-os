import unittest
from dataclasses import replace
from tempfile import TemporaryDirectory

from hive_mind_os.endpoint_oracle import (
    CustodyError,
    EndpointSeal,
    EndpointSealStore,
    reject_changed_candidate,
)


class EndpointOracleTests(unittest.TestCase):
    def seal(self):
        return EndpointSeal(
            "episode-1",
            "sha256:" + "1" * 64,
            "sha256:" + "2" * 64,
            "sha256:" + "3" * 64,
            "sha256:" + "4" * 64,
            "sha256:" + "5" * 64,
            "sha256:" + "6" * 64,
            "sha256:" + "7" * 64,
            "learner",
            "independent-evaluator",
            "2026-09-14T00:00:00Z",
        )

    def test_seal_digest_round_trips_and_candidate_is_immutable(self):
        base = self.seal()
        sealed = replace(base, seal_digest=base.seal())
        with TemporaryDirectory() as directory:
            store = EndpointSealStore(f"{directory}/seals.json")
            store.seal_once(sealed)
            self.assertEqual(store.get("episode-1"), sealed)
        with self.assertRaises(CustodyError):
            reject_changed_candidate(sealed, "sha256:" + "9" * 64)

    def test_learner_cannot_evaluate_itself(self):
        with self.assertRaises(CustodyError):
            replace(self.seal(), evaluator_id="learner")


if __name__ == "__main__":
    unittest.main()
