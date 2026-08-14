"""Exact, non-generic recovery primitives for three sealed L2 incidents."""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from controller import FULL_SHA, NodeView, format_time, parse_time
from durable_controller import (
    AutopilotError,
    ClaimError,
    ReceiptError,
    append_jsonl,
    atomic_write_json,
    digest_json,
    read_json,
)

REPAIR_AUTHORITY_DOCUMENT = ".autopilot/sealed-repair-authorities.json"
REPAIR_CLAIM_KIND = "hive-mind-autopilot-sealed-repair-claim-v1"
REPAIR_DOCTOR_KIND = "hive-mind-autopilot-full-doctor-evidence-v1"
REPAIR_DOCTOR_FILE = "sealed-repair-doctor.json"
DIGEST_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
REPAIR_AUTHORITY_MATERIAL_DIGESTS = {
    "OPTIMIZER-370": "sha256:380b642ffbc32892eee60fab8b9a23f3b1fdd9e5c66a5309f97c2d9a842ab4dd",
    "ORCH-300": "sha256:348714232a0be8a82bbf168fa96c55c52a155d4549955b6d8e113abcb26adc9d",
}
SEALED_CAPABILITY_COMMIT = "b8ed8273b8819250a0e7850550d3335e7446d590"
OPTIMIZER_INCIDENT_TREE = "8bfe011cb1ac5cbbc4772d5b77dd981638a38b8d"
OPTIMIZER_CONTINUATION_PATH = ".autopilot/optimizer-370-active-completion-continuation.json"
OPTIMIZER_CONTINUATION_DIGEST = "sha256:4ddac1dd2ec6255ea46ca0a13968c084232a5ffe6438ae4f6e7dd8ba3848642d"
OPTIMIZER_CONTINUATION_CAPABILITY_COMMIT = "0000000000000000000000000000000000000000"
REPAIR_PRIOR_STATES = {
    "OPTIMIZER-370": "PR_OPEN",
    "ORCH-300": "CI_FAILED",
}

BUILDER_COURT_PATH = ".autopilot/builder-330-recovery-court.json"
BUILDER_APPEALS_PATH = ".autopilot/builder-330-recovery-appeals.json"
BUILDER_REPLAN_PATH = ".autopilot/builder-330-recovery-replan.json"
BUILDER_BOOTSTRAP_PATH = ".autopilot/builder-330-recovery-bootstrap.json"
BUILDER_EVIDENCE_PATH = ".autopilot/builder-330-recovery-evidence.json"
BUILDER_EVIDENCE_DIGEST = "sha256:fa08e2cbd40acfe15b6d42c7005348b63b414d586814d8d4257abaffd7c66d06"
BUILDER_DIGESTS = {
    BUILDER_COURT_PATH: "sha256:b3cbb1178dde47c22d365218cc306e6aa31a59af252782a5edf572ab5858e69a",
    BUILDER_APPEALS_PATH: "sha256:52c32912394146f36cfa55e11f5777da9d81b18885059408c4c791d186a54607",
    BUILDER_REPLAN_PATH: "sha256:afeda169e182db86dc8309d08493ce4a00f3ce806c96231be8ca2e18fcb28a13",
}
BUILDER_SUCCESSOR_COURT_PATH = ".autopilot/builder-330-successor-recovery-court.json"
BUILDER_SUCCESSOR_APPEALS_PATH = ".autopilot/builder-330-successor-recovery-appeals.json"
BUILDER_SUCCESSOR_REPLAN_PATH = ".autopilot/builder-330-successor-recovery-replan.json"
BUILDER_SUCCESSOR_BOOTSTRAP_PATH = ".autopilot/builder-330-successor-recovery-bootstrap.json"
BUILDER_SUCCESSOR_EVIDENCE_PATH = ".autopilot/builder-330-successor-recovery-evidence.json"
BUILDER_SUCCESSOR_EVIDENCE_DIGEST = "sha256:4348caec76b78cd13825067b228efa060f3f3f1a79a54fc0630fb701e8c6698f"
BUILDER_SUCCESSOR_DIGESTS = {
    BUILDER_SUCCESSOR_COURT_PATH: "sha256:04d49b160b061f770f320c377505a2a90d8894158bfa5f5fec8bed7aabf03c8d",
    BUILDER_SUCCESSOR_APPEALS_PATH: "sha256:3ddc737ef9556fc79aefec8d2d44ce821bf1984f9bc32c443a2e1a8f159ba1d8",
    BUILDER_SUCCESSOR_REPLAN_PATH: "sha256:3f152fd7d1bcee6fd23f97932ca2b5eba9205ca02da6f64a1a134f7b79f0f4ad",
}
BUILDER_SUCCESSOR_CAPABILITY_COMMIT = "0000000000000000000000000000000000000000"
BUILDER_RECOVERY_ID = "builder-330-r4-foreign-successor-recovery-v2"
BUILDER_EXECUTION_KIND = "hive-mind-autopilot-builder-330-successor-retirement-v2"
BUILDER_CLAIM_KIND = "hive-mind-autopilot-builder-330-successor-claim-v2"
BUILDER_EXECUTION_FILE = "builder-330-successor-retirement-execution.json"
BUILDER_RECOVERY_FILE = "builder-330-successor-retirement-recovery.json"
BUILDER_LEASE_FILE = "builder-330-successor-retirement-lease.json"
BUILDER_INTENT_FILE = "builder-330-successor-retirement-intent.json"
BUILDER_AUDIT_FILE = "builder-330-successor-retirement-audit.jsonl"
ORCH_SUCCESSOR_COURT_PATH = ".autopilot/orch-300-successor-court.json"
ORCH_SUCCESSOR_APPEALS_PATH = ".autopilot/orch-300-successor-appeals.json"
ORCH_SUCCESSOR_REPLAN_PATH = ".autopilot/orch-300-successor-replan.json"
ORCH_SUCCESSOR_EVIDENCE_PATH = ".autopilot/orch-300-successor-evidence.json"
ORCH_SUCCESSOR_BOOTSTRAP_PATH = ".autopilot/orch-300-successor-bootstrap.json"
ORCH_SUCCESSOR_CAPABILITY_COMMIT = "0000000000000000000000000000000000000000"
ORCH_SUCCESSOR_DIGESTS = {
    ORCH_SUCCESSOR_COURT_PATH: "sha256:d27adbf38f7469af9a8af40bdf6b46540e182663750db95fbcc2112c3e023b5f",
    ORCH_SUCCESSOR_APPEALS_PATH: "sha256:04fc994d2199c8f227d43397619d8d547eb372583e6f3eac1546050e28ecf589",
    ORCH_SUCCESSOR_REPLAN_PATH: "sha256:6c94fd20e35169461df80963283d7c0c689f6eb83cda62ea343dc2bffad33fb4",
    ORCH_SUCCESSOR_EVIDENCE_PATH: "sha256:c4aac80029d3c9af47f94746ddec2c3c03b59eb18661f54588b7ee9a75db7511",
}


@dataclass(frozen=True)
class BuilderSuccessorTopology:
    """The single compiled projection of the exact Builder v2 forensic record."""

    branch: str
    source_ref: str
    source_head: str
    source_tree: str
    archive_ref: str
    legacy_archive_ref: str
    preserved_paths: tuple[str, ...]
    old_claim: str
    old_claim_parent: str
    old_claim_tree: str
    old_claim_payload_digest: str
    old_candidate: str
    old_candidate_tree: str
    legacy_merge: str
    legacy_merge_parents: tuple[str, str]
    legacy_merge_tree: str
    foreign_base: str
    foreign_base_parent: str
    foreign_base_tree: str
    repair_claim: str
    repair_claim_parent: str
    repair_claim_tree: str
    repair_claim_payload_digest: str
    candidate: str
    candidate_parent: str
    candidate_tree: str
    receipt: str
    receipt_parent: str
    receipt_tree: str
    receipt_payload_digest: str
    r4_ref: str
    r4_head: str
    r4_head_tree: str
    prior_r4_head: str
    adverse_extension_parent: str
    adverse_extension_paths: tuple[str, ...]
    canonical_receipt_merge: str
    canonical_receipt_merge_parents: tuple[str, str]
    canonical_receipt_merge_tree: str
    other_candidate: str
    other_candidate_parent: str
    other_receipt: str
    other_receipt_digest: str
    other_receipt_merge: str
    other_receipt_merge_parents: tuple[str, str]
    other_receipt_merge_tree: str
    expected_builder_receipts: tuple[str, str]


