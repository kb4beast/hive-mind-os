#!/usr/bin/env python3
"""Command-line interface for the repository-resident implementation control plane."""

from __future__ import annotations

import argparse
import errno
import importlib.util
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, Sequence

import execution_supervisor as execution_supervisor_runtime
from attended_host import AttendedCodexHost, EvidenceResolver
from controller import (
    AUTHORITY_ID,
    FULL_SHA,
    LEGACY_SEMANTIC_RECONCILIATION_MANIFEST,
    RUNTIME_BOOTSTRAP_LOCK,
    RUNTIME_BOOTSTRAP_MANIFEST,
    RUNTIME_READY_MANIFEST,
    _compact_authority_path_id,
    _inspect_noncanonical_authority,
    _is_link_like,
    _legacy_semantic_inventory,
    _legacy_semantic_material,
    _linked_worktree_roots,
    _migration_material,
    _plan_legacy_semantic_paths,
    _plan_migration_paths,
    _reject_link_components,
    _validate_legacy_semantic_manifest,
    _validate_migration_manifest,
    active_global_host_reservations,
    bind_host_repository_runtime,
    bootstrap_runtime_authority_migration,
    build_host_provider_attestation,
    exclusive_write_json_or_identical,
    execution_host_effect_obligations,
    format_time,
    grant_host_scheduler_capacity,
    host_capacity_path,
    host_capacity_record_in_current_lineage,
    host_scheduler_observation,
    initialize_execution_namespace,
    initialize_host_runtime,
    initialize_repository_runtime_authority,
    install_execution_adapter_identity,
    parse_strict_canonical_json_bytes,
    parse_time,
    publication_observation_evidence_ref,
    publish_host_capacity,
    read_current_host_runtime_identity,
    read_host_capacity_predecessor_for_writer_rotation,
    read_strict_canonical_json,
    reconcile_legacy_worktree_execution_authority,
    reconcile_pending_host_capacity_renewal,
    record_host_scheduler_demand,
    recover_host_authority_jsonl_torn_tail,
    release_global_host_session,
    renew_host_capacity_authority,
    require_execution_authority_dir,
    require_execution_namespace,
    reserve_global_host_session,
    resolve_host_runtime_dir,
    resolve_repository_state_dir,
    runtime_file_lock,
    runtime_file_lock_is_held,
    runtime_kernel_identity,
    runtime_repository_identity,
    stage_repository_runtime_authority,
    strict_jsonl_records,
    upgrade_execution_namespace_kernel,
    upgrade_host_runtime_kernel,
    validate_repository_runtime_ready_chain,
)
from dag_standard import (
    add_dag_standard_arguments,
    run_dag_standard_command,
)
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
from execution_supervisor import (
    FixedPointEvidence,
    FixedPointVerificationRequest,
    HostCapability,
    ObserverContext,
    ObserverResult,
    StepContext,
    StepDisposition,
    StepResult,
    SupervisorError,
    WaitCondition,
    WaitObservationVerificationRequest,
    reconcile_unknown_attempt,
    recover_torn_tail,
    run_to_fixed_point,
)
from healing import heal_round
from host_execution import execute_contract, reconcile_global_expired_host_reservations
from learning import commit_lessons
from learning import summarize as summarize_lessons
from orchestration import (
    OrchestrationError,
    active_host_reservations,
    active_write_launch_reservations,
    assert_launch_authority,
    bind_launch,
    binding_events,
    build_orchestration_contract,
    derive_launch_identity,
    fence_launch,
    infer_intent,
    load_policy,
    prepare_launch,
    should_publish_release,
    simple_prompt,
)
from release_barrier import (
    CURRENT_RELEASE,
    RELEASE_HISTORY,
    RELEASE_KIND,
)
from release_barrier import (
    ControlPlane as ReleaseBarrierControlPlane,
)
from round_driver import (
    drive_round,
    fixed_validation_environment_policy,
    select_round,
)
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
DISPATCH_GENERATION = "dispatcher-admission.json"
DISPATCH_GENERATION_KIND = "hive-mind-shared-dispatch-admission-v1"
DISPATCH_ADMISSION_INTENT_KIND = "hive-mind-dispatcher-admission-intent-v1"
DISPATCH_PRE_LAUNCH_ABORT_KIND = "hive-mind-dispatcher-pre-launch-abort-v1"
SNAPSHOT_OBSERVATION = "github-snapshot-observation.json"
SNAPSHOT_OBSERVATION_KIND = "hive-mind-github-snapshot-observation-v2"
SNAPSHOT_OBSERVATION_TTL_MINUTES = 30
GITHUB_NODE_PR_LIMIT = 1000
SNAPSHOT_CANDIDATE_KIND = "hive-mind-github-snapshot-candidate-v1"
SNAPSHOT_SOURCE_REF_OBSERVATION_KIND = (
    "hive-mind-github-snapshot-source-ref-observation-v1"
)
SNAPSHOT_SOURCE_REF_OBSERVATION_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "execution_namespace",
        "execution_id",
        "observation_id",
        "repository",
        "repository_transport_digest",
        "target_ref",
        "target_sha",
        "branch_refs",
        "ls_remote_argv",
        "raw_stdout",
        "raw_stdout_digest",
        "observed_at",
        "record_id",
    }
)
SNAPSHOT_SOURCE_REF_MAX_BYTES = 8 * 1024 * 1024
SNAPSHOT_OBSERVATION_ARCHIVE_KIND = (
    "hive-mind-expired-github-snapshot-observation-v1"
)
PUBLICATION_TRANSACTION_KIND = "hive-mind-publication-transaction-v1"
PUBLICATION_RESERVATION_KIND = "hive-mind-publication-reservation-v1"
PUBLICATION_EVENT_KIND = "hive-mind-publication-transition-v2"
PUBLICATION_VALIDATION_CHALLENGE_KIND = (
    "hive-mind-publication-validation-challenge-v1"
)
PUBLICATION_VALIDATION_COMPLETION_KIND = (
    "hive-mind-publication-validation-broker-completion-v1"
)
SUPERSEDED_PUBLICATION_TARGET_OBSERVATION_KIND = (
    "hive-mind-superseded-publication-target-observation-v1"
)
SUPERSEDED_PUBLICATION_TARGET_OBSERVATION_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "repository",
        "repository_transport_digest",
        "target_ref",
        "expected_target_sha",
        "pinned_sha",
        "observed_target_sha",
        "observation_ref",
        "observation_ref_sha",
        "transaction_ref",
        "observed_transaction_sha",
        "receipt_heads",
        "execution_namespace",
        "execution_id",
        "release_id",
        "publication_transaction_id",
        "observed_at",
        "record_id",
    }
)
PUBLICATION_BROKER_GATE_MARKER = "HIVE_MIND_BROKER_GATE_RESULT="
GOVERNED_PUBLICATION_KERNEL_PATHS = (
    ".autopilot/bin",
    ".autopilot/tests",
)
PUBLICATION_BROKER_GATE_HARNESS = r'''import hashlib
import json
import pathlib
import sys
import unittest

root = pathlib.Path(sys.argv[1]).resolve(strict=True)
sys.path.insert(0, str(root))
source = root / "src"
if source.is_dir():
    sys.path.insert(0, str(source))
suite = unittest.defaultTestLoader.discover(
    start_dir=str(root / "tests"),
    pattern="test*.py",
    top_level_dir=str(root / "tests"),
)

def flatten(value):
    for item in value:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item

test_ids = sorted(test.id() for test in flatten(suite))
manifest_bytes = json.dumps(
    test_ids, ensure_ascii=False, sort_keys=True, separators=(",", ":")
).encode("utf-8")
source_entries = []
for candidate in sorted((root / "tests").rglob("*")):
    if candidate.is_symlink():
        raise SystemExit("test source manifest contains a symbolic link")
    if not candidate.is_file():
        continue
    content = candidate.read_bytes()
    header = b"blob " + str(len(content)).encode("ascii") + b"\0"
    source_entries.append(
        {
            "path": candidate.relative_to(root).as_posix(),
            "blob": hashlib.sha1(header + content, usedforsecurity=False).hexdigest(),
        }
    )
source_manifest_bytes = json.dumps(
    source_entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")
).encode("utf-8")
source_manifest_digest = (
    "sha256:" + hashlib.sha256(source_manifest_bytes).hexdigest()
)
if not test_ids or len(test_ids) != len(set(test_ids)):
    payload = {
        "discovered": len(test_ids),
        "executed": 0,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
        "expected_failures": 0,
        "unexpected_successes": 0,
        "manifest_digest": "sha256:" + hashlib.sha256(manifest_bytes).hexdigest(),
        "source_manifest_digest": source_manifest_digest,
        "successful": False,
    }
    print("HIVE_MIND_BROKER_GATE_RESULT=" + json.dumps(payload, sort_keys=True))
    raise SystemExit(2)
result = unittest.TextTestRunner(verbosity=2).run(suite)
payload = {
    "discovered": len(test_ids),
    "executed": int(result.testsRun),
    "failures": len(result.failures),
    "errors": len(result.errors),
    "skipped": len(result.skipped),
    "expected_failures": len(result.expectedFailures),
    "unexpected_successes": len(result.unexpectedSuccesses),
    "manifest_digest": "sha256:" + hashlib.sha256(manifest_bytes).hexdigest(),
    "source_manifest_digest": source_manifest_digest,
    "successful": bool(result.wasSuccessful() and result.testsRun == len(test_ids)),
}
print("HIVE_MIND_BROKER_GATE_RESULT=" + json.dumps(payload, sort_keys=True))
raise SystemExit(0 if payload["successful"] else 1)
'''
PUBLICATION_NONTERMINAL_STATUSES = frozenset(
    {"PREPARED", "PINNED", "VALIDATED", "PUBLISHING"}
)
PUBLICATION_INDETERMINATE_STATUSES = frozenset({"PUBLISH_UNKNOWN"})
PUBLICATION_TERMINAL_STATUSES = frozenset(
    {
        "PUBLISHED",
        "SUPERSEDED_INTEGRATED",
        "REJECTED",
        "VALIDATION_FAILED",
        "RECOVERY_REQUIRED",
        "NO_PUSH",
        "INTEGRATION_CONFLICT",
        "EXPIRED_FENCED",
    }
)
PUBLICATION_TRANSACTION_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "status",
        "transaction_key",
        "attempt_epoch",
        "nonce",
        "transaction_id",
        "execution_namespace",
        "execution_id",
        "release_id",
        "round_id",
        "repository",
        "target_branch",
        "expected_target_sha",
        "authority_digest",
        "authority_baseline_digest",
        "receipt_heads",
        "receipt_heads_digest",
        "transaction_ref",
        "coordinator_id",
        "transaction_lease_nonce",
        "transaction_lease_id",
        "lease_expires_at",
        "publishing_lease_nonce",
        "publishing_lease_id",
        "publishing_lease_expires_at",
        "pinned_sha",
        "validation_evidence",
        "outcome",
        "detail",
        "actor",
        "reserved_at",
        "updated_at",
        "completed_at",
        "record_id",
    }
)
PUBLICATION_GATE_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "argv",
        "interpreter_path",
        "interpreter_digest_before",
        "interpreter_digest_after",
        "git_executable_path",
        "git_executable_digest_before",
        "git_executable_digest_after",
        "round_driver_path",
        "round_driver_digest_before",
        "round_driver_digest_after",
        "worktree_tree",
        "worktree_head_after",
        "transaction_ref_after",
        "worktree_status_porcelain",
        "environment_policy_digest",
        "started_at",
        "completed_at",
        "exit_code",
        "output_digest",
        "summary",
        "test_manifest_digest",
        "test_source_manifest_digest",
        "test_counts",
        "sandbox_broker_identity_id",
        "stdlib_bundle_digest",
    }
)
PUBLICATION_VALIDATION_EVIDENCE_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "execution_namespace",
        "execution_id",
        "transaction_id",
        "transaction_record_id",
        "release_id",
        "dispatcher_admission_epoch",
        "authority_digest",
        "authority_baseline_digest",
        "receipt_heads_digest",
        "pinned_sha",
        "pinned_tree",
        "protected_test_manifest_digest",
        "candidate_test_manifest_digest",
        "test_diff_policy",
        "governed_kernel_manifest_digest",
        "kernel_diff_policy",
        "host_id",
        "capacity_generation",
        "lease",
        "released_lease",
        "cleanup",
        "gate",
        "broker_completion_id",
        "evidence_id",
    }
)
PUBLICATION_VALIDATION_CHALLENGE_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "execution_namespace",
        "execution_id",
        "transaction_id",
        "transaction_record_id",
        "release_id",
        "dispatcher_admission_epoch",
        "target_generation",
        "target_watermark_record_id",
        "authority_baseline_digest",
        "receipt_heads_digest",
        "pinned_sha",
        "pinned_tree",
        "protected_test_manifest_digest",
        "candidate_test_manifest_digest",
        "test_diff_policy",
        "governed_kernel_manifest_digest",
        "kernel_diff_policy",
        "host_id",
        "capacity_generation",
        "kernel_bundle_digest",
        "interpreter_policy_digest",
        "stdlib_bundle_digest",
        "gate_identity_id",
        "sandbox_broker_identity_id",
        "issued_by",
        "issued_at",
        "expires_at",
        "challenge_id",
    }
)
PUBLICATION_VALIDATION_COMPLETION_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "execution_namespace",
        "execution_id",
        "challenge_id",
        "challenge_record_id",
        "transaction_id",
        "transaction_record_id",
        "pinned_sha",
        "kernel_bundle_digest",
        "interpreter_policy_digest",
        "stdlib_bundle_digest",
        "gate_identity_id",
        "sandbox_broker_identity_id",
        "lease",
        "cleanup",
        "gate",
        "completed_by",
        "completed_at",
        "completion_id",
    }
)
KEYED_VALIDATION_LEASE_FIELDS = frozenset(
    {
        "schema_version",
        "node_id",
        "owner",
        "target_sha",
        "acquired_at",
        "expires_at",
        "renewal_count",
        "status",
        "execution_id",
        "validation_resource_key",
        "authority_nonce",
        "claim_id",
        "claim_authority_class",
        "launch_instruction_id",
        "resource_key",
        "authority_epoch",
        "release_id",
        "transaction_sha",
        "host_reservation_id",
        "capacity_host_id",
        "capacity_generation",
        "lease_id",
        "global_host_reservation_id",
        "global_capacity_generation",
    }
)
KEYED_VALIDATION_CLEANUP_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "execution_id",
        "release_id",
        "transaction_sha",
        "lease_id",
        "lease_released",
        "host_reservation",
        "errors",
        "recorded_at",
        "record_id",
    }
)
PUBLICATION_RESOURCE_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "status",
        "transaction_id",
        "execution_id",
        "release_id",
        "repository",
        "target_branch",
        "expected_target_sha",
        "expires_at",
        "outcome",
        "transaction",
        "record_id",
    }
)
PUBLICATION_EVENT_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "transaction_id",
        "transaction_record_id",
        "status",
        "detail",
        "recorded_at",
        "previous_event_id",
        "transaction",
        "event_id",
    }
)
TARGET_CONTROL_FIELDS = frozenset(
    {
        "bootstrap_completion",
        "default_claim_lease_minutes",
        "max_consultation_rounds",
        "plan_fingerprint",
        "plan_id",
        "prohibitions",
        "schema_version",
        "orchestration_policy_file",
        "source_of_truth",
        "target",
        "verify_git_objects",
        "workflow_policy_file",
    }
)
TARGET_CONTROL_TARGET_FIELDS = frozenset(
    {
        "baseline_observed_at",
        "baseline_rule",
        "baseline_sha",
        "baseline_tree",
        "branch",
        "repository",
        "execution_mode",
        "final_integration_branch",
        "protected_until_final_integration",
        "release_branch_base",
    }
)
TARGET_PLAN_FIELDS = frozenset(
    {
        "baseline",
        "created_at",
        "nodes",
        "plan_fingerprint",
        "plan_id",
        "schema_version",
        "state_machine",
        "subject",
        "title",
    }
)
MAX_TARGET_CONTROL_BYTES = 1024 * 1024
MAX_TARGET_PLAN_BYTES = 16 * 1024 * 1024

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


class HostCapacityWaiting(AutopilotError):
    """Authenticated scheduler demand exists but owns no current slot grant."""


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

    def _git(
        self,
        args: Sequence[str],
        *,
        check: bool = False,
        environment: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run every authority Git read with replacement/graft semantics disabled.

        Replacement refs and legacy grafts alter commit parents and trees only in
        the reading clone; the object pushed to another clone keeps its raw graph.
        A scheduler must therefore never validate the substituted graph.  The
        process flag disables replacements atomically with each Git operation and
        the explicit graft check rejects the legacy on-disk override channel.
        """

        child_environment = dict(environment or {})
        supplied_no_replace = child_environment.get("GIT_NO_REPLACE_OBJECTS")
        if supplied_no_replace not in {None, "1"}:
            raise AutopilotError("Git replacement-object policy cannot be overridden")
        child_environment["GIT_NO_REPLACE_OBJECTS"] = "1"

        executable = shutil.which("git")
        if executable is None:
            raise AutopilotError("the authority Git executable is unavailable")
        executable_path = Path(executable).resolve(strict=True)
        executable_digest = "sha256:" + sha256(executable_path.read_bytes()).hexdigest()
        installed_git = getattr(self, "_hive_mind_git_executable", None)
        executable_identity = (str(executable_path), executable_digest)
        if installed_git is None:
            self._hive_mind_git_executable = executable_identity
        elif installed_git != executable_identity:
            raise AutopilotError("the authority Git executable changed during the run")
        inherited_path = os.environ.get("PATH", "")
        child_environment["PATH"] = os.pathsep.join(
            item
            for item in (str(executable_path.parent), inherited_path)
            if item
        )

        hooks_path = self.arbiter_dir / "git-hooks-disabled.authority"
        hooks_path.parent.mkdir(parents=True, exist_ok=True)
        if self._is_link_like(hooks_path.parent) or self._is_link_like(hooks_path):
            raise AutopilotError("Git hook-disable authority traverses a link")
        hook_payload = b"hive-mind-git-hooks-disabled-v1\n"
        if not hooks_path.exists():
            descriptor = os.open(
                hooks_path,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_BINARY", 0),
                0o600,
            )
            try:
                os.write(descriptor, hook_payload)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            self._fsync_directory(hooks_path.parent)
        try:
            installed_hook_payload = hooks_path.read_bytes()
        except OSError as error:
            raise AutopilotError("Git hook-disable authority is unreadable") from error
        if not hooks_path.is_file() or installed_hook_payload != hook_payload:
            raise AutopilotError("Git hook-disable authority is not exact")
        hardened_prefix = (
            "--no-replace-objects",
            "-c",
            f"core.hooksPath={hooks_path}",
        )

        common_dir = getattr(self, "_hive_mind_git_common_dir", None)
        if common_dir is None:
            located = super()._git(
                (
                    *hardened_prefix,
                    "rev-parse",
                    "--path-format=absolute",
                    "--git-common-dir",
                ),
                check=False,
                environment=child_environment,
            )
            candidate = located.stdout.strip()
            if (
                located.returncode != 0
                or not candidate
                or not Path(candidate).is_absolute()
            ):
                raise AutopilotError(
                    "canonical Git common directory cannot be authenticated"
                )
            common_dir = Path(candidate).resolve(strict=False)
            self._hive_mind_git_common_dir = common_dir
        grafts = Path(common_dir) / "info" / "grafts"
        if grafts.exists() or self._is_link_like(grafts):
            raise AutopilotError(
                "legacy Git graft authority is forbidden for scheduler operations"
            )
        replacement_refs = super()._git(
            (*hardened_prefix, "for-each-ref", "--format=%(refname)", "refs/replace"),
            check=False,
            environment=child_environment,
        )
        if replacement_refs.returncode != 0 or replacement_refs.stdout.strip():
            raise AutopilotError(
                "Git replacement refs are forbidden for scheduler operations"
            )
        return super()._git(
            (*hardened_prefix, *tuple(args)),
            check=check,
            environment=child_environment,
        )

    @property
    def current_release_path(self) -> Path:
        """Return the release owned by this immutable execution namespace."""

        return self.execution_dir / CURRENT_RELEASE

    @property
    def release_history_path(self) -> Path:
        return self.execution_dir / RELEASE_HISTORY

    @property
    def dispatcher_generation_path(self) -> Path:
        return self.execution_dir / DISPATCH_GENERATION

    @property
    def snapshot_observation_path(self) -> Path:
        return self.execution_dir / SNAPSHOT_OBSERVATION

    @property
    def snapshot_observation_archive_dir(self) -> Path:
        legacy = self.execution_dir / "github-snapshot-observation-archive"
        return legacy if legacy.exists() else self.execution_dir / "oa"

    @property
    def snapshot_candidate_dir(self) -> Path:
        legacy = self.execution_dir / "github-snapshot-candidates"
        return legacy if legacy.exists() else self.execution_dir / "sc"

    @property
    def github_snapshot_path(self) -> Path:
        return self.execution_dir / "github-state.json"

    @property
    def execution_target_ref(self) -> str:
        if AUTHORITY_ID.fullmatch(self.execution_id) is None:
            raise AutopilotError("execution target reference identity is invalid")
        return (
            "refs/hive-mind-autopilot/executions/"
            f"{self.execution_id.removeprefix('sha256:')}/target"
        )

    def _execution_target_sha(self) -> str | None:
        execution_id = getattr(self, "execution_id", None)
        if not isinstance(execution_id, str) or AUTHORITY_ID.fullmatch(execution_id) is None:
            return None
        completed = self._git(
            ("rev-parse", "--verify", f"{self.execution_target_ref}^{{commit}}"),
            check=False,
        )
        value = completed.stdout.strip()
        if completed.returncode != 0:
            return None
        if FULL_SHA.fullmatch(value) is None:
            raise AutopilotError("execution target reference is malformed")
        return value

    def current_target_sha(self) -> str:
        """Return this execution's pinned target, falling back before first install."""

        pinned = self._execution_target_sha()
        return pinned if pinned is not None else super().current_target_sha()

    @property
    def remote_transport_identity_path(self) -> Path:
        return self.arbiter_dir / "canonical-remote-transport.json"

    @property
    def publication_journal_path(self) -> Path:
        return self.execution_dir / "publication-transactions.jsonl"

    def _active_execution_write_reservations(self) -> tuple[Mapping[str, Any], ...]:
        try:
            return tuple(
                active_write_launch_reservations(
                    self.repo_root,
                    execution_dir=self.execution_dir,
                    execution_id=self.execution_id,
                    execution_namespace=self.execution_namespace,
                )
            )
        except OrchestrationError as error:
            raise AutopilotError(str(error)) from error

    def _active_execution_host_reservations(self) -> tuple[Mapping[str, Any], ...]:
        try:
            return tuple(
                active_host_reservations(
                    self.repo_root,
                    execution_dir=self.execution_dir,
                    execution_id=self.execution_id,
                    execution_namespace=self.execution_namespace,
                )
            )
        except OrchestrationError as error:
            raise AutopilotError(str(error)) from error

    def _assert_no_execution_launch_reservations(self, operation: str) -> None:
        reservations = self._active_execution_host_reservations()
        if reservations:
            identities = sorted(
                str(
                    item.get("launch_instruction_id")
                    or item.get("sidecar_id")
                    or item.get("node_id")
                )
                for item in reservations
            )
            raise AutopilotError(
                f"{operation} is fenced by active launch/sidecar reservations: "
                + ", ".join(identities)
            )

    def _assert_no_global_host_reservations(self, operation: str) -> None:
        host_lock_path = self.host_runtime_dir / "locks" / "host-authority.lock"
        if not runtime_file_lock_is_held(host_lock_path):
            raise AutopilotError(
                f"{operation} requires outer machine host authority"
            )
        reservations = [
            item
            for item in active_global_host_reservations(self.host_runtime_dir)
            if item.get("execution_id") == self.execution_id
        ]
        if reservations:
            raise AutopilotError(
                f"{operation} is fenced by active machine host reservations: "
                + ", ".join(
                    sorted(str(item.get("reservation_id")) for item in reservations)
                )
            )

    def _assert_no_publication_transaction(self, operation: str) -> None:
        path = self._publication_resource_path()
        if not path.is_file():
            return
        resource = self._strict_json_file(
            path, label="publication target reservation"
        )
        _, transaction = self._validated_publication_resource(
            resource,
            label="publication target reservation",
            allow_foreign=True,
        )
        if transaction.get("status") in {
            "PREPARED",
            "PINNED",
            "VALIDATED",
            "PUBLISHING",
            "PUBLISH_UNKNOWN",
        }:
            raise AutopilotError(
                f"{operation} is fenced by publication transaction "
                f"{transaction.get('transaction_id')}"
            )

    def _assert_publication_not_indeterminate_unlocked(self) -> None:
        """Fence every admission surface for the full publication transaction.

        The base controller historically fenced only ``PUBLISH_UNKNOWN``.  A
        PREPARED transaction already seals the exact zero-activity authority
        baseline, so admitting a claim or validation lease between its final
        observation and PUBLISHING would invalidate the commit being published.
        Dynamic controller claim/validation guards call this override while
        holding their canonical authority locks.
        """

        super()._assert_publication_not_indeterminate_unlocked()
        current = self._current_publication_resource()
        if current is None:
            return
        _, transaction = current
        if transaction.get("status") in {
            "PREPARED",
            "PINNED",
            "VALIDATED",
            "PUBLISHING",
            "PUBLISH_UNKNOWN",
        }:
            validation_state = getattr(
                self, "_publication_keyed_validation_state", None
            )
            validation = (
                getattr(validation_state, "authority", None)
                if validation_state is not None
                else None
            )
            if (
                transaction.get("status") == "PINNED"
                and isinstance(validation, Mapping)
                and validation.get("release_id")
                == transaction.get("release_id")
                and validation.get("transaction_id")
                == transaction.get("transaction_id")
                and validation.get("transaction_sha")
                == self._local_ref_sha(str(transaction["transaction_ref"]))
            ):
                return
            raise AutopilotError(
                "execution admission is fenced by active publication transaction "
                f"{transaction.get('transaction_id')}"
            )

    @contextmanager
    def _publication_keyed_validation_guard(
        self, *, release_id: str, transaction_sha: str
    ):
        current = self._current_publication_resource()
        if current is None:
            raise AutopilotError(
                "keyed validation requires a PINNED publication transaction"
            )
        _, transaction = current
        if (
            transaction.get("status") != "PINNED"
            or transaction.get("release_id") != release_id
            or FULL_SHA.fullmatch(transaction_sha) is None
        ):
            raise AutopilotError(
                "keyed validation differs from PINNED publication authority"
            )
        state = getattr(self, "_publication_keyed_validation_state", None)
        if state is None:
            state = threading.local()
            self._publication_keyed_validation_state = state
        prior = getattr(state, "authority", None)
        state.authority = {
            "transaction_id": transaction["transaction_id"],
            "release_id": release_id,
            "transaction_sha": transaction_sha,
        }
        try:
            yield
        finally:
            state.authority = prior

    def acquire_keyed_validation_lease_internal(
        self,
        node_id: str,
        owner: str,
        *,
        host_id: str,
        release_id: str,
        transaction_sha: str,
        lease_minutes: int = 10,
    ) -> Mapping[str, Any]:
        with self._publication_keyed_validation_guard(
            release_id=release_id, transaction_sha=transaction_sha
        ):
            return super().acquire_keyed_validation_lease_internal(
                node_id,
                owner,
                host_id=host_id,
                release_id=release_id,
                transaction_sha=transaction_sha,
                lease_minutes=lease_minutes,
            )

    def renew_keyed_validation_lease_internal(
        self,
        node_id: str,
        owner: str,
        *,
        lease_id: str,
        host_id: str,
        release_id: str,
        transaction_sha: str,
        lease_minutes: int = 10,
    ) -> Mapping[str, Any]:
        with self._publication_keyed_validation_guard(
            release_id=release_id, transaction_sha=transaction_sha
        ):
            return super().renew_keyed_validation_lease_internal(
                node_id,
                owner,
                lease_id=lease_id,
                host_id=host_id,
                release_id=release_id,
                transaction_sha=transaction_sha,
                lease_minutes=lease_minutes,
            )

    def release_keyed_validation_lease_internal(
        self,
        node_id: str,
        owner: str,
        *,
        lease_id: str,
        host_id: str,
        release_id: str,
        transaction_sha: str,
    ) -> Mapping[str, Any]:
        with self._publication_keyed_validation_guard(
            release_id=release_id, transaction_sha=transaction_sha
        ):
            return super().release_keyed_validation_lease_internal(
                node_id,
                owner,
                lease_id=lease_id,
                host_id=host_id,
                release_id=release_id,
                transaction_sha=transaction_sha,
            )

    @staticmethod
    def _is_link_like(path: Path) -> bool:
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            return False
        attributes = getattr(metadata, "st_file_attributes", 0)
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse)

    def _secure_execution_path(self, relative: str | Path) -> Path:
        """Resolve a private authority path without traversing links/junctions."""

        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise AutopilotError("execution authority path escapes its namespace")
        root = self.execution_dir
        current = root
        if self._is_link_like(root):
            raise AutopilotError("execution namespace is a link or junction")
        for component in candidate.parts:
            current = current / component
            if current.exists() and self._is_link_like(current):
                raise AutopilotError(
                    f"execution authority path traverses a link or junction: {current}"
                )
        try:
            current.resolve(strict=False).relative_to(root.resolve(strict=False))
        except ValueError as error:
            raise AutopilotError("execution authority path escapes its namespace") from error
        return current

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        """Flush a directory entry after an authority link/replace/unlink."""

        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        try:
            descriptor = os.open(directory, flags)
        except OSError as error:
            # CPython on Windows cannot open directory handles via os.open. The
            # underlying atomic replace is still write-through at file close; other
            # platforms must support and complete the directory durability barrier.
            if os.name == "nt" and error.errno in {
                errno.EACCES,
                errno.EINVAL,
                errno.EPERM,
            }:
                return
            raise AutopilotError(
                f"cannot open authority directory for durability: {directory}: {error}"
            ) from error
        try:
            os.fsync(descriptor)
        except OSError as error:
            if os.name == "nt" and error.errno in {errno.EINVAL, errno.ENOTSUP}:
                return
            raise AutopilotError(
                f"cannot flush authority directory: {directory}: {error}"
            ) from error
        finally:
            os.close(descriptor)

    def _atomic_write_authority_json(
        self, path: Path, value: Mapping[str, Any]
    ) -> None:
        root: Path | None = None
        for candidate in (self.execution_dir, self.arbiter_dir):
            try:
                path.relative_to(candidate)
            except ValueError:
                continue
            root = candidate
            break
        if root is None:
            raise AutopilotError("atomic authority path escapes controller roots")
        self._ensure_authority_directory(root, path.parent)
        if path.exists() and self._is_link_like(path):
            raise AutopilotError("atomic authority path is a link or junction")
        atomic_write_json(path, value)
        self._fsync_directory(path.parent)

    def _ensure_authority_directory(self, root: Path, directory: Path) -> None:
        if self._is_link_like(root):
            raise AutopilotError("authority root is a link or junction")
        root = root.resolve(strict=False)
        directory = Path(os.path.abspath(directory))
        try:
            directory.relative_to(root)
        except ValueError as error:
            raise AutopilotError("authority directory escapes its root") from error
        missing: list[Path] = []
        current = directory
        while current != root and not current.exists():
            missing.append(current)
            current = current.parent
        if current.exists() and self._is_link_like(current):
            raise AutopilotError("authority directory traverses a link or junction")
        directory.mkdir(parents=True, exist_ok=True)
        current = root
        for component in directory.relative_to(root).parts:
            current = current / component
            if self._is_link_like(current) or not current.is_dir():
                raise AutopilotError(
                    "authority directory traverses a link, junction, or non-directory"
                )
        for created in reversed(missing):
            self._fsync_directory(created.parent)

    @staticmethod
    def _git_transport_environment_issues() -> tuple[str, ...]:
        blocked = {
            "GIT_DIR",
            "GIT_WORK_TREE",
            "GIT_COMMON_DIR",
            "GIT_CONFIG_COUNT",
            "GIT_CONFIG_PARAMETERS",
            "GIT_CONFIG_GLOBAL",
            "GIT_CONFIG_SYSTEM",
            "GIT_CONFIG_NOSYSTEM",
            "GIT_OBJECT_DIRECTORY",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        }
        issues = [name for name in sorted(blocked) if name in os.environ]
        issues.extend(
            name
            for name in sorted(os.environ)
            if name.startswith("GIT_CONFIG_KEY_")
            or name.startswith("GIT_CONFIG_VALUE_")
        )
        return tuple(issues)

    def _observed_remote_transport_identity(self) -> Mapping[str, Any]:
        """Read the literal origin transport with every rewrite channel disabled."""

        injected = self._git_transport_environment_issues()
        if injected:
            raise AutopilotError(
                "Git transport identity is ambiguous under injected environment: "
                + ", ".join(injected)
            )
        urls = self._git(
            ("config", "--local", "--get-all", "remote.origin.url"), check=False
        )
        configured = [line.strip() for line in urls.stdout.splitlines() if line.strip()]
        if urls.returncode != 0 or len(configured) != 1:
            raise AutopilotError("canonical origin must have one literal local fetch URL")
        push_urls = self._git(
            ("config", "--local", "--get-all", "remote.origin.pushurl"), check=False
        )
        if push_urls.returncode not in {0, 1} or push_urls.stdout.strip():
            raise AutopilotError("canonical origin may not define a distinct push URL")
        rewrites = self._git(
            (
                "config",
                "--get-regexp",
                r"^url\..*\.(insteadOf|pushInsteadOf)$",
            ),
            check=False,
        )
        if rewrites.returncode not in {0, 1} or rewrites.stdout.strip():
            raise AutopilotError("Git URL rewrite configuration is forbidden")
        material: dict[str, Any] = {
            "schema_version": 1,
            "kind": "hive-mind-canonical-remote-transport-v1",
            "repository": str(self.control["target"]["repository"]),
            "remote_name": "origin",
            "fetch_url": configured[0],
            "push_url": configured[0],
        }
        material["record_id"] = digest_json(material)
        return material

    def bind_canonical_remote_transport_identity(self) -> Mapping[str, Any]:
        """Bind one repository transport while global arbiter authority is held."""

        lock_path = self.arbiter_dir / "locks" / "arbiter-authority.lock"
        if not runtime_file_lock_is_held(lock_path):
            raise AutopilotError(
                "canonical remote transport binding requires global arbiter authority"
            )
        observed = self._observed_remote_transport_identity()
        path = self.remote_transport_identity_path
        if path.exists() and self._is_link_like(path):
            raise AutopilotError("canonical remote transport authority is a link")
        if path.is_file():
            installed = self._strict_json_file(
                path, label="canonical remote transport authority"
            )
            if installed != observed:
                raise AutopilotError(
                    "canonical remote transport differs from repository arbiter binding"
                )
            return observed
        self._atomic_write_authority_json(path, dict(observed))
        return observed

    def assert_canonical_remote_transport_identity(self) -> Mapping[str, Any]:
        """Recheck the sealed transport immediately before any remote effect."""

        path = self.remote_transport_identity_path
        if not path.is_file() or self._is_link_like(path):
            raise AutopilotError(
                "canonical remote transport is unbound; run execution-init"
            )
        installed = self._strict_json_file(
            path, label="canonical remote transport authority"
        )
        observed = self._observed_remote_transport_identity()
        if installed != observed:
            raise AutopilotError(
                "canonical remote transport changed after arbiter binding"
            )
        return observed

    def execution_transaction_ref(
        self, transaction_id: str, *, execution_id: str | None = None
    ) -> str:
        """Derive the only private integration ref for an opaque transaction."""

        selected_execution_id = execution_id or self.execution_id
        if (
            AUTHORITY_ID.fullmatch(transaction_id) is None
            or AUTHORITY_ID.fullmatch(selected_execution_id) is None
        ):
            raise AutopilotError("publication transaction id is invalid")
        reference_id = digest_json(
            {
                "kind": "hive-mind-publication-transaction-evidence-ref-v1",
                "execution_id": selected_execution_id,
                "transaction_id": transaction_id,
            }
        )
        return "refs/heads/hme/t/" + reference_id.removeprefix("sha256:")

    def _assert_execution_evidence_ref(self, reference: str) -> None:
        allowed = re.compile(r"refs/heads/hme/(?:t|s|b|p)/[0-9a-f]{64}")
        if (
            not isinstance(reference, str)
            or allowed.fullmatch(reference) is None
            or any(character in reference for character in " \t\r\n\0~^:?*[\\")
            or ".." in reference
            or reference.endswith("/")
        ):
            raise AutopilotError("execution evidence ref is outside its namespace")
        checked = self._git(("check-ref-format", reference), check=False)
        if checked.returncode != 0:
            raise AutopilotError("execution evidence ref is not a valid Git reference")

    def _local_ref_sha(self, reference: str) -> str | None:
        resolved = self._git(
            ("rev-parse", "--verify", f"{reference}^{{commit}}"), check=False
        )
        value = resolved.stdout.strip()
        if resolved.returncode != 0:
            return None
        if FULL_SHA.fullmatch(value) is None:
            raise AutopilotError("local Git reference has malformed commit identity")
        return value

    def _materialize_remote_evidence_ref(
        self,
        reference: str,
        expected_sha: str,
        *,
        label: str,
    ) -> None:
        """Authenticate a remote immutable ref and copy it into this clone."""

        self._assert_execution_evidence_ref(reference)
        if FULL_SHA.fullmatch(expected_sha) is None:
            raise AutopilotError(f"{label} commit identity is invalid")
        self.assert_canonical_remote_transport_identity()
        try:
            remote_sha = self._remote_ref_sha(reference)
        except (ClaimError, AutopilotError) as error:
            raise AutopilotError(f"cannot observe {label}: {error}") from error
        if remote_sha != expected_sha:
            raise AutopilotError(
                f"{label} is absent or differs from its sealed remote ref"
            )
        local = self._git(
            ("rev-parse", "--verify", f"{reference}^{{commit}}"), check=False
        )
        if local.returncode == 0:
            if local.stdout.strip() != expected_sha:
                raise AutopilotError(f"local {label} ref conflicts with remote authority")
            return
        fetched = self._git(
            (
                "fetch",
                "--no-tags",
                "--no-write-fetch-head",
                "origin",
                f"+{reference}:{reference}",
            ),
            check=False,
        )
        if fetched.returncode != 0:
            raise AutopilotError(f"cannot materialize {label} in this clone")
        local = self._git(
            ("rev-parse", "--verify", f"{reference}^{{commit}}"), check=False
        )
        if local.returncode != 0 or local.stdout.strip() != expected_sha:
            raise AutopilotError(f"materialized {label} differs from remote authority")

    def _publish_remote_evidence_ref(
        self,
        reference: str,
        expected_sha: str,
        *,
        label: str,
    ) -> None:
        """O_EXCL-publish one immutable clone-independent Git capability."""

        self._assert_execution_evidence_ref(reference)
        if FULL_SHA.fullmatch(expected_sha) is None:
            raise AutopilotError(f"{label} commit identity is invalid")
        local = self._git(
            ("rev-parse", "--verify", f"{reference}^{{commit}}"), check=False
        )
        if local.returncode != 0 or local.stdout.strip() != expected_sha:
            raise AutopilotError(f"local {label} ref does not equal its sealed commit")
        self.assert_canonical_remote_transport_identity()
        remote_sha = self._remote_ref_sha(reference)
        if remote_sha is not None and remote_sha != expected_sha:
            raise AutopilotError(f"remote {label} ref is already bound differently")
        if remote_sha is None:
            pushed = self._git(
                (
                    "push",
                    "--porcelain",
                    f"--force-with-lease={reference}:",
                    "origin",
                    f"{expected_sha}:{reference}",
                ),
                check=False,
            )
            observed = self._remote_ref_sha(reference)
            if observed != expected_sha:
                raise AutopilotError(
                    f"remote {label} publication is indeterminate; "
                    f"push_exit_code={pushed.returncode}"
                )
        self._materialize_remote_evidence_ref(
            reference, expected_sha, label=label
        )

    def _publication_resource_path(self) -> Path:
        key = digest_json(
            {
                "kind": "hive-mind-publication-resource-v1",
                "repository": str(self.control["target"]["repository"]),
                "target_branch": self.target_branch,
            }
        )
        return (
            self.arbiter_dir
            / "publication-reservations"
            / f"{key.removeprefix('sha256:')}.json"
        )

    def _publication_transaction_path(self, transaction_id: str) -> Path:
        return self._secure_execution_path(
            Path("publication-transactions")
            / f"{transaction_id.removeprefix('sha256:')}.json"
        )

    def _publication_validation_challenge_path(self, transaction_id: str) -> Path:
        if AUTHORITY_ID.fullmatch(transaction_id) is None:
            raise AutopilotError("publication validation transaction id is invalid")
        return self._secure_execution_path(
            Path("publication-validation-challenges")
            / f"{transaction_id.removeprefix('sha256:')}.json"
        )

    def _publication_validation_completion_path(self, challenge_id: str) -> Path:
        if AUTHORITY_ID.fullmatch(challenge_id) is None:
            raise AutopilotError("publication validation challenge id is invalid")
        return self._secure_execution_path(
            Path("publication-validation-completions")
            / f"{challenge_id.removeprefix('sha256:')}.json"
        )

    def _publication_archive_path(self, transaction_id: str, record_id: str) -> Path:
        if (
            AUTHORITY_ID.fullmatch(transaction_id) is None
            or AUTHORITY_ID.fullmatch(record_id) is None
        ):
            raise AutopilotError("publication archive authority is invalid")
        return (
            self.arbiter_dir
            / "publication-reservation-archive"
            / f"{transaction_id.removeprefix('sha256:')}-"
            f"{record_id.removeprefix('sha256:')}.json"
        )

    @staticmethod
    def _seal_publication_record(record: Mapping[str, Any]) -> dict[str, Any]:
        sealed = dict(record)
        sealed.pop("record_id", None)
        sealed["record_id"] = digest_json(sealed)
        return sealed

    @staticmethod
    def _publication_nonce_is_valid(value: object) -> bool:
        return (
            isinstance(value, str)
            and len(value) == 64
            and all(character in "0123456789abcdef" for character in value)
        )

    def _publication_stdlib_bundle_identity(self) -> Mapping[str, object]:
        """Seal the stdlib implementation imported by the trusted gate harness."""

        modules: dict[str, Mapping[str, str]] = {}
        for name in (
            "hashlib",
            "json",
            "json.decoder",
            "json.encoder",
            "pathlib",
            "subprocess",
            "tempfile",
            "unittest",
            "unittest.loader",
            "unittest.result",
            "unittest.runner",
            "unittest.suite",
        ):
            specification = importlib.util.find_spec(name)
            origin = None if specification is None else specification.origin
            if not isinstance(origin, str) or origin in {"built-in", "frozen"}:
                raise AutopilotError(
                    f"publication validation stdlib module is unavailable: {name}"
                )
            path = Path(origin).resolve()
            if not path.is_file() or self._is_link_like(path):
                raise AutopilotError(
                    f"publication validation stdlib module is link-backed: {name}"
                )
            modules[name] = {
                "path": str(path),
                "digest": "sha256:" + sha256(path.read_bytes()).hexdigest(),
            }
        material: dict[str, object] = {
            "schema_version": 1,
            "kind": "hive-mind-publication-stdlib-bundle-v1",
            "modules": modules,
        }
        material["bundle_digest"] = digest_json(material)
        return material

    def _publication_sandbox_broker_identity(self) -> Mapping[str, object]:
        """Describe the native filesystem broker without overstating network safety."""

        command = shutil.which("codex.exe") or shutil.which("codex")
        executable: Path | None = None
        version: str | None = None
        unavailable_reason: str | None = None
        if command is None:
            unavailable_reason = "NATIVE_CODEX_SANDBOX_UNAVAILABLE"
        else:
            candidate = Path(command).resolve()
            if not candidate.is_file() or self._is_link_like(candidate):
                unavailable_reason = "NATIVE_CODEX_SANDBOX_LINK_BACKED"
            else:
                try:
                    version_process = subprocess.run(
                        [str(candidate), "--version"],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        timeout=30,
                        env={
                            key: value
                            for key, value in os.environ.items()
                            if not key.upper().startswith(("GIT_", "PYTHON"))
                        },
                    )
                except (OSError, subprocess.SubprocessError):
                    unavailable_reason = "NATIVE_CODEX_SANDBOX_EXECUTION_UNAVAILABLE"
                else:
                    observed_version = version_process.stdout.strip()
                    if (
                        version_process.returncode != 0
                        or not observed_version
                        or len(observed_version) > 256
                    ):
                        unavailable_reason = (
                            "NATIVE_CODEX_SANDBOX_VERSION_UNAUTHENTICATED"
                        )
                    else:
                        executable = candidate
                        version = observed_version
        # Codex 0.146's Windows restricted-token profile gives a useful
        # filesystem boundary, but its disable-network flag has been observed
        # permitting direct sockets on this host.  No untrusted test may run
        # until a separately attestable network-denial provider is integrated.
        material: dict[str, object] = {
            "schema_version": 1,
            "kind": "hive-mind-publication-sandbox-broker-v1",
            "executable_path": str(executable) if executable is not None else None,
            "executable_digest": (
                "sha256:" + sha256(executable.read_bytes()).hexdigest()
                if executable is not None
                else None
            ),
            "version": version,
            "permission_profile": ":read-only",
            "working_directory_policy": "ISOLATED_STANDALONE_BUNDLE",
            "network_flag": "--sandbox-state-disable-network",
            "network_isolation_attestation": None,
            "network_isolation_verified": False,
            "unavailable_reason": unavailable_reason,
        }
        material["identity_id"] = digest_json(material)
        return material

    def publication_validation_gate_identity(self) -> Mapping[str, object]:
        """Return the exact executable/code policy allowed to mint VALIDATED."""

        interpreter = Path(sys.executable).resolve()
        driver = Path(__file__).resolve().with_name("round_driver.py")
        git_command = shutil.which("git")
        if git_command is None:
            raise AutopilotError("validation Git executable is unavailable")
        git_executable = Path(git_command).resolve()
        for path, label in (
            (interpreter, "validation interpreter"),
            (git_executable, "validation Git executable"),
            (driver, "fixed validation driver"),
        ):
            if not path.is_file() or self._is_link_like(path):
                raise AutopilotError(f"{label} is unavailable or link-backed")
        environment_policy = dict(fixed_validation_environment_policy())
        environment_policy.update(
            {
                "harness_digest": "sha256:"
                + sha256(PUBLICATION_BROKER_GATE_HARNESS.encode("utf-8")).hexdigest(),
                "isolated_object_store": True,
                "remote_count": 0,
                "credential_environment": "EMPTY",
                "nonzero_exact_test_manifest_required": True,
                "skips_require_governed_allowance": True,
                "network_isolation_required": True,
            }
        )
        stdlib_bundle = self._publication_stdlib_bundle_identity()
        sandbox_broker = self._publication_sandbox_broker_identity()
        material: dict[str, object] = {
            "schema_version": 1,
            "kind": "hive-mind-fixed-publication-gate-identity-v1",
            "argv": [
                str(interpreter),
                "-I",
                "-S",
                "-B",
                "-c",
                PUBLICATION_BROKER_GATE_HARNESS,
                "<transaction-worktree>",
            ],
            "interpreter_path": str(interpreter),
            "interpreter_digest": "sha256:"
            + sha256(interpreter.read_bytes()).hexdigest(),
            "git_executable_path": str(git_executable),
            "git_executable_digest": "sha256:"
            + sha256(git_executable.read_bytes()).hexdigest(),
            "round_driver_path": str(driver),
            "round_driver_digest": "sha256:" + sha256(driver.read_bytes()).hexdigest(),
            "environment_policy_digest": digest_json(environment_policy),
            "stdlib_bundle_digest": stdlib_bundle["bundle_digest"],
            "sandbox_broker_identity_id": sandbox_broker["identity_id"],
        }
        material["identity_id"] = digest_json(material)
        return material

    @staticmethod
    def _publication_gate_matches_identity(
        gate: Mapping[str, object], identity: Mapping[str, object]
    ) -> bool:
        raw_argv = gate.get("argv")
        normalized_argv: object = raw_argv
        if isinstance(raw_argv, list) and len(raw_argv) == 7:
            normalized_argv = [*raw_argv[:-1], "<transaction-worktree>"]
        return not any(
            observed != identity.get(identity_field)
            for observed, identity_field in (
                (normalized_argv, "argv"),
                (gate.get("interpreter_path"), "interpreter_path"),
                (gate.get("interpreter_digest_before"), "interpreter_digest"),
                (gate.get("interpreter_digest_after"), "interpreter_digest"),
                (gate.get("git_executable_path"), "git_executable_path"),
                (
                    gate.get("git_executable_digest_before"),
                    "git_executable_digest",
                ),
                (
                    gate.get("git_executable_digest_after"),
                    "git_executable_digest",
                ),
                (gate.get("round_driver_path"), "round_driver_path"),
                (gate.get("round_driver_digest_before"), "round_driver_digest"),
                (gate.get("round_driver_digest_after"), "round_driver_digest"),
                (
                    gate.get("environment_policy_digest"),
                    "environment_policy_digest",
                ),
                (gate.get("stdlib_bundle_digest"), "stdlib_bundle_digest"),
                (
                    gate.get("sandbox_broker_identity_id"),
                    "sandbox_broker_identity_id",
                ),
            )
        )

    def _validated_publication_gate(
        self, value: object, *, label: str
    ) -> Mapping[str, object]:
        if not isinstance(value, Mapping) or set(value) != PUBLICATION_GATE_FIELDS:
            raise AutopilotError(f"{label} has an invalid exact schema")
        gate = dict(value)
        argv = gate.get("argv")
        interpreter = gate.get("interpreter_path")
        git_executable = gate.get("git_executable_path")
        driver = gate.get("round_driver_path")
        digest_fields = (
            "interpreter_digest_before",
            "interpreter_digest_after",
            "git_executable_digest_before",
            "git_executable_digest_after",
            "round_driver_digest_before",
            "round_driver_digest_after",
            "environment_policy_digest",
            "output_digest",
            "test_manifest_digest",
            "test_source_manifest_digest",
            "sandbox_broker_identity_id",
            "stdlib_bundle_digest",
        )
        counts = gate.get("test_counts")
        count_fields = {
            "discovered",
            "executed",
            "failures",
            "errors",
            "skipped",
            "expected_failures",
            "unexpected_successes",
            "successful",
        }
        if (
            gate.get("schema_version") != 1
            or gate.get("kind") != "hive-mind-fixed-publication-gate-result-v1"
            or not isinstance(argv, list)
            or len(argv) != 7
            or argv[:-1]
            != [
                interpreter,
                "-I",
                "-S",
                "-B",
                "-c",
                PUBLICATION_BROKER_GATE_HARNESS,
            ]
            or not isinstance(argv[-1], str)
            or not Path(argv[-1]).is_absolute()
            or not isinstance(interpreter, str)
            or not Path(interpreter).is_absolute()
            or not isinstance(git_executable, str)
            or not Path(git_executable).is_absolute()
            or not isinstance(driver, str)
            or not Path(driver).is_absolute()
            or any(
                not isinstance(gate.get(field), str)
                or AUTHORITY_ID.fullmatch(str(gate[field])) is None
                for field in digest_fields
            )
            or gate.get("interpreter_digest_before")
            != gate.get("interpreter_digest_after")
            or gate.get("git_executable_digest_before")
            != gate.get("git_executable_digest_after")
            or gate.get("round_driver_digest_before")
            != gate.get("round_driver_digest_after")
            or FULL_SHA.fullmatch(str(gate.get("worktree_tree"))) is None
            or FULL_SHA.fullmatch(str(gate.get("worktree_head_after"))) is None
            or FULL_SHA.fullmatch(str(gate.get("transaction_ref_after"))) is None
            or gate.get("worktree_status_porcelain") != ""
            or gate.get("exit_code") != 0
            or not isinstance(gate.get("summary"), str)
            or not isinstance(counts, Mapping)
            or set(counts) != count_fields
            or any(
                type(counts.get(field)) is not int or int(counts[field]) < 0
                for field in count_fields - {"successful"}
            )
            or type(counts.get("successful")) is not bool
            or counts.get("successful") is not True
            or int(counts.get("discovered", 0)) < 1
            or counts.get("executed") != counts.get("discovered")
            or counts.get("failures") != 0
            or counts.get("errors") != 0
            or counts.get("skipped") != 0
            or counts.get("expected_failures") != 0
            or counts.get("unexpected_successes") != 0
        ):
            raise AutopilotError(f"{label} is not an exact successful fixed gate")
        try:
            started = parse_time(gate.get("started_at"))
            completed = parse_time(gate.get("completed_at"))
        except Exception as error:
            raise AutopilotError(f"{label} timestamps are malformed") from error
        if completed < started:
            raise AutopilotError(f"{label} completed before it started")
        return gate

    def _validated_publication_validation_evidence(
        self,
        value: object,
        *,
        transaction: Mapping[str, Any],
        label: str,
    ) -> Mapping[str, object] | None:
        if value is None:
            return None
        if (
            not isinstance(value, Mapping)
            or set(value) != PUBLICATION_VALIDATION_EVIDENCE_FIELDS
        ):
            raise AutopilotError(f"{label} has an invalid exact schema")
        evidence = dict(value)
        material = dict(evidence)
        evidence_id = material.pop("evidence_id", None)
        lease = evidence.get("lease")
        released_lease = evidence.get("released_lease")
        cleanup = evidence.get("cleanup")
        gate = self._validated_publication_gate(
            evidence.get("gate"), label=f"{label} gate"
        )
        if (
            evidence.get("schema_version") != 1
            or evidence.get("kind")
            != "hive-mind-fixed-publication-validation-v1"
            or evidence_id != digest_json(material)
            or AUTHORITY_ID.fullmatch(str(evidence_id)) is None
            or evidence.get("execution_namespace")
            != transaction.get("execution_namespace")
            or evidence.get("execution_id") != transaction.get("execution_id")
            or evidence.get("transaction_id") != transaction.get("transaction_id")
            or evidence.get("release_id") != transaction.get("release_id")
            or evidence.get("authority_digest") != transaction.get("authority_digest")
            or evidence.get("authority_baseline_digest")
            != transaction.get("authority_baseline_digest")
            or evidence.get("receipt_heads_digest")
            != transaction.get("receipt_heads_digest")
            or evidence.get("pinned_sha") != transaction.get("pinned_sha")
            or FULL_SHA.fullmatch(str(evidence.get("pinned_tree"))) is None
            or AUTHORITY_ID.fullmatch(
                str(evidence.get("protected_test_manifest_digest"))
            )
            is None
            or AUTHORITY_ID.fullmatch(
                str(evidence.get("candidate_test_manifest_digest"))
            )
            is None
            or evidence.get("test_diff_policy")
            != "TARGET_TEST_BLOBS_IMMUTABLE_ADDITIONS_ALLOWED"
            or AUTHORITY_ID.fullmatch(
                str(evidence.get("governed_kernel_manifest_digest"))
            )
            is None
            or evidence.get("kernel_diff_policy")
            != "GOVERNED_AUTOPILOT_KERNEL_EXACTLY_IMMUTABLE"
            or type(evidence.get("dispatcher_admission_epoch")) is not int
            or int(evidence["dispatcher_admission_epoch"]) < 1
            or not isinstance(evidence.get("host_id"), str)
            or not str(evidence["host_id"]).strip()
            or AUTHORITY_ID.fullmatch(str(evidence.get("capacity_generation"))) is None
            or AUTHORITY_ID.fullmatch(
                str(evidence.get("broker_completion_id"))
            )
            is None
            or AUTHORITY_ID.fullmatch(
                str(evidence.get("transaction_record_id"))
            )
            is None
            or gate.get("worktree_head_after") != transaction.get("pinned_sha")
            or gate.get("transaction_ref_after") != transaction.get("pinned_sha")
            or gate.get("worktree_tree") != evidence.get("pinned_tree")
            or gate.get("test_source_manifest_digest")
            != evidence.get("candidate_test_manifest_digest")
        ):
            raise AutopilotError(f"{label} authority binding is invalid")
        if not isinstance(lease, Mapping) or set(lease) != KEYED_VALIDATION_LEASE_FIELDS:
            raise AutopilotError(f"{label} keyed lease schema is invalid")
        lease_material = dict(lease)
        global_reservation_id = lease_material.pop(
            "global_host_reservation_id", None
        )
        global_generation = lease_material.pop("global_capacity_generation", None)
        lease_id = lease_material.pop("lease_id", None)
        if (
            lease_id != digest_json(lease_material)
            or AUTHORITY_ID.fullmatch(str(lease_id)) is None
            or lease.get("status") != "ACTIVE"
            or lease.get("execution_id") != transaction.get("execution_id")
            or lease.get("release_id") != transaction.get("release_id")
            or lease.get("transaction_sha") != transaction.get("pinned_sha")
            or lease.get("capacity_host_id") != evidence.get("host_id")
            or lease.get("capacity_generation")
            != evidence.get("capacity_generation")
            or lease.get("host_reservation_id") != global_reservation_id
            or lease.get("capacity_generation") != global_generation
            or lease.get("claim_id") is not None
            or lease.get("launch_instruction_id") is not None
            or lease.get("resource_key") is not None
            or lease.get("authority_epoch") is not None
            or lease.get("target_sha") != transaction.get("expected_target_sha")
        ):
            raise AutopilotError(f"{label} keyed lease authority is invalid")
        try:
            acquired_at = parse_time(lease.get("acquired_at"))
            lease_expires_at = parse_time(lease.get("expires_at"))
        except Exception as error:
            raise AutopilotError(f"{label} keyed lease times are malformed") from error
        if lease_expires_at <= acquired_at:
            raise AutopilotError(f"{label} keyed lease lifetime is invalid")
        if not isinstance(released_lease, Mapping):
            raise AutopilotError(f"{label} released lease archive is absent")
        allowed_released_fields = (
            (KEYED_VALIDATION_LEASE_FIELDS - {
                "global_host_reservation_id",
                "global_capacity_generation",
            })
            | {"released_at", "renewed_at"}
        )
        required_released_fields = allowed_released_fields - {"renewed_at"}
        if not (
            set(released_lease) == required_released_fields
            or set(released_lease) == allowed_released_fields
        ):
            raise AutopilotError(f"{label} released lease archive schema is invalid")
        if (
            released_lease.get("status") != "RELEASED"
            or released_lease.get("lease_id") != lease_id
            or released_lease.get("execution_id")
            != transaction.get("execution_id")
            or released_lease.get("release_id") != transaction.get("release_id")
            or released_lease.get("transaction_sha")
            != transaction.get("pinned_sha")
            or released_lease.get("host_reservation_id") != global_reservation_id
            or released_lease.get("capacity_host_id") != evidence.get("host_id")
            or released_lease.get("capacity_generation")
            != evidence.get("capacity_generation")
        ):
            raise AutopilotError(f"{label} released lease archive is not exact")
        try:
            released_at = parse_time(released_lease.get("released_at"))
            released_expires_at = parse_time(released_lease.get("expires_at"))
            renewed_at = (
                parse_time(released_lease.get("renewed_at"))
                if "renewed_at" in released_lease
                else None
            )
        except Exception as error:
            raise AutopilotError(
                f"{label} released lease archive times are malformed"
            ) from error
        if (
            released_at < acquired_at
            or released_expires_at <= acquired_at
            or (renewed_at is not None and renewed_at < acquired_at)
        ):
            raise AutopilotError(f"{label} released lease archive lifetime is invalid")
        if (
            not isinstance(cleanup, Mapping)
            or set(cleanup) != KEYED_VALIDATION_CLEANUP_FIELDS
        ):
            raise AutopilotError(f"{label} keyed cleanup schema is invalid")
        cleanup_material = dict(cleanup)
        cleanup_id = cleanup_material.pop("record_id", None)
        host_reservation = cleanup.get("host_reservation")
        if (
            cleanup_id != digest_json(cleanup_material)
            or AUTHORITY_ID.fullmatch(str(cleanup_id)) is None
            or cleanup.get("schema_version") != 1
            or cleanup.get("kind") != "hive-mind-keyed-validation-cleanup-v1"
            or cleanup.get("execution_id") != transaction.get("execution_id")
            or cleanup.get("release_id") != transaction.get("release_id")
            or cleanup.get("transaction_sha") != transaction.get("pinned_sha")
            or cleanup.get("lease_id") != lease_id
            or cleanup.get("lease_released") is not True
            or cleanup.get("errors") != []
            or not isinstance(host_reservation, Mapping)
        ):
            raise AutopilotError(f"{label} keyed cleanup authority is invalid")
        reservation_material = dict(host_reservation)
        reservation_event_id = reservation_material.pop("event_id", None)
        reservation_identity = {
            "kind": "hive-mind-host-reservation-key-v1",
            "repository": host_reservation.get("repository"),
            "execution_id": host_reservation.get("execution_id"),
            "host_id": host_reservation.get("host_id"),
            "provider_generation": host_reservation.get("provider_generation"),
            "capacity_generation": host_reservation.get("capacity_generation"),
            "local_reservation_id": host_reservation.get("local_reservation_id"),
            "reservation_kind": host_reservation.get("reservation_kind"),
        }
        if "host_kernel_generation" in host_reservation:
            reservation_identity.update(
                {
                    "host_kernel_generation": host_reservation.get(
                        "host_kernel_generation"
                    ),
                    "execution_adapter_identity_record_id": host_reservation.get(
                        "execution_adapter_identity_record_id"
                    ),
                }
            )
        if "host_scheduler_grant_id" in host_reservation:
            reservation_identity["host_scheduler_grant_id"] = (
                host_reservation.get("host_scheduler_grant_id")
            )
        if (
            reservation_event_id != digest_json(reservation_material)
            or AUTHORITY_ID.fullmatch(str(reservation_event_id)) is None
            or host_reservation.get("reservation_id")
            != digest_json(reservation_identity)
            or host_reservation.get("reservation_id") != global_reservation_id
            or host_reservation.get("state") != "RELEASED"
            or host_reservation.get("reservation_kind") != "VALIDATION"
            or host_reservation.get("execution_id")
            != transaction.get("execution_id")
            or host_reservation.get("host_id") != evidence.get("host_id")
            or AUTHORITY_ID.fullmatch(
                str(host_reservation.get("provider_generation"))
            )
            is None
            or type(host_reservation.get("provider_epoch")) is not int
            or int(host_reservation["provider_epoch"]) < 1
            or host_reservation.get("capacity_generation")
            != evidence.get("capacity_generation")
            or host_reservation.get("write_scopes") != []
        ):
            raise AutopilotError(f"{label} validation host permit is invalid")
        try:
            parse_time(cleanup.get("recorded_at"))
            host_reserved_at = parse_time(host_reservation.get("reserved_at"))
            host_expires_at = parse_time(host_reservation.get("expires_at"))
            host_released_at = parse_time(host_reservation.get("released_at"))
            gate_started_at = parse_time(gate.get("started_at"))
            gate_completed_at = parse_time(gate.get("completed_at"))
        except Exception as error:
            raise AutopilotError(f"{label} cleanup times are malformed") from error
        if (
            gate_started_at < acquired_at
            or gate_started_at < host_reserved_at
            or gate_completed_at > released_at
            or gate_completed_at > released_expires_at
            or gate_completed_at > host_expires_at
            or gate_completed_at > host_released_at
        ):
            raise AutopilotError(
                f"{label} fixed gate ran outside its lease/host permit"
            )
        return evidence

    def _validated_publication_transaction(
        self,
        value: object,
        *,
        label: str,
        expected_execution_id: str | None = None,
        expected_execution_namespace: str | None = None,
    ) -> dict[str, Any]:
        """Authenticate one exact transaction record before trusting any field."""

        if not isinstance(value, Mapping) or set(value) != PUBLICATION_TRANSACTION_FIELDS:
            raise AutopilotError(f"{label} has an invalid exact schema")
        record = dict(value)
        material = dict(record)
        record_id = material.pop("record_id", None)
        if (
            record.get("schema_version") != 1
            or record.get("kind") != PUBLICATION_TRANSACTION_KIND
            or not isinstance(record_id, str)
            or AUTHORITY_ID.fullmatch(record_id) is None
            or record_id != digest_json(material)
        ):
            raise AutopilotError(f"{label} has an invalid record seal")
        status = record.get("status")
        if status not in (
            PUBLICATION_NONTERMINAL_STATUSES
            | PUBLICATION_INDETERMINATE_STATUSES
            | PUBLICATION_TERMINAL_STATUSES
        ):
            raise AutopilotError(f"{label} has an invalid status")
        round_id = record.get("round_id")
        if not (
            isinstance(round_id, str)
            and (
                AUTHORITY_ID.fullmatch(round_id) is not None
                or (
                    round_id.startswith("R")
                    and round_id[1:].isdigit()
                    and int(round_id[1:]) >= 1
                )
            )
        ):
            raise AutopilotError(f"{label} has an invalid round id")
        if any(
            (
                not isinstance(record.get(field), str)
                or AUTHORITY_ID.fullmatch(str(record.get(field))) is None
            )
            for field in (
                "transaction_key",
                "transaction_id",
                "execution_id",
                "release_id",
                "authority_digest",
                "authority_baseline_digest",
                "receipt_heads_digest",
                "transaction_lease_id",
            )
        ):
            raise AutopilotError(f"{label} has malformed digest authority")
        selected_execution_id = expected_execution_id or self.execution_id
        selected_execution_namespace = (
            expected_execution_namespace or self.execution_namespace
        )
        if (
            record.get("execution_namespace") != selected_execution_namespace
            or record.get("execution_id") != selected_execution_id
            or record.get("repository")
            != str(self.control["target"]["repository"])
            or record.get("target_branch") != self.target_branch
            or not isinstance(record.get("coordinator_id"), str)
            or not str(record["coordinator_id"]).strip()
            or not isinstance(record.get("actor"), str)
            or not str(record["actor"]).strip()
            or not isinstance(record.get("detail"), str)
            or not str(record["detail"]).strip()
            or FULL_SHA.fullmatch(str(record.get("expected_target_sha"))) is None
            or type(record.get("attempt_epoch")) is not int
            or int(record["attempt_epoch"]) < 1
            or not self._publication_nonce_is_valid(record.get("nonce"))
            or not self._publication_nonce_is_valid(
                record.get("transaction_lease_nonce")
            )
        ):
            raise AutopilotError(f"{label} has malformed immutable coordinates")
        heads = record.get("receipt_heads")
        if not isinstance(heads, list) or not heads:
            raise AutopilotError(f"{label} has no exact receipt heads")
        normalized_heads: list[dict[str, str]] = []
        for item in heads:
            if (
                not isinstance(item, Mapping)
                or set(item) != {"node_id", "branch", "sha"}
                or not isinstance(item.get("node_id"), str)
                or not str(item["node_id"]).strip()
                or not isinstance(item.get("branch"), str)
                or not str(item["branch"]).strip()
                or FULL_SHA.fullmatch(str(item.get("sha"))) is None
            ):
                raise AutopilotError(f"{label} has malformed receipt-head evidence")
            normalized_heads.append(
                {
                    "node_id": str(item["node_id"]),
                    "branch": str(item["branch"]),
                    "sha": str(item["sha"]),
                }
            )
        if (
            normalized_heads
            != sorted(normalized_heads, key=lambda item: item["node_id"])
            or len({item["node_id"] for item in normalized_heads})
            != len(normalized_heads)
            or record.get("receipt_heads_digest") != digest_json(normalized_heads)
        ):
            raise AutopilotError(f"{label} receipt heads are noncanonical")
        expected_key = digest_json(
            {
                "kind": "hive-mind-publication-transaction-key-v1",
                "execution_id": selected_execution_id,
                "release_id": record["release_id"],
                "round_id": round_id,
                "expected_target_sha": record["expected_target_sha"],
                "authority_digest": record["authority_digest"],
                "authority_baseline_digest": record[
                    "authority_baseline_digest"
                ],
                "receipt_heads": normalized_heads,
            }
        )
        if record.get("transaction_key") != expected_key:
            raise AutopilotError(f"{label} transaction key is noncanonical")
        expected_transaction_id = digest_json(
            {
                "kind": "hive-mind-publication-attempt-key-v1",
                "transaction_key": expected_key,
                "attempt_epoch": record["attempt_epoch"],
                "nonce": record["nonce"],
            }
        )
        expected_lease_id = digest_json(
            {
                "kind": "hive-mind-publication-coordinator-lease-v1",
                "transaction_id": expected_transaction_id,
                "nonce": record["transaction_lease_nonce"],
            }
        )
        if (
            record.get("transaction_id") != expected_transaction_id
            or record.get("transaction_lease_id") != expected_lease_id
            or record.get("transaction_ref")
            != self.execution_transaction_ref(
                expected_transaction_id, execution_id=selected_execution_id
            )
        ):
            raise AutopilotError(f"{label} attempt/lease authority is noncanonical")
        try:
            reserved_at = parse_time(record.get("reserved_at"))
            updated_at = parse_time(record.get("updated_at"))
            lease_expires_at = parse_time(record.get("lease_expires_at"))
        except Exception as error:
            raise AutopilotError(f"{label} has malformed timestamps") from error
        if updated_at < reserved_at or lease_expires_at <= reserved_at:
            raise AutopilotError(f"{label} timestamp ordering is invalid")
        publishing_fields = (
            record.get("publishing_lease_nonce"),
            record.get("publishing_lease_id"),
            record.get("publishing_lease_expires_at"),
        )
        if all(value is None for value in publishing_fields):
            publishing_present = False
        elif all(value is not None for value in publishing_fields):
            publishing_present = True
            if (
                not self._publication_nonce_is_valid(publishing_fields[0])
                or not isinstance(publishing_fields[1], str)
                or AUTHORITY_ID.fullmatch(str(publishing_fields[1])) is None
                or FULL_SHA.fullmatch(str(record.get("pinned_sha"))) is None
            ):
                raise AutopilotError(f"{label} has malformed publishing authority")
            expected_publishing_id = digest_json(
                {
                    "kind": "hive-mind-publication-operation-lease-v1",
                    "transaction_id": expected_transaction_id,
                    "transaction_lease_id": expected_lease_id,
                    "pinned_sha": record["pinned_sha"],
                    "nonce": publishing_fields[0],
                }
            )
            try:
                publishing_expires_at = parse_time(publishing_fields[2])
            except Exception as error:
                raise AutopilotError(
                    f"{label} has malformed publishing lease expiry"
                ) from error
            if (
                publishing_fields[1] != expected_publishing_id
                or publishing_expires_at <= reserved_at
            ):
                raise AutopilotError(f"{label} publishing lease is noncanonical")
        else:
            raise AutopilotError(f"{label} has a partial publishing lease")
        pinned_sha = record.get("pinned_sha")
        if pinned_sha is not None and FULL_SHA.fullmatch(str(pinned_sha)) is None:
            raise AutopilotError(f"{label} has an invalid pinned SHA")
        validation_evidence = self._validated_publication_validation_evidence(
            record.get("validation_evidence"),
            transaction=record,
            label=f"{label} validation evidence",
        )
        completed_at_value = record.get("completed_at")
        if status in PUBLICATION_NONTERMINAL_STATUSES:
            if record.get("outcome") is not None or completed_at_value is not None:
                raise AutopilotError(f"{label} nonterminal outcome is malformed")
            if status == "PREPARED" and (
                pinned_sha is not None
                or publishing_present
                or validation_evidence is not None
            ):
                raise AutopilotError(f"{label} PREPARED state carries publish authority")
            if status == "PINNED" and (
                pinned_sha is None
                or publishing_present
                or validation_evidence is not None
            ):
                raise AutopilotError(
                    f"{label} PINNED state lacks exact portable commit authority"
                )
            if status == "VALIDATED" and (
                pinned_sha is None
                or publishing_present
                or validation_evidence is None
            ):
                raise AutopilotError(
                    f"{label} VALIDATED state lacks its fixed-gate capability"
                )
            if status == "PUBLISHING" and (
                pinned_sha is None
                or not publishing_present
                or validation_evidence is None
            ):
                raise AutopilotError(f"{label} PUBLISHING state lacks operation authority")
        else:
            if record.get("outcome") != status or completed_at_value is None:
                raise AutopilotError(f"{label} terminal outcome is malformed")
            try:
                completed_at = parse_time(completed_at_value)
            except Exception as error:
                raise AutopilotError(f"{label} completion time is malformed") from error
            if completed_at < reserved_at or updated_at != completed_at:
                raise AutopilotError(f"{label} terminal time ordering is invalid")
            if status in {
                "PUBLISHED",
                "SUPERSEDED_INTEGRATED",
                "PUBLISH_UNKNOWN",
                "NO_PUSH",
            } and (
                pinned_sha is None or validation_evidence is None
            ):
                raise AutopilotError(
                    f"{label} validated outcome lacks its fixed-gate capability"
                )
            if status == "PUBLISH_UNKNOWN" and not publishing_present:
                raise AutopilotError(
                    f"{label} indeterminate outcome lacks its sealed publish intent"
                )
        if publishing_present and validation_evidence is None:
            raise AutopilotError(
                f"{label} publish authority was minted without fixed validation"
            )
        return record

    def _validated_publication_resource(
        self, value: object, *, label: str, allow_foreign: bool = False
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not isinstance(value, Mapping) or set(value) != PUBLICATION_RESOURCE_FIELDS:
            raise AutopilotError(f"{label} has an invalid exact schema")
        resource = dict(value)
        material = dict(resource)
        record_id = material.pop("record_id", None)
        if (
            resource.get("schema_version") != 1
            or resource.get("kind") != PUBLICATION_RESERVATION_KIND
            or not isinstance(record_id, str)
            or AUTHORITY_ID.fullmatch(record_id) is None
            or record_id != digest_json(material)
        ):
            raise AutopilotError(f"{label} has an invalid record seal")
        raw_transaction = resource.get("transaction")
        foreign_id: str | None = None
        foreign_namespace: str | None = None
        if allow_foreign and isinstance(raw_transaction, Mapping):
            raw_id = raw_transaction.get("execution_id")
            raw_namespace = raw_transaction.get("execution_namespace")
            if (
                isinstance(raw_id, str)
                and AUTHORITY_ID.fullmatch(raw_id) is not None
                and isinstance(raw_namespace, str)
                and raw_namespace.strip()
            ):
                foreign_id = raw_id
                foreign_namespace = raw_namespace
        transaction = self._validated_publication_transaction(
            raw_transaction,
            label=f"{label} embedded transaction",
            expected_execution_id=foreign_id,
            expected_execution_namespace=foreign_namespace,
        )
        expected = {
            "status": transaction["status"],
            "transaction_id": transaction["transaction_id"],
            "execution_id": transaction["execution_id"],
            "release_id": transaction["release_id"],
            "repository": transaction["repository"],
            "target_branch": transaction["target_branch"],
            "expected_target_sha": transaction["expected_target_sha"],
            "expires_at": transaction["lease_expires_at"],
            "outcome": transaction["outcome"],
        }
        if any(resource.get(field) != expected_value for field, expected_value in expected.items()):
            raise AutopilotError(f"{label} differs from its embedded transaction")
        return resource, transaction

    def _publication_transition_allowed(
        self, previous: Mapping[str, Any], current: Mapping[str, Any]
    ) -> bool:
        if previous.get("transaction_id") != current.get("transaction_id"):
            return bool(
                previous.get("status") in PUBLICATION_TERMINAL_STATUSES
                and current.get("status") == "PREPARED"
                and previous.get("repository") == current.get("repository")
                and previous.get("target_branch") == current.get("target_branch")
                and (
                    previous.get("transaction_key") != current.get("transaction_key")
                    or current.get("attempt_epoch")
                    == int(previous.get("attempt_epoch", 0)) + 1
                )
            )
        immutable_fields = (
            "transaction_key",
            "attempt_epoch",
            "nonce",
            "execution_namespace",
            "execution_id",
            "release_id",
            "round_id",
            "repository",
            "target_branch",
            "expected_target_sha",
            "authority_digest",
            "authority_baseline_digest",
            "receipt_heads",
            "receipt_heads_digest",
            "transaction_ref",
            "coordinator_id",
            "transaction_lease_nonce",
            "transaction_lease_id",
            "reserved_at",
        )
        if any(previous.get(field) != current.get(field) for field in immutable_fields):
            return False
        previous_status = previous.get("status")
        current_status = current.get("status")
        previous_validation = previous.get("validation_evidence")
        current_validation = current.get("validation_evidence")
        if previous_validation is not None and previous_validation != current_validation:
            return False
        if (
            previous_validation is None
            and current_validation is not None
            and not (
                previous_status == "PINNED"
                and current_status == "VALIDATED"
                and isinstance(current_validation, Mapping)
                and current_validation.get("transaction_record_id")
                == previous.get("record_id")
            )
        ):
            return False
        if previous_status in PUBLICATION_TERMINAL_STATUSES:
            return previous == current
        if previous_status == "PUBLISH_UNKNOWN":
            # A later point-in-time observation at the predecessor cannot prove
            # that the earlier push failed: the pinned commit may have been
            # accepted and subsequently reverted.  Only observing the exact
            # pinned SHA resolves the historical uncertainty.
            return current_status in {
                "PUBLISH_UNKNOWN",
                "PUBLISHED",
                "SUPERSEDED_INTEGRATED",
            }
        if previous_status == "PREPARED":
            return current_status in (
                {"PREPARED", "PINNED"}
                | PUBLICATION_TERMINAL_STATUSES
            )
        if previous_status == "PINNED":
            return current_status in (
                {"PINNED", "VALIDATED"}
                | PUBLICATION_TERMINAL_STATUSES
            )
        if previous_status == "VALIDATED":
            return current_status in (
                {"VALIDATED", "PUBLISHING"}
                | PUBLICATION_TERMINAL_STATUSES
            )
        return previous_status == "PUBLISHING" and current_status in (
            {"PUBLISHING"}
            | PUBLICATION_INDETERMINATE_STATUSES
            | PUBLICATION_TERMINAL_STATUSES
        )

    @staticmethod
    def _publication_coordinates(record: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            field: record.get(field)
            for field in (
                "transaction_key",
                "execution_namespace",
                "execution_id",
                "release_id",
                "round_id",
                "repository",
                "target_branch",
                "expected_target_sha",
                "authority_digest",
                "authority_baseline_digest",
                "receipt_heads",
                "receipt_heads_digest",
            )
        }

    def _publication_resource_record(
        self, transaction: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        raw_execution_id = transaction.get("execution_id")
        raw_execution_namespace = transaction.get("execution_namespace")
        transaction = self._validated_publication_transaction(
            transaction,
            label="publication transaction",
            expected_execution_id=(
                str(raw_execution_id)
                if isinstance(raw_execution_id, str)
                else None
            ),
            expected_execution_namespace=(
                str(raw_execution_namespace)
                if isinstance(raw_execution_namespace, str)
                else None
            ),
        )
        return self._seal_publication_record(
            {
                "schema_version": 1,
                "kind": PUBLICATION_RESERVATION_KIND,
                "status": transaction["status"],
                "transaction_id": transaction["transaction_id"],
                "execution_id": transaction["execution_id"],
                "release_id": transaction["release_id"],
                "repository": transaction["repository"],
                "target_branch": transaction["target_branch"],
                "expected_target_sha": transaction["expected_target_sha"],
                "expires_at": transaction["lease_expires_at"],
                "outcome": transaction["outcome"],
                # Embedding the exact record makes a reservation-first crash
                # recoverable without trusting a missing execution-local copy.
                "transaction": dict(transaction),
            }
        )

    def _validate_publication_event(
        self,
        value: object,
        *,
        label: str,
        previous_event: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if not isinstance(value, Mapping) or set(value) != PUBLICATION_EVENT_FIELDS:
            raise AutopilotError(f"{label} has an invalid exact schema")
        event = dict(value)
        material = dict(event)
        event_id = material.pop("event_id", None)
        if (
            event.get("schema_version") != 1
            or event.get("kind") != PUBLICATION_EVENT_KIND
            or not isinstance(event_id, str)
            or AUTHORITY_ID.fullmatch(event_id) is None
            or event_id != digest_json(material)
        ):
            raise AutopilotError(f"{label} has an invalid event seal")
        transaction = self._validated_publication_transaction(
            event.get("transaction"), label=f"{label} transaction"
        )
        if any(
            event.get(field) != transaction.get(transaction_field)
            for field, transaction_field in (
                ("transaction_id", "transaction_id"),
                ("transaction_record_id", "record_id"),
                ("status", "status"),
                ("recorded_at", "updated_at"),
            )
        ) or event.get("detail") != transaction.get("detail"):
            raise AutopilotError(f"{label} differs from its transaction")
        expected_previous = (
            previous_event.get("event_id") if previous_event is not None else None
        )
        if event.get("previous_event_id") != expected_previous:
            raise AutopilotError(f"{label} is not chained to its predecessor")
        if previous_event is None:
            if transaction.get("status") != "PREPARED":
                raise AutopilotError(
                    f"{label} cannot begin without a PREPARED transaction"
                )
        else:
            previous_transaction = previous_event.get("transaction")
            assert isinstance(previous_transaction, Mapping)
            if not self._publication_transition_allowed(
                previous_transaction, transaction
            ):
                raise AutopilotError(f"{label} contains an impossible state transition")
        return event

    def _read_publication_journal(
        self, *, allow_torn_tail: bool
    ) -> tuple[list[Mapping[str, Any]], bytes]:
        path = self._secure_execution_path("publication-transactions.jsonl")
        if not path.is_file():
            return [], b""
        if self._is_link_like(path):
            raise AutopilotError("publication journal is a link or junction")
        raw = path.read_bytes()
        complete = raw
        tail = b""
        if raw and not raw.endswith(b"\n"):
            split = raw.rfind(b"\n")
            complete = raw[: split + 1] if split >= 0 else b""
            tail = raw[split + 1 :]
            if not allow_torn_tail:
                raise AutopilotError("publication journal has a torn final append")
        events: list[Mapping[str, Any]] = []
        for index, line in enumerate(complete.splitlines(), 1):
            value = self._strict_json_bytes(
                line, label=f"publication journal line {index}"
            )
            event = self._validate_publication_event(
                value,
                label=f"publication journal line {index}",
                previous_event=events[-1] if events else None,
            )
            if line + b"\n" != self._canonical_json_bytes(event):
                raise AutopilotError(
                    f"publication journal line {index} is noncanonical"
                )
            events.append(event)
        return events, tail

    def _publication_journal_events(self) -> list[Mapping[str, Any]]:
        events, _ = self._read_publication_journal(allow_torn_tail=False)
        return events

    def _next_publication_event(
        self,
        transaction: Mapping[str, Any],
        events: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any] | None:
        if events and all(
            events[-1].get(field) == transaction.get(transaction_field)
            for field, transaction_field in (
                ("transaction_id", "transaction_id"),
                ("transaction_record_id", "record_id"),
                ("status", "status"),
            )
        ):
            return None
        material: dict[str, Any] = {
            "schema_version": 1,
            "kind": PUBLICATION_EVENT_KIND,
            "transaction_id": transaction["transaction_id"],
            "transaction_record_id": transaction["record_id"],
            "status": transaction["status"],
            "detail": transaction["detail"],
            "recorded_at": transaction["updated_at"],
            "previous_event_id": events[-1]["event_id"] if events else None,
            "transaction": dict(transaction),
        }
        event = {**material, "event_id": digest_json(material)}
        return self._validate_publication_event(
            event,
            label="publication journal next event",
            previous_event=events[-1] if events else None,
        )

    def _preflight_publication_event(
        self, transaction: Mapping[str, Any]
    ) -> None:
        events, torn_tail = self._read_publication_journal(allow_torn_tail=True)
        event = self._next_publication_event(transaction, events)
        if event is None:
            if torn_tail:
                raise AutopilotError(
                    "publication journal has bytes after its durable transaction event"
                )
            return
        payload = self._canonical_json_bytes(event)
        if torn_tail and (
            len(torn_tail) >= len(payload) or not payload.startswith(torn_tail)
        ):
            raise AutopilotError(
                "publication journal torn tail is not an exact prefix of the durable transition"
            )

    def _append_publication_event(
        self, transaction: Mapping[str, Any], *, detail: str
    ) -> Mapping[str, Any]:
        transaction = self._validated_publication_transaction(
            transaction, label="publication journal transaction"
        )
        events, torn_tail = self._read_publication_journal(allow_torn_tail=True)
        event = self._next_publication_event(transaction, events)
        if event is None:
            if torn_tail:
                raise AutopilotError(
                    "publication journal has bytes after its durable transaction event"
                )
            return events[-1]
        payload = self._canonical_json_bytes(event)
        path = self._secure_execution_path("publication-transactions.jsonl")
        self._ensure_authority_directory(self.execution_dir, path.parent)
        if torn_tail:
            if len(torn_tail) >= len(payload) or not payload.startswith(torn_tail):
                raise AutopilotError(
                    "publication journal torn tail is not an exact prefix of the durable transition"
                )
            descriptor = os.open(
                path,
                os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            try:
                complete_size = path.stat().st_size - len(torn_tail)
                os.ftruncate(descriptor, complete_size)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            self._fsync_directory(path.parent)
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            with os.fdopen(descriptor, "ab", closefd=True) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            # os.fdopen owns descriptor after successful construction.
            pass
        self._fsync_directory(path.parent)
        return event

    def _write_publication_pair(
        self, transaction: Mapping[str, Any], *, detail: str
    ) -> None:
        transaction = self._validated_publication_transaction(
            transaction, label="publication transaction update"
        )
        # Reject an impossible transition or adversarial torn tail before either
        # half of the reservation/transaction pair is replaced.
        self._preflight_publication_event(transaction)
        resource_path = self._publication_resource_path()
        if resource_path.is_file():
            resource_value = self._strict_json_file(
                resource_path, label="publication target reservation"
            )
            _, prior = self._validated_publication_resource(
                resource_value,
                label="publication target reservation",
                allow_foreign=True,
            )
            if not self._publication_transition_allowed(prior, transaction):
                raise AutopilotError(
                    "publication reservation contains an impossible transition"
                )
        # Reservation first: it embeds enough exact evidence to reconstruct the
        # execution record if the process dies between these two durable replaces.
        self._atomic_write_authority_json(
            resource_path,
            self._publication_resource_record(transaction),
        )
        self._atomic_write_authority_json(
            self._publication_transaction_path(str(transaction["transaction_id"])),
            transaction,
        )
        self._append_publication_event(transaction, detail=detail)

    def _validate_receipt_heads(
        self, receipt_heads: Mapping[str, str], release: Mapping[str, Any]
    ) -> list[dict[str, str]]:
        wave = list(release.get("released_wave", []))
        if set(receipt_heads) != set(wave):
            raise AutopilotError(
                "publication receipt heads must exactly cover the released wave"
            )
        sealed: list[dict[str, str]] = []
        for node_id in sorted(wave):
            sha = receipt_heads.get(node_id)
            if not isinstance(sha, str) or FULL_SHA.fullmatch(sha) is None:
                raise AutopilotError(
                    f"publication receipt head is invalid for {node_id}"
                )
            sealed.append(
                {
                    "node_id": node_id,
                    "branch": str(self.node(node_id)["branch"]),
                    "sha": sha,
                }
            )
        return sealed

    def _round_authority_digests(
        self, snapshot: object, *, release_id: str
    ) -> tuple[str, str]:
        if (
            not isinstance(snapshot, Mapping)
            or snapshot.get("schema_version") != 1
            or snapshot.get("kind")
            != "hive-mind-round-authority-snapshot-v1"
            or snapshot.get("execution_namespace") != self.execution_namespace
            or snapshot.get("execution_id") != self.execution_id
            or snapshot.get("release_id") != release_id
        ):
            raise AutopilotError("round authority snapshot identity is invalid")
        raw_digest = snapshot.get("authority_digest")
        if not isinstance(raw_digest, str) or AUTHORITY_ID.fullmatch(raw_digest) is None:
            raise AutopilotError("round authority snapshot digest is invalid")
        authoritative = dict(snapshot)
        authoritative.pop("observed_at", None)
        authoritative.pop("authority_digest", None)
        if digest_json(authoritative) != raw_digest:
            raise AutopilotError("round authority snapshot digest does not seal its bytes")
        baseline = dict(authoritative)
        baseline["publication_transaction_fence"] = None
        baseline["active_publication_count"] = 0
        baseline["publication_transaction_status"] = None
        return raw_digest, digest_json(baseline)

    def _current_publication_resource(
        self,
    ) -> tuple[Mapping[str, Any], Mapping[str, Any]] | None:
        path = self._publication_resource_path()
        if not path.is_file():
            return None
        value = self._strict_json_file(
            path, label="publication target reservation"
        )
        return self._validated_publication_resource(
            value,
            label="publication target reservation",
            allow_foreign=True,
        )

    def _assert_canonical_publication_chain(
        self,
        transaction: Mapping[str, Any],
        pinned_sha: str,
    ) -> str:
        """Prove the pin is exactly base + one ordered two-parent merge per receipt."""

        if FULL_SHA.fullmatch(pinned_sha) is None:
            raise AutopilotError("publication pin is not a full commit identity")
        transaction_ref = str(transaction.get("transaction_ref"))
        if self._local_ref_sha(transaction_ref) != pinned_sha:
            raise AutopilotError(
                "publication transaction ref does not equal its proposed pin"
            )
        heads = transaction.get("receipt_heads")
        if not isinstance(heads, list) or not heads:
            raise AutopilotError("publication pin has no ordered receipt authority")
        current = pinned_sha
        for item in reversed(heads):
            if not isinstance(item, Mapping):
                raise AutopilotError("publication pin receipt authority is malformed")
            receipt_sha = str(item.get("sha"))
            parents = self._git(
                ("rev-list", "--parents", "-n", "1", current),
                check=False,
            )
            fields = parents.stdout.strip().split()
            if (
                parents.returncode != 0
                or len(fields) != 3
                or fields[0] != current
                or fields[2] != receipt_sha
                or any(FULL_SHA.fullmatch(value) is None for value in fields)
            ):
                raise AutopilotError(
                    "publication pin is not the exact ordered first-parent merge chain"
                )
            previous = fields[1]
            expected_tree = self._git(
                (
                    "-c",
                    f"core.hooksPath={os.devnull}",
                    "-c",
                    "commit.gpgSign=false",
                    "-c",
                    "merge.verifySignatures=false",
                    "merge-tree",
                    "--write-tree",
                    previous,
                    receipt_sha,
                ),
                check=False,
            )
            expected_lines = [
                line.strip()
                for line in expected_tree.stdout.splitlines()
                if line.strip()
            ]
            actual_tree = self._git(
                ("rev-parse", "--verify", f"{current}^{{tree}}"),
                check=False,
            )
            if (
                expected_tree.returncode != 0
                or not expected_lines
                or FULL_SHA.fullmatch(expected_lines[0]) is None
                or actual_tree.returncode != 0
                or actual_tree.stdout.strip() != expected_lines[0]
            ):
                raise AutopilotError(
                    "publication pin merge tree differs from the canonical merge"
                )
            current = previous
        if current != transaction.get("expected_target_sha"):
            raise AutopilotError(
                "publication pin contains a foreign first-parent commit"
            )
        final_tree = self._git(
            ("rev-parse", "--verify", f"{pinned_sha}^{{tree}}"), check=False
        )
        tree = final_tree.stdout.strip()
        if final_tree.returncode != 0 or FULL_SHA.fullmatch(tree) is None:
            raise AutopilotError("publication pin final tree is unavailable")
        return tree

    def _authenticated_remote_publication_pin(
        self, transaction: Mapping[str, Any]
    ) -> str | None:
        remote_pin = self._remote_ref_sha(str(transaction["transaction_ref"]))
        if remote_pin is None:
            return None
        self._materialize_remote_evidence_ref(
            str(transaction["transaction_ref"]),
            remote_pin,
            label="prepared publication recovery evidence",
        )
        ancestors = [
            str(transaction["expected_target_sha"]),
            *[
                str(item["sha"])
                for item in transaction["receipt_heads"]
                if isinstance(item, Mapping)
            ],
        ]
        if FULL_SHA.fullmatch(remote_pin) is None or any(
            not self.is_ancestor(ancestor, remote_pin) for ancestor in ancestors
        ):
            raise AutopilotError(
                "prepared publication remote evidence lacks its sealed base or "
                "receipt ancestry"
            )
        self._assert_canonical_publication_chain(transaction, remote_pin)
        expected_identity = {
            "repository": str(transaction["repository"]),
            "target_branch": str(transaction["target_branch"]),
            "plan_fingerprint": self.expected_plan_fingerprint,
        }
        pinned_identity = self._dispatch_identity_at(remote_pin)
        if any(
            pinned_identity.get(field) != value
            for field, value in expected_identity.items()
        ):
            raise AutopilotError(
                "prepared publication remote tree changed dispatcher authority"
            )
        return remote_pin

    def _adopt_prepared_publication_pin(
        self,
        transaction: Mapping[str, Any],
        *,
        actor: str,
    ) -> Mapping[str, Any]:
        supplied = self._validated_publication_transaction(
            transaction, label="prepared publication pin token"
        )
        remote_pin = self._authenticated_remote_publication_pin(supplied)
        if remote_pin is None:
            return supplied
        with self._host_arbiter_guard():
            with self.execution_lock(
                "dispatcher-admission.lock", timeout_seconds=120.0
            ):
                _, current = self._validated_publication_resource(
                    self._strict_json_file(
                        self._publication_resource_path(),
                        label="publication target reservation",
                    ),
                    label="publication target reservation",
                )
                if any(
                    current.get(field) != supplied.get(field)
                    for field in (
                        "transaction_id",
                        "transaction_key",
                        "execution_id",
                        "release_id",
                        "coordinator_id",
                        "transaction_lease_id",
                    )
                ):
                    raise AutopilotError(
                        "prepared publication changed before remote pin adoption"
                    )
                if current.get("status") == "PINNED":
                    if current.get("pinned_sha") != remote_pin:
                        raise AutopilotError(
                            "durable publication pin differs from remote evidence"
                        )
                    self._write_publication_pair(
                        current, detail="durable publication pin evidence repaired"
                    )
                    return current
                if (
                    current.get("status") != "PREPARED"
                    or current.get("record_id") != supplied.get("record_id")
                    or parse_time(current.get("lease_expires_at")) <= self.clock()
                ):
                    raise AutopilotError(
                        "prepared publication pin token is stale"
                    )
                pinned = dict(current)
                pinned.update(
                    {
                        "status": "PINNED",
                        "pinned_sha": remote_pin,
                        "detail": (
                            "portable transaction commit sealed for fixed "
                            "revalidation"
                        ),
                        "actor": actor,
                        "updated_at": format_time(self.clock()),
                    }
                )
                pinned = self._seal_publication_record(pinned)
                self._write_publication_pair(
                    pinned,
                    detail="portable transaction commit sealed for fixed revalidation",
                )
                return pinned

    def pin_publication_transaction(
        self,
        transaction: Mapping[str, Any],
        *,
        pinned_sha: str,
        actor: str,
    ) -> Mapping[str, Any]:
        """Publish and seal clone-portable commit evidence before validation."""

        supplied = self._validated_publication_transaction(
            transaction, label="publication pin token"
        )
        if (
            supplied.get("status") not in {"PREPARED", "PINNED"}
            or FULL_SHA.fullmatch(pinned_sha) is None
            or not isinstance(actor, str)
            or not actor.strip()
            or parse_time(supplied.get("lease_expires_at")) <= self.clock()
        ):
            raise AutopilotError("publication pin authority is invalid or stale")
        transaction_ref = str(supplied["transaction_ref"])
        if supplied.get("status") == "PINNED":
            if supplied.get("pinned_sha") != pinned_sha:
                raise AutopilotError("publication pin retry changed its commit")
            self._materialize_remote_evidence_ref(
                transaction_ref,
                pinned_sha,
                label="publication transaction evidence",
            )
        self._assert_canonical_publication_chain(supplied, pinned_sha)
        if supplied.get("status") == "PREPARED":
            self._publish_remote_evidence_ref(
                transaction_ref,
                pinned_sha,
                label="publication transaction evidence",
            )
        pinned = self._adopt_prepared_publication_pin(supplied, actor=actor)
        if pinned.get("status") != "PINNED" or pinned.get("pinned_sha") != pinned_sha:
            raise AutopilotError("publication pin did not become durable authority")
        return pinned

    def _publication_test_source_manifest(
        self, commit: str, *, label: str
    ) -> tuple[list[dict[str, str]], str]:
        """Return the exact tracked test-source blob manifest at one raw commit."""

        if FULL_SHA.fullmatch(commit) is None:
            raise AutopilotError(f"{label} commit identity is invalid")
        listed = self._git(
            ("ls-tree", "-r", "-z", "--full-tree", commit, "--", "tests"),
            check=False,
        )
        if listed.returncode != 0:
            raise AutopilotError(f"{label} cannot be read from the pinned graph")
        entries: list[dict[str, str]] = []
        for raw_entry in listed.stdout.split("\0"):
            if not raw_entry:
                continue
            try:
                authority, path = raw_entry.split("\t", 1)
                mode, object_type, object_id = authority.split(" ", 2)
            except ValueError as error:
                raise AutopilotError(f"{label} contains malformed Git tree bytes") from error
            path_value = Path(path)
            if (
                object_type != "blob"
                or mode not in {"100644", "100755"}
                or FULL_SHA.fullmatch(object_id) is None
                or path_value.is_absolute()
                or ".." in path_value.parts
                or path_value.parts[:1] != ("tests",)
                or "\\" in path
            ):
                raise AutopilotError(
                    f"{label} contains a non-regular or ambiguous test source"
                )
            entries.append({"path": path_value.as_posix(), "blob": object_id})
        entries.sort(key=lambda item: item["path"])
        if len(entries) != len({item["path"] for item in entries}):
            raise AutopilotError(f"{label} contains duplicate test source paths")
        return entries, digest_json(entries)

    def _publication_governed_kernel_manifest(
        self, commit: str, *, label: str
    ) -> tuple[list[dict[str, str]], str]:
        """Seal the kernel/test sources ordinary round publication may not alter.

        Execution identity authenticates the controller that is doing the judging;
        it does not by itself prove that the candidate commit did not replace that
        controller or delete its governed Autopilot tests.  Kernel upgrades require
        their own courtroom/migration authority, which the ordinary round publisher
        intentionally does not possess.
        """

        if FULL_SHA.fullmatch(commit) is None:
            raise AutopilotError(f"{label} commit identity is invalid")
        listed = self._git(
            (
                "ls-tree",
                "-r",
                "-z",
                "--full-tree",
                commit,
                "--",
                *GOVERNED_PUBLICATION_KERNEL_PATHS,
            ),
            check=False,
        )
        if listed.returncode != 0:
            raise AutopilotError(f"{label} cannot be read from the pinned graph")
        entries: list[dict[str, str]] = []
        for raw_entry in listed.stdout.split("\0"):
            if not raw_entry:
                continue
            try:
                authority, path = raw_entry.split("\t", 1)
                mode, object_type, object_id = authority.split(" ", 2)
            except ValueError as error:
                raise AutopilotError(
                    f"{label} contains malformed Git tree bytes"
                ) from error
            normalized = path.replace("\\", "/")
            if (
                object_type != "blob"
                or mode not in {"100644", "100755"}
                or FULL_SHA.fullmatch(object_id) is None
                or normalized != path
                or not any(
                    normalized == prefix or normalized.startswith(prefix + "/")
                    for prefix in GOVERNED_PUBLICATION_KERNEL_PATHS
                )
                or "/../" in f"/{normalized}/"
                or normalized.startswith("/")
            ):
                raise AutopilotError(
                    f"{label} contains a non-regular or ambiguous kernel source"
                )
            entries.append(
                {"path": normalized, "mode": mode, "blob": object_id}
            )
        entries.sort(key=lambda item: item["path"])
        if (
            not entries
            or len(entries) != len({item["path"] for item in entries})
            or not all(
                any(
                    item["path"] == prefix
                    or item["path"].startswith(prefix + "/")
                    for item in entries
                )
                for prefix in GOVERNED_PUBLICATION_KERNEL_PATHS
            )
        ):
            raise AutopilotError(
                f"{label} is empty, duplicate, or incomplete"
            )
        return entries, digest_json(entries)

    def _assert_publication_source_policy(
        self,
        transaction: Mapping[str, Any],
        authority: Mapping[str, object],
    ) -> None:
        """Recompute the protected test and kernel policy from raw Git objects."""

        expected = str(transaction["expected_target_sha"])
        pinned = str(transaction["pinned_sha"])
        protected_tests, protected_tests_digest = (
            self._publication_test_source_manifest(
                expected, label="protected target test manifest"
            )
        )
        candidate_tests, candidate_tests_digest = (
            self._publication_test_source_manifest(
                pinned, label="candidate test manifest"
            )
        )
        protected_by_path = {
            item["path"]: item["blob"] for item in protected_tests
        }
        candidate_by_path = {
            item["path"]: item["blob"] for item in candidate_tests
        }
        protected_kernel, protected_kernel_digest = (
            self._publication_governed_kernel_manifest(
                expected, label="protected Autopilot kernel manifest"
            )
        )
        candidate_kernel, candidate_kernel_digest = (
            self._publication_governed_kernel_manifest(
                pinned, label="candidate Autopilot kernel manifest"
            )
        )
        if (
            not candidate_tests
            or any(
                candidate_by_path.get(path) != blob
                for path, blob in protected_by_path.items()
            )
            or protected_tests_digest
            != authority.get("protected_test_manifest_digest")
            or candidate_tests_digest
            != authority.get("candidate_test_manifest_digest")
            or authority.get("test_diff_policy")
            != "TARGET_TEST_BLOBS_IMMUTABLE_ADDITIONS_ALLOWED"
            or candidate_kernel != protected_kernel
            or candidate_kernel_digest != protected_kernel_digest
            or protected_kernel_digest
            != authority.get("governed_kernel_manifest_digest")
            or authority.get("kernel_diff_policy")
            != "GOVERNED_AUTOPILOT_KERNEL_EXACTLY_IMMUTABLE"
        ):
            raise AutopilotError(
                "publication source policy changed or permits an ungoverned "
                "test/kernel mutation"
            )

    def _validated_publication_validation_challenge(
        self, value: object, *, label: str
    ) -> dict[str, object]:
        if (
            not isinstance(value, Mapping)
            or set(value) != PUBLICATION_VALIDATION_CHALLENGE_FIELDS
        ):
            raise AutopilotError(f"{label} has an invalid exact schema")
        challenge = dict(value)
        material = dict(challenge)
        challenge_id = material.pop("challenge_id", None)
        digest_fields = (
            "execution_id",
            "transaction_id",
            "transaction_record_id",
            "release_id",
            "target_watermark_record_id",
            "authority_baseline_digest",
            "receipt_heads_digest",
            "protected_test_manifest_digest",
            "candidate_test_manifest_digest",
            "governed_kernel_manifest_digest",
            "capacity_generation",
            "kernel_bundle_digest",
            "interpreter_policy_digest",
            "stdlib_bundle_digest",
            "gate_identity_id",
            "sandbox_broker_identity_id",
        )
        if (
            challenge_id != digest_json(material)
            or AUTHORITY_ID.fullmatch(str(challenge_id)) is None
            or challenge.get("schema_version") != 1
            or challenge.get("kind") != PUBLICATION_VALIDATION_CHALLENGE_KIND
            or challenge.get("execution_namespace") != self.execution_namespace
            or challenge.get("execution_id") != self.execution_id
            or any(
                AUTHORITY_ID.fullmatch(str(challenge.get(field))) is None
                for field in digest_fields
            )
            or type(challenge.get("dispatcher_admission_epoch")) is not int
            or int(challenge["dispatcher_admission_epoch"]) < 1
            or type(challenge.get("target_generation")) is not int
            or int(challenge["target_generation"]) < 1
            or FULL_SHA.fullmatch(str(challenge.get("pinned_sha"))) is None
            or FULL_SHA.fullmatch(str(challenge.get("pinned_tree"))) is None
            or challenge.get("test_diff_policy")
            != "TARGET_TEST_BLOBS_IMMUTABLE_ADDITIONS_ALLOWED"
            or challenge.get("kernel_diff_policy")
            != "GOVERNED_AUTOPILOT_KERNEL_EXACTLY_IMMUTABLE"
            or not isinstance(challenge.get("host_id"), str)
            or not str(challenge["host_id"]).strip()
            or not isinstance(challenge.get("issued_by"), str)
            or not str(challenge["issued_by"]).strip()
        ):
            raise AutopilotError(f"{label} authority binding is invalid")
        try:
            issued_at = parse_time(challenge.get("issued_at"))
            expires_at = parse_time(challenge.get("expires_at"))
        except Exception as error:
            raise AutopilotError(f"{label} timestamps are malformed") from error
        if expires_at <= issued_at:
            raise AutopilotError(f"{label} lifetime is invalid")
        return challenge

    def _validated_publication_validation_completion(
        self, value: object, *, label: str
    ) -> dict[str, object]:
        if (
            not isinstance(value, Mapping)
            or set(value) != PUBLICATION_VALIDATION_COMPLETION_FIELDS
        ):
            raise AutopilotError(f"{label} has an invalid exact schema")
        completion = dict(value)
        material = dict(completion)
        completion_id = material.pop("completion_id", None)
        if (
            completion_id != digest_json(material)
            or AUTHORITY_ID.fullmatch(str(completion_id)) is None
            or completion.get("schema_version") != 1
            or completion.get("kind") != PUBLICATION_VALIDATION_COMPLETION_KIND
            or completion.get("execution_namespace") != self.execution_namespace
            or completion.get("execution_id") != self.execution_id
            or any(
                AUTHORITY_ID.fullmatch(str(completion.get(field))) is None
                for field in (
                    "challenge_id",
                    "challenge_record_id",
                    "transaction_id",
                    "transaction_record_id",
                    "kernel_bundle_digest",
                    "interpreter_policy_digest",
                    "stdlib_bundle_digest",
                    "gate_identity_id",
                    "sandbox_broker_identity_id",
                )
            )
            or FULL_SHA.fullmatch(str(completion.get("pinned_sha"))) is None
            or not isinstance(completion.get("lease"), Mapping)
            or not isinstance(completion.get("cleanup"), Mapping)
            or not isinstance(completion.get("gate"), Mapping)
            or not isinstance(completion.get("completed_by"), str)
            or not str(completion["completed_by"]).strip()
        ):
            raise AutopilotError(f"{label} authority binding is invalid")
        try:
            parse_time(completion.get("completed_at"))
        except Exception as error:
            raise AutopilotError(f"{label} completion time is malformed") from error
        return completion

    def _publication_validation_challenge(
        self,
        transaction: Mapping[str, Any],
        *,
        pinned_sha: str,
        actor: str,
    ) -> Mapping[str, object]:
        """Create/adopt the immutable broker capability for one exact pin."""

        path = self._publication_validation_challenge_path(
            str(transaction["transaction_id"])
        )
        if path.is_file():
            value = self._validated_publication_validation_challenge(
                self._strict_json_file(
                    path, label="publication validation challenge"
                ),
                label="publication validation challenge",
            )
            if (
                value.get("transaction_id") != transaction.get("transaction_id")
                or value.get("pinned_sha") != pinned_sha
                or not self._publication_pin_descends_challenge(
                    value, transaction
                )
            ):
                raise AutopilotError(
                    "publication validation challenge conflicts with the pin"
                )
            return dict(value)

        with self._host_arbiter_guard():
            with self.execution_lock(
                "dispatcher-admission.lock", timeout_seconds=120.0
            ):
                _, current = self._validated_publication_resource(
                    self._strict_json_file(
                        self._publication_resource_path(),
                        label="publication target reservation",
                    ),
                    label="publication target reservation",
                )
                if (
                    current.get("status") != "PINNED"
                    or current.get("record_id") != transaction.get("record_id")
                    or current.get("pinned_sha") != pinned_sha
                    or parse_time(current.get("lease_expires_at")) <= self.clock()
                ):
                    raise AutopilotError(
                        "publication validation challenge requires the exact live PINNED record"
                    )
                if path.is_file():
                    existing = self._validated_publication_validation_challenge(
                        self._strict_json_file(
                            path, label="publication validation challenge"
                        ),
                        label="publication validation challenge",
                    )
                    if (
                        existing.get("transaction_id")
                        != current.get("transaction_id")
                        or existing.get("pinned_sha") != pinned_sha
                        or not self._publication_pin_descends_challenge(
                            existing, current
                        )
                    ):
                        raise AutopilotError(
                            "publication validation challenge conflicts with the pin"
                        )
                    return existing
                release = self.current_release()
                issues = self._release_issues(release)
                if issues or not isinstance(release, Mapping):
                    raise AutopilotError(
                        "publication validation challenge lacks a live release: "
                        + "; ".join(issues)
                    )
                pinned_tree = self._assert_canonical_publication_chain(
                    current, pinned_sha
                )
                protected_tests, protected_tests_digest = (
                    self._publication_test_source_manifest(
                        str(current["expected_target_sha"]),
                        label="protected target test manifest",
                    )
                )
                candidate_tests, candidate_tests_digest = (
                    self._publication_test_source_manifest(
                        pinned_sha,
                        label="candidate test manifest",
                    )
                )
                protected_kernel, protected_kernel_digest = (
                    self._publication_governed_kernel_manifest(
                        str(current["expected_target_sha"]),
                        label="protected Autopilot kernel manifest",
                    )
                )
                candidate_kernel, candidate_kernel_digest = (
                    self._publication_governed_kernel_manifest(
                        pinned_sha,
                        label="candidate Autopilot kernel manifest",
                    )
                )
                protected_by_path = {
                    item["path"]: item["blob"] for item in protected_tests
                }
                candidate_by_path = {
                    item["path"]: item["blob"] for item in candidate_tests
                }
                if not candidate_tests or any(
                    candidate_by_path.get(path) != blob
                    for path, blob in protected_by_path.items()
                ):
                    raise AutopilotError(
                        "publication validation test policy forbids deleting or "
                        "rewriting target tests; only additive test sources are allowed"
                    )
                if (
                    candidate_kernel != protected_kernel
                    or candidate_kernel_digest != protected_kernel_digest
                ):
                    raise AutopilotError(
                        "ordinary publication cannot alter the governed Autopilot "
                        "kernel or its protected tests; use the explicit kernel "
                        "court/migration path"
                    )
                kernel = runtime_kernel_identity(self.repo_root)
                stdlib_bundle = self._publication_stdlib_bundle_identity()
                gate_identity = self.publication_validation_gate_identity()
                issued_at = format_time(self.clock())
                material: dict[str, object] = {
                    "schema_version": 1,
                    "kind": PUBLICATION_VALIDATION_CHALLENGE_KIND,
                    "execution_namespace": self.execution_namespace,
                    "execution_id": self.execution_id,
                    "transaction_id": current["transaction_id"],
                    "transaction_record_id": current["record_id"],
                    "release_id": current["release_id"],
                    "dispatcher_admission_epoch": release["admission_epoch"],
                    "target_generation": release["target_generation"],
                    "target_watermark_record_id": release[
                        "target_watermark_record_id"
                    ],
                    "authority_baseline_digest": current[
                        "authority_baseline_digest"
                    ],
                    "receipt_heads_digest": current["receipt_heads_digest"],
                    "pinned_sha": pinned_sha,
                    "pinned_tree": pinned_tree,
                    "protected_test_manifest_digest": protected_tests_digest,
                    "candidate_test_manifest_digest": candidate_tests_digest,
                    "test_diff_policy": "TARGET_TEST_BLOBS_IMMUTABLE_ADDITIONS_ALLOWED",
                    "governed_kernel_manifest_digest": protected_kernel_digest,
                    "kernel_diff_policy": (
                        "GOVERNED_AUTOPILOT_KERNEL_EXACTLY_IMMUTABLE"
                    ),
                    "host_id": release["host_id"],
                    "capacity_generation": release["capacity_generation"],
                    "kernel_bundle_digest": kernel["bundle_digest"],
                    "interpreter_policy_digest": kernel[
                        "interpreter_policy_digest"
                    ],
                    "stdlib_bundle_digest": stdlib_bundle["bundle_digest"],
                    "gate_identity_id": gate_identity["identity_id"],
                    "sandbox_broker_identity_id": gate_identity[
                        "sandbox_broker_identity_id"
                    ],
                    "issued_by": actor,
                    "issued_at": issued_at,
                    "expires_at": current["lease_expires_at"],
                }
                challenge = {**material, "challenge_id": digest_json(material)}
                challenge = self._validated_publication_validation_challenge(
                    challenge, label="new publication validation challenge"
                )
                self._write_immutable_json(path, challenge)
                return challenge

    def _publication_pin_descends_challenge(
        self,
        challenge: Mapping[str, object],
        current: Mapping[str, Any],
    ) -> bool:
        """Prove all post-challenge transitions were lease-only PINNED renewals."""

        if (
            challenge.get("transaction_id") != current.get("transaction_id")
            or challenge.get("pinned_sha") != current.get("pinned_sha")
            or current.get("status") != "PINNED"
        ):
            return False
        events = self._publication_journal_events()
        selected_events = [
            event
            for event in events
            if event.get("transaction_id") == current.get("transaction_id")
        ]
        records: list[Mapping[str, Any]] = []
        for event in selected_events:
            nested = event.get("transaction")
            if not isinstance(nested, Mapping):
                return False
            record = self._validated_publication_transaction(
                nested, label="publication challenge renewal lineage"
            )
            if event.get("transaction_record_id") != record.get("record_id"):
                return False
            records.append(record)
        start = next(
            (
                index
                for index, event in enumerate(records)
                if event.get("record_id")
                == challenge.get("transaction_record_id")
            ),
            None,
        )
        end = next(
            (
                index
                for index, event in enumerate(records)
                if event.get("record_id") == current.get("record_id")
            ),
            None,
        )
        if start is None or end is None or end < start:
            return False
        lineage = records[start : end + 1]
        stable_fields = (
            "transaction_id",
            "transaction_key",
            "transaction_lease_id",
            "release_id",
            "expected_target_sha",
            "receipt_heads_digest",
            "authority_baseline_digest",
            "pinned_sha",
        )
        return bool(
            lineage
            and all(event.get("status") == "PINNED" for event in lineage)
            and all(
                all(event.get(field) == lineage[0].get(field) for field in stable_fields)
                for event in lineage
            )
            and all(
                self._publication_transition_allowed(previous, successor)
                for previous, successor in zip(lineage, lineage[1:])
            )
        )

    @staticmethod
    def _isolated_validation_environment(sandbox: Path) -> Mapping[str, str]:
        allowed = {
            "PATH",
            "PATHEXT",
            "SYSTEMROOT",
            "WINDIR",
            "COMSPEC",
            "NUMBER_OF_PROCESSORS",
            "PROCESSOR_ARCHITECTURE",
            "LANG",
            "LC_ALL",
        }
        environment = {
            key: value for key, value in os.environ.items() if key.upper() in allowed
        }
        home = sandbox / ".validation-home"
        temporary = sandbox / ".validation-tmp"
        home.mkdir(mode=0o700)
        temporary.mkdir(mode=0o700)
        environment.update(
            {
                "HOME": str(home),
                "USERPROFILE": str(home),
                "TEMP": str(temporary),
                "TMP": str(temporary),
                "GIT_NO_REPLACE_OBJECTS": "1",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_TERMINAL_PROMPT": "0",
                "GCM_INTERACTIVE": "Never",
                "PYTHONNOUSERSITE": "1",
            }
        )
        return environment

    def _run_isolated_publication_gate(
        self,
        transaction: Mapping[str, Any],
        challenge: Mapping[str, object],
    ) -> Mapping[str, object]:
        """Run the fixed gate in a credentialless standalone Git object store."""

        sandbox_broker = self._publication_sandbox_broker_identity()
        if (
            sandbox_broker.get("identity_id")
            != challenge.get("sandbox_broker_identity_id")
            or sandbox_broker.get("network_isolation_verified") is not True
            or not isinstance(
                sandbox_broker.get("network_isolation_attestation"), Mapping
            )
        ):
            raise AutopilotError(
                "publication validation is blocked: the installed sandbox broker "
                "does not provide independently attestable network denial"
            )

        with tempfile.TemporaryDirectory(
            prefix="hive-mind-publication-validation-"
        ) as temporary_text:
            temporary = Path(temporary_text).resolve()
            bundle = temporary / "authority.bundle"
            sandbox = temporary / "worktree"
            bundled = self._git(
                ("bundle", "create", str(bundle), "--all"), check=False
            )
            if bundled.returncode != 0:
                raise AutopilotError(
                    "publication broker could not isolate Git objects"
                )
            cloned = self._git(
                ("clone", "--no-checkout", str(bundle), str(sandbox)),
                check=False,
            )
            if cloned.returncode != 0:
                raise AutopilotError(
                    "publication broker could not create its isolated clone"
                )
            removed = self._git(
                ("-C", str(sandbox), "remote", "remove", "origin"),
                check=False,
            )
            if removed.returncode not in {0, 2}:
                raise AutopilotError(
                    "publication broker could not remove sandbox transport"
                )
            bundle.unlink(missing_ok=True)
            checkout = self._git(
                (
                    "-C",
                    str(sandbox),
                    "checkout",
                    "--detach",
                    str(challenge["pinned_sha"]),
                ),
                check=False,
            )
            if checkout.returncode != 0:
                raise AutopilotError(
                    "publication broker could not materialize the pinned commit"
                )
            transaction_ref = str(transaction["transaction_ref"])
            installed_ref = self._git(
                (
                    "-C",
                    str(sandbox),
                    "update-ref",
                    transaction_ref,
                    str(challenge["pinned_sha"]),
                    "0" * 40,
                ),
                check=False,
            )
            if installed_ref.returncode != 0:
                raise AutopilotError(
                    "publication broker could not install its isolated pin"
                )
            remotes = self._git(
                ("-C", str(sandbox), "remote"), check=False
            )
            alternates = sandbox / ".git" / "objects" / "info" / "alternates"
            if (
                remotes.returncode != 0
                or remotes.stdout.strip()
                or alternates.exists()
                or self._is_link_like(alternates)
                or (sandbox / ".git" / "info" / "grafts").exists()
            ):
                raise AutopilotError(
                    "publication validation sandbox retained transport or shared objects"
                )
            environment = dict(
                self._isolated_validation_environment(temporary)
            )
            identity = self.publication_validation_gate_identity()
            interpreter = Path(str(identity["interpreter_path"]))
            git_executable = Path(str(identity["git_executable_path"]))
            driver = Path(str(identity["round_driver_path"]))
            argv = [
                str(interpreter),
                "-I",
                "-S",
                "-B",
                "-c",
                PUBLICATION_BROKER_GATE_HARNESS,
                str(sandbox),
            ]
            interpreter_before = "sha256:" + sha256(
                interpreter.read_bytes()
            ).hexdigest()
            git_before = "sha256:" + sha256(git_executable.read_bytes()).hexdigest()
            driver_before = "sha256:" + sha256(driver.read_bytes()).hexdigest()
            tree_before = self._git(
                ("-C", str(sandbox), "rev-parse", "HEAD^{tree}"), check=True
            ).stdout.strip()
            started_at = format_time(self.clock())
            broker_argv = [
                str(sandbox_broker["executable_path"]),
                "sandbox",
                "-P",
                str(sandbox_broker["permission_profile"]),
                "--sandbox-state-disable-network",
                "-C",
                str(sandbox),
                "--",
                *argv,
            ]
            completed = subprocess.run(
                broker_argv,
                cwd=sandbox,
                capture_output=True,
                env=environment,
                timeout=3600,
            )
            completed_at = format_time(self.clock())
            interpreter_after = "sha256:" + sha256(
                interpreter.read_bytes()
            ).hexdigest()
            git_after = "sha256:" + sha256(git_executable.read_bytes()).hexdigest()
            driver_after = "sha256:" + sha256(driver.read_bytes()).hexdigest()
            tree_after = self._git(
                ("-C", str(sandbox), "rev-parse", "HEAD^{tree}"), check=True
            ).stdout.strip()
            head_after = self._git(
                ("-C", str(sandbox), "rev-parse", "HEAD"), check=True
            ).stdout.strip()
            ref_after = self._git(
                (
                    "-C",
                    str(sandbox),
                    "rev-parse",
                    transaction_ref,
                ),
                check=True,
            ).stdout.strip()
            status_after = self._git(
                (
                    "-C",
                    str(sandbox),
                    "status",
                    "--porcelain=v1",
                    "--untracked-files=all",
                ),
                check=True,
            ).stdout
            if (
                tree_before != tree_after
                or tree_after != challenge.get("pinned_tree")
                or head_after != challenge.get("pinned_sha")
                or ref_after != challenge.get("pinned_sha")
                or interpreter_before != interpreter_after
                or git_before != git_after
                or driver_before != driver_after
            ):
                raise AutopilotError(
                    "publication broker sandbox authority changed during validation"
                )
            stdout = bytes(completed.stdout or b"")
            stderr = bytes(completed.stderr or b"")
            output_text = (stdout + b"\n" + stderr).decode(
                "utf-8", errors="replace"
            )
            marker_lines = [
                line.removeprefix(PUBLICATION_BROKER_GATE_MARKER)
                for line in output_text.splitlines()
                if line.startswith(PUBLICATION_BROKER_GATE_MARKER)
            ]
            if len(marker_lines) != 1:
                raise AutopilotError(
                    "publication broker gate omitted its exact test manifest"
                )
            raw_counts = json.loads(marker_lines[0])
            if not isinstance(raw_counts, Mapping):
                raise AutopilotError(
                    "publication broker gate returned malformed test counts"
                )
            test_manifest_digest = raw_counts.get("manifest_digest")
            test_source_manifest_digest = raw_counts.get(
                "source_manifest_digest"
            )
            test_counts = {
                key: value
                for key, value in raw_counts.items()
                if key not in {"manifest_digest", "source_manifest_digest"}
            }
            lines = [
                line
                for line in output_text.strip().splitlines()
                if not line.startswith(PUBLICATION_BROKER_GATE_MARKER)
            ]
            gate_result = {
                "schema_version": 1,
                "kind": "hive-mind-fixed-publication-gate-result-v1",
                "argv": argv,
                "interpreter_path": str(interpreter),
                "interpreter_digest_before": interpreter_before,
                "interpreter_digest_after": interpreter_after,
                "git_executable_path": str(git_executable),
                "git_executable_digest_before": git_before,
                "git_executable_digest_after": git_after,
                "round_driver_path": str(driver),
                "round_driver_digest_before": driver_before,
                "round_driver_digest_after": driver_after,
                "worktree_tree": tree_before,
                "worktree_head_after": head_after,
                "transaction_ref_after": ref_after,
                "worktree_status_porcelain": status_after,
                "environment_policy_digest": identity[
                    "environment_policy_digest"
                ],
                "started_at": started_at,
                "completed_at": completed_at,
                "exit_code": int(completed.returncode),
                "output_digest": "sha256:"
                + sha256(stdout + b"\x00" + stderr).hexdigest(),
                "summary": lines[-1] if lines else "no test output",
                "test_manifest_digest": test_manifest_digest,
                "test_source_manifest_digest": test_source_manifest_digest,
                "test_counts": test_counts,
                "sandbox_broker_identity_id": sandbox_broker["identity_id"],
                "stdlib_bundle_digest": challenge["stdlib_bundle_digest"],
            }
            validated_gate = self._validated_publication_gate(
                gate_result, label="publication broker fixed gate result"
            )
            if (
                validated_gate.get("test_source_manifest_digest")
                != challenge.get("candidate_test_manifest_digest")
            ):
                raise AutopilotError(
                    "publication broker executed a test source manifest that "
                    "differs from the sealed candidate"
                )
            return validated_gate

    def run_publication_validation_broker(
        self,
        transaction: Mapping[str, Any],
        *,
        pinned_sha: str,
        actor: str,
        lease_minutes: int = 60,
    ) -> Mapping[str, object]:
        """Run/adopt the only gate artifact accepted by VALIDATED sealing."""

        supplied = self._validated_publication_transaction(
            transaction, label="publication broker token"
        )
        if (
            supplied.get("status") != "PINNED"
            or supplied.get("pinned_sha") != pinned_sha
            or type(lease_minutes) is not int
            or lease_minutes < 1
            or not actor.strip()
        ):
            raise AutopilotError("publication broker requires a live exact PINNED token")
        challenge = self._publication_validation_challenge(
            supplied, pinned_sha=pinned_sha, actor=actor
        )
        with self._host_arbiter_guard():
            with self.execution_lock(
                "dispatcher-admission.lock", timeout_seconds=120.0
            ):
                _, live_pin = self._validated_publication_resource(
                    self._strict_json_file(
                        self._publication_resource_path(),
                        label="publication target reservation",
                    ),
                    label="publication target reservation",
                )
                if (
                    live_pin.get("status") != "PINNED"
                    or live_pin.get("transaction_id")
                    != supplied.get("transaction_id")
                    or live_pin.get("pinned_sha") != pinned_sha
                    or parse_time(live_pin.get("lease_expires_at")) <= self.clock()
                    or not self._publication_pin_descends_challenge(
                        challenge, live_pin
                    )
                ):
                    raise AutopilotError(
                        "publication broker challenge no longer has a live PINNED lineage"
                    )
                supplied = live_pin
        gate_identity = self.publication_validation_gate_identity()
        stdlib_bundle = self._publication_stdlib_bundle_identity()
        if (
            challenge.get("gate_identity_id") != gate_identity.get("identity_id")
            or challenge.get("sandbox_broker_identity_id")
            != gate_identity.get("sandbox_broker_identity_id")
            or challenge.get("stdlib_bundle_digest")
            != stdlib_bundle.get("bundle_digest")
        ):
            raise AutopilotError(
                "publication validation challenge kernel or broker identity changed"
            )
        completion_path = self._publication_validation_completion_path(
            str(challenge["challenge_id"])
        )
        if completion_path.is_file():
            completion = self._validated_publication_validation_completion(
                self._strict_json_file(
                    completion_path,
                    label="publication validation broker completion",
                ),
                label="publication validation broker completion",
            )
            if (
                completion.get("challenge_id") != challenge.get("challenge_id")
                or completion.get("challenge_record_id")
                != challenge.get("challenge_id")
                or completion.get("transaction_record_id")
                != challenge.get("transaction_record_id")
            ):
                raise AutopilotError(
                    "publication validation broker completion conflicts"
                )
            return dict(completion)

        release = self.current_release()
        if not isinstance(release, Mapping):
            raise AutopilotError("publication broker release is unavailable")
        wave = release.get("released_wave")
        if not isinstance(wave, list) or not wave:
            raise AutopilotError("publication broker release has no validation anchor")
        anchor = str(wave[0])
        lease = self.acquire_keyed_validation_lease_internal(
            anchor,
            actor,
            host_id=str(release["host_id"]),
            release_id=str(release["release_id"]),
            transaction_sha=pinned_sha,
            lease_minutes=lease_minutes,
        )
        stop = threading.Event()
        renewal_errors: list[BaseException] = []

        def renew() -> None:
            interval = max(1.0, min(30.0, lease_minutes * 20.0))
            while not stop.wait(interval):
                try:
                    self.renew_keyed_validation_lease_internal(
                        anchor,
                        actor,
                        lease_id=str(lease["lease_id"]),
                        host_id=str(release["host_id"]),
                        release_id=str(release["release_id"]),
                        transaction_sha=pinned_sha,
                        lease_minutes=lease_minutes,
                    )
                except BaseException as error:
                    renewal_errors.append(error)
                    stop.set()

        renewer = threading.Thread(
            target=renew,
            name=f"publication-validation-broker:{anchor}",
            daemon=True,
        )
        renewer.start()
        gate: Mapping[str, object] | None = None
        gate_error: BaseException | None = None
        cleanup: Mapping[str, object] | None = None
        try:
            gate = self._run_isolated_publication_gate(supplied, challenge)
        except BaseException as error:
            gate_error = error
        finally:
            stop.set()
            renewer.join(timeout=35.0)
            try:
                cleanup = self.release_keyed_validation_lease_internal(
                    anchor,
                    actor,
                    lease_id=str(lease["lease_id"]),
                    host_id=str(release["host_id"]),
                    release_id=str(release["release_id"]),
                    transaction_sha=pinned_sha,
                )
            except BaseException as error:
                if gate_error is None:
                    gate_error = error
        if renewer.is_alive() or renewal_errors or gate_error is not None:
            detail = gate_error
            if detail is None and renewal_errors:
                detail = renewal_errors[0]
            raise AutopilotError(
                "publication validation broker did not settle exactly"
                + (f": {detail}" if detail is not None else "")
            )
        assert gate is not None and cleanup is not None
        completion_material: dict[str, object] = {
            "schema_version": 1,
            "kind": PUBLICATION_VALIDATION_COMPLETION_KIND,
            "execution_namespace": self.execution_namespace,
            "execution_id": self.execution_id,
            "challenge_id": challenge["challenge_id"],
            "challenge_record_id": challenge["challenge_id"],
            "transaction_id": supplied["transaction_id"],
            "transaction_record_id": challenge["transaction_record_id"],
            "pinned_sha": pinned_sha,
            "kernel_bundle_digest": challenge["kernel_bundle_digest"],
            "interpreter_policy_digest": challenge[
                "interpreter_policy_digest"
            ],
            "stdlib_bundle_digest": challenge["stdlib_bundle_digest"],
            "gate_identity_id": challenge["gate_identity_id"],
            "sandbox_broker_identity_id": challenge[
                "sandbox_broker_identity_id"
            ],
            "lease": dict(lease),
            "cleanup": dict(cleanup),
            "gate": dict(gate),
            "completed_by": actor,
            "completed_at": format_time(self.clock()),
        }
        completion = {
            **completion_material,
            "completion_id": digest_json(completion_material),
        }
        completion = self._validated_publication_validation_completion(
            completion, label="new publication validation broker completion"
        )
        self._write_immutable_json(completion_path, completion)
        return completion

    def seal_validated_publication_transaction(
        self,
        transaction: Mapping[str, Any],
        *,
        pinned_sha: str,
        validation_evidence: Mapping[str, object],
        actor: str,
    ) -> Mapping[str, Any]:
        """Mint VALIDATED only from the exact fixed gate and released permits."""

        supplied = self._validated_publication_transaction(
            transaction, label="publication validation token"
        )
        if (
            supplied.get("status") != "PINNED"
            or supplied.get("pinned_sha") != pinned_sha
            or not isinstance(validation_evidence, Mapping)
            or set(validation_evidence) != {"broker_completion_id"}
            or AUTHORITY_ID.fullmatch(
                str(validation_evidence.get("broker_completion_id"))
            )
            is None
            or not isinstance(actor, str)
            or not actor.strip()
        ):
            raise AutopilotError("publication validation authority is invalid or stale")
        challenge = self._validated_publication_validation_challenge(
            self._strict_json_file(
                self._publication_validation_challenge_path(
                    str(supplied["transaction_id"])
                ),
                label="publication validation challenge",
            ),
            label="publication validation challenge",
        )
        challenge_id = challenge["challenge_id"]
        if (
            challenge.get("transaction_id") != supplied.get("transaction_id")
            or challenge.get("pinned_sha") != pinned_sha
            or not self._publication_pin_descends_challenge(challenge, supplied)
        ):
            raise AutopilotError("publication validation challenge is not current")
        completion = self._validated_publication_validation_completion(
            self._strict_json_file(
                self._publication_validation_completion_path(str(challenge_id)),
                label="publication validation broker completion",
            ),
            label="publication validation broker completion",
        )
        completion_id = completion["completion_id"]
        if (
            completion_id != validation_evidence.get("broker_completion_id")
            or completion.get("challenge_id") != challenge_id
            or completion.get("challenge_record_id") != challenge_id
            or completion.get("transaction_id") != supplied.get("transaction_id")
            or completion.get("transaction_record_id")
            != challenge.get("transaction_record_id")
            or completion.get("pinned_sha") != pinned_sha
        ):
            raise AutopilotError(
                "publication validation broker completion is not current"
            )
        kernel = runtime_kernel_identity(self.repo_root)
        stdlib_bundle = self._publication_stdlib_bundle_identity()
        gate_identity = self.publication_validation_gate_identity()
        sandbox_broker = self._publication_sandbox_broker_identity()
        if (
            challenge.get("kernel_bundle_digest") != kernel.get("bundle_digest")
            or challenge.get("interpreter_policy_digest")
            != kernel.get("interpreter_policy_digest")
            or completion.get("kernel_bundle_digest") != kernel.get("bundle_digest")
            or completion.get("interpreter_policy_digest")
            != kernel.get("interpreter_policy_digest")
            or challenge.get("stdlib_bundle_digest")
            != stdlib_bundle.get("bundle_digest")
            or completion.get("stdlib_bundle_digest")
            != stdlib_bundle.get("bundle_digest")
            or challenge.get("gate_identity_id") != gate_identity.get("identity_id")
            or completion.get("gate_identity_id") != gate_identity.get("identity_id")
            or challenge.get("sandbox_broker_identity_id")
            != gate_identity.get("sandbox_broker_identity_id")
            or completion.get("sandbox_broker_identity_id")
            != gate_identity.get("sandbox_broker_identity_id")
            or sandbox_broker.get("identity_id")
            != gate_identity.get("sandbox_broker_identity_id")
            or sandbox_broker.get("network_isolation_verified") is not True
            or not isinstance(
                sandbox_broker.get("network_isolation_attestation"), Mapping
            )
        ):
            raise AutopilotError(
                "publication validation broker kernel/network authority changed "
                "or is unavailable"
            )
        gate = self._validated_publication_gate(
            completion.get("gate"), label="publication fixed gate result"
        )
        if not self._publication_gate_matches_identity(gate, gate_identity):
            raise AutopilotError(
                "publication gate code/interpreter differs from fixed authority"
            )
        self._materialize_remote_evidence_ref(
            str(supplied["transaction_ref"]),
            pinned_sha,
            label="publication transaction evidence",
        )
        pinned_tree = self._assert_canonical_publication_chain(supplied, pinned_sha)
        self._assert_publication_source_policy(supplied, challenge)
        if (
            gate.get("worktree_tree") != pinned_tree
            or gate.get("worktree_head_after") != pinned_sha
            or gate.get("transaction_ref_after") != pinned_sha
            or gate.get("test_source_manifest_digest")
            != challenge.get("candidate_test_manifest_digest")
        ):
            raise AutopilotError(
                "publication fixed gate did not finish on the exact pinned tree/ref"
            )
        lease = completion.get("lease")
        cleanup = completion.get("cleanup")
        if not isinstance(lease, Mapping) or not isinstance(cleanup, Mapping):
            raise AutopilotError("publication validation lease evidence is absent")
        host_reservation = cleanup.get("host_reservation")
        if not isinstance(host_reservation, Mapping):
            raise AutopilotError(
                "publication validation host reservation evidence is absent"
            )
        lease_id = lease.get("lease_id")
        if not isinstance(lease_id, str) or AUTHORITY_ID.fullmatch(lease_id) is None:
            raise AutopilotError("publication validation lease id is invalid")
        archive_path = self.coordination_dir / "validation-leases" / (
            lease_id.replace(":", "-") + ".json"
        )
        if (
            not archive_path.is_file()
            or self._is_link_like(archive_path)
            or self._is_link_like(archive_path.parent)
        ):
            raise AutopilotError(
                "publication validation released-lease archive is unavailable"
            )
        released_lease = self._strict_json_file(
            archive_path, label="publication validation released-lease archive"
        )
        if not isinstance(released_lease, Mapping):
            raise AutopilotError(
                "publication validation released-lease archive is malformed"
            )
        with self._host_arbiter_guard():
            with self.execution_lock(
                "dispatcher-admission.lock", timeout_seconds=120.0
            ):
                _, current = self._validated_publication_resource(
                    self._strict_json_file(
                        self._publication_resource_path(),
                        label="publication target reservation",
                    ),
                    label="publication target reservation",
                )
                if (
                    current.get("transaction_id") != supplied.get("transaction_id")
                    or current.get("status") != "PINNED"
                    or current.get("pinned_sha") != pinned_sha
                    or parse_time(current.get("lease_expires_at")) <= self.clock()
                    or not self._publication_pin_descends_challenge(
                        challenge, current
                    )
                ):
                    raise AutopilotError(
                        "publication validation token changed before sealing"
                    )
                release = self.current_release()
                release_issues = self._release_issues(release)
                if release_issues or not isinstance(release, Mapping):
                    raise AutopilotError(
                        "publication validation requires the exact live release: "
                        + "; ".join(release_issues)
                    )
                if (
                    release.get("release_id") != current.get("release_id")
                    or release.get("target_sha")
                    != current.get("expected_target_sha")
                    or type(release.get("admission_epoch")) is not int
                    or int(release["admission_epoch"]) < 1
                    or not isinstance(release.get("host_id"), str)
                    or AUTHORITY_ID.fullmatch(
                        str(release.get("capacity_generation"))
                    )
                    is None
                ):
                    raise AutopilotError(
                        "publication validation release authority changed"
                    )
                live_capacity = reconcile_pending_host_capacity_renewal(
                    self.host_runtime_dir,
                    host_id=str(release["host_id"]),
                    now=self.clock(),
                )
                self._release_capacity_issuance_unlocked(release)
                if (
                    live_capacity.get("provider_generation")
                    != host_reservation.get("provider_generation")
                    or live_capacity.get("provider_epoch")
                    != host_reservation.get("provider_epoch")
                    or live_capacity.get("capacity_generation")
                    != host_reservation.get("capacity_generation")
                ):
                    raise AutopilotError(
                        "publication validation host provider/capacity rotated "
                        "before the gate capability was sealed"
                    )
                authority = self.round_authority_snapshot(str(current["release_id"]))
                _, authority_baseline = self._round_authority_digests(
                    authority, release_id=str(current["release_id"])
                )
                if authority_baseline != current.get("authority_baseline_digest"):
                    raise AutopilotError(
                        "publication round authority changed during fixed validation"
                    )
                if self.publication_validation_gate_identity() != gate_identity:
                    raise AutopilotError(
                        "publication gate code/interpreter changed before sealing"
                    )
                current_tree = self._assert_canonical_publication_chain(
                    current, pinned_sha
                )
                if current_tree != pinned_tree:
                    raise AutopilotError(
                        "publication pin changed after the fixed gate"
                    )
                evidence: dict[str, object] = {
                    "schema_version": 1,
                    "kind": "hive-mind-fixed-publication-validation-v1",
                    "execution_namespace": self.execution_namespace,
                    "execution_id": self.execution_id,
                    "transaction_id": current["transaction_id"],
                    "transaction_record_id": current["record_id"],
                    "release_id": current["release_id"],
                    "dispatcher_admission_epoch": int(release["admission_epoch"]),
                    "authority_digest": current["authority_digest"],
                    "authority_baseline_digest": current[
                        "authority_baseline_digest"
                    ],
                    "receipt_heads_digest": current["receipt_heads_digest"],
                    "pinned_sha": pinned_sha,
                    "pinned_tree": pinned_tree,
                    "protected_test_manifest_digest": challenge[
                        "protected_test_manifest_digest"
                    ],
                    "candidate_test_manifest_digest": challenge[
                        "candidate_test_manifest_digest"
                    ],
                    "test_diff_policy": challenge["test_diff_policy"],
                    "governed_kernel_manifest_digest": challenge[
                        "governed_kernel_manifest_digest"
                    ],
                    "kernel_diff_policy": challenge["kernel_diff_policy"],
                    "host_id": str(release["host_id"]),
                    "capacity_generation": str(release["capacity_generation"]),
                    "lease": dict(lease),
                    "released_lease": dict(released_lease),
                    "cleanup": dict(cleanup),
                    "gate": dict(gate),
                    "broker_completion_id": completion_id,
                }
                evidence["evidence_id"] = digest_json(evidence)
                candidate = dict(current)
                candidate.update(
                    {
                        "status": "VALIDATED",
                        "validation_evidence": evidence,
                        "detail": "fixed publication gate capability sealed",
                        "actor": actor,
                        "updated_at": format_time(self.clock()),
                    }
                )
                candidate = self._seal_publication_record(candidate)
                self._validated_publication_transaction(
                    candidate, label="validated publication transaction"
                )
                self._write_publication_pair(
                    candidate, detail="fixed publication gate capability sealed"
                )
                return candidate

    @contextmanager
    def publication_recovery_guard(
        self,
        transaction: Mapping[str, Any],
        *,
        coordinator_id: str,
        adopt_remote_pin: bool = True,
    ):
        """Authorize one exact PREPARED/PINNED private-round crash resume."""

        supplied = self._validated_publication_transaction(
            transaction, label="publication recovery token"
        )
        if (
            supplied.get("status") not in {"PREPARED", "PINNED"}
            or supplied.get("coordinator_id") != coordinator_id
            or parse_time(supplied.get("lease_expires_at")) <= self.clock()
        ):
            raise AutopilotError(
                "publication recovery token is not a live PREPARED/PINNED lease"
            )
        if supplied.get("status") == "PREPARED":
            if adopt_remote_pin:
                supplied = dict(
                    self._adopt_prepared_publication_pin(
                        supplied, actor=coordinator_id
                    )
                )
            elif self._remote_ref_sha(str(supplied["transaction_ref"])) is not None:
                raise AutopilotError(
                    "new PREPARED publication unexpectedly collides with remote "
                    "transaction evidence"
                )
        prior = getattr(self, "_publication_recovery_authority", None)
        self._publication_recovery_authority = {
            "transaction_id": supplied["transaction_id"],
            "transaction_key": supplied["transaction_key"],
            "transaction_lease_id": supplied["transaction_lease_id"],
            "coordinator_id": coordinator_id,
        }
        try:
            yield supplied
        finally:
            self._publication_recovery_authority = prior

    def round_authority_snapshot(self, release_id: str) -> Mapping[str, object]:
        """Expose a fenced PREPARED transaction only to its exact crash resumer."""

        snapshot = dict(super().round_authority_snapshot(release_id))
        recovery = getattr(self, "_publication_recovery_authority", None)
        fence = snapshot.get("publication_transaction_fence")
        if not isinstance(recovery, Mapping) or not isinstance(fence, Mapping):
            return snapshot
        if fence.get("transaction_id") != recovery.get("transaction_id"):
            return snapshot
        current_pair = self._current_publication_resource()
        if current_pair is None:
            raise AutopilotError("publication recovery reservation disappeared")
        _, current = current_pair
        if any(
            current.get(field) != recovery.get(field)
            for field in (
                "transaction_id",
                "transaction_key",
                "transaction_lease_id",
                "coordinator_id",
            )
        ) or current.get("status") not in {"PREPARED", "PINNED"}:
            raise AutopilotError("publication recovery lease changed")
        authoritative = dict(snapshot)
        authoritative.pop("observed_at", None)
        authoritative.pop("authority_digest", None)
        authoritative["publication_transaction_fence"] = None
        authoritative["active_publication_count"] = 0
        authoritative["publication_transaction_status"] = None
        authoritative["authority_digest"] = digest_json(authoritative)
        authoritative["observed_at"] = snapshot["observed_at"]
        return authoritative

    def _observe_publication_remote(
        self, receipt_heads: Sequence[Mapping[str, str]]
    ) -> tuple[str | None, Mapping[str, str]]:
        self.assert_canonical_remote_transport_identity()
        target = self._remote_ref_sha(f"refs/heads/{self.target_branch}")
        heads: dict[str, str] = {}
        for item in receipt_heads:
            observed = self._remote_ref_sha(f"refs/heads/{item['branch']}")
            if observed is None:
                raise AutopilotError(
                    f"publication receipt branch is absent: {item['branch']}"
                )
            heads[str(item["node_id"])] = observed
        return target, heads

    def _materialize_observed_publication_target(
        self,
        transaction_id: str,
        observed_sha: str,
        *,
        observation_key: str,
    ) -> str:
        """Fetch one point-in-time target observation to its portable evidence ref."""

        if (
            AUTHORITY_ID.fullmatch(transaction_id) is None
            or FULL_SHA.fullmatch(observed_sha) is None
            or AUTHORITY_ID.fullmatch(observation_key) is None
        ):
            raise AutopilotError("publication target observation identity is invalid")
        observation_ref = publication_observation_evidence_ref(
            self.execution_id,
            transaction_id,
            observation_key,
        )
        self._assert_execution_evidence_ref(observation_ref)
        local = self._local_ref_sha(observation_ref)
        if local is None:
            self.assert_canonical_remote_transport_identity()
            fetched = self._git(
                (
                    "fetch",
                    "--no-write-fetch-head",
                    "origin",
                    f"refs/heads/{self.target_branch}:{observation_ref}",
                ),
                check=False,
            )
            if fetched.returncode != 0:
                raise AutopilotError(
                    "cannot materialize the observed publication target"
                )
            local = self._local_ref_sha(observation_ref)
        if local != observed_sha:
            raise AutopilotError(
                "publication target changed while its observation was materialized"
            )
        return observation_ref

    def _validated_superseded_publication_observation(
        self,
        value: object,
        *,
        transaction: Mapping[str, Any],
        expected_target_sha: str,
        observed_target_sha: str,
        label: str,
    ) -> dict[str, object]:
        if (
            not isinstance(value, Mapping)
            or set(value) != SUPERSEDED_PUBLICATION_TARGET_OBSERVATION_FIELDS
        ):
            raise AutopilotError(f"{label} has an invalid exact schema")
        observation = dict(value)
        material = dict(observation)
        record_id = material.pop("record_id", None)
        receipts = observation.get("receipt_heads")
        normalized_receipts: list[dict[str, str]] = []
        if not isinstance(receipts, list) or not receipts:
            raise AutopilotError(f"{label} has no receipt-head observations")
        for receipt in receipts:
            if (
                not isinstance(receipt, Mapping)
                or set(receipt)
                != {"node_id", "branch", "expected_sha", "observed_sha"}
                or not isinstance(receipt.get("node_id"), str)
                or not str(receipt["node_id"]).strip()
                or not isinstance(receipt.get("branch"), str)
                or not str(receipt["branch"]).strip()
                or FULL_SHA.fullmatch(str(receipt.get("expected_sha"))) is None
                or receipt.get("observed_sha") != receipt.get("expected_sha")
            ):
                raise AutopilotError(f"{label} has a malformed receipt-head proof")
            normalized_receipts.append(
                {
                    "node_id": str(receipt["node_id"]),
                    "branch": str(receipt["branch"]),
                    "expected_sha": str(receipt["expected_sha"]),
                    "observed_sha": str(receipt["observed_sha"]),
                }
            )
        expected_receipts = [
            {
                "node_id": str(item["node_id"]),
                "branch": str(item["branch"]),
                "expected_sha": str(item["sha"]),
                "observed_sha": str(item["sha"]),
            }
            for item in transaction["receipt_heads"]
        ]
        transport = self.assert_canonical_remote_transport_identity()
        observation_ref = observation.get("observation_ref")
        if not isinstance(observation_ref, str):
            raise AutopilotError(f"{label} observation ref is invalid")
        self._assert_execution_evidence_ref(observation_ref)
        observation_key = digest_json(
            {
                "kind": "hive-mind-superseded-publication-observation-ref-key-v1",
                "execution_id": self.execution_id,
                "publication_transaction_id": transaction["transaction_id"],
                "expected_target_sha": expected_target_sha,
                "observed_target_sha": observed_target_sha,
                "receipt_heads": normalized_receipts,
                "observed_at": observation.get("observed_at"),
            }
        )
        required_observation_ref = publication_observation_evidence_ref(
            self.execution_id,
            str(transaction["transaction_id"]),
            observation_key,
        )
        try:
            parse_time(observation.get("observed_at"))
        except Exception as error:
            raise AutopilotError(f"{label} time is malformed") from error
        if (
            record_id != digest_json(material)
            or AUTHORITY_ID.fullmatch(str(record_id)) is None
            or observation.get("schema_version") != 1
            or observation.get("kind")
            != SUPERSEDED_PUBLICATION_TARGET_OBSERVATION_KIND
            or observation.get("repository")
            != self.repository_identity.get("repository")
            or observation.get("repository_transport_digest")
            != self.repository_identity.get("transport_digest")
            or transport.get("record_id") is None
            or observation.get("target_ref")
            != f"refs/heads/{self.target_branch}"
            or observation.get("expected_target_sha") != expected_target_sha
            or observation.get("pinned_sha") != transaction.get("pinned_sha")
            or observation.get("observed_target_sha") != observed_target_sha
            or observation.get("observation_ref_sha") != observed_target_sha
            or observation_ref != required_observation_ref
            or observation.get("transaction_ref")
            != transaction.get("transaction_ref")
            or observation.get("observed_transaction_sha")
            != transaction.get("pinned_sha")
            or normalized_receipts != expected_receipts
            or observation.get("receipt_heads") != normalized_receipts
            or observation.get("execution_namespace")
            != self.execution_namespace
            or observation.get("execution_id") != self.execution_id
            or observation.get("release_id") != transaction.get("release_id")
            or observation.get("publication_transaction_id")
            != transaction.get("transaction_id")
        ):
            raise AutopilotError(f"{label} authority binding is invalid")
        return observation

    def _superseded_publication_observation_path(
        self, observation_id: str
    ) -> Path:
        if AUTHORITY_ID.fullmatch(observation_id) is None:
            raise AutopilotError(
                "superseded publication observation id is invalid"
            )
        path = (
            self.arbiter_dir
            / "target-observations"
            / (observation_id.removeprefix("sha256:") + ".json")
        )
        if self._is_link_like(path) or self._is_link_like(path.parent):
            raise AutopilotError(
                "superseded publication observation traverses a link"
            )
        return path

    def _create_superseded_publication_observation(
        self,
        transaction: Mapping[str, Any],
        *,
        expected_target_sha: str,
        observed_target_sha: str,
        observed_heads: Mapping[str, str],
        observed_transaction_sha: str,
    ) -> Mapping[str, object]:
        receipts = [
            {
                "node_id": str(item["node_id"]),
                "branch": str(item["branch"]),
                "expected_sha": str(item["sha"]),
                "observed_sha": str(observed_heads.get(str(item["node_id"]))),
            }
            for item in transaction["receipt_heads"]
        ]
        observed_at = format_time(self.clock())
        observation_key = digest_json(
            {
                "kind": "hive-mind-superseded-publication-observation-ref-key-v1",
                "execution_id": self.execution_id,
                "publication_transaction_id": transaction["transaction_id"],
                "expected_target_sha": expected_target_sha,
                "observed_target_sha": observed_target_sha,
                "receipt_heads": receipts,
                "observed_at": observed_at,
            }
        )
        observation_ref = self._materialize_observed_publication_target(
            str(transaction["transaction_id"]),
            observed_target_sha,
            observation_key=observation_key,
        )
        self._publish_remote_evidence_ref(
            observation_ref,
            observed_target_sha,
            label="superseded publication target observation",
        )
        material: dict[str, object] = {
            "schema_version": 1,
            "kind": SUPERSEDED_PUBLICATION_TARGET_OBSERVATION_KIND,
            "repository": self.repository_identity["repository"],
            "repository_transport_digest": self.repository_identity[
                "transport_digest"
            ],
            "target_ref": f"refs/heads/{self.target_branch}",
            "expected_target_sha": expected_target_sha,
            "pinned_sha": transaction["pinned_sha"],
            "observed_target_sha": observed_target_sha,
            "observation_ref": observation_ref,
            "observation_ref_sha": observed_target_sha,
            "transaction_ref": transaction["transaction_ref"],
            "observed_transaction_sha": observed_transaction_sha,
            "receipt_heads": receipts,
            "execution_namespace": self.execution_namespace,
            "execution_id": self.execution_id,
            "release_id": transaction["release_id"],
            "publication_transaction_id": transaction["transaction_id"],
            "observed_at": observed_at,
        }
        observation = {**material, "record_id": digest_json(material)}
        return self._validated_superseded_publication_observation(
            observation,
            transaction=transaction,
            expected_target_sha=expected_target_sha,
            observed_target_sha=observed_target_sha,
            label="new superseded publication target observation",
        )

    def _seal_superseded_publication_watermark(
        self,
        transaction: Mapping[str, Any],
        *,
        sealed_record_id: str,
        starting_watermark: Mapping[str, object],
        observed_target_sha: str,
        observed_heads: Mapping[str, str],
        observed_transaction_sha: str,
        actor: str,
    ) -> Mapping[str, object]:
        """Advance/adopt the target watermark, then prove the complete remote set."""

        already_sealed = bool(
            starting_watermark.get("source_kind")
            == "SUPERSEDED_PUBLICATION"
            and starting_watermark.get("source_execution_id") == self.execution_id
            and starting_watermark.get("source_release_id")
            == transaction.get("release_id")
            and starting_watermark.get("publication_transaction_id")
            == transaction.get("transaction_id")
            and starting_watermark.get("target_sha") == observed_target_sha
            and AUTHORITY_ID.fullmatch(
                str(starting_watermark.get("source_observation_id"))
            )
            is not None
        )
        if already_sealed:
            raw_observation = self._strict_json_file(
                self._superseded_publication_observation_path(
                    str(starting_watermark["source_observation_id"])
                ),
                label="superseded publication target observation",
            )
            if not isinstance(raw_observation, Mapping):
                raise AutopilotError(
                    "superseded publication target observation is malformed"
                )
            observation = self._validated_superseded_publication_observation(
                raw_observation,
                transaction=transaction,
                # The controller already replayed the prior watermark before
                # returning this source record; the immutable observation seals
                # its exact predecessor for clone-independent recovery.
                expected_target_sha=str(raw_observation.get("expected_target_sha")),
                observed_target_sha=observed_target_sha,
                label="superseded publication target observation",
            )
            watermark = dict(starting_watermark)
        else:
            observation = self._create_superseded_publication_observation(
                transaction,
                expected_target_sha=str(starting_watermark["target_sha"]),
                observed_target_sha=observed_target_sha,
                observed_heads=observed_heads,
                observed_transaction_sha=observed_transaction_sha,
            )
            with self._host_arbiter_guard():
                with self.execution_lock(
                    "dispatcher-admission.lock", timeout_seconds=120.0
                ):
                    _, current = self._validated_publication_resource(
                        self._strict_json_file(
                            self._publication_resource_path(),
                            label="publication target reservation",
                        ),
                        label="publication target reservation",
                    )
                    current_watermark = self.repository_target_watermark()
                    if (
                        current.get("transaction_id")
                        != transaction.get("transaction_id")
                        or current.get("record_id") != sealed_record_id
                        or current.get("status") != "PUBLISH_UNKNOWN"
                        or current_watermark.get("record_id")
                        != starting_watermark.get("record_id")
                        or current_watermark.get("target_generation")
                        != starting_watermark.get("target_generation")
                        or current_watermark.get("target_sha")
                        != starting_watermark.get("target_sha")
                    ):
                        raise AutopilotError(
                            "publication or target generation changed before "
                            "superseded evidence was sealed"
                        )
                    watermark = dict(
                        self.advance_repository_target_watermark_from_superseded_publication(
                            expected_generation=int(
                                current_watermark["target_generation"]
                            ),
                            expected_target_sha=str(current_watermark["target_sha"]),
                            target_sha=observed_target_sha,
                            source_release_id=str(current["release_id"]),
                            publication_transaction_id=str(
                                current["transaction_id"]
                            ),
                            source_observation=observation,
                            actor=actor,
                        )
                    )

        remote_target, post_heads = self._observe_publication_remote(
            list(transaction["receipt_heads"])
        )
        remote_transaction = self._remote_ref_sha(
            str(transaction["transaction_ref"])
        )
        remote_observation = self._remote_ref_sha(str(observation["observation_ref"]))
        if (
            remote_target != observed_target_sha
            or remote_transaction != transaction.get("pinned_sha")
            or remote_observation != observed_target_sha
            or any(
                post_heads.get(str(item["node_id"])) != item["sha"]
                for item in transaction["receipt_heads"]
            )
            or watermark.get("target_sha") != observed_target_sha
            or watermark.get("source_kind") != "SUPERSEDED_PUBLICATION"
            or watermark.get("source_execution_id") != self.execution_id
            or watermark.get("source_release_id") != transaction.get("release_id")
            or watermark.get("publication_transaction_id")
            != transaction.get("transaction_id")
            or watermark.get("source_observation_id")
            != observation.get("record_id")
        ):
            raise AutopilotError(
                "superseded publication remote proof changed after watermark CAS"
            )
        return watermark

    def begin_publication_transaction(
        self,
        *,
        release_id: str,
        round_id: str,
        expected_target_sha: str,
        authority_digest: str,
        receipt_heads: Mapping[str, str],
        coordinator_id: str,
        actor: str,
        resume_lease_id: str | None = None,
        lease_minutes: int = 15,
    ) -> Mapping[str, Any]:
        """Reserve/adopt one crash-persistent publication transaction."""

        if (
            AUTHORITY_ID.fullmatch(release_id) is None
            or not (
                AUTHORITY_ID.fullmatch(round_id) is not None
                or (
                    round_id.startswith("R")
                    and round_id[1:].isdigit()
                    and int(round_id[1:]) >= 1
                )
            )
            or FULL_SHA.fullmatch(expected_target_sha) is None
            or AUTHORITY_ID.fullmatch(authority_digest) is None
            or not isinstance(coordinator_id, str)
            or not coordinator_id.strip()
            or not actor.strip()
            or type(lease_minutes) is not int
            or lease_minutes < 1
        ):
            raise AutopilotError("publication transaction authority is invalid")
        terminal_fence = self.plan_terminal_fence()
        if terminal_fence is not None:
            raise AutopilotError(
                "publication transaction reservation is closed by the execution "
                f"terminal fence {terminal_fence['record_id']}"
            )
        round_snapshot = getattr(self, "round_authority_snapshot", None)
        if not callable(round_snapshot):
            raise AutopilotError("publication requires typed round authority")
        observed_authority = round_snapshot(release_id)
        observed_digest, authority_baseline_digest = self._round_authority_digests(
            observed_authority, release_id=release_id
        )
        if authority_digest not in {
            observed_digest,
            authority_baseline_digest,
        }:
            raise AutopilotError(
                "publication authority digest differs from the fresh round snapshot"
            )
        # Remote reads happen without authority locks. They are sealed now and
        # observed again immediately before any push.
        with self.execution_lock("dispatcher-admission.lock", timeout_seconds=120.0):
            self._assert_execution_not_terminal_unlocked(
                "publication transaction reservation"
            )
            release = self.current_release()
            release_issues = self._release_issues(release)
            if release_issues or not isinstance(release, Mapping):
                raise AutopilotError(
                    "publication transaction requires a live release: "
                    + "; ".join(release_issues)
                )
            if (
                release.get("release_id") != release_id
                or release.get("target_sha") != expected_target_sha
            ):
                raise AutopilotError(
                    "publication transaction release/target fence mismatch"
                )
            sealed_heads = self._validate_receipt_heads(receipt_heads, release)
        remote_target, observed_heads = self._observe_publication_remote(sealed_heads)
        if remote_target != expected_target_sha or any(
            observed_heads.get(item["node_id"]) != item["sha"]
            for item in sealed_heads
        ):
            raise AutopilotError(
                "publication target or receipt heads differ from remote authority"
            )
        transaction_key = digest_json(
            {
                "kind": "hive-mind-publication-transaction-key-v1",
                "execution_id": self.execution_id,
                "release_id": release_id,
                "round_id": round_id,
                "expected_target_sha": expected_target_sha,
                "authority_digest": authority_digest,
                "authority_baseline_digest": authority_baseline_digest,
                "receipt_heads": sealed_heads,
            }
        )
        now = self.clock()
        resource_path = self._publication_resource_path()
        with self._host_arbiter_guard():
            with self.execution_lock(
                "dispatcher-admission.lock", timeout_seconds=120.0
            ):
                self._assert_execution_not_terminal_unlocked(
                    "publication transaction reservation"
                )
                self.assert_canonical_remote_transport_identity()
                release = self.current_release()
                release_issues = self._release_issues(release)
                if release_issues or not isinstance(release, Mapping):
                    raise AutopilotError(
                        "publication transaction requires a live release: "
                        + "; ".join(release_issues)
                    )
                if (
                    release.get("release_id") != release_id
                    or release.get("target_sha") != expected_target_sha
                ):
                    raise AutopilotError(
                        "publication transaction release/target fence mismatch"
                    )
                if resource_path.exists() and self._is_link_like(resource_path):
                    raise AutopilotError("publication reservation authority is a link")
                attempt_epoch = 1
                if resource_path.is_file():
                    existing_value = self._strict_json_file(
                        resource_path, label="publication target reservation"
                    )
                    existing, embedded = self._validated_publication_resource(
                        existing_value,
                        label="publication target reservation",
                        allow_foreign=True,
                    )
                    if embedded.get("status") == "PUBLISH_UNKNOWN":
                        raise AutopilotError(
                            "target publication has an indeterminate remote outcome; "
                            "adjudicate its exact transaction before new admission"
                        )
                    nonterminal = (
                        embedded.get("status") in PUBLICATION_NONTERMINAL_STATUSES
                    )
                    if nonterminal and parse_time(
                        embedded.get("lease_expires_at")
                    ) > now:
                        recovery = getattr(
                            self, "_publication_recovery_authority", None
                        )
                        effective_resume_lease_id = resume_lease_id
                        if (
                            effective_resume_lease_id is None
                            and isinstance(recovery, Mapping)
                            and recovery.get("transaction_id")
                            == embedded.get("transaction_id")
                            and recovery.get("transaction_key") == transaction_key
                            and recovery.get("coordinator_id") == coordinator_id
                        ):
                            effective_resume_lease_id = str(
                                recovery.get("transaction_lease_id")
                            )
                        if (
                            embedded.get("transaction_key") == transaction_key
                            and embedded.get("coordinator_id") == coordinator_id
                            and effective_resume_lease_id
                            == embedded.get("transaction_lease_id")
                        ):
                            self._write_publication_pair(
                                embedded,
                                detail="publication transaction crash evidence repaired",
                            )
                            return embedded
                        raise AutopilotError(
                            "target publication has another live coordinator lease"
                        )
                    if nonterminal and embedded.get("status") == "PUBLISHING":
                        # Once the durable operation intent exists, lease expiry
                        # cannot prove that the remote effect did not happen.  A
                        # publisher may still be inside push or may have lost the
                        # response after acceptance.  Preserve the exact intent as
                        # an indeterminate active fence; only the remote
                        # adjudicator may later resolve it.
                        completed_at = format_time(now)
                        unknown = dict(embedded)
                        unknown.update(
                            {
                                "status": "PUBLISH_UNKNOWN",
                                "outcome": "PUBLISH_UNKNOWN",
                                "detail": (
                                    "publication coordinator lease expired after "
                                    "durable remote-effect intent"
                                ),
                                "actor": actor,
                                "updated_at": completed_at,
                                "completed_at": completed_at,
                            }
                        )
                        unknown = self._seal_publication_record(unknown)
                        if unknown.get("execution_id") == self.execution_id:
                            self._write_publication_pair(
                                unknown,
                                detail=(
                                    "expired PUBLISHING authority retained as "
                                    "indeterminate remote outcome"
                                ),
                            )
                        else:
                            self._atomic_write_authority_json(
                                resource_path,
                                self._publication_resource_record(unknown),
                            )
                        raise AutopilotError(
                            "target publication has an indeterminate remote outcome; "
                            "adjudicate its exact transaction before new admission"
                        )
                    if nonterminal:
                        archive = {
                            "schema_version": 1,
                            "kind": "hive-mind-expired-publication-reservation-v1",
                            "disposition": "EXPIRED_FENCED",
                            "reservation": dict(existing),
                        }
                        archive["archive_id"] = digest_json(archive)
                        self._write_immutable_authority_json(
                            self.arbiter_dir,
                            self._publication_archive_path(
                                str(embedded["transaction_id"]),
                                str(embedded["record_id"]),
                            ),
                            archive,
                        )
                        completed_at = format_time(now)
                        expired = dict(embedded)
                        expired.update(
                            {
                                "status": "EXPIRED_FENCED",
                                "outcome": "EXPIRED_FENCED",
                                "detail": "publication coordinator lease expired and was fenced",
                                "actor": actor,
                                "updated_at": completed_at,
                                "completed_at": completed_at,
                            }
                        )
                        expired = self._seal_publication_record(expired)
                        if expired.get("execution_id") == self.execution_id:
                            self._write_publication_pair(
                                expired,
                                detail="expired publication coordinator fenced",
                            )
                        else:
                            # The repository arbiter may fence a dead foreign
                            # coordinator, but must never write into that execution's
                            # private transaction journal. The immutable archive plus
                            # embedded terminal resource is the exact recovery proof.
                            self._atomic_write_authority_json(
                                resource_path,
                                self._publication_resource_record(expired),
                            )
                        embedded = expired
                    prior_epoch = embedded.get("attempt_epoch")
                    if type(prior_epoch) is int and prior_epoch >= 1:
                        attempt_epoch = prior_epoch + 1
                nonce = secrets.token_hex(32)
                transaction_lease_nonce = secrets.token_hex(32)
                transaction_id = digest_json(
                    {
                        "kind": "hive-mind-publication-attempt-key-v1",
                        "transaction_key": transaction_key,
                        "attempt_epoch": attempt_epoch,
                        "nonce": nonce,
                    }
                )
                record = self._seal_publication_record(
                    {
                        "schema_version": 1,
                        "kind": PUBLICATION_TRANSACTION_KIND,
                        "status": "PREPARED",
                        "transaction_key": transaction_key,
                        "attempt_epoch": attempt_epoch,
                        "nonce": nonce,
                        "transaction_id": transaction_id,
                        "execution_namespace": self.execution_namespace,
                        "execution_id": self.execution_id,
                        "release_id": release_id,
                        "round_id": round_id,
                        "repository": str(self.control["target"]["repository"]),
                        "target_branch": self.target_branch,
                        "expected_target_sha": expected_target_sha,
                        "authority_digest": authority_digest,
                        "authority_baseline_digest": authority_baseline_digest,
                        "receipt_heads": sealed_heads,
                        "receipt_heads_digest": digest_json(sealed_heads),
                        "transaction_ref": self.execution_transaction_ref(
                            transaction_id
                        ),
                        "coordinator_id": coordinator_id,
                        "transaction_lease_nonce": transaction_lease_nonce,
                        "transaction_lease_id": digest_json(
                            {
                                "kind": "hive-mind-publication-coordinator-lease-v1",
                                "transaction_id": transaction_id,
                                "nonce": transaction_lease_nonce,
                            }
                        ),
                        "lease_expires_at": format_time(
                            now + timedelta(minutes=lease_minutes)
                        ),
                        "publishing_lease_nonce": None,
                        "publishing_lease_id": None,
                        "publishing_lease_expires_at": None,
                        "pinned_sha": None,
                        "validation_evidence": None,
                        "outcome": None,
                        "detail": "publication transaction reserved",
                        "actor": actor,
                        "reserved_at": format_time(now),
                        "updated_at": format_time(now),
                        "completed_at": None,
                    }
                )
                self._write_publication_pair(
                    record, detail="publication transaction reserved"
                )
        # PREPARED is now the admission fence.  Recompute the full authority
        # baseline after publishing that fence, with only this exact transaction
        # projected out, so a claim/lease/reservation that won the preceding race
        # is observed and the transaction is rejected before any Git publication
        # evidence or target effect.  From this point onward the dynamic
        # claim/validation/launch guards reject new admission until terminal.
        try:
            with self.publication_recovery_guard(
                record,
                coordinator_id=coordinator_id,
                adopt_remote_pin=False,
            ):
                fenced_authority = round_snapshot(release_id)
            _, fenced_baseline_digest = self._round_authority_digests(
                fenced_authority, release_id=release_id
            )
            if fenced_baseline_digest != authority_baseline_digest:
                raise AutopilotError(
                    "round authority changed before publication admission fenced"
                )
            remote_target, observed_heads = self._observe_publication_remote(
                sealed_heads
            )
            if remote_target != expected_target_sha or any(
                observed_heads.get(item["node_id"]) != item["sha"]
                for item in sealed_heads
            ):
                raise AutopilotError(
                    "publication target or receipt heads changed before the "
                    "PREPARED authority fence stabilized"
                )
        except Exception as error:
            self.finish_publication_transaction(
                record,
                pinned_sha=None,
                outcome="REJECTED",
                actor=actor,
                detail=f"publication PREPARED authority rejected: {error}",
            )
            raise
        return record

    def renew_publication_transaction(
        self,
        transaction: Mapping[str, Any],
        *,
        coordinator_id: str,
        transaction_lease_id: str,
        lease_minutes: int = 15,
    ) -> Mapping[str, Any]:
        if type(lease_minutes) is not int or lease_minutes < 1:
            raise AutopilotError("publication lease duration is invalid")
        supplied = self._validated_publication_transaction(
            transaction, label="publication lease token"
        )
        with self._host_arbiter_guard():
            with self.execution_lock(
                "dispatcher-admission.lock", timeout_seconds=120.0
            ):
                resource_value = self._strict_json_file(
                    self._publication_resource_path(),
                    label="publication target reservation",
                )
                _, current = self._validated_publication_resource(
                    resource_value, label="publication target reservation"
                )
                if (
                    current.get("transaction_id") != supplied.get("transaction_id")
                    or current.get("transaction_key") != supplied.get("transaction_key")
                    or current.get("record_id") != supplied.get("record_id")
                    or current.get("coordinator_id") != coordinator_id
                    or current.get("transaction_lease_id") != transaction_lease_id
                    or current.get("status")
                    not in {"PREPARED", "PINNED", "VALIDATED"}
                    or parse_time(current.get("lease_expires_at")) <= self.clock()
                ):
                    raise AutopilotError("publication coordinator lease is stale")
                renewed = dict(current)
                renewed["lease_expires_at"] = format_time(
                    self.clock() + timedelta(minutes=lease_minutes)
                )
                renewed["detail"] = "publication coordinator lease renewed"
                renewed["updated_at"] = format_time(self.clock())
                renewed = self._seal_publication_record(renewed)
                self._write_publication_pair(
                    renewed, detail="publication coordinator lease renewed"
                )
                return renewed

    def _publication_watermark_matches(
        self,
        watermark: Mapping[str, object],
        transaction: Mapping[str, Any],
        pinned_sha: str,
    ) -> bool:
        return bool(
            watermark.get("source_kind") == "PUBLICATION"
            and watermark.get("source_execution_id") == self.execution_id
            and watermark.get("source_release_id") == transaction.get("release_id")
            and watermark.get("publication_transaction_id")
            == transaction.get("transaction_id")
            # PUBLICATION watermarks now retain a typed transition record and
            # the exact sealed transaction bytes.  repository_target_watermark()
            # has already dereferenced and authenticated that lineage; absence
            # of the transition id is therefore legacy/non-authoritative.
            and isinstance(watermark.get("source_observation_id"), str)
            and AUTHORITY_ID.fullmatch(str(watermark["source_observation_id"]))
            is not None
            and watermark.get("target_sha") == pinned_sha
        )

    def _recover_watermarked_publication(
        self,
        supplied: Mapping[str, Any],
        *,
        pinned_sha: str,
        actor: str,
    ) -> Mapping[str, Any]:
        """Finish the one crash window after watermark CAS and before journaling."""

        with self._host_arbiter_guard():
            with self.execution_lock(
                "dispatcher-admission.lock", timeout_seconds=120.0
            ):
                resource_value = self._strict_json_file(
                    self._publication_resource_path(),
                    label="publication target reservation",
                )
                _, current = self._validated_publication_resource(
                    resource_value, label="publication target reservation"
                )
                if (
                    current.get("transaction_id") != supplied.get("transaction_id")
                    or current.get("pinned_sha") != pinned_sha
                ):
                    raise AutopilotError(
                        "watermarked publication differs from durable transaction"
                    )
                if current.get("status") == "PUBLISHED":
                    self._write_publication_pair(
                        current,
                        detail="watermarked publication evidence repaired",
                    )
                    return current
                if current.get("status") != "PUBLISHING":
                    raise AutopilotError(
                        "repository watermark may only recover PUBLISHING authority"
                    )
                watermark = self.repository_target_watermark()
                if not self._publication_watermark_matches(
                    watermark, current, pinned_sha
                ):
                    raise AutopilotError(
                        "repository watermark does not prove this publication CAS"
                    )
                sealed_record_id = str(current["record_id"])
                sealed_heads = list(current["receipt_heads"])
                transaction_ref = str(current["transaction_ref"])

        observation_error: str | None = None
        try:
            remote_target, remote_heads = self._observe_publication_remote(
                sealed_heads
            )
            remote_transaction = self._remote_ref_sha(transaction_ref)
        except Exception as error:
            observation_error = str(error)
            remote_target = None
            remote_heads = {}
            remote_transaction = None
        exact_remote = bool(
            observation_error is None
            and remote_target == pinned_sha
            and remote_transaction == pinned_sha
            and all(
                remote_heads.get(str(item["node_id"])) == item["sha"]
                for item in sealed_heads
            )
        )

        with self._host_arbiter_guard():
            with self.execution_lock(
                "dispatcher-admission.lock", timeout_seconds=120.0
            ):
                resource_value = self._strict_json_file(
                    self._publication_resource_path(),
                    label="publication target reservation",
                )
                _, current = self._validated_publication_resource(
                    resource_value, label="publication target reservation"
                )
                if (
                    current.get("transaction_id") != supplied.get("transaction_id")
                    or current.get("record_id") != sealed_record_id
                    or current.get("status") != "PUBLISHING"
                ):
                    if (
                        current.get("transaction_id")
                        == supplied.get("transaction_id")
                        and current.get("status") == "PUBLISHED"
                    ):
                        self._write_publication_pair(
                            current,
                            detail="watermarked publication evidence repaired",
                        )
                        return current
                    raise AutopilotError(
                        "publication authority changed during watermark recovery"
                    )
                watermark = self.repository_target_watermark()
                if not self._publication_watermark_matches(
                    watermark, current, pinned_sha
                ):
                    raise AutopilotError(
                        "repository watermark changed during publication recovery"
                    )
                outcome = "PUBLISHED" if exact_remote else "PUBLISH_UNKNOWN"
                detail = (
                    "repository watermark and full remote ref set prove publication"
                    if exact_remote
                    else "repository watermark is durable but fresh remote ref proof "
                    "is unavailable"
                    + (f": {observation_error}" if observation_error else "")
                )
                completed_at = format_time(self.clock())
                finished = dict(current)
                finished.update(
                    {
                        "status": outcome,
                        "outcome": outcome,
                        "detail": detail,
                        "actor": actor,
                        "updated_at": completed_at,
                        "completed_at": completed_at,
                    }
                )
                finished = self._seal_publication_record(finished)
                self._write_publication_pair(finished, detail=detail)
                return finished

    def publish_pinned_transaction(
        self,
        transaction: Mapping[str, Any],
        *,
        pinned_sha: str,
        actor: str,
        _reconcile_expired: bool = False,
    ) -> Mapping[str, Any]:
        """Publish one fixed validated SHA without holding local locks on network I/O."""

        supplied = self._validated_publication_transaction(
            transaction, label="publication completion token"
        )
        transaction_id = supplied.get("transaction_id")
        if (
            FULL_SHA.fullmatch(pinned_sha) is None
            or not actor.strip()
            or supplied.get("status")
            not in {
                "VALIDATED",
                "PUBLISHING",
                "PUBLISHED",
                "REJECTED",
                "PUBLISH_UNKNOWN",
            }
        ):
            raise AutopilotError(
                "publication completion requires an exact VALIDATED capability"
            )
        existing_watermark = self.repository_target_watermark()
        if self._publication_watermark_matches(
            existing_watermark, supplied, pinned_sha
        ):
            return self._recover_watermarked_publication(
                supplied, pinned_sha=pinned_sha, actor=actor
            )
        round_snapshot = getattr(self, "round_authority_snapshot", None)
        if not callable(round_snapshot):
            raise AutopilotError("publication requires typed round authority")
        authority_before = round_snapshot(str(supplied.get("release_id")))
        before_digest, before_baseline_digest = self._round_authority_digests(
            authority_before, release_id=str(supplied["release_id"])
        )
        if before_baseline_digest != supplied.get("authority_baseline_digest"):
            raise AutopilotError(
                "publication round authority changed since transaction reservation"
            )

        # Phase one authenticates the shared reservation and the pinned commit in
        # this clone.  A takeover clone may first materialize the immutable remote
        # transaction ref left by the original coordinator.  No shared state is
        # advanced merely because that clone happened to have cached Git objects.
        transaction_ref = str(supplied["transaction_ref"])
        local_transaction = self._git(
            ("rev-parse", "--verify", f"{transaction_ref}^{{commit}}"),
            check=False,
        )
        if local_transaction.returncode != 0:
            self._materialize_remote_evidence_ref(
                transaction_ref,
                pinned_sha,
                label="publication transaction evidence",
            )

        with self._host_arbiter_guard():
            with self.execution_lock(
                "dispatcher-admission.lock", timeout_seconds=120.0
            ):
                resource_value = self._strict_json_file(
                    self._publication_resource_path(),
                    label="publication target reservation",
                )
                _, installed = self._validated_publication_resource(
                    resource_value, label="publication target reservation"
                )
                if any(
                    installed.get(field) != supplied.get(field)
                    for field in (
                        "transaction_id",
                        "transaction_key",
                        "execution_id",
                        "release_id",
                        "coordinator_id",
                        "transaction_lease_id",
                    )
                ):
                    raise AutopilotError(
                        "publication transaction token differs from durable authority"
                    )
                if installed.get("status") not in {
                    "VALIDATED",
                    "PUBLISHING",
                }:
                    if (
                        installed.get("pinned_sha") == pinned_sha
                        and installed.get("outcome")
                        in {
                            "PUBLISHED",
                            "SUPERSEDED_INTEGRATED",
                            "REJECTED",
                            "PUBLISH_UNKNOWN",
                        }
                    ):
                        self._write_publication_pair(
                            installed,
                            detail="terminal publication evidence repaired",
                        )
                        return installed
                    raise AutopilotError("publication transaction is already terminal")
                exact_record = installed.get("record_id") == supplied.get("record_id")
                crash_resume = (
                    supplied.get("status") == "VALIDATED"
                    and installed.get("status") == "PUBLISHING"
                    and installed.get("pinned_sha") == pinned_sha
                    and installed.get("validation_evidence")
                    == supplied.get("validation_evidence")
                )
                if not exact_record and not crash_resume:
                    raise AutopilotError(
                        "publication transaction record changed outside the exact "
                        "PUBLISHING crash-resume transition"
                    )
                expired_reconciliation = (
                    parse_time(installed.get("lease_expires_at")) <= self.clock()
                )
                if expired_reconciliation and not (
                    _reconcile_expired and installed.get("status") == "PUBLISHING"
                ):
                    raise AutopilotError("publication transaction is not live")
                release = self.current_release()
                release_issues = self._release_issues(release)
                if release_issues or not isinstance(release, Mapping) or (
                    release.get("release_id") != installed.get("release_id")
                    or release.get("target_sha")
                    != installed.get("expected_target_sha")
                ):
                    raise AutopilotError(
                        "publication release changed after validation transaction began"
                    )
                transaction_ref = str(installed["transaction_ref"])
                resolved = self._git(
                    ("rev-parse", "--verify", f"{transaction_ref}^{{commit}}"),
                    check=False,
                )
                if resolved.returncode != 0 or resolved.stdout.strip() != pinned_sha:
                    raise AutopilotError(
                        "publication private transaction ref does not equal pinned SHA"
                    )
                expected = str(installed["expected_target_sha"])
                if not self.is_ancestor(expected, pinned_sha):
                    raise AutopilotError(
                        "publication pinned SHA is not a fast-forward of reserved target"
                    )
                if installed.get("status") in {"VALIDATED", "PUBLISHING"} and (
                    installed.get("pinned_sha") != pinned_sha
                ):
                    raise AutopilotError(
                        "publication retry changed its pinned transaction SHA"
                    )
                validation = installed.get("validation_evidence")
                if not isinstance(validation, Mapping):
                    raise AutopilotError(
                        "publication transaction lacks fixed-gate capability"
                    )
                gate_identity = self.publication_validation_gate_identity()
                gate = validation.get("gate")
                if not isinstance(gate, Mapping) or not self._publication_gate_matches_identity(
                    gate, gate_identity
                ):
                    raise AutopilotError(
                        "publication fixed-gate capability is not current"
                    )
                if self._assert_canonical_publication_chain(
                    installed, pinned_sha
                ) != validation.get("pinned_tree"):
                    raise AutopilotError(
                        "publication pin differs from fixed-gate tree authority"
                    )
                self._assert_publication_source_policy(installed, validation)
                recovering_publishing = installed.get("status") == "PUBLISHING"
                validated_record_id = str(installed["record_id"])

        # VALIDATED can only exist after the immutable transaction ref was
        # published and verified.  Re-fetch it here so a takeover clone proves
        # the same capability before target publication.
        self._materialize_remote_evidence_ref(
            transaction_ref,
            pinned_sha,
            label="publication transaction evidence",
        )

        authority_at_intent = round_snapshot(str(supplied.get("release_id")))
        intent_digest, intent_baseline_digest = self._round_authority_digests(
            authority_at_intent, release_id=str(supplied["release_id"])
        )
        if (
            intent_digest != before_digest
            or intent_baseline_digest != supplied.get("authority_baseline_digest")
        ):
            raise AutopilotError(
                "publication round authority changed before PUBLISHING intent"
            )

        # Phase two revalidates after the remote evidence effect and only then
        # seals the bounded PUBLISHING operation lease.  No host/repository lock
        # remains held during the target observation or exact target CAS below.
        with self._host_arbiter_guard():
            with self.execution_lock(
                "dispatcher-admission.lock", timeout_seconds=120.0
            ):
                self._assert_execution_not_terminal_unlocked(
                    "publication PUBLISHING transition"
                )
                resource_value = self._strict_json_file(
                    self._publication_resource_path(),
                    label="publication target reservation",
                )
                _, current = self._validated_publication_resource(
                    resource_value, label="publication target reservation"
                )
                if (
                    current.get("transaction_id") != transaction_id
                    or current.get("record_id") != validated_record_id
                    or current.get("transaction_ref") != transaction_ref
                    or current.get("status") not in {"VALIDATED", "PUBLISHING"}
                ):
                    raise AutopilotError(
                        "publication authority changed while transaction evidence "
                        "was published"
                    )
                expired_reconciliation = (
                    parse_time(current.get("lease_expires_at")) <= self.clock()
                )
                if expired_reconciliation and not (
                    _reconcile_expired and current.get("status") == "PUBLISHING"
                ):
                    raise AutopilotError(
                        "publication transaction expired before PUBLISHING intent"
                    )
                release = self.current_release()
                release_issues = self._release_issues(release)
                if release_issues or not isinstance(release, Mapping) or (
                    release.get("release_id") != current.get("release_id")
                    or release.get("target_sha")
                    != current.get("expected_target_sha")
                ):
                    raise AutopilotError(
                        "publication release changed before PUBLISHING intent"
                    )
                release_target_generation = int(release["target_generation"])
                release_target_watermark_record_id = str(
                    release["target_watermark_record_id"]
                )
                locked_authority = round_snapshot(str(current["release_id"]))
                locked_digest, locked_baseline = self._round_authority_digests(
                    locked_authority, release_id=str(current["release_id"])
                )
                if (
                    locked_digest != before_digest
                    or locked_baseline != current.get("authority_baseline_digest")
                ):
                    raise AutopilotError(
                        "publication authority changed inside PUBLISHING transition"
                    )
                current_validation = current.get("validation_evidence")
                if (
                    not isinstance(current_validation, Mapping)
                    or self.publication_validation_gate_identity() != gate_identity
                    or self._assert_canonical_publication_chain(
                        current, pinned_sha
                    )
                    != current_validation.get("pinned_tree")
                ):
                    raise AutopilotError(
                        "publication fixed-gate capability changed before intent"
                    )
                if current.get("status") == "PUBLISHING":
                    if current.get("pinned_sha") != pinned_sha:
                        raise AutopilotError(
                            "publication retry changed its pinned transaction SHA"
                        )
                    publishing = dict(current)
                else:
                    operation_seconds = (
                        len(current["receipt_heads"]) + 8
                    ) * 30 + 120
                    operation_minutes = (operation_seconds + 59) // 60
                    if operation_minutes > 180:
                        raise AutopilotError(
                            "publication receipt set exceeds bounded operation lease"
                        )
                    publishing_nonce = secrets.token_hex(32)
                    publishing_lease_id = digest_json(
                        {
                            "kind": "hive-mind-publication-operation-lease-v1",
                            "transaction_id": transaction_id,
                            "transaction_lease_id": current[
                                "transaction_lease_id"
                            ],
                            "pinned_sha": pinned_sha,
                            "nonce": publishing_nonce,
                        }
                    )
                    operation_expires_at = format_time(
                        self.clock() + timedelta(minutes=operation_minutes)
                    )
                    publishing = dict(current)
                    publishing.update(
                        {
                            "status": "PUBLISHING",
                            "pinned_sha": pinned_sha,
                            "publishing_lease_nonce": publishing_nonce,
                            "publishing_lease_id": publishing_lease_id,
                            "publishing_lease_expires_at": operation_expires_at,
                            "lease_expires_at": operation_expires_at,
                            "detail": "remote publication in progress",
                            "actor": actor,
                            "updated_at": format_time(self.clock()),
                        }
                    )
                    publishing = self._seal_publication_record(publishing)
                    self._write_publication_pair(
                        publishing, detail="remote publication intent persisted"
                    )

        # The remote operation is intentionally outside all host/repository locks.
        push_exit_code: int | None = None
        detail = ""
        try:
            sealed_heads = list(publishing["receipt_heads"])
            remote_target, observed_heads = self._observe_publication_remote(
                sealed_heads
            )
            remote_transaction = self._remote_ref_sha(transaction_ref)
            exact_heads = not any(
                observed_heads.get(str(item["node_id"])) != item["sha"]
                for item in sealed_heads
            )
            exact_transaction = remote_transaction == pinned_sha
            if exact_heads and exact_transaction and remote_target == pinned_sha:
                outcome = "PUBLISHED"
                detail = "remote target already equals pinned SHA"
            elif expired_reconciliation:
                outcome = "PUBLISH_UNKNOWN"
                detail = (
                    "expired PUBLISHING intent cannot prove its historical remote "
                    "effect from current refs"
                )
            elif not exact_heads:
                outcome = (
                    "PUBLISH_UNKNOWN" if recovering_publishing else "REJECTED"
                )
                detail = "remote receipt heads changed after validation"
            elif not exact_transaction:
                outcome = (
                    "PUBLISH_UNKNOWN" if recovering_publishing else "REJECTED"
                )
                detail = "immutable remote transaction evidence changed after validation"
            elif remote_target != expected:
                outcome = (
                    "PUBLISH_UNKNOWN" if recovering_publishing else "REJECTED"
                )
                detail = "remote target changed before fast-forward publication"
            else:
                self.assert_canonical_remote_transport_identity()
                lease_arguments = [
                    (
                        "--force-with-lease="
                        f"refs/heads/{self.target_branch}:{expected}"
                    ),
                    *[
                        (
                            "--force-with-lease="
                            f"refs/heads/{item['branch']}:{item['sha']}"
                        )
                        for item in sealed_heads
                    ],
                    f"--force-with-lease={transaction_ref}:{pinned_sha}",
                ]
                refspecs = [
                    f"{pinned_sha}:refs/heads/{self.target_branch}",
                    *[
                        f"{item['sha']}:refs/heads/{item['branch']}"
                        for item in sealed_heads
                    ],
                    f"{pinned_sha}:{transaction_ref}",
                ]
                push = self._git(
                    (
                        "push",
                        "--porcelain",
                        "--atomic",
                        *lease_arguments,
                        "origin",
                        *refspecs,
                    ),
                    check=False,
                )
                push_exit_code = push.returncode
                try:
                    remote_after, observed_heads_after = (
                        self._observe_publication_remote(sealed_heads)
                    )
                    remote_transaction_after = self._remote_ref_sha(transaction_ref)
                except Exception:
                    remote_after = None
                    observed_heads_after = {}
                    remote_transaction_after = None
                exact_after = all(
                    observed_heads_after.get(str(item["node_id"])) == item["sha"]
                    for item in sealed_heads
                ) and remote_transaction_after == pinned_sha
                if remote_after == pinned_sha and exact_after:
                    outcome = "PUBLISHED"
                    detail = "atomic full-ref leased push reached pinned SHA"
                elif remote_after == expected and exact_after:
                    # A nonzero client result plus the current predecessor is
                    # not historical rejection evidence: the server may have
                    # accepted the push, lost the response, and then observed a
                    # fast revert.  Once PUBLISHING exists and push was invoked,
                    # only the exact pinned target proves success; every other
                    # post-effect state remains indeterminate.
                    outcome = "PUBLISH_UNKNOWN"
                    detail = (
                        "push response and current predecessor do not resolve "
                        "the historical PUBLISHING intent"
                    )
                else:
                    outcome = "PUBLISH_UNKNOWN"
                    detail = "remote outcome could not be proven after push"
        except Exception as error:
            outcome = "PUBLISH_UNKNOWN"
            detail = f"remote publication observation failed: {error}"

        authority_after: Mapping[str, Any] | None = None
        try:
            authority_after = round_snapshot(str(supplied.get("release_id")))
        except Exception as error:
            if outcome == "PUBLISHED":
                outcome = "PUBLISH_UNKNOWN"
            elif outcome != "PUBLISH_UNKNOWN":
                outcome = "REJECTED"
            detail += f"; final round authority unavailable: {error}"
        try:
            after_digest, after_baseline_digest = self._round_authority_digests(
                authority_after, release_id=str(supplied["release_id"])
            )
        except AutopilotError as error:
            if outcome == "PUBLISHED":
                outcome = "PUBLISH_UNKNOWN"
            elif outcome != "PUBLISH_UNKNOWN":
                outcome = "REJECTED"
            detail += f"; final round authority digest is unavailable: {error}"
            after_digest = None
            after_baseline_digest = None
        if (
            after_baseline_digest != supplied.get("authority_baseline_digest")
            or before_digest != after_digest
        ):
            if outcome == "PUBLISHED":
                outcome = "PUBLISH_UNKNOWN"
            elif outcome != "PUBLISH_UNKNOWN":
                outcome = "REJECTED"
            detail += "; round authority changed during remote publication"

        with self._host_arbiter_guard():
            with self.execution_lock(
                "dispatcher-admission.lock", timeout_seconds=120.0
            ):
                resource_value = self._strict_json_file(
                    self._publication_resource_path(),
                    label="publication target reservation",
                )
                _, current = self._validated_publication_resource(
                    resource_value, label="publication target reservation"
                )
                if current.get("transaction_id") != transaction_id:
                    raise AutopilotError(
                        "publication target reservation changed before outcome journal"
                    )
                if current.get("status") != "PUBLISHING":
                    if current.get("pinned_sha") == pinned_sha:
                        self._write_publication_pair(
                            current,
                            detail="terminal publication evidence repaired",
                        )
                        return current
                    raise AutopilotError(
                        "publication terminal evidence conflicts with retry"
                    )
                if current.get("record_id") != publishing.get("record_id"):
                    raise AutopilotError(
                        "publication operation authority changed during remote effect"
                    )
                if (
                    not expired_reconciliation
                    and parse_time(current.get("publishing_lease_expires_at"))
                    <= self.clock()
                ):
                    outcome = "PUBLISH_UNKNOWN"
                    detail += "; bounded publication operation lease expired"
                if outcome == "PUBLISHED":
                    try:
                        target_watermark = self.repository_target_watermark()
                        if not self._publication_watermark_matches(
                            target_watermark, current, pinned_sha
                        ):
                            if (
                                target_watermark.get("target_generation")
                                != release_target_generation
                                or target_watermark.get("record_id")
                                != release_target_watermark_record_id
                                or target_watermark.get("target_sha")
                                != current.get("expected_target_sha")
                            ):
                                raise AutopilotError(
                                    "repository target watermark changed before "
                                    "publication outcome"
                                )
                            self.advance_repository_target_watermark(
                                expected_generation=release_target_generation,
                                expected_target_sha=str(
                                    current["expected_target_sha"]
                                ),
                                target_sha=pinned_sha,
                                source_release_id=str(current["release_id"]),
                                publication_transaction_id=str(
                                    current["transaction_id"]
                                ),
                                source_record=current,
                                actor=actor,
                            )
                    except Exception as error:
                        outcome = "PUBLISH_UNKNOWN"
                        detail += (
                            "; repository target watermark publication failed: "
                            + str(error)
                        )
                completed_at = format_time(self.clock())
                finished = dict(current)
                finished.update(
                    {
                        "status": outcome,
                        "pinned_sha": pinned_sha,
                        "outcome": outcome,
                        "detail": detail
                        + (
                            f"; push_exit_code={push_exit_code}"
                            if push_exit_code is not None
                            else ""
                        ),
                        "actor": actor,
                        "updated_at": completed_at,
                        "completed_at": completed_at,
                    }
                )
                finished = self._seal_publication_record(finished)
                self._write_publication_pair(
                    finished, detail=str(finished["detail"])
                )
                return finished

    def adjudicate_unknown_publication(
        self,
        transaction: Mapping[str, Any],
        *,
        actor: str,
    ) -> Mapping[str, Any]:
        """Resolve only what a fresh exact remote observation can prove.

        ``PUBLISH_UNKNOWN`` remains the installed repository fence while the
        network is observed without locks.  The original unknown event stays in
        the chained journal; this method appends a separately sealed observation
        as PUBLISHED or another PUBLISH_UNKNOWN.  Seeing the predecessor later
        is retryable current-state evidence, never proof that the original push
        was rejected.
        """

        supplied = self._validated_publication_transaction(
            transaction, label="indeterminate publication token"
        )
        if supplied.get("status") != "PUBLISH_UNKNOWN" or not actor.strip():
            raise AutopilotError(
                "publication adjudication requires an exact PUBLISH_UNKNOWN token"
            )
        with self._host_arbiter_guard():
            with self.execution_lock(
                "dispatcher-admission.lock", timeout_seconds=120.0
            ):
                resource_value = self._strict_json_file(
                    self._publication_resource_path(),
                    label="publication target reservation",
                )
                _, current = self._validated_publication_resource(
                    resource_value, label="publication target reservation"
                )
                if (
                    current.get("transaction_id")
                    != supplied.get("transaction_id")
                    or current.get("record_id") != supplied.get("record_id")
                    or current.get("status") != "PUBLISH_UNKNOWN"
                ):
                    if (
                        current.get("transaction_id")
                        == supplied.get("transaction_id")
                        and current.get("status") == "PUBLISHED"
                    ):
                        self._write_publication_pair(
                            current,
                            detail="publication adjudication evidence repaired",
                        )
                        return current
                    raise AutopilotError(
                        "indeterminate publication token differs from durable authority"
                    )
                release = self.current_release()
                if (
                    not isinstance(release, Mapping)
                    or release.get("release_id") != current.get("release_id")
                    or release.get("target_sha")
                    != current.get("expected_target_sha")
                ):
                    raise AutopilotError(
                        "publication adjudication release authority changed"
                    )
                sealed_record_id = str(current["record_id"])
                sealed_heads = list(current["receipt_heads"])
                expected = str(current["expected_target_sha"])
                pinned = str(current["pinned_sha"])
                transaction_ref = str(current["transaction_ref"])
                release = self.current_release()
                if not isinstance(release, Mapping):
                    raise AutopilotError(
                        "publication adjudication release is unavailable"
                    )
                release_target_generation = int(release["target_generation"])
                release_target_watermark_record_id = str(
                    release["target_watermark_record_id"]
                )
                starting_watermark = dict(self.repository_target_watermark())

        remote_target: str | None = None
        observed_heads: Mapping[str, str] = {}
        remote_transaction: str | None = None
        observation_error: str | None = None
        try:
            remote_target, observed_heads = self._observe_publication_remote(
                sealed_heads
            )
            remote_transaction = self._remote_ref_sha(transaction_ref)
        except Exception as error:
            observation_error = str(error)
        exact_heads = observation_error is None and all(
            observed_heads.get(str(item["node_id"])) == item["sha"]
            for item in sealed_heads
        )
        exact_transaction = remote_transaction == pinned
        descendant_target = False
        if (
            exact_heads
            and exact_transaction
            and isinstance(remote_target, str)
            and remote_target not in {expected, pinned}
        ):
            try:
                self._materialize_observed_publication_target(
                    str(supplied["transaction_id"]),
                    remote_target,
                    observation_key=digest_json(
                        {
                            "kind": (
                                "hive-mind-publication-target-preflight-ref-v1"
                            ),
                            "transaction_id": supplied["transaction_id"],
                            "observed_target_sha": remote_target,
                        }
                    ),
                )
                descendant_target = self.is_ancestor(pinned, remote_target)
            except Exception as error:
                observation_error = str(error)
        if exact_heads and exact_transaction and remote_target == pinned:
            outcome = "PUBLISHED"
            detail = "remote re-observation proves the pinned SHA was published"
        elif exact_heads and exact_transaction and descendant_target:
            outcome = "SUPERSEDED_INTEGRATED"
            detail = (
                "fresh remote and target-generation evidence prove the pinned "
                "publication is integrated in a newer target"
            )
        elif exact_heads and exact_transaction and remote_target == expected:
            outcome = "PUBLISH_UNKNOWN"
            detail = (
                "CURRENTLY_AT_PREDECESSOR: historical publication remains unknown; "
                "an accepted push followed by a revert is observationally identical; "
                "RETRYABLE_UNKNOWN requires a separately leased exact-CAS attempt"
            )
        else:
            outcome = "PUBLISH_UNKNOWN"
            detail = (
                "remote publication remains indeterminate"
                + (
                    f": {observation_error}"
                    if observation_error
                    else "; target or receipt heads advanced ambiguously"
                )
            )

        superseded_watermark_record_id: str | None = None
        if outcome == "SUPERSEDED_INTEGRATED" and isinstance(remote_target, str):
            try:
                superseded_watermark = self._seal_superseded_publication_watermark(
                    supplied,
                    sealed_record_id=sealed_record_id,
                    starting_watermark=starting_watermark,
                    observed_target_sha=remote_target,
                    observed_heads=observed_heads,
                    observed_transaction_sha=str(remote_transaction),
                    actor=actor,
                )
                superseded_watermark_record_id = str(
                    superseded_watermark["record_id"]
                )
            except Exception as error:
                outcome = "PUBLISH_UNKNOWN"
                detail = (
                    "remote target contains the pin but its monotonic repository "
                    "target generation could not be sealed and reobserved: "
                    + str(error)
                )

        with self._host_arbiter_guard():
            with self.execution_lock(
                "dispatcher-admission.lock", timeout_seconds=120.0
            ):
                resource_value = self._strict_json_file(
                    self._publication_resource_path(),
                    label="publication target reservation",
                )
                _, current = self._validated_publication_resource(
                    resource_value, label="publication target reservation"
                )
                if (
                    current.get("transaction_id")
                    != supplied.get("transaction_id")
                    or current.get("record_id") != sealed_record_id
                    or current.get("status") != "PUBLISH_UNKNOWN"
                ):
                    if (
                        current.get("transaction_id")
                        == supplied.get("transaction_id")
                        and current.get("status") == "PUBLISHED"
                    ):
                        self._write_publication_pair(
                            current,
                            detail="publication adjudication evidence repaired",
                        )
                        return current
                    raise AutopilotError(
                        "publication authority changed during remote adjudication"
                    )
                target_watermark = self.repository_target_watermark()
                if outcome == "PUBLISHED" and not self._publication_watermark_matches(
                    target_watermark, current, pinned
                ):
                    if (
                        target_watermark.get("target_generation")
                        != release_target_generation
                        or target_watermark.get("record_id")
                        != release_target_watermark_record_id
                        or target_watermark.get("target_sha") != expected
                    ):
                        outcome = "PUBLISH_UNKNOWN"
                        detail = (
                            "remote pinned target is exact but repository target "
                            "generation changed before adjudication"
                        )
                    else:
                        try:
                            target_watermark = (
                                self.advance_repository_target_watermark(
                                    expected_generation=release_target_generation,
                                    expected_target_sha=expected,
                                    target_sha=pinned,
                                    source_release_id=str(current["release_id"]),
                                    publication_transaction_id=str(
                                        current["transaction_id"]
                                    ),
                                    source_record=current,
                                    actor=actor,
                                )
                            )
                        except Exception as error:
                            outcome = "PUBLISH_UNKNOWN"
                            detail = (
                                "remote pinned target is exact but repository target "
                                "generation could not advance: "
                                + str(error)
                            )
                if outcome == "SUPERSEDED_INTEGRATED" and not (
                    isinstance(remote_target, str)
                    and target_watermark.get("target_sha") == remote_target
                    and target_watermark.get("record_id")
                    == superseded_watermark_record_id
                    and target_watermark.get("source_kind")
                    == "SUPERSEDED_PUBLICATION"
                    and target_watermark.get("source_execution_id")
                    == self.execution_id
                    and target_watermark.get("source_release_id")
                    == current.get("release_id")
                    and target_watermark.get("publication_transaction_id")
                    == current.get("transaction_id")
                    and descendant_target
                ):
                    outcome = "PUBLISH_UNKNOWN"
                    detail = (
                        "remote target contains the pin but no matching newer "
                        "repository target generation is durable"
                    )
                completed_at = format_time(self.clock())
                resolved = dict(current)
                resolved.update(
                    {
                        "status": outcome,
                        "outcome": outcome,
                        "detail": detail,
                        "actor": actor,
                        "updated_at": completed_at,
                        "completed_at": completed_at,
                    }
                )
                resolved = self._seal_publication_record(resolved)
                self._write_publication_pair(resolved, detail=detail)
                return resolved

    def finish_publication_transaction(
        self,
        transaction: Mapping[str, Any],
        *,
        pinned_sha: str | None,
        outcome: str,
        actor: str,
        detail: str,
    ) -> Mapping[str, Any]:
        """Terminalize a no-push/adverse transaction without discarding evidence."""

        allowed = {
            "VALIDATION_FAILED",
            "RECOVERY_REQUIRED",
            "NO_PUSH",
            "INTEGRATION_CONFLICT",
            "REJECTED",
        }
        if (
            outcome not in allowed
            or (pinned_sha is not None and FULL_SHA.fullmatch(pinned_sha) is None)
            or not actor.strip()
            or not detail.strip()
        ):
            raise AutopilotError("publication terminal disposition is invalid")
        supplied = self._validated_publication_transaction(
            transaction, label="publication terminal token"
        )
        with self._host_arbiter_guard():
            with self.execution_lock(
                "dispatcher-admission.lock", timeout_seconds=120.0
            ):
                resource_value = self._strict_json_file(
                    self._publication_resource_path(),
                    label="publication target reservation",
                )
                _, current = self._validated_publication_resource(
                    resource_value, label="publication target reservation"
                )
                if any(
                    current.get(field) != supplied.get(field)
                    for field in (
                        "transaction_id",
                        "transaction_key",
                        "execution_id",
                        "release_id",
                        "coordinator_id",
                        "transaction_lease_id",
                    )
                ):
                    raise AutopilotError(
                        "publication terminal disposition token is stale"
                    )
                if current.get("status") not in {
                    "PREPARED",
                    "PINNED",
                    "VALIDATED",
                    "PUBLISHING",
                }:
                    if (
                        current.get("outcome") == outcome
                        and current.get("pinned_sha") == pinned_sha
                    ):
                        self._write_publication_pair(
                            current,
                            detail="terminal publication evidence repaired",
                        )
                        return current
                    raise AutopilotError(
                        "publication transaction already has another terminal outcome"
                    )
                if current.get("status") == "PUBLISHING":
                    # A generic adverse/NO_PUSH path has no authority to decide an
                    # unlocked remote effect.  Only the exact PUBLISHING observer
                    # may append PUBLISHED/REJECTED/PUBLISH_UNKNOWN; otherwise a
                    # concurrent finisher could reopen admission while the push
                    # succeeds.
                    raise AutopilotError(
                        "PUBLISHING can only be resolved by exact remote publication "
                        "observation"
                    )
                current_pin = current.get("pinned_sha")
                if current.get("status") == "PREPARED":
                    if pinned_sha is not None:
                        raise AutopilotError(
                            "PREPARED terminalization cannot invent a pinned SHA"
                        )
                elif pinned_sha != current_pin:
                    raise AutopilotError(
                        "publication terminal disposition must preserve the exact "
                        "durable pinned SHA"
                    )
                if outcome == "NO_PUSH" and current.get("status") != "VALIDATED":
                    raise AutopilotError(
                        "NO_PUSH requires the exact fixed-gate capability"
                    )
                if current.get("record_id") != supplied.get("record_id"):
                    raise AutopilotError(
                        "publication terminal token is not the current exact lease record"
                    )
                if parse_time(current.get("lease_expires_at")) <= self.clock():
                    raise AutopilotError(
                        "publication coordinator lease expired before terminal disposition"
                    )
                now = format_time(self.clock())
                finished = dict(current)
                finished.update(
                    {
                        "status": outcome,
                        "pinned_sha": pinned_sha,
                        "outcome": outcome,
                        "detail": detail,
                        "actor": actor,
                        "updated_at": now,
                        "completed_at": now,
                    }
                )
                finished = self._seal_publication_record(finished)
                self._write_publication_pair(finished, detail=detail)
                return finished

    def _dispatch_identity_at(self, target_sha: str) -> Mapping[str, str]:
        """Authenticate local scheduling inputs against one exact target commit.

        Snapshot observations fetch into a private ref first, so the candidate can be
        newer than ``origin/<target>`` without being allowed to change that canonical
        ref before its plan and repository identity have been authenticated.
        """

        local_repository = str(self.control["target"]["repository"])
        local_branch = self.target_branch
        local_fingerprint = self.expected_plan_fingerprint
        if self.plan_fingerprint != local_fingerprint:
            raise AutopilotError(
                "local dispatcher plan does not match its control-plane fingerprint"
            )
        if FULL_SHA.fullmatch(target_sha) is None:
            raise AutopilotError("dispatcher target identity requires a full Git SHA")
        if not self.verify_git_objects:
            return {
                "repository": local_repository,
                "target_branch": local_branch,
                "target_sha": target_sha,
                "plan_fingerprint": local_fingerprint,
            }
        if not self.git_object_exists(target_sha):
            raise AutopilotError("dispatcher target identity commit is unavailable")
        documents: dict[str, Mapping[str, Any]] = {}
        document_contracts = (
            (
                "control-plane.json",
                TARGET_CONTROL_FIELDS,
                MAX_TARGET_CONTROL_BYTES,
            ),
            ("plan.json", TARGET_PLAN_FIELDS, MAX_TARGET_PLAN_BYTES),
        )
        for name, expected_fields, maximum_bytes in document_contracts:
            completed = self._git(
                ("show", f"{target_sha}:.autopilot/{name}"),
                check=False,
            )
            if completed.returncode != 0:
                raise AutopilotError(
                    f"live target lacks canonical dispatcher input .autopilot/{name}"
                )
            raw = completed.stdout.encode("utf-8")
            if not raw or len(raw) > maximum_bytes:
                raise AutopilotError(
                    f"live target dispatcher input .autopilot/{name} exceeds its "
                    "bounded authority envelope"
                )
            try:
                value = parse_strict_canonical_json_bytes(
                    raw,
                    label=f"live target dispatcher input .autopilot/{name}",
                    expected_fields=expected_fields,
                )
            except ConfigurationError as error:
                raise AutopilotError(str(error)) from error
            if not isinstance(value, Mapping):
                raise AutopilotError(
                    f"live target dispatcher input .autopilot/{name} is not an object"
                )
            documents[name] = value
        canonical_control = documents["control-plane.json"]
        target_plan = documents["plan.json"]
        canonical_plan = dict(target_plan)
        embedded_fingerprint = canonical_plan.pop("plan_fingerprint", None)
        canonical_fingerprint = canonical_control.get("plan_fingerprint")
        canonical_target = canonical_control.get("target")
        baseline = target_plan.get("baseline")
        nodes = target_plan.get("nodes")
        state_machine = target_plan.get("state_machine")
        protected = (
            canonical_target.get("protected_until_final_integration")
            if isinstance(canonical_target, Mapping)
            else None
        )
        if (
            canonical_control.get("schema_version") != 1
            or target_plan.get("schema_version") != 1
            or not isinstance(canonical_fingerprint, str)
            or embedded_fingerprint != canonical_fingerprint
            or canonical_fingerprint != digest_json(canonical_plan)
            or canonical_control.get("plan_id") != target_plan.get("plan_id")
            or not isinstance(target_plan.get("plan_id"), str)
            or not str(target_plan["plan_id"]).strip()
            or not isinstance(canonical_target, Mapping)
            or set(canonical_target) != TARGET_CONTROL_TARGET_FIELDS
            or not isinstance(canonical_target.get("repository"), str)
            or not str(canonical_target["repository"]).strip()
            or not isinstance(canonical_target.get("branch"), str)
            or not str(canonical_target["branch"]).strip()
            or not isinstance(canonical_target.get("execution_mode"), str)
            or type(canonical_control.get("verify_git_objects")) is not bool
            or type(canonical_control.get("default_claim_lease_minutes")) is not int
            or int(canonical_control["default_claim_lease_minutes"]) < 1
            or type(canonical_control.get("max_consultation_rounds")) is not int
            or int(canonical_control["max_consultation_rounds"]) < 1
            or any(
                not isinstance(canonical_control.get(field), str)
                or not str(canonical_control[field]).strip()
                for field in ("plan_id", "orchestration_policy_file", "workflow_policy_file")
            )
            or any(
                not isinstance(canonical_control.get(field), list)
                or any(
                    not isinstance(item, str) or not item.strip()
                    for item in canonical_control[field]
                )
                for field in ("prohibitions", "source_of_truth")
            )
            or not isinstance(canonical_control.get("bootstrap_completion"), Mapping)
            or any(
                not isinstance(canonical_target.get(field), str)
                or not str(canonical_target[field]).strip()
                for field in (
                    "baseline_observed_at",
                    "baseline_rule",
                    "baseline_sha",
                    "baseline_tree",
                    "execution_mode",
                    "final_integration_branch",
                    "release_branch_base",
                )
            )
            or FULL_SHA.fullmatch(str(canonical_target.get("baseline_sha"))) is None
            or FULL_SHA.fullmatch(str(canonical_target.get("baseline_tree"))) is None
            or (
                FULL_SHA.fullmatch(
                    str(canonical_target.get("release_branch_base"))
                )
                is None
            )
            or not isinstance(protected, list)
            or any(not isinstance(item, str) or not item for item in protected)
            or not isinstance(baseline, Mapping)
            or set(baseline) != {"branch", "commit", "tree"}
            or not isinstance(baseline.get("branch"), str)
            or FULL_SHA.fullmatch(str(baseline.get("commit"))) is None
            or FULL_SHA.fullmatch(str(baseline.get("tree"))) is None
            or not isinstance(target_plan.get("created_at"), str)
            or not isinstance(target_plan.get("subject"), str)
            or not isinstance(target_plan.get("title"), str)
            or not isinstance(nodes, list)
            or not nodes
            or any(
                not isinstance(node, Mapping)
                or not isinstance(node.get("id"), str)
                or not str(node["id"]).strip()
                for node in nodes
            )
            or not isinstance(state_machine, list)
            or not state_machine
            or any(not isinstance(state, str) or not state for state in state_machine)
        ):
            raise AutopilotError("live target canonical dispatcher identity is malformed")
        canonical_repository = str(canonical_target["repository"])
        canonical_branch = str(canonical_target["branch"])
        if (
            local_repository != canonical_repository
            or local_branch != canonical_branch
            or local_fingerprint != canonical_fingerprint
        ):
            raise AutopilotError(
                "worktree dispatcher inputs are stale relative to the live target commit"
            )
        return {
            "repository": canonical_repository,
            "target_branch": canonical_branch,
            "target_sha": target_sha,
            "plan_fingerprint": canonical_fingerprint,
        }

    def _canonical_dispatch_identity(self) -> Mapping[str, str]:
        """Authenticate local scheduling inputs against the live target commit."""

        target_sha: str | None = None
        for reference in (
            self.execution_target_ref,
            f"refs/remotes/origin/{self.target_branch}",
            f"refs/heads/{self.target_branch}",
        ):
            resolved = self._git(("rev-parse", "--verify", reference), check=False)
            candidate = resolved.stdout.strip()
            if resolved.returncode == 0 and FULL_SHA.fullmatch(candidate):
                target_sha = candidate
                break
        if target_sha is None:
            fallback = self.current_target_sha()
            if self.verify_git_objects:
                raise AutopilotError(
                    "cannot resolve the configured target branch for dispatcher authority"
                )
            # Lightweight fixtures may intentionally have no commits. Only that
            # isolated case falls back to their locally sealed control inputs.
            return {
                "repository": str(self.control["target"]["repository"]),
                "target_branch": self.target_branch,
                "target_sha": fallback,
                "plan_fingerprint": self.expected_plan_fingerprint,
            }
        return self._dispatch_identity_at(target_sha)

    def _dispatcher_generation(self) -> Mapping[str, Any] | None:
        if not self.dispatcher_generation_path.is_file():
            return None
        value = self._strict_json_file(
            self.dispatcher_generation_path,
            label="dispatcher admission generation",
        )
        return value if isinstance(value, Mapping) else None

    def _snapshot_observation(self) -> Mapping[str, Any] | None:
        if not self.snapshot_observation_path.is_file():
            return None
        value = self._strict_json_file(
            self.snapshot_observation_path,
            label="GitHub snapshot observation",
        )
        return value if isinstance(value, Mapping) else None

    def current_release(self) -> Mapping[str, Any] | None:
        if not self.current_release_path.is_file():
            return None
        value = self._strict_json_file(
            self.current_release_path, label="execution dispatcher release"
        )
        return value if isinstance(value, Mapping) else None

    @staticmethod
    def _snapshot_fetch_ref(
        execution_id: str, observation_epoch: int, observation_id: str
    ) -> str:
        """Return the only Git ref an observation token may fetch into."""

        if (
            AUTHORITY_ID.fullmatch(execution_id) is None
            or observation_epoch < 1
            or AUTHORITY_ID.fullmatch(observation_id) is None
        ):
            raise AutopilotError("snapshot observation fetch authority is invalid")
        reference_id = digest_json(
            {
                "kind": "hive-mind-snapshot-observation-evidence-ref-v1",
                "execution_id": execution_id,
                "observation_epoch": observation_epoch,
                "observation_id": observation_id,
            }
        )
        return "refs/heads/hme/s/" + reference_id.removeprefix("sha256:")

    @staticmethod
    def _snapshot_branch_fetch_ref(
        execution_id: str,
        observation_epoch: int,
        observation_id: str,
        node_id: str,
        branch: str,
    ) -> str:
        reference_id = digest_json(
            {
                "kind": "hive-mind-snapshot-branch-evidence-ref-v1",
                "execution_id": execution_id,
                "observation_epoch": observation_epoch,
                "observation_id": observation_id,
                "node_id": node_id,
                "branch": branch,
            }
        )
        return "refs/heads/hme/b/" + reference_id.removeprefix("sha256:")

    def _snapshot_branch_fetches(
        self, observation_epoch: int, observation_id: str
    ) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        for node_id in sorted(self._nodes):
            branch = self.node(node_id).get("branch")
            if not isinstance(branch, str) or not branch.strip():
                raise AutopilotError(
                    f"snapshot observation node {node_id} has no canonical branch"
                )
            result.append(
                {
                    "node_id": node_id,
                    "branch": branch,
                    "fetch_ref": self._snapshot_branch_fetch_ref(
                        self.execution_id,
                        observation_epoch,
                        observation_id,
                        node_id,
                        branch,
                    ),
                }
            )
        return result

    @staticmethod
    def _canonical_json_bytes(value: object) -> bytes:
        try:
            rendered = json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
        except (TypeError, ValueError) as error:
            raise AutopilotError("JSON evidence is not canonically serializable") from error
        return (rendered + "\n").encode("utf-8")

    @staticmethod
    def _strict_json_bytes(raw: bytes, *, label: str) -> object:
        def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"duplicate JSON key: {key}")
                result[key] = value
            return result

        def reject_constant(value: str) -> object:
            raise ValueError(f"nonfinite JSON number: {value}")

        try:
            return json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=reject_duplicates,
                parse_constant=reject_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise AutopilotError(f"{label} is not strict JSON: {error}") from error

    def _strict_json_file(self, path: Path, *, label: str) -> object:
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise AutopilotError(f"{label} is unavailable: {error}") from error
        return self._strict_json_bytes(raw, label=label)

    def _write_immutable_json(self, path: Path, value: object) -> Path:
        """Create immutable exact evidence, accepting only an identical retry."""

        payload = self._canonical_json_bytes(value)
        try:
            relative = path.relative_to(self.execution_dir)
        except ValueError as error:
            raise AutopilotError(
                "immutable execution evidence must remain in its namespace"
            ) from error
        path = self._secure_execution_path(relative)
        self._ensure_authority_directory(self.execution_dir, path.parent)
        path = self._secure_execution_path(relative)
        # Keep the O_EXCL private name short enough for ordinary Windows path
        # limits even when the immutable evidence filename is already a digest.
        temporary = path.parent / f".{secrets.token_hex(8)}.tmp"
        descriptor: int | None = None
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_BINARY", 0),
                0o600,
            )
            with os.fdopen(descriptor, "wb", closefd=True) as handle:
                descriptor = None
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path)
                self._fsync_directory(path.parent)
            except FileExistsError:
                try:
                    current = path.read_bytes()
                except OSError as error:
                    raise AutopilotError(
                        f"immutable evidence collision is unreadable: {path}"
                    ) from error
                if current != payload:
                    raise AutopilotError(
                        f"immutable evidence collision differs from sealed bytes: {path}"
                    )
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if temporary.exists():
                temporary.unlink()
                self._fsync_directory(temporary.parent)
        return path

    def _write_immutable_authority_json(
        self, root: Path, path: Path, value: object
    ) -> Path:
        """Create identical-only immutable evidence inside an authority root."""

        if self._is_link_like(root):
            raise AutopilotError("immutable authority root is a link or junction")
        root = root.resolve(strict=False)
        try:
            relative = path.relative_to(root)
        except ValueError as error:
            raise AutopilotError("immutable authority path escapes its root") from error
        current = root
        for component in relative.parts:
            current = current / component
            if current.exists() and self._is_link_like(current):
                raise AutopilotError(
                    f"immutable authority path traverses a link or junction: {current}"
                )
        payload = self._canonical_json_bytes(value)
        self._ensure_authority_directory(root, path.parent)
        temporary = path.parent / f".{path.name}.{secrets.token_hex(16)}.tmp"
        descriptor: int | None = None
        try:
            descriptor = os.open(
                temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
            with os.fdopen(descriptor, "wb", closefd=True) as handle:
                descriptor = None
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path)
                self._fsync_directory(path.parent)
            except FileExistsError:
                if path.read_bytes() != payload:
                    raise AutopilotError(
                        "immutable authority archive collides with different bytes"
                    )
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if temporary.exists():
                temporary.unlink()
                self._fsync_directory(temporary.parent)
        return path

    @staticmethod
    def _snapshot_candidate_artifact(
        observation_id: str, snapshot_digest: str
    ) -> str:
        if (
            AUTHORITY_ID.fullmatch(observation_id) is None
            or AUTHORITY_ID.fullmatch(snapshot_digest) is None
        ):
            raise AutopilotError("snapshot candidate artifact authority is invalid")
        artifact_id = digest_json(
            {
                "kind": "hive-mind-snapshot-candidate-artifact-v1",
                "observation_id": observation_id,
                "snapshot_digest": snapshot_digest,
            }
        )
        return f"sc/{artifact_id.removeprefix('sha256:')}.json"

    @staticmethod
    def _legacy_snapshot_candidate_artifact(
        observation_id: str, snapshot_digest: str
    ) -> str:
        return (
            "github-snapshot-candidates/"
            f"{observation_id.removeprefix('sha256:')}/"
            f"{snapshot_digest.removeprefix('sha256:')}.json"
        )

    def _pending_snapshot_candidate(
        self, observation: Mapping[str, Any]
    ) -> Mapping[str, Any] | None:
        """Adopt only the one exact artifact left before INSTALLING was durable."""

        observation_id = str(observation.get("observation_id"))
        candidate_root = self.snapshot_candidate_dir
        using_legacy_layout = candidate_root.name == "github-snapshot-candidates"
        directory = self._secure_execution_path(
            candidate_root.relative_to(self.execution_dir)
            / (
                observation_id.removeprefix("sha256:")
                if using_legacy_layout
                else ""
            )
        )
        if not directory.exists():
            return None
        if self._is_link_like(directory) or not directory.is_dir():
            raise AutopilotError(
                "pending GitHub snapshot candidate directory is not private authority"
            )
        matches: list[tuple[Path, Mapping[str, Any], str]] = []
        for path in sorted(directory.iterdir(), key=lambda item: item.name):
            if self._is_link_like(path) or not path.is_file():
                raise AutopilotError("pending snapshot candidate artifact is invalid")
            candidate = self._strict_json_file(
                path, label="pending immutable GitHub snapshot candidate"
            )
            issues = self._snapshot_candidate_issues(candidate, observation)
            if issues or not isinstance(candidate, Mapping):
                if using_legacy_layout:
                    raise AutopilotError(
                        "pending immutable GitHub snapshot candidate is invalid: "
                        + "; ".join(issues)
                    )
                continue
            snapshot_digest = digest_json(candidate)
            expected = self._secure_execution_path(
                self._snapshot_candidate_artifact(observation_id, snapshot_digest)
            )
            legacy_expected = self._secure_execution_path(
                self._legacy_snapshot_candidate_artifact(
                    observation_id, snapshot_digest
                )
            )
            if path in {expected, legacy_expected}:
                matches.append((path, candidate, snapshot_digest))
        if len(matches) != 1:
            if not matches:
                return None
            raise AutopilotError(
                "pending snapshot recovery requires exactly one immutable candidate"
            )
        path, candidate, snapshot_digest = matches[0]
        expected_paths = {
            self._secure_execution_path(
                self._snapshot_candidate_artifact(observation_id, snapshot_digest)
            ),
            self._secure_execution_path(
                self._legacy_snapshot_candidate_artifact(
                    observation_id, snapshot_digest
                )
            ),
        }
        if path not in expected_paths:
            raise AutopilotError(
                "pending snapshot candidate path differs from its canonical digest"
            )
        return dict(candidate)

    @staticmethod
    def _snapshot_observation_issues(value: object) -> tuple[str, ...]:
        if not isinstance(value, Mapping):
            return ("shared GitHub snapshot observation is missing or malformed",)
        material = dict(value)
        record_id = material.pop("record_id", None)
        issues: list[str] = []
        required = {
            "schema_version",
            "kind",
            "status",
            "execution_namespace",
            "execution_id",
            "observation_epoch",
            "observation_id",
            "fetch_ref",
            "branch_fetches",
            "repository",
            "target_branch",
            "base_target_sha",
            "target_sha",
            "plan_fingerprint",
            "snapshot_digest",
            "candidate_artifact",
            "supersedes_observation_id",
            "actor",
            "began_at",
            "expires_at",
            "installed_at",
            "record_id",
        }
        if set(value) != required:
            issues.append("shared GitHub snapshot observation fields are invalid")
        if (
            value.get("schema_version") != 2
            or value.get("kind") != SNAPSHOT_OBSERVATION_KIND
        ):
            issues.append("shared GitHub snapshot observation schema/kind is invalid")
        execution_namespace = value.get("execution_namespace")
        execution_id = value.get("execution_id")
        if not isinstance(execution_namespace, str) or not execution_namespace:
            issues.append("shared GitHub snapshot execution namespace is invalid")
        if not isinstance(execution_id, str) or AUTHORITY_ID.fullmatch(execution_id) is None:
            issues.append("shared GitHub snapshot execution id is invalid")
        if record_id != digest_json(material):
            issues.append("shared GitHub snapshot observation digest is invalid")
        if type(value.get("observation_epoch")) is not int or int(
            value.get("observation_epoch", 0)
        ) < 1:
            issues.append("shared GitHub snapshot observation epoch is invalid")
        observation_id = value.get("observation_id")
        if not isinstance(observation_id, str) or AUTHORITY_ID.fullmatch(observation_id) is None:
            issues.append("shared GitHub snapshot observation id is invalid")
        if (
            isinstance(execution_id, str)
            and AUTHORITY_ID.fullmatch(execution_id) is not None
            and
            isinstance(observation_id, str)
            and AUTHORITY_ID.fullmatch(observation_id) is not None
            and type(value.get("observation_epoch")) is int
            and int(value["observation_epoch"]) >= 1
        ):
            expected_ref = ControlPlane._snapshot_fetch_ref(
                str(execution_id), int(value["observation_epoch"]), observation_id
            )
            if value.get("fetch_ref") != expected_ref:
                issues.append("shared GitHub snapshot observation fetch ref is invalid")
        elif not isinstance(value.get("fetch_ref"), str):
            issues.append("shared GitHub snapshot observation fetch ref is invalid")
        branch_fetches = value.get("branch_fetches")
        if not isinstance(branch_fetches, list):
            issues.append("shared GitHub snapshot observation branch fetches are invalid")
        else:
            seen_nodes: set[str] = set()
            seen_branches: set[str] = set()
            seen_refs: set[str] = set()
            for item in branch_fetches:
                if not isinstance(item, Mapping) or set(item) != {
                    "node_id",
                    "branch",
                    "fetch_ref",
                }:
                    issues.append(
                        "shared GitHub snapshot observation branch fetch entry is invalid"
                    )
                    continue
                node_id = item.get("node_id")
                branch = item.get("branch")
                branch_ref = item.get("fetch_ref")
                if (
                    not isinstance(node_id, str)
                    or not node_id
                    or not isinstance(branch, str)
                    or not branch
                    or not isinstance(branch_ref, str)
                    or not isinstance(execution_id, str)
                    or AUTHORITY_ID.fullmatch(execution_id) is None
                    or not isinstance(observation_id, str)
                    or AUTHORITY_ID.fullmatch(observation_id) is None
                    or type(value.get("observation_epoch")) is not int
                    or value["observation_epoch"] < 1
                    or branch_ref
                    != ControlPlane._snapshot_branch_fetch_ref(
                        execution_id,
                        int(value["observation_epoch"]),
                        observation_id,
                        node_id,
                        branch,
                    )
                ):
                    issues.append(
                        "shared GitHub snapshot observation branch fetch authority is invalid"
                    )
                if (
                    node_id in seen_nodes
                    or branch in seen_branches
                    or branch_ref in seen_refs
                ):
                    issues.append(
                        "shared GitHub snapshot observation branch fetches are duplicated"
                    )
                seen_nodes.add(str(node_id))
                seen_branches.add(str(branch))
                seen_refs.add(str(branch_ref))
        if value.get("status") not in {
            "PENDING",
            "INSTALLING",
            "INSTALLED",
            "SUPERSEDED",
        }:
            issues.append("shared GitHub snapshot observation status is invalid")
        if not isinstance(value.get("repository"), str) or not value.get("repository"):
            issues.append("shared GitHub snapshot observation repository is invalid")
        if not isinstance(value.get("target_branch"), str) or not value.get("target_branch"):
            issues.append("shared GitHub snapshot observation target branch is invalid")
        for field, label in (
            ("base_target_sha", "base target SHA"),
            ("target_sha", "target SHA"),
        ):
            if not isinstance(value.get(field), str) or FULL_SHA.fullmatch(
                str(value.get(field))
            ) is None:
                issues.append(f"shared GitHub snapshot observation {label} is invalid")
        if (
            value.get("status") == "PENDING"
            and value.get("target_sha") != value.get("base_target_sha")
        ):
            issues.append("pending GitHub snapshot observation changed its target SHA")
        fingerprint = value.get("plan_fingerprint")
        if not isinstance(fingerprint, str) or AUTHORITY_ID.fullmatch(fingerprint) is None:
            issues.append("shared GitHub snapshot observation plan fingerprint is invalid")
        snapshot_digest = value.get("snapshot_digest")
        if value.get("status") in {"INSTALLING", "INSTALLED", "SUPERSEDED"}:
            if not isinstance(snapshot_digest, str) or AUTHORITY_ID.fullmatch(
                snapshot_digest
            ) is None:
                issues.append("shared GitHub snapshot observation candidate digest is invalid")
            candidate_artifact = value.get("candidate_artifact")
            if (
                isinstance(observation_id, str)
                and isinstance(snapshot_digest, str)
                and AUTHORITY_ID.fullmatch(observation_id) is not None
                and AUTHORITY_ID.fullmatch(snapshot_digest) is not None
            ):
                expected_artifact = ControlPlane._snapshot_candidate_artifact(
                    observation_id, snapshot_digest
                )
                legacy_artifact = (
                    ControlPlane._legacy_snapshot_candidate_artifact(
                        observation_id, snapshot_digest
                    )
                )
                if candidate_artifact not in {expected_artifact, legacy_artifact}:
                    issues.append(
                        "shared GitHub snapshot observation candidate artifact is invalid"
                    )
            elif candidate_artifact is not None:
                issues.append(
                    "shared GitHub snapshot observation candidate artifact is invalid"
                )
        elif snapshot_digest is not None:
            issues.append("pending shared GitHub snapshot observation has a candidate digest")
        elif value.get("candidate_artifact") is not None:
            issues.append("pending shared GitHub snapshot observation has a candidate artifact")
        supersedes = value.get("supersedes_observation_id")
        if supersedes is not None and (
            not isinstance(supersedes, str)
            or AUTHORITY_ID.fullmatch(supersedes) is None
            or supersedes == observation_id
        ):
            issues.append("shared GitHub snapshot supersession authority is invalid")
        if not isinstance(value.get("actor"), str) or not str(value.get("actor")).strip():
            issues.append("shared GitHub snapshot observation actor is invalid")
        try:
            began_at = parse_time(value.get("began_at"))
            expires_at = parse_time(value.get("expires_at"))
            if expires_at <= began_at:
                issues.append(
                    "shared GitHub snapshot observation expiry does not follow its start"
                )
        except (ConfigurationError, TypeError, ValueError):
            began_at = None
            issues.append("shared GitHub snapshot observation time authority is invalid")
        installed_at = value.get("installed_at")
        if value.get("status") in {"INSTALLED", "SUPERSEDED"}:
            try:
                parsed_installed = parse_time(installed_at)
                if began_at is not None and parsed_installed < began_at:
                    issues.append(
                        "installed GitHub snapshot observation predates its start"
                    )
            except (ConfigurationError, TypeError, ValueError):
                issues.append("terminal GitHub snapshot observation time is invalid")
        elif installed_at is not None:
            issues.append("unfinished GitHub snapshot observation has an install time")
        return tuple(dict.fromkeys(issues))

    @staticmethod
    def _seal_snapshot_observation(record: Mapping[str, Any]) -> dict[str, Any]:
        sealed = dict(record)
        sealed.pop("record_id", None)
        sealed["record_id"] = digest_json(sealed)
        return sealed

    def _snapshot_observation_dispatch_issues(
        self,
        expected_snapshot_digest: object,
        *,
        expected_observation_id: object = None,
        expected_observation_epoch: object = None,
        expected_observation_record_id: object = None,
        expected_target_sha: object = None,
        expected_plan_fingerprint: object = None,
    ) -> tuple[str, ...]:
        """Treat an in-flight shared observation as an execution fence.

        No legacy exception is allowed: a generation or release without an exact
        installed observation binding is preserved as evidence but is nonlive.
        """

        observation = self._snapshot_observation()
        issues = list(self._snapshot_observation_issues(observation))
        if not issues:
            assert isinstance(observation, Mapping)
            if (
                observation.get("execution_namespace") != self.execution_namespace
                or observation.get("execution_id") != self.execution_id
            ):
                issues.append(
                    "shared GitHub snapshot observation execution identity mismatch"
                )
            if observation.get("branch_fetches") != self._snapshot_branch_fetches(
                int(observation["observation_epoch"]),
                str(observation["observation_id"]),
            ):
                issues.append(
                    "shared GitHub snapshot observation branch inventory differs from "
                    "the canonical plan"
                )
            if observation.get("status") != "INSTALLED":
                issues.append("shared GitHub snapshot observation is still in progress")
            try:
                if parse_time(observation.get("expires_at")) <= self.clock():
                    issues.append(
                        "shared GitHub snapshot observation expired; refresh is required"
                    )
            except Exception:
                # Structural timestamp diagnostics are already emitted above.
                pass
            artifact = observation.get("candidate_artifact")
            if isinstance(artifact, str):
                try:
                    candidate = self._strict_json_file(
                        self._secure_execution_path(artifact),
                        label="immutable GitHub snapshot candidate",
                    )
                    if digest_json(candidate) != observation.get("snapshot_digest"):
                        issues.append(
                            "shared GitHub snapshot immutable candidate digest mismatch"
                        )
                    issues.extend(self._snapshot_candidate_issues(candidate, observation))
                    query = (
                        candidate.get("github_query")
                        if isinstance(candidate, Mapping)
                        else None
                    )
                    if (
                        not isinstance(query, Mapping)
                        or query.get("evidence_available") is not True
                        or query.get("complete") is not True
                    ):
                        issues.append(
                            "GitHub pull-request evidence is unavailable or incomplete; "
                            "refresh online before dispatch"
                        )
                except AutopilotError as error:
                    issues.append(str(error))
            else:
                issues.append(
                    "shared GitHub snapshot immutable candidate evidence is missing"
                )
            if (
                not isinstance(expected_snapshot_digest, str)
                or observation.get("snapshot_digest") != expected_snapshot_digest
            ):
                issues.append("shared GitHub snapshot observation evidence mismatch")
            comparisons = (
                ("observation_id", expected_observation_id, "id"),
                ("observation_epoch", expected_observation_epoch, "epoch"),
                ("record_id", expected_observation_record_id, "record digest"),
                ("target_sha", expected_target_sha, "target SHA"),
                ("plan_fingerprint", expected_plan_fingerprint, "plan fingerprint"),
            )
            for field, expected, label in comparisons:
                if expected is not None and observation.get(field) != expected:
                    issues.append(
                        f"shared GitHub snapshot observation {label} fence mismatch"
                    )
        return tuple(dict.fromkeys(issues))

    @contextmanager
    def _snapshot_reservation_guard(self):
        """Serialize only global transport/ref identity before execution reservation."""

        with self.host_lock(timeout_seconds=120.0):
            with self.arbiter_lock(timeout_seconds=120.0):
                with self.execution_lock(
                    "dispatcher-admission.lock", timeout_seconds=120.0
                ):
                    self.assert_canonical_remote_transport_identity()
                    self._assert_no_global_host_reservations(
                        "GitHub snapshot observation"
                    )
                    yield

    def _assert_execution_not_terminal_unlocked(self, operation: str) -> None:
        """Reject every controller mutation after durable plan quiescence."""

        fence = self._read_plan_terminal_fence_unlocked()
        if fence is not None:
            raise AutopilotError(
                f"{operation} is closed by the execution terminal fence "
                f"{fence['record_id']}"
            )

    @contextmanager
    def _host_arbiter_guard(self):
        with self.host_lock(timeout_seconds=120.0):
            with self.arbiter_lock(timeout_seconds=120.0):
                yield

    @contextmanager
    def _host_arbiter_execution_guard(self):
        with self._host_arbiter_guard():
            with self.execution_lock(
                "dispatcher-admission.lock", timeout_seconds=120.0
            ):
                yield

    def begin_github_snapshot_observation(self, *, actor: str) -> Mapping[str, Any]:
        """Reserve a monotonic cross-worktree observation before external reads.

        A slower observation that began first can never install after a newer one. The
        reservation is deliberately taken before ``git fetch``/``gh`` reads, not when
        their already-stale bytes eventually reach the installer.
        """

        if not actor.strip():
            raise AutopilotError("GitHub snapshot observation actor is required")
        with self._snapshot_reservation_guard():
            self._assert_execution_not_terminal_unlocked(
                "GitHub snapshot observation"
            )
            self._assert_no_execution_launch_reservations(
                "GitHub snapshot observation"
            )
            self._assert_no_publication_transaction(
                "GitHub snapshot observation"
            )
            active = self.active_claims()
            if active:
                raise AutopilotError(
                    "GitHub snapshot observation is deferred while shared claims are active"
                )
            canonical = self._canonical_dispatch_identity()
            previous = self._snapshot_observation()
            observation_epoch = 1
            supersedes_observation_id: str | None = None
            if previous is not None:
                issues = self._snapshot_observation_issues(previous)
                if issues:
                    raise AutopilotError("; ".join(issues))
                if any(
                    previous.get(field) != canonical[field]
                    for field in ("repository", "target_branch", "plan_fingerprint")
                ) or previous.get("execution_id") != self.execution_id:
                    raise AutopilotError(
                        "snapshot observation namespace differs from canonical authority"
                    )
                if previous.get("branch_fetches") != self._snapshot_branch_fetches(
                    int(previous["observation_epoch"]),
                    str(previous["observation_id"]),
                ):
                    raise AutopilotError(
                        "snapshot observation branch inventory differs from canonical plan"
                    )
                if previous.get("status") in {"PENDING", "INSTALLING"}:
                    if parse_time(previous.get("expires_at")) > self.clock():
                        # Single-flight: autonomous applications join the same exact
                        # remote read instead of endlessly superseding each other.
                        return previous
                    archive_material: dict[str, Any] = {
                        "schema_version": 1,
                        "kind": SNAPSHOT_OBSERVATION_ARCHIVE_KIND,
                        "disposition": "EXPIRED",
                        "observation_id": previous["observation_id"],
                        "observation_record_id": previous["record_id"],
                        "observation": dict(previous),
                    }
                    archive_material["archive_id"] = digest_json(archive_material)
                    archive_path = self.snapshot_observation_archive_dir / (
                        f"{int(previous['observation_epoch']):020d}-"
                        f"{str(previous['observation_id']).removeprefix('sha256:')}.json"
                    )
                    self._write_immutable_json(archive_path, archive_material)
                raw_epoch = previous.get("observation_epoch")
                if type(raw_epoch) is int and raw_epoch >= 1:
                    observation_epoch = raw_epoch + 1
                supersedes_observation_id = str(previous["observation_id"])
            generation = self._dispatcher_generation()
            if generation is not None:
                generation_issues = self._dispatcher_generation_issues(
                    generation,
                    require_observation_binding=False,
                )
                if generation_issues:
                    raise AutopilotError("; ".join(generation_issues))
                generation_epoch = generation.get("snapshot_observation_epoch")
                generation_observation_id = generation.get(
                    "snapshot_observation_id"
                )
                if previous is None and (
                    generation_observation_id is not None
                    or generation_epoch is not None
                ):
                    raise AutopilotError(
                        "shared snapshot observation evidence is missing; automatic "
                        "replacement would erase the execution fence"
                    )
                if type(generation_epoch) is int and generation_epoch >= observation_epoch:
                    observation_epoch = generation_epoch + 1
                snapshot_digest = generation.get("github_snapshot_digest")
                if snapshot_digest is not None and (
                    not isinstance(snapshot_digest, str)
                    or AUTHORITY_ID.fullmatch(snapshot_digest) is None
                ):
                    raise AutopilotError(
                        "shared dispatcher generation has invalid snapshot evidence"
                    )
            else:
                snapshot_digest = None
            observation_material = {
                "nonce": secrets.token_hex(32),
                "execution_id": self.execution_id,
                "observation_epoch": observation_epoch,
                "repository": canonical["repository"],
                "target_branch": canonical["target_branch"],
                "target_sha": canonical["target_sha"],
                "plan_fingerprint": canonical["plan_fingerprint"],
            }
            observation_id = digest_json(observation_material)
            fetch_ref = self._snapshot_fetch_ref(
                self.execution_id, observation_epoch, observation_id
            )
            branch_fetches = self._snapshot_branch_fetches(
                observation_epoch, observation_id
            )
            now = self.clock()
            record = self._seal_snapshot_observation(
                {
                    "schema_version": 2,
                    "kind": SNAPSHOT_OBSERVATION_KIND,
                    "status": "PENDING",
                    "execution_namespace": self.execution_namespace,
                    "execution_id": self.execution_id,
                    "observation_epoch": observation_epoch,
                    "observation_id": observation_id,
                    "fetch_ref": fetch_ref,
                    "branch_fetches": branch_fetches,
                    "repository": canonical["repository"],
                    "target_branch": canonical["target_branch"],
                    "base_target_sha": canonical["target_sha"],
                    "target_sha": canonical["target_sha"],
                    "plan_fingerprint": canonical["plan_fingerprint"],
                    "snapshot_digest": None,
                    "candidate_artifact": None,
                    "supersedes_observation_id": supersedes_observation_id,
                    "actor": actor,
                    "began_at": format_time(now),
                    "expires_at": format_time(
                        now + timedelta(minutes=SNAPSHOT_OBSERVATION_TTL_MINUTES)
                    ),
                    "installed_at": None,
                }
            )
            # Publish the new token first. If the process dies before invalidating the
            # generation below, every consumer sees this PENDING record and fails
            # closed. Publishing in the opposite order could leave the older token
            # installable after a crash between the two atomic replaces.
            self._atomic_write_authority_json(self.snapshot_observation_path, record)
            self._invalidate_dispatcher_admission_unlocked(
                actor=actor,
                reason="a newer GitHub snapshot observation began",
                github_snapshot_digest=(
                    str(snapshot_digest) if isinstance(snapshot_digest, str) else None
                ),
                reconciliation_digest=(
                    str(generation["reconciliation_digest"])
                    if isinstance(generation, Mapping)
                    and isinstance(generation.get("reconciliation_digest"), str)
                    else None
                ),
            )
            return record

    def _dispatcher_generation_issues(
        self,
        value: object,
        *,
        require_observation_binding: bool = True,
    ) -> tuple[str, ...]:
        if not isinstance(value, Mapping):
            return ("shared dispatcher generation is missing or malformed",)
        material = dict(value)
        generation_id = material.pop("generation_id", None)
        issues: list[str] = []
        common_fields = {
            "schema_version",
            "kind",
            "status",
            "execution_namespace",
            "execution_id",
            "admission_epoch",
            "release_id",
            "repository",
            "target_branch",
            "target_sha",
            "target_generation",
            "target_watermark_record_id",
            "plan_fingerprint",
            "github_snapshot_digest",
            "reconciliation_digest",
            "snapshot_observation_id",
            "snapshot_observation_epoch",
            "snapshot_observation_record_id",
            "host_id",
            "capacity_generation",
            "capacity_epoch",
            "capacity_record_id",
            "session_cap",
            "generation_id",
        }
        active_fields = common_fields | {"recorded_at"}
        invalidated_fields = common_fields | {
            "actor",
            "reason",
            "observed_target_sha",
            "recorded_at",
        }
        expected_fields = (
            active_fields if value.get("status") == "ACTIVE" else invalidated_fields
        )
        if set(value) != expected_fields:
            issues.append("shared dispatcher generation fields are invalid")
        if value.get("schema_version") != 1 or value.get("kind") != DISPATCH_GENERATION_KIND:
            issues.append("shared dispatcher generation schema/kind is invalid")
        if generation_id != digest_json(material):
            issues.append("shared dispatcher generation digest is invalid")
        if type(value.get("admission_epoch")) is not int or int(value["admission_epoch"]) < 1:
            issues.append("shared dispatcher admission epoch is invalid")
        if value.get("status") not in {"ACTIVE", "INVALIDATED"}:
            issues.append("shared dispatcher generation status is invalid")
        if not isinstance(value.get("execution_namespace"), str) or not value.get(
            "execution_namespace"
        ):
            issues.append("shared dispatcher generation execution namespace is invalid")
        if not isinstance(value.get("execution_id"), str) or AUTHORITY_ID.fullmatch(
            str(value.get("execution_id"))
        ) is None:
            issues.append("shared dispatcher generation execution id is invalid")
        elif (
            value.get("execution_namespace") != self.execution_namespace
            or value.get("execution_id") != self.execution_id
        ):
            issues.append("shared dispatcher generation execution identity mismatch")
        release_id = value.get("release_id")
        if release_id is not None and (
            not isinstance(release_id, str) or AUTHORITY_ID.fullmatch(release_id) is None
        ):
            issues.append("shared dispatcher generation release id is invalid")
        if not isinstance(value.get("repository"), str) or not value.get("repository"):
            issues.append("shared dispatcher generation repository is invalid")
        if not isinstance(value.get("target_branch"), str) or not value.get("target_branch"):
            issues.append("shared dispatcher generation target branch is invalid")
        if not isinstance(value.get("target_sha"), str) or FULL_SHA.fullmatch(str(value.get("target_sha"))) is None:
            issues.append("shared dispatcher generation target SHA is invalid")
        if type(value.get("target_generation")) is not int or int(
            value.get("target_generation", 0)
        ) < 1:
            issues.append("shared dispatcher generation target generation is invalid")
        if AUTHORITY_ID.fullmatch(
            str(value.get("target_watermark_record_id"))
        ) is None:
            issues.append(
                "shared dispatcher generation target watermark record is invalid"
            )
        plan_fingerprint = value.get("plan_fingerprint")
        if not isinstance(plan_fingerprint, str) or AUTHORITY_ID.fullmatch(plan_fingerprint) is None:
            issues.append("shared dispatcher generation plan fingerprint is invalid")
        snapshot_digest = value.get("github_snapshot_digest")
        reconciliation_digest = value.get("reconciliation_digest")
        if snapshot_digest is not None and (
            not isinstance(snapshot_digest, str)
            or AUTHORITY_ID.fullmatch(snapshot_digest) is None
        ):
            issues.append("shared dispatcher generation snapshot digest is invalid")
        if reconciliation_digest is not None and (
            not isinstance(reconciliation_digest, str)
            or AUTHORITY_ID.fullmatch(reconciliation_digest) is None
        ):
            issues.append("shared dispatcher generation reconciliation digest is invalid")
        if value.get("status") == "ACTIVE" and (
            snapshot_digest is None or reconciliation_digest is None
        ):
            issues.append("active shared dispatcher generation lacks sealed evidence digests")
        capacity_values = (
            value.get("host_id"),
            value.get("capacity_generation"),
            value.get("capacity_epoch"),
            value.get("capacity_record_id"),
            value.get("session_cap"),
        )
        if value.get("status") == "ACTIVE" or any(
            item is not None for item in capacity_values
        ):
            (
                host_id,
                capacity_generation,
                capacity_epoch,
                capacity_record_id,
                session_cap,
            ) = (
                capacity_values
            )
            if not isinstance(host_id, str) or not host_id.strip():
                issues.append("shared dispatcher generation host id is invalid")
            for field, item in (
                ("capacity generation", capacity_generation),
                ("capacity record", capacity_record_id),
            ):
                if not isinstance(item, str) or AUTHORITY_ID.fullmatch(item) is None:
                    issues.append(f"shared dispatcher generation {field} is invalid")
            if type(session_cap) is not int or session_cap < 1:
                issues.append("shared dispatcher generation session cap is invalid")
            if type(capacity_epoch) is not int or capacity_epoch < 1:
                issues.append("shared dispatcher generation capacity epoch is invalid")
        observation_id = value.get("snapshot_observation_id")
        observation_epoch = value.get("snapshot_observation_epoch")
        observation_record_id = value.get("snapshot_observation_record_id")
        if require_observation_binding or any(
            item is not None
            for item in (observation_id, observation_epoch, observation_record_id)
        ):
            if (
                not isinstance(observation_id, str)
                or AUTHORITY_ID.fullmatch(observation_id) is None
            ):
                issues.append("shared dispatcher generation observation id is invalid")
            if type(observation_epoch) is not int or observation_epoch < 1:
                issues.append("shared dispatcher generation observation epoch is invalid")
            if (
                not isinstance(observation_record_id, str)
                or AUTHORITY_ID.fullmatch(observation_record_id) is None
            ):
                issues.append(
                    "shared dispatcher generation observation record digest is invalid"
                )
        return tuple(dict.fromkeys(issues))

    def _invalidate_dispatcher_admission_unlocked(
        self,
        *,
        actor: str,
        reason: str,
        github_snapshot_digest: str | None,
        reconciliation_digest: str | None,
    ) -> None:
        """Publish the newest execution-scoped scheduling-evidence watermark.

        Observation, reconciliation, generation, and release authority live in the
        immutable execution namespace. Only machine capacity and conflicting target
        refs are repository-arbitrated, so unrelated applications do not rotate one
        another's monotonic admission epoch.
        """

        self._assert_execution_not_terminal_unlocked(
            "dispatcher evidence invalidation"
        )

        if github_snapshot_digest is not None and (
            AUTHORITY_ID.fullmatch(github_snapshot_digest) is None
        ):
            raise AutopilotError("shared dispatcher snapshot digest is invalid")
        if reconciliation_digest is not None and (
            AUTHORITY_ID.fullmatch(reconciliation_digest) is None
        ):
            raise AutopilotError("shared dispatcher reconciliation digest is invalid")
        canonical = self._canonical_dispatch_identity()
        target_watermark = self.repository_target_watermark()
        if target_watermark.get("target_sha") != canonical["target_sha"]:
            raise AutopilotError(
                "repository target watermark differs from canonical dispatcher target"
            )
        generation = self._dispatcher_generation()
        self._assert_no_global_host_reservations(
            "dispatcher evidence invalidation"
        )
        self._assert_no_execution_launch_reservations(
            "dispatcher evidence invalidation"
        )
        self._assert_no_publication_transaction("dispatcher evidence invalidation")
        active = self.active_claims()
        if active:
            raise AutopilotError(
                "shared dispatcher evidence cannot advance while claims are active: "
                + ", ".join(sorted(str(node_id) for node_id in active))
            )
        if generation is None:
            admission_epoch = 1
            release_id = None
        else:
            issues = self._dispatcher_generation_issues(
                generation,
                require_observation_binding=False,
            )
            if issues:
                raise AutopilotError("; ".join(issues))
            if any(
                generation.get(field) != canonical[field]
                for field in ("repository", "target_branch")
            ):
                raise AutopilotError(
                    "shared dispatcher repository/target branch differs from canonical authority"
                )
            admission_epoch = int(generation["admission_epoch"]) + 1
            release_id = generation.get("release_id")
        observation = self._snapshot_observation()
        observation_issues = self._snapshot_observation_issues(observation)
        if observation_issues:
            observation_id = None
            observation_epoch = None
            observation_record_id = None
        else:
            assert isinstance(observation, Mapping)
            observation_id = observation["observation_id"]
            observation_epoch = observation["observation_epoch"]
            observation_record_id = observation["record_id"]
        marker: dict[str, Any] = {
            "schema_version": 1,
            "kind": DISPATCH_GENERATION_KIND,
            "status": "INVALIDATED",
            "execution_namespace": self.execution_namespace,
            "execution_id": self.execution_id,
            "admission_epoch": admission_epoch,
            "release_id": release_id,
            "repository": canonical["repository"],
            "target_branch": canonical["target_branch"],
            "target_sha": canonical["target_sha"],
            "target_generation": target_watermark["target_generation"],
            "target_watermark_record_id": target_watermark["record_id"],
            "plan_fingerprint": canonical["plan_fingerprint"],
            "github_snapshot_digest": github_snapshot_digest,
            "reconciliation_digest": reconciliation_digest,
            "snapshot_observation_id": observation_id,
            "snapshot_observation_epoch": observation_epoch,
            "snapshot_observation_record_id": observation_record_id,
            "host_id": generation.get("host_id") if generation else None,
            "capacity_generation": (
                generation.get("capacity_generation") if generation else None
            ),
            "capacity_epoch": generation.get("capacity_epoch") if generation else None,
            "capacity_record_id": (
                generation.get("capacity_record_id") if generation else None
            ),
            "session_cap": generation.get("session_cap") if generation else None,
            "actor": actor,
            "reason": reason,
            "observed_target_sha": canonical["target_sha"],
            "recorded_at": format_time(self.clock()),
        }
        marker["generation_id"] = digest_json(marker)
        self._atomic_write_authority_json(self.dispatcher_generation_path, marker)

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

    def _remote_ref_sha(self, ref: str, *, remote: str = "origin") -> str | None:
        # The keyword is part of the base signature (controller.ControlPlane).
        # Dropping it here made every base-class call that passes remote= raise
        # TypeError, which silently disabled branch quarantine during healing.
        if remote != "origin":
            raise ClaimError("only the configured canonical remote name 'origin' is allowed")
        completed = self._git(("ls-remote", remote, ref), check=False)
        if completed.returncode != 0:
            raise ClaimError("cannot inspect configured origin: " + completed.stderr.strip())
        fields = completed.stdout.strip().split()
        if not fields:
            return None
        if len(fields) != 2 or fields[1] != ref or FULL_SHA.fullmatch(fields[0]) is None:
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

    def _target_tracking_sha(self) -> str:
        reference = f"refs/remotes/origin/{self.target_branch}"
        completed = self._git(
            ("rev-parse", "--verify", f"{reference}^{{commit}}"),
            check=False,
        )
        value = completed.stdout.strip()
        if completed.returncode != 0 or FULL_SHA.fullmatch(value) is None:
            raise AutopilotError(
                "snapshot authority requires the canonical origin target tracking ref"
            )
        return value

    @staticmethod
    def _snapshot_source_refs_from_stdout(
        raw_stdout: str, *, label: str
    ) -> Mapping[str, str]:
        if (
            not isinstance(raw_stdout, str)
            or len(raw_stdout.encode("utf-8")) > SNAPSHOT_SOURCE_REF_MAX_BYTES
            or "\x00" in raw_stdout
        ):
            raise AutopilotError(f"{label} exceeds its bounded text authority")
        entries: list[tuple[str, str]] = []
        for line in raw_stdout.splitlines():
            if not line:
                continue
            fields = line.split("\t")
            if (
                len(fields) != 2
                or FULL_SHA.fullmatch(fields[0]) is None
                or not fields[1].startswith("refs/heads/")
                or fields[1] == "refs/heads/"
                or any(character in fields[1] for character in " \r\n\0")
            ):
                raise AutopilotError(f"{label} contains a malformed remote ref")
            entries.append((fields[1], fields[0]))
        if (
            entries != sorted(entries, key=lambda item: item[0])
            or len(entries) != len({reference for reference, _sha in entries})
        ):
            raise AutopilotError(f"{label} is duplicated or noncanonical")
        return {reference: sha for reference, sha in entries}

    def _validated_snapshot_source_ref_observation(
        self,
        value: object,
        observation: Mapping[str, Any],
        *,
        label: str,
    ) -> dict[str, object]:
        if (
            not isinstance(value, Mapping)
            or set(value) != SNAPSHOT_SOURCE_REF_OBSERVATION_FIELDS
        ):
            raise AutopilotError(f"{label} has an invalid exact schema")
        source = dict(value)
        material = dict(source)
        record_id = material.pop("record_id", None)
        raw_stdout = source.get("raw_stdout")
        if not isinstance(raw_stdout, str):
            raise AutopilotError(f"{label} raw remote bytes are unavailable")
        refs = self._snapshot_source_refs_from_stdout(raw_stdout, label=label)
        branch_refs = source.get("branch_refs")
        expected_fetches = observation.get("branch_fetches")
        if not isinstance(branch_refs, list) or not isinstance(expected_fetches, list):
            raise AutopilotError(f"{label} branch inventory is malformed")
        expected_branches: list[dict[str, object]] = []
        for fetch in expected_fetches:
            if not isinstance(fetch, Mapping):
                raise AutopilotError(f"{label} branch inventory is malformed")
            branch = str(fetch.get("branch"))
            reference = f"refs/heads/{branch}"
            sha = refs.get(reference)
            expected_branches.append(
                {
                    "node_id": fetch.get("node_id"),
                    "branch": branch,
                    "ref": reference,
                    "present": sha is not None,
                    "sha": sha,
                }
            )
        target_ref = f"refs/heads/{observation.get('target_branch')}"
        argv = source.get("ls_remote_argv")
        if (
            record_id != digest_json(material)
            or AUTHORITY_ID.fullmatch(str(record_id)) is None
            or source.get("schema_version") != 1
            or source.get("kind") != SNAPSHOT_SOURCE_REF_OBSERVATION_KIND
            or source.get("execution_namespace") != self.execution_namespace
            or source.get("execution_id") != self.execution_id
            or source.get("observation_id") != observation.get("observation_id")
            or source.get("repository") != observation.get("repository")
            or source.get("repository_transport_digest")
            != self.repository_identity.get("transport_digest")
            or source.get("target_ref") != target_ref
            or source.get("target_sha") != refs.get(target_ref)
            or FULL_SHA.fullmatch(str(source.get("target_sha"))) is None
            or source.get("branch_refs") != expected_branches
            or not isinstance(argv, list)
            or len(argv) < 4
            or argv[0] != "git"
            or argv[-3:] != ["ls-remote", "--heads", "origin"]
            or source.get("raw_stdout_digest")
            != "sha256:" + sha256(raw_stdout.encode("utf-8")).hexdigest()
        ):
            raise AutopilotError(f"{label} authority binding is invalid")
        try:
            parse_time(source.get("observed_at"))
        except Exception as error:
            raise AutopilotError(f"{label} time is malformed") from error
        return source

    def _snapshot_source_ref_observation_from_raw(
        self,
        observation: Mapping[str, Any],
        *,
        raw_stdout: str,
        ls_remote_argv: Sequence[str],
    ) -> Mapping[str, object]:
        refs = self._snapshot_source_refs_from_stdout(
            raw_stdout, label="GitHub snapshot source-ref observation"
        )
        branch_refs: list[dict[str, object]] = []
        raw_fetches = observation.get("branch_fetches")
        if not isinstance(raw_fetches, list):
            raise AutopilotError(
                "GitHub snapshot source-ref observation lacks branch authority"
            )
        for fetch in raw_fetches:
            if not isinstance(fetch, Mapping):
                raise AutopilotError(
                    "GitHub snapshot source-ref observation branch is malformed"
                )
            branch = str(fetch.get("branch"))
            reference = f"refs/heads/{branch}"
            sha = refs.get(reference)
            branch_refs.append(
                {
                    "node_id": fetch.get("node_id"),
                    "branch": branch,
                    "ref": reference,
                    "present": sha is not None,
                    "sha": sha,
                }
            )
        target_ref = f"refs/heads/{observation.get('target_branch')}"
        material: dict[str, object] = {
            "schema_version": 1,
            "kind": SNAPSHOT_SOURCE_REF_OBSERVATION_KIND,
            "execution_namespace": self.execution_namespace,
            "execution_id": self.execution_id,
            "observation_id": observation["observation_id"],
            "repository": observation["repository"],
            "repository_transport_digest": self.repository_identity[
                "transport_digest"
            ],
            "target_ref": target_ref,
            "target_sha": refs.get(target_ref),
            "branch_refs": branch_refs,
            "ls_remote_argv": list(ls_remote_argv),
            "raw_stdout": raw_stdout,
            "raw_stdout_digest": "sha256:"
            + sha256(raw_stdout.encode("utf-8")).hexdigest(),
            "observed_at": format_time(self.clock()),
        }
        source = {**material, "record_id": digest_json(material)}
        return self._validated_snapshot_source_ref_observation(
            source,
            observation,
            label="new GitHub snapshot source-ref observation",
        )

    def _collect_snapshot_source_ref_observation(
        self, observation: Mapping[str, Any]
    ) -> Mapping[str, object]:
        self.assert_canonical_remote_transport_identity()
        completed = self._git(
            ("ls-remote", "--heads", "origin"), check=False
        )
        if completed.returncode != 0:
            raise AutopilotError(
                "GitHub snapshot source refs are unavailable for CAS revalidation"
            )
        argv = [
            "git",
            "--no-replace-objects",
            "-c",
            f"core.hooksPath={self.arbiter_dir / 'git-hooks-disabled.authority'}",
            "ls-remote",
            "--heads",
            "origin",
        ]
        return self._snapshot_source_ref_observation_from_raw(
            observation,
            raw_stdout=completed.stdout,
            ls_remote_argv=argv,
        )

    @staticmethod
    def _snapshot_source_ref_state(
        source: Mapping[str, object],
    ) -> Mapping[str, object]:
        return {
            "target_ref": source.get("target_ref"),
            "target_sha": source.get("target_sha"),
            "branch_refs": source.get("branch_refs"),
        }

    def _snapshot_source_revalidation_path(self, observation_id: str) -> Path:
        if AUTHORITY_ID.fullmatch(observation_id) is None:
            raise AutopilotError("snapshot source revalidation id is invalid")
        return self._secure_execution_path(
            Path("sr") / f"{observation_id.removeprefix('sha256:')}.json"
        )

    def _supersede_snapshot_observation_after_source_change(
        self,
        *,
        observation_id: str,
        observation_record_id: str,
    ) -> None:
        """Terminalize a stale read so a new begin can allocate a fresh token."""

        with self._host_arbiter_execution_guard():
            current = self._snapshot_observation()
            self._supersede_snapshot_observation_after_source_change_unlocked(
                current,
                observation_id=observation_id,
                observation_record_id=observation_record_id,
            )

    def _supersede_snapshot_observation_after_source_change_unlocked(
        self,
        current: object,
        *,
        observation_id: str,
        observation_record_id: str,
    ) -> None:
        """Fence one exact INSTALLING observation while authority locks are held."""

        issues = self._snapshot_observation_issues(current)
        if issues:
            raise AutopilotError("; ".join(issues))
        assert isinstance(current, Mapping)
        if current.get("observation_id") != observation_id:
            return
        if current.get("status") == "SUPERSEDED":
            return
        if (
            current.get("record_id") != observation_record_id
            or current.get("status") != "INSTALLING"
        ):
            raise AutopilotError(
                "snapshot observation changed while source drift was fenced"
            )
        superseded = dict(current)
        superseded["status"] = "SUPERSEDED"
        # The v2 record has one terminal timestamp slot.  For SUPERSEDED it
        # records the terminalization cut, never an installation claim.
        superseded["installed_at"] = format_time(self.clock())
        superseded = self._seal_snapshot_observation(superseded)
        self._atomic_write_authority_json(
            self.snapshot_observation_path, superseded
        )
        generation = self._dispatcher_generation()
        self._invalidate_dispatcher_admission_unlocked(
            actor="autopilot:snapshot-source-revalidation",
            reason=(
                "canonical remote source refs changed during snapshot observation"
            ),
            github_snapshot_digest=(
                str(current["snapshot_digest"])
                if isinstance(current.get("snapshot_digest"), str)
                else None
            ),
            reconciliation_digest=(
                str(generation["reconciliation_digest"])
                if isinstance(generation, Mapping)
                and isinstance(generation.get("reconciliation_digest"), str)
                else None
            ),
        )

    def _snapshot_candidate_issues(
        self,
        candidate: object,
        observation: Mapping[str, Any],
    ) -> tuple[str, ...]:
        if not isinstance(candidate, Mapping):
            return ("GitHub snapshot must be an object",)
        issues: list[str] = []
        required = {
            "schema_version",
            "kind",
            "execution_namespace",
            "execution_id",
            "observation_id",
            "observation_epoch",
            "fetch_ref",
            "repository",
            "target_branch",
            "target_sha",
            "branch_observations",
            "branches",
            "raw_pull_requests",
            "pull_requests",
            "github_query",
            "git_query",
            "source_ref_observation",
            "candidate_id",
        }
        if set(candidate) != required:
            issues.append("GitHub snapshot candidate fields are invalid")
        if (
            candidate.get("schema_version") != 1
            or candidate.get("kind") != SNAPSHOT_CANDIDATE_KIND
        ):
            issues.append("GitHub snapshot candidate schema/kind is invalid")
        material = dict(candidate)
        candidate_id = material.pop("candidate_id", None)
        if candidate_id != digest_json(material):
            issues.append("GitHub snapshot candidate seal is invalid")
        comparisons = (
            ("execution_namespace", "execution_namespace"),
            ("execution_id", "execution_id"),
            ("observation_id", "observation_id"),
            ("observation_epoch", "observation_epoch"),
            ("fetch_ref", "fetch_ref"),
            ("repository", "repository"),
            ("target_branch", "target_branch"),
        )
        for candidate_field, observation_field in comparisons:
            if candidate.get(candidate_field) != observation.get(observation_field):
                issues.append(
                    f"GitHub snapshot {candidate_field} does not match its reservation"
                )
        target_sha = candidate.get("target_sha")
        if not isinstance(target_sha, str) or FULL_SHA.fullmatch(target_sha) is None:
            issues.append("GitHub snapshot target_sha is invalid")
        try:
            source_ref_observation = (
                self._validated_snapshot_source_ref_observation(
                    candidate.get("source_ref_observation"),
                    observation,
                    label="GitHub snapshot source-ref observation",
                )
            )
        except AutopilotError as error:
            issues.append(str(error))
            source_ref_observation = {}
        if source_ref_observation.get("target_sha") != target_sha:
            issues.append(
                "GitHub snapshot target differs from fresh canonical source refs"
            )
        expected_fetches = observation.get("branch_fetches")
        branch_observations = candidate.get("branch_observations")
        if not isinstance(expected_fetches, list) or not isinstance(
            branch_observations, list
        ):
            issues.append("GitHub snapshot branch observations are invalid")
            expected_fetches = []
            branch_observations = []
        if len(branch_observations) != len(expected_fetches):
            issues.append("GitHub snapshot does not cover every canonical node branch")
        expected_branches: list[dict[str, object]] = []
        expected_refspecs: list[str] = []
        for index, expected in enumerate(expected_fetches):
            observed = (
                branch_observations[index]
                if index < len(branch_observations)
                else None
            )
            if (
                not isinstance(expected, Mapping)
                or not isinstance(observed, Mapping)
                or set(observed) != {
                    "node_id",
                    "branch",
                    "fetch_ref",
                    "present",
                    "sha",
                }
            ):
                issues.append("GitHub snapshot branch observation entry is invalid")
                continue
            for field in ("node_id", "branch", "fetch_ref"):
                if observed.get(field) != expected.get(field):
                    issues.append(
                        "GitHub snapshot branch observation authority mismatch"
                    )
            present = observed.get("present")
            sha = observed.get("sha")
            if type(present) is not bool:
                issues.append("GitHub snapshot branch presence is invalid")
            elif present:
                if not isinstance(sha, str) or FULL_SHA.fullmatch(sha) is None:
                    issues.append("GitHub snapshot branch SHA is invalid")
                else:
                    expected_branches.append(
                        {
                            "name": expected.get("branch"),
                            "sha": sha,
                            "node_id": expected.get("node_id"),
                        }
                    )
                    expected_refspecs.append(
                        f"+refs/heads/{expected.get('branch')}:{expected.get('fetch_ref')}"
                    )
            elif sha is not None:
                issues.append("absent GitHub snapshot branch carries a SHA")
        if candidate.get("branches") != expected_branches:
            issues.append("GitHub snapshot branches do not match private branch refs")
        expected_source_branches = [
            {
                "node_id": item.get("node_id"),
                "branch": item.get("branch"),
                "ref": f"refs/heads/{item.get('branch')}",
                "present": item.get("present"),
                "sha": item.get("sha"),
            }
            for item in branch_observations
            if isinstance(item, Mapping)
        ]
        if source_ref_observation.get("branch_refs") != expected_source_branches:
            issues.append(
                "GitHub snapshot branch evidence differs from fresh canonical source refs"
            )

        git_query = candidate.get("git_query")
        expected_git_query = {
            "target_refspec": (
                f"+refs/heads/{observation.get('target_branch')}:"
                f"{observation.get('fetch_ref')}"
            ),
            "branch_refspecs": expected_refspecs,
            "ls_remote_argv": [
                "git",
                "--no-replace-objects",
                "-c",
                f"core.hooksPath={os.devnull}",
                "ls-remote",
                "--heads",
                "origin",
            ],
        }
        if git_query != expected_git_query:
            issues.append("GitHub snapshot Git invocation provenance is invalid")
        elif source_ref_observation.get("ls_remote_argv") != expected_git_query[
            "ls_remote_argv"
        ]:
            issues.append(
                "GitHub snapshot source-ref invocation differs from Git provenance"
            )

        raw_pull_requests = candidate.get("raw_pull_requests")
        pull_requests = candidate.get("pull_requests")
        github_query = candidate.get("github_query")
        if not isinstance(raw_pull_requests, list) or not isinstance(
            pull_requests, list
        ):
            issues.append("GitHub snapshot pull-request evidence is invalid")
            raw_pull_requests = []
            pull_requests = []
        if not isinstance(github_query, Mapping) or set(github_query) != {
            "offline",
            "evidence_available",
            "complete",
            "node_queries",
            "exit_code",
        }:
            issues.append("GitHub snapshot query provenance is invalid")
            github_query = {}
        offline = github_query.get("offline")
        evidence_available = github_query.get("evidence_available")
        complete = github_query.get("complete")
        node_queries = github_query.get("node_queries")
        if (
            type(offline) is not bool
            or type(evidence_available) is not bool
            or type(complete) is not bool
            or not isinstance(node_queries, list)
            or github_query.get("exit_code") != 0
        ):
            issues.append("GitHub snapshot query result is invalid")
        elif offline:
            if (
                evidence_available is not False
                or complete is not False
                or node_queries
                or raw_pull_requests
                or pull_requests
            ):
                issues.append("offline GitHub snapshot misrepresents unavailable evidence")
        elif evidence_available is not True or complete is not True:
            issues.append("GitHub snapshot pull-request evidence is incomplete")
        else:
            expected_queries: list[dict[str, object]] = []
            raw_by_branch: dict[str, list[object]] = {}
            for raw in raw_pull_requests:
                if isinstance(raw, Mapping) and isinstance(
                    raw.get("headRefName"), str
                ):
                    raw_by_branch.setdefault(str(raw["headRefName"]), []).append(raw)
            for fetch in expected_fetches:
                if not isinstance(fetch, Mapping):
                    continue
                node_id = str(fetch.get("node_id"))
                branch = str(fetch.get("branch"))
                result = raw_by_branch.get(branch, [])
                expected_queries.append(
                    {
                        "node_id": node_id,
                        "branch": branch,
                        "argv": [
                            "gh",
                            "pr",
                            "list",
                            "--repo",
                            observation.get("repository"),
                            "--head",
                            branch,
                            "--state",
                            "all",
                            "--limit",
                            str(GITHUB_NODE_PR_LIMIT),
                            "--json",
                            "number,state,headRefName,statusCheckRollup",
                        ],
                        "exit_code": 0,
                        "result_count": len(result),
                        "result_digest": digest_json(result),
                    }
                )
                if len(result) >= GITHUB_NODE_PR_LIMIT:
                    issues.append(
                        f"GitHub snapshot pull-request evidence for {node_id} is truncated"
                    )
            if node_queries != expected_queries:
                issues.append("GitHub snapshot per-node query provenance is noncanonical")

        branch_to_node = {
            str(item.get("branch")): str(item.get("node_id"))
            for item in expected_fetches
            if isinstance(item, Mapping)
        }
        normalized_prs: list[dict[str, object]] = []
        seen_pr_numbers: set[int] = set()
        for item in raw_pull_requests:
            if not isinstance(item, Mapping) or set(item) != {
                "number",
                "state",
                "headRefName",
                "statusCheckRollup",
            }:
                issues.append("GitHub snapshot raw pull-request schema is invalid")
                continue
            number = item.get("number")
            state = item.get("state")
            head = item.get("headRefName")
            rollup = item.get("statusCheckRollup")
            if (
                type(number) is not int
                or number < 1
                or not isinstance(state, str)
                or state.upper() not in {"OPEN", "CLOSED", "MERGED"}
                or not isinstance(head, str)
                or (rollup is not None and not isinstance(rollup, list))
                or (
                    isinstance(rollup, list)
                    and any(not isinstance(check, Mapping) for check in rollup)
                )
            ):
                issues.append("GitHub snapshot raw pull-request value is invalid")
                continue
            if number in seen_pr_numbers:
                issues.append("GitHub snapshot pull-request evidence is duplicated")
                continue
            seen_pr_numbers.add(number)
            node_id = branch_to_node.get(head)
            if node_id is None:
                continue
            conclusions = {
                str(check.get("conclusion") or "").upper()
                for check in (rollup or [])
                if isinstance(check, Mapping)
            }
            failure = {"FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED"}
            success = {"SUCCESS", "SKIPPED", "NEUTRAL"}
            ci = (
                "failure"
                if conclusions & failure
                else "success"
                if conclusions and conclusions <= success
                else "pending"
            )
            normalized_prs.append(
                {
                    "node_id": node_id,
                    "number": number,
                    "state": "open" if state.upper() == "OPEN" else "closed",
                    "merged": state.upper() == "MERGED",
                    "ci": ci,
                }
            )
        if pull_requests != normalized_prs:
            issues.append(
                "GitHub snapshot normalized pull requests differ from raw evidence"
            )
        return tuple(dict.fromkeys(issues))

    def _snapshot_generation_matches(
        self,
        generation: object,
        observation: Mapping[str, Any],
        snapshot_digest: str,
    ) -> bool:
        return bool(
            isinstance(generation, Mapping)
            and not self._dispatcher_generation_issues(generation)
            and generation.get("github_snapshot_digest") == snapshot_digest
            and generation.get("snapshot_observation_id")
            == observation.get("observation_id")
            and generation.get("snapshot_observation_epoch")
            == observation.get("observation_epoch")
            and generation.get("snapshot_observation_record_id")
            == observation.get("record_id")
        )

    def _snapshot_digest(self) -> str | None:
        path = self.github_snapshot_path
        if not path.is_file():
            return None
        try:
            snapshot = self._strict_json_file(
                path, label="installed GitHub snapshot evidence"
            )
        except AutopilotError:
            return None
        if not isinstance(snapshot, Mapping) or snapshot.get(
            "target_sha"
        ) != self.current_target_sha():
            return None
        return digest_json(snapshot)

    def install_github_snapshot(
        self, source: Path | None, *, observation_id: str
    ) -> Path:
        """Install exactly the latest reserved remote observation.

        The source is read once, its private fetch ref is authenticated, and only then
        is ``origin/<target>`` advanced with an old-value compare-and-swap. A stale
        fetch can add objects and its private ref, but it cannot perturb canonical
        scheduling refs or shared execution authority.
        """

        # Caller-controlled bytes are consumed exactly once before any authority
        # transition. Subsequent crash recovery uses only the sealed artifact.
        candidate_from_source: object | None = None
        if source is not None:
            if not source.is_file():
                raise AutopilotError("GitHub snapshot candidate source is unavailable")
            candidate_from_source = self._strict_json_file(
                source, label="GitHub snapshot candidate"
            )

        # Phase one is execution-local. Persist the immutable candidate and the
        # INSTALLING transition, then release this lock before entering the global
        # arbiter so lock order is never inverted.
        with self.execution_lock("dispatcher-admission.lock", timeout_seconds=120.0):
            self._assert_execution_not_terminal_unlocked(
                "GitHub snapshot installation"
            )
            self._assert_no_execution_launch_reservations(
                "GitHub snapshot installation"
            )
            self._assert_no_publication_transaction(
                "GitHub snapshot installation"
            )
            active = self.active_claims()
            if active:
                raise AutopilotError(
                    "GitHub snapshot installation is deferred while claims are active"
                )
            observation = self._snapshot_observation()
            observation_issues = self._snapshot_observation_issues(observation)
            if observation_issues:
                raise AutopilotError("; ".join(observation_issues))
            assert isinstance(observation, Mapping)
            if (
                observation.get("execution_namespace") != self.execution_namespace
                or observation.get("execution_id") != self.execution_id
                or observation.get("observation_id") != observation_id
            ):
                raise AutopilotError(
                    "GitHub snapshot observation was superseded or changed namespace"
                )
            if observation.get("branch_fetches") != self._snapshot_branch_fetches(
                int(observation["observation_epoch"]), observation_id
            ):
                raise AutopilotError(
                    "GitHub snapshot observation branch inventory is noncanonical"
                )
            status_before = str(observation["status"])
            if status_before == "SUPERSEDED":
                raise AutopilotError(
                    "GitHub snapshot observation was superseded by source-ref drift"
                )
            if (
                status_before != "INSTALLED"
                and parse_time(observation.get("expires_at")) <= self.clock()
            ):
                raise AutopilotError(
                    "GitHub snapshot observation expired before installation"
                )

            sealed_candidate: object | None = None
            pending_candidate: object | None = None
            artifact_value = observation.get("candidate_artifact")
            if status_before in {"INSTALLING", "INSTALLED"}:
                if not isinstance(artifact_value, str):
                    raise AutopilotError(
                        "snapshot observation lacks immutable candidate recovery evidence"
                    )
                artifact_path = self._secure_execution_path(artifact_value)
                if artifact_path.is_file():
                    sealed_candidate = self._strict_json_file(
                        artifact_path,
                        label="immutable GitHub snapshot candidate",
                    )
                elif candidate_from_source is None:
                    raise AutopilotError(
                        "immutable GitHub snapshot candidate is unavailable for recovery"
                    )
            elif status_before == "PENDING":
                pending_candidate = self._pending_snapshot_candidate(observation)

            durable_candidate = sealed_candidate or pending_candidate
            if durable_candidate is not None and candidate_from_source is not None:
                if self._canonical_json_bytes(
                    durable_candidate
                ) != self._canonical_json_bytes(candidate_from_source):
                    raise AutopilotError(
                        "GitHub snapshot retry differs from immutable candidate evidence"
                    )
            candidate = durable_candidate or candidate_from_source
            if candidate is None:
                raise AutopilotError("GitHub snapshot candidate source is required")
            candidate_issues = self._snapshot_candidate_issues(candidate, observation)
            if candidate_issues:
                raise AutopilotError("; ".join(candidate_issues))
            assert isinstance(candidate, Mapping)
            candidate_target = str(candidate["target_sha"])
            snapshot_digest = digest_json(candidate)
            expected_artifact = self._snapshot_candidate_artifact(
                observation_id, snapshot_digest
            )
            if observation.get("candidate_artifact") == (
                self._legacy_snapshot_candidate_artifact(
                    observation_id, snapshot_digest
                )
            ):
                expected_artifact = str(observation["candidate_artifact"])
            if status_before in {"INSTALLING", "INSTALLED"} and (
                observation.get("snapshot_digest") != snapshot_digest
                or observation.get("candidate_artifact") != expected_artifact
                or observation.get("target_sha") != candidate_target
            ):
                raise AutopilotError(
                    "immutable GitHub snapshot candidate does not match observation authority"
                )
            artifact_path = self._secure_execution_path(expected_artifact)
            self._write_immutable_json(artifact_path, candidate)
            if status_before == "PENDING":
                installing = dict(observation)
                installing["status"] = "INSTALLING"
                installing["target_sha"] = candidate_target
                installing["snapshot_digest"] = snapshot_digest
                installing["candidate_artifact"] = expected_artifact
                observation = self._seal_snapshot_observation(installing)
                self._atomic_write_authority_json(
                    self.snapshot_observation_path, observation
                )
            observation_record_id = str(observation["record_id"])

        # Remote evidence refs are immutable clone-independent capabilities.
        # Their network verification/materialization happens without host,
        # repository, or execution locks; phase two revalidates the exact shared
        # observation after reacquiring the canonical lock order.
        source_revalidation_record_id: str | None = None
        source_revalidation_path = self._snapshot_source_revalidation_path(
            observation_id
        )
        if self.verify_git_objects:
            self._materialize_remote_evidence_ref(
                str(observation["fetch_ref"]),
                candidate_target,
                label="snapshot target evidence",
            )
            assert isinstance(candidate, Mapping)
            for branch_observation in candidate["branch_observations"]:
                assert isinstance(branch_observation, Mapping)
                branch_ref = str(branch_observation["fetch_ref"])
                if branch_observation["present"] is True:
                    self._materialize_remote_evidence_ref(
                        branch_ref,
                        str(branch_observation["sha"]),
                        label=(
                            "snapshot branch evidence "
                            + str(branch_observation["node_id"])
                        ),
                    )
                else:
                    self.assert_canonical_remote_transport_identity()
                    if self._remote_ref_sha(branch_ref) is not None:
                        raise AutopilotError(
                            "absent snapshot branch has a remote reserved evidence ref"
                        )
                    local = self._git(
                        ("rev-parse", "--verify", f"{branch_ref}^{{commit}}"),
                        check=False,
                    )
                    if local.returncode == 0:
                        raise AutopilotError(
                            "absent snapshot branch has a local reserved evidence ref"
                        )
            source_revalidation = self._validated_snapshot_source_ref_observation(
                self._collect_snapshot_source_ref_observation(observation),
                observation,
                label="fresh snapshot source-ref CAS observation",
            )
            self._atomic_write_authority_json(
                source_revalidation_path, source_revalidation
            )
            source_revalidation_record_id = str(
                source_revalidation["record_id"]
            )
            candidate_source = self._validated_snapshot_source_ref_observation(
                candidate.get("source_ref_observation"),
                observation,
                label="immutable candidate source-ref observation",
            )
            if self._snapshot_source_ref_state(
                source_revalidation
            ) != self._snapshot_source_ref_state(candidate_source):
                self._supersede_snapshot_observation_after_source_change(
                    observation_id=observation_id,
                    observation_record_id=observation_record_id,
                )
                raise AutopilotError(
                    "canonical remote target or source branch changed during "
                    "snapshot observation; a fresh token is required"
                )

        # Phase two holds machine-host and repository-arbiter authority only for
        # exact revalidation and ref CAS. The execution lock is nested in the one
        # global order: host -> arbiter -> execution.
        with self._host_arbiter_guard():
            with self.execution_lock(
                "dispatcher-admission.lock", timeout_seconds=120.0
            ):
                self._assert_execution_not_terminal_unlocked(
                    "GitHub snapshot installation CAS"
                )
                self.assert_canonical_remote_transport_identity()
                self._assert_no_global_host_reservations(
                    "GitHub snapshot installation CAS"
                )
                self._assert_no_execution_launch_reservations(
                    "GitHub snapshot installation CAS"
                )
                if self.active_claims():
                    raise AutopilotError(
                        "GitHub snapshot installation CAS is fenced by active claims"
                    )
                current_observation = self._snapshot_observation()
                current_issues = self._snapshot_observation_issues(current_observation)
                if current_issues:
                    raise AutopilotError("; ".join(current_issues))
                assert isinstance(current_observation, Mapping)
                if (
                    current_observation.get("observation_id") != observation_id
                    or current_observation.get("record_id") != observation_record_id
                    or current_observation.get("snapshot_digest") != snapshot_digest
                    or current_observation.get("candidate_artifact")
                    != expected_artifact
                    or current_observation.get("status") not in {"INSTALLING", "INSTALLED"}
                ):
                    raise AutopilotError(
                        "GitHub snapshot observation changed before target CAS"
                    )
                artifact_candidate = self._strict_json_file(
                    self._secure_execution_path(expected_artifact),
                    label="immutable GitHub snapshot candidate",
                )
                if (
                    digest_json(artifact_candidate) != snapshot_digest
                    or self._snapshot_candidate_issues(
                        artifact_candidate, current_observation
                    )
                ):
                    raise AutopilotError(
                        "immutable GitHub snapshot candidate failed CAS revalidation"
                    )
                if self.verify_git_objects:
                    installed_source_revalidation = (
                        self._validated_snapshot_source_ref_observation(
                            self._strict_json_file(
                                source_revalidation_path,
                                label="snapshot source-ref CAS observation",
                            ),
                            current_observation,
                            label="snapshot source-ref CAS observation",
                        )
                    )
                    candidate_source = (
                        self._validated_snapshot_source_ref_observation(
                            artifact_candidate.get("source_ref_observation")
                            if isinstance(artifact_candidate, Mapping)
                            else None,
                            current_observation,
                            label="immutable candidate source-ref observation",
                        )
                    )
                    if (
                        installed_source_revalidation.get("record_id")
                        != source_revalidation_record_id
                        or self._snapshot_source_ref_state(
                            installed_source_revalidation
                        )
                        != self._snapshot_source_ref_state(candidate_source)
                    ):
                        raise AutopilotError(
                            "snapshot source-ref observation changed before CAS"
                        )
                    # The unlocked collection above proves the candidate before
                    # entering shared authority, but it is not the CAS cut: a
                    # target or source ref can move while this process waits for
                    # the host/repository/execution locks.  Observe the complete
                    # canonical ref set again while those locks fence every Hive
                    # Mind publisher, persist the exact raw receipt, and compare
                    # presence as well as SHA before touching either tracking ref.
                    cas_source_revalidation = (
                        self._validated_snapshot_source_ref_observation(
                            self._collect_snapshot_source_ref_observation(
                                current_observation
                            ),
                            current_observation,
                            label="locked snapshot source-ref CAS observation",
                        )
                    )
                    self._atomic_write_authority_json(
                        source_revalidation_path, cas_source_revalidation
                    )
                    source_revalidation_record_id = str(
                        cas_source_revalidation["record_id"]
                    )
                    if self._snapshot_source_ref_state(
                        cas_source_revalidation
                    ) != self._snapshot_source_ref_state(candidate_source):
                        self._supersede_snapshot_observation_after_source_change_unlocked(
                            current_observation,
                            observation_id=observation_id,
                            observation_record_id=observation_record_id,
                        )
                        raise AutopilotError(
                            "canonical remote target or source branch changed at "
                            "the snapshot CAS cut; a fresh token is required"
                        )
                canonical_before = self._canonical_dispatch_identity()
                if any(
                    current_observation.get(field) != canonical_before[field]
                    for field in ("repository", "target_branch", "plan_fingerprint")
                ):
                    raise AutopilotError(
                        "GitHub snapshot observation is stale relative to canonical authority"
                    )
                candidate_identity = self._dispatch_identity_at(candidate_target)
                if any(
                    current_observation.get(field) != candidate_identity[field]
                    for field in ("repository", "target_branch", "plan_fingerprint")
                ):
                    raise AutopilotError(
                        "GitHub snapshot candidate changed repository, branch, or plan authority"
                    )

                if self.verify_git_objects:
                    fetched = self._git(
                        (
                            "rev-parse",
                            "--verify",
                            f"{current_observation['fetch_ref']}^{{commit}}",
                        ),
                        check=False,
                    )
                    if fetched.returncode != 0 or fetched.stdout.strip() != candidate_target:
                        raise AutopilotError(
                            "GitHub snapshot private fetch ref does not match candidate target"
                        )
                    if not self.is_ancestor(
                        str(current_observation["base_target_sha"]), candidate_target
                    ):
                        raise AutopilotError(
                            "GitHub snapshot candidate is stale or non-descendant"
                        )
                    assert isinstance(artifact_candidate, Mapping)
                    for branch_observation in artifact_candidate["branch_observations"]:
                        assert isinstance(branch_observation, Mapping)
                        resolved = self._git(
                            (
                                "rev-parse",
                                "--verify",
                                f"{branch_observation['fetch_ref']}^{{commit}}",
                            ),
                            check=False,
                        )
                        resolved_sha = resolved.stdout.strip()
                        if branch_observation["present"] is True:
                            if (
                                resolved.returncode != 0
                                or resolved_sha != branch_observation["sha"]
                            ):
                                raise AutopilotError(
                                    "GitHub snapshot branch evidence differs from its private ref"
                                )
                        elif resolved.returncode == 0:
                            raise AutopilotError(
                                "GitHub snapshot claims a branch is absent but its reserved ref exists"
                            )
                    execution_target = self._execution_target_sha()
                    base_target = str(current_observation["base_target_sha"])
                    current_tracking = self._target_tracking_sha()
                    # The execution-private ref is the durable proof that this exact
                    # observation already completed its shared tracking-ref CAS.  A
                    # different execution may then advance origin/<target> again
                    # before this observation finalizes (or while its process is
                    # down).  Retrying must adopt that proof without regressing the
                    # newer compatible target or leaving this observation forever in
                    # INSTALLING.
                    cas_already_applied = execution_target == candidate_target
                    if cas_already_applied and self.is_ancestor(
                        candidate_target, current_tracking
                    ):
                        retained_tracking = current_tracking
                    elif current_tracking == candidate_target:
                        retained_tracking = candidate_target
                    elif (
                        self.is_ancestor(base_target, current_tracking)
                        and self.is_ancestor(current_tracking, candidate_target)
                    ):
                        reference = f"refs/remotes/origin/{self.target_branch}"
                        updated = self._git(
                            (
                                "update-ref",
                                reference,
                                candidate_target,
                                current_tracking,
                            ),
                            check=False,
                        )
                        if updated.returncode != 0:
                            raise AutopilotError(
                                "GitHub snapshot target tracking ref compare-and-swap conflicted"
                            )
                        retained_tracking = candidate_target
                    else:
                        raise AutopilotError(
                            "GitHub snapshot candidate is stale or non-descendant of "
                            "the current target tracking ref"
                        )
                    observed_tracking = self._target_tracking_sha()
                    if observed_tracking != retained_tracking:
                        raise AutopilotError(
                            "GitHub snapshot target tracking ref changed during CAS proof"
                        )
                    if not (
                        observed_tracking == candidate_target
                        or (
                            cas_already_applied
                            and self.is_ancestor(candidate_target, observed_tracking)
                        )
                    ):
                        raise AutopilotError(
                            "GitHub snapshot target tracking ref did not retain or "
                            "compatibly overtake the candidate"
                        )
                    if execution_target is None:
                        expected_execution_target = "0" * 40
                    elif execution_target == candidate_target:
                        expected_execution_target = None
                    elif execution_target == base_target:
                        expected_execution_target = base_target
                    else:
                        raise AutopilotError(
                            "execution target changed before snapshot installation"
                        )
                    if expected_execution_target is not None:
                        pinned = self._git(
                            (
                                "update-ref",
                                self.execution_target_ref,
                                candidate_target,
                                expected_execution_target,
                            ),
                            check=False,
                        )
                        if pinned.returncode != 0:
                            raise AutopilotError(
                                "execution target compare-and-swap conflicted"
                            )
                    if self._execution_target_sha() != candidate_target:
                        raise AutopilotError(
                            "execution target did not retain the snapshot candidate"
                        )
                    target_watermark = self.repository_target_watermark()
                    watermark_sha = str(target_watermark["target_sha"])
                    if watermark_sha != candidate_target:
                        if self.is_ancestor(watermark_sha, candidate_target):
                            target_watermark = (
                                self.advance_repository_target_watermark_from_snapshot(
                                    expected_generation=int(
                                        target_watermark["target_generation"]
                                    ),
                                    expected_target_sha=watermark_sha,
                                    target_sha=candidate_target,
                                    source_observation=current_observation,
                                    actor="autopilot:snapshot",
                                )
                            )
                        elif not self.is_ancestor(candidate_target, watermark_sha):
                            raise AutopilotError(
                                "repository target watermark conflicts with the "
                                "snapshot candidate"
                            )
                elif candidate_target != current_observation.get("base_target_sha"):
                    raise AutopilotError(
                        "lightweight snapshot fixtures cannot advance an unverified target"
                    )

        # Phase three finalizes only if the exact CAS result and observation remain
        # current. An identical retry can resume from any preceding crash point.
        with self._host_arbiter_execution_guard():
            self._assert_execution_not_terminal_unlocked(
                "GitHub snapshot installation finalization"
            )
            self._assert_no_global_host_reservations(
                "GitHub snapshot installation finalization"
            )
            self._assert_no_execution_launch_reservations(
                "GitHub snapshot installation finalization"
            )
            if self.active_claims():
                raise AutopilotError(
                    "GitHub snapshot finalization is fenced by active claims"
                )
            observation = self._snapshot_observation()
            observation_issues = self._snapshot_observation_issues(observation)
            if observation_issues:
                raise AutopilotError("; ".join(observation_issues))
            assert isinstance(observation, Mapping)
            if (
                observation.get("observation_id") != observation_id
                or observation.get("record_id") != observation_record_id
                or observation.get("snapshot_digest") != snapshot_digest
                or observation.get("candidate_artifact") != expected_artifact
                or observation.get("status") not in {"INSTALLING", "INSTALLED"}
            ):
                raise AutopilotError(
                    "GitHub snapshot observation changed before installation finalized"
                )
            candidate = self._strict_json_file(
                self._secure_execution_path(expected_artifact),
                label="immutable GitHub snapshot candidate",
            )
            if digest_json(candidate) != snapshot_digest:
                raise AutopilotError(
                    "immutable GitHub snapshot candidate changed before finalization"
                )
            if self.verify_git_objects and self._execution_target_sha() != candidate_target:
                raise AutopilotError(
                    "execution target moved before snapshot finalization"
                )
            if self.verify_git_objects:
                target_watermark = self.repository_target_watermark()
                watermark_sha = str(target_watermark["target_sha"])
                if not (
                    watermark_sha == candidate_target
                    or self.is_ancestor(candidate_target, watermark_sha)
                ):
                    raise AutopilotError(
                        "repository target watermark no longer contains the snapshot target"
                    )
            canonical_after = self._canonical_dispatch_identity()
            if canonical_after != self._dispatch_identity_at(candidate_target):
                raise AutopilotError(
                    "canonical dispatcher identity changed during snapshot installation"
                )

            path = self.github_snapshot_path
            if path.is_file():
                installed_candidate = self._strict_json_file(
                    path, label="installed GitHub snapshot evidence"
                )
                if digest_json(installed_candidate) != snapshot_digest:
                    raise AutopilotError(
                        "installed GitHub snapshot evidence conflicts with sealed candidate"
                    )
            else:
                assert isinstance(candidate, Mapping)
                self._atomic_write_authority_json(path, candidate)
            execution = self._execution()
            if execution is not None:
                atomic_write_json(
                    self.retirement_recovery_path,
                    {
                        "schema_version": 1,
                        "kind": RETIREMENT_KIND,
                        "retirement_id": execution["retirement_id"],
                        "snapshot_digest": snapshot_digest,
                        "reconciliation_digest": None,
                        "target_sha": candidate_target,
                        "recorded_at": format_time(self.clock()),
                    },
                )

            if observation.get("status") != "INSTALLED":
                installed_observation = dict(observation)
                installed_observation["status"] = "INSTALLED"
                installed_observation["installed_at"] = format_time(self.clock())
                observation = self._seal_snapshot_observation(installed_observation)
                self._atomic_write_authority_json(
                    self.snapshot_observation_path, observation
                )
            if not self._snapshot_generation_matches(
                self._dispatcher_generation(), observation, snapshot_digest
            ):
                self._invalidate_dispatcher_admission_unlocked(
                    actor="autopilot:snapshot",
                    reason="install or recover a GitHub snapshot watermark",
                    github_snapshot_digest=snapshot_digest,
                    reconciliation_digest=None,
                )
            return path

    def reconcile(self, target_sha: str, *, actor: str, reason: str, changed_paths: Sequence[str] = ()) -> Path:
        with self._host_arbiter_execution_guard():
            self._assert_execution_not_terminal_unlocked("target reconciliation")
            self._assert_no_global_host_reservations("target reconciliation")
            self._assert_no_execution_launch_reservations("target reconciliation")
            self._assert_no_publication_transaction("target reconciliation")
            active = self.active_claims()
            if active:
                raise AutopilotError(
                    "target reconciliation is deferred while shared claims are active"
                )
            generation = self._dispatcher_generation()
            issues = self._dispatcher_generation_issues(generation)
            if issues:
                raise AutopilotError(
                    "target reconciliation requires shared snapshot authority: "
                    + "; ".join(issues)
                )
            assert isinstance(generation, Mapping)
            snapshot_digest = self._snapshot_digest()
            observation = self._snapshot_observation()
            observation_issues = self._snapshot_observation_dispatch_issues(
                snapshot_digest,
                expected_observation_id=(
                    observation.get("observation_id")
                    if isinstance(observation, Mapping)
                    else None
                ),
                expected_observation_epoch=(
                    observation.get("observation_epoch")
                    if isinstance(observation, Mapping)
                    else None
                ),
                expected_observation_record_id=(
                    observation.get("record_id")
                    if isinstance(observation, Mapping)
                    else None
                ),
                expected_target_sha=target_sha,
                expected_plan_fingerprint=self.expected_plan_fingerprint,
            )
            if observation_issues:
                raise AutopilotError(
                    "target reconciliation requires completed shared snapshot authority: "
                    + "; ".join(observation_issues)
                )
            if (
                snapshot_digest is None
                or generation.get("github_snapshot_digest") != snapshot_digest
            ):
                raise AutopilotError(
                    "target reconciliation requires this worktree to install the latest "
                    "shared GitHub snapshot"
                )
            path = super().reconcile(
                target_sha,
                actor=actor,
                reason=reason,
                changed_paths=changed_paths,
            )
            execution = self._execution()
            recovery = self._sealed_document(self.retirement_recovery_path)
            if execution is not None and recovery is not None and recovery.get("snapshot_digest") == self._snapshot_digest():
                updated = dict(recovery)
                updated["reconciliation_digest"] = self._reconciliation_digest()
                updated["target_sha"] = self.current_target_sha()
                updated["recorded_at"] = format_time(self.clock())
                atomic_write_json(self.retirement_recovery_path, updated)
            reconciliation_digest = self._reconciliation_digest()
            if reconciliation_digest is None:
                raise AutopilotError(
                    "target reconciliation did not produce current canonical evidence"
                )
            self._invalidate_dispatcher_admission_unlocked(
                actor=actor,
                reason="target reconciliation advanced shared dispatcher evidence",
                github_snapshot_digest=snapshot_digest,
                reconciliation_digest=reconciliation_digest,
            )
            return path

    def _shared_release_shape_issues(self, record: object) -> tuple[str, ...]:
        """Validate shared authority without consulting worktree-local evidence."""

        if not isinstance(record, Mapping):
            return ("dispatcher release record is missing or invalid",)
        issues: list[str] = []
        required_fields = {
            "schema_version",
            "kind",
            "actor",
            "execution_namespace",
            "execution_id",
            "repository",
            "target_branch",
            "target_sha",
            "target_generation",
            "target_watermark_record_id",
            "plan_fingerprint",
            "reconciliation_digest",
            "github_snapshot_digest",
            "snapshot_observation_id",
            "snapshot_observation_epoch",
            "snapshot_observation_record_id",
            "host_id",
            "capacity_generation",
            "capacity_epoch",
            "capacity_record_id",
            "capacity_max_total_sessions",
            "capacity_validation_slots",
            "session_cap",
            "admission_epoch",
            "supersedes_release_id",
            "released_wave",
            "directive",
            "action",
            "verdicts",
            "issued_at",
            "receipt_retirement_execution_digest",
            "primary_host_reservations",
            "release_admission_id",
            "release_id",
        }
        if set(record) != required_fields:
            issues.append("dispatcher release fields are invalid")
        if record.get("schema_version") != 1 or record.get("kind") != RELEASE_KIND:
            issues.append("dispatcher release schema/kind is invalid")
        material = dict(record)
        release_id = material.pop("release_id", None)
        if release_id != digest_json(material):
            issues.append("dispatcher release digest is invalid")
        admission_material = dict(record)
        admission_id = admission_material.pop("release_admission_id", None)
        admission_material.pop("release_id", None)
        admission_material.pop("primary_host_reservations", None)
        expected_admission_id = digest_json(
            {
                "kind": "hive-mind-release-admission-key-v1",
                "release": admission_material,
            }
        )
        if admission_id != expected_admission_id:
            issues.append("dispatcher release admission id is invalid")
        if type(record.get("admission_epoch")) is not int or int(record["admission_epoch"]) < 1:
            issues.append("dispatcher release admission epoch is invalid")
        if (
            record.get("execution_namespace") != self.execution_namespace
            or record.get("execution_id") != self.execution_id
        ):
            issues.append("dispatcher release execution identity is invalid")
        host_id = record.get("host_id")
        if not isinstance(host_id, str) or not host_id.strip():
            issues.append("dispatcher release host id is invalid")
        for field in ("capacity_generation", "capacity_record_id"):
            value = record.get(field)
            if not isinstance(value, str) or AUTHORITY_ID.fullmatch(value) is None:
                issues.append(f"dispatcher release {field} is invalid")
        for field in (
            "capacity_epoch",
            "capacity_max_total_sessions",
            "capacity_validation_slots",
        ):
            value = record.get(field)
            if type(value) is not int or value < 0:
                issues.append(f"dispatcher release {field} is invalid")
        if record.get("capacity_epoch", 0) < 1 or record.get(
            "capacity_max_total_sessions", 0
        ) < 1:
            issues.append("dispatcher release host capacity bounds are invalid")
        session_cap = record.get("session_cap")
        if type(session_cap) is not int or session_cap < 1:
            issues.append("dispatcher release session cap is invalid")
        try:
            canonical = self._canonical_dispatch_identity()
        except Exception as error:
            issues.append(f"canonical dispatcher identity is unavailable: {error}")
            canonical = {}
        for field in ("repository", "target_branch", "target_sha", "plan_fingerprint"):
            if record.get(field) != canonical.get(field):
                issues.append(f"dispatcher release {field} is stale or noncanonical")
        if type(record.get("target_generation")) is not int or int(
            record.get("target_generation", 0)
        ) < 1:
            issues.append("dispatcher release target generation is invalid")
        if AUTHORITY_ID.fullmatch(
            str(record.get("target_watermark_record_id"))
        ) is None:
            issues.append("dispatcher release target watermark record is invalid")
        try:
            target_watermark = self.repository_target_watermark()
        except Exception as error:
            issues.append(f"repository target watermark is unavailable: {error}")
        else:
            if (
                record.get("target_sha") != target_watermark.get("target_sha")
                or record.get("target_generation")
                != target_watermark.get("target_generation")
                or record.get("target_watermark_record_id")
                != target_watermark.get("record_id")
            ):
                issues.append(
                    "dispatcher release repository target watermark is stale"
                )
        for field in ("reconciliation_digest", "github_snapshot_digest"):
            value = record.get(field)
            if not isinstance(value, str) or AUTHORITY_ID.fullmatch(value) is None:
                issues.append(f"dispatcher release {field} is invalid")
        observation_id = record.get("snapshot_observation_id")
        if (
            not isinstance(observation_id, str)
            or AUTHORITY_ID.fullmatch(observation_id) is None
        ):
            issues.append("dispatcher release snapshot observation id is invalid")
        observation_epoch = record.get("snapshot_observation_epoch")
        if type(observation_epoch) is not int or observation_epoch < 1:
            issues.append("dispatcher release snapshot observation epoch is invalid")
        observation_record_id = record.get("snapshot_observation_record_id")
        if (
            not isinstance(observation_record_id, str)
            or AUTHORITY_ID.fullmatch(observation_record_id) is None
        ):
            issues.append(
                "dispatcher release snapshot observation record digest is invalid"
            )
        wave = record.get("released_wave")
        if (
            not isinstance(wave, list)
            or any(not isinstance(node_id, str) or not node_id for node_id in wave)
            or len(wave) != len(set(wave))
        ):
            issues.append("dispatcher release wave is invalid")
            wave = []
        if type(session_cap) is int and len(wave) > session_cap:
            issues.append("dispatcher release exceeds authenticated host capacity")
        try:
            active_host_reservations = self._active_execution_host_reservations()
        except Exception as error:
            issues.append(f"dispatcher host reservation inventory is unavailable: {error}")
            active_host_reservations = ()
        release_bound_reservations = [
            item
            for item in active_host_reservations
            if item.get("reservation_kind") in {"WRITE_LAUNCH", "SIDECAR"}
        ]
        for reservation in release_bound_reservations:
            if (
                reservation.get("dispatcher_release_id")
                != record.get("release_id")
                or reservation.get("dispatcher_admission_epoch")
                != record.get("admission_epoch")
                or reservation.get("capacity_host_id") != record.get("host_id")
                or reservation.get("capacity_generation")
                != record.get("capacity_generation")
            ):
                issues.append(
                    "active launch/sidecar reservation differs from dispatcher release"
                )
        claims = self.active_claims()
        latest_bindings: dict[str, Mapping[str, object]] = {}
        try:
            for event in binding_events(
                self.repo_root, state_dir=self.execution_dir
            ):
                instruction_id = event.get("launch_instruction_id")
                if isinstance(instruction_id, str):
                    latest_bindings[instruction_id] = event
        except Exception as error:
            issues.append(f"dispatcher terminal binding inventory is unavailable: {error}")
        terminal_release_binding = any(
            event.get("dispatcher_release_id") == record.get("release_id")
            and event.get("dispatcher_admission_epoch")
            == record.get("admission_epoch")
            and event.get("state") in {"RELEASED", "SUPERSEDED"}
            for event in latest_bindings.values()
        )
        authority_is_in_use = (
            bool(release_bound_reservations)
            or terminal_release_binding
            or any(node_id in claims for node_id in wave)
        )
        if not authority_is_in_use:
            try:
                expected_wave = self._compiled_frontier(
                    self._base_status(),
                    max_sessions=session_cap if type(session_cap) is int else 0,
                )
                if wave != expected_wave:
                    issues.append(
                        "dispatcher release is not the exact authenticated compiled frontier"
                    )
            except Exception as error:
                issues.append(f"authenticated compiled frontier is unavailable: {error}")
        verdicts = record.get("verdicts")
        if not isinstance(verdicts, Mapping) or set(verdicts) != set(self._nodes):
            issues.append("dispatcher release does not cover every candidate node")
            verdicts = {}
        elif any(value not in {"START NOW", "WAIT", "STOP"} for value in verdicts.values()):
            issues.append("dispatcher release contains an invalid candidate verdict")
        for node_id in wave:
            if node_id not in self._nodes:
                issues.append(f"dispatcher release contains unknown node: {node_id}")
                continue
            if verdicts.get(node_id) != "START NOW":
                issues.append(f"released node lacks START NOW verdict: {node_id}")
        for index, first in enumerate(wave):
            if first not in self._nodes:
                continue
            for second in wave[index + 1:]:
                if second not in self._nodes:
                    continue
                if not bool(self.node(first).get("parallel_safe")) or not bool(
                    self.node(second).get("parallel_safe")
                ):
                    issues.append(
                        f"dispatcher release contains a serial node pair: {first} vs {second}"
                    )
                elif self._nodes_conflict(first, second):
                    issues.append(
                        f"dispatcher release contains a conflicting pair: {first} vs {second}"
                    )
        directive, action = self._action_sentence(wave)
        if record.get("directive") != directive or record.get("action") != action:
            issues.append("dispatcher release directive/action is inconsistent with released wave")
        for node_id in wave:
            if node_id not in self._nodes:
                continue
            conflicts = self._claim_conflicts(node_id, claims)
            if conflicts:
                issues.append(
                    f"dispatcher release invalidated by conflicting claim for {node_id}: "
                    + "; ".join(conflicts)
                )
        reservations = record.get("primary_host_reservations")
        if not isinstance(reservations, list) or len(reservations) != len(wave):
            issues.append("dispatcher release primary host reservations are incomplete")
        else:
            for index, reservation in enumerate(reservations):
                if (
                    not isinstance(reservation, Mapping)
                    or set(reservation)
                    != {"node_id", "resource_key", "reservation_id"}
                    or reservation.get("node_id") != wave[index]
                    or not isinstance(reservation.get("resource_key"), str)
                    or AUTHORITY_ID.fullmatch(str(reservation.get("resource_key")))
                    is None
                    or not isinstance(reservation.get("reservation_id"), str)
                    or AUTHORITY_ID.fullmatch(str(reservation.get("reservation_id")))
                    is None
                ):
                    issues.append(
                        "dispatcher release primary host reservation schema is invalid"
                    )
        return tuple(dict.fromkeys(issues))

    def _release_capacity_issuance_unlocked(
        self, release: Mapping[str, Any]
    ) -> Mapping[str, object]:
        """Authenticate a release's original record in the live generation.

        Same-policy renewal deliberately rotates only the capacity record and
        expiry.  The release keeps its original record as issuance evidence, so
        effect admission must prove that record is an authenticated predecessor
        of the current generation rather than compare it to current.json.
        """

        if not runtime_file_lock_is_held(
            self.host_runtime_dir / "locks" / "host-authority.lock"
        ):
            raise AutopilotError(
                "dispatcher capacity lineage requires host authority"
            )
        host_id = release.get("host_id")
        capacity_generation = release.get("capacity_generation")
        capacity_record_id = release.get("capacity_record_id")
        if (
            not isinstance(host_id, str)
            or not host_id.strip()
            or not isinstance(capacity_generation, str)
            or AUTHORITY_ID.fullmatch(capacity_generation) is None
            or not isinstance(capacity_record_id, str)
            or AUTHORITY_ID.fullmatch(capacity_record_id) is None
        ):
            raise AutopilotError("dispatcher capacity issuance is malformed")
        issuance = host_capacity_record_in_current_lineage(
            self.host_runtime_dir,
            host_id,
            capacity_generation=capacity_generation,
            record_id=capacity_record_id,
        )
        if any(
            issuance.get(capacity_field) != release.get(release_field)
            for capacity_field, release_field in (
                ("host_id", "host_id"),
                ("capacity_generation", "capacity_generation"),
                ("capacity_epoch", "capacity_epoch"),
                ("record_id", "capacity_record_id"),
                ("max_total_sessions", "capacity_max_total_sessions"),
                ("validation_slots", "capacity_validation_slots"),
            )
        ):
            raise AutopilotError(
                "dispatcher release differs from authenticated capacity issuance"
            )
        return issuance

    def _issuer_release_issues(self, record: object) -> tuple[str, ...]:
        issues = list(super()._release_issues(record))
        issues.extend(self._shared_release_shape_issues(record))
        execution = self._execution()
        if execution is not None:
            expected = digest_json(execution)
            if not isinstance(record, Mapping) or record.get("receipt_retirement_execution_digest") != expected:
                issues.append("dispatcher release was issued before receipt retirement recovery")
        return tuple(dict.fromkeys(issues))

    def _release_issues(self, record: object) -> tuple[str, ...]:
        """Validate consumer authority solely from shared/canonical state."""

        issues = list(self._shared_release_shape_issues(record))
        generation = self._dispatcher_generation()
        generation_issues = self._dispatcher_generation_issues(generation)
        issues.extend(generation_issues)
        expected_snapshot_digest = (
            record.get("github_snapshot_digest")
            if isinstance(record, Mapping)
            else None
        )
        issues.extend(
            self._snapshot_observation_dispatch_issues(
                expected_snapshot_digest,
                expected_observation_id=(
                    record.get("snapshot_observation_id")
                    if isinstance(record, Mapping)
                    else None
                ),
                expected_observation_epoch=(
                    record.get("snapshot_observation_epoch")
                    if isinstance(record, Mapping)
                    else None
                ),
                expected_observation_record_id=(
                    record.get("snapshot_observation_record_id")
                    if isinstance(record, Mapping)
                    else None
                ),
                expected_target_sha=(
                    record.get("target_sha") if isinstance(record, Mapping) else None
                ),
                expected_plan_fingerprint=(
                    record.get("plan_fingerprint")
                    if isinstance(record, Mapping)
                    else None
                ),
            )
        )
        if not generation_issues and isinstance(generation, Mapping):
            if generation.get("status") != "ACTIVE":
                issues.append("shared dispatcher admission is invalidated")
            if not isinstance(record, Mapping) or (
                generation.get("release_id") != record.get("release_id")
                or generation.get("admission_epoch") != record.get("admission_epoch")
            ):
                issues.append("shared dispatcher admission generation fence mismatch")
            if isinstance(record, Mapping) and any(
                generation.get(field) != record.get(field)
                for field in (
                    "execution_namespace",
                    "execution_id",
                    "repository",
                    "target_branch",
                    "target_sha",
                    "plan_fingerprint",
                    "github_snapshot_digest",
                    "reconciliation_digest",
                    "snapshot_observation_id",
                    "snapshot_observation_epoch",
                    "snapshot_observation_record_id",
                    "host_id",
                    "capacity_generation",
                    "capacity_epoch",
                    "capacity_record_id",
                    "session_cap",
                )
            ):
                issues.append("shared dispatcher generation identity mismatch")
        return tuple(dict.fromkeys(issues))

    def _append_release_history_once(self, record: Mapping[str, Any]) -> None:
        """Complete the release/history pair without duplicating a crash retry."""

        records = strict_jsonl_records(
            self.release_history_path,
            label="execution dispatcher release history",
        )
        matching = [
            item
            for item in records
            if item.get("release_id") == record.get("release_id")
        ]
        if matching:
            if len(matching) != 1 or matching[0] != record or records[-1] != record:
                raise AutopilotError(
                    "dispatcher release history conflicts with crash recovery"
                )
            return
        append_jsonl(self.release_history_path, record)

    def dispatch(
        self,
        *,
        actor: str,
        host_id: str,
        execution_adapter_identity: Mapping[str, object],
        requested_nodes: Sequence[str] = (),
    ) -> Mapping[str, Any]:
        """Reserve host slots and publish one execution-scoped release atomically."""

        if not isinstance(host_id, str) or not host_id.strip():
            raise AutopilotError("dispatcher requires an authenticated host id")
        repository = str(self.control["target"]["repository"])
        issued_at = format_time(self.clock())

        # Preflight capacity without a repository/execution lock. The final phase
        # rereads every byte and refuses if availability changed.
        with self.host_lock(timeout_seconds=120.0):
            capacity = reconcile_pending_host_capacity_renewal(
                self.host_runtime_dir,
                host_id=host_id,
                now=self.clock(),
            )
            self._dispatcher_adapter_coordinates(
                execution_adapter_identity,
                capacity=capacity,
                repository=repository,
                host_id=host_id,
                execution_namespace=self.execution_namespace,
                execution_id=self.execution_id,
            )
            host_reservations = active_global_host_reservations(
                self.host_runtime_dir
            )
        # The host kernel enforces one aggregate OS-user ceiling.  Provider ids
        # authenticate provenance; they never partition capacity.
        occupied = list(host_reservations)
        own = [
            item
            for item in occupied
            if item.get("execution_id") == self.execution_id
            and item.get("host_id") == host_id
        ]
        capacity_limit = int(capacity["max_total_sessions"])

        if own:
            with self.host_lock(timeout_seconds=120.0):
                with self.arbiter_lock(timeout_seconds=120.0):
                    with self.execution_lock(
                        "dispatcher-admission.lock", timeout_seconds=120.0
                    ):
                        current_capacity = reconcile_pending_host_capacity_renewal(
                            self.host_runtime_dir,
                            host_id=host_id,
                            now=self.clock(),
                        )
                        current_own = [
                            item
                            for item in active_global_host_reservations(
                                self.host_runtime_dir
                            )
                            if item.get("host_id") == host_id
                            and item.get("execution_id") == self.execution_id
                        ]
                        current = self.current_release()
                        issues = self._release_issues(current)
                        issuer_issues = self._issuer_release_issues(current)
                        if not issuer_issues and isinstance(current, Mapping):
                            self._release_capacity_issuance_unlocked(current)
                            expected_ids = {
                                str(item.get("reservation_id"))
                                for item in current.get(
                                    "primary_host_reservations", []
                                )
                                if isinstance(item, Mapping)
                            }
                            active_ids = {
                                str(item.get("reservation_id"))
                                for item in current_own
                                if item.get("reservation_kind") == "PRIMARY"
                            }
                            requested = [str(item) for item in requested_nodes]
                            exact_permits = (
                                current.get("host_id") == host_id
                                and expected_ids == active_ids
                                and all(
                                    item.get(
                                        "execution_adapter_identity_record_id"
                                    )
                                    == execution_adapter_identity.get("record_id")
                                    for item in current_own
                                )
                                and current.get("capacity_generation")
                                == current_capacity.get("capacity_generation")
                                and current.get("capacity_epoch")
                                == current_capacity.get("capacity_epoch")
                                and current.get("capacity_max_total_sessions")
                                == current_capacity.get("max_total_sessions")
                                and current.get("capacity_validation_slots")
                                == current_capacity.get("validation_slots")
                                and (
                                    not requested
                                    or requested
                                    == list(current.get("released_wave", []))
                                )
                            )
                            if exact_permits and not issues:
                                return current
                            if exact_permits:
                                generation = self._dispatcher_generation()
                                if isinstance(generation, Mapping) and int(
                                    generation.get("admission_epoch", 0)
                                ) > int(current.get("admission_epoch", 0)):
                                    raise AutopilotError(
                                        "dispatcher crash recovery would regress admission authority"
                                    )
                                self._append_release_history_once(current)
                                self._publish_dispatch_generation_unlocked(current)
                                repaired_issues = self._release_issues(current)
                                if repaired_issues:
                                    raise AutopilotError(
                                        "dispatcher crash recovery did not restore exact authority: "
                                        + "; ".join(repaired_issues)
                                    )
                                return current
                        # A crash may have persisted only a strict prefix of the
                        # permit/release/history/generation transaction.  With no
                        # launch or sidecar bound yet, the stable permit coordinates
                        # below can reconstruct and finish that exact admission.
                        self._assert_no_execution_launch_reservations(
                            "dispatcher crash recovery"
                        )

        # Build all expensive local evidence outside global locks. Existing exact
        # permits use their first reservation time so a crash retry is deterministic.
        with self.arbiter_lock(timeout_seconds=120.0):
            with self.execution_lock(
                "dispatcher-admission.lock", timeout_seconds=120.0
            ):
                draft = self._build_dispatch_release_unlocked(
                    actor=actor,
                    host_id=host_id,
                    capacity=capacity,
                    session_cap=capacity_limit,
                    issued_at=issued_at,
                    requested_nodes=requested_nodes,
                )

        reserved: list[Mapping[str, Any]] = []
        newly_reserved: list[Mapping[str, Any]] = []
        with self.host_lock(timeout_seconds=120.0):
            with self.arbiter_lock(timeout_seconds=120.0):
                with self.execution_lock(
                    "dispatcher-admission.lock", timeout_seconds=120.0
                ):
                    current_capacity = reconcile_pending_host_capacity_renewal(
                        self.host_runtime_dir,
                        host_id=host_id,
                        now=self.clock(),
                    )
                    if current_capacity != capacity:
                        raise AutopilotError(
                            "host capacity generation changed during dispatcher admission"
                        )
                    current_inventory = active_global_host_reservations(
                        self.host_runtime_dir
                    )
                    current_occupied = list(current_inventory)
                    current_own = [
                        item
                        for item in current_occupied
                        if item.get("execution_id") == self.execution_id
                        and item.get("host_id") == host_id
                    ]
                    concurrent_release = self.current_release()
                    concurrent_issues = self._release_issues(concurrent_release)
                    if not concurrent_issues and isinstance(
                        concurrent_release, Mapping
                    ):
                        self._release_capacity_issuance_unlocked(
                            concurrent_release
                        )
                        release_permits = {
                            str(item.get("reservation_id"))
                            for item in concurrent_release.get(
                                "primary_host_reservations", []
                            )
                            if isinstance(item, Mapping)
                        }
                        inventory_permits = {
                            str(item.get("reservation_id"))
                            for item in current_own
                            if item.get("reservation_kind") == "PRIMARY"
                        }
                        requested = [str(item) for item in requested_nodes]
                        if (
                            concurrent_release.get("host_id") == host_id
                            and release_permits == inventory_permits
                            and all(
                                item.get(
                                    "execution_adapter_identity_record_id"
                                )
                                == execution_adapter_identity.get("record_id")
                                for item in current_own
                            )
                            and (
                                not requested
                                or requested
                                == list(concurrent_release.get("released_wave", []))
                            )
                        ):
                            return concurrent_release
                        raise AutopilotError(
                            "another dispatcher completed a different live admission"
                        )
                    repeated_full = self._build_dispatch_release_unlocked(
                        actor=actor,
                        host_id=host_id,
                        capacity=capacity,
                        session_cap=capacity_limit,
                        issued_at=issued_at,
                        requested_nodes=requested_nodes,
                    )
                    if repeated_full != draft:
                        raise AutopilotError(
                            "dispatcher evidence changed before host reservation"
                        )
                    self._assert_no_execution_launch_reservations(
                        "dispatcher pre-launch admission"
                    )
                    full_coordinates = self._primary_reservation_coordinates(draft)
                    demand = record_host_scheduler_demand(
                        self.host_runtime_dir,
                        host_id=host_id,
                        repository=repository,
                        repository_transport_digest=str(
                            self.repository_identity["transport_digest"]
                        ),
                        execution_namespace=self.execution_namespace,
                        execution_id=self.execution_id,
                        plan_fingerprint=self.expected_plan_fingerprint,
                        capacity_generation=str(capacity["capacity_generation"]),
                        execution_adapter_identity=execution_adapter_identity,
                        candidate_reservation_ids=[
                            str(item["local_reservation_id"])
                            for item in full_coordinates
                        ],
                        weight=1,
                        actor=actor,
                        recorded_at=issued_at,
                    )
                    scheduler = grant_host_scheduler_capacity(
                        self.host_runtime_dir,
                        host_id=host_id,
                        actor=actor,
                        now=self.clock(),
                    )
                    grants_by_local = {
                        str(item["local_reservation_id"]): item
                        for item in scheduler["outstanding_grants"]
                        if isinstance(item, Mapping)
                        and item.get("demand_id") == demand.get("demand_id")
                    }
                    selected_coordinates = [
                        item
                        for item in full_coordinates
                        if str(item["local_reservation_id"]) in grants_by_local
                    ]
                    if not selected_coordinates:
                        raise HostCapacityWaiting(
                            "authenticated demand is queued without a current host grant"
                        )
                    selected_nodes = [
                        str(item["node_id"]) for item in selected_coordinates
                    ]
                    repeated = self._build_dispatch_release_unlocked(
                        actor=actor,
                        host_id=host_id,
                        capacity=capacity,
                        session_cap=capacity_limit,
                        issued_at=issued_at,
                        requested_nodes=selected_nodes,
                    )
                    wave = list(repeated["released_wave"])
                    expected_coordinates = self._primary_reservation_coordinates(
                        repeated
                    )
                    admission_intent, prospective_release = (
                        self._dispatcher_admission_intent(
                            repeated,
                            expected_coordinates,
                            capacity,
                            execution_adapter_identity,
                            grants_by_local,
                        )
                    )
                    admission_intent = self._write_dispatcher_admission_intent(
                        admission_intent
                    )
                    by_local = {
                            str(item.get("local_reservation_id")): item
                            for item in current_own
                            if item.get("reservation_kind") == "PRIMARY"
                        }
                    expected_local_ids = {
                            item["local_reservation_id"]
                            for item in expected_coordinates
                        }
                    if any(
                        item.get("reservation_kind") != "PRIMARY"
                        for item in current_own
                    ):
                        raise AutopilotError(
                            "non-primary host reservations fence dispatcher recovery"
                        )
                    unexpected = set(by_local) - expected_local_ids
                    if unexpected:
                        for local_id in sorted(unexpected):
                            reservation = by_local[local_id]
                            abandoned_intent = (
                                self._dispatcher_intent_for_reservation(
                                    reservation
                                )
                            )
                            self._abort_global_primary_reservation(
                                reservation,
                                abandoned_intent,
                                actor=actor,
                                reason="fence abandoned partial dispatcher admission",
                            )
                            by_local.pop(local_id)
                    expires_at = min(
                        parse_time(capacity["expires_at"]),
                        self.clock() + timedelta(minutes=90),
                    )
                    try:
                        for coordinate in expected_coordinates:
                            existing = by_local.get(
                                str(coordinate["local_reservation_id"])
                            )
                            if existing is not None:
                                reserved.append(existing)
                                continue
                            created = reserve_global_host_session(
                                self.host_runtime_dir,
                                repository=repository,
                                execution_id=self.execution_id,
                                host_id=host_id,
                                capacity_generation=str(
                                    capacity["capacity_generation"]
                                ),
                                local_reservation_id=str(
                                    coordinate["local_reservation_id"]
                                ),
                                reservation_kind="PRIMARY",
                                resource_key=str(coordinate["resource_key"]),
                                write_scopes=list(coordinate["write_scopes"]),
                                actor_time=issued_at,
                                expires_at=format_time(expires_at),
                                now=self.clock(),
                                execution_adapter_identity=(
                                    execution_adapter_identity
                                ),
                                host_scheduler_grant_id=str(
                                    grants_by_local[
                                        str(coordinate["local_reservation_id"])
                                    ]["grant_id"]
                                ),
                            )
                            reserved.append(created)
                            newly_reserved.append(created)
                    except Exception:
                        for reservation in reversed(newly_reserved):
                            self._abort_global_primary_reservation(
                                reservation,
                                admission_intent,
                                actor=actor,
                                reason="rollback incomplete dispatcher admission",
                            )
                        raise
                    actual_reservations = [
                        {
                            "node_id": wave[index],
                            "resource_key": reservation["resource_key"],
                            "reservation_id": reservation["reservation_id"],
                        }
                        for index, reservation in enumerate(reserved)
                    ]
                    if actual_reservations != prospective_release.get(
                        "primary_host_reservations"
                    ):
                        for reservation in reversed(newly_reserved):
                            self._abort_global_primary_reservation(
                                reservation,
                                admission_intent,
                                actor=actor,
                                reason="rollback mismatched dispatcher permits",
                            )
                        raise AutopilotError(
                            "reserved host permits differ from durable dispatcher intent"
                        )
                    record = dict(prospective_release)
                    issues = self._issuer_release_issues(record)
                    if issues:
                        for reservation in reversed(newly_reserved):
                            self._abort_global_primary_reservation(
                                reservation,
                                admission_intent,
                                actor=actor,
                                reason="rollback rejected dispatcher release",
                            )
                        raise AutopilotError(
                            "dispatcher candidate failed issuer validation: "
                            + "; ".join(issues)
                        )
                    self._atomic_write_authority_json(
                        self.current_release_path, record
                    )
                    self._append_release_history_once(record)
                    self._publish_dispatch_generation_unlocked(record)
                    return record

    def authenticate_dispatch_plan_assertion(self, plan_path: Path) -> None:
        """Accept ``--plan`` only when it asserts the exact canonical graph.

        ``dag-rounds`` may compile an equivalent plan from a nonstandard path. The
        path never becomes authority: dispatch still uses the target-authenticated
        repository plan and merely proves the supplied graph has the same fingerprint.
        """

        if not plan_path.is_file() or self._is_link_like(plan_path):
            raise AutopilotError("dispatch plan assertion is unavailable or link-backed")
        try:
            raw = plan_path.read_bytes()
        except OSError as error:
            raise AutopilotError(
                f"dispatch plan assertion is unavailable: {error}"
            ) from error
        if not raw or len(raw) > MAX_TARGET_PLAN_BYTES:
            raise AutopilotError("dispatch plan assertion exceeds its bounded envelope")
        try:
            candidate = parse_strict_canonical_json_bytes(
                raw,
                label="dispatch plan assertion",
                expected_fields=TARGET_PLAN_FIELDS,
            )
        except ConfigurationError as error:
            raise AutopilotError(str(error)) from error
        if not isinstance(candidate, Mapping):
            raise AutopilotError("dispatch plan assertion must be a JSON object")
        material = dict(candidate)
        embedded = material.pop("plan_fingerprint", None)
        if (
            embedded != self.expected_plan_fingerprint
            or digest_json(material) != self.expected_plan_fingerprint
        ):
            raise AutopilotError(
                "dispatch plan assertion differs from the canonical target plan; "
                "custom plans are analysis-only until governed promotion"
            )

    def _compiled_frontier(
        self, status: Mapping[str, Any], *, max_sessions: int
    ) -> list[str]:
        """Return the pending members of the canonical compiled barrier.

        A host-capacity generation may legitimately widen after earlier members
        of a compiled level have completed.  ``select_round`` then recompiles the
        level at the new capacity and returns the whole first incomplete round,
        including its already-complete members.  Those members are historical
        barrier evidence, not launch candidates.  Filtering only controller-
        authenticated COMPLETE rows preserves the canonical round boundary while
        preventing a capacity change from making completed work ineligible and
        wedging the remaining frontier.
        """

        if type(max_sessions) is not int or max_sessions < 1:
            raise AutopilotError("compiled frontier requires authenticated host capacity")
        compiled = select_round(
            self,
            status,
            max_sessions=max_sessions,
            plan_path=self.ap_root / "plan.json",
        )
        if compiled is None:
            return []
        rows = status.get("nodes")
        completed = (
            {
                str(row.get("node_id"))
                for row in rows
                if isinstance(row, Mapping) and row.get("state") == "COMPLETE"
            }
            if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes))
            else set()
        )
        return [node_id for node_id in compiled.nodes if node_id not in completed]

    def _build_dispatch_release_unlocked(
        self,
        *,
        actor: str,
        host_id: str,
        capacity: Mapping[str, Any],
        session_cap: int,
        issued_at: str,
        requested_nodes: Sequence[str] = (),
    ) -> Mapping[str, Any]:
        """Build a release candidate without mutating host or repository authority."""

        self._assert_execution_not_terminal_unlocked("dispatcher release")
        recovery_issues = self._recovery_issues()
        if recovery_issues:
            raise AutopilotError("; ".join(recovery_issues))
        if not actor.strip():
            raise AutopilotError("dispatcher actor is required")
        self._assert_no_execution_launch_reservations("dispatcher release")
        self._assert_no_publication_transaction("dispatcher release")
        if self.target_requires_reconciliation():
            raise AutopilotError("dispatcher release is forbidden until live target reconciliation completes")
        reconciliation_digest = self._reconciliation_digest()
        snapshot_digest = self._snapshot_digest()
        if reconciliation_digest is None or snapshot_digest is None:
            raise AutopilotError("dispatcher release requires current reconciliation and GitHub snapshot evidence")
        observation = self._snapshot_observation()
        observation_issues = self._snapshot_observation_dispatch_issues(
            snapshot_digest,
            expected_observation_id=(
                observation.get("observation_id")
                if isinstance(observation, Mapping)
                else None
            ),
            expected_observation_epoch=(
                observation.get("observation_epoch")
                if isinstance(observation, Mapping)
                else None
            ),
            expected_observation_record_id=(
                observation.get("record_id")
                if isinstance(observation, Mapping)
                else None
            ),
        )
        if observation_issues:
            raise AutopilotError(
                "dispatcher release requires completed shared snapshot authority: "
                + "; ".join(observation_issues)
            )
        canonical = self._canonical_dispatch_identity()
        target_watermark = self.repository_target_watermark()
        assert isinstance(observation, Mapping)
        if (
            observation.get("target_sha") != canonical["target_sha"]
            or observation.get("plan_fingerprint") != canonical["plan_fingerprint"]
            or target_watermark.get("target_sha") != canonical["target_sha"]
        ):
            raise AutopilotError(
                "dispatcher snapshot observation is stale relative to canonical authority"
            )
        previous_generation = self._dispatcher_generation()
        if previous_generation is None:
            raise AutopilotError(
                "dispatcher release requires shared snapshot/reconciliation initialization; "
                "install a fresh GitHub snapshot and reconcile first"
            )
        generation_issues = self._dispatcher_generation_issues(previous_generation)
        if generation_issues:
            raise AutopilotError("; ".join(generation_issues))
        if any(
            previous_generation.get(field) != canonical[field]
            for field in ("repository", "target_branch", "target_sha", "plan_fingerprint")
        ):
            raise AutopilotError(
                "dispatcher canonical identity differs from the newest shared evidence"
            )
        if (
            previous_generation.get("github_snapshot_digest") != snapshot_digest
            or previous_generation.get("reconciliation_digest") != reconciliation_digest
            or previous_generation.get("target_generation")
            != target_watermark["target_generation"]
            or previous_generation.get("target_watermark_record_id")
            != target_watermark["record_id"]
            or previous_generation.get("snapshot_observation_id")
            != observation["observation_id"]
            or previous_generation.get("snapshot_observation_epoch")
            != observation["observation_epoch"]
            or previous_generation.get("snapshot_observation_record_id")
            != observation["record_id"]
        ):
            raise AutopilotError(
                "this worktree's snapshot/reconciliation evidence is stale relative to "
                "the shared dispatcher watermark"
            )
        admission_epoch = int(previous_generation["admission_epoch"]) + 1
        supersedes_release_id = previous_generation.get("release_id")
        base_status = self._base_status()
        ready = base_status.get("ready", [])
        eligible = [str(item) for item in ready] if isinstance(ready, list) else []
        frontier = self._compiled_frontier(
            base_status, max_sessions=session_cap
        )
        requested = list(dict.fromkeys(str(item) for item in requested_nodes))
        if requested_nodes and requested != list(requested_nodes):
            raise AutopilotError("requested dispatcher frontier contains duplicates")
        if len(requested) > session_cap:
            raise AutopilotError(
                "requested dispatcher wave exceeds authenticated available host "
                f"capacity of {session_cap}"
            )
        if requested_nodes and requested != frontier[: len(requested)]:
            raise AutopilotError(
                "requested dispatcher wave is not an exact authenticated frontier prefix: "
                + (", ".join(frontier) or "<quiescent>")
            )
        unavailable = [node_id for node_id in frontier if node_id not in eligible]
        if unavailable:
            raise AutopilotError(
                "authenticated compiled frontier is not fully eligible: "
                + ", ".join(unavailable)
            )
        wave = requested if requested_nodes else frontier
        verdicts = self._candidate_verdicts(base_status, wave)
        directive, action = self._action_sentence(wave)
        record: dict[str, Any] = {
            "schema_version": 1, "kind": RELEASE_KIND, "actor": actor,
            "execution_namespace": self.execution_namespace,
            "execution_id": self.execution_id,
            "repository": canonical["repository"], "target_branch": canonical["target_branch"],
            "target_sha": canonical["target_sha"], "plan_fingerprint": canonical["plan_fingerprint"],
            "target_generation": target_watermark["target_generation"],
            "target_watermark_record_id": target_watermark["record_id"],
            "reconciliation_digest": reconciliation_digest, "github_snapshot_digest": snapshot_digest,
            "snapshot_observation_id": observation["observation_id"],
            "snapshot_observation_epoch": observation["observation_epoch"],
            "snapshot_observation_record_id": observation["record_id"],
            "host_id": host_id,
            "capacity_generation": capacity["capacity_generation"],
            "capacity_epoch": capacity["capacity_epoch"],
            "capacity_record_id": capacity["record_id"],
            "capacity_max_total_sessions": capacity["max_total_sessions"],
            "capacity_validation_slots": capacity["validation_slots"],
            "session_cap": session_cap,
            "admission_epoch": admission_epoch,
            "supersedes_release_id": supersedes_release_id,
            "released_wave": wave, "directive": directive, "action": action, "verdicts": verdicts,
            "issued_at": issued_at,
            "receipt_retirement_execution_digest": digest_json(self._execution()) if self._execution() is not None else None,
            "primary_host_reservations": [],
        }
        admission_material = dict(record)
        admission_material.pop("primary_host_reservations", None)
        record["release_admission_id"] = digest_json(
            {
                "kind": "hive-mind-release-admission-key-v1",
                "release": admission_material,
            }
        )
        return record

    def _primary_reservation_coordinates(
        self, draft: Mapping[str, Any]
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for node_id in draft.get("released_wave", []):
            node = self.node(str(node_id))
            identity = derive_launch_identity(
                repository=str(draft["repository"]),
                execution_id=self.execution_id,
                execution_namespace=self.execution_namespace,
                node_id=str(node_id),
                lifecycle="NODE_DELIVERY",
                authority_class="WRITE_AUTHORIZED",
                branch=str(node["branch"]),
                target_branch=str(draft["target_branch"]),
                target_sha=str(draft["target_sha"]),
                plan_fingerprint=str(draft["plan_fingerprint"]),
            )
            scopes = node.get("file_locks")
            if not isinstance(scopes, list) or not all(
                isinstance(item, str) and item.strip() for item in scopes
            ):
                raise AutopilotError(
                    f"dispatcher node {node_id} lacks exact host write scopes"
                )
            resource_key = str(identity["resource_key"])
            local_reservation_id = digest_json(
                {
                    "kind": "hive-mind-release-primary-permit-v1",
                    "execution_id": self.execution_id,
                    "admission_epoch": draft["admission_epoch"],
                    "target_sha": draft["target_sha"],
                    "target_generation": draft["target_generation"],
                    "target_watermark_record_id": draft[
                        "target_watermark_record_id"
                    ],
                    "plan_fingerprint": draft["plan_fingerprint"],
                    "snapshot_observation_record_id": draft[
                        "snapshot_observation_record_id"
                    ],
                    "host_id": draft["host_id"],
                    "capacity_generation": draft["capacity_generation"],
                    "node_id": node_id,
                    "resource_key": resource_key,
                }
            )
            result.append(
                {
                    "node_id": node_id,
                    "resource_key": resource_key,
                    "local_reservation_id": local_reservation_id,
                    "write_scopes": list(scopes),
                }
            )
        return result

    @staticmethod
    def _dispatcher_adapter_coordinates(
        execution_adapter_identity: Mapping[str, object],
        *,
        capacity: Mapping[str, object],
        repository: str,
        host_id: str,
        execution_namespace: str | None = None,
        execution_id: str | None = None,
    ) -> dict[str, object]:
        if not isinstance(execution_adapter_identity, Mapping):
            raise AutopilotError(
                "dispatcher requires an immutable execution adapter identity"
            )
        record = dict(execution_adapter_identity)
        material = dict(record)
        record_id = material.pop("record_id", None)
        expected_path = (
            "execution-adapter-bindings/"
            + str(record_id).removeprefix("sha256:")
            + ".json"
        )
        blob_digest = "sha256:" + sha256(
            (
                json.dumps(
                    record,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                    allow_nan=False,
                )
                + "\n"
            ).encode("utf-8")
        ).hexdigest()
        if (
            set(record)
            != {
                "schema_version",
                "kind",
                "execution_namespace",
                "execution_id",
                "repository",
                "host_id",
                "provider_generation",
                "provider_epoch",
                "provider_identity_digest",
                "adapter_identity_kind",
                "adapter_identity_record_id",
                "adapter_identity_blob_digest",
                "adapter_identity_source_path",
                "record_id",
            }
            or record.get("schema_version") != 1
            or record.get("kind") != "hive-mind-execution-adapter-identity-v1"
            or record_id != digest_json(material)
            or AUTHORITY_ID.fullmatch(str(record_id)) is None
            or record.get("repository") != repository
            or record.get("host_id") != host_id
            or (
                execution_namespace is not None
                and record.get("execution_namespace") != execution_namespace
            )
            or (
                execution_id is not None
                and record.get("execution_id") != execution_id
            )
            or record.get("provider_generation")
            != capacity.get("provider_generation")
            or record.get("provider_epoch") != capacity.get("provider_epoch")
            or AUTHORITY_ID.fullmatch(
                str(record.get("provider_identity_digest"))
            )
            is None
            or record.get("adapter_identity_kind")
            != "hive-mind-codex-app-server-identity-v1"
            or AUTHORITY_ID.fullmatch(
                str(record.get("adapter_identity_record_id"))
            )
            is None
            or record.get("adapter_identity_source_path")
            != "execution-adapter-identities/"
            + str(record.get("adapter_identity_record_id")).removeprefix(
                "sha256:"
            )
            + ".json"
            or AUTHORITY_ID.fullmatch(
                str(record.get("adapter_identity_blob_digest"))
            )
            is None
            or AUTHORITY_ID.fullmatch(blob_digest) is None
        ):
            raise AutopilotError(
                "dispatcher execution adapter identity differs from host authority"
            )
        return {
            "host_kernel_generation": capacity["host_kernel_generation"],
            "execution_adapter_identity_record_id": record_id,
            "execution_adapter_identity_path": expected_path,
            "execution_adapter_identity_blob_digest": blob_digest,
        }

    @staticmethod
    def _primary_host_reservation_id(
        draft: Mapping[str, Any],
        coordinate: Mapping[str, Any],
        capacity: Mapping[str, Any],
        execution_adapter_identity: Mapping[str, object],
        host_scheduler_grant_id: str | None = None,
    ) -> str:
        adapter_record_id = execution_adapter_identity.get("record_id")
        identity: dict[str, object] = {
                "kind": "hive-mind-host-reservation-key-v1",
                "repository": draft["repository"],
                "execution_id": draft["execution_id"],
                "host_id": draft["host_id"],
                "provider_generation": capacity["provider_generation"],
                "capacity_generation": draft["capacity_generation"],
                "local_reservation_id": coordinate["local_reservation_id"],
                "reservation_kind": "PRIMARY",
                "host_kernel_generation": capacity["host_kernel_generation"],
                "execution_adapter_identity_record_id": adapter_record_id,
        }
        if host_scheduler_grant_id is not None:
            identity["host_scheduler_grant_id"] = host_scheduler_grant_id
        return digest_json(identity)

    def _dispatcher_admission_intent_path(self, release_admission_id: str) -> Path:
        if AUTHORITY_ID.fullmatch(release_admission_id) is None:
            raise AutopilotError("dispatcher admission intent id is invalid")
        return self._secure_execution_path(
            Path("di")
            / f"{release_admission_id.removeprefix('sha256:')}.json"
        )

    def _dispatcher_pre_launch_abort_path(self, reservation_id: str) -> Path:
        if AUTHORITY_ID.fullmatch(reservation_id) is None:
            raise AutopilotError("dispatcher pre-launch abort reservation id is invalid")
        return self._secure_execution_path(
            Path("pa")
            / f"{reservation_id.removeprefix('sha256:')}.json"
        )

    def _validated_dispatcher_admission_intent(
        self, value: object, *, label: str
    ) -> dict[str, Any]:
        legacy_fields = {
            "schema_version",
            "kind",
            "execution_namespace",
            "execution_id",
            "repository",
            "release_admission_id",
            "release_id",
            "admission_epoch",
            "target_sha",
            "target_generation",
            "target_watermark_record_id",
            "plan_fingerprint",
            "snapshot_observation_record_id",
            "host_id",
            "provider_generation",
            "provider_epoch",
            "capacity_generation",
            "capacity_epoch",
            "reservations",
            "release",
            "actor",
            "issued_at",
            "record_id",
        }
        current_fields = legacy_fields | {
            "host_kernel_generation",
            "execution_adapter_identity_record_id",
            "execution_adapter_identity_path",
            "execution_adapter_identity_blob_digest",
        }
        scheduler_fields = current_fields
        if not isinstance(value, Mapping):
            raise AutopilotError(f"{label} has an invalid exact schema")
        intent = dict(value)
        schema_version = intent.get("schema_version")
        if (
            schema_version == 1
            and set(intent) != legacy_fields
            or schema_version == 2
            and set(intent) != current_fields
            or schema_version == 3
            and set(intent) != scheduler_fields
            or schema_version not in {1, 2, 3}
        ):
            raise AutopilotError(f"{label} has an invalid exact schema")
        material = dict(intent)
        record_id = material.pop("record_id", None)
        reservations = intent.get("reservations")
        release = intent.get("release")
        if (
            record_id != digest_json(material)
            or AUTHORITY_ID.fullmatch(str(record_id)) is None
            or intent.get("kind") != DISPATCH_ADMISSION_INTENT_KIND
            or intent.get("execution_namespace") != self.execution_namespace
            or intent.get("execution_id") != self.execution_id
            or any(
                AUTHORITY_ID.fullmatch(str(intent.get(field))) is None
                for field in (
                    "release_admission_id",
                    "release_id",
                    "target_watermark_record_id",
                    "plan_fingerprint",
                    "snapshot_observation_record_id",
                    "provider_generation",
                    "capacity_generation",
                )
            )
            or type(intent.get("admission_epoch")) is not int
            or int(intent["admission_epoch"]) < 1
            or type(intent.get("target_generation")) is not int
            or int(intent["target_generation"]) < 1
            or type(intent.get("provider_epoch")) is not int
            or int(intent["provider_epoch"]) < 1
            or type(intent.get("capacity_epoch")) is not int
            or int(intent["capacity_epoch"]) < 1
            or FULL_SHA.fullmatch(str(intent.get("target_sha"))) is None
            or not isinstance(intent.get("repository"), str)
            or not str(intent["repository"]).strip()
            or not isinstance(intent.get("host_id"), str)
            or not str(intent["host_id"]).strip()
            or not isinstance(intent.get("actor"), str)
            or not str(intent["actor"]).strip()
            or not isinstance(reservations, list)
            or not reservations
            or not isinstance(release, Mapping)
        ):
            raise AutopilotError(f"{label} authority binding is invalid")
        if schema_version in {2, 3}:
            adapter_record_id = intent.get(
                "execution_adapter_identity_record_id"
            )
            if (
                AUTHORITY_ID.fullmatch(
                    str(intent.get("host_kernel_generation"))
                )
                is None
                or AUTHORITY_ID.fullmatch(str(adapter_record_id)) is None
                or intent.get("execution_adapter_identity_path")
                != "execution-adapter-bindings/"
                + str(adapter_record_id).removeprefix("sha256:")
                + ".json"
                or AUTHORITY_ID.fullmatch(
                    str(intent.get("execution_adapter_identity_blob_digest"))
                )
                is None
            ):
                raise AutopilotError(
                    f"{label} execution adapter authority is invalid"
                )
        try:
            parse_time(intent.get("issued_at"))
        except Exception as error:
            raise AutopilotError(f"{label} issue time is malformed") from error
        seen: set[str] = set()
        for reservation in reservations:
            reservation_fields = {
                "node_id",
                "resource_key",
                "local_reservation_id",
                "reservation_id",
            }
            if schema_version == 3:
                reservation_fields.add("host_scheduler_grant_id")
            if (
                not isinstance(reservation, Mapping)
                or set(reservation) != reservation_fields
                or not isinstance(reservation.get("node_id"), str)
                or any(
                    AUTHORITY_ID.fullmatch(str(reservation.get(field))) is None
                    for field in (
                        "resource_key",
                        "local_reservation_id",
                        "reservation_id",
                        *(
                            ("host_scheduler_grant_id",)
                            if schema_version == 3
                            else ()
                        ),
                    )
                )
                or reservation.get("reservation_id") in seen
            ):
                raise AutopilotError(f"{label} reservation inventory is invalid")
            seen.add(str(reservation["reservation_id"]))
            expected_reservation_id = digest_json(
                {
                    "kind": "hive-mind-host-reservation-key-v1",
                    "repository": intent["repository"],
                    "execution_id": intent["execution_id"],
                    "host_id": intent["host_id"],
                    "provider_generation": intent["provider_generation"],
                    "capacity_generation": intent["capacity_generation"],
                    "local_reservation_id": reservation[
                        "local_reservation_id"
                    ],
                    "reservation_kind": "PRIMARY",
                    **(
                        {
                            "host_kernel_generation": intent[
                                "host_kernel_generation"
                            ],
                            "execution_adapter_identity_record_id": intent[
                                "execution_adapter_identity_record_id"
                            ],
                        }
                        if schema_version in {2, 3}
                        else {}
                    ),
                    **(
                        {
                            "host_scheduler_grant_id": reservation[
                                "host_scheduler_grant_id"
                            ]
                        }
                        if schema_version == 3
                        else {}
                    ),
                }
            )
            if reservation.get("reservation_id") != expected_reservation_id:
                raise AutopilotError(
                    f"{label} reservation digest is not canonical"
                )
        release_material = dict(release)
        embedded_release_id = release_material.pop("release_id", None)
        admission_material = dict(release_material)
        embedded_admission_id = admission_material.pop(
            "release_admission_id", None
        )
        embedded_reservations = admission_material.pop(
            "primary_host_reservations", None
        )
        expected_admission_id = digest_json(
            {
                "kind": "hive-mind-release-admission-key-v1",
                "release": admission_material,
            }
        )
        expected_release_reservations = [
            {
                "node_id": item["node_id"],
                "resource_key": item["resource_key"],
                "reservation_id": item["reservation_id"],
            }
            for item in reservations
        ]
        if (
            embedded_release_id != digest_json(release_material)
            or embedded_release_id != intent.get("release_id")
            or embedded_admission_id != expected_admission_id
            or embedded_admission_id != intent.get("release_admission_id")
            or embedded_reservations != expected_release_reservations
            or release.get("execution_namespace")
            != intent.get("execution_namespace")
            or release.get("execution_id") != intent.get("execution_id")
            or release.get("repository") != intent.get("repository")
            or release.get("admission_epoch") != intent.get("admission_epoch")
            or release.get("host_id") != intent.get("host_id")
            or release.get("capacity_generation")
            != intent.get("capacity_generation")
            or release.get("capacity_epoch") != intent.get("capacity_epoch")
        ):
            raise AutopilotError(f"{label} embedded release authority is invalid")
        return intent

    def _dispatcher_admission_intent(
        self,
        draft: Mapping[str, Any],
        coordinates: Sequence[Mapping[str, Any]],
        capacity: Mapping[str, Any],
        execution_adapter_identity: Mapping[str, object],
        scheduler_grants: Mapping[str, Mapping[str, object]],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        adapter_coordinates = self._dispatcher_adapter_coordinates(
            execution_adapter_identity,
            capacity=capacity,
            repository=str(draft["repository"]),
            host_id=str(draft["host_id"]),
            execution_namespace=self.execution_namespace,
            execution_id=self.execution_id,
        )
        reservations = [
            {
                "node_id": coordinate["node_id"],
                "resource_key": coordinate["resource_key"],
                "local_reservation_id": coordinate["local_reservation_id"],
                "host_scheduler_grant_id": scheduler_grants[
                    str(coordinate["local_reservation_id"])
                ]["grant_id"],
                "reservation_id": self._primary_host_reservation_id(
                    draft,
                    coordinate,
                    capacity,
                    execution_adapter_identity,
                    str(
                        scheduler_grants[
                            str(coordinate["local_reservation_id"])
                        ]["grant_id"]
                    ),
                ),
            }
            for coordinate in coordinates
        ]
        release = dict(draft)
        release["primary_host_reservations"] = [
            {
                "node_id": item["node_id"],
                "resource_key": item["resource_key"],
                "reservation_id": item["reservation_id"],
            }
            for item in reservations
        ]
        release["release_id"] = digest_json(release)
        material: dict[str, Any] = {
            "schema_version": 3,
            "kind": DISPATCH_ADMISSION_INTENT_KIND,
            "execution_namespace": self.execution_namespace,
            "execution_id": self.execution_id,
            "repository": draft["repository"],
            "release_admission_id": draft["release_admission_id"],
            "release_id": release["release_id"],
            "admission_epoch": draft["admission_epoch"],
            "target_sha": draft["target_sha"],
            "target_generation": draft["target_generation"],
            "target_watermark_record_id": draft["target_watermark_record_id"],
            "plan_fingerprint": draft["plan_fingerprint"],
            "snapshot_observation_record_id": draft[
                "snapshot_observation_record_id"
            ],
            "host_id": draft["host_id"],
            "provider_generation": capacity["provider_generation"],
            "provider_epoch": capacity["provider_epoch"],
            "capacity_generation": draft["capacity_generation"],
            "capacity_epoch": draft["capacity_epoch"],
            **adapter_coordinates,
            "reservations": reservations,
            "release": release,
            "actor": draft["actor"],
            "issued_at": draft["issued_at"],
        }
        intent = {**material, "record_id": digest_json(material)}
        return (
            self._validated_dispatcher_admission_intent(
                intent, label="new dispatcher admission intent"
            ),
            release,
        )

    def _write_dispatcher_admission_intent(
        self, intent: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        validated = self._validated_dispatcher_admission_intent(
            intent, label="dispatcher admission intent"
        )
        self._write_immutable_json(
            self._dispatcher_admission_intent_path(
                str(validated["release_admission_id"])
            ),
            validated,
        )
        return validated

    def _dispatcher_intent_for_reservation(
        self, reservation: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        directory = self._secure_execution_path("di")
        if not directory.is_dir() or self._is_link_like(directory):
            raise AutopilotError(
                "orphan dispatcher permit lacks a durable admission intent"
            )
        matches: list[Mapping[str, Any]] = []
        for path in sorted(directory.iterdir(), key=lambda candidate: candidate.name):
            if self._is_link_like(path) or not path.is_file() or path.suffix != ".json":
                raise AutopilotError("dispatcher admission intent inventory is unsafe")
            intent = self._validated_dispatcher_admission_intent(
                self._strict_json_file(path, label="dispatcher admission intent"),
                label="dispatcher admission intent",
            )
            if any(
                item.get("reservation_id") == reservation.get("reservation_id")
                for item in intent["reservations"]
            ):
                matches.append(intent)
        if len(matches) != 1:
            raise AutopilotError(
                "orphan dispatcher permit has ambiguous admission intent authority"
            )
        return matches[0]

    def _abort_global_primary_reservation(
        self,
        reservation: Mapping[str, Any],
        intent: Mapping[str, Any],
        *,
        actor: str,
        reason: str,
    ) -> Mapping[str, Any]:
        validated_intent = self._validated_dispatcher_admission_intent(
            intent, label="dispatcher abort admission intent"
        )
        matching = [
            item
            for item in validated_intent["reservations"]
            if item.get("reservation_id") == reservation.get("reservation_id")
        ]
        if (
            len(matching) != 1
            or reservation.get("reservation_kind") != "PRIMARY"
            or reservation.get("execution_id") != self.execution_id
            or reservation.get("local_reservation_id")
            != matching[0].get("local_reservation_id")
            or reservation.get("resource_key") != matching[0].get("resource_key")
            or reservation.get("host_id") != validated_intent.get("host_id")
            or reservation.get("provider_generation")
            != validated_intent.get("provider_generation")
            or reservation.get("capacity_generation")
            != validated_intent.get("capacity_generation")
            or (
                validated_intent.get("schema_version") == 2
                and any(
                    reservation.get(field) != validated_intent.get(field)
                    for field in (
                        "host_kernel_generation",
                        "execution_adapter_identity_record_id",
                        "execution_adapter_identity_path",
                        "execution_adapter_identity_blob_digest",
                    )
                )
            )
        ):
            raise AutopilotError(
                "dispatcher pre-launch abort differs from its exact admission intent"
            )
        active_write = self._active_execution_write_reservations()
        active_host = self._active_execution_host_reservations()
        host_effects = execution_host_effect_obligations(self.execution_dir)
        if active_write or active_host or host_effects:
            raise AutopilotError(
                "dispatcher permit cannot be aborted after local launch/effect authority exists"
            )
        empty_activity = {
            "active_write_launch_reservation_ids": [],
            "active_host_reservation_ids": [],
            "host_effect_obligation_ids": [],
        }
        material: dict[str, Any] = {
            "schema_version": 1,
            "kind": DISPATCH_PRE_LAUNCH_ABORT_KIND,
            "state": "NEVER_LAUNCHED",
            "execution_namespace": self.execution_namespace,
            "execution_id": self.execution_id,
            "repository": validated_intent["repository"],
            "release_id": validated_intent["release_id"],
            "release_admission_id": validated_intent["release_admission_id"],
            "admission_epoch": validated_intent["admission_epoch"],
            "intent_record_id": validated_intent["record_id"],
            "reservation_id": reservation["reservation_id"],
            "local_reservation_id": reservation["local_reservation_id"],
            "resource_key": reservation["resource_key"],
            "node_id": matching[0]["node_id"],
            "host_id": reservation["host_id"],
            "provider_generation": reservation["provider_generation"],
            "capacity_generation": reservation["capacity_generation"],
            **empty_activity,
            "empty_activity_digest": digest_json(empty_activity),
            "reason": "DISPATCH_ADMISSION_ABORTED_BEFORE_LAUNCH",
            "actor": validated_intent["actor"],
            "recorded_at": validated_intent["issued_at"],
        }
        abort = {**material, "record_id": digest_json(material)}
        path = self._dispatcher_pre_launch_abort_path(
            str(reservation["reservation_id"])
        )
        self._write_immutable_json(path, abort)
        release_global_host_session(
            self.host_runtime_dir,
            str(reservation["reservation_id"]),
            execution_id=self.execution_id,
            local_reservation_id=str(reservation["local_reservation_id"]),
            capacity_generation=str(reservation["capacity_generation"]),
            actor=actor,
            reason=reason,
            released_at=format_time(self.clock()),
            pre_launch_abort_receipt=abort,
            repo_root=self.repo_root,
            coordination_dir=self.coordination_dir,
            execution_dir=self.execution_dir,
            execution_namespace=self.execution_namespace,
        )
        return abort

    def _publish_dispatch_generation_unlocked(
        self, record: Mapping[str, Any]
    ) -> None:
        generation: dict[str, Any] = {
            "schema_version": 1,
            "kind": DISPATCH_GENERATION_KIND,
            "status": "ACTIVE",
            "execution_namespace": self.execution_namespace,
            "execution_id": self.execution_id,
            "admission_epoch": record["admission_epoch"],
            "release_id": record["release_id"],
            "repository": record["repository"],
            "target_branch": record["target_branch"],
            "target_sha": record["target_sha"],
            "target_generation": record["target_generation"],
            "target_watermark_record_id": record[
                "target_watermark_record_id"
            ],
            "plan_fingerprint": record["plan_fingerprint"],
            "github_snapshot_digest": record["github_snapshot_digest"],
            "reconciliation_digest": record["reconciliation_digest"],
            "snapshot_observation_id": record["snapshot_observation_id"],
            "snapshot_observation_epoch": record["snapshot_observation_epoch"],
            "snapshot_observation_record_id": record[
                "snapshot_observation_record_id"
            ],
            "host_id": record["host_id"],
            "capacity_generation": record["capacity_generation"],
            "capacity_epoch": record["capacity_epoch"],
            "capacity_record_id": record["capacity_record_id"],
            "session_cap": record["session_cap"],
            "recorded_at": format_time(self.clock()),
        }
        generation["generation_id"] = digest_json(generation)
        self._atomic_write_authority_json(self.dispatcher_generation_path, generation)

    @contextmanager
    def dispatcher_launch_authority_guard(
        self,
        node_id: str,
        *,
        host_id: str | None = None,
        release_id: str | None = None,
    ):
        """Hold and revalidate shared release authority for a hosted effect."""

        if host_id is None:
            candidates = {
                str(item.get("capacity_host_id"))
                for item in self._active_execution_write_reservations()
                if item.get("node_id") == node_id
                and isinstance(item.get("capacity_host_id"), str)
                and str(item.get("capacity_host_id")).strip()
            }
            if len(candidates) != 1:
                raise ClaimError(
                    "host effect lacks one exact binding-derived capacity host id"
                )
            host_id = next(iter(candidates))
        with self.host_lock(timeout_seconds=120.0):
            with self.arbiter_lock(timeout_seconds=120.0):
                with self.execution_lock(
                    "dispatcher-admission.lock", timeout_seconds=120.0
                ):
                    self._assert_no_publication_transaction(
                        "host launch admission"
                    )
                    release = self.assert_start_now(node_id)
                    bound = [
                        item
                        for item in self._active_execution_write_reservations()
                        if item.get("node_id") == node_id
                    ]
                    if bound and any(
                        item.get("capacity_host_id") != host_id
                        or item.get("dispatcher_release_id")
                        != release.get("release_id")
                        or item.get("dispatcher_admission_epoch")
                        != release.get("admission_epoch")
                        for item in bound
                    ):
                        raise ClaimError(
                            "host effect binding differs from dispatcher/capacity authority"
                        )
                    if release.get("host_id") != host_id:
                        raise ClaimError("host effect capacity host identity mismatch")
                    if release_id is not None and release.get("release_id") != release_id:
                        raise ClaimError("host effect dispatcher release fence mismatch")
                    capacity = reconcile_pending_host_capacity_renewal(
                        self.host_runtime_dir,
                        host_id=host_id,
                        now=self.clock(),
                    )
                    self._release_capacity_issuance_unlocked(release)
                    if any(
                        release.get(field) != capacity.get(capacity_field)
                        for field, capacity_field in (
                            ("capacity_generation", "capacity_generation"),
                            ("capacity_epoch", "capacity_epoch"),
                            (
                                "capacity_max_total_sessions",
                                "max_total_sessions",
                            ),
                            ("capacity_validation_slots", "validation_slots"),
                        )
                    ):
                        raise ClaimError("host effect capacity generation is stale")
                    permit = next(
                        (
                            item
                            for item in release.get(
                                "primary_host_reservations", []
                            )
                            if isinstance(item, Mapping)
                            and item.get("node_id") == node_id
                        ),
                        None,
                    )
                    active_ids = {
                        str(item.get("reservation_id"))
                        for item in active_global_host_reservations(
                            self.host_runtime_dir
                        )
                    }
                    if (
                        not isinstance(permit, Mapping)
                        or permit.get("reservation_id") not in active_ids
                    ):
                        raise ClaimError(
                            "host effect primary capacity reservation is not active"
                        )
                    yield release

    def claim(
        self,
        node_id: str,
        owner: str,
        *,
        claim_authority_class: str,
        launch_instruction_id: str | None = None,
        resource_key: str | None = None,
        authority_epoch: int | None = None,
        _internal_authority: object | None = None,
        lease_minutes: int = 90,
        publish_remote: bool = False,
        remote: str = "origin",
    ) -> Mapping[str, Any]:
        """Atomically revalidate the shared release before claim admission."""

        if claim_authority_class == "HOSTED_LAUNCH":
            # The core hosted guard now owns the single host -> arbiter ->
            # dispatcher -> binding -> claim order and revalidates this subclass's
            # release/capacity guard before the claim effect.
            return super().claim(
                node_id,
                owner,
                claim_authority_class=claim_authority_class,
                launch_instruction_id=launch_instruction_id,
                resource_key=resource_key,
                authority_epoch=authority_epoch,
                _internal_authority=_internal_authority,
                lease_minutes=lease_minutes,
                publish_remote=publish_remote,
                remote=remote,
            )
        with self.execution_lock("dispatcher-admission.lock", timeout_seconds=120.0):
            return super().claim(
                node_id,
                owner,
                claim_authority_class=claim_authority_class,
                launch_instruction_id=launch_instruction_id,
                resource_key=resource_key,
                authority_epoch=authority_epoch,
                _internal_authority=_internal_authority,
                lease_minutes=lease_minutes,
                publish_remote=publish_remote,
                remote=remote,
            )

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
    root.add_argument(
        "--state-dir",
        default=None,
        help=(
            "Shared execution-authority directory. Defaults to "
            "HIVE_MIND_RUNTIME_STATE_DIR or the primary Git worktree's "
            ".autopilot/state; worktree-local evidence remains local."
        ),
    )
    root.add_argument(
        "--execution-namespace",
        default="default",
        help="Immutable execution namespace selector (default: default)",
    )
    root.add_argument(
        "--host-runtime-dir",
        default=None,
        help=(
            "Explicit machine-user host runtime override; it must match the "
            "already sealed host-runtime locator"
        ),
    )
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
    dispatch.add_argument("--host-id", required=True)
    dispatch.add_argument(
        "--host-adapter",
        choices=("app-server", "attended"),
        default="app-server",
    )
    dispatch.add_argument("--wait-seconds", type=int, default=60)
    dispatch.add_argument("--node", action="append", default=[])
    dispatch.add_argument(
        "--plan",
        help="Equivalent plan assertion; canonical target plan remains authoritative",
    )
    dispatch.add_argument("--json", action="store_true", dest="json_output")

    def add_claim_authority_arguments(command: argparse.ArgumentParser) -> None:
        command.add_argument("--launch-instruction-id", required=True)
        command.add_argument("--resource-key", required=True)
        command.add_argument("--authority-epoch", required=True, type=int)

    claim = commands.add_parser("claim")
    claim.add_argument("node_id")
    claim.add_argument("--owner", required=True)
    add_claim_authority_arguments(claim)
    claim.add_argument("--lease-minutes", type=int, default=90)
    claim.add_argument("--publish-remote", action="store_true")
    claim.add_argument("--remote", default="origin")

    heartbeat = commands.add_parser("heartbeat")
    heartbeat.add_argument("node_id")
    heartbeat.add_argument("--owner", required=True)
    heartbeat.add_argument("--claim-id", required=True)
    add_claim_authority_arguments(heartbeat)
    heartbeat.add_argument("--lease-minutes", type=int, default=90)

    release = commands.add_parser("release")
    release.add_argument("node_id")
    release.add_argument("--owner", required=True)
    release.add_argument("--claim-id", required=True)
    add_claim_authority_arguments(release)
    release.add_argument("--reason", required=True)

    reap = commands.add_parser("reap-stale-remote-claim")
    reap.add_argument("node_id")
    reap.add_argument("--owner", required=True)
    reap.add_argument("--reason", required=True)

    complete = commands.add_parser("complete")
    complete.add_argument("node_id")
    complete.add_argument("--owner", required=True)
    complete.add_argument("--claim-id", required=True)
    add_claim_authority_arguments(complete)
    complete.add_argument("--receipt", required=True)

    fail = commands.add_parser("fail")
    fail.add_argument("node_id")
    fail.add_argument("--owner", required=True)
    fail.add_argument("--claim-id", required=True)
    add_claim_authority_arguments(fail)
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

    snapshot_begin = commands.add_parser("snapshot-observation-begin")
    snapshot_begin.add_argument("--actor", required=True)

    snapshot = commands.add_parser("install-github-snapshot")
    snapshot.add_argument(
        "file",
        nargs="?",
        help="Strict candidate JSON; omit only to resume immutable INSTALLING evidence",
    )
    snapshot.add_argument("--observation-id", required=True)

    render = commands.add_parser("render-prompt")
    render.add_argument("node_id")
    render.add_argument("--host-id", required=True)

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
    validation_acquire.add_argument("--claim-id", required=True)
    add_claim_authority_arguments(validation_acquire)
    validation_acquire.add_argument("--lease-minutes", type=int, default=10)

    validation_renew = commands.add_parser("validation-lease-renew")
    validation_renew.add_argument("node_id")
    validation_renew.add_argument("--owner", required=True)
    validation_renew.add_argument("--claim-id", required=True)
    validation_renew.add_argument("--lease-id", required=True)
    add_claim_authority_arguments(validation_renew)
    validation_renew.add_argument("--lease-minutes", type=int, default=10)

    validation_release = commands.add_parser("validation-lease-release")
    validation_release.add_argument("node_id")
    validation_release.add_argument("--owner", required=True)
    validation_release.add_argument("--claim-id", required=True)
    validation_release.add_argument("--lease-id", required=True)
    add_claim_authority_arguments(validation_release)

    retirement = commands.add_parser("retire-receipt-branch")
    retirement.add_argument("retirement_id")
    retirement.add_argument("--actor", required=True)

    builder_retirement = commands.add_parser("retire-builder-330-branch")
    builder_retirement.add_argument("--actor", required=True)

    orchestrate = commands.add_parser("orchestrate")
    orchestrate.add_argument("--request", default="")
    orchestrate.add_argument("--actor", default="autopilot:orchestrator")
    orchestrate.add_argument("--host-id", required=True)
    orchestrate.add_argument(
        "--host-adapter",
        choices=("app-server", "attended"),
        default="app-server",
    )
    orchestrate.add_argument("--wait-seconds", type=int, default=60)
    orchestrate.add_argument(
        "--apply",
        action="store_true",
        help="Publish a safe release when inferred intent and live state allow it",
    )
    orchestrate.add_argument("--json", action="store_true", dest="json_output")

    wave = commands.add_parser("execute-wave")
    wave.add_argument("--request", default="execute the dag")
    wave.add_argument("--actor", default="autopilot:orchestrator")
    wave.add_argument("--host-id", required=True)
    wave.add_argument(
        "--host-adapter",
        choices=("app-server", "attended"),
        default="app-server",
    )
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
    wave.add_argument(
        "--no-heal",
        action="store_true",
        help="Do not repair a withheld wave; report the wedge and exit",
    )

    drive = commands.add_parser("run-round")
    drive.add_argument("--actor", default="autopilot:round-driver")
    drive.add_argument(
        "--release-id",
        required=True,
        help="Exact current shared dispatcher release fence",
    )
    drive.add_argument(
        "--no-push",
        action="store_true",
        help="Integrate locally without advancing the remote singleton target",
    )
    run = commands.add_parser("run")
    run.add_argument("--request", default="execute the canonical dag to quiescence")
    run.add_argument("--actor", default="autopilot:supervisor")
    run.add_argument("--host-id", required=True)
    run.add_argument(
        "--host-adapter",
        choices=("app-server", "attended"),
        default="app-server",
    )
    run.add_argument("--wait-seconds", type=int, default=60)
    run.add_argument("--observation-fingerprint")
    run.add_argument("--resume-token")

    run_recovery = commands.add_parser("run-recover-torn-tail")
    run_recovery.add_argument("--actor", required=True)
    run_recovery.add_argument("--reason", required=True)

    run_reconcile = commands.add_parser("run-reconcile-unknown")
    run_reconcile.add_argument("--host-id", required=True)
    run_reconcile.add_argument(
        "--host-adapter",
        choices=("app-server", "attended"),
        default="app-server",
    )
    run_reconcile.add_argument("--wait-seconds", type=int, default=60)
    run_reconcile.add_argument("--attempt-id", required=True)
    run_reconcile.add_argument("--actor", required=True)

    heal = commands.add_parser("heal")
    heal.add_argument("--actor", default="autopilot:healer")
    heal.add_argument("--host-id", required=True)
    heal.add_argument(
        "--host-adapter",
        choices=("app-server", "attended"),
        default="app-server",
    )
    heal.add_argument("--wait-seconds", type=int, default=60)
    heal.add_argument("--node", action="append", default=[])
    heal.add_argument(
        "--dry-run",
        action="store_true",
        help="Produce the same diagnosis and report with every action withheld",
    )

    lift = commands.add_parser("lift-retry-quarantine")
    lift.add_argument("node_id")
    lift.add_argument("--actor", required=True)

    retire = commands.add_parser("escalation-resolve")
    retire.add_argument("node_id")
    retire.add_argument("--actor", required=True)

    lessons = commands.add_parser("lessons")
    lessons.add_argument("--json", action="store_true", dest="json_output")
    lessons.add_argument(
        "--commit",
        action="store_true",
        help="Check newly recorded lessons into the current branch",
    )
    lessons.add_argument(
        "--push",
        action="store_true",
        help="Publish committed lessons so other sessions and repositories get them",
    )
    lessons.add_argument("--actor", default="autopilot:learner")

    intent = commands.add_parser("infer-intent")
    intent.add_argument("request", nargs="?", default="")
    intent.add_argument("--json", action="store_true", dest="json_output")

    commands.add_parser("simple-prompt")

    prepare = commands.add_parser("prepare-launch")
    prepare.add_argument("instruction_id")
    prepare.add_argument("--host", required=True)
    prepare.add_argument("--host-id", required=True)
    prepare.add_argument("--attempt", type=int, default=1)
    prepare.add_argument("--retry-of")
    prepare.add_argument("--repository", required=True)
    prepare.add_argument("--node-id", required=True)
    prepare.add_argument("--lifecycle", required=True)
    prepare.add_argument("--branch", required=True)
    prepare.add_argument("--resource-key", required=True)
    prepare.add_argument("--target-sha", required=True)
    prepare.add_argument("--plan-fingerprint", required=True)
    prepare.add_argument("--target-branch", required=True)
    prepare.add_argument(
        "--authority-class",
        required=True,
        choices=("PREPARATION_ONLY", "WRITE_AUTHORIZED"),
    )

    bind = commands.add_parser("bind-launch")
    bind.add_argument("instruction_id")
    bind.add_argument("--host", required=True)
    bind.add_argument("--task-id", required=True)
    bind.add_argument("--host-id", required=True)
    bind.add_argument("--cursor")
    bind.add_argument("--capability", required=True)
    bind.add_argument("--resource-key", required=True)
    bind.add_argument("--authority-epoch", required=True, type=int)

    commands.add_parser("launch-bindings")

    authority = commands.add_parser("check-launch-authority")
    authority.add_argument("instruction_id")
    authority.add_argument("--resource-key", required=True)
    authority.add_argument("--authority-epoch", required=True, type=int)

    fence = commands.add_parser("fence-launch")
    fence.add_argument("instruction_id")
    fence.add_argument("--actor", required=True)
    fence.add_argument("--reason", required=True)

    runtime_migrate = commands.add_parser("runtime-authority-migrate")
    runtime_migrate.add_argument("--actor", required=True)
    runtime_migrate.add_argument(
        "--mode",
        choices=("dry-run", "apply", "verify", "rollback-before-ready"),
        default="apply",
    )
    runtime_migrate.add_argument(
        "--reason",
        help="Required for rollback-before-ready; recorded in the abort receipt",
    )

    execution_init = commands.add_parser("execution-init")
    execution_init.add_argument("--namespace", required=True)
    execution_init.add_argument("--actor", required=True)

    execution_kernel_upgrade = commands.add_parser("execution-kernel-upgrade")
    execution_kernel_upgrade.add_argument("--execution-id", required=True)
    execution_kernel_upgrade.add_argument(
        "--expected-identity-record-id", required=True
    )
    execution_kernel_upgrade.add_argument("--actor", required=True)
    execution_kernel_upgrade.add_argument("--reason", required=True)

    host_init = commands.add_parser("host-runtime-init")
    host_init.add_argument("--actor", required=True)

    host_upgrade = commands.add_parser("host-runtime-upgrade")
    host_upgrade.add_argument("--actor", required=True)
    host_upgrade.add_argument("--reason", required=True)
    host_upgrade.add_argument("--expected-host-kernel-generation")

    host_tail_recovery = commands.add_parser("host-runtime-recover-torn-tail")
    host_tail_recovery.add_argument(
        "--ledger-kind",
        required=True,
        choices=(
            "repository-registry",
            "provider-history",
            "capacity-history",
            "reservation-history",
            "scheduler-history",
            "host-kernel-history",
        ),
    )
    host_tail_recovery.add_argument("--host-id")
    host_tail_recovery.add_argument("--actor", required=True)
    host_tail_recovery.add_argument("--reason", required=True)

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


def _instantiate_app_server_adapter(
    plane: ControlPlane,
    *,
    host_id: str,
    wait_seconds: int,
) -> tuple[object, str, Mapping[str, object], Mapping[str, object]] | None:
    """Load one exact execution-bound provider without capacity/reaper effects."""

    adapter_path = Path(__file__).resolve().with_name("app_server_host.py")
    if not adapter_path.is_file():
        return None
    if plane._is_link_like(adapter_path) or adapter_path.resolve().parent != Path(
        __file__
    ).resolve().parent:
        raise AutopilotError("App Server adapter path is outside the trusted checkout")
    adapter_bytes = adapter_path.read_bytes()
    module_digest = "sha256:" + sha256(adapter_bytes).hexdigest()
    module_name = (
        "_hive_mind_app_server_host_"
        + module_digest.removeprefix("sha256:")
    )
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    if spec is None or spec.loader is None:
        raise AutopilotError("App Server adapter cannot be loaded from its sealed path")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    if (
        getattr(module, "APP_SERVER_HOST_ADAPTER_KIND", None)
        != "hive-mind-codex-app-server-host-v1"
        or getattr(module, "APP_SERVER_HOST_ADAPTER_VERSION", None) != 1
    ):
        raise AutopilotError("App Server adapter contract version is not authorized")
    factory = getattr(module, "create_app_server_host", None)
    if not callable(factory):
        return None
    adapter = factory(
        plane=plane,
        host_id=host_id,
        execution_namespace=plane.execution_namespace,
        execution_id=plane.execution_id,
        execution_dir=plane.execution_dir,
        host_runtime_dir=plane.host_runtime_dir,
        wait_seconds=wait_seconds,
        adapter_module_digest=module_digest,
    )
    if (
        getattr(adapter, "host_id", None) != host_id
        or getattr(adapter, "adapter_module_digest", None) != module_digest
    ):
        raise AutopilotError(
            "App Server adapter host identity differs from the dispatched host"
        )
    provider_identity = _app_server_provider_identity(
        plane,
        adapter,
        host_id=host_id,
        module_digest=module_digest,
    )
    if getattr(adapter, "provider_identity_digest", None) != provider_identity.get(
        "provider_identity_digest"
    ):
        raise AutopilotError(
            "App Server adapter provider digest differs from sealed identity"
        )
    lifecycle = _app_server_lifecycle_authority(
        plane,
        adapter,
        host_id=host_id,
        provider_identity=provider_identity,
    )
    return adapter, module_digest, provider_identity, lifecycle


def _load_host_adapter(
    plane: ControlPlane,
    *,
    adapter_name: str,
    host_id: str,
    wait_seconds: int,
) -> tuple[
    HostCapability,
    object | None,
    str,
    Mapping[str, object] | None,
]:
    """Resolve only an explicitly selected, identity-bound host capability."""

    if adapter_name == "attended":
        return (
            HostCapability.ATTENDED_CARD_ONLY,
            None,
            "the attended card adapter cannot authenticate autonomous host lifecycle",
            None,
        )
    if adapter_name != "app-server":
        raise AutopilotError(f"unknown host adapter: {adapter_name}")
    canonical_host_id = _canonical_app_server_host_id(plane)
    if host_id != canonical_host_id:
        raise AutopilotError(
            "--host-id is an assertion of the sealed machine-user App Server "
            f"provider and must equal {canonical_host_id}"
        )
    loaded = _instantiate_app_server_adapter(
        plane, host_id=host_id, wait_seconds=wait_seconds
    )
    if loaded is None:
        return (
            HostCapability.NO_LAUNCH,
            None,
            "the authenticated Codex App Server adapter is not installed",
            None,
        )
    adapter, module_digest, provider_identity, lifecycle = loaded
    try:
        _recover_expired_app_server_reservations(
            plane,
            adapter,
            host_id=host_id,
        )
        capacity = _ensure_app_server_capacity(
            plane,
            adapter,
            host_id=host_id,
            module_digest=module_digest,
            provider_identity=provider_identity,
            lifecycle=lifecycle,
        )
        with plane.host_lock(timeout_seconds=120.0):
            execution_adapter_identity = install_execution_adapter_identity(
                plane.host_runtime_dir,
                repo_root=plane.repo_root,
                execution_dir=plane.execution_dir,
                execution_namespace=plane.execution_namespace,
                execution_id=plane.execution_id,
                host_id=host_id,
                adapter_identity_path=(
                    plane.execution_dir
                    / "host"
                    / "codex-app-server-v1"
                    / "identity.json"
                ),
                adapter_identity=provider_identity,
            )
        capacity_provider = getattr(adapter, "host_capacity_authority", None)
        if not callable(capacity_provider) or capacity_provider(
            repo_root=plane.repo_root
        ) != capacity:
            raise AutopilotError(
                "App Server adapter does not expose the installed capacity authority"
            )
    except BaseException:
        close = getattr(adapter, "close", None)
        if callable(close):
            close()
        raise
    if lifecycle.get("autonomous_launch") is not True:
        return (
            HostCapability.AUTHENTICATED_OBSERVER,
            adapter,
            "Codex App Server lifecycle is authenticated, but its installed "
            "thread/start protocol has no crash-exact idempotency authority; "
            "autonomous launch is withheld",
            execution_adapter_identity,
        )
    return (
        HostCapability.AUTHENTICATED_LIFECYCLE,
        adapter,
        "authenticated Codex App Server lifecycle adapter",
        execution_adapter_identity,
    )


def _supervisor_wait_condition(
    plane: ControlPlane,
    *,
    frontier_id: str,
    release_id: str,
    evidence: Mapping[str, object],
) -> WaitCondition:
    # The caller's detail is deliberately not a wake authority: a host result or
    # exception string cannot be replay-authenticated.  The fingerprint is always
    # recomputed from the controller's exact durable inventories and, for an
    # indeterminate publication, a fresh full remote-ref observation.
    if not isinstance(evidence, Mapping):
        raise AutopilotError("supervisor wait detail is malformed")
    observation = _supervisor_wait_observation_fingerprint(
        plane,
        frontier_id=frontier_id,
        asserted_release_id=release_id,
    )
    return WaitCondition(
        observation_fingerprint=observation,
        resume_token=digest_json(
            {
                "kind": "hive-mind-supervisor-wait-resume-v1",
                "execution_id": plane.execution_id,
                "frontier_id": frontier_id,
                "observation_fingerprint": observation,
            }
        ),
    )


def _authenticate_supervisor_execution(
    plane: ControlPlane,
    directory: Path,
    execution_id: str,
    execution_namespace: str,
    plan_fingerprint: str,
) -> Path:
    """Bind supervisor journal authority to the exact execution plan.

    The controller's lower-level directory authenticator proves the repository,
    namespace, execution id, transport, and kernel bundle.  The supervisor also
    makes the plan fingerprint part of every journal record, so authenticate that
    fourth coordinate here before it can read or mutate the journal.
    """

    if (
        plan_fingerprint != plane.expected_plan_fingerprint
        or plan_fingerprint != plane.execution_identity.get("plan_fingerprint")
    ):
        raise AutopilotError(
            "supervisor plan fingerprint differs from execution authority"
        )
    return require_execution_authority_dir(
        plane.repo_root,
        directory,
        execution_id=execution_id,
        execution_namespace=execution_namespace,
    )


def _supervisor_wait_observation_fingerprint(
    plane: ControlPlane,
    *,
    frontier_id: str,
    asserted_release_id: str | None = None,
) -> str:
    """Authenticate one stable wake observation without admitting any work."""

    publication_before = plane._current_publication_resource()
    transaction_before = (
        publication_before[1] if publication_before is not None else None
    )
    remote_publication: Mapping[str, object] | None = None
    if (
        isinstance(transaction_before, Mapping)
        and transaction_before.get("execution_id") == plane.execution_id
        and transaction_before.get("status") == "PUBLISH_UNKNOWN"
    ):
        try:
            receipt_heads = list(transaction_before["receipt_heads"])
            remote_target, remote_heads = plane._observe_publication_remote(
                receipt_heads
            )
            remote_transaction = plane._remote_ref_sha(
                str(transaction_before["transaction_ref"])
            )
            remote_publication = {
                "available": True,
                "target_sha": remote_target,
                "receipt_heads": dict(remote_heads),
                "transaction_sha": remote_transaction,
            }
        except Exception as error:
            remote_publication = {
                "available": False,
                "error_type": type(error).__name__,
                "error_digest": digest_json(
                    {
                        "kind": "hive-mind-supervisor-wait-remote-error-v1",
                        "detail": str(error),
                    }
                ),
            }

    with plane._host_arbiter_execution_guard():
        scheduler_observation = host_scheduler_observation(
            plane.host_runtime_dir,
            host_id=_canonical_app_server_host_id(plane),
            execution_id=plane.execution_id,
        )
        publication_after = plane._current_publication_resource()
        transaction_after = (
            publication_after[1] if publication_after is not None else None
        )
        if (
            isinstance(transaction_before, Mapping)
            != isinstance(transaction_after, Mapping)
            or (
                isinstance(transaction_before, Mapping)
                and isinstance(transaction_after, Mapping)
                and transaction_before.get("record_id")
                != transaction_after.get("record_id")
            )
        ):
            raise AutopilotError(
                "supervisor wait authority changed during remote observation"
            )
        status = plane._base_status()
        release = plane.current_release()
        release_issues = plane._release_issues(release)
        release_id = (
            str(release.get("release_id"))
            if isinstance(release, Mapping)
            and isinstance(release.get("release_id"), str)
            else None
        )
        if asserted_release_id is not None and asserted_release_id not in {
            release_id,
            "sha256:" + "0" * 64,
        }:
            raise AutopilotError(
                "supervisor wait release differs from current controller authority"
            )
        observation = plane._snapshot_observation()
        observation_record = (
            {
                "record_id": observation.get("record_id"),
                "status": observation.get("status"),
                "expires_at": observation.get("expires_at"),
                "fresh": (
                    observation.get("status") == "INSTALLED"
                    and parse_time(observation.get("expires_at")) > plane.clock()
                ),
            }
            if isinstance(observation, Mapping)
            else None
        )
        target_watermark = plane.repository_target_watermark()
        authority_digest: str | None = None
        authority_error: str | None = None
        if not release_issues and release_id is not None:
            try:
                authority = plane.round_authority_snapshot(release_id)
                raw_digest = authority.get("authority_digest")
                if not isinstance(raw_digest, str):
                    raise AutopilotError(
                        "round authority snapshot has no digest"
                    )
                authority_digest = raw_digest
            except Exception as error:
                authority_error = digest_json(
                    {
                        "kind": "hive-mind-supervisor-wait-authority-error-v1",
                        "error_type": type(error).__name__,
                        "detail": str(error),
                    }
                )
        material = {
            "kind": "hive-mind-supervisor-wait-observation-v2",
            "execution_id": plane.execution_id,
            "execution_namespace": plane.execution_namespace,
            "plan_fingerprint": plane.expected_plan_fingerprint,
            "frontier_id": frontier_id,
            "release_id": release_id,
            "release_record_id": (
                release.get("release_id") if isinstance(release, Mapping) else None
            ),
            "release_issues": list(release_issues),
            "status_digest": digest_json(status),
            "snapshot_observation": observation_record,
            "publication_record_id": (
                transaction_after.get("record_id")
                if isinstance(transaction_after, Mapping)
                else None
            ),
            "publication_status": (
                transaction_after.get("status")
                if isinstance(transaction_after, Mapping)
                else None
            ),
            "remote_publication": remote_publication,
            "target_watermark_record_id": target_watermark.get("record_id"),
            "authority_digest": authority_digest,
            "authority_error": authority_error,
            "host_scheduler_observation": scheduler_observation,
        }
    return digest_json(material)


def _supervisor_wait_observation_verifier(
    plane: ControlPlane,
    *,
    request: WaitObservationVerificationRequest,
) -> str:
    if (
        Path(request.execution_dir).resolve() != plane.execution_dir.resolve()
        or request.execution_id != plane.execution_id
        or request.execution_namespace != plane.execution_namespace
        or request.plan_fingerprint != plane.expected_plan_fingerprint
    ):
        raise AutopilotError(
            "wait observation request differs from execution authority"
        )
    expected_token = digest_json(
        {
            "kind": "hive-mind-supervisor-wait-resume-v1",
            "execution_id": plane.execution_id,
            "frontier_id": request.frontier_id,
            "observation_fingerprint": request.stored_observation_fingerprint,
        }
    )
    if request.resume_token != expected_token:
        raise AutopilotError("wait observation resume token is not authentic")
    return _supervisor_wait_observation_fingerprint(
        plane, frontier_id=request.frontier_id
    )


def _automatic_supervisor_wait_resume(
    plane: ControlPlane,
    *,
    observation_fingerprint: str | None,
    resume_token: str | None,
) -> tuple[str | None, str | None]:
    """Reobserve a durable controller wait without caller-supplied guesswork.

    The durable token authenticates the *stored* observation.  The current
    fingerprint is independently recomputed here and authenticated again by the
    supervisor after it takes its lease.  A concurrent journal/controller change
    therefore fails closed instead of turning this read-only convenience into a
    wake authority.
    """

    if observation_fingerprint is not None or resume_token is not None:
        return observation_fingerprint, resume_token
    replay = execution_supervisor_runtime._load_journal(
        plane.execution_dir / execution_supervisor_runtime.JOURNAL_NAME,
        execution_id=plane.execution_id,
        execution_namespace=plane.execution_namespace,
        plan_fingerprint=plane.expected_plan_fingerprint,
    )
    condition = replay.durable_wait
    frontier_id = replay.current_frontier
    if (
        condition is None
        or replay.durable_wait_host_capability
        in {HostCapability.ATTENDED_CARD_ONLY, HostCapability.NO_LAUNCH}
        or condition.observation_fingerprint is None
        or condition.resume_token is None
        or frontier_id is None
    ):
        return None, None
    current = _supervisor_wait_observation_fingerprint(
        plane, frontier_id=frontier_id
    )
    return current, condition.resume_token


def _controller_reconcile_unknown_attempt(
    plane: ControlPlane,
    adapter: object,
    *,
    host_id: str,
    actor: str,
    attempt_id: str,
) -> tuple[str, StepResult]:
    """Derive a recovery result only from durable controller and host facts."""

    journal_path = plane.execution_dir / execution_supervisor_runtime.JOURNAL_NAME
    replay = execution_supervisor_runtime._load_journal(
        journal_path,
        execution_id=plane.execution_id,
        execution_namespace=plane.execution_namespace,
        plan_fingerprint=plane.expected_plan_fingerprint,
    )
    matches = [item for item in replay.pending_attempts if item[1] == attempt_id]
    if len(matches) != 1:
        raise AutopilotError(
            "unknown-attempt reconciliation must name one durable pending attempt"
        )
    transaction_id, _, frontier_id, host_capability = matches[0]
    release = plane.current_release()
    publication_pair = plane._current_publication_resource()
    publication = publication_pair[1] if publication_pair is not None else None
    status = plane.observe_status()

    result: StepResult
    authority_digest: str | None = None
    release_id = (
        str(release.get("release_id"))
        if isinstance(release, Mapping)
        and isinstance(release.get("release_id"), str)
        else "sha256:" + "0" * 64
    )
    if (
        isinstance(publication, Mapping)
        and publication.get("execution_id") == plane.execution_id
        and publication.get("release_id") == release_id
    ):
        publication_status = str(publication.get("status"))
        if publication_status in {"PUBLISHED", "SUPERSEDED_INTEGRATED"}:
            next_frontier = digest_json(
                {
                    "kind": "hive-mind-supervisor-round-frontier-v1",
                    "execution_id": plane.execution_id,
                    "prior_frontier_id": frontier_id,
                    "release_id": release_id,
                    "publication_record_id": publication.get("record_id"),
                }
            )
            result = StepResult(
                disposition=StepDisposition.ROUND_COMPLETE,
                detail=(
                    "durable publication evidence proves the crash-unknown round "
                    "completed"
                ),
                next_frontier_id=next_frontier,
            )
        elif publication_status == "REJECTED":
            result = StepResult(
                disposition=StepDisposition.BLOCKED,
                detail="durable publication evidence proves the unknown round was rejected",
            )
        else:
            result = StepResult(
                disposition=StepDisposition.WAITING,
                detail=(
                    "the crash-unknown step is fenced by a nonterminal or "
                    "indeterminate publication transaction"
                ),
                wait_condition=_supervisor_wait_condition(
                    plane,
                    frontier_id=frontier_id,
                    release_id=release_id,
                    evidence=publication,
                ),
            )
    else:
        release_issues = plane._release_issues(release)
        if release_issues or not isinstance(release, Mapping):
            raise AutopilotError(
                "unknown attempt lacks a current authenticated release: "
                + "; ".join(release_issues)
            )
        authority = plane.round_authority_snapshot(release_id)
        raw_authority_digest = authority.get("authority_digest")
        if not isinstance(raw_authority_digest, str):
            raise AutopilotError(
                "unknown attempt lacks a sealed round authority digest"
            )
        authority_digest = raw_authority_digest
        active_fields = (
            "active_write_launch_reservations",
            "active_host_reservations",
            "execution_global_host_reservations",
            "active_claims",
            "conflicting_global_reservations",
            "reconciliation_obligations",
            "host_effect_obligations",
        )
        active = any(bool(authority.get(field)) for field in active_fields) or any(
            (
                authority.get("active_validation_lease") is not None,
                authority.get("active_publication_count") != 0,
                authority.get("active_host_effect_count") != 0,
            )
        )
        if status.get("complete") is True and not active:
            observer_context = ObserverContext(
                execution_dir=plane.execution_dir,
                execution_id=plane.execution_id,
                execution_namespace=plane.execution_namespace,
                plan_fingerprint=plane.expected_plan_fingerprint,
                initial_frontier_id=plane.expected_plan_fingerprint,
                frontier_id=frontier_id,
                completed_frontiers=replay.completed_frontiers,
            )
            terminal_observation_id = _capture_terminal_lifecycle_observation(
                plane,
                adapter,
                context=observer_context,
                host_id=host_id,
                release_id=release_id,
            )
            return (
                terminal_observation_id,
                StepResult(
                    disposition=StepDisposition.PLAN_QUIESCENT,
                    detail=(
                        "controller and authenticated host lifecycle prove the "
                        "crash-unknown attempt reached fixed point"
                    ),
                    terminal_observation_id=terminal_observation_id,
                ),
            )
        if active:
            result = StepResult(
                disposition=StepDisposition.WAITING,
                detail=(
                    "durable launch/publication authority remains active; the "
                    "unknown attempt is closed without duplicating an effect"
                ),
                wait_condition=_supervisor_wait_condition(
                    plane,
                    frontier_id=frontier_id,
                    release_id=release_id,
                    evidence=authority,
                ),
            )
        elif host_capability is HostCapability.AUTHENTICATED_OBSERVER:
            result = StepResult(
                disposition=StepDisposition.WAITING_FOR_HOST,
                detail=(
                    "observer-only authority cannot replay an unfinished "
                    "crash-unknown controller step"
                ),
                wait_condition=_supervisor_wait_condition(
                    plane,
                    frontier_id=frontier_id,
                    release_id=release_id,
                    evidence=authority,
                ),
            )
        else:
            # No durable host/publication effect survived the STEP_STARTED crash.
            # Close that uncertainty, then let the next supervisor epoch replay the
            # deterministic controller step through its idempotency authorities.
            result = StepResult(
                disposition=StepDisposition.WAITING,
                detail=(
                    "no durable effect exists for the crash-unknown step; an "
                    "immediate new controller epoch may safely retry it"
                ),
                wait_condition=WaitCondition(wake_at=plane.clock()),
            )

    observation_material: dict[str, object] = {
        "schema_version": 1,
        "kind": "hive-mind-supervisor-attempt-adjudication-v1",
        "execution_namespace": plane.execution_namespace,
        "execution_id": plane.execution_id,
        "plan_fingerprint": plane.expected_plan_fingerprint,
        "attempt_id": attempt_id,
        "supervisor_transaction_id": transaction_id,
        "frontier_id": frontier_id,
        "host_capability": host_capability.value,
        "release_id": release_id,
        "release_record_id": (
            release.get("release_id") if isinstance(release, Mapping) else None
        ),
        "publication_record_id": (
            publication.get("record_id")
            if isinstance(publication, Mapping)
            else None
        ),
        "authority_digest": authority_digest,
        "status_digest": digest_json(status),
        "disposition": result.disposition.value,
        "detail_digest": digest_json(
            {
                "kind": "hive-mind-supervisor-adjudication-detail-v1",
                "detail": result.detail,
            }
        ),
        "adjudicated_by": actor,
        "adjudicated_at": format_time(plane.clock()),
    }
    observation_id = digest_json(observation_material)
    observation = {**observation_material, "observation_id": observation_id}
    plane._write_immutable_json(
        plane._secure_execution_path(
            Path("supervisor-attempt-adjudications")
            / f"{observation_id.removeprefix('sha256:')}.json"
        ),
        observation,
    )
    return observation_id, result


def _refresh_supervisor_snapshot(plane: ControlPlane, *, actor: str) -> None:
    """Run only the sealed snapshot coordinator, outside controller locks."""

    script = Path(__file__).resolve().with_name("github_snapshot.py")
    if (
        not script.is_file()
        or plane._is_link_like(script)
        or script.resolve().parent != Path(__file__).resolve().parent
    ):
        raise AutopilotError("sealed GitHub snapshot coordinator is unavailable")
    command = [
        sys.executable,
        str(script),
        "--repo-root",
        str(plane.repo_root),
        "--state-dir",
        str(plane.coordination_dir),
        "--execution-namespace",
        plane.execution_namespace,
        "--host-runtime-dir",
        str(plane.host_runtime_dir),
        "--reconcile",
        "--actor",
        actor,
    ]
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }
    completed = subprocess.run(
        command,
        cwd=plane.repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        timeout=1800,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise AutopilotError(
            "autonomous GitHub snapshot/reconciliation failed closed"
            + (f": {detail}" if detail else "")
        )


def _capture_terminal_lifecycle_observation(
    plane: ControlPlane,
    adapter: object,
    *,
    context: StepContext | ObserverContext,
    host_id: str,
    release_id: str,
) -> str:
    capture = getattr(adapter, "capture_terminal_lifecycle_observation", None)
    if not callable(capture):
        raise AutopilotError(
            "authenticated host adapter cannot capture terminal lifecycle truth"
        )
    raw = capture(
        execution_namespace=plane.execution_namespace,
        execution_id=plane.execution_id,
        execution_dir=plane.execution_dir,
        host_id=host_id,
        frontier_id=context.frontier_id,
        release_id=release_id,
    )
    observation_id = (
        raw.get("observation_id") if isinstance(raw, Mapping) else raw
    )
    if not isinstance(observation_id, str):
        raise AutopilotError("terminal host observation has no sealed identity")
    checked = _authenticated_host_lifecycle_observation(
        plane,
        adapter,
        host_id=host_id,
        frontier_id=context.frontier_id,
        observation_id=observation_id,
        expected_disposition=StepDisposition.PLAN_QUIESCENT,
    )
    if isinstance(raw, Mapping) and dict(raw) != dict(checked):
        raise AutopilotError(
            "captured host lifecycle observation changed before authentication"
        )
    return observation_id


def _recover_supervisor_expired_validation_lease(
    plane: ControlPlane, *, actor: str
) -> Mapping[str, object]:
    """Perform the one typed, crash-idempotent pre-round expiry transition."""

    before = plane.observe_status()
    expired = before.get("expired_validation_lease")
    if expired is None:
        return before
    if not isinstance(expired, Mapping):
        raise AutopilotError(
            "expired validation recovery obligation is malformed"
        )
    lease_id = expired.get("lease_id")
    if not isinstance(lease_id, str) or AUTHORITY_ID.fullmatch(lease_id) is None:
        raise AutopilotError(
            "expired validation recovery obligation has no exact lease id"
        )
    plane.break_expired_validation_lease(
        actor=actor,
        lease_id=lease_id,
    )
    after = plane.observe_status()
    remaining = after.get("expired_validation_lease")
    if remaining is not None:
        raise AutopilotError(
            "expired validation lease remained after its exact recovery transition"
        )
    return after


def _supervisor_terminal_observer(
    plane: ControlPlane,
    adapter: object,
    *,
    context: ObserverContext,
    host_id: str,
) -> ObserverResult:
    """Nominate only an already-terminal execution; never admit or run work."""

    if (
        context.execution_id != plane.execution_id
        or context.execution_namespace != plane.execution_namespace
        or context.plan_fingerprint != plane.expected_plan_fingerprint
    ):
        return ObserverResult(
            disposition=StepDisposition.RECOVERY_REQUIRED,
            detail="terminal observer identity differs from controller authority",
        )
    try:
        status = _recover_supervisor_expired_validation_lease(
            plane, actor="autopilot:observer-expired-validation-recovery"
        )
        publication_pair = plane._current_publication_resource()
        publication = (
            publication_pair[1] if publication_pair is not None else None
        )
        if (
            isinstance(publication, Mapping)
            and publication.get("execution_id") == plane.execution_id
            and publication.get("status") == "PUBLISH_UNKNOWN"
        ):
            adjudicated = plane.adjudicate_unknown_publication(
                publication,
                actor="autopilot:observer-publication-adjudication",
            )
            if adjudicated.get("status") == "PUBLISH_UNKNOWN":
                return ObserverResult(
                    disposition=StepDisposition.WAITING_FOR_HOST,
                    detail=(
                        "publication outcome remains historically indeterminate; "
                        "the exact target transaction stays fenced"
                    ),
                    wait_condition=_supervisor_wait_condition(
                        plane,
                        frontier_id=context.frontier_id,
                        release_id=str(adjudicated["release_id"]),
                        evidence=adjudicated,
                    ),
                )
            status = plane.observe_status()
        release = plane.current_release()
        release_issues = plane._release_issues(release)
        if release_issues or not isinstance(release, Mapping):
            return ObserverResult(
                disposition=StepDisposition.WAITING_FOR_HOST,
                detail=(
                    "authenticated observer cannot create or replace a dispatcher "
                    "release; crash-exact launch authority is required"
                ),
                wait_condition=_supervisor_wait_condition(
                    plane,
                    frontier_id=context.frontier_id,
                    release_id="sha256:" + "0" * 64,
                    evidence={
                        "status": status,
                        "release_issues": list(release_issues),
                    },
                ),
            )
        release_id = str(release["release_id"])
        if status.get("complete") is not True:
            return ObserverResult(
                disposition=StepDisposition.WAITING_FOR_HOST,
                detail=(
                    "authenticated observer found unfinished controller work; "
                    "no dispatch, reservation, binding, or host effect was admitted"
                ),
                wait_condition=_supervisor_wait_condition(
                    plane,
                    frontier_id=context.frontier_id,
                    release_id=release_id,
                    evidence=status,
                ),
            )
        authority = plane.round_authority_snapshot(release_id)
        authority_status = authority.get("status")
        activity_fields = (
            "active_write_launch_reservations",
            "active_host_reservations",
            "execution_global_host_reservations",
            "active_claims",
            "conflicting_global_reservations",
            "reconciliation_obligations",
            "host_effect_obligations",
        )
        activity = any(bool(authority.get(field)) for field in activity_fields) or any(
            (
                authority.get("active_validation_lease") is not None,
                authority.get("active_publication_count") != 0,
                authority.get("active_host_effect_count") != 0,
            )
        )
        if (
            not isinstance(authority_status, Mapping)
            or authority_status.get("complete") is not True
            or activity
        ):
            return ObserverResult(
                disposition=StepDisposition.WAITING_FOR_HOST,
                detail=(
                    "controller is not at a sealed zero-activity terminal cut; "
                    "observer admission remains closed"
                ),
                wait_condition=_supervisor_wait_condition(
                    plane,
                    frontier_id=context.frontier_id,
                    release_id=release_id,
                    evidence=authority,
                ),
            )
        observation_id = _capture_terminal_lifecycle_observation(
            plane,
            adapter,
            context=context,
            host_id=host_id,
            release_id=release_id,
        )
        return ObserverResult(
            disposition=StepDisposition.PLAN_QUIESCENT,
            detail=(
                "authenticated observer nominated an already-terminal controller "
                "cut with zero host lifecycle; the controller verifier must seal it"
            ),
            terminal_observation_id=observation_id,
        )
    except Exception as error:
        return ObserverResult(
            disposition=StepDisposition.RECOVERY_REQUIRED,
            detail=f"terminal observer could not authenticate controller truth: {error}",
        )


def _controller_round_step_result(
    plane: ControlPlane,
    adapter: object,
    *,
    context: StepContext,
    host_id: str,
    actor: str,
    release: Mapping[str, object],
) -> StepResult:
    current_pair = plane._current_publication_resource()
    current_transaction = current_pair[1] if current_pair is not None else None
    if (
        isinstance(current_transaction, Mapping)
        and current_transaction.get("execution_id") == plane.execution_id
        and current_transaction.get("release_id") == release.get("release_id")
    ):
        status = current_transaction.get("status")
        if status in {"VALIDATED", "PUBLISHING"}:
            pinned_sha = current_transaction.get("pinned_sha")
            if not isinstance(pinned_sha, str):
                return StepResult(
                    StepDisposition.RECOVERY_REQUIRED,
                    f"{status} recovery lacks its pinned transaction SHA",
                )
            expired = (
                parse_time(current_transaction.get("lease_expires_at"))
                <= plane.clock()
            )
            if status == "VALIDATED" and expired:
                receipt_heads = {
                    str(item["node_id"]): str(item["sha"])
                    for item in current_transaction.get("receipt_heads", [])
                    if isinstance(item, Mapping)
                }
                current_transaction = plane.begin_publication_transaction(
                    release_id=str(current_transaction["release_id"]),
                    round_id=str(current_transaction["round_id"]),
                    expected_target_sha=str(
                        current_transaction["expected_target_sha"]
                    ),
                    authority_digest=str(current_transaction["authority_digest"]),
                    receipt_heads=receipt_heads,
                    coordinator_id=actor,
                    actor=actor,
                )
                with plane.publication_recovery_guard(
                    current_transaction, coordinator_id=actor
                ):
                    result = drive_round(
                        plane,
                        actor=actor,
                        push=True,
                        round_authority={"release_id": str(release["release_id"])},
                    )
            else:
                recovered = plane.publish_pinned_transaction(
                    current_transaction,
                    pinned_sha=pinned_sha,
                    actor=actor,
                    _reconcile_expired=(status == "PUBLISHING" and expired),
                )
                outcome = recovered.get("outcome")
                if outcome == "PUBLISHED":
                    result: Mapping[str, object] = {
                        "disposition": "ROUND_COMPLETE",
                        "publication_transaction": dict(recovered),
                    }
                elif outcome == "REJECTED":
                    result = {
                        "disposition": "PUBLISH_REJECTED",
                        "publication_transaction": dict(recovered),
                    }
                else:
                    result = {
                        "disposition": "PUBLISH_UNKNOWN",
                        "publication_transaction": dict(recovered),
                    }
        elif status in {"PREPARED", "PINNED"}:
            if parse_time(current_transaction.get("lease_expires_at")) <= plane.clock():
                receipt_heads = {
                    str(item["node_id"]): str(item["sha"])
                    for item in current_transaction.get("receipt_heads", [])
                    if isinstance(item, Mapping)
                }
                current_transaction = plane.begin_publication_transaction(
                    release_id=str(current_transaction["release_id"]),
                    round_id=str(current_transaction["round_id"]),
                    expected_target_sha=str(
                        current_transaction["expected_target_sha"]
                    ),
                    authority_digest=str(current_transaction["authority_digest"]),
                    receipt_heads=receipt_heads,
                    coordinator_id=actor,
                    actor=actor,
                )
            with plane.publication_recovery_guard(
                current_transaction, coordinator_id=actor
            ):
                result = drive_round(
                    plane,
                    actor=actor,
                    push=True,
                    round_authority={"release_id": str(release["release_id"])},
                )
        elif status in {"PUBLISHED", "SUPERSEDED_INTEGRATED"}:
            result = {
                "disposition": "ROUND_COMPLETE",
                "publication_transaction": dict(current_transaction),
            }
        elif status == "REJECTED":
            result = {
                "disposition": "PUBLISH_REJECTED",
                "publication_transaction": dict(current_transaction),
            }
        elif status == "PUBLISH_UNKNOWN":
            adjudicated = plane.adjudicate_unknown_publication(
                current_transaction,
                actor=actor,
            )
            outcome = adjudicated.get("outcome")
            result = {
                "disposition": (
                    "ROUND_COMPLETE"
                    if outcome in {"PUBLISHED", "SUPERSEDED_INTEGRATED"}
                    else "PUBLISH_REJECTED"
                    if outcome == "REJECTED"
                    else "PUBLISH_UNKNOWN"
                ),
                "publication_transaction": dict(adjudicated),
            }
        else:
            result = drive_round(
                plane,
                actor=actor,
                push=True,
                round_authority={"release_id": str(release["release_id"])},
            )
    else:
        result = drive_round(
            plane,
            actor=actor,
            push=True,
            round_authority={"release_id": str(release["release_id"])},
        )
    if not isinstance(result, Mapping) or not isinstance(
        result.get("disposition"), str
    ):
        return StepResult(
            disposition=StepDisposition.RECOVERY_REQUIRED,
            detail="round driver returned malformed controller evidence",
        )
    disposition = str(result["disposition"])
    if disposition == "CONTROLLER_QUIESCENT_CANDIDATE":
        observation_id = _capture_terminal_lifecycle_observation(
            plane,
            adapter,
            context=context,
            host_id=host_id,
            release_id=str(release["release_id"]),
        )
        return StepResult(
            disposition=StepDisposition.PLAN_QUIESCENT,
            detail=(
                "controller DAG and authority are complete with authenticated "
                "zero host lifecycle"
            ),
            terminal_observation_id=observation_id,
        )
    if disposition == "ROUND_COMPLETE":
        publication = result.get("publication_transaction")
        next_frontier = digest_json(
            {
                "kind": "hive-mind-supervisor-round-frontier-v1",
                "execution_id": plane.execution_id,
                "prior_frontier_id": context.frontier_id,
                "release_id": release["release_id"],
                "publication_record_id": (
                    publication.get("record_id")
                    if isinstance(publication, Mapping)
                    else None
                ),
            }
        )
        return StepResult(
            disposition=StepDisposition.ROUND_COMPLETE,
            detail="controller published the exact validated round",
            next_frontier_id=next_frontier,
        )
    if disposition in {"ACTIVE", "PENDING"}:
        return StepResult(
            disposition=StepDisposition.WAITING,
            detail="controller round is waiting on authenticated durable evidence",
            wait_condition=_supervisor_wait_condition(
                plane,
                frontier_id=context.frontier_id,
                release_id=str(release["release_id"]),
                evidence=result,
            ),
        )
    if disposition == "PUBLISH_UNKNOWN":
        return StepResult(
            disposition=StepDisposition.WAITING,
            detail=(
                "remote publication outcome remains indeterminate; the exact "
                "transaction stays fenced for another authenticated observation"
            ),
            wait_condition=_supervisor_wait_condition(
                plane,
                frontier_id=context.frontier_id,
                release_id=str(release["release_id"]),
                evidence=result,
            ),
        )
    if disposition in {"BLOCKED", "PUBLISH_REJECTED"}:
        return StepResult(
            disposition=StepDisposition.BLOCKED,
            detail=f"controller round stopped with {disposition}",
        )
    return StepResult(
        disposition=StepDisposition.RECOVERY_REQUIRED,
        detail=f"controller round requires recovery: {disposition}",
    )


def _supervisor_controller_step(
    plane: ControlPlane,
    adapter: object,
    *,
    context: StepContext,
    host_id: str,
    execution_adapter_identity: Mapping[str, object],
    actor: str,
    request: str,
    launch_authorized: bool,
) -> StepResult:
    """Own DAG progression in the controller; the host supplies effects only."""

    if (
        context.execution_id != plane.execution_id
        or context.execution_namespace != plane.execution_namespace
        or context.plan_fingerprint != plane.expected_plan_fingerprint
    ):
        return StepResult(
            disposition=StepDisposition.RECOVERY_REQUIRED,
            detail="supervisor step identity differs from controller authority",
        )
    snapshot_issues = plane._snapshot_observation_dispatch_issues(
        plane._snapshot_digest()
    )
    publication_pair = plane._current_publication_resource()
    publication = publication_pair[1] if publication_pair is not None else None
    published_target_requires_refresh = bool(
        isinstance(publication, Mapping)
        and publication.get("execution_id") == plane.execution_id
        and publication.get("status") == "PUBLISHED"
        and publication.get("pinned_sha") != plane._execution_target_sha()
    )
    release = plane.current_release()
    release_issues = plane._release_issues(release)
    if snapshot_issues or release_issues or published_target_requires_refresh:
        try:
            _refresh_supervisor_snapshot(plane, actor=actor)
        except Exception as error:
            return StepResult(
                disposition=StepDisposition.RECOVERY_REQUIRED,
                detail=f"snapshot/reconciliation recovery failed: {error}",
            )
    try:
        _recover_supervisor_expired_validation_lease(plane, actor=actor)
        status = plane.status()
        release = plane.current_release()
        if plane._release_issues(release):
            if not launch_authorized:
                return StepResult(
                    disposition=StepDisposition.WAITING_FOR_HOST,
                    detail=(
                        "authenticated observer cannot publish a dispatcher release; "
                        "crash-exact launch authority is unavailable"
                    ),
                    wait_condition=_supervisor_wait_condition(
                        plane,
                        frontier_id=context.frontier_id,
                        release_id="sha256:" + "0" * 64,
                        evidence=status,
                    ),
                )
            release = plane.dispatch(
                actor=actor,
                host_id=host_id,
                execution_adapter_identity=execution_adapter_identity,
            )
            status = plane.status()
        if not isinstance(release, Mapping) or plane._release_issues(release):
            raise AutopilotError("controller could not authenticate a dispatcher release")
        wave = release.get("released_wave")
        if not isinstance(wave, list):
            raise AutopilotError("dispatcher release wave is malformed")
        if not launch_authorized and status.get("complete") is not True:
            return StepResult(
                disposition=StepDisposition.WAITING_FOR_HOST,
                detail=(
                    "authenticated observer found unfinished controller work; "
                    "crash-exact launch authority is unavailable"
                ),
                wait_condition=_supervisor_wait_condition(
                    plane,
                    frontier_id=context.frontier_id,
                    release_id=str(release["release_id"]),
                    evidence=status,
                ),
            )
        if not launch_authorized:
            return _controller_round_step_result(
                plane,
                adapter,
                context=context,
                host_id=host_id,
                actor=actor,
                release=release,
            )
        if not wave:
            return _controller_round_step_result(
                plane,
                adapter,
                context=context,
                host_id=host_id,
                actor=actor,
                release=release,
            )
        contract = build_orchestration_contract(
            plane,
            request,
            status=status,
            host_id=host_id,
            allow_sidecars=False,
            allow_preparation_tasks=False,
        )
        tasks = contract.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            raise AutopilotError(
                "authenticated dispatcher wave produced no executable contract"
            )
        bind_tasks = getattr(adapter, "bind_tasks", None)
        if not callable(bind_tasks):
            raise AutopilotError(
                "authenticated host adapter cannot bind controller-selected tasks"
            )
        bind_tasks(tasks)
        host_result = execute_contract(
            plane.repo_root,
            contract,
            adapter,
            EvidenceResolver(),
            state_dir=plane.execution_dir,
            host_runtime_dir=plane.host_runtime_dir,
        )
    except HostCapacityWaiting as error:
        return StepResult(
            disposition=StepDisposition.WAITING_FOR_CAPACITY,
            detail=str(error),
            wait_condition=_supervisor_wait_condition(
                plane,
                frontier_id=context.frontier_id,
                release_id="sha256:" + "0" * 64,
                evidence={"scheduler_wait": str(error)},
            ),
        )
    except Exception as error:
        return StepResult(
            disposition=StepDisposition.RECOVERY_REQUIRED,
            detail=f"controller-owned supervisor step failed: {error}",
        )
    if (
        not isinstance(host_result, Mapping)
        or host_result.get("kind") != "hive-mind-host-execution-result-v1"
    ):
        return StepResult(
            disposition=StepDisposition.RECOVERY_REQUIRED,
            detail="host executor returned malformed lifecycle evidence",
        )
    terminal = host_result.get("terminal")
    required_ids = {
        str(task.get("launch_instruction_id"))
        for task in tasks
        if isinstance(task, Mapping) and task.get("required") is True
    }
    if isinstance(terminal, Mapping) and required_ids <= set(terminal):
        failures = [
            instruction_id
            for instruction_id in sorted(required_ids)
            if terminal.get(instruction_id) != "SUCCEEDED"
        ]
        if failures:
            return StepResult(
                disposition=StepDisposition.BLOCKED,
                detail="required host tasks ended without success: "
                + ", ".join(failures),
            )
        return _controller_round_step_result(
            plane,
            adapter,
            context=context,
            host_id=host_id,
            actor=actor,
            release=release,
        )
    host_state = host_result.get("supervisor_state")
    if host_state == "WAITING_FOR_HOST":
        disposition = StepDisposition.WAITING_FOR_HOST
    elif host_state in {"WAITING", "ACTIVE"}:
        disposition = StepDisposition.WAITING
    elif host_state == "RECOVERY_REQUIRED":
        return StepResult(
            disposition=StepDisposition.RECOVERY_REQUIRED,
            detail="host executor reported recovery-required lifecycle authority",
        )
    else:
        return StepResult(
            disposition=StepDisposition.RECOVERY_REQUIRED,
            detail=f"host executor returned unknown supervisor state: {host_state}",
        )
    return StepResult(
        disposition=disposition,
        detail="controller is waiting for authenticated host lifecycle progress",
        wait_condition=_supervisor_wait_condition(
            plane,
            frontier_id=context.frontier_id,
            release_id=str(release["release_id"]),
            evidence=host_result,
        ),
    )


HOST_LIFECYCLE_OBSERVATION_KIND = (
    "hive-mind-authenticated-host-lifecycle-observation-v1"
)
APP_SERVER_PROVIDER_IDENTITY_SOURCE = "codex-app-server-provider-identity-v1"
APP_SERVER_CONSERVATIVE_CAPACITY_SOURCE = (
    "codex-app-server-conservative-capacity-v1"
)
APP_SERVER_MAX_TOTAL_SESSIONS = 1
APP_SERVER_VALIDATION_SLOTS = 1
APP_SERVER_MAX_EVIDENCED_SESSIONS = 256
RUNTIME_MIGRATION_OPERATION_KIND = "hive-mind-runtime-migration-operation-v1"
RUNTIME_MIGRATION_ABORT_KIND = "hive-mind-runtime-migration-abort-v1"
RUNTIME_MIGRATION_COMPLETE_KIND = "hive-mind-runtime-migration-complete-v1"
RUNTIME_MIGRATION_OPERATION_ROOT = "mo"
HOST_LIFECYCLE_OBSERVATION_FIELDS = {
    "schema_version",
    "kind",
    "execution_namespace",
    "execution_id",
    "host_id",
    "frontier_id",
    "disposition",
    "active_host_threads",
    "active_host_turns",
    "unobserved_host_lifecycle_items",
    "observed_at",
    "observation_id",
}
APP_SERVER_PROVIDER_IDENTITY_FIELDS = {
    "schema_version",
    "kind",
    "execution_namespace",
    "execution_id",
    "host_id",
    "machine_user_id",
    "provider_identity_digest",
    "adapter_module_path",
    "adapter_module_digest",
    "launcher_path",
    "launcher_digest",
    "cli_module_path",
    "cli_module_digest",
    "executable_path",
    "executable_digest",
    "executable_version",
    "schema_bundle_digest",
    "thread_start_schema_digest",
    "turn_start_schema_digest",
    "environment_root_digest",
    "behavior_environment_digest",
    "provider_config_digest",
    "execution_config_digest",
    "account_identity_digest",
    "effective_model",
    "effective_model_provider",
    "transport",
    "initialize_result_digest",
    "created_at",
    "record_id",
}
APP_SERVER_CAPACITY_CAPABILITY_FIELDS = {
    "schema_version",
    "kind",
    "host_id",
    "provider_identity_digest",
    "max_total_sessions",
    "validation_slots",
    "issued_at",
    "expires_at",
    "source",
    "record_id",
}


def _app_server_global_provider_material(
    record: Mapping[str, object],
) -> Mapping[str, object]:
    """Return only machine-user App Server identity shared across executions."""

    return {
        "kind": "hive-mind-codex-app-server-provider-identity-v1",
        **{
            field: record.get(field)
            for field in (
                "machine_user_id",
                "launcher_path",
                "launcher_digest",
                "cli_module_path",
                "cli_module_digest",
                "executable_path",
                "executable_digest",
                "executable_version",
                "schema_bundle_digest",
                "thread_start_schema_digest",
                "turn_start_schema_digest",
                "environment_root_digest",
                "behavior_environment_digest",
                "provider_config_digest",
                "account_identity_digest",
                "transport",
                "initialize_result_digest",
            )
        },
    }


def _canonical_app_server_host_id(plane: ControlPlane) -> str:
    """Derive one App Server provider id from sealed machine-user authority."""

    with plane.host_lock(timeout_seconds=120.0):
        value = read_current_host_runtime_identity(plane.host_runtime_dir)
    if AUTHORITY_ID.fullmatch(str(value.get("machine_user_id"))) is None:
        raise AutopilotError(
            "host writer identity cannot authenticate the App Server provider"
        )
    return digest_json(
        {
            "kind": "hive-mind-codex-app-server-provider-v1",
            "machine_user_id": value["machine_user_id"],
        }
    )


def _app_server_provider_identity(
    plane: ControlPlane,
    adapter: object,
    *,
    host_id: str,
    module_digest: str,
) -> Mapping[str, object]:
    provider = getattr(adapter, "host_provider_identity", None)
    if not callable(provider):
        raise AutopilotError("App Server adapter lacks sealed provider identity")
    value = provider(repo_root=plane.repo_root)
    if not isinstance(value, Mapping) or set(value) != (
        APP_SERVER_PROVIDER_IDENTITY_FIELDS
    ):
        raise AutopilotError("App Server provider identity schema is invalid")
    record = dict(value)
    material = dict(record)
    record_id = material.pop("record_id", None)
    with plane.host_lock(timeout_seconds=120.0):
        runtime_identity = read_current_host_runtime_identity(
            plane.host_runtime_dir
        )
    machine_user_id = runtime_identity.get("machine_user_id")
    provider_material = _app_server_global_provider_material(record)
    provider_identity_digest = digest_json(provider_material)
    if (
        record.get("schema_version") != 1
        or record.get("kind") != "hive-mind-codex-app-server-identity-v1"
        or record.get("execution_namespace") != plane.execution_namespace
        or record.get("execution_id") != plane.execution_id
        or record.get("host_id") != host_id
        or record.get("machine_user_id") != machine_user_id
        or record.get("adapter_module_digest") != module_digest
        or record_id != digest_json(material)
        or record.get("provider_identity_digest") != provider_identity_digest
        or record.get("transport") != "stdio://"
        or not isinstance(record.get("executable_version"), str)
        or not str(record["executable_version"]).strip()
        or any(
            not isinstance(record.get(field), str)
            or AUTHORITY_ID.fullmatch(str(record[field])) is None
            for field in (
                "schema_bundle_digest",
                "thread_start_schema_digest",
                "turn_start_schema_digest",
                "environment_root_digest",
                "behavior_environment_digest",
                "provider_config_digest",
                "execution_config_digest",
                "account_identity_digest",
                "initialize_result_digest",
            )
        )
        or not isinstance(record.get("effective_model"), str)
        or not str(record["effective_model"]).strip()
        or not (
            record.get("effective_model_provider") is None
            or (
                isinstance(record.get("effective_model_provider"), str)
                and str(record["effective_model_provider"]).strip()
            )
        )
    ):
        raise AutopilotError("App Server provider identity is invalid")
    expected_adapter = Path(__file__).resolve().with_name("app_server_host.py")
    path_digest_pairs = (
        (record.get("adapter_module_path"), record.get("adapter_module_digest")),
        (record.get("launcher_path"), record.get("launcher_digest")),
        (record.get("executable_path"), record.get("executable_digest")),
    )
    for raw_path, raw_digest in path_digest_pairs:
        if (
            not isinstance(raw_path, str)
            or not Path(raw_path).is_absolute()
            or not isinstance(raw_digest, str)
            or AUTHORITY_ID.fullmatch(raw_digest) is None
        ):
            raise AutopilotError("App Server provider executable path is invalid")
        provider_path = Path(raw_path)
        if (
            not provider_path.is_file()
            or plane._is_link_like(provider_path)
            or "sha256:" + sha256(provider_path.read_bytes()).hexdigest()
            != raw_digest
        ):
            raise AutopilotError(
                "App Server provider executable differs from sealed identity"
            )
    if Path(str(record["adapter_module_path"])).resolve() != expected_adapter:
        raise AutopilotError("App Server provider identity names another adapter")
    cli_path = record.get("cli_module_path")
    cli_digest = record.get("cli_module_digest")
    if (cli_path is None) != (cli_digest is None):
        raise AutopilotError("App Server CLI module identity is partial")
    if cli_path is not None:
        if (
            not isinstance(cli_path, str)
            or not Path(cli_path).is_absolute()
            or not isinstance(cli_digest, str)
            or AUTHORITY_ID.fullmatch(cli_digest) is None
        ):
            raise AutopilotError("App Server CLI module identity is invalid")
        selected_cli = Path(cli_path)
        if (
            not selected_cli.is_file()
            or plane._is_link_like(selected_cli)
            or "sha256:" + sha256(selected_cli.read_bytes()).hexdigest()
            != cli_digest
        ):
            raise AutopilotError("App Server CLI module differs from sealed identity")
    try:
        parse_time(record.get("created_at"))
    except Exception as error:
        raise AutopilotError("App Server provider identity timestamp is invalid") from error
    return record


def _app_server_lifecycle_authority(
    plane: ControlPlane,
    adapter: object,
    *,
    host_id: str,
    provider_identity: Mapping[str, object],
) -> Mapping[str, object]:
    provider = getattr(adapter, "host_lifecycle_authority", None)
    if not callable(provider):
        raise AutopilotError("App Server adapter lacks lifecycle capability authority")
    lifecycle = provider(repo_root=plane.repo_root)
    fields = {
        "schema_version",
        "kind",
        "host_id",
        "create",
        "query",
        "resume",
        "interrupt",
        "archive",
        "autonomous_launch",
        "source",
        "record_id",
    }
    if not isinstance(lifecycle, Mapping) or set(lifecycle) != fields:
        raise AutopilotError("App Server lifecycle capability schema is invalid")
    material = dict(lifecycle)
    record_id = material.pop("record_id", None)
    if (
        lifecycle.get("schema_version") != 1
        or lifecycle.get("kind") != "hive-mind-host-lifecycle-capability-v1"
        or lifecycle.get("host_id") != host_id
        or record_id != digest_json(material)
        or type(lifecycle.get("autonomous_launch")) is not bool
        or any(
            lifecycle.get(field) is not True
            for field in ("create", "query", "resume", "interrupt", "archive")
        )
        or lifecycle.get("source")
        != "codex-app-server-stdio:" + str(provider_identity.get("record_id"))
    ):
        raise AutopilotError("App Server lifecycle capability is invalid")
    return dict(lifecycle)


def _ensure_app_server_capacity(
    plane: ControlPlane,
    adapter: object,
    *,
    host_id: str,
    module_digest: str,
    provider_identity: Mapping[str, object],
    lifecycle: Mapping[str, object],
) -> Mapping[str, object]:
    """Publish one conservative or externally evidenced aggregate ceiling."""

    lifecycle_fields = {
        "schema_version",
        "kind",
        "host_id",
        "create",
        "query",
        "resume",
        "interrupt",
        "archive",
        "autonomous_launch",
        "source",
        "record_id",
    }
    if not isinstance(lifecycle, Mapping) or set(lifecycle) != lifecycle_fields:
        raise AutopilotError("App Server lifecycle capability schema is invalid")
    lifecycle_material = dict(lifecycle)
    lifecycle_record_id = lifecycle_material.pop("record_id", None)
    if (
        lifecycle.get("schema_version") != 1
        or lifecycle.get("kind") != "hive-mind-host-lifecycle-capability-v1"
        or lifecycle.get("host_id") != host_id
        or lifecycle_record_id != digest_json(lifecycle_material)
        or type(lifecycle.get("autonomous_launch")) is not bool
        or any(
            lifecycle.get(field) is not True
            for field in ("create", "query", "resume", "interrupt", "archive")
        )
    ):
        raise AutopilotError("App Server lifecycle capability is invalid")
    now = plane.clock()
    provider_identity_digest = provider_identity.get("provider_identity_digest")
    if (
        provider_identity.get("adapter_module_digest") != module_digest
        or not isinstance(provider_identity_digest, str)
        or AUTHORITY_ID.fullmatch(provider_identity_digest) is None
    ):
        raise AutopilotError("App Server capacity lacks provider identity")
    capability_reader = getattr(adapter, "host_capacity_capability", None)
    raw_capability = (
        capability_reader(repo_root=plane.repo_root)
        if lifecycle.get("autonomous_launch") is True
        and callable(capability_reader)
        else None
    )
    capability_source = APP_SERVER_CONSERVATIVE_CAPACITY_SOURCE
    max_total_sessions = APP_SERVER_MAX_TOTAL_SESSIONS
    validation_slots = APP_SERVER_VALIDATION_SLOTS
    declarative = True
    expires_at = now + timedelta(hours=1)
    if raw_capability is None:
        capability_material: dict[str, object] = {
            "schema_version": 1,
            "kind": "hive-mind-conservative-host-capacity-evidence-v1",
            "host_id": host_id,
            "provider_identity_digest": provider_identity_digest,
            "max_total_sessions": max_total_sessions,
            "validation_slots": validation_slots,
            "reason": "no sealed product/operator ceiling evidence",
        }
        capability_record: Mapping[str, object] = {
            **capability_material,
            "record_id": digest_json(capability_material),
        }
    else:
        if not isinstance(raw_capability, Mapping) or set(raw_capability) != (
            APP_SERVER_CAPACITY_CAPABILITY_FIELDS
        ):
            raise AutopilotError("App Server capacity capability schema is invalid")
        capability_record = dict(raw_capability)
        material = dict(capability_record)
        record_id = material.pop("record_id", None)
        try:
            issued = parse_time(capability_record.get("issued_at"))
            expires = parse_time(capability_record.get("expires_at"))
        except Exception as error:
            raise AutopilotError(
                "App Server capacity capability timestamps are invalid"
            ) from error
        if (
            capability_record.get("schema_version") != 1
            or capability_record.get("kind")
            != "hive-mind-host-capacity-capability-v1"
            or capability_record.get("host_id") != host_id
            or capability_record.get("provider_identity_digest")
            != provider_identity_digest
            or record_id != digest_json(material)
            or type(capability_record.get("max_total_sessions")) is not int
            or type(capability_record.get("validation_slots")) is not int
            or not isinstance(capability_record.get("source"), str)
            or not str(capability_record["source"]).strip()
            or issued > now
            or expires <= issued
            or expires - issued > timedelta(hours=24)
        ):
            raise AutopilotError("App Server capacity capability is invalid")
        asserted_total = int(capability_record["max_total_sessions"])
        asserted_validation = int(capability_record["validation_slots"])
        if (
            asserted_total < 1
            or asserted_total > APP_SERVER_MAX_EVIDENCED_SESSIONS
            or asserted_validation < 0
            or asserted_validation > asserted_total
        ):
            raise AutopilotError(
                "App Server evidenced capacity exceeds bounded policy"
            )
        if expires > now:
            max_total_sessions = asserted_total
            validation_slots = asserted_validation
            capability_source = str(capability_record["source"])
            declarative = False
            expires_at = expires
        else:
            # Expired evidence is retained in the conservative generation digest,
            # but no longer grants more than one aggregate session.
            capability_source = APP_SERVER_CONSERVATIVE_CAPACITY_SOURCE
    capability_digest = digest_json(
        {
            "kind": "hive-mind-app-server-capacity-generation-evidence-v1",
            "provider_identity_digest": provider_identity_digest,
            "capacity_evidence_record_id": capability_record["record_id"],
            "max_total_sessions": max_total_sessions,
            "validation_slots": validation_slots,
            "declarative": declarative,
        }
    )
    provider_attestation = build_host_provider_attestation(
        plane.host_runtime_dir,
        host_id=host_id,
        provider_identity_source=APP_SERVER_PROVIDER_IDENTITY_SOURCE,
        provider_identity_material=_app_server_global_provider_material(
            provider_identity
        ),
    )
    with plane.host_lock(timeout_seconds=120.0):
        evidence_path = (
            plane.host_runtime_dir
            / "capacity-evidence"
            / f"{str(capability_record['record_id']).removeprefix('sha256:')}.json"
        )
        plane._write_immutable_authority_json(
            plane.host_runtime_dir, evidence_path, capability_record
        )
        path = host_capacity_path(plane.host_runtime_dir, host_id)
        current: Mapping[str, object] | None = None
        retired_writer_predecessor = False
        if path.is_file() and not plane._is_link_like(path):
            # This is both a read and the idempotent completion point for a
            # history-first renewal that crashed after replacing current.json
            # but before extending every sealed live permit.  No fast return is
            # safe until that exact reservation cut has been reconciled.
            try:
                current = reconcile_pending_host_capacity_renewal(
                    plane.host_runtime_dir,
                    host_id=host_id,
                    now=now,
                )
            except ConfigurationError as reconciliation_error:
                try:
                    current = read_host_capacity_predecessor_for_writer_rotation(
                        plane.host_runtime_dir,
                        host_id,
                        now=now,
                    )
                except ConfigurationError:
                    raise reconciliation_error
                retired_writer_predecessor = True
        elif path.exists():
            raise AutopilotError("installed host capacity path is invalid")
        if current is not None and not retired_writer_predecessor:
            try:
                current_expires = parse_time(current.get("expires_at"))
            except Exception as error:
                raise AutopilotError("installed host capacity expiry is invalid") from error
            exact_policy = (
                current.get("capability_source") == capability_source
                and current.get("capability_digest") == capability_digest
                and current.get("declarative") is declarative
                and current.get("max_total_sessions")
                == max_total_sessions
                and current.get("validation_slots")
                == validation_slots
            )
            if exact_policy and current_expires > now + timedelta(minutes=15):
                return current
            if exact_policy and current_expires > now:
                # Polling a long-running host must not rotate the generation
                # out from under its live permits merely because the unchanged
                # policy is nearing expiry.  The host-kernel renewal CAS seals
                # the exact active reservation cut and extends both the
                # capacity record and every still-live permit under the same
                # provider/capacity generation.  Externally evidenced ceilings
                # are never extended beyond their own sealed expiry.
                if expires_at <= current_expires:
                    return current
                return renew_host_capacity_authority(
                    plane.host_runtime_dir,
                    host_id=host_id,
                    capacity_generation=str(current["capacity_generation"]),
                    expected_capacity_record_id=str(current["record_id"]),
                    issued_at=format_time(now),
                    expires_at=format_time(expires_at),
                    capability_source=capability_source,
                    capability_digest=capability_digest,
                    provider_identity_source=APP_SERVER_PROVIDER_IDENTITY_SOURCE,
                    provider_identity_digest=str(provider_identity_digest),
                    actor="autopilot:app-server-capacity-renewal",
                    now=now,
                )
            capacity_epoch = int(current["capacity_epoch"]) + 1
            expected_generation = str(current["capacity_generation"])
        elif current is None:
            capacity_epoch = 1
            expected_generation = None
        else:
            # A successful structural predecessor read is intentionally not an
            # admission capability.  It exists only so the new canonical host
            # writer can rotate provider/capacity authority after a zero-active
            # kernel upgrade without trusting stale writer semantics.
            capacity_epoch = int(current["capacity_epoch"]) + 1
            expected_generation = str(current["capacity_generation"])
        capacity_generation = digest_json(
            {
                "kind": "hive-mind-declarative-host-capacity-generation-v1",
                "host_id": host_id,
                "capacity_epoch": capacity_epoch,
                "previous_generation": expected_generation,
                "capability_digest": capability_digest,
                "capacity_evidence_record_id": capability_record["record_id"],
            }
        )
        return publish_host_capacity(
            plane.host_runtime_dir,
            host_id=host_id,
            capacity_generation=capacity_generation,
            capacity_epoch=capacity_epoch,
            max_total_sessions=max_total_sessions,
            validation_slots=validation_slots,
            issued_at=format_time(now),
            expires_at=format_time(expires_at),
            capability_source=capability_source,
            capability_digest=capability_digest,
            provider_identity_source=APP_SERVER_PROVIDER_IDENTITY_SOURCE,
            provider_identity_digest=str(provider_identity_digest),
            provider_attestation=provider_attestation,
            declarative=declarative,
            now=now,
            expected_generation=expected_generation,
        )


def _registered_repository_checkout(
    plane: ControlPlane,
    binding: Mapping[str, object],
) -> Path | None:
    """Resolve only an authenticated registry binding to an existing checkout.

    The registry deliberately does not grant arbitrary path discovery.  Only
    its monotonic, authenticated ``checkout_roots`` inventory is considered;
    each candidate must independently resolve back to the same coordination
    authority.  Missing/unavailable registered checkouts remain charged.
    """

    coordination_text = binding.get("coordination_dir")
    repository = binding.get("repository")
    transport_digest = binding.get("transport_digest")
    checkout_roots = binding.get("checkout_roots")
    if (
        not isinstance(coordination_text, str)
        or not Path(coordination_text).is_absolute()
        or not isinstance(repository, str)
        or not isinstance(transport_digest, str)
        or AUTHORITY_ID.fullmatch(transport_digest) is None
        or not isinstance(checkout_roots, list)
        or checkout_roots != sorted(set(checkout_roots))
        or any(
            not isinstance(checkout, str) or not Path(checkout).is_absolute()
            for checkout in checkout_roots
        )
    ):
        return None
    coordination = Path(os.path.abspath(coordination_text)).absolute()
    if str(coordination) != coordination_text:
        return None
    for component in reversed((coordination, *coordination.parents)):
        if component.exists() and plane._is_link_like(component):
            return None
    if str(coordination.resolve(strict=False)) != coordination_text:
        return None
    ordered = list(checkout_roots)
    current = str(plane.repo_root)
    if current in ordered:
        ordered.remove(current)
        ordered.insert(0, current)
    for checkout in ordered:
        candidate = Path(checkout)
        if str(Path(os.path.abspath(checkout)).absolute()) != checkout:
            continue
        if any(
            component.exists() and plane._is_link_like(component)
            for component in reversed((candidate, *candidate.parents))
        ):
            continue
        if any(
            component.exists() and plane._is_link_like(component)
            for component in (
                candidate / ".git",
                candidate / ".autopilot",
                candidate / ".autopilot" / "control-plane.json",
            )
        ):
            continue
        if not (candidate / ".git").exists() or not (
            candidate / ".autopilot" / "control-plane.json"
        ).is_file():
            continue
        try:
            if resolve_repository_state_dir(candidate) != coordination:
                continue
        except ConfigurationError:
            continue
        return candidate
    return None


def _recover_expired_app_server_reservations(
    plane: ControlPlane,
    adapter: object,
    *,
    host_id: str,
) -> None:
    """Reconcile every expired permit before rotating the OS-user capacity."""

    if host_id != _canonical_app_server_host_id(plane):
        raise AutopilotError("global host recovery provider identity is invalid")
    foreign_adapters: dict[tuple[str, str], object] = {}

    def repository_resolver(
        repository_binding: Mapping[str, object],
    ) -> Path | None:
        return _registered_repository_checkout(plane, repository_binding)

    def adapter_resolver(
        *,
        reservation: Mapping[str, object],
        repository_binding: Mapping[str, object],
        execution_identity: Mapping[str, object],
        execution_adapter_identity: Mapping[str, object],
        repo_root: Path,
        execution_dir: Path,
    ) -> object | None:
        namespace = execution_identity.get("namespace")
        execution_id = execution_identity.get("execution_id")
        if (
            not isinstance(namespace, str)
            or not isinstance(execution_id, str)
            or AUTHORITY_ID.fullmatch(execution_id) is None
            or reservation.get("execution_id") != execution_id
            or repository_binding.get("repository")
            != execution_identity.get("repository")
            or execution_adapter_identity.get("record_id")
            != reservation.get("execution_adapter_identity_record_id")
            or execution_adapter_identity.get("execution_id") != execution_id
            or execution_adapter_identity.get("execution_namespace") != namespace
            or execution_adapter_identity.get("repository")
            != repository_binding.get("repository")
            or execution_adapter_identity.get("host_id")
            != reservation.get("host_id")
            or execution_adapter_identity.get("provider_generation")
            != reservation.get("provider_generation")
            or execution_adapter_identity.get("provider_epoch")
            != reservation.get("provider_epoch")
        ):
            return None
        try:
            owning_plane = (
                plane
                if (
                    Path(repo_root).resolve() == plane.repo_root.resolve()
                    and execution_id == plane.execution_id
                    and namespace == plane.execution_namespace
                )
                else ControlPlane(
                    Path(repo_root),
                    state_dir=Path(str(repository_binding["coordination_dir"])),
                    execution_namespace=namespace,
                    host_runtime_dir=plane.host_runtime_dir,
                )
            )
            if (
                owning_plane.execution_identity != execution_identity
                or owning_plane.execution_dir.resolve() != Path(execution_dir).resolve()
                or owning_plane.execution_id != execution_id
                or owning_plane.execution_namespace != namespace
                or _canonical_app_server_host_id(owning_plane)
                != reservation.get("host_id")
            ):
                return None
            if owning_plane is plane:
                return adapter
            cache_key = (str(owning_plane.repo_root), owning_plane.execution_id)
            cached = foreign_adapters.get(cache_key)
            if cached is not None:
                return cached
            loaded = _instantiate_app_server_adapter(
                owning_plane,
                host_id=str(reservation["host_id"]),
                wait_seconds=60,
            )
            if loaded is None:
                return None
            foreign_adapters[cache_key] = loaded[0]
            return loaded[0]
        except (AutopilotError, ConfigurationError, OSError, KeyError, TypeError):
            return None

    results: tuple[Mapping[str, object], ...]
    reconciliation_error: BaseException | None = None
    try:
        results = reconcile_global_expired_host_reservations(
            plane.host_runtime_dir,
            adapter_resolver=adapter_resolver,
            repository_root_resolver=repository_resolver,
            actor="autopilot:host-capacity-recovery",
            reason="expired predecessor permit fences host-kernel capacity renewal",
        )
    except BaseException as error:
        reconciliation_error = error
        results = ()
    close_errors: list[str] = []
    for foreign_adapter in foreign_adapters.values():
        close = getattr(foreign_adapter, "close", None)
        if not callable(close):
            close_errors.append("foreign App Server adapter lacks close authority")
            continue
        try:
            close()
        except Exception as error:
            close_errors.append(str(error))
    if reconciliation_error is not None:
        raise reconciliation_error
    if close_errors:
        raise AutopilotError(
            "foreign App Server recovery adapters did not close exactly: "
            + "; ".join(close_errors)
        )
    unresolved = [
        result
        for result in results
        if result.get("state") != "RECOVERED"
    ]
    if unresolved:
        summary = ", ".join(
            f"{item.get('reservation_id')}={item.get('state')}"
            for item in unresolved
        )
        raise AutopilotError(
            "expired host reservations remain charged after global lifecycle "
            f"reconciliation: {summary}"
        )


def _register_current_checkout(plane: ControlPlane) -> Mapping[str, object]:
    """Idempotently expose this exact authenticated clone to host recovery."""

    with plane.host_lock(timeout_seconds=120.0):
        return bind_host_repository_runtime(
            plane.host_runtime_dir,
            repository=str(plane.control["target"]["repository"]),
            transport_digest=str(plane.repository_identity["transport_digest"]),
            coordination_dir=plane.coordination_dir,
            repo_root=plane.repo_root,
            bound_at=format_time(plane.clock()),
        )


def _authenticated_host_lifecycle_observation(
    plane: ControlPlane,
    adapter: object,
    *,
    host_id: str,
    frontier_id: str,
    observation_id: str,
    expected_disposition: StepDisposition,
) -> Mapping[str, object]:
    """Read host facts without allowing the host to mint controller evidence."""

    reader = getattr(adapter, "read_lifecycle_observation", None)
    if not callable(reader):
        raise AutopilotError(
            "authenticated host adapter lacks lifecycle-observation authority"
        )
    observed = reader(
        execution_namespace=plane.execution_namespace,
        execution_id=plane.execution_id,
        execution_dir=plane.execution_dir,
        host_id=host_id,
        frontier_id=frontier_id,
        observation_id=observation_id,
    )
    if not isinstance(observed, Mapping) or set(observed) != (
        HOST_LIFECYCLE_OBSERVATION_FIELDS
    ):
        raise AutopilotError("authenticated host lifecycle observation schema is invalid")
    record = dict(observed)
    material = dict(record)
    sealed_id = material.pop("observation_id", None)
    if (
        record.get("schema_version") != 1
        or record.get("kind") != HOST_LIFECYCLE_OBSERVATION_KIND
        or sealed_id != digest_json(material)
        or sealed_id != observation_id
        or AUTHORITY_ID.fullmatch(str(sealed_id)) is None
        or record.get("execution_namespace") != plane.execution_namespace
        or record.get("execution_id") != plane.execution_id
        or record.get("host_id") != host_id
        or record.get("frontier_id") != frontier_id
        or record.get("disposition") != expected_disposition.value
    ):
        raise AutopilotError("authenticated host lifecycle observation is not current")
    for field in (
        "active_host_threads",
        "active_host_turns",
        "unobserved_host_lifecycle_items",
    ):
        if type(record.get(field)) is not int or int(record[field]) < 0:
            raise AutopilotError(
                f"authenticated host lifecycle observation has invalid {field}"
            )
    try:
        parse_time(record.get("observed_at"))
    except Exception as error:
        raise AutopilotError(
            "authenticated host lifecycle observation timestamp is invalid"
        ) from error
    return record


def _supervisor_fixed_point_verifier(
    plane: ControlPlane,
    adapter: object,
    *,
    host_id: str,
    request: FixedPointVerificationRequest,
) -> FixedPointEvidence:
    """Seal a durable controller fixed point and combine it with host facts."""

    if (
        Path(request.execution_dir).resolve() != plane.execution_dir.resolve()
        or request.execution_id != plane.execution_id
        or request.execution_namespace != plane.execution_namespace
        or request.plan_fingerprint != plane.expected_plan_fingerprint
    ):
        raise AutopilotError("fixed-point request differs from execution authority")
    lifecycle = _authenticated_host_lifecycle_observation(
        plane,
        adapter,
        host_id=host_id,
        frontier_id=request.current_frontier_id,
        observation_id=request.terminal_observation_id,
        expected_disposition=StepDisposition.PLAN_QUIESCENT,
    )
    if any(
        lifecycle[field] != 0
        for field in (
            "active_host_threads",
            "active_host_turns",
            "unobserved_host_lifecycle_items",
        )
    ):
        raise AutopilotError(
            "host lifecycle is not quiescent; controller terminal fence withheld"
        )
    release = plane.current_release()
    if not isinstance(release, Mapping):
        raise AutopilotError("fixed-point verification requires a release")
    release_id = str(release.get("release_id"))
    remote_target_before = plane._remote_ref_sha(
        f"refs/heads/{plane.target_branch}"
    )
    if remote_target_before != release.get("target_sha"):
        raise AutopilotError(
            "fixed-point verification requires a fresh exact remote target observation"
        )
    sealed = plane.plan_terminal_fence()
    if sealed is None:
        if plane._release_issues(release):
            raise AutopilotError("fixed-point verification requires a valid release")
        before = plane.round_authority_snapshot(release_id)
        if (
            before.get("execution_id") != plane.execution_id
            or before.get("execution_namespace") != plane.execution_namespace
            or before.get("release_id") != release_id
            or not isinstance(before.get("authority_digest"), str)
        ):
            raise AutopilotError("controller authority is not fixed-point eligible")
        sealed = plane.seal_plan_quiescent(
            release_id,
            actor="autopilot:supervisor-fixed-point",
            expected_authority_digest=str(before["authority_digest"]),
        )
    required_seal = {
        "schema_version",
        "kind",
        "execution_id",
        "execution_namespace",
        "release_id",
        "admission_epoch",
        "target_sha",
        "target_generation",
        "target_watermark_record_id",
        "plan_fingerprint",
        "authority_digest",
        "controller_observation_id",
        "sealed_by",
        "sealed_at",
        "state",
        "record_id",
    }
    if (
        not isinstance(sealed, Mapping)
        or set(sealed) != required_seal
        or sealed.get("execution_id") != plane.execution_id
        or sealed.get("execution_namespace") != plane.execution_namespace
        or sealed.get("release_id") != release_id
        or sealed.get("plan_fingerprint") != plane.expected_plan_fingerprint
        or sealed.get("target_sha") != release.get("target_sha")
        or sealed.get("target_generation") != release.get("target_generation")
        or sealed.get("target_watermark_record_id")
        != release.get("target_watermark_record_id")
        or sealed.get("state") != "PLAN_QUIESCENT"
        or not isinstance(sealed.get("controller_observation_id"), str)
    ):
        raise AutopilotError("controller fixed-point seal is malformed")
    target_watermark = plane.repository_target_watermark()
    if (
        target_watermark.get("target_sha") != sealed.get("target_sha")
        or target_watermark.get("target_generation")
        != sealed.get("target_generation")
        or target_watermark.get("record_id")
        != sealed.get("target_watermark_record_id")
    ):
        raise AutopilotError(
            "controller fixed-point seal differs from repository target generation"
        )
    terminal_snapshot = plane.round_authority_snapshot(release_id)
    stable_authority = dict(terminal_snapshot)
    stable_authority.pop("authority_digest", None)
    stable_authority.pop("publication_transaction_status", None)
    stable_authority.pop("observed_at", None)
    if stable_authority.get("plan_terminal_fence") != sealed:
        raise AutopilotError(
            "controller fixed-point seal is not the live terminal authority"
        )
    # The seal records the digest of the exact zero-activity cut immediately
    # before the terminal fence was installed.  Reconstruct only that documented
    # transition; every other field must still be byte-for-byte authoritative.
    stable_authority["plan_terminal_fence"] = None
    if digest_json(stable_authority) != sealed.get("authority_digest"):
        raise AutopilotError(
            "controller authority changed after the fixed-point cut"
        )
    status = terminal_snapshot.get("status")
    collections = {
        "claims": terminal_snapshot.get("active_claims"),
        "launches": terminal_snapshot.get("active_write_launch_reservations"),
        "hosts": terminal_snapshot.get("active_host_reservations"),
        "global": terminal_snapshot.get("execution_global_host_reservations"),
        "conflicts": terminal_snapshot.get("conflicting_global_reservations"),
        "reconciliation": terminal_snapshot.get("reconciliation_obligations"),
        "host effects": terminal_snapshot.get("host_effect_obligations"),
    }
    if (
        not isinstance(status, Mapping)
        or status.get("complete") is not True
        or any(not isinstance(value, list) for value in collections.values())
        or any(value for value in collections.values())
        or terminal_snapshot.get("active_validation_lease") is not None
        or terminal_snapshot.get("active_publication_count") != 0
        or terminal_snapshot.get("active_host_effect_count") != 0
    ):
        raise AutopilotError(
            "live controller authority is not a durable zero-activity fixed point"
        )
    remote_target_after = plane._remote_ref_sha(
        f"refs/heads/{plane.target_branch}"
    )
    if remote_target_after != sealed.get("target_sha"):
        raise AutopilotError(
            "remote target changed across the controller fixed-point seal"
        )
    return FixedPointEvidence.create(
        execution_id=plane.execution_id,
        execution_namespace=plane.execution_namespace,
        plan_fingerprint=plane.expected_plan_fingerprint,
        initial_frontier_id=request.initial_frontier_id,
        current_frontier_id=request.current_frontier_id,
        terminal_observation_id=request.terminal_observation_id,
        release_authority_id=release_id,
        controller_observation_id=str(sealed["controller_observation_id"]),
        dag_complete=True,
        active_claims=len(collections["claims"]),
        active_launches=len(collections["launches"]),
        active_sidecars=len(collections["hosts"]),
        active_validation_leases=(
            1 if terminal_snapshot["active_validation_lease"] is not None else 0
        ),
        active_publication_transactions=int(
            terminal_snapshot["active_publication_count"]
        ),
        active_global_reservations=len(collections["global"]),
        host_lifecycle_authenticated=True,
        active_host_threads=int(lifecycle["active_host_threads"]),
        active_host_turns=int(lifecycle["active_host_turns"]),
        unobserved_host_lifecycle_items=int(
            lifecycle["unobserved_host_lifecycle_items"]
        ),
    )


def _runtime_migration_plan(
    repo_root: Path,
    coordination_dir: Path,
    *,
    now: datetime,
) -> Mapping[str, object]:
    """Build one deterministic, read-only plan for both migration reducers."""

    repository_identity = runtime_repository_identity(repo_root)
    if not isinstance(repository_identity, Mapping):
        raise AutopilotError(
            "runtime migration planning requires canonical repository identity"
        )
    semantic_roots, semantic_entries = _legacy_semantic_inventory(
        repo_root,
        coordination_dir,
        repository_identity=repository_identity,
    )
    bootstrap_roots, bootstrap_sources = _inspect_noncanonical_authority(
        repo_root,
        coordination_dir,
        now=now,
    )
    semantic_inventory = [str(item) for item in semantic_roots]
    bootstrap_inventory = [str(item) for item in bootstrap_roots]
    if semantic_inventory != bootstrap_inventory:
        raise AutopilotError(
            "runtime migration worktree inventory changed during dry-run"
        )
    semantic_material = _legacy_semantic_material(
        repository_identity,
        semantic_inventory,
        semantic_entries,
    )
    bootstrap_material = _migration_material(
        repository_identity,
        bootstrap_inventory,
        bootstrap_sources,
    )
    semantic_id = digest_json(semantic_material)
    bootstrap_id = digest_json(bootstrap_material)
    planned_semantic = [
        {
            key: value
            for key, value in _plan_legacy_semantic_paths(
                coordination_dir, semantic_id, entry
            ).items()
            if key not in {"source_bytes_base64", "rollback"}
        }
        for entry in semantic_entries
    ]
    planned_bootstrap = [
        {
            key: value
            for key, value in _plan_migration_paths(
                coordination_dir, bootstrap_id, source
            ).items()
            if key not in {"source_bytes_base64", "rollback"}
        }
        for source in bootstrap_sources
    ]
    operation_material: dict[str, object] = {
        "kind": "hive-mind-runtime-migration-operation-key-v1",
        "repository_identity": dict(repository_identity),
        "coordination_dir": str(coordination_dir),
        "worktree_inventory": semantic_inventory,
        "semantic_reconciliation_id": semantic_id,
        "bootstrap_migration_id": bootstrap_id,
    }
    material: dict[str, object] = {
        "schema_version": 1,
        "kind": "hive-mind-runtime-migration-plan-v1",
        "operation_id": digest_json(operation_material),
        "repository_identity": dict(repository_identity),
        "coordination_dir": str(coordination_dir),
        "worktree_inventory": semantic_inventory,
        "semantic_reconciliation_id": semantic_id,
        "semantic_entries": planned_semantic,
        "bootstrap_migration_id": bootstrap_id,
        "bootstrap_sources": planned_bootstrap,
        "rollback_disposition": "ABORT_AND_PRESERVE_ONLY",
    }
    return _validated_runtime_migration_plan(
        {**material, "plan_id": digest_json(material)}
    )


def _validated_runtime_migration_plan(
    value: object,
) -> Mapping[str, object]:
    fields = {
        "schema_version",
        "kind",
        "operation_id",
        "repository_identity",
        "coordination_dir",
        "worktree_inventory",
        "semantic_reconciliation_id",
        "semantic_entries",
        "bootstrap_migration_id",
        "bootstrap_sources",
        "rollback_disposition",
        "plan_id",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise AutopilotError("runtime migration plan schema is ambiguous")
    material = dict(value)
    plan_id = material.pop("plan_id", None)
    operation_material = {
        "kind": "hive-mind-runtime-migration-operation-key-v1",
        "repository_identity": value.get("repository_identity"),
        "coordination_dir": value.get("coordination_dir"),
        "worktree_inventory": value.get("worktree_inventory"),
        "semantic_reconciliation_id": value.get(
            "semantic_reconciliation_id"
        ),
        "bootstrap_migration_id": value.get("bootstrap_migration_id"),
    }
    if (
        value.get("schema_version") != 1
        or value.get("kind") != "hive-mind-runtime-migration-plan-v1"
        or value.get("rollback_disposition") != "ABORT_AND_PRESERVE_ONLY"
        or not isinstance(value.get("repository_identity"), Mapping)
        or not isinstance(value.get("coordination_dir"), str)
        or not Path(str(value["coordination_dir"])).is_absolute()
        or not isinstance(value.get("worktree_inventory"), list)
        or any(
            not isinstance(item, str) or not Path(item).is_absolute()
            for item in value["worktree_inventory"]
        )
        or not isinstance(value.get("semantic_entries"), list)
        or not all(
            isinstance(item, Mapping) for item in value["semantic_entries"]
        )
        or not isinstance(value.get("bootstrap_sources"), list)
        or not all(
            isinstance(item, Mapping) for item in value["bootstrap_sources"]
        )
        or any(
            AUTHORITY_ID.fullmatch(str(value.get(field))) is None
            for field in (
                "operation_id",
                "semantic_reconciliation_id",
                "bootstrap_migration_id",
            )
        )
        or value.get("operation_id") != digest_json(operation_material)
        or plan_id != digest_json(material)
    ):
        raise AutopilotError("runtime migration plan is invalid")
    return dict(value)


def _runtime_migration_operation_path(
    coordination_dir: Path, operation_id: str
) -> Path:
    if AUTHORITY_ID.fullmatch(operation_id) is None:
        raise AutopilotError("runtime migration operation id is invalid")
    return (
        coordination_dir
        / RUNTIME_MIGRATION_OPERATION_ROOT
        / (_compact_authority_path_id(operation_id) + ".op.json")
    )


def _validated_runtime_migration_operation(
    value: object,
    *,
    plan: Mapping[str, object] | None = None,
) -> Mapping[str, object]:
    fields = {
        "schema_version",
        "kind",
        "status",
        "operation_id",
        "plan",
        "actor",
        "prepared_at",
        "record_id",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise AutopilotError("runtime migration operation schema is ambiguous")
    material = dict(value)
    record_id = material.pop("record_id", None)
    embedded = value.get("plan")
    validated_plan = _validated_runtime_migration_plan(embedded)
    if (
        value.get("schema_version") != 1
        or value.get("kind") != RUNTIME_MIGRATION_OPERATION_KIND
        or value.get("status") != "PREPARED"
        or value.get("operation_id") != validated_plan.get("operation_id")
        or AUTHORITY_ID.fullmatch(str(value.get("operation_id"))) is None
        or not isinstance(value.get("actor"), str)
        or not str(value["actor"]).strip()
        or record_id != digest_json(material)
    ):
        raise AutopilotError("runtime migration operation is invalid")
    try:
        parse_time(value.get("prepared_at"))
    except Exception as error:
        raise AutopilotError(
            "runtime migration operation timestamp is invalid"
        ) from error
    if plan is not None and validated_plan != plan:
        raise AutopilotError("runtime migration operation plan changed")
    return dict(value)


def _install_runtime_migration_operation(
    coordination_dir: Path,
    plan: Mapping[str, object],
    *,
    actor: str,
    prepared_at: str,
) -> Mapping[str, object]:
    path = _runtime_migration_operation_path(
        coordination_dir, str(plan["operation_id"])
    )
    if path.exists() or _is_link_like(path):
        return _validated_runtime_migration_operation(
            read_strict_canonical_json(path, label="runtime migration operation"),
            plan=plan,
        )
    material: dict[str, object] = {
        "schema_version": 1,
        "kind": RUNTIME_MIGRATION_OPERATION_KIND,
        "status": "PREPARED",
        "operation_id": plan["operation_id"],
        "plan": dict(plan),
        "actor": actor,
        "prepared_at": prepared_at,
    }
    operation = {**material, "record_id": digest_json(material)}
    exclusive_write_json_or_identical(path, operation)
    return _validated_runtime_migration_operation(
        read_strict_canonical_json(path, label="runtime migration operation"),
        plan=plan,
    )


def _runtime_migration_abort_path(
    coordination_dir: Path, operation_id: str
) -> Path:
    return (
        coordination_dir
        / RUNTIME_MIGRATION_OPERATION_ROOT
        / (_compact_authority_path_id(operation_id) + ".abort.json")
    )


def _runtime_migration_abort(
    coordination_dir: Path,
    operation: Mapping[str, object],
) -> Mapping[str, object] | None:
    path = _runtime_migration_abort_path(
        coordination_dir, str(operation["operation_id"])
    )
    if not path.exists() and not _is_link_like(path):
        return None
    value = read_strict_canonical_json(
        path, label="runtime migration abort receipt"
    )
    fields = {
        "schema_version",
        "kind",
        "status",
        "operation_id",
        "operation_record_id",
        "inverse_restoration_permitted",
        "retired_authority_preserved",
        "actor",
        "reason",
        "recorded_at",
        "record_id",
    }
    material = dict(value) if isinstance(value, Mapping) else {}
    record_id = material.pop("record_id", None)
    if (
        not isinstance(value, Mapping)
        or set(value) != fields
        or value.get("schema_version") != 1
        or value.get("kind") != RUNTIME_MIGRATION_ABORT_KIND
        or value.get("status") != "ABORTED_FENCED"
        or value.get("operation_id") != operation.get("operation_id")
        or value.get("operation_record_id") != operation.get("record_id")
        or value.get("inverse_restoration_permitted") is not False
        or value.get("retired_authority_preserved") is not True
        or not isinstance(value.get("actor"), str)
        or not str(value["actor"]).strip()
        or not isinstance(value.get("reason"), str)
        or not str(value["reason"]).strip()
        or record_id != digest_json(material)
    ):
        raise AutopilotError("runtime migration abort receipt is invalid")
    try:
        parse_time(value.get("recorded_at"))
    except Exception as error:
        raise AutopilotError(
            "runtime migration abort timestamp is invalid"
        ) from error
    return dict(value)


def _runtime_migration_completion_path(
    coordination_dir: Path, operation_id: str
) -> Path:
    return (
        coordination_dir
        / RUNTIME_MIGRATION_OPERATION_ROOT
        / (_compact_authority_path_id(operation_id) + ".complete.json")
    )


def _validated_runtime_migration_completion(
    value: object,
    *,
    operation: Mapping[str, object],
    semantic_reconciliation_id: str | None = None,
    bootstrap_migration_id: str | None = None,
    ready_record_id: str | None = None,
) -> Mapping[str, object]:
    fields = {
        "schema_version",
        "kind",
        "status",
        "operation_id",
        "operation_record_id",
        "semantic_reconciliation_id",
        "bootstrap_migration_id",
        "ready_record_id",
        "actor",
        "completed_at",
        "record_id",
    }
    material = dict(value) if isinstance(value, Mapping) else {}
    record_id = material.pop("record_id", None)
    if (
        not isinstance(value, Mapping)
        or set(value) != fields
        or value.get("schema_version") != 1
        or value.get("kind") != RUNTIME_MIGRATION_COMPLETE_KIND
        or value.get("status") != "COMPLETE"
        or value.get("operation_id") != operation.get("operation_id")
        or value.get("operation_record_id") != operation.get("record_id")
        or AUTHORITY_ID.fullmatch(
            str(value.get("semantic_reconciliation_id"))
        )
        is None
        or AUTHORITY_ID.fullmatch(str(value.get("bootstrap_migration_id")))
        is None
        or AUTHORITY_ID.fullmatch(str(value.get("ready_record_id"))) is None
        or (
            semantic_reconciliation_id is not None
            and value.get("semantic_reconciliation_id")
            != semantic_reconciliation_id
        )
        or (
            bootstrap_migration_id is not None
            and value.get("bootstrap_migration_id") != bootstrap_migration_id
        )
        or (
            ready_record_id is not None
            and value.get("ready_record_id") != ready_record_id
        )
        or not isinstance(value.get("actor"), str)
        or not str(value["actor"]).strip()
        or record_id != digest_json(material)
    ):
        raise AutopilotError("runtime migration completion is invalid")
    try:
        parse_time(value.get("completed_at"))
    except Exception as error:
        raise AutopilotError(
            "runtime migration completion timestamp is invalid"
        ) from error
    return dict(value)


def _complete_runtime_migration_operation(
    coordination_dir: Path,
    operation: Mapping[str, object],
    *,
    semantic_reconciliation_id: str,
    bootstrap_migration_id: str,
    ready_record_id: str,
    actor: str,
    completed_at: str,
) -> Mapping[str, object]:
    path = _runtime_migration_completion_path(
        coordination_dir, str(operation["operation_id"])
    )
    if path.exists() or _is_link_like(path):
        return _validated_runtime_migration_completion(
            read_strict_canonical_json(
                path, label="runtime migration completion"
            ),
            operation=operation,
            semantic_reconciliation_id=semantic_reconciliation_id,
            bootstrap_migration_id=bootstrap_migration_id,
            ready_record_id=ready_record_id,
        )
    material: dict[str, object] = {
        "schema_version": 1,
        "kind": RUNTIME_MIGRATION_COMPLETE_KIND,
        "status": "COMPLETE",
        "operation_id": operation["operation_id"],
        "operation_record_id": operation["record_id"],
        "semantic_reconciliation_id": semantic_reconciliation_id,
        "bootstrap_migration_id": bootstrap_migration_id,
        "ready_record_id": ready_record_id,
        "actor": actor,
        "completed_at": completed_at,
    }
    completion = {**material, "record_id": digest_json(material)}
    exclusive_write_json_or_identical(path, completion)
    return _validated_runtime_migration_completion(
        read_strict_canonical_json(path, label="runtime migration completion"),
        operation=operation,
        semantic_reconciliation_id=semantic_reconciliation_id,
        bootstrap_migration_id=bootstrap_migration_id,
        ready_record_id=ready_record_id,
    )


def _active_runtime_migration_operation(
    repo_root: Path,
    coordination_dir: Path,
) -> Mapping[str, object] | None:
    operation_root = coordination_dir / RUNTIME_MIGRATION_OPERATION_ROOT
    if not operation_root.exists() and not _is_link_like(operation_root):
        return None
    safe_root = _reject_link_components(
        operation_root, label="runtime migration operation directory"
    )
    if not safe_root.is_dir():
        raise AutopilotError("runtime migration operation path is not a directory")
    repository_identity = runtime_repository_identity(repo_root)
    active: list[Mapping[str, object]] = []
    for path in sorted(safe_root.glob("*.op.json"), key=lambda item: item.name):
        operation = _validated_runtime_migration_operation(
            read_strict_canonical_json(path, label="runtime migration operation")
        )
        if path != _runtime_migration_operation_path(
            coordination_dir, str(operation["operation_id"])
        ):
            raise AutopilotError("runtime migration operation path is invalid")
        plan = operation["plan"]
        if (
            not isinstance(plan, Mapping)
            or plan.get("repository_identity") != repository_identity
            or plan.get("coordination_dir") != str(coordination_dir)
        ):
            raise AutopilotError(
                "runtime migration operation belongs to another authority"
            )
        completion_path = _runtime_migration_completion_path(
            coordination_dir, str(operation["operation_id"])
        )
        if completion_path.exists() or _is_link_like(completion_path):
            if not isinstance(plan, Mapping):
                raise AutopilotError(
                    "runtime migration completion lost its sealed plan"
                )
            ready_chain = validate_repository_runtime_ready_chain(
                repo_root, coordination_dir
            )
            ready = ready_chain.get("ready")
            if not isinstance(ready, Mapping):
                raise AutopilotError(
                    "runtime migration completion lacks a valid READY chain"
                )
            _validated_runtime_migration_completion(
                read_strict_canonical_json(
                    completion_path, label="runtime migration completion"
                ),
                operation=operation,
                semantic_reconciliation_id=str(
                    plan.get("semantic_reconciliation_id")
                ),
                bootstrap_migration_id=str(plan.get("bootstrap_migration_id")),
                ready_record_id=str(ready.get("record_id")),
            )
            continue
        if _runtime_migration_abort(coordination_dir, operation) is None:
            active.append(operation)
    if len(active) > 1:
        raise AutopilotError(
            "multiple nonterminal runtime migration operations are installed"
        )
    return active[0] if active else None


def _verify_runtime_migration(
    repo_root: Path, coordination_dir: Path
) -> Mapping[str, object]:
    ready_path = coordination_dir / RUNTIME_READY_MANIFEST
    if ready_path.exists() or _is_link_like(ready_path):
        return {
            "schema_version": 1,
            "kind": "hive-mind-runtime-migration-verification-v1",
            "status": "READY",
            "ready_chain": dict(
                validate_repository_runtime_ready_chain(
                    repo_root, coordination_dir
                )
            ),
        }
    repository_identity = runtime_repository_identity(repo_root)
    if not isinstance(repository_identity, Mapping):
        raise AutopilotError(
            "runtime migration verification requires repository identity"
        )
    current_inventory = [str(item) for item in _linked_worktree_roots(repo_root)]
    manifests: dict[str, object] = {}
    aborted_operations: list[Mapping[str, object]] = []
    operation_root = coordination_dir / RUNTIME_MIGRATION_OPERATION_ROOT
    if operation_root.exists() or _is_link_like(operation_root):
        safe_operation_root = _reject_link_components(
            operation_root, label="runtime migration operation directory"
        )
        if not safe_operation_root.is_dir():
            raise AutopilotError(
                "runtime migration operation path is not a directory"
            )
        for path in sorted(
            safe_operation_root.glob("*.op.json"),
            key=lambda item: item.name,
        ):
            operation = _validated_runtime_migration_operation(
                read_strict_canonical_json(
                    path, label="runtime migration operation"
                )
            )
            if path != _runtime_migration_operation_path(
                coordination_dir, str(operation["operation_id"])
            ):
                raise AutopilotError("runtime migration operation path is invalid")
            abort = _runtime_migration_abort(coordination_dir, operation)
            if abort is not None:
                aborted_operations.append(
                    {"operation": dict(operation), "abort": dict(abort)}
                )
    semantic_path = coordination_dir / LEGACY_SEMANTIC_RECONCILIATION_MANIFEST
    if semantic_path.exists() or semantic_path.is_symlink():
        semantic = read_strict_canonical_json(
            semantic_path, label="legacy semantic reconciliation manifest"
        )
        if not isinstance(semantic, Mapping) or semantic.get("status") != "COMPLETE":
            raise AutopilotError(
                "legacy semantic reconciliation is not complete"
            )
        semantic_inventory = semantic.get("worktree_inventory")
        if not isinstance(semantic_inventory, list) or any(
            not isinstance(item, str) or not Path(item).is_absolute()
            for item in semantic_inventory
        ):
            raise AutopilotError(
                "legacy semantic reconciliation inventory is invalid"
            )
        _validate_legacy_semantic_manifest(
            semantic,
            repository_identity=repository_identity,
            inventory=semantic_inventory,
            coordination_dir=coordination_dir,
        )
        manifests["semantic_reconciliation"] = dict(semantic)
    bootstrap_path = coordination_dir / RUNTIME_BOOTSTRAP_MANIFEST
    if bootstrap_path.exists() or bootstrap_path.is_symlink():
        bootstrap = read_strict_canonical_json(
            bootstrap_path, label="runtime bootstrap migration manifest"
        )
        if not isinstance(bootstrap, Mapping) or bootstrap.get("status") != "COMPLETE":
            raise AutopilotError("runtime bootstrap migration is not complete")
        bootstrap_inventory = bootstrap.get("worktree_inventory")
        if not isinstance(bootstrap_inventory, list) or any(
            not isinstance(item, str) or not Path(item).is_absolute()
            for item in bootstrap_inventory
        ):
            raise AutopilotError(
                "runtime bootstrap migration inventory is invalid"
            )
        _validate_migration_manifest(
            bootstrap,
            repository_identity=repository_identity,
            inventory=bootstrap_inventory,
            coordination_dir=coordination_dir,
        )
        manifests["bootstrap_migration"] = dict(bootstrap)
    if not manifests and not aborted_operations:
        raise AutopilotError("no applied runtime migration evidence exists")
    return {
        "schema_version": 1,
        "kind": "hive-mind-runtime-migration-verification-v1",
        "status": (
            "ABORTED_FENCED"
            if aborted_operations
            else "PRE_READY_COMPLETE"
        ),
        "manifests": manifests,
        "aborted_operations": aborted_operations,
        "current_worktree_inventory": current_inventory,
    }


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    adapter_to_close: object | None = None
    try:
        if args.command in {"dag-rounds", "dag-lint"}:
            # Plan-only analysis: deliberately does not construct a live control
            # plane so any repository's plan.json can be compiled and linted.
            return run_dag_standard_command(args)
        if args.command == "host-runtime-init":
            identity = initialize_host_runtime(args.host_runtime_dir)
            canonical_host_id = digest_json(
                {
                    "kind": "hive-mind-codex-app-server-provider-v1",
                    "machine_user_id": identity["machine_user_id"],
                }
            )
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "hive-mind-host-runtime-initialization-v1",
                        "actor": args.actor,
                        "host_runtime_dir": str(
                            resolve_host_runtime_dir(args.host_runtime_dir)
                        ),
                        "identity": dict(identity),
                        "canonical_app_server_host_id": canonical_host_id,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "host-runtime-upgrade":
            # Like execution-kernel upgrade, this is an explicit bootstrap
            # aperture.  Every ordinary host writer must reject a stale kernel;
            # only this zero-active-reservation CAS may replace it.
            identity = upgrade_host_runtime_kernel(
                args.host_runtime_dir,
                actor=args.actor,
                reason=args.reason,
                expected_host_kernel_generation=(
                    args.expected_host_kernel_generation
                ),
            )
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "hive-mind-host-kernel-upgrade-result-v1",
                        "host_runtime_dir": str(
                            resolve_host_runtime_dir(args.host_runtime_dir)
                        ),
                        "actor": args.actor,
                        "reason": args.reason,
                        "identity": dict(identity),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "host-runtime-recover-torn-tail":
            receipt = recover_host_authority_jsonl_torn_tail(
                args.host_runtime_dir,
                ledger_kind=args.ledger_kind,
                actor=args.actor,
                reason=args.reason,
                host_id=args.host_id,
            )
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "hive-mind-host-torn-tail-recovery-result-v1",
                        "host_runtime_dir": str(
                            resolve_host_runtime_dir(args.host_runtime_dir)
                        ),
                        "ledger_kind": args.ledger_kind,
                        "host_id": args.host_id,
                        "outcome": "RECOVERED" if receipt is not None else "CLEAN",
                        "receipt": dict(receipt) if receipt is not None else None,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "execution-kernel-upgrade":
            # A kernel mismatch is exactly what this command is authorized to
            # repair.  Do not construct ControlPlane first: ordinary plane
            # construction authenticates the installed kernel and must reject
            # the new checkout until this zero-activity CAS succeeds.
            repo_root = Path(args.repo_root).resolve()
            coordination_dir = resolve_repository_state_dir(
                repo_root, args.state_dir
            )
            host_runtime_dir = resolve_host_runtime_dir(args.host_runtime_dir)
            identity = upgrade_execution_namespace_kernel(
                repo_root,
                coordination_dir,
                host_runtime_dir=host_runtime_dir,
                execution_namespace=args.execution_namespace,
                execution_id=args.execution_id,
                actor=args.actor,
                reason=args.reason,
                expected_identity_record_id=args.expected_identity_record_id,
            )
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "hive-mind-execution-kernel-upgrade-result-v1",
                        "execution_namespace": args.execution_namespace,
                        "execution_id": args.execution_id,
                        "coordination_dir": str(coordination_dir),
                        "host_runtime_dir": str(host_runtime_dir),
                        "actor": args.actor,
                        "reason": args.reason,
                        "identity": dict(identity),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "runtime-authority-migrate" and args.mode != "apply":
            repo_root = Path(args.repo_root).resolve()
            coordination_dir = resolve_repository_state_dir(
                repo_root, args.state_dir
            )
            if args.mode == "verify":
                print(
                    json.dumps(
                        _verify_runtime_migration(repo_root, coordination_dir),
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 0
            ready_path = coordination_dir / RUNTIME_READY_MANIFEST
            if ready_path.exists() or _is_link_like(ready_path):
                if args.mode == "rollback-before-ready":
                    raise AutopilotError(
                        "rollback-before-ready is forbidden after READY publication"
                    )
                print(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "kind": "hive-mind-runtime-migration-dry-run-v1",
                            "status": "ALREADY_READY",
                            "plan": None,
                            "resumes_operation": None,
                            "verification": _verify_runtime_migration(
                                repo_root, coordination_dir
                            ),
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 0
            existing_operation = _active_runtime_migration_operation(
                repo_root, coordination_dir
            )
            plan = (
                dict(existing_operation["plan"])
                if isinstance(existing_operation, Mapping)
                and isinstance(existing_operation.get("plan"), Mapping)
                else _runtime_migration_plan(
                    repo_root,
                    coordination_dir,
                    now=datetime.now(UTC),
                )
            )
            if args.mode == "dry-run":
                print(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "kind": "hive-mind-runtime-migration-dry-run-v1",
                            "status": "DRY_RUN",
                            "plan": dict(plan),
                            "resumes_operation": (
                                dict(existing_operation)
                                if isinstance(existing_operation, Mapping)
                                else None
                            ),
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 0
            if not isinstance(args.reason, str) or not args.reason.strip():
                raise AutopilotError(
                    "rollback-before-ready requires a nonempty --reason"
                )
            host_runtime_dir = resolve_host_runtime_dir(args.host_runtime_dir)
            host_lock = host_runtime_dir / "locks" / "host-authority.lock"
            with runtime_file_lock(host_lock, timeout_seconds=120.0):
                read_current_host_runtime_identity(host_runtime_dir)
                with runtime_file_lock(
                    coordination_dir / RUNTIME_BOOTSTRAP_LOCK,
                    timeout_seconds=120.0,
                ):
                    recorded_at = format_time(datetime.now(UTC))
                    locked_operation = _active_runtime_migration_operation(
                        repo_root, coordination_dir
                    )
                    if (
                        isinstance(locked_operation, Mapping)
                        and locked_operation.get("plan") != plan
                    ):
                        raise AutopilotError(
                            "runtime migration operation changed while rollback waited"
                        )
                    operation = (
                        locked_operation
                        if isinstance(locked_operation, Mapping)
                        else _install_runtime_migration_operation(
                            coordination_dir,
                            plan,
                            actor=args.actor,
                            prepared_at=recorded_at,
                        )
                    )
                    existing_abort = _runtime_migration_abort(
                        coordination_dir, operation
                    )
                    if existing_abort is None:
                        abort_material: dict[str, object] = {
                            "schema_version": 1,
                            "kind": RUNTIME_MIGRATION_ABORT_KIND,
                            "status": "ABORTED_FENCED",
                            "operation_id": operation["operation_id"],
                            "operation_record_id": operation["record_id"],
                            "inverse_restoration_permitted": False,
                            "retired_authority_preserved": True,
                            "actor": args.actor,
                            "reason": args.reason,
                            "recorded_at": recorded_at,
                        }
                        abort = {
                            **abort_material,
                            "record_id": digest_json(abort_material),
                        }
                        exclusive_write_json_or_identical(
                            _runtime_migration_abort_path(
                                coordination_dir,
                                str(operation["operation_id"]),
                            ),
                            abort,
                        )
                        existing_abort = _runtime_migration_abort(
                            coordination_dir, operation
                        )
                    if existing_abort is None:
                        raise AutopilotError(
                            "runtime migration abort receipt was not installed"
                        )
            print(json.dumps(existing_abort, indent=2, sort_keys=True))
            return 0
        execution_namespace = (
            args.namespace if args.command == "execution-init" else args.execution_namespace
        )
        plane = ControlPlane(
            Path(args.repo_root),
            state_dir=args.state_dir,
            execution_namespace=execution_namespace,
            host_runtime_dir=args.host_runtime_dir,
        )
        if args.command == "execution-init":
            with plane.host_lock(timeout_seconds=120.0):
                bind_host_repository_runtime(
                    plane.host_runtime_dir,
                    repository=str(plane.control["target"]["repository"]),
                    coordination_dir=plane.coordination_dir,
                    repo_root=plane.repo_root,
                    transport_digest=str(
                        plane.repository_identity["transport_digest"]
                    ),
                    bound_at=format_time(plane.clock()),
                )
                with plane.arbiter_lock(timeout_seconds=120.0):
                    directory = initialize_execution_namespace(
                        plane.coordination_dir, plane.execution_identity
                    )
                    transport = plane.bind_canonical_remote_transport_identity()
            # Remote transport is deliberately observed without holding either
            # host or repository authority.  The short second cut below rechecks
            # the exact transport and installs only this immutable ref receipt.
            plane.assert_canonical_remote_transport_identity()
            target_reference = f"refs/heads/{plane.target_branch}"
            target_sha = plane._remote_ref_sha(target_reference)
            if target_sha is None:
                raise AutopilotError(
                    "execution initialization cannot observe the canonical target ref"
                )
            target_observation = {
                "schema_version": 1,
                "kind": "hive-mind-initial-remote-target-observation-v1",
                "repository": str(plane.control["target"]["repository"]),
                "repository_transport_digest": str(
                    plane.repository_identity["transport_digest"]
                ),
                "target_ref": target_reference,
                "target_sha": target_sha,
                "transport_record_id": transport["record_id"],
                "execution_id": plane.execution_id,
                "execution_namespace": plane.execution_namespace,
                "observed_at": format_time(plane.clock()),
            }
            target_observation = {
                **target_observation,
                "record_id": digest_json(target_observation),
            }
            target_observation_id = str(target_observation["record_id"])
            with plane.host_lock(timeout_seconds=120.0):
                with plane.arbiter_lock(timeout_seconds=120.0):
                    plane.assert_canonical_remote_transport_identity()
                    if plane._remote_ref_sha(target_reference) != target_sha:
                        raise AutopilotError(
                            "canonical target changed during execution initialization; "
                            "retry with a fresh remote observation"
                        )
                    watermark = plane.initialize_repository_target_watermark(
                        target_sha=target_sha,
                        source_observation=target_observation,
                        actor=args.actor,
                    )
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "hive-mind-execution-initialization-v1",
                        "actor": args.actor,
                        "execution_namespace": plane.execution_namespace,
                        "execution_id": plane.execution_id,
                        "execution_dir": str(directory),
                        "remote_transport_record_id": transport["record_id"],
                        "target_observation_id": target_observation_id,
                        "target_sha": target_sha,
                        "target_generation": watermark["target_generation"],
                        "target_watermark_record_id": watermark["record_id"],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command != "runtime-authority-migrate":
            require_execution_namespace(
                plane.coordination_dir, plane.execution_identity
            )
            _register_current_checkout(plane)
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
            if args.plan:
                plane.authenticate_dispatch_plan_assertion(Path(args.plan))
            capability, adapter, adapter_detail, adapter_identity = _load_host_adapter(
                plane,
                adapter_name=args.host_adapter,
                host_id=args.host_id,
                wait_seconds=args.wait_seconds,
            )
            adapter_to_close = adapter
            if (
                capability is not HostCapability.AUTHENTICATED_LIFECYCLE
                or adapter is None
                or not isinstance(adapter_identity, Mapping)
            ):
                raise AutopilotError(
                    "dispatcher requires crash-exact autonomous host authority: "
                    + adapter_detail
                )
            result = plane.dispatch(
                actor=args.actor,
                host_id=args.host_id,
                execution_adapter_identity=adapter_identity,
                requested_nodes=args.node,
            )
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
                        claim_authority_class="HOSTED_LAUNCH",
                        launch_instruction_id=args.launch_instruction_id,
                        resource_key=args.resource_key,
                        authority_epoch=args.authority_epoch,
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
                        claim_id=args.claim_id,
                        claim_authority_class="HOSTED_LAUNCH",
                        launch_instruction_id=args.launch_instruction_id,
                        resource_key=args.resource_key,
                        authority_epoch=args.authority_epoch,
                        lease_minutes=args.lease_minutes,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "release":
            plane.release(
                args.node_id,
                args.owner,
                claim_id=args.claim_id,
                claim_authority_class="HOSTED_LAUNCH",
                launch_instruction_id=args.launch_instruction_id,
                resource_key=args.resource_key,
                authority_epoch=args.authority_epoch,
                reason=args.reason,
            )
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
            print(
                plane.complete(
                    args.node_id,
                    args.owner,
                    receipt,
                    claim_id=args.claim_id,
                    claim_authority_class="HOSTED_LAUNCH",
                    launch_instruction_id=args.launch_instruction_id,
                    resource_key=args.resource_key,
                    authority_epoch=args.authority_epoch,
                )
            )
            return 0
        if args.command == "fail":
            print(
                json.dumps(
                    plane.fail(
                        args.node_id,
                        args.owner,
                        claim_id=args.claim_id,
                        claim_authority_class="HOSTED_LAUNCH",
                        launch_instruction_id=args.launch_instruction_id,
                        resource_key=args.resource_key,
                        authority_epoch=args.authority_epoch,
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
        if args.command == "snapshot-observation-begin":
            print(
                json.dumps(
                    plane.begin_github_snapshot_observation(actor=args.actor),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "install-github-snapshot":
            print(
                plane.install_github_snapshot(
                    Path(args.file) if args.file else None,
                    observation_id=args.observation_id,
                )
            )
            return 0
        if args.command == "render-prompt":
            # Complete any crash-pending same-policy renewal before rendering an
            # executable host identity. The prompt itself remains read-only; one
            # snapshot cache avoids replaying thousands of Git reads.
            with plane.host_lock(timeout_seconds=120.0):
                capacity = reconcile_pending_host_capacity_renewal(
                    plane.host_runtime_dir,
                    host_id=args.host_id,
                    now=plane.clock(),
                )
            if capacity.get("host_id") != args.host_id:
                raise AutopilotError(
                    "worker prompt host id is not authenticated by host capacity"
                )
            with plane.snapshot_cache():
                print(
                    plane.render_worker_prompt(
                        args.node_id, host_id=args.host_id
                    )
                )
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
                claim_id=args.claim_id,
                claim_authority_class="HOSTED_LAUNCH",
                launch_instruction_id=args.launch_instruction_id,
                resource_key=args.resource_key,
                authority_epoch=args.authority_epoch,
                lease_minutes=args.lease_minutes,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "validation-lease-renew":
            result = plane.renew_global_validation_lease(
                args.node_id,
                args.owner,
                lease_id=args.lease_id,
                claim_id=args.claim_id,
                claim_authority_class="HOSTED_LAUNCH",
                launch_instruction_id=args.launch_instruction_id,
                resource_key=args.resource_key,
                authority_epoch=args.authority_epoch,
                lease_minutes=args.lease_minutes,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "validation-lease-release":
            plane.release_global_validation_lease(
                args.node_id,
                args.owner,
                lease_id=args.lease_id,
                claim_id=args.claim_id,
                claim_authority_class="HOSTED_LAUNCH",
                launch_instruction_id=args.launch_instruction_id,
                resource_key=args.resource_key,
                authority_epoch=args.authority_epoch,
            )
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
            with plane.host_lock(timeout_seconds=120.0):
                with plane.arbiter_lock(timeout_seconds=120.0):
                    with plane.execution_lock(
                        "dispatcher-admission.lock", timeout_seconds=120.0
                    ):
                        release = plane.assert_start_now(args.node_id)
                        if release.get("host_id") != args.host_id:
                            raise AutopilotError(
                                "launch adapter host id differs from dispatcher host"
                            )
                        permit = next(
                            (
                                item
                                for item in release.get(
                                    "primary_host_reservations", []
                                )
                                if isinstance(item, Mapping)
                                and item.get("node_id") == args.node_id
                                and item.get("resource_key") == args.resource_key
                            ),
                            None,
                        )
                        if not isinstance(permit, Mapping):
                            raise AutopilotError(
                                "launch has no exact primary host reservation"
                            )
                        inventory = {
                            str(item["reservation_id"]): item
                            for item in active_global_host_reservations(
                                plane.host_runtime_dir
                            )
                        }
                        host_reservation = inventory.get(
                            str(permit["reservation_id"])
                        )
                        if not isinstance(host_reservation, Mapping):
                            raise AutopilotError(
                                "launch primary host reservation is no longer active"
                            )
                        prepared = prepare_launch(
                            plane.repo_root,
                            args.instruction_id,
                            args.host,
                            execution_id=plane.execution_id,
                            execution_namespace=plane.execution_namespace,
                            repository=args.repository,
                            node_id=args.node_id,
                            lifecycle=args.lifecycle,
                            branch=args.branch,
                            attempt=args.attempt,
                            retry_of=args.retry_of,
                            resource_key=args.resource_key,
                            target_sha=args.target_sha,
                            plan_fingerprint=args.plan_fingerprint,
                            target_branch=args.target_branch,
                            authority_class=args.authority_class,
                            dispatcher_release_id=(
                                str(release["release_id"])
                                if args.authority_class == "WRITE_AUTHORIZED"
                                else None
                            ),
                            dispatcher_admission_epoch=(
                                int(release["admission_epoch"])
                                if args.authority_class == "WRITE_AUTHORIZED"
                                else None
                            ),
                            host_reservation_id=str(
                                host_reservation["reservation_id"]
                            ),
                            capacity_host_id=str(host_reservation["host_id"]),
                            capacity_generation=str(
                                host_reservation["capacity_generation"]
                            ),
                            capacity_epoch=int(host_reservation["capacity_epoch"]),
                            reservation_expires_at=str(
                                host_reservation["expires_at"]
                            ),
                            host_kernel_generation=str(
                                host_reservation["host_kernel_generation"]
                            ),
                            execution_adapter_identity_record_id=str(
                                host_reservation[
                                    "execution_adapter_identity_record_id"
                                ]
                            ),
                            execution_adapter_identity_path=str(
                                host_reservation[
                                    "execution_adapter_identity_path"
                                ]
                            ),
                            execution_adapter_identity_blob_digest=str(
                                host_reservation[
                                    "execution_adapter_identity_blob_digest"
                                ]
                            ),
                            state_dir=plane.execution_dir,
                        )
            print(json.dumps(prepared, indent=2, sort_keys=True))
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
                        resource_key=args.resource_key,
                        authority_epoch=args.authority_epoch,
                        state_dir=plane.execution_dir,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "launch-bindings":
            print(
                json.dumps(
                    binding_events(plane.repo_root, state_dir=plane.execution_dir),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "check-launch-authority":
            print(
                json.dumps(
                    assert_launch_authority(
                        plane.repo_root,
                        args.instruction_id,
                        resource_key=args.resource_key,
                        authority_epoch=args.authority_epoch,
                        state_dir=plane.execution_dir,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "fence-launch":
            fenced = fence_launch(
                plane.repo_root,
                args.instruction_id,
                actor=args.actor,
                reason=args.reason,
                state_dir=plane.execution_dir,
            )
            print(
                json.dumps(
                    fenced,
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "runtime-authority-migrate":
            # Readiness is the final publication step.  Identity and standard
            # locks are staged under the bootstrap lock, attended legacy state is
            # migrated under its exact standard lock, and only then can ordinary
            # production readers/writers observe a ready authority runtime.
            ready_path = plane.coordination_dir / RUNTIME_READY_MANIFEST
            if ready_path.exists() or plane._is_link_like(ready_path):
                chain = validate_repository_runtime_ready_chain(
                    plane.repo_root, plane.coordination_dir
                )
                migration_completion: Mapping[str, object] | None = None
                pending_operation = _active_runtime_migration_operation(
                    plane.repo_root, plane.coordination_dir
                )
                if isinstance(pending_operation, Mapping):
                    pending_plan = pending_operation.get("plan")
                    if not isinstance(pending_plan, Mapping):
                        raise AutopilotError(
                            "runtime migration recovery lost its sealed plan"
                        )
                    with plane.host_lock(timeout_seconds=120.0):
                        with runtime_file_lock(
                            plane.coordination_dir / RUNTIME_BOOTSTRAP_LOCK,
                            timeout_seconds=120.0,
                        ):
                            locked_chain = validate_repository_runtime_ready_chain(
                                plane.repo_root, plane.coordination_dir
                            )
                            if locked_chain != chain:
                                raise AutopilotError(
                                    "runtime READY chain changed during migration recovery"
                                )
                            migration_completion = (
                                _complete_runtime_migration_operation(
                                    plane.coordination_dir,
                                    pending_operation,
                                    semantic_reconciliation_id=str(
                                        pending_plan[
                                            "semantic_reconciliation_id"
                                        ]
                                    ),
                                    bootstrap_migration_id=str(
                                        pending_plan["bootstrap_migration_id"]
                                    ),
                                    ready_record_id=str(
                                        chain["ready"]["record_id"]
                                    ),
                                    actor=args.actor,
                                    completed_at=format_time(plane.clock()),
                                )
                            )
                print(
                    json.dumps(
                        {
                            "coordination_dir": str(plane.coordination_dir),
                            "runtime_identity": dict(chain["runtime_identity"]),
                            "bootstrap_authority": dict(
                                chain["bootstrap_authority"]
                            ),
                            "attended_host": dict(chain["attended_host"]),
                            "ready": dict(chain["ready"]),
                            "execution_dir": chain["execution_dir"],
                            "execution_identity": dict(
                                chain["execution_identity"]
                            ),
                            "default_execution_adoption_digest": chain[
                                "default_execution_adoption_digest"
                            ],
                            "operation_completion": (
                                dict(migration_completion)
                                if isinstance(migration_completion, Mapping)
                                else None
                            ),
                            "outcome": "ALREADY_READY",
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 0
            existing_operation = _active_runtime_migration_operation(
                plane.repo_root, plane.coordination_dir
            )
            migration_plan = (
                dict(existing_operation["plan"])
                if isinstance(existing_operation, Mapping)
                and isinstance(existing_operation.get("plan"), Mapping)
                else _runtime_migration_plan(
                    plane.repo_root,
                    plane.coordination_dir,
                    now=plane.clock(),
                )
            )
            with plane.host_lock(timeout_seconds=120.0):
                with runtime_file_lock(
                    plane.coordination_dir / RUNTIME_BOOTSTRAP_LOCK,
                    timeout_seconds=120.0,
                ):
                    locked_operation = _active_runtime_migration_operation(
                        plane.repo_root, plane.coordination_dir
                    )
                    if (
                        isinstance(locked_operation, Mapping)
                        and locked_operation.get("plan") != migration_plan
                    ):
                        raise AutopilotError(
                            "runtime migration operation changed before apply"
                        )
                    operation = (
                        locked_operation
                        if isinstance(locked_operation, Mapping)
                        else _install_runtime_migration_operation(
                            plane.coordination_dir,
                            migration_plan,
                            actor=args.actor,
                            prepared_at=format_time(plane.clock()),
                        )
                    )
                    if _runtime_migration_abort(
                        plane.coordination_dir, operation
                    ) is not None:
                        raise AutopilotError(
                            "runtime migration operation was append-only aborted; "
                            "preserved authority will not be reactivated"
                        )
                    bind_host_repository_runtime(
                        plane.host_runtime_dir,
                        repository=str(
                            plane.control["target"]["repository"]
                        ),
                        coordination_dir=plane.coordination_dir,
                        repo_root=plane.repo_root,
                        transport_digest=str(
                            plane.repository_identity["transport_digest"]
                        ),
                        bound_at=format_time(plane.clock()),
                    )
                    legacy_authority_reconciliation = (
                        reconcile_legacy_worktree_execution_authority(
                            plane.repo_root,
                            plane.coordination_dir,
                            host_runtime_dir=plane.host_runtime_dir,
                            actor=args.actor,
                            clock=plane.clock,
                        )
                    )
                    if legacy_authority_reconciliation.get(
                        "reconciliation_id"
                    ) != migration_plan.get("semantic_reconciliation_id"):
                        raise AutopilotError(
                            "semantic reconciliation differs from the sealed migration plan"
                        )
                    bootstrap_migration = bootstrap_runtime_authority_migration(
                        plane.repo_root,
                        plane.coordination_dir,
                        actor=args.actor,
                        clock=plane.clock,
                    )
                    if bootstrap_migration.get(
                        "migration_id"
                    ) != migration_plan.get("bootstrap_migration_id"):
                        raise AutopilotError(
                            "bootstrap migration differs from the sealed migration plan"
                        )
                    stage_repository_runtime_authority(
                        plane.repo_root,
                        plane.coordination_dir,
                        host_runtime_dir=plane.host_runtime_dir,
                    )
                    with plane.bootstrap_arbiter_lock(
                        bootstrap_migration_id=str(
                            bootstrap_migration["migration_id"]
                        ),
                        timeout_seconds=120.0,
                    ):
                        with runtime_file_lock(
                            plane.coordination_dir
                            / "locks"
                            / "attended-host.lock",
                            timeout_seconds=120.0,
                        ):
                            attended_migration = AttendedCodexHost(
                                plane
                            ).migrate_legacy_ledger(
                                actor=args.actor,
                                already_holds_runtime_lock=True,
                            )
                            runtime_identity = initialize_repository_runtime_authority(
                                plane.repo_root,
                                plane.coordination_dir,
                                attended_migration=attended_migration,
                            )
                            ready = read_strict_canonical_json(
                                plane.coordination_dir / RUNTIME_READY_MANIFEST,
                                label="runtime authority READY receipt",
                            )
                            if (
                                not isinstance(ready, Mapping)
                                or AUTHORITY_ID.fullmatch(
                                    str(ready.get("record_id"))
                                )
                                is None
                            ):
                                raise AutopilotError(
                                    "runtime authority READY receipt is invalid"
                                )
                            migration_completion = (
                                _complete_runtime_migration_operation(
                                    plane.coordination_dir,
                                    operation,
                                    semantic_reconciliation_id=str(
                                        legacy_authority_reconciliation[
                                            "reconciliation_id"
                                        ]
                                    ),
                                    bootstrap_migration_id=str(
                                        bootstrap_migration["migration_id"]
                                    ),
                                    ready_record_id=str(ready["record_id"]),
                                    actor=args.actor,
                                    completed_at=format_time(plane.clock()),
                                )
                            )
            print(
                json.dumps(
                    {
                        "coordination_dir": str(plane.coordination_dir),
                        "operation": dict(operation),
                        "operation_completion": dict(migration_completion),
                        "runtime_identity": dict(runtime_identity),
                        "legacy_worktree_authority_reconciliation": dict(
                            legacy_authority_reconciliation
                        ),
                        "bootstrap_authority": dict(bootstrap_migration),
                        "attended_host": dict(attended_migration),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "run-recover-torn-tail":
            receipt = recover_torn_tail(
                execution_dir=plane.execution_dir,
                execution_id=plane.execution_id,
                execution_namespace=plane.execution_namespace,
                authenticate=lambda directory, execution_id, namespace, plan: (
                    _authenticate_supervisor_execution(
                        plane, directory, execution_id, namespace, plan
                    )
                ),
                plan_fingerprint=plane.expected_plan_fingerprint,
                initial_frontier_id=plane.expected_plan_fingerprint,
                actor=args.actor,
                reason=args.reason,
                clock=plane.clock,
            )
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "hive-mind-supervisor-torn-tail-recovery-result-v1",
                        "execution_namespace": plane.execution_namespace,
                        "execution_id": plane.execution_id,
                        "epoch": receipt.epoch,
                        "transaction_id": receipt.transaction_id,
                        "tail_digest": receipt.tail_digest,
                        "tail_bytes": receipt.tail_bytes,
                        "evidence_path": str(receipt.evidence_path),
                        "journal_event_id": receipt.journal_event_id,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "run-reconcile-unknown":
            capability, adapter, adapter_detail, _adapter_identity = _load_host_adapter(
                plane,
                adapter_name=args.host_adapter,
                host_id=args.host_id,
                wait_seconds=args.wait_seconds,
            )
            adapter_to_close = adapter
            if (
                capability
                not in {
                    HostCapability.AUTHENTICATED_LIFECYCLE,
                    HostCapability.AUTHENTICATED_OBSERVER,
                }
                or adapter is None
            ):
                raise AutopilotError(
                    "unknown-attempt reconciliation requires authenticated host "
                    f"lifecycle: {adapter_detail}"
                )
            observation_id, reconciliation_result = (
                _controller_reconcile_unknown_attempt(
                    plane,
                    adapter,
                    host_id=args.host_id,
                    actor=args.actor,
                    attempt_id=args.attempt_id,
                )
            )

            def verify_fixed_point(
                request: FixedPointVerificationRequest,
            ) -> FixedPointEvidence:
                return _supervisor_fixed_point_verifier(
                    plane,
                    adapter,
                    host_id=args.host_id,
                    request=request,
                )

            reconciled = reconcile_unknown_attempt(
                execution_dir=plane.execution_dir,
                execution_id=plane.execution_id,
                execution_namespace=plane.execution_namespace,
                authenticate=lambda directory, execution_id, namespace, plan: (
                    _authenticate_supervisor_execution(
                        plane, directory, execution_id, namespace, plan
                    )
                ),
                plan_fingerprint=plane.expected_plan_fingerprint,
                initial_frontier_id=plane.expected_plan_fingerprint,
                attempt_id=args.attempt_id,
                observation_id=observation_id,
                result=reconciliation_result,
                verify_fixed_point=verify_fixed_point,
                clock=plane.clock,
            )
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": (
                            "hive-mind-supervisor-attempt-reconciliation-result-v1"
                        ),
                        "execution_namespace": plane.execution_namespace,
                        "execution_id": plane.execution_id,
                        "attempt_id": args.attempt_id,
                        "observation_id": observation_id,
                        "disposition": reconciled.disposition.value,
                        "successful": reconciled.successful,
                        "frontier_id": reconciled.frontier_id,
                        "journal_event_id": reconciled.journal_event_id,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            if reconciled.disposition in {
                StepDisposition.ROUND_COMPLETE,
                StepDisposition.PLAN_QUIESCENT,
            }:
                return 0
            if reconciled.disposition in {
                StepDisposition.WAITING,
                StepDisposition.WAITING_FOR_HOST,
            }:
                return 3
            if reconciled.disposition is StepDisposition.BLOCKED:
                return 4
            return 2
        if args.command == "run":
            capability, adapter, adapter_detail, adapter_identity = _load_host_adapter(
                plane,
                adapter_name=args.host_adapter,
                host_id=args.host_id,
                wait_seconds=args.wait_seconds,
            )
            adapter_to_close = adapter

            def step(context: StepContext) -> StepResult:
                if adapter is None:
                    return StepResult(
                        disposition=StepDisposition.WAITING_FOR_HOST,
                        detail=adapter_detail,
                    )
                return _supervisor_controller_step(
                    plane,
                    adapter,
                    context=context,
                    host_id=args.host_id,
                    execution_adapter_identity=adapter_identity,
                    actor=args.actor,
                    request=args.request,
                    launch_authorized=(
                        capability is HostCapability.AUTHENTICATED_LIFECYCLE
                    ),
                )

            def verify_fixed_point(
                request: FixedPointVerificationRequest,
            ) -> FixedPointEvidence:
                if adapter is None:
                    raise AutopilotError(
                        "fixed-point verification requires an authenticated host adapter"
                    )
                return _supervisor_fixed_point_verifier(
                    plane,
                    adapter,
                    host_id=args.host_id,
                    request=request,
                )

            def observe_terminal(context: ObserverContext) -> ObserverResult:
                if adapter is None:
                    return ObserverResult(
                        disposition=StepDisposition.WAITING_FOR_HOST,
                        detail=adapter_detail,
                        wait_condition=_supervisor_wait_condition(
                            plane,
                            frontier_id=context.frontier_id,
                            release_id="sha256:" + "0" * 64,
                            evidence={"host_capability": capability.value},
                        ),
                    )
                return _supervisor_terminal_observer(
                    plane,
                    adapter,
                    context=context,
                    host_id=args.host_id,
                )

            def verify_wait_observation(
                request: WaitObservationVerificationRequest,
            ) -> str:
                return _supervisor_wait_observation_verifier(
                    plane, request=request
                )

            observation_fingerprint, resume_token = (
                _automatic_supervisor_wait_resume(
                    plane,
                    observation_fingerprint=args.observation_fingerprint,
                    resume_token=args.resume_token,
                )
            )
            result = run_to_fixed_point(
                execution_dir=plane.execution_dir,
                execution_id=plane.execution_id,
                execution_namespace=plane.execution_namespace,
                authenticate=lambda directory, execution_id, namespace, plan: (
                    _authenticate_supervisor_execution(
                        plane, directory, execution_id, namespace, plan
                    )
                ),
                plan_fingerprint=plane.expected_plan_fingerprint,
                initial_frontier_id=plane.expected_plan_fingerprint,
                host_capability=capability,
                step=step,
                verify_fixed_point=verify_fixed_point,
                observe_terminal=(
                    observe_terminal
                    if capability is HostCapability.AUTHENTICATED_OBSERVER
                    else None
                ),
                verify_wait_observation=verify_wait_observation,
                observation_fingerprint=observation_fingerprint,
                resume_token=resume_token,
                clock=plane.clock,
            )
            document: dict[str, object] = {
                "schema_version": 1,
                "kind": "hive-mind-autonomous-run-result-v1",
                "execution_namespace": plane.execution_namespace,
                "execution_id": plane.execution_id,
                "host_id": args.host_id,
                "host_adapter": args.host_adapter,
                "host_capability": capability.value,
                "disposition": result.disposition.value,
                "successful": result.successful,
                "detail": result.detail,
                "epoch": result.epoch,
                "transaction_id": result.transaction_id,
                "frontier_id": result.frontier_id,
                "completed_frontiers": list(result.completed_frontiers),
                "journal_event_id": result.journal_event_id,
                "fixed_point_evidence": (
                    result.fixed_point_evidence.to_payload()
                    if result.fixed_point_evidence is not None
                    else None
                ),
                "wait_condition": (
                    result.wait_condition.to_payload()
                    if result.wait_condition is not None
                    else None
                ),
                "unknown_attempt_id": result.unknown_attempt_id,
            }
            print(json.dumps(document, indent=2, sort_keys=True))
            if result.disposition is StepDisposition.PLAN_QUIESCENT:
                return 0
            if result.disposition in {
                StepDisposition.WAITING,
                StepDisposition.WAITING_FOR_HOST,
            }:
                return 3
            if result.disposition is StepDisposition.BLOCKED:
                return 4
            return 2
        if args.command == "run-round":
            result = drive_round(
                plane,
                actor=args.actor,
                push=not args.no_push,
                round_authority={
                    "release_id": args.release_id,
                },
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result.get("disposition") in {
                "ROUND_COMPLETE",
                "ROUND_VALIDATED_LOCAL",
            } else 1
        if args.command == "heal":
            healing_adapter_identity: Mapping[str, object] | None = None
            if not args.dry_run:
                (
                    capability,
                    adapter,
                    _adapter_detail,
                    loaded_adapter_identity,
                ) = _load_host_adapter(
                    plane,
                    adapter_name=args.host_adapter,
                    host_id=args.host_id,
                    wait_seconds=args.wait_seconds,
                )
                adapter_to_close = adapter
                if (
                    capability is HostCapability.AUTHENTICATED_LIFECYCLE
                    and isinstance(loaded_adapter_identity, Mapping)
                ):
                    healing_adapter_identity = loaded_adapter_identity
            print(
                json.dumps(
                    heal_round(
                        plane,
                        actor=args.actor,
                        host_id=args.host_id,
                        execution_adapter_identity=healing_adapter_identity,
                        nodes=args.node or None,
                        apply=not args.dry_run,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "lessons":
            index = summarize_lessons(plane.ap_root, now=plane.clock())
            if args.commit or args.push:
                index["commit"] = commit_lessons(
                    plane, actor=args.actor, push=args.push
                )
            if args.json_output:
                print(json.dumps(index, indent=2, sort_keys=True))
            else:
                print(f"LESSONS: {index['total']}")
                for name, count in index["by_confidence"].items():
                    print(f"  {name}: {count}")
                print(f"PENDING ATTEMPTS: {index['pending_attempts']}")
                for row in index["lessons"]:
                    counts = row["counts"]
                    print(
                        f"- [{row['confidence']}] {row['signature']} "
                        f"(held {counts['UNBLOCKED']}, did-not-hold "
                        f"{counts['NO_EFFECT']}, refused {counts['REFUSED']})"
                    )
                    if row.get("withdrawn"):
                        print(f"    WITHDRAWN: {row['guidance']}")
                if "commit" in index:
                    print(f"COMMIT: {index['commit'].get('outcome')}")
                    if "push" in index["commit"]:
                        print(f"PUSH: {index['commit']['push']}")
            return 0
        if args.command == "lift-retry-quarantine":
            lifted = plane.lift_retry_quarantine(args.node_id, actor=args.actor)
            print(
                json.dumps(
                    lifted
                    if lifted is not None
                    else {"node_id": args.node_id, "outcome": "not-quarantined"},
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "escalation-resolve":
            resolved = plane.resolve_escalation(args.node_id, actor=args.actor)
            print(
                json.dumps(
                    resolved
                    if resolved is not None
                    else {"node_id": args.node_id, "outcome": "not-escalated"},
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "execute-wave":
            capability, host, adapter_detail, adapter_identity = _load_host_adapter(
                plane,
                adapter_name=args.host_adapter,
                host_id=args.host_id,
                wait_seconds=args.wait_seconds,
            )
            adapter_to_close = host
            if capability is not HostCapability.AUTHENTICATED_LIFECYCLE or host is None:
                print(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "kind": "hive-mind-host-wait-v1",
                            "execution_namespace": plane.execution_namespace,
                            "execution_id": plane.execution_id,
                            "host_id": args.host_id,
                            "host_adapter": args.host_adapter,
                            "disposition": "WAITING_FOR_HOST",
                            "detail": adapter_detail,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 3
            status, decision = select_orchestration_status(plane, args.request)
            if args.apply and should_publish_release(decision, status):
                if not isinstance(adapter_identity, Mapping):
                    raise AutopilotError(
                        "wave dispatch lacks immutable execution adapter authority"
                    )
                plane.dispatch(
                    actor=args.actor,
                    host_id=args.host_id,
                    execution_adapter_identity=adapter_identity,
                )
                status = plane.status()
            # The attended host has no sidecar API; the wave runs without its
            # optional sidecar cohort rather than refusing to run at all.
            contract = build_orchestration_contract(
                plane,
                args.request,
                status=status,
                host_id=args.host_id,
                allow_sidecars=False,
                allow_preparation_tasks=False,
            )
            if not contract["tasks"] and args.apply and not args.no_heal:
                # A withheld wave is exactly what healing exists for: repair the
                # defunct evidence, refresh authority, and rebuild the contract
                # once before conceding.
                healed = heal_round(
                    plane,
                    actor=args.actor,
                    host_id=args.host_id,
                    execution_adapter_identity=adapter_identity,
                    status=status,
                )
                print(f"HEAL: {healed['disposition']}")
                for action in healed["actions"]:
                    print(
                        f"  - {action['kind']} {action['node_id'] or ''} "
                        f"{action['outcome']}: {action['detail']}"
                    )
                if healed["disposition"] == "HEALED":
                    status = plane.status()
                    contract = build_orchestration_contract(
                        plane,
                        args.request,
                        status=status,
                        host_id=args.host_id,
                        allow_sidecars=False,
                        allow_preparation_tasks=False,
                    )
            print(f"INTENT: {contract['intent']['intent']}")
            print(f"CONTRACT: {contract['contract_id']}")
            if not contract["tasks"]:
                print(f"NO RELEASED WAVE: {contract['dispatch_release']['action']}")
                for issue in contract["dispatch_release"]["issues"]:
                    print(f"  - {issue}")
                return 1
            bind_tasks = getattr(host, "bind_tasks", None)
            if not callable(bind_tasks):
                raise AutopilotError(
                    "authenticated host adapter cannot bind the signed task wave"
                )
            bind_tasks(contract["tasks"])
            result = execute_contract(
                plane.repo_root,
                contract,
                host,
                EvidenceResolver(),
                state_dir=plane.execution_dir,
                host_runtime_dir=plane.host_runtime_dir,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result.get("successful") is True else 1
        if args.command == "orchestrate":
            status, decision = select_orchestration_status(plane, args.request)
            if args.apply and should_publish_release(decision, status):
                (
                    capability,
                    adapter,
                    adapter_detail,
                    adapter_identity,
                ) = _load_host_adapter(
                    plane,
                    adapter_name=args.host_adapter,
                    host_id=args.host_id,
                    wait_seconds=args.wait_seconds,
                )
                adapter_to_close = adapter
                if (
                    capability is not HostCapability.AUTHENTICATED_LIFECYCLE
                    or adapter is None
                    or not isinstance(adapter_identity, Mapping)
                ):
                    raise AutopilotError(
                        "orchestration dispatch requires crash-exact autonomous "
                        "host authority: "
                        + adapter_detail
                    )
                plane.dispatch(
                    actor=args.actor,
                    host_id=args.host_id,
                    execution_adapter_identity=adapter_identity,
                )
                status = plane.status()
            result = build_orchestration_contract(
                plane,
                args.request,
                status=status,
                host_id=args.host_id,
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
        SupervisorError,
    ) as error:
        print(f"autopilot: {error}", file=sys.stderr)
        return 2
    finally:
        close_adapter = getattr(adapter_to_close, "close", None)
        if callable(close_adapter):
            close_adapter()


if __name__ == "__main__":
    raise SystemExit(main())
