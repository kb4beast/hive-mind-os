"""Controlled token comparator for the portable DAG context lane."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Sequence

from .runtime_contracts import (
    canonical_digest,
    raw_sha256,
    require_digest,
    require_identifier,
)


class TokenBenchmarkError(ValueError):
    """A token comparison is unmeasured or not controlled."""


TOKENIZER_ID = "hive-mind-portable-lexical-tokenizer-v1"
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[^\sA-Za-z0-9_]", re.UNICODE)


@dataclass(frozen=True, slots=True)
class BenchmarkControls:
    acceptance_digest: str
    authority_digest: str
    subject_snapshot_digest: str
    model_route_digest: str
    budget_digest: str

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            require_digest(getattr(self, name), name)

    def to_document(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class TokenBenchmarkLane:
    lane_id: str
    subject_class: str
    comparator_digest: str
    challenger_digest: str
    controls: BenchmarkControls
    comparator_input_tokens: int
    challenger_input_tokens: int
    repetitions: int
    measurement_source: str
    tokenizer_id: str
    accepted_outcome_digest: str

    def __post_init__(self) -> None:
        require_identifier(self.lane_id, "lane_id")
        require_identifier(self.subject_class, "subject_class")
        require_digest(self.comparator_digest, "comparator_digest")
        require_digest(self.challenger_digest, "challenger_digest")
        if self.comparator_digest == self.challenger_digest:
            raise TokenBenchmarkError("comparator and challenger must be distinct")
        if not isinstance(self.controls, BenchmarkControls):
            raise TokenBenchmarkError("benchmark controls are required")
        for name in (
            "comparator_input_tokens",
            "challenger_input_tokens",
            "repetitions",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise TokenBenchmarkError(f"{name} must be a positive measured integer")
        if self.measurement_source not in {"provider-measured", "tokenizer-measured"}:
            raise TokenBenchmarkError(
                "static estimates cannot qualify the token benchmark"
            )
        require_identifier(self.tokenizer_id, "tokenizer_id")
        require_digest(self.accepted_outcome_digest, "accepted_outcome_digest")

    @property
    def saved_tokens(self) -> int:
        return self.comparator_input_tokens - self.challenger_input_tokens

    @property
    def reduction_basis_points(self) -> int:
        return (self.saved_tokens * 10_000) // self.comparator_input_tokens

    def to_document(self) -> dict[str, Any]:
        return {
            "lane_id": self.lane_id,
            "subject_class": self.subject_class,
            "comparator_digest": self.comparator_digest,
            "challenger_digest": self.challenger_digest,
            "controls": self.controls.to_document(),
            "comparator_input_tokens": self.comparator_input_tokens,
            "challenger_input_tokens": self.challenger_input_tokens,
            "saved_tokens": self.saved_tokens,
            "reduction_basis_points": self.reduction_basis_points,
            "repetitions": self.repetitions,
            "measurement_source": self.measurement_source,
            "tokenizer_id": self.tokenizer_id,
            "accepted_outcome_digest": self.accepted_outcome_digest,
        }


@dataclass(frozen=True, slots=True)
class TokenBenchmarkReport:
    lanes: tuple[TokenBenchmarkLane, ...]
    comparator_input_tokens: int
    challenger_input_tokens: int
    reduction_basis_points: int
    threshold_basis_points: int
    threshold_met: bool
    disposition: str
    forbidden_claim: str
    report_digest: str = ""

    def __post_init__(self) -> None:
        if not self.lanes:
            raise TokenBenchmarkError("benchmark report requires lanes")
        expected = canonical_digest(self.to_document(include_digest=False))
        if not self.report_digest:
            object.__setattr__(self, "report_digest", expected)
        elif self.report_digest != expected:
            raise TokenBenchmarkError("benchmark report digest is invalid")

    def to_document(self, *, include_digest: bool = True) -> dict[str, Any]:
        result = {
            "schema_version": 1,
            "kind": "hive-mind-controlled-token-benchmark-v1",
            "lanes": [lane.to_document() for lane in self.lanes],
            "comparator_input_tokens": self.comparator_input_tokens,
            "challenger_input_tokens": self.challenger_input_tokens,
            "reduction_basis_points": self.reduction_basis_points,
            "threshold_basis_points": self.threshold_basis_points,
            "threshold_met": self.threshold_met,
            "disposition": self.disposition,
            "forbidden_claim": self.forbidden_claim,
        }
        if include_digest:
            result["report_digest"] = self.report_digest
        return result


def build_token_benchmark_report(
    lanes: Sequence[TokenBenchmarkLane], *, threshold_basis_points: int = 3_000
) -> TokenBenchmarkReport:
    """Aggregate measured lanes without converting a narrow result to superiority."""

    values = tuple(lanes)
    if not values or len({lane.lane_id for lane in values}) != len(values):
        raise TokenBenchmarkError("benchmark lanes are required and must be unique")
    if (
        type(threshold_basis_points) is not int
        or not 0 < threshold_basis_points < 10_000
    ):
        raise TokenBenchmarkError(
            "threshold_basis_points must be between zero and 10000"
        )
    comparator = sum(lane.comparator_input_tokens for lane in values)
    challenger = sum(lane.challenger_input_tokens for lane in values)
    reduction = ((comparator - challenger) * 10_000) // comparator
    threshold_met = reduction >= threshold_basis_points and all(
        lane.saved_tokens > 0 for lane in values
    )
    return TokenBenchmarkReport(
        lanes=values,
        comparator_input_tokens=comparator,
        challenger_input_tokens=challenger,
        reduction_basis_points=reduction,
        threshold_basis_points=threshold_basis_points,
        threshold_met=threshold_met,
        disposition="MEASURED_LOWER_INPUT_CONTEXT"
        if threshold_met
        else "THRESHOLD_NOT_MET",
        forbidden_claim="No product superiority, quality parity, or outcome improvement is established.",
    )


def measure_lexical_tokens(text: str) -> int:
    """Measure deterministic portable token units from exact Unicode text."""

    if type(text) is not str or not text:
        raise TokenBenchmarkError("tokenizer input must be non-empty text")
    return len(_TOKEN_PATTERN.findall(text))


def controlled_fixture_lanes() -> tuple[TokenBenchmarkLane, ...]:
    """Build reproducible synthetic lanes from exact comparator/challenger text."""

    roles = (
        "orchestrator",
        "explorer",
        "architect",
        "builder",
        "curator",
        "integrator",
        "steward",
        "optimizer",
    )
    subject_sizes = (
        ("repository", 24),
        ("monorepo", 40),
        ("research-artifact", 20),
        ("workflow", 16),
    )
    result: list[TokenBenchmarkLane] = []
    for subject_class, record_count in subject_sizes:
        records = tuple(
            (
                f"{subject_class}-claim-{index:03d} requires evidence-{index:03d}, "
                f"acceptance-{index:03d}, rollback-{index:03d}, and authority-local"
            )
            for index in range(record_count)
        )
        shared = (
            f"subject={subject_class}\nrequest=portable-dag-v4\n"
            "authority=local-reversible-only\nacceptance=all-claims-retained\n"
        )
        comparator_text = shared + "\n".join(
            f"delivery={role}|{record}" for role in roles for record in records
        )
        challenger_text = shared + "\n".join(
            f"direct={roles[index % len(roles)]}|{record}"
            for index, record in enumerate(records)
        )
        challenger_text += "\n" + "\n".join(
            f"cold-ref={raw_sha256(record.encode('utf-8'))}" for record in records
        )
        controls = BenchmarkControls(
            canonical_digest({"acceptance": list(records)}),
            canonical_digest({"allowed": ["inspect", "local-test"]}),
            canonical_digest(
                {"subject_class": subject_class, "records": list(records)}
            ),
            canonical_digest({"route": "same-deterministic-fixture-route-v1"}),
            canonical_digest({"input_limit": 100_000, "output_limit": 20_000}),
        )
        outcome = canonical_digest(
            {"accepted_claim_ids": [record.split(" ", 1)[0] for record in records]}
        )
        result.append(
            TokenBenchmarkLane(
                f"lane-{subject_class}",
                subject_class,
                raw_sha256(comparator_text.encode("utf-8")),
                raw_sha256(challenger_text.encode("utf-8")),
                controls,
                measure_lexical_tokens(comparator_text),
                measure_lexical_tokens(challenger_text),
                5,
                "tokenizer-measured",
                TOKENIZER_ID,
                outcome,
            )
        )
    return tuple(result)


def controlled_fixture_report() -> TokenBenchmarkReport:
    """Return the bounded checked comparator report used by qualification."""

    return build_token_benchmark_report(controlled_fixture_lanes())


__all__ = [
    "BenchmarkControls",
    "TokenBenchmarkError",
    "TokenBenchmarkLane",
    "TokenBenchmarkReport",
    "TOKENIZER_ID",
    "build_token_benchmark_report",
    "controlled_fixture_lanes",
    "controlled_fixture_report",
    "measure_lexical_tokens",
]
