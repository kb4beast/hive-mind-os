#!/usr/bin/env python3
"""Command-line interface for the repository-resident implementation control plane."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Sequence

from durable_controller import (
    AutopilotError,
    ClaimError,
    ConfigurationError,
    ReceiptError,
    atomic_write_json,
    digest_json,
    read_json,
)
from release_barrier import ControlPlane as ReleaseBarrierControlPlane

RECON_PREMATURE_RECEIPT = "37055e0b8c6dac451e899401802061fe258594f7"
RECEIPT_BRANCH_RETIREMENTS = ".autopilot/receipt-branch-retirements.json"
RETIREMENT_KIND = "hive-mind-autopilot-receipt-branch-retirement-v1"
EXPLORER_RETIREMENT = {
    "retirement_id": "explorer-310-rejected-receipt-branch-v1",
    "node_id": "EXPLORER-310",
    "branch": "autopilot/explorer-310",
    "candidate_commit": "3d305e63391094846e8d8ebacad2fa73dbb2db8b",
    "receipt_commit": "2304036fe92e7fe499785a500c173300943a55fb",
    "expected_remote_head": "2304036fe92e7fe499785a500c173300943a55fb",
    "contract_version": 1,
    "plan_fingerprint": "sha256:9769f9796efb351da9b764fd49983b1130adccc0b8592e42581714d3727f8b39",
    "blocker_id": "sha256:e3d19e5a17fb286d55eb7bf82d975aaed569c514d37553218391e13518b48382",
    "violation": "Explorer's broad Git argv allowlist admitted git diff --output=escaped.patch, a repository-writing flag outside its read-only authority.",
    "evidence_refs": [
        "git:3d305e63391094846e8d8ebacad2fa73dbb2db8b:src/hive_mind_os/brain_kernel/explorer.py",
        "git:2304036fe92e7fe499785a500c173300943a55fb",
    ],
    "archive_ref": "refs/hive-mind-autopilot/quarantine/explorer-310/2304036fe92e7fe499785a500c173300943a55fb",
    "replacement_required": True,
}


class ControlPlane(ReleaseBarrierControlPlane):
    """CLI plane with one fail-closed RECON receipt supersession repair.

    RECON-010 published a durable receipt before the merged PR #120 release-barrier
    amendment was fully implemented. The historical receipt must remain in Git history,
    but the replacement receipt required by the amended contract must become the only
    active RECON completion record. This repair recognizes only that exact historical
    receipt and only when the replacement explicitly binds it in receipt authority.
    Every other duplicate-receipt situation remains fail-closed.
    """

    def _resolve_recon_receipt_records(
        self, records: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
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
        recon = records.get("RECON-010")
        if not isinstance(recon, list):
            return records
        resolved = self._resolve_recon_receipt_records(recon)
        if resolved is recon:
            return records
        updated = dict(records)
        updated["RECON-010"] = resolved
        return updated

    @property
    def receipt_branch_retirements_path(self) -> Path:
        return self.repo_root / RECEIPT_BRANCH_RETIREMENTS

    @property
    def receipt_branch_retirement_state_path(self) -> Path:
        return self.state_dir / "receipt-branch-retirements" / "EXPLORER-310.json"

    def _retirement_document(self) -> Mapping[str, Any] | None:
        if not self.receipt_branch_retirements_path.is_file():
            return None
        value = read_json(self.receipt_branch_retirements_path)
        return value if isinstance(value, Mapping) else None

    def receipt_branch_retirement_issues(self) -> tuple[str, ...]:
        document = self._retirement_document()
        if document is None:
            return (f"required receipt-branch retirement file is missing: {RECEIPT_BRANCH_RETIREMENTS}",)
        if document.get("schema_version") != 1:
            return ("receipt-branch retirements schema_version is unsupported",)
        records = document.get("receipt_branch_retirements")
        if not isinstance(records, list) or len(records) != 1:
            return ("receipt-branch retirements must contain exactly one sealed EXPLORER-310 record",)
        if not isinstance(records[0], Mapping) or dict(records[0]) != EXPLORER_RETIREMENT:
            return ("receipt-branch retirement record is not the sealed EXPLORER-310 receipt retirement",)
        if EXPLORER_RETIREMENT["plan_fingerprint"] != self.expected_plan_fingerprint:
            return ("receipt-branch retirement plan fingerprint is stale",)
        node = super().node("EXPLORER-310")
        if node.get("branch") != EXPLORER_RETIREMENT["branch"]:
            return ("receipt-branch retirement branch does not match EXPLORER-310 contract",)
        if node.get("contract_version") != EXPLORER_RETIREMENT["contract_version"]:
            return ("receipt-branch retirement contract version does not match EXPLORER-310",)
        return ()

    def _retirement_record(self, retirement_id: str) -> Mapping[str, Any]:
        issues = self.receipt_branch_retirement_issues()
        if issues:
            raise AutopilotError("; ".join(issues))
        if retirement_id != EXPLORER_RETIREMENT["retirement_id"]:
            raise AutopilotError("receipt-branch retirement id is not authorized")
        return EXPLORER_RETIREMENT

    def validate_configuration(self) -> tuple[str, ...]:
        issues = list(super().validate_configuration())
        issues.extend(self.receipt_branch_retirement_issues())
        return tuple(dict.fromkeys(issues))

    def _remote_ref_sha(self, reference: str, *, remote: str) -> str | None:
        completed = self._git(("ls-remote", remote, reference), check=False)
        if completed.returncode != 0:
            raise ClaimError(f"cannot inspect remote {remote!r}: {completed.stderr.strip()}")
        fields = completed.stdout.strip().split()
        if not fields:
            return None
        if len(fields) != 2 or fields[1] != reference or len(fields[0]) != 40:
            raise ClaimError("remote ref returned an invalid commit identity")
        return fields[0]

    def _retirement_history_issues(self, record: Mapping[str, Any]) -> tuple[str, ...]:
        if not self._has_git_repository():
            return ()
        candidate = str(record["candidate_commit"])
        receipt = str(record["receipt_commit"])
        if not (self.git_object_exists(candidate) and self.git_object_exists(receipt)):
            return ("receipt-branch retirement requires the pinned candidate and receipt Git objects",)
        parents = self._git(("show", "-s", "--format=%P", receipt), check=True).stdout.strip().split()
        if parents != [candidate]:
            return ("receipt-branch retirement receipt must have only the pinned candidate parent",)
        if self._commit_tree(candidate) != self._commit_tree(receipt):
            return ("receipt-branch retirement receipt must preserve the candidate tree",)
        message = self._git(("show", "-s", "--format=%B", receipt), check=True).stdout
        sealed = self._parse_receipt_message(message)
        if not isinstance(sealed, Mapping):
            return ("receipt-branch retirement receipt message is not a durable completion receipt",)
        for key in ("node_id", "branch", "plan_fingerprint", "contract_version"):
            if sealed.get(key) != record.get(key):
                return (f"receipt-branch retirement receipt {key} does not match sealed record",)
        if sealed.get("final_commit") != candidate:
            return ("receipt-branch retirement receipt final_commit does not match pinned candidate",)
        return ()

    def _create_retirement_commit(self, record: Mapping[str, Any], *, actor: str) -> str:
        if not self._has_git_repository():
            raise AutopilotError("receipt-branch retirement requires a Git repository")
        receipt = str(record["receipt_commit"])
        tree = self._git(("rev-parse", f"{receipt}^{{tree}}"), check=True).stdout.strip()
        payload = {
            "kind": RETIREMENT_KIND,
            "retirement_id": record["retirement_id"],
            "node_id": record["node_id"],
            "branch": record["branch"],
            "candidate_commit": record["candidate_commit"],
            "receipt_commit": receipt,
            "expected_remote_head": record["expected_remote_head"],
            "plan_fingerprint": record["plan_fingerprint"],
            "contract_version": record["contract_version"],
            "blocker_id": record["blocker_id"],
            "reason": record["violation"],
            "actor": actor,
            "timestamp": self.clock().astimezone().isoformat(),
        }
        message = RETIREMENT_KIND + "\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        created = self._git(
            ("-c", "user.name=Hive Mind Autopilot Retirement", "-c", "user.email=autopilot-retirement@hive-mind.invalid", "commit-tree", tree, "-p", receipt, "-m", message),
            check=True,
            environment={
                "GIT_AUTHOR_NAME": "Hive Mind Autopilot Retirement",
                "GIT_AUTHOR_EMAIL": "autopilot-retirement@hive-mind.invalid",
                "GIT_COMMITTER_NAME": "Hive Mind Autopilot Retirement",
                "GIT_COMMITTER_EMAIL": "autopilot-retirement@hive-mind.invalid",
            },
        ).stdout.strip()
        if len(created) != 40:
            raise AutopilotError("failed to create zero-path receipt-branch retirement commit")
        parents = self._git(("show", "-s", "--format=%P", created), check=True).stdout.strip().split()
        if parents != [receipt] or self._commit_tree(created) != tree:
            raise AutopilotError("receipt-branch retirement commit is not an immutable zero-path child of the receipt")
        return created

    def _retirement_execution(self) -> Mapping[str, Any] | None:
        if not self.receipt_branch_retirement_state_path.is_file():
            return None
        value = read_json(self.receipt_branch_retirement_state_path)
        if not isinstance(value, Mapping):
            raise AutopilotError("receipt-branch retirement execution record is invalid")
        required = {
            "schema_version", "kind", "status", "retirement_id", "retirement_commit",
            "archive_ref", "expected_remote_head", "actor", "github_snapshot_digest",
            "reconciliation_digest",
        }
        if set(value) != required or value.get("schema_version") != 1 or value.get("kind") != RETIREMENT_KIND or value.get("status") != "RETIRED":
            raise AutopilotError("receipt-branch retirement execution record is invalid")
        return value

    def receipt_branch_retirement_digest(self) -> str | None:
        execution = self._retirement_execution()
        if execution is None:
            return None
        if execution.get("retirement_id") != EXPLORER_RETIREMENT["retirement_id"]:
            raise AutopilotError("receipt-branch retirement execution record is invalid")
        return digest_json(execution)

    def _retirement_recovery_issues(self) -> tuple[str, ...]:
        execution = self._retirement_execution()
        if execution is None:
            return ()
        issues: list[str] = []
        if execution.get("github_snapshot_digest") == self._snapshot_digest():
            issues.append("receipt-branch retirement requires a fresh GitHub snapshot")
        if execution.get("reconciliation_digest") == self._reconciliation_digest():
            issues.append("receipt-branch retirement requires fresh target reconciliation")
        return tuple(issues)

    def dispatch(self, *, actor: str, requested_nodes: Sequence[str] = ()) -> Mapping[str, Any]:
        issues = self._retirement_recovery_issues()
        if issues:
            raise AutopilotError("; ".join(issues))
        return super().dispatch(actor=actor, requested_nodes=requested_nodes)

    def retire_receipt_branch(self, retirement_id: str, *, actor: str, remote: str = "origin") -> Mapping[str, Any]:
        """Archive then retire the one sealed bad Explorer receipt branch.

        This method is intentionally never invoked by the implementation change.
        Its one remote transaction creates the immutable quarantine reference and
        deletes the source only under the pinned expected-head lease.
        """

        if not actor.strip():
            raise AutopilotError("receipt-branch retirement actor is required")
        record = self._retirement_record(retirement_id)
        if self.claim_path(str(record["node_id"])).is_file():
            raise ClaimError("receipt-branch retirement is forbidden while the node has an active claim")
        prior = self._retirement_execution()
        if prior is not None:
            if prior.get("retirement_id") == retirement_id and prior.get("status") == "RETIRED":
                return prior
            raise AutopilotError("receipt-branch retirement execution record conflicts with sealed record")
        expected = str(record["expected_remote_head"])
        branch = str(record["branch"])
        source_head = self.remote_branch_sha(branch, remote=remote)
        archive_ref = str(record["archive_ref"])
        archive = self._remote_ref_sha(archive_ref, remote=remote)
        if archive is not None:
            if source_head is not None:
                raise ClaimError("receipt-branch retirement quarantine ref already exists; refuse mutation")
            fetched = self._git(("fetch", "--no-tags", remote, archive_ref), check=False)
            if fetched.returncode != 0:
                raise ClaimError("cannot fetch receipt-branch retirement quarantine ref for verification")
            history_issues = self._retirement_history_issues(record)
            if history_issues:
                raise AutopilotError("; ".join(history_issues))
            message = self._git(("show", "-s", "--format=%B", archive), check=False)
            if message.returncode != 0 or not message.stdout.startswith(RETIREMENT_KIND + "\n"):
                raise ClaimError("receipt-branch retirement quarantine ref is not the sealed retirement commit")
            try:
                payload = json.loads(message.stdout.split("\n", 1)[1])
            except (IndexError, json.JSONDecodeError):
                payload = None
            if not isinstance(payload, Mapping) or payload.get("retirement_id") != retirement_id or payload.get("receipt_commit") != record["receipt_commit"]:
                raise ClaimError("receipt-branch retirement quarantine ref does not bind the sealed receipt")
            retirement_commit = archive
        else:
            if source_head != expected:
                raise ClaimError("receipt-branch retirement remote head does not match the sealed expected SHA")
            history_issues = self._retirement_history_issues(record)
            if history_issues:
                raise AutopilotError("; ".join(history_issues))
            retirement_commit = self._create_retirement_commit(record, actor=actor)
            pushed = self._git(
                (
                    "push", "--atomic", f"--force-with-lease=refs/heads/{branch}:{expected}",
                    f"--force-with-lease={archive_ref}:", remote,
                    f"{retirement_commit}:{archive_ref}", f":refs/heads/{branch}",
                ),
                check=False,
            )
            if pushed.returncode != 0:
                raise ClaimError("receipt-branch retirement archive/delete transaction failed: " + pushed.stderr.strip())
        if self._remote_ref_sha(archive_ref, remote=remote) != retirement_commit:
            raise ClaimError("receipt-branch retirement quarantine ref verification failed after atomic transaction")
        if self.remote_branch_sha(branch, remote=remote) is not None:
            raise ClaimError("receipt-branch retirement source branch still exists after atomic transaction")
        execution = {
            "schema_version": 1,
            "kind": RETIREMENT_KIND,
            "status": "RETIRED",
            "retirement_id": retirement_id,
            "retirement_commit": retirement_commit,
            "archive_ref": archive_ref,
            "expected_remote_head": expected,
            "actor": actor,
            "github_snapshot_digest": self._snapshot_digest(),
            "reconciliation_digest": self._reconciliation_digest(),
        }
        atomic_write_json(self.receipt_branch_retirement_state_path, execution)
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
    retirement.add_argument("--remote", default="origin")

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


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
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
            print(plane.render_worker_prompt(args.node_id))
            return 0
        if args.command == "verify-receipt":
            value = read_json(Path(args.receipt))
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
            print(json.dumps(plane.retire_receipt_branch(args.retirement_id, actor=args.actor, remote=args.remote), indent=2, sort_keys=True))
            return 0
        raise AssertionError(args.command)
    except (AutopilotError, ClaimError, ConfigurationError, ReceiptError) as error:
        print(f"autopilot: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
