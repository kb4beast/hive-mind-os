#!/usr/bin/env python3
"""Fail-closed verifier for VTC's sealed, no-code court contract."""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
D=Path(__file__).resolve().parent; R=D.parents[3]; sys.path.insert(0,str(D))
from generate_plan import build_plan, digest
from specs import EVALUATED_COMMIT,EVALUATED_TREE,REJECTED_TUPLES
IDS=["VTC-SEAL-000","VTC-DISCOVERY-010","VTC-CROSS-020","VTC-INTEGRATE-030","VTC-JUDGE-040"]
DEPS={"VTC-SEAL-000":[],"VTC-DISCOVERY-010":["VTC-SEAL-000"],"VTC-CROSS-020":["VTC-SEAL-000"],"VTC-INTEGRATE-030":["VTC-DISCOVERY-010","VTC-CROSS-020"],"VTC-JUDGE-040":["VTC-INTEGRATE-030"]}
def run(*args): return subprocess.run(args,cwd=R,check=True,capture_output=True,text=True).stdout.strip()
def main():
 try:
  if run("git","rev-parse",f"{EVALUATED_COMMIT}^{{tree}}") != EVALUATED_TREE: raise ValueError("evaluated tree mismatch")
  if any((c,t)==(EVALUATED_COMMIT,EVALUATED_TREE) for c,t in REJECTED_TUPLES): raise ValueError("bad tuple normalized")
  plan=build_plan(); manifest=json.loads((D/"manifest.json").read_text())
  if manifest["baseline"]!={"commit":EVALUATED_COMMIT,"tree":EVALUATED_TREE} or manifest["rejected_tuples"]!=[{"commit":c,"tree":t} for c,t in REJECTED_TUPLES]: raise ValueError("baseline seal mismatch")
  if manifest["expected_node_ids"]!=IDS or manifest["expected_dependencies"]!=DEPS or manifest["expected_plan_digest"]!=plan["plan_digest"]: raise ValueError("graph seal mismatch")
  for item in plan["nodes"]:
   raw=dict(item); actual=raw.pop("contract_digest")
   if actual!=digest(raw) or item["dependencies"]!=DEPS[item["id"]]: raise ValueError("contract mismatch: "+item["id"])
  print(json.dumps({"verified":True,"plan_id":plan["plan_id"],"plan_digest":plan["plan_digest"],"node_count":len(plan["nodes"])})); return 0
 except (OSError,ValueError,KeyError,json.JSONDecodeError,subprocess.CalledProcessError) as error: print(json.dumps({"verified":False,"error":str(error)})); return 2
if __name__=="__main__": raise SystemExit(main())
