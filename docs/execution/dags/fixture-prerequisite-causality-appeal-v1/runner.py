#!/usr/bin/env python3
"""Hermetic receipt utility for the no-code fixture causality appeal.

It deliberately has no implementation path.  The execute subcommand is the one
sealed FPC-EXECUTE-020 operation: it creates a fresh venv, installs the checked
out source, runs exactly one root CI command, and persists a digest-bound JSON
transcript.  It neither retries nor mutates repository code.
"""
from __future__ import annotations
import argparse, hashlib, json, os, platform, subprocess, sys, tempfile, time
from pathlib import Path
from specs import BASELINE_COMMIT, BASELINE_TREE, DISCOVERY_COUNT, DISCOVERY_DIGEST, ROOT_CI, RUNNER_TIMEOUT_SECONDS
ROOT = Path(__file__).resolve().parents[4]
def canonical(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
def digest(value): return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()
def finalize(receipt):
    data = dict(receipt); data.pop("receipt_digest", None); data["receipt_digest"] = digest(data); return data
def write_receipt(path, receipt):
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True); target.write_text(json.dumps(finalize(receipt), sort_keys=True, indent=2) + "\n", encoding="utf-8")
def verify(receipt, phase):
    got = receipt.get("receipt_digest"); body = dict(receipt); body.pop("receipt_digest", None)
    if got != digest(body): raise ValueError("receipt digest mismatch")
    if receipt.get("phase") != phase: raise ValueError("receipt phase mismatch")
    if receipt.get("baseline") != {"commit": BASELINE_COMMIT, "tree": BASELINE_TREE}: raise ValueError("baseline identity mismatch")
    if phase == "discovery":
        discovery = receipt.get("discovery", {})
        if discovery.get("tests_discovered") != DISCOVERY_COUNT or discovery.get("test_id_digest") != DISCOVERY_DIGEST: raise ValueError("discovery identity mismatch")
    if phase == "execution":
        env = receipt.get("environment", {})
        if env.get("PYTHONNOUSERSITE") != "1" or env.get("PYTHONPATH") is not None: raise ValueError("non-hermetic environment")
        if receipt.get("execution", {}).get("timeout_seconds") != RUNNER_TIMEOUT_SECONDS: raise ValueError("wrong execution timeout")
        if receipt.get("execution", {}).get("attempts") != 1: raise ValueError("execution must be exactly one attempt")
        if not receipt.get("transcript_digest"): raise ValueError("durable transcript is missing")
    if phase in {"cross", "integration"} and not receipt.get("conclusion"): raise ValueError("missing conclusion")
def discover_ids():
    import unittest
    loader = unittest.defaultTestLoader; suite = loader.discover(str(ROOT / "tests"))
    ids = []
    def walk(node):
        if isinstance(node, unittest.TestSuite):
            for item in node: walk(item)
        else: ids.append(node.id())
    walk(suite); return ids
def discovery_receipt():
    ids = discover_ids(); result = {"schema_version": 1, "kind": "fpc-discovery-v1", "phase": "discovery", "baseline": {"commit": BASELINE_COMMIT, "tree": BASELINE_TREE}, "discovery": {"tests_discovered": len(ids), "test_id_digest": "sha256:" + hashlib.sha256("\n".join(ids).encode()).hexdigest(), "first_id": ids[0] if ids else None, "last_id": ids[-1] if ids else None}, "conclusion": "discovery-only; no causal authority"}; return finalize(result)
