from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from hive_mind_os.acceptance import (
    AcceptanceSpecification,
    AcceptanceSpecificationError,
    normalize_acceptance_specifications,
)
from hive_mind_os.curator import AcceptanceCheck, ContaminationError, CuratorReview
from hive_mind_os.ledger import EvidenceLedger
from hive_mind_os.mission import RepositoryMission, ScriptedRepositoryBackend
from tests.fixtures.fixture_repo import build_fixture_repo


class AcceptanceSpecificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fixture = build_fixture_repo(self.root / "repository")
        self.specification = AcceptanceSpecification(
            "increment-returns-two",
            "increment(1) returns 2",
            (
                sys.executable,
                "-B",
                "-c",
                "from tiny_pkg.maths import increment; assert increment(1) == 2",
            ),
        )

    def review(self) -> CuratorReview:
        return CuratorReview(
            "acceptance-run",
            EvidenceLedger(),
            objective="Fix increment",
            acceptance_criteria=(self.specification.criterion,),
            acceptance_specifications=(self.specification,),
            base_workspace=self.fixture.root,
        )

    def check(self) -> AcceptanceCheck:
        return AcceptanceCheck(
            "increment-contract",
            self.specification.argv,
            criteria=(self.specification.criterion,),
            specification_id=self.specification.identifier,
            specification_digest=self.specification.digest,
        )

    def test_normalization_is_canonical_by_identifier(self) -> None:
        alpha = AcceptanceSpecification(
            "alpha",
            "alpha criterion",
            (sys.executable, "-B", "-c", "pass"),
        )
        self.assertEqual(
            normalize_acceptance_specifications((self.specification, alpha)),
            normalize_acceptance_specifications((alpha, self.specification)),
        )

    def test_direct_specification_construction_matches_schema_size_limits(self) -> None:
        with self.assertRaisesRegex(AcceptanceSpecificationError, "4000"):
            AcceptanceSpecification("long-criterion", "x" * 4001, ("command",))
        with self.assertRaisesRegex(AcceptanceSpecificationError, "128"):
            AcceptanceSpecification(
                "too-many-arguments",
                "criterion",
                tuple("command" for _ in range(129)),
            )
        with self.assertRaisesRegex(AcceptanceSpecificationError, "16384"):
            AcceptanceSpecification(
                "long-argument", "criterion", ("x" * 16385,)
            )

    def test_untyped_criterion_cannot_start_a_delivery(self) -> None:
        with self.assertRaisesRegex(ValueError, "typed executable"):
            RepositoryMission(
                self.fixture.root,
                "Fix increment",
                acceptance_criteria=("increment(1) returns 2",),
                backend=ScriptedRepositoryBackend(),
                pin=self.fixture.commit_two,
                output_dir=self.root / "output",
            )

    def test_direct_curator_review_rejects_an_untyped_criterion(self) -> None:
        with self.assertRaisesRegex(ContaminationError, "typed executable"):
            CuratorReview(
                "untyped",
                EvidenceLedger(),
                objective="Fix increment",
                acceptance_criteria=("increment(1) returns 2",),
                base_workspace=self.fixture.root,
            )

    def test_seal_rejects_a_command_that_does_not_equal_the_specification(self) -> None:
        review = self.review()
        forged = AcceptanceCheck(
            "forged",
            (sys.executable, "-B", "-c", "pass"),
            criteria=(self.specification.criterion,),
            specification_id=self.specification.identifier,
            specification_digest=self.specification.digest,
        )
        with self.assertRaisesRegex(ContaminationError, "does not exactly match"):
            review.seal((forged,))

    def test_reproduction_rejects_a_receipt_with_the_wrong_executed_command(self) -> None:
        review = self.review()
        review.seal((self.check(),))

        def runner(check: AcceptanceCheck):
            return (
                {
                    "result": "succeeded",
                    "execution": {
                        "requested_argv": list(check.argv),
                        "argv": ["wrong-command"],
                        "acceptance_specification": {
                            "id": check.specification_id,
                            "digest": check.specification_digest,
                        }
                        if check.specification_id is not None
                        else None,
                        "outcome": "succeeded",
                        "exit_code": 0,
                        "stdout": {"truncated": False},
                        "stderr": {"truncated": False},
                    },
                },
                (),
            )

        verdict, _ = review.reproduce(
            head_workspace=self.fixture.root,
            declared_paths=(),
            command_runner=runner,
            repository_test_argv=self.specification.argv,
            delivery_verifier=lambda: (True, ()),
            provenance_resolves=True,
            license_evaluated=True,
        )
        self.assertEqual(verdict.decision, "reject")
        self.assertTrue(
            all(
                item["receipt_binding"] == "executed-argv-mismatch"
                for item in verdict.acceptance_results
            )
        )

    def test_timeout_and_truncated_output_cannot_satisfy_expected_failure(self) -> None:
        failure = AcceptanceSpecification(
            "negative-case",
            "invalid input is rejected",
            (sys.executable, "-B", "-c", "raise SystemExit(1)"),
            expected="failed",
        )
        review = CuratorReview(
            "timeout",
            EvidenceLedger(),
            objective="Reject invalid input",
            acceptance_criteria=(failure.criterion,),
            acceptance_specifications=(failure,),
            base_workspace=self.fixture.root,
        )
        check = AcceptanceCheck(
            "negative-case",
            failure.argv,
            expected="failed",
            criteria=(failure.criterion,),
            specification_id=failure.identifier,
            specification_digest=failure.digest,
        )
        review.seal((check,))

        def runner(current: AcceptanceCheck):
            return (
                {
                    "result": "failed",
                    "execution": {
                        "requested_argv": list(current.argv),
                        "argv": list(current.argv),
                        "acceptance_specification": {
                            "id": current.specification_id,
                            "digest": current.specification_digest,
                        }
                        if current.specification_id is not None
                        else None,
                        "outcome": "timeout",
                        "exit_code": None,
                        "stdout": {"truncated": True},
                        "stderr": {"truncated": False},
                    },
                },
                (),
            )

        verdict, _ = review.reproduce(
            head_workspace=self.fixture.root,
            declared_paths=(),
            command_runner=runner,
            repository_test_argv=failure.argv,
            delivery_verifier=lambda: (True, ()),
            provenance_resolves=True,
            license_evaluated=True,
        )
        self.assertEqual(verdict.decision, "reject")
        self.assertTrue(
            any(
                item["receipt_binding"] == "invalid-execution-outcome"
                for item in verdict.acceptance_results
            )
        )

    def test_expected_failure_with_a_nonzero_exit_is_accepted(self) -> None:
        failure = AcceptanceSpecification(
            "negative-case",
            "invalid input is rejected",
            (sys.executable, "-B", "-c", "raise SystemExit(1)"),
            expected="failed",
        )
        review = CuratorReview(
            "expected-failure",
            EvidenceLedger(),
            objective="Reject invalid input",
            acceptance_criteria=(failure.criterion,),
            acceptance_specifications=(failure,),
            base_workspace=self.fixture.root,
        )
        check = AcceptanceCheck(
            "negative-case",
            failure.argv,
            expected="failed",
            criteria=(failure.criterion,),
            specification_id=failure.identifier,
            specification_digest=failure.digest,
        )
        review.seal((check,))

        def runner(current: AcceptanceCheck):
            return (
                {
                    "result": "failed",
                    "execution": {
                        "requested_argv": list(current.argv),
                        "argv": list(current.argv),
                        "acceptance_specification": {
                            "id": current.specification_id,
                            "digest": current.specification_digest,
                        },
                        "outcome": "failed",
                        "exit_code": 1,
                        "stdout": {"truncated": False},
                        "stderr": {"truncated": False},
                    },
                },
                (),
            )

        verdict, _ = review.reproduce(
            head_workspace=self.fixture.root,
            declared_paths=(),
            command_runner=runner,
            repository_test_argv=failure.argv,
            delivery_verifier=lambda: (True, ()),
            provenance_resolves=True,
            license_evaluated=True,
        )
        self.assertEqual(verdict.decision, "adopt")


if __name__ == "__main__":
    unittest.main()
