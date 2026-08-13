#!/usr/bin/env python3
"""Reproducible doctor-performance receipt runner and verifier.

This script never edits controller behavior or test discovery. A run launches the
exact doctor command in a fresh process for each trial and writes one canonical JSON
receipt chosen by the caller. Environment values are intentionally not copied because
they may contain credentials; the receipt records the complete non-secret execution
surface needed for reproduction instead.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
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
MINIMUM_TRIALS = 6
DOCTOR_TIMEOUT_SECONDS = 180
QUALIFICATION_P95_SECONDS = 135.0


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
    if count < MINIMUM_TRIALS:
        raise ValueError(f"at least {MINIMUM_TRIALS} trials are required")
    return ["cold" if index % 2 == 0 else "warm" for index in range(count)]


def tracked_snapshot() -> dict[str, str]:
    entries = run_git("ls-files", "-s", "--", ".autopilot").splitlines()
    normalized = [line for line in entries if line and "/state/" not in line]
    return {
        "commit": run_git("rev-parse", "HEAD"),
        "tree": run_git("rev-parse", "HEAD^{tree}"),
        "index_tree": run_git("write-tree"),
        "autopilot_index_digest": digest(normalized),
        "autopilot_tracked_entry_count": str(len(normalized)),
    }


def execution_environment(python: str) -> dict[str, Any]:
    probe = subprocess.run(
        (python, "-c", "import json,platform,sys;print(json.dumps({'executable':sys.executable,'version':platform.python_version(),'implementation':platform.python_implementation()}))"),
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    runtime = json.loads(probe.stdout)
    return {
        "runtime": runtime,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "working_directory": str(ROOT),
        "network_policy": "no-network",
        "process_environment_values_retained": False,
        "process_environment_omission_reason": "credential-safety",
    }


def run_trials(*, python: str, runtime_id: str, phase: str, count: int) -> dict[str, Any]:
    modes = trial_modes(count)
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
                timeout=DOCTOR_TIMEOUT_SECONDS + 60,
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
        "kind": "doctor-performance-benchmark-receipt-v1",
        "phase": phase,
        "runtime_id": runtime_id,
        "command": command,
        "doctor_internal_timeout_seconds": DOCTOR_TIMEOUT_SECONDS,
        "trial_policy": {
            "minimum_trials": MINIMUM_TRIALS,
            "actual_trials": count,
            "alternation": "cold-first-then-warm",
            "cold_trials": modes.count("cold"),
            "fresh_process_every_trial": True,
            "cold_warm_is_declared_not_an_os-cache-eviction-claim": True,
        },
        "source": tracked_snapshot(),
        "environment": execution_environment(python),
        "trials": trials,
        "metrics": {
            "nearest_rank_p95_seconds": nearest_rank_p95(durations),
            "all_below_doctor_timeout": all(value < DOCTOR_TIMEOUT_SECONDS for value in durations),
            "all_doctor_passed": all(bool(item["doctor_passed"]) for item in trials),
            "qualification_limit_seconds": QUALIFICATION_P95_SECONDS,
        },
    }
    receipt["receipt_digest"] = digest(receipt)
    return receipt


def verify_receipt(receipt: dict[str, Any], *, require_qualification: bool) -> None:
    supplied = receipt.get("receipt_digest")
    material = dict(receipt)
    material.pop("receipt_digest", None)
    if supplied != digest(material):
        raise ValueError("receipt digest mismatch")
    command = receipt.get("command")
    if not isinstance(command, list) or tuple(command[1:]) != EXACT_DOCTOR_SUFFIX:
        raise ValueError("doctor command changed")
    trials = receipt.get("trials")
    if not isinstance(trials, list) or len(trials) < MINIMUM_TRIALS:
        raise ValueError("insufficient trials")
    expected_modes = trial_modes(len(trials))
    if [item.get("mode") for item in trials] != expected_modes:
        raise ValueError("trial modes are not cold-first alternating")
    if not all(item.get("fresh_process") is True for item in trials):
        raise ValueError("every trial must use a fresh process")
    durations = [float(item["elapsed_seconds"]) for item in trials]
    observed = float(receipt["metrics"]["nearest_rank_p95_seconds"])
    if observed != nearest_rank_p95(durations):
        raise ValueError("nearest-rank p95 mismatch")
    if require_qualification:
        if not all(bool(item.get("doctor_passed")) for item in trials):
            raise ValueError("candidate doctor trial failed")
        if not all(value < DOCTOR_TIMEOUT_SECONDS for value in durations):
            raise ValueError("candidate doctor trial reached timeout")
        if observed > QUALIFICATION_P95_SECONDS:
            raise ValueError("candidate p95 exceeds qualification limit")


def self_test() -> None:
    if trial_modes(6) != ["cold", "warm", "cold", "warm", "cold", "warm"]:
        raise AssertionError("mode schedule is not deterministic")
    if nearest_rank_p95([1, 2, 3, 4, 5, 6]) != 6:
        raise AssertionError("nearest-rank p95 implementation changed")
    sample: dict[str, Any] = {
        "command": [sys.executable, *EXACT_DOCTOR_SUFFIX],
        "trials": [
            {"mode": mode, "fresh_process": True, "elapsed_seconds": 100 + index, "doctor_passed": True}
            for index, mode in enumerate(trial_modes(6))
        ],
        "metrics": {"nearest_rank_p95_seconds": 105.0},
    }
    sample["receipt_digest"] = digest(sample)
    verify_receipt(sample, require_qualification=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("self-test")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--python", required=True)
    run_parser.add_argument("--runtime-id", required=True)
    run_parser.add_argument("--phase", choices=("baseline", "candidate"), required=True)
    run_parser.add_argument("--trials", type=int, default=MINIMUM_TRIALS)
    run_parser.add_argument("--output", required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--receipt", required=True)
    verify_parser.add_argument("--qualification", action="store_true")
    args = parser.parse_args()
    if args.command == "self-test":
        self_test()
        print(json.dumps({"self_test": "passed"}, sort_keys=True))
        return 0
    if args.command == "run":
        receipt = run_trials(
            python=args.python,
            runtime_id=args.runtime_id,
            phase=args.phase,
            count=args.trials,
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"receipt": str(output), "digest": receipt["receipt_digest"]}, sort_keys=True))
        return 0
    receipt = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
    verify_receipt(receipt, require_qualification=args.qualification)
    print(json.dumps({"verified": True, "receipt": args.receipt}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
