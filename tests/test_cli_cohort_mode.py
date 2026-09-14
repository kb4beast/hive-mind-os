from __future__ import annotations

import argparse
import asyncio
import io
import json
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace

from hive_mind_os import cli
from hive_mind_os.outcome_graph import OutcomeGraphSpec, OutcomeWorkPackage
from hive_mind_os.whole_os_service import ServiceError


class WholeOSCohortCLITests(unittest.TestCase):
    def test_direct_kernel_cli_defaults_to_cohort_with_strict_opt_out(self) -> None:
        parser = cli.build_parser()

        self.assertEqual(parser.parse_args(["ship it"]).execution_mode, "cohort")
        self.assertEqual(
            parser.parse_args(["ship it", "--execution-mode", "strict"]).execution_mode,
            "strict",
        )

    def test_direct_kernel_cli_reports_selected_mode(self) -> None:
        output = io.StringIO()
        args = cli.build_parser().parse_args(["ship it", "--execution-mode", "strict"])

        with redirect_stdout(output):
            exit_code = asyncio.run(cli._run(args))

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(output.getvalue())["execution_mode"], "strict")

    def test_whole_os_defaults_to_cohort(self) -> None:
        args = cli.build_whole_os_parser().parse_args(
            ["status", "--config", "service.json"]
        )

        self.assertEqual(args.execution_mode, "cohort")
        self.assertIsNone(args.max_parallel_packages)
        execution = cli._whole_os_execution_document(args, graph_maximum=8)
        self.assertEqual(execution["mode"], "cohort")
        self.assertEqual(execution["max_parallel_packages"], 8)
        self.assertEqual(execution["checkpoint"], "cohort_boundary")
        self.assertTrue(str(execution["policy_digest"]).startswith("sha256:"))

    def test_strict_mode_preserves_single_package_compatibility(self) -> None:
        args = cli.build_whole_os_parser().parse_args(
            [
                "status",
                "--config",
                "service.json",
                "--execution-mode",
                "strict",
            ]
        )

        execution = cli._whole_os_execution_document(args, graph_maximum=8)
        self.assertEqual(execution["mode"], "strict")
        self.assertEqual(execution["max_parallel_packages"], 1)
        self.assertEqual(execution["checkpoint"], "per_package")

    def test_cohort_mode_uses_the_graph_concurrency_limit(self) -> None:
        args = cli.build_whole_os_parser().parse_args(
            ["inspect", "--config", "service.json", "--execution-mode", "cohort"]
        )

        execution = cli._whole_os_execution_document(args, graph_maximum=6)
        self.assertEqual(execution["mode"], "cohort")
        self.assertEqual(execution["max_parallel_packages"], 6)
        self.assertEqual(execution["checkpoint"], "cohort_boundary")

    def test_cohort_size_alias_is_capped_by_the_sealed_graph(self) -> None:
        args = cli.build_whole_os_parser().parse_args(
            [
                "run-once",
                "--config",
                "service.json",
                "--execution-mode",
                "cohort",
                "--cohort-size",
                "20",
            ]
        )

        self.assertEqual(args.max_parallel_packages, 20)
        self.assertEqual(
            cli._whole_os_execution_document(args, graph_maximum=4)[
                "max_parallel_packages"
            ],
            4,
        )

    def test_parallel_limit_is_rejected_in_strict_mode(self) -> None:
        args = argparse.Namespace(execution_mode="strict", max_parallel_packages=2)

        with self.assertRaisesRegex(ServiceError, "requires --execution-mode cohort"):
            cli._whole_os_execution_document(args, graph_maximum=8)

    def test_cohort_run_routes_through_one_kickoff_and_terminal_round(self) -> None:
        graph = OutcomeGraphSpec(
            (
                OutcomeWorkPackage("a", ("outcome-a",)),
                OutcomeWorkPackage("b", ("outcome-b",)),
            ),
            "sha256:" + "1" * 64,
            maximum_concurrent=2,
        )
        config = SimpleNamespace(
            campaign_id="campaign",
            tenant_id="tenant",
            repository_id="repository",
            binding_descriptor=SimpleNamespace(digest="sha256:" + "2" * 64),
            graph=graph,
        )
        args = argparse.Namespace(execution_mode="cohort", max_parallel_packages=None)
        execution = cli._whole_os_execution_document(args, graph_maximum=2)

        document = cli._run_unconfigured_cohort(config, execution)

        self.assertEqual(document["status"], "blocked")
        blocked = document["blocked_packages"]
        cohort = document["cohort"]
        self.assertIsInstance(blocked, list)
        self.assertIsInstance(cohort, dict)
        assert isinstance(blocked, list) and isinstance(cohort, dict)
        self.assertEqual(set(blocked), {"a", "b"})
        self.assertEqual(cohort["convergence_rounds"], 1)
        self.assertEqual(cohort["verification_rounds"], 1)
        assurance = document["terminal_assurance"]
        self.assertIsInstance(assurance, dict)
        assert isinstance(assurance, dict)
        self.assertRegex(str(assurance["candidate_digest"]), r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            assurance["producer_identity"], "whole-os-cli-unconfigured-host"
        )
        self.assertEqual(
            assurance["reviewer_identity"], "whole-os-cli-terminal-curator"
        )
        self.assertNotEqual(
            assurance["producer_identity"], assurance["reviewer_identity"]
        )
        self.assertTrue(assurance["review_refs"])
        self.assertTrue(assurance["aggregate_refs"])
        self.assertTrue(assurance["verification_refs"])
        repair = assurance["repair"]
        self.assertIsInstance(repair, dict)
        assert isinstance(repair, dict)
        self.assertFalse(repair["attempted"])
        self.assertIsNone(repair["directive"])
        self.assertIn("hard-gated", str(repair["reason"]))

    def test_help_exposes_mode_and_concurrency_selection(self) -> None:
        parser = cli.build_whole_os_parser()
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit):
            parser.parse_args(["resume", "--help"])
        help_text = output.getvalue()

        self.assertIn("--execution-mode", help_text)
        self.assertIn("--max-parallel-packages", help_text)
        self.assertIn("--cohort-size", help_text)


if __name__ == "__main__":
    unittest.main()
