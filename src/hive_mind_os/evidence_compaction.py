"""Loss-accounted compaction of bounded test and tool evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from .runtime_contracts import canonical_digest, require_digest


class EvidenceCompactionError(ValueError):
    """Raw evidence cannot be compacted without hiding required information."""


_MATERIAL_ERROR = re.compile(
    r"(?:\bFAIL(?:ED|URE)?\b|\bERROR\b|\bFATAL\b|\bPANIC\b|"
    r"\bEXCEPTION\b|\bASSERT(?:ION)?ERROR\b|\bCAUSED BY\b|"
    r"\bTIMEOUT\b|\bDENIED\b|\bVIOLATION\b)",
    re.IGNORECASE,
)
_CAUSAL = re.compile(
    r"(?:^Traceback|\bcaused by\b|\broot cause\b|\bexception\b|"
    r"\bassert(?:ion)?error\b|\bfatal\b|\bpanic\b)",
    re.IGNORECASE,
)
_PASS_SUMMARY = re.compile(
    r"(?:\bOK\b|\bPASSED\b|\btests? passed\b|\bRan \d+ tests?\b)",
    re.IGNORECASE,
)


def _raw_digest(raw: bytes) -> str:
    return "sha256:" + sha256(raw).hexdigest()


def _normalized_line(value: str) -> str:
    return " ".join(value.strip().split())


@dataclass(frozen=True, slots=True)
class CompactedEvidence:
    outcome: str
    exit_code: int
    raw_digest: str
    raw_byte_count: int
    raw_line_count: int
    first_causal_error: str | None
    distinct_material_errors: tuple[str, ...]
    retained_lines: tuple[str, ...]
    omitted_line_count: int
    decode_replacements: int
    compact_digest: str = ""

    def __post_init__(self) -> None:
        if self.outcome not in {"PASSED", "FAILED", "CANCELLED"}:
            raise EvidenceCompactionError("unsupported evidence outcome")
        if type(self.exit_code) is not int:
            raise EvidenceCompactionError("evidence exit_code must be an integer")
        if self.outcome == "PASSED" and self.exit_code != 0:
            raise EvidenceCompactionError("passing evidence requires exit code zero")
        if self.outcome == "FAILED" and self.exit_code == 0:
            raise EvidenceCompactionError("failed evidence requires a non-zero exit code")
        require_digest(self.raw_digest, "raw_digest")
        for label in (
            "raw_byte_count",
            "raw_line_count",
            "omitted_line_count",
            "decode_replacements",
        ):
            value = getattr(self, label)
            if type(value) is not int or value < 0:
                raise EvidenceCompactionError(f"{label} must be non-negative")
        if self.omitted_line_count > self.raw_line_count:
            raise EvidenceCompactionError("omitted line count exceeds raw evidence")
        if self.outcome == "FAILED" and not self.distinct_material_errors:
            raise EvidenceCompactionError("failed evidence requires a material error")
        if (
            self.first_causal_error is not None
            and self.first_causal_error not in self.distinct_material_errors
        ):
            raise EvidenceCompactionError("first causal error must be retained as material")
        expected = canonical_digest(self.to_document(include_digest=False))
        if not self.compact_digest:
            object.__setattr__(self, "compact_digest", expected)
        elif self.compact_digest != expected:
            raise EvidenceCompactionError("compact evidence digest is invalid")

    def to_document(self, *, include_digest: bool = True) -> dict[str, Any]:
        value: dict[str, Any] = {
            "schema_version": 1,
            "outcome": self.outcome,
            "exit_code": self.exit_code,
            "raw_digest": self.raw_digest,
            "raw_byte_count": self.raw_byte_count,
            "raw_line_count": self.raw_line_count,
            "first_causal_error": self.first_causal_error,
            "distinct_material_errors": list(self.distinct_material_errors),
            "retained_lines": list(self.retained_lines),
            "omitted_line_count": self.omitted_line_count,
            "decode_replacements": self.decode_replacements,
        }
        if include_digest:
            value["compact_digest"] = self.compact_digest
        return value

    def verify_raw(self, raw: bytes) -> bool:
        if type(raw) is not bytes:
            return False
        return len(raw) == self.raw_byte_count and _raw_digest(raw) == self.raw_digest


def compact_evidence(
    raw: bytes,
    *,
    outcome: str,
    exit_code: int,
    passing_tail_lines: int = 12,
    maximum_raw_bytes: int = 8_388_608,
) -> CompactedEvidence:
    """Compact one bounded log while retaining a digest of all original bytes.

    Failure compaction keeps the first causal line and every distinct line that
    is materially error-bearing.  If a failing tool produces no recognizable
    error marker, its first non-empty line is treated as the causal error rather
    than manufacturing a successful-looking empty summary.
    """

    if type(raw) is not bytes or not raw:
        raise EvidenceCompactionError("raw evidence must be non-empty immutable bytes")
    if type(maximum_raw_bytes) is not int or maximum_raw_bytes <= 0:
        raise EvidenceCompactionError("maximum_raw_bytes must be positive")
    if len(raw) > maximum_raw_bytes:
        raise EvidenceCompactionError("raw evidence exceeds the declared compaction bound")
    if type(passing_tail_lines) is not int or passing_tail_lines < 1:
        raise EvidenceCompactionError("passing_tail_lines must be positive")
    normalized_outcome = outcome.upper()
    if normalized_outcome not in {"PASSED", "FAILED", "CANCELLED"}:
        raise EvidenceCompactionError("unsupported evidence outcome")
    if type(exit_code) is not int:
        raise EvidenceCompactionError("exit_code must be an integer")
    if normalized_outcome == "PASSED" and exit_code != 0:
        raise EvidenceCompactionError("passing evidence requires exit code zero")
    if normalized_outcome == "FAILED" and exit_code == 0:
        raise EvidenceCompactionError("failed evidence requires a non-zero exit code")
    text = raw.decode("utf-8", "replace")
    replacements = text.count("\ufffd")
    lines = text.splitlines()
    normalized = [_normalized_line(line) for line in lines]
    nonempty = [line for line in normalized if line]

    if normalized_outcome == "PASSED":
        summaries = [line for line in nonempty if _PASS_SUMMARY.search(line)]
        tail = nonempty[-passing_tail_lines:]
        retained = tuple(dict.fromkeys((*summaries, *tail)))
        material: tuple[str, ...] = ()
        first_causal = None
    else:
        errors = [line for line in nonempty if _MATERIAL_ERROR.search(line)]
        causal = next((line for line in nonempty if _CAUSAL.search(line)), None)
        if causal is None:
            causal = errors[0] if errors else (nonempty[0] if nonempty else "<empty decoded log>")
        material = tuple(dict.fromkeys((causal, *errors)))
        first_causal = causal
        retained = material
    # ``retained_lines`` contains distinct normalized lines, so duplicates and
    # blank lines are genuinely omitted even when one equal line is retained.
    omitted = max(0, len(lines) - len(retained))
    return CompactedEvidence(
        outcome=normalized_outcome,
        exit_code=exit_code,
        raw_digest=_raw_digest(raw),
        raw_byte_count=len(raw),
        raw_line_count=len(lines),
        first_causal_error=first_causal,
        distinct_material_errors=material,
        retained_lines=retained,
        omitted_line_count=omitted,
        decode_replacements=replacements,
    )


__all__ = [
    "CompactedEvidence",
    "EvidenceCompactionError",
    "compact_evidence",
]
