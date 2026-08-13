#!/usr/bin/env python3
"""Deterministically materialize the no-code FPC appeal DAG."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from typing import Any
from specs import (SPECS, DAG_DIR, OPENING, BASELINE_COMMIT, BASELINE_TREE,
                   CAUSALITY_RECEIPT, DISCOVERY_COUNT, DISCOVERY_DIGEST,
                   FROZEN_AUTOPILOT_PLAN, RUNNER_TIMEOUT_SECONDS)

OUTPUT_PATH = ".autopilot/state/fixture-prerequisite-causality-appeal-v1.json"
COMMON_FORBIDDEN = [
    ".autopilot/plan.json", ".autopilot/control-plane.json", ".autopilot/bin/**",
    ".autopilot/tests/**", "tests/**", "src/**", "pyproject.toml", "refs/heads/main",
    "refs/remotes/origin/**", "docs/execution/dags/fixture-prerequisite-v1/**",
    "docs/execution/dags/git-commit-observation-v1/**",
    "docs/execution/dags/doctor-performance-v1/**",
    "evidence/performance/doctor-performance-v1/**",
    "evidence/courts/CASE-DOCTOR-PERFORMANCE-PROMOTION.json",
]
def digest(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(data.encode()).hexdigest()
def build_plan() -> dict[str, Any]:
    writes = {node["id"]: node["write_scope"] for node in SPECS}
    nodes = []
    for spec in SPECS:
        node = dict(spec)
        other = sorted({path for ident, paths in writes.items() if ident != node["id"] for path in paths})
        node["forbidden_scope"] = list(dict.fromkeys([*COMMON_FORBIDDEN, *other]))
        node["file_locks"] = list(node["write_scope"])
        node["downstream_unlock_value"] = node["critical_path_importance"]
        node["contract_digest"] = digest(node)
        nodes.append(node)
    plan = {
        "schema_version": 1,
        "kind": "hive-mind-fixture-prerequisite-causality-appeal-v1",
        "plan_id": "fixture-prerequisite-causality-appeal-v1",
        "title": "Fixture prerequisite causality appeal (no-code)",
        "baseline": {"commit": BASELINE_COMMIT, "tree": BASELINE_TREE,
                     "predecessor_causality_receipt": CAUSALITY_RECEIPT,
                     "frozen_autopilot_plan": FROZEN_AUTOPILOT_PLAN},
        "source": {"directory": DAG_DIR, "opening_court": OPENING},
        "current_state": {"implementation": "forbidden", "authority": "causality-evidence-only",
                          "fixture_promotion": "forbidden", "gco_promotion": "forbidden",
                          "performance_claim": "forbidden", "knowledge_baseline_retry": "forbidden"},
        "execution": {"max_sessions": 4,
                      "generate": f"python {DAG_DIR}/generate_plan.py --output {OUTPUT_PATH}",
                      "lint": f"python .autopilot/bin/autopilot.py --repo-root . dag-lint --plan {OUTPUT_PATH} --strict --json",
                      "rounds": f"python .autopilot/bin/autopilot.py --repo-root . dag-rounds --plan {OUTPUT_PATH} --max-sessions 4 --actor codex:fixture-prerequisite-causality --json",
                      "rules": ["workers use isolated branches and one retained unsquashed commit", "FPC-CROSS-030 may run in parallel with FPC-EXECUTE-020 only after FPC-DISCOVERY-010", "the root-CI execution is exactly one serialized hermetic invocation with a 2700-second timeout", "no main, remote, implementation, protected plan, or existing DAG mutation"]},
        "invariants": [
            f"The predecessor causality receipt is pinned at {CAUSALITY_RECEIPT}; it found exactly {DISCOVERY_COUNT} test IDs with digest {DISCOVERY_DIGEST} and did not complete its root-CI inventory.",
            "The sole allowed root-CI execution is fresh editable-install, PYTHONNOUSERSITE=1, cleared PYTHONPATH, -E -s, repository src import origin, and a complete durable transcript.",
            f"That execution has a hard serialized wall-clock budget of {RUNNER_TIMEOUT_SECONDS} seconds and never authorizes a rerun.",
            "No code, tests, production source, Autopilot plan, cache, daemon, network effect, fixture/GCO promotion, performance conclusion, or knowledge BASELINE retry is authorized.",
            "Only a distinct Judge may issue a narrow causal disposition; any implementation requires an independently sealed successor DAG.",
        ], "nodes": nodes}
    plan["plan_digest"] = digest(plan)
    return plan
def render(plan: dict[str, Any]) -> bytes:
    return (json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", default=OUTPUT_PATH); parser.add_argument("--stdout", action="store_true"); args = parser.parse_args()
    plan = build_plan()
    if args.stdout: print(render(plan).decode(), end="")
    else:
        output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True); output.write_bytes(render(plan))
        print(json.dumps({"output": str(output), "plan_id": plan["plan_id"], "plan_digest": plan["plan_digest"], "nodes": len(plan["nodes"])}, sort_keys=True))
    return 0
if __name__ == "__main__": raise SystemExit(main())