class SealedRecoveryMixin:
    """Mixin layered above the generic durable/release controller.

    The public entry points accept only a node already present in the sealed registry or,
    for Builder retirement, no caller-selected identity at all.  Generic existing-branch
    claims, duplicate receipts, and branch retirement remain unchanged and fail closed.
    """

    @property
    def repair_authority_path(self) -> Path:
        return self.repo_root / REPAIR_AUTHORITY_DOCUMENT

    def _repair_authority_document(self) -> Mapping[str, Any] | None:
        if not self.repair_authority_path.is_file():
            return None
        value = read_json(self.repair_authority_path)
        return value if isinstance(value, Mapping) else None

    def _repair_records(self) -> dict[str, Mapping[str, Any]]:
        document = self._repair_authority_document()
        if not isinstance(document, Mapping) or document.get("schema_version") != 1:
            return {}
        records = document.get("repair_authorities")
        if not isinstance(records, list):
            return {}
        return {
            str(record.get("node_id")): record
            for record in records
            if isinstance(record, Mapping) and isinstance(record.get("node_id"), str)
        }

    def _repair_record(self, node_id: str) -> Mapping[str, Any]:
        records = self._repair_records()
        if set(records) != set(REPAIR_AUTHORITY_MATERIAL_DIGESTS):
            raise AutopilotError("sealed repair authority registry is incomplete or expanded")
        record = self._effective_repair_record(node_id)
        if record is None:
            raise AutopilotError(f"node {node_id} has no sealed repair authority")
        issues = self._repair_authority_issues(node_id)
        if issues:
            raise AutopilotError("; ".join(issues))
        return record

    def _repair_authority_issues(self, node_id: str) -> tuple[str, ...]:
        """Validate only the authority chain requested by an operational action.

        Aggregate doctor output may report every sealed incident, but a damaged
        Builder record must never disable Optimizer and a damaged ORCH successor
        must never disable either unrelated grant.
        """

        document = self._repair_authority_document()
        rows = document.get("repair_authorities") if isinstance(document, Mapping) else None
        node_ids = [row.get("node_id") for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []
        if (
            not isinstance(document, Mapping)
            or set(document) != {"schema_version", "repair_authorities"}
            or document.get("schema_version") != 1
            or not isinstance(rows, list)
            or len(rows) != 2
            or any(not isinstance(row, Mapping) for row in rows)
            or set(node_ids) != set(REPAIR_AUTHORITY_MATERIAL_DIGESTS)
            or len(node_ids) != len(set(node_ids))
        ):
            return ("sealed repair authority registry envelope is invalid",)
        records = self._repair_records()
        record = records.get(node_id)
        if not isinstance(record, Mapping):
            return (f"{node_id}: sealed repair authority is missing",)
        issues: list[str] = []
        material = dict(record)
        capability = material.pop("capability_commit", None)
        if digest_json(material) != REPAIR_AUTHORITY_MATERIAL_DIGESTS.get(node_id):
            issues.append(f"{node_id}: sealed repair authority material was altered")
        issues.extend(f"{node_id}: {issue}" for issue in self._capability_issues(capability))
        node = super().node(node_id)
        if record.get("branch") != node.get("branch"):
            issues.append(f"{node_id}: sealed repair branch differs from node contract")
        if record.get("contract_version") != node.get("contract_version"):
            issues.append(f"{node_id}: sealed repair contract version differs")
        if record.get("plan_fingerprint") != self.expected_plan_fingerprint:
            issues.append(f"{node_id}: sealed repair plan fingerprint is stale")
        target = self.control.get("target")
        if not isinstance(target, Mapping) or record.get("repository") != target.get("repository"):
            issues.append(f"{node_id}: sealed repair repository identity differs")
        if node_id == "ORCH-300":
            issues.extend(self._orch_successor_record_issues())
        return tuple(dict.fromkeys(issues))

    def _capability_issues(self, capability: object) -> tuple[str, ...]:
        if not isinstance(capability, str) or FULL_SHA.fullmatch(capability) is None:
            return ("sealed recovery capability commit is invalid",)
        if capability != SEALED_CAPABILITY_COMMIT or capability == "0" * 40:
            return ("sealed recovery capability commit is not the exact compiled pin",)
        if self.verify_git_objects and not self.git_object_exists(capability):
            return ("sealed recovery capability commit object is unavailable",)
        return ()

    def _successor_capability_issues(self, capability: object) -> tuple[str, ...]:
        if not isinstance(capability, str) or FULL_SHA.fullmatch(capability) is None:
            return ("Builder successor capability commit is invalid",)
        if capability != BUILDER_SUCCESSOR_CAPABILITY_COMMIT or capability == "0" * 40:
            return ("Builder successor capability commit is not the exact compiled pin",)
        if self.verify_git_objects and not self.git_object_exists(capability):
            return ("Builder successor capability commit object is unavailable",)
        return ()

    def _orch_successor_capability_issues(self, capability: object) -> tuple[str, ...]:
        if not isinstance(capability, str) or FULL_SHA.fullmatch(capability) is None:
            return ("ORCH successor capability commit is invalid",)
        if capability != ORCH_SUCCESSOR_CAPABILITY_COMMIT or capability == "0" * 40:
            return ("ORCH successor capability commit is not the exact compiled pin",)
        if self.verify_git_objects and not self.git_object_exists(capability):
            return ("ORCH successor capability commit object is unavailable",)
        return ()

    def sealed_recovery_issues(self) -> tuple[str, ...]:
        issues: list[str] = []
        document = self._repair_authority_document()
        if not isinstance(document, Mapping) or set(document) != {"schema_version", "repair_authorities"}:
            issues.append("sealed repair authority document shape is invalid")
            return tuple(issues)
        if document.get("schema_version") != 1:
            issues.append("sealed repair authority schema_version is unsupported")
        records = document.get("repair_authorities")
        if not isinstance(records, list) or len(records) != 2:
            issues.append("sealed repair authority document must contain exactly two records")
            return tuple(issues)
        observed: set[str] = set()
        for record in records:
            if not isinstance(record, Mapping):
                issues.append("sealed repair authority entry must be an object")
                continue
            node_id = record.get("node_id")
            if node_id not in REPAIR_AUTHORITY_MATERIAL_DIGESTS or node_id in observed:
                issues.append("sealed repair authority node set is invalid")
                continue
            observed.add(str(node_id))
            material = dict(record)
            capability = material.pop("capability_commit", None)
            if digest_json(material) != REPAIR_AUTHORITY_MATERIAL_DIGESTS[str(node_id)]:
                issues.append(f"{node_id}: sealed repair authority material was altered")
            issues.extend(f"{node_id}: {issue}" for issue in self._capability_issues(capability))
            node = super().node(str(node_id))
            if record.get("branch") != node.get("branch"):
                issues.append(f"{node_id}: sealed repair branch differs from node contract")
            if record.get("contract_version") != node.get("contract_version"):
                issues.append(f"{node_id}: sealed repair contract version differs")
            if record.get("plan_fingerprint") != self.expected_plan_fingerprint:
                issues.append(f"{node_id}: sealed repair plan fingerprint is stale")
            target = self.control.get("target")
            if not isinstance(target, Mapping) or record.get("repository") != target.get("repository"):
                issues.append(f"{node_id}: sealed repair repository identity differs")
            allowed = record.get("allowed_paths")
            expected_paths = sorted(str(path) for path in node.get("write_scope", []))
            if not isinstance(allowed, list) or sorted(allowed) != expected_paths:
                issues.append(f"{node_id}: sealed repair paths differ from exact node scope")
            identities = [
                record.get("advocate_identity"),
                record.get("cross_examiner_identity"),
                record.get("expert_witness_identity"),
                record.get("judge_identity"),
            ]
            if any(not isinstance(item, str) or not item for item in identities) or len(set(identities)) != 4:
                issues.append(f"{node_id}: sealed court identities are missing or not distinct")
            if record.get("decision") != "ADAPT":
                issues.append(f"{node_id}: sealed repair disposition must be ADAPT")
            if record.get("prior_state") != REPAIR_PRIOR_STATES[str(node_id)]:
                issues.append(f"{node_id}: sealed prior state is invalid")
        if observed != set(REPAIR_AUTHORITY_MATERIAL_DIGESTS):
            issues.append("sealed repair authority registry omits an exact incident")
        issues.extend(self._builder_record_issues())
        issues.extend(self._builder_successor_record_issues())
        issues.extend(self._orch_successor_record_issues())
        return tuple(dict.fromkeys(issues))

    def _builder_document(self, relative: str) -> Mapping[str, Any] | None:
        path = self.repo_root / relative
        if not path.is_file():
            return None
        value = read_json(path)
        return value if isinstance(value, Mapping) else None

    def _builder_record_issues(self) -> tuple[str, ...]:
        issues: list[str] = []
        for path, expected in BUILDER_DIGESTS.items():
            value = self._builder_document(path)
            if value is None or digest_json(value) != expected:
                issues.append(f"Builder sealed record differs from {expected}: {path}")
        court = self._builder_document(BUILDER_COURT_PATH) or {}
        appeals = self._builder_document(BUILDER_APPEALS_PATH) or {}
        replan = self._builder_document(BUILDER_REPLAN_PATH) or {}
        bootstrap = self._builder_document(BUILDER_BOOTSTRAP_PATH)
        if not isinstance(bootstrap, Mapping) or set(bootstrap) != {
            "schema_version", "recovery_id", "court_disposition_digest",
            "appeals_ordering_disposition_digest", "replan_digest", "evidence_record_digest",
            "capability_commit",
        }:
            issues.append("Builder recovery bootstrap record shape is invalid")
            bootstrap = {}
        if bootstrap.get("recovery_id") != "builder-330-stale-candidate-recovery-v1":
            issues.append("Builder recovery bootstrap identity is invalid")
        for key, expected in (
            ("court_disposition_digest", BUILDER_DIGESTS[BUILDER_COURT_PATH]),
            ("appeals_ordering_disposition_digest", BUILDER_DIGESTS[BUILDER_APPEALS_PATH]),
            ("replan_digest", BUILDER_DIGESTS[BUILDER_REPLAN_PATH]),
            ("evidence_record_digest", BUILDER_EVIDENCE_DIGEST),
        ):
            if bootstrap.get(key) != expected:
                issues.append(f"Builder recovery bootstrap {key} is invalid")
        issues.extend(self._capability_issues(bootstrap.get("capability_commit")))
        evidence = self._builder_document(BUILDER_EVIDENCE_PATH)
        if evidence is None or digest_json(evidence) != BUILDER_EVIDENCE_DIGEST:
            issues.append("Builder recovery evidence record digest is invalid")
        if appeals.get("court_disposition_digest") != digest_json(court):
            issues.append("Builder Appeals record does not bind the Court record")
        if replan.get("court_disposition_digest") != digest_json(court) or replan.get(
            "appeals_ordering_disposition_digest"
        ) != digest_json(appeals):
            issues.append("Builder replan does not bind Court and Appeals records")
        node = super().node("BUILDER-330")
        if replan.get("branch") != node.get("branch"):
            issues.append("Builder sealed branch differs from node contract")
        if replan.get("plan_fingerprint") != self.expected_plan_fingerprint:
            issues.append("Builder sealed plan fingerprint is stale")
        if sorted(replan.get("preserved_candidate_paths", [])) != sorted(node.get("write_scope", [])):
            issues.append("Builder preserved paths differ from exact node scope")
        return tuple(dict.fromkeys(issues))

    def _builder_successor_record_issues(self) -> tuple[str, ...]:
        issues: list[str] = []
        for path, expected in BUILDER_SUCCESSOR_DIGESTS.items():
            value = self._builder_document(path)
            if value is None or digest_json(value) != expected:
                issues.append(f"Builder successor sealed record differs from {expected}: {path}")
        court = self._builder_document(BUILDER_SUCCESSOR_COURT_PATH) or {}
        appeals = self._builder_document(BUILDER_SUCCESSOR_APPEALS_PATH) or {}
        replan = self._builder_document(BUILDER_SUCCESSOR_REPLAN_PATH) or {}
        evidence = self._builder_document(BUILDER_SUCCESSOR_EVIDENCE_PATH)
        bootstrap = self._builder_document(BUILDER_SUCCESSOR_BOOTSTRAP_PATH)
        required_bootstrap = {
            "schema_version", "recovery_id", "supersedes_recovery_id",
            "supersedes_bootstrap_digest", "court_disposition_digest",
            "appeals_ordering_disposition_digest", "replan_digest",
            "evidence_record_digest", "capability_commit",
        }
        if not isinstance(bootstrap, Mapping) or set(bootstrap) != required_bootstrap:
            issues.append("Builder successor bootstrap record shape is invalid")
            bootstrap = {}
        expected_bootstrap = {
            "recovery_id": BUILDER_RECOVERY_ID,
            "supersedes_recovery_id": "builder-330-stale-candidate-recovery-v1",
            "supersedes_bootstrap_digest": "sha256:40ae612644dbff1fe6323eff5e2f17605cfd9b03ff11b06b27a424b21627f975",
            "court_disposition_digest": BUILDER_SUCCESSOR_DIGESTS[BUILDER_SUCCESSOR_COURT_PATH],
            "appeals_ordering_disposition_digest": BUILDER_SUCCESSOR_DIGESTS[BUILDER_SUCCESSOR_APPEALS_PATH],
            "replan_digest": BUILDER_SUCCESSOR_DIGESTS[BUILDER_SUCCESSOR_REPLAN_PATH],
            "evidence_record_digest": BUILDER_SUCCESSOR_EVIDENCE_DIGEST,
        }
        for key, expected in expected_bootstrap.items():
            if bootstrap.get(key) != expected:
                issues.append(f"Builder successor bootstrap {key} is invalid")
        issues.extend(self._successor_capability_issues(bootstrap.get("capability_commit")))
        if evidence is None or digest_json(evidence) != BUILDER_SUCCESSOR_EVIDENCE_DIGEST:
            issues.append("Builder successor evidence record digest is invalid")
        if appeals.get("court_disposition_digest") != digest_json(court):
            issues.append("Builder successor Appeals record does not bind the Court record")
        if replan.get("court_disposition_digest") != digest_json(court) or replan.get(
            "appeals_ordering_disposition_digest"
        ) != digest_json(appeals):
            issues.append("Builder successor replan does not bind Court and Appeals records")
        supersedes = replan.get("supersedes")
        expected_supersedes = {
            "recovery_id": "builder-330-stale-candidate-recovery-v1",
            "court_digest": BUILDER_DIGESTS[BUILDER_COURT_PATH],
            "appeals_digest": BUILDER_DIGESTS[BUILDER_APPEALS_PATH],
            "replan_digest": BUILDER_DIGESTS[BUILDER_REPLAN_PATH],
            "evidence_digest": BUILDER_EVIDENCE_DIGEST,
            "bootstrap_digest": "sha256:40ae612644dbff1fe6323eff5e2f17605cfd9b03ff11b06b27a424b21627f975",
            "capability_commit": SEALED_CAPABILITY_COMMIT,
            "expected_remote_head": "93a9c46b57fe581216021e791e61403b09494c5f",
        }
        if not isinstance(supersedes, Mapping) or dict(supersedes) != expected_supersedes:
            issues.append("Builder successor does not exactly supersede the v1 authority")
        node = super().node("BUILDER-330")
        if replan.get("branch") != node.get("branch"):
            issues.append("Builder successor branch differs from node contract")
        if replan.get("plan_fingerprint") != self.expected_plan_fingerprint:
            issues.append("Builder successor plan fingerprint is stale")
        if sorted(replan.get("preserved_candidate_paths", [])) != sorted(node.get("write_scope", [])):
            issues.append("Builder successor preserved paths differ from exact node scope")
        if replan.get("expected_remote_head") != "01ee3ec1bd3bfb0bc18bbdea70a428b16b96ee64":
            issues.append("Builder successor canonical head is not exact")
        if replan.get("archive_ref") == replan.get("legacy_archive_ref"):
            issues.append("Builder successor archive must be distinct from the v1 archive")
        aggregate = replan.get("aggregate_quarantine")
        pull = aggregate.get("pull_request") if isinstance(aggregate, Mapping) else None
        if not isinstance(pull, Mapping) or pull.get("number") != 139:
            issues.append("Builder successor aggregate PR quarantine is invalid")
        if isinstance(pull, Mapping) and pull.get("classification") is not None:
            issues.append("Builder successor replan PR schema is expanded")
        identities = [
            court.get("advocate_identity"), court.get("cross_examiner_identity"),
            court.get("expert_witness_identity"), court.get("judge_identity"),
        ]
        if any(not isinstance(value, str) or not value.strip() for value in identities) or len(set(identities)) != 4:
            issues.append("Builder successor court identities are missing or not distinct")
        return tuple(dict.fromkeys(issues))

    def _orch_successor_record_issues(self) -> tuple[str, ...]:
        issues: list[str] = []
        documents: dict[str, Mapping[str, Any]] = {}
        for path, expected in ORCH_SUCCESSOR_DIGESTS.items():
            value = self._builder_document(path)
            if value is None or digest_json(value) != expected:
                issues.append(f"ORCH successor sealed record differs from {expected}: {path}")
            else:
                documents[path] = value
        court = documents.get(ORCH_SUCCESSOR_COURT_PATH, {})
        appeals = documents.get(ORCH_SUCCESSOR_APPEALS_PATH, {})
        replan = documents.get(ORCH_SUCCESSOR_REPLAN_PATH, {})
        evidence = documents.get(ORCH_SUCCESSOR_EVIDENCE_PATH, {})
        bootstrap = self._builder_document(ORCH_SUCCESSOR_BOOTSTRAP_PATH) or {}
        if appeals.get("court_disposition_digest") != digest_json(court):
            issues.append("ORCH successor Appeals does not bind Court")
        if (
            replan.get("court_disposition_digest") != digest_json(court)
            or replan.get("appeals_ordering_disposition_digest") != digest_json(appeals)
        ):
            issues.append("ORCH successor replan does not bind Court and Appeals")
        expected_bootstrap = {
            "schema_version": 1,
            "grant_id": "orch-300-atomic-store-continuation-v2",
            "supersedes_grant_id": "orch-300-continuation-supersession-v1",
            "court_disposition_digest": digest_json(court),
            "appeals_ordering_disposition_digest": digest_json(appeals),
            "replan_digest": digest_json(replan),
            "evidence_digest": digest_json(evidence),
            "capability_commit": ORCH_SUCCESSOR_CAPABILITY_COMMIT,
        }
        if dict(bootstrap) != expected_bootstrap:
            issues.append("ORCH successor bootstrap is incomplete, expanded, or unpinned")
        authority = replan.get("repair_authority") if isinstance(replan, Mapping) else None
        if not isinstance(authority, Mapping):
            issues.append("ORCH successor repair authority is missing")
            authority = {}
        old = self._repair_records().get("ORCH-300")
        if not isinstance(old, Mapping) or digest_json(old) != "sha256:7915508f0450a58960b26e521c5440910ce8fc166a9ceeb50b7a9660365b7c59":
            issues.append("ORCH v1 authority is not preserved byte-for-byte")
        historical = (
            "src/hive_mind_os/brain_kernel/planner.py",
            "tests/test_hive_cortex_orchestrator.py",
        )
        allowed = (
            "src/hive_mind_os/brain_kernel/planner.py",
            "src/hive_mind_os/brain_kernel/store.py",
            "tests/test_brain_kernel_store.py",
            "tests/test_hive_cortex_orchestrator.py",
        )
        if tuple(authority.get("historical_merge_paths", ())) != historical:
            issues.append("ORCH successor historical merge scope is invalid")
        if tuple(authority.get("allowed_paths", ())) != allowed:
            issues.append("ORCH successor final repair scope is invalid")
        if tuple(authority.get("preserved_patch_paths", ())) != historical:
            issues.append("ORCH successor patch artifact paths differ from historical scope")
        expected_patch_evidence = {
            "preserved_patch_artifact": authority.get("preserved_patch_artifact"),
            "preserved_patch_artifact_sha256": authority.get("preserved_patch_artifact_sha256"),
            "preserved_patch_blob_sha1": authority.get("preserved_patch_blob_sha1"),
            "preserved_patch_sha256": authority.get("preserved_patch_sha256"),
            "preserved_patch_byte_length": authority.get("preserved_patch_byte_length"),
            "preserved_patch_base_commit": authority.get("rolled_back_claim"),
            "preserved_patch_remote_head": authority.get("old_receipt_commit"),
            "preserved_patch_checkout_rule": authority.get("preserved_patch_checkout_rule"),
            "preserved_patch_paths": list(historical),
        }
        if any(court.get(key) != value for key, value in expected_patch_evidence.items()):
            issues.append("ORCH successor Court patch evidence differs from runtime authority")
        if authority.get("supersedes_grant_id") != "orch-300-continuation-supersession-v1":
            issues.append("ORCH successor does not retire v1 grant")
        if authority.get("capability_commit") != ORCH_SUCCESSOR_CAPABILITY_COMMIT:
            issues.append("ORCH successor authority capability pin differs")
        issues.extend(self._orch_successor_capability_issues(authority.get("capability_commit")))
        artifact = self.repo_root / str(authority.get("preserved_patch_artifact", ""))
        checkout_rule = authority.get("preserved_patch_checkout_rule")
        attributes_path = self.repo_root / ".gitattributes"
        try:
            attribute_lines = attributes_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            attribute_lines = []
        artifact_mentions = [
            line for line in attribute_lines
            if ".autopilot/evidence/orch-300-v1-preserved-two-file.patch.gz.b64" in line
        ]
        if artifact_mentions != [checkout_rule]:
            issues.append("ORCH successor patch checkout normalization rule is missing or expanded")
        try:
            artifact_bytes = artifact.read_bytes()
            encoded = artifact_bytes.decode("ascii")
            lines = encoded.splitlines()
            if (
                not encoded.endswith("\n") or "\r" in encoded or len(lines) != 197
                or any(len(line) != 76 for line in lines)
                or "sha256:" + hashlib.sha256(artifact_bytes).hexdigest()
                != authority.get("preserved_patch_artifact_sha256")
            ):
                raise ValueError("noncanonical patch wrapper")
            compressed = base64.b64decode("".join(lines), validate=True)
            if base64.encodebytes(compressed).decode("ascii") != encoded:
                raise ValueError("noncanonical patch base64")
            raw = gzip.decompress(compressed)
        except (OSError, UnicodeError, ValueError, gzip.BadGzipFile):
            raw = b""
            issues.append("ORCH successor preserved patch artifact cannot be decoded")
        if len(raw) != authority.get("preserved_patch_byte_length"):
            issues.append("ORCH successor preserved patch byte length differs")
        if "sha256:" + hashlib.sha256(raw).hexdigest() != authority.get("preserved_patch_sha256"):
            issues.append("ORCH successor preserved patch SHA-256 differs")
        blob_sha1 = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
        if blob_sha1 != authority.get("preserved_patch_blob_sha1"):
            issues.append("ORCH successor preserved patch Git blob identity differs")
        try:
            patch_text = raw.decode("utf-8")
        except UnicodeDecodeError:
            patch_text = ""
            issues.append("ORCH successor preserved patch is not canonical UTF-8")
        patch_paths: list[str] = []
        for left, right in re.findall(r"^diff --git a/(.+) b/(.+)$", patch_text, re.MULTILINE):
            if left != right:
                issues.append("ORCH successor preserved patch contains a rename or path mismatch")
            patch_paths.append(left)
        if tuple(sorted(set(patch_paths))) != tuple(sorted(historical)) or len(patch_paths) != len(set(patch_paths)):
            issues.append("ORCH successor preserved patch headers differ from exact historical scope")
        if evidence.get("replan_digest") != digest_json(replan):
            issues.append("ORCH successor evidence does not bind replan")
        rolled_back = authority.get("rolled_back_claim")
        if self.verify_git_objects:
            try:
                self._fetch_exact_orch_successor_objects(authority)
            except (AutopilotError, ClaimError):
                issues.append("ORCH successor exact historical objects cannot be authenticated")
            if not isinstance(rolled_back, str) or not self.git_object_exists(rolled_back):
                issues.append("ORCH successor rolled-back claim object is unavailable")
            elif self._commit_parents(rolled_back) != tuple(authority.get("rolled_back_claim_parents", ())):
                issues.append("ORCH successor rolled-back claim parents differ")
            elif self._commit_tree(rolled_back) != authority.get("rolled_back_claim_tree"):
                issues.append("ORCH successor rolled-back claim tree differs")
            else:
                payload = self._repair_claim_message(rolled_back)
                if not isinstance(payload, Mapping) or digest_json(payload) != authority.get(
                    "rolled_back_claim_payload_digest"
                ):
                    issues.append("ORCH successor rolled-back claim payload differs")
                if self.is_ancestor(rolled_back, self.current_target_sha()):
                    issues.append("ORCH successor execution release contains rolled-back v1 claim")
            if (
                isinstance(rolled_back, str)
                and self.git_object_exists(rolled_back)
                and raw
                and not self._patch_applies_to_commit(
                    rolled_back, raw, tuple(sorted(historical))
                )
            ):
                issues.append("ORCH successor preserved patch does not apply to exact rolled-back claim")
        return tuple(dict.fromkeys(issues))

    def _patch_applies_to_commit(
        self,
        commit: str,
        patch: bytes,
        paths: tuple[str, ...],
    ) -> bool:
        if FULL_SHA.fullmatch(commit) is None or not paths:
            return False
        try:
            executable = self._trusted_tool("git")
            environment = self._sealed_transport_environment(tool="git")
            with tempfile.TemporaryDirectory(prefix="hive-orch-patch-check-") as raw_root:
                root = Path(raw_root)
                for relative in paths:
                    shown = subprocess.run(
                        (executable, "-C", str(self.repo_root), "show", f"{commit}:{relative}"),
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=False,
                        timeout=30,
                        env=environment,
                    )
                    if shown.returncode != 0:
                        return False
                    destination = root / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(shown.stdout)
                checked = subprocess.run(
                    (executable, "apply", "--check", "--whitespace=nowarn", "-"),
                    cwd=root,
                    input=patch,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=30,
                    env=environment,
                )
                return checked.returncode == 0
        except (OSError, subprocess.SubprocessError, AutopilotError):
            return False

    def _effective_repair_record(self, node_id: str) -> Mapping[str, Any] | None:
        if node_id == "OPTIMIZER-370":
            return self._repair_records().get(node_id)
        if node_id != "ORCH-300" or self._orch_successor_record_issues():
            return None
        replan = self._builder_document(ORCH_SUCCESSOR_REPLAN_PATH) or {}
        record = replan.get("repair_authority")
        return record if isinstance(record, Mapping) else None

    @property
    def repair_doctor_path(self) -> Path:
        return self.state_dir / REPAIR_DOCTOR_FILE

    def _doctor_evidence_digest(self) -> str | None:
        if not self.repair_doctor_path.is_file():
            return None
        value = read_json(self.repair_doctor_path)
        required = {
            "schema_version", "kind", "target_sha", "plan_fingerprint",
            "github_snapshot_digest", "reconciliation_digest", "doctor_result_digest",
            "controller_tests_run", "recorded_at",
        }
        if not isinstance(value, Mapping) or set(value) != required:
            return None
        if value.get("schema_version") != 1 or value.get("kind") != REPAIR_DOCTOR_KIND:
            return None
        if value.get("controller_tests_run") is not True:
            return None
        if value.get("target_sha") != self.current_target_sha():
            return None
        if value.get("plan_fingerprint") != self.expected_plan_fingerprint:
            return None
        if value.get("github_snapshot_digest") != self._snapshot_digest():
            return None
        if value.get("reconciliation_digest") != self._reconciliation_digest():
            return None
        return digest_json(value)

    def doctor(self, *, run_controller_tests: bool) -> dict[str, object]:
        result = super().doctor(run_controller_tests=run_controller_tests)
        if result.get("passed") is True and run_controller_tests:
            atomic_write_json(
                self.repair_doctor_path,
                {
                    "schema_version": 1,
                    "kind": REPAIR_DOCTOR_KIND,
                    "target_sha": self.current_target_sha(),
                    "plan_fingerprint": self.expected_plan_fingerprint,
                    "github_snapshot_digest": self._snapshot_digest(),
                    "reconciliation_digest": self._reconciliation_digest(),
                    "doctor_result_digest": digest_json(result),
                    "controller_tests_run": True,
                    "recorded_at": format_time(self.clock()),
                },
            )
            self.after_doctor()
        return result

    def _snapshot_rows(self, key: str, field: str, value: object) -> list[Mapping[str, Any]]:
        rows = self.github_snapshot().get(key, [])
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, Mapping) and row.get(field) == value]

    def _repair_live_issues(self, record: Mapping[str, Any]) -> tuple[str, ...]:
        issues: list[str] = []
        node_id = str(record["node_id"])
        if self.target_requires_reconciliation() or self._reconciliation_digest() is None:
            issues.append("sealed repair requires current singleton reconciliation")
        if self._snapshot_digest() is None:
            issues.append("sealed repair requires a current authenticated GitHub snapshot")
        if self._doctor_evidence_digest() is None:
            issues.append("sealed repair requires a successful current full doctor")
        current = self.current_target_sha()
        incident = str(record["incident_target_sha"])
        capability = str(record["capability_commit"])
        if self.verify_git_objects:
            if not self.is_ancestor(incident, current):
                issues.append("sealed repair current release does not descend from incident target")
            if not self.is_ancestor(capability, current):
                issues.append("sealed repair current release omits capability commit")
            scope_base = str(record.get("claim_target_sha", incident))
            changed = set(self._diff_paths(scope_base, current))
            if changed & set(record["allowed_paths"]):
                issues.append("sealed repair scope changed between incident and execution release")
        prs = self._snapshot_rows("pull_requests", "node_id", node_id)
        if len(prs) != 1:
            issues.append(f"{node_id}: snapshot must contain exactly one node PR")
        else:
            pr = prs[0]
            expected_ci = "failure" if record["prior_state"] == "CI_FAILED" else "success"
            expected = {
                "number": record["pr"],
                "state": "open",
                "merged": False,
                "ci": expected_ci,
                "base": record["pr_base_branch"],
                "head": record["pr_head_branch"],
                "head_sha": record["old_receipt_commit"],
                "draft": record["pr_is_draft"],
                "created_at": record["pr_created_at"],
            }
            for key, expected_value in expected.items():
                if pr.get(key) != expected_value:
                    issues.append(f"{node_id}: snapshot PR {key} is not the sealed value")
        branches = self._snapshot_rows("branches", "name", record["branch"])
        if len(branches) != 1 or branches[0].get("sha") != record["old_receipt_commit"]:
            issues.append(f"{node_id}: snapshot branch head is not the sealed receipt")
        claim = self.active_claims().get(node_id)
        if claim is not None:
            issues.append(f"{node_id}: an active claim already exists")
        for dependency in super().node(node_id).get("dependencies", []):
            if super().node_view(str(dependency)).state != "COMPLETE":
                issues.append(f"{node_id}: dependency {dependency} is not complete")
        if record.get("grant_id") == "orch-300-atomic-store-continuation-v2":
            issues.extend(self._orch_successor_live_issues(record))
            issues.extend(
                self._live_pr_metadata_issues(
                    record,
                    str(record["old_receipt_commit"]),
                    expected_base_sha=str(record["pr_base_sha"]),
                )
            )
        return tuple(dict.fromkeys(issues))

    def node(self, node_id: str) -> Mapping[str, Any]:
        """Project v2 ORCH scope only while its exact sealed claim is active."""

        raw = super().node(node_id)
        if node_id != "ORCH-300":
            return raw
        record = self._effective_repair_record(node_id)
        claim = self.active_claims().get(node_id)
        receipt_override = getattr(self, "_sealed_receipt_scope_override", None)
        if (
            record is None
            or not (
                isinstance(claim, Mapping)
                and claim.get("kind") == REPAIR_CLAIM_KIND
                and claim.get("grant_id") == record.get("grant_id")
                and claim.get("authority_digest") == digest_json(record)
                or receipt_override == (node_id, digest_json(record))
            )
        ):
            return raw
        updated = dict(raw)
        allowed = list(record["allowed_paths"])
        updated["write_scope"] = allowed
        updated["file_locks"] = allowed
        updated["required_tests"] = list(dict.fromkeys((
            *raw.get("required_tests", []),
            "orch-v2-store-batch-atomicity-concurrency",
        )))
        return updated

    def node_view(self, node_id: str) -> NodeView:
        if node_id == "BUILDER-330":
            execution = self._builder_execution()
            if execution is None:
                return super().node_view(node_id)
            recovery_issues = self._builder_recovery_issues()
            if recovery_issues:
                return NodeView(
                    node_id,
                    "REPAIR_REQUIRED",
                    tuple(recovery_issues),
                    tuple(super().node(node_id).get("dependencies", [])),
                    branch=str(super().node(node_id).get("branch")),
                )
            base = super().node_view(node_id)
            if base.state != "READY":
                return base
            return NodeView(
                node_id,
                "READY",
                ("exact Builder successor retirement and fresh-state gates passed",),
                tuple(super().node(node_id).get("dependencies", [])),
                branch=str(super().node(node_id).get("branch")),
            )
        if node_id not in REPAIR_AUTHORITY_MATERIAL_DIGESTS:
            return super().node_view(node_id)
        record = self._effective_repair_record(node_id)
        if record is None:
            return super().node_view(node_id)
        raw = super()._durable_receipt_records().get(node_id, [])
        if len(raw) == 1 and raw[0].get("commit") == record.get("old_receipt_commit"):
            return NodeView(
                node_id,
                "REPAIR_REQUIRED",
                ("sealed historical receipt is retained but rejected/adapted",),
                tuple(super().node(node_id).get("dependencies", [])),
                branch=str(record["branch"]),
                pr_number=int(record["pr"]),
            )
        claim = self.active_claims().get(node_id)
        if claim is not None:
            return NodeView(
                node_id,
                "RUNNING" if claim.get("status") == "RUNNING" else "CLAIMED",
                (),
                tuple(super().node(node_id).get("dependencies", [])),
                active_claim_owner=str(claim.get("owner")) if claim.get("owner") else None,
                branch=str(record["branch"]),
                pr_number=int(record["pr"]),
            )
        base = super().node_view(node_id)
        if base.state != record.get("prior_state"):
            return base
        if self._repair_authority_issues(node_id) or self._repair_live_issues(record):
            return base
        return NodeView(
            node_id,
            "READY",
            ("exact sealed repair authority permits continuation from retained receipt",),
            tuple(super().node(node_id).get("dependencies", [])),
            branch=str(record["branch"]),
            pr_number=int(record["pr"]),
        )

    @staticmethod
    def _claim_payload(record: Mapping[str, Any], claim: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "kind": REPAIR_CLAIM_KIND,
            "repair_id": record["repair_id"],
            "grant_id": record["grant_id"],
            "node_id": record["node_id"],
            "repository": record["repository"],
            "branch": record["branch"],
            "pr": record["pr"],
            "old_receipt_commit": record["old_receipt_commit"],
            "execution_target_sha": claim["target_sha"],
            "owner": claim["owner"],
            "expires_at": claim["expires_at"],
            "plan_fingerprint": record["plan_fingerprint"],
            "authority_digest": digest_json(record),
            "release_id": claim["release_id"],
            "github_snapshot_digest": claim["github_snapshot_digest"],
            "reconciliation_digest": claim["reconciliation_digest"],
            "doctor_evidence_digest": claim["doctor_evidence_digest"],
            "claim_topology": record["claim_topology"],
        }

    def _repair_claim_tree_and_parents(
        self,
        record: Mapping[str, Any],
        target: str,
    ) -> tuple[str, tuple[str, ...]]:
        old = str(record["old_receipt_commit"])
        if record["node_id"] == "OPTIMIZER-370":
            return str(record["old_receipt_tree"]), (old,)
        merged = self._git(("merge-tree", "--write-tree", old, target), check=False)
        tree = merged.stdout.strip()
        if merged.returncode != 0 or FULL_SHA.fullmatch(tree) is None:
            raise ClaimError("ORCH sealed repair merge tree is conflicting or unavailable")
        changed = self._diff_paths(target, tree)
        expected_merge_paths = record.get("historical_merge_paths", record["allowed_paths"])
        if tuple(sorted(changed)) != tuple(sorted(expected_merge_paths)):
            raise ClaimError("ORCH sealed repair merge tree differs from exact preserved scope")
        return tree, (old, target)

    def _create_repair_claim_commits(
        self,
        record: Mapping[str, Any],
        local: Mapping[str, Any],
    ) -> tuple[str, str]:
        tree, parents = self._repair_claim_tree_and_parents(record, str(local["target_sha"]))
        payload = self._claim_payload(record, local)
        message = REPAIR_CLAIM_KIND + "\n" + json.dumps(payload, sort_keys=True, separators=(",", ":"))
        args: list[str] = [
            "-c", "user.name=Hive Mind Autopilot Repair Claim",
            "-c", "user.email=autopilot-repair@hive-mind.invalid",
            "commit-tree", tree,
        ]
        for parent in parents:
            args.extend(("-p", parent))
        args.extend(("-m", message))
        identity = {
            "GIT_AUTHOR_NAME": "Hive Mind Autopilot Repair Claim",
            "GIT_AUTHOR_EMAIL": "autopilot-repair@hive-mind.invalid",
            "GIT_COMMITTER_NAME": "Hive Mind Autopilot Repair Claim",
            "GIT_COMMITTER_EMAIL": "autopilot-repair@hive-mind.invalid",
        }
        created = self._git(tuple(args), check=True, environment=identity).stdout.strip()
        if FULL_SHA.fullmatch(created) is None:
            raise ClaimError("sealed repair claim commit creation failed")
        if self._commit_parents(created) != parents or self._commit_tree(created) != tree:
            raise ClaimError("sealed repair claim topology or tree is invalid")
        if record["node_id"] != "OPTIMIZER-370":
            return created, created
        target = str(local["target_sha"])
        merged = self._git(("merge-tree", "--write-tree", created, target), check=False)
        merge_tree = merged.stdout.strip()
        if merged.returncode != 0 or FULL_SHA.fullmatch(merge_tree) is None:
            raise ClaimError("Optimizer sealed execution merge is conflicting or unavailable")
        if tuple(sorted(self._diff_paths(target, merge_tree))) != tuple(sorted(record["allowed_paths"])):
            raise ClaimError("Optimizer execution merge differs from exact preserved scope")
        merge_payload = {
            "schema_version": 1,
            "kind": "hive-mind-autopilot-sealed-execution-merge-v1",
            "node_id": record["node_id"],
            "grant_id": record["grant_id"],
            "repair_claim_commit": created,
            "execution_target_sha": target,
            "authority_digest": digest_json(record),
        }
        merge_message = merge_payload["kind"] + "\n" + json.dumps(
            merge_payload, sort_keys=True, separators=(",", ":")
        )
        merge_args = (
            "-c", "user.name=Hive Mind Autopilot Repair Merge",
            "-c", "user.email=autopilot-repair@hive-mind.invalid",
            "commit-tree", merge_tree, "-p", created, "-p", target, "-m", merge_message,
        )
        execution_merge = self._git(merge_args, check=True, environment=identity).stdout.strip()
        if FULL_SHA.fullmatch(execution_merge) is None:
            raise ClaimError("Optimizer sealed execution merge creation failed")
        if self._commit_parents(execution_merge) != (created, target) or self._commit_tree(execution_merge) != merge_tree:
            raise ClaimError("Optimizer sealed execution merge topology or tree is invalid")
        return created, execution_merge

    def _fetch_exact_repair_head(self, record: Mapping[str, Any]) -> str:
        """Fetch the sealed old head into a bounded non-symbolic local ref."""

        node_key = str(record["node_id"]).lower()
        old = str(record["old_receipt_commit"])
        branch_ref = f"refs/heads/{record['branch']}"
        local_ref = f"refs/hive-mind-autopilot/repair-fetch/{node_key}/{old}"
        self._git(("update-ref", "-d", local_ref), check=False)
        fetched = self._git(
            ("fetch", "--no-tags", "origin", f"{branch_ref}:{local_ref}"),
            check=False,
        )
        if fetched.returncode != 0:
            raise ClaimError("sealed repair cannot fetch exact canonical old branch")
        observed = self._git(("rev-parse", "--verify", local_ref), check=False).stdout.strip()
        if observed != old or not self.git_object_exists(old):
            raise ClaimError("sealed repair fetched head differs from pinned old receipt")
        if self._commit_tree(old) != record["old_receipt_tree"]:
            raise ClaimError("sealed repair fetched old receipt tree differs")
        return local_ref

    def _fetch_exact_orch_successor_objects(self, record: Mapping[str, Any]) -> None:
        """Authenticate the rolled-back v1 claim and the restored canonical head.

        A release-only clone need not already contain either object.  Fetching uses
        only controller-selected immutable refs and rechecks the canonical branch
        before and after the bounded fetch so a caller cannot substitute history.
        """

        if record.get("grant_id") != "orch-300-atomic-store-continuation-v2":
            return
        if not self._origin_is_configured_repository(record):
            raise ClaimError("ORCH v2 object authentication requires literal configured origin")
        old = str(record["old_receipt_commit"])
        rolled_back = str(record["rolled_back_claim"])
        branch_ref = f"refs/heads/{record['branch']}"
        if self._remote_ref_sha(branch_ref) != old:
            raise ClaimError("ORCH v2 canonical head drifted before object authentication")
        fetches = (
            (branch_ref, old, f"refs/hive-mind-autopilot/repair-fetch/orch-300/{old}"),
            (rolled_back, rolled_back, f"refs/hive-mind-autopilot/repair-fetch/orch-300/{rolled_back}"),
        )
        try:
            for source, expected, local_ref in fetches:
                self._git(("update-ref", "-d", local_ref), check=False)
                fetched = self._git(
                    ("fetch", "--no-tags", "origin", f"{source}:{local_ref}"),
                    check=False,
                )
                observed = self._git(("rev-parse", "--verify", local_ref), check=False).stdout.strip()
                if fetched.returncode != 0 or observed != expected or not self.git_object_exists(expected):
                    raise ClaimError("ORCH v2 exact historical object fetch failed")
            if self._remote_ref_sha(branch_ref) != old:
                raise ClaimError("ORCH v2 canonical head raced during object authentication")
        finally:
            for _source, _expected, local_ref in fetches:
                self._git(("update-ref", "-d", local_ref), check=False)

    def _old_repair_history_issues(self, record: Mapping[str, Any]) -> tuple[str, ...]:
        old = str(record["old_receipt_commit"])
        candidate = str(record["candidate_commit"])
        original_claim = str(record["original_claim_commit"])
        claim_target = str(record.get("claim_target_sha", record["incident_target_sha"]))
        issues: list[str] = []
        if self._commit_parents(old) != (candidate,):
            issues.append("sealed old receipt is not directly parented by exact candidate")
        if self._commit_tree(candidate) != record["candidate_tree"] or self._commit_tree(old) != record["old_receipt_tree"]:
            issues.append("sealed old candidate or receipt tree differs")
        if self._commit_tree(candidate) != self._commit_tree(old):
            issues.append("sealed old receipt is not zero-path")
        if self._commit_parents(original_claim) != (claim_target,):
            issues.append("sealed original claim parent differs from claim target")
        expected_claim_tree = record.get("claim_target_tree", self._commit_tree(claim_target))
        if self._commit_tree(original_claim) != expected_claim_tree:
            issues.append("sealed original claim tree differs from claim target")
        if not self.is_ancestor(original_claim, candidate):
            issues.append("sealed candidate does not retain original claim ancestry")
        historical_scope = record.get("historical_merge_paths", record["allowed_paths"])
        if tuple(sorted(self._diff_paths(claim_target, candidate))) != tuple(sorted(historical_scope)):
            issues.append("sealed historical candidate diff differs from exact node scope")
        shown = self._git(("show", "-s", "--format=%B", old), check=False)
        receipt = self._parse_receipt_message(shown.stdout) if shown.returncode == 0 else None
        if not isinstance(receipt, Mapping) or digest_json(receipt) != record["old_receipt_payload_digest"]:
            issues.append("sealed old receipt payload differs from exact digest")
        else:
            expected = {
                "node_id": record["node_id"],
                "branch": record["branch"],
                "plan_fingerprint": record["plan_fingerprint"],
                "contract_version": record["contract_version"],
                "base_commit": claim_target,
                "final_commit": candidate,
                "final_tree": record["candidate_tree"],
                "pr": record["expected_old_pr"],
            }
            for key, value in expected.items():
                if receipt.get(key) != value:
                    issues.append(f"sealed old receipt {key} differs")
        return tuple(dict.fromkeys(issues))

    def _release_binding_issues(self, local: Mapping[str, Any] | None = None) -> tuple[str, ...]:
        issues: list[str] = []
        release = self.current_release()
        if not isinstance(release, Mapping) or self._release_issues(release):
            return ("sealed recovery dispatcher release is stale",)
        target = self.current_target_sha()
        if release.get("target_sha") != target:
            issues.append("sealed recovery release target differs from current singleton target")
        if release.get("github_snapshot_digest") != self._snapshot_digest():
            issues.append("sealed recovery release snapshot binding is stale")
        if release.get("reconciliation_digest") != self._reconciliation_digest():
            issues.append("sealed recovery release reconciliation binding is stale")
        if self._doctor_evidence_digest() is None:
            issues.append("sealed recovery full doctor binding is stale")
        if local is not None:
            expected = {
                "target_sha": target,
                "release_id": release.get("release_id"),
                "github_snapshot_digest": self._snapshot_digest(),
                "reconciliation_digest": self._reconciliation_digest(),
                "doctor_evidence_digest": self._doctor_evidence_digest(),
            }
            for key, value in expected.items():
                if local.get(key) != value:
                    issues.append(f"sealed recovery active lease {key} is stale")
        return tuple(dict.fromkeys(issues))

    def _live_release_issues(
        self,
        record: Mapping[str, Any],
        expected_target: str | None = None,
    ) -> tuple[str, ...]:
        """Authenticate one literal-origin release ref and its fetched object twice."""

        if not self._origin_is_configured_repository(record):
            return ("sealed recovery live release check requires literal configured origin",)
        reference = f"refs/heads/{self.target_branch}"
        expected = expected_target or self.current_target_sha()
        observed = self._remote_ref_sha(reference)
        if observed != expected:
            return ("literal origin singleton release differs from captured execution target",)
        local_ref = f"refs/hive-mind-autopilot/release-fetch/{expected}"
        self._git(("update-ref", "-d", local_ref), check=False)
        try:
            fetched = self._git(
                ("fetch", "--no-tags", "origin", f"{reference}:{local_ref}"),
                check=False,
            )
            fetched_sha = self._git(("rev-parse", "--verify", local_ref), check=False).stdout.strip()
            if fetched.returncode != 0 or fetched_sha != expected or not self.git_object_exists(expected):
                return ("literal origin singleton release object cannot be authenticated",)
            if self._remote_ref_sha(reference) != expected:
                return ("literal origin singleton release raced during authentication",)
            if (
                record.get("grant_id") == "orch-300-atomic-store-continuation-v2"
                and self._remote_ref_sha("refs/heads/main")
                != record.get("protected_main_sha")
            ):
                return ("ORCH v2 protected main differs from sealed authority",)
            return ()
        finally:
            self._git(("update-ref", "-d", local_ref), check=False)

    def _query_github_pr(self, repository: str, number: int) -> Mapping[str, Any] | None:
        """Read one fixed GitHub PR through the authenticated CLI; never accept a URL."""

        if repository != "kb4beast/hive-mind-os" or type(number) is not int or number < 1:
            return None
        try:
            environment = self._sealed_transport_environment(tool="gh")
            executable = self._trusted_tool("gh")
        except AutopilotError:
            return None
        try:
            completed = subprocess.run(
                (
                    executable, "api", "--hostname", "github.com", "--method", "GET",
                    f"repos/{repository}/pulls/{number}",
                ),
                cwd=self.repo_root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=30,
                env=environment,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if completed.returncode != 0:
            return None
        try:
            value = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, Mapping) else None

    def _query_github_issue_event(
        self,
        repository: str,
        issue: int,
        event_id: int,
    ) -> Mapping[str, Any] | None:
        if repository != "kb4beast/hive-mind-os" or issue != 131 or event_id != 29298109938:
            return None
        environment = self._sealed_transport_environment(tool="gh")
        try:
            completed = subprocess.run(
                (
                    self._trusted_tool("gh"), "api", "--hostname", "github.com", "--method", "GET",
                    f"repos/{repository}/issues/events/{event_id}",
                ),
                cwd=self.repo_root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                check=False, timeout=30, env=environment,
            )
        except (OSError, subprocess.TimeoutExpired, AutopilotError):
            return None
        if completed.returncode != 0:
            return None
        try:
            value = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, Mapping) else None

    def _orch_successor_live_issues(self, record: Mapping[str, Any]) -> tuple[str, ...]:
        if record.get("grant_id") != "orch-300-atomic-store-continuation-v2":
            return ()
        issues: list[str] = []
        old = str(record["old_receipt_commit"])
        if self.remote_branch_sha(str(record["branch"])) != old:
            issues.append("ORCH v2 canonical branch is not the exact rolled-back receipt")
        if self._remote_ref_sha("refs/heads/main") != record.get("protected_main_sha"):
            issues.append("ORCH v2 protected main differs from sealed authority")
        if self.claim_path("ORCH-300").is_file():
            local = read_json(self.claim_path("ORCH-300"))
            if not isinstance(local, Mapping) or local.get("grant_id") != record.get("grant_id"):
                issues.append("ORCH v2 local claim is absent only for v1 replay or is foreign")
        event = self._query_github_issue_event(str(record["repository"]), 131, int(record["rollback_event_id"]))
        actor = event.get("actor") if isinstance(event, Mapping) else None
        expected_event = {
            "id": record["rollback_event_id"],
            "event": "head_ref_force_pushed",
            "created_at": record["rollback_event_at"],
            "commit_id": old,
            "actor": "kb4beast",
            "issue_number": 131,
            "issue_url": "https://api.github.com/repos/kb4beast/hive-mind-os/issues/131",
            "issue_html_url": "https://github.com/kb4beast/hive-mind-os/pull/131",
            "repository_url": "https://api.github.com/repos/kb4beast/hive-mind-os",
        }
        issue = event.get("issue") if isinstance(event, Mapping) else None
        observed_event = {
            "id": event.get("id") if isinstance(event, Mapping) else None,
            "event": event.get("event") if isinstance(event, Mapping) else None,
            "created_at": event.get("created_at") if isinstance(event, Mapping) else None,
            "commit_id": event.get("commit_id") if isinstance(event, Mapping) else None,
            "actor": actor.get("login") if isinstance(actor, Mapping) else None,
            "issue_number": issue.get("number") if isinstance(issue, Mapping) else None,
            "issue_url": issue.get("url") if isinstance(issue, Mapping) else None,
            "issue_html_url": issue.get("html_url") if isinstance(issue, Mapping) else None,
            "repository_url": issue.get("repository_url") if isinstance(issue, Mapping) else None,
        }
        if observed_event != expected_event:
            issues.append("ORCH v2 rollback event cannot be authenticated")
        rolled_back = str(record["rolled_back_claim"])
        if self.verify_git_objects and self.is_ancestor(rolled_back, self.current_target_sha()):
            issues.append("ORCH v2 current release contains rolled-back claim")
        return tuple(issues)

    def _live_pr_metadata_issues(
        self,
        record: Mapping[str, Any],
        expected_head_sha: str,
        *,
        expected_base_sha: str | None = None,
    ) -> tuple[str, ...]:
        """Authenticate exact PR identity immediately around a sealed remote mutation."""

        aggregate = record.get("aggregate_quarantine")
        if isinstance(aggregate, Mapping):
            expected = aggregate.get("pull_request")
            repository = record.get("repository")
            if not isinstance(expected, Mapping):
                return ("Builder successor PR139 authority is malformed",)
            expected_mergeable = expected.get("mergeable")
            expected_mergeable_state = expected.get("mergeable_state")
        else:
            phase_base = expected_base_sha
            expected = {
                "number": record.get("pr"),
                "state": "open",
                "draft": record.get("pr_is_draft"),
                "created_at": record.get("pr_created_at"),
                "base_ref": record.get("pr_base_branch"),
                "base_sha": phase_base or record.get("pr_base_sha"),
                "head_ref": record.get("pr_head_branch"),
            }
            repository = record.get("repository")
            expected_mergeable = None
            expected_mergeable_state = None
        number = expected.get("number") if isinstance(expected, Mapping) else None
        if repository != "kb4beast/hive-mind-os" or type(number) is not int:
            return ("sealed live PR authority repository or number is invalid",)
        payload = self._query_github_pr(str(repository), number)
        if not isinstance(payload, Mapping):
            return (f"live GitHub PR {number} cannot be authenticated",)
        base = payload.get("base")
        head = payload.get("head")
        base_repo = base.get("repo") if isinstance(base, Mapping) else None
        head_repo = head.get("repo") if isinstance(head, Mapping) else None
        observed = {
            "number": payload.get("number"),
            "state": payload.get("state"),
            "draft": payload.get("draft"),
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
            "base_ref": base.get("ref") if isinstance(base, Mapping) else None,
            "base_sha": base.get("sha") if isinstance(base, Mapping) else None,
            "base_repository": base_repo.get("full_name") if isinstance(base_repo, Mapping) else None,
            "head_ref": head.get("ref") if isinstance(head, Mapping) else None,
            "head_sha": head.get("sha") if isinstance(head, Mapping) else None,
            "head_repository": head_repo.get("full_name") if isinstance(head_repo, Mapping) else None,
            "closed_at": payload.get("closed_at"),
            "merged_at": payload.get("merged_at"),
        }
        required = {
            "number": number,
            "state": expected.get("state"),
            "draft": expected.get("draft"),
            "created_at": expected.get("created_at"),
            "base_ref": expected.get("base_ref"),
            "base_repository": repository,
            "head_ref": expected.get("head_ref"),
            "head_sha": expected_head_sha,
            "head_repository": repository,
            "closed_at": None,
            "merged_at": None,
        }
        allowed_base_shas: set[str] | None = None
        if (
            not isinstance(aggregate, Mapping)
            and record.get("grant_id") == "orch-300-atomic-store-continuation-v2"
            and expected_head_sha != record.get("old_receipt_commit")
        ):
            allowed_base_shas = {
                str(expected.get("base_sha")),
                self.current_target_sha(),
            }
        elif isinstance(aggregate, Mapping) or expected.get("base_sha") is not None:
            required["base_sha"] = expected.get("base_sha")
        if isinstance(aggregate, Mapping):
            required["updated_at"] = expected.get("updated_at")
        issues = [
            f"live GitHub PR {number} {key} differs from sealed authority"
            for key, value in required.items()
            if observed.get(key) != value
        ]
        if isinstance(aggregate, Mapping):
            if payload.get("mergeable") is not expected_mergeable:
                issues.append(f"live GitHub PR {number} mergeable differs from quarantine evidence")
            if payload.get("mergeable_state") != expected_mergeable_state:
                issues.append(f"live GitHub PR {number} mergeable_state differs from quarantine evidence")
        elif allowed_base_shas is not None and observed.get("base_sha") not in allowed_base_shas:
            issues.append(f"live GitHub PR {number} base_sha differs from bounded volatile attestation")
        return tuple(issues)

    def _recover_interrupted_repair_claim(self, record: Mapping[str, Any]) -> None:
        if not self._origin_is_configured_repository(record):
            raise ClaimError("sealed repair recovery requires literal configured origin")
        live_issues = self._live_release_issues(record)
        if live_issues:
            raise ClaimError("; ".join(live_issues))
        path = self.claim_path(str(record["node_id"]))
        if not path.is_file():
            return
        value = read_json(path)
        if not isinstance(value, Mapping) or value.get("kind") != REPAIR_CLAIM_KIND:
            raise ClaimError("sealed repair existing claim is foreign or malformed")
        if value.get("authority_digest") != digest_json(record):
            raise ClaimError("sealed repair existing claim authority is stale")
        status = value.get("status")
        if status not in {"PREPARING", "PREPARED"}:
            if status == "CLAIMED" and parse_time(value.get("expires_at")) <= self.clock():
                remote_head = value.get("remote_head_commit")
                observed = self.remote_branch_sha(str(record["branch"]))
                if observed == remote_head and isinstance(remote_head, str):
                    pr_issues = self._live_pr_metadata_issues(
                        record, remote_head, expected_base_sha=str(record.get("pr_base_sha"))
                    )
                    if pr_issues:
                        raise ClaimError("; ".join(pr_issues))
                    if self._live_release_issues(record):
                        raise ClaimError("sealed repair release changed before expired-claim rollback")
                    self._cas_update_branch(
                        str(record["branch"]), remote_head, str(record["old_receipt_commit"])
                    )
                    observed = self.remote_branch_sha(str(record["branch"]))
                    pr_issues = self._live_pr_metadata_issues(
                        record,
                        str(record["old_receipt_commit"]),
                        expected_base_sha=str(record.get("pr_base_sha")),
                    )
                    if pr_issues:
                        raise ClaimError("; ".join(pr_issues))
                if observed == record["old_receipt_commit"]:
                    append_jsonl(self.state_dir / "sealed-repair-adverse.jsonl", {
                        "event": "expired_claim_rolled_back", "node_id": record["node_id"],
                        "remote_head_commit": remote_head,
                    })
                    path.unlink()
                    return
                retained = dict(value)
                retained["status"] = "ADVERSE"
                retained["adverse_reason"] = "expired repair claim advanced beyond exact rollback head"
                atomic_write_json(path, retained)
                raise ClaimError("expired sealed repair claim requires reconciliation")
            return
        old = str(record["old_receipt_commit"])
        created = value.get("remote_claim_commit")
        remote_head = value.get("remote_head_commit")
        observed = self.remote_branch_sha(str(record["branch"]))
        if status == "PREPARING" and created is None and observed == old:
            append_jsonl(self.state_dir / "sealed-repair-adverse.jsonl", {"event": "cleared_pre_cas_claim", "node_id": record["node_id"]})
            path.unlink()
            return
        if status == "PREPARED" and isinstance(created, str) and isinstance(remote_head, str):
            if observed == remote_head:
                pr_issues = self._live_pr_metadata_issues(
                    record, remote_head, expected_base_sha=str(record.get("pr_base_sha"))
                )
                if pr_issues:
                    raise ClaimError("; ".join(pr_issues))
                if self._live_release_issues(record):
                    raise ClaimError("sealed repair release changed before interrupted-claim rollback")
                self._cas_update_branch(str(record["branch"]), remote_head, old)
                observed = self.remote_branch_sha(str(record["branch"]))
                pr_issues = self._live_pr_metadata_issues(
                    record, old, expected_base_sha=str(record.get("pr_base_sha"))
                )
                if pr_issues:
                    raise ClaimError("; ".join(pr_issues))
            if observed == old:
                append_jsonl(self.state_dir / "sealed-repair-adverse.jsonl", {"event": "rolled_back_interrupted_claim", "node_id": record["node_id"], "claim_commit": created, "remote_head_commit": remote_head})
                path.unlink()
                return
        raise ClaimError("sealed repair interrupted claim requires reconciliation")

    def _cas_update_branch(self, branch: str, expected: str, new: str) -> None:
        reference = f"refs/heads/{branch}"
        pushed = self._git(
            (
                "push", "--atomic", f"--force-with-lease={reference}:{expected}",
                "origin", f"{new}:{reference}",
            ),
            check=False,
        )
        if pushed.returncode != 0:
            raise ClaimError("sealed recovery compare-and-swap push failed: " + pushed.stderr.strip())

    def _cas_create_branch(self, branch: str, new: str) -> None:
        reference = f"refs/heads/{branch}"
        pushed = self._git(
            (
                "push", "--atomic", f"--force-with-lease={reference}:",
                "origin", f"{new}:{reference}",
            ),
            check=False,
        )
        if pushed.returncode != 0:
            raise ClaimError("sealed recovery absent-ref compare-and-swap push failed: " + pushed.stderr.strip())

    def _cas_delete_branch(self, branch: str, expected: str) -> None:
        reference = f"refs/heads/{branch}"
        pushed = self._git(
            (
                "push", "--atomic", f"--force-with-lease={reference}:{expected}",
                "origin", f":{reference}",
            ),
            check=False,
        )
        if pushed.returncode != 0:
            raise ClaimError("sealed recovery exact-head delete failed: " + pushed.stderr.strip())

    def _builder_successor_claim_payload(
        self,
        local: Mapping[str, Any],
    ) -> dict[str, Any]:
        replan = self._builder_document(BUILDER_SUCCESSOR_REPLAN_PATH) or {}
        topology = self._builder_successor_topology(replan)
        return {
            "schema_version": 1,
            "kind": BUILDER_CLAIM_KIND,
            "recovery_id": BUILDER_RECOVERY_ID,
            "node_id": "BUILDER-330",
            "repository": replan.get("repository"),
            "branch": topology.branch,
            "owner": local.get("owner"),
            "expires_at": local.get("expires_at"),
            "plan_fingerprint": self.expected_plan_fingerprint,
            "target_sha": local.get("target_sha"),
            "release_id": local.get("release_id"),
            "retirement_execution_digest": local.get("builder_execution_digest"),
            "retirement_recovery_digest": local.get("builder_recovery_digest"),
            "authority_digest": local.get("builder_authority_digest"),
            "replan_digest": local.get("builder_replan_digest"),
            "archive_ref": topology.archive_ref,
            "archived_source_head": topology.source_head,
            "snapshot_digest": local.get("snapshot_digest"),
            "reconciliation_digest": local.get("reconciliation_digest"),
            "doctor_evidence_digest": local.get("doctor_evidence_digest"),
        }

    def _builder_successor_claim_issues(
        self,
        value: object,
        *,
        require_published: bool = True,
    ) -> tuple[str, ...]:
        required = {
            "schema_version", "kind", "status", "recovery_id", "node_id", "owner",
            "claimed_at", "heartbeat_at", "expires_at", "plan_fingerprint", "remote",
            "branch", "target_sha", "remote_claim_commit", "remote_claim_payload_digest",
            "previous_remote_claim_commit",
            "builder_execution_digest", "builder_recovery_digest", "builder_authority_digest",
            "builder_replan_digest", "archive_ref", "archived_source_head", "release_id",
            "snapshot_digest", "reconciliation_digest", "doctor_evidence_digest",
        }
        if not isinstance(value, Mapping) or set(value) != required:
            return ("Builder successor local claim schema is invalid",)
        replan = self._builder_document(BUILDER_SUCCESSOR_REPLAN_PATH) or {}
        bootstrap = self._builder_document(BUILDER_SUCCESSOR_BOOTSTRAP_PATH) or {}
        topology = self._builder_successor_topology(replan)
        execution = self._builder_execution()
        issues: list[str] = []
        expected_scalars = {
            "schema_version": 1,
            "kind": BUILDER_CLAIM_KIND,
            "recovery_id": BUILDER_RECOVERY_ID,
            "node_id": "BUILDER-330",
            "plan_fingerprint": self.expected_plan_fingerprint,
            "remote": "origin",
            "branch": topology.branch,
            "archive_ref": topology.archive_ref,
            "archived_source_head": topology.source_head,
            "builder_execution_digest": digest_json(execution or {}),
            "builder_authority_digest": digest_json(bootstrap),
            "builder_replan_digest": BUILDER_SUCCESSOR_DIGESTS[BUILDER_SUCCESSOR_REPLAN_PATH],
        }
        for key, expected in expected_scalars.items():
            if value.get(key) != expected:
                issues.append(f"Builder successor local claim {key} is invalid")
        for key in (
            "owner", "claimed_at", "heartbeat_at", "expires_at", "target_sha", "release_id",
            "snapshot_digest", "reconciliation_digest", "doctor_evidence_digest",
        ):
            item = value.get(key)
            if type(item) is not str or not item or item != item.strip():
                issues.append(f"Builder successor local claim {key} is invalid")
        if DIGEST_SHA256.fullmatch(str(value.get("builder_recovery_digest", ""))) is None:
            issues.append("Builder successor local claim recovery digest is invalid")
        if value.get("status") not in {"PREPARING", "PREPARED", "CLAIMED", "RUNNING", "ADVERSE"}:
            issues.append("Builder successor local claim status is invalid")
        commit = value.get("remote_claim_commit")
        previous = value.get("previous_remote_claim_commit")
        payload_digest = value.get("remote_claim_payload_digest")
        if require_published or value.get("status") != "PREPARING":
            if not isinstance(commit, str) or FULL_SHA.fullmatch(commit) is None:
                issues.append("Builder successor remote claim commit is invalid")
            if not isinstance(payload_digest, str) or DIGEST_SHA256.fullmatch(payload_digest) is None:
                issues.append("Builder successor claim payload digest is invalid")
        if previous is not None and (not isinstance(previous, str) or FULL_SHA.fullmatch(previous) is None):
            issues.append("Builder successor previous claim commit is invalid")
        try:
            for key in ("claimed_at", "heartbeat_at", "expires_at"):
                if format_time(parse_time(value.get(key))) != value.get(key):
                    issues.append(f"Builder successor local claim {key} is not canonical")
        except (TypeError, ValueError):
            issues.append("Builder successor local claim timestamps are invalid")
        if not issues and isinstance(commit, str):
            expected_payload = self._builder_successor_claim_payload(value)
            if digest_json(expected_payload) != payload_digest:
                issues.append("Builder successor claim payload digest differs")
            shown = self._git(("show", "-s", "--format=%B", commit), check=False)
            try:
                actual = json.loads(shown.stdout.strip()) if shown.returncode == 0 else None
            except json.JSONDecodeError:
                actual = None
            if not isinstance(actual, Mapping) or dict(actual) != expected_payload:
                issues.append("Builder successor remote claim payload is invalid")
            if self.verify_git_objects and (
                self._commit_parents(commit) != (str(value["target_sha"]),)
                or self._commit_tree(commit) != self._commit_tree(str(value["target_sha"]))
            ):
                issues.append("Builder successor claim is not a zero-path child of its release")
        return tuple(dict.fromkeys(issues))

    def _builder_successor_ref_issues(
        self,
        topology: BuilderSuccessorTopology,
        expected_source: str | None,
    ) -> tuple[str, ...]:
        issues: list[str] = []
        if self._remote_ref_sha(topology.source_ref) != expected_source:
            issues.append("Builder successor canonical source differs from the exact phase head")
        if self._remote_ref_sha(topology.archive_ref) != topology.source_head:
            issues.append("Builder successor immutable archive differs from retired source")
        if self._remote_ref_sha(topology.legacy_archive_ref) is not None:
            issues.append("Builder successor legacy archive must remain absent")
        return tuple(issues)

    def _create_builder_successor_claim_commit(self, local: Mapping[str, Any]) -> str:
        target = str(local["target_sha"])
        tree = self._commit_tree(target)
        payload = self._builder_successor_claim_payload(local)
        identity = {
            "GIT_AUTHOR_NAME": "Hive Mind Autopilot Builder Successor Claim",
            "GIT_AUTHOR_EMAIL": "autopilot-claim@hive-mind.invalid",
            "GIT_COMMITTER_NAME": "Hive Mind Autopilot Builder Successor Claim",
            "GIT_COMMITTER_EMAIL": "autopilot-claim@hive-mind.invalid",
        }
        created = self._git(
            (
                "-c", "user.name=Hive Mind Autopilot Builder Successor Claim",
                "-c", "user.email=autopilot-claim@hive-mind.invalid",
                "commit-tree", tree, "-p", target, "-m",
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
            ),
            check=True,
            environment=identity,
        ).stdout.strip()
        if FULL_SHA.fullmatch(created) is None:
            raise ClaimError("Builder successor failed to create exact claim commit")
        return created

    def claim(
        self,
        node_id: str,
        owner: str,
        *,
        lease_minutes: int = 90,
        publish_remote: bool = False,
        remote: str = "origin",
    ) -> Mapping[str, Any]:
        if node_id == "BUILDER-330" and self._builder_execution() is not None:
            if type(owner) is not str or not owner or owner != owner.strip() or any(
                ord(character) < 32 or ord(character) == 127 for character in owner
            ):
                raise ClaimError("Builder successor reclaim owner is invalid")
            if type(lease_minutes) is not int or not 1 <= lease_minutes <= 1_440:
                raise ClaimError("Builder successor reclaim lease is invalid")
            if not publish_remote or remote != "origin":
                raise ClaimError("Builder successor reclaim requires literal-origin remote publication")
            replan = self._builder_document(BUILDER_SUCCESSOR_REPLAN_PATH) or {}
            bootstrap = self._builder_document(BUILDER_SUCCESSOR_BOOTSTRAP_PATH) or {}
            if not self._origin_is_configured_repository(replan):
                raise ClaimError("Builder successor reclaim requires literal configured origin")
            recovery_issues = self._builder_recovery_issues()
            if recovery_issues:
                raise ClaimError("; ".join(recovery_issues))
            target = self.current_target_sha()
            live_issues = self._builder_successor_release_issues(replan, target)
            if live_issues:
                raise ClaimError("; ".join(live_issues))
            self.assert_start_now(node_id)
            topology = self._builder_successor_topology(replan)
            path = self.claim_path(node_id)
            existing = read_json(path) if path.is_file() else None
            if existing is not None:
                existing_issues = self._builder_successor_claim_issues(
                    existing,
                    require_published=(
                        isinstance(existing, Mapping)
                        and existing.get("status") != "PREPARING"
                    ),
                )
                if existing_issues:
                    raise ClaimError("; ".join(existing_issues))
                assert isinstance(existing, Mapping)
                if existing.get("owner") != owner:
                    raise ClaimError("Builder successor reclaim already belongs to another owner")
                claim_commit = str(existing["remote_claim_commit"])
                observed = self._remote_ref_sha(topology.source_ref)
                if existing.get("status") == "ADVERSE":
                    raise ClaimError("Builder successor reclaim has adverse recovery evidence")
                if existing.get("status") == "PREPARING":
                    if observed is not None:
                        adverse = dict(existing)
                        adverse["status"] = "ADVERSE"
                        atomic_write_json(path, adverse)
                        raise ClaimError("Builder successor preparing claim has unexpected remote mutation")
                    append_jsonl(self.state_dir / BUILDER_AUDIT_FILE, {
                        "event": "builder_successor_preparing_claim_cleared_without_mutation",
                        "claim_digest": digest_json(existing),
                        "recorded_at": format_time(self.clock()),
                    })
                    path.unlink()
                    existing = None
                if existing is None:
                    pass
                elif parse_time(existing.get("expires_at")) <= self.clock():
                    if observed == claim_commit:
                        try:
                            self._cas_delete_branch(topology.branch, claim_commit)
                        except ClaimError:
                            adverse = dict(existing)
                            adverse["status"] = "ADVERSE"
                            atomic_write_json(path, adverse)
                            raise ClaimError("Builder successor expired claim advanced during exact cleanup") from None
                        observed = self._remote_ref_sha(topology.source_ref)
                    if observed is None:
                        append_jsonl(self.state_dir / BUILDER_AUDIT_FILE, {
                            "event": "builder_successor_expired_claim_released",
                            "claim_digest": digest_json(existing),
                            "recorded_at": format_time(self.clock()),
                        })
                        path.unlink()
                        existing = None
                    else:
                        adverse = dict(existing)
                        adverse["status"] = "ADVERSE"
                        atomic_write_json(path, adverse)
                        raise ClaimError("Builder successor expired claim remote state is ambiguous")
                if existing is None:
                    pass
                elif observed == claim_commit:
                    post_issues = (
                        *self._builder_successor_release_issues(replan, str(existing["target_sha"])),
                        *self._builder_successor_ref_issues(topology, claim_commit),
                    )
                    if post_issues:
                        raise ClaimError("; ".join(post_issues))
                    recovered = dict(existing)
                    recovered["status"] = "CLAIMED"
                    atomic_write_json(path, recovered)
                    return recovered
                elif (
                    existing.get("status") == "PREPARED"
                    and isinstance(existing.get("previous_remote_claim_commit"), str)
                    and observed == existing.get("previous_remote_claim_commit")
                ):
                    previous = str(existing["previous_remote_claim_commit"])
                    try:
                        self._cas_update_branch(topology.branch, previous, claim_commit)
                        post_issues = (
                            *self._builder_successor_release_issues(replan, str(existing["target_sha"])),
                            *self._builder_successor_ref_issues(topology, claim_commit),
                        )
                        if post_issues:
                            raise ClaimError("; ".join(post_issues))
                        recovered = dict(existing)
                        recovered["status"] = "CLAIMED"
                        recovered["previous_remote_claim_commit"] = None
                        atomic_write_json(path, recovered)
                        return recovered
                    except Exception:
                        if self._remote_ref_sha(topology.source_ref) == claim_commit:
                            try:
                                self._cas_update_branch(topology.branch, claim_commit, previous)
                            except ClaimError:
                                adverse = dict(existing)
                                adverse["status"] = "ADVERSE"
                                atomic_write_json(path, adverse)
                        raise
                elif observed is not None:
                    adverse = dict(existing)
                    adverse["status"] = "ADVERSE"
                    atomic_write_json(path, adverse)
                    raise ClaimError("Builder successor reclaim remote head is ambiguous")
                elif existing is not None:
                    try:
                        self._cas_create_branch(topology.branch, claim_commit)
                        post_issues = (
                            *self._builder_successor_release_issues(replan, str(existing["target_sha"])),
                            *self._builder_successor_ref_issues(topology, claim_commit),
                        )
                        if post_issues:
                            raise ClaimError("; ".join(post_issues))
                        recovered = dict(existing)
                        recovered["status"] = "CLAIMED"
                        atomic_write_json(path, recovered)
                        return recovered
                    except Exception:
                        if self._remote_ref_sha(topology.source_ref) == claim_commit:
                            try:
                                self._cas_delete_branch(topology.branch, claim_commit)
                            except ClaimError:
                                adverse = dict(existing)
                                adverse["status"] = "ADVERSE"
                                atomic_write_json(path, adverse)
                        raise
            if self._builder_successor_ref_issues(topology, None):
                raise ClaimError("; ".join(self._builder_successor_ref_issues(topology, None)))
            release = self.current_release()
            if not isinstance(release, Mapping) or type(release.get("release_id")) is not str:
                raise ClaimError("Builder successor reclaim requires current explicit release")
            now = self.clock()
            recovery = self._builder_document(f".autopilot/state/{BUILDER_RECOVERY_FILE}") or {}
            local: dict[str, Any] = {
                "schema_version": 1,
                "kind": BUILDER_CLAIM_KIND,
                "status": "PREPARING",
                "recovery_id": BUILDER_RECOVERY_ID,
                "node_id": "BUILDER-330",
                "owner": owner,
                "claimed_at": format_time(now),
                "heartbeat_at": format_time(now),
                "expires_at": format_time(now + timedelta(minutes=lease_minutes)),
                "plan_fingerprint": self.expected_plan_fingerprint,
                "remote": "origin",
                "branch": topology.branch,
                "target_sha": target,
                "remote_claim_commit": None,
                "remote_claim_payload_digest": None,
                "previous_remote_claim_commit": None,
                "builder_execution_digest": digest_json(self._builder_execution() or {}),
                "builder_recovery_digest": digest_json(recovery),
                "builder_authority_digest": digest_json(bootstrap),
                "builder_replan_digest": BUILDER_SUCCESSOR_DIGESTS[BUILDER_SUCCESSOR_REPLAN_PATH],
                "archive_ref": topology.archive_ref,
                "archived_source_head": topology.source_head,
                "release_id": release["release_id"],
                "snapshot_digest": self._snapshot_digest(),
                "reconciliation_digest": self._reconciliation_digest(),
                "doctor_evidence_digest": self._doctor_evidence_digest(),
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError as error:
                raise ClaimError("Builder successor reclaim intent already exists") from error
            try:
                os.write(descriptor, (json.dumps(local, sort_keys=True, indent=2) + "\n").encode())
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            created: str | None = None
            try:
                created = self._create_builder_successor_claim_commit(local)
                local["remote_claim_commit"] = created
                local["remote_claim_payload_digest"] = digest_json(
                    self._builder_successor_claim_payload(local)
                )
                local["status"] = "PREPARED"
                atomic_write_json(path, local)
                prepared_issues = self._builder_successor_claim_issues(local)
                pre_issues = (
                    *prepared_issues,
                    *self._builder_successor_release_issues(replan, target),
                    *self._builder_successor_ref_issues(topology, None),
                )
                if pre_issues:
                    raise ClaimError("; ".join(pre_issues))
                self._cas_create_branch(topology.branch, created)
                post_issues = (
                    *self._builder_successor_release_issues(replan, target),
                    *self._builder_successor_ref_issues(topology, created),
                    *self._builder_successor_claim_issues(local),
                )
                if post_issues:
                    raise ClaimError("; ".join(post_issues))
                local["status"] = "CLAIMED"
                atomic_write_json(path, local)
                return local
            except Exception:
                compensated = self._remote_ref_sha(topology.source_ref) is None
                if created is not None and self._remote_ref_sha(topology.source_ref) == created:
                    try:
                        self._cas_delete_branch(topology.branch, created)
                        compensated = self._remote_ref_sha(topology.source_ref) is None
                    except ClaimError:
                        compensated = False
                if compensated:
                    path.unlink(missing_ok=True)
                else:
                    local["status"] = "ADVERSE"
                    atomic_write_json(path, local)
                    append_jsonl(self.state_dir / BUILDER_AUDIT_FILE, {
                        "event": "builder_successor_claim_compensation_failed",
                        "claim_commit": created,
                        "recorded_at": format_time(self.clock()),
                    })
                raise
        if node_id not in REPAIR_AUTHORITY_MATERIAL_DIGESTS:
            return super().claim(
                node_id,
                owner,
                lease_minutes=lease_minutes,
                publish_remote=publish_remote,
                remote=remote,
            )
        if not owner.strip() or not 1 <= lease_minutes <= 1_440:
            raise ClaimError("sealed repair owner and bounded lease are required")
        if not publish_remote or remote != "origin":
            raise ClaimError("sealed repair claim requires literal origin remote publication")
        record = self._repair_record(node_id)
        if not self._origin_is_configured_repository(record):
            raise ClaimError("sealed repair requires literal configured origin repository")
        live_issues = self._live_release_issues(record)
        if live_issues:
            raise ClaimError("; ".join(live_issues))
        self._recover_interrupted_repair_claim(record)
        self.assert_start_now(node_id)
        if self._repair_live_issues(record):
            raise ClaimError("; ".join(self._repair_live_issues(record)))
        live_issues = self._live_release_issues(record)
        if live_issues:
            raise ClaimError("; ".join(live_issues))
        old = str(record["old_receipt_commit"])
        branch = str(record["branch"])
        pr_issues = self._live_pr_metadata_issues(record, old)
        if pr_issues:
            raise ClaimError("; ".join(pr_issues))
        if self.remote_branch_sha(branch) != old:
            raise ClaimError("sealed repair remote head moved from exact old receipt")
        now = self.clock()
        release = self.current_release()
        if not isinstance(release, Mapping):
            raise ClaimError("sealed repair requires current explicit dispatcher release")
        local: dict[str, Any] = {
            "schema_version": 1,
            "kind": REPAIR_CLAIM_KIND,
            "node_id": node_id,
            "owner": owner,
            "status": "PREPARING",
            "claimed_at": format_time(now),
            "heartbeat_at": format_time(now),
            "expires_at": format_time(now + timedelta(minutes=lease_minutes)),
            "plan_fingerprint": self.expected_plan_fingerprint,
            "remote": "origin",
            "remote_claim_commit": None,
            "execution_merge_commit": None,
            "remote_head_commit": None,
            "target_sha": self.current_target_sha(),
            "branch": branch,
            "old_receipt_commit": old,
            "repair_id": record["repair_id"],
            "grant_id": record["grant_id"],
            "authority_digest": digest_json(record),
            "release_id": release.get("release_id"),
            "github_snapshot_digest": self._snapshot_digest(),
            "reconciliation_digest": self._reconciliation_digest(),
            "doctor_evidence_digest": self._doctor_evidence_digest(),
        }
        path = self.claim_path(node_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            raise ClaimError(f"node {node_id} already has a claim") from error
        try:
            os.write(descriptor, (json.dumps(local, sort_keys=True, indent=2) + "\n").encode())
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        created: str | None = None
        remote_head: str | None = None
        try:
            fetch_ref = self._fetch_exact_repair_head(record)
            history_issues = self._old_repair_history_issues(record)
            if history_issues:
                raise ClaimError("; ".join(history_issues))
            created, remote_head = self._create_repair_claim_commits(record, local)
            local["remote_claim_commit"] = created
            local["execution_merge_commit"] = remote_head
            local["remote_head_commit"] = remote_head
            local["status"] = "PREPARED"
            atomic_write_json(path, local)
            binding_issues = self._release_binding_issues(local)
            if binding_issues:
                raise ClaimError("; ".join(binding_issues))
            if self.remote_branch_sha(branch) != old:
                raise ClaimError("sealed repair remote changed during claim verification")
            if not self.is_ancestor(old, remote_head):
                raise ClaimError("sealed repair publication is not a fast-forward from old receipt")
            pr_issues = self._live_pr_metadata_issues(record, old)
            if pr_issues:
                raise ClaimError("; ".join(pr_issues))
            self._cas_update_branch(branch, old, remote_head)
            if self.remote_branch_sha(branch) != remote_head:
                raise ClaimError("sealed repair remote claim verification failed")
            if self._release_binding_issues(local):
                raise ClaimError("sealed repair release changed during claim publication")
            live_issues = self._live_release_issues(record, str(local["target_sha"]))
            if live_issues:
                raise ClaimError("; ".join(live_issues))
            pr_issues = self._live_pr_metadata_issues(record, remote_head)
            if pr_issues:
                raise ClaimError("; ".join(pr_issues))
            local["status"] = "CLAIMED"
            atomic_write_json(path, local)
            return local
        except Exception:
            rolled_back = self.remote_branch_sha(branch) == old
            if remote_head is not None and self.remote_branch_sha(branch) == remote_head:
                try:
                    self._cas_update_branch(branch, remote_head, old)
                    rolled_back = self.remote_branch_sha(branch) == old
                except ClaimError:
                    append_jsonl(
                        self.state_dir / "sealed-repair-adverse.jsonl",
                        {"node_id": node_id, "event": "claim_compensation_failed", "claim_commit": created, "remote_head_commit": remote_head},
                    )
                    rolled_back = False
            if rolled_back:
                path.unlink(missing_ok=True)
            else:
                local["status"] = "ADVERSE"
                local["adverse_reason"] = "claim publication could not be rolled back or reconciled"
                atomic_write_json(path, local)
            raise
        finally:
            if "fetch_ref" in locals():
                self._git(("update-ref", "-d", fetch_ref), check=False)

    def clean_stale_claims(self) -> tuple[str, ...]:
        """Never orphan a Builder successor remote claim via generic local cleanup."""

        removed: list[str] = []
        if not self.claims_dir.is_dir():
            return ()
        now = self.clock()
        for path in sorted(self.claims_dir.glob("*.json")):
            if path.stem == "BUILDER-330" and self._builder_execution() is not None:
                continue
            try:
                value = read_json(path)
                expires = parse_time(value.get("expires_at")) if isinstance(value, Mapping) else now
            except (OSError, ValueError):
                expires = now
            if expires <= now:
                stale = self.state_dir / "stale-claims" / path.name
                stale.parent.mkdir(parents=True, exist_ok=True)
                os.replace(path, stale)
                removed.append(path.stem)
        return tuple(removed)

    def heartbeat(
        self,
        node_id: str,
        owner: str,
        *,
        lease_minutes: int = 90,
        running: bool = True,
    ) -> Mapping[str, Any]:
        if node_id != "BUILDER-330" or self._builder_execution() is None:
            return super().heartbeat(
                node_id, owner, lease_minutes=lease_minutes, running=running
            )
        if type(lease_minutes) is not int or not 1 <= lease_minutes <= 1_440:
            raise ClaimError("Builder successor heartbeat lease is invalid")
        path = self.claim_path(node_id)
        value = read_json(path) if path.is_file() else None
        issues = self._builder_successor_claim_issues(value)
        if issues:
            raise ClaimError("; ".join(issues))
        assert isinstance(value, Mapping)
        if value.get("owner") != owner or value.get("status") not in {"CLAIMED", "RUNNING"}:
            raise ClaimError("Builder successor heartbeat owner or state differs")
        if parse_time(value.get("expires_at")) <= self.clock():
            raise ClaimError("Builder successor claim lease has expired")
        replan = self._builder_document(BUILDER_SUCCESSOR_REPLAN_PATH) or {}
        if not self._origin_is_configured_repository(replan):
            raise ClaimError("Builder successor heartbeat requires literal configured origin")
        topology = self._builder_successor_topology(replan)
        old_commit = str(value["remote_claim_commit"])
        pre_issues = (
            *self._builder_successor_release_issues(replan, str(value["target_sha"])),
            *self._builder_successor_ref_issues(topology, old_commit),
        )
        if pre_issues:
            raise ClaimError("; ".join(pre_issues))
        now = self.clock()
        updated = dict(value)
        updated["status"] = "PREPARED"
        updated["heartbeat_at"] = format_time(now)
        updated["expires_at"] = format_time(now + timedelta(minutes=lease_minutes))
        updated["previous_remote_claim_commit"] = old_commit
        new_commit = self._create_builder_successor_claim_commit(updated)
        updated["remote_claim_commit"] = new_commit
        updated["remote_claim_payload_digest"] = digest_json(
            self._builder_successor_claim_payload(updated)
        )
        atomic_write_json(path, updated)
        try:
            self._cas_update_branch(topology.branch, old_commit, new_commit)
            post_issues = (
                *self._builder_successor_release_issues(replan, str(value["target_sha"])),
                *self._builder_successor_ref_issues(topology, new_commit),
                *self._builder_successor_claim_issues(updated),
            )
            if post_issues:
                raise ClaimError("; ".join(post_issues))
            updated["status"] = "RUNNING" if running else "CLAIMED"
            updated["previous_remote_claim_commit"] = None
            atomic_write_json(path, updated)
            return updated
        except Exception:
            compensated = self._remote_ref_sha(topology.source_ref) == old_commit
            if self._remote_ref_sha(topology.source_ref) == new_commit:
                try:
                    self._cas_update_branch(topology.branch, new_commit, old_commit)
                    compensated = self._remote_ref_sha(topology.source_ref) == old_commit
                except ClaimError:
                    compensated = False
            if compensated:
                atomic_write_json(path, value)
            else:
                adverse = dict(updated)
                adverse["status"] = "ADVERSE"
                atomic_write_json(path, adverse)
            raise

    def release(self, node_id: str, owner: str, *, reason: str) -> None:
        if node_id == "BUILDER-330" and self._builder_execution() is not None:
            path = self.claim_path(node_id)
            if not path.is_file():
                return
            value = read_json(path)
            issues = self._builder_successor_claim_issues(value)
            if issues:
                raise ClaimError("; ".join(issues))
            assert isinstance(value, Mapping)
            if value.get("owner") != owner:
                raise ClaimError("Builder successor release owner differs")
            replan = self._builder_document(BUILDER_SUCCESSOR_REPLAN_PATH) or {}
            if not self._origin_is_configured_repository(replan):
                raise ClaimError("Builder successor release requires literal configured origin")
            topology = self._builder_successor_topology(replan)
            claim_commit = str(value["remote_claim_commit"])
            pre_issues = (
                *self._builder_successor_release_issues(replan, str(value["target_sha"])),
                *self._builder_successor_ref_issues(topology, claim_commit),
            )
            if pre_issues:
                adverse = dict(value)
                adverse["status"] = "ADVERSE"
                atomic_write_json(path, adverse)
                raise ClaimError("; ".join(pre_issues))
            try:
                self._cas_delete_branch(topology.branch, claim_commit)
            except ClaimError:
                adverse = dict(value)
                adverse["status"] = "ADVERSE"
                atomic_write_json(path, adverse)
                raise
            if self._remote_ref_sha(topology.source_ref) is not None:
                adverse = dict(value)
                adverse["status"] = "ADVERSE"
                atomic_write_json(path, adverse)
                raise ClaimError("Builder successor release remote deletion was not exact")
            append_jsonl(self.state_dir / "releases.jsonl", {
                "node_id": node_id,
                "owner": owner,
                "reason": reason,
                "remote_claim_commit": claim_commit,
                "recovery_id": BUILDER_RECOVERY_ID,
                "released_at": format_time(self.clock()),
            })
            path.unlink()
            return
        if node_id not in REPAIR_AUTHORITY_MATERIAL_DIGESTS:
            return super().release(node_id, owner, reason=reason)
        path = self.claim_path(node_id)
        if not path.is_file():
            return
        value = read_json(path)
        if not isinstance(value, Mapping) or value.get("owner") != owner:
            raise ClaimError("sealed repair claim owner does not match")
        record = self._repair_record(node_id)
        if not self._origin_is_configured_repository(record):
            raise ClaimError("sealed repair release requires literal configured origin")
        if value.get("status") == "COMPLETING":
            intent_path = self.state_dir / f"sealed-repair-completion-{node_id.lower()}.json"
            intent = read_json(intent_path) if intent_path.is_file() else None
            receipt_commit = intent.get("receipt_commit") if isinstance(intent, Mapping) else None
            if isinstance(receipt_commit, str):
                shown = self._git(("show", "-s", "--format=%B", receipt_commit), check=False)
                receipt = self._parse_receipt_message(shown.stdout) if shown.returncode == 0 else None
                if isinstance(receipt, Mapping):
                    recovered = self._recover_interrupted_repair_completion(
                        node_id, owner, receipt, value, record
                    )
                    if recovered is not None:
                        append_jsonl(self.state_dir / "releases.jsonl", {
                            "node_id": node_id, "owner": owner,
                            "reason": reason + "; recovered committed receipt",
                            "released_at": format_time(self.clock()),
                        })
                        return
                    value = read_json(path)
                    if not isinstance(value, Mapping):
                        return
        live_issues = self._live_release_issues(record, str(value.get("target_sha")))
        if live_issues:
            raise ClaimError("; ".join(live_issues))
        remote_head = value.get("remote_head_commit")
        observed = self.remote_branch_sha(str(record["branch"]))
        if isinstance(remote_head, str) and observed == remote_head:
            self._cas_update_branch(str(record["branch"]), remote_head, str(record["old_receipt_commit"]))
            if self.remote_branch_sha(str(record["branch"])) != record["old_receipt_commit"]:
                raise ClaimError("sealed repair rollback verification failed")
        elif observed != record["old_receipt_commit"]:
            raise ClaimError("sealed repair rollback is forbidden after the branch advanced")
        append_jsonl(
            self.state_dir / "releases.jsonl",
            {"node_id": node_id, "owner": owner, "reason": reason, "released_at": format_time(self.clock())},
        )
        path.unlink()

    def _repair_claim_message(self, commit: str) -> Mapping[str, Any] | None:
        shown = self._git(("show", "-s", "--format=%B", commit), check=False)
        if shown.returncode != 0:
            return None
        text = shown.stdout.rstrip("\n")
        prefix = REPAIR_CLAIM_KIND + "\n"
        if not text.startswith(prefix):
            return None
        try:
            value = json.loads(text[len(prefix):])
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, Mapping) else None

    def _sealed_receipt_shape_issues(
        self, node_id: str, receipt: Mapping[str, Any]
    ) -> tuple[str, ...]:
        required = {
            "schema_version", "plan_fingerprint", "node_id", "contract_version",
            "base_commit", "base_tree", "final_commit", "final_tree", "branch", "pr",
            "changed_paths", "tests", "evidence_refs", "model_runtime", "role_identities",
            "authority", "consultations", "acceptance_decision", "timestamp", "rollback_ref",
        }
        issues: list[str] = []
        if set(receipt) != required:
            issues.append("sealed replacement receipt schema is expanded or incomplete")
        for key in ("node_id", "branch", "timestamp", "rollback_ref"):
            if not isinstance(receipt.get(key), str) or not str(receipt.get(key)).strip():
                issues.append(f"sealed replacement receipt {key} must be a nonblank string")
        if receipt.get("node_id") != node_id:
            issues.append("sealed replacement receipt node identity is invalid")
        if receipt.get("schema_version") != 1 or type(receipt.get("schema_version")) is not int:
            issues.append("sealed replacement receipt schema_version must be integer 1")
        if receipt.get("contract_version") != 1 or type(receipt.get("contract_version")) is not int:
            issues.append("sealed replacement receipt contract_version must be integer 1")
        if not isinstance(receipt.get("plan_fingerprint"), str) or DIGEST_SHA256.fullmatch(
            str(receipt.get("plan_fingerprint"))
        ) is None:
            issues.append("sealed replacement receipt plan_fingerprint must be canonical SHA-256")
        for key in ("base_commit", "base_tree", "final_commit", "final_tree"):
            if not isinstance(receipt.get(key), str) or FULL_SHA.fullmatch(str(receipt.get(key))) is None:
                issues.append(f"sealed replacement receipt {key} must be a full lowercase Git SHA")
        try:
            parsed_timestamp = parse_time(receipt.get("timestamp"))
        except (TypeError, ValueError):
            issues.append("sealed replacement receipt timestamp must be canonical date-time text")
        else:
            if receipt.get("timestamp") != format_time(parsed_timestamp):
                issues.append("sealed replacement receipt timestamp must be canonical UTC Z text")
        if type(receipt.get("pr")) is not int:
            issues.append("sealed replacement receipt pr must be an integer")
        for key in ("changed_paths", "evidence_refs"):
            values = receipt.get(key)
            if not isinstance(values, list) or not values or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                issues.append(f"sealed replacement receipt {key} must contain nonblank strings")
            elif len(values) != len(set(values)):
                issues.append(f"sealed replacement receipt {key} must be unique")
        changed_paths = receipt.get("changed_paths")
        if isinstance(changed_paths, list) and changed_paths != sorted(changed_paths):
            issues.append("sealed replacement receipt changed_paths must be sorted")
        runtime = receipt.get("model_runtime")
        if (
            not isinstance(runtime, Mapping)
            or set(runtime) != {"provider", "model"}
            or any(not isinstance(runtime.get(key), str) or not runtime.get(key, "").strip() for key in runtime)
        ):
            issues.append("sealed replacement receipt model_runtime is incomplete")
        roles = receipt.get("role_identities")
        if not isinstance(roles, list) or not roles:
            issues.append("sealed replacement receipt role_identities must be nonempty")
        else:
            seen_roles: set[str] = set()
            seen_identities: set[str] = set()
            for role in roles:
                if not isinstance(role, Mapping) or set(role) != {"role", "identity", "identity_kind"}:
                    issues.append("sealed replacement role identity shape is invalid")
                    continue
                if any(not isinstance(role.get(key), str) or not role.get(key, "").strip() for key in role):
                    issues.append("sealed replacement role identity fields must be nonblank")
                role_name = str(role.get("role"))
                if role_name in seen_roles:
                    issues.append("sealed replacement role identities contain a duplicate role")
                seen_roles.add(role_name)
                identity = str(role.get("identity"))
                if identity in seen_identities:
                    issues.append("sealed replacement role identities reuse an identity")
                seen_identities.add(identity)
                if role.get("identity_kind") not in {"model_role", "service", "human"}:
                    issues.append("sealed replacement role identity kind is invalid")
            expected_roles = list(self.node(node_id)["roles"])
            if [role.get("role") for role in roles if isinstance(role, Mapping)] != expected_roles:
                issues.append("sealed replacement role identity ordering differs from the node contract")
        tests = receipt.get("tests")
        if not isinstance(tests, list) or not tests:
            issues.append("sealed replacement receipt tests must be nonempty")
        else:
            observed_test_names: list[str] = []
            for test in tests:
                if not isinstance(test, Mapping) or set(test) != {"name", "status", "command"}:
                    issues.append("sealed replacement test record shape is invalid")
                    continue
                command = test.get("command")
                if (
                    not isinstance(test.get("name"), str)
                    or not test.get("name", "").strip()
                    or test.get("status") != "passed"
                    or not isinstance(command, list)
                    or not command
                    or any(not isinstance(item, str) or not item.strip() for item in command)
                ):
                    issues.append("sealed replacement test record fields are invalid")
                else:
                    observed_test_names.append(str(test["name"]))
            if observed_test_names != list(self.node(node_id)["required_tests"]):
                issues.append("sealed replacement test ordering differs from the node contract")
        authority = receipt.get("authority")
        authority_keys = {
            "node_id", "autonomy_level", "grants", "grant_id",
            "supersedes_receipt_commit", "repair_authority_digest",
            "repair_claim_commit", "execution_merge_commit", "execution_target_sha",
            "repair_claim_payload_digest",
        }
        if not isinstance(authority, Mapping) or set(authority) != authority_keys:
            issues.append("sealed replacement authority shape is expanded or incomplete")
        else:
            for key in ("node_id", "autonomy_level", "grant_id"):
                if not isinstance(authority.get(key), str) or not authority.get(key, "").strip():
                    issues.append(f"sealed replacement authority {key} must be nonblank text")
            grants = authority.get("grants")
            if (
                not isinstance(grants, list)
                or len(grants) != 1
                or not isinstance(grants[0], str)
                or not grants[0].strip()
            ):
                issues.append("sealed replacement authority grants must contain one nonblank grant")
            for key in (
                "supersedes_receipt_commit", "repair_claim_commit",
                "execution_merge_commit", "execution_target_sha",
            ):
                if not isinstance(authority.get(key), str) or FULL_SHA.fullmatch(str(authority.get(key))) is None:
                    issues.append(f"sealed replacement authority {key} must be a full lowercase Git SHA")
            for key in ("repair_authority_digest", "repair_claim_payload_digest"):
                if not isinstance(authority.get(key), str) or DIGEST_SHA256.fullmatch(
                    str(authority.get(key))
                ) is None:
                    issues.append(f"sealed replacement authority {key} must be canonical SHA-256")
        consultations = receipt.get("consultations")
        consultation_keys = {
            "request_id", "mission_id", "question", "reason_code", "requesting_role",
            "consulted_roles", "round", "suspected_cheating", "evidence_refs", "decision",
            "answer", "dissent", "human_escalation", "authority_class",
            "role_first_exhausted", "cheating_disposition", "identity_records",
        }
        if not isinstance(consultations, list):
            issues.append("sealed replacement consultations must be a list")
        else:
            request_ids: list[str] = []
            for consultation in consultations:
                if not isinstance(consultation, Mapping) or set(consultation) != consultation_keys:
                    issues.append("sealed replacement consultation shape is expanded or incomplete")
                    continue
                for key in (
                    "request_id", "mission_id", "question", "reason_code",
                    "requesting_role", "decision", "cheating_disposition",
                ):
                    if not isinstance(consultation.get(key), str) or not consultation.get(key, "").strip():
                        issues.append(f"sealed replacement consultation {key} must be nonblank text")
                request_ids.append(str(consultation.get("request_id")))
                if type(consultation.get("round")) is not int or not 1 <= consultation.get("round", 0) <= 3:
                    issues.append("sealed replacement consultation round must be integer 1 through 3")
                for key in ("suspected_cheating", "human_escalation", "role_first_exhausted"):
                    if type(consultation.get(key)) is not bool:
                        issues.append(f"sealed replacement consultation {key} must be boolean")
                for key in ("evidence_refs", "dissent"):
                    values = consultation.get(key)
                    if not isinstance(values, list) or any(
                        not isinstance(value, str) or not value.strip() for value in values
                    ):
                        issues.append(f"sealed replacement consultation {key} must contain nonblank strings")
                    elif len(values) != len(set(values)):
                        issues.append(f"sealed replacement consultation {key} must be unique")
                if consultation.get("decision") not in {
                    "RESOLVED", "REMAND", "REPLAN", "BLOCKED_EVIDENCE",
                    "TRUE_AUTHORITY_REQUIRED", "QUARANTINE",
                }:
                    issues.append("sealed replacement consultation decision is invalid")
                if consultation.get("cheating_disposition") not in {
                    "NOT_APPLICABLE", "CONFIRMED", "DISPROVED", "UNRESOLVED",
                }:
                    issues.append("sealed replacement consultation cheating disposition is invalid")
                answer = consultation.get("answer")
                if answer is not None and (not isinstance(answer, str) or not answer.strip()):
                    issues.append("sealed replacement consultation answer must be null or nonblank text")
                authority_class = consultation.get("authority_class")
                if authority_class is not None and (
                    not isinstance(authority_class, str) or not authority_class.strip()
                ):
                    issues.append("sealed replacement consultation authority_class must be null or nonblank text")
                consulted = consultation.get("consulted_roles")
                if (
                    not isinstance(consulted, list)
                    or any(not isinstance(role, str) for role in consulted)
                    or len(consulted) < 2
                    or len(consulted) != len(set(consulted))
                ):
                    issues.append("sealed replacement consultation roles must contain two unique roles")
                    consulted = []
                if consultation.get("requesting_role") in consulted:
                    issues.append("sealed replacement consultation cannot consult the requesting role")
                identities = consultation.get("identity_records")
                if not isinstance(identities, list):
                    issues.append("sealed replacement consultation identities must be a list")
                    continue
                identity_roles: list[str] = []
                identity_values: list[str] = []
                for identity in identities:
                    if not isinstance(identity, Mapping) or set(identity) != {"role", "identity", "identity_kind"}:
                        issues.append("sealed replacement consultation identity shape is invalid")
                        continue
                    if any(
                        not isinstance(identity.get(key), str) or not identity.get(key, "").strip()
                        for key in ("role", "identity", "identity_kind")
                    ):
                        issues.append("sealed replacement consultation identity fields must be nonblank strings")
                        continue
                    if identity.get("identity_kind") not in {"model_role", "service", "human"}:
                        issues.append("sealed replacement consultation identity kind is invalid")
                    identity_roles.append(str(identity["role"]))
                    identity_values.append(str(identity["identity"]))
                if len(identity_roles) != len(set(identity_roles)):
                    issues.append("sealed replacement consultation identities contain a duplicate role")
                if len(identity_values) != len(set(identity_values)):
                    issues.append("sealed replacement consultation identities reuse an identity")
                if identity_roles != consulted:
                    issues.append("sealed replacement consultation identities do not exactly order consulted roles")
            if len(request_ids) != len(set(request_ids)):
                issues.append("sealed replacement consultations contain a duplicate request_id")
        if receipt.get("acceptance_decision") != "ADAPT":
            issues.append("sealed replacement acceptance_decision must be ADAPT")
        return tuple(dict.fromkeys(issues))

    def _replacement_receipt_issues(
        self,
        node_id: str,
        receipt: Mapping[str, Any],
        *,
        active_claim: Mapping[str, Any] | None = None,
    ) -> tuple[str, ...]:
        record = self._effective_repair_record(node_id)
        if record is None:
            return ("sealed replacement authority is unavailable",)
        issues = list(self._sealed_receipt_shape_issues(node_id, receipt))
        if self._has_git_repository() and not self.verify_git_objects:
            issues.append("sealed replacement in a Git repository requires object verification")
        if record.get("grant_id") == "orch-300-atomic-store-continuation-v2":
            self._sealed_receipt_scope_override = (node_id, digest_json(record))
        try:
            generic_issues = list(
                super().validate_receipt(node_id, receipt, require_integrated=False)
            )
            if (
                node_id == "OPTIMIZER-370"
                and record.get("grant_id") == "optimizer-370-invalid-receipt-supersession-v1"
                and receipt.get("base_commit") == record.get("incident_target_sha")
                and receipt.get("base_tree") == OPTIMIZER_INCIDENT_TREE
            ):
                # This one sealed topology deliberately retains the incident base
                # in the durable receipt while the correction is measured from
                # the later execution release merged as the second parent.  Keep
                # every generic check except its incompatible base..final path
                # equality; exact execution-target scope is proved below.
                generic_issues = [
                    issue for issue in generic_issues
                    if issue != "receipt changed_paths do not match the exact base..final diff"
                ]
            issues.extend(generic_issues)
        finally:
            self.__dict__.pop("_sealed_receipt_scope_override", None)
        recovery_issues = self._repair_authority_issues(node_id)
        if recovery_issues:
            issues.extend(recovery_issues)
        authority = receipt.get("authority")
        if not isinstance(authority, Mapping):
            return tuple(dict.fromkeys((*issues, "sealed replacement receipt authority is invalid")))
        expected_authority_keys = {
            "node_id", "autonomy_level", "grants", "grant_id",
            "supersedes_receipt_commit", "repair_authority_digest",
            "repair_claim_commit", "execution_merge_commit", "execution_target_sha",
            "repair_claim_payload_digest",
        }
        if set(authority) != expected_authority_keys:
            issues.append("sealed replacement authority shape is expanded or incomplete")
        if authority.get("node_id") != node_id or authority.get("autonomy_level") != "A3":
            issues.append("sealed replacement authority node or autonomy level is invalid")
        if authority.get("grants") != [record["grant_id"]]:
            issues.append("sealed replacement grants are not the exact singleton grant")
        if authority.get("grant_id") != record["grant_id"]:
            issues.append("sealed replacement grant_id is invalid")
        if authority.get("supersedes_receipt_commit") != record["old_receipt_commit"]:
            issues.append("sealed replacement omits exact supersedes_receipt_commit")
        if authority.get("repair_authority_digest") != digest_json(record):
            issues.append("sealed replacement authority digest is invalid")
        claim_commit = authority.get("repair_claim_commit")
        if not isinstance(claim_commit, str) or FULL_SHA.fullmatch(claim_commit) is None:
            issues.append("sealed replacement repair_claim_commit is invalid")
        execution_target = authority.get("execution_target_sha")
        if not isinstance(execution_target, str) or FULL_SHA.fullmatch(execution_target) is None:
            issues.append("sealed replacement execution_target_sha is invalid")
        claim_payload_digest = authority.get("repair_claim_payload_digest")
        if not isinstance(claim_payload_digest, str) or DIGEST_SHA256.fullmatch(claim_payload_digest) is None:
            issues.append("sealed replacement repair_claim_payload_digest is invalid")
        expected_base = record["incident_target_sha"] if node_id == "OPTIMIZER-370" else execution_target
        if receipt.get("base_commit") != expected_base:
            issues.append("sealed replacement base_commit differs from sealed provenance base")
        if self.verify_git_objects and isinstance(expected_base, str) and self.git_object_exists(expected_base):
            if receipt.get("base_tree") != self._commit_tree(expected_base):
                issues.append("sealed replacement base_tree differs from sealed provenance base")
        if receipt.get("pr") != record["replacement_pr"]:
            issues.append("sealed replacement PR is not the pinned actual PR")
        if receipt.get("acceptance_decision") != "ADAPT":
            issues.append("sealed replacement disposition must be ADAPT")
        if active_claim is not None:
            if claim_commit != active_claim.get("remote_claim_commit"):
                issues.append("sealed replacement repair claim differs from active lease")
            if execution_target != active_claim.get("target_sha"):
                issues.append("sealed replacement execution target differs from active lease")
            if active_claim.get("grant_id") != record["grant_id"]:
                issues.append("active sealed repair lease grant is invalid")
            if active_claim.get("authority_digest") != digest_json(record):
                issues.append("active sealed repair lease authority digest is invalid")
            if authority.get("execution_merge_commit") != active_claim.get("execution_merge_commit"):
                issues.append("sealed replacement execution merge differs from active lease")
            if self.current_target_sha() != active_claim.get("target_sha"):
                continuation_issues = (
                    self._optimizer_continuation_issues(
                        active_claim,
                        receipt,
                        expected_pr_head=str(receipt.get("final_commit")),
                    )
                    if node_id == "OPTIMIZER-370"
                    else ("not an Optimizer continuation",)
                )
                if continuation_issues:
                    issues.append("sealed replacement completion target moved after claim")
                    issues.extend(continuation_issues)
        if self.verify_git_objects and isinstance(claim_commit, str) and FULL_SHA.fullmatch(claim_commit):
            old = str(record["old_receipt_commit"])
            final = receipt.get("final_commit")
            if record.get("grant_id") == "orch-300-atomic-store-continuation-v2":
                rolled_back = str(record["rolled_back_claim"])
                capability = str(record["capability_commit"])
                incident = str(record["incident_target_sha"])
                chain = (incident, capability, execution_target, final)
                if (
                    not all(isinstance(commit, str) and self.git_object_exists(commit) for commit in chain)
                    or not self.is_ancestor(incident, capability)
                    or not self.is_ancestor(capability, str(execution_target))
                    or not self.is_ancestor(str(execution_target), str(final))
                ):
                    issues.append("ORCH v2 successor omits the sealed capability ancestry chain")
                for label, commit in (
                    ("repair claim", claim_commit),
                    ("execution target", execution_target),
                    ("final", final),
                    ("integrated target", self.current_target_sha()),
                ):
                    if isinstance(commit, str) and self.git_object_exists(commit) and self.is_ancestor(rolled_back, commit):
                        issues.append(f"ORCH v2 {label} contains rolled-back v1 claim ancestry")
            if not self.git_object_exists(claim_commit):
                issues.append("sealed repair claim object is unavailable")
            else:
                parents = self._commit_parents(claim_commit)
                expected_parents = (old,) if node_id == "OPTIMIZER-370" else (old, str(execution_target))
                if parents != expected_parents:
                    issues.append("sealed repair claim parent ordering is invalid")
                message = self._repair_claim_message(claim_commit)
                if not isinstance(message, Mapping):
                    issues.append("sealed repair claim message is invalid")
                else:
                    if set(message) != set(self._claim_payload(record, {
                        "target_sha": execution_target,
                        "owner": message.get("owner"),
                        "expires_at": message.get("expires_at"),
                        "release_id": message.get("release_id"),
                        "github_snapshot_digest": message.get("github_snapshot_digest"),
                        "reconciliation_digest": message.get("reconciliation_digest"),
                        "doctor_evidence_digest": message.get("doctor_evidence_digest"),
                    })):
                        issues.append("sealed repair claim message shape is invalid")
                    for key, expected in {
                        "schema_version": 1,
                        "kind": REPAIR_CLAIM_KIND,
                        "repair_id": record["repair_id"],
                        "grant_id": record["grant_id"],
                        "node_id": node_id,
                        "repository": record["repository"],
                        "branch": record["branch"],
                        "pr": record["pr"],
                        "old_receipt_commit": old,
                        "execution_target_sha": execution_target,
                        "plan_fingerprint": record["plan_fingerprint"],
                        "authority_digest": digest_json(record),
                        "claim_topology": record["claim_topology"],
                    }.items():
                        if message.get(key) != expected:
                            issues.append(f"sealed repair claim message {key} is invalid")
                    if any(not isinstance(message.get(key), str) or not message.get(key) for key in (
                        "owner", "expires_at", "release_id", "github_snapshot_digest",
                        "reconciliation_digest", "doctor_evidence_digest",
                    )):
                        issues.append("sealed repair claim message dynamic evidence is incomplete")
                    if authority.get("repair_claim_payload_digest") != digest_json(message):
                        issues.append("sealed replacement does not bind the complete repair claim payload")
                    if active_claim is not None and dict(message) != self._claim_payload(record, active_claim):
                        issues.append("sealed repair claim message differs from active lease")
                if node_id == "OPTIMIZER-370":
                    if self._commit_tree(claim_commit) != record["old_receipt_tree"]:
                        issues.append("Optimizer repair claim is not zero-path")
                else:
                    tree, _ = self._repair_claim_tree_and_parents(record, str(execution_target))
                    if self._commit_tree(claim_commit) != tree:
                        issues.append("ORCH repair merge claim tree is not deterministic")
            execution_merge = authority.get("execution_merge_commit")
            if not isinstance(execution_merge, str) or FULL_SHA.fullmatch(execution_merge) is None:
                issues.append("sealed replacement execution_merge_commit is invalid")
            elif node_id == "ORCH-300":
                if execution_merge != claim_commit:
                    issues.append("ORCH execution merge must be the repair claim itself")
                if self.git_object_exists(str(record["rolled_back_claim"])) and self.is_ancestor(
                    str(record["rolled_back_claim"]), execution_merge
                ):
                    issues.append("ORCH v2 execution merge contains rolled-back v1 claim ancestry")
            elif not self.git_object_exists(execution_merge):
                issues.append("Optimizer execution merge object is unavailable")
            else:
                expected_merge = self._git(("merge-tree", "--write-tree", claim_commit, str(execution_target)), check=False)
                merge_tree = expected_merge.stdout.strip()
                if expected_merge.returncode != 0 or FULL_SHA.fullmatch(merge_tree) is None:
                    issues.append("Optimizer execution merge tree cannot be reproduced")
                if self._commit_parents(execution_merge) != (claim_commit, execution_target):
                    issues.append("Optimizer execution merge parent ordering is invalid")
                if self._commit_tree(execution_merge) != merge_tree:
                    issues.append("Optimizer execution merge tree is not deterministic")
                if tuple(sorted(self._diff_paths(str(execution_target), execution_merge))) != tuple(sorted(record["allowed_paths"])):
                    issues.append("Optimizer execution merge differs from exact preserved scope")
            if not isinstance(final, str) or not isinstance(execution_merge, str) or not self.is_ancestor(execution_merge, final):
                issues.append("sealed replacement final does not descend from repair claim")
            if not isinstance(execution_target, str) or not isinstance(final, str) or not self.is_ancestor(execution_target, final):
                issues.append("sealed replacement final does not descend from execution release")
            if isinstance(execution_target, str) and isinstance(final, str):
                observed = self._diff_paths(execution_target, final)
                declared = receipt.get("changed_paths")
                if not isinstance(declared, list) or tuple(sorted(declared)) != observed:
                    issues.append("sealed replacement changed_paths differ from execution release diff")
                if record.get("grant_id") == "orch-300-atomic-store-continuation-v2":
                    if tuple(sorted(observed)) != tuple(sorted(record["allowed_paths"])):
                        issues.append("ORCH v2 replacement diff is not the exact four-path scope")
                elif node_id == "OPTIMIZER-370":
                    if tuple(sorted(observed)) != tuple(sorted(record["allowed_paths"])):
                        issues.append("Optimizer replacement diff is not the exact two-path scope")
                elif not observed or set(observed) - set(record["allowed_paths"]):
                    issues.append("sealed replacement diff expands or omits exact repair scope")
        return tuple(dict.fromkeys(issues))

    def _optimizer_continuation_record(self) -> Mapping[str, Any] | None:
        value = self._builder_document(OPTIMIZER_CONTINUATION_PATH)
        required = {
            "schema_version", "grant_id", "court_id", "decision", "advocate_identity",
            "cross_examiner_identity", "expert_witness_identity", "judge_identity", "node_id",
            "repository", "origin_name", "origin_url", "branch", "pr", "incident_target_sha",
            "incident_target_tree", "old_receipt_commit", "old_receipt_tree",
            "repair_claim_commit", "execution_merge_commit", "execution_target_sha",
            "candidate_commit", "candidate_tree", "intended_receipt_digest", "plan_fingerprint",
            "prior_grant_id", "prior_authority_digest", "protected_main_ref",
            "protected_main_sha", "capability_commit", "allowed_paths", "overlay_paths",
            "acceptance_conditions", "rollback", "dissent",
        }
        if not isinstance(value, Mapping) or set(value) != required:
            return None
        identities = {
            value.get("advocate_identity"), value.get("cross_examiner_identity"),
            value.get("expert_witness_identity"), value.get("judge_identity"),
        }
        exact = {
            "schema_version": 1,
            "grant_id": "optimizer-370-active-g-to-h-completion-continuation-v1",
            "decision": "ADAPT", "node_id": "OPTIMIZER-370",
            "repository": "kb4beast/hive-mind-os", "origin_name": "origin",
            "origin_url": "https://github.com/kb4beast/hive-mind-os.git",
            "branch": "autopilot/optimizer-370", "pr": 135,
            "incident_target_sha": "cfe17ff7d6b06bdaa42e9ba6ec2a75a9c66c6a58",
            "incident_target_tree": OPTIMIZER_INCIDENT_TREE,
            "old_receipt_commit": "926f60ec345d7bf5b5eb9229009de1f7e7888a97",
            "old_receipt_tree": "260bef36a3f7132d2af316e2a0c6564fabf6e7c7",
            "repair_claim_commit": "8fa51243327ae928e46df180bfd81fbf90062cf5",
            "execution_merge_commit": "88f2962b64f7cc9f88284c5dd30106de5313da7b",
            "execution_target_sha": "9ea57b8ee1bb630b4fe3a8350e1629c4fb4a4379",
            "candidate_commit": "948368b77ba8de920369f416970e83b909bd50ba",
            "candidate_tree": "e7fe4cdec441550a0007306182b222ac76ba73b3",
            "intended_receipt_digest": "sha256:bf5b2cdd03f40b88980a964d843bf8829b9dc2393864b4ded360f04a42e8afdd",
            "plan_fingerprint": "sha256:9769f9796efb351da9b764fd49983b1130adccc0b8592e42581714d3727f8b39",
            "prior_grant_id": "optimizer-370-invalid-receipt-supersession-v1",
            "prior_authority_digest": REPAIR_AUTHORITY_MATERIAL_DIGESTS["OPTIMIZER-370"],
            "protected_main_ref": "refs/heads/main",
            "protected_main_sha": "8bcecb7f6a182f86d30f9b9696c9720b6e06a0c8",
            "capability_commit": OPTIMIZER_CONTINUATION_CAPABILITY_COMMIT,
        }
        if (
            any(value.get(key) != expected for key, expected in exact.items())
            or len(identities) != 4
            or None in identities
            or digest_json(value) != OPTIMIZER_CONTINUATION_DIGEST
            or tuple(value.get("allowed_paths", ())) != (
                "src/hive_mind_os/brain_kernel/optimizer.py",
                "tests/test_hive_cortex_optimizer.py",
            )
        ):
            return None
        return value

    def _optimizer_continuation_issues(
        self,
        claim: Mapping[str, Any],
        receipt: Mapping[str, Any],
        *,
        expected_pr_head: str,
    ) -> tuple[str, ...]:
        continuation = self._optimizer_continuation_record()
        prior = self._effective_repair_record("OPTIMIZER-370")
        if continuation is None or prior is None:
            return ("Optimizer active completion continuation authority is unavailable",)
        issues: list[str] = []
        expected_claim = {
            "node_id": "OPTIMIZER-370",
            "branch": continuation["branch"],
            "remote_claim_commit": continuation["repair_claim_commit"],
            "execution_merge_commit": continuation["execution_merge_commit"],
            "target_sha": continuation["execution_target_sha"],
            "grant_id": continuation["prior_grant_id"],
            "authority_digest": continuation["prior_authority_digest"],
        }
        for key, expected in expected_claim.items():
            if claim.get(key) != expected:
                issues.append(f"Optimizer continuation active claim {key} differs")
        if digest_json(receipt) != continuation["intended_receipt_digest"]:
            issues.append("Optimizer continuation intended receipt digest differs")
        if (
            receipt.get("final_commit") != continuation["candidate_commit"]
            or receipt.get("final_tree") != continuation["candidate_tree"]
            or tuple(receipt.get("changed_paths", ())) != tuple(continuation["allowed_paths"])
        ):
            issues.append("Optimizer continuation candidate or exact scope differs")
        current = self.current_target_sha()
        execution_target = str(continuation["execution_target_sha"])
        capability = str(continuation["capability_commit"])
        if not self.verify_git_objects or not self._has_git_repository():
            issues.append("Optimizer continuation requires authenticated Git objects")
        else:
            if (
                current == execution_target
                or not self.is_ancestor(execution_target, current)
                or not self.is_ancestor(capability, current)
            ):
                issues.append("Optimizer continuation current release omits exact G-to-H capability")
            if tuple(self._diff_paths(execution_target, current)) != tuple(
                sorted(continuation["overlay_paths"])
            ):
                issues.append("Optimizer continuation H changes paths outside exact overlay")
            if self.is_ancestor(str(continuation["candidate_commit"]), current):
                issues.append("Optimizer continuation candidate is already in singleton release")
        if self._remote_ref_sha(str(continuation["protected_main_ref"])) != continuation["protected_main_sha"]:
            issues.append("Optimizer continuation protected main moved")
        if self._remote_ref_sha(f"refs/heads/{self.target_branch}") != current:
            issues.append("Optimizer continuation live singleton release differs")
        issues.extend(self._live_pr_metadata_issues(prior, expected_pr_head))
        release = self.current_release()
        if not isinstance(release, Mapping) or release.get("target_sha") != current:
            issues.append("Optimizer continuation dispatcher release is not bound to H")
        elif self._release_binding_issues():
            issues.append("Optimizer continuation H release evidence is stale")
        return tuple(dict.fromkeys(issues))

    def _claim_provenance_issues(
        self,
        node_id: str,
        receipt: Mapping[str, Any],
    ) -> tuple[str, ...]:
        """Retain generic provenance except for the exact ORCH 01ca-to-G successor."""

        authority = receipt.get("authority")
        if node_id != "ORCH-300" or not isinstance(authority, Mapping):
            return super()._claim_provenance_issues(node_id, receipt)
        record = self._effective_repair_record(node_id)
        if record is None or authority.get("grant_id") != record.get("grant_id"):
            return super()._claim_provenance_issues(node_id, receipt)
        issues: list[str] = []
        original = str(record["original_claim_commit"])
        final = receipt.get("final_commit")
        if not self.git_object_exists(original):
            issues.append("ORCH sealed original claim object is unavailable")
            return tuple(issues)
        if self._commit_parents(original) != (record["claim_target_sha"],):
            issues.append("ORCH sealed original claim parent is invalid")
        if self._commit_tree(original) != record["claim_target_tree"]:
            issues.append("ORCH sealed original claim tree is invalid")
        shown = self._git(("show", "-s", "--format=%B", original), check=False)
        try:
            original_payload = json.loads(shown.stdout.strip()) if shown.returncode == 0 else None
        except json.JSONDecodeError:
            original_payload = None
        expected = {
            "kind": "hive-mind-autopilot-remote-claim-v1",
            "node_id": node_id,
            "target_sha": record["claim_target_sha"],
            "branch": record["branch"],
            "plan_fingerprint": record["plan_fingerprint"],
        }
        if not isinstance(original_payload, Mapping) or any(original_payload.get(key) != value for key, value in expected.items()):
            issues.append("ORCH sealed original claim payload is invalid")
        if not isinstance(final, str) or not self.is_ancestor(original, final):
            issues.append("ORCH replacement does not retain original claim ancestry")
        return tuple(dict.fromkeys(issues))

    def validate_receipt(
        self,
        node_id: str,
        value: object,
        *,
        require_integrated: bool = False,
    ) -> tuple[str, ...]:
        if node_id not in REPAIR_AUTHORITY_MATERIAL_DIGESTS or not isinstance(value, Mapping):
            return super().validate_receipt(node_id, value, require_integrated=require_integrated)
        authority = value.get("authority")
        if not isinstance(authority, Mapping) or "supersedes_receipt_commit" not in authority:
            return super().validate_receipt(node_id, value, require_integrated=require_integrated)
        issues = list(self._replacement_receipt_issues(node_id, value))
        final = value.get("final_commit")
        if require_integrated and self.verify_git_objects and isinstance(final, str) and not self.is_ancestor(final, self.current_target_sha()):
            issues.append("sealed replacement receipt is not integrated")
        return tuple(dict.fromkeys(issues))

    def resolve_sealed_repair_records(
        self,
        node_id: str,
        records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        record = self._effective_repair_record(node_id)
        if record is None or len(records) != 2:
            return records
        old = next((item for item in records if item.get("commit") == record["old_receipt_commit"]), None)
        replacement = next((item for item in records if item.get("commit") != record["old_receipt_commit"]), None)
        if old is None or replacement is None:
            return records
        old_receipt = old.get("receipt")
        new_receipt = replacement.get("receipt")
        if not isinstance(old_receipt, Mapping) or not isinstance(new_receipt, Mapping):
            return records
        if digest_json(old_receipt) != record["old_receipt_payload_digest"]:
            return records
        if old_receipt.get("pr") != record["expected_old_pr"]:
            return records
        if self._replacement_receipt_issues(node_id, new_receipt):
            return records
        return [replacement]

    def _receipt_index_contains(self, node_id: str, receipt_commit: str) -> bool:
        path = self.state_dir / "receipt-index.jsonl"
        if not path.is_file():
            return False
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, Mapping) and value.get("node_id") == node_id and value.get(
                "receipt_commit"
            ) == receipt_commit:
                return True
        return False

    def _recover_interrupted_repair_completion(
        self,
        node_id: str,
        owner: str,
        receipt: Mapping[str, Any],
        claim: Mapping[str, Any],
        record: Mapping[str, Any],
    ) -> str | None:
        intent_path = self.state_dir / f"sealed-repair-completion-{node_id.lower()}.json"
        if not intent_path.is_file():
            return None
        intent = read_json(intent_path)
        required = {
            "schema_version", "kind", "status", "node_id", "owner", "target_sha",
            "remote_expected_final", "receipt_digest", "receipt_commit",
            "active_claim_digest", "prepared_at",
        }
        if not isinstance(intent, Mapping) or set(intent) != required:
            raise ClaimError("sealed repair completion intent is foreign or malformed")
        if (
            intent.get("kind") != "hive-mind-autopilot-sealed-repair-completion-v1"
            or intent.get("status") != "PREPARED"
            or intent.get("node_id") != node_id
            or intent.get("owner") != owner
            or intent.get("receipt_digest") != digest_json(receipt)
        ):
            raise ClaimError("sealed repair completion intent identity is invalid")
        claimed_material = dict(claim)
        claimed_material["status"] = "CLAIMED"
        claimed_material.pop("adverse_reason", None)
        if intent.get("active_claim_digest") != digest_json(claimed_material):
            raise ClaimError("sealed repair completion intent claim binding is invalid")
        if claim.get("status") not in {"CLAIMED", "COMPLETING"} or intent.get("target_sha") != claim.get("target_sha"):
            raise ClaimError("sealed repair completion recovery target or state is invalid")
        final = str(intent["remote_expected_final"])
        receipt_commit = intent.get("receipt_commit")
        remote = self.remote_branch_sha(str(record["branch"]))

        def adverse(error: Exception) -> None:
            retained = dict(claim)
            retained["status"] = "ADVERSE"
            retained["adverse_reason"] = str(error)
            atomic_write_json(self.claim_path(node_id), retained)
            append_jsonl(self.state_dir / "sealed-repair-adverse.jsonl", {
                "event": "receipt_restart_recovery_failed", "node_id": node_id,
                "remote_head": remote, "receipt_commit": receipt_commit,
                "error": str(error),
            })

        if receipt_commit is None:
            if remote != final:
                error = ClaimError("sealed repair completion stopped before commit but remote moved")
                adverse(error)
                raise error
            local_ref = f"refs/heads/{record['branch']}"
            local = self._git(("rev-parse", "--verify", local_ref), check=False).stdout.strip()
            if local != final:
                if (
                    FULL_SHA.fullmatch(local) is None
                    or self._commit_parents(local) != (final,)
                    or self._commit_tree(local) != receipt.get("final_tree")
                ):
                    error = ReceiptError("sealed repair interrupted local receipt is ambiguous")
                    adverse(error)
                    raise error
                shown = self._git(("show", "-s", "--format=%B", local), check=False)
                local_receipt = self._parse_receipt_message(shown.stdout) if shown.returncode == 0 else None
                if not isinstance(local_receipt, Mapping) or digest_json(local_receipt) != digest_json(receipt):
                    error = ReceiptError("sealed repair interrupted local receipt payload is invalid")
                    adverse(error)
                    raise error
                rolled_back = self._git(("update-ref", local_ref, final, local), check=False)
                observed = self._git(("rev-parse", "--verify", local_ref), check=False).stdout.strip()
                if rolled_back.returncode != 0 or observed != final:
                    error = ReceiptError("sealed repair interrupted local receipt rollback failed")
                    adverse(error)
                    raise error
            restored = dict(claim)
            restored["status"] = "CLAIMED"
            atomic_write_json(self.claim_path(node_id), restored)
            intent_path.unlink()
            return None
        if not isinstance(receipt_commit, str) or FULL_SHA.fullmatch(receipt_commit) is None:
            error = ClaimError("sealed repair completion intent receipt commit is invalid")
            adverse(error)
            raise error
        if remote == final:
            local_ref = f"refs/heads/{record['branch']}"
            local = self._git(("rev-parse", "--verify", local_ref), check=False).stdout.strip()
            if local == receipt_commit:
                updated = self._git(("update-ref", local_ref, final, receipt_commit), check=False)
                local = self._git(("rev-parse", "--verify", local_ref), check=False).stdout.strip()
                if updated.returncode != 0 or local != final:
                    error = ReceiptError("sealed repair local receipt rollback failed")
                    adverse(error)
                    raise error
            elif local != final:
                error = ReceiptError("sealed repair local receipt ref is ambiguous")
                adverse(error)
                raise error
            restored = dict(claim)
            restored["status"] = "CLAIMED"
            atomic_write_json(self.claim_path(node_id), restored)
            intent_path.unlink()
            return None
        if remote != receipt_commit:
            error = ClaimError("sealed repair completion recovery remote head is ambiguous")
            adverse(error)
            raise error
        pr_issues = self._live_pr_metadata_issues(record, receipt_commit)
        if pr_issues:
            error = ClaimError("; ".join(pr_issues))
            adverse(error)
            raise error
        if self._commit_parents(receipt_commit) != (final,) or self._commit_tree(receipt_commit) != receipt.get("final_tree"):
            error = ReceiptError("sealed repair recovered receipt topology or tree is invalid")
            adverse(error)
            raise error
        shown = self._git(("show", "-s", "--format=%B", receipt_commit), check=False)
        recovered_receipt = self._parse_receipt_message(shown.stdout) if shown.returncode == 0 else None
        if not isinstance(recovered_receipt, Mapping) or digest_json(recovered_receipt) != digest_json(receipt):
            error = ReceiptError("sealed repair recovered receipt payload is invalid")
            adverse(error)
            raise error
        validation_owner = f"sealed-repair-completion:{owner}"
        validation = self.acquire_global_validation_lease(node_id, validation_owner, lease_minutes=30)
        try:
            local_path = self.receipt_path(node_id)
            if local_path.is_file():
                if digest_json(read_json(local_path)) != digest_json(receipt):
                    raise ReceiptError("sealed repair recovered local receipt conflicts")
            else:
                atomic_write_json(local_path, receipt)
            if not self._receipt_index_contains(node_id, receipt_commit):
                append_jsonl(
                    self.state_dir / "receipt-index.jsonl",
                    {
                        "node_id": node_id,
                        "receipt_commit": receipt_commit,
                        "receipt_digest": digest_json(receipt),
                        "final_commit": final,
                        "supersedes_receipt_commit": record["old_receipt_commit"],
                        "timestamp": receipt.get("timestamp"),
                    },
                )
            self.claim_path(node_id).unlink()
            intent_path.unlink()
            append_jsonl(self.state_dir / "sealed-repair-adverse.jsonl", {
                "event": "receipt_publication_recovered_after_restart",
                "node_id": node_id, "receipt_commit": receipt_commit,
            })
            return receipt_commit
        finally:
            self.release_global_validation_lease(
                node_id, validation_owner, lease_id=str(validation["lease_id"])
            )

    def complete(self, node_id: str, owner: str, receipt: Mapping[str, Any]) -> str:
        if node_id not in REPAIR_AUTHORITY_MATERIAL_DIGESTS:
            return super().complete(node_id, owner, receipt)
        record = self._repair_record(node_id)
        if not self._origin_is_configured_repository(record):
            raise ClaimError("sealed repair completion requires literal configured origin")
        claim_path = self.claim_path(node_id)
        if not claim_path.is_file():
            recovered = self._recover_terminal_repair_completion_without_claim(
                node_id, owner, receipt, record
            )
            if recovered is not None:
                return recovered
            raise ClaimError("sealed repair completion requires an active claim")
        claim = read_json(claim_path)
        if not isinstance(claim, Mapping) or claim.get("kind") != REPAIR_CLAIM_KIND:
            raise ClaimError("sealed repair completion claim is invalid")
        if claim.get("owner") != owner:
            raise ClaimError("sealed repair completion owner differs")
        if claim.get("authority_digest") != digest_json(record):
            raise ClaimError("sealed repair completion claim authority is stale")
        recovered = self._recover_interrupted_repair_completion(
            node_id, owner, receipt, claim, record
        )
        if recovered is not None:
            return recovered
        claim = read_json(claim_path)
        if not isinstance(claim, Mapping):
            raise ClaimError("sealed repair completion claim disappeared during recovery")
        final = receipt.get("final_commit")
        continuation = (
            node_id == "OPTIMIZER-370"
            and self.current_target_sha() != claim.get("target_sha")
            and isinstance(final, str)
            and not self._optimizer_continuation_issues(
                claim, receipt, expected_pr_head=final
            )
        )
        live_issues = (
            () if continuation
            else self._live_release_issues(record, str(claim.get("target_sha")))
        )
        if live_issues:
            raise ClaimError("; ".join(live_issues))
        if parse_time(claim.get("expires_at")) <= self.clock() and not continuation:
            raise ClaimError("sealed repair completion lease expired")
        binding_issues = self._release_binding_issues() if continuation else self._release_binding_issues(claim)
        if binding_issues:
            raise ClaimError("; ".join(binding_issues))
        local_path = self.receipt_path(node_id)
        if local_path.exists():
            raise ReceiptError("sealed repair cannot overwrite a local receipt")
        if not isinstance(final, str) or self.remote_branch_sha(str(record["branch"])) != final:
            raise ReceiptError("sealed repair remote branch must equal the exact final candidate")
        issues = self._replacement_receipt_issues(node_id, receipt, active_claim=claim)
        if issues:
            raise ReceiptError("; ".join(issues))
        validation_owner = f"sealed-repair-completion:{owner}"
        validation = self.acquire_global_validation_lease(node_id, validation_owner, lease_minutes=30)
        receipt_commit: str | None = None
        remote_published = False
        intent_path = self.state_dir / f"sealed-repair-completion-{node_id.lower()}.json"
        claim_state = dict(claim)
        try:
            if (self._release_binding_issues() if continuation else self._release_binding_issues(claim)):
                raise ClaimError("sealed repair release changed before receipt publication")
            if self.remote_branch_sha(str(record["branch"])) != final:
                raise ReceiptError("sealed repair remote final moved before receipt publication")
            pr_issues = self._live_pr_metadata_issues(record, str(final))
            if pr_issues:
                raise ClaimError("; ".join(pr_issues))
            if continuation:
                continuation_issues = self._optimizer_continuation_issues(
                    claim, receipt, expected_pr_head=str(final)
                )
                if continuation_issues:
                    raise ClaimError("; ".join(continuation_issues))
            intent = {
                "schema_version": 1,
                "kind": "hive-mind-autopilot-sealed-repair-completion-v1",
                "status": "PREPARED",
                "node_id": node_id,
                "owner": owner,
                "target_sha": claim["target_sha"],
                "remote_expected_final": final,
                "receipt_digest": digest_json(receipt),
                "receipt_commit": None,
                "active_claim_digest": digest_json(claim),
                "prepared_at": format_time(self.clock()),
            }
            atomic_write_json(intent_path, intent)
            claim_state["status"] = "COMPLETING"
            atomic_write_json(claim_path, claim_state)
            receipt_commit = self._create_receipt_commit(node_id, receipt)
            intent["receipt_commit"] = receipt_commit
            atomic_write_json(intent_path, intent)
            self.assert_global_validation_lease(
                node_id, validation_owner, lease_id=str(validation["lease_id"])
            )
            self._cas_update_branch(str(record["branch"]), str(final), receipt_commit)
            remote_published = self.remote_branch_sha(str(record["branch"])) == receipt_commit
            if not remote_published:
                raise ReceiptError("sealed repair receipt remote CAS verification failed")
            self.assert_global_validation_lease(
                node_id, validation_owner, lease_id=str(validation["lease_id"])
            )
            if (self._release_binding_issues() if continuation else self._release_binding_issues(claim)):
                raise ClaimError("sealed repair release changed during receipt publication")
            live_issues = (
                () if continuation
                else self._live_release_issues(record, str(claim["target_sha"]))
            )
            if live_issues:
                raise ClaimError("; ".join(live_issues))
            pr_issues = self._live_pr_metadata_issues(record, receipt_commit)
            if pr_issues:
                raise ClaimError("; ".join(pr_issues))
            if continuation:
                continuation_issues = self._optimizer_continuation_issues(
                    claim, receipt, expected_pr_head=receipt_commit
                )
                if continuation_issues:
                    raise ClaimError("; ".join(continuation_issues))
            atomic_write_json(local_path, receipt)
            append_jsonl(
                self.state_dir / "receipt-index.jsonl",
                {
                    "node_id": node_id,
                    "receipt_commit": receipt_commit,
                    "receipt_digest": digest_json(receipt),
                    "final_commit": final,
                    "supersedes_receipt_commit": record["old_receipt_commit"],
                    "timestamp": receipt.get("timestamp"),
                },
            )
            claim_path.unlink()
            intent_path.unlink(missing_ok=True)
            return receipt_commit
        except Exception:
            compensated = not remote_published
            if receipt_commit is not None and self.remote_branch_sha(str(record["branch"])) == receipt_commit:
                try:
                    self._cas_update_branch(str(record["branch"]), receipt_commit, str(final))
                    compensated = self.remote_branch_sha(str(record["branch"])) == final
                except ClaimError:
                    compensated = False
            local_rolled_back = receipt_commit is None
            if receipt_commit is not None:
                local_ref = f"refs/heads/{record['branch']}"
                local_update = self._git(("update-ref", local_ref, str(final), receipt_commit), check=False)
                local_head = self._git(("rev-parse", "--verify", local_ref), check=False).stdout.strip()
                local_rolled_back = local_update.returncode == 0 and local_head == final
            local_path.unlink(missing_ok=True)
            if compensated and local_rolled_back:
                claim_state["status"] = "CLAIMED"
                atomic_write_json(claim_path, claim_state)
                intent_path.unlink(missing_ok=True)
            else:
                claim_state["status"] = "ADVERSE"
                claim_state["adverse_reason"] = "receipt publication could not be rolled back"
                atomic_write_json(claim_path, claim_state)
                append_jsonl(self.state_dir / "sealed-repair-adverse.jsonl", {
                    "event": "receipt_compensation_failed", "node_id": node_id,
                    "receipt_commit": receipt_commit, "final_commit": final,
                })
            raise
        finally:
            self.release_global_validation_lease(
                node_id, validation_owner, lease_id=str(validation["lease_id"])
            )

    def _recover_terminal_repair_completion_without_claim(
        self,
        node_id: str,
        owner: str,
        receipt: Mapping[str, Any],
        record: Mapping[str, Any],
    ) -> str | None:
        intent_path = self.state_dir / f"sealed-repair-completion-{node_id.lower()}.json"
        if not intent_path.is_file():
            return None
        intent = read_json(intent_path)
        required = {
            "schema_version", "kind", "status", "node_id", "owner", "target_sha",
            "remote_expected_final", "receipt_digest", "receipt_commit",
            "active_claim_digest", "prepared_at",
        }
        if (
            not isinstance(intent, Mapping)
            or set(intent) != required
            or intent.get("kind") != "hive-mind-autopilot-sealed-repair-completion-v1"
            or intent.get("status") != "PREPARED"
            or intent.get("node_id") != node_id
            or intent.get("owner") != owner
            or intent.get("receipt_digest") != digest_json(receipt)
        ):
            raise ClaimError("sealed repair terminal completion intent is invalid")
        receipt_commit = intent.get("receipt_commit")
        if not isinstance(receipt_commit, str) or FULL_SHA.fullmatch(receipt_commit) is None:
            raise ClaimError("sealed repair terminal completion lacks exact receipt commit")
        if self.remote_branch_sha(str(record["branch"])) != receipt_commit:
            raise ClaimError("sealed repair terminal completion remote head is ambiguous")
        local_path = self.receipt_path(node_id)
        if not local_path.is_file() or digest_json(read_json(local_path)) != digest_json(receipt):
            raise ClaimError("sealed repair terminal completion local receipt is missing")
        if not self._receipt_index_contains(node_id, receipt_commit):
            raise ClaimError("sealed repair terminal completion index is missing")
        if (
            self._commit_parents(receipt_commit) != (intent.get("remote_expected_final"),)
            or self._commit_tree(receipt_commit) != receipt.get("final_tree")
        ):
            raise ClaimError("sealed repair terminal completion topology is invalid")
        shown = self._git(("show", "-s", "--format=%B", receipt_commit), check=False)
        recovered = self._parse_receipt_message(shown.stdout) if shown.returncode == 0 else None
        if not isinstance(recovered, Mapping) or digest_json(recovered) != digest_json(receipt):
            raise ClaimError("sealed repair terminal completion payload is invalid")
        intent_path.unlink()
        append_jsonl(self.state_dir / "sealed-repair-adverse.jsonl", {
            "event": "receipt_terminal_cleanup_recovered_after_restart",
            "node_id": node_id,
            "receipt_commit": receipt_commit,
        })
        return receipt_commit

    @property
    def builder_execution_path(self) -> Path:
        return self.state_dir / BUILDER_EXECUTION_FILE

    @property
    def builder_recovery_path(self) -> Path:
        return self.state_dir / BUILDER_RECOVERY_FILE

    @property
    def builder_lease_path(self) -> Path:
        return self.state_dir / BUILDER_LEASE_FILE

    @property
    def builder_intent_path(self) -> Path:
        return self.state_dir / BUILDER_INTENT_FILE

    def _builder_execution(self) -> Mapping[str, Any] | None:
        if not self.builder_execution_path.is_file():
            return None
        value = read_json(self.builder_execution_path)
        required = {
            "schema_version", "kind", "status", "recovery_id", "source_head",
            "archive_ref", "snapshot_digest", "reconciliation_digest", "doctor_evidence_digest",
            "target_sha", "release_id", "actor", "authority_digest", "replan_digest",
            "validation_lease_id", "validation_lease_digest", "completed_at",
        }
        if not isinstance(value, Mapping) or set(value) != required:
            raise AutopilotError("Builder retirement execution record is invalid")
        if value.get("kind") != BUILDER_EXECUTION_KIND or value.get("status") != "RETIRED":
            raise AutopilotError("Builder retirement execution disposition is invalid")
        if (
            value.get("schema_version") != 1
            or value.get("recovery_id") != BUILDER_RECOVERY_ID
            or FULL_SHA.fullmatch(str(value.get("source_head", ""))) is None
            or value.get("archive_ref")
            != "refs/hive-mind-autopilot/archive/builder-330/01ee3ec1bd3bfb0bc18bbdea70a428b16b96ee64"
            or FULL_SHA.fullmatch(str(value.get("target_sha", ""))) is None
            or any(
                not isinstance(value.get(key), str) or not str(value.get(key)).strip()
                for key in (
                    "snapshot_digest", "reconciliation_digest", "doctor_evidence_digest",
                    "release_id", "actor", "validation_lease_id",
                    "validation_lease_digest", "completed_at",
                )
            )
            or DIGEST_SHA256.fullmatch(str(value.get("authority_digest", ""))) is None
            or value.get("replan_digest")
            != BUILDER_SUCCESSOR_DIGESTS[BUILDER_SUCCESSOR_REPLAN_PATH]
        ):
            raise AutopilotError("Builder retirement execution semantics are invalid")
        try:
            if format_time(parse_time(value["completed_at"])) != value["completed_at"]:
                raise ValueError
        except (TypeError, ValueError):
            raise AutopilotError("Builder retirement execution timestamp is invalid") from None
        return value

    def _builder_recovery_issues(self) -> tuple[str, ...]:
        execution = self._builder_execution()
        if execution is None:
            return ()
        recovery = self._builder_document(f".autopilot/state/{BUILDER_RECOVERY_FILE}")
        required = {
            "schema_version", "kind", "recovery_id", "snapshot_digest",
            "reconciliation_digest", "doctor_evidence_digest", "target_sha",
            "live_ref_attestation_digest", "live_ref_attested_at", "recorded_at",
        }
        if not isinstance(recovery, Mapping) or set(recovery) != required:
            return ("Builder retirement requires fresh snapshot, reconciliation, and doctor before dispatch",)
        if recovery.get("kind") != BUILDER_EXECUTION_KIND:
            return ("Builder retirement recovery record kind is invalid",)
        if recovery.get("snapshot_digest") != self._snapshot_digest():
            return ("Builder retirement snapshot is not fresh",)
        if recovery.get("reconciliation_digest") != self._reconciliation_digest():
            return ("Builder retirement reconciliation is not fresh",)
        if recovery.get("doctor_evidence_digest") != self._doctor_evidence_digest():
            return ("Builder retirement doctor evidence is not fresh",)
        if recovery.get("target_sha") != self.current_target_sha():
            return ("Builder retirement recovery target is stale",)
        replan = self._builder_document(BUILDER_SUCCESSOR_REPLAN_PATH) or {}
        bootstrap = self._builder_document(BUILDER_SUCCESSOR_BOOTSTRAP_PATH) or {}
        topology = self._builder_successor_topology(replan)
        if (
            execution.get("recovery_id") != BUILDER_RECOVERY_ID
            or execution.get("authority_digest") != digest_json(bootstrap)
            or execution.get("replan_digest") != BUILDER_SUCCESSOR_DIGESTS[BUILDER_SUCCESSOR_REPLAN_PATH]
            or recovery.get("recovery_id") != BUILDER_RECOVERY_ID
        ):
            return ("Builder retirement execution or recovery authority binding is stale",)
        live_issues = self._builder_successor_release_issues(
            replan, self.current_target_sha()
        )
        if live_issues:
            return tuple(live_issues)
        branches = self._snapshot_rows("branches", "name", topology.branch)
        refs = self._snapshot_rows("refs", "name", topology.archive_ref)
        expected_live_source: object = None
        if branches:
            claim = self.active_claims().get("BUILDER-330")
            branch_sha = branches[0].get("sha") if len(branches) == 1 else None
            if not (
                isinstance(claim, Mapping)
                and claim.get("kind") == BUILDER_CLAIM_KIND
                and not self._builder_successor_claim_issues(claim)
                and claim.get("target_sha") == self.current_target_sha()
                and claim.get("branch") == topology.branch
                and claim.get("remote_claim_commit") == branch_sha
                and claim.get("remote") == "origin"
                and branch_sha != topology.source_head
            ):
                return ("Builder retirement fresh snapshot contains an unbound canonical source",)
            shown = self._git(("show", "-s", "--format=%B", str(branch_sha)), check=False)
            try:
                claim_payload = json.loads(shown.stdout.strip()) if shown.returncode == 0 else None
            except json.JSONDecodeError:
                claim_payload = None
            expected_claim = self._builder_successor_claim_payload(claim)
            if not isinstance(claim_payload, Mapping) or dict(claim_payload) != expected_claim:
                return ("Builder retirement fresh claim commit payload is invalid",)
            expected_live_source = branch_sha
        if len(refs) != 1 or refs[0].get("sha") != topology.source_head:
            return ("Builder retirement fresh snapshot omits the exact archive ref",)
        if self._snapshot_rows("pull_requests", "node_id", "BUILDER-330"):
            return ("Builder retirement fresh snapshot assigns an aggregate PR to Builder",)
        live_source = self._remote_ref_sha(topology.source_ref)
        live_archive = self._remote_ref_sha(topology.archive_ref)
        live_legacy_archive = self._remote_ref_sha(topology.legacy_archive_ref)
        if live_source != expected_live_source or live_archive != topology.source_head or live_legacy_archive is not None:
            return ("Builder retirement live source/archive attestation differs from fresh snapshot",)
        live_material = {
            "source_ref": topology.source_ref,
            "source_sha": live_source,
            "archive_ref": topology.archive_ref,
            "archive_sha": live_archive,
            "legacy_archive_ref": topology.legacy_archive_ref,
            "legacy_archive_sha": live_legacy_archive,
        }
        if recovery.get("live_ref_attestation_digest") != digest_json(live_material):
            return ("Builder retirement persisted live ref attestation is stale",)
        return ()

    def after_install_github_snapshot(self) -> None:
        if self._builder_execution() is not None:
            replan = self._builder_document(BUILDER_SUCCESSOR_REPLAN_PATH) or {}
            topology = self._builder_successor_topology(replan)
            attested_at = format_time(self.clock())
            live_material = {
                "source_ref": topology.source_ref,
                "source_sha": self._remote_ref_sha(topology.source_ref),
                "archive_ref": topology.archive_ref,
                "archive_sha": self._remote_ref_sha(topology.archive_ref),
                "legacy_archive_ref": topology.legacy_archive_ref,
                "legacy_archive_sha": self._remote_ref_sha(topology.legacy_archive_ref),
            }
            atomic_write_json(
                self.builder_recovery_path,
                {
                    "schema_version": 1,
                    "kind": BUILDER_EXECUTION_KIND,
                    "recovery_id": BUILDER_RECOVERY_ID,
                    "snapshot_digest": self._snapshot_digest(),
                    "reconciliation_digest": None,
                    "doctor_evidence_digest": None,
                    "target_sha": self.current_target_sha(),
                    "live_ref_attestation_digest": digest_json(live_material),
                    "live_ref_attested_at": attested_at,
                    "recorded_at": attested_at,
                },
            )

    def after_reconcile(self) -> None:
        if self._builder_execution() is None or not self.builder_recovery_path.is_file():
            return
        recovery = read_json(self.builder_recovery_path)
        if not isinstance(recovery, Mapping) or recovery.get("snapshot_digest") != self._snapshot_digest():
            return
        updated = dict(recovery)
        updated["reconciliation_digest"] = self._reconciliation_digest()
        updated["doctor_evidence_digest"] = None
        updated["target_sha"] = self.current_target_sha()
        updated["recorded_at"] = format_time(self.clock())
        atomic_write_json(self.builder_recovery_path, updated)

    def after_doctor(self) -> None:
        if self._builder_execution() is None or not self.builder_recovery_path.is_file():
            return
        recovery = read_json(self.builder_recovery_path)
        if not isinstance(recovery, Mapping):
            return
        if recovery.get("snapshot_digest") != self._snapshot_digest() or recovery.get(
            "reconciliation_digest"
        ) != self._reconciliation_digest():
            return
        updated = dict(recovery)
        updated["doctor_evidence_digest"] = self._doctor_evidence_digest()
        updated["recorded_at"] = format_time(self.clock())
        atomic_write_json(self.builder_recovery_path, updated)

    def _builder_successor_topology(
        self,
        replan: Mapping[str, Any],
    ) -> BuilderSuccessorTopology:
        chain = replan["forensic_chain"]
        quarantine = replan["aggregate_quarantine"]
        adverse = quarantine["adverse_extension"]
        if not all(isinstance(value, Mapping) for value in (chain, quarantine, adverse)):
            raise ClaimError("Builder successor topology record is malformed")
        return BuilderSuccessorTopology(
            branch=str(replan["branch"]), source_ref=str(replan["source_ref"]),
            source_head=str(replan["expected_remote_head"]), source_tree=str(replan["expected_remote_tree"]),
            archive_ref=str(replan["archive_ref"]), legacy_archive_ref=str(replan["legacy_archive_ref"]),
            preserved_paths=tuple(str(path) for path in replan["preserved_candidate_paths"]),
            old_claim=str(chain["old_claim"]), old_claim_parent=str(chain["old_claim_parent"]),
            old_claim_tree=str(chain["old_claim_tree"]),
            old_claim_payload_digest=str(chain["old_claim_payload_digest"]),
            old_candidate=str(chain["old_candidate"]), old_candidate_tree=str(chain["old_candidate_tree"]),
            legacy_merge=str(chain["legacy_merge"]),
            legacy_merge_parents=tuple(chain["legacy_merge_parents"]),
            legacy_merge_tree=str(chain["legacy_merge_tree"]), foreign_base=str(chain["foreign_base"]),
            foreign_base_parent=str(chain["foreign_base_parent"]), foreign_base_tree=str(chain["foreign_base_tree"]),
            repair_claim=str(chain["repair_claim"]), repair_claim_parent=str(chain["repair_claim_parent"]),
            repair_claim_tree=str(chain["repair_claim_tree"]),
            repair_claim_payload_digest=str(chain["repair_claim_payload_digest"]),
            candidate=str(chain["candidate"]), candidate_parent=str(chain["candidate_parent"]),
            candidate_tree=str(chain["candidate_tree"]), receipt=str(chain["receipt"]),
            receipt_parent=str(chain["receipt_parent"]), receipt_tree=str(chain["receipt_tree"]),
            receipt_payload_digest=str(chain["receipt_payload_digest"]), r4_ref=str(quarantine["r4_ref"]),
            r4_head=str(quarantine["r4_head"]), r4_head_tree=str(quarantine["r4_head_tree"]),
            prior_r4_head=str(quarantine["prior_r4_head"]),
            adverse_extension_parent=str(adverse["parent"]),
            adverse_extension_paths=tuple(str(path) for path in adverse["changed_paths"]),
            canonical_receipt_merge=str(quarantine["canonical_receipt_merge"]),
            canonical_receipt_merge_parents=tuple(quarantine["canonical_receipt_merge_parents"]),
            canonical_receipt_merge_tree=str(quarantine["canonical_receipt_merge_tree"]),
            other_candidate=str(quarantine["other_candidate"]),
            other_candidate_parent=str(quarantine["other_candidate_parent"]),
            other_receipt=str(quarantine["other_receipt"]),
            other_receipt_digest=str(quarantine["other_receipt_digest"]),
            other_receipt_merge=str(quarantine["other_receipt_merge"]),
            other_receipt_merge_parents=tuple(quarantine["other_receipt_merge_parents"]),
            other_receipt_merge_tree=str(quarantine["other_receipt_merge_tree"]),
            expected_builder_receipts=tuple(quarantine["expected_builder_receipts"]),
        )

    def _commit_json_payload_digest(self, commit: str, *, receipt: bool) -> str | None:
        message = self._git(("show", "-s", "--format=%B", commit), check=False).stdout
        value = self._parse_receipt_message(message) if receipt else None
        if not receipt:
            try:
                parsed = json.loads(message.strip())
            except json.JSONDecodeError:
                parsed = None
            value = parsed if isinstance(parsed, Mapping) else None
        return digest_json(value) if isinstance(value, Mapping) else None

    def _builder_history_issues(self, replan: Mapping[str, Any]) -> tuple[str, ...]:
        if not self.verify_git_objects:
            return ()
        topology = self._builder_successor_topology(replan)
        issues: list[str] = []
        parent_expectations = {
            topology.old_claim: (topology.old_claim_parent,),
            topology.old_candidate: (topology.old_claim,),
            topology.legacy_merge: topology.legacy_merge_parents,
            topology.foreign_base: (topology.foreign_base_parent,),
            topology.repair_claim: (topology.repair_claim_parent,),
            topology.candidate: (topology.candidate_parent,),
            topology.receipt: (topology.receipt_parent,),
            topology.canonical_receipt_merge: topology.canonical_receipt_merge_parents,
            topology.other_candidate: (topology.other_candidate_parent,),
            topology.other_receipt: (topology.other_candidate,),
            topology.other_receipt_merge: topology.other_receipt_merge_parents,
            topology.r4_head: (topology.adverse_extension_parent,),
        }
        tree_expectations = {
            topology.old_claim: topology.old_claim_tree,
            topology.old_candidate: topology.old_candidate_tree,
            topology.legacy_merge: topology.legacy_merge_tree,
            topology.foreign_base: topology.foreign_base_tree,
            topology.repair_claim: topology.repair_claim_tree,
            topology.candidate: topology.candidate_tree,
            topology.receipt: topology.receipt_tree,
            topology.canonical_receipt_merge: topology.canonical_receipt_merge_tree,
            topology.other_candidate: topology.candidate_tree,
            topology.other_receipt: topology.candidate_tree,
            topology.other_receipt_merge: topology.other_receipt_merge_tree,
            topology.r4_head: topology.r4_head_tree,
        }
        for commit, parents in parent_expectations.items():
            if self._commit_parents(commit) != tuple(parents):
                issues.append(f"Builder successor parent topology differs at {commit}")
        for commit, tree in tree_expectations.items():
            if self._commit_tree(commit) != tree:
                issues.append(f"Builder successor tree differs at {commit}")
        if self._commit_json_payload_digest(topology.old_claim, receipt=False) != topology.old_claim_payload_digest:
            issues.append("Builder successor old claim payload differs")
        if self._commit_json_payload_digest(topology.repair_claim, receipt=False) != topology.repair_claim_payload_digest:
            issues.append("Builder successor repair claim payload differs")
        if self._commit_json_payload_digest(topology.receipt, receipt=True) != topology.receipt_payload_digest:
            issues.append("Builder successor canonical receipt payload differs")
        if self._commit_json_payload_digest(topology.other_receipt, receipt=True) != topology.other_receipt_digest:
            issues.append("Builder successor quarantined receipt payload differs")
        if tuple(sorted(self._diff_paths(topology.old_claim_parent, topology.old_candidate))) != tuple(
            sorted(topology.preserved_paths)
        ):
            issues.append("Builder successor legacy candidate scope differs")
        if tuple(sorted(self._diff_paths(topology.foreign_base, topology.candidate))) != tuple(
            sorted(topology.preserved_paths)
        ):
            issues.append("Builder successor foreign candidate scope differs")
        if self._diff_paths(topology.candidate, topology.receipt):
            issues.append("Builder successor canonical receipt is not zero-path")
        if tuple(self._diff_paths(topology.prior_r4_head, topology.r4_head)) != tuple(
            sorted(topology.adverse_extension_paths)
        ):
            issues.append("Builder successor r4 adverse-extension scope differs")
        for ancestor in (
            topology.old_claim, topology.old_candidate, topology.legacy_merge,
            topology.foreign_base, topology.repair_claim, topology.candidate,
            topology.receipt, topology.canonical_receipt_merge, topology.other_receipt,
            topology.other_receipt_merge, topology.prior_r4_head,
        ):
            if not self.is_ancestor(ancestor, topology.r4_head):
                issues.append(f"Builder successor r4 omits sealed ancestry {ancestor}")
        completed = self._git(
            ("log", "--format=%H%x1f%B%x1e", f"{topology.foreign_base}..{topology.r4_head}"),
            check=False,
        )
        receipts: list[str] = []
        if completed.returncode == 0:
            for raw in completed.stdout.split("\x1e"):
                parts = raw.strip("\n").split("\x1f", 1)
                if len(parts) == 2:
                    payload = self._parse_receipt_message(parts[1])
                    if isinstance(payload, Mapping) and payload.get("node_id") == "BUILDER-330":
                        receipts.append(parts[0])
        if tuple(sorted(receipts)) != tuple(sorted(topology.expected_builder_receipts)):
            issues.append("Builder successor r4 receipt set is expanded or incomplete")
        return tuple(dict.fromkeys(issues))

    def _builder_successor_release_issues(
        self,
        replan: Mapping[str, Any],
        target: str,
    ) -> tuple[str, ...]:
        topology = self._builder_successor_topology(replan)
        incident = replan["incident_release"]
        protected_main = replan["protected_main"]
        bootstrap = self._builder_document(BUILDER_SUCCESSOR_BOOTSTRAP_PATH) or {}
        issues: list[str] = []
        if not isinstance(incident, Mapping) or target == str(incident.get("commit")):
            issues.append("Builder successor requires a post-G release containing the capability")
        elif self.verify_git_objects and not self.is_ancestor(str(incident.get("commit")), target):
            issues.append("Builder successor execution release does not descend from G")
        if self.verify_git_objects and isinstance(incident, Mapping):
            incident_commit = str(incident.get("commit"))
            if self._commit_tree(incident_commit) != incident.get("tree"):
                issues.append("Builder successor G tree differs from sealed evidence")
            if self._commit_parents(incident_commit) != tuple(incident.get("parents", ())):
                issues.append("Builder successor G parents differ from sealed evidence")
        capability = bootstrap.get("capability_commit")
        if self.verify_git_objects and (
            not isinstance(capability, str) or not self.is_ancestor(capability, target)
        ):
            issues.append("Builder successor execution release omits exact capability")
        if self.verify_git_objects and isinstance(incident, Mapping):
            changed = set(self._diff_paths(str(incident.get("commit")), target))
            overlap = changed.intersection(topology.preserved_paths)
            if overlap:
                issues.append("Builder successor execution release changed preserved Builder scope")
            for forbidden in (
                topology.r4_head, topology.prior_r4_head, topology.canonical_receipt_merge,
                topology.other_receipt_merge, topology.other_receipt, topology.receipt,
            ):
                if self.is_ancestor(forbidden, target):
                    issues.append(f"Builder successor execution release contains quarantined ancestry {forbidden}")
        if not isinstance(protected_main, Mapping) or self._remote_ref_sha(str(protected_main.get("ref"))) != protected_main.get("commit"):
            issues.append("Builder successor protected main differs from sealed evidence")
        if self._remote_ref_sha(topology.r4_ref) != topology.r4_head:
            issues.append("Builder successor live r4 ref differs from sealed adverse extension")
        issues.extend(self._live_release_issues(replan, target))
        issues.extend(self._live_pr_metadata_issues(replan, topology.r4_head))
        return tuple(dict.fromkeys(issues))

    def _fetch_builder_successor_refs(
        self,
        topology: BuilderSuccessorTopology,
        *,
        source_remote_ref: str | None = None,
    ) -> tuple[str, str]:
        source_fetch = f"refs/hive-mind-autopilot/repair-fetch/builder-330/{topology.source_head}"
        r4_fetch = f"refs/hive-mind-autopilot/repair-fetch/builder-330/{topology.r4_head}"
        for reference in (source_fetch, r4_fetch):
            self._git(("update-ref", "-d", reference), check=False)
        source = source_remote_ref or topology.source_ref
        fetched_source = self._git(("fetch", "--no-tags", "origin", f"{source}:{source_fetch}"), check=False)
        fetched_r4 = self._git(("fetch", "--no-tags", "origin", f"{topology.r4_ref}:{r4_fetch}"), check=False)
        observed_source = self._git(("rev-parse", "--verify", source_fetch), check=False).stdout.strip()
        observed_r4 = self._git(("rev-parse", "--verify", r4_fetch), check=False).stdout.strip()
        if (
            fetched_source.returncode != 0 or fetched_r4.returncode != 0
            or observed_source != topology.source_head or observed_r4 != topology.r4_head
        ):
            for reference in (source_fetch, r4_fetch):
                self._git(("update-ref", "-d", reference), check=False)
            raise ClaimError("Builder successor cannot fetch exact source and r4 evidence")
        return source_fetch, r4_fetch

    def _recover_expired_builder_lease(self, replan: Mapping[str, Any]) -> None:
        if not self.builder_lease_path.is_file():
            return
        value = read_json(self.builder_lease_path)
        required = {
            "schema_version", "kind", "recovery_id", "node_id", "actor",
            "source_head", "archive_ref", "target_sha", "release_id",
            "authority_digest", "replan_digest", "validation_owner",
            "validation_lease_id", "validation_lease_digest", "expires_at", "status",
        }
        if not isinstance(value, Mapping) or set(value) != required:
            raise ClaimError("Builder retirement existing lease is foreign or malformed")
        if value.get("kind") != BUILDER_EXECUTION_KIND or value.get("status") != "ACTIVE":
            raise ClaimError("Builder retirement existing lease requires reconciliation")
        if parse_time(value.get("expires_at")) > self.clock():
            raise ClaimError("Builder retirement lease already exists")
        topology = self._builder_successor_topology(replan)
        if self._remote_ref_sha(topology.source_ref) != topology.source_head or self._remote_ref_sha(
            topology.archive_ref
        ) is not None:
            raise ClaimError("expired Builder lease cannot be recovered after ref mutation")
        archive = self.state_dir / "builder-retirement-leases" / (digest_json(value).replace(":", "-") + ".json")
        atomic_write_json(archive, {**value, "status": "EXPIRED_RECOVERED", "recovered_at": format_time(self.clock())})
        self.builder_lease_path.unlink()

    def _resume_builder_validation_lease(
        self,
        intent: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        scope, mutex_dir = self._validation_mutex_scope()
        path = mutex_dir / "global-validation-lease.json"
        if not path.is_file():
            raise ClaimError("Builder retirement shared validation mutex is missing")
        current, _ = self._read_validation_lease(path, scope)
        expected_owner = intent.get("validation_owner")
        if (
            current.get("node_id") != "BUILDER-330"
            or current.get("owner") != expected_owner
            or current.get("lease_id") != intent.get("validation_lease_id")
            or digest_json(current) != intent.get("validation_lease_digest")
        ):
            raise ClaimError("Builder retirement shared validation mutex identity differs")
        if parse_time(current.get("expires_at")) <= self.clock():
            replacement = self.acquire_global_validation_lease(
                "BUILDER-330", str(expected_owner), lease_minutes=30
            )
            return replacement
        self._held_validation_leases[("BUILDER-330", str(expected_owner))] = (
            str(current["lease_id"]),
            str(current["lease_token"]),
        )
        return current

    def _release_builder_validation_lease(self, value: Mapping[str, Any]) -> None:
        owner = str(value["validation_owner"])
        lease_id = str(value["validation_lease_id"])
        if self.validation_lease_path.is_file():
            self.release_global_validation_lease("BUILDER-330", owner, lease_id=lease_id)

    def _recover_interrupted_builder_retirement(
        self,
        replan: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        if not self.builder_intent_path.is_file():
            return None
        intent = read_json(self.builder_intent_path)
        required = {
            "schema_version", "kind", "status", "recovery_id", "source_head",
            "archive_ref", "target_sha", "release_id", "snapshot_digest",
            "reconciliation_digest", "doctor_evidence_digest", "actor",
            "authority_digest", "replan_digest", "validation_owner",
            "validation_lease_id", "validation_lease_digest", "lease_digest", "prepared_at",
        }
        if isinstance(intent, Mapping) and intent.get("status") == "REMOTE_RETIRED_PENDING_VERIFICATION":
            required = required | {"remote_retired_at"}
        if not isinstance(intent, Mapping) or set(intent) != required:
            raise ClaimError("Builder retirement prepared intent is foreign or malformed")
        if intent.get("kind") != BUILDER_EXECUTION_KIND or intent.get("status") not in {
            "PREPARED", "REMOTE_RETIRED_PENDING_VERIFICATION",
        }:
            raise ClaimError("Builder retirement prepared intent requires reconciliation")
        bootstrap = self._builder_document(BUILDER_SUCCESSOR_BOOTSTRAP_PATH) or {}
        if (
            intent.get("authority_digest") != digest_json(bootstrap)
            or intent.get("replan_digest") != digest_json(replan)
        ):
            raise ClaimError("Builder interrupted retirement authority binding differs")
        if not self.builder_lease_path.is_file():
            raise ClaimError("Builder interrupted retirement lease is missing")
        lease = read_json(self.builder_lease_path)
        if not isinstance(lease, Mapping) or digest_json(lease) != intent.get("lease_digest"):
            raise ClaimError("Builder interrupted retirement lease binding differs")
        for key in (
            "recovery_id", "source_head", "archive_ref", "target_sha", "release_id", "actor",
            "authority_digest", "replan_digest", "validation_owner", "validation_lease_id",
            "validation_lease_digest",
        ):
            if lease.get(key) != intent.get(key):
                raise ClaimError(f"Builder interrupted retirement lease {key} differs")
        topology = self._builder_successor_topology(replan)
        source = self._remote_ref_sha(topology.source_ref)
        archive = self._remote_ref_sha(topology.archive_ref)
        if (source, archive) not in {
            (topology.source_head, None), (None, topology.source_head),
        }:
            adverse = dict(intent)
            adverse["status"] = "ADVERSE"
            adverse["adverse_reason"] = "source/archive state is ambiguous"
            adverse["recorded_at"] = format_time(self.clock())
            atomic_write_json(self.builder_intent_path, adverse)
            raise ClaimError("Builder retirement prepared transaction refs are ambiguous")
        validation = self._resume_builder_validation_lease(intent)
        if validation.get("lease_id") != intent.get("validation_lease_id"):
            lease = {
                **lease,
                "validation_lease_id": validation["lease_id"],
                "validation_lease_digest": digest_json(validation),
            }
            atomic_write_json(self.builder_lease_path, lease)
            intent = {
                **intent,
                "validation_lease_id": validation["lease_id"],
                "validation_lease_digest": digest_json(validation),
                "lease_digest": digest_json(lease),
            }
            atomic_write_json(self.builder_intent_path, intent)
        if source == topology.source_head and archive is None:
            if parse_time(lease.get("expires_at")) <= self.clock():
                self._release_builder_validation_lease(intent)
                self._recover_expired_builder_lease(replan)
                self.builder_intent_path.unlink(missing_ok=True)
                append_jsonl(self.state_dir / BUILDER_AUDIT_FILE, {
                    "event": "builder_prepared_intent_cleared_without_mutation",
                    "source_head": topology.source_head,
                    "recorded_at": format_time(self.clock()),
                })
                return None
            fetch_refs = self._fetch_builder_successor_refs(topology)
            try:
                issues = list(self._builder_successor_release_issues(replan, str(intent["target_sha"])))
                issues.extend(self._builder_history_issues(replan))
                if issues:
                    raise ClaimError("; ".join(issues))
                if (
                    self._remote_ref_sha(topology.source_ref) != topology.source_head
                    or self._remote_ref_sha(topology.archive_ref) is not None
                ):
                    raise ClaimError("Builder retirement refs raced before resumed archive transaction")
                self.assert_global_validation_lease(
                    "BUILDER-330", str(intent["validation_owner"]),
                    lease_id=str(intent["validation_lease_id"]),
                )
                pushed = self._git((
                    "push", "--atomic", f"--force-with-lease={topology.source_ref}:{topology.source_head}",
                    f"--force-with-lease={topology.archive_ref}:", "origin",
                    f"{topology.source_head}:{topology.archive_ref}", f":{topology.source_ref}",
                ), check=False)
                if pushed.returncode != 0:
                    raise ClaimError("Builder retirement resumed atomic archive/delete failed")
                self.assert_global_validation_lease(
                    "BUILDER-330", str(intent["validation_owner"]),
                    lease_id=str(intent["validation_lease_id"]),
                )
            finally:
                for reference in fetch_refs:
                    self._git(("update-ref", "-d", reference), check=False)
            source = self._remote_ref_sha(topology.source_ref)
            archive = self._remote_ref_sha(topology.archive_ref)
        if source is not None or archive != topology.source_head:
            raise ClaimError("Builder retirement prepared transaction refs are ambiguous")
        if intent.get("status") == "PREPARED":
            intent = {
                **intent,
                "status": "REMOTE_RETIRED_PENDING_VERIFICATION",
                "remote_retired_at": format_time(self.clock()),
            }
            atomic_write_json(self.builder_intent_path, intent)
        fetch_refs = self._fetch_builder_successor_refs(topology, source_remote_ref=topology.archive_ref)
        try:
            # Transaction recovery is decided from the exact ref state before any
            # current-release gate, so release advancement cannot strand mutation.
            if self.current_target_sha() != intent.get("target_sha"):
                if self._compensate_builder_retirement(
                    topology.source_ref, topology.archive_ref, topology.source_head
                ):
                    self._release_builder_validation_lease(intent)
                    self.builder_lease_path.unlink(missing_ok=True)
                    self.builder_intent_path.unlink(missing_ok=True)
                    raise ClaimError("Builder retirement rolled back after release advanced")
                raise ClaimError("Builder retirement release advanced and rollback failed")
            verification_issues = list(self._builder_successor_release_issues(replan, str(intent["target_sha"])))
            verification_issues.extend(self._builder_history_issues(replan))
            if self._commit_tree(topology.source_head) != topology.source_tree:
                verification_issues.append("Builder interrupted retirement archive tree differs")
            if verification_issues:
                if self._compensate_builder_retirement(
                    topology.source_ref, topology.archive_ref, topology.source_head
                ):
                    self._release_builder_validation_lease(intent)
                    self.builder_lease_path.unlink(missing_ok=True)
                    self.builder_intent_path.unlink(missing_ok=True)
                else:
                    adverse = dict(intent)
                    adverse["status"] = "ADVERSE"
                    adverse["adverse_reason"] = "; ".join(verification_issues)
                    adverse["recorded_at"] = format_time(self.clock())
                    atomic_write_json(self.builder_intent_path, adverse)
                raise ClaimError("; ".join(verification_issues))
            execution = {
                "schema_version": 1,
                "kind": BUILDER_EXECUTION_KIND,
                "status": "RETIRED",
                "recovery_id": intent["recovery_id"],
                "source_head": topology.source_head,
                "archive_ref": topology.archive_ref,
                "snapshot_digest": intent["snapshot_digest"],
                "reconciliation_digest": intent["reconciliation_digest"],
                "doctor_evidence_digest": intent["doctor_evidence_digest"],
                "target_sha": intent["target_sha"],
                "release_id": intent["release_id"],
                "actor": intent["actor"],
                "authority_digest": intent["authority_digest"],
                "replan_digest": intent["replan_digest"],
                "validation_lease_id": intent["validation_lease_id"],
                "validation_lease_digest": intent["validation_lease_digest"],
                "completed_at": format_time(self.clock()),
            }
            atomic_write_json(self.builder_execution_path, execution)
            append_jsonl(self.state_dir / BUILDER_AUDIT_FILE, {"event": "builder_branch_retirement_recovered", **execution})
            return self._finalize_builder_execution_cleanup(execution, replan) or execution
        finally:
            for reference in fetch_refs:
                self._git(("update-ref", "-d", reference), check=False)

    def _builder_release_preflight(self) -> Mapping[str, Any]:
        release = self.current_release()
        if not isinstance(release, Mapping) or self._release_issues(release):
            raise ClaimError("Builder retirement requires one exact current dispatcher release")
        if release.get("target_sha") != self.current_target_sha():
            raise ClaimError("Builder retirement dispatcher target is stale")
        verdicts = release.get("verdicts")
        if not isinstance(verdicts, Mapping) or verdicts.get("BUILDER-330") != "STOP":
            raise ClaimError("Builder retirement requires an exact Builder STOP verdict")
        view = super().node_view("BUILDER-330")
        if view.state != "REPAIR_REQUIRED":
            raise ClaimError("Builder retirement requires exact controller REPAIR_REQUIRED state")
        return release

    def _compensate_builder_retirement(self, source_ref: str, archive_ref: str, expected: str) -> bool:
        if self._remote_ref_sha(source_ref) is not None or self._remote_ref_sha(archive_ref) != expected:
            return False
        pushed = self._git(
            (
                "push", "--atomic", f"--force-with-lease={source_ref}:",
                f"--force-with-lease={archive_ref}:{expected}", "origin",
                f"{expected}:{source_ref}", f":{archive_ref}",
            ),
            check=False,
        )
        return (
            pushed.returncode == 0
            and self._remote_ref_sha(source_ref) == expected
            and self._remote_ref_sha(archive_ref) is None
        )

    def _finalize_builder_execution_cleanup(
        self,
        execution: Mapping[str, Any],
        replan: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        """Finish only the local cleanup window after a durable RETIRED record exists."""

        if not self.builder_intent_path.is_file():
            return None
        intent = read_json(self.builder_intent_path)
        if not isinstance(intent, Mapping) or intent.get("status") != "REMOTE_RETIRED_PENDING_VERIFICATION":
            raise ClaimError("Builder post-execution intent is invalid")
        for key in (
            "recovery_id", "source_head", "archive_ref", "target_sha", "release_id", "actor",
            "authority_digest", "replan_digest", "validation_lease_id", "validation_lease_digest",
        ):
            if intent.get(key) != execution.get(key):
                raise ClaimError(f"Builder post-execution cleanup {key} differs")
        topology = self._builder_successor_topology(replan)
        if self._remote_ref_sha(topology.source_ref) is not None or self._remote_ref_sha(
            topology.archive_ref
        ) != topology.source_head:
            raise ClaimError("Builder post-execution cleanup remote state differs")
        if self.builder_lease_path.is_file():
            lease = read_json(self.builder_lease_path)
            if not isinstance(lease, Mapping) or digest_json(lease) != intent.get("lease_digest"):
                raise ClaimError("Builder post-execution cleanup lease differs")
            archive = self.state_dir / "builder-retirement-leases" / (
                digest_json(lease).replace(":", "-") + ".json"
            )
            atomic_write_json(archive, {**lease, "status": "RELEASED", "released_at": format_time(self.clock())})
            self.builder_lease_path.unlink()
        self._release_builder_validation_lease(intent)
        self.builder_intent_path.unlink()
        append_jsonl(self.state_dir / BUILDER_AUDIT_FILE, {
            "event": "builder_post_execution_cleanup_recovered",
            "recovery_id": execution["recovery_id"],
            "recorded_at": format_time(self.clock()),
        })
        return execution

    def retire_builder_branch(self, *, actor: str) -> Mapping[str, Any]:
        if (
            type(actor) is not str or not actor or actor != actor.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in actor)
        ):
            raise AutopilotError("Builder retirement actor is required")
        issues = (*self._builder_record_issues(), *self._builder_successor_record_issues())
        if issues:
            raise AutopilotError("; ".join(issues))
        replan = self._builder_document(BUILDER_SUCCESSOR_REPLAN_PATH)
        bootstrap = self._builder_document(BUILDER_SUCCESSOR_BOOTSTRAP_PATH)
        assert isinstance(replan, Mapping) and isinstance(bootstrap, Mapping)
        topology = self._builder_successor_topology(replan)
        if not self._origin_is_configured_repository(replan):
            raise ClaimError("Builder retirement requires literal origin repository identity")
        prior = self._builder_execution()
        if prior is not None:
            recovered_cleanup = self._finalize_builder_execution_cleanup(prior, replan)
            if recovered_cleanup is not None:
                return recovered_cleanup
            raise ClaimError("Builder retirement attempted reuse is forbidden")
        recovered = self._recover_interrupted_builder_retirement(replan)
        if recovered is not None:
            return recovered
        self._recover_expired_builder_lease(replan)
        if self.target_requires_reconciliation() or self._snapshot_digest() is None or self._reconciliation_digest() is None:
            raise ClaimError("Builder retirement requires current snapshot and reconciliation")
        if self._doctor_evidence_digest() is None:
            raise ClaimError("Builder retirement requires current full doctor evidence")
        release = self._builder_release_preflight()
        target_sha = self.current_target_sha()
        live_issues = self._builder_successor_release_issues(replan, target_sha)
        if live_issues:
            raise ClaimError("; ".join(live_issues))
        branches = self._snapshot_rows("branches", "name", topology.branch)
        if len(branches) != 1 or branches[0].get("sha") != topology.source_head or branches[0].get("stale") is not True:
            raise ClaimError("Builder retirement snapshot does not bind exact stale branch")
        if self._snapshot_rows("pull_requests", "node_id", "BUILDER-330"):
            raise ClaimError("Builder retirement is forbidden when a Builder PR exists")
        snapshot_prs = self._snapshot_rows("pull_requests", "number", 139)
        if len(snapshot_prs) != 1 or snapshot_prs[0].get("head_sha") != topology.r4_head:
            raise ClaimError("Builder retirement snapshot does not bind exact aggregate PR139")
        if self.claim_path("BUILDER-330").is_file():
            raise ClaimError("Builder retirement is forbidden by active claim")
        validation_owner = f"builder-retirement:{actor}"
        validation = self.acquire_global_validation_lease("BUILDER-330", validation_owner, lease_minutes=30)
        now = self.clock()
        lease = {
            "schema_version": 1,
            "kind": BUILDER_EXECUTION_KIND,
            "recovery_id": BUILDER_RECOVERY_ID,
            "node_id": "BUILDER-330",
            "actor": actor,
            "source_head": topology.source_head,
            "archive_ref": topology.archive_ref,
            "target_sha": target_sha,
            "release_id": release.get("release_id"),
            "authority_digest": digest_json(bootstrap),
            "replan_digest": digest_json(replan),
            "validation_owner": validation_owner,
            "validation_lease_id": validation["lease_id"],
            "validation_lease_digest": digest_json(validation),
            "expires_at": format_time(now + timedelta(minutes=30)),
            "status": "ACTIVE",
        }
        self.builder_lease_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.builder_lease_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            self.release_global_validation_lease(
                "BUILDER-330", validation_owner, lease_id=str(validation["lease_id"])
            )
            raise ClaimError("Builder retirement lease already exists") from error
        try:
            os.write(descriptor, (json.dumps(lease, sort_keys=True, indent=2) + "\n").encode())
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        preserve_lease = False
        execution_persisted = False
        fetch_refs: tuple[str, ...] = ()
        try:
            source_ref = topology.source_ref
            archive_ref = topology.archive_ref
            expected = topology.source_head
            if self._release_binding_issues():
                raise ClaimError("Builder retirement release binding is stale")
            if self._remote_ref_sha(source_ref) != expected:
                raise ClaimError("Builder retirement source is absent or moved")
            if self._remote_ref_sha(archive_ref) is not None:
                raise ClaimError("Builder retirement archive already exists; reuse is forbidden")
            if self._remote_ref_sha(topology.legacy_archive_ref) is not None:
                raise ClaimError("Builder retirement legacy archive collision is forbidden")
            if parse_time(read_json(self.builder_lease_path).get("expires_at")) <= self.clock():
                raise ClaimError("Builder retirement lease expired")
            fetch_refs = self._fetch_builder_successor_refs(topology)
            history_issues = self._builder_history_issues(replan)
            if history_issues:
                raise ClaimError("; ".join(history_issues))
            if self._remote_ref_sha(source_ref) != expected or self._remote_ref_sha(archive_ref) is not None:
                raise ClaimError("Builder retirement refs changed during verification")
            if self._release_binding_issues():
                raise ClaimError("Builder retirement release changed before archive transaction")
            live_issues = self._builder_successor_release_issues(replan, str(lease["target_sha"]))
            if live_issues:
                raise ClaimError("; ".join(live_issues))
            intent = {
                "schema_version": 1,
                "kind": BUILDER_EXECUTION_KIND,
                "status": "PREPARED",
                "recovery_id": BUILDER_RECOVERY_ID,
                "source_head": expected,
                "archive_ref": archive_ref,
                "target_sha": lease["target_sha"],
                "release_id": lease["release_id"],
                "snapshot_digest": self._snapshot_digest(),
                "reconciliation_digest": self._reconciliation_digest(),
                "doctor_evidence_digest": self._doctor_evidence_digest(),
                "actor": actor,
                "authority_digest": lease["authority_digest"],
                "replan_digest": lease["replan_digest"],
                "validation_owner": lease["validation_owner"],
                "validation_lease_id": lease["validation_lease_id"],
                "validation_lease_digest": lease["validation_lease_digest"],
                "lease_digest": digest_json(lease),
                "prepared_at": format_time(self.clock()),
            }
            atomic_write_json(self.builder_intent_path, intent)
            self.assert_global_validation_lease(
                "BUILDER-330", validation_owner, lease_id=str(validation["lease_id"])
            )
            pushed = self._git(
                (
                    "push", "--atomic", f"--force-with-lease={source_ref}:{expected}",
                    f"--force-with-lease={archive_ref}:", "origin",
                    f"{expected}:{archive_ref}", f":{source_ref}",
                ),
                check=False,
            )
            if pushed.returncode != 0:
                raise ClaimError("Builder retirement atomic archive/delete failed: " + pushed.stderr.strip())
            self.assert_global_validation_lease(
                "BUILDER-330", validation_owner, lease_id=str(validation["lease_id"])
            )
            intent = {
                **intent,
                "status": "REMOTE_RETIRED_PENDING_VERIFICATION",
                "remote_retired_at": format_time(self.clock()),
            }
            atomic_write_json(self.builder_intent_path, intent)
            try:
                if self._remote_ref_sha(source_ref) is not None or self._remote_ref_sha(archive_ref) != expected:
                    raise ClaimError("Builder retirement remote verification failed")
                for reference in fetch_refs:
                    self._git(("update-ref", "-d", reference), check=False)
                fetch_refs = self._fetch_builder_successor_refs(topology, source_remote_ref=archive_ref)
                if self._builder_history_issues(replan) or self._commit_tree(expected) != topology.source_tree:
                    raise ClaimError("Builder retirement archive tree or ancestry verification failed")
                if self._remote_ref_sha(topology.legacy_archive_ref) is not None:
                    raise ClaimError("Builder retirement legacy archive changed during transaction")
                if self._release_binding_issues():
                    raise ClaimError("Builder retirement release changed during archive transaction")
                live_issues = self._builder_successor_release_issues(replan, str(lease["target_sha"]))
                if live_issues:
                    raise ClaimError("; ".join(live_issues))
                execution = {
                    "schema_version": 1,
                    "kind": BUILDER_EXECUTION_KIND,
                    "status": "RETIRED",
                    "recovery_id": BUILDER_RECOVERY_ID,
                    "source_head": expected,
                    "archive_ref": archive_ref,
                    "snapshot_digest": self._snapshot_digest(),
                    "reconciliation_digest": self._reconciliation_digest(),
                    "doctor_evidence_digest": self._doctor_evidence_digest(),
                    "target_sha": lease["target_sha"],
                    "release_id": lease["release_id"],
                    "actor": actor,
                    "authority_digest": lease["authority_digest"],
                    "replan_digest": lease["replan_digest"],
                    "validation_lease_id": lease["validation_lease_id"],
                    "validation_lease_digest": lease["validation_lease_digest"],
                    "completed_at": format_time(self.clock()),
                }
                atomic_write_json(self.builder_execution_path, execution)
                execution_persisted = True
                append_jsonl(self.state_dir / BUILDER_AUDIT_FILE, {"event": "builder_branch_retired", **execution})
                return self._finalize_builder_execution_cleanup(execution, replan) or execution
            except Exception as error:
                if execution_persisted:
                    preserve_lease = True
                    raise
                compensated = self._compensate_builder_retirement(source_ref, archive_ref, expected)
                append_jsonl(self.state_dir / BUILDER_AUDIT_FILE, {
                    "event": "builder_retirement_compensated" if compensated else "builder_retirement_compensation_failed",
                    "source_head": expected, "archive_ref": archive_ref, "error": str(error),
                    "recorded_at": format_time(self.clock()),
                })
                if compensated:
                    self.builder_intent_path.unlink(missing_ok=True)
                else:
                    preserve_lease = True
                    adverse = dict(intent)
                    adverse["status"] = "ADVERSE"
                    adverse["adverse_reason"] = str(error)
                    adverse["recorded_at"] = format_time(self.clock())
                    atomic_write_json(self.builder_intent_path, adverse)
                raise
        finally:
            for reference in fetch_refs:
                self._git(("update-ref", "-d", reference), check=False)
            if not preserve_lease and self.builder_lease_path.is_file():
                current_lease = read_json(self.builder_lease_path)
                archive = self.state_dir / "builder-retirement-leases" / (
                    digest_json(current_lease).replace(":", "-") + ".json"
                )
                atomic_write_json(archive, {**current_lease, "status": "RELEASED", "released_at": format_time(self.clock())})
                self.builder_lease_path.unlink()
            if not preserve_lease and self.validation_lease_path.is_file():
                self._release_builder_validation_lease(lease)
