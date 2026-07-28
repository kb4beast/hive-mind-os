from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Sequence

from .autonomy import AutonomyBudget
from .current_state_audit import (
    collect_current_state_audit,
    create_audit_artifact,
    write_audit_artifact,
)
from .ledger import EvidenceLedger
from .mission import RepositoryMission, ScriptedRepositoryBackend
from .mission_store import (
    MissionStore,
    MissionStoreError,
    ReconciliationError,
    resume_mission,
)
from .model_backend import ModelBackend
from .model_provider import ModelProviderError, provider_from_env
from .models import AutonomyLevel, Objective, Role
from .policy import PolicyEngine
from .runtime import HiveKernel


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hive-mind", description="Run the Hive Mind OS bootstrap kernel")
    parser.add_argument("goal", help="Outcome for the specialist agent team")
    parser.add_argument("--repository", help="Optional owner/repository target")
    parser.add_argument("--criterion", action="append", default=[], help="Acceptance criterion; repeatable")
    parser.add_argument(
        "--backend",
        choices=("deterministic", "model"),
        default="deterministic",
        help="Agent backend (default: deterministic offline backend)",
    )
    return parser


def build_audit_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hive-mind audit",
        description="Emit a digested CurrentStateAudit for a Git worktree",
    )
    parser.add_argument(
        "--repository",
        default=".",
        help="Git worktree to audit (default: current directory)",
    )
    parser.add_argument(
        "--output",
        help="Write the JSON artifact to this path; omit to print it",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Collect repository and docket facts without executing tests; marks the audit incomplete",
    )
    parser.add_argument(
        "--signing-key-file",
        help="Optional file containing an HMAC key; the key is never written to the artifact",
    )
    parser.add_argument(
        "--signing-key-id",
        help="Required stable identifier when --signing-key-file is used",
    )
    return parser


def build_deliver_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hive-mind deliver",
        description="Produce a verified local repository delivery artifact",
    )
    parser.add_argument(
        "--repository",
        required=True,
        help="Local Git worktree to improve",
    )
    parser.add_argument(
        "--objective",
        required=True,
        help="Measurable repository outcome",
    )
    parser.add_argument(
        "--criterion",
        action="append",
        default=[],
        help="Acceptance criterion; repeatable",
    )
    parser.add_argument(
        "--backend",
        choices=("scripted", "model"),
        default="scripted",
        help="Repository backend (default: deterministic offline scripted backend)",
    )
    parser.add_argument(
        "--pin",
        help="Optional full 40-hex base commit; defaults to the local worktree HEAD",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Absent directory to publish after independent verification",
    )
    parser.add_argument(
        "--scripted-variant",
        choices=("good", "sabotage"),
        default="good",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--state-dir",
        help="Persist checkpoints and receipts here for later resume",
    )
    return parser


def build_resume_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hive-mind resume",
        description="Resume one interrupted durable repository mission",
    )
    parser.add_argument("mission_id", help="Durable mission identifier")
    parser.add_argument(
        "--state-dir",
        default=".hive-mind-state",
        help="Mission state directory (default: .hive-mind-state)",
    )
    return parser


