#!/usr/bin/env python3
"""Fail-closed verifier for the FPC no-code appeal seal."""
from __future__ import annotations
import hashlib, json, subprocess, sys
from pathlib import Path
D = Path(__file__).resolve().parent; R = D.parents[3]; sys.path.insert(0, str(D))
from generate_plan import build_plan, digest
IDS = ["FPC-SEAL-000", "FPC-DISCOVERY-010", "FPC-EXECUTE-020", "FPC-CROSS-030", "FPC-INTEGRATE-040", "FPC-JUDGE-050"]
DEPS = {"FPC-SEAL-000": [], "FPC-DISCOVERY-010": ["FPC-SEAL-000"], "FPC-EXECUTE-020": ["FPC-SEAL-000", "FPC-DISCOVERY-010"], "FPC-CROSS-030": ["FPC-SEAL-000", "FPC-DISCOVERY-010"], "FPC-INTEGRATE-040": ["FPC-EXECUTE-020", "FPC-CROSS-030"], "FPC-JUDGE-050": ["FPC-INTEGRATE-040"]}
PATHS = ["docs/execution/dags/fixture-prerequisite-causality-appeal-v1/.gitignore", "docs/execution/dags/fixture-prerequisite-causality-appeal-v1/README.md", "docs/execution/dags/fixture-prerequisite-causality-appeal-v1/generate_plan.py", "docs/execution/dags/fixture-prerequisite-causality-appeal-v1/runner.py", "docs/execution/dags/fixture-prerequisite-causality-appeal-v1/specs.py", "docs/execution/dags/fixture-prerequisite-causality-appeal-v1/verify_plan.py", "evidence/courts/CASE-FIXTURE-PREREQUISITE-CAUSALITY-APPEAL-OPENING.json"]
def blob(path: str) -> str:
    return subprocess.run(("git", "hash-object", "--", path), cwd=R, stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
def main() -> int:
    try:
        manifest = json.loads((D / "manifest.json").read_text()); plan = build_plan()
        if manifest.get("expected_node_ids") != IDS or manifest.get("expected_dependencies") != DEPS: raise ValueError("manifest graph mismatch")
        if manifest.get("expected_plan_digest") != plan["plan_digest"] or [x["id"] for x in plan["nodes"]] != IDS: raise ValueError("plan seal mismatch")
        for node in plan["nodes"]:
            raw = dict(node); actual = raw.pop("contract_digest", None)
            if actual != digest(raw) or node["dependencies"] != DEPS[node["id"]]: raise ValueError("node contract mismatch: " + node["id"])
        for path in PATHS:
            if blob(path) != manifest["sources"].get(path): raise ValueError("source mismatch: " + path)
        got = "sha256:" + hashlib.sha256((R / ".autopilot/plan.json").read_bytes()).hexdigest()
        if got != manifest["sealed_autopilot_plan_sha256"]: raise ValueError("sealed autopilot plan changed")
        print(json.dumps({"verified": True, "plan_id": plan["plan_id"], "plan_digest": plan["plan_digest"], "node_count": len(plan["nodes"])})); return 0
    except (OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(json.dumps({"verified": False, "error": str(error)})); return 2
if __name__ == "__main__": raise SystemExit(main())
