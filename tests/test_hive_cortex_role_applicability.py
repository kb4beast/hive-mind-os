from __future__ import annotations

import asyncio
import json
import unittest

from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.context import CompiledContext, ContextRequest
from hive_mind_os.brain_kernel.contracts import ContextManifest
from hive_mind_os.brain_kernel.role_applicability import (
    DEFAULT_APPLICABILITY_POLICY,
    ROLE_DEPENDENCIES,
    ApplicabilityDenied,
    ArchetypeSignals,
    ContextTier,
    RoleDisposition,
    RoleDispositionRecord,
    TaskArchetype,
    resolve_dispositions,
    route_prior_results,
)
from hive_mind_os.brain_kernel.role_runtime import RoleRuntime
from hive_mind_os.brain_kernel.roles import (
    KERNEL_IMPLEMENTED_ROLES,
    RoleInvocation,
    RoleProtocolError,
    result_digest,
)
from hive_mind_os.model_provider import ModelResponse, ProviderConfig, ProviderKind

DIGEST = "sha256:" + "a" * 64


def _signals(
    archetype: TaskArchetype, *, recovery: bool = False
) -> ArchetypeSignals:
    values = {
        TaskArchetype.DOC_ONLY: ("docs/one.md",),
        TaskArchetype.TEST_ONLY: ("tests/test_one.py",),
        TaskArchetype.SINGLE_MODULE_CHANGE: ("src/one.py",),
        TaskArchetype.MULTI_MODULE_CHANGE: ("src/a.py", "src/b.py"),
        TaskArchetype.EXTERNAL_EFFECT: ("src/a.py",),
        TaskArchetype.INVESTIGATION: (),
    }
    return ArchetypeSignals(
        write_scope=values[archetype],
        performs_external_effect=archetype is TaskArchetype.EXTERNAL_EFFECT,
        asserts_recovery=recovery,
        acceptance_count=1,
        evidence_refs=(f"evidence:{archetype.value}",),
    )


class _Provider:
    kind = ProviderKind.OPENAI_COMPATIBLE

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.config = ProviderConfig(
            kind=self.kind,
            base_url="https://provider.example/v1",
            model="test-model",
            api_key_env="TEST_API_KEY",
        )

    @property
    def credential_reference(self) -> str:
        return "test-double"

    def build_request_body(self, request) -> bytes:
        return json.dumps({"system": request.system, "user": request.user}).encode()

    def complete_once(self, request) -> ModelResponse:
        self.calls.append(request.user)
        marker = "outputs must contain exactly these keys: "
        names = request.system.split(marker, 1)[1].split(".", 1)[0].split(", ")
        turn = {
            "summary": "provider result",
            "outputs": {name: f"output:{name}" for name in names},
            "proposed_actions": [],
            "lessons": [],
            "success": True,
        }
        raw = json.dumps(turn).encode()
        return ModelResponse(json.dumps(turn), raw, 1, 1)


def _invocation(role: str) -> RoleInvocation:
    request = ContextRequest(
        mission_id="MISSION-applicability",
        work_id=f"WORK-{role}",
        attempt_id=f"ATTEMPT-{role}",
        role=role,
        charter_digest=DIGEST,
        authority_digest=DIGEST,
        token_budget=100,
        query="bounded role mission",
        now="2026-09-02T00:00:00Z",
        data_scopes=("repository",),
        hot_items=(),
        evaluator_mode=role == "curator",
    )
    manifest = ContextManifest(
        request.mission_id,
        request.work_id,
        request.attempt_id,
        role,
        DIGEST,
        DIGEST,
        100,
        0,
        (),
        (),
        (),
        (),
        {"budget": 0},
        (),
        role == "curator",
        canonical_digest({"role": role}),
    )
    return RoleInvocation(
        request.mission_id,
        request.work_id,
        request.attempt_id,
        role,
        f"runtime:{role}",
        CompiledContext(request, manifest, (), ()),
        DIGEST,
        ("evidence:runtime",),
        ("artifact:base",),
        ("artifact:candidate",),
    )


