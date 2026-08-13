"""Pure parity probes for separately produced legacy and canonical observations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ...brain_kernel.canonical import canonical_digest
from .models import AuthorityPath, CompatibilityError, CompatibilityObservation

_VOLATILE_KEYS = frozenset({"created_at", "started_at", "completed_at", "timestamp"})


def _stable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _stable(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
            if str(key) not in _VOLATILE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_stable(item) for item in value]
    if hasattr(value, "value") and not isinstance(value, (str, bytes)):
        return value.value
    return value


@dataclass(frozen=True, slots=True)
class ParityVerdict:
    entry_point: str
    operation: str
    behavior_match: bool
    evidence_match: bool
    differences: tuple[str, ...]
    legacy_digest: str
    canonical_digest: str

    @property
    def matched(self) -> bool:
        return self.behavior_match and self.evidence_match and not self.differences

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_point": self.entry_point,
            "operation": self.operation,
            "behavior_match": self.behavior_match,
            "evidence_match": self.evidence_match,
            "matched": self.matched,
            "differences": list(self.differences),
            "legacy_digest": self.legacy_digest,
            "canonical_digest": self.canonical_digest,
        }


def _observation(value: CompatibilityObservation | Mapping[str, Any]) -> CompatibilityObservation:
    if isinstance(value, CompatibilityObservation):
        return value
    try:
        return CompatibilityObservation(
            str(value["entry_point"]),
            str(value["operation"]),
            AuthorityPath(value["authority_path"]),
            str(value["status"]),
            dict(value["behavior"]),
            dict(value["evidence"]),
            int(value.get("effect_count", 0)),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise CompatibilityError("parity input is not a typed compatibility observation") from error


class ParityProbe:
    """Compare behavior/evidence without invoking either authority path."""

    def compare(
        self,
        legacy: CompatibilityObservation | Mapping[str, Any],
        canonical: CompatibilityObservation | Mapping[str, Any],
    ) -> ParityVerdict:
        left = _observation(legacy)
        right = _observation(canonical)
        if left.entry_point != right.entry_point or left.operation != right.operation:
            raise CompatibilityError("parity observations refer to different operations")
        for observation in (left, right):
            if observation.effect_count and observation.authority_path is not AuthorityPath.SHADOW:
                raise CompatibilityError("parity requires effect-free or shadow observations")
        left_behavior = _stable({"status": left.status, **left.behavior})
        right_behavior = _stable({"status": right.status, **right.behavior})
        left_evidence = _stable(left.evidence)
        right_evidence = _stable(right.evidence)
        differences: list[str] = []
        if left_behavior != right_behavior:
            differences.append("behavior")
        if left_evidence != right_evidence:
            differences.append("evidence")
        return ParityVerdict(
            left.entry_point,
            left.operation,
            left_behavior == right_behavior,
            left_evidence == right_evidence,
            tuple(differences),
            canonical_digest({"behavior": left_behavior, "evidence": left_evidence}),
            canonical_digest({"behavior": right_behavior, "evidence": right_evidence}),
        )

    def probe(
        self,
        legacy_projection: Callable[[], CompatibilityObservation | Mapping[str, Any]],
        canonical_projection: Callable[[], CompatibilityObservation | Mapping[str, Any]],
    ) -> ParityVerdict:
        """Run supplied projections only; effectful legacy/canonical calls are out of scope."""

        return self.compare(legacy_projection(), canonical_projection())
