import tempfile
import unittest

from hive_mind_os.campaign_service import (
    CampaignService,
    CampaignServiceConfig,
    CampaignStatus,
)
from hive_mind_os.scheduler import ManualClock, Scheduler


class CampaignServiceDurabilityTests(unittest.TestCase):
    def test_scopes_campaign_repository_and_uses_configured_capacity(self):
        with tempfile.TemporaryDirectory() as temp:
            clock = ManualClock(100)
            scheduler = Scheduler(temp + "/queue", clock=clock)
            for number in range(3):
                scheduler.enqueue(
                    "build",
                    {"repository_id": "repo.one", "number": number},
                    mission_id="mission.one",
                )
            scheduler.enqueue(
                "build", {"repository_id": "repo.one"}, mission_id="mission.other"
            )
            calls = []
            service = CampaignService(
                CampaignServiceConfig(
                    "mission.one",
                    "config.one",
                    ("repo.one",),
                    "sha256:" + "a" * 64,
                    concurrency=2,
                    daily_allowance=2,
                    job_kinds=("build",),
                ),
                scheduler,
                temp + "/state",
                executor=lambda job: calls.append(job.id) or "ok",
                clock=clock.now,
            )
            self.assertEqual(service.run_once().status, CampaignStatus.PROGRESSED)
            self.assertEqual(len(calls), 2)
            self.assertEqual(service.run_once().status, CampaignStatus.BLOCKED)
            self.assertIsNotNone(
                scheduler.claim("other", mission_id="mission.other")
            )
            service.close()
            scheduler.close()

    def test_missing_executor_and_wrong_repository_never_succeed(self):
        with tempfile.TemporaryDirectory() as temp:
            clock = ManualClock(0)
            scheduler = Scheduler(temp + "/queue", clock=clock)
            scheduler.enqueue(
                "build", {"repository_id": "repo.one"}, mission_id="mission.one"
            )
            service = CampaignService(
                CampaignServiceConfig(
                    "mission.one", "config", ("repo.one",), "sha256:" + "b" * 64
                ),
                scheduler,
                temp + "/state",
                clock=clock.now,
            )
            self.assertEqual(service.run_once().status, CampaignStatus.BLOCKED)
            service.close()
            scheduler.close()

    def test_uncertain_effect_is_observed_and_adopted_without_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            clock = ManualClock(0)
            scheduler = Scheduler(temp + "/queue", clock=clock)
            job = scheduler.enqueue(
                "build", {"repository_id": "repo.one"}, mission_id="mission.one"
            )
            calls = []

            def uncertain(_job):
                calls.append("called")
                raise ConnectionError("response lost")

            service = CampaignService(
                CampaignServiceConfig(
                    "mission.one", "config", ("repo.one",), "sha256:" + "c" * 64
                ),
                scheduler,
                temp + "/state",
                executor=uncertain,
                clock=clock.now,
            )
            self.assertEqual(service.run_once().status, CampaignStatus.BLOCKED)
            service.reconcile_effect(job.id, observed_result="receipt.one")
            clock.advance(2)
            self.assertEqual(service.run_once().status, CampaignStatus.PROGRESSED)
            self.assertEqual(calls, ["called"])
            service.close()
            scheduler.close()


if __name__ == "__main__":
    unittest.main()
