"""Independent challenger evaluation across held-out, PIT, adversarial, and
comparator surfaces, with sealed holdouts and append-only losing evidence."""

from __future__ import annotations

import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any

from .canonical import canonical_bytes, canonical_digest

__all__ = [
    "ChallengerDescriptor",
    "EvaluationContract",
    "EvaluationError",
    "EvaluationIdentities",
    "EvaluationRecord",
    "EvaluationRuntime",
    "EvaluationVerdict",
    "GuardrailSpec",
    "HoldoutSeal",
    "HoldoutViolation",
    "SealedHoldout",
    "SurfaceKind",
    "SurfaceResult",
]


class EvaluationError(ValueError):
    """An evaluation input violates the independent-evaluation contract."""


class HoldoutViolation(RuntimeError):
    """Holdout content was requested before an intact prediction seal."""


class SurfaceKind(StrEnum):
    HELD_OUT = "held-out"
    PIT = "pit"
    ADVERSARIAL = "adversarial"
    COMPARATOR = "comparator"


class EvaluationVerdict(StrEnum):
    KEEP = "keep"
    RETEST = "retest"
    DISCARD = "discard"
    QUARANTINE = "quarantine"


def _require_identifier(value: object, label: str) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise EvaluationError(f"{label} must be an exact non-empty trimmed string")
    return value


def _require_measurements(values: object, label: str) -> tuple[float, ...]:
    if type(values) is not tuple or not values:
        raise EvaluationError(f"{label} must be a non-empty tuple of measurements")
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise EvaluationError(f"{label} must contain numeric measurements")
        if not math.isfinite(float(value)):
            raise EvaluationError(f"{label} must contain finite measurements")
    return values


def _require_non_negative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvaluationError(f"{label} must be a number")
    if not math.isfinite(float(value)) or float(value) < 0.0:
        raise EvaluationError(f"{label} must be a finite non-negative number")
    return float(value)


@dataclass(frozen=True, slots=True)
class EvaluationIdentities:
    """AC1: the evaluator is distinct from both the proposer and the builder."""

    proposer_id: str
    builder_id: str
    evaluator_id: str

    def __post_init__(self) -> None:
        _require_identifier(self.proposer_id, "proposer_id")
        _require_identifier(self.builder_id, "builder_id")
        _require_identifier(self.evaluator_id, "evaluator_id")
        if self.proposer_id == self.builder_id:
            raise EvaluationError("proposer and builder identities must be distinct")
        if self.evaluator_id in {self.proposer_id, self.builder_id}:
            raise EvaluationError(
                "evaluator identity must be independent of the proposer and the builder"
            )

    def document(self) -> dict[str, str]:
        return {
            "proposer_id": self.proposer_id,
            "builder_id": self.builder_id,
            "evaluator_id": self.evaluator_id,
        }


@dataclass(frozen=True, slots=True)
class ChallengerDescriptor:
    """Plain mirror of an upstream challenger proposal; no kernel import."""

    challenger_id: str
    parent_champion_id: str
    change_ref: str
    proposal_digest: str

    def __post_init__(self) -> None:
        _require_identifier(self.challenger_id, "challenger_id")
        _require_identifier(self.parent_champion_id, "parent_champion_id")
        _require_identifier(self.change_ref, "change_ref")
        _require_identifier(self.proposal_digest, "proposal_digest")
        if self.challenger_id == self.parent_champion_id:
            raise EvaluationError("a challenger cannot be its own parent champion")

    def document(self) -> dict[str, str]:
        return {
            "challenger_id": self.challenger_id,
            "parent_champion_id": self.parent_champion_id,
            "change_ref": self.change_ref,
            "proposal_digest": self.proposal_digest,
        }


@dataclass(frozen=True, slots=True)
class HoldoutSeal:
    """Order stamp proving a prediction was fixed before any reveal."""

    holdout_id: str
    evaluator_id: str
    prediction_digest: str
    sequence: int

    def __post_init__(self) -> None:
        _require_identifier(self.holdout_id, "holdout_id")
        _require_identifier(self.evaluator_id, "evaluator_id")
        _require_identifier(self.prediction_digest, "prediction_digest")
        if not self.prediction_digest.startswith("sha256:"):
            raise EvaluationError("prediction_digest must be a sha256 canonical digest")
        if isinstance(self.sequence, bool) or type(self.sequence) is not int:
            raise EvaluationError("seal sequence must be an integer")
        if self.sequence < 1:
            raise EvaluationError("seal sequence must be a positive order stamp")


