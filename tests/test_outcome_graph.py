import unittest

from hive_mind_os.outcome_graph import (
    GraphError,
    OutcomeWorkPackage,
    compile_outcome_graph,
    dispatch_rounds,
)


class OutcomeGraphTests(unittest.TestCase):
    def test_dependency_ready_work_fans_out_with_capacity(self):
        graph = compile_outcome_graph(
            (
                OutcomeWorkPackage("root", ("R1",), allowed_paths=("root",)),
                OutcomeWorkPackage(
                    "a", ("R2",), ("root",), allowed_paths=("a",)
                ),
                OutcomeWorkPackage(
                    "b", ("R3",), ("root",), allowed_paths=("b",)
                ),
            ),
            base_snapshot="a" * 40,
            maximum_concurrent=2,
            court_receipt="ref:court/1",
        )
        self.assertEqual(dispatch_rounds(graph), (("root",), ("a", "b")))

    def test_cycles_missing_dependencies_and_parallel_writer_collisions_fail(self):
        with self.assertRaises(GraphError):
            compile_outcome_graph(
                (OutcomeWorkPackage("a", ("R",), ("missing",)),),
                base_snapshot="a" * 40,
            )
        with self.assertRaises(GraphError):
            compile_outcome_graph(
                (
                    OutcomeWorkPackage("a", ("R",), ("b",)),
                    OutcomeWorkPackage("b", ("R",), ("a",)),
                ),
                base_snapshot="a" * 40,
            )
        with self.assertRaises(GraphError):
            compile_outcome_graph(
                (
                    OutcomeWorkPackage("a", ("R",), allowed_paths=("same",)),
                    OutcomeWorkPackage("b", ("R",), allowed_paths=("same",)),
                ),
                base_snapshot="a" * 40,
                maximum_concurrent=2,
            )


if __name__ == "__main__":
    unittest.main()
