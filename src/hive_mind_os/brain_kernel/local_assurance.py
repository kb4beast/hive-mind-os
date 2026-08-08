"""Fail-closed local measurement packets for the post-migration kernel.

The packet deliberately reports only deterministic local evidence.  It is not a
release attestation, a production certificate, or a comparative-quality verdict.
"""

from __future__ import annotations

import re
from typing import Mapping, Sequence

from .canonical import canonical_digest

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_REQUIRED_RECEIPTS = frozenset(
    {"phase11-parity", "phase11-rollback", "security-regression", "recovery-regression"}
)


class LocalAssuranceError(ValueError):
    """A local assurance packet lacks a binding or attempts promotion."""


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise LocalAssuranceError(f"{label} must be a lowercase 40-hex digest")
    return value


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise LocalAssuranceError(f"{label} must be a lowercase sha256 digest")
    return value


def _route_record(value: Mapping[str, object]) -> dict[str, str]:
    route = value.get("route")
    if not isinstance(route, str) or not route:
        raise LocalAssuranceError("Phase 11 route is required")
    return {
        "route": route,
        "manifest_digest": _digest(value.get("manifest_digest"), "Phase 11 manifest digest"),
        "parity_receipt_digest": _digest(
            value.get("parity_receipt_digest"), "Phase 11 parity receipt digest"
        ),
        "rollback_receipt_digest": _digest(
            value.get("rollback_receipt_digest"), "Phase 11 rollback receipt digest"
        ),
    }


def _receipt_records(receipts: Sequence[Mapping[str, object]]) -> tuple[dict[str, str], ...]:
    result: list[dict[str, str]] = []
    names: set[str] = set()
    for receipt in receipts:
        name = receipt.get("name")
        if not isinstance(name, str) or not name:
            raise LocalAssuranceError("test receipt name is required")
        if name in names:
            raise LocalAssuranceError("test receipt names must be unique")
        if receipt.get("status") != "passed":
            raise LocalAssuranceError(f"test receipt {name} did not pass")
        names.add(name)
        result.append({"name": name, "status": "passed", "digest": _digest(receipt.get("digest"), f"test receipt {name} digest")})
    missing = _REQUIRED_RECEIPTS - names
    if missing:
        raise LocalAssuranceError("required receipt is missing: " + ", ".join(sorted(missing)))
    return tuple(sorted(result, key=lambda item: item["name"]))


def _measurement_record(
    value: Mapping[str, object], candidate_commit: str
) -> dict[str, object]:
    if _sha(value.get("code_digest"), "benchmark candidate") != candidate_commit:
        raise LocalAssuranceError("benchmark candidate does not match assurance candidate")
    verdict = value.get("verdict")
    if not isinstance(verdict, Mapping) or verdict.get("disposition") != "measurement-recorded":
        raise LocalAssuranceError("benchmark verdict must remain measurement-recorded")
    judge = verdict.get("judge_id")
    lanes = verdict.get("lane_identities")
    if not isinstance(judge, str) or not judge or not isinstance(lanes, Sequence) or isinstance(lanes, str):
        raise LocalAssuranceError("benchmark judge and lane identities are required")
    lane_identities = tuple(lanes)
    if not all(isinstance(identity, str) and identity for identity in lane_identities):
        raise LocalAssuranceError("benchmark lane identities are invalid")
    if judge in lane_identities or len(set(lane_identities)) != len(lane_identities):
        raise LocalAssuranceError("benchmark judge must be distinct from lanes")
    lane_digests = value.get("lane_digests")
    if not isinstance(lane_digests, Mapping):
        raise LocalAssuranceError("benchmark lane digests are required")
    return {
        "run_id": value.get("run_id"),
        "code_digest": candidate_commit,
        "corpus_digest": _digest(value.get("corpus_digest"), "benchmark corpus digest"),
        "harness_digest": _digest(value.get("harness_digest"), "benchmark harness digest"),
        "results_digest": _digest(value.get("results_digest"), "benchmark results digest"),
        "lane_digests": {str(name): _digest(digest, "benchmark lane digest") for name, digest in sorted(lane_digests.items())},
        "verdict": {
            "disposition": "measurement-recorded",
            "judge_id": judge,
            "lane_identities": list(lane_identities),
        },
    }


def build_local_assurance_report(
    *,
    candidate_commit: str,
    candidate_tree: str,
    phase11_routes: Sequence[Mapping[str, object]],
    benchmark_report: Mapping[str, object],
    test_receipts: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Bind local migration, measurement, security, and recovery evidence.

    Every accepted outcome is intentionally capped below release or superiority.  Any
    absent/malformed binding fails before a packet can be produced.
    """

    commit = _sha(candidate_commit, "candidate commit")
    tree = _sha(candidate_tree, "candidate tree")
    routes = tuple(_route_record(route) for route in phase11_routes)
    if not routes:
        raise LocalAssuranceError("at least one Phase 11 route is required")
    if len({route["route"] for route in routes}) != len(routes):
        raise LocalAssuranceError("Phase 11 routes must be unique")
    report: dict[str, object] = {
        "schema_version": 1,
        "scope": "local-deterministic",
        "candidate_commit": commit,
        "candidate_tree": tree,
        "phase11_routes": list(sorted(routes, key=lambda item: item["route"])),
        "benchmark": _measurement_record(benchmark_report, commit),
        "test_receipts": list(_receipt_records(test_receipts)),
        "release_ready": False,
        "production_ready": False,
        "comparative_claim_authorized": False,
        "signed_attestation_present": False,
        "real_provider_used": False,
    }
    report["report_digest"] = canonical_digest(report)
    return report
