import unittest

from hive_mind_os.campaign_context import CampaignContextError, CampaignContextRequest

D = "sha256:" + "e" * 64


class CampaignContextTests(unittest.TestCase):
    def test_handles_are_required_and_unique(self):
        with self.assertRaises(CampaignContextError):
            CampaignContextRequest("subject", D, "node", D, D, "builder", ("h", "h"))
