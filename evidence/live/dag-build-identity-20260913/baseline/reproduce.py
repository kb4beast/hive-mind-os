"""Independent bounded baseline reproduction; no dispatcher or execution calls."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import datetime
import inspect
import argparse
import io
import tarfile

parser = argparse.ArgumentParser()
parser.add_argument("--repo", type=Path, default=Path(r"C:\h\continuity-draft1"))
parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent)
arguments = parser.parse_args()
ROOT = arguments.output.resolve()
ROOT.mkdir(parents=True, exist_ok=True)
REPO = arguments.repo.resolve()
PIN = "b19b2a177e2d10ebf49b565dcdd1ad9878bbaeac"
EXTRACT = ROOT / "baseline"
EXTRACT.mkdir(exist_ok=True)
def sha(data):
    return hashlib.sha256(data).hexdigest()
def git(*args):
    return subprocess.check_output(["git", "-C", str(REPO), *args])
fixture_paths = ["tests/test_portable_plan.py", "tests/test_dag_standard_product.py"]
archive = tarfile.open(fileobj=io.BytesIO(git("archive", "--format=tar", PIN, "src", *fixture_paths)), mode="r:")
sources = []
for member in archive.getmembers():
    if not member.isfile():
        continue
    path = member.name
    data = archive.extractfile(member).read()
    target = EXTRACT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    blob_id = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    sources.append({"path": path, "bytes": len(data), "sha256": sha(data), "git_blob": blob_id})
sys.dont_write_bytecode = True
sys.path[:0] = [str(EXTRACT / "src"), str(EXTRACT)]
from tests.test_dag_standard_product import compiler_plan, STANDARD
from hive_mind_os.subject_execution import SubjectExecutionService, SubjectExecutionMode

plan = compiler_plan()
inputs = ROOT / "inputs"
inputs.mkdir(exist_ok=True)
plan_path = inputs / "plan.json"
standard_path = inputs / "standard.md"
plan_path.write_bytes(plan.canonical_bytes())
standard_path.write_bytes(STANDARD)
outputs = ROOT / "outputs"
outputs.mkdir(exist_ok=True)
common = ["--plan", str(plan_path), "--standard", str(standard_path), "--expected-plan-digest", plan.digest()]
env = os.environ.copy()
env["PYTHONPATH"] = str(EXTRACT / "src")
env["PYTHONDONTWRITEBYTECODE"] = "1"
results = []
sentinel = b"existing-output-must-survive-a-rejected-identity\n"
wrong = "sha256:" + "e" * 64
assert wrong not in (plan.request_id, plan.subject.subject_id)
def output_record(path):
    return {"exists": path.exists(), "sha256": sha(path.read_bytes()) if path.exists() else None, "canonical_plan": path.exists() and path.read_bytes() == plan.canonical_bytes()}
def cli(case, args, output=None):
    command = [sys.executable, "-B", "-m", "hive_mind_os.dag_cli", *args]
    before = output_record(output) if output else None
    completed = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=30, check=False)
    row = {"case": case, "boundary": "CLI", "command": command, "cwd": str(ROOT), "pythonpath": env["PYTHONPATH"], "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr, "stdout_utf8_sha256": sha(completed.stdout.encode()), "stderr_utf8_sha256": sha(completed.stderr.encode()), "before": before, "after": output_record(output) if output else None}
    results.append(row)
    return row
service = SubjectExecutionService()
base = dict(plan_path=plan_path, standard_path=standard_path, expected_plan_digest=plan.digest(), mode=SubjectExecutionMode.REPOSITORY)
def service_call(case, operation, kwargs, output=None):
    before = output_record(output) if output else None
    row = {"case": case, "boundary": "service", "operation": operation, "arguments": {k: str(v) for k, v in kwargs.items()}, "before": before}
    try:
        response = getattr(service, operation)(**kwargs)
        row.update(result=response.to_document(), exception=None)
    except Exception as error:
        row.update(exception={"type": type(error).__name__, "message": str(error)})
    row["after"] = output_record(output) if output else None
    results.append(row)
    return row
for field in ("request", "subject"):
    flag = f"--expected-{field}-id"
    keyword = f"expected_{field}_id"
    control = cli(f"validate_wrong_{field}", ["validate", *common, flag, wrong])
    assert control["returncode"] == 2
    control = service_call(f"service_validate_wrong_{field}", "validate_files", {**base, keyword: wrong})
    assert control["exception"]["type"] == "ContractViolation"
    for existing in (False, True):
        suffix = "existing" if existing else "absent"
        output = outputs / f"cli_wrong_{field}_{suffix}.json"
        assert not output.exists(), "Run in a fresh report directory; retain prior results"
        if existing:
            output.write_bytes(sentinel)
        row = cli(f"build_wrong_{field}_{suffix}", ["build", *common, flag, wrong, "--output", str(output), *(["--replace"] if existing else [])], output)
        assert row["returncode"] == 0 and row["after"]["canonical_plan"]
        output = outputs / f"service_wrong_{field}_{suffix}.json"
        if existing:
            output.write_bytes(sentinel)
        row = service_call(f"service_build_wrong_{field}_{suffix}", "build_file", {**base, keyword: wrong, "output_path": output, "replace_existing": existing}, output)
        assert row["exception"]["type"] == "TypeError" and row["after"] == row["before"]
for existing in (False, True):
    output = outputs / f"service_omitted_{existing}.json"
    if existing:
        output.write_bytes(sentinel)
    row = service_call(f"service_build_omitted_{existing}", "build_file", {**base, "output_path": output, "replace_existing": existing}, output)
    assert row["exception"] is None and row["after"]["canonical_plan"]
output = outputs / "cli_matching.json"
row = cli("build_matching", ["build", *common, "--expected-request-id", plan.request_id, "--expected-subject-id", plan.subject.subject_id, "--output", str(output)], output)
assert row["returncode"] == 0 and row["after"]["canonical_plan"]
assert not list(outputs.glob("*.tmp"))
for item in sources:
    assert sha((EXTRACT / item["path"]).read_bytes()) == item["sha256"]
receipt = {"schema_version": 1, "reviewer": "/root/delivery_curator", "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "subject_commit": PIN, "subject_tree": git("rev-parse", f"{PIN}^{{tree}}").decode().strip(), "status": "reproduced", "python": sys.version, "python_executable": sys.executable, "service_signature": str(inspect.signature(service.build_file)), "actual_request_id": plan.request_id, "actual_subject_id": plan.subject.subject_id, "plan_digest": plan.digest(), "wrong_identity": wrong, "results": results, "source_bytes_unchanged": True, "source_manifest": sources, "limits": ["Only local inert plan build/validation operations invoked", "No authentication, activation, dispatcher, runtime execution or full suite", "Fixture helper imported from exact baseline tests; no test suite executed", "Direct service mismatches raise TypeError because the API lacks these keywords; silent loss is at the CLI boundary"]}
(ROOT / "RESULTS.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": receipt["status"], "cases": len(results), "source_files": len(sources), "cli_mismatch_writes": 4, "service_missing_keyword_rejections": 4, "results_sha256": sha((ROOT / "RESULTS.json").read_bytes())}, indent=2))
