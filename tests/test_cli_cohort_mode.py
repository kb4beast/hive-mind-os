from __future__ import annotations

import argparse
import asyncio
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from hive_mind_os import cli
from hive_mind_os.outcome_graph import OutcomeGraphSpec, OutcomeWorkPackage
from hive_mind_os.scheduler import Scheduler
from hive_mind_os.whole_os_bootstrap import WholeOSHostUnavailable
from hive_mind_os.whole_os_service import ServiceError, WholeOSService


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

    def test_cohort_start_routes_through_real_service_to_completion(self) -> None:
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
        args = cli.build_whole_os_parser().parse_args(
            ["start", "--config", "service.json", "--json"]
        )
        observation = SimpleNamespace(
            campaign_id="campaign",
            status="complete",
            completed_packages=("a", "b"),
            pending_packages=(),
            blocked_packages=(),
            last_result=None,
        )
        service = Mock()
        service.run_to_completion.return_value = observation
        registry = Mock()
        registry.resolve.return_value = SimpleNamespace(
            bindings="bindings", host="host"
        )
        output = io.StringIO()

        with (
            patch.object(cli, "load_service_config", return_value=config),
            patch.object(cli, "WholeOSService", return_value=service) as service_type,
            redirect_stdout(output),
        ):
            exit_code = cli._run_whole_os(args, host_factories=registry)

        self.assertEqual(exit_code, 0)
        registry.resolve.assert_called_once_with(config)
        service_type.assert_called_once_with(config, "bindings", "host")
        service.run_to_completion.assert_called_once_with()
        service.run_cohort.assert_not_called()
        service.close.assert_called_once_with()
        self.assertEqual(json.loads(output.getvalue())["status"], "complete")

    def test_cohort_run_once_routes_through_real_service_cohort(self) -> None:
        graph = OutcomeGraphSpec(
            (OutcomeWorkPackage("a", ("outcome-a",)),),
            "sha256:" + "1" * 64,
        )
        config = SimpleNamespace(
            campaign_id="campaign",
            tenant_id="tenant",
            repository_id="repository",
            binding_descriptor=SimpleNamespace(digest="sha256:" + "2" * 64),
            graph=graph,
        )
        args = cli.build_whole_os_parser().parse_args(
            ["run-once", "--config", "service.json", "--json"]
        )
        observation = SimpleNamespace(
            campaign_id="campaign",
            status="ready",
            completed_packages=("a",),
            pending_packages=(),
            blocked_packages=(),
            last_result=None,
        )
        service = Mock()
        service.run_cohort.return_value = observation
        registry = Mock()
        registry.resolve.return_value = SimpleNamespace(
            bindings="bindings", host="host"
        )

        with (
            patch.object(cli, "load_service_config", return_value=config),
            patch.object(cli, "WholeOSService", return_value=service),
            redirect_stdout(io.StringIO()),
        ):
            exit_code = cli._run_whole_os(args, host_factories=registry)

        self.assertEqual(exit_code, 0)
        service.run_cohort.assert_called_once_with()
        service.run_to_completion.assert_not_called()

    def test_status_is_read_only_and_does_not_resolve_a_host(self) -> None:
        with TemporaryDirectory() as directory:
            graph = OutcomeGraphSpec(
                (OutcomeWorkPackage("a", ("outcome-a",)),),
                "sha256:" + "1" * 64,
            )
            config = SimpleNamespace(
                campaign_id="campaign",
                tenant_id="tenant",
                repository_id="repository",
                state_dir=Path(directory) / "absent-state",
                binding_descriptor=SimpleNamespace(digest="sha256:" + "2" * 64),
                graph=graph,
            )
            args = cli.build_whole_os_parser().parse_args(
                ["status", "--config", "service.json", "--json"]
            )
            registry = Mock()
            output = io.StringIO()

            with (
                patch.object(cli, "load_service_config", return_value=config),
                patch.object(cli, "WholeOSService") as service_type,
                redirect_stdout(output),
            ):
                exit_code = cli._run_whole_os(args, host_factories=registry)

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output.getvalue())["status"], "idle")
            registry.resolve.assert_not_called()
            service_type.assert_not_called()
            self.assertFalse(config.state_dir.exists())

    def test_status_reads_existing_queue_without_changing_database_bytes(self) -> None:
        with TemporaryDirectory() as directory:
            state_dir = Path(directory) / "state"
            graph = OutcomeGraphSpec(
                (OutcomeWorkPackage("a", ("outcome-a",)),),
                "sha256:" + "1" * 64,
            )
            config = SimpleNamespace(
                campaign_id="campaign",
                tenant_id="tenant",
                repository_id="repository",
                state_dir=state_dir,
                binding_descriptor=SimpleNamespace(digest="sha256:" + "2" * 64),
                graph=graph,
            )
            scheduler = Scheduler(state_dir / "queue")
            scheduler.enqueue(
                WholeOSService.JOB_KIND,
                {"package_id": "a"},
                mission_id="campaign",
            )
            scheduler.close()
            database = state_dir / "queue" / "scheduler.sqlite3"
            before = database.read_bytes()
            args = cli.build_whole_os_parser().parse_args(
                ["status", "--config", "service.json", "--json"]
            )
            output = io.StringIO()

            with (
                patch.object(cli, "load_service_config", return_value=config),
                redirect_stdout(output),
            ):
                exit_code = cli._run_whole_os(args)

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output.getvalue())["status"], "ready")
            self.assertEqual(database.read_bytes(), before)

    def test_unknown_host_provider_returns_typed_capability_blocker(self) -> None:
        graph = OutcomeGraphSpec(
            (OutcomeWorkPackage("a", ("outcome-a",)),),
            "sha256:" + "1" * 64,
        )
        config = SimpleNamespace(
            campaign_id="campaign",
            tenant_id="tenant",
            repository_id="repository",
            binding_descriptor=SimpleNamespace(digest="sha256:" + "2" * 64),
            graph=graph,
        )
        args = cli.build_whole_os_parser().parse_args(
            ["start", "--config", "service.json", "--json"]
        )
        registry = Mock()
        registry.resolve.side_effect = WholeOSHostUnavailable(
            "no independently admitted host factory matches the sealed descriptor"
        )
        error = io.StringIO()

        with (
            patch.object(cli, "load_service_config", return_value=config),
            patch.object(cli, "WholeOSService") as service_type,
            redirect_stderr(error),
        ):
            exit_code = cli._run_whole_os(args, host_factories=registry)

        self.assertEqual(exit_code, 2)
        document = json.loads(error.getvalue())
        self.assertEqual(document["status"], "blocked")
        self.assertEqual(document["blocker"], "blocked_capability")
        service_type.assert_not_called()

    def test_help_exposes_mode_and_concurrency_selection(self) -> None:
        parser = cli.build_whole_os_parser()
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit):
            parser.parse_args(["resume", "--help"])
        help_text = output.getvalue()

        self.assertIn("--execution-mode", help_text)
        self.assertIn("--max-parallel-packages", help_text)
        self.assertIn("--cohort-size", help_text)

    def test_help_exposes_one_command_start(self) -> None:
        help_text = cli.build_whole_os_parser().format_help()

        self.assertIn("start", help_text)


if __name__ == "__main__":
    unittest.main()
