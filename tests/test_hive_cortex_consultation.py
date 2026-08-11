from __future__ import annotations

import json
import unittest
from pathlib import Path

from hive_mind_os.brain_kernel.consultation import (
    CheatingDisposition,
    ConsultationDecision,
    ConsultationLoop,
    ConsultationReason,
    ConsultationRequest,
    RoleAssessment,
    evaluate_consultation,
    validate_consultation_document,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / ".autopilot" / "tests" / "fixtures" / "consultations"


def request(
    reason: ConsultationReason = ConsultationReason.AMBIGUOUS_DESIGN,
    *,
    round: int = 1,
    cheating: bool = False,
    authority_class: str | None = None,
) -> ConsultationRequest:
    return ConsultationRequest(
        request_id="CONSULT-test",
        mission_id="MISSION-test",
        question="What is the smallest safe next step?",
        reason_code=reason,
        requesting_role="builder",
        applicable_roles=("architect", "curator", "steward"),
        round=round,
        suspected_cheating=cheating,
        evidence_refs=("evidence:question",),
        authority_class=authority_class,
    )


def testimony(*, role: str = "architect", **kwargs: object) -> RoleAssessment:
    return RoleAssessment(
        role=role,
        identity=f"role:{role}:test",
        answer="Use the reversible option.",
        evidence_refs=("evidence:role",),
        **kwargs,
    )


class HiveCortexConsultationTests(unittest.TestCase):
    def test_role_first_resolution_tests(self) -> None:
        result = evaluate_consultation(
            request(),
            (testimony(), testimony(role="curator")),
        )
        self.assertEqual(result.decision, ConsultationDecision.RESOLVED)
        self.assertTrue(result.role_first_exhausted)
        self.assertFalse(result.human_escalation)
        self.assertEqual(len(result.identity_records), 2)
        self.assertTrue(validate_consultation_document(result.to_document()).valid)

    def test_anti_cheating_tests(self) -> None:
        confirmed = evaluate_consultation(
            request(ConsultationReason.SUSPECTED_CHEATING, cheating=True),
            (
                testimony(cheating_disposition=CheatingDisposition.CONFIRMED),
                testimony(role="curator", cheating_disposition=CheatingDisposition.CONFIRMED),
            ),
        )
        self.assertEqual(confirmed.decision, ConsultationDecision.QUARANTINE)
        self.assertEqual(confirmed.cheating_disposition, CheatingDisposition.CONFIRMED)

        disproved = evaluate_consultation(
            request(ConsultationReason.SUSPECTED_CHEATING, cheating=True),
            (
                testimony(cheating_disposition=CheatingDisposition.DISPROVED),
                testimony(role="curator", cheating_disposition=CheatingDisposition.DISPROVED),
            ),
        )
        self.assertEqual(disproved.decision, ConsultationDecision.RESOLVED)
        self.assertEqual(disproved.cheating_disposition, CheatingDisposition.DISPROVED)
        self.assertTrue(disproved.evidence_refs)

    def test_fake_human_escalation_tests(self) -> None:
        with self.assertRaises(ValueError):
            testimony(identity_kind="human")

        result = evaluate_consultation(
            request(
                ConsultationReason.MISSING_EXTERNAL_AUTHORITY,
                authority_class="credential_or_secret",
            ),
            (
                testimony(authority_required=True),
                testimony(role="curator", authority_required=True),
            ),
        )
        self.assertEqual(result.decision, ConsultationDecision.TRUE_AUTHORITY_REQUIRED)
        self.assertTrue(result.human_escalation)
        self.assertEqual(result.authority_class, "credential_or_secret")

        blocked = evaluate_consultation(
            request(ConsultationReason.MISSING_EXTERNAL_AUTHORITY),
            (testimony(authority_required=True), testimony(role="curator", authority_required=True)),
        )
        self.assertEqual(blocked.decision, ConsultationDecision.BLOCKED_EVIDENCE)
        self.assertFalse(blocked.human_escalation)

    def test_consultation_loop_tests(self) -> None:
        loop = ConsultationLoop()
        loop, first = loop.append(request(), (testimony(), testimony(role="curator")))
        self.assertEqual(len(loop.history), 1)
        self.assertEqual(first.round, 1)

        loop, second = loop.append(
            request(ConsultationReason.NO_PROGRESS, round=2),
            (testimony(proposed_decision=ConsultationDecision.REMAND), testimony(role="curator")),
        )
        self.assertEqual(second.decision, ConsultationDecision.REMAND)
        loop, third = loop.append(
            request(ConsultationReason.NO_PROGRESS, round=3),
            (testimony(), testimony(role="curator")),
        )
        self.assertTrue(loop.exhausted)
        self.assertEqual(third.decision, ConsultationDecision.QUARANTINE)
        with self.assertRaises(ValueError):
            loop.append(request(round=4), (testimony(), testimony(role="curator")))

    def test_human_escalation_requires_two_roles(self) -> None:
        with self.assertRaises(ValueError):
            evaluate_consultation(request(), (testimony(),))

    def test_schema_fixtures_round_trip(self) -> None:
        for path in sorted(FIXTURES.glob("valid-*.json")):
            with self.subTest(path=path.name):
                document = json.loads(path.read_text(encoding="utf-8"))
                validation = validate_consultation_document(document)
                self.assertTrue(validation.valid, validation.issues)


if __name__ == "__main__":
    unittest.main()
