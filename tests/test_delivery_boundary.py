from __future__ import annotations

import unittest
from pathlib import Path

from hive_mind_os.delivery_boundary import (
    DeliveryBoundaryError,
    external_delivery_boundary_findings,
    is_hivemind_source_tree,
    require_external_delivery_independence,
)


class DeliveryBoundaryTests(unittest.TestCase):
    def test_identifies_the_hivemind_source_tree(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        self.assertTrue(is_hivemind_source_tree(repository))
        self.assertFalse(is_hivemind_source_tree(repository / "tests"))

    def test_ordinary_application_source_with_a_generic_graph_term_is_allowed(
        self,
    ) -> None:
        require_external_delivery_independence(
            (
                (
                    "src/application.py",
                    b"def topological_order(graph: dict[str, set[str]]) -> list[str]:\n    return []\n",
                ),
                (
                    "tests/test_application.py",
                    b"def test_graph_order() -> None:\n    assert True\n",
                ),
            )
        )

    def test_hivemind_runtime_and_workspace_references_are_rejected(self) -> None:
        findings = external_delivery_boundary_findings(
            (
                (
                    "src/application.py",
                    b"from hive_mind_os.dag_executor import DagExecutor\n",
                ),
                ("config/runtime.toml", b"state = '.hive-mind/run-state'\n"),
                ("requirements.txt", b"hive-mind-os==1.0\n"),
            )
        )
        self.assertEqual(
            findings,
            (
                "config/runtime.toml: HiveMind workspace reference",
                "requirements.txt: HiveMind runtime dependency",
                "src/application.py: HiveMind runtime dependency",
            ),
        )
        with self.assertRaises(DeliveryBoundaryError):
            require_external_delivery_independence(
                (("src/application.py", b"from hive_mind_os import runtime\n"),)
            )

    def test_hivemind_can_deliver_its_own_runtime_without_waiving_other_guards(
        self,
    ) -> None:
        require_external_delivery_independence(
            (
                (
                    "src/hive_mind_os/runtime.py",
                    b"from hive_mind_os.models import Role\n",
                ),
            ),
            allow_hivemind_runtime_dependencies=True,
        )
        findings = external_delivery_boundary_findings(
            (("plans/dags/candidate/plan.json", b"{}"),),
            allow_hivemind_runtime_dependencies=True,
        )
        self.assertEqual(
            findings, ("plans/dags/candidate/plan.json: DAG plan artifact",)
        )

    def test_dag_plan_artifacts_and_source_paths_are_rejected(self) -> None:
        findings = external_delivery_boundary_findings(
            (
                ("Brain/plans/dags/candidate/plan.json", b"{}"),
                ("src/config.py", b"PLAN = 'Brain/plans/dags/candidate/plan.json'\n"),
            )
        )
        self.assertEqual(
            findings,
            (
                "Brain/plans/dags/candidate/plan.json: DAG plan artifact",
                "src/config.py: DAG plan-directory reference",
            ),
        )
