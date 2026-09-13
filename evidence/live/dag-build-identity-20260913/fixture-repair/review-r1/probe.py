"""Independent fixture transport/ref-availability review; external synthetic Git only."""
import ast
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path("C:/h/node-guide1")
OUT = Path(__file__).parent
OLD = "89925ecafc4ea4233ec921a26a6839bc2ca17f0a"
HEAD = "6e134f6251fdd30b6da712df8342d1d8986093a5"
TREE = "a38f5ce501198b87739743114e0e155c0bf5b080"
ENV = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
ENV.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_CONFIG_NOSYSTEM="1")
records = []


def git(root, *args, expected=0):
    command = ["git", "-C", str(root), *args]
    start = time.monotonic()
    result = subprocess.run(command, env=ENV, capture_output=True, timeout=45)
    records.append({"argv": command, "exit_code": result.returncode, "start": start, "finish": time.monotonic(),
                    "stdout": result.stdout.decode(errors="replace"), "stderr": result.stderr.decode(errors="replace")})
    if expected is not None:
        assert result.returncode == expected, records[-1]
    return result


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


assert git(ROOT, "rev-parse", "HEAD").stdout.decode().strip() == HEAD
assert git(ROOT, "rev-parse", "HEAD^{tree}").stdout.decode().strip() == TREE
assert not git(ROOT, "status", "--porcelain").stdout
path = "tests/test_generic_dag_v3_overlay.py"
old = git(ROOT, "show", OLD + ":" + path).stdout
new = git(ROOT, "show", HEAD + ":" + path).stdout


def assertions(raw):
    return Counter(ast.dump(n, include_attributes=False) for n in ast.walk(ast.parse(raw))
                   if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr.startswith("assert"))


before, after = assertions(old), assertions(new)
assert not before - after
assert new.count(b'"--no-local"') - old.count(b'"--no-local"') == 6
docs = []
for name in ("USER_GUIDE/README.md", "USER_GUIDE/00_START_HERE.md", "USER_GUIDE/07_GENERIC_DAG_EXECUTION.md"):
    raw = git(ROOT, "show", HEAD + ":" + name).stdout
    assert raw == git(ROOT, "show", OLD + ":" + name).stdout
    docs.append({"path": name, "sha256": sha(raw), "bytes": len(raw)})
evidence = "evidence/live/generic-dag-guide-20260913/ci-repair/"
manifest = json.loads(git(ROOT, "show", HEAD + ":" + evidence + "MANIFEST.json").stdout)
for item in manifest["artifacts"]:
    raw = git(ROOT, "show", HEAD + ":" + evidence + item["path"]).stdout
    assert sha(raw) == item["sha256"] and len(raw) == item["bytes"]
    assert raw == (ROOT / evidence / item["path"]).read_bytes()
assert not git(ROOT, "diff", "--name-only", OLD, HEAD, "src", "USER_GUIDE").stdout

source = OUT / "source"
source.mkdir()
git(source, "init", "--quiet", "--initial-branch=main")
git(source, "config", "user.name", "Independent transport fixture")
git(source, "config", "user.email", "review@example.invalid")
git(source, "config", "core.autocrlf", "false")
(source / "payload.txt").write_bytes(b"main payload\n")
git(source, "add", "payload.txt")
git(source, "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "main fixture")
main = git(source, "rev-parse", "HEAD").stdout.decode().strip()
tree = git(source, "rev-parse", "HEAD^{tree}").stdout.decode().strip()
git(source, "switch", "--quiet", "-c", "historical")
(source / "payload.txt").write_bytes(b"historical payload\n")
git(source, "add", "payload.txt")
git(source, "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "historical fixture")
historical = git(source, "rev-parse", "HEAD").stdout.decode().strip()
git(source, "update-ref", "refs/remotes/origin/historical", historical)
git(source, "switch", "--quiet", "main")
git(source, "branch", "-D", "historical")
private = Path("objects/info/source-maintenance-probe.lock")
marker = source / ".git" / private
marker.parent.mkdir(parents=True, exist_ok=True)
marker.write_bytes(b"private source metadata\n")
controls = []
for label, flags in (("local-copy", []), ("normal-transport", ["--no-local"])):
    target = OUT / label
    git(OUT, "clone", "--quiet", *flags, "--no-hardlinks", str(source), str(target))
    present = git(target, "cat-file", "-e", historical + "^{commit}", expected=None).returncode == 0
    checkout = git(target, "switch", "--quiet", "-C", "fixture-target", historical, expected=None)
    controls.append({"label": label, "private_metadata_copied": (target / ".git" / private).exists(),
                     "remote_tracking_only_commit_available": present, "switch_returncode": checkout.returncode,
                     "switch_stderr": checkout.stderr.decode(errors="replace")})
assert controls[0]["remote_tracking_only_commit_available"]
assert not controls[1]["remote_tracking_only_commit_available"]
assert controls[0]["private_metadata_copied"] and not controls[1]["private_metadata_copied"]


def maintain():
    for _ in range(8):
        git(source, "commit-graph", "write", "--reachable", "--split")


def clone(index):
    target = OUT / f"concurrent-{index}"
    git(OUT, "clone", "--quiet", "--no-local", "--no-hardlinks", str(source), str(target))
    assert git(target, "rev-parse", "HEAD").stdout.decode().strip() == main
    assert git(target, "rev-parse", "HEAD^{tree}").stdout.decode().strip() == tree
    assert (target / "payload.txt").read_bytes() == b"main payload\n"
    assert not (target / ".git" / private).exists()


with ThreadPoolExecutor(max_workers=4) as pool:
    futures = [pool.submit(maintain), *(pool.submit(clone, n) for n in range(3))]
    for future in futures:
        future.result()
assert marker.read_bytes() == b"private source metadata\n"
clones = [r for r in records if "clone" in r["argv"] and "concurrent-" in r["argv"][-1]]
writes = [r for r in records if "commit-graph" in r["argv"]]
overlaps = sum(c["start"] < w["finish"] and w["start"] < c["finish"] for c in clones for w in writes)
assert overlaps > 0
assert not git(ROOT, "status", "--porcelain").stdout
assert git(ROOT, "rev-parse", "HEAD").stdout.decode().strip() == HEAD
result = {"reviewer": "/root/continuity_repair_builder", "head": HEAD, "tree": TREE,
          "original_assertion_calls": sum(before.values()), "retained_original_assertion_calls": sum((before & after).values()),
          "added_assertion_calls": sum((after - before).values()), "added_no_local_options": 6,
          "unchanged_guide_artifacts": docs, "ci_repair_manifest_verified": True,
          "remote_ref_controls": controls, "concurrent_clones": 3, "commit_graph_writes": 8,
          "overlapping_intervals": overlaps, "candidate_clean": True,
          "limitation": "Windows synthetic Git probe; no claim to reproduce exact Linux race timing or run affected V3 tests.",
          "records": records}
(OUT / "PROBE-RESULTS.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: v for k, v in result.items() if k != "records"}, indent=2))
