from __future__ import annotations

import argparse
import json
from pathlib import Path

from hive_mind_os.foundation.orchestrator_playbook import (
    compile_orchestrator_plan,
    compile_orchestrator_successor,
    example_orchestrator_request,
)
from hive_mind_os.foundation.orchestrator_playbook_contracts import (
    ORCHESTRATOR_SCHEMA_NAMES,
    validate_orchestrator,
    validate_orchestrator_catalog,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the Phase 5A Orchestrator from an isolated wheel installation."
    )
    parser.add_argument("--installed-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    installed_root = args.installed_root.resolve()
    module_path = Path(__file__).resolve()
    # The script itself remains in the source checkout. The imported package must not.
    import hive_mind_os.foundation.orchestrator_playbook as module

    imported_from = Path(module.__file__).resolve()
    if not imported_from.is_relative_to(installed_root):
        raise RuntimeError(
            f"orchestrator_playbook imported from {imported_from}, not {installed_root}"
        )
    successor = compile_orchestrator_successor()
    plan = compile_orchestrator_plan(example_orchestrator_request())
    if not validate_orchestrator_catalog().valid:
        raise RuntimeError("Phase 5A schema catalog is invalid")
    if not validate_orchestrator("orchestrator-agent-successor-v1", successor).valid:
        raise RuntimeError("installed Orchestrator successor is invalid")
    if not validate_orchestrator("orchestrator-plan-envelope-v1", plan).valid:
        raise RuntimeError("installed Orchestrator plan is invalid")
    if successor["effective_capabilities"] or successor["tool_refs"]:
        raise RuntimeError("installed Orchestrator gained effective capabilities or tools")
    if successor["authority"] != "none" or successor["activation"] != "inert":
        raise RuntimeError("installed Orchestrator authority or activation drifted")
    court = plan["outputs"]["court_schedule"]
    stop = plan["outputs"]["stop_decision"]
    handoff = plan["outputs"]["handoff"]
    if court["authenticated_distinct_actors"]:
        raise RuntimeError("installed candidate fabricated authenticated independence")
    if court["independence_status"] != "procedural-only":
        raise RuntimeError("installed example procedural coverage drifted")
    if stop["evidence_status"] != "claimed-unverified":
        raise RuntimeError("installed example evidence truth state drifted")
    if stop["decision"] != "defer" or handoff["next_role"] != "curator":
        raise RuntimeError("installed example stop or handoff posture drifted")
    expected_scope = {
        "request_id": plan["request_id"],
        "request_digest": plan["request_digest"],
        "objective_id": plan["objective_id"],
        "tenant_id": plan["tenant_id"],
        "repository_id": plan["repository_id"],
    }
    for field, output in plan["outputs"].items():
        for scope_field, expected in expected_scope.items():
            if output[scope_field] != expected:
                raise RuntimeError(
                    f"installed {field} lost {scope_field} scope binding"
                )
    if any(
        output.get("completion_authorized") is True
        or output.get("activation_authorized") is True
        for output in plan["outputs"].values()
    ):
        raise RuntimeError("installed candidate authorized completion or activation")

    try:
        script_path = module_path.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        script_path = module_path.name
    imported_path = imported_from.relative_to(installed_root).as_posix()

    result = {
        "schema_version": 1,
        "verification": "phase5a-installed-wheel",
        "script_path": script_path,
        "imported_from": imported_path,
        "successor_digest": successor["content_digest"],
        "request_digest": plan["request_digest"],
        "plan_digest": plan["plan_digest"],
        "schema_count": len(ORCHESTRATOR_SCHEMA_NAMES),
        "output_count": len(plan["outputs"]),
        "work_item_count": len(plan["outputs"]["objective_decomposition"]["work_items"]),
        "dependency_count": len(plan["outputs"]["dependency_graph"]["edges"]),
        "activation": successor["activation"],
        "authority": successor["authority"],
        "effective_capability_count": len(successor["effective_capabilities"]),
        "tool_count": len(successor["tool_refs"]),
        "independence_status": court["independence_status"],
        "authenticated_distinct_actors": False,
        "stop_decision": stop["decision"],
        "evidence_status": stop["evidence_status"],
        "handoff_role": handoff["next_role"],
        "handoff_required_ref_count": len(handoff["required_refs"]),
        "max_handoff_refs": successor["budgets"]["max_handoff_refs"],
        "completion_authorized": False,
        "activation_authorized": False,
    }
    rendered = json.dumps(result, sort_keys=True)
    print(rendered)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
