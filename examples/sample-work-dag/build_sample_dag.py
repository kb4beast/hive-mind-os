"""Build, validate, and print one sample Orchestrator work DAG.

The graph is constructed with the real kernel planner, so every property this
example prints -- topological order, ready waves, digests, and the messages the
validator returns for malformed graphs -- is derived, not asserted.

Run from a checkout:

    python examples/sample-work-dag/build_sample_dag.py
    python examples/sample-work-dag/build_sample_dag.py --json sample-work-dag.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from hive_mind_os.brain_kernel.canonical import canonical_digest  # noqa: E402
from hive_mind_os.brain_kernel.contracts import (  # noqa: E402
    Budget,
    MissionCharter,
    MissionState,
    WorkItem,
    WorkState,
)
from hive_mind_os.brain_kernel.objectives import ObjectiveGraph  # noqa: E402
from hive_mind_os.brain_kernel.planner import OrchestratorPlanner, WorkSchedule  # noqa: E402

EMPTY_DIGEST = "sha256:" + "0" * 64
MISSION_ID = "MISSION-checkout-latency"
OBJECTIVE = "Cut p95 checkout latency below 400ms without changing the public API"

CHARTER = MissionCharter(
    schema_version=1,
    mission_id=MISSION_ID,
    created_at="2026-08-28T00:00:00Z",
    objective=OBJECTIVE,
    acceptance_specs=("SPEC-p95-under-400ms", "SPEC-no-public-api-change"),
    repository_root="/srv/checkout",
    base_commit="a" * 40,
    target_branch="release/hive-mind-autopilot",
    policy_fingerprint=EMPTY_DIGEST,
    role_registry_fingerprint=EMPTY_DIGEST,
    model_route_fingerprint=EMPTY_DIGEST,
    budget=Budget(
        max_wall_seconds=7200,
        max_model_calls=240,
        max_input_tokens=2_000_000,
        max_output_tokens=500_000,
        max_cost_microunits=9_000_000,
        max_tool_calls=900,
        max_work_items=12,
        max_depth=3,
    ),
    external_grants=(),
    protected_branches=("main",),
    human_gates=("GATE-schema-migration",),
    status=MissionState.PLANNING,
)

ROOT_ID = "WORK-000-root"


def work_item(
    work_id: str,
    role: str,
    risk_tier: str,
    dependencies: tuple[str, ...],
    title: str,
    expected_outputs: tuple[str, ...] = (),
    required_inputs: tuple[str, ...] = (),
    acceptance_specs: tuple[str, ...] = (),
    write_scope: tuple[str, ...] = (),
    depth: int = 1,
    parent_work_id: str | None = ROOT_ID,
) -> WorkItem:
    return WorkItem(
        work_id=work_id,
        mission_id=MISSION_ID,
        parent_work_id=parent_work_id,
        depth=depth,
        title=title,
        objective=OBJECTIVE,
        role=role,
        risk_tier=risk_tier,
        dependencies=dependencies,
        required_inputs=required_inputs,
        expected_outputs=expected_outputs,
        acceptance_specs=acceptance_specs,
        write_scope=write_scope,
        requested_actions=(),
        context_request={},
        max_attempts=2,
        status=WorkState.PROPOSED,
        authority_envelope_digest=EMPTY_DIGEST,
        idempotency_key=canonical_digest({"work_id": work_id}),
    )


WORK_ITEMS = (
    work_item(
        ROOT_ID, "orchestrator", "R0", ("WORK-060-verify",),
        "Deliver the checkout latency objective",
        required_inputs=("evidence:verdict",), depth=0, parent_work_id=None,
    ),
    work_item(
        "WORK-010-profile", "explorer", "R0", (),
        "Reproduce and profile the p95 regression",
        expected_outputs=("evidence:profile",),
    ),
    work_item(
        "WORK-011-survey", "explorer", "R0", (),
        "Survey call sites and query plans",
        expected_outputs=("evidence:callgraph",),
    ),
    work_item(
        "WORK-020-design", "architect", "R1", ("WORK-010-profile", "WORK-011-survey"),
        "Design the cache and index change with rollback",
        expected_outputs=("design:adr-014",),
        required_inputs=("evidence:profile", "evidence:callgraph"),
    ),
    work_item(
        "WORK-030-cache", "builder", "R2", ("WORK-020-design",),
        "Implement the read-through cache",
        expected_outputs=("code:cache",),
        required_inputs=("design:adr-014",),
        acceptance_specs=("SPEC-p95-under-400ms",),
        write_scope=("src/checkout/cache.py",),
    ),
    work_item(
        "WORK-031-index", "builder", "R3", ("WORK-020-design",),
        "Add the covering index migration",
        expected_outputs=("code:migration",),
        required_inputs=("design:adr-014",),
        acceptance_specs=("SPEC-no-public-api-change",),
        write_scope=("migrations/0042_index.sql",),
    ),
    work_item(
        "WORK-040-contract", "integrator", "R1", ("WORK-030-cache", "WORK-031-index"),
        "Re-run the public API contract tests",
        expected_outputs=("evidence:contract",),
        required_inputs=("code:cache", "code:migration"),
        write_scope=("src/checkout/api.py",),
    ),
    work_item(
        "WORK-050-health", "steward", "R1", ("WORK-030-cache",),
        "Add the cache hit-rate metric and runbook",
        expected_outputs=("ops:runbook",),
        required_inputs=("code:cache",),
        write_scope=("docs/runbooks/cache.md",),
    ),
    work_item(
        "WORK-060-verify", "curator", "R2", ("WORK-040-contract", "WORK-050-health"),
        "Independently re-run the sealed checks",
        expected_outputs=("evidence:verdict",),
        required_inputs=("evidence:contract", "ops:runbook"),
    ),
)


def schedule(
    work_id: str,
    risk_lane: str,
    stop_conditions: tuple[str, ...],
    consultation_roles: tuple[str, ...],
    human_gates: tuple[str, ...] = (),
    *,
    wall_seconds: int = 900,
    model_calls: int = 40,
    tool_calls: int = 150,
) -> WorkSchedule:
    return WorkSchedule(
        work_id=work_id,
        budget=Budget(
            max_wall_seconds=wall_seconds,
            max_model_calls=model_calls,
            max_input_tokens=200_000,
            max_output_tokens=50_000,
            max_cost_microunits=1_000_000,
            max_tool_calls=tool_calls,
            max_work_items=12,
            max_depth=3,
        ),
        risk_lane=risk_lane,
        stop_conditions=stop_conditions,
        consultation_roles=consultation_roles,
        human_gates=human_gates,
    )


SCHEDULES = (
    schedule(ROOT_ID, "R0", ("all child work reached ACCEPTED",), ("curator", "architect"),
             wall_seconds=300, model_calls=10, tool_calls=20),
    schedule("WORK-010-profile", "R0", ("regression reproduced with a receipt",),
             ("architect", "curator"), wall_seconds=600, model_calls=20, tool_calls=80),
    schedule("WORK-011-survey", "R0", ("call graph enumerated",),
             ("architect", "curator"), wall_seconds=600, model_calls=20, tool_calls=80),
    schedule("WORK-020-design", "R1", ("ADR records rollback and threats",),
             ("curator", "steward"), wall_seconds=600, model_calls=30, tool_calls=60),
    schedule("WORK-030-cache", "R2", ("sealed checks pass in the builder workspace",),
             ("curator", "architect")),
    schedule("WORK-031-index", "R3", ("migration is reversible",),
             ("curator", "steward"), ("GATE-schema-migration",)),
    schedule("WORK-040-contract", "R1", ("public API contract unchanged",),
             ("curator", "architect"), wall_seconds=600, model_calls=25, tool_calls=100),
    schedule("WORK-050-health", "R1", ("runbook and metric committed",),
             ("curator", "architect"), wall_seconds=600, model_calls=20, tool_calls=80),
    schedule("WORK-060-verify", "R2", ("verdict recorded from the sealed checks",),
             ("architect", "steward"), model_calls=30, tool_calls=120),
)


def rejection_reason(items) -> str:
    try:
        ObjectiveGraph(CHARTER, items)
    except ValueError as error:
        return str(error)
    return "accepted"


def malformed_graphs() -> tuple[tuple[str, str], ...]:
    """Return each malformed graph label with the validator's own message."""

    base = list(WORK_ITEMS)

    def rewrite(work_id: str, **changes):
        return [replace(item, **changes) if item.work_id == work_id else item for item in base]

    ninth_child = base + [
        work_item("WORK-070-extra", "steward", "R1", ("WORK-020-design",),
                  "A ninth child under one parent", ("ops:extra",),
                  write_scope=("docs/extra.md",))
    ]
    return (
        ("two nodes write the same file, no dependency between them",
         rejection_reason(rewrite("WORK-050-health",
                                  write_scope=("src/checkout/cache.py",),
                                  dependencies=("WORK-020-design",)))),
        ("one node writes a directory another writes a file inside",
         rejection_reason(rewrite("WORK-050-health",
                                  write_scope=("src/checkout",),
                                  dependencies=("WORK-020-design",)))),
        ("the same two nodes with the dependency edge restored",
         rejection_reason(rewrite("WORK-050-health", write_scope=("src/checkout/cache.py",)))),
        ("a dependency cycle",
         rejection_reason(rewrite("WORK-010-profile", dependencies=("WORK-060-verify",)))),
        ("a node depending on itself",
         rejection_reason(rewrite("WORK-030-cache", dependencies=("WORK-030-cache",)))),
        ("a child depth that does not match its parent",
         rejection_reason(rewrite("WORK-030-cache", depth=3))),
        ("a charter acceptance spec no node covers",
         rejection_reason(rewrite("WORK-030-cache", acceptance_specs=()))),
        ("a ninth child under one parent", rejection_reason(ninth_child)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", help="Write the canonical plan document to this path")
    arguments = parser.parse_args()

    plan = OrchestratorPlanner().plan(CHARTER, WORK_ITEMS, SCHEDULES)
    graph = plan.graph

    print(f"charter_digest {CHARTER.digest()}")
    print(f"graph_digest   {graph.digest}")
    print(f"plan_digest    {plan.digest}")

    print("\nTopological order (ties broken by work id):")
    for item in graph.ordered_items():
        dependencies = ", ".join(item.dependencies) or "-"
        print(f"  depth {item.depth}  {item.work_id:<18} {item.role:<12} {item.risk_tier}  <- {dependencies}")

    print("\nReady waves:")
    completed: list[str] = []
    wave = 1
    while len(completed) < len(WORK_ITEMS):
        ready = [item.work_id for item in graph.ready_items(completed) if item.work_id not in completed]
        if not ready:
            break
        print(f"  wave {wave}: {', '.join(ready)}")
        completed.extend(ready)
        wave += 1

    print("\nGraphs the validator refuses:")
    for label, message in malformed_graphs():
        print(f"  {label}\n    -> {message}")

    if arguments.json:
        destination = Path(arguments.json)
        destination.write_text(
            json.dumps(plan.to_document(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"\nWrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
