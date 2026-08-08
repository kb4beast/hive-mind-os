"""Fail-closed local measurement packets for the post-migration kernel.

The packet deliberately reports only deterministic local evidence.  It is not a
release attestation, a production certificate, or a comparative-quality verdict.
"""

from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
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


def _load_object(path: str | Path, label: str) -> dict[str, object]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LocalAssuranceError(f"cannot read {label}: {type(error).__name__}") from None
    if not isinstance(document, dict):
        raise LocalAssuranceError(f"{label} must be a JSON object")
    return document


def _relative_artifact(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise LocalAssuranceError(f"{label} path is required")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise LocalAssuranceError(f"{label} path must be relative and confined")
    path = (root / candidate).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        raise LocalAssuranceError(f"{label} path must be relative and confined") from None
    if path.is_symlink() or not path.is_file():
        raise LocalAssuranceError(f"{label} artifact is unavailable")
    return path


def _file_digest(path: Path) -> str:
    return "sha256:" + sha256(path.read_bytes()).hexdigest()


def verify_local_assurance_artifact(
    report_path: str | Path, receipt_manifest_path: str | Path
) -> dict[str, object]:
    """Verify an assurance report and every receipt transcript it references.

    The manifest intentionally carries commands and interpreter labels for reproduction,
    while the report binds only their content digests. Both are required: a digest without
    its retained bytes is not accepted as Phase 12 local evidence.
    """

    report = _load_object(report_path, "assurance report")
    claimed_digest = _digest(report.pop("report_digest", None), "assurance report digest")
    if canonical_digest(report) != claimed_digest:
        raise LocalAssuranceError("assurance report digest does not match its content")
    routes = report.get("phase11_routes")
    benchmark = report.get("benchmark")
    receipts = report.get("test_receipts")
    if not isinstance(routes, list) or not isinstance(benchmark, Mapping) or not isinstance(receipts, list):
        raise LocalAssuranceError("assurance report has malformed bindings")
    rebuilt = build_local_assurance_report(
        candidate_commit=_sha(report.get("candidate_commit"), "candidate commit"),
        candidate_tree=_sha(report.get("candidate_tree"), "candidate tree"),
        phase11_routes=tuple(route for route in routes if isinstance(route, Mapping)),
        benchmark_report=benchmark,
        test_receipts=tuple(receipt for receipt in receipts if isinstance(receipt, Mapping)),
    )
    if rebuilt != {**report, "report_digest": claimed_digest}:
        raise LocalAssuranceError("assurance report does not match its fail-closed reconstruction")

    manifest_path = Path(receipt_manifest_path)
    manifest = _load_object(manifest_path, "receipt manifest")
    if manifest.get("schema_version") != 1:
        raise LocalAssuranceError("unsupported receipt manifest schema")
    for name in ("candidate_commit", "candidate_tree"):
        if manifest.get(name) != report.get(name):
            raise LocalAssuranceError(f"receipt manifest {name} does not match assurance report")
    if manifest.get("report_digest") != claimed_digest:
        raise LocalAssuranceError("receipt manifest does not bind the assurance report")
    manifest_receipts = manifest.get("receipts")
    if not isinstance(manifest_receipts, list):
        raise LocalAssuranceError("receipt manifest receipts are required")
    expected_receipts = {
        receipt["name"]: receipt["digest"]
        for receipt in receipts
        if isinstance(receipt.get("name"), str) and isinstance(receipt.get("digest"), str)
    }
    observed_receipts: dict[str, str] = {}
    root = manifest_path.resolve().parent
    for receipt in manifest_receipts:
        if not isinstance(receipt, Mapping):
            raise LocalAssuranceError("receipt manifest entry is malformed")
        name = receipt.get("name")
        command = receipt.get("command")
        interpreter = receipt.get("interpreter")
        if not isinstance(name, str) or not name or name in observed_receipts:
            raise LocalAssuranceError("receipt manifest names must be unique")
        if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
            raise LocalAssuranceError("receipt manifest command is required")
        if not isinstance(interpreter, str) or not interpreter:
            raise LocalAssuranceError("receipt manifest interpreter is required")
        transcript = _relative_artifact(root, receipt.get("transcript_path"), "receipt transcript")
        actual = _file_digest(transcript)
        if actual != _digest(receipt.get("digest"), "receipt transcript digest"):
            raise LocalAssuranceError("receipt transcript digest does not match its content")
        observed_receipts[name] = actual
    if observed_receipts != expected_receipts:
        raise LocalAssuranceError("receipt manifest does not match assurance receipt bindings")

    benchmark_manifest = manifest.get("benchmark_summary")
    if not isinstance(benchmark_manifest, Mapping):
        raise LocalAssuranceError("benchmark summary binding is required")
    summary_path = _relative_artifact(root, benchmark_manifest.get("path"), "benchmark summary")
    if _file_digest(summary_path) != _digest(benchmark_manifest.get("digest"), "benchmark summary digest"):
        raise LocalAssuranceError("benchmark summary digest does not match its content")
    summary = _load_object(summary_path, "benchmark summary")
    benchmark_keys = ("run_id", "code_digest", "corpus_digest", "harness_digest", "results_digest", "lane_digests", "verdict")
    if {key: summary.get(key) for key in benchmark_keys} != benchmark:
        raise LocalAssuranceError("benchmark summary does not match assurance measurement")
    return {**report, "report_digest": claimed_digest}
