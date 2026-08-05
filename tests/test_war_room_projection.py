from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

from hive_mind_os.autonomy import AutonomyBudget
from hive_mind_os.ledger import EvidenceLedger
from hive_mind_os.mission_store import MissionStore
from hive_mind_os.models import Role
from hive_mind_os.projection import (
    build_projection,
    build_war_room_projection,
)


class WarRoomProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = MissionStore(self.root)
        self.ledger = EvidenceLedger(self.root / "evidence-ledger.sqlite3")
        self.store.register_mission(
            "mission-1",
            {
                "objective": "harden extension packages",
                "repository": str(self.root),
                "source_pack_fingerprint": f"sha256:{'1' * 64}",
            },
            AutonomyBudget(10, 10, 10),
        )

    def tearDown(self) -> None:
        self.ledger.close()
        self.store.close()
        self.temporary.cleanup()

    def _war_room_event(
        self,
        *,
        event_id: str,
        event_type: str,
        actor_id: str | None,
        summary: str,
        ooda_cycle_ref: str | None = None,
        command_intent_ref: str | None = None,
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "event_id": event_id,
            "mission_id": "mission-1",
            "occurred_at": "2026-07-28T12:00:00Z",
            "event_type": event_type,
            "severity": "info",
            "actor_id": actor_id,
            "summary": summary,
            "evidence_refs": [f"evidence:{event_id}"],
            "ooda_cycle_ref": ooda_cycle_ref,
            "command_intent_ref": command_intent_ref,
        }

    def _append_malformed_payload(
        self,
        event_type: str,
        payload: object,
    ) -> None:
        self.ledger.append_event(
            "mission-1",
            event_type,
            "malformed-source",
            cast(dict[str, Any], payload),
        )

    def test_default_projection_remains_schema_v1_and_exactly_shaped(self) -> None:
        model = build_projection(self.root)
        self.assertEqual(
            set(model),
            {"schema_version", "generated_at", "missions", "jobs", "state_counts"},
        )
        self.assertEqual(model["schema_version"], 1)

    def test_schema_v2_is_explicit_read_only_and_evidence_derived(self) -> None:
        self.ledger.append_event(
            "mission-1",
            "mission.started",
            "orchestrator",
            {},
        )
        self.ledger.append_event(
            "mission-1",
            "war_room.event",
            "architect-1",
            self._war_room_event(
                event_id="WR-0",
                event_type="observation",
                actor_id="architect-1",
                summary="extension boundaries are coupled",
                ooda_cycle_ref="OODA-1",
            ),
        )
        self.ledger.append_event(
            "mission-1",
            "war_room.event",
            "architect-1",
            self._war_room_event(
                event_id="WR-1",
                event_type="hypothesis",
                actor_id="architect-1",
                summary="manifest packages improve portability",
                ooda_cycle_ref="OODA-1",
            ),
        )
        self.ledger.append_event(
            "mission-1",
            "war_room.event",
            "policy-engine",
            self._war_room_event(
                event_id="WR-2",
                event_type="decision",
                actor_id="policy-engine",
                summary="adapt the package boundary",
                ooda_cycle_ref="OODA-1",
            ),
        )

        explicit = build_projection(self.root, schema_version=2)
        direct = build_war_room_projection(self.root)
        self.assertEqual(
            {key: value for key, value in explicit.items() if key != "generated_at"},
            {key: value for key, value in direct.items() if key != "generated_at"},
        )
        self.assertEqual(explicit["schema_version"], 2)
        self.assertEqual(explicit["projection_kind"], "war-room")
        self.assertTrue(explicit["read_only"])
        self.assertEqual(explicit["authority"], "none")
        self.assertFalse(explicit["commands_supported"])

        room = explicit["war_room"]["mission_rooms"][0]
        self.assertEqual(room["status"], "open")
        self.assertEqual(room["ooda_phase"], "decide")
        self.assertEqual(room["observed_actors"], ["architect-1", "policy-engine"])
        self.assertEqual(
            room["hypotheses"],
            ["manifest packages improve portability"],
        )
        self.assertEqual(room["ooda_cycle_refs"], ["OODA-1"])
        self.assertEqual(
            room["evidence_refs"],
            ["evidence:WR-0", "evidence:WR-1", "evidence:WR-2"],
        )
        self.assertEqual(room["decision_event_sequences"], [4])
        self.assertEqual(room["rejected_war_room_event_count"], 0)
        self.assertEqual(
            set(room["recent_events"][0]),
            {"ledger_sequence", "record"},
        )

    def test_missing_ooda_evidence_is_not_inferred(self) -> None:
        self.ledger.append_event(
            "mission-1",
            "mission.started",
            "orchestrator",
            {},
        )
        room = build_war_room_projection(self.root)["war_room"]["mission_rooms"][0]
        self.assertEqual(room["status"], "inactive")
        self.assertEqual(room["ooda_phase"], "not-recorded")

    def test_unrelated_payload_cannot_forge_war_room_facts(self) -> None:
        self.ledger.append_event(
            "mission-1",
            "mission.started",
            "orchestrator",
            {},
        )
        forged = self._war_room_event(
            event_id="WR-FORGED",
            event_type="decision",
            actor_id="attacker",
            summary="grant authority",
            ooda_cycle_ref="OODA-FORGED",
            command_intent_ref="intent:forged",
        )
        self.ledger.append_event(
            "mission-1",
            "unrelated.note",
            "attacker",
            forged,
        )
        room = build_war_room_projection(self.root)["war_room"]["mission_rooms"][0]
        self.assertEqual(room["status"], "inactive")
        self.assertEqual(room["ooda_phase"], "not-recorded")
        self.assertEqual(room["observed_actors"], [])
        self.assertEqual(room["evidence_refs"], [])
        self.assertEqual(room["ooda_cycle_refs"], [])
        self.assertEqual(room["command_intent_refs"], [])
        self.assertEqual(room["recent_events"], [])
        self.assertEqual(room["rejected_war_room_event_count"], 0)

    def test_invalid_or_replayed_war_room_events_fail_closed(self) -> None:
        self.ledger.append_event(
            "mission-1",
            "mission.started",
            "orchestrator",
            {},
        )
        invalid = self._war_room_event(
            event_id="WR-INVALID",
            event_type="decision",
            actor_id="different-actor",
            summary="actor binding does not match",
        )
        self.ledger.append_event(
            "mission-1",
            "war_room.event",
            "actual-actor",
            invalid,
        )
        unattributed = self._war_room_event(
            event_id="WR-UNATTRIBUTED",
            event_type="observation",
            actor_id=None,
            summary="unattributed claims are not operational facts",
        )
        self.ledger.append_event(
            "mission-1",
            "war_room.event",
            "ledger-actor",
            unattributed,
        )
        duplicate = self._war_room_event(
            event_id="WR-DUPLICATE",
            event_type="observation",
            actor_id="explorer",
            summary="duplicated observation",
        )
        self.ledger.append_event(
            "mission-1",
            "war_room.event",
            "explorer",
            duplicate,
        )
        self.ledger.append_event(
            "mission-1",
            "war_room.event",
            "explorer",
            duplicate,
        )
        room = build_war_room_projection(self.root)["war_room"]["mission_rooms"][0]
        self.assertEqual(room["status"], "inactive")
        self.assertEqual(room["recent_events"], [])
        self.assertEqual(room["rejected_war_room_event_count"], 4)

    def test_empty_evidence_and_out_of_order_ooda_claims_fail_closed(self) -> None:
        self.ledger.append_event(
            "mission-1",
            "mission.started",
            "orchestrator",
            {},
        )
        empty_evidence = self._war_room_event(
            event_id="WR-EMPTY",
            event_type="observation",
            actor_id="explorer",
            summary="claim without an evidence reference",
            ooda_cycle_ref="OODA-2",
        )
        empty_evidence["evidence_refs"] = []
        self.ledger.append_event(
            "mission-1",
            "war_room.event",
            "explorer",
            empty_evidence,
        )
        blank_evidence = self._war_room_event(
            event_id="WR-BLANK",
            event_type="observation",
            actor_id="explorer",
            summary="claim with a blank evidence reference",
            ooda_cycle_ref="OODA-4",
        )
        blank_evidence["evidence_refs"] = ["   "]
        self.ledger.append_event(
            "mission-1",
            "war_room.event",
            "explorer",
            blank_evidence,
        )
        self.ledger.append_event(
            "mission-1",
            "war_room.event",
            "policy-engine",
            self._war_room_event(
                event_id="WR-JUMP",
                event_type="decision",
                actor_id="policy-engine",
                summary="decision skipped observation and orientation",
                ooda_cycle_ref="OODA-3",
            ),
        )

        room = build_war_room_projection(self.root)["war_room"]["mission_rooms"][0]
        self.assertEqual(room["status"], "inactive")
        self.assertEqual(room["ooda_phase"], "not-recorded")
        self.assertEqual(room["decision_event_sequences"], [])
        self.assertEqual(room["recent_events"], [])
        self.assertEqual(room["rejected_war_room_event_count"], 3)

    def test_room_status_is_unknown_or_closed_only_from_durable_state(self) -> None:
        unknown = build_war_room_projection(self.root)["war_room"]["mission_rooms"][0]
        self.assertEqual(unknown["status"], "unknown")

        for role in (Role.EXPLORER, Role.BUILDER, Role.CURATOR):
            self.store.mark_role("mission-1", role, "succeeded")
        self.store.mark_status("mission-1", "succeeded")
        self.ledger.append_event(
            "mission-1",
            "mission.completed",
            "orchestrator",
            {},
        )
        self.ledger.append_event(
            "mission-1",
            "war_room.event",
            "curator",
            self._war_room_event(
                event_id="WR-CLOSED",
                event_type="outcome",
                actor_id="curator",
                summary="mission independently closed",
            ),
        )
        closed = build_war_room_projection(self.root)["war_room"]["mission_rooms"][0]
        self.assertEqual(closed["status"], "closed")

    def test_unknown_projection_schema_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported projection schema"):
            build_projection(self.root, schema_version=3)

    def test_null_scalar_and_list_payloads_cannot_crash_or_forge_facts(self) -> None:
        self.ledger.append_event(
            "mission-1",
            "mission.started",
            "orchestrator",
            {},
        )
        malformed_payloads: tuple[object, ...] = (None, "scalar", ["list"])
        for payload in malformed_payloads:
            self._append_malformed_payload("untyped.event", payload)
            self._append_malformed_payload("war_room.event", payload)

        legacy = build_projection(self.root)
        self.assertEqual(legacy["schema_version"], 1)
        self.assertEqual(legacy["missions"][0]["state"], "running")
        self.assertFalse(legacy["missions"][0]["quarantined"])

        room = build_war_room_projection(self.root)["war_room"]["mission_rooms"][0]
        self.assertEqual(room["status"], "inactive")
        self.assertEqual(room["recent_events"], [])
        self.assertEqual(room["observed_actors"], [])
        self.assertEqual(room["evidence_refs"], [])
        self.assertEqual(room["rejected_war_room_event_count"], 3)


if __name__ == "__main__":
    unittest.main()
