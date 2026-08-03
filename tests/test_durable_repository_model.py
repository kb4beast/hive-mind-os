from __future__ import annotations

import asyncio
import base64
import json
import sqlite3
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from hive_mind_os.acceptance import AcceptanceSpecification
from hive_mind_os.autonomy import AutonomyBudget
from hive_mind_os.durable_repository_model import (
    DurableRepositoryModelBackend,
    DurableRepositoryModelError,
    DurableRepositoryModelProfile,
    ModelRoleAdmissionJournal,
    RedactionPolicy,
)
from hive_mind_os.mission import RepositoryMission
from hive_mind_os.mission_store import MissionStore, SimulatedCrash, resume_mission
from hive_mind_os.model_backend import ModelBackend
from hive_mind_os.model_provider import (
    ModelRequest,
    ModelResponse,
    ModelTransportError,
    ProviderConfig,
    ProviderKind,
)
from hive_mind_os.model_turn_state import ModelTurnBudget, ModelTurnStore
from hive_mind_os.models import AutonomyLevel, Role, WorkItem, WorkStatus
from hive_mind_os.policy import PolicyEngine
from hive_mind_os.roles import DEFAULT_LIFECYCLE, ROLE_CONTRACTS
from tests.fixtures.fixture_repo import build_fixture_repo

MISSION_ID = "MISSION-DURABLE-REPOSITORY-47"
REDACTION_POLICY = RedactionPolicy(
    "durable-repository-test-redaction",
    "sha256:" + "b" * 64,
)
FAST_TEST_ARGV = (
    sys.executable,
    "-B",
    "-c",
    (
        "from tiny_pkg.maths import increment; "
        "raise SystemExit(0 if increment(1) == 2 else 1)"
    ),
)