def execute(receipt_path, transcript_path):
    transcript = {"schema_version": 1, "command": ROOT_CI, "started_at_epoch": time.time(), "timeout_seconds": RUNNER_TIMEOUT_SECONDS, "attempts": 1, "note": "sealed no-code execution; implementation and retries forbidden"}
    with tempfile.TemporaryDirectory(prefix="fpc-execute-") as temp:
        venv = Path(temp) / "venv"; interpreter = venv / "Scripts" / "python.exe"
        clean = dict(os.environ); clean["PYTHONNOUSERSITE"] = "1"; clean.pop("PYTHONPATH", None)
        steps = [[sys.executable, "-E", "-s", "-m", "venv", str(venv)], [str(interpreter), "-E", "-s", "-m", "pip", "install", "--disable-pip-version-check", "--no-deps", "-e", "."]]
        transcript["setup"] = []
        for command in steps:
            run = subprocess.run(command, cwd=ROOT, env=clean, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=RUNNER_TIMEOUT_SECONDS)
            transcript["setup"].append({"command": command, "returncode": run.returncode, "output": run.stdout})
            if run.returncode: break
        else:
            command = [str(interpreter), "-E", "-s", "-m", "unittest", "discover", "-s", "tests", "-v"]
            try:
                run = subprocess.run(command, cwd=ROOT, env=clean, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=RUNNER_TIMEOUT_SECONDS)
                transcript["root_ci"] = {"command": command, "returncode": run.returncode, "output": run.stdout, "timed_out": False}
            except subprocess.TimeoutExpired as error:
                transcript["root_ci"] = {"command": command, "returncode": 124, "output": (error.stdout or ""), "timed_out": True}
    transcript["finished_at_epoch"] = time.time(); write_receipt(transcript_path, transcript)
    receipt = {"schema_version": 1, "kind": "fpc-execution-v1", "phase": "execution", "baseline": {"commit": BASELINE_COMMIT, "tree": BASELINE_TREE}, "environment": {"PYTHONNOUSERSITE": "1", "PYTHONPATH": None}, "execution": {"attempts": 1, "timeout_seconds": RUNNER_TIMEOUT_SECONDS, "command": ROOT_CI}, "transcript_digest": digest(json.loads(Path(transcript_path).read_text())), "conclusion": "execution evidence only; no implementation authority"}; write_receipt(receipt_path, receipt)
def self_test():
    good = {"schema_version": 1, "kind": "fpc-discovery-v1", "phase": "discovery", "baseline": {"commit": BASELINE_COMMIT, "tree": BASELINE_TREE}, "discovery": {"tests_discovered": DISCOVERY_COUNT, "test_id_digest": DISCOVERY_DIGEST}, "conclusion": "test"}; verify(finalize(good), "discovery")
    execute_like = {"schema_version": 1, "kind": "fpc-execution-v1", "phase": "execution", "baseline": {"commit": BASELINE_COMMIT, "tree": BASELINE_TREE}, "environment": {"PYTHONNOUSERSITE": "1", "PYTHONPATH": None}, "execution": {"attempts": 1, "timeout_seconds": RUNNER_TIMEOUT_SECONDS}, "transcript_digest": "sha256:test", "conclusion": "test"}; verify(finalize(execute_like), "execution")
def main():
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test"); discovery = sub.add_parser("discover"); discovery.add_argument("--receipt", required=True)
    verify_parser = sub.add_parser("verify"); verify_parser.add_argument("--receipt", required=True); verify_parser.add_argument("--phase", required=True)
    run = sub.add_parser("execute-once"); run.add_argument("--receipt", required=True); run.add_argument("--transcript", required=True)
    args = parser.parse_args()
    try:
        if args.command == "self-test": self_test(); print(json.dumps({"self_test": "passed"}))
        elif args.command == "discover": write_receipt(args.receipt, discovery_receipt()); print(json.dumps({"receipt": args.receipt}))
        elif args.command == "verify": verify(json.loads(Path(args.receipt).read_text()), args.phase); print(json.dumps({"verified": True, "receipt": args.receipt}))
        else: execute(args.receipt, args.transcript); print(json.dumps({"receipt": args.receipt, "transcript": args.transcript, "attempts": 1}))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(json.dumps({"verified": False, "error": str(error)})); return 2
if __name__ == "__main__": raise SystemExit(main())
