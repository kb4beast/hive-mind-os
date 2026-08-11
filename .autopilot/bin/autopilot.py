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
from orchestration import (
    OrchestrationError,
    bind_launch,
    binding_events,
    build_orchestration_contract,
    infer_intent,
    load_policy,
    observe_terminal_launch,
    prepare_launch,
    release_launch,
    should_publish_release,
    simple_prompt,
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

    def validate_configuration(self) -> tuple[str, ...]:
        issues = list(super().validate_configuration())
        try:
            load_policy(self.repo_root)
        except OrchestrationError as error:
            issues.append(str(error))
        return tuple(dict.fromkeys(issues))


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

    orchestrate = commands.add_parser("orchestrate")
    orchestrate.add_argument("--request", default="")
    orchestrate.add_argument("--actor", default="autopilot:orchestrator")
    orchestrate.add_argument(
        "--apply",
        action="store_true",
        help="Publish a safe release when inferred intent and live state allow it",
    )
    orchestrate.add_argument("--json", action="store_true", dest="json_output")

    intent = commands.add_parser("infer-intent")
    intent.add_argument("request", nargs="?", default="")
    intent.add_argument("--json", action="store_true", dest="json_output")

    commands.add_parser("simple-prompt")

    prepare = commands.add_parser("prepare-launch")
    prepare.add_argument("instruction_id")
    prepare.add_argument("--host", required=True)

    bind = commands.add_parser("bind-launch")
    bind.add_argument("instruction_id")
    bind.add_argument("--host", required=True)
    bind.add_argument("--task-id", required=True)
    bind.add_argument("--host-id")
    bind.add_argument("--cursor")

    terminal = commands.add_parser("record-launch-terminal")
    terminal.add_argument("instruction_id")
    terminal.add_argument(
        "--terminal-state", choices=("SUCCEEDED", "FAILED", "CANCELLED"), required=True
    )
    terminal.add_argument("--host-event-ref", required=True)
    terminal.add_argument("--observed-by", required=True)

    release_binding = commands.add_parser("release-launch")
    release_binding.add_argument("instruction_id")
    release_binding.add_argument("--terminal-event", required=True)
    release_binding.add_argument("--reason", required=True)

    commands.add_parser("launch-bindings")

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
            print(json.dumps(prepare_launch(plane.repo_root, args.instruction_id, args.host), indent=2, sort_keys=True))
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
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "release-launch":
            print(
                json.dumps(
                    release_launch(
                        plane.repo_root,
                        args.instruction_id,
                        terminal_event_id=args.terminal_event,
                        reason=args.reason,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "record-launch-terminal":
            print(
                json.dumps(
                    observe_terminal_launch(
                        plane.repo_root,
                        args.instruction_id,
                        terminal_state=args.terminal_state,
                        host_event_ref=args.host_event_ref,
                        observed_by=args.observed_by,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "launch-bindings":
            print(json.dumps(binding_events(plane.repo_root), indent=2, sort_keys=True))
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
