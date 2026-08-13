#!/usr/bin/env python3
"""Deterministically materialize the doctor-performance-v1 DAG."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from specs import SPECS

DAG_DIR = "docs/execution/dags/doctor-performance-v1"
OUTPUT_PATH = ".autopilot/state/doctor-performance-v1.json"
COMMON_FORBIDDEN = [
    ".autopilot/plan.json",
    ".autopilot/control-plane.json",
    ".autopilot/bin/**",
    ".autopilot/state/**",
    "src/**",
    ".github/**",
    "docs/execution/dags/knowledge-projection-v1/**",
    "docs/plan/knowledge-projection-tournament-2026-08-13/**",
    "refs/heads/main",
    "refs/remotes/origin/**",
]


def digest(value: object) -> str:
    body = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def build_plan() -> dict[str, Any]:
    write_scopes = {str(spec["id"]): list(spec["write_scope"]) for spec in SPECS}
    nodes: list[dict[str, Any]] = []
    for spec in SPECS:
        item = dict(spec)
        overrides = list(item.pop("forbidden_overrides", []))
        other_scopes = sorted(
            {
                scope
                for owner, scopes in write_scopes.items()
                if owner != item["id"]
                for scope in scopes
            }
        )
        autopilot_tests = (
            overrides
            if item["id"] == "DP-FIXTURE-030"
            else [".autopilot/tests/test_*.py"]
        )
        item["forbidden_scope"] = list(
            dict.fromkeys([*COMMON_FORBIDDEN, *autopilot_tests, *other_scopes])
        )
        item["file_locks"] = list(item["write_scope"])
        item["downstream_unlock_value"] = item["critical_path_importance"]
        item["stopping_condition"] = (
            "Stop when every required test and acceptance criterion passes on one "
            "immutable candidate, receipts and identities are retained, no material "
            "finding is unresolved, and changed paths equal write_scope."
        )
        item["rollback"] = (
            "Revert this node's single retained unsquashed integration commit; restore "
            "the frozen suite, retain evidence as superseded, and do not unwind sibling "
            "or predecessor commits."
        )
        item["contract_digest"] = digest(item)
        nodes.append(item)

    plan: dict[str, Any] = {
        "schema_version": 1,
        "kind": "hive-mind-doctor-performance-plan-v1",
        "plan_id": "doctor-performance-v1",
        "title": "Invocation-scoped doctor fixture qualification",
        "subject": (
            "Make the unchanged doctor gate complete within its existing 180-second "
            "timeout by replacing repeated HealingFixture repository construction with "
            "a validated content-addressed seed and per-invocation isolated derivations."
        ),
        "baseline": {
            "planning_commit": "b527aa696590d3a56cefa445dd62a65e569f9116",
            "planning_tree": "b5f5a459f93e85c34f88c5e9bdaa96aa55c37a5c",
            "blocker_evidence_commit": "6bc343f079be6f2d5fd6953d92099a8d5de872b1",
            "blocker_evidence_tree": "16fd5559b5dac7853e044bf2c59893b15022ee74",
            "retrieved_at": "2026-08-13",
        },
        "standard": {
            "path": "docs/execution/DAG_AUTHORING_STANDARD.md",
            "source_commit": "a93df2632f259f4b63f7a4f27eb0b163b5a47204",
            "git_blob_sha": "70e43b0a8078a303d44c0109b8dd218a948258c2",
        },
        "source": {
            "directory": DAG_DIR,
            "generator": f"{DAG_DIR}/generate_plan.py",
            "specifications": [f"{DAG_DIR}/specs.py"],
            "court_record": "evidence/courts/CASE-BASELINE-000-DOCTOR-PERFORMANCE.json",
            "proposed_adr": "docs/architecture/ADR-063-INVOCATION-SCOPED-TEST-FIXTURES.md",
        },
        "current_state": {
            "planning": "complete",
            "implementation": "not_started",
            "knowledge_baseline": "blocked",
            "doctor_controller_change": "forbidden",
            "production_git_cache": "deferred",
        },
        "execution": {
            "max_sessions": 2,
            "generate": f"python {DAG_DIR}/generate_plan.py --output {OUTPUT_PATH}",
            "lint": (
                "python .autopilot/bin/autopilot.py --repo-root . dag-lint "
                f"--plan {OUTPUT_PATH} --strict --json"
            ),
            "rounds": (
                "python .autopilot/bin/autopilot.py --repo-root . dag-rounds "
                f"--plan {OUTPUT_PATH} --max-sessions 2 "
                "--actor codex:doctor-performance --json"
            ),
            "rules": [
                "one node branch and one unsquashed integration commit per node",
                "workers never mutate main, protected remotes, the control plane, or sealed plans",
                "DP-TESTS-010 and DP-BENCH-020 are the only parallel implementation round",
                "the Integrator validates exactly once after each integrated round",
                "no rebase, squash, amend, force-push, scope widening, or external effect",
            ],
        },
        "invariants": [
            "The doctor command, controller timeout, test discovery, test IDs, test bodies, assertions, subtests, behavior constants, order, and skip remain unchanged.",
            "The frozen and candidate suites have the identical complete unittest ID set digest sha256:7c0cf4ae7a2efca60af613b1702c97133a28b043bad09b231fe3a6c97d23eef4.",
            "On the cited host the frozen suite has 381 total executions: 380 pass, zero fail, zero error, and the same conditional skip test_orchestration.IntentOrchestrationTests.test_binding_state_symlink_escape_is_rejected only when directory symlink creation raises OSError.",
            "Every candidate doctor trial is below 180 seconds and nearest-rank p95 is at most 135 seconds on both pinned runtimes.",
            "A seed is content-addressed from a pinned tracked .autopilot snapshot and revalidated before each derivation.",
            "Every invocation receives a fresh isolated writable repository and object database with no sharing, alternates, hardlinks, symlinks, persistent cache, cached verdict, prior result, or network.",
            "Untracked, ignored, state, bytecode, credential-shaped, and outside-snapshot content never enters the seed.",
            "Production code, controller code, protected refs, sealed knowledge artifacts, and .autopilot/plan.json do not change.",
            "Qualification is evidence only; only a distinct Judge may authorize retrying knowledge BASELINE-000.",
        ],
        "nodes": nodes,
    }
    plan["plan_digest"] = digest(plan)
    return plan


def render(plan: dict[str, Any]) -> bytes:
    return (
        json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=OUTPUT_PATH)
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()
    plan = build_plan()
    if args.stdout:
        print(render(plan).decode("utf-8"), end="")
    else:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(render(plan))
        print(json.dumps({
            "output": str(output),
            "plan_id": plan["plan_id"],
            "plan_digest": plan["plan_digest"],
            "nodes": len(plan["nodes"]),
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
