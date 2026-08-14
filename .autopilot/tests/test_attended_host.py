from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fixture_support import copy_autopilot_fixture

BIN = Path(__file__).resolve().parents[1] / "bin"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, BIN / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


controller = _load("attended_controller", "controller.py")
attended = _load("attended_host_module", "attended_host.py")

NODE = "MISSION-400"
BRANCH = "autopilot/mission-400"
INSTRUCTION = "sha256:" + "a" * 64


def git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", "-C", str(root)) + arguments,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class AttendedHostTests(unittest.TestCase):
    """The adapter must satisfy host_execution's validators and never block."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.root = base / "work"
        self.origin = base / "origin.git"
        self.root.mkdir()
        subprocess.run(
            ("git", "init", "--bare", "--initial-branch=main", str(self.origin)),
            check=True,
            capture_output=True,
        )
        git(self.root, "init", "--initial-branch=main")
        git(self.root, "config", "user.name", "Fixture")
        git(self.root, "config", "user.email", "fixture@hive-mind.invalid")
        copy_autopilot_fixture(Path(__file__).resolve().parents[1], self.root / ".autopilot")
        control_path = self.root / ".autopilot" / "control-plane.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control["verify_git_objects"] = False
        control_path.write_text(json.dumps(control, indent=2) + "\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", "fixture base")
        git(self.root, "remote", "add", "origin", str(self.origin))
        git(self.root, "push", "-u", "origin", "main")
        self.target = git(self.root, "rev-parse", "HEAD")
        self.plane = controller.ControlPlane(self.root)
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
            [{"launch_instruction_id": INSTRUCTION, "node_id": NODE}]
        )

    def _sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def push_node_head(self, *, email: str) -> str:
        tree = git(self.root, "rev-parse", f"{self.target}^{{tree}}")
        commit = subprocess.run(
            (
                "git", "-C", str(self.root),
                "-c", "user.name=Fixture Identity",
                "-c", f"user.email={email}",
                "commit-tree", tree, "-p", self.target, "-m", "node head",
            ),
            check=True,
            capture_output=True,
            text=True,
            env={**__import__("os").environ, "GIT_AUTHOR_EMAIL": email, "GIT_COMMITTER_EMAIL": email},
        ).stdout.strip()
        git(self.root, "push", "--force", "origin", f"{commit}:refs/heads/{BRANCH}")
        return commit

    def create(self) -> dict:
        return dict(
            self.host.create_thread(
                title=f"Hive Mind {NODE}",
                prompt="rendered node contract",
                idempotency_key=INSTRUCTION,
            )
        )

    def test_creation_matches_the_host_binding_contract(self) -> None:
        created = self.create()
        self.assertEqual(set(created), {
            "kind", "host_id", "task_id", "cursor", "capability", "idempotency_key",
        })
        self.assertEqual(created["kind"], attended.CREATE_KIND)
        self.assertEqual(created["idempotency_key"], INSTRUCTION)
        card = self.host.cards_dir / f"{created['task_id']}.md"
        self.assertIn("rendered node contract", card.read_text(encoding="utf-8"))

    def test_lookup_enables_crash_safe_adoption(self) -> None:
        created = self.create()
        persisted = self.host.lookup_thread(idempotency_key=INSTRUCTION)
        assert persisted is not None
        self.assertEqual(persisted["task_id"], created["task_id"])
        self.assertEqual(
            persisted["capability_digest"],
            "sha256:" + attended._digest(created["capability"]),
        )

    def test_corrupt_ledger_fails_closed_instead_of_resetting(self) -> None:
        self.create()
        self.host.ledger_path.write_text("{", encoding="utf-8")
        with self.assertRaises(attended.AttendedHostError):
            self.host.lookup_thread(idempotency_key=INSTRUCTION)

    def test_duplicate_ledger_key_fails_closed(self) -> None:
        self.host.host_dir.mkdir(parents=True, exist_ok=True)
        self.host.ledger_path.write_text('{"x":{},"x":{}}\n', encoding="utf-8")
        with self.assertRaisesRegex(attended.AttendedHostError, "duplicate key"):
            self.host.pending_cards()

    def test_identical_create_reuses_one_durable_binding(self) -> None:
        first = self.create()
        ledger_before = self.host.ledger_path.read_bytes()
        card = self.host.cards_dir / f"{first['task_id']}.md"
        card_before = card.read_bytes()
        second = self.create()
        self.assertEqual(first["task_id"], second["task_id"])
        ledger = json.loads(self.host.ledger_path.read_text(encoding="utf-8"))
        self.assertEqual(list(ledger), [INSTRUCTION])
        self.assertEqual(ledger_before, self.host.ledger_path.read_bytes())
        self.assertEqual(card_before, card.read_bytes())

    def test_idempotency_key_cannot_be_reused_for_different_instructions(self) -> None:
        self.create()
        with self.assertRaisesRegex(attended.AttendedHostError, "different launch"):
            self.host.create_thread(
                title=f"Hive Mind {NODE}",
                prompt="competing instructions",
                idempotency_key=INSTRUCTION,
            )

    def test_general_ledger_read_rejects_a_tampered_card(self) -> None:
        created = self.create()
        card = self.host.cards_dir / f"{created['task_id']}.md"
        card.write_text("competing card\n", encoding="utf-8")
        with self.assertRaisesRegex(attended.AttendedHostError, "card digest"):
            self.host.pending_cards()

    def test_task_binding_rejects_a_traversing_node_id(self) -> None:
        with self.assertRaisesRegex(attended.AttendedHostError, "unsafe"):
            self.host.bind_tasks(
                [{"launch_instruction_id": "launch:escape", "node_id": "../escape"}]
            )

    def test_receipt_commit_is_the_only_success_evidence(self) -> None:
        created = self.create()
        self.push_node_head(email=attended.RECEIPT_IDENTITY)
        events = self.host.wait_threads(
            [{"task_id": created["task_id"], "after_event_cursor": None}]
        )
        self.assertEqual([event["state"] for event in events], ["SUCCEEDED"])
        self.assertEqual(set(events[0]), {
            "kind", "host_id", "task_id", "cursor", "capability",
            "state", "event_id", "event_cursor",
        })

    def test_pushed_work_without_a_receipt_is_active(self) -> None:
        created = self.create()
        head = self.push_node_head(email="worker@example.invalid")
        events = self.host.wait_threads(
            [{"task_id": created["task_id"], "after_event_cursor": None}]
        )
        self.assertEqual([event["state"] for event in events], ["ACTIVE"])
        self.assertEqual(events[0]["event_cursor"], head)

    def test_unchanged_evidence_emits_no_repeat_event(self) -> None:
        created = self.create()
        head = self.push_node_head(email="worker@example.invalid")
        events = self.host.wait_threads(
            [{"task_id": created["task_id"], "after_event_cursor": head}]
        )
        self.assertEqual(events, ())

    def test_silence_returns_within_the_deadline(self) -> None:
        created = self.create()
        events = self.host.wait_threads(
            [{"task_id": created["task_id"], "after_event_cursor": None}]
        )
        self.assertEqual(events, ())
        self.assertLessEqual(self.now, 10)
        self.assertTrue(self.slept, "a silent wait must poll, not spin")

    def test_recorded_blocker_is_terminal_failure(self) -> None:
        created = self.create()
        blockers = Path(self.plane.blockers_dir)
        blockers.mkdir(parents=True, exist_ok=True)
        (blockers / f"{NODE}.jsonl").write_text(
            json.dumps({"node_id": NODE, "kind": "escalation"}) + "\n", encoding="utf-8"
        )
        events = self.host.wait_threads(
            [{"task_id": created["task_id"], "after_event_cursor": None}]
        )
        self.assertEqual([event["state"] for event in events], ["FAILED"])

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
        self.assertEqual(set(ack), {
            "kind", "host_id", "task_id", "cursor", "capability",
            "accepted", "message_id", "idempotency_key",
        })
        relay = self.root / ".autopilot" / "state" / "host" / "cards" / f"{NODE}.relay.md"
        self.assertIn("continue; report BLOCKS", relay.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
