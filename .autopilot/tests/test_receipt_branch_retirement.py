from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import autopilot  # noqa: E402


class ReceiptBranchRetirementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        shutil.copytree(Path(__file__).resolve().parents[1], self.root / ".autopilot")
        control_path = self.root / ".autopilot" / "control-plane.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control["verify_git_objects"] = False
        control_path.write_text(json.dumps(control), encoding="utf-8")
        self.plane = autopilot.ControlPlane(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_exact_record_rejects_unknown_duplicate_and_cross_node_records(self) -> None:
        path = self.root / ".autopilot" / "receipt-branch-retirements.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(self.plane.receipt_branch_retirement_issues(), ())
        document["receipt_branch_retirements"].append(dict(document["receipt_branch_retirements"][0]))
        path.write_text(json.dumps(document), encoding="utf-8")
        self.assertTrue(self.plane.receipt_branch_retirement_issues())
        document["receipt_branch_retirements"] = [dict(autopilot.EXPLORER_RETIREMENT, node_id="ARCH-100")]
        path.write_text(json.dumps(document), encoding="utf-8")
        self.assertTrue(self.plane.receipt_branch_retirement_issues())

    def test_archive_and_delete_are_one_leased_atomic_transaction(self) -> None:
        record = autopilot.EXPLORER_RETIREMENT
        expected = record["expected_remote_head"]
        archive = record["archive_ref"]
        retirement = "a" * 40
        commands: list[tuple[str, ...]] = []
        state = {"source": expected, "archive": None}

        self.plane._has_git_repository = lambda: False  # type: ignore[method-assign]
        self.plane._create_retirement_commit = lambda _record, *, actor: retirement  # type: ignore[method-assign]

        def git(args, *, check=False, environment=None):
            command = tuple(args)
            commands.append(command)
            if command[0] == "ls-remote" and command[-1] == f"refs/heads/{record['branch']}":
                output = f"{state['source']}\t{command[-1]}\n" if state["source"] else ""
                return subprocess.CompletedProcess(command, 0, output, "")
            if command[0] == "ls-remote" and command[-1] == archive:
                output = f"{state['archive']}\t{archive}\n" if state["archive"] else ""
                return subprocess.CompletedProcess(command, 0, output, "")
            if command[0] == "push":
                self.assertIn("--atomic", command)
                self.assertIn(f"--force-with-lease=refs/heads/{record['branch']}:{expected}", command)
                self.assertIn(f"--force-with-lease={archive}:", command)
                state["archive"] = retirement
                state["source"] = None
                return subprocess.CompletedProcess(command, 0, "", "")
            self.fail(f"unexpected Git command: {command}")

        self.plane._git = git  # type: ignore[method-assign]
        result = self.plane.retire_receipt_branch(record["retirement_id"], actor="test:recovery")
        self.assertEqual(result["retirement_commit"], retirement)
        push_index = next(index for index, command in enumerate(commands) if command[0] == "push")
        self.assertGreater(push_index, 1)
        self.assertEqual(state, {"source": None, "archive": retirement})

    def test_head_mismatch_or_archive_conflict_performs_no_delete(self) -> None:
        record = autopilot.EXPLORER_RETIREMENT
        commands: list[tuple[str, ...]] = []
        self.plane._has_git_repository = lambda: False  # type: ignore[method-assign]

        def git(args, *, check=False, environment=None):
            command = tuple(args)
            commands.append(command)
            if command[0] == "ls-remote" and command[-1].startswith("refs/heads/"):
                return subprocess.CompletedProcess(command, 0, f"{'b' * 40}\t{command[-1]}\n", "")
            if command[0] == "ls-remote":
                return subprocess.CompletedProcess(command, 0, "", "")
            self.fail(f"unexpected mutation: {command}")

        self.plane._git = git  # type: ignore[method-assign]
        with self.assertRaises(autopilot.ClaimError):
            self.plane.retire_receipt_branch(record["retirement_id"], actor="test:recovery")
        self.assertFalse(any(command[0] == "push" for command in commands))

    def test_preexisting_bad_archive_fails_without_writing_state(self) -> None:
        record = autopilot.EXPLORER_RETIREMENT
        self.plane._has_git_repository = lambda: False  # type: ignore[method-assign]

        def git(args, *, check=False, environment=None):
            command = tuple(args)
            if command[0] == "ls-remote" and command[-1].startswith("refs/heads/"):
                return subprocess.CompletedProcess(command, 0, "", "")
            if command[0] == "ls-remote":
                return subprocess.CompletedProcess(command, 0, f"{'d' * 40}\t{command[-1]}\n", "")
            if command[:2] == ("fetch", "--no-tags"):
                return subprocess.CompletedProcess(command, 0, "", "")
            if command[:3] == ("show", "-s", "--format=%B"):
                return subprocess.CompletedProcess(command, 0, "not a retirement receipt", "")
            self.fail(f"unexpected mutation: {command}")

        self.plane._git = git  # type: ignore[method-assign]
        with self.assertRaises(autopilot.ClaimError):
            self.plane.retire_receipt_branch(record["retirement_id"], actor="test:recovery")
        self.assertFalse(self.plane.receipt_branch_retirement_state_path.exists())

    def test_atomic_push_failure_leaves_no_retirement_state(self) -> None:
        record = autopilot.EXPLORER_RETIREMENT
        expected = record["expected_remote_head"]
        self.plane._has_git_repository = lambda: False  # type: ignore[method-assign]
        self.plane._create_retirement_commit = lambda _record, *, actor: "e" * 40  # type: ignore[method-assign]

        def git(args, *, check=False, environment=None):
            command = tuple(args)
            if command[0] == "ls-remote" and command[-1].startswith("refs/heads/"):
                return subprocess.CompletedProcess(command, 0, f"{expected}\t{command[-1]}\n", "")
            if command[0] == "ls-remote":
                return subprocess.CompletedProcess(command, 0, "", "")
            if command[0] == "push":
                return subprocess.CompletedProcess(command, 1, "", "simulated atomic refusal")
            self.fail(f"unexpected command: {command}")

        self.plane._git = git  # type: ignore[method-assign]
        with self.assertRaises(autopilot.ClaimError):
            self.plane.retire_receipt_branch(record["retirement_id"], actor="test:recovery")
        self.assertFalse(self.plane.receipt_branch_retirement_state_path.exists())

    def test_tampered_receipt_parent_fails_before_remote_mutation(self) -> None:
        record = autopilot.EXPLORER_RETIREMENT
        self.plane._has_git_repository = lambda: True  # type: ignore[method-assign]
        self.plane.git_object_exists = lambda _sha: True  # type: ignore[method-assign]
        self.plane._commit_tree = lambda _sha: "a" * 40  # type: ignore[method-assign]

        def git(args, *, check=False, environment=None):
            command = tuple(args)
            if command[:3] == ("show", "-s", "--format=%P"):
                return subprocess.CompletedProcess(command, 0, "f" * 40 + "\n", "")
            self.fail(f"unexpected remote mutation: {command}")

        self.plane._git = git  # type: ignore[method-assign]
        self.assertTrue(self.plane._retirement_history_issues(record))

    def test_idempotent_retry_adopts_a_verified_archive_without_a_second_push(self) -> None:
        record = autopilot.EXPLORER_RETIREMENT
        archive_commit = "c" * 40
        commands: list[tuple[str, ...]] = []
        payload = {
            "retirement_id": record["retirement_id"],
            "receipt_commit": record["receipt_commit"],
        }
        self.plane._has_git_repository = lambda: False  # type: ignore[method-assign]

        def git(args, *, check=False, environment=None):
            command = tuple(args)
            commands.append(command)
            if command[0] == "ls-remote" and command[-1].startswith("refs/heads/"):
                return subprocess.CompletedProcess(command, 0, "", "")
            if command[0] == "ls-remote":
                return subprocess.CompletedProcess(command, 0, f"{archive_commit}\t{command[-1]}\n", "")
            if command[:2] == ("fetch", "--no-tags"):
                return subprocess.CompletedProcess(command, 0, "", "")
            if command[:3] == ("show", "-s", "--format=%B"):
                return subprocess.CompletedProcess(command, 0, autopilot.RETIREMENT_KIND + "\n" + json.dumps(payload), "")
            self.fail(f"unexpected mutation: {command}")

        self.plane._git = git  # type: ignore[method-assign]
        result = self.plane.retire_receipt_branch(record["retirement_id"], actor="test:recovery")
        self.assertEqual(result["retirement_commit"], archive_commit)
        self.assertFalse(any(command[0] == "push" for command in commands))

    def test_fresh_clone_resumes_after_atomic_push_before_runtime_state_write(self) -> None:
        source_root = Path(__file__).resolve().parents[2]
        record = autopilot.EXPLORER_RETIREMENT
        remote = self.root / "remote.git"
        fresh = self.root / "fresh"

        def run(*args: str, cwd: Path | None = None) -> None:
            subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)

        run("git", "init", "--bare", str(remote))
        run("git", "push", str(remote), f"{record['receipt_commit']}:refs/heads/{record['branch']}", cwd=source_root)
        source_plane = autopilot.ControlPlane(source_root)
        retirement_commit = source_plane._create_retirement_commit(record, actor="test:recovery")
        run(
            "git", "push", "--atomic",
            f"--force-with-lease=refs/heads/{record['branch']}:{record['expected_remote_head']}",
            f"--force-with-lease={record['archive_ref']}:", str(remote),
            f"{retirement_commit}:{record['archive_ref']}", f":refs/heads/{record['branch']}",
            cwd=source_root,
        )
        run("git", "clone", "--no-local", str(remote), str(fresh))
        shutil.copytree(source_root / ".autopilot", fresh / ".autopilot")
        control_path = fresh / ".autopilot" / "control-plane.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control["verify_git_objects"] = False
        control_path.write_text(json.dumps(control), encoding="utf-8")
        resumed = autopilot.ControlPlane(fresh)
        self.assertFalse(resumed.git_object_exists(record["receipt_commit"]))
        result = resumed.retire_receipt_branch(record["retirement_id"], actor="test:recovery")
        self.assertEqual(result["retirement_commit"], retirement_commit)
        self.assertTrue(resumed.git_object_exists(record["receipt_commit"]))

    def test_malformed_execution_record_fails_closed(self) -> None:
        path = self.plane.receipt_branch_retirement_state_path
        path.parent.mkdir(parents=True)
        path.write_text("[]", encoding="utf-8")
        with self.assertRaises(autopilot.AutopilotError):
            self.plane.receipt_branch_retirement_digest()

    def test_fresh_snapshot_and_reconciliation_are_required_after_retirement(self) -> None:
        source = self.root / "snapshot.json"
        source.write_text(json.dumps({"target_sha": "a" * 40, "pull_requests": [], "branches": []}), encoding="utf-8")
        self.plane.install_github_snapshot(source)
        self.plane.reconcile("a" * 40, actor="test:recovery", reason="before retirement")
        execution = {
            "schema_version": 1,
            "kind": autopilot.RETIREMENT_KIND,
            "status": "RETIRED",
            "retirement_id": autopilot.EXPLORER_RETIREMENT["retirement_id"],
            "retirement_commit": "a" * 40,
            "archive_ref": autopilot.EXPLORER_RETIREMENT["archive_ref"],
            "expected_remote_head": autopilot.EXPLORER_RETIREMENT["expected_remote_head"],
            "actor": "test:recovery",
            "github_snapshot_digest": self.plane._snapshot_digest(),
            "reconciliation_digest": self.plane._reconciliation_digest(),
        }
        autopilot.atomic_write_json(self.plane.receipt_branch_retirement_state_path, execution)
        self.assertEqual(len(self.plane._retirement_recovery_issues()), 2)
        self.plane.install_github_snapshot(source)
        self.plane.reconcile("a" * 40, actor="test:recovery", reason="fresh recovery")
        self.assertEqual(self.plane._retirement_recovery_issues(), ())

    def test_cli_exposes_only_the_guarded_retirement_command(self) -> None:
        args = autopilot.parser().parse_args([
            "retire-receipt-branch", autopilot.EXPLORER_RETIREMENT["retirement_id"], "--actor", "test:recovery",
        ])
        self.assertEqual(args.command, "retire-receipt-branch")
        self.assertEqual(args.remote, "origin")


if __name__ == "__main__":
    unittest.main()
