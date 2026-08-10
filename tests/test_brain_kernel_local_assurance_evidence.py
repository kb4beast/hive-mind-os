from __future__ import annotations

import unittest
from pathlib import Path

from hive_mind_os.brain_kernel.local_assurance import verify_local_assurance_artifact


class LocalAssuranceEvidenceTests(unittest.TestCase):
    def test_retained_phase12_packet_is_content_addressable(self) -> None:
        root = Path(__file__).resolve().parents[1]
        packet = root / "evidence" / "local_assurance" / "phase12-9efe64b"

        report = verify_local_assurance_artifact(
            packet / "assurance.json", packet / "receipts.json"
        )

        self.assertEqual("9efe64b80b4bf7b50c7bcf20e9aef5acb8fc55a7", report["candidate_commit"])
        self.assertFalse(report["release_ready"])


if __name__ == "__main__":
    unittest.main()