class SealedHoldout:
    """AC2: case payloads are unreachable except through a valid ``reveal``."""

    __slots__ = (
        "_holdout_id",
        "_cases",
        "_prediction",
        "_seal",
        "_violations",
        "_sequence",
        "_seal_sequence",
        "_reveal_sequence",
    )

    def __init__(self, holdout_id: str, cases: Mapping[str, Any]) -> None:
        self._holdout_id = _require_identifier(holdout_id, "holdout_id")
        if not isinstance(cases, Mapping) or not cases:
            raise EvaluationError("a sealed holdout requires at least one case")
        prepared: dict[str, Any] = {}
        for case_id, payload in cases.items():
            prepared[_require_identifier(case_id, "holdout case id")] = payload
        canonical_bytes(prepared)
        self._cases: dict[str, Any] = prepared
        self._prediction: dict[str, Any] | None = None
        self._seal: HoldoutSeal | None = None
        self._violations: list[str] = []
        self._sequence = 0
        self._seal_sequence: int | None = None
        self._reveal_sequence: int | None = None

    def _stamp(self) -> int:
        self._sequence += 1
        return self._sequence

    def _record_violation(self, kind: str) -> None:
        self._stamp()
        self._violations.append(kind)

    @property
    def case_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._cases))

    @property
    def violations(self) -> tuple[str, ...]:
        return tuple(self._violations)

    @property
    def ordering(self) -> dict[str, Any]:
        valid = (
            self._seal_sequence is not None
            and not self._violations
            and (
                self._reveal_sequence is None
                or self._reveal_sequence > self._seal_sequence
            )
        )
        return {
            "seal_sequence": self._seal_sequence,
            "reveal_sequence": self._reveal_sequence,
            "valid": valid,
        }

    def seal_prediction(
        self,
        evaluator_id: str,
        prediction_content: Mapping[str, Any],
    ) -> HoldoutSeal:
        identity = _require_identifier(evaluator_id, "evaluator_id")
        if not isinstance(prediction_content, Mapping):
            raise EvaluationError("prediction content must be a mapping")
        if self._seal is not None:
            raise HoldoutViolation("holdout already sealed")
        prediction = dict(prediction_content)
        sequence = self._stamp()
        seal = HoldoutSeal(
            self._holdout_id,
            identity,
            canonical_digest(prediction),
            sequence,
        )
        self._prediction = prediction
        self._seal = seal
        self._seal_sequence = sequence
        return seal

    def reveal(self, seal: HoldoutSeal | None = None) -> dict[str, Any]:
        recorded = self._seal
        if seal is None or recorded is None or self._prediction is None:
            self._record_violation("reveal_without_seal")
            raise HoldoutViolation("holdout reveal requires an intact prior seal")
        if (
            seal.holdout_id != self._holdout_id
            or seal != recorded
            or seal.prediction_digest != canonical_digest(self._prediction)
        ):
            self._record_violation("prediction_digest_mismatch")
            raise HoldoutViolation(
                "sealed prediction was altered or belongs to another holdout"
            )
        if self._reveal_sequence is None:
            self._reveal_sequence = self._stamp()
        return dict(self._cases)


def _artifact_issue(reference: str) -> str | None:
    """Local re-implementation of the ``path#sha256:<digest>`` contract."""

    if type(reference) is not str:
        return "artifact reference must be path#sha256:<digest>"
    raw_path, separator, expected_digest = reference.rpartition("#")
    if not separator or not raw_path or not expected_digest.startswith("sha256:"):
        return "artifact reference must be path#sha256:<digest>"
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        return f"artifact does not resolve: {raw_path}"
    if f"sha256:{sha256(path.read_bytes()).hexdigest()}" != expected_digest:
        return f"artifact digest mismatch: {raw_path}"
    return None


@dataclass(frozen=True, slots=True)
class SurfaceResult:
    kind: SurfaceKind
    name: str
    baseline_samples: tuple[float, ...]
    candidate_samples: tuple[float, ...]
    artifact_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SurfaceKind):
            raise EvaluationError("surface kind must be a SurfaceKind member")
        _require_identifier(self.name, "surface name")
        _require_measurements(self.baseline_samples, "baseline_samples")
        _require_measurements(self.candidate_samples, "candidate_samples")
        if type(self.artifact_refs) is not tuple:
            raise EvaluationError("artifact_refs must be a tuple of references")
        for reference in self.artifact_refs:
            _require_identifier(reference, "artifact reference")

    def document(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "name": self.name,
            "baseline_samples": [float(value) for value in self.baseline_samples],
            "candidate_samples": [float(value) for value in self.candidate_samples],
            "artifact_refs": list(self.artifact_refs),
        }


