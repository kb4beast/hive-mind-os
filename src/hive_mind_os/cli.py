from __future__ import annotations

import argparse
import asyncio
import json

from .models import Objective
from .runtime import HiveKernel


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hive-mind", description="Run the Hive Mind OS bootstrap kernel")
    parser.add_argument("goal", help="Outcome for the specialist agent team")
    parser.add_argument("--repository", help="Optional owner/repository target")
    parser.add_argument("--criterion", action="append", default=[], help="Acceptance criterion; repeatable")
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


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
