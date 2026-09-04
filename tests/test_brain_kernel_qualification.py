from __future__ import annotations

import unittest
from dataclasses import replace

from hive_mind_os.brain_kernel.qualification import (
    EvidenceKind,
    EvidenceReceipt,
    ExecutionMode,
    IssuerAuthority,
    QualificationDisposition,
    QualificationLevel,
    QualificationRequest,
    qualify_claim,
)

NOW = "2026-09-03T20:00:00Z"
FRESH = "2026-09-03T19:00:00Z"
EXPIRES = "2026-09-04T20:00:00Z"


def digest(number: int) -> str:
    return f"sha256:{number:064x}"


ALL_KINDS = tuple(EvidenceKind)
LOCAL_AUTHORITY = IssuerAuthority(
    issuer_id="local-curator",
    trust_domain="candidate-lab",
    evidence_kinds=ALL_KINDS,
)
EXTERNAL_AUTHORITY = IssuerAuthority(
    issuer_id="external-curator",
    trust_domain="independent-lab",
    evidence_kinds=ALL_KINDS,
)


def request(level: QualificationLevel) -> QualificationRequest:
    return QualificationRequest(
        claim_id="CLAIM-agent-can-code-and-qa",
        candidate_digest=digest(1),
        candidate_trust_domain="candidate-lab",
        target_level=level,
        as_of=NOW,
    )


def receipt(
    kind: EvidenceKind,
    number: int,
    **changes: object,
) -> EvidenceReceipt:
    modes = {
        EvidenceKind.STRUCTURAL: ExecutionMode.STATIC,
        EvidenceKind.BOUNDED_LOCAL: ExecutionMode.LOCAL,
        EvidenceKind.CONTROL_PLANE: ExecutionMode.LOCAL,
        EvidenceKind.FULL_SUITE: ExecutionMode.LOCAL,
        EvidenceKind.PROVIDER_BACKED: ExecutionMode.PROVIDER,
        EvidenceKind.INDEPENDENT_E2E: ExecutionMode.PROVIDER,
        EvidenceKind.PRODUCTION: ExecutionMode.PRODUCTION,
        EvidenceKind.SUPERIORITY: ExecutionMode.PROVIDER,
    }
    external = kind in {
        EvidenceKind.INDEPENDENT_E2E,
        EvidenceKind.PRODUCTION,
        EvidenceKind.SUPERIORITY,
    }
    values: dict[str, object] = {
        "receipt_id": f"RECEIPT-{number}",
        "claim_id": "CLAIM-agent-can-code-and-qa",
        "candidate_digest": digest(1),
        "evidence_kind": kind,
        "passed": True,
        "issuer_id": "external-curator" if external else "local-curator",
        "issuer_trust_domain": ("independent-lab" if external else "candidate-lab"),
        "observed_at": FRESH,
        "expires_at": EXPIRES,
        "artifact_digest": digest(1000 + number),
        "execution_mode": modes[kind],
        "strict": kind in {EvidenceKind.CONTROL_PLANE, EvidenceKind.FULL_SUITE},
        "score": 73.0,
    }
    if kind is EvidenceKind.SUPERIORITY:
        values.update(
            comparator_digest=digest(20),
            budget_digest=digest(30),
            run_id=f"RUN-{number}",
        )
    values.update(changes)
    return EvidenceReceipt(**values)  # type: ignore[arg-type]


def bounded_receipts() -> tuple[EvidenceReceipt, ...]:
    return (
        receipt(EvidenceKind.STRUCTURAL, 1),
        receipt(EvidenceKind.BOUNDED_LOCAL, 2),
        receipt(EvidenceKind.CONTROL_PLANE, 3),
        receipt(EvidenceKind.FULL_SUITE, 4),
    )


def production_receipts() -> tuple[EvidenceReceipt, ...]:
    return bounded_receipts() + (
        receipt(EvidenceKind.PROVIDER_BACKED, 5),
        receipt(EvidenceKind.INDEPENDENT_E2E, 6),
        receipt(EvidenceKind.PRODUCTION, 7),
    )