def build_missions_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hive-mind missions",
        description="List durable repository missions",
    )
    parser.add_argument(
        "--state-dir",
        default=".hive-mind-state",
        help="Mission state directory (default: .hive-mind-state)",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    objective = Objective(
        goal=args.goal,
        repository=args.repository,
        acceptance_criteria=tuple(args.criterion),
    )
    ledger = EvidenceLedger()
    backend = None
    if args.backend == "model":
        try:
            backend = ModelBackend(
                provider_from_env(),
                ledger=ledger,
                role_providers={
                    Role.CURATOR: provider_from_env(role=Role.CURATOR)
                },
            )
        except (ModelProviderError, ValueError) as error:
            raise SystemExit(f"model backend configuration failed: {error}") from None
    report = await HiveKernel(backend=backend, ledger=ledger).run_objective(objective)
    print(
        json.dumps(
            {
                "run_id": report.run_id,
                "status": report.status.value,
                "roles_completed": [result.role.value for result in report.results],
                "evidence_count": report.evidence_count,
            },
            indent=2,
        )
    )
    return 0 if report.status.value == "succeeded" else 1


async def _run_deliver(args: argparse.Namespace) -> int:
    state_store = MissionStore(args.state_dir) if args.state_dir else None
    ledger = EvidenceLedger(
        state_store.state_dir / "evidence-ledger.sqlite3"
        if state_store is not None
        else ":memory:"
    )
    budget = AutonomyBudget(
        max_episodes=1000,
        max_tool_calls=500,
        max_compute_units=500.0,
        max_tool_calls_per_episode=100,
        max_compute_units_per_episode=100.0,
    )
    if args.backend == "model":
        try:
            backend = ModelBackend(
                provider_from_env(),
                ledger=ledger,
                budget=budget,
                role_providers={
                    Role.CURATOR: provider_from_env(role=Role.CURATOR)
                },
            )
        except (ModelProviderError, ValueError) as error:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "error": f"model backend configuration failed: {error}",
                    },
                    indent=2,
                ),
                file=sys.stderr,
            )
            return 1
    else:
        backend = ScriptedRepositoryBackend(args.scripted_variant)
    try:
        repository = Path(args.repository).resolve()
        output_dir = (
            Path(args.output_dir)
            if args.output_dir
            else repository.parent / f"{repository.name}-hive-mind-delivery"
        )
        mission = RepositoryMission(
            repository,
            args.objective,
            acceptance_criteria=tuple(args.criterion),
            backend=backend,
            pin=args.pin,
            output_dir=output_dir,
            policy=PolicyEngine(AutonomyLevel.REPOSITORY),
            budget=budget,
            ledger=ledger,
            mission_store=state_store,
        )
        report = await mission.run()
    except (OSError, RuntimeError, ValueError) as error:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": f"{type(error).__name__}: {error}",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1
    stream = sys.stdout if report.status.value == "succeeded" else sys.stderr
    print(
        json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        file=stream,
    )
    return 0 if report.status.value == "succeeded" else 1


async def _run_resume(args: argparse.Namespace) -> int:
    store = MissionStore(args.state_dir)
    try:
        report = await resume_mission(store, args.mission_id)
    except ReconciliationError as error:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "error": str(error),
                    "reconciliation": error.report,
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    except (MissionStoreError, OSError, ValueError) as error:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": f"{type(error).__name__}: {error}",
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    finally:
        store.close()
    print(
        json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report.status.value == "succeeded" else 1


def _run_missions(args: argparse.Namespace) -> int:
    store = MissionStore(args.state_dir)
    try:
        inventory = store.list_missions()
    finally:
        store.close()
    print(
        json.dumps(
            {"missions": inventory},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _run_audit(args: argparse.Namespace, invocation: Sequence[str]) -> int:
    if bool(args.signing_key_file) != bool(args.signing_key_id):
        raise SystemExit("--signing-key-file and --signing-key-id must be supplied together")
    signing_key = Path(args.signing_key_file).read_bytes() if args.signing_key_file else None
    audit = collect_current_state_audit(
        args.repository,
        run_tests=not args.skip_tests,
        invocation=invocation,
    )
    artifact = create_audit_artifact(
        audit,
        signing_key=signing_key,
        signing_key_id=args.signing_key_id,
    )
    if args.output:
        write_audit_artifact(artifact, args.output)
        integrity = artifact.get("integrity")
        digest = integrity.get("digest") if isinstance(integrity, dict) else None
        print(
            json.dumps(
                {
                    "artifact": str(Path(args.output).resolve()),
                    "digest": digest,
                    "complete": audit["complete"],
                    "failures": audit["failures"],
                },
                indent=2,
            )
        )
    else:
        print(json.dumps(artifact, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if audit["complete"] else 1


def main(argv: Sequence[str] | None = None) -> None:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "audit":
        args = build_audit_parser().parse_args(arguments[1:])
        raise SystemExit(_run_audit(args, ("hive-mind", *arguments)))
    if arguments and arguments[0] == "deliver":
        args = build_deliver_parser().parse_args(arguments[1:])
        raise SystemExit(asyncio.run(_run_deliver(args)))
    if arguments and arguments[0] == "resume":
        args = build_resume_parser().parse_args(arguments[1:])
        raise SystemExit(asyncio.run(_run_resume(args)))
    if arguments and arguments[0] == "missions":
        args = build_missions_parser().parse_args(arguments[1:])
        raise SystemExit(_run_missions(args))
    args = build_parser().parse_args(arguments)
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
