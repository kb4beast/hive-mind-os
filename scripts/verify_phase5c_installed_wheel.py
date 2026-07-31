from __future__ import annotations

import argparse
import json
from pathlib import Path

from hive_mind_os.foundation.builder_playbook import (
    compile_builder_implementation,
    compile_builder_successor,
    example_builder_request,
)
from hive_mind_os.foundation.builder_playbook_contracts import (
    BUILDER_SCHEMA_NAMES,
    OUTPUT_FIELDS,
    OUTPUT_SCHEMA_BY_FIELD,
    RESOURCE_AXES,
    RESOURCE_SECTIONS,
    validate_builder,
    validate_builder_catalog,
)


def _verify_resources(implementation: dict[str, object]) -> None:
    resource = implementation["resource_accounting"]  # type: ignore[index]
    if resource["accounting_status"] != "known":  # type: ignore[index]
        raise RuntimeError("installed example resource accounting is not known")
    if resource["lease_status"] != "not-issued":  # type: ignore[index]
        raise RuntimeError("installed Builder issued a resource lease")
    if resource["budget_authorized"]:  # type: ignore[index]
        raise RuntimeError("installed Builder authorized a budget")
    axes = resource["axes"]  # type: ignore[index]
    for axis in RESOURCE_AXES:
        allocation = axes[axis]
        sections = allocation["section_allocations"]
        if set(sections) != set(RESOURCE_SECTIONS):
            raise RuntimeError(f"installed {axis} section catalog drifted")
        for reserve in ("checkpoint_reserve", "evidence_reserve", "rollback_reserve"):
            if allocation[reserve] <= 0:
                raise RuntimeError(f"installed {axis} {reserve} is not positive")
        if any(value <= 0 for value in sections.values()):
            raise RuntimeError(f"installed {axis} contains an unfunded Builder section")
        total = (
            allocation["checkpoint_reserve"]
            + allocation["evidence_reserve"]
            + allocation["rollback_reserve"]
            + sum(sections.values())
        )
        if total != allocation["ceiling"]:
            raise RuntimeError(f"installed {axis} resource plan does not reconcile")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the Phase 5C Builder from an isolated wheel installation."
    )
    parser.add_argument("--installed-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    installed_root = args.installed_root.resolve()
    module_path = Path(__file__).resolve()
    import hive_mind_os.foundation.builder_playbook as module

    imported_from = Path(module.__file__).resolve()
    if not imported_from.is_relative_to(installed_root):
        raise RuntimeError(
            f"builder_playbook imported from {imported_from}, not {installed_root}"
        )

    successor = compile_builder_successor()
    implementation = compile_builder_implementation(example_builder_request())
    if not validate_builder_catalog().valid:
        raise RuntimeError("Phase 5C schema catalog is invalid")
    if not validate_builder("builder-agent-successor-v1", successor).valid:
        raise RuntimeError("installed Builder successor is invalid")
    if not validate_builder(
        "builder-implementation-envelope-v1", implementation
    ).valid:
        raise RuntimeError("installed Builder implementation envelope is invalid")
    for field in OUTPUT_FIELDS:
        if not validate_builder(
            OUTPUT_SCHEMA_BY_FIELD[field], implementation["outputs"][field]
        ).valid:
            raise RuntimeError(f"installed Builder {field} output is invalid")

    if successor["effective_capabilities"] or successor["tool_refs"]:
        raise RuntimeError("installed Builder gained effective capabilities or tools")
    if successor["authority"] != "none" or successor["activation"] != "inert":
        raise RuntimeError("installed Builder authority or activation drifted")
    if successor["public"]:
        raise RuntimeError("installed Builder became public")
    for field in (
        "implementation_authorized",
        "execution_authorized",
        "test_result_authorized",
        "completion_authorized",
        "promotion_authorized",
    ):
        if successor[field]:
            raise RuntimeError(f"installed Builder escalated {field}")

    expected_scope = {
        "request_id": implementation["request_id"],
        "request_digest": implementation["request_digest"],
        "objective_id": implementation["objective_id"],
        "tenant_id": implementation["tenant_id"],
        "repository_id": implementation["repository_id"],
    }
    for field, output in implementation["outputs"].items():
        for scope_field, expected in expected_scope.items():
            if output[scope_field] != expected:
                raise RuntimeError(f"installed {field} lost {scope_field} binding")
        if output["authority_state"]["authority"] != "none":
            raise RuntimeError(f"installed {field} gained authority")

    if implementation["outputs"]["implementation_scope"]["implementation_authorized"]:
        raise RuntimeError("installed Builder authorized implementation")
    if implementation["outputs"]["change_plan"]["execution_authorized"]:
        raise RuntimeError("installed Builder authorized execution")
    if implementation["outputs"]["test_plan"]["tests_executed"]:
        raise RuntimeError("installed Builder claimed tests ran")
    if implementation["outputs"]["test_plan"]["test_results_authorized"]:
        raise RuntimeError("installed Builder authorized test results")
    if implementation["outputs"]["artifact_manifest"]["artifacts_created"]:
        raise RuntimeError("installed Builder claimed artifacts were created")

    handoff = implementation["outputs"]["curator_handoff"]
    if handoff["next_role"] != "curator":
        raise RuntimeError("installed Builder no longer routes to Curator")
    if handoff["authenticated_distinct_actors"]:
        raise RuntimeError("installed Builder manufactured authenticated independence")
    if not handoff["same_assistant_performed_procedural_passes"]:
        raise RuntimeError("installed Builder concealed procedural same-assistant passes")
    if handoff["independence_claimed"]:
        raise RuntimeError("installed Builder claimed independence")
    for field in (
        "implementation_authorized",
        "completion_authorized",
        "promotion_authorized",
        "activation_authorized",
    ):
        if handoff[field]:
            raise RuntimeError(f"installed Builder escalated handoff {field}")

    _verify_resources(implementation)

    try:
        script_path = module_path.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        script_path = module_path.name
    imported_path = imported_from.relative_to(installed_root).as_posix()
    result = {
        "schema_version": 1,
        "verification": "phase5c-installed-wheel",
        "script_path": script_path,
        "imported_from": imported_path,
        "successor_digest": successor["content_digest"],
        "request_digest": implementation["request_digest"],
        "implementation_digest": implementation["implementation_digest"],
        "schema_count": len(BUILDER_SCHEMA_NAMES),
        "output_count": len(implementation["outputs"]),
        "requirement_count": len(
            implementation["request_snapshot"]["adjudicated_requirements"]
        ),
        "change_count": len(implementation["outputs"]["change_plan"]["ordered_changes"]),
        "test_count": len(implementation["outputs"]["test_plan"]["tests"]),
        "artifact_count": len(
            implementation["outputs"]["artifact_manifest"]["artifacts"]
        ),
        "activation": successor["activation"],
        "authority": successor["authority"],
        "effective_capability_count": len(successor["effective_capabilities"]),
        "tool_count": len(successor["tool_refs"]),
        "resource_accounting_status": implementation["resource_accounting"][
            "accounting_status"
        ],
        "resource_axes_reconciled": list(RESOURCE_AXES),
        "resource_section_count": len(RESOURCE_SECTIONS),
        "handoff_role": handoff["next_role"],
        "implementation_authorized": False,
        "execution_authorized": False,
        "test_result_authorized": False,
        "completion_authorized": False,
        "promotion_authorized": False,
        "activation_authorized": False,
        "authenticated_distinct_actors": False,
        "same_assistant_performed_procedural_passes": True,
        "independence_claimed": False,
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
