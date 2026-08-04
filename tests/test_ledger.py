from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from hive_mind_os.ledger import EvidenceLedger, LedgerIntegrityError


class LedgerIntegrityTests(unittest.TestCase):
    def test_tampered_event_is_detected_after_triggers_are_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ledger.sqlite3"
            ledger = EvidenceLedger(path)
            ledger.append_event("mission", "started", "builder", {"value": 1})
            ledger.close()
            connection = sqlite3.connect(path)
            with connection:
                connection.execute("DROP TRIGGER events_no_update")
                connection.execute(
                    "UPDATE events SET payload=? WHERE sequence=1",
                    ('{"value":2}',),
                )
            connection.close()
            ledger = EvidenceLedger(path)
            try:
                with self.assertRaises(LedgerIntegrityError):
                    ledger.events()
            finally:
                ledger.close()
