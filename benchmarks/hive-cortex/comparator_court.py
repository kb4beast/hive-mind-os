"""Comparator provenance registry and measurement-capped court for hive-cortex.

This module is deliberately standalone. ``benchmarks/hive-cortex`` is not a
Python package (the hyphen makes it unimportable by module path), so load this
file with :func:`importlib.util.spec_from_file_location`::

    import importlib.util
    from pathlib import Path

    path = Path("benchmarks/hive-cortex/comparator_court.py")
    spec = importlib.util.spec_from_file_location("hive_cortex_comparator_court", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

The court exists to make one thing structurally impossible: recording a
comparative quality claim that no reproducible receipt supports. The only
disposition this module can express is
``hive_mind_os.benchmark_harness.MEASUREMENT_DISPOSITION``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from hive_mind_os.benchmark_harness import MEASUREMENT_DISPOSITION

SCHEMA_VERSION = 1

JUDGE_ID = "hive-cortex-independent-benchmark-judge"

#: Rendered verbatim into ``docs/benchmarks/HIVE_CORTEX_RESULTS.md`` and checked
#: by :func:`guard_results_document`.
DISCLAIMER = (
    "These are measurements only; they authorize no comparative quality or "
    "superiority claim."
)

OBLIGATIONS: tuple[str, ...] = (
    "No comparative claim is authorized by this measurement.",
    "External comparators must be executed under equal pinned conditions "
    "before any superiority court may be convened.",
    "All losing and failed attempts are retained with the same artifact "
    "inventory as passing attempts.",
)

AVAILABILITY_PINNED = "pinned"
AVAILABILITY_UNAVAILABLE = "unavailable"
_AVAILABILITY = (AVAILABILITY_PINNED, AVAILABILITY_UNAVAILABLE)

_SUPERIORITY_TERM = (
    r"\b(?:outperform(?:s|ed|ing)?|beats|stronger\s+than|superior\s+to"
    r"|state[-\s]of[-\s]the[-\s]art)\b"
)
_SUBJECT_TERM = r"\b(?:hive|benchmark|comparator|baseline)"
_SUPERIORITY_PATTERN = re.compile(
    rf"{_SUBJECT_TERM}.{{0,160}}{_SUPERIORITY_TERM}"
    rf"|{_SUPERIORITY_TERM}.{{0,160}}{_SUBJECT_TERM}",
    re.IGNORECASE | re.DOTALL,
)


class ComparatorProvenanceError(ValueError):
    """Raised when a comparator entry is neither pinned+licensed nor excused."""


class SuperiorityClaimError(ValueError):
    """Raised when a verdict tries to express anything above a measurement."""


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ComparatorProvenanceError(
            f"comparator field {field!r} must be a non-empty string"
        )
    return value


@dataclass(frozen=True)
class ComparatorRecord:
    """One comparator: pinned with a license, or honestly marked unavailable."""

    source_id: str
    name: str
    pin: str | None
    license: str | None
    availability: str
    reason: str | None

    def __post_init__(self) -> None:
        _require_text(self.source_id, "source_id")
        _require_text(self.name, "name")
        if self.availability not in _AVAILABILITY:
            raise ComparatorProvenanceError(
                "comparator availability must be one of "
                f"{_AVAILABILITY}: {self.availability!r}"
            )
        if self.availability == AVAILABILITY_PINNED:
            if not (self.pin or "").strip():
                raise ComparatorProvenanceError(
                    f"pinned comparator {self.source_id} requires an exact pin"
                )
            if not (self.license or "").strip():
                raise ComparatorProvenanceError(
                    f"pinned comparator {self.source_id} requires a license"
                )
        else:
            if not (self.reason or "").strip():
                raise ComparatorProvenanceError(
                    f"unavailable comparator {self.source_id} requires a reason"
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "name": self.name,
            "pin": self.pin,
            "license": self.license,
            "availability": self.availability,
            "reason": self.reason,
        }


def load_comparators(path: str | Path) -> tuple[ComparatorRecord, ...]:
    """Parse the comparator registry, validating every entry's provenance."""

    registry = Path(path)
    payload = json.loads(registry.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ComparatorProvenanceError("comparator registry must be a JSON object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ComparatorProvenanceError(
            "unsupported comparator registry schema_version: "
            f"{payload.get('schema_version')!r}"
        )
    entries = payload.get("comparators")
    if not isinstance(entries, list) or not entries:
        raise ComparatorProvenanceError("comparator registry must list comparators")
    records: list[ComparatorRecord] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ComparatorProvenanceError("comparator entries must be JSON objects")
        record = ComparatorRecord(
            source_id=str(entry.get("source_id", "")),
            name=str(entry.get("name", "")),
            pin=entry.get("pin"),
            license=entry.get("license"),
            availability=str(entry.get("availability", "")),
            reason=entry.get("reason"),
        )
        if record.source_id in seen:
            raise ComparatorProvenanceError(
                f"duplicate comparator source_id: {record.source_id}"
            )
        seen.add(record.source_id)
        records.append(record)
    return tuple(records)


@dataclass(frozen=True)
class ComparatorCourtVerdict:
    """A measurement record. It cannot, by construction, rank anything."""

    schema_version: int
    disposition: str
    judge_id: str
    lane_identities: tuple[str, ...]
    comparators: tuple[ComparatorRecord, ...]
    results_digest: str
    obligations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.disposition != MEASUREMENT_DISPOSITION:
            raise SuperiorityClaimError(
                "superiority dispositions require reproducible receipts from "
                "multiple pinned external comparators; none exist"
            )
        if self.judge_id in self.lane_identities:
            raise ValueError(
                "benchmark judge must be independent from lane identities"
            )
        if len(set(self.lane_identities)) != len(self.lane_identities):
            raise ValueError("benchmark lane identities must be distinct")
        if not self.lane_identities:
            raise ValueError("verdict requires at least one lane identity")
        if not (self.results_digest or "").strip():
            raise ValueError("verdict requires a results digest")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "disposition": self.disposition,
            "judge_id": self.judge_id,
            "lane_identities": list(self.lane_identities),
            "comparators": [record.to_dict() for record in self.comparators],
            "results_digest": self.results_digest,
            "obligations": list(self.obligations),
        }


