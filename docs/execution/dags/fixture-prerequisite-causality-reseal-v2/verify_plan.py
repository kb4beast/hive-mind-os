#!/usr/bin/env python3
"""Fail-closed verifier for the FPCR v2 seal."""
from __future__ import annotations
import hashlib, json, subprocess, sys
from pathlib import Path
D=Path(__file__).resolve().parent; R=D.parents[3]; sys.path.insert(0,str(D))
from generate_plan import build_plan, digest
from specs import EVALUATED_COMMIT, EVALUATED_TREE, REJECTED_TUPLES
IDS=["FPCR-SEAL-000","FPCR-DISCOVERY-010","FPCR-EXECUTE-020","FPCR-CROSS-030","FPCR-INTEGRATE-040","FPCR-JUDGE-050"]
DEPS={"FPCR-SEAL-000":[],"FPCR-DISCOVERY-010":["FPCR-SEAL-000"],"FPCR-EXECUTE-020":["FPCR-DISCOVERY-010"],"FPCR-CROSS-030":["FPCR-DISCOVERY-010"],"FPCR-INTEGRATE-040":["FPCR-EXECUTE-020","FPCR-CROSS-030"],"FPCR-JUDGE-050":["FPCR-INTEGRATE-040"]}
PATHS=["docs/execution/dags/fixture-prerequisite-causality-reseal-v2/.gitignore","docs/execution/dags/fixture-prerequisite-causality-reseal-v2/README.md","docs/execution/dags/fixture-prerequisite-causality-reseal-v2/generate_plan.py","docs/execution/dags/fixture-prerequisite-causality-reseal-v2/runner.py","docs/execution/dags/fixture-prerequisite-causality-reseal-v2/specs.py","docs/execution/dags/fixture-prerequisite-causality-reseal-v2/verify_plan.py","evidence/courts/CASE-FIXTURE-PREREQUISITE-CAUSALITY-RESEAL-DEFECT.json"]
def run(*args): return subprocess.run(args,cwd=R,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=True).stdout.strip()
def blob(path): return run("git","hash-object","--",path)
def main():
    try:
        tree=run("git","rev-parse",f"{EVALUATED_COMMIT}^{{tree}}")
        if tree != EVALUATED_TREE: raise ValueError("real evaluated tree mismatch")
        for commit,bad_tree in REJECTED_TUPLES:
            if (commit,bad_tree)==(EVALUATED_COMMIT,EVALUATED_TREE): raise ValueError("bad tuple normalized")
        manifest=json.loads((D/"manifest.json").read_text()); plan=build_plan()
        if manifest.get("baseline") != {"commit":EVALUATED_COMMIT,"tree":EVALUATED_TREE}: raise ValueError("manifest tuple mismatch")
        if manifest.get("rejected_tuples") != [{"commit":c,"tree":t} for c,t in REJECTED_TUPLES]: raise ValueError("rejected tuple seal mismatch")
        if manifest.get("expected_node_ids") != IDS or manifest.get("expected_dependencies") != DEPS or manifest.get("expected_plan_digest") != plan["plan_digest"]: raise ValueError("graph seal mismatch")
        for node in plan["nodes"]:
            raw=dict(node); actual=raw.pop("contract_digest",None)
            if actual != digest(raw) or node["dependencies"] != DEPS[node["id"]]: raise ValueError("node contract mismatch: "+node["id"])
        for path in PATHS:
            if blob(path) != manifest["sources"].get(path): raise ValueError("source mismatch: "+path)
        frozen="sha256:"+hashlib.sha256((R/".autopilot/plan.json").read_bytes()).hexdigest()
        if frozen != manifest["sealed_autopilot_plan_sha256"]: raise ValueError("sealed autopilot plan changed")
        print(json.dumps({"verified":True,"plan_id":plan["plan_id"],"plan_digest":plan["plan_digest"],"node_count":len(plan["nodes"])})); return 0
    except (OSError,ValueError,subprocess.CalledProcessError,json.JSONDecodeError) as error: print(json.dumps({"verified":False,"error":str(error)})); return 2
if __name__ == "__main__": raise SystemExit(main())
