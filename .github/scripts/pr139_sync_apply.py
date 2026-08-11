#!/usr/bin/env python3
"""One-shot, ancestry-preserving synchronization for PR #139's release branch."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

HEAD_BRANCH = "release/hive-mind-os-singleton-20260811-r4"
BASE_BRANCH = "release/hive-mind-os-singleton-20260810-r2"
TEMPORARY_PATHS = (
    ".github/workflows/pr139-sync-export.yml",
    ".github/workflows/pr139-sync-apply.yml",
    ".github/scripts/pr139_sync_apply.py",
)
EXPECTED_CONFLICTS = {
    ".autopilot/bin/autopilot.py",
    ".autopilot/bin/controller.py",
    ".autopilot/tests/test_explorer_receipt_retirement.py",
    ".gitignore",
    "docs/architecture/ADR_INDEX.md",
}


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        args,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(
            f"{' '.join(args)} failed ({completed.returncode}):\n"
            f"{completed.stdout}\n{completed.stderr}"
        )
    return completed


def git_show(stage: int, path: str) -> str:
    return run("git", "show", f":{stage}:{path}").stdout


def replace_once(text: str, before: str, after: str, label: str) -> str:
    count = text.count(before)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, observed {count}")
    return text.replace(before, after, 1)


def resolve_autopilot() -> None:
    text = git_show(2, ".autopilot/bin/autopilot.py")
    release_import = (
        "from release_barrier import (\n"
        "    ControlPlane as ReleaseBarrierControlPlane,\n"
        ")\n"
    )
    text = replace_once(
        text,
        release_import,
        release_import + "from sealed_recovery import SealedRecoveryMixin\n",
        "sealed recovery import",
    )
    text = replace_once(
        text,
        "class ControlPlane(ReleaseBarrierControlPlane):",
        "class ControlPlane(SealedRecoveryMixin, ReleaseBarrierControlPlane):",
        "ControlPlane MRO",
    )
    text = replace_once(
        text,
        "    receipt commits are direct children of the candidate on the current target.\n"
        "    Every other duplicate-receipt situation remains fail-closed.\n"
        '    """\n',
        "    receipt commits are direct children of the candidate on the current target.\n"
        "\n"
        "    The sealed recovery mixin additionally admits only the exact retained recovery\n"
        "    authorities for OPTIMIZER-370, ORCH-300, and BUILDER-330. All unrelated duplicate\n"
        "    receipts and branch-recovery attempts remain fail-closed.\n"
        '    """\n',
        "ControlPlane documentation",
    )
    old_receipts = (
        "    def _durable_receipt_records(self) -> dict[str, list[dict[str, Any]]]:\n"
        "        records = super()._durable_receipt_records()\n"
        '        recon = records.get("RECON-010")\n'
        "        if not isinstance(recon, list):\n"
        "            return records\n"
        "        resolved = self._resolve_recon_receipt_records(recon)\n"
        "        if resolved is recon:\n"
        "            return records\n"
        "        updated = dict(records)\n"
        '        updated["RECON-010"] = resolved\n'
        "        return updated\n"
    )
    new_receipts = (
        "    def _durable_receipt_records(self) -> dict[str, list[dict[str, Any]]]:\n"
        "        records = super()._durable_receipt_records()\n"
        "        updated = dict(records)\n"
        '        recon = updated.get("RECON-010")\n'
        "        if isinstance(recon, list):\n"
        "            resolved = self._resolve_recon_receipt_records(recon)\n"
        "            if resolved is not recon:\n"
        '                updated["RECON-010"] = resolved\n'
        '        for node_id in ("OPTIMIZER-370", "ORCH-300"):\n'
        "            node_records = updated.get(node_id)\n"
        "            if isinstance(node_records, list):\n"
        "                resolved = self.resolve_sealed_repair_records(node_id, node_records)\n"
        "                if resolved is not node_records:\n"
        "                    updated[node_id] = resolved\n"
        "        return updated\n"
    )
    text = replace_once(text, old_receipts, new_receipts, "durable receipt composition")
    old_validate = (
        "    def validate_configuration(self) -> tuple[str, ...]:\n"
        "        issues = list(super().validate_configuration())\n"
        "        issues.extend(self.receipt_retirement_issues())\n"
        "        try:\n"
        "            load_policy(self.repo_root)\n"
        "        except OrchestrationError as error:\n"
        "            issues.append(str(error))\n"
        "        return tuple(dict.fromkeys(issues))\n"
    )
    new_validate = old_validate.replace(
        "        issues.extend(self.receipt_retirement_issues())\n",
        "        issues.extend(self.receipt_retirement_issues())\n"
        "        issues.extend(self.sealed_recovery_issues())\n",
    )
    text = replace_once(text, old_validate, new_validate, "configuration validation")
    old_parser = (
        '    retirement = commands.add_parser("retire-receipt-branch")\n'
        '    retirement.add_argument("retirement_id")\n'
        '    retirement.add_argument("--actor", required=True)\n'
        "\n"
        '    orchestrate = commands.add_parser("orchestrate")\n'
    )
    new_parser = (
        '    retirement = commands.add_parser("retire-receipt-branch")\n'
        '    retirement.add_argument("retirement_id")\n'
        '    retirement.add_argument("--actor", required=True)\n'
        "\n"
        '    builder_retirement = commands.add_parser("retire-builder-330-branch")\n'
        '    builder_retirement.add_argument("--actor", required=True)\n'
        "\n"
        '    orchestrate = commands.add_parser("orchestrate")\n'
    )
    text = replace_once(text, old_parser, new_parser, "builder retirement parser")
    old_handler = (
        '        if args.command == "retire-receipt-branch":\n'
        "            print(json.dumps(plane.retire_receipt_branch(args.retirement_id, actor=args.actor), indent=2, sort_keys=True))\n"
        "            return 0\n"
        '        if args.command == "infer-intent":\n'
    )
    new_handler = (
        '        if args.command == "retire-receipt-branch":\n'
        "            print(json.dumps(plane.retire_receipt_branch(args.retirement_id, actor=args.actor), indent=2, sort_keys=True))\n"
        "            return 0\n"
        '        if args.command == "retire-builder-330-branch":\n'
        "            print(json.dumps(plane.retire_builder_branch(actor=args.actor), indent=2, sort_keys=True))\n"
        "            return 0\n"
        '        if args.command == "infer-intent":\n'
    )
    text = replace_once(text, old_handler, new_handler, "builder retirement handler")
    Path(".autopilot/bin/autopilot.py").write_text(text, encoding="utf-8")


