from __future__ import annotations

import base64
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

from fixture_support import copy_autopilot_fixture, ready_runtime

BIN = Path(__file__).resolve().parents[1] / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))
MODULE_PATH = BIN / "controller.py"
SPEC = importlib.util.spec_from_file_location("runtime_state_controller", MODULE_PATH)
assert SPEC and SPEC.loader
controller = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = controller
SPEC.loader.exec_module(controller)


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2030, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, minutes: int) -> None:
        self.value += timedelta(minutes=minutes)


def run_git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def install_fixture(root: Path, *, repository: str | None = None) -> None:
    source = Path(__file__).resolve().parents[1]
    copy_autopilot_fixture(source, root / ".autopilot")
    control_path = root / ".autopilot" / "control-plane.json"
    control = json.loads(control_path.read_text(encoding="utf-8"))
    control["verify_git_objects"] = False
    if repository is not None:
        control["target"]["repository"] = repository
    controller.atomic_write_json(control_path, control)


def receipt(plane: object, node_id: str) -> dict[str, object]:
    node = plane.node(node_id)
    scope = str(node["write_scope"][0])
    changed = scope.removesuffix("/**").replace("*", "artifact")
    if scope.endswith("/**"):
        changed += "/artifact.txt"
    return {
        "schema_version": 1,
        "plan_fingerprint": plane.expected_plan_fingerprint,
        "node_id": node_id,
        "contract_version": 1,
        "base_commit": "7" * 40,
        "final_commit": "8" * 40,
        "base_tree": "9" * 40,
        "final_tree": "a" * 40,
        "branch": node["branch"],
        "pr": 123,
        "changed_paths": [changed],
        "tests": [
            {
                "name": name,
                "status": "passed",
                "command": ["python", "-m", "unittest"],
            }
            for name in node["required_tests"]
        ],
        "evidence_refs": ["evidence:runtime-state-test"],
        "model_runtime": {"provider": "fixture", "model": "fixture"},
        "role_identities": [
            {
                "role": role,
                "identity": f"role:{role}",
                "identity_kind": "model_role",
            }
            for role in node["roles"]
        ],
        "authority": {
            "node_id": node_id,
            "autonomy_level": "A3",
            "grants": ["repository"],
        },
        "consultations": [],
        "acceptance_decision": "ADOPT",
        "timestamp": "2030-01-01T00:00:00Z",
        "rollback_ref": "revert:fixture",
    }


class LinkedWorktreeRuntimeStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.primary = base / "primary"
        self.secondary = base / "secondary"
        self.primary.mkdir()
        install_fixture(self.primary)
        run_git(self.primary, "init", "--initial-branch=main")
        run_git(self.primary, "config", "user.name", "Runtime Fixture")
        run_git(self.primary, "config", "user.email", "runtime@hive-mind.invalid")
        run_git(self.primary, "add", "-A")
        run_git(self.primary, "commit", "-m", "runtime fixture")
        run_git(
            self.primary,
            "worktree",
            "add",
            "--detach",
            str(self.secondary),
            "HEAD",
        )
        self.clock = Clock()
        self.first = controller.ControlPlane(self.primary, clock=self.clock)
        self.second = controller.ControlPlane(self.secondary, clock=self.clock)

    def write_legacy_claim(
        self,
        *,
        node_id: str = "RECON-010",
        expires_at: object = "2020-01-01T00:00:00Z",
        raw: bytes | None = None,
    ) -> tuple[Path, bytes]:
        path = self.secondary / ".autopilot" / "state" / "claims" / f"{node_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = raw or (
            json.dumps(
                {
                    "schema_version": 1,
                    "node_id": node_id,
                    "owner": "legacy:worker",
                    "status": "CLAIMED",
                    "claimed_at": "2019-12-31T23:00:00Z",
                    "heartbeat_at": "2019-12-31T23:00:00Z",
                    "expires_at": expires_at,
                    "plan_fingerprint": self.second.expected_plan_fingerprint,
                    "remote": "origin",
                    "remote_claim_commit": "2" * 40,
                    "target_sha": "1" * 40,
                    "branch": self.second.node(node_id)["branch"],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        path.write_bytes(payload)
        return path, payload

    def write_legacy_lease(
        self,
        *,
        expires_at: object = "2020-01-01T00:00:00Z",
    ) -> tuple[Path, bytes]:
        path = self.secondary / ".autopilot" / "state" / "global-validation-lease.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = (
            json.dumps(
                {
                    "schema_version": 1,
                    "node_id": "RECON-010",
                    "owner": "legacy:validator",
                    "target_sha": "1" * 40,
                    "acquired_at": "2019-12-31T23:00:00Z",
                    "expires_at": expires_at,
                    "status": "ACTIVE",
                    "lease_id": "sha256:" + "6" * 64,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        path.write_bytes(payload)
        return path, payload

    def write_legacy_task_binding(self) -> tuple[Path, bytes, str]:
        path = self.secondary / ".autopilot" / "state" / "task-bindings.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        instruction_id = controller.digest_json(
            {
                "kind": "legacy-worktree-launch-v1",
                "worktree": str(self.secondary),
            }
        )
        material = {
            "attempt": 1,
            "host": "codex",
            "kind": "hive-mind-task-binding-event-v1",
            "launch_instruction_id": instruction_id,
            "previous_event_id": None,
            "recorded_at": "2029-12-31T23:59:00Z",
            "retry_of": None,
            "schema_version": 1,
            "state": "PREPARED",
        }
        event = {
            **material,
            "event_id": controller.digest_json(material),
        }
        payload = (
            json.dumps(
                event,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        path.write_bytes(payload)
        return path, payload, instruction_id

    def tearDown(self) -> None:
        if self.primary.exists() and self.secondary.exists():
            subprocess.run(
                (
                    "git",
                    "-C",
                    str(self.primary),
                    "worktree",
                    "remove",
                    "--force",
                    str(self.secondary),
                ),
                check=False,
                capture_output=True,
            )
        self.temporary.cleanup()

    def test_linked_worktrees_resolve_one_primary_authority(self) -> None:
        expected = (self.primary / ".autopilot" / "state").resolve()
        self.assertEqual(self.first.coordination_dir, expected)
        self.assertEqual(self.second.coordination_dir, expected)

    def test_linked_worktree_completion_is_one_shared_terminal_authority(self) -> None:
        ready_runtime(controller, self.primary)
        self.assertEqual(self.first.state_dir, self.second.state_dir)
        self.assertEqual(self.first.state_dir, self.first.execution_dir)
        controller.atomic_write_json(
            self.first.receipt_path("BOOT-000"),
            receipt(self.first, "BOOT-000"),
        )
        claim = self.first.claim_internal("RECON-010", "worker:shared")
        claim_id = str(claim["claim_id"])
        completed_path = self.second.complete_internal(
            "RECON-010",
            "worker:shared",
            receipt(self.second, "RECON-010"),
            claim_id=claim_id,
        )
        self.assertEqual(completed_path, self.first.receipt_path("RECON-010"))
        self.assertTrue(self.first.completed("RECON-010"))
        self.assertTrue(self.second.completed("RECON-010"))
        self.assertFalse(self.first.claim_path("RECON-010").exists())
        events = self.first._receipt_terminal_events()
        terminal = next(
            event for event in events if event["node_id"] == "RECON-010"
        )
        self.assertEqual(terminal["claim_id"], claim_id)
        self.assertEqual(
            terminal["receipt_digest"],
            controller.digest_json(self.first.stored_receipt("RECON-010")),
        )
        self.assertNotIn("RECON-010", self.second.ready_nodes())

    def test_validation_lease_uses_exact_generation_fence(self) -> None:
        ready_runtime(controller, self.primary)
        first = self.first.acquire_global_validation_lease_internal(
            "RECON-010", "worker:first", lease_minutes=1
        )
        with self.assertRaises(controller.AutopilotError):
            self.second.acquire_global_validation_lease_internal(
                "BASE-020", "worker:second", lease_minutes=1
            )
        with self.assertRaisesRegex(controller.AutopilotError, "fence"):
            self.second.release_global_validation_lease_internal(
                "RECON-010",
                "worker:first",
                lease_id="sha256:" + "0" * 64,
            )
        self.second.release_global_validation_lease_internal(
            "RECON-010",
            "worker:first",
            lease_id=str(first["lease_id"]),
        )

        second = self.second.acquire_global_validation_lease_internal(
            "RECON-010", "worker:first", lease_minutes=1
        )
        self.assertNotEqual(first["lease_id"], second["lease_id"])
        self.clock.advance(2)
        with self.assertRaisesRegex(controller.AutopilotError, "fence"):
            self.first.break_expired_validation_lease(
                actor="test:reaper",
                lease_id=str(first["lease_id"]),
            )
        broken = self.first.break_expired_validation_lease(
            actor="test:reaper",
            lease_id=str(second["lease_id"]),
        )
        self.assertEqual(broken["lease_id"], second["lease_id"])

    def test_old_claim_generation_cannot_mutate_replacement(self) -> None:
        ready_runtime(controller, self.primary)
        controller.atomic_write_json(
            self.first.receipt_path("BOOT-000"),
            receipt(self.first, "BOOT-000"),
        )
        first = self.first.claim_internal("RECON-010", "worker:reused")
        first_id = str(first["claim_id"])
        self.first.release_internal(
            "RECON-010",
            "worker:reused",
            claim_id=first_id,
            reason="first generation ended",
        )
        replacement = self.first.claim_internal("RECON-010", "worker:reused")
        replacement_id = str(replacement["claim_id"])
        self.assertNotEqual(first_id, replacement_id)

        stale_calls = (
            lambda: self.second.heartbeat_internal(
                "RECON-010", "worker:reused", claim_id=first_id
            ),
            lambda: self.second.release_internal(
                "RECON-010",
                "worker:reused",
                claim_id=first_id,
                reason="stale release",
            ),
            lambda: self.second.fail_internal(
                "RECON-010",
                "worker:reused",
                claim_id=first_id,
                error="stale failure",
            ),
            lambda: self.second.complete_internal(
                "RECON-010",
                "worker:reused",
                receipt(self.second, "RECON-010"),
                claim_id=first_id,
            ),
        )
        for call in stale_calls:
            with self.subTest(call=call):
                with self.assertRaisesRegex(controller.ClaimError, "fence"):
                    call()

        live = self.second.heartbeat_internal(
            "RECON-010",
            "worker:reused",
            claim_id=replacement_id,
        )
        self.assertEqual(live["claim_id"], replacement_id)

    def test_concurrent_linked_worktree_claim_admission_has_one_winner(self) -> None:
        ready_runtime(controller, self.primary)
        for plane in (self.first, self.second):
            controller.atomic_write_json(
                plane.receipt_path("BOOT-000"),
                receipt(plane, "BOOT-000"),
            )
        barrier = threading.Barrier(2)
        successes: list[dict[str, object]] = []
        failures: list[Exception] = []

        def attempt(plane: object, owner: str) -> None:
            barrier.wait()
            try:
                successes.append(dict(plane.claim_internal("RECON-010", owner)))
            except Exception as error:  # the losing admission is expected evidence
                failures.append(error)

        workers = (
            threading.Thread(target=attempt, args=(self.first, "worker:first")),
            threading.Thread(target=attempt, args=(self.second, "worker:second")),
        )
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=15)
            self.assertFalse(worker.is_alive(), "claim admission deadlocked")

        self.assertEqual(len(successes), 1, (successes, failures))
        self.assertEqual(len(failures), 1, (successes, failures))
        self.assertIsInstance(failures[0], controller.ClaimError)
        claim_files = list(self.first.claims_dir.glob("*.json"))
        self.assertEqual(len(claim_files), 1)
        retained = json.loads(claim_files[0].read_text(encoding="utf-8"))
        self.assertEqual(retained["claim_id"], successes[0]["claim_id"])

    def test_noncanonical_linked_authority_fails_closed(self) -> None:
        legacy = self.secondary / ".autopilot" / "state" / "task-bindings.jsonl"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text('{"state":"BOUND"}\n', encoding="utf-8")
        with self.assertRaisesRegex(
            controller.ConfigurationError,
            "explicit reconciliation",
        ):
            with self.first.runtime_lock("claim-authority.lock"):
                self.fail("noncanonical authority was silently ignored")

    def test_bootstrap_migrates_exact_expired_legacy_bytes_before_identity(self) -> None:
        claim_path, claim_bytes = self.write_legacy_claim()
        lease_path, lease_bytes = self.write_legacy_lease()
        migration = controller.bootstrap_runtime_authority_migration(
            self.primary,
            self.first.coordination_dir,
            actor="test:migrator",
        )
        # Complete staged publication separately: bootstrap must first preserve
        # and retire the exact split-authority bytes before repository identity
        # and READY become observable.
        ready_runtime(controller, self.primary)
        self.assertEqual(migration["status"], "COMPLETE")
        self.assertEqual(len(migration["sources"]), 2)
        self.assertFalse(claim_path.exists())
        self.assertFalse(lease_path.exists())
        expected = {
            str(claim_path): claim_bytes,
            str(lease_path): lease_bytes,
        }
        for source in migration["sources"]:
            original = expected[source["source_path"]]
            self.assertEqual(
                base64.b64decode(source["source_bytes_base64"]),
                original,
            )
            self.assertEqual(Path(source["archive_path"]).read_bytes(), original)
            self.assertEqual(Path(source["retired_path"]).read_bytes(), original)
            self.assertEqual(source["rollback"]["to"], source["source_path"])
        self.assertTrue(
            (self.first.coordination_dir / "runtime-identity.json").is_file()
        )

    def test_bootstrap_prepared_manifest_resumes_after_archive_crash(self) -> None:
        claim_path, claim_bytes = self.write_legacy_claim()
        original_retire = controller._retire_migration_source
        with mock.patch.object(
            controller,
            "_retire_migration_source",
            side_effect=RuntimeError("synthetic crash after archive"),
        ):
            with self.assertRaisesRegex(RuntimeError, "synthetic crash"):
                controller.bootstrap_runtime_authority_migration(
                    self.primary,
                    self.first.coordination_dir,
                    actor="test:migrator",
                    clock=self.clock,
                )
        manifest_path = (
            self.first.coordination_dir / controller.RUNTIME_BOOTSTRAP_MANIFEST
        )
        prepared = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(prepared["status"], "PREPARED")
        self.assertTrue(claim_path.is_file())
        self.assertEqual(
            Path(prepared["sources"][0]["archive_path"]).read_bytes(),
            claim_bytes,
        )
        with mock.patch.object(
            controller,
            "_retire_migration_source",
            wraps=original_retire,
        ):
            completed = controller.bootstrap_runtime_authority_migration(
                self.primary,
                self.first.coordination_dir,
                actor="test:migrator",
                clock=self.clock,
            )
        self.assertEqual(completed["status"], "COMPLETE")
        self.assertFalse(claim_path.exists())
        again = controller.bootstrap_runtime_authority_migration(
            self.primary,
            self.first.coordination_dir,
            actor="test:migrator",
            clock=self.clock,
        )
        self.assertEqual(again, completed)

    def test_bootstrap_preserves_duplicate_expired_same_node_sources(self) -> None:
        first_path, first_bytes = self.write_legacy_claim()
        third = self.primary.parent / "third"
        run_git(
            self.primary,
            "worktree",
            "add",
            "--detach",
            str(third),
            "HEAD",
        )
        second_path = third / ".autopilot" / "state" / "claims" / "RECON-010.json"
        second_path.parent.mkdir(parents=True, exist_ok=True)
        second_value = json.loads(first_bytes.decode("utf-8"))
        second_value["owner"] = "legacy:other-worker"
        second_bytes = (
            json.dumps(second_value, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        second_path.write_bytes(second_bytes)
        try:
            completed = controller.bootstrap_runtime_authority_migration(
                self.primary,
                self.first.coordination_dir,
                actor="test:migrator",
                clock=self.clock,
            )
            self.assertEqual(completed["status"], "COMPLETE")
            self.assertEqual(len(completed["sources"]), 2)
            self.assertEqual(
                {source["source_path"] for source in completed["sources"]},
                {str(first_path), str(second_path)},
            )
            for source in completed["sources"]:
                self.assertTrue(Path(source["archive_path"]).is_file())
                self.assertTrue(Path(source["retired_path"]).is_file())
        finally:
            subprocess.run(
                (
                    "git",
                    "-C",
                    str(self.primary),
                    "worktree",
                    "remove",
                    "--force",
                    str(third),
                ),
                check=False,
                capture_output=True,
            )

    def test_bootstrap_rejects_live_malformed_ambiguous_and_secondary_authority(self) -> None:
        cases = (
            (
                "live",
                lambda: self.write_legacy_claim(
                    expires_at="2031-01-01T00:00:00Z"
                )[0],
                "still live",
            ),
            (
                "malformed-json",
                lambda: self.write_legacy_claim(raw=b"{not-json\n")[0],
                "malformed",
            ),
            (
                "malformed-expiry",
                lambda: self.write_legacy_claim(expires_at="not-a-time")[0],
                "expiry is malformed",
            ),
        )
        # Each rejected attempt leaves no manifest, so its exact source can be
        # removed before exercising the next independent refusal.
        for label, install, message in cases:
            with self.subTest(label=label):
                source = install()
                with self.assertRaisesRegex(controller.ConfigurationError, message):
                    controller.bootstrap_runtime_authority_migration(
                        self.primary,
                        self.first.coordination_dir,
                        actor="test:migrator",
                        clock=self.clock,
                    )
                self.assertTrue(source.exists())
                self.assertFalse(
                    (
                        self.first.coordination_dir
                        / controller.RUNTIME_BOOTSTRAP_MANIFEST
                    ).exists()
                )
                source.unlink()

        ambiguous = (
            json.dumps(
                {
                    "node_id": "BASE-020",
                    "owner": "legacy:worker",
                    "status": "CLAIMED",
                    "expires_at": "2020-01-01T00:00:00Z",
                }
            )
            + "\n"
        ).encode("utf-8")
        source, _raw = self.write_legacy_claim(raw=ambiguous)
        with self.assertRaisesRegex(
            controller.ConfigurationError,
            "unexpected schema",
        ):
            controller.bootstrap_runtime_authority_migration(
                self.primary,
                self.first.coordination_dir,
                actor="test:migrator",
                clock=self.clock,
            )
        source.unlink()

        ledger = self.secondary / ".autopilot" / "state" / "task-bindings.jsonl"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text('{"state":"BOUND"}\n', encoding="utf-8")
        with self.assertRaisesRegex(
            controller.ConfigurationError,
            "semantic reconciliation",
        ):
            controller.bootstrap_runtime_authority_migration(
                self.primary,
                self.first.coordination_dir,
                actor="test:migrator",
                clock=self.clock,
            )

    def test_semantic_reconciliation_fences_task_and_quarantines_attended_authority(self) -> None:
        task_path, task_bytes, instruction_id = self.write_legacy_task_binding()
        attended_path = (
            self.secondary
            / ".autopilot"
            / "state"
            / "host"
            / "attended-threads.json"
        )
        attended = {
            "schema_version": 1,
            "threads": [
                {
                    "task_id": "attended-legacy",
                    "state": "BOUND",
                }
            ],
        }
        controller.atomic_write_json(attended_path, attended)
        attended_bytes = attended_path.read_bytes()
        host_runtime = self.primary.parent / "host-runtime"
        host_base = self.primary.parent / "host-account-authority"

        with mock.patch.object(
            controller, "_host_runtime_base_dir", return_value=host_base
        ):
            controller.initialize_host_runtime(host_runtime)
            with controller.runtime_file_lock(
                host_runtime / "locks" / "host-authority.lock",
                timeout_seconds=120.0,
            ):
                with controller.runtime_file_lock(
                    self.first.coordination_dir
                    / controller.RUNTIME_BOOTSTRAP_LOCK,
                    timeout_seconds=120.0,
                ):
                    completed = (
                        controller.reconcile_legacy_worktree_execution_authority(
                            self.primary,
                            self.first.coordination_dir,
                            host_runtime_dir=host_runtime,
                            actor="test:semantic-court",
                            clock=self.clock,
                        )
                    )
                    replayed = (
                        controller.reconcile_legacy_worktree_execution_authority(
                            self.primary,
                            self.first.coordination_dir,
                            host_runtime_dir=host_runtime,
                            actor="test:semantic-court",
                            clock=self.clock,
                        )
                    )
                    bootstrap = controller.bootstrap_runtime_authority_migration(
                        self.primary,
                        self.first.coordination_dir,
                        actor="test:semantic-court",
                        clock=self.clock,
                    )

        self.assertEqual(completed, replayed)
        self.assertEqual(completed["status"], "COMPLETE")
        self.assertEqual(bootstrap["status"], "COMPLETE")
        self.assertFalse(task_path.exists())
        self.assertFalse(attended_path.exists())
        entries = {
            entry["relative_path"]: entry for entry in completed["entries"]
        }
        task_entry = entries["task-bindings.jsonl"]
        attended_entry = entries["host/attended-threads.json"]
        self.assertEqual(
            task_entry["classification"], "ADOPT_FENCED", task_entry
        )
        self.assertEqual(attended_entry["classification"], "QUARANTINE")
        self.assertEqual(Path(task_entry["archive_path"]).read_bytes(), task_bytes)
        self.assertEqual(
            Path(attended_entry["archive_path"]).read_bytes(), attended_bytes
        )

        destination = Path(task_entry["destination_path"])
        installed = destination.read_bytes()
        self.assertTrue(installed.startswith(task_bytes))
        from orchestration import _binding_events_unlocked

        events = _binding_events_unlocked(self.primary, destination.parent)
        matching = [
            event
            for event in events
            if event["launch_instruction_id"] == instruction_id
        ]
        self.assertEqual([event["state"] for event in matching], ["PREPARED", "SUPERSEDED"])
        self.assertIn("external cancellation NOT_CLAIMED", matching[-1]["reason"])

        obligations = controller._legacy_authority_quarantine_obligations_unlocked(
            self.first.coordination_dir
        )
        self.assertEqual(len(obligations), 1)
        self.assertEqual(obligations[0]["relative_path"], "host/attended-threads.json")
        self.assertEqual(obligations[0]["external_cancellation"], "NOT_CLAIMED")

    def test_semantic_reconciliation_replays_fence_after_prepared_crash(self) -> None:
        task_path, task_bytes, instruction_id = self.write_legacy_task_binding()
        host_runtime = self.primary.parent / "host-runtime"
        host_base = self.primary.parent / "host-account-authority"
        original_retire = controller._retire_migration_source

        with mock.patch.object(
            controller, "_host_runtime_base_dir", return_value=host_base
        ):
            controller.initialize_host_runtime(host_runtime)
            with controller.runtime_file_lock(
                host_runtime / "locks" / "host-authority.lock",
                timeout_seconds=120.0,
            ):
                with controller.runtime_file_lock(
                    self.first.coordination_dir
                    / controller.RUNTIME_BOOTSTRAP_LOCK,
                    timeout_seconds=120.0,
                ):
                    with mock.patch.object(
                        controller,
                        "_retire_migration_source",
                        side_effect=RuntimeError("synthetic semantic retirement crash"),
                    ):
                        with self.assertRaisesRegex(RuntimeError, "synthetic semantic"):
                            controller.reconcile_legacy_worktree_execution_authority(
                                self.primary,
                                self.first.coordination_dir,
                                host_runtime_dir=host_runtime,
                                actor="test:semantic-restart",
                                clock=self.clock,
                            )
                    prepared = controller.read_json(
                        self.first.coordination_dir
                        / controller.LEGACY_SEMANTIC_RECONCILIATION_MANIFEST
                    )
                    self.assertEqual(prepared["status"], "PREPARED")
                    self.assertTrue(task_path.is_file())
                    task_entry = prepared["entries"][0]
                    destination = Path(task_entry["destination_path"])
                    self.assertTrue(destination.read_bytes().startswith(task_bytes))
                    with mock.patch.object(
                        controller,
                        "_retire_migration_source",
                        wraps=original_retire,
                    ):
                        completed = (
                            controller.reconcile_legacy_worktree_execution_authority(
                                self.primary,
                                self.first.coordination_dir,
                                host_runtime_dir=host_runtime,
                                actor="test:semantic-restart",
                                clock=self.clock,
                            )
                        )

        self.assertEqual(completed["status"], "COMPLETE")
        self.assertFalse(task_path.exists())
        from orchestration import _binding_events_unlocked

        events = _binding_events_unlocked(self.primary, destination.parent)
        matching = [
            event
            for event in events
            if event["launch_instruction_id"] == instruction_id
        ]
        self.assertEqual(
            [event["state"] for event in matching],
            ["PREPARED", "SUPERSEDED"],
        )


class RuntimeIdentityTests(unittest.TestCase):
    def test_nondefault_execution_command_prefix_seals_all_authority_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install_fixture(root)
            ready_runtime(controller, root)
            default = controller.ControlPlane(root)
            identity = controller.execution_namespace_identity(
                default.repository_identity,
                kernel_identity=controller.runtime_kernel_identity(root),
                namespace="application-two",
                target_branch=default.target_branch,
                plan_fingerprint=default.expected_plan_fingerprint,
            )
            with default.arbiter_lock(timeout_seconds=120.0):
                controller.initialize_execution_namespace(
                    default.coordination_dir, identity
                )
            other = controller.ControlPlane(
                root,
                execution_namespace="application-two",
                host_runtime_dir=default.host_runtime_dir,
            )
            prefix = other.autopilot_command_prefix()
            self.assertIn(f'--repo-root "{root.resolve()}"', prefix)
            self.assertIn(
                f'--state-dir "{other.coordination_dir}"', prefix
            )
            self.assertIn(
                f'--host-runtime-dir "{other.host_runtime_dir}"', prefix
            )
            self.assertIn("--execution-namespace application-two", prefix)
            self.assertNotIn("--execution-namespace default", prefix)
            default_before = {
                str(path.relative_to(default.execution_dir)): path.read_bytes()
                for path in default.execution_dir.rglob("*")
                if path.is_file()
            }
            rendered = "\n".join(
                (
                    other.render_worker_prompt(
                        "BOOT-000", host_id="host:authenticated-fixture"
                    ),
                    other.render_worker_prompt(
                        "RECON-010", host_id="host:authenticated-fixture"
                    ),
                )
            )
            self.assertNotIn("{{", rendered)
            self.assertNotIn(
                "python .autopilot/bin/autopilot.py --repo-root .", rendered
            )
            self.assertIn(prefix, rendered)
            self.assertIn("--execution-namespace application-two", rendered)
            self.assertIn(
                "Authenticated host: `host:authenticated-fixture`", rendered
            )
            self.assertNotIn("--execution-namespace default", rendered)
            default_after = {
                str(path.relative_to(default.execution_dir)): path.read_bytes()
                for path in default.execution_dir.rglob("*")
                if path.is_file()
            }
            self.assertEqual(default_after, default_before)

    def test_template_drift_is_rejected_before_execution_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install_fixture(root)
            ready_runtime(controller, root)
            plane = controller.ControlPlane(root)
            before = {
                str(path.relative_to(plane.coordination_dir)): path.read_bytes()
                for path in plane.coordination_dir.rglob("*")
                if path.is_file()
            }
            template = root / ".autopilot" / "templates" / "worker.md"
            template.write_bytes(template.read_bytes() + b"\nmutated kernel template\n")
            with self.assertRaisesRegex(
                controller.ConfigurationError,
                "another target or plan",
            ):
                controller.ControlPlane(root)
            after = {
                str(path.relative_to(plane.coordination_dir)): path.read_bytes()
                for path in plane.coordination_dir.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)

    def test_long_lived_plane_reauthenticates_kernel_before_append(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install_fixture(root)
            ready_runtime(controller, root)
            plane = controller.ControlPlane(root)
            before = {
                str(path.relative_to(plane.coordination_dir)): path.read_bytes()
                for path in plane.coordination_dir.rglob("*")
                if path.is_file()
            }
            learning = root / ".autopilot" / "bin" / "learning.py"
            learning.write_bytes(learning.read_bytes() + b"\n# stale kernel writer\n")
            with self.assertRaisesRegex(
                controller.ConfigurationError,
                "kernel bundle or interpreter policy changed",
            ):
                plane.record_blocker(
                    "BOOT-000",
                    cause="kernel changed after construction",
                    fix="restart under an explicit zero-activity kernel upgrade",
                    retry_when="the execution identity binds the installed kernel",
                )
            after = {
                str(path.relative_to(plane.coordination_dir)): path.read_bytes()
                for path in plane.coordination_dir.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)

    def test_staged_runtime_remains_closed_until_attended_migration_publishes_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install_fixture(root)
            host_runtime = root / "host-runtime"
            host_base_patch = mock.patch.object(
                controller,
                "_host_runtime_base_dir",
                return_value=root / "host-account-authority",
            )
            host_base_patch.start()
            self.addCleanup(host_base_patch.stop)
            controller.initialize_host_runtime(host_runtime)
            plane = controller.ControlPlane(root, host_runtime_dir=host_runtime)
            bootstrap_lock = plane.coordination_dir / controller.RUNTIME_BOOTSTRAP_LOCK
            attended_lock = plane.coordination_dir / "locks" / "attended-host.lock"
            with plane.host_lock(timeout_seconds=120.0):
                with controller.runtime_file_lock(
                    bootstrap_lock, timeout_seconds=120.0
                ):
                    bootstrap = controller.bootstrap_runtime_authority_migration(
                        root,
                        plane.coordination_dir,
                        actor="test:crash-boundary",
                    )
                    controller.stage_repository_runtime_authority(
                        root,
                        plane.coordination_dir,
                        host_runtime_dir=host_runtime,
                    )
                    self.assertTrue(
                        (plane.coordination_dir / "runtime-identity.json").is_file()
                    )
                    self.assertFalse(
                        (plane.coordination_dir / controller.RUNTIME_READY_MANIFEST).exists()
                    )
                    with self.assertRaisesRegex(
                        controller.ConfigurationError,
                        "not ready",
                    ):
                        with plane.runtime_lock("claim-authority.lock"):
                            self.fail("staged authority escaped before attended migration")
                    with self.assertRaisesRegex(
                        controller.ConfigurationError, "not ready"
                    ):
                        with plane.arbiter_lock(timeout_seconds=120.0):
                            self.fail("normal arbiter escaped before READY")
                    with plane.bootstrap_arbiter_lock(
                        bootstrap_migration_id=str(bootstrap["migration_id"]),
                        timeout_seconds=120.0,
                    ):
                        with controller.runtime_file_lock(
                            attended_lock,
                            timeout_seconds=120.0,
                        ):
                            controller.initialize_repository_runtime_authority(
                                root,
                                plane.coordination_dir,
                                attended_migration={"outcome": "ABSENT", "entries": 0},
                            )
            with plane.runtime_lock("claim-authority.lock"):
                pass

    def test_ready_chain_and_nonempty_default_adoption_are_exactly_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install_fixture(root)
            plane = controller.ControlPlane(root)
            bootstrap_lock = plane.coordination_dir / controller.RUNTIME_BOOTSTRAP_LOCK
            attended_lock = plane.coordination_dir / "locks" / "attended-host.lock"
            arbiter_lock = (
                plane.coordination_dir
                / "arbiter"
                / "locks"
                / "arbiter-authority.lock"
            )
            receipt = {
                "schema_version": 1,
                "kind": controller.ATTENDED_MIGRATION_KIND,
                "status": "COMPLETE",
                "entries": 1,
                "migration_id": "sha256:" + "e" * 64,
            }
            with controller.runtime_file_lock(bootstrap_lock, timeout_seconds=120.0):
                controller.bootstrap_runtime_authority_migration(
                    root, plane.coordination_dir, actor="test:idempotent-migration"
                )
                controller.stage_repository_runtime_authority(
                    root, plane.coordination_dir
                )
                first_index_material = {
                    "schema_version": 1,
                    "kind": "fixture-terminal-index-v1",
                    "previous_event_id": None,
                }
                first_index_event = {
                    **first_index_material,
                    "event_id": controller.digest_json(first_index_material),
                }
                controller.append_jsonl(
                    plane.coordination_dir / "receipt-index.jsonl",
                    first_index_event,
                )
                ledger = plane.coordination_dir / "host" / "attended-threads.json"
                controller.atomic_write_json(
                    ledger,
                    {"schema_version": 1, "threads": [{"task_id": "thread:test"}]},
                )
                controller.atomic_write_json(
                    plane.coordination_dir
                    / "migrations"
                    / "attended-host-v1"
                    / "manifest.json",
                    receipt,
                )
                with controller.runtime_file_lock(
                    arbiter_lock, timeout_seconds=120.0
                ):
                    with controller.runtime_file_lock(
                        attended_lock, timeout_seconds=120.0
                    ):
                        first = controller.initialize_repository_runtime_authority(
                            root,
                            plane.coordination_dir,
                            attended_migration=receipt,
                        )
                        second = controller.initialize_repository_runtime_authority(
                            root,
                            plane.coordination_dir,
                            attended_migration=receipt,
                        )
            self.assertEqual(first, second)
            ready_plane = controller.ControlPlane(root)
            second_index_material = {
                "schema_version": 1,
                "kind": "fixture-terminal-index-v1",
                "previous_event_id": first_index_event["event_id"],
            }
            controller.append_jsonl(
                ready_plane.state_dir / "receipt-index.jsonl",
                {
                    **second_index_material,
                    "event_id": controller.digest_json(second_index_material),
                },
            )
            controller.atomic_write_json(
                ready_plane.state_dir / "target.json",
                {
                    "schema_version": 1,
                    "target_sha": ready_plane.baseline_sha,
                    "actor": "test:post-ready",
                    "reason": "prove READY does not freeze mutable authority",
                    "changed_paths": [],
                    "timestamp": "2030-01-01T00:00:00Z",
                    "plan_fingerprint": ready_plane.expected_plan_fingerprint,
                },
            )
            controller.atomic_write_json(
                ready_plane.state_dir / "github-state.json",
                {
                    "target_sha": ready_plane.baseline_sha,
                    "pull_requests": [],
                    "branches": [],
                },
            )
            chain = controller.validate_repository_runtime_ready_chain(
                root, plane.coordination_dir
            )
            self.assertEqual(chain["execution_dir"], str(ready_plane.execution_dir))
            manifest = controller.read_json(
                ready_plane.execution_dir
                / "migrations"
                / "singleton-default-adoption.json"
            )
            index_entry = next(
                entry
                for entry in manifest["entries"]
                if entry["relative_path"] == "receipt-index.jsonl"
            )
            archive = Path(index_entry["archive_path"])
            archived = archive.read_bytes()
            archive.write_bytes(archived + b"tamper")
            with self.assertRaisesRegex(
                controller.ConfigurationError, "archive differs"
            ):
                controller.validate_repository_runtime_ready_chain(
                    root, plane.coordination_dir
                )
            self.assertEqual(chain["attended_host"], receipt)
            adopted = (
                Path(str(chain["execution_dir"]))
                / "host"
                / "attended-threads.json"
            )
            self.assertTrue(adopted.is_file())
            self.assertFalse(ledger.exists())

    def test_target_watermarks_are_keyed_by_mutable_target_ref(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install_fixture(root)
            ready_runtime(controller, root)
            plane = controller.ControlPlane(root)
            first = plane.repository_target_watermark()
            other_branch = "release/independent"
            other_sha = "b" * 40
            other_identity = controller.execution_namespace_identity(
                plane.repository_identity,
                kernel_identity=controller.runtime_kernel_identity(root),
                namespace="independent",
                target_branch=other_branch,
                plan_fingerprint=plane.expected_plan_fingerprint,
            )
            other_execution = str(other_identity["execution_id"])
            transport_material: dict[str, object] = {
                "schema_version": 1,
                "kind": "hive-mind-canonical-remote-transport-v1",
                "repository": plane.repository_identity["repository"],
                "remote_name": "origin",
                "fetch_url": plane.repository_identity["canonical_remote_fetch"],
                "push_url": plane.repository_identity["canonical_remote_push"],
            }
            transport = {
                **transport_material,
                "record_id": controller.digest_json(transport_material),
            }
            controller.atomic_write_json(
                plane.arbiter_dir / "canonical-remote-transport.json", transport
            )
            observation_material: dict[str, object] = {
                "schema_version": 1,
                "kind": controller.INITIAL_REMOTE_TARGET_OBSERVATION_KIND,
                "repository": plane.repository_identity["repository"],
                "repository_transport_digest": plane.repository_identity[
                    "transport_digest"
                ],
                "target_ref": f"refs/heads/{other_branch}",
                "target_sha": other_sha,
                "transport_record_id": transport["record_id"],
                "execution_id": other_execution,
                "execution_namespace": "independent",
                "observed_at": "2030-01-01T00:00:00Z",
            }
            observation = {
                **observation_material,
                "record_id": controller.digest_json(observation_material),
            }
            first_paths = controller._repository_target_watermark_paths(
                plane.coordination_dir,
                repository_identity=plane.repository_identity,
                target_branch=plane.target_branch,
            )
            other_paths = controller._repository_target_watermark_paths(
                plane.coordination_dir,
                repository_identity=plane.repository_identity,
                target_branch=other_branch,
            )
            self.assertNotEqual(first_paths, other_paths)
            with plane.arbiter_lock(timeout_seconds=120.0):
                controller.initialize_execution_namespace(
                    plane.coordination_dir, other_identity
                )
                other = controller._initialize_repository_target_watermark(
                    plane.coordination_dir,
                    repository_identity=plane.repository_identity,
                    target_branch=other_branch,
                    target_sha=other_sha,
                    source_execution_id=other_execution,
                    source_observation=observation,
                    actor="test:second-target",
                    recorded_at="2030-01-01T00:00:00Z",
                )
                next_sha = "c" * 40
                snapshot_material = {
                    "schema_version": 2,
                    "kind": "hive-mind-github-snapshot-observation-v2",
                    "status": "INSTALLING",
                    "execution_namespace": "independent",
                    "execution_id": other_execution,
                    "observation_epoch": 1,
                    "observation_id": controller.digest_json(
                        {"kind": "fixture-other-target-snapshot-v1"}
                    ),
                    "fetch_ref": "refs/heads/hive-mind-evidence/other-target",
                    "branch_fetches": [],
                    "repository": plane.repository_identity["repository"],
                    "target_branch": other_branch,
                    "base_target_sha": other_sha,
                    "target_sha": next_sha,
                    "plan_fingerprint": plane.expected_plan_fingerprint,
                    "snapshot_digest": controller.digest_json(
                        {"kind": "fixture-other-target-candidate-v1"}
                    ),
                    "candidate_artifact": "snapshot-candidates/other.json",
                    "supersedes_observation_id": None,
                    "actor": "test:second-target",
                    "began_at": "2030-01-01T00:00:00Z",
                    "expires_at": "2030-01-01T00:30:00Z",
                    "installed_at": None,
                }
                snapshot_source = {
                    **snapshot_material,
                    "record_id": controller.digest_json(snapshot_material),
                }
                transition = controller._install_target_transition_evidence_unlocked(
                    plane.coordination_dir,
                    repository_identity=plane.repository_identity,
                    target_branch=other_branch,
                    previous=other,
                    target_sha=next_sha,
                    execution_id=other_execution,
                    execution_namespace="independent",
                    plan_fingerprint=plane.expected_plan_fingerprint,
                    source_kind="SNAPSHOT_INSTALL",
                    source_release_id=None,
                    publication_transaction_id=None,
                    source_record=snapshot_source,
                    observed_at="2030-01-01T00:01:00Z",
                )
                advanced = controller._advance_repository_target_watermark_unlocked(
                    plane.coordination_dir,
                    repository_identity=plane.repository_identity,
                    target_branch=other_branch,
                    execution_id=other_execution,
                    expected_generation=1,
                    expected_target_sha=other_sha,
                    target_sha=next_sha,
                    source_kind="SNAPSHOT_INSTALL",
                    source_release_id=None,
                    publication_transaction_id=None,
                    source_observation_id=str(transition["transition_id"]),
                    actor="test:advance-second-target",
                    recorded_at="2030-01-01T00:01:00Z",
                )
            self.assertEqual(other["target_generation"], 1)
            self.assertEqual(advanced["target_generation"], 2)
            self.assertEqual(
                plane.repository_target_watermark()["record_id"], first["record_id"]
            )
            self.assertEqual(
                controller._read_repository_target_watermark_unlocked(
                    plane.coordination_dir,
                    repository_identity=plane.repository_identity,
                    target_branch=other_branch,
                )["record_id"],
                advanced["record_id"],
            )
            observation_path = controller._initial_remote_target_observation_path(
                plane.coordination_dir,
                repository_identity=plane.repository_identity,
                target_branch=other_branch,
                observation_id=str(observation["record_id"]),
            )
            sealed_observation = observation_path.read_bytes()
            observation_path.unlink()
            with self.assertRaises(controller.ConfigurationError):
                controller._read_repository_target_watermark_unlocked(
                    plane.coordination_dir,
                    repository_identity=plane.repository_identity,
                    target_branch=other_branch,
                )
            observation_path.parent.mkdir(parents=True, exist_ok=True)
            observation_path.write_bytes(sealed_observation)
            changed = dict(observation)
            changed["target_sha"] = "d" * 40
            changed_material = dict(changed)
            changed_material.pop("record_id")
            changed["record_id"] = controller.digest_json(changed_material)
            controller.atomic_write_json(observation_path, changed)
            with self.assertRaisesRegex(
                controller.ConfigurationError, "observation"
            ):
                controller._read_repository_target_watermark_unlocked(
                    plane.coordination_dir,
                    repository_identity=plane.repository_identity,
                    target_branch=other_branch,
                )

    def test_snapshot_watermark_retains_and_replays_exact_source_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install_fixture(root)
            ready_runtime(controller, root)
            plane = controller.ControlPlane(root, clock=Clock())
            previous = plane.repository_target_watermark()
            target_sha = "b" * 40
            observation_id = controller.digest_json(
                {
                    "kind": "fixture-snapshot-observation-key-v1",
                    "execution_id": plane.execution_id,
                    "target_sha": target_sha,
                }
            )
            material = {
                "schema_version": 2,
                "kind": "hive-mind-github-snapshot-observation-v2",
                "status": "INSTALLING",
                "execution_namespace": plane.execution_namespace,
                "execution_id": plane.execution_id,
                "observation_epoch": 1,
                "observation_id": observation_id,
                "fetch_ref": "refs/heads/hive-mind-evidence/snapshot-fixture",
                "branch_fetches": [],
                "repository": plane.repository_identity["repository"],
                "target_branch": plane.target_branch,
                "base_target_sha": previous["target_sha"],
                "target_sha": target_sha,
                "plan_fingerprint": plane.expected_plan_fingerprint,
                "snapshot_digest": controller.digest_json(
                    {"kind": "fixture-snapshot-v1", "target_sha": target_sha}
                ),
                "candidate_artifact": "snapshot-candidates/fixture.json",
                "supersedes_observation_id": None,
                "actor": "test:snapshot",
                "began_at": "2030-01-01T00:00:00Z",
                "expires_at": "2030-01-01T00:30:00Z",
                "installed_at": None,
            }
            observation = {
                **material,
                "record_id": controller.digest_json(material),
            }
            with plane.arbiter_lock(timeout_seconds=120.0):
                advanced = plane.advance_repository_target_watermark_from_snapshot(
                    expected_generation=int(previous["target_generation"]),
                    expected_target_sha=str(previous["target_sha"]),
                    target_sha=target_sha,
                    source_observation=observation,
                    actor="test:snapshot",
                )
                replayed = plane.advance_repository_target_watermark_from_snapshot(
                    expected_generation=int(previous["target_generation"]),
                    expected_target_sha=str(previous["target_sha"]),
                    target_sha=target_sha,
                    source_observation=observation,
                    actor="test:snapshot",
                )
            self.assertEqual(advanced, replayed)
            transition_id = str(advanced["source_observation_id"])
            current_path, _history_path = (
                controller._repository_target_watermark_paths(
                    plane.coordination_dir,
                    repository_identity=plane.repository_identity,
                    target_branch=plane.target_branch,
                )
            )
            evidence_path = (
                current_path.parent
                / "transition-evidence"
                / (transition_id.removeprefix("sha256:") + ".json")
            )
            evidence = controller.read_strict_canonical_json(
                evidence_path,
                label="fixture target transition evidence",
            )
            source_path = plane.coordination_dir / str(evidence["source_blob_path"])
            self.assertEqual(
                controller.read_strict_canonical_json(
                    source_path,
                    label="fixture retained snapshot observation",
                ),
                observation,
            )
            source_path.unlink()
            with self.assertRaisesRegex(
                controller.ConfigurationError,
                "missing|source blob",
            ):
                plane.repository_target_watermark()

    def test_publication_watermark_retains_exact_transaction_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install_fixture(root)
            ready_runtime(controller, root)
            plane = controller.ControlPlane(root, clock=Clock())
            previous = plane.repository_target_watermark()
            target_sha = "c" * 40
            release_id = "sha256:" + "1" * 64
            transaction_id = "sha256:" + "2" * 64
            material = {
                "schema_version": 1,
                "kind": "hive-mind-publication-transaction-v1",
                "status": "PUBLISHING",
                "transaction_key": controller.digest_json(
                    {"kind": "fixture-publication-key-v1"}
                ),
                "attempt_epoch": 1,
                "nonce": "3" * 64,
                "transaction_id": transaction_id,
                "execution_namespace": plane.execution_namespace,
                "execution_id": plane.execution_id,
                "release_id": release_id,
                "round_id": controller.digest_json(
                    {"kind": "fixture-round-v1"}
                ),
                "repository": plane.repository_identity["repository"],
                "target_branch": plane.target_branch,
                "expected_target_sha": previous["target_sha"],
                "authority_digest": controller.digest_json(
                    {"kind": "fixture-authority-v1"}
                ),
                "authority_baseline_digest": controller.digest_json(
                    {"kind": "fixture-baseline-authority-v1"}
                ),
                "receipt_heads": [],
                "receipt_heads_digest": controller.digest_json([]),
                "transaction_ref": "refs/heads/hive-mind-evidence/fixture-transaction",
                "coordinator_id": "test:publisher",
                "transaction_lease_nonce": "4" * 64,
                "transaction_lease_id": controller.digest_json(
                    {"kind": "fixture-transaction-lease-v1"}
                ),
                "lease_expires_at": "2030-01-01T00:30:00Z",
                "publishing_lease_nonce": "5" * 64,
                "publishing_lease_id": controller.digest_json(
                    {"kind": "fixture-publishing-lease-v1"}
                ),
                "publishing_lease_expires_at": "2030-01-01T00:10:00Z",
                "pinned_sha": target_sha,
                "validation_evidence": {
                    "evidence_id": controller.digest_json(
                        {"kind": "fixture-validation-v1"}
                    )
                },
                "outcome": None,
                "detail": "fixture publishing authority",
                "actor": "test:publisher",
                "reserved_at": "2030-01-01T00:00:00Z",
                "updated_at": "2030-01-01T00:01:00Z",
                "completed_at": None,
            }
            source = {**material, "record_id": controller.digest_json(material)}
            with plane.arbiter_lock(timeout_seconds=120.0):
                advanced = plane.advance_repository_target_watermark(
                    expected_generation=int(previous["target_generation"]),
                    expected_target_sha=str(previous["target_sha"]),
                    target_sha=target_sha,
                    source_release_id=release_id,
                    publication_transaction_id=transaction_id,
                    source_record=source,
                    actor="test:publisher",
                )
            self.assertEqual(advanced["source_kind"], "PUBLICATION")
            transition_id = str(advanced["source_observation_id"])
            current_path, _history = controller._repository_target_watermark_paths(
                plane.coordination_dir,
                repository_identity=plane.repository_identity,
                target_branch=plane.target_branch,
            )
            evidence = controller.read_strict_canonical_json(
                current_path.parent
                / "transition-evidence"
                / (transition_id.removeprefix("sha256:") + ".json"),
                label="fixture publication transition evidence",
            )
            source_path = plane.coordination_dir / str(evidence["source_blob_path"])
            self.assertEqual(
                controller.read_strict_canonical_json(
                    source_path,
                    label="fixture retained publication source",
                ),
                source,
            )

    def test_superseded_publication_watermark_retains_exact_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install_fixture(root)
            ready_runtime(controller, root)
            plane = controller.ControlPlane(root)
            current = plane.repository_target_watermark()
            release_id = "sha256:" + "1" * 64
            transaction_id = "sha256:" + "2" * 64
            target_sha = "c" * 40
            material: dict[str, object] = {
                "schema_version": 1,
                "kind": (
                    controller.SUPERSEDED_PUBLICATION_TARGET_OBSERVATION_KIND
                ),
                "repository": plane.repository_identity["repository"],
                "repository_transport_digest": plane.repository_identity[
                    "transport_digest"
                ],
                "target_ref": f"refs/heads/{plane.target_branch}",
                "expected_target_sha": current["target_sha"],
                "pinned_sha": "b" * 40,
                "observed_target_sha": target_sha,
                "observation_ref": (
                    "refs/heads/hive-mind-evidence/publication-observations/"
                    f"{plane.execution_id.removeprefix('sha256:')}/"
                    f"{transaction_id.removeprefix('sha256:')}/sealed"
                ),
                "observation_ref_sha": target_sha,
                "transaction_ref": (
                    "refs/heads/hive-mind-evidence/publication-transactions/"
                    "sealed"
                ),
                "observed_transaction_sha": "b" * 40,
                "receipt_heads": [
                    {
                        "node_id": "RECON-010",
                        "branch": "recon-010",
                        "expected_sha": "a" * 40,
                        "observed_sha": "a" * 40,
                    }
                ],
                "execution_namespace": plane.execution_namespace,
                "execution_id": plane.execution_id,
                "release_id": release_id,
                "publication_transaction_id": transaction_id,
                "observed_at": "2030-01-01T00:00:00Z",
            }
            observation = {
                **material,
                "record_id": controller.digest_json(material),
            }
            with plane.arbiter_lock(timeout_seconds=120.0):
                advanced = (
                    plane.advance_repository_target_watermark_from_superseded_publication(
                        expected_generation=int(current["target_generation"]),
                        expected_target_sha=str(current["target_sha"]),
                        target_sha=target_sha,
                        source_release_id=release_id,
                        publication_transaction_id=transaction_id,
                        source_observation=observation,
                        actor="test:superseded",
                    )
                )
            self.assertEqual(advanced["source_kind"], "SUPERSEDED_PUBLICATION")
            self.assertEqual(
                advanced["source_observation_id"], observation["record_id"]
            )
            path = controller._superseded_publication_target_observation_path(
                plane.coordination_dir,
                repository_identity=plane.repository_identity,
                target_branch=plane.target_branch,
                observation_id=str(observation["record_id"]),
            )
            sealed = path.read_bytes()
            path.unlink()
            with self.assertRaisesRegex(controller.ConfigurationError, "observation"):
                plane.repository_target_watermark()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(sealed)
            changed = dict(observation)
            changed["observed_target_sha"] = "d" * 40
            changed_material = dict(changed)
            changed_material.pop("record_id")
            changed["record_id"] = controller.digest_json(changed_material)
            controller.atomic_write_json(path, changed)
            with self.assertRaisesRegex(controller.ConfigurationError, "observation"):
                plane.repository_target_watermark()

    def test_runtime_lock_is_same_thread_reentrant_but_excludes_other_threads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / "locks" / "runtime.lock"
            failures: list[Exception] = []
            with controller.runtime_file_lock(lock):
                with controller.runtime_file_lock(lock, timeout_seconds=0.05):
                    pass

                def contend() -> None:
                    try:
                        with controller.runtime_file_lock(
                            lock,
                            timeout_seconds=0.05,
                        ):
                            self.fail("another thread entered an owned runtime lock")
                    except Exception as error:
                        failures.append(error)

                worker = threading.Thread(target=contend)
                worker.start()
                worker.join(timeout=5)
                self.assertFalse(worker.is_alive(), "runtime lock contender deadlocked")
            self.assertEqual(len(failures), 1)
            self.assertIsInstance(failures[0], controller.ConfigurationError)
            with controller.runtime_file_lock(lock, timeout_seconds=0.05):
                pass

    def test_first_claim_read_waits_for_admission_and_observes_winner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install_fixture(root)
            plane = controller.ControlPlane(root)
            ready_runtime(controller, root)
            controller.atomic_write_json(
                plane.receipt_path("BOOT-000"),
                receipt(plane, "BOOT-000"),
            )
            with plane.runtime_lock("claim-authority.lock"):
                pass
            claim_path = plane.claim_path("RECON-010")
            writer_entered = threading.Event()
            allow_write = threading.Event()
            reader_started = threading.Event()
            reader_finished = threading.Event()
            claimed: list[Mapping[str, object]] = []
            observed: list[dict[str, Mapping[str, object]]] = []
            original_write = controller.atomic_write_json

            def gated_write(path: Path, value: object) -> None:
                if path == claim_path:
                    writer_entered.set()
                    if not allow_write.wait(timeout=5):
                        raise RuntimeError("claim admission test timed out")
                original_write(path, value)

            def admit() -> None:
                claimed.append(dict(plane.claim_internal("RECON-010", "worker:first")))

            def read() -> None:
                reader_started.set()
                observed.append(plane.active_claims())
                reader_finished.set()

            with mock.patch.object(controller, "atomic_write_json", gated_write):
                writer = threading.Thread(target=admit)
                writer.start()
                self.assertTrue(writer_entered.wait(timeout=5))
                reader = threading.Thread(target=read)
                reader.start()
                self.assertTrue(reader_started.wait(timeout=5))
                self.assertFalse(
                    reader_finished.wait(timeout=0.1),
                    "claim read escaped before first admission committed",
                )
                allow_write.set()
                writer.join(timeout=5)
                reader.join(timeout=5)
            self.assertFalse(writer.is_alive())
            self.assertFalse(reader.is_alive())
            self.assertEqual(observed[0]["RECON-010"]["claim_id"], claimed[0]["claim_id"])

    def test_shared_directory_rejects_another_repository_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            first_root = base / "first"
            second_root = base / "second"
            shared = (base / "shared-state").resolve()
            first_root.mkdir()
            second_root.mkdir()
            install_fixture(first_root, repository="https://example.invalid/one.git")
            install_fixture(second_root, repository="https://example.invalid/two.git")
            first = controller.ControlPlane(first_root, state_dir=shared)
            second = controller.ControlPlane(second_root, state_dir=shared)
            ready_runtime(controller, first_root, state_dir=shared)
            with first.runtime_lock("claim-authority.lock"):
                pass
            with self.assertRaisesRegex(
                controller.ConfigurationError,
                "another repository",
            ):
                with second.runtime_lock("claim-authority.lock"):
                    self.fail("identity mismatch was accepted")

    def test_empty_claim_read_does_not_create_runtime_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install_fixture(root)
            plane = controller.ControlPlane(root)
            self.assertEqual(plane.active_claims(), {})
            self.assertFalse((plane.coordination_dir / "runtime-identity.json").exists())
            self.assertFalse((plane.coordination_dir / "locks").exists())

    def test_relative_explicit_state_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install_fixture(root)
            with self.assertRaisesRegex(
                controller.ConfigurationError,
                "must be absolute",
            ):
                controller.ControlPlane(root, state_dir="relative-state")

    def test_intermediate_state_link_is_rejected_before_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "repository"
            target = base / "real-authority"
            alias = base / "authority-alias"
            root.mkdir()
            target.mkdir()
            install_fixture(root)
            if os.name == "nt":
                linked = subprocess.run(
                    ("cmd", "/c", "mklink", "/J", str(alias), str(target)),
                    capture_output=True,
                    text=True,
                )
                if linked.returncode != 0:
                    self.skipTest(f"directory junction unavailable: {linked.stderr}")
            else:
                try:
                    os.symlink(target, alias, target_is_directory=True)
                except (NotImplementedError, OSError) as error:
                    self.skipTest(f"directory links unavailable: {error}")
            try:
                state = alias / "nested-state"
                with self.assertRaisesRegex(
                    controller.ConfigurationError,
                    "link component",
                ):
                    controller.ControlPlane(root, state_dir=state)
                with self.assertRaisesRegex(
                    controller.ConfigurationError,
                    "link component",
                ):
                    with controller.runtime_file_lock(state / "locks" / "test.lock"):
                        self.fail("runtime lock followed an intermediate link")
            finally:
                if alias.exists() or controller._is_link_like(alias):
                    if os.name == "nt":
                        os.rmdir(alias)
                    else:
                        alias.unlink()

    def test_stale_claim_archives_never_overwrite_same_fence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install_fixture(root)
            clock = Clock()
            plane = controller.ControlPlane(root, clock=clock)
            ready_runtime(controller, root)
            controller.atomic_write_json(
                plane.receipt_path("BOOT-000"),
                receipt(plane, "BOOT-000"),
            )
            claim = plane.claim_internal(
                "RECON-010",
                "worker:first",
                lease_minutes=1,
            )
            claim_id = str(claim["claim_id"])
            path = plane.claim_path("RECON-010")
            original = path.read_bytes()
            clock.advance(2)
            self.assertEqual(plane.clean_stale_claims(), ("RECON-010",))
            archive_dir = plane.coordination_dir / "stale-claims"
            first_archive = archive_dir / (claim_id.replace(":", "-") + ".json")
            first_bytes = first_archive.read_bytes()

            # Replaying the exact stale authority must retain a second archive;
            # mutating its owner while reusing claim_id is invalid authority and
            # is correctly rejected by the strict claim reader.
            path.write_bytes(original)
            self.assertEqual(plane.clean_stale_claims(), ("RECON-010",))
            second_archive = archive_dir / (
                claim_id.replace(":", "-") + "-2.json"
            )
            self.assertEqual(first_archive.read_bytes(), first_bytes)
            self.assertEqual(second_archive.read_bytes(), original)

    def test_failure_releases_only_the_untouched_remote_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install_fixture(root)
            plane = controller.ControlPlane(root)
            ready_runtime(controller, root)
            claim_id = "sha256:" + "3" * 64
            controller.atomic_write_json(
                plane.claim_path("RECON-010"),
                {
                    "node_id": "RECON-010",
                    "owner": "worker:failed",
                    "claim_id": claim_id,
                    "expires_at": "2099-01-01T00:00:00Z",
                    "remote": "origin",
                    "remote_claim_commit": "4" * 40,
                    "claim_authority_class": "PRIVILEGED_INTERNAL",
                    "launch_instruction_id": None,
                    "resource_key": None,
                    "authority_epoch": None,
                },
            )
            released: list[tuple[str, str, str]] = []
            plane.release_remote_claim = (  # type: ignore[method-assign]
                lambda node_id, commit, *, remote: released.append(
                    (node_id, commit, remote)
                )
            )
            plane.fail_internal(
                "RECON-010",
                "worker:failed",
                claim_id=claim_id,
                error="synthetic worker failure",
            )
            self.assertEqual(
                released,
                [("RECON-010", "4" * 40, "origin")],
            )
            self.assertFalse(plane.claim_path("RECON-010").exists())

    def test_remote_release_preserves_an_advanced_branch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install_fixture(root)
            plane = controller.ControlPlane(root)
            plane.remote_branch_sha = lambda *_args, **_kwargs: "5" * 40  # type: ignore[method-assign]

            def unexpected_git(*_args, **_kwargs):
                self.fail("advanced implementation branch was deleted")

            plane._git = unexpected_git  # type: ignore[method-assign]
            plane.release_remote_claim("RECON-010", "4" * 40)

    def test_malformed_claim_never_reads_as_absent_or_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install_fixture(root)
            plane = controller.ControlPlane(root)
            ready_runtime(controller, root)
            with plane.runtime_lock("claim-authority.lock"):
                pass
            path = plane.claim_path("RECON-010")
            path.parent.mkdir(parents=True, exist_ok=True)
            for label, raw in (
                ("json", b"{not-json\n"),
                (
                    "expiry",
                    (
                        json.dumps(
                            {
                                "node_id": "RECON-010",
                                "owner": "worker:legacy",
                                "expires_at": "not-a-time",
                            }
                        )
                        + "\n"
                    ).encode("utf-8"),
                ),
            ):
                with self.subTest(label=label):
                    path.write_bytes(raw)
                    with self.assertRaises(controller.ConfigurationError):
                        plane.active_claims()
                    with self.assertRaises(controller.ConfigurationError):
                        plane.clean_stale_claims()
                    self.assertEqual(path.read_bytes(), raw)

    def test_malformed_validation_lease_never_breaks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install_fixture(root)
            plane = controller.ControlPlane(root)
            ready_runtime(controller, root)
            with plane.runtime_lock("global-validation-lease.lock"):
                pass
            path = plane.validation_lease_path
            path.parent.mkdir(parents=True, exist_ok=True)
            lease_id = "sha256:" + "7" * 64
            malformed = b"{not-json\n"
            path.write_bytes(malformed)
            with self.assertRaises(controller.ConfigurationError):
                plane.break_expired_validation_lease(
                    actor="test:reaper",
                    lease_id=lease_id,
                )
            self.assertEqual(path.read_bytes(), malformed)
            value = {
                "schema_version": 1,
                "node_id": "RECON-010",
                "owner": "worker:legacy",
                "expires_at": "not-a-time",
                "lease_id": lease_id,
                "status": "ACTIVE",
            }
            controller.atomic_write_json(path, value)
            with self.assertRaisesRegex(controller.AutopilotError, "malformed"):
                plane.break_expired_validation_lease(
                    actor="test:reaper",
                    lease_id=lease_id,
                )
            self.assertTrue(path.is_file())

    def test_validation_archive_is_exclusive_and_identical_retry_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install_fixture(root)
            clock = Clock()
            plane = controller.ControlPlane(root, clock=clock)
            ready_runtime(controller, root)
            lease = plane.acquire_global_validation_lease_internal(
                "RECON-010",
                "worker:validator",
            )
            lease_id = str(lease["lease_id"])
            plane.release_global_validation_lease_internal(
                "RECON-010",
                "worker:validator",
                lease_id=lease_id,
            )
            archive = plane.coordination_dir / "validation-leases" / (
                lease_id.replace(":", "-") + ".json"
            )
            archived_bytes = archive.read_bytes()

            controller.atomic_write_json(plane.validation_lease_path, lease)
            clock.advance(1)
            plane.release_global_validation_lease_internal(
                "RECON-010",
                "worker:validator",
                lease_id=lease_id,
            )
            self.assertEqual(archive.read_bytes(), archived_bytes)
            self.assertFalse(plane.validation_lease_path.exists())

            controller.atomic_write_json(plane.validation_lease_path, lease)
            conflicting = json.loads(archive.read_text(encoding="utf-8"))
            conflicting["owner"] = "worker:other"
            controller.atomic_write_json(archive, conflicting)
            with self.assertRaisesRegex(
                controller.ConfigurationError,
                "conflicts",
            ):
                plane.release_global_validation_lease_internal(
                    "RECON-010",
                    "worker:validator",
                    lease_id=lease_id,
                )
            self.assertTrue(plane.validation_lease_path.is_file())


    def test_host_registry_cross_indexes_transport_and_monotonic_checkouts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            primary = base / "primary"
            alias = base / "alias"
            sibling = base / "sibling"
            for root in (primary, alias, sibling):
                install_fixture(root)
                subprocess.run(
                    ("git", "init", str(root)),
                    check=True,
                    capture_output=True,
                )
            shared_remote = base / "sealed-origin.git"
            shared_remote.mkdir()
            for root in (primary, alias, sibling):
                subprocess.run(
                    (
                        "git",
                        "-C",
                        str(root),
                        "config",
                        "remote.origin.url",
                        str(shared_remote),
                    ),
                    check=True,
                    capture_output=True,
                )
            alias_control_path = alias / ".autopilot" / "control-plane.json"
            alias_control = json.loads(alias_control_path.read_text(encoding="utf-8"))
            alias_control["target"]["repository"] = "Alias/Hive"
            alias_control_path.write_text(
                json.dumps(alias_control, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            host_base = base / "canonical-host-base"
            host_runtime = base / "host-runtime"
            with mock.patch.object(
                controller, "_host_runtime_base_dir", return_value=host_base
            ):
                controller.initialize_host_runtime(host_runtime)
                primary_identity = controller.runtime_repository_identity(primary)
                alias_identity = controller.runtime_repository_identity(alias)
                sibling_identity = controller.runtime_repository_identity(sibling)
                assert primary_identity and alias_identity and sibling_identity
                coordination = primary / ".autopilot" / "state"
                with controller.runtime_file_lock(
                    host_runtime / "locks" / "host-authority.lock"
                ):
                    controller.bind_host_repository_runtime(
                        host_runtime,
                        repository=str(primary_identity["repository"]),
                        transport_digest=str(primary_identity["transport_digest"]),
                        coordination_dir=coordination,
                        repo_root=primary,
                        bound_at="2030-01-01T00:00:00Z",
                    )
                    with self.assertRaisesRegex(
                        controller.ConfigurationError, "already bound|aliases"
                    ):
                        controller.bind_host_repository_runtime(
                            host_runtime,
                            repository=str(alias_identity["repository"]),
                            transport_digest=str(alias_identity["transport_digest"]),
                            coordination_dir=alias / ".autopilot" / "state",
                            repo_root=alias,
                            bound_at="2030-01-01T00:00:01Z",
                        )
                    controller.bind_host_repository_runtime(
                        host_runtime,
                        repository=str(sibling_identity["repository"]),
                        transport_digest=str(sibling_identity["transport_digest"]),
                        coordination_dir=coordination,
                        repo_root=sibling,
                        bound_at="2030-01-01T00:00:02Z",
                    )
                    bindings = controller.host_repository_registry_bindings(
                        host_runtime
                    )
                self.assertEqual(len(bindings), 1)
                self.assertEqual(
                    bindings[0]["checkout_roots"],
                    sorted((str(primary.resolve()), str(sibling.resolve()))),
                )


class HostKernelCapacityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.base_patch = mock.patch.object(
            controller,
            "_host_runtime_base_dir",
            return_value=self.base / "canonical-account-authority",
        )
        self.base_patch.start()
        self.host_runtime = self.base / "host-kernel"
        controller.initialize_host_runtime(self.host_runtime)
        self.clock = Clock()
        self.host_id = "app-server:sealed-provider"
        self.provider_digest = "sha256:" + "1" * 64

    def tearDown(self) -> None:
        self.base_patch.stop()
        self.temporary.cleanup()

    def publish(
        self,
        *,
        generation_digit: str,
        epoch: int,
        maximum: int,
        validation_slots: int,
        expires_minutes: int,
        expected_generation: str | None,
        declarative: bool = False,
    ) -> Mapping[str, object]:
        generation = "sha256:" + generation_digit * 64
        now = self.clock()
        with controller.runtime_file_lock(
            self.host_runtime / "locks" / "host-authority.lock"
        ):
            return controller.publish_host_capacity(
                self.host_runtime,
                host_id=self.host_id,
                capacity_generation=generation,
                capacity_epoch=epoch,
                max_total_sessions=maximum,
                validation_slots=validation_slots,
                issued_at=controller.format_time(now),
                expires_at=controller.format_time(
                    now + timedelta(minutes=expires_minutes)
                ),
                capability_source="fixture:external-capacity",
                capability_digest="sha256:" + generation_digit * 64,
                provider_identity_source="fixture:app-server-provider",
                provider_identity_digest=self.provider_digest,
                declarative=declarative,
                now=now,
                expected_generation=expected_generation,
            )

    def reserve(
        self,
        local_digit: str,
        *,
        kind: str = "PRIMARY",
        repository: str = "Example/Hive",
        execution_id: str = "sha256:" + "a" * 64,
        resource_key: str | None = None,
    ) -> Mapping[str, object]:
        capacity = controller.read_host_capacity(
            self.host_runtime, self.host_id, now=self.clock()
        )
        with controller.runtime_file_lock(
            self.host_runtime / "locks" / "host-authority.lock"
        ):
            return controller.reserve_global_host_session(
                self.host_runtime,
                repository=repository,
                execution_id=execution_id,
                host_id=self.host_id,
                capacity_generation=str(capacity["capacity_generation"]),
                local_reservation_id="sha256:" + local_digit * 64,
                reservation_kind=kind,
                resource_key=resource_key or "sha256:" + local_digit * 64,
                write_scopes=(),
                actor_time=controller.format_time(self.clock()),
                expires_at=str(capacity["expires_at"]),
                now=self.clock(),
            )

    def install_dispatch_abort_receipt(
        self,
        plane: object,
        reservation: Mapping[str, object],
        *,
        node_id: str = "TEST-PRIMARY",
        admission_epoch: int = 7,
    ) -> Mapping[str, object]:
        release_base: dict[str, object] = {
            "schema_version": 1,
            "kind": "hive-mind-autopilot-dispatch-release-v1",
            "actor": "test:dispatcher-rollback",
            "execution_namespace": plane.execution_namespace,
            "execution_id": plane.execution_id,
            "repository": plane.repository_identity["repository"],
            "target_branch": plane.target_branch,
            "target_sha": plane.current_target_sha(),
            "target_generation": 1,
            "target_watermark_record_id": plane.repository_target_watermark()[
                "record_id"
            ],
            "plan_fingerprint": plane.expected_plan_fingerprint,
            "reconciliation_digest": "sha256:" + "1" * 64,
            "github_snapshot_digest": "sha256:" + "2" * 64,
            "snapshot_observation_id": "sha256:" + "3" * 64,
            "snapshot_observation_epoch": 1,
            "snapshot_observation_record_id": "sha256:" + "4" * 64,
            "host_id": reservation["host_id"],
            "capacity_generation": reservation["capacity_generation"],
            "capacity_epoch": reservation["capacity_epoch"],
            "capacity_record_id": "sha256:" + "5" * 64,
            "capacity_max_total_sessions": 1,
            "capacity_validation_slots": 1,
            "session_cap": 1,
            "admission_epoch": admission_epoch,
            "supersedes_release_id": None,
            "released_wave": [node_id],
            "directive": "START NOW",
            "action": "fixture",
            "verdicts": {node_id: "START NOW"},
            "issued_at": controller.format_time(self.clock()),
            "receipt_retirement_execution_digest": None,
        }
        release_admission_id = controller.digest_json(
            {
                "kind": "hive-mind-release-admission-key-v1",
                "release": release_base,
            }
        )
        release_material = {
            **release_base,
            "primary_host_reservations": [
                {
                    "node_id": node_id,
                    "resource_key": reservation["resource_key"],
                    "reservation_id": reservation["reservation_id"],
                }
            ],
            "release_admission_id": release_admission_id,
        }
        release = {
            **release_material,
            "release_id": controller.digest_json(release_material),
        }
        intent_material: dict[str, object] = {
            "schema_version": 1,
            "kind": controller.DISPATCH_ADMISSION_INTENT_KIND,
            "execution_namespace": plane.execution_namespace,
            "execution_id": plane.execution_id,
            "repository": plane.repository_identity["repository"],
            "release_admission_id": release_admission_id,
            "release_id": release["release_id"],
            "admission_epoch": admission_epoch,
            "target_sha": plane.current_target_sha(),
            "target_generation": 1,
            "target_watermark_record_id": release_base[
                "target_watermark_record_id"
            ],
            "plan_fingerprint": plane.expected_plan_fingerprint,
            "snapshot_observation_record_id": release_base[
                "snapshot_observation_record_id"
            ],
            "host_id": reservation["host_id"],
            "provider_generation": reservation["provider_generation"],
            "provider_epoch": reservation["provider_epoch"],
            "capacity_generation": reservation["capacity_generation"],
            "capacity_epoch": reservation["capacity_epoch"],
            "reservations": [
                {
                    "node_id": node_id,
                    "resource_key": reservation["resource_key"],
                    "local_reservation_id": reservation[
                        "local_reservation_id"
                    ],
                    "reservation_id": reservation["reservation_id"],
                }
            ],
            "release": release,
            "actor": "test:dispatcher-rollback",
            "issued_at": controller.format_time(self.clock()),
        }
        intent = {
            **intent_material,
            "record_id": controller.digest_json(intent_material),
        }
        intent_path = (
            plane.execution_dir
            / "di"
            / f"{release_admission_id.removeprefix('sha256:')}.json"
        )
        controller.exclusive_write_json_or_identical(intent_path, intent)
        empty_activity = {
            "active_write_launch_reservation_ids": [],
            "active_host_reservation_ids": [],
            "host_effect_obligation_ids": [],
        }
        abort_material: dict[str, object] = {
            "schema_version": 1,
            "kind": controller.PRE_LAUNCH_ABORT_KIND,
            "state": "NEVER_LAUNCHED",
            "execution_namespace": plane.execution_namespace,
            "execution_id": plane.execution_id,
            "repository": reservation["repository"],
            "release_id": release["release_id"],
            "release_admission_id": release_admission_id,
            "admission_epoch": admission_epoch,
            "intent_record_id": intent["record_id"],
            "reservation_id": reservation["reservation_id"],
            "local_reservation_id": reservation["local_reservation_id"],
            "resource_key": reservation["resource_key"],
            "node_id": node_id,
            "host_id": reservation["host_id"],
            "provider_generation": reservation["provider_generation"],
            "capacity_generation": reservation["capacity_generation"],
            **empty_activity,
            "empty_activity_digest": controller.digest_json(empty_activity),
            "reason": "DISPATCH_ADMISSION_ABORTED_BEFORE_LAUNCH",
            "actor": "test:dispatcher-rollback",
            "recorded_at": controller.format_time(self.clock()),
        }
        return {
            **abort_material,
            "record_id": controller.digest_json(abort_material),
        }

    def test_one_provider_and_one_aggregate_budget(self) -> None:
        self.publish(
            generation_digit="2",
            epoch=1,
            maximum=2,
            validation_slots=1,
            expires_minutes=10,
            expected_generation=None,
        )
        self.reserve("3")
        self.reserve("4")
        with self.assertRaisesRegex(
            controller.ConfigurationError, "capacity is exhausted"
        ):
            self.reserve("5")
        with controller.runtime_file_lock(
            self.host_runtime / "locks" / "host-authority.lock"
        ):
            with self.assertRaisesRegex(
                controller.ConfigurationError, "provider cannot rotate"
            ):
                controller.publish_host_capacity(
                    self.host_runtime,
                    host_id="cli-selected-peer",
                    capacity_generation="sha256:" + "6" * 64,
                    capacity_epoch=1,
                    max_total_sessions=2,
                    validation_slots=1,
                    issued_at=controller.format_time(self.clock()),
                    expires_at=controller.format_time(
                        self.clock() + timedelta(minutes=10)
                    ),
                    capability_source="fixture:external-capacity",
                    capability_digest="sha256:" + "6" * 64,
                    provider_identity_source="fixture:app-server-provider",
                    provider_identity_digest=self.provider_digest,
                    declarative=False,
                    now=self.clock(),
                    expected_generation=None,
                )

    def test_declarative_capacity_is_conservative(self) -> None:
        with self.assertRaisesRegex(
            controller.ConfigurationError, "limited to one"
        ):
            self.publish(
                generation_digit="7",
                epoch=1,
                maximum=2,
                validation_slots=1,
                expires_minutes=10,
                expected_generation=None,
                declarative=True,
            )

    def test_provider_generation_upgrades_only_at_zero_activity_and_cannot_downgrade(self) -> None:
        first = self.publish(
            generation_digit="2",
            epoch=1,
            maximum=1,
            validation_slots=1,
            expires_minutes=10,
            expected_generation=None,
        )
        original_provider_digest = self.provider_digest
        self.provider_digest = "sha256:" + "3" * 64
        upgraded = self.publish(
            generation_digit="4",
            epoch=2,
            maximum=1,
            validation_slots=1,
            expires_minutes=10,
            expected_generation=str(first["capacity_generation"]),
        )
        self.assertEqual(upgraded["provider_epoch"], 2)
        self.assertNotEqual(
            upgraded["provider_generation"], first["provider_generation"]
        )
        self.provider_digest = original_provider_digest
        with self.assertRaisesRegex(
            controller.ConfigurationError, "downgrade or replay"
        ):
            self.publish(
                generation_digit="5",
                epoch=3,
                maximum=1,
                validation_slots=1,
                expires_minutes=10,
                expected_generation=str(upgraded["capacity_generation"]),
            )

    def test_provider_upgrade_crash_reuses_exact_history_generation(self) -> None:
        first = self.publish(
            generation_digit="2",
            epoch=1,
            maximum=1,
            validation_slots=1,
            expires_minutes=10,
            expected_generation=None,
        )
        provider_path = self.host_runtime / "host-provider.json"
        original_atomic_write = controller.atomic_write_json

        def crash_before_provider_current(path: Path, value: object) -> None:
            if path == provider_path:
                raise RuntimeError("synthetic provider current crash")
            original_atomic_write(path, value)

        self.provider_digest = "sha256:" + "6" * 64
        with mock.patch.object(
            controller, "atomic_write_json", side_effect=crash_before_provider_current
        ):
            with self.assertRaisesRegex(RuntimeError, "provider current"):
                self.publish(
                    generation_digit="7",
                    epoch=2,
                    maximum=1,
                    validation_slots=1,
                    expires_minutes=10,
                    expected_generation=str(first["capacity_generation"]),
                )
        history_path = self.host_runtime / "host-provider-history.jsonl"
        pending = controller.strict_jsonl_records(
            history_path, label="test provider history"
        )[-1]
        self.assertEqual(pending["provider_epoch"], 2)
        self.clock.advance(1)
        resumed = self.publish(
            generation_digit="7",
            epoch=2,
            maximum=1,
            validation_slots=1,
            expires_minutes=10,
            expected_generation=str(first["capacity_generation"]),
        )
        installed = controller.read_strict_canonical_json(
            provider_path, label="test provider current"
        )
        self.assertEqual(installed, pending)
        self.assertEqual(resumed["provider_generation"], pending["provider_generation"])
        self.assertEqual(
            len(controller.strict_jsonl_records(
                history_path, label="test provider history"
            )),
            2,
        )

    def test_expired_active_reservation_still_blocks_provider_upgrade(self) -> None:
        first = self.publish(
            generation_digit="8",
            epoch=1,
            maximum=1,
            validation_slots=1,
            expires_minutes=1,
            expected_generation=None,
        )
        self.reserve("9")
        self.clock.advance(2)
        self.provider_digest = "sha256:" + "a" * 64
        with self.assertRaisesRegex(
            controller.ConfigurationError, "reservations remain active"
        ):
            self.publish(
                generation_digit="b",
                epoch=2,
                maximum=1,
                validation_slots=1,
                expires_minutes=10,
                expected_generation=str(first["capacity_generation"]),
            )

    def test_capacity_history_crash_retry_reuses_exact_sealed_candidate(self) -> None:
        capacity_path = controller.host_capacity_path(
            self.host_runtime, self.host_id
        )
        original_atomic_write = controller.atomic_write_json

        def crash_before_current(path: Path, value: object) -> None:
            if path == capacity_path:
                raise RuntimeError("synthetic crash after capacity history append")
            original_atomic_write(path, value)

        with mock.patch.object(
            controller, "atomic_write_json", side_effect=crash_before_current
        ):
            with self.assertRaisesRegex(RuntimeError, "history append"):
                self.publish(
                    generation_digit="6",
                    epoch=1,
                    maximum=1,
                    validation_slots=1,
                    expires_minutes=10,
                    expected_generation=None,
                )
        history_path = capacity_path.parent / "capacity-history.jsonl"
        history = controller._strict_capacity_history(history_path)
        self.assertEqual(len(history), 1)
        sealed = history[0]["capacity_record"]
        self.assertIsInstance(sealed, Mapping)
        self.assertFalse(capacity_path.exists())

        # A restarted adapter computes a new time window, but the already
        # durable generation candidate is the only lawful value to install.
        self.clock.advance(1)
        resumed = self.publish(
            generation_digit="6",
            epoch=1,
            maximum=1,
            validation_slots=1,
            expires_minutes=10,
            expected_generation=None,
        )
        self.assertEqual(resumed, sealed)
        self.assertEqual(
            len(controller._strict_capacity_history(history_path)), 1
        )

        # A retry after current replacement is equally idempotent and cannot
        # use a new timestamp as a pretext to widen the sealed capacity.
        self.clock.advance(1)
        self.assertEqual(
            self.publish(
                generation_digit="6",
                epoch=1,
                maximum=1,
                validation_slots=1,
                expires_minutes=10,
                expected_generation=None,
            ),
            sealed,
        )
        with self.assertRaisesRegex(
            controller.ConfigurationError, "conflicts with installed bytes"
        ):
            self.publish(
                generation_digit="6",
                epoch=1,
                maximum=2,
                validation_slots=1,
                expires_minutes=10,
                expected_generation=None,
            )

    def test_same_policy_capacity_renewal_keeps_live_session_across_expiry(self) -> None:
        capacity = self.publish(
            generation_digit="6",
            epoch=1,
            maximum=1,
            validation_slots=1,
            expires_minutes=30,
            expected_generation=None,
        )
        reservation = self.reserve("7")
        predecessor_expiry = str(capacity["expires_at"])
        self.clock.advance(16)
        renewed_at = controller.format_time(self.clock())
        successor_expiry = controller.format_time(
            self.clock() + timedelta(minutes=60)
        )
        capacity_path = controller.host_capacity_path(
            self.host_runtime, self.host_id
        )
        original_atomic_write = controller.atomic_write_json

        def crash_after_renewal_intent(path: Path, value: object) -> None:
            if path == capacity_path:
                raise RuntimeError("synthetic capacity renewal crash")
            original_atomic_write(path, value)

        arguments = {
            "host_id": self.host_id,
            "capacity_generation": capacity["capacity_generation"],
            "expected_capacity_record_id": capacity["record_id"],
            "issued_at": renewed_at,
            "expires_at": successor_expiry,
            "capability_source": capacity["capability_source"],
            "capability_digest": capacity["capability_digest"],
            "provider_identity_source": "fixture:app-server-provider",
            "provider_identity_digest": self.provider_digest,
            "actor": "test:capacity-renewer",
        }
        with controller.runtime_file_lock(
            self.host_runtime / "locks" / "host-authority.lock"
        ):
            with self.assertRaisesRegex(
                controller.ConfigurationError, "provider, policy, or capability"
            ):
                controller.renew_host_capacity_authority(
                    self.host_runtime,
                    **{**arguments, "capability_digest": "sha256:" + "8" * 64},
                    now=self.clock(),
                )
            with self.assertRaisesRegex(
                controller.ConfigurationError, "provider differs"
            ):
                controller.renew_host_capacity_authority(
                    self.host_runtime,
                    **{
                        **arguments,
                        "provider_identity_digest": "sha256:" + "9" * 64,
                    },
                    now=self.clock(),
                )
        with controller.runtime_file_lock(
            self.host_runtime / "locks" / "host-authority.lock"
        ), mock.patch.object(
            controller,
            "atomic_write_json",
            side_effect=crash_after_renewal_intent,
        ):
            with self.assertRaisesRegex(RuntimeError, "renewal crash"):
                controller.renew_host_capacity_authority(
                    self.host_runtime, **arguments, now=self.clock()
                )

        # Restart after the predecessor wall-clock expiry.  The exact durable
        # renewal candidate and active-permit cut complete; clock expiry alone
        # never frees or duplicates the external session.
        self.clock.advance(15)
        with controller.runtime_file_lock(
            self.host_runtime / "locks" / "host-authority.lock"
        ):
            renewed = controller.renew_host_capacity_authority(
                self.host_runtime, **arguments, now=self.clock()
            )
            active = controller.active_global_host_reservations(self.host_runtime)
            replayed = controller.renew_host_capacity_authority(
                self.host_runtime, **arguments, now=self.clock()
            )
        self.assertEqual(renewed, replayed)
        self.assertEqual(
            renewed["capacity_generation"], capacity["capacity_generation"]
        )
        self.assertEqual(renewed["capacity_epoch"], capacity["capacity_epoch"])
        self.assertNotEqual(renewed["record_id"], capacity["record_id"])
        self.assertEqual(renewed["expires_at"], successor_expiry)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["reservation_id"], reservation["reservation_id"])
        self.assertEqual(active[0]["expires_at"], successor_expiry)
        self.assertEqual(active[0]["prior_expires_at"], predecessor_expiry)
        history = controller._strict_capacity_history(
            capacity_path.parent / "capacity-history.jsonl"
        )
        self.assertEqual(len(history), 2)
        self.assertEqual(history[-1]["rotation_reason"], "SAME_POLICY_RENEWAL")

    def test_pending_capacity_renewal_reconciles_partial_permit_cut_and_lineage(self) -> None:
        capacity = self.publish(
            generation_digit="4",
            epoch=1,
            maximum=2,
            validation_slots=1,
            expires_minutes=30,
            expected_generation=None,
        )
        first = self.reserve("5")
        second = self.reserve("6")
        self.clock.advance(16)
        arguments = {
            "host_id": self.host_id,
            "capacity_generation": capacity["capacity_generation"],
            "expected_capacity_record_id": capacity["record_id"],
            "issued_at": controller.format_time(self.clock()),
            "expires_at": controller.format_time(
                self.clock() + timedelta(minutes=60)
            ),
            "capability_source": capacity["capability_source"],
            "capability_digest": capacity["capability_digest"],
            "provider_identity_source": "fixture:app-server-provider",
            "provider_identity_digest": self.provider_digest,
            "actor": "test:partial-capacity-renewer",
        }
        original_append = controller._append_host_reservation_unlocked
        appended = 0

        def crash_after_first_permit(*args, **kwargs):
            nonlocal appended
            if appended == 1:
                raise RuntimeError("synthetic crash after one permit renewal")
            event = original_append(*args, **kwargs)
            appended += 1
            return event

        with controller.runtime_file_lock(
            self.host_runtime / "locks" / "host-authority.lock"
        ), mock.patch.object(
            controller,
            "_append_host_reservation_unlocked",
            side_effect=crash_after_first_permit,
        ):
            with self.assertRaisesRegex(RuntimeError, "one permit renewal"):
                controller.renew_host_capacity_authority(
                    self.host_runtime,
                    **arguments,
                    now=self.clock(),
                )

        capacity_path = controller.host_capacity_path(
            self.host_runtime, self.host_id
        )
        installed_after_crash = controller.read_strict_canonical_json(
            capacity_path,
            label="partially renewed host capacity",
        )
        self.assertNotEqual(installed_after_crash["record_id"], capacity["record_id"])
        with controller.runtime_file_lock(
            self.host_runtime / "locks" / "host-authority.lock"
        ):
            before = controller._host_reservation_events_unlocked(self.host_runtime)
            reconciled = controller.reconcile_pending_host_capacity_renewal(
                self.host_runtime,
                host_id=self.host_id,
                now=self.clock(),
            )
            after = controller._host_reservation_events_unlocked(self.host_runtime)
            active = controller.active_global_host_reservations(self.host_runtime)
            old_issuance = controller.host_capacity_record_in_current_lineage(
                self.host_runtime,
                self.host_id,
                capacity_generation=str(capacity["capacity_generation"]),
                record_id=str(capacity["record_id"]),
            )
            new_issuance = controller.host_capacity_record_in_current_lineage(
                self.host_runtime,
                self.host_id,
                capacity_generation=str(capacity["capacity_generation"]),
                record_id=str(reconciled["record_id"]),
            )
            replayed = controller.reconcile_pending_host_capacity_renewal(
                self.host_runtime,
                host_id=self.host_id,
                now=self.clock(),
            )
            with self.assertRaisesRegex(
                controller.ConfigurationError, "outside the current lineage"
            ):
                controller.host_capacity_record_in_current_lineage(
                    self.host_runtime,
                    self.host_id,
                    capacity_generation=str(capacity["capacity_generation"]),
                    record_id="sha256:" + "f" * 64,
                )
        self.assertEqual(reconciled, replayed)
        self.assertEqual(old_issuance, capacity)
        self.assertEqual(new_issuance, reconciled)
        self.assertEqual(len(after), len(before) + 1)
        self.assertEqual(
            {item["reservation_id"] for item in active},
            {first["reservation_id"], second["reservation_id"]},
        )
        self.assertTrue(
            all(item["expires_at"] == reconciled["expires_at"] for item in active)
        )

    def test_expired_keyed_validation_recovers_both_crash_orders_and_capacity(self) -> None:
        capacity = self.publish(
            generation_digit="5",
            epoch=1,
            maximum=1,
            validation_slots=1,
            expires_minutes=30,
            expected_generation=None,
        )
        repo_root = self.base / "validation-repository"
        repo_root.mkdir()
        install_fixture(repo_root)
        ready_runtime(controller, repo_root)
        plane = controller.ControlPlane(
            repo_root,
            clock=self.clock,
            host_runtime_dir=self.host_runtime,
        )
        release_id = "sha256:" + "7" * 64
        transaction_sha = "8" * 40
        repository = str(plane.control["target"]["repository"])

        def install_lease(node_id: str, owner: str) -> tuple[dict[str, object], Mapping[str, object]]:
            local_id = controller.digest_json(
                {
                    "kind": "hive-mind-keyed-validation-reservation-v1",
                    "execution_id": plane.execution_id,
                    "release_id": release_id,
                    "transaction_sha": transaction_sha,
                    "node_id": node_id,
                    "owner": owner,
                }
            )
            with controller.runtime_file_lock(
                self.host_runtime / "locks" / "host-authority.lock"
            ):
                reservation = controller.reserve_global_host_session(
                    self.host_runtime,
                    repository=repository,
                    execution_id=plane.execution_id,
                    host_id=self.host_id,
                    capacity_generation=str(capacity["capacity_generation"]),
                    local_reservation_id=local_id,
                    reservation_kind="VALIDATION",
                    resource_key=plane.validation_resource_key,
                    write_scopes=(),
                    actor_time=controller.format_time(self.clock()),
                    expires_at=str(capacity["expires_at"]),
                    now=self.clock(),
                )
            lease: dict[str, object] = {
                "schema_version": 1,
                "node_id": node_id,
                "owner": owner,
                "target_sha": plane.current_target_sha(),
                "acquired_at": controller.format_time(self.clock()),
                "expires_at": controller.format_time(
                    self.clock() + timedelta(minutes=1)
                ),
                "renewal_count": 0,
                "status": "ACTIVE",
                "execution_id": plane.execution_id,
                "validation_resource_key": plane.validation_resource_key,
                "authority_nonce": "9" * 64,
                "claim_id": None,
                "claim_authority_class": controller.INTERNAL_CLAIM_AUTHORITY,
                "launch_instruction_id": None,
                "resource_key": None,
                "authority_epoch": None,
                "release_id": release_id,
                "transaction_sha": transaction_sha,
                "host_reservation_id": reservation["reservation_id"],
                "capacity_host_id": self.host_id,
                "capacity_generation": capacity["capacity_generation"],
            }
            lease["lease_id"] = controller.digest_json(lease)
            controller.atomic_write_json(plane.validation_lease_path, lease)
            return lease, reservation

        first_lease, first_reservation = install_lease(
            "RECON-010", "validator:first"
        )
        self.clock.advance(2)
        with mock.patch.object(
            controller,
            "release_global_host_session",
            side_effect=RuntimeError("synthetic crash after lease archive"),
        ):
            with self.assertRaisesRegex(RuntimeError, "lease archive"):
                plane.recover_expired_keyed_validation_lease_internal(
                    actor="test:expiry-recovery",
                    lease_id=str(first_lease["lease_id"]),
                )
        self.assertFalse(plane.validation_lease_path.exists())
        recovered = plane.recover_expired_keyed_validation_lease_internal(
            actor="test:expiry-recovery",
            host_reservation_id=str(first_reservation["reservation_id"]),
        )
        self.assertEqual(recovered["state"], "RECOVERED")
        self.assertEqual(recovered["reservation"]["state"], "RELEASED")

        second_lease, second_reservation = install_lease(
            "BASE-020", "validator:second"
        )
        self.clock.advance(2)
        with controller.runtime_file_lock(
            self.host_runtime / "locks" / "host-authority.lock"
        ):
            with self.assertRaisesRegex(
                controller.ConfigurationError,
                "terminal lease or never-acquired evidence",
            ):
                controller.release_global_host_session(
                    self.host_runtime,
                    str(second_reservation["reservation_id"]),
                    execution_id=plane.execution_id,
                    local_reservation_id=str(
                        second_reservation["local_reservation_id"]
                    ),
                    capacity_generation=str(
                        second_reservation["capacity_generation"]
                    ),
                    actor="test:reverse-crash",
                    reason="evidence-free reservation release must remain charged",
                    released_at=controller.format_time(self.clock()),
                )
            still_charged = controller.global_host_reservation_record(
                self.host_runtime,
                str(second_reservation["reservation_id"]),
            )
        self.assertIn(still_charged["state"], controller.HOST_RESERVATION_ACTIVE_STATES)
        reverse = plane.recover_expired_keyed_validation_lease_internal(
            actor="test:expiry-recovery",
            lease_id=str(second_lease["lease_id"]),
        )
        self.assertEqual(reverse["reservation"]["state"], "RELEASED")
        self.assertFalse(plane.validation_lease_path.exists())

        # The single aggregate validation slot is reusable only after both
        # durable authorities reach terminal state.
        third_lease, _third_reservation = install_lease(
            "GRAPH-030", "validator:third"
        )
        self.assertEqual(third_lease["status"], "ACTIVE")

    def test_keyed_validation_release_requires_local_terminal_archive(self) -> None:
        capacity = self.publish(
            generation_digit="b",
            epoch=1,
            maximum=1,
            validation_slots=1,
            expires_minutes=60,
            expected_generation=None,
        )
        repo_root = self.base / "validation-release-repository"
        install_fixture(repo_root)
        ready_runtime(controller, repo_root)
        plane = controller.ControlPlane(
            repo_root,
            clock=self.clock,
            host_runtime_dir=self.host_runtime,
        )
        node_id = next(iter(plane._nodes))
        release_id = "sha256:" + "c" * 64
        transaction_sha = "d" * 40
        release = {
            "release_id": release_id,
            "admission_epoch": 1,
            "target_sha": plane.current_target_sha(),
        }
        plane.current_release = lambda: release  # type: ignore[attr-defined]
        plane._release_issues = lambda _value: ()  # type: ignore[attr-defined]

        acquired = plane.acquire_keyed_validation_lease_internal(
            node_id,
            "validator:normal-release",
            host_id=self.host_id,
            release_id=release_id,
            transaction_sha=transaction_sha,
        )
        reservation_id = str(acquired["global_host_reservation_id"])
        with mock.patch.object(
            plane,
            "release_global_validation_lease",
            side_effect=RuntimeError("synthetic local terminalization failure"),
        ):
            with self.assertRaisesRegex(
                controller.AutopilotError, "local terminalization failure"
            ):
                plane.release_keyed_validation_lease_internal(
                    node_id,
                    "validator:normal-release",
                    lease_id=str(acquired["lease_id"]),
                    host_id=self.host_id,
                    release_id=release_id,
                    transaction_sha=transaction_sha,
                )
        with controller.runtime_file_lock(
            self.host_runtime / "locks" / "host-authority.lock"
        ):
            charged = controller.global_host_reservation_record(
                self.host_runtime, reservation_id
            )
        self.assertIn(charged["state"], controller.HOST_RESERVATION_ACTIVE_STATES)

        settled = plane.release_keyed_validation_lease_internal(
            node_id,
            "validator:normal-release",
            lease_id=str(acquired["lease_id"]),
            host_id=self.host_id,
            release_id=release_id,
            transaction_sha=transaction_sha,
        )
        replayed = plane.release_keyed_validation_lease_internal(
            node_id,
            "validator:normal-release",
            lease_id=str(acquired["lease_id"]),
            host_id=self.host_id,
            release_id=release_id,
            transaction_sha=transaction_sha,
        )
        self.assertEqual(
            settled["host_reservation"]["event_id"],
            replayed["host_reservation"]["event_id"],
        )
        self.assertEqual(
            settled["host_reservation"]["external_cancellation"],
            "CONFIRMED_VALIDATION_TERMINAL",
        )
        evidence_path = self.host_runtime / str(
            settled["host_reservation"]["validation_terminal_evidence_path"]
        )
        self.assertTrue(evidence_path.is_file())
        self.assertEqual(
            settled["host_reservation"]["capacity_generation"],
            capacity["capacity_generation"],
        )

    def test_keyed_validation_never_acquired_rollback_is_host_authenticated(self) -> None:
        self.publish(
            generation_digit="e",
            epoch=1,
            maximum=1,
            validation_slots=1,
            expires_minutes=60,
            expected_generation=None,
        )
        repo_root = self.base / "validation-never-acquired-repository"
        install_fixture(repo_root)
        ready_runtime(controller, repo_root)
        plane = controller.ControlPlane(
            repo_root,
            clock=self.clock,
            host_runtime_dir=self.host_runtime,
        )
        node_id = next(iter(plane._nodes))
        release_id = "sha256:" + "1" * 64
        transaction_sha = "2" * 40
        release = {
            "release_id": release_id,
            "admission_epoch": 1,
            "target_sha": plane.current_target_sha(),
        }
        plane.current_release = lambda: release  # type: ignore[attr-defined]
        plane._release_issues = lambda _value: ()  # type: ignore[attr-defined]
        with mock.patch.object(
            plane,
            "acquire_global_validation_lease",
            side_effect=RuntimeError("synthetic lease admission refusal"),
        ):
            with self.assertRaisesRegex(RuntimeError, "admission refusal") as refusal:
                plane.acquire_keyed_validation_lease_internal(
                    node_id,
                    "validator:never-acquired",
                    host_id=self.host_id,
                    release_id=release_id,
                    transaction_sha=transaction_sha,
                )
        self.assertIs(type(refusal.exception), RuntimeError, str(refusal.exception))
        with controller.runtime_file_lock(
            self.host_runtime / "locks" / "host-authority.lock"
        ):
            events = controller._host_reservation_events_unlocked(self.host_runtime)
            active = controller.active_global_host_reservations(self.host_runtime)
        terminal = events[-1]
        self.assertEqual(active, ())
        self.assertEqual(terminal["reservation_kind"], "VALIDATION")
        self.assertEqual(
            terminal["external_cancellation"],
            "CONFIRMED_VALIDATION_NEVER_ACQUIRED",
        )
        self.assertEqual(
            terminal["validation_terminal_evidence_type"], "NEVER_ACQUIRED"
        )
        evidence_path = self.host_runtime / str(
            terminal["validation_terminal_evidence_path"]
        )
        source_path = controller._validation_never_acquired_source_path(
            plane.execution_dir,
            str(terminal["reservation_id"]),
        )
        self.assertEqual(evidence_path.read_bytes(), source_path.read_bytes())

    def test_expired_generation_rotates_only_after_terminal_recovery(self) -> None:
        first = self.publish(
            generation_digit="8",
            epoch=1,
            maximum=1,
            validation_slots=1,
            expires_minutes=5,
            expected_generation=None,
        )
        reservation = self.reserve("9")
        self.clock.advance(6)
        with self.assertRaisesRegex(
            controller.ConfigurationError, "reservations remain active"
        ):
            self.publish(
                generation_digit="a",
                epoch=2,
                maximum=1,
                validation_slots=1,
                expires_minutes=10,
                expected_generation=str(first["capacity_generation"]),
            )
        observation: dict[str, object] = {
            "schema_version": 1,
            "kind": controller.HOST_LIFECYCLE_OBSERVATION_KIND,
            "host_id": self.host_id,
            "reservation_id": reservation["reservation_id"],
            "execution_id": reservation["execution_id"],
            "local_reservation_id": reservation["local_reservation_id"],
            "capacity_generation": reservation["capacity_generation"],
            "host_task_id": "thread:terminal",
            "host_cursor": "cursor:terminal",
            "capability_digest": "sha256:" + "b" * 64,
            "state": "TERMINAL",
            "terminal_state": "SUCCEEDED",
            "observed_at": controller.format_time(self.clock()),
            "source_event_id": "sha256:" + "c" * 64,
        }
        observation["observation_id"] = controller.digest_json(observation)
        with controller.runtime_file_lock(
            self.host_runtime / "locks" / "host-authority.lock"
        ):
            fenced = controller.fence_expired_global_host_session(
                self.host_runtime,
                str(reservation["reservation_id"]),
                execution_id=str(reservation["execution_id"]),
                local_reservation_id=str(reservation["local_reservation_id"]),
                capacity_generation=str(reservation["capacity_generation"]),
                actor="test:reconciler",
                reason="authenticated terminal lifecycle after crash",
                fenced_at=controller.format_time(self.clock()),
                now=self.clock(),
                lifecycle_observation=observation,
                local_terminal_event_id="sha256:" + "d" * 64,
            )
        observation_path = self.host_runtime / str(
            fenced["lifecycle_observation_path"]
        )
        self.assertTrue(observation_path.is_file())
        with tempfile.TemporaryDirectory(
            dir=self.base, prefix="unrelated-coordinator-execution-"
        ) as coordinator_execution:
            Path(coordinator_execution, "local-copy.json").write_text(
                "disposable coordinator evidence\n", encoding="utf-8"
            )
        # Replay and capacity rotation depend only on immutable host-kernel
        # evidence, not on the coordinator execution that obtained it.
        with controller.runtime_file_lock(
            self.host_runtime / "locks" / "host-authority.lock"
        ):
            reopened = controller.global_host_reservation_record(
                self.host_runtime, str(reservation["reservation_id"])
            )
        self.assertEqual(reopened, fenced)
        rotated = self.publish(
            generation_digit="a",
            epoch=2,
            maximum=1,
            validation_slots=1,
            expires_minutes=10,
            expected_generation=str(first["capacity_generation"]),
        )
        self.assertEqual(rotated["capacity_epoch"], 2)

    def test_pre_launch_abort_is_idempotent_and_does_not_poison_rotation(self) -> None:
        repo_root = self.base / "pre-launch-repo"
        install_fixture(repo_root)
        ready_runtime(controller, repo_root)
        plane = controller.ControlPlane(repo_root)
        first = self.publish(
            generation_digit="2",
            epoch=1,
            maximum=1,
            validation_slots=1,
            expires_minutes=10,
            expected_generation=None,
        )
        reservation = self.reserve(
            "3",
            repository=str(plane.repository_identity["repository"]),
            execution_id=plane.execution_id,
        )
        abort_receipt = self.install_dispatch_abort_receipt(
            plane, reservation
        )
        with controller.runtime_file_lock(
            self.host_runtime / "locks" / "host-authority.lock"
        ):
            released = controller.release_global_host_session(
                self.host_runtime,
                str(reservation["reservation_id"]),
                execution_id=str(reservation["execution_id"]),
                local_reservation_id=str(reservation["local_reservation_id"]),
                capacity_generation=str(reservation["capacity_generation"]),
                actor="test:dispatcher-rollback",
                reason="dispatcher transaction aborted before local PREPARED",
                released_at=controller.format_time(self.clock()),
                pre_launch_abort_receipt=abort_receipt,
                repo_root=repo_root,
                coordination_dir=plane.coordination_dir,
                execution_dir=plane.execution_dir,
                execution_namespace=plane.execution_namespace,
            )
            replayed = controller.release_global_host_session(
                self.host_runtime,
                str(reservation["reservation_id"]),
                execution_id=str(reservation["execution_id"]),
                local_reservation_id=str(reservation["local_reservation_id"]),
                capacity_generation=str(reservation["capacity_generation"]),
                actor="test:dispatcher-rollback-retry",
                reason="crash retry after durable host release",
                released_at=controller.format_time(self.clock()),
                pre_launch_abort_receipt=abort_receipt,
                repo_root=repo_root,
                coordination_dir=plane.coordination_dir,
                execution_dir=plane.execution_dir,
                execution_namespace=plane.execution_namespace,
            )
        self.assertEqual(released, replayed)
        self.assertEqual(
            released["external_cancellation"], "CONFIRMED_NEVER_LAUNCHED"
        )
        rotated = self.publish(
            generation_digit="6",
            epoch=2,
            maximum=1,
            validation_slots=1,
            expires_minutes=10,
            expected_generation=str(first["capacity_generation"]),
        )
        self.assertEqual(rotated["capacity_epoch"], 2)

    def test_pre_launch_abort_api_rejects_forged_empty_cut_after_binding(self) -> None:
        import orchestration

        repo_root = self.base / "forged-pre-launch-repo"
        install_fixture(repo_root)
        ready_runtime(controller, repo_root)
        plane = controller.ControlPlane(repo_root)
        self.publish(
            generation_digit="8",
            epoch=1,
            maximum=1,
            validation_slots=1,
            expires_minutes=10,
            expected_generation=None,
        )
        node_id = "BOOT-000"
        node = plane.node(node_id)
        identity = orchestration.derive_launch_identity(
            execution_id=plane.execution_id,
            execution_namespace=plane.execution_namespace,
            repository=str(plane.repository_identity["repository"]),
            node_id=node_id,
            lifecycle="NODE_DELIVERY",
            authority_class="WRITE_AUTHORIZED",
            branch=str(node["branch"]),
            target_branch=plane.target_branch,
            target_sha=plane.current_target_sha(),
            plan_fingerprint=plane.expected_plan_fingerprint,
        )
        reservation = self.reserve(
            "9",
            repository=str(plane.repository_identity["repository"]),
            execution_id=plane.execution_id,
            resource_key=str(identity["resource_key"]),
        )
        abort_receipt = self.install_dispatch_abort_receipt(
            plane, reservation, node_id=node_id
        )
        with plane.execution_lock(
            "dispatcher-admission.lock", timeout_seconds=120.0
        ):
            orchestration.prepare_launch(
                repo_root,
                str(identity["launch_instruction_id"]),
                "fixture-host",
                execution_id=plane.execution_id,
                execution_namespace=plane.execution_namespace,
                repository=str(plane.repository_identity["repository"]),
                node_id=node_id,
                lifecycle="NODE_DELIVERY",
                branch=str(node["branch"]),
                resource_key=str(identity["resource_key"]),
                target_sha=plane.current_target_sha(),
                plan_fingerprint=plane.expected_plan_fingerprint,
                target_branch=plane.target_branch,
                authority_class="WRITE_AUTHORIZED",
                dispatcher_release_id=str(abort_receipt["release_id"]),
                dispatcher_admission_epoch=int(abort_receipt["admission_epoch"]),
                host_reservation_id=str(reservation["reservation_id"]),
                capacity_host_id=str(reservation["host_id"]),
                capacity_generation=str(reservation["capacity_generation"]),
                capacity_epoch=int(reservation["capacity_epoch"]),
                reservation_expires_at=str(reservation["expires_at"]),
                state_dir=plane.execution_dir,
            )
        with controller.runtime_file_lock(
            self.host_runtime / "locks" / "host-authority.lock"
        ):
            with self.assertRaisesRegex(
                controller.ConfigurationError, "negative activity cut"
            ):
                controller.release_global_host_session(
                    self.host_runtime,
                    str(reservation["reservation_id"]),
                    execution_id=plane.execution_id,
                    local_reservation_id=str(
                        reservation["local_reservation_id"]
                    ),
                    capacity_generation=str(
                        reservation["capacity_generation"]
                    ),
                    actor="test:forged-abort",
                    reason="forged empty receipt after local launch binding",
                    released_at=controller.format_time(self.clock()),
                    pre_launch_abort_receipt=abort_receipt,
                    repo_root=repo_root,
                    coordination_dir=plane.coordination_dir,
                    execution_dir=plane.execution_dir,
                    execution_namespace=plane.execution_namespace,
                )
            with self.assertRaisesRegex(
                controller.ConfigurationError, "authoritative ledger"
            ):
                controller.release_global_host_session(
                    self.host_runtime,
                    str(reservation["reservation_id"]),
                    execution_id=plane.execution_id,
                    local_reservation_id=str(
                        reservation["local_reservation_id"]
                    ),
                    capacity_generation=str(
                        reservation["capacity_generation"]
                    ),
                    actor="test:forged-terminal",
                    reason="shape-only terminal digest must not free capacity",
                    released_at=controller.format_time(self.clock()),
                    local_terminal_event={
                        "event_id": "sha256:" + "f" * 64,
                        "state": "RELEASED",
                        "terminal_state": "SUCCEEDED",
                        "host_event_id": "sha256:" + "e" * 64,
                        "host_reservation_id": reservation["reservation_id"],
                        "capacity_generation": reservation[
                            "capacity_generation"
                        ],
                    },
                    repo_root=repo_root,
                    coordination_dir=plane.coordination_dir,
                    execution_dir=plane.execution_dir,
                    execution_namespace=plane.execution_namespace,
                )


if __name__ == "__main__":
    unittest.main()
