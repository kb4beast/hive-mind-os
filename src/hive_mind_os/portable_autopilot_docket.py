from __future__ import annotations

from .courtroom import (
    BurdenOfProof,
    Disposition,
    ImplementationState,
    SourceRecord,
    SourceStatus,
)
from .founding_docket import ClaimSpec

PORTABLE_AUTOPILOT_SOURCES: tuple[SourceRecord, ...] = (
    SourceRecord(
        id="SRC-024",
        title="Live subject-neutral GenericPrompt",
        uri="https://github.com/kb4beast/Junk/blob/760d5e2468484924cbdd077a78584f570a67bd2c/Generic%20prompt",
        kind="user_supplied_external_prompt",
        status=SourceStatus.PARTIAL,
        version_ref="git:760d5e2468484924cbdd077a78584f570a67bd2c:0fce4315bdaaaf0e1cf4ed5b57dfd15efacd4717",
        license_spdx=None,
        content_digest="sha256:f810b17311cebae09413abcfbb1c2155a4934d8ebefa483aadb512e36eed2c5b",
        provenance_complete=True,
        requires_complete_ingestion=True,
        object_type="remote_content_snapshot",
        retrieved_at="2026-08-11T13:36:00Z",
        snapshot_ref="evidence/sources/SRC-024-genericprompt-lineage/manifest.json",
    ),
    SourceRecord(
        id="SRC-025",
        title="Archived specialized GenericPrompt",
        uri="repository:docs/plan/genericprompt-execution-2026-08-09/SOURCE_GENERICPROMPT.txt",
        kind="user_supplied_prompt_snapshot",
        status=SourceStatus.PARTIAL,
        version_ref="sha256:9535faf5031411829ea3b940e059c6c7f22d38aec638c917ca8b6d7766ab250a",
        license_spdx=None,
        content_digest="sha256:9535faf5031411829ea3b940e059c6c7f22d38aec638c917ca8b6d7766ab250a",
        provenance_complete=False,
        requires_complete_ingestion=True,
        object_type="content_snapshot",
        retrieved_at="2026-08-09T00:00:00Z",
        snapshot_ref="evidence/sources/SRC-024-genericprompt-lineage/manifest.json",
    ),
)


PORTABLE_AUTOPILOT_CLAIMS: tuple[ClaimSpec, ...] = (
    ClaimSpec(
        "CLM-085",
        ("SRC-024",),
        "The live GenericPrompt wording cannot authorize copying or redistribution while its license remains unresolved",
        "source_license",
        disposition=Disposition.QUARANTINE,
        burden=BurdenOfProof.CAPTURE,
        state=ImplementationState.INVENTORIED,
        rationale="The object and digest are pinned, but the repository declares no reuse license; retain metadata and prohibit source-derived copying.",
    ),
    ClaimSpec(
        "CLM-086",
        ("SRC-024",),
        "Durable primary tasks, dependency-safe parallel waves, polling, recovery, and quiescence are hypotheses requiring independent implementation evidence rather than authority from a prompt",
        "portable_orchestration",
        disposition=Disposition.DEFER,
        burden=BurdenOfProof.DESIGN,
        state=ImplementationState.INVENTORIED,
        rationale="Evaluate independently expressed mechanisms through ADR-055 and executable tests; do not treat the unlicensed prompt as admitted design authority.",
    ),
    ClaimSpec(
        "CLM-087",
        ("SRC-025",),
        "The archived specialized GenericPrompt remains a separate incomplete source whose provenance and reuse rights are unresolved",
        "source_lineage",
        disposition=Disposition.DEFER,
        burden=BurdenOfProof.CAPTURE,
        state=ImplementationState.INVENTORIED,
        rationale="Preserve the snapshot and its digest without inferring authorship, license, or relationship to SRC-024.",
    ),
    ClaimSpec(
        "CLM-088",
        ("SRC-024", "SRC-025"),
        "No derivation, supersession, or equivalence relationship between the two GenericPrompt exhibits is established by current custody evidence",
        "source_lineage",
        disposition=Disposition.DEFER,
        burden=BurdenOfProof.CAPTURE,
        state=ImplementationState.INVENTORIED,
        rationale="A shared theme or filename is not chain-of-custody evidence; preserve the unresolved counterclaim explicitly.",
    ),
)
