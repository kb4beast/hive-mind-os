from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Any, Sequence
from uuid import uuid4

from .agents import Agent, AgentBackend, create_agents
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
from .roles import DEFAULT_LIFECYCLE, ROLE_CONTRACTS, RoleContract


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


class HiveKernel:
    """Coordinates direct agent classes through evidence-bearing contracts."""

    def __init__(
        self,
        backend: AgentBackend | None = None,
        ledger: EvidenceLedger | None = None,
        policy: PolicyEngine | None = None,
        lifecycle: tuple[Role, ...] = DEFAULT_LIFECYCLE,
        agents: Sequence[Agent] | None = None,
    ) -> None:
        self.backend = backend or DeterministicBackend()
        self.ledger = ledger or EvidenceLedger()
        self.policy = policy or PolicyEngine()
        self.lifecycle = lifecycle
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
        run_id = str(uuid4())
        started_at = utc_now()
        results: list[AgentResult] = []
        self.ledger.append_event(
            run_id, "objective.started", Role.ORCHESTRATOR.value, asdict(objective)
        )

        for role in self.lifecycle:
            work_item = WorkItem(
                objective_id=objective.id,
                role=role,
                instruction=ROLE_CONTRACTS[role].mission,
                dependencies=tuple(result.work_item_id for result in results),
            )
            self.ledger.append_event(
                run_id, "work.started", role.value, asdict(work_item)
            )
            try:
                result = await self.agents[role].run(
                    work_item, objective, tuple(results)
                )
                self._validate_result(role, result)
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

    @staticmethod
    def _validate_result(role: Role, result: AgentResult) -> None:
        if result.role is not role:
            raise ValueError(
                f"agent returned result for {result.role}, expected {role}"
            )
        if not result.success:
            raise RuntimeError(result.summary)
        required = set(ROLE_CONTRACTS[role].required_outputs)
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
