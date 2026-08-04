from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hive_mind_os.acceptance import AcceptanceSpecification
from hive_mind_os.autonomy import AutonomyBudget
from hive_mind_os.git_adapter import verify_delivery
from hive_mind_os.mission import (
    MissionFailed,
    MissionReport,
    RepositoryMission,
    ScriptedRepositoryBackend,
)
from hive_mind_os.model_backend import ModelBackend
from hive_mind_os.model_provider import (
    ModelRequest,
    ModelResponse,
    ProviderConfig,
    ProviderKind,
)
from hive_mind_os.models import AutonomyLevel, RiskTier, Role, WorkStatus
from hive_mind_os.policy import Action, PolicyEngine
from hive_mind_os.receipts import FileReceiptValidator, ReceiptReference
from hive_mind_os.roles import DEFAULT_LIFECYCLE, ROLE_CONTRACTS
from hive_mind_os.runtime import HiveKernel
from tests.fixtures.fixture_repo import (
    GOOD_FIX,
    SABOTAGE_FIX,
    build_fixture_repo,
    fixture_fix,
)


def _action(action: str, **payload: object) -> str:
    return json.dumps(
        {"action": action, **payload},
        sort_keys=True,
        separators=(",", ":"),
    )


def _fixture_acceptance_specification() -> AcceptanceSpecification:
    return AcceptanceSpecification(
        "increment-returns-two",
        "increment(1) returns 2",
        (
            sys.executable,
            "-B",
            "-c",
            "from tiny_pkg.maths import increment; assert increment(1) == 2",
        ),
    )


