import unittest

from hive_mind_os.builder_session import (
    BuilderDisposition,
    BuilderSession,
    BuilderSessionResult,
    BuilderSessionSpec,
)


class BuilderSessionTests(unittest.TestCase):
    def spec(self, **changes):
        values = {
            "package_id": "package",
            "attempt_id": "attempt",
            "tenant_id": "tenant",
            "starting_candidate": "base",
            "allowed_paths": ("src",),
            "max_tools": 1,
            "max_repairs": 1,
            "max_seconds": 1.0,
        }
        values.update(changes)
        return BuilderSessionSpec(**values)

    def test_path_tool_and_repair_budgets_are_enforced(self):
        session = BuilderSession(self.spec())
        session.record_tool("edit")
        with self.assertRaises(RuntimeError):
            session.record_tool("test")
        self.assertTrue(session.record_failure("first"))
        self.assertFalse(session.record_failure("first"))
        with self.assertRaises(RuntimeError):
            session.record_failure("second")
        with self.assertRaises(PermissionError):
            session.validate_paths(("../other/repo",))

    def test_wall_time_budget_cannot_return_ready_for_verification(self):
        ticks = iter((0.0, 2.0))
        session = BuilderSession(self.spec(), clock=lambda: next(ticks))
        result = session.run(
            lambda _: BuilderSessionResult(
                BuilderDisposition.READY_FOR_VERIFICATION,
                "candidate",
                ("src/main.py",),
            )
        )
        self.assertEqual(result.disposition, BuilderDisposition.BUDGET_EXHAUSTED)
        self.assertIsNone(result.candidate)


if __name__ == "__main__":
    unittest.main()
