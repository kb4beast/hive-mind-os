#!/usr/bin/env python3
"""Fail-closed verifier for the sealed VPR contract and parser adversaries."""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
D=Path(__file__).resolve().parent; R=D.parents[3]; sys.path.insert(0,str(D))
from generate_plan import build_plan, digest
from specs import EVALUATED_COMMIT,EVALUATED_TREE,REJECTED_TUPLES,LedgerParseError,parse_outcome_ledger
IDS=["VPR-SEAL-000","VPR-LEDGER-010","VPR-CROSS-020","VPR-INTEGRATE-030","VPR-JUDGE-040"]
DEPS={"VPR-SEAL-000":[],"VPR-LEDGER-010":["VPR-SEAL-000"],"VPR-CROSS-020":["VPR-SEAL-000"],"VPR-INTEGRATE-030":["VPR-LEDGER-010","VPR-CROSS-020"],"VPR-JUDGE-040":["VPR-INTEGRATE-030"]}
def run(*args): return subprocess.run(args,cwd=R,check=True,capture_output=True,text=True).stdout.strip()
def parser_contract():
    ids=["pkg.Case.test_a","pkg.Case.test_b"]
    good=parse_outcome_ledger(["test a (pkg.Case.test_a) ... ok","test b (pkg.Case.test_b) ...","WARNING: buffered diagnostic","custom_retry"],ids,["custom_retry"])
    if good["outcomes"]!={ids[0]:"ok",ids[1]:"custom_retry"}: raise ValueError("parser acceptance mismatch")
    cases=[["test a (pkg.Case.test_a) ... ok"],["test a (pkg.Case.test_a) ... unknown","test b (pkg.Case.test_b) ... ok"],["test a (pkg.Case.test_a) ...","test b (pkg.Case.test_b) ... ok"],["test a (pkg.Case.test_a) ... ok","test a (pkg.Case.test_a) ... ok","test b (pkg.Case.test_b) ... ok"],["test z (pkg.Case.test_z) ... ok","test a (pkg.Case.test_a) ... ok","test b (pkg.Case.test_b) ... ok"]]
    for lines in cases:
        try: parse_outcome_ledger(lines,ids,["custom_retry"])
        except LedgerParseError: continue
        raise ValueError("parser accepted adversarial case")
def main():
 try:
  if run("git","rev-parse",f"{EVALUATED_COMMIT}^{{tree}}") != EVALUATED_TREE: raise ValueError("evaluated tree mismatch")
  if any((c,t)==(EVALUATED_COMMIT,EVALUATED_TREE) for c,t in REJECTED_TUPLES): raise ValueError("bad tuple normalized")
  parser_contract(); plan=build_plan(); manifest=json.loads((D/"manifest.json").read_text())
  if manifest["baseline"]!={"commit":EVALUATED_COMMIT,"tree":EVALUATED_TREE} or manifest["rejected_tuples"] != [{"commit":c,"tree":t} for c,t in REJECTED_TUPLES]: raise ValueError("baseline seal mismatch")
  if manifest["expected_node_ids"]!=IDS or manifest["expected_dependencies"]!=DEPS or manifest["expected_plan_digest"]!=plan["plan_digest"]: raise ValueError("graph seal mismatch")
  for item in plan["nodes"]:
   raw=dict(item); actual=raw.pop("contract_digest")
   if actual!=digest(raw) or item["dependencies"]!=DEPS[item["id"]]: raise ValueError("contract mismatch: "+item["id"])
  print(json.dumps({"verified":True,"plan_id":plan["plan_id"],"plan_digest":plan["plan_digest"],"node_count":len(plan["nodes"]),"parser_adversarial_cases":5})); return 0
 except (OSError,ValueError,KeyError,json.JSONDecodeError,subprocess.CalledProcessError) as error: print(json.dumps({"verified":False,"error":str(error)})); return 2
if __name__=="__main__": raise SystemExit(main())
