#!/usr/bin/env python3
"""Fail-closed verifier for the sealed git-commit-observation-v1 DAG."""

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

from generate_plan import COMMON_FORBIDDEN, OUTPUT_PATH, build_plan, digest, render  # noqa: E402

MANIFEST_PATH = DAG_DIR / "manifest.json"
EXPECTED_NODE_IDS = [
    "GCO-SEAL-000",
    "GCO-BASELINE-010",
    "GCO-TEST-020",
    "GCO-ARCH-030",
    "GCO-BUILD-040",
    "GCO-INTEGRATE-050",
    "GCO-SAFETY-060",
    "GCO-SMOKE-070",
    "GCO-QUALIFY-080",
    "GCO-JUDGE-090",
]
EXPECTED_DEPENDENCIES = {
    "GCO-SEAL-000": [],
    "GCO-BASELINE-010": ["GCO-SEAL-000"],
    "GCO-TEST-020": ["GCO-SEAL-000"],
    "GCO-ARCH-030": ["GCO-SEAL-000", "GCO-BASELINE-010"],
    "GCO-BUILD-040": ["GCO-TEST-020", "GCO-ARCH-030"],
    "GCO-INTEGRATE-050": ["GCO-BUILD-040"],
    "GCO-SAFETY-060": ["GCO-INTEGRATE-050"],
    "GCO-SMOKE-070": ["GCO-SAFETY-060"],
    "GCO-QUALIFY-080": ["GCO-SMOKE-070"],
    "GCO-JUDGE-090": ["GCO-QUALIFY-080"],
}
EXPECTED_WRITE_SCOPES = {
    "GCO-SEAL-000": [
        "docs/execution/dags/git-commit-observation-v1/README.md",
        "docs/execution/dags/git-commit-observation-v1/.gitignore",
        "docs/execution/dags/git-commit-observation-v1/specs.py",
        "docs/execution/dags/git-commit-observation-v1/generate_plan.py",
        "docs/execution/dags/git-commit-observation-v1/verify_plan.py",
        "docs/execution/dags/git-commit-observation-v1/benchmark.py",
        "docs/execution/dags/git-commit-observation-v1/manifest.json",
        "evidence/courts/CASE-GIT-COMMIT-OBSERVATION-OPENING.json",
    ],
    "GCO-BASELINE-010": ["evidence/performance/git-commit-observation-v1/baseline-diagnostic.json"],
    "GCO-TEST-020": ["tests/test_doctor_git_fact_batching.py"],
    "GCO-ARCH-030": ["docs/architecture/ADR-064-ONE-SHOT-RAW-GIT-COMMIT-OBSERVATIONS.md"],
    "GCO-BUILD-040": [".autopilot/bin/controller.py"],
    "GCO-INTEGRATE-050": [".autopilot/bin/durable_controller.py"],
    "GCO-SAFETY-060": ["evidence/performance/git-commit-observation-v1/safety-qualification.json"],
    "GCO-SMOKE-070": [
        "evidence/performance/git-commit-observation-v1/smoke-python-3.14.json",
        "evidence/performance/git-commit-observation-v1/smoke-python-3.12.json",
    ],
    "GCO-QUALIFY-080": [
        "evidence/performance/git-commit-observation-v1/candidate-python-3.14.json",
        "evidence/performance/git-commit-observation-v1/candidate-python-3.12.json",
        "evidence/performance/git-commit-observation-v1/qualification.json",
    ],
    "GCO-JUDGE-090": ["evidence/courts/CASE-GIT-COMMIT-OBSERVATION-QUALIFICATION.json"],
}
EXPECTED_PRIMARY_ROLES = {
    "GCO-SEAL-000": "orchestrator",
    "GCO-BASELINE-010": "explorer",
    "GCO-TEST-020": "curator",
    "GCO-ARCH-030": "architect",
    "GCO-BUILD-040": "builder",
    "GCO-INTEGRATE-050": "integrator",
    "GCO-SAFETY-060": "steward",
    "GCO-SMOKE-070": "optimizer",
    "GCO-QUALIFY-080": "curator",
    "GCO-JUDGE-090": "orchestrator",
}
EXPECTED_SEALED_PATHS = [
    "docs/execution/dags/git-commit-observation-v1/.gitignore",
    "docs/execution/dags/git-commit-observation-v1/README.md",
    "docs/execution/dags/git-commit-observation-v1/benchmark.py",
    "docs/execution/dags/git-commit-observation-v1/generate_plan.py",
    "docs/execution/dags/git-commit-observation-v1/specs.py",
    "docs/execution/dags/git-commit-observation-v1/verify_plan.py",
    "evidence/courts/CASE-GIT-COMMIT-OBSERVATION-OPENING.json",
]


