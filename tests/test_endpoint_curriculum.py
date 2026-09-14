import unittest

from hive_mind_os.endpoint_curriculum import (
    EndpointEpisodeManifest,
    EndpointError,
    EpisodeState,
)


class EndpointCurriculumTests(unittest.TestCase):
    def manifest(self, **changes):
        values = {
            "episode_id": "episode-1",
            "source_record_id": "source-1",
            "mode": "endpoint_reconstruction",
            "first_commit": "a" * 40,
            "first_tree_digest": "sha256:" + "1" * 64,
            "final_commit": "b" * 40,
            "final_tree_digest": "sha256:" + "2" * 64,
            "readme_digest": None,
            "readme_origin_commit": None,
            "brief_visibility": "owner_authored_brief",
            "repository_family_id": "family-a",
            "dataset_split": "promotion_holdout",
            "dependency_manifest_digest": "sha256:" + "3" * 64,
            "fixture_manifest_digest": "sha256:" + "4" * 64,
            "source_dispositions": ("adopt",),
            "obligation_refs": (),
        }
        values.update(changes)
        return EndpointEpisodeManifest(**values)

    def test_distinct_endpoints_remain_admitted(self):
        self.assertEqual(self.manifest().state, EpisodeState.REGISTERED)

    def test_equal_endpoint_identity_is_degenerate(self):
        manifest = self.manifest(final_commit="a" * 40)
        self.assertEqual(manifest.state, EpisodeState.DEGENERATE_EPISODE)

    def test_unknown_fields_and_invalid_brief_are_rejected(self):
        with self.assertRaises(EndpointError):
            self.manifest(brief_visibility="final_readme")
        with self.assertRaises(EndpointError):
            EndpointEpisodeManifest.from_dict(
                {**self.manifest().to_dict(), "learner_hint": "future target"}
            )


if __name__ == "__main__":
    unittest.main()