@dataclass
class FakeProvider:
    responses: list[str | BaseException]

    def __post_init__(self) -> None:
        self.config = ProviderConfig(
            ProviderKind.OPENAI_COMPATIBLE,
            "https://models.example/v1",
            "durable-repository-fake",
            "DURABLE_REPOSITORY_TEST_KEY",
            max_output_tokens=128,
            max_retries=3,
        )
        self.kind = ProviderKind.OPENAI_COMPATIBLE
        self.calls: list[ModelRequest] = []

    def build_request_body(self, request: ModelRequest) -> bytes:
        return json.dumps(
            {"system": request.system, "user": request.user},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def complete_once(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        content = self.responses.pop(0)
        if isinstance(content, BaseException):
            raise content
        return ModelResponse(content, json.dumps({"content": content}).encode(), 10, 5)

    def complete(self, request: ModelRequest) -> ModelResponse:
        raise AssertionError("sealed durable repository model calls complete_once exactly once")


def _action(action_name: str, **details: object) -> str:
    return json.dumps(
        {"action": action_name, **details}, sort_keys=True, separators=(",", ":")
    )


def _turn(role: Role) -> str:
    actions: list[str] = []
    if role is Role.EXPLORER:
        actions = [_action("run_tests", argv=list(FAST_TEST_ARGV))]
    elif role is Role.BUILDER:
        actions = [
            _action("create_branch", name="phase/model-durable-delivery"),
            _action(
                "write_file",
                path="tiny_pkg/maths.py",
                content_base64=base64.b64encode(
                    b"def increment(value: int) -> int:\n    return value + 1\n"
                ).decode("ascii"),
            ),
            _action("run_tests", argv=list(FAST_TEST_ARGV)),
            _action("commit", message="fix: model durable repository mission"),
        ]
    return json.dumps(
        {
            "summary": f"{role.value} completed durable repository model contract",
            "outputs": {
                name: f"model evidence for {role.value} {name}"
                for name in ROLE_CONTRACTS[role].required_outputs
            },
            "proposed_actions": actions,
            "lessons": [f"{role.value} durable lesson"],
            "success": True,
        },
        sort_keys=True,
    )


class DurableRepositoryModelTests(unittest.TestCase):
    @staticmethod
    def _durable_backend(mission: RepositoryMission) -> DurableRepositoryModelBackend:
        if not isinstance(mission.backend, DurableRepositoryModelBackend):
            raise AssertionError("fixture did not create a durable repository model backend")
        return cast(DurableRepositoryModelBackend, mission.backend)

    def _profile(
        self,
        backend: ModelBackend,
        *,
        policy: PolicyEngine | None = None,
        redaction_policy: RedactionPolicy = REDACTION_POLICY,
    ) -> DurableRepositoryModelProfile:
        return DurableRepositoryModelProfile.from_backend(
            profile_id="durable-repository-fake-profile",
            acceptance_specification=AcceptanceSpecification(
                "increment-returns-two",
                "increment(1) returns 2",
                FAST_TEST_ARGV,
            ),
            budget=ModelTurnBudget(
                MISSION_ID,
                max_episodes=8,
                max_tool_calls=8,
                max_compute_units=100.0,
                max_tool_calls_per_episode=1,
                max_compute_units_per_episode=20.0,
            ),
            policy_decision_ref="POLICY-durable-repository",
            policy_autonomy=(policy or PolicyEngine(AutonomyLevel.REPOSITORY)).autonomy,
            lease_id="LEASE-durable-repository",
            redaction_policy=redaction_policy,
            backend=backend,
        )

    def _mission(
        self,
        root: Path,
        provider: FakeProvider,
        *,
        crash_hook=None,
        policy: PolicyEngine | None = None,
        redaction_policy: RedactionPolicy = REDACTION_POLICY,
    ) -> tuple[RepositoryMission, MissionStore, DurableRepositoryModelProfile]:
        fixture = build_fixture_repo(root / "repository")
        store = MissionStore(root / "state")
        model_root = store.mission_root(MISSION_ID)
        model_root.mkdir(parents=True, exist_ok=True)
        backend = ModelBackend(provider)
        active_policy = policy or PolicyEngine(AutonomyLevel.REPOSITORY)
        profile = self._profile(
            backend,
            policy=active_policy,
            redaction_policy=redaction_policy,
        )
        durable_backend = DurableRepositoryModelBackend(
            backend,
            ModelTurnStore(model_root / "model-turns.sqlite3"),
            profile,
            redaction_policy=redaction_policy,
            admission_journal=store,
        )
        mission = RepositoryMission(
            fixture.root,
            "Fix the failing test",
            acceptance_criteria=("increment(1) returns 2",),
            acceptance_specifications=(profile.acceptance_specification,),
            backend=durable_backend,
            pin=fixture.commit_two,
            output_dir=root / "delivery",
            mission_store=store,
            crash_hook=crash_hook,
            policy=active_policy,
            _run_id=MISSION_ID,
        )
        return mission, store, profile

    def test_full_model_mission_is_journaled_with_stable_work_items(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = FakeProvider([_turn(role) for role in DEFAULT_LIFECYCLE])
            mission, store, _ = self._mission(root, provider)
            durable = self._durable_backend(mission)
            report = asyncio.run(mission.run())
            self.assertIs(report.status, WorkStatus.SUCCEEDED)
            self.assertEqual(len(provider.calls), len(DEFAULT_LIFECYCLE))
            self.assertTrue((root / "delivery").is_dir())
            plans = [store.role_work_plan(MISSION_ID, role) for role in DEFAULT_LIFECYCLE]
            self.assertEqual(len({str(plan["work_item_id"]) for plan in plans}), 8)
            self.assertEqual(
                [str(plan["work_item_id"]) for plan in plans],
                [result.work_item_id for result in report.results],
            )
            completion = store.completed_model_role(MISSION_ID, Role.EXPLORER)
            assert completion is not None
            persisted = completion["agent_result"]
            assert isinstance(persisted, dict)
            persisted_evidence = persisted["evidence"]
            assert isinstance(persisted_evidence, list)
            self.assertEqual(
                persisted_evidence[0]["created_at"],
                report.results[1].evidence[0].created_at,
            )
            journal = json.dumps(
                {
                    "config": store.mission(MISSION_ID)["config"],
                    "plans": plans,
                    "inputs": [
                        store.role_input(MISSION_ID, role)
                        for role in DEFAULT_LIFECYCLE
                    ],
                },
                sort_keys=True,
            )
            self.assertNotIn("https://models.example/v1", journal)
            self.assertNotIn("DURABLE_REPOSITORY_TEST_KEY", journal)
            with durable.store._connection:  # noqa: SLF001 - hostile-host tamper probe
                durable.store._connection.execute(
                    "DROP TRIGGER model_turn_events_no_update"
                )
                durable.store._connection.execute(
                    """
                    UPDATE model_turn_events SET event_json='{}'
                    WHERE logical_turn_id=? AND sequence=1
                    """,
                    (str(completion["model_turn_id"]),),
                )
            with self.assertRaises(DurableRepositoryModelError):
                durable.verify_completed_role(
                    completion,
                    Role.EXPLORER,
                    str(plans[1]["work_item_id"]),
                )
            durable.store.close()
            mission.ledger.close()
            store.close()

    def test_resume_rehydrates_completed_model_turn_without_a_second_call(self) -> None:
        def crash(step_index: int, boundary: str) -> None:
            # Explorer has performed its one provider call before its first capability
            # intent.  The completed turn therefore has to be rehydrated, not retried.
            if step_index == 0 and boundary == "after_intent":
                raise SimulatedCrash

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_provider = FakeProvider([_turn(role) for role in DEFAULT_LIFECYCLE])
            mission, store, profile = self._mission(root, first_provider, crash_hook=crash)
            durable = self._durable_backend(mission)
            with self.assertRaises(SimulatedCrash):
                asyncio.run(mission.run())
            durable.store.close()
            mission.ledger.close()
            self.assertEqual(len(first_provider.calls), 2)
            self.assertEqual(store.mission(MISSION_ID)["status"], "interrupted")

            resumed_provider = FakeProvider(
                [_turn(role) for role in DEFAULT_LIFECYCLE[2:]]
            )
            resumed_backends: list[DurableRepositoryModelBackend] = []

            def resolver(sealed: DurableRepositoryModelProfile) -> DurableRepositoryModelBackend:
                self.assertEqual(sealed.to_dict(), profile.to_dict())
                backend = DurableRepositoryModelBackend(
                    ModelBackend(resumed_provider),
                    ModelTurnStore(
                        store.mission_root(MISSION_ID) / "model-turns.sqlite3"
                    ),
                    sealed,
                    redaction_policy=REDACTION_POLICY,
                    admission_journal=store,
                )
                resumed_backends.append(backend)
                return backend

            report = asyncio.run(
                resume_mission(
                    store,
                    MISSION_ID,
                    model_backend_resolver=resolver,
                )
            )
            self.assertIs(report.status, WorkStatus.SUCCEEDED)
            self.assertEqual(len(resumed_provider.calls), 6)
            explorer = store.completed_model_role(MISSION_ID, Role.EXPLORER)
            assert explorer is not None
            self.assertEqual(len(explorer["capability_receipts"]), 2)
            resumed_backends[0].store.close()
            store.close()

    def test_model_resume_requires_an_injected_sealed_resolver(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = FakeProvider([_turn(role) for role in DEFAULT_LIFECYCLE])
            mission, store, _ = self._mission(root, provider)
            durable = self._durable_backend(mission)
            mission.ledger.close()
            with self.assertRaisesRegex(RuntimeError, "injected backend resolver"):
                asyncio.run(resume_mission(store, MISSION_ID))
            self.assertEqual(provider.calls, [])
            durable.store.close()
            store.close()

    def test_model_lane_rejects_multi_specification_missions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = FakeProvider([_turn(role) for role in DEFAULT_LIFECYCLE])
            fixture = build_fixture_repo(root / "repository")
            store = MissionStore(root / "state")
            store.mission_root(MISSION_ID).mkdir(parents=True, exist_ok=True)
            raw_backend = ModelBackend(provider)
            profile = self._profile(raw_backend)
            durable_backend = DurableRepositoryModelBackend(
                raw_backend,
                ModelTurnStore(
                    store.mission_root(MISSION_ID) / "model-turns.sqlite3"
                ),
                profile,
                redaction_policy=REDACTION_POLICY,
                admission_journal=store,
            )
            second = AcceptanceSpecification(
                "different-criterion",
                "another independently executable predicate",
                FAST_TEST_ARGV,
            )
            with self.assertRaisesRegex(ValueError, "exactly one typed acceptance"):
                RepositoryMission(
                    fixture.root,
                    "Fix the failing test",
                    acceptance_specifications=(profile.acceptance_specification, second),
                    backend=durable_backend,
                    pin=fixture.commit_two,
                    output_dir=root / "delivery",
                    mission_store=store,
                    _run_id=MISSION_ID,
                )
            durable_backend.store.close()
            raw_backend.ledger.close()
            store.close()

    def test_changed_resolver_profile_is_rejected_before_any_provider_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = FakeProvider([_turn(role) for role in DEFAULT_LIFECYCLE])
            mission, store, profile = self._mission(root, provider)
            durable = self._durable_backend(mission)
            mission.ledger.close()
            durable.store.close()
            changed_provider = FakeProvider([_turn(role) for role in DEFAULT_LIFECYCLE])
            changed_provider.config = ProviderConfig(
                ProviderKind.OPENAI_COMPATIBLE,
                "https://models.example/v1",
                "substituted-model",
                "DURABLE_REPOSITORY_TEST_KEY",
                max_output_tokens=128,
                max_retries=3,
            )

            def resolver(sealed: DurableRepositoryModelProfile) -> DurableRepositoryModelBackend:
                return DurableRepositoryModelBackend(
                    ModelBackend(changed_provider),
                    ModelTurnStore(
                        store.mission_root(MISSION_ID) / "model-turns.sqlite3"
                    ),
                    sealed,
                    redaction_policy=REDACTION_POLICY,
                    admission_journal=store,
                )

            with self.assertRaisesRegex(RuntimeError, "differs from the sealed"):
                asyncio.run(
                    resume_mission(
                        store,
                        MISSION_ID,
                        model_backend_resolver=resolver,
                    )
                )
            self.assertEqual(changed_provider.calls, [])
            # The failing wrapper reaches profile validation before it has a need to
            # retain a model turn; close the original store only.
            self.assertEqual(profile.budget.mission_id, MISSION_ID)
            store.close()

    def test_replaced_turn_store_after_admission_blocks_without_provider_replay(self) -> None:
        def crash(step_index: int, boundary: str) -> None:
            if step_index == 0 and boundary == "after_intent":
                raise SimulatedCrash

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_provider = FakeProvider([_turn(role) for role in DEFAULT_LIFECYCLE])
            mission, store, profile = self._mission(root, first_provider, crash_hook=crash)
            durable = self._durable_backend(mission)
            with self.assertRaises(SimulatedCrash):
                asyncio.run(mission.run())
            durable.store.close()
            mission.ledger.close()
            turn_path = store.mission_root(MISSION_ID) / "model-turns.sqlite3"
            for path in (turn_path, Path(f"{turn_path}-wal"), Path(f"{turn_path}-shm")):
                if path.exists():
                    path.unlink()
            resumed_provider = FakeProvider([_turn(role) for role in DEFAULT_LIFECYCLE])
            resumed_backends: list[DurableRepositoryModelBackend] = []

            def resolver(sealed: DurableRepositoryModelProfile) -> DurableRepositoryModelBackend:
                backend = DurableRepositoryModelBackend(
                    ModelBackend(resumed_provider),
                    ModelTurnStore(turn_path),
                    sealed,
                    redaction_policy=REDACTION_POLICY,
                    admission_journal=store,
                )
                resumed_backends.append(backend)
                return backend

            report = asyncio.run(
                resume_mission(
                    store,
                    MISSION_ID,
                    model_backend_resolver=resolver,
                )
            )
            self.assertIs(report.status, WorkStatus.BLOCKED)
            self.assertEqual(resumed_provider.calls, [])
            resumed_backends[0].store.close()
            store.close()

    def test_custom_policy_cannot_expand_to_repository_authority_on_resume(self) -> None:
        def crash(step_index: int, boundary: str) -> None:
            if step_index == 0 and boundary == "after_intent":
                raise SimulatedCrash

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            narrow_policy = PolicyEngine(AutonomyLevel.SANDBOX)
            first_provider = FakeProvider([_turn(role) for role in DEFAULT_LIFECYCLE])
            mission, store, profile = self._mission(
                root,
                first_provider,
                crash_hook=crash,
                policy=narrow_policy,
            )
            durable = self._durable_backend(mission)
            with self.assertRaises(SimulatedCrash):
                asyncio.run(mission.run())
            durable.store.close()
            mission.ledger.close()
            resumed_provider = FakeProvider([_turn(role) for role in DEFAULT_LIFECYCLE])
            resumed_backends: list[DurableRepositoryModelBackend] = []

            def resolver(sealed: DurableRepositoryModelProfile) -> DurableRepositoryModelBackend:
                backend = DurableRepositoryModelBackend(
                    ModelBackend(resumed_provider),
                    ModelTurnStore(
                        store.mission_root(MISSION_ID) / "model-turns.sqlite3"
                    ),
                    sealed,
                    redaction_policy=REDACTION_POLICY,
                    admission_journal=store,
                )
                resumed_backends.append(backend)
                return backend

            with self.assertRaisesRegex(ValueError, "policy differs"):
                asyncio.run(
                    resume_mission(
                        store,
                        MISSION_ID,
                        model_backend_resolver=resolver,
                    )
                )
            self.assertEqual(resumed_provider.calls, [])
            self.assertEqual(profile.policy_autonomy, AutonomyLevel.SANDBOX)
            resumed_backends[0].store.close()
            store.close()

    def test_redaction_policy_material_and_profile_secret_are_required_before_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret = "durable-model-profile-secret"
            redaction_policy = RedactionPolicy(
                "durable-repository-secret-redaction",
                "sha256:" + "c" * 64,
                (secret,),
            )
            store = MissionStore(root / "state")
            model_root = store.mission_root(MISSION_ID)
            model_root.mkdir(parents=True, exist_ok=True)
            backend = ModelBackend(FakeProvider([_turn(role) for role in DEFAULT_LIFECYCLE]))
            profile = self._profile(
                backend,
                redaction_policy=redaction_policy,
            )
            object.__setattr__(profile, "profile_id", secret)
            with self.assertRaisesRegex(RuntimeError, "contains configured redaction material"):
                DurableRepositoryModelBackend(
                    backend,
                    ModelTurnStore(model_root / "model-turns.sqlite3"),
                    profile,
                    redaction_policy=redaction_policy,
                    admission_journal=store,
                )
            self.assertFalse(store.has_mission(MISSION_ID))
            backend.ledger.close()
            store.close()

    def test_redaction_policy_omission_blocks_resume_before_any_provider_call(self) -> None:
        def crash(step_index: int, boundary: str) -> None:
            if step_index == 0 and boundary == "after_intent":
                raise SimulatedCrash

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret = "durable-model-resume-secret"
            sealed_redaction = RedactionPolicy(
                "durable-repository-resume-redaction",
                "sha256:" + "d" * 64,
                (secret,),
            )
            first_provider = FakeProvider([_turn(role) for role in DEFAULT_LIFECYCLE])
            mission, store, _ = self._mission(
                root,
                first_provider,
                crash_hook=crash,
                redaction_policy=sealed_redaction,
            )
            durable = self._durable_backend(mission)
            with self.assertRaises(SimulatedCrash):
                asyncio.run(mission.run())
            durable.store.close()
            mission.ledger.close()
            resumed_provider = FakeProvider([_turn(role) for role in DEFAULT_LIFECYCLE])
            omitted_redaction = RedactionPolicy(
                sealed_redaction.identifier,
                sealed_redaction.digest,
            )

            def resolver(sealed: DurableRepositoryModelProfile) -> DurableRepositoryModelBackend:
                return DurableRepositoryModelBackend(
                    ModelBackend(resumed_provider),
                    ModelTurnStore(
                        store.mission_root(MISSION_ID) / "model-turns.sqlite3"
                    ),
                    sealed,
                    redaction_policy=omitted_redaction,
                    admission_journal=store,
                )

            with self.assertRaisesRegex(RuntimeError, "redaction policy differs"):
                asyncio.run(
                    resume_mission(
                        store,
                        MISSION_ID,
                        model_backend_resolver=resolver,
                    )
                )
            self.assertEqual(resumed_provider.calls, [])
            store.close()

    def test_ambiguous_provider_turn_blocks_the_mission_without_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = FakeProvider(
                [
                    _turn(Role.ORCHESTRATOR),
                    ModelTransportError("request may have reached the provider"),
                ]
            )
            mission, store, _ = self._mission(root, provider)
            durable = self._durable_backend(mission)
            report = asyncio.run(mission.run())
            self.assertIs(report.status, WorkStatus.BLOCKED)
            self.assertEqual(store.mission(MISSION_ID)["status"], "blocked")
            self.assertEqual(len(provider.calls), 2)
            durable.store.close()
            mission.ledger.close()
            store.close()

    def test_direct_model_backend_cannot_enter_a_durable_repository_mission(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = build_fixture_repo(root / "repository")
            store = MissionStore(root / "state")
            backend = ModelBackend(FakeProvider([_turn(role) for role in DEFAULT_LIFECYCLE]))
            specification = AcceptanceSpecification(
                "increment-returns-two",
                "increment(1) returns 2",
                FAST_TEST_ARGV,
            )
            with self.assertRaisesRegex(ValueError, "sealed durable repository model adapter"):
                RepositoryMission(
                    fixture.root,
                    "Fix the failing test",
                    acceptance_specifications=(specification,),
                    backend=backend,
                    pin=fixture.commit_two,
                    output_dir=root / "delivery",
                    mission_store=store,
                    _run_id=MISSION_ID,
                )
            self.assertEqual(backend.ledger.events(), [])
            backend.ledger.close()
            store.close()

    def test_wrapper_refuses_direct_dispatch_without_a_role_admission_witness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = FakeProvider([_turn(Role.ORCHESTRATOR)])
            mission, store, _ = self._mission(root, provider)
            durable = self._durable_backend(mission)
            prepared = durable.prepare(
                ROLE_CONTRACTS[Role.ORCHESTRATOR],
                WorkItem(
                    MISSION_ID,
                    Role.ORCHESTRATOR,
                    "coordinate the durable repository mission",
                ),
                mission.objective,
                (),
            )
            with self.assertRaisesRegex(DurableRepositoryModelError, "admission witness"):
                asyncio.run(durable.execute_prepared(prepared))
            with self.assertRaisesRegex(DurableRepositoryModelError, "could not be witnessed"):
                durable.admit(prepared, "sha256:" + "0" * 64)
            with self.assertRaisesRegex(DurableRepositoryModelError, "admission witness"):
                asyncio.run(durable.execute_admitted(prepared))
            self.assertEqual(provider.calls, [])
            durable.store.close()
            mission.ledger.close()
            store.close()

    def test_wrapper_rejects_a_forged_admission_journal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = MissionStore(root / "state")
            model_root = store.mission_root(MISSION_ID)
            model_root.mkdir(parents=True, exist_ok=True)
            backend = ModelBackend(FakeProvider([_turn(Role.ORCHESTRATOR)]))
            profile = self._profile(backend)
            with self.assertRaisesRegex(DurableRepositoryModelError, "concrete MissionStore"):
                DurableRepositoryModelBackend(
                    backend,
                    ModelTurnStore(model_root / "model-turns.sqlite3"),
                    profile,
                    redaction_policy=REDACTION_POLICY,
                    admission_journal=cast(ModelRoleAdmissionJournal, object()),
                )
            self.assertEqual(backend.ledger.events(), [])
            backend.ledger.close()
            store.close()

    def test_v3_store_migrates_additively_to_the_role_journal_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            store = MissionStore(state)
            store.close()
            connection = sqlite3.connect(state / "missions.sqlite3")
            with connection:
                for name in (
                    "mission_role_work_plans",
                    "mission_role_inputs",
                    "mission_role_effects",
                    "mission_role_completions",
                ):
                    connection.execute(f"DROP TRIGGER IF EXISTS {name}_no_update")
                    connection.execute(f"DROP TRIGGER IF EXISTS {name}_no_delete")
                    connection.execute(f"DROP TABLE IF EXISTS {name}")
                connection.execute("UPDATE metadata SET value='3' WHERE key='schema_version'")
            connection.close()
            reopened = MissionStore(state)
            self.assertEqual(
                reopened._connection.execute(  # noqa: SLF001 - migration contract probe
                    "SELECT value FROM metadata WHERE key='schema_version'"
                ).fetchone()["value"],
                "5",
            )
            self.assertEqual(
                reopened._connection.execute(  # noqa: SLF001 - migration contract probe
                    "SELECT COUNT(*) FROM sqlite_master "
                    "WHERE type='table' AND name='mission_role_completions'"
                ).fetchone()[0],
                1,
            )
            reopened.close()

    def test_v3_non_model_mission_record_survives_additive_migration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            store = MissionStore(state)
            legacy_id = "MISSION-LEGACY-V3"
            legacy_config = {
                "repository": "C:/legacy/repository",
                "objective": "preserve a legacy scripted mission",
                "source_pack_fingerprint": "sha256:" + "e" * 64,
            }
            store.register_mission(
                legacy_id,
                legacy_config,
                AutonomyBudget(max_episodes=1, max_tool_calls=1, max_compute_units=1.0),
            )
            store.close()
            connection = sqlite3.connect(state / "missions.sqlite3")
            with connection:
                for name in (
                    "mission_role_work_plans",
                    "mission_role_inputs",
                    "mission_role_effects",
                    "mission_role_completions",
                    "mission_role_admissions",
                ):
                    connection.execute(f"DROP TRIGGER IF EXISTS {name}_no_update")
                    connection.execute(f"DROP TRIGGER IF EXISTS {name}_no_delete")
                    connection.execute(f"DROP TABLE IF EXISTS {name}")
                connection.execute("UPDATE metadata SET value='3' WHERE key='schema_version'")
            connection.close()
            reopened = MissionStore(state)
            self.assertEqual(reopened.mission(legacy_id)["config"], legacy_config)
            self.assertEqual(reopened.mission(legacy_id)["status"], "active")
            reopened.close()


if __name__ == "__main__":
    unittest.main()
