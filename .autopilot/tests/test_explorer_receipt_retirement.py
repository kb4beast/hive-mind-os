from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import autopilot  # noqa: E402


class ExplorerReceiptRetirementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        shutil.copytree(Path(__file__).resolve().parents[1], self.root / ".autopilot")
        control = self.root / ".autopilot" / "control-plane.json"
        value = json.loads(control.read_text(encoding="utf-8"))
        value["verify_git_objects"] = False
        control.write_text(json.dumps(value), encoding="utf-8")
        self.plane = autopilot.ControlPlane(self.root)
        self.record = autopilot.EXPLORER_RETIREMENT

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _ready(self, plane: autopilot.ControlPlane | None = None) -> autopilot.ControlPlane:
        plane = plane or self.plane
        plane._origin_is_configured_repository = lambda _record: True  # type: ignore[method-assign]
        plane.current_target_sha = lambda: self.record["target_sha"]  # type: ignore[method-assign]
        plane.target_requires_reconciliation = lambda: False  # type: ignore[method-assign]
        plane._snapshot_digest = lambda: "snapshot"  # type: ignore[method-assign]
        plane._reconciliation_digest = lambda: "reconciliation"  # type: ignore[method-assign]
        return plane

    def test_sealed_record_binds_canonical_court_and_rejects_tampering(self) -> None:
        self.assertEqual(self.plane.receipt_retirement_issues(), ())
        court = self.root / ".autopilot" / "receipt-branch-retirement-court.json"
        value = json.loads(court.read_text(encoding="utf-8"))
        value["decision"] = "ADOPT"
        court.write_text(json.dumps(value), encoding="utf-8")
        self.assertTrue(self.plane.receipt_retirement_issues())
        document = self.root / ".autopilot" / "receipt-branch-retirements.json"
        value = json.loads(document.read_text(encoding="utf-8"))
        value["receipt_branch_retirements"].append(dict(value["receipt_branch_retirements"][0]))
        document.write_text(json.dumps(value), encoding="utf-8")
        self.assertTrue(self.plane.receipt_retirement_issues())

    def test_no_remote_injection_surface_exists(self) -> None:
        args = autopilot.parser().parse_args([
            "retire-receipt-branch", self.record["retirement_id"], "--actor", "test:builder",
        ])
        self.assertFalse(hasattr(args, "remote"))
        with self.assertRaises(TypeError):
            self.plane.retire_receipt_branch(self.record["retirement_id"], actor="test", remote="evil")  # type: ignore[call-arg]

    def test_pushurl_and_rewrite_injection_cannot_mutate_disposable_foreign_remote(self) -> None:
        foreign = self.root / "foreign.git"

        def run(*args: str) -> None:
            subprocess.run(args, cwd=self.root, check=True, capture_output=True, text=True)

        run("git", "init")
        run("git", "remote", "add", "origin", self.record["origin_url"])
        self.assertTrue(self.plane._origin_is_configured_repository(self.record))
        run("git", "init", "--bare", str(foreign))
        run("git", "config", "--add", "remote.origin.pushurl", str(foreign))
        run("git", "config", "--add", "remote.origin.pushurl", str(foreign / "second"))
        self.assertFalse(self.plane._origin_is_configured_repository(self.record))
        with self.assertRaisesRegex(autopilot.ClaimError, "configured origin repository identity"):
            self.plane.retire_receipt_branch(self.record["retirement_id"], actor="test:builder")
        refs = subprocess.run(("git", "--git-dir", str(foreign), "for-each-ref"), check=True, capture_output=True, text=True)
        self.assertEqual(refs.stdout, "")
        run("git", "config", "--unset-all", "remote.origin.pushurl")
        run("git", "config", "url.https://foreign.invalid/.pushInsteadOf", self.record["origin_url"])
        self.assertFalse(self.plane._origin_is_configured_repository(self.record))
        run("git", "config", "--unset-all", "url.https://foreign.invalid/.pushInsteadOf")
        with mock.patch.dict(os.environ, {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "remote.origin.pushurl",
            "GIT_CONFIG_VALUE_0": str(foreign),
        }, clear=False):
            self.assertFalse(self.plane._origin_is_configured_repository(self.record))
        with mock.patch.dict(os.environ, {"GIT_CONFIG_PARAMETERS": "'remote.origin.pushurl=foreign'"}, clear=False):
            self.assertFalse(self.plane._origin_is_configured_repository(self.record))
        self.assertEqual(refs.stdout, "")

    def test_moved_source_and_archive_collision_never_push(self) -> None:
        plane = self._ready()
        commands: list[tuple[str, ...]] = []

        def git(args, *, check=False, environment=None):
            command = tuple(args)
            commands.append(command)
            if command[0] == "ls-remote" and command[-1].startswith("refs/heads/"):
                return subprocess.CompletedProcess(command, 0, f"{'a' * 40}\t{command[-1]}\n", "")
            if command[0] == "ls-remote":
                return subprocess.CompletedProcess(command, 0, f"{'b' * 40}\t{command[-1]}\n", "")
            self.fail(f"unexpected mutation: {command}")

        plane._git = git  # type: ignore[method-assign]
        with self.assertRaises(autopilot.ClaimError):
            plane.retire_receipt_branch(self.record["retirement_id"], actor="test:builder")
        self.assertFalse(any(command[0] == "push" for command in commands))

    def test_source_race_before_atomic_transaction_never_pushes(self) -> None:
        plane = self._ready()
        expected = self.record["expected_remote_head"]
        calls = 0
        pushed = False

        def remote(reference: str) -> str | None:
            nonlocal calls
            calls += 1
            if reference == self.record["archive_ref"]:
                return None
            return expected if calls < 3 else "f" * 40

        plane._remote_ref_sha = remote  # type: ignore[method-assign]
        plane._git = lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "", "")  # type: ignore[method-assign]
        plane._retirement_history_issues = lambda _record: ()  # type: ignore[method-assign]
        plane._create_archive_commit = lambda _record: "c" * 40  # type: ignore[method-assign]
        with self.assertRaises(autopilot.ClaimError):
            plane.retire_receipt_branch(self.record["retirement_id"], actor="test:builder")
        self.assertFalse(pushed)

    def test_atomic_push_has_both_leases_and_writes_audit_only_after_verification(self) -> None:
        plane = self._ready()
        expected = self.record["expected_remote_head"]
        state = {"source": expected, "archive": None}
        pushes: list[tuple[str, ...]] = []
        plane._retirement_history_issues = lambda _record: ()  # type: ignore[method-assign]
        plane._create_archive_commit = lambda _record: "c" * 40  # type: ignore[method-assign]

        def remote(reference: str) -> str | None:
            return state["source"] if reference.startswith("refs/heads/") else state["archive"]

        def git(args, *, check=False, environment=None):
            command = tuple(args)
            if command[0] == "fetch":
                return subprocess.CompletedProcess(command, 0, "", "")
            if command[0] == "push":
                pushes.append(command)
                self.assertIn("--atomic", command)
                self.assertIn(f"--force-with-lease=refs/heads/{self.record['branch']}:{expected}", command)
                self.assertIn(f"--force-with-lease={self.record['archive_ref']}:", command)
                state["archive"], state["source"] = "c" * 40, None
                return subprocess.CompletedProcess(command, 0, "", "")
            self.fail(f"unexpected command: {command}")

        plane._remote_ref_sha = remote  # type: ignore[method-assign]
        plane._git = git  # type: ignore[method-assign]
        plane._verify_archive = lambda _commit, _record: None  # type: ignore[method-assign]
        result = plane.retire_receipt_branch(self.record["retirement_id"], actor="test:builder")
        self.assertEqual(result["archive_commit"], "c" * 40)
        self.assertEqual(len(pushes), 1)
        self.assertTrue((plane.state_dir / autopilot.RETIREMENT_AUDIT).is_file())

    def test_atomic_delete_failure_never_writes_execution_evidence(self) -> None:
        plane = self._ready()
        expected = self.record["expected_remote_head"]
        plane._remote_ref_sha = lambda ref: expected if ref.startswith("refs/heads/") else None  # type: ignore[method-assign]
        plane._retirement_history_issues = lambda _record: ()  # type: ignore[method-assign]
        plane._create_archive_commit = lambda _record: "c" * 40  # type: ignore[method-assign]

        def git(args, *, check=False, environment=None):
            command = tuple(args)
            if command[0] == "fetch":
                return subprocess.CompletedProcess(command, 0, "", "")
            if command[0] == "push":
                return subprocess.CompletedProcess(command, 1, "", "remote rejected delete")
            self.fail(f"unexpected command: {command}")

        plane._git = git  # type: ignore[method-assign]
        with self.assertRaisesRegex(autopilot.ClaimError, "atomic archive/delete failed"):
            plane.retire_receipt_branch(self.record["retirement_id"], actor="test:builder")
        self.assertFalse(plane.retirement_execution_path.exists())
        self.assertFalse((plane.state_dir / autopilot.RETIREMENT_AUDIT).exists())

    def test_forged_archive_and_active_claim_are_fail_closed(self) -> None:
        plane = self._ready()
        claim = plane.claim_path("EXPLORER-310")
        claim.parent.mkdir(parents=True, exist_ok=True)
        claim.write_text("{}", encoding="utf-8")
        with self.assertRaises(autopilot.ClaimError):
            plane.retire_receipt_branch(self.record["retirement_id"], actor="test:builder")
        claim.unlink()
        plane._remote_ref_sha = lambda ref: None if ref.startswith("refs/heads/") else "d" * 40  # type: ignore[method-assign]
        plane._git = lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "", "")  # type: ignore[method-assign]
        plane._verify_archive = lambda *_args: (_ for _ in ()).throw(autopilot.ClaimError("forged"))  # type: ignore[method-assign]
        with self.assertRaisesRegex(autopilot.ClaimError, "forged"):
            plane.retire_receipt_branch(self.record["retirement_id"], actor="test:builder")

    def test_fresh_snapshot_and_reconciliation_are_required_before_dispatch(self) -> None:
        plane = self._ready()
        execution = {
            "schema_version": 1, "kind": autopilot.RETIREMENT_KIND, "status": "RETIRED",
            "retirement_id": self.record["retirement_id"], "archive_commit": "c" * 40,
            "archive_ref": self.record["archive_ref"], "source_head": self.record["expected_remote_head"],
            "snapshot_digest": "snapshot", "reconciliation_digest": "reconciliation",
            "actor": "test", "completed_at": "2026-08-11T00:00:00+00:00",
        }
        autopilot.atomic_write_json(plane.retirement_execution_path, execution)
        self.assertTrue(plane._recovery_issues())
        snapshot = self.root / "snapshot.json"
        snapshot.write_text(json.dumps({"target_sha": self.record["target_sha"], "pull_requests": [], "branches": []}), encoding="utf-8")
        plane.install_github_snapshot(snapshot)
        plane.reconcile(self.record["target_sha"], actor="test", reason="fresh after retirement")
        self.assertEqual(plane._recovery_issues(), ())
        self.assertEqual(json.loads((plane.state_dir / "github-state.json").read_text()), json.loads(snapshot.read_text()))

    def test_real_bare_remote_retains_archive_and_fresh_clone_resumes(self) -> None:
        source = Path(__file__).resolve().parents[2]
        remote = self.root / "origin.git"
        clone = self.root / "clone"

        def run(*args: str, cwd: Path | None = None) -> None:
            subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)

        run("git", "init", "--bare", str(remote))
        run("git", "push", str(remote), f"{self.record['receipt_commit']}:refs/heads/{self.record['branch']}", cwd=source)
        run("git", "clone", "--no-local", str(remote), str(clone))
        shutil.copytree(source / ".autopilot", clone / ".autopilot")
        control = clone / ".autopilot" / "control-plane.json"
        value = json.loads(control.read_text(encoding="utf-8")); value["verify_git_objects"] = False
        control.write_text(json.dumps(value), encoding="utf-8")
        plane = self._ready(autopilot.ControlPlane(clone))
        result = plane.retire_receipt_branch(self.record["retirement_id"], actor="test:builder")
        archive = self.record["archive_ref"]
        self.assertIsNone(plane._remote_ref_sha(f"refs/heads/{self.record['branch']}"))
        self.assertEqual(plane._remote_ref_sha(archive), result["archive_commit"])
        fresh = self.root / "fresh"
        run("git", "clone", "--no-local", str(remote), str(fresh))
        shutil.copytree(source / ".autopilot", fresh / ".autopilot")
        fresh_control = fresh / ".autopilot" / "control-plane.json"
        fresh_value = json.loads(fresh_control.read_text(encoding="utf-8")); fresh_value["verify_git_objects"] = False
        fresh_control.write_text(json.dumps(fresh_value), encoding="utf-8")
        resumed = self._ready(autopilot.ControlPlane(fresh))
        resumed_result = resumed.retire_receipt_branch(self.record["retirement_id"], actor="test:recovery")
        self.assertEqual(resumed_result["archive_commit"], result["archive_commit"])


if __name__ == "__main__":
    unittest.main()
