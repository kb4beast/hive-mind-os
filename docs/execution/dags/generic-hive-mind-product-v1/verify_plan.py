#!/usr/bin/env python3
"""Verify and optionally materialize the sealed generic-product overlay DAG."""

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


class OverlayVerificationError(RuntimeError):
    """The checked-in overlay sources or generated plan are inconsistent."""


def git_blob_sha(path: Path) -> str:
    body = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(body)).encode("ascii") + b"\0" + body
    ).hexdigest()


def load_manifest() -> dict[str, Any]:
    value = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise OverlayVerificationError("overlay manifest must be an object")
    return value


def verify() -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = load_manifest()
    if manifest.get("schema_version") != 1:
        raise OverlayVerificationError("unsupported overlay manifest version")
    if manifest.get("plan_id") != "generic-hive-mind-product-v1":
        raise OverlayVerificationError("unexpected overlay plan id")

    sources = manifest.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise OverlayVerificationError("overlay source inventory is missing")
    for name, expected in sorted(sources.items()):
        if not isinstance(name, str) or not isinstance(expected, str):
            raise OverlayVerificationError("overlay source inventory is malformed")
        observed = git_blob_sha(HERE / name)
        if observed != expected:
            raise OverlayVerificationError(
                f"overlay source {name} mismatch: expected {expected}, observed {observed}"
            )

    standard = manifest.get("standard")
    if not isinstance(standard, dict):
        raise OverlayVerificationError("authoring-standard binding is missing")
    standard_path = standard.get("path")
    expected_standard_blob = standard.get("git_blob_sha")
    if not isinstance(standard_path, str) or not isinstance(
        expected_standard_blob, str
    ):
        raise OverlayVerificationError("authoring-standard binding is malformed")
    observed_standard_blob = git_blob_sha(REPO_ROOT / standard_path)
    if observed_standard_blob != expected_standard_blob:
        raise OverlayVerificationError(
            "authoring-standard bytes mismatch: "
            f"expected {expected_standard_blob}, observed {observed_standard_blob}"
        )

    plan = build_plan()
    expected_digest = manifest.get("expected_plan_digest")
    if plan.get("plan_digest") != expected_digest:
        raise OverlayVerificationError(
            "generated plan digest mismatch: "
            f"expected {expected_digest}, observed {plan.get('plan_digest')}"
        )
    nodes = plan.get("nodes")
    if not isinstance(nodes, list):
        raise OverlayVerificationError("generated plan nodes are missing")
    observed_ids = [node.get("id") for node in nodes if isinstance(node, dict)]
    expected_ids = manifest.get("expected_node_ids")
    if observed_ids != expected_ids:
        raise OverlayVerificationError(
            f"generated node order mismatch: expected {expected_ids}, observed {observed_ids}"
        )
    if len(nodes) != manifest.get("expected_node_count"):
        raise OverlayVerificationError("generated node count mismatch")
    if len(set(observed_ids)) != len(observed_ids):
        raise OverlayVerificationError("generated node ids are not unique")

    for node in nodes:
        if not isinstance(node, dict):
            raise OverlayVerificationError("generated node must be an object")
        expected = node.get("contract_digest")
        material = dict(node)
        material.pop("contract_digest", None)
        observed = digest(material)
        if expected != observed:
            raise OverlayVerificationError(
                f"node {node.get('id')} contract digest mismatch"
            )

    sealed = REPO_ROOT / str(manifest.get("sealed_plan_unchanged"))
    if not sealed.is_file():
        raise OverlayVerificationError("sealed .autopilot/plan.json is missing")
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
    parser.add_argument(
        "--write",
        action="store_true",
        help="Materialize the verified plan under ignored .autopilot/state/.",
    )
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
    except OverlayVerificationError as error:
        print(json.dumps({"verified": False, "error": str(error)}, sort_keys=True))
        raise SystemExit(2) from None
