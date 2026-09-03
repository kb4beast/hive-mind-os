"""Measured-only sidecar economics with fail-closed workload-class gates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Sequence

from .runtime_contracts import canonical_digest, require_digest, require_identifier


class CalibrationError(ValueError):
    """A sidecar comparison is not controlled or is represented dishonestly."""


class MeasurementKind(StrEnum):
    MEASURED = "MEASURED"
    ESTIMATED = "ESTIMATED"
    UNAVAILABLE = "UNAVAILABLE"


class CalibrationDisposition(StrEnum):
    ENABLED = "ENABLED"
    DISABLED_NEGATIVE = "DISABLED_NEGATIVE"
    INSUFFICIENT_MEASUREMENT = "INSUFFICIENT_MEASUREMENT"


@dataclass(frozen=True, slots=True)
class TokenMeasurement:
    value: int | None
    kind: MeasurementKind
    evidence_digest: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, MeasurementKind):
            raise CalibrationError("measurement kind must be typed")
        if self.kind is MeasurementKind.UNAVAILABLE:
            if self.value is not None:
                raise CalibrationError("unavailable measurement cannot carry a numeric value")
        elif type(self.value) is not int or self.value < 0:
            raise CalibrationError("measured and estimated values must be non-negative integers")
        if self.kind is MeasurementKind.MEASURED:
            if self.evidence_digest is None:
                raise CalibrationError("measured value requires evidence")
            require_digest(self.evidence_digest, "measurement evidence_digest")
        elif self.evidence_digest is not None:
            require_digest(self.evidence_digest, "measurement evidence_digest")

    def to_document(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "kind": self.kind.value,
            "evidence_digest": self.evidence_digest,
        }


@dataclass(frozen=True, slots=True)
class ControlledRunIdentity:
    acceptance_digest: str
    authority_digest: str
    subject_snapshot_digest: str
    model_route_digest: str
    budget_digest: str

    def __post_init__(self) -> None:
        for label in (
            "acceptance_digest",
            "authority_digest",
            "subject_snapshot_digest",
            "model_route_digest",
            "budget_digest",
        ):
            require_digest(getattr(self, label), label)

    def to_document(self) -> dict[str, str]:
        return {
            "acceptance_digest": self.acceptance_digest,
            "authority_digest": self.authority_digest,
            "subject_snapshot_digest": self.subject_snapshot_digest,
            "model_route_digest": self.model_route_digest,
            "budget_digest": self.budget_digest,
        }


@dataclass(frozen=True, slots=True)
class SidecarTrial:
    trial_id: str
    workload_class: str
    parent_identity: ControlledRunIdentity
    sidecar_identity: ControlledRunIdentity
    avoided_parent_input: TokenMeasurement
    avoided_parent_output: TokenMeasurement
    avoided_parent_coordination: TokenMeasurement
    sidecar_input: TokenMeasurement
    sidecar_output: TokenMeasurement
    sidecar_coordination: TokenMeasurement

    def __post_init__(self) -> None:
        require_identifier(self.trial_id, "trial_id")
        require_identifier(self.workload_class, "workload_class")
        if not isinstance(self.parent_identity, ControlledRunIdentity) or not isinstance(
            self.sidecar_identity, ControlledRunIdentity
        ):
            raise CalibrationError("trial identities must be typed")
        if self.parent_identity != self.sidecar_identity:
            raise CalibrationError(
                "sidecar comparison must retain acceptance, authority, subject snapshot, model route, and budget"
            )
        measurements = (
            self.avoided_parent_input,
            self.avoided_parent_output,
            self.avoided_parent_coordination,
            self.sidecar_input,
            self.sidecar_output,
            self.sidecar_coordination,
        )
        if any(not isinstance(item, TokenMeasurement) for item in measurements):
            raise CalibrationError("trial measurements must be typed")

    @property
    def measured(self) -> bool:
        return all(
            item.kind is MeasurementKind.MEASURED
            for item in (
                self.avoided_parent_input,
                self.avoided_parent_output,
                self.avoided_parent_coordination,
                self.sidecar_input,
                self.sidecar_output,
                self.sidecar_coordination,
            )
        )

    @property
    def net_savings(self) -> int | None:
        if not self.measured:
            return None
        avoided = sum(
            item.value or 0
            for item in (
                self.avoided_parent_input,
                self.avoided_parent_output,
                self.avoided_parent_coordination,
            )
        )
        cost = sum(
            item.value or 0
            for item in (self.sidecar_input, self.sidecar_output, self.sidecar_coordination)
        )
        return avoided - cost

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "trial_id": self.trial_id,
            "workload_class": self.workload_class,
            "parent_identity": self.parent_identity.to_document(),
            "sidecar_identity": self.sidecar_identity.to_document(),
            "avoided_parent_input": self.avoided_parent_input.to_document(),
            "avoided_parent_output": self.avoided_parent_output.to_document(),
            "avoided_parent_coordination": self.avoided_parent_coordination.to_document(),
            "sidecar_input": self.sidecar_input.to_document(),
            "sidecar_output": self.sidecar_output.to_document(),
            "sidecar_coordination": self.sidecar_coordination.to_document(),
            "net_savings": self.net_savings,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())


@dataclass(frozen=True, slots=True)
class CalibrationVerdict:
    workload_class: str
    disposition: CalibrationDisposition
    trial_digests: tuple[str, ...]
    measured_trial_count: int
    net_savings: int | None
    reason: str

    def __post_init__(self) -> None:
        require_identifier(self.workload_class, "workload_class")
        if not isinstance(self.disposition, CalibrationDisposition):
            raise CalibrationError("calibration disposition must be typed")
        for digest in self.trial_digests:
            require_digest(digest, "trial digest")
        if type(self.measured_trial_count) is not int or self.measured_trial_count < 0:
            raise CalibrationError("measured_trial_count must be non-negative")
        if self.net_savings is not None and type(self.net_savings) is not int:
            raise CalibrationError("net_savings must be an integer or unavailable")
        if not self.reason.strip():
            raise CalibrationError("calibration reason is required")

    @property
    def enabled(self) -> bool:
        return self.disposition is CalibrationDisposition.ENABLED

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "workload_class": self.workload_class,
            "disposition": self.disposition.value,
            "trial_digests": list(self.trial_digests),
            "measured_trial_count": self.measured_trial_count,
            "net_savings": self.net_savings,
            "reason": self.reason,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())


def calibrate_sidecar(
    workload_class: str,
    trials: Sequence[SidecarTrial],
    *,
    minimum_measured_trials: int = 2,
    minimum_net_savings: int = 1,
) -> CalibrationVerdict:
    """Issue a workload-class verdict; estimates can never enable a sidecar."""

    require_identifier(workload_class, "workload_class")
    if type(minimum_measured_trials) is not int or minimum_measured_trials < 1:
        raise CalibrationError("minimum_measured_trials must be positive")
    if type(minimum_net_savings) is not int or minimum_net_savings < 1:
        raise CalibrationError("minimum_net_savings must be positive")
    selected = tuple(trials)
    if any(item.workload_class != workload_class for item in selected):
        raise CalibrationError("calibration mixes workload classes")
    if len({item.trial_id for item in selected}) != len(selected):
        raise CalibrationError("calibration contains duplicate trial identities")
    measured = tuple(item for item in selected if item.measured)
    measured_savings = tuple(item.net_savings for item in measured)
    if any(value is not None and value < 0 for value in measured_savings):
        return CalibrationVerdict(
            workload_class=workload_class,
            disposition=CalibrationDisposition.DISABLED_NEGATIVE,
            trial_digests=tuple(item.digest for item in selected),
            measured_trial_count=len(measured),
            net_savings=sum(value or 0 for value in measured_savings),
            reason="at least one measured trial is negative; this workload class is stopped",
        )
    if len(measured) < minimum_measured_trials or len(measured) != len(selected):
        return CalibrationVerdict(
            workload_class=workload_class,
            disposition=CalibrationDisposition.INSUFFICIENT_MEASUREMENT,
            trial_digests=tuple(item.digest for item in selected),
            measured_trial_count=len(measured),
            net_savings=(
                None if not measured else sum(value or 0 for value in measured_savings)
            ),
            reason="static estimates or unavailable observations cannot authorize sidecar use",
        )
    total = sum(value or 0 for value in measured_savings)
    if total < minimum_net_savings:
        return CalibrationVerdict(
            workload_class=workload_class,
            disposition=CalibrationDisposition.DISABLED_NEGATIVE,
            trial_digests=tuple(item.digest for item in selected),
            measured_trial_count=len(measured),
            net_savings=total,
            reason="measured net savings do not clear the configured positive threshold",
        )
    return CalibrationVerdict(
        workload_class=workload_class,
        disposition=CalibrationDisposition.ENABLED,
        trial_digests=tuple(item.digest for item in selected),
        measured_trial_count=len(measured),
        net_savings=total,
        reason="every controlled trial is measured and aggregate net savings are positive",
    )


__all__ = [
    "CalibrationDisposition",
    "CalibrationError",
    "CalibrationVerdict",
    "ControlledRunIdentity",
    "MeasurementKind",
    "SidecarTrial",
    "TokenMeasurement",
    "calibrate_sidecar",
]
