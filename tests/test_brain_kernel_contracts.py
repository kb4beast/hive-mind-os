from __future__ import annotations

import math
import unittest
from dataclasses import FrozenInstanceError

from hive_mind_os.brain_kernel.canonical import canonical_bytes, canonical_digest
from hive_mind_os.brain_kernel.contracts import (
    Budget,
    Candidate,
    CandidateState,
    ConstraintEnvelope,
    ContextManifest,
    EffectIntent,
    EffectReceipt,
    EvaluationPlan,
    EvaluationState,
    HistoricalEvidenceReference,
    MemoryRecord,
    MemoryState,
    MissionCharter,
    MissionState,
    TechnicalCloseoutReport,
    TechnicalCloseoutState,
    WorkItem,
    WorkState,
    normalize_portable_path,
)
from hive_mind_os.contracts import KERNEL_SCHEMA_NAMES, validate_contract

DIGEST = "sha256:" + "0" * 64
SHA = "0" * 40
TIME = "2026-08-07T12:00:00Z"
BUDGET = Budget(1, 1, 1, 1, 1, 1, 1, 1)


def charter() -> MissionCharter:
    return MissionCharter(
        1, "MISSION-phase-1", TIME, "a measurable result", (DIGEST,), "C:/repo",
        SHA, "kernel-phase-1", DIGEST, DIGEST, DIGEST, BUDGET, (), ("main",), (),
        MissionState.CREATED,
    )


class KernelContractTests(unittest.TestCase):
    def test_contracts_validate_and_round_trip_canonically(self) -> None:
        contracts = (
            charter(),
            WorkItem("WORK-one", "MISSION-phase-1", None, 0, "title", "objective", "builder", "R2", (), (), (), (), ("src\\one.py",), (), {}, 1, WorkState.PROPOSED, DIGEST, DIGEST),
            ConstraintEnvelope("AUTH-one", "MISSION-phase-1", "WORK-one", None, "builder", "R2", ("read",), (), ("src",), ("src\\one.py",), (), (), (), (), BUDGET, TIME, DIGEST, DIGEST),
            ContextManifest("MISSION-phase-1", "WORK-one", "ATTEMPT-one", "builder", DIGEST, DIGEST, 5, 5, (), (), (), (), {}, (), True, DIGEST),
            EffectIntent("MISSION-phase-1", "WORK-one", "ATTEMPT-one", "builder-1", "builder", "write", "R2", "filesystem", "src\\one.py", DIGEST, DIGEST, DIGEST, (), "revert", "POLICY-1", DIGEST),
            EffectReceipt(DIGEST, TIME, TIME, "filesystem", "1", DIGEST, "SUCCEEDED", None, None, (), DIGEST, None, None),
            MemoryRecord("MEMORY-one", "fact", "mission", (), "artifact", (), "verified", "internal", TIME, None, TIME, TIME, MemoryState.ACTIVE, (), (), None, (), "retain", DIGEST),
            EvaluationPlan("PLAN-one", SHA, DIGEST, ("python -m unittest",), (), ("tests\\test_one.py",), (DIGEST,), (), (), (), "json", (), BUDGET, EvaluationState.SEALED, DIGEST),
            Candidate("CANDIDATE-one", "MISSION-phase-1", SHA, (), CandidateState.PROPOSED, DIGEST, DIGEST),
            HistoricalEvidenceReference("receipt:legacy", DIGEST, "legacy", "retain"),
            TechnicalCloseoutReport("MISSION-phase-1", DIGEST, DIGEST, ("builder",), ("builder",), (), ("WORK-one",), (DIGEST,), (DIGEST,), TechnicalCloseoutState.TECHNICALLY_VERIFIED, DIGEST),
        )
        self.assertEqual(len(contracts), len(KERNEL_SCHEMA_NAMES) - 1)
        for contract in contracts:
            with self.subTest(contract=type(contract).__name__):
                document = contract.to_document()
                self.assertTrue(contract.validate().valid, contract.validate().issues)
                self.assertEqual(canonical_bytes(document), canonical_bytes(dict(reversed(document.items()))))
                restored = type(contract).from_document(document)
                self.assertEqual(contract.canonical_bytes(), restored.canonical_bytes())

        event = {"event_id":"EVENT-1", "mission_id":"MISSION-phase-1", "work_id":None, "attempt_id":None, "event_type":"created", "event_version":1, "actor_id":"orchestrator-1", "actor_role":"orchestrator", "occurred_at":TIME, "recorded_at":TIME, "payload":{}, "previous_digest":None, "digest":DIGEST}
        self.assertTrue(validate_contract("brain-kernel-event", event).valid)

    def test_canonical_digest_ignores_field_order_and_rejects_nan(self) -> None:
        self.assertEqual(canonical_digest({"a": 1, "b": 2}), canonical_digest({"b": 2, "a": 1}))
        with self.assertRaises(ValueError):
            canonical_bytes({"bad": math.nan})

    def test_invalid_values_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            Budget(-1, 0, 0, 0, 0, 0, 0, 0)
        with self.assertRaises(ValueError):
            MissionCharter(1, "MISSION-one", "not-a-time", "objective", (DIGEST,), "root", SHA, "branch", DIGEST, DIGEST, DIGEST, BUDGET, (), (), (), MissionState.CREATED)
        with self.assertRaises(ValueError):
            WorkItem("WORK-one", "MISSION-one", None, 0, "title", "objective", "builder", "R2", (), (), (), (), ("../escape",), (), {}, 1, WorkState.PROPOSED, DIGEST, DIGEST)
        with self.assertRaises(ValueError):
            Candidate("CANDIDATE-one", "MISSION-one", "bad", (), CandidateState.PROPOSED, DIGEST, DIGEST)
        invalid = charter().to_document() | {"status": "UNKNOWN", "extra": 1}
        result = validate_contract("brain-kernel-charter", invalid)
        self.assertFalse(result.valid)
        self.assertTrue(any("unknown properties" in issue or "enum" in issue for issue in result.issues))

    def test_frozen_and_portable(self) -> None:
        value = charter()
        with self.assertRaises(FrozenInstanceError):
            value.objective = "other"  # type: ignore[misc]
        self.assertEqual(normalize_portable_path("src\\kernel\\one.py"), "src/kernel/one.py")
        self.assertEqual(normalize_portable_path("src/kernel/one.py"), "src/kernel/one.py")
        with self.assertRaises(ValueError):
            normalize_portable_path("C:/escape")

    def test_authority_can_only_narrow(self) -> None:
        parent = ConstraintEnvelope("AUTH-parent", "MISSION-phase-1", "WORK-one", None, "builder", "R2", ("read", "write"), (), ("src", "tests"), ("src", "tests"), ("local",), (), (), (), BUDGET, TIME, DIGEST, DIGEST)
        child = ConstraintEnvelope("AUTH-child", "MISSION-phase-1", "WORK-one", DIGEST, "builder", "R2", ("read",), (), ("src",), ("src",), (), (), (), (), Budget(1, 0, 0, 0, 0, 0, 0, 0), TIME, DIGEST, DIGEST)
        self.assertTrue(child.is_no_broader_than(parent))