class VerificationError(RuntimeError):
    """The checked-in DAG sources or generated plan violate the sealed contract."""


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


def git_output(*args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
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


def verify_manifest_self(manifest: dict[str, Any]) -> None:
    binding = manifest.get("manifest_self")
    if not isinstance(binding, dict):
        raise VerificationError("manifest self-binding is missing")
    if binding.get("path") != "docs/execution/dags/git-commit-observation-v1/manifest.json":
        raise VerificationError("manifest self path changed")
    supplied = binding.get("canonical_material_sha256")
    material = json.loads(json.dumps(manifest))
    material["manifest_self"].pop("canonical_material_sha256", None)
    observed = digest(material)
    if supplied != observed:
        raise VerificationError(f"manifest material mismatch: expected {supplied}, observed {observed}")


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


def graph_round_count(nodes: list[dict[str, Any]]) -> int:
    levels: dict[str, int] = {}
    remaining = {str(item["id"]): item for item in nodes}
    while remaining:
        progressed = False
        for node_id, item in list(remaining.items()):
            dependencies = list(item["dependencies"])
            if all(dependency in levels for dependency in dependencies):
                levels[node_id] = 0 if not dependencies else 1 + max(levels[value] for value in dependencies)
                del remaining[node_id]
                progressed = True
        if not progressed:
            raise VerificationError("graph contains unresolved dependencies or a cycle")
    by_level: dict[int, list[dict[str, Any]]] = {}
    for item in nodes:
        by_level.setdefault(levels[str(item["id"])], []).append(item)
    rounds = 0
    for members in by_level.values():
        serial = [item for item in members if item.get("parallel_safe") is False]
        parallel = [item for item in members if item.get("parallel_safe") is True]
        rounds += len(serial) + (1 if parallel else 0)
    return rounds


def verify_node_contracts(plan: dict[str, Any]) -> None:
    nodes = plan.get("nodes")
    if not isinstance(nodes, list):
        raise VerificationError("generated nodes are missing")
    ids = [item.get("id") for item in nodes if isinstance(item, dict)]
    if ids != EXPECTED_NODE_IDS:
        raise VerificationError("generated node order mismatch")
    all_writes = {node_id: scopes for node_id, scopes in EXPECTED_WRITE_SCOPES.items()}
    for item in nodes:
        if not isinstance(item, dict):
            raise VerificationError("generated node must be an object")
        node_id = str(item.get("id"))
        if item.get("dependencies") != EXPECTED_DEPENDENCIES[node_id]:
            raise VerificationError(f"dependency mismatch for {node_id}")
        if item.get("write_scope") != EXPECTED_WRITE_SCOPES[node_id]:
            raise VerificationError(f"write scope mismatch for {node_id}")
        if item.get("file_locks") != EXPECTED_WRITE_SCOPES[node_id]:
            raise VerificationError(f"file locks do not cover write scope for {node_id}")
        if item.get("primary_role") != EXPECTED_PRIMARY_ROLES[node_id]:
            raise VerificationError(f"primary role mismatch for {node_id}")
        if not item.get("required_inputs") or not item.get("expected_outputs"):
            raise VerificationError(f"input/output contract missing from {node_id}")
        if not item.get("required_tests") or not item.get("stopping_condition") or not item.get("rollback"):
            raise VerificationError(f"test/stopping/rollback contract missing from {node_id}")
        forbidden = set(item.get("forbidden_scope", []))
        if not set(COMMON_FORBIDDEN).issubset(forbidden):
            raise VerificationError(f"global forbidden scope missing from {node_id}")
        required_other_writes = {
            scope
            for owner, scopes in all_writes.items()
            if owner != node_id
            for scope in scopes
        }
        if not required_other_writes.issubset(forbidden):
            raise VerificationError(f"other-node write scope missing from forbiddens for {node_id}")
        if set(item["write_scope"]) & forbidden:
            raise VerificationError(f"{node_id} forbids its own write scope")
        expected = item.get("contract_digest")
        material = dict(item)
        material.pop("contract_digest", None)
        if expected != digest(material):
            raise VerificationError(f"contract digest mismatch for {node_id}")
    covered = {item["primary_role"] for item in nodes}
    if covered != {"orchestrator", "explorer", "architect", "builder", "curator", "integrator", "steward", "optimizer"}:
        raise VerificationError(f"eight-role lifecycle incomplete: {sorted(covered)}")
    if graph_round_count(nodes) != 9:
        raise VerificationError("graph does not compile to the sealed nine rounds")


def verify_predecessor(name: str, binding: dict[str, Any]) -> None:
    verifier = REPO_ROOT / str(binding.get("verifier"))
    manifest = REPO_ROOT / str(binding.get("manifest"))
    if git_blob(verifier) != binding.get("verifier_blob"):
        raise VerificationError(f"{name} verifier changed")
    if git_blob(manifest) != binding.get("manifest_blob"):
        raise VerificationError(f"{name} manifest changed")
    completed = subprocess.run(
        (sys.executable, str(verifier)),
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
        raise VerificationError(f"{name} DAG verification failed: {completed.stdout[-2000:]}")
    try:
        result = json.loads(completed.stdout.splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as error:
        raise VerificationError(f"{name} verifier output was not JSON") from error
    if result.get("plan_digest") != binding.get("plan_digest"):
        raise VerificationError(f"{name} plan digest changed")


def verify() -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = read_json(MANIFEST_PATH)
    if manifest.get("schema_version") != 1 or manifest.get("plan_id") != "git-commit-observation-v1":
        raise VerificationError("manifest identity changed")
    if manifest.get("expected_node_ids") != EXPECTED_NODE_IDS:
        raise VerificationError("manifest node IDs mismatch")
    if manifest.get("expected_dependencies") != EXPECTED_DEPENDENCIES:
        raise VerificationError("manifest dependencies mismatch")
    verify_manifest_self(manifest)
    verify_manifest_sources(manifest)

    standard = manifest.get("standard")
    if not isinstance(standard, dict) or git_blob(REPO_ROOT / str(standard.get("path"))) != standard.get("git_blob_sha"):
        raise VerificationError("DAG authoring standard changed")

    sealed_plan = REPO_ROOT / str(manifest.get("sealed_plan_unchanged"))
    observed_plan_sha = "sha256:" + hashlib.sha256(sealed_plan.read_bytes()).hexdigest()
    if observed_plan_sha != manifest.get("sealed_plan_sha256"):
        raise VerificationError(".autopilot/plan.json changed")

    baseline = manifest.get("baseline")
    if not isinstance(baseline, dict):
        raise VerificationError("baseline binding missing")
    baseline_commit = str(baseline.get("commit"))
    if git_output("show", "-s", "--format=%T", baseline_commit) != baseline.get("tree"):
        raise VerificationError("baseline commit/tree mismatch")

    rejected = manifest.get("rejected_candidate")
    if not isinstance(rejected, dict):
        raise VerificationError("rejected candidate binding missing")
    if git_output("show", "-s", "--format=%T", str(rejected.get("commit"))) != rejected.get("tree"):
        raise VerificationError("rejected candidate commit/tree mismatch")
    for relative, expected in rejected.get("evidence", {}).items():
        if git_blob(REPO_ROOT / relative) != expected:
            raise VerificationError(f"rejected-candidate evidence changed: {relative}")

    predecessors = manifest.get("predecessor_dags")
    if not isinstance(predecessors, dict) or set(predecessors) != {"knowledge-projection-v1", "doctor-performance-v1"}:
        raise VerificationError("predecessor DAG bindings missing")
    for name, binding in predecessors.items():
        if not isinstance(binding, dict):
            raise VerificationError(f"malformed predecessor binding: {name}")
        verify_predecessor(name, binding)

    opening = read_json(REPO_ROOT / "evidence/courts/CASE-GIT-COMMIT-OBSERVATION-OPENING.json")
    if opening.get("case_id") != "CASE-GIT-COMMIT-OBSERVATION-OPENING" or opening.get("verdict", {}).get("disposition") != "adapt":
        raise VerificationError("opening court identity or disposition changed")

    plan = build_plan()
    verify_node_contracts(plan)
    if plan.get("plan_digest") != manifest.get("expected_plan_digest"):
        raise VerificationError("generated plan digest mismatch")
    if len(plan["nodes"]) != manifest.get("expected_node_count"):
        raise VerificationError("generated plan node count mismatch")
    if graph_round_count(plan["nodes"]) != manifest.get("expected_round_count"):
        raise VerificationError("generated plan round count mismatch")
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
        "round_count": graph_round_count(plan["nodes"]),
        "materialized": str(output) if args.write else None,
        "sealed_sources": len(manifest["sources"]) + 1,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.SubprocessError, VerificationError) as error:
        print(json.dumps({"verified": False, "error": str(error)}, sort_keys=True))
        raise SystemExit(2) from None
