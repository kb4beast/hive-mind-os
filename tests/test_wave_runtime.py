from __future__ import annotations

import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event, Lock
from unittest.mock import patch

from hive_mind_os.brain_kernel.candidate_state import (
    CandidateSnapshot,
    CandidateStateError,
    CandidateStateJournal,
)
from hive_mind_os.runtime_contracts import WaveState
from hive_mind_os.wave_manifest import CandidateIdentity

DIGEST = "sha256:" + "a" * 64
OTHER_DIGEST = "sha256:" + "b" * 64
SUBJECT = "sha256:" + "c" * 64
IDENTITY = CandidateIdentity("1" * 40, "2" * 40, SUBJECT)
ROOT = Path(__file__).resolve().parents[1]


class CandidateStateJournalTests(unittest.TestCase):
    def checkpoint(self, journal: CandidateStateJournal):
        return journal.checkpoint(
            candidate_id="candidate-1",
            wave_id="wave-1",
            node_id="node-1",
            generation=1,
            manifest_digest=DIGEST,
            authority_digest=OTHER_DIGEST,
            checkpoint_digest=DIGEST,
            idempotency_key="checkpoint-1",
        )

    def test_sealed_candidate_survives_restart_and_reaches_integration_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidates.sqlite3"
            journal = CandidateStateJournal(path)
            self.checkpoint(journal)
            sealed = journal.transition(
                "candidate-1",
                expected_sequence=1,
                state=WaveState.CANDIDATE_SEALED,
                identity=IDENTITY,
                idempotency_key="seal-1",
            )
            journal.transition(
                "candidate-1",
                expected_sequence=2,
                state=WaveState.VERIFYING,
                idempotency_key="verify-1",
            )
            journal.close()

            resumed = CandidateStateJournal(path)
            ready = resumed.transition(
                "candidate-1",
                expected_sequence=3,
                state=WaveState.INTEGRATION_READY,
                checkpoint_digest=OTHER_DIGEST,
                idempotency_key="ready-1",
            )
            self.assertEqual(ready.identity, IDENTITY)
            self.assertEqual(ready.state, WaveState.INTEGRATION_READY)
            old_retry = resumed.transition(
                "candidate-1",
                expected_sequence=1,
                state=WaveState.CANDIDATE_SEALED,
                identity=IDENTITY,
                idempotency_key="seal-1",
            )
            self.assertEqual(old_retry, sealed)
            self.assertEqual([item.sequence for item in resumed.history("candidate-1")], [1, 2, 3, 4])
            self.assertTrue(sealed.sealed)
            resumed.close()

    def test_sealing_requires_and_permanently_binds_exact_identity(self) -> None:
        journal = CandidateStateJournal()
        self.addCleanup(journal.close)
        self.checkpoint(journal)
        with self.assertRaises(CandidateStateError):
            journal.transition(
                "candidate-1",
                expected_sequence=1,
                state=WaveState.CANDIDATE_SEALED,
                idempotency_key="missing-identity",
            )
        journal.transition(
            "candidate-1",
            expected_sequence=1,
            state=WaveState.CANDIDATE_SEALED,
            identity=IDENTITY,
            idempotency_key="seal",
        )
        changed = CandidateIdentity("3" * 40, "4" * 40, SUBJECT)
        with self.assertRaisesRegex(CandidateStateError, "immutable"):
            journal.transition(
                "candidate-1",
                expected_sequence=2,
                state=WaveState.VERIFYING,
                identity=changed,
                idempotency_key="mutate",
            )

    def test_compare_and_swap_and_idempotency_prevent_competing_parents(self) -> None:
        journal = CandidateStateJournal()
        self.addCleanup(journal.close)
        original = self.checkpoint(journal)
        retry = journal.checkpoint(
            candidate_id="candidate-1",
            wave_id="wave-1",
            node_id="node-1",
            generation=1,
            manifest_digest=DIGEST,
            authority_digest=OTHER_DIGEST,
            checkpoint_digest=DIGEST,
            idempotency_key="checkpoint-1",
        )
        self.assertEqual(retry, original)
        journal.transition(
            "candidate-1",
            expected_sequence=1,
            state=WaveState.CANDIDATE_SEALED,
            identity=IDENTITY,
            idempotency_key="winner",
        )
        with self.assertRaisesRegex(CandidateStateError, "compare-and-swap"):
            journal.transition(
                "candidate-1",
                expected_sequence=1,
                state=WaveState.RECOVERABLE,
                identity=IDENTITY,
                idempotency_key="loser",
                reason="competing parent lost CAS",
            )

    def test_terminal_state_cannot_be_reopened(self) -> None:
        journal = CandidateStateJournal()
        self.addCleanup(journal.close)
        self.checkpoint(journal)
        journal.transition(
            "candidate-1",
            expected_sequence=1,
            state=WaveState.CANDIDATE_SEALED,
            identity=IDENTITY,
            idempotency_key="seal",
        )
        journal.transition(
            "candidate-1",
            expected_sequence=2,
            state=WaveState.FAILED,
            idempotency_key="fail",
            reason="independent verification failed",
        )
        with self.assertRaises(CandidateStateError):
            journal.transition(
                "candidate-1",
                expected_sequence=3,
                state=WaveState.VERIFYING,
                idempotency_key="reopen",
            )

    def test_preseal_drift_can_record_replan_without_inventing_a_candidate(self) -> None:
        journal = CandidateStateJournal()
        self.addCleanup(journal.close)
        self.checkpoint(journal)
        result = journal.transition(
            "candidate-1",
            expected_sequence=1,
            state=WaveState.REPLAN_REQUIRED,
            idempotency_key="preseal-replan",
            reason="subject snapshot drifted before sealing",
        )
        self.assertIsNone(result.identity)
        self.assertEqual(result.state, WaveState.REPLAN_REQUIRED)

    def test_database_triggers_preserve_append_only_history(self) -> None:
        journal = CandidateStateJournal()
        self.addCleanup(journal.close)
        self.checkpoint(journal)
        with self.assertRaises(sqlite3.IntegrityError):
            journal.connection.execute("UPDATE candidate_events SET payload_json='{}'")
        with self.assertRaises(sqlite3.IntegrityError):
            journal.connection.execute("DELETE FROM candidate_events")

    def test_boolean_candidate_schema_version_is_rejected(self) -> None:
        journal = CandidateStateJournal()
        self.addCleanup(journal.close)
        document = self.checkpoint(journal).to_document()
        document["schema_version"] = True
        with self.assertRaisesRegex(CandidateStateError, "unknown shape"):
            CandidateSnapshot.from_document(document)

    def test_same_handle_verification_serializes_database_access(self) -> None:
        journal = CandidateStateJournal()
        self.addCleanup(journal.close)
        self.checkpoint(journal)
        original_rows = journal._rows
        first_read_entered = Event()
        release_first_read = Event()
        second_verify_started = Event()
        second_read_entered = Event()
        counter_lock = Lock()
        read_count = 0

        def observed_rows(
            candidate_id: str | None = None,
        ) -> tuple[sqlite3.Row, ...]:
            nonlocal read_count
            with counter_lock:
                read_count += 1
                read_ordinal = read_count
            if read_ordinal == 1:
                first_read_entered.set()
                if not release_first_read.wait(2):
                    raise AssertionError("test did not release the first journal read")
            elif read_ordinal == 2:
                second_read_entered.set()
            return original_rows(candidate_id)

        def run_second_verify() -> None:
            second_verify_started.set()
            journal.verify()

        with patch.object(journal, "_rows", side_effect=observed_rows):
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(journal.verify)
                self.assertTrue(first_read_entered.wait(2))
                second = pool.submit(run_second_verify)
                self.assertTrue(second_verify_started.wait(2))
                try:
                    self.assertFalse(
                        second_read_entered.wait(0.1),
                        "two verifiers entered one SQLite connection concurrently",
                    )
                finally:
                    release_first_read.set()
                first.result(timeout=2)
                second.result(timeout=2)
        self.assertTrue(second_read_entered.is_set())

    def test_repeated_concurrent_same_handle_verification_is_stable(self) -> None:
        journal = CandidateStateJournal()
        self.addCleanup(journal.close)
        self.checkpoint(journal)
        journal.checkpoint(
            candidate_id="candidate-2",
            wave_id="wave-1",
            node_id="node-2",
            generation=1,
            manifest_digest=DIGEST,
            authority_digest=OTHER_DIGEST,
            checkpoint_digest=OTHER_DIGEST,
            idempotency_key="checkpoint-2",
        )
        start = Barrier(3)

        def verify_many() -> None:
            start.wait(timeout=2)
            for _ in range(500):
                journal.verify()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = (pool.submit(verify_many), pool.submit(verify_many))
            start.wait(timeout=2)
            for future in futures:
                future.result(timeout=10)
        journal.verify()

    def test_concurrent_same_handle_transitions_preserve_one_cas_winner(self) -> None:
        journal = CandidateStateJournal()
        self.addCleanup(journal.close)
        self.checkpoint(journal)
        start = Barrier(3)

        def seal(idempotency_key: str) -> CandidateSnapshot | CandidateStateError:
            start.wait(timeout=2)
            try:
                return journal.transition(
                    "candidate-1",
                    expected_sequence=1,
                    state=WaveState.CANDIDATE_SEALED,
                    identity=IDENTITY,
                    idempotency_key=idempotency_key,
                )
            except CandidateStateError as error:
                return error

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = (pool.submit(seal, "seal-a"), pool.submit(seal, "seal-b"))
            start.wait(timeout=2)
            results = tuple(future.result(timeout=5) for future in futures)
        successes = tuple(
            result for result in results if isinstance(result, CandidateSnapshot)
        )
        failures = tuple(
            result for result in results if isinstance(result, CandidateStateError)
        )
        self.assertEqual(1, len(successes))
        self.assertEqual(1, len(failures))
        self.assertIn("compare-and-swap", str(failures[0]))
        self.assertEqual(
            [1, 2],
            [item.sequence for item in journal.history("candidate-1")],
        )

    def test_constructor_rejection_closes_its_sqlite_connection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "malformed-candidates.sqlite3"
            journal = CandidateStateJournal(path)
            journal.close()
            connection = sqlite3.connect(path)
            connection.execute(
                """
                INSERT INTO candidate_events(
                    candidate_id, candidate_sequence, idempotency_key,
                    payload_json, previous_digest, event_digest
                ) VALUES(?,?,?,?,?,?)
                """,
                ("candidate-1", 1, "bad", "{}", None, "bad-digest"),
            )
            connection.commit()
            connection.close()
            script = (
                "import gc, pathlib, sys\n"
                f"sys.path[:0] = [{str(ROOT / 'src')!r}, {str(ROOT)!r}]\n"
                "from hive_mind_os.brain_kernel.candidate_state import "
                "CandidateStateError, CandidateStateJournal\n"
                "try:\n"
                f"    CandidateStateJournal(pathlib.Path({str(path)!r}))\n"
                "except CandidateStateError as error:\n"
                "    print(f'constructor_error={type(error).__name__}: {error}')\n"
                "else:\n"
                "    raise AssertionError('malformed journal construction passed')\n"
                "gc.collect()\n"
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    "-X",
                    "utf8",
                    "-W",
                    "error::ResourceWarning",
                    "-c",
                    script,
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("constructor_error=CandidateStateError", completed.stdout)
            self.assertNotIn("ResourceWarning", completed.stderr)
            self.assertNotIn("Exception ignored", completed.stderr)


if __name__ == "__main__":
    unittest.main()
