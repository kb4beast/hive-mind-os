"""One worker process for the parallel-execution arena.

Runs in its own linked worktree and drives the packaged controller CLI through a
node's full lifecycle. It is a separate process on purpose: cross-worktree
authority can only be observed between real concurrent processes, never between
two objects inside one interpreter.

Every step is emitted as a JSON line so the arena test can assert on what
actually happened rather than on a return code alone.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "bin" / "autopilot.py"
# Suite names the node contract requires; the arena runs each node's real module
# and records that single outcome under every name the contract lists.
SUITES = {
    "EVAL-520": (
        ["-m", "unittest", "tests.test_hive_cortex_evaluation"],
        [
            "held-out-evaluation-tests",
            "pit-leakage-tests",
            "noise-floor-tests",
            "missing-artifact-quarantine-tests",
        ],
    ),
    "POISON-540": (
        [
            "-m", "unittest", "discover", "-s", "tests/hive_cortex",
            "-p", "test_learning_poisoning.py",
        ],
        ["memory-poisoning-suite", "stale-evidence-suite", "overgeneralization-suite"],
    ),
}


def run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )


def cli(worktree: Path, *args: str) -> subprocess.CompletedProcess:
    return run(sys.executable, str(BIN), "--repo-root", str(worktree), *args)


def emit(worker: str, step: str, **detail: object) -> None:
    print(
        json.dumps(
            {
                "t": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "worker": worker,
                "step": step,
                **detail,
            }
        ),
        flush=True,
    )


def main() -> int:
    (
        _script, root_text, worktree_text, node_id, branch,
        base, fingerprint, donor_text, lane, rival,
    ) = sys.argv
    root = Path(root_text)
    worktree = Path(worktree_text)
    donor = json.loads(donor_text)
    worker = "worker-" + lane
    owner = worker + "@" + worktree.name

    # Lane b probes the rival node first: a claim the other worktree already
    # holds must be refused, which is only observable through shared authority.
    if lane == "b":
        time.sleep(2.0)
        attack = cli(worktree, "claim", rival, "--owner", owner)
        emit(
            worker, "double-claim-probe", target=rival,
            rejected=attack.returncode != 0,
            message=(attack.stderr or attack.stdout).strip()[-160:],
        )
        if attack.returncode == 0:
            emit(worker, "fatal", reason="cross-worktree double claim was granted")
            return 1

    claimed = cli(worktree, "claim", node_id, "--owner", owner, "--publish-remote")
    emit(worker, "claim", node=node_id, ok=claimed.returncode == 0,
         message=(claimed.stderr or claimed.stdout).strip()[-160:])
    if claimed.returncode != 0:
        return 1

    # The published claim commit is the branch tip; node work builds on it so the
    # receipt retains exactly one claim in its base..final ancestry.
    run("git", "fetch", "--quiet", "origin", cwd=worktree)
    based = run("git", "checkout", "-B", branch, "origin/" + branch, cwd=worktree)
    if based.returncode != 0:
        emit(worker, "fatal", reason="claim-commit checkout failed",
             err=based.stderr[-200:])
        return 1

    checkout = run(
        "git", "checkout", donor["final_commit"], "--", *donor["changed_paths"],
        cwd=worktree,
    )
    if checkout.returncode != 0:
        emit(worker, "fatal", reason="donor checkout failed", err=checkout.stderr[-200:])
        return 1
    run("git", "add", "-A", cwd=worktree)
    committed = run(
        "git", "commit", "--quiet", "-m", node_id + ": arena node work", cwd=worktree
    )
    if committed.returncode != 0:
        emit(worker, "fatal", reason="commit failed", err=committed.stderr[-200:])
        return 1
    final = run("git", "rev-parse", "HEAD", cwd=worktree).stdout.strip()
    emit(worker, "work-committed", commit=final[:9], files=len(donor["changed_paths"]))

    command, suite_names = SUITES[node_id]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(worktree / "src")
    environment.pop("GIT_EDITOR", None)
    tested = subprocess.run(
        [sys.executable, *command], cwd=worktree, capture_output=True,
        text=True, encoding="utf-8", errors="replace", env=environment,
    )
    lines = (tested.stderr or tested.stdout).strip().splitlines()
    outcome = lines[-1] if lines else ""
    emit(worker, "node-tests", ok=tested.returncode == 0, result=outcome[:120])
    if tested.returncode != 0:
        emit(worker, "fatal", reason="node test suite failed")
        return 1

    pushed = run("git", "push", "--quiet", "origin", "HEAD:" + branch, cwd=worktree)
    if pushed.returncode != 0:
        emit(worker, "fatal", reason="push failed", err=pushed.stderr[-200:])
        return 1

    # The repository-wide gate: both lanes contend for one lease.
    if lane == "b":
        time.sleep(1.0)
    rejections = 0
    deadline = time.monotonic() + 120
    while True:
        lease = cli(worktree, "validation-lease-acquire", node_id, "--owner", owner)
        if lease.returncode == 0:
            emit(worker, "lease-acquired", after_rejections=rejections)
            break
        if time.monotonic() > deadline:
            emit(worker, "fatal", reason="validation lease never became available")
            return 1
        rejections += 1
        emit(worker, "lease-wait",
             message=(lease.stderr or lease.stdout).strip()[-140:])
        time.sleep(1.5)
    time.sleep(6.0 if lane == "a" else 1.0)
    released = cli(worktree, "validation-lease-release", node_id, "--owner", owner)
    emit(worker, "lease-released", ok=released.returncode == 0)

    changed = run(
        "git", "diff", "--name-only", base + ".." + final, cwd=worktree
    ).stdout.split()
    receipt = {
        "schema_version": 1,
        "plan_fingerprint": fingerprint,
        "node_id": node_id,
        "contract_version": 1,
        "base_commit": base,
        "final_commit": final,
        "base_tree": run(
            "git", "rev-parse", base + "^{tree}", cwd=worktree
        ).stdout.strip(),
        "final_tree": run(
            "git", "rev-parse", final + "^{tree}", cwd=worktree
        ).stdout.strip(),
        "branch": branch,
        "pr": None,
        "changed_paths": sorted(changed),
        "tests": [
            {
                "name": name,
                "status": "passed",
                "command": " ".join(["python", *command]),
                "result": outcome[:120],
            }
            for name in suite_names
        ],
        "evidence_refs": [
            "git-diff:" + base + ".." + final,
            "arena-test-run:" + " ".join(command) + " => " + outcome[:80],
        ],
        "model_runtime": donor["model_runtime"],
        "role_identities": donor["role_identities"],
        "authority": {
            "autonomy_level": "EXECUTION_AUTHORIZED",
            "claim_owner": owner,
            "grants": sorted(changed),
            "node_id": node_id,
        },
        "consultations": [],
        "acceptance_decision": "ADOPT",
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rollback_ref": base,
    }
    receipt_path = root / ("receipt-" + node_id + ".json")
    receipt_path.write_text(json.dumps(receipt, indent=1), encoding="utf-8")

    completed = cli(
        worktree, "complete", node_id, "--owner", owner, "--receipt", str(receipt_path)
    )
    emit(worker, "complete", ok=completed.returncode == 0,
         message=(completed.stderr or completed.stdout).strip()[-200:])
    if completed.returncode != 0:
        return 1
    run("git", "push", "--quiet", "origin", branch + ":" + branch, cwd=worktree)
    emit(worker, "done",
         receipt_commit=run("git", "rev-parse", branch, cwd=worktree).stdout.strip()[:9])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