def resolve_controller() -> None:
    path = Path(".autopilot/bin/controller.py")
    text = path.read_text(encoding="utf-8")
    text, count = re.subn(
        r"<<<<<<< HEAD\nimport time\n=======\n>>>>>>> [0-9a-f]{40}\n",
        "import time\n",
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError(f"controller import conflict: observed {count} matches")
    path.write_text(text, encoding="utf-8")


def resolve_gitignore() -> None:
    text = git_show(2, ".gitignore")
    needle = "!.autopilot/bin/sidecar_execution.py\n"
    text = replace_once(
        text,
        needle,
        needle + "!/.autopilot/bin/sealed_recovery.py\n",
        "sealed recovery gitignore exception",
    )
    Path(".gitignore").write_text(text, encoding="utf-8")


def resolve_adr_index() -> None:
    text = git_show(2, "docs/architecture/ADR_INDEX.md")
    needle = (
        "| `ADR-056`     | [Singleton release branch execution]"
        "(ADR-056-SINGLETON-RELEASE-BRANCH-EXECUTION.md)"
        "                                         | Singleton execution        "
        "| adopted; `main` remains excluded until final promotion                               |\n"
    )
    sealed = (
        "| `ADR-057`     | [Sealed L2 recovery bootstrap]"
        "(ADR-057-SEALED-L2-RECOVERY-BOOTSTRAP.md)"
        "                                                     | Singleton L2 recovery      "
        "| adapted only for OPTIMIZER-370, ORCH-300, and BUILDER-330                            |\n"
    )
    if sealed in text:
        raise RuntimeError("sealed recovery ADR row already present")
    text = replace_once(text, needle, needle + sealed, "sealed recovery ADR row")
    Path("docs/architecture/ADR_INDEX.md").write_text(text, encoding="utf-8")


def adapt_integrated_tests() -> None:
    blocker = Path(".autopilot/tests/test_blocker_protocol.py")
    text = blocker.read_text(encoding="utf-8")
    needle = '            shutil.copytree(source, root / ".autopilot")\n'
    if text.count(needle) != 2:
        raise RuntimeError("unexpected blocker fixture-copy shape")
    blocker.write_text(
        text.replace(
            needle,
            '            copy_autopilot_fixture(source, root / ".autopilot")\n',
        ),
        encoding="utf-8",
    )

    bootstrap = Path(".autopilot/tests/test_sealed_recovery_bootstrap.py")
    text = bootstrap.read_text(encoding="utf-8")
    old = (
        '        repository = self.root / "sealed-real-flow"\n'
        '        remote = self.root / "sealed-real-flow.git"\n'
        "        copy_autopilot_fixture(Path(__file__).resolve().parents[1], repository / \".autopilot\")\n"
        "\n"
        "        def run(*args: str, check: bool = True) -> str:\n"
    )
    new = (
        '        repository = self.root / "sealed-real-flow"\n'
        '        remote = self.root / "sealed-real-flow.git"\n'
        "        copy_autopilot_fixture(Path(__file__).resolve().parents[1], repository / \".autopilot\")\n"
        "        control = json.loads(\n"
        '            (repository / ".autopilot" / "control-plane.json").read_text(encoding="utf-8")\n'
        "        )\n"
        '        target_branch = str(control["target"]["branch"])\n'
        "\n"
        "        def run(*args: str, check: bool = True) -> str:\n"
    )
    text = replace_once(text, old, new, "dynamic singleton target fixture")
    replacements = {
        '        run("git", "branch", "release/hive-mind-os-singleton-20260810-r2", target)\n':
            '        run("git", "branch", target_branch, target)\n',
        '            f"{target}:refs/heads/release/hive-mind-os-singleton-20260810-r2",\n':
            '            f"{target}:refs/heads/{target_branch}",\n',
        '            f"{published_receipt}:refs/heads/release/hive-mind-os-singleton-20260810-r2",\n':
            '            f"{published_receipt}:refs/heads/{target_branch}",\n',
        '        run("git", "fetch", "origin", "release/hive-mind-os-singleton-20260810-r2")\n':
            '        run("git", "fetch", "origin", target_branch)\n',
    }
    for before, after in replacements.items():
        text = replace_once(text, before, after, "dynamic target branch reference")
    bootstrap.write_text(text, encoding="utf-8")


def verify_and_publish(head_before: str, base_sha: str) -> None:
    for temporary in TEMPORARY_PATHS:
        if Path(temporary).exists():
            run("git", "rm", "-f", temporary)

    # Writing a resolved worktree file does not clear its unmerged index stages;
    # stage every reviewed resolution before asserting that the conflict set is empty.
    run("git", "add", "-A")
    unmerged = set(
        filter(None, run("git", "diff", "--name-only", "--diff-filter=U").stdout.splitlines())
    )
    if unmerged:
        raise RuntimeError(f"unresolved conflicts remain: {sorted(unmerged)}")

    for root in (Path(".autopilot"), Path(".gitignore"), Path("docs/architecture/ADR_INDEX.md")):
        paths = [root] if root.is_file() else list(root.rglob("*"))
        for path in paths:
            if not path.is_file():
                continue
            for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if line.startswith(("<<<<<<<", "=======", ">>>>>>>")):
                    raise RuntimeError(f"conflict marker remains at {path}:{line_number}")

    run("git", "add", "-A")
    run("git", "diff", "--cached", "--check")
    run(sys.executable, "-m", "compileall", "-q", ".autopilot/bin", ".autopilot/tests")
    run(sys.executable, "-m", "unittest", "discover", "-s", ".autopilot/tests", "-v")
    run(
        "git",
        "commit",
        "-m",
        "Merge current singleton base into PR #139 release branch",
        "-m",
        "Preserve PR #139 portable orchestration and token-aware sidecars while integrating the sealed L2 recovery bootstrap from the current singleton base. Resolve overlapping control-plane and fixture changes without rewriting either parent history.",
    )
    first_parent = run("git", "rev-parse", "HEAD^").stdout.strip()
    second_parent = run("git", "rev-parse", "HEAD^2").stdout.strip()
    if first_parent != head_before or second_parent != base_sha:
        raise RuntimeError(
            f"unexpected merge ancestry: first={first_parent}, second={second_parent}"
        )
    if os.environ.get("PR139_SYNC_NO_PUSH") != "1":
        run("git", "push", "origin", f"HEAD:refs/heads/{HEAD_BRANCH}")


def main() -> int:
    run("git", "config", "user.name", "Hive Mind Sync")
    run("git", "config", "user.email", "hive-mind-sync@users.noreply.github.com")
    run(
        "git",
        "fetch",
        "--no-tags",
        "origin",
        f"+refs/heads/{BASE_BRANCH}:refs/remotes/origin/{BASE_BRANCH}",
    )
    base_sha = run("git", "rev-parse", f"refs/remotes/origin/{BASE_BRANCH}").stdout.strip()
    head_before = run("git", "rev-parse", "HEAD").stdout.strip()
    merge = run("git", "merge", "--no-ff", "--no-commit", base_sha, check=False)
    if merge.returncode not in (0, 1):
        raise RuntimeError(f"git merge failed: {merge.stdout}\n{merge.stderr}")
    unmerged = set(
        filter(None, run("git", "diff", "--name-only", "--diff-filter=U").stdout.splitlines())
    )
    if unmerged != EXPECTED_CONFLICTS:
        raise RuntimeError(
            f"unexpected conflict set: expected={sorted(EXPECTED_CONFLICTS)}, "
            f"observed={sorted(unmerged)}"
        )

    resolve_autopilot()
    resolve_controller()
    Path(".autopilot/tests/test_explorer_receipt_retirement.py").write_text(
        git_show(3, ".autopilot/tests/test_explorer_receipt_retirement.py"),
        encoding="utf-8",
    )
    resolve_gitignore()
    resolve_adr_index()
    adapt_integrated_tests()
    verify_and_publish(head_before, base_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
