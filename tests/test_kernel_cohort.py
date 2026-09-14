from __future__ import annotations

import asyncio
import unittest

from hive_mind_os.agents import RoleContract
from hive_mind_os.models import (
    AgentResult,
    Evidence,
    Objective,
    Role,
    WorkItem,
    WorkStatus,
)
from hive_mind_os.roles import DEFAULT_LIFECYCLE
from hive_mind_os.runtime import ExecutionStrategy, HiveKernel


def _result(contract: RoleContract, work_item: WorkItem) -> AgentResult:
    return AgentResult(
        role=contract.role,
        work_item_id=work_item.id,
        summary=f"{contract.role.value} complete",
        evidence=tuple(
            Evidence("contract-output", output, "test")
            for output in contract.required_outputs
        ),
    )


class _CohortProbeBackend:
    def __init__(self) -> None:
        self.started: set[Role] = set()
        self.all_specialists_started = asyncio.Event()
        self.release = asyncio.Event()
        self.curator_context: tuple[Role, ...] = ()

    async def execute(
        self,
        contract: RoleContract,
        work_item: WorkItem,
        objective: Objective,
        context: tuple[AgentResult, ...],
    ) -> AgentResult:
        del objective
        if contract.role is Role.CURATOR:
            self.curator_context = tuple(item.role for item in context)
            return _result(contract, work_item)
        self.started.add(contract.role)
        if len(self.started) == len(DEFAULT_LIFECYCLE) - 1:
            self.all_specialists_started.set()
        await self.release.wait()
        return _result(contract, work_item)


class _ContextProbeBackend:
    def __init__(self) -> None:
        self.context_sizes: list[int] = []

    async def execute(
        self,
        contract: RoleContract,
        work_item: WorkItem,
        objective: Objective,
        context: tuple[AgentResult, ...],
    ) -> AgentResult:
        del objective
        self.context_sizes.append(len(context))
        return _result(contract, work_item)


class KernelCohortTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_runs_one_parallel_room_then_one_convergence(self) -> None:
        backend = _CohortProbeBackend()
        kernel = HiveKernel(backend=backend)
        running = asyncio.create_task(kernel.run_objective(Objective("ship it")))

        await asyncio.wait_for(backend.all_specialists_started.wait(), timeout=1)
        self.assertFalse(running.done())
        self.assertNotIn(Role.CURATOR, backend.started)
        backend.release.set()
        report = await asyncio.wait_for(running, timeout=1)

        self.assertIs(report.status, WorkStatus.SUCCEEDED)
        self.assertEqual(
            tuple(result.role for result in report.results), DEFAULT_LIFECYCLE
        )
        self.assertEqual(
            set(backend.curator_context), set(DEFAULT_LIFECYCLE) - {Role.CURATOR}
        )
        event_types = [event["event_type"] for event in kernel.ledger.events()]
        self.assertEqual(event_types.count("cohort.kickoff"), 1)
        self.assertEqual(event_types.count("cohort.converged"), 1)

    async def test_sequential_strategy_remains_an_explicit_compatibility_mode(
        self,
    ) -> None:
        backend = _ContextProbeBackend()
        report = await HiveKernel(
            backend=backend, execution_strategy=ExecutionStrategy.SEQUENTIAL
        ).run_objective(Objective("legacy ordering"))

        self.assertIs(report.status, WorkStatus.SUCCEEDED)
        self.assertEqual(backend.context_sizes, list(range(len(DEFAULT_LIFECYCLE))))


if __name__ == "__main__":
    unittest.main()
