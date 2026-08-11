#!/usr/bin/env python3
"""Command-line interface for the repository-resident implementation control plane."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from durable_controller import (
    AutopilotError,
    ClaimError,
    ConfigurationError,
    ReceiptError,
    read_json,
)
from release_barrier import ControlPlane as ReleaseBarrierControlPlane

RECON_PREMATURE_RECEIPT = "37055e0b8c6dac451e899401802061fe258594f7"


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
        raise AssertionError(args.command)
    except (AutopilotError, ClaimError, ConfigurationError, ReceiptError) as error:
        print(f"autopilot: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
