from __future__ import annotations

import importlib

import hive_mind_os.roles as legacy_roles
from hive_mind_os.models import Role
from hive_mind_os.reference.package_system import (
    AgentManifest,
    SkillManifest,
    ToolManifest,
    WorkflowManifest,
)
from hive_mind_os.reference.package_system.builtins import hive_core_catalog
from hive_mind_os.roles import DEFAULT_LIFECYCLE, ROLE_CONTRACTS


def test_hive_core_agents_are_lossless_legacy_role_contracts() -> None:
    catalog = hive_core_catalog()
    for role, contract in ROLE_CONTRACTS.items():
        component = catalog.component(f"agent.{role.value}")
        assert isinstance(component, AgentManifest)
        assert component.role_binding == role.value
        assert component.mission == contract.mission
        assert component.required_outputs == contract.required_outputs
        assert component.requested_capabilities == contract.default_capabilities
        assert component.quality_gates == contract.quality_gates
        assert component.skill_ids == (f"skill.{role.value}",)
        skill = catalog.component(component.skill_ids[0])
        assert isinstance(skill, SkillManifest)
        assert set(skill.requested_capabilities) <= set(
            component.requested_capabilities
        )


def test_legacy_role_facade_does_not_load_optional_extension_resources(
    monkeypatch,
) -> None:
    def fail_if_loaded():
        raise AssertionError("optional package loader crossed the runtime import boundary")

    monkeypatch.setattr(
        "hive_mind_os.reference.package_system.builtins.hive_core_catalog",
        fail_if_loaded,
    )
    reloaded = importlib.reload(legacy_roles)
    assert set(reloaded.ROLE_CONTRACTS) == set(Role)
    assert reloaded.DEFAULT_LIFECYCLE == DEFAULT_LIFECYCLE


def test_hive_core_workflow_preserves_default_lifecycle_order() -> None:
    workflow = hive_core_catalog().component("workflow.default-lifecycle")
    assert isinstance(workflow, WorkflowManifest)
    encoded = tuple(
        Role(transition.to_state)
        for transition in workflow.transitions
        if transition.to_state != "complete"
    )
    assert encoded == DEFAULT_LIFECYCLE


def test_hive_core_tools_are_inert_and_bound_without_escalation() -> None:
    catalog = hive_core_catalog()
    for component_id, capability_id in (
        ("tool.repository-inspect", "read_repository"),
        ("tool.evidence-query", "query_ledger"),
        ("tool.contract-validate", "run_contract_tests"),
    ):
        tool = catalog.component(component_id)
        assert isinstance(tool, ToolManifest)
        assert tool.capability_id == capability_id
        assert not tool.side_effecting
        assert not tool.idempotency_required
        assert not tool.rollback_required


def test_declarative_workflows_add_no_war_room_or_promotion_authority() -> None:
    catalog = hive_core_catalog()
    ooda = catalog.component("workflow.ooda")
    challenger = catalog.component("workflow.challenger-experiment")
    assert isinstance(ooda, WorkflowManifest)
    assert isinstance(challenger, WorkflowManifest)
    assert challenger.terminal_states == ("evaluated", "quarantined")
    assert "workflow.war-room" not in {
        component.component_id
        for component in catalog.package("hive-core").components
    }
    assert {"activate", "promote", "accept"}.isdisjoint(
        transition.event for transition in challenger.transitions
    )
