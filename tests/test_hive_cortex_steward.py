from __future__ import annotations

import unittest
from collections.abc import Iterator, Mapping

from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.reconciler import RepairKind
from hive_mind_os.brain_kernel.steward import (
    HealthObservation,
    HealthObservationValue,
    HealthStatus,
    HealthSurface,
    OperationalReadiness,
    Steward,
    StewardIntegrityError,
)


def observation(
    surface: HealthSurface,
    status: HealthStatus = HealthStatus.HEALTHY,
    **changes: object,
) -> HealthObservationValue:
    evidence = {"surface": surface.value, "verified": True}
    values: dict[str, object] = {
        "surface": surface,
        "status": status,
        "subject_id": f"{surface.value}-1",
        "evidence": evidence,
        "evidence_digest": canonical_digest(evidence),
        "recovery_ref": None if status is HealthStatus.HEALTHY else f"recovery:{surface.value}",
    }
    values.update(changes)
    return HealthObservation(**values)  # type: ignore[arg-type]


def complete_observations() -> tuple[HealthObservationValue, ...]:
    return tuple(observation(surface) for surface in HealthSurface)


class HiveCortexStewardTests(unittest.TestCase):
    def test_complete_healthy_evidence_proves_operational_readiness(self) -> None:
        report = Steward().assess(reversed(complete_observations()))
        self.assertEqual(OperationalReadiness.READY, report.readiness)
        self.assertEqual((), report.proposals)
        self.assertEqual(tuple(HealthSurface), tuple(item.surface for item in report.observations))
        self.assertEqual(report.report_digest, Steward().assess(complete_observations()).report_digest)

    def test_health_checks_cover_every_required_operational_surface(self) -> None:
        with self.assertRaisesRegex(StewardIntegrityError, "missing: providers"):
            Steward().assess(complete_observations()[:-1])
        with self.assertRaisesRegex(StewardIntegrityError, "more than once"):
            Steward().assess((*complete_observations(), observation(HealthSurface.QUEUES)))

    def test_degraded_health_only_proposes_bounded_reversible_recovery(self) -> None:
        observations = list(complete_observations())
        observations[1] = observation(HealthSurface.LEASES, HealthStatus.DEGRADED)
        report = Steward().assess(observations)
        self.assertEqual(OperationalReadiness.REPAIR_REQUIRED, report.readiness)
        self.assertEqual(1, len(report.proposals))
        proposal = report.proposals[0]
        self.assertEqual(RepairKind.RELEASE_STALE_LEASE, proposal.repair_kind)
        self.assertEqual(1, proposal.max_attempts)
        self.assertTrue(proposal.rollback_ref.startswith("rollback:"))

    def test_critical_evidence_or_recovery_failures_fail_closed(self) -> None:
        observations = list(complete_observations())
        observations[5] = observation(HealthSurface.RECEIPTS, HealthStatus.CRITICAL)
        self.assertEqual(OperationalReadiness.QUARANTINED, Steward().assess(observations).readiness)
        with self.assertRaisesRegex(StewardIntegrityError, "digest does not match"):
            observation(HealthSurface.EVENT_CHAINS, evidence_digest="sha256:" + "0" * 64)
        with self.assertRaisesRegex(StewardIntegrityError, "requires a recovery reference"):
            observation(HealthSurface.WORKSPACES, HealthStatus.DEGRADED, recovery_ref=None)

    def test_nested_evidence_is_defensively_immutable_after_validation(self) -> None:
        evidence = {"surface": "queues", "nested": {"state": "healthy"}}
        sealed = observation(
            HealthSurface.QUEUES,
            evidence=evidence,
            evidence_digest=canonical_digest(evidence),
        )
        evidence["nested"]["state"] = "corrupted"  # type: ignore[index]
        self.assertEqual("healthy", sealed.evidence["nested"]["state"])  # type: ignore[index]
        with self.assertRaises(TypeError):
            sealed.evidence["nested"]["state"] = "corrupted"  # type: ignore[index]
        report = Steward().assess((sealed, *complete_observations()[1:]))
        self.assertEqual(OperationalReadiness.READY, report.readiness)

    def test_rejects_lossy_or_colliding_evidence_mapping_keys(self) -> None:
        non_string = {"surface": "queues", "nested": {1: "would be coerced"}}
        with self.assertRaisesRegex(StewardIntegrityError, "keys must be strings"):
            observation(
                HealthSurface.QUEUES,
                evidence=non_string,
                evidence_digest=canonical_digest(non_string),
            )

        class CollidingEvidence(Mapping[str, object]):
            def __getitem__(self, key: str) -> object:
                if key == "surface":
                    return "queues"
                raise KeyError(key)

            def __iter__(self) -> Iterator[str]:
                return iter(("surface",))

            def __len__(self) -> int:
                return 1

            def items(self) -> object:  # type: ignore[override]
                return (("surface", "queues"), ("surface", "forged"))

        with self.assertRaisesRegex(StewardIntegrityError, "must not collide"):
            observation(
                HealthSurface.QUEUES,
                evidence=CollidingEvidence(),
                evidence_digest=canonical_digest({"surface": "queues"}),
            )

    def test_observation_blocks_object_setattr_evidence_tampering(self) -> None:
        sealed = observation(HealthSurface.QUEUES)
        with self.assertRaises(AttributeError):
            object.__setattr__(sealed, "evidence", {"surface": "queues", "verified": False})
        self.assertEqual(OperationalReadiness.READY, Steward().assess((sealed, *complete_observations()[1:])).readiness)

    def test_observation_has_no_mutable_public_pair_or_registry_to_forge(self) -> None:
        sealed = observation(HealthSurface.QUEUES)
        forged = {"surface": "queues", "verified": False}
        with self.assertRaises(AttributeError):
            object.__setattr__(sealed, "evidence", forged)
        with self.assertRaises(AttributeError):
            object.__setattr__(sealed, "evidence_digest", canonical_digest(forged))
        self.assertFalse(hasattr(__import__("hive_mind_os.brain_kernel.steward", fromlist=["*"],), "_OBSERVATION_SEALS"))

    def test_assessment_rejects_tuple_constructor_bypass(self) -> None:
        evidence = {"surface": "queues", "verified": True}
        bypassed = tuple.__new__(
            HealthObservation,
            (
                HealthSurface.QUEUES,
                HealthStatus.HEALTHY,
                "",
                evidence,
                canonical_digest(evidence),
                None,
                "forged-provenance-tag",
            ),
        )
        with self.assertRaisesRegex(StewardIntegrityError, "provenance is invalid"):
            Steward().assess((bypassed, *complete_observations()[1:]))

    def test_assessment_rejects_matching_digest_tuple_counterfeit(self) -> None:
        evidence = {"surface": "queues", "verified": True}
        counterfeit = tuple.__new__(
            HealthObservation,
            (
                HealthSurface.QUEUES,
                HealthStatus.HEALTHY,
                "queues-1",
                evidence,
                canonical_digest(evidence),
                None,
                "forged-provenance-tag",
            ),
        )
        with self.assertRaisesRegex(StewardIntegrityError, "provenance is invalid"):
            Steward().assess((counterfeit, *complete_observations()[1:]))

    def test_assessment_uses_closure_bound_primitives_after_public_rebinding(self) -> None:
        sealed = observation(HealthSurface.QUEUES)
        other_observations = complete_observations()[1:]
        module = __import__("hive_mind_os.brain_kernel.steward", fromlist=["*"])
        original = module.canonical_digest
        object.__setattr__(
            sealed.evidence,
            "_items",
            (("surface", "queues"), ("verified", False)),
        )
        module.canonical_digest = lambda _: sealed.evidence_digest
        try:
            with self.assertRaisesRegex(StewardIntegrityError, "provenance is invalid"):
                Steward().assess((sealed, *other_observations))
        finally:
            module.canonical_digest = original

    def test_construction_rejects_non_json_or_recursive_evidence_fail_closed(self) -> None:
        with self.assertRaisesRegex(StewardIntegrityError, "finite JSON"):
            HealthObservation(
                HealthSurface.QUEUES,
                HealthStatus.HEALTHY,
                "queues-1",
                {"bad": object()},
                "sha256:" + "0" * 64,
            )
        recursive: dict[str, object] = {"surface": "queues"}
        recursive["self"] = recursive
        with self.assertRaisesRegex(StewardIntegrityError, "finite JSON"):
            HealthObservation(
                HealthSurface.QUEUES,
                HealthStatus.HEALTHY,
                "queues-1",
                recursive,
                "sha256:" + "0" * 64,
            )


if __name__ == "__main__":
    unittest.main()
