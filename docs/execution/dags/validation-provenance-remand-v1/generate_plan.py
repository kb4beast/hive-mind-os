#!/usr/bin/env python3
"""Deterministically materialize the VPR evidence-only DAG."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from specs import SPECS, DAG_DIR, EVALUATED_COMMIT, EVALUATED_TREE, REJECTED_TUPLES, COMMON_FORBIDDEN, OPENING
OUTPUT = ".autopilot/state/validation-provenance-remand-v1.json"
def digest(value): return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
def build_plan():
    writes={item["id"]:item["write_scope"] for item in SPECS}; nodes=[]
    for item in SPECS:
        value=dict(item); other=sorted({path for ident, paths in writes.items() if ident != value["id"] for path in paths})
        value["forbidden_scope"]=list(dict.fromkeys([*COMMON_FORBIDDEN,*other])); value["file_locks"]=list(value["write_scope"]); value["downstream_unlock_value"]=value["critical_path_importance"]; value["contract_digest"]=digest(value); nodes.append(value)
    result={"schema_version":1,"kind":"hive-mind-validation-provenance-remand-v1","plan_id":"validation-provenance-remand-v1","title":"Validation provenance remand (evidence only)","baseline":{"commit":EVALUATED_COMMIT,"tree":EVALUATED_TREE,"rejected_tuples":[{"commit":c,"tree":t} for c,t in REJECTED_TUPLES]},"source":{"directory":DAG_DIR,"opening_court":OPENING},"current_state":{"implementation":"forbidden","candidate":"forbidden","ci_rerun":"forbidden","promotion":"forbidden","baseline_retry":"forbidden","main_and_remote":"forbidden"},"execution":{"max_sessions":4,"lint":f"python .autopilot/bin/autopilot.py --repo-root . dag-lint --plan {OUTPUT} --strict --json","rounds":f"python .autopilot/bin/autopilot.py --repo-root . dag-rounds --plan {OUTPUT} --max-sessions 4 --actor codex:vpr --json","rules":["VPR-LEDGER-010 and VPR-CROSS-020 may run in parallel after VPR-SEAL-000","no CI, unittest discovery, candidate execution, source/test/plan mutation, main, or remote effect","41950 and d02 may not be reused, relabeled, qualified, or composed","a successful ledger reduces provenance uncertainty only"]},"invariants":[f"Only {EVALUATED_COMMIT}/{EVALUATED_TREE} is observed.","Every discovery ID must bind exactly once or the ledger fails closed.","Warnings may interleave; custom labels require explicit declaration.","No VPR result grants implementation, candidate, promotion, performance, CI, or baseline-retry authority."],"nodes":nodes}; result["plan_digest"]=digest(result); return result
def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--output",default=OUTPUT); parser.add_argument("--stdout",action="store_true"); args=parser.parse_args(); text=json.dumps(build_plan(),sort_keys=True,indent=2)+"\n"
    if args.stdout: print(text,end="")
    else: path=Path(args.output); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(text); print(json.dumps({"output":str(path),"plan_digest":build_plan()["plan_digest"],"nodes":5},sort_keys=True))
if __name__ == "__main__": main()
