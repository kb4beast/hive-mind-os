"""Command-line boundary for the portable DAG product surface."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .powershell_preparation import prepare_read_only_powershell
from .subject_execution import (
    SubjectExecutionError,
    SubjectExecutionMode,
    SubjectExecutionService,
)


def _add_plan_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--plan", required=True)
    parser.add_argument("--standard", required=True)
    parser.add_argument("--expected-plan-digest", required=True)
    parser.add_argument(
        "--mode",
        choices=[item.value for item in SubjectExecutionMode],
        default=SubjectExecutionMode.REPOSITORY.value,
    )
    parser.add_argument(
        "--subject", help="Operator label only; never an authority grant"
    )
    parser.add_argument("--expected-request-id")
    parser.add_argument("--expected-subject-id")


def build_dag_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hive-mind dag",
        description="Build, inspect, and run portable governed DAGs",
    )
    commands = parser.add_subparsers(dest="dag_command", required=True)
    build = commands.add_parser("build", help="Seal canonical inert plan bytes")
    _add_plan_arguments(build)
    build.add_argument("--output", required=True)
    build.add_argument("--replace", action="store_true")
    for name in ("validate", "rounds", "graph"):
        command = commands.add_parser(name)
        _add_plan_arguments(command)
    for name in ("execute", "resume"):
        command = commands.add_parser(name)
        _add_plan_arguments(command)
        command.add_argument("--activation", required=True)
        command.add_argument("--state-directory", required=True)
    status = commands.add_parser("status")
    status.add_argument("--state-directory", required=True)
    status.add_argument("--run-id")
    status.add_argument("--plan", required=True)
    status.add_argument("--expected-plan-digest", required=True)
    cancel = commands.add_parser("cancel")
    cancel.add_argument("--activation", required=True)
    cancel.add_argument("--state-directory", required=True)
    cancel.add_argument("--run-id", required=True)
    cancel.add_argument("--reason", required=True)
    reconcile = commands.add_parser("reconcile")
    reconcile.add_argument("--state-directory", required=True)
    reconcile.add_argument("--run-id", required=True)
    reconcile.add_argument("--receipt", required=True)
    prepare = commands.add_parser("prepare-powershell")
    prepare.add_argument("--plan", required=True)
    prepare.add_argument("--standard", required=True)
    prepare.add_argument("--subject", required=True)
    prepare.add_argument("--expected-plan-digest", required=True)
    prepare.add_argument("--state-directory", required=True)
    prepare.add_argument("--execution-client", required=True)
    prepare.add_argument("--expected-execution-client-digest", required=True)
    return parser


@dataclass(frozen=True, slots=True)
class _PlanArguments:
    plan_path: Path
    standard_path: Path
    expected_plan_digest: str
    mode: SubjectExecutionMode
    expected_request_id: str | None
    expected_subject_id: str | None


def _plan_arguments(args: argparse.Namespace) -> _PlanArguments:
    return _PlanArguments(
        Path(args.plan),
        Path(args.standard),
        args.expected_plan_digest,
        SubjectExecutionMode(args.mode),
        args.expected_request_id,
        args.expected_subject_id,
    )


def _validate(service: SubjectExecutionService, arguments: _PlanArguments):
    return service.validate_files(
        plan_path=arguments.plan_path,
        standard_path=arguments.standard_path,
        expected_plan_digest=arguments.expected_plan_digest,
        mode=arguments.mode,
        expected_request_id=arguments.expected_request_id,
        expected_subject_id=arguments.expected_subject_id,
    )


def _inspection_arguments(arguments: _PlanArguments) -> dict[str, object]:
    return {
        "plan_path": arguments.plan_path,
        "standard_path": arguments.standard_path,
        "expected_plan_digest": arguments.expected_plan_digest,
        "mode": arguments.mode,
        "expected_request_id": arguments.expected_request_id,
        "expected_subject_id": arguments.expected_subject_id,
    }


def run_dag_command(
    args: argparse.Namespace, *, service: SubjectExecutionService | None = None
) -> int:
    service = service or SubjectExecutionService()
    try:
        if args.dag_command == "build":
            arguments = _plan_arguments(args)
            result = service.build_file(
                plan_path=arguments.plan_path,
                standard_path=arguments.standard_path,
                expected_plan_digest=arguments.expected_plan_digest,
                mode=arguments.mode,
                output_path=Path(args.output),
                replace_existing=args.replace,
            ).to_document()
        elif args.dag_command == "validate":
            result = {
                "status": "VALID",
                **_validate(service, _plan_arguments(args)).to_document(),
            }
        elif args.dag_command == "rounds":
            result = {
                "status": "VALID",
                "rounds": service.rounds(
                    **_inspection_arguments(_plan_arguments(args))
                ),
            }
        elif args.dag_command == "graph":
            result = service.graph(**_inspection_arguments(_plan_arguments(args)))
        elif args.dag_command == "status":
            state = Path(args.state_directory) / "dag-execution.sqlite3"
            result = service.status(
                state_path=state,
                plan_path=Path(args.plan),
                expected_plan_digest=args.expected_plan_digest,
                run_id=args.run_id,
            )
        elif args.dag_command == "prepare-powershell":
            prepared = prepare_read_only_powershell(
                subject=args.subject,
                plan_path=Path(args.plan),
                standard_path=Path(args.standard),
                expected_plan_digest=args.expected_plan_digest,
                state_directory=Path(args.state_directory),
                execution_client_path=Path(args.execution_client),
                expected_execution_client_digest=args.expected_execution_client_digest,
            )
            result = {**prepared.to_document(), "text": prepared.text}
        elif args.dag_command in {"execute", "resume", "cancel", "reconcile"}:
            # Raw files cannot become an AuthorizedOneRun merely by being named
            # on a command line. A configured host integration must parse and
            # authenticate them, then call SubjectExecutionService programmatically.
            raise SubjectExecutionError(
                "EXTERNAL_RUNTIME_REQUIRED: this CLI has no authenticated host adapter "
                "or signature verifier"
            )
        else:
            raise SubjectExecutionError("unsupported DAG command")
    except (OSError, ValueError, SubjectExecutionError) as error:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "error": f"{type(error).__name__}: {error}",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    args = build_dag_parser().parse_args(argv)
    raise SystemExit(run_dag_command(args))


__all__ = ["build_dag_parser", "main", "run_dag_command"]


if __name__ == "__main__":
    main()
