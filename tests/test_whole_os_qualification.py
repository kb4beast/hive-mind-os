import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hive_mind_os.whole_os_qualification import (
    Disposition,
    ExternalObligation,
    PilotReport,
    QualificationLedger,
)


class WholeOSQualificationTests(unittest.TestCase):
    def test_blocked_pilot_does_not_promote(self):
        report = PilotReport(
            "pilot",
            "roblox",
            "sha256:" + "a" * 64,
            0,
            0,
            (),
            False,
            0,
            0,
            None,
            (
                ExternalObligation(
                    "runtime",
                    Disposition.BLOCKED_CAPABILITY,
                    "Studio unavailable",
                    ("R14",),
                ),
            ),
        )
        self.assertEqual(report.disposition(), Disposition.BLOCKED_CAPABILITY)

    def test_ledger_detects_tampering(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "ledger.jsonl"
            ledger = QualificationLedger(path)
            ledger.append("candidate", {"id": "one"})
            path.write_text(
                path.read_text().replace("candidate", "tampered"), encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                ledger.read()


if __name__ == "__main__":
    unittest.main()
