from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from hive_mind_os import cli
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

    def test_normalization_is_canonical_by_identifier(self) -> None:
        alpha = AcceptanceSpecification("alpha", "alpha criterion", ("command",))
        self.assertEqual(
            normalize_acceptance_specifications((self.specification, alpha)),
            normalize_acceptance_specifications((alpha, self.specification)),
        )

    def test_schema_limits_are_enforced_at_construction(self) -> None:
        with self.assertRaisesRegex(AcceptanceSpecificationError, "4000"):
            AcceptanceSpecification("long-criterion", "x" * 4001, ("command",))
        with self.assertRaisesRegex(AcceptanceSpecificationError, "128"):
            AcceptanceSpecification(
                "too-many-arguments", "criterion", tuple("command" for _ in range(129))
            )

    def test_untyped_criterion_cannot_start_a_delivery(self) -> None:
        with self.assertRaisesRegex(ValueError, "typed executable"):
            RepositoryMission(
                self.fixture.root,
                "Fix increment",
                acceptance_criteria=(self.specification.criterion,),
                backend=ScriptedRepositoryBackend(),
                pin=self.fixture.commit_two,
                output_dir=self.root / "output",
            )

    def test_curator_requires_an_exact_specification_bound_check(self) -> None:
        review = CuratorReview(
            "acceptance-run",
            EvidenceLedger(),
            objective="Fix increment",
            acceptance_criteria=(self.specification.criterion,),
            acceptance_specifications=(self.specification,),
            base_workspace=self.fixture.root,
        )
        forged = AcceptanceCheck(
            "forged",
            (sys.executable, "-B", "-c", "pass"),
            criteria=(self.specification.criterion,),
            specification_id=self.specification.identifier,
            specification_digest=self.specification.digest,
        )
        with self.assertRaisesRegex(ContaminationError, "does not exactly match"):
            review.seal((forged,))

    def test_receipt_must_bind_the_specification_and_requested_argv(self) -> None:
        review = CuratorReview(
            "acceptance-run",
            EvidenceLedger(),
            objective="Fix increment",
            acceptance_criteria=(self.specification.criterion,),
            acceptance_specifications=(self.specification,),
            base_workspace=self.fixture.root,
        )
        check = AcceptanceCheck(
            "increment-contract",
            self.specification.argv,
            criteria=(self.specification.criterion,),
            specification_id=self.specification.identifier,
            specification_digest=self.specification.digest,
        )
        review.seal((check,))

        def runner(current: AcceptanceCheck):
            return (
                {
                    "result": "succeeded",
                    "execution": {
                        "requested_argv": list(current.argv),
                        "argv": ["wrong-command"],
                        "acceptance_specification": {
                            "id": current.specification_id,
                            "digest": current.specification_digest,
                        },
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
            any(
                item["receipt_binding"] == "executed-argv-mismatch"
                for item in verdict.acceptance_results
            )
        )

    def test_cli_loader_rejects_non_object_documents(self) -> None:
        path = self.root / "acceptance.json"
        path.write_text(json.dumps([self.specification.to_dict()]), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "must be a JSON object"):
            cli._load_acceptance_specifications((str(path),))


if __name__ == "__main__":
    unittest.main()
