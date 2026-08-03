from __future__ import annotations

import unittest

from hive_mind_os.package_system import (
    OODAContractValidation,
    OODAPhase,
    OODAState,
    OODAStatus,
    OODATerminalRecord,
    OODATransition,
    validate_ooda_contract,
)


def _transition(
    sequence: int,
    from_phase: OODAPhase,
    to_phase: OODAPhase,
    **overrides: str | None,
) -> OODATransition:
    values: dict[str, object] = {
        "sequence": sequence,
        "from_phase": from_phase,
        "to_phase": to_phase,
        "actor_id": "actor-independent",
        "occurred_at": "2026-07-28T12:00:00Z",
        "evidence_refs": (f"evidence:{sequence}",),
        "decision_ref": None,
        "policy_decision_ref": None,
        "action_intent_ref": None,
        "action_receipt_ref": None,
        "outcome_ref": None,
    }
    values.update(overrides)
    return OODATransition(**values)  # type: ignore[arg-type]


class OODAWorkflowTests(unittest.TestCase):
    def test_replay_enforces_the_evidence_bound_cycle(self) -> None:
        state = OODAState.initial(cycle_id="OODA-1", mission_id="MISSION-1")
        state = state.apply(_transition(1, OODAPhase.OBSERVE, OODAPhase.ORIENT))
        state = state.apply(_transition(2, OODAPhase.ORIENT, OODAPhase.DECIDE))
        state = state.apply(
            _transition(
                3,
                OODAPhase.DECIDE,
                OODAPhase.ACT,
                decision_ref="decision:3",
                policy_decision_ref="policy:3",
                action_intent_ref="intent:3",
            )
        )
        state = state.apply(
            _transition(
                4,
                OODAPhase.ACT,
                OODAPhase.OBSERVE,
                action_receipt_ref="receipt:4",
                outcome_ref="outcome:4",
            )
        )
        assert state.iteration == 2
        assert state.phase is OODAPhase.OBSERVE
        assert state.sequence == 4
        assert state.to_contract()["last_transition"]["outcome_ref"] == "outcome:4"

    def test_illegal_act_and_sequence_transitions_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "entering act requires"):
            _transition(1, OODAPhase.DECIDE, OODAPhase.ACT)
        with self.assertRaisesRegex(ValueError, "action receipt"):
            _transition(1, OODAPhase.ACT, OODAPhase.OBSERVE)
        with self.assertRaisesRegex(ValueError, "illegal OODA"):
            _transition(1, OODAPhase.OBSERVE, OODAPhase.DECIDE)

        state = OODAState.initial(cycle_id="OODA-2", mission_id="MISSION-2")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            state.apply(_transition(2, OODAPhase.OBSERVE, OODAPhase.ORIENT))

    def test_stop_is_terminal_and_records_an_outcome(self) -> None:
        state = OODAState.initial(cycle_id="OODA-3", mission_id="MISSION-3")
        state = state.apply(_transition(1, OODAPhase.OBSERVE, OODAPhase.ORIENT))
        stopped = state.stop(
            status=OODAStatus.BLOCKED,
            actor_id="curator-independent",
            occurred_at="2026-07-28T12:01:00Z",
            evidence_refs=("evidence:terminal",),
            outcome_ref="outcome:blocked",
            reason="source evidence is incomplete",
        )
        assert stopped.status is OODAStatus.BLOCKED
        assert stopped.stop_reason == "source evidence is incomplete"
        assert stopped.last_transition is not None
        assert stopped.last_transition.outcome_ref is None
        assert stopped.terminal_record is not None
        assert stopped.terminal_record.outcome_ref == "outcome:blocked"
        assert stopped.terminal_record.sequence == 2
        assert stopped.sequence == 2
        contract = stopped.to_contract()
        validation = validate_ooda_contract(contract)
        assert isinstance(validation, OODAContractValidation)
        assert validation.valid, validation.issues
        with self.assertRaisesRegex(ValueError, "stopped"):
            stopped.apply(_transition(2, OODAPhase.ORIENT, OODAPhase.DECIDE))

    def test_initial_state_can_stop_without_losing_terminal_evidence(self) -> None:
        stopped = OODAState.initial(
            cycle_id="OODA-INITIAL-STOP",
            mission_id="MISSION-INITIAL-STOP",
        ).stop(
            status=OODAStatus.FAILED,
            actor_id="curator-independent",
            occurred_at="2026-07-28T12:01:00+00:00",
            evidence_refs=("evidence:failure",),
            outcome_ref="outcome:failed",
            reason="evidence gate failed",
        )
        assert stopped.last_transition is None
        assert stopped.sequence == 1
        assert stopped.terminal_record is not None
        assert stopped.terminal_record.outcome_ref == "outcome:failed"
        assert validate_ooda_contract(stopped.to_contract()).valid

    def test_timestamps_and_terminal_records_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "RFC 3339"):
            _transition(
                1,
                OODAPhase.OBSERVE,
                OODAPhase.ORIENT,
                occurred_at="2026-07-28 12:00:00",
            )
        with self.assertRaisesRegex(ValueError, "must be terminal"):
            OODATerminalRecord(
                sequence=1,
                status=OODAStatus.RUNNING,
                actor_id="curator",
                occurred_at="2026-07-28T12:00:00Z",
                evidence_refs=("evidence:terminal",),
                outcome_ref="outcome:invalid",
                reason="cannot stop as running",
            )

    def test_contract_validator_rejects_forged_cross_field_state(self) -> None:
        state = OODAState.initial(cycle_id="OODA-FORGED", mission_id="MISSION-FORGED")
        state = state.apply(_transition(1, OODAPhase.OBSERVE, OODAPhase.ORIENT))
        forged = state.to_contract()
        forged["phase"] = "decide"
        result = validate_ooda_contract(forged)
        assert not result.valid
        assert "state phase does not match the last transition" in result.issues

        forged_terminal = state.to_contract()
        forged_terminal["status"] = "blocked"
        forged_terminal["stop_reason"] = "invented"
        result = validate_ooda_contract(forged_terminal)
        assert not result.valid
        assert "terminal state requires a terminal record" in result.issues
