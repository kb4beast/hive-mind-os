#!/usr/bin/env python3
"""Verify and optionally materialize the knowledge-projection DAG."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from generate_plan import OUTPUT_PATH, build_plan, digest

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
MANIFEST_PATH = HERE / "manifest.json"
EXPECTED_BUNDLE_SOURCES = (
    "docs/plan/knowledge-projection-tournament-2026-08-13/README.md",
    "docs/plan/knowledge-projection-tournament-2026-08-13/USER_OBJECTIVE.md",
    "docs/plan/knowledge-projection-tournament-2026-08-13/SOURCE_REGISTER.md",
    "docs/plan/knowledge-projection-tournament-2026-08-13/TOURNAMENT_RESULTS.json",
    "docs/plan/knowledge-projection-tournament-2026-08-13/ARCHITECTURE_DECISION.md",
    "docs/plan/knowledge-projection-tournament-2026-08-13/IMPLEMENTATION_PROGRAM.md",
    "docs/plan/knowledge-projection-tournament-2026-08-13/DAG.md",
    "docs/execution/dags/knowledge-projection-v1/README.md",
)


class VerificationError(RuntimeError):
    """The checked-in DAG sources or generated plan are inconsistent."""


def git_blob_sha(path: Path) -> str:
    body = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(body)).encode("ascii") + b"\0" + body
    ).hexdigest()


def load_manifest() -> dict[str, Any]:
    value = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise VerificationError("manifest must be an object")
    return value


def verify() -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = load_manifest()
    if manifest.get("schema_version") != 1:
        raise VerificationError("unsupported manifest version")
    if manifest.get("plan_id") != "knowledge-projection-v1":
        raise VerificationError("unexpected plan id")

    sources = manifest.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise VerificationError("source inventory is missing")
    for name, expected in sorted(sources.items()):
        if not isinstance(name, str) or not isinstance(expected, str):
            raise VerificationError("source inventory is malformed")
        observed = git_blob_sha(HERE / name)
        if observed != expected:
            raise VerificationError(
                f"source {name} mismatch: expected {expected}, observed {observed}"
            )

    bundle_sources = manifest.get("bundle_sources")
    if not isinstance(bundle_sources, dict):
        raise VerificationError("tournament bundle inventory is missing")
    if set(bundle_sources) != set(EXPECTED_BUNDLE_SOURCES):
        missing = sorted(set(EXPECTED_BUNDLE_SOURCES) - set(bundle_sources))
        extra = sorted(set(bundle_sources) - set(EXPECTED_BUNDLE_SOURCES))
        raise VerificationError(
            f"tournament bundle inventory mismatch: missing={missing}, extra={extra}"
        )
    for path, expected in sorted(bundle_sources.items()):
        if not isinstance(path, str) or not isinstance(expected, str):
            raise VerificationError("tournament bundle inventory is malformed")
        observed = git_blob_sha(REPO_ROOT / path)
        if observed != expected:
            raise VerificationError(
                f"bundle source {path} mismatch: expected {expected}, observed {observed}"
            )

    standard = manifest.get("standard")
    if not isinstance(standard, dict):
        raise VerificationError("authoring-standard binding is missing")
    path = standard.get("path")
    expected_standard = standard.get("git_blob_sha")
    if not isinstance(path, str) or not isinstance(expected_standard, str):
        raise VerificationError("authoring-standard binding is malformed")
    observed_standard = git_blob_sha(REPO_ROOT / path)
    if observed_standard != expected_standard:
        raise VerificationError(
            "authoring-standard mismatch: "
            f"expected {expected_standard}, observed {observed_standard}"
        )

    plan = build_plan()
    if plan.get("plan_digest") != manifest.get("expected_plan_digest"):
        raise VerificationError(
            "generated plan digest mismatch: "
            f"expected {manifest.get('expected_plan_digest')}, "
            f"observed {plan.get('plan_digest')}"
        )
    nodes = plan.get("nodes")
    if not isinstance(nodes, list):
        raise VerificationError("generated nodes are missing")
    ids = [item.get("id") for item in nodes if isinstance(item, dict)]
    if ids != manifest.get("expected_node_ids"):
        raise VerificationError("generated node order mismatch")
    if len(nodes) != manifest.get("expected_node_count") or len(set(ids)) != len(ids):
        raise VerificationError("generated node count or uniqueness mismatch")
    for item in nodes:
        if not isinstance(item, dict):
            raise VerificationError("generated node must be an object")
        expected = item.get("contract_digest")
        material = dict(item)
        material.pop("contract_digest", None)
        if expected != digest(material):
            raise VerificationError(f"node {item.get('id')} contract digest mismatch")

    sealed_plan = REPO_ROOT / str(manifest.get("sealed_plan_unchanged"))
    if not sealed_plan.is_file():
        raise VerificationError("sealed .autopilot/plan.json is missing")
    baseline_bytes = manifest.get("sealed_plan_sha256")
    observed_bytes = "sha256:" + hashlib.sha256(sealed_plan.read_bytes()).hexdigest()
    if observed_bytes != baseline_bytes:
        raise VerificationError(
            f"sealed plan bytes changed: expected {baseline_bytes}, observed {observed_bytes}"
        )
    return manifest, plan


def render(plan: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            plan,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    manifest, plan = verify()
    output = REPO_ROOT / OUTPUT_PATH
    if args.write:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(render(plan))
    print(
        json.dumps(
            {
                "verified": True,
                "plan_id": plan["plan_id"],
                "plan_digest": plan["plan_digest"],
                "node_count": len(plan["nodes"]),
                "materialized": str(output) if args.write else None,
                "baseline_commit": manifest["baseline_commit"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerificationError as error:
        print(json.dumps({"verified": False, "error": str(error)}, sort_keys=True))
        raise SystemExit(2) from None
