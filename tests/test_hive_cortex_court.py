from __future__ import annotations

import unittest

from hive_mind_os.brain_kernel.court_runtime import (
    CourtBrief,
    CourtCase,
    CourtClaimKind,
    CourtDisposition,
    CourtHistory,
    CourtParticipant,
    CourtProtocolError,
    CourtSeat,
    CourtVerdict,
    record_case,
)


def participant(seat: CourtSeat, identity: str, task: str) -> CourtParticipant:
    return CourtParticipant(seat, identity, task)


def briefs(*, same_task: bool = False) -> tuple[CourtBrief, ...]:
    advocate_task = "present the strongest supported case"
    cross_task = advocate_task if same_task else "find contradictions and counterexamples"
    return (
        CourtBrief(participant(CourtSeat.ADVOCATE, "advocate-1", advocate_task), "supported", ("evidence:1",)),
        CourtBrief(participant(CourtSeat.CROSS_EXAMINER, "cross-1", cross_task), "challenged", ("evidence:2",), dissent="risk remains"),
        CourtBrief(participant(CourtSeat.EXPERT_WITNESS, "expert-1", "assess evidence quality"), "reproduced", ("evidence:3",)),
        CourtBrief(participant(CourtSeat.JUDGE, "judge-1", "weigh the retained record"), "decide", ("evidence:4",)),
    )


def case(kind: CourtClaimKind = CourtClaimKind.ORDINARY, *, affected: tuple[str, ...] = ()) -> CourtCase:
    return CourtCase("COURT-test", kind, "A bounded proposition", affected)


def verdict(disposition: CourtDisposition = CourtDisposition.ADOPT) -> CourtVerdict:
    return CourtVerdict("COURT-test", disposition, "judge-1", ("burden met",), ("evidence:1",), ("record dissent",))


def appeal_briefs() -> tuple[CourtBrief, ...]:
    return (*briefs(), CourtBrief(participant(CourtSeat.APPEALS_JUDGE, "appeals-1", "review new evidence and procedure"), "appeal decision", ("evidence:new",)))


class HiveCortexCourtTests(unittest.TestCase):
    def test_court_identity_separation_tests(self) -> None:
        with self.assertRaisesRegex(CourtProtocolError, "distinct tasks"):
            record_case(CourtHistory(), case(), briefs(same_task=True), verdict())

        with self.assertRaisesRegex(CourtProtocolError, "affected generator"):
            record_case(CourtHistory(), case(affected=("judge-1",)), briefs(), verdict())

        history = record_case(CourtHistory(), case(), briefs(), verdict())
        self.assertEqual(len(history.records), 1)

    def test_dissent_retention_tests(self) -> None:
        first = record_case(CourtHistory(), case(), briefs(), verdict(CourtDisposition.REJECT))
        appeal_case = CourtCase("COURT-appeal", CourtClaimKind.ORDINARY, "new evidence", ())
        appeal_verdict = CourtVerdict("COURT-appeal", CourtDisposition.ADAPT, "appeals-1", ("new evidence considered",), ("evidence:new",))
        history = record_case(first, appeal_case, appeal_briefs(), appeal_verdict, appeal_of="COURT-test")
        self.assertEqual(len(history.records), 2)
        self.assertIn("risk remains", history.dissent)
        self.assertIn("record dissent", history.dissent)
        with self.assertRaisesRegex(CourtProtocolError, "cannot be replaced"):
            record_case(history, case(), briefs(), verdict(CourtDisposition.REJECT))

    def test_friendly_reviewer_attack_tests(self) -> None:
        with self.assertRaisesRegex(CourtProtocolError, "distinct identity"):
            bad = list(briefs())
            bad[1] = CourtBrief(participant(CourtSeat.CROSS_EXAMINER, "advocate-1", "challenge"), "friendly", ("evidence:2",))
            record_case(CourtHistory(), case(CourtClaimKind.CHEATING), bad, verdict())

        with self.assertRaisesRegex(CourtProtocolError, "affected generator"):
            record_case(CourtHistory(), case(CourtClaimKind.SUPERIORITY, affected=("judge-1",)), briefs(), verdict())


if __name__ == "__main__":
    unittest.main()
