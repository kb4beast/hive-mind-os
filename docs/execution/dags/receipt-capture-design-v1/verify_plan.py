#!/usr/bin/env python3
"""Fail-closed verifier for the sealed receipt-capture design court."""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
D = Path(__file__).resolve().parent; R = D.parents[3]; sys.path.insert(0, str(D))
from generate_plan import build_plan, digest
from specs import AUTHORITY_COMMIT, AUTHORITY_TREE, DESIGN_REQUIREMENTS
IDS = ["RCD-SEAL-000", "RCD-ARCH-010", "RCD-CROSS-020", "RCD-INTEGRATE-030", "RCD-JUDGE-040"]
DEPS = {"RCD-SEAL-000": [], "RCD-ARCH-010": ["RCD-SEAL-000"], "RCD-CROSS-020": ["RCD-SEAL-000"], "RCD-INTEGRATE-030": ["RCD-ARCH-010", "RCD-CROSS-020"], "RCD-JUDGE-040": ["RCD-INTEGRATE-030"]}
def run(*args): return subprocess.run(args, cwd=R, check=True, capture_output=True, text=True).stdout.strip()
def main():
    try:
        if run("git", "rev-parse", f"{AUTHORITY_COMMIT}^{{tree}}") != AUTHORITY_TREE: raise ValueError("authority tree mismatch")
        plan = build_plan(); manifest = json.loads((D / "manifest.json").read_text())
        if manifest["authority"] != {"commit": AUTHORITY_COMMIT, "tree": AUTHORITY_TREE}: raise ValueError("authority seal mismatch")
        if manifest["expected_node_ids"] != IDS or manifest["expected_dependencies"] != DEPS: raise ValueError("graph seal mismatch")
        if manifest["expected_plan_digest"] != plan["plan_digest"] or manifest["required_design_elements"] != DESIGN_REQUIREMENTS: raise ValueError("digest or design requirements mismatch")
        if manifest["lint_warning_justification"] != plan["lint_warning_justifications"]: raise ValueError("lint-warning justification mismatch")
        for item in plan["nodes"]:
            raw = dict(item); actual = raw.pop("contract_digest")
            if actual != digest(raw) or item["dependencies"] != DEPS[item["id"]]: raise ValueError("contract mismatch: " + item["id"])
        print(json.dumps({"verified": True, "plan_id": plan["plan_id"], "plan_digest": plan["plan_digest"], "node_count": len(plan["nodes"])})); return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(json.dumps({"verified": False, "error": str(error)})); return 2
if __name__ == "__main__": raise SystemExit(main())
