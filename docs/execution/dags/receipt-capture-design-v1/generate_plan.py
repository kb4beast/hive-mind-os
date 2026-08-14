#!/usr/bin/env python3
"""Deterministically materialize the receipt-capture design-only DAG."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from specs import SPECS, DAG_DIR, AUTHORITY_COMMIT, AUTHORITY_TREE, COMMON_FORBIDDEN, OPENING, PREDECESSOR, DESIGN_REQUIREMENTS
OUTPUT = ".autopilot/state/receipt-capture-design-v1.json"
def digest(value): return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
def build_plan():
    writes = {item["id"]: item["write_scope"] for item in SPECS}; nodes = []
    for item in SPECS:
        value = dict(item); other = sorted({p for ident, paths in writes.items() if ident != value["id"] for p in paths})
        value["forbidden_scope"] = list(dict.fromkeys([*COMMON_FORBIDDEN, *other])); value["file_locks"] = list(value["write_scope"])
        value["downstream_unlock_value"] = value["critical_path_importance"]; value["contract_digest"] = digest(value); nodes.append(value)
    plan = {
        "schema_version": 1, "kind": "hive-mind-receipt-capture-design-v1", "plan_id": "receipt-capture-design-v1", "title": "Receipt capture design (forward-looking, no code)",
        "authority": {"commit": AUTHORITY_COMMIT, "tree": AUTHORITY_TREE, "predecessor": PREDECESSOR},
        "source": {"directory": DAG_DIR, "opening_court": OPENING}, "design_requirements": DESIGN_REQUIREMENTS,
        "current_state": {"implementation": "forbidden", "ci_and_test_execution": "forbidden", "candidate_use": "forbidden", "main_and_remote": "forbidden"},
        "execution": {"max_sessions": 4, "lint": f"python .autopilot/bin/autopilot.py --repo-root . dag-lint --plan {OUTPUT} --strict --json", "rounds": f"python .autopilot/bin/autopilot.py --repo-root . dag-rounds --plan {OUTPUT} --max-sessions 4 --actor codex:rcd --json", "rules": ["RCD-ARCH-010 and RCD-CROSS-020 may run in parallel after RCD-SEAL-000", "no code, tests, CI, unittest discovery, candidates, performance, main, remote, or plan mutation", "only a later separate native implementation-proposal DAG may be opened after an RCD Judge finds zero unresolved material findings"]},
        "invariants": ["This court designs future retention; it does not repair historical evidence.", "Every design must cover every sealed receipt-capture requirement.", "41950 and d02 remain adverse evidence and are not reusable.", "The Judge may authorize an opening only, never implementation."],
        "lint_warning_justifications": [{"check": "scaffold-collision", "node": "RCD-SEAL-000", "subjects": ["docs/execution/__init__.py", "docs/execution/dags/__init__.py"], "reason": "These documentation-resident DAG scripts are executed by explicit path and are not Python package modules. The requested sealed write surface excludes both unrelated package markers; no marker is needed or may be created."}], "nodes": nodes,
    }; plan["plan_digest"] = digest(plan); return plan
def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--output", default=OUTPUT); parser.add_argument("--stdout", action="store_true"); args = parser.parse_args(); text = json.dumps(build_plan(), sort_keys=True, indent=2) + "\n"
    if args.stdout: print(text, end="")
    else: path = Path(args.output); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text); print(json.dumps({"output": str(path), "plan_digest": build_plan()["plan_digest"], "nodes": 5}, sort_keys=True))
if __name__ == "__main__": main()
