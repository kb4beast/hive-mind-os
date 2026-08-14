from __future__ import annotations

import argparse
import io
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from hive_mind_os.brain_kernel.events import KernelEvent
from hive_mind_os.brain_kernel.store import (
    DATABASE_FILENAME,
    KernelIntegrityError,
    KernelStore,
)
from hive_mind_os.cli import _run_kernel_status, build_kernel_parser

TIME = "2026-08-07T12:00:00Z"


def event(
    event_id: str,
    event_type: str,
    previous: str | None,
    payload: dict[str, str] | None = None,
    work_id: str | None = None,
) -> KernelEvent:
    return KernelEvent(
        event_id,
        "MISSION-one",
        event_type,
        "actor",
        TIME,
        payload or {},
        work_id=work_id,
        previous_digest=previous,
    )


class KernelStoreTests(unittest.TestCase):
    def test_append_only_chain_restart_and_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / DATABASE_FILENAME
            store = KernelStore(path)
            store.append(event("EVENT-1", "mission.created", None))
            head = store.events()[-1]["digest"]
            store.append(
                event("EVENT-2", "mission.transition", head, {"status": "PLANNING"}),
                expected_sequence=1,
            )
            before = store.projection()
            store.write_snapshot()
            store.close()

            reopened = KernelStore(path)
            self.assertEqual(before, reopened.projection())
            self.assertEqual(before, reopened.rebuild_projections())
            self.assertEqual(before, reopened.load_snapshot())
            self.assertEqual(
                {
                    "mission_id": "MISSION-one",
                    "status": "PLANNING",
                    "work": [],
                    "last_sequence": 2,
                    "state_digest": reopened.status("MISSION-one")["state_digest"],
                },
                reopened.status("MISSION-one"),
            )
            reopened.close()

    def test_rejects_wrong_chain_mutation_and_illegal_transition(self) -> None:
        store = KernelStore()
        store.append(event("EVENT-1", "mission.created", None))
        with self.assertRaises(KernelIntegrityError):
            store.append(
                event("EVENT-2", "mission.transition", None, {"status": "READY"})
            )
        head = store.events()[-1]["digest"]
        with self.assertRaises(KernelIntegrityError):
            store.append(
                event("EVENT-3", "mission.transition", head, {"status": "COMPLETED"})
            )
        with self.assertRaises(sqlite3.IntegrityError):
            store.connection.execute("DELETE FROM events")
        store.close()

    def test_failed_reducer_transaction_leaves_no_partial_event_or_projection(self) -> None:
        store = KernelStore()
        store.append(event("EVENT-1", "mission.created", None))
        before = store.projection()
        head = store.events()[-1]["digest"]
        with self.assertRaises(KernelIntegrityError):
            store.append(
                event("EVENT-2", "mission.transition", head, {"status": "COMPLETED"})
            )
        self.assertEqual(["EVENT-1"], [row["event_id"] for row in store.events()])
        self.assertEqual(before, store.projection())
        store.close()

    def test_corrupt_snapshot_is_replaced_from_the_event_spine(self) -> None:
        store = KernelStore()
        store.append(event("EVENT-1", "mission.created", None))
        store.write_snapshot()
        store.connection.execute("UPDATE snapshots SET state_digest='bad'")
        expected = {"missions": {"MISSION-one": "CREATED"}, "work": {}}
        self.assertEqual(expected, store.load_snapshot())
        snapshot = store.connection.execute("SELECT state_digest FROM snapshots").fetchone()
        self.assertEqual(store.status("MISSION-one")["state_digest"], snapshot["state_digest"])
        store.close()

    def test_snapshot_rejects_paired_state_and_digest_tampering(self) -> None:
        store = KernelStore()
        store.append(event("EVENT-1", "mission.created", None))
        store.write_snapshot()
        store.connection.execute(
            "UPDATE snapshots SET state_json=?, state_digest=?",
            ('{"missions":{"MISSION-one":"COMPLETED"},"work":{}}', "sha256:00"),
        )
        self.assertEqual("CREATED", store.load_snapshot()["missions"]["MISSION-one"])
        store.close()

    def test_concurrent_appends_are_uniquely_ordered(self) -> None:
        store = KernelStore()
        store.append(event("EVENT-0", "mission.created", None))

        def append(index: int) -> int:
            while True:
                head = store.events()[-1]["digest"]
                try:
                    return store.append(
                        event(
                            f"EVENT-{index}",
                            "work.created",
                            head,
                            work_id=f"WORK-{index}",
                        )
                    )
                except KernelIntegrityError as error:
                    if "chain head" not in str(error):
                        raise

        with ThreadPoolExecutor(max_workers=8) as executor:
            sequences = list(executor.map(append, range(1, 17)))
        self.assertEqual(list(range(2, 18)), sorted(sequences))
        self.assertEqual(17, len(store.events()))
        self.assertEqual(16, len(store.status("MISSION-one")["work"]))
        store.close()

    def test_idempotency_retry_is_not_a_second_event(self) -> None:
        store = KernelStore()
        created = event("EVENT-1", "mission.created", None)
        self.assertEqual(1, store.append(created, idempotency_key="create-one"))
        self.assertEqual(1, store.append(created, idempotency_key="create-one"))
        self.assertEqual(1, len(store.events()))
        store.close()

    def test_idempotency_retry_must_bind_the_same_predecessor(self) -> None:
        store = KernelStore()
        created = event("EVENT-1", "mission.created", None)
        store.append(created, idempotency_key="create-one")
        competing = event("EVENT-1", "mission.created", "f" * 64)
        with self.assertRaisesRegex(KernelIntegrityError, "different event"):
            store.append(competing, idempotency_key="create-one")
        self.assertEqual(1, len(store.events()))
        store.close()

    def test_unknown_schema_version_fails_without_rewriting_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / DATABASE_FILENAME
            store = KernelStore(path)
            store.close()
            connection = sqlite3.connect(path)
            connection.execute(
                "UPDATE kernel_metadata SET value='999' WHERE key='schema_version'"
            )
            connection.commit()
            connection.close()
            with self.assertRaisesRegex(KernelIntegrityError, "schema version"):
                KernelStore(path)
            connection = sqlite3.connect(path)
            observed = connection.execute(
                "SELECT value FROM kernel_metadata WHERE key='schema_version'"
            ).fetchone()[0]
            connection.close()
            self.assertEqual(observed, "999")

    def test_invalid_effect_state_fails_on_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / DATABASE_FILENAME
            store = KernelStore(path)
            store.enqueue_effect(
                idempotency_key="effect-one",
                intent_digest="sha256:" + "1" * 64,
                intent={"operation": "test"},
                recorded_at=TIME,
            )
            store.connection.execute(
                "UPDATE effect_outbox SET state='garbage'"
            )
            store.connection.commit()
            store.close()
            with self.assertRaisesRegex(KernelIntegrityError, "invalid state"):
                KernelStore(path)

    def test_batch_append_is_atomic_and_exact_retry_is_read_only(self) -> None:
        store = KernelStore()
        first = event("EVENT-1", "mission.created", None)
        first_digest = first.digest_for(None)
        second = event(
            "EVENT-2",
            "mission.transition",
            first_digest,
            {"status": "PLANNING"},
        )
        entries = ((first, "batch-one"), (second, "batch-two"))
        self.assertEqual((1, 2), store.append_batch(entries))
        before_events = store.events()
        before_projection = store.projection()
        self.assertEqual((1, 2), store.append_batch(entries))
        self.assertEqual(before_events, store.events())
        self.assertEqual(before_projection, store.projection())
        store.close()

    def test_batch_reducer_failure_rolls_back_every_event_and_projection(self) -> None:
        store = KernelStore()
        first = event("EVENT-1", "mission.created", None)
        first_digest = first.digest_for(None)
        invalid = event(
            "EVENT-2",
            "mission.transition",
            first_digest,
            {"status": "COMPLETED"},
        )
        with self.assertRaises(KernelIntegrityError):
            store.append_batch(((first, "batch-one"), (invalid, "batch-two")))
        self.assertEqual([], store.events())
        self.assertEqual({"missions": {}, "work": {}}, store.projection())
        store.close()

    def test_batch_rejects_partial_retry_and_competing_bindings(self) -> None:
        store = KernelStore()
        first = event("EVENT-1", "mission.created", None)
        store.append(first, idempotency_key="batch-one")
        first_digest = store.events()[-1]["digest"]
        second = event(
            "EVENT-2",
            "mission.transition",
            first_digest,
            {"status": "PLANNING"},
        )
        with self.assertRaisesRegex(KernelIntegrityError, "partial batch retry"):
            store.append_batch(((first, "batch-one"), (second, "batch-two")))
        competing = event("EVENT-other", "mission.created", None)
        with self.assertRaisesRegex(KernelIntegrityError, "already bound"):
            store.append(competing, idempotency_key="batch-one")
        self.assertEqual(["EVENT-1"], [row["event_id"] for row in store.events()])
        store.close()

    def test_kernel_status_reads_a_fixture_database_without_creating_missing_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary) / "state"
            missing = argparse.Namespace(
                state_dir=str(state_dir), mission_id="MISSION-one", json_output=True
            )
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(1, _run_kernel_status(missing))
            self.assertFalse(state_dir.exists())
            self.assertIn("does not exist", stderr.getvalue())

            state_dir.mkdir()
            store = KernelStore(KernelStore.database_path(state_dir))
            store.append(event("EVENT-1", "mission.created", None))
            store.close()
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    0,
                    _run_kernel_status(
                        argparse.Namespace(
                            state_dir=str(state_dir),
                            mission_id="MISSION-one",
                            json_output=True,
                        )
                    ),
                )
            self.assertIn('"status": "CREATED"', stdout.getvalue())
            reader = KernelStore(KernelStore.database_path(state_dir), read_only=True)
            self.assertEqual("CREATED", reader.status("MISSION-one")["status"])
            with self.assertRaises(KernelIntegrityError):
                reader.write_snapshot()
            reader.close()
            parsed = build_kernel_parser().parse_args(
                ["status", "MISSION-one", "--state-dir", str(state_dir), "--json"]
            )
            self.assertEqual("status", parsed.kernel_command)

    def test_database_path_is_portable_relative_to_a_windows_style_state_dir(self) -> None:
        database = KernelStore.database_path("kernel-state\\nested")
        self.assertEqual(DATABASE_FILENAME, database.name)
        self.assertEqual("nested", database.parent.name)
