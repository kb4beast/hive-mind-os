#!/usr/bin/env python3
"""Fail-closed verifier for the sealed doctor-performance-v1 DAG."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

DAG_DIR = Path(__file__).resolve().parent
REPO_ROOT = DAG_DIR.parents[3]
sys.path.insert(0, str(DAG_DIR))

from generate_plan import OUTPUT_PATH, build_plan, digest, render  # noqa: E402

MANIFEST_PATH = DAG_DIR / "manifest.json"
EXPECTED_NODE_IDS = [
    "DP-CONTRACT-000",
    "DP-TESTS-010",
    "DP-BENCH-020",
    "DP-FIXTURE-030",
    "DP-QUALIFY-040",
    "DP-JUDGE-050",
]
EXPECTED_DEPENDENCIES = {
    "DP-CONTRACT-000": [],
    "DP-TESTS-010": ["DP-CONTRACT-000"],
    "DP-BENCH-020": ["DP-CONTRACT-000"],
    "DP-FIXTURE-030": ["DP-TESTS-010", "DP-BENCH-020"],
    "DP-QUALIFY-040": ["DP-FIXTURE-030"],
    "DP-JUDGE-050": ["DP-QUALIFY-040"],
}
EXPECTED_SEALED_PATHS = [
    "docs/architecture/ADR-063-INVOCATION-SCOPED-TEST-FIXTURES.md",
    "docs/execution/dags/doctor-performance-v1/.gitignore",
    "docs/execution/dags/doctor-performance-v1/README.md",
    "docs/execution/dags/doctor-performance-v1/benchmark.py",
    "docs/execution/dags/doctor-performance-v1/generate_plan.py",
    "docs/execution/dags/doctor-performance-v1/specs.py",
    "docs/execution/dags/doctor-performance-v1/verify_plan.py",
    "evidence/courts/CASE-BASELINE-000-DOCTOR-PERFORMANCE.json",
]
EXPECTED_FORBIDDEN = {
    ".autopilot/plan.json",
    ".autopilot/control-plane.json",
    ".autopilot/bin/**",
    ".autopilot/state/**",
    "src/**",
    ".github/**",
    "docs/execution/dags/knowledge-projection-v1/**",
    "docs/plan/knowledge-projection-tournament-2026-08-13/**",
    "refs/heads/main",
    "refs/remotes/origin/**",
}


class VerificationError(RuntimeError):
    pass


def git_blob(path: Path) -> str:
    completed = subprocess.run(
        ("git", "hash-object", "--", str(path)),
        cwd=REPO_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return completed.stdout.strip()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise VerificationError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise VerificationError(f"{path} must contain an object")
    return value


def verify_manifest_sources(manifest: dict[str, Any]) -> None:
    sources = manifest.get("sources")
    if not isinstance(sources, dict) or sorted(sources) != sorted(EXPECTED_SEALED_PATHS):
        raise VerificationError("manifest source set is incomplete or unexpected")
    for relative in EXPECTED_SEALED_PATHS:
        path = REPO_ROOT / relative
        if not path.is_file():
            raise VerificationError(f"sealed source is missing: {relative}")
        observed = git_blob(path)
        expected = sources.get(relative)
        if observed != expected:
            raise VerificationError(
                f"sealed source mismatch for {relative}: expected {expected}, observed {observed}"
            )


def verify_node_contracts(plan: dict[str, Any]) -> None:
    nodes = plan.get("nodes")
    if not isinstance(nodes, list):
        raise VerificationError("generated nodes are missing")
    ids = [item.get("id") for item in nodes if isinstance(item, dict)]
    if ids != EXPECTED_NODE_IDS:
        raise VerificationError("generated node order mismatch")
    for item in nodes:
        if not isinstance(item, dict):
            raise VerificationError("generated node must be an object")
        node_id = str(item.get("id"))
        if item.get("dependencies") != EXPECTED_DEPENDENCIES[node_id]:
            raise VerificationError(f"dependency mismatch for {node_id}")
        if not EXPECTED_FORBIDDEN.issubset(set(item.get("forbidden_scope", []))):
            raise VerificationError(f"global forbidden scope missing from {node_id}")
        if not item.get("required_inputs") or not item.get("expected_outputs"):
            raise VerificationError(f"input/output contract missing from {node_id}")
        expected = item.get("contract_digest")
        material = dict(item)
        material.pop("contract_digest", None)
        if expected != digest(material):
            raise VerificationError(f"contract digest mismatch for {node_id}")

    fixture = next(item for item in nodes if item["id"] == "DP-FIXTURE-030")
    if fixture["write_scope"] != [
        ".autopilot/tests/fixture_support.py",
        ".autopilot/tests/test_healing.py",
    ]:
        raise VerificationError("fixture node write scope widened")
    if ".autopilot/tests/test_healing.py" in fixture["forbidden_scope"]:
        raise VerificationError("fixture node forbids its authorized healing fixture path")
    test_writes = next(item for item in nodes if item["id"] == "DP-TESTS-010")["write_scope"]
    if test_writes != [
        "tests/test_autopilot_fixture_seed.py",
        "tests/test_doctor_performance_contract.py",
    ]:
        raise VerificationError("independent test-author scope widened")


def verify() -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = read_json(MANIFEST_PATH)
    if manifest.get("expected_node_ids") != EXPECTED_NODE_IDS:
        raise VerificationError("manifest node IDs mismatch")
    if manifest.get("expected_dependencies") != EXPECTED_DEPENDENCIES:
        raise VerificationError("manifest dependencies mismatch")
    verify_manifest_sources(manifest)

    standard = manifest.get("standard")
    if not isinstance(standard, dict):
        raise VerificationError("standard seal missing")
    standard_path = REPO_ROOT / str(standard.get("path"))
    if git_blob(standard_path) != standard.get("git_blob_sha"):
        raise VerificationError("DAG authoring standard changed")

    sealed_plan = REPO_ROOT / str(manifest.get("sealed_plan_unchanged"))
    observed_sha = "sha256:" + hashlib.sha256(sealed_plan.read_bytes()).hexdigest()
    if observed_sha != manifest.get("sealed_plan_sha256"):
        raise VerificationError(".autopilot/plan.json changed")

    knowledge_verifier = REPO_ROOT / str(manifest.get("knowledge_plan_verifier"))
    if git_blob(knowledge_verifier) != manifest.get("knowledge_plan_verifier_blob"):
        raise VerificationError("knowledge plan verifier changed")
    completed = subprocess.run(
        (sys.executable, str(knowledge_verifier)),
        cwd=REPO_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode:
        raise VerificationError("knowledge DAG verification failed: " + completed.stdout[-2000:])

    plan = build_plan()
    verify_node_contracts(plan)
    if plan.get("plan_digest") != manifest.get("expected_plan_digest"):
        raise VerificationError("generated plan digest mismatch")
    if len(plan["nodes"]) != manifest.get("expected_node_count"):
        raise VerificationError("generated plan node count mismatch")
    return manifest, plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    manifest, plan = verify()
    output = REPO_ROOT / OUTPUT_PATH
    if args.write:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(render(plan))
    print(json.dumps({
        "verified": True,
        "plan_id": plan["plan_id"],
        "plan_digest": plan["plan_digest"],
        "node_count": len(plan["nodes"]),
        "materialized": str(output) if args.write else None,
        "sealed_sources": len(manifest["sources"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerificationError as error:
        print(json.dumps({"verified": False, "error": str(error)}, sort_keys=True))
        raise SystemExit(2) from None