@dataclass(frozen=True, slots=True)
class GuardrailSpec:
    surface: SurfaceKind
    maximum_regression: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.surface, SurfaceKind):
            raise EvaluationError("guardrail surface must be a SurfaceKind member")
        _require_non_negative(self.maximum_regression, "maximum_regression")


@dataclass(frozen=True, slots=True)
class EvaluationContract:
    minimum_repetitions: int = 3
    noise_multiplier: float = 2.0
    minimum_effect: float = 0.0
    guardrails: tuple[GuardrailSpec, ...] = (
        GuardrailSpec(SurfaceKind.ADVERSARIAL),
        GuardrailSpec(SurfaceKind.COMPARATOR),
    )

    def __post_init__(self) -> None:
        if (
            isinstance(self.minimum_repetitions, bool)
            or type(self.minimum_repetitions) is not int
            or self.minimum_repetitions < 2
        ):
            raise EvaluationError("minimum_repetitions must be an integer of at least 2")
        _require_non_negative(self.noise_multiplier, "noise_multiplier")
        _require_non_negative(self.minimum_effect, "minimum_effect")
        if type(self.guardrails) is not tuple:
            raise EvaluationError("guardrails must be a tuple of GuardrailSpec")
        surfaces: set[SurfaceKind] = set()
        for spec in self.guardrails:
            if not isinstance(spec, GuardrailSpec):
                raise EvaluationError("guardrails must be a tuple of GuardrailSpec")
            if spec.surface in surfaces:
                raise EvaluationError(f"duplicate guardrail surface: {spec.surface.value}")
            surfaces.add(spec.surface)

    @property
    def fingerprint(self) -> str:
        return canonical_digest(
            {
                "minimum_repetitions": self.minimum_repetitions,
                "noise_multiplier": float(self.noise_multiplier),
                "minimum_effect": float(self.minimum_effect),
                "guardrails": [
                    {
                        "surface": spec.surface.value,
                        "maximum_regression": float(spec.maximum_regression),
                    }
                    for spec in self.guardrails
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class EvaluationRecord:
    evaluation_id: str
    verdict: EvaluationVerdict
    reasons: tuple[str, ...]
    primary_effect: float | None
    required_effect: float | None
    noise_floor: float | None
    record_path: Path
    record_digest: str


class EvaluationRuntime:
    """Independent evaluator: quarantines first, never retests optimistically."""

    __slots__ = ("_contract",)

    def __init__(self, contract: EvaluationContract | None = None) -> None:
        if contract is not None and not isinstance(contract, EvaluationContract):
            raise EvaluationError("contract must be an EvaluationContract")
        self._contract = contract if contract is not None else EvaluationContract()

    @property
    def contract(self) -> EvaluationContract:
        return self._contract

    def evaluate(
        self,
        descriptor: ChallengerDescriptor,
        identities: EvaluationIdentities,
        surfaces: Sequence[SurfaceResult],
        holdout: SealedHoldout,
        *,
        evidence_root: str | Path,
    ) -> EvaluationRecord:
        if not isinstance(descriptor, ChallengerDescriptor):
            raise EvaluationError("descriptor must be a ChallengerDescriptor")
        if not isinstance(identities, EvaluationIdentities):
            raise EvaluationError("identities must be an EvaluationIdentities")
        if not isinstance(holdout, SealedHoldout):
            raise EvaluationError("holdout must be a SealedHoldout")
        if isinstance(surfaces, (str, bytes)) or not isinstance(surfaces, Sequence):
            raise EvaluationError("surfaces must be a sequence of SurfaceResult")
        given = tuple(surfaces)
        if not given:
            raise EvaluationError("at least one surface result is required")
        for surface in given:
            if not isinstance(surface, SurfaceResult):
                raise EvaluationError("surfaces must be a sequence of SurfaceResult")
        ordered = tuple(sorted(given, key=lambda item: (item.kind.value, item.name)))
        contract = self._contract

        ordering = holdout.ordering
        violations = holdout.violations

        # 1. Quarantine set (AC2 + AC4). Nothing below is measured if it is non-empty.
        quarantine_reasons: list[str] = []
        if not ordering["valid"] or violations:
            kinds = ", ".join(violations) if violations else "no intact prediction seal"
            quarantine_reasons.append(f"holdout boundary violated: {kinds}")
        seen: set[tuple[SurfaceKind, str]] = set()
        for surface in ordered:
            key = (surface.kind, surface.name)
            if key in seen:
                quarantine_reasons.append(f"duplicate surface: {surface.name}")
            seen.add(key)
            if not surface.artifact_refs:
                quarantine_reasons.append(
                    f"surface has no retained artifacts: {surface.name}"
                )
            for reference in surface.artifact_refs:
                issue = _artifact_issue(reference)
                if issue is not None:
                    quarantine_reasons.append(f"missing or mutated artifact: {issue}")

        verdict: EvaluationVerdict
        reasons: list[str]
        primary_effect: float | None = None
        required_effect: float | None = None
        noise_floor: float | None = None

        if quarantine_reasons:
            # 2. Absent or mutated evidence never falls through to a retest.
            verdict = EvaluationVerdict.QUARANTINE
            reasons = quarantine_reasons
        else:
            by_kind = {surface.kind: surface for surface in ordered}
            retest_reasons: list[str] = []
            missing = [kind.value for kind in SurfaceKind if kind not in by_kind]
            if missing:
                retest_reasons.append("missing surfaces: " + ", ".join(sorted(missing)))
            thin = sorted(
                surface.name
                for surface in ordered
                if min(len(surface.baseline_samples), len(surface.candidate_samples))
                < contract.minimum_repetitions
            )
            if thin:
                retest_reasons.append(
                    "insufficient repeated measurements: " + ", ".join(thin)
                )
            if retest_reasons:
                # 3. Incomplete measurement surface: retest, do not judge.
                verdict = EvaluationVerdict.RETEST
                reasons = retest_reasons
            else:
                # 4. Hard guardrails, retained as losing evidence.
                guardrail_reasons: list[str] = []
                for spec in contract.guardrails:
                    surface = by_kind[spec.surface]
                    effect = fmean(surface.candidate_samples) - fmean(
                        surface.baseline_samples
                    )
                    regression = max(0.0, -effect)
                    if regression > spec.maximum_regression:
                        guardrail_reasons.append(
                            f"hard guardrail regressed: {surface.name}"
                        )
                if guardrail_reasons:
                    verdict = EvaluationVerdict.DISCARD
                    reasons = guardrail_reasons
                else:
                    # 5. Primary decision on the held-out surface.
                    held_out = by_kind[SurfaceKind.HELD_OUT]
                    primary_effect = fmean(held_out.candidate_samples) - fmean(
                        held_out.baseline_samples
                    )
                    noise_floor = max(
                        pstdev(held_out.baseline_samples),
                        pstdev(held_out.candidate_samples),
                    )
                    required_effect = max(
                        float(contract.minimum_effect),
                        float(contract.noise_multiplier) * noise_floor,
                    )
                    if primary_effect > required_effect:
                        verdict = EvaluationVerdict.KEEP
                        reasons = [
                            "held-out effect exceeded the required effect over the noise floor"
                        ]
                    elif primary_effect < -required_effect:
                        verdict = EvaluationVerdict.DISCARD
                        reasons = [
                            "challenger materially underperformed the champion on held-out evidence"
                        ]
                    else:
                        verdict = EvaluationVerdict.RETEST
                        reasons = [
                            "held-out effect did not exceed the measured noise floor"
                        ]

        # 6. Retention for every verdict, losing evidence included (AC3).
        recorded_seal = holdout._seal
        document: dict[str, Any] = {
            "schema_version": 1,
            "descriptor": descriptor.document(),
            "identities": identities.document(),
            "contract_fingerprint": contract.fingerprint,
            "verdict": verdict.value,
            "reasons": list(dict.fromkeys(reasons)),
            "primary_effect": primary_effect,
            "required_effect": required_effect,
            "noise_floor": noise_floor,
            "holdout": {
                "holdout_id": holdout._holdout_id,
                "ordering": dict(ordering),
                "violations": list(violations),
                "prediction_digest": (
                    recorded_seal.prediction_digest if recorded_seal is not None else None
                ),
            },
            "surfaces": [surface.document() for surface in ordered],
        }
        evaluation_id = "EVAL-" + canonical_digest(document)[7:23]
        document["evaluation_id"] = evaluation_id

        root = Path(evidence_root)
        root.mkdir(parents=True, exist_ok=True)
        record_path = root / f"{evaluation_id}.json"
        payload = canonical_bytes(document) + b"\n"
        try:
            with record_path.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            if record_path.read_bytes() != payload:
                raise EvaluationError(
                    "retained evaluation record was mutated"
                ) from None
        return EvaluationRecord(
            evaluation_id,
            verdict,
            tuple(document["reasons"]),
            primary_effect,
            required_effect,
            noise_floor,
            record_path,
            canonical_digest(document),
        )
