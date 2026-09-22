import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hive_mind_os.whole_os_qualification import (
    REQUIRED_ROBLOX_RUNTIME_CHECKS,
    Disposition,
    EvidenceKind,
    EvidenceRef,
    ExternalObligation,
    PilotAttempt,
    PilotReport,
    PilotRuntimeEvidence,
    QualificationClaimScope,
    QualificationLedger,
    canonical_digest,
)


class WholeOSQualificationTests(unittest.TestCase):
    @staticmethod
    def receipt(subject: str, label: str, observed_at: int = 0) -> EvidenceRef:
        return EvidenceRef(
            f"receipt:{label}",
            canonical_digest(label),
            EvidenceKind.EXTERNAL_RECEIPT,
            subject,
            observed_at,
        )

    def attempt(
        self,
        attempt_id: str,
        subject: str,
        family: str,
        *,
        domain: str | None = None,
        runtime: bool = False,
        hive_free: bool | None = None,
    ) -> PilotAttempt:
        runtime_evidence = tuple(
            PilotRuntimeEvidence(
                check,
                self.receipt(subject, f"{attempt_id}-{check}"),
            )
            for check in sorted(REQUIRED_ROBLOX_RUNTIME_CHECKS)
        ) if runtime else ()
        return PilotAttempt(
            attempt_id,
            subject,
            family,
            "sha256:" + "a" * 64,
            "accepted",
            self.receipt(subject, f"delivery-{attempt_id}"),
            1,
            2,
            1,
            domain,
            runtime_evidence,
            hive_free,
        )

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

    def test_self_pilot_requires_three_distinct_change_families(self):
        attempts = (
            self.attempt("one", "self", "same"),
            self.attempt("two", "self", "same"),
            self.attempt("three", "self", "different"),
        )
        report = PilotReport(
            "pilot",
            "self",
            "sha256:" + "a" * 64,
            0,
            259200,
            attempts,
            True,
            0,
            0,
            self.receipt("pilot", "rollback"),
            restart_evidence=self.receipt("pilot", "restart"),
            observation_evidence=self.receipt("pilot", "observation", 259200),
            subject_ids=("self",),
            production_candidate=self.receipt(
                "sha256:" + "a" * 64, "production-self"
            ),
            benchmark_candidate=self.receipt(
                "sha256:" + "a" * 64, "benchmark-self"
            ),
        )
        self.assertEqual(report.disposition(), Disposition.DEFER)

    def test_external_pilot_accepts_two_declared_non_roblox_targets(self):
        coupon = self.attempt(
            "coupon-one", "coupon-hive", "feature", domain="web", hive_free=True
        )
        rainbow = self.attempt(
            "rainbow-one",
            "reeses-rainbow-web",
            "failure",
            domain="web",
            hive_free=True,
        )
        candidate = "sha256:" + "a" * 64
        report = PilotReport(
            "pilot",
            "external",
            candidate,
            0,
            259200,
            (coupon, rainbow),
            True,
            0,
            0,
            self.receipt("pilot", "rollback"),
            restart_evidence=self.receipt("pilot", "restart-external"),
            observation_evidence=self.receipt(
                "pilot", "observation-external", 259200
            ),
            subject_ids=("coupon-hive", "reeses-rainbow-web"),
            claim_scope=QualificationClaimScope.BOUNDED_OPERATIONAL_PRODUCTION,
            production_candidate=self.receipt(candidate, "production-external"),
        )
        self.assertEqual(report.disposition(), Disposition.ADOPT)
        self.assertEqual(
            replace(
                report,
                claim_scope=QualificationClaimScope.FULL_AUTONOMY_OR_SUPERIORITY,
            ).disposition(),
            Disposition.DEFER,
        )
        self.assertEqual(
            replace(
                report,
                claim_scope=QualificationClaimScope.FULL_AUTONOMY_OR_SUPERIORITY,
                benchmark_candidate=self.receipt(candidate, "benchmark-external"),
            ).disposition(),
            Disposition.ADOPT,
        )
        self.assertEqual(
            replace(report, attempts=(coupon,)).disposition(), Disposition.DEFER
        )
        self.assertEqual(
            replace(report, rollback_evidence=None).disposition(), Disposition.DEFER
        )
        self.assertEqual(
            replace(
                report,
                observation_evidence=self.receipt(
                    "pilot", "stale-observation", 259199
                ),
            ).disposition(),
            Disposition.DEFER,
        )
        self.assertEqual(
            replace(report, ended_at=259199).disposition(), Disposition.DEFER
        )


if __name__ == "__main__":
    unittest.main()
