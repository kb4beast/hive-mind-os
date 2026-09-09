from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

from hive_mind_os.compiled_tournament import compile_node_execution
from hive_mind_os.portable_plan import NodeEffectMode, NodeExecutionContract
from tests.test_tournament_plan_factory import authority, evidence, request
from hive_mind_os.plan_generation import PinnedArtifact
from hive_mind_os.tournament_plan_factory import TournamentPlanFactory


class CompiledTournamentTests(unittest.TestCase):
    def setUp(self) -> None:
        standard = Path("docs/execution/DAG_AUTHORING_STANDARD_V2.md").read_bytes()
        self.plan = TournamentPlanFactory().build(
            request(), standard=PinnedArtifact.pin("standard", standard),
            authority=authority(), evidence=evidence(),
        )

    def test_every_fixture_node_declares_plan_driven_execution(self) -> None:
        compiled = compile_node_execution(self.plan)
        self.assertEqual({node.node_id for node in self.plan.nodes}, set(compiled))
        writer = [item for item in compiled.values() if item.writable]
        self.assertEqual(1, len(writer))
        self.assertTrue(writer[0].exclusive_writer)

    def test_arbitrary_node_names_do_not_change_execution_semantics(self) -> None:
        first, second = self.plan.nodes[:2]
        renamed_first = replace(first, node_id="inspect-anything")
        renamed_second = replace(second, node_id="review-anything", dependencies=("inspect-anything",))
        arbitrary = replace(self.plan, plan_id="arbitrary-two-node-fixture", nodes=(renamed_first, renamed_second))
        compiled = compile_node_execution(arbitrary)
        self.assertEqual({"inspect-anything", "review-anything"}, set(compiled))
        self.assertTrue(all(not item.writable for item in compiled.values()))

    def test_undeclared_or_nonexclusive_writes_fail_closed(self) -> None:
        node = self.plan.nodes[0]
        missing = replace(node, execution=None)
        with self.assertRaisesRegex(ValueError, "lacks a plan-authored execution contract"):
            compile_node_execution(replace(self.plan, nodes=(missing,)))
        with self.assertRaisesRegex(ValueError, "exclusive"):
            replace(node, execution=NodeExecutionContract(
                "build", node.roles[0], node.adapter_ids[0], NodeEffectMode.BOUNDED_WRITE,
                False, ("summary",),
            ))

    def test_unsupported_transitions_recovery_and_cancellation_fail_closed(self) -> None:
        node = self.plan.nodes[0]
        assert node.execution is not None
        variants = (
            (replace(node.execution, success_transition="invented-transition"), "success transition"),
            (replace(node.execution, retry_policy="retry-forever"), "retry policy"),
            (replace(node.execution, cancellation_policy="leave-process-running"), "cancellation policy"),
        )
        for execution, message in variants:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                compile_node_execution(replace(self.plan, nodes=(replace(node, execution=execution),)))


if __name__ == "__main__":
    unittest.main()
