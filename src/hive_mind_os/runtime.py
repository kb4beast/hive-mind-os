from __future__ import annotations

import asyncio
from dataclasses import asdict
from enum import StrEnum
from typing import Any, Sequence
from uuid import uuid4

from .agents import Agent, AgentBackend, RoleContract, create_agents
from .ledger import EvidenceLedger
from .models import (
    AgentResult,
    Evidence,
    Objective,
    Role,
    RunReport,
    WorkItem,
    WorkStatus,
    utc_now,
)
from .policy import PolicyEngine
from .roles import DEFAULT_LIFECYCLE, ROLE_CONTRACTS


class DeterministicBackend:
    """Offline backend used for bootstrap, tests, and safe dry runs."""

    async def execute(
        self,
        contract: RoleContract,
        work_item: WorkItem,
        objective: Objective,
        context: tuple[AgentResult, ...],
    ) -> AgentResult:
        await asyncio.sleep(0)
        evidence = tuple(
            Evidence(
                kind="contract-output",
                summary=output,
                source=f"role:{contract.role.value}",
                payload={"objective": objective.goal, "prior_results": len(context)},
            )
            for output in contract.required_outputs
        )
        return AgentResult(
            role=contract.role,
            work_item_id=work_item.id,
            summary=f"{contract.role.value} completed its bounded contract",
            evidence=evidence,
            lessons=(f"validated bootstrap contract for {contract.role.value}",),
        )


class SpecialistAgent:
    def __init__(self, contract: RoleContract, backend: AgentBackend) -> None:
        self.contract = contract
        self.backend = backend

    async def run(
        self,
        work_item: WorkItem,
        objective: Objective,
        context: tuple[AgentResult, ...],
    ) -> AgentResult:
        work_item.status = WorkStatus.RUNNING
        result = await self.backend.execute(
            self.contract, work_item, objective, context
        )
        work_item.status = WorkStatus.SUCCEEDED if result.success else WorkStatus.FAILED
        return result


class ExecutionStrategy(StrEnum):
    """Scheduling strategy for the direct specialist runtime."""

    COHORT = "cohort"
    SEQUENTIAL = "sequential"


