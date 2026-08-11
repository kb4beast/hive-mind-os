"""Exact, non-generic recovery primitives for three sealed L2 incidents."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
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
OPTIMIZER_COMPLETION_AUTHORITY_DOCUMENT = ".autopilot/optimizer-370-completion-overlay-authority.json"
OPTIMIZER_COMPLETION_AUTHORITY_DIGEST = "sha256:dd33d10191e7c03dea8bcd0959b58c0c8ea14da9b42c29ef386c503b2c07aab7"
OPTIMIZER_COMPLETION_CAPABILITY_COMMIT = "b8ed8273b8819250a0e7850550d3335e7446d590"
OPTIMIZER_GENERIC_DIFF_ISSUE = "receipt changed_paths do not match the exact base..final diff"
OPTIMIZER_CONTINUATION_KIND = "hive-mind-autopilot-optimizer-completion-continuation-v1"
OPTIMIZER_CONTINUATION_FILE = "optimizer-370-completion-continuation.json"
DIGEST_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
REPAIR_AUTHORITY_MATERIAL_DIGESTS = {
    "OPTIMIZER-370": "sha256:380b642ffbc32892eee60fab8b9a23f3b1fdd9e5c66a5309f97c2d9a842ab4dd",
    "ORCH-300": "sha256:348714232a0be8a82bbf168fa96c55c52a155d4549955b6d8e113abcb26adc9d",
}
SEALED_CAPABILITY_COMMIT = "b8ed8273b8819250a0e7850550d3335e7446d590"
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
BUILDER_EXECUTION_KIND = "hive-mind-autopilot-builder-330-retirement-v1"
BUILDER_EXECUTION_FILE = "builder-330-retirement-execution.json"
BUILDER_RECOVERY_FILE = "builder-330-retirement-recovery.json"
BUILDER_LEASE_FILE = "builder-330-retirement-lease.json"
BUILDER_INTENT_FILE = "builder-330-retirement-intent.json"
BUILDER_AUDIT_FILE = "builder-330-retirement-audit.jsonl"


class SealedRecoveryMixin:
    """Mixin layered above the generic durable/release controller.

    The public entry points accept only a node already present in the sealed registry or,
    for Builder retirement, no caller-selected identity at all.  Generic existing-branch
    claims, duplicate receipts, and branch retirement remain unchanged and fail closed.
    """

    @property
    def repair_authority_path(self) -> Path:
        return self.repo_root / REPAIR_AUTHORITY_DOCUMENT

    @property
    def optimizer_completion_authority_path(self) -> Path:
        return self.repo_root / OPTIMIZER_COMPLETION_AUTHORITY_DOCUMENT

    @property
    def optimizer_continuation_path(self) -> Path:
        if self._has_git_repository() and self.verify_git_objects:
            common = self._git(("rev-parse", "--path-format=absolute", "--git-common-dir"), check=False)
            value = common.stdout.strip()
            if common.returncode != 0 or not value:
                raise ClaimError("Optimizer continuation Git common directory is unavailable")
            return Path(value).resolve() / "hive-mind-autopilot" / OPTIMIZER_CONTINUATION_FILE
        return self.state_dir / OPTIMIZER_CONTINUATION_FILE

    def _optimizer_completion_authority(self) -> Mapping[str, Any] | None:
        if not self.optimizer_completion_authority_path.is_file():
            return None
        value = read_json(self.optimizer_completion_authority_path)
        return value if isinstance(value, Mapping) else None

    def _optimizer_completion_authority_issues(self) -> tuple[str, ...]:
        value = self._optimizer_completion_authority()
        if not isinstance(value, Mapping):
            return ("Optimizer completion authority is unavailable",)
        material = dict(value)
        capability = material.pop("capability_commit", None)
        issues: list[str] = []
        if digest_json(material) != OPTIMIZER_COMPLETION_AUTHORITY_DIGEST:
            issues.append("Optimizer completion authority material was altered")
        for key, relative in (
            ("court_digest", ".autopilot/optimizer-370-completion-overlay-court.json"),
            ("appeals_digest", ".autopilot/optimizer-370-completion-overlay-appeals.json"),
            ("evidence_digest", ".autopilot/optimizer-370-completion-overlay-evidence.json"),
        ):
            path = self.repo_root / relative
            document = read_json(path) if path.is_file() else None
            if not isinstance(document, Mapping) or digest_json(document) != value.get(key):
                issues.append(f"Optimizer completion {key} evidence differs")
        appeals_path = self.repo_root / ".autopilot/optimizer-370-completion-overlay-appeals.json"
        appeals = read_json(appeals_path) if appeals_path.is_file() else None
        if (
            not isinstance(appeals, Mapping)
            or appeals.get("court_digest") != value.get("court_digest")
            or appeals.get("court_disposition") != "ADAPT"
        ):
            issues.append("Optimizer Appeals record does not bind the Court disposition")
        if capability != OPTIMIZER_COMPLETION_CAPABILITY_COMMIT:
            issues.append("Optimizer completion capability differs from compiled pin")
        if capability == "0" * 40 or not isinstance(capability, str):
            issues.append("Optimizer completion capability is zero or invalid")
        if self._has_git_repository() and not self.verify_git_objects:
            issues.append("Optimizer completion requires Git object verification in a Git repository")
        if self.verify_git_objects and isinstance(capability, str) and not self.git_object_exists(capability):
            issues.append("Optimizer completion capability object is unavailable")
        return tuple(dict.fromkeys(issues))

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
        record = records.get(node_id)
        if record is None:
            raise AutopilotError(f"node {node_id} has no sealed repair authority")
        issues = self.sealed_recovery_issues()
        if issues:
            raise AutopilotError("; ".join(issues))
        return record

    def _capability_issues(self, capability: object) -> tuple[str, ...]:
        if not isinstance(capability, str) or FULL_SHA.fullmatch(capability) is None:
            return ("sealed recovery capability commit is invalid",)
        if capability != SEALED_CAPABILITY_COMMIT or capability == "0" * 40:
            return ("sealed recovery capability commit is not the exact compiled pin",)
        if self.verify_git_objects and not self.git_object_exists(capability):
            return ("sealed recovery capability commit object is unavailable",)
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
        issues.extend(self._optimizer_completion_authority_issues())
        issues.extend(self._builder_record_issues())
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
        return tuple(dict.fromkeys(issues))

    def node_view(self, node_id: str) -> NodeView:
        if node_id not in REPAIR_AUTHORITY_MATERIAL_DIGESTS:
            return super().node_view(node_id)
        record = self._repair_records().get(node_id)
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
        if self.sealed_recovery_issues() or self._repair_live_issues(record):
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
        if tuple(sorted(changed)) != tuple(sorted(record["allowed_paths"])):
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
        if tuple(sorted(self._diff_paths(claim_target, candidate))) != tuple(sorted(record["allowed_paths"])):
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
            return ()
        finally:
            self._git(("update-ref", "-d", local_ref), check=False)

    def _recover_interrupted_repair_claim(self, record: Mapping[str, Any]) -> None:
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
                    self._cas_update_branch(
                        str(record["branch"]), remote_head, str(record["old_receipt_commit"])
                    )
                    observed = self.remote_branch_sha(str(record["branch"]))
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
                self._cas_update_branch(str(record["branch"]), remote_head, old)
                observed = self.remote_branch_sha(str(record["branch"]))
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

    def claim(
        self,
        node_id: str,
        owner: str,
        *,
        lease_minutes: int = 90,
        publish_remote: bool = False,
        remote: str = "origin",
    ) -> Mapping[str, Any]:
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
        self._recover_interrupted_repair_claim(record)
        self.assert_start_now(node_id)
        if self._repair_live_issues(record):
            raise ClaimError("; ".join(self._repair_live_issues(record)))
        if not self._origin_is_configured_repository(record):
            raise ClaimError("sealed repair requires literal configured origin repository")
        live_issues = self._live_release_issues(record)
        if live_issues:
            raise ClaimError("; ".join(live_issues))
        old = str(record["old_receipt_commit"])
        branch = str(record["branch"])
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
            self._cas_update_branch(branch, old, remote_head)
            if self.remote_branch_sha(branch) != remote_head:
                raise ClaimError("sealed repair remote claim verification failed")
            if self._release_binding_issues(local):
                raise ClaimError("sealed repair release changed during claim publication")
            live_issues = self._live_release_issues(record, str(local["target_sha"]))
            if live_issues:
                raise ClaimError("; ".join(live_issues))
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

    def release(self, node_id: str, owner: str, *, reason: str) -> None:
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

    def _exact_optimizer_completion_issues(
        self,
        receipt: Mapping[str, Any],
    ) -> tuple[str, ...]:
        capability = self._optimizer_completion_authority()
        if not isinstance(capability, Mapping):
            return ("exact Optimizer completion authority is unavailable",)
        issues = list(self._optimizer_completion_authority_issues())
        authority = receipt.get("authority")
        if not isinstance(authority, Mapping):
            return tuple((*issues, "exact Optimizer receipt authority is invalid"))
        exact = {
            "base_commit": capability["incident_base_sha"],
            "base_tree": capability["incident_base_tree"],
            "final_commit": capability["candidate_commit"],
            "final_tree": capability["candidate_tree"],
            "pr": capability["pr"],
        }
        for key, expected in exact.items():
            if receipt.get(key) != expected:
                issues.append(f"exact Optimizer receipt {key} differs")
        authority_exact = {
            "grant_id": capability["grant_id"],
            "supersedes_receipt_commit": capability["old_receipt_commit"],
            "repair_claim_commit": capability["repair_claim_commit"],
            "execution_merge_commit": capability["execution_merge_commit"],
            "execution_target_sha": capability["execution_target_sha"],
        }
        for key, expected in authority_exact.items():
            if authority.get(key) != expected:
                issues.append(f"exact Optimizer receipt authority {key} differs")
        if receipt.get("changed_paths") != capability["authorized_optimizer_paths"]:
            issues.append("exact Optimizer receipt must declare both authorized paths in order")
        if digest_json(receipt) != capability["receipt_digest"]:
            issues.append("exact Optimizer receipt digest differs")
        if self._has_git_repository() and not self.verify_git_objects:
            issues.append("exact Optimizer receipt cannot disable Git object verification")
        if self.verify_git_objects:
            old = str(capability["old_receipt_commit"])
            claim = str(capability["repair_claim_commit"])
            execution = str(capability["execution_merge_commit"])
            target = str(capability["execution_target_sha"])
            final = str(capability["candidate_commit"])
            required = (old, claim, execution, target, final)
            if any(not self.git_object_exists(commit) for commit in required):
                issues.append("exact Optimizer topology object is unavailable")
            else:
                if self._commit_parents(claim) != (old,) or self._commit_tree(claim) != self._commit_tree(old):
                    issues.append("exact Optimizer repair claim is not the pinned zero-path child")
                if self._commit_parents(execution) != (claim, target):
                    issues.append("exact Optimizer execution merge parent ordering differs")
                if not self.is_ancestor(execution, final) or not self.is_ancestor(target, final):
                    issues.append("exact Optimizer candidate ancestry differs")
                if self._commit_tree(target) != capability["execution_target_tree"]:
                    issues.append("exact Optimizer execution target tree differs")
                if self._commit_tree(final) != capability["candidate_tree"]:
                    issues.append("exact Optimizer candidate tree differs")
                if self._diff_paths(target, final) != tuple(capability["authorized_optimizer_paths"]):
                    issues.append("exact Optimizer execution diff must equal both authorized paths")
        return tuple(dict.fromkeys(issues))

    def _replacement_receipt_issues(
        self,
        node_id: str,
        receipt: Mapping[str, Any],
        *,
        active_claim: Mapping[str, Any] | None = None,
        continuation: Mapping[str, Any] | None = None,
    ) -> tuple[str, ...]:
        issues = list(self._sealed_receipt_shape_issues(node_id, receipt))
        generic_issues = list(super().validate_receipt(node_id, receipt, require_integrated=False))
        exact_optimizer_issues: tuple[str, ...] = ()
        authority_value = receipt.get("authority")
        exact_optimizer = (
            node_id == "OPTIMIZER-370"
            and isinstance(authority_value, Mapping)
            and authority_value.get("grant_id") == "optimizer-370-invalid-receipt-supersession-v1"
        )
        if exact_optimizer and self._has_git_repository():
            exact_optimizer_issues = self._exact_optimizer_completion_issues(receipt)
            if not exact_optimizer_issues:
                generic_issues = [issue for issue in generic_issues if issue != OPTIMIZER_GENERIC_DIFF_ISSUE]
        issues.extend(generic_issues)
        issues.extend(exact_optimizer_issues)
        record = self._repair_records().get(node_id)
        if record is None:
            return ("sealed replacement authority is unavailable",)
        recovery_issues = self.sealed_recovery_issues()
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
            if (
                self.current_target_sha() != active_claim.get("target_sha")
                and continuation is None
            ):
                issues.append("sealed replacement completion target moved after claim")
        if self.verify_git_objects and isinstance(claim_commit, str) and FULL_SHA.fullmatch(claim_commit):
            old = str(record["old_receipt_commit"])
            final = receipt.get("final_commit")
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
                if node_id == "OPTIMIZER-370":
                    if observed != tuple(sorted(record["allowed_paths"])):
                        issues.append("sealed replacement diff must equal the complete exact repair scope")
                elif not observed or set(observed) - set(record["allowed_paths"]):
                    issues.append("sealed replacement diff expands or omits exact repair scope")
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
        record = self._repair_records().get(node_id)
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

    def _durable_receipt_records(self) -> dict[str, list[dict[str, Any]]]:
        records = super()._durable_receipt_records()
        if not self._has_git_repository():
            return records
        target = self.current_target_sha()
        for node_id, authority in self._repair_records().items():
            old = str(authority["old_receipt_commit"])
            node_records = records.setdefault(node_id, [])
            if any(item.get("commit") == old for item in node_records):
                continue
            if not self.git_object_exists(old) or not self.is_ancestor(old, target):
                continue
            shown = self._git(
                ("show", "-s", "--format=%H%x1f%P%x1f%T%x1f%B", old),
                check=False,
            )
            parts = shown.stdout.split("\x1f", 3) if shown.returncode == 0 else []
            receipt = self._parse_receipt_message(parts[3]) if len(parts) == 4 else None
            if isinstance(receipt, Mapping):
                node_records.append({
                    "commit": parts[0].strip(),
                    "parents": tuple(parts[1].split()),
                    "tree": parts[2].strip(),
                    "receipt": receipt,
                })
        return records

    def resolve_sealed_repair_records(
        self,
        node_id: str,
        records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        record = self._repair_records().get(node_id)
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

    def _exact_receipt_index_entry(
        self,
        node_id: str,
        receipt_commit: str,
        receipt: Mapping[str, Any],
        record: Mapping[str, Any],
    ) -> bool:
        path = self.state_dir / "receipt-index.jsonl"
        if not path.is_file():
            return False
        matches: list[Mapping[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, Mapping) and value.get("node_id") == node_id:
                matches.append(value)
        expected = {
            "node_id": node_id,
            "receipt_commit": receipt_commit,
            "receipt_digest": digest_json(receipt),
            "final_commit": receipt.get("final_commit"),
            "supersedes_receipt_commit": record["old_receipt_commit"],
            "timestamp": receipt.get("timestamp"),
        }
        return len(matches) == 1 and dict(matches[0]) == expected

    def _recover_consumed_optimizer_completion_without_intent(
        self,
        node_id: str,
        owner: str,
        receipt: Mapping[str, Any],
        record: Mapping[str, Any],
    ) -> str | None:
        intent_path = self.state_dir / f"sealed-repair-completion-{node_id.lower()}.json"
        if (
            node_id != "OPTIMIZER-370"
            or self.claim_path(node_id).is_file()
            or intent_path.is_file()
            or not self.optimizer_continuation_path.is_file()
        ):
            return None
        continuation = self._reconcile_optimizer_continuation_transition()
        if not isinstance(continuation, Mapping) or continuation.get("status") != "CONSUMED":
            return None
        authority = self._optimizer_completion_authority()
        issues = self._optimizer_completion_authority_issues()
        if not isinstance(authority, Mapping) or issues:
            raise ClaimError("; ".join(issues or ("Optimizer authority is unavailable",)))
        receipt_commit = continuation.get("receipt_commit")
        final = receipt.get("final_commit")
        if (
            owner != authority.get("claim_owner")
            or continuation.get("owner") != owner
            or continuation.get("node_id") != node_id
            or continuation.get("capability_digest") != digest_json(authority)
            or continuation.get("capability_commit") != authority.get("capability_commit")
            or continuation.get("receipt_digest") != digest_json(receipt)
            or continuation.get("receipt_digest") != authority.get("receipt_digest")
            or not isinstance(receipt_commit, str)
            or FULL_SHA.fullmatch(receipt_commit) is None
            or self.remote_branch_sha(str(record["branch"])) != receipt_commit
        ):
            raise ClaimError("consumed Optimizer response-recovery binding differs")
        target = continuation.get("target_sha")
        capability_commit = str(authority["capability_commit"])
        if (
            not isinstance(target, str)
            or FULL_SHA.fullmatch(target) is None
            or self._commit_parents(target) != (capability_commit,)
            or self._commit_tree(target) != continuation.get("target_tree")
            or self._optimizer_reseal_content_issues(capability_commit, target)
        ):
            raise ClaimError("consumed Optimizer exact H evidence differs")
        local_path = self.receipt_path(node_id)
        if (
            not local_path.is_file()
            or digest_json(read_json(local_path)) != digest_json(receipt)
            or not self._exact_receipt_index_entry(node_id, receipt_commit, receipt, record)
        ):
            raise ClaimError("consumed Optimizer response-recovery evidence differs")
        if (
            self._commit_parents(receipt_commit) != (final,)
            or self._commit_tree(receipt_commit) != receipt.get("final_tree")
        ):
            raise ReceiptError("consumed Optimizer response-recovery topology differs")
        shown = self._git(("show", "-s", "--format=%B", receipt_commit), check=False)
        parsed = self._parse_receipt_message(shown.stdout) if shown.returncode == 0 else None
        if not isinstance(parsed, Mapping) or digest_json(parsed) != digest_json(receipt):
            raise ReceiptError("consumed Optimizer response-recovery payload differs")
        return receipt_commit

    def _recover_terminal_repair_completion_without_claim(
        self,
        node_id: str,
        owner: str,
        receipt: Mapping[str, Any],
        record: Mapping[str, Any],
    ) -> str | None:
        intent_path = self.state_dir / f"sealed-repair-completion-{node_id.lower()}.json"
        if self.claim_path(node_id).is_file() or not intent_path.is_file():
            return None
        intent = read_json(intent_path)
        base_required = {
            "schema_version", "kind", "status", "node_id", "owner", "target_sha",
            "remote_expected_final", "receipt_digest", "receipt_commit",
            "active_claim_digest", "prepared_at",
        }
        continuation_required = {
            "continuation_digest", "continuation_target_sha", "continuation_grant_id",
        }
        intent_keys = frozenset(intent) if isinstance(intent, Mapping) else frozenset()
        if not isinstance(intent, Mapping) or intent_keys not in {
            frozenset(base_required), frozenset(base_required | continuation_required)
        }:
            raise ClaimError("terminal sealed repair intent is foreign or malformed")
        if (
            intent.get("kind") != "hive-mind-autopilot-sealed-repair-completion-v1"
            or intent.get("status") != "PREPARED"
            or intent.get("node_id") != node_id
            or intent.get("owner") != owner
            or intent.get("receipt_digest") != digest_json(receipt)
        ):
            raise ClaimError("terminal sealed repair intent identity is invalid")
        receipt_commit = intent.get("receipt_commit")
        final = receipt.get("final_commit")
        if not isinstance(receipt_commit, str) or FULL_SHA.fullmatch(receipt_commit) is None:
            raise ClaimError("terminal sealed repair receipt commit is invalid")
        if self.remote_branch_sha(str(record["branch"])) != receipt_commit:
            raise ClaimError("terminal sealed repair remote head differs")
        local_path = self.receipt_path(node_id)
        if not local_path.is_file() or digest_json(read_json(local_path)) != digest_json(receipt):
            raise ClaimError("terminal sealed repair local receipt differs")
        if not self._exact_receipt_index_entry(node_id, receipt_commit, receipt, record):
            raise ClaimError("terminal sealed repair index is absent, duplicate, or conflicting")
        if (
            self._commit_parents(receipt_commit) != (final,)
            or self._commit_tree(receipt_commit) != receipt.get("final_tree")
        ):
            raise ReceiptError("terminal sealed repair receipt topology differs")
        shown = self._git(("show", "-s", "--format=%B", receipt_commit), check=False)
        parsed = self._parse_receipt_message(shown.stdout) if shown.returncode == 0 else None
        if not isinstance(parsed, Mapping) or digest_json(parsed) != digest_json(receipt):
            raise ReceiptError("terminal sealed repair receipt payload differs")
        if continuation_required.issubset(intent):
            continuation = read_json(self.optimizer_continuation_path)
            continuation_digest_matches = (
                isinstance(continuation, Mapping)
                and digest_json(continuation) == intent.get("continuation_digest")
            )
            if isinstance(continuation, Mapping) and continuation.get("status") == "CONSUMED":
                continuation_digest_matches = (
                    continuation.get("previous_digest") == intent.get("continuation_digest")
                    and continuation.get("receipt_commit") == receipt_commit
                )
            if (
                not isinstance(continuation, Mapping)
                or continuation.get("status") not in {"CONSUMING", "CONSUMED"}
                or not continuation_digest_matches
                or continuation.get("target_sha") != intent.get("continuation_target_sha")
                or continuation.get("grant_id") != intent.get("continuation_grant_id")
                or continuation.get("claim_digest") != intent.get("active_claim_digest")
            ):
                raise ClaimError("terminal Optimizer continuation binding differs")
            if continuation.get("status") == "CONSUMING":
                self._transition_optimizer_continuation(
                    "CONSUMING", "CONSUMED", receipt_commit=receipt_commit
                )
        intent_path.unlink()
        append_jsonl(self.state_dir / "sealed-repair-adverse.jsonl", {
            "event": "terminal_receipt_reconciled_without_claim",
            "node_id": node_id,
            "receipt_commit": receipt_commit,
        })
        return receipt_commit

    @staticmethod
    def _exclusive_write_json(path: Path, value: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(descriptor, data)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _transition_optimizer_continuation(
        self,
        expected_status: str,
        status: str,
        *,
        receipt_commit: str | None = None,
        bindings: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        path = self.optimizer_continuation_path
        lock = path.with_suffix(path.suffix + ".transition")
        self._reconcile_optimizer_continuation_transition()
        current = read_json(path)
        if not isinstance(current, Mapping):
            raise ClaimError("Optimizer continuation CAS state is unavailable")
        if current.get("status") == status:
            return current
        transition = {
            "schema_version": 1,
            "kind": OPTIMIZER_CONTINUATION_KIND + "-transition",
            "expected_status": expected_status,
            "next_status": status,
            "expected_digest": digest_json(current),
            "receipt_commit": receipt_commit,
            "bindings": dict(bindings) if bindings is not None else None,
        }
        try:
            self._exclusive_write_json(lock, transition)
        except FileExistsError:
            existing = read_json(lock)
            if (
                not isinstance(existing, Mapping)
                or existing.get("kind") != OPTIMIZER_CONTINUATION_KIND + "-transition"
                or existing.get("expected_status") != expected_status
                or existing.get("next_status") != status
                or existing.get("receipt_commit") != receipt_commit
                or existing.get("bindings") != (
                    dict(bindings) if bindings is not None else None
                )
            ):
                raise ClaimError("Optimizer continuation has a foreign durable transition")
            transition = dict(existing)
        try:
            current = read_json(path)
            if isinstance(current, Mapping) and current.get("status") == status:
                lock.unlink()
                return current
            if (
                not isinstance(current, Mapping)
                or current.get("status") != expected_status
                or digest_json(current) != transition["expected_digest"]
            ):
                raise ClaimError("Optimizer continuation CAS state differs")
            updated = dict(current)
            updated["status"] = status
            updated["previous_digest"] = digest_json(current)
            updated["transitioned_at"] = format_time(self.clock())
            if receipt_commit is not None:
                updated["receipt_commit"] = receipt_commit
            if bindings is not None:
                updated.update(bindings)
            atomic_write_json(path, updated)
            lock.unlink()
            return updated
        except Exception:
            # The durable transition remains for exact restart reconciliation.
            raise

    def _reconcile_optimizer_continuation_transition(self) -> Mapping[str, Any] | None:
        path = self.optimizer_continuation_path
        marker = path.with_suffix(path.suffix + ".transition")
        if not marker.is_file():
            value = read_json(path) if path.is_file() else None
            return value if isinstance(value, Mapping) else None
        transition = read_json(marker)
        required = {
            "schema_version", "kind", "expected_status", "next_status",
            "expected_digest", "receipt_commit", "bindings",
        }
        if (
            not isinstance(transition, Mapping)
            or set(transition) != required
            or transition.get("schema_version") != 1
            or transition.get("kind") != OPTIMIZER_CONTINUATION_KIND + "-transition"
        ):
            raise ClaimError("Optimizer continuation has a foreign durable transition")
        current = read_json(path)
        if not isinstance(current, Mapping):
            raise ClaimError("Optimizer continuation durable transition lost its state")
        if current.get("status") == transition.get("next_status"):
            marker.unlink()
            return current
        if (
            current.get("status") != transition.get("expected_status")
            or digest_json(current) != transition.get("expected_digest")
        ):
            raise ClaimError("Optimizer continuation durable transition state differs")
        updated = dict(current)
        updated["status"] = transition["next_status"]
        updated["previous_digest"] = digest_json(current)
        updated["transitioned_at"] = format_time(self.clock())
        if transition.get("receipt_commit") is not None:
            updated["receipt_commit"] = transition["receipt_commit"]
        bindings = transition.get("bindings")
        if bindings is not None:
            if not isinstance(bindings, Mapping):
                raise ClaimError("Optimizer continuation transition bindings are invalid")
            updated.update(bindings)
        atomic_write_json(path, updated)
        marker.unlink()
        return updated

    def _optimizer_continuation_issues(
        self,
        continuation: object,
        claim: Mapping[str, Any],
        receipt: Mapping[str, Any],
        *,
        statuses: tuple[str, ...] = ("ACTIVE", "CONSUMING"),
        live: bool = True,
        check_expiry: bool = True,
    ) -> tuple[str, ...]:
        if not isinstance(continuation, Mapping):
            return ("Optimizer continuation is unavailable",)
        capability = self._optimizer_completion_authority()
        if not isinstance(capability, Mapping):
            return ("Optimizer continuation authority is unavailable",)
        issues = list(self._optimizer_completion_authority_issues())
        required = {
            "schema_version", "kind", "status", "node_id", "grant_id", "owner",
            "claim_digest", "capability_digest", "capability_commit", "target_sha",
            "target_tree", "release_id", "github_snapshot_digest",
            "reconciliation_digest", "doctor_evidence_digest", "main_sha", "pr",
            "receipt_digest", "expires_at", "created_at",
        }
        optional = {"previous_digest", "transitioned_at", "receipt_commit"}
        if set(continuation) - required - optional or required - set(continuation):
            issues.append("Optimizer continuation shape is foreign or incomplete")
        expected = {
            "schema_version": 1,
            "kind": OPTIMIZER_CONTINUATION_KIND,
            "node_id": "OPTIMIZER-370",
            "grant_id": capability["grant_id"],
            "owner": capability["claim_owner"],
            "capability_digest": digest_json(capability),
            "capability_commit": capability["capability_commit"],
            "main_sha": capability["main_sha"],
            "pr": capability["pr"],
            "receipt_digest": capability["receipt_digest"],
        }
        for key, value in expected.items():
            if continuation.get(key) != value:
                issues.append(f"Optimizer continuation {key} differs")
        if continuation.get("status") not in statuses:
            issues.append("Optimizer continuation state is not active for completion")
        claimed_material = dict(claim)
        claimed_material["status"] = "CLAIMED"
        claimed_material.pop("adverse_reason", None)
        if continuation.get("claim_digest") != digest_json(claimed_material):
            issues.append("Optimizer continuation claim digest differs")
        if claim.get("status") not in {"CLAIMED", "COMPLETING"}:
            issues.append("Optimizer continuation requires CLAIMED or crash-resuming COMPLETING state")
        if claim.get("owner") != capability["claim_owner"] or claim.get("grant_id") != capability["grant_id"]:
            issues.append("Optimizer continuation claim owner or grant differs")
        if claim.get("target_sha") != capability["execution_target_sha"]:
            issues.append("Optimizer continuation claim execution target differs")
        if check_expiry:
            try:
                if parse_time(claim.get("expires_at")) <= self.clock():
                    issues.append("Optimizer continuation cannot waive claim expiry")
                if parse_time(continuation.get("expires_at")) <= self.clock():
                    issues.append("Optimizer continuation lease expired")
            except (TypeError, ValueError):
                issues.append("Optimizer continuation expiry is invalid")
        if digest_json(receipt) != capability["receipt_digest"]:
            issues.append("Optimizer continuation receipt digest differs")
        target = continuation.get("target_sha")
        if not isinstance(target, str) or FULL_SHA.fullmatch(target) is None:
            issues.append("Optimizer continuation H is invalid")
            return tuple(dict.fromkeys(issues))
        if self.verify_git_objects:
            capability_commit = str(capability["capability_commit"])
            g = str(capability["execution_target_sha"])
            if self._commit_parents(capability_commit) != (g,):
                issues.append("Optimizer capability is not a direct child of G")
            if self._commit_parents(target) != (capability_commit,):
                issues.append("Optimizer H is not the exact direct reseal child")
            if self._commit_tree(target) != continuation.get("target_tree"):
                issues.append("Optimizer continuation H tree differs")
            if self._diff_paths(g, target) != tuple(capability["overlay_paths"]):
                issues.append("Optimizer G-to-H overlay path set differs")
            if self._diff_paths(capability_commit, target) != tuple(capability["reseal_paths"]):
                issues.append("Optimizer capability-to-H reseal path set differs")
            issues.extend(self._optimizer_reseal_content_issues(capability_commit, target))
        if live:
            if self.current_target_sha() != target:
                issues.append("Optimizer continuation does not pin current H exactly")
            release = self.current_release()
            if not isinstance(release, Mapping) or self._release_issues(release):
                issues.append("Optimizer continuation H release is invalid")
            else:
                bindings = {
                    "target_sha": target,
                    "release_id": continuation.get("release_id"),
                    "github_snapshot_digest": continuation.get("github_snapshot_digest"),
                    "reconciliation_digest": continuation.get("reconciliation_digest"),
                }
                for key, value in bindings.items():
                    if release.get(key) != value:
                        issues.append(f"Optimizer continuation H release {key} differs")
            if continuation.get("doctor_evidence_digest") != self._doctor_evidence_digest():
                issues.append("Optimizer continuation doctor binding differs")
            if self._remote_ref_sha(f"refs/heads/{self.target_branch}") != target:
                issues.append("Optimizer literal-origin release is not exact H")
            if self._remote_ref_sha("refs/heads/main") != capability["main_sha"]:
                issues.append("Optimizer continuation observed main movement")
        return tuple(dict.fromkeys(issues))

    def _optimizer_reseal_content_issues(
        self, capability_commit: str, target_sha: str
    ) -> tuple[str, ...]:
        authority_path = OPTIMIZER_COMPLETION_AUTHORITY_DOCUMENT
        code_path = ".autopilot/bin/sealed_recovery.py"
        capability_authority = self._git(
            ("show", f"{capability_commit}:{authority_path}"), check=False
        )
        target_authority = self._git(("show", f"{target_sha}:{authority_path}"), check=False)
        capability_code = self._git(("show", f"{capability_commit}:{code_path}"), check=False)
        target_code = self._git(("show", f"{target_sha}:{code_path}"), check=False)
        if any(
            result.returncode != 0
            for result in (capability_authority, target_authority, capability_code, target_code)
        ):
            return ("Optimizer exact reseal blobs are unavailable",)
        try:
            before_authority = json.loads(capability_authority.stdout)
            after_authority = json.loads(target_authority.stdout)
        except json.JSONDecodeError:
            return ("Optimizer exact reseal authority blob is invalid",)
        expected_authority = dict(before_authority)
        expected_authority["capability_commit"] = capability_commit
        issues: list[str] = []
        if after_authority != expected_authority:
            issues.append("Optimizer H authority is not the exact capability substitution")
        old_line = (
            f'OPTIMIZER_COMPLETION_CAPABILITY_COMMIT = '
            f'"{before_authority.get("capability_commit")}"'
        )
        new_line = f'OPTIMIZER_COMPLETION_CAPABILITY_COMMIT = "{capability_commit}"'
        before_code = capability_code.stdout
        if before_code.count(old_line) != 1:
            issues.append("Optimizer capability source substitution site is not unique")
        elif target_code.stdout != before_code.replace(old_line, new_line, 1):
            issues.append("Optimizer H source is not the exact capability substitution")
        return tuple(issues)

    def _arm_optimizer_continuation(
        self,
        claim: Mapping[str, Any],
        receipt: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        capability = self._optimizer_completion_authority()
        if not isinstance(capability, Mapping):
            return None
        if (
            not self._has_git_repository()
            or digest_json(receipt) != capability["receipt_digest"]
            or claim.get("target_sha") != capability["execution_target_sha"]
            or claim.get("grant_id") != capability["grant_id"]
        ):
            return None
        if self.optimizer_continuation_path.is_file():
            existing = self._reconcile_optimizer_continuation_transition()
            if self.current_target_sha() == capability["execution_target_sha"]:
                raise ClaimError("pre-armed Optimizer continuation is awaiting exact H")
            if isinstance(existing, Mapping) and existing.get("status") == "ARMED":
                if self.current_target_sha() != existing.get("target_sha"):
                    raise ClaimError("Optimizer continuation does not pin current H exactly")
                armed_issues = self._optimizer_continuation_issues(
                    existing,
                    claim,
                    receipt,
                    statuses=("ARMED",),
                    live=False,
                )
                if armed_issues:
                    raise ClaimError("; ".join(armed_issues))
                release = self.current_release()
                if not isinstance(release, Mapping) or self._release_issues(release):
                    raise ClaimError("Optimizer continuation requires the actual H release")
                existing = self._transition_optimizer_continuation(
                    "ARMED",
                    "ACTIVE",
                    bindings={
                        "release_id": release.get("release_id"),
                        "github_snapshot_digest": release.get("github_snapshot_digest"),
                        "reconciliation_digest": release.get("reconciliation_digest"),
                        "doctor_evidence_digest": self._doctor_evidence_digest(),
                    },
                )
            issues = self._optimizer_continuation_issues(existing, claim, receipt)
            if issues:
                raise ClaimError("; ".join(issues))
            return existing if isinstance(existing, Mapping) else None
        if self.current_target_sha() == capability["execution_target_sha"]:
            return None
        raise ClaimError("post-H Optimizer completion requires a pre-armed exact continuation")

    def arm_optimizer_completion_continuation(
        self,
        owner: str,
        target_sha: str,
    ) -> Mapping[str, Any]:
        """O_EXCL-bind one exact H while release is still G and the claim is live."""

        capability = self._optimizer_completion_authority()
        if not isinstance(capability, Mapping) or self._optimizer_completion_authority_issues():
            raise ClaimError("Optimizer continuation authority is unavailable or invalid")
        record = self._repair_record("OPTIMIZER-370")
        if not self._origin_is_configured_repository(record):
            raise ClaimError("Optimizer continuation requires literal configured origin")
        if (
            self.current_target_sha() != capability["execution_target_sha"]
            or self._remote_ref_sha(f"refs/heads/{self.target_branch}")
            != capability["execution_target_sha"]
            or self._remote_ref_sha("refs/heads/main") != capability["main_sha"]
        ):
            raise ClaimError("Optimizer continuation can arm only while release is exact G")
        claim_path = self.claim_path("OPTIMIZER-370")
        claim = read_json(claim_path) if claim_path.is_file() else None
        if (
            not isinstance(claim, Mapping)
            or claim.get("status") != "CLAIMED"
            or claim.get("owner") != owner
            or owner != capability["claim_owner"]
            or claim.get("grant_id") != capability["grant_id"]
            or claim.get("target_sha") != capability["execution_target_sha"]
            or parse_time(claim.get("expires_at")) <= self.clock()
        ):
            raise ClaimError("Optimizer continuation requires the exact live CLAIMED lease")
        receipt = read_json(self.repo_root / ".autopilot/optimizer-370-intended-receipt.json")
        if not isinstance(receipt, Mapping) or digest_json(receipt) != capability["receipt_digest"]:
            raise ClaimError("Optimizer continuation intended receipt differs")
        prs = self._snapshot_rows("pull_requests", "node_id", "OPTIMIZER-370")
        if len(prs) != 1:
            raise ClaimError("Optimizer continuation requires exactly PR 135")
        pr = prs[0]
        expected_pr = {
            "number": capability["pr"], "state": "open", "merged": False,
            "ci": "success", "base": self.target_branch,
            "head": capability["pr_head_branch"], "head_sha": capability["pr_head_sha"],
            "draft": True,
        }
        if any(pr.get(key) != value for key, value in expected_pr.items()):
            raise ClaimError("Optimizer continuation PR 135 metadata differs")
        now = self.clock()
        bounded_expiry = min(
            parse_time(claim["expires_at"]),
            now + timedelta(minutes=int(capability["continuation_minutes"])),
        )
        continuation = {
            "schema_version": 1,
            "kind": OPTIMIZER_CONTINUATION_KIND,
            "status": "ARMED",
            "node_id": "OPTIMIZER-370",
            "grant_id": capability["grant_id"],
            "owner": capability["claim_owner"],
            "claim_digest": digest_json(claim),
            "capability_digest": digest_json(capability),
            "capability_commit": capability["capability_commit"],
            "target_sha": target_sha,
            "target_tree": self._commit_tree(target_sha),
            "release_id": None,
            "github_snapshot_digest": None,
            "reconciliation_digest": None,
            "doctor_evidence_digest": None,
            "main_sha": capability["main_sha"],
            "pr": capability["pr"],
            "receipt_digest": capability["receipt_digest"],
            "expires_at": format_time(bounded_expiry),
            "created_at": format_time(now),
        }
        issues = self._optimizer_continuation_issues(
            continuation, claim, receipt, statuses=("ARMED",), live=False
        )
        if issues:
            raise ClaimError("; ".join(issues))
        try:
            self._exclusive_write_json(self.optimizer_continuation_path, continuation)
        except FileExistsError as error:
            raise ClaimError("Optimizer continuation CAS create raced") from error
        return continuation

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
        continuation_required = {
            "continuation_digest", "continuation_target_sha", "continuation_grant_id",
        }
        if not isinstance(intent, Mapping) or set(intent) not in (
            required,
            required | continuation_required,
        ):
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
        continuation: Mapping[str, Any] | None = None
        if continuation_required.issubset(intent):
            value = read_json(self.optimizer_continuation_path)
            if not isinstance(value, Mapping):
                raise ClaimError("sealed repair completion continuation is unavailable")
            continuation = value
            bound_digest = digest_json(value) == intent.get("continuation_digest")
            if value.get("status") == "CONSUMED":
                bound_digest = (
                    value.get("previous_digest") == intent.get("continuation_digest")
                    and value.get("receipt_commit") == intent.get("receipt_commit")
                )
            if (
                not bound_digest
                or value.get("target_sha") != intent.get("continuation_target_sha")
                or value.get("grant_id") != intent.get("continuation_grant_id")
            ):
                raise ClaimError("sealed repair completion continuation binding differs")
            if value.get("status") != "CONSUMED":
                continuation_issues = self._optimizer_continuation_issues(
                    value,
                    claim,
                    receipt,
                    statuses=("CONSUMING",),
                    live=False,
                    check_expiry=False,
                )
                if continuation_issues:
                    raise ClaimError("; ".join(continuation_issues))
        final = str(intent["remote_expected_final"])
        receipt_commit = intent.get("receipt_commit")
        remote = self.remote_branch_sha(str(record["branch"]))

        if continuation is not None and continuation.get("status") == "CONSUMED":
            if (
                not isinstance(receipt_commit, str)
                or remote != receipt_commit
                or not self.receipt_path(node_id).is_file()
                or digest_json(read_json(self.receipt_path(node_id))) != digest_json(receipt)
                or not self._exact_receipt_index_entry(
                    node_id, receipt_commit, receipt, record
                )
            ):
                raise ClaimError("consumed Optimizer continuation terminal evidence differs")
            if (
                self._commit_parents(receipt_commit) != (final,)
                or self._commit_tree(receipt_commit) != receipt.get("final_tree")
            ):
                raise ReceiptError("consumed Optimizer receipt topology or tree differs")
            shown = self._git(("show", "-s", "--format=%B", receipt_commit), check=False)
            parsed = self._parse_receipt_message(shown.stdout) if shown.returncode == 0 else None
            if not isinstance(parsed, Mapping) or digest_json(parsed) != digest_json(receipt):
                raise ReceiptError("consumed Optimizer receipt payload differs")
            self.claim_path(node_id).unlink(missing_ok=True)
            intent_path.unlink()
            return receipt_commit

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
            if continuation is not None:
                self._transition_optimizer_continuation("CONSUMING", "ACTIVE")
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
            if continuation is not None:
                self._transition_optimizer_continuation("CONSUMING", "ACTIVE")
            intent_path.unlink()
            return None
        if remote != receipt_commit:
            error = ClaimError("sealed repair completion recovery remote head is ambiguous")
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
        self.acquire_global_validation_lease(node_id, validation_owner, lease_minutes=10)
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
            if continuation is not None:
                self._transition_optimizer_continuation(
                    "CONSUMING", "CONSUMED", receipt_commit=str(receipt_commit)
                )
            self.claim_path(node_id).unlink()
            intent_path.unlink()
            append_jsonl(self.state_dir / "sealed-repair-adverse.jsonl", {
                "event": "receipt_publication_recovered_after_restart",
                "node_id": node_id, "receipt_commit": receipt_commit,
            })
            return receipt_commit
        finally:
            self.release_global_validation_lease(node_id, validation_owner)

    def complete(self, node_id: str, owner: str, receipt: Mapping[str, Any]) -> str:
        if node_id not in REPAIR_AUTHORITY_MATERIAL_DIGESTS:
            return super().complete(node_id, owner, receipt)
        record = self._repair_record(node_id)
        if self._has_git_repository() and not self.verify_git_objects:
            raise ClaimError("sealed repair completion requires Git object verification")
        if not self._origin_is_configured_repository(record):
            raise ClaimError("sealed repair completion requires literal configured origin")
        consumed = self._recover_consumed_optimizer_completion_without_intent(
            node_id, owner, receipt, record
        )
        if consumed is not None:
            return consumed
        terminal = self._recover_terminal_repair_completion_without_claim(
            node_id, owner, receipt, record
        )
        if terminal is not None:
            return terminal
        claim_path = self.claim_path(node_id)
        if not claim_path.is_file():
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
        if claim.get("status") not in {"CLAIMED", "COMPLETING"}:
            raise ClaimError("sealed repair completion claim status is not executable")
        if parse_time(claim.get("expires_at")) <= self.clock():
            raise ClaimError("sealed repair completion lease expired")
        continuation = self._arm_optimizer_continuation(claim, receipt) if node_id == "OPTIMIZER-370" else None
        if continuation is None:
            live_issues = self._live_release_issues(record, str(claim.get("target_sha")))
            if live_issues:
                raise ClaimError("; ".join(live_issues))
            binding_issues = self._release_binding_issues(claim)
            if binding_issues:
                raise ClaimError("; ".join(binding_issues))
        else:
            continuation_issues = self._optimizer_continuation_issues(
                continuation, claim, receipt, statuses=("ACTIVE", "CONSUMING")
            )
            if continuation_issues:
                raise ClaimError("; ".join(continuation_issues))
        local_path = self.receipt_path(node_id)
        if local_path.exists():
            raise ReceiptError("sealed repair cannot overwrite a local receipt")
        final = receipt.get("final_commit")
        if not isinstance(final, str) or self.remote_branch_sha(str(record["branch"])) != final:
            raise ReceiptError("sealed repair remote branch must equal the exact final candidate")
        issues = self._replacement_receipt_issues(
            node_id, receipt, active_claim=claim, continuation=continuation
        )
        if issues:
            raise ReceiptError("; ".join(issues))
        validation_owner = f"sealed-repair-completion:{owner}"
        self.acquire_global_validation_lease(node_id, validation_owner, lease_minutes=10)
        receipt_commit: str | None = None
        remote_published = False
        intent_path = self.state_dir / f"sealed-repair-completion-{node_id.lower()}.json"
        claim_state = dict(claim)
        try:
            if continuation is None and self._release_binding_issues(claim):
                raise ClaimError("sealed repair release changed before receipt publication")
            if self.remote_branch_sha(str(record["branch"])) != final:
                raise ReceiptError("sealed repair remote final moved before receipt publication")
            if continuation is not None and continuation.get("status") == "ACTIVE":
                continuation = self._transition_optimizer_continuation("ACTIVE", "CONSUMING")
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
            if continuation is not None:
                intent.update({
                    "continuation_digest": digest_json(continuation),
                    "continuation_target_sha": continuation["target_sha"],
                    "continuation_grant_id": continuation["grant_id"],
                })
            atomic_write_json(intent_path, intent)
            claim_state["status"] = "COMPLETING"
            atomic_write_json(claim_path, claim_state)
            receipt_commit = self._create_receipt_commit(node_id, receipt)
            intent["receipt_commit"] = receipt_commit
            atomic_write_json(intent_path, intent)
            self._cas_update_branch(str(record["branch"]), str(final), receipt_commit)
            remote_published = self.remote_branch_sha(str(record["branch"])) == receipt_commit
            if not remote_published:
                raise ReceiptError("sealed repair receipt remote CAS verification failed")
            if continuation is None and self._release_binding_issues(claim):
                raise ClaimError("sealed repair release changed during receipt publication")
            if continuation is None:
                live_issues = self._live_release_issues(record, str(claim["target_sha"]))
                if live_issues:
                    raise ClaimError("; ".join(live_issues))
            else:
                continuation_issues = self._optimizer_continuation_issues(
                    continuation, claim_state, receipt, statuses=("CONSUMING",)
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
            if continuation is not None:
                continuation = self._transition_optimizer_continuation(
                    "CONSUMING", "CONSUMED", receipt_commit=str(receipt_commit)
                )
            claim_path.unlink(missing_ok=True)
            intent_path.unlink(missing_ok=True)
            return receipt_commit
        except Exception:
            if continuation is not None:
                durable_continuation = self._reconcile_optimizer_continuation_transition()
                if (
                    isinstance(durable_continuation, Mapping)
                    and durable_continuation.get("status") == "CONSUMED"
                ):
                    # CONSUMED is the durable commit point.  Receipt publication and
                    # evidence must never be compensated after this transition.
                    raise
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
                if continuation is not None and continuation.get("status") == "CONSUMING":
                    self._transition_optimizer_continuation("CONSUMING", "ACTIVE")
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
            self.release_global_validation_lease(node_id, validation_owner)

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
            "target_sha", "release_id", "actor", "completed_at",
        }
        if not isinstance(value, Mapping) or set(value) != required:
            raise AutopilotError("Builder retirement execution record is invalid")
        if value.get("kind") != BUILDER_EXECUTION_KIND or value.get("status") != "RETIRED":
            raise AutopilotError("Builder retirement execution disposition is invalid")
        return value

    def _builder_recovery_issues(self) -> tuple[str, ...]:
        execution = self._builder_execution()
        if execution is None:
            return ()
        recovery = self._builder_document(f".autopilot/state/{BUILDER_RECOVERY_FILE}")
        required = {
            "schema_version", "kind", "recovery_id", "snapshot_digest",
            "reconciliation_digest", "doctor_evidence_digest", "target_sha", "recorded_at",
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
        replan = self._builder_document(BUILDER_REPLAN_PATH) or {}
        branches = self._snapshot_rows("branches", "name", replan.get("branch"))
        refs = self._snapshot_rows("refs", "name", replan.get("archive_ref"))
        if branches:
            return ("Builder retirement fresh snapshot still contains canonical source",)
        if len(refs) != 1 or refs[0].get("sha") != replan.get("candidate_commit"):
            return ("Builder retirement fresh snapshot omits the exact archive ref",)
        return ()

    def after_install_github_snapshot(self) -> None:
        if self._builder_execution() is not None:
            atomic_write_json(
                self.builder_recovery_path,
                {
                    "schema_version": 1,
                    "kind": BUILDER_EXECUTION_KIND,
                    "recovery_id": "builder-330-stale-candidate-recovery-v1",
                    "snapshot_digest": self._snapshot_digest(),
                    "reconciliation_digest": None,
                    "doctor_evidence_digest": None,
                    "target_sha": self.current_target_sha(),
                    "recorded_at": format_time(self.clock()),
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

    def _builder_history_issues(self, replan: Mapping[str, Any]) -> tuple[str, ...]:
        if not self.verify_git_objects:
            return ()
        claim = str(replan["claim_commit"])
        candidate = str(replan["candidate_commit"])
        if self._commit_parents(candidate) != (claim,):
            return ("Builder candidate parent differs from sealed claim",)
        if self._commit_tree(claim) != replan["claim_tree"] or self._commit_tree(candidate) != replan["candidate_tree"]:
            return ("Builder sealed claim or candidate tree differs",)
        if tuple(sorted(self._diff_paths(str(replan["claim_target_sha"]), candidate))) != tuple(
            sorted(replan["preserved_candidate_paths"])
        ):
            return ("Builder candidate diff differs from exact preserved paths",)
        return ()

    def _recover_expired_builder_lease(self, replan: Mapping[str, Any]) -> None:
        if not self.builder_lease_path.is_file():
            return
        value = read_json(self.builder_lease_path)
        required = {
            "schema_version", "kind", "recovery_id", "node_id", "actor",
            "source_head", "archive_ref", "target_sha", "release_id",
            "expires_at", "status",
        }
        if not isinstance(value, Mapping) or set(value) != required:
            raise ClaimError("Builder retirement existing lease is foreign or malformed")
        if value.get("kind") != BUILDER_EXECUTION_KIND or value.get("status") != "ACTIVE":
            raise ClaimError("Builder retirement existing lease requires reconciliation")
        if parse_time(value.get("expires_at")) > self.clock():
            raise ClaimError("Builder retirement lease already exists")
        source_ref = f"refs/heads/{replan['branch']}"
        if self._remote_ref_sha(source_ref) != replan["expected_remote_head"] or self._remote_ref_sha(
            str(replan["archive_ref"])
        ) is not None:
            raise ClaimError("expired Builder lease cannot be recovered after ref mutation")
        archive = self.state_dir / "builder-retirement-leases" / (digest_json(value).replace(":", "-") + ".json")
        atomic_write_json(archive, {**value, "status": "EXPIRED_RECOVERED", "recovered_at": format_time(self.clock())})
        self.builder_lease_path.unlink()

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
            "lease_digest", "prepared_at",
        }
        if not isinstance(intent, Mapping) or set(intent) != required:
            raise ClaimError("Builder retirement prepared intent is foreign or malformed")
        if intent.get("kind") != BUILDER_EXECUTION_KIND or intent.get("status") != "PREPARED":
            raise ClaimError("Builder retirement prepared intent requires reconciliation")
        if not self.builder_lease_path.is_file():
            raise ClaimError("Builder interrupted retirement lease is missing")
        lease = read_json(self.builder_lease_path)
        if not isinstance(lease, Mapping) or digest_json(lease) != intent.get("lease_digest"):
            raise ClaimError("Builder interrupted retirement lease binding differs")
        for key in ("recovery_id", "source_head", "archive_ref", "target_sha", "release_id", "actor"):
            if lease.get(key) != intent.get(key):
                raise ClaimError(f"Builder interrupted retirement lease {key} differs")
        expected = str(replan["expected_remote_head"])
        source_ref = f"refs/heads/{replan['branch']}"
        archive_ref = str(replan["archive_ref"])
        source = self._remote_ref_sha(source_ref)
        archive = self._remote_ref_sha(archive_ref)
        if source == expected and archive is None:
            if self.builder_lease_path.is_file() and parse_time(read_json(self.builder_lease_path).get("expires_at")) <= self.clock():
                self._recover_expired_builder_lease(replan)
                self.builder_intent_path.unlink()
                append_jsonl(self.state_dir / BUILDER_AUDIT_FILE, {
                    "event": "builder_prepared_intent_cleared_without_mutation",
                    "source_head": expected, "recorded_at": format_time(self.clock()),
                })
                return None
            raise ClaimError("Builder retirement prepared transaction is still leased")
        if source is not None or archive != expected:
            raise ClaimError("Builder retirement prepared transaction refs are ambiguous")
        fetch_ref = "refs/hive-mind-autopilot/repair-fetch/builder-330/" + expected
        self._git(("update-ref", "-d", fetch_ref), check=False)
        fetched = self._git(("fetch", "--no-tags", "origin", f"{archive_ref}:{fetch_ref}"), check=False)
        try:
            if fetched.returncode != 0 or self._builder_history_issues(replan):
                raise ClaimError("Builder interrupted retirement archive verification failed")
            if self._commit_tree(expected) != replan["candidate_tree"]:
                raise ClaimError("Builder interrupted retirement archive tree differs")
            execution = {
                "schema_version": 1,
                "kind": BUILDER_EXECUTION_KIND,
                "status": "RETIRED",
                "recovery_id": intent["recovery_id"],
                "source_head": expected,
                "archive_ref": archive_ref,
                "snapshot_digest": intent["snapshot_digest"],
                "reconciliation_digest": intent["reconciliation_digest"],
                "doctor_evidence_digest": intent["doctor_evidence_digest"],
                "target_sha": intent["target_sha"],
                "release_id": intent["release_id"],
                "actor": intent["actor"],
                "completed_at": format_time(self.clock()),
            }
            atomic_write_json(self.builder_execution_path, execution)
            append_jsonl(self.state_dir / BUILDER_AUDIT_FILE, {"event": "builder_branch_retirement_recovered", **execution})
            if self.builder_lease_path.is_file():
                retained_lease = read_json(self.builder_lease_path)
                lease_archive = self.state_dir / "builder-retirement-leases" / (
                    digest_json(retained_lease).replace(":", "-") + ".json"
                )
                atomic_write_json(lease_archive, {**retained_lease, "status": "RECOVERED", "released_at": format_time(self.clock())})
                self.builder_lease_path.unlink()
            self.builder_intent_path.unlink()
            return execution
        finally:
            self._git(("update-ref", "-d", fetch_ref), check=False)

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
        if not isinstance(intent, Mapping) or intent.get("status") != "PREPARED":
            raise ClaimError("Builder post-execution intent is invalid")
        for key in ("recovery_id", "source_head", "archive_ref", "target_sha", "release_id", "actor"):
            if intent.get(key) != execution.get(key):
                raise ClaimError(f"Builder post-execution cleanup {key} differs")
        source_ref = f"refs/heads/{replan['branch']}"
        archive_ref = str(replan["archive_ref"])
        expected = str(replan["expected_remote_head"])
        if self._remote_ref_sha(source_ref) is not None or self._remote_ref_sha(archive_ref) != expected:
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
        self.builder_intent_path.unlink()
        append_jsonl(self.state_dir / BUILDER_AUDIT_FILE, {
            "event": "builder_post_execution_cleanup_recovered",
            "recovery_id": execution["recovery_id"],
            "recorded_at": format_time(self.clock()),
        })
        return execution

    def retire_builder_branch(self, *, actor: str) -> Mapping[str, Any]:
        if not actor.strip():
            raise AutopilotError("Builder retirement actor is required")
        issues = self.sealed_recovery_issues()
        if issues:
            raise AutopilotError("; ".join(issues))
        replan = self._builder_document(BUILDER_REPLAN_PATH)
        bootstrap = self._builder_document(BUILDER_BOOTSTRAP_PATH)
        assert isinstance(replan, Mapping) and isinstance(bootstrap, Mapping)
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
        live_issues = self._live_release_issues(replan, self.current_target_sha())
        if live_issues:
            raise ClaimError("; ".join(live_issues))
        capability = str(bootstrap["capability_commit"])
        if self.verify_git_objects and not self.is_ancestor(capability, self.current_target_sha()):
            raise ClaimError("Builder retirement current release omits capability")
        branches = self._snapshot_rows("branches", "name", replan["branch"])
        if len(branches) != 1 or branches[0].get("sha") != replan["candidate_commit"] or branches[0].get("stale") is not True:
            raise ClaimError("Builder retirement snapshot does not bind exact stale branch")
        if self._snapshot_rows("pull_requests", "node_id", "BUILDER-330"):
            raise ClaimError("Builder retirement is forbidden when a Builder PR exists")
        if self.claim_path("BUILDER-330").is_file() or self.validation_lease_path.is_file():
            raise ClaimError("Builder retirement is forbidden by active claim or validation lease")
        history_issues = self._builder_history_issues(replan)
        if history_issues:
            raise ClaimError("; ".join(history_issues))
        now = self.clock()
        lease = {
            "schema_version": 1,
            "kind": BUILDER_EXECUTION_KIND,
            "recovery_id": "builder-330-stale-candidate-recovery-v1",
            "node_id": "BUILDER-330",
            "actor": actor,
            "source_head": replan["expected_remote_head"],
            "archive_ref": replan["archive_ref"],
            "target_sha": self.current_target_sha(),
            "release_id": release.get("release_id"),
            "expires_at": format_time(now + timedelta(minutes=10)),
            "status": "ACTIVE",
        }
        self.builder_lease_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.builder_lease_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            raise ClaimError("Builder retirement lease already exists") from error
        try:
            os.write(descriptor, (json.dumps(lease, sort_keys=True, indent=2) + "\n").encode())
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        preserve_lease = False
        fetch_ref = "refs/hive-mind-autopilot/repair-fetch/builder-330/" + str(replan["expected_remote_head"])
        try:
            source_ref = f"refs/heads/{replan['branch']}"
            archive_ref = str(replan["archive_ref"])
            expected = str(replan["expected_remote_head"])
            if self._release_binding_issues():
                raise ClaimError("Builder retirement release binding is stale")
            if self._remote_ref_sha(source_ref) != expected:
                raise ClaimError("Builder retirement source is absent or moved")
            if self._remote_ref_sha(archive_ref) is not None:
                raise ClaimError("Builder retirement archive already exists; reuse is forbidden")
            if parse_time(read_json(self.builder_lease_path).get("expires_at")) <= self.clock():
                raise ClaimError("Builder retirement lease expired")
            self._git(("update-ref", "-d", fetch_ref), check=False)
            fetched = self._git(("fetch", "--no-tags", "origin", f"{source_ref}:{fetch_ref}"), check=False)
            observed = self._git(("rev-parse", "--verify", fetch_ref), check=False).stdout.strip()
            if fetched.returncode != 0 or observed != expected:
                raise ClaimError("Builder retirement cannot fetch the exact source object")
            history_issues = self._builder_history_issues(replan)
            if history_issues:
                raise ClaimError("; ".join(history_issues))
            if self._remote_ref_sha(source_ref) != expected or self._remote_ref_sha(archive_ref) is not None:
                raise ClaimError("Builder retirement refs changed during verification")
            if self._release_binding_issues():
                raise ClaimError("Builder retirement release changed before archive transaction")
            live_issues = self._live_release_issues(replan, str(lease["target_sha"]))
            if live_issues:
                raise ClaimError("; ".join(live_issues))
            intent = {
                "schema_version": 1,
                "kind": BUILDER_EXECUTION_KIND,
                "status": "PREPARED",
                "recovery_id": "builder-330-stale-candidate-recovery-v1",
                "source_head": expected,
                "archive_ref": archive_ref,
                "target_sha": lease["target_sha"],
                "release_id": lease["release_id"],
                "snapshot_digest": self._snapshot_digest(),
                "reconciliation_digest": self._reconciliation_digest(),
                "doctor_evidence_digest": self._doctor_evidence_digest(),
                "actor": actor,
                "lease_digest": digest_json(lease),
                "prepared_at": format_time(self.clock()),
            }
            atomic_write_json(self.builder_intent_path, intent)
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
            try:
                if self._remote_ref_sha(source_ref) is not None or self._remote_ref_sha(archive_ref) != expected:
                    raise ClaimError("Builder retirement remote verification failed")
                fetched = self._git(("fetch", "--no-tags", "origin", f"{archive_ref}:{fetch_ref}"), check=False)
                if fetched.returncode != 0 or self._commit_tree(expected) != replan["candidate_tree"] or not self.is_ancestor(
                    str(replan["claim_commit"]), expected
                ):
                    raise ClaimError("Builder retirement archive tree or ancestry verification failed")
                if self._release_binding_issues():
                    raise ClaimError("Builder retirement release changed during archive transaction")
                live_issues = self._live_release_issues(replan, str(lease["target_sha"]))
                if live_issues:
                    raise ClaimError("; ".join(live_issues))
                execution = {
                    "schema_version": 1,
                    "kind": BUILDER_EXECUTION_KIND,
                    "status": "RETIRED",
                    "recovery_id": "builder-330-stale-candidate-recovery-v1",
                    "source_head": expected,
                    "archive_ref": archive_ref,
                    "snapshot_digest": self._snapshot_digest(),
                    "reconciliation_digest": self._reconciliation_digest(),
                    "doctor_evidence_digest": self._doctor_evidence_digest(),
                    "target_sha": lease["target_sha"],
                    "release_id": lease["release_id"],
                    "actor": actor,
                    "completed_at": format_time(self.clock()),
                }
                atomic_write_json(self.builder_execution_path, execution)
                append_jsonl(self.state_dir / BUILDER_AUDIT_FILE, {"event": "builder_branch_retired", **execution})
                self.builder_intent_path.unlink(missing_ok=True)
                return execution
            except Exception as error:
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
                    adverse["status"] = "RECONCILIATION_REQUIRED"
                    adverse["error"] = str(error)
                    adverse["recorded_at"] = format_time(self.clock())
                    atomic_write_json(self.builder_intent_path, adverse)
                raise
        finally:
            self._git(("update-ref", "-d", fetch_ref), check=False)
            if not preserve_lease and self.builder_lease_path.is_file():
                current_lease = read_json(self.builder_lease_path)
                archive = self.state_dir / "builder-retirement-leases" / (
                    digest_json(current_lease).replace(":", "-") + ".json"
                )
                atomic_write_json(archive, {**current_lease, "status": "RELEASED", "released_at": format_time(self.clock())})
                self.builder_lease_path.unlink()
