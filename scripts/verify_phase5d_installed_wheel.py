from __future__ import annotations

import argparse
import json
from pathlib import Path

from hive_mind_os.foundation.curator_playbook import (
    compile_curator_successor,
    compile_curator_verification,
    example_curator_request,
)
from hive_mind_os.foundation.curator_playbook_contracts import (
    CURATOR_SCHEMA_NAMES,
    OUTPUT_FIELDS,
    OUTPUT_SCHEMA_BY_FIELD,
    RESOURCE_AXES,
    RESOURCE_SECTIONS,
    validate_curator,
    validate_curator_catalog,
)


def _verify_resources(verification: dict[str, object]) -> None:
    resource = verification["resource_accounting"]  # type: ignore[index]
    if resource["accounting_status"] != "known":  # type: ignore[index]
        raise RuntimeError("installed Curator example resource accounting is not known")
    if resource["lease_status"] != "not-issued":  # type: ignore[index]
        raise RuntimeError("installed Curator issued a resource lease")
    if resource["budget_authorized"]:  # type: ignore[index]
        raise RuntimeError("installed Curator authorized a budget")
    axes = resource["axes"]  # type: ignore[index]
    for axis in RESOURCE_AXES:
        allocation = axes[axis]
        sections = allocation["section_allocations"]
        if set(sections) != set(RESOURCE_SECTIONS):
            raise RuntimeError(f"installed {axis} section catalog drifted")
        for reserve in ("verification_reserve", "evidence_reserve", "rollback_reserve"):
            if allocation[reserve] <= 0:
                raise RuntimeError(f"installed {axis} {reserve} is not positive")
        if any(value <= 0 for value in sections.values()):
            raise RuntimeError(f"installed {axis} contains an unfunded Curator section")
        total = (
            allocation["verification_reserve"]
            + allocation["evidence_reserve"]
            + allocation["rollback_reserve"]
            + sum(sections.values())
        )
        if total != allocation["ceiling"]:
            raise RuntimeError(f"installed {axis} resource plan does not reconcile")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the Phase 5D Curator from an isolated wheel installation."
    )
    parser.add_argument("--installed-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    installed_root = args.installed_root.resolve()
    module_path = Path(__file__).resolve()
    import hive_mind_os.foundation.curator_playbook as module

    imported_from = Path(module.__file__).resolve()
    if not imported_from.is_relative_to(installed_root):
        raise RuntimeError(
            f"curator_playbook imported from {imported_from}, not {installed_root}"
        )

    successor = compile_curator_successor()
    verification = compile_curator_verification(example_curator_request())
    if not validate_curator_catalog().valid:
        raise RuntimeError("Phase 5D schema catalog is invalid")
    if not validate_curator("curator-agent-successor-v1", successor).valid:
        raise RuntimeError("installed Curator successor is invalid")
    if not validate_curator("curator-verification-envelope-v1", verification).valid:
        raise RuntimeError("installed Curator verification envelope is invalid")
    for field in OUTPUT_FIELDS:
        if not validate_curator(
            OUTPUT_SCHEMA_BY_FIELD[field], verification["outputs"][field]
        ).valid:
            raise RuntimeError(f"installed Curator {field} output is invalid")

    if successor["effective_capabilities"] or successor["tool_refs"]:
        raise RuntimeError("installed Curator gained effective capabilities or tools")
    if successor["authority"] != "none" or successor["activation"] != "inert":
        raise RuntimeError("installed Curator authority or activation drifted")
    if successor["public"]:
        raise RuntimeError("installed Curator became public")
    for field in (
        "implementation_authorized",
        "execution_authorized",
        "test_result_authorized",
        "completion_authorized",
        "release_authorized",
        "approval_authorized",
        "promotion_authorized",
    ):
        if successor[field]:
            raise RuntimeError(f"installed Curator escalated {field}")

    expected_scope = {
        "request_id": verification["request_id"],
        "request_digest": verification["request_digest"],
        "objective_id": verification["objective_id"],
        "tenant_id": verification["tenant_id"],
        "repository_id": verification["repository_id"],
    }
    for field, output in verification["outputs"].items():
        for scope_field, expected in expected_scope.items():
            if output[scope_field] != expected:
                raise RuntimeError(f"installed {field} lost {scope_field} binding")
        if output["authority_state"]["authority"] != "none":
            raise RuntimeError(f"installed {field} gained authority")
        if output["authenticated_distinct_actors"]:
            raise RuntimeError(f"installed {field} manufactured authenticated independence")
        if not output["same_assistant_performed_procedural_passes"]:
            raise RuntimeError(f"installed {field} concealed procedural same-assistant passes")
        if output["independence_claimed"]:
            raise RuntimeError(f"installed {field} claimed independence")

    reproduction = verification["outputs"]["clean_boundary_reproduction"]
    if reproduction["commands_executed_by_playbook"]:
        raise RuntimeError("installed Curator claimed commands executed")
    if reproduction["test_results_authorized"]:
        raise RuntimeError("installed Curator authorized test results")
    artifact = verification["outputs"]["artifact_receipt_verification"]
    if artifact["artifacts_created_by_playbook"] or artifact["verification_authorized"]:
        raise RuntimeError("installed Curator claimed artifact or verification authority")
    rollback = verification["outputs"]["rollback_verification"]
    if (
        rollback["rollback_executed_by_playbook"]
        or rollback["rollback_verified_by_playbook"]
        or rollback["rollback_authorized"]
    ):
        raise RuntimeError("installed Curator escalated rollback authority")
    recommendation = verification["outputs"]["release_recommendation"]
    if recommendation["recommendation"] != "defer":
        raise RuntimeError("installed Curator exceeded the bounded release recommendation")
    if (
        recommendation["release_ready"]
        or recommendation["release_authorized"]
        or recommendation["approval_authorized"]
    ):
        raise RuntimeError("installed Curator claimed release or approval authority")

    _verify_resources(verification)

    try:
        script_path = module_path.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        script_path = module_path.name
    imported_path = imported_from.relative_to(installed_root).as_posix()
    result = {
        "schema_version": 1,
        "verification": "phase5d-installed-wheel",
        "script_path": script_path,
        "imported_from": imported_path,
        "successor_digest": successor["content_digest"],
        "request_digest": verification["request_digest"],
        "verification_digest": verification["verification_digest"],
        "schema_count": len(CURATOR_SCHEMA_NAMES),
        "output_count": len(verification["outputs"]),
        "claim_count": len(verification["request_snapshot"]["claims"]),
        "check_count": len(verification["request_snapshot"]["sealed_checks"]),
        "evidence_count": len(verification["request_snapshot"]["observed_evidence"]),
        "source_count": len(verification["request_snapshot"]["sources"]),
        "regression_target_count": len(
            verification["request_snapshot"]["regression_targets"]
        ),
        "activation": successor["activation"],
        "authority": successor["authority"],
        "effective_capability_count": len(successor["effective_capabilities"]),
        "tool_count": len(successor["tool_refs"]),
        "resource_accounting_status": verification["resource_accounting"][
            "accounting_status"
        ],
        "resource_axes_reconciled": list(RESOURCE_AXES),
        "resource_section_count": len(RESOURCE_SECTIONS),
        "structural_status": recommendation["structural_status"],
        "recommendation": recommendation["recommendation"],
        "implementation_authorized": False,
        "execution_authorized": False,
        "test_result_authorized": False,
        "completion_authorized": False,
        "release_authorized": False,
        "approval_authorized": False,
        "promotion_authorized": False,
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