class RoleApplicabilityTests(unittest.TestCase):
    def test_every_archetype_resolves_all_eight_roles_in_lifecycle_order(self) -> None:
        for archetype in TaskArchetype:
            records = resolve_dispositions(_signals(archetype))
            self.assertEqual(KERNEL_IMPLEMENTED_ROLES, tuple(item.role for item in records))
            self.assertEqual(8, len(records))

    def test_small_task_costs_fewer_than_eight_model_calls_but_eight_records(self) -> None:
        records = resolve_dispositions(_signals(TaskArchetype.DOC_ONLY))
        self.assertEqual(8, len(records))
        self.assertLess(sum(item.disposition is RoleDisposition.MODEL_EXECUTE for item in records), 8)

    def test_curator_external_effect_and_recovery_invariants(self) -> None:
        for archetype in TaskArchetype:
            curator = resolve_dispositions(_signals(archetype))[4]
            self.assertIsNot(curator.disposition, RoleDisposition.NOT_APPLICABLE)
        external = {item.role: item for item in resolve_dispositions(_signals(TaskArchetype.EXTERNAL_EFFECT))}
        self.assertNotEqual(RoleDisposition.NOT_APPLICABLE, external["integrator"].disposition)
        self.assertNotEqual(RoleDisposition.NOT_APPLICABLE, external["steward"].disposition)
        recovery = {item.role: item for item in resolve_dispositions(_signals(TaskArchetype.DOC_ONLY, recovery=True))}
        self.assertNotEqual(RoleDisposition.NOT_APPLICABLE, recovery["steward"].disposition)

    def test_deferred_without_trigger_and_blocked_without_reason_are_denied(self) -> None:
        for disposition in (RoleDisposition.DEFERRED, RoleDisposition.BLOCKED):
            with self.subTest(disposition=disposition), self.assertRaises(ApplicabilityDenied):
                RoleDispositionRecord(
                    "builder", disposition, "policy result", ("evidence:one",)
                )

    def test_policy_digest_is_deterministic_and_signals_require_evidence(self) -> None:
        self.assertEqual(
            DEFAULT_APPLICABILITY_POLICY.policy_digest,
            DEFAULT_APPLICABILITY_POLICY.policy_digest,
        )
        with self.assertRaises(ApplicabilityDenied):
            ArchetypeSignals((), False, False, 1, ())


class ContextRoutingTests(unittest.TestCase):
    def test_direct_transitive_and_unrelated_context_are_explicit(self) -> None:
        routed = route_prior_results(
            "builder", ("orchestrator", "explorer", "architect", "curator")
        )
        self.assertIs(ContextTier.FULL, routed["architect"])
        self.assertIs(ContextTier.DIGEST, routed["orchestrator"])
        self.assertIs(ContextTier.DIGEST, routed["explorer"])
        self.assertIs(ContextTier.OMITTED, routed["curator"])
        self.assertEqual(4, len(routed))

    def test_dependencies_cover_roles_are_acyclic_and_full_deliveries_are_linear(self) -> None:
        self.assertEqual(set(KERNEL_IMPLEMENTED_ROLES), set(ROLE_DEPENDENCIES))
        full = 0
        for index, role in enumerate(KERNEL_IMPLEMENTED_ROLES):
            prior = KERNEL_IMPLEMENTED_ROLES[:index]
            routed = route_prior_results(role, prior)
            self.assertEqual(set(prior), set(routed))
            full += sum(tier is ContextTier.FULL for tier in routed.values())
        self.assertEqual(7, full)
        self.assertEqual(28, sum(range(8)))


class LifecycleAccountabilityTests(unittest.TestCase):
    def test_doc_only_mission_returns_eight_results_with_two_model_calls(self) -> None:
        provider = _Provider()
        runtime = RoleRuntime(provider)
        self.addCleanup(runtime.backend.ledger.close)
        results = asyncio.run(
            runtime.run_mission(
                tuple(_invocation(role) for role in KERNEL_IMPLEMENTED_ROLES),
                signals=_signals(TaskArchetype.DOC_ONLY),
            )
        )
        self.assertEqual(KERNEL_IMPLEMENTED_ROLES, tuple(item.role for item in results))
        self.assertEqual(2, len(provider.calls))
        self.assertTrue(all(item.result_digest == result_digest(item) for item in results))

    def test_deterministic_result_binds_disposition_without_provider_call(self) -> None:
        provider = _Provider()
        record = RoleDispositionRecord(
            "builder",
            RoleDisposition.DETERMINISTIC_CHECK,
            "verified by a pinned deterministic check",
            ("evidence:check",),
        )
        runtime = RoleRuntime(provider)
        self.addCleanup(runtime.backend.ledger.close)
        result = runtime.deterministic_result(_invocation("builder"), record)
        self.assertEqual([], provider.calls)
        self.assertIn(record.digest, result.base_artifact_refs)

    def test_blocked_disposition_fails_closed(self) -> None:
        record = RoleDispositionRecord(
            "builder",
            RoleDisposition.BLOCKED,
            "authority is absent",
            ("evidence:blocker",),
            blocking_reason="single-writer lease is absent",
        )
        runtime = RoleRuntime(_Provider())
        self.addCleanup(runtime.backend.ledger.close)
        with self.assertRaises(ApplicabilityDenied):
            runtime.deterministic_result(_invocation("builder"), record)

    def test_curator_still_requires_evaluator_isolated_context(self) -> None:
        invocation = _invocation("curator")
        bad_request = ContextRequest(
            invocation.mission_id,
            invocation.work_id,
            invocation.attempt_id,
            "curator",
            DIGEST,
            DIGEST,
            100,
            "query",
            "2026-09-02T00:00:00Z",
            ("repository",),
            (),
            evaluator_mode=False,
        )
        bad = RoleInvocation(
            **{**invocation.to_kwargs(), "context": CompiledContext(bad_request, invocation.context.manifest, (), ())}
        )
        runtime = RoleRuntime(_Provider())
        self.addCleanup(runtime.backend.ledger.close)
        with self.assertRaises(RoleProtocolError):
            runtime.deterministic_result(
                bad,
                RoleDispositionRecord(
                    "curator", RoleDisposition.DETERMINISTIC_CHECK, "check", ("evidence:one",)
                ),
            )


if __name__ == "__main__":
    unittest.main()
