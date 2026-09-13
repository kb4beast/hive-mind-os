"""Retained fixture transport control and concurrent commit-graph exercise."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

OUT = Path(__file__).resolve().parent
ROOT = Path(r"C:\h\node-guide1")
SOURCE = OUT / "source"
SOURCE.mkdir(exist_ok=False)
ENV = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
ENV.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull})
RECORDS = []

def git(repo, *args):
    command = ["git", "-C", str(repo), *args]
    started = time.monotonic()
    result = subprocess.run(command, env=ENV, capture_output=True, timeout=120)
    RECORDS.append({"argv": command, "exit_code": result.returncode,
        "started_monotonic": started, "finished_monotonic": time.monotonic(),
        "stdout": result.stdout.decode("utf-8", errors="replace"),
        "stderr": result.stderr.decode("utf-8", errors="replace")})
    assert result.returncode == 0, RECORDS[-1]
    return result.stdout.strip().decode()

git(SOURCE, "init", "--quiet")
git(SOURCE, "config", "user.name", "Transport fixture")
git(SOURCE, "config", "user.email", "transport@example.invalid")
git(SOURCE, "config", "core.autocrlf", "false")
(SOURCE / "payload.txt").write_bytes(b"immutable payload\n")
git(SOURCE, "add", "payload.txt")
git(SOURCE, "commit", "--quiet", "-m", "fixture")
head, tree = git(SOURCE, "rev-parse", "HEAD"), git(SOURCE, "rev-parse", "HEAD^{tree}")
relative = Path("objects/info/source-maintenance-probe.lock")
marker = SOURCE / ".git" / relative
marker.parent.mkdir(parents=True, exist_ok=True)
marker.write_bytes(b"source-only maintenance metadata\n")
controls = []
for name, switches, copied in (("pre-fix", [], True), ("fixed", ["--no-local"], False)):
    target = OUT / name
    git(OUT, "clone", "--quiet", *switches, "--no-hardlinks", str(SOURCE), str(target))
    assert (target / ".git" / relative).exists() is copied
    assert git(target, "rev-parse", "HEAD") == head
    assert git(target, "rev-parse", "HEAD^{tree}") == tree
    assert (target / "payload.txt").read_bytes() == (SOURCE / "payload.txt").read_bytes()
    controls.append({"name": name, "marker_copied": copied, "head": head, "tree": tree})

def maintain():
    for _ in range(6):
        git(SOURCE, "commit-graph", "write", "--reachable", "--split")

def clone_during_maintenance(index):
    target = OUT / f"concurrent-{index}"
    git(OUT, "clone", "--quiet", "--no-local", "--no-hardlinks", str(SOURCE), str(target))
    assert git(target, "rev-parse", "HEAD") == head
    assert git(target, "rev-parse", "HEAD^{tree}") == tree
    assert not (target / ".git" / relative).exists()
    assert (target / "payload.txt").read_bytes() == (SOURCE / "payload.txt").read_bytes()

with ThreadPoolExecutor(max_workers=4) as pool:
    futures = [pool.submit(maintain), *(pool.submit(clone_during_maintenance, n) for n in range(3))]
    for future in futures:
        future.result()

clones = [r for r in RECORDS if "clone" in r["argv"] and "concurrent-" in r["argv"][-1]]
maintenance = [r for r in RECORDS if "commit-graph" in r["argv"]]
overlaps = sum(c["started_monotonic"] < m["finished_monotonic"] and m["started_monotonic"] < c["finished_monotonic"] for c in clones for m in maintenance)
assert overlaps > 0, "No command interval overlap observed"
failure = Path(r"C:\h\node-completeness-audit\pr179-linux314-failure-api.log")
failure_copy = OUT / failure.name
failure_copy.write_bytes(failure.read_bytes())
result = {"status": "passed", "controls": controls, "concurrent_transport_clones": len(clones),
    "commit_graph_writes": len(maintenance), "overlapping_command_pairs": overlaps,
    "failed_ci_evidence": {"path": str(failure_copy), "sha256": hashlib.sha256(failure.read_bytes()).hexdigest()},
    "limitations": "Command intervals overlap; no claim that the exact Linux disappearance timing was reproduced. Stable marker control deterministically distinguishes private-directory copying from object transport.",
    "records": RECORDS}
(OUT / "TRANSPORT-VALIDATION.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps({key: value for key, value in result.items() if key not in {"records", "controls"}}))
