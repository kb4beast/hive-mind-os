#!/usr/bin/env python3
"""Materialize the sealed knowledge-projection implementation DAG."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from specs import SPECS

DAG_DIR = "docs/execution/dags/knowledge-projection-v1"
PLAN_BUNDLE = "docs/plan/knowledge-projection-tournament-2026-08-13"
OUTPUT_PATH = ".autopilot/state/knowledge-projection-v1.json"
GENERATOR_COMMAND = f"python {DAG_DIR}/generate_plan.py --output {OUTPUT_PATH}"
LINT_COMMAND = (
    "python .autopilot/bin/autopilot.py --repo-root . dag-lint "
    f"--plan {OUTPUT_PATH} --strict --json"
)
COMMON_FORBIDDEN = [
    ".autopilot/plan.json",
    ".autopilot/control-plane.json",
    f"{DAG_DIR}/**",
    f"{PLAN_BUNDLE}/**",
    ".github/CODEOWNERS",
    ".github/governance/**",
    "pyproject.toml",
    "docs/architecture/HARDENED_VISION_CONTRACT.md",
    "refs/heads/main",
    "refs/remotes/origin/main",
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
    nodes: list[dict[str, Any]] = []
    write_scopes = {
        str(spec["id"]): list(spec["write_scope"])
        for spec in SPECS
    }
    for spec in SPECS:
        item = dict(spec)
        item["downstream_unlock_value"] = item["critical_path_importance"]
        item["file_locks"] = list(item["write_scope"])
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
        item["stopping_condition"] = (
            "Stop after every focused test and acceptance criterion passes on one "
            "immutable candidate, independent review has no material unresolved "
            "finding, receipts are retained, the claim is settled, and changed "
            "paths exactly match write_scope."
        )
        item["rollback"] = (
            "Revert only this node's retained integration commit; preserve ancestry, "
            "private canonical history, receipts, conflicts, dissent, adverse evidence, "
            "and tombstones. Disable the node's new version or adapter before rebuilding "
            "derived projections."
        )
        item["contract_digest"] = digest(item)
        nodes.append(item)

    plan: dict[str, Any] = {
        "schema_version": 1,
        "kind": "hive-mind-knowledge-projection-plan-v1",
        "plan_id": "knowledge-projection-v1",
        "title": "Private Knowledge Graph and Safe Shared Learning",
        "subject": (
            "Repository-neutral append-only knowledge, generated private Obsidian-compatible "
            "views, immutable repeatable idea passes and backward reasons, complete role/court/"
            "champion/challenger traceability, and independently gated sanitized shared learning."
        ),
        "baseline": {
            "repository": "https://github.com/kb4beast/hive-mind-os.git",
            "branch": "main",
            "commit": "a93df2632f259f4b63f7a4f27eb0b163b5a47204",
            "tree": "a9ba24f17974b1992298f3bc9a85e8f878b7bc5d",
            "retrieved_at": "2026-08-13",
        },
        "standard": {
            "path": "docs/execution/DAG_AUTHORING_STANDARD.md",
            "source_commit": "a93df2632f259f4b63f7a4f27eb0b163b5a47204",
            "git_blob_sha": "70e43b0a8078a303d44c0109b8dd218a948258c2",
        },
        "source": {
            "tournament_bundle": PLAN_BUNDLE,
            "directory": DAG_DIR,
            "generator": f"{DAG_DIR}/generate_plan.py",
            "specifications": [f"{DAG_DIR}/specs.py"],
        },
        "current_state": {
            "planning": "complete",
            "implementation": "not_started",
            "private_projection": "not_started",
            "offline_release_bundle": "not_started",
            "local_shared_registry": "not_started",
            "remote_shared_publication": "quarantined",
            "automatic_shared_lesson_activation": "quarantined",
        },
        "execution": {
            "max_sessions": 8,
            "generate": GENERATOR_COMMAND,
            "lint": LINT_COMMAND,
            "rounds": (
                "python .autopilot/bin/autopilot.py --repo-root . dag-rounds "
                f"--plan {OUTPUT_PATH} --max-sessions 8 "
                "--actor codex:knowledge-projection --json"
            ),
            "rules": [
                "one branch, worktree, claim, and immutable candidate per node",
                "workers never mutate main, the integration target, the DAG, or the sealed plan",
                "one integrator merges a conflict-free round in declared order and validates once",
                "no rebase, squash, amend, force-push, hidden scope widening, or auto-merge",
                "focused worker tests and one repository-wide validation per integrated round",
            ],
        },
        "invariants": [
            "Obsidian, Markdown, Bases, Canvas, dashboards, indices, and caches are rebuildable non-authoritative views.",
            "Private logical coverage excludes raw secrets, credentials, hidden reasoning, raw transcripts, and unbounded bodies.",
            "One stable idea may have unbounded immutable successor passes; the execution dependency graph remains acyclic.",
            "No role writes directly to generated notes and no generated note grants authority or becomes new evidence.",
            "Shared records are newly composed allowlisted abstractions, never redacted copies of private objects.",
            "Append-only metadata and deletion receipts do not force retention of credentials, customer data, or legally erasable protected bodies.",
            "Named Obsidian compatibility claims require retained current official-source evidence; otherwise the product claim narrows to generic Markdown, YAML, and JSON.",
            "Before the exact release court, release and registry work uses only synthetic, independently reviewed, license-clean fixtures.",
            "Remote publication, watcher, bidirectional Inbox, and automatic shared-lesson activation remain outside this plan.",
            "Missing or ambiguous authority, identity, classification, license, provenance, de-identification, evidence, or rollback fails closed.",
            "Every role, court seat, gate return, dissent, losing idea, challenger, negative result, and later appeal remains attributable.",
            "Never edit .autopilot/plan.json or reinterpret its historical receipts.",
        ],
        "nodes": nodes,
    }
    plan["plan_digest"] = digest(plan)
    return plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=OUTPUT_PATH)
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()
    plan = build_plan()
    body = json.dumps(
        plan,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ) + "\n"
    if args.stdout:
        print(body, end="")
    else:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(body.encode("utf-8"))
        print(
            json.dumps(
                {
                    "output": str(output),
                    "plan_id": plan["plan_id"],
                    "plan_digest": plan["plan_digest"],
                    "nodes": len(plan["nodes"]),
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
