#!/usr/bin/env python3
"""Materialize the generic Hive Mind OS product-completion DAG.

This is an additive overlay. It never reads, replaces, or edits
``.autopilot/plan.json``. The output is deterministic canonical JSON that can be
passed directly to ``autopilot dag-lint`` and ``autopilot dag-rounds``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from specs_a import SPECS as SPECS_A
from specs_b import SPECS as SPECS_B

DAG_DIR = "docs/execution/dags/generic-hive-mind-product-v1"
OUTPUT_PATH = ".autopilot/state/generic-hive-mind-product-v1.json"
GENERATOR_COMMAND = (
    f"python {DAG_DIR}/generate_plan.py --output {OUTPUT_PATH}"
)
LINT_COMMAND = (
    "python .autopilot/bin/autopilot.py --repo-root . dag-lint "
    f"--plan {OUTPUT_PATH} --strict --json"
)
COMMON_FORBIDDEN = [
    ".autopilot/plan.json",
    f"{DAG_DIR}/**",
    ".github/CODEOWNERS",
    ".github/governance/**",
    "docs/architecture/HARDENED_VISION_CONTRACT.md",
]


def digest(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def build_plan() -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    for spec in (*SPECS_A, *SPECS_B):
        node = dict(spec)
        node["downstream_unlock_value"] = node["critical_path_importance"]
        node["file_locks"] = list(node["write_scope"])
        node["forbidden_scope"] = list(COMMON_FORBIDDEN)
        node["stopping_condition"] = (
            "Stop after the focused tests and every criterion pass on one immutable "
            "candidate, independent review has no material unresolved finding, the "
            "receipt is published, the claim is settled, and no out-of-scope path changed."
        )
        node["rollback"] = (
            "Revert only this node's integration commit; preserve ancestry, receipts, "
            "adverse evidence, and the sealed v1 plan."
        )
        if node["id"] == "BASELINE-000":
            node["required_tests"] = [
                GENERATOR_COMMAND,
                LINT_COMMAND,
                "python .autopilot/bin/autopilot.py --repo-root . doctor --json",
            ]
        elif node["id"] == "HANDOFF-700":
            node["required_tests"] = [
                GENERATOR_COMMAND,
                LINT_COMMAND,
                "python -m unittest discover -s tests -v",
            ]
        node["contract_digest"] = digest(node)
        nodes.append(node)

    plan: dict[str, Any] = {
        "schema_version": 1,
        "kind": "hive-mind-generic-product-overlay-v1",
        "plan_id": "generic-hive-mind-product-v1",
        "title": "Generic Hive Mind OS DAG Builder, Executor, and Token Economy",
        "baseline": {
            "repository": "kb4beast/hive-mind-os",
            "pr": 144,
            "branch": "release/hive-mind-os-singleton-20260812-r5",
            "parent_commit": "cc349bef0aad0f288ba7db6ee7ffd4ea911906fb",
        },
        "standard": {
            "path": "docs/execution/DAG_AUTHORING_STANDARD.md",
            "source_commit": "cc349bef0aad0f288ba7db6ee7ffd4ea911906fb",
            "git_blob_sha": "70e43b0a8078a303d44c0109b8dd218a948258c2",
        },
        "source": {
            "directory": DAG_DIR,
            "generator": f"{DAG_DIR}/generate_plan.py",
            "specifications": [f"{DAG_DIR}/specs_a.py", f"{DAG_DIR}/specs_b.py"],
        },
        "execution": {
            "max_sessions": 8,
            "generate": GENERATOR_COMMAND,
            "lint": LINT_COMMAND,
            "rounds": (
                "python .autopilot/bin/autopilot.py --repo-root . dag-rounds "
                f"--plan {OUTPUT_PATH} --max-sessions 8 "
                "--actor codex:generic-product --json"
            ),
            "mode": (
                "Codex parent consumes rounds JSON until PUBLIC-RUNTIME-500 provides "
                "product-native external-plan execution."
            ),
            "rules": [
                "one branch/worktree/claim per node",
                "workers never mutate target",
                "integrator merges sealed candidates in compiled order and advances target once",
                "no rebase/squash/force/auto-merge",
                "focused worker tests; one integrated full validation per round",
            ],
        },
        "invariants": [
            "Never edit .autopilot/plan.json or invalidate existing receipts.",
            "Never undo code already implemented on PR #144.",
            "Never edit the overlay DAG from a worker node.",
            "Settle mutated claims before expiry; sealed candidates survive long verification.",
            "Deterministic operations do not consume model calls; model context is direct-dependency and budgeted.",
        ],
        "nodes": nodes,
    }
    plan["plan_digest"] = digest(plan)
    return plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=OUTPUT_PATH,
        help="Output path for the materialized plan.",
    )
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()

    plan = build_plan()
    rendered = json.dumps(
        plan,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ) + "\n"
    if args.stdout:
        print(rendered, end="")
    else:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(rendered.encode("utf-8"))
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
