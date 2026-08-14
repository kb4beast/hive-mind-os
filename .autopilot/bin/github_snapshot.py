"""Build and install the dispatcher's GitHub snapshot from live state.

The dispatcher protocol requires a current ``.autopilot/state/github-state.json``
before any release. Hand-assembling that JSON is error-prone and burns
orchestrator context, so this script derives it deterministically:

- target SHA from a controller-reserved private observation ref
- pull-request state per plan node through the ``gh`` CLI (optional)
- remote node branches through ``git ls-remote``

It then installs the snapshot through the controller's validator and prints the
exact reconcile/dispatch commands for the current target. It never mutates GitHub,
The remote read fetches only the target branch into a unique private ref and never
updates ``FETCH_HEAD`` or ``origin/<target>``. The controller authenticates the
candidate commit and compare-and-swap advances the canonical tracking ref at install.

Usage:
  python .autopilot/bin/github_snapshot.py [--repo-root .] [--offline]
      [--reconcile --actor HOST:SESSION]

``--offline`` records that GitHub PR evidence is unavailable.  The candidate may
be retained for diagnostics, but dispatcher/reconciliation authority stays
closed until a complete online observation is installed; an empty list is never
treated as proof that no pull request exists.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

FAILURE_CONCLUSIONS = {"FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED"}
SUCCESS_CONCLUSIONS = {"SUCCESS", "SKIPPED", "NEUTRAL"}
GITHUB_NODE_PR_LIMIT = 1000


_GIT_COMMON_DIRS: dict[Path, Path] = {}


def _harden_git_argv(args: list[str], *, cwd: Path) -> tuple[list[str], dict[str, str]]:
    """Neutralize clone-local graph/hook injection for snapshot authority reads."""

    environment = {
        key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")
    }
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    environment["GIT_TERMINAL_PROMPT"] = "0"
    hardened = [
        "git",
        "--no-replace-objects",
        "-c",
        f"core.hooksPath={os.devnull}",
        *args[1:],
    ]
    root = cwd.resolve()
    common = _GIT_COMMON_DIRS.get(root)
    if common is None:
        located = subprocess.run(
            [
                "git",
                "--no-replace-objects",
                "-c",
                f"core.hooksPath={os.devnull}",
                "rev-parse",
                "--path-format=absolute",
                "--git-common-dir",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
        )
        raw_common = located.stdout.strip()
        if located.returncode != 0 or not raw_common or not Path(raw_common).is_absolute():
            raise SystemExit("snapshot Git common directory cannot be authenticated")
        common = Path(raw_common).resolve(strict=False)
        _GIT_COMMON_DIRS[root] = common
    grafts = common / "info" / "grafts"
    if grafts.exists() or grafts.is_symlink():
        raise SystemExit("snapshot authority rejects legacy Git grafts")
    replacements = subprocess.run(
        [
            "git",
            "--no-replace-objects",
            "-c",
            f"core.hooksPath={os.devnull}",
            "for-each-ref",
            "--format=%(refname)",
            "refs/replace",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
    )
    if replacements.returncode != 0 or replacements.stdout.strip():
        raise SystemExit("snapshot authority rejects Git replacement refs")
    return hardened, environment


def run(args: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    environment = None
    invoked = list(args)
    if invoked and invoked[0] == "git":
        invoked, environment = _harden_git_argv(invoked, cwd=cwd)
    completed = subprocess.run(
        invoked,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
    )
    if check and completed.returncode != 0:
        raise SystemExit(
            f"command failed ({' '.join(invoked)}):\n{completed.stderr.strip()}"
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


def digest_json(value: object) -> str:
    import hashlib

    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def strict_json(text: str, *, label: str) -> object:
    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(value: str) -> object:
        raise ValueError(f"nonfinite JSON number: {value}")

    try:
        return json.loads(
            text,
            object_pairs_hook=pairs,
            parse_constant=constant,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise SystemExit(f"{label} is malformed strict JSON: {error}") from error


def render_command(arguments: list[str]) -> str:
    """Render only the already-authenticated argv used by this process."""

    return subprocess.list2cmdline([str(item) for item in arguments])


def main(*, _coordinator_locked: bool = False) -> int:
    parser = argparse.ArgumentParser(prog="github_snapshot")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--state-dir")
    parser.add_argument("--execution-namespace", default="default")
    parser.add_argument("--host-runtime-dir")
    parser.add_argument(
        "--host-id",
        help=(
            "authenticated host provider used only to render an executable "
            "dispatch handoff"
        ),
    )
    parser.add_argument("--offline", action="store_true")
    parser.add_argument(
        "--reconcile",
        action="store_true",
        help="also record the reconciliation for the fetched target SHA",
    )
    parser.add_argument("--actor", default="")
    args = parser.parse_args()
    if args.reconcile and not args.actor.strip():
        parser.error("--reconcile requires --actor HOST:SESSION")

    root = Path(args.repo_root).resolve()
    from autopilot import ControlPlane
    from controller import reconcile_pending_host_capacity_renewal

    plane = ControlPlane(
        root,
        state_dir=args.state_dir,
        execution_namespace=args.execution_namespace,
        host_runtime_dir=args.host_runtime_dir,
    )
    if args.host_id:
        with plane.host_lock(timeout_seconds=120.0):
            capacity = reconcile_pending_host_capacity_renewal(
                plane.host_runtime_dir,
                host_id=args.host_id,
                now=plane.clock(),
            )
        if capacity.get("host_id") != args.host_id:
            raise SystemExit(
                "snapshot dispatch handoff host id is not authenticated"
            )
    if not _coordinator_locked:
        # Every process joins the same observation token, but only one coordinator
        # may own its private refs and immutable candidate at a time. This local,
        # execution-scoped lock spans remote reads by design; it never serializes a
        # different execution namespace or holds the repository arbiter.
        with plane.execution_lock(
            "github-snapshot-coordinator.lock", timeout_seconds=3600.0
        ):
            return main(_coordinator_locked=True)
    autopilot = str((root / ".autopilot/bin/autopilot.py").resolve())
    autopilot_prefix = [
        sys.executable,
        autopilot,
        "--repo-root",
        str(root),
        "--state-dir",
        str(plane.coordination_dir),
        "--host-runtime-dir",
        str(plane.host_runtime_dir),
        "--execution-namespace",
        args.execution_namespace,
    ]

    # Reserve before any remote observation. If another worktree begins a newer
    # observation while this process is fetching, this token becomes stale and the
    # eventual install fails rather than overwriting newer shared scheduling evidence.
    observation = run(
        [
            *autopilot_prefix,
            "snapshot-observation-begin",
            "--actor",
            args.actor.strip() or "autopilot:github-snapshot",
        ],
        cwd=root,
    )
    try:
        reservation = strict_json(
            observation.stdout, label="snapshot observation reservation"
        )
        if not isinstance(reservation, dict):
            raise TypeError("reservation is not an object")
        execution_namespace = str(reservation["execution_namespace"])
        execution_id = str(reservation["execution_id"])
        if (
            execution_namespace != args.execution_namespace
            or execution_id != plane.execution_id
        ):
            raise TypeError("reservation execution identity mismatch")
        repository = str(reservation["repository"])
        branch = str(reservation["target_branch"])
        if not repository.strip() or not branch.strip():
            raise TypeError("reservation target identity is empty")
        observation_id = str(reservation["observation_id"])
        observation_epoch = int(reservation["observation_epoch"])
        fetch_ref = str(reservation["fetch_ref"])
        reservation_status = str(reservation["status"])
        branch_fetches = reservation["branch_fetches"]
        if not isinstance(branch_fetches, list):
            raise TypeError("branch_fetches is not a list")
    except (KeyError, TypeError, ValueError) as error:
        raise SystemExit("snapshot observation reservation returned malformed authority") from error

    if reservation_status in {"INSTALLING", "INSTALLED"}:
        run(
            [
                *autopilot_prefix,
                "install-github-snapshot",
                "--observation-id",
                observation_id,
            ],
            cwd=root,
        )
        target_sha = str(reservation["target_sha"])
        print(f"snapshot resumed: target={target_sha}")
        if args.reconcile:
            run(
                [
                    *autopilot_prefix,
                    "reconcile",
                    "--target-sha",
                    target_sha,
                    "--actor",
                    args.actor,
                    "--reason",
                    "resumed immutable dispatcher snapshot and target reconciliation",
                ],
                cwd=root,
            )
            print(f"reconciled: {target_sha}")
        return 0
    if reservation_status != "PENDING":
        raise SystemExit("snapshot observation reservation has an unsupported status")

    target_refspec = f"+refs/heads/{branch}:{fetch_ref}"
    run(
        [
            "git",
            "fetch",
            "--no-tags",
            "--no-write-fetch-head",
            "origin",
            target_refspec,
        ],
        cwd=root,
    )
    target_sha = run(
        ["git", "rev-parse", "--verify", f"{fetch_ref}^{{commit}}"], cwd=root
    ).stdout.strip()

    fetched_plan = run(
        ["git", "show", f"{target_sha}:.autopilot/plan.json"], cwd=root
    )
    try:
        plan = strict_json(fetched_plan.stdout, label="fetched target plan")
        if not isinstance(plan, dict):
            raise TypeError("fetched target plan is not an object")
    except TypeError as error:
        raise SystemExit("fetched target plan is malformed") from error
    branch_to_node = {
        str(node.get("branch")): str(node.get("id"))
        for node in plan.get("nodes", [])
        if isinstance(node, dict)
    }
    expected_fetches = {
        str(item.get("branch")): item
        for item in branch_fetches
        if isinstance(item, dict)
    }
    if set(expected_fetches) != set(branch_to_node) or any(
        expected_fetches[name].get("node_id") != node_id
        for name, node_id in branch_to_node.items()
    ):
        raise SystemExit(
            "snapshot observation branch inventory differs from the fetched target plan"
        )

    pull_requests: list[dict[str, object]] = []
    raw_pull_requests: list[dict[str, Any]] = []
    github_node_queries: list[dict[str, object]] = []
    if not args.offline:
        seen_numbers: set[int] = set()
        for fetch in branch_fetches:
            if not isinstance(fetch, dict):
                raise SystemExit("snapshot observation branch fetch entry is malformed")
            node_id = str(fetch["node_id"])
            node_branch = str(fetch["branch"])
            github_argv = [
                "gh",
                "pr",
                "list",
                "--repo",
                repository,
                "--head",
                node_branch,
                "--state",
                "all",
                "--limit",
                str(GITHUB_NODE_PR_LIMIT),
                "--json",
                "number,state,headRefName,statusCheckRollup",
            ]
            listed = run(github_argv, cwd=root, check=False)
            if listed.returncode != 0:
                raise SystemExit(
                    f"gh pr list failed for node {node_id}:\n{listed.stderr.strip()}"
                )
            parsed_prs = strict_json(
                listed.stdout or "[]",
                label=f"GitHub pull-request response for {node_id}",
            )
            if not isinstance(parsed_prs, list) or any(
                not isinstance(item, dict) for item in parsed_prs
            ):
                raise SystemExit("gh pr list returned malformed JSON evidence")
            if len(parsed_prs) >= GITHUB_NODE_PR_LIMIT:
                raise SystemExit(
                    f"GitHub pull-request evidence for {node_id} reached the bounded "
                    "pagination limit and is therefore incomplete"
                )
            node_raw = [dict(item) for item in parsed_prs]
            if any(str(item.get("headRefName")) != node_branch for item in node_raw):
                raise SystemExit(
                    f"GitHub pull-request query for {node_id} returned another branch"
                )
            for item in node_raw:
                number = item.get("number")
                if type(number) is not int or number in seen_numbers:
                    raise SystemExit("GitHub pull-request evidence is duplicated or invalid")
                seen_numbers.add(number)
                state = str(item.get("state", "")).upper()
                raw_pull_requests.append(item)
                pull_requests.append(
                    {
                        "node_id": node_id,
                        "number": number,
                        "state": "open" if state == "OPEN" else "closed",
                        "merged": state == "MERGED",
                        "ci": rollup_ci(item.get("statusCheckRollup")),
                    }
                )
            github_node_queries.append(
                {
                    "node_id": node_id,
                    "branch": node_branch,
                    "argv": github_argv,
                    "exit_code": listed.returncode,
                    "result_count": len(node_raw),
                    "result_digest": digest_json(node_raw),
                }
            )

    branches: list[dict[str, object]] = []
    ls_remote_argv = [
        "git",
        "--no-replace-objects",
        "-c",
        f"core.hooksPath={os.devnull}",
        "ls-remote",
        "--heads",
        "origin",
    ]
    heads = run(["git", "ls-remote", "--heads", "origin"], cwd=root).stdout
    source_ref_observation = plane._snapshot_source_ref_observation_from_raw(
        reservation,
        raw_stdout=heads,
        ls_remote_argv=ls_remote_argv,
    )
    if source_ref_observation.get("target_sha") != target_sha:
        raise SystemExit(
            "target branch advanced while the snapshot was being collected; "
            "the reserved observation must be refreshed"
        )
    remote_heads: dict[str, str] = {}
    for line in heads.splitlines():
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        sha, ref = parts[0].strip(), parts[1].strip()
        name = ref.removeprefix("refs/heads/")
        if name in remote_heads and remote_heads[name] != sha:
            raise SystemExit(f"git ls-remote returned duplicate branch truth for {name}")
        remote_heads[name] = sha

    branch_observations: list[dict[str, object]] = []
    branch_refspecs: list[str] = []
    for item in branch_fetches:
        if not isinstance(item, dict):
            raise SystemExit("snapshot observation branch fetch entry is malformed")
        name = str(item["branch"])
        sha = remote_heads.get(name)
        present = sha is not None
        branch_observations.append(
            {
                "node_id": item["node_id"],
                "branch": name,
                "fetch_ref": item["fetch_ref"],
                "present": present,
                "sha": sha,
            }
        )
        if present:
            refspec = f"+refs/heads/{name}:{item['fetch_ref']}"
            branch_refspecs.append(refspec)
            branches.append(
                {"name": name, "sha": sha, "node_id": item["node_id"]}
            )
    if branch_refspecs:
        run(
            [
                "git",
                "fetch",
                "--no-tags",
                "--no-write-fetch-head",
                "origin",
                *branch_refspecs,
            ],
            cwd=root,
        )
    for item in branch_observations:
        if item["present"] is not True:
            continue
        resolved = run(
            ["git", "rev-parse", "--verify", f"{item['fetch_ref']}^{{commit}}"],
            cwd=root,
        ).stdout.strip()
        if resolved != item["sha"]:
            raise SystemExit(
                f"private branch ref changed during observation: {item['branch']}"
            )

    # These immutable, execution-namespaced remote refs are the portable Git
    # authority for the shared observation.  Publishing them before the shared
    # INSTALLING marker means another independent clone can resume after this
    # coordinator disappears; O_EXCL publication also prevents an old local
    # object/ref cache from being replayed under the current observation token.
    plane._publish_remote_evidence_ref(
        fetch_ref,
        target_sha,
        label="snapshot target evidence",
    )
    for item in branch_observations:
        if item["present"] is True:
            plane._publish_remote_evidence_ref(
                str(item["fetch_ref"]),
                str(item["sha"]),
                label=f"snapshot branch evidence {item['node_id']}",
            )
        else:
            plane.assert_canonical_remote_transport_identity()
            if plane._remote_ref_sha(str(item["fetch_ref"])) is not None:
                raise SystemExit(
                    "absent snapshot branch already has a reserved remote evidence ref: "
                    f"{item['branch']}"
                )

    snapshot = {
        "schema_version": 1,
        "kind": "hive-mind-github-snapshot-candidate-v1",
        "execution_namespace": execution_namespace,
        "execution_id": execution_id,
        "observation_id": observation_id,
        "observation_epoch": observation_epoch,
        "fetch_ref": fetch_ref,
        "repository": repository,
        "target_branch": branch,
        "target_sha": target_sha,
        "branch_observations": branch_observations,
        "pull_requests": pull_requests,
        "raw_pull_requests": raw_pull_requests,
        "branches": branches,
        "github_query": {
            "offline": bool(args.offline),
            "evidence_available": not bool(args.offline),
            "complete": not bool(args.offline),
            "node_queries": github_node_queries,
            "exit_code": 0,
        },
        "git_query": {
            "target_refspec": target_refspec,
            "branch_refspecs": branch_refspecs,
            "ls_remote_argv": ls_remote_argv,
        },
        "source_ref_observation": source_ref_observation,
    }
    snapshot["candidate_id"] = digest_json(snapshot)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    ) as handle:
        json.dump(snapshot, handle, indent=2, sort_keys=True, allow_nan=False)
        snapshot_path = handle.name

    try:
        run(
            [*autopilot_prefix,
             "install-github-snapshot", snapshot_path,
             "--observation-id", observation_id],
            cwd=root,
        )
    finally:
        Path(snapshot_path).unlink(missing_ok=True)
    print(f"snapshot installed: target={target_sha}")
    print(f"  pull_requests={len(pull_requests)} branches={len(branches)}")

    if args.reconcile:
        run(
            [*autopilot_prefix, "reconcile",
             "--target-sha", target_sha, "--actor", args.actor,
             "--reason", "scripted dispatcher snapshot and target reconciliation"],
            cwd=root,
        )
        print(f"reconciled: {target_sha}")
        if args.host_id:
            print(
                "next: "
                + render_command(
                    [
                        *autopilot_prefix,
                        "dispatch",
                        "--host-id",
                        args.host_id,
                        "--actor",
                        args.actor,
                    ]
                )
            )
    else:
        print(
            "next: "
            + render_command(
                [
                    *autopilot_prefix,
                    "reconcile",
                    "--target-sha",
                    target_sha,
                    "--actor",
                    "HOST:SESSION",
                    "--reason",
                    "<why>",
                ]
            )
        )
        if args.host_id:
            print(
                "then: "
                + render_command(
                    [
                        *autopilot_prefix,
                        "dispatch",
                        "--host-id",
                        args.host_id,
                        "--actor",
                        "HOST:SESSION",
                    ]
                )
            )
        else:
            print(
                "then: dispatch handoff withheld until --host-id names the "
                "authenticated host provider"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
