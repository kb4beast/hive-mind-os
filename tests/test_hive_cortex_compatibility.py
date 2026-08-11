from __future__ import annotations

import unittest
from types import SimpleNamespace

from hive_mind_os.cortex.compatibility import (
    AdapterMode,
    AuthorityPath,
    AutonomousBrainAdapter,
    CompatibilityError,
    CompatibilityObservation,
    LegacyWorkerAdapter,
    MissionLoopAdapter,
    ParityProbe,
    RepositoryMissionAdapter,
    RollbackRouter,
    default_compatibility_registry,
)
from hive_mind_os.mission_loop import BuilderAction


class HiveCortexCompatibilityTests(unittest.TestCase):
    def test_compatibility_adapter_tests(self) -> None:
        registry = default_compatibility_registry()
        self.assertEqual(
            {descriptor.entry_point for descriptor in registry.descriptors()},
            {"RepositoryMission", "MissionLoop", "AutonomousBrain", "legacy workers"},
        )
        for blocker in registry.retirement_blockers():
            self.assertTrue(blocker.reason)
            self.assertTrue(blocker.required_evidence)
            self.assertTrue(blocker.rollback_ref.startswith("rollback:"))

        request = RepositoryMissionAdapter().request("MISSION-compat", "run", {"pin": "abc"})
        self.assertEqual(request.authority_path, AuthorityPath.LEGACY)
        self.assertTrue(request.payload_digest.startswith("sha256:"))

        action_request = MissionLoopAdapter().translate_action(
            BuilderAction("search", {"query": "compatibility"})
        )
        self.assertEqual(action_request.operation, "search")

        run = AutonomousBrainAdapter().project_run(
            {"run_id": "AR-compat", "status": "prepared", "branch": "hive-mind/ar-compat"}
        )
        self.assertEqual(run.status, "prepared")

        job = SimpleNamespace(
            id="JOB-compat",
            kind="repository-mission",
            payload={"mission_id": "M-compat"},
            payload_digest="sha256:" + "1" * 64,
            state="ready",
            attempts=0,
            lease_owner=None,
            lease_expiry=None,
            mission_id="M-compat",
        )
        self.assertEqual(LegacyWorkerAdapter().project_job(job).status, "ready")

    def test_no_dual_write_tests(self) -> None:
        calls: list[str] = []
        router = RollbackRouter(
            lambda value: calls.append(f"legacy:{value}") or "legacy-result",
            lambda value: calls.append(f"canonical:{value}") or "canonical-result",
            rollback_ref="rollback:compatibility",
        )
        self.assertEqual(router.invoke("one"), "legacy-result")
        self.assertEqual(calls, ["legacy:one"])
        self.assertEqual(router.rollback().active, AdapterMode.LEGACY)

        legacy = CompatibilityObservation(
            "MissionLoop", "state", AuthorityPath.SHADOW, "succeeded", {"status": "succeeded"}, {"receipt": "r1"}
        )
        canonical = CompatibilityObservation(
            "MissionLoop", "state", AuthorityPath.SHADOW, "succeeded", {"status": "succeeded"}, {"receipt": "r1"}
        )
        verdict = ParityProbe().compare(legacy, canonical)
        router.qualify(verdict)
        self.assertEqual(router.route(AdapterMode.CANONICAL).active, AdapterMode.CANONICAL)
        self.assertEqual(router.invoke("two"), "canonical-result")
        self.assertEqual(calls, ["legacy:one", "canonical:two"])

    def test_parity_rejects_authority_effects(self) -> None:
        effectful = CompatibilityObservation(
            "RepositoryMission", "run", AuthorityPath.LEGACY, "succeeded", {}, {}, effect_count=1
        )
        shadow = CompatibilityObservation(
            "RepositoryMission", "run", AuthorityPath.SHADOW, "succeeded", {}, {}
        )
        with self.assertRaises(CompatibilityError):
            ParityProbe().compare(effectful, shadow)

    def test_rollback_routing_tests(self) -> None:
        router = RollbackRouter(lambda: "legacy", lambda: "canonical")
        with self.assertRaises(CompatibilityError):
            router.route(AdapterMode.CANONICAL)
        mismatch = ParityProbe().compare(
            CompatibilityObservation("AutonomousBrain", "run", AuthorityPath.SHADOW, "failed", {"status": "failed"}, {}),
            CompatibilityObservation("AutonomousBrain", "run", AuthorityPath.SHADOW, "succeeded", {"status": "succeeded"}, {}),
        )
        with self.assertRaises(CompatibilityError):
            router.qualify(mismatch)
        self.assertEqual(router.rollback().active, AdapterMode.LEGACY)


if __name__ == "__main__":
    unittest.main()
