#!/usr/bin/env python3
"""Deterministically materialize the sealed fixture-prerequisite DAG."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from typing import Any
from specs import SPECS, BASELINE_COMMIT, BASELINE_TREE, REJECTED_FIXTURE_COMMIT, REJECTED_FIXTURE_TREE, GCO_CANDIDATE_COMMIT, FIXTURE_FAILURE, FROZEN_VECTOR

DAG_DIR="docs/execution/dags/fixture-prerequisite-v1"
OUTPUT_PATH=".autopilot/state/fixture-prerequisite-v1.json"
COMMON_FORBIDDEN=[".autopilot/plan.json", ".autopilot/control-plane.json", ".autopilot/bin/controller.py", ".autopilot/bin/durable_controller.py", ".autopilot/bin/sealed_recovery.py", ".autopilot/bin/release_barrier.py", ".autopilot/tests/test_healing.py", "src/**", "refs/heads/main", "refs/remotes/origin/**", "docs/execution/dags/git-commit-observation-v1/**", "tests/test_doctor_git_fact_batching.py", "docs/execution/dags/doctor-performance-v1/**", "evidence/performance/doctor-performance-v1/**", "evidence/courts/CASE-DOCTOR-PERFORMANCE-PROMOTION.json"]
def digest(value: object)->str:
 return "sha256:"+hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
def build_plan()->dict[str,Any]:
 writes={x["id"]:x["write_scope"] for x in SPECS}; nodes=[]
 for spec in SPECS:
  item=dict(spec); other=sorted({p for n,paths in writes.items() if n!=item["id"] for p in paths})
  item["forbidden_scope"]=list(dict.fromkeys([*COMMON_FORBIDDEN,*other])); item["file_locks"]=list(item["write_scope"]); item["downstream_unlock_value"]=item["critical_path_importance"]; item["contract_digest"]=digest(item); nodes.append(item)
 plan={"schema_version":1,"kind":"hive-mind-fixture-prerequisite-plan-v1","plan_id":"fixture-prerequisite-v1","title":"Hermetic ephemeral fixture root-CI prerequisite","baseline":{"commit":BASELINE_COMMIT,"tree":BASELINE_TREE,"rejected_fixture_commit":REJECTED_FIXTURE_COMMIT,"rejected_fixture_tree":REJECTED_FIXTURE_TREE,"gco_candidate_commit":GCO_CANDIDATE_COMMIT},"source":{"directory":DAG_DIR,"opening_court":"evidence/courts/CASE-FIXTURE-PREREQUISITE-OPENING.json"},"current_state":{"implementation":"not_started","authority":"root-CI-fixture-prerequisite-only","gco_promotion":"forbidden","performance_claim":"forbidden","knowledge_baseline_retry":"forbidden"},"execution":{"max_sessions":4,"generate":f"python {DAG_DIR}/generate_plan.py --output {OUTPUT_PATH}","lint":f"python .autopilot/bin/autopilot.py --repo-root . dag-lint --plan {OUTPUT_PATH} --strict --json","rounds":f"python .autopilot/bin/autopilot.py --repo-root . dag-rounds --plan {OUTPUT_PATH} --max-sessions 4 --actor codex:fixture-prerequisite --json","rules":["workers use isolated branches and one retained unsquashed commit","only FPP-CAUSALITY-010 and FPP-TEST-020 may run in parallel","no main, remote, protected plan, production source, existing GCO artifact, or doctor evidence mutation"]},"invariants":["Hermetic root CI uses a fresh editable-install venv, PYTHONNOUSERSITE=1, cleared PYTHONPATH, -E -s, and import resolution from repository src/hive_mind_os.","Baseline predicate is exactly 1050 tests, 1 failure, 8 skips, with sole failure "+FIXTURE_FAILURE+" caused by absent ContentAddressedFixtureSeed, FixtureIntegrityError, and FixturePolicyError.","Fixture support is ephemeral, content-verified, network-free, cleanup-safe, cross-worktree isolated, and rejects tamper/torn seeds, symlink/junction/hardlink/shared/alternate/promisor object stores.","No persistent mutable seed/result/verdict/fixture cache, daemon, shared objects, --shared clone, ambient HEAD/branch/remote authority, or reuse/relabel/cherry-pick/byte reuse of rejected fixture candidate is allowed.","The frozen .autopilot doctor vector "+FROZEN_VECTOR+", timeout, p95 burden, GCO status, performance evidence, and knowledge BASELINE retry authority remain unchanged.","Only a distinct FPP-JUDGE-070 verdict may clear the fixture root-CI prerequisite; it cannot authorize GCO promotion or any broader result."],"nodes":nodes}
 plan["plan_digest"]=digest(plan); return plan
def render(plan:dict[str,Any])->bytes:return (json.dumps(plan,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n").encode()
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--output",default=OUTPUT_PATH);p.add_argument("--stdout",action="store_true");a=p.parse_args();plan=build_plan()
 if a.stdout: print(render(plan).decode(),end="")
 else:
  out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(render(plan));print(json.dumps({"output":str(out),"plan_id":plan["plan_id"],"plan_digest":plan["plan_digest"],"nodes":len(plan["nodes"])},sort_keys=True))
 return 0
if __name__=="__main__":raise SystemExit(main())
