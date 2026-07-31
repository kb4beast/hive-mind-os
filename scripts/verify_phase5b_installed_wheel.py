from __future__ import annotations

import argparse
import json
from pathlib import Path

from hive_mind_os.foundation.architect_playbook import (
    compile_architect_design,
    compile_architect_successor,
    example_architect_request,
)
from hive_mind_os.foundation.architect_playbook_contracts import (
    ARCHITECT_SCHEMA_NAMES,
    OUTPUT_FIELDS,
    OUTPUT_SCHEMA_BY_FIELD,
    RESOURCE_AXES,
    RESOURCE_SECTIONS,
    validate_architect,
    validate_architect_catalog,
)


def _verify_resources(design: dict[str, object]) -> None:
    resource = design["outputs"]["resource_plan"]  # type: ignore[index]
    if resource["accounting_status"] != "known":  # type: ignore[index]
        raise RuntimeError("installed example resource accounting is not known")
    if resource["lease_status"] != "not-issued":  # type: ignore[index]
        raise RuntimeError("installed Architect issued a resource lease")
    axes = resource["axes"]  # type: ignore[index]
    for axis in RESOURCE_AXES:
        allocation = axes[axis]
        sections = allocation["section_allocations"]
        if set(sections) != set(RESOURCE_SECTIONS):
            raise RuntimeError(f"installed {axis} section catalog drifted")
        if allocation["rollback_reserve"] <= 0:
            raise RuntimeError(f"installed {axis} rollback reserve is not positive")
        if allocation["verification_reserve"] <= 0:
            raise RuntimeError(f"installed {axis} verification reserve is not positive")
        if any(value <= 0 for value in sections.values()):
            raise RuntimeError(f"installed {axis} contains an unfunded design section")
        total = (
            allocation["rollback_reserve"]
            + allocation["verification_reserve"]
            + sum(sections.values())
        )
        if total != allocation["ceiling"]:
            raise RuntimeError(f"installed {axis} resource plan does not reconcile")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the Phase 5B Architect from an isolated wheel installation."
    )
    parser.add_argument("--installed-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    installed_root = args.installed_root.resolve()
    module_path = Path(__file__).resolve()
    import hive_mind_os.foundation.architect_playbook as module

    imported_from = Path(module.__file__).resolve()
    if not imported_from.is_relative_to(installed_root):
        raise RuntimeError(
            f"architect_playbook imported from {imported_from}, not {installed_root}"
        )

    successor = compile_architect_successor()
    design = compile_architect_design(example_architect_request())
    if not validate_architect_catalog().valid:
        raise RuntimeError("Phase 5B schema catalog is invalid")
    if not validate_architect("architect-agent-successor-v1", successor).valid:
        raise RuntimeError("installed Architect successor is invalid")
    if not validate_architect("architect-design-envelope-v1", design).valid:
        raise RuntimeError("installed Architect design envelope is invalid")
    for field in OUTPUT_FIELDS:
        if not validate_architect(
            OUTPUT_SCHEMA_BY_FIELD[field], design["outputs"][field]
        ).valid:
            raise RuntimeError(f"installed Architect {field} output is invalid")

    if successor["effective_capabilities"] or successor["tool_refs"]:
        raise RuntimeError("installed Architect gained effective capabilities or tools")
    if successor["authority"] != "none" or successor["activation"] != "inert":
        raise RuntimeError("installed Architect authority or activation drifted")

    analysis = design["outputs"]["option_analysis"]
    rankings = analysis["rankings"]
    if rankings[0]["option_id"] != "option:modular-inert":
        raise RuntimeError("installed viable example option did not rank first")
    if rankings[0]["viability_status"] != "viable":
        raise RuntimeError("installed first example option is not viable")
    if rankings[1]["weighted_score_ppm"] <= rankings[0]["weighted_score_ppm"]:
        raise RuntimeError("installed blocked example no longer has the higher raw score")
    if rankings[1]["viability_status"] != "blocked":
        raise RuntimeError("installed high-score example option is not blocked")
    if analysis["requested_option_eligible"]:
        raise RuntimeError("installed Architect accepted the blocked requested option")
    if analysis["selection_status"] != "defer":
        raise RuntimeError("installed Architect no longer defers selection")
    if analysis["selection_authorized"]:
        raise RuntimeError("installed Architect authorized design selection")

    expected_scope = {
        "request_id": design["request_id"],
        "request_digest": design["request_digest"],
        "objective_id": design["objective_id"],
        "tenant_id": design["tenant_id"],
        "repository_id": design["repository_id"],
    }
    for field, output in design["outputs"].items():
        for scope_field, expected in expected_scope.items():
            if output[scope_field] != expected:
                raise RuntimeError(f"installed {field} lost {scope_field} binding")

    if design["outputs"]["architecture"]["implementation_authorized"]:
        raise RuntimeError("installed Architect authorized implementation")
    if design["outputs"]["threat_model"]["risk_acceptance_authorized"]:
        raise RuntimeError("installed Architect accepted residual risk")
    if design["outputs"]["resource_plan"]["budget_authorized"]:
        raise RuntimeError("installed Architect authorized a budget")
    if design["outputs"]["handoff"]["activation_authorized"]:
        raise RuntimeError("installed Architect authorized activation")
    if design["outputs"]["handoff"]["next_role"] != "curator":
        raise RuntimeError("installed Architect example handoff no longer routes to Curator")

    _verify_resources(design)

    try:
        script_path = module_path.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        script_path = module_path.name
    imported_path = imported_from.relative_to(installed_root).as_posix()
    result = {
        "schema_version": 1,
        "verification": "phase5b-installed-wheel",
        "script_path": script_path,
        "imported_from": imported_path,
        "successor_digest": successor["content_digest"],
        "request_digest": design["request_digest"],
        "design_digest": design["design_digest"],
        "schema_count": len(ARCHITECT_SCHEMA_NAMES),
        "output_count": len(design["outputs"]),
        "option_count": len(design["request_snapshot"]["options"]),
        "provisional_preferred_option_id": analysis["provisional_preferred_option_id"],
        "requested_option_id": analysis["requested_option_id"],
        "requested_option_eligible": analysis["requested_option_eligible"],
        "selection_status": analysis["selection_status"],
        "activation": successor["activation"],
        "authority": successor["authority"],
        "effective_capability_count": len(successor["effective_capabilities"]),
        "tool_count": len(successor["tool_refs"]),
        "resource_accounting_status": design["outputs"]["resource_plan"][
            "accounting_status"
        ],
        "resource_axes_reconciled": list(RESOURCE_AXES),
        "resource_section_count": len(RESOURCE_SECTIONS),
        "handoff_role": design["outputs"]["handoff"]["next_role"],
        "selection_authorized": False,
        "implementation_authorized": False,
        "risk_acceptance_authorized": False,
        "budget_authorized": False,
        "activation_authorized": False,
        "authenticated_distinct_actors": False,
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
