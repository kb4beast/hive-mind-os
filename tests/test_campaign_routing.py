import unittest

from hive_mind_os.campaign_routing import ModelRoute, RouteStatus, select_route

D = "sha256:" + "a" * 64


class CampaignRoutingTests(unittest.TestCase):
    def test_deterministic_work_uses_no_model(self):
        self.assertEqual(
            select_route(
                required_capabilities=(),
                permitted_policy_digest=D,
                routes=(),
                deterministic=True,
            ).status,
            RouteStatus.NO_MODEL,
        )

    def test_policy_mismatch_blocks(self):
        route = ModelRoute("provider", "model", "low", D, ("build",), 1, 10)
        self.assertEqual(
            select_route(
                required_capabilities=("build",),
                permitted_policy_digest="sha256:" + "b" * 64,
                routes=(route,),
            ).status,
            RouteStatus.BLOCKED_CAPABILITY,
        )
