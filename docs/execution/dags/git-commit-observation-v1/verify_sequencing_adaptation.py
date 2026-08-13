#!/usr/bin/env python3
"""Fail-closed verifier for the additive GCO sequencing adaptation."""

from __future__ import annotations

import ast
import hashlib
import json
import py_compile
import subprocess
import sys
from pathlib import Path
from typing import Any


DAG_DIR = Path(__file__).resolve().parent
REPO_ROOT = DAG_DIR.parents[3]
MANIFEST_PATH = DAG_DIR / "sequencing-adaptation.manifest.json"
ADAPTATION_PATH = DAG_DIR / "sequencing-adaptation.json"
COURT_PATH = REPO_ROOT / "evidence/courts/CASE-GIT-COMMIT-OBSERVATION-SEQUENCING-APPEAL.json"
ORIGINAL_VERIFIER = DAG_DIR / "verify_plan.py"
ADJUDICATED_COMMIT = "794723765fc4755d7a371cfa54c8877d1037f048"
ORIGINAL_PLAN_DIGEST = "sha256:6d14f5dee38d15cb9608b7fb8092c4c1f28150961b70737def2fd4ede7f5a90d"
AUTOPILOT_PLAN_SHA256 = "sha256:85fd0c69fed4aa8cd40019bfeaccc5a686fa408ae5183060ae0320d412cea9ef"
EXPECTED_PATHS = [
    "docs/execution/dags/git-commit-observation-v1/sequencing-adaptation.json",
    "docs/execution/dags/git-commit-observation-v1/sequencing-adaptation.manifest.json",
    "docs/execution/dags/git-commit-observation-v1/verify_sequencing_adaptation.py",
    "evidence/courts/CASE-GIT-COMMIT-OBSERVATION-SEQUENCING-APPEAL.json",
]
PINNED_BLOBS = {
    "docs/execution/dags/git-commit-observation-v1/manifest.json": "4b12501a7b0b7a61477697892e040d5458468c13",
    "docs/execution/dags/git-commit-observation-v1/specs.py": "2946e786a14ac18b4805a0f5dab62b6380c88eb7",
    "docs/execution/dags/git-commit-observation-v1/verify_plan.py": "2d348a48616992eca2fca9b3c6bf63f50fc4cdbf",
    "tests/test_doctor_git_fact_batching.py": "37782c3282cbb23d54cef12c90c0a6ab9ffab63f",
    "docs/architecture/ADR-064-ONE-SHOT-RAW-GIT-COMMIT-OBSERVATIONS.md": "59d003bad3f5eefdd4319444995cc347c52f8ee1",
    "evidence/performance/git-commit-observation-v1/baseline-diagnostic.json": "5a01f59514a31d6338ff0a4c57d0639741e6b4b5",
    "evidence/courts/CASE-GIT-COMMIT-OBSERVATION-OPENING.json": "d3af08903e9f0a6a7eae8345562a9090e48d8843",
}
COMPLETED = [
    ("GCO-SEAL-000", "8e516cf2169d10b2c505c03020848629d5fbfd1e", "670e7b501d1052fd36fd8dfdd59254cdf48c3a0a"),
    ("GCO-BASELINE-010", "76b7d4ef5a9be3a72f8e246e72628a6609fc8ddb", "ba9f0eee6ef61e7ac6182bb12b61594d6d1e776e"),
    ("GCO-TEST-020", "8182cd433386d225aba72d0a6f39e3737d579c4a", "e5327ab3d30571a86c38e7baa6e0730912fceb35"),
    ("GCO-ARCH-030", ADJUDICATED_COMMIT, "dff7ccb1bcc74fa709e4b0e5b2f17cd4615591b4"),
]
EXPECTED_IDENTITIES = {
    "orchestrator": "/root",
    "independent-cross-examiner-and-curator": "/root/gco_contract_cross_exam",
    "appeals-judge": "/root/gco_contract_judge",
    "affected-builder": "/root/gco_build_040",
    "clerk": "/root/gco_erratum_seal_035",
}
SOLE_FAILURE = "test_24_durable_consumption_is_explicit_pure_and_never_retained"
EXPECTED_ADAPTATION_BLOB = "1fd6055becd4e23680e79d0aff33777310ad6e1b"
EXPECTED_COURT_BLOB = "843f5abd1a587959d1696ef16a1078c87f495304"


