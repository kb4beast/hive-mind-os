import unittest

from hive_mind_os.role_coverage import ROLES, RoleCoveragePlan, RoleRow, build_coverage


class RoleCoverageTests(unittest.TestCase):
    def rows(self):
        return tuple(
            RoleRow(role, f"identity-{role}", ("package",), (f"ref:{role}",))
            for role in ROLES
        )

    def test_all_eight_distinct_roles_close_one_cohort_receipt(self):
        plan = RoleCoveragePlan("mission", "cohort", "graph", "policy", self.rows())
        receipt = build_coverage(
            plan, {role: ("complete", f"ref:result/{role}") for role in ROLES}
        )
        self.assertTrue(receipt.complete)
        self.assertEqual(len(receipt.results), 8)

    def test_duplicate_role_row_and_missing_evidence_fail_closed(self):
        with self.assertRaises(ValueError):
            RoleCoveragePlan(
                "mission",
                "cohort",
                "graph",
                "policy",
                (*self.rows(), self.rows()[0]),
            )
        rows = list(self.rows())
        rows[0] = RoleRow(ROLES[0], "identity-orchestrator", ("package",), ())
        plan = RoleCoveragePlan("mission", "cohort", "graph", "policy", tuple(rows))
        receipt = build_coverage(
            plan, {role: ("complete", f"ref:result/{role}") for role in ROLES}
        )
        self.assertFalse(receipt.complete)
        self.assertEqual(receipt.missing, ("orchestrator",))


if __name__ == "__main__":
    unittest.main()
