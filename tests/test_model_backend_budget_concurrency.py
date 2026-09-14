from __future__ import annotations

import asyncio
import json
import threading
import unittest

from hive_mind_os.autonomy import AutonomyBudget, BudgetExceeded
from hive_mind_os.model_backend import ModelBackend
from hive_mind_os.model_provider import (
    ModelRequest,
    ModelResponse,
    ProviderConfig,
    ProviderKind,
)
from hive_mind_os.models import Objective, Role, WorkItem
from hive_mind_os.roles import ROLE_CONTRACTS


def _valid_turn(role: Role) -> str:
    return json.dumps(
        {
            "summary": f"{role.value} complete",
            "outputs": {
                name: f"evidence for {name}"
                for name in ROLE_CONTRACTS[role].required_outputs
            },
            "proposed_actions": [],
            "lessons": ["bounded concurrent call"],
            "success": True,
        },
        sort_keys=True,
    )


class ConcurrentProvider:
    def __init__(
        self,
        *,
        rendezvous: threading.Barrier | None = None,
        release: threading.Event | None = None,
    ) -> None:
        self.config = ProviderConfig(
            ProviderKind.OPENAI_COMPATIBLE,
            "https://models.example/v1",
            "concurrent-model",
            "FAKE_KEY_ENV",
            max_retries=0,
        )
        self.kind = ProviderKind.OPENAI_COMPATIBLE
        self.rendezvous = rendezvous
        self.release = release
        self.started = threading.Event()
        self.calls = 0
        self.max_in_flight = 0
        self._in_flight = 0
        self._lock = threading.Lock()

    def build_request_body(self, request: ModelRequest) -> bytes:
        return json.dumps(
            {"system": request.system, "user": request.user},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    def complete_once(self, request: ModelRequest) -> ModelResponse:
        del request
        with self._lock:
            self.calls += 1
            self._in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)
        self.started.set()
        try:
            if self.rendezvous is not None:
                self.rendezvous.wait(timeout=3)
            if self.release is not None and not self.release.wait(timeout=3):
                raise TimeoutError("test provider was not released")
            content = _valid_turn(Role.ARCHITECT)
            return ModelResponse(content, content.encode(), 10, 5)
        finally:
            with self._lock:
                self._in_flight -= 1

    def complete(self, request: ModelRequest) -> ModelResponse:
        return self.complete_once(request)

    @property
    def credential_reference(self) -> str:
        return "test-provider"


def _execute(backend: ModelBackend, objective: Objective, instruction: str):
    role = Role.ARCHITECT
    return backend.execute(
        ROLE_CONTRACTS[role],
        WorkItem(objective.id, role, instruction),
        objective,
        (),
    )


class ModelBackendBudgetConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_parallel_calls_overlap_and_settle_exact_usage(self) -> None:
        provider = ConcurrentProvider(rendezvous=threading.Barrier(2))
        budget = AutonomyBudget(2, 2, 100.0)
        backend = ModelBackend(provider, budget=budget)
        objective = Objective("run two roles concurrently")

        results = await asyncio.gather(
            _execute(backend, objective, "first"),
            _execute(backend, objective, "second"),
        )

        self.assertTrue(all(result.success for result in results))
        self.assertEqual(provider.max_in_flight, 2)
        self.assertEqual(budget.episodes_used, 2)
        self.assertEqual(budget.tool_calls_used, 2)

    async def test_contention_rejects_overcommit_before_second_provider_call(
        self,
    ) -> None:
        release = threading.Event()
        provider = ConcurrentProvider(release=release)
        budget = AutonomyBudget(2, 1, 100.0)
        backend = ModelBackend(provider, budget=budget)
        objective = Objective("respect one shared model call")

        first = asyncio.create_task(_execute(backend, objective, "first"))
        started = await asyncio.to_thread(provider.started.wait, 3)
        self.assertTrue(started)
        second = asyncio.create_task(_execute(backend, objective, "second"))
        await asyncio.sleep(0)
        release.set()
        outcomes = await asyncio.gather(first, second, return_exceptions=True)

        self.assertEqual(sum(isinstance(item, BudgetExceeded) for item in outcomes), 1)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(budget.episodes_used, 1)
        self.assertEqual(budget.tool_calls_used, 1)

    async def test_failed_pre_call_reservation_releases_episode_slot(self) -> None:
        provider = ConcurrentProvider()
        budget = AutonomyBudget(
            1,
            1,
            0.1,
            max_compute_units_per_episode=0.1,
        )
        backend = ModelBackend(provider, budget=budget)
        objective = Objective("reject an oversized request")

        with self.assertRaises(BudgetExceeded):
            await _execute(backend, objective, "oversized")

        self.assertEqual(provider.calls, 0)
        self.assertEqual(budget.episodes_used, 0)
        self.assertEqual(budget.tool_calls_used, 0)


if __name__ == "__main__":
    unittest.main()
