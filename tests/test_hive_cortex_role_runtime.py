from __future__ import annotations

import asyncio
import json
import unittest

from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.context import CompiledContext, ContextRequest
from hive_mind_os.brain_kernel.contracts import ContextManifest
from hive_mind_os.brain_kernel.role_runtime import RoleCapabilityDenied, RoleRuntime
from hive_mind_os.brain_kernel.roles import KERNEL_IMPLEMENTED_ROLES, RoleInvocation
from hive_mind_os.model_provider import ModelResponse, ProviderConfig, ProviderKind


_DIGEST = "sha256:" + "a" * 64


class _Provider:
    kind = ProviderKind.OPENAI_COMPATIBLE

    def __init__(self, name: str) -> None:
        self.calls: list[tuple[str, str]] = []
        self.config = ProviderConfig(
            kind=self.kind,
            base_url="https://provider.example/v1",
            model=name,
            api_key_env="TEST_API_KEY",
        )

    @property
    def credential_reference(self) -> str:
        return "test-double"

    def build_request_body(self, request) -> bytes:
        return json.dumps({"system": request.system, "user": request.user}).encode()

    def complete_once(self, request) -> ModelResponse:
        self.calls.append((request.system, request.user))
        system = request.system
        marker = "outputs must contain exactly these keys: "
        names = system.split(marker, 1)[1].split(".", 1)[0].split(", ")
        turn = {
            "summary": "provider result",
            "outputs": {name: f"output:{name}" for name in names},
            "proposed_actions": [],
            "lessons": [],
            "success": True,
        }
        raw = json.dumps(turn).encode()
        return ModelResponse(json.dumps(turn), raw, 1, 1)

    def complete(self, request) -> ModelResponse:
        return self.complete_once(request)


def _invocation(role: str) -> RoleInvocation:
    request = ContextRequest(
        mission_id="MISSION-runtime",
        work_id=f"WORK-{role}",
        attempt_id=f"ATTEMPT-{role}",
        role=role,
        charter_digest=_DIGEST,
        authority_digest=_DIGEST,
        token_budget=100,
        query="bounded role mission",
        now="1970-01-01T00:00:00Z",
        data_scopes=("repository",),
        hot_items=(),
        evaluator_mode=role == "curator",
    )
    manifest = ContextManifest(
        request.mission_id,
        request.work_id,
        request.attempt_id,
        role,
        _DIGEST,
        _DIGEST,
        100,
        0,
        (),
        (),
        (),
        (),
        {"budget": 0},
        (),
        role == "curator",
        canonical_digest({"role": role, "attempt": request.attempt_id}),
    )
    return RoleInvocation(
        mission_id=request.mission_id,
        work_id=request.work_id,
        attempt_id=request.attempt_id,
        role=role,
        executor_id=f"runtime:{role}",
        context=CompiledContext(request, manifest, (), ()),
        authority_envelope_digest=_DIGEST,
        evidence_refs=("evidence:runtime",),
        base_artifact_refs=("artifact:base",),
        candidate_artifact_refs=("artifact:candidate",),
    )


class RoleRuntimeTests(unittest.TestCase):
    def test_all_eight_role_runtime_tests(self) -> None:
        provider = _Provider("shared")
        results = asyncio.run(RoleRuntime(provider).run_mission(tuple(map(_invocation, KERNEL_IMPLEMENTED_ROLES))))
        self.assertEqual(tuple(result.role for result in results), KERNEL_IMPLEMENTED_ROLES)
        self.assertEqual(len(provider.calls), 8)
        self.assertTrue(all(result.output_artifact_refs for result in results))
        self.assertTrue(all(not result.effect_receipt_refs for result in results))

    def test_role_provider_routing_tests(self) -> None:
        shared = _Provider("shared")
        builder = _Provider("builder")
        runtime = RoleRuntime(shared, role_providers={"builder": builder})
        result = asyncio.run(runtime.execute(_invocation("builder")))
        self.assertEqual(result.role, "builder")
        self.assertEqual(len(shared.calls), 0)
        self.assertEqual(len(builder.calls), 1)
        self.assertIn("Role identity: runtime:builder", builder.calls[0][1])

    def test_role_capability_denial_tests(self) -> None:
        runtime = RoleRuntime(_Provider("shared"))
        with self.assertRaises(RoleCapabilityDenied):
            runtime.request_capability(_invocation("orchestrator"), "write")
        request = runtime.request_capability(_invocation("orchestrator"), "plan")
        self.assertEqual(request["status"], "requested")
