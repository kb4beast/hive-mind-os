"""Compile plan-authored node execution contracts for the local host."""

from __future__ import annotations

from dataclasses import dataclass

from .portable_plan import NodeEffectMode, PortablePlanBundle
from .runtime_contracts import ContractViolation


@dataclass(frozen=True, slots=True)
class CompiledNodeExecution:
    node_id: str
    stage_kind: str
    role: str
    worker_capability: str
    writable: bool
    exclusive_writer: bool
    required_outputs: tuple[str, ...]
    success_transition: str
    failure_transition: str
    retry_policy: str
    cancellation_policy: str


def compile_node_execution(plan: PortablePlanBundle) -> dict[str, CompiledNodeExecution]:
    """Validate generic local-execution semantics without inspecting node ids."""

    capabilities = {item.capability_id: item for item in plan.capabilities}
    adapters = {item.adapter_id for item in plan.adapters}
    compiled: dict[str, CompiledNodeExecution] = {}
    writers: list[CompiledNodeExecution] = []
    for node in plan.nodes:
        execution = node.execution
        if execution is None:
            raise ContractViolation(
                f"node {node.node_id} lacks a plan-authored execution contract"
            )
        if execution.worker_capability not in node.adapter_ids:
            raise ContractViolation(
                f"node {node.node_id} worker capability is not in its adapter lease"
            )
        if execution.worker_capability not in adapters:
            raise ContractViolation(
                f"node {node.node_id} requires an unavailable worker capability"
            )
        if execution.success_transition not in {
            "release-dependents", "selected-experiment-or-no-change"
        }:
            raise ContractViolation(
                f"node {node.node_id} requests an unsupported success transition"
            )
        if execution.retry_policy != "plan-recovery":
            raise ContractViolation(
                f"node {node.node_id} requests an unsupported retry policy"
            )
        if execution.cancellation_policy != "terminate-process-tree":
            raise ContractViolation(
                f"node {node.node_id} requests an unsupported cancellation policy"
            )
        operations = {
            capabilities[capability_id].operation
            for capability_id in node.capability_ids
            if capability_id in capabilities
        }
        writable = execution.effect_mode is NodeEffectMode.BOUNDED_WRITE
        if writable and "local-edit" not in operations:
            raise ContractViolation(
                f"node {node.node_id} declares writes without a local-edit capability"
            )
        if not writable and "local-edit" in operations:
            raise ContractViolation(
                f"node {node.node_id} has an undeclared writable capability"
            )
        item = CompiledNodeExecution(
            node.node_id, execution.stage_kind, execution.execution_role,
            execution.worker_capability, writable, execution.exclusive_writer,
            execution.required_outputs, execution.success_transition,
            execution.failure_transition, execution.retry_policy,
            execution.cancellation_policy,
        )
        compiled[node.node_id] = item
        if writable:
            writers.append(item)
    if any(not item.exclusive_writer for item in writers):
        raise ContractViolation("every writable node requires an exclusive writer lease")
    return compiled


def first_stage(
    compiled: dict[str, CompiledNodeExecution], stage_kind: str,
) -> CompiledNodeExecution | None:
    return next((item for item in compiled.values() if item.stage_kind == stage_kind), None)


__all__ = ["CompiledNodeExecution", "compile_node_execution", "first_stage"]
