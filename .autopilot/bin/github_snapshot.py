"""Build and install the dispatcher's GitHub snapshot from live state.

The dispatcher protocol requires a current ``.autopilot/state/github-state.json``
before any release. Hand-assembling that JSON is error-prone and burns
orchestrator context, so this script derives it deterministically:

- target SHA from ``refs/remotes/origin/<target-branch>`` after a fetch
- pull-request state per plan node through the ``gh`` CLI (optional)
- remote node branches through ``git ls-remote``

It then installs the snapshot through the controller's validator and prints the
exact reconcile/dispatch commands for the current target. Read-only against
GitHub; writes only under ``.autopilot/state/``.

Usage:
  python .autopilot/bin/github_snapshot.py [--repo-root .] [--offline]
      [--reconcile --actor HOST:SESSION]

``--offline`` skips the ``gh`` PR inventory (empty pull_requests list). Use it
only when no node PRs are expected to be open, e.g. the start of a wave on a
freshly integrated target; PR-state gates degrade to branch/receipt evidence.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

FAILURE_CONCLUSIONS = {"FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED"}
SUCCESS_CONCLUSIONS = {"SUCCESS", "SKIPPED", "NEUTRAL"}


def run(args: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, encoding="utf-8"
    )
    if check and completed.returncode != 0:
        raise SystemExit(
            f"command failed ({' '.join(args)}):\n{completed.stderr.strip()}"
        )
    return completed


def rollup_ci(rollup: object) -> str:
    if not isinstance(rollup, list) or not rollup:
        return "pending"
    conclusions = {
        str(item.get("conclusion") or "").upper()
        for item in rollup
        if isinstance(item, dict)
    }
    if conclusions & FAILURE_CONCLUSIONS:
        return "failure"
    if conclusions and conclusions <= SUCCESS_CONCLUSIONS:
        return "success"
    return "pending"


def main() -> int:
    parser = argparse.ArgumentParser(prog="github_snapshot")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument(
        "--reconcile",
        action="store_true",
        help="also record the reconciliation for the fetched target SHA",
    )
    parser.add_argument("--actor", default="")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    control = json.loads((root / ".autopilot/control-plane.json").read_text("utf-8"))
    target = control["target"]
    branch = target["branch"]
    repository = target.get("repository", "")

    run(["git", "fetch", "--no-tags", "origin", branch], cwd=root)
    target_sha = run(
        ["git", "rev-parse", "--verify", f"refs/remotes/origin/{branch}"], cwd=root
    ).stdout.strip()

    plan = json.loads((root / ".autopilot/plan.json").read_text("utf-8"))
    branch_to_node = {
        str(node.get("branch")): str(node.get("id"))
        for node in plan.get("nodes", [])
        if isinstance(node, dict)
    }

    pull_requests: list[dict[str, object]] = []
    if not args.offline:
        listed = run(
            [
                "gh", "pr", "list", "--repo", repository, "--state", "all",
                "--limit", "200",
                "--json", "number,state,headRefName,statusCheckRollup",
            ],
            cwd=root,
            check=False,
        )
        if listed.returncode != 0:
            raise SystemExit(
                "gh pr list failed; rerun with --offline only if no node PRs are "
                f"expected to be open:\n{listed.stderr.strip()}"
            )
        for item in json.loads(listed.stdout or "[]"):
            node_id = branch_to_node.get(str(item.get("headRefName")))
            if node_id is None:
                continue
            state = str(item.get("state", "")).upper()
            pull_requests.append(
                {
                    "node_id": node_id,
                    "number": item.get("number"),
                    "state": "open" if state == "OPEN" else "closed",
                    "merged": state == "MERGED",
                    "ci": rollup_ci(item.get("statusCheckRollup")),
                }
            )

    branches: list[dict[str, object]] = []
    heads = run(["git", "ls-remote", "--heads", "origin"], cwd=root).stdout
    for line in heads.splitlines():
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        sha, ref = parts[0].strip(), parts[1].strip()
        name = ref.removeprefix("refs/heads/")
        if name in branch_to_node:
            branches.append({"name": name, "sha": sha, "node_id": branch_to_node[name]})

    snapshot = {
        "target_sha": target_sha,
        "pull_requests": pull_requests,
        "branches": branches,
        "source": "github_snapshot.py"
        + (" --offline" if args.offline else " via gh pr list"),
    }
    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    ) as handle:
        json.dump(snapshot, handle, indent=2, sort_keys=True)
        snapshot_path = handle.name

    autopilot = str(root / ".autopilot/bin/autopilot.py")
    run(
        [sys.executable, autopilot, "--repo-root", str(root),
         "install-github-snapshot", snapshot_path],
        cwd=root,
    )
    print(f"snapshot installed: target={target_sha}")
    print(f"  pull_requests={len(pull_requests)} branches={len(branches)}")

    if args.reconcile:
        if not args.actor.strip():
            raise SystemExit("--reconcile requires --actor HOST:SESSION")
        run(
            [sys.executable, autopilot, "--repo-root", str(root), "reconcile",
             "--target-sha", target_sha, "--actor", args.actor,
             "--reason", "scripted dispatcher snapshot and target reconciliation"],
            cwd=root,
        )
        print(f"reconciled: {target_sha}")
        print("next: python .autopilot/bin/autopilot.py --repo-root . dispatch "
              f"--actor {args.actor}")
    else:
        print("next: python .autopilot/bin/autopilot.py --repo-root . reconcile "
              f"--target-sha {target_sha} --actor HOST:SESSION --reason <why>")
        print("then: python .autopilot/bin/autopilot.py --repo-root . dispatch "
              "--actor HOST:SESSION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
