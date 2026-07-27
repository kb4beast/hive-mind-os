from __future__ import annotations

from .courtroom import (
    BurdenOfProof,
    Disposition,
    ImplementationState,
    SourceRecord,
    SourceStatus,
)
from .founding_docket import ClaimSpec

SIBLING_GPT_SOURCES: tuple[SourceRecord, ...] = (
    SourceRecord(
        id="SRC-023",
        title="Sibling Hive OS Classic GPT Simulation Pack",
        uri="user-supplied-sibling:hive_os_classic_gpt_pack",
        kind="source_pack",
        status=SourceStatus.PARTIAL,
        version_ref="sha256:9d55be7e5d4e18fc77473e50afe8cb17dccb4e866f3c24317d300e1594455369",
        license_spdx=None,
        content_digest="sha256:9d55be7e5d4e18fc77473e50afe8cb17dccb4e866f3c24317d300e1594455369",
        provenance_complete=False,
        requires_complete_ingestion=True,
        object_type="content_snapshot",
        retrieved_at="2026-07-27T00:00:00-05:00",
        snapshot_ref="evidence/sources/SRC-023-classic-gpt-pack/manifest.json",
    ),
)


SIBLING_GPT_CLAIMS: tuple[ClaimSpec, ...] = (
    ClaimSpec(
        "CLM-081",
        ("SRC-023",),
        "The sibling classic-GPT pack is a reasoning simulation and cannot prove durable orchestration, independent agents, sandboxing, persistent memory, or external effects",
        "simulation_truthfulness",
        disposition=Disposition.DEFER,
        burden=BurdenOfProof.CAPTURE,
        state=ImplementationState.INVENTORIED,
        rationale="Preserve the broader pack separately from SRC-022 and defer reliance until its license and provenance are resolved.",
    ),
    ClaimSpec(
        "CLM-082",
        ("SRC-023",),
        "Classic-GPT request modes, selective role depth, compact output, and explicit maturity labels can improve usability only while preserving the truth and authority boundary",
        "simulation_interface",
        disposition=Disposition.DEFER,
        burden=BurdenOfProof.CAPTURE,
        state=ImplementationState.INVENTORIED,
        rationale="Capture the interface ideas without promoting them from a source whose reuse grant and chain of custody remain unresolved.",
    ),
    ClaimSpec(
        "CLM-083",
        ("SRC-023",),
        "A simulation label such as A5 must never grant money, credentials, root secrets, constitutional mutation, concealment, or unbounded replication authority",
        "authority_boundary",
        disposition=Disposition.DEFER,
        burden=BurdenOfProof.CAPTURE,
        state=ImplementationState.INVENTORIED,
        rationale="Preserve the conflict between broad simulation language and the constitutional authority boundary for later adjudication.",
    ),
    ClaimSpec(
        "CLM-084",
        ("SRC-023",),
        "The sibling imgo.jpg and Logo.png files are contextual exhibits whose provenance and underlying claims must be resolved before either can serve as independent proof",
        "image_provenance",
        disposition=Disposition.DEFER,
        burden=BurdenOfProof.CAPTURE,
        state=ImplementationState.INVENTORIED,
        rationale="imgo.jpg may share an origin with SRC-002 but has a different preserved digest; Logo.png is a derived visual summary. Neither may overwrite or independently prove the earlier record.",
    ),
)
