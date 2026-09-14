import unittest
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from hive_mind_os.delivery_broker import (
    ArtifactKind,
    DeliveryBroker,
    DeliveryGrant,
    DeliveryRequest,
    DeliveryResult,
    DeliveryState,
)
from hive_mind_os.lesson_delivery import (
    DurableDeliveryLedger,
    LessonDeliveryCoordinator,
    LessonDeliveryObligation,
    ObligationState,
)

D = "sha256:" + "a" * 64
TARGET = "https://example.test/hive/lessons"


class Transport:
    def __init__(self):
        self.effects = 0
        self.observed: DeliveryResult | None = None

    def push(self, branch, commit):
        self.effects += 1
        return commit

    def find_or_create_draft(self, branch, base, title, body):
        self.effects += 1
        return "draft-1"

    def observe(self, request):
        return self.observed


class LessonDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.draft = b"document_status: DRAFT\nprocessing_state: REVIEWED_DRAFT\n"
        self.digest = "sha256:" + sha256(self.draft).hexdigest()

    def obligation(self, **changes):
        values: dict[str, Any] = {
            "external_mission_id": "mission-1",
            "origin_mission_token": "opaque-mission",
            "subject_id": "tenant-a:repo-a",
            "safe_draft_digest": self.digest,
            "local_artifact_path": ".hivemind/lessons/drafts/mission-1.md",
            "local_commit_sha": "b" * 40,
            "upstream_repository_id": TARGET,
            "upstream_path": "docs/lessons/drafts/draft-1.md",
            "export_authority_digest": D,
            "delivery_idempotency_key": "lesson-mission-1",
        }
        values.update(changes)
        return LessonDeliveryObligation(**values)

    def request(self):
        return DeliveryRequest(
            "request-1",
            "lesson-mission-1",
            "tenant-a",
            "b" * 40,
            D,
            D,
            TARGET,
            "main",
            "codex/lessons/mission-1",
            "lesson-grant",
            ArtifactKind.LESSONS_ONLY,
            self.digest,
            "lesson-mission-1",
            ("docs/lessons/drafts/draft-1.md",),
        )

    def coordinator(self, root, transport):
        ledger = DurableDeliveryLedger(root / "ledger.json")
        broker = DeliveryBroker(
            transport,
            grants={
                "lesson-grant": DeliveryGrant(
                    "lesson-grant",
                    "tenant-a",
                    TARGET,
                    "main",
                    "codex/lessons/",
                    (ArtifactKind.LESSONS_ONLY,),
                )
            },
            state_path=root / "broker.json",
        )
        return LessonDeliveryCoordinator(ledger, broker)

    def test_one_durable_obligation_retains_and_publishes_draft_only(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            transport = Transport()
            coordinator = self.coordinator(root, transport)
            retained = coordinator.retain(
                self.obligation(), target_root=root / "target", safe_draft=self.draft
            )
            self.assertEqual(retained.obligation_state, ObligationState.RETAINED_DRAFT)
            published = coordinator.publish(retained, self.request())
            self.assertEqual(published.obligation_state, ObligationState.DRAFT_PR_OPEN)
            self.assertEqual(transport.effects, 2)
            self.assertTrue((root / "target" / retained.local_artifact_path).is_file())
            restored = DurableDeliveryLedger(root / "ledger.json").get(
                retained.subject_id, retained.external_mission_id
            )
            self.assertEqual(restored, published)

    def test_missing_destination_is_a_retained_typed_blocker(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            coordinator = self.coordinator(root, Transport())
            retained = coordinator.retain(
                self.obligation(upstream_repository_id=None, upstream_path=None),
                target_root=root / "target",
                safe_draft=self.draft,
            )
            blocked = coordinator.publish(retained, self.request())
            self.assertEqual(
                blocked.obligation_state, ObligationState.BLOCKED_EXPORT_DESTINATION
            )

    def test_uncertain_effect_reconciles_without_repeating_publication(self):
        class UncertainTransport(Transport):
            def find_or_create_draft(self, branch, base, title, body):
                self.effects += 1
                raise TimeoutError("response lost")

        with TemporaryDirectory() as directory:
            root = Path(directory)
            transport = UncertainTransport()
            coordinator = self.coordinator(root, transport)
            retained = coordinator.retain(
                self.obligation(), target_root=root / "target", safe_draft=self.draft
            )
            retryable = coordinator.publish(retained, self.request())
            self.assertEqual(
                retryable.obligation_state, ObligationState.EXPORT_FAILED_RETRYABLE
            )
            effect_count = transport.effects
            transport.observed = DeliveryResult(
                DeliveryState.PUBLISHED,
                self.request_digest(),
                "b" * 40,
                "draft-1",
            )
            published = coordinator.publish(retryable, self.request(), reconcile=True)
            self.assertEqual(published.obligation_state, ObligationState.DRAFT_PR_OPEN)
            self.assertEqual(transport.effects, effect_count)

    def request_digest(self):
        from hive_mind_os.brain_kernel.canonical import canonical_digest

        return canonical_digest(self.request())


if __name__ == "__main__":
    unittest.main()
