#!/usr/bin/env python3
"""Deterministically materialize the Appeals-Judge-authorized GCO DAG."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from specs import SPECS, VECTOR_DIGEST

DAG_DIR = "docs/execution/dags/git-commit-observation-v1"
OUTPUT_PATH = ".autopilot/state/git-commit-observation-v1.json"
COMMON_FORBIDDEN = [
    ".autopilot/plan.json",
    ".autopilot/control-plane.json",
    ".autopilot/state/**",
    ".autopilot/tests/**",
    ".autopilot/bin/sealed_recovery.py",
    ".autopilot/bin/release_barrier.py",
    "src/**",
    ".github/**",
    "docs/execution/dags/knowledge-projection-v1/**",
    "docs/plan/knowledge-projection-tournament-2026-08-13/**",
    "docs/execution/dags/doctor-performance-v1/**",
    "docs/architecture/ADR-063-INVOCATION-SCOPED-TEST-FIXTURES.md",
    "evidence/performance/doctor-performance-v1/**",
    "evidence/courts/CASE-BASELINE-000-DOCTOR-PERFORMANCE.json",
    "evidence/courts/CASE-DOCTOR-PERFORMANCE-PROMOTION.json",
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
        other_node_scopes = sorted(
            {
                scope
                for owner, scopes in write_scopes.items()
                if owner != item["id"]
                for scope in scopes
            }
        )
        item["forbidden_scope"] = list(
            dict.fromkeys([*COMMON_FORBIDDEN, *other_node_scopes])
        )
        item["file_locks"] = list(item["write_scope"])
        item["downstream_unlock_value"] = item["critical_path_importance"]
        item["contract_digest"] = digest(item)
        nodes.append(item)

    plan: dict[str, Any] = {
        "schema_version": 1,
        "kind": "hive-mind-git-commit-observation-plan-v1",
        "plan_id": "git-commit-observation-v1",
        "title": "Invocation-local immutable Git commit observation challenger",
        "subject": (
            "Evaluate a separately governed challenger that replaces repeated unsafe commit "
            "fact reads in exercised diagnostic and pure receipt-validation paths with one "
            "bounded, fail-closed, invocation-local raw commit observation."
        ),
        "baseline": {
            "planning_commit": "61f31cbbee36471ce6e5f0ad7b94db81ad33e9bb",
            "planning_tree": "8713db647ad2843a336a2f0c6781ebf8161ee47a",
            "retrieved_at": "2026-08-13",
            "rejected_candidate_commit": "41950b74bdec2b6e1c48ee7f5ef3ce947d0c8378",
            "rejected_candidate_tree": "b02326bf108de2fbaa2f174975f937979c02bf90",
            "rejected_candidate_disposition": "reject",
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
            "opening_court": "evidence/courts/CASE-GIT-COMMIT-OBSERVATION-OPENING.json",
            "appeal_source": "evidence/courts/CASE-DOCTOR-PERFORMANCE-PROMOTION.json",
            "proposed_adr": "docs/architecture/ADR-064-ONE-SHOT-RAW-GIT-COMMIT-OBSERVATIONS.md",
        },
        "current_state": {
            "planning": "complete",
            "implementation": "not_started",
            "appeal_authority": "court-opening-and-this-sealed-DAG-only",
            "generic_git_cache": "forbidden",
            "superiority_claim": "forbidden",
            "knowledge_baseline_retry": "not_authorized",
        },
        "execution": {
            "max_sessions": 4,
            "generate": f"python {DAG_DIR}/generate_plan.py --output {OUTPUT_PATH}",
            "lint": (
                "python .autopilot/bin/autopilot.py --repo-root . dag-lint "
                f"--plan {OUTPUT_PATH} --strict --json"
            ),
            "rounds": (
                "python .autopilot/bin/autopilot.py --repo-root . dag-rounds "
                f"--plan {OUTPUT_PATH} --max-sessions 4 "
                "--actor codex:git-commit-observation --json"
            ),
            "rules": [
                "one node branch and one retained unsquashed integration commit per node",
                "workers never mutate main, protected remotes, sealed plans, or predecessor DAGs",
                "only GCO-BASELINE-010 and GCO-TEST-020 share a dispatch round",
                "the single Integrator validates exactly once after each integrated round",
                "workers run focused required_tests; repository-wide suites run only at the conditional qualification gate and round integration",
                "no rebase, squash, amend, force-push, scope widening, hidden cache, or external effect",
            ],
        },
        "invariants": [
            "GitCommitObservation is private, immutable, invocation-local, finite, non-serializable, non-retained, and destroyed before effect-adjacent decisions.",
            "One git cat-file --batch process reads full validated commit OIDs linewise with replacement disabled and exact count/order/type/size/body/terminator/hash/grammar validation.",
            "Repository root, absolute Git directory, common directory, object format, and permitted object store are bound; shallow, graft, promisor, replace, and alternate configurations fail closed unless separately proven safe.",
            "No diff or ancestry batching, ambient replacement of existing Git helpers, generic cache, ref/HEAD/negative/ancestry cache, persistent state, shared daemon, or cross-instance/invocation reuse is allowed.",
            "Before and after claims, completion, retirement, repair, fetch, push, update-ref, CAS, compensation, or publication, mutable state and authority are freshly read without the observation and existing CAS/force-with-lease remains authoritative.",
            "sealed_recovery.py and release_barrier.py never consume the observation and remain unchanged.",
            "The exact doctor command, 180-second timeout, frozen test behavior, and complete vector remain unchanged.",
            f"The complete unittest ID set remains {VECTOR_DIGEST}; 381 executions equal 380 pass plus the same conditional skip, with zero failures and errors.",
            "Qualification uses one fresh smoke per pinned runtime; only two passing sub-180-second smokes permit at least six fresh cold-first alternating trials per runtime, all passing below 180 seconds with nearest-rank p95 at most 135 seconds.",
            "The baseline and rejected fixture candidate remain pinned adverse comparators; no evidence is rewritten, discarded, or reused as a fresh trial.",
            "No generic caching, automatic promotion, superiority, remote-effect, or knowledge BASELINE-000 retry authority is created.",
            "Only a distinct GCO-JUDGE-090 ADOPT verdict with zero unresolved findings may authorize this narrowly bounded candidate.",
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
