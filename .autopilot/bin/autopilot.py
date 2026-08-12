#!/usr/bin/env python3
"""Command-line interface for the repository-resident implementation control plane."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Sequence

from attended_host import AttendedCodexHost, EvidenceResolver
from controller import FULL_SHA, format_time
from dag_standard import add_dag_standard_arguments, run_dag_standard_command
from durable_controller import (
    AutopilotError,
    ClaimError,
    ConfigurationError,
    ReceiptError,
    append_jsonl,
    atomic_write_json,
    digest_json,
    read_json,
)
from host_execution import execute_contract
from orchestration import (
    OrchestrationError,
    bind_launch,
    binding_events,
    build_orchestration_contract,
    infer_intent,
    load_policy,
    prepare_launch,
    should_publish_release,
    simple_prompt,
)
from release_barrier import (
    RELEASE_HISTORY,
    RELEASE_KIND,
)
from release_barrier import (
    ControlPlane as ReleaseBarrierControlPlane,
)
from round_driver import drive_round
from sealed_recovery import SealedRecoveryMixin

RECON_PREMATURE_RECEIPT = "37055e0b8c6dac451e899401802061fe258594f7"
RECON_ANCESTRY_DUPLICATE_RECEIPT = "4191ebfd571c9852f5f6faaa43cea0f48f3e0fe8"
RECON_CANONICAL_RECEIPT = "369f956817ff10231c06d09c7c802f47f76d57b0"
RETIREMENT_KIND = "hive-mind-autopilot-receipt-branch-retirement-v1"
RETIREMENT_DOCUMENT = ".autopilot/receipt-branch-retirements.json"
RETIREMENT_COURT_DOCUMENT = ".autopilot/receipt-branch-retirement-court.json"
RETIREMENT_AUDIT = "receipt-branch-retirement-audit.jsonl"
RETIREMENT_RECOVERY = "receipt-branch-retirement-recovery.json"
RETIREMENT_EXECUTION = "receipt-branch-retirement-execution.json"

EXPLORER_COURT_DISPOSITION = {
    "schema_version": 1,
    "court_id": "court-explorer-310-receipt-boundary-20260811",
    "node_id": "EXPLORER-310",
    "decision": "QUARANTINE",
    "judge_identity": "court:appeals-independent-explorer-310",
    "cross_examiner_identity": "curator:receipt-retirement-cross-examination",
    "finding": "The rejected receipt branch must be retained under a sealed quarantine ref before its active node ref can be retired.",
    "blocker_id": "sha256:e3d19e5a17fb286d55eb7bf82d975aaed569c514d37553218391e13518b48382",
}

EXPLORER_APPEALS_ORDERING_DISPOSITION = {
    "schema_version": 1,
    "appeals_id": "appeals-explorer-310-retirement-ordering-20260811",
    "node_id": "EXPLORER-310",
    "decision": "ADAPT",
    "preserves_court_disposition": "QUARANTINE",
    "appeals_judge_identity": "appeals:independent-retirement-ordering",
    "incident_target_sha": "01ca563a8a11fddde6f698abe42d10db3dd1bc71",
    "capability_commit": "e57790de9b6db7a426db620f4db59db8c13495bc",
    "finding": "The sealed incident target is provenance, while execution requires a current reconciled singleton target containing the integrated retirement capability.",
}

EXPLORER_RETIREMENT = {
    "schema_version": 1,
    "retirement_id": "explorer-310-rejected-receipt-branch-v1",
    "node_id": "EXPLORER-310",
    "origin_name": "origin",
    "origin_url": "https://github.com/kb4beast/hive-mind-os.git",
    "repository": "kb4beast/hive-mind-os",
    "branch": "autopilot/explorer-310",
    "candidate_commit": "3d305e63391094846e8d8ebacad2fa73dbb2db8b",
    "receipt_commit": "2304036fe92e7fe499785a500c173300943a55fb",
    "expected_remote_head": "2304036fe92e7fe499785a500c173300943a55fb",
    "incident_target_sha": "01ca563a8a11fddde6f698abe42d10db3dd1bc71",
    "capability_commit": "e57790de9b6db7a426db620f4db59db8c13495bc",
    "contract_version": 1,
    "plan_fingerprint": "sha256:9769f9796efb351da9b764fd49983b1130adccc0b8592e42581714d3727f8b39",
    "blocker_id": "sha256:e3d19e5a17fb286d55eb7bf82d975aaed569c514d37553218391e13518b48382",
    "violation": "Explorer's broad Git argv allowlist admitted git diff --output=escaped.patch, a repository-writing flag outside its read-only authority.",
    "court_disposition_digest": digest_json(EXPLORER_COURT_DISPOSITION),
    "appeals_ordering_disposition_digest": digest_json(EXPLORER_APPEALS_ORDERING_DISPOSITION),
    "archive_ref": "refs/hive-mind-autopilot/quarantine/explorer-310/2304036fe92e7fe499785a500c173300943a55fb",
    "replacement_required": True,
}


class ControlPlane(SealedRecoveryMixin, ReleaseBarrierControlPlane):
    """CLI plane with sealed, fail-closed RECON receipt repairs.

    RECON-010 published a durable receipt before the merged PR #120 release-barrier
    amendment was fully implemented. The historical receipt must remain in Git history,
    but the replacement receipt required by the amended contract must become the only
    active RECON completion record. This repair recognizes only that exact historical
    receipt and only when the replacement explicitly binds it in receipt authority.
    PR #124 later integrated a second receipt for the same candidate alongside the
    already-expanded canonical receipt. The exact sibling pair is also sealed here:
    the expanded receipt is accepted only when all immutable candidate fields match,
    its scope and grants strictly contain the older receipt, and Git confirms both
    receipt commits are direct children of the candidate on the current target.

    The sealed recovery mixin additionally admits only the exact retained recovery
    authorities for OPTIMIZER-370, ORCH-300, and BUILDER-330. All unrelated duplicate
    receipts and branch-recovery attempts remain fail-closed.
    """

    def _resolve_integrated_recon_ancestry_duplicate(
        self, records: list[dict[str, Any]]
    ) -> list[dict[str, Any]] | None:
        by_commit = {
            record.get("commit"): record
            for record in records
            if isinstance(record.get("commit"), str)
        }
        if set(by_commit) != {
            RECON_ANCESTRY_DUPLICATE_RECEIPT,
            RECON_CANONICAL_RECEIPT,
        }:
            return None
        duplicate = by_commit[RECON_ANCESTRY_DUPLICATE_RECEIPT]
        canonical = by_commit[RECON_CANONICAL_RECEIPT]
        old_receipt = duplicate.get("receipt")
        new_receipt = canonical.get("receipt")
        if not isinstance(old_receipt, Mapping) or not isinstance(new_receipt, Mapping):
            return None
        for key in (
            "schema_version",
            "plan_fingerprint",
            "node_id",
            "contract_version",
            "base_commit",
            "base_tree",
            "branch",
            "pr",
            "final_commit",
            "final_tree",
        ):
            if new_receipt.get(key) != old_receipt.get(key):
                return None
        final = new_receipt.get("final_commit")
        if new_receipt.get("node_id") != "RECON-010" or not isinstance(final, str):
            return None
        old_paths = old_receipt.get("changed_paths")
        new_paths = new_receipt.get("changed_paths")
        old_authority = old_receipt.get("authority")
        new_authority = new_receipt.get("authority")
        old_grants = old_authority.get("grants") if isinstance(old_authority, Mapping) else None
        new_grants = new_authority.get("grants") if isinstance(new_authority, Mapping) else None
        evidence_refs = new_receipt.get("evidence_refs")
        if not (
            isinstance(old_paths, list)
            and isinstance(new_paths, list)
            and set(old_paths) < set(new_paths)
            and isinstance(old_grants, list)
            and isinstance(new_grants, list)
            and set(old_grants) < set(new_grants)
            and "dispatcher-release-barrier" in new_grants
            and isinstance(evidence_refs, list)
            and f"historical-receipt:{RECON_PREMATURE_RECEIPT}" in evidence_refs
        ):
            return None
        if self._has_git_repository():
            target = self.current_target_sha()
            for receipt_commit in (
                RECON_ANCESTRY_DUPLICATE_RECEIPT,
                RECON_CANONICAL_RECEIPT,
            ):
                parent = self._git(
                    ("rev-parse", f"{receipt_commit}^"), check=True
                ).stdout.strip()
                if parent != final or not self.is_ancestor(receipt_commit, target):
                    return None
        return [canonical]

    def _resolve_recon_receipt_records(
        self, records: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        integrated = self._resolve_integrated_recon_ancestry_duplicate(records)
        if integrated is not None:
            return integrated
        if len(records) != 2:
            return records
        historical = next(
            (
                record
                for record in records
                if record.get("commit") == RECON_PREMATURE_RECEIPT
            ),
            None,
        )
        replacement = next(
            (
                record
                for record in records
                if record.get("commit") != RECON_PREMATURE_RECEIPT
            ),
            None,
        )
        if historical is None or replacement is None:
            return records
        old_receipt = historical.get("receipt")
        new_receipt = replacement.get("receipt")
        if not isinstance(old_receipt, Mapping) or not isinstance(new_receipt, Mapping):
            return records
        authority = new_receipt.get("authority")
        if not isinstance(authority, Mapping):
            return records
        if authority.get("supersedes_receipt_commit") != RECON_PREMATURE_RECEIPT:
            return records
        for key in (
            "schema_version",
            "plan_fingerprint",
            "node_id",
            "contract_version",
            "base_commit",
            "base_tree",
            "branch",
            "pr",
        ):
            if new_receipt.get(key) != old_receipt.get(key):
                return records
        if new_receipt.get("node_id") != "RECON-010":
            return records
        final = new_receipt.get("final_commit")
        if self._has_git_repository():
            if not isinstance(final, str) or not self.is_ancestor(
                RECON_PREMATURE_RECEIPT, final
            ):
                return records
        return [replacement]

    def _durable_receipt_records(self) -> dict[str, list[dict[str, Any]]]:
        records = super()._durable_receipt_records()
        updated = dict(records)
        recon = updated.get("RECON-010")
        if isinstance(recon, list):
            resolved = self._resolve_recon_receipt_records(recon)
            if resolved is not recon:
                updated["RECON-010"] = resolved
        for node_id in ("BUILDER-330", "OPTIMIZER-370", "ORCH-300"):
            node_records = updated.get(node_id)
            if isinstance(node_records, list):
                resolved = self.resolve_sealed_repair_records(node_id, node_records)
                if resolved is not node_records:
                    updated[node_id] = resolved
        return updated

    @property
    def retirement_document_path(self) -> Path:
        return self.repo_root / RETIREMENT_DOCUMENT

    @property
    def retirement_court_path(self) -> Path:
        return self.repo_root / RETIREMENT_COURT_DOCUMENT

    @property
    def retirement_appeals_path(self) -> Path:
        return self.repo_root / ".autopilot/receipt-branch-retirement-appeals.json"

    @property
    def retirement_execution_path(self) -> Path:
        return self.state_dir / RETIREMENT_EXECUTION

    @property
    def retirement_recovery_path(self) -> Path:
        return self.state_dir / RETIREMENT_RECOVERY

    def _sealed_document(self, path: Path) -> Mapping[str, Any] | None:
        if not path.is_file():
            return None
        value = read_json(path)
        return value if isinstance(value, Mapping) else None

    def receipt_retirement_issues(self) -> tuple[str, ...]:
        issues: list[str] = []
        court = self._sealed_document(self.retirement_court_path)
        if court is None or dict(court) != EXPLORER_COURT_DISPOSITION:
            issues.append("receipt retirement court disposition is not the sealed Explorer quarantine record")
        appeals = self._sealed_document(self.retirement_appeals_path)
        if appeals is None or dict(appeals) != EXPLORER_APPEALS_ORDERING_DISPOSITION:
            issues.append("receipt retirement appeals ordering disposition is not the sealed ADAPT record")
        document = self._sealed_document(self.retirement_document_path)
        if document is None:
            issues.append("required receipt retirement document is missing")
            return tuple(issues)
        if document.get("schema_version") != 1:
            issues.append("receipt retirement document schema_version is unsupported")
        records = document.get("receipt_branch_retirements")
        if not isinstance(records, list) or len(records) != 1:
            issues.append("receipt retirement document must contain exactly one sealed record")
        elif not isinstance(records[0], Mapping) or dict(records[0]) != EXPLORER_RETIREMENT:
            issues.append("receipt retirement record is not the sealed Explorer record")
        target = self.control.get("target")
        if not isinstance(target, Mapping) or target.get("repository") != EXPLORER_RETIREMENT["repository"]:
            issues.append("receipt retirement repository identity does not match the configured singleton repository")
        if EXPLORER_RETIREMENT["plan_fingerprint"] != self.expected_plan_fingerprint:
            issues.append("receipt retirement plan fingerprint is stale")
        node = super().node("EXPLORER-310")
        for key in ("branch", "contract_version"):
            if node.get(key) != EXPLORER_RETIREMENT[key]:
                issues.append(f"receipt retirement {key} does not match the Explorer contract")
        return tuple(dict.fromkeys(issues))

    def validate_configuration(self) -> tuple[str, ...]:
        issues = list(super().validate_configuration())
        issues.extend(self.receipt_retirement_issues())
        issues.extend(self.sealed_recovery_issues())
        try:
            load_policy(self.repo_root)
        except OrchestrationError as error:
            issues.append(str(error))
        return tuple(dict.fromkeys(issues))

    def _retirement_record(self, retirement_id: str) -> Mapping[str, Any]:
        issues = self.receipt_retirement_issues()
        if issues:
            raise AutopilotError("; ".join(issues))
        if retirement_id != EXPLORER_RETIREMENT["retirement_id"]:
            raise AutopilotError("receipt retirement id is not authorized")
        return EXPLORER_RETIREMENT

    def _origin_is_configured_repository(self, record: Mapping[str, Any]) -> bool:
        """Accept only one literal configured origin with no rewrite channel.

        ``git remote get-url origin`` reports the fetch URL when a distinct push URL
        exists.  It is therefore insufficient proof of a push destination.  The
        retirement transaction is deliberately unavailable when a push URL, URL
        rewrite, or process-injected Git config could redirect its sole mutation.
        """

        if record.get("origin_name") != "origin" or not isinstance(record.get("origin_url"), str):
            return False
        blocked_environment = {
            "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS",
            "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM",
        }
        if any(name in os.environ for name in blocked_environment) or any(
            name.startswith("GIT_CONFIG_KEY_") or name.startswith("GIT_CONFIG_VALUE_")
            for name in os.environ
        ):
            return False
        urls = self._git(("config", "--get-all", "remote.origin.url"), check=False)
        if urls.returncode != 0:
            return False
        configured_urls = [line.strip() for line in urls.stdout.splitlines() if line.strip()]
        if configured_urls != [record["origin_url"]]:
            return False
        push_urls = self._git(("config", "--get-all", "remote.origin.pushurl"), check=False)
        if push_urls.returncode not in {0, 1} or push_urls.stdout.strip():
            return False
        rewrites = self._git(("config", "--get-regexp", r"^url\..*\.(insteadOf|pushInsteadOf)$"), check=False)
        if rewrites.returncode not in {0, 1} or rewrites.stdout.strip():
            return False
        return record["origin_url"] == f"https://github.com/{record['repository']}.git"

    def _remote_ref_sha(self, reference: str) -> str | None:
        completed = self._git(("ls-remote", "origin", reference), check=False)
        if completed.returncode != 0:
            raise ClaimError("cannot inspect configured origin: " + completed.stderr.strip())
        fields = completed.stdout.strip().split()
        if not fields:
            return None
        if len(fields) != 2 or fields[1] != reference or FULL_SHA.fullmatch(fields[0]) is None:
            raise ClaimError("configured origin returned an invalid ref identity")
        return fields[0]

    def _retirement_history_issues(self, record: Mapping[str, Any]) -> tuple[str, ...]:
        if not self._has_git_repository():
            return ()
        candidate = str(record["candidate_commit"])
        receipt = str(record["receipt_commit"])
        if not (self.git_object_exists(candidate) and self.git_object_exists(receipt)):
            return ("receipt retirement requires the sealed candidate and receipt objects",)
        if self._commit_parents(receipt) != (candidate,):
            return ("receipt retirement receipt parent is not the sealed candidate",)
        if self._commit_tree(candidate) != self._commit_tree(receipt):
            return ("receipt retirement receipt does not preserve the candidate tree",)
        message = self._git(("show", "-s", "--format=%B", receipt), check=True).stdout
        sealed = self._parse_receipt_message(message)
        if not isinstance(sealed, Mapping):
            return ("receipt retirement receipt message is not canonical completion evidence",)
        for key in ("node_id", "branch", "plan_fingerprint", "contract_version"):
            if sealed.get(key) != record.get(key):
                return (f"receipt retirement receipt {key} does not match the sealed record",)
        if sealed.get("final_commit") != candidate:
            return ("receipt retirement receipt final_commit is not the sealed candidate",)
        return ()

    @staticmethod
    def _archive_payload(record: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "kind": RETIREMENT_KIND,
            "schema_version": 1,
            "retirement_id": record["retirement_id"],
            "node_id": record["node_id"],
            "repository": record["repository"],
            "origin_url": record["origin_url"],
            "branch": record["branch"],
            "candidate_commit": record["candidate_commit"],
            "receipt_commit": record["receipt_commit"],
            "expected_remote_head": record["expected_remote_head"],
            "incident_target_sha": record["incident_target_sha"],
            "capability_commit": record["capability_commit"],
            "plan_fingerprint": record["plan_fingerprint"],
            "contract_version": record["contract_version"],
            "blocker_id": record["blocker_id"],
            "court_disposition_digest": record["court_disposition_digest"],
            "appeals_ordering_disposition_digest": record["appeals_ordering_disposition_digest"],
            "violation": record["violation"],
        }

    def _create_archive_commit(self, record: Mapping[str, Any]) -> str:
        receipt = str(record["receipt_commit"])
        tree = self._git(("rev-parse", f"{receipt}^{{tree}}"), check=True).stdout.strip()
        payload = self._archive_payload(record)
        message = RETIREMENT_KIND + "\n" + json.dumps(payload, sort_keys=True, separators=(",", ":"))
        created = self._git(
            (
                "-c", "user.name=Hive Mind Autopilot Retirement",
                "-c", "user.email=autopilot-retirement@hive-mind.invalid",
                "commit-tree", tree, "-p", receipt, "-m", message,
            ),
            check=True,
            environment={
                "GIT_AUTHOR_NAME": "Hive Mind Autopilot Retirement",
                "GIT_AUTHOR_EMAIL": "autopilot-retirement@hive-mind.invalid",
                "GIT_COMMITTER_NAME": "Hive Mind Autopilot Retirement",
                "GIT_COMMITTER_EMAIL": "autopilot-retirement@hive-mind.invalid",
            },
        ).stdout.strip()
        if FULL_SHA.fullmatch(created) is None:
            raise AutopilotError("receipt retirement did not create a commit")
        if self._commit_parents(created) != (receipt,) or self._commit_tree(created) != tree:
            raise AutopilotError("receipt retirement archive is not a zero-path child of the receipt")
        return created

    def _verify_archive(self, archive_commit: str, record: Mapping[str, Any]) -> None:
        receipt = str(record["receipt_commit"])
        if not self.git_object_exists(archive_commit):
            raise ClaimError("receipt retirement archive object is unavailable after fetch")
        if self._commit_parents(archive_commit) != (receipt,):
            raise ClaimError("receipt retirement archive parent is forged or moved")
        if self._commit_tree(archive_commit) != self._commit_tree(receipt):
            raise ClaimError("receipt retirement archive tree is forged or moved")
        result = self._git(("show", "-s", "--format=%B", archive_commit), check=False)
        expected = RETIREMENT_KIND + "\n" + json.dumps(self._archive_payload(record), sort_keys=True, separators=(",", ":"))
        if result.returncode != 0 or result.stdout.rstrip("\n") != expected:
            raise ClaimError("receipt retirement archive payload is forged or incomplete")

    def _execution(self) -> Mapping[str, Any] | None:
        if not self.retirement_execution_path.is_file():
            return None
        value = read_json(self.retirement_execution_path)
        required = {
            "schema_version", "kind", "status", "retirement_id", "archive_commit", "archive_ref",
            "source_head", "snapshot_digest", "reconciliation_digest", "actor", "completed_at",
        }
        if not isinstance(value, Mapping) or set(value) != required or value.get("schema_version") != 1 or value.get("kind") != RETIREMENT_KIND or value.get("status") != "RETIRED":
            raise AutopilotError("receipt retirement execution record is invalid")
        return value

    def _recovery_issues(self) -> tuple[str, ...]:
        execution = self._execution()
        if execution is None:
            return ()
        recovery = self._sealed_document(self.retirement_recovery_path)
        if recovery is None:
            return ("receipt retirement requires a fresh snapshot and reconciliation before dispatch",)
        required = {"schema_version", "kind", "retirement_id", "snapshot_digest", "reconciliation_digest", "target_sha", "recorded_at"}
        if set(recovery) != required or recovery.get("kind") != RETIREMENT_KIND or recovery.get("retirement_id") != execution.get("retirement_id"):
            return ("receipt retirement recovery record is invalid",)
        if recovery.get("snapshot_digest") != self._snapshot_digest() or recovery.get("reconciliation_digest") != self._reconciliation_digest() or recovery.get("target_sha") != self.current_target_sha():
            return ("receipt retirement requires a fresh snapshot and reconciliation before dispatch",)
        return ()

    def install_github_snapshot(self, source: Path) -> Path:
        path = super().install_github_snapshot(source)
        execution = self._execution()
        if execution is not None:
            atomic_write_json(self.retirement_recovery_path, {
                "schema_version": 1, "kind": RETIREMENT_KIND, "retirement_id": execution["retirement_id"],
                "snapshot_digest": self._snapshot_digest(), "reconciliation_digest": None,
                "target_sha": self.current_target_sha(), "recorded_at": format_time(self.clock()),
            })
        return path

    def reconcile(self, target_sha: str, *, actor: str, reason: str, changed_paths: Sequence[str] = ()) -> Path:
        path = super().reconcile(target_sha, actor=actor, reason=reason, changed_paths=changed_paths)
        execution = self._execution()
        recovery = self._sealed_document(self.retirement_recovery_path)
        if execution is not None and recovery is not None and recovery.get("snapshot_digest") == self._snapshot_digest():
            updated = dict(recovery)
            updated["reconciliation_digest"] = self._reconciliation_digest()
            updated["target_sha"] = self.current_target_sha()
            updated["recorded_at"] = format_time(self.clock())
            atomic_write_json(self.retirement_recovery_path, updated)
        return path

    def _release_issues(self, record: object) -> tuple[str, ...]:
        issues = list(super()._release_issues(record))
        execution = self._execution()
        if execution is not None:
            expected = digest_json(execution)
            if not isinstance(record, Mapping) or record.get("receipt_retirement_execution_digest") != expected:
                issues.append("dispatcher release was issued before receipt retirement recovery")
        return tuple(dict.fromkeys(issues))

    def dispatch(self, *, actor: str, requested_nodes: Sequence[str] = ()) -> Mapping[str, Any]:
        recovery_issues = self._recovery_issues()
        if recovery_issues:
            raise AutopilotError("; ".join(recovery_issues))
        if not actor.strip():
            raise AutopilotError("dispatcher actor is required")
        if self.target_requires_reconciliation():
            raise AutopilotError("dispatcher release is forbidden until live target reconciliation completes")
        reconciliation_digest = self._reconciliation_digest()
        snapshot_digest = self._snapshot_digest()
        if reconciliation_digest is None or snapshot_digest is None:
            raise AutopilotError("dispatcher release requires current reconciliation and GitHub snapshot evidence")
        base_status = self._base_status()
        ready = base_status.get("ready", [])
        eligible = [str(item) for item in ready] if isinstance(ready, list) else []
        if requested_nodes:
            wave = list(dict.fromkeys(str(item) for item in requested_nodes))
            unavailable = [node_id for node_id in wave if node_id not in eligible]
            if unavailable:
                raise AutopilotError("dispatcher cannot release non-eligible nodes: " + ", ".join(unavailable))
            for index, first in enumerate(wave):
                for second in wave[index + 1:]:
                    if self._nodes_conflict(first, second):
                        raise AutopilotError(f"requested parallel release conflicts: {first} vs {second}")
        else:
            wave = []
            for node_id in sorted(eligible):
                if all(not self._nodes_conflict(node_id, chosen) for chosen in wave):
                    wave.append(node_id)
        verdicts = self._candidate_verdicts(base_status, wave)
        directive, action = self._action_sentence(wave)
        record: dict[str, Any] = {
            "schema_version": 1, "kind": RELEASE_KIND, "actor": actor,
            "target_sha": self.current_target_sha(), "plan_fingerprint": self.expected_plan_fingerprint,
            "reconciliation_digest": reconciliation_digest, "github_snapshot_digest": snapshot_digest,
            "released_wave": wave, "directive": directive, "action": action, "verdicts": verdicts,
            "issued_at": format_time(self.clock()),
            "receipt_retirement_execution_digest": digest_json(self._execution()) if self._execution() is not None else None,
        }
        record["release_id"] = digest_json(record)
        atomic_write_json(self.current_release_path, record)
        append_jsonl(self.state_dir / RELEASE_HISTORY, record)
        return record

    def retire_receipt_branch(self, retirement_id: str, *, actor: str) -> Mapping[str, Any]:
        """Perform the sole configured archive-before-delete recovery transaction.

        No user-provided remote, branch, SHA, or archive ref is accepted.  The only
        mutation is a single origin push guarded by both the active-ref and empty-
        archive-ref leases.  This method is intentionally not called by this change.
        """

        if not actor.strip():
            raise AutopilotError("receipt retirement actor is required")
        record = self._retirement_record(retirement_id)
        if not self._origin_is_configured_repository(record):
            raise ClaimError("receipt retirement requires configured origin repository identity")
        current_target = self.current_target_sha()
        if self.target_requires_reconciliation():
            raise ClaimError("receipt retirement requires a current singleton target reconciliation")
        capability = str(record["capability_commit"])
        if not self.git_object_exists(capability) or not self.is_ancestor(capability, current_target):
            raise ClaimError("receipt retirement requires a current singleton target containing the sealed capability commit")
        if self._snapshot_digest() is None or self._reconciliation_digest() is None:
            raise ClaimError("receipt retirement requires current GitHub snapshot and reconciliation evidence")
        if self.claim_path(str(record["node_id"])).is_file():
            raise ClaimError("receipt retirement is forbidden while Explorer has an active claim")
        prior = self._execution()
        archive_ref = str(record["archive_ref"])
        branch_ref = f"refs/heads/{record['branch']}"
        expected = str(record["expected_remote_head"])
        source_head = self._remote_ref_sha(branch_ref)
        archive_head = self._remote_ref_sha(archive_ref)
        if prior is not None:
            if prior.get("retirement_id") != retirement_id:
                raise AutopilotError("receipt retirement execution conflicts with sealed record")
            if source_head is not None or archive_head != prior.get("archive_commit"):
                raise ClaimError("receipt retirement remote state no longer matches its append-only execution record")
            fetched = self._git(("fetch", "--no-tags", "origin", archive_ref), check=False)
            if fetched.returncode != 0:
                raise ClaimError("cannot fetch configured receipt retirement archive")
            self._verify_archive(str(archive_head), record)
            return prior
        if archive_head is not None:
            # A retained archive with a live source is a collision, not an invitation
            # to overwrite either ref.  A source-absent archive can only be resumed
            # after full local content verification.
            if source_head is not None:
                raise ClaimError("receipt retirement archive collision leaves active source untouched")
            fetched = self._git(("fetch", "--no-tags", "origin", archive_ref), check=False)
            if fetched.returncode != 0:
                raise ClaimError("cannot fetch pre-existing receipt retirement archive")
            self._verify_archive(str(archive_head), record)
            archive_commit = str(archive_head)
        else:
            if source_head != expected:
                raise ClaimError("receipt retirement active source does not match sealed expected SHA")
            fetched = self._git(("fetch", "--no-tags", "origin", branch_ref), check=False)
            if fetched.returncode != 0:
                raise ClaimError("cannot fetch sealed Explorer receipt branch")
            history_issues = self._retirement_history_issues(record)
            if history_issues:
                raise AutopilotError("; ".join(history_issues))
            # Re-read both refs immediately before the leased atomic transaction.
            if self._remote_ref_sha(branch_ref) != expected or self._remote_ref_sha(archive_ref) is not None:
                raise ClaimError("receipt retirement remote changed during verification")
            archive_commit = self._create_archive_commit(record)
            pushed = self._git(
                (
                    "push", "--atomic",
                    f"--force-with-lease={branch_ref}:{expected}",
                    f"--force-with-lease={archive_ref}:",
                    "origin", f"{archive_commit}:{archive_ref}", f":{branch_ref}",
                ),
                check=False,
            )
            if pushed.returncode != 0:
                raise ClaimError("receipt retirement atomic archive/delete failed: " + pushed.stderr.strip())
        # Re-validate origin after the transaction/recovery before any local effect
        # record can imply success.
        if self._remote_ref_sha(archive_ref) != archive_commit or self._remote_ref_sha(branch_ref) is not None:
            raise ClaimError("receipt retirement remote verification failed after archive/delete")
        fetched = self._git(("fetch", "--no-tags", "origin", archive_ref), check=False)
        if fetched.returncode != 0:
            raise ClaimError("cannot fetch receipt retirement archive for final verification")
        self._verify_archive(archive_commit, record)
        execution = {
            "schema_version": 1, "kind": RETIREMENT_KIND, "status": "RETIRED",
            "retirement_id": retirement_id, "archive_commit": archive_commit,
            "archive_ref": archive_ref, "source_head": expected,
            "snapshot_digest": self._snapshot_digest(), "reconciliation_digest": self._reconciliation_digest(),
            "actor": actor, "completed_at": format_time(self.clock()),
        }
        atomic_write_json(self.retirement_execution_path, execution)
        append_jsonl(self.state_dir / RETIREMENT_AUDIT, {"event": "receipt_branch_retired", **execution})
        return execution

def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="autopilot")
    root.add_argument("--repo-root", default=".")
    commands = root.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser("doctor")
    doctor.add_argument("--skip-controller-tests", action="store_true")
    doctor.add_argument("--json", action="store_true", dest="json_output")

    status = commands.add_parser("status")
    status.add_argument("--json", action="store_true", dest="json_output")

    ready = commands.add_parser("ready")
    ready.add_argument("--json", action="store_true", dest="json_output")

    dispatch = commands.add_parser("dispatch")
    dispatch.add_argument("--actor", required=True)
    dispatch.add_argument("--node", action="append", default=[])
    dispatch.add_argument("--json", action="store_true", dest="json_output")

    claim = commands.add_parser("claim")
    claim.add_argument("node_id")
    claim.add_argument("--owner", required=True)
    claim.add_argument("--lease-minutes", type=int, default=90)
    claim.add_argument("--publish-remote", action="store_true")
    claim.add_argument("--remote", default="origin")

    heartbeat = commands.add_parser("heartbeat")
    heartbeat.add_argument("node_id")
    heartbeat.add_argument("--owner", required=True)
    heartbeat.add_argument("--lease-minutes", type=int, default=90)

    release = commands.add_parser("release")
    release.add_argument("node_id")
    release.add_argument("--owner", required=True)
    release.add_argument("--reason", required=True)

    reap = commands.add_parser("reap-stale-remote-claim")
    reap.add_argument("node_id")
    reap.add_argument("--owner", required=True)
    reap.add_argument("--reason", required=True)

    complete = commands.add_parser("complete")
    complete.add_argument("node_id")
    complete.add_argument("--owner", required=True)
    complete.add_argument("--receipt", required=True)

    fail = commands.add_parser("fail")
    fail.add_argument("node_id")
    fail.add_argument("--owner", required=True)
    fail.add_argument("--error", required=True)
    fail.add_argument("--kind", choices=("failure", "escalation"), default="failure")
    fail.add_argument("--evidence-ref", action="append", default=[])
    fail.add_argument("--blocker-cause")
    fail.add_argument("--blocker-fix")
    fail.add_argument("--retry-when")
    fail.add_argument("--attempted-command", action="append", default=[])
    fail.add_argument("--blocker-category", default="execution")

    blocker_resolve = commands.add_parser("blocker-resolve")
    blocker_resolve.add_argument("node_id")
    blocker_resolve.add_argument("blocker_id")
    blocker_resolve.add_argument("--actor", required=True)
    blocker_resolve.add_argument("--fix", required=True)
    blocker_resolve.add_argument("--retry-command", action="append", required=True)
    blocker_resolve.add_argument("--evidence-ref", action="append", default=[])

    reconcile = commands.add_parser("reconcile")
    reconcile.add_argument("--target-sha", required=True)
    reconcile.add_argument("--actor", required=True)
    reconcile.add_argument("--reason", required=True)
    reconcile.add_argument("--changed-path", action="append", default=[])

    snapshot = commands.add_parser("install-github-snapshot")
    snapshot.add_argument("file")

    render = commands.add_parser("render-prompt")
    render.add_argument("node_id")

    verify = commands.add_parser("verify-receipt")
    verify.add_argument("node_id")
    verify.add_argument("receipt")
    verify.add_argument("--require-integrated", action="store_true")

    wave_start = commands.add_parser("subtask-wave-start")
    wave_start.add_argument("wave_id")
    wave_start.add_argument("--node", action="append", required=True)
    wave_start.add_argument("--target-sha")

    wave_poll = commands.add_parser("subtask-wave-poll")
    wave_poll.add_argument("wave_id")
    wave_poll.add_argument("--status", action="append", required=True)

    validation_acquire = commands.add_parser("validation-lease-acquire")
    validation_acquire.add_argument("node_id")
    validation_acquire.add_argument("--owner", required=True)
    validation_acquire.add_argument("--lease-minutes", type=int, default=10)

    validation_release = commands.add_parser("validation-lease-release")
    validation_release.add_argument("node_id")
    validation_release.add_argument("--owner", required=True)

    retirement = commands.add_parser("retire-receipt-branch")
    retirement.add_argument("retirement_id")
    retirement.add_argument("--actor", required=True)

    builder_retirement = commands.add_parser("retire-builder-330-branch")
    builder_retirement.add_argument("--actor", required=True)

    orchestrate = commands.add_parser("orchestrate")
    orchestrate.add_argument("--request", default="")
    orchestrate.add_argument("--actor", default="autopilot:orchestrator")
    orchestrate.add_argument(
        "--apply",
        action="store_true",
        help="Publish a safe release when inferred intent and live state allow it",
    )
    orchestrate.add_argument("--json", action="store_true", dest="json_output")

    wave = commands.add_parser("execute-wave")
    wave.add_argument("--request", default="execute the dag")
    wave.add_argument("--actor", default="autopilot:orchestrator")
    wave.add_argument(
        "--apply",
        action="store_true",
        help="Publish a safe release when inferred intent and live state allow it",
    )
    wave.add_argument(
        "--wait-seconds",
        type=int,
        default=60,
        help="Wall-clock bound on one evidence poll; the host is never waited on",
    )

    drive = commands.add_parser("run-round")
    drive.add_argument("--actor", default="autopilot:round-driver")
    drive.add_argument("--max-sessions", type=int, default=8)
    drive.add_argument(
        "--no-push",
        action="store_true",
        help="Integrate locally without advancing the remote singleton target",
    )
    drive.add_argument(
        "--skip-validation",
        action="store_true",
        help="Stop before the round's single leased repository-wide gate",
    )

    intent = commands.add_parser("infer-intent")
    intent.add_argument("request", nargs="?", default="")
    intent.add_argument("--json", action="store_true", dest="json_output")

    commands.add_parser("simple-prompt")

    prepare = commands.add_parser("prepare-launch")
    prepare.add_argument("instruction_id")
    prepare.add_argument("--host", required=True)
    prepare.add_argument("--attempt", type=int, default=1)
    prepare.add_argument("--retry-of")

    bind = commands.add_parser("bind-launch")
    bind.add_argument("instruction_id")
    bind.add_argument("--host", required=True)
    bind.add_argument("--task-id", required=True)
    bind.add_argument("--host-id")
    bind.add_argument("--cursor")
    bind.add_argument("--capability", required=True)

    commands.add_parser("launch-bindings")

    add_dag_standard_arguments(commands)

    return root


def print_status(document: dict[str, object]) -> None:
    print(f"TARGET SHA: {document['target_sha']}")
    print(f"PLAN: {document['plan_id']} ({document['plan_fingerprint']})")
    print(
        "STATE: RECONCILIATION_REQUIRED"
        if document["reconciliation_required"]
        else "STATE: RECONCILED"
    )
    counts = document["counts"]
    assert isinstance(counts, dict)
    for key in (
        "COMPLETE",
        "RUNNING",
        "CLAIMED",
        "READY",
        "INTEGRATION_READY",
        "PROMOTION_READY",
        "PR_OPEN",
        "CI_FAILED",
        "REPAIR_REQUIRED",
        "RECONCILIATION_REQUIRED",
        "BLOCKED",
        "ESCALATION_REQUIRED",
        "QUARANTINED",
        "BOOTSTRAP_REQUIRED",
    ):
        if key in counts:
            print(f"{key}: {counts[key]}")
    eligible = document.get("eligible", [])
    if isinstance(eligible, list):
        print("ELIGIBLE ONLY: " + (", ".join(str(item) for item in eligible) or "none"))
    release = document.get("dispatch_release")
    if isinstance(release, Mapping):
        verdicts = release.get("verdicts", {})
        if isinstance(verdicts, Mapping):
            for node_id in sorted(str(item) for item in verdicts):
                print(f"VERDICT {node_id}: {verdicts[node_id]}")
        print(f"DISPATCH DIRECTIVE: {release.get('directive', 'WAIT')}")
        print(str(release.get("action", "Do not open any worker sessions yet")))
    ready = document.get("ready", [])
    if isinstance(ready, list):
        print("START NOW: " + (", ".join(str(item) for item in ready) or "none"))


def print_dispatch(result: Mapping[str, object]) -> None:
    verdicts = result.get("verdicts", {})
    if isinstance(verdicts, Mapping):
        for node_id in sorted(str(item) for item in verdicts):
            print(f"{node_id}: {verdicts[node_id]}")
    print(str(result.get("directive", "WAIT")))
    print(str(result.get("action", "Do not open any worker sessions yet")))


def select_orchestration_status(
    plane: ControlPlane,
    request: str,
) -> tuple[Mapping[str, object], object]:
    """Select mutating recovery status only after a pure state-aware intent decision."""

    observed = plane.observe_status()
    decision = infer_intent(request, observed)
    status = observed if decision.intent == "CHECK" else plane.status()
    return status, decision


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command in {"dag-rounds", "dag-lint"}:
            # Plan-only analysis: deliberately does not construct a live control
            # plane so any repository's plan.json can be compiled and linted.
            return run_dag_standard_command(args)
        plane = ControlPlane(Path(args.repo_root))
        if args.command == "doctor":
            result = plane.doctor(
                run_controller_tests=not args.skip_controller_tests
            )
            if args.json_output:
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                print("PASS" if result["passed"] else "FAIL")
                for check in result["checks"]:
                    print(f"- {check['name']}: {'PASS' if check['passed'] else 'FAIL'}")
                    for detail in check["details"]:
                        print(f"  {detail}")
            return 0 if result["passed"] else 1
        if args.command == "status":
            result = plane.status()
            if args.json_output:
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                print_status(result)
            return 0
        if args.command == "ready":
            result = plane.status()
            ready = result.get("ready", [])
            ready_list = [str(item) for item in ready] if isinstance(ready, list) else []
            if args.json_output:
                print(
                    json.dumps(
                        {
                            "ready": ready_list,
                            "eligible": result.get("eligible", []),
                            "dispatch_release": result.get("dispatch_release", {}),
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
            elif ready_list:
                print("\n".join(ready_list))
            else:
                release = result.get("dispatch_release", {})
                action = release.get("action") if isinstance(release, Mapping) else None
                print(str(action or "Do not open any worker sessions yet"))
            return 0
        if args.command == "dispatch":
            result = plane.dispatch(actor=args.actor, requested_nodes=args.node)
            if args.json_output:
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                print_dispatch(result)
            return 0
        if args.command == "claim":
            print(
                json.dumps(
                    plane.claim(
                        args.node_id,
                        args.owner,
                        lease_minutes=args.lease_minutes,
                        publish_remote=args.publish_remote,
                        remote=args.remote,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "heartbeat":
            print(
                json.dumps(
                    plane.heartbeat(
                        args.node_id,
                        args.owner,
                        lease_minutes=args.lease_minutes,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "release":
            plane.release(args.node_id, args.owner, reason=args.reason)
            return 0
        if args.command == "reap-stale-remote-claim":
            print(
                json.dumps(
                    plane.reap_stale_remote_claim(
                        args.node_id, args.owner, reason=args.reason
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "complete":
            receipt = read_json(Path(args.receipt))
            if not isinstance(receipt, dict):
                raise ReceiptError("receipt file must contain an object")
            print(plane.complete(args.node_id, args.owner, receipt))
            return 0
        if args.command == "fail":
            print(
                json.dumps(
                    plane.fail(
                        args.node_id,
                        args.owner,
                        error=args.error,
                        kind=args.kind,
                        evidence_refs=args.evidence_ref,
                        blocker_cause=args.blocker_cause,
                        blocker_fix=args.blocker_fix,
                        retry_when=args.retry_when,
                        attempted_command=args.attempted_command,
                        blocker_category=args.blocker_category,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "blocker-resolve":
            print(
                json.dumps(
                    plane.resolve_blocker(
                        args.node_id,
                        args.blocker_id,
                        actor=args.actor,
                        fix=args.fix,
                        retry_command=args.retry_command,
                        evidence_refs=args.evidence_ref,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "reconcile":
            print(
                plane.reconcile(
                    args.target_sha,
                    actor=args.actor,
                    reason=args.reason,
                    changed_paths=args.changed_path,
                )
            )
            return 0
        if args.command == "install-github-snapshot":
            print(plane.install_github_snapshot(Path(args.file)))
            return 0
        if args.command == "render-prompt":
            # Prompt rendering is a pure observation; one snapshot cache keeps the
            # durable receipt reconstruction from replaying thousands of Git calls.
            with plane.snapshot_cache():
                print(plane.render_worker_prompt(args.node_id))
            return 0
        if args.command == "verify-receipt":
            value = read_json(Path(args.receipt))
            with plane.snapshot_cache():
                issues = plane.validate_receipt(
                    args.node_id,
                    value,
                    require_integrated=args.require_integrated,
                )
            if issues:
                print("\n".join(issues), file=sys.stderr)
                return 1
            print("VALID")
            return 0
        if args.command == "subtask-wave-start":
            print(json.dumps(plane.start_subtask_wave(args.wave_id, args.node, target_sha=args.target_sha), indent=2, sort_keys=True))
            return 0
        if args.command == "subtask-wave-poll":
            statuses: dict[str, str] = {}
            for item in args.status:
                if "=" not in item:
                    raise AutopilotError("subtask status must be NODE=STATE")
                node, state = item.split("=", 1)
                if not node or node in statuses:
                    raise AutopilotError("subtask status nodes must be non-empty and unique")
                statuses[node] = state
            print(json.dumps(plane.poll_subtask_wave(args.wave_id, statuses), indent=2, sort_keys=True))
            return 0
        if args.command == "validation-lease-acquire":
            result = plane.acquire_global_validation_lease(
                args.node_id,
                args.owner,
                lease_minutes=args.lease_minutes,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "validation-lease-release":
            plane.release_global_validation_lease(args.node_id, args.owner)
            return 0
        if args.command == "retire-receipt-branch":
            print(json.dumps(plane.retire_receipt_branch(args.retirement_id, actor=args.actor), indent=2, sort_keys=True))
            return 0
        if args.command == "retire-builder-330-branch":
            print(json.dumps(plane.retire_builder_branch(actor=args.actor), indent=2, sort_keys=True))
            return 0
        if args.command == "infer-intent":
            result = infer_intent(args.request, plane.observe_status()).to_dict()
            if args.json_output:
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                print(result["intent"])
            return 0
        if args.command == "simple-prompt":
            print(simple_prompt())
            return 0
        if args.command == "prepare-launch":
            print(
                json.dumps(
                    prepare_launch(
                        plane.repo_root,
                        args.instruction_id,
                        args.host,
                        attempt=args.attempt,
                        retry_of=args.retry_of,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "bind-launch":
            print(
                json.dumps(
                    bind_launch(
                        plane.repo_root,
                        args.instruction_id,
                        args.host,
                        args.task_id,
                        host_id=args.host_id,
                        cursor=args.cursor,
                        capability=args.capability,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "launch-bindings":
            print(json.dumps(binding_events(plane.repo_root), indent=2, sort_keys=True))
            return 0
        if args.command == "run-round":
            print(
                json.dumps(
                    drive_round(
                        plane,
                        actor=args.actor,
                        max_sessions=args.max_sessions,
                        push=not args.no_push,
                        validate=not args.skip_validation,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "execute-wave":
            status, decision = select_orchestration_status(plane, args.request)
            if args.apply and should_publish_release(decision, status):
                plane.dispatch(actor=args.actor)
                status = plane.status()
            contract = build_orchestration_contract(plane, args.request, status=status)
            print(f"INTENT: {contract['intent']['intent']}")
            print(f"CONTRACT: {contract['contract_id']}")
            if not contract["tasks"]:
                print(f"NO RELEASED WAVE: {contract['dispatch_release']['action']}")
                for issue in contract["dispatch_release"]["issues"]:
                    print(f"  - {issue}")
                return 0
            host = AttendedCodexHost(plane, wait_seconds=args.wait_seconds)
            host.bind_tasks(contract["tasks"])
            result = execute_contract(
                plane.repo_root, contract, host, EvidenceResolver()
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            for card in host.pending_cards():
                print(f"OPEN SESSION: {card['title']} -> {card['card']}")
            return 0
        if args.command == "orchestrate":
            status, decision = select_orchestration_status(plane, args.request)
            if args.apply and should_publish_release(decision, status):
                plane.dispatch(actor=args.actor)
                status = plane.status()
            result = build_orchestration_contract(
                plane,
                args.request,
                status=status,
            )
            if args.json_output:
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                print(f"INTENT: {result['intent']['intent']}")
                print(f"CONTRACT: {result['contract_id']}")
                print(f"CLOSURE TARGET: {result['closure_target'] or 'none'}")
                print(f"QUIESCENT: {'yes' if result['quiescent'] else 'no'}")
                for task in result["tasks"]:
                    print(
                        f"{task['action']}: {task['title']} "
                        f"[{task['transport']}]"
                    )
            return 0
        raise AssertionError(args.command)
    except (
        AutopilotError,
        ClaimError,
        ConfigurationError,
        OrchestrationError,
        ReceiptError,
    ) as error:
        print(f"autopilot: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
