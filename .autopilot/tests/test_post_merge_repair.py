from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fixture_support import copy_autopilot_fixture

BIN = Path(__file__).resolve().parents[1] / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import autopilot  # noqa: E402
from durable_controller import ControlPlane as DurableControlPlane  # noqa: E402


class PostMergeRepairTests(unittest.TestCase):
    @staticmethod
    def repository_root() -> Path:
        return Path(__file__).resolve().parents[2]

    @staticmethod
    def current_head(repository: Path) -> str:
        return subprocess.run(
            ("git", "-C", str(repository), "rev-parse", "HEAD"),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def live_plane(self) -> autopilot.ControlPlane:
        repository = self.repository_root()
        plane = autopilot.ControlPlane(repository)
        head = self.current_head(repository)
        plane.current_target_sha = lambda: head  # type: ignore[method-assign]
        plane._durable_receipt_cache = None
        return plane

    def test_exact_authority_and_successor_receipts_validate(self) -> None:
        plane = self.live_plane()
        self.assertEqual(plane._post_merge_repair_issues(), ())
        self.assertEqual(plane.sealed_recovery_issues(), ())

        raw = DurableControlPlane._durable_receipt_records(plane)
        expected = {
            "BUILDER-330": "6e7a4dd8a8bc24c589b14b3e4909216f35d850cb",
            "ORCH-300": "38912a9e590581ecf1e3100256d8bb43466b92e9",
            "OPTIMIZER-370": "9470f751a9cbd2e16dc05a99389c68770b3ed232",
        }
        for node_id, receipt_commit in expected.items():
            with self.subTest(node_id=node_id):
                self.assertEqual(len(raw[node_id]), 2)
                resolved = plane.resolve_sealed_repair_records(node_id, raw[node_id])
                self.assertEqual([item["commit"] for item in resolved], [receipt_commit])
                self.assertEqual(plane.node_view(node_id).state, "COMPLETE")

    def test_third_receipt_remains_fail_closed(self) -> None:
        plane = self.live_plane()
        raw = DurableControlPlane._durable_receipt_records(plane)
        records = list(raw["ORCH-300"])
        records.append({**records[0], "commit": "f" * 40})
        self.assertEqual(
            plane.resolve_sealed_repair_records("ORCH-300", records),
            records,
        )

    def test_authority_tamper_fails_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_autopilot_fixture(
                self.repository_root() / ".autopilot",
                root / ".autopilot",
            )
            control_path = root / ".autopilot" / "control-plane.json"
            control = json.loads(control_path.read_text(encoding="utf-8"))
            control["verify_git_objects"] = False
            control_path.write_text(
                json.dumps(control, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            authority_path = (
                root / ".autopilot" / "post-merge-repair-authorities.json"
            )
            authority = json.loads(authority_path.read_text(encoding="utf-8"))
            authority["records"][0]["candidate_commit"] = "f" * 40
            authority_path.write_text(
                json.dumps(authority, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            plane = autopilot.ControlPlane(root)
            issues = plane.validate_configuration()
            self.assertIn(
                "post-merge repair authority document was altered",
                issues,
            )


if __name__ == "__main__":
    unittest.main()
