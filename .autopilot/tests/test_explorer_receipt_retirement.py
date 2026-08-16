from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fixture_support import copy_autopilot_fixture, ready_runtime

BIN = Path(__file__).resolve().parents[1] / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import autopilot  # noqa: E402
import controller as runtime_controller  # noqa: E402


class ExplorerReceiptRetirementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.host_base = self.root / "host-authority-base"
        self.host_base_patch = mock.patch.object(
            runtime_controller,
            "_host_runtime_base_dir",
            return_value=self.host_base,
        )
        self.host_base_patch.start()
        self.host_runtime = self.root / "host-runtime"
        runtime_controller.initialize_host_runtime(self.host_runtime)
        copy_autopilot_fixture(Path(__file__).resolve().parents[1], self.root / ".autopilot")
        control = self.root / ".autopilot" / "control-plane.json"
        value = json.loads(control.read_text(encoding="utf-8"))
        value["verify_git_objects"] = False
        runtime_controller.atomic_write_json(control, value)
        self.plane = autopilot.ControlPlane(
            self.root, host_runtime_dir=self.host_runtime
        )
        self.record = autopilot.EXPLORER_RETIREMENT

    def tearDown(self) -> None:
        self.host_base_patch.stop()
        self.temporary.cleanup()

    def _ready(self, plane: autopilot.ControlPlane | None = None) -> autopilot.ControlPlane:
        plane = plane or self.plane
        if not (plane.repo_root / ".git").exists():
            subprocess.run(
                ("git", "init", "--quiet", str(plane.repo_root)),
                check=True,
                capture_output=True,
            )
        configured_origin = subprocess.run(
            ("git", "-C", str(plane.repo_root), "remote", "get-url", "origin"),
            check=False,
            capture_output=True,
            text=True,
        )
        if configured_origin.returncode != 0:
            subprocess.run(
                (
                    "git",
                    "-C",
                    str(plane.repo_root),
                    "remote",
                    "add",
                    "origin",
                    str(plane.repo_root),
                ),
                check=True,
                capture_output=True,
            )
        ready_runtime(runtime_controller, plane.repo_root)
        with plane.host_lock():
            runtime_controller.bind_host_repository_runtime(
                plane.host_runtime_dir,
                repository=str(plane.control["target"]["repository"]),
                coordination_dir=plane.coordination_dir,
                repo_root=plane.repo_root,
                transport_digest=str(plane.repository_identity["transport_digest"]),
                bound_at=runtime_controller.format_time(plane.clock()),
            )
            with plane.arbiter_lock():
                runtime_controller.initialize_execution_namespace(
                    plane.coordination_dir, plane.execution_identity
                )
                plane.bind_canonical_remote_transport_identity()
        execution_target = "d" * 40
        plane._origin_is_configured_repository = lambda _record: True  # type: ignore[method-assign]
        plane.current_target_sha = lambda: execution_target  # type: ignore[method-assign]
        plane.target_requires_reconciliation = lambda: False  # type: ignore[method-assign]
        plane._snapshot_digest = lambda: "snapshot"  # type: ignore[method-assign]
        plane._reconciliation_digest = lambda: "reconciliation"  # type: ignore[method-assign]
        plane.git_object_exists = lambda _sha: True  # type: ignore[method-assign]
        plane.is_ancestor = lambda ancestor, descendant: ancestor == self.record["capability_commit"] and descendant == execution_target  # type: ignore[method-assign]
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
        appeals = self.root / ".autopilot" / "receipt-branch-retirement-appeals.json"
        value = json.loads(appeals.read_text(encoding="utf-8"))
        value["decision"] = "QUARANTINE"
        appeals.write_text(json.dumps(value), encoding="utf-8")
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
        # Historical recovery seeding above deliberately uses digest sentinels. The
        # fresh observation must exercise the real digest implementation or its
        # installed bytes can never match the shared dispatcher watermark.
        plane._snapshot_digest = autopilot.ControlPlane._snapshot_digest.__get__(  # type: ignore[method-assign]
            plane, autopilot.ControlPlane
        )
        plane._reconciliation_digest = (  # type: ignore[method-assign]
            autopilot.ControlPlane._reconciliation_digest.__get__(
                plane, autopilot.ControlPlane
            )
        )
        observation = plane.begin_github_snapshot_observation(actor="test:snapshot")
        branch_observations = [
            {
                "node_id": item["node_id"],
                "branch": item["branch"],
                "fetch_ref": item["fetch_ref"],
                "present": False,
                "sha": None,
            }
            for item in observation["branch_fetches"]
        ]
        ls_remote_argv = [
            "git",
            "--no-replace-objects",
            "-c",
            f"core.hooksPath={os.devnull}",
            "ls-remote",
            "--heads",
            "origin",
        ]
        raw_stdout = (
            f"{'d' * 40}\trefs/heads/{observation['target_branch']}\n"
        )
        source_material = {
            "schema_version": 1,
            "kind": autopilot.SNAPSHOT_SOURCE_REF_OBSERVATION_KIND,
            "execution_namespace": observation["execution_namespace"],
            "execution_id": observation["execution_id"],
            "observation_id": observation["observation_id"],
            "repository": observation["repository"],
            "repository_transport_digest": plane.repository_identity[
                "transport_digest"
            ],
            "target_ref": f"refs/heads/{observation['target_branch']}",
            "target_sha": "d" * 40,
            "branch_refs": [
                {
                    "node_id": item["node_id"],
                    "branch": item["branch"],
                    "ref": f"refs/heads/{item['branch']}",
                    "present": False,
                    "sha": None,
                }
                for item in observation["branch_fetches"]
            ],
            "ls_remote_argv": ls_remote_argv,
            "raw_stdout": raw_stdout,
            "raw_stdout_digest": "sha256:"
            + autopilot.sha256(raw_stdout.encode("utf-8")).hexdigest(),
            "observed_at": "2026-08-14T00:00:00+00:00",
        }
        candidate = {
            "schema_version": 1,
            "kind": autopilot.SNAPSHOT_CANDIDATE_KIND,
            "execution_namespace": observation["execution_namespace"],
            "execution_id": observation["execution_id"],
            "observation_id": observation["observation_id"],
            "observation_epoch": observation["observation_epoch"],
            "fetch_ref": observation["fetch_ref"],
            "repository": observation["repository"],
            "target_branch": observation["target_branch"],
            "target_sha": "d" * 40,
            "branch_observations": branch_observations,
            "pull_requests": [],
            "raw_pull_requests": [],
            "branches": [],
            "github_query": {
                "offline": True,
                "evidence_available": False,
                "complete": False,
                "node_queries": [],
                "exit_code": 0,
            },
            "git_query": {
                "target_refspec": (
                    f"+refs/heads/{observation['target_branch']}:"
                    f"{observation['fetch_ref']}"
                ),
                "branch_refspecs": [],
                "ls_remote_argv": ls_remote_argv,
            },
            "source_ref_observation": {
                **source_material,
                "record_id": autopilot.digest_json(source_material),
            },
        }
        candidate["candidate_id"] = autopilot.digest_json(candidate)
        snapshot = self.root / "snapshot.json"
        snapshot.write_text(json.dumps(candidate), encoding="utf-8")
        plane.install_github_snapshot(
            snapshot,
            observation_id=str(observation["observation_id"]),
        )
        plane.reconcile("d" * 40, actor="test", reason="fresh after retirement")
        self.assertEqual(plane._recovery_issues(), ())
        self.assertEqual(
            json.loads(plane.github_snapshot_path.read_text()),
            candidate,
        )

    def test_execution_requires_integrated_capability_and_current_snapshot_reconciliation(self) -> None:
        plane = self._ready()
        plane.is_ancestor = lambda _ancestor, _descendant: False  # type: ignore[method-assign]
        with self.assertRaisesRegex(autopilot.ClaimError, "containing the sealed capability commit"):
            plane.retire_receipt_branch(self.record["retirement_id"], actor="test:builder")
        plane = self._ready()
        plane._snapshot_digest = lambda: None  # type: ignore[method-assign]
        with self.assertRaisesRegex(autopilot.ClaimError, "snapshot and reconciliation evidence"):
            plane.retire_receipt_branch(self.record["retirement_id"], actor="test:builder")
        plane = self._ready()
        plane._reconciliation_digest = lambda: None  # type: ignore[method-assign]
        with self.assertRaisesRegex(autopilot.ClaimError, "snapshot and reconciliation evidence"):
            plane.retire_receipt_branch(self.record["retirement_id"], actor="test:builder")
        plane = self._ready()
        plane.target_requires_reconciliation = lambda: True  # type: ignore[method-assign]
        with self.assertRaisesRegex(autopilot.ClaimError, "current singleton target reconciliation"):
            plane.retire_receipt_branch(self.record["retirement_id"], actor="test:builder")

    def test_real_bare_remote_retains_archive_and_fresh_clone_resumes(self) -> None:
        source = Path(__file__).resolve().parents[2]
        seed = self.root / "seed"
        remote = self.root / "origin.git"
        clone = self.root / "clone"

        def run(*args: str, cwd: Path | None = None) -> str:
            return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()

        run("git", "init", str(seed))
        run("git", "config", "user.name", "Fixture", cwd=seed)
        run("git", "config", "user.email", "fixture@example.invalid", cwd=seed)
        (seed / "candidate.txt").write_text("candidate\n", encoding="utf-8")
        run("git", "add", "candidate.txt", cwd=seed)
        run("git", "commit", "-m", "synthetic candidate", cwd=seed)
        candidate = run("git", "rev-parse", "HEAD", cwd=seed)
        receipt_payload = {
            "node_id": "EXPLORER-310",
            "branch": "autopilot/explorer-310",
            "plan_fingerprint": self.record["plan_fingerprint"],
            "contract_version": self.record["contract_version"],
            "final_commit": candidate,
        }
        receipt_message = self.plane._receipt_message(receipt_payload)
        tree = run("git", "rev-parse", "HEAD^{tree}", cwd=seed)
        receipt = run("git", "commit-tree", tree, "-p", candidate, "-m", receipt_message, cwd=seed)
        synthetic = dict(self.record)
        synthetic.update({
            "candidate_commit": candidate,
            "receipt_commit": receipt,
            "expected_remote_head": receipt,
            "archive_ref": f"refs/hive-mind-autopilot/quarantine/explorer-310/{receipt}",
        })
        run("git", "init", "--bare", str(remote))
        run("git", "push", str(remote), f"{receipt}:refs/heads/{synthetic['branch']}", cwd=seed)
        run("git", "clone", "--no-local", str(remote), str(clone))
        copy_autopilot_fixture(source / ".autopilot", clone / ".autopilot")
        control = clone / ".autopilot" / "control-plane.json"
        value = json.loads(control.read_text(encoding="utf-8"))
        value["verify_git_objects"] = False
        runtime_controller.atomic_write_json(control, value)
        prior_record = self.record
        self.record = synthetic
        plane = self._ready(
            autopilot.ControlPlane(clone, host_runtime_dir=self.host_runtime)
        )
        plane._retirement_record = lambda _retirement_id: synthetic  # type: ignore[method-assign]
        result = plane.retire_receipt_branch(synthetic["retirement_id"], actor="test:builder")
        archive = synthetic["archive_ref"]
        self.assertIsNone(plane._remote_ref_sha(f"refs/heads/{synthetic['branch']}"))
        self.assertEqual(plane._remote_ref_sha(archive), result["archive_commit"])
        fresh = self.root / "fresh"
        run("git", "clone", "--no-local", str(remote), str(fresh))
        copy_autopilot_fixture(source / ".autopilot", fresh / ".autopilot")
        fresh_control = fresh / ".autopilot" / "control-plane.json"
        fresh_value = json.loads(fresh_control.read_text(encoding="utf-8"))
        fresh_value["verify_git_objects"] = False
        runtime_controller.atomic_write_json(fresh_control, fresh_value)
        resumed = self._ready(
            autopilot.ControlPlane(
                fresh,
                state_dir=plane.coordination_dir,
                host_runtime_dir=self.host_runtime,
            )
        )
        resumed._retirement_record = lambda _retirement_id: synthetic  # type: ignore[method-assign]
        resumed_result = resumed.retire_receipt_branch(synthetic["retirement_id"], actor="test:recovery")
        self.assertEqual(resumed_result["archive_commit"], result["archive_commit"])
        self.record = prior_record


if __name__ == "__main__":
    unittest.main()
