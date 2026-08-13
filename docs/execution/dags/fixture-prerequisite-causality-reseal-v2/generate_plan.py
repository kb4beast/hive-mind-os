#!/usr/bin/env python3
"""Deterministically materialize the FPCR v2 no-code DAG."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from typing import Any
from specs import SPECS, DAG_DIR, OPENING, EVALUATED_COMMIT, EVALUATED_TREE, REJECTED_TUPLES, CLAIMED_DISCOVERY_COUNT, FROZEN_AUTOPILOT_PLAN, RUNNER_TIMEOUT_SECONDS

OUTPUT_PATH = ".autopilot/state/fixture-prerequisite-causality-reseal-v2.json"
COMMON_FORBIDDEN = [".autopilot/plan.json", ".autopilot/control-plane.json", ".autopilot/bin/**", ".autopilot/tests/**", "tests/**", "src/**", "pyproject.toml", "refs/heads/main", "refs/remotes/origin/**", "docs/execution/dags/fixture-prerequisite-v1/**", "docs/execution/dags/fixture-prerequisite-causality-appeal-v1/**", "docs/execution/dags/git-commit-observation-v1/**", "docs/execution/dags/doctor-performance-v1/**", "evidence/performance/doctor-performance-v1/**", "evidence/courts/CASE-DOCTOR-PERFORMANCE-PROMOTION.json"]
def digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
def build_plan() -> dict[str, Any]:
    writes = {spec["id"]: spec["write_scope"] for spec in SPECS}; nodes = []
    for spec in SPECS:
        node = dict(spec); other = sorted({path for ident, paths in writes.items() if ident != node["id"] for path in paths})
        node["forbidden_scope"] = list(dict.fromkeys([*COMMON_FORBIDDEN, *other])); node["file_locks"] = list(node["write_scope"]); node["downstream_unlock_value"] = node["critical_path_importance"]; node["contract_digest"] = digest(node); nodes.append(node)
    plan = {"schema_version":1,"kind":"hive-mind-fixture-prerequisite-causality-reseal-v2","plan_id":"fixture-prerequisite-causality-reseal-v2","title":"Fixture prerequisite causality reseal v2 (no-code)","baseline":{"commit":EVALUATED_COMMIT,"tree":EVALUATED_TREE,"rejected_tuples":[{"commit":c,"tree":t} for c,t in REJECTED_TUPLES],"frozen_autopilot_plan":FROZEN_AUTOPILOT_PLAN},"source":{"directory":DAG_DIR,"opening_court":OPENING},"current_state":{"implementation":"forbidden","authority":"corrected-source-causality-evidence-only","original_fpc_nodes":"forbidden","fixture_promotion":"forbidden","gco_promotion":"forbidden","performance_claim":"forbidden","knowledge_baseline_retry":"forbidden"},"execution":{"max_sessions":4,"generate":f"python {DAG_DIR}/generate_plan.py --output {OUTPUT_PATH}","lint":f"python .autopilot/bin/autopilot.py --repo-root . dag-lint --plan {OUTPUT_PATH} --strict --json","rounds":f"python .autopilot/bin/autopilot.py --repo-root . dag-rounds --plan {OUTPUT_PATH} --max-sessions 4 --actor codex:fpcr-v2 --json","rules":["workers use isolated branches and one retained unsquashed commit","FPCR-EXECUTE-020 and FPCR-CROSS-030 may run in parallel only after FPCR-DISCOVERY-010","the root-CI execution is exactly one serialized hermetic invocation with a 2700-second timeout","no main, remote, implementation, protected plan, existing DAG mutation, original FPC unlock, performance/GCO/baseline work"]},"invariants":[f"Only source commit/tree {EVALUATED_COMMIT}/{EVALUATED_TREE} may be evaluated; runner must invoke git rev-parse {EVALUATED_COMMIT}^{{tree}} and require {EVALUATED_TREE}.",f"Bad tuples {REJECTED_TUPLES[0][0]}/{REJECTED_TUPLES[0][1]} and {REJECTED_TUPLES[1][0]}/{REJECTED_TUPLES[1][1]} are rejected before discovery or execution.",f"{CLAIMED_DISCOVERY_COUNT} is a claim to independently verify, not a sealed result.",f"Exactly one root-CI execution is allowed with a hard serialized {RUNNER_TIMEOUT_SECONDS}-second budget and no retry.","No code, tests, production source, Autopilot plan, cache, daemon, network effect, original-FPC unlock, fixture/GCO promotion, performance conclusion, or knowledge BASELINE retry is authorized."],"nodes":nodes}
    plan["plan_digest"] = digest(plan); return plan
def render(plan: dict[str, Any]) -> bytes: return (json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+"\n").encode()
def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--output",default=OUTPUT_PATH); parser.add_argument("--stdout",action="store_true"); args=parser.parse_args(); plan=build_plan()
    if args.stdout: print(render(plan).decode(),end="")
    else:
        output=Path(args.output); output.parent.mkdir(parents=True,exist_ok=True); output.write_bytes(render(plan)); print(json.dumps({"output":str(output),"plan_id":plan["plan_id"],"plan_digest":plan["plan_digest"],"nodes":len(plan["nodes"])},sort_keys=True))
    return 0
if __name__ == "__main__": raise SystemExit(main())