class HiveKernel:
    """Coordinates direct agent classes through evidence-bearing contracts."""

    def __init__(
        self,
        backend: AgentBackend | None = None,
        ledger: EvidenceLedger | None = None,
        policy: PolicyEngine | None = None,
        lifecycle: tuple[Role, ...] = DEFAULT_LIFECYCLE,
        agents: Sequence[Agent] | None = None,
        execution_strategy: ExecutionStrategy | str = ExecutionStrategy.COHORT,
    ) -> None:
        self.backend = backend or DeterministicBackend()
        self.ledger = ledger or EvidenceLedger()
        self.policy = policy or PolicyEngine()
        self.lifecycle = lifecycle
        self.execution_strategy = ExecutionStrategy(execution_strategy)
        direct_agents = (
            tuple(agents)
            if agents is not None
            else create_agents(self.backend, lifecycle)
        )
        if tuple(agent.role for agent in direct_agents) != lifecycle:
            raise ValueError(
                "direct agents must match the configured lifecycle exactly"
            )
        self.agents: dict[Role, Agent] = {agent.role: agent for agent in direct_agents}

    async def run_objective(self, objective: Objective) -> RunReport:
        """Run an objective using the configured scheduling strategy.

        Cohort mode is the default: every non-curator specialist receives the
        same immutable kickoff context and runs concurrently.  Their complete
        result set then goes to the Curator once for terminal convergence.  The
        legacy sequential lifecycle remains available for compatibility.
        """

        if self.execution_strategy is ExecutionStrategy.SEQUENTIAL:
            return await self._run_sequential(objective)
        return await self._run_cohort(objective)

    async def _run_sequential(self, objective: Objective) -> RunReport:
        run_id = str(uuid4())
        started_at = utc_now()
        results: list[AgentResult] = []
        self.ledger.append_event(
            run_id, "objective.started", Role.ORCHESTRATOR.value, asdict(objective)
        )

        for role in self.lifecycle:
            agent = self.agents[role]
            work_item = WorkItem(
                objective_id=objective.id,
                role=role,
                instruction=agent.contract.mission,
                dependencies=tuple(result.work_item_id for result in results),
            )
            self.ledger.append_event(
                run_id, "work.started", role.value, asdict(work_item)
            )
            try:
                result = await agent.run(work_item, objective, tuple(results))
                self._validate_result(agent, result)
            except Exception as exc:
                work_item.status = WorkStatus.FAILED
                self.ledger.append_event(
                    run_id,
                    "work.failed",
                    role.value,
                    {
                        "work_item_id": work_item.id,
                        "error": type(exc).__name__,
                        "message": str(exc),
                    },
                )
                return RunReport(
                    run_id=run_id,
                    objective_id=objective.id,
                    results=tuple(results),
                    status=WorkStatus.FAILED,
                    started_at=started_at,
                    completed_at=utc_now(),
                )

            results.append(result)
            event_sequence = self.ledger.append_event(
                run_id,
                "work.completed",
                role.value,
                self._result_payload(result),
            )
            self.ledger.append_lessons(
                run_id, role.value, result.lessons, event_sequence
            )

        self.ledger.append_event(
            run_id,
            "objective.completed",
            Role.ORCHESTRATOR.value,
            {"objective_id": objective.id, "result_count": len(results)},
        )
        return RunReport(
            run_id=run_id,
            objective_id=objective.id,
            results=tuple(results),
            status=WorkStatus.SUCCEEDED,
            started_at=started_at,
            completed_at=utc_now(),
        )

    async def _run_cohort(self, objective: Objective) -> RunReport:
        run_id = str(uuid4())
        started_at = utc_now()
        self.ledger.append_event(
            run_id,
            "objective.started",
            Role.ORCHESTRATOR.value,
            {**asdict(objective), "execution_strategy": ExecutionStrategy.COHORT.value},
        )

        convergence_role = Role.CURATOR if Role.CURATOR in self.lifecycle else None
        cohort_roles = tuple(
            role for role in self.lifecycle if role is not convergence_role
        )
        work_items = {
            role: WorkItem(
                objective_id=objective.id,
                role=role,
                instruction=self.agents[role].contract.mission,
            )
            for role in cohort_roles
        }
        self.ledger.append_event(
            run_id,
            "cohort.kickoff",
            Role.ORCHESTRATOR.value,
            {
                "objective_id": objective.id,
                "roles": [role.value for role in cohort_roles],
                "shared_context": "objective-only",
                "convergence_role": None
                if convergence_role is None
                else convergence_role.value,
            },
        )
        for role in cohort_roles:
            self.ledger.append_event(
                run_id, "work.started", role.value, asdict(work_items[role])
            )

        async def execute(role: Role) -> AgentResult:
            agent = self.agents[role]
            result = await agent.run(work_items[role], objective, ())
            self._validate_result(agent, result)
            return result

        raw_outcomes = await asyncio.gather(
            *(execute(role) for role in cohort_roles), return_exceptions=True
        )
        results_by_role: dict[Role, AgentResult] = {}
        failed = False
        for role, outcome in zip(cohort_roles, raw_outcomes, strict=True):
            work_item = work_items[role]
            if isinstance(outcome, BaseException):
                failed = True
                work_item.status = WorkStatus.FAILED
                self.ledger.append_event(
                    run_id,
                    "work.failed",
                    role.value,
                    {
                        "work_item_id": work_item.id,
                        "error": type(outcome).__name__,
                        "message": str(outcome),
                    },
                )
                continue
            results_by_role[role] = outcome
            event_sequence = self.ledger.append_event(
                run_id, "work.completed", role.value, self._result_payload(outcome)
            )
            self.ledger.append_lessons(
                run_id, role.value, outcome.lessons, event_sequence
            )

        if failed:
            self.ledger.append_event(
                run_id,
                "cohort.failed",
                Role.ORCHESTRATOR.value,
                {
                    "completed_roles": [role.value for role in results_by_role],
                    "failed_roles": [
                        role.value
                        for role in cohort_roles
                        if role not in results_by_role
                    ],
                },
            )
            return RunReport(
                run_id=run_id,
                objective_id=objective.id,
                results=self._ordered_results(results_by_role),
                status=WorkStatus.FAILED,
                started_at=started_at,
                completed_at=utc_now(),
            )

        if convergence_role is not None:
            role = convergence_role
            agent = self.agents[role]
            context = self._ordered_results(results_by_role)
            work_item = WorkItem(
                objective_id=objective.id,
                role=role,
                instruction=agent.contract.mission,
                dependencies=tuple(item.work_item_id for item in context),
            )
            self.ledger.append_event(
                run_id, "work.started", role.value, asdict(work_item)
            )
            try:
                result = await agent.run(work_item, objective, context)
                self._validate_result(agent, result)
            except Exception as exc:
                work_item.status = WorkStatus.FAILED
                self.ledger.append_event(
                    run_id,
                    "work.failed",
                    role.value,
                    {
                        "work_item_id": work_item.id,
                        "error": type(exc).__name__,
                        "message": str(exc),
                    },
                )
                return RunReport(
                    run_id=run_id,
                    objective_id=objective.id,
                    results=self._ordered_results(results_by_role),
                    status=WorkStatus.FAILED,
                    started_at=started_at,
                    completed_at=utc_now(),
                )
            results_by_role[role] = result
            event_sequence = self.ledger.append_event(
                run_id, "work.completed", role.value, self._result_payload(result)
            )
            self.ledger.append_lessons(
                run_id, role.value, result.lessons, event_sequence
            )

        ordered_results = self._ordered_results(results_by_role)
        self.ledger.append_event(
            run_id,
            "cohort.converged",
            Role.ORCHESTRATOR.value,
            {
                "objective_id": objective.id,
                "result_count": len(ordered_results),
                "convergence_rounds": 1,
            },
        )
        self.ledger.append_event(
            run_id,
            "objective.completed",
            Role.ORCHESTRATOR.value,
            {"objective_id": objective.id, "result_count": len(ordered_results)},
        )
        return RunReport(
            run_id=run_id,
            objective_id=objective.id,
            results=ordered_results,
            status=WorkStatus.SUCCEEDED,
            started_at=started_at,
            completed_at=utc_now(),
        )

    def _ordered_results(
        self, results_by_role: dict[Role, AgentResult]
    ) -> tuple[AgentResult, ...]:
        return tuple(
            results_by_role[role] for role in self.lifecycle if role in results_by_role
        )

    @staticmethod
    def _validate_result(agent: Agent | Role, result: AgentResult) -> None:
        """Validate direct runtime results and retain the legacy helper signature."""

        if isinstance(agent, Agent):
            role = agent.role
            required = set(agent.contract.required_outputs)
        else:
            role = agent
            required = set(ROLE_CONTRACTS[role].required_outputs)
        if result.role is not role:
            raise ValueError(
                f"agent returned result for {result.role}, expected {role}"
            )
        if not result.success:
            raise RuntimeError(result.summary)
        observed = {
            item.summary for item in result.evidence if item.kind == "contract-output"
        }
        missing = required - observed
        if missing:
            raise ValueError(
                f"{role.value} omitted required evidence: {sorted(missing)}"
            )

    @staticmethod
    def _result_payload(result: AgentResult) -> dict[str, Any]:
        return {
            "work_item_id": result.work_item_id,
            "summary": result.summary,
            "success": result.success,
            "evidence": [asdict(item) for item in result.evidence],
            "proposed_actions": list(result.proposed_actions),
            "lessons": list(result.lessons),
        }
