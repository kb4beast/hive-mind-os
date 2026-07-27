from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Sequence

from .current_state_audit import (
    collect_current_state_audit,
    create_audit_artifact,
    write_audit_artifact,
)
from .models import Objective
from .runtime import HiveKernel


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hive-mind", description="Run the Hive Mind OS bootstrap kernel")
    parser.add_argument("goal", help="Outcome for the specialist agent team")
    parser.add_argument("--repository", help="Optional owner/repository target")
    parser.add_argument("--criterion", action="append", default=[], help="Acceptance criterion; repeatable")
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


async def _run(args: argparse.Namespace) -> int:
    objective = Objective(
        goal=args.goal,
        repository=args.repository,
        acceptance_criteria=tuple(args.criterion),
    )
    report = await HiveKernel().run_objective(objective)
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
    args = build_parser().parse_args(arguments)
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
