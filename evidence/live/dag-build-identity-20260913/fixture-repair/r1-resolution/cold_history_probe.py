"""Run repaired fixtures with no developer historical heads or copied objects."""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = Path(r"C:\h\node-guide1")
COLD = OUT / "cold-source"
ENV = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
ENV.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull})
records = []

def git(root, *args, expected=0):
    result = subprocess.run(["git", "-C", str(root), *args], env=ENV, capture_output=True, timeout=180)
    records.append({"argv": ["git", "-C", str(root), *args], "exit_code": result.returncode,
        "stdout": result.stdout.decode("utf-8", errors="replace"), "stderr": result.stderr.decode("utf-8", errors="replace")})
    assert (result.returncode == 0) is (expected == 0), records[-1]
    return result.stdout

branch = git(ROOT, "branch", "--show-current").decode().strip()
pin = git(ROOT, "rev-parse", "HEAD").decode().strip()
git(OUT, "clone", "--quiet", "--no-local", "--no-hardlinks", "--single-branch", "--no-tags", "--branch", branch, str(ROOT), str(COLD))
provenance = json.loads((COLD / "tests/fixtures/generic-v3-history.provenance.json").read_text())
for commit in provenance["required_commits"]:
    git(COLD, "cat-file", "-e", f"{commit}^{{commit}}", expected=1)
git(COLD, "cat-file", "-e", provenance["bundle"]["prerequisite_commit"] + "^{commit}")
file = "tests/test_generic_dag_v3_overlay.py"
repaired = (ROOT / file).read_bytes()
(COLD / file).write_bytes(repaired)

def assertions(raw):
    return [ast.dump(item, include_attributes=False) for item in ast.walk(ast.parse(raw))
        if isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute) and item.func.attr.startswith("assert")]
original = assertions(git(ROOT, "show", "89925ecafc4ea4233ec921a26a6839bc2ca17f0a:" + file))
current = assertions(repaired)
remaining = list(current)
for assertion in original:
    remaining.remove(assertion)

names = [
    "test_history_bundle_supplies_required_objects_to_prerequisite_only_repository",
    "test_authenticated_attributes_defeat_system_and_global_autocrlf",
    "test_authoring_authenticates_root_attributes_and_rejects_info_attributes_before_filters",
    "test_git_replace_hidden_worktree_and_mode_substitution_fail_closed",
]
ENV["PYTHONPATH"] = str(COLD / "src") + os.pathsep + str(COLD)
command = [sys.executable, "-B", "-m", "unittest", *("tests.test_generic_dag_v3_overlay.GenericDagV3OverlayTests." + name for name in names), "-v"]
with (OUT / "cold-focused.stdout.txt").open("wb") as stdout, (OUT / "cold-focused.stderr.txt").open("wb") as stderr:
    result = subprocess.run(command, cwd=COLD, env=ENV, stdout=stdout, stderr=stderr, timeout=1200)
report = {"status": "passed" if result.returncode == 0 else "failed", "source_commit": pin,
    "repaired_test_sha256": hashlib.sha256(repaired).hexdigest(),
    "original_assertion_calls_preserved": len(original), "current_assertion_calls": len(current),
    "cold_required_commits_initially_absent": provenance["required_commits"],
    "command": command, "exit_code": result.returncode, "records": records,
    "test_stdout_sha256": hashlib.sha256((OUT / "cold-focused.stdout.txt").read_bytes()).hexdigest(),
    "test_stderr_sha256": hashlib.sha256((OUT / "cold-focused.stderr.txt").read_bytes()).hexdigest()}
(OUT / "COLD-HISTORY-VALIDATION.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps({key: value for key, value in report.items() if key not in {"records", "command"}}))
raise SystemExit(result.returncode)
