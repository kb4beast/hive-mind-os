from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hive_mind_os.curator import (
    AcceptanceCheck,
    ContaminationError,
    CuratorReview,
    check_context_manifest,
)
from hive_mind_os.ledger import EvidenceLedger
from hive_mind_os.mission import RepositoryMission, ScriptedRepositoryBackend
from hive_mind_os.model_backend import ModelBackend
from hive_mind_os.model_provider import (
    ModelRequest,
    ModelResponse,
    ProviderConfig,
    ProviderKind,
    provider_from_env,
)
from hive_mind_os.models import (
    AgentResult,
    Objective,
    Role,
    WorkItem,
    WorkStatus,
)
from hive_mind_os.roles import ROLE_CONTRACTS
from tests.fixtures.fixture_repo import build_fixture_repo


class _OneTurnProvider:
    kind = ProviderKind.OPENAI_COMPATIBLE

    def __init__(self, model: str) -> None:
        self.config = ProviderConfig(
            self.kind,
            "https://models.example/v1",
            model,
            "UNUSED_TEST_KEY",
            max_retries=0,
        )

    def build_request_body(self, request: ModelRequest) -> bytes:
        return json.dumps(
            {"system": request.system, "user": request.user},
            sort_keys=True,
        ).encode()

    def complete_once(self, request: ModelRequest) -> ModelResponse:
        checks = json.dumps(
            {
                "acceptance_checks": [
                    {
                        "name": "fixture-check",
                        "argv": [sys.executable, "-B", "-c", "pass"],
                        "expected": "succeeded",
                    }
                ]
            },
            sort_keys=True,
        )
        turn = json.dumps(
            {
                "summary": "blind Curator turn",
                "outputs": {
                    "verification report": checks,
                    "defect findings": "none",
                    "release recommendation": "reproduce sealed checks",
                },
                "proposed_actions": [],
                "lessons": [],
                "success": True,
            },
            sort_keys=True,
        )
        return ModelResponse(turn, turn.encode(), 1, 1)

    def complete(self, request: ModelRequest) -> ModelResponse:
        return self.complete_once(request)


class CuratorReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.fixture = build_fixture_repo(self.root / "source")
        self.counter = 0

    def run_mission(
        self,
        *,
        backend: ScriptedRepositoryBackend | None = None,
        mission_type: type[RepositoryMission] = RepositoryMission,
    ):
        self.counter += 1
        output = self.root / f"delivery-{self.counter}"
        report = asyncio.run(
            mission_type(
                self.fixture.root,
                "Fix the failing test",
                acceptance_criteria=("increment(1) returns 2",),
                backend=backend or ScriptedRepositoryBackend(),
                pin=self.fixture.commit_two,
                output_dir=output,
            ).run()
        )
        return report, output

    def review(self) -> CuratorReview:
        return CuratorReview(
            "run",
            EvidenceLedger(),
            objective="objective",
            acceptance_criteria=("criterion",),
            base_workspace=self.fixture.root,
        )

    def test_blind_seal_precedes_head_access_and_reordering_is_rejected(self) -> None:
        review = self.review()
        review.seal(
            [AcceptanceCheck("check", (sys.executable, "-B", "-c", "pass"))]
        )
        self.assertIsNotNone(review.seal_sequence)
        check_context_manifest(
            {"prior_roles": [], "summaries": [], "receipt_digests": []},
            acting_identity="builder",
            verifying_identity="curator",
            seal_sequence=review.seal_sequence,
            head_access_sequence=(review.seal_sequence or 0) + 1,
        )
        with self.assertRaisesRegex(ContaminationError, "after candidate-head"):
            check_context_manifest(
                {"prior_roles": [], "summaries": [], "receipt_digests": []},
                acting_identity="builder",
                verifying_identity="curator",
                seal_sequence=review.seal_sequence,
                head_access_sequence=review.seal_sequence,
            )

        report, _ = self.run_mission()
        event_positions = {
            event_type: report.event_types.index(event_type)
            for event_type in (
                "curator.acceptance.sealed",
                "curator.workspace.materialized",
            )
        }
        self.assertLess(
            event_positions["curator.acceptance.sealed"],
            event_positions["curator.workspace.materialized"],
        )

    def test_check_added_after_seal_is_rejected(self) -> None:
        review = self.review()
        review.seal(
            [AcceptanceCheck("check", (sys.executable, "-B", "-c", "pass"))]
        )
        with self.assertRaisesRegex(ContaminationError, "after the blind seal"):
            review.add_check(
                AcceptanceCheck("late", (sys.executable, "-B", "-c", "pass"))
            )

    def test_sabotage_fails_sealed_check_and_test_weakening_heuristic(self) -> None:
        report, output = self.run_mission(
            backend=ScriptedRepositoryBackend("sabotage")
        )
        self.assertIs(report.status, WorkStatus.FAILED)
        self.assertFalse(output.exists())
        checklist_event = next(
            event
            for event in report.ledger_events
            if event["event_type"] == "curator.checklist"
        )
        weakened = next(
            item
            for item in checklist_event["payload"]["items"]
            if item["key"] == "tests-weakened"
        )
        self.assertEqual(weakened["finding"], "fail")
        file_finding = weakened["details"]["files"][0]
        self.assertLess(file_finding["retained_assertion_delta"], 0)
        reproduction = next(
            event
            for event in report.ledger_events
            if event["event_type"] == "curator.reproduction.completed"
        )
        self.assertEqual(reproduction["payload"]["decision"], "reject")
        self.assertTrue(
            any(
                not item["matched"]
                for item in reproduction["payload"]["acceptance_results"]
            )
        )

    def test_builder_receipt_contamination_fails_mission_closed(self) -> None:
        class ContaminatedMission(RepositoryMission):
            def _context_manifest(self, role, context):
                manifest = super()._context_manifest(role, context)
                if role is Role.CURATOR:
                    builder_digest = next(
                        str(record["digest"])
                        for record in self._receipt_records
                        if record["actor_id"] == Role.BUILDER.value
                    )
                    manifest["receipt_digests"] = [builder_digest]
                return manifest

        report, output = self.run_mission(mission_type=ContaminatedMission)
        self.assertIs(report.status, WorkStatus.FAILED)
        self.assertFalse(output.exists())
        self.assertEqual(report.failure["type"], "ContaminationError")
        self.assertIn("contaminated-verification", report.event_types)

    def test_malformed_context_manifest_fields_fail_mission_closed(self) -> None:
        malformed_cases = (
            ("prior_roles", "builder", False),
            ("summaries", "diff --git a/file b/file", False),
            ("receipt_digests", None, True),
            ("notes", "diff --git a/file b/file", False),
            ("model_id", "diff --git a/file b/file", False),
        )
        for field, value, remove in malformed_cases:
            with self.subTest(field=field):
                class MalformedManifestMission(RepositoryMission):
                    def _context_manifest(self, role, context):
                        manifest = super()._context_manifest(role, context)
                        if role is Role.CURATOR:
                            if remove:
                                manifest.pop(field)
                            else:
                                manifest[field] = value
                        return manifest

                report, output = self.run_mission(
                    mission_type=MalformedManifestMission
                )
                self.assertIs(report.status, WorkStatus.FAILED)
                self.assertFalse(output.exists())
                failure = report.failure
                self.assertIsNotNone(failure)
                if failure is None:
                    self.fail("failed mission did not record its failure")
                self.assertEqual(failure["type"], "ContaminationError")
                if field == "model_id":
                    self.assertIn("candidate diff bytes", failure["message"])
                else:
                    self.assertIn(field, failure["message"])
                self.assertIn("contaminated-verification", report.event_types)

    def test_same_identity_verification_is_rejected(self) -> None:
        class SameIdentityBackend(ScriptedRepositoryBackend):
            async def execute(self, contract, work_item, objective, context):
                result = await super().execute(
                    contract, work_item, objective, context
                )
                if contract.role is Role.CURATOR:
                    return AgentResult(
                        role=Role.BUILDER,
                        work_item_id=result.work_item_id,
                        summary=result.summary,
                        evidence=result.evidence,
                        proposed_actions=result.proposed_actions,
                        lessons=result.lessons,
                    )
                return result

        report, output = self.run_mission(backend=SameIdentityBackend())
        self.assertIs(report.status, WorkStatus.FAILED)
        self.assertFalse(output.exists())
        self.assertIn("contaminated-verification", report.event_types)
        self.assertIn(
            "must differ from the acting identity",
            report.failure["message"],
        )

    def test_not_evaluated_is_recorded_and_non_blocking(self) -> None:
        report, _ = self.run_mission()
        self.assertIs(report.status, WorkStatus.SUCCEEDED)
        checklist_event = next(
            event
            for event in report.ledger_events
            if event["event_type"] == "curator.checklist"
        )
        license_item = next(
            item
            for item in checklist_event["payload"]["items"]
            if item["key"] == "introduced-code-license-declared"
        )
        self.assertEqual(license_item["finding"], "not-evaluated")
        self.assertEqual(report.curator_verdict, "adopt")

    def test_role_override_and_shared_provider_are_explicit_in_receipts(self) -> None:
        environment = {
            "HIVE_MIND_MODEL_PROVIDER": "openai_compatible",
            "HIVE_MIND_MODEL_MODEL": "shared-model",
            "HIVE_MIND_MODEL_API_KEY_ENV": "SHARED_KEY",
            "SHARED_KEY": "shared-secret",
            "HIVE_MIND_MODEL_PROVIDER__CURATOR": "openai_compatible",
            "HIVE_MIND_MODEL_MODEL__CURATOR": "curator-model",
            "HIVE_MIND_MODEL_API_KEY_ENV__CURATOR": "CURATOR_KEY",
            "CURATOR_KEY": "curator-secret",
        }
        with patch.dict(os.environ, environment, clear=True):
            shared = provider_from_env()
            curator = provider_from_env(role=Role.CURATOR)
        ledger = EvidenceLedger()
        backend = ModelBackend(
            _OneTurnProvider(shared.config.model),
            ledger=ledger,
            role_providers={
                Role.CURATOR: _OneTurnProvider(curator.config.model)
            },
        )
        asyncio.run(
            backend.execute(
                ROLE_CONTRACTS[Role.CURATOR],
                WorkItem("objective", Role.CURATOR, "blind review"),
                Objective("objective", repository="base-workspace"),
                (),
            )
        )
        call = ledger.events()[0]["payload"]
        self.assertEqual(call["model_id"], "curator-model")
        self.assertEqual(
            backend.identity_for_role(Role.CURATOR)["configuration"],
            "role-override",
        )

        shared_ledger = EvidenceLedger()
        shared_backend = ModelBackend(
            _OneTurnProvider("shared-model"),
            ledger=shared_ledger,
        )
        self.assertEqual(
            shared_backend.identity_for_role(Role.CURATOR),
            {
                "provider_kind": "openai_compatible",
                "model_id": "shared-model",
                "configuration": "shared",
            },
        )
        asyncio.run(
            shared_backend.execute(
                ROLE_CONTRACTS[Role.CURATOR],
                WorkItem("objective", Role.CURATOR, "blind review"),
                Objective("objective", repository="base-workspace"),
                (),
            )
        )
        self.assertEqual(
            shared_ledger.events()[0]["payload"]["provider_configuration"],
            "shared",
        )

    def test_full_scripted_mission_passes_and_sabotage_stays_closed(self) -> None:
        good, output = self.run_mission()
        self.assertIs(good.status, WorkStatus.SUCCEEDED)
        self.assertTrue(output.exists())
        self.assertIn("curator.acceptance.sealed", good.event_types)
        self.assertIn("curator.checklist", good.event_types)
        self.assertEqual(
            next(
                manifest
                for manifest in good.context_manifests
                if manifest["role"] == Role.CURATOR.value
            )["prior_roles"],
            [],
        )

        sabotage, sabotage_output = self.run_mission(
            backend=ScriptedRepositoryBackend("sabotage")
        )
        self.assertIs(sabotage.status, WorkStatus.FAILED)
        self.assertFalse(sabotage_output.exists())


if __name__ == "__main__":
    unittest.main()
