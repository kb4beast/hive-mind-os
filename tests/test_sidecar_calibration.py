from __future__ import annotations

import unittest
from dataclasses import replace

from hive_mind_os.sidecar_calibration import (
    CalibrationDisposition,
    CalibrationError,
    ControlledRunIdentity,
    MeasurementKind,
    SidecarTrial,
    TokenMeasurement,
    calibrate_sidecar,
)


def digest(character: str) -> str:
    return "sha256:" + character * 64


IDENTITY = ControlledRunIdentity(
    digest("1"), digest("2"), digest("3"), digest("4"), digest("5")
)


def measured(value: int) -> TokenMeasurement:
    return TokenMeasurement(value, MeasurementKind.MEASURED, digest("6"))


def trial(trial_id: str, *, avoided: int = 100, cost: int = 20) -> SidecarTrial:
    return SidecarTrial(
        trial_id,
        "review-small",
        IDENTITY,
        IDENTITY,
        measured(avoided),
        measured(avoided),
        measured(0),
        measured(cost),
        measured(cost),
        measured(0),
    )


class SidecarCalibrationTests(unittest.TestCase):
    def test_positive_controlled_measured_trials_enable_workload_class(self) -> None:
        verdict = calibrate_sidecar(
            "review-small",
            (trial("trial-1"), trial("trial-2")),
        )
        self.assertEqual(verdict.disposition, CalibrationDisposition.ENABLED)
        self.assertEqual(verdict.net_savings, 320)
        self.assertTrue(verdict.enabled)

    def test_one_negative_measured_trial_stops_class(self) -> None:
        verdict = calibrate_sidecar(
            "review-small",
            (trial("trial-positive"), trial("trial-negative", avoided=10, cost=20)),
        )
        self.assertEqual(
            verdict.disposition,
            CalibrationDisposition.DISABLED_NEGATIVE,
        )
        self.assertFalse(verdict.enabled)

    def test_estimated_or_unavailable_values_cannot_enable(self) -> None:
        estimated = replace(
            trial("trial-estimated"),
            sidecar_input=TokenMeasurement(1, MeasurementKind.ESTIMATED, digest("7")),
        )
        unavailable = replace(
            trial("trial-unavailable"),
            sidecar_output=TokenMeasurement(None, MeasurementKind.UNAVAILABLE, None),
        )
        verdict = calibrate_sidecar("review-small", (estimated, unavailable))
        self.assertEqual(
            verdict.disposition,
            CalibrationDisposition.INSUFFICIENT_MEASUREMENT,
        )
        self.assertIsNone(verdict.net_savings)
        self.assertEqual(
            estimated.sidecar_input.to_document()["kind"],
            "ESTIMATED",
        )

    def test_acceptance_authority_subject_route_and_budget_must_be_identical(self) -> None:
        fields = (
            "acceptance_digest",
            "authority_digest",
            "subject_snapshot_digest",
            "model_route_digest",
            "budget_digest",
        )
        for field in fields:
            with self.subTest(field=field):
                changed = replace(IDENTITY, **{field: digest("f")})
                with self.assertRaisesRegex(CalibrationError, "must retain"):
                    replace(trial("trial-mismatch"), sidecar_identity=changed)

    def test_unavailable_is_not_zero_and_measurement_evidence_is_required(self) -> None:
        with self.assertRaises(CalibrationError):
            TokenMeasurement(0, MeasurementKind.UNAVAILABLE, None)
        with self.assertRaises(CalibrationError):
            TokenMeasurement(1, MeasurementKind.MEASURED, None)


if __name__ == "__main__":
    unittest.main()