class QualificationTests(unittest.TestCase):
    authorities = (LOCAL_AUTHORITY, EXTERNAL_AUTHORITY)

    def qualify(
        self,
        level: QualificationLevel,
        receipts: tuple[EvidenceReceipt, ...],
        authorities: tuple[IssuerAuthority, ...] | None = None,
    ):
        return qualify_claim(
            request(level),
            receipts,
            authorities if authorities is not None else self.authorities,
        )

    def test_bounded_local_is_an_attainable_adoption_level(self) -> None:
        decision = self.qualify(QualificationLevel.BOUNDED_LOCAL, bounded_receipts())
        self.assertTrue(decision.qualified)
        self.assertEqual(QualificationDisposition.ADOPT, decision.disposition)
        self.assertEqual(QualificationLevel.BOUNDED_LOCAL, decision.achieved_level)
        self.assertEqual((), decision.failures)
        self.assertEqual((), decision.missing_requirements)

    def test_numeric_scores_never_compensate_for_missing_hard_evidence(self) -> None:
        structural = replace(receipt(EvidenceKind.STRUCTURAL, 1), score=100.0)
        provider = replace(receipt(EvidenceKind.PROVIDER_BACKED, 5), score=100.0)
        decision = self.qualify(
            QualificationLevel.PROVIDER_BACKED, (structural, provider)
        )
        self.assertFalse(decision.qualified)
        self.assertEqual(QualificationDisposition.DEFER, decision.disposition)
        self.assertEqual(QualificationLevel.STRUCTURAL, decision.achieved_level)
        self.assertEqual(100.0, decision.informational_score)
        self.assertIn(
            "bounded_local:real_local_execution", decision.missing_requirements
        )

    def test_claim_and_candidate_bindings_fail_closed(self) -> None:
        changes = (
            {"claim_id": "CLAIM-other"},
            {"candidate_digest": digest(999)},
        )
        for change in changes:
            with self.subTest(change=change):
                forged = replace(receipt(EvidenceKind.STRUCTURAL, 1), **change)
                decision = self.qualify(QualificationLevel.STRUCTURAL, (forged,))
                self.assertFalse(decision.qualified)
                self.assertEqual(
                    QualificationDisposition.QUARANTINE, decision.disposition
                )
                self.assertEqual((forged.receipt_id,), decision.rejected_receipt_ids)

    def test_untrusted_issuer_domain_and_kind_bindings_fail_closed(self) -> None:
        structural = receipt(EvidenceKind.STRUCTURAL, 1)
        cases = (
            (
                replace(structural, issuer_id="unknown"),
                self.authorities,
                "not trusted",
            ),
            (
                replace(structural, issuer_trust_domain="forged-domain"),
                self.authorities,
                "trust-domain",
            ),
            (
                structural,
                (
                    IssuerAuthority(
                        issuer_id="local-curator",
                        trust_domain="candidate-lab",
                        evidence_kinds=(EvidenceKind.FULL_SUITE,),
                    ),
                ),
                "evidence kind",
            ),
        )
        for forged, authorities, message in cases:
            with self.subTest(message=message):
                decision = self.qualify(
                    QualificationLevel.STRUCTURAL, (forged,), authorities
                )
                self.assertEqual(
                    QualificationDisposition.QUARANTINE, decision.disposition
                )
                self.assertTrue(any(message in item for item in decision.failures))

    def test_future_stale_and_expired_evidence_fail_closed(self) -> None:
        structural = receipt(EvidenceKind.STRUCTURAL, 1)
        cases = (
            replace(
                structural,
                observed_at="2026-09-03T21:00:00Z",
                expires_at="2026-09-04T21:00:00Z",
            ),
            replace(
                structural,
                observed_at="2026-07-01T00:00:00Z",
                expires_at=EXPIRES,
            ),
            replace(
                structural,
                observed_at="2026-09-01T00:00:00Z",
                expires_at="2026-09-02T00:00:00Z",
            ),
        )
        for stale in cases:
            with self.subTest(receipt=stale):
                decision = self.qualify(QualificationLevel.STRUCTURAL, (stale,))
                self.assertEqual(
                    QualificationDisposition.QUARANTINE, decision.disposition
                )
                self.assertEqual((stale.receipt_id,), decision.rejected_receipt_ids)

    def test_fixture_test_double_and_local_cannot_claim_provider_backing(self) -> None:
        for mode in (
            ExecutionMode.FIXTURE,
            ExecutionMode.TEST_DOUBLE,
            ExecutionMode.LOCAL,
        ):
            with self.subTest(mode=mode):
                provider = replace(
                    receipt(EvidenceKind.PROVIDER_BACKED, 5), execution_mode=mode
                )
                decision = self.qualify(
                    QualificationLevel.PROVIDER_BACKED,
                    bounded_receipts() + (provider,),
                )
                self.assertEqual(
                    QualificationDisposition.QUARANTINE, decision.disposition
                )
                self.assertIn(provider.receipt_id, decision.rejected_receipt_ids)

    def test_fixture_cannot_satisfy_bounded_execution_or_strict_gates(self) -> None:
        for kind in (
            EvidenceKind.BOUNDED_LOCAL,
            EvidenceKind.CONTROL_PLANE,
            EvidenceKind.FULL_SUITE,
        ):
            with self.subTest(kind=kind):
                evidence = tuple(
                    replace(item, execution_mode=ExecutionMode.FIXTURE)
                    if item.evidence_kind is kind
                    else item
                    for item in bounded_receipts()
                )
                decision = self.qualify(QualificationLevel.BOUNDED_LOCAL, evidence)
                self.assertEqual(
                    QualificationDisposition.QUARANTINE, decision.disposition
                )

    def test_same_trust_domain_blocks_independent_e2e(self) -> None:
        same_domain = replace(
            receipt(EvidenceKind.INDEPENDENT_E2E, 6),
            issuer_id="local-curator",
            issuer_trust_domain="candidate-lab",
        )
        evidence = bounded_receipts() + (
            receipt(EvidenceKind.PROVIDER_BACKED, 5),
            same_domain,
        )
        decision = self.qualify(QualificationLevel.INDEPENDENT_E2E, evidence)
        self.assertEqual(QualificationDisposition.QUARANTINE, decision.disposition)
        self.assertTrue(
            any("share a trust domain" in item for item in decision.failures)
        )

    def test_separate_trust_domain_can_reach_independent_e2e(self) -> None:
        evidence = bounded_receipts() + (
            receipt(EvidenceKind.PROVIDER_BACKED, 5),
            receipt(EvidenceKind.INDEPENDENT_E2E, 6),
        )
        decision = self.qualify(QualificationLevel.INDEPENDENT_E2E, evidence)
        self.assertTrue(decision.qualified)
        self.assertEqual(QualificationLevel.INDEPENDENT_E2E, decision.achieved_level)

    def test_failed_strict_control_plane_or_full_suite_quarantines(self) -> None:
        for kind in (EvidenceKind.CONTROL_PLANE, EvidenceKind.FULL_SUITE):
            with self.subTest(kind=kind):
                evidence = tuple(
                    replace(item, passed=False, score=100.0)
                    if item.evidence_kind is kind
                    else item
                    for item in bounded_receipts()
                )
                decision = self.qualify(QualificationLevel.BOUNDED_LOCAL, evidence)
                self.assertEqual(
                    QualificationDisposition.QUARANTINE, decision.disposition
                )
                self.assertFalse(decision.qualified)
                self.assertTrue(any("failed strict" in x for x in decision.failures))

    def test_adverse_receipt_cannot_be_compensated_by_a_passing_receipt(self) -> None:
        passing = replace(receipt(EvidenceKind.STRUCTURAL, 1), score=100.0)
        adverse = replace(
            receipt(EvidenceKind.STRUCTURAL, 2),
            passed=False,
            score=0.0,
        )

        decision = self.qualify(
            QualificationLevel.STRUCTURAL,
            (passing, adverse),
        )

        self.assertFalse(decision.qualified)
        self.assertEqual(QualificationDisposition.QUARANTINE, decision.disposition)
        self.assertEqual(QualificationLevel.STRUCTURAL, decision.achieved_level)
        self.assertEqual((), decision.missing_requirements)
        self.assertEqual((passing.receipt_id,), decision.accepted_receipt_ids)
        self.assertEqual((adverse.receipt_id,), decision.rejected_receipt_ids)
        self.assertTrue(
            any("adverse structural evidence" in item for item in decision.failures)
        )

    def test_superiority_requires_two_equal_budget_repeated_comparators(self) -> None:
        comparisons = (
            receipt(EvidenceKind.SUPERIORITY, 20),
            receipt(EvidenceKind.SUPERIORITY, 21),
            receipt(
                EvidenceKind.SUPERIORITY,
                22,
                comparator_digest=digest(21),
            ),
            receipt(
                EvidenceKind.SUPERIORITY,
                23,
                comparator_digest=digest(21),
                execution_mode=ExecutionMode.PRODUCTION,
            ),
        )
        decision = self.qualify(
            QualificationLevel.SUPERIORITY,
            production_receipts() + comparisons,
        )
        self.assertTrue(decision.qualified)
        self.assertEqual(QualificationLevel.SUPERIORITY, decision.achieved_level)
        self.assertEqual(QualificationDisposition.ADOPT, decision.disposition)

    def test_superiority_requires_independent_provider_or_production_evidence(
        self,
    ) -> None:
        valid = (
            receipt(EvidenceKind.SUPERIORITY, 20),
            receipt(EvidenceKind.SUPERIORITY, 21),
            receipt(
                EvidenceKind.SUPERIORITY,
                22,
                comparator_digest=digest(21),
            ),
            receipt(
                EvidenceKind.SUPERIORITY,
                23,
                comparator_digest=digest(21),
            ),
        )
        cases = tuple(
            (
                replace(valid[0], execution_mode=mode),
                "provider or production execution",
            )
            for mode in (
                ExecutionMode.FIXTURE,
                ExecutionMode.TEST_DOUBLE,
                ExecutionMode.LOCAL,
            )
        ) + (
            (
                replace(
                    valid[0],
                    issuer_id="local-curator",
                    issuer_trust_domain="candidate-lab",
                ),
                "share a trust domain",
            ),
        )
        for invalid, expected_failure in cases:
            with self.subTest(
                execution_mode=invalid.execution_mode,
                issuer_trust_domain=invalid.issuer_trust_domain,
            ):
                decision = self.qualify(
                    QualificationLevel.SUPERIORITY,
                    production_receipts() + (invalid,) + valid[1:],
                )
                self.assertFalse(decision.qualified)
                self.assertEqual(
                    QualificationDisposition.QUARANTINE,
                    decision.disposition,
                )
                self.assertIn(invalid.receipt_id, decision.rejected_receipt_ids)
                self.assertTrue(
                    any(expected_failure in item for item in decision.failures)
                )

    def test_one_comparator_or_nonrepeated_receipts_cannot_reach_superiority(
        self,
    ) -> None:
        one_comparator = (
            receipt(EvidenceKind.SUPERIORITY, 20),
            receipt(EvidenceKind.SUPERIORITY, 21),
        )
        repeated_run = (
            receipt(EvidenceKind.SUPERIORITY, 30, run_id="SAME-RUN"),
            receipt(EvidenceKind.SUPERIORITY, 31, run_id="SAME-RUN"),
            receipt(
                EvidenceKind.SUPERIORITY,
                32,
                comparator_digest=digest(21),
                run_id="SAME-RUN-2",
            ),
            receipt(
                EvidenceKind.SUPERIORITY,
                33,
                comparator_digest=digest(21),
                run_id="SAME-RUN-2",
            ),
        )
        duplicate_artifacts = tuple(
            replace(item, artifact_digest=digest(888)) for item in repeated_run
        )
        for comparisons in (one_comparator, repeated_run, duplicate_artifacts):
            with self.subTest(comparisons=comparisons):
                decision = self.qualify(
                    QualificationLevel.SUPERIORITY,
                    production_receipts() + comparisons,
                )
                self.assertFalse(decision.qualified)
                self.assertEqual(QualificationDisposition.DEFER, decision.disposition)
                self.assertEqual(QualificationLevel.PRODUCTION, decision.achieved_level)

    def test_unequal_budget_or_self_comparison_quarantines_superiority(self) -> None:
        valid = (
            receipt(EvidenceKind.SUPERIORITY, 20),
            receipt(EvidenceKind.SUPERIORITY, 21),
            receipt(
                EvidenceKind.SUPERIORITY,
                22,
                comparator_digest=digest(21),
            ),
            receipt(
                EvidenceKind.SUPERIORITY,
                23,
                comparator_digest=digest(21),
            ),
        )
        cases = (
            valid[:-1] + (replace(valid[-1], budget_digest=digest(31)),),
            (replace(valid[0], comparator_digest=digest(1)),) + valid[1:],
        )
        for comparisons in cases:
            with self.subTest(comparisons=comparisons):
                decision = self.qualify(
                    QualificationLevel.SUPERIORITY,
                    production_receipts() + comparisons,
                )
                self.assertEqual(
                    QualificationDisposition.QUARANTINE, decision.disposition
                )

    def test_duplicate_receipts_quarantine_and_evaluation_is_pure(self) -> None:
        structural = receipt(EvidenceKind.STRUCTURAL, 1)
        duplicate = self.qualify(
            QualificationLevel.STRUCTURAL, (structural, structural)
        )
        self.assertEqual(QualificationDisposition.QUARANTINE, duplicate.disposition)
        self.assertEqual((structural.receipt_id,), duplicate.rejected_receipt_ids)

        first = self.qualify(QualificationLevel.BOUNDED_LOCAL, bounded_receipts())
        second = self.qualify(
            QualificationLevel.BOUNDED_LOCAL,
            tuple(reversed(bounded_receipts())),
        )
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
