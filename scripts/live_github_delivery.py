"""Manual P07 delivery run. This script is intentionally excluded from CI."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from hive_mind_os.autonomy import AutonomyBudget
from hive_mind_os.git_adapter import GitWorkspace
from hive_mind_os.github_adapter import GitHubClient
from hive_mind_os.ledger import EvidenceLedger
from hive_mind_os.mission_store import MissionStore
from hive_mind_os.models import AutonomyLevel
from hive_mind_os.policy import PolicyEngine


def _head(repository: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Push one exact local commit, open/adopt one draft PR, poll GitHub "
            "Actions, and preserve protection evidence. Never merges."
        )
    )
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--base", default="main")
    parser.add_argument("--title", required=True)
    parser.add_argument("--body", default="Automated P07 draft-delivery evidence.")
    parser.add_argument(
        "--desired-rules",
        type=Path,
        default=Path(".github/governance/required-repository-rules.json"),
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=Path("evidence/live/P07"),
    )
    parser.add_argument("--head", dest="expected_head")
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    parser.add_argument("--max-check-attempts", type=int, default=40)
    parser.add_argument("--check-interval-s", type=float, default=15.0)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    repository = args.repository.resolve()
    head = _head(repository)
    if args.expected_head and args.expected_head != head:
        raise SystemExit(
            f"refusing stale delivery: expected {args.expected_head}, found {head}"
        )
    evidence_dir = args.evidence_dir.resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = hashlib.sha256(
        f"{args.owner}/{args.repo}\0{args.branch}\0{head}".encode()
    ).hexdigest()
    mission_id = f"P07-live-{fingerprint[:20]}"
    store = MissionStore(evidence_dir / "state")
    ledger = EvidenceLedger(evidence_dir / "evidence-ledger.sqlite3")
    try:
        if not store.has_mission(mission_id):
            store.register_mission(
                mission_id,
                {
                    "objective": "P07 exact-head GitHub delivery",
                    "source_pack_fingerprint": f"sha256:{fingerprint}",
                    "owner": args.owner,
                    "repository": args.repo,
                    "branch": args.branch,
                    "head_sha": head,
                },
                AutonomyBudget(100, 100, 100.0),
            )
        policy = PolicyEngine(AutonomyLevel.REPOSITORY)
        with tempfile.TemporaryDirectory(prefix="hive-p07-live-") as temporary:
            workspace = GitWorkspace.materialize(
                repository,
                head,
                Path(temporary) / "workspace",
                evidence_dir / "git-receipts",
                policy=policy,
            )
            client = GitHubClient(
                args.owner,
                args.repo,
                evidence_dir / "github-receipts",
                token_env=args.token_env,
                policy=policy,
                ledger=ledger,
                mission_store=store,
                mission_id=mission_id,
            )
            delivery = client.deliver(
                workspace,
                branch=args.branch,
                base=args.base,
                title=args.title,
                body=args.body,
                desired_rules_path=args.desired_rules.resolve(),
                max_check_attempts=args.max_check_attempts,
                check_interval_s=args.check_interval_s,
            )
        result = {
            "schema_version": 1,
            "mission_id": mission_id,
            "owner": args.owner,
            "repository": args.repo,
            "branch": delivery.push.branch,
            "head_sha": delivery.push.head_sha,
            "pull_request": {
                "number": delivery.pull_request.number,
                "url": delivery.pull_request.url,
                "draft": delivery.pull_request.draft,
            },
            "checks": [
                {
                    "name": check.name,
                    "conclusion": check.conclusion,
                    "workflow_run_id": check.workflow_run_id,
                    "workflow_run_url": check.workflow_run_url,
                    "json_digest": check.json_digest,
                    "receipt_digest": check.receipt["digest"],
                }
                for check in delivery.checks
            ],
            "protection": {
                "matches": delivery.protection.matches,
                "mismatches": list(delivery.protection.mismatches),
                "evidence_path": delivery.protection.evidence_path,
                "evidence_digest": delivery.protection.evidence_digest,
            },
        }
        output = evidence_dir / "live-run.json"
        output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    finally:
        ledger.close()
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
