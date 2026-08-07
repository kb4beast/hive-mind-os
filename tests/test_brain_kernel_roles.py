from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.context import CompiledContext, ContextRequest
from hive_mind_os.brain_kernel.contracts import ContextManifest
from hive_mind_os.brain_kernel.events import KernelEvent
from hive_mind_os.brain_kernel.roles import (
    KERNEL_IMPLEMENTED_ROLES,
    RoleInvocation,
    RoleProtocolError,
    append_role_result,
    result_digest,
)
from hive_mind_os.brain_kernel.store import KernelIntegrityError, KernelStore
from hive_mind_os.cortex.repository.role_handlers import (
    RepositoryRoleHandlers,
    register_kernel_prompts,
    run_fixture_role_mission,
)
from hive_mind_os.prompt_registry import PromptRegistry

_DIGEST = "sha256:" + "a" * 64


def _context(role: str, *, evaluator: bool = False) -> CompiledContext:
    request = ContextRequest(
        mission_id="MISSION-fixture",
        work_id="WORK-fixture",
        attempt_id=f"ATTEMPT-{role}",
        role=role,
        charter_digest=_DIGEST,
        authority_digest=_DIGEST,
        token_budget=10,
        query="fixture",
        now="1970-01-01T00:00:00Z",
        data_scopes=("repository",),
        hot_items=(),
        evaluator_mode=evaluator,
    )
    manifest = ContextManifest(
        request.mission_id,
        request.work_id,
        request.attempt_id,
        role,
        _DIGEST,
        _DIGEST,
        10,
        0,
        (),
        (),
        (),
        (),
        {"budget": 0},
        (),
        evaluator,
        canonical_digest({"role": role, "attempt": request.attempt_id}),
    )
    return CompiledContext(request, manifest, (), ())


def _invocation(role: str) -> RoleInvocation:
    return RoleInvocation(
        mission_id="MISSION-fixture",
        work_id="WORK-fixture",
        attempt_id=f"ATTEMPT-{role}",
        role=role,
        executor_id=f"fixture:{role}",
        context=_context(role, evaluator=role == "curator"),
        authority_envelope_digest=_DIGEST,
        evidence_refs=("evidence:fixture",),
        base_artifact_refs=("artifact:base",),
        candidate_artifact_refs=("artifact:candidate",),
    )


class KernelRoleHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.handlers = RepositoryRoleHandlers()

    def test_all_eight_roles_are_executable_and_evidence_bound(self) -> None:
        self.assertEqual(set(KERNEL_IMPLEMENTED_ROLES), set(self.handlers.roles()))
        results = []
        for role in KERNEL_IMPLEMENTED_ROLES:
            with self.subTest(role=role):
                result = self.handlers.execute(_invocation(role))
                self.assertEqual(role, result.role)
                self.assertTrue(result.base_artifact_refs)
                self.assertTrue(result.output_artifact_refs)
                self.assertEqual(
                    result.result_digest,
                    result_digest(result),
                )
                results.append(result)
        self.assertEqual(len({result.executor_id for result in results}), 8)
        self.assertEqual(len({result.context_manifest_digest for result in results}), 8)

    def test_orchestrator_cannot_write_or_accept(self) -> None:
        handler = self.handlers.handler_for("orchestrator")
        self.assertNotIn("write", handler.capabilities.allowed_actions)
        self.assertNotIn("accept", handler.capabilities.allowed_actions)
        self.assertIn("write", handler.capabilities.forbidden_actions)

    def test_curator_requires_a_fresh_evaluator_context(self) -> None:
        invocation = _invocation("curator")
        result = self.handlers.execute(invocation)
        self.assertEqual("integrator", result.requested_next_role)
        with self.assertRaises(RoleProtocolError):
            self.handlers.execute(
                RoleInvocation(
                    **{
                        **invocation.to_kwargs(),
                        "context": _context("curator", evaluator=False),
                    }
                )
            )

    def test_integrator_requests_builder_work_instead_of_patching(self) -> None:
        result = self.handlers.execute(_invocation("integrator"))
        self.assertEqual("builder", result.requested_next_role)
        self.assertNotIn("write", self.handlers.handler_for("integrator").capabilities.allowed_actions)

    def test_optimizer_cannot_promote_or_change_a_champion(self) -> None:
        handler = self.handlers.handler_for("optimizer")
        self.assertNotIn("promote", handler.capabilities.allowed_actions)
        self.assertIn("promote", handler.capabilities.forbidden_actions)
        self.assertIsNone(self.handlers.execute(_invocation("optimizer")).requested_next_role)

    def test_role_and_context_mismatch_fails_closed(self) -> None:
        invocation = _invocation("architect")
        with self.assertRaises(RoleProtocolError):
            self.handlers.execute(
                RoleInvocation(
                    **{**invocation.to_kwargs(), "role": "builder"}
                )
            )

    def test_result_is_appended_to_the_event_spine_and_replay_validates_it(self) -> None:
        store = KernelStore()
        try:
            store.append(
                KernelEvent(
                    "mission",
                    "MISSION-fixture",
                    "mission.created",
                    "fixture",
                    "1970-01-01T00:00:00Z",
                    {},
                )
            )
            head = store.events()[-1]["digest"]
            store.append(
                KernelEvent(
                    "work",
                    "MISSION-fixture",
                    "work.created",
                    "fixture",
                    "1970-01-01T00:00:00Z",
                    {},
                    work_id="WORK-fixture",
                    previous_digest=head,
                )
            )
            for status in ("READY", "LEASED", "RUNNING"):
                head = store.events()[-1]["digest"]
                store.append(
                    KernelEvent(
                        f"work:{status}",
                        "MISSION-fixture",
                        "work.transition",
                        "fixture",
                        "1970-01-01T00:00:00Z",
                        {"status": status},
                        work_id="WORK-fixture",
                        previous_digest=head,
                    )
                )
            result = self.handlers.execute(_invocation("architect"))
            sequence = append_role_result(store, result, occurred_at="1970-01-01T00:00:00Z")
            self.assertEqual(sequence, append_role_result(store, result, occurred_at="1970-01-01T00:00:00Z"))
            event = store.events()[-1]
            self.assertEqual("role.result", event["event_type"])
            self.assertEqual(result.executor_id, event["actor_id"])
            self.assertEqual(result.role, event["actor_role"])
            store.rebuild_projections()

            corrupted = dict(event["payload"])
            corrupted["result"] = {**corrupted["result"], "role": "builder"}
            with self.assertRaises(KernelIntegrityError):
                store.append(
                    KernelEvent(
                        "forged-result",
                        "MISSION-fixture",
                        "role.result",
                        result.executor_id,
                        "1970-01-01T00:00:00Z",
                        corrupted,
                        work_id=result.work_id,
                        attempt_id=result.attempt_id,
                        actor_role=result.role,
                        previous_digest=store.events()[-1]["digest"],
                    )
                )
        finally:
            store.close()

    def test_kernel_prompts_register_locally_without_champion_mutation(self) -> None:
        with TemporaryDirectory() as temporary:
            registry = PromptRegistry(Path(temporary))
            try:
                digests = register_kernel_prompts(registry)
                self.assertEqual(set(KERNEL_IMPLEMENTED_ROLES), set(digests))
                for role, digest in digests.items():
                    self.assertIn(role, registry.read(digest))
                    self.assertIsNone(registry.champion_digest(role))
            finally:
                registry.close()

    def test_fixture_mission_runs_all_roles_and_persists_separate_results(self) -> None:
        store = KernelStore()
        try:
            results = run_fixture_role_mission(store)
            self.assertEqual(KERNEL_IMPLEMENTED_ROLES, tuple(result.role for result in results))
            events = [event for event in store.events() if event["event_type"] == "role.result"]
            self.assertEqual(8, len(events))
            self.assertEqual(
                {result.executor_id for result in results},
                {event["actor_id"] for event in events},
            )
            self.assertTrue(all(not result.effect_receipt_refs for result in results))
            self.assertTrue(
                all(work["status"] == "RUNNING" for work in store.projection()["work"].values())
            )
        finally:
            store.close()
