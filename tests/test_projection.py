from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from hive_mind_os.autonomy import AutonomyBudget
from hive_mind_os.cli import main
from hive_mind_os.ledger import EvidenceLedger
from hive_mind_os.mission_store import MissionStore
from hive_mind_os.models import Role
from hive_mind_os.projection import build_projection, projection_html, projection_json
from hive_mind_os.scheduler import Scheduler


class ProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = MissionStore(self.root)
        self.ledger = EvidenceLedger(self.root / "evidence-ledger.sqlite3")
        self.scheduler = Scheduler(self.root)

    def tearDown(self) -> None:
        self.scheduler.close()
        self.ledger.close()
        self.store.close()
        self.temporary.cleanup()

    def _register(self, mission_id: str) -> None:
        self.store.register_mission(
            mission_id,
            {
                "objective": f"objective {mission_id}",
                "repository": str(self.root),
                "source_pack_fingerprint": f"sha256:{'1' * 64}",
            },
            AutonomyBudget(10, 10, 10),
        )

    def test_store_success_without_ledger_completion_is_unknown(self) -> None:
        self._register("gap")
        for role in (Role.EXPLORER, Role.BUILDER, Role.CURATOR):
            self.store.mark_role("gap", role, "succeeded")
        self.store.mark_status("gap", "succeeded")
        model = build_projection(self.root)
        self.assertEqual(model["missions"][0]["state"], "unknown")

    def test_blocked_mission_renders_reason_and_quarantine(self) -> None:
        self._register("blocked")
        self.store.mark_status(
            "blocked",
            "blocked",
            blocker="workspace digest mismatch",
        )
        self.ledger.append_event(
            "blocked",
            "candidate.quarantined",
            "curator",
            {"verdict": "quarantine"},
        )
        mission = build_projection(self.root)["missions"][0]
        self.assertEqual(mission["state"], "blocked")
        self.assertEqual(mission["blocked_reasons"], ["workspace digest mismatch"])
        self.assertTrue(mission["quarantined"])

    def test_dead_letter_renders_recorded_mission_failure(self) -> None:
        job = self.scheduler.enqueue(
            "test",
            {"mission_id": "dead", "objective": "fails"},
            max_attempts=1,
            mission_id="dead",
        )
        claimed = self.scheduler.claim("worker")
        assert claimed is not None and claimed.lease_token is not None
        self.scheduler.fail(
            job.id,
            claimed.lease_token,
            "terminal fixture failure",
            mission_id="dead",
        )
        mission = build_projection(self.root)["missions"][0]
        self.assertEqual(mission["state"], "dead-letter")
        self.assertEqual(mission["blocked_reasons"], ["terminal fixture failure"])

    def test_html_is_self_contained_and_matches_golden(self) -> None:
        model = {
            "schema_version": 1,
            "generated_at": "<timestamp>",
            "missions": [
                {
                    "mission_id": "M-unknown",
                    "objective": "missing evidence",
                    "state": "unknown",
                    "blocked_reasons": [],
                    "quarantined": False,
                    "receipt_count": 0,
                },
                {
                    "mission_id": "M-blocked",
                    "objective": "blocked work",
                    "state": "blocked",
                    "blocked_reasons": ["needs evidence"],
                    "quarantined": True,
                    "receipt_count": 2,
                },
            ],
            "jobs": [],
            "state_counts": {},
        }
        rendered = projection_html(model)
        golden = (
            Path(__file__).parent
            / "fixtures"
            / "projection"
            / "status.html"
        ).read_text(encoding="utf-8")
        self.assertEqual(rendered, golden)
        self.assertNotIn("<script", rendered)
        for state in ("unknown", "blocked", "quarantined"):
            self.assertIn(state, rendered)

    def test_json_projection_and_status_cli_round_trip_all_fields(self) -> None:
        self._register("active")
        self.ledger.append_event("active", "mission.started", "orchestrator", {})
        model = json.loads(projection_json(build_projection(self.root)))
        self.assertEqual(
            set(model),
            {"schema_version", "generated_at", "missions", "jobs", "state_counts"},
        )
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as exit_context:
            main(["status", "--state-dir", str(self.root), "--json"])
        self.assertEqual(exit_context.exception.code, 0)
        parsed = json.loads(output.getvalue())
        self.assertEqual(parsed["missions"][0]["state"], "running")


if __name__ == "__main__":
    unittest.main()
