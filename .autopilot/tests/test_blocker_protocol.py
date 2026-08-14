from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Mapping

from fixture_support import copy_autopilot_fixture

MODULE_PATH = Path(__file__).resolve().parents[1] / "bin" / "controller.py"
SPEC = importlib.util.spec_from_file_location("blocker_controller", MODULE_PATH)
assert SPEC and SPEC.loader
controller = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = controller
SPEC.loader.exec_module(controller)


class BlockerProtocolTests(unittest.TestCase):
    @staticmethod
    def _git(repo: Path, *args: str) -> str:
        completed = subprocess.run(
            ("git", "-C", str(repo), *args),
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        return completed.stdout.strip()

    @staticmethod
    def _autopilot(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            (
                sys.executable,
                str(repo / ".autopilot" / "bin" / "autopilot.py"),
                "--repo-root",
                str(repo),
                *args,
            ),
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            timeout=60,
        )

    def _real_linked_validation_worktrees(self, root: Path) -> tuple[Path, Path, Path]:
        origin = root / "origin.git"
        seed = root / "seed"
        first = root / "worktree-a"
        second = root / "worktree-b"
        subprocess.run(
            ("git", "init", "--bare", str(origin)),
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        self._git(root, "init", str(seed))
        self._git(seed, "config", "user.name", "Validation Mutex Fixture")
        self._git(seed, "config", "user.email", "validation-mutex@hive-mind.invalid")
        copy_autopilot_fixture(
            Path(__file__).resolve().parents[1],
            seed / ".autopilot",
        )
        self._git(seed, "add", "-f", ".autopilot")
        self._git(seed, "commit", "-m", "validation mutex fixture")
        target_branch = controller.read_json(
            seed / ".autopilot" / "control-plane.json"
        )["target"]["branch"]
        self._git(seed, "branch", target_branch, "HEAD")
        self._git(seed, "remote", "add", "origin", str(origin.resolve()))
        self._git(seed, "push", "origin", f"HEAD:refs/heads/{target_branch}")
        self._git(seed, "worktree", "add", "--detach", str(first), "HEAD")
        self._git(seed, "worktree", "add", "--detach", str(second), "HEAD")
        # The mutex authenticates repository identity, not the disposable transport.
        # Switch to the exact secret-free production identity after constructing the
        # local worktrees; none of these mutex tests performs a remote Git operation.
        self._git(
            seed,
            "remote",
            "set-url",
            "origin",
            "https://github.com/kb4beast/hive-mind-os.git",
        )
        return seed, first, second

    def test_blocker_packet_names_cause_fix_and_retry_condition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = Path(__file__).resolve().parents[1]
            copy_autopilot_fixture(source, root / ".autopilot")
            control = controller.read_json(root / ".autopilot" / "control-plane.json")
            control["verify_git_objects"] = False
            controller.atomic_write_json(root / ".autopilot" / "control-plane.json", control)
            plane = controller.ControlPlane(
                root,
                validation_mutex_root=root / ".autopilot" / "state" / "validation-mutex",
            )
            packet = plane.record_blocker(
                "ARCH-100",
                category="remote-authority",
                cause="remote TLS revocation validation failed",
                fix="restore certificate revocation validation or provide a trusted network path",
                retry_when="remote inspection succeeds without disabling TLS controls",
                attempted_command=["git", "ls-remote", "origin"],
                evidence_refs=["test:evidence"],
            )
            self.assertTrue(packet["blocker_id"])
            self.assertEqual(packet["status"], "OPEN")
            self.assertTrue(plane.safe_retry_allowed(packet))
            self.assertEqual(packet["recovery_action"]["action"], "REPORT_BLOCKER")
            stored = root / ".autopilot" / "state" / "blockers" / "ARCH-100.jsonl"
            self.assertIn("retry_when", stored.read_text(encoding="utf-8"))

    def test_permission_does_not_authorize_security_bypass(self) -> None:
        self.assertFalse(
            controller.ControlPlane.safe_retry_allowed(
                {"fix": "disable TLS certificate revocation", "retry_when": "retry"}
            )
        )

    def test_stale_dispatcher_release_requests_orchestrator_subtask(self) -> None:
        action = controller.ControlPlane.recovery_action(
            {"category": "dispatcher", "cause": "dispatcher release is stale", "fix": "rerun dispatch"}
        )
        self.assertEqual(action["action"], "SPAWN_SUBTASK")
        self.assertEqual(action["role"], "orchestrator")
        self.assertEqual(
            action["required_sequence"],
            list(controller.SUBTASK_EXECUTION_SEQUENCE),
        )
        self.assertLess(
            action["required_sequence"].index("dispatch_explicit_start_now"),
            action["required_sequence"].index("claim_remote_node_branch"),
        )

    def test_git_transport_allowlist_accepts_proxy_only_in_child_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = Path(__file__).resolve().parents[1]
            copy_autopilot_fixture(source, root / ".autopilot")
            control = controller.read_json(root / ".autopilot" / "control-plane.json")
            control["verify_git_objects"] = False
            controller.atomic_write_json(root / ".autopilot" / "control-plane.json", control)
            original = controller.os.environ.get("HTTPS_PROXY")
            controller.os.environ["HTTPS_PROXY"] = "https://proxy.example.test:8443"
            try:
                environment = {
                    "PATH": controller.os.environ.get("PATH", ""),
                    "GIT_TERMINAL_PROMPT": "0",
                }
                for key in controller.SAFE_GIT_TRANSPORT_ENVIRONMENT_KEYS:
                    value = controller.os.environ.get(key)
                    if value and not any(character in value for character in "\r\n"):
                        if key.lower() in {"http_proxy", "https_proxy"}:
                            parsed = controller.urlparse(value)
                            if parsed.scheme in {"http", "https", "socks5", "socks5h"} and parsed.hostname:
                                environment[key] = value
                        else:
                            environment[key] = value
                self.assertEqual(environment["HTTPS_PROXY"], "https://proxy.example.test:8443")
                self.assertNotIn("GITHUB_TOKEN", environment)
            finally:
                if original is None:
                    controller.os.environ.pop("HTTPS_PROXY", None)
                else:
                    controller.os.environ["HTTPS_PROXY"] = original

    def test_human_question_is_resolved_into_immediate_safe_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = Path(__file__).resolve().parents[1]
            copy_autopilot_fixture(source, root / ".autopilot")
            control = controller.read_json(root / ".autopilot" / "control-plane.json")
            control["verify_git_objects"] = False
            controller.atomic_write_json(root / ".autopilot" / "control-plane.json", control)
            plane = controller.ControlPlane(
                root,
                validation_mutex_root=root / ".autopilot" / "state" / "validation-mutex",
            )
            opened = plane.record_human_question(
                "ARCH-100",
                question="Which trusted proxy environment is available?",
                cause="Git remote inspection cannot start without the runtime transport path",
                attempted_command=["git", "ls-remote", "origin"],
            )
            resolved = plane.resolve_human_question(
                "ARCH-100",
                opened["question_id"],
                answer="Use the existing trusted HTTPS proxy environment.",
                fix="Pass validated HTTP_PROXY, HTTPS_PROXY, and NO_PROXY to the Git subprocess.",
                retry_command=["git", "ls-remote", "origin"],
            )
            self.assertEqual(resolved["recovery_action"]["action"], "RETRY_NOW")
            self.assertNotIn("trusted HTTPS proxy", resolved["answer_digest"])
            text = (root / ".autopilot" / "state" / "questions" / "ARCH-100.jsonl").read_text()
            self.assertIn("QUESTION_OPENED", text)
            self.assertIn("QUESTION_RESOLVED", text)

    def test_subtask_wave_cannot_end_on_idle_or_recoverable_children(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = Path(__file__).resolve().parents[1]
            copy_autopilot_fixture(source, root / ".autopilot")
            control = controller.read_json(root / ".autopilot" / "control-plane.json")
            control["verify_git_objects"] = False
            controller.atomic_write_json(root / ".autopilot" / "control-plane.json", control)
            plane = controller.ControlPlane(root)
            plane.start_subtask_wave(
                "wave-l1",
                ("ACCEPT-240", "CONSULT-210"),
                target_sha="0" * 40,
            )
            active = plane.poll_subtask_wave(
                "wave-l1",
                {"ACCEPT-240": "IDLE_UNCOLLECTED", "CONSULT-210": "BLOCKED_RECOVERABLE"},
            )
            self.assertFalse(active["may_end_turn"])
            self.assertFalse(active["target_mutation_allowed"])
            self.assertEqual(active["recovery_actions"]["ACCEPT-240"], "COLLECT_RESULT_NOW")
            self.assertEqual(active["recovery_actions"]["CONSULT-210"], "APPLY_FIX_AND_RETRY_NOW")
            settled = plane.poll_subtask_wave(
                "wave-l1",
                {"ACCEPT-240": "SUCCEEDED", "CONSULT-210": "BLOCKED_EXTERNAL_AUTHORITY"},
            )
            self.assertTrue(settled["may_end_turn"])
            self.assertTrue(settled["target_mutation_allowed"])

    def test_stale_snapshot_recovery_is_ordered_and_stash_safe(self) -> None:
        action = controller.ControlPlane.recovery_action(
            {
                "category": "snapshot",
                "cause": "validated snapshot target mismatch after release advance",
                "fix": "refresh stale snapshot and recover child work",
            }
        )
        self.assertEqual(action["action"], "SPAWN_SUBTASK")
        sequence = action["required_sequence"]
        self.assertEqual(sequence, list(controller.STALE_TARGET_RECOVERY_SEQUENCE))
        self.assertLess(sequence.index("refresh_validated_github_snapshot"), sequence.index("install_snapshot_and_reconcile"))
        self.assertLess(sequence.index("doctor_status_dispatch_and_reclaim"), sequence.index("apply_exact_node_named_stash"))
        self.assertTrue(all("stash@" not in step for step in sequence))

    def test_repository_wide_validation_has_singleton_lease(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = Path(__file__).resolve().parents[1]
            copy_autopilot_fixture(source, root / ".autopilot")
            (root / ".autopilot" / "state" / "global-validation-lease.json").unlink(
                missing_ok=True
            )
            control = controller.read_json(root / ".autopilot" / "control-plane.json")
            control["verify_git_objects"] = False
            controller.atomic_write_json(root / ".autopilot" / "control-plane.json", control)
            plane = controller.ControlPlane(
                root,
                validation_mutex_root=root / ".autopilot" / "state" / "validation-mutex",
            )
            self.assertEqual(
                plane.validation_lease_path,
                root
                / ".autopilot"
                / "state"
                / "validation-mutex"
                / "global-validation-lease.json",
            )
            lease = plane.acquire_global_validation_lease("ACCEPT-240", "worker:accept")
            self.assertEqual(lease["status"], "ACTIVE")
            self.assertEqual(lease["scope_kind"], "non-git-fixture")
            with self.assertRaises(controller.AutopilotError):
                plane.acquire_global_validation_lease("CONSULT-210", "worker:consult")
            plane.release_global_validation_lease(
                "ACCEPT-240",
                "worker:accept",
                lease_id=str(lease["lease_id"]),
            )
            second = plane.acquire_global_validation_lease("CONSULT-210", "worker:consult")
            self.assertEqual(second["node_id"], "CONSULT-210")

    def test_validation_lease_concurrent_acquisition_has_exactly_one_winner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_autopilot_fixture(Path(__file__).resolve().parents[1], root / ".autopilot")
            control = controller.read_json(root / ".autopilot" / "control-plane.json")
            control["verify_git_objects"] = False
            controller.atomic_write_json(root / ".autopilot" / "control-plane.json", control)
            plane = controller.ControlPlane(
                root,
                validation_mutex_root=root / ".autopilot" / "state" / "validation-mutex",
            )
            barrier = threading.Barrier(2)
            outcomes: list[str] = []

            def acquire(node_id: str, owner: str) -> None:
                barrier.wait()
                try:
                    plane.acquire_global_validation_lease(node_id, owner)
                    outcomes.append("won")
                except controller.AutopilotError:
                    outcomes.append("lost")

            threads = [
                threading.Thread(target=acquire, args=("ACCEPT-240", "worker:accept")),
                threading.Thread(target=acquire, args=("CONSULT-210", "worker:consult")),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(sorted(outcomes), ["lost", "won"])

    def test_validation_mutex_is_shared_across_real_linked_worktrees(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            seed, first, second = self._real_linked_validation_worktrees(Path(directory))
            planes = (controller.ControlPlane(first), controller.ControlPlane(second))
            self.assertEqual(planes[0].validation_lease_path, planes[1].validation_lease_path)
            common_dir = Path(self._git(seed, "rev-parse", "--path-format=absolute", "--git-common-dir"))
            self.assertTrue(planes[0].validation_lease_path.is_relative_to(common_dir))

            barrier = threading.Barrier(2)
            outcomes: list[tuple[str, Mapping[str, object] | None]] = []

            def acquire(plane: controller.ControlPlane, node_id: str, owner: str) -> None:
                barrier.wait()
                try:
                    lease = plane.acquire_global_validation_lease(node_id, owner)
                    outcomes.append(("won", lease))
                except controller.AutopilotError:
                    outcomes.append(("lost", None))

            threads = (
                threading.Thread(
                    target=acquire,
                    args=(planes[0], "ACCEPT-240", "worker:worktree-a"),
                ),
                threading.Thread(
                    target=acquire,
                    args=(planes[1], "CONSULT-210", "worker:worktree-b"),
                ),
            )
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(sorted(result for result, _lease in outcomes), ["lost", "won"])
            winner_index = next(
                index for index, outcome in enumerate(outcomes) if outcome[0] == "won"
            )
            winning_lease = outcomes[winner_index][1]
            assert winning_lease is not None
            winning_plane = next(
                plane
                for plane in planes
                if plane._held_validation_leases.get(
                    (str(winning_lease["node_id"]), str(winning_lease["owner"]))
                ) == (winning_lease["lease_id"], winning_lease["lease_token"])
            )
            losing_plane = next(plane for plane in planes if plane is not winning_plane)
            with self.assertRaisesRegex(controller.AutopilotError, "is active"):
                losing_plane.acquire_global_validation_lease(
                    str(winning_lease["node_id"]),
                    str(winning_lease["owner"]),
                )
            winning_plane.release_global_validation_lease(
                str(winning_lease["node_id"]),
                str(winning_lease["owner"]),
                lease_id=str(winning_lease["lease_id"]),
            )

    def test_validation_mutex_recovers_expired_crash_with_immutable_archive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _seed, first, second = self._real_linked_validation_worktrees(Path(directory))
            started = datetime(2030, 1, 1, tzinfo=UTC)
            crashed = controller.ControlPlane(first, clock=lambda: started)
            old = crashed.acquire_global_validation_lease(
                "ACCEPT-240",
                "worker:crashed",
                lease_minutes=1,
            )
            restarted = controller.ControlPlane(
                second,
                clock=lambda: started + timedelta(minutes=2),
            )
            with self.assertRaisesRegex(controller.AutopilotError, "ID mismatch"):
                crashed.release_global_validation_lease(
                    "ACCEPT-240",
                    "worker:crashed",
                    lease_id="sha256:" + "0" * 64,
                    lease_token=str(old["lease_token"]),
                )
            replacement = restarted.acquire_global_validation_lease(
                "CONSULT-210",
                "worker:restarted",
            )
            archive = restarted.validation_lease_archive_dir / (
                str(old["lease_id"]).replace(":", "-") + ".expired.json"
            )
            self.assertEqual(controller.read_json(archive), old)
            with self.assertRaisesRegex(controller.AutopilotError, "ID mismatch"):
                crashed.release_global_validation_lease(
                    "CONSULT-210",
                    "worker:restarted",
                    lease_id=str(old["lease_id"]),
                    lease_token=str(old["lease_token"]),
                )
            restarted.release_global_validation_lease(
                "CONSULT-210",
                "worker:restarted",
                lease_id=str(replacement["lease_id"]),
            )
            self.assertEqual(controller.read_json(archive), old)

    def test_validation_mutex_fails_closed_on_foreign_origin_and_malformed_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            seed, first, second = self._real_linked_validation_worktrees(Path(directory))
            holder = controller.ControlPlane(first)
            observer = controller.ControlPlane(second)
            lease = holder.acquire_global_validation_lease("ACCEPT-240", "worker:holder")
            original_origin = self._git(seed, "config", "--get", "remote.origin.url")
            self._git(seed, "remote", "set-url", "origin", str(Path(directory) / "foreign.git"))
            with self.assertRaisesRegex(controller.AutopilotError, "origin identity"):
                observer.acquire_global_validation_lease("CONSULT-210", "worker:observer")
            self._git(seed, "remote", "set-url", "origin", original_origin)

            malformed = dict(lease)
            malformed["unexpected"] = True
            unsigned = dict(malformed)
            unsigned.pop("lease_id")
            malformed["lease_id"] = controller.digest_json(unsigned)
            controller.atomic_write_json(holder.validation_lease_path, malformed)
            with self.assertRaisesRegex(controller.AutopilotError, "schema is malformed"):
                observer.acquire_global_validation_lease("CONSULT-210", "worker:observer")

    def test_validation_mutex_cross_process_token_release_and_replacement_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _seed, first, second = self._real_linked_validation_worktrees(Path(directory))
            holder = controller.ControlPlane(first)
            restarted = controller.ControlPlane(second)
            first_lease = holder.acquire_global_validation_lease(
                "ACCEPT-240",
                "worker:cross-process",
            )
            self.assertRegex(str(first_lease["lease_token"]), r"\A[0-9a-f]{64}\Z")
            with self.assertRaisesRegex(controller.AutopilotError, "token is required"):
                restarted.assert_global_validation_lease(
                    "ACCEPT-240",
                    "worker:cross-process",
                    lease_id=str(first_lease["lease_id"]),
                )
            with self.assertRaisesRegex(controller.AutopilotError, "token is required"):
                restarted.release_global_validation_lease(
                    "ACCEPT-240",
                    "worker:cross-process",
                    lease_id=str(first_lease["lease_id"]),
                )
            self.assertTrue(restarted.validation_lease_path.exists())
            self.assertEqual(
                restarted.assert_global_validation_lease(
                    "ACCEPT-240",
                    "worker:cross-process",
                    lease_id=str(first_lease["lease_id"]),
                    lease_token=str(first_lease["lease_token"]),
                )["lease_id"],
                first_lease["lease_id"],
            )
            restarted.release_global_validation_lease(
                "ACCEPT-240",
                "worker:cross-process",
                lease_id=str(first_lease["lease_id"]),
                lease_token=str(first_lease["lease_token"]),
            )
            with self.assertRaisesRegex(controller.AutopilotError, "is absent"):
                restarted.release_global_validation_lease(
                    "ACCEPT-240",
                    "worker:cross-process",
                    lease_id=str(first_lease["lease_id"]),
                    lease_token=str(first_lease["lease_token"]),
                )
            second_lease = restarted.acquire_global_validation_lease(
                "CONSULT-210",
                "worker:replacement",
            )
            self.assertNotEqual(first_lease["lease_token"], second_lease["lease_token"])
            with self.assertRaisesRegex(controller.AutopilotError, "identity mismatch"):
                holder.release_global_validation_lease(
                    "ACCEPT-240",
                    "worker:cross-process",
                    lease_id=str(first_lease["lease_id"]),
                    lease_token=str(first_lease["lease_token"]),
                )

    def test_validation_mutex_heartbeat_uses_revision_cas_and_remains_reclaimable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _seed, first, second = self._real_linked_validation_worktrees(Path(directory))
            started = datetime(2030, 1, 1, tzinfo=UTC)
            current_time = [started]
            holder = controller.ControlPlane(first, clock=lambda: current_time[0])
            observer = controller.ControlPlane(second, clock=lambda: current_time[0])
            initial = holder.acquire_global_validation_lease(
                "ACCEPT-240",
                "worker:long-run",
                lease_minutes=2,
            )
            current_time[0] = started + timedelta(minutes=1)
            renewed = holder.renew_global_validation_lease(
                "ACCEPT-240",
                "worker:long-run",
                lease_id=str(initial["lease_id"]),
                lease_token=str(initial["lease_token"]),
                lease_minutes=3,
            )
            self.assertEqual(renewed["revision"], 1)
            self.assertEqual(renewed["prior_lease_id"], initial["lease_id"])
            self.assertEqual(renewed["lease_token"], initial["lease_token"])
            self.assertNotEqual(renewed["lease_id"], initial["lease_id"])
            current_time[0] = started + timedelta(minutes=2, seconds=30)
            with self.assertRaisesRegex(controller.AutopilotError, "is active"):
                observer.acquire_global_validation_lease(
                    "CONSULT-210",
                    "worker:observer",
                )
            with self.assertRaisesRegex(controller.AutopilotError, "renewal identity"):
                holder.renew_global_validation_lease(
                    "ACCEPT-240",
                    "worker:long-run",
                    lease_id=str(initial["lease_id"]),
                    lease_token=str(initial["lease_token"]),
                )
            current_time[0] = started + timedelta(minutes=5)
            replacement = observer.acquire_global_validation_lease(
                "CONSULT-210",
                "worker:observer",
            )
            expired_archive = observer.validation_lease_archive_dir / (
                str(renewed["lease_id"]).replace(":", "-") + ".expired.json"
            )
            self.assertEqual(controller.read_json(expired_archive), renewed)
            observer.release_global_validation_lease(
                "CONSULT-210",
                "worker:observer",
                lease_id=str(replacement["lease_id"]),
            )

    def test_validation_mutex_assert_and_renew_fail_on_exact_target_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_autopilot_fixture(
                Path(__file__).resolve().parents[1],
                root / ".autopilot",
            )
            control = controller.read_json(root / ".autopilot" / "control-plane.json")
            control["verify_git_objects"] = False
            controller.atomic_write_json(root / ".autopilot" / "control-plane.json", control)
            plane = controller.ControlPlane(
                root,
                validation_mutex_root=root / ".autopilot" / "state" / "validation-mutex",
            )
            original_target = "a" * 40
            plane.current_target_sha = lambda: original_target  # type: ignore[method-assign]
            lease = plane.acquire_global_validation_lease("ACCEPT-240", "worker:target")
            active_before = plane.validation_lease_path.read_bytes()
            plane.current_target_sha = lambda: "b" * 40  # type: ignore[method-assign]
            with self.assertRaisesRegex(controller.AutopilotError, "target moved"):
                plane.assert_global_validation_lease(
                    "ACCEPT-240",
                    "worker:target",
                    lease_id=str(lease["lease_id"]),
                    lease_token=str(lease["lease_token"]),
                )
            with self.assertRaisesRegex(controller.AutopilotError, "target moved"):
                plane.renew_global_validation_lease(
                    "ACCEPT-240",
                    "worker:target",
                    lease_id=str(lease["lease_id"]),
                    lease_token=str(lease["lease_token"]),
                )
            self.assertEqual(plane.validation_lease_path.read_bytes(), active_before)
            plane.current_target_sha = lambda: original_target  # type: ignore[method-assign]
            plane.release_global_validation_lease(
                "ACCEPT-240",
                "worker:target",
                lease_id=str(lease["lease_id"]),
                lease_token=str(lease["lease_token"]),
            )

    def test_validation_mutex_duration_has_deterministic_upper_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_autopilot_fixture(
                Path(__file__).resolve().parents[1],
                root / ".autopilot",
            )
            control = controller.read_json(root / ".autopilot" / "control-plane.json")
            control["verify_git_objects"] = False
            controller.atomic_write_json(root / ".autopilot" / "control-plane.json", control)
            plane = controller.ControlPlane(
                root,
                validation_mutex_root=root / ".autopilot" / "state" / "validation-mutex",
            )
            excessive = controller.MAX_VALIDATION_LEASE_MINUTES + 1
            with self.assertRaisesRegex(controller.AutopilotError, "between 1 and"):
                plane.acquire_global_validation_lease(
                    "ACCEPT-240",
                    "worker:duration",
                    lease_minutes=excessive,
                )
            lease = plane.acquire_global_validation_lease(
                "ACCEPT-240",
                "worker:duration",
                lease_minutes=controller.MAX_VALIDATION_LEASE_MINUTES,
            )
            active_before = plane.validation_lease_path.read_bytes()
            with self.assertRaisesRegex(controller.AutopilotError, "inputs are malformed"):
                plane.renew_global_validation_lease(
                    "ACCEPT-240",
                    "worker:duration",
                    lease_id=str(lease["lease_id"]),
                    lease_token=str(lease["lease_token"]),
                    lease_minutes=excessive,
                )
            self.assertEqual(plane.validation_lease_path.read_bytes(), active_before)
            renewed = plane.renew_global_validation_lease(
                "ACCEPT-240",
                "worker:duration",
                lease_id=str(lease["lease_id"]),
                lease_token=str(lease["lease_token"]),
                lease_minutes=controller.MAX_VALIDATION_LEASE_MINUTES,
            )
            self.assertEqual(
                controller.parse_time(renewed["expires_at"])
                - controller.parse_time(renewed["heartbeat_at"]),
                timedelta(minutes=controller.MAX_VALIDATION_LEASE_MINUTES),
            )
            plane.release_global_validation_lease(
                "ACCEPT-240",
                "worker:duration",
                lease_id=str(renewed["lease_id"]),
                lease_token=str(renewed["lease_token"]),
            )

    def test_validation_mutex_cli_acquire_renew_release_across_fresh_processes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _seed, first, _second = self._real_linked_validation_worktrees(Path(directory))
            acquired_process = self._autopilot(
                first,
                "validation-lease-acquire",
                "ACCEPT-240",
                "--owner",
                "worker:cli",
                "--lease-minutes",
                "5",
            )
            self.assertEqual(acquired_process.returncode, 0, acquired_process.stderr)
            acquired = json.loads(acquired_process.stdout)
            renewed_process = self._autopilot(
                first,
                "validation-lease-renew",
                "ACCEPT-240",
                "--owner",
                "worker:cli",
                "--lease-id",
                str(acquired["lease_id"]),
                "--lease-token",
                str(acquired["lease_token"]),
                "--lease-minutes",
                "5",
            )
            self.assertEqual(renewed_process.returncode, 0, renewed_process.stderr)
            renewed = json.loads(renewed_process.stdout)
            self.assertEqual(renewed["revision"], 1)
            self.assertNotEqual(renewed["lease_id"], acquired["lease_id"])
            unauthorized_release = self._autopilot(
                first,
                "validation-lease-release",
                "ACCEPT-240",
                "--owner",
                "worker:cli",
                "--lease-id",
                str(renewed["lease_id"]),
            )
            self.assertNotEqual(unauthorized_release.returncode, 0)
            self.assertIn("--lease-token", unauthorized_release.stderr)
            self.assertTrue(controller.ControlPlane(first).validation_lease_path.exists())
            released_process = self._autopilot(
                first,
                "validation-lease-release",
                "ACCEPT-240",
                "--owner",
                "worker:cli",
                "--lease-id",
                str(renewed["lease_id"]),
                "--lease-token",
                str(renewed["lease_token"]),
            )
            self.assertEqual(released_process.returncode, 0, released_process.stderr)
            plane = controller.ControlPlane(first)
            self.assertFalse(plane.validation_lease_path.exists())
            released_archive = plane.validation_lease_archive_dir / (
                str(renewed["lease_id"]).replace(":", "-") + ".released.json"
            )
            self.assertEqual(controller.read_json(released_archive), renewed)

    def test_validation_mutex_recovers_expired_crash_stranded_cas_guard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _seed, first, second = self._real_linked_validation_worktrees(Path(directory))
            started = datetime(2030, 1, 1, tzinfo=UTC)
            holder = controller.ControlPlane(first, clock=lambda: started)
            lease = holder.acquire_global_validation_lease(
                "ACCEPT-240",
                "worker:cas-crash",
                lease_minutes=1,
            )
            scope, _mutex_dir = holder._validation_mutex_scope()
            current, encoded = holder._read_validation_lease(
                holder.validation_lease_path,
                scope,
            )
            transaction = holder._claim_validation_lease_cas(
                holder.validation_lease_path,
                current,
                encoded,
            )
            self.assertTrue(transaction.exists())
            restarted = controller.ControlPlane(
                second,
                clock=lambda: started + timedelta(minutes=2),
            )
            replacement = restarted.acquire_global_validation_lease(
                "CONSULT-210",
                "worker:recovered",
            )
            self.assertFalse(transaction.exists())
            archive = restarted.validation_lease_archive_dir / (
                str(lease["lease_id"]).replace(":", "-") + ".expired.json"
            )
            self.assertEqual(controller.read_json(archive), lease)
            restarted.release_global_validation_lease(
                "CONSULT-210",
                "worker:recovered",
                lease_id=str(replacement["lease_id"]),
            )

    def test_validation_mutex_rejects_git_identity_injection_and_fixture_in_git(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            seed, first, _second = self._real_linked_validation_worktrees(Path(directory))
            canonical = "https://github.com/kb4beast/hive-mind-os.git"
            for injected in (
                " " + canonical,
                canonical + "\nhttps://github.com/foreign/repo.git",
                "-c core.hooksPath=attacker",
            ):
                with self.subTest(injected=injected):
                    self._git(seed, "config", "--replace-all", "remote.origin.url", injected)
                    with self.assertRaises(controller.AutopilotError):
                        controller.ControlPlane(first).acquire_global_validation_lease(
                            "ACCEPT-240",
                            "worker:injection",
                        )
            self._git(seed, "config", "--replace-all", "remote.origin.url", canonical)
            with self.assertRaisesRegex(controller.ConfigurationError, "validation_mutex_root"):
                controller.ControlPlane(
                    first,
                    validation_mutex_root=Path(directory) / "injected-mutex",
                ).acquire_global_validation_lease("ACCEPT-240", "worker:fixture-injection")

    def test_validation_mutex_rejects_noncanonical_inputs_and_partial_artifacts(self) -> None:
        class TextSubclass(str):
            pass

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_autopilot_fixture(
                Path(__file__).resolve().parents[1],
                root / ".autopilot",
            )
            control = controller.read_json(root / ".autopilot" / "control-plane.json")
            control["verify_git_objects"] = False
            controller.atomic_write_json(root / ".autopilot" / "control-plane.json", control)
            mutex_root = root / ".autopilot" / "state" / "validation-mutex"
            plane = controller.ControlPlane(root, validation_mutex_root=mutex_root)
            invalid_calls = (
                (TextSubclass("ACCEPT-240"), "worker:strict", 1),
                ("ACCEPT-240", TextSubclass("worker:strict"), 1),
                ("ACCEPT-240", " worker:strict", 1),
                ("ACCEPT-240", "worker:strict\n", 1),
                ("ACCEPT-240", "worker:strict", True),
            )
            for node_id, owner, minutes in invalid_calls:
                with self.subTest(node_id=node_id, owner=owner, minutes=minutes):
                    with self.assertRaises(controller.AutopilotError):
                        plane.acquire_global_validation_lease(
                            node_id,
                            owner,
                            lease_minutes=minutes,
                        )
            lease = plane.acquire_global_validation_lease("ACCEPT-240", "worker:strict")
            with self.assertRaises(controller.AutopilotError):
                plane.release_global_validation_lease(
                    "ACCEPT-240",
                    "worker:strict",
                    lease_id=TextSubclass(str(lease["lease_id"])),
                )
            with self.assertRaises(controller.AutopilotError):
                plane.renew_global_validation_lease(
                    "ACCEPT-240",
                    "worker:strict",
                    lease_id=str(lease["lease_id"]),
                    lease_token=TextSubclass(str(lease["lease_token"])),
                )
            plane.release_global_validation_lease(
                "ACCEPT-240",
                "worker:strict",
                lease_id=str(lease["lease_id"]),
            )
            mutex_root.mkdir(parents=True, exist_ok=True)
            plane.validation_lease_path.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(controller.AutopilotError, "malformed"):
                plane.acquire_global_validation_lease("ACCEPT-240", "worker:partial")
            self.assertEqual(plane.validation_lease_path.read_text(encoding="utf-8"), "{")

    def test_validation_mutex_archive_collision_never_clobbers_or_releases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_autopilot_fixture(
                Path(__file__).resolve().parents[1],
                root / ".autopilot",
            )
            control = controller.read_json(root / ".autopilot" / "control-plane.json")
            control["verify_git_objects"] = False
            controller.atomic_write_json(root / ".autopilot" / "control-plane.json", control)
            plane = controller.ControlPlane(
                root,
                validation_mutex_root=root / ".autopilot" / "state" / "validation-mutex",
            )
            lease = plane.acquire_global_validation_lease("ACCEPT-240", "worker:archive")
            archive = plane.validation_lease_archive_dir / (
                str(lease["lease_id"]).replace(":", "-") + ".released.json"
            )
            archive.parent.mkdir()
            archive.write_text("immutable collision\n", encoding="utf-8")
            active_before = plane.validation_lease_path.read_bytes()
            with self.assertRaisesRegex(controller.AutopilotError, "archive collision"):
                plane.release_global_validation_lease(
                    "ACCEPT-240",
                    "worker:archive",
                    lease_id=str(lease["lease_id"]),
                )
            self.assertEqual(archive.read_text(encoding="utf-8"), "immutable collision\n")
            self.assertEqual(plane.validation_lease_path.read_bytes(), active_before)

    def test_validation_mutex_rejects_symlinked_namespace_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_autopilot_fixture(
                Path(__file__).resolve().parents[1],
                root / ".autopilot",
            )
            control = controller.read_json(root / ".autopilot" / "control-plane.json")
            control["verify_git_objects"] = False
            controller.atomic_write_json(root / ".autopilot" / "control-plane.json", control)
            actual = root / "actual-mutex"
            actual.mkdir()
            mutex_root = root / ".autopilot" / "state" / "validation-mutex"
            mutex_root.parent.mkdir(parents=True, exist_ok=True)
            try:
                mutex_root.symlink_to(actual, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"directory symlinks unavailable: {error}")
            plane = controller.ControlPlane(root, validation_mutex_root=mutex_root)
            with self.assertRaisesRegex(controller.AutopilotError, "indirect or invalid"):
                plane.acquire_global_validation_lease("ACCEPT-240", "worker:symlink")
