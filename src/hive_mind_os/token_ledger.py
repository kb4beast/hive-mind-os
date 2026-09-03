"""Honest token measurements and deterministic calibration receipts.

The module distinguishes provider measurements from local estimates and from
facts that are genuinely unavailable.  It never converts an unavailable value
to zero and never writes controller policy.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from statistics import median_low
from threading import RLock
from typing import Sequence

from .ledger import EvidenceLedger


class TokenAccountingError(ValueError):
    """A token record would misstate what was measured."""


class TokenSource(StrEnum):
    MEASURED = "measured"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"


def _canonical_digest(value: object) -> str:
    body = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{sha256(body).hexdigest()}"


def _count(value: int | None, source: TokenSource, label: str) -> None:
    if value is not None and (
        not isinstance(value, int) or isinstance(value, bool) or value < 0
    ):
        raise TokenAccountingError(f"{label} must be a non-negative integer or None")
    if source is TokenSource.UNAVAILABLE and value is not None:
        raise TokenAccountingError(f"unavailable {label} must be None")
    if source is not TokenSource.UNAVAILABLE and value is None:
        raise TokenAccountingError(f"{source.value} {label} requires a value")


@dataclass(frozen=True, slots=True)
class TokenMeasurement:
    input_tokens: int | None
    output_tokens: int | None
    input_source: TokenSource
    output_source: TokenSource
    estimator: str | None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    cache_source: TokenSource = TokenSource.UNAVAILABLE

    def __post_init__(self) -> None:
        for field in ("input_source", "output_source", "cache_source"):
            try:
                object.__setattr__(self, field, TokenSource(getattr(self, field)))
            except (TypeError, ValueError) as error:
                raise TokenAccountingError(f"{field} is unknown") from error
        _count(self.input_tokens, self.input_source, "input_tokens")
        _count(self.output_tokens, self.output_source, "output_tokens")
        if self.cache_source is TokenSource.UNAVAILABLE:
            if (
                self.cache_read_tokens is not None
                or self.cache_write_tokens is not None
            ):
                raise TokenAccountingError(
                    "unavailable cache token counts must be None"
                )
        else:
            if self.cache_read_tokens is None and self.cache_write_tokens is None:
                raise TokenAccountingError(
                    "measured or estimated cache usage requires a count"
                )
            for value, label in (
                (self.cache_read_tokens, "cache_read_tokens"),
                (self.cache_write_tokens, "cache_write_tokens"),
            ):
                if value is not None and (
                    not isinstance(value, int) or isinstance(value, bool) or value < 0
                ):
                    raise TokenAccountingError(f"{label} must be non-negative or None")
        estimated = TokenSource.ESTIMATED in (
            self.input_source,
            self.output_source,
            self.cache_source,
        )
        if estimated and (
            not isinstance(self.estimator, str) or not self.estimator.strip()
        ):
            raise TokenAccountingError("estimated counts require an estimator name")
        if not estimated and self.estimator is not None:
            raise TokenAccountingError(
                "estimator must be absent when no count is estimated"
            )

    def to_document(self) -> dict[str, object]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "input_source": self.input_source.value,
            "output_source": self.output_source.value,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "cache_source": self.cache_source.value,
            "estimator": self.estimator,
        }


def measure_call(
    *,
    request_bytes: int | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    max_output_tokens: int,
    estimator: str = "bytes-div-4",
    cache_read_tokens: int | None = None,
    cache_write_tokens: int | None = None,
) -> TokenMeasurement:
    """Prefer provider counts and estimate only the known request byte body.

    ``max_output_tokens`` is a limit, not observed use, so a missing completion
    count remains unavailable rather than being reported as the limit.
    """

    if request_bytes is not None and (
        not isinstance(request_bytes, int)
        or isinstance(request_bytes, bool)
        or request_bytes < 0
    ):
        raise TokenAccountingError("request_bytes must be non-negative or None")
    if (
        not isinstance(max_output_tokens, int)
        or isinstance(max_output_tokens, bool)
        or max_output_tokens < 1
    ):
        raise TokenAccountingError("max_output_tokens must be positive")
    for value, label in (
        (prompt_tokens, "prompt_tokens"),
        (completion_tokens, "completion_tokens"),
        (cache_read_tokens, "cache_read_tokens"),
        (cache_write_tokens, "cache_write_tokens"),
    ):
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            raise TokenAccountingError(f"{label} must be non-negative or None")
    if prompt_tokens is not None:
        input_value = prompt_tokens
        input_source = TokenSource.MEASURED
    elif request_bytes is not None:
        input_value = max(1, request_bytes // 4)
        input_source = TokenSource.ESTIMATED
    else:
        input_value = None
        input_source = TokenSource.UNAVAILABLE
    output_value = completion_tokens
    output_source = (
        TokenSource.MEASURED
        if completion_tokens is not None
        else TokenSource.UNAVAILABLE
    )
    has_cache = cache_read_tokens is not None or cache_write_tokens is not None
    return TokenMeasurement(
        input_tokens=input_value,
        output_tokens=output_value,
        input_source=input_source,
        output_source=output_source,
        estimator=estimator if input_source is TokenSource.ESTIMATED else None,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        cache_source=TokenSource.MEASURED if has_cache else TokenSource.UNAVAILABLE,
    )


@dataclass(frozen=True, slots=True)
class TokenRecord:
    run_id: str
    role: str
    work_item_id: str
    outcome: str
    retry_index: int
    measurement: TokenMeasurement
    context_manifest_digest: str | None
    omitted_role_count: int
    purpose: str = "model_call"
    call_count: int = 1
    fallback_count: int = 0
    avoided_input_tokens: int | None = None
    coordination_tokens: int = 0

    def __post_init__(self) -> None:
        for value, label in (
            (self.run_id, "run_id"),
            (self.role, "role"),
            (self.work_item_id, "work_item_id"),
            (self.outcome, "outcome"),
            (self.purpose, "purpose"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise TokenAccountingError(f"{label} is required")
        for value, label in (
            (self.retry_index, "retry_index"),
            (self.omitted_role_count, "omitted_role_count"),
            (self.call_count, "call_count"),
            (self.fallback_count, "fallback_count"),
            (self.coordination_tokens, "coordination_tokens"),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise TokenAccountingError(f"{label} must be a non-negative integer")
        if self.call_count < 1:
            raise TokenAccountingError("call_count must be at least one")
        if self.avoided_input_tokens is not None and (
            not isinstance(self.avoided_input_tokens, int)
            or isinstance(self.avoided_input_tokens, bool)
            or self.avoided_input_tokens < 0
        ):
            raise TokenAccountingError(
                "avoided_input_tokens must be non-negative or None"
            )
        if self.context_manifest_digest is not None and (
            not isinstance(self.context_manifest_digest, str)
            or len(self.context_manifest_digest) != 71
            or not self.context_manifest_digest.startswith("sha256:")
            or any(
                character not in "0123456789abcdef"
                for character in self.context_manifest_digest[7:]
            )
        ):
            raise TokenAccountingError(
                "context_manifest_digest must be absent or a lowercase sha256 digest"
            )

    @property
    def record_digest(self) -> str:
        return _canonical_digest(self.to_document())

    def to_document(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "role": self.role,
            "work_item_id": self.work_item_id,
            "outcome": self.outcome,
            "retry_index": self.retry_index,
            "measurement": self.measurement.to_document(),
            "context_manifest_digest": self.context_manifest_digest,
            "omitted_role_count": self.omitted_role_count,
            "purpose": self.purpose,
            "call_count": self.call_count,
            "fallback_count": self.fallback_count,
            "avoided_input_tokens": self.avoided_input_tokens,
            "coordination_tokens": self.coordination_tokens,
        }


@dataclass(frozen=True, slots=True)
class PurposeCalibration:
    purpose: str
    sample_count: int
    median_input_tokens: int
    median_output_tokens: int
    observed_net_savings_tokens: int
    confidence: str

    def __post_init__(self) -> None:
        if not isinstance(self.purpose, str) or not self.purpose.strip():
            raise TokenAccountingError("calibration purpose is required")
        for field in (
            "sample_count",
            "median_input_tokens",
            "median_output_tokens",
            "observed_net_savings_tokens",
        ):
            value = getattr(self, field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise TokenAccountingError(f"{field} must be a non-negative integer")
        if self.confidence not in {"insufficient", "provisional", "calibrated"}:
            raise TokenAccountingError("calibration confidence is unknown")

    def to_document(self) -> dict[str, object]:
        return {
            "purpose": self.purpose,
            "sample_count": self.sample_count,
            "median_input_tokens": self.median_input_tokens,
            "median_output_tokens": self.median_output_tokens,
            "observed_net_savings_tokens": self.observed_net_savings_tokens,
            "confidence": self.confidence,
        }


def calibrate(
    records: Sequence[TokenRecord], *, minimum_samples: int = 5
) -> tuple[PurposeCalibration, ...]:
    """Build stable per-purpose medians without extrapolating sparse history."""

    if (
        not isinstance(minimum_samples, int)
        or isinstance(minimum_samples, bool)
        or minimum_samples < 1
    ):
        raise TokenAccountingError("minimum_samples must be positive")
    grouped: dict[str, list[TokenRecord]] = {}
    for record in records:
        if record.outcome == "succeeded":
            grouped.setdefault(record.purpose, []).append(record)
    result: list[PurposeCalibration] = []
    for purpose in sorted(grouped):
        usable: list[tuple[TokenRecord, int, int]] = []
        for record in grouped[purpose]:
            input_tokens = record.measurement.input_tokens
            output_tokens = record.measurement.output_tokens
            if input_tokens is not None and output_tokens is not None:
                usable.append((record, input_tokens, output_tokens))
        count = len(usable)
        inputs = [input_tokens for _, input_tokens, _ in usable]
        outputs = [output_tokens for _, _, output_tokens in usable]
        median_input = int(median_low(inputs)) if inputs else 0
        median_output = int(median_low(outputs)) if outputs else 0
        if count < minimum_samples:
            confidence = "insufficient"
            savings = 0
        else:
            confidence = "calibrated" if count >= minimum_samples * 2 else "provisional"
            observed = [
                max(
                    0,
                    avoided - input_tokens - output_tokens - record.coordination_tokens,
                )
                for record, input_tokens, output_tokens in usable
                if (avoided := record.avoided_input_tokens) is not None
            ]
            savings = int(median_low(observed)) if observed else 0
        result.append(
            PurposeCalibration(
                purpose=purpose,
                sample_count=count,
                median_input_tokens=median_input,
                median_output_tokens=median_output,
                observed_net_savings_tokens=savings,
                confidence=confidence,
            )
        )
    return tuple(result)


def calibration_document(
    calibrations: Sequence[PurposeCalibration],
) -> dict[str, object]:
    ordered = sorted(calibrations, key=lambda item: item.purpose)
    if len({item.purpose for item in ordered}) != len(ordered):
        raise TokenAccountingError("calibration purposes must be unique")
    return {
        "schema_version": 1,
        "kind": "hive-mind-token-calibration",
        "calibrations": [item.to_document() for item in ordered],
    }


class TokenLedger:
    """Single append seam for token records over the evidence ledger."""

    def __init__(self, ledger: EvidenceLedger | None = None) -> None:
        self.ledger = ledger if ledger is not None else EvidenceLedger()
        self._lock = RLock()
        self._recorded = {
            str(event["payload"]["record_digest"])
            for event in self.ledger.events()
            if event["event_type"] == "token.accounting"
            and isinstance(event["payload"], dict)
            and isinstance(event["payload"].get("record_digest"), str)
        }

    def record(self, record: TokenRecord) -> int:
        digest = record.record_digest
        with self._lock:
            if digest in self._recorded:
                raise TokenAccountingError("token record is already appended")
            sequence = self.ledger.append_event(
                record.run_id,
                "token.accounting",
                record.role,
                {"record_digest": digest, **record.to_document()},
            )
            self._recorded.add(digest)
            return sequence
