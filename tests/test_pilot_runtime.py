import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hive_mind_os.pilot_runtime import (
    PilotBlockerCode,
    PilotController,
    PilotPlan,
    PilotPrerequisites,
    PilotStore,
)
from hive_mind_os.whole_os_qualification import (
    Disposition,
    EvidenceKind,
    EvidenceRef,
    ExternalObligation,
    PilotAttempt,
    QualificationClaimScope,
    canonical_digest,
)

D = "sha256:" + "a" * 64


class PilotRuntimeTests(unittest.TestCase):
    @staticmethod
    def evidence(subject: str, label: str) -> EvidenceRef:
        return EvidenceRef(
            f"receipt:{label}",
            canonical_digest(label),
            EvidenceKind.EXTERNAL_RECEIPT,
            subject,
            0,
        )

    def prerequisites(self, *subjects: str) -> PilotPrerequisites:
        return PilotPrerequisites(
            self.evidence(D, "host"),
            self.evidence("pilot", "supervisor"),
            self.evidence("pilot", "authority"),
            self.evidence(D, "benchmark"),
            tuple(self.evidence(subject, f"target-{subject}") for subject in subjects),
            tuple(self.evidence(subject, f"runtime-{subject}") for subject in subjects),
            self.evidence(D, "production"),
        )

    def test_fresh_pilot_retains_typed_missing_prerequisite_blockers(self):
        with TemporaryDirectory() as root:
            plan = PilotPlan("pilot", "self", D, ("subject",), 0, 259200, 1, 100, 4, D)
            controller = PilotController(PilotStore(Path(root)), plan)
            report = controller.report()
            self.assertEqual(report.elapsed_seconds, 0)
            self.assertEqual(report.disposition(), Disposition.BLOCKED_AUTHORITY)
            self.assertEqual(
                {item.obligation_id for item in report.obligations},
                {
                    PilotBlockerCode.MISSING_WHOLE_OS_HOST,
                    PilotBlockerCode.MISSING_SUPERVISOR,
                    PilotBlockerCode.MISSING_AUTHORITY,
                    PilotBlockerCode.MISSING_BENCHMARK,
                    PilotBlockerCode.MISSING_PRODUCTION_CANDIDATE,
                },
            )

    def test_observation_watermark_is_monotonic_and_bounded(self):
        with TemporaryDirectory() as root:
            plan = PilotPlan(
                "pilot",
                "self",
                D,
                ("subject",),
                10,
                259210,
                1,
                100,
                4,
                canonical_digest("authority"),
                self.prerequisites(),
            )
            controller = PilotController(PilotStore(Path(root)), plan)
            controller.record_observation(20)
            self.assertEqual(controller.report().ended_at, 20)
            with self.assertRaisesRegex(ValueError, "backward"):
                controller.record_observation(19)
            with self.assertRaisesRegex(ValueError, "planned window"):
                controller.record_observation(259211)

    def test_retries_reconcile_one_external_obligation(self):
        with TemporaryDirectory() as root:
            plan = PilotPlan("pilot", "external", D, ("subject",), 0, 259200, 1, 100, 4, D)
            controller = PilotController(PilotStore(Path(root)), plan)
            obligation = ExternalObligation(
                "runtime",
                Disposition.BLOCKED_CAPABILITY,
                "runtime unavailable",
                ("R14",),
            )
            controller.record_controls(obligations=(obligation,))
            controller.record_controls(obligations=(obligation,))
            self.assertIn(obligation, controller.report().obligations)
            changed = ExternalObligation(
                "runtime",
                Disposition.BLOCKED_CAPABILITY,
                "different content",
                ("R14",),
            )
            with self.assertRaisesRegex(ValueError, "different content"):
                controller.record_controls(obligations=(changed,))

    def test_external_pilot_names_missing_targets_and_runtime(self):
        with TemporaryDirectory() as root:
            plan = PilotPlan(
                "pilot",
                "external",
                D,
                ("ordinary", "game"),
                0,
                259200,
                2,
                10,
                2,
                canonical_digest("authority"),
                PilotPrerequisites(
                    self.evidence(D, "host"),
                    None,
                    self.evidence("pilot", "authority"),
                    self.evidence(D, "benchmark"),
                    production_candidate=self.evidence(D, "production"),
                ),
                QualificationClaimScope.BOUNDED_OPERATIONAL_PRODUCTION,
            )
            report = PilotController(PilotStore(Path(root)), plan).report()
            self.assertEqual(
                {item.obligation_id for item in report.obligations},
                {
                    PilotBlockerCode.MISSING_TARGETS,
                    PilotBlockerCode.MISSING_RUNTIME,
                },
            )

    def test_external_pilot_accepts_two_non_roblox_target_receipts(self):
        with TemporaryDirectory() as root:
            prerequisites = replace(
                self.prerequisites("coupon-hive", "reeses-rainbow-web"),
                benchmark_candidate=None,
            )
            plan = PilotPlan(
                "pilot",
                "external",
                D,
                ("coupon-hive", "reeses-rainbow-web"),
                0,
                259200,
                2,
                10,
                2,
                canonical_digest("authority"),
                prerequisites,
                QualificationClaimScope.BOUNDED_OPERATIONAL_PRODUCTION,
            )
            report = PilotController(PilotStore(Path(root)), plan).report()
            self.assertFalse(report.obligations)

    def test_full_autonomy_still_requires_n30_and_benchmark_cannot_replace_production(self):
        subjects = ("coupon-hive", "reeses-rainbow-web")
        complete = self.prerequisites(*subjects)
        bounded_without_production = replace(
            complete,
            production_candidate=None,
        )
        with TemporaryDirectory() as root:
            plan = PilotPlan(
                "pilot",
                "external",
                D,
                subjects,
                0,
                259200,
                2,
                10,
                2,
                canonical_digest("authority"),
                bounded_without_production,
                QualificationClaimScope.BOUNDED_OPERATIONAL_PRODUCTION,
            )
            obligations = PilotController(PilotStore(Path(root)), plan).report().obligations
            self.assertEqual(
                {item.obligation_id for item in obligations},
                {PilotBlockerCode.MISSING_PRODUCTION_CANDIDATE},
            )

        with TemporaryDirectory() as root:
            plan = PilotPlan(
                "pilot",
                "external",
                D,
                subjects,
                0,
                259200,
                2,
                10,
                2,
                canonical_digest("authority"),
                replace(complete, benchmark_candidate=None),
                QualificationClaimScope.FULL_AUTONOMY_OR_SUPERIORITY,
            )
            obligations = PilotController(PilotStore(Path(root)), plan).report().obligations
            self.assertEqual(
                {item.obligation_id for item in obligations},
                {PilotBlockerCode.MISSING_BENCHMARK},
            )

    def test_external_runtime_receipts_cover_every_declared_subject(self):
        subjects = ("coupon-hive", "reeses-rainbow-web")
        prerequisites = replace(
            self.prerequisites(*subjects),
            benchmark_candidate=None,
            runtime=(self.evidence("coupon-hive", "runtime-coupon-hive"),),
        )
        with TemporaryDirectory() as root:
            plan = PilotPlan(
                "pilot",
                "external",
                D,
                subjects,
                0,
                259200,
                2,
                10,
                2,
                canonical_digest("authority"),
                prerequisites,
                QualificationClaimScope.BOUNDED_OPERATIONAL_PRODUCTION,
            )
            self.assertEqual(
                {
                    item.obligation_id
                    for item in PilotController(PilotStore(Path(root)), plan)
                    .report()
                    .obligations
                },
                {PilotBlockerCode.MISSING_RUNTIME},
            )

    def test_plan_rejects_mismatched_candidate_pilot_and_authority_receipts(self):
        subjects = ("coupon-hive", "reeses-rainbow-web")
        complete = self.prerequisites(*subjects)
        cases = (
            (
                replace(
                    complete,
                    production_candidate=self.evidence("other-candidate", "production"),
                ),
                canonical_digest("authority"),
                "production receipt targets another candidate",
            ),
            (
                replace(
                    complete,
                    whole_os_host=self.evidence("other-candidate", "host"),
                ),
                canonical_digest("authority"),
                "host receipt targets another candidate",
            ),
            (
                replace(
                    complete,
                    delivery_authority=self.evidence("other-pilot", "authority"),
                ),
                canonical_digest("authority"),
                "delivery authority receipt targets another pilot",
            ),
            (complete, canonical_digest("other-authority"), "authority digest"),
        )
        for prerequisites, authority_digest, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                ValueError, message
            ):
                PilotPlan(
                    "pilot",
                    "external",
                    D,
                    subjects,
                    0,
                    259200,
                    2,
                    10,
                    2,
                    authority_digest,
                    prerequisites,
                    QualificationClaimScope.BOUNDED_OPERATIONAL_PRODUCTION,
                )

    def test_legacy_pilot_state_without_scope_loads_as_full_autonomy(self):
        with TemporaryDirectory() as root:
            path = Path(root)
            prerequisites = replace(self.prerequisites(), benchmark_candidate=None)
            plan = PilotPlan(
                "pilot",
                "self",
                D,
                ("subject",),
                0,
                259200,
                1,
                10,
                2,
                canonical_digest("authority"),
                prerequisites,
                QualificationClaimScope.BOUNDED_OPERATIONAL_PRODUCTION,
            )
            store = PilotStore(path)
            PilotController(store, plan)
            document = json.loads(store.current.read_text(encoding="utf-8"))
            document["plan"].pop("claim_scope")
            store.current.write_text(json.dumps(document) + "\n", encoding="utf-8")
            self.assertEqual(
                store.load().plan.claim_scope,
                QualificationClaimScope.FULL_AUTONOMY_OR_SUPERIORITY,
            )

    def test_active_attempt_survives_restart_and_enforces_concurrency(self):
        with TemporaryDirectory() as root:
            plan = PilotPlan(
                "pilot",
                "self",
                D,
                ("subject",),
                0,
                259200,
                1,
                10,
                4,
                canonical_digest("authority"),
                self.prerequisites(),
            )
            store = PilotStore(Path(root))
            PilotController(store, plan).begin_attempt(
                attempt_id="one",
                subject_id="subject",
                family_id="failure-a",
                started_at=1,
                resource_units=3,
            )
            resumed = PilotController(PilotStore(Path(root)), plan)
            self.assertEqual(resumed.report().active_attempt_ids, ("one",))
            with self.assertRaisesRegex(ValueError, "maximum concurrency"):
                resumed.begin_attempt(
                    attempt_id="two",
                    subject_id="subject",
                    family_id="failure-b",
                    started_at=2,
                )
            receipt = self.evidence("subject", "delivery-one")
            resumed.complete_attempt(
                PilotAttempt(
                    "one",
                    "subject",
                    "failure-a",
                    D,
                    "accepted",
                    receipt,
                    1,
                    3,
                    3,
                )
            )
            self.assertFalse(resumed.report().active_attempt_ids)

    def test_daily_resource_and_delivery_limits_reset_on_next_day(self):
        with TemporaryDirectory() as root:
            plan = PilotPlan(
                "pilot",
                "self",
                D,
                ("subject",),
                0,
                259200,
                2,
                2,
                1,
                canonical_digest("authority"),
                self.prerequisites(),
            )
            controller = PilotController(PilotStore(Path(root)), plan)
            controller.record_attempt(
                PilotAttempt(
                    "day-one",
                    "subject",
                    "family-one",
                    D,
                    "accepted",
                    self.evidence("subject", "delivery-day-one"),
                    1,
                    2,
                    2,
                )
            )
            with self.assertRaisesRegex(ValueError, "daily resource"):
                controller.begin_attempt(
                    attempt_id="same-day",
                    subject_id="subject",
                    family_id="family-two",
                    started_at=3,
                )
            controller.begin_attempt(
                attempt_id="next-day",
                subject_id="subject",
                family_id="family-two",
                started_at=86400,
            )
            controller.complete_attempt(
                PilotAttempt(
                    "next-day",
                    "subject",
                    "family-two",
                    D,
                    "accepted",
                    self.evidence("subject", "delivery-next-day"),
                    86400,
                    86401,
                )
            )
            controller.begin_attempt(
                attempt_id="next-day-second",
                subject_id="subject",
                family_id="family-three",
                started_at=86402,
            )
            second = PilotAttempt(
                "next-day-second",
                "subject",
                "family-three",
                D,
                "accepted",
                self.evidence("subject", "delivery-next-day-second"),
                86402,
                86403,
            )
            with self.assertRaisesRegex(ValueError, "delivery rate"):
                controller.complete_attempt(second)


if __name__ == "__main__":
    unittest.main()
