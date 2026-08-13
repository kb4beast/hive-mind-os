#!/usr/bin/env python3
"""Fail-closed benchmark harness for git-commit-observation-v1.

Sealing runs only ``self-test``. Diagnostic, smoke, and qualification commands are
for their authorized DAG nodes. The harness never changes the doctor command,
timeout, test discovery, source, or Git state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[4]
EXACT_DOCTOR_SUFFIX = (
    ".autopilot/bin/autopilot.py",
    "--repo-root",
    ".",
    "doctor",
    "--json",
)
DOCTOR_TIMEOUT_SECONDS = 180
OUTER_TIMEOUT_SECONDS = 240
MINIMUM_QUALIFICATION_TRIALS = 6
QUALIFICATION_P95_SECONDS = 135.0
VECTOR_TOTAL = 381
VECTOR_PASSED = 380
VECTOR_SKIPPED = 1
VECTOR_DIGEST = "sha256:7c0cf4ae7a2efca60af613b1702c97133a28b043bad09b231fe3a6c97d23eef4"
CONDITIONAL_SKIP_ID = (
    "test_orchestration.IntentOrchestrationTests."
    "test_binding_state_symlink_escape_is_rejected"
)
REJECTED_CANDIDATE = {
    "commit": "41950b74bdec2b6e1c48ee7f5ef3ce947d0c8378",
    "tree": "b02326bf108de2fbaa2f174975f937979c02bf90",
    "disposition": "reject",
}


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def run_git(*args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return completed.stdout.strip()


def nearest_rank_p95(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("at least one duration is required")
    ordered = sorted(float(value) for value in values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def trial_modes(count: int) -> list[str]:
    if count < MINIMUM_QUALIFICATION_TRIALS:
        raise ValueError(f"at least {MINIMUM_QUALIFICATION_TRIALS} trials are required")
    return ["cold" if index % 2 == 0 else "warm" for index in range(count)]


def tracked_snapshot() -> dict[str, str]:
    entries = run_git("ls-files", "-s", "--", ".autopilot", "tests/test_doctor_git_fact_batching.py").splitlines()
    normalized = [line for line in entries if line and "/state/" not in line]
    return {
        "commit": run_git("rev-parse", "HEAD"),
        "tree": run_git("rev-parse", "HEAD^{tree}"),
        "index_tree": run_git("write-tree"),
        "tracked_surface_digest": digest(normalized),
        "tracked_entry_count": str(len(normalized)),
    }


def execution_environment(python: str) -> dict[str, Any]:
    probe = subprocess.run(
        (
            python,
            "-c",
            "import json,platform,sys;print(json.dumps({'executable':sys.executable,'version':platform.python_version(),'implementation':platform.python_implementation()}))",
        ),
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return {
        "runtime": json.loads(probe.stdout),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "working_directory": str(ROOT),
        "network_policy": "no-network",
        "process_environment_values_retained": False,
        "process_environment_omission_reason": "credential-safety",
    }


def phase_modes(phase: str, count: int) -> list[str]:
    if phase in {"baseline-diagnostic", "smoke"}:
        if count != 1:
            raise ValueError(f"{phase} requires exactly one fresh trial")
        return ["diagnostic" if phase == "baseline-diagnostic" else "smoke"]
    if phase == "candidate":
        return trial_modes(count)
    raise ValueError(f"unsupported phase: {phase}")


def run_trials(*, python: str, runtime_id: str, phase: str, count: int) -> dict[str, Any]:
    modes = phase_modes(phase, count)
    command = [python, *EXACT_DOCTOR_SUFFIX]
    trials: list[dict[str, Any]] = []
    for index, mode in enumerate(modes, start=1):
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=OUTER_TIMEOUT_SECONDS,
            )
            elapsed = time.perf_counter() - started
            output = completed.stdout
            trials.append({
                "index": index,
                "mode": mode,
                "fresh_process": True,
                "elapsed_seconds": round(elapsed, 6),
                "exit_code": completed.returncode,
                "outer_timeout": False,
                "stdout_sha256": "sha256:" + hashlib.sha256(output.encode("utf-8")).hexdigest(),
                "doctor_passed": completed.returncode == 0,
            })
        except subprocess.TimeoutExpired as error:
            elapsed = time.perf_counter() - started
            output = error.stdout if isinstance(error.stdout, str) else ""
            trials.append({
                "index": index,
                "mode": mode,
                "fresh_process": True,
                "elapsed_seconds": round(elapsed, 6),
                "exit_code": None,
                "outer_timeout": True,
                "stdout_sha256": "sha256:" + hashlib.sha256(output.encode("utf-8")).hexdigest(),
                "doctor_passed": False,
            })
    durations = [float(item["elapsed_seconds"]) for item in trials]
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "kind": "git-commit-observation-benchmark-receipt-v1",
        "phase": phase,
        "runtime_id": runtime_id,
        "command": command,
        "doctor_internal_timeout_seconds": DOCTOR_TIMEOUT_SECONDS,
        "outer_timeout_seconds": OUTER_TIMEOUT_SECONDS,
        "trial_policy": {
            "actual_trials": count,
            "modes": modes,
            "fresh_process_every_trial": True,
            "cold_warm_is_declared_not_an_os_cache_eviction_claim": True,
        },
        "source": tracked_snapshot(),
        "environment": execution_environment(python),
        "frozen_behavior_contract": {
            "total": VECTOR_TOTAL,
            "passed": VECTOR_PASSED,
            "skipped": VECTOR_SKIPPED,
            "conditional_skip_id": CONDITIONAL_SKIP_ID,
            "complete_unittest_id_set_sha256": VECTOR_DIGEST,
        },
        "comparators": {
            "doctor_baseline": "evidence/performance/doctor-performance-v1/baseline-summary.json",
            "rejected_fixture_candidate": REJECTED_CANDIDATE,
        },
        "trials": trials,
        "metrics": {
            "nearest_rank_p95_seconds": nearest_rank_p95(durations),
            "all_below_doctor_timeout": all(value < DOCTOR_TIMEOUT_SECONDS for value in durations),
            "all_doctor_passed": all(bool(item["doctor_passed"]) for item in trials),
            "qualification_limit_seconds": QUALIFICATION_P95_SECONDS,
        },
        "diagnostic_only": phase == "baseline-diagnostic",
        "promotion_authority": False,
        "superiority_claim": False,
    }
    receipt["receipt_digest"] = digest(receipt)
    return receipt


def verify_receipt(receipt: dict[str, Any], *, phase: str, require_qualification: bool = False) -> None:
    supplied = receipt.get("receipt_digest")
    material = dict(receipt)
    material.pop("receipt_digest", None)
    if supplied != digest(material):
        raise ValueError("receipt digest mismatch")
    if receipt.get("phase") != phase:
        raise ValueError("receipt phase mismatch")
    command = receipt.get("command")
    if not isinstance(command, list) or tuple(command[1:]) != EXACT_DOCTOR_SUFFIX:
        raise ValueError("doctor command changed")
    if receipt.get("doctor_internal_timeout_seconds") != DOCTOR_TIMEOUT_SECONDS:
        raise ValueError("doctor timeout changed")
    trials = receipt.get("trials")
    if not isinstance(trials, list):
        raise ValueError("trials are missing")
    expected_modes = phase_modes(phase, len(trials))
    if [item.get("mode") for item in trials] != expected_modes:
        raise ValueError("trial mode schedule changed")
    if not all(item.get("fresh_process") is True for item in trials):
        raise ValueError("every trial must use a fresh process")
    durations = [float(item["elapsed_seconds"]) for item in trials]
    observed = float(receipt["metrics"]["nearest_rank_p95_seconds"])
    if observed != nearest_rank_p95(durations):
        raise ValueError("nearest-rank p95 mismatch")
    frozen = receipt.get("frozen_behavior_contract", {})
    if frozen.get("total") != VECTOR_TOTAL or frozen.get("complete_unittest_id_set_sha256") != VECTOR_DIGEST:
        raise ValueError("frozen behavior contract changed")
    if require_qualification:
        if phase != "candidate" or len(trials) < MINIMUM_QUALIFICATION_TRIALS:
            raise ValueError("qualification requires at least six candidate trials")
        if not all(bool(item.get("doctor_passed")) for item in trials):
            raise ValueError("candidate doctor trial failed")
        if not all(value < DOCTOR_TIMEOUT_SECONDS for value in durations):
            raise ValueError("candidate doctor trial reached timeout")
        if observed > QUALIFICATION_P95_SECONDS:
            raise ValueError("candidate p95 exceeds qualification limit")


def receipt_passes_smoke(receipt: dict[str, Any]) -> bool:
    verify_receipt(receipt, phase="smoke")
    trial = receipt["trials"][0]
    return bool(trial["doctor_passed"]) and float(trial["elapsed_seconds"]) < DOCTOR_TIMEOUT_SECONDS


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_command(command: Sequence[str]) -> tuple[dict[str, Any], str]:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = completed.stdout
    return ({
        "command": list(command),
        "elapsed_seconds": round(time.perf_counter() - started, 6),
        "exit_code": completed.returncode,
        "passed": completed.returncode == 0,
        "stdout_sha256": "sha256:" + hashlib.sha256(output.encode("utf-8")).hexdigest(),
    }, output)


DISCOVERY_PROGRAM = r"""
import hashlib,json,sys,unittest
from pathlib import Path
root=Path(sys.argv[1]).resolve();sys.path.insert(0,str(root))
suite=unittest.defaultTestLoader.discover(str(root),pattern='test_*.py',top_level_dir=str(root))
def flatten(item):
    for child in item:
        if isinstance(child,unittest.TestSuite): yield from flatten(child)
        else: yield child
