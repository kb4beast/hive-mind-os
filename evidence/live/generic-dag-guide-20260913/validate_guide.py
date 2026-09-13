"""Read-only source checks plus inert CLI examples in an external fixture folder."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(r"C:\h\node-guide1")
OUT = Path(__file__).resolve().parent
PIN = "b19b2a177e2d10ebf49b565dcdd1ad9878bbaeac"
DOCS = ["USER_GUIDE/README.md", "USER_GUIDE/00_START_HERE.md", "USER_GUIDE/07_GENERIC_DAG_EXECUTION.md"]
SOURCES = ["AGENTS.md", "LICENSE", "pyproject.toml", "src/hive_mind_os/cli.py",
    "src/hive_mind_os/dag_cli.py", "src/hive_mind_os/dag_standard.py",
    "src/hive_mind_os/portable_plan.py", "src/hive_mind_os/subject_execution.py",
    "src/hive_mind_os/local_dag_runtime.py", "src/hive_mind_os/local_run_authority.py",
    "src/hive_mind_os/local_codex_worker.py", "src/hive_mind_os/compiled_tournament.py",
    "src/hive_mind_os/powershell_preparation.py", "docs/execution/PUBLIC_DAG_RUNTIME.md",
    "docs/execution/DAG_AUTHORING_STANDARD_V2.md", "tests/test_public_dag_cli.py",
    "tests/test_subject_execution.py", "tests/test_dag_standard_product.py",
    "tests/test_portable_plan.py", "tests/test_local_dag_runtime.py", "USER_GUIDE/00_START_HERE.md"]

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def git(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *args])

assert git("rev-parse", "HEAD").decode().strip() == PIN
sources = []
for name in SOURCES:
    raw = git("show", f"{PIN}:{name}")
    sources.append({"path": name, "git_blob": git("rev-parse", f"{PIN}:{name}").decode().strip(),
                    "sha256": digest(raw), "byte_count": len(raw)})
links = []
for name in DOCS:
    text = (ROOT / name).read_text(encoding="utf-8")
    for link in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
        if "://" not in link:
            target = (ROOT / name).parent / link.split("#")[0]
            assert target.is_file(), (name, link)
            links.append({"document": name, "target": link})
original_start = git("show", f"{PIN}:USER_GUIDE/00_START_HERE.md").decode()
assert original_start.split("\n", 2)[2] in (ROOT / DOCS[1]).read_text(encoding="utf-8")

fixture = OUT / "inert-fixture"
fixture.mkdir(exist_ok=False)
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from tests.test_dag_standard_product import STANDARD, compiler_plan
plan = compiler_plan()
(fixture / "plan.json").write_bytes(plan.canonical_bytes())
(fixture / "standard.md").write_bytes(STANDARD)
environment = os.environ.copy()
environment["PYTHONPATH"] = str(ROOT / "src")
records = []
def cli(label: str, args: list[str], expected: int = 0):
    command = [sys.executable, "-B", "-m", "hive_mind_os.cli", "dag", *args]
    result = subprocess.run(command, cwd=fixture, env=environment, capture_output=True, timeout=60)
    record = {"label": label, "argv": command, "exit_code": result.returncode}
    for stream in ("stdout", "stderr"):
        raw = getattr(result, stream)
        path = OUT / f"{label}.{stream}.txt"
        path.write_bytes(raw)
        record[stream] = {"path": str(path), "sha256": digest(raw), "byte_count": len(raw)}
    records.append(record)
    assert result.returncode == expected, record
    return json.loads(result.stdout) if result.stdout and "--help" not in args else result

for args in (["--help"], ["build", "--help"], ["execute", "--help"], ["resume", "--help"]):
    cli("help-" + (args[0] if args[0] != "--help" else "dag"), args)
bound = ["--plan", str(fixture / "plan.json"), "--standard", str(fixture / "standard.md"),
         "--expected-plan-digest", plan.digest(), "--mode", "repository"]
identity = ["--expected-request-id", plan.request_id, "--expected-subject-id", plan.subject.subject_id]
for command in ("validate", "rounds", "graph"):
    cli(command, [command, *bound, *identity])
cli("build", ["build", *bound, "--output", str(fixture / "sealed.json")])
assert (fixture / "sealed.json").read_bytes() == plan.canonical_bytes()
cli("build-existing", ["build", *bound, "--output", str(fixture / "sealed.json")], 2)
status = cli("missing-status", ["status", "--state-directory", str(fixture / "absent-state"),
    "--plan", str(fixture / "plan.json"), "--expected-plan-digest", plan.digest()])
assert status["state_present"] is False and not (fixture / "absent-state").exists()
cli("external-refusal", ["execute", *bound, "--state-directory", str(fixture / "absent-state")], 2)
assert not (fixture / "absent-state").exists()
assert "EXTERNAL_RUNTIME_REQUIRED" in (OUT / "external-refusal.stderr.txt").read_text()
cli("mismatched-identity", ["validate", *bound, "--expected-request-id", "sha256:" + "f" * 64], 2)

result = {"status": "passed", "scope": "Documentation link/source checks and inert CLI fixtures only; no local execution, activation, signing, or full suite run.",
    "base_commit": PIN, "base_tree": git("rev-parse", "HEAD^{tree}").decode().strip(),
    "sources": sources, "links": links, "historical_start_body_preserved": True, "commands": records,
    "document_working_bytes": [{"path": name, "sha256": digest((ROOT / name).read_bytes()),
                               "byte_count": (ROOT / name).stat().st_size} for name in DOCS]}
(OUT / "VALIDATION.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": "passed", "source_blobs": len(sources), "links": len(links), "inert_commands": len(records)}))
