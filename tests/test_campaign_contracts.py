from __future__ import annotations

import json
import math
import unittest

from hive_mind_os.campaign_contracts import (
    AcceptanceBinding, CampaignMission, CampaignState, CandidateCompletion,
    ClaimLevel, PackageState, ResourceAllocation, SuccessorContract, WorkPackage,
    campaign_state_event, package_state_event, parse_campaign_mission,
    parse_historical_inert_plan,
)
from hive_mind_os.runtime_contracts import ContractViolation
from hive_mind_os.contracts import validate_contract

DIGEST = "sha256:" + "0" * 64
SHA = "0" * 40
TIME = "2026-09-14T01:00:00Z"


def package(*, state: PackageState = PackageState.READY, completion=None, authority=DIGEST, dependencies=()):
    return WorkPackage(1, "PKG-one", "MISSION-one", "deliver a checked outcome", "src", ("R01",), dependencies,
        (AcceptanceBinding("A01", "test-runner", "receipt:one", "passed", "curator", ClaimLevel.RUNTIME),),
        "T2", ResourceAllocation(1, 2, 3), ("receipt:one",), "revert the commit", authority, state, TIME, completion)


def mission(*, packages=None, authority=DIGEST, parent_digest=None):
    return CampaignMission(1, "MISSION-one", "deliver a checked outcome", "src", ("R01",),
        (package(authority=authority),) if packages is None else packages, authority, CampaignState.READY, TIME, parent_digest)


class CampaignContractTests(unittest.TestCase):
    def test_round_trip_is_canonical_and_maps_known_states(self):
        value = mission()
        parsed = parse_campaign_mission(json.dumps(value.to_document()).encode())
        self.assertEqual(value.digest, parsed.digest)
        self.assertTrue(validate_contract("campaign-mission", value.to_document()).valid)
        self.assertTrue(validate_contract("work-package", value.packages[0].to_document()).valid)
        self.assertEqual(campaign_state_event(CampaignState.READY), "MISSION_READY")
        self.assertEqual(package_state_event(PackageState.VERIFYING), "WORK_VERIFYING")

    def test_exact_completion_and_truthful_no_change(self):
        complete = CandidateCompletion("implemented", SHA, DIGEST, (DIGEST,))
        self.assertEqual(package(state=PackageState.COMPLETED, completion=complete).completion, complete)
        no_change = CandidateCompletion("no-change", SHA, DIGEST, (DIGEST,))
        self.assertEqual(package(state=PackageState.NO_CHANGE, completion=no_change).completion, no_change)
        with self.assertRaises(ContractViolation):
            package(state=PackageState.COMPLETED)
        with self.assertRaises(ContractViolation):
            package(state=PackageState.NO_CHANGE, completion=complete)

    def test_rejects_integer_bool_nan_and_inconsistent_authority(self):
        with self.assertRaises(ContractViolation):
            ResourceAllocation(True, 1, 1)
        with self.assertRaises(ContractViolation):
            ResourceAllocation(math.nan, 1, 1)
        with self.assertRaises(ContractViolation):
            mission(packages=(package(authority="sha256:" + "1" * 64),))

    def test_rejects_orphan_requirement_dependency_and_unknown_state(self):
        with self.assertRaises(ContractViolation):
            mission(packages=(WorkPackage(1, "PKG-two", "MISSION-one", "x", "src", ("R02",), (), package().acceptance, "T2", ResourceAllocation(1, 1, 1), ("receipt:two",), "rollback", DIGEST, PackageState.READY, TIME),))
        with self.assertRaises(ContractViolation):
            mission(packages=(package(dependencies=("PKG-missing",)),))
        doc = mission().to_document(); doc["state"] = "SURPRISE"
        with self.assertRaises((ContractViolation, ValueError)):
            parse_campaign_mission(json.dumps(doc).encode())

    def test_successor_keeps_requirement_parent_and_changed_acceptance_disposition(self):
        predecessor = DIGEST
        child = mission(parent_digest=predecessor)
        value = SuccessorContract(predecessor, child, ("R01",), ("A01",), DIGEST)
        self.assertEqual(value.successor.parent_digest, predecessor)
        with self.assertRaises(ContractViolation):
            SuccessorContract(predecessor, child, ("R01",), ("A01",), None)
        with self.assertRaises(ContractViolation):
            SuccessorContract(predecessor, mission(), ("R01",), (), None)

    def test_unknown_fields_and_historical_fixture_gate_fail_closed(self):
        doc = mission().to_document(); doc["control_path"] = "candidate/app.txt"
        with self.assertRaises(ContractViolation):
            parse_campaign_mission(json.dumps(doc).encode())
        package_doc = mission().packages[0].to_document()
        package_doc["acceptance"][0]["extra"] = True
        self.assertFalse(validate_contract("work-package", package_doc).valid)
        historical = b'{"schema_version":0,"historical_inert_plan":true,"candidate":"app.txt"}'
        with self.assertRaises(ContractViolation):
            parse_historical_inert_plan(historical)
        self.assertEqual(parse_historical_inert_plan(historical, fixture_mode=True)["candidate"], "app.txt")
        with self.assertRaises(ContractViolation):
            parse_campaign_mission(historical, fixture_mode=True)


if __name__ == "__main__":
    unittest.main()
