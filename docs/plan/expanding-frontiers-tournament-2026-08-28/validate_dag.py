"""Validate EXECUTION_DAG.json: dependency resolution, acyclicity, level ordering,
durability ordering for irreversible nodes, critical-path integrity, and presence of
every GenericPrompt section 17 node-contract field.

Run: python docs/plan/expanding-frontiers-tournament-2026-08-28/validate_dag.py
Exit 0 = valid. Exit 1 = errors printed.
"""

from __future__ import annotations

import json
import pathlib
import sys

CONTRACT_FIELDS = [
    "id", "objective", "rationale", "dependencies", "assumptions", "required_inputs",
    "expected_outputs", "read_scope", "write_scope", "forbidden_scope", "branch",
    "acceptance_criteria", "evidence_requirements", "risk", "reversibility", "effort",
    "critical_path_importance", "downstream_unlock_value", "merge_conflict_surface",
    "file_locks", "semantic_locks", "parallel_safe", "rollback", "stopping_condition",
    "escalation_conditions", "min_openai_model", "min_anthropic_model",
]


def main() -> int:
    plan = json.loads((pathlib.Path(__file__).with_name("EXECUTION_DAG.json")).read_text(encoding="utf-8"))
    nodes = {n["id"]: n for n in plan["nodes"]}
    errors: list[str] = []

    level_of = {i: int(l.split("_")[1]) for l, ids in plan["safe_parallelism"].items() for i in ids}
    if set(level_of) != set(nodes):
        errors.append(f"level coverage mismatch: {sorted(set(nodes) ^ set(level_of))}")

    seen: set[str] = set()
    stack: set[str] = set()

    def visit(nid: str) -> None:
        if nid in stack:
            errors.append(f"cycle detected at {nid}")
            return
        if nid in seen:
            return
        stack.add(nid)
        for dep in nodes[nid]["dependencies"]:
            if dep in nodes:
                visit(dep)
        stack.discard(nid)
        seen.add(nid)

    for nid in nodes:
        visit(nid)

    for nid, node in nodes.items():
        for dep in node["dependencies"]:
            if dep not in nodes:
                errors.append(f"{nid}: unknown dependency {dep}")
            elif level_of.get(dep, -1) >= level_of.get(nid, 99):
                errors.append(f"{nid} (L{level_of.get(nid)}) depends on {dep} (L{level_of.get(dep)}); a dependency level is not an executable wave")
        if node["reversibility"] == "irreversible" and len(plan["safe_parallelism"][f"level_{level_of[nid]}"]) != 1:
            errors.append(f"{nid} is irreversible but shares its level with other nodes")
        for field in CONTRACT_FIELDS:
            if field not in node:
                errors.append(f"{nid}: missing section-17 contract field {field}")

    path = plan["critical_path"]
    for earlier, later in zip(path, path[1:]):
        if earlier not in nodes[later]["dependencies"]:
            errors.append(f"critical path is not a chain: {later} does not depend on {earlier}")

    if errors:
        print("DAG INVALID")
        for error in errors:
            print(f"  - {error}")
        return 1

    print(f"DAG VALID: {len(nodes)} nodes, {len(plan['safe_parallelism'])} levels, critical path {' -> '.join(path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