def build_verdict(
    *,
    lane_identities: Sequence[str],
    comparators: Sequence[ComparatorRecord],
    results_digest: str,
) -> ComparatorCourtVerdict:
    """Assemble the only verdict this node is permitted to record."""

    return ComparatorCourtVerdict(
        schema_version=SCHEMA_VERSION,
        disposition=MEASUREMENT_DISPOSITION,
        judge_id=JUDGE_ID,
        lane_identities=tuple(lane_identities),
        comparators=tuple(comparators),
        results_digest=results_digest,
        obligations=OBLIGATIONS,
    )


def guard_results_document(text: str) -> tuple[str, ...]:
    """Return violation strings for a results document. Empty tuple == pass."""

    violations: list[str] = []
    for match in _SUPERIORITY_PATTERN.finditer(text):
        excerpt = " ".join(match.group(0).split())
        if len(excerpt) > 120:
            excerpt = excerpt[:117] + "..."
        violations.append(f"unsupported superiority phrasing: {excerpt}")
    if DISCLAIMER not in text:
        violations.append(
            "missing mandatory disclaimer line: " + DISCLAIMER
        )
    return tuple(violations)


__all__ = [
    "AVAILABILITY_PINNED",
    "AVAILABILITY_UNAVAILABLE",
    "ComparatorCourtVerdict",
    "ComparatorProvenanceError",
    "ComparatorRecord",
    "DISCLAIMER",
    "JUDGE_ID",
    "OBLIGATIONS",
    "SCHEMA_VERSION",
    "SuperiorityClaimError",
    "build_verdict",
    "guard_results_document",
    "load_comparators",
]