ids=[case.id() for case in flatten(suite)]
body=('\n'.join(ids)+'\n').encode()
print(json.dumps({'count':len(ids),'digest':'sha256:'+hashlib.sha256(body).hexdigest(),'conditional_skip_present':%r in ids}))
""" % CONDITIONAL_SKIP_ID


def discover_vector(python: str) -> dict[str, Any]:
    completed = subprocess.run(
        (python, "-c", DISCOVERY_PROGRAM, str(ROOT / ".autopilot" / "tests")),
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    value = json.loads(completed.stdout)
    value["matches_frozen"] = (
        value.get("count") == VECTOR_TOTAL
        and value.get("digest") == VECTOR_DIGEST
        and value.get("conditional_skip_present") is True
    )
    return value


def not_run_receipt(runtime_id: str, reason: str, source: dict[str, str]) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": 1,
        "kind": "git-commit-observation-not-run-receipt-v1",
        "phase": "candidate",
        "runtime_id": runtime_id,
        "status": "not_run",
        "reason": reason,
        "source": source,
        "trials": [],
        "promotion_authority": False,
        "superiority_claim": False,
    }
    value["receipt_digest"] = digest(value)
    return value


def qualification_digest(value: dict[str, Any]) -> str:
    material = dict(value)
    material.pop("qualification_digest", None)
    return digest(material)


def build_qualification(
    *,
    python_314: str,
    python_312: str,
    smoke_314: Path,
    smoke_312: Path,
    candidate_314: Path,
    candidate_312: Path,
    qualification_path: Path,
) -> dict[str, Any]:
    smokes = [
        json.loads(smoke_314.read_text(encoding="utf-8")),
        json.loads(smoke_312.read_text(encoding="utf-8")),
    ]
    smoke_passed = all(receipt_passes_smoke(item) for item in smokes)
    source = tracked_snapshot()
    qualification: dict[str, Any] = {
        "schema_version": 1,
        "kind": "git-commit-observation-qualification-v1",
        "source": source,
        "smoke_receipt_digests": [item["receipt_digest"] for item in smokes],
        "comparators": {
            "doctor_baseline": "evidence/performance/doctor-performance-v1/baseline-summary.json",
            "rejected_fixture_candidate": REJECTED_CANDIDATE,
        },
        "frozen_behavior_contract": {
            "total": VECTOR_TOTAL,
            "passed": VECTOR_PASSED,
            "skipped": VECTOR_SKIPPED,
            "conditional_skip_id": CONDITIONAL_SKIP_ID,
            "complete_unittest_id_set_sha256": VECTOR_DIGEST,
        },
        "promotion_authority": False,
        "superiority_claim": False,
        "knowledge_baseline_retry_authority": False,
    }
    if not smoke_passed:
        reason = "one or both fresh smoke trials did not pass below 180 seconds"
        first = not_run_receipt("python-3.14-system", reason, source)
        second = not_run_receipt("python-3.12-bundled", reason, source)
        write_json(candidate_314, first)
        write_json(candidate_312, second)
        qualification.update({
            "status": "smoke_gate_failed",
            "six_trial_qualification_executed": False,
            "post_performance_tests_executed": False,
            "candidate_receipt_digests": [first["receipt_digest"], second["receipt_digest"]],
            "unresolved_material_findings": [reason],
        })
    else:
        first = run_trials(python=python_314, runtime_id="python-3.14-system", phase="candidate", count=MINIMUM_QUALIFICATION_TRIALS)
        second = run_trials(python=python_312, runtime_id="python-3.12-bundled", phase="candidate", count=MINIMUM_QUALIFICATION_TRIALS)
        write_json(candidate_314, first)
        write_json(candidate_312, second)
        qualification["six_trial_qualification_executed"] = True
        qualification["candidate_receipt_digests"] = [first["receipt_digest"], second["receipt_digest"]]
        performance_passed = True
        performance_findings: list[str] = []
        for receipt in (first, second):
            try:
                verify_receipt(receipt, phase="candidate", require_qualification=True)
            except ValueError as error:
                performance_passed = False
                performance_findings.append(f"{receipt['runtime_id']}: {error}")
        if not performance_passed:
            qualification.update({
                "status": "performance_gate_failed",
                "post_performance_tests_executed": False,
                "unresolved_material_findings": performance_findings,
            })
        else:
            vector = discover_vector(python_314)
            focused, _ = run_command((python_314, "-m", "unittest", "tests.test_doctor_git_fact_batching", "-v"))
            autopilot, autopilot_output = run_command((python_314, "-m", "unittest", "discover", "-s", ".autopilot/tests", "-v"))
            repository, _ = run_command((python_314, "-m", "unittest", "discover", "-s", "tests", "-v"))
            ran_match = re.search(r"Ran (\d+) tests", autopilot_output)
            autopilot["observed_total"] = int(ran_match.group(1)) if ran_match else None
            autopilot["observed_one_skip"] = "skipped=1" in autopilot_output
            gates_passed = all((
                vector["matches_frozen"],
                focused["passed"],
                autopilot["passed"],
                autopilot["observed_total"] == VECTOR_TOTAL,
                autopilot["observed_one_skip"],
                repository["passed"],
            ))
            qualification.update({
                "status": "passed" if gates_passed else "behavior_or_ci_gate_failed",
                "post_performance_tests_executed": True,
                "behavior_vector": vector,
                "validation": {
                    "focused_adversarial": focused,
                    "full_autopilot": autopilot,
                    "full_repository_ci": repository,
                },
                "unresolved_material_findings": [] if gates_passed else ["behavior vector, focused tests, or full CI failed"],
            })
    qualification["qualification_digest"] = qualification_digest(qualification)
    write_json(qualification_path, qualification)
    return qualification


def verify_program(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("qualification_digest") != qualification_digest(value):
        raise ValueError("qualification digest mismatch")
    if value.get("promotion_authority") is not False or value.get("superiority_claim") is not False:
        raise ValueError("qualification claimed authority")
    status = value.get("status")
    if status == "smoke_gate_failed":
        if value.get("six_trial_qualification_executed") is not False:
            raise ValueError("failed smoke did not stop qualification")
    elif status == "passed":
        if value.get("six_trial_qualification_executed") is not True:
            raise ValueError("passing qualification lacks six-trial matrix")
        if value.get("post_performance_tests_executed") is not True:
            raise ValueError("passing qualification lacks post-performance tests")
        if value.get("behavior_vector", {}).get("matches_frozen") is not True:
            raise ValueError("passing qualification lacks frozen behavior vector")
        if value.get("unresolved_material_findings") != []:
            raise ValueError("passing qualification has unresolved findings")
    elif status not in {"performance_gate_failed", "behavior_or_ci_gate_failed"}:
        raise ValueError("unknown qualification status")
    return value


def self_test() -> None:
    if trial_modes(6) != ["cold", "warm", "cold", "warm", "cold", "warm"]:
        raise AssertionError("mode schedule is not deterministic")
    if nearest_rank_p95([1, 2, 3, 4, 5, 6]) != 6:
        raise AssertionError("nearest-rank p95 changed")
    if phase_modes("smoke", 1) != ["smoke"] or phase_modes("baseline-diagnostic", 1) != ["diagnostic"]:
        raise AssertionError("single-trial policies changed")
    sample: dict[str, Any] = {
        "phase": "candidate",
        "command": [sys.executable, *EXACT_DOCTOR_SUFFIX],
        "doctor_internal_timeout_seconds": DOCTOR_TIMEOUT_SECONDS,
        "trials": [
            {"mode": mode, "fresh_process": True, "elapsed_seconds": 100 + index, "doctor_passed": True}
            for index, mode in enumerate(trial_modes(6))
        ],
        "metrics": {"nearest_rank_p95_seconds": 105.0},
        "frozen_behavior_contract": {"total": VECTOR_TOTAL, "complete_unittest_id_set_sha256": VECTOR_DIGEST},
    }
    sample["receipt_digest"] = digest(sample)
    verify_receipt(sample, phase="candidate", require_qualification=True)
    bad_smoke = dict(sample)
    bad_smoke.update({
        "phase": "smoke",
        "trials": [{"mode": "smoke", "fresh_process": True, "elapsed_seconds": 181.0, "doctor_passed": False}],
        "metrics": {"nearest_rank_p95_seconds": 181.0},
    })
    bad_smoke["receipt_digest"] = digest({key: value for key, value in bad_smoke.items() if key != "receipt_digest"})
    if receipt_passes_smoke(bad_smoke):
        raise AssertionError("failed smoke did not stop")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("self-test")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--python", required=True)
    run_parser.add_argument("--runtime-id", required=True)
    run_parser.add_argument("--phase", choices=("baseline-diagnostic", "smoke", "candidate"), required=True)
    run_parser.add_argument("--trials", type=int, required=True)
    run_parser.add_argument("--output", required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--receipt", required=True)
    verify_parser.add_argument("--phase", choices=("baseline-diagnostic", "smoke", "candidate"), required=True)
    verify_parser.add_argument("--qualification", action="store_true")
    qualify_parser = subparsers.add_parser("qualify")
    qualify_parser.add_argument("--python-3-14", required=True)
    qualify_parser.add_argument("--python-3-12", required=True)
    qualify_parser.add_argument("--smoke-3-14", required=True)
    qualify_parser.add_argument("--smoke-3-12", required=True)
    qualify_parser.add_argument("--candidate-3-14", required=True)
    qualify_parser.add_argument("--candidate-3-12", required=True)
    qualify_parser.add_argument("--qualification", required=True)
    verify_program_parser = subparsers.add_parser("verify-program")
    verify_program_parser.add_argument("--qualification", required=True)
    args = parser.parse_args()
    if args.command == "self-test":
        self_test()
        print(json.dumps({"self_test": "passed"}, sort_keys=True))
        return 0
    if args.command == "run":
        receipt = run_trials(python=args.python, runtime_id=args.runtime_id, phase=args.phase, count=args.trials)
        output = Path(args.output)
        write_json(output, receipt)
        print(json.dumps({"receipt": str(output), "digest": receipt["receipt_digest"]}, sort_keys=True))
        return 0
    if args.command == "verify":
        receipt = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
        verify_receipt(receipt, phase=args.phase, require_qualification=args.qualification)
        print(json.dumps({"verified": True, "receipt": args.receipt}, sort_keys=True))
        return 0
    if args.command == "qualify":
        result = build_qualification(
            python_314=args.python_3_14,
            python_312=args.python_3_12,
            smoke_314=Path(args.smoke_3_14),
            smoke_312=Path(args.smoke_3_12),
            candidate_314=Path(args.candidate_3_14),
            candidate_312=Path(args.candidate_3_12),
            qualification_path=Path(args.qualification),
        )
        print(json.dumps({"qualification": args.qualification, "status": result["status"], "digest": result["qualification_digest"]}, sort_keys=True))
        return 0
    result = verify_program(Path(args.qualification))
    print(json.dumps({"verified": True, "qualification": args.qualification, "status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({"verified": False, "error": str(error)}, sort_keys=True))
        raise SystemExit(2) from None