class VerificationError(RuntimeError):
    """The additive sequencing seal is incomplete or inconsistent."""


def git(*args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=REPO_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if check and completed.returncode:
        raise VerificationError(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise VerificationError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise VerificationError(f"{path} must contain one JSON object")
    return value


def blob(path: str | Path) -> str:
    target = Path(path)
    if not target.is_absolute():
        target = REPO_ROOT / target
    if not target.is_file():
        raise VerificationError(f"required file missing: {target}")
    return git("hash-object", "--", str(target))


def canonical_digest(value: dict[str, Any]) -> str:
    material = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(material).hexdigest()


def verify_original_seal() -> None:
    for path, expected in PINNED_BLOBS.items():
        observed = blob(path)
        if observed != expected:
            raise VerificationError(f"pinned input changed: {path}: expected {expected}, observed {observed}")
    observed_plan = "sha256:" + hashlib.sha256((REPO_ROOT / ".autopilot/plan.json").read_bytes()).hexdigest()
    if observed_plan != AUTOPILOT_PLAN_SHA256:
        raise VerificationError(f".autopilot/plan.json changed: {observed_plan}")
    completed = subprocess.run(
        (sys.executable, str(ORIGINAL_VERIFIER)),
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
        raise VerificationError(f"original GCO verifier failed: {completed.stdout[-2000:]}")
    try:
        result = json.loads(completed.stdout.splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as error:
        raise VerificationError("original GCO verifier did not return JSON") from error
    if result.get("verified") is not True or result.get("plan_digest") != ORIGINAL_PLAN_DIGEST:
        raise VerificationError(f"original GCO plan binding changed: {result}")
    for node_id, commit, tree in COMPLETED:
        if git("show", "-s", "--format=%T", commit) != tree:
            raise VerificationError(f"completed node commit/tree changed: {node_id}")


def verify_court(court: dict[str, Any]) -> None:
    if court.get("case_id") != "CASE-GIT-COMMIT-OBSERVATION-SEQUENCING-APPEAL":
        raise VerificationError("sequencing appeal case identity changed")
    if court.get("adjudicated_commit") != ADJUDICATED_COMMIT:
        raise VerificationError("sequencing appeal adjudicated commit changed")
    participants = court.get("participants")
    if not isinstance(participants, list):
        raise VerificationError("sequencing appeal participants missing")
    observed = {item.get("seat"): item.get("identity") for item in participants if isinstance(item, dict)}
    if observed != EXPECTED_IDENTITIES:
        raise VerificationError(f"sequencing appeal identities changed: {observed}")
    unseated = court.get("unseated_roles")
    if not isinstance(unseated, dict) or "No separate Advocate" not in str(unseated.get("advocate")):
        raise VerificationError("unseated Advocate limitation missing")
    if "No separate Expert Witness" not in str(unseated.get("expert_witness")):
        raise VerificationError("unseated Expert limitation missing")
    if "does not adjudicate implementation merit or performance" not in str(unseated.get("limitation")):
        raise VerificationError("appeal adjudication limitation missing")
    verdict = court.get("verdict")
    expected_false = (
        "implementation_merit_adjudicated",
        "performance_adjudicated",
        "promotion_authorized",
        "superiority_claim_authorized",
        "baseline_retry_authorized",
        "remote_authority_granted",
    )
    if not isinstance(verdict, dict) or verdict.get("disposition") != "adapt":
        raise VerificationError("appeal ADAPT verdict missing")
    if any(verdict.get(key) is not False for key in expected_false):
        raise VerificationError("appeal exceeded bounded authority")


def verify_adaptation(adaptation: dict[str, Any]) -> None:
    if adaptation.get("adaptation_id") != "git-commit-observation-v1-sequencing-adaptation":
        raise VerificationError("adaptation identity changed")
    if adaptation.get("adjudicated_commit") != ADJUDICATED_COMMIT:
        raise VerificationError("adaptation adjudicated commit changed")
    original = adaptation.get("original_plan")
    if original != {
        "status": "permanently-historical-and-quarantined",
        "digest": ORIGINAL_PLAN_DIGEST,
        "manifest_blob": PINNED_BLOBS["docs/execution/dags/git-commit-observation-v1/manifest.json"],
        "autopilot_plan_sha256": AUTOPILOT_PLAN_SHA256,
    }:
        raise VerificationError("original plan quarantine or binding changed")
    completed = adaptation.get("completed_nodes")
    expected_completed = [{"id": node, "commit": commit, "tree": tree} for node, commit, tree in COMPLETED]
    if completed != expected_completed:
        raise VerificationError("carried-forward completion changed")
    nodes = adaptation.get("adapted_nodes")
    if not isinstance(nodes, list) or [item.get("id") for item in nodes if isinstance(item, dict)] != [
        "GCO-ERRATUM-SEAL-035", "GCO-BUILD-040", "GCO-INTEGRATE-050"
    ]:
        raise VerificationError("adapted node sequence changed")
    seal, build, integrate = nodes
    if seal.get("dependencies") != ["GCO-TEST-020", "GCO-ARCH-030"]:
        raise VerificationError("erratum dependencies changed")
    if sorted(seal.get("write_scope", [])) != EXPECTED_PATHS:
        raise VerificationError("erratum four-file scope changed")
    if build.get("dependencies") != ["GCO-ERRATUM-SEAL-035"] or build.get("write_scope") != [".autopilot/bin/controller.py"]:
        raise VerificationError("superseded Builder dependency or scope changed")
    producer = build.get("producer_test_contract")
    if not isinstance(producer, dict) or producer.get("sole_expected_failure") != SOLE_FAILURE:
        raise VerificationError("Builder sole expected failure changed")
    methods = producer.get("must_pass_methods")
    test_tree = ast.parse((REPO_ROOT / "tests/test_doctor_git_fact_batching.py").read_text(encoding="utf-8"))
    contract = next(
        (node for node in test_tree.body if isinstance(node, ast.ClassDef) and node.name == "GitCommitObservationContract"),
        None,
    )
    if contract is None:
        raise VerificationError("GitCommitObservationContract class is missing")
    all_methods = [
        node.name for node in contract.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
    ]
    expected_methods = [name for name in all_methods if name != SOLE_FAILURE]
    if methods != expected_methods or len(methods) != 27 or len(all_methods) != 28:
        raise VerificationError("Builder producer subset is not the exact 27-method complement")
    required_tail = [
        "test_25_effect_boundaries_keep_fresh_cas_and_force_with_lease_reads",
        "test_26_sealed_recovery_and_release_barrier_cannot_consume_observation",
        "test_27_existing_autopilot_test_tree_is_frozen_by_scope",
    ]
    if producer.get("must_pass_after_expected_failure") != required_tail or not producer.get("any_other_failure_blocks"):
        raise VerificationError("Builder tail or fail-closed rule changed")
    if integrate.get("dependencies") != ["exact-provisional-GCO-BUILD-040-commit-and-digest-receipt"]:
        raise VerificationError("Integrator exact provisional dependency changed")
    if integrate.get("write_scope") != [".autopilot/bin/durable_controller.py"]:
        raise VerificationError("Integrator one-file scope changed")
    gates = integrate.get("required_gates")
    if not isinstance(gates, dict) or gates.get("focused") != "all 28 GitCommitObservationContract methods pass":
        raise VerificationError("Integrator 28-test green gate changed")
    if gates.get("immutable_surfaces") != [".autopilot/bin/sealed_recovery.py", ".autopilot/bin/release_barrier.py"]:
        raise VerificationError("recovery/release immutability changed")
    if adaptation.get("unchanged_blocked_tail") != ["GCO-SAFETY-060", "GCO-SMOKE-070", "GCO-QUALIFY-080", "GCO-JUDGE-090"]:
        raise VerificationError("blocked tail changed")
    if adaptation.get("completion_claim") is not False or adaptation.get("superiority_claim") is not False:
        raise VerificationError("adaptation makes an unauthorized completion or superiority claim")


def verify_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != 1 or manifest.get("adaptation_id") != "git-commit-observation-v1-sequencing-adaptation":
        raise VerificationError("sequencing manifest identity changed")
    if manifest.get("adjudicated_commit") != ADJUDICATED_COMMIT:
        raise VerificationError("sequencing manifest adjudicated commit changed")
    if manifest.get("original_plan_digest") != ORIGINAL_PLAN_DIGEST or manifest.get("autopilot_plan_sha256") != AUTOPILOT_PLAN_SHA256:
        raise VerificationError("sequencing manifest original-plan binding changed")
    if manifest.get("pinned_inputs") != PINNED_BLOBS:
        raise VerificationError("sequencing manifest pinned input set changed")
    sources = manifest.get("sources")
    expected_sources = [path for path in EXPECTED_PATHS if not path.endswith("sequencing-adaptation.manifest.json")]
    if not isinstance(sources, dict) or sorted(sources) != sorted(expected_sources):
        raise VerificationError("sequencing manifest source set changed")
    if sources.get("docs/execution/dags/git-commit-observation-v1/sequencing-adaptation.json") != EXPECTED_ADAPTATION_BLOB:
        raise VerificationError("sequencing adaptation canonical blob changed")
    if sources.get("evidence/courts/CASE-GIT-COMMIT-OBSERVATION-SEQUENCING-APPEAL.json") != EXPECTED_COURT_BLOB:
        raise VerificationError("sequencing appeal canonical blob changed")
    for path, expected in sources.items():
        if blob(path) != expected:
            raise VerificationError(f"sequencing source blob mismatch: {path}")
    binding = manifest.get("manifest_self")
    if not isinstance(binding, dict) or binding.get("path") != "docs/execution/dags/git-commit-observation-v1/sequencing-adaptation.manifest.json":
        raise VerificationError("sequencing manifest self-binding missing")
    supplied = binding.get("canonical_material_sha256")
    material = json.loads(json.dumps(manifest))
    material["manifest_self"].pop("canonical_material_sha256", None)
    observed = canonical_digest(material)
    if supplied != observed:
        raise VerificationError(f"sequencing manifest material mismatch: expected {supplied}, observed {observed}")
    if manifest.get("permitted_delta") != {"status": "added-only", "paths": EXPECTED_PATHS, "commit_count": 1}:
        raise VerificationError("sequencing manifest permitted delta changed")


def verify_delta() -> str:
    head = git("rev-parse", "HEAD")
    if head == ADJUDICATED_COMMIT:
        if git("diff", "--name-only") or git("diff", "--cached", "--name-only"):
            raise VerificationError("tracked or staged changes exist before erratum commit")
        untracked = sorted(filter(None, git("ls-files", "--others", "--exclude-standard").splitlines()))
        if untracked != EXPECTED_PATHS:
            raise VerificationError(f"pre-commit delta is not exactly four untracked files: {untracked}")
        return "pre-commit"
    if git("rev-list", "--count", f"{ADJUDICATED_COMMIT}..HEAD") != "1":
        raise VerificationError("erratum must be exactly one commit after the adjudicated commit")
    if git("show", "-s", "--format=%P", "HEAD") != ADJUDICATED_COMMIT:
        raise VerificationError("erratum commit parent is not the adjudicated commit")
    changed = git("diff", "--name-status", f"{ADJUDICATED_COMMIT}..HEAD").splitlines()
    expected = [f"A\t{path}" for path in EXPECTED_PATHS]
    if sorted(changed) != sorted(expected):
        raise VerificationError(f"committed delta is not exactly four added files: {changed}")
    if git("status", "--porcelain=v1"):
        raise VerificationError("erratum worktree is not clean after commit")
    return "committed"


def main() -> int:
    verify_original_seal()
    court = read_json(COURT_PATH)
    adaptation = read_json(ADAPTATION_PATH)
    manifest = read_json(MANIFEST_PATH)
    verify_court(court)
    verify_adaptation(adaptation)
    verify_manifest(manifest)
    state = verify_delta()
    py_compile.compile(str(Path(__file__).resolve()), doraise=True)
    print(json.dumps({
        "verified": True,
        "adaptation_id": adaptation["adaptation_id"],
        "adjudicated_commit": ADJUDICATED_COMMIT,
        "original_plan_digest": ORIGINAL_PLAN_DIGEST,
        "delta_state": state,
        "permitted_paths": EXPECTED_PATHS,
        "manifest_digest": manifest["manifest_self"]["canonical_material_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.SubprocessError, VerificationError, py_compile.PyCompileError) as error:
        print(json.dumps({"verified": False, "error": str(error)}, sort_keys=True))
        raise SystemExit(2) from None
