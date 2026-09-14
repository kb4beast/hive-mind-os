import tempfile
import unittest
from pathlib import Path

from hive_mind_os.delivery_broker import (
    ArtifactKind,
    DeliveryBroker,
    DeliveryGrant,
    DeliveryRequest,
    DeliveryState,
)


class Transport:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def push(self, branch, commit):
        self.calls.append(("push", branch, commit))
        if self.fail:
            raise TimeoutError()
        return commit

    def find_or_create_draft(self, branch, base, title, body):
        self.calls.append(("pr", branch, base))
        return "1"


def request(key="key", tenant="tenant.one"):
    return DeliveryRequest(
        "request.one", "package.one", tenant, "a" * 40, "b" * 40,
        "sha256:" + "c" * 64, "owner/repo", "main", "codex/run",
        "grant.one", ArtifactKind.APPLICATION, "sha256:" + "d" * 64, key,
        ("src/a.py",),
    )


class DeliveryBrokerDurabilityTests(unittest.TestCase):
    def grant(self):
        return DeliveryGrant(
            "grant.one", "tenant.one", "owner/repo", "main", "codex/",
            (ArtifactKind.APPLICATION,),
        )

    def test_grant_is_scoped_and_result_survives_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "delivery.json"
            transport = Transport()
            broker = DeliveryBroker(
                transport, grants={"grant.one": self.grant()}, state_path=state
            )
            self.assertEqual(broker.prepare(request()).state, DeliveryState.PUBLISHED)
            restarted = DeliveryBroker(
                Transport(), grants={"grant.one": self.grant()}, state_path=state
            )
            self.assertEqual(restarted.prepare(request()).state, DeliveryState.PUBLISHED)
            self.assertEqual(restarted.transport.calls, [])
            self.assertEqual(
                restarted.prepare(request(tenant="tenant.two")).state,
                DeliveryState.BLOCKED,
            )

    def test_uncertain_effect_is_durable_and_not_retried(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "delivery.json"
            first = Transport(True)
            broker = DeliveryBroker(
                first, grants={"grant.one": self.grant()}, state_path=state
            )
            self.assertEqual(
                broker.prepare(request()).state, DeliveryState.RECONCILIATION_REQUIRED
            )
            second = Transport()
            restarted = DeliveryBroker(
                second, grants={"grant.one": self.grant()}, state_path=state
            )
            self.assertEqual(
                restarted.prepare(request()).state,
                DeliveryState.RECONCILIATION_REQUIRED,
            )
            self.assertEqual(second.calls, [])


if __name__ == "__main__":
    unittest.main()
