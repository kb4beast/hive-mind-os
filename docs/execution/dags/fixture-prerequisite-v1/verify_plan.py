#!/usr/bin/env python3
"""Fail-closed verifier for fixture-prerequisite-v1."""
from __future__ import annotations
import hashlib,json,subprocess,sys
from pathlib import Path
D=Path(__file__).resolve().parent;R=D.parents[3];sys.path.insert(0,str(D))
from generate_plan import build_plan,digest,OUTPUT_PATH,render
IDS=["FPP-SEAL-000","FPP-CAUSALITY-010","FPP-TEST-020","FPP-ARCH-030","FPP-BUILD-040","FPP-CURATE-050","FPP-INTEGRATE-060","FPP-JUDGE-070"]
DEPS={"FPP-SEAL-000":[],"FPP-CAUSALITY-010":["FPP-SEAL-000"],"FPP-TEST-020":["FPP-SEAL-000"],"FPP-ARCH-030":["FPP-CAUSALITY-010","FPP-TEST-020"],"FPP-BUILD-040":["FPP-ARCH-030","FPP-TEST-020"],"FPP-CURATE-050":["FPP-BUILD-040"],"FPP-INTEGRATE-060":["FPP-CAUSALITY-010","FPP-BUILD-040","FPP-CURATE-050"],"FPP-JUDGE-070":["FPP-INTEGRATE-060"]}
PATHS=["docs/execution/dags/fixture-prerequisite-v1/.gitignore","docs/execution/dags/fixture-prerequisite-v1/README.md","docs/execution/dags/fixture-prerequisite-v1/benchmark.py","docs/execution/dags/fixture-prerequisite-v1/generate_plan.py","docs/execution/dags/fixture-prerequisite-v1/specs.py","docs/execution/dags/fixture-prerequisite-v1/verify_plan.py","evidence/courts/CASE-FIXTURE-PREREQUISITE-OPENING.json"]
def blob(x):return subprocess.run(("git","hash-object","--",str(x)),cwd=R,stdout=subprocess.PIPE,text=True,check=True).stdout.strip()
def main():
 try:
  m=json.loads((D/"manifest.json").read_text());plan=build_plan()
  if m.get("expected_node_ids")!=IDS or m.get("expected_dependencies")!=DEPS:raise ValueError("manifest graph mismatch")
  if plan["plan_digest"]!=m.get("expected_plan_digest") or [x["id"] for x in plan["nodes"]]!=IDS:raise ValueError("plan seal mismatch")
  for x in plan["nodes"]:
   y=dict(x);got=y.pop("contract_digest",None)
   if got!=digest(y) or x["dependencies"]!=DEPS[x["id"]]:raise ValueError("node contract mismatch: "+x["id"])
  for p in PATHS:
   if blob(R/p)!=m["sources"].get(p):raise ValueError("source mismatch: "+p)
  if "sha256:"+hashlib.sha256((R/".autopilot/plan.json").read_bytes()).hexdigest()!=m["sealed_plan_sha256"]:raise ValueError("sealed autopilot plan changed")
  print(json.dumps({"verified":True,"plan_id":plan["plan_id"],"plan_digest":plan["plan_digest"],"node_count":len(plan["nodes"])}));return 0
 except (OSError,ValueError,subprocess.CalledProcessError,json.JSONDecodeError) as e:print(json.dumps({"verified":False,"error":str(e)}));return 2
if __name__=="__main__":raise SystemExit(main())