class _RepositoryProvider:
    def __init__(self) -> None:
        self.config = ProviderConfig(
            ProviderKind.OPENAI_COMPATIBLE,
            "https://models.example/v1",
            "fixture-model",
            "UNUSED_TEST_KEY",
            max_retries=0,
        )
        self.kind = ProviderKind.OPENAI_COMPATIBLE
        self.index = 0

    def build_request_body(self, request: ModelRequest) -> bytes:
        return json.dumps(
            {
                "system": request.system,
                "user": request.user,
                "corrective": request.corrective_message,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    def complete_once(self, request: ModelRequest) -> ModelResponse:
        role = DEFAULT_LIFECYCLE[self.index]
        self.index += 1
        test_argv = [
            sys.executable,
            "-B",
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-v",
        ]
        actions: list[str] = []
        if role is Role.EXPLORER:
            actions = [_action("run_tests", argv=test_argv)]
        elif role is Role.BUILDER:
            actions = [
                _action("create_branch", name="phase/mission-delivery"),
                _action(
                    "write_file",
                    path="tiny_pkg/maths.py",
                    content_base64=base64.b64encode(GOOD_FIX).decode("ascii"),
                ),
                _action("run_tests", argv=test_argv),
                _action("commit", message="fix: satisfy repository objective"),
            ]
        elif role is Role.CURATOR:
            actions = [
                _action("run_tests", argv=test_argv),
                _action(
                    "run_criterion",
                    argv=[
                        sys.executable,
                        "-B",
                        "-c",
                        (
                            "from tiny_pkg.maths import increment; "
                            "assert increment(1) == 2"
                        ),
                    ],
                ),
                _action("verify_delivery"),
            ]
        turn = json.dumps(
            {
                "summary": f"{role.value} model repository turn",
                "outputs": {
                    name: (
                        json.dumps(
                            {
                                "acceptance_checks": [
                                    {
                                        "name": "repository-regression",
                                        "argv": test_argv,
                                        "expected": "succeeded",
                                    },
                                    {
                                        "name": "objective-criterion",
                                        "argv": [
                                            sys.executable,
                                            "-B",
                                            "-c",
                                            (
                                                "from tiny_pkg.maths import increment; "
                                                "assert increment(1) == 2"
                                            ),
                                        ],
                                        "expected": "succeeded",
                                    },
                                ]
                            },
                            sort_keys=True,
                        )
                        if role is Role.CURATOR
                        and name == "verification report"
                        else f"model evidence for {name}"
                    )
                    for name in ROLE_CONTRACTS[role].required_outputs
                },
                "proposed_actions": actions,
                "lessons": ["model turn executed through typed capabilities"],
                "success": True,
            },
            sort_keys=True,
        )
        raw = json.dumps({"content": turn}, sort_keys=True).encode()
        return ModelResponse(turn, raw, 10, 5)

    def complete(self, request: ModelRequest) -> ModelResponse:
        return self.complete_once(request)


class _CorrectingBuilderProvider(_RepositoryProvider):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[ModelRequest] = []
        self.invalid_builder_turn_sent = False

    def complete_once(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        role = DEFAULT_LIFECYCLE[self.index]
        response = super().complete_once(request)
        if role is Role.BUILDER and not self.invalid_builder_turn_sent:
            self.invalid_builder_turn_sent = True
            self.index -= 1
            turn = json.loads(response.content)
            turn["proposed_actions"][1] = _action(
                "write_file",
                path="tiny_pkg/maths.py",
                content="not-base64-field",
            )
            content = json.dumps(turn, sort_keys=True)
            return ModelResponse(
                content,
                json.dumps({"content": content}, sort_keys=True).encode(),
                10,
                5,
            )
        return response


class _SelfApprovingProvider(_RepositoryProvider):
    def complete_once(self, request: ModelRequest) -> ModelResponse:
        role = DEFAULT_LIFECYCLE[self.index]
        self.index += 1
        real_tests = [
            sys.executable,
            "-B",
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-v",
        ]
        pass_command = [sys.executable, "-B", "-c", "pass"]
        actions: list[str] = []
        if role is Role.EXPLORER:
            actions = [_action("run_tests", argv=real_tests)]
        elif role is Role.BUILDER:
            actions = [
                _action("create_branch", name="phase/mission-delivery"),
                _action(
                    "write_file",
                    path="README.md",
                    content_base64=base64.b64encode(b"not a fix\n").decode("ascii"),
                ),
                _action("run_tests", argv=pass_command),
                _action("commit", message="docs: pretend to fix objective"),
            ]
        elif role is Role.CURATOR:
            actions = [
                _action("run_tests", argv=pass_command),
                _action("run_criterion", argv=pass_command),
                _action("verify_delivery"),
            ]
        turn = json.dumps(
            {
                "summary": f"{role.value} adversarial repository turn",
                "outputs": {
                    name: f"adversarial evidence for {name}"
                    for name in ROLE_CONTRACTS[role].required_outputs
                },
                "proposed_actions": actions,
                "lessons": ["attempted backend-controlled self-approval"],
                "success": True,
            },
            sort_keys=True,
        )
        raw = json.dumps({"content": turn}, sort_keys=True).encode()
        return ModelResponse(turn, raw, 10, 5)


class RepositoryMissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.fixture = build_fixture_repo(self.base / "source")
        self.counter = 0

    def output(self, label: str) -> Path:
        self.counter += 1
        return self.base / f"{label}-{self.counter}"

    def run_mission(
        self,
        *,
        backend=None,
        policy: PolicyEngine | None = None,
        budget: AutonomyBudget | None = None,
        label: str = "artifact",
    ) -> tuple[MissionReport, Path]:
        output = self.output(label)
        report = asyncio.run(
            RepositoryMission(
                self.fixture.root,
                "Fix the failing test",
                acceptance_criteria=("increment(1) returns 2",),
                acceptance_specifications=(_fixture_acceptance_specification(),),
                backend=backend,
                pin=self.fixture.commit_two,
                output_dir=output,
                policy=policy,
                budget=budget,
            ).run()
        )
        return report, output

    def assert_receipts_resolve(self, report: MissionReport) -> None:
        self.assertIsNotNone(report.receipt_root)
        validator = FileReceiptValidator(report.receipt_root or "")
        self.assertGreater(len(report.receipts), 0)
        for record in report.receipts:
            validation = validator.validate(
                ReceiptReference(record["path"], record["digest"]),
                mission_id=record["mission_id"],
                state_ref=record["state_ref"],
                actor_id=record["actor_id"],
                action_id=record["action_id"],
                action_kind=record["action_kind"],
                action_digest=record["action_digest"],
            )
            self.assertTrue(validation.valid, validation.issues)

    def assert_failed_evidence_is_preserved(
        self,
        report: MissionReport,
        output: Path,
    ) -> None:
        self.assertIs(report.status, WorkStatus.FAILED)
        self.assertFalse(output.exists())
        self.assertIsNotNone(report.receipt_root)
        self.assertNotEqual(Path(report.receipt_root or ""), output)
        self.assertTrue(
            (Path(report.receipt_root or "") / "mission-report.json").is_file()
        )
        self.assert_receipts_resolve(report)

    def test_golden_scripted_delivery_and_report_fixture(self) -> None:
        report, output = self.run_mission()
        self.assertIs(report.status, WorkStatus.SUCCEEDED)
        self.assertEqual(report.curator_verdict, "adopt")
        self.assertEqual(tuple(result.role for result in report.results), DEFAULT_LIFECYCLE)
        for name in ("changes.bundle", "changes.patch", "delivery.json"):
            self.assertTrue((output / name).is_file())
        self.assertTrue(verify_delivery(output, self.fixture.root))
        self.assert_receipts_resolve(report)
        self.assertEqual(
            len(report.receipts),
            report.budget_consumption["tool_calls"],
        )
        committed = json.loads(
            (
                Path(__file__).parent
                / "fixtures"
                / "mission"
                / "golden_report.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(report.to_dict(normalize_volatile=True), committed)

    def test_curator_workspace_and_context_are_independent(self) -> None:
        marker = "builder-private-rationale-marker"

        class MarkedBackend(ScriptedRepositoryBackend):
            async def execute(self, contract, work_item, objective, context):
                result = await super().execute(
                    contract,
                    work_item,
                    objective,
                    context,
                )
                if contract.role is Role.BUILDER:
                    return type(result)(
                        role=result.role,
                        work_item_id=result.work_item_id,
                        summary=marker,
                        evidence=result.evidence,
                        proposed_actions=result.proposed_actions,
                        lessons=result.lessons,
                        success=result.success,
                    )
                return result

        backend = MarkedBackend()
        report, _ = self.run_mission(backend=backend)
        self.assertIs(report.status, WorkStatus.SUCCEEDED)
        self.assertNotEqual(report.builder_workspace, report.curator_workspace)
        curator_context = backend.contexts[Role.CURATOR][0]
        encoded = json.dumps(curator_context, sort_keys=True)
        self.assertNotIn(Role.BUILDER.value, curator_context["roles"])
        self.assertNotIn(marker, encoded)
        manifest = next(
            item
            for item in report.context_manifests
            if item["role"] == Role.CURATOR.value
        )
        self.assertNotIn(Role.BUILDER.value, manifest["prior_roles"])
        builder_digests = {
            record["digest"]
            for record in report.receipts
            if record["actor_id"] == Role.BUILDER.value
        }
        self.assertTrue(
            builder_digests.isdisjoint(set(manifest["receipt_digests"]))
        )
        self.assertEqual(manifest["prior_roles"], [])
        self.assertEqual(manifest["provider_kind"], "scripted")
        self.assertEqual(manifest["model_id"], "scripted-repository")
        self.assertNotIn("contaminated-verification", report.event_types)
        self.assertLess(
            report.event_types.index("curator.acceptance.sealed"),
            report.event_types.index("curator.workspace.materialized"),
        )
        self.assertIn("curator.workspace.materialized", report.event_types)

    def test_curator_rejects_test_weakening_without_export(self) -> None:
        backend = ScriptedRepositoryBackend("sabotage")
        self.assertEqual(
            fixture_fix("sabotage"),
            ("tests/test_maths.py", SABOTAGE_FIX),
        )
        report, output = self.run_mission(backend=backend)
        self.assertIs(report.status, WorkStatus.FAILED)
        self.assertEqual(report.curator_verdict, "reject")
        self.assert_failed_evidence_is_preserved(report, output)
        self.assertIn("curator.divergence", report.event_types)
        self.assertEqual(report.failure["type"], "MissionFailed")

    def test_policy_ceiling_denies_builder_write_and_exports_nothing(self) -> None:
        report, output = self.run_mission(
            policy=PolicyEngine(AutonomyLevel.ADVISE),
        )
        self.assertIs(report.status, WorkStatus.FAILED)
        self.assertFalse(output.exists())
        self.assertIn("requires autonomy level", report.failure["message"])
        self.assertEqual(report.event_types[:2], ("mission.started", "policy.decision"))

    def test_failure_report_retains_the_mission_cause_when_evidence_fails(self) -> None:
        class BrokenEvidenceMission(RepositoryMission):
            def _preserve_failure_evidence(self, final_output: Path) -> str | None:
                raise MissionFailed("receipt validation failed")

        output = self.output("broken-evidence")
        report = asyncio.run(
            BrokenEvidenceMission(
                self.fixture.root,
                "Fix the failing test",
                acceptance_criteria=("increment(1) returns 2",),
                acceptance_specifications=(_fixture_acceptance_specification(),),
                pin=self.fixture.commit_two,
                output_dir=output,
                policy=PolicyEngine(AutonomyLevel.ADVISE),
            ).run()
        )
        self.assertIs(report.status, WorkStatus.FAILED)
        self.assertIn("mission failed because", report.failure["message"])
        self.assertIn("requires autonomy level", report.failure["message"])
        self.assertIn("additionally, evidence preservation failed", report.failure["message"])

    def test_budget_exhaustion_is_recorded_and_exports_nothing(self) -> None:
        report, output = self.run_mission(
            budget=AutonomyBudget(1, 0, 0.0),
        )
        self.assertIs(report.status, WorkStatus.FAILED)
        self.assertFalse(output.exists())
        self.assertEqual(report.failure["type"], "BudgetExceeded")
        self.assertIn("budget.exhausted", report.event_types)

    def test_two_scripted_runs_have_deterministic_tree_and_event_shape(self) -> None:
        first, _ = self.run_mission(label="first")
        second, _ = self.run_mission(label="second")
        self.assertIs(first.status, WorkStatus.SUCCEEDED)
        self.assertIs(second.status, WorkStatus.SUCCEEDED)
        self.assertEqual(first.head_sha, second.head_sha)
        self.assertEqual(first.tree_digest, second.tree_digest)
        self.assertEqual(first.event_types, second.event_types)

    def test_every_result_preserves_kernel_validation(self) -> None:
        report, _ = self.run_mission()
        self.assertIs(report.status, WorkStatus.SUCCEEDED)
        for result in report.results:
            HiveKernel._validate_result(result.role, result)

    def test_model_backend_uses_the_same_capability_path(self) -> None:
        budget = AutonomyBudget(
            1000,
            500,
            500.0,
            max_tool_calls_per_episode=100,
            max_compute_units_per_episode=100.0,
        )
        provider = _RepositoryProvider()
        report, output = self.run_mission(
            backend=ModelBackend(provider, budget=budget),
            budget=budget,
            label="model",
        )
        self.assertIs(report.status, WorkStatus.SUCCEEDED)
        self.assertEqual(provider.index, len(DEFAULT_LIFECYCLE))
        self.assertTrue(verify_delivery(output, self.fixture.root))
        model_calls = [
            event
            for event in report.ledger_events
            if event["event_type"] == "model.call"
        ]
        self.assertEqual(len(model_calls), len(DEFAULT_LIFECYCLE))
        curator_call = next(
            event
            for event in model_calls
            if event["payload"]["role"] == Role.CURATOR.value
        )
        self.assertEqual(curator_call["payload"]["model_id"], "fixture-model")
        self.assertEqual(
            curator_call["payload"]["context_manifest"]["prior_roles"],
            [],
        )
        self.assertEqual(report.objective_id, report.run_id)
        self.assertEqual(
            report.budget_consumption["tool_calls"],
            len(report.receipts) + len(model_calls),
        )

    def test_builder_invalid_action_json_is_corrected_not_fatal(self) -> None:
        budget = AutonomyBudget(
            1000,
            500,
            500.0,
            max_tool_calls_per_episode=100,
            max_compute_units_per_episode=100.0,
        )
        provider = _CorrectingBuilderProvider()
        report, output = self.run_mission(
            backend=ModelBackend(provider, budget=budget),
            budget=budget,
            label="builder-correction",
        )

        self.assertIs(report.status, WorkStatus.SUCCEEDED)
        self.assertTrue(verify_delivery(output, self.fixture.root))
        builder_calls = [
            event["payload"]
            for event in report.ledger_events
            if event["event_type"] == "model.call"
            and event["payload"]["role"] == Role.BUILDER.value
        ]
        self.assertEqual(
            [call["outcome"] for call in builder_calls],
            ["invalid_output", "succeeded"],
        )
        self.assertEqual([call["retry_index"] for call in builder_calls], [0, 1])
        correction = next(
            request for request in provider.requests if request.corrective_message
        )
        self.assertIn("not-base64-field", correction.corrective_message or "")
        self.assertIn("unexpected or missing fields", correction.corrective_message or "")

    def test_model_backend_cannot_substitute_self_approving_test_commands(self) -> None:
        budget = AutonomyBudget(
            1000,
            500,
            500.0,
            max_tool_calls_per_episode=100,
            max_compute_units_per_episode=100.0,
        )
        provider = _SelfApprovingProvider()
        report, output = self.run_mission(
            backend=ModelBackend(provider, budget=budget),
            budget=budget,
            label="self-approval",
        )
        self.assert_failed_evidence_is_preserved(report, output)
        self.assertIn(
            "differs from the Explorer failure-reproducing command",
            report.failure["message"],
        )
        failing = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-v",
            ],
            cwd=self.fixture.root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            check=False,
            text=True,
            timeout=60,
        )
        self.assertNotEqual(failing.returncode, 0)

    def test_model_backend_is_bound_to_the_mission_budget(self) -> None:
        provider = _RepositoryProvider()
        backend = ModelBackend(provider)
        mission_budget = AutonomyBudget(
            1000,
            45,
            500.0,
            max_tool_calls_per_episode=100,
            max_compute_units_per_episode=100.0,
        )
        report, output = self.run_mission(
            backend=backend,
            budget=mission_budget,
            label="shared-model-budget",
        )
        self.assertIs(backend.budget, mission_budget)
        self.assertIs(report.status, WorkStatus.FAILED)
        self.assertFalse(output.exists())
        self.assertEqual(report.failure["type"], "BudgetExceeded")
        self.assertLessEqual(
            report.budget_consumption["tool_calls"],
            45,
        )
        model_calls = [
            event
            for event in report.ledger_events
            if event["event_type"] == "model.call"
        ]
        self.assertEqual(len(model_calls), provider.index)
        self.assertGreater(len(model_calls), 0)
        self.assertEqual(
            report.budget_consumption["tool_calls"],
            len(report.receipts) + len(model_calls),
        )

    def test_model_backend_restrictive_budget_is_not_replaced_by_default(self) -> None:
        provider = _RepositoryProvider()
        restrictive_budget = AutonomyBudget(
            1000,
            0,
            0.0,
            max_tool_calls_per_episode=100,
            max_compute_units_per_episode=100.0,
        )
        backend = ModelBackend(provider, budget=restrictive_budget)
        report, output = self.run_mission(
            backend=backend,
            label="restrictive-backend-budget",
        )
        self.assertIs(backend.budget, restrictive_budget)
        self.assertIs(report.status, WorkStatus.FAILED)
        self.assertFalse(output.exists())
        self.assertEqual(report.failure["type"], "BudgetExceeded")
        self.assertEqual(provider.index, 0)
        self.assertEqual(report.budget_consumption["tool_calls"], 0)
        self.assertFalse(
            any(
                event["event_type"] == "model.call"
                for event in report.ledger_events
            )
        )

    def test_failed_git_operation_keeps_receipts_and_budget_accounting(self) -> None:
        class ExistingBranchBackend(ScriptedRepositoryBackend):
            async def execute(self, contract, work_item, objective, context):
                result = await super().execute(
                    contract,
                    work_item,
                    objective,
                    context,
                )
                if contract.role is Role.BUILDER:
                    return type(result)(
                        role=result.role,
                        work_item_id=result.work_item_id,
                        summary=result.summary,
                        evidence=result.evidence,
                        proposed_actions=(_action("create_branch", name="main"),),
                        lessons=result.lessons,
                        success=result.success,
                    )
                return result

        report, output = self.run_mission(
            backend=ExistingBranchBackend(),
            label="failed-git",
        )
        self.assert_failed_evidence_is_preserved(report, output)
        builder_records = [
            record
            for record in report.receipts
            if record["actor_id"] == Role.BUILDER.value
        ]
        self.assertEqual(len(builder_records), 5)
        self.assertEqual(
            [record["result"] for record in builder_records[-2:]],
            ["succeeded", "failed"],
        )
        self.assertEqual(
            report.budget_consumption["tool_calls"],
            len(report.receipts),
        )
        failed_digest = builder_records[-1]["digest"]
        self.assertTrue(
            any(
                event["event_type"] == "receipt.recorded"
                and event["payload"]["digest"] == failed_digest
                for event in report.ledger_events
            )
        )

    def test_cli_golden_and_sabotage_paths(self) -> None:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = os.pathsep.join(
            (str(Path(__file__).parents[1] / "src"), str(Path(__file__).parents[1]))
        )
        good_output = self.output("cli-good")
        acceptance_specification = self.base / "increment-returns-two.json"
        acceptance_specification.write_text(
            json.dumps(_fixture_acceptance_specification().to_dict(), sort_keys=True),
            encoding="utf-8",
        )
        command = [
            sys.executable,
            "-m",
            "hive_mind_os.cli",
            "deliver",
            "--repository",
            str(self.fixture.root),
            "--backend",
            "scripted",
            "--pin",
            self.fixture.commit_two,
            "--objective",
            "Fix the failing test",
            "--criterion",
            "increment(1) returns 2",
            "--acceptance-spec",
            str(acceptance_specification),
            "--output-dir",
            str(good_output),
        ]
        good = subprocess.run(
            command,
            cwd=Path(__file__).parents[1],
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            check=False,
            text=True,
            timeout=60,
        )
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertEqual(json.loads(good.stdout)["status"], "succeeded")
        self.assertTrue(verify_delivery(good_output, self.fixture.root))

        sabotage_output = self.output("cli-sabotage")
        sabotage = subprocess.run(
            [
                *command[:-1],
                str(sabotage_output),
                "--scripted-variant",
                "sabotage",
            ],
            cwd=Path(__file__).parents[1],
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            check=False,
            text=True,
            timeout=60,
        )
        self.assertNotEqual(sabotage.returncode, 0)
        self.assertEqual(json.loads(sabotage.stderr)["status"], "failed")
        self.assertFalse(sabotage_output.exists())

    def test_output_parent_symlink_is_rejected_when_supported(self) -> None:
        target = self.base / "output-target"
        target.mkdir()
        linked = self.base / "output-link"
        try:
            linked.symlink_to(target, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")
        mission = RepositoryMission(
            self.fixture.root,
            "Fix the failing test",
            acceptance_specifications=(_fixture_acceptance_specification(),),
            backend=ScriptedRepositoryBackend(),
            pin=self.fixture.commit_two,
            output_dir=linked / "delivery",
        )
        with self.assertRaisesRegex(ValueError, "must not traverse"):
            mission._validated_output()

    def test_explorer_command_is_bounded_but_writes_remain_denied(self) -> None:
        sandbox = PolicyEngine(AutonomyLevel.SANDBOX)
        self.assertTrue(
            sandbox.decide(
                Role.EXPLORER,
                Action.RUN_COMMANDS,
                RiskTier.MODERATE,
            ).allowed
        )
        self.assertFalse(
            PolicyEngine(AutonomyLevel.ADVISE).decide(
                Role.EXPLORER,
                Action.RUN_COMMANDS,
                RiskTier.MODERATE,
            ).allowed
        )
        self.assertFalse(
            sandbox.decide(
                Role.EXPLORER,
                Action.WRITE_WORKSPACE,
                RiskTier.MODERATE,
            ).allowed
        )


if __name__ == "__main__":
    unittest.main()
