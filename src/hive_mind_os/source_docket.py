from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .additional_video_docket import ADDITIONAL_CLAIMS, ADDITIONAL_SOURCES
from .classic_gpt_docket import CLASSIC_GPT_CLAIMS, CLASSIC_GPT_SOURCES
from .courtroom import (
    CapabilityMaturity,
    Disposition,
    DocketAudit,
    DocketDecision,
    IdeaClaim,
    ImplementationState,
    SourceDocketAuditor,
    SourceRecord,
)
from .founding_docket import CLAIMS as FOUNDING_CLAIMS
from .founding_docket import SOURCES as FOUNDING_SOURCES
from .founding_docket import ClaimSpec
from .recursive_improvement_docket import (
    RECURSIVE_IMPROVEMENT_CLAIMS,
    RECURSIVE_IMPROVEMENT_SOURCES,
)
from .sibling_gpt_docket import SIBLING_GPT_CLAIMS, SIBLING_GPT_SOURCES

SOURCES = (
    *FOUNDING_SOURCES,
    *ADDITIONAL_SOURCES,
    *RECURSIVE_IMPROVEMENT_SOURCES,
    *CLASSIC_GPT_SOURCES,
    *SIBLING_GPT_SOURCES,
)
CLAIMS = (
    *FOUNDING_CLAIMS,
    *ADDITIONAL_CLAIMS,
    *RECURSIVE_IMPROVEMENT_CLAIMS,
    *CLASSIC_GPT_CLAIMS,
    *SIBLING_GPT_CLAIMS,
)


@dataclass(frozen=True, slots=True)
class FoundingSourceDocket:
    schema_version: int
    sources: tuple[SourceRecord, ...]
    claims: tuple[IdeaClaim, ...]
    decisions: tuple[DocketDecision, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(f"unsupported source docket schema: {self.schema_version}")
        source_ids = [source.id for source in self.sources]
        claim_ids = [claim.id for claim in self.claims]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source docket contains duplicate source ids")
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("source docket contains duplicate claim ids")

    def audit(self) -> DocketAudit:
        return SourceDocketAuditor().audit(self.sources, self.claims, self.decisions)

    @property
    def source_count(self) -> int:
        return len(self.sources)

    @property
    def claim_count(self) -> int:
        return len(self.claims)

    @property
    def inventory_digest(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "sources": [source.to_contract() for source in self.sources],
            "claims": [claim.to_contract() for claim in self.claims],
            "decisions": [decision.to_contract() for decision in self.decisions],
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def _claim(spec: ClaimSpec) -> IdeaClaim:
    architecture_refs = (
        ()
        if spec.disposition in {Disposition.DEFER, Disposition.REJECT, Disposition.QUARANTINE}
        else (
            f"docs/architecture/CONGLOMERATED_SYSTEM.md#{spec.section}",
            "docs/architecture/COURTROOM_SYNTHESIS.md",
        )
    )
    acceptance_tests = (
        ()
        if not architecture_refs
        else (f"AT-{spec.id}: prove {spec.proposition.lower()}",)
    )
    return IdeaClaim(
        id=spec.id,
        case_id=spec.id.replace("CLM", "CASE"),
        proposition=spec.proposition,
        source_ids=spec.sources,
        category=spec.category,
        burden=spec.burden,
        architecture_refs=architecture_refs,
        acceptance_tests=acceptance_tests,
        outcome_metrics=spec.metrics,
        code_refs=spec.code_refs,
        test_refs=spec.test_refs,
        benchmark_refs=spec.benchmark_refs,
        comparator_source_ids=spec.comparators,
        implementation_state=spec.state,
        capability_maturity=(
            CapabilityMaturity.STRUCTURALLY_PROTOTYPED
            if spec.state in {ImplementationState.IMPLEMENTED, ImplementationState.VALIDATED}
            else CapabilityMaturity.SPECIFIED
        ),
    )


def _decision(spec: ClaimSpec) -> DocketDecision:
    if spec.disposition is Disposition.ADOPT:
        advocate = f"The source presents {spec.proposition.lower()} as a material operating-system capability."
        cross = "Challenge reproducibility, security, licensing, cost, failure recovery, correlated model error, and self-approval."
    elif spec.disposition is Disposition.ADAPT:
        advocate = f"The mechanism behind this claim can strengthen Hive Mind OS: {spec.proposition}"
        cross = "Preserve the mechanism only after removing source-specific assumptions and adding evidence, policy, isolation, and rollback controls."
    else:
        advocate = f"The source or claim may contain useful evidence: {spec.proposition}"
        cross = "The current evidence is insufficient for architecture or promotion; do not fill gaps with model inference."

    return DocketDecision(
        claim_id=spec.id,
        disposition=spec.disposition,
        rationale=spec.rationale
        or "Adopt or adapt only behind enforceable evidence, authority, recovery, and outcome gates.",
        advocate_case=advocate,
        cross_examination=cross,
        expert_findings=(
            "Product: tie the idea to measurable customer value.",
            "Architecture: use replaceable contracts and explicit failure modes.",
            "Security/SRE: fail closed, isolate execution, retain audit and rollback evidence.",
        ),
    )


def load_default_source_docket() -> FoundingSourceDocket:
    return FoundingSourceDocket(
        schema_version=1,
        sources=SOURCES,
        claims=tuple(_claim(spec) for spec in CLAIMS),
        decisions=tuple(_decision(spec) for spec in CLAIMS),
    )


def load_source_docket(
    repository: str | Path | None = None,
) -> FoundingSourceDocket:
    """Load the immutable founding docket plus admitted additive reconciliations."""

    docket = load_default_source_docket()
    if repository is None:
        return docket
    from .ingestion import reconcile_docket

    return reconcile_docket(docket, repository)
