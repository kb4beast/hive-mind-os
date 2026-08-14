from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from hashlib import sha256
from pathlib import Path
from unittest import mock

from fixture_support import copy_autopilot_fixture, ready_runtime

BIN = Path(__file__).resolve().parents[1] / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, BIN / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


controller = _load("controller", "controller.py")
orchestration = _load("orchestration", "orchestration.py")
attended = _load("attended_host_module", "attended_host.py")

NODE = "MISSION-400"
BRANCH = "autopilot/mission-400"


def git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", "-C", str(root)) + arguments,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class AttendedHostTests(unittest.TestCase):
    """The adapter must satisfy host_execution's validators and never block."""

    PRE_READY_TESTS = frozenset(
        {
            "test_explicit_migration_archives_exact_bytes_and_is_retry_idempotent",
            "test_bootstrap_migration_mode_verifies_the_already_held_lock",
            "test_prepared_migration_recovers_after_ledger_replace_crash",
            "test_prepared_migration_restores_a_missing_ledger_from_archives",
            "test_completed_migration_rejects_a_missing_ledger",
            "test_migration_archive_tamper_fails_closed",
            "test_linked_worktree_can_explicitly_migrate_primary_legacy_cards",
            "test_attended_ledger_rejects_adversarial_json_and_schema",
            "test_attended_ledger_requires_digest_identity_and_canonical_card_path",
            "test_migration_rejects_noncanonical_archived_source",
            "test_migration_rejects_duplicate_and_nonfinite_archived_source",
            "test_migration_manifest_rejects_unknown_fields_and_impossible_transition",
            "test_migration_rejects_impossible_legacy_authority_state",
            "test_external_coordination_migration_uses_selected_root",
            "test_pre_ready_adapter_rejects_reuse_after_execution_identity_appears",
        }
    )

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.base = base
        self.root = base / "work"
        self.origin = base / "origin.git"
        self.root.mkdir()
        subprocess.run(
            ("git", "init", "--bare", "--initial-branch=main", str(self.origin)),
            check=True,
            capture_output=True,
        )
        git(self.root, "init", "--initial-branch=main")
        git(self.root, "config", "core.autocrlf", "false")
        git(self.root, "config", "user.name", "Fixture")
        git(self.root, "config", "user.email", "fixture@hive-mind.invalid")
        copy_autopilot_fixture(
            Path(__file__).resolve().parents[1], self.root / ".autopilot"
        )
        control_path = self.root / ".autopilot" / "control-plane.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control["verify_git_objects"] = False
        control_path.write_bytes(
            (
                json.dumps(control, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
            ).encode("utf-8")
        )
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", "fixture base")
        git(self.root, "remote", "add", "origin", str(self.origin))
        git(self.root, "push", "-u", "origin", "main")
        self.target = git(self.root, "rev-parse", "HEAD")
        if self._testMethodName not in self.PRE_READY_TESTS:
            ready_runtime(controller, self.root, actor="test:attended-runtime")
        self.plane = controller.ControlPlane(self.root)
        target = self.plane.control["target"]
        self.repository = str(target["repository"])
        self.launch_target_sha = str(target["baseline_sha"])
        self.launch_plan_fingerprint = str(self.plane.control["plan_fingerprint"])
        self.launch_target_branch = str(target["branch"])
        identity = orchestration.derive_launch_identity(
            execution_id=self.plane.execution_id,
            execution_namespace=self.plane.execution_namespace,
            repository=self.repository,
            node_id=NODE,
            lifecycle="NODE_DELIVERY",
            authority_class="WRITE_AUTHORIZED",
            branch=BRANCH,
            target_branch=self.launch_target_branch,
            target_sha=self.launch_target_sha,
            plan_fingerprint=self.launch_plan_fingerprint,
        )
        self.instruction = str(identity["launch_instruction_id"])
        self.resource = str(identity["resource_key"])
        self.slept: list[float] = []
        self.now = 0.0
        self.host = attended.AttendedCodexHost(
            self.plane,
            wait_seconds=10,
            poll_seconds=5,
            clock=lambda: self.now,
            sleep=self._sleep,
        )
        self.host.bind_tasks(
            [{"launch_instruction_id": self.instruction, "node_id": NODE}]
        )

    def _sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def test_card_adapter_declares_no_autonomous_lifecycle(self) -> None:
        capability = self.host.host_lifecycle_authority(repo_root=self.root)
        self.assertEqual(capability["host_id"], attended.HOST_ID)
        self.assertEqual(capability["source"], "attended-card-only")
        for field in (
            "create",
            "query",
            "resume",
            "interrupt",
            "archive",
            "autonomous_launch",
        ):
            self.assertIs(capability[field], False)
        material = dict(capability)
        record_id = material.pop("record_id")
        self.assertEqual(record_id, attended._mapping_digest(material))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def push_node_head(self, *, email: str) -> str:
        tree = git(self.root, "rev-parse", f"{self.target}^{{tree}}")
        commit = subprocess.run(
            (
                "git",
                "-C",
                str(self.root),
                "-c",
                "user.name=Fixture Identity",
                "-c",
                f"user.email={email}",
                "commit-tree",
                tree,
                "-p",
                self.target,
                "-m",
                "node head",
            ),
            check=True,
            capture_output=True,
            text=True,
            env={
                **__import__("os").environ,
                "GIT_AUTHOR_EMAIL": email,
                "GIT_COMMITTER_EMAIL": email,
            },
        ).stdout.strip()
        git(self.root, "push", "--force", "origin", f"{commit}:refs/heads/{BRANCH}")
        return commit

    def prepare(
        self,
        *,
        instruction: str | None = None,
        resource: str | None = None,
        host: str = "codex",
        authority_class: str = "WRITE_AUTHORIZED",
    ) -> dict:
        instruction_id = instruction or self.instruction
        resource_key = resource or self.resource
        with self.plane.execution_lock("dispatcher-admission.lock"):
            return dict(
                orchestration.prepare_launch(
                    self.root,
                    instruction_id,
                    host,
                    execution_id=self.plane.execution_id,
                    execution_namespace=self.plane.execution_namespace,
                    repository=self.repository,
                    node_id=NODE,
                    lifecycle="NODE_DELIVERY",
                    branch=BRANCH,
                    resource_key=resource_key,
                    target_sha=self.launch_target_sha,
                    plan_fingerprint=self.launch_plan_fingerprint,
                    target_branch=self.launch_target_branch,
                    authority_class=authority_class,
                    dispatcher_release_id=(
                        "sha256:" + "e" * 64
                        if authority_class == "WRITE_AUTHORIZED"
                        else None
                    ),
                    dispatcher_admission_epoch=(
                        1 if authority_class == "WRITE_AUTHORIZED" else None
                    ),
                    host_reservation_id=controller.digest_json(
                        {
                            "kind": "hive-mind-attended-test-host-reservation-v1",
                            "launch_instruction_id": instruction_id,
                        }
                    ),
                    capacity_host_id="test:sealed-host",
                    capacity_generation="sha256:" + "d" * 64,
                    capacity_epoch=1,
                    reservation_expires_at="2099-01-01T00:00:00Z",
                    state_dir=self.plane.execution_dir,
                )
            )

    def fence(self, instruction_id: str, *, actor: str, reason: str) -> dict:
        with self.plane.execution_lock("dispatcher-admission.lock"):
            return dict(
                orchestration.fence_launch(
                    self.root,
                    instruction_id,
                    actor=actor,
                    reason=reason,
                    state_dir=self.plane.execution_dir,
                )
            )

    def create(self) -> dict:
        prepared = self.prepare()
        created = dict(
            self.host.create_thread(
                title=f"Hive Mind {NODE}",
                prompt="rendered node contract",
                idempotency_key=self.instruction,
            )
        )
        with self.plane.execution_lock("dispatcher-admission.lock"):
            orchestration.bind_launch(
                self.root,
                self.instruction,
                "codex",
                str(created["task_id"]),
                host_id=str(created["host_id"]),
                cursor=str(created["cursor"]),
                capability=str(created["capability"]),
                resource_key=self.resource,
                authority_epoch=int(prepared["authority_epoch"]),
                state_dir=self.plane.execution_dir,
            )
        return created

    def write_legacy_ledger(self) -> tuple[bytes, bytes, Path]:
        card = self.root / ".autopilot" / "state" / "host" / "cards" / f"{NODE}.md"
        card.parent.mkdir(parents=True, exist_ok=True)
        card_bytes = b"# Exact legacy card\r\n\r\nkeep these bytes\r\n"
        card.write_bytes(card_bytes)
        legacy = {
            self.instruction: {
                "host_id": attended.HOST_ID,
                "task_id": "attended-" + attended._digest(self.instruction)[:32],
                "cursor": attended.CURSOR,
                "capability": attended.CAPABILITY,
                "capability_digest": "sha256:" + attended._digest(attended.CAPABILITY),
                "node_id": NODE,
                "title": f"Hive Mind {NODE}",
                "card": str(card.relative_to(self.root)),
                "authority_state": "BOUND",
            }
        }
        ledger_bytes = attended._canonical_document(legacy)
        self.host.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.host.ledger_path.write_bytes(ledger_bytes)
        return ledger_bytes, card_bytes, card

    def write_modern_ledger(self) -> dict:
        task_id = "attended-" + attended._digest(self.instruction)[:32]
        card = self.host.cards_dir / f"{task_id}.md"
        card_bytes = b"# Canonical attended card\n"
        self.host._install_immutable_card(card, card_bytes)
        entry = {
            "host_id": attended.HOST_ID,
            "task_id": task_id,
            "cursor": attended.CURSOR,
            "capability": attended.CAPABILITY,
            "capability_digest": "sha256:" + attended._digest(attended.CAPABILITY),
            "node_id": NODE,
            "title": f"Hive Mind {NODE}",
            "card_scope": "runtime_state",
            "card": self.host._canonical_card_path(task_id),
            "card_digest": attended._bytes_digest(card_bytes),
            "prompt_digest": "sha256:" + attended._digest("canonical prompt"),
        }
        self.host.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.host.ledger_path.write_bytes(
            attended._canonical_document({self.instruction: entry})
        )
        return entry

    def migrate_pre_ready_runtime(
        self,
        *,
        actor: str,
        host: attended.AttendedCodexHost | None = None,
    ) -> dict:
        selected = host or self.host
        coordination_dir = selected.coordination_dir
        bootstrap_lock = coordination_dir / controller.RUNTIME_BOOTSTRAP_LOCK
        attended_lock = coordination_dir / "locks" / "attended-host.lock"
        with controller.runtime_file_lock(bootstrap_lock, timeout_seconds=120.0):
            controller.bootstrap_runtime_authority_migration(
                selected.repo_root,
                coordination_dir,
                actor=actor,
            )
            controller.stage_repository_runtime_authority(
                selected.repo_root,
                coordination_dir,
            )
            with controller.runtime_file_lock(attended_lock, timeout_seconds=120.0):
                return dict(
                    selected.migrate_legacy_ledger(
                        actor=actor,
                        already_holds_runtime_lock=True,
                    )
                )

    def leave_prepared_migration(self, *, actor: str) -> dict:
        original = self.host._atomic_write_bytes

        def fail_ledger_replace(path: Path, value: bytes) -> None:
            if Path(path) == self.host.ledger_path:
                raise OSError("simulated crash before ledger replace")
            original(path, value)

        with mock.patch.object(
            self.host,
            "_atomic_write_bytes",
            side_effect=fail_ledger_replace,
        ):
            with self.assertRaisesRegex(OSError, "simulated crash"):
                self.migrate_pre_ready_runtime(actor=actor)
        manifest_path = (
            self.plane.coordination_dir
            / "migrations"
            / "attended-host-v1"
            / "manifest.json"
        )
        prepared = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(prepared["status"], "PREPARED")
        return prepared

    @staticmethod
    def wait_target(created: dict, after: str | None = None) -> dict:
        return {
            "host_id": created["host_id"],
            "task_id": created["task_id"],
            "cursor": created["cursor"],
            "capability": created["capability"],
            "after_event_cursor": after,
        }

    def test_creation_matches_the_host_binding_contract(self) -> None:
        created = self.create()
        self.assertEqual(
            set(created),
            {
                "kind",
                "host_id",
                "task_id",
                "cursor",
                "capability",
                "idempotency_key",
            },
        )
        self.assertEqual(created["kind"], attended.CREATE_KIND)
        self.assertEqual(created["idempotency_key"], self.instruction)
        card = self.host.cards_dir / f"{created['task_id']}.md"
        self.assertIn("rendered node contract", card.read_text(encoding="utf-8"))

    def test_preparation_only_task_is_rejected_before_attended_binding(self) -> None:
        with self.assertRaisesRegex(
            attended.AttendedHostError, "cannot bind an unobservable preparation-only"
        ):
            self.host.bind_tasks(
                [
                    {
                        "launch_instruction_id": self.instruction,
                        "node_id": NODE,
                        "authority_class": "PREPARATION_ONLY",
                    }
                ]
            )
        self.assertFalse(self.host.ledger_path.exists())

    def test_existing_preparation_card_is_not_presented_as_pending(self) -> None:
        preparation = orchestration.derive_launch_identity(
            execution_id=self.plane.execution_id,
            execution_namespace=self.plane.execution_namespace,
            repository=self.repository,
            node_id=NODE,
            lifecycle="NODE_DELIVERY",
            authority_class="PREPARATION_ONLY",
            branch=BRANCH,
            target_branch=self.launch_target_branch,
            target_sha=self.launch_target_sha,
            plan_fingerprint=self.launch_plan_fingerprint,
        )
        instruction = str(preparation["launch_instruction_id"])
        self.host.bind_tasks([{"launch_instruction_id": instruction, "node_id": NODE}])
        self.prepare(
            instruction=instruction,
            resource=str(preparation["resource_key"]),
            host="legacy-attended",
            authority_class="PREPARATION_ONLY",
        )
        # Simulate a card preserved from a pre-fix attended deployment.  The
        # immutable registry remains evidence, but it is no longer actionable.
        task_id = "attended-" + attended._digest(instruction)[:32]
        card = self.host.cards_dir / f"{task_id}.md"
        card_text = "# historical read-only preparation\n"
        self.host._install_immutable_card(card, card_text.encode("utf-8"))
        with self.plane.runtime_lock("attended-host.lock"):
            self.host._write_ledger_unlocked(
                {
                    instruction: {
                        "host_id": attended.HOST_ID,
                        "task_id": task_id,
                        "cursor": attended.CURSOR,
                        "capability": attended.CAPABILITY,
                        "capability_digest": "sha256:"
                        + attended._digest(attended.CAPABILITY),
                        "node_id": NODE,
                        "title": "Historical preparation",
                        "card_scope": "runtime_state",
                        "card": card.relative_to(self.plane.execution_dir).as_posix(),
                        "card_digest": attended._bytes_digest(
                            card_text.encode("utf-8")
                        ),
                        "prompt_digest": "sha256:"
                        + attended._digest("historical prompt"),
                    }
                }
            )

        self.assertEqual(self.host.pending_cards(), ())

    def test_lookup_enables_crash_safe_adoption(self) -> None:
        created = self.create()
        persisted = self.host.lookup_thread(idempotency_key=self.instruction)
        assert persisted is not None
        self.assertEqual(persisted, created)

    def test_runtime_authority_rejects_corrupt_validation_lease(self) -> None:
        self.plane.validation_lease_path.parent.mkdir(parents=True, exist_ok=True)
        self.plane.validation_lease_path.write_text("{not-json", encoding="utf-8")
        with self.assertRaisesRegex(controller.ConfigurationError, "cannot parse JSON"):
            self.host.inspect_runtime_authority(repo_root=self.root)

    def test_runtime_authority_lease_read_holds_the_validation_lock(self) -> None:
        lease = self.plane.acquire_global_validation_lease_internal(
            NODE,
            "test:attended-inspection",
        )
        entered_read = threading.Event()
        permit_read = threading.Event()
        competing_lock_acquired = threading.Event()
        failures: list[BaseException] = []
        result: list[dict] = []
        original_read = attended.read_json

        def held_read(path: Path) -> object:
            value = original_read(path)
            entered_read.set()
            if not permit_read.wait(5):
                raise TimeoutError("test did not release validation lease read")
            return value

        def inspect() -> None:
            try:
                result.append(
                    dict(self.host.inspect_runtime_authority(repo_root=self.root))
                )
            except BaseException as error:
                failures.append(error)

        def take_competing_lock() -> None:
            try:
                with self.plane.runtime_lock("global-validation-lease.lock"):
                    competing_lock_acquired.set()
            except BaseException as error:
                failures.append(error)

        try:
            with mock.patch.object(attended, "read_json", side_effect=held_read):
                inspection = threading.Thread(target=inspect)
                inspection.start()
                self.assertTrue(entered_read.wait(5))
                competitor = threading.Thread(target=take_competing_lock)
                competitor.start()
                try:
                    self.assertFalse(competing_lock_acquired.wait(0.2))
                finally:
                    permit_read.set()
                inspection.join(5)
                competitor.join(5)
            self.assertEqual(failures, [])
            self.assertEqual(result[0]["active_validation_lease"], lease)
            self.assertFalse(result[0]["quiescent"])
            self.assertTrue(competing_lock_acquired.is_set())
        finally:
            self.plane.release_global_validation_lease_internal(
                NODE,
                "test:attended-inspection",
                lease_id=str(lease["lease_id"]),
            )

    def test_receipt_commit_is_the_only_success_evidence(self) -> None:
        created = self.create()
        self.push_node_head(email=attended.RECEIPT_IDENTITY)
        events = self.host.wait_threads([self.wait_target(created)])
        self.assertEqual([event["state"] for event in events], ["SUCCEEDED"])
        self.assertEqual(
            set(events[0]),
            {
                "kind",
                "host_id",
                "task_id",
                "cursor",
                "capability",
                "state",
                "event_id",
                "event_cursor",
            },
        )

    def test_pushed_work_without_a_receipt_is_active(self) -> None:
        created = self.create()
        head = self.push_node_head(email="worker@example.invalid")
        events = self.host.wait_threads([self.wait_target(created)])
        self.assertEqual([event["state"] for event in events], ["ACTIVE"])
        self.assertEqual(events[0]["event_cursor"], head)

    def test_unchanged_evidence_emits_no_repeat_event(self) -> None:
        created = self.create()
        head = self.push_node_head(email="worker@example.invalid")
        events = self.host.wait_threads([self.wait_target(created, head)])
        self.assertEqual(events, ())

    def test_silence_returns_within_the_deadline(self) -> None:
        created = self.create()
        events = self.host.wait_threads([self.wait_target(created)])
        self.assertEqual(events, ())
        self.assertLessEqual(self.now, 10)
        self.assertTrue(self.slept, "a silent wait must poll, not spin")

    def test_recorded_blocker_is_terminal_failure(self) -> None:
        created = self.create()
        blocker = self.plane.record_blocker(
            NODE,
            cause="fixture terminal blocker",
            fix="repair the fixture cause",
            retry_when="the repair has been verified",
            category="test",
        )
        events = self.host.wait_threads([self.wait_target(created)])
        self.assertEqual([event["state"] for event in events], ["FAILED"])
        blocker_line = json.dumps(
            blocker,
            ensure_ascii=False,
            sort_keys=True,
        )
        self.assertEqual(
            events[0]["event_cursor"],
            "blocker:" + attended._digest(blocker_line)[:32],
        )

    def test_relay_message_is_acknowledged_and_written(self) -> None:
        created = self.create()
        ack = self.host.send_message_to_thread(
            host_id=created["host_id"],
            task_id=created["task_id"],
            cursor=created["cursor"],
            capability=created["capability"],
            message="continue; report BLOCKS",
            idempotency_key="relay-1",
        )
        self.assertTrue(ack["accepted"])
        self.assertEqual(
            set(ack),
            {
                "kind",
                "host_id",
                "task_id",
                "cursor",
                "capability",
                "accepted",
                "message_id",
                "idempotency_key",
            },
        )
        relay = self.host.cards_dir / f"{created['task_id']}.relay.md"
        self.assertTrue(relay.is_relative_to(self.plane.execution_dir))
        legacy_relay = (
            self.plane.coordination_dir
            / "host"
            / "cards"
            / f"{created['task_id']}.relay.md"
        )
        self.assertFalse(legacy_relay.exists())
        self.assertIn("continue; report BLOCKS", relay.read_text(encoding="utf-8"))

    def test_card_and_create_identity_are_immutable(self) -> None:
        created = self.create()
        with self.assertRaisesRegex(attended.AttendedHostError, "launch identity"):
            self.host.create_thread(
                title=f"Hive Mind {NODE}",
                prompt="different rendered contract",
                idempotency_key=self.instruction,
            )
        card = self.host.cards_dir / f"{created['task_id']}.md"
        card.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(attended.AttendedHostError, "integrity digest"):
            self.host.lookup_thread(idempotency_key=self.instruction)

    def test_immutable_card_failure_before_publication_leaves_no_final_bytes(
        self,
    ) -> None:
        card = self.host.cards_dir / "crash-safe-card.md"
        value = b"complete immutable session card\n"
        with mock.patch.object(
            attended.os,
            "link",
            side_effect=OSError("simulated crash before immutable publication"),
        ):
            with self.assertRaisesRegex(OSError, "simulated crash"):
                self.host._install_immutable_card(card, value)

        self.assertFalse(card.exists())
        self.assertEqual(
            tuple(card.parent.glob(f".{card.name}.*.tmp")),
            (),
            "a failed private write must not strand a final or temporary authority file",
        )

    def test_immutable_card_preserves_an_unverified_incumbent(self) -> None:
        card = self.host.cards_dir / "partial-incumbent.md"
        card.parent.mkdir(parents=True, exist_ok=True)
        partial = b"partial crash-leftover bytes"
        card.write_bytes(partial)

        with self.assertRaisesRegex(attended.AttendedHostError, "conflicts"):
            self.host._install_immutable_card(card, b"complete expected bytes")

        self.assertEqual(card.read_bytes(), partial)

    def test_immutable_card_concurrent_publish_never_replaces_the_winner(self) -> None:
        card = self.host.cards_dir / "concurrent-card.md"
        first = b"first complete immutable card"
        second = b"second complete immutable card"
        barrier = threading.Barrier(2)
        successes: list[bytes] = []
        failures: list[BaseException] = []

        def publish(value: bytes) -> None:
            try:
                barrier.wait(timeout=5)
                self.host._install_immutable_card(card, value)
                successes.append(value)
            except BaseException as error:
                failures.append(error)

        first_thread = threading.Thread(target=publish, args=(first,))
        second_thread = threading.Thread(target=publish, args=(second,))
        first_thread.start()
        second_thread.start()
        first_thread.join(timeout=5)
        second_thread.join(timeout=5)

        self.assertFalse(first_thread.is_alive())
        self.assertFalse(second_thread.is_alive())
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], attended.AttendedHostError)
        self.assertIn("conflicts", str(failures[0]))
        self.assertEqual(card.read_bytes(), successes[0])

    def test_atomic_registry_writes_sync_the_parent_directory(self) -> None:
        text_target = self.host.host_dir / "atomic-text.json"
        bytes_target = self.host.host_dir / "atomic-bytes.json"
        with mock.patch.object(
            attended.AttendedCodexHost,
            "_fsync_directory",
        ) as sync_parent:
            self.host._atomic_write(text_target, '{"durable":true}\n')
            self.host._atomic_write_bytes(bytes_target, b"durable bytes\n")

        self.assertEqual(text_target.read_text(encoding="utf-8"), '{"durable":true}\n')
        self.assertEqual(bytes_target.read_bytes(), b"durable bytes\n")
        self.assertEqual(
            sync_parent.call_args_list,
            [mock.call(text_target.parent), mock.call(bytes_target.parent)],
        )

    def test_atomic_write_does_not_acknowledge_an_unsynced_parent_directory(
        self,
    ) -> None:
        target = self.host.host_dir / "unsynced-parent.json"
        with mock.patch.object(
            attended.AttendedCodexHost,
            "_fsync_directory",
            side_effect=OSError("simulated parent directory sync failure"),
        ):
            with self.assertRaisesRegex(OSError, "parent directory sync failure"):
                self.host._atomic_write_bytes(target, b"complete replacement bytes")

        # ``replace`` already made the fully written temp file visible, but the
        # caller received an error and cannot claim durable publication.
        self.assertEqual(target.read_bytes(), b"complete replacement bytes")
        self.assertEqual(tuple(target.parent.glob(f"{target.name}.*")), ())

    def test_attended_ledger_rejects_adversarial_json_and_schema(self) -> None:
        entry = self.write_modern_ledger()
        duplicate = f'{{"{self.instruction}":{{}},"{self.instruction}":{{}}}}\n'.encode(
            "utf-8"
        )
        nonfinite = b'{"untrusted":NaN}\n'
        noncanonical = json.dumps(
            {self.instruction: entry},
            ensure_ascii=True,
            sort_keys=True,
        ).encode("utf-8")
        unexpected_entry = {**entry, "untrusted": True}
        unexpected = attended._canonical_document({self.instruction: unexpected_entry})
        cases = (
            ("duplicate", duplicate, "duplicate JSON key"),
            ("nonfinite", nonfinite, "non-finite JSON"),
            ("noncanonical", noncanonical, "noncanonical JSON encoding"),
            ("unexpected", unexpected, "exact supported schema"),
        )

        for label, encoded, message in cases:
            with self.subTest(label=label):
                self.host.ledger_path.write_bytes(encoded)
                with self.assertRaisesRegex(attended.AttendedHostError, message):
                    self.host._ledger_unlocked()

    def test_attended_ledger_requires_digest_identity_and_canonical_card_path(
        self,
    ) -> None:
        entry = self.write_modern_ledger()
        with self.assertRaisesRegex(attended.AttendedHostError, "sha256 identity"):
            self.host.create_thread(
                title="invalid identity",
                prompt="must never write a card",
                idempotency_key="sha256:not-a-digest",
            )

        self.host.ledger_path.write_bytes(
            attended._canonical_document({"not-a-digest": entry})
        )
        with self.assertRaisesRegex(
            attended.AttendedHostError, "launch instruction identity"
        ):
            self.host._ledger_unlocked()

        noncanonical_entry = {
            **entry,
            "card": str(entry["card"]).replace("/", "\\"),
        }
        self.host.ledger_path.write_bytes(
            attended._canonical_document({self.instruction: noncanonical_entry})
        )
        with self.assertRaisesRegex(attended.AttendedHostError, "path is noncanonical"):
            self.host._ledger_unlocked()

    def test_migration_rejects_noncanonical_archived_source(self) -> None:
        self.write_legacy_ledger()
        prepared = self.leave_prepared_migration(actor="curator:archive-canonical-test")
        source = self.plane.coordination_dir / str(prepared["source_archive"])
        source_value = json.loads(source.read_text(encoding="utf-8"))
        noncanonical = json.dumps(
            source_value,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        source_digest = attended._bytes_digest(noncanonical)
        source = (
            self.plane.coordination_dir
            / "migrations"
            / "attended-host-v1"
            / "ledgers"
            / f"{source_digest[7:]}.json"
        )
        source.write_bytes(noncanonical)
        prepared["source_ledger_digest"] = source_digest
        prepared["source_ledger_bytes"] = len(noncanonical)
        prepared["source_archive"] = source.relative_to(
            self.plane.coordination_dir
        ).as_posix()
        manifest_path = (
            self.plane.coordination_dir
            / "migrations"
            / "attended-host-v1"
            / "manifest.json"
        )
        manifest_path.write_bytes(attended._canonical_document(prepared))

        with self.assertRaisesRegex(attended.AttendedHostError, "noncanonical JSON"):
            self.migrate_pre_ready_runtime(actor="curator:archive-canonical-test")

    def test_migration_rejects_duplicate_and_nonfinite_archived_source(self) -> None:
        self.write_legacy_ledger()
        prepared = self.leave_prepared_migration(actor="curator:archive-json-test")
        manifest_path = (
            self.plane.coordination_dir
            / "migrations"
            / "attended-host-v1"
            / "manifest.json"
        )
        duplicate = f'{{"{self.instruction}":{{}},"{self.instruction}":{{}}}}\n'.encode(
            "utf-8"
        )
        cases = (
            ("duplicate", duplicate, "duplicate JSON key"),
            ("nonfinite", b'{"untrusted":NaN}\n', "non-finite JSON"),
        )

        for label, source_bytes, message in cases:
            with self.subTest(label=label):
                source_digest = attended._bytes_digest(source_bytes)
                source = (
                    self.plane.coordination_dir
                    / "migrations"
                    / "attended-host-v1"
                    / "ledgers"
                    / f"{source_digest[7:]}.json"
                )
                source.write_bytes(source_bytes)
                manifest_path.write_bytes(
                    attended._canonical_document(
                        {
                            **prepared,
                            "source_ledger_digest": source_digest,
                            "source_ledger_bytes": len(source_bytes),
                            "source_archive": source.relative_to(
                                self.plane.coordination_dir
                            ).as_posix(),
                        }
                    )
                )
                with self.assertRaisesRegex(attended.AttendedHostError, message):
                    self.migrate_pre_ready_runtime(actor="curator:archive-json-test")

    def test_migration_manifest_rejects_unknown_fields_and_impossible_transition(
        self,
    ) -> None:
        self.write_legacy_ledger()
        prepared = self.leave_prepared_migration(actor="curator:manifest-schema-test")
        manifest_path = (
            self.plane.coordination_dir
            / "migrations"
            / "attended-host-v1"
            / "manifest.json"
        )

        manifest_path.write_bytes(
            attended._canonical_document({**prepared, "unexpected": "field"})
        )
        with self.assertRaisesRegex(attended.AttendedHostError, "exact schema"):
            self.migrate_pre_ready_runtime(actor="curator:manifest-schema-test")

        impossible_complete = {
            **prepared,
            "status": "COMPLETE",
            "prepared_manifest_digest": "sha256:" + "0" * 64,
        }
        manifest_path.write_bytes(attended._canonical_document(impossible_complete))
        with self.assertRaisesRegex(
            attended.AttendedHostError, "impossible completion"
        ):
            self.migrate_pre_ready_runtime(actor="curator:manifest-schema-test")

    def test_migration_rejects_impossible_legacy_authority_state(self) -> None:
        self.write_legacy_ledger()
        legacy = json.loads(self.host.ledger_path.read_text(encoding="utf-8"))
        legacy[self.instruction]["authority_state"] = "RELEASED"
        self.host.ledger_path.write_bytes(attended._canonical_document(legacy))

        with self.assertRaisesRegex(attended.AttendedHostError, "authority state"):
            self.migrate_pre_ready_runtime(actor="curator:authority-transition-test")

    def test_registry_create_is_linearized_before_a_concurrent_fence(self) -> None:
        self.prepare()
        entered_write = threading.Event()
        permit_write = threading.Event()
        create_done = threading.Event()
        fence_done = threading.Event()
        failures: list[BaseException] = []
        original_write = self.host._write_ledger_unlocked

        def held_write(value: dict) -> None:
            entered_write.set()
            if not permit_write.wait(5):
                raise TimeoutError("test did not release attended registry write")
            original_write(value)

        def create_card() -> None:
            try:
                self.host.create_thread(
                    title=f"Hive Mind {NODE}",
                    prompt="rendered node contract",
                    idempotency_key=self.instruction,
                )
            except BaseException as error:
                failures.append(error)
            finally:
                create_done.set()

        def fence() -> None:
            try:
                self.fence(
                    self.instruction,
                    actor="curator:concurrent-create-fence",
                    reason="prove registry create and fence serialization",
                )
            except BaseException as error:
                failures.append(error)
            finally:
                fence_done.set()

        with mock.patch.object(
            self.host,
            "_write_ledger_unlocked",
            side_effect=held_write,
        ):
            create_thread = threading.Thread(target=create_card)
            create_thread.start()
            self.assertTrue(entered_write.wait(5))
            fence_thread = threading.Thread(target=fence)
            fence_thread.start()
            try:
                self.assertFalse(
                    fence_done.wait(0.2),
                    "fence must wait until the authority-guarded registry write completes",
                )
            finally:
                permit_write.set()
            self.assertTrue(create_done.wait(5))
            self.assertTrue(fence_done.wait(5))
            create_thread.join()
            fence_thread.join()
        self.assertEqual(failures, [])
        self.assertIn(self.instruction, self.host._ledger())
        self.assertEqual(self.host.pending_cards(), ())

    def test_fenced_binding_hides_card_and_rejects_relay_and_wait(self) -> None:
        created = self.create()
        self.assertEqual(len(self.host.pending_cards()), 1)
        self.fence(
            self.instruction,
            actor="curator:test",
            reason="exercise stale attended authority",
        )
        self.assertEqual(self.host.pending_cards(), ())
        self.assertIsNone(self.host.lookup_thread(idempotency_key=self.instruction))
        with self.assertRaisesRegex(attended.AttendedHostError, "stale or revoked"):
            self.host.send_message_to_thread(
                host_id=str(created["host_id"]),
                task_id=str(created["task_id"]),
                cursor=str(created["cursor"]),
                capability=str(created["capability"]),
                message="continue",
                idempotency_key="fenced-relay",
            )
        with self.assertRaisesRegex(attended.AttendedHostError, "stale or revoked"):
            self.host.wait_threads([self.wait_target(created)])

    def test_relay_is_idempotent_and_conflicting_replay_fails(self) -> None:
        created = self.create()
        arguments = {
            "host_id": str(created["host_id"]),
            "task_id": str(created["task_id"]),
            "cursor": str(created["cursor"]),
            "capability": str(created["capability"]),
            "message": "first relay",
            "idempotency_key": "same-relay",
        }
        first = self.host.send_message_to_thread(**arguments)
        second = self.host.send_message_to_thread(**arguments)
        self.assertEqual(first, second)
        with self.assertRaisesRegex(attended.AttendedHostError, "conflicts"):
            self.host.send_message_to_thread(
                **{**arguments, "message": "changed relay"}
            )

    def test_relay_write_is_linearized_before_a_concurrent_fence(self) -> None:
        created = self.create()
        entered_write = threading.Event()
        permit_write = threading.Event()
        relay_done = threading.Event()
        fence_done = threading.Event()
        failures: list[BaseException] = []
        original_write = self.host._atomic_write

        def held_write(path: Path, text: str) -> None:
            if Path(path).name == f"{created['task_id']}.relay.md":
                entered_write.set()
                if not permit_write.wait(5):
                    raise TimeoutError("test did not release attended relay write")
            original_write(path, text)

        def relay() -> None:
            try:
                self.host.send_message_to_thread(
                    host_id=str(created["host_id"]),
                    task_id=str(created["task_id"]),
                    cursor=str(created["cursor"]),
                    capability=str(created["capability"]),
                    message="linearized relay",
                    idempotency_key="linearized-relay",
                )
            except BaseException as error:
                failures.append(error)
            finally:
                relay_done.set()

        def fence() -> None:
            try:
                self.fence(
                    self.instruction,
                    actor="curator:concurrent-fence",
                    reason="prove relay and fence serialization",
                )
            except BaseException as error:
                failures.append(error)
            finally:
                fence_done.set()

        with mock.patch.object(self.host, "_atomic_write", side_effect=held_write):
            relay_thread = threading.Thread(target=relay)
            relay_thread.start()
            self.assertTrue(entered_write.wait(5))
            fence_thread = threading.Thread(target=fence)
            fence_thread.start()
            try:
                self.assertFalse(
                    fence_done.wait(0.2),
                    "fence must wait until the authority-guarded relay write completes",
                )
            finally:
                permit_write.set()
            self.assertTrue(relay_done.wait(5))
            self.assertTrue(fence_done.wait(5))
            relay_thread.join()
            fence_thread.join()
        self.assertEqual(failures, [])
        self.assertEqual(self.host.pending_cards(), ())

    def test_explicit_migration_archives_exact_bytes_and_is_retry_idempotent(
        self,
    ) -> None:
        ledger_bytes, card_bytes, legacy_card = self.write_legacy_ledger()
        result = self.migrate_pre_ready_runtime(actor="curator:migration-test")
        self.assertEqual(result["status"], "COMPLETE")
        source_archive = self.plane.coordination_dir / str(result["source_archive"])
        self.assertEqual(source_archive.read_bytes(), ledger_bytes)
        card_archive = self.plane.coordination_dir / str(result["cards"][0]["archive"])
        self.assertEqual(card_archive.read_bytes(), card_bytes)
        normalized = json.loads(self.host.ledger_path.read_text(encoding="utf-8"))
        entry = normalized[self.instruction]
        self.assertNotIn("authority_state", entry)
        self.assertEqual(entry["card_scope"], "runtime_state")
        self.assertEqual(
            entry["card_digest"], "sha256:" + sha256(card_bytes).hexdigest()
        )
        immutable = self.plane.coordination_dir / entry["card"]
        self.assertEqual(immutable.name, f"{entry['task_id']}.md")
        self.assertEqual(immutable.read_bytes(), card_bytes)
        self.assertEqual(legacy_card.read_bytes(), card_bytes)
        self.assertEqual(
            self.migrate_pre_ready_runtime(actor="curator:migration-test"),
            result,
        )

    def test_bootstrap_migration_mode_verifies_the_already_held_lock(self) -> None:
        self.write_legacy_ledger()
        with self.assertRaisesRegex(
            controller.ConfigurationError,
            "runtime authority",
        ):
            self.host.migrate_legacy_ledger(actor="curator:pre-ready-test")
        with self.assertRaisesRegex(
            attended.AttendedHostError,
            "bootstrap and attended runtime locks",
        ):
            self.host.migrate_legacy_ledger(
                actor="curator:bootstrap-lock-test",
                already_holds_runtime_lock=True,
            )
        completed = self.migrate_pre_ready_runtime(actor="curator:bootstrap-lock-test")
        self.assertEqual(completed["status"], "COMPLETE")

    def test_prepared_migration_recovers_after_ledger_replace_crash(self) -> None:
        ledger_bytes, _, _ = self.write_legacy_ledger()
        self.leave_prepared_migration(actor="curator:crash-test")
        self.assertEqual(self.host.ledger_path.read_bytes(), ledger_bytes)
        completed = self.migrate_pre_ready_runtime(actor="curator:crash-test")
        self.assertEqual(completed["status"], "COMPLETE")
        self.assertIn(
            self.instruction,
            json.loads(self.host.ledger_path.read_text(encoding="utf-8")),
        )

    def test_prepared_migration_restores_a_missing_ledger_from_archives(self) -> None:
        self.write_legacy_ledger()
        prepared = self.leave_prepared_migration(actor="curator:missing-ledger-test")
        self.host.ledger_path.unlink()
        normalized_card = self.plane.coordination_dir / str(
            prepared["cards"][0]["normalized_card"]
        )
        normalized_card.unlink()

        completed = self.migrate_pre_ready_runtime(actor="curator:missing-ledger-test")

        self.assertEqual(completed["status"], "COMPLETE")
        restored = json.loads(self.host.ledger_path.read_text(encoding="utf-8"))
        self.assertIn(self.instruction, restored)
        archived_card = self.plane.coordination_dir / str(
            completed["cards"][0]["archive"]
        )
        self.assertEqual(normalized_card.read_bytes(), archived_card.read_bytes())

    def test_completed_migration_rejects_a_missing_ledger(self) -> None:
        self.write_legacy_ledger()
        completed = self.migrate_pre_ready_runtime(
            actor="curator:completed-missing-ledger-test"
        )
        self.assertEqual(completed["status"], "COMPLETE")
        self.host.ledger_path.unlink()
        with self.assertRaisesRegex(
            attended.AttendedHostError,
            "completed attended ledger is missing",
        ):
            self.migrate_pre_ready_runtime(
                actor="curator:completed-missing-ledger-test"
            )

    def test_migration_archive_tamper_fails_closed(self) -> None:
        self.write_legacy_ledger()
        result = self.migrate_pre_ready_runtime(actor="curator:tamper-test")
        archive = self.plane.coordination_dir / str(result["cards"][0]["archive"])
        archive.write_bytes(b"tampered archive")
        with self.assertRaisesRegex(
            attended.AttendedHostError, "archive failed integrity"
        ):
            self.migrate_pre_ready_runtime(actor="curator:tamper-test")

    def test_linked_worktree_adopts_the_same_registry_and_card(self) -> None:
        created = self.create()
        secondary = self.base / "secondary"
        git(self.root, "worktree", "add", "-b", "fixture-secondary", str(secondary))
        try:
            secondary_plane = controller.ControlPlane(secondary)
            secondary_host = attended.AttendedCodexHost(secondary_plane)
            self.assertEqual(
                secondary_plane.coordination_dir,
                self.plane.coordination_dir,
            )
            self.assertEqual(
                secondary_host.lookup_thread(idempotency_key=self.instruction),
                created,
            )
            self.assertEqual(len(secondary_host.pending_cards()), 1)
        finally:
            git(self.root, "worktree", "remove", "--force", str(secondary))

    def test_linked_worktree_can_explicitly_migrate_primary_legacy_cards(self) -> None:
        ledger_bytes, card_bytes, _ = self.write_legacy_ledger()
        secondary = self.base / "secondary-migration"
        git(self.root, "worktree", "add", "-b", "fixture-migration", str(secondary))
        try:
            secondary_plane = controller.ControlPlane(secondary)
            secondary_host = attended.AttendedCodexHost(secondary_plane)
            result = self.migrate_pre_ready_runtime(
                actor="curator:linked-migration-test",
                host=secondary_host,
            )
            self.assertEqual(result["status"], "COMPLETE")
            self.assertEqual(
                (
                    secondary_plane.coordination_dir / str(result["source_archive"])
                ).read_bytes(),
                ledger_bytes,
            )
            normalized = json.loads(
                secondary_host.ledger_path.read_text(encoding="utf-8")
            )[self.instruction]
            self.assertEqual(
                (
                    secondary_plane.coordination_dir / str(normalized["card"])
                ).read_bytes(),
                card_bytes,
            )
        finally:
            git(self.root, "worktree", "remove", "--force", str(secondary))

    def test_external_coordination_migration_uses_selected_root(self) -> None:
        ledger_bytes, _, _ = self.write_legacy_ledger()
        external = self.base / "external-runtime"
        external_plane = controller.ControlPlane(self.root, state_dir=external)
        external_host = attended.AttendedCodexHost(external_plane)
        external_host.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        external_host.ledger_path.write_bytes(ledger_bytes)
        self.host.ledger_path.unlink()

        self.assertEqual(external_host.coordination_dir, external.resolve())
        self.assertEqual(external_host.authority_dir, external.resolve())
        result = self.migrate_pre_ready_runtime(
            actor="curator:external-state-migration",
            host=external_host,
        )

        self.assertEqual(result["status"], "COMPLETE")
        self.assertTrue(external_host.ledger_path.is_file())
        self.assertFalse(
            (self.plane.coordination_dir / "migrations" / "attended-host-v1").exists()
        )

    def test_sibling_execution_namespaces_do_not_share_attended_authority(
        self,
    ) -> None:
        created = self.create()
        sibling_pending = controller.ControlPlane(
            self.root,
            execution_namespace="sibling",
        )
        with self.plane.arbiter_lock(timeout_seconds=120.0):
            controller.initialize_execution_namespace(
                self.plane.coordination_dir,
                sibling_pending.execution_identity,
            )
        sibling_plane = controller.ControlPlane(
            self.root,
            execution_namespace="sibling",
        )
        sibling_identity = orchestration.derive_launch_identity(
            execution_id=sibling_plane.execution_id,
            execution_namespace=sibling_plane.execution_namespace,
            repository=self.repository,
            node_id=NODE,
            lifecycle="NODE_DELIVERY",
            authority_class="WRITE_AUTHORIZED",
            branch=BRANCH,
            target_branch=self.launch_target_branch,
            target_sha=self.launch_target_sha,
            plan_fingerprint=self.launch_plan_fingerprint,
        )
        sibling_instruction = str(sibling_identity["launch_instruction_id"])
        sibling_resource = str(sibling_identity["resource_key"])
        self.assertNotEqual(sibling_instruction, self.instruction)
        self.assertEqual(sibling_resource, self.resource)

        sibling_host = attended.AttendedCodexHost(
            sibling_plane,
            wait_seconds=10,
            poll_seconds=5,
            clock=lambda: self.now,
            sleep=self._sleep,
        )
        sibling_host.bind_tasks(
            [{"launch_instruction_id": sibling_instruction, "node_id": NODE}]
        )
        self.assertIsNone(sibling_host.lookup_thread(idempotency_key=self.instruction))
        with sibling_plane.execution_lock("dispatcher-admission.lock"):
            prepared = orchestration.prepare_launch(
                self.root,
                sibling_instruction,
                "codex",
                execution_id=sibling_plane.execution_id,
                execution_namespace=sibling_plane.execution_namespace,
                repository=self.repository,
                node_id=NODE,
                lifecycle="NODE_DELIVERY",
                branch=BRANCH,
                resource_key=sibling_resource,
                target_sha=self.launch_target_sha,
                plan_fingerprint=self.launch_plan_fingerprint,
                target_branch=self.launch_target_branch,
                authority_class="WRITE_AUTHORIZED",
                dispatcher_release_id="sha256:" + "c" * 64,
                dispatcher_admission_epoch=1,
                host_reservation_id=controller.digest_json(
                    {
                        "kind": "hive-mind-attended-test-host-reservation-v1",
                        "launch_instruction_id": sibling_instruction,
                    }
                ),
                capacity_host_id="test:sealed-host",
                capacity_generation="sha256:" + "d" * 64,
                capacity_epoch=1,
                reservation_expires_at="2099-01-01T00:00:00Z",
                state_dir=sibling_plane.execution_dir,
            )
        sibling_created = dict(
            sibling_host.create_thread(
                title=f"Hive Mind {NODE}",
                prompt="rendered sibling node contract",
                idempotency_key=sibling_instruction,
            )
        )
        with sibling_plane.execution_lock("dispatcher-admission.lock"):
            orchestration.bind_launch(
                self.root,
                sibling_instruction,
                "codex",
                str(sibling_created["task_id"]),
                host_id=str(sibling_created["host_id"]),
                cursor=str(sibling_created["cursor"]),
                capability=str(sibling_created["capability"]),
                resource_key=sibling_resource,
                authority_epoch=int(prepared["authority_epoch"]),
                state_dir=sibling_plane.execution_dir,
            )

        self.assertNotEqual(sibling_created["task_id"], created["task_id"])
        self.assertIsNone(self.host.lookup_thread(idempotency_key=sibling_instruction))
        self.assertTrue(
            sibling_host.ledger_path.is_relative_to(sibling_plane.execution_dir)
        )
        self.assertTrue(self.host.ledger_path.is_relative_to(self.plane.execution_dir))
        self.assertNotEqual(sibling_host.ledger_path, self.host.ledger_path)
        self.assertFalse((self.plane.coordination_dir / "host" / "cards").exists())

    def test_pre_ready_adapter_rejects_reuse_after_execution_identity_appears(
        self,
    ) -> None:
        self.assertEqual(self.host.authority_dir, self.plane.coordination_dir)
        execution_identity = self.plane.execution_dir / "execution-identity.json"
        execution_identity.parent.mkdir(parents=True, exist_ok=True)
        execution_identity.write_bytes(b"{}\n")
        legacy_ledger = self.host.ledger_path
        before = legacy_ledger.read_bytes() if legacy_ledger.exists() else None

        with self.assertRaisesRegex(
            attended.AttendedHostError,
            "authority phase changed; construct a fresh adapter",
        ):
            self.host.create_thread(
                title="must not escape legacy authority",
                prompt="no write is authorized",
                idempotency_key=self.instruction,
            )

        after = legacy_ledger.read_bytes() if legacy_ledger.exists() else None
        self.assertEqual(after, before)
        self.assertFalse((self.plane.coordination_dir / "host" / "cards").exists())


if __name__ == "__main__":
    unittest.main()
